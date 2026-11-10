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
LATE_FOOD_DAYS = 14     # closer: slaughter for meat in the last two weeks of a long open run...
LATE_FOOD_PER_CIT = 40  # ...while edible food is under this per citizen
HOUSE_DIG = {"w": 11, "h": 9}   # housing expansion: one more 99-tile room when the housing levels fill
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
        self.days = days or 0
        self.tries, self.last = {}, {}
        self.roles = {}          # room id -> farm | dorm | dine | office
        self.brew_orders = set()
        self.now = 0
        self.alert_since = None
        self.hands_off = None
        self.days_left = None
        self.day = None
        self.owned = set()       # order ids this layer added: the model loop refuses to cancel them
        self.report = []         # the layer's recent actions (day, tool, args, outcome), for the model loop
        self.done = set()        # closer keys whose order was accepted once: never re-added
        self.full = {}           # area id -> its open_tiles when a placement found no free floor there

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
        self.sites = [s for s in lst(self.map.get("sites")) if isinstance(s, dict)]
        self.orders = [x for x in lst(self.o.get("orders")) if isinstance(x, dict)]
        if isinstance(self.o.get("orders"), list):
            self.brew_orders.intersection_update(x.get("id") for x in self.orders)
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
        self.expand()
        self.digging()
        self.farms()
        self.supply()
        self.furnish()
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
        """DF stops validating orders around 20 citizens unless the manager has an office with a chair."""
        if self.cit < 14 or not self.adm.get("manager_active_for_orders"):
            return
        mo = self.adm.get("manager_office")
        if isinstance(mo, dict) and mo.get("chair"):
            return
        mgr = self.adm.get("MANAGER_id")
        offices = self.zone("office")
        owned = [z for z in offices if mgr is not None and z.get("owner") == mgr]
        mine = next((z for z in owned if not self.cramped(z)), owned[0] if owned else None)
        if not mine:
            spare = next((z for z in offices if z.get("owner") is None and not self.cramped(z)), None)
            if spare and mgr is not None:
                self.act("office_assign", "assign_zone", {"zone_id": spare["id"], "dwarf_id": mgr})
                return
            room = self.office_room()
            if room:
                result = self.act("office_zone", "make_zone", {"kind": "office", "site": room["id"]})
                if result and result.get("ok") and (self.free.get("chair") or 0) > 0:
                    self.act("office_chair", "place_furniture", {"kind": "chair", "site": room["id"]})
            return
        if d(mine.get("furniture")).get("chair") or d(mine.get("furniture_planned")).get("chair"):
            return
        room = next((s for s in self.sites if s.get("kind") in "RA" and s.get("z") == mine.get("z")
                     and s.get("x") == mine.get("x") and s.get("y") == mine.get("y")), None)
        room = room or next(iter(self.dug_rooms("office") + self.kind("A")), None)
        if self.cramped(mine) or (room and self.is_full(room)):
            self.move_office(mgr, mine)   # the chair can never fit there
        elif room and (self.free.get("chair") or 0) > 0:
            self.act("office_chair", "place_furniture", {"kind": "chair", "site": room["id"]})

    def cramped(self, z):
        """An office zone a chair can never fit in: a single tile (a stair landing's A area is one tile, the stair)."""
        return (z.get("w") or 1) * (z.get("h") or 1) <= 1

    def office_room(self, avoid=None):
        """Where an office can hold its chair: a dug office room, else a dug level with free floor (never a stair-only
        A area, whose one tile is the stair)."""
        rooms = [r for r in self.dug_rooms("office") if not self.is_full(r)]
        rooms += [a for a in self.house_rooms(None) if self.free_tiles(a) >= 2]
        return next((r for r in rooms if not (avoid and covers(r, avoid) and covers(avoid, r))), None)

    def move_office(self, mgr, old):
        """The manager's office can't take a chair (its zone is one stair tile, or its floor is full), and from about
        20 citizens DF validates no order without one: locally an MY1 fort kept a 1x1 office on a stair landing for
        200 days and every order added after day 50 stayed unvalidated. Make an office on a level with free floor,
        put the chair in it, and give it to the manager."""
        room = self.office_room(avoid=old)
        if not room or mgr is None:
            return
        result = self.act("office_move_" + room["id"], "make_zone", {"kind": "office", "site": room["id"]},
                          retry=5, limit=2)
        if not (result and result.get("ok")):
            return
        zid = d(result.get("result")).get("zone_id")
        if (self.free.get("chair") or 0) > 0:
            self.act("office_move_chair", "place_furniture", {"kind": "chair", "site": room["id"]}, retry=1, limit=10)
        if zid is not None:
            self.act("office_move_assign", "assign_zone", {"zone_id": zid, "dwarf_id": mgr}, retry=2, limit=5)

    def build(self, wtype, retry=3):
        sites = self.kind("W")
        if not sites or not self.material():
            return
        result = self.act("ws_" + wtype, "build_workshop", {"type": wtype, "site": sites[0]["id"]}, retry=retry)
        if result and result.get("ok"):
            self.sites.remove(sites[0])

    def workshops(self):
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        for t in ("Carpenters", "Still", "Kitchen"):
            if t not in have:
                self.build(t)
        if "Fishery" not in have and any(p.get("job") == "Fish" for p in self.people):
            self.build("Fishery")

    def bed_target(self):
        """Beds per citizen is read at the horizon; a migrant task's wave is bigger than the fort's bed stock."""
        return self.cit + (12 if self.surge else 3)

    def farm_target(self):
        return max(4, min(10, math.ceil(self.cit / 5)))

    def digging(self):
        rooms = self.kind("R")
        pending = self.o.get("dig_designations_pending") or 0
        stairs = self.kind("S")
        if stairs and self.surface is not None and (len(rooms) < 2 or (not any(r.get("soil") for r in rooms)
                                                                       and not self.o.get("farm_plots"))):
            self.act("stairs", "dig_stairs", {"site": stairs[-1]["id"], "z_bottom": self.surface - 4}, retry=12, limit=3)
        if pending > 90:
            return
        farms = len(lst(self.o.get("farm_plots"))) + sum(1 for r, v in self.roles.items() if v == "farm" and not any(z.get("id") == r and z.get("used_by") for z in self.kind("R")))
        for r in self.undug_rooms():
            rid = r["id"]
            if rid in self.roles:
                continue
            need = [x for x in ("dorm", "dine", "office") if x not in self.roles.values()]
            if r.get("soil") and farms < self.farm_target():
                result = self.act("dig_" + rid, "dig_room", {"site": rid}, retry=3, limit=2)
                if result and result.get("ok"):
                    self.roles[rid] = "farm"
                    farms += 1
            elif need:
                role = need[0]
                size = {"dorm": {"w": 9, "h": 7}, "dine": {"w": 7, "h": 5}, "office": {}}[role]
                result = self.act("dig_" + rid, "dig_room", {"site": rid, **size}, retry=3, limit=2)
                if result and result.get("ok"):
                    self.roles[rid] = role

    def farms(self):
        plots = lst(self.o.get("farm_plots"))
        target = self.farm_target()
        if len(plots) >= target:
            return
        cands = self.kind("F") + [r for r in self.dug_rooms() if r.get("soil") and self.roles.get(r["id"], "farm") == "farm"]
        seeds = d(self.st.get("seeds_by_kind"))
        if any(not d(v).get("underground") for v in seeds.values()):
            cands += self.kind("G")[:2]
        for s in cands[:target - len(plots)]:
            self.act("farm_" + s["id"], "build_farm", {"site": s["id"]}, retry=4, limit=3)

    def supply(self):
        """Standing orders that keep working in a hands-off window, then one-shot furniture sized to the population."""
        if not self.standing("brew_drink"):
            self.act("o_brew", "add_order", {"recipe": "brew_drink", "amount": 3, "repeat": "daily", "when": [
                {"stock": "drink", "below": DRINK_CAP}, {"stock": "plants_brewable", "at_least": 2},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=3)
        if not self.standing("make_barrel"):
            self.act("o_barrel", "add_order", {"recipe": "make_barrel", "amount": 2, "repeat": "daily", "when": [
                {"stock": "barrels_empty", "below": 4}, {"stock": "logs", "at_least": 2}]}, retry=3)
        if not self.standing("cook_meal"):
            self.act("o_cook", "add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily", "when": [
                {"stock": "prepared_meals", "below": MEAL_CAP}, {"stock": "plants_total", "at_least": 10}]}, retry=3)
        plants = d(self.st.get("plants_by_kind"))
        if (self.st.get("drink") or 0) < 3 * self.cit and not self.st.get("plants_brewable") and plants \
                and not self.pending("brew_drink_from_fruit"):
            self.act("o_fruit", "add_order", {"recipe": "brew_drink_from_fruit", "amount": 3}, retry=4)
        seats = math.ceil(self.cit / 2) + 2
        beds_have = self.st.get("beds") or 0
        wants = [("make_bed", beds_have, self.bed_target(), 30),
                 ("make_table", self.st.get("tables") or 0, seats, 15),
                 ("make_chair", self.st.get("chairs") or 0, seats + 1, 15)]
        if self.surge and beds_have < self.bed_target() - 5:
            wants = wants[:1]   # a migrant wave is scored on placed beds: the carpenters make beds first (5ef22a35)
        for recipe, have, want, batch in wants:
            # the whole shortfall in one order: each new order waits days for the manager's validation (16 days on
            # a 41-citizen fort, locally), so batches of 8 re-paid that wait for every batch
            if have < want and not self.pending(recipe) and self.logs():
                self.act("o_" + recipe, "add_order", {"recipe": recipe, "amount": min(batch, want - have)},
                         retry=1, limit=99)

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
            if carp == 1 and self.cit >= 15 and self.logs() >= 5:
                self.build("Carpenters", retry=3)   # one shop can't make a wave's beds before the window

    def endgame_supply(self):
        """The supply sub-score credits a stock by its projected days left: a draining stock is credited only as far
        as it lasts, and a flat or rising one in full. From ENDGAME_DAYS before the horizon, a second brew order with a
        cap well above the usual one keeps drink rising through the final stretch (while plants stay above a reserve
        that protects the food count, since plants are food too), and cooking keeps meals rising from surplus food.
        Meat is added when edible food is short of a few days per citizen."""
        # Plants are food too, and the score takes the lower of drink and food over the final stretch. A dwarf drinks
        # about 0.06 a day and eats about 0.024, so a year of drink is ~20 per citizen and a year of food ~8, and one
        # brew turns 1 food into 5 drinks. Brewing therefore pays only while drink is the scarcer of the two: a
        # staircase of three orders brews from any plant while drink is really short (under ~200 days), up to a
        # year of drink only while a year of food stands, and up to the cap only while food is ample. Locally on
        # MY1 the old single order (brew while 12+ plants remain) took drink from 400 to 441 while food fell from 113
        # to 91 over the final stretch (142 days left, supply 0.71).
        cap = max(600, 30 * self.cit)
        for key, drink_below, food_at_least in (("o_brew_short_end", 12 * self.cit, None),
                                                ("o_brew_year_end", 20 * self.cit, max(30, 8 * self.cit)),
                                                ("o_brew_end", cap, max(40, 12 * self.cit))):
            gate = {"stock": "plants_brewable", "at_least": 2} if food_at_least is None else \
                {"stock": "food_edible", "at_least": food_at_least}
            self.act(key, "add_order", {"recipe": "brew_drink", "amount": 4, "repeat": "daily", "when": [
                {"stock": "drink", "below": drink_below}, gate, {"stock": "barrels_empty", "at_least": 1}]},
                retry=3, limit=4)
        self.act("o_barrel_end", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 8}, {"stock": "logs", "at_least": 4}]}, retry=3, limit=4)
        self.act("o_cook_end", "add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily", "when": [
            {"stock": "prepared_meals", "below": max(300, 10 * self.cit)},
            {"stock": "food_edible", "at_least": max(30, 4 * self.cit)}]}, retry=3, limit=4)
        # Late food from tame animals (e-man07's 1e6cbe5e timing rule, extended to open midyear horizons by
        # mpjunior92's 07b5e1e3): in the last two weeks of a long open run, meat from one spare animal every few days
        # turns a slowly draining food stock into a rising one over the scored final stretch. The old trigger (under
        # 4 food per citizen) almost never fired; locally MY1 forts ended with food lasting 259-269 days of the 336
        # the score credits in full. The Butchers is built when food first looks short, so it stands in time.
        food = self.st.get("food_edible") or 0
        late = self.days >= 168 and isinstance(self.days_left, int) and 2 <= self.days_left <= LATE_FOOD_DAYS
        if food < 4 * self.cit or (late and food < LATE_FOOD_PER_CIT * self.cit):
            self.butcher()
        elif food < LATE_FOOD_PER_CIT * self.cit and not any(
                isinstance(w, dict) and w.get("type") == "Butchers" for w in lst(self.o.get("workshops"))):
            self.build("Butchers")

    def window_supply(self):
        """Before a hands-off window: brew whenever a plant and a barrel allow, at a cap the window can't reach, so
        drink keeps rising while nobody can act (LT08 wants drink at the end above drink at the window's start;
        LT01 wants a batch brewed inside it). Plants are food too, and food must also hold through the window, so
        half a plant per citizen stays unbrewed. Barrels are the usual limit: an extra barrel order runs alongside."""
        self.act("o_brew_win", "add_order", {"recipe": "brew_drink", "amount": 5, "repeat": "daily", "when": [
            {"stock": "drink", "below": 2000}, {"stock": "plants_brewable", "at_least": self.plant_reserve()},
            {"stock": "barrels_empty", "at_least": 1}]}, retry=2, limit=5)
        self.act("o_barrel_win", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 10}, {"stock": "logs", "at_least": 3}]}, retry=2, limit=5)
        if (self.st.get("food_edible") or 0) < 4 * self.cit:
            self.butcher()

    def plant_reserve(self):
        """Brewable plants kept unbrewed before a window, sized to the food the rest of the run needs (a dwarf eats
        about 8 units a year; 0.03 a day with margin) after the fort's other edible food. The old flat half a plant
        per citizen held back every plant on forts with few plants and plenty of meat, fish and meals, so nothing
        brewed and drink fell through the window (LT08 wants drink at the end at least drink at its start)."""
        days = (self.days_left or 0) + 7
        need = math.ceil(0.03 * self.cit * days)
        other = (self.st.get("food_edible") or 0) - (self.st.get("plants_brewable") or 0)
        return max(1, min(max(3, self.cit // 2), need - other))

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
        if not result.get("ok"):
            if result.get("error_code") == "no_space":
                self.mark_full(room)
            return []
        res = d(result.get("result"))
        points = res.get("at") or []
        if points and not isinstance(points[0], list):
            points = [points]
        n, avail = res.get("n"), res.get("available")
        if type(n) is int and type(avail) is int and n < min(count, avail):
            self.mark_full(room)   # fewer placed than asked for and in stock: the room has no free floor left
        return [{"kind": kind, "x": x, "y": y, "z": z} for x, y, z in points]

    # ---- housing capacity: floor tiles, not furniture items, are what runs out (one item per free floor tile)
    def mark_full(self, room):
        self.full[room.get("id")] = room.get("open_tiles") or 0

    def is_full(self, room):
        """Full since a placement found no free floor, until the area grows (more of its level dug)."""
        rid = room.get("id")
        return rid in self.full and (room.get("open_tiles") or 0) <= self.full[rid]

    def free_tiles(self, area):
        """Free floor in an A area, estimated: its open tiles less the furniture and farm plots inside it."""
        if area.get("kind") != "A":
            return 0 if self.is_full(area) else max(0, (area.get("w") or 3) * (area.get("h") or 3) - sum(
                1 for f in lst(self.o.get("furniture")) if isinstance(f, dict) and covers(area, f)))
        used = sum(1 for f in lst(self.o.get("furniture")) if isinstance(f, dict) and covers(area, f))
        used += sum((p.get("w") or 1) * (p.get("h") or 1) for p in lst(self.o.get("farm_plots"))
                    if isinstance(p, dict) and covers(area, p))
        return 0 if self.is_full(area) else max(0, (area.get("open_tiles") or 0) - used)

    def house_rooms(self, first):
        """Where furniture can go, most room first: the role's own room, then every other dug level with space."""
        out = [first] if first and not self.is_full(first) else []
        rest = [a for a in self.kind("A") if a not in out and (a.get("open_tiles") or 0) >= 6 and not self.is_full(a)
                and (a.get("w") or 0) <= 30 and (a.get("h") or 0) <= 30]
        rest.sort(key=lambda a: (-self.free_tiles(a), str(a.get("id"))))
        return out + [a for a in rest if self.free_tiles(a) > 0]

    def bed_goal(self):
        return max(self.cit + 2, self.bed_target()) if self.surge else self.cit + 2

    def seat_goal(self):
        return math.ceil(self.cit / 2) + 1

    def tiles_needed(self):
        """Floor still needed for the housing the score reads: a bed per citizen (and the wave), a table and a
        chair per two, plus room for the year's migrants while much of an open run is left."""
        beds = max(0, self.bed_goal() - (self.placed.get("bed") or 0))
        seats = max(0, self.seat_goal() - (self.placed.get("table") or 0)) + \
            max(0, self.seat_goal() - (self.placed.get("chair") or 0))
        growth = 12 if self.hands_off is None and (self.days_left or 0) > 60 else 0
        return beds + seats + growth

    def expand(self):
        """Dig another big room before the housing levels fill. The fort's first dug rooms mostly become farms and
        one dormitory that also takes the dining tables; a migrant wave then finds no floor for its beds
        (place_furniture: no_space) while the beds sit in stock. One expansion is dug at a time: an 11x9 room on an
        undug R site (a non-soil one first, so the soil stays for farms), or, with no R site left, a deeper
        staircase that opens new levels and new R sites."""
        if self.cit < 7 or not (self.kind("A") or self.dug_rooms()):
            return
        digging = [r for r in self.kind("R") if self.roles.get(r["id"]) == "house" and not r.get("dug")]
        if digging or (self.o.get("dig_designations_pending") or 0) > 60:
            return
        free = sum(self.free_tiles(a) for a in self.house_rooms(None))
        if free >= self.tiles_needed():
            return
        rooms = [r for r in self.undug_rooms() if r["id"] not in self.roles]
        rooms.sort(key=lambda r: (bool(r.get("soil")), str(r.get("id"))))
        if rooms:
            rid = rooms[0]["id"]
            result = self.act("house_" + rid, "dig_room", {"site": rid, **HOUSE_DIG}, retry=2, limit=2)
            if result and result.get("ok"):
                self.roles[rid] = "house"
            return
        stairs = self.kind("S")
        if stairs and self.surface is not None:
            self.act("stairs_deep", "dig_stairs", {"site": stairs[0]["id"], "z_bottom": self.surface - 6},
                     retry=8, limit=3)

    def furnish(self):
        dorm, dine = self.room_for("dorm"), self.room_for("dine") or self.room_for("dorm")
        beds_now = self.placed.get("bed") or 0
        if dorm:
            n = min(self.free.get("bed") or 0, self.bed_goal() - beds_now, 30)
            placed = []
            for room in self.house_rooms(dorm) if n > 0 else []:
                if n <= 0:
                    break
                main = room is dorm
                pts = self.place("beds" if main else "beds_" + room["id"], "bed", room, n)
                placed += pts
                n -= len(pts)
                if pts and not main and self.needs_zone(room, self.zone("dorm") + self.zone("bedroom"), ("bed",), pts):
                    self.act("z_dorm_" + room["id"], "make_zone", {"kind": "dormitory", "site": room["id"]}, retry=3)
            beds_now += len(placed)
            if self.needs_zone(dorm, self.zone("dorm") + self.zone("bedroom"), ("bed",), placed):
                self.act("z_dorm", "make_zone", {"kind": "dormitory", "site": dorm["id"]}, retry=3)
        if dine:
            want = self.seat_goal()
            ns = {k: min(self.free.get(k) or 0, want - (self.placed.get(k) or 0), 15) for k in ("table", "chair")}
            # while beds are short, keep the floor they still need: seats take only what is left over
            bed_left = max(0, self.bed_goal() - beds_now)
            if bed_left:
                spare = max(0, sum(self.free_tiles(a) for a in self.house_rooms(None)) - bed_left)
                ns["table"] = min(ns["table"], spare // 2)
                ns["chair"] = min(ns["chair"], spare - max(0, ns["table"]))
            placed = []
            for kind in ("table", "chair"):
                n = ns[kind]
                for room in self.house_rooms(dine) if n > 0 else []:
                    if n <= 0:
                        break
                    main = room is dine
                    pts = self.place("f_" + kind if main else "f_%s_%s" % (kind, room["id"]), kind, room, n)
                    placed += pts
                    n -= len(pts)
                    if pts and not main and self.needs_zone(room, self.zone("dining"), ("table", "chair"), pts):
                        self.act("z_dine_" + room["id"], "make_zone", {"kind": "dining_hall", "site": room["id"]},
                                 retry=3)
            if self.needs_zone(dine, self.zone("dining"), ("table", "chair"), placed):
                self.act("z_dine", "make_zone", {"kind": "dining_hall", "site": dine["id"]}, retry=3)

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
        if not self.may("slaughter", 5, 3):
            return
        q = self.game.query("units", kind="animals")
        for a in lst(d(q.get("result")).get("units") or d(q.get("result")).get("animals")):
            a = d(a)
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
