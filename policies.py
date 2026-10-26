"""Reference policies for smoke.py. Both speak harness2's tool API (same tools, same validation as
the model2 arm), so a model's score can be placed between a floor and a ceiling:
  Scripted  the playbook harness2.MANUAL describes, followed mechanically (upper reference)
  Random    uniformly random *valid* tool calls built from the observation (lower reference: a floor near noop)
A policy is called with the harness2 observation and returns (tool_name, args).
"""
import random

DAY = 1200


def _pending(obs, recipe):
    return any(o.get("recipe") == recipe and o.get("left", 0) > 0 for o in obs.get("orders") or [])


def manager_office_step(obs, may):
    """v2: from 20 citizens the manager validates work orders only from an office zone assigned to them with a built
    chair in it (observe2.lua administrators.manager_office). The next tool call towards that, or None when it isn't
    needed or already done. `may(key)` rate-limits each step (and records the try). Raw coordinates, as the policies
    use elsewhere: the office goes over the first dug underground area, else the farthest free 3x3 surface site."""
    adm = obs.get("administrators") if isinstance(obs.get("administrators"), dict) else {}
    if not (adm.get("manager_needs_office") and adm.get("manager_active_for_orders")):
        return None
    office = adm.get("manager_office")
    if isinstance(office, dict) and office.get("chair"):
        return None
    names = {d.get("name"): d.get("id") for d in obs.get("dwarves") or [] if isinstance(d, dict)}
    mgr = names.get(adm.get("MANAGER"))
    zones = [z for z in obs.get("zones") or [] if isinstance(z, dict) and z.get("type") == "Office"]
    mine = next((z for z in zones if mgr is not None and z.get("owner") == mgr), None)
    if mine is None:
        free = next((z for z in zones if z.get("owner") is None), None)
        if free and mgr is not None:
            return ("assign_zone", {"zone_id": free["id"], "dwarf_id": mgr}) if may("office_assign") else None
        m = obs.get("map") if isinstance(obs.get("map"), dict) else {}
        areas, ws = m.get("underground_dug_areas") or [], m.get("free_3x3_sites_near_wagon") or []
        if areas:
            box = {k: areas[0][k] for k in ("x", "y", "z", "w", "h")}
        elif ws:
            box = {"x": ws[-1]["x"] - 1, "y": ws[-1]["y"] - 1, "z": ws[-1]["z"], "w": 3, "h": 3}
        else:
            return None
        return ("make_zone", {"kind": "office", **box}) if may("office_zone") else None
    st = obs.get("stocks") if isinstance(obs.get("stocks"), dict) else {}
    if (st.get("furniture_free") or {}).get("chair", 0) > 0:
        if may("office_chair"):
            return "place_furniture", {"kind": "chair", **{k: mine[k] for k in ("x", "y", "z", "w", "h")}}
    elif not _pending(obs, "make_chair") and may("office_chair_order"):
        return "add_order", {"recipe": "make_chair", "amount": 1}
    return None


