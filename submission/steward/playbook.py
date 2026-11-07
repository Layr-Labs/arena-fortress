"""The playbook: the fort's essentials as deterministic rules over the observation.

Each cycle `plan(obs, day)` returns the actions to run now, in priority order. Every action has a key; a key has a
cooldown and a failure count, so a rule that keeps failing backs off instead of burning actions, and the failures
show up in the model's report. The playbook owns (and the model may not cancel) the standing orders it creates.

Layout (sites are the server's ids, docs/GAME-API.md §4):
  surface (z0)  workshops on W sites
  z0-1          the farm level: a big room dug next to the stair; F sites in it become farm plots
  z0-2          the dormitory: beds placed over the level's A site, a dormitory zone over it
  z0-3          the hall: tables and chairs over the A site, a dining hall zone; the manager's office in an R room
On a fort that already has dug levels the same rules use what is there (A sites, F sites, R rooms).
"""
DAY = 1200

REOBSERVE = {"build_workshop", "build_farm", "dig_stairs", "dig_room", "place_furniture", "make_zone"}

# the workshop a strange mood's skill asks for (DF job_skill names; DF's mood rules)
MOOD_WORKSHOP = {
    "CARPENTRY": "Carpenters", "WOODCRAFT": "Craftsdwarfs", "STONECRAFT": "Craftsdwarfs", "BONECARVE": "Craftsdwarfs",
    "MASONRY": "Masons", "LEATHERWORK": "Leatherworks", "TANNER": "Tanners", "WEAVING": "Loom",
    "CLOTHESMAKING": "Clothiers", "GLASSMAKER": "GlassFurnace", "SMELT": "Smelter", "FORGE_WEAPON":
    "MetalsmithsForge", "FORGE_ARMOR": "MetalsmithsForge", "FORGE_FURNITURE": "MetalsmithsForge",
    "METALCRAFT": "MetalsmithsForge", "CUTGEM": "Jewelers", "ENCRUSTGEM": "Jewelers", "MECHANICS": "Mechanics",
    "BOWYER": "Bowyers", "WOODCUTTING": "Carpenters", "STONE_CARVE": "Masons", "SHEARING": "Farmers",
    "SPINNING": "Farmers", "POTTERY": "Kiln", "GLAZING": "Kiln", "PRESSING": "SCREW_PRESS",
}
MOOD_WORKSHOP_TEXT = [(w.lower(), v) for w, v in (
    ("carpent", "Carpenters"), ("woodcraft", "Craftsdwarfs"), ("stonecraft", "Craftsdwarfs"),
    ("bone", "Craftsdwarfs"), ("mason", "Masons"), ("leather", "Leatherworks"), ("tann", "Tanners"),
    ("weav", "Loom"), ("cloth", "Clothiers"), ("glass", "GlassFurnace"), ("smelt", "Smelter"),
    ("forg", "MetalsmithsForge"), ("metal", "MetalsmithsForge"), ("gem", "Jewelers"), ("jewel", "Jewelers"),
    ("mechanic", "Mechanics"), ("bow", "Bowyers"), ("craft", "Craftsdwarfs"))]

CORE_WORKSHOPS = ("Carpenters", "Still", "Kitchen")
LATER_WORKSHOPS = ("Farmers", "Craftsdwarfs", "Butchers")
KEY_PROFESSIONS = ("Miner", "Woodworker", "Carpenter", "Planter", "Farmer", "Woodcutter", "Brewer", "Cook")


def _thr(args):
    return next((c.get("below") for c in args.get("when") or [] if "below" in c), 0)


def _n(x, d=0):
    return x if isinstance(x, (int, float)) else d


