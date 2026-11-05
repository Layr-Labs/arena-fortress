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
  band.py select   [--k 4] [--cap 8] [--leader ID]  prints the re-score picks (JSON list: the leader first, then
                   every single-run contender whose ub95 reaches the leader's lb95, at most --cap; then, up to --k
                   picks in all, the contenders whose pooled interval reaches highest above the leader's lower bound)
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
    return tasks, S.SU.weights(suite), S.SU.anchors(suite)     # weights and anchors: one source (harnessarena.suite)


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
            e.pop("elect_over", None)
            continue
        if e.get("status") == "leader-elect" and e.get("elect_over") == lid:
            continue              # still awaiting Yukon's promotion over this same leader: keep the tag
        b, gap = band_of(e.get("pooled") or {}, lp, band_pts, e.get("valid", True))
        e["band_gap"] = gap
        if e.get("status") in ("leader", "leader-elect") or b == "contender":
            e["status"] = b if b == "contender" else "dropped"
        elif e.get("status") == "contender":
            e["status"] = "dropped"
        p = (e.get("pooled") or {}).get("point")
        # leading on pooled games: a contender's pooled point above the leader's, both re-scored at least once
        e["leading_on_pooled"] = bool(e.get("status") == "contender" and p is not None and lp is not None and p > lp
                                      and (e.get("pooled") or {}).get("runs", 0) >= 2 and lead.get("runs", 0) >= 2)
    return store


def leader_elect(score, valid, leader_score, bips):
    """True when this run's emitted score is the one Yukon will promote: a valid full-suite result (stage 2, judge
    not fail or hold), confirmation not failed, and Yukon's own rule (gate.would_promote) against the incumbent.
    band.py tag runs before Yukon reads the score, so without this the new leader is tagged against the old one."""
    if not valid or not isinstance(score.get("score"), (int, float)):
        return False
    m = score.get("metrics") or {}
    if not str(m.get("judge_verdict") or "").startswith("pass"):
        return False
    if str(m.get("confirmation") or "").startswith("failed"):
        return False
    if leader_score in (None, ""):
        return False              # unknown incumbent: don't guess (the next run's re-banding settles it)
    import gate
    return gate.would_promote(score["score"], leader_score, int(bips or 0))[0]


def tag_decision(store, a, score, games, suite, t=None):
    """Pure: -> metrics to add to score.json; mutates the store (with _nowrite when there's nothing to keep)."""
    t = t or now()
    m = score.get("metrics") or {}
    verdict = str(m.get("judge_verdict") or "")
    valid = m.get("stage") == 2 and not verdict.startswith(("fail", "hold"))
    old_leader = store.get("leader")
    if a.leader is not None:
        store["leader"] = a.leader or None
    leader_changed = store.get("leader") != old_leader
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
    if sid != lid and leader_elect(score, valid, getattr(a, "leader_score", None), getattr(a, "bips", 0)):
        band = "leader-elect"     # Yukon promotes after this run; the next run's re-banding makes it the leader
    keep = sid == BASELINE or sid == lid or band in ("contender", "leader-elect") or prev is not None
    out = {"band": band, "band_gap": gap, "band_leader_point": lp, "pooled_runs": stats["runs"],
           "pooled_point": stats["point"], "pooled_lb95": stats["lb95"]}
    if not keep:
        if leader_changed:        # Yukon promoted someone since the last run: re-band and save, without this entry
            rebanding(store, a.band_pts)
            return out
        return {**out, "_nowrite": True}
    e = store["entries"].setdefault(sid, {"submission": sid, "kind": a.kind, "first_seen": t, "runs": []})
    e.update(solver=a.solver or e.get("solver"), tree=a.tree or e.get("tree"), branch=a.branch or e.get("branch"),
             valid=valid, runs=runs, pooled=stats, status=band if band != "none" else "dropped", updated=t)
    if band == "leader-elect":
        e["elect_over"] = lid
    rebanding(store, a.band_pts)
    return out


def record_decision(store, a, games, suite, t=None):
    t = t or now()
    if a.leader is not None:
        store["leader"] = a.leader or None
    e = store["entries"].get(a.submission)
    if e is None:
        return {"ok": False, "reason": f"{a.submission} is not in the store", "_nowrite": True}
    run = {"run": a.run, "at": t, "source": a.source, "games": games}
    drift = getattr(a, "drift", None)
    if drift:                              # rescore.yml: the same-harness drift check and routing fingerprint
        run["drift"] = {k: v for k, v in drift.items() if not isinstance(v, (dict, list))}
        e["drift_last"] = run["drift"]
    e["runs"].append(run)
    e["pooled"] = pooled(e["runs"], suite)
    e["updated"] = t
    rebanding(store, a.band_pts)
    return {"ok": True, "status": e["status"], "pooled": e["pooled"], "leading_on_pooled": e["leading_on_pooled"]}


def select(store, k=4, cap=8):
    """The leader first, then the re-score picks:
    1. every contender with a single run whose pooled ub95 reaches the leader's pooled lb95 (it could be ahead, and
       one run can't tell: leading_on_pooled needs >= 2 runs each), highest ub95 first, at most `cap`;
    2. if that's fewer than `k`, the other contenders whose ub95 reaches highest above the leader's lb95, fewest runs
       first on ties, up to `k` picks in all.
    A fixed K alone missed one: on 2026-11-04 five single-run contenders reached the leader and the fifth (ub95 0.01
    lower) wasn't re-scored."""
    lid = store.get("leader") or BASELINE
    lead = (store["entries"].get(lid) or {}).get("pooled") or {}
    llb = lead.get("lb95") or 0.0
    cs = [e for sid, e in store["entries"].items() if sid != lid and e.get("status") == "contender"
          and (e.get("pooled") or {}).get("ub95") is not None]
    cs.sort(key=lambda e: (-(e["pooled"]["ub95"] - llb), e["pooled"].get("runs", 0)))
    first = [e for e in cs if e["pooled"].get("runs", 0) < 2 and e["pooled"]["ub95"] >= llb][:max(cap, 0)]
    took = {e["submission"] for e in first}
    rest = [e for e in cs if e["submission"] not in took][:max(k - len(first), 0)]
    picks = ([lid] if lid in store["entries"] else []) + [e["submission"] for e in first + rest]
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
        if e.get("status") not in ("leader", "leader-elect", "contender"):
            continue
        p = e.get("pooled") or {}
        mark = ("leader" if e["submission"] == lid else "leader-elect (awaiting Yukon's promotion)"
                if e.get("status") == "leader-elect" else
                "leading on pooled games" if e.get("leading_on_pooled") else "contender")
        name = "the import baseline" if e["submission"] == BASELINE else f"`{e['submission'][:8]}` {link(e)}"
        lines.append(f"| {mark} | {name} | {e.get('solver') or ''} | {p.get('point')} | {p.get('lb95')} | {p.get('ub95')} "
                     f"| {p.get('runs')} | {p.get('games')} | {'' if e.get('band_gap') is None else e['band_gap']} |")
    lines += ["", "Each submission's note and declared dependencies (its attribution) are on its PR and its Yukon "
              "submission page.", "",
              "## How to use this list", "",
              "Contenders are as good as the leader within the noise of one run, so they are worth reading even when "
              "Yukon didn't promote them. Pooled scores (more games) are better estimates than any single run. For a "
              "submission id above:", "",
              "```sh",
              "yukon submission-note <id>          # its research note",
              "yukon attribution declared <id>     # what it builds on",
              "yukon reset <id>                    # restore submission/ from its commit (promoted or not)",
              "```", "",
              "Build on any of them freely, credit what you use (`dependencies.json` and `NOTE.md`), and add an "
              "improvement of your own: `SUBMITTING.md` §3a, `RULES.md` §8."]
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
    for f in ("--solver", "--tree", "--branch", "--run", "--leader", "--leader-point", "--leader-score"):
        x.add_argument(f)
    x.add_argument("--bips", type=int, default=0, help="Yukon's minScoreImprovementBips (gate.py bips)")
    x.add_argument("--source", default="score"); x.add_argument("--band-pts", type=float, default=band_pts)
    x = sp.add_parser("record")
    for f in ("--detail", "--suite", "--submission"):
        x.add_argument(f, required=True)
    x.add_argument("--run"); x.add_argument("--leader"); x.add_argument("--source", default="rescore")
    x.add_argument("--drift", type=json.loads, default=None, help="flat drift/route metrics (JSON) for this run")
    x.add_argument("--band-pts", type=float, default=band_pts)
    x = sp.add_parser("select"); x.add_argument("--k", type=int, default=4); x.add_argument("--leader")
    x.add_argument("--cap", type=int, default=8)
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
        print(json.dumps(select(st, a.k, a.cap)))
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
