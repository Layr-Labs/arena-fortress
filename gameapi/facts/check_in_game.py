#!/usr/bin/env python3
"""In-game check of gameapi.facts (run inside the DF image, with a fort loaded; check_in_game.sh does the setup).

Exercises observe(), every query, events(), and each new v0 tool once (build_workshop of non-frozen types, a
generic add_order and item-type `when` conditions, slaughter), plus a strange mood (scenarios/lua/mood.lua) to see the
mood facts. Advances game time with the frozen loop's smoke.advance() (popups dismissed as in a real game).
Prints a JSON-lines log and a summary; exits 1 if a check failed.
"""
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from gameapi.facts import Game  # noqa: E402

RESULTS = []


def log(step, ok, **info):
    RESULTS.append((step, ok))
    print(json.dumps({"step": step, "ok": ok, **info}, default=str), flush=True)


def short(v, n=600):
    s = json.dumps(v, default=str)
    return s if len(s) <= n else s[:n] + "...(%d chars)" % len(s)


def advance_days(days):
    import smoke   # the frozen loop's advance (advance.lua + popup dismissal); read-only use
    moved, calls = 0, 0
    while moved < days * 1200 and calls < 12:   # DF pauses on some announcements (a mood): carry on, as a game would
        moved += smoke.advance(days * 1200 - moved)
        calls += 1
    return moved


