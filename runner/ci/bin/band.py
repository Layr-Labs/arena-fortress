#!/usr/bin/env python3
"""runner/ci/bin/band.py: the contender band (challenge/SCORING.md §4.2; docs/SCORING-INFRA.md §5.10).

Every complete, valid submission whose lower bound is within BAND_PTS of the leader's pooled point estimate is a
`contender`. The organiser-only store keeps each contender's runs (per-task game values, never published) in
`seasons/<season>/contenders.json` of the ops repo (DFBENCH_OPS_REPO; written like the ledger, runner/ci/bin/ledger.py),
pools them across runs (scoring, confirmation and weekly re-score runs: the scorer's own suite value and stratified
bootstrap over all of a submission's games), and publishes aggregates only (CONTENDERS.md). Yukon's promotion is
untouched: the band and the pooled numbers are reported, never used to promote.

  band.py tag      --score SCORE_JSON --detail DETAIL_JSON --suite SUITE --submission ID --kind submission|baseline
                   [--solver U] [--tree T] [--branch B] [--run R] [--source score|confirm] [--leader ID]
                   [--leader-point X] [--band-pts 3.8]
                   adds this run to the store when the submission is (or becomes) a contender, the leader or the
                   baseline; writes flat metrics band, band_gap, band_leader_point, pooled_runs into SCORE_JSON
  band.py record   --detail DETAIL_JSON --suite SUITE --submission ID [--run R] [--source rescore] [--leader ID]
                   [--band-pts 3.8]    a weekly re-score run of a stored entry: append, re-pool, re-band
  band.py select   [--k 4] [--leader ID]  prints the re-score picks (JSON list: the leader first, then the K
                   contenders whose pooled interval reaches highest above the leader's lower bound)
  band.py publish  --out CONTENDERS.md [--repo OWNER/NAME]     the aggregates-only list
  band.py show

The verdict gate: a submission whose judge verdict is fail or hold, or a stage-1-only result, is never a contender.
Env: as ledger.py (DFBENCH_OPS_TOKEN or GITHUB_TOKEN, DFBENCH_OPS_REPO, DFBENCH_SEASON); DFBENCH_BAND_PTS.
"""
import argparse, datetime, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE))))     # runner/ (dfbenchlib)
from dfbenchlib import score as S  # noqa: E402

STORE = "contenders.json"
BASELINE = "baseline"
DEFAULT_BAND = 3.8          # ~1 SD of the difference between two runs of one harness (runs/s0-noise-2026-10-27)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def empty():
    return {"entries": {}, "leader": None}


# ---- scoring over pooled runs (the scorer's own functions; nothing re-implemented) ----

def suite_parts(suite):
    tasks = [{"id": t["id"], "kind": t.get("kind", "outcome"), "family": t.get("family", t["id"]),
              "stage": t.get("stage", 1),
              "zlim": ((suite.get("lab_z") or {}).get("floor"), (suite.get("lab_z") or {}).get("cap", S.Z_CAP))}
             for t in suite["tasks"]]
    weights = suite.get("weights") or {"OP1": 0.5, "MY1": 0.3, "labs": 0.2}
    anchors = {t["id"]: t["anchor"] for t in suite["tasks"] if t.get("anchor")}
    return tasks, weights, anchors


def run_games(detail):
    """score_detail.json -> {task: [{kind, O, partial}]} of the scored (ok) games: what pooling needs, nothing else."""
    out = {}
    for g in detail.get("games") or []:
        if g.get("status") != "ok":
            continue
        out.setdefault(g["task"], []).append({"kind": g.get("kind"), "O": g.get("O"), "partial": g.get("partial")})
    return out


def pooled(runs, suite):
    """-> {point, lb95, ub95, runs, games} over every game of every run (stratified bootstrap by task, seeded)."""
    tasks, weights, anchors = suite_parts(suite)
    by_task = {}
    for r in runs:
        for tid, gs in (r.get("games") or {}).items():
            by_task.setdefault(tid, []).extend(gs)
    point, _ = S.suite_value(by_task, tasks, weights, anchors)
    if point is None:
        return {"point": None, "lb95": None, "ub95": None, "runs": len(runs), "games": 0}
    bs = suite.get("bootstrap") or {}
    lb, ub = S.bootstrap(by_task, tasks, weights, anchors, int(bs.get("resamples", 10000)), int(bs.get("seed", 0)),
                         float(bs.get("alpha", 0.05)))
    r2 = lambda v: None if v is None else round(v, 2)
    return {"point": r2(point), "lb95": r2(lb), "ub95": r2(ub), "runs": len(runs),
            "games": sum(len(v) for v in by_task.values())}


# ---- the band ----

