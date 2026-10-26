#!/usr/bin/env python3
"""runner/ci/bin/tier.py: who submitted, and their tier (challenge/RULES.md §7; docs/SCORING-INFRA.md §5.5).

  tier.py resolve --submission ID --out-dir DIR      writes DIR/submitter.json, DIR/note.md, DIR/deps.json
                                                     and prints one line: user, tier, limits (nothing private)

Sources (Yukon @ c708d54, read 2026-10-23):
- GET {api}/api/submissions/{id}            public: submission.solverUsername, coauthors, note, benchmarkId,
                                            submissionCommitSha (optionalViewerAuth; the organiser key is sent if set)
- GET {api}/api/submissions/{id}/attribution  {declaration, dependencies: [{submissionId, rationale, evidence}]};
                                            readable once the candidate commit exists, i.e. during scoring
- GET {api}/api/solvers/{username}/profile  public: participations[] {benchmark {id, challengeId}, contributions[]
                                            {submission {status, promotionStatus}}}; it lists promoted results only
                                            on automatic benchmarks. In scalar mode an improving submission becomes
                                            `accepted` (a valid non-improving one is `rejected`; accepted may later
                                            be superseded): we count status accepted or promotionStatus promoted /
                                            superseded on a benchmark that isn't ours (nor this challenge's)
- GET https://api.github.com/users/{login}  created_at

Tiers (challenge/RULES.md §7, decided 2026-10-23): established = a promoted result on another Yukon benchmark OR a
valid score on ours already (our ledger's first_valid); otherwise probation if the GitHub account is younger than
probation_days, else new.

Tier rules: env DFBENCH_TIERS (JSON, merged over DEFAULT_TIERS), overrides DFBENCH_TIER_OVERRIDES ({username: tier}).
Fail closed: any error reaching Yukon or GitHub -> exit 3 with "infra:" (the run stops before any game; the ledger
is untouched, so it doesn't count). There is no path that skips the limits.

Env: DFBENCH_YUKON_API (base URL, required: dev https://yukon-api-dev.fly.dev or prod https://yukon-api-prod.fly.dev), YUKON_API_KEY (optional bearer), DFBENCH_YUKON_CHALLENGE_ID (optional),
     GITHUB_TOKEN (for api.github.com; optional, raises the rate limit), DFBENCH_TIERS, DFBENCH_TIER_OVERRIDES;
     for the "valid score here" check the ledger in the ops store: DFBENCH_OPS_TOKEN, DFBENCH_OPS_REPO, DFBENCH_SEASON.
"""
import argparse, datetime, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

DEFAULT_TIERS = {
    "established": {"in_flight": 1, "weekly": 7, "suite": "full"},
    "new": {"in_flight": 1, "weekly": 2, "suite": "stage1_until_first_valid"},
    "probation": {"in_flight": 1, "weekly": 1, "suite": "stage1"},
    "probation_days": 30,
}
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


class Infra(Exception):
    pass


def yukon_headers(env=os.environ):
    """The organiser's bearer for Yukon reads, if YUKON_API_KEY is set. A hidden row (the dev demo) may answer 404
    to anonymous reads, so every Yukon call in the workflow goes through this."""
    return {"Authorization": f"Bearer {env['YUKON_API_KEY']}"} if env.get("YUKON_API_KEY") else {}