def main():
    g = Game()
    t0 = time.time()
    tools = g.tools()
    ws_enum = next(t for t in tools if t["function"]["name"] == "build_workshop")["function"]["parameters"]["properties"]["type"]["enum"]
    log("tools", len(tools) == 22, n=len(tools), names=sorted(t["function"]["name"] for t in tools), build_workshop_enum=ws_enum)

    obs = g.observe()
    tick0 = obs["date"]["abs_tick"]
    errs = {k: v for k, v in obs.items() if isinstance(v, str) and v.startswith("ERR")}
    log("observe", obs.get("schema") == 7 and not errs, keys=sorted(obs), errors=errs,
        bytes=len(json.dumps(obs)), date=obs["date"], sites=obs["map"]["sites"], orders=obs.get("orders"),
        administrators=obs.get("administrators"), zones_total=obs.get("zones_total"),
        furniture_total=obs.get("furniture_total"), furniture_unzoned=obs.get("furniture_unzoned"),
        dig_pending_by_z=obs.get("dig_pending_by_z"), plugins=obs.get("plugins"))
    removed = [k for k in ("manager_needs_office",) if k in (obs.get("administrators") or {})]
    removed += ["threats.note"] if "note" in (obs.get("threats") or {}) else []
    removed += ["map.free_3x3_sites_near_wagon"] if "free_3x3_sites_near_wagon" in (obs.get("map") or {}) else []
    log("observe_no_interpretation", not removed, present=removed)

    for name, args in [("stocks", {"limit": 5}), ("stocks", {"item_type": "WOOD", "limit": 3}),
                       ("units", {"limit": 2}), ("units", {"kind": "animals", "limit": 30}),
                       ("units", {"kind": "others", "limit": 3}), ("jobs", {"limit": 5}), ("orders", {}),
                       ("buildings", {"limit": 5}), ("zones", {}), ("map", {"radius": 4}),
                       ("map", {"radius": 3, "z": obs["map"]["surface_z"] - 3}),
                       ("manager_order_types", {}), ("workshop_types", {})]:
        r = g.query(name, **args)
        log(f"query {name} {json.dumps(args)}", r.get("ok") is True, result=short(r, 2500))
    log("query unknown", g.query("nope").get("error_code") == "unknown_query")
    log("query bad limit", g.query("jobs", limit=10**6).get("error_code") == "bad_arguments")
    hid = g.query("map", radius=1, z=obs["map"]["surface_z"] - 12)
    log("query map hidden tiles are '?'", hid.get("ok") and all(set(row) <= {"?"} for lv in hid["levels"] for row in lv["shape"]),
        levels=hid.get("levels"))

    ev = g.events(since_tick=tick0 - 30 * 1200, limit=20)
    log("events", isinstance(ev, list), n=len(ev), first=ev[:3])

    # --- new tools -------------------------------------------------------------------------------------------
    free_w = [s["id"] for s in obs["map"]["sites"] if s["kind"] == "W" and s["free"]]
    log("free W sites", len(free_w) >= 3, sites=free_w)
    built = {}
    for typ, site in zip(["Leatherworks", "Craftsdwarfs", "Butchers"], free_w):
        r = g.act("build_workshop", {"type": typ, "site": site})
        built[typ] = r
        log(f"build_workshop {typ} at {site}", r.get("ok") is True, result=r)
    r = g.act("build_workshop", {"type": "Siege", "site": free_w[-1]}) if free_w else {}
    log("build_workshop Siege (5x5) on a 3x3 W site", r.get("ok") is False, result=r)
    r = g.act("build_workshop", {"type": "NotAWorkshop", "site": free_w[0]}) if free_w else {}
    log("build_workshop unknown type", r.get("error_code") == "bad_arguments" and "allowed" in r, error=r.get("error"))

    r = g.act("add_manager_order", {"job": "ConstructBlocks", "material_category": ["wood"], "amount": 2})
    log("add_manager_order ConstructBlocks wood", r.get("ok") is True, result=r)
    r = g.act("add_manager_order", {"job": "CustomReaction", "reaction": "MAKE_PEARLASH", "amount": 1})
    log("add_manager_order reaction MAKE_PEARLASH", r.get("ok") is True, result=r)
    r = g.act("add_manager_order", {"job": "ConstructBin", "material_category": ["wood"], "amount": 1, "repeat": "monthly",
                                    "when": [{"item_type": "BIN", "below": 5}, {"item_type": "WOOD", "flags": ["unrotten"], "at_least": 10},
                                             {"item_type": "ANY", "flags": ["unrotten", "cookable"], "at_least": 1}]})
    log("add_manager_order with item_type/flags when (and ANY + flags)", r.get("ok") is True, result=r)
    r = g.act("add_order", {"recipe": "cook_meal", "amount": 3, "repeat": "daily", "when": [{"stock": "food_edible", "at_least": 20}]})
    cook_id = (r.get("result") or {}).get("order_id")
    log("add_order frozen recipe with stock when", r.get("ok") is True, result=r)
    r = g.act("add_order", {"amount": 5, "repeat": "daily", "when": [{"below": 70, "at_least": 0}]})
    log("add_order without recipe (the e2e glm call) names the field", r.get("error_code") == "bad_arguments"
        and "add_order needs recipe" in r.get("error", ""), result=r)
    r = g.act("add_order", {"recipe": "brew_drink", "amount": 5, "repeat": "daily", "when": [{"below": 70}]})
    log("add_order when without stock names the field", r.get("error_code") == "bad_arguments"
        and "needs stock" in r.get("error", ""), result=r)
    r = g.act("add_manager_order", {"job": "Dig", "amount": 1})
    log("add_manager_order non-manager job refused", r.get("error_code") == "bad_arguments", result=r)
    r = g.act("add_manager_order", {"job": "MakeBarrel", "material_category": ["notacategory"], "amount": 1})
    log("add_manager_order bad material_category refused by workorder", r.get("ok") is False, result=r)
    r = g.act("add_manager_order", {"job": "ConstructBin", "material_category": ["wood"], "amount": 1, "repeat": "daily",
                                    "when": [{"item_type": "BIN", "flags": ["notaflag"], "below": 5}]})
    log("add_manager_order bad when flag refused by workorder", r.get("ok") is False, result=r)
    obs2 = g.observe()
    cook = next((o for o in obs2["orders"] if o["id"] == cook_id), None)
    log("observe order when: flag-only condition (the old NONE bug)",
        bool(cook) and cook["when"][0].get("item_type") is None and cook["when"][0].get("flags") == ["cookable", "unrotten"]
        and cook["when"][0].get("stock") == "food_edible" and cook.get("recipe") == "cook_meal"
        and isinstance(cook.get("created_tick"), int), order=cook)
    q = g.query("orders")
    log("query orders full conditions", q.get("ok") is True, orders=q.get("orders"))

    animals = g.query("units", kind="animals", limit=50).get("units") or []
    cand = [a for a in animals if a.get("tame") and not a.get("pet_owner_id") and not a.get("marked_for_slaughter")]
    target = cand[0]["id"] if cand else None
    r = g.act("slaughter", {"unit_id": target}) if target is not None else {"ok": False}
    log("slaughter", r.get("ok") is True, target=cand[0] if cand else None, result=r)
    pets = [a for a in animals if a.get("pet_owner_id")]
    if pets:
        r = g.act("slaughter", {"unit_id": pets[0]["id"]})
        log("slaughter a pet refused", r.get("error_code") == "not_slaughterable", result=r)
    cit = (obs.get("dwarves") or [{}])[0].get("id")
    r = g.act("slaughter", {"unit_id": cit})
    log("slaughter a citizen refused", r.get("error_code") == "not_slaughterable", result=r)
    after = {a["id"]: a for a in g.query("units", kind="animals", limit=50).get("units") or []}
    log("slaughter mark visible in units query", target in after and after[target]["marked_for_slaughter"] is True)

    # a few frozen tools, results without advice
    for tool, args in [("appoint_manager", {}), ("cancel_order", {"order_id": 999999}),
                       ("enable_automation", {"name": "autochop"}), ("lock_door", {"locked": True}),
                       ("build_farm", {"site": "R1"}), ("dig_room", {"site": "X9"}),
                       ("advance_days", {"days": 1}), ("no_such_tool", {})]:
        r = g.act(tool, args)
        advice = set(r) & {"hint", "note", "reminder", "warning", "valid", "nearest_free_centre"}
        advice |= set(r.get("result") or {}) & {"hint", "note", "reminder", "warning", "valid", "nearest_free_centre"}
        log(f"frozen {tool} {json.dumps(args)}", not advice, result=r)
    s1 = next((s["id"] for s in obs2["map"]["sites"] if s["kind"] == "S"), None)
    if s1:
        r = g.act("dig_stairs", {"site": s1})
        log(f"dig_stairs {s1}", r.get("ok") is True, result=r)

    # --- strange mood ---------------------------------------------------------------------------------------
    # schema 7: only what a vanilla player sees (gameapi/manual/MOOD-VISIBILITY.md). A fey woodcrafter finds logs (it
    # gathers, then works: never waiting, so no demands shown); a secretive mason finds no rock on this fort (it claims
    # the Masons and waits: its demand is shown as the workshop words it)
    hidden_keys = {"flags", "available", "available_approx", "item"}
    out = g.df.run("lua", "-f", os.path.join(REPO, "scenarios", "lua", "mood.lua"), "woodcrafter", "fey", "0")
    log("mood.lua woodcrafter fey 0", "MOOD " in out, out=out[-400:])
    m0 = g.observe().get("moods") or []
    log("observe moods (just struck): no claim, no demands", len(m0) == 1 and all(
        not m.get("waiting") and "items_needed" not in m and "claimed_building_id" not in m for m in m0), moods=m0)
    moved = advance_days(3)
    obs3 = g.observe()
    log("advance 3 days", moved > 0, ticks=moved)
    moods = {m["mood"]: m for m in obs3.get("moods") or []}
    fey = moods.get("Fey") or {}
    log("fey woodcrafter after 3 days: claimed, gathering/working, no demands shown",
        fey.get("claimed_workshop") == "Craftsdwarfs" and not fey.get("waiting") and "items_needed" not in fey, mood=fey)
    log("workshops after 3 days", True, workshops=obs3.get("workshops"))
    after = {a["id"]: a for a in g.query("units", kind="animals", limit=50).get("units") or []}
    jobs = g.query("jobs", limit=200).get("jobs") or []
    log("slaughter progress after 3 days", True, animal_still_alive=target in after,
        slaughter_jobs=[j for j in jobs if "Slaughter" in j["job"] or "Butcher" in j["job"]])
    ev = g.events(since_tick=tick0 - 1, limit=50)
    log("events since start", len(ev) > 0, n=len(ev), events=ev[-15:])
    log("sites after", True, sites=obs3["map"]["sites"])

    # the organiser's reference harness (contract §3.1; only in the organiser's checkout) reads this
    # observation through its adapter
    try:
        if not os.path.isdir(os.path.join(REPO, "baseline", "starter")):
            raise ImportError("the reference harness is not in this checkout")
        sys.path.insert(0, os.path.join(REPO, "baseline"))
        from starter import observation as SO, render as SR, status as SS
        n = SO.normalise({"day": 1, "tick": obs3["date"]["abs_tick"], "days_left": 100, "game_over": False,
                          "observation": obs3})
        text = SR.render_obs(n)
        st = SS.status(n)
        log("starter adapter reads the observation", bool(text) and bool(SO.sites(n).get("W")),
            sites_by_kind={k: [x.get("id") for x in v] for k, v in SO.sites(n).items()},
            moods=n.get("moods"), orders=n.get("orders"), administrators=n.get("administrators"),
            render=text[:1500] if isinstance(text, str) else short(text, 1500), status=short(st, 1500))
    except Exception as e:   # noqa: BLE001 (report any incompatibility as a failed check)
        import traceback
        log("starter adapter reads the observation", False, error=repr(e), tb=traceback.format_exc()[-1500:])

    # --- a mood that waits (DF has one mood at a time: reload the fort) ------------------------------------
    env = dict(os.environ, SNAPSHOT=os.path.join(REPO, "scenarios", "snapshots", "scripted-y1"))
    rr = subprocess.run(["./reset_fort.sh"], cwd=REPO, env=env, capture_output=True, text=True)
    log("reload scripted-y1", "READY" in rr.stdout, out=rr.stdout[-200:])
    g = Game()
    free_w = [s["id"] for s in g.observe()["map"]["sites"] if s["kind"] == "W" and s["free"]]
    r = g.act("build_workshop", {"type": "Masons", "site": free_w[0]})
    log(f"build_workshop Masons at {free_w[0]}", r.get("ok") is True, result=r)
    out2 = g.df.run("lua", "-f", os.path.join(REPO, "scenarios", "lua", "mood.lua"), "mason", "secretive", "0")
    log("mood.lua mason secretive 0", "MOOD " in out2, out=out2[-400:])
    m0 = g.observe().get("moods") or []
    log("secretive mood just struck: no demands", len(m0) == 1 and "items_needed" not in m0[0], moods=m0)
    moved = advance_days(3)
    sec = (g.observe().get("moods") or [{}])[0]
    need = sec.get("items_needed") or []
    log("secretive mason after 3 days: waiting in Masons, demand 'rock', primary quantity null",
        sec.get("claimed_workshop") == "Masons" and sec.get("waiting") is True and bool(need)
        and need[0].get("demand") == "rock" and need[0].get("quantity") is None
        and not any(set(x) & hidden_keys for x in need) and "material" not in need[0], ticks=moved, mood=sec)

    bad = [s for s, ok in RESULTS if not ok]
    print(json.dumps({"summary": {"checks": len(RESULTS), "failed": bad, "wall_s": round(time.time() - t0, 1)}}))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