class Scripted:
    RETRY_DAYS = 3        # don't repeat the same setup step more often than this
    MAX_TRIES = 4         # give up on a setup step after this many attempts

    ROOM_WAIT_DAYS = 5    # farm room dug this long ago and still no soil farm site: try another stair site
    ROOM_GIVE_UP_DAYS = 15  # ... or this long, if its dig never finishes (a designation on an undiggable tile)
    SQUAD_SIZE = 6
    FARMS = 2             # underground farm plots
    SEAL_DIST = 45        # seal the shelter once a hostile is this close to the wagon (or the hatch is ready)

    def __init__(self, seed=0):
        self.tries, self.last = {}, {}
        self.stairs = None   # (x, y, z) of the access stair once dug
        self.failed_stairs = []   # stair sites whose room gave no soil farm site (a brook bed, stone), avoided after
        self.alarmed = False # defensive measures are in force (hostiles were seen)
        self.alert_tick = 0

    def _defence_setup(self, obs, now):
        """Peacetime setup the manual recommends: a squad (off duty, so nobody stops working) and a shelter burrow
        over the first dug level below the surface. No equipment, alert or orders until hostiles show up."""
        mil = obs.get("military") if isinstance(obs.get("military"), dict) else {}
        bur = obs.get("burrows") if isinstance(obs.get("burrows"), dict) else {}
        m = obs.get("map") if isinstance(obs.get("map"), dict) else {}
        if not mil.get("squads") and len(obs.get("dwarves") or []) >= 2 * self.SQUAD_SIZE and self._may("squad", now):
            return self._do("squad", now, ("create_squad", {"size": self.SQUAD_SIZE}))
        areas = m.get("underground_dug_areas") or []
        if areas and not any(b.get("civ_alert_burrow") for b in bur.get("list") or []) and self._may("burrow", now):
            a = areas[0]
            return self._do("burrow", now, ("create_burrow", {k: a[k] for k in ("x", "y", "z", "w", "h")}))
        return None

    def _defend(self, obs, now):
        """When hostiles are visible: shelter civilians, seal the entrance, use the squad; undo it when they're gone."""
        th = obs.get("threats") if isinstance(obs.get("threats"), dict) else {}
        mil = obs.get("military") if isinstance(obs.get("military"), dict) else {}
        bur = obs.get("burrows") if isinstance(obs.get("burrows"), dict) else {}
        drs = obs.get("doors") if isinstance(obs.get("doors"), dict) else {}
        m = obs.get("map") if isinstance(obs.get("map"), dict) else {}
        hostiles = th.get("visible_hostiles", 0) or 0
        squad = (mil.get("squads") or [None])[0]
        alert = bur.get("civilian_alert")
        doors = drs.get("list") or []
        if not hostiles:
            if not self.alarmed:
                return None
            # all clear: back to work
            if alert:
                return "civilian_alert", {"on": False}
            if any(d.get("locked") for d in doors):
                return "lock_door", {"locked": False}
            if squad and squad.get("orders"):
                return "squad_order", {"order": "stand_down"}
            self.alarmed = False
            return None
        self.alarmed = True
        setup = self._defence_setup(obs, now)
        if setup:
            return setup
        if squad and squad.get("uniform") == "none" and self._may("equip", now):
            return self._do("equip", now, ("equip_squad", {"uniform": "weapon_only"}))
        shelter = next((b for b in bur.get("list") or [] if b.get("civ_alert_burrow")), None)
        box = (shelter or {}).get("bbox") or {}
        ents = m.get("surface_entrances") or []
        # the stair that leads into the shelter (its foot is inside the burrow's box), else the first one
        ent = next((e for e in ents if box and box["x1"] <= e["x"] <= box["x2"] and box["y1"] <= e["y"] <= box["y2"]
                    and box["z1"] <= e["z"] - 1 <= box["z2"]), ents[0] if ents else None)
        hatch = next((d for d in doors if d.get("kind") == "hatch" and ent
                      and (d.get("x"), d.get("y"), d.get("z")) == (ent["x"], ent["y"], ent["z"])), None)
        if ent and not hatch:
            if drs.get("hatch_cover_items_free", 0) > 0 and self._may("hatch", now):
                return self._do("hatch", now, ("build_door", {"kind": "hatch", "x": ent["x"], "y": ent["y"], "z": ent["z"]}))
            if not drs.get("hatch_cover_items_free") and not _pending(obs, "make_hatch_cover") and self._may("order_hatch", now):
                return self._do("order_hatch", now, ("add_order", {"recipe": "make_hatch_cover", "amount": 1}))
        sealed_ready = hatch and hatch.get("built")
        dist = th.get("nearest_hostile_dist_to_wagon")
        dist = 10 ** 6 if dist is None else dist
        orders = (squad or {}).get("orders") or []
        attacking = any(o.get("order") == "attack" and o.get("targets_alive") for o in orders)
        if squad and squad.get("members") and squad.get("armed", 0) >= hostiles and not attacking:
            return "squad_order", {"order": "attack"}      # a party the armed squad matches: go and fight it
        if shelter and (sealed_ready or dist <= self.SEAL_DIST):
            if not alert:
                self.alert_tick = now
                return "civilian_alert", {"on": True}
            # outnumbered: hold the shelter's entrance from inside instead of fighting in the open
            if (squad and squad.get("members") and not attacking and ent
                    and not any(o.get("order") == "station" for o in orders) and self._may("station", now)):
                return self._do("station", now, ("squad_order", {"order": "station", "x": ent["x"], "y": ent["y"], "z": ent["z"] - 1}))
            # lock once everyone is in. Measured: a citizen left outside with the alert on reopens a locked hatch to
            # get in (research/defensive-tools.md), so locking early only helps if the party is at the door
            # v2.1: squad members stationed at the stair foot count as sheltered. DF spreads a stationed squad over
            # the tiles around the station point, some just outside the burrow box, so "every citizen inside" often
            # never held and the lock waited for the 2-day fallback, after the party had started (LT05 study, §5.3)
            squad_n = len([m for m in (squad or {}).get("members") or [] if isinstance(m, dict)]) if any(
                o.get("order") == "station" for o in orders) else 0
            everyone = shelter.get("citizens_inside", 0) >= len(obs.get("dwarves") or []) - squad_n
            if sealed_ready and not hatch.get("locked") and not attacking and (
                    everyone or now - self.alert_tick >= 2 * DAY or dist <= 15):
                return "lock_door", {"locked": True}
        return None

    def _office(self, obs, now):
        return manager_office_step(obs, lambda k: self._may(k, now) and bool(self._do(k, now, True)))

    def _may(self, key, now):
        if self.tries.get(key, 0) >= self.MAX_TRIES:
            return False
        return now - self.last.get(key, -10 ** 9) >= self.RETRY_DAYS * DAY

    def _do(self, key, now, call):
        self.tries[key] = self.tries.get(key, 0) + 1
        self.last[key] = now
        return call

    def __call__(self, obs):
        now = (obs.get("date") or {}).get("abs_tick", 0)
        st, m = obs.get("stocks") or {}, obs.get("map") or {}
        plugins, adm = obs.get("plugins") or {}, obs.get("administrators") or {}
        if not isinstance(st, dict) or not isinstance(m, dict):
            return "advance_days", {"days": 1}          # observation failed; let time pass
        sites = m.get("free_3x3_sites_near_wagon") or []
        surface_z = m.get("surface_z")
        citizens = len(obs.get("dwarves") or [])

        # 0. defence first while hostiles are visible (no-op otherwise)
        d = self._defend(obs, now)
        if d:
            return d
        hostile = ((obs.get("threats") or {}) if isinstance(obs.get("threats"), dict) else {}).get("visible_hostiles")

        # 1. manager, then the automation the manual calls required
        if not adm.get("manager_active_for_orders") and self._may("manager", now):
            return self._do("manager", now, ("appoint_manager", {}))
        o = self._office(obs, now)
        if o:
            return o
        for p in ("autochop", "seedwatch"):
            if plugins.get(p) != "on" and self._may(p, now):
                return self._do(p, now, ("enable_automation", {"name": p}))
        if st.get("logs_usable", 0) == 0 and st.get("boulders_usable", 0) == 0:
            return "advance_days", {"days": 1}

        # 2. workshops for drink, furniture and meals
        have = {w.get("type") for w in obs.get("workshops") or []}
        for t in ("Carpenters", "Still", "Kitchen"):
            if t not in have and sites and self._may("ws_" + t, now):
                return self._do("ws_" + t, now, ("build_workshop", {"type": t, **sites[0]}))

        # 3. standing orders: barrels before brewing, beds for everyone, meals, a little furniture
        if st.get("barrels_empty", 0) < 2 and not _pending(obs, "make_barrel"):
            return "add_order", {"recipe": "make_barrel", "amount": 5}
        if st.get("plants_brewable", 0) > 0 and not _pending(obs, "brew_drink"):
            return "add_order", {"recipe": "brew_drink", "amount": 5}
        if st.get("beds", 0) < citizens and not _pending(obs, "make_bed"):
            return "add_order", {"recipe": "make_bed", "amount": min(10, citizens - st.get("beds", 0))}
        if not _pending(obs, "cook_meal") and st.get("prepared_meals", 0) < 2 * citizens:
            return "add_order", {"recipe": "cook_meal", "amount": 5}
        for r in ("make_table", "make_chair"):
            if not _pending(obs, r) and self._may("order_" + r, now):
                return self._do("order_" + r, now, ("add_order", {"recipe": r, "amount": 3}))

        # 4. underground farm: stair down one level, dig a room around its foot, farm it
        farms = obs.get("farm_plots") or []
        ug = m.get("underground_soil_farm_sites") or []
        if self.stairs and "room" in self.tries and not farms and not ug:
            # the room one level down gave no soil farm site (on a fresh embark it can cut a brook bed or hit stone):
            # once its dig is done (or stuck), dig another stair away from this one
            waited = now - self.last.get("room", now)
            if (waited >= self.ROOM_WAIT_DAYS * DAY and not obs.get("dig_designations_pending")) \
                    or waited >= self.ROOM_GIVE_UP_DAYS * DAY:
                self.failed_stairs.append(self.stairs[:2])
                self.stairs = None
                self.tries.pop("room", None)
        # farthest free site (keep the near ones for workshops), at least 8 tiles from any stair that failed
        ok = [s for s in sites if all(max(abs(s["x"] - fx), abs(s["y"] - fy)) >= 8 for fx, fy in self.failed_stairs)]
        if surface_z is not None and self.stairs is None and ok and self._may("stairs", now):
            s = ok[-1]
            self.stairs = (s["x"], s["y"], surface_z)
            return self._do("stairs", now, ("dig_stairs", {"x": s["x"], "y": s["y"],
                                                           "z_top": surface_z, "z_bottom": surface_z - 1}))
        if self.stairs and "room" not in self.tries:
            # 7x3 with the stair at the west end: two 3x3 plots fit beside it (any 3x3 inside a 5x5
            # room centred on the stair would contain the stair, so no plot would fit)
            x, y, z = self.stairs
            return self._do("room", now, ("dig_room", {"x": x, "y": y - 1, "z": z - 1, "w": 7, "h": 3}))
        if len(farms) < self.FARMS and ug and self._may("farm_%d" % len(farms), now):
            return self._do("farm_%d" % len(farms), now, ("build_farm", dict(ug[0])))
        if farms and plugins.get("autofarm") != "on" and self._may("autofarm", now):
            return self._do("autofarm", now, ("enable_automation", {"name": "autofarm"}))

        # 5. peacetime defence setup (squad off duty, shelter burrow), then let the fortress work
        d = self._defence_setup(obs, now)
        if d:
            return d
        return "advance_days", {"days": 1 if obs.get("dig_designations_pending", 0) or hostile else 3}


