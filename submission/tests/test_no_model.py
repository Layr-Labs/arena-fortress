"""The measurement build's switch: with NO_MODEL the harness never calls the model and the layer plays to the end."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import Task, WalkGame  # noqa: E402
from plain import harness  # noqa: E402


class NoModel:
    """A model that fails the test if it is ever asked."""
    usage = {}

    def chat(self, *a, **kw):
        raise AssertionError("the model was called")


class EndingGame(WalkGame):
    """WalkGame with a task() and a game over from day 130."""

    def task(self):
        return {"tools": [], "manual": "", "task": {"name": "t", "days": 336}}

    def observe(self):
        r = super().observe()
        if self.day >= 130:
            r["game_over"] = True
        return r


class NoModelSwitch(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_switch_is_on(self):
        self.assertTrue(harness.NO_MODEL)

    def test_run_never_calls_the_model_and_the_layer_plays_on(self):
        g = EndingGame()
        p = harness.Plain(Task(), g, NoModel())
        p.run()
        self.assertEqual(p.stop_reason, "game_over")
        self.assertEqual(p.stats["turns"], 0)
        self.assertTrue(g.advances)
        self.assertGreaterEqual(g.day, 130)


if __name__ == "__main__":
    unittest.main()
