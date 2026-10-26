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
import glob, json, os, random, sys

from . import ROOT, RUNNER_VERSION
from .game import DAYS_PER_YEAR, last_summary_row, ledger_summary

sys.path.insert(0, ROOT)
from bench import outcomes, predicates   # noqa: E402  the trusted scorers, unchanged

SCORE_VERSION = "s0-score/1"
PRED = {"LT01": predicates.lt01, "LT02": predicates.lt02, "LT03": predicates.lt03, "LT04": predicates.lt04,
        "LT05": predicates.lt05, "LT08": predicates.lt08, "LT09": predicates.lt09,
        "LT08-items": lambda r, d: predicates.lt08(r, d, items=True)}
Z_CAP = 1.5


def _read_row(gdir):
    p = os.path.join(gdir, "summary.jsonl")
    rows = []
    if os.path.exists(p):
        with open(p) as f:
            rows = [json.loads(l) for l in f if l.strip()]
    rows = [r for r in rows if not r.get("crashed")]
    return rows[-1] if rows else None


def score_game(game_dir):
    """-> per-game record from trusted artifacts, or one with status != 'ok' (excluded from the score)."""
    with open(os.path.join(game_dir, "game.json")) as f:
        rec = json.load(f)
    spec = rec["spec"]
    out = {"game_id": spec["game_id"], "task": spec["task_id"], "kind": spec.get("kind"), "family": spec.get("family"),
           "stage": spec.get("stage", 1), "k": spec["k"], "status": rec.get("status"), "notes": list(rec.get("notes") or [])}
    g = os.path.join(game_dir, "game")
    row = _read_row(g)
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
        return _score_crashed(out, g, spec, rec)
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
    o = outcomes.for_run(g, row)
    days = float(row.get("days_played") or 0)
    tw = gst.get("throttle_wait_total_s")
    tw = led["throttle_wait_s"] if tw is None else float(tw)
    out.update(throttle_wait_s=round(min(tw, float(row.get("wall_s") or rec.get("wall_s") or 0)), 2))
    out.update(days=days, wall_s=row.get("wall_s"), wall_capped=bool(row.get("wall_capped")),
               finished_by=row.get("finished_by"), actions_used=row.get("actions_used"),
               actions_rejected=row.get("actions_rejected"),
               harness_digest=row.get("harness_digest"), key=row.get("key"))
    if o is None:
        out["status"] = "infra"
        out["notes"].append("no daily samples")
        return out
    out.update(O=o["outcome"], tier=o["tier"], s=o["s"])
    if spec.get("kind") == "lab":
        fn = PRED.get(spec.get("predicate") or spec["task_id"])
        got = [(r, dd) for r, dd in predicates.runs([g])]
        if fn is None or not got:
            out["status"] = "infra"
            out["notes"].append("no predicate or no lab artifacts")
            return out
        try:
            c, part, info = fn(*got[-1])
            out.update(partial=round(part, 4), passed=all(x for x in c if x is not None), clauses=c)
        except (IndexError, KeyError, ZeroDivisionError) as e:
            # e.g. a wall-capped or lost fort that never reached day A: scored as no credit
            out.update(partial=0.0, passed=False, clauses=None)
            out["notes"].append(f"predicate error {type(e).__name__}: {e}; partial 0")
    return out


ZERO_S = {"survival": 0.0, "supply": 0.0, "wellbeing": 0.0, "growth": 0.0}