class Random:
    P_ADVANCE = 1 / 3     # without this a uniform choice advances 1 call in 9 and the decision cap ends play early
    # create_burrow and civilian_alert are left out (refs 1, 2026-10-10): a random alert with a random 1-100 tile
    # Shelter burrow, turned off only by chance, confines civilians away from drink and food, so random killed the
    # fort it was meant to sit just above (3/3 start-year runs lost 3-11 dwarves to thirst with drink in stock;
    # runs/validation-2026-10-10). Random is a floor near noop, not a fort killer (CONTRIBUTING.md, Reference arms).
    TOOLS = ("appoint_manager", "build_workshop", "build_farm", "add_order", "cancel_order", "enable_automation",
             "dig_room", "dig_stairs", "create_squad", "equip_squad", "squad_order", "build_door", "lock_door")

    def __init__(self, seed=0):
        self.rng = random.Random(seed)

    def __call__(self, obs):
        import harness2 as H2   # local: keeps this module importable without the DF install
        r = self.rng
        m = obs.get("map") if isinstance(obs.get("map"), dict) else {}
        w = m.get("wagon") or {"x": 97, "y": 96, "z": 106}
        if r.random() < self.P_ADVANCE:
            return "advance_days", {"days": r.randint(1, 7)}
        name = r.choice(self.TOOLS)
        near = lambda c, d=20: max(0, c + r.randint(-d, d))
        if name == "build_workshop":
            sites = m.get("free_3x3_sites_near_wagon") or [{"x": near(w["x"]), "y": near(w["y"]), "z": w["z"]}]
            return name, {"type": r.choice(sorted(H2.WORKSHOPS)), **r.choice(sites)}
        if name == "build_farm":
            sites = (m.get("underground_soil_farm_sites") or []) + (m.get("surface_soil_sites_NOT_for_starting_seeds") or [])
            return name, dict(r.choice(sites)) if sites else {"x": near(w["x"]), "y": near(w["y"]), "z": w["z"]}
        if name == "add_order":
            return name, {"recipe": r.choice(sorted(H2.RECIPES)), "amount": r.randint(1, 10)}
        if name == "cancel_order":
            orders = obs.get("orders") or []
            return name, {"order_id": r.choice(orders)["id"] if orders else 0}
        if name == "enable_automation":
            return name, {"name": r.choice(sorted(H2.AUTOMATION))}
        if name == "dig_room":
            return name, {"x": near(w["x"]), "y": near(w["y"]), "z": w["z"] - r.randint(0, 3),
                          "w": r.randint(1, 10), "h": r.randint(1, 10)}
        if name == "dig_stairs":
            return name, {"x": near(w["x"]), "y": near(w["y"]), "z_top": w["z"], "z_bottom": w["z"] - r.randint(1, 3)}
        if name == "create_squad":
            return name, {"size": r.randint(1, 10)}
        if name == "equip_squad":
            return name, {"uniform": r.choice(["weapon_only", "leather", "metal"])}
        if name == "squad_order":
            order = r.choice(["attack", "station", "stand_down"])
            return name, ({"order": order, "x": near(w["x"]), "y": near(w["y"]), "z": w["z"] - r.randint(0, 1)}
                          if order == "station" else {"order": order})
        if name == "build_door":
            ents = m.get("surface_entrances") or []
            if ents and r.random() < 0.5:
                e = r.choice(ents)
                return name, {"kind": "hatch", "x": e["x"], "y": e["y"], "z": e["z"]}
            return name, {"kind": r.choice(["door", "hatch"]), "x": near(w["x"]), "y": near(w["y"]), "z": w["z"]}
        if name == "lock_door":
            return name, {"locked": r.random() < 0.5}
        return name, {}


