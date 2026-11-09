#!/usr/bin/env python3
"""runner/ci/bin/gate.py: the leader and the comparisons with it, isolated (docs/SCORING-INFRA.md §5.4). Scalar
mode compares with one leader; a Pareto season would replace these checks with a frontier check.

  gate.py leader --benchmark ID [--fallback-point X --fallback-score Y]   prints leader_point=, leader_score=
leader: Yukon's incumbent, authoritative (GET {DFBENCH_YUKON_API}/api/benchmarks/{id}: currentBestScore and
        currentBestMetrics.stage1_point, which our score.json carries). If Yukon can't be read, the fallback values
        (the leader file in the ops store) are used when given, else it exits 3 (infra).

  gate.py stage2 --stage1-score s1.json [--leader-point X] [--leader-score Y] [--suite S] [--force]
                                                                           prints run_stage2=true|false,
                                                                           stage1_point=, stage1_ub95=
  gate.py judge  --score scored.json [--leader-score Y] [--min-gain 0]    prints judge=true|false and reason=...
stage2: run OP1 unless even a perfect OP1 couldn't reach the leader's score: (1 - w2) x stage-1 ub95 + w2 x 100 <
        leader score (w2 = the stage-2 weight from --suite; always if there's no leader, or --force).
judge:  run the judge iff the run is complete (stage 2) and its score beats the leader's by more than --min-gain
        (always when there's no leader). Otherwise Yukon can't promote it, so the judge is not needed.

  gate.py leader-id --benchmark ID      prints leader_id= (Yukon's incumbent submission; empty: the import baseline)
  gate.py bips [--manifest benchmark.json]                                  prints minScoreImprovementBips
  gate.py confirm --score scored.json --plans s1.json,s2.json --suite SUITE [--leader-score Y] [--bips B]
                  [--tasks T1,T2 (default: the suite's confirm_tasks)] [--games-dir DIR] [--off]       prints confirm=true|false, reason=, matrix=
confirm: a complete (stage 2) score that Yukon would promote (yukon src/benchmark/score.ts: (score - incumbent) /
        |incumbent| x 10000 >= minScoreImprovementBips; no incumbent, or Yukon unreadable: yes) plays a second batch
        of the long tasks (--tasks): game ids TASK-(n..2n-1), the same forts and seeds as TASK-(0..n-1) (the server
        plays run k on pool[(seed + k) mod forts]). The matrix reuses the plans' jobs and timeouts. Not again when
        the games dir already holds a second batch (an organiser re-run merged from a confirmed run).
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "framework"))
from tier import Infra, http_json, yukon_headers  # noqa: E402
from harnessarena import suite as SU  # noqa: E402


def leader(benchmark_id, env=os.environ, http=http_json):
    """-> (stage1_point | None, score | None) from Yukon's incumbent. Raises Infra."""
    api = (env.get("DFBENCH_YUKON_API") or "").rstrip("/")
    if not api.startswith("https://"):
        raise Infra("DFBENCH_YUKON_API is not set to an https URL")
    h = yukon_headers(env)
    b = http(f"{api}/api/benchmarks/{benchmark_id}", h)["benchmark"]
    m = b.get("currentBestMetrics") or {}
    return m.get("stage1_point"), b.get("currentBestScore")


def leader_id(benchmark_id, env=os.environ, http=http_json):
    """-> Yukon's incumbent submission id (the most recently promoted), or None while main is the import baseline."""
    api = (env.get("DFBENCH_YUKON_API") or "").rstrip("/")
    if not api.startswith("https://"):
        raise Infra("DFBENCH_YUKON_API is not set to an https URL")
    rows = http(f"{api}/api/benchmarks/{benchmark_id}/submissions", yukon_headers(env)).get("submissions") or []
    prom = sorted((r for r in rows if r.get("promotionStatus") == "promoted"),
                  key=lambda r: r.get("promotionFinishedAt") or "", reverse=True)
    return prom[0]["id"] if prom else None


