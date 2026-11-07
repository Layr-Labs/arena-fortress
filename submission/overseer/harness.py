"""Overseer: a deterministic Dwarf Fortress manager for game API v0. Reads facts, acts through the public tools only.

Order of work follows the score's gates: survive, supply, wellbeing, housing. Every step is idempotent and rate
limited, so a refused action is retried later rather than looped on. Makes no model calls.
Run: python -m overseer   (reads DFBENCH_TASK)
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
    def __init__(self, game):
        self.game = game
        self.tries, self.last = {}, {}
        self.roles = {}          # room id -> farm | dorm | dine | office
        self.brew_orders = set()
        self.drink_growth = False
        self.beds_first = False
        self.now = 0
        self.alert_since = None

    def set_task(self, task):
        """Select fresh-start policies from the public task."""
        task = d(task)
        self.drink_growth = bool(task.get("hands_off")) and (
            "drink must not end lower" in str(task.get("goal") or "").casefold())
        self.beds_first = bool(task.get("hands_off")) and (
            "every dwarf must have a placed bed" in str(task.get("goal") or "").casefold())

    # ---- the action gate
    def may(self, key, retry=2, limit=6):
        return self.tries.get(key, 0) < limit and self.now - self.last.get(key, -10 ** 9) >= retry * DAY

    def act(self, key, tool, args, retry=2, limit=6):
        """One rate-limited action. Returns the response if it ran, else None."""
        if not self.may(key, retry, limit):
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
        return r

    # ---- facts
    def load(self, resp):
        self.o = d(resp.get("observation"))
        self.st, self.map = d(self.o.get("stocks")), d(self.o.get("map"))
        self.adm = d(self.o.get("administrators"))
        self.now = d(self.o.get("date")).get("abs_tick") or resp.get("tick") or 0
        self.people = [x for x in lst(self.o.get("dwarves")) if isinstance(x, dict)]
        self.cit = self.adm.get("citizens") or len(self.people)
        self.sites = [s for s in lst(self.map.get("sites")) if isinstance(s, dict)]
        self.orders = [x for x in lst(self.o.get("orders")) if isinstance(x, dict)]
        if isinstance(self.o.get("orders"), list):
            self.brew_orders.intersection_update(x.get("id") for x in self.orders)
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

    def workshops(self):
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        for t in ("Carpenters", "Still", "Kitchen"):
            if t not in have:
                self.build(t)
        if "Fishery" not in have and any(p.get("job") == "Fish" for p in self.people):
            self.build("Fishery")
        if self.beds_first and sum(w.get("type") == "Carpenters" for w in lst(self.o.get("workshops"))
                                   if isinstance(w, dict)) < 2:
            self.build("Carpenters")

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
                if role == "dorm" and self.beds_first:
                    size = {"w": 11, "h": 9}
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
        if not (self.brew_orders if self.drink_growth else self.standing("brew_drink")):
            when = [{"stock": "plants_brewable", "at_least": 2}, {"stock": "barrels_empty", "at_least": 1}]
            if not self.drink_growth:
                when.insert(0, {"stock": "drink", "below": DRINK_CAP})
            self.act("o_brew", "add_order", {"recipe": "brew_drink", "amount": 3,
                     "repeat": "daily", "when": when}, retry=3)
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
        for recipe, have, want in (("make_bed", self.st.get("beds") or 0, self.cit + 3),
                                   ("make_table", self.st.get("tables") or 0, seats),
                                   ("make_chair", self.st.get("chairs") or 0, seats + 1)):
            if self.beds_first and recipe in ("make_table", "make_chair"):
                continue
            if have < want and not self.pending(recipe) and self.logs():
                self.act("o_" + recipe, "add_order", {"recipe": recipe, "amount": min(8, want - have)}, retry=1, limit=99)

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
            return [], result.get("error_code")
        points = d(result.get("result")).get("at") or []
        if points and not isinstance(points[0], list):
            points = [points]
        return [{"kind": kind, "x": x, "y": y, "z": z} for x, y, z in points], None

    def furnish(self):
        dorm, dine = self.room_for("dorm"), self.room_for("dine") or self.room_for("dorm")
        if dorm:
            short = self.cit + 2 - (self.placed.get("bed") or 0)
            n = min(self.free.get("bed") or 0, short, 30)
            placed, error = self.place("beds", "bed", dorm, n) if n > 0 else ([], None)
            bed_rooms = [(dorm, placed, "z_dorm")]
            if self.beds_first and error == "no_space":
                areas = sorted((s for s in self.kind("A") if s["id"] != dorm["id"]
                                and s.get("open_tiles", 0) >= 6),
                               key=lambda s: (-s.get("open_tiles", 0), s["id"]))
                if areas:
                    alternate = areas[0]
                    placed, _ = self.place("beds_" + alternate["id"], "bed", alternate, n)
                    bed_rooms.append((alternate, placed, "z_dorm_" + alternate["id"]))
            for room, placed, key in bed_rooms:
                if self.needs_zone(room, self.zone("dorm") + self.zone("bedroom"), ("bed",), placed):
                    self.act(key, "make_zone", {"kind": "dormitory", "site": room["id"]}, retry=3)
        if dine:
            want = math.ceil(self.cit / 2) + 1
            placed = []
            for kind in ("table", "chair"):
                n = min(self.free.get(kind) or 0, want - (self.placed.get(kind) or 0), 15)
                if n > 0 and not self.beds_first:
                    points, _ = self.place("f_" + kind, kind, dine, n)
                    placed += points
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
    ov.set_task(task.task)
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
