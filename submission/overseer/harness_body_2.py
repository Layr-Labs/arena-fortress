"""Overseer class body, part 2 of 4. Not a module of its own: harness.py executes this file inside `class Overseer`, with harness.py's globals, after part 1."""
def food_slope(self):
    pts = [(r[0], r[1]) for r in self.food_hist
           if isinstance(r[0], (int, float)) and isinstance(r[1], (int, float))]
    if len(pts) < 3:
        return None
    n = len(pts)
    mean_x = sum(x for x, _ in pts) / n
    mean_y = sum(y for _, y in pts) / n
    var = sum((x - mean_x) ** 2 for x, _ in pts)
    if var <= 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in pts) / var
def food_cover(self):
    s = self.food_slope()
    if s is None or s >= 0:
        return None
    return (self.st.get("food_edible") or 0) / -s
def food_alarm(self):
    if self.days < 180 or self.caravan_settling():
        return False
    cover = self.food_cover()
    return cover is not None and cover < FOOD_ALARM_DAYS
def food_security(self):
    cover = self.food_cover()
    drink_days, food_days = self.leg_days()
    drink_short = drink_days < min(food_days, ALLOC_SHORT_DAYS)
    oid = self.key_order.get("o_cook_food")
    mine_on_book = oid is not None and oid in self.owned and any(x.get("id") == oid for x in self.orders)
    if mine_on_book:
        cur = next(x for x in self.orders if x.get("id") == oid)
        floored = any(k == ("PLANT", "DRINK_MAT") and t == "AtLeast" for k, t, _ in when_sig(cur.get("when")))
        if floored != drink_short and "when" in cur:
            r = self.act("o_cook_food_retire", "cancel_order", {"order_id": oid}, retry=4, limit=8)
            if r is not None and r.get("ok"):
                log("cook_food_recut", day=self.day, order=oid, floored=floored, drink_short=drink_short,
                    drink_days=round(drink_days), food_days=round(food_days))
                self.done.discard("o_cook_food")
                return
    if cover is None or cover >= FOOD_ALARM_DAYS:
        oid = self.key_order.get("o_cook_food")
        if cover is not None and oid is not None and oid in self.owned and any(
                x.get("id") == oid for x in self.orders):
            self.act("o_cook_food_retire", "cancel_order", {"order_id": oid}, retry=4, limit=8)
            self.done.discard("o_cook_food")
        return
    if self.may("food_butcher", 1, 40):
        self.last["food_butcher"] = self.now
        self.butcher()
    have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
    mine = self.key_order.get("o_cook_food")
    if mine is not None and any(x.get("id") == mine for x in self.orders):
        return
    if "Kitchen" in have and not self.ordered_now("o_cook_food") and not any(
            x.get("recipe") == "cook_meal" and x.get("repeat") and x.get("active") is not False
            and not any(d(w).get("stock") == "plants_total"
                        or str(d(w).get("item_type") or "").upper() == "SEEDS" for w in lst(x.get("when")))
            for x in self.orders):
        when = [{"stock": "prepared_meals", "below": max(MEAL_CAP, 3 * self.cit)}]
        if drink_short:
            when.append({"stock": "plants_brewable", "at_least": self.hold_floor()})
        if self.hands_off is not None:
            tool, args = self.cook_order(when)
            self.cook_act("o_cook_food", tool, args, retry=2, limit=10)
        else:
            self.act("o_cook_food", "add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily",
                                                  "when": when}, retry=2, limit=10)
def perishable(self):
    s = self.st
    vals = [s.get(k) for k in ("food_edible", "prepared_meals", "plants_total")]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return 0
    return vals[0] - vals[1] - vals[2]
def lineage_spare(self):
    left = self.days_to_end()
    if (left is not None and left <= HOLD_GROW_DAYS) or self.harvest_closed():
        return True
    tiles, sown = self.plot_tiles()
    seeds = self.st.get("seeds")
    if not isinstance(seeds, (int, float)) or isinstance(seeds, bool) or tiles <= 0:
        return False
    return seeds - sown >= max(0, tiles - sown) + SEEDS_PER_PLOT