def band_of(stats, leader_point, band_pts, valid=True):
    """-> (band, gap). gap = lb95 - the leader's pooled point (None if either is unknown)."""
    if not valid or stats.get("lb95") is None:
        return "none", None
    if leader_point is None:
        return "contender", None
    gap = round(stats["lb95"] - leader_point, 2)
    return ("contender" if gap >= -band_pts else "none"), gap


def leader_point(store, leader_id):
    e = store["entries"].get(leader_id or BASELINE)
    return (e or {}).get("pooled", {}).get("point")


def rebanding(store, band_pts):
    """Recompute every entry's band and the leading-on-pooled flag against the current leader's pooled point."""
    lid = store.get("leader") or BASELINE
    lp = leader_point(store, lid)
    lead = store["entries"].get(lid, {}).get("pooled") or {}
    for sid, e in store["entries"].items():
        if sid == lid:
            e["status"], e["band_gap"], e["leading_on_pooled"] = "leader", 0.0, False
            continue
        b, gap = band_of(e.get("pooled") or {}, lp, band_pts, e.get("valid", True))
        e["band_gap"] = gap
        if e.get("status") == "leader" or b == "contender":
            e["status"] = b if b == "contender" else "dropped"
        elif e.get("status") == "contender":
            e["status"] = "dropped"
        p = (e.get("pooled") or {}).get("point")
        # leading on pooled games: a contender's pooled point above the leader's, both re-scored at least once
        e["leading_on_pooled"] = bool(e.get("status") == "contender" and p is not None and lp is not None and p > lp
                                      and (e.get("pooled") or {}).get("runs", 0) >= 2 and lead.get("runs", 0) >= 2)
    return store


def tag_decision(store, a, score, games, suite, t=None):
    """Pure: -> metrics to add to score.json; mutates the store (with _nowrite when there's nothing to keep)."""
    t = t or now()
    m = score.get("metrics") or {}
    verdict = str(m.get("judge_verdict") or "")
    valid = m.get("stage") == 2 and not verdict.startswith(("fail", "hold"))
    if a.leader is not None:
        store["leader"] = a.leader or None
    sid = BASELINE if a.kind == "baseline" else a.submission
    lid = store.get("leader") or BASELINE
    prev = store["entries"].get(sid)
    run = {"run": a.run, "at": t, "source": a.source, "games": games}
    runs = ((prev or {}).get("runs") or []) + [run]
    stats = pooled(runs, suite)
    lp = leader_point(store, lid) if sid != lid else stats["point"]
    if lp is None and a.leader_point not in (None, ""):
        lp = float(a.leader_point)                        # the leader isn't in the store: Yukon's own numbers
    band, gap = ("leader", 0.0) if sid == lid else band_of(stats, lp, a.band_pts, valid)
    keep = sid == BASELINE or sid == lid or band == "contender" or prev is not None
    out = {"band": band, "band_gap": gap, "band_leader_point": lp, "pooled_runs": stats["runs"],
           "pooled_point": stats["point"], "pooled_lb95": stats["lb95"]}
    if not keep:
        return {**out, "_nowrite": True}
    e = store["entries"].setdefault(sid, {"submission": sid, "kind": a.kind, "first_seen": t, "runs": []})
    e.update(solver=a.solver or e.get("solver"), tree=a.tree or e.get("tree"), branch=a.branch or e.get("branch"),
             valid=valid, runs=runs, pooled=stats, status=band if band != "none" else "dropped", updated=t)
    rebanding(store, a.band_pts)
    return out


def record_decision(store, a, games, suite, t=None):
    t = t or now()
    if a.leader is not None:
        store["leader"] = a.leader or None
    e = store["entries"].get(a.submission)
    if e is None:
        return {"ok": False, "reason": f"{a.submission} is not in the store", "_nowrite": True}
    e["runs"].append({"run": a.run, "at": t, "source": a.source, "games": games})
    e["pooled"] = pooled(e["runs"], suite)
    e["updated"] = t
    rebanding(store, a.band_pts)
    return {"ok": True, "status": e["status"], "pooled": e["pooled"], "leading_on_pooled": e["leading_on_pooled"]}


def select(store, k=4):
    """The leader first, then the K contenders whose pooled ub95 reaches highest above the leader's pooled lb95 (the
    ones most likely to be ahead), ties broken by fewer runs."""
    lid = store.get("leader") or BASELINE
    lead = (store["entries"].get(lid) or {}).get("pooled") or {}
    llb = lead.get("lb95") or 0.0
    cs = [e for sid, e in store["entries"].items() if sid != lid and e.get("status") == "contender"
          and (e.get("pooled") or {}).get("ub95") is not None]
    cs.sort(key=lambda e: (-(e["pooled"]["ub95"] - llb), e["pooled"].get("runs", 0)))
    picks = ([lid] if lid in store["entries"] else []) + [e["submission"] for e in cs[:k]]
    return picks


