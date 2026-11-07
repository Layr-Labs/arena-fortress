"""Reading `dfbench local run` / `local suite` output directories (the challenge's docs/GAME-API.md §6 artifacts).

A run directory holds one directory per game (`<TASK>-<k>/` with `game.json`, `game/`, `gateway/`), possibly
nested under per-task directories, plus `score.json`, `score_detail.json` and `suite.json`. Nothing under a game's
`harness/` is read: that's the harness's own output, which the official scorer never reads either.
"""
import glob, json, os

from . import challenge

LAB_PREFIX = "LT"


def _load(p, default=None):
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _jsonl(p):
    out = []
    try:
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


def game_dirs(run_dir):
    """Every game directory under run_dir (has game.json and game/), skipping retried attempts (attempt-*)."""
    out = []
    for p in sorted(glob.glob(os.path.join(run_dir, "**", "game.json"), recursive=True)):
        d = os.path.dirname(p)
        rel = os.path.relpath(d, run_dir).split(os.sep)
        if os.path.isdir(os.path.join(d, "game")) and not any(x.startswith("attempt-") for x in rel):
            out.append(d)
    return out


class Game:
    """One game's artifacts, loaded lazily."""

    def __init__(self, d):
        self.dir = d
        self.rec = _load(os.path.join(d, "game.json"), {}) or {}
        self.spec = self.rec.get("spec") or {}
        self.id = self.spec.get("game_id") or os.path.basename(d)
        self.task = self.spec.get("task_id") or self.id.rsplit("-", 1)[0]
        self.k = self.spec.get("k")
        self.seed = self.spec.get("seed")
        self._cache = {}

    def _game_file(self, suffix):
        hits = sorted(glob.glob(os.path.join(self.dir, "game", f"*{suffix}")))
        return hits[0] if hits else None

    @property
    def summary(self):
        if "summary" not in self._cache:
            rows = [r for r in _jsonl(os.path.join(self.dir, "game", "summary.jsonl")) if not r.get("crashed")]
            self._cache["summary"] = rows[-1] if rows else {}
        return self._cache["summary"]

    @property
    def daily(self):
        if "daily" not in self._cache:
            p = self._game_file(".daily.json")
            self._cache["daily"] = _load(p, {}) if p else {}
        return self._cache["daily"]

    @property
    def samples(self):
        return (self.daily or {}).get("samples") or []

    @property
    def events(self):
        e = (self.daily or {}).get("events") or {}
        return e if isinstance(e, dict) else {}

    @property
    def api(self):
        if "api" not in self._cache:
            p = self._game_file(".api.jsonl")
            self._cache["api"] = _jsonl(p) if p else []
        return self._cache["api"]

    @property
    def usage(self):
        if "usage" not in self._cache:
            self._cache["usage"] = _jsonl(os.path.join(self.dir, "gateway", "usage.jsonl"))
        return self._cache["usage"]

    @property
    def gateway_status(self):
        return _load(os.path.join(self.dir, "gateway", "gateway-status.json"), {}) or {}


def _detail_records(run_dir):
    """game_id -> the scorer's per-game record, from every score_detail.json under run_dir."""
    out = {}
    for p in glob.glob(os.path.join(run_dir, "**", "score_detail.json"), recursive=True):
        for g in (_load(p, {}) or {}).get("games") or []:
            if g.get("game_id"):
                out[g["game_id"]] = g
    return out


def _suite_tasks(run_dir):
    """task id -> task definition, merged from every suite.json under (or above) run_dir."""
    tasks, weights, anchors, boot, zlim = {}, None, {}, None, None
    paths = glob.glob(os.path.join(run_dir, "**", "suite.json"), recursive=True)
    if not paths:
        up = os.path.join(os.path.dirname(os.path.abspath(run_dir)), "suite.json")
        paths = [up] if os.path.exists(up) else []
    for p in sorted(paths):
        s = _load(p, {}) or {}
        weights = weights or s.get("weights")
        boot = boot or s.get("bootstrap")
        lz = s.get("lab_z") or {}
        zlim = zlim or (lz.get("floor"), lz.get("cap", 1.5))
        for t in s.get("tasks") or []:
            tasks.setdefault(t["id"], t)
            if t.get("anchor"):
                anchors[t["id"]] = t["anchor"]
    for p in glob.glob(os.path.join(run_dir, "**", "score_detail.json"), recursive=True):
        d = _load(p, {}) or {}
        weights = weights or d.get("weights")
        for k, v in (d.get("anchors") or {}).items():
            anchors.setdefault(k, v)
    return tasks, weights, anchors, boot, zlim


