#!/usr/bin/env python3
"""runner/ci/bin/dispatch.py: what kind of run this is, from the ref Yukon dispatched it on.

  dispatch.py classify --ref REF --sha SHA [--out-dir DIR]     prints kind=, submission=, tier=, user=

Yukon (scalar mode, @ bd7fb62) dispatches the scoring workflow on two kinds of branch, with no inputs:
- `submissions/<submission id>` (a UUID): a competitor's submission, PR open (src/execution/github-actions.ts:70);
- `yukon/baseline/<sourceRef>[/<track>]`: the import-time baseline, no PR, no submitter
  (github-actions.ts:71 and baselineBranchName, :1407). The baseline's score becomes the benchmark's baseline and
  its first currentBest (src/store/postgres.ts:1981), so it plays the full suite like any complete submission.

kind=baseline: no tier, no ledger slot, no judge (nothing to promote; the baseline is main itself). With
--out-dir, writes the same submitter.json/note.md/deps.json tier.py writes for a submission, so later jobs read one
shape. Any other ref exits 2: the workflow scores only what Yukon dispatches (an organiser re-run of a submission
uses its submissions/<id> ref).
"""
import argparse, json, os, re, sys

UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
BASELINE = re.compile(r"^yukon/baseline/([0-9a-fA-F]{7,40})(?:/[A-Za-z0-9._-]+)?$")
BASELINE_LIMITS = {"in_flight": 1, "weekly": 0, "suite": "full"}


class NotScorable(Exception):
    pass


def classify(ref, sha):
    """-> dict(kind, submission, user, tier). Raises NotScorable."""
    if ref.startswith("submissions/"):
        sub = ref[len("submissions/"):]
        if not UUID.match(sub):
            raise NotScorable(f"{ref}: the submission id is not a UUID")
        return {"kind": "submission", "submission": sub, "user": "", "tier": ""}
    m = BASELINE.match(ref)
    if m:
        if not sha.lower().startswith(m.group(1).lower()):
            raise NotScorable(f"{ref}: the branch names {m.group(1)} but the run is at {sha}")
        return {"kind": "baseline", "submission": f"baseline-{sha[:12]}", "user": "(baseline)", "tier": "baseline"}
    raise NotScorable(f"{ref}: not a Yukon submission or baseline branch")


def baseline_files(r, sha, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, "note.md"), "w").write("")
    json.dump({"declaration": "none", "dependencies": []}, open(os.path.join(out_dir, "deps.json"), "w"), indent=1)
    json.dump({"submission": r["submission"], "username": r["user"], "coauthors": [], "benchmark_id": None,
               "commit": sha, "tier": "baseline", "reason": "Yukon import baseline", "limits": BASELINE_LIMITS,
               "declaration": "none", "dependencies": []},
              open(os.path.join(out_dir, "submitter.json"), "w"), indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("classify"); x.add_argument("--ref", required=True); x.add_argument("--sha", required=True)
    x.add_argument("--out-dir")
    a = ap.parse_args()
    try:
        r = classify(a.ref, a.sha)
    except NotScorable as e:
        print(f"not scorable: {e}", file=sys.stderr)
        sys.exit(2)
    if r["kind"] == "baseline" and a.out_dir:
        baseline_files(r, a.sha, a.out_dir)
    for k in ("kind", "submission", "user", "tier"):
        print(f"{k}={r[k]}")
    if r["kind"] == "baseline":
        l = BASELINE_LIMITS
        for k in ("in_flight", "weekly", "suite"):
            print(f"{k}={l[k]}")
        print("benchmark=")


if __name__ == "__main__":
    main()
