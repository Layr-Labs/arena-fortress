#!/usr/bin/env python3
"""runner/ci/bin/emit_score.py: the ONE place that writes the file Yukon reads (scorePath, artifact dfbench-score)
from the trusted score and the judge's verdict (docs/SCORING-INFRA.md §5.9; challenge/RULES.md §8a).

  emit_score.py --mode scalar|pareto --score scored.json --out .yukon/score.json
                [--dossier dossier.json | --override pass|fail --actor X | --not-run REASON] [--set k=v ...]

Verdict (the same in both modes): the dossier's `verdict` (pass | fail | hold); an organiser override (pass | fail);
or "not run" (the judge wasn't needed: the score can't change the board). A missing or unreadable dossier, or any
other verdict, is `hold` (fail closed).

scalar (season 0 today; promotionMode automatic):
  pass / not run -> the trusted score as is, metrics.judge_verdict
  fail / hold    -> score 0, partial true, metrics.judge_verdict, metrics.score_if_accepted: Yukon records a
                    non-improving result and doesn't promote (the Distillation sentinel) [Yukon Q7]
pareto (Yukon docs/pareto-mode.md; NOT exercised yet, kept so the switch is one flag):
  {"valid": verdict == pass and the run is complete (stage 2), "reason": ..., "scores": [lb95, credits per
   game-year] | null, "metrics": {...}}. Objectives (to declare): S_lcb "+", credits_per_game_year "-".
Prints the verdict and the emitted score only.
"""
import argparse, json, os


def verdict_of(dossier=None, override=None, actor=None, not_run=None):
    """-> (verdict, note). verdict in pass | fail | hold | not_run."""
    if override:
        return override, f"organiser override by {actor or 'organiser'}"
    if not_run:
        return "not_run", not_run
    v = (dossier or {}).get("verdict")
    if v in ("pass", "fail", "hold"):
        return v, None
    return "hold", "no readable verdict (fail closed)"


def emit(score, mode="scalar", dossier=None, override=None, actor=None, not_run=None, extra=None):
    s = json.loads(json.dumps(score))
    m = dict(s.get("metrics") or {})
    m.update(extra or {})
    verdict, note = verdict_of(dossier, override, actor, not_run)
    m["judge_verdict"] = verdict if verdict != "not_run" else f"not_run: {note}"
    if note and verdict != "not_run":
        m["judge_note"] = note
    if mode == "pareto":
        complete = m.get("stage") == 2
        valid = verdict == "pass" and complete
        reason = ("judge passed" if valid else
                  "stage 1 only" if verdict == "pass" else
                  f"judge {verdict}" + (f": {note}" if note else ""))
        scores = [s.get("score") if complete else m.get("lb95"), m.get("credits_per_game_year")]
        out = {"valid": valid, "reason": reason, "metrics": m}
        out["scores"] = scores if all(isinstance(x, (int, float)) for x in scores) else None
        if not valid and out["scores"] is None:
            out.pop("scores")
        return out
    s["metrics"] = m
    if verdict in ("fail", "hold"):
        m["score_if_accepted"] = s.get("score")
        s["score"] = 0
        s["partial"] = True
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["scalar", "pareto"], default="scalar")
    ap.add_argument("--score", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--dossier"); ap.add_argument("--override", choices=["pass", "fail"]); ap.add_argument("--actor")
    ap.add_argument("--not-run"); ap.add_argument("--set", action="append", default=[], metavar="K=V")
    a = ap.parse_args()
    dossier = None
    if a.dossier and os.path.exists(a.dossier):
        try:
            dossier = json.load(open(a.dossier))
        except ValueError:
            dossier = None
    extra = dict(x.split("=", 1) for x in a.set)
    out = emit(json.load(open(a.score)), a.mode, dossier, a.override, a.actor, a.not_run, extra)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=1)
    print(f"judge_verdict {out['metrics']['judge_verdict']}; "
          + (f"score {out['score']}" if a.mode == "scalar" else f"valid {out['valid']} scores {out.get('scores')}"))


if __name__ == "__main__":
    main()