def suite_config(path):
    """(tasks by id, weights, anchors, bootstrap, zlim) from one suite file (runner/suites/*.json)."""
    s = _load(path, None)
    if not s:
        raise SystemExit(f"not a suite file: {path}")
    lz = s.get("lab_z") or {}
    tasks = {t["id"]: t for t in s.get("tasks") or []}
    anchors = {t["id"]: t["anchor"] for t in tasks.values() if t.get("anchor")}
    return tasks, s.get("weights"), anchors, s.get("bootstrap"), (lz.get("floor"), lz.get("cap", 1.5))


def default_suite_path(start):
    """The challenge clone's public suite (what local runs are scored against), or None outside a clone."""
    root = challenge.find_root(start)
    p = os.path.join(root, "runner", "suites", "season0-public.json") if root else None
    return p if p and os.path.exists(p) else None


class Run:
    """A run directory: its games, their scored records, and the suite definition to aggregate them."""

    def __init__(self, run_dir, rescore=True, suite=None):
        self.dir = os.path.abspath(run_dir)
        if not os.path.isdir(self.dir):
            raise SystemExit(f"not a directory: {run_dir}")
        self.games = [Game(d) for d in game_dirs(self.dir)]
        if not self.games:
            raise SystemExit(f"no games under {run_dir} (expected <TASK>-<k>/game.json from `dfbench local run`)")
        score, self.outcomes = challenge.scorer(self.dir)
        detail = _detail_records(self.dir)
        self.scored_by = "score_detail.json"
        recs = {}
        for g in self.games:
            r = None
            if score is not None and rescore:
                try:
                    r = score.score_game(g.dir)
                    self.scored_by = "challenge scorer"
                except Exception:
                    r = None
            recs[g.id] = r or detail.get(g.id)
        self.records = recs
        tasks, weights, anchors, boot, zlim = _suite_tasks(self.dir)
        self.suite_source = "the run's own suite.json / score_detail.json"
        if suite:
            st, sw, sa, sb, sz = suite_config(suite)
            tasks = {**tasks, **st}
            weights, anchors, boot, zlim = sw or weights, {**anchors, **sa}, sb or boot, sz
            self.suite_source = os.path.relpath(suite)
        for g in self.games:
            if g.task not in tasks:
                lab = (g.spec.get("kind") == "lab") or g.task.startswith(LAB_PREFIX)
                tasks[g.task] = {"id": g.task, "kind": "lab" if lab else "outcome",
                                 "family": "labs" if lab else (g.spec.get("family") or g.task)}
        self.tasks = [{"id": t["id"], "kind": t.get("kind", "outcome"), "family": t.get("family", t["id"]),
                       "stage": t.get("stage", 1), "zlim": zlim or (None, 1.5)} for t in tasks.values()]
        self.weights = weights or {"OP1": 0.5, "MY1": 0.3, "labs": 0.2}
        self.anchors = anchors
        self.bootstrap_cfg = boot or {"resamples": 10000, "seed": 0, "alpha": 0.05}
        self.label = os.path.relpath(self.dir)

    def labels(self):
        """What the run is (fake, mixed or real stack; full, partial, single-task or smoke; local or official; which
        suite and anchors), from its score.json (dfbench writes these labels), else from run.json and the games."""
        m = (_load(os.path.join(self.dir, "score.json"), {}) or {}).get("metrics") or {}
        meta = _load(os.path.join(self.dir, "run.json"), {}) or {}
        lab = {k: m.get(k) for k in ("result_kind", "stack", "scope", "tasks_played", "anchors_id", "suite",
                                     "official_comparable")}
        lab["stack"] = lab["stack"] or meta.get("stack")
        lab["result_kind"] = lab["result_kind"] or "local"
        lab["tasks_played"] = lab["tasks_played"] or ",".join(sorted({g.task for g in self.games}))
        if m.get("watch") or meta.get("watch"):   # `dfbench local ... --watch`: rendered DF, never comparable
            lab["watch"] = True
        return lab

    def ok_records(self):
        return [r for r in self.records.values() if r and r.get("status") == "ok"]

    def by_task(self):
        out = {}
        for r in self.ok_records():
            if self._scorable(r):
                out.setdefault(r["task"], []).append(r)
        return out

    def _scorable(self, r):
        lab = next((t for t in self.tasks if t["id"] == r["task"]), {}).get("kind") == "lab"
        return ("partial" in r) if lab else ("O" in r)

    def game(self, gid):
        return next((g for g in self.games if g.id == gid), None)
