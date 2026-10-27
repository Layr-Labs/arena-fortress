#!/usr/bin/env python3
"""runner/ci/bin/testers.py: put internal testers on a `tester` tier (RULES.md §7 limits don't fit a dry run).

tier.py reads two repo variables: DFBENCH_TIERS (JSON, merged over its DEFAULT_TIERS; new tier names allowed) and
DFBENCH_TIER_OVERRIDES ({github username: tier}). This adds or updates a `tester` tier (full suite from the first
submission, a higher weekly limit) and maps the given usernames to it, keeping every other entry as it is.

  testers.py add alice,bob [--weekly 10] [--in-flight 2]     prints the two variables' new JSON
  testers.py remove alice                                    drops overrides (the tier entry stays)
  ... --repo Layr-Labs/dfbench-challenge                     reads the current values with `gh variable get` and,
                                                             with --apply, writes them back with `gh variable set`

Usernames are GitHub logins, matched exactly as Yukon reports the submitter (tier.py `decide`).
"""
import argparse, json, re, subprocess, sys

LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
TIER = "tester"


def users(csv):
    out = [u.strip() for u in csv.split(",") if u.strip()]
    bad = [u for u in out if not LOGIN.match(u)]
    if bad or not out:
        raise SystemExit(f"not GitHub logins: {', '.join(bad) or '(none)'}")
    return out


def add(tiers, overrides, names, weekly=10, in_flight=2):
    tiers = dict(tiers)
    tiers[TIER] = {**tiers.get(TIER, {}), "in_flight": in_flight, "weekly": weekly, "suite": "full"}
    overrides = {**overrides, **{u: TIER for u in names}}
    return tiers, overrides


def remove(overrides, names):
    return {u: t for u, t in overrides.items() if u not in names}


def gh_get(repo, name):
    r = subprocess.run(["gh", "variable", "get", name, "-R", repo], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}


def gh_set(repo, name, value):
    subprocess.run(["gh", "variable", "set", name, "-R", repo, "-b", json.dumps(value, separators=(",", ":"))],
                   check=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["add", "remove"]); ap.add_argument("users")
    ap.add_argument("--weekly", type=int, default=10); ap.add_argument("--in-flight", type=int, default=2)
    ap.add_argument("--repo"); ap.add_argument("--apply", action="store_true")
    ap.add_argument("--tiers", default="{}", help="current DFBENCH_TIERS (without --repo)")
    ap.add_argument("--overrides", default="{}", help="current DFBENCH_TIER_OVERRIDES (without --repo)")
    a = ap.parse_args(argv)
    names = users(a.users)
    if a.apply and not a.repo:
        ap.error("--apply needs --repo")
    tiers = gh_get(a.repo, "DFBENCH_TIERS") if a.repo else json.loads(a.tiers)
    over = gh_get(a.repo, "DFBENCH_TIER_OVERRIDES") if a.repo else json.loads(a.overrides)
    if a.cmd == "add":
        tiers, over = add(tiers, over, names, a.weekly, a.in_flight)
    else:
        over = remove(over, names)
    print(json.dumps({"DFBENCH_TIERS": tiers, "DFBENCH_TIER_OVERRIDES": over}, indent=1))
    if a.apply:
        if a.cmd == "add":
            gh_set(a.repo, "DFBENCH_TIERS", tiers)
        gh_set(a.repo, "DFBENCH_TIER_OVERRIDES", over)


if __name__ == "__main__":
    main()
