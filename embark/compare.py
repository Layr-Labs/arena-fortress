#!/usr/bin/env python3
"""Determinism check for two embark snapshots of the same (seed, rules): compare/report their SNAPSHOT.json.

  python3 embark/compare.py <snapA> <snapB>      exit 0 if every reproducible field matches

Reproducible (must match): the world tile and 4x4 rectangle, the start tick and citizen count, the world name, and
the fingerprints `map` (every tile's type, liquid and aquifer flags), `plants` (positions and species) and `loadout`
(the wagon's items by type, weapons apart).
Reported but allowed to differ (DF rolls them at embark from an RNG we can't seed): the fort name; `roster_core`
(professions + work skills: 6 of the 7 "Play now!" dwarves are fixed, the crafter slot varies, e.g. STONECRAFTER vs
METALCRAFTER); `roster` (adds performance skills from random personalities); `items` (spider webs, gear carried by
wildlife/cavern units); `loadout_weapons` (6-8 weapons of random kinds); world.sav's bytes.
"""
import hashlib, json, os, sys

STRICT_FP = ("map", "plants", "loadout")
LOOSE_FP = ("roster_core", "roster", "items")


def load(d):
    s = json.load(open(os.path.join(d, "SNAPSHOT.json")))
    e = s["embark"]
    p = e["probe"]
    sha = hashlib.sha256(open(os.path.join(d, "world.sav"), "rb").read()).hexdigest()[:12]
    return s, e, p, sha


def main(a, b):
    sa, ea, pa, ha = load(a)
    sb, eb, pb, hb = load(b)
    rows = [("world_tile", ea["world_tile"], eb["world_tile"], True), ("local", ea["local"], eb["local"], True),
            ("rect", pa["site"]["rect"], pb["site"]["rect"], True),
            ("abs_tick", sa["abs_tick"], sb["abs_tick"], True), ("citizens", sa["citizens"], sb["citizens"], True),
            ("world_name", sa["world_name"], sb["world_name"], True), ("fort_name", sa["fort_name"], sb["fort_name"], False)]
    rows += [("fp." + k, pa["fingerprint"].get(k), pb["fingerprint"].get(k), True) for k in STRICT_FP]
    rows += [("fp." + k, pa["fingerprint"].get(k), pb["fingerprint"].get(k), False) for k in LOOSE_FP]
    rows += [("loadout_weapons", pa.get("loadout_weapons"), pb.get("loadout_weapons"), False),
             ("world.sav", ha, hb, False)]
    bad = 0
    print(f"{a}  vs  {b}  (seed {ea['seed']}, {ea['rules']})")
    for name, x, y, strict in rows:
        same = x == y
        bad += strict and not same
        print(f"  {'ok  ' if same else ('DIFF' if strict else 'diff')} {name:16} {x}" + ("" if same else f"  |  {y}"))
    print("DETERMINISTIC" if not bad else f"NOT DETERMINISTIC: {bad} reproducible field(s) differ")
    return 0 if not bad else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
