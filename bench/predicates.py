#!/usr/bin/env python3
"""Lab-task success predicates and partial credit (BENCHMARK-v1 §2, score_version 2), from saved run artifacts only
(summary row + <arm>-<k>.daily.json with the recorder's samples, ev, moods, beds and S0/S), so any batch can be
rescored without rerunning (§3.7).

  python3 bench/predicates.py <task> <batch-dir>...      task: LT01 | LT02 | LT03 | LT04 | LT05 | LT08 | LT08-items | LT09
  prints per arm: pass c/n, per-clause pass counts, mean partial; then witness-vs-noop permutation p on partial.

Day d is sample d (sample 0 is taken at load, before the setup; one sample per 1200 ticks). A = active_days,
H = the last sample. Window W = (A, H].
LT01, LT02 and LT05 (v2, score_version 4) also read <arm>-<k>.credit.json (credited items; `tick` since v2) and
S.farm_plots[].planted. Score_version 5: Δdeaths is bench/outcomes.run_deaths (the larger of score.lua's count, the
recorder's citizen ledger and CITIZEN_DEATH announcements); LT02 is rescue_v2 and LT09 embark_production_v2, whose
credited clauses became "never out of supply over W". A clause whose input wasn't recorded (credit ticks in older runs) is None: shown, and left
out of pass.
"""
import glob, json, os, random, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bench.outcomes import run_deaths   # noqa: E402  score_version 5: deaths from the ledger / announcements too

TASKS = {"LT01": (39, 21), "LT02": (69, 21), "LT05": (23, 7), "LT09": (92, 28),
         "LT08": (39, 21), "LT08-items": (39, 21), "LT04": (31, 14), "LT03": (38, 7)}
DAY = 1200
INSANE = {"Melancholy", "Raving", "Berserk", "Traumatized"}   # df.mood_type insanities
BREAKDOWN = ("CITIZEN_TANTRUM", "CITIZEN_LOST_TO_STRESS", "BERSERK_CITIZEN")


def runs(dirs):
    """(summary row, daily dump) for every completed run under the batch dirs (<dir>/<arm>-<k>/ or flat)."""
    seen = set()
    for d in dirs:
        for s in sorted(glob.glob(os.path.join(d, "**", "summary.jsonl"), recursive=True)):
            rows = [json.loads(l) for l in open(s) if l.strip()]
            last = {}
            for r in rows:   # every (arm, k) in the file, last completed row each (flat smoke.py dirs hold several)
                if not r.get("crashed"):
                    last[(r["arm"], r["k"])] = r
            for (arm, k), r in sorted(last.items()):
                base = os.path.join(os.path.dirname(s), f"{arm}-{k}")
                key = (os.path.realpath(os.path.dirname(s)), arm, k)
                if key in seen or not os.path.exists(base + ".daily.json"):
                    continue
                seen.add(key)
                dd = json.load(open(base + ".daily.json"))
                if os.path.exists(base + ".credit.json"):
                    dd["_credit"] = json.load(open(base + ".credit.json"))
                yield r, dd


def lt08(r, dd, items=False):
    """migrant_surge_v1: Δdeaths 0; drink and food > 0 every day of W; D[H].drink >= D[A].drink; beds >= citizens
    at H. Beds are placed (installed) bed buildings; LT08-items (the fallback, a different task hash) counts bed items."""
    s = dd["samples"]
    A, _ = TASKS["LT08"]
    H = len(s) - 1
    W = s[A + 1:H + 1]
    deaths = run_deaths(r, dd)
    beds = s[H].get("beds_items" if items else "beds_placed", 0)
    cit = max(1, s[H]["citizens"])
    c = [deaths == 0, all(x["drink"] > 0 and x["food"] > 0 for x in W), s[H]["drink"] >= s[A]["drink"], beds >= cit]
    frac = sum(x["drink"] > 0 and x["food"] > 0 for x in W) / max(1, len(W))
    part = (min(1, beds / cit) + frac + min(1, s[H]["drink"] / max(1, s[A]["drink"])) + (deaths == 0)) / 4
    if s[H]["citizens"] == 0:
        c, part = [False] * 4, 0.0
    return c, part, {"beds": beds, "cit": s[H]["citizens"], "drink_A": s[A]["drink"], "drink_H": s[H]["drink"],
                     "pop_peak": max(x["citizens"] for x in s)}