def publish(store, repo=None, season=None):
    """-> CONTENDERS.md text: aggregates only (pooled S, runs, games), links to each submission's PR."""
    lid = store.get("leader") or BASELINE
    rows = sorted(store["entries"].values(), key=lambda e: -((e.get("pooled") or {}).get("point") or -1e9))
    link = (lambda e: f"[PR](https://github.com/{repo}/pulls?q=is%3Apr+head%3A{e.get('branch') or 'submissions/' + e['submission']})"
            if repo and e["submission"] != BASELINE else "")
    lines = [f"# Contender band, season {season or os.environ.get('DFBENCH_SEASON', 's0')}", "",
             "Every submission whose lower bound is within the band of the leader's pooled point estimate. Pooled = "
             "all of a submission's scored games (its scoring run, any confirmation batch and the weekly re-scores), "
             "scored like a single run. Aggregates only. **Yukon's board decides promotion; this list doesn't.** "
             "See `SCORING.md` §4.2.", "",
             f"Updated {now()}.", "",
             "| | submission | solver | pooled S (point) | lower bound | upper bound | runs | games | gap to leader |",
             "|---|---|---|---|---|---|---|---|---|"]
    for e in rows:
        if e.get("status") not in ("leader", "contender"):
            continue
        p = e.get("pooled") or {}
        mark = "leader" if e["submission"] == lid else ("leading on pooled games" if e.get("leading_on_pooled") else "contender")
        name = "the import baseline" if e["submission"] == BASELINE else f"`{e['submission'][:8]}` {link(e)}"
        lines.append(f"| {mark} | {name} | {e.get('solver') or ''} | {p.get('point')} | {p.get('lb95')} | {p.get('ub95')} "
                     f"| {p.get('runs')} | {p.get('games')} | {'' if e.get('band_gap') is None else e['band_gap']} |")
    lines += ["", "Each submission's note and declared dependencies (its attribution) are on its PR and its Yukon "
              "submission page."]
    return "\n".join(lines) + "\n"


def main():
    import ledger as L                          # the ops store (contents API, optimistic concurrency)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    band_pts = float(os.environ.get("DFBENCH_BAND_PTS") or DEFAULT_BAND)
    x = sp.add_parser("tag")
    for f in ("--score", "--detail", "--suite", "--submission"):
        x.add_argument(f, required=True)
    x.add_argument("--kind", choices=["submission", "baseline"], default="submission")
    for f in ("--solver", "--tree", "--branch", "--run", "--leader", "--leader-point"):
        x.add_argument(f)
    x.add_argument("--source", default="score"); x.add_argument("--band-pts", type=float, default=band_pts)
    x = sp.add_parser("record")
    for f in ("--detail", "--suite", "--submission"):
        x.add_argument(f, required=True)
    x.add_argument("--run"); x.add_argument("--leader"); x.add_argument("--source", default="rescore")
    x.add_argument("--band-pts", type=float, default=band_pts)
    x = sp.add_parser("select"); x.add_argument("--k", type=int, default=4); x.add_argument("--leader")
    x = sp.add_parser("publish"); x.add_argument("--out", required=True); x.add_argument("--repo")
    sp.add_parser("show")
    a = ap.parse_args()
    if a.cmd == "tag":
        score = json.load(open(a.score))
        games, suite = run_games(json.load(open(a.detail))), json.load(open(a.suite))
        r = L.update(STORE, lambda st: tag_decision(st, a, score, games, suite), f"band: {a.kind} {a.submission}", empty)
        r.pop("_nowrite", None)
        score.setdefault("metrics", {}).update({k: v for k, v in r.items()})
        json.dump(score, open(a.score, "w"), indent=1)
        print(f"band {r['band']} (gap {r['band_gap']}, leader point {r['band_leader_point']}, pooled runs {r['pooled_runs']})")
    elif a.cmd == "record":
        games, suite = run_games(json.load(open(a.detail))), json.load(open(a.suite))
        r = L.update(STORE, lambda st: record_decision(st, a, games, suite), f"band: re-score {a.submission}", empty)
        r.pop("_nowrite", None)
        print(json.dumps(r))
    elif a.cmd == "select":
        st, _ = L.load(STORE)
        st = st or empty()
        if a.leader is not None:
            st["leader"] = a.leader or None
        print(json.dumps(select(st, a.k)))
    elif a.cmd == "publish":
        st, _ = L.load(STORE)
        open(a.out, "w").write(publish(st or empty(), a.repo, L.SEASON))
        print(f"wrote {a.out}")
    else:
        st, _ = L.load(STORE)
        for sid, e in ((st or empty())["entries"]).items():
            print(sid, e.get("status"), json.dumps(e.get("pooled")), "leading" if e.get("leading_on_pooled") else "")


if __name__ == "__main__":
    main()
