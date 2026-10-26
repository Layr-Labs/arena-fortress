#!/usr/bin/env python3
"""`credited_value_dr`: credited value with per-class diminishing returns (docs/BENCHMARK-v1.md §3.4, §7 Q7;
score_version 3).

Gross `credited_value` (credit.lua) counts every credited item at its full value, so a run that queues chairs
forever scores like one that runs a fort (fort-gym's "26 chairs for 13 dwarves"). This rescales it from saved
artifacts only: the `<arm>-<k>.credit.json` item log (`dump items`: id, ty, c, v, stack, credited), the summary
row (`citizen_days`, `pop_peak`) and, if those are missing, the daily samples. Items are taken in creation order
(item id); past its class cap an item counts at OVER (10%) of its value.

  class        items (credit.lua `ty` / `c`)                cap
  drink        ty DRINK                                     H · RATE_DRINK · citizen_days units (summed `stack`)
  food         c food (FOOD, FISH, CHEESE)                  H · RATE_FOOD · citizen_days units, one shared pool
  barrels      ty BARREL                                    drink items inside the drink cap + BARREL_EXTRA items
  artifact     c artifact                                   none (one per strange mood; not something to spam)
  durable      everything else, per item type `ty`          max(DURABLE_MIN, DURABLE_PER_CITIZEN · peak citizens)
               (furniture, bins, cages, clothing, tools, ...)

- An item that crosses a consumable cap is split pro rata by units.
- Raw goods (logs, plants, meat) are never credited by credit.lua, so they never reach this.
- Pots are TOOL items, which the item log doesn't tell apart from other tools: they take the durable TOOL cap.
- `citizen_days` is the run's total (one sample per game day, day 0 included), so for a finished run the
  consumable cap scales with how long and how big the fort was. The per-day reward (bench/reward.py) still uses
  the gross daily `credited_value` sample; the daily samples don't carry the item log.

  python3 bench/dr.py <run dir> [<run dir> ...]    # prints gross, DR and the caps per run (stdlib only)
"""
import glob, json, os, sys

OVER = 0.10                 # value fraction counted past a cap
H = 2.0                     # consumable headroom: twice what the fort uses
RATE_DRINK = 0.049          # units per citizen-day: noop's drink stock decline while drink > 0. Measured 0.0493 on
RATE_FOOD = 0.126           #   credited-2026-10-08 (refs 0) and re-measured 0.0488 / 0.1296 (food: gross decline)
                            #   on lambda-refs-2026-10-10 ref-start-year-336d noop, n = 20 (refs 1-2): unchanged
DURABLE_PER_CITIZEN = 2     # per item type: 2 per citizen at the run's peak ...
DURABLE_MIN = 10            # ... and never fewer than 10
BARREL_EXTRA = 10           # brewing fills one empty barrel per drink item; 10 more for food and storage
PARAMS = dict(OVER=OVER, H=H, RATE_DRINK=RATE_DRINK, RATE_FOOD=RATE_FOOD, DURABLE_PER_CITIZEN=DURABLE_PER_CITIZEN,
              DURABLE_MIN=DURABLE_MIN, BARREL_EXTRA=BARREL_EXTRA)
SUMMARY_CLASSES = ("drink", "food", "furniture", "other")   # bench/summarize_run.py's outcome classes


def _klass(it):
    if it.get("c") == "artifact":
        return "artifact"
    if it.get("ty") == "DRINK":
        return "drink"
    if it.get("c") == "food":
        return "food"
    if it.get("ty") == "BARREL":
        return "barrel"
    return "durable"


