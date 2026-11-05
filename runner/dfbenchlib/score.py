"""Trusted scoring of a run directory into score.json (docs/HARNESS-CHALLENGE.md §4.2; runner/README.md).

Inputs, trusted only: each game's `game/` (the game server's §6 artifacts), `gateway/usage.jsonl` (the gateway
ledger) and the runner's own `game.json`. Nothing under `harness/` is ever read.

Per game: outcome O (bench/outcomes.py, score v5) for outcome tasks (OP1, MY1); lab partial credit
(bench/predicates.py) for lab tasks. Per task: mean O, or mean partial normalised to noop 0 / witness 1
(BENCHMARK-v1 §3.2: z = (p - p_noop) / (p_witness - p_noop), capped at 1.5, not floored), reported x100.
Suite: S = sum_f w_f * F_f / sum_f w_f over the families present (OP1 0.5, MY1 0.3, labs 0.2 = the mean of the lab
task scores). Published scalar: the one-sided 95% lower bound of S by a stratified bootstrap over games (each task's
games resampled with replacement within the task), seeded.
"""
import glob, hashlib, json, os, random, re, sys

from . import ROOT, RUNNER_VERSION
from . import df_adapter
from .game import DAYS_PER_YEAR, ledger_summary

sys.path.insert(0, os.path.join(ROOT, "framework"))
from harnessarena import adapter as A, suite as SU   # noqa: E402

SCORE_VERSION = "s0-score/1"
PRED = df_adapter.PRED          # compatibility: the DF lab predicates now live in the DF adapter
Z_CAP = 1.5


def suite_key(keys):
    """One flat comparability key for score.json (Yukon shows one row per flat metric). Each game's key includes its
    task's hash, so a real suite has one key per task: report a digest over the sorted keys and their count."""
    if not keys:
        return None
    if len(keys) == 1:
        return keys[0]
    h = hashlib.sha256("\n".join(keys).encode()).hexdigest()[:16]
    return f"{keys[0].split('|')[0]}|suite:{h}|keys:{len(keys)}"


def _read_row(gdir):
    return df_adapter.DF.read_episode(gdir)


def score_game(game_dir, adapter=None):
    """-> per-game record from trusted artifacts, or one with status != 'ok' (excluded from the score). The
    environment-specific parts (the episode record, the per-episode score) come from the adapter."""
    ad = adapter or df_adapter.DF
    with open(os.path.join(game_dir, "game.json")) as f:
        rec = json.load(f)
    spec = rec["spec"]
    out = {"game_id": spec["game_id"], "task": spec["task_id"], "kind": spec.get("kind"), "family": spec.get("family"),
           "stage": spec.get("stage", 1), "k": spec["k"], "status": rec.get("status"), "notes": list(rec.get("notes") or [])}
    g = os.path.join(game_dir, "game")
    row = ad.read_episode(g)
    led = ledger_summary(os.path.join(game_dir, "gateway", "usage.jsonl"))
    try:
        with open(os.path.join(game_dir, "gateway", "gateway-status.json")) as f:
            gst = json.load(f)
    except (OSError, ValueError):
        gst = {}
    out["ledger"] = led
    out["blocked_reason"] = gst.get("blocked_reason")
    out["price_table_hash"] = gst.get("price_table_hash") or led.get("price_table_hash")
    if rec.get("crash_twice"):
        return _score_crashed(out, g, spec, rec, ad)
    if (gst.get("usage_unknown_calls") or 0) > 0 or led["usage_missing"]:
        out["status"] = "infra"
        out["notes"].append("usage unknown on a gateway call (fail closed): infra")
        return out
    if gst.get("blocked_reason") == "upstream_unreliable":
        out["status"] = "infra"
        out["notes"].append("the provider hung or lost too many calls (gateway upstream_unreliable): infra")
        return out
    if rec.get("status") != "ok" or row is None:
        out["status"] = rec.get("status") if rec.get("status") != "ok" else "infra"
        if row is None:
            out["notes"].append("no summary row")
        return out
    ep = ad.episode_fields(row)
    tw = gst.get("throttle_wait_total_s")
    tw = led["throttle_wait_s"] if tw is None else float(tw)
    out.update(throttle_wait_s=round(min(tw, float(ep.get("wall_s") or rec.get("wall_s") or 0)), 2))
    out.update(ep)
    try:
        sc = ad.score_episode(g, row, spec)
    except A.EpisodeInfra as e:
        out["status"] = "infra"
        out["notes"].append(str(e))
        return out
    out["notes"].extend(sc.pop("notes", []))
    out.update(sc)
    return out


