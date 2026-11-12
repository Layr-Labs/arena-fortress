"""Overseer class body, part 1 of 4. Not a module of its own: harness.py executes this file inside `class Overseer`, with harness.py's globals."""
def __init__(self, game, goal="", days=0):
    self.game = game
    self.surge_wish = "migrant" in str(goal).lower()
    self.days = days or 0
    self.tries, self.last = {}, {}
    self.roles = {}
    self.room_box = {}
    self.brew_orders = set()
    self.now = 0
    self.alert_since = None
    self.hands_off = None
    self.days_left = None
    self.day = None
    self.owned = set()
    self.overflow = set()
    self.last_place = {}
    self.report = []
    self.done = set()
    self.food_hist = deque(maxlen=FOOD_HISTORY)
    self.rate_hist = deque(maxlen=RATE_WINDOW)
    self.stock_hist = deque(maxlen=SLOPE_WINDOW)
    self.stock_day = None
    self.sliding = False
    self.glut_prev = None
    self.glut_jump = 0
    self.cup_target = None
    self.key_order = {}
    self.caravan_cursor = None
    self.caravan_probe_day = None
    self.caravan_active = False
    self.caravan_last_day = None
    self.caravan_arrival_day = None
    self.caravan_leave_day = None
    self.winter_plan_year = None
    self.craft_mark = None
    self.craft_amount_day = None
    self.craft_desired = None
    self.pop_prev = None
    self.waves = 0
    self.rank_note = False
    self.stall_note = False
    self.window_fund = None
    self.water_halts = {}
    self.water_cache = {}
    self.water_cache_day = {}
    self.water_probe_day = {}
    self.water_probes, self.water_probe_day_no = 0, None
    self.water_event_tick = None
    self.dig_at_water = []
    self.water_base = None
    self.breach = None
    self.wet_z = set()
    self.fort_water_memo = (None, None)
    self.gain_outside = False
    self.fort_dry_scans = 0
    self.fort_dry_day = None
    self.shafts = {}
    self.scan = (None, [])
    self.rise_watch = None
    self.wet_day = None
    self.hatch_id = None
    self.flood_locked = set()
    self.hatch_water_memo = {}
    self.wet_skip_day = {}
    self.shop_stuck = {}
    self.frame_idle = {}
    self.frame_seen = {}
    self.dead_w_sites = set()
    self.site_mem = {}
    self.wagon_seen = None
    self.mem_tried = set()
    self.zone_banned = set()
    self.place_banned = set()
    self.f_yield_food_t = None
    self.f_lift_base = None
    self.office_tile = None
    self.office_yield = None
    self.office_shelter_tried = set()
    self.open_maps = {}
    self.level_maps = {}
    self.shelter_level_in = set()
    self.stress_done = set()
    self.stress_zone = {}
    self.meeting_looks = [0, 0, 0]
    self.meeting_looks_tick = None
    self.stress_seen = {}
    self.bed_zone = {}
    self.stress_rooms = set()
    self.wild_day = {}
    self.wild_from = {}
    self.wild_act_stamp = None
    self.loads = 0
    self.alloc = None
    self.alloc_day = None
    self.seeds_cond_ok = True
    self.census_day = None
    self.census = {}
    self.fruit_seen = False
    self.hold_armed = False
    self.hold_seen_day = None
    self.hold_mode = None
    self.f_rec = []
    self.f_plan_key = None
    self.barrel_lost_day = None
    self.own_seeds = {}
    self.own_food = None
    self.own_plants = None
    self.merchant_plants = None
    self.f_dry_floor = None
    self.f_reserve_logged = False
    self.wild_alert_since = None
    self.wild_watch = {}
    self.wild_rest_until = None
    self.access_tick = None
    self.access_from = None
    self.access_drink = None
    self.access_log_day = None
    self.invader_window = None
    self.invader_guard = None
    self.invader_guard_foot = False
    self.invader_defer_day = None
    self.invader_unguarded_day = None
    self.fight_log_day = None
    self.guard_need_why = None
    self.muster = None
    self.muster_since = None
    self.muster_contact = None
    self.shaft_since = None
    self.shaft_contact = None
    self.gate_post = False
    self.shaft_rest = False
    self.mark_wait_since = None
    self.gate_waiting = False
    self.gate_mark_seen = None
    self.gear_cache = None
    self.gear_where = None
    self.squad_post = None
    self.armed_seen = {}
    self.duty_from = None
    self.duty_seen = False
    self.metal_refused = False
    self.equip_day = None
    self.spears_ordered = 0
    self.access_look = None
    self.safe_held = False
    self.safe_log_day = None
    self.wild_dist_prev = {}
    self.wild_dist_load = None
    self.lock_skip_day = None
    self.wild_units_memo = None
    self.wild_spans = []
    self.wild_evidence = {}
    self.wild_fight = {}
    self.wild_dist = {}
    self.event_seen = {}
    self.mark_interrupts = {}
    self.bed_full = {}
    self.seat_full = {}
    self.floor_maps = {}
    self.nofloor = {}
    self.house_full_day = None
    self.seat_nobox_day = None
    self.seat_refused_day = None
    self.new_zones = []
    self.pend_mark = None
    self.rot_seen = False
    self.pass_days = []
    self.rot_brews = set()
    self.recycle_brews = set()
    self.stall_brews = set()
    self.stall_memo = None
    self.stall_on = False
    self.cook_wait_since = None
    self.kitchen_busy_since = None
    self.brew_shots = {}
    self.fruit_census_day = None
    self.seed_wait = 0
    self.kind_seasons = {}
    self.rot_prev = None
    self.rot_hist = []
    self.press_on = False
    self.press_stand = False
    self.press_harv = False
    self.kind_brew = {}
    self.idle_days = []
    self.plant_age = []
    self.age_day = None
    self.wood_hist = []
    self.press_memo = None
    self.press_day = None
    self.labor_on = False
    self.labor_memo = None
    self.labor_nojob = 0
    self.plant_census_day = None
    self.in_plot = None
    self.seed_seen = {}
    self.seed_first_day = None
    self.plant_loose = None
    self.loose_hist = []
    self.stall_since = None
    self.stall_logged = False
    self.alert_seen_day = None
    self.mig_prev = None
    self.mig_start = None
    self.mig_waves = 0
    self.wealth_hist = deque(maxlen=CRAFT_STALL_DAYS * 4)
    self.plan_key = None
    self.liaison_seen = False
    self.head_zones = set()
    self.lean_drink = None
    self.marked = {n: "seed" for n in DANGER_SEED}
    self.mark_fought = set()
    self.mark_station = None
    self.mark_kind = None
    self.plot_rooms = set()
    self.bed_held = set()
    self.mark_hold = None
    self.mark_settled = {}
    self.mark_last_seen = {}
    self.mark_arrived = {}
    self.water_rise_tick = None
    self.risk = []
    self.mark_query = None
    self.shelter_made = False
    self.shelter_added = set()
    self.shelter_skip = set()
    self.entrances = {}
    self.alert_locked = set()
    self.prearm_seen = None
    self.trap_last = None
    self.pocket_memo = {}
    self.pocket_reads = (None, 0)
    self.trap_pokes = 0
    self.trap_seen = 0
    self.entrance_occupied = set()
    self.gate_top = False
    self.big_log_day = None
    self.hatch_ordered = 0
    self.shaft = None
    self.shaft_stop = False
    self.dig_batches = []
    self.dig_unsafe = set()
    self.order_src = {}
    self.carp_pause = None
    self.carp_capped_day = None
    self.brew_cancel_day = None
    self.batch_seen = {}
    self.floor_stair_sent = {}
    self.shaft_open_days = []
    self.stranded = set()
    self.stranded_day = None
    self.stranded_known = set()
    self.stranded_fort = set()
    self.home_call = None
    self.strand_skipped = {}
    self.gates = {}
    self.gate_seen = {}
    self.gate_probe_day = None
    self.gate_door_ordered = 0
    self.shelter_boxes = {}
    log("danger_list", seed=sorted(self.marked), weak=list(DANGER_WEAK))
def may(self, key, retry=2, limit=6):
    return self.tries.get(key, 0) < limit and self.now - self.last.get(key, -10 ** 9) >= retry * DAY
def act(self, key, tool, args, retry=2, limit=6):
    if key in self.done or not self.may(key, retry, limit):
        return None
    if self.carp_paused_order(key, tool, args):
        self.last[key] = self.now
        if self.may("carp_hold_log_" + key, 1, 10 ** 6):
            self.last["carp_hold_log_" + key] = self.now
            log("carp_pause_hold", day=self.day, key=key, tool=tool, args=args)
        return {"ok": False, "error_code": "carp_pause", "local": True,
                "error": "not run: the layer's carpentry orders wait while the miner digs"}
    if tool == "place_furniture" and self.floor_refused(args.get("site"), args.get("w"), args.get("h")):
        return {"ok": False, "error_code": OVERFLOW_ERROR, "local": True,
                "error": "no free floor tile (this box answered so and nothing on its site changed since)"}
    if tool in OPEN_SITE_TOOLS and key not in OFFICE_TEMP_KEYS \
            and str(args.get("site") or "")[:1] in (("A", "R") if tool == "create_burrow" else ("A",)):
        n_open = self.box_open(self.call_box({"site": args["site"]} if str(args["site"])[:1] == "A" else args))
        if n_open:
            self.tries[key] = self.tries.get(key, 0) + 1
            self.last[key] = self.now
            if self.may("site_open_log_" + key, 1, 10 ** 6):
                self.last["site_open_log_" + key] = self.now
                log("site_open", day=self.day, key=key, tool=tool, args=args, outside=n_open)
            return {"ok": False, "error_code": "site_open", "local": True,
                    "error": "not run: %d walkable outside tile(s) in the box" % n_open}
    if tool == "dig_stairs" and str(args.get("site") or "")[:1] == "S":
        hold = "the fort already has %d surface entrances (the observation lists %d; an unlisted one takes no " \
            "hatch)" % (len(self.entrances), ENTRANCE_LIST_MAX) if len(self.entrances) >= ENTRANCE_LIST_MAX else None
        if hold:
            self.last[key] = self.now
            if self.may("entrance_hold_log_" + key, 1, 10 ** 6):
                self.last["entrance_hold_log_" + key] = self.now
                log("entrance_hold", day=self.day, key=key, args=args, why=hold)
            return {"ok": False, "error_code": "entrance_hold", "local": True, "error": "not run: " + hold}
        box = self.call_box({"site": args.get("site"), "w": 1, "h": 1})
        near = self.beasts_near(dict(zip(("x", "y", "z", "w", "h"), box)), WILD_NEAR_TILES, WILD_NEAR_Z) \
            if box else []
        if near:
            self.last[key] = self.now
            if self.may("dig_beast_log_" + key, 1, 10 ** 6):
                self.last["dig_beast_log_" + key] = self.now
                log("dig_beast_hold", day=self.day, key=key, args=args, near=near[:3])
            return {"ok": False, "error_code": "beast_near", "local": True,
                    "error": "not run: a big beast is near the stair site"}
    why = self.room_reserved(tool, args)
    if why:
        self.tries[key] = self.tries.get(key, 0) + 1
        self.last[key] = self.now
        if self.may("room_reserved_log_" + key, 7, 10 ** 6):
            self.last["room_reserved_log_" + key] = self.now
            log("room_reserved", day=self.day, key=key, tool=tool, args=args, why=why)
        return {"ok": False, "error_code": "room_reserved", "local": True, "error": "not run: " + why}
    self.tries[key] = self.tries.get(key, 0) + 1
    self.last[key] = self.now
    r = self.game.act(tool, args)
    if tool == "place_furniture" and not r.get("ok") and args.get("site") is not None \
            and "no free floor tile" in str(r.get("error") or ""):
        self.nofloor[self.nofloor_key(args["site"], args.get("w"), args.get("h"))] = \
            (self.obs_day(), self.site_sig(args["site"]))
    self.count += 1
    log("act", key=key, tool=tool, args=args, ok=r.get("ok"), code=r.get("error_code"),
        err=str(r.get("error") or "")[:160])
    if not r.get("ok") and tool in ("make_zone", "place_furniture") and args.get("site") is not None:
        m = re.search(r"\[1, ?(\d+)\]", str(r.get("error") or ""))
        if m:
            banned = self.zone_banned if tool == "make_zone" else self.place_banned
            if args["site"] not in banned:
                banned.add(args["site"])
                log("wide_site", day=self.day, tool=tool, site=args["site"], cap=int(m.group(1)))
    if not r.get("ok") and r.get("error_code") == "site_used" and args.get("site") is not None \
            and re.search(r"already used \(farm plot", str(r.get("error") or "")):
        sid = args["site"]
        self.plot_rooms.add(sid)
        if self.roles.get(sid) not in (None, "farm"):
            log("room_lost_to_plot", day=self.day, site=sid, role=self.roles.get(sid), tool=tool)
            self.roles.pop(sid, None)
    if r.get("ok"):
        self.tries[key] = max(0, self.tries[key] - 1)
        if tool == "create_burrow":
            self.shelter_made = True
        if tool == "make_zone" and str(args.get("site") or "").startswith("R"):
            label = {"dormitory": "Dormitory", "dining_hall": "DiningHall", "office": "Office",
                     "meeting_area": "MeetingHall", "bedroom": "Bedroom"}.get(args.get("kind"), "zone")
            for s_ in self.sites:
                if s_.get("id") == args["site"]:
                    s_["free"] = False
                    s_["used_by"] = sorted(set(lst(s_.get("used_by"))) | {label + " (this pass)"})
        if tool == "make_zone":
            at = d(r.get("result")).get("at")
            if isinstance(at, list) and len(at) >= 5 and all(isinstance(v, int) for v in at[:5]):
                label = {"dormitory": "Dormitory", "dining_hall": "DiningHall", "office": "Office",
                         "meeting_area": "MeetingHall", "bedroom": "Bedroom"}.get(args.get("kind"), "zone")
                self.zones.append({"id": d(r.get("result")).get("zone_id"), "type": label, "x": at[0],
                                   "y": at[1], "z": at[2], "w": at[3], "h": at[4], "this_pass": True})
        if tool == "assign_zone" and args.get("zone_id") is not None:
            for z_ in self.zones:
                if isinstance(z_, dict) and z_.get("id") == args["zone_id"]:
                    z_["owner"] = args.get("dwarf_id")
        zb = args.get("z_bottom")
        if tool == "dig_stairs" and args.get("site") is not None and isinstance(zb, int) \
                and not isinstance(zb, bool):
            self.shafts[args["site"]] = min(zb, self.shafts.get(args["site"], zb))
        if tool == "civilian_alert" and isinstance(self.o.get("burrows"), dict):
            self.o["burrows"]["civilian_alert"] = bool(args.get("on"))
        if tool == "squad_order":
            if key != "squad_reassert":
                self.squad_post = None if args.get("order") == "stand_down" else (key, dict(args))
            sq = next(iter(lst(d(self.o.get("military")).get("squads"))), None)
            if isinstance(sq, dict):
                if args.get("order") == "stand_down":
                    sq["orders"] = []
                elif args.get("order") == "station":
                    sq["orders"] = [{"order": "station", "x": args.get("x"), "y": args.get("y"),
                                     "z": args.get("z")}]
                elif args.get("order") == "attack":
                    sq["orders"] = [{"order": "attack"}]
        if tool == "add_order" and args.get("recipe") == "brew_drink" and args.get("repeat") == "daily":
            order_id = d(r.get("result")).get("order_id")
            if type(order_id) is int:
                self.brew_orders.add(order_id)
        if tool == "add_order" and args.get("recipe") == "brew_drink" and not args.get("repeat") \
                and key in BREW_SHOT_KEYS:
            order_id = (r.get("result") if isinstance(r.get("result"), dict) else r).get("order_id")
            if type(order_id) is int:
                self.brew_shots[order_id] = key
    if r.get("ok") and tool in ("add_order", "add_manager_order"):
        res = r.get("result") if isinstance(r.get("result"), dict) else r
        if res.get("order_id") is not None:
            self.owned.add(res.get("order_id"))
            self.key_order[key] = res.get("order_id")
            if isinstance(getattr(self, "order_src", None), dict):
                self.order_src[res.get("order_id")] = (key, tool, dict(args))
        if args.get("repeat") and key.startswith("o_") and key.endswith(("_end", "_win", "_prog")):
            self.done.add(key)
    if r.get("ok") and tool in ("dig_room", "dig_stairs") and isinstance(getattr(self, "dig_batches", None), list):
        self.note_dig_batch(key, tool, args)
    self.report = (self.report + [{"day": self.day, "tool": tool, "args": args, "ok": bool(r.get("ok")),
                                   **({"error_code": r.get("error_code"), "error": str(r.get("error") or "")[:100]}
                                      if not r.get("ok") else {})}])[-REPORT_KEEP:]
    return r