def lt04(r, dd):
    """stress_relief_v1: no tantrum / lost-to-stress / berserk announcement after day 7; D[H].stressed <= 1;
    Δdeaths 0. Partial 0.5·clip(1 − D[H].stressed / D[0+].stressed) + 0.5·[clause 1]. D[0] here is the first sample
    after the setup (sample 1), since sample 0 is taken before stress.lua runs."""
    s = dd["samples"]
    H = len(s) - 1
    br = sum(sum((x.get("ev") or {}).get(t, 0) for t in BREAKDOWN) for x in s[8:H + 1])
    deaths = run_deaths(r, dd)
    st0 = max(1, s[1]["stressed"])
    c = [br == 0, s[H]["stressed"] <= 1, deaths == 0]
    part = 0.5 * max(0.0, min(1.0, 1 - s[H]["stressed"] / st0)) + 0.5 * (br == 0)
    if s[H]["citizens"] == 0:
        c, part = [False] * 3, 0.0
    return c, part, {"breakdowns_after_d7": br, "stressed_H": s[H]["stressed"], "stressed_1": s[1]["stressed"],
                     "deaths": deaths}


def lt03(r, dd):
    """mood_artifact_v1 (the mood dwarf = whoever is in a strange mood in sample 1, right after the setup; babies
    have mood Baby and are ignored): an artifact was made (S.num_artifacts > S0.num_artifacts, or a MADE_ARTIFACT
    announcement); the mood dwarf is alive, not in a mood at H, and never insane in a daily
    sample; Δdeaths 0. Partial 0.2·[claimed] + 0.3·[begun] + 0.5·[made], 0 if the dwarf went insane."""
    s = dd["samples"]
    S0, S = dd.get("S0") or {}, dd.get("S") or {}
    ev = {}
    for x in s:
        for t, n in (x.get("ev") or {}).items():
            ev[t] = ev.get(t, 0) + n
    made = (S.get("num_artifacts", 0) > S0.get("num_artifacts", 0)) or ev.get("MADE_ARTIFACT", 0) > 0
    ids = {m["unit_id"] for x in s[1:2] for m in x.get("moods") or [] if m["mood"] not in INSANE | {"Baby"}}
    insane = any(m["mood"] in INSANE and m["unit_id"] in ids for x in s for m in x.get("moods") or [])
    alive_ids0 = {c["id"] for c in S.get("citizens") or []}
    # an insanity between daily samples: the dwarf is "lost to stress" (leaves the citizen list) and DF counts it
    insane = insane or (S.get("total_insanities", 0) > S0.get("total_insanities", 0) and not ids <= alive_ids0)
    alive_ids = {c["id"] for c in S.get("citizens") or []}
    at_h = {m["unit_id"] for m in s[-1].get("moods") or [] if m["mood"] != "Baby"}
    sane_end = bool(ids) and all(i in alive_ids and i not in at_h for i in ids)
    deaths = run_deaths(r, dd)
    claimed = ev.get("MOOD_BUILDING_CLAIMED", 0) > 0
    begun = ev.get("ARTIFACT_BEGUN", 0) > 0
    c = [made, sane_end and not insane, deaths == 0]
    part = 0.0 if insane else 0.2 * claimed + 0.3 * begun + 0.5 * made
    return c, part, {"claimed": claimed, "begun": begun, "made": made, "insane": insane,
                     "artifacts": [S0.get("num_artifacts"), S.get("num_artifacts")], "deaths": deaths}


def _window(s, task):
    A, _ = TASKS[task]
    H = len(s) - 1
    return A, H, s[A + 1:H + 1]


