"""The observation as a short status report for the model: what matters now first, then the details it needs to act
(ids, sites), then what happened since the last consult. Facts only come from the observation; the judgements
("LOW", "stuck") are this harness's own reading of them."""
import json


def _j(x, n=None):
    s = json.dumps(x, separators=(",", ":"), ensure_ascii=False, default=str)
    return s if n is None or len(s) <= n else s[:n] + "…"


def report(obs, day, days_left, days, hands_off_day, events, journal, notes, status, reason):
    st = obs.get("stocks") if isinstance(obs.get("stocks"), dict) else {}
    adm = obs.get("administrators") if isinstance(obs.get("administrators"), dict) else {}
    dw = [d for d in obs.get("dwarves") or [] if isinstance(d, dict)]
    cit = len(dw)
    L = []
    head = f"DAY {day} of {days}, {days_left} left"
    if hands_off_day is not None:
        head += f"; hands-off from day {hands_off_day} ({max(0, hands_off_day - day)} days to act)"
    L.append(head + f". Consulted because: {reason}.")

    # --- alerts (this harness's reading) ---
    alerts = status.get("alerts") or []
    if alerts:
        L.append("ALERTS: " + "; ".join(alerts))

    # --- people ---
    stressed = obs.get("stressed_citizens")
    jobs = {}
    for d in dw:
        j = d.get("job") or "idle"
        jobs[j] = jobs.get(j, 0) + 1
    idle = jobs.get("idle", 0)
    L.append(f"CITIZENS {cit} (stressed {stressed}, idle {idle}). Manager: {adm.get('MANAGER')} "
             f"(validating orders: {adm.get('manager_active_for_orders')}, office: {_j(adm.get('manager_office'))}).")

    # --- supply ---
    trend = status.get("trend") or {}
    def tr(k):
        t = trend.get(k)
        return "" if t is None else f" ({t:+.1f}/day)"
    L.append("SUPPLY drink %s%s, food_edible %s%s, prepared_meals %s, plants_brewable %s, plants_total %s, seeds %s, "
             "barrels_empty %s, logs_usable %s, boulders_usable %s." % (
                 st.get("drink"), tr("drink"), st.get("food_edible"), tr("food"), st.get("prepared_meals"),
                 st.get("plants_brewable"), st.get("plants_total"), st.get("seeds"), st.get("barrels_empty"),
                 st.get("logs_usable"), st.get("boulders_usable")))
    seeds = st.get("seeds_by_kind") or {}
    if seeds:
        L.append("SEEDS " + ", ".join(f"{k}:{(v or {}).get('n')}{'(ug)' if (v or {}).get('underground') else ''}"
                                       for k, v in list(seeds.items())[:10]))

    # --- housing ---
    h = status.get("housing") or {}
    L.append(f"HOUSING placed beds {h.get('beds_placed')} / citizens {cit}; dining seats {h.get('seats')} "
             f"(need {(cit + 1) // 2}); bed items {st.get('beds')}, free {_j(st.get('furniture_free'))}.")

    # --- workshops, farms, orders ---
    ws = [f"{w.get('type')}#{w.get('id')}{'' if w.get('built') else '(unbuilt)'}"
          f"{'[' + ','.join(w.get('jobs')[:3]) + ']' if w.get('jobs') else ''}"
          for w in obs.get("workshops") or [] if isinstance(w, dict)]
    L.append("WORKSHOPS " + (", ".join(ws) or "none"))
    fp = [f"#{p.get('id')}{'ug' if p.get('subterranean') else 'surf'}:{p.get('crop_this_season') or '-'}"
          f"{'' if p.get('built') else '(unbuilt)'}" for p in obs.get("farm_plots") or [] if isinstance(p, dict)]
    L.append("FARMS " + (", ".join(fp) or "none") + f"; plugins {_j(obs.get('plugins'))}.")
    mine = status.get("orders") or set()
    od = []
    for o in obs.get("orders") or []:
        if not isinstance(o, dict):
            continue
        name = o.get("recipe") or o.get("reaction") or o.get("job")
        flag = "[S]" if o.get("id") in mine else ""
        state = "ok" if o.get("active") else ("unvalidated" if not o.get("validated") else "inactive")
        od.append(f"#{o.get('id')}{flag} {name} {o.get('left')}/{o.get('total')} {o.get('repeat') or 'once'} "
                  f"{state} jobs:{o.get('jobs_in_progress')}")
    L.append("ORDERS " + ("; ".join(od[:20]) or "none"))

    # --- moods, threats ---
    for m in obs.get("moods") or []:
        if isinstance(m, dict):
            L.append("MOOD " + _j({k: m.get(k) for k in ("unit_id", "mood", "skill", "job", "claimed_workshop",
                                                          "waiting", "items_needed")}, 600))
    th = obs.get("threats") if isinstance(obs.get("threats"), dict) else {}
    if th.get("visible_hostiles"):
        L.append("THREATS " + _j({k: th.get(k) for k in ("visible_hostiles", "nearest_hostile_dist_to_wagon",
                                                          "by_race")}, 400)
                 + "; military " + _j(obs.get("military"), 300) + "; alert " +
                 _j((obs.get("burrows") or {}).get("civilian_alert") if isinstance(obs.get("burrows"), dict) else None))
    if th.get("dead_citizens_total"):
        L.append(f"DEAD citizens so far: {th.get('dead_citizens_total')}")

    # --- sites the model may use ---
    sites = ((obs.get("map") or {}) if isinstance(obs.get("map"), dict) else {}).get("sites") or []
    by = {}
    for s in sites:
        if isinstance(s, dict) and s.get("free", True):
            k = s.get("kind")
            tag = s["id"]
            if k == "R":
                st_ = "dug" if s.get("dug") else ("digging" if s.get("designated") else "undug")
                tag += f"({st_}{',soil' if s.get('soil') else ''},z{s.get('z')})"
            elif k == "A":
                tag += f"(z{s.get('z')},{s.get('open_tiles')} tiles)"
            by.setdefault(k, []).append(tag)
    L.append("SITES (use the id before the brackets) " +
             "; ".join(f"{k}: {' '.join(v[:10])}" for k, v in sorted(by.items())))
    if obs.get("dig_designations_pending"):
        L.append(f"DIGGING pending tiles {obs.get('dig_designations_pending')}")

    # --- what happened ---
    canc = obs.get("recent_cancellations") or []
    if canc:
        L.append("CANCELLATIONS " + _j(canc[:6], 700))
    evs = [f"d{(e.get('tick') or 0) // 1200}:{e.get('type')}:{(e.get('text') or '')[:80]}" for e in events
           if isinstance(e, dict) and e.get("announcement")]
    if evs:
        L.append("EVENTS " + " | ".join(evs[-10:]))
    recent = [j for j in journal if j["day"] >= day - 8]
    fails = [f"d{j['day']} {j['by']} {j['tool']} {_j(j['args'], 80)} -> {j['result'][:120]}"
             for j in recent if not j["ok"]][-8:]
    done = [f"d{j['day']} {j['by']} {j['tool']} {_j(j['args'], 60)}" for j in recent if j["ok"]][-10:]
    if done:
        L.append("DONE RECENTLY " + " | ".join(done))
    if fails:
        L.append("FAILED RECENTLY " + " | ".join(fails))
    if status.get("plan"):
        L.append("STEWARD PLAN " + status["plan"])
    if notes:
        L.append("YOUR NOTES " + " | ".join(notes))
    return "\n".join(L)