def load(self, resp):
    self.loads += 1
    self.o = d(resp.get("observation"))
    self.st, self.map = d(self.o.get("stocks")), d(self.o.get("map"))
    self.adm = d(self.o.get("administrators"))
    self.hands_off = resp.get("hands_off_in_days")
    self.surge = self.surge_wish and self.hands_off is not None
    self.days_left = resp.get("days_left") if isinstance(resp.get("days_left"), int) else None
    self.day = resp.get("day")
    if isinstance(self.day, (int, float)) and not isinstance(self.day, bool) \
            and (not self.pass_days or self.day > self.pass_days[-1]):
        self.pass_days = (self.pass_days + [self.day])[-4:]
    self.now = d(self.o.get("date")).get("abs_tick") or resp.get("tick") or 0
    self.people = [x for x in lst(self.o.get("dwarves")) if isinstance(x, dict)]
    seen_cat = getattr(self, "stress_seen", None)
    for x in self.people if isinstance(seen_cat, dict) else ():
        c = x.get("stress")
        if x.get("id") is not None and isinstance(c, int) and not isinstance(c, bool):
            seen_cat[x["id"]] = max(seen_cat.get(x["id"], c), c)
    self.cit = self.adm.get("citizens") or len(self.people)
    self.sites = [s for s in lst(self.map.get("sites")) if isinstance(s, dict)]
    self.note_w_sites()
    self.orders = [x for x in lst(self.o.get("orders")) if isinstance(x, dict)]
    if isinstance(self.o.get("orders"), list):
        self.brew_orders.intersection_update(x.get("id") for x in self.orders)
        self.owned.intersection_update(x.get("id") for x in self.orders)
        on_book = {x.get("id") for x in self.orders}
        self.brew_shots = {k: v for k, v in self.brew_shots.items() if k in on_book}
    self.zones = [z for z in lst(self.o.get("zones")) if isinstance(z, dict)]
    self.free = d(self.st.get("furniture_free"))
    self.placed = {}
    for f in lst(self.o.get("furniture")):
        if isinstance(f, dict):
            self.placed[f.get("kind")] = self.placed.get(f.get("kind"), 0) + 1
    self.surface = self.map.get("surface_z")
    self.record_caravan()
    if isinstance(self.day, (int, float)):
        rec = (self.day, self.st.get("food_edible") or 0, self.st.get("drink") or 0)
        if self.food_hist and self.food_hist[-1][0] == self.day:
            self.food_hist[-1] = rec
        else:
            self.food_hist.append(rec)
    if isinstance(self.day, (int, float)) and isinstance(self.st.get("drink"), (int, float)):
        rec = (self.day, self.st.get("drink") or 0, self.st.get("food_edible") or 0, self.cit or 0,
               bool(self.caravan_settling()))
        if self.rate_hist and self.rate_hist[-1][0] == self.day:
            self.rate_hist[-1] = rec
        else:
            self.rate_hist.append(rec)
    self.f_record()
    if not self.caravan_settling() and isinstance(self.st.get("seeds_by_kind"), dict):
        self.own_seeds = {k: int(d(v).get("n") or 0) for k, v in self.live_seeds_by_kind().items()}
        self.own_food = self.st.get("food_edible")
        self.own_plants = {k: int(d(v).get("n") or 0) for k, v in d(self.st.get("plants_by_kind")).items()}
        self.merchant_plants = None
    elif self.caravan_active and self.merchant_plants is None and isinstance(self.own_plants, dict):
        self.merchant_plants = {k: max(0, int(d(v).get("n") or 0) - self.own_plants.get(k, 0))
                                for k, v in d(self.st.get("plants_by_kind")).items()}
    if isinstance(self.day, int) and self.day != self.stock_day:
        self.stock_day = self.day
        self.stock_hist.append((self.day, self.st.get("drink") or 0, self.st.get("food_edible") or 0,
                                self.st.get("prepared_meals") or 0))
    self.glut_jump = ((self.st.get("plants_brewable") or 0) - self.glut_prev) if self.glut_prev is not None else 0
    self.glut_prev = self.st.get("plants_brewable") or 0
    rot = self.st.get("plants_rotten")
    if not isinstance(rot, (int, float)) or isinstance(rot, bool):
        rot = None
    base = self.rot_prev
    if isinstance(self.day, (int, float)) and rot is not None:
        self.rot_hist = [h for h in self.rot_hist if self.day - h[0] <= ROT_ARM_DAYS and h[0] < self.day]
        if self.rot_hist:
            base = min(h[1] for h in self.rot_hist)
    if not self.rot_seen and rot is not None and base is not None \
            and rot - base >= ROT_ARM_RISE and self.alloc_on():
        self.rot_seen = True
        log("rot_seen", day=self.day, rotten=rot, prev=base, pb=self.st.get("plants_brewable"),
            seeds=self.st.get("seeds"), barrels=self.st.get("barrels_empty"))
    if rot is not None:
        self.rot_prev = rot
        if isinstance(self.day, (int, float)):
            self.rot_hist = [h for h in self.rot_hist if h[0] != self.day] + [(self.day, rot)]
    if d(self.o.get("burrows")).get("civilian_alert") and isinstance(self.day, (int, float)):
        self.alert_seen_day = self.day
    if isinstance(self.cit, int) and not isinstance(self.cit, bool) and self.cit > 0:
        if self.mig_start is None:
            self.mig_start = self.cit
        if self.mig_prev is not None and self.cit - self.mig_prev >= 2:
            self.mig_waves += 1
            log("pop_wave", day=self.day, arrived=self.cit - self.mig_prev, citizens=self.cit,
                waves=self.mig_waves, forecast=self.pop_forecast())
        self.mig_prev = self.cit
    for name, v in d(self.st.get("seeds_by_kind")).items():
        if isinstance(d(v).get("seasons"), list):
            self.kind_seasons[name] = list(d(v)["seasons"])
    for name, v in d(self.st.get("plants_by_kind")).items():
        if isinstance(d(v).get("brewable"), bool):
            self.kind_brew[str(name)] = d(v)["brewable"]
    if isinstance(self.day, (int, float)) and self.day != self.age_day:
        self.age_day = self.day
        self.age_plants()
        if isinstance(self.st.get("logs_usable"), (int, float)):
            fell = any(p.get("job") == "FellTree" for p in self.people)
            self.wood_hist = (self.wood_hist + [(self.day, self.st.get("logs_usable"), fell)])[-60:]
    if isinstance(self.day, (int, float)) and isinstance(self.o.get("dwarves"), list):
        idle = sum(1 for p in self.people if p.get("job") == "idle")
        if self.idle_days and self.idle_days[-1][0] == self.day:
            self.idle_days[-1] = (self.day, idle)
        else:
            self.idle_days = (self.idle_days + [(self.day, idle)])[-2:]
    for w in lst(self.o.get("workshops")):
        if not isinstance(w, dict) or w.get("id") is None:
            continue
        stuck_now = (not w.get("built")) and any(
            isinstance(j, dict) and j.get("job") == "ConstructBuilding" and j.get("suspended")
            for j in lst(w.get("job_details")))
        if stuck_now:
            if self.shop_stuck.get(w["id"]) is None:
                self.shop_stuck[w["id"]] = self.obs_day()
        else:
            self.shop_stuck.pop(w["id"], None)
    self.note_butcher_frames()
    self.record_water()
    self.record_caravan()
    self.record_wildlife(self.wild_stamp())
    self.note_wild_evidence(self.o)
    self.learn_marks(self.o)
    self.note_access(self.o, self.now)
def safe_due(self):
    ho = self.hands_off
    if not isinstance(ho, (int, float)) or isinstance(ho, bool):
        return False
    gaps = [b - a for a, b in zip(self.pass_days, self.pass_days[1:])][-3:]
    return ho <= max([1] + gaps)
def alert_barred(self):
    return self.safe_held
def safe_state(self, why=None):
    if why is None:
        self.safe_held = self.safe_due()
        if not self.safe_held:
            return
        why = "hands_off"
    else:
        self.safe_held = True
    lifted, opened = False, []
    if d(self.o.get("burrows")).get("civilian_alert"):
        r = self.act("safe_alert_off", "civilian_alert", {"on": False}, retry=0.25, limit=10 ** 6)
        if r and r.get("ok"):
            lifted = True
            if self.wild_alert_since is not None:
                self.wild_alert_closed()
            self.alert_since = None
            self.wild_alert_since = None
    by_id = {d(x).get("id"): d(x) for x in lst(d(self.o.get("doors")).get("list"))}
    flood = self.hatch_id if self.breach else None
    for hid in sorted(self.alert_locked, key=str):
        x = by_id.get(hid)
        if hid == flood or (x is not None and not x.get("locked")):
            self.alert_locked.discard(hid)
            continue
        r = self.act("safe_unlock_" + str(hid), "lock_door", {"locked": False, "door_id": hid},
                     retry=0.25, limit=10 ** 6)
        if r and r.get("ok"):
            self.alert_locked.discard(hid)
            opened.append(hid)
    if lifted or opened or self.safe_log_day != self.day:
        self.safe_log_day = self.day
        log("safe_state", day=self.day, why=why, hands_off=self.hands_off, lifted=lifted, unlocked=opened)
def access_free(self, obs):
    obs = d(obs)
    if d(obs.get("burrows")).get("civilian_alert"):
        return False
    return not any(d(x).get("locked") and d(x).get("id") in self.alert_locked
                   for x in lst(d(obs.get("doors")).get("list")))
def access_evidence(self, obs, drink=None):
    obs = d(obs)
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    surface = d(obs.get("map")).get("surface_z", getattr(self, "surface", None))
    if num(surface) and any(c["z"] >= surface for c in self.citizen_spots(obs)):
        return "surface"
    bur = d(obs.get("burrows"))
    shelter = next((d(b) for b in lst(bur.get("list")) if d(b).get("civ_alert_burrow")), None)
    inside = (shelter or {}).get("citizens_inside")
    cit = d(obs.get("administrators")).get("citizens") or len(self.citizen_spots(obs))
    if num(inside) and num(cit) and inside < cit:
        return "outside"
    if num(drink) and num(self.access_drink) and drink < self.access_drink:
        return "drank"
    return None
def note_access(self, obs, tick):
    if not isinstance(tick, (int, float)) or isinstance(tick, bool):
        return
    if self.access_tick is None:
        self.access_tick = tick
    if tick == self.access_look:
        return
    self.access_look = tick
    drink = d(d(obs).get("stocks")).get("drink")
    if self.access_free(obs):
        ev = self.access_evidence(obs, drink)
        if not ev:
            self.access_from = None
        elif self.access_from is None:
            self.access_from = tick
        if ev and self.access_from is not None and tick - self.access_from >= ACCESS_WINDOW_DAYS * DAY \
                and tick > self.access_tick:
            if self.thirst_due(tick):
                log("access_window", day=self.day, since_day=round(self.access_tick / DAY, 1),
                    from_day=round(self.access_from / DAY, 1), evidence=ev)
            self.access_tick = tick
    else:
        self.access_from = None
    if isinstance(drink, (int, float)) and not isinstance(drink, bool):
        self.access_drink = drink
def thirst_due(self, now=None):
    now = self.now if now is None else now
    return self.access_tick is not None and isinstance(now, (int, float)) \
        and now - self.access_tick > ACCESS_CAP_DAYS * DAY
def thirst_signs(self, obs=None):
    obs = d(self.o if obs is None else obs)
    n = sum(1 for p in lst(obs.get("dwarves")) if isinstance(p, dict) and p.get("job") == "DrinkItem")
    n += sum(1 for t in lst(obs.get("recent_cancellations"))
             if re.search(r"cancels (Drink|Eat)\b.*(find path|Forbidden area|inaccessible)", str(t)))
    return n
def wild_stamp(self):
    s = self.obs_day()
    return self.loads if s is None else s
def obs_day(self):
    if isinstance(self.day, (int, float)) and not isinstance(self.day, bool):
        return self.day
    if isinstance(self.now, (int, float)) and not isinstance(self.now, bool):
        return int(self.now) // DAY
    return None
