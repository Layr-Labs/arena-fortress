"""Offline regressions for the goal policies (the placed-bed goal and the drink-growth goal).

The Overseer is driven against a stub game whose act() answers are scripted; no DF and no model is involved.
Only this build's additions are asserted: policy detection from the task text, the ceiling-less brew order, the
seats skipped while the bed goal is unmet, the second Carpenters, the no-space bed fallback to the next-largest
area, and the beds_unmet() reading the model loop uses to slow its advances.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from overseer.harness import Overseer  # noqa: E402


class StubGame:
    """A GameClient stand-in: scripted act() answers in order; the defaults answer ok."""

    def __init__(self, answers=()):
        self.answers = list(answers)
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, json.loads(json.dumps(args))))
        if self.answers:
            a = self.answers.pop(0)
            return a(tool, args) if callable(a) else a
        return {"ok": True, "result": {}}

    def query(self, *a, **kw):
        return {"result": {}}

    def observe(self, *a, **kw):
        return {}


def obs(cit=10, beds_stock=12, furniture=(), sites=None, orders=None, people=(), stocks=None, workshops=None):
    """A minimal obs-schema-8 shaped observation for the parts these tests touch."""
    return {
        "stocks": {"furniture_free": {"bed": beds_stock, "chair": 4, "table": 4},
                   "beds": beds_stock, "tables": 0, "chairs": 0, "logs_usable": 20, "boulders_usable": 0,
                   **(stocks or {})},
        "administrators": {"citizens": cit},
        "dwarves": people,
        "workshops": workshops or [],
        "map": {"surface_z": 70, "sites": sites or [{"id": "A1", "kind": "A", "x": 10, "y": 10, "z": 74,
                                                    "w": 10, "h": 8, "open_tiles": 60}]},
        "orders": orders or [],
        "zones": [],
        "furniture": list(furniture),
    }


def resp(cit=10, **kw):
    o = obs(cit=cit, **kw)
    return {"observation": o, "day": 5, "tick": 5 * 1200, "days_left": 30}


class TestGoalPolicies(unittest.TestCase):
    def make(self, answers=()):
        game = StubGame(answers)
        return Overseer(game), game

    def test_policy_detection(self):
        ov, _ = self.make()
        ov.set_task({"goal": "By day 60 every dwarf must have a placed bed, drink and food in stock; "
                            "and drink must not end lower than it was on day 39.", "hands_off": {"from_day": 39}})
        self.assertTrue(ov.beds_first)
        self.assertTrue(ov.drink_growth)
        ov2, _ = self.make()
        ov2.set_task({"goal": "Run the fortress for 336 days.", "hands_off": None})
        self.assertFalse(ov2.beds_first)
        self.assertFalse(ov2.drink_growth)
        ov3, _ = self.make()
        ov3.set_task({"goal": "drink must not end lower", "hands_off": None})   # an open task: no goal policy
        self.assertFalse(ov3.drink_growth)

    def test_brew_growth_has_no_drink_ceiling(self):
        ov, game = self.make()
        ov.set_task({"goal": "drink must not end lower", "hands_off": {"from_day": 39}})
        ov.load(resp())
        ov.count = 0
        ov.supply()
        brews = [c for c in game.calls if c[0] == "add_order" and c[1].get("recipe") == "brew_drink"]
        self.assertEqual(len(brews), 1)
        stocks = [w for w in brews[0][1].get("when", []) if w.get("stock") == "drink"]
        self.assertEqual(stocks, [], "the drink-growth brew order must carry no drink condition")

    def test_regular_brew_keeps_its_ceiling(self):
        ov, game = self.make()
        ov.load(resp())
        ov.count = 0
        ov.supply()
        brews = [c for c in game.calls if c[0] == "add_order" and c[1].get("recipe") == "brew_drink"]
        self.assertTrue(any(w.get("stock") == "drink" for w in brews[0][1]["when"]))

    def test_beds_first_skips_seat_orders_and_keeps_beds(self):
        ov, game = self.make()
        ov.set_task({"goal": "every dwarf must have a placed bed", "hands_off": {"from_day": 39}})
        ov.load(resp(cit=10, beds_stock=6))
        ov.count = 0
        ov.supply()
        recipes = [c[1].get("recipe") for c in game.calls if c[0] == "add_order"]
        self.assertIn("make_bed", recipes)
        self.assertNotIn("make_table", recipes)
        self.assertNotIn("make_chair", recipes)
        game.calls.clear()
        ov.furnish()
        kinds = [c[1].get("kind") for c in game.calls if c[0] == "place_furniture"]
        self.assertEqual(kinds, ["bed"], "beds first: no seat placement while the bed goal has a shortfall")

    def test_second_carpenters_for_the_bed_goal(self):
        ov, game = self.make()
        ov.set_task({"goal": "every dwarf must have a placed bed", "hands_off": {"from_day": 39}})
        ov.load(resp(sites=[{"id": t, "kind": "W", "x": 5 * i + 1, "y": 1, "z": 75, "w": 3, "h": 3}
                            for i, t in enumerate(("W2", "W3", "W4"))] + obs()["map"]["sites"]))
        ov.o["workshops"] = [{"type": "Carpenters", "built": True, "x": 1, "y": 1, "z": 75, "w": 3, "h": 3,
                              "jobs": []}]
        ov.count = 0
        ov.workshops()
        builds = [c for c in game.calls if c[0] == "build_workshop"]
        carps = [b for b in builds if b[1].get("type") == "Carpenters"]
        self.assertEqual(len(carps), 1, "one second Carpenters on the wave task (the first took its site already)")

    def test_bed_fallback_to_next_largest_area(self):
        ov, game = self.make([
            {"ok": False, "error_code": "no_space", "error": "no space in the dorm box"},   # primary: no_space
            {"ok": True, "result": {"at": [45, 12, 74]}},                                  # alternate: placed (in A2)
        ])
        ov.set_task({"goal": "every dwarf must have a placed bed", "hands_off": {"from_day": 39}})
        ov.load(resp(cit=30, sites=[
            {"id": "A1", "kind": "A", "x": 10, "y": 10, "z": 74, "w": 9, "h": 7, "open_tiles": 60},
            {"id": "A2", "kind": "A", "x": 40, "y": 10, "z": 74, "w": 10, "h": 14, "open_tiles": 90}], beds_stock=32))
        ov.count = 0
        ov.furnish()
        placements = [c for c in game.calls if c[0] == "place_furniture" and c[1].get("kind") == "bed"]
        self.assertEqual([p[1].get("site") for p in placements], ["A1", "A2"])
        zones = [c for c in game.calls if c[0] == "make_zone"]
        self.assertTrue(any(z[1].get("site") == "A2" for z in zones), "the alternate's furniture gets a zone too")

    def test_overflow_runs_without_the_bed_goal(self):
        # housing counts placed beds on every task: the dorm-full fallback is not a lab-goal privilege
        ov, game = self.make([
            {"ok": False, "error_code": "no_space", "error": "no space in the dorm box"},
            {"ok": True, "result": {"at": [45, 12, 74]}},
        ])
        ov.load(resp(cit=30, sites=[
            {"id": "A1", "kind": "A", "x": 10, "y": 10, "z": 74, "w": 9, "h": 7, "open_tiles": 60},
            {"id": "A2", "kind": "A", "x": 40, "y": 10, "z": 74, "w": 10, "h": 14, "open_tiles": 90}], beds_stock=32))
        ov.count = 0
        ov.furnish()
        placements = [c for c in game.calls if c[0] == "place_furniture" and c[1].get("kind") == "bed"]
        self.assertEqual([p[1].get("site") for p in placements], ["A1", "A2"])
        self.assertFalse(ov.beds_first, "no goal text: the policies stay off, the fallback still runs")

    def test_progress_keeps_crafting_past_the_hamlet_wealth(self):
        # each rank gained counts 0.5 progress steps without exports and an elected mayor 1.0, so the standing
        # wood crafts order lasts the whole run; the Hamlet's wealth number only gates the first Craftsdwarfs build
        ov, game = self.make()
        ov.days = 336
        ov.load(resp(beds_stock=0, stocks={"boulders_usable": 5},
                     workshops=[{"type": "Craftsdwarfs", "built": True}],
                     orders=[{"id": 7, "job": "MakeCrafts", "left": 0, "repeat": "daily",
                              "material_category": ["wood"]}]))
        ov.day = 40
        ov.o["wealth"] = {"created": 99999}
        ov.count = 0
        ov.progress()
        self.assertFalse(any(c[0] == "build_workshop" for c in game.calls), "no second Craftsdwarfs at the cap")
        self.assertFalse(game.calls, "the wood order stands, stone waits for stock: no actions this day")

    def test_progress_adds_the_stone_crafts_order(self):
        # stone is dug out of every level and competes with no bed or barrel: a second crafts order from it
        ov, game = self.make()
        ov.days = 336
        ov.load(resp(beds_stock=0, stocks={"boulders_usable": 60},
                     workshops=[{"type": "Craftsdwarfs", "built": True}],
                     orders=[{"id": 7, "job": "MakeCrafts", "left": 0, "repeat": "daily",
                              "material_category": ["wood"]}]))
        ov.day = 40
        ov.o["wealth"] = {"created": 99999}
        ov.count = 0
        ov.progress()
        stone = [c for c in game.calls if c[0] == "add_manager_order"
                 and "stone" in (c[1].get("material_category") or [])]
        self.assertEqual(len(stone), 1, "one standing stone crafts order")
        self.assertEqual(json.loads(json.dumps(stone[0][1].get("when")))[0].get("item_type"), "BOULDER")

    def test_fallback_waits_for_a_real_no_space(self):
        ov, game = self.make([
            {"ok": False, "error_code": "bad_site", "error": "not a site"},
        ])
        ov.set_task({"goal": "every dwarf must have a placed bed", "hands_off": {"from_day": 39}})
        ov.load(resp(cit=30, sites=[
            {"id": "A1", "kind": "A", "x": 10, "y": 10, "z": 74, "w": 9, "h": 7, "open_tiles": 60},
            {"id": "A2", "kind": "A", "x": 40, "y": 10, "z": 74, "w": 10, "h": 14, "open_tiles": 90}], beds_stock=32))
        ov.count = 0
        ov.furnish()
        placements = [c for c in game.calls if c[0] == "place_furniture" and c[1].get("kind") == "bed"]
        self.assertEqual([p[1].get("site") for p in placements], ["A1"],
                         "only an actual no_space moves to the alternate area")

    def test_beds_unmet_reads_the_observation(self):
        ov, _ = self.make()
        ov.set_task({"goal": "every dwarf must have a placed bed", "hands_off": {"from_day": 39}})
        ov.load(resp(cit=13, furniture=[{"kind": "bed", "built": True, "x": 1, "y": 1, "z": 74}] * 12))
        self.assertTrue(ov.beds_unmet())
        ov.load(resp(cit=13, furniture=[{"kind": "bed", "built": True, "x": 1, "y": 1, "z": 74}] * 13))
        self.assertFalse(ov.beds_unmet())
        ov2, _ = self.make()   # no goal: never reports unmet
        ov2.load(resp(cit=13))
        self.assertFalse(ov2.beds_unmet())

    def test_layer_owned_brew_cancel_is_disclosed_by_state(self):
        # the brew_own record survives: the goal policy's own brew is not re-added while the order stands
        ov, game = self.make([
            {"ok": True, "result": {"order_id": 17}},
        ])
        ov.set_task({"goal": "drink must not end lower", "hands_off": {"from_day": 39}})
        ov.load(resp())
        ov.count = 0
        ov.supply()
        self.assertEqual(ov.brew_orders, {17})
        game.calls.clear()
        # same observation (the order list is stale and doesn't name it yet): no second add
        ov.load(resp(orders=[]))
        ov.count = 0
        ov.last = {k: ov.now for k in ov.last}
        ov.supply()
        self.assertFalse(any(c[0] == "add_order" for c in game.calls if c[1].get("recipe") == "brew_drink"))

    def test_garbage_task_never_raises(self):
        for info in (None, {}, {"goal": 3}, {"goal": None, "hands_off": 4}, {"hands_off": {"from_day": 39}}):
            ov, _ = self.make()
            ov.set_task(info)
            self.assertIsInstance(ov.beds_first, bool)
            self.assertIsInstance(ov.drink_growth, bool)


if __name__ == "__main__":
    unittest.main()
