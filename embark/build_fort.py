#!/usr/bin/env python3
"""build_fort.py RECIPE.json : turn the loaded fresh embark into a task fort (docs/SEED-FORTS.md).

Runs inside the DF container with the embark loaded and paused (embark/make_task_fort.sh calls it). A recipe
(embark/forts/*.json) says what the fort must look like when the run starts; the steps below make it so directly,
without playing a policy for a year:

  1. population   migrant waves sized by a raised caravan report (embark/fort_events.lua wave), one game day each,
                  until `population.target` citizens (DF picks who comes; the count per wealth was stable when measured)
  2. structures   the same tool calls the scripted reference policy makes (harness2.act: appoint_manager,
                  build_workshop on W sites, dig_stairs + dig_room for the farm room, build_farm on its soil), each
                  completed at once with DFHack's dig-now / build-now instead of waiting for dwarves
  3. settle       `settle_days` of game time so farmers plant the plots and migrants walk in (DF's simulation:
                  not reproducible run to run, BENCHMARK-v2 §7.1)
  4. stocks       exact counts with embark/fort_stock.lua (logs, drink in barrels, empty barrels, plants, seeds,
                  food, furniture)
  5. orders, plugins, stress, report and pending events (embark/fort_events.lua)

Prints BUILD-STEP lines as it goes and a final BUILD-OK. Exit 1 on any failed step.
"""
import json, os, re, subprocess, sys, time

DFP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, DFP)
import harness as H  # noqa: E402
import harness2 as H2  # noqa: E402

EMB = os.path.join(DFP, "embark")
T0 = time.time()


def log(*a):
    print(f"BUILD-STEP [+{time.time() - T0:.0f}s]", *a, flush=True)


def lua(script, *args):
    return H.dfhack("lua", "-f", os.path.join(EMB, script), *[str(x) for x in args])


def fail(msg):
    print("BUILD-FAIL", msg, flush=True)
    sys.exit(1)


def tick():
    return int(re.sub(r"\D", "", H.dfhack("lua", "print(df.global.cur_year*403200+df.global.cur_year_tick)")) or 0)


def run_ticks(n, limit_s=900):
    """Let DF run n game ticks (clearing popups; DF's own auto-pauses are resumed). Raises on a stuck game."""
    end, t_last, last = tick() + n, time.time(), None
    H.dfhack("lua", "-f", os.path.join(DFP, "advance.lua"), str(n), "notrip")
    while True:
        time.sleep(1)
        H.dfhack("lua", "local p=df.global.world.status.popups for i=#p-1,0,-1 do p:erase(i) end "
                        "local mi=df.global.game.main_interface if mi.options.open then mi.options.open=false end")
        t = tick()
        if t >= end:
            break
        if t != last:
            last, t_last = t, time.time()
        elif time.time() - t_last > 60:
            fail(f"DF stopped ticking at {t}")
        if "true" in H.dfhack("lua", "print(df.global.pause_state)"):
            H.dfhack("lua", "-f", os.path.join(DFP, "advance.lua"), str(end - t), "notrip")
        if time.time() - t_last > limit_s:
            fail("advance took too long")
    H.dfhack("lua", "df.global.pause_state=true")


def citizens():
    m = re.search(r"CITIZENS (\d+)", lua("fort_events.lua", "count"))
    return int(m.group(1)) if m else 0


def call(name, args):
    res, err = H2.act(name, args)
    log(f"{name} {json.dumps(args, sort_keys=True)} -> {'ERROR ' if err else ''}{str(res)[:160]}")
    return res, err


def population(p):
    """Waves in order (reported wealth each) while the fort is below `target`; then at least `min` citizens.
    The v2 harness's manager needs an assigned office from 20 citizens (BENCHMARK-v2 decision 5), so a recipe that
    replaces a 19-dwarf snapshot must stay at <= 19. A wave's size varies (+10 to +12 at 18500 from 7 founders,
    measured over 16 builds), and an arrived citizen can't be sent away again (flags1.left, as invade.lua uses for
    raiders, doesn't remove a citizen), so one wave is used and a fort outside [min, max] fails with BUILD-FAIL
    population; make_task_fort.sh then rebuilds it from the embark (up to 3 tries)."""
    target = p["target"]
    for w in p.get("waves", []):
        n = citizens()
        if n >= target:
            break
        log(lua("fort_events.lua", "wave", w))
        run_ticks(1200)
        log(f"citizens {n} -> {citizens()}")
    n = citizens()
    if not p.get("min", target) <= n <= p.get("max", 10 ** 6):
        fail(f"population {n} outside [{p.get('min', target)}, {p.get('max')}]")
    log(lua("fort_events.lua", "clear_migrants"))
    return n


