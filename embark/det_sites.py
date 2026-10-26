#!/usr/bin/env python3
"""Per-tick RNG draws by call site, compared across replays (research/determinism.md).

  python3 embark/det_sites.py SITE_DIR...      (det_check.sh site phase: site-r<k>/pause-*.jsonl from det_shim.c)

Each pause dump holds cumulative draws per caller address at a game tick. Per replay, per-tick deltas per site; prints
the first tick at which any site's delta differs between replays, and the sites that differ there and in the next ticks.
"""
import glob, json, os, sys
from collections import defaultdict


def load(d):
    """{abs_tick: {pc: cumulative}} keeping the last dump at each tick."""
    by = {}
    for f in sorted(glob.glob(os.path.join(d, "pause-*.jsonl"))):
        rows = [json.loads(l) for l in open(f)]
        by[rows[0]["abs_tick"]] = {r["pc"]: r["n"] for r in rows[1:]}
    return by


def deltas(by):
    ticks = sorted(by)
    out = {}
    for a, b in zip(ticks, ticks[1:]):
        if b == a + 1:
            out[b] = {pc: by[b].get(pc, 0) - by[a].get(pc, 0) for pc in set(by[a]) | set(by[b])}
    return out


def main(dirs):
    reps = [deltas(load(d)) for d in dirs]
    common = sorted(set.intersection(*[set(r) for r in reps]))
    shown = 0
    for t in common:
        pcs = set().union(*[set(r[t]) for r in reps])
        diff = {pc: [r[t].get(pc, 0) for r in reps] for pc in pcs if len({r[t].get(pc, 0) for r in reps}) > 1}
        if diff:
            same = {pc: reps[0][t].get(pc, 0) for pc in pcs if pc not in diff and reps[0][t].get(pc, 0)}
            print(f"tick {t}: {len(diff)} site(s) differ; draws per replay: "
                  + "; ".join(f"{pc}={v}" for pc, v in sorted(diff.items(), key=lambda kv: -max(kv[1]))[:12]))
            print(f"   ({len(same)} other sites drew identically this tick)")
            shown += 1
            if shown >= 4:
                break
    if not shown:
        print("no per-site differences in", len(common), "common ticks")


if __name__ == "__main__":
    main(sys.argv[1:])