def http_json(url, headers=None, tries=3, opener=None):
    """GET url -> JSON. Retries 5xx/429/connection errors; 4xx other than 429 is final. Raises Infra."""
    opener = opener or urllib.request.urlopen
    last = None
    for i in range(tries):
        req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "dfbench-admit",
                                                   **(headers or {})})
        try:
            with opener(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code != 429 and e.code < 500:
                raise Infra(f"{urllib.parse.urlsplit(url).path}: {last}")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            last = type(e).__name__
        time.sleep(2 ** i)
    raise Infra(f"{urllib.parse.urlsplit(url).path}: {last}")


def tiers_config(env=os.environ):
    cfg = json.loads(json.dumps(DEFAULT_TIERS))
    for k, v in json.loads(env.get("DFBENCH_TIERS") or "{}").items():
        cfg[k] = {**cfg.get(k, {}), **v} if isinstance(v, dict) else v
    return cfg


def is_established(profile, our_benchmark, our_challenge=None):
    for p in profile.get("participations") or []:
        b = p.get("benchmark") or {}
        if b.get("id") == our_benchmark or (our_challenge and b.get("challengeId") == our_challenge):
            continue
        for c in p.get("contributions") or []:
            sub = c.get("submission") or {}
            if sub.get("status") == "accepted" or sub.get("promotionStatus") in ("promoted", "superseded"):
                return True
    return False


def account_age_days(created_at, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    t = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    return (now - t).total_seconds() / 86400


def decide(username, profile, gh_user, our_benchmark, cfg, overrides, our_challenge=None, now=None, valid_here=False):
    """-> (tier, reason). Overrides win; then established (promoted elsewhere, or a valid score here); then
    probation by GitHub account age; else new."""
    if username in overrides:
        t = overrides[username]
        if t not in cfg or not isinstance(cfg[t], dict):
            raise Infra(f"override names unknown tier {t!r}")
        return t, "organiser override"
    if is_established(profile, our_benchmark, our_challenge):
        return "established", "promoted result on another Yukon benchmark"
    if valid_here:
        return "established", "valid score on this benchmark"
    age = account_age_days(gh_user["created_at"], now)
    if age < float(cfg.get("probation_days", 30)):
        return "probation", f"GitHub account {age:.0f} days old"
    return "new", "no promoted result elsewhere, no valid score here yet"


def ledger_valid_here(username, env=os.environ):
    """True if our ledger (ops store) records a first valid score for this user. Raises Infra if unreadable."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ledger
    try:
        led, _ = ledger.load("ledger.json")
    except SystemExit as e:
        raise Infra(f"ledger: {e}")
    return bool(((led or {}).get("users") or {}).get(username, {}).get("first_valid"))


def resolve(submission_id, env=os.environ, http=http_json, now=None, valid_here=ledger_valid_here):
    if not UUID.match(submission_id or ""):
        raise Infra(f"submission id {submission_id!r} is not a UUID (ref submissions/<id>)")
    api = (env.get("DFBENCH_YUKON_API") or "").rstrip("/")
    if not api.startswith("https://"):
        raise Infra("DFBENCH_YUKON_API is not set to an https URL")
    yh = yukon_headers(env)
    sub = http(f"{api}/api/submissions/{submission_id}", yh)["submission"]
    user = sub.get("solverUsername")
    if not user or not LOGIN.match(user):
        raise Infra("submission has no usable solverUsername")
    att = http(f"{api}/api/submissions/{submission_id}/attribution", yh)
    prof = http(f"{api}/api/solvers/{urllib.parse.quote(user)}/profile", yh)
    gh = {"Authorization": f"Bearer {env['GITHUB_TOKEN']}"} if env.get("GITHUB_TOKEN") else {}
    ghu = http(f"https://api.github.com/users/{urllib.parse.quote(user)}", gh)
    cfg = tiers_config(env)
    overrides = json.loads(env.get("DFBENCH_TIER_OVERRIDES") or "{}")
    tier, reason = decide(user, prof, ghu, sub.get("benchmarkId"), cfg, overrides,
                          env.get("DFBENCH_YUKON_CHALLENGE_ID") or None, now, valid_here(user))
    return {
        "submission": submission_id, "username": user, "coauthors": sub.get("coauthors") or [],
        "benchmark_id": sub.get("benchmarkId"), "commit": sub.get("submissionCommitSha"),
        "tier": tier, "reason": reason, "limits": cfg[tier],
        "declaration": att.get("declaration"), "dependencies": att.get("dependencies") or [],
        "note": sub.get("note") or "",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("resolve"); x.add_argument("--submission", required=True); x.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    try:
        r = resolve(a.submission)
    except Infra as e:
        print(f"infra: cannot establish the submitter's tier ({e}); not scored, not counted", file=sys.stderr)
        sys.exit(3)
    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "note.md"), "w") as f:
        f.write(r["note"])
    with open(os.path.join(a.out_dir, "deps.json"), "w") as f:
        json.dump({"declaration": r["declaration"], "dependencies": r["dependencies"]}, f, indent=1)
    with open(os.path.join(a.out_dir, "submitter.json"), "w") as f:
        json.dump({k: v for k, v in r.items() if k != "note"}, f, indent=1)
    l = r["limits"]
    print(f"submitter {r['username']}: tier {r['tier']} ({r['reason']}); in flight {l['in_flight']}, "
          f"weekly {l['weekly']}, suite {l['suite']}; {len(r['dependencies'])} declared dependencies")


if __name__ == "__main__":
    main()
