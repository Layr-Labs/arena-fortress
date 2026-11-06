"""Caretaker: a deterministic Dwarf Fortress management layer for game API v0.
Executes rate-limited, idempotent public tool calls to ensure basic fort operations:
manager appointment, office setup, core workshops, farming, standing repeating supply orders,
dormitory and dining hall zoning, bed and dining furniture placement, strange mood handling, and defense.
Makes no model calls and spends zero credits.
"""
import json
import math
import sys
import time

DAY = 1200                  # ticks per in-game day
DRINK_CAP = 300
MEAL_CAP = 200
MAX_ACTIONS_PER_DAY = 15

MOOD_WORKSHOP = {
    "WOODCRAFT": "Craftsdwarfs", "STONECRAFT": "Craftsdwarfs", "BONECARVE": "Craftsdwarfs",
    "CARPENTRY": "Carpenters", "MASONRY": "Masons", "WOOD_BURNING": "WoodFurnace",
    "GLASSMAKER": "GlassFurnace", "TANNER": "Leatherworks", "LEATHERWORK": "Leatherworks",
    "WEAVING": "Loom", "CLOTHESMAKING": "Clothiers", "FORGE_WEAPON": "MetalsmithsForge",
    "FORGE_ARMOR": "MetalsmithsForge", "FORGE_FURNITURE": "MetalsmithsForge",
    "METALCRAFT": "MetalsmithsForge", "CUTGEM": "Jewelers", "ENCRUSTGEM": "Jewelers",
    "MECHANICS": "Mechanics", "POTTERY": "Kiln", "BOWYER": "Bowyers",
}


def _d(v):
    return v if isinstance(v, dict) else {}


def _l(v):
    return v if isinstance(v, list) else []


