#!/usr/bin/env python3
"""fort_check.py SUMMARY.json RECIPE.json : check a built task fort (embark/fort_summary.lua output) against its
recipe's `expect` ranges. Keys are dotted paths into the summary; a value is [lo, hi] (inclusive), or an exact
list/dict (e.g. the enabled plugins). Prints one line per check and exits 1 if any fails."""
import json, sys


def get(d, path):
    for k in path.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(k, 0 if k[:1].isupper() else None)   # a workshop type that isn't there counts 0
    return d


def check(summary, expect):
    bad = []
    for k, want in expect.items():
        have = get(summary, k)
        if isinstance(want, list) and len(want) == 2 and all(isinstance(x, (int, float)) for x in want):
            ok = isinstance(have, (int, float)) and want[0] <= have <= want[1]
        else:
            # DFHack's json encodes an empty table as [], so an empty dict and an empty list are the same here
            norm = lambda v: {} if v in ([], {}, None) else (sorted(v) if isinstance(v, list) else v)
            ok = norm(have) == norm(want)
        print(f"{'ok  ' if ok else 'FAIL'} {k}: {have!r} (want {want!r})")
        if not ok:
            bad.append(k)
    return bad


if __name__ == "__main__":
    s, r = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
    bad = check(s, r.get("expect", {}))
    print("CHECK", "OK" if not bad else "FAIL " + ",".join(bad))
    sys.exit(1 if bad else 0)
