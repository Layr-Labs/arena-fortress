#!/usr/bin/env python3
"""runner/ci/bin/attribution_verify.py: verify attribution after publication (challenge/RULES.md §8a; RUNBOOK §2.6).

Yukon shows a submission's declared dependencies only to its author until the submission is published, so the
judge often scores with the formal list hidden (attribution_verified: false; it then judges from the note and the
code). Once published, the list is readable: this re-checks recent unverified ledger entries against it.

  attribution_verify.py check [--days 14] [--max 20] [--comment]

For each scored or rejected entry whose attribution was recorded unverified and not yet checked: read
GET {api}/api/submissions/<id>/attribution. Still hidden (404) -> skipped, try again next run. Otherwise every base
producer and overlap suspect the judge recorded (ledger.py attribution) must be in the declared list:
verified_ok, or verify_flagged with the missing ids. Flags go to the job summary and, with --comment, to the
submission's PR. Report only: it never changes Yukon's result. Bounded and fail-soft: any error skips the entry.
Env: as ledger.py, plus DFBENCH_YUKON_API and YUKON_API_KEY (tier.yukon_headers), GH_TOKEN for --comment.
"""
import argparse, datetime, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ledger, tier  # noqa: E402


def pending(led, days, cap, t=None):
    t = t or datetime.datetime.now(datetime.timezone.utc)
    out = []
    for e in reversed((led or {}).get("entries", [])):
        rec = e.get("attribution") or {}
        if rec.get("verified") is not False or rec.get("checked") or e.get("status") not in ledger.SCORED:
            continue
        try:
            age = t - datetime.datetime.fromisoformat(rec.get("judged") or e.get("updated"))
        except (TypeError, ValueError):
            continue
        if age.days <= days:
            out.append(e)
        if len(out) >= cap:
            break
    return out


def judge_entry(e, att):
    """-> (result, reason) given the published attribution record."""
    declared = {d.get("submissionId") for d in (att.get("dependencies") or []) if isinstance(d, dict)}
    rec = e.get("attribution") or {}
    need = [x for x in rec.get("base_producers", []) + rec.get("suspects", []) if x and x != e["submission"]]
    missing = sorted({x for x in need if x not in declared})
    if missing:
        return "verify_flagged", "published declaration doesn't name: " + ", ".join(missing)
    return "verified_ok", f"published declaration names all {len(set(need))} recorded base/overlap submission(s)"


def comment(sid, body, repo=None):
    repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
    pr = subprocess.run(["gh", "pr", "list", "-R", repo, "--head", f"submissions/{sid}", "--state", "all",
                         "--json", "number", "-q", ".[0].number"], capture_output=True, text=True).stdout.strip()
    if pr:
        subprocess.run(["gh", "pr", "comment", pr, "-R", repo, "--body", body], capture_output=True, text=True)


def check(days=14, cap=20, do_comment=False, env=os.environ, http=None):
    api = (env.get("DFBENCH_YUKON_API") or "").rstrip("/")
    led, _ = ledger.load("ledger.json")
    lines = []
    for e in pending(led, days, cap):
        sid = e["submission"]
        try:
            att = (http or tier.http_json)(f"{api}/api/submissions/{sid}/attribution", tier.yukon_headers(env))
        except tier.Infra as err:
            lines.append(f"- `{sid}`: skipped ({err})")
            continue
        result, reason = judge_entry(e, att)
        a = argparse.Namespace(submission=sid, result=result, reason=reason, verified=None, basis=None,
                               base_producers="", suspects="")
        ledger.update("ledger.json", lambda l: ledger.attribution_decision(l, a), f"attribution check {sid}: {result}",
                      lambda: {"entries": [], "users": {}})
        lines.append(f"- `{sid}` ({e.get('user')}): **{result}**: {reason}")
        if result == "verify_flagged" and do_comment:
            comment(sid, f"**dfbench attribution check (after publication): flagged for the organiser.** {reason}. "
                         "During scoring the formal dependency list was hidden by Yukon; the organiser will review "
                         "(RULES §8: correct the attribution, or the result may be unranked).")
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("check"); x.add_argument("--days", type=int, default=14); x.add_argument("--max", type=int, default=20)
    x.add_argument("--comment", action="store_true")
    a = ap.parse_args()
    try:
        lines = check(a.days, a.max, a.comment)
    except SystemExit as e:              # ledger.load exits on HTTP errors: fail soft
        print(f"attribution check skipped: {e}", file=sys.stderr)
        return
    text = "### Attribution checks after publication\n" + ("\n".join(lines) if lines else "(nothing pending)") + "\n"
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(text)


if __name__ == "__main__":
    main()