def manifest_bips(path=None):
    """minScoreImprovementBips of the benchmark's track (benchmark.json at the repo root on BENCH, challenge/ here)."""
    for p in ([path] if path else ["benchmark.json", os.path.join("challenge", "benchmark.json")]):
        if p and os.path.exists(p):
            m = json.load(open(p))
            t = (m.get("tracks") or [m])[0]
            return int(t.get("minScoreImprovementBips") or 0)
    return 0


OUTCOME_MAX = 100.0     # a game's outcome O is at most 100 (bench/outcomes.py), so OP1's family value is too


def stage2_weight(suite):
    """The suite-score weight of the stage-2 families (season 0: OP1 0.5)."""
    w = SU.weights(suite) if suite else {}
    fams = {t.get("family", t["id"]) for t in (suite or {}).get("tasks", []) if int(t.get("stage", 1)) >= 2}
    return sum(float(w.get(f, 0)) for f in fams) or 0.5


def stage2(s1, leader_point=None, force=False, leader_score=None, w2=0.5):
    """Play stage 2 unless even a perfect stage 2 couldn't reach the leader's score.

    The suite score is (1 - w2) x the stage-1 value + w2 x the stage-2 families, so the best this harness can reach
    is (1 - w2) x its stage-1 ub95 + w2 x 100. Until 2026-11-09 the rule compared the stage-1 ub95 with the leader's
    stage-1 point instead: once stage 1 saturated (labs z-capped at 1.5, MY1 in the 90s), the leader's single high
    stage-1 draw (100.6) cut harnesses whose OP1, half of the score and the only family that still separates them,
    was never played (the pooled leader among them). Without the leader's score, the old comparison is the fallback."""
    m = s1.get("metrics") or {}
    ub = m.get("ub95")
    if force:
        return True, "forced"
    if ub is None:
        return False, "no stage-1 score"
    ls = _num(leader_score)
    if ls is not None:
        best = (1 - w2) * float(ub) + w2 * OUTCOME_MAX
        return best >= ls, f"best case {best:.2f} (stage-1 ub95 {ub}, perfect stage 2) vs leader score {ls:g}"
    if leader_point in (None, ""):
        return True, "no leader yet"
    return ub >= float(leader_point), f"stage-1 ub95 {ub} vs leader stage-1 point {leader_point} (no leader score)"


def _num(x):
    try:
        return None if x in (None, "") else float(x)
    except (TypeError, ValueError):
        return None


def stage2_note(stage, full_suite=True, tier="", run_stage2=None, stage1_ub95=None, leader_point=None,
                leader_score=None, w2=0.5):
    """-> one line for the `stage2` metric: why OP1 was or wasn't played. Yukon's PR comment shows a stage-1-only
    result as "Scored 0" (it ignores `partial`), so this row is the submitter's only explanation."""
    ub, lp, ls = _num(stage1_ub95), _num(leader_point), _num(leader_score)
    if ub is not None and ls is not None:          # the rule since 2026-11-09 (stage2())
        best = (1 - w2) * ub + w2 * OUTCOME_MAX
        bar = (f"best case with a perfect OP1 {best:.2f} {'>=' if best >= ls else '<'} leader's score {ls:g}")
        reached = best >= ls
    else:
        bar = (f"stage-1 upper bound {ub:g} {'>=' if ub is not None and lp is not None and ub >= lp else '<'} "
               f"leader's stage-1 point {lp:g}") if ub is not None and lp is not None else None
        reached = bool(bar) and ub >= lp
        if lp is None:
            bar = None
    if str(stage) == "2":
        if lp is None and ls is None:
            return "played (no leader yet)"
        return f"played ({bar})" if bar and reached else "played (forced by the organiser)"
    tail = "; not a failure: Yukon records a stage-1-only result as 0, not promotable (SCORING.md §4)"
    if str(full_suite).lower() not in ("true", "1"):
        return f"skipped: tier {tier or '?'} plays stage 1 only (RULES.md tiers){tail}"
    if str(run_stage2).lower() == "false":
        why = (f"{bar}, so this harness could not lead and OP1 was not played" if bar
               else "no stage-1 score, so OP1 was not played")
        return f"skipped: {why}{tail}"
    return f"not completed: stage 2 was due but its games did not finish{tail}"


