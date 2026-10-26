#!/usr/bin/env python3
"""Gated outcome score (docs/SUCCESS.md): did the fort survive, keep itself supplied, keep its dwarves sane, and
house and grow its population? From saved artifacts only (summary row, <arm>-<k>.daily.json, <arm>-<k>.final.json,
the scenario JSON), so any batch can be rescored without rerunning. stdlib only.

Four tiers, each a sub-score in [0, 1]. A tier counts only as far as every tier below it holds (a soft gate):

  O = 100 · (s1 + s1·s2 + s1·s2·s3 + s1·s2·s3·s4) / 4

  s1 survival   0 if the fort is lost (no citizens at H). Else 0.5·max(0, 1 − X/3) + 0.5·max(0, 1 − X/C0), with
                X = citizen deaths during the run (run_deaths: net of the snapshot's dead, the larger of score.lua,
                the citizen ledger and CITIZEN_DEATH announcements) + citizens lost to insanity, C0 =
                citizens at the start. Times the security factor: 1 with no threat, or a threat that is over at H
                (no live invaders on the map); 0.5 while raiders are still on the map at H.
  s2 supply     min over drink and food of 0.5·coverage + 0.5·min(1, T / T_STAR). coverage = share of the final
                stretch F with the stock > 0. T = days the stock at H lasts at the net decline rate over F
                (stock_H / decline, decline = minus the least-squares slope of the daily stock over F, the day
                before F included; infinite if the stock is not falling). F is the hands-off
                window when the task has one, else the last quarter of the run (7-28 days).
  s3 wellbeing  w_stress · w_events, where w_stress = 1 − mean over F of (stressed / citizens) (stressed = DFHack
                stress category <= 1), averaged 50/50 with the share of needs met at H when the recorder has needs;
                w_events = max(0, 1 − E / max(3, C̄/10)), E = tantrums + berserks + lost-to-stress + possessed
                tantrums + citizens seen in an insane mood (failed strange moods, stress insanity), C̄ = mean citizens.
  s4 growth     housing = mean(min(1, placed beds / citizens), min(1, 2 · dining seats / citizens)) at H. On
                horizons >= 336 d, 0.5·housing + 0.5·progression, progression = min(1, steps / 2): each fortress
                rank gained or new land-holder title counts 1 if exports meet its threshold, else 0.5; a new
                mayor and the monarch's arrival count 1 (progression_steps).

Gates (the `tier` reached, 0-4: the number of consecutive gates passed):
  G1 nobody died or went insane, the fort stands, and no raider is left on the map
  G2 drink and food in stock every day of F, and T >= T_STAR for both
  G3 no breakdown event or failed mood, and at most 10% of citizen-days in F stressed
  G4 placed beds >= citizens and dining seats >= citizens / 2 at H (and a progression step on >= 336 d horizons)

  python3 bench/outcomes.py <run dir | batch dir> [...]          # one line per run
  python3 bench/outcomes.py <dirs> --json                        # the full breakdown per run
Also reported, not scored: the hand-off liabilities at H (`handoff`, final_state.lua) and the citizen deaths by
source (`death_sources`: score.lua, the ledger, CITIZEN_DEATH announcements, world history), flagged when they
disagree.

  python3 bench/outcomes.py <dirs> --groups                      # mean O and tier counts per (batch, scenario, arm)
"""
import glob, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAY = 1200
OUTCOME_VERSION = 1
T_STAR = 336           # days of supply past H that count as sustained: one DF year (12 months of 28 days)
STRESSED_OK = 0.10     # G3: at most this share of citizen-days in F stressed
BREAKDOWN = ("CITIZEN_TANTRUM", "BERSERK_CITIZEN", "CITIZEN_LOST_TO_STRESS", "POSSESSED_TANTRUM")
INSANE = {"Melancholy", "Raving", "Berserk", "Traumatized"}
PROG_CAP = 2           # progression steps for full credit (year-plus horizons only)
# export thresholds (wiki Fortress / Noble, normal economy; hard economy is x5): fortress_rank 1..5 = Hamlet ..
# Metropolis, and the land-holder titles. A step reached without them counts half (created-wealth route).
RANK_EXPORT = {1: 500, 2: 2500, 3: 10000, 4: 20000, 5: 30000}
LAND_EXPORT = {"BARON": 10000, "BARONESS": 10000, "COUNT": 20000, "COUNTESS": 20000, "DUKE": 30000, "DUCHESS": 30000}
RUN_DIR = re.compile(r"^[A-Za-z0-9_]+-\d+$")


