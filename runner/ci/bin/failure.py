#!/usr/bin/env python3
"""runner/ci/bin/failure.py: actionable admission failures (tester feedback, 2026-10-28).

A failure on the way to a scored game says four things, so the submitter knows whether to act: the failing endpoint
(or step), the HTTP status, whether a retry can help, and who can resolve it (submitter | organiser | Yukon |
GitHub). tier.py, ledger.py and score.yml write one record per failure to `<who dir>/admit_error.json`; score.yml
shows it in the step log, the job summary and the submission PR's comment. Python 3 stdlib only.

  failure.py render --file admit_error.json [--format log|summary|comment]
"""
import argparse, json, re, sys



def classify(endpoint, status=None, detail=""):
    """-> {endpoint, status, retryable, owner, cause, action}. `endpoint`: a URL path (e.g. /api/submissions/<id>),
    a host-qualified path, or a step name; `status`: the HTTP status (int) or None for connection errors."""
    ep = endpoint or "?"
    s = status if isinstance(status, int) else None
    server = s is not None and (s >= 500 or s == 429)
    conn = s is None and bool(re.search(r"URLError|Timeout|OSError|connection", detail, re.I))
    if "api.github.com" in ep or ep.startswith("github:"):
        owner, cause = "GitHub", ("GitHub's API rate-limited or refused the account lookup" if s in (403, 429)
                                  else "GitHub's API couldn't be read")
        retry = s in (403, 429) or server or conn or s is None
    elif "/attribution" in ep:
        owner, retry = "Yukon", True
        cause = ("the submission's attribution record isn't readable by the organiser key yet (Yukon shows it only "
                 "to its author until the submission is published)" if s == 404
                 else "Yukon's attribution record couldn't be read")
    elif ep.startswith("/api/solvers/"):
        owner, retry = "Yukon", True
        cause = "Yukon's solver profile (for the tier) couldn't be read"
    elif ep.startswith("/api/submissions/"):
        owner, retry = "Yukon", True
        cause = ("Yukon has no record of this submission yet" if s == 404
                 else "Yukon's submission record couldn't be read")
    elif ep.startswith("ledger") or "dfbench-ops" in ep:
        owner, retry = "organiser", True
        cause = "the organiser's ledger couldn't be read or written"
    elif ep.startswith("config:"):
        owner, retry = "organiser", False
        cause = f"the scoring workflow is misconfigured ({ep[7:]})"
    else:
        owner, retry = "organiser", bool(server or conn)
        cause = detail or f"{ep} failed"
    if s in (401, 403) and owner == "Yukon":
        owner, retry = "organiser", False
        cause = "the organiser's Yukon key was refused (check YUKON_API_KEY and DFBENCH_YUKON_API)"
    if server or conn:
        cause += " (the service answered with an error or didn't answer)"
    if owner == "submitter":
        action = "fix your submission and resubmit"
    elif retry:
        action = "not your fault: resubmit (it isn't counted), or wait for the organiser to re-run it"
    else:
        action = "not your fault: the organiser has to fix this; resubmitting won't help until they do"
    return {"endpoint": ep, "status": s, "retryable": bool(retry), "owner": owner, "cause": cause, "action": action}


def render(rec, fmt="log"):
    st = rec.get("status")
    head = f"{rec.get('cause')}"
    facts = (f"endpoint `{rec.get('endpoint')}`, " + (f"HTTP {st}, " if st else "no HTTP status, ") +
             f"{'retryable' if rec.get('retryable') else 'not retryable'}, resolved by: {rec.get('owner')}")
    if fmt == "log":
        return f"admission failed: {head} [{facts}]. {rec.get('action')}"
    if fmt == "summary":
        return (f"### Admission failed: not scored, not counted\n\n- **Cause:** {head}\n- **Where:** {facts}\n"
                f"- **What to do:** {rec.get('action')}\n")
    return f"{head}.\n\n- {facts}\n- **What to do:** {rec.get('action')}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("render"); r.add_argument("--file", required=True)
    r.add_argument("--format", choices=["log", "summary", "comment"], default="log")
    a = ap.parse_args()
    print(render(json.load(open(a.file)), a.format))


if __name__ == "__main__":
    sys.exit(main())