def judge_needed(scored, leader_score=None, min_gain=0.0, bips=0):
    m = scored.get("metrics") or {}
    if m.get("stage") != 2:
        return False, "stage 1 only: not promotable"
    sc = scored.get("score")
    if not isinstance(sc, (int, float)):
        return False, "no score"
    if leader_score in (None, ""):
        return True, "no leader yet"
    if bips:                                      # Yukon's own rule: judge exactly what Yukon would promote
        go, why = would_promote(sc, leader_score, bips)
        return go, why if go else f"would not be promoted: {why}"
    if sc > float(leader_score) + min_gain:
        return True, f"score {sc} beats the leader's {leader_score}"
    return False, f"score {sc} does not beat the leader's {leader_score}"


def improvement_bips(score, incumbent):
    """Yukon's rule (direction +): (score - incumbent) / |incumbent| x 10000; 0 if equal; inf over a 0 incumbent."""
    d = float(score) - float(incumbent)
    if d == 0:
        return 0.0
    if float(incumbent) == 0:
        return float("inf") if d > 0 else float("-inf")
    return d / abs(float(incumbent)) * 10000


def would_promote(score, incumbent=None, bips=0):
    if not isinstance(score, (int, float)):
        return False, "no score"
    if incumbent in (None, ""):
        return True, "no incumbent known (or Yukon unreadable): confirm, fail safe"
    b = improvement_bips(score, incumbent)
    need = float(bips or 0)
    ok = b >= need if need > 0 else b > 0
    return ok, f"score {score} vs incumbent {incumbent}: {b:+.0f} bips (needs {'>=' if need > 0 else '>'} {need:.0f})"


def second_batch(plans, n_by_task, tasks):
    """-> matrix: the plans' jobs for `tasks`, game ids shifted by the task's n (TASK-k -> TASK-(k+n))."""
    inc = []
    for plan in plans:
        for job in plan.get("include", []):
            games = []
            for g in job["games"].split(","):
                tid, _, k = g.rpartition("-")
                if tid in tasks and k.isdigit():
                    games.append(f"{tid}-{int(k) + n_by_task[tid]}")
            if games:
                inc.append({"job": f"c-{'-'.join(games)}"[:90], "games": ",".join(games),
                            "timeout_min": job["timeout_min"],
                            "play_timeout_min": job.get("play_timeout_min", job["timeout_min"])})
    return {"include": inc}


def has_second_batch(games_dir, n_by_task, tasks):
    if not games_dir or not os.path.isdir(games_dir):
        return False
    for name in os.listdir(games_dir):
        tid, _, k = name.rpartition("-")
        if tid in tasks and k.isdigit() and int(k) >= n_by_task[tid]:
            return True
    return False


