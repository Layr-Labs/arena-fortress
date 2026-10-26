#!/usr/bin/env python3
"""pool_task.py: a seed-built lab task (scenarios/seed/*.json) on another split's fort pool.

  python3 embark/pool_task.py scenarios/seed/lt01-drought.json --split train --seeds 1000,1002,1003,1004 --out X.json
  python3 embark/pool_task.py scenarios/seed/lt01-drought.json --split test-private --seeds 9001,9004,... \\
      --snapshots /srv/dfbench/s0/pool --out /srv/dfbench/s0/tasks/lt01.json        # verifier only, never in a repo

The task's `fort` block says which recipe builds its forts and which seed range each split draws from. The output is
the same task with `split`, `name` (suffixed -train / -private) and `snapshot_pool` (fort-<recipe>-<seed> under
--snapshots) set, so smoke.py / bench/labrun.py run it unchanged; build the forts first with docker/task_forts.sh.
Seeds outside the split's range are refused. bench/key.py then gives the variant its own task hash (it hashes the
JSON and each pool member's embark id + recipe + build-script hashes)."""
import argparse, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUFFIX = {"train": "-train", "test-public": "", "test-private": "-private"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("--split", required=True, choices=sorted(SUFFIX))
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--snapshots", default="scenarios/snapshots")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sc = json.load(open(a.task))
    fort = sc["fort"]
    lo, hi = fort["seeds"][a.split]
    seeds = [int(s) for s in a.seeds.split(",") if s.strip()]
    bad = [s for s in seeds if not lo <= s <= hi]
    if bad:
        sys.exit(f"seeds {bad} are outside {a.split}'s range [{lo}, {hi}]")
    recipe = json.load(open(os.path.join(ROOT, fort["recipe"])))["name"]
    base = sc["name"][: -len("-seed")] if sc["name"].endswith("-seed") else sc["name"]
    sc["name"] = base + "-seed" + SUFFIX[a.split]
    sc["split"] = a.split
    sc["snapshot_pool"] = [os.path.join(a.snapshots, f"fort-{recipe}-{s}") for s in seeds]
    sc["fort"] = dict(fort, pool={a.split: seeds})
    if a.split == "test-private" and os.path.realpath(a.out).startswith(ROOT):
        sys.exit("refusing to write a test-private task inside the repo")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(sc, f, indent=1)
        f.write("\n")
    print(f"{a.out}: {sc['name']} split={a.split} pool={sc['snapshot_pool']}")


if __name__ == "__main__":
    main()
