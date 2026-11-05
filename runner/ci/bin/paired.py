#!/usr/bin/env python3
"""runner/ci/bin/paired.py: the leader-alongside-challenger confirmation (challenge/SCORING.md §4.1, D26).

When a submission would be promoted, score.yml plays its confirmation batch (MY1 and OP1 by default) and, in the same
window, the leader's harness (main's submission/ tree) on the very same games: same tasks, k, forts and seeds. This
script pairs the two game by game and bootstraps the difference challenger − leader of the suite value over those
games, with the scorer's own functions (runner/dfbenchlib/score.py, nothing re-implemented). Provider-side drift that
hits both harnesses in the same window cancels in the difference; a promotion needs its lower bound above 0.

  paired.py decide --challenger score_detail.json --leader score_detail.json --suite S --scored scored.json \
      [--tasks MY1,OP1] [--alpha A] [--off] [--leader-verified true|false|unknown]

Rewrites --scored in place: adds paired_* metrics; if the paired lower bound is not above 0 (and the check is on and
the leader harness was verified), the emitted score becomes 0/partial (non-improving for Yukon) with
confirmation=failed_paired, keeping the pooled value as score_pooled. Prints `paired=passed|failed|skipped` and
`score=` for $GITHUB_OUTPUT.
"""
import argparse, json, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))          # runner/ (dfbenchlib)
from dfbenchlib import score as S  # noqa: E402
from band import suite_parts  # noqa: E402
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "framework"))
from harnessarena import suite as SU  # noqa: E402


def pairs(chal, lead, tasks):
    """-> {task: [(challenger game, leader game)]}: ok games present in both, matched on (task, k)."""
    want = set(tasks)
    key = lambda g: (g["task"], g["k"])
    lmap = {key(g): g for g in lead.get("games") or [] if g.get("status") == "ok" and g["task"] in want}
    out = {}
    for g in chal.get("games") or []:
        if g.get("status") == "ok" and g["task"] in want and key(g) in lmap:
            out.setdefault(g["task"], []).append((g, lmap[key(g)]))
    for v in out.values():
        v.sort(key=lambda p: p[0]["k"])
    return out


def _value(by_task, tasks, weights, anchors):
    v, _ = S.suite_value(by_task, tasks, weights, anchors)
    return v


def paired_diff(prs, suite, B=None, seed=None, alpha=None):
    """-> {point, lb, challenger_point, leader_point, n} (lb: the one-sided `alpha` lower bound of the difference)."""
    tasks, weights, anchors = suite_parts(suite)
    bs = suite.get("bootstrap") or {}
    B = int(B or bs.get("resamples", 10000))
    seed = int(bs.get("seed", 0) if seed is None else seed)
    alpha = float(bs.get("alpha", 0.05) if alpha is None else alpha)
    n = sum(len(v) for v in prs.values())
    if not n:
        return {"point": None, "lb": None, "challenger_point": None, "leader_point": None, "n": 0}
    c = {t: [p[0] for p in v] for t, v in prs.items()}
    l = {t: [p[1] for p in v] for t, v in prs.items()}
    cp, lp = _value(c, tasks, weights, anchors), _value(l, tasks, weights, anchors)
    rng = random.Random(seed)
    vals = []
    for _ in range(B):
        idx = {t: [rng.randrange(len(v)) for _ in v] for t, v in prs.items()}
        bc = {t: [prs[t][i][0] for i in ix] for t, ix in idx.items()}
        bl = {t: [prs[t][i][1] for i in ix] for t, ix in idx.items()}
        vals.append(_value(bc, tasks, weights, anchors) - _value(bl, tasks, weights, anchors))
    vals.sort()
    r = lambda v: None if v is None else round(v, 2)
    return {"point": r(cp - lp), "lb": r(vals[int(alpha * B)]), "challenger_point": r(cp), "leader_point": r(lp),
            "n": n}


def decide(scored, d, on=True, verified="unknown"):
    """Apply the paired verdict to a scored.json dict in place. -> 'passed' | 'failed' | 'skipped'."""
    m = scored["metrics"]
    m.update(paired_diff_point=d["point"], paired_diff_lb=d["lb"], leader_window_point=d["leader_point"],
             challenger_window_point=d["challenger_point"], paired_games=d["n"], leader_verified=verified)
    if not on:
        m["paired_note"] = "off (vars.DFBENCH_CONFIRM_PAIRED)"
        return "skipped"
    if verified == "false":
        # main's submission/ isn't Yukon's incumbent: the comparison isn't against the leader; report only
        m["paired_note"] = "main's submission/ is not the incumbent's tree: reported, not applied"
        return "skipped"
    if d["lb"] is None:
        m["paired_note"] = "no paired games (the leader batch didn't play): reported, not applied"
        return "skipped"
    if d["lb"] > 0:
        m["paired_note"] = "the challenger beats the leader in the same window"
        return "passed"
    m.update(confirmation="failed_paired", score_pooled=scored.get("score"),
             paired_note="not clearly better than the leader played in the same window: not promoted")
    scored["score"] = 0
    scored["partial"] = True
    return "failed"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("decide")
    p.add_argument("--challenger", required=True); p.add_argument("--leader", required=True)
    p.add_argument("--suite", required=True); p.add_argument("--scored", required=True)
    p.add_argument("--tasks", default="")
    p.add_argument("--alpha", type=float, default=None)
    p.add_argument("--off", action="store_true")
    p.add_argument("--leader-verified", default="unknown", choices=["true", "false", "unknown"])
    a = ap.parse_args()
    suite = json.load(open(a.suite))
    tasks = [t for t in a.tasks.split(",") if t] or list(SU.confirm_tasks(suite))
    chal = json.load(open(a.challenger))
    try:
        lead = json.load(open(a.leader))
    except (OSError, ValueError):
        lead = {"games": []}
    scored = json.load(open(a.scored))
    d = paired_diff(pairs(chal, lead, tasks), suite, alpha=a.alpha)
    v = decide(scored, d, on=not a.off, verified=a.leader_verified)
    json.dump(scored, open(a.scored, "w"), indent=1)
    print(f"paired={v}")
    print(f"score={scored['score']}")
    sys.stderr.write(f"paired: {v}; diff {d['point']} (lb {d['lb']}) over {d['n']} games; leader {d['leader_point']}\n")


if __name__ == "__main__":
    main()
