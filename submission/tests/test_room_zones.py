"""Regressions for shared room coverage. No game or network is used."""
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
    def __init__(self):
        self.calls = []
        self.at = {"bed": [11, 11, 9], "table": [12, 11, 9], "chair": [11, 12, 9]}
        self.fail = set()

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if tool == "place_furniture":
            if args["kind"] in self.fail:
                return {"ok": False, "error_code": "no_space"}
            at = self.at[args["kind"]]
            n = len(at) if isinstance(at[0], list) else 1
            return {"ok": True, "result": {"n": n, "at": copy.deepcopy(at)}}
        return {"ok": True, "result": {"zone_id": len(self.calls)}}


def site(id="A1", x=10, y=10, z=9, w=7, h=6, open_tiles=32, **kw):
    return {"id": id, "kind": id[0], "x": x, "y": y, "z": z,
            "w": w, "h": h, "open_tiles": open_tiles, **kw}


def zone(kind, x=10, y=10, z=9, w=7, h=6, **kw):
    return {"type": kind, "x": x, "y": y, "z": z, "w": w, "h": h, **kw}


def facts(sites, zones=(), furniture=(), free=None, day=0):
    return {"tick": day * harness.DAY, "observation": {
        "administrators": {"citizens": 7}, "map": {"sites": copy.deepcopy(sites)},
        "zones": copy.deepcopy(list(zones)), "furniture": copy.deepcopy(list(furniture)),
        "stocks": {"furniture_free": free or {}}}}