def _json(p, default=None):
    try:
        return json.load(open(p)) if p and os.path.exists(p) else default
    except ValueError:
        return default


_SCEN = None


def scenario(name):
    """The scenario JSON whose name (or file stem) is `name`, or {}."""
    global _SCEN
    if _SCEN is None:
        _SCEN = {}
        for p in glob.glob(os.path.join(ROOT, "scenarios", "**", "*.json"), recursive=True):
            sc = _json(p, {}) or {}
            if isinstance(sc, dict):
                _SCEN.setdefault(sc.get("name") or os.path.splitext(os.path.basename(p))[0], sc)
    return _SCEN.get(name or "", {})


def _events(daily, row):
    """Announcement counts over the run: the recorder's per-day `ev` if present, else the summary's `events`."""
    tot, have = {}, False
    for s in daily.get("samples") or []:
        for t, n in (s.get("ev") or {}).items():
            tot[t] = tot.get(t, 0) + n
            have = True
    if not have:
        ev = row.get("events") or (daily.get("events") if isinstance(daily.get("events"), dict) else {}) or {}
        tot = {t: (v.get("n", 0) if isinstance(v, dict) else v) for t, v in ev.items()}
    return tot


def _clip(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def progression_steps(p0, p):
    """DF progression gained over the run, weighted toward trade (docs/SUCCESS.md §2.2). Each fortress rank gained
    and each new land-holder title held by a citizen counts 1 if the fort's exported wealth at H meets that step's
    export threshold, else 0.5 (it was reached on created wealth, which furniture spam and felled logs inflate).
    A new mayor (elected at 50 citizens) and the monarch's arrival count 1. Thresholds: normal economy defaults."""
    exported = p.get("exported") or 0
    steps = 0.0
    for r in range((p0.get("fortress_rank") or 0) + 1, (p.get("fortress_rank") or 0) + 1):
        steps += 1.0 if exported >= RANK_EXPORT.get(r, float("inf")) else 0.5
    new = set(p.get("positions") or []) - set(p0.get("positions") or [])
    for pos in new:
        if pos in LAND_EXPORT:
            steps += 1.0 if exported >= LAND_EXPORT[pos] else 0.5
        elif pos == "MAYOR":
            steps += 1.0
    if p.get("king_arrived") and not p0.get("king_arrived"):
        steps += 1.0
    return steps


def death_sources(row, daily, final=None):
    """Citizen deaths during the run by source: `score` (score.lua's incident count, F − F0), `ledger` (recorder
    cit_log gone = died), `announced` (CITIZEN_DEATH in the per-day ev) and `history` (world-history
    HIST_FIGURE_DIED events at the site whose victim is a ledger citizen). None where the run predates a source."""
    final = final or {}
    d = row.get("citizen_deaths")
    if d is None and final.get("F") and final.get("F0"):
        d = (final["F"].get("citizen_deaths") or 0) - (final["F0"].get("citizen_deaths") or 0)
    log = daily.get("cit_log")
    samples = daily.get("samples") or []
    hd = daily.get("hist_deaths")
    return {"score": d,
            "ledger": None if log is None else sum(1 for e in log if e.get("gone") == "died"),
            "announced": sum((s.get("ev") or {}).get("CITIZEN_DEATH", 0) for s in samples)
            if any("ev" in s for s in samples) else None,
            "history": len(hd) if isinstance(hd, list) else None}


def run_deaths(row, daily, final=None):
    """Citizen deaths during the run (score_version 5): the largest of death_sources(). score.lua's count misses
    e.g. a berserk dwarf that is killed after leaving the fort's group (LT04 noop, in game 2026-10-13)."""
    return max([v for v in death_sources(row, daily, final).values() if v is not None] or [0])


def score_run(row, daily, final=None, sc=None):
    """-> dict: O, tier, s1..s4, gates and the inputs, or None if the run has no daily samples."""
    final = final or {}
    samples = [s for s in daily.get("samples") or [] if "abs_tick" in s]
    if not samples:
        return None
    sc = sc if sc is not None else scenario(row.get("scenario"))
    t0 = samples[0]["abs_tick"]
    day = lambda s: (s["abs_tick"] - t0) // DAY
    H = day(samples[-1])
    last = samples[-1]
    cit_H = last.get("citizens") or 0
    C0 = row.get("pop_start") or samples[0].get("citizens") or 0
    mean_cit = sum(s.get("citizens", 0) for s in samples) / len(samples)
    inputs = {"days": H, "citizens_start": C0, "citizens_end": cit_H}
    missing = []

    # ---- final stretch F: the hands-off window if the task has one, else the last quarter (7-28 d)
    A = row.get("hands_off_from_day")
    if A is None and sc.get("hands_off_days"):
        A = (sc.get("days") or H) - sc["hands_off_days"]
    if A is None or A >= H:
        A = H - int(_clip(round(H / 4), 7, 28))
    A = max(0, A)
    F = [s for s in samples if A < day(s) <= H]
    sA = max((s for s in samples if day(s) <= A), key=day, default=samples[0])
    inputs["final_stretch"] = [A, H]

    # ---- s1 survival (+ security)
    dsrc = death_sources(row, daily, final)
    deaths = max([v for v in dsrc.values() if v is not None] or [0])
    known = {v for v in dsrc.values() if v is not None}
    log = daily.get("cit_log")
    if log is not None:
        insane_lost = sum(1 for e in log if e.get("gone") == "insane")
        arrived = sum(1 for e in log if e.get("kind") == "migrant")
        born = sum(1 for e in log if e.get("kind") == "born")
    else:
        insane_lost, arrived, born = 0, None, None
        missing.append("cit_log")
    # an insane citizen who later dies is in both counts (older ledgers keep it as 'insane'): count each loss once
    X = max(deaths, sum(1 for e in log if e.get("gone") in ("died", "insane"))) if log is not None else deaths
    lost = cit_H == 0
    s_surv = 0.0 if lost else 0.5 * max(0.0, 1 - X / 3) + 0.5 * max(0.0, 1 - X / max(1, C0))
    F0, Ff = final.get("F0") or {}, final.get("F") or {}
    ev = _events(daily, row)
    inv_killed = (Ff.get("invaders_killed") or 0) - (F0.get("invaders_killed") or 0) if Ff else (row.get("invaders_killed") or 0)
    inv_alive = row.get("invaders_alive_final")
    if inv_alive is None:
        inv_alive = Ff.get("invaders_alive") or 0
    ambush = sum(n for t, n in ev.items() if t.startswith("AMBUSH_") or t in ("NIGHT_ATTACK_STARTS", "UNDEAD_ATTACK"))
    inv_new = 0
    S0p, Sp = ((daily.get("S0") or {}).get("prog") or {}), ((daily.get("S") or {}).get("prog") or {})
    if Sp.get("invasions") and S0p.get("invasions"):
        inv_new = Sp["invasions"]["n"] - S0p["invasions"]["n"]
    threat = inv_killed > 0 or (inv_alive or 0) > 0 or ambush > 0 or inv_new > 0 or bool(row.get("scenario_setup") and
                                                                                         "INVADERS" in str(row.get("scenario_setup")))
    s_sec = 1.0 if not threat or not inv_alive else 0.5
    s1 = s_surv * s_sec
    g1 = X == 0 and not lost and not inv_alive
    inputs.update(deaths=deaths, death_sources=dsrc, deaths_disagree=len(known) > 1, insane_lost=insane_lost, fort_lost=lost, threat=threat, invaders_killed=inv_killed,
                  invaders_alive_end=inv_alive, migrants=arrived, born=born)

    # ---- s2 supply: coverage over F and the projected days the stock lasts past H
    sup = {}
    for x in ("drink", "food"):
        cov = sum(1 for s in F if (s.get(x) or 0) > 0) / max(1, len(F))
        xA, xH = sA.get(x) or 0, last.get(x) or 0
        pts = [(day(s), s.get(x) or 0) for s in [sA] + F]
        mx, my = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        vx = sum((p[0] - mx) ** 2 for p in pts)
        decline = -sum((p[0] - mx) * (p[1] - my) for p in pts) / vx if vx else 0.0   # least-squares slope over F
        T = float("inf") if decline <= 0 and xH > 0 else (0.0 if xH <= 0 else xH / decline)
        sup[x] = {"coverage": round(cov, 3), "stock_A": xA, "stock_H": xH, "days_left": None if T == float("inf") else round(T, 1),
                  "per_citizen_H": round(xH / max(1, cit_H), 2),
                  "score": round(0.5 * cov + 0.5 * min(1.0, T / T_STAR), 3)}
    s2 = min(sup["drink"]["score"], sup["food"]["score"])
    g2 = all(sup[x]["coverage"] == 1 and (sup[x]["days_left"] is None or sup[x]["days_left"] >= T_STAR) for x in sup)

    # ---- s3 wellbeing
    fs = [s for s in F if s.get("citizens")]
    stressed_share = sum(s.get("stressed", 0) / s["citizens"] for s in fs) / max(1, len(fs))
    w_stress = 1 - stressed_share
    needs = ((daily.get("S") or {}).get("wb") or {}).get("needs") or (last.get("wb") or {}).get("needs")
    needs_met = None
    if needs and needs.get("n"):
        needs_met = 1 - needs["unmet"] / needs["n"]
        w_calm = 0.5 * w_stress + 0.5 * needs_met
    else:
        w_calm = w_stress
        missing.append("needs")
    brk = sum(ev.get(t, 0) for t in BREAKDOWN)
    mood_units = {}
    for s in samples:
        for m in s.get("moods") or []:
            mood_units.setdefault(m["unit_id"], set()).add(m["mood"])
    insane_units = sum(1 for ms in mood_units.values() if ms & INSANE)   # failed strange moods and stress insanity
    E = brk + insane_units
    w_events = max(0.0, 1 - E / max(3.0, mean_cit / 10))
    s3 = w_calm * w_events
    g3 = E == 0 and stressed_share <= STRESSED_OK
    inputs.update(stressed_share_F=round(stressed_share, 3), needs_met=None if needs_met is None else round(needs_met, 3),
                  breakdowns=brk, insane_units=insane_units, strange_moods=ev.get("STRANGE_MOOD", 0),
                  artifacts=ev.get("MADE_ARTIFACT", 0))

    # ---- s4 growth / progression
    home = last.get("home") or ((daily.get("S") or {}).get("home"))
    beds = (home or {}).get("beds_placed", last.get("beds_placed"))
    if beds is None:
        beds = (((daily.get("S") or {}).get("furniture") or {}).get("BED") or {}).get("built")
    seats = (home or {}).get("dining_seats")
    if seats is None and (daily.get("S") or {}).get("zones") is not None:
        seats = sum(min(z.get("contains", {}).get("TABLE", 0), z.get("contains", {}).get("CHAIR", 0))
                    for z in daily["S"]["zones"] if z.get("type") == "DiningHall")
    if beds is None:
        missing.append("beds")
    if seats is None:
        missing.append("dining")
    beds_pc = min(1.0, (beds or 0) / max(1, cit_H))
    dine_pc = min(1.0, 2 * (seats or 0) / max(1, cit_H))
    housing = (beds_pc + dine_pc) / 2
    prog_steps = progression_steps(S0p, Sp) if Sp and S0p else None
    long_h = H >= 336
    if long_h:
        if prog_steps is None:
            missing.append("progression")
        s4 = 0.5 * housing + 0.5 * min(1.0, (prog_steps or 0) / PROG_CAP)
    else:
        s4 = housing
    g4 = (beds or 0) >= cit_H and 2 * (seats or 0) >= cit_H and (not long_h or (prog_steps or 0) > 0)
    inputs.update(beds_placed=beds, dining_seats=seats, progression_steps=prog_steps,
                  bedrooms_owned=(home or {}).get("bedrooms_owned"),
                  fortress_rank=Sp.get("fortress_rank"), positions=Sp.get("positions"),
                  wealth_created=Sp.get("wealth_created"), exported=Sp.get("exported"))

    # hand-off liabilities at H (report-only, not in O): final_state's `handoff` block, the recorder's S
    handoff = (daily.get("S") or {}).get("handoff")
    O = 100 * (s1 + s1 * s2 + s1 * s2 * s3 + s1 * s2 * s3 * s4) / 4
    gates = [g1, g2, g3, g4]
    tier = next((i for i, g in enumerate(gates) if not g), 4)
    r = lambda v: round(v, 3)
    return {"outcome": round(O, 1), "tier": tier, "gates": gates,
            "s": {"survival": r(s1), "supply": r(s2), "wellbeing": r(s3), "growth": r(s4)},
            "parts": {"s_surv": r(s_surv), "s_sec": s_sec, "supply": sup, "w_stress": r(w_stress), "w_calm": r(w_calm),
                      "w_events": r(w_events), "beds_pc": r(beds_pc), "dining_pc": r(dine_pc), "housing": r(housing)},
            "inputs": inputs, "handoff": handoff, "missing": missing, "outcome_version": OUTCOME_VERSION}


def for_run(run_dir, row=None, exact=False):
    """Outcome for one run dir holding <arm>-<k>.daily.json (and summary.jsonl / .final.json)."""
    if row is None:
        p = os.path.join(run_dir, "summary.jsonl")
        rows = [json.loads(l) for l in open(p) if l.strip()] if os.path.exists(p) else []
        rows = [x for x in rows if not x.get("crashed")]
        if not rows:
            return None
        row = rows[-1]
    stem = os.path.join(run_dir, f"{row['arm']}-{row['k']}")
    daily = _json(stem + ".daily.json")
    if daily is None:
        return None
    return score_run(row, daily, _json(stem + ".final.json", {}) or {})


def discover(roots):
    """-> {(batch, scenario, arm): [(row, run_dir)]}: the last non-crashed row per (batch, arm, k)."""
    last = {}
    for root in roots:
        for p in sorted(glob.glob(os.path.join(root, "**", "summary.jsonl"), recursive=True)):
            d = os.path.dirname(p)
            batch = os.path.dirname(d) if RUN_DIR.match(os.path.basename(d)) else d
            for line in open(p):
                if not line.strip():
                    continue
                r = json.loads(line)
                if "arm" not in r or "k" not in r or r.get("crashed"):
                    continue
                last[(batch, r["arm"], r["k"])] = (r, d)
    groups = {}
    for (batch, arm, k), (r, d) in sorted(last.items()):
        groups.setdefault((batch, r.get("scenario") or "start-year", arm), []).append((r, d))
    return groups


HANDOFF_KEYS = ("unburied_dead", "ghosts", "stranded", "wounded_no_hospital", "moods_missing_items", "hostiles")


def handoff_line(o):
    """'hand-off: 3 liabilities (unburied dead 3, ghosts 2)', or None when the run has no handoff block."""
    h = o.get("handoff")
    if not h:
        return None
    parts = [f"{k.replace('_', ' ')} {h[k]}" for k in HANDOFF_KEYS if h.get(k)]
    return (f"hand-off: {h.get('total', 0)} liabilities" + (f" ({', '.join(parts)})" if parts else "")
            + (f"; wounded {h['wounded']}, hospitals {h['hospitals']}" if h.get("wounded") else ""))


def line(o):
    s = o["s"]
    return (f"outcome {o['outcome']:.1f} (tier {o['tier']}/4; survival {s['survival']:.2f}, supply {s['supply']:.2f}, "
            f"wellbeing {s['wellbeing']:.2f}, growth {s['growth']:.2f})"
            + (f" [no {', '.join(o['missing'])}]" if o["missing"] else "")
            + (f"; deaths by source {o['inputs']['death_sources']} DISAGREE" if o["inputs"].get("deaths_disagree") else ""))


def main(argv):
    as_json, grouped = "--json" in argv, "--groups" in argv
    dirs = [a for a in argv if not a.startswith("--")]
    groups = discover(dirs)
    out = []
    for (batch, scen, arm), rows in groups.items():
        os_ = []
        for r, d in rows:
            o = for_run(d, r)
            if o is None:
                continue
            os_.append(o)
            if not grouped:
                if as_json:
                    out.append({"batch": batch, "scenario": scen, "arm": arm, "k": r["k"], **o})
                else:
                    print(f"{os.path.relpath(batch, ROOT)} {scen} {arm}-{r['k']}: {line(o)}"
                          + (f"; {handoff_line(o)}" if handoff_line(o) else ""))
        if grouped and os_:
            n = len(os_)
            m = lambda f: sum(f(o) for o in os_) / n
            tiers = [sum(o["tier"] == t for o in os_) for t in range(5)]
            print(f"{os.path.relpath(batch, ROOT)} {scen} {arm} n={n}: O {m(lambda o: o['outcome']):.1f}  tiers 0-4 {tiers}  "
                  f"s1 {m(lambda o: o['s']['survival']):.2f} s2 {m(lambda o: o['s']['supply']):.2f} "
                  f"s3 {m(lambda o: o['s']['wellbeing']):.2f} s4 {m(lambda o: o['s']['growth']):.2f}")
    if as_json:
        print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