def _score_crashed(out, g, spec, rec):
    """DF crashed or hung on the game's re-run too (challenge/SCORING.md §6): scored at the state reached, from the
    server's last summary row (crashed or not) and its daily samples, like a wall-capped game; with no samples, as
    a lost fort (O 0, partial 0). Not infra, so it can't be used to re-roll a game."""
    out.update(status="ok", crash_twice=True, throttle_wait_s=0.0, wall_capped=False)
    out["notes"].append("DF crashed or hung on two attempts: scored at the state reached")
    row = last_summary_row(g)
    o = None
    if row is not None:
        try:
            o = outcomes.for_run(g, row)
        except (OSError, ValueError, KeyError, IndexError, ZeroDivisionError, TypeError) as e:
            out["notes"].append(f"outcome error {type(e).__name__}: {e}")
    if row is not None:
        out.update(days=float(row.get("days_played") or 0), wall_s=row.get("wall_s"),
                   finished_by="crashed", actions_used=row.get("actions_used"),
                   actions_rejected=row.get("actions_rejected"), harness_digest=row.get("harness_digest"),
                   key=row.get("key"))
    else:
        out.update(days=0.0, wall_s=rec.get("wall_s"), finished_by="crashed")
    if o is None:
        out["notes"].append("no daily samples: scored as a lost fort")
        out.update(O=0.0, tier=0, s=dict(ZERO_S))
    else:
        out.update(O=o["outcome"], tier=o["tier"], s=o["s"])
    if spec.get("kind") == "lab":
        fn = PRED.get(spec.get("predicate") or spec["task_id"])
        part, passed, c = 0.0, False, None
        stem = os.path.join(g, f"{row['arm']}-{row['k']}") if row else None
        if fn and o is not None and stem and os.path.exists(stem + ".daily.json"):
            try:
                dd = json.load(open(stem + ".daily.json"))
                if os.path.exists(stem + ".credit.json"):
                    dd["_credit"] = json.load(open(stem + ".credit.json"))
                c, part, _ = fn(row, dd)
                passed = all(x for x in c if x is not None)
            except (IndexError, KeyError, ZeroDivisionError, TypeError, ValueError) as e:
                out["notes"].append(f"predicate error {type(e).__name__}: {e}; partial 0")
                part, passed, c = 0.0, False, None
        out.update(partial=round(part, 4), passed=passed, clauses=c)
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


def _fmt_task(t, gs, anchors):
    n = len(gs)
    if t["kind"] == "lab":
        p = sum(g["partial"] for g in gs) / n
        return (f"pass {sum(bool(g['passed']) for g in gs)}/{n}, partial {p:.2f}, "
                f"z {task_value(t, gs, anchors) / 100:.2f}")
    tiers = [sum(g["tier"] == i for g in gs) for i in range(5)]
    return f"O {sum(g['O'] for g in gs) / n:.1f} (n {n}; tiers 0-4 {','.join(map(str, tiers))})"


def score_dir(run_dir, suite, write=True):
    """-> (score.json dict, detail dict). Writes both into run_dir unless write=False."""
    tasks = [{"id": t["id"], "kind": t.get("kind", "outcome"), "family": t.get("family", t["id"]),
              "stage": t.get("stage", 1), "n": t.get("n", 8),
              "zlim": ((suite.get("lab_z") or {}).get("floor"), (suite.get("lab_z") or {}).get("cap", Z_CAP))}
             for t in suite["tasks"]]
    weights = suite.get("weights") or {"OP1": 0.5, "MY1": 0.3, "labs": 0.2}
    anchors = {t["id"]: t["anchor"] for t in suite["tasks"] if t.get("anchor")}
    bs = suite.get("bootstrap") or {}
    games = [score_game(os.path.dirname(p)) for p in sorted(glob.glob(os.path.join(run_dir, "**", "game.json"),
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
               **{t["id"]: _fmt_task(t, by_task[t["id"]], anchors) for t in tasks_present},
               **{f"family_{f}": r(v) for f, v in fam.items()},
               "credits_per_game_year": r(cost / years, 4) if years else None,
               "calls_per_game_year": r(calls / years, 1) if years else None,
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
               "key": keys[0] if len(keys) == 1 else (keys or None),
               "price_table_hash": pth[0] if len(pth) == 1 else (",".join(pth) or None),
               "suite": suite.get("name"), "score_version": SCORE_VERSION, "runner": RUNNER_VERSION,
               "anchors": suite.get("anchors_note"),
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