def shop_stale(self, w):
    first = self.shop_stuck.get(w.get("id"))
    cur = self.obs_day()
    return first is not None and cur is not None and cur > first
def note_butcher_frames(self):
    shops = self.o.get("workshops") if isinstance(self.o, dict) else None
    if not isinstance(shops, list):
        return
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    day = self.obs_day()
    alert = bool(d(self.o.get("burrows")).get("civilian_alert"))
    now = set()
    for w in shops:
        if not isinstance(w, dict) or w.get("id") is None or w.get("type") != "Butchers":
            continue
        if w.get("built") is not False:
            self.frame_idle.pop(w["id"], None)
            self.frame_seen.pop(w["id"], None)
            continue
        now.add(w["id"])
        if all(num(w.get(k)) for k in ("x", "y", "z")):
            self.frame_seen[w["id"]] = (w["x"], w["y"], w["z"])
        jobs = [j for j in lst(w.get("job_details")) if isinstance(j, dict) and j.get("job") == "ConstructBuilding"]
        worked = any(j.get("worker_id") not in (None, -1) for j in jobs)
        if worked:
            self.frame_idle.pop(w["id"], None)
        elif day is not None and not alert and self.material() >= 1:
            self.frame_idle.setdefault(w["id"], set()).add(day)
        if len(self.frame_idle.get(w["id"], ())) >= BUTCHER_FRAME_IDLE_DAYS and w["id"] in self.frame_seen:
            self.dead_w_sites.add(self.frame_seen[w["id"]])
    for fid in [k for k in self.frame_seen if k not in now]:
        self.dead_w_sites.add(self.frame_seen.pop(fid))
        self.frame_idle.pop(fid, None)
def butcher_frame_dead(self, w):
    return w.get("type") == "Butchers" and w.get("built") is False \
        and len(self.frame_idle.get(w.get("id"), ())) >= BUTCHER_FRAME_IDLE_DAYS
def butcher_key(self):
    n = len(getattr(self, "dead_w_sites", ()))
    return "ws_Butchers" if not n else "ws_Butchers_%d" % (n + 1)
def butchers_ready(self):
    return any(isinstance(w, dict) and w.get("type") == "Butchers"
               and not (w.get("built") is False and (self.butcher_frame_dead(w) or self.shop_stale(w)))
               for w in lst(self.o.get("workshops")))
def dead_site(self, site):
    x, y, z = site.get("x"), site.get("y"), site.get("z")
    for (wx, wy, wz) in getattr(self, "dead_w_sites", ()):
        if wz == z and isinstance(x, (int, float)) and isinstance(y, (int, float)) \
                and x <= wx < x + (site.get("w") or 1) and y <= wy < y + (site.get("h") or 1):
            return True
    return False
def kind(self, k):
    return [s for s in self.sites if s.get("kind") == k]
def pending(self, recipe):
    return any(x.get("recipe") == recipe and (x.get("left") or 0) > 0 for x in self.orders)
def standing(self, recipe):
    return any(x.get("recipe") == recipe and x.get("repeat") for x in self.orders)
def regular_cook_on_book(self):
    skip = {self.key_order.get(k) for k in ("o_cook_food", "o_winter_cook", "o_cook_end")} - {None}
    mine = self.cook_standing(False)
    if mine is not None and mine.get("id") not in skip:
        return True
    cap = MEAL_CAP
    for x in self.orders:
        if x.get("recipe") != "cook_meal" or not x.get("repeat") or x.get("id") in skip:
            continue
        if self.seed_clause_dead(x):
            continue
        caps = [v for k, t, v in when_sig(x.get("when")) if k == ("FOOD", None) and t == "LessThan"
                and isinstance(v, (int, float))]
        if caps and min(caps) < cap:
            continue
        return True
    return False
def zone(self, word):
    return [z for z in self.zones if word in str(z.get("type")).lower()]
def logs(self):
    return self.st.get("logs_usable", 0) or 0
def material(self):
    return self.logs() + (self.st.get("boulders_usable", 0) or 0)
def undug_rooms(self):
    return [r for r in self.kind("R") if not r.get("designated")]
def dug_rooms(self, role=None):
    return [r for r in self.kind("R") if r.get("dug") and r.get("free", True)
            and (role is None or self.roles.get(r["id"]) == role)]
def water_now(self):
    return (d(self.o.get("water_on_fort_levels")).get("tiles") or 0) > 0
def water_texts(self):
    texts = [str(t).lower() for t in lst(self.o.get("recent_events")) + lst(self.o.get("recent_cancellations"))]
    drowned = any("found dead" in t and "drown" in t for t in texts)
    wet_cancel = any(re.search(r"(cancels|unable to) (dig|carve|detail|channel|mine)\b[^:]*:.*\b(damp|wet|water)",
                               t) for t in texts)
    found_dead = any("found dead" in t for t in texts)
    return drowned, wet_cancel, found_dead
def water_probe_ok(self):
    if self.water_probe_day_no != self.day:
        self.water_probe_day_no, self.water_probes = self.day, 0
    if self.water_probes >= WATER_PROBES_PER_DAY:
        return False
    self.water_probes += 1
    return True
def site_near(self, x, y, z, margin=WATER_SITE_MARGIN):
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (x, y, z)):
        return None
    best, dist = None, 10 ** 9
    for s in self.sites:
        if s.get("z") != z:
            continue
        sx, sy = s.get("x"), s.get("y")
        w, h = s.get("w", 1) or 1, s.get("h", 1) or 1
        dx = max((sx - margin) - x, x - (sx + w + margin - 1), 0)
        dy = max((sy - margin) - y, y - (sy + h + margin - 1), 0)
        near = max(dx, dy)
        if near <= margin and near < dist:
            best, dist = s.get("id"), near
    return best
def water_death_sites(self):
    if not self.water_probe_ok():
        return set()
    try:
        r = self.game.events(since_tick=max(0, self.water_event_tick or self.now - WATER_EVENT_LOOKBACK_DAYS * DAY))
    except Exception as e:
        log("water_events_error", error=repr(e)[:160])
        return set()
    self.water_event_tick = self.now
    hits = set()
    for ev in lst(d(r).get("events")):
        ev = d(ev)
        text = str(ev.get("text") or "").lower()
        if "found dead" not in text:
            continue
        if not (ev.get("type") == "CITIZEN_DEATH" or "drown" in text or self.water_now()):
            continue
        sid = self.site_near(ev.get("x"), ev.get("y"), ev.get("z"))
        if sid is not None:
            hits.add(sid)
    return hits
def count_water(self, res, boxes=None, margin=0, zs=None):
    res = d(res)
    def hit(x, y, z):
        if boxes is None:
            return True
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (x, y, z)):
            return False
        return any((z in zs if zs is not None else z == bz)
                   and bx - margin <= x <= bx + bw - 1 + margin and by - margin <= y <= by + bh - 1 + margin
                   for bx, by, bw, bh, bz in boxes)
    n = 0
    for liq in lst(res.get("liquid")):
        liq = d(liq)
        if not liq.get("magma") and (liq.get("depth") or 0) > 0 and hit(liq.get("x"), liq.get("y"), liq.get("z")):
            n += 1
    x1, y1 = res.get("x1"), res.get("y1")
    for level in lst(res.get("levels")):
        z = d(level).get("z")
        for i, row in enumerate(lst(d(level).get("material"))):
            for j, ch in enumerate(str(row)):
                if ch in WATER_MATERIAL_CHARS and (boxes is None or (isinstance(x1, int) and isinstance(y1, int)
                                                                     and hit(x1 + j, y1 + i, z))):
                    n += 1
    return n
def dig_box(self, site):
    x, y, z = int(site.get("x") or 0), int(site.get("y") or 0), int(site.get("z") or 0)
    w, h = max(1, int(site.get("w") or 1)), max(1, int(site.get("h") or 1))
    if site.get("kind") == "R":
        w, h = max(w, DIG_BOX_R[0]), max(h, DIG_BOX_R[1])
    return x, y, w, h, z
def water_wetness(self, site):
    return self.water_cache.get(site.get("id"))
def water_rank(self, site):
    w = self.water_wetness(site)
    return 1 if w is None else (2 if w > 0 else 0)
def water_measure(self, site, levels=1, force=False, rise=False):
    sid = site.get("id")
    if not force and self.water_wetness(site) is not None:
        return self.water_cache.get(sid)
    bx, by, bw, bh, z = self.dig_box(site)
    margin = RISE_MARGIN if rise else WATER_DIG_MARGIN
    span = max(0, min(int(levels), WET_QUERY_SPAN))
    z_top = min(300, max(0, z + (1 if rise else 0)))
    if isinstance(self.surface, int) and not isinstance(self.surface, bool):
        z_top = max(z, min(z_top, self.surface))
    z2 = max(0, z - span - (1 if rise else 0))
    z2 = max(z2, z_top - WET_QUERY_SPAN)
    n = self.scan_count((bx, by, bw, bh, z), margin, z2, z_top)
    if n is None:
        if not self.water_probe_ok():
            return None if force else self.water_cache.get(sid)
        n = self.probe_count(sid, (bx, by, bw, bh, z), margin, z2, z_top)
        if n is None:
            return None
    if not rise:
        self.water_cache[sid], self.water_cache_day[sid] = n, self.day
    if n > 0:
        self.dig_at_water = (self.dig_at_water + [sid])[-REPORT_KEEP:]
    return n
