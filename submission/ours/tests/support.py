"""Shared stubs and observations for the open-play tests. Not a test module."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from overseer.harness import DAY, Overseer  # noqa: E402
from plain.harness import Plain  # noqa: E402

from dfbench_client import GameAPIError  # noqa: E402

HERD = [{"id": 1, "race": "CAT", "tame": True, "adult": True, "pet_owner_id": -1},
        {"id": 2, "race": "WATER_BUFFALO", "tame": True, "adult": True, "pet_owner_id": -1},
        {"id": 3, "race": "DOG", "tame": True, "adult": True, "pet_owner_id": 77},      # a pet: never marked
        {"id": 4, "race": "YAK", "tame": True, "adult": True, "pet_owner_id": None},
        {"id": 5, "race": "BIRD_TURKEY", "tame": False, "adult": True, "pet_owner_id": -1},   # not tame
        {"id": 6, "race": "COW", "tame": True, "adult": True, "pet_owner_id": -1, "marked_for_slaughter": True},
        {"id": 7, "race": "DONKEY", "tame": True, "adult": True, "pet_owner_id": -1},
        {"id": 8, "race": "RABBIT", "tame": True, "adult": True, "pet_owner_id": -1}]


class StubGame:
    def __init__(self, herd=None, refuse=(), query_error=False):
        self.calls = []
        self.queries = 0
        self.herd = HERD if herd is None else herd
        self.refuse = set(refuse)          # (tool, id) pairs the game answers ok: false to
        self.query_error = query_error

    def act(self, tool, args):
        self.calls.append((tool, json.loads(json.dumps(args))))
        if (tool, args.get("unit_id", args.get("order_id"))) in self.refuse or (tool, None) in self.refuse:
            return {"ok": False, "error_code": "game_refused", "error": "scripted"}
        return {"ok": True, "result": {"order_id": 100 + len(self.calls)}}

    def query(self, name, **kw):
        self.queries += 1
        self.asked = getattr(self, "asked", []) + [kw.get("kind")]
        if self.query_error:
            raise GameAPIError("scripted")
        rows = getattr(self, "others", []) if kw.get("kind") == "others" else self.herd   # others: creatures in
        return {"result": {"units": [dict(u) for u in rows], "total": len(rows)}}       # sight, not the fort's own

    def tools(self, name):
        return [a for t, a in self.calls if t == name]


def resp(days_left, day, food, drink=50, cit=10, hands_off=None, orders=(), workshops=("Carpenters", "Still",
                                                                                         "Kitchen", "Butchers"),
         meals=0, plants=0):
    r = {"day": day, "days_left": days_left, "tick": day * DAY, "observation": {
        "date": {"abs_tick": day * DAY}, "administrators": {"citizens": cit, "manager_active_for_orders": True},
        "stocks": {"food_edible": food, "drink": drink, "logs_usable": 20, "prepared_meals": meals,
                   "plants_total": plants},
        "workshops": [{"type": w, "built": True} for w in workshops], "orders": list(orders),
        "plugins": {"autochop": "on", "seedwatch": "on", "autofarm": "on"},
        "dwarves": [{"id": i, "adult": True} for i in range(cit)], "map": {"sites": []}}}
    if hands_off is not None:
        r["hands_off_in_days"] = hands_off
    return r


def overseer(r, **kw):
    g = StubGame(**kw)
    ov = Overseer(g, goal="Run the fortress", days=336)
    ov.set_task({"goal": "Run the fortress for 336 days."})
    ov.load(r)
    ov.count = 0
    return ov, g


def bare(days_left, day, fishing=True, workshops=("Carpenters", "Still", "Kitchen"), **kw):
    """A fort with a free workshop site and, by default, neither a Fishery nor a Butchers and one dwarf fishing."""
    r = resp(days_left, day, food=60, workshops=workshops, **kw)
    r["observation"]["map"]["sites"] = [{"id": "W1", "kind": "W"}]
    if fishing:
        r["observation"]["dwarves"][4].update(profession="Fisherdwarf", job="Fish")
    return r


E1 = {"id": "E1", "kind": "E", "x": 92, "y": 100, "z": 153}
HATCH = {"id": 14, "kind": "hatch", "built": True, "locked": False, "x": 92, "y": 100, "z": 153}
BOX = {"x1": 89, "x2": 101, "y1": 99, "y2": 105, "z1": 150, "z2": 152}


def threat_resp(day, dist, n=3, invader=False, alert=False, inside=0, cit=10, tiles=124, doors=(HATCH,), sites=(E1,),
                free_hatch=0, at=None, drop=()):
    """An open-play observation with `n` hostiles `dist` tiles from the wagon (None: no hostile in sight). `drop`
    names sections to leave out, as a failed part of an observation would be."""
    r = resp(336 - day, day, food=60, cit=cit)
    o = r["observation"]
    o["threats"] = {"visible_hostiles": 0, "hostiles": [], "by_race": {}, "dead_citizens_total": 0}
    if dist is not None:
        x, y, z = at or (10, 10, 165)
        o["threats"] = {"visible_hostiles": n, "nearest_hostile_dist_to_wagon": dist, "dead_citizens_total": 0,
                        "by_race": {"HARPY": {"n": n, "invader": invader}},
                        "hostiles": [{"id": 900 + i, "race": "HARPY", "invader": invader, "x": x, "y": y, "z": z,
                                      "dist_to_wagon": dist} for i in range(n)]}
    o["burrows"] = {"civilian_alert": alert, "list": [{"id": 0, "name": "Shelter", "civ_alert_burrow": True,
                                                       "citizens_inside": inside, "tiles": tiles, "bbox": BOX}]}
    o["doors"] = {"list": [dict(x) for x in doors], "hatch_cover_items_free": free_hatch}
    o["map"]["surface_z"] = 153
    if sites is None:
        del o["map"]["sites"]
    else:
        o["map"]["sites"] = [dict(s) for s in sites]
    for name in drop:
        o[name] = "ERR: scripted"
    return r


def locked(*ids):
    return [dict(HATCH, locked=HATCH["id"] in ids)] + [{"id": i, "kind": "door", "built": True, "locked": True,
                                                         "x": 95, "y": 101, "z": 151} for i in ids if i != HATCH["id"]]


def hold(day, **kw):
    return {"since": day * DAY, "phase": "hold", "why": None, "alert_off": False, "rest": False, "due": None,
            "tries": 0, "fresh": False, "blind": 0, "shut": False, **kw}


class Lockdown:
    """play() runs one defence pass on a fresh controller; again() runs the next pass on the same one."""

    def play(self, r, refuse=(), **state):
        ov, g = overseer(r, refuse=refuse)
        for k, v in state.items():
            setattr(ov, k, v)
        ov.defend()
        return ov, g

    def again(self, ov, g, r):
        ov.load(r); ov.count = 0
        ov.defend()


class Task:
    task, days, credits = {"goal": "Run the fortress"}, 336, 0.5


class WalkGame:
    """advance_days answers from a script (one dict of extra result fields per call); observe() follows the clock."""

    def __init__(self, script=(), threats=None, water=None):
        self.script, self.advances, self.day, self.last = list(script), [], 100, {}
        self.threats, self.water = threats or {}, water or {}

    def act(self, tool, args):
        if tool != "advance_days":           # the layer's own actions between steps
            return {"ok": True, "result": {}}
        self.advances.append(args["days"])
        extra = self.script.pop(0) if self.script else {}
        self.day += args["days"]
        return {"ok": True, "day": self.day, "result": {"advanced_ticks": extra.pop("ticks", args["days"] * DAY),
                                                        "stopped": None, **extra}}

    def observe(self):
        r = resp(336 - self.day, self.day, food=60)
        if self.day in self.threats:
            r["observation"]["threats"] = {"visible_hostiles": 1, "nearest_hostile_dist_to_wagon": self.threats[self.day]}
        if self.day in self.water:
            r["observation"]["water_on_fort_levels"] = {"tiles": 9, "total_depth": self.water[self.day]}
        return r

    def query(self, *a, **kw):
        return {"result": {"units": [], "total": 0}}


def plain(game):
    p = Plain(Task(), game, model=None)
    p.guard.load(resp(236, 100, food=60))
    return p


WAGON = {"x": 96, "y": 96, "z": 153}


def beast(race, dist, **kw):
    """A creature `dist` tiles east of the wagon, as the units query lists it."""
    return {"id": 700, "race": race, "hostile": False, "x": WAGON["x"] + dist, "y": WAGON["y"], "z": 153, **kw}


def quiet(day, others=(), drink=50, **kw):
    """An open-play observation with no hostile in the threats list; `others` is what the units query will list."""
    r = threat_resp(day, None, **kw)
    r["observation"]["map"]["wagon"] = dict(WAGON)
    r["observation"]["stocks"]["drink"] = drink
    r["others"] = [dict(u) for u in others]
    return r
