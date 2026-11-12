"""Wall-budget exit for the standalone overseer loop.

The server watchdog ends the game at the wall cap with NO run-out to the
horizon, and SCORING §6 scores the horizon state. The overseer must stop
advancing while time remains, so the runner's /finish can run the fort out.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))

from overseer.harness import Overseer, WALL_RESERVE  # noqa: E402

def _module_of(obj):
    return str(sys.modules[obj.__module__].__file__)


assert Path(_module_of(Overseer)).resolve().is_relative_to(VARIANT.resolve())


class FakeGame:
    """Only the four methods the overseer run loop uses. No network."""

    def __init__(self, wall_s=None, used=0.0, health_no_used=False, health_raises=False):
        self.task_data = {"limits": {"wall_s": wall_s}}
        self.used = used
        self.advance_cost = 100.0
        self.health_no_used = health_no_used
        self.health_raises = health_raises
        self.actions = []

    def task(self):
        return self.task_data

    def health(self):
        if self.health_raises:
            raise RuntimeError("health down")
        h = {"phase": "ready", "day": len(self.actions)}
        if not self.health_no_used:
            h["wall_used_s"] = self.used
        return h

    def observe(self):
        return {"tick": len(self.actions) * 48, "day": len(self.actions),
                "observation": {"stocks": {}, "map": {}}}

    def act(self, tool, args=None):
        self.actions.append((tool, args))
        if tool == "advance_days":
            self.used += self.advance_cost
        return {"tick": len(self.actions) * 48, "day": len(self.actions),
                "result": {"stopped": None}, "game_over": len(self.actions) >= 50}


class Quiet(Overseer):
    """Isolate the gate: plan nothing, advance one day per pass."""

    def plan(self):
        self.count = 0

    def pace(self, resp):
        return 1


class WallGateTest(unittest.TestCase):
    def run_overseer(self, game):
        return Quiet(game).run()

    def test_exit_before_the_cap_and_no_advance_after(self):
        # cap 1000 s, already 900 used -> left 100 <= 120 reserve: no advances at all
        game = FakeGame(wall_s=1000.0, used=900.0)
        self.assertEqual(self.run_overseer(game), "wall_budget")
        self.assertEqual(game.actions, [])

    def test_advances_while_the_budget_is_large(self):
        # 1000 s cap, 120 reserve, fake 100 s per advance: act only while left > 120
        game = FakeGame(wall_s=1000.0, used=0.0)
        reason = self.run_overseer(game)
        self.assertEqual(reason, "wall_budget")
        self.assertEqual(len(game.actions), 9)   # acts while left>120: used 0..800 pass; left=100 stops
        self.assertLess(game.used, 1000.0)       # never advanced past the cap line

    def test_no_cap_means_no_gate(self):
        game = FakeGame(wall_s=None)
        self.assertEqual(self.run_overseer(game), "over")   # runs to game_over
        self.assertTrue(game.actions)

    def test_no_wall_reading_means_no_gate(self):
        game = FakeGame(health_no_used=True)
        self.assertEqual(self.run_overseer(game), "over")

    def test_health_failure_means_no_gate(self):
        game = FakeGame(health_raises=True)
        self.assertEqual(self.run_overseer(game), "over")

    def test_wall_left_none_cases(self):
        ov = Quiet(FakeGame(wall_s=None))
        ov.wall_s = None
        self.assertIsNone(ov.wall_left())
        ov2 = Quiet(FakeGame(health_no_used=True))
        ov2.wall_s = 100.0
        self.assertIsNone(ov2.wall_left())

    def test_game_over_wins_over_the_gate(self):
        game = FakeGame(wall_s=1000.0, used=900.0)
        game.observe = lambda: {"game_over": True}
        self.assertEqual(self.run_overseer(game), "game_over")


if __name__ == "__main__":
    unittest.main()