class Caretaker:
    def __init__(self, game):
        self.game = game
        self.tries = {}       # key -> attempt count
        self.last = {}        # key -> tick of last attempt
        self.roles = {}       # site_id -> "farm" | "dorm" | "dine" | "office"
        self.now = 0
        self.alert_since = None
        self.count = 0

    def may(self, key, retry_days=2, limit=6):
        if self.tries.get(key, 0) >= limit:
            return False
        return (self.now - self.last.get(key, -10**9)) >= retry_days * DAY

    def act(self, key, tool, args, retry_days=2, limit=6):
        """Execute one rate-limited action via the game API."""
        if not self.may(key, retry_days, limit):
            return None
        self.tries[key] = self.tries.get(key, 0) + 1
        self.last[key] = self.now
        r = self.game.act(tool, args)
        self.count += 1
        if r.get("ok"):
            self.tries[key] = max(0, self.tries[key] - 1)
        return r

    def load(self, resp):
        self.resp = resp
        self.o = _d(resp.get("observation"))
        self.st = _d(self.o.get("stocks"))
        self.map = _d(self.o.get("map"))
        self.adm = _d(self.o.get("administrators"))
        self.now = _d(self.o.get("date")).get("abs_tick") or resp.get("tick") or 0
        self.people = [x for x in _l(self.o.get("dwarves")) if isinstance(x, dict)]
        self.cit = max(1, self.adm.get("citizens") or len(self.people))
        self.sites = [s for s in _l(self.map.get("sites")) if isinstance(s, dict)]
        self.orders = [x for x in _l(self.o.get("orders")) if isinstance(x, dict)]
        self.zones = [z for z in _l(self.o.get("zones")) if isinstance(z, dict)]
        self.free_furn = _d(self.st.get("furniture_free"))
        self.placed = {}
        for f in _l(self.o.get("furniture")):
            if isinstance(f, dict):
                k = f.get("kind")
                self.placed[k] = self.placed.get(k, 0) + 1
        self.surface = self.map.get("surface_z")

    def kind(self, k):
        return [s for s in self.sites if s.get("kind") == k]

    def logs(self):
        return self.st.get("logs_usable", 0) or 0

    def material(self):
        return self.logs() + (self.st.get("boulders_usable", 0) or 0)

    def standing(self, recipe):
        return any(x.get("recipe") == recipe and x.get("repeat") for x in self.orders)

    def pending(self, recipe):
        return any(x.get("recipe") == recipe and (x.get("left") or 0) > 0 for x in self.orders)

    def zone_match(self, word):
        return [z for z in self.zones if word.lower() in str(z.get("type")).lower()]

    def undug_rooms(self):
        return [r for r in self.kind("R") if not r.get("designated")]

    def dug_rooms(self, role=None):
        return [r for r in self.kind("R") if r.get("dug") and r.get("free", True)
                and (role is None or self.roles.get(r["id"]) == role)]

    def farm_target(self):
        return max(3, min(8, math.ceil(self.cit / 5)))

    # ---- Work routines
    def step_mood(self):
        """Construct mood workshop and trigger slaughter if bone demanded."""
        for m in _l(self.o.get("moods")):
            m = _d(m)
            if m.get("mood") in ("Melancholy", "Raving", "Berserk", "Traumatized"):
                continue
            if not m.get("claimed_building_id"):
                skill = str(m.get("skill") or "").upper()
                wtype = MOOD_WORKSHOP.get(skill, "Craftsdwarfs")
                have = {w.get("type") for w in _l(self.o.get("workshops")) if isinstance(w, dict)}
                if wtype not in have:
                    self.build_ws(wtype, retry_days=2)
            for need in _l(m.get("items_needed")):
                need = _d(need)
                desc = str(need.get("demand") or need.get("item") or "").lower()
                if "bone" in desc:
                    have = {w.get("type") for w in _l(self.o.get("workshops")) if isinstance(w, dict)}
                    if "Butchers" not in have:
                        self.build_ws("Butchers", retry_days=2)
                    if self.may("slaughter", retry_days=4, limit=4):
                        q = self.game.query("units", kind="animals")
                        res = _d(q.get("result"))
                        animals = _l(res.get("units") or res.get("animals"))
                        for a in animals:
                            a = _d(a)
                            if a.get("tame") and a.get("pet_owner_id") in (None, -1) and not a.get("marked_for_slaughter"):
                                self.act("slaughter", "slaughter", {"unit_id": a.get("id")}, retry_days=4, limit=4)
                                break

    def step_management(self):
        """Appoint manager, enable automation plugins, and create office zone with chair."""
        if not self.adm.get("manager_active_for_orders"):
            free = [p for p in self.people if not p.get("positions") and p.get("adult", True)]
            free.sort(key=lambda p: -(p.get("organizer_skill") or 0))
            mgr_id = free[0]["id"] if free else None
            self.act("manager", "appoint_manager", {"dwarf_id": mgr_id} if mgr_id else {}, retry_days=1, limit=8)

        plugins = _d(self.o.get("plugins"))
        for plug in ("autochop", "seedwatch"):
            if plugins.get(plug) != "on":
                self.act("plug_" + plug, "enable_automation", {"name": plug}, retry_days=5)
        if self.o.get("farm_plots") and plugins.get("autofarm") != "on":
            self.act("plug_autofarm", "enable_automation", {"name": "autofarm"}, retry_days=5)

        # Office setup: required by DF once population reaches ~14-20
        if self.cit >= 14 or self.adm.get("manager_needs_office"):
            mo = self.adm.get("manager_office")
            if isinstance(mo, dict) and mo.get("chair"):
                return
            mgr_id = self.adm.get("MANAGER_id")
            offices = self.zone_match("office")
            mine = next((z for z in offices if mgr_id is not None and z.get("owner") == mgr_id), None)
            if not mine:
                spare = next((z for z in offices if z.get("owner") is None), None)
                if spare and mgr_id is not None:
                    self.act("office_assign", "assign_zone", {"zone_id": spare["id"], "dwarf_id": mgr_id}, retry_days=2)
                    return
                # Create office zone
                room = next(iter(self.dug_rooms("office") + self.dug_rooms("dine") + self.kind("A")), None)
                if room:
                    self.act("office_zone", "make_zone", {"kind": "office", "site": room["id"]}, retry_days=3)
                return
            # Office exists, check chair
            has_chair = _d(mine.get("furniture")).get("chair") or _d(mine.get("furniture_planned")).get("chair")
            if not has_chair:
                if (self.free_furn.get("chair") or 0) > 0:
                    room = next((s for s in self.sites if s.get("kind") in "RA" and s.get("z") == mine.get("z")), None)
                    room = room or next(iter(self.dug_rooms("office") + self.kind("A")), None)
                    if room:
                        self.act("office_chair", "place_furniture", {"kind": "chair", "site": room["id"]}, retry_days=2)
                elif not self.pending("make_chair") and self.logs():
                    self.act("o_chair_urgent", "add_order", {"recipe": "make_chair", "amount": 1}, retry_days=2)

    def build_ws(self, wtype, retry_days=3):
        sites = self.kind("W")
        if not sites or not self.material():
            return
        self.act("ws_" + wtype, "build_workshop", {"type": wtype, "site": sites[0]["id"]}, retry_days=retry_days)

    def step_workshops(self):
        """Construct essential workshops: Carpenters, Still, Kitchen."""
        have = {w.get("type") for w in _l(self.o.get("workshops")) if isinstance(w, dict)}
        for t in ("Carpenters", "Still", "Kitchen"):
            if t not in have and self.material():
                self.build_ws(t)

    def step_digging(self):
        """Dig stairs down into soil/rock, designate farm rooms, dorms, dining rooms."""
        rooms = self.kind("R")
        pending = self.o.get("dig_designations_pending") or 0
        stairs = self.kind("S")
        if stairs and self.surface is not None and (len(rooms) < 2 or (not any(r.get("soil") for r in rooms)
                                                                       and not self.o.get("farm_plots"))):
            self.act("stairs", "dig_stairs", {"site": stairs[-1]["id"], "z_bottom": self.surface - 4}, retry_days=10, limit=3)
        if pending > 80:
            return
        farm_cnt = len(_l(self.o.get("farm_plots"))) + sum(1 for v in self.roles.values() if v == "farm")
        for r in self.undug_rooms():
            rid = r["id"]
            if rid in self.roles:
                continue
            needs = [x for x in ("dorm", "dine", "office") if x not in self.roles.values()]
            if r.get("soil") and farm_cnt < self.farm_target():
                if self.act("dig_" + rid, "dig_room", {"site": rid}, retry_days=3, limit=2):
                    self.roles[rid] = "farm"
                    farm_cnt += 1
            elif needs:
                role = needs[0]
                size = {"dorm": {"w": 9, "h": 7}, "dine": {"w": 7, "h": 5}, "office": {"w": 3, "h": 3}}[role]
                if self.act("dig_" + rid, "dig_room", {"site": rid, **size}, retry_days=3, limit=2):
                    self.roles[rid] = role

    def step_farms(self):
        """Build farm plots on soil rooms or designated farm sites."""
        plots = _l(self.o.get("farm_plots"))
        target = self.farm_target()
        if len(plots) >= target:
            return
        cands = self.kind("F") + [r for r in self.dug_rooms() if r.get("soil") and self.roles.get(r["id"], "farm") == "farm"]
        seeds = _d(self.st.get("seeds_by_kind"))
        if any(not _d(v).get("underground") for v in seeds.values()):
            cands += self.kind("G")[:2]
        for s in cands[:target - len(plots)]:
            self.act("farm_" + s["id"], "build_farm", {"site": s["id"]}, retry_days=4, limit=3)

    def step_standing_orders(self):
        """Standing daily orders that run continuously even through hands-off windows."""
        if not self.standing("brew_drink"):
            self.act("o_brew", "add_order", {"recipe": "brew_drink", "amount": 3, "repeat": "daily", "when": [
                {"stock": "drink", "below": DRINK_CAP}, {"stock": "plants_brewable", "at_least": 2},
                {"stock": "barrels_empty", "at_least": 1}]}, retry_days=3)
        if not self.standing("make_barrel"):
            self.act("o_barrel", "add_order", {"recipe": "make_barrel", "amount": 2, "repeat": "daily", "when": [
                {"stock": "barrels_empty", "below": 6}, {"stock": "logs", "at_least": 2}]}, retry_days=3)
        if not self.standing("cook_meal"):
            self.act("o_cook", "add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily", "when": [
                {"stock": "prepared_meals", "below": MEAL_CAP}, {"stock": "plants_total", "at_least": 10}]}, retry_days=3)

        # Fallback fruit brewing if drink is low and plants are scarce
        plants = _d(self.st.get("plants_by_kind"))
        if (self.st.get("drink") or 0) < 3 * self.cit and not self.st.get("plants_brewable") and plants \
                and not self.pending("brew_drink_from_fruit"):
            self.act("o_fruit", "add_order", {"recipe": "brew_drink_from_fruit", "amount": 3}, retry_days=4)

        # Sized furniture orders for housing
        seats = math.ceil(self.cit / 2) + 2
        for recipe, have, want in (("make_bed", self.st.get("beds") or 0, self.cit + 3),
                                   ("make_table", self.st.get("tables") or 0, seats),
                                   ("make_chair", self.st.get("chairs") or 0, seats + 1)):
            if have < want and not self.pending(recipe) and self.logs():
                self.act("o_" + recipe, "add_order", {"recipe": recipe, "amount": min(6, want - have)}, retry_days=2, limit=99)

    def room_for(self, role):
        rooms = [r for r in self.kind("R") if self.roles.get(r["id"]) == role]
        for r in rooms:
            a = next((s for s in self.kind("A") if s.get("z") == r.get("z")), None)
            if a and role != "farm" and (r.get("dug") or a.get("open_tiles", 0) >= 6):
                return a
        dug = [r for r in rooms if r.get("dug")]
        if dug:
            return dug[0]
        taken = {r.get("z") for r in self.kind("R") if self.roles.get(r["id"], "").startswith("farm")}
        return next((s for s in self.kind("A") if s.get("z") not in taken), None)

    def step_housing(self):
        """Zone dormitory and dining hall, and place beds, tables, chairs to maximize s4."""
        dorm = self.room_for("dorm")
        dine = self.room_for("dine") or self.room_for("dorm")

        # Dormitory & Beds
        if dorm:
            if not self.zone_match("dorm") and not self.zone_match("bedroom"):
                self.act("z_dorm", "make_zone", {"kind": "dormitory", "site": dorm["id"]}, retry_days=3)
            short = self.cit + 2 - (self.placed.get("bed") or 0)
            n_beds = min(self.free_furn.get("bed") or 0, short, 15)
            if n_beds > 0:
                self.act("p_beds", "place_furniture", {"kind": "bed", "site": dorm["id"], "count": n_beds}, retry_days=1, limit=99)

        # Dining Hall & Seats (Table + Chair)
        if dine:
            if not self.zone_match("dining"):
                self.act("z_dine", "make_zone", {"kind": "dining_hall", "site": dine["id"]}, retry_days=3)
            want_seats = math.ceil(self.cit / 2) + 1
            for kind in ("table", "chair"):
                n = min(self.free_furn.get(kind) or 0, want_seats - (self.placed.get(kind) or 0), 10)
                if n > 0:
                    self.act("p_" + kind, "place_furniture", {"kind": kind, "site": dine["id"], "count": n}, retry_days=1, limit=99)

    def step_defense(self):
        """Peacetime squad reserve and shelter burrow; responsive alert on close hostiles."""
        mil = _d(self.o.get("military"))
        bur = _d(self.o.get("burrows"))
        th = _d(self.o.get("threats"))
        squads = _l(mil.get("squads"))
        squad = _d(squads[0]) if squads else None

        if not squad and self.cit >= 14:
            self.act("squad", "create_squad", {"size": 4}, retry_days=5, limit=3)
        if squad and squad.get("uniform") == "none":
            self.act("equip", "equip_squad", {"uniform": "leather"}, retry_days=5, limit=3)

        shelter = self.room_for("dorm")
        if shelter and not any(_d(b).get("civ_alert_burrow") for b in _l(bur.get("list"))):
            self.act("burrow", "create_burrow", {"site": shelter["id"]}, retry_days=5, limit=3)

        hostiles = th.get("visible_hostiles") or 0
        invaders = [h for h in _l(th.get("hostiles")) if _d(h).get("invader")]
        orders = _l((squad or {}).get("orders"))

        if hostiles and squad and (squad.get("armed") or 0) >= 1 and not orders:
            self.act("attack", "squad_order", {"order": "attack"}, retry_days=1, limit=99)
        if not hostiles and orders:
            self.act("stand_down", "squad_order", {"order": "stand_down"}, retry_days=1, limit=99)

        alert = bur.get("civilian_alert")
        dist = th.get("nearest_hostile_dist_to_wagon") or 10**6
        near = dist <= 45

        if invaders and near and not alert and any(_d(b).get("civ_alert_burrow") for b in _l(bur.get("list"))):
            if self.act("alert_on", "civilian_alert", {"on": True}, retry_days=15, limit=99):
                self.alert_since = self.now

        # Do not leave alert on indefinitely (starvation risk)
        too_long = self.alert_since is not None and (self.now - self.alert_since) > 10 * DAY
        if alert and (not invaders or too_long):
            self.act("alert_off", "civilian_alert", {"on": False}, retry_days=1, limit=99)
            self.alert_since = None

    def step(self, resp):
        """Execute one daily maintenance pass. Returns number of actions taken."""
        self.load(resp)
        self.count = 0
        try:
            self.step_mood()
            if self.count < MAX_ACTIONS_PER_DAY: self.step_defense()
            if self.count < MAX_ACTIONS_PER_DAY: self.step_management()
            if self.count < MAX_ACTIONS_PER_DAY: self.step_workshops()
            if self.count < MAX_ACTIONS_PER_DAY: self.step_digging()
            if self.count < MAX_ACTIONS_PER_DAY: self.step_farms()
            if self.count < MAX_ACTIONS_PER_DAY: self.step_standing_orders()
            if self.count < MAX_ACTIONS_PER_DAY: self.step_housing()
        except Exception:
            pass  # Ensure Caretaker never raises an unhandled error into the harness loop
        return self.count
