"""Regressions for room role assignment and site use. No game or network is used."""
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


class FakeGame:
    def __init__(self, failures=0):
        self.failures, self.calls, self.used = failures, [], set()

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if self.failures:
            self.failures -= 1
            return {"ok": False, "error_code": "tile_hidden" if tool == "dig_room" else "no_material"}
        if tool == "build_workshop":
            if args["site"] in self.used:
                return {"ok": False, "error_code": "site_used"}
            self.used.add(args["site"])
        return {"ok": True, "result": {"id": len(self.calls)}}


def facts(sites):
    return {"tick": 0, "observation": {"administrators": {"citizens": 7},
            "stocks": {"logs_usable": 10}, "map": {"surface_z": 10, "sites": copy.deepcopy(sites)}}}


def room(soil):
    return {"id": "R1", "kind": "R", "soil": soil, "designated": False, "dug": False,
            "free": True, "x": 10, "y": 10, "z": 9}


def workshops():
    return [{"id": "W" + str(i), "kind": "W", "free": True, "x": 10*i, "y": 10, "z": 10}
            for i in range(1, 4)]


class Repairs(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, sites, failures=0):
        game = FakeGame(failures)
        overseer = harness.Overseer(game)
        overseer.load(facts(sites))
        overseer.count = 0
        return overseer, game

    def test_failed_farm_dig_keeps_role_free_and_retries_after_delay(self):
        self.check_failed_dig(True, "farm")

    def test_failed_room_dig_keeps_role_free_and_retries_after_delay(self):
        self.check_failed_dig(False, "dorm")

    def check_failed_dig(self, soil, role):
        overseer, game = self.overseer([room(soil)], failures=1)
        overseer.digging()
        self.assertEqual(overseer.roles, {})
        self.assertEqual(overseer.tries["dig_R1"], 1)
        self.assertEqual(overseer.last["dig_R1"], 0)
        overseer.now = 2 * harness.DAY
        overseer.digging()
        self.assertEqual(len(game.calls), 1)
        self.assertEqual(overseer.roles, {})
        overseer.now = 3 * harness.DAY
        overseer.digging()
        self.assertEqual(len(game.calls), 2)
        self.assertEqual(overseer.roles, {"R1": role})
        self.assertEqual(overseer.tries["dig_R1"], 1)

    def test_successful_dig_assigns_role_once(self):
        for soil, role in ((True, "farm"), (False, "dorm")):
            with self.subTest(soil=soil):
                overseer, game = self.overseer([room(soil)])
                overseer.digging()
                overseer.now = 3 * harness.DAY
                overseer.digging()
                self.assertEqual(overseer.roles, {"R1": role})
                self.assertEqual(len(game.calls), 1)
                self.assertEqual(overseer.tries["dig_R1"], 0)
                if role == "dorm":
                    self.assertEqual(game.calls[0][1], {"site": "R1", "w": 9, "h": 7})

    def test_drink_growth_goal_removes_ceiling_only_for_a_lab_window(self):
        for window, capped in ((39, False), (None, True)):
            with self.subTest(window=window):
                overseer, game = self.overseer([])
                overseer.drink_growth = True
                overseer.hands_off = window
                overseer.supply()
                brew = next(args for tool, args in game.calls
                            if tool == "add_order" and args.get("recipe") == "brew_drink")
                self.assertEqual(any(c.get("stock") == "drink" for c in brew["when"]), capped)
                self.assertTrue(any(c.get("stock") == "plants_brewable" for c in brew["when"]))
                self.assertTrue(any(c.get("stock") == "barrels_empty" for c in brew["when"]))

    def test_migrant_bed_deficit_does_not_queue_dining_furniture(self):
        overseer, game = self.overseer([])
        overseer.surge = True
        overseer.supply()
        recipes = [args.get("recipe") for tool, args in game.calls if tool == "add_order"]
        self.assertIn("make_bed", recipes)
        self.assertNotIn("make_table", recipes)
        self.assertNotIn("make_chair", recipes)

    def test_migrant_bed_batch_covers_a_large_observed_shortfall(self):
        overseer, game = self.overseer([])
        overseer.surge = True
        overseer.cit = 51
        overseer.st["beds"] = 19
        overseer.supply()
        bed = next(args for tool, args in game.calls
                   if tool == "add_order" and args.get("recipe") == "make_bed")
        self.assertEqual(bed["amount"], 30)

    def test_migrant_carpenter_capacity_scales_with_population(self):
        overseer, game = self.overseer(workshops())
        overseer.surge = True
        overseer.cit = 45
        overseer.o["workshops"] = [{"type": "Carpenters"}] * 2
        overseer.closer()
        self.assertEqual(game.calls, [("build_workshop", {"type": "Carpenters", "site": "W1"})])
        game.calls.clear()
        overseer.o["workshops"] = [{"type": "Carpenters"}] * 3
        overseer.closer()
        self.assertEqual(game.calls, [])

    def test_large_migrant_wave_can_reserve_an_additional_dorm(self):
        overseer, game = self.overseer([room(True)])
        overseer.o["farm_plots"] = [{"id": n} for n in range(4)]
        overseer.roles = {"R10": "dorm", "R11": "dine", "R12": "office"}
        overseer.surge = True
        overseer.cit = 51
        overseer.placed = {"bed": 43}
        overseer.digging()
        self.assertEqual(overseer.roles["R1"], "dorm")
        self.assertEqual(game.calls[0][1], {"site": "R1", "w": 9, "h": 7})

    def test_two_existing_farms_leave_next_soil_room_for_housing(self):
        overseer, game = self.overseer([room(True)])
        overseer.o["farm_plots"] = [{"id": 4}, {"id": 5}]
        overseer.cit = 52
        overseer.digging()
        self.assertEqual(overseer.roles["R1"], "dorm")

    def test_farm_candidates_do_not_consume_housing_level(self):
        sites = [room(True),
                 {"id": "F1", "kind": "F", "z": 9},
                 {"id": "F2", "kind": "F", "z": 8}]
        overseer, game = self.overseer(sites)
        overseer.roles["R1"] = "dorm"
        overseer.farms()
        self.assertEqual([args["site"] for tool, args in game.calls if tool == "build_farm"], ["F2"])

    def test_failed_dig_retains_existing_retry_limit(self):
        overseer, game = self.overseer([room(True)], failures=2)
        for day in (0, 3, 6):
            overseer.now = day * harness.DAY
            overseer.digging()
        self.assertEqual(len(game.calls), 2)
        self.assertEqual(overseer.tries["dig_R1"], 2)
        self.assertEqual(overseer.roles, {})

    def test_successful_workshops_use_three_distinct_sites(self):
        overseer, game = self.overseer(workshops())
        overseer.workshops()
        self.assertEqual([(a["type"], a["site"]) for _, a in game.calls],
                         [("Carpenters", "W1"), ("Still", "W2"), ("Kitchen", "W3")])
        self.assertEqual(game.used, {"W1", "W2", "W3"})
        self.assertEqual(overseer.kind("W"), [])

    def test_failed_build_keeps_site_for_next_workshop(self):
        overseer, game = self.overseer(workshops(), failures=1)
        overseer.workshops()
        self.assertEqual([(a["type"], a["site"]) for _, a in game.calls],
                         [("Carpenters", "W1"), ("Still", "W1"), ("Kitchen", "W2")])
        self.assertEqual([s["id"] for s in overseer.kind("W")], ["W3"])

    def test_retry_gate_does_not_consume_a_site(self):
        overseer, game = self.overseer(workshops(), failures=1)
        overseer.build("Carpenters")
        self.assertEqual([s["id"] for s in overseer.kind("W")], ["W1", "W2", "W3"])
        overseer.build("Carpenters")
        self.assertEqual(len(game.calls), 1)
        self.assertEqual([s["id"] for s in overseer.kind("W")], ["W1", "W2", "W3"])
        overseer.build("Still")
        self.assertEqual([s["id"] for s in overseer.kind("W")], ["W2", "W3"])
        self.assertEqual(overseer.tries["ws_Carpenters"], 1)
        self.assertEqual(overseer.last["ws_Carpenters"], 0)


if __name__ == "__main__":
    unittest.main()
