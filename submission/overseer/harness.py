"""Overseer: a deterministic Dwarf Fortress manager for game API v0. Reads facts, acts through the public tools only.

Order of work follows the score's gates: survive, supply, wellbeing, housing. Every step is idempotent and rate
limited, so a refused action is retried later rather than looped on. Makes no model calls.
Run: python -m overseer   (reads DFBENCH_TASK)

Lineage: the layer and its regular steps are e-man07's submission 6e775ed2 as repaired by GordoAR's 5dfdcf15 (main).
Two housing-measurement steps (seats counted inside dining zones, re-zoning loose furniture) come from e-man07's
efac22bf. This copy adds the "closer" steps (endgame supply mode for the scored final stretch, the pre-window boost on
lab tasks, a housing check sized to the window), a progression step for full-year games (the Hamlet rank's created
wealth, from wood crafts made only from surplus logs), a bed target sized for a migrant wave, an action report for the
model loop, and the ownership record the model-loop guard reads (owned orders).
"""
import json
import math
import sys
import time

from dfbench_client import ActionLimit, GameAPIError, GameClient, GameOver, HandsOff, load_task

DAY = 1200
MAX_PER_PASS = 12
MAX_PASSES = 3
DRINK_CAP = 300
MEAL_CAP = 200
ENDGAME_DAYS = 64       # closer: the scored final stretch is the last quarter of a long run, clipped to 28 days;
                        #   the supply slope over it must be >= 0, so production is raised a month before it starts
WINDOW_PREP_DAYS = 14   # closer: days before a lab task's hands-off window when its orders and beds are secured
REPORT_KEEP = 24        # action report lines kept for the model loop
WEALTH_TARGET = 5500    # progression: the Hamlet rank needs 20 citizens and 5000 created wealth (docs/SUCCESS.md)
PROGRESS_FROM_DAY = 40  # progression: crafts start once the core setup has had its logs
LOG_RESERVE = 25        # progression: crafts take logs only above this stock, so beds and barrels come first
LARGE_LIVESTOCK = frozenset(("DONKEY", "MULE", "HORSE", "COW", "YAK", "WATER_BUFFALO", "MUSKOX", "LLAMA",
                             "CAMEL_1_HUMP", "CAMEL_2_HUMP"))
MOOD_WORKSHOP = {
    "WOODCRAFT": "Craftsdwarfs", "STONECRAFT": "Craftsdwarfs", "BONECARVE": "Craftsdwarfs", "CARPENTRY": "Carpenters",
    "MASONRY": "Masons", "WOOD_BURNING": "WoodFurnace", "GLASSMAKER": "GlassFurnace", "TANNER": "Leatherworks",
    "LEATHERWORK": "Leatherworks", "WEAVING": "Loom", "CLOTHESMAKING": "Clothiers", "FORGE_WEAPON": "MetalsmithsForge",
    "FORGE_ARMOR": "MetalsmithsForge", "FORGE_FURNITURE": "MetalsmithsForge", "METALCRAFT": "MetalsmithsForge",
    "CUTGEM": "Jewelers", "ENCRUSTGEM": "Jewelers", "MECHANICS": "Mechanics", "POTTERY": "Kiln", "BOWYER": "Bowyers",
}


def log(kind, **kw):
    print(json.dumps({"t": round(time.time(), 2), "kind": kind, **kw}, default=str), flush=True)


def d(v):
    return v if isinstance(v, dict) else {}


def lst(v):
    return v if isinstance(v, list) else []


def covers(area, item):
    return (area["z"] == item["z"] and area["x"] <= item["x"] and area["y"] <= item["y"]
            and area["x"] + area["w"] >= item["x"] + item.get("w", 1)
            and area["y"] + area["h"] >= item["y"] + item.get("h", 1))


