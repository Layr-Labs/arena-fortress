"""Check the bed-only fallback with recorded areas and offline responses."""
import copy
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness
from test_room_zones import facts, site, zone

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class FakeGame:
    def __init__(self):
        self.calls = []
        self.responses = {"A7": {"ok": False, "error_code": "no_space"},
                          "A2": {"ok": True, "result": {"n": 1, "at": [91, 96, 77]}}}

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if tool == "place_furniture":
            return copy.deepcopy(self.responses[args["site"]])
        return {"ok": True, "result": {"zone_id": len(self.calls)}}


class BedFallback(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.game = FakeGame()
        self.agent = harness.Overseer(self.game)
        self.agent.beds_first = True
        self.agent.count = 0
        self.primary = site("A7", x=93, y=91, z=75, w=9, h=7, open_tiles=63)
        self.alternate = site("A2", x=90, y=86, z=77, w=10, h=14, open_tiles=85)
        self.rooms = [site("R7", x=93, y=91, z=75, dug=True),
                      site("R8", x=90, y=86, z=77, w=7, h=5, dug=True, soil=True)]
        self.agent.roles = {"R7": "dorm", "R8": "farm"}
        self.load()

    def load(self, zones=(), furniture=(), extra=(), free=5, day=0):
        resp = facts([self.primary, self.alternate] + self.rooms + list(extra),
                     zones, furniture, free={"bed": free}, day=day)
        resp["observation"]["administrators"]["citizens"] = 47
        resp["observation"]["farm_plots"] = [
            {"id": 51, "x": 90, "y": 86, "z": 77, "w": 3, "h": 3}]
        self.agent.load(resp)

    def placements(self):
        return [args for tool, args in self.game.calls if tool == "place_furniture"]

    def zones(self):
        return [args for tool, args in self.game.calls if tool == "make_zone"]

    def test_recorded_a7_failure_uses_a2_on_farm_level_and_zones_expanded_area(self):
        beds = [{"kind": "bed", "x": 93 + n % 9, "y": 91 + n // 9, "z": 75}
                for n in range(44)]
        old = [zone("Dormitory", x=93, y=91, z=75, w=9, h=7),
               zone("Dormitory", x=90, y=86, z=77, w=10, h=8)]
        self.load(old, beds)
        self.agent.furnish()
        self.assertEqual(self.placements(), [
            {"kind": "bed", "site": "A7", "count": 5},
            {"kind": "bed", "site": "A2", "count": 5}])
        self.assertEqual(self.zones(), [{"kind": "dormitory", "site": "A2"}])
        self.assertEqual(self.agent.last["beds_A2"], 0)
        self.assertEqual(self.agent.last["z_dorm_A2"], 0)

    def test_general_bed_shortfall_falls_back_the_same_way(self):
        # PR36 gated the alternate area on the LT08 goal text; the general shortfall (0 placed beds for 47
        # citizens) now triggers it too, so any long task can recover from a no_space primary.
        self.agent.beds_first = False
        self.agent.furnish()
        self.assertEqual([a["site"] for a in self.placements()], ["A7", "A2"])
        self.assertEqual(self.zones(), [{"kind": "dormitory", "site": "A2"}])

    def test_no_shortfall_does_not_fall_back(self):
        self.agent.beds_first = False
        self.load(furniture=[{"kind": "bed", "x": 10 + n, "y": 10, "z": 9} for n in range(47)])
        self.assertFalse(self.agent.beds_short)
        self.agent.furnish()
        self.assertEqual([a["site"] for a in self.placements()], ["A7"])
        self.assertEqual(self.zones(), [])

    def test_other_error_does_not_fall_back(self):
        self.game.responses["A7"] = {"ok": False, "error_code": "no_item"}
        self.agent.furnish()
        self.assertEqual([a["site"] for a in self.placements()], ["A7"])
        self.assertEqual(self.zones(), [])

    def test_blocked_primary_does_not_fall_back(self):
        for gate in ("retry", "limit"):
            with self.subTest(gate=gate):
                self.game.calls.clear()
                self.agent.last.clear()
                self.agent.tries.clear()
                if gate == "retry":
                    self.agent.last["beds"] = 0
                else:
                    self.agent.tries["beds"] = 99
                self.agent.furnish()
                self.assertEqual(self.game.calls, [])

    def test_no_spare_bed_does_not_fall_back(self):
        self.load(free=0)
        self.agent.furnish()
        self.assertEqual(self.game.calls, [])

    def test_partial_primary_success_does_not_fall_back(self):
        self.game.responses["A7"] = {"ok": True, "result": {"n": 1, "at": [[94, 92, 75]]}}
        self.agent.furnish()
        self.assertEqual([a["site"] for a in self.placements()], ["A7"])
        self.assertEqual(self.zones(), [{"kind": "dormitory", "site": "A7"}])

    def test_partial_alternate_uses_returned_points_for_coverage(self):
        old = [zone("Dormitory", x=90, y=86, z=77, w=10, h=8)]
        for points, expected in (([[91, 87, 77]], []),
                                 ([[91, 87, 77], [91, 96, 77]], [{"kind": "dormitory", "site": "A2"}])):
            with self.subTest(points=points):
                self.game.calls.clear()
                self.agent.last.clear()
                self.game.responses["A2"] = {"ok": True, "result": {"n": len(points), "at": points}}
                self.load(old)
                self.agent.furnish()
                self.assertEqual(self.placements()[-1]["count"], 5)
                self.assertEqual(self.zones(), expected)

    def test_failed_alternate_does_not_add_an_empty_zone_or_try_third_area(self):
        self.game.responses["A2"] = {"ok": False, "error_code": "no_space"}
        self.load(extra=[site("A3", z=74, open_tiles=84)])
        self.agent.furnish()
        self.assertEqual([a["site"] for a in self.placements()], ["A7", "A2"])
        self.assertEqual(self.zones(), [])
        self.assertEqual(self.agent.tries["beds_A2"], 1)

    def test_primary_is_excluded_even_if_it_has_most_open_tiles(self):
        self.primary["open_tiles"] = 100
        self.load()
        self.agent.furnish()
        self.assertEqual([a["site"] for a in self.placements()], ["A7", "A2"])

    def test_alternate_rank_is_deterministic_and_skips_stair_only_area(self):
        self.load(extra=[site("A0", open_tiles=5), site("A3", open_tiles=85)])
        self.agent.furnish()
        self.assertEqual([a["site"] for a in self.placements()], ["A7", "A2"])

    def test_stair_only_alternate_is_not_used(self):
        self.alternate["open_tiles"] = 5
        self.load()
        self.agent.furnish()
        self.assertEqual([a["site"] for a in self.placements()], ["A7"])

    def test_open_tiles_does_not_limit_requested_bed_count(self):
        self.alternate["open_tiles"] = 6
        self.load(free=40)
        self.agent.furnish()
        self.assertEqual([a["count"] for a in self.placements()], [30, 30])

    def test_single_area_does_not_retry_primary(self):
        self.agent.sites = [self.primary] + self.rooms
        self.agent.furnish()
        self.assertEqual([a["site"] for a in self.placements()], ["A7"])

    def test_alternate_retry_and_limit_gates_are_retained(self):
        for gate in ("retry", "limit"):
            with self.subTest(gate=gate):
                self.game.calls.clear()
                self.agent.last.clear()
                self.agent.tries.clear()
                if gate == "retry":
                    self.agent.last["beds_A2"] = 0
                else:
                    self.agent.tries["beds_A2"] = 99
                self.agent.furnish()
                self.assertEqual([a["site"] for a in self.placements()], ["A7"])
                self.assertEqual(self.zones(), [])

    def test_both_placement_keys_retry_after_one_day(self):
        self.game.responses["A2"] = {"ok": False, "error_code": "no_space"}
        self.agent.furnish()
        self.game.calls.clear()
        self.agent.furnish()
        self.assertEqual(self.game.calls, [])
        self.load(day=1)
        self.agent.furnish()
        self.assertEqual([a["site"] for a in self.placements()], ["A7", "A2"])

    def test_failed_alternate_still_zones_existing_uncovered_beds(self):
        self.game.responses["A2"] = {"ok": False, "error_code": "no_space"}
        self.load(furniture=[{"kind": "bed", "x": 91, "y": 96, "z": 77}])
        self.agent.furnish()
        self.assertEqual(self.zones(), [{"kind": "dormitory", "site": "A2"}])

    def test_primary_and_alternate_can_both_get_needed_zones(self):
        self.load(furniture=[{"kind": "bed", "x": 94, "y": 92, "z": 75}])
        self.agent.furnish()
        self.assertEqual(self.zones(), [{"kind": "dormitory", "site": "A7"},
                                       {"kind": "dormitory", "site": "A2"}])


if __name__ == "__main__":
    unittest.main()