class RoomZones(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.reset()

    def reset(self):
        self.game = FakeGame()
        self.overseer = harness.Overseer(self.game)
        self.overseer.count = 0

    def load(self, *args, **kw):
        self.overseer.load(facts(*args, **kw))

    def zone_calls(self):
        return [args for tool, args in self.game.calls if tool == "make_zone"]

    def test_stair_only_area_does_not_get_shared_zones(self):
        self.load([site(w=1, h=1, open_tiles=1)], free={"bed": 1, "table": 1, "chair": 1})
        self.overseer.furnish()
        self.assertEqual(self.game.calls, [])

    def test_expanded_area_covers_furniture_outside_old_zones_once(self):
        old = [zone("Dormitory", w=1, h=1), zone("DiningHall", w=1, h=1)]
        furniture = [{"kind": kind, "x": x, "y": 11, "z": 9}
                     for x, kind in enumerate(("bed", "table", "chair"), 12)]
        self.load([site()], old, furniture)
        self.overseer.furnish()
        self.assertEqual(self.zone_calls(), [{"kind": "dormitory", "site": "A1"},
                                            {"kind": "dining_hall", "site": "A1"}])
        self.game.calls.clear()
        covered = old + [zone("Dormitory"), zone("DiningHall")]
        self.load([site()], covered, furniture, day=4)
        self.overseer.furnish()
        self.assertEqual(self.zone_calls(), [])

    def test_correct_existing_zones_do_not_change(self):
        self.load([site()], [zone("Dormitory"), zone("DiningHall")],
                  free={"bed": 1, "table": 1, "chair": 1})
        self.overseer.furnish()
        self.assertEqual(self.zone_calls(), [])
        self.assertEqual([tool for tool, _ in self.game.calls], ["place_furniture"] * 3)

    def test_expansion_without_uncovered_or_new_furniture_adds_no_zone(self):
        bedroom = zone("Bedroom", w=3, h=3, owner=83)
        furniture = [{"kind": "bed", "x": 11, "y": 11, "z": 9}]
        self.load([site()], [bedroom], furniture)
        self.overseer.furnish()
        self.assertEqual(self.zone_calls(), [])

    def test_private_bedroom_covering_target_does_not_get_a_dormitory(self):
        self.load([site(w=3, h=3, open_tiles=9)],
                  [zone("Bedroom", w=3, h=3, owner=83)], free={"bed": 1})
        self.overseer.furnish()
        self.assertEqual(self.zone_calls(), [])

    def test_new_furniture_on_expanded_area_gets_shared_zone(self):
        self.game.at["bed"] = [13, 11, 9]
        self.load([site()], [zone("Dormitory", w=3, h=3)], free={"bed": 1})
        self.overseer.furnish()
        self.assertEqual(self.zone_calls(), [{"kind": "dormitory", "site": "A1"}])

    def test_fallback_skips_stair_and_farm_levels(self):
        self.load([site("R1", z=8, soil=True, designated=True, dug=True),
                   site("A1", w=1, h=1, open_tiles=1), site("A2", z=8), site("A3", z=7)])
        self.overseer.roles["R1"] = "farm"
        self.assertEqual(self.overseer.room_for("dorm")["id"], "A3")

    def test_zone_on_another_level_does_not_cover_furniture(self):
        self.load([site()], [zone("Dormitory", z=8)],
                  [{"kind": "bed", "x": 11, "y": 11, "z": 9}])
        self.overseer.furnish()
        self.assertEqual(self.zone_calls(), [{"kind": "dormitory", "site": "A1"}])

    def test_dug_role_room_remains_fallback_when_area_site_is_absent(self):
        self.load([site("R1", w=3, h=3, dug=True, designated=True)])
        self.overseer.roles["R1"] = "dorm"
        self.assertEqual(self.overseer.room_for("dorm")["id"], "R1")

    def test_new_furniture_inside_old_zone_does_not_expand_it(self):
        self.load([site()], [zone("Dormitory", w=3, h=3)], free={"bed": 1})
        self.overseer.furnish()
        self.assertEqual(self.zone_calls(), [])
        self.assertEqual([tool for tool, _ in self.game.calls], ["place_furniture"])

    def test_zone_boundary_uses_the_returned_furniture_tile(self):
        for x, expected in ((12, []), (13, [{"kind": "dormitory", "site": "A1"}])):
            with self.subTest(x=x):
                self.reset()
                self.game.at["bed"] = [x, 12, 9]
                self.load([site()], [zone("Dormitory", w=3, h=3)], free={"bed": 1})
                self.overseer.furnish()
                self.assertEqual(self.zone_calls(), expected)
                self.assertEqual(self.game.calls[0][0], "place_furniture")

    def test_partial_placement_uses_only_returned_coordinates(self):
        for points, expected in (([[11, 11, 9], [12, 11, 9]], []),
                                 ([[12, 11, 9], [13, 11, 9]], [{"kind": "dormitory", "site": "A1"}])):
            with self.subTest(points=points):
                self.reset()
                self.game.at["bed"] = points
                self.load([site()], [zone("Dormitory", w=3, h=3)], free={"bed": 5})
                self.overseer.furnish()
                self.assertEqual(self.game.calls[0][0], "place_furniture")
                self.assertEqual(self.game.calls[0][1]["count"], 5)
                self.assertEqual(self.zone_calls(), expected)

    def test_failed_or_retry_blocked_placement_does_not_create_an_empty_zone(self):
        for blocked in (False, True):
            with self.subTest(blocked=blocked):
                self.reset()
                if blocked:
                    self.overseer.last["beds"] = 0
                else:
                    self.game.fail.add("bed")
                self.load([site()], free={"bed": 1})
                self.overseer.furnish()
                self.assertEqual(self.zone_calls(), [])

    def test_failed_new_placement_still_zones_existing_uncovered_furniture(self):
        self.game.fail.add("bed")
        self.load([site()], [zone("Dormitory", w=3, h=3)],
                  [{"kind": "bed", "x": 13, "y": 11, "z": 9}], free={"bed": 1})
        self.overseer.furnish()
        self.assertEqual(self.zone_calls(), [{"kind": "dormitory", "site": "A1"}])
        self.assertEqual([tool for tool, _ in self.game.calls], ["place_furniture", "make_zone"])

    def test_day_25_dining_placements_remain_inside_old_zone(self):
        self.game.at = {"bed": [[90, 99, 103], [91, 99, 103], [92, 99, 103]],
                        "table": [[93, 99, 103], [97, 99, 103], [98, 99, 103]],
                        "chair": [[99, 99, 103], [100, 99, 103], [101, 99, 103]]}
        old = [zone("Dormitory", x=93, y=99, z=103, w=10, h=7),
               zone("DiningHall", x=93, y=99, z=103, w=10, h=7)]
        self.load([site("A8", x=90, y=99, z=103, w=13, h=7, open_tiles=83)], old,
                  free={"bed": 3, "table": 3, "chair": 3})
        self.overseer.furnish()
        self.assertEqual(self.zone_calls(), [{"kind": "dormitory", "site": "A8"}])
        self.assertEqual([tool for tool, _ in self.game.calls],
                         ["place_furniture", "make_zone", "place_furniture", "place_furniture"])

    def test_dining_checks_both_placements_before_adding_one_zone(self):
        self.game.at["table"], self.game.at["chair"] = [12, 11, 9], [13, 11, 9]
        self.load([site()], [zone("DiningHall", w=3, h=3)], free={"table": 1, "chair": 1})
        self.overseer.furnish()
        self.assertEqual(self.zone_calls(), [{"kind": "dining_hall", "site": "A1"}])
        self.assertEqual([tool for tool, _ in self.game.calls],
                         ["place_furniture", "place_furniture", "make_zone"])

    def test_separate_existing_zones_can_cover_all_new_furniture(self):
        self.game.at["bed"] = [[12, 11, 9], [13, 11, 9]]
        old = [zone("Dormitory", w=3), zone("Bedroom", x=13, w=3, owner=83)]
        self.load([site()], old, free={"bed": 2})
        self.overseer.furnish()
        self.assertEqual(self.zone_calls(), [])


if __name__ == "__main__":
    unittest.main()