def _credited_in_window(dd, A, ty):
    """Units (stack) of credited items of type `ty` made from day A on; None if the ledger has no ticks."""
    items = [x for x in (dd.get("_credit") or {}).get("items") or [] if x.get("credited")]
    if not dd.get("_credit") or any("tick" not in x for x in items):
        return None
    t_a = dd["samples"][0]["abs_tick"] + A * DAY
    return sum(x.get("stack") or 1 for x in items if x.get("ty") == ty and x["tick"] >= t_a)


def lt01(r, dd):
    """drought_v1: Δdeaths 0; drink > 0 every day of W; D[H].drink >= D[H].citizens; >= 5 credited drink made in W
    (one brew job: the throughput test). Partial 0.5·frac(W drink>0) + 0.25·min(1, D[H].drink / D[H].citizens) +
    0.25·min(1, drink_W / 5), minus 0.25 per death, floored at 0 (drink_W unknown counts 0)."""
    s = dd["samples"]
    A, H, W = _window(s, "LT01")
    deaths = run_deaths(r, dd)
    cit = max(1, s[H]["citizens"])
    dw = _credited_in_window(dd, A, "DRINK")
    c = [deaths == 0, all(x["drink"] > 0 for x in W), s[H]["drink"] >= s[H]["citizens"], None if dw is None else dw >= 5]
    frac = sum(x["drink"] > 0 for x in W) / max(1, len(W))
    part = max(0.0, 0.5 * frac + 0.25 * min(1, s[H]["drink"] / cit) + 0.25 * min(1, (dw or 0) / 5) - 0.25 * deaths)
    if s[H]["citizens"] == 0:
        c, part = [False] * 4, 0.0
    return c, part, {"drink_H": s[H]["drink"], "cit": s[H]["citizens"], "drink_made_in_W": dw, "deaths": deaths}


def lt02(r, dd):
    """rescue_v2 (score_version 5; v1's credited-value clause replaced by an outcome clause, docs/SUCCESS.md §4):
    Δdeaths 0; drink > 0 every day of W; a built Still and a built farm plot with seeds or crops in it (S); food > 0
    every day of W ("never out of supply over the window"). Partial 0.4·frac(W drink>0) + 0.3·frac(W food>0) +
    0.15·[Still] + 0.15·[farm planted]."""
    s = dd["samples"]
    A, H, W = _window(s, "LT02")
    S = dd.get("S") or {}
    deaths = run_deaths(r, dd)
    still = any(w.get("type") == "Still" and w.get("built") for w in S.get("workshops") or [])
    plots = S.get("farm_plots") or []
    farm = (any(p.get("built") and p.get("planted", 0) > 0 for p in plots) if any("planted" in p for p in plots)
            else None if plots else False)
    food_ok = all(x["food"] > 0 for x in W)
    c = [deaths == 0, all(x["drink"] > 0 for x in W), farm if still else False, food_ok]   # farm None: not recorded
    frac = sum(x["drink"] > 0 for x in W) / max(1, len(W))
    ffrac = sum(x["food"] > 0 for x in W) / max(1, len(W))
    part = 0.4 * frac + 0.3 * ffrac + 0.15 * still + 0.15 * bool(farm)
    if s[H]["citizens"] == 0:
        c, part = [False] * 4, 0.0
    return c, part, {"credited": r.get("credited_value_final"), "still": still, "farm_planted": farm,
                     "food_days_W": ffrac, "deaths": deaths}


def lt09(r, dd):
    """embark_production_v2 (score_version 5; the spec's credited-in-W clause replaced by supply over W, docs/SUCCESS.md
    §4): Δdeaths 0; drink > 0 and food > 0 every day of W; D[H].drink >= 2·D[H].citizens; S has a built Still,
    Kitchen and Carpenters and >= 2 built, planted farm plots. Partial 0.5·frac(W drink>0 ∧ food>0) +
    0.25·min(1, D[H].drink / (2·D[H].citizens)) + 0.25·(share of the 4 setup items: Still, Kitchen, Carpenters,
    2 planted plots), 0 if the fort is lost."""
    s = dd["samples"]
    A, H, W = _window(s, "LT09")
    S = dd.get("S") or {}
    deaths = run_deaths(r, dd)
    cit = max(1, s[H]["citizens"])
    built = {w.get("type") for w in S.get("workshops") or [] if w.get("built")}
    plots = S.get("farm_plots") or []
    planted = sum(1 for p in plots if p.get("built") and (p.get("planted", 0) > 0 if "planted" in p else True))
    setup = [t in built for t in ("Still", "Kitchen", "Carpenters")] + [planted >= 2]
    sup = [x["drink"] > 0 and x["food"] > 0 for x in W]
    c = [deaths == 0, all(sup), s[H]["drink"] >= 2 * s[H]["citizens"], all(setup)]
    part = 0.5 * sum(sup) / max(1, len(sup)) + 0.25 * min(1, s[H]["drink"] / (2 * cit)) + 0.25 * sum(setup) / 4
    if s[H]["citizens"] == 0:
        c, part = [False] * 4, 0.0
    return c, part, {"drink_H": s[H]["drink"], "cit": s[H]["citizens"], "setup": setup, "deaths": deaths}


