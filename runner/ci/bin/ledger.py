#!/usr/bin/env python3
"""runner/ci/bin/ledger.py: the organiser's submission ledger and leader file (docs/SCORING-INFRA.md §5.4-5.5).

Both live in the organiser-only store (default Layr-Labs/dfbench-ops, private), on its main branch, as
`seasons/<season>/ledger.json` and `seasons/<season>/leader.json`. The scoring workflow writes them with
DFBENCH_OPS_TOKEN (environment secret; contents: write on that repo only). Writes go through the GitHub contents API
with the file's sha (optimistic concurrency, retried on conflict), so two runs can't both take the last slot of a
user's week or of the global allowance. Python 3 stdlib only.

  admit   --submission ID --user U --in-flight N --weekly N --suite S [--global N] [--rerun] [--run ID] [--tree T]
          reserve a slot; prints {"admitted", "reason", "full_suite", "week", ...}; a submission/ tree (T, the git
          tree id) identical to one already scored this season is refused and not counted
  finish  --submission ID --status scored|infra_failed|rejected|cancelled [--score X] [--stage N] [--run ID]
          `scored` also records the user's first valid score here (unlocks the full suite for tier `new`)
  leader-get [--field stage1_point|score|submission]       prints the field ("" if no leader)
  leader-set --stage1-point X --submission ID [--score Y] [--note TEXT]
  show    [--user U]

Rules (challenge/RULES.md §7; per user, no teams; the limits bound the organiser's spend): a week is the ISO week
(UTC, Monday 00:00). Counted: reserved, scored and rejected entries (a rejected harness still used the runners). Not
counted: infra_failed and cancelled. In flight: at most --in-flight `reserved` entries per user. Weekly: at most
--weekly counted entries per user. Global: at most --global counted entries per week over all users; when it is used
up the admit is refused with the date the next week starts, and nothing is written (not counted). Suite: `full`,
`stage1`, or `stage1_until_first_valid` (full once the user has a first valid score here). `--rerun` (an organiser
re-dispatch of the same submission) never takes a new slot and isn't refused by the limits.

Env: DFBENCH_OPS_TOKEN, else GITHUB_TOKEN or GH_TOKEN; DFBENCH_OPS_REPO (default Layr-Labs/dfbench-ops); DFBENCH_OPS_BRANCH (main);
     DFBENCH_SEASON (s0).
"""
import argparse, base64, datetime, json, os, sys, time, urllib.error, urllib.request

REPO = os.environ.get("DFBENCH_OPS_REPO", "Layr-Labs/dfbench-ops")
BRANCH = os.environ.get("DFBENCH_OPS_BRANCH", "main")
SEASON = os.environ.get("DFBENCH_SEASON", "s0")
COUNTED = {"reserved", "scored", "rejected"}
SCORED = {"scored", "rejected"}          # a result exists (rejected: scored, then excluded by an organiser)