def probe_count(self, sid, box, margin, z2, z_top):
    bx, by, bw, bh, z = box
    cx, cy = bx + (bw - 1) // 2, by + (bh - 1) // 2
    radius = min(20, max(WATER_QUERY_RADIUS, max(bw, bh) // 2 + margin + 2))
    try:
        r = self.game.query("map", x=min(400, max(0, cx)), y=min(400, max(0, cy)),
                            z=z_top, z2=z2, radius=radius)
    except Exception as e:
        log("water_probe_error", site=sid, error=repr(e)[:160])
        return None
    res = query_result(r)
    if res is None:
        log("water_probe_error", site=sid, day=self.day, z=z_top, z2=z2, error=query_error(r))
        return None
    return self.count_water(res, boxes=[box], margin=margin, zs=set(range(z2, z_top + 1)))
def scan_count(self, box, margin, z_low, z_high):
    day, answers = self.scan
    if day != self.day or not answers:
        return None
    bx, by, bw, bh, _ = box
    need = set(range(z_low, z_high + 1))
    n, seen = 0, set()
    for res in answers:
        x1, x2, y1, y2 = (res.get(k) for k in ("x1", "x2", "y1", "y2"))
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (x1, x2, y1, y2)):
            continue
        if not (x1 <= bx - margin and bx + bw - 1 + margin <= x2 and y1 <= by - margin and by + bh - 1 + margin <= y2):
            continue
        zs = {d(lv).get("z") for lv in lst(res.get("levels"))} & need
        zs -= seen
        if not zs:
            continue
        seen |= zs
        n += self.count_water(res, boxes=[box], margin=margin, zs=zs)
    return n if seen == need else None
def water_ok(self, site):
    sid = site.get("id")
    if sid not in self.water_halts:
        return True
    if self.breach:
        return False
    if self.water_probe_day.get(sid) == self.day:
        return False
    self.water_probe_day[sid] = self.day
    n = self.water_measure(site, levels=1 if site.get("kind") != "S" else 2, force=True,
                           rise=self.rise_watch is not None)
    if n == 0 and not (isinstance(site.get("z"), int) and site.get("z") in self.wet_z):
        del self.water_halts[sid]
        log("water_resume", site=sid, day=self.day)
        return True
    return False
def water_generic_halt(self, cause):
    newly = []
    for s in self.undug_rooms() + self.kind("S"):
        sid = s.get("id")
        if sid not in self.water_halts:
            self.water_halts[sid] = self.day
            newly.append(sid)
    if newly:
        log("water_halt", day=self.day, cause=cause, sites=sorted(newly))
def record_water(self):
    try:
        drowned, wet_cancel, found_dead = self.water_texts()
        causes = []
        if drowned:
            causes.append("drowned_death_text")
        if wet_cancel:
            causes.append("wet_dig_cancel_text")
        if (d(self.o.get("water_on_fort_levels")).get("deep_tiles") or 0) > 0:
            causes.append("deep_indoor_water")
        if causes:
            self.water_generic_halt("+".join(causes))
        if found_dead and (drowned or self.water_now()):
            for sid in sorted(self.water_death_sites()):
                if sid not in self.water_halts:
                    self.water_halts[sid] = self.day
                    log("water_halt", day=self.day, site=sid, cause="death_near_site")
        self.check_breach()
    except Exception as e:
        log("water_record_error", error=repr(e)[:200])
def last_dig_tick(self):
    digs = [t for k, t in self.last.items() if k == "stairs" or k.startswith("dig_")]
    return max(digs) if digs else None
def check_breach(self, rising=False):
    deep = d(self.o.get("water_on_fort_levels")).get("deep_tiles") or 0
    if self.water_base is None:
        self.water_base = deep
        if not rising:
            return
    if self.breach:
        if deep <= self.water_base + BREACH_RELEASE_GAIN and not self.water_now():
            log("flood_recede", day=self.day, deep=deep, base=self.water_base)
            self.breach, self.wet_z, self.rise_watch = None, set(), None
            return
        cause = self.breach.get("cause")
        if cause == "deep_water_gain" and not rising:
            inside = self.fort_water()
            if inside is None or self.fort_dry_day == self.day:
                return
            self.fort_dry_day = self.day
            self.fort_dry_scans = self.fort_dry_scans + 1 if inside == 0 else 0
            if self.fort_dry_scans >= BREACH_CLEAR_SCANS:
                log("flood_outside", day=self.day, deep=deep, base=self.water_base, scans=self.fort_dry_scans)
                self.breach, self.wet_z, self.fort_dry_scans = None, set(), 0
        elif cause == "water_rising_unread" and not rising:
            inside = self.fort_water(shallow=True)
            if inside is None or self.fort_dry_day == self.day:
                return
            self.fort_dry_day = self.day
            if inside > 0:
                self.breach["cause"] = "water_rising_after_dig"
                log("flood_confirmed", day=self.day, inside=inside)
                return
            self.fort_dry_scans += 1
            if self.fort_dry_scans >= BREACH_CLEAR_SCANS:
                log("flood_outside", day=self.day, deep=deep, base=self.water_base, scans=self.fort_dry_scans,
                    to="rise_watch")
                self.breach, self.wet_z, self.fort_dry_scans = None, set(), 0
                self.rise_watch = {"day": self.day, "inside": 0}
        return
    if self.rise_watch is not None and deep <= self.water_base + BREACH_RELEASE_GAIN and not self.water_now():
        log("rise_watch_end", day=self.day, deep=deep, base=self.water_base)
        self.rise_watch = None
    last = self.last_dig_tick()
    dug_recent = last is not None and (self.now - last) <= BREACH_DIG_WINDOW_DAYS * DAY
    cause = None
    if rising:
        rd = self.fort_reading(force=True)
        inside = None if rd is None or not rd["complete"] and not rd["any"] else rd["any"]
        if inside:
            cause = "water_rising_after_dig" if dug_recent else "water_rising_in_fort"
        elif inside is None:
            if dug_recent:
                cause = "water_rising_unread"
        else:
            if self.rise_watch is None:
                log("water_rising_local", day=self.day, dug_recent=dug_recent, deep=deep, base=self.water_base,
                    halted=sorted(str(k) for k in self.water_halts))
            self.rise_watch = {"day": self.day, "inside": 0}
            return
    elif self.rise_watch is not None:
        inside = self.fort_water(shallow=True)
        rd = self.fort_water_memo[1] if self.fort_water_memo[0] == self.day else None
        if not inside and rd is not None and rd.get("any"):
            inside = rd["any"]
        if inside:
            cause = "water_in_fort"
    if cause is None and deep - self.water_base >= BREACH_DEEP_GAIN:
        inside = self.fort_water()
        if inside is not None and inside < BREACH_FORT_MIN:
            if not self.gain_outside:
                log("deep_water_outside", day=self.day, deep=deep, base=self.water_base, inside=inside)
                self.gain_outside = True
            return
        cause = "deep_water_gain"
    if cause is None:
        return
    self.gain_outside, self.fort_dry_scans, self.rise_watch = False, 0, None
    zs = [s.get("z") for s in self.kind("S") if isinstance(s.get("z"), int)]
    self.breach = {"day": self.day, "z": min(zs) if zs else None, "cause": cause}
    log("flood_breach", day=self.day, cause=cause, z=self.breach["z"], deep=deep, base=self.water_base,
        digs_pending=self.o.get("dig_designations_pending"))
def fort_boxes(self):
    out = []
    for s in self.sites:
        if not all(isinstance(s.get(k), int) and not isinstance(s.get(k), bool) for k in ("x", "y", "z")):
            continue
        k = s.get("kind")
        if (k == "R" and s.get("dug")) or k in ("S", "E") \
                or (k == "A" and (not isinstance(self.surface, int) or s["z"] < self.surface)):
            out.append(s)
    return out
def fort_water(self, shallow=False):
    rd = self.fort_reading()
    if rd is None or (shallow and not rd["complete"]):
        return None
    return rd["any"] if shallow else rd["deep"]
def fort_box_list(self):
    out = [(b["x"], b["y"], max(1, b.get("w") or 1), max(1, b.get("h") or 1), b["z"]) for b in self.fort_boxes()]
    bottom = self.stair_bottom() if isinstance(self.surface, int) and not isinstance(self.surface, bool) else None
    for st in self.sites:
        if not all(isinstance(st.get(k), int) and not isinstance(st.get(k), bool) for k in ("x", "y", "z")):
            continue
        zb = self.shafts.get(st.get("id")) if st.get("kind") == "S" else (bottom if st.get("kind") == "E" else None)
        if isinstance(zb, int):
            for zz in range(max(zb, st["z"] - WET_SCAN_LEVELS), st["z"]):
                out.append((st["x"], st["y"], 1, 1, zz))
    dug = {s.get("id") for s in self.sites if s.get("dug")}
    for rid, box in sorted(self.room_box.items(), key=lambda kv: str(kv[0])):
        vals = tuple(box.get(k) for k in ("x", "y", "w", "h", "z"))
        if rid in dug and all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
            out.append(vals)
    return out
def fort_reading(self, force=False):
    if self.fort_water_memo[0] == self.day and not force:
        return self.fort_water_memo[1]
    boxes = self.fort_box_list()
    query = getattr(self.game, "query", None)
    if not boxes or query is None:
        return None
    xs = [b[0] for b in boxes] + [b[0] + b[2] - 1 for b in boxes]
    ys = [b[1] for b in boxes] + [b[1] + b[3] - 1 for b in boxes]
    cx, cy = (min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2
    radius = max(WATER_QUERY_RADIUS, min(20, max(max(xs) - min(xs), max(ys) - min(ys)) // 2 + 2))
    z = max(b[4] for b in boxes)
    z_low = min(b[4] for b in boxes)
    deep, wet, bands, complete, bands_kept = 0, {}, 0, False, False
    while bands < 3:
        if z < z_low:
            complete = True
            break
        if not force and not self.water_probe_ok():
            break
        z2 = max(z_low, z - WET_QUERY_SPAN)
        try:
            r = query("map", x=min(400, max(0, cx)), y=min(400, max(0, cy)), z=min(300, max(0, z)),
                      z2=max(0, z2), radius=radius)
        except Exception as e:
            log("fort_water_error", day=self.day, error=repr(e)[:160])
            break
        res = query_result(r)
        if res is None:
            log("fort_water_error", day=self.day, z=z, z2=z2, error=query_error(r))
            break
        bands += 1
        if self.scan[0] != self.day or not bands_kept:
            self.scan = (self.day, [])
            bands_kept = True
        self.scan[1].append(res)
        for liq in lst(res.get("liquid")):
            liq = d(liq)
            tx, ty, tz = liq.get("x"), liq.get("y"), liq.get("z")
            depth = liq.get("depth") or 0
            if liq.get("magma") or depth < WET_DEPTH_MIN \
                    or not all(isinstance(v, int) and not isinstance(v, bool) for v in (tx, ty, tz)):
                continue
            if any(bz == tz and bx - WET_BOX_MARGIN <= tx <= bx + bw - 1 + WET_BOX_MARGIN
                   and by - WET_BOX_MARGIN <= ty <= by + bh - 1 + WET_BOX_MARGIN for bx, by, bw, bh, bz in boxes):
                if depth >= 4:
                    deep += 1
                if not (isinstance(self.surface, int) and tz >= self.surface):
                    wet[tz] = wet.get(tz, 0) + 1
        z = z2 - 1
    if z < z_low:
        complete = bands > 0
    val = {"deep": deep, "any": sum(wet.values()), "complete": complete, "wet": wet} if bands else None
    self.fort_water_memo = (self.day, val)
    return val
def water_rising_stop(self):
    self.water_rise_tick = self.now
    self.water_generic_halt("water_rising_stop")
    self.check_breach(rising=True)
def flooded_pending(self):
    o = getattr(self, "o", {})
    return bool(self.breach) and bool(o) and (o.get("dig_designations_pending") or 0) > 0
def dry(self, z):
    return z not in self.wet_z
def record_wet_levels(self):
    if self.wet_day == self.day or not isinstance(self.surface, int):
        return
    xs = [s["x"] for s in self.sites if isinstance(s.get("x"), int)]
    ys = [s["y"] for s in self.sites if isinstance(s.get("y"), int)]
    if not xs or not ys:
        return
    self.wet_day = self.day
    boxes = self.fort_box_list()
    cx, cy = (min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2
    radius = max(WATER_QUERY_RADIUS, min(20, max(max(xs) - min(xs), max(ys) - min(ys)) // 2 + 1))
    z_stop = max(0, self.surface - WET_SCAN_LEVELS)
    wet, bands = set(), 0
    z = min(300, max(0, self.surface))
    while z >= z_stop and bands < 3:
        if not self.water_probe_ok():
            break
        z2 = max(z_stop, z - WET_QUERY_SPAN)
        try:
            r = self.game.query("map", x=min(400, max(0, cx)), y=min(400, max(0, cy)),
                                z=z, z2=z2, radius=radius)
        except Exception as e:
            log("water_probe_error", day=self.day, error=repr(e)[:160])
            break
        res = query_result(r)
        if res is None:
            log("water_probe_error", day=self.day, z=z, z2=z2, error=query_error(r))
            break
        bands += 1
        for liq in lst(res.get("liquid")):
            liq = d(liq)
            tx, ty, zz = liq.get("x"), liq.get("y"), liq.get("z")
            if (not liq.get("magma") and (liq.get("depth") or 0) >= WET_DEPTH_MIN
                    and all(isinstance(v, int) and not isinstance(v, bool) for v in (tx, ty, zz))
                    and zz < self.surface
                    and any(bz == zz and bx - WET_BOX_MARGIN <= tx <= bx + bw - 1 + WET_BOX_MARGIN
                            and by - WET_BOX_MARGIN <= ty <= by + bh - 1 + WET_BOX_MARGIN
                            for bx, by, bw, bh, bz in boxes)):
                wet.add(zz)
        z = z2 - 1
    if bands:
        self.wet_z = wet
        if wet:
            log("wet_levels", day=self.day, levels=sorted(wet, reverse=True))
def contain_flood(self):
    self.record_wet_levels()
    doors = d(self.o.get("doors"))
    hatches = [d(x) for x in lst(doors.get("list")) if d(x).get("kind") == "hatch"]
    stair = next(iter(self.kind("E")), None)
    hatch = next((x for x in hatches if self.hatch_id is not None and x.get("id") == self.hatch_id), None)
    if hatch is None and stair is not None:
        hatch = next((x for x in hatches if x.get("x") == stair.get("x") and x.get("y") == stair.get("y")
                      and x.get("z") == stair.get("z")), None)
    if hatch is not None or stair is not None:
        if hatch is not None:
            self.hatch_id = hatch.get("id")
            if hatch.get("locked") and self.hatch_id not in self.alert_locked:
                self.flood_locked.add(self.hatch_id)
            if not hatch.get("locked") and self.flood_lock_wanted(hatch):
                r = self.act("flood_lock", "lock_door", {"locked": True, "door_id": self.hatch_id}, retry=1, limit=8)
                if r and r.get("ok"):
                    self.flood_locked.add(self.hatch_id)
                    log("flood_lock", day=self.day, door=self.hatch_id)
        else:
            free = doors.get("hatch_cover_items_free") or 0
            if free <= 0:
                if not self.pending("make_hatch_cover"):
                    self.act("flood_hatch_order", "add_order", {"recipe": "make_hatch_cover", "amount": 2},
                             retry=1, limit=30)
            else:
                r = self.act("flood_hatch", "build_door", {"kind": "hatch", "site": stair["id"]}, retry=2, limit=8)
                hid = d(d(r).get("result")).get("id") if r else None
                if hid is not None:
                    self.hatch_id = hid
    else:
        wall = next(iter(self.kind("D")), None)
        if wall is not None:
            self.act("flood_wall", "build_wall", {"site": wall["id"]}, retry=2, limit=8)
def season(self):
    return self.game_doy() // SEASON_DAYS
def winter(self):
    return self.season() == 3
def record_caravan(self):
    if not hasattr(self.game, "events") or not isinstance(self.day, (int, float)):
        return
    if self.caravan_probe_day == self.day:
        return
    self.caravan_probe_day = self.day
    since = self.caravan_cursor if self.caravan_cursor is not None else max(0, self.now - 8 * DAY)
    try:
        page = self.game.events(since_tick=int(since))
    except Exception as e:
        log("caravan_events_error", error=repr(e)[:160])
        return
    self.caravan_cursor = self.now
    last_arrive = last_leave = None
    for ev in lst(d(page).get("events")):
        ev = d(ev)
        t = str(ev.get("type") or "")
        ev_tick = ev.get("tick") or 0
        if ev_tick > self.now:
            continue
        ev_day = (self.day + (ev_tick - self.now) // DAY) if isinstance(self.now, (int, float)) \
            else ev_tick // DAY
        if t in CARAVAN_ARRIVALS:
            if last_arrive is None or ev_day >= last_arrive:
                last_arrive = ev_day
        elif t == CARAVAN_EMBARK:
            if last_leave is None or ev_day >= last_leave:
                last_leave = ev_day
        if t == "CANCEL_JOB" and "Dig" in str(ev.get("text") or "") and "Dangerous terrain" in str(ev.get("text")) \
                and all(isinstance(ev.get(k), int) for k in ("x", "y", "z")):
            self.dig_unsafe.add((ev["x"], ev["y"], ev["z"]))
        if t in LIAISON_EVENTS and not self.liaison_seen:
            self.liaison_seen = True
            log("liaison_seen", day=self.day, type=t)
    if last_arrive is not None:
        self.caravan_arrival_day = last_arrive
    if last_leave is not None:
        self.caravan_leave_day = last_leave
    if last_arrive is not None or last_leave is not None:
        self.caravan_last_day = max(self.caravan_last_day or 0, last_arrive or 0, last_leave or 0)
    active = False
    arr, lea = self.caravan_arrival_day, self.caravan_leave_day
    if arr is not None:
        if lea is None or lea < arr:
            active = (self.day - arr) <= CARAVAN_MAX_DAYS
        else:
            active = (self.day - lea) <= CARAVAN_GRACE_DAYS
    if active != self.caravan_active:
        log("caravan", on=active, day=self.day, arrival=self.caravan_arrival_day, leave=self.caravan_leave_day)
        self.caravan_active = active
def caravan_settling(self):
    if self.caravan_active:
        return True
    return self.caravan_last_day is not None and (self.day or 0) - self.caravan_last_day < CARAVAN_SETTLE_DAYS
def leg_slopes(self):
    for hist, di, fo in ((self.stock_hist, 1, 2), (self.food_hist, 2, 1)):
        if len(hist) >= 3:
            return (ols_slope([(p[0], p[di]) for p in hist]), ols_slope([(p[0], p[fo]) for p in hist]))
    return None, None
def drink_secure(self, drink_slope):
    if drink_slope is None or drink_slope >= 0:
        return True
    return (self.st.get("drink") or 0) / -drink_slope >= SLOPE_HORIZON
def food_min_leg(self):
    drink, food = self.leg_slopes()
    if food is None or food >= 0:
        return False
    return self.drink_secure(drink)
def f_keeper_yield(self):
    if not self.alloc_on():
        return False
    left = self.days_to_end()
    if left is None or left > self.f_len() + FYIELD_LEAD:
        return False
    drink = self.st.get("drink") or 0
    cit = max(1, self.cit or 0)
    today = self.day if isinstance(self.day, (int, float)) else (self.days or 0) - left
    pts = [p for p in self.rate_hist if p[0] >= today - self.f_len() and not p[4]]
    use = self.fyield_drain(pts)
    if use is None:
        use = self.use_rate("drink", ALLOC_DRINK_PER_CIT_DAY) * cit
    if use <= 0 or drink <= 0:
        return False
    t_drink = (drink - use * left) / use
    if self.f_yield_food_t is not None:
        if t_drink < min(SLOPE_HORIZON, self.f_yield_food_t):
            log("f_keeper_yield_off", day=self.day, drink=drink, t_drink=round(t_drink),
                t_food=round(self.f_yield_food_t))
            self.f_yield_food_t = None
            return False
        return True
    if len(pts) >= 3:
        food_sl = ols_slope([(p[0], p[2]) for p in pts])
    else:
        food_sl = self.leg_slopes()[1]
        if food_sl is None:
            return False
    food = self.st.get("food_edible") or 0
    t_food = food / -food_sl if food_sl < 0 else float("inf")
    if t_food != float("inf") and t_drink >= FYIELD_MARGIN * min(SLOPE_HORIZON, t_food):
        self.f_yield_food_t = min(SLOPE_HORIZON, t_food)
        log("f_keeper_yield_on", day=self.day, drink=drink, food=food, drain=round(use, 3),
            t_drink=round(t_drink), t_food=None if t_food == float("inf") else round(t_food))
        return True
    return False
def f_lift_level(self):
    if not self.alloc_on():
        return None
    left = self.days_to_end()
    if left is None or left < 1 or left > self.f_len() + FYIELD_LEAD:
        return None
    if self.hold_armed and not self.food_lean():
        return None
    if self.f_lift_base is None:
        self.f_lift_base = max(1, int(self.st.get("drink") or 0))
    if self.f_yield_food_t is not None:
        return None
    today = self.day if isinstance(self.day, (int, float)) else (self.days or 0) - left
    a = today - (self.f_len() - left) - 1
    pts = [p for p in self.rate_hist if p[0] >= a and not p[4]]
    level = self.f_lift_base
    food = self.st.get("food_edible") or 0
    if self.hold_on_book("o_brew_flift") or self.hold_on_book("o_brew_flift_mid"):
        if len(pts) < 3 or pts[-1][0] - pts[0][0] < FLIFT_CUT_SPAN:
            return level
        food_sl = ols_slope([(p[0], p[2]) for p in pts])
        return None if food_sl < 0 and food / -food_sl < SLOPE_HORIZON else level
    if len(pts) < 3 or pts[-1][0] - pts[0][0] < 3:
        pts = [p for p in self.rate_hist if p[0] >= today - self.f_len() and not p[4]]
    if len(pts) < 3 or pts[-1][0] - pts[0][0] < 3:
        return None
    food_sl = ols_slope([(p[0], p[2]) for p in pts])
    drain = self.fyield_drain(pts) or 0.0
    cost = drain / BREW_DRINKS
    drink = self.st.get("drink") or 0
    t_drink = max(0.0, drink - drain * left) / drain if drain > 0 else float("inf")
    if t_drink >= FYIELD_MARGIN * SLOPE_HORIZON:
        return None
    if food_sl - cost >= 0:
        return level
    food_end = food + (food_sl - cost) * left
    t_food = max(0.0, food_end) / (cost - food_sl)
    return level if t_drink < min(SLOPE_HORIZON, t_food) else None
def f_drink_lift(self):
    left = self.days_to_end()
    if left is None or left < 1:
        return
    level = self.f_lift_level()
    f = self.f_len()
    want = {"o_brew_flift": level, "o_brew_flift_mid": None}
    if level is not None and f - left >= f / 2.0 - HOLD_MID_TOL:
        want["o_brew_flift_mid"] = level + 2 * LEAN_BREW_AMOUNT * BREW_DRINKS
    have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
    for key, lvl in want.items():
        on_book = self.hold_on_book(key)
        if lvl is None:
            if on_book and level is None:
                r = self.act(key + "_cut", "cancel_order", {"order_id": self.key_order.get(key)}, retry=2, limit=4)
                if r is not None:
                    log("f_drink_lift", day=self.day, order=key, on=False, drink=self.st.get("drink"),
                        food=self.st.get("food_edible"), ok=r.get("ok"))
            continue
        if on_book or self.caravan_active or "Still" not in have:
            continue
        r = self.act(key, "add_order", {"recipe": "brew_drink", "amount": LEAN_BREW_AMOUNT, "repeat": "daily",
                                        "when": [{"stock": "drink", "below": int(lvl)},
                                                 {"stock": "plants_brewable", "at_least": 1},
                                                 {"stock": "barrels_empty", "at_least": 1}]},
                     retry=2, limit=6)
        if r is not None:
            log("f_drink_lift", day=self.day, order=key, on=True, below=int(lvl), drink=self.st.get("drink"),
                food=self.st.get("food_edible"), pb=self.st.get("plants_brewable"), ok=r.get("ok"))
@staticmethod
def fyield_drain(pts):
    if len(pts) < 3 or pts[-1][0] - pts[0][0] < 3:
        return None
    span = pts[-1][0] - pts[0][0]
    drops = sum(max(0, a[1] - b[1]) for a, b in zip(pts, pts[1:]))
    net = -ols_slope([(p[0], p[1]) for p in pts])
    drain = max(net, drops / span)
    return drain if drain > 0 else None
def alloc_on(self):
    return (self.days or 0) >= 180 and self.hands_off is None
def measured_rate(self, leg):
    i = 1 if leg == "drink" else 2
    drop = cit_days = days = 0.0
    pairs = 0
    h = list(self.rate_hist)
    for a, b in zip(h, h[1:]):
        dt = b[0] - a[0]
        if dt <= 0 or a[4] or b[4] or b[i] >= a[i]:
            continue
        c = max(1, (a[3] + b[3]) / 2)
        drop += a[i] - b[i]
        cit_days += c * dt
        days += dt
        pairs += 1
    if pairs < RATE_MIN_PAIRS or days < RATE_MIN_DAYS or cit_days <= 0:
        return None
    lo, hi = RATE_CLAMP[leg]
    return min(hi, max(lo, drop / cit_days))
def use_rate(self, leg, prior):
    m = self.measured_rate(leg)
    return prior if m is None else m
def legs_run_out(self):
    if len(self.stock_hist) < SLOPE_MIN_PTS or self.caravan_settling():
        return False, False
    left = self.days_to_end()
    if left is None:
        return False, False
    out = []
    for i in (1, 2):
        sl = ols_slope([(p[0], p[i]) for p in self.stock_hist])
        out.append(sl < 0 and self.stock_hist[-1][i] / -sl < left)
    return tuple(out)
def leg_days(self):
    cit = max(1, self.cit or 0)
    return ((self.st.get("drink") or 0) / (self.use_rate("drink", ALLOC_DRINK_PER_CIT_DAY) * cit),
            (self.st.get("food_edible") or 0) / (self.use_rate("food", ALLOC_FOOD_PER_CIT_DAY) * cit))
def days_to_end(self):
    if self.days_left is not None:
        return self.days_left
    if not isinstance(self.day, (int, float)):
        return None
    return max(0, (self.days or 0) - self.day)
def last_stretch(self):
    left = self.days_to_end()
    return self.alloc_on() and left is not None and left <= LAST_STRETCH_DAYS
def reserve_build(self):
    left = self.days_to_end()
    return (self.alloc_on() and left is not None
            and LAST_STRETCH_DAYS < left <= LAST_STRETCH_DAYS + RESERVE_BUILD_DAYS)
def plant_reserve(self):
    return max(COOK_PLANTS_RESERVE, PLANT_RESERVE_PER_CIT * (self.cit or 0), self.f_need())
def f_need(self):
    return math.ceil(HOLD_COVER * self.use_rate("drink", DRINK_PER_CIT_DAY) * max(1, self.cit or 0)
                     * self.f_len() / 5)
def plant_plan(self):
    dd, fd = self.leg_days()
    sides = self.allocation()
    lean = self.food_lean()
    hold = self.hold_active()
    dout, fout = self.legs_run_out()
    left = self.days_to_end()
    plan = {
        "sides": sides, "lean": lean, "hold": hold, "last": self.last_stretch(), "build": self.reserve_build(),
        "floor": self.plant_floor(),
        "rot_keep": self.rot_keep() if self.rot_seen or self.loose_stuck() else ROT_KEEP,
        "f_need": self.f_need(), "reserve": self.plant_reserve(), "run_out": (dout, fout),
        "food_first": self.food_min_leg(),
        "in_f": left is not None and left <= self.f_len(),
        "brew_ok": ("brew" in sides) and not lean,
        "drink_days": round(dd), "food_days": round(fd),
    }
    key = tuple((k, str(v)) for k, v in plan.items() if k not in ("drink_days", "food_days"))
    if key != self.plan_key:
        self.plan_key = key
        log("plant_plan", day=self.day, **{k: (sorted(v) if isinstance(v, frozenset) else v)
                                           for k, v in plan.items()})
    return plan
def plant_floor(self):
    if self.hold_active():
        return max(self.base_plant_floor(), self.hold_reserve())
    return self.base_plant_floor()
def base_plant_floor(self):
    if self.last_stretch():
        return 2
    if self.reserve_build():
        return self.plant_reserve()
    return COOK_PLANTS_RESERVE
def hold_floor(self):
    return self.plant_reserve() + ALLOC_HOLD_MARGIN
def allocation(self):
    both = frozenset(("brew", "cook"))
    if not self.alloc_on():
        return both
    if self.food_lean():
        want = frozenset(("cook",))
        if self.alloc != want:
            dd, fd = self.leg_days()
            log("alloc", day=self.day, sides=sorted(want), drink_days=round(dd), food_days=round(fd), lean=True)
            self.alloc, self.alloc_day = want, self.day
        return self.alloc
    last = self.last_stretch()
    if last:
        want = both
    else:
        dd, fd = self.leg_days()
        dout, fout = self.legs_run_out()
        want = set()
        if dd < ALLOC_SHORT_DAYS or dd < ALLOC_AHEAD * fd or dout:
            want.add("brew")
        if fd < ALLOC_SHORT_DAYS or fd < ALLOC_AHEAD * dd or fout:
            want.add("cook")
        want = frozenset(want) or both
    if self.alloc is None:
        self.alloc, self.alloc_day = want, self.day
        log("alloc", day=self.day, sides=sorted(want))
    elif want != self.alloc and (last or not self.caravan_active):
        day = self.day if isinstance(self.day, (int, float)) else 0
        if last or self.alloc_day is None or day - self.alloc_day >= ALLOC_DWELL_DAYS:
            dd, fd = self.leg_days()
            log("alloc", day=self.day, sides=sorted(want), drink_days=round(dd), food_days=round(fd))
            self.alloc, self.alloc_day = want, day
    return self.alloc
def food_lean(self):
    if not self.alloc_on():
        return False
    left = self.days_to_end()
    if left is None or left > LEAN_DAYS:
        return False
    dd, fd = self.leg_days()
    drink_out = self.legs_run_out()[0]
    if self.lean_drink is not None and drink_out:
        log("food_lean", day=self.day, on=False, drink=self.st.get("drink"), food=self.st.get("food_edible"),
            reason="drink_runs_out")
        self.lean_drink = None
        return False
    if self.lean_drink is None:
        if self.caravan_settling() or dd < LEAN_AHEAD * fd or drink_out:
            return False
        self.lean_drink = max(1, int(self.st.get("drink") or 0))
        log("food_lean", day=self.day, on=True, keep=self.lean_drink, drink_days=round(dd), food_days=round(fd),
            food=self.st.get("food_edible"), pb=self.st.get("plants_brewable"))
        return True
    if dd < LEAN_EXIT * fd:
        log("food_lean", day=self.day, on=False, drink=self.st.get("drink"), food=self.st.get("food_edible"))
        self.lean_drink = None
        return False
    return True
def lean_supply(self):
    if not self.food_lean():
        return
    keep, level = self.key_order.get("o_brew"), self.lean_drink
    end = self.key_order.get("o_brew_end")
    lift = (self.key_order.get("o_brew_flift"), self.key_order.get("o_brew_flift_mid"))
    for x in self.orders:
        oid = x.get("id")
        if x.get("recipe") != "brew_drink" or oid is None or oid in (keep, end) + lift \
                or oid in self.recycle_brews or oid in self.stall_brews:
            continue
        if not x.get("repeat") and (x.get("left") or 0) <= 0:
            continue
        if x.get("repeat") and any(k[0] == "DRINK" and t == "LessThan" and isinstance(v, (int, float))
                                   and v <= level for k, t, v in when_sig(x.get("when"))):
            continue
        r = self.act("lean_cancel_%s" % oid, "cancel_order", {"order_id": oid}, retry=2, limit=3)
        if r is not None:
            log("lean_cancel", day=self.day, order=oid, repeat=bool(x.get("repeat")), when=x.get("when"))
            for k, v in list(self.key_order.items()):
                if v == oid:
                    self.done.discard(k)
def f_len(self):
    return min(28, max(7, int(self.days or 0) // 4))
def game_doy(self):
    v = d(d(getattr(self, "o", None)).get("date")).get("day_of_year")
    if isinstance(v, int) and not isinstance(v, bool):
        return v % YEAR_DAYS
    return int(self.day or 0) % YEAR_DAYS
def calendar_day(self, doy, fallback):
    v = d(d(getattr(self, "o", None)).get("date")).get("day_of_year")
    if not isinstance(v, int) or isinstance(v, bool) or not isinstance(self.day, (int, float)):
        return fallback
    start = (v - int(self.day)) % YEAR_DAYS
    return (doy - start) % YEAR_DAYS
def fallow_closed(self):
    plots = [d(p) for p in lst(self.o.get("farm_plots")) if isinstance(p, dict)]
    if not plots or any("crop_this_season" not in p for p in plots):
        return False
    if any(str(p.get("crop_this_season") or "none").lower() != "none" for p in plots):
        return False
    if (self.st.get("seeds") or 0) <= 0:
        return False
    left = self.days_to_end()
    to_turn = SEASON_DAYS - self.game_doy() % SEASON_DAYS
    return left is not None and left <= to_turn
def harvest_closed(self):
    left = self.days_to_end()
    if left is None or not d(self.st.get("seeds_by_kind")):
        return False
    kinds = []
    for v in self.live_seeds_by_kind().values():
        v = d(v)
        if (v.get("n") or 0) <= 0:
            continue
        seasons = v.get("seasons")
        if not isinstance(seasons, list):
            return False
        kinds.append(set(seasons))
    doy = self.game_doy()
    name = lambda t: SEASON_NAMES[((doy + t) % YEAR_DAYS) // SEASON_DAYS]
    for t in range(0, max(0, left - HOLD_GROW_DAYS) + 1):
        a, b = name(t), name(t + HOLD_GROW_DAYS)
        if any(a in k and b in k for k in kinds):
            return self.fallow_closed()
    return True
def hold_reserve(self):
    if self.my1_plan():
        return self.my1_hold_reserve()
    need = HOLD_COVER * self.use_rate("drink", DRINK_PER_CIT_DAY) * max(1, self.cit or 0) * self.f_len() / 5
    return max(HOLD_MIN, 2 + math.ceil(need))
def hold_active(self):
    left = self.days_to_end()
    if not self.alloc_on() or left is None or left < 1:
        return False
    if not self.hold_armed and left <= self.f_len():
        return False
    if not self.hold_armed:
        if not self.harvest_closed():
            self.hold_seen_day = None
            return False
        day = self.day if isinstance(self.day, (int, float)) else 0
        if self.hold_seen_day is None:
            self.hold_seen_day = day
        if day - self.hold_seen_day < HOLD_CONFIRM_DAYS:
            return False
    rate = self.f_drink_rate() if self.my1_plan() else \
        self.use_rate("drink", DRINK_PER_CIT_DAY) * max(1, self.cit or 0)
    need = rate * max(0, left - self.f_len())
    if (self.st.get("drink") or 0) < 0.5 * need:
        return False
    if not self.hold_armed:
        self.hold_armed = True
        log("harvest_hold", day=self.day, doy=self.game_doy(), reserve=self.hold_reserve(),
            pb=self.st.get("plants_brewable"), drink=self.st.get("drink"))
    return True
def hold_cook(self):
    if not self.hold_active():
        return False
    dd, fd = self.leg_days()
    return fd >= dd
def hold_drink_rate(self):
    return self.use_rate("drink", DRINK_PER_CIT_DAY) * max(1, self.cit or 0)
def hold_on_book(self, key):
    oid = self.key_order.get(key)
    return oid is not None and any(x.get("id") == oid for x in self.orders)
def hold_standing(self, key, below, floor=1):
    floor = max(1, int(floor))
    if self.hold_on_book(key):
        oid = self.key_order.get(key)
        x = next((o for o in self.orders if o.get("id") == oid), {})
        have = [v for k, t, v in when_sig(x.get("when")) if k == ("PLANT", "DRINK_MAT") and t == "AtLeast"]
        if not (have and have[0] != floor and not (x.get("jobs_in_progress") or 0) and self.may(key + "_cut", 2)):
            return
        r = self.act(key + "_cut", "cancel_order", {"order_id": oid}, retry=2, limit=8)
        self.done.discard(key)
        if not (r and r.get("ok")):
            return
        self.last.pop(key, None)
    self.act(key, "add_order", {"recipe": "brew_drink", "amount": 1, "repeat": "daily", "when": [
        {"stock": "drink", "below": int(below)}, {"stock": "plants_brewable", "at_least": floor},
        {"stock": "barrels_empty", "at_least": 1}]}, retry=2, limit=6)
def hold_supply(self):
    if not self.hold_armed or not self.alloc_on():
        return
    left = self.days_to_end()
    if left is None or left < 1:
        return
    have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
    if "Still" not in have:
        return
    f = self.f_len()
    rate = self.hold_drink_rate()
    drink = self.st.get("drink") or 0
    lean = self.food_lean()
    if self.my1_plan():
        self.my1_hold_supply(left, f, lean)
        self.hold_standing("o_brew_dry", max(5, math.ceil(HOLD_DRY_DAYS * rate)), self.f_dry_floor or 1)
        return
    self.hold_standing("o_brew_dry", max(5, math.ceil(HOLD_DRY_DAYS * rate)))
    mid = self.hold_mid_plan()
    if mid is not None and self.hold_on_book("o_brew_pre") and self.may("o_brew_pre_cut", 4):
        self.act("o_brew_pre_cut", "cancel_order", {"order_id": self.key_order.get("o_brew_pre")}, retry=2,
                 limit=4)
    if f < left <= f + HOLD_PREP_DAYS and not lean and mid is None and not self.hold_on_book("o_brew_pre"):
        want = drink - rate * (left - f)
        if want > HOLD_DRY_DAYS * rate:
            self.hold_standing("o_brew_pre", math.ceil(want))
    cookable = any(d(v).get("brewable") and d(v).get("cookable") for v in d(self.st.get("plants_by_kind")).values())
    food_stays = cookable and self.food_min_leg()
    if mid is not None and left <= f + HOLD_PREP_DAYS and not lean and not food_stays:
        self.hold_mid(mid, f, left, drink)
    elif left <= f and not lean and not food_stays:
        self.hold_standing("o_brew_f", max(600, 30 * (self.cit or 0)))
    if left > f and self.hold_active():
        reserve = self.hold_reserve()
        for x in self.orders:
            if x.get("recipe") != "brew_drink" or x.get("id") in self.owned or x.get("id") is None:
                continue
            if any(k == ("PLANT", "DRINK_MAT") and t == "AtLeast" and isinstance(v, (int, float))
                   and v >= reserve for k, t, v in when_sig(x.get("when"))):
                continue
            self.act("hold_cancel_%s" % x.get("id"), "cancel_order", {"order_id": x.get("id")}, retry=2, limit=3)
            log("hold_cancel", day=self.day, order=x.get("id"), when=x.get("when"))
def my1_hold_supply(self, left, f, lean):
    if self.hold_on_book("o_brew_pre") and self.may("o_brew_pre_cut", 4):
        self.act("o_brew_pre_cut", "cancel_order", {"order_id": self.key_order.get("o_brew_pre")}, retry=2,
                 limit=4)
    cookable = any(d(v).get("brewable") and d(v).get("cookable") for v in d(self.st.get("plants_by_kind")).values())
    food_stays = cookable and self.food_min_leg()
    if left <= f + HOLD_PREP_DAYS and not food_stays:
        self.f_plan_brew()
    else:
        self.f_dry_floor = None
    if self.hold_active():
        reserve = self.hold_reserve()
        plan_ids = {self.key_order.get(k) for k in F_PLAN_KEYS} | set(self.recycle_brews)
        for x in self.orders:
            if x.get("recipe") != "brew_drink" or x.get("id") is None or x.get("id") in plan_ids:
                continue
            if x.get("id") in self.owned and (x.get("jobs_in_progress") or 0) and not x.get("repeat") \
                    and (x.get("left") or 0) <= 1:
                continue
            if x.get("repeat") and self.leaves_reserve(x.get("total") or x.get("left"), x.get("when"), True,
                                                       reserve):
                continue
            if not x.get("repeat") and (x.get("left") or 0) <= 0:
                continue
            if not x.get("repeat") and self.pb_free() - self.plan_queued() >= reserve:
                continue
            self.act("hold_cancel_%s" % x.get("id"), "cancel_order", {"order_id": x.get("id")}, retry=2, limit=3)
            log("hold_cancel", day=self.day, order=x.get("id"), when=x.get("when"))
def leaves_reserve(self, amount, when, repeat, reserve):
    a = amount if isinstance(amount, int) and not isinstance(amount, bool) and amount >= 1 else 1
    if repeat:
        floors = [v for k, t, v in when_sig(when) if k == ("PLANT", "DRINK_MAT") and t == "AtLeast"
                  and isinstance(v, (int, float)) and not isinstance(v, bool)]
        return bool(floors) and max(floors) >= reserve + a
    return a <= self.pb_free() - self.plan_queued() - reserve
def hold_proj_rate(self):
    if isinstance(self.day, (int, float)):
        pts = [(p[0], p[1]) for p in self.stock_hist if self.day - p[0] <= HOLD_RATE_DAYS]
        if len(pts) >= 3 and pts[-1][0] - pts[0][0] >= 7:
            net = -ols_slope(pts)
            if net > 0:
                return net
    return self.hold_drink_rate()
def hold_mid_plan(self):
    if not self.hold_armed or not self.alloc_on():
        return None
    left, f = self.days_to_end(), self.f_len()
    n = self.pb_free()
    if left is None or f < 2 or left > f + HOLD_PREP_DAYS:
        return None
    if self.hold_mode != "mid" and n >= 1 and (self.hold_mode is None or left > f):
        p0 = max(HOLD_F_LEAD, int(math.ceil(f - left)))
        gain = sum(6.0 * BREW_DRINKS * p * (f - p) / f ** 3 for p in range(p0, min(f, p0 + n)))
        rate = self.hold_proj_rate()
        mode = "mid" if gain < rate else "daily"
        if mode != self.hold_mode:
            log("hold_mode", day=self.day, mode=mode, held=n, gain=round(gain, 2), rate=round(rate, 2),
                left=left)
        self.hold_mode = mode
    return n if self.hold_mode == "mid" and n >= 1 else None
def hold_mid(self, n, f, left, drink):
    p = f - left
    rate = self.hold_proj_rate()
    if p >= f / 2.0 - HOLD_MID_TOL:
        amount = min(30, self.pb_free() - self.brew_planned())
        if amount >= 1 and not self.own_pending("o_brew_midshot"):
            r = self.act("o_brew_midshot", "add_order", {"recipe": "brew_drink", "amount": amount}, retry=1,
                         limit=4)
            if r is not None:
                log("hold_midshot", day=self.day, amount=amount, held=n, into_f=p, drink=drink, ok=r.get("ok"))
        return
    if self.hold_on_book("o_brew_mid"):
        return
    below = drink - rate * (f / 2.0 - p)
    if below <= HOLD_DRY_DAYS * rate:
        return
    r = self.act("o_brew_mid", "add_order", {"recipe": "brew_drink", "amount": min(30, n), "repeat": "daily",
                                             "when": [{"stock": "drink", "below": int(math.ceil(below))},
                                                      {"stock": "plants_brewable", "at_least": 1},
                                                      {"stock": "barrels_empty", "at_least": 1}]},
                 retry=2, limit=6)
    if r is not None:
        log("hold_mid", day=self.day, amount=min(30, n), below=int(math.ceil(below)), rate=round(rate, 2),
            into_f=p, drink=drink, ok=r.get("ok"))
def my1_plan(self):
    return self.alloc_on() and (self.days or 0) < 336
def plan_queued(self):
    n = 0
    for x in self.orders:
        if x.get("recipe") != "brew_drink":
            continue
        left = x.get("left") if isinstance(x.get("left"), (int, float)) else 0
        if not x.get("repeat"):
            n += max(0, left)
        elif x.get("active") is True or (x.get("jobs_in_progress") or 0) > 0:
            n += max(0, left)
    return min(n, self.st.get("plants_brewable") or 0)
def f_record(self):
    if not isinstance(self.day, (int, float)) or not isinstance(self.st.get("drink"), (int, float)):
        return
    if self.day < (self.days or 0) - self.f_len() - F_REC_LEAD:
        return
    rec = (self.day, self.st.get("drink") or 0, self.st.get("food_edible") or 0)
    if self.f_rec and self.f_rec[-1][0] == self.day:
        self.f_rec[-1] = rec
    elif not self.f_rec or self.f_rec[-1][0] < self.day:
        self.f_rec.append(rec)
def f_drink_rate(self, prior_only=False):
    pop = max(self.cit or 0, self.pop_forecast() or 0)
    rate = DRINK_PER_CIT_DAY * max(1, pop)
    if not prior_only and isinstance(self.day, (int, float)) and not self.caravan_settling():
        pts = [(p[0], p[1]) for p in self.rate_hist if self.day - p[0] <= HOLD_RATE_DAYS and not p[4]]
        if self.caravan_arrival_day is not None:
            hist = [(p[0], p[1]) for p in self.rate_hist if self.day - p[0] <= HOLD_RATE_DAYS]
            for i in range(len(hist) - 1, 0, -1):
                gap = hist[i][0] - hist[i - 1][0]
                if hist[i - 1][1] - hist[i][1] > CARAVAN_DROP_MIN + CARAVAN_DROP_RATE * rate * max(1, gap):
                    pts = [p for p in pts if p[0] >= hist[i][0]]
                    break
        if len(pts) >= 3 and pts[-1][0] - pts[0][0] >= 7:
            rate = max(rate, -ols_slope(pts))
    return rate
def f_project(self, idx, rate, adds=(), dry=None, dry_until=None):
    H = int(self.days or 0)
    A = H - self.f_len()
    now = int(self.day) if isinstance(self.day, (int, float)) else 0
    cur = (self.st.get("drink") if idx == 1 else self.st.get("food_edible")) or 0
    rec = [(r[0], r[idx]) for r in self.f_rec if r[0] <= now]
    def known(x):
        if not rec:
            return cur
        if x <= rec[0][0]:
            return rec[0][1]
        for (d0, v0), (d1, v1) in zip(rec, rec[1:]):
            if d0 <= x <= d1:
                return v0 + (v1 - v0) * (x - d0) / float(d1 - d0) if d1 > d0 else v1
        return rec[-1][1]
    pts, low, lift = [], None, 0
    for x in range(min(A, now + 1), H + 1):
        if x <= now:
            v = known(x)
        else:
            v = cur - rate * (x - now) + sum(a for t, a in adds if t <= x) + lift
            if dry is not None and x < (dry_until or 0) and v < dry:
                lift += BREW_DRINKS
                v += BREW_DRINKS
            low = v if low is None else min(low, v)
        if x >= A:
            pts.append((x, v))
    return ols_slope(pts), pts[-1][1], (cur if low is None else low)
def f_brew_need(self, prior_only=False):
    key = (self.loads, self.day, self.st.get("drink"), self.st.get("plants_brewable"), self.cit, len(self.orders),
           prior_only)
    memo = getattr(self, "_f_need_memo", None)
    if not isinstance(memo, dict) or len(memo) > 16:
        memo = self._f_need_memo = {}
    if key in memo:
        return memo[key]
    H = int(self.days or 0)
    f = self.f_len()
    now = int(self.day) if isinstance(self.day, (int, float)) else 0
    rate = self.f_drink_rate(prior_only)
    land0 = now + F_LAND_DAYS
    queued = self.plan_queued()
    base = [(land0, BREW_DRINKS * queued)] if queued else []
    land = max(land0, H - f + int(round(f / 2.0)))
    dry = HOLD_DRY_DAYS * rate
    out = (0, land, rate, None)
    if land <= H - F_LAND_DAYS:
        for k in range(0, F_PLAN_MAX + 1):
            s, vh, _ = self.f_project(1, rate, base + ([(land, BREW_DRINKS * k)] if k else []), dry=dry,
                                      dry_until=land)
            out = (k, land, rate, s)
            if s >= -max(0.0, vh) / T_STAR + F_SLOPE_MARGIN:
                break
    memo[key] = out
    return out
def f_mid_need(self, rate):
    f = self.f_len()
    land = int(round(f / 2.0))
    low = HOLD_DRY_DAYS * rate
    for k in range(0, F_PLAN_MAX + 1):
        pts = [(x, low + rate * (land - x) + (BREW_DRINKS * k if x >= land else 0)) for x in range(0, f + 1)]
        if ols_slope(pts) >= -max(0.0, pts[-1][1]) / T_STAR + F_SLOPE_MARGIN:
            return k
    return F_PLAN_MAX
def my1_hold_reserve(self):
    left = self.days_to_end()
    if left is not None and left <= self.f_len():
        return max(F_PLAN_MIN, self.pb_free())
    return max(F_PLAN_MIN, self.f_mid_need(self.f_drink_rate(prior_only=True)) + F_PLAN_SPARE)
def f_plan_brew(self):
    need, land, rate, slope = self.f_brew_need()
    now = int(self.day)
    drink = self.st.get("drink") or 0
    free = self.pb_free() - self.plan_queued()
    self.f_dry_floor = None
    plan = (need, land, min(need, max(0, free)))
    if plan != self.f_plan_key:
        self.f_plan_key = plan
        log("f_plan", day=self.day, need=need, land=land, rate=round(rate, 2), drink=drink,
            pb=self.st.get("plants_brewable"), free=free, slope=None if slope is None else round(slope, 2),
            food=self.st.get("food_edible"))
    mid_id = self.key_order.get("o_brew_mid")
    mid = next((x for x in self.orders if x.get("id") == mid_id), None) if mid_id is not None else None
    amount = min(need, F_PLAN_MAX, max(0, free))
    if amount < 1 or land - now <= HOLD_MID_TOL or self.f_shot_due(now, land, amount):
        if mid is not None and not (mid.get("jobs_in_progress") or 0) and self.may("o_brew_mid_cut", 2):
            self.act("o_brew_mid_cut", "cancel_order", {"order_id": mid_id}, retry=2, limit=8)
            self.done.discard("o_brew_mid")
        if amount >= 1 and not self.own_pending("o_brew_midshot"):
            r = self.act("o_brew_midshot", "add_order", {"recipe": "brew_drink", "amount": amount}, retry=1,
                         limit=8)
            if r is not None:
                log("hold_midshot", day=self.day, amount=amount, need=need, land=land, drink=drink,
                    ok=r.get("ok"))
        return
    level = drink + BREW_DRINKS * self.plan_queued() - rate * (land - now)
    if level <= HOLD_DRY_DAYS * rate + rate * HOLD_MID_TOL:
        if mid is not None and not (mid.get("jobs_in_progress") or 0) and self.may("o_brew_mid_cut", 2):
            self.act("o_brew_mid_cut", "cancel_order", {"order_id": mid_id}, retry=2, limit=8)
            self.done.discard("o_brew_mid")
        self.f_prelift(max(0, free), rate, land, drink)
        return
    below = int(math.ceil(level))
    if mid is not None:
        have = [v for k, t, v in when_sig(mid.get("when")) if k == ("DRINK", None) and t == "LessThan"]
        tot = mid.get("total") or mid.get("left")
        if (have and abs(have[0] - below) > max(3, 0.15 * below)) or (isinstance(tot, int) and tot != amount):
            if not (mid.get("jobs_in_progress") or 0) and self.may("o_brew_mid_cut", 2):
                self.act("o_brew_mid_cut", "cancel_order", {"order_id": mid_id}, retry=2, limit=8)
                self.done.discard("o_brew_mid")
        return
    r = self.act("o_brew_mid", "add_order", {"recipe": "brew_drink", "amount": amount, "repeat": "daily",
                                             "when": [{"stock": "drink", "below": below},
                                                      {"stock": "plants_brewable", "at_least": 1},
                                                      {"stock": "barrels_empty", "at_least": 1}]},
                 retry=2, limit=8)
    if r is not None:
        log("hold_mid", day=self.day, amount=amount, below=below, rate=round(rate, 2), land=land, drink=drink,
            ok=r.get("ok"))
def f_load_gap(self):
    days = [r[0] for r in self.f_rec]
    gaps = sorted(b - a for a, b in list(zip(days, days[1:]))[-3:] if b > a)
    g = gaps[len(gaps) // 2] if gaps else F_LOAD_GAP
    return max(1, min(14, g))
def f_shot_due(self, now, land, amount):
    start = land - (amount + 1) // 2
    return now >= start - HOLD_MID_TOL or now + self.f_load_gap() > start
def f_leg_score(self, rate, adds):
    H = int(self.days or 0)
    A = H - self.f_len()
    now = int(self.day) if isinstance(self.day, (int, float)) else 0
    rec = {r[0]: r[1] for r in self.f_rec if A <= r[0] <= now}
    v = float(self.st.get("drink") or 0)
    pts = sorted(rec.items())
    if not pts or pts[0][0] > A:
        pts = [(A, pts[0][1] if pts else v)] + pts
    for x in range(now + 1, H + 1):
        v = max(0.0, v - rate) + sum(a for t, a in adds if t == x)
        if x >= A:
            pts.append((x, v))
    if len(pts) < 2:
        return 1.0
    cov = sum(1 for x, y in pts if x > A and y > 0) / float(max(1, H - A))
    sl, vh = ols_slope(pts), pts[-1][1]
    t = float("inf") if sl >= 0 and vh > 0 else (0.0 if vh <= 0 else vh / -sl)
    return 0.5 * cov + 0.5 * min(1.0, t / T_STAR)
def f_split(self, free, rate, land):
    now = int(self.day) if isinstance(self.day, (int, float)) else 0
    q = BREW_DRINKS * self.plan_queued()
    best = None
    for pre in range(0, max(0, free) + 1):
        adds = [(now + F_LAND_DAYS, q + BREW_DRINKS * pre), (land, BREW_DRINKS * (free - pre))]
        sc = min(self.f_leg_score(rate * m, adds) for m in F_SPLIT_RATES)
        if best is None or sc > best[0] + 1e-9:
            best = (sc, pre)
    return (0, 0) if best is None else (best[1], max(0, free) - best[1])
def f_prelift(self, free, rate, land, drink):
    pre, mid = self.f_split(free, rate, land)
    if mid >= 1:
        self.f_dry_floor = mid + 1
    if pre >= 1 and not self.own_pending("o_brew_prelift"):
        r = self.act("o_brew_prelift", "add_order", {"recipe": "brew_drink", "amount": min(F_PLAN_MAX, pre)},
                     retry=1, limit=8)
        if r is not None:
            log("f_prelift", day=self.day, pre=pre, mid=mid, land=land, drink=drink, rate=round(rate, 2),
                ok=r.get("ok"))
def f_reserve_hold(self):
    if not self.my1_plan():
        return False
    left = self.days_to_end()
    if left is None or left <= self.f_len():
        return False
    food = self.st.get("food_edible") or 0
    if food >= F_RESERVE_FOOD_PER_CIT * max(1, self.cit or 0):
        return True
    cover = self.food_cover()
    return cover is None or cover >= left - self.f_len()
def hold_veto(self, name, args):
    if name not in ("add_order", "add_manager_order") or not isinstance(args, dict):
        return None
    brew = args.get("recipe") == "brew_drink" or "BREW" in str(args.get("reaction") or "").upper() \
        or (name == "add_manager_order" and "BREW" in str(args.get("job") or "").upper())
    if not brew:
        return None
    if self.barrel_keep():
        return self.barrel_veto(name, args)
    left = self.days_to_end()
    if not self.hold_armed or left is None or (left <= self.f_len() and not self.my1_plan()) \
            or not self.hold_active():
        return None
    reserve = self.hold_reserve()
    if self.my1_plan():
        amount = args.get("amount") if isinstance(args.get("amount"), int) else 1
        if self.leaves_reserve(amount, args.get("when"), bool(args.get("repeat")), reserve):
            return None
        log("hold_veto", day=self.day, tool=name, args=args, reserve=reserve, pb=self.st.get("plants_brewable"))
        return ("not run: no new crop can ripen before the run ends, so the deterministic layer keeps %d brewable "
                "plants to brew at mid-F (the last %d days), where they lift the drink trend most. %d plants are "
                "free now: a one-shot of at most that many runs, or a repeat order with a plants_brewable "
                "at_least %d clause." % (reserve, self.f_len(),
                                         max(0, self.pb_free() - self.plan_queued() - reserve),
                                         reserve + max(1, amount)))
    if any(k == ("PLANT", "DRINK_MAT") and t == "AtLeast" and isinstance(v, (int, float)) and v >= reserve
           for k, t, v in when_sig(args.get("when"))):
        return None
    log("hold_veto", day=self.day, tool=name, args=args, reserve=reserve, pb=self.st.get("plants_brewable"))
    return ("not run: no new crop can ripen before the run ends, so the deterministic layer keeps the brewable "
            "plants for the last %d days and brews them there one a day (drink keeps rising to the end). A brew "
            "order now needs a plants_brewable at_least %d clause." % (self.f_len(), reserve))
def keeps_barrel(self, amount, when, repeat):
    a = amount if isinstance(amount, int) and not isinstance(amount, bool) and amount >= 1 else 1
    if repeat:
        floors = [v for k, t, v in when_sig(when) if k == ("PLANT", "DRINK_MAT") and t == "AtLeast"
                  and isinstance(v, (int, float)) and not isinstance(v, bool)]
        return bool(floors) and max(floors) >= a + BARREL_KEEP + self.barrel_over()
    return a <= self.pb_free() - self.brew_planned() - BARREL_KEEP
def barrel_veto(self, name, args):
    if self.keeps_barrel(args.get("amount"), args.get("when"), bool(args.get("repeat"))):
        return None
    need = (args.get("amount") if isinstance(args.get("amount"), int) else 1) + BARREL_KEEP + self.barrel_over()
    log("barrel_veto", day=self.day, tool=name, args=args, pb=self.st.get("plants_brewable"))
    return ("not run: the deterministic layer keeps the fort's only plant barrel holding a plant (a barrel emptied "
            "of plants is taken by other food, and later harvests then lie loose and rot); its own brew standing "
            "already brews %d a day while drink is under its level. A brew order needs repeat with a "
            "plants_brewable at_least clause of at least amount + %d (%d here)." % (BARREL_KEEP_AMOUNT, BARREL_KEEP,
                                                                                     need))
def barrel_cancel(self):
    if not self.barrel_keep():
        return
    for x in self.orders:
        if x.get("recipe") != "brew_drink" or not x.get("repeat") or x.get("id") in self.owned \
                or x.get("id") is None:
            continue
        if self.keeps_barrel(x.get("total") or x.get("left"), x.get("when"), True):
            continue
        r = self.act("barrel_cancel_%s" % x.get("id"), "cancel_order", {"order_id": x.get("id")}, retry=2, limit=3)
        if r is not None:
            log("barrel_cancel", day=self.day, order=x.get("id"), when=x.get("when"), ok=r.get("ok"))
def own_pending(self, key):
    oid = self.key_order.get(key)
    return oid is not None and any(x.get("id") == oid and (x.get("left") or 0) > 0 for x in self.orders)
def allocate_plants(self):
    if not self.alloc_on() or not isinstance(self.day, (int, float)):
        return
    plan = self.plant_plan()
    sides, last, floor = plan["sides"], plan["last"], plan["floor"]
    dd, fd = self.leg_days()
    pb = self.st.get("plants_brewable") or 0
    have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
    if "brew" in sides and (dd <= fd or last) and "Still" in have and not self.own_pending("o_brew_alloc"):
        n = min(ALLOC_BREW_MAX, self.brew_budget() - floor, (self.st.get("barrels_empty") or 0) - self.brew_queued())
        cap = self.barrel_brew_cap()
        if cap is not None:
            n = min(n, cap)
        if last and dd > fd:
            n = min(n, ALLOC_BREW_MAX // 2)
        if n >= 1:
            self.act("o_brew_alloc", "add_order", {"recipe": "brew_drink", "amount": n}, retry=1, limit=99)
    seeds_ok = self.seeds_banked()
    if "cook" in sides and (fd < dd or last) and "Kitchen" in have and seeds_ok \
            and not self.own_pending("o_cook_alloc"):
        other = (self.st.get("plants_total") or 0) - pb
        cfloor = floor if self.hold_cook() else self.base_plant_floor()
        n = min(ALLOC_COOK_MAX, max(0, self.brew_budget() - cfloor) + max(0, other) // 2)
        if last and fd >= dd:
            n = min(n, ALLOC_COOK_MAX // 2)
        if n >= 1 and self.meal_wait():
            log("meal_wait", day=self.day, source="o_cook_alloc", loose=d(self.plant_loose).get("loose"))
        elif n >= 1:
            self.act("o_cook_alloc", "add_order", {"recipe": "cook_meal", "amount": n}, retry=1, limit=99)
def press_waiting(self):
    be = self.st.get("barrels_empty") or 0
    if self.rot_seen:
        waiting = (self.st.get("plants_brewable") or 0) - self.rot_keep() - be
    else:
        waiting = self.brew_planned() - be
    return max(waiting, self.seed_wait)
def barrel_press(self):
    if self.press_memo == self.loads:
        return self.press_on
    self.press_memo = self.loads
    stand, harv = self.press_stand, self.press_harv
    short = None
    if not self.alloc_on() or not ((self.days or 0) >= 336 or self.rot_seen) or self.food_lean():
        stand = harv = False
    else:
        be = self.st.get("barrels_empty") or 0
        if not self.rot_seen and (self.day or 0) < PRESS_FROM_DAY:
            stand = False
        else:
            waiting = self.press_waiting()
            if not stand and waiting >= PRESS_ON and be <= PRESS_BARRELS_LOW and not self.caravan_active:
                stand = True
            elif stand and (waiting <= PRESS_OFF or be >= PRESS_BARRELS_FREE):
                stand = False
        if (not self.rot_seen and (self.day or 0) < HARVEST_PRESS_FROM_DAY) or self.harvest_growing() <= 0:
            harv = False
        else:
            short = self.harvest_barrels_short()
            if not harv and short >= HARVEST_PRESS_ON and be < PRESS_BARRELS_FREE and not self.caravan_active:
                harv = True
            elif harv and short <= 0:
                harv = False
    on = stand or harv
    if on != self.press_on or harv != self.press_harv:
        log("barrel_press", day=self.day, on=on, standing=stand, harvest=harv, short=short,
            pb=self.st.get("plants_brewable"), barrels=self.st.get("barrels_empty"),
            rotten=self.st.get("plants_rotten"), logs=self.logs())
    self.press_on, self.press_stand, self.press_harv = on, stand, harv
    if on and isinstance(self.day, (int, float)):
        self.press_day = self.day
    return on
def labor_press(self):
    if self.labor_memo == self.loads:
        return self.labor_on
    self.labor_memo = self.loads
    on, why = self.labor_on, None
    alert = bool(d(self.o.get("burrows")).get("civilian_alert"))
    if self.hands_off is not None or not ((self.days or 0) >= 336 or self.rot_seen) or self.food_lean() \
            or (not self.rot_seen and (self.day or 0) < LABOR_FROM_DAY) or self.caravan_active or alert:
        on = False
    else:
        free = self.pb_free()
        keep = self.rot_keep() if self.rot_seen else 0
        wanted = max(self.brew_planned(), self.seed_wait, free - keep if self.rot_seen else 0)
        waiting = max(0, min(wanted, free - keep))
        stills = [w for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Still"
                  and w.get("built") is not False]
        jobs = [d(j) for w in stills for j in lst(w.get("job_details"))]
        worked = sum(1 for j in jobs if isinstance(j.get("worker_id"), int) and j["worker_id"] >= 0)
        idle_jobs = len(jobs) - worked
        crafters = sum(1 for p in self.people if p.get("job") == "MakeCrafts")
        if not on and waiting >= PRESS_ON and (self.st.get("barrels_empty") or 0) >= 1 and idle_jobs >= 1 \
                and worked < min(len(stills), waiting) and crafters >= 1:
            on, why = True, dict(waiting=waiting, stills=len(stills), worked=worked, idle_jobs=idle_jobs,
                                 crafters=crafters)
        elif on and (waiting <= PRESS_OFF or (not jobs and self.labor_nojob >= 1)):
            on = False
        self.labor_nojob = 0 if jobs else self.labor_nojob + 1
    if on != self.labor_on:
        log("labor_press", day=self.day, on=on, pb=self.st.get("plants_brewable"), pb_free=self.pb_free(),
            barrels=self.st.get("barrels_empty"), **(why or {}))
    self.labor_on = on
    if on and isinstance(self.day, (int, float)):
        self.press_day = self.day
    return on
def cook_stalled(self):
    if self.stall_memo == self.loads:
        return self.stall_on
    self.stall_memo = self.loads
    oid = self.key_order.get("o_cook_rot")
    mine = next((x for x in self.orders if oid is not None and x.get("id") == oid and (x.get("left") or 0) > 0),
                None)
    if mine is not None and not (mine.get("jobs_in_progress") or 0):
        if self.cook_wait_since is None:
            self.cook_wait_since = self.now
    else:
        self.cook_wait_since = None
    kitchens = [w for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Kitchen"
                and w.get("built") is not False]
    busy = bool(kitchens) and all(any(d(j).get("job") == "PrepareMeal" and (oid is None or d(j).get("order_id") != oid)
                                      for j in lst(w.get("job_details"))) for w in kitchens)
    if busy:
        if self.kitchen_busy_since is None:
            self.kitchen_busy_since = self.now
    else:
        self.kitchen_busy_since = None
    wait = COOK_STALL_DAYS * DAY
    on = (self.cook_wait_since is not None and self.now - self.cook_wait_since >= wait) \
        or (self.kitchen_busy_since is not None and self.now - self.kitchen_busy_since >= wait)
    if on != self.stall_on:
        log("kitchen_stall", day=self.day, on=on, rot_order=oid if mine is not None else None,
            rot_no_job=self.cook_wait_since is not None, busy=busy, pb=self.st.get("plants_brewable"),
            rotten=self.st.get("plants_rotten"))
    self.stall_on = on
    return on
def f_food_falling(self):
    if not isinstance(self.day, (int, float)) or not self.days:
        return False
    start = self.days - self.f_len()
    pts = [(p[0], p[2]) for p in self.stock_hist if isinstance(p[0], (int, float))]
    before = [q for q in pts if q[0] <= start]
    pts = before[-1:] + [q for q in pts if q[0] > start]
    if len(pts) < 2:
        return False
    slope = ols_slope(pts)
    return slope is not None and slope < 0
def rot_guard(self):
    aged = self.aged_plants()
    stuck = self.loose_stuck()
    if not (self.rot_seen or aged >= 1 or stuck >= 1) or not self.alloc_on() \
            or not isinstance(self.day, (int, float)):
        return
    if self.caravan_active and self.glut_jump >= GLUT_JUMP and self.caravan_arrival_day is not None \
            and self.day - self.caravan_arrival_day <= 1:
        return
    plan = self.plant_plan()
    if plan["in_f"] and plan["food_first"]:
        return
    have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
    pb = self.st.get("plants_brewable") or 0
    barrels = self.st.get("barrels_empty") or 0
    keep = plan["rot_keep"]
    glut = self.drink_glut()
    aged_only = not self.rot_seen or glut
    risk = max(aged, stuck)
    if self.caravan_active:
        p = d(self.plant_loose)
        risk = min(risk, p["loose"] if p.get("day") == self.day and isinstance(p.get("loose"), int) else 0)
    cap = max(0, risk - self.brew_planned()) if aged_only else ALLOC_BREW_MAX
    cook = plan["lean"] or (glut and (barrels < PRESS_BARRELS_FREE or self.wood_dry()))
    meal_ok = any(d(v).get("cookable") for v in d(self.st.get("plants_by_kind")).values())
    stuck_still = stuck >= 1 and not meal_ok
    if stuck_still:
        cook = False
    stall = False
    if cook and "Kitchen" in have and cap >= 1:
        stall = "Still" in have and self.cook_stalled() and not (plan["in_f"] and self.f_food_falling())
        n = min(cap, self.pb_free() - keep)
        if not stall:
            if n >= 2 and not self.own_pending("o_cook_rot"):
                self.act("o_cook_rot", "add_order", {"recipe": "cook_meal", "amount": max(1, n // 2)},
                         retry=1, limit=99)
                log("rot_cook", day=self.day, plants=n, aged=aged, sides=plan["sides"], lean=plan["lean"],
                    drink=self.st.get("drink"), food=self.st.get("food_edible"))
            return
        aged_only = True
        cap = max(0, risk - self.brew_planned())
    if "Still" in have and (not plan["lean"] or stuck_still or stall):
        pending = sum(max(0, x.get("left") or 0) for x in self.orders if x.get("id") in self.rot_brews)
        limit = min(ROT_SHOT_MAX, max(ALLOC_BREW_MAX, risk))
        n = min(limit - pending, self.brew_budget() - keep, barrels - self.brew_queued())
        if aged_only:
            n = min(n, cap - pending)
        bcap = self.barrel_brew_cap()
        if bcap is not None:
            n = min(n, bcap)
        if n >= 1:
            r = self.act("o_brew_rot", "add_order", {"recipe": "brew_drink", "amount": n}, retry=1, limit=99)
            oid = d(d(r).get("result")).get("order_id") if r and r.get("ok") else None
            if oid is not None:
                self.rot_brews.add(oid)
                if stall:
                    self.stall_brews.add(oid)
                    log("stall_brew", day=self.day, brews=n, risk=risk, aged=aged, stuck=stuck, keep=keep, pb=pb,
                        barrels=barrels, rot_order=self.key_order.get("o_cook_rot"))
                if stuck >= 1:
                    log("stuck_brew", day=self.day, brews=n, stuck=stuck, keep=keep, pb=pb,
                        loose=d(self.plant_loose).get("loose"), barrels=barrels,
                        alert=d(self.o.get("burrows")).get("civilian_alert"))
                if plan["hold"]:
                    log("rot_reserve_out", day=self.day, brews=n, keep=keep, floor=plan["floor"],
                        rotting=self.rotting_held(), pb=pb, loose=d(self.plant_loose).get("loose"))
    if not self.rot_seen and stuck < 1:
        return
    growing = sum(p.get("seeds_or_crops_in_plot") or 0 for p in lst(self.o.get("farm_plots"))
                  if isinstance(p, dict) and isinstance(p.get("seeds_or_crops_in_plot"), int))
    short = max(0, pb - keep) + growing - barrels
    if short >= 1 and "Carpenters" in have and self.logs() >= 4 and not self.own_pending("o_barrel_rot"):
        self.act("o_barrel_rot", "add_order", {"recipe": "make_barrel", "amount": min(ROT_BARREL_MAX, short)},
                 retry=1, limit=99)
def age_plants(self):
    if not isinstance(self.st.get("plants_brewable"), (int, float)):
        return
    now, tot = self.pb_free(), sum(n for _, n in self.plant_age)
    if now > tot:
        self.plant_age.append([self.day if self.day >= 1 else None, now - tot])
    gone = max(0, tot - now)
    while gone > 0 and self.plant_age:
        take = min(gone, self.plant_age[0][1])
        self.plant_age[0][1] -= take
        gone -= take
        if self.plant_age[0][1] <= 0:
            self.plant_age.pop(0)
def aged_plants(self):
    if not isinstance(self.day, (int, float)) or self.hands_off is not None \
            or (self.days < 336 and not self.rot_seen):
        return 0
    return sum(n for d0, n in self.plant_age if d0 is not None and self.day - d0 >= PLANT_USE_AGE)
def cover_336(self, leg, stock, prior):
    rate = max(self.measured_rate(leg) or 0, prior)
    pop = max(self.cit or 0, self.pop_forecast() if self.alloc_on() else 0)
    return pop > 0 and stock >= DRINK_GLUT_MARGIN * 336 * rate * pop
def drink_glut(self):
    if not self.alloc_on() or not self.cover_336("drink", self.st.get("drink") or 0, DRINK_PER_CIT_DAY):
        return False
    if self.cover_336("food", self.st.get("food_edible") or 0, FOOD_PER_CIT_DAY):
        return False
    tiles, sown = self.plot_tiles()
    free = (self.st.get("seeds") or 0) - sown
    return free >= tiles - sown
def wood_dry(self):
    if self.days < 336 or self.hands_off is not None or not self.wood_hist \
            or not isinstance(self.day, (int, float)):
        return False
    span = [h for h in self.wood_hist if self.day - h[0] <= WOOD_DRY_DAYS]
    if not span or self.day - self.wood_hist[0][0] < WOOD_DRY_DAYS or span[-1][1] >= WOOD_DRY_LOGS:
        return False
    if any(f for _, _, f in span):
        return False
    return all(b[1] <= a[1] for a, b in zip(span, span[1:]))
def rot_keep(self):
    if self.hold_active():
        keep, rotting = max(ROT_KEEP, self.plant_floor()), self.rotting_held()
        return max(0, min(keep, self.pb_free() - rotting)) if rotting > 0 else keep
    stuck = self.loose_stuck()
    return max(0, min(ROT_KEEP, self.pb_free() - stuck)) if stuck > 0 else ROT_KEEP
def rotting_held(self):
    stuck = self.loose_stuck()
    if not self.rot_seen:
        return stuck
    aged = self.aged_plants()
    p = d(self.plant_loose)
    fresh = isinstance(p.get("day"), (int, float)) and isinstance(self.day, (int, float)) \
        and self.day - p["day"] <= PLANT_USE_AGE
    return max(stuck, min(aged, p["loose"]) if fresh and isinstance(p.get("loose"), int) else 0)
def loose_stuck(self):
    if not isinstance(self.day, (int, float)) or not self.loose_hist or self.loose_hist[-1][0] != self.day:
        return 0
    old = [h for h in self.loose_hist if self.day - h[0] >= LOOSE_BREW_DAYS]
    if not old:
        return 0
    span = [h for h in self.loose_hist if h[0] >= old[-1][0]]
    return max(0, min(n for _, n in span))
def plot_tiles(self):
    tiles = sown = 0
    for p in lst(self.o.get("farm_plots")):
        p = d(p)
        w, h = p.get("w"), p.get("h")
        if p.get("built") is False or not all(isinstance(v, int) and not isinstance(v, bool) for v in (w, h)):
            continue
        tiles += w * h
        n = p.get("seeds_or_crops_in_plot")
        sown += n if isinstance(n, int) and not isinstance(n, bool) else 0
    return tiles, sown
def recycle_kind_ok(self, name, left):
    seasons = self.kind_seasons.get(name)
    if not isinstance(seasons, list) or left is None:
        return False
    grow = RECYCLE_GROW_DAYS.get(name, RECYCLE_GROW_DEFAULT)
    if left < grow + RECYCLE_LEAD_DAYS:
        return False
    doy = self.game_doy()
    name_at = lambda t: SEASON_NAMES[((doy + t) % YEAR_DAYS) // SEASON_DAYS]
    return name_at(RECYCLE_LEAD_DAYS) in seasons and name_at(RECYCLE_LEAD_DAYS + grow) in seasons
def regrow_cap(self):
    if not self.my1_plan() or not self.hold_active():
        return 0
    left = self.days_to_end()
    if left is None:
        return 0
    tiles, sown = self.plot_tiles()
    if tiles <= sown:
        return 0
    pbk = d(self.st.get("plants_by_kind"))
    standing = {k: int(d(v).get("n") or 0) for k, v in pbk.items() if d(v).get("brewable") and (d(v).get("n") or 0) > 0}
    if not standing:
        return 0
    f = self.f_len()
    for k in standing:
        grow = RECYCLE_GROW_DAYS.get(k, RECYCLE_GROW_DEFAULT)
        if not self.recycle_kind_ok(k, left) or left < grow + RECYCLE_LEAD_DAYS + f:
            return 0
    seeds = d(self.live_seeds_by_kind())
    sowable = sum(int(d(v).get("n") or 0) for k, v in seeds.items()
                  if self.recycle_kind_ok(k, left) and standing.get(k, 0) < AUTOFARM_THRESHOLD)
    free = max(0, sowable - sown)
    return max(0, min(sum(standing.values()), min(self.pb_free(), sum(standing.values())), tiles - sown - free))
