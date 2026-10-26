#!/usr/bin/env python3
"""fort_compare.py A B : compare two task forts built from the same seed and recipe (embark/make_task_fort.sh), or a
task fort with the legacy snapshot it replaces (pass the legacy's fort_summary.lua JSON as B).

Must match between two builds of one (seed, recipe): the embark id (tile, rectangle, map / plants / loadout
fingerprints), the recipe and build-script hashes, the layout (what was built where) and every field the recipe's
`expect` pins to one value. Reported, allowed to differ: the citizens (DF picks the migrants; their number can differ
by one where a top-up wave lands), stress, food above the target, seeds held by planting jobs, the tick, world.sav."""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fort_check import get  # noqa: E402

FIELDS = ("pop.citizens", "pop.stressed", "pop.stress_mean", "stocks.drink", "stocks.food", "stocks.plants_brewable",
          "stocks.seeds", "stocks.logs_free", "stocks.barrels", "stocks.barrels_empty", "stocks.beds_free",
          "stocks.tables_free", "stocks.chairs_free", "buildings.workshops", "buildings.farm_plots_underground",
          "buildings.farm_plots_planted", "buildings.stockpiles", "orders.n", "nobles", "plugins",
          "events.migrants_pending", "events.reported_wealth", "map.dug_below_surface", "date.day")


def load(p):
    if os.path.isdir(p):
        s = json.load(open(os.path.join(p, "SNAPSHOT.json")))
        return s, s.get("task_fort", {}).get("summary") or {}
    d = json.load(open(p))
    return {}, d


def main(a, b):
    sa, xa = load(a)
    sb, xb = load(b)
    bad = 0
    if sa.get("embark") and sb.get("embark"):
        ea, eb = sa["embark"], sb["embark"]
        for k in ("seed", "world_tile", "local"):
            ok = ea[k] == eb[k]; bad += not ok
            print(f"{'ok  ' if ok else 'DIFF'} embark.{k}: {ea[k]} | {eb[k]}")
        for k in ("map", "plants", "loadout"):
            va, vb = ea["probe"]["fingerprint"][k], eb["probe"]["fingerprint"][k]
            ok = va == vb; bad += not ok
            print(f"{'ok  ' if ok else 'DIFF'} fp.{k}: {va} | {vb}")
    if sa.get("task_fort") and sb.get("task_fort"):
        ta, tb = sa["task_fort"], sb["task_fort"]
        for k in ("recipe", "recipe_sha256", "build_sha256", "layout"):
            ok = ta.get(k) == tb.get(k); bad += not ok
            print(f"{'ok  ' if ok else 'DIFF'} task_fort.{k}: {ta.get(k)} | {tb.get(k)}")
    for k in FIELDS:
        va, vb = get(xa, k), get(xb, k)
        print(f"{'same' if va == vb else '    '} {k}: {va} | {vb}")
    print("COMPARE", "OK" if not bad else f"{bad} id/layout difference(s)")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main(*sys.argv[1:3]) else 0)
