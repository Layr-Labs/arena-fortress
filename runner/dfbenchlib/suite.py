"""Suites (runner/suites/*.json, format in runner/README.md) and running many games in parallel."""
import glob, json, os, re
from concurrent.futures import ThreadPoolExecutor

from . import ROOT
from .game import DAYS_PER_YEAR, Game, crash_twice, docker_mem_mb, log, mem_mb, scenario_task_id


def load_suite(path):
    s = json.load(open(path))
    if s.get("schema") != "dfbench-suite/1":
        raise SystemExit(f"{path}: schema must be dfbench-suite/1")
    return s


def task_budget(t, suite, override=None):
    """Per-game credits: --budget wins; else the task's budget_usd; else the suite's rate x days / 336."""
    if override is not None:
        return float(override)
    if t.get("budget_usd") is not None:
        return float(t["budget_usd"])
    rate = float(suite.get("budget_usd_per_game_year", 0.50))
    return round(rate * t["days"] / DAYS_PER_YEAR, 4)


def expand(suite, stages=None, only=None, seed=None, n=None, budget=None):
    """-> game specs for the suite's tasks (stage filter, explicit game ids, seed/n overrides)."""
    out = []
    for t in suite["tasks"]:
        if stages and t.get("stage", 1) not in stages:
            continue
        if only and t["id"] not in only and not any(g.startswith(t["id"] + "-") for g in only):
            continue                     # load only the tasks that will run
        path = os.path.join(ROOT, t["scenario"])
        if not os.path.exists(path):
            raise SystemExit(f"task {t['id']}: its task file {t['scenario']} is missing from this checkout")
        sc = json.load(open(path))
        days = int(t.get("days") or sc.get("days"))
        t = {**t, "days": days}
        for k in range(int(n or t.get("n", 8))):
            gid = f"{t['id']}-{k}"
            if only and gid not in only and t["id"] not in only:
                continue
            out.append({"game_id": gid, "task_id": t["id"], "kind": t.get("kind", "outcome"),
                        "family": t.get("family", t["id"]), "stage": t.get("stage", 1), "predicate": t.get("predicate"),
                        "scenario": t["scenario"], "k": k,
                        "seed": int(seed if seed is not None else suite.get("seed", 12345)),
                        "days": days, "wall_s": float(t.get("wall_s") or suite.get("wall_s_per_game_year", 5400) * days / DAYS_PER_YEAR),
                        "budget_usd": task_budget(t, suite, budget), "strange_moods": bool(t.get("strange_moods", False)),
                        "actions_per_game_day": suite.get("rules", {}).get("actions_per_game_day", 40),
                        "max_advance_days": suite.get("rules", {}).get("max_advance_days", 28)})
    return out


def missing_forts(specs):
    """Start forts the given games need that aren't on disk (real DF stack only): [(task id, fort path)]. Forts are
    looked up where the game container mounts them (DFBENCH_SNAPSHOTS_DIR, default scenarios/snapshots/)."""
    import sys
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from bench import key as BK       # the game's own start-fort resolution (fort_start_snapshot -> seed-built default)
    snaps = os.environ.get("DFBENCH_SNAPSHOTS_DIR") or os.path.join(ROOT, "scenarios", "snapshots")
    out, seen = [], set()
    for s in specs:
        if s["scenario"] in seen:
            continue
        seen.add(s["scenario"])
        sc = json.load(open(os.path.join(ROOT, s["scenario"])))
        starts = list(sc.get("snapshot_pool") or []) or [sc.get("snapshot", "fort_start_snapshot")]
        for p in starts:
            if p.startswith("scenarios/snapshots/"):
                full = os.path.join(snaps, p[len("scenarios/snapshots/"):])
            else:
                full = BK.start_snapshot(p)
                if full.startswith(os.path.join(ROOT, "scenarios", "snapshots") + os.sep):
                    full = os.path.join(snaps, os.path.relpath(full, os.path.join(ROOT, "scenarios", "snapshots")))
            if not os.path.exists(os.path.join(full, "world.sav")):
                out.append((s["task_id"], full))
    return out


def check_forts(specs, stack):
    """Fail fast, before any container starts, if a game's start fort hasn't been built."""
    if stack == "fake":
        return
    miss = missing_forts(specs)
    if miss:
        lines = "\n".join(f"  {t}: {p}" for t, p in miss)
        raise SystemExit("start forts not built yet:\n" + lines + "\nbuild them with .yukon/setup.sh (labs, MY1, OP1; "
                         "docs/SEED-FORTS.md), or point DFBENCH_SNAPSHOTS_DIR at a directory that has them")


