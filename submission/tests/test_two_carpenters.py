"""Check the bounded bed-goal workshop target with offline clients only."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness
from test_brew_growth import public_task

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class FakeGame:
    def __init__(self):
        self.calls = []
        self.fail = False

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if self.fail:
            return {"ok": False, "error_code": "no_material"}
        return {"ok": True, "result": {"id": len(self.calls)}}


class TwoCarpenters(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, workshops=None, goal=True, job="idle", material=10, sites=5):
        if workshops is None:
            workshops = [{"type": t, "built": True} for t in ("Carpenters", "Still", "Kitchen")]
        game = FakeGame()
        overseer = harness.Overseer(game)
        overseer.set_task(public_task("lt08-migrant-surge.json" if goal else "op1-start-year.json"))
        overseer.load({"tick": 0, "observation": {
            "administrators": {"citizens": 47}, "dwarves": [{"id": 87, "job": job}],
            "stocks": {"logs_usable": material}, "workshops": workshops,
            "map": {"sites": [{"id": "W" + str(i), "kind": "W"} for i in range(1, sites + 1)]}}})
        overseer.count = 0
        return overseer, game

    def test_public_bed_goal_requests_a_second_carpenters(self):
        overseer, game = self.overseer()
        self.assertTrue(overseer.beds_first)
        overseer.workshops()
        self.assertEqual(game.calls, [("build_workshop", {"type": "Carpenters", "site": "W1"})])
        self.assertEqual(overseer.kind("W")[0]["id"], "W2")

    def test_normal_goal_with_a_bed_shortfall_also_requests_a_second(self):
        overseer, game = self.overseer(goal=False)   # 47 citizens, no placed beds observed
        self.assertFalse(overseer.beds_first)
        self.assertTrue(overseer.beds_short)
        overseer.workshops()
        self.assertEqual(game.calls, [("build_workshop", {"type": "Carpenters", "site": "W1"})])
        overseer, game = self.overseer(workshops=[], goal=False)
        overseer.workshops()
        self.assertEqual([args["type"] for _, args in game.calls], ["Carpenters", "Still", "Kitchen"])

    def test_planned_and_built_workshops_count_toward_two(self):
        for states in ([True, False], [False, False], [True, True], [True, True, True], [False]):
            with self.subTest(states=states):
                workshops = [{"type": "Carpenters", "built": built} for built in states]
                workshops += [{"type": t, "built": True} for t in ("Still", "Kitchen")]
                overseer, game = self.overseer(workshops=workshops)
                overseer.workshops()
                expected = [("build_workshop", {"type": "Carpenters", "site": "W1"})] if len(states) < 2 else []
                self.assertEqual(game.calls, expected)

    def test_core_and_fishery_use_sites_before_the_second_carpenters(self):
        overseer, game = self.overseer(workshops=[{"type": "Carpenters", "built": True}], job="Fish")
        overseer.workshops()
        self.assertEqual(game.calls, [
            ("build_workshop", {"type": "Still", "site": "W1"}),
            ("build_workshop", {"type": "Kitchen", "site": "W2"}),
            ("build_workshop", {"type": "Fishery", "site": "W3"}),
            ("build_workshop", {"type": "Carpenters", "site": "W4"})])

    def test_first_carpenters_request_blocks_a_second_in_the_same_pass(self):
        overseer, game = self.overseer(workshops=[], job="Fish")
        overseer.workshops()
        self.assertEqual(game.calls, [
            ("build_workshop", {"type": "Carpenters", "site": "W1"}),
            ("build_workshop", {"type": "Still", "site": "W2"}),
            ("build_workshop", {"type": "Kitchen", "site": "W3"}),
            ("build_workshop", {"type": "Fishery", "site": "W4"})])
        self.assertEqual([s["id"] for s in overseer.kind("W")], ["W5"])

    def test_failed_build_keeps_site_and_waits_for_the_existing_retry(self):
        overseer, game = self.overseer()
        game.fail = True
        overseer.workshops()
        self.assertEqual(len(game.calls), 1)
        self.assertEqual(overseer.kind("W")[0]["id"], "W1")
        game.fail = False
        overseer.workshops()
        overseer.now = 2 * harness.DAY
        overseer.workshops()
        self.assertEqual(len(game.calls), 1)
        overseer.now = 3 * harness.DAY
        overseer.workshops()
        self.assertEqual(game.calls, [("build_workshop", {"type": "Carpenters", "site": "W1"})] * 2)
        self.assertEqual(overseer.kind("W")[0]["id"], "W2")

    def test_material_and_site_gates_still_apply(self):
        for options in ({"material": 0}, {"sites": 0}):
            with self.subTest(options=options):
                overseer, game = self.overseer(**options)
                overseer.workshops()
                self.assertEqual(game.calls, [])


if __name__ == "__main__":
    unittest.main()
