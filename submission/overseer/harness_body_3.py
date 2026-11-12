"""Overseer class body, part 3 of 4. Not a module of its own: harness.py executes this file inside `class Overseer`, with harness.py's globals, after part 2."""
def endgame_supply(self):
    cap = max(600, 30 * self.cit)
    reserve = BREW_END_FLOOR
    if self.hold_active():
        reserve = self.hold_reserve() + 4
    spare = (self.days_left is not None and self.days_left <= BREW_SPARE_DAYS and self.food_min_leg()) \
        or (self.alloc_on() and "brew" not in self.allocation())
    if spare:
        end_id = self.key_order.get("o_brew_end")
        if end_id is not None and end_id in self.owned:
            self.act("o_brew_end_retire", "cancel_order", {"order_id": end_id}, retry=4, limit=8)
            self.done.discard("o_brew_end")
    else:
        self.act("o_brew_end", "add_order", {"recipe": "brew_drink", "amount": 4, "repeat": "daily", "when": [
            {"stock": "drink", "below": cap}, {"stock": "plants_brewable", "at_least": reserve},
            {"stock": "barrels_empty", "at_least": 1}]}, retry=3, limit=4)
    self.act("o_barrel_end", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
        {"stock": "barrels_empty", "below": 8}, {"stock": "logs", "at_least": 4}]}, retry=3, limit=4)
    tool, args = self.cook_order(self.cook_when(endgame=True))
    if not self.sync_cook("o_cook_end", args["when"]):
        self.cook_act("o_cook_end", tool, args, retry=3, limit=4)
    if (self.st.get("food_edible") or 0) < 4 * self.cit:
        self.butcher()
def surge_hold(self):
    return self.surge and self.in_window_prep()
def surge_window_hold(self):
    if not self.surge_hold():
        return
    for key in ("o_brew", "o_cook"):
        oid = self.key_order.get(key)
        if oid is not None and any(x.get("id") == oid for x in self.orders):
            self.act(key + "_hold", "cancel_order", {"order_id": oid}, retry=1, limit=4)
    food_ok = (self.st.get("food_edible") or 0) >= SURGE_FOOD_SAFE * self.cit
    mine = {self.key_order.get(k) for k in ("o_cook_food", "o_brew_win", "o_brew_bridge_win")} - {None}
    drink = self.st.get("drink") or 0
    for x in self.orders:
        if not x.get("repeat") or x.get("id") in mine or x.get("recipe") not in ("cook_meal", "brew_drink"):
            continue
        stocks = {d(w).get("stock") for w in lst(x.get("when"))}
        if x.get("recipe") == "cook_meal" and ("plants_brewable" in stocks or not food_ok):
            continue
        if x.get("recipe") == "brew_drink" and any(
                t == "LessThan" and isinstance(v, (int, float)) and v <= drink and k[0] == "DRINK"
                for k, t, v in when_sig(x.get("when"))):
            continue
        self.act("plant_hold_%s" % x.get("id"), "cancel_order", {"order_id": x.get("id")}, retry=2, limit=3)
def window_supply(self):
    if not self.surge or not isinstance(self.hands_off, int) or self.hands_off <= self.surge_brew_lead():
        self.act("o_brew_win", "add_order", {"recipe": "brew_drink", "amount": 5, "repeat": "daily", "when": [
            {"stock": "plants_brewable", "at_least": 2},
            {"stock": "food_edible", "at_least": max(3, self.cit // 2)},
            {"stock": "barrels_empty", "at_least": 1}]}, retry=1 if self.surge else 2, limit=5)
    self.act("o_barrel_win", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
        {"stock": "barrels_empty", "below": 10}, {"stock": "logs", "at_least": 3}]}, retry=2, limit=5)
    self.window_bridge()
    self.fruit_watch()
    if (self.st.get("food_edible") or 0) < 4 * self.cit:
        self.butcher()