class Playbook:
    RETRY_DAYS = 2
    MAX_FAILS = 4

    def __init__(self, days=336, hands_off_day=None, name="", brief="", goal=""):
        self.days, self.hands_off_day, self.name = days, hands_off_day, name
        self.tries, self.fails, self.last, self.done = {}, {}, {}, set()
        self.orders = {}          # standing-order key -> order id
        self.order_ids = set()    # every order this playbook made
        self.levels = {}          # role ("farm", "dorm", "hall") -> z
        self.stair_dug_at = None
        self.history = []         # (day, drink, food) samples for trends
        self.alerts = []
        self.pending_urgent = []
        self.zones_made = {}      # role -> zone id
        self.last_hostile_day = -99
        self.citizens0 = None
        self.mood_seen = set()
        self.stretch_drink = None
        self.meat_late = 0

    # ------------------------------------------------------------------------------------------------------------
    # bookkeeping
    def _may(self, key, day, every=None):
        if self.fails.get(key, 0) >= self.MAX_FAILS:
            return False
        wait = every if every is not None else self.RETRY_DAYS * (1 + self.fails.get(key, 0))
        return day - self.last.get(key, -10 ** 6) >= wait

    def result(self, key, tool, args, resp, day):
        self.last[key] = day
        self.tries[key] = self.tries.get(key, 0) + 1
        if resp.get("ok"):
            self.fails[key] = 0
            r = resp.get("result") or {}
            if tool in ("add_order", "add_manager_order"):
                oid = r.get("order_id", r.get("id"))
                if oid is not None and not key.startswith("model:"):
                    self.order_ids.add(oid)
                    if key.startswith("so_"):
                        self.orders[key] = oid
            if tool == "make_zone" and key.startswith("zone_"):
                self.zones_made[key[5:]] = r.get("zone_id")
            if tool == "dig_stairs" and key == "stair":
                self.done.add("stair")
                z0 = (r.get("steps") or [{}])[0].get("at", [None, None, None])
                top = args.get("_z0")
                self.levels.update({"farm": top - 1, "dorm": top - 2, "hall": top - 3} if top is not None else {})
            if tool == "dig_room" and key.startswith("room_"):
                self.done.add(key)
            if tool == "cancel_order":
                self.order_ids.discard(args.get("order_id"))
        else:
            self.fails[key] = self.fails.get(key, 0) + 1
            if tool == "place_furniture" and resp.get("error_code") == "no_space":
                self.need_space = day

    def see_events(self, events):
        for e in events or []:
            t = (e or {}).get("type") or ""
            if t in ("STRANGE_MOOD", "CITIZEN_DEATH", "BERSERK_CITIZEN", "CITIZEN_TANTRUM", "AMBUSH", "SIEGE",
                     "MEGABEAST_ARRIVAL", "WEREBEAST_ARRIVAL", "MIGRANT_ARRIVAL", "CAVE_COLLAPSE"):
                self.pending_urgent.append(t)

    def tripwire(self, stopped):
        r = (stopped or {}).get("reason")
        if r:
            self.pending_urgent.append(str(r))

    def urgent(self, obs):
        u, self.pending_urgent = self.pending_urgent, []
        moods = [m for m in obs.get("moods") or [] if isinstance(m, dict)]
        new = [m for m in moods if (m.get("unit_id"), m.get("job")) not in self.mood_seen]
        for m in moods:
            self.mood_seen.add((m.get("unit_id"), m.get("job")))
        if new:
            u.append("strange mood")
        if any(m.get("waiting") for m in moods) and "mood_wait" not in u:
            u.append("mood dwarf waiting for items")
        # migrants are routine for the playbook; don't wake the model just for them
        u = [x for x in u if x not in ("MIGRANT_ARRIVAL", "announcement:MIGRANT_ARRIVAL")]
        return ", ".join(dict.fromkeys(u)) if u else None

    def status(self):
        return {"alerts": self.alerts, "trend": self.trend, "housing": self.housing, "orders": self.order_ids,
                "plan": self.plan_text}

    def veto(self, tool, args, obs):
        """Model actions the playbook refuses: cancelling its standing orders."""
        if tool == "cancel_order" and args.get("order_id") in self.order_ids:
            return "that order is the steward's standing order; it keeps drink/food/furniture coming"
        if (tool == "add_order" and args.get("recipe") == "cook_meal") or \
                (tool == "add_manager_order" and str(args.get("job")) == "PrepareMeal"):
            return "cooking is the steward's (it cooks only while food is plentiful): meals made from scarce plants " \
                   "leave nothing to brew"
        if tool in ("add_order", "add_manager_order") and _n(args.get("amount"), 1) > 10:
            return "amount over 10: order 10 or fewer and top up later"
        if tool in ("add_order", "add_manager_order") and args.get("repeat"):
            if not args.get("when"):
                return "a repeating order needs a `when` stock condition, or it runs forever and eats its inputs"
            mine = {o.get("recipe") for o in getattr(self, "orders_now", []) if o.get("id") in self.order_ids
                    and o.get("repeat")}
            if args.get("recipe") in mine:
                return f"the steward already runs a standing {args.get('recipe')} order; use a one-off order to top up"
        if tool == "enable_automation" and args.get("name") == "autolabor":
            return "autolabor reassigns every dwarf's labors at once; the fort's labors are left as DF set them"
        if tool == "enable_automation" and getattr(self, "plugins", {}).get(args.get("name")) == "on":
            return f"{args.get('name')} is already on"
        if tool == "civilian_alert" and args.get("on") and not getattr(self, "hostiles", None):
            return "no hostiles are visible; the alert would stop all work outside the shelter"
        return None

    # ------------------------------------------------------------------------------------------------------------
    # reading the observation
    def _read(self, obs, day):
        st = obs.get("stocks") if isinstance(obs.get("stocks"), dict) else {}
        m = obs.get("map") if isinstance(obs.get("map"), dict) else {}
        self.st, self.m = st, m
        self.adm = obs.get("administrators") if isinstance(obs.get("administrators"), dict) else {}
        self.dwarves = [d for d in obs.get("dwarves") or [] if isinstance(d, dict)]
        self.cit = len(self.dwarves)
        if self.citizens0 is None:
            self.citizens0 = self.cit
        self.surface = m.get("surface_z")
        self.sites = [s for s in m.get("sites") or [] if isinstance(s, dict)]
        self.workshops = [w for w in obs.get("workshops") or [] if isinstance(w, dict)]
        self.ws_types = {w.get("type") for w in self.workshops}
        self.built = {w.get("type") for w in self.workshops if w.get("built")}
        self.plots = [p for p in obs.get("farm_plots") or [] if isinstance(p, dict)]
        self.zones = [z for z in obs.get("zones") or [] if isinstance(z, dict)]
        self.furniture = [f for f in obs.get("furniture") or [] if isinstance(f, dict)]
        self.orders_now = [o for o in obs.get("orders") or [] if isinstance(o, dict)]
        self.plugins = obs.get("plugins") if isinstance(obs.get("plugins"), dict) else {}
        drink, food = _n(st.get("drink")), _n(st.get("food_edible"))
        self.history = [h for h in self.history if h[0] != day] + [(day, drink, food)]
        self.history = self.history[-30:]
        self.trend = {"drink": self._slope(1), "food": self._slope(2)}
        beds_placed = sum(1 for f in self.furniture if f.get("kind") == "bed")
        self.housing = {"beds_placed": beds_placed, "seats": self._seats()}
        self.alerts = []
        if drink < 2 * self.cit:
            self.alerts.append(f"drink LOW ({drink} for {self.cit})")
        if food < 2 * self.cit:
            self.alerts.append(f"food LOW ({food} for {self.cit})")
        if beds_placed < self.cit:
            self.alerts.append(f"beds placed {beds_placed} < citizens {self.cit}")
        if self.trend["drink"] is not None and self.trend["drink"] < 0 and drink / max(0.1, -self.trend["drink"]) < 40:
            self.alerts.append("drink falling, <40 days left at this rate")
        if self.trend["food"] is not None and self.trend["food"] < 0 and food / max(0.1, -self.trend["food"]) < 40:
            self.alerts.append("food falling, <40 days left at this rate")
        unval = [o for o in self.orders_now if not o.get("validated") and o.get("id") in self.order_ids]
        if len(unval) >= 2 and not self.adm.get("manager_active_for_orders"):
            self.alerts.append("orders not validated: no active manager")
        elif len(unval) >= 4:
            self.alerts.append(f"{len(unval)} orders waiting for validation (manager office?)")
        self._obs_burrows = obs.get("burrows") if isinstance(obs.get("burrows"), dict) else {}
        self._obs_moods = [x for x in obs.get("moods") or [] if isinstance(x, dict)]
        self.hostiles = [h for h in ((obs.get("threats") or {}).get("hostiles") or []) if isinstance(h, dict)] \
            if isinstance(obs.get("threats"), dict) else []

    def _slope(self, i):
        h = [x for x in self.history if x[0] >= self.history[-1][0] - 12]
        if len(h) < 3 or h[-1][0] - h[0][0] < 4:
            return None
        n = len(h)
        mx = sum(x[0] for x in h) / n
        my = sum(x[i] for x in h) / n
        den = sum((x[0] - mx) ** 2 for x in h)
        return sum((x[0] - mx) * (x[i] - my) for x in h) / den if den else None

    def _seats(self):
        dining = {z.get("id") for z in self.zones if "din" in str(z.get("type") or "").lower()}
        if not dining:
            return 0
        chairs = [f for f in self.furniture if f.get("kind") == "chair" and set(f.get("zone_ids") or []) & dining]
        tables = [f for f in self.furniture if f.get("kind") == "table" and set(f.get("zone_ids") or []) & dining]
        # a seat is a chair with a table next to it (8-neighbour, same level)
        n = 0
        for c in chairs:
            if any(t.get("z") == c.get("z") and abs(t.get("x", 0) - c.get("x", 0)) <= 1
                   and abs(t.get("y", 0) - c.get("y", 0)) <= 1 for t in tables):
                n += 1
        return n

    def _sites(self, kind, free=True):
        return [s for s in self.sites if s.get("kind") == kind and (not free or s.get("free", True))]

    def _a_site(self, z):
        return next((s for s in self._sites("A") if s.get("z") == z), None)

    def _pending(self, recipe=None, job=None):
        for o in self.orders_now:
            if (recipe and o.get("recipe") == recipe) or (job and o.get("job") == job):
                if _n(o.get("left")) > 0 or o.get("repeat"):
                    return True
        return False

    def _have_order(self, key):
        oid = self.orders.get(key)
        return oid is not None and any(o.get("id") == oid for o in self.orders_now)

    def _free(self, kind):
        return _n((self.st.get("furniture_free") or {}).get(kind))

    # ------------------------------------------------------------------------------------------------------------
    # the plan
    def plan(self, obs, day):
        self.debug = {}
        self._read(obs, day)
        self.debug["orders"] = [f"{o.get('id')}:{o.get('recipe') or o.get('job')}:{o.get('left')}/{o.get('total')}"
                                f":{'v' if o.get('validated') else '-'}{'a' if o.get('active') else '-'}"
                                f":{o.get('jobs_in_progress')}" for o in self.orders_now]
        self.debug["stock"] = {k: self.st.get(k) for k in ("drink", "food_edible", "plants_brewable", "plants_total",
                                                           "seeds", "logs_usable", "barrels_empty", "prepared_meals",
                                                           "beds", "furniture_free")}
        self.debug["plots"] = [(p.get("id"), p.get("seeds_or_crops_in_plot"), p.get("crop_this_season"))
                               for p in self.plots]
        self.debug["housing"] = self.housing
        mid = self.adm.get("MANAGER_id")
        self.debug["manager"] = next(({k: d.get(k) for k in ("job", "x", "y", "z", "stress")}
                                      for d in self.dwarves if d.get("id") == mid), None)
        self.debug["canc"] = (obs.get("recent_cancellations") or [])[:3]
        out = []
        steps = [self._defence, self._manager, self._office, self._automation, self._workshops, self._mood,
                 self._standing_orders, self._food, self._topups, self._dig, self._farms, self._housing]
        for step in steps:
            for a in step(day) or []:
                if a is None:
                    continue
                key, tool, args = a
                if self._may(key, day):
                    out.append((key, tool, args))
            if len(out) >= 14:
                break
        self.plan_text = self._describe()
        return out[:14]

    def _describe(self):
        bits = []
        for role in ("farm", "dorm", "hall"):
            if role in self.levels:
                bits.append(f"{role} level z{self.levels[role]}")
        so = [k[3:] for k in self.orders]
        if so:
            bits.append("standing orders: " + ",".join(so))
        gave_up = [k for k, v in self.fails.items() if v >= self.MAX_FAILS]
        if gave_up:
            bits.append("gave up on: " + ",".join(gave_up[:8]))
        return "; ".join(bits)

    # --- 0. defence ---------------------------------------------------------------------------------------------
    def _defence(self, day):
        invaders = [h for h in self.hostiles if h.get("invader") or h.get("dist_to_wagon", 999) < 25]
        acts = []
        burrows = self._obs_burrows
        alert_on = bool(burrows.get("civilian_alert"))
        has_burrow = any(b.get("civ_alert_burrow") for b in burrows.get("list") or [] if isinstance(b, dict))
        if invaders:
            self.last_hostile_day = day
            near = min(_n(h.get("dist_to_wagon"), 999) for h in invaders)
            if not has_burrow:
                a = self._a_site(self.levels.get("dorm")) or (self._sites("A") or [None])[0]
                if a:
                    acts.append(("burrow", "create_burrow", {"site": a["id"], "levels": 3}))
            elif not alert_on and near <= 45:
                acts.append(("alert_on", "civilian_alert", {"on": True}))
        elif alert_on and day - self.last_hostile_day >= 1:
            acts.append(("alert_off", "civilian_alert", {"on": False}))
        return acts

    # --- 1. manager ---------------------------------------------------------------------------------------------
    def _manager(self, day):
        mgr = self.adm.get("MANAGER")
        if mgr and mgr != "VACANT":
            return []
        free = [d for d in self.dwarves if not d.get("positions") and d.get("adult", True)]
        spare = [d for d in free if not any(p in (d.get("profession") or "") for p in KEY_PROFESSIONS)]
        spare.sort(key=lambda d: -_n(d.get("organizer_skill")))
        pick = (spare or free or [{}])[0].get("id")
        return [("manager", "appoint_manager", {"dwarf_id": pick} if pick is not None else {})]

    def _office(self, day):
        """The manager's office: an office zone with a built chair, assigned to the manager. DF stops validating
        orders from about 20 citizens without one, which stalls every order, so this runs early (from 14 citizens)
        and the zone and its chair go on the same site: a chair placed on the site is always inside the zone."""
        mid = self.adm.get("MANAGER_id")
        if mid is None or (self.cit < 14 and not self.adm.get("manager_required_office")):
            return []
        office = self.adm.get("manager_office")
        offices = [z for z in self.zones if "office" in str(z.get("type") or "").lower()]
        self.debug["office"] = {"adm": office, "zones": [{k: z.get(k) for k in ("id", "x", "y", "z", "w", "h", "owner",
                                "furniture", "furniture_planned")} for z in offices], "mid": mid,
                                "free_chair": self._free("chair")}
        if isinstance(office, dict) and office.get("chair"):
            return []

        def has_chair(z):
            return bool((z.get("furniture") or {}).get("chair") or (z.get("furniture_planned") or {}).get("chair"))

        mine = next((z for z in offices if z.get("owner") == mid), None)
        if mine is not None and has_chair(mine):
            return []                                   # placed; DF builds it
        # an office that already has a chair goes to the manager (also re-assigns away from a chairless one)
        ready = next((z for z in offices if z.get("owner") is None and has_chair(z)), None)
        if ready:
            return [("office_assign_%s" % ready["id"], "assign_zone", {"zone_id": ready["id"], "dwarf_id": mid})]
        if mine is not None:
            site = self._site_for_zone(mine)
            if site and self._free("chair") > 0 and self.tries.get("office_chair", 0) < 2:
                return [("office_chair", "place_furniture", {"kind": "chair", "site": site["id"], "count": 1})]
        elif (free_off := next((z for z in offices if z.get("owner") is None), None)) is not None:
            return [("office_assign_%s" % free_off["id"], "assign_zone", {"zone_id": free_off["id"], "dwarf_id": mid})]
        if self._free("chair") <= 0:
            if "Carpenters" in self.ws_types and not self._pending_once("make_chair"):
                return [("office_chair_order", "add_order", {"recipe": "make_chair", "amount": 2})]
            return []
        # a fresh office (zone + chair on the same site, same cycle); at most one every 4 days
        if not self._may("new_office", day, every=4):
            return []
        site = self._office_site(exclude=getattr(self, "office_site", None))
        if not site:
            return []
        self.office_site = site["id"]
        self.last["new_office"] = day
        return [("zone_office_" + site["id"], "make_zone", {"kind": "office", "site": site["id"]}),
                ("office_chair_" + site["id"], "place_furniture", {"kind": "chair", "site": site["id"], "count": 1})]

    def _office_site(self, exclude=None):
        """A dug R room nobody uses (a real 3x3 office), else the largest A site (most free tiles; >= 4, so it
        is more than a stair's foot)."""
        rooms = [s for s in self._sites("R") if s.get("dug") and s.get("free", True) and s.get("id") != exclude]
        if rooms:
            return rooms[0]
        a = [s for s in self._sites("A") if _n(s.get("open_tiles"), 0) >= 4 and s.get("id") != exclude]
        a.sort(key=lambda s: -_n(s.get("open_tiles"), 0))
        return a[0] if a else None

    def _site_for_zone(self, z):
        """The site the zone was made on: the same box (zone x,y,z,w,h = the site's)."""
        for s in self.sites:
            if s.get("kind") in ("R", "A") and (s.get("x"), s.get("y"), s.get("z")) == (z.get("x"), z.get("y"), z.get("z")):
                return s
        return None

    # --- 2. automation ------------------------------------------------------------------------------------------
    def _automation(self, day):
        acts = []
        for p in ("autochop", "seedwatch", "autofarm"):
            if self.plugins.get(p) != "on":
                acts.append(("auto_" + p, "enable_automation", {"name": p}))
        return acts

    # --- 3. workshops -------------------------------------------------------------------------------------------
    def _workshops(self, day):
        wsites = self._sites("W")
        if not wsites:
            return []
        has_mat = _n(self.st.get("logs_usable")) + _n(self.st.get("boulders_usable")) > 0
        if not has_mat:
            return []
        want = list(CORE_WORKSHOPS) + ["Fishery"]   # every season-0 site has a river or brook: fish is food
        if self.cit >= 10 or day > 20:
            want += ["Farmers"]
        if self.cit >= 14 or day > 40:
            want += ["Craftsdwarfs", "Butchers"]
        for t in want:
            if t not in self.ws_types:
                return [("ws_" + t, "build_workshop", {"type": t, "site": wsites[0]["id"]})]
        # furniture behind the population: more Carpenters so several carpenters work at once (max 3)
        carp = sum(1 for w in self.workshops if w.get("type") == "Carpenters")
        backlog = (max(0, self.cit - self.housing["beds_placed"]) + max(0, (self.cit + 1) // 2 - self.housing["seats"]))
        if carp < 3 and backlog > 8 * carp and _n(self.st.get("logs_usable")) > 10:
            return [("ws_Carpenters%d" % (carp + 1), "build_workshop", {"type": "Carpenters", "site": wsites[0]["id"]})]
        return []

    # --- 4. moods -----------------------------------------------------------------------------------------------
    def _mood(self, day):
        acts = []
        wsites = self._sites("W")
        for m in self._obs_moods:
            if not isinstance(m, dict) or m.get("claimed_workshop"):
                continue
            skill = str(m.get("skill") or "").upper()
            ws = MOOD_WORKSHOP.get(skill)
            if not ws:
                low = skill.lower()
                ws = next((v for k, v in MOOD_WORKSHOP_TEXT if k in low), None)
            if ws and ws not in self.ws_types and wsites:
                acts.append(("mood_ws_" + ws, "build_workshop", {"type": ws, "site": wsites[0]["id"]}))
        return acts

    # --- 5. standing orders ---------------------------------------------------------------------------------
    def _final_stretch(self, day):
        """The last days before the fort runs without us (hands-off window) or the end of a long run: stocks must
        be rising into it, because the score reads the trend over that window."""
        if self.hands_off_day is not None:
            return self.hands_off_day - day <= 14
        return self.days - day <= max(30, self.days // 4 + 4)

    def _targets(self, day=0):
        c = max(self.cit, 7)
        # beds/tables/chairs: DF's order condition counts only unplaced items, so the standing orders keep a few
        # spare; the shortfall itself is ordered one-off by _topups from placed + free counts
        t = {"drink": max(60, 7 * c), "meals": max(10, c // 2), "spare": 3, "barrels": 6 + c // 8,
             "plant_reserve": 2}   # a larger reserve starved brewing: OP1 ran dry at day 322 (measured)
        if self._final_stretch(day):
            if self.stretch_drink is None:
                self.stretch_drink = _n(self.st.get("drink"))
            t["drink"] = max(t["drink"], int(self.stretch_drink + 4 * c))
        return t

    def _standing_orders(self, day):
        if "Still" not in self.ws_types and "Carpenters" not in self.ws_types:
            return []
        t = self._targets(day)
        c = max(self.cit, 7)
        want = [
            ("so_barrel", "add_order", {"recipe": "make_barrel", "amount": 2, "repeat": "daily",
                                        "when": [{"stock": "barrels_empty", "below": t["barrels"]},
                                                 {"stock": "logs", "at_least": 3}]}, "Carpenters"),
            ("so_brew", "add_order", {"recipe": "brew_drink", "amount": 3, "repeat": "daily",
                                      "when": [{"stock": "drink", "below": t["drink"]},
                                               {"stock": "plants_brewable", "at_least": t["plant_reserve"]},
                                               {"stock": "barrels_empty", "at_least": 1}]}, "Still"),
            ("so_fruit", "add_order", {"recipe": "brew_drink_from_fruit", "amount": 2, "repeat": "daily",
                                       "when": [{"stock": "drink", "below": t["drink"]},
                                                {"stock": "barrels_empty", "at_least": 1}]}, "Still"),
            # no cooking: it destroys the cooked plant's seeds (brewing or eating raw returns them). A standing cook
            # order took OP1 from 58 seeds to 2 and the plots went unplanted (measured twice); the score counts
            # edible items, raw or cooked, so meals buy nothing here.
            ("so_fish", "add_manager_order", {"job": "PrepareRawFish", "amount": 3, "repeat": "daily",
                                              "when": [{"item_type": "FISH_RAW", "at_least": 1}]}, "Fishery"),
            ("so_bed", "add_order", {"recipe": "make_bed", "amount": 2, "repeat": "daily",
                                     "when": [{"stock": "beds", "below": t["spare"]},
                                              {"stock": "logs", "at_least": 3}]}, "Carpenters"),
            ("so_table", "add_order", {"recipe": "make_table", "amount": 1, "repeat": "daily",
                                       "when": [{"stock": "tables", "below": t["spare"]},
                                                {"stock": "logs", "at_least": 5}]}, "Carpenters"),
            ("so_chair", "add_order", {"recipe": "make_chair", "amount": 1, "repeat": "daily",
                                       "when": [{"stock": "chairs", "below": t["spare"] + 1},
                                                {"stock": "logs", "at_least": 5}]}, "Carpenters"),
        ]
        if self.days >= 200 and self.cit >= 10 and self.housing["beds_placed"] >= self.cit:
            # created wealth for the fortress rank (Hamlet: 20 citizens + 5000 created): wooden crafts from spare logs
            want.append(("so_crafts", "add_manager_order", {
                "job": "MakeCrafts", "material_category": ["wood"], "amount": 2, "repeat": "daily",
                "when": [{"item_type": "WOOD", "at_least": 40}, {"item_type": "CRAFTS", "below": 400}]}, "Craftsdwarfs"))
        acts = []
        self._made_args = getattr(self, "_made_args", {})
        for key, tool, args, ws in want:
            if ws not in self.ws_types:
                continue
            made = self.orders.get(key)
            if made is not None and self._have_order(key):
                old = self._made_args.get(key)
                # the population outgrew the order's threshold: replace it (cancel, then add next cycle)
                if old and _thr(args) > _thr(old) * 1.25 + 3:
                    acts.append((key + "_cancel", "cancel_order", {"order_id": made}))
                    self.orders.pop(key, None)
                continue
            self._made_args[key] = args
            acts.append((key, tool, args))
        return acts

    # --- 5b. food emergency: meat from the fortress's livestock -----------------------------------------------
    MEAT_ORDER = ("YAK", "WATER_BUFFALO", "COW", "HORSE", "DONKEY", "MULE", "LLAMA", "ALPACA", "SHEEP", "GOAT",
                  "PIG", "BIRD_TURKEY", "BIRD_GOOSE", "BIRD_DUCK", "BIRD_GUINEAFOWL", "BIRD_CHICKEN")

    def food_low(self, obs):
        st = obs.get("stocks") if isinstance(obs.get("stocks"), dict) else {}
        cit = len([d for d in obs.get("dwarves") or [] if isinstance(d, dict)])
        return _n(st.get("food_edible")) < max(10, cit // 2)

    def wants_animals(self, obs, day):
        """Livestock is needed for food when it runs low, and in the last 20 days of a long run while food is not
        rising (the score projects the final weeks' trend: stores laid in before the end count)."""
        if self.food_low(obs):
            return True
        return self.days >= 200 and self.days - day <= 20 and self.meat_late < 3 \
            and (self.trend.get("food") is None or self.trend.get("food") <= 0.2) if hasattr(self, "trend") else False

    def _food(self, day):
        animals = getattr(self, "animals", None)
        if not animals:
            return []
        late = not self.food_low({"stocks": self.st, "dwarves": self.dwarves})
        if late and not self._may("meat_late", day, every=5):
            return []
        if "Butchers" not in self.ws_types:
            w = self._sites("W")
            return [("ws_Butchers", "build_workshop", {"type": "Butchers", "site": w[0]["id"]})] if w else []
        if any(a.get("marked_for_slaughter") for a in animals):
            return []                                   # one at a time
        cand = [a for a in animals if a.get("tame") and not a.get("pet_owner_id") and a.get("race") in self.MEAT_ORDER]
        if not cand:
            return []
        # biggest race first, adults before young (more meat)
        cand.sort(key=lambda a: (self.MEAT_ORDER.index(a["race"]), not a.get("adult")))
        if late:
            cand = [a for a in cand if a.get("adult")]
            if not cand:
                return []
            self.meat_late += 1
            self.last["meat_late"] = day
        a = cand[0]
        return [("slaughter_%s" % a["id"], "slaughter", {"unit_id": a["id"]})]

    # --- 6. one-time top-ups (fast reaction while the standing orders wait for their daily check) --------------
    def _topups(self, day):
        acts = []
        drink, cit = _n(self.st.get("drink")), max(1, self.cit)
        plants, barrels = _n(self.st.get("plants_brewable")), _n(self.st.get("barrels_empty"))
        if "Still" in self.ws_types and drink < 4 * cit and plants > 0 and barrels > 0 \
                and not self._pending_once("brew_drink"):
            acts.append(("top_brew", "add_order", {"recipe": "brew_drink", "amount": max(1, min(10, plants, barrels))}))
        if "Carpenters" in self.ws_types and barrels < 2 and _n(self.st.get("logs_usable")) > 2 \
                and not self._pending_once("make_barrel"):
            acts.append(("top_barrel", "add_order", {"recipe": "make_barrel", "amount": 4}))
        logs = _n(self.st.get("logs_usable"))
        if "Carpenters" in self.ws_types and logs > 3:
            need_beds = self.cit + 2 - self.housing["beds_placed"] - self._free("bed")
            if need_beds > 2 and not self._pending_once("make_bed"):
                acts.append(("top_bed", "add_order", {"recipe": "make_bed", "amount": min(15, need_beds)}))
            need_seats = (self.cit + 1) // 2 + 2 - self.housing["seats"]
            for kind, recipe in (("table", "make_table"), ("chair", "make_chair")):
                n = need_seats - self._free(kind)
                if n > 1 and not self._pending_once(recipe):
                    acts.append(("top_" + kind, "add_order", {"recipe": recipe, "amount": min(10, n)}))
        return acts

    def _pending_once(self, recipe):
        return any(o.get("recipe") == recipe and not o.get("repeat") and _n(o.get("left")) > 0
                   for o in self.orders_now)

    # --- 7. digging ---------------------------------------------------------------------------------------------
    def _dig(self, day):
        """A stair shaft three levels down, then a big room per level beside it (dig_room from its R site)."""
        if self.surface is None:
            return []
        acts = []
        z0 = self.surface
        # DF gives a manager who is also a miner dig jobs before order validation: dig designated before the first
        # orders are validated can hold every order for two weeks (measured: LT08 fort 2002, manager digging days
        # 2-15, orders validated day 16). So the first dig waits until our orders are validated, at most 6 days.
        if getattr(self, "first_day", None) is None:
            self.first_day = day
        if "stair" not in self.done and day - self.first_day < 6 and len(self.plots) >= 2 \
                and not any(o.get("validated") for o in self.orders_now):
            return []
        if "stair" not in self.done:
            # an existing dug level 2+ below the surface is reused; otherwise dig our own shaft
            s_sites = self._sites("S")
            if s_sites:
                s = sorted(s_sites, key=lambda s: self._dist_wagon(s))[0]
                acts.append(("stair", "dig_stairs", {"site": s["id"], "z_bottom": z0 - 3, "_z0": z0}))
            return acts
        # one room per level: the first R site seen on each level gets a big dig
        for role, dz, (w, h) in (("farm", 1, (11, 7)), ("dorm", 2, (11, 7)), ("hall", 3, (11, 7))):
            z = z0 - dz
            key = "room_" + role
            if key in self.done:
                continue
            r = next((s for s in self._sites("R") if s.get("z") == z and not s.get("designated")), None)
            if r:
                acts.append((key, "dig_room", {"site": r["id"], "w": w, "h": h}))
        # the living levels are full (a placement failed for space): one more room from the next free R site there
        if getattr(self, "need_space", None) is not None and self._may("expand", day, every=6):
            levels = [z0 - 2, z0 - 3, z0 - 1]
            r = next((s for z in levels for s in self._sites("R") if s.get("z") == z and not s.get("designated")), None)
            if r:
                self.need_space = None
                self.last["expand"] = day
                acts.append(("expand_" + r["id"], "dig_room", {"site": r["id"], "w": 9, "h": 7}))
        return acts

    def _dist_wagon(self, s):
        w = self.m.get("wagon") or {}
        return max(abs(_n(s.get("x")) - _n(w.get("x"))), abs(_n(s.get("y")) - _n(w.get("y"))))

    # --- 8. farms -----------------------------------------------------------------------------------------------
    def _farms(self, day):
        want = min(10, max(6, self.cit // 3 + 2))
        if len(self.plots) >= want:
            return []
        f = self._sites("F")
        if f:
            return [("farm_" + f[0]["id"], "build_farm", {"site": f[0]["id"]})]
        rooms = [s for s in self._sites("R") if s.get("dug") and s.get("soil") and s.get("free", True)
                 and s.get("z") == self.levels.get("farm")]
        if rooms:
            return [("farm_" + rooms[0]["id"], "build_farm", {"site": rooms[0]["id"]})]
        return []

    # --- 9. housing: beds, dormitory, dining --------------------------------------------------------------------
    def _housing(self, day):
        acts = []
        dorm = self._living_site("dorm")
        hall = self._living_site("hall") or dorm
        if self._office_needs_chair():
            osite = getattr(self, "office_site", None)
            dorm = None if dorm and dorm.get("id") == osite else dorm
            hall = None if hall and hall.get("id") == osite else hall
        if dorm:
            n = self._free("bed")
            if n > 0:
                acts.append(("beds", "place_furniture", {"kind": "bed", "site": dorm["id"], "count": min(30, n)}))
            if not self._zone_on(dorm, "dorm") and self._may("zone_dorm_z%s" % dorm.get("z"), 0):
                acts.append(("zone_dorm", "make_zone", {"kind": "dormitory", "site": dorm["id"]}))
        if hall:
            t, c = self._free("table"), self._free("chair")
            reserve_chair = 2 if self._office_needs_chair() else 0
            k = min(t, max(0, c - reserve_chair), 15)
            if k > 0:
                acts.append(("tables", "place_furniture", {"kind": "table", "site": hall["id"], "count": k}))
                acts.append(("chairs", "place_furniture", {"kind": "chair", "site": hall["id"], "count": k}))
            if not self._zone_on(hall, "din"):
                acts.append(("zone_hall", "make_zone", {"kind": "dining_hall", "site": hall["id"]}))
        return acts

    def _office_needs_chair(self):
        office = self.adm.get("manager_office")
        return self.cit >= 12 and not (isinstance(office, dict) and office.get("chair"))

    def _living_site(self, role):
        """The A site of the role's level once it has room; else any A site that is not mostly farm."""
        z = self.levels.get(role)
        if z is None and self.surface is not None:
            z = self.surface - {"farm": 1, "dorm": 2, "hall": 3}[role]
        a = self._a_site(z)
        if a and _n(a.get("open_tiles"), 9) >= 6:
            return a
        if role == "dorm":
            # a fort with its own layout: the biggest A site without farm plots
            cands = [s for s in self._sites("A") if not any(p.get("z") == s.get("z") for p in self.plots)]
            cands.sort(key=lambda s: -_n(s.get("open_tiles")))
            if cands and _n(cands[0].get("open_tiles")) >= 6:
                return cands[0]
            # last resort: the farm level's spare tiles
            farm_a = [s for s in self._sites("A") if _n(s.get("open_tiles")) >= 3]
            return farm_a[0] if farm_a else None
        return None

    def _zone_on(self, site, kind):
        return any(kind in str(z.get("type") or "").lower() and z.get("z") == site.get("z") for z in self.zones)

    # --- time ---------------------------------------------------------------------------------------------------
    def advance_days(self, obs, day, days_left):
        """Short steps while the fort is being set up or something is going on, longer once it runs itself."""
        busy = (_n(obs.get("dig_designations_pending")) > 0 or self.hostiles or self._obs_moods
                or any(not w.get("built") for w in self.workshops) or self.alerts)
        if day < 6 or self.hostiles or self._obs_moods:
            return 1
        if busy:
            return 2
        return 4 if self.days >= 200 else 3