ZERO_S = df_adapter.ZERO_S      # compatibility


def _score_crashed(out, g, spec, rec, ad=None):
    """The environment crashed or hung on the game's re-run too (challenge/SCORING.md §6): scored at the state
    reached (the adapter's score_crashed). Not infra, so it can't be used to re-roll a game."""
    ad = ad or df_adapter.DF
    out.update(status="ok", crash_twice=True, throttle_wait_s=0.0, wall_capped=False)
    out["notes"].append("DF crashed or hung on two attempts: scored at the state reached")
    sc = ad.score_crashed(g, spec, rec)
    out["notes"].extend(sc.pop("notes", []))
    out.update(sc)
    return out


def task_value(task, games, anchors):
    """Mean O (outcome tasks) or 100 * z of the mean partial (lab tasks), z clipped to zlim = (floor, cap)."""
    if task["kind"] == "lab":
        p = sum(g["partial"] for g in games) / len(games)
        a = anchors.get(task["id"]) or {"noop": 0.0, "witness": 1.0}
        den = a["witness"] - a["noop"]
        z = (p - a["noop"]) / den if den > 0 else 0.0
        lo, hi = task.get("zlim") or (None, Z_CAP)
        z = min(hi, z) if hi is not None else z
        z = max(lo, z) if lo is not None else z
        return 100 * z
    return sum(g["O"] for g in games) / len(games)


def suite_value(by_task, tasks, weights, anchors):
    fam = {}
    for t in tasks:
        gs = by_task.get(t["id"])
        if gs:
            fam.setdefault(t["family"], []).append(task_value(t, gs, anchors))
    present = {f: sum(v) / len(v) for f, v in fam.items()}
    w = {f: weights.get(f, 0.0) for f in present}
    tot = sum(w.values())
    return (sum(w[f] * present[f] for f in present) / tot if tot else None), present


def bootstrap(by_task, tasks, weights, anchors, B=10000, seed=0, alpha=0.05):
    rng = random.Random(seed)
    vals = []
    for _ in range(B):
        bt = {tid: [gs[rng.randrange(len(gs))] for _ in gs] for tid, gs in by_task.items()}
        v, _ = suite_value(bt, tasks, weights, anchors)
        vals.append(v)
    vals.sort()
    return vals[int(alpha * B)], vals[min(B - 1, int((1 - alpha) * B))]


def _fmt_task(t, gs, anchors, adapter=None):
    return (adapter or df_adapter.DF).format_task(t, gs, task_value(t, gs, anchors))


# the suites whose forts are the season's private pool: only these give an officially comparable result
OFFICIAL_SUITES = {"season0"}


def anchors_id(suite):
    """A short id of the anchors a score used: the suite, where they were measured and the run (from anchors_note)."""
    note = suite.get("anchors_note") or ""
    where = ("native" if re.search(r"native", note, re.I) else "rosetta" if re.search(r"rosetta", note, re.I) else
             "unknown")
    prov = "provisional" if re.search(r"provisional", note, re.I) else "final"
    run = re.search(r"run (\d{8,})", note)
    return f"{suite.get('anchors_from') or suite.get('name')}/{where}/{prov}" + (f"/run{run.group(1)}" if run else "")


def result_labels(run_dir, suite, tasks, by_task, keys):
    """What a score is, so a fake, single-task, partial or local result is never mistaken for an official one (tester
    feedback, 2026-10-28). result_kind: official in the scoring workflow (DFBENCH_RESULT_KIND), else local. stack:
    run.json's (local runs), else DFBENCH_STACK, else fake if every game key is a fake key."""
    meta = {}
    try:
        meta = json.load(open(os.path.join(run_dir, "run.json")))
    except (OSError, ValueError):
        pass
    stack = meta.get("stack") or os.environ.get("DFBENCH_STACK") or (
        "fake" if keys and all("|fake" in k for k in keys) else "real")
    played = [t["id"] for t in tasks if t["id"] in by_task]
    scope = ("smoke" if suite.get("smoke") else "full" if len(played) == len(tasks) and len(tasks) > 1
             else "single-task" if len(played) == 1 else "partial")
    kind = os.environ.get("DFBENCH_RESULT_KIND") or "local"
    labels = {"result_kind": kind, "stack": stack, "scope": scope, "tasks_played": ",".join(played) or None,
              "anchors_id": anchors_id(suite),
              "official_comparable": kind == "official" and stack == "real" and scope == "full"
                                     and suite.get("name") in OFFICIAL_SUITES}
    if meta.get("watch"):   # local watch mode (runner/dfbenchlib/watch.py): rendered DF, other prefs, slower
        labels.update({"watch": True, "comparable": False, "official_comparable": False,
                       "watch_note": meta.get("watch_note") or "watch mode: not comparable"})
    return labels


