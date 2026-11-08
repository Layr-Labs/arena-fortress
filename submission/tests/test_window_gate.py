"""Promoted pre-window reserve contract, using only public observations."""
import io
from contextlib import redirect_stdout
import unittest
from overseer.harness import Overseer


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args))
        return {"ok": True, "result": {"order_id": len(self.calls)}}


class WindowGate(unittest.TestCase):
    def test_window_brew_has_minimum_real_inputs_and_remains_owned_once(self):
        g = FakeGame()
        ov = Overseer(g, goal="Migrants are arriving", days=60)
        ov.load({"tick": 30 * 1200, "day": 30, "hands_off_in_days": 9,
                 "observation": {"administrators": {"citizens": 43},
                                 "stocks": {"food_edible": 200}}})
        ov.count = 0
        with redirect_stdout(io.StringIO()):
            ov.window_supply()
            ov.now += 1200
            ov.window_supply()
        brew = [a for t, a in g.calls if a.get("recipe") == "brew_drink"]
        self.assertEqual(len(brew), 1)
        self.assertEqual(brew[0]["when"], [
            {"stock": "drink", "below": 2000},
            {"stock": "plants_brewable", "at_least": 21},
            {"stock": "barrels_empty", "at_least": 1}])
        self.assertEqual(brew[0]["repeat"], "daily")
        self.assertEqual(ov.owned, {1, 2})
        self.assertIn("o_brew_win", ov.done)


if __name__ == "__main__":
    unittest.main()