def resolve_scenario(x):
    """A scenario path (absolute, cwd- or repo-relative), or a bare name: scenarios/<x>.json, scenarios/seed/<x>.json,
    else the scenario whose `name` or `id` is x."""
    for p in (x, os.path.join(ROOT, x), os.path.join(ROOT, "scenarios", x + ".json"),
              os.path.join(ROOT, "scenarios", "seed", x + ".json")):
        if os.path.isfile(p):
            return os.path.abspath(p)
    for p in sorted(glob.glob(os.path.join(ROOT, "scenarios", "**", "*.json"), recursive=True)):
        try:
            sc = json.load(open(p))
        except (ValueError, OSError):
            continue
        if isinstance(sc, dict) and x in (sc.get("name"), sc.get("id")):
            return p
    raise SystemExit(f"no scenario {x!r} (a path, or a name under scenarios/)")


DEFAULT_SUITE = os.path.join(ROOT, "runner", "suites", "season0.json")


def local_task(scenario, seed, n, budget, wall_s=None, suite_path=DEFAULT_SUITE):
    """A one-task 'suite' for `dfbench local run --task scenarios/X.json`. If the season's suite has a task on the
    same scenario, its settings (anchor, wall cap, strange_moods, budget rule, weights) are used."""
    path = resolve_scenario(scenario)
    sc = json.load(open(path))
    rel = os.path.relpath(os.path.abspath(path), ROOT)
    base = load_suite(suite_path) if suite_path and os.path.exists(suite_path) else {}
    for t in base.get("tasks") or []:
        if os.path.normpath(t["scenario"]) == os.path.normpath(rel):
            t = {**t, "n": n}
            if budget is not None:
                t["budget_usd"] = budget
            if wall_s:
                t["wall_s"] = wall_s
            keep = {k: base[k] for k in ("rules", "budget_usd_per_game_year", "wall_s_per_game_year", "weights",
                                         "bootstrap", "lab_z", "infra", "anchors_note") if k in base}
            return {"schema": "dfbench-suite/1", "name": f"local-{t['id']}", "seed": seed, **keep, "tasks": [t]}
    tid = scenario_task_id(sc, scenario)
    lab = bool(re.match(r"^LT\d\d$", tid))
    days = int(sc.get("days") or 60)
    t = {"id": tid, "kind": "lab" if lab else "outcome", "family": "labs" if lab else tid, "predicate": tid if lab else None,
         "scenario": rel, "n": n, "days": days, "stage": 1,
         "wall_s": wall_s or max(1800, 5400 * days / DAYS_PER_YEAR), "budget_usd": budget,
         "strange_moods": bool(sc.get("strange_moods", False))}
    return {"schema": "dfbench-suite/1", "name": f"local-{tid}", "seed": seed, "tasks": [t]}


def run_games(specs, opt, out_dir, parallel=1, retries=1):
    """Run every spec (up to `parallel` at once); infra failures are re-run up to `retries` times."""
    os.makedirs(out_dir, exist_ok=True)
    need = parallel * (mem_mb(opt.get("game_mem", "3g")) + mem_mb(opt.get("harness_mem", "2g")) + 512)
    have = docker_mem_mb()
    if have and need > have and opt.get("stack") != "fake":
        log(f"warning: --parallel {parallel} may need ~{need} MB; the Docker VM has {have} MB")

    def one(spec):
        rec, causes = None, []
        for attempt in range(retries + 1):
            g = Game(spec, opt, out_dir)
            rec = g.run()
            rec["attempt"] = attempt
            if rec["status"] != "ok":
                causes.append(rec.get("infra_cause"))
                if crash_twice(causes):
                    # DF crashed or hung on two attempts: scored at the state reached, not re-run (SCORING.md §6)
                    rec["crash_twice"] = True
            with open(os.path.join(g.dir, "game.json"), "w") as f:
                json.dump(rec, f, indent=1)
            if rec["status"] == "ok" or rec.get("crash_twice"):
                break
            log(f"{spec['game_id']}: attempt {attempt} {rec['status']}; " + ("retrying" if attempt < retries else "giving up"))
        return rec

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as ex:
        return list(ex.map(one, specs))
