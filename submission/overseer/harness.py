"""Overseer: a deterministic Dwarf Fortress manager for game API v0. Reads facts, acts through the public tools only.

Order of work follows the score's gates: survive, supply, wellbeing, housing. Every step is idempotent and rate
limited, so a refused action is retried later rather than looped on. Makes no model calls.
Run: python -m overseer   (reads DFBENCH_TASK)

Lineage: the layer and its steps come from e-man07's submissions 6e775ed2 (the architecture and the first layer) and
efac22bf (its real-DF fixes), both declared in dependencies.json. This copy adds the "closer" steps (endgame supply
mode for the scored final stretch, the pre-window boost on lab tasks, a housing check sized to the window), an
action report for the model loop, and the ownership record the model-loop guard reads (owned orders).
"""
import json
import math
import sys
import time

from dfbench_client import ActionLimit, GameAPIError, GameClient, GameOver, HandsOff, load_task

DAY = 1200
MAX_PER_PASS = 12
MAX_PASSES = 3
DRINK_LOW = 200         # below this, drink comes first: one plant brews five drinks, so a big buffer is cheap
DRINK_CAP = 1000
MEAL_CAP = 200
ENDGAME_DAYS = 64       # closer: the scored final stretch is the last quarter of a long run, clipped to 28 days;
                        #   the supply slope over it must be >= 0, so production is raised a month before it starts
WINDOW_PREP_DAYS = 14   # closer: days before a lab task's hands-off window when its orders and beds are secured
REPORT_KEEP = 24        # action report lines kept for the model loop
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