def api(method, path, body=None):
    tok = os.environ.get("DFBENCH_OPS_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not tok:
        sys.exit("ledger: set GITHUB_TOKEN")
    req = urllib.request.Request("https://api.github.com" + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "dfbench-ledger"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


def load(name):
    st, r = api("GET", f"/repos/{REPO}/contents/seasons/{SEASON}/{name}?ref={BRANCH}")
    if st == 404:
        return None, None
    if st != 200:
        sys.exit(f"ledger: GET {name}: HTTP {st}")
    return json.loads(base64.b64decode(r["content"])), r["sha"]


def save(name, obj, sha, msg):
    body = {"message": msg, "branch": BRANCH,
            "content": base64.b64encode((json.dumps(obj, indent=1, sort_keys=True) + "\n").encode()).decode()}
    if sha:
        body["sha"] = sha
    st, _ = api("PUT", f"/repos/{REPO}/contents/seasons/{SEASON}/{name}", body)
    return st in (200, 201)


def update(name, fn, msg, empty):
    for attempt in range(8):
        obj, sha = load(name)
        obj = obj if obj is not None else empty()
        result = fn(obj)
        if result is None or result.get("_nowrite"):
            return result
        if save(name, obj, sha, msg):
            return result
        time.sleep(1 + attempt)                 # 409/422: someone else wrote; reload and re-decide
    sys.exit(f"ledger: could not write {name} after retries")


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def week_of(ts):
    y, w, _ = datetime.datetime.fromisoformat(ts).isocalendar()
    return f"{y}-W{w:02d}"


def next_week_start(t=None):
    t = t or now()
    d = (t - datetime.timedelta(days=t.weekday())).date() + datetime.timedelta(days=7)
    return f"{d.isoformat()} 00:00 UTC"


def full_suite(suite, user_rec):
    if suite == "full":
        return True
    if suite == "stage1_until_first_valid":
        return bool((user_rec or {}).get("first_valid"))
    return False


def admit_decision(led, a, t=None):
    """Pure: mutates `led` on admission; returns the result dict (with _nowrite when nothing changed)."""
    t = t or now()
    wk = week_of(t.isoformat())
    es = led.setdefault("entries", [])
    users = led.setdefault("users", {})
    full = full_suite(a.suite, users.get(a.user))
    base = {"week": wk, "full_suite": full, "user": a.user}
    mine = [e for e in es if e["submission"] == a.submission]
    if mine and a.rerun:
        mine[-1].update(status="reserved", updated=t.isoformat(), reruns=mine[-1].get("reruns", 0) + 1)
        return {**base, "admitted": True, "reason": "organiser re-run (no new slot)"}
    if mine and mine[-1]["status"] in COUNTED:
        return {**base, "admitted": False, "reason": "submission already in the ledger", "_nowrite": True}
    tree = getattr(a, "tree", None)
    if tree:
        # red team: resubmitting an unchanged harness draws DF's variance again and the best draw could be kept;
        # a submission/ tree identical to one already scored this season (anyone's) is refused, not counted
        same = [e for e in es if e.get("tree") == tree and e["status"] in SCORED and e["submission"] != a.submission]
        if same:
            whose = "your" if same[-1]["user"] == a.user else f"{same[-1]['user']}'s"
            return {**base, "admitted": False, "_nowrite": True,
                    "reason": f"submission/ is identical to {whose} submission {same[-1]['submission']}, already "
                              "scored this season; an unchanged harness isn't scored again (this attempt doesn't "
                              "count)"}
    if a.global_cap is not None:
        used_all = sum(1 for e in es if e["week"] == wk and e["status"] in COUNTED)
        if used_all >= a.global_cap:
            return {**base, "admitted": False, "_nowrite": True,
                    "reason": f"this week's global allowance ({a.global_cap} submissions) is used up; submit again "
                              f"after {next_week_start(t)} (this attempt doesn't count)"}
    own = [e for e in es if e["user"] == a.user]
    if sum(1 for e in own if e["status"] == "reserved") >= a.in_flight:
        return {**base, "admitted": False, "_nowrite": True,
                "reason": f"{a.user} already has {a.in_flight} submission(s) in flight; submit again when it finishes"}
    used = sum(1 for e in own if e["week"] == wk and e["status"] in COUNTED)
    if used >= a.weekly:
        return {**base, "admitted": False, "_nowrite": True,
                "reason": f"weekly limit reached for {a.user} ({used}/{a.weekly} in {wk}); submit again after "
                          f"{next_week_start(t)}"}
    es.append({"submission": a.submission, "user": a.user, "week": wk, "status": "reserved",
               "created": t.isoformat(), "updated": t.isoformat(), "run": a.run, "tree": tree})
    return {**base, "admitted": True, "reason": f"slot {used + 1}/{a.weekly} in {wk}"}


def cmd_admit(a):
    r = update("ledger.json", lambda led: admit_decision(led, a), f"admit {a.submission} ({a.user})",
               lambda: {"entries": [], "users": {}})
    r.pop("_nowrite", None)
    print(json.dumps(r))


def finish_decision(led, a, t=None):
    t = t or now()
    mine = [e for e in led.setdefault("entries", []) if e["submission"] == a.submission]
    if not mine:
        return {"ok": False, "reason": "not in the ledger", "_nowrite": True}
    e = mine[-1]
    e.update(status=a.status, updated=t.isoformat())
    for k in ("score", "stage", "run"):
        v = getattr(a, k)
        if v is not None:
            e[k] = v
    if a.status == "scored":
        u = led.setdefault("users", {}).setdefault(e["user"], {})
        u.setdefault("first_valid", {"submission": a.submission, "at": t.isoformat()})
    return {"ok": True}


def cmd_finish(a):
    r = update("ledger.json", lambda led: finish_decision(led, a), f"finish {a.submission}: {a.status}",
               lambda: {"entries": [], "users": {}})
    r.pop("_nowrite", None)
    print(json.dumps(r))


def cmd_leader_get(a):
    obj, _ = load("leader.json")
    print("" if not obj or obj.get(a.field) is None else obj[a.field])


def cmd_leader_set(a):
    def fn(obj):
        obj.clear()
        obj.update(stage1_point=a.stage1_point, submission=a.submission, score=a.score, note=a.note,
                   updated=now().isoformat())
        return {"ok": True}
    print(json.dumps(update("leader.json", fn, f"leader {a.submission}: stage-1 point {a.stage1_point}", dict)))


def cmd_show(a):
    led, _ = load("ledger.json")
    for e in (led or {"entries": []})["entries"]:
        if not a.user or e.get("user") == a.user:
            print(json.dumps(e, sort_keys=True))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    x = sp.add_parser("admit"); x.add_argument("--submission", required=True); x.add_argument("--user", required=True)
    x.add_argument("--in-flight", type=int, required=True); x.add_argument("--weekly", type=int, required=True)
    x.add_argument("--suite", required=True, choices=["full", "stage1", "stage1_until_first_valid"])
    x.add_argument("--global", dest="global_cap", type=int)
    x.add_argument("--rerun", action="store_true"); x.add_argument("--run")
    x.add_argument("--tree", help="git tree id of submission/ (refused if identical to one already scored)")
    x.set_defaults(f=cmd_admit)
    x = sp.add_parser("finish"); x.add_argument("--submission", required=True)
    x.add_argument("--status", required=True, choices=["scored", "infra_failed", "rejected", "cancelled"])
    x.add_argument("--score", type=float); x.add_argument("--stage"); x.add_argument("--run")
    x.set_defaults(f=cmd_finish)
    x = sp.add_parser("leader-get"); x.add_argument("--field", default="stage1_point", choices=["stage1_point", "score", "submission"])
    x.set_defaults(f=cmd_leader_get)
    x = sp.add_parser("leader-set"); x.add_argument("--stage1-point", type=float, required=True)
    x.add_argument("--submission", required=True); x.add_argument("--score", type=float); x.add_argument("--note")
    x.set_defaults(f=cmd_leader_set)
    x = sp.add_parser("show"); x.add_argument("--user"); x.set_defaults(f=cmd_show)
    a = p.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