class Overseer:
    def __init__(self, game, goal="", days=0):
        self.game = game
        self.surge = "migrant" in str(goal).lower()   # the task's own text says more dwarves are on the way
        self.drink_growth = "drink must not end lower" in str(goal).lower()
        self.initial_citizens = None
        self.days = days or 0
        self.tries, self.last = {}, {}
        self.roles = {}          # room id -> farm | dorm | dine | office
        self.brew_orders = set()
        self.now = 0
        self.alert_since = None
        self.hands_off = None
        self.days_left = None
        self.logging_hold = False
        self.logging_scan_day = None
        self.day = None
        self.progress_orders = set()
        self.office_recoveries = 0
        self.workshop_stalls = {}
        self.workshop_replacements = {}
        self.owned = set()       # order ids this layer added: the model loop refuses to cancel them
        self.report = []         # the layer's recent actions (day, tool, args, outcome), for the model loop
        self.done = set()        # closer keys whose order was accepted once: never re-added

    # ---- the action gate
    def may(self, key, retry=2, limit=6):
        return self.tries.get(key, 0) < limit and self.now - self.last.get(key, -10 ** 9) >= retry * DAY

    def act(self, key, tool, args, retry=2, limit=6):
        """One rate-limited action. Returns the response if it ran, else None."""
        if key in self.done or not self.may(key, retry, limit):
            return None
        self.tries[key] = self.tries.get(key, 0) + 1
        self.last[key] = self.now
        r = self.game.act(tool, args)
        self.count += 1
        log("act", key=key, tool=tool, args=args, ok=r.get("ok"), code=r.get("error_code"),
            err=str(r.get("error") or "")[:160])
        if r.get("ok"):
            self.tries[key] = max(0, self.tries[key] - 1)
            if tool == "add_order" and args.get("recipe") == "brew_drink" and args.get("repeat") == "daily":
                order_id = d(r.get("result")).get("order_id")
                if type(order_id) is int:
                    self.brew_orders.add(order_id)
        if r.get("ok") and tool in ("add_order", "add_manager_order"):
            res = r.get("result") if isinstance(r.get("result"), dict) else r
            if res.get("order_id") is not None:
                self.owned.add(res.get("order_id"))
                if key == "o_crafts_prog":
                    self.progress_orders.add(res["order_id"])
            if args.get("repeat") and key.startswith("o_") and key.endswith(("_end", "_win", "_prog")):
                self.done.add(key)   # a standing closer or progression order is added once per game
        self.report = (self.report + [{"day": self.day, "tool": tool, "args": args, "ok": bool(r.get("ok")),
                                       **({"error_code": r.get("error_code"), "error": str(r.get("error") or "")[:100]}
                                          if not r.get("ok") else {})}])[-REPORT_KEEP:]
        return r

    # ---- facts
    def load(self, resp):
        self.o = d(resp.get("observation"))
        self.st, self.map = d(self.o.get("stocks")), d(self.o.get("map"))
        self.adm = d(self.o.get("administrators"))
        self.hands_off = resp.get("hands_off_in_days")
        self.days_left = resp.get("days_left") if isinstance(resp.get("days_left"), int) else None
        self.day = resp.get("day")
        self.now = d(self.o.get("date")).get("abs_tick") or resp.get("tick") or 0
        self.people = [x for x in lst(self.o.get("dwarves")) if isinstance(x, dict)]
        self.cit = self.adm.get("citizens") or len(self.people)
        if self.initial_citizens is None and type(self.cit) is int and self.cit > 0:
            self.initial_citizens = self.cit
        self.sites = [s for s in lst(self.map.get("sites")) if isinstance(s, dict)]
        self.orders = [x for x in lst(self.o.get("orders")) if isinstance(x, dict)]
        if isinstance(self.o.get("orders"), list):
            self.brew_orders.intersection_update(x.get("id") for x in self.orders)
            self.progress_orders.intersection_update(x.get("id") for x in self.orders)
            self.owned.intersection_update(x.get("id") for x in self.orders)   # a removed order is nobody's
        self.zones = [z for z in lst(self.o.get("zones")) if isinstance(z, dict)]
        self.free = d(self.st.get("furniture_free"))
        self.placed = {}
        for f in lst(self.o.get("furniture")):
            if isinstance(f, dict):
                self.placed[f.get("kind")] = self.placed.get(f.get("kind"), 0) + 1
        self.surface = self.map.get("surface_z")

    def kind(self, k):
        return [s for s in self.sites if s.get("kind") == k]

    def pending(self, recipe):
        return any(x.get("recipe") == recipe and (x.get("left") or 0) > 0 for x in self.orders)

    def standing(self, recipe):
        return any(x.get("recipe") == recipe and x.get("repeat") for x in self.orders)

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

    # ---- the work, most urgent first
    def plan(self):
        self.mood()
        self.defend()
        self.management()
        self.workshops()
        self.digging()
        self.farms()
        self.supply()
        self.furnish()
        self.rezone()
        self.progress()
        self.closer()

    def scan_logging_risk(self):
        """Wait briefly before sending woodcutters past a served visible alligator."""
        if (self.days < 336 or self.surge or type(self.day) is not int or self.day >= 56
                or d(self.o.get("plugins")).get("autochop") == "on"
                or self.cit <= 0 or (self.st.get("food_edible") or 0) < 2 * self.cit
                or (self.st.get("drink") or 0) < 4 * self.cit):
            self.logging_hold = False
            return
        if self.logging_scan_day == self.day:
            return
        self.logging_scan_day = self.day
        try:
            q = self.game.query("units", kind="others", limit=300)
            others = lst(d(q.get("result")).get("units"))
            predators = [u for u in others if isinstance(u, dict) and u.get("race") == "ALLIGATOR"
                         and not u.get("visitor")]
            self.logging_hold = bool(predators)
            log("logging_wildlife_scan", day=self.day, held=self.logging_hold, visible_predators=predators)
        except Exception as exc:
            self.logging_hold = False
            log("logging_wildlife_query_error", error=type(exc).__name__)

    def management(self):
        if not self.adm.get("manager_active_for_orders"):
            free = [p for p in self.people if not p.get("positions") and p.get("adult", True)]
            free.sort(key=lambda p: -(p.get("organizer_skill") or 0))
            self.act("manager", "appoint_manager", {"dwarf_id": free[0]["id"]} if free else {}, retry=1, limit=8)
        self.scan_logging_risk()
        plugins = d(self.o.get("plugins"))
        for name in ("autochop", "seedwatch"):
            if name == "autochop" and self.logging_hold:
                continue
            if plugins.get(name) != "on":
                self.act("plug_" + name, "enable_automation", {"name": name}, retry=5)
        if self.o.get("farm_plots") and plugins.get("autofarm") != "on":
            self.act("plug_autofarm", "enable_automation", {"name": "autofarm"}, retry=5)
        self.office()

    def office(self):
        """DF stops validating orders around 20 citizens unless the manager has an office with a chair."""
        if self.cit < 14 or not self.adm.get("manager_active_for_orders"):
            return
        mo = self.adm.get("manager_office")
        if isinstance(mo, dict) and mo.get("chair"):
            return
        mgr = self.adm.get("MANAGER_id")
        offices = self.zone("office")
        # An empty office cannot approve the order for its own missing chair.
        # Reuse a built chair through a bounded observed site instead.
        ready = next((z for z in offices if z.get("owner") in (None, mgr)
                      and d(z.get("furniture")).get("chair")), None)
        if ready and mgr is not None:
            self.act("office_ready_assign", "assign_zone", {"zone_id": ready["id"], "dwarf_id": mgr})
            return
        pending_chair = any(z.get("owner") in (None, mgr)
                            and d(z.get("furniture_planned")).get("chair") for z in offices)
        if mgr is not None and not pending_chair and self.office_recoveries < 2:
            chairs = [f for f in lst(self.o.get("furniture"))
                      if isinstance(f, dict) and f.get("kind") == "chair" and f.get("built") is True]
            sites = [a for a in self.kind("A")
                     if 0 < (a.get("w") or 0) <= 20 and 0 < (a.get("h") or 0) <= 20
                     and any(covers(a, f) for f in chairs)
                     and not any(d(f).get("z") == a.get("z") for f in lst(self.o.get("farm_plots")))]
            if sites:
                result = self.act("office_recover_zone", "make_zone",
                                  {"kind": "office", "site": sites[0]["id"]}, retry=3, limit=4)
                if result and result.get("ok"):
                    self.office_recoveries += 1
                    zone_id = d(result.get("result")).get("zone_id")
                    if type(zone_id) is int:
                        self.act("office_recover_assign", "assign_zone",
                                 {"zone_id": zone_id, "dwarf_id": mgr}, retry=1)
                return
        mine = next((z for z in offices if mgr is not None and z.get("owner") == mgr), None)
        if not mine:
            spare = next((z for z in offices if z.get("owner") is None), None)
            if spare and mgr is not None:
                self.act("office_assign", "assign_zone", {"zone_id": spare["id"], "dwarf_id": mgr})
                return
            room = next(iter(self.dug_rooms("office") + self.dug_rooms("dine") + self.kind("A")), None)
            if room:
                result = self.act("office_zone", "make_zone", {"kind": "office", "site": room["id"]})
                if result and result.get("ok") and (self.free.get("chair") or 0) > 0:
                    self.act("office_chair", "place_furniture", {"kind": "chair", "site": room["id"]})
            return
        if d(mine.get("furniture")).get("chair") or d(mine.get("furniture_planned")).get("chair"):
            return
        if (self.free.get("chair") or 0) > 0:
            room = next((s for s in self.sites if s.get("kind") in "RA" and s.get("z") == mine.get("z")
                         and s.get("x") == mine.get("x") and s.get("y") == mine.get("y")), None)
            room = room or next(iter(self.dug_rooms("office") + self.kind("A")), None)
            if room:
                self.act("office_chair", "place_furniture", {"kind": "chair", "site": room["id"]})

    def build(self, wtype, retry=3):
        sites = self.kind("W")
        if not sites or not self.material():
            return
        result = self.act("ws_" + wtype, "build_workshop", {"type": wtype, "site": sites[0]["id"]}, retry=retry)
        if result and result.get("ok"):
            self.sites.remove(sites[0])
        return result

    def ensure_workshop(self, wtype):
        existing = [w for w in lst(self.o.get("workshops"))
                    if isinstance(w, dict) and w.get("type") == wtype]
        if not existing:
            self.workshop_stalls.pop(wtype, None)
            self.build(wtype)
            return
        def suspended(w):
            jobs = [j for j in lst(w.get("job_details"))
                    if isinstance(j, dict) and j.get("job") == "ConstructBuilding"]
            return w.get("built") is False and jobs and all(j.get("suspended") is True for j in jobs)
        if not all(suspended(w) for w in existing):
            self.workshop_stalls.pop(wtype, None)
            return
        since = self.workshop_stalls.setdefault(wtype, self.now)
        # A normal pending construction gets time to complete; only explicit suspension qualifies.
        if self.now - since < 7 * DAY or self.workshop_replacements.get(wtype, 0) >= 2:
            return
        result = self.build(wtype)
        if result and result.get("ok"):
            self.workshop_replacements[wtype] = self.workshop_replacements.get(wtype, 0) + 1
            self.workshop_stalls[wtype] = self.now

    def workshops(self):
        for t in ("Carpenters", "Still", "Kitchen"):
            self.ensure_workshop(t)
        if any(p.get("job") == "Fish" for p in self.people):
            self.ensure_workshop("Fishery")

    def bed_target(self):
        """Beds per citizen is read at the horizon; a migrant task's wave is bigger than the fort's bed stock."""
        if self.surge:
            forecast = min(90, 3 * (self.initial_citizens or self.cit))
            return max(self.cit + 12, forecast)
        return self.cit + 3

    def farm_target(self):
        return max(4, min(10, math.ceil(self.cit / 5)))

    def stair_site(self, stairs):
        """Prefer distance from observed liquid/brook tiles; unknown map cells supply no facts."""
        fallback = stairs[-1]
        if self.days < 336 or self.surge:
            return fallback
        candidates = [s for s in stairs if type(s.get("x")) is int and type(s.get("y")) is int]
        if len(candidates) < 2 or type(self.surface) is not int:
            return fallback
        cx = (min(s["x"] for s in candidates) + max(s["x"] for s in candidates)) // 2
        cy = (min(s["y"] for s in candidates) + max(s["y"] for s in candidates)) // 2
        extent = max(max(abs(s["x"] - cx), abs(s["y"] - cy)) for s in candidates)
        # Include the existing 9x7 room footprint around every candidate, within the API bound.
        radius = min(20, max(12, extent + 10))
        try:
            result = d(self.game.query("map", x=cx, y=cy, z=self.surface,
                                       z2=max(0, self.surface - 1), radius=radius).get("result"))
        except Exception as exc:
            log("stairs_water_query_error", error=type(exc).__name__)
            return fallback
        water = {(v["x"], v["y"]) for v in lst(result.get("liquid"))
                 if isinstance(v, dict) and type(v.get("x")) is int and type(v.get("y")) is int
                 and type(v.get("depth")) is int and v["depth"] > 0}
        # Brooks can be walkable at the surface while water lies directly below them.
        x1, y1 = result.get("x1"), result.get("y1")
        if type(x1) is int and type(y1) is int:
            for level in lst(result.get("levels")):
                if not isinstance(level, dict):
                    continue
                shapes, materials = lst(level.get("shape")), lst(level.get("material"))
                for iy, row in enumerate(shapes):
                    if not isinstance(row, str):
                        continue
                    mat = materials[iy] if iy < len(materials) and isinstance(materials[iy], str) else ""
                    for ix, tile in enumerate(row):
                        if tile in ("~", "_") or (ix < len(mat) and mat[ix] in ("k", "R", "o", "i")):
                            water.add((x1 + ix, y1 + iy))
        if not water:
            return fallback
        def distance(site):
            return min((site["x"] - x) ** 2 + (site["y"] - y) ** 2 for x, y in water)
        # Preserve the previous last-site tie break when the observed distances agree.
        chosen = max(enumerate(candidates), key=lambda pair: (distance(pair[1]), pair[0]))[1]
        log("stairs_water_choice", site=chosen["id"], distance2=distance(chosen), known_water=len(water))
        return chosen

    def digging(self):
        rooms = self.kind("R")
        pending = self.o.get("dig_designations_pending") or 0
        stairs = self.kind("S")
        if stairs and self.surface is not None and (len(rooms) < 2 or (not any(r.get("soil") for r in rooms)
                                                                       and not self.o.get("farm_plots"))) and self.may("stairs", 12, 3):
            site = self.stair_site(stairs)
            self.act("stairs", "dig_stairs", {"site": site["id"], "z_bottom": self.surface - 4}, retry=12, limit=3)
        if pending > 90:
            return
        farms = len(lst(self.o.get("farm_plots"))) + sum(1 for r, v in self.roles.items() if v == "farm" and not any(z.get("id") == r and z.get("used_by") for z in self.kind("R")))
        for r in self.undug_rooms():
            rid = r["id"]
            if rid in self.roles:
                continue
            need = [x for x in ("dorm", "dine", "office") if x not in self.roles.values()]
            if not need and self.surge and farms >= 4 and self.placed.get("bed", 0) < self.cit:
                need = ["dorm"]   # a larger wave needs more floor, not only more bed items
            # Ordinary full-year forts keep farms first, placing housing after those crop rooms.
            # Shorter tasks and migrant goals reserve housing after two plots.
            if r.get("soil") and farms < self.farm_target() and (farms < 2 or not need or (self.days >= 336 and not self.surge)):
                result = self.act("dig_" + rid, "dig_room", {"site": rid}, retry=3, limit=2)
                if result and result.get("ok"):
                    self.roles[rid] = "farm"
                    farms += 1
            elif need:
                role = need[0]
                # Short ordinary rescues need crop levels to remain available: a
                # large housing zone on the other side also consumes the farm room.
                if self.days < 336 and not self.surge and any(
                        other.get("z") == r.get("z") and self.roles.get(other["id"]) == "farm"
                        for other in rooms):
                    continue
                dining_size = {"w": 3, "h": 3} if self.surge else {"w": 7, "h": 5}
                size = {"dorm": {"w": 9, "h": 7}, "dine": dining_size, "office": {}}[role]
                result = self.act("dig_" + rid, "dig_room", {"site": rid, **size}, retry=3, limit=2)
                if result and result.get("ok"):
                    self.roles[rid] = role

    def farms(self):
        plots = lst(self.o.get("farm_plots"))
        target = self.farm_target()
        if len(plots) >= target:
            return
        housing_levels = {r.get("z") for r in self.kind("R")
                          if self.roles.get(r["id"]) in ("dorm", "dine", "office")}
        cands = [s for s in self.kind("F") if s.get("z") not in housing_levels] + [
            r for r in self.dug_rooms() if r.get("soil") and self.roles.get(r["id"], "farm") == "farm"]
        seeds = d(self.st.get("seeds_by_kind"))
        if any(not d(v).get("underground") for v in seeds.values()):
            cands += self.kind("G")[:2]
        for s in cands[:target - len(plots)]:
            self.act("farm_" + s["id"], "build_farm", {"site": s["id"]}, retry=4, limit=3)

    def supply(self):
        """Standing orders that keep working in a hands-off window, then one-shot furniture sized to the population."""
        if not self.standing("brew_drink"):
            # Keep the ordinary reserve even when the higher food-protected tier is dormant.
            ordinary_cap = max(600, 30 * self.cit) if self.days >= 336 and not self.surge and not self.drink_growth \
                and self.hands_off is None else DRINK_CAP
            ceiling = [] if self.drink_growth and isinstance(self.hands_off, int) else [
                {"stock": "drink", "below": ordinary_cap}]
            self.act("o_brew", "add_order", {"recipe": "brew_drink", "amount": 3, "repeat": "daily", "when": ceiling + [
                {"stock": "plants_brewable", "at_least": 2},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=3)
        if self.days >= 336 and not self.drink_growth:
            # Food-gated reserve tiers adapted from peer58a2d2ae's published endgame policy.
            # The native brewing recipe requires a plant; three explicit conditions fit the API.
            self.act("o_brew_surplus_end", "add_order", {"recipe": "brew_drink", "amount": 3,
                     "repeat": "daily", "when": [
                         {"stock": "drink", "below": max(600, 30 * self.cit)},
                         {"stock": "food_edible", "at_least": max(150, 12 * self.cit)},
                         {"stock": "barrels_empty", "at_least": 1}]}, retry=3, limit=4)
        if not self.standing("make_barrel"):
            self.act("o_barrel", "add_order", {"recipe": "make_barrel", "amount": 2, "repeat": "daily", "when": [
                {"stock": "barrels_empty", "below": 4}, {"stock": "logs", "at_least": 2}]}, retry=3)
        if not self.standing("cook_meal"):
            self.act("o_cook", "add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily", "when": [
                {"stock": "prepared_meals", "below": MEAL_CAP}, {"stock": "plants_total", "at_least": 10}]}, retry=3)
        if not self.surge and (self.days >= 336 or (self.days >= 216 and self.hands_off is None)):
            # Preserve fresh processed fish in full-year and ordinary handover tasks.
            self.act("o_cook_fish_end", "add_manager_order", {
                "job": "PrepareMeal", "amount": 2, "repeat": "daily", "when": [
                    {"item_type": "FISH", "flags": ["unrotten", "cookable"], "at_least": 2},
                    {"item_type": "FOOD", "flags": ["unrotten"], "below": MEAL_CAP}]}, retry=3, limit=4)
        plants = d(self.st.get("plants_by_kind"))
        if (self.st.get("drink") or 0) < 3 * self.cit and not self.st.get("plants_brewable") and plants \
                and not self.pending("brew_drink_from_fruit"):
            self.act("o_fruit", "add_order", {"recipe": "brew_drink_from_fruit", "amount": 3}, retry=4)
        food = self.st.get("food_edible")
        if type(food) is int and self.cit > 0 and food < 2 * self.cit:
            self.butcher(prefer_food=True)
        seats = math.ceil(self.cit / 2) + 2
        for recipe, have, want in (("make_bed", self.st.get("beds") or 0, self.bed_target()),
                                   ("make_table", min(self.seats(), self.dining_items("table")) + (self.free.get("table") or 0), seats),
                                   ("make_chair", min(self.seats(), self.dining_items("chair")) + (self.free.get("chair") or 0), seats + 1)):
            if self.surge and recipe != "make_bed" and self.placed.get("bed", 0) < self.cit:
                continue
            if have < want and not self.pending(recipe) and self.logs():
                batch = 30 if self.surge and recipe == "make_bed" else 8
                result = self.act("o_" + recipe, "add_order",
                                  {"recipe": recipe, "amount": min(batch, want - have)}, retry=1, limit=99)
                if self.surge and recipe == "make_bed" and want - have > 30 and result and result.get("ok"):
                    # Queue the remaining reserve now, while the manager can approve both batches together.
                    self.act("o_bed_prequeue", "add_order",
                             {"recipe": recipe, "amount": min(30, want - have - 30)}, retry=1, limit=99)

    # ---- the closer: what the score reads at the end of the run
    def in_endgame(self):
        """Open-play tasks: the scored final stretch (the last quarter of the run, 7-28 days) is near."""
        return self.hands_off is None and self.days_left is not None and self.days_left <= ENDGAME_DAYS

    def in_window_prep(self):
        """Lab tasks: the hands-off window starts soon; after it begins only standing orders keep working."""
        return isinstance(self.hands_off, int) and 0 < self.hands_off <= WINDOW_PREP_DAYS

    def closer(self):
        if self.in_endgame():
            self.endgame_supply()
            self.housing_check()
        elif self.in_window_prep():
            self.window_supply()
            self.housing_check()
        if self.surge:
            carp = sum(1 for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Carpenters")
            target = max(2, min(4, math.ceil(self.cit / 15)))
            if carp < target and self.cit >= 15 and self.logs() >= 5:
                self.build("Carpenters", retry=3)   # scale capacity with the migrant wave, not only the queue

    def endgame_supply(self):
        """The supply sub-score credits a stock by its projected days left: a draining stock is credited only as far
        as it lasts, and a flat or rising one in full. From ENDGAME_DAYS before the horizon, a second brew order with a
        cap well above the usual one keeps drink rising through the final stretch (while plants stay above a reserve
        that protects the food count, since plants are food too), and cooking keeps meals rising from surplus food.
        Meat is added when edible food is short of a few days per citizen."""
        cap = max(600, 30 * self.cit)
        if self.days >= 336:
            # Preserve a food-independent emergency tier as population grows (peer58a2d2ae).
            self.act("o_brew_emergency_end", "add_order", {"recipe": "brew_drink", "amount": 4,
                     "repeat": "daily", "when": [
                         {"stock": "drink", "below": 12 * self.cit},
                         {"stock": "plants_brewable", "at_least": 2},
                         {"stock": "barrels_empty", "at_least": 1}]}, retry=3, limit=4)
        reserve = max(12, self.cit)
        reserve_gate = {"stock": "food_edible", "at_least": max(150, 12 * self.cit)} if self.days >= 336 else \
            {"stock": "plants_brewable", "at_least": reserve}
        self.act("o_brew_end", "add_order", {"recipe": "brew_drink", "amount": 4, "repeat": "daily", "when": [
            {"stock": "drink", "below": cap}, reserve_gate,
            {"stock": "barrels_empty", "at_least": 1}]}, retry=3, limit=4)
        self.act("o_barrel_end", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 8}, {"stock": "logs", "at_least": 4}]}, retry=3, limit=4)
        self.act("o_cook_end", "add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily", "when": [
            {"stock": "prepared_meals", "below": max(300, 10 * self.cit)},
            {"stock": "food_edible", "at_least": max(30, 4 * self.cit)}]}, retry=3, limit=4)
        food = self.st.get("food_edible") or 0
        if food < 4 * self.cit:
            self.butcher(prefer_food=True)
        elif self.days >= 336 and food < 12 * self.cit:
            # A positive stock can still have less than a year's food runway.
            # Build the late reserve from adult livestock, preserving small animals.
            self.butcher(prefer_food=True, large_only=True)

    def window_supply(self):
        """Before a hands-off window: brew whenever a plant and a barrel allow, at a cap the window can't reach, so
        drink keeps rising while nobody can act (LT08 wants drink at the end above drink at the window's start;
        LT01 wants a batch brewed inside it). Plants are food too, and food must also hold through the window, so
        half a plant per citizen stays unbrewed. Barrels are the usual limit: an extra barrel order runs alongside."""
        self.act("o_brew_win", "add_order", {"recipe": "brew_drink", "amount": 5, "repeat": "daily", "when": [
            {"stock": "drink", "below": 2000}, {"stock": "plants_brewable", "at_least": max(3, self.cit // 2)},
            {"stock": "barrels_empty", "at_least": 1}]}, retry=2, limit=5)
        self.act("o_barrel_win", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 10}, {"stock": "logs", "at_least": 3}]}, retry=2, limit=5)
        if (self.st.get("food_edible") or 0) < 4 * self.cit:
            self.butcher(prefer_food=True)

    def ordered_now(self, key):
        """The regular supply step already ran this key in this pass (the observation's order list is stale then)."""
        return self.last.get(key) == self.now

    def housing_check(self):
        """Housing is read at the horizon: placed (built) beds per citizen and seats inside dining zones per two
        citizens. Near the end, order the shortfall at once (a built bed needs the item, a carpenter and an installer)
        and place whatever is free; the regular furnish step then zones it."""
        beds_short = self.cit - (self.placed.get("bed") or 0)
        if beds_short > 0 and (self.st.get("beds") or 0) < self.cit + 2 and self.logs() >= 2 \
                and not self.pending("make_bed") and not self.ordered_now("o_make_bed"):
            self.act("o_bed_close", "add_order", {"recipe": "make_bed", "amount": min(30, max(2, beds_short + 2))},
                     retry=2, limit=10)
        if self.surge and beds_short > 0:
            return   # a migrant task is scored on beds, not seats: the carpenters' queue stays with the beds
        seats_short = math.ceil(self.cit / 2) - self.seats()
        if seats_short > 0 and self.logs() >= 2:
            for recipe, have in (("make_table", self.st.get("tables") or 0), ("make_chair", self.st.get("chairs") or 0)):
                want = math.ceil(self.cit / 2) + 1
                if have < want and not self.pending(recipe) and not self.ordered_now("o_" + recipe):
                    self.act("o_%s_close" % recipe, "add_order", {"recipe": recipe, "amount": min(30, want - have)},
                             retry=2, limit=10)

    def seats(self):
        """Seats as the score counts them: tables and chairs inside dining zones."""
        n = 0
        for z in self.zone("dining"):
            f = d(z.get("furniture"))
            n += min(f.get("table") or 0, f.get("chair") or 0)
        return n

    def rezone(self):
        """Only furniture inside a zone counts or gets used. Zone each level's loose built tables, chairs and beds, and
        put a dining zone over a level whose tables and chairs sit in no dining zone (a dormitory's seats earn nothing)."""
        loose, by_z = {}, {}
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
            site = next((x for x in self.kind("A") if x.get("z") == z and (x.get("w") or 0) <= 20 and (x.get("h") or 0) <= 20), None)
            if not site:
                site = next((x for x in self.dug_rooms() if x.get("z") == z), None)
            if not site:
                continue
            if kinds & {"table", "chair"}:
                self.act("rz_dine_%s" % site["id"], "make_zone", {"kind": "dining_hall", "site": site["id"]}, retry=2, limit=3)
            if "bed" in kinds:
                self.act("rz_dorm_%s" % site["id"], "make_zone", {"kind": "dormitory", "site": site["id"]}, retry=2, limit=3)
        for z, kinds in by_z.items():
            if kinds.get("table") and kinds.get("chair"):
                site = next((x for x in self.kind("A") if x.get("z") == z and (x.get("open_tiles") or 0) >= 6
                             and (x.get("w") or 0) <= 20 and (x.get("h") or 0) <= 20), None)
                if site:
                    self.act("dx_dine_%s" % site["id"], "make_zone", {"kind": "dining_hall", "site": site["id"]}, retry=3, limit=2)

    def progress(self):
        """Full-year games only. The growth gate on a 336-day horizon also needs a DF progression step, and the only
        one in reach is the Hamlet rank: 20 citizens and 5000 created wealth. Citizens come with the year's migrant
        waves; wealth is made. Wood crafts are the cheapest wealth per log (several crafts from one log), so from
        PROGRESS_FROM_DAY a Craftsdwarfs is built and one standing order makes crafts whenever logs are above a
        reserve that keeps beds, barrels and seats first. It stops once the wealth is there."""
        if self.days < 336 or (self.day or 0) < PROGRESS_FROM_DAY or self.cit < 7:
            return
        if (d(self.o.get("wealth")).get("created") or 0) >= WEALTH_TARGET:
            for oid in sorted(self.progress_orders):
                self.act("stop_crafts_%s" % oid, "cancel_order", {"order_id": oid}, retry=3, limit=4)
            return
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        if "Craftsdwarfs" not in have:
            self.build("Craftsdwarfs", retry=5)
            return
        if not any(x.get("job") == "MakeCrafts" and x.get("repeat") for x in self.orders):
            self.act("o_crafts_prog", "add_manager_order", {"job": "MakeCrafts", "amount": 3, "repeat": "daily",
                     "material_category": ["wood"], "when": [{"item_type": "WOOD", "at_least": LOG_RESERVE}]},
                     retry=4, limit=6)

    def room_for(self, role):
        """The dug level of a role's big room (its A site covers the whole dig), else the room itself."""
        rooms = [r for r in self.kind("R") if self.roles.get(r["id"]) == role]
        for r in rooms:
            a = next((s for s in self.kind("A") if s.get("z") == r.get("z")), None)
            if a and role != "farm" and (r.get("dug") or a.get("open_tiles", 0) >= 6):
                return a
        dug = [r for r in rooms if r.get("dug")]
        if dug:
            return dug[0]
        taken = {r.get("z") for r in self.kind("R") if self.roles.get(r["id"], "").startswith("farm")}
        return next((s for s in self.kind("A") if s.get("z") not in taken and s.get("open_tiles", 0) >= 6), None)

    def needs_zone(self, room, zones, kinds, placed=()):
        if any(covers(z, room) for z in zones):
            return False
        return any(f.get("kind") in kinds and covers(room, f)
                   and not any(covers(z, f) for z in zones)
                   for f in lst(self.o.get("furniture")) + list(placed))

    def place(self, key, kind, room, count):
        result = d(self.act(key, "place_furniture", {"kind": kind, "site": room["id"], "count": count},
                            retry=1, limit=99))
        if kind == "bed" and result.get("error_code") == "no_space":
            # A full dorm must not strand available beds. The API checks actual
            # indoor floor capacity in each alternative; occupied farms stay intact.
            # The alternative-site strategy is described by a9f894e / 5ef22a35.
            alternatives = sorted((s for s in self.kind("A")
                                   if s.get("z") != room.get("z") and s.get("open_tiles", 0) >= 6),
                                  key=lambda s: -s.get("open_tiles", 0))
            for site in alternatives[:2]:
                result = d(self.act(key + "_" + site["id"], "place_furniture",
                                   {"kind": kind, "site": site["id"], "count": count}, retry=1, limit=99))
                if result.get("ok"):
                    if not any(covers(z, site) for z in self.zone("dorm") + self.zone("bedroom")):
                        self.act("z_extra_" + site["id"], "make_zone",
                                 {"kind": "dormitory", "site": site["id"]}, retry=3)
                    break
        if not result.get("ok"):
            return []
        points = d(result.get("result")).get("at") or []
        if points and not isinstance(points[0], list):
            points = [points]
        return [{"kind": kind, "x": x, "y": y, "z": z} for x, y, z in points]

    def dining_items(self, kind):
        """Count each observed item once, only if it is inside a dining zone."""
        zones = self.zone("dining")
        return sum(1 for f in lst(self.o.get("furniture"))
                   if isinstance(f, dict) and f.get("kind") == kind
                   and any(covers(z, f) for z in zones))

    def dining_sites(self, preferred):
        """The zone API accepts boxes up to 20x20. Keep placement on bounded observed sites."""
        def usable(site):
            return site and 0 < (site.get("w") or 0) <= 20 and 0 < (site.get("h") or 0) <= 20
        farm_z = {r.get("z") for r in self.kind("R") if self.roles.get(r["id"]) == "farm"}
        candidates = ([preferred] if usable(preferred) else [])
        candidates += [r for r in self.kind("R") if r.get("dug") and usable(r)
                       and self.roles.get(r["id"]) != "farm"
                       and not any("farm" in str(x).lower() for x in lst(r.get("used_by")))]
        candidates += [a for a in self.kind("A") if usable(a) and a.get("open_tiles", 0) >= 6
                       and a.get("z") not in farm_z]
        result, seen = [], set()
        for site in candidates:
            if site["id"] not in seen:
                result.append(site); seen.add(site["id"])
        return result

    def furnish(self):
        dorm, dine = self.room_for("dorm"), self.room_for("dine") or self.room_for("dorm")
        if dorm:
            short = self.cit + 2 - (self.placed.get("bed") or 0)
            n = min(self.free.get("bed") or 0, short, 30)
            placed = self.place("beds", "bed", dorm, n) if n > 0 else []
            if self.needs_zone(dorm, self.zone("dorm") + self.zone("bedroom"), ("bed",), placed):
                self.act("z_dorm", "make_zone", {"kind": "dormitory", "site": dorm["id"]}, retry=3)
        dining_sites = self.dining_sites(dine)
        if dining_sites and not (self.surge and self.placed.get("bed", 0) < self.cit):
            want = math.ceil(self.cit / 2) + 1
            for kind in ("table", "chair"):
                n = min(self.free.get(kind) or 0, want - self.seats(), 15)
                if n <= 0:
                    continue
                attempts = 0
                for site in dining_sites:
                    if attempts >= 3:
                        break
                    counts = {k: sum(1 for f in lst(self.o.get("furniture"))
                                     if isinstance(f, dict) and f.get("kind") == k and covers(site, f))
                              for k in ("table", "chair")}
                    other = "chair" if kind == "table" else "table"
                    # Fill existing unmatched furniture before adding another unmatched set.
                    count = min(self.free.get(kind) or 0, 15,
                                max(0, want - self.seats() + counts[other] - counts[kind]))
                    if site.get("kind") == "R":
                        count = min(count, max(0, site["w"] * site["h"] // 2 - counts[kind]))
                    if count <= 0:
                        continue
                    attempts += 1
                    placed = self.place("f_%s_%s" % (kind, site["id"]), kind, site, count)
                    if placed:
                        if self.needs_zone(site, self.zone("dining"), ("table", "chair"), placed):
                            self.act("z_dine_" + site["id"], "make_zone",
                                     {"kind": "dining_hall", "site": site["id"]}, retry=3)
                        break
                    if not self.report or self.report[-1].get("error_code") != "no_space":
                        break
            # Furniture may already be present on the selected floor before this pass.
            dine = dining_sites[0]
            if self.needs_zone(dine, self.zone("dining"), ("table", "chair")):
                self.act("z_dine_" + dine["id"], "make_zone",
                         {"kind": "dining_hall", "site": dine["id"]}, retry=3)

    def mood(self):
        for m in lst(self.o.get("moods")):
            m = d(m)
            if m.get("mood") in ("Melancholy", "Raving", "Berserk", "Traumatized"):
                continue
            if not m.get("claimed_building_id"):
                want = MOOD_WORKSHOP.get(str(m.get("skill")).upper(), "Craftsdwarfs")
                # e6cb74a4 adapts 937a7b6c's bounded repair to unclaimed moods.
                self.ensure_workshop(want)
            for need in lst(m.get("items_needed")):
                if "bone" in str(d(need).get("item") or d(need).get("demand")).lower():
                    self.butcher()

    def butcher(self, prefer_food=False, large_only=False):
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        if "Butchers" not in have:
            self.build("Butchers")
        if not self.may("slaughter", 5, 3):
            return
        q = self.game.query("units", kind="animals")
        animals = [d(a) for a in lst(d(q.get("result")).get("units") or d(q.get("result")).get("animals"))]
        eligible = [a for a in animals if a.get("tame") and a.get("pet_owner_id") in (None, -1)
                    and not a.get("marked_for_slaughter")]
        if prefer_food or large_only:
            large = [a for a in eligible if a.get("adult") is True and str(a.get("race")).upper() in LARGE_LIVESTOCK]
            if large:
                males = [a for a in large if a.get("female") is False]
                eligible = males or large
            elif large_only:
                eligible = []
        if eligible:
            self.act("slaughter", "slaughter", {"unit_id": eligible[0].get("id")}, retry=5, limit=3)

    def defend(self):
        th, mil = d(self.o.get("threats")), d(self.o.get("military"))
        bur = d(self.o.get("burrows"))
        alert = bur.get("civilian_alert")
        if alert and self.alert_since is None:
            self.alert_since = self.now
        elif alert is False:
            self.alert_since = None
        squads = lst(mil.get("squads"))
        squad = d(squads[0]) if squads else None
        if not squad and self.cit >= 14:
            self.act("squad", "create_squad", {"size": 4}, retry=5, limit=3)
        if squad and squad.get("uniform") == "none":
            self.act("equip", "equip_squad", {"uniform": "leather"}, retry=5, limit=3)
        shelter = self.room_for("dorm")
        if shelter and not any(d(b).get("civ_alert_burrow") for b in lst(bur.get("list"))):
            self.act("burrow", "create_burrow", {"site": shelter["id"]}, retry=5, limit=3)
        invaders = [h for h in lst(th.get("hostiles")) if d(h).get("invader")]
        hostile = th.get("visible_hostiles") or 0
        orders = lst((squad or {}).get("orders"))
        if hostile and squad and (squad.get("armed") or 0) >= 1 and not orders:
            self.act("attack", "squad_order", {"order": "attack"}, retry=1, limit=99)
        if not hostile and orders:
            self.act("stand_down", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
        near = (th.get("nearest_hostile_dist_to_wagon") or 10 ** 6) <= 45
        if invaders and near and not alert and any(d(b).get("civ_alert_burrow") for b in lst(bur.get("list"))):
            r = self.act("alert_on", "civilian_alert", {"on": True}, retry=20, limit=99)
            if r and r.get("ok"):
                self.alert_since = self.now
        # civilians can't reach drink or food under a long alert: never hold it more than 10 days
        too_long = self.alert_since is not None and self.now - self.alert_since > 10 * DAY
        if alert and (not invaders or too_long):
            r = self.act("alert_off", "civilian_alert", {"on": False}, retry=1, limit=99)
            if r and r.get("ok"):
                self.alert_since = None

    def step(self, resp):
        """One pass of the deterministic layer for the plain loop. Returns the number of actions it ran."""
        self.load(resp)
        self.count = 0
        try:
            self.plan()
        except (HandsOff, GameOver):
            raise
        except ActionLimit:
            log("guard_action_limit")
        except Exception as e:   # a surprise in this layer must never stop the model loop
            log("guard_error", error=repr(e)[:300])
        return self.count

    def pace(self, resp):
        if d(self.o.get("threats")).get("visible_hostiles") or self.o.get("moods"):
            return 1
        if (self.o.get("dig_designations_pending") or 0) > 0 or (resp.get("day") or 0) < 14:
            return 1
        return 2

    def run(self):
        self.game.task()
        while True:
            resp = self.game.observe()
            if resp.get("game_over"):
                return "game_over"
            for _ in range(MAX_PASSES):
                self.load(resp)
                self.count = 0
                try:
                    self.plan()
                except (ActionLimit, HandsOff, GameOver):
                    raise
                except Exception as e:   # a surprise in one step must never stop time
                    log("plan_error", error=repr(e)[:300])
                if not self.count:
                    break
                resp = self.game.observe()
            self.load(resp)
            r = self.game.act("advance_days", {"days": self.pace(resp)})
            log("advance", day=r.get("day"), stopped=d(r.get("result")).get("stopped"), cit=self.cit,
                drink=self.st.get("drink"), food=self.st.get("food_edible"))
            if r.get("game_over") or d(r.get("result")).get("hands_off"):
                return "over"


def main():
    task = load_task()
    game = GameClient(task.game_url)
    log("start", task=repr(task))
    ov = Overseer(game)
    while True:
        try:
            reason = ov.run()
            log("done", reason=reason)
            return 0
        except ActionLimit as e:
            log("action_limit", error=str(e)[:200])
            game.act("advance_days", {"days": 1})
        except (HandsOff, GameOver) as e:
            log("done", reason=type(e).__name__)
            return 0
        except GameAPIError as e:
            log("game_error", error=str(e)[:300])
            return 1


if __name__ == "__main__":
    sys.exit(main())