def window_bridge(self):
    if not self.surge or not isinstance(self.hands_off, int) or self.hands_off <= 0 or "o_brew_bridge_win" in self.done:
        return
    drink, cit = self.st.get("drink"), self.cit or 0
    if not isinstance(drink, (int, float)) or isinstance(drink, bool) or cit <= 0:
        return
    cap = int(round(drink - SURGE_BRIDGE_RATE * cit * self.hands_off))
    win = (self.days_left - self.hands_off) if isinstance(self.days_left, int) and self.days_left > self.hands_off \
        else 21
    need = math.ceil(SURGE_WINDOW_USE * cit * win / BREW_DRINKS)
    amount = max(2, min(5, math.ceil(3 * need / win)))
    r = self.act("o_brew_bridge_win", "add_order", {"recipe": "brew_drink", "amount": amount, "repeat": "daily",
                                                    "when": [{"stock": "drink", "below": cap},
                                                             {"stock": "plants_brewable", "at_least": 2},
                                                             {"stock": "food_edible", "at_least": max(3, cit // 2)}]},
                 retry=1, limit=5)
    if r is not None:
        log("window_bridge", day=self.day, cap=cap, drink=drink, cit=cit, hands_off=self.hands_off, window=win,
            need=need, amount=amount, ok=bool(r.get("ok")))
def surge_brew_lead(self):
    gaps = [b - a for a, b in zip(self.pass_days, self.pass_days[1:])][-3:]
    return min(SURGE_BREW_LEAD_MAX, SURGE_BREW_LEAD + max([0] + gaps))
def fruit_watch(self):
    if self.surge or not isinstance(self.hands_off, int):
        return
    cap = max(1, FRUIT_WIN_DRINK_PER_CIT * self.cit)
    if (self.st.get("drink") or 0) >= cap:
        return
    self.act("o_fruit_win", "add_manager_order", {
        "job": "CustomReaction", "reaction": "BREW_DRINK_FROM_PLANT_GROWTH", "amount": 1, "repeat": "daily",
        "when": [{"item_type": "PLANT_GROWTH", "flags": ["unrotten"], "reaction_product": "DRINK_MAT",
                  "at_least": 1},
                 {"item_type": "BARREL", "flags": ["empty"], "at_least": 1},
                 {"item_type": "DRINK", "below": cap}]}, retry=2, limit=5)
def ordered_now(self, key):
    return self.last.get(key) == self.now
def housing_check(self):
    beds_short = self.cit - (self.placed.get("bed") or 0)
    if beds_short > 0 and (self.st.get("beds") or 0) < self.cit + 2 and self.logs() >= 2 \
            and not self.pending("make_bed") and not self.ordered_now("o_make_bed"):
        self.act("o_bed_close", "add_order", {"recipe": "make_bed", "amount": min(30, max(2, beds_short + 2))},
                 retry=2, limit=10)
    if self.surge and beds_short > 0:
        return
    seats_short = math.ceil(self.cit / 2) - self.seats()
    if seats_short > 0 and self.logs() >= 2:
        want = math.ceil(self.cit / 2) + 1
        for recipe, kind in (("make_table", "table"), ("make_chair", "chair")):
            have = (self.placed_dry(kind) if self.breach else self.dine_count(kind)) + (self.free.get(kind) or 0)
            goal = max(want, self.dine_count("table")) if kind == "chair" and not self.breach else want
            if have < goal and not self.pending(recipe) and not self.ordered_now("o_" + recipe):
                r = self.act("o_%s_close" % recipe, "add_order", {"recipe": recipe, "amount": min(30, goal - have)},
                             retry=2, limit=10)
                if r is not None:
                    log("housing_close", day=self.day, item=kind, have=have, stock=self.st.get(kind + "s"),
                        want=want, seats=self.seats(), cit=self.cit)
def seats_full(self):
    if self.surge or self.breach or self.harvest_furniture_lean():
        return 0
    cit = self.cit or 0
    short = max(0, cit - (self.st.get("tables") or 0)) + max(0, cit - (self.st.get("chairs") or 0))
    if short and self.logs() - self.logs_guard() < short:
        return 0
    return cit
def seats(self):
    n = 0
    for z in self.zone("dining"):
        f = d(z.get("furniture"))
        n += min(f.get("table") or 0, f.get("chair") or 0)
    return n
def rezone(self):
    loose, by_z, handled = {}, {}, set()
    dining = {z.get("id") for z in self.zone("dining")}
    for f in lst(self.o.get("furniture")):
        f = d(f)
        if not f.get("built") or f.get("kind") not in ("bed", "table", "chair"):
            continue
        if not f.get("zone_ids"):
            loose.setdefault(f.get("z"), set()).add(f.get("kind"))
        if f.get("kind") != "bed" and not dining & set(lst(f.get("zone_ids"))):
            by_z.setdefault(f.get("z"), {}).setdefault(f["kind"], 0)
            by_z[f.get("z")][f["kind"]] += 1
    for z, kinds in loose.items():
        site = next((x for x in self.closed_a() if x.get("z") == z and self.area_fits(x, ZONE_MAX)
                     and not self.farm_claimed(x)), None)
        if not site:
            site = next((x for x in self.dug_rooms() if x.get("z") == z
                         and not self.roles.get(x["id"], "").startswith("farm")
                         and self.roles.get(x["id"]) != "office" and not self.farm_claimed(x)), None)
        if not site:
            continue
        if kinds & {"table", "chair"}:
            r = self.act("rz_dine_%s" % site["id"], "make_zone", {"kind": "dining_hall", "site": site["id"]}, retry=2, limit=3)
            if r and r.get("ok"):
                handled.add(("lz_dine_", z))
        if "bed" in kinds:
            r = self.act("rz_dorm_%s" % site["id"], "make_zone", {"kind": "dormitory", "site": site["id"]}, retry=2, limit=3)
            if r and r.get("ok"):
                handled.add(("lz_dorm_", z))
    for z, kinds in by_z.items():
        if kinds.get("table") and kinds.get("chair"):
            site = next((x for x in self.closed_a() if x.get("z") == z and (x.get("open_tiles") or 0) >= 6
                         and self.area_fits(x, ZONE_MAX) and not self.farm_claimed(x)), None)
            if site:
                r = self.act("dx_dine_%s" % site["id"], "make_zone", {"kind": "dining_hall", "site": site["id"]}, retry=3, limit=2)
                if r and r.get("ok"):
                    handled.add(("lz_dine_", z))
    self.zone_loose(handled)
def wealth_created(self):
    return d(self.o.get("wealth")).get("created") or 0
def wealth_target(self):
    if self.days < 336 or (self.day or 0) > PROGRESS_LAST_DAY or self.cit >= 20:
        return WEALTH_TARGET
    return max(WEALTH_TARGET, (WAVE_POP_TARGET + WAVE_POP_BUFFER) * WAVE_WEALTH_PER_CIT)
def furniture_logs_needed(self):
    seats = math.ceil(self.cit / 2) + 2
    beds_short = max(0, self.bed_target() - (self.st.get("beds") or 0))
    seats_short = max(0, seats - (self.st.get("tables") or 0)) + max(0, seats + 1 - (self.st.get("chairs") or 0))
    barrels_short = max(0, BARREL_GUARD - (self.st.get("barrels_empty") or 0))
    return beds_short + seats_short + barrels_short
def logs_guard(self):
    return LOG_RESERVE + self.furniture_logs_needed()
def craft_amount_chase(self):
    gap = self.wealth_target() - self.wealth_created()
    window_left = max(1, PROGRESS_LAST_DAY - (self.day or 0))
    cday, cfund = self.craft_checkpoint()
    cgap, cleft = cfund - self.wealth_created(), max(1, cday - (self.day or 0))
    if self.craft_mark is not None:
        d0, w0 = self.craft_mark
        span = (self.day or 0) - d0
        if span >= CRAFT_RATE_SPAN:
            rate = (self.wealth_created() - w0) / span
            if rate * window_left * CRAFT_RATE_MARGIN >= gap and rate * cleft * CRAFT_RATE_MARGIN >= cgap:
                return CRAFT_AMOUNT_BASE
    return CRAFT_AMOUNT_WAVE
def craft_checkpoint(self):
    day = self.day or 0
    for (cday, fund), doy in zip(CRAFT_CHECKPOINTS, CRAFT_CHECKPOINT_DOYS):
        cday = self.calendar_day(doy, cday)
        if day < cday:
            return cday, min(fund, self.wealth_target())
    return PROGRESS_LAST_DAY, self.wealth_target()
def progress(self):
    if self.days < 336 or (self.day or 0) < PROGRESS_FROM_DAY or self.cit < 7:
        return
    self.progress_record()
    met = self.wealth_created() >= self.wealth_target()
    chasing = (self.day or 0) <= PROGRESS_LAST_DAY and self.cit < 20 and not met
    shops = [w for w in lst(self.o.get("workshops"))
             if isinstance(w, dict) and w.get("type") == "Craftsdwarfs"]
    if not shops:
        self.build("Craftsdwarfs", retry=5)
        return
    if self.craft_press():
        self.craft_stalled()
        return
    self.craft_fallback()
    if met and any(x.get("job") == "MakeCrafts" and x.get("repeat")
                   and "bone" not in lst(x.get("material_category")) for x in self.orders):
        return
    low_logs = self.logs() < self.logs_guard()
    want = 1
    if chasing and not low_logs:
        gap = self.wealth_target() - self.wealth_created()
        want = 4 if gap > WAVE_GAP_FOURTH_SHOP else 3 if gap > WAVE_GAP_THIRD_SHOP else 2
    if len(shops) < want:
        self.build("Craftsdwarfs", retry=5)
    standing = next((x for x in self.orders if x.get("job") == "MakeCrafts" and x.get("repeat")
                     and "bone" not in lst(x.get("material_category"))), None)
    post = (self.day or 0) > PROGRESS_LAST_DAY
    desired = self.craft_amount_chase() if chasing else CRAFT_AMOUNT_POST if post else CRAFT_AMOUNT_BASE
    if standing is None:
        amount = self.craft_desired if self.craft_desired in (CRAFT_AMOUNT_BASE, CRAFT_AMOUNT_WAVE) else desired
        if self.logs() >= self.logs_guard():
            self.mark_craft_flip(amount)
            self.act("o_crafts_prog", "add_manager_order", {"job": "MakeCrafts",
                     "amount": amount, "repeat": "daily", "material_category": ["wood"],
                     "when": [{"item_type": "WOOD", "at_least": LOG_RESERVE}]}, retry=4, limit=6)
        return
    if chasing and (standing.get("total") or desired) != desired and not low_logs \
            and (self.craft_amount_day is None
                 or (self.day or 0) - self.craft_amount_day >= CRAFT_ADAPT_MIN_DAYS):
        self.mark_craft_flip(desired)
        r = self.act("o_crafts_recut", "cancel_order", {"order_id": standing.get("id")}, retry=2, limit=4)
        if r is not None and r.get("ok"):
            self.done.discard("o_crafts_prog")
def craft_press(self):
    wood = [x for x in self.orders if x.get("job") == "MakeCrafts" and x.get("repeat")
            and "bone" not in lst(x.get("material_category"))]
    mine = self.key_order.get("o_crafts_press")
    dry = self.wood_dry()
    if dry and self.may("wood_dry_log", WOOD_DRY_DAYS, 10 ** 6):
        self.last["wood_dry_log"] = self.now
        log("wood_dry", day=self.day, logs=self.logs(), since=self.wood_hist[0][0])
    if self.barrel_press() or self.labor_press() or dry:
        heavy = [x for x in wood if (x.get("total") or 0) > PRESS_CRAFT_AMOUNT]
        if heavy:
            for x in heavy:
                r = self.act("o_crafts_hold_%s" % x.get("id"), "cancel_order", {"order_id": x.get("id")},
                             retry=1, limit=4)
                if r is not None and r.get("ok"):
                    self.done.discard("o_crafts_prog")
                    log("craft_press", day=self.day, held=x.get("id"), amount=x.get("total"),
                        pb=self.st.get("plants_brewable"), barrels=self.st.get("barrels_empty"))
        elif dry:
            for x in wood:
                r = self.act("o_crafts_dry_%s" % x.get("id"), "cancel_order", {"order_id": x.get("id")},
                             retry=1, limit=4)
                if r is not None and r.get("ok"):
                    self.done.discard("o_crafts_prog")
        elif not wood:
            self.act("o_crafts_press", "add_manager_order", {"job": "MakeCrafts", "amount": PRESS_CRAFT_AMOUNT,
                     "repeat": "daily", "material_category": ["wood"],
                     "when": [{"item_type": "WOOD", "at_least": LOG_RESERVE}]}, retry=1, limit=99)
        return True
    if mine is not None and any(x.get("id") == mine for x in wood):
        r = self.act("o_crafts_free", "cancel_order", {"order_id": mine}, retry=1, limit=99)
        if r is not None and r.get("ok"):
            self.key_order.pop("o_crafts_press", None)
            self.done.discard("o_crafts_prog")
            log("craft_press", day=self.day, released=mine, pb=self.st.get("plants_brewable"),
                barrels=self.st.get("barrels_empty"))
        return True
    return False
def craft_stalled(self):
    day = self.day
    if not isinstance(day, (int, float)) or isinstance(day, bool):
        return False
    w = self.wealth_created()
    if self.wealth_hist and self.wealth_hist[-1][0] == day:
        self.wealth_hist[-1] = (day, w)
    else:
        self.wealth_hist.append((day, w))
    wood = any(x.get("job") == "MakeCrafts" and x.get("repeat") and (x.get("left") or 0) > 0
               and "wood" in lst(x.get("material_category")) for x in self.orders)
    if wood and any("wooden crafts" in str(t).lower() and "needs logs" in str(t).lower()
                    for t in lst(self.o.get("recent_cancellations"))):
        return True
    old = [p for p in self.wealth_hist if day - p[0] >= CRAFT_STALL_DAYS]
    if not old:
        return False
    d0, w0 = old[-1]
    return wood and w - w0 < CRAFT_STALL_RISE
def craft_fallback(self):
    if not self.craft_stalled():
        return
    if self.press_day is not None and isinstance(self.day, (int, float)) \
            and self.day - self.press_day < CRAFT_STALL_DAYS:
        return
    cats = {tuple(lst(x.get("material_category"))) for x in self.orders if x.get("job") == "MakeCrafts"}
    for cat in ("bone",):
        if (cat,) in cats:
            continue
        r = self.act("o_crafts_%s_prog" % cat, "add_manager_order", {
            "job": "MakeCrafts", "amount": CRAFT_ALT_AMOUNT, "repeat": "daily", "material_category": [cat]},
            retry=4, limit=3)
        if r is not None:
            log("craft_fallback", day=self.day, material=cat, ok=bool(r.get("ok")), wealth=self.wealth_created(),
                logs=self.logs())
def progress_record(self):
    if self.pop_prev is not None and self.cit > self.pop_prev:
        self.waves += self.cit - self.pop_prev
        log("prog_wave", day=self.day, arrived=self.cit - self.pop_prev, citizens=self.cit,
            waves=self.waves, wealth=self.wealth_created())
    self.pop_prev = self.cit
    if self.window_fund is None and (self.day or 0) > PROGRESS_LAST_DAY:
        self.window_fund = self.wealth_created()
    if not self.rank_note and self.cit >= WAVE_POP_TARGET and self.wealth_created() >= HAMLET_WEALTH:
        self.rank_note = True
        log("prog_rank_race", day=self.day, citizens=self.cit, wealth=self.wealth_created(),
            note="pop >= 20 with the Hamlet created wealth: the rank follows within ~2 d (7/7 measured)")
    if not self.stall_note and (self.day or 0) > 214 and self.cit < WAVE_POP_TARGET:
        self.stall_note = True
        log("prog_wave_stall", day=self.day, citizens=self.cit, waves=self.waves,
            window_fund=self.window_fund,
            note="both hard-coded waves are in and the census is under 20: the spring wealth wave is all "
                 "that is left, and its arrival lands ~19+ days into the season on the measured lag")
def mark_craft_flip(self, desired):
    if desired != self.craft_desired:
        self.craft_desired = desired
        self.craft_amount_day = self.day
    self.craft_mark = (self.day, self.wealth_created())
def area_fits(self, site, cap):
    if cap is None or not isinstance(site, dict):
        return True
    if site.get("id") in (self.zone_banned if cap <= ZONE_MAX else self.place_banned):
        return False
    return (site.get("w") or 1) <= cap and (site.get("h") or 1) <= cap
def room_for(self, role, max_wh=None):
    rooms = [r for r in self.kind("R") if self.roles.get(r["id"]) == role and self.dry(r.get("z"))
             and r["id"] not in self.plot_rooms]
    for r in rooms:
        a = next((s for s in self.closed_a() if s.get("z") == r.get("z") and s.get("id") not in self.plot_rooms
                  and self.dry(s.get("z")) and self.area_fits(s, max_wh) and not self.farm_claimed(s)), None)
        if a and role != "farm" and (r.get("dug") or a.get("open_tiles", 0) >= 6):
            return a
    dug = [r for r in rooms if r.get("dug")]
    if dug:
        return dug[0]
    taken = {r.get("z") for r in self.kind("R") if self.roles.get(r["id"], "").startswith("farm")}
    return next((s for s in sorted(self.closed_a(), key=lambda s: -(s.get("z") or 0))
                 if s.get("z") not in taken and s.get("open_tiles", 0) >= 6 and s.get("id") not in self.plot_rooms
                 and self.dry(s.get("z")) and self.area_fits(s, max_wh)), None)
def dine_usable(self, dine, dorm=None):
    if not isinstance(dine, dict) or dine.get("kind") != "R":
        return isinstance(dine, dict)
    used = [str(u) for u in lst(dine.get("used_by"))]
    box = self.site_box(dine, ZONE_MAX)
    if used:
        return all(u.startswith("DiningHall") for u in used) \
            or (self._ints(box, ("x", "y", "z", "w", "h"))
                and any(self._ints(z, ("x", "y", "z", "w", "h")) and covers(z, box) for z in self.zone("dining")))
    if isinstance(dorm, dict) and dorm.get("id") == dine.get("id"):
        return False
    return dine.get("free", True) is not False
def needs_zone(self, room, zones, kinds, placed=()):
    if any(covers(z, room) for z in zones):
        return False
    return any(f.get("kind") in kinds and covers(room, f)
               and not any(covers(z, f) for z in zones)
               for f in lst(self.o.get("furniture")) + list(placed))
def place(self, key, kind, room, count):
    args = {"kind": kind, "site": room["id"], "count": count}
    args.update(self.box_wh(room, PLACE_MAX))
    result = d(self.act(key, "place_furniture", args, retry=1, limit=99))
    self.last_place = result
    if not result.get("ok"):
        return []
    points = d(result.get("result")).get("at") or []
    if points and not isinstance(points[0], list):
        points = [points]
    return [{"kind": kind, "x": x, "y": y, "z": z} for x, y, z in points]
def floor_full(self):
    return d(self.last_place).get("error_code") == OVERFLOW_ERROR \
        or OVERFLOW_ERROR in str(d(self.last_place).get("error") or "")
def overflow_site(self, dorm):
    farm_z = {r.get("z") for r in self.kind("R") if self.roles.get(r["id"], "").startswith("farm")}
    def free_floor(s, allow_rooms):
        return (s.get("id") != dorm.get("id") and s.get("id") not in self.overflow
                and s.get("z") not in farm_z and (s.get("open_tiles") or 0) >= OVERFLOW_MIN_TILES
                and (s.get("kind") == "A" or (allow_rooms and s.get("dug"))))
    dorms = [r for r in self.kind("R") if self.roles.get(r["id"]) == "dorm" and r.get("z") != dorm.get("z")
             and r.get("dug") and free_floor(r, True)]
    same = [s for s in self.sites if s.get("z") == dorm.get("z") and free_floor(s, True)]
    other = [s for s in self.closed_a() if s.get("z") != dorm.get("z") and free_floor(s, False)]
    biggest = lambda pool: max(pool, key=lambda s: s.get("open_tiles") or 0, default=None)
    return biggest(dorms) or biggest(same) or biggest(other)
def overflow_beds(self, dorm, n):
    alt = self.overflow_site(dorm)
    if not alt:
        return
    result = d(self.act("beds_ov", "place_furniture", {"kind": "bed", "site": alt["id"], "count": n},
                        retry=1, limit=30))
    if not result:
        return
    self.overflow.add(alt["id"])
    points = d(result.get("result")).get("at") or []
    if points and not isinstance(points[0], list):
        points = [points]
    placed = [{"kind": "bed", "x": x, "y": y, "z": z} for x, y, z in points]
    if placed and self.needs_zone(alt, self.zone("dorm") + self.zone("bedroom"), ("bed",), placed):
        self.act("z_dorm_ov", "make_zone", {"kind": "dormitory", "site": alt["id"]}, retry=3)
def placed_dry(self, kind):
    if not self.breach:
        return self.placed.get(kind) or 0
    return sum(1 for f in lst(self.o.get("furniture"))
               if d(f).get("kind") == kind and self.dry(f.get("z")))
def meeting_area(self):
    if self.zone("meeting") or self.breach:
        return
    site = self.stress_site(meeting=True)
    near_shaft = self.shaft_cols() and MEETING_SHAFT_TILES is not None and (
        site is None or self.shaft_gap(self.site_box(site, ZONE_MAX)) < MEETING_SHAFT_TILES)
    if near_shaft:
        far = self.meeting_far_box()
        if far is None and isinstance(self.day, (int, float)) and self.day < MEETING_NEAR_DAY:
            if self.may("meeting_wait_log", 10, 10 ** 6):
                self.last["meeting_wait_log"] = self.now
                log("meeting_wait", day=self.day, site=(site or {}).get("id"))
            return
        if far is not None and self.meeting_in_pocket(*far):
            far = None
        if far is not None:
            s_, w_, h_ = far
            args = {"kind": "meeting_area", "site": s_["id"]}
            if (w_, h_) != (s_.get("w"), s_.get("h")):
                args.update(w=w_, h=h_)
            r = self.act("z_meeting_far", "make_zone", args, retry=3, limit=4)
            if r is not None:
                log("meeting_far", day=self.day, site=s_["id"], w=w_, h=h_, first=True, ok=bool(r.get("ok")))
            return
        near = self.meeting_far_box(gap=MEETING_FOOT_TILES)
        if near is not None and self.meeting_in_pocket(*near):
            near = None
        if near is not None:
            s_, w_, h_ = near
            args = {"kind": "meeting_area", "site": s_["id"]}
            if (w_, h_) != (s_.get("w"), s_.get("h")):
                args.update(w=w_, h=h_)
            r = self.act("z_meeting_near", "make_zone", args, retry=3, limit=4)
            if r is not None:
                log("meeting_near", day=self.day, site=s_["id"], w=w_, h=h_, ok=bool(r.get("ok")),
                    gap=self.shaft_gap({"x": s_["x"], "y": s_["y"], "z": s_["z"], "w": w_, "h": h_}))
            return
        if site is None or self.shaft_gap(self.site_box(site, ZONE_MAX)) < MEETING_FOOT_TILES:
            if self.may("meeting_foot_log", 10, 10 ** 6):
                self.last["meeting_foot_log"] = self.now
                log("meeting_foot_skip", day=self.day, site=(site or {}).get("id"))
            return
    if site is not None and self.meeting_in_pocket(site):
        site = None
    if site is not None and (getattr(self, "tries", None) or {}).get("z_meeting", 0) < 4:
        r = self.act("z_meeting", "make_zone", {"kind": "meeting_area", "site": site["id"]}, retry=3, limit=4)
        if r and r.get("ok") and isinstance(getattr(self, "stress_rooms", None), set):
            self.stress_rooms.add(site["id"])
        return
    mb = self.meeting_box()
    if mb is not None:
        s, w, h = mb
        args = {"kind": "meeting_area", "site": s["id"]}
        if (w, h) != (s.get("w"), s.get("h")):
            args.update(w=w, h=h)
        r = self.act("z_meeting_box", "make_zone", args, retry=3, limit=4)
        if r is not None:
            log("meeting_box", day=self.day, site=s["id"], w=w, h=h, ok=bool(r.get("ok")))
    elif self.open_a():
        self.people_room("meeting")
def meeting_in_pocket(self, s, w=None, h=None):
    box = {"x": d(s).get("x"), "y": d(s).get("y"), "z": d(s).get("z"),
           "w": w or d(s).get("w") or 3, "h": h or d(s).get("h") or 3}
    if not self.pocket_box(box):
        return False
    if self.may("meeting_pocket_log", 1, 10 ** 6):
        self.last["meeting_pocket_log"] = self.now
        log("meeting_pocket_skip", day=self.day, site=d(s).get("id"), w=box["w"], h=box["h"])
    return True
def shaft_cols(self):
    return self.open_entrances() if isinstance(getattr(self, "sites", None), list) else []
def shaft_people(self):
    return MEETING_SHAFT_TILES is not None and not getattr(self, "breach", None) and bool(self.shaft_cols())
def shaft_near(self, box):
    return self.shaft_gap(box) < MEETING_SHAFT_TILES
def shaft_wait(self):
    return self.shaft_people() and not getattr(self, "surge", None) and getattr(self, "hands_off", None) is None \
        and isinstance(self.day, (int, float)) and not isinstance(self.day, bool) and self.day < MEETING_FAR_WAIT_DAY
def site_sig(self, sid):
    s = next((x for x in getattr(self, "sites", None) or [] if isinstance(x, dict) and x.get("id") == sid), None)
    if s is None:
        return None
    pend = d(self.o.get("dig_pending_by_z")) if isinstance(getattr(self, "o", None), dict) else {}
    z = s.get("z")
    return (s.get("x"), s.get("y"), z, s.get("w"), s.get("h"), s.get("open_tiles"),
            d(s.get("tiles")).get("floor"), pend.get(z, pend.get(str(z))))
def nofloor_key(self, sid, w=None, h=None):
    if w is None or h is None:
        s = next((x for x in getattr(self, "sites", None) or [] if isinstance(x, dict) and x.get("id") == sid), {})
        w = s.get("w") if w is None else w
        h = s.get("h") if h is None else h
    return (sid, w, h)
def floor_refused(self, sid, w=None, h=None):
    mark = self.nofloor.get(self.nofloor_key(sid, w, h)) if sid is not None else None
    if mark is None:
        return False
    day, sig = mark
    today = self.obs_day()
    if isinstance(today, (int, float)) and isinstance(day, (int, float)) and today - day >= NOFLOOR_DAYS:
        return False
    return sig == self.site_sig(sid)
def site_floor(self, site, walk=False):
    num = lambda v: isinstance(v, int) and not isinstance(v, bool)
    if not isinstance(site, dict) or not all(num(site.get(k)) for k in ("x", "y", "z")):
        return None
    sid = site.get("id")
    x0, y0, z = site["x"], site["y"], site["z"]
    w = min(site["w"] if num(site.get("w")) else 3, ZONE_MAX)
    h = min(site["h"] if num(site.get("h")) else 3, ZONE_MAX)
    sig = (x0, y0, z, w, h, site.get("open_tiles"))
    today = self.obs_day()
    hit = self.floor_maps.get(sid)
    if hit is not None and hit[0] == sig and isinstance(today, (int, float)) and isinstance(hit[1], (int, float)):
        if today - hit[1] < (FLOOR_PROBE_DAYS if hit[2] is not None else 1):
            return hit[3] if walk else hit[2]
    tiles = walks = None
    try:
        r = self.game.query("map", x=min(400, max(0, x0 + (w - 1) // 2)), y=min(400, max(0, y0 + (h - 1) // 2)),
                            z=z, z2=z, radius=min(20, max(w, h) // 2 + 1))
        res = query_result(r)
    except Exception as e:
        log("site_floor_error", site=sid, error=repr(e)[:160])
        res = None
    if res is not None and num(res.get("x1")) and num(res.get("y1")):
        lv = next((d(v) for v in lst(res.get("levels")) if d(v).get("z") == z), None)
        if lv is not None and isinstance(lv.get("shape"), list):
            light = lv.get("light") if isinstance(lv.get("light"), list) else []
            busy, solid = set(), set()
            for b in lst(res.get("buildings")):
                b = d(b)
                kind = str(b.get("type") or "").lower()
                if b.get("z") != z or kind in FURNITURE_BUILDINGS:
                    continue
                if all(num(b.get(k)) for k in ("x1", "x2", "y1", "y2")):
                    cover = {(bx, by) for bx in range(b["x1"], b["x2"] + 1) for by in range(b["y1"], b["y2"] + 1)}
                    busy |= cover
                    if kind not in ("farmplot", "stockpile"):
                        solid |= cover
            for g in lst(res.get("designations")):
                g = d(g)
                if g.get("z", z) == z and num(g.get("x")) and num(g.get("y")):
                    busy.add((g["x"], g["y"]))
            tiles, walks = set(), set()
            for i, row in enumerate(lv["shape"]):
                ty = res["y1"] + i
                if not (y0 <= ty < y0 + h) or not isinstance(row, str):
                    continue
                lrow = light[i] if i < len(light) and isinstance(light[i], str) else ""
                for j, ch in enumerate(row):
                    tx = res["x1"] + j
                    if x0 <= tx < x0 + w and ch in FLOOR_SHAPES and (j >= len(lrow) or lrow[j] != "?"):
                        if (tx, ty) not in busy:
                            tiles.add((tx, ty))
                        if (tx, ty) not in solid:
                            walks.add((tx, ty))
    self.floor_maps[sid] = (sig, today, tiles, walks)
    if tiles is not None and self.may("site_floor_log_" + str(sid), 5, 10 ** 6):
        self.last["site_floor_log_" + str(sid)] = self.now
        log("site_floor", day=self.day, site=sid, box=[x0, y0, z, w, h], floor=len(tiles), walk=len(walks))
    return walks if walk else tiles
@staticmethod
def floor_in(tiles, b):
    return sum(1 for (x, y) in tiles if b["x"] <= x < b["x"] + b["w"] and b["y"] <= y < b["y"] + b["h"])
def far_site(self, site, avoid, min_tiles=SHAFT_PEOPLE_MIN_TILES, role=None, skip_roles=()):
    if not self.shaft_people():
        return site
    if isinstance(site, dict) and not self.shaft_near(self.site_box(site, ZONE_MAX)):
        return site
    far = self.far_box(avoid, min_tiles=min_tiles, rooms=True, role=role, skip_roles=skip_roles)
    if far is None:
        return None
    s, w, h = far
    return dict(s, far_wh=(w, h))
def shaft_gap(self, box):
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if not isinstance(box, dict) or not all(num(box.get(k)) for k in ("x", "y", "z", "w", "h")):
        return 10 ** 6
    best = 10 ** 6
    for ex, ey, ez in self.shaft_cols():
        if not (ez - MEETING_SHAFT_LEVELS <= box["z"] <= ez):
            continue
        dx = max(box["x"] - ex, 0, ex - (box["x"] + box["w"] - 1))
        dy = max(box["y"] - ey, 0, ey - (box["y"] + box["h"] - 1))
        best = min(best, max(dx, dy))
    return best
def meeting_far_box(self, gap=None, avoid=()):
    if MEETING_SHAFT_TILES is None:
        return None
    beds = [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
            if isinstance(f, dict) and f.get("kind") == "bed"]
    sleep = [z for z in self.zones if any(k in str(z.get("type")).lower() for k in ("dormitory", "bedroom"))]
    return self.far_box(sleep + beds + list(avoid), walk=True, gap=gap)
def far_cut(self, box, avoid, min_tiles, floor=None, placing=True, gap=None):
    if not all(isinstance(box.get(k), int) and not isinstance(box.get(k), bool) for k in ("x", "y", "z", "w", "h")):
        return None
    best, best_key = None, None
    sid = box.get("id")
    for h in range(box["h"], 0, -1):
        for w in range(box["w"], 0, -1):
            if w * h < min_tiles:
                break
            b = dict(box, w=w, h=h)
            if self.shaft_gap(b) < (MEETING_SHAFT_TILES if gap is None else gap) \
                    or any(self.rects_overlap(z, b) for z in avoid) or self.farm_claimed(b) \
                    or self.reserved_hit(b) is not None:
                continue
            n = self.floor_in(floor, b) if floor is not None else 0
            if floor is not None and n < FAR_FLOOR_MIN:
                break
            if placing and sid is not None and self.floor_refused(sid, w, h):
                continue
            key = (n, w * h)
            if best_key is None or key > best_key:
                best, best_key = (w, h), key
            break
    return best
def far_box(self, avoid, min_tiles=MEETING_MIN_TILES, rooms=False, cap=ZONE_MAX, role=None, skip_roles=(),
            walk=False, gap=None):
    if MEETING_SHAFT_TILES is None:
        return None
    surface = d(self.o.get("map")).get("surface_z", getattr(self, "surface", None))
    cands = list(self.closed_a())
    if rooms:
        cands += [r for r in self.kind("R") if r.get("dug") and self.zoneable(r)
                  and not str(self.roles.get(r.get("id")) or "").startswith("farm")
                  and self.roles.get(r.get("id")) not in skip_roles]
    best = None
    for s in cands:
        if s.get("id") in self.plot_rooms or s.get("id") in self.zone_banned or not self.dry(s.get("z")):
            continue
        if s.get("kind") == "A" and (s.get("open_tiles") or 0) < min_tiles:
            continue
        if isinstance(surface, (int, float)) and isinstance(s.get("z"), (int, float)) and s["z"] >= surface:
            continue
        floor = None
        if s.get("kind") == "A":
            floor = self.site_floor(s, walk=walk)
            if floor is None:
                continue
        cut = self.far_cut(self.site_box(s, cap), avoid, min_tiles, floor=floor, placing=not walk, gap=gap)
        if cut is None:
            continue
        w, h = cut
        size = self.floor_in(floor, dict(s, w=w, h=h)) if floor is not None else w * h
        key = (role is not None and self.roles.get(s.get("id")) == role, size, s.get("z") or 0)
        if best is None or key > best[0]:
            best = (key, s, w, h)
    return None if best is None else best[1:]
def meeting_far(self):
    if MEETING_SHAFT_TILES is None or self.breach or not self.shaft_cols():
        return
    meets = self.zone("meeting")
    if not meets or any(self.shaft_gap(z) >= MEETING_SHAFT_TILES for z in meets):
        return
    far = self.meeting_far_box()
    if far is None or self.meeting_in_pocket(*far):
        return
    s, w, h = far
    args = {"kind": "meeting_area", "site": s["id"]}
    if (w, h) != (s.get("w"), s.get("h")):
        args.update(w=w, h=h)
    r = self.act("z_meeting_far", "make_zone", args, retry=3, limit=4)
    if r is not None:
        log("meeting_far", day=self.day, site=s["id"], w=w, h=h, first=False, ok=bool(r.get("ok")),
            near=[(z.get("x"), z.get("y"), z.get("z")) for z in meets][:3])
def meeting_use(self):
    meets = self.zone("meeting")
    surface = d(self.o.get("map")).get("surface_z", getattr(self, "surface", None))
    if self.breach or not meets or "z_meeting_use" in self.done or not isinstance(surface, (int, float)):
        return
    if self.meeting_looks_tick == self.now:
        return
    self.meeting_looks_tick = self.now
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    for p in self.people:
        if str(p.get("job") or "").lower() != "idle" or not all(num(p.get(k)) for k in ("x", "y", "z")):
            continue
        self.meeting_looks[0] += 1
        spot = {"x": p["x"], "y": p["y"], "z": p["z"], "w": 1, "h": 1}
        if any(self.rects_overlap(z, spot) for z in meets):
            self.meeting_looks[1] += 1
        if p["z"] >= surface:
            self.meeting_looks[2] += 1
    n, inside, up = self.meeting_looks
    if n < MEETING_USE_LOOKS or inside >= MEETING_USE_MIN * n or up * 2 < n:
        return
    homes = self.zone("dining") + [z for z in self.zones if any(k in str(z.get("type")).lower()
                                                               for k in ("dormitory", "bedroom"))]
    def reach(b):
        for z in homes:
            if not all(num(z.get(k)) for k in ("x", "y", "z", "w", "h")) or abs(z["z"] - b["z"]) > 1:
                continue
            dx = max(z["x"] - (b["x"] + b["w"] - 1), 0, b["x"] - (z["x"] + z["w"] - 1))
            dy = max(z["y"] - (b["y"] + b["h"] - 1), 0, b["y"] - (z["y"] + z["h"] - 1))
            if max(dx, dy) <= MEETING_USE_REACH:
                return True
        return False
    box = None
    for pick in (lambda: self.meeting_far_box(avoid=meets),
                 lambda: self.meeting_far_box(gap=MEETING_FOOT_TILES, avoid=meets),
                 lambda: self.meeting_box(avoid=meets)):
        got = pick()
        if got is None:
            continue
        s_, w_, h_ = got
        b = {"x": s_.get("x"), "y": s_.get("y"), "z": s_.get("z"), "w": w_, "h": h_}
        if not all(num(b[k]) for k in b) or b["z"] >= surface or not reach(b) \
                or self.shaft_gap(b) < MEETING_FOOT_TILES:
            continue
        box = got
        break
    if self.may("meeting_use_log", 5, 10 ** 6):
        self.last["meeting_use_log"] = self.now
        log("meeting_unused", day=self.day, looks=n, inside=inside, surface=up,
            site=box[0].get("id") if box else None)
    if box is None:
        return
    s_, w_, h_ = box
    args = {"kind": "meeting_area", "site": s_["id"]}
    if (w_, h_) != (s_.get("w"), s_.get("h")):
        args.update(w=w_, h=h_)
    r = self.act("z_meeting_use", "make_zone", args, retry=3, limit=4)
    if r is not None and r.get("ok"):
        self.done.add("z_meeting_use")
def meeting_box(self, avoid=()):
    beds = [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
            if isinstance(f, dict) and f.get("kind") == "bed"]
    sleep = [z for z in self.zones if any(k in str(z.get("type")).lower() for k in ("dormitory", "bedroom"))]
    dines = self.zone("dining")
    cands = []
    for s in self.closed_a():
        if s.get("id") in self.plot_rooms or s.get("id") in self.zone_banned or not self.dry(s.get("z")) \
                or (s.get("open_tiles") or 0) < MEETING_MIN_TILES:
            continue
        box = self.site_box(s, ZONE_MAX)
        if not all(isinstance(box.get(k), int) and not isinstance(box.get(k), bool) for k in ("x", "y", "z")) \
                or self.farm_claimed(box):
            continue
        cands.append((s, box))
    cands.sort(key=lambda e: (not any(self.rects_overlap(z, e[1]) for z in dines), -(e[0].get("z") or 0)))
    for s, box in cands:
        floor = self.site_floor(s, walk=True)
        if floor is None:
            continue
        if self.meeting_in_pocket(s, box["w"], box["h"]):
            continue
        for h in range(box["h"], 0, -1):
            for w in range(box["w"], 0, -1):
                if w * h < MEETING_MIN_TILES:
                    break
                b = dict(box, w=w, h=h)
                if not any(self.rects_overlap(z, b) for z in sleep + beds + list(avoid)) \
                        and self.reserved_hit(b) is None:
                    if self.floor_in(floor, b) >= min(FAR_FLOOR_MIN, MEETING_MIN_TILES):
                        return s, w, h
                    break
    return None
def furnish(self):
    self.new_zones = []
    dorm, dine = self.room_for("dorm", ZONE_MAX), self.room_for("dine", ZONE_MAX) or self.room_for("dorm", ZONE_MAX)
    if dine is not None and not self.dine_usable(dine, dorm):
        log("dine_skip", day=self.day, site=dine.get("id"), used_by=dine.get("used_by"),
            dorm=(dorm or {}).get("id"))
        dine = None
    if dine is None and self.open_a() and (self.free.get("table") or 0) > 0 \
            and not (self.surge and self.placed_dry("bed") < self.cit):
        self.people_room("dine")
    seat_wait = False
    if self.shaft_people() and not self.surge:
        dorm, dine, seat_wait = self.shaft_rooms(dorm, dine)
    if self.surge:
        self.surge_beds(dorm)
    else:
        short = self.cit + 2 - self.placed_dry("bed")
        n = min(self.free.get("bed") or 0, short, 30)
        placed = self.place("beds", "bed", dorm, n) if (dorm and n > 0) else []
        if n > 0 and len(placed) < n:
            self.surge_beds(dorm, already=len(placed))
        if dorm and self.needs_zone(self.site_box(dorm, ZONE_MAX), self.zone("dorm") + self.zone("bedroom"),
                                    ("bed",), placed):
            self.act("z_dorm", "make_zone", {"kind": "dormitory", "site": dorm["id"],
                                             **self.box_wh(dorm, ZONE_MAX)}, retry=3)
    if not (self.surge and self.placed_dry("bed") < self.cit):
        want = math.ceil(self.cit / 2) + 1
        full = self.seats_full()
        placed = []
        for kind in ("table", "chair"):
            if not dine or dine.get("id") in self.plot_rooms:
                break
            have = self.placed_dry(kind) if self.breach else self.dine_count(kind)
            goal = max(want, full)
            if kind == "chair" and not self.breach:
                goal = max(want, self.dine_count("table") + sum(1 for f in placed if f["kind"] == "table"))
            n = min(self.free.get(kind) or 0, goal - have, 15)
            if n > 0:
                placed += self.place("f_" + kind, kind, dine, n)
        if dine and self.needs_zone(self.site_box(dine, ZONE_MAX), self.zone("dining"), ("table", "chair"),
                                    placed):
            self.act("z_dine", "make_zone", {"kind": "dining_hall", "site": dine["id"],
                                             **self.box_wh(dine, ZONE_MAX)}, retry=3)
        if not seat_wait:
            self.seat_spread(max(want, full), sum(1 for f in placed if f["kind"] == "table"),
                             sum(1 for f in placed if f["kind"] == "chair"), half=want)
def shaft_rooms(self, dorm, dine):
    def furn(kinds):
        return [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
                if isinstance(f, dict) and f.get("kind") in kinds and self._ints(f)]
    zones_of = lambda words: [z for z in self.zones if any(k in str(z.get("type")).lower() for k in words)]
    beds_due = min(self.free.get("bed") or 0, self.cit + 2 - self.placed_dry("bed")) > 0
    if dorm is not None and beds_due:
        far = self.far_site(dorm, zones_of(("dining", "meeting")) + furn(("table", "chair")),
                            role="dorm", skip_roles=("dine", "office", "stress", "bedroom"))
        if far is not None and far is not dorm:
            log("shaft_dorm", day=self.day, near=dorm.get("id"), site=far.get("id"), wh=far.get("far_wh"))
            dorm = far
    sleep = zones_of(("dormitory", "bedroom")) + furn(("bed",))
    if isinstance(dorm, dict) and beds_due:
        sleep.append(self.site_box(dorm, ZONE_MAX))
    far = self.far_site(dine, sleep, role="dine", skip_roles=("dorm", "house", "office", "stress", "bedroom"))
    if far is not None:
        if far is not dine:
            if self.may("shaft_dine_log", 10, 10 ** 6):
                self.last["shaft_dine_log"] = self.now
                log("shaft_dine", day=self.day, near=(dine or {}).get("id"), site=far.get("id"),
                    wh=far.get("far_wh"))
        return dorm, far, False
    halls = self.zone("dining")
    if halls and not (isinstance(dine, dict) and any(self.rects_overlap(self.site_box(dine, ZONE_MAX), z)
                                                      for z in halls)):
        stand = [x for x in self.closed_a() + self.kind("R")
                 if x.get("id") not in self.plot_rooms and self.dry(x.get("z"))
                 and (x.get("kind") == "A" or x.get("dug"))
                 and any(self.rects_overlap(self.site_box(x, ZONE_MAX), z) for z in halls)]
        if stand:
            dine = stand[0]
    if self.may("shaft_dine_near_log", 10, 10 ** 6):
        self.last["shaft_dine_near_log"] = self.now
        log("shaft_dine_near", day=self.day, near=(dine or {}).get("id"))
    return dorm, dine, False
def surge_bed_sites(self, dorm):
    out, seen, today = [], set(), self.obs_day()
    def full(s):
        mark = self.bed_full.get(s.get("id"))
        if mark is None:
            return False
        day, tiles = mark
        grown = isinstance(s.get("open_tiles"), int) and isinstance(tiles, int) and s["open_tiles"] > tiles
        fresh = isinstance(today, (int, float)) and isinstance(day, (int, float)) \
            and today - day < SURGE_BED_RETRY_DAYS
        return fresh and not grown
    areas = []
    for a in sorted(self.kind("A"), key=lambda s: -(s.get("open_tiles") or 0)):
        if not self.dry(a.get("z")) or (a.get("open_tiles") or 0) < OVERFLOW_MIN_TILES:
            continue
        if self.area_fits(a, PLACE_MAX):
            areas.append(a)
        else:
            areas.extend(self.surge_chunks(a))
    areas = [a for a in areas if not self.box_open((a["x"], a["y"], a["z"], a.get("w") or 1, a.get("h") or 1)
                                                   if all(isinstance(a.get(k), int) for k in ("x", "y", "z"))
                                                   else None)]
    live = {a.get("parent", a.get("id")) for a in areas}
    full_z = {a.get("z") for a in self.kind("A") if full(a) and a.get("id") in live}
    by_z = {}
    for a in areas:
        by_z.setdefault(a.get("z"), []).append(full(a))
    full_z |= {z for z, marks in by_z.items() if all(marks)}
    def add(s):
        if not isinstance(s, dict) or s.get("id") in seen:
            return
        seen.add(s.get("id"))
        if full(s) or (s.get("kind") == "R" and s.get("z") in full_z):
            return
        out.append(s)
    add(dorm)
    for r in sorted(self.kind("R"), key=lambda s: -(s.get("open_tiles") or 0)):
        if (self.roles.get(r["id"]) in ("dorm", "house") or (self.surge and self.roles.get(r["id"]) == "office")) \
                and r.get("dug") and self.dry(r.get("z")) \
                and "farm" not in str(r.get("used_by") or "").lower() and r["id"] not in self.plot_rooms:
            add(r)
    for a in areas:
        add(a)
    for r in self.kind("R"):
        if r.get("dug") and r.get("free", True) and r["id"] not in self.roles and self.dry(r.get("z")) \
                and r["id"] not in self.plot_rooms:
            add(r)
    return out
def surge_chunks(self, a):
    vals = [a.get(k) for k in ("x", "y", "z", "w", "h")]
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in vals):
        return []
    x, y, z, w, h = vals
    return [{"id": "%s@%d,%d" % (a.get("id"), x0, y0), "kind": "A", "chunk": True, "x": x0, "y": y0, "z": z,
             "w": min(PLACE_MAX, x + w - x0), "h": min(PLACE_MAX, y + h - y0), "open_tiles": a.get("open_tiles"),
             "parent": a.get("id"), "corner": x0 == x and y0 == y}
            for y0 in range(y, y + h, PLACE_MAX) for x0 in range(x, x + w, PLACE_MAX)]
def chunk_where(self, site):
    where = self.chunk_at(site)
    if where is not None and not site.get("chunk"):
        where.update(self.box_wh(site, PLACE_MAX))
    return where
@staticmethod
def chunk_at(site):
    if not site.get("chunk"):
        return {"site": site["id"]}
    if site.get("parent") is None or not site.get("corner"):
        return None
    return {"site": site["parent"], "w": site["w"], "h": site["h"]}
def surge_beds(self, dorm, already=0):
    free = (self.free.get("bed") or 0) - already
    n = min(free, self.cit + 2 - self.placed_dry("bed") - already, 30)
    n0 = n
    tried, skip_z = 0, set()
    for site in self.surge_bed_sites(dorm):
        if n <= 0 or tried >= SURGE_BED_SITES:
            break
        if site.get("kind") == "R" and site.get("z") in skip_z:
            continue
        key = "beds" if dorm is not None and site.get("id") == dorm.get("id") else "beds_" + str(site.get("id"))
        where = self.chunk_where(site)
        if where is None:
            continue
        result = self.act(key, "place_furniture", {"kind": "bed", **where, "count": n}, retry=1, limit=99)
        if result is None:
            continue
        tried += 1
        self.last_place = result
        points = (d(result.get("result")).get("at") or []) if result.get("ok") else []
        if points and not isinstance(points[0], list):
            points = [points]
        placed = [{"kind": "bed", "x": x, "y": y, "z": z} for x, y, z in points]
        if result.get("ok") and placed and site.get("kind") in ("A", "R") and not site.get("chunk") \
                and self.area_fits(site, ZONE_MAX) and self.needs_zone(site, self.zone("dorm") + self.zone("bedroom"), ("bed",), placed):
            self.act("z_dorm" if key == "beds" else "z_dorm_" + str(site.get("id")), "make_zone",
                     {"kind": "dormitory", "site": site["id"]}, retry=3)
        if not result.get("ok") or len(placed) < n:
            self.bed_full[site.get("id")] = (self.obs_day(), site.get("open_tiles"))
            if site.get("kind") == "A" and not result.get("ok") and result.get("error_code") != "site_open":
                skip_z.add(site.get("z"))
            if result.get("error_code") == "site_used" and self.roles.get(site.get("id")) == "dorm":
                self.roles.pop(site.get("id"), None)
                log("surge_dorm_lost", day=self.day, site=site.get("id"))
        avail = d(result.get("result")).get("available")
        if result.get("ok") and not (isinstance(avail, int) and avail >= n > len(placed)):
            n -= len(placed)
            break
        n -= len(placed)
    if n > 0 and n == n0 and tried and not self.surge:
        self.house_full_day = self.obs_day()
    if dorm is not None and n > 0 and self.needs_zone(self.site_box(dorm, ZONE_MAX),
                                                      self.zone("dorm") + self.zone("bedroom"), ("bed",)):
        self.act("z_dorm", "make_zone", {"kind": "dormitory", "site": dorm["id"],
                                         **self.box_wh(dorm, ZONE_MAX)}, retry=3)
@staticmethod
def _ints(s, keys=("x", "y", "z")):
    return isinstance(s, dict) and all(isinstance(s.get(k), int) and not isinstance(s.get(k), bool) for k in keys)
def box_wh(self, site, cap):
    if not isinstance(site, dict):
        return {}
    w0, h0 = site.get("w"), site.get("h")
    w, h = (w0 if isinstance(w0, int) else 3), (h0 if isinstance(h0, int) else 3)
    fw = site.get("far_wh")
    if isinstance(fw, tuple) and len(fw) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in fw):
        w, h = max(1, min(fw[0], cap)), max(1, min(fw[1], cap))
        return {} if (w, h) == (w0, h0) else {"w": w, "h": h}
    if site.get("kind") == "R":
        b = self.room_box.get(site.get("id"))
        if isinstance(b, dict) and all(b.get(k) == site.get(k) for k in ("x", "y", "z")) \
                and isinstance(b.get("w"), int) and isinstance(b.get("h"), int):
            w, h = b["w"], b["h"]
    w, h = max(1, min(w, cap)), max(1, min(h, cap))
    return {} if (w, h) == (w0, h0) else {"w": w, "h": h}
def site_box(self, site, cap):
    box = {k: site.get(k) for k in ("id", "x", "y", "z", "w", "h")}
    box["w"] = box["w"] if isinstance(box["w"], int) else 3
    box["h"] = box["h"] if isinstance(box["h"], int) else 3
    box.update(self.box_wh(site, cap))
    return box
def dine_count(self, kind):
    dine = {z.get("id") for z in self.zone("dining") if z.get("id") is not None}
    items = [f for f in map(d, lst(self.o.get("furniture"))) if f.get("kind") == kind and f.get("zone_ids")]
    if dine and items:
        return sum(1 for f in items if any(i in dine for i in lst(f.get("zone_ids"))))
    n = 0
    for z in self.zone("dining"):
        n += (d(z.get("furniture")).get(kind) or 0) + (d(z.get("furniture_planned")).get(kind) or 0)
    return n
def stray(self, kind):
    types = {z.get("id"): str(z.get("type")).lower() for z in self.zones}
    uses = ("dining", "office") if kind == "chair" else ("dining",)
    n = 0
    for f in lst(self.o.get("furniture")):
        f = d(f)
        if f.get("kind") == kind and f.get("built") \
                and not any(u in types.get(i, "") for i in lst(f.get("zone_ids")) for u in uses):
            n += 1
    return n
def placeable(self, s):
    if not self._ints(s) or not self.dry(s.get("z")) or s.get("id") in self.plot_rooms:
        return False
    if s.get("kind") == "A":
        return True
    return s.get("kind") == "R" and bool(s.get("dug")) and "farm" not in str(s.get("used_by") or "").lower()
def zoneable(self, s):
    return self.placeable(s) and (s.get("kind") == "A" or s.get("free", True))
def seat_boxes(self):
    out, seen = [], set()
    def add(s, w, h, zoned):
        w, h = max(1, min(w, ZONE_MAX)), max(1, min(h, ZONE_MAX))
        bid = "%s:%dx%d" % (s["id"], w, h)
        box = {"id": bid, "site": s["id"], "x": s["x"], "y": s["y"], "z": s["z"], "w": w, "h": h,
               "zoned": zoned, "open_tiles": s.get("open_tiles")}
        if bid in seen or (not zoned and self.farm_claimed(box)):
            return
        seen.add(bid)
        out.append(box)
    for zn in self.zone("dining"):
        if not self._ints(zn, ("x", "y", "z", "w", "h")):
            continue
        for s in self.sites:
            if s.get("kind") in ("A", "R") and self.placeable(s) \
                    and (s.get("x"), s.get("y"), s.get("z")) == (zn["x"], zn["y"], zn["z"]):
                add(s, zn["w"], zn["h"], True)
                break
    for r in self.kind("R"):
        if self.roles.get(r.get("id")) in ("house", "dine", "dorm") and self.zoneable(r):
            b = self.site_box(r, ZONE_MAX)
            add(r, b["w"], b["h"], False)
    for a in sorted(self.closed_a(), key=lambda s: -(s.get("open_tiles") or 0)):
        if self.zoneable(a) and (a.get("open_tiles") or 0) >= OVERFLOW_MIN_TILES:
            add(a, a.get("w") or 1, a.get("h") or 1, False)
    for r in self.kind("R"):
        if r.get("id") not in self.roles and self.zoneable(r):
            b = self.site_box(r, ZONE_MAX)
            add(r, b["w"], b["h"], False)
    return out
def seat_spread(self, want, used_t=0, used_c=0, half=None):
    need = want - self.seats() - min(used_t, used_c)
    n = min(need, (self.free.get("table") or 0) - used_t, (self.free.get("chair") or 0) - used_c, 15)
    if n <= 0:
        return
    today = self.obs_day()
    tried = 0
    boxes = self.shaft_seats(self.seat_boxes())
    if not boxes:
        if self.seat_nobox_day != today:
            log("seat_no_box", day=self.day, need=n, seats=self.seats(), want=want)
        self.seat_nobox_day = today
        return
    for b in boxes:
        mark = self.seat_full.get(b["id"])
        if mark is not None:
            day, tiles = mark
            grown = isinstance(b.get("open_tiles"), int) and isinstance(tiles, int) and b["open_tiles"] > tiles
            if isinstance(today, (int, float)) and isinstance(day, (int, float)) \
                    and today - day < SURGE_BED_RETRY_DAYS and not grown:
                continue
        where = {"site": b["site"], "w": b["w"], "h": b["h"]}
        rt = self.act("seat_t_" + b["id"], "place_furniture", {"kind": "table", **where, "count": n},
                      retry=1, limit=99)
        if rt is None:
            continue
        tried += 1
        tp = (d(rt.get("result")).get("at") or []) if rt.get("ok") else []
        if tp and not isinstance(tp[0], list):
            tp = [tp]
        if not tp:
            self.seat_full[b["id"]] = (today, b.get("open_tiles"))
            continue
        rc = self.act("seat_c_" + b["id"], "place_furniture", {"kind": "chair", **where, "count": len(tp)},
                      retry=1, limit=99)
        cp = (d(rc.get("result")).get("at") or []) if (rc and rc.get("ok")) else []
        if cp and not isinstance(cp[0], list):
            cp = [cp]
        if len(cp) < len(tp):
            self.seat_full[b["id"]] = (today, b.get("open_tiles"))
        placed = [{"kind": "table", "x": x, "y": y, "z": z} for x, y, z in tp] \
            + [{"kind": "chair", "x": x, "y": y, "z": z} for x, y, z in cp]
        if not b["zoned"] and self.needs_zone(b, self.zone("dining"), ("table", "chair"), placed):
            rz = self.act("seat_z_" + b["id"], "make_zone", {"kind": "dining_hall", **where}, retry=2, limit=4)
            if rz and rz.get("ok"):
                self.done.add("seat_z_" + b["id"])
                self.new_zones.append({"type": "DiningHall", **{k: b[k] for k in ("x", "y", "z", "w", "h")}})
        log("seat_spread", day=self.day, box=b["id"], tables=len(tp), chairs=len(cp), seats=self.seats(),
            want=want)
        return
    if tried:
        if half is None or self.seats() < half:
            self.house_full_day = today
        else:
            self.seat_refused_day = today
def shaft_seats(self, boxes):
    if not self.shaft_people():
        return boxes
    avoid = [z for z in self.zones if any(k in str(z.get("type")).lower() for k in ("dormitory", "bedroom"))]
    avoid += [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
              if isinstance(f, dict) and f.get("kind") == "bed" and self._ints(f)]
    far, near, seen = [], [], set()
    for b in boxes:
        if not self.shaft_near(b):
            if b["id"] not in seen:
                seen.add(b["id"])
                far.append(b)
            continue
        site = next((x for x in self.sites if isinstance(x, dict) and x.get("id") == b.get("site")), None)
        floor = self.site_floor(site) if isinstance(site, dict) and site.get("kind") == "A" else None
        if isinstance(site, dict) and site.get("kind") == "A" and floor is None:
            near.append(b)
            continue
        cut = self.far_cut(dict(b, id=b.get("site")), avoid, SHAFT_PEOPLE_MIN_TILES, floor=floor)
        if cut is not None:
            w, h = cut
            bid = "%s:%dx%d" % (b["site"], w, h)
            if bid not in seen:
                seen.add(bid)
                zoned = any(self._ints(z, ("x", "y", "z", "w", "h"))
                            and (z["x"], z["y"], z["z"], z["w"], z["h"]) == (b["x"], b["y"], b["z"], w, h)
                            for z in self.zone("dining"))
                far.append(dict(b, id=bid, w=w, h=h, zoned=zoned))
        else:
            near.append(b)
    return far + near
def zone_loose(self, handled=()):
    types = {z.get("id"): str(z.get("type")).lower() for z in self.zones}
    fresh = [z for z in self.new_zones if self._ints(z, ("x", "y", "z", "w", "h"))]
    for kinds, words, zkind, key in ((("table", "chair"), ("dining",), "dining_hall", "lz_dine_"),
                                     (("bed",), ("dorm", "bedroom"), "dormitory", "lz_dorm_")):
        by_z = {}
        for f in lst(self.o.get("furniture")):
            f = d(f)
            if not f.get("built") or f.get("kind") not in kinds or not self._ints(f):
                continue
            if any(w in types.get(i, "") for i in lst(f.get("zone_ids")) for w in words):
                continue
            if (key, f["z"]) in handled:
                continue
            if any(covers(z, f) for z in fresh if any(w in str(z.get("type")).lower() for w in words)):
                continue
            by_z.setdefault(f["z"], []).append(f)
        for z, items in by_z.items():
            best = None
            for s in self.sites:
                if s.get("kind") not in ("A", "R") or s.get("z") != z or not self.zoneable(s):
                    continue
                inside = [f for f in items if s["x"] <= f["x"] < s["x"] + ZONE_MAX
                          and s["y"] <= f["y"] < s["y"] + ZONE_MAX]
                if kinds == ("bed",):
                    score = len(inside)
                else:
                    score = min(sum(1 for f in inside if f["kind"] == "table"),
                                sum(1 for f in inside if f["kind"] == "chair"))
                if score <= 0:
                    continue
                w = max(f["x"] for f in inside) - s["x"] + 1
                h = max(f["y"] for f in inside) - s["y"] + 1
                box = {"id": "%s:lz" % s["id"], "x": s["x"], "y": s["y"], "z": z, "w": w, "h": h}
                if self.farm_claimed(box):
                    continue
                cand = (score, -(w * h), s["id"], w, h)
                if best is None or cand[:2] > best[:2]:
                    best = cand
            if best is not None:
                _, _, sid, w, h = best
                k = "%s%s_%dx%d" % (key, sid, w, h)
                r = self.act(k, "make_zone", {"kind": zkind, "site": sid, "w": w, "h": h}, retry=2, limit=3)
                if r and r.get("ok"):
                    self.done.add(k)
def house_waiting(self, full=False):
    beds = (self.free.get("bed") or 0) > 0 and self.placed_dry("bed") < self.cit + 2
    goal = math.ceil(self.cit / 2) + 1
    if full:
        goal = max(goal, self.seats_full())
    seats = min(self.free.get("table") or 0, self.free.get("chair") or 0) > 0 and self.seats() < goal
    return beds, seats
def farms_met(self):
    try:
        farms = len(lst(self.o.get("farm_plots"))) + sum(
            1 for r, v in self.roles.items() if v == "farm"
            and not any(z.get("id") == r and z.get("used_by") for z in self.kind("R")))
        return farms >= self.farm_target()
    except Exception as e:
        log("farms_met_error", error=repr(e)[:200])
        return False
def house_blocked(self, full=False):
    if self.surge or self.hands_off is not None:
        return False
    today, day = self.obs_day(), self.house_full_day
    for mark in ((self.seat_nobox_day, self.seat_refused_day) if full else ()):
        if isinstance(mark, (int, float)) and (not isinstance(day, (int, float)) or mark > day):
            day = mark
    if day is None or not isinstance(today, (int, float)) or today - day > HOUSE_FULL_DAYS:
        return False
    return any(self.house_waiting(full))
def house_floor(self, pending):
    if not self.house_blocked(full=True) or self.breach:
        return
    beds_wait, seats_wait = self.house_waiting(full=True)
    if not isinstance(pending, int) or isinstance(pending, bool) or pending >= HOUSE_PENDING_MAX:
        return
    spare = [r for r in self.undug_rooms() if r["id"] not in self.roles and self.dry(r.get("z"))
             and not self.room_taken(r)
             and not self.farm_claimed(dict(r, w=HOUSE_ROOM[0], h=HOUSE_ROOM[1]))]
    if not any(self.house_waiting()) and not self.farms_met():
        spare = [r for r in spare if not r.get("soil")]
    r = self.pick_dig_site(spare) if spare else None
    if r is not None:
        box = {"site": r["id"], "w": HOUSE_ROOM[0], "h": HOUSE_ROOM[1]}
        res = self.act("dig_house_" + str(r["id"]), "dig_room", box, retry=3, limit=2)
        if res and res.get("ok"):
            self.roles[r["id"]] = "house"
            self.note_room_box(r, box)
            log("house_floor_dig", day=self.day, site=r["id"], beds_wait=beds_wait, seats_wait=seats_wait)
        return
    if self.house_blocked():
        self.floor_stair("stairs_house", "house_floor_stair")
    elif seats_wait and self.seat_shaft_due() \
            and not any(self.roles.get(x["id"]) == "house" and not x.get("dug") for x in self.kind("R")):
        self.shelter_shaft(why="seats")
def seat_shaft_due(self):
    today, mark = self.obs_day(), self.seat_nobox_day
    return isinstance(today, (int, float)) and isinstance(mark, (int, float)) and today - mark <= HOUSE_FULL_DAYS
def note_dig_batch(self, key, tool, args):
    site = next((x for x in self.sites if x.get("id") == args.get("site")), None)
    if site is None or not self._ints(site, ("x", "y", "z")):
        return
    x0, y0, z0 = site["x"], site["y"], site["z"]
    if tool == "dig_room":
        w = args.get("w") or site.get("w") or 3
        h = args.get("h") or site.get("h") or 3
        tiles = {(x, y, z0) for x in range(x0, x0 + w) for y in range(y0, y0 + h)}
    else:
        zb = args.get("z_bottom") if isinstance(args.get("z_bottom"), int) else z0 - 1
        tiles = {(x0, y0, z) for z in range(zb, z0 + 1)}
    bid = "%s:%s:%s" % (key, args.get("site"), self.day)
    self.dig_batches.append({"id": bid, "key": key, "day": self.day, "tiles": tiles, "paused": False})
def batch_pending(self, b):
    seen = self.batch_seen.get(b["id"])
    if seen is not None and seen[0] == self.day:
        return seen[1]
    tiles = {t for t in b["tiles"] if not any(u[2] == t[2] and abs(u[0] - t[0]) <= DIG_UNSAFE_RADIUS
                                               and abs(u[1] - t[1]) <= DIG_UNSAFE_RADIUS for u in self.dig_unsafe)}
    if not tiles:
        self.batch_seen[b["id"]] = (self.day, 0)
        return 0
    xs, ys, zs = [t[0] for t in tiles], [t[1] for t in tiles], [t[2] for t in tiles]
    cx, cy = (min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2
    radius = min(20, max(max(xs) - cx, cx - min(xs), max(ys) - cy, cy - min(ys)) + 1)
    z_hi = max(zs)
    z_lo = max(min(zs), z_hi - 4)
    try:
        res = query_result(self.game.query("map", x=cx, y=cy, z=z_hi, z2=z_lo, radius=radius))
    except Exception as e:
        log("carp_batch_query_error", error=repr(e)[:160])
        res = None
    if not isinstance(res, dict) or not isinstance(res.get("designations"), list):
        self.batch_seen[b["id"]] = (self.day, None)
        return None
    des = {(q.get("x"), q.get("y"), q.get("z")) for q in map(d, res["designations"])}
    n = len({t for t in tiles if z_lo <= t[2] <= z_hi} & des)
    self.batch_seen[b["id"]] = (self.day, n)
    return n
def mine_citizen(self):
    try:
        res = query_result(self.game.query("units", kind="citizens", limit=300))
    except Exception as e:
        log("carp_units_error", error=repr(e)[:160])
        return None
    mine = [d(u) for u in lst(d(res).get("units")) if "MINE" in {str(x).upper() for x in lst(d(u).get("labors"))}]
    if len(mine) != 1:
        return None
    return mine[0].get("id"), str(mine[0].get("job") or "")
def barrels_pausable(self):
    empty = self.st.get("barrels_empty")
    if not isinstance(empty, int) or isinstance(empty, bool) or empty < BARREL_SAFE_FLOOR:
        return False, "empty_barrels_%s_below_%d" % (empty, BARREL_SAFE_FLOOR)
    if isinstance(self.brew_cancel_day, (int, float)) and isinstance(self.day, (int, float)) \
            and self.day - self.brew_cancel_day <= BREW_CANCEL_LOOKBACK_DAYS:
        return False, "brew_cancel_d%s" % self.brew_cancel_day
    return True, "empty_barrels_%d" % empty
def carp_paused_order(self, key, tool, args):
    p = getattr(self, "carp_pause", None)
    if p is None or key.startswith("carp_") or tool not in ("add_order", "add_manager_order"):
        return False
    recipe, job = args.get("recipe"), args.get("job")
    if recipe in CARP_PAUSE_RECIPES or job in ("MakeCrafts", "ConstructBed", "ConstructTable", "ConstructThrone"):
        return True
    return bool(p.get("barrels")) and (recipe == "make_barrel" or job == "MakeBarrel")
def carp_pause_step(self):
    if not isinstance(self.day, (int, float)):
        return
    for t in lst(self.o.get("recent_cancellations")):
        if "Brew" in str(t) and "Needs empty food storage item" in str(t):
            self.brew_cancel_day = self.day
    p = self.carp_pause
    if p is not None:
        b = next((x for x in self.dig_batches if x["id"] == p["batch"]), None)
        n = self.batch_pending(b) if b is not None else 0
        if p.get("barrels"):
            ok, why = self.barrels_pausable()
            if not ok:
                self.carp_resume(p, kinds=("MakeBarrel",), why="barrels:" + why)
        if n == 0:
            self.carp_resume(p, why="batch_clear")
        elif self.day - p["day"] >= CARP_PAUSE_MAX_DAYS:
            self.carp_resume(p, why="cap_%d_days" % CARP_PAUSE_MAX_DAYS)
            self.carp_capped_day = self.day
        return
    if d(self.o.get("burrows")).get("civilian_alert") is True or self.breach:
        return
    if isinstance(self.carp_capped_day, (int, float)) and self.day - self.carp_capped_day < CARP_PAUSE_COOLDOWN_DAYS:
        return
    waiting = [b for b in self.dig_batches if not b["paused"] and self.day - b["day"] >= CARP_PAUSE_WAIT_DAYS]
    if not waiting:
        return
    live = []
    for b in waiting:
        n = self.batch_pending(b)
        if n == 0:
            self.dig_batches.remove(b)
        elif n:
            live.append((b, n))
    if not live:
        return
    miner = self.mine_citizen()
    if miner is None or miner[1] not in CARP_MINER_JOBS:
        return
    b, n = live[0]
    b["paused"] = True
    barrels, bwhy = self.barrels_pausable()
    jobs = dict(CARP_PAUSE_JOBS, **({"MakeBarrel": "make_barrel"} if barrels else {}))
    saved = []
    for o in self.orders:
        oid = o.get("id")
        if oid not in self.owned or o.get("job") not in jobs:
            continue
        r = self.act("carp_pause_%s" % oid, "cancel_order", {"order_id": oid}, retry=0.25, limit=4)
        if r and r.get("ok"):
            saved.append({"id": oid, "job": o.get("job"), "left": o.get("left"), "src": self.order_src.get(oid),
                          "recipe": o.get("recipe") or jobs.get(o.get("job")), "repeat": o.get("repeat"),
                          "mat": o.get("material_category")})
            self.owned.discard(oid)
    self.carp_pause = {"day": self.day, "batch": b["id"], "saved": saved, "barrels": barrels}
    log("carp_pause", day=self.day, batch=b["id"], batch_key=b["key"], batch_day=b["day"], pending=n,
        miner=miner[0], miner_job=miner[1], cancelled=[(x["id"], x["job"], x["left"]) for x in saved],
        barrels=barrels, barrels_why=bwhy)
def carp_resume(self, p, kinds=None, why=""):
    keep, back = [], []
    for x in p["saved"]:
        if kinds is not None and x["job"] not in kinds:
            keep.append(x)
            continue
        src = x.get("src")
        if src is not None:
            key0, tool, args = src
            args = dict(args)
            if not args.get("repeat") and isinstance(x.get("left"), int) and x["left"] > 0:
                args["amount"] = min(30, x["left"])
        elif x.get("recipe"):
            key0, tool, args = None, "add_order", {"recipe": x["recipe"], "amount": max(1, min(30, x.get("left") or 1))}
        elif x.get("job"):
            key0, tool, args = None, "add_manager_order", {"job": x["job"], "amount": max(1, min(30, x.get("left") or 1)),
                                                           **({"material_category": x["mat"]} if x.get("mat") else {})}
        else:
            continue
        r = self.act("carp_resume_%s" % x["id"], tool, args, retry=0.25, limit=4)
        if r and r.get("ok"):
            res = r.get("result") if isinstance(r.get("result"), dict) else r
            if key0 and res.get("order_id") is not None:
                self.key_order[key0] = res.get("order_id")
                self.order_src[res.get("order_id")] = (key0, tool, args)
            back.append((x["id"], x["job"], args.get("amount")))
        else:
            keep.append(x)
    if kinds is not None:
        p["barrels"] = False
        p["saved"] = keep
        log("carp_resume", day=self.day, why=why, batch=p["batch"], readded=back, partial=True)
        return
    self.carp_pause = None
    log("carp_resume", day=self.day, why=why, batch=p["batch"], readded=back, failed=[x["id"] for x in keep],
        paused_days=round(self.day - p["day"], 2))
def pending_at(self, z):
    v = d(self.o.get("dig_pending_by_z")).get(str(z))
    return v if isinstance(v, int) and not isinstance(v, bool) else 0
def floor_stair(self, key, kind):
    if self.surface is None:
        return
    zs = [a.get("z") for a in self.kind("A") if self.dry(a.get("z")) and isinstance(a.get("z"), int)]
    if not zs:
        return
    zb = min(zs) - 1
    last = self.last.get(key)
    if last is not None and self.now - last < SURGE_FLOOR_STAIR_DAYS * DAY:
        return
    sent = self.floor_stair_sent.get(key)
    capped = False
    if sent is not None and sent[1] == zb and self.pending_at(zb) > 0 and len(sent) > 3 and not sent[3] \
            and isinstance(self.day, (int, float)) and isinstance(sent[2], (int, float)) \
            and self.day - sent[2] >= STAIR_WAIT_CAP_DAYS:
        capped = True
        log("floor_stair_wait_cap", day=self.day, key=key, site=sent[0], z_bottom=zb, since=sent[2])
    if sent is not None and sent[1] == zb and self.pending_at(zb) > 0 and not capped:
        if self.may("floor_stair_wait_log_" + key, 7, 10 ** 6):
            self.last["floor_stair_wait_log_" + key] = self.now
            log("floor_stair_wait", day=self.day, key=key, site=sent[0], z_bottom=zb, pending=self.pending_at(zb))
        return
    cands = [s for s in self.kind("S") if all(isinstance(s.get(k), int) for k in ("x", "y", "z"))
             and 0 < s["z"] - zb <= 20 and not self.column_dug(s, zb + 1, s["z"] - 1)]
    site = self.pick_dig_site(cands, levels=2) if cands else None
    if site is None:
        return
    res = self.act(key, "dig_stairs", {"site": site["id"], "z_bottom": zb}, retry=SURGE_FLOOR_STAIR_DAYS, limit=3)
    if res is None:
        return
    if res.get("ok"):
        self.floor_stair_sent[key] = (site.get("id"), zb, self.day, capped or bool(
            sent is not None and sent[1] == zb and len(sent) > 3 and sent[3]))
    log(kind, day=self.day, site=site.get("id"), z_bottom=zb, ok=res.get("ok"), free=self.surge_floor_free())
def stressed(self):
    owned = {z.get("owner") for z in self.zone("bedroom") if z.get("owner") is not None} | self.stress_done
    out = []
    for p in self.people:
        s = p.get("stress")
        if p.get("id") is None or not isinstance(s, int) or isinstance(s, bool):
            continue
        if p["id"] in owned:
            continue
        seen = self.stress_seen.get(p["id"])
        if s <= STRESS_CATEGORY or (s <= STRESS_RISE_CATEGORY and seen is not None and seen > s):
            out.append(p)
    out.sort(key=lambda p: p.get("stress") or 0)
    return out
def zone_of(self, word, owner):
    return next((z.get("id") for z in self.zone(word) if z.get("owner") == owner), None)
def farm_claimed(self, s):
    plots = [p for p in lst(self.o.get("farm_plots")) if isinstance(p, dict)]
    for r in self.kind("R"):
        if r.get("id") == s.get("id") or not str(self.roles.get(r.get("id")) or "").startswith("farm"):
            continue
        if any(self.rects_overlap(r, p) for p in plots):
            continue
        if BED_HELD_BOX and r.get("id") in (getattr(self, "bed_held", None) or ()) and lst(r.get("used_by")):
            continue
        if self.rects_overlap(r, s):
            return True
    return False
@staticmethod
def rects_overlap(a, b):
    v = [a.get(k) for k in ("x", "y", "z")] + [b.get(k) for k in ("x", "y", "z")] \
        + [(a.get("w"), a.get("h"), b.get("w"), b.get("h"))]
    nums = [x for t in v for x in (t if isinstance(t, tuple) else (t,))]
    if any(not isinstance(n, (int, float)) or isinstance(n, bool) for n in nums):
        return False
    return (a["z"] == b["z"] and a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
            and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])
def grazer_cull(self):
    if not self.may("grazer_cull", 1, 10 ** 6):
        return
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    surface = self.surface if num(getattr(self, "surface", None)) else d(self.map).get("surface_z")
    if not num(surface):
        return
    self.last["grazer_cull"] = self.now
    try:
        q = query_result(self.game.query("units", kind="animals"))
    except Exception as e:
        log("grazer_query_error", error=repr(e)[:160])
        return
    cand = []
    for a in map(d, lst(d(q).get("units") or d(q).get("animals"))):
        if not a.get("tame") or a.get("pet_owner_id") not in (None, -1) or a.get("marked_for_slaughter"):
            continue
        if not grazer_race(a.get("race")) or not num(a.get("z")) or a["z"] >= surface:
            continue
        cand.append(a)
    if not cand:
        return
    if not self.butchers_ready():
        self.build("Butchers", key=self.butcher_key())
    cand.sort(key=lambda a: (not a.get("adult"), a.get("id") or 0))
    marked = []
    for a in cand[:GRAZER_CULL_PER_PASS]:
        r = self.act("grazer_cull_%s" % a.get("id"), "slaughter", {"unit_id": a.get("id")}, retry=1, limit=3)
        if r and r.get("ok"):
            marked.append(a.get("id"))
    if marked:
        log("grazer_cull", day=self.day, marked=marked, races=sorted({str(a.get("race")) for a in cand}),
            below=len(cand), surface=surface)
def stray_attacks(self, obs):
    obs = d(obs)
    profs = {str(p.get("profession") or "").lower() for p in lst(obs.get("dwarves")) if isinstance(p, dict)}
    profs = {p for p in profs if p} | CITIZEN_WORDS
    seen = self.__dict__.setdefault("stray_seen", set())
    out = []
    for t in lst(obs.get("recent_events")):
        t = str(t)
        m = COMBAT_RE.match(t.lower().strip())
        if not m or t in seen:
            continue
        a, b = m.group(1).strip(), m.group(2).strip()
        if a.startswith("stray ") and citizen_noun(b, profs):
            seen.add(t)
            out.append((a[len("stray "):], t))
    return out
def stray_cull(self):
    if not STRAY_CULL:
        return
    pend = self.__dict__.setdefault("stray_pending", [])
    for name, text in self.stray_attacks(self.o):
        spec = stray_spec(name)
        if spec[0] is None:
            continue
        if spec not in pend:
            pend.append(spec)
        log("stray_attack", day=self.day, name=name, race=spec[0], text=text[:160])
    if not pend:
        return
    if not self.butchers_ready():
        self.build("Butchers", key=self.butcher_key())
    try:
        q = query_result(self.game.query("units", kind="animals"))
    except Exception as e:
        log("stray_query_error", error=repr(e)[:160])
        return
    marked, left = [], []
    animals = [d(a) for a in lst(d(q).get("units") or d(q).get("animals"))]
    for race, female, adult in pend:
        cand = [a for a in animals if a.get("tame") and a.get("pet_owner_id") in (None, -1)
                and not a.get("marked_for_slaughter") and a.get("id") not in marked
                and race in str(a.get("race") or "").upper().split("_")
                and (female is None or a.get("female") is None or bool(a.get("female")) == female)
                and (adult is None or a.get("adult") is None or bool(a.get("adult")) == adult)]
        for a in cand:
            if len(marked) >= STRAY_CULL_PER_PASS:
                left.append((race, female, adult))
                break
            r = self.act("stray_cull_%s" % a.get("id"), "slaughter", {"unit_id": a.get("id")}, retry=1, limit=3)
            if r and r.get("ok"):
                marked.append(a.get("id"))
    pend[:] = list(dict.fromkeys(left))
    if marked:
        log("stray_cull", day=self.day, marked=marked)
def stress_site(self, meeting=False):
    zapped = lambda s: any(covers(z, s) or self.rects_overlap(z, s) for z in self.zones)
    people = [] if meeting else self.people_boxes()
    roles = (None, "stress", "bedroom", "meeting") if meeting else (None, "stress", "bedroom")
    mine = [r for r in self.dug_rooms() if meeting and self.roles.get(r["id"]) == "meeting"]
    room = next((r for r in mine + self.dug_rooms() if r["id"] not in self.stress_rooms
                 and self.roles.get(r["id"]) in roles and not zapped(r)
                 and self.dry(r.get("z")) and not self.room_near_shaft(r)
                 and not self.under_people(dict(r, w=r.get("w") or 3, h=r.get("h") or 3), people)), None)
    if room:
        return room
    return next((s for s in self.closed_a() if s.get("id") not in self.stress_rooms and self.dry(s.get("z"))
                 and self.area_fits(s, ZONE_MAX) and (s.get("open_tiles") or 0) >= STRESS_ROOM_SIZE ** 2
                 and not zapped(s) and not self.farm_claimed(s) and not self.room_near_shaft(s)
                 and (meeting or not self.under_people(dict(s, w=STRESS_ROOM_SIZE, h=STRESS_ROOM_SIZE),
                                                         people))
                 and self.corner_floor(s)), None)
def stress_corner_site(self):
    people = self.people_boxes()
    num = lambda v: isinstance(v, int) and not isinstance(v, bool)
    stuff = [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
             if isinstance(f, dict) and f.get("kind") != "hatch" and all(num(f.get(k)) for k in ("x", "y", "z"))]
    keep_off = [z for z in self.zone("bedroom") + self.zone("meeting")
                if all(num(z.get(k)) for k in ("x", "y", "z", "w", "h"))]
    best = None
    for s in self.closed_a():
        if s.get("id") in self.stress_rooms or s.get("id") in self.zone_banned or not self.dry(s.get("z")) \
                or not all(num(s.get(k)) for k in ("x", "y", "z", "w", "h")):
            continue
        ax, ay, az = s["x"], s["y"], s["z"]
        for f in stuff:
            if f.get("kind") != "bed" or f["z"] != az or not (ax <= f["x"] < ax + min(s["w"], ZONE_MAX)
                                                               and ay <= f["y"] < ay + min(s["h"], ZONE_MAX)):
                continue
            box = {"x": ax, "y": ay, "z": az, "w": f["x"] - ax + 1, "h": f["y"] - ay + 1}
            if sum(1 for g in stuff if self.rects_overlap(g, box)) != 1 \
                    or any(self.rects_overlap(z, box) for z in keep_off) or self.under_people(box, people) \
                    or self.shaft_near(box):
                continue
            key = (box["w"] * box["h"], f["y"], f["x"])
            if best is None or key < best[0]:
                best = (key, dict(s, w=box["w"], h=box["h"], _bed=True))
    return best[1] if best else None
def corner_floor(self, s):
    if s.get("kind") != "A":
        return True
    if self.floor_refused(s.get("id"), STRESS_ROOM_SIZE, STRESS_ROOM_SIZE):
        return False
    w, h = s.get("w"), s.get("h")
    if isinstance(w, int) and isinstance(h, int) and (s.get("open_tiles") or 0) >= w * h:
        return True
    tiles = self.site_floor(s)
    return tiles is not None and self.floor_in(tiles, {"x": s["x"], "y": s["y"], "w": STRESS_ROOM_SIZE,
                                                       "h": STRESS_ROOM_SIZE}) >= 1
def room_near_shaft(self, s):
    if not self.shaft_people():
        return False
    box = {k: s.get(k) for k in ("x", "y", "z")}
    box.update(w=STRESS_ROOM_SIZE, h=STRESS_ROOM_SIZE)
    return self.shaft_near(box)
def stress_noble_office(self, p):
    did = p.get("id")
    if did not in (self.adm.get("MANAGER_id"), self.adm.get("EXPEDITION_LEADER_id")):
        return
    if self.zone_of("office", did):
        return
    spare = next((z for z in self.zone("office") if z.get("owner") is None), None)
    if spare:
        self.act("stress_office_as_%s" % did, "assign_zone", {"zone_id": spare["id"], "dwarf_id": did},
                 retry=1, limit=10)
        return
    site = self.stress_site()
    if site is None:
        return
    self.stress_rooms.add(site["id"])
    r = self.act("stress_office_z_%s" % did, "make_zone", {"kind": "office", "site": site["id"]}, retry=3, limit=4)
    if r and r.get("ok") and (self.free.get("chair") or 0) > 0:
        self.act("stress_office_c_%s" % did, "place_furniture", {"kind": "chair", "site": site["id"]},
                 retry=1, limit=6)
def head_ids(self):
    out = []
    el = self.adm.get("EXPEDITION_LEADER_id")
    if el is not None:
        out.append(el)
    for p in self.people:
        if p.get("id") is not None and p.get("id") not in out \
                and any(str(x).upper() in HEAD_POSITIONS for x in lst(p.get("positions"))):
            out.append(p.get("id"))
    return out
def head_offices(self):
    if self.days < 336 or self.hands_off is not None or self.breach:
        return
    due = (self.day or 0) >= self.calendar_day(LIAISON_OFFICE_DOY, LIAISON_OFFICE_DAY) \
        or self.liaison_seen or self.caravan_arrival_day is not None
    if not due:
        return
    mgr = self.adm.get("MANAGER_id")
    offices = self.zone("office")
    spares = [z for z in offices if z.get("owner") is None]
    if mgr is not None and self.zone_of("office", mgr) is None and spares \
            and spares[0].get("id") not in self.head_zones:
        spares = spares[1:]
    for did in self.head_ids():
        if did == mgr:
            continue
        mine = next((z for z in offices if z.get("owner") == did), None)
        if mine is not None:
            if d(mine.get("furniture")).get("chair") or d(mine.get("furniture_planned")).get("chair") \
                    or (self.free.get("chair") or 0) <= 0:
                continue
            room = next((s for s in self.sites if s.get("kind") in "RA" and s.get("z") == mine.get("z")
                         and s.get("x") == mine.get("x") and s.get("y") == mine.get("y")
                         and self.area_fits(s, PLACE_MAX)), None)
            if room is not None:
                self.act("head_office_c_%s" % did, "place_furniture", {"kind": "chair", "site": room["id"]},
                         retry=2, limit=6)
            continue
        if spares:
            z = spares.pop(0)
            self.act("head_office_as_%s" % did, "assign_zone", {"zone_id": z["id"], "dwarf_id": did},
                     retry=1, limit=10)
            continue
        if not self.may("head_office_z_%s" % did, 3, 4):
            continue
        site = self.stress_site() or self.head_office_site()
        if site is None:
            continue
        self.stress_rooms.add(site["id"])
        r = self.act("head_office_z_%s" % did, "make_zone", {"kind": "office", "site": site["id"]},
                     retry=3, limit=4)
        log("head_office", day=self.day, dwarf=did, site=site["id"], ok=bool(r and r.get("ok")))
        zid = d(r.get("result")).get("zone_id") if r and r.get("ok") else None
        if zid is not None:
            self.head_zones.add(zid)
            self.act("head_office_as_%s" % did, "assign_zone", {"zone_id": zid, "dwarf_id": did},
                     retry=1, limit=10)
        if r and r.get("ok") and (self.free.get("chair") or 0) > 0:
            self.act("head_office_cz_%s" % did, "place_furniture", {"kind": "chair", "site": site["id"]},
                     retry=1, limit=6)
def chair_target(self, seats):
    heads = len(self.head_ids()) if self.days >= 336 and self.hands_off is None else 0
    return seats + 1 + heads
def head_office_site(self):
    cands = [s for s in self.closed_a() if s.get("id") not in self.stress_rooms and self.dry(s.get("z"))
             and self.area_fits(s, ZONE_MAX)]
    offices = self.zone("office")
    clear = [s for s in cands if not any(covers(z, s) or self.rects_overlap(z, s) for z in offices)]
    return next(iter(clear + cands), None)
def stress_watch(self):
    low = [p for p in self.people if isinstance(p.get("stress"), int) and not isinstance(p.get("stress"), bool)
           and p["stress"] <= STRESS_WATCH_CATEGORY]
    if not low or not self.may("stress_watch", 1, 10 ** 6):
        return
    self.last["stress_watch"] = self.now
    want = {p.get("id") for p in low}
    units = {}
    try:
        res = query_result(self.game.query("units", kind="citizens", limit=300))
        units = {d(u).get("id"): d(u) for u in lst(d(res).get("units"))} if res is not None else {}
    except Exception as e:
        log("stress_watch_error", error=repr(e)[:160])
    rows = []
    for p in sorted(low, key=lambda p: (p["stress"], p.get("id") or 0)):
        u = units.get(p.get("id")) or {}
        needs = []
        for n in lst(u.get("needs")):
            n = d(n)
            f, lv = n.get("focus_level"), n.get("need_level")
            if isinstance(f, (int, float)) and isinstance(lv, (int, float)) and f < 0:
                needs.append((f * lv, str(n.get("need")), f, lv))
        needs.sort()
        rows.append({"id": p.get("id"), "cat": p["stress"], "job": p.get("job"), "squad": p.get("squad_id"),
                     "at": [p.get("x"), p.get("y"), p.get("z")],
                     "unmet": [[n, f, lv] for _, n, f, lv in needs[:STRESS_WATCH_NEEDS]]})
    log("stress_watch", day=self.day, alert=bool(d(self.o.get("burrows")).get("civilian_alert")),
        n=len(rows), cits=rows, ids=sorted(x for x in want if x is not None))
def stress_housing(self):
    if self.breach:
        return
    for p in self.stressed()[:STRESS_ROOM_CAP]:
        did = p.get("id")
        zone = self.stress_zone.get(did)
        if zone is None:
            zid = self.zone_of("bedroom", did)
            if zid is not None:
                zone = next(z for z in self.zone("bedroom") if z.get("id") == zid)
        if zone is None:
            site = self.stress_site()
            if site is None:
                if not any(self.roles.get(r["id"]) == "stress" and not r.get("dug") for r in self.kind("R")):
                    cand = next((r for r in self.undug_rooms() if self.dry(r.get("z")) and self.water_ok(r)
                                 and self.roles.get(r["id"]) is None and not self.room_near_shaft(r)
                                 and not self.people_later(r)), None)
                    if cand is not None:
                        res = self.act("dig_stress_" + cand["id"], "dig_room", {"site": cand["id"]}, retry=3, limit=4)
                        if res and res.get("ok"):
                            self.roles[cand["id"]] = "stress"
                            self.note_room_box(cand, {})
                    else:
                        site = self.stress_corner_site() if STRESS_CORNER else None
                        if site is None and self.may("stress_no_site_log", 7, 10 ** 6):
                            self.last["stress_no_site_log"] = self.now
                            log("stress_no_site", day=self.day, dwarf=did, stress=p.get("stress"))
                        elif site is not None:
                            log("stress_corner", day=self.day, dwarf=did, site=site["id"],
                                at=[site.get("x"), site.get("y"), site.get("z")])
                if site is None:
                    continue
            self.stress_rooms.add(site["id"])
            zw, zh = (site["w"], site["h"]) if "_bed" in site else (STRESS_ROOM_SIZE, STRESS_ROOM_SIZE)
            r = self.act("stress_zone_%s" % did, "make_zone",
                         {"kind": "bedroom", "site": site["id"], "w": zw, "h": zh}, retry=3, limit=4)
            at = d(d(r).get("result")).get("at") if r and r.get("ok") else None
            if not (r and r.get("ok")) or not (isinstance(at, list) and len(at) >= 3):
                continue
            zone = {"id": d(d(r).get("result")).get("zone_id"), "x": at[0], "y": at[1], "z": at[2],
                    "site": site["id"]}
            if site.get("_bed"):
                zone["has_bed"] = True
            self.stress_zone[did] = zone
        if zone.get("id") is None:
            continue
        if zone.get("has_bed"):
            pass
        elif (self.free.get("bed") or 0) > 0:
            sid = next((x.get("id") for x in self.sites if x.get("kind") in ("R", "A")
                        and all(x.get(k) == zone.get(k) for k in ("x", "y", "z"))), None) or zone.get("site")
            if sid is not None:
                self.act("stress_bed_%s" % did, "place_furniture",
                         {"kind": "bed", "site": sid, "w": STRESS_ROOM_SIZE, "h": STRESS_ROOM_SIZE, "count": 1},
                         retry=1, limit=10)
        elif not self.pending("make_bed"):
            self.act("stress_o_bed", "add_order", {"recipe": "make_bed", "amount": 1}, retry=2, limit=6)
        r = self.act("stress_assign_%s" % did, "assign_zone", {"zone_id": zone["id"], "dwarf_id": did},
                     retry=1, limit=10)
        if r and r.get("ok"):
            self.stress_done.add(did)
        self.stress_noble_office(p)
def house_everyone(self):
    if self.breach or self.surge or self.hands_off is not None:
        return
    owned = {z.get("owner") for z in self.zone("bedroom") if z.get("owner") is not None}
    owned |= self.stress_done | set(self.stress_zone)
    stressed = {p.get("id") for p in self.stressed()}
    cands = [p for p in self.people if p.get("id") is not None and p.get("id") not in owned
             and p.get("id") not in stressed]
    cands.sort(key=lambda p: (p.get("adult") is False, -(p.get("id") if isinstance(p.get("id"), int) else 0)))
    waiting_bed = 0
    for p in cands[:BEDROOM_PASS_CAP]:
        did = p.get("id")
        zone = self.bed_zone.get(did)
        if zone is None:
            site = self.stress_site()
            if site is None:
                inflight = sum(1 for r in self.kind("R") if self.roles.get(r["id"]) == "bedroom" and not r.get("dug"))
                if inflight >= BEDROOM_DIG_INFLIGHT:
                    continue
                farms_short = not self.farms_met()
                cand = self.pick_dig_site([r for r in self.undug_rooms() if self.dry(r.get("z"))
                                           and self.roles.get(r["id"]) is None and not self.room_near_shaft(r)
                                           and not (farms_short and r.get("soil"))
                                           and not self.people_later(r)])
                if cand is not None:
                    res = self.act("dig_bedroom_" + cand["id"], "dig_room", {"site": cand["id"]}, retry=3, limit=4)
                    if res and res.get("ok"):
                        self.roles[cand["id"]] = "bedroom"
                        self.note_room_box(cand, {})
                        log("bedroom_dig", day=self.day, dwarf=did, site=cand["id"])
                elif self.may("bedroom_no_site_log", 7, 10 ** 6):
                    self.last["bedroom_no_site_log"] = self.now
                    log("bedroom_no_site", day=self.day, dwarf=did, unhoused=len(cands))
                continue
            self.stress_rooms.add(site["id"])
            r = self.act("bedroom_zone_%s" % did, "make_zone",
                         {"kind": "bedroom", "site": site["id"], "w": STRESS_ROOM_SIZE, "h": STRESS_ROOM_SIZE},
                         retry=3, limit=4)
            at = d(d(r).get("result")).get("at") if r and r.get("ok") else None
            if not (r and r.get("ok")) or not (isinstance(at, list) and len(at) >= 3):
                continue
            zone = {"id": d(d(r).get("result")).get("zone_id"), "x": at[0], "y": at[1], "z": at[2],
                    "site": site["id"]}
            self.bed_zone[did] = zone
            log("bedroom", day=self.day, dwarf=did, site=site["id"], zone=zone.get("id"))
        if zone.get("id") is None:
            continue
        seen = next((z for z in self.zones if z.get("id") == zone["id"]), {})
        has_bed = (d(seen.get("furniture")).get("bed") or 0) + (d(seen.get("furniture_planned")).get("bed") or 0) > 0
        if not has_bed and "bedroom_bed_%s" % did not in self.done:
            if (self.free.get("bed") or 0) > 0:
                self.act("bedroom_bed_%s" % did, "place_furniture",
                         {"kind": "bed", "site": zone["site"], "w": STRESS_ROOM_SIZE, "h": STRESS_ROOM_SIZE,
                          "count": 1}, retry=1, limit=10)
            else:
                waiting_bed += 1
        r = self.act("bedroom_assign_%s" % did, "assign_zone", {"zone_id": zone["id"], "dwarf_id": did},
                     retry=1, limit=10)
        if r and r.get("ok"):
            self.done.add("bedroom_assign_%s" % did)
    if waiting_bed and not self.pending("make_bed") and self.logs():
        self.act("bedroom_o_bed", "add_order", {"recipe": "make_bed", "amount": min(BEDROOM_BED_BATCH,
                                                                                     waiting_bed + 1)},
                 retry=2, limit=99)
def mood(self):
    for m in lst(self.o.get("moods")):
        m = d(m)
        if m.get("mood") in ("Melancholy", "Raving", "Berserk", "Traumatized"):
            continue
        if not m.get("claimed_building_id"):
            want = MOOD_WORKSHOP.get(str(m.get("skill")).upper(), "Craftsdwarfs")
            stuck = getattr(self, "shop_stuck", None) or {}
            have = {w.get("type") for w in lst(self.o.get("workshops"))
                    if isinstance(w, dict) and (w.get("built") or w.get("id") not in stuck)}
            if want not in have:
                self.done.discard("ws_" + want)
                key = "ws_mood_%s_%d" % (want, int(self.now // (3 * DAY)))
                if not self.mood_build(want, key):
                    self.build(want, retry=1, key=key)
        for need in lst(m.get("items_needed")):
            if "bone" in str(d(need).get("item") or d(need).get("demand")).lower():
                self.butcher(for_food=False)
def note_w_sites(self):
    if not hasattr(self, "site_mem"):
        self.site_mem, self.wagon_seen, self.mem_tried = {}, None, set()
    wag = d(d(getattr(self, "map", None)).get("wagon"))
    xyz = tuple(wag.get(k) for k in ("x", "y", "z"))
    if wag.get("present") and all(isinstance(v, int) and not isinstance(v, bool) for v in xyz):
        self.wagon_seen = xyz
    for s in lst(getattr(self, "sites", None)):
        if isinstance(s, dict) and str(s.get("id", ""))[:1] in ("W", "G", "F") and all(
                isinstance(s.get(k), int) and not isinstance(s.get(k), bool) for k in ("x", "y", "z")):
            self.site_mem[s["id"]] = {k: s.get(k) for k in ("id", "x", "y", "z", "w", "h")}
            self.site_mem[s["id"]]["kind"] = s["id"][:1]
def remembered(self, kind):
    if d(d(getattr(self, "map", None)).get("wagon")).get("present", True):
        return []
    listed = {s.get("id") for s in lst(getattr(self, "sites", None)) if isinstance(s, dict)}
    tried = getattr(self, "mem_tried", None) or set()
    return [dict(s, _mem=True) for sid, s in sorted((getattr(self, "site_mem", None) or {}).items(),
                                                   key=lambda e: (e[0][:1], int(e[0][1:]) if e[0][1:].isdigit() else 0))
            if s.get("kind") == kind and sid not in listed and sid not in tried]
@staticmethod
def site_args(s, box=False):
    if not s.get("_mem"):
        return {"site": s["id"]}
    a = {"x": s["x"], "y": s["y"], "z": s["z"]}
    if box:
        a.update(w=s.get("w") or 3, h=s.get("h") or 3)
    return a
def mem_used(self, s, r):
    if s.get("_mem") and r is not None:
        if not hasattr(self, "mem_tried"):
            self.mem_tried = set()
        self.mem_tried.add(s["id"])
def shop_clash(self, s):
    for w in lst(self.o.get("workshops")):
        w = d(w)
        wx, wy = w.get("x"), w.get("y")
        if w.get("z") == s.get("z") and isinstance(wx, int) and isinstance(wy, int) \
                and abs(wx - s["x"]) <= 2 and abs(wy - s["y"]) <= 2:
            return True
    return False
def mood_sites(self):
    out = [s for s in lst(getattr(self, "sites", None)) if isinstance(s, dict)
           and str(s.get("id", "")).startswith("W") and not self.frame_on(s)]
    out += [s for s in self.remembered("W") if not self.shop_clash(s)]
    wag = getattr(self, "wagon_seen", None)
    if wag:
        out.sort(key=lambda e: -max(abs(e["x"] - wag[0]), abs(e["y"] - wag[1])))
    return out
def mood_build(self, want, key):
    if not isinstance(getattr(self, "o", None), dict):
        return False
    cands = self.mood_sites()
    if not cands or not self.material():
        return False
    s = cands[0]
    r = self.act(key, "build_workshop", dict(self.site_args(s), type=want), retry=1)
    if r and r.get("ok"):
        if not s.get("_mem"):
            self.sites = [x for x in self.sites if x.get("id") != s["id"]]
        log("mood_shop", day=self.day, type=want, site=s["id"], listed=not s.get("_mem"))
    self.mem_used(s, r)
    return True
def kitchen_sheltered(self):
    boxes = [d(b.get("bbox")) for b in lst(d(self.o.get("burrows")).get("list"))
             if isinstance(b, dict) and b.get("civ_alert_burrow")]
    for w in lst(self.o.get("workshops")):
        if not isinstance(w, dict) or w.get("type") != "Kitchen":
            continue
        x, y, z = w.get("x"), w.get("y"), w.get("z")
        for bb in boxes:
            try:
                if bb["x1"] <= x <= bb["x2"] and bb["y1"] <= y <= bb["y2"] and bb["z1"] <= z <= bb["z2"]:
                    return True
            except (KeyError, TypeError):
                continue
    return False
def slaughter_wait(self):
    alert = bool(d(self.o.get("burrows")).get("civilian_alert"))
    recent = self.alert_seen_day is not None and isinstance(self.day, (int, float)) \
        and self.day - self.alert_seen_day <= ALERT_QUIET_DAYS
    if (alert or recent) and not self.kitchen_sheltered():
        return "alert"
    return None
def f_livestock(self):
    if not self.alloc_on() or not isinstance(self.day, (int, float)):
        return
    left = self.days_to_end()
    if left is None or left > self.f_len() or left < F_SLAUGHTER_TAIL:
        return
    if self.my1_plan() and self.f_len() - left < F_SLAUGHTER_FROM:
        return
    food = self.st.get("food_edible") or 0
    use = self.use_rate("food", ALLOC_FOOD_PER_CIT_DAY) * max(1, self.cit or 0)
    if use <= 0 or food / use >= F_FOOD_COVER_DAYS:
        return
    if self.slaughter_wait() is not None or not self.may("f_slaughter", F_SLAUGHTER_DAYS, 99):
        return
    if not self.butchers_ready():
        self.build("Butchers", key=self.butcher_key())
    try:
        q = query_result(self.game.query("units", kind="animals"))
    except Exception as e:
        log("butcher_query_error", error=repr(e)[:160])
        return
    units = [d(a) for a in lst(d(q).get("units") or d(q).get("animals"))]
    if self.my1_plan():
        units.sort(key=lambda a: any(w in SMALL_ANIMALS for w in str(a.get("race") or "").upper().split("_")))
    for a in units:
        if a.get("tame") and a.get("pet_owner_id") in (None, -1) and not a.get("marked_for_slaughter"):
            r = self.act("f_slaughter", "slaughter", {"unit_id": a.get("id")}, retry=F_SLAUGHTER_DAYS, limit=99)
            if r is not None:
                log("f_slaughter", day=self.day, unit=a.get("id"), race=a.get("race"), food=food,
                    cover=round(food / use), left=left, ok=r.get("ok"))
            return
def butcher(self, for_food=True):
    if not self.butchers_ready():
        self.build("Butchers", key=self.butcher_key())
    if for_food:
        why = self.slaughter_wait()
        if why is not None:
            if self.may("slaughter_wait_log", 1, 99):
                self.last["slaughter_wait_log"] = self.now
                log("slaughter_wait", day=self.day, why=why, perishable=self.perishable(),
                    alert_seen=self.alert_seen_day)
            return
    if not self.may("slaughter", 5, 3):
        return
    try:
        q = query_result(self.game.query("units", kind="animals"))
    except Exception as e:
        log("butcher_query_error", error=repr(e)[:160])
        return
    keep = for_food and self.f_reserve_hold()
    for a in sorted(map(d, lst(d(q).get("units") or d(q).get("animals"))), key=lambda a: not grazer_race(a.get("race"))):
        if keep and not grazer_race(a.get("race")):
            if not self.f_reserve_logged:
                self.f_reserve_logged = True
                log("f_reserve_keep", day=self.day, unit=a.get("id"), race=a.get("race"),
                    food=self.st.get("food_edible"), cit=self.cit)
            continue
        if a.get("tame") and a.get("pet_owner_id") in (None, -1) and not a.get("marked_for_slaughter"):
            self.act("slaughter", "slaughter", {"unit_id": a.get("id")}, retry=5, limit=3)
            return
def defend(self):
    th, mil = d(self.o.get("threats")), d(self.o.get("military"))
    bur = d(self.o.get("burrows"))
    alert = bur.get("civilian_alert")
    if alert and self.alert_since is None:
        self.alert_since = self.now
    elif alert is False:
        self.alert_since = None
        if self.wild_spans and self.wild_spans[-1][1] is None and self.wild_alert_since is not None \
                and self.now - self.wild_alert_since > DAY:
            self.wild_alert_closed()
            self.wild_alert_since = None
    squads = lst(mil.get("squads"))
    squad = d(squads[0]) if squads else None
    foes = [d(h) for h in lst(th.get("hostiles")) if d(h).get("invader")]
    if squad:
        self.arm_record(squad)
    if not squad and foes and self.cit >= SQUAD_MIN_CIT:
        self.create_squad("squad", self.fight_squad_size(th))
    elif not squad and self.cit >= SQUAD_MIN_CIT:
        self.create_squad("squad", 4)
    if squad and squad.get("uniform") == "none" and self.equip_day is None:
        tpl = self.uniform_choice()
        r = self.act("equip", "equip_squad", {"uniform": tpl}, retry=1, limit=3)
        if r is not None:
            if not r.get("ok") and tpl == "metal":
                self.metal_refused = True
                self.tries["equip"] = max(0, self.tries.get("equip", 1) - 1)
                self.last.pop("equip", None)
            if r.get("ok"):
                self.equip_day = self.day
            log("equip_once", day=self.day, uniform=tpl, ok=r.get("ok"), invaders=bool(foes))
    if squad and squad.get("uniform") not in (None, "none"):
        self.spear_supply(squad)
    self.gate_survey()
    self.shelter_grow()
    invaders = [h for h in lst(th.get("hostiles")) if d(h).get("invader")]
    hostile = th.get("visible_hostiles") or 0
    window = self.invader_window is not None and self.now < self.invader_window
    if self.invader_window is not None and not window:
        log("invader_window_end", day=self.day, invaders=len(invaders), hostile=hostile,
            guard=list(self.invader_guard) if self.invader_guard else None)
        self.invader_window = None
    orders = lst((squad or {}).get("orders"))
    odds = self.fight_odds(squad, th) if hostile and squad else None
    if hostile and squad and odds["go"] and not window \
            and (not orders or self.mark_station is not None or self.invader_guard is not None
                 or self.muster is not None):
        args = {"order": "attack"}
        if odds["targets"] is not None:
            args["target_ids"] = odds["targets"]
        r = self.act("attack", "squad_order", args, retry=1, limit=99)
        if r and r.get("ok"):
            self.mark_station = None
            self.gate_post = False
            self.invader_guard = None
            self.muster = None
            log("fight_go", day=self.day, ours=odds["ours"], theirs=odds["theirs"], endgame=odds["endgame"],
                armed=odds["armed"], members=odds["members"], foes=odds["foes"])
    elif hostile and squad and not odds["go"] and not window:
        attacking = any(d(o).get("order") == "attack" for o in orders)
        armable = len(self.armable_ids(squad))
        odds_arm = self.fight_odds(dict(squad, armed=max(squad.get("armed") or 0, armable)), th)
        if invaders and not attacking and self.invader_guard is None \
                and squad.get("uniform") not in (None, "none") and odds_arm["why"] != "big_only" \
                and (odds_arm["go"] or not self.duty_seen or self.muster is not None):
            self.guard_muster(squad, force="invaders")
        elif (attacking and odds["retreat"]) or self.invader_guard is not None:
            r = self.act("fight_retreat", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
            if r and r.get("ok"):
                self.invader_guard = None
                log("fight_retreat", day=self.day, ours=odds["ours"], theirs=odds["theirs"], why=odds["why"])
        elif self.fight_log_day != self.day:
            self.fight_log_day = self.day
            log("fight_hold", day=self.day, ours=odds["ours"], theirs=odds["theirs"], why=odds["why"],
                armed=odds["armed"], members=odds["members"], foes=odds["foes"], endgame=odds["endgame"],
                attacking=attacking)
    if not hostile and orders and self.mark_station is None and self.muster is None:
        r = self.act("stand_down", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
        if r and r.get("ok"):
            self.invader_guard = None
    if not hostile and squad:
        self.guard_muster(squad)
    if window and hostile:
        self.invader_guard_station(squad, invaders)
    near = (th.get("nearest_hostile_dist_to_wagon") or 10 ** 6) <= 45
    if invaders and near and not alert and not self.alert_barred() and not window \
            and self.shelter_listed(bur):
        r = self.act("alert_on", "civilian_alert", {"on": True}, retry=1, limit=10 ** 6)
        if r and r.get("ok"):
            self.alert_since = self.now
    too_long = self.alert_since is not None and self.now - self.alert_since > 10 * DAY
    thirst = self.thirst_due()
    if thirst and alert:
        too_long = True
    elif thirst and self.access_from is not None:
        until = self.access_from + ACCESS_WINDOW_DAYS * DAY
        if self.wild_rest_until is None or self.wild_rest_until < until:
            self.wild_rest_until = until
            log("access_hold", day=self.day, until_day=round(until / DAY, 1),
                since_day=round(self.access_tick / DAY, 1))
    elif thirst and self.access_log_day != self.day:
        self.access_log_day = self.day
        inside = next((d(b).get("citizens_inside") for b in lst(bur.get("list"))
                       if d(b).get("civ_alert_burrow")), None)
        log("access_unseen", day=self.day, since_day=round(self.access_tick / DAY, 1), inside=inside,
            citizens=self.cit, drink=self.st.get("drink"), wanting=self.thirst_signs(),
            locked=sorted(str(d(x).get("id")) for x in lst(d(self.o.get("doors")).get("list"))
                          if d(x).get("locked")))
        self.trap_seen += 1
        self.shelter_trap()
    if not thirst:
        self.trap_pokes, self.trap_last, self.trap_seen = 0, None, 0
    big = self.big_units() if alert else []
    if big and self.alert_since is not None and self.now - self.alert_since > BIG_FREE_DAYS * DAY \
            and not self.wild_approaching(big):
        log("big_hold_aged", day=self.day, animals=sorted({u["_mark"] for u in big}))
        big = []
    if alert and big and not too_long and not invaders:
        for u in big:
            self.wild_watch[u["_mark"]] = self.now
        if self.big_log_day != self.day:
            self.big_log_day = self.day
            log("big_hold", day=self.day, animals=sorted({u["_mark"] for u in big}), near=len(big))
    lift = alert and ((not invaders and not big and not self.wild_alert_hold()) or too_long)
    if lift and not too_long and self.home_holding():
        lift = False
    if lift and not invaders and self.alert_since is not None \
            and self.now - self.alert_since <= (10 + CAP_DEFER_DAYS) * DAY \
            and not (thirst and self.now - self.access_tick > (ACCESS_CAP_DAYS + CAP_DEFER_DAYS) * DAY):
        pressing = self.mark_pressing()
        if too_long and not pressing:
            pressing = self.fight_pressing()
        if pressing:
            if self.may("cap_defer_log", 1, 10 ** 6):
                self.last["cap_defer_log"] = self.now
                log("cap_defer", day=self.day, animals=pressing, cap=too_long)
            lift = False
    if lift and not invaders and not thirst and self.gate_waiting:
        close = self.shaft_wait_close()
        if close:
            if self.may("shaft_wait_defer_log", 1, 10 ** 6):
                self.last["shaft_wait_defer_log"] = self.now
                log("shaft_wait_defer", day=self.day, animals=sorted({u["_mark"] for u in close}), cap=too_long)
            lift = False
    if lift and invaders:
        if thirst:
            budget = self.now - self.access_tick <= (ACCESS_CAP_DAYS + CAP_DEFER_DAYS) * DAY
        else:
            budget = self.alert_since is not None and self.now - self.alert_since <= (10 + CAP_DEFER_DAYS) * DAY
        at_door = self.invaders_at_entrance(invaders) if budget else []
        if at_door:
            if self.invader_defer_day != self.day:
                self.invader_defer_day = self.day
                log("invader_defer", day=self.day, invaders=at_door,
                    since_day=round(self.access_tick / DAY, 1) if self.access_tick is not None else None)
            lift = False
    if lift:
        r = self.act("alert_off", "civilian_alert", {"on": False}, retry=1, limit=99)
        if r and r.get("ok"):
            if isinstance(self.o.get("burrows"), dict):
                self.o["burrows"]["civilian_alert"] = False
            if self.wild_alert_since is not None or big:
                self.wild_rest_until = self.now + WILD_REST_DAYS * DAY
                self.wild_alert_closed()
                log("wild_rest", day=self.day, cap=too_long, until_day=self.day + WILD_REST_DAYS
                    if isinstance(self.day, (int, float)) else None)
            if thirst:
                until = self.now + ACCESS_WINDOW_DAYS * DAY
                if self.wild_rest_until is None or self.wild_rest_until < until:
                    self.wild_rest_until = until
                log("access_lift", day=self.day, since_day=round(self.access_tick / DAY, 1),
                    wanting=self.thirst_signs(), drink=self.st.get("drink"))
            if invaders:
                self.invader_window = self.now + ACCESS_WINDOW_DAYS * DAY
                if self.wild_rest_until is None or self.wild_rest_until < self.invader_window:
                    self.wild_rest_until = self.invader_window
                self.invader_guard = None
                log("invader_window", day=self.day, until_day=round(self.invader_window / DAY, 1),
                    invaders=len(invaders), thirst=bool(thirst),
                    squad=len(lst(squad.get("members"))) if squad else 0,
                    armed=(squad.get("armed") or 0) if squad else 0)
                if hostile:
                    self.invader_guard_station(squad, invaders)
            self.alert_since = None
            self.wild_alert_since = None
def create_squad(self, key, n):
    if key in self.done or not self.may(key, 5, 3):
        return None
    ids = self.squad_pick(n)
    args = {"dwarf_ids": ids} if ids else {"size": n}
    return self.act(key, "create_squad", args, retry=5, limit=3)