def lt05(r, dd):
    """goblin_raid_v2: Δdeaths 0; no invader alive on the map at H (dead or gone); no visible hostile on any day of
    W. Partial (citizen survival only, as the goal says) 0.5·max(0, 1 − Δdeaths/3) + 0.5·max(0, 1 − Δdeaths/C0)."""
    s = dd["samples"]
    A, H, W = _window(s, "LT05")
    deaths = run_deaths(r, dd)
    alive = r.get("invaders_alive_final")
    c = [deaths == 0, None if alive is None else alive == 0, all(x.get("hostiles", 0) == 0 for x in W)]
    c0 = max(1, r.get("pop_start") or s[0]["citizens"])
    part = 0.5 * max(0, 1 - deaths / 3) + 0.5 * max(0, 1 - deaths / c0)
    if s[H]["citizens"] == 0:
        c, part = [False] * 3, 0.0
    return c, part, {"deaths": deaths, "invaders_alive_H": alive, "hostile_days_W": sum(x.get("hostiles", 0) > 0 for x in W)}


def perm_p(a, b, n=10000, seed=1):
    """Two-sided permutation p for the difference in means."""
    if not a or not b:
        return None
    rng = random.Random(seed)
    obs = abs(sum(a) / len(a) - sum(b) / len(b))
    pool, hits = a + b, 0
    for _ in range(n):
        rng.shuffle(pool)
        x, y = pool[:len(a)], pool[len(a):]
        hits += abs(sum(x) / len(x) - sum(y) / len(y)) >= obs - 1e-12
    return (hits + 1) / (n + 1)


def score(task, dirs):
    fn = {"LT01": lt01, "LT02": lt02, "LT05": lt05, "LT09": lt09, "LT08": lt08, "LT08-items": lambda r, d: lt08(r, d, items=True),
          "LT04": lt04, "LT03": lt03}[task]
    out = {}
    for r, dd in runs(dirs):
        c, part, info = fn(r, dd)
        out.setdefault(r["arm"], []).append({"k": r["k"], "pass": all(x for x in c if x is not None), "clauses": c,
                                             "partial": round(part, 3), **info})
    return out


def main():
    task, dirs = sys.argv[1], sys.argv[2:]
    out = score(task, dirs)
    for arm in ("noop", "random", "scripted", "automation", "witness", *sorted(set(out) - {"noop", "random", "scripted", "automation", "witness"})):
        v = out.get(arm)
        if not v:
            continue
        v.sort(key=lambda x: x["k"])
        print(f"{task} {arm:10s} pass {sum(x['pass'] for x in v)}/{len(v)}  clauses "
              f"{[sum(bool(x['clauses'][i]) for x in v) for i in range(len(v[0]['clauses']))]}  partial mean "
              f"{sum(x['partial'] for x in v) / len(v):.2f}  {[x['partial'] for x in v]}")
        for x in v:
            print("   ", {k: x[k] for k in x if k not in ("clauses",)})
    if "witness" in out and "noop" in out:
        p = perm_p([x["partial"] for x in out["witness"]], [x["partial"] for x in out["noop"]])
        print(f"{task} witness vs noop partial: permutation p = {p:.4f}")


if __name__ == "__main__":
    main()
