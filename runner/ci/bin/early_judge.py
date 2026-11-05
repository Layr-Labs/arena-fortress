#!/usr/bin/env python3
"""runner/ci/bin/early_judge.py: decisions for the judge run before any game (score.yml job early-judge, enabled by
vars.DFBENCH_JUDGE_EARLY; challenge/RULES.md §8a).

  early_judge.py verdict DOSSIER                      prints verdict=pass|fail|hold|error and go=true|false
  early_judge.py reuse --early V --early-leader A --leader B     prints reuse=true|false and reason=...
  early_judge.py stub OUT                             writes the score.json body for a submission stopped early

verdict: the dossier's verdict. A missing or unreadable dossier, no verdict in it, or a hold whose every condition is
  the judge's own infrastructure (runner/judge committee: "judge infrastructure failure: ..." for a provider error,
  malformed output or the cost cap) is `error`: the games still run and the end-of-run judge runs as before, which
  fails closed. A hold with any other condition (size limit, a finding for an organiser, manipulation) stops the run.
  So early is fail-open on our errors and final on a real fail or hold; go=false only for fail and hold.
reuse: at the end, a passing early dossier stands in for the judge when the incumbent is the one the early judge saw
  (attribution is judged against the incumbent, the base producer); a different or unknown incumbent re-runs it.
stub: score 0, partial, stage 0, no games; emit_score.py --dossier then sets judge_verdict (fail or hold)."""
import argparse, json, os, sys

STOPPED = ("fail", "hold")


INFRA = "judge infrastructure failure"


def verdict(path):
    try:
        d = json.load(open(path))
        v = d.get("verdict")
    except (OSError, ValueError, AttributeError):
        return "error"
    if v not in ("pass", "fail", "hold"):
        return "error"
    conds = d.get("hold_conditions") or []
    if v == "hold" and conds and all(str(c).startswith(INFRA) for c in conds):
        return "error"      # our outage, not a finding: don't stop the submitter's run on it
    return v


def reuse(early, early_leader, leader):
    if early != "pass":
        return False, f"early verdict {early or 'none'}"
    known = lambda x: x not in (None, "", "unknown")
    if not (known(early_leader) and known(leader)):
        return False, "incumbent unknown at the start or now (fail safe: judge again)"
    if early_leader != leader:
        return False, f"incumbent changed during the run ({early_leader[:8]} -> {leader[:8]}): judge again"
    return True, f"incumbent unchanged ({leader[:8]}): the early pass stands"


def stub():
    return {"score": 0, "partial": True,
            "metrics": {"stage": 0, "games": "0 scored / 0 run", "judge_stage": "early",
                        "games_note": "not played: the judge failed or held this submission before any game "
                                      "(challenge/RULES.md §8a); this attempt counts"}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("verdict").add_argument("dossier")
    x = sp.add_parser("reuse"); x.add_argument("--early", default=""); x.add_argument("--early-leader", default="")
    x.add_argument("--leader", default="")
    sp.add_parser("stub").add_argument("out")
    a = ap.parse_args()
    if a.cmd == "verdict":
        v = verdict(a.dossier)
        print(f"verdict={v}"); print(f"go={'false' if v in STOPPED else 'true'}")
    elif a.cmd == "reuse":
        ok, why = reuse(a.early, a.early_leader, a.leader)
        print(f"reuse={'true' if ok else 'false'}"); print(f"reason={why}")
    else:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        json.dump(stub(), open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