def meat_keep(self):
    if not self.alloc_on() or self.caravan_active or not isinstance(self.day, (int, float)):
        return
    have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
    if "Kitchen" not in have:
        return
    meat = self.perishable()
    if meat < MEAT_KEEP_MIN or self.own_pending("o_cook_meat"):
        return
    if self.meal_wait():
        log("meal_wait", day=self.day, source="o_cook_meat", perishable=meat, loose=d(self.plant_loose).get("loose"))
        return
    plants = self.st.get("plants_total") or 0
    cookable = [k for k, v in self.live_seeds_by_kind().items() if int(d(v).get("n") or 0) >= SEEDWATCH_TARGET]
    if cookable and (self.hold_cook() or not self.lineage_spare()):
        return
    n = min(MEAT_KEEP_MAX, max(1, meat // MEAT_KEEP_PER_JOB))
    r = self.act("o_cook_meat", "add_order", {"recipe": "cook_meal", "amount": n}, retry=1, limit=99)
    if r is not None and r.get("ok"):
        log("meat_keep", day=self.day, amount=n, perishable=meat, meals=self.st.get("prepared_meals"),
            plants=plants, seeds=self.st.get("seeds"))
def stock_sliding(self):
    if self.days < 180 or self.hands_off is not None or len(self.stock_hist) < SLOPE_MIN_PTS:
        return False
    drink = ols_slope([(p[0], p[1]) for p in self.stock_hist])
    food = ols_slope([(p[0], p[2]) for p in self.stock_hist])
    now = self.stock_hist[-1]
    hit = ((drink < 0 and now[1] / -drink < SLOPE_HORIZON)
           or (food < 0 and now[2] / -food < SLOPE_HORIZON))
    if self.caravan_settling():
        hit = False
    if hit != self.sliding:
        log("slide_alarm", on=hit, day=self.day, days_left=self.days_left, slope_drink=round(drink, 4),
            slope_food=round(food, 4), drink=now[1], food=now[2], meals=now[3])
        self.sliding = hit
    return hit
def plan(self):
    for f in (self.safe_state, self.stranded_survey, self.home_call_alert, self.mood, self.defend, self.wildlife_response, self.mark_guard,
              self.squad_hold, self.shaft_hatch, self.entrance_hatches, self.office_guard):
        try:
            f()
        except (ActionLimit, HandsOff, GameOver):
            raise
        except Exception as e:
            log("guard_step_error", step=f.__name__, error=repr(e)[:300])
    self.management()
    self.workshops()
    self.digging()
    self.carp_pause_step()
    self.farms()
    self.seed_census()
    self.plant_census()
    self.seed_guard()
    self.brew_shot_trim()
    self.supply()
    self.surge_start_brew()
    self.allocate_plants()
    self.rot_guard()
    self.seed_recycle()
    self.hold_supply()
    self.barrel_cancel()
    self.lean_supply()
    self.f_drink_lift()
    self.food_security()
    self.f_livestock()
    self.meat_keep()
    self.glut_bank()
    self.winter_plan()
    self.furnish()
    self.cup_supply()
    self.meeting_area()
    self.meeting_far()
    self.meeting_use()
    self.grazer_cull()
    self.stray_cull()
    self.stress_watch()
    self.stress_housing()
    self.house_everyone()
    self.patient_water()
    self.head_offices()
    self.rezone()
    self.progress()
    self.closer()
def management(self):
    if not self.adm.get("manager_active_for_orders"):
        free = [p for p in self.people if not p.get("positions") and p.get("adult", True)]
        free.sort(key=lambda p: -(p.get("organizer_skill") or 0))
        self.act("manager", "appoint_manager", {"dwarf_id": free[0]["id"]} if free else {}, retry=1, limit=8)
    plugins = d(self.o.get("plugins"))
    for name in ("autochop", "seedwatch"):
        if plugins.get(name) != "on":
            self.act("plug_" + name, "enable_automation", {"name": name}, retry=5)
    if self.o.get("farm_plots") and plugins.get("autofarm") != "on":
        self.act("plug_autofarm", "enable_automation", {"name": "autofarm"}, retry=5)
    self.office()
def office(self):
    if self.office_yield is not None:
        if self.office_shelter():
            self.office_yield = None
            return
        self.office_yield_move()
        return
    if not self.cit or not self.adm.get("manager_active_for_orders"):
        return
    small = self.cit < OFFICE_FULL_CIT
    if small and not self.my1_plan():
        return
    mo = self.adm.get("manager_office")
    mgr = self.adm.get("MANAGER_id")
    if self.office_release(mgr):
        return
    if self.office_shelter():
        return
    offices = self.zone("office")
    mine = next((z for z in offices if mgr is not None and z.get("owner") == mgr), None)
    if isinstance(mo, dict) and mo.get("chair"):
        if mine is not None and (not small or self.dug_rooms("office")):
            self.office_move(mine, mgr)
        return
    if not mine:
        spare = next((z for z in offices if z.get("owner") is None and z.get("id") not in self.head_zones), None)
        if spare and mgr is not None:
            if self.office_beasts(spare):
                return
            self.act("office_assign", "assign_zone", {"zone_id": spare["id"], "dwarf_id": mgr})
            return
        spare_dine = self.dug_rooms("dine") if self.zone("dining") else []
        closed = [s for s in self.closed_a() if self.area_fits(s, ZONE_MAX) and not self.site_open(s)]
        if small:
            closed = [s for s in closed if self.site_open(s) == 0]
        if small and self.shaft_people():
            closed.sort(key=lambda s: bool(self.shaft_near(self.site_box(s, ZONE_MAX))))
        room = next(iter(self.dug_rooms("office") + closed + spare_dine), None)
        if room:
            result = self.act("office_zone", "make_zone", {"kind": "office", "site": room["id"]})
            if result and result.get("ok") and (self.free.get("chair") or 0) > 0:
                self.act("office_chair", "place_furniture", {"kind": "chair", "site": room["id"]})
            zid = d(d(result).get("result")).get("zone_id") if result and result.get("ok") else None
            if zid is not None and mgr is not None:
                at = lst(d(d(result).get("result")).get("at"))
                box = dict(zip(("x", "y", "z", "w", "h"), at)) if len(at) >= 5 else \
                    {k: room.get(k) for k in ("x", "y", "z", "w", "h")}
                if not self.office_beasts(box):
                    self.act("office_assign", "assign_zone", {"zone_id": zid, "dwarf_id": mgr})
        elif not small and self.office_temp_small(mgr):
            pass
        else:
            self.office_box(ready_only=small)
        return
    if (not small or self.dug_rooms("office")) and self.office_move(mine, mgr):
        return
    if d(mine.get("furniture")).get("chair") or d(mine.get("furniture_planned")).get("chair"):
        return
    if (self.free.get("chair") or 0) > 0:
        room = next((s for s in self.sites if s.get("kind") in "RA" and s.get("z") == mine.get("z")
                     and s.get("x") == mine.get("x") and s.get("y") == mine.get("y")
                     and self.area_fits(s, PLACE_MAX)), None)
        room = room or next(iter(self.dug_rooms("office")
                                 + [s for s in self.closed_a() if self.area_fits(s, PLACE_MAX)]), None)
        if room:
            temp = not small and room.get("kind") == "A" and bool(self.site_open(room))
            self.act("office_temp_chair" if temp else "office_chair", "place_furniture",
                     {"kind": "chair", "site": room["id"]})
def shelter_office_rooms(self):
    out = []
    for sid, b in sorted(self.shelter_boxes.items(), key=lambda kv: str(kv[0])):
        if sid in self.shelter_level_in or sid in self.office_shelter_tried \
                or not (isinstance(b, tuple) and len(b) == 5):
            continue
        s = next((x for x in self.sites if isinstance(x, dict) and x.get("id") == sid), None)
        if s is None or s.get("kind") not in ("A", "R") or (s.get("x"), s.get("y"), s.get("z")) != (b[0], b[1], b[4]):
            continue
        w, h = b[2] - b[0] + 1, b[3] - b[1] + 1
        if not (1 <= w <= PLACE_MAX and 1 <= h <= PLACE_MAX):
            continue
        if self.level_open((b[0], b[1], b[4], w, h)) != 0:
            continue
        out.append((s, b))
    return out
def in_shelter_box(self, zone):
    if not self._ints(zone, ("x", "y", "z")):
        return False
    return any(isinstance(b, tuple) and len(b) == 5 and sid not in self.shelter_level_in and b[4] == zone["z"]
               and b[0] <= zone["x"] <= b[2] and b[1] <= zone["y"] <= b[3]
               for sid, b in self.shelter_boxes.items())
def office_shelter(self):
    mgr = self.adm.get("MANAGER_id")
    if mgr is None or not self.adm.get("manager_active_for_orders") or not self.cit:
        return False
    if self.cit < OFFICE_FULL_CIT and not self.my1_plan():
        return False
    owned = [z for z in self.zone("office") if z.get("owner") == mgr and z.get("id") is not None]
    if any(self.in_shelter_box(z) for z in owned):
        return False
    if (self.free.get("chair") or 0) <= 0:
        return False
    rooms = [(s, b) for s, b in self.shelter_office_rooms()
             if not self.office_beasts({"x": b[0], "y": b[1], "z": b[4], "w": b[2] - b[0] + 1, "h": b[3] - b[1] + 1})]
    if not rooms:
        return False
    s, b = rooms[0]
    x1, y1, z = b[0], b[1], b[4]
    built = [d(f) for f in lst(self.o.get("furniture")) if d(f).get("built") is not False]
    if any(f.get("x") == x1 and f.get("y") == y1 and f.get("z") == z for f in built):
        self.office_shelter_tried.add(s["id"])
        log("office_shelter_skip", day=self.day, site=s["id"], why="corner_taken")
        return False
    self.office_shelter_tried.add(s["id"])
    r = self.act("office_shelter_chair", "place_furniture",
                 {"kind": "chair", "site": s["id"], "w": b[2] - x1 + 1, "h": b[3] - y1 + 1}, retry=1, limit=4)
    at = d(r.get("result")).get("at") if r and r.get("ok") else None
    if isinstance(at, list) and at and isinstance(at[0], list):
        at = at[0]
    if not (isinstance(at, list) and len(at) == 3 and all(isinstance(v, int) and not isinstance(v, bool)
                                                           for v in at)):
        return r is not None
    w, h = at[0] - x1 + 1, at[1] - y1 + 1
    inside = lambda f: x1 <= (f.get("x") if isinstance(f.get("x"), int) else -1) <= at[0] \
        and y1 <= (f.get("y") if isinstance(f.get("y"), int) else -1) <= at[1] and f.get("z") == z
    if not (1 <= w <= ZONE_MAX and 1 <= h <= ZONE_MAX) or at[2] != z or any(inside(f) for f in built):
        log("office_shelter_skip", day=self.day, site=s["id"], why="chair_far", at=at)
        return True
    zr = self.act("office_shelter_zone", "make_zone", {"kind": "office", "site": s["id"], "w": w, "h": h},
                  retry=1, limit=4)
    zid = d(d(zr).get("result")).get("zone_id") if zr and zr.get("ok") else None
    if zid is None:
        return True
    a = self.act("office_shelter_assign", "assign_zone", {"zone_id": zid, "dwarf_id": mgr}, retry=0.25, limit=10)
    ok = bool(a and a.get("ok"))
    log("office_shelter", day=self.day, site=s["id"], zone=zid, at=at, w=w, h=h, ok=ok,
        old=[z.get("id") for z in owned])
    if ok:
        holder = self.office_holder(mgr)
        for z in owned:
            if holder is not None and z.get("id") != zid:
                rr = self.act("office_release_%s" % z["id"], "assign_zone",
                              {"zone_id": z["id"], "dwarf_id": holder}, retry=1, limit=6)
                log("office_release", day=self.day, zone=z["id"], holder=holder, manager=mgr,
                    ok=bool(rr and rr.get("ok")))
    return True
def office_temp_small(self, mgr):
    wide = [x for x in self.kind("A") + self.dug_rooms()
            if not self.area_fits(x, ZONE_MAX) and self.area_fits(x, PLACE_MAX)]
    if wide:
        return False
    site = next((x for x in self.kind("A") if self.area_fits(x, ZONE_MAX) and self.site_open(x)), None)
    if site is None:
        return False
    self.office_room()
    r = self.act("office_temp_zone", "make_zone", {"kind": "office", "site": site["id"]}, retry=2, limit=4)
    if not (r and r.get("ok")):
        return r is not None
    if self.may("office_temp_log", 5, 10 ** 6):
        self.last["office_temp_log"] = self.now
        log("office_temp", day=self.day, site=site["id"], small=True)
    if (self.free.get("chair") or 0) > 0:
        self.act("office_temp_chair", "place_furniture", {"kind": "chair", "site": site["id"]})
    zid = d(d(r).get("result")).get("zone_id")
    if zid is not None and mgr is not None:
        at = lst(d(d(r).get("result")).get("at"))
        box = dict(zip(("x", "y", "z", "w", "h"), at)) if len(at) >= 5 else \
            {k: site.get(k) for k in ("x", "y", "z", "w", "h")}
        if not self.office_beasts(box):
            self.act("office_assign", "assign_zone", {"zone_id": zid, "dwarf_id": mgr})
    return True
def call_box(self, args):
    sid = args.get("site")
    s = next((x for x in getattr(self, "sites", None) or [] if isinstance(x, dict) and x.get("id") == sid), None)
    num = lambda v: isinstance(v, int) and not isinstance(v, bool)
    if s is None or not all(num(s.get(k)) for k in ("x", "y", "z")):
        return None
    w = args.get("w") if num(args.get("w")) else (s.get("w") if num(s.get("w")) else 1)
    h = args.get("h") if num(args.get("h")) else (s.get("h") if num(s.get("h")) else 1)
    return (s["x"], s["y"], s["z"], max(1, w), max(1, h))
def box_open(self, box):
    if box is None:
        return None
    today = self.obs_day()
    hit = self.open_maps.get(box)
    if hit is not None and isinstance(today, (int, float)) and isinstance(hit[0], (int, float)) \
            and today - hit[0] < OPEN_PROBE_DAYS:
        return hit[1]
    x0, y0, z, w, h = box
    n = None
    try:
        r = self.game.query("map", x=min(400, max(0, x0 + (w - 1) // 2)), y=min(400, max(0, y0 + (h - 1) // 2)),
                            z=z, z2=z, radius=min(20, max(w, h) // 2 + 1))
        res = query_result(r)
    except Exception as e:
        log("box_open_error", box=list(box), error=repr(e)[:160])
        res = None
    if isinstance(res, dict) and isinstance(res.get("x1"), int) and isinstance(res.get("y1"), int):
        lv = next((d(v) for v in lst(res.get("levels")) if d(v).get("z") == z), None)
        if lv is not None and isinstance(lv.get("shape"), list) and isinstance(lv.get("light"), list):
            n = 0
            for i, (row, lrow) in enumerate(zip(lv["shape"], lv["light"])):
                ty = res["y1"] + i
                if not (y0 <= ty < y0 + h) or not isinstance(row, str) or not isinstance(lrow, str):
                    continue
                for j, (ch, li) in enumerate(zip(row, lrow)):
                    if x0 <= res["x1"] + j < x0 + w and ch in OPEN_WALK and li == "o":
                        n += 1
    self.open_maps[box] = (today, n)
    return n
def site_open(self, s, args=None):
    if not isinstance(s, dict) or s.get("id") is None:
        return None
    return self.box_open(self.call_box(dict(d(args), site=s["id"])))
def beasts_near(self, zone, tiles, levels):
    return [u for u in self.office_beasts(zone, ((tiles, levels),))]
def office_beasts(self, zone, rules=None):
    rules = rules or ((OFFICE_BEAST_TILES, WILD_NEAR_Z), (OFFICE_BEAST_LEVEL_TILES, 1))
    num = lambda v: isinstance(v, int) and not isinstance(v, bool)
    if not all(num(zone.get(k)) for k in ("x", "y", "z")):
        return []
    x1, y1, oz = zone["x"], zone["y"], zone["z"]
    x2 = x1 + max(1, zone["w"] if num(zone.get("w")) else 1) - 1
    y2 = y1 + max(1, zone["h"] if num(zone.get("h")) else 1) - 1
    out = []
    for u in self.others():
        if not big_race(u.get("race")) or not self.mark_of(u) or not all(num(u.get(k)) for k in ("x", "y", "z")):
            continue
        tiles = max(x1 - u["x"], u["x"] - x2, y1 - u["y"], u["y"] - y2, 0)
        dz = abs(u["z"] - oz)
        if any(tiles <= t and dz <= lv for t, lv in rules):
            out.append((str(u.get("race")), u["x"], u["y"], u["z"], tiles))
    return out
def office_holder(self, mgr):
    for p in sorted(self.people, key=lambda p: p.get("id") if isinstance(p.get("id"), int) else 10 ** 9):
        if isinstance(p.get("id"), int) and p["id"] != mgr and not p.get("positions") and p.get("adult", True):
            return p["id"]
    return None
def office_guard(self):
    mgr = self.adm.get("MANAGER_id")
    y = self.office_yield
    if y is not None:
        zone = next((z for z in self.zone("office") if z.get("id") == y["zone"]), None)
        if zone is None:
            log("office_yield_end", day=self.day, zone=y["zone"], why="zone_gone")
            self.office_yield = None
            return
        near = self.office_beasts(zone)
        if near:
            y["clear"] = None
            if zone.get("owner") == mgr and mgr is not None:
                holder = self.office_holder(mgr)
                if holder is not None:
                    r = self.act("office_yield", "assign_zone", {"zone_id": zone["id"], "dwarf_id": holder},
                                 retry=0.25, limit=10 ** 6)
                    if r and r.get("ok"):
                        y["holder"] = holder
                        log("office_yield", day=self.day, zone=zone["id"], holder=holder, near=near[:3],
                            again=True)
            return
        if y.get("clear") is None:
            y["clear"] = self.now
        if self.now - y["clear"] < OFFICE_CLEAR_DAYS * DAY:
            return
        if mgr is None:
            return
        r = self.act("office_return", "assign_zone", {"zone_id": zone["id"], "dwarf_id": mgr},
                     retry=0.25, limit=10 ** 6)
        if r and r.get("ok"):
            log("office_return", day=self.day, zone=zone["id"], manager=mgr,
                days=round((self.now - y["since"]) / DAY, 2))
            self.office_yield = None
        return
    if mgr is None:
        return
    zone = next((z for z in self.zone("office") if z.get("owner") == mgr), None)
    if zone is None:
        return
    near = self.office_beasts(zone)
    if not near:
        return
    holder = self.office_holder(mgr)
    if holder is None:
        if self.may("office_yield_none", 1, 10 ** 6):
            self.last["office_yield_none"] = self.now
            log("office_yield_none", day=self.day, zone=zone.get("id"), near=near[:3])
        return
    r = self.act("office_yield", "assign_zone", {"zone_id": zone["id"], "dwarf_id": holder},
                 retry=0.25, limit=10 ** 6)
    if r and r.get("ok"):
        self.office_yield = {"zone": zone["id"], "holder": holder, "since": self.now, "clear": None}
        log("office_yield", day=self.day, zone=zone["id"], holder=holder, manager=mgr, near=near[:3])
def office_open(self, zone):
    if not self._ints(zone, ("x", "y", "z")):
        return None
    box = (zone["x"], zone["y"], zone["z"], zone.get("w") or 1, zone.get("h") or 1)
    n = self.box_open(box)
    if n:
        return n
    lv = self.level_open(box)
    return lv if lv else n
def office_on_room(self, zone):
    if not self._ints(zone, ("x", "y", "z")):
        return False
    for r in self.kind("R"):
        if self.roles.get(r.get("id")) != "office" or not self._ints(r, ("x", "y", "z")):
            continue
        b = self.room_box.get(r["id"])
        b = b if isinstance(b, dict) and self._ints(b, ("x", "y", "z")) else r
        if b["z"] == zone["z"] and b["x"] <= zone["x"] < b["x"] + (b.get("w") or 3) \
                and b["y"] <= zone["y"] < b["y"] + (b.get("h") or 3):
            return True
    return False
def office_settled(self, zone):
    return self.office_open(zone) == 0 or self.office_on_room(zone)
def office_move(self, mine, mgr):
    if mgr is None or not self.office_open(mine) or self.office_on_room(mine):
        return False
    room = next(iter(self.dug_rooms("office")), None)
    if room is None:
        self.office_room()
        return False
    if OFFICE_CHAIR_FIRST and (self.free.get("chair") or 0) <= 0 and not self.room_chair(room):
        if self.may("office_move_wait_log", 2, 10 ** 6):
            self.last["office_move_wait_log"] = self.now
            log("office_move_wait", day=self.day, site=room["id"], old=mine.get("id"), why="no_chair")
        return False
    r = self.act("office_move_zone", "make_zone", {"kind": "office", "site": room["id"]}, retry=2, limit=4)
    zid = d(r.get("result")).get("zone_id") if r and r.get("ok") else None
    if zid is None:
        return r is not None
    a = self.act("office_move_assign", "assign_zone", {"zone_id": zid, "dwarf_id": mgr}, retry=0.5, limit=6)
    if (self.free.get("chair") or 0) > 0:
        c = self.act("office_move_chair", "place_furniture", {"kind": "chair", "site": room["id"]}, retry=2, limit=4)
        if c and c.get("ok"):
            self.office_chair_zones = getattr(self, "office_chair_zones", set()) | {zid}
    elif self.room_chair(room):
        self.office_chair_zones = getattr(self, "office_chair_zones", set()) | {zid}
    log("office_move", day=self.day, site=room["id"], zone=zid, old=mine.get("id"), ok=bool(a and a.get("ok")))
    if a and a.get("ok"):
        self.office_release(mgr)
    return True
def office_yield_move(self):
    mgr = self.adm.get("MANAGER_id")
    if mgr is None or not self.adm.get("manager_active_for_orders") or self.zone_of("office", mgr) is not None:
        return False
    cands = self.dug_rooms("office") + [s_ for s_ in self.closed_a() if self.area_fits(s_, ZONE_MAX)
                                        and self.site_open(s_) == 0]
    room = next((s_ for s_ in cands if self._ints(s_, ("x", "y", "z")) and not self.site_level_open(s_)
                 and not self.office_beasts({k: s_.get(k) for k in ("x", "y", "z", "w", "h")})), None)
    if room is None:
        return False
    r = self.act("office_yield_zone", "make_zone", {"kind": "office", "site": room["id"]}, retry=1, limit=6)
    zid = d(d(r).get("result")).get("zone_id") if r and r.get("ok") else None
    if zid is None:
        return r is not None
    a = self.act("office_yield_assign", "assign_zone", {"zone_id": zid, "dwarf_id": mgr}, retry=0.25, limit=10)
    if (self.free.get("chair") or 0) > 0:
        self.act("office_yield_chair", "place_furniture", {"kind": "chair", "site": room["id"]}, retry=1, limit=6)
    ok = bool(a and a.get("ok"))
    log("office_yield_move", day=self.day, site=room["id"], zone=zid, old=(self.office_yield or {}).get("zone"),
        ok=ok)
    if ok:
        self.office_yield = None
    return True
def office_release(self, mgr):
    if mgr is None:
        return False
    owned = [z for z in self.zone("office") if z.get("owner") == mgr and z.get("id") is not None]
    if len(owned) < 2 or not any(self.office_settled(z) for z in owned):
        return False
    if OFFICE_CHAIR_FIRST and not any(self.office_settled(z) and self.office_chaired(z) for z in owned) \
            and any(self.office_chaired(z) for z in owned):
        if self.may("office_release_hold_log", 2, 10 ** 6):
            self.last["office_release_hold_log"] = self.now
            log("office_release_hold", day=self.day, owned=[z.get("id") for z in owned], why="no_chair")
        return False
    holder = self.office_holder(mgr)
    acted = False
    for z in owned:
        if self.office_settled(z) or not self.office_open(z) or holder is None:
            continue
        r = self.act("office_release_%s" % z["id"], "assign_zone", {"zone_id": z["id"], "dwarf_id": holder},
                     retry=1, limit=6)
        if r is not None:
            acted = True
            log("office_release", day=self.day, zone=z["id"], holder=holder, manager=mgr, ok=bool(r.get("ok")))
    return acted
def office_chaired(self, zone):
    return bool(d(d(zone).get("furniture")).get("chair") or d(d(zone).get("furniture_planned")).get("chair")
                or d(zone).get("id") in getattr(self, "office_chair_zones", ()))
def room_chair(self, room):
    b = self.room_box.get(room.get("id"))
    b = b if isinstance(b, dict) and self._ints(b, ("x", "y", "z")) else room
    if not self._ints(b, ("x", "y", "z")):
        return False
    w, h = b.get("w") or 3, b.get("h") or 3
    return any(d(f).get("kind") == "chair" and d(f).get("built") is not False and d(f).get("z") == b["z"]
               and isinstance(d(f).get("x"), int) and isinstance(d(f).get("y"), int)
               and b["x"] <= d(f)["x"] < b["x"] + w and b["y"] <= d(f)["y"] < b["y"] + h
               for f in lst(self.o.get("furniture")))
def office_wants_room(self):
    if "office" in self.roles.values() or (self.cit or 0) < OFFICE_FULL_CIT \
            or not self.adm.get("manager_active_for_orders"):
        return False
    mgr = self.adm.get("MANAGER_id")
    mine = next((z for z in self.zone("office") if mgr is not None and z.get("owner") == mgr), None)
    if mine is not None and self.office_settled(mine):
        return False
    if self.shelter_office_rooms():
        return False
    return not self.dug_rooms("office") and not any(self.site_open(a) == 0 and self.area_fits(a, ZONE_MAX)
                                                     for a in self.kind("A"))
def office_room(self):
    if "office" in self.roles.values() or "dorm" not in self.roles.values():
        return
    spare = [r for r in self.undug_rooms() if r["id"] not in self.roles and self.dry(r.get("z"))
             and not self.room_taken(r)]
    r = self.pick_dig_site(spare) if spare else None
    if r is None:
        return
    size = {"w": SURGE_FLOOR_ROOM[0], "h": SURGE_FLOOR_ROOM[1]} if self.surge else {}
    res = self.act("dig_office_room", "dig_room", {"site": r["id"], **size}, retry=2, limit=4)
    if res and res.get("ok"):
        self.roles[r["id"]] = "office"
        self.note_room_box(r, size)
        log("office_room", day=self.day, site=r["id"], **size)
def open_refusal(self, tool, args):
    try:
        args = d(args)
        sid = str(args.get("site") or "")
        if tool in OPEN_SITE_TOOLS and sid[:1] in (("A", "R") if tool == "create_burrow" else ("A",)):
            n = self.box_open(self.call_box({"site": args["site"]} if sid[:1] == "A" else args))
            if n:
                return "site %s holds %d walkable outside tile(s) (open ground, no roof): no Shelter, zone or " \
                       "furniture goes there; use a dug room" % (sid, n)
        if tool == "dig_stairs" and sid[:1] == "S":
            why = self.entrance_hold()
            if why:
                return why
            box = self.call_box({"site": args.get("site"), "w": 1, "h": 1})
            near = self.beasts_near(dict(zip(("x", "y", "z", "w", "h"), box)), WILD_NEAR_TILES, WILD_NEAR_Z) \
                if box else []
            if near:
                return "a big beast (%s) is within %d tiles of stair site %s on the surface" % (
                    near[0][0].lower(), WILD_NEAR_TILES, sid)
    except Exception as e:
        log("open_refusal_error", error=repr(e)[:160])
    return None
def closed_a(self):
    inside = [x for x in self.kind("A") if not self.site_open(x)]
    shut = [x for x in inside if not self.site_level_open(x)]
    rest = [x for x in inside if x not in shut]
    if rest and not shut and self.may("people_level_log", 1, 10 ** 6):
        self.last["people_level_log"] = self.now
        log("people_level_fallback", day=self.day, sites=[x.get("id") for x in rest][:6])
    return shut + rest
def site_level_open(self, s, wh=None):
    if not self._ints(s, ("x", "y", "z")):
        return None
    w, h = wh if wh else (s.get("w") or 1, s.get("h") or 1)
    return self.level_open((s["x"], s["y"], s["z"], w, h))
def level_open(self, box):
    today = self.obs_day()
    hit = self.level_maps.get(box)
    if hit is not None and isinstance(today, (int, float)) and isinstance(hit[0], (int, float)) \
            and today - hit[0] < OPEN_PROBE_DAYS:
        return hit[1]
    x0, y0, z, w, h = box
    out = None
    try:
        res = query_result(self.game.query("map", x=min(400, max(0, x0 + (w - 1) // 2)),
                                           y=min(400, max(0, y0 + (h - 1) // 2)), z=z, z2=z, radius=LEVEL_RADIUS))
    except Exception as e:
        log("level_open_error", box=list(box), error=repr(e)[:160])
        res = None
    if isinstance(res, dict) and isinstance(res.get("x1"), int) and isinstance(res.get("y1"), int):
        lv = next((d(v) for v in lst(res.get("levels")) if d(v).get("z") == z), None)
        if lv is not None and isinstance(lv.get("shape"), list) and isinstance(lv.get("light"), list):
            rows, lights, x1, y1 = lv["shape"], lv["light"], res["x1"], res["y1"]
            stop = set()
            for b in lst(res.get("buildings")):
                b = d(b)
                if str(b.get("type")) in ("Door", "Hatch") and self._ints(b, ("x1", "y1")):
                    for bx in range(b["x1"], (b.get("x2") if isinstance(b.get("x2"), int) else b["x1"]) + 1):
                        for by in range(b["y1"], (b.get("y2") if isinstance(b.get("y2"), int) else b["y1"]) + 1):
                            stop.add((bx, by))
            def cell(x, y):
                i, j = y - y1, x - x1
                if 0 <= i < len(rows) and 0 <= i < len(lights) and isinstance(rows[i], str) \
                        and isinstance(lights[i], str) and 0 <= j < len(rows[i]) and j < len(lights[i]):
                    return rows[i][j], lights[i][j]
                return None
            start = [(x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + h)
                     if (cell(x, y) or ("#", ""))[0] in LEVEL_WALK and (x, y) not in stop]
            seen, todo, edge, found = set(start), list(start), False, False
            while todo and not found:
                x, y = todo.pop()
                c = cell(x, y)
                if c[1] == "o":
                    found = True
                    break
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        n = (x + dx, y + dy)
                        if n in seen or n in stop:
                            continue
                        cn = cell(*n)
                        if cn is None:
                            edge = True
                            continue
                        if cn[0] in LEVEL_WALK:
                            seen.add(n)
                            todo.append(n)
            out = 1 if found else (None if edge or not start else 0)
    self.level_maps[box] = (today, out)
    return out
def shelter_box_of(self, s):
    wh = self.box_wh(s, SHELTER_SIDE_MAX) if s.get("kind") == "R" else {}
    return (s.get("x"), s.get("y"), s.get("z"), wh.get("w", s.get("w") or 1), wh.get("h", s.get("h") or 1))
def open_a(self):
    return any(self.site_open(x) for x in self.kind("A"))
def people_room(self, role):
    if "dorm" not in self.roles.values():
        return None
    if role != "house" and role in self.roles.values():
        return None
    if role == "house" and any(self.roles.get(r["id"]) == "house" and not r.get("dug") for r in self.kind("R")):
        return None
    spare = [r for r in self.undug_rooms() if r["id"] not in self.roles and self.dry(r.get("z"))
             and not self.room_taken(r)]
    r = self.pick_dig_site(spare) if spare else None
    if r is None:
        return None
    size = {"w": SURGE_FLOOR_ROOM[0], "h": SURGE_FLOOR_ROOM[1]} if (self.surge or role == "house") else {}
    res = self.act("dig_%s_room" % role, "dig_room", {"site": r["id"], **size}, retry=2, limit=6)
    if res and res.get("ok"):
        self.roles[r["id"]] = role
        self.note_room_box(r, size)
        log("people_room", day=self.day, role=role, site=r["id"], **size)
        return r
    return None
def shelter_tiles(self):
    return sum((b[2] - b[0] + 1) * (b[3] - b[1] + 1) for b in self.shelter_boxes.values()
               if isinstance(b, tuple) and len(b) == 5)
def shelter_room(self, pending):
    if self.breach or not any(isinstance(k, tuple) and k[0] in ("open", "level") for k in self.shelter_skip):
        return
    if not isinstance(pending, int) or isinstance(pending, bool) \
            or pending >= SURGE_FLOOR_ROOM[0] * SURGE_FLOOR_ROOM[1] // 2:
        return
    have, want = self.shelter_tiles(), SHELTER_TILES_PER_CIT * (self.cit or 0)
    if have >= want:
        return
    if self.may("shelter_short_log", 2, 10 ** 6):
        self.last["shelter_short_log"] = self.now
        log("shelter_short", day=self.day, tiles=have, want=want, cit=self.cit)
    if self.people_room("house") is None and self.shaft is None \
            and not any(self.roles.get(r["id"]) == "house" and not r.get("dug") for r in self.kind("R")) \
            and not any(r["id"] not in self.roles for r in self.undug_rooms()):
        self.shelter_shaft()
def entrance_hold(self):
    if len(self.entrances) >= ENTRANCE_MAX:
        return "the fort already has %d surface entrances (at most %d); use the existing stairs" % (
            len(self.entrances), ENTRANCE_MAX)
    if self.hatch_free_spare() < 1:
        return "no free hatch cover is in hand for a new surface stair (the open entrances need theirs first); " \
               "the layer keeps covers on order"
    return None
def hatch_free_spare(self):
    doors = d(self.o.get("doors"))
    free = doors.get("hatch_cover_items_free")
    if not isinstance(free, int) or isinstance(free, bool):
        return 0
    at = {(x.get("x"), x.get("y"), x.get("z")) for x in map(d, lst(doors.get("list"))) if x.get("kind") == "hatch"}
    blocked = {d(x).get("id") for x in self.kind("E") if d(x).get("building")} | self.entrance_occupied
    waiting = [sid for sid, p in sorted(self.entrances.items(), key=lambda kv: site_key(kv[0]))
               if p not in at and sid not in blocked]
    return free - len(waiting)
def column_rock(self, s, z_low, z_high):
    try:
        res = query_result(self.game.query("map", x=s["x"], y=s["y"], z=z_high, z2=z_low, radius=0))
    except Exception as e:
        log("column_rock_error", error=repr(e)[:160])
        return None
    if not isinstance(res, dict) or not isinstance(res.get("x1"), int):
        return None
    seen = {}
    for lv in lst(res.get("levels")):
        lv = d(lv)
        rows = lv.get("shape") if isinstance(lv.get("shape"), list) else []
        i, j = s["y"] - res["y1"], s["x"] - res["x1"]
        if 0 <= i < len(rows) and isinstance(rows[i], str) and 0 <= j < len(rows[i]):
            seen[lv.get("z")] = rows[i][j]
    if any(z not in seen for z in range(z_low, z_high + 1)):
        return None
    return all(seen[z] in "#?" for z in range(z_low, z_high + 1))
def people_gap(self, s):
    best = None
    for z in self.zones:
        if not any(k in str(z.get("type")).lower() for k in ("meeting", "dining", "dormitory")):
            continue
        if not self._ints(z, ("x", "y", "w", "h")):
            continue
        g = max(z["x"] - s["x"], s["x"] - (z["x"] + z["w"] - 1), z["y"] - s["y"], s["y"] - (z["y"] + z["h"] - 1), 0)
        best = g if best is None else min(best, g)
    return 10 ** 6 if best is None else best
def shelter_shaft(self, why="shelter"):
    if self.shaft_stop or self.shaft is not None or self.surface is None or self.breach:
        return
    if len(self.entrances) + 1 > ENTRANCE_MAX:
        return
    if self.hatch_free_spare() < 1:
        return
    zs = [a.get("z") for a in self.kind("A") if self.dry(a.get("z")) and isinstance(a.get("z"), int)]
    if not zs:
        return
    zb = min(zs) - 1
    cands = [x for x in self.kind("S") if self._ints(x, ("x", "y", "z")) and 0 < x["z"] - zb <= 20
             and self.people_gap(x) >= SHAFT_PEOPLE_GAP]
    cands = [x for x in cands if self.column_rock(x, zb + 1, x["z"] - 1)]
    site = self.pick_dig_site(cands, levels=2) if cands else None
    if site is None:
        return
    res = self.act("stairs_shelter", "dig_stairs", {"site": site["id"], "z_bottom": zb},
                   retry=SURGE_FLOOR_STAIR_DAYS, limit=6)
    if res and res.get("ok"):
        self.shaft = {"site": site["id"], "x": site["x"], "y": site["y"], "z": site["z"], "day": self.day,
                      "e": None, "listed": None, "sent": None}
        log("shelter_shaft", day=self.day, why=why, site=site["id"], z_bottom=zb, tiles=self.shelter_tiles(),
            gap=self.people_gap(site), spare_covers=self.hatch_free_spare())
def shaft_hatch(self):
    sh = self.shaft
    if sh is None:
        return
    e = next((x for x in self.kind("E") if x.get("x") == sh["x"] and x.get("y") == sh["y"]
              and x.get("z") == sh["z"]), None)
    if e is None and sh.get("e") is None:
        return
    if e is not None:
        sh["e"] = e.get("id")
    if sh.get("listed") is None:
        sh["listed"] = self.day
        log("shaft_entrance", day=self.day, site=sh["e"], at=[sh["x"], sh["y"], sh["z"]])
    doors = d(self.o.get("doors"))
    hatch = next((x for x in map(d, lst(doors.get("list"))) if x.get("kind") == "hatch"
                  and (x.get("x"), x.get("y"), x.get("z")) == (sh["x"], sh["y"], sh["z"])), None)
    if hatch is not None and hatch.get("built", True):
        days = round((self.day or 0) - (sh["listed"] or 0), 2) if isinstance(self.day, (int, float)) else None
        self.shaft_open_days.append(days)
        log("shaft_hatched", day=self.day, site=sh["e"], open_days=days)
        self.shaft = None
        return
    if hatch is not None:
        return
    if d(self.o.get("burrows")).get("civilian_alert") is True and not self.hatch_safe((sh["x"], sh["y"], sh["z"])):
        if self.may("shaft_hatch_hold_log", 1, 10 ** 6):
            self.last["shaft_hatch_hold_log"] = self.now
            log("shaft_hatch_hold", day=self.day, site=sh["e"])
        return
    r = self.act("shaft_hatch_" + str(sh["e"]), "build_door", {"kind": "hatch", "site": sh["e"]},
                 retry=0.25, limit=SHAFT_HATCH_TRIES)
    if r is None:
        return
    if r.get("ok"):
        sh["sent"] = self.day
        log("shaft_hatch", day=self.day, site=sh["e"])
        return
    self.shaft_stop = True
    self.shaft = None
    log("shaft_stop", day=self.day, site=sh["e"], code=r.get("error_code"), err=str(r.get("error") or "")[:120])
def office_box(self, ready_only=False):
    if self.office_tile is None:
        cands = [s for s in self.kind("A") + self.dug_rooms()
                 if not self.area_fits(s, ZONE_MAX) and self.area_fits(s, PLACE_MAX)
                 and all(isinstance(s.get(k), int) and not isinstance(s.get(k), bool) for k in ("x", "y"))]
        ok = (lambda s: self.site_open(s) == 0) if ready_only \
            else (lambda s: s.get("kind") != "A" or not self.site_open(s))
        room = next((s for s in cands if ok(s)), None)
        if room is None:
            if ready_only:
                return
            self.office_room()
            room = next(iter(cands), None)
            if room is None:
                return
            if self.may("office_temp_log", 5, 10 ** 6):
                self.last["office_temp_log"] = self.now
                log("office_temp", day=self.day, site=room["id"])
        if (self.free.get("chair") or 0) <= 0:
            return
        box = {"kind": "chair", "site": room["id"], "w": min(ZONE_MAX, room.get("w") or 1),
               "h": min(ZONE_MAX, room.get("h") or 1)}
        r = self.act("office_box_chair", "place_furniture", box, retry=2, limit=4)
        at = d(r.get("result")).get("at") if r and r.get("ok") else None
        if isinstance(at, list) and at and isinstance(at[0], list):
            at = at[0]
        if not (isinstance(at, list) and len(at) == 3 and all(isinstance(v, int) and not isinstance(v, bool)
                                                               for v in at)):
            return
        w, h = at[0] - room["x"] + 1, at[1] - room["y"] + 1
        if not (1 <= w <= ZONE_MAX and 1 <= h <= ZONE_MAX):
            log("office_box_far", day=self.day, site=room["id"], at=at)
            return
        self.office_tile = (room["id"], w, h)
        log("office_box", day=self.day, site=room["id"], at=at, w=w, h=h)
    sid, w, h = self.office_tile
    if ready_only and any(x.get("id") == sid and x.get("kind") == "A" and self.site_open(x)
                          for x in self.kind("A")):
        return
    r = self.act("office_box_zone", "make_zone", {"kind": "office", "site": sid, "w": w, "h": h},
                 retry=2, limit=4)
    if r and r.get("ok"):
        self.done.add("office_box_zone")
def frame_on(self, site):
    x, y, z = site.get("x"), site.get("y"), site.get("z")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (x, y, z)):
        return False
    for w in lst(self.o.get("workshops")):
        w = d(w)
        if w.get("built") or w.get("z") != z:
            continue
        wx, wy = w.get("x"), w.get("y")
        if isinstance(wx, (int, float)) and isinstance(wy, (int, float)) \
                and not isinstance(wx, bool) and not isinstance(wy, bool) \
                and x <= wx < x + (site.get("w") or 1) and y <= wy < y + (site.get("h") or 1):
            return True
    return False
def harvest_bench_wanted(self, shops):
    carps = [w for w in shops if w.get("type") == "Carpenters" and not self.shop_stale(w)]
    if not carps or self.logs() - self.logs_guard() < HARVEST_CARP_SPARE_LOGS:
        return False
    for w in carps:
        jobs = [str(d(j).get("job")) for j in lst(w.get("job_details"))] + [str(j) for j in lst(w.get("jobs"))]
        if not any(j.startswith("MakeBarrel") for j in jobs):
            return False
    return len(self.idle_days) >= 2 and all(n >= 1 for _, n in self.idle_days)
def build(self, wtype, retry=3, key=None):
    sites = [s for s in self.kind("W") if not self.frame_on(s)]
    if not sites:
        sites = [s for s in self.remembered("W") if not self.shop_clash(s)]
    if wtype == "Butchers":
        sites = [s for s in sites if not self.dead_site(s)]
    if not sites or not self.material():
        return
    result = self.act(key or ("ws_" + wtype), "build_workshop", dict(self.site_args(sites[0]), type=wtype),
                      retry=retry)
    if result and result.get("ok") and not sites[0].get("_mem"):
        self.sites.remove(sites[0])
    self.mem_used(sites[0], result)
def workshops(self):
    shops = [w for w in lst(self.o.get("workshops")) if isinstance(w, dict)]
    have = {w.get("type") for w in shops if not self.shop_stale(w)}
    stale = {w.get("type") for w in shops if self.shop_stale(w)}
    for t in ("Carpenters", "Still", "Kitchen"):
        if t not in have:
            if t not in stale:
                self.done.discard("ws_" + t)
            self.build(t, key="ws_rebuild_" + str(t) if t in stale else None,
                       retry=REBUILD_GAP_DAYS if t in stale else 3)
    if self.hands_off is None and "Still" in have:
        stills = sum(1 for w in shops if w.get("type") == "Still" and not self.shop_stale(w))
        backlog = sum((x.get("left") or 0) for x in self.orders
                      if x.get("recipe") == "brew_drink" and not x.get("repeat") and x.get("active") is not False)
        if stills < STILL_MAX and (backlog >= STILL_BACKLOG or self.rot_seen) and self.logs() >= 4:
            self.build("Still", key="ws_Still_%d" % (stills + 1), retry=3)
        self.kitchen_backlog(shops)
        carp = sum(1 for w in shops if w.get("type") == "Carpenters" and not self.shop_stale(w))
        if carp == 1 and (backlog >= STILL_BACKLOG or self.rot_seen
                          or self.harvest_barrels_short() >= HARVEST_CARP_SHORT) and self.logs() >= 4 \
                and not self.surge:
            self.build("Carpenters", key="ws_Carpenters_2", retry=3)
        elif self.barrel_press() and 1 <= carp < PRESS_CARPENTERS and self.logs() >= 4 and not self.surge:
            self.build("Carpenters", key="ws_Carpenters_%d" % (carp + 1), retry=3)
        elif self.barrel_press() and self.press_harv and PRESS_CARPENTERS <= carp < HARVEST_CARPENTERS \
                and not self.surge and self.harvest_bench_wanted(shops):
            self.build("Carpenters", key="ws_Carpenters_%d" % (carp + 1), retry=3)
    if "Fishery" not in have and (self.food_alarm()
                                  or any(p.get("job") == "Fish" for p in self.people)):
        self.build("Fishery", key="ws_rebuild_Fishery" if "Fishery" in stale else None,
                   retry=REBUILD_GAP_DAYS if "Fishery" in stale else 3)
def kitchen_backlog(self, shops):
    if self.hands_off is not None or (getattr(self, "days", 0) or 0) < 336 or getattr(self, "surge", False):
        return False
    kitchens = sum(1 for w in shops if w.get("type") == "Kitchen" and not self.shop_stale(w))
    if not 1 <= kitchens < KITCHEN_MAX or self.logs() < 4:
        return False
    backlog = sum(max(0, x.get("left") or 0) for x in self.orders
                  if x.get("recipe") == "cook_meal" and not x.get("repeat"))
    if backlog < KITCHEN_BACKLOG or not (self.rot_seen or self.aged_plants() >= 1):
        return False
    key = "ws_Kitchen_%d" % (kitchens + 1)
    if key not in self.done:
        log("kitchen_backlog", day=self.day, kitchens=kitchens, backlog=backlog, rot_seen=self.rot_seen,
            aged=self.aged_plants(), rotten=self.st.get("plants_rotten"), pb=self.st.get("plants_brewable"))
    self.build("Kitchen", key=key, retry=3)
    return True
def bed_target(self):
    if self.surge:
        return self.surge_pop() + SURGE_BED_MARGIN
    return self.cit + (FULL_YEAR_BEDS if self.days >= 336 else 3)
def surge_pop(self):
    cit = self.cit if isinstance(self.cit, (int, float)) and not isinstance(self.cit, bool) else 0
    start = self.mig_start
    if self.mig_waves == 0 and isinstance(start, (int, float)) and cit <= start \
            and isinstance(self.day, (int, float)) and self.day <= SURGE_WAVE_WAIT_DAYS:
        return max(cit, int(math.ceil(SURGE_FIRST_WAVE * start)))
    return cit
def surge_beds_short(self):
    return self.surge and ((self.st.get("beds") or 0) < self.bed_target()
                           or (self.placed.get("bed") or 0) < (self.cit or 0))
def surge_bed_orders(self, have, want):
    queued = sum(max(0, x.get("left") or 0) for x in self.orders
                 if x.get("recipe") == "make_bed" and not x.get("repeat"))
    gap = min(want - have - queued, self.logs())
    for key in ("o_make_bed", "o_make_bed_2"):
        if gap < 1:
            break
        amount = min(30, gap)
        result = self.act(key, "add_order", {"recipe": "make_bed", "amount": amount}, retry=1, limit=99)
        if not (result and result.get("ok")):
            break
        gap -= amount
        log("surge_bed_book", day=self.day, have=have, queued=queued, want=want, added=amount)
def farm_target(self):
    pop = self.pop_forecast()
    if self.days >= 336:
        base = max(6, min(12, math.ceil(pop / 3)))
        tiles, sown = self.plot_tiles()
        built = sum(1 for p in lst(self.o.get("farm_plots")) if isinstance(p, dict) and p.get("built") is not False)
        seeds = self.st.get("seeds")
        if tiles > 0 and isinstance(seeds, (int, float)) and not isinstance(seeds, bool) \
                and seeds - sown >= SEEDS_PER_PLOT + max(0, tiles - sown):
            base = max(base, min(12, built + 1))
        return base
    return max(4, min(10, math.ceil(pop / 5)))
def pop_forecast(self):
    cit = self.cit if isinstance(self.cit, (int, float)) and not isinstance(self.cit, bool) else 0
    if self.hands_off is not None:
        return cit
    left = self.days_to_end()
    if left is not None and left <= HOLD_GROW_DAYS:
        return cit
    start = self.mig_start if self.mig_start is not None else cit
    prior = 1 if start > EMBARK_PARTY else 0
    waves = max(0, WAVES_EXPECTED - prior - self.mig_waves)
    return int(math.ceil(cit + WAVE_MEAN * waves))
def pick_dig_site(self, cands, levels=1):
    for i, site in enumerate(cands):
        if not self.water_ok(site):
            continue
        if self.water_wetness(site) is None:
            self.water_measure(site, levels)
        if self.water_rank(site) == 2:
            continue
        return site
    return None
def dig_refusal(self, tool, args):
    if tool not in ("dig_room", "dig_stairs") or not isinstance(args, dict):
        return None
    if self.breach:
        return "a flood breach is contained (water rose after a dig); no new digs until it recedes"
    sid = args.get("site")
    site = next((s for s in getattr(self, "sites", None) or [] if s.get("id") == sid), None)
    if site is None:
        return None
    if not self.water_ok(site):
        return f"site {sid} is halted: water stands at or near it"
    try:
        n = self.water_measure(site, levels=2 if site.get("kind") == "S" else 1)
    except Exception as e:
        log("water_probe_error", site=sid, error=repr(e)[:160])
        return None
    if n:
        return f"site {sid}: {n} water tiles (river, pool or liquid) touch its dig box; digging it lets the water in"
    return None
def stair_bottom(self):
    zs = [r.get("z") for r in self.kind("R")
          if isinstance(r.get("z"), int) and (self.roles.get(r["id"]) or r.get("dug"))]
    if not zs:
        return max(0, self.surface - 1)
    return max(0, min(self.surface, min(zs)))
def digging(self):
    if self.breach:
        self.contain_flood()
        return
    rooms = self.kind("R")
    pending = self.o.get("dig_designations_pending") or 0
    if self.office_wants_room():
        self.office_room()
    if pending <= 90:
        self.surge_capacity()
        farms = len(lst(self.o.get("farm_plots"))) + sum(1 for r, v in self.roles.items() if v == "farm" and not any(z.get("id") == r and z.get("used_by") for z in self.kind("R")))
        remaining = self.undug_rooms()
        shaft = self.shaft_people()
        if shaft:
            remaining.sort(key=lambda r: self.shaft_near(dict(r, w=r.get("w") or 3, h=r.get("h") or 3)))
        plots_up = self.shaft_plots_held(sum(1 for p in lst(self.o.get("farm_plots"))
                                             if isinstance(p, dict) and self.dry(p.get("z"))))
        while remaining:
            r = self.pick_dig_site(remaining)
            if r is None:
                break
            remaining.remove(r)
            rid = r["id"]
            if rid in self.roles:
                continue
            need = [x for x in ("dorm", "dine", "office") if x not in self.roles.values()]
            people = [x for x in need if x != "office"]
            held = self.bed_held_rooms() if BED_HELD_BOX else []
            house_first = bool(people) and farms + sum(1 for h in held if h.get("used_by")) >= HOUSE_AFTER_FARMS \
                and (self.house_blocked() or bool(held)) \
                and not self.rush_holds_digs()
            if r.get("soil") and farms < self.farm_target() and not house_first:
                if shaft and plots_up and self.shaft_dig_waits(r, {}):
                    continue
                result = self.act("dig_" + rid, "dig_room", {"site": rid}, retry=3, limit=2)
                if result and result.get("ok"):
                    self.roles[rid] = "farm"
                    farms += 1
            elif need and not self.rush_holds_digs():
                role = people[0] if house_first else need[0]
                size = {"dorm": {"w": 9, "h": 7}, "dine": {"w": 7, "h": 5}, "office": {}}[role]
                if size and self.hands_off is None and self.farm_claimed(dict(r, **size)):
                    continue
                if shaft and (role == "dine" or (role == "dorm" and self.placed_dry("bed") >= (self.cit or 0))) \
                        and self.shaft_dig_waits(r, size):
                    continue
                result = self.act("dig_" + rid, "dig_room", {"site": rid, **size}, retry=3, limit=2)
                if result and result.get("ok"):
                    self.roles[rid] = role
                    self.note_room_box(r, size)
    self.surge_stair(pending)
    self.shelter_room(pending)
    self.house_floor(pending)
    stairs = self.kind("S")
    if stairs and self.surface is not None and (len(rooms) < 2 or (not any(r.get("soil") for r in rooms)
                                                                   and not self.o.get("farm_plots"))):
        stair = self.pick_dig_site(list(reversed(stairs)), levels=2)
        if stair is None and self.water_rank(stairs[-1]) != 2:
            stair = stairs[-1]
        if stair is not None and self.water_ok(stair):
            self.act("stairs", "dig_stairs", {"site": stair["id"], "z_bottom": self.stair_bottom()},
                     retry=2, limit=3)
def reserved_hit(self, box, kind=""):
    if not isinstance(box, dict) or not self._ints(box, ("x", "y", "z", "w", "h")) or kind in BEDROOM_OWN_KINDS:
        return None
    for z in self.zone("bedroom"):
        if self._ints(z, ("x", "y", "z", "w", "h")) and self.rects_overlap(z, box):
            return z.get("id"), z.get("owner")
    return None
def people_boxes(self):
    if not self.shaft_people():
        return []
    out = [z for z in self.zone("meeting") + self.zone("dining") if self._ints(z, ("x", "y", "z", "w", "h"))]
    beds = [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
            if isinstance(f, dict) and f.get("kind") == "bed" and self._ints(f)]
    sleep = [z for z in self.zones if any(k in str(z.get("type")).lower() for k in ("dormitory", "bedroom"))]
    surface = d(self.o.get("map")).get("surface_z", getattr(self, "surface", None))
    for s_ in self.closed_a():
        if s_.get("id") in self.zone_banned or not self.dry(s_.get("z")) \
                or (isinstance(surface, (int, float)) and isinstance(s_.get("z"), (int, float))
                    and s_["z"] >= surface):
            continue
        floor = self.site_floor(s_, walk=True)
        if floor is None:
            continue
        cut = self.far_cut(self.site_box(s_, ZONE_MAX), sleep + beds, MEETING_MIN_TILES, floor=floor,
                           placing=False)
        if cut is not None:
            out.append({"x": s_["x"], "y": s_["y"], "z": s_["z"], "w": cut[0], "h": cut[1], "site": s_["id"]})
    return out
def people_later(self, room):
    if not self.shaft_people() or not self._ints(room, ("x", "y", "z")):
        return False
    rb = {"x": room["x"], "y": room["y"], "z": room["z"], "w": room.get("w") or 3, "h": room.get("h") or 3}
    beds = [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
            if isinstance(f, dict) and f.get("kind") == "bed" and self._ints(f)]
    sleep = [z for z in self.zones if any(k in str(z.get("type")).lower() for k in ("dormitory", "bedroom"))]
    for a in self.closed_a():
        if a.get("z") != rb["z"] or not self._ints(a, ("x", "y", "z", "w", "h")):
            continue
        x1, y1 = min(a["x"], rb["x"]), min(a["y"], rb["y"])
        x2, y2 = max(a["x"] + a["w"], rb["x"] + rb["w"]), max(a["y"] + a["h"], rb["y"] + rb["h"])
        u = {"x": x1, "y": y1, "z": rb["z"], "w": min(ZONE_MAX, x2 - x1), "h": min(ZONE_MAX, y2 - y1)}
        cut = self.far_cut(u, sleep + beds, MEETING_MIN_TILES, placing=False)
        if cut is not None and self.rects_overlap(dict(u, w=cut[0], h=cut[1]), rb):
            return True
    return False
def under_people(self, box, boxes=None):
    boxes = self.people_boxes() if boxes is None else boxes
    return any(self.rects_overlap(b, box) for b in boxes)
def room_reserved(self, tool, args):
    if tool not in ("make_zone", "build_farm", "place_furniture") or not isinstance(args, dict):
        return None
    sid = args.get("site")
    site = next((x for x in getattr(self, "sites", None) or [] if x.get("id") == sid), None)
    if site is None:
        return None
    box = self.site_box(site, PLACE_MAX)
    w, h = args.get("w"), args.get("h")
    if isinstance(w, int) and isinstance(h, int) and not isinstance(w, bool) and not isinstance(h, bool):
        box = dict(box, w=w, h=h)
    kind = "farm" if tool == "build_farm" else str(args.get("kind") or "")
    hit = self.reserved_hit(box, kind)
    if hit is None:
        if tool == "build_farm":
            rid = self.dorm_corner_hit(box)
            if rid is not None:
                return "site %s covers the corner of room %s, the dormitory the beds still wait for (a plot " \
                       "there closes the whole room to beds)" % (sid, rid)
        return None
    return "site %s covers room %s, dug for a private bedroom (%s)" % (sid, hit[0], hit[1])
def dorm_corner_hit(self, box):
    if not DORM_CORNER_HOLD or not self._ints(box, ("x", "y", "z", "w", "h")):
        return None
    try:
        need = self.surge_pop() if getattr(self, "surge", None) else (self.cit or 0)
        if self.placed_dry("bed") >= need \
                or not ((self.free.get("bed") or 0) > 0 or self.pending("make_bed")) or self.my1_plan() \
                or (self.st.get("drink") or 0) < self.f_drink_rate(prior_only=True) * BED_ROOM_DRINK_DAYS:
            return None
    except Exception as e:
        log("dorm_corner_error", error=repr(e)[:160])
        return None
    plots = [p for p in lst(self.o.get("farm_plots")) if self._ints(p, ("x", "y", "z", "w", "h"))]
    for r in self.kind("R"):
        if self.roles.get(r.get("id")) not in ("dorm", "house") or not r.get("dug") \
                or not self._ints(r, ("x", "y", "z")):
            continue
        if any("farm plot" in str(u).lower() for u in lst(r.get("used_by"))) or r.get("id") in self.plot_rooms:
            continue
        corner = {"x": r["x"], "y": r["y"], "z": r["z"], "w": 3, "h": 3}
        if any(self.rects_overlap(corner, p) for p in plots):
            continue
        if self.rects_overlap(corner, box):
            return r.get("id")
    return None
def dorm_lost(self):
    for r in self.kind("R"):
        rid = r.get("id")
        if self.roles.get(rid) == "dorm" and any("farm plot" in str(u).lower() for u in lst(r.get("used_by"))):
            self.roles.pop(rid, None)
            log("surge_dorm_lost", day=self.day, site=rid, why="used_by")
def shaft_refusal(self, tool, args):
    if not isinstance(args, dict) or not self.shaft_people():
        return None
    kind = str(args.get("kind") or "")
    sid = args.get("site")
    site = next((x for x in getattr(self, "sites", None) or [] if x.get("id") == sid), None)
    if site is None:
        return None
    w, h = args.get("w"), args.get("h")
    box = self.site_box(site, PLACE_MAX)
    if isinstance(w, int) and isinstance(h, int) and not isinstance(w, bool) and not isinstance(h, bool):
        box = dict(box, w=w, h=h)
    if not self.shaft_near(box):
        return None
    why = "site %s lies within %d tiles of the open shaft at %s" % (
        sid, MEETING_SHAFT_TILES, ",".join("%d,%d" % c[:2] for c in self.shaft_cols()))
    if (tool == "place_furniture" and kind in ("table", "chair")) \
            or (tool == "make_zone" and kind in ("dining_hall", "meeting_area")):
        if kind != "meeting_area" and any(self.rects_overlap(z, box) for z in self.zone("dining")):
            return None
        beds = [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
                if isinstance(f, dict) and f.get("kind") == "bed" and self._ints(f)]
        sleep = [z for z in self.zones if any(k in str(z.get("type")).lower() for k in ("dormitory", "bedroom"))]
        far = self.far_box(sleep + beds, min_tiles=SHAFT_PEOPLE_MIN_TILES, rooms=True,
                           skip_roles=("dorm", "house", "office", "stress", "bedroom"))
        if far is not None:
            return why + "; use site %s with w=%d h=%d (far from it)" % (far[0].get("id"), far[1], far[2])
        if kind == "meeting_area" and self.shaft_wait():
            return why + "; wait for the digging to open a room further from it"
        return None
    if not self.shaft_wait():
        return None
    if tool == "build_farm" and self.shaft_plots_held(
            sum(1 for p in lst(self.o.get("farm_plots")) if isinstance(p, dict) and self.dry(p.get("z")))):
        return why + "; plant a farm site further from it"
    if tool == "dig_room" and self.placed_dry("bed") >= (self.cit or 0):
        return why + "; dig a room further from it"
    return None
def shaft_dig_waits(self, r, size):
    box = {"x": r.get("x"), "y": r.get("y"), "z": r.get("z"), "w": size.get("w", 3), "h": size.get("h", 3)}
    if not (self.shaft_near(box) and self.shaft_wait()):
        return False
    if self.may("shaft_dig_wait_" + str(r.get("id")), 10, 10 ** 6):
        self.last["shaft_dig_wait_" + str(r.get("id"))] = self.now
        log("shaft_dig_wait", day=self.day, site=r.get("id"), size=size or None)
    return True
def surge_capacity(self):
    if not self.surge:
        return
    self.dorm_lost()
    have = sum(1 for rid, role in self.roles.items() if role == "dorm")
    added = 0
    spare = [r for r in self.undug_rooms() if r["id"] not in self.roles]
    rock = self.rock_rooms(spare)
    extra = bool(ROCK_DORM and rock and self.surge_beds_due() and not self.rock_rooms(self.dorm_rooms()))
    if have < surge_dorm_rooms(self.cit) or extra:
        r = self.pick_dig_site(rock) if rock and ROCK_DORM else None
        if r is None and not (extra and have >= surge_dorm_rooms(self.cit)):
            r = self.pick_dig_site(spare) if spare else None
        if r is not None and extra and have >= surge_dorm_rooms(self.cit):
            log("rock_dorm_dig", day=self.day, site=r.get("id"), have=have)
        if r is not None and have == 1 and self.rock_dorm_wait(r):
            r = None
        if r is not None:
            box = self.surge_room_box(r)
            result = self.act("dig_dorm_cap", "dig_room", box, retry=3, limit=6)
            if result and result.get("ok"):
                self.roles[r["id"]] = "dorm"
                self.note_room_box(r, box)
                added = d(result.get("result")).get("designated")
    self.surge_floor(added if isinstance(added, int) and not isinstance(added, bool) else 0)
    self.rock_dorm_stair()
def rock_rooms(self, rooms):
    return [r for r in rooms if r.get("soil") is False]
def dorm_rooms(self):
    return [r for r in self.kind("R") if self.roles.get(r.get("id")) == "dorm"]
def surge_beds_due(self):
    return bool(self.surge) and isinstance(self.hands_off, int) and self.hands_off > 0 \
        and self.placed_dry("bed") < self.surge_pop()
def rock_dorm_wait(self, r):
    if not ROCK_DORM or not ROCK_DORM_WAIT or r.get("soil") is not True or not self.surge_beds_due() \
            or self.beds_wait_floor():
        return False
    if self.rock_rooms(self.kind("R")) or self.shaft_stop or len(self.entrances) + 1 > ENTRANCE_MAX \
            or self.surface is None:
        return False
    zs = [a.get("z") for a in self.kind("A") if self.dry(a.get("z")) and isinstance(a.get("z"), int)]
    if not zs:
        return False
    zb = min(zs) - 1
    if self.shaft is None and not any(self._ints(x, ("x", "y", "z")) and 0 < x["z"] - zb <= 20
                                      and self.column_rock(x, zb + 1, x["z"] - 1) for x in self.kind("S")):
        return False
    if self.may("rock_dorm_wait_log", 2, 10 ** 6):
        self.last["rock_dorm_wait_log"] = self.now
        log("rock_dorm_wait", day=self.day, site=r.get("id"), spare_covers=self.hatch_free_spare())
    return True
def beds_wait_floor(self):
    if (self.free.get("bed") or 0) <= 0:
        return False
    rooms = [rid for rid, v in self.roles.items() if v == "dorm"]
    if not rooms:
        return True
    today = self.obs_day()
    for rid in rooms:
        mark = self.bed_full.get(rid)
        if mark and isinstance(today, (int, float)) and isinstance(mark[0], (int, float)) \
                and today - mark[0] < SURGE_BED_RETRY_DAYS:
            return True
    return False
def rock_dorm_stair(self):
    if not ROCK_DORM or not self.surge_beds_due() or self.breach:
        return
    rooms = self.kind("R")
    if not rooms or self.rock_rooms(rooms):
        return
    if self.may("rock_dorm_log", 2, 10 ** 6):
        self.last["rock_dorm_log"] = self.now
        log("rock_dorm_short", day=self.day, rooms=[r.get("id") for r in rooms][:8],
            spare_covers=self.hatch_free_spare(), entrances=len(self.entrances), shaft=bool(self.shaft))
    self.shelter_shaft(why="rock_dorm")
def surge_room_box(self, r):
    w, h = SURGE_FLOOR_ROOM
    plain = {"site": r["id"], "w": w, "h": h}
    if SURGE_ROOM_SITE_ONLY:
        return plain
    st = d(r.get("stair"))
    vals = (r.get("x"), r.get("y"), r.get("z"), st.get("x"), st.get("y"))
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
        return plain
    x, y, z, sx, sy = vals
    if x == sx + 1:
        x0, y0 = x, y - (h - 3) // 2
    elif x + 2 == sx - 1:
        x0, y0 = sx - w, y - (h - 3) // 2
    elif y == sy + 1:
        x0, y0 = x - (w - 3) // 2, y
    elif y + 2 == sy - 1:
        x0, y0 = x - (w - 3) // 2, sy - h
    else:
        return plain
    if x0 < 0 or y0 < 0:
        return plain
    return {"x": x0, "y": y0, "z": z, "w": w, "h": h}
def surge_floor_free(self):
    out = 0
    for a in self.kind("A"):
        z = a.get("z")
        if not self.dry(z) or not isinstance(a.get("open_tiles"), int):
            continue
        used = sum(1 for f in lst(self.o.get("furniture")) if d(f).get("z") == z)
        used += sum((d(p).get("w") or 3) * (d(p).get("h") or 3) for p in lst(self.o.get("farm_plots"))
                    if d(p).get("z") == z)
        used += sum(9 for w in lst(self.o.get("workshops")) if d(w).get("z") == z)
        out += max(0, a["open_tiles"] - used)
    plots = [p for p in lst(self.o.get("farm_plots")) if self._ints(p, ("x", "y", "z", "w", "h"))]
    furn = [f for f in lst(self.o.get("furniture")) if self._ints(f)]
    for r in self.kind("R"):
        box = self.room_box.get(r.get("id"))
        if not any("farm plot" in str(u).lower() for u in lst(r.get("used_by"))) \
                or not self._ints(box, ("x", "y", "z", "w", "h")) or not self.dry(box["z"]):
            continue
        tiles = {(x, y) for x in range(box["x"], box["x"] + box["w"]) for y in range(box["y"], box["y"] + box["h"])}
        for p in plots:
            if p["z"] == box["z"]:
                tiles -= {(x, y) for x in range(p["x"], p["x"] + p["w"]) for y in range(p["y"], p["y"] + p["h"])}
        tiles -= {(f["x"], f["y"]) for f in furn if f["z"] == box["z"]}
        out -= len(tiles)
    return max(0, out)
def surge_floor_short(self, pending=0):
    if not self.surge or not isinstance(self.hands_off, int) or self.hands_off <= 0:
        return False
    if not any(self.dry(a.get("z")) for a in self.kind("A")):
        return False
    need = self.surge_pop() + 2 - self.placed_dry("bed")
    if need <= 0:
        return False
    return self.surge_floor_free() + max(0, pending) < need + SURGE_FLOOR_MARGIN
def surge_floor(self, added=0):
    pending = self.o.get("dig_designations_pending") or 0
    if not isinstance(pending, int):
        return
    pending += max(0, added)
    if not self.surge_floor_short(pending):
        return
    spare = [r for r in self.undug_rooms() if r["id"] not in self.roles and self.dry(r.get("z"))]
    rock = self.rock_rooms(spare) if ROCK_DORM else []
    r = (self.pick_dig_site(rock) if rock else None) or (self.pick_dig_site(spare) if spare else None)
    if r is not None and any(v == "dorm" for v in self.roles.values()) and self.rock_dorm_wait(r):
        return
    if r is not None:
        box = self.surge_room_box(r)
        res = self.act("dig_floor_cap", "dig_room", box, retry=1, limit=8)
        if res and res.get("ok"):
            self.roles[r["id"]] = "dorm"
            self.note_room_box(r, box)
            log("surge_floor_dig", day=self.day, site=r["id"], free=self.surge_floor_free(), pending=pending)
        return
    if pending >= SURGE_FLOOR_ROOM[0] * SURGE_FLOOR_ROOM[1] // 2 or self.surface is None:
        return
    zs = [a.get("z") for a in self.kind("A") if self.dry(a.get("z")) and isinstance(a.get("z"), int)]
    if not zs:
        return
    zb = min(zs) - 1
    last = self.last.get("stairs_floor_s")
    if last is not None and self.now - last < SURGE_FLOOR_STAIR_DAYS * DAY:
        return
    cands = [s for s in self.kind("S") if all(isinstance(s.get(k), int) for k in ("x", "y", "z"))
             and 0 < s["z"] - zb <= 20 and not self.column_dug(s, zb + 1, s["z"] - 1)]
    site = self.pick_dig_site(cands, levels=2) if cands else None
    if site is None:
        return
    res = self.act("stairs_floor_s", "dig_stairs", {"site": site["id"], "z_bottom": zb},
                   retry=SURGE_FLOOR_STAIR_DAYS, limit=3)
    if res is None:
        return
    log("surge_floor_stair", day=self.day, site=site.get("id"), z_bottom=zb, ok=res.get("ok"),
        free=self.surge_floor_free())
def column_dug(self, s, z_low, z_high):
    for a in self.kind("A"):
        if isinstance(a.get("z"), int) and z_low <= a["z"] <= z_high \
                and all(isinstance(a.get(k), int) for k in ("x", "y", "w", "h")) \
                and a["x"] <= s["x"] < a["x"] + a["w"] and a["y"] <= s["y"] < a["y"] + a["h"]:
            return True
    return False
def over_dug(self, s, z):
    for a in self.kind("A"):
        if a.get("z") == z and all(isinstance(a.get(k), int) for k in ("x", "y", "w", "h")) \
                and a["x"] <= s["x"] < a["x"] + a["w"] and a["y"] <= s["y"] < a["y"] + a["h"]:
            return True
    return False
def surge_stair(self, pending):
    if not self.surge or not isinstance(self.day, (int, float)):
        return
    if self.pend_mark is None or self.pend_mark[1] != pending:
        self.pend_mark = (self.day, pending)
        return
    if pending <= 0 or self.day - self.pend_mark[0] < SURGE_STALL_DAYS:
        return
    dug_dorms = sum(1 for r in self.kind("R") if self.roles.get(r["id"]) == "dorm" and r.get("dug"))
    if dug_dorms >= surge_dorm_rooms(self.cit) or any(r["id"] not in self.roles for r in self.undug_rooms()):
        return
    stairs = self.kind("S")
    site = self.pick_dig_site(list(stairs), levels=2) if stairs else None
    if site is None or self.surface is None:
        return
    result = self.act("stairs_surge", "dig_stairs", {"site": site["id"], "z_bottom": self.stair_bottom()},
                      retry=SURGE_STALL_DAYS, limit=3)
    if result and result.get("ok"):
        self.pend_mark = (self.day, pending)
def farms(self):
    plots = [p for p in lst(self.o.get("farm_plots")) if self.dry(p.get("z"))]
    target = self.farm_target()
    if len(plots) >= target:
        return
    cands = (self.kind("F") or self.remembered("F")) + [r for r in self.dug_rooms() if r.get("soil") and self.roles.get(r["id"], "farm") == "farm"
                              and r["id"] not in self.plot_rooms
                              and not any("farm plot" in str(u).lower() for u in lst(r.get("used_by")))]
    seeds = self.live_seeds_by_kind()
    if any(not d(v).get("underground") for v in seeds.values()):
        cands += (self.kind("G") or self.remembered("G"))[:2]
    cands = [s for s in cands if self.dry(s.get("z"))]
    free = [s for s in cands if not self.room_taken(s)]
    if len(free) < len(cands):
        skipped = [s.get("id") for s in cands if s not in free]
        if skipped != getattr(self, "farm_skip_logged", None):
            self.farm_skip_logged = skipped
            log("farm_site_in_room", day=self.day, skipped=skipped, fallback=not free and not plots)
        spare = [] if free or not plots else self.surge_room_plots([s for s in cands if s not in free])
        cands = free or spare if free or plots else cands[:1]
    rush = self.seed_rush()
    cands = self.shaft_plots(cands, plots, target)
    cands = self.bed_room_hold(cands, plots)
    for s in cands[:target - len(plots)]:
        r = self.act("farm_" + s["id"], "build_farm", self.site_args(s, box=True), retry=4, limit=3)
        self.mem_used(s, r)
        if rush and r is not None and r.get("ok") and d(self.o.get("plugins")).get("autofarm") != "on":
            self.act("plug_autofarm", "enable_automation", {"name": "autofarm"}, retry=5)
def bed_held_rooms(self):
    if not getattr(self, "bed_held", None):
        return []
    boxes = [p for p in lst(self.o.get("farm_plots")) if isinstance(p, dict)]
    return [r for r in self.kind("R") if r.get("id") in self.bed_held and r.get("dug")
            and r.get("id") not in self.plot_rooms
            and not any("farm plot" in str(u).lower() for u in lst(r.get("used_by")))
            and not any(self.rects_overlap(b, r) for b in boxes)]
def bed_room_hold(self, cands, plots):
    if not BED_ROOM_HOLD or getattr(self, "surge", None) or getattr(self, "hands_off", None) is not None \
            or not cands:
        return cands
    try:
        if self.placed_dry("bed") >= (self.cit or 0) \
                or not ((self.free.get("bed") or 0) > 0 or self.pending("make_bed")) or self.my1_plan() \
                or (self.st.get("drink") or 0) < self.f_drink_rate(prior_only=True) * BED_ROOM_DRINK_DAYS:
            return cands
    except Exception as e:
        log("bed_room_hold_error", error=repr(e)[:160])
        return cands
    boxes = [p for p in lst(self.o.get("farm_plots")) if isinstance(p, dict)
             and all(isinstance(p.get(k), int) and not isinstance(p.get(k), bool) for k in ("x", "y", "z", "w", "h"))]
    rooms = [r for r in self.kind("R") if r.get("dug") and self.dry(r.get("z"))
             and r.get("id") not in self.plot_rooms
             and not any("farm plot" in str(u).lower() for u in lst(r.get("used_by")))
             and not any(self.rects_overlap(b, r) for b in boxes)]
    out, held, n = [], [], len(plots)
    for c in cands:
        hits = [r for r in rooms if r.get("id") == c.get("id") or self.rects_overlap(r, dict(c, w=c.get("w") or 3,
                                                                                         h=c.get("h") or 3))]
        if hits and n >= 1 and not [r for r in rooms if r not in hits]:
            held.append(c.get("id"))
            self.bed_held |= {r.get("id") for r in hits if r.get("id")}
            continue
        out.append(c)
        n += 1
        rooms = [r for r in rooms if r not in hits]
    if held and self.may("bed_room_hold_log", 3, 10 ** 6):
        self.last["bed_room_hold_log"] = self.now
        log("bed_room_hold", day=self.day, held=held, rooms=[r.get("id") for r in rooms],
            beds_placed=self.placed_dry("bed"), free_beds=self.free.get("bed") or 0)
    return out
def shaft_plots(self, cands, plots, target):
    if not self.shaft_people() or not cands:
        return cands
    box = lambda c: self.site_box(c, PLACE_MAX) if c.get("kind") == "R" else dict(c, w=c.get("w") or 3,
                                                                                     h=c.get("h") or 3)
    far = [c for c in cands if not self.shaft_near(box(c))]
    near = [c for c in cands if self.shaft_near(box(c))]
    if near and self.shaft_plots_held(len(plots), target) and self.shaft_wait():
        if self.may("shaft_plot_wait_log", 10, 10 ** 6):
            self.last["shaft_plot_wait_log"] = self.now
            log("shaft_plot_wait", day=self.day, near=[c.get("id") for c in near][:4],
                far=[c.get("id") for c in far][:4])
        return far
    return far + near
def shaft_plots_held(self, plots, target=None):
    target = self.farm_target() if target is None else target
    if self.plots_needed():
        return False
    return plots >= max(1, math.ceil(target / 2))
def plots_needed(self):
    try:
        if self.my1_plan():
            return True
        left = self.days_to_end()
        if not isinstance(left, (int, float)) or left <= 0:
            return False
        have = (self.st.get("drink") or 0) + (self.st.get("plants_brewable") or 0) * BREW_DRINKS
        return have < self.f_drink_rate(prior_only=True) * left
    except Exception as e:
        log("plots_needed_error", error=repr(e)[:160])
        return True
def surge_room_plots(self, skipped):
    if not self.surge or not isinstance(self.hands_off, int) or self.hands_off <= 0 or not skipped:
        return []
    left = self.days_to_end()
    if left is None or left < HOLD_GROW_DAYS:
        return []
    boxes = [{"x": r.get("x"), "y": r.get("y"), "z": r.get("z"), "w": 3, "h": 3} for r in self.kind("R")]
    ok = [s for s in skipped if not any(self.rects_overlap(dict(s, w=s.get("w") or 3, h=s.get("h") or 3), b)
                                        for b in boxes)]
    if not ok:
        return []
    pending = self.o.get("dig_designations_pending") or 0
    pending = pending if isinstance(pending, int) and not isinstance(pending, bool) else 0
    need = self.surge_pop() + 2 - self.placed_dry("bed")
    if self.surge_floor_free() + pending - 9 < max(0, need) + SURGE_FLOOR_MARGIN:
        return []
    log("surge_room_plot", day=self.day, site=ok[0].get("id"), free=self.surge_floor_free(), need=need)
    return ok[:1]
def seed_rush(self):
    if not isinstance(self.hands_off, int) or self.surge or not isinstance(self.day, (int, float)) \
            or self.day > SEED_RUSH_DAYS:
        return False
    if (self.st.get("plants_brewable") or 0) > 0 or (self.st.get("drink") or 0) >= max(1, self.cit or 0):
        return False
    if any(d(p).get("built") for p in lst(self.o.get("farm_plots"))):
        return False
    season = SEASON_NAMES[(self.game_doy() // SEASON_DAYS) % 4]
    return any((d(v).get("n") or 0) > 0 and d(v).get("underground") and season in lst(d(v).get("seasons"))
               for v in self.live_seeds_by_kind().values())
def rush_holds_digs(self):
    if not self.seed_rush():
        return False
    soil_left = any(r.get("soil") and r["id"] not in self.roles for r in self.undug_rooms())
    farm_waiting = any(v == "farm" for v in self.roles.values()) and not lst(self.o.get("farm_plots"))
    return soil_left or farm_waiting
def rush_signs(self, obs):
    if not self.seed_rush():
        return set()
    out = set()
    sites = [d(x) for x in lst(d(obs.get("map")).get("sites"))]
    for x in sites:
        if x.get("kind") == "R" and x.get("soil") and not x.get("designated") and x.get("id") not in self.roles:
            out.add("farm_room:%s" % x.get("id"))
        if x.get("kind") == "F" and not lst(obs.get("farm_plots")):
            out.add("farm_site:%s" % x.get("id"))
    return out
def cook_when(self, endgame=False):
    if endgame:
        food_gate = max(30, self.cit if self.days >= 336 else 4 * self.cit)
        when = [{"stock": "prepared_meals", "below": max(300, 10 * self.cit)},
                {"stock": "food_edible", "at_least": food_gate}]
    else:
        when = [{"stock": "prepared_meals", "below": MEAL_CAP}, {"stock": "plants_total", "at_least": 10}]
    if self.days >= COOK_RESERVE_DAYS and COOK_PLANTS_RESERVE > 0 and (not self.winter() or self.hold_cook()):
        when.append({"stock": "plants_brewable", "at_least": self.cook_floor()})
    return when
def cook_floor(self):
    if self.hold_cook():
        base = self.hold_floor() if "cook" not in self.allocation() else COOK_PLANTS_RESERVE
        return max(base, self.hold_reserve() + 2)
    if not self.alloc_on() or self.last_stretch():
        return COOK_PLANTS_RESERVE
    if "cook" not in self.allocation():
        return self.hold_floor()
    return max(COOK_PLANTS_RESERVE, self.base_plant_floor())
def seed_floor(self):
    left = self.days_to_end()
    if self.hands_off is None and ((left is not None and left <= HOLD_GROW_DAYS) or self.harvest_closed()):
        return 0
    plots = len(lst(self.o.get("farm_plots")))
    cit = getattr(self, "cit", None)
    if self.hands_off is not None and isinstance(cit, (int, float)) \
            and (d(getattr(self, "st", None)).get("drink") or 0) < 3 * cit:
        plots = max(plots, self.farm_target())
    return plots * SEEDS_PER_PLOT
def seed_guard(self):
    if self.hands_off is None:
        return
    floor, seeds = self.seed_floor(), self.st.get("seeds")
    if floor <= 0 or not isinstance(seeds, (int, float)) or isinstance(seeds, bool) or self.seeds_banked():
        return
    need = self.seed_need(floor)
    for x in self.orders:
        oid = x.get("id")
        if x.get("recipe") != "cook_meal" and x.get("job") != "PrepareMeal":
            continue
        if oid is None or oid in self.owned or not (x.get("repeat") or (x.get("left") or 0) > 0):
            continue
        if any(k[0] == "SEEDS" and t == "AtLeast" and isinstance(v, (int, float)) and v >= need
               for k, t, v in when_sig(x.get("when"))):
            continue
        r = self.act("seed_guard_%s" % oid, "cancel_order", {"order_id": oid}, retry=1, limit=3)
        if r is not None and r.get("ok"):
            log("seed_guard_cancel", day=self.day, order=oid, seeds=seeds, floor=floor)
def seed_census(self):
    if self.hands_off is None or (self.st.get("plants_brewable") or 0) > 0:
        return
    early = isinstance(self.day, (int, float)) and self.day <= SEED_CENSUS_EARLY_DAYS
    if self.census_day is not None and isinstance(self.day, (int, float)) \
            and self.day - self.census_day < (1 if early else SEED_CENSUS_DAYS):
        return
    query = getattr(self.game, "query", None)
    if query is None:
        return
    self.census_day = self.day
    out = {}
    for item_type in ("SEEDS", "PLANT_GROWTH"):
        try:
            raw = query("stocks", item_type=item_type)
        except Exception as e:
            log("seed_census_error", item_type=item_type, error=repr(e)[:160])
            continue
        r = query_result(raw)
        if r is None:
            log("seed_census_error", item_type=item_type, error=query_error(raw))
            continue
        groups = [d(g) for g in lst(r.get("groups"))]
        keys = ("rotten", "forbidden", "in_job", "in_building", "in_inventory", "construction")
        tot = {k: sum(int(g.get(k) or 0) for g in groups) for k in ("items", "count") + keys}
        free = sum(max(0, int(g.get("items") or 0) - sum(int(g.get(k) or 0) for k in
                                                       ("rotten", "forbidden", "in_building", "construction")))
                   for g in groups)
        out[item_type] = {**tot, "free_items": free,
                          "by_material": [{k: g.get(k) for k in ("material", "items", "count") + keys}
                                          for g in groups[:12]]}
    if not out:
        return
    self.census = out
    self.fruit_seen = d(out.get("PLANT_GROWTH")).get("free_items", 0) > 0
    log("seed_census", day=self.day, seeds=self.st.get("seeds"), **out)
    gone = self.seeds_not_in_query()
    if gone:
        log("seed_ghosts", day=self.day, kinds=gone)
def plant_census(self):
    if not lst(self.o.get("farm_plots")) or not isinstance(self.day, (int, float)):
        return
    if self.plant_census_day is not None and self.day - self.plant_census_day < PLANT_CENSUS_DAYS:
        return
    query = getattr(self.game, "query", None)
    if query is None:
        return
    self.plant_census_day = self.day
    try:
        raw = query("stocks", item_type="PLANT")
    except Exception as e:
        log("plant_census_error", error=repr(e)[:160])
        return
    r = query_result(raw)
    if r is None or not isinstance(r.get("groups"), list):
        return
    kinds = d(self.st.get("plants_by_kind"))
    total = brew = items = 0
    loose = boxed = 0
    for g in r.get("groups"):
        g = d(g)
        n_items, n_count = int(g.get("items") or 0), int(g.get("count") or 0)
        m = str(g.get("material") or "")
        pid = set((m.split(":")[1] if m.count(":") >= 2 else m).lower().split("_"))
        if n_items > 0 and any(d(v).get("brewable") and set(str(k).lower().split()) <= pid
                               for k, v in kinds.items()):
            per = n_count / n_items if n_count >= n_items else 1
            inv = int(g.get("in_inventory") or 0)
            if self.caravan_active and inv > 0:
                per = 1
            out = n_items - inv - int(g.get("in_building") or 0) - int(g.get("in_job") or 0) \
                - int(g.get("rotten") or 0)
            loose += round(max(0, out) * per)
            boxed += round(max(0, inv) * per)
        if int(g.get("rotten") or 0) >= n_items > 0:
            continue
        ib = int(g.get("in_building") or 0)
        n = max(0, ib - int(g.get("in_job") or 0))
        if n <= 0:
            continue
        units = (n_count * n + n_items // 2) // n_items if ib >= n_items > 0 and n_count >= n_items \
            else min(n, max(0, n_count - (n_items - ib)) if n_count else n)
        items += n
        total += units
        m = str(g.get("material") or "")
        pid = set((m.split(":")[1] if m.count(":") >= 2 else m).lower().split("_"))
        if any(d(v).get("brewable") and set(str(k).lower().split()) <= pid for k, v in kinds.items()):
            brew += units
    self.plant_loose = {"loose": loose, "contained": boxed, "day": self.day}
    self.loose_hist = [h for h in self.loose_hist if self.day - h[0] <= LOOSE_HIST_DAYS and h[0] < self.day]
    self.loose_hist.append([self.day, loose])
    prev = self.in_plot
    self.in_plot = {"total": total, "brewable": brew, "items": items}
    if prev is None or prev != self.in_plot:
        log("plant_census", day=self.day, in_plots=total, brewable=brew, pb=self.st.get("plants_brewable"),
            seeds=self.st.get("seeds"), sown=self.plot_tiles()[1])
    if brew >= HARVEST_STALL_MIN:
        if self.stall_since is None:
            self.stall_since = self.day
        if not self.stall_logged and self.day - self.stall_since >= HARVEST_STALL_DAYS:
            self.stall_logged = True
            jobs = {}
            for p in self.people:
                jobs[p.get("job")] = jobs.get(p.get("job"), 0) + 1
            log("harvest_stall", day=self.day, since=self.stall_since, in_plots=total, brewable=brew,
                seeds=self.st.get("seeds"), plots=self.plot_tiles(), barrels=self.st.get("barrels_empty"),
                alert=d(self.o.get("burrows")).get("civilian_alert"), plugins=self.o.get("plugins"),
                jobs=jobs, cancels=lst(self.o.get("recent_cancellations"))[:4])
    else:
        self.stall_since, self.stall_logged = None, False
def pb_free(self):
    pb = self.st.get("plants_brewable") or 0
    return max(0, pb - int(d(self.in_plot).get("brewable") or 0))
def fruit_census(self):
    if self.hands_off is not None or not isinstance(self.day, (int, float)):
        return self.fruit_seen
    if self.fruit_census_day is not None and self.day - self.fruit_census_day < 1:
        return self.fruit_seen
    query = getattr(self.game, "query", None)
    if query is None:
        return self.fruit_seen
    self.fruit_census_day = self.day
    try:
        raw = query("stocks", item_type="PLANT_GROWTH")
    except Exception as e:
        log("fruit_census_error", error=repr(e)[:160])
        return self.fruit_seen
    r = query_result(raw)
    if r is None or not isinstance(r.get("groups"), list):
        return self.fruit_seen
    free = sum(max(0, int(d(g).get("items") or 0) - sum(int(d(g).get(k) or 0) for k in
                                                        ("rotten", "forbidden", "in_building", "construction")))
               for g in r.get("groups"))
    self.fruit_seen = free > 0
    log("fruit_census", day=self.day, free=free, drink=self.st.get("drink"))
    return self.fruit_seen
def sown_seeds(self):
    tiles, sicp = self.plot_tiles()
    ripe = int(d(self.in_plot).get("items", d(self.in_plot).get("total")) or 0)
    return max(0, sicp - ripe)
def free_seeds(self):
    seeds = self.st.get("seeds")
    if not isinstance(seeds, (int, float)) or isinstance(seeds, bool):
        return 0
    return max(0, int(seeds) - self.sown_seeds())
def seed_need(self, floor=None):
    floor = self.seed_floor() if floor is None else floor
    if floor <= 0:
        return 0
    return max(0, floor - self.sown_seeds())
def seeds_banked(self):
    return self.free_seeds() >= self.seed_need()
def seed_clause_dead(self, x):
    floors = [v for k, t, v in when_sig(x.get("when")) if k[0] == "SEEDS" and t == "AtLeast"
              and isinstance(v, (int, float))]
    return bool(floors) and max(floors) > self.free_seeds()
def brew_shots_queued(self):
    out = [(x, self.brew_shots[x.get("id")]) for x in self.orders
           if x.get("id") in self.brew_shots and not x.get("repeat") and (x.get("left") or 0) > 0]
    return sorted(out, key=lambda p: p[0].get("id") or 0)
def brew_queued(self):
    return sum(max(0, x.get("left") or 0) for x, _ in self.brew_shots_queued())
def brew_budget(self):
    return self.pb_free() - self.brew_queued()
def brew_shot_allow(self, key):
    allow = self._brew_shot_allow(key)
    pb = self.plant_barrel()
    if pb is not None and pb[0] > 0:
        allow = min(allow, max(0, pb[0] - BARREL_KEEP))
    return allow
def _brew_shot_allow(self, key):
    free = self.pb_free()
    if not self.alloc_on():
        return free
    plan = self.plant_plan()
    if plan["lean"]:
        return free
    if key == "o_brew_rot":
        if plan["in_f"] and plan["food_first"]:
            return 0
        return free - plan["rot_keep"]
    if key == "o_brew_seed":
        return self.regrow_cap() if plan["hold"] else free
    if "brew" not in plan["sides"]:
        return 0
    return free - plan["floor"]
def brew_shot_trim(self):
    queued = self.brew_shots_queued()
    if not queued:
        return
    rank = {k: i for i, k in enumerate(BREW_SHOT_KEYS)}
    queued.sort(key=lambda p: (rank.get(p[1], len(rank)), p[0].get("id") or 0))
    allow = {}
    held = 0
    for x, key in queued:
        if key not in allow:
            allow[key] = self.brew_shot_allow(key)
        left = max(0, x.get("left") or 0)
        if held >= allow[key]:
            oid = x.get("id")
            r = self.act("brew_trim_%s" % oid, "cancel_order", {"order_id": oid}, retry=2, limit=3)
            if r is not None and r.get("ok"):
                log("brew_trim", day=self.day, order=oid, source=key, left=left, held=held, allow=allow[key],
                    pb=self.st.get("plants_brewable"), pb_free=self.pb_free(), sides=sorted(self.allocation()))
            continue
        held += left
def seeds_not_in_query(self):
    groups = lst(d(d(self.census).get("SEEDS")).get("by_material"))
    if not d(self.census).get("SEEDS"):
        return {}
    have = {}
    for g in groups:
        m = str(d(g).get("material") or "")
        pid = m.split(":")[1] if m.count(":") >= 2 else m
        have[pid] = have.get(pid, 0) + int(d(g).get("count") or 0)
    out = {}
    for name, k in d(self.st.get("seeds_by_kind")).items():
        n = int(d(k).get("n") or 0)
        words = set(str(name).lower().split())
        got = sum(c for pid, c in have.items() if words and words <= set(pid.lower().split("_")))
        if n > got:
            out[name] = n - got
    return out
def live_seeds_by_kind(self):
    seeds = d(self.st.get("seeds_by_kind"))
    fresh = self.census_day is not None and isinstance(self.day, (int, float)) \
        and self.day - self.census_day <= SEED_CENSUS_DAYS
    if not fresh:
        return seeds
    gone = self.seeds_not_in_query()
    if not gone:
        return seeds
    out = {}
    for name, v in seeds.items():
        n = int(d(v).get("n") or 0) - gone.get(name, 0)
        if n > 0:
            out[name] = {**d(v), "n": n}
    return out
def note_room_box(self, site, args):
    a, s = d(args), d(site)
    box = {k: a.get(k, s.get(k)) for k in ("x", "y", "z")}
    box["w"] = a.get("w", s.get("w", 3))
    box["h"] = a.get("h", s.get("h", 3))
    if s.get("id") is not None:
        self.room_box[s["id"]] = box
def room_taken(self, s):
    for rid, box in self.room_box.items():
        if rid == s.get("id") or str(self.roles.get(rid) or "").startswith("farm"):
            continue
        if self.rects_overlap(box, s):
            return True
    return False
def cook_order(self, when, amount=2):
    sf = self.seed_floor()
    if sf <= 0 or not self.seeds_cond_ok:
        return "add_order", {"recipe": "cook_meal", "amount": amount, "repeat": "daily", "when": list(when)}
    items = [as_item(c) for c in when]
    seeds = {"item_type": "SEEDS", "at_least": self.seed_need(sf)}
    if len(items) >= 3:
        items[1] = seeds
    else:
        items.append(seeds)
    return "add_manager_order", {"job": "PrepareMeal", "amount": amount, "repeat": "daily", "when": items}
def cook_act(self, key, tool, args, retry=3, limit=6):
    r = self.act(key, tool, args, retry=retry, limit=limit)
    if r is not None and not r.get("ok") and tool == "add_manager_order" \
            and r.get("error_code") == "bad_arguments":
        self.seeds_cond_ok = False
        self.last.pop(key, None)
        log("seeds_cond_off", key=key, err=str(r.get("error") or "")[:160])
    return r
def cook_standing(self, endgame):
    oid = self.key_order.get("o_cook_end" if endgame else "o_cook")
    if oid is not None:
        x = next((x for x in self.orders if x.get("id") == oid and x.get("repeat")), None)
        if x is not None:
            return x
    skip = {oid for oid in (self.key_order.get("o_winter_cook"), self.key_order.get("o_cook"),
                            self.key_order.get("o_cook_end")) if oid is not None}
    for x in self.orders:
        if x.get("recipe") != "cook_meal" or not x.get("repeat") or x.get("id") not in self.owned:
            continue
        if x.get("id") in skip:
            continue
        stocks = {d(w).get("stock") for w in lst(x.get("when"))}
        if ("food_edible" in stocks) == endgame and (endgame or "plants_total" in stocks):
            return x
    return None
def cook_when_same(self, have, want):
    hs, ws = when_sig(have), when_sig(want)
    if hs == ws:
        return True
    if len(hs) != len(ws):
        return False
    free = self.free_seeds()
    for (hk, ht, hv), (wk, wt, wv) in zip(hs, ws):
        if (hk, ht) != (wk, wt):
            return False
        if hv == wv:
            continue
        if hk[0] != "SEEDS" or not all(isinstance(v, (int, float)) for v in (hv, wv)):
            return False
        if (hv > free and free - wv >= SEED_COND_TOL) or hv < wv - SEED_COND_TOL:
            return False
    return True
def sync_cook(self, key, desired):
    st = self.cook_standing(key == "o_cook_end")
    if st is None or self.cook_when_same(st.get("when"), desired):
        return False
    if self.may(key + "_recut", 4):
        self.act(key + "_recut", "cancel_order", {"order_id": st.get("id")}, retry=2, limit=8)
        self.done.discard(key)
    return True
def brew_cap(self):
    if self.my1_plan() and self.hold_active():
        left = self.days_to_end() or 0
        return max(HOLD_DRY_DAYS, int(math.ceil(self.f_drink_rate() * left)))
    return max(200, DRINK_PER_CIT_YEAR * self.cit)
def brew_amount(self):
    if self.my1_plan() and self.hold_active():
        return 1
    if self.food_lean():
        return LEAN_BREW_AMOUNT
    gap = max(0, self.brew_cap() - (self.st.get("drink") or 0))
    if self.barrel_keep():
        return max(1, min(BARREL_KEEP_AMOUNT, gap // 10))
    return max(1, min(10, gap // 10))
def barrel_keep(self):
    return self.alloc_on() and (self.days or 0) < 336 and not self.food_lean() and not self.hold_active() \
        and not self.last_stretch()
def plant_barrel(self):
    if not self.alloc_on() or (self.days or 0) >= 336 or not isinstance(self.day, (int, float)):
        return None
    p = d(self.plant_loose)
    if not isinstance(p.get("day"), (int, float)) or self.day - p["day"] > PLANT_BARREL_FRESH_DAYS:
        return None
    if not isinstance(p.get("contained"), int) or not isinstance(p.get("loose"), int):
        return None
    return p["contained"], p["loose"]
def barrel_brew_cap(self):
    pb = self.plant_barrel()
    if pb is None or pb[0] <= 0:
        return None
    return max(0, pb[0] - BARREL_KEEP - self.brew_queued())
def meal_wait(self):
    pb = self.plant_barrel()
    if pb is None or pb[0] > 0 or pb[1] <= 0:
        self.barrel_lost_day = None
        return False
    if self.barrel_lost_day is None:
        self.barrel_lost_day = self.day
    return self.day - self.barrel_lost_day < PLANT_BARREL_WAIT_DAYS
def brew_planned(self):
    drink = self.st.get("drink") or 0
    n = 0
    for x in self.orders:
        if x.get("recipe") != "brew_drink":
            continue
        if not x.get("repeat"):
            n += max(0, x.get("left") or 0)
            continue
        if x.get("active") is False:
            continue
        caps = [v for k, t, v in when_sig(x.get("when")) if k == ("DRINK", None) and t == "LessThan"
                and isinstance(v, (int, float))]
        if caps and drink >= min(caps):
            continue
        left = x.get("left") if isinstance(x.get("left"), (int, float)) else 0
        n += max(0, left if left > 0 else (x.get("total") or 0))
    return min(n, self.st.get("plants_brewable") or 0)
def harvest_growing(self):
    tiles, sown = self.plot_tiles()
    if sown <= 0:
        return 0.0
    brew_sown = 0
    for p in lst(self.o.get("farm_plots")):
        p = d(p)
        w, h, n = p.get("w"), p.get("h"), p.get("seeds_or_crops_in_plot")
        if p.get("built") is False or not all(isinstance(v, int) and not isinstance(v, bool) for v in (w, h, n)):
            continue
        if self.crop_brewable(p.get("crop_this_season")):
            brew_sown += n
    ripe_items = int(d(self.in_plot).get("items", d(self.in_plot).get("total")) or 0)
    ripe = int(d(self.in_plot).get("total") or 0)
    growing = max(0, sown - ripe_items) * HARVEST_YIELD + min(ripe, sown)
    return growing * brew_sown / sown
def crop_brewable(self, crop):
    pid = set(str(crop or "").lower().split("_"))
    for name, ok in self.kind_brew.items():
        words = set(str(name).lower().split())
        if words and words <= pid:
            return bool(ok)
    return True
def harvest_furniture_lean(self):
    if self.surge or not self.barrel_press() or not self.press_harv:
        return False
    left = self.days_to_end()
    return left is None or left > ENDGAME_DAYS
def harvest_barrels_short(self):
    if self.hands_off is not None or not (self.days >= 336 or self.rot_seen) or self.food_lean():
        return 0
    be = self.st.get("barrels_empty") or 0
    if be >= PRESS_BARRELS_FREE and self.pb_free() - self.brew_planned() >= HARVEST_IDLE_PLANTS:
        return 0
    want = min(BARREL_AHEAD_MAX, int(math.ceil(self.pb_free() + self.harvest_growing())))
    return max(0, want - be)
def brew_standing(self):
    oid = self.key_order.get("o_brew")
    if oid is None:
        return None
    return next((x for x in self.orders if x.get("id") == oid and x.get("recipe") == "brew_drink"
                 and x.get("repeat")), None)
def sync_brew(self):
    st = self.brew_standing()
    if st is None or (self.caravan_active and not self.hold_active()):
        return False
    want = self.brew_when()
    have_sig, want_sig = when_sig(st.get("when")), when_sig(want)
    gate, cap = (have_sig[0][2] if have_sig else None), want_sig[0][2]
    if isinstance(gate, (int, float)) and not isinstance(gate, bool) \
            and abs(gate - cap) <= 0.3 * cap and self.brew_rest_same(have_sig[1:], want_sig[1:]):
        return False
    if self.may("o_brew_recut", 4):
        self.act("o_brew_recut", "cancel_order", {"order_id": st.get("id")}, retry=2, limit=8)
    return True
@staticmethod
def brew_rest_same(have, want):
    if len(have) != len(want):
        return False
    for (hk, ht, hv), (wk, wt, wv) in zip(have, want):
        if (hk, ht) != (wk, wt):
            return False
        if hv == wv:
            continue
        if hk != ("PLANT", "DRINK_MAT") or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                   for v in (hv, wv)):
            return False
        if min(hv, wv) <= 2 or abs(hv - wv) > BREW_FLOOR_TOL * max(hv, wv):
            return False
    return True
def brew_on_book(self):
    if self.brew_standing() is not None:
        return True
    want = when_sig(self.brew_when())
    cap, floor = want[0][2], want[1][2]
    for x in self.orders:
        if x.get("recipe") != "brew_drink" or not x.get("repeat"):
            continue
        ok = True
        for k, t, v in when_sig(x.get("when")):
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                ok = False
            elif k == ("DRINK", None) and t == "LessThan":
                ok = ok and v >= cap
            elif k == ("PLANT", "DRINK_MAT") and t == "AtLeast":
                ok = ok and v <= floor
            elif k == ("BARREL", None) and t == "AtLeast":
                ok = ok and v <= 1
            else:
                ok = False
        if ok and self.barrel_keep() and not self.keeps_barrel(x.get("total") or x.get("left"), x.get("when"), True):
            ok = False
        if ok:
            return True
    return False
def brew_floor(self):
    if self.my1_plan() and self.hold_active():
        return self.hold_reserve() + 1
    if self.food_lean():
        return 1
    if self.hold_active():
        if self.my1_plan():
            return self.hold_reserve() + 1
        return self.hold_reserve() + HOLD_STANDING_MARGIN
    if self.alloc_on() and "brew" not in self.allocation():
        return self.hold_floor()
    if self.hands_off is not None:
        return 1
    if self.barrel_keep():
        pb = self.plant_barrel()
        return BARREL_KEEP_AMOUNT + BARREL_KEEP + (pb[1] if pb is not None and pb[0] > 0 else 0)
    return 2
def brew_when(self):
    cap = self.lean_drink if self.food_lean() else self.brew_cap()
    return [{"stock": "drink", "below": cap},
            {"stock": "plants_brewable", "at_least": self.brew_floor()},
            {"stock": "barrels_empty", "at_least": 1}]
def surge_start_brew(self):
    if not self.surge or "o_brew_start" in self.done or not isinstance(self.hands_off, int) \
            or self.hands_off <= WINDOW_PREP_DAYS:
        return
    pb = self.st.get("plants_brewable")
    food = self.st.get("food_edible")
    if not isinstance(pb, int) or isinstance(pb, bool) or pb <= 0 or not isinstance(food, (int, float)):
        return
    if food - pb < SURGE_START_FOOD * (self.cit or 0):
        return
    r = self.act("o_brew_start", "add_order", {"recipe": "brew_drink", "amount": min(pb, RECYCLE_MAX)},
                 retry=1, limit=4)
    if r is not None and r.get("ok"):
        self.done.add("o_brew_start")
        log("surge_start_brew", day=self.day, amount=min(pb, RECYCLE_MAX), food=food, cit=self.cit)
def supply(self):
    f_yield = self.f_keeper_yield()
    if f_yield:
        st = self.brew_standing()
        if st is not None:
            r = self.act("o_brew_fyield", "cancel_order", {"order_id": st.get("id")}, retry=1, limit=4)
            if r is not None and r.get("ok"):
                log("f_keeper_yield", day=self.day, order=st.get("id"), drink=self.st.get("drink"),
                    food=self.st.get("food_edible"))
    if not f_yield and not self.surge_hold() and not self.sync_brew() and not self.brew_on_book() \
            and not self.caravan_active:
        self.act("o_brew", "add_order", {"recipe": "brew_drink", "amount": self.brew_amount(),
                                         "repeat": "daily", "when": self.brew_when()}, retry=3)
    if not self.standing("make_barrel"):
        self.act("o_barrel", "add_order", {"recipe": "make_barrel", "amount": 2, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 4}, {"stock": "logs", "at_least": 2}]}, retry=3)
    be = self.st.get("barrels_empty") or 0
    need = self.brew_planned() - be
    if self.hands_off is None and (self.days >= 336 or self.rot_seen) and not self.food_lean():
        need = max(need, self.harvest_barrels_short())
    spare = self.logs() - self.logs_guard()
    pend = sum(max(0, x.get("left") or 0) for x in self.orders
               if x.get("recipe") == "make_barrel" and not x.get("repeat"))
    if self.hands_off is None and self.barrel_press():
        carp = sum(1 for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Carpenters")
        room = min(need, PRESS_JOBS_PER_BENCH * max(1, carp)) - pend
        if room >= 1 and spare >= 1:
            self.act("o_barrel_need", "add_order", {"recipe": "make_barrel",
                                                    "amount": min(PRESS_BARREL_BATCH, max(room, need - pend), spare)},
                     retry=1, limit=99)
    elif self.hands_off is None and need >= 4 and spare >= 1 and not pend:
        self.act("o_barrel_need", "add_order", {"recipe": "make_barrel", "amount": min(10, need, spare)},
                 retry=2, limit=99)
    tool, args = self.cook_order(self.cook_when())
    if not self.surge_hold() and not self.sync_cook("o_cook", args["when"]) and not self.regular_cook_on_book():
        self.cook_act("o_cook", tool, args, retry=3)
    if (self.st.get("drink") or 0) < 3 * self.cit and not self.st.get("plants_brewable") \
            and not self.caravan_active and not self.pending("brew_drink_from_fruit") and self.fruit_census():
        self.act("o_fruit", "add_order", {"recipe": "brew_drink_from_fruit", "amount": 3}, retry=4)
    seats = math.ceil(self.cit / 2) + 2
    cap = math.ceil(self.cit / 2)
    lean_furn = self.harvest_furniture_lean()
    full = self.seats_full()
    for recipe, have, want in (("make_bed", self.st.get("beds") or 0, self.bed_target()),
                               ("make_table", self.st.get("tables") or 0,
                                max(seats, full) + min(cap, self.stray("table"))),
                               ("make_chair", self.st.get("chairs") or 0,
                                self.chair_target(max(seats, full)) + min(cap, self.stray("chair")))):
        if lean_furn:
            want = min(want, {"make_bed": self.cit, "make_table": cap}.get(recipe) or self.chair_target(cap))
            key = "o_" + recipe
            oid = self.key_order.get(key)
            mine = next((x for x in self.orders if oid is not None and x.get("id") == oid), None)
            if mine is not None and have >= want and (mine.get("left") or 0) > 0:
                r = self.act("furn_yield_" + recipe, "cancel_order", {"order_id": oid}, retry=1, limit=99)
                if r is not None and r.get("ok"):
                    log("furniture_yield", day=self.day, recipe=recipe, order=oid, left=mine.get("left"),
                        have=have, want=want, barrels=self.st.get("barrels_empty"))
                continue
        if self.surge and recipe == "make_bed":
            self.surge_bed_orders(have, want)
            continue
        if self.surge and self.surge_beds_short():
            continue
        if have < want and not self.pending(recipe) and self.logs():
            batch = 30 if (recipe == "make_bed" and self.surge) else 8
            self.act("o_" + recipe, "add_order", {"recipe": recipe, "amount": min(batch, want - have)}, retry=1, limit=99)
def glut_bank(self):
    if self.caravan_active and self.glut_jump >= GLUT_JUMP and self.caravan_arrival_day is not None \
            and (self.day or 0) - self.caravan_arrival_day <= 1:
        return
    if self.days_left is not None and self.days_left <= BREW_SPARE_DAYS and self.food_min_leg():
        return
    if self.drink_glut():
        return
    plan = self.plant_plan() if self.alloc_on() else None
    if plan is not None and "brew" not in plan["sides"]:
        return
    pb = self.st.get("plants_brewable") or 0
    amount = min(5, self.brew_budget() - (plan["floor"] if plan is not None else 0))
    bcap = self.barrel_brew_cap()
    if bcap is not None:
        amount = min(amount, bcap)
    if amount < 1:
        return
    if self.glut_jump >= GLUT_JUMP or pb >= GLUT_PB:
        self.act("o_brew_glut", "add_order", {"recipe": "brew_drink", "amount": amount},
                 retry=1, limit=99)
def window_days(self):
    if isinstance(self.hands_off, int) and 0 < self.hands_off:
        return self.hands_off
    if self.days_left is not None:
        return max(0, self.days_left - ENDGAME_DAYS)
    return max(0, (self.days or 0) - ENDGAME_DAYS - (self.day or 0))
def winter_needs(self):
    w = self.window_days()
    return (int(WINTER_DRINK_PER_CIT * self.cit + self.use_rate("drink", DRINK_PER_CIT_DAY) * self.cit * w),
            int(WINTER_FOOD_PER_CIT * self.cit + self.use_rate("food", FOOD_PER_CIT_DAY) * self.cit * w))
def winter_plan(self):
    if self.days < 180 or self.caravan_active or self.day is None or self.winter():
        return
    plan_day = self.calendar_day(WINTER_PLAN_DOY, min(WINTER_PLAN_LATE_DAY, self.days - WINTER_PLAN_LOOKAHEAD))
    if (self.day or 0) < plan_day:
        return
    year = int(self.day) // YEAR_DAYS
    if self.winter_plan_year == year:
        return
    drink_need, food_need = self.winter_needs()
    short_drink = drink_need - (self.st.get("drink") or 0)
    short_food = food_need - (self.st.get("food_edible") or 0)
    seeds = d(self.st.get("seeds_by_kind"))
    winter_seeds = any(isinstance(k, dict) and "winter" in lst(k.get("seasons")) for k in seeds.values())
    ok = True
    if short_drink > 0:
        when = [{"stock": "plants_brewable", "at_least": 2}, {"stock": "barrels_empty", "at_least": 1}]
        if self.hold_active():
            when[0]["at_least"] = self.hold_reserve() + 4
        if winter_seeds:
            when.insert(0, {"stock": "drink", "below": drink_need})
        ok &= bool(d(self.act("o_winter_brew", "add_order", {"recipe": "brew_drink", "amount": 4,
                                                             "repeat": "daily", "when": when},
                              retry=3, limit=6)).get("ok"))
    if short_food > 0:
        plants = {"stock": "plants_total", "at_least": 10}
        if self.hold_cook():
            plants = {"stock": "plants_brewable", "at_least": max(10, self.hold_reserve() + 2)}
        tool, args = self.cook_order([{"stock": "prepared_meals", "below": max(300, food_need)}, plants])
        ok &= bool(d(self.cook_act("o_winter_cook", tool, args, retry=3, limit=6)).get("ok"))
    if ok:
        self.winter_plan_year = year
    log("winter_plan", day=self.day, cit=self.cit, drink_need=drink_need, food_need=food_need,
        short_drink=short_drink, short_food=short_food, winter_seeds=winter_seeds, planned=ok)
def in_endgame(self):
    return self.hands_off is None and self.days_left is not None and self.days_left <= ENDGAME_DAYS
def in_window_prep(self):
    return isinstance(self.hands_off, int) and 0 < self.hands_off <= WINDOW_PREP_DAYS
def closer(self):
    slide = self.stock_sliding()
    if self.in_endgame() or slide:
        self.endgame_supply()
        if self.in_endgame():
            self.housing_check()
    elif self.in_window_prep():
        self.surge_window_hold()
        self.window_supply()
        self.housing_check()
    if self.surge:
        carp = sum(1 for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Carpenters")
        if carp == 1 and self.cit >= 15 and self.logs() >= 5:
            self.build("Carpenters", retry=3)
        elif 2 <= carp < SURGE_CARPENTERS and self.cit >= SURGE_CARP_CIT and self.logs() >= 5 \
                and self.surge_beds_short():
            self.build("Carpenters", key="ws_Carpenters_surge_%d" % (carp + 1), retry=3)