def credited_value_dr(items, citizen_days, peak_citizens):
    """items: credit.lua `dump items` entries (credited ones are used). -> dict with the DR value, the gross value,
    both by summary class, the caps and what each cap cut."""
    its = sorted((i for i in items if i.get("credited", True)), key=lambda i: i.get("id", 0))
    cd, peak = max(0, citizen_days or 0), max(0, peak_citizens or 0)
    cap_units = {"drink": H * RATE_DRINK * cd, "food": H * RATE_FOOD * cd}
    n_t = max(DURABLE_MIN, DURABLE_PER_CITIZEN * peak)
    used = {"drink": 0.0, "food": 0.0}
    drink_in_cap = 0
    for i in its:   # drink items that start inside the drink cap: one barrel each
        if _klass(i) == "drink":
            if used["drink"] < cap_units["drink"]:
                drink_in_cap += 1
            used["drink"] += i.get("stack") or 1
    cap_barrels = drink_in_cap + BARREL_EXTRA
    used = {"drink": 0.0, "food": 0.0}
    count = {}
    gross_c, dr_c, cut = {c: 0.0 for c in SUMMARY_CLASSES}, {c: 0.0 for c in SUMMARY_CLASSES}, {}
    for i in its:
        v, k = i.get("v") or 0, _klass(i)
        if k in ("drink", "food"):
            st = i.get("stack") or 1
            full = min(1.0, max(0.0, (cap_units[k] - used[k]) / st))
            used[k] += st
        elif k == "artifact":
            full = 1.0
        else:
            key = "BARREL" if k == "barrel" else i.get("ty") or "?"
            count[key] = count.get(key, 0) + 1
            full = 1.0 if count[key] <= (cap_barrels if k == "barrel" else n_t) else 0.0
        dv = v * (full + OVER * (1 - full))
        sc = i.get("c") if i.get("c") in SUMMARY_CLASSES else "other"
        gross_c[sc] += v
        dr_c[sc] += dv
        if full < 1:
            ck = k if k in ("drink", "food", "barrel") else i.get("ty") or "?"
            cut[ck] = cut.get(ck, 0.0) + (v - dv)
    r = lambda x: round(x, 1)
    return {"credited_value": r(sum(gross_c.values())), "credited_value_dr": r(sum(dr_c.values())),
            "by_class": {c: r(gross_c[c]) for c in SUMMARY_CLASSES},
            "by_class_dr": {c: r(dr_c[c]) for c in SUMMARY_CLASSES},
            "caps": {"drink_units": r(cap_units["drink"]), "food_units": r(cap_units["food"]),
                     "barrels": cap_barrels, "per_type": n_t},
            "units": {"drink": used["drink"], "food": used["food"]},
            "cut": {k: r(v) for k, v in sorted(cut.items(), key=lambda kv: -kv[1])},
            "citizen_days": cd, "peak_citizens": peak}


def _first(*paths):
    for p in paths:
        if p and os.path.exists(p):
            return p


def for_run(run_dir, row=None, exact=False):
    """DR for one run dir holding <arm>-<k>.credit.json (and summary.jsonl / .daily.json). row: its summary row,
    else the last non-crashed row of <run_dir>/summary.jsonl. None if there is no item log. exact: only
    <arm>-<k>.credit.json, never the first credit file in the dir (a dir with several runs)."""
    if row is None:
        p = os.path.join(run_dir, "summary.jsonl")
        rows = [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []
        rows = [x for x in rows if not x.get("crashed")]
        row = rows[-1] if rows else {}
    name = f"{row['arm']}-{row['k']}" if "arm" in row and "k" in row else None
    cf = _first(name and os.path.join(run_dir, name + ".credit.json"),
                *([] if exact else sorted(glob.glob(os.path.join(run_dir, "*.credit.json")))[:1]))
    if not cf:
        return None
    try:
        credit = json.load(open(cf))
    except (OSError, ValueError):
        return None
    if "items" not in credit:
        return None
    cd, peak = row.get("citizen_days"), row.get("pop_peak")
    if cd is None or peak is None:
        df_ = _first(cf[:-len(".credit.json")] + ".daily.json")
        samples = (json.load(open(df_)).get("samples") or []) if df_ else []
        cit = [s.get("citizens") or 0 for s in samples]
        if cd is None:
            cd = sum(cit)
        if peak is None:
            peak = max(cit + [row.get("pop_start") or 0])
    return credited_value_dr(credit["items"], cd, peak)


if __name__ == "__main__":
    for d in sys.argv[1:]:
        print(d, json.dumps(for_run(d)))
