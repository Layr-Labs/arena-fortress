#!/usr/bin/env python3
"""runner/ci/bin/gate.py: the leader and the comparisons with it, isolated (docs/SCORING-INFRA.md §5.4). Scalar
mode compares with one leader; a Pareto season would replace these checks with a frontier check.

  gate.py leader --benchmark ID [--fallback-point X --fallback-score Y]   prints leader_point=, leader_score=
leader: Yukon's incumbent, authoritative (GET {DFBENCH_YUKON_API}/api/benchmarks/{id}: currentBestScore and
        currentBestMetrics.stage1_point, which our score.json carries). If Yukon can't be read, the fallback values
        (the leader file in the ops store) are used when given, else it exits 3 (infra).

  gate.py stage2 --stage1-score s1.json [--leader-point X] [--force]       prints run_stage2=true|false
  gate.py judge  --score scored.json [--leader-score Y] [--min-gain 0]    prints judge=true|false and reason=...
stage2: run OP1 iff the stage-1 ub95 >= the leader's stage-1 point (always if there's no leader, or --force).
judge:  run the judge iff the run is complete (stage 2) and its score beats the leader's by more than --min-gain
        (always when there's no leader). Otherwise Yukon can't promote it, so the judge is not needed.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tier import Infra, http_json, yukon_headers  # noqa: E402


def leader(benchmark_id, env=os.environ, http=http_json):
    """-> (stage1_point | None, score | None) from Yukon's incumbent. Raises Infra."""
    api = (env.get("DFBENCH_YUKON_API") or "").rstrip("/")
    if not api.startswith("https://"):
        raise Infra("DFBENCH_YUKON_API is not set to an https URL")
    h = yukon_headers(env)
    b = http(f"{api}/api/benchmarks/{benchmark_id}", h)["benchmark"]
    m = b.get("currentBestMetrics") or {}
    return m.get("stage1_point"), b.get("currentBestScore")


def stage2(s1, leader_point=None, force=False):
    m = s1.get("metrics") or {}
    ub = m.get("ub95")
    if force:
        return True, "forced"
    if ub is None:
        return False, "no stage-1 score"
    if leader_point in (None, ""):
        return True, "no leader yet"
    return ub >= float(leader_point), f"stage-1 ub95 {ub} vs leader {leader_point}"


def judge_needed(scored, leader_score=None, min_gain=0.0):
    m = scored.get("metrics") or {}
    if m.get("stage") != 2:
        return False, "stage 1 only: not promotable"
    sc = scored.get("score")
    if not isinstance(sc, (int, float)):
        return False, "no score"
    if leader_score in (None, ""):
        return True, "no leader yet"
    if sc > float(leader_score) + min_gain:
        return True, f"score {sc} beats the leader's {leader_score}"
    return False, f"score {sc} does not beat the leader's {leader_score}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("leader"); x.add_argument("--benchmark", required=True)
    x.add_argument("--fallback-point"); x.add_argument("--fallback-score")
    x = sp.add_parser("stage2"); x.add_argument("--stage1-score", required=True); x.add_argument("--leader-point")
    x.add_argument("--force", action="store_true")
    x = sp.add_parser("judge"); x.add_argument("--score", required=True); x.add_argument("--leader-score")
    x.add_argument("--min-gain", type=float, default=0.0)
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
    if a.cmd == "stage2":
        s1 = json.load(open(a.stage1_score))
        go, why = stage2(s1, a.leader_point, a.force)
        m = s1.get("metrics") or {}
        print(f"run_stage2={'true' if go else 'false'}")
        print(f"stage1_point={'' if m.get('point') is None else m['point']}")
        sys.stderr.write(f"gate: {why} -> stage 2 {go}\n")
    else:
        go, why = judge_needed(json.load(open(a.score)), a.leader_score, a.min_gain)
        print(f"judge={'true' if go else 'false'}"); print(f"reason={why}")
        sys.stderr.write(f"judge needed: {go} ({why})\n")


if __name__ == "__main__":
    main()
