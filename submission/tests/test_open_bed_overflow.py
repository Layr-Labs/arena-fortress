"""Synthetic API-contract fixtures, not measurements of DF or hidden forts."""
import io
import json
from contextlib import redirect_stdout
import unittest

from support import StubGame, overseer, resp


class FurnitureGame(StubGame):
    def __init__(self, primary):
        super().__init__()
        self.primary = primary

    def act(self, tool, args):
        self.calls.append((tool, json.loads(json.dumps(args))))
        if tool == "place_furniture" and args.get("kind") == "bed":
            if args["site"] == "A1":
                return self.primary
            return {"ok": True, "result": {"at": [[20 + i, 20, 99] for i in range(args["count"])]}}
        return {"ok": True, "result": {}}


class OpenBedOverflow(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def scenario(self, primary, citizens=10, beds=6):
        r = resp(days_left=36, day=300, food=100, drink=100, cit=citizens)
        o = r["observation"]
        o["stocks"]["furniture_free"] = {"bed": 8}
        o["furniture"] = [{"kind": "bed", "built": True, "x": i, "y": 1, "z": 100} for i in range(beds)]
        o["map"]["sites"] = [
            {"id": "A1", "kind": "A", "x": 0, "y": 0, "z": 100, "w": 9, "h": 7, "open_tiles": 60},
            {"id": "A2", "kind": "A", "x": 20, "y": 20, "z": 99, "w": 9, "h": 7, "open_tiles": 60},
        ]
        o["zones"] = []
        ov, _ = overseer(r)
        g = FurnitureGame(primary)
        ov.game = g
        return ov, g

    def bed_calls(self, game, site="A2"):
        return [args for args in game.tools("place_furniture") if args.get("kind") == "bed" and args.get("site") == site]

    def test_no_space_fills_only_the_scored_shortfall(self):
        ov, g = self.scenario({"ok": False, "error_code": "no_space"})
        needed = ov.cit - ov.placed.get("bed", 0)
        ov.furnish()
        self.assertEqual([a["count"] for a in self.bed_calls(g)], [needed])

    def test_no_new_overflow_when_population_is_already_housed(self):
        ov, g = self.scenario({"ok": False, "error_code": "no_space"}, beds=10)
        ov.furnish()
        self.assertEqual(self.bed_calls(g), [])

    def test_unknown_or_unrecognized_placement_receipts_do_not_create_overflow(self):
        for response in ({"ok": False, "error_code": "bad_arguments"}, {"ok": True, "result": {}}, {"ok": True, "result": {"at": [["x", 0, 100]]}}):
            with self.subTest(response=response):
                ov, g = self.scenario(response)
                ov.furnish()
                self.assertEqual(self.bed_calls(g), [])

    def test_rate_limited_primary_does_not_trigger_an_extra_attempt(self):
        ov, g = self.scenario({"ok": False, "error_code": "no_space"})
        ov.done.add("beds")
        ov.furnish()
        self.assertEqual(self.bed_calls(g), [])

    def test_same_observation_does_not_retry_the_overflow(self):
        ov, g = self.scenario({"ok": False, "error_code": "no_space"})
        ov.furnish()
        first = len(self.bed_calls(g))
        ov.furnish()
        self.assertEqual(first, 1)
        self.assertEqual(len(self.bed_calls(g)), first)

    def test_non_surge_lab_behavior_is_unchanged(self):
        ov, g = self.scenario({"ok": False, "error_code": "no_space"})
        ov.lab = True
        ov.hands_off = 5
        ov.furnish()
        self.assertEqual(self.bed_calls(g), [])

    def test_surge_keeps_its_existing_reserve_remainder(self):
        ov, g = self.scenario({"ok": True, "result": {"at": [[0, 0, 100], [1, 0, 100]]}})
        ov.surge = True
        ov.beds_first = True
        ov.lab = True
        ov.hands_off = 5
        ov.furnish()
        requested = self.bed_calls(g, "A1")[0]["count"]
        self.assertEqual(self.bed_calls(g)[0]["count"], requested - 2)

    def test_active_farm_area_is_not_used_for_open_play_overflow(self):
        ov, g = self.scenario({"ok": False, "error_code": "no_space"})
        ov.o["farm_plots"] = [{"x": 20, "y": 20, "z": 99, "w": 3, "h": 3}]
        ov.furnish()
        self.assertEqual(self.bed_calls(g), [])

    def test_pending_farm_level_is_not_used_for_open_play_overflow(self):
        ov, g = self.scenario({"ok": False, "error_code": "no_space"})
        ov.sites.append({"id": "Rfarm", "kind": "R", "z": 99, "x": 20, "y": 20, "w": 3, "h": 3})
        ov.roles["Rfarm"] = "farm"
        ov.furnish()
        self.assertEqual(self.bed_calls(g), [])

    def test_invalid_or_oversized_alternate_geometry_is_not_used(self):
        for width, height in ((21, 9), (9, 21), (0, 9), (True, 9), (9, None)):
            with self.subTest(width=width, height=height):
                ov, g = self.scenario({"ok": False, "error_code": "no_space"})
                ov.sites[1].update(w=width, h=height)
                ov.furnish()
                self.assertEqual(self.bed_calls(g), [])

    def test_surge_and_open_task_are_mutually_exclusive_without_a_lab_flag(self):
        ov, _ = self.scenario({"ok": False, "error_code": "no_space"})
        ov.surge = True
        ov.lab = False
        ov.hands_off = None
        self.assertFalse(ov.open_task())

    def test_an_alternate_with_exhausted_retries_is_not_used(self):
        ov, g = self.scenario({"ok": False, "error_code": "no_space"})
        ov.tries["beds_A2"] = 6
        ov.furnish()
        self.assertEqual(len(self.bed_calls(g, "A1")), 1)
        self.assertEqual(self.bed_calls(g), [])

    def test_same_level_alternate_is_not_used(self):
        ov, g = self.scenario({"ok": False, "error_code": "no_space"})
        ov.sites[1]["z"] = ov.sites[0]["z"]
        ov.furnish()
        self.assertEqual(len(self.bed_calls(g, "A1")), 1)
        self.assertEqual(self.bed_calls(g), [])

    def test_partial_receipt_covering_the_population_deficit_has_no_extra_reserve(self):
        ov, g = self.scenario({"ok": True, "result": {"at": [[i, 0, 100] for i in range(4)]}})
        ov.furnish()
        self.assertEqual(len(self.bed_calls(g, "A1")), 1)
        self.assertEqual(self.bed_calls(g), [])

    def test_open_play_carries_only_the_population_deficit_after_partial_placement(self):
        primary_count = 2
        ov, g = self.scenario({"ok": True, "result": {"at": [[0, 0, 100], [1, 0, 100]]}})
        needed = max(0, ov.cit - ov.placed.get("bed", 0) - primary_count)
        ov.furnish()
        overflow = [args for args in g.tools("place_furniture") if args.get("kind") == "bed" and args.get("site") == "A2"]
        self.assertTrue(overflow, "Open tasks discard a confirmed placement remainder even with an eligible alternate")
        self.assertEqual(len(overflow), 1)
        self.assertEqual(overflow[0]["count"], needed, "Do not place the extra reserve once the scored population deficit is covered")


if __name__ == "__main__":
    unittest.main(verbosity=2)