class Overseer:
    def __init__(self, game, goal="", days=0):
        self.game = game
        self.surge = "migrant" in str(goal).lower()   # the task's own text says more dwarves are on the way
        self.days = days or 0
        self.tries, self.last = {}, {}
        self.roles = {}          # room id -> farm | dorm | dine | office
        self.now = 0
        self.alert_since = None
        self.first_tick = None
        self.bad_offices = set()
        self.days_left = None
        self.owned = set()       # order ids this layer added: the model loop refuses to cancel them
        self.report = []         # the layer's recent actions (day, tool, args, outcome), for the model loop
        self.done = set()        # closer keys whose order was accepted once: never re-added
        self.day = None

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
        if r.get("ok") and tool in ("add_order", "add_manager_order"):
            res = r.get("result") if isinstance(r.get("result"), dict) else r
            if res.get("order_id") is not None:
                self.owned.add(res.get("order_id"))
            if args.get("repeat") and key.startswith("o_") and key.endswith(("_end", "_win")):
                self.done.add(key)   # a standing closer order is added once per game
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
        if self.first_tick is None:
            self.first_tick = self.now
        self.people = [x for x in lst(self.o.get("dwarves")) if isinstance(x, dict)]
        self.cit = self.adm.get("citizens") or len(self.people)
        self.sites = [s for s in lst(self.map.get("sites")) if isinstance(s, dict)]
        self.orders = [x for x in lst(self.o.get("orders")) if isinstance(x, dict)]
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
        self.low_food()
        self.rank()
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

    def office_ready(self):
        mo = self.adm.get("manager_office")
        if isinstance(mo, dict) and mo.get("chair"):
            return True
        mgr = self.adm.get("MANAGER_id")
        mine = next((z for z in self.zone("office") if mgr is not None and z.get("owner") == mgr), None)
        return bool(mine and (d(mine.get("furniture")).get("chair") or d(mine.get("furniture_planned")).get("chair")))

    def office(self):
        """DF stops validating orders around 20 citizens unless the manager has an office with a chair. A chair order
        made after that point can't validate, so this runs early, all in one pass, and its chair is reserved."""
        if self.cit < 14 or not self.adm.get("manager_active_for_orders") or self.office_ready():
            return
        if not self.free.get("chair") and not self.pending("make_chair") and self.logs():
            self.act("o_office_chair", "add_order", {"recipe": "make_chair", "amount": 2}, retry=1, limit=20)
        mgr = self.adm.get("MANAGER_id")
        offices = self.zone("office")
        mine = next((z for z in offices if mgr is not None and z.get("owner") == mgr), None)
        big = [x for x in self.kind("A") if (x.get("open_tiles") or 0) >= 6 and (x.get("w") or 0) <= 20 and (x.get("h") or 0) <= 20]
        room = next(iter(self.dug_rooms("office") + big + self.dug_rooms()), None)
        if mine and mine.get("id") in self.bad_offices:
            mine = None
        if not mine:
            spare = next((z for z in offices if z.get("owner") is None and z.get("id") not in self.bad_offices), None)
            zone_id = spare.get("id") if spare else None
            if zone_id is None and room:
                r = self.act("office_zone", "make_zone", {"kind": "office", "site": room["id"]})
                zone_id = d(r.get("result")).get("zone_id", r.get("zone_id")) if r and r.get("ok") else None
            if zone_id is None or mgr is None:
                return
            r = self.act("office_assign", "assign_zone", {"zone_id": zone_id, "dwarf_id": mgr})
            if not (r and r.get("ok")):
                return
        else:
            room = next((x for x in self.sites if x.get("kind") in ("R", "A") and x.get("z") == mine.get("z")
                         and x.get("x") == mine.get("x") and x.get("y") == mine.get("y")), room)
        if (self.free.get("chair") or 0) > 0 and room:
            r = self.act("office_chair", "place_furniture", {"kind": "chair", "site": room["id"]}, retry=1, limit=12)
            if r and r.get("ok"):
                self.free["chair"] -= 1
                self.office_placed = True
            elif r and r.get("error_code") == "no_space" and mine:
                self.bad_offices.add(mine.get("id"))   # no tile for a chair here: the next pass makes another office
                self.tries.pop("office_zone", None)
                self.tries.pop("office_assign", None)

    def build(self, wtype, retry=3):
        sites = [w for w in self.kind("W") if w["id"] not in self.spent_sites]
        if not sites or not self.material():
            return
        r = self.act("ws_" + wtype, "build_workshop", {"type": wtype, "site": sites[0]["id"]}, retry=retry)
        if r is not None:
            self.spent_sites.add(sites[0]["id"])

    def workshops(self):
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        for t in ("Carpenters", "Still", "Kitchen"):
            if t not in have:
                self.build(t)
        # one Carpenters can't keep up with a migrant wave's beds
        carp = sum(1 for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Carpenters")
        want = 3 if self.cit >= 30 else 2 if self.cit >= 15 else 1
        if carp and carp < want and self.logs() >= 5:
            r = [w for w in self.kind("W") if w["id"] not in self.spent_sites]
            if r and self.act("ws_carp%d" % carp, "build_workshop", {"type": "Carpenters", "site": r[0]["id"]}, retry=3):
                self.spent_sites.add(r[0]["id"])

    def farm_target(self):
        """Each plot takes up to 9 seeds, and crops go to 'none' once seeds run out, so seeds cap the plots."""
        want = max(4, min(10, math.ceil(self.cit / 5)))
        have = len(lst(self.o.get("farm_plots")))
        return min(want, have + (self.st.get("seeds") or 0) // 12)

    def housing_z(self):
        return {r.get("z") for r in self.kind("R") if self.roles.get(r["id"]) in ("dorm", "dine")}

    def digging(self):
        rooms = self.kind("R")
        pending = self.o.get("dig_designations_pending") or 0
        stairs = self.kind("S")
        deep = [r for r in rooms if self.surface is not None and (r.get("z") or 0) <= self.surface - 2]
        if stairs and self.surface is not None and (not deep or (not any(r.get("soil") for r in rooms)
                                                                 and not self.o.get("farm_plots"))):
            self.act("stairs", "dig_stairs", {"site": stairs[-1]["id"], "z_bottom": self.surface - 4}, retry=12, limit=3)
        if pending > 90:
            return
        farms = len(lst(self.o.get("farm_plots"))) + sum(
            1 for rid, v in self.roles.items() if v == "farm"
            and not any(x.get("id") == rid and x.get("used_by") for x in self.kind("R")))
        need = [x for x in ("dorm", "dine", "office") if x not in self.roles.values()]
        waited = self.now - (self.first_tick or self.now) >= 8 * DAY
        # housing goes on its own deep level: a level's A box must stay within make_zone's 20 tiles, and farm plots
        # built on dug floor would eat the room. Deepest first for housing, shallowest first for farms.
        undug = sorted([r for r in self.undug_rooms() if r["id"] not in self.roles], key=lambda r: r.get("z") or 0)
        used_z = {r.get("z") for r in self.kind("R") if self.roles.get(r["id"]) in ("dorm", "dine")}
        for role in need:
            deep = [r for r in undug if self.surface is None or (r.get("z") or 0) <= self.surface - 2 or waited]
            deep = [r for r in deep if r.get("z") not in used_z or role == "office"]
            if not deep:
                break
            r = deep[0]
            size = {"dorm": {"w": 11, "h": 7}, "dine": {"w": 9, "h": 5}, "office": {}}[role]
            if self.act("dig_" + r["id"], "dig_room", {"site": r["id"], **size}, retry=3, limit=2):
                self.roles[r["id"]] = role
                used_z.add(r.get("z"))
                undug.remove(r)
        hz = self.housing_z()
        for r in reversed(undug):
            if r.get("soil") and r.get("z") not in hz and farms < self.farm_target():
                if self.act("dig_" + r["id"], "dig_room", {"site": r["id"]}, retry=3, limit=2):
                    self.roles[r["id"]] = "farm"
                    farms += 1

    def farms(self):
        plots = lst(self.o.get("farm_plots"))
        target = self.farm_target()
        if len(plots) >= target:
            return
        hz = self.housing_z()
        cands = [x for x in self.kind("F") if x.get("z") not in hz] + [r for r in self.dug_rooms() if r.get("soil") and r.get("z") not in hz and self.roles.get(r["id"], "farm") == "farm"]
        seeds = d(self.st.get("seeds_by_kind"))
        if any(not d(v).get("underground") for v in seeds.values()):
            cands += self.kind("G")[:2]
        for s in cands[:target - len(plots)]:
            self.act("farm_" + s["id"], "build_farm", {"site": s["id"]}, retry=4, limit=3)

    def supply(self):
        """Standing orders that keep working in a hands-off window, then one-shot furniture sized to the population."""
        brews = sum(1 for x in self.orders if x.get("recipe") == "brew_drink" and x.get("repeat"))
        if brews < 1:   # drink first while it is short
            self.act("o_brew", "add_order", {"recipe": "brew_drink", "amount": 3, "repeat": "daily", "when": [
                {"stock": "drink", "below": DRINK_LOW}, {"stock": "plants_brewable", "at_least": 2},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=3)
        elif brews < 2:   # then only surplus plants, so cooking and raw food aren't starved
            self.act("o_brew2", "add_order", {"recipe": "brew_drink", "amount": 3, "repeat": "daily", "when": [
                {"stock": "drink", "below": DRINK_CAP}, {"stock": "plants_brewable", "at_least": 8 if self.surge else 30},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=3)
        if not self.standing("make_barrel"):
            self.act("o_barrel", "add_order", {"recipe": "make_barrel", "amount": 2, "repeat": "daily", "when": [
                {"stock": "barrels_empty", "below": 4}, {"stock": "logs", "at_least": 2}]}, retry=3)
        if not self.standing("cook_meal"):
            self.act("o_cook", "add_order", {"recipe": "cook_meal", "amount": 3, "repeat": "daily", "when": [
                {"stock": "prepared_meals", "below": MEAL_CAP}, {"stock": "food_edible", "at_least": 8}]}, retry=3)
        plants = d(self.st.get("plants_by_kind"))
        if (self.st.get("drink") or 0) < 3 * self.cit and not self.st.get("plants_brewable") and plants \
                and not self.pending("brew_drink_from_fruit"):
            self.act("o_fruit", "add_order", {"recipe": "brew_drink_from_fruit", "amount": 3}, retry=4)
        seats = math.ceil(self.cit / 2) + 2
        for recipe, have, want in (("make_bed", self.st.get("beds") or 0, self.bed_target()),
                                   ("make_table", self.st.get("tables") or 0, seats),
                                   ("make_chair", self.st.get("chairs") or 0, seats + 1)):
            if recipe != "make_bed" and (self.pending("make_bed") or (self.st.get("beds") or 0) < self.cit):
                continue   # beds first: they count one per citizen, and carpenters are the bottleneck
            if have < want and not self.pending(recipe) and self.logs():
                self.act("o_" + recipe, "add_order", {"recipe": recipe, "amount": min(15, want - have)}, retry=1, limit=99)

    def seats(self):
        """Seats as the score counts them: tables and chairs inside dining zones."""
        n = 0
        for z in self.zone("dining"):
            f = d(z.get("furniture"))
            n += min(f.get("table") or 0, f.get("chair") or 0)
        return n

    def bed_target(self):
        return self.cit + (12 if self.surge else max(3, self.cit // 5))

    def rank(self):
        """Full-year games only: DF's Hamlet rank needs 20 citizens and 5000 created wealth, and crafts raise wealth."""
        if self.days < 336 or self.cit < 12:
            return
        if (d(self.o.get("wealth")).get("created") or 0) >= 6000 or self.logs() < 15:
            return
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        if "Craftsdwarfs" not in have:
            self.build("Craftsdwarfs", retry=5)
        elif not any(x.get("job") == "MakeCrafts" and (x.get("left") or 0) > 0 for x in self.orders):
            self.act("o_crafts", "add_manager_order", {"job": "MakeCrafts", "amount": 5, "material_category": ["wood"]},
                     retry=3, limit=60)

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

    def endgame_supply(self):
        """The supply sub-score credits a stock by its projected days left: a draining stock is credited only as far
        as it lasts, and a flat or rising one in full. From ENDGAME_DAYS before the horizon, a third brew order with a
        cap well above the usual one keeps drink rising through the final stretch (while plants stay above a reserve
        that protects the food count, since plants are food too), and cooking keeps meals rising from surplus food.
        Meat is added when edible food is short of a few days per citizen."""
        cap = max(600, 30 * self.cit)
        reserve = max(12, self.cit)
        if not any(x.get("recipe") == "brew_drink" and x.get("repeat")
                   and any(d(c).get("value") == cap for c in lst(x.get("when"))) for x in self.orders):
            self.act("o_brew_end", "add_order", {"recipe": "brew_drink", "amount": 4, "repeat": "daily", "when": [
                {"stock": "drink", "below": cap}, {"stock": "plants_brewable", "at_least": reserve},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=3, limit=4)
        if sum(1 for x in self.orders if x.get("recipe") == "make_barrel" and x.get("repeat")) < 2:
            self.act("o_barrel_end", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
                {"stock": "barrels_empty", "below": 8}, {"stock": "logs", "at_least": 4}]}, retry=3, limit=4)
        if sum(1 for x in self.orders if x.get("recipe") == "cook_meal" and x.get("repeat")) < 2:
            self.act("o_cook_end", "add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily", "when": [
                {"stock": "prepared_meals", "below": max(300, 10 * self.cit)},
                {"stock": "food_edible", "at_least": max(30, 4 * self.cit)}]}, retry=3, limit=4)
        if (self.st.get("food_edible") or 0) < 4 * self.cit:
            self.butcher()

    def window_supply(self):
        """Before a hands-off window: brew whenever a plant and a barrel allow, at a cap the window can't reach, so
        drink keeps rising while nobody can act (LT08 wants drink at the end above drink at the window's start;
        LT01 wants a batch brewed inside it). Plants are food too, and food must also hold through the window, so
        half a plant per citizen stays unbrewed. Barrels are the usual limit: an extra barrel order runs alongside."""
        if not any(x.get("recipe") == "brew_drink" and x.get("repeat")
                   and any(d(c).get("value") == 2000 for c in lst(x.get("when"))) for x in self.orders):
            self.act("o_brew_win", "add_order", {"recipe": "brew_drink", "amount": 5, "repeat": "daily", "when": [
                {"stock": "drink", "below": 2000}, {"stock": "plants_brewable", "at_least": max(3, self.cit // 2)},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=2, limit=5)
        if sum(1 for x in self.orders if x.get("recipe") == "make_barrel" and x.get("repeat")) < 2:
            self.act("o_barrel_win", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
                {"stock": "barrels_empty", "below": 10}, {"stock": "logs", "at_least": 3}]}, retry=2, limit=5)
        if (self.st.get("food_edible") or 0) < 4 * self.cit:
            self.butcher()

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
        seats_short = math.ceil(self.cit / 2) - self.seats()
        if seats_short > 0 and self.logs() >= 2:
            for recipe, have in (("make_table", self.st.get("tables") or 0), ("make_chair", self.st.get("chairs") or 0)):
                want = math.ceil(self.cit / 2) + 1
                if have < want and not self.pending(recipe) and not self.ordered_now("o_" + recipe):
                    self.act("o_%s_close" % recipe, "add_order", {"recipe": recipe, "amount": min(30, want - have)},
                             retry=2, limit=10)

    def room_for(self, role):
        """The dug level of a role's big room (its A site covers the whole dig), else the room itself."""
        rooms = [r for r in self.kind("R") if self.roles.get(r["id"]) == role]
        for r in rooms:
            a = next((s for s in self.kind("A") if s.get("z") == r.get("z")), None)
            if a and role != "farm" and a.get("open_tiles", 0) >= 6:
                return a
        dug = [r for r in rooms if r.get("dug")]
        if dug:
            return dug[0]
        taken = {r.get("z") for r in self.kind("R") if self.roles.get(r["id"], "").startswith("farm")}
        return next((s for s in self.kind("A") if s.get("z") not in taken and (s.get("open_tiles") or 0) >= 6), None)

    def spill_sites(self, first):
        """Where furniture may go: the role's room, then any other dug level, then dug spare rooms."""
        out = [first] if first else []
        for x in self.kind("A") + self.dug_rooms():
            if self.roles.get(x["id"]) != "farm" and all(x["id"] != y["id"] for y in out):
                out.append(x)
        return out

    def place(self, kind, n, sites):
        for site in sites:
            if n <= 0:
                return
            r = self.act("p_%s_%s" % (kind, site["id"]), "place_furniture",
                         {"kind": kind, "site": site["id"], "count": min(n, 30)}, retry=1, limit=99)
            if r is None:
                continue
            if r.get("ok"):
                return
            if r.get("error_code") == "no_material":
                return

    def rezone(self):
        """Only furniture inside a zone counts or gets used. Zone each level's loose tables, chairs and beds."""
        loose = {}
        for f in lst(self.o.get("furniture")):
            f = d(f)
            if not f.get("zone_ids") and f.get("kind") in ("bed", "table", "chair") and f.get("built"):
                loose.setdefault(f.get("z"), set()).add(f.get("kind"))
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

    def low_food(self):
        """Meat counts as food: when stock is short of a few days per citizen, butcher a spare tame animal."""
        food = self.st.get("food_edible") or 0
        left = self.hands_off
        buffer_up = isinstance(left, int) and left <= 25 and food < 3 * self.cit   # nothing can be done inside the window
        if food < max(10, 2 * self.cit) or buffer_up:
            self.butcher()

    def furnish(self):
        dorm, dine = self.room_for("dorm"), self.room_for("dine") or self.room_for("dorm")
        if dorm:
            if not any(z.get("z") == dorm.get("z") and (z.get("w") or 0) * (z.get("h") or 0) >= 6
                       for z in self.zone("dorm") + self.zone("bedroom")):
                self.act("z_dorm_%s" % dorm.get("z"), "make_zone", {"kind": "dormitory", "site": dorm["id"]}, retry=3)
        n = min(self.free.get("bed") or 0, self.bed_target() - (self.placed.get("bed") or 0))
        self.place("bed", n, self.spill_sites(dorm))
        if dine:
            if not any(z.get("z") == dine.get("z") and (z.get("w") or 0) * (z.get("h") or 0) >= 6
                       for z in self.zone("dining")):
                self.act("z_dine_%s" % dine.get("z"), "make_zone", {"kind": "dining_hall", "site": dine["id"]}, retry=3)
            short = math.ceil(self.cit / 2) + 1 - self.seats()
            if short > 0:
                in_zones = {"table": 0, "chair": 0}
                for z in self.zone("dining"):
                    for kind in in_zones:
                        in_zones[kind] += d(z.get("furniture")).get(kind) or 0
                    for kind in in_zones:
                        in_zones[kind] += d(z.get("furniture_planned")).get(kind) or 0
                for kind in ("table", "chair"):
                    free = self.free.get(kind) or 0
                    if kind == "chair" and self.cit >= 14 and not self.office_ready() and not self.office_placed:
                        free -= 1   # the manager's chair comes first: without it no order validates past 20 citizens
                    self.place(kind, min(free, math.ceil(self.cit / 2) + 1 - in_zones[kind]), [dine])
                self.dine_over_existing()

    def dine_over_existing(self):
        """Tables and chairs placed in a dormitory earn no seats: a dining zone over the same level makes them count."""
        dining = {z.get("id") for z in self.zone("dining")}
        by_z = {}
        for f in lst(self.o.get("furniture")):
            f = d(f)
            if f.get("built") and f.get("kind") in ("table", "chair") and not dining & set(lst(f.get("zone_ids"))):
                by_z.setdefault(f.get("z"), {}).setdefault(f["kind"], 0)
                by_z[f.get("z")][f["kind"]] += 1
        for z, kinds in by_z.items():
            if kinds.get("table") and kinds.get("chair"):
                site = next((x for x in self.kind("A") if x.get("z") == z and (x.get("open_tiles") or 0) >= 6
                             and (x.get("w") or 0) <= 20 and (x.get("h") or 0) <= 20), None)
                if site:
                    self.act("dx_dine_%s" % site["id"], "make_zone", {"kind": "dining_hall", "site": site["id"]}, retry=3, limit=2)

    def mood(self):
        for m in lst(self.o.get("moods")):
            m = d(m)
            if m.get("mood") in ("Melancholy", "Raving", "Berserk", "Traumatized"):
                continue
            if not m.get("claimed_building_id"):
                want = MOOD_WORKSHOP.get(str(m.get("skill")).upper(), "Craftsdwarfs")
                have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
                if want not in have:
                    self.build(want, retry=2)
            for need in lst(m.get("items_needed")):
                if "bone" in str(d(need).get("item") or d(need).get("demand")).lower():
                    self.butcher()

    def butcher(self):
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        if "Butchers" not in have:
            self.build("Butchers")
        if not self.may("slaughter", 3, 40):
            return
        q = self.game.query("units", kind="animals")
        for a in lst(d(q.get("result")).get("units") or d(q.get("result")).get("animals")):
            a = d(a)
            if a.get("tame") and a.get("pet_owner_id") in (None, -1) and not a.get("marked_for_slaughter"):
                self.act("slaughter", "slaughter", {"unit_id": a.get("id")}, retry=3, limit=40)
                return

    def defend(self):
        th, mil = d(self.o.get("threats")), d(self.o.get("military"))
        bur = d(self.o.get("burrows"))
        squads = lst(mil.get("squads"))
        squad = d(squads[0]) if squads else None
        if not squad and self.cit >= 14:
            self.act("squad", "create_squad", {"size": 4}, retry=5, limit=3)
        if squad and squad.get("uniform") == "none":
            self.act("equip", "equip_squad", {"uniform": "weapon_only"}, retry=5, limit=3)
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
        alert = bur.get("civilian_alert")
        near = (th.get("nearest_hostile_dist_to_wagon") or 10 ** 6) <= 45
        if invaders and near and not alert and any(d(b).get("civ_alert_burrow") for b in lst(bur.get("list"))):
            if self.act("alert_on", "civilian_alert", {"on": True}, retry=20, limit=99):
                self.alert_since = self.now
        # civilians can't reach drink or food under a long alert: never hold it more than 10 days
        too_long = self.alert_since is not None and self.now - self.alert_since > 10 * DAY
        if alert and (not invaders or too_long):
            self.act("alert_off", "civilian_alert", {"on": False}, retry=1, limit=99)
            self.alert_since = None

    def step(self, resp):
        """One pass of the deterministic layer for the plain loop. Returns the number of actions it ran."""
        self.load(resp)
        self.count = 0
        self.spent_sites = set()
        self.office_placed = False
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
                self.spent_sites = set()
                self.office_placed = False
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