def watch_key(key):
    """A watch-mode key: `+watch` after the dfset hash (or at the end of a key without one)."""
    if isinstance(key, list):
        return [watch_key(k) for k in key]
    if not isinstance(key, str) or "+watch" in key:
        return key
    out, n = re.subn(r"(\|dfset=[^|]*)", r"\1+watch", key, count=1)
    return out if n else key + "|watch"


def labels_banner(m):
    """One line for the top and bottom of a run's output."""
    ok = "OFFICIALLY COMPARABLE" if m.get("official_comparable") else "NOT an official result"
    if m.get("watch"):
        ok += " (WATCH MODE: rendered DF, not comparable with any headless run)"
    return (f"== {ok}: {m.get('result_kind')} | stack {m.get('stack')} | scope {m.get('scope')}"
            f" ({m.get('tasks_played') or '-'}) | suite {m.get('suite')} | anchors {m.get('anchors_id')} ==")


def score_dir(run_dir, suite, write=True):
    """-> (score.json dict, detail dict). Writes both into run_dir unless write=False."""
    tasks = [{"id": t["id"], "kind": t.get("kind", "outcome"), "family": t.get("family", t["id"]),
              "stage": t.get("stage", 1), "n": t.get("n", 8),
              "zlim": ((suite.get("lab_z") or {}).get("floor"), (suite.get("lab_z") or {}).get("cap", Z_CAP))}
             for t in suite["tasks"]]
    weights = SU.weights(suite)
    anchors = SU.anchors(suite)
    adapter = A.get(SU.environment(suite))
    bs = suite.get("bootstrap") or {}
    games = [score_game(os.path.dirname(p), adapter) for p in sorted(glob.glob(os.path.join(run_dir, "**", "game.json"),
                                                                       recursive=True))
             if os.path.isdir(os.path.join(os.path.dirname(p), "game"))
             and not any(x.startswith("attempt-") for x in os.path.relpath(p, run_dir).split(os.sep))]
    ok = [g for g in games if g["status"] == "ok"]
    by_task = {}
    for g in ok:
        by_task.setdefault(g["task"], []).append(g)
    tasks_present = [t for t in tasks if t["id"] in by_task]
    point, fam = suite_value(by_task, tasks, weights, anchors)
    lb = ub = None
    if point is not None:
        lb, ub = bootstrap(by_task, tasks, weights, anchors, int(bs.get("resamples", 10000)), int(bs.get("seed", 0)),
                           float(bs.get("alpha", 0.05)))
    stage2 = [t for t in tasks if t["stage"] >= 2]
    complete = all(t["id"] in by_task for t in tasks)
    stage1_done = all(t["id"] in by_task for t in tasks if t["stage"] == 1)
    # challenge/SCORING.md §4: metrics.stage 2 = complete, 1 = stage 1 only (score 0, partial, not promotable);
    # "subset" = any other incomplete run (local runs of a few tasks: the bound over the families present)
    stage = 2 if complete else (1 if stage1_done and stage2 else "subset")
    years = sum(g["days"] for g in ok) / DAYS_PER_YEAR or None
    led = [g["ledger"] for g in ok]
    cost = sum(x["cost_usd"] for x in led)
    calls = sum(x["ok_calls"] for x in led)
    wall = sum(float(g.get("wall_s") or 0) for g in ok)
    long_h = [g for g in ok if g["kind"] != "lab"]
    sub = {k: round(sum(g["s"][k] for g in long_h) / len(long_h), 3) for k in ("survival", "supply", "wellbeing", "growth")} \
        if long_h else {}
    tiers = [sum(g["tier"] == i for g in long_h) for i in range(5)]
    digests = sorted({g.get("harness_digest") for g in ok if g.get("harness_digest")})
    keys = sorted({g.get("key") for g in ok if g.get("key")})
    pth = sorted({g.get("price_table_hash") for g in ok if g.get("price_table_hash")})
    r = lambda v, d=2: None if v is None else round(v, d)
    metrics = {"stage": stage, "promotable": stage == 2, "point": r(point), "lb95": r(lb), "ub95": r(ub),
               **{t["id"]: _fmt_task(t, by_task[t["id"]], anchors, adapter) for t in tasks_present},
               **{f"family_{f}": r(v) for f, v in fam.items()},
               "credits_per_game_year": r(cost / years, 4) if years else None,
               "calls_per_game_year": r(calls / years, 1) if years else None,
               # model-side behaviour, to spot provider drift between runs (runs/s0-op1-native-2026-10-28)
               "model_latency_s_per_call": r(sum(x.get("latency_s") or 0 for x in led) / calls, 2) if calls else None,
               "reasoning_tokens_per_call": r(sum(x.get("reasoning_tokens") or 0 for x in led) / calls, 1) if calls else None,
               "completion_tokens_per_call": r(sum(x.get("completion_tokens") or 0 for x in led) / calls, 1) if calls else None,
               "wall_h_per_game_year": r(wall / 3600 / years, 3) if years else None,
               "wall_capped": sum(g.get("wall_capped", False) for g in ok),
               "actions_per_game_year": r(sum(g.get("actions_used") or 0 for g in ok) / years, 1) if years else None,
               "actions_rejected_per_game_year": r(sum(g.get("actions_rejected") or 0 for g in ok) / years, 1) if years else None,
               "throttle_wait_s": r(sum(g["throttle_wait_s"] for g in ok), 1),
               "credits_exhausted": sum(g.get("blocked_reason") == "budget_exhausted" for g in ok),
               "subscores": " ".join(f"{k} {v:.2f}" for k, v in sub.items()) or None,
               "tiers": ",".join(map(str, tiers)) if long_h else None,
               "games": f"{len(ok)} scored / {len(games)} run",
               "infra_excluded": len(games) - len(ok),
               "crash_twice": sum(bool(g.get("crash_twice")) for g in ok),
               "game_years": r(years, 2),
               "credits_usd": r(cost, 4),
               "harness_digest": digests[0] if len(digests) == 1 else (digests or None),
               "key": suite_key(keys),
               "price_table_hash": pth[0] if len(pth) == 1 else (",".join(pth) or None),
               "suite": suite.get("name"), "score_version": SCORE_VERSION, "runner": RUNNER_VERSION,
               "anchors": suite.get("anchors_note"),
               **result_labels(run_dir, suite, tasks, by_task, keys),
               "bootstrap": f"stratified by task, {int(bs.get('resamples', 10000))} resamples, seed {int(bs.get('seed', 0))}"}
    # per-game z below -1 (a lost or harmed fort on a task with a narrow anchor gap, e.g. LT08): listed while the
    # floor is undecided (the suite score stays unfloored)
    low = []
    for g in ok:
        a = anchors.get(g["task"])
        if g["kind"] == "lab" and a and a["witness"] > a["noop"]:
            z = (g["partial"] - a["noop"]) / (a["witness"] - a["noop"])
            if z < -1:
                low.append(f"{g['game_id']} {z:.2f}")
    metrics["lab_z_below_minus1"] = ", ".join(low) or None
    if metrics.get("watch") and metrics.get("key"):
        # the per-game keys can't tell (the server computes dfset from docker/prefs_overrides.py, which the watch
        # image doesn't change): mark the suite key so it never matches a headless one
        metrics["key"] = watch_key(metrics["key"])
    score = {"score": r(lb), "metrics": metrics}
    if stage != 2:
        score["partial"] = True
    if stage == 1:
        score["score"] = 0          # not promotable: Yukon records it as non-improving (SCORING.md §4)
    detail = {"score": score, "families": fam, "weights": weights, "anchors": anchors, "games": games}
    if write:
        json.dump(score, open(os.path.join(run_dir, "score.json"), "w"), indent=1)
        json.dump(detail, open(os.path.join(run_dir, "score_detail.json"), "w"), indent=1)
    return score, detail