def structures(s, sites0, surface_z):
    """sites0: free 3x3 sites of the pristine embark around the map's centre (embark/fort_site.lua sites), so the
    layout depends only on the map. Workshops take them nearest first; the farm stair the farthest whose room is soil."""
    if s.get("manager"):
        call("appoint_manager", {})
    used, left = [], list(sites0)
    for t in s.get("workshops", []):
        # the first pristine site that still takes it (a sapling or an item can land on one within the build's day)
        while left:
            site = left.pop(0)
            _, err = call("build_workshop", {"type": t, **{k: site[k] for k in "xyz"}})
            used.append(site)
            if not err:
                break
        else:
            fail("no free 3x3 site left for " + t)
    farms = s.get("farms", 0)
    if farms:
        # the scripted policy's farm room: a stair at the farthest free 3x3 site, a 7x3 room one level down with the
        # stair at its west end. Farthest first, skipping sites whose room box isn't all soil (tree roots under a
        # living tree are never dug, so the room would lose a plot; a brook bed or stone gives no plot)
        z = surface_z
        # the scripted policy sees 8 sites; if none of those has a soil room under it, the further ones in order
        near = [x for x in sites0[:8] if x not in used and x["z"] == z]
        far = [x for x in sites0[8:] if x not in used and x["z"] == z]
        st = next((x for x in list(reversed(near)) + far
                   if lua("fort_site.lua", "room", x["x"], x["y"] - 1, z - 1, 7, 3).strip().endswith("OK")), None)
        if st is None:
            fail("no free 3x3 site has an all-soil 7x3 room under it")
        call("dig_stairs", {"x": st["x"], "y": st["y"], "z_top": z, "z_bottom": z - 1})
        call("dig_room", {"x": st["x"], "y": st["y"] - 1, "z": z - 1, "w": 7, "h": 3})
        log("dig-now", H.dfhack("dig-now")[:120])
        for _ in range(8):
            obs = H2.observe()
            left = obs.get("dig_designations_pending", 0) or 0
            if not left:
                break
            log(f"{left} designations left: running half a day")
            run_ticks(600)
        built = 0
        for _ in range(farms + 2):
            if built >= farms:
                break
            obs = H2.observe()
            ug = (obs.get("map") or {}).get("underground_soil_farm_sites") or []
            if not ug:
                break
            _, err = call("build_farm", dict(ug[0]))
            built += 0 if err else 1
        if built < farms:
            fail(f"built {built} of {farms} farm plots")
    if s.get("workshops") or farms:
        # buildingplan attaches materials to a planned building over the next ticks; build-now skips a building
        # until it has them ("Skipped N buildings with pending items"), so give it a few ticks and retry
        for _ in range(6):
            out = H.dfhack("build-now")
            log("build-now", " / ".join(out.splitlines())[:160])
            m = re.search(r"Skipped (\d+) building", out)
            if not m or m.group(1) == "0":
                break
            run_ticks(100)
    for p in s.get("plugins", []):
        call("enable_automation", {"name": p})


def stocks(st):
    for cmd in st:
        out = lua("fort_stock.lua", *cmd)
        log(out.splitlines()[-1] if out else f"(no output) {cmd}")
        if "STOCK" not in out:
            fail(f"stock step {cmd}: {out[-300:]}")


def main():
    recipe = json.load(open(sys.argv[1]))
    H.dfhack("lua", "df.global.pause_state=true")
    log("recipe", recipe["name"], "tick", tick(), "citizens", citizens())
    # sites from the pristine embark, anchored at the map's centre (not the wagon, which DF places +-1 tile at
    # random), so every build of a seed gets the same layout (embark/fort_site.lua)
    out = lua("fort_site.lua", "sites", 24)
    sites0 = json.loads(out.split("SITES", 1)[1]) if "SITES" in out else []
    surface_z = sites0[0]["z"] if sites0 else None
    log("sites", [(x["x"], x["y"], x["z"]) for x in sites0], lua("fort_site.lua", "anchor").strip())
    if "population" in recipe:
        population(recipe["population"])
    stocks(recipe.get("pre_stocks", []))   # e.g. logs, so the workshops below have material
    structures(recipe.get("structures", {}), sites0, surface_z)
    if recipe.get("settle_days"):
        run_ticks(int(recipe["settle_days"] * 1200))
        log("settled", recipe["settle_days"], "days; citizens", citizens())
        if "population" in recipe and not recipe["population"].get("min", 0) <= citizens() <= recipe["population"].get("max", 10 ** 6):
            fail(f"population {citizens()} after settling")
    stocks(recipe.get("stocks", []))
    for o in recipe.get("orders", []):
        _, err = call("add_order", o)
        if err:
            fail("add_order")
    for cmd in recipe.get("events", []):
        log(lua("fort_events.lua", *cmd))
    H.dfhack("lua", "df.global.pause_state=true")
    print("BUILD-OK", recipe["name"], "tick", tick(), "citizens", citizens(), f"{time.time() - T0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