class Automation:
    """DFHack's own automation, set up once and then lightly managed (research/automation-arm.md).
    Setup and layout go through automation/commands.py (control-panel, orders import, quickfort), not the LLM
    tool API; the policy returns harness2 tool calls only for what the tool API already covers (appointing the
    manager, one-off orders, advancing time). Each call runs the layout steps whose prerequisites hold. drain() returns the
    DFHack commands it ran since the last call, for the step log."""
    RETRY_DAYS = 3
    MAX_TRIES = 4
    DORM_BEDS = 22         # beds per dormitory in yukon-automation.csv
    REACT_DAYS = 5         # minimum gap between repeats of the same reaction
    DIG_GIVE_UP = 25
    KEY_PROFESSIONS = ("Miner", "Woodworker", "Carpenter", "Planter", "Farmer")

    def __init__(self, seed=0):
        self.tries, self.last, self.done, self.log = {}, {}, set(), []
        self.stair = None
        self.pop0 = None

    def drain(self):
        log, self.log = self.log, []
        return log

    def _may(self, key, now, days=None):
        if self.tries.get(key, 0) >= self.MAX_TRIES:
            return False
        return now - self.last.get(key, -10 ** 9) >= (days or self.RETRY_DAYS) * DAY

    def _mark(self, key, now):
        self.tries[key] = self.tries.get(key, 0) + 1
        self.last[key] = now

    def _qf(self, key, now, name, x, y, z, *extra, **kw):
        """One quickfort step; marked done on success, retried (up to MAX_TRIES) on failure."""
        from automation import commands as C
        self._mark(key, now)
        ok, res = C.quickfort(name, x, y, z, *extra, **kw)
        self.log.append(f"quickfort {kw.get('command', 'run')} {kw.get('blueprint', C.BLUEPRINT)} {name} "
                        f"@{x},{y},{z}: {'ok' if ok else 'FAILED'} {res}"[:300])
        if ok:
            self.done.add(key)
        return ok

    def _stale(self, key, now):
        """A designation that is still not dug after DIG_GIVE_UP days (an undiggable tile, a lost miner): build
        on what is dug rather than wait forever; quickfort skips tiles that aren't floor."""
        return now - self.last.get(key, now) > self.DIG_GIVE_UP * DAY

    def _dug(self, x, y, z, w, h):
        from automation import commands as C
        r = C.query("undug", x, y, z, w, h)
        return r.get("ok") and r.get("undug") == 0

    def _layout_step(self, obs, now):
        """Run the blueprint steps whose prerequisites hold. Returns True if it ran any."""
        m = obs.get("map") or {}
        w = m.get("wagon") or {"x": 97, "y": 96, "z": 106}
        sites = m.get("free_3x3_sites_near_wagon") or []
        citizens = len(obs.get("dwarves") or [])
        steps = [("workshops", lambda: True,                           # carpenter, mechanic, mason, craftsdwarf
                  lambda k: self._qf(k, now, "/workshops", w["x"], w["y"], w["z"], blueprint="library/embark.csv")),
]
        steps.append(("dig", lambda: True, lambda k: self._dig(k, now)))
        for ws in ("still", "kitchen"):     # one per call, on a free site read after earlier placements
            steps.append((ws, lambda: bool(sites),
                          lambda k, ws=ws: self._qf(k, now, "/" + ws, sites[0]["x"], sites[0]["y"], sites[0]["z"])))
        # embark stockpiles (top-left 7 W, 3 S of the wagon centre: south of the workshops) wait until the rooms
        # are furnished: placed at once, every dwarf (the miner too) spends the first weeks hauling the wagon out
        steps.append(("stockpiles", lambda: "rooms" in self.done,
                      lambda k: self._qf(k, now, "/stockpiles", w["x"] - 7, w["y"] + 3, w["z"], blueprint="library/embark.csv")))
        # library/basic standing orders after the first migrant wave, as Dreamfort's checklist says
        steps.append(("basic_orders", lambda: citizens > self.pop0, lambda k: self._orders(k, now, "library/basic")))
        if self.stair:
            x, y, z = self.stair
            steps += [
                ("farm_build", lambda: self._dug(x + 1, y - 1, z - 1, 11, 3) or self._stale("dig", now),
                 lambda k: self._qf(k, now, "/farm_build", x, y, z - 1)),
                ("rooms", lambda: (self._dug(x + 1, y - 1, z - 2, 11, 3) and self._dug(x - 5, y - 1, z - 2, 5, 3))
                 or self._stale("dig", now),
                 lambda k: self._rooms(k, now, "rooms", z - 2)),
                ("dorm2_dig", lambda: "rooms" in self.done and citizens >= self.DORM_BEDS - 4,
                 lambda k: self._qf(k, now, "/dorm2_dig", x, y, z - 3)),
                ("dorm2", lambda: "dorm2_dig" in self.done and (self._dug(x + 1, y - 1, z - 3, 11, 3) or self._stale("dorm2_dig", now)),
                 lambda k: self._rooms(k, now, "dorm2", z - 3)),
            ]
        ran = False
        for key, ready, do in steps:
            if key in self.done or not self._may(key, now):
                continue
            if key in ("still", "kitchen") and ran:
                break                       # its free site was read before this call's placements
            if ready():
                do(key)
                ran = True
                if key in ("still", "kitchen"):
                    break
        return ran

    def _orders(self, key, now, name):
        from automation import commands as C
        self._mark(key, now)
        self.log.append(C.import_orders(name))
        self.done.add(key)
        return True

    def _dig(self, key, now):
        from automation import commands as C
        r = C.query("stair_site")
        self._mark(key, now)
        if not r.get("ok"):
            self.log.append(f"stair_site: {r.get('error')}")
            return False
        s = r["site"]
        x, y, z = s["x"], s["y"], s["z"]
        # farm level first (priority 3), then the rooms (default 4); the stair column at each level
        ok = (self._qf("dig_top", now, "/stair_top", x, y, z, "-p", "3")
              and self._qf("dig_farm", now, "/farm_dig", x, y, z - 1, "-p", "3")
              and self._qf("dig_rooms", now, "/rooms_dig", x, y, z - 2))
        if ok:
            self.stair = (x, y, z)
            self.done.add(key)
        return ok

    def _rooms(self, key, now, prefix, z):
        """Furniture orders for the blueprint (quickfort's own `orders` command), then the planned furniture
        (buildingplan waits for the items) and the zones."""
        x, y, _ = self.stair
        for sub, mode in (("_orders", "orders"), ("_build", "run")):
            if key + sub not in self.done and not self._qf(key + sub, now, f"/{prefix}_build", x, y, z, command=mode):
                return False
        if self._qf(key + "_zone", now, f"/{prefix}_zone", x, y, z):
            self.done.add(key)
            return True
        return False

    def __call__(self, obs):
        now = (obs.get("date") or {}).get("abs_tick", 0)
        st, adm = obs.get("stocks") or {}, obs.get("administrators") or {}
        if not isinstance(st, dict):
            return "advance_days", {"days": 1}
        if "setup" not in self.done:
            from automation import commands as C
            self.pop0 = len(obs.get("dwarves") or [])
            self.log += C.setup()
            self.done.add("setup")
        if not adm.get("manager_active_for_orders") and self._may("manager", now):
            self._mark("manager", now)
            # the manager spends time on ManageWorkOrders (prioritized): don't take the only miner or woodworker
            free = [d for d in obs.get("dwarves") or [] if not d.get("positions")]
            spare = [d for d in free if not any(p in (d.get("profession") or "") for p in self.KEY_PROFESSIONS)]
            pick = (spare or free or [{}])[0].get("id")
            return "appoint_manager", ({"dwarf_id": pick} if pick is not None else {})
        o = manager_office_step(obs, lambda k: self._may(k, now) and (self._mark(k, now) or True))
        if o:
            return o
        if self._layout_step(obs, now):
            return "advance_days", {"days": 1}

        # light reactions to obvious states; the standing orders do the routine work
        citizens = len(obs.get("dwarves") or [])
        built = {w.get("type"): w for w in obs.get("workshops") or [] if w.get("built")}
        drink, plants, barrels = st.get("drink", 0), st.get("plants_brewable", 0), st.get("barrels_empty", 0)
        # the standing brew order (automation/standing-orders.json) needs >= 5 plants; below that, brew what there is
        if "Still" in built and drink < 5 * citizens and plants > 0 and self._may("brew", now, self.REACT_DAYS):
            if barrels > 0:
                self._mark("brew", now); self.tries["brew"] = 0
                return "add_order", {"recipe": "brew_drink", "amount": max(1, min(5, plants, barrels))}
            if "Carpenters" in built and st.get("logs_usable", 0) > 0 and self._may("barrel", now, self.REACT_DAYS):
                self._mark("barrel", now); self.tries["barrel"] = 0
                return "add_order", {"recipe": "make_barrel", "amount": 3}
        # migrants beyond the planned dormitory beds: loose beds until the next dormitory is dug
        # (each dormitory's own `quickfort orders` covers its 22 beds)
        planned = self.DORM_BEDS * (("rooms" in self.done) + ("dorm2" in self.done))
        if (planned and citizens > planned and "Carpenters" in built and st.get("beds", 0) < citizens
                and self._may("beds", now, self.REACT_DAYS)):
            self._mark("beds", now); self.tries["beds"] = 0
            return "add_order", {"recipe": "make_bed", "amount": min(5, citizens - st.get("beds", 0))}
        # idle carpenter with plenty of wood: a little more furniture than the standing stock levels ask for
        car = built.get("Carpenters")
        if car and not car.get("jobs") and st.get("logs_usable", 0) >= 50 and self._may("furniture", now, 7):
            self._mark("furniture", now); self.tries["furniture"] = 0
            return "add_order", {"recipe": ("make_table", "make_chair", "make_door")[now // DAY % 3], "amount": 2}
        return "advance_days", {"days": 1 if obs.get("dig_designations_pending", 0) else 3}


# --- lab tasks (BENCHMARK-v1 §2): task witnesses -----------------------------------------------------------------------
# Withheld from the public release while a season is running: a task's witness is a policy that solves it, which
# would hand competitors a solution. Witness scores and strategy notes are published; the code is released when the
# season closes. bench/labrun.py --only witness needs them.
WITNESSES = {}
