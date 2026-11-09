"""Migrant-task (surge) housing rules: bed target from day 0, beds before seats, overflow placement, office chair.
No game or network is used."""
import copy
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

SURGE_GOAL = "Migrants are arriving. From day 39 you can't act for 21 days."
OPEN_GOAL = "Run the fortress for 336 days."


class FakeGame:
    """place_furniture fills the named sites up to their capacity; everything else succeeds."""

    def __init__(self, capacity):
        self.calls = []
        self.capacity = dict(capacity)

    def act(self, tool, args):
        self.calls.append((tool, copy.deepcopy(args)))
        if tool == "place_furniture":
            room = self.capacity.get(args["site"], 0)
            n = min(room, args.get("count", 1))
            if n <= 0:
                return {"ok": False, "error_code": "no_space"}
            self.capacity[args["site"]] = room - n
            return {"ok": True, "result": {"n": n, "at": [[20 + i, 20, 9] for i in range(n)]}}
        return {"ok": True, "result": {"order_id": len(self.calls), "zone_id": len(self.calls)}}


def site(id, z, w=9, h=7, open_tiles=40, **kw):
    return {"id": id, "kind": id[0], "x": 10, "y": 10, "z": z, "w": w, "h": h, "open_tiles": open_tiles, **kw}


def facts(citizens, free, stocks=None, furniture=(), office=None, sites=None, surface=None):
    st = {"logs_usable": 100, "beds": free.get("bed", 0), "tables": free.get("table", 0),
          "chairs": free.get("chair", 0), "furniture_free": dict(free), **(stocks or {})}
    adm = {"citizens": citizens, "manager_active_for_orders": True,
           "manager_office": office if office is not None else {"zone_id": 1, "chair": True}}
    return {"day": 5, "tick": 5 * harness.DAY, "observation": {
        "administrators": adm, "stocks": st, "furniture": list(furniture), "orders": [], "zones": [],
        "map": {"surface_z": surface, "sites": copy.deepcopy(sites if sites is not None else
                                       [site("R1", 9, w=3, h=3, dug=True), site("A1", 9), site("A2", 8)])}}}


class SurgeBeds(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def make(self, goal, capacity, *args, **kw):
        game = FakeGame(capacity)
        ov = harness.Overseer(game, goal=goal, days=60)
        ov.roles = {"R1": "dorm"}
        ov.count = 0
        ov.load(facts(*args, **kw))
        return ov, game

    def placed(self, game, kind):
        return [(a["site"], a.get("count", 1)) for t, a in game.calls if t == "place_furniture" and a["kind"] == kind]

    def orders(self, game):
        return [a["recipe"] for t, a in game.calls if t == "add_order"]

    def test_surge_orders_the_whole_wave_from_day_zero(self):
        ov, _ = self.make(SURGE_GOAL, {}, 19, {"bed": 19})
        self.assertEqual(ov.bed_target(), harness.SURGE_BEDS)
        ov, _ = self.make(OPEN_GOAL, {}, 19, {"bed": 19})
        self.assertEqual(ov.bed_target(), 22)

    def test_surge_places_beds_and_no_seats_while_beds_are_short(self):
        ov, game = self.make(SURGE_GOAL, {"A1": 60}, 19, {"bed": 19, "table": 12, "chair": 12})
        ov.furnish()
        self.assertEqual(self.placed(game, "bed"), [("A1", 19)])
        self.assertEqual(self.placed(game, "table") + self.placed(game, "chair"), [])
        ov.supply()
        self.assertIn("make_bed", self.orders(game))
        self.assertNotIn("make_table", self.orders(game))
        self.assertNotIn("make_chair", self.orders(game))

    def test_surge_still_orders_a_chair_for_a_chairless_office(self):
        ov, game = self.make(SURGE_GOAL, {"A1": 60}, 25, {"bed": 0}, office="none")
        ov.supply()
        self.assertIn("make_chair", self.orders(game))
        self.assertNotIn("make_table", self.orders(game))

    def test_surge_overflow_goes_to_another_dug_level(self):
        ov, game = self.make(SURGE_GOAL, {"A1": 5, "A2": 30}, 30, {"bed": 20})
        ov.furnish()
        self.assertEqual(self.placed(game, "bed"), [("A1", 20), ("A2", 15)])

    def dig_calls(self, game):
        return [a for t, a in game.calls if t == "dig_room"]

    def test_surge_digs_the_dormitory_first_below_the_shallow_levels(self):
        sites = [site("R1", 77, w=3, h=3, designated=False, soil=True),
                 site("R4", 75, w=3, h=3, designated=False, soil=True)]
        ov, game = self.make(SURGE_GOAL, {}, 19, {"bed": 19}, sites=sites, surface=78)
        ov.roles = {}
        ov.digging()
        self.assertEqual(self.dig_calls(game), [{"site": "R1"}, {"site": "R4", "w": 9, "h": 7}])
        self.assertEqual(ov.roles, {"R1": "farm", "R4": "dorm"})

    def test_open_play_keeps_farms_first(self):
        sites = [site("R1", 77, w=3, h=3, designated=False, soil=True),
                 site("R4", 75, w=3, h=3, designated=False, soil=True)]
        ov, game = self.make(OPEN_GOAL, {}, 19, {"bed": 19}, sites=sites, surface=78)
        ov.roles = {}
        ov.digging()
        self.assertEqual(ov.roles, {"R1": "farm", "R4": "farm"})

    def test_second_pass_on_the_same_day_does_not_overflow(self):
        ov, game = self.make(SURGE_GOAL, {"A1": 60, "A2": 30}, 30, {"bed": 19})
        ov.furnish()
        ov.load(facts(30, {"bed": 4}))   # same tick: the day's dorm placement is rate-limited now
        ov.furnish()
        self.assertEqual(self.placed(game, "bed"), [("A1", 19)])

    def test_surge_keeps_farm_plots_off_the_dormitory_floor(self):
        sites = [site("F1", 75, w=3, h=3, x=12, y=12), site("F2", 75, w=3, h=3, x=40, y=40)]
        for goal, expected in ((SURGE_GOAL, ["F2"]), (OPEN_GOAL, ["F1", "F2"])):
            ov, game = self.make(goal, {}, 19, {"bed": 19}, sites=sites, surface=78)
            ov.dorm_box = (10, 10, 75, 9, 7)
            ov.farms()
            built = [a["site"] for t, a in game.calls if t == "build_farm"]
            self.assertEqual(built, expected, goal)

    def test_open_play_keeps_seats_beside_beds(self):
        ov, game = self.make(OPEN_GOAL, {"A1": 60}, 19, {"bed": 19, "table": 12, "chair": 12})
        ov.furnish()
        self.assertTrue(self.placed(game, "table") and self.placed(game, "chair"))
        self.assertEqual(len(self.placed(game, "bed")), 1)


if __name__ == "__main__":
    unittest.main()
