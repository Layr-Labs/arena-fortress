"""The summary.jsonl row of a v3 game: smoke.run_one's row, field for field, plus the v3 fields (contract §6), so
bench/outcomes.py and bench/predicates.py score it unchanged. Fields that belong to the frozen loop's own harness
(history window, loop notes, prompt tokens, ...) keep their names with neutral values; the gateway's ledger has
the token counts."""
import fcntl, time

DAY = 1200


def append_line(path, line):
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(line + "\n"); f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)


def _causes(sc):
    c = (sc or {}).get("citizen_death_causes") or {}
    return {} if isinstance(c, list) else c


def summary_row(g, sf, daily, credit, crashed):
    """g: the rules.Game at its end. sf: score.lua at the end; daily: smoke.daily_metrics; credit: credit.lua dump."""
    s0, sc, start, days = g.s0, g.task, g.start_tick, g.days
    sf, daily, credit = sf or {}, daily or {}, credit or {}
    played = ((sf.get("abs_tick") or start) - start) / DAY
    start_causes = _causes(s0)
    deaths = {k: v - start_causes.get(k, 0) for k, v in _causes(sf).items() if v - start_causes.get(k, 0) > 0}
    o0 = s0.get("other_death_causes") or {}
    o0 = {} if isinstance(o0, list) else o0
    od = sf.get("other_death_causes") or {}
    od = {} if isinstance(od, list) else od
    other_deaths = {k: v - o0.get(k, 0) for k, v in od.items() if v - o0.get(k, 0) > 0}
    thefts = [t for t in (sf.get("thefts") or []) if isinstance(t, dict) and t.get("tick", -1) >= start]
    ilog = g.backend.interruption_log()
    st = g.stats
    cond = g.condition or {}
    model = cond.get("model")
    row = {"arm": g.arm, "k": g.k, "crashed": crashed, "wall_s": round(time.time() - g.t_wall0),
           "scenario": sc.get("name"), "scenario_metrics": sc.get("metrics"), "scenario_setup": g.setup_out,
           "days_played": round(played, 1), "days_target": days,
           "hands_off_from_day": (g.ho_tick - start) // DAY if g.ho_tick is not None else None,
           "survived_year": played >= 336 and sf.get("citizens", 0) > 0,
           "survived_horizon": played >= days and sf.get("citizens", 0) > 0,
           "pop_start": s0["citizens"], "pop_peak": g.peak, "pop_final": sf.get("citizens"),
           "wealth_created_start": s0["wealth_created"], "wealth_created_final": sf.get("wealth_created"),
           "wealth_total_final": sf.get("wealth_total"),
           "wealth_crafted_final": sf.get("wealth_crafted"), "wealth_logs_final": sf.get("wealth_logs"),
           "wealth_by_category_final": sf.get("wealth_by_category"),
           "produced_value_final": credit.get("produced"), "credited_value_final": credit.get("credited"),
           "produced_by_category_final": credit.get("produced_by_category"),
           "credited_by_category_final": credit.get("credited_by_category"),
           "placed_value_final": credit.get("placed_value"), "raw_value_final": credit.get("raw_value"),
           "credit_meta": credit.get("meta"),
           "food_min": g.min_food, "drink_min": g.min_drink, "food_final": sf.get("food"), "drink_final": sf.get("drink"),
           "food_positive": min(g.min_food, sf.get("food", 0) or 0) > 0,
           "citizen_deaths": (sf["citizen_deaths"] - s0.get("citizen_deaths", 0)) if "citizen_deaths" in sf else None,
           "citizen_deaths_before_start": s0.get("citizen_deaths", 0),
           "starvation_or_thirst_deaths": deaths.get("HUNGER", 0) + deaths.get("THIRST", 0),
           "citizen_death_causes": deaths, "other_death_causes": other_deaths,
           "invaders_killed": sf.get("invaders_killed"), "invaders_alive_final": sf.get("invaders_alive"),
           "thefts": len(thefts), "theft_items": [t.get("item_type") for t in thefts],
           "thief_held_items_final": sf.get("thief_held_items"), "thieves_on_map_final": sf.get("thieves_on_map"),
           "thieves_caged_final": sf.get("thieves_caged"),
           "thieves_killed": (sf["thieves_dead"] - s0.get("thieves_dead", 0)) if "thieves_dead" in sf else None,
           "loops": None, "loop_notes": False, "history": None, "old_obs": None, "action_log": None,
           **daily,
           # run_one's stats block (the frozen loop's model-side counters are the gateway's in v3: 0 / None here)
           "interruptions": len(ilog), "length_retries": 0, "rate_limit_waits": 0, "no_tool_call": 0,
           "decisions": st["decisions"], "rejected": st["rejected"], "forced_adv": 0, "api_errors": 0,
           "stalls": st["stalls"], "context_trims": 0, "tools": st["tools"], "tripwire_stops": st["tripwire_stops"],
           "prompt_tok": None, "completion_tok": None, "cap_hit_day": st["cap_hit_day"], "providers": {},
           "hands_off_advances": st["hands_off_advances"],
           "interruption_log": [{"day": (x["tick"] - start) // DAY if x.get("tick") else None, "focus": x.get("focus"),
                                 "text": (x.get("text") or "")[:160]} for x in ilog[:20]],
           "model": model, "provider_pin": cond.get("provider"), "endpoint": cond.get("endpoint"),
           "dropped_request_fields": None, "thinking": None}
    row["instance"] = getattr(getattr(g.backend, "H", None), "INSTANCE", None)
    # v3 (contract §6)
    row.update({"api": "v0", "key": g.key, "harness_digest": g.harness_digest, "run_id": g.run_id,
                "wall_capped": g.wall_capped, "actions_used": g.actions_used, "actions_rejected": g.actions_rejected,
                "action_limit_rejections": g.limit_rejections, "end_reason": g.end_reason,
                "finish_reason": g.finish_reason, "wall_used_s": round(g.wall_used(), 1),
                "throttle_s": round(g.throttle_s, 1), "unmanaged_s": round(g.unmanaged_s, 1),
                "advances": st["advances"], "runout_advances": st["runout_advances"],
                "tripwires_ignored": st["tripwires_ignored"], "observes": st["observes"], "queries": st["queries"],
                "strange_moods": bool(sc.get("strange_moods")), "rules": {"K": g.K, "max_advance_days": g.max_days,
                                                                          "wall_s": g.wall_s},
                "facts": getattr(g.facts, "NAME", getattr(g.facts, "__name__", None))})
    return row