def confirm(scored, plans, n_by_task, tasks, leader_score=None, bips=0, games_dir=None, off=False):
    """-> (confirm, reason, matrix)."""
    empty = {"include": []}
    m = scored.get("metrics") or {}
    if off:
        return False, "off (vars.DFBENCH_CONFIRM)", empty
    if m.get("stage") != 2:
        return False, "stage 1 only: not promotable", empty
    if has_second_batch(games_dir, n_by_task, tasks):
        return False, "already pooled (the games include a second batch)", empty
    go, why = would_promote(scored.get("score"), leader_score, bips)
    if not go:
        return False, f"would not be promoted: {why}", empty
    mx = second_batch(plans, n_by_task, tasks)
    if not mx["include"]:
        return False, "no long-task games in the plan", empty
    return True, f"would be promoted ({why}): {len(mx['include'])} confirmation games", mx


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("leader"); x.add_argument("--benchmark", required=True)
    x.add_argument("--fallback-point"); x.add_argument("--fallback-score")
    x = sp.add_parser("stage2"); x.add_argument("--stage1-score", required=True); x.add_argument("--leader-point")
    x.add_argument("--leader-score"); x.add_argument("--suite", default="")
    x.add_argument("--force", action="store_true")
    x = sp.add_parser("judge"); x.add_argument("--score", required=True); x.add_argument("--leader-score")
    x.add_argument("--min-gain", type=float, default=0.0); x.add_argument("--bips", type=float, default=0)
    x = sp.add_parser("leader-id"); x.add_argument("--benchmark", required=True)
    sp.add_parser("bips").add_argument("--manifest", default="")
    x = sp.add_parser("confirm"); x.add_argument("--score", required=True); x.add_argument("--plans", required=True)
    x.add_argument("--suite", required=True); x.add_argument("--leader-score"); x.add_argument("--bips", type=float, default=0)
    x.add_argument("--tasks", default=""); x.add_argument("--games-dir"); x.add_argument("--off", action="store_true")
    a = ap.parse_args()
    if a.cmd == "leader":
        try:
            point, score = leader(a.benchmark)
            src = "yukon"
        except Infra as e:
            if a.fallback_point is None and a.fallback_score is None:
                print(f"infra: cannot read the incumbent ({e})", file=sys.stderr); sys.exit(3)
            point, score, src = a.fallback_point or None, a.fallback_score or None, "leader file (Yukon unreachable)"
        print(f"leader_point={'' if point is None else point}"); print(f"leader_score={'' if score is None else score}")
        sys.stderr.write(f"leader ({src}): stage-1 point {point}, score {score}\n")
        return
    if a.cmd == "leader-id":
        try:
            print(f"leader_id={leader_id(a.benchmark) or ''}")
        except Infra as e:
            print(f"infra: cannot read Yukon's submissions ({e})", file=sys.stderr); sys.exit(3)
        return
    if a.cmd == "bips":
        print(manifest_bips(a.manifest or None))
        return
    if a.cmd == "stage2":
        s1 = json.load(open(a.stage1_score))
        suite = json.load(open(a.suite)) if a.suite else None
        go, why = stage2(s1, a.leader_point, a.force, a.leader_score, stage2_weight(suite))
        m = s1.get("metrics") or {}
        print(f"run_stage2={'true' if go else 'false'}")
        print(f"stage1_point={'' if m.get('point') is None else m['point']}")
        print(f"stage1_ub95={'' if m.get('ub95') is None else m['ub95']}")
        sys.stderr.write(f"gate: {why} -> stage 2 {go}\n")
    elif a.cmd == "confirm":
        suite = json.load(open(a.suite))
        tasks = [t for t in a.tasks.split(",") if t] or SU.confirm_tasks(suite)   # default: the suite's
        n_by = {t["id"]: int(t.get("n", 8)) for t in suite["tasks"]}
        plans = [json.loads(open(p).read()) if os.path.exists(p) else json.loads(p) for p in a.plans.split(";")]
        go, why, mx = confirm(json.load(open(a.score)), plans, n_by, tasks, a.leader_score, a.bips, a.games_dir, a.off)
        print(f"confirm={'true' if go else 'false'}"); print(f"reason={why}"); print(f"matrix={json.dumps(mx)}")
        sys.stderr.write(f"confirmation: {go} ({why})\n")
    else:
        go, why = judge_needed(json.load(open(a.score)), a.leader_score, a.min_gain, a.bips)
        print(f"judge={'true' if go else 'false'}"); print(f"reason={why}")
        sys.stderr.write(f"judge needed: {go} ({why})\n")


if __name__ == "__main__":
    main()
