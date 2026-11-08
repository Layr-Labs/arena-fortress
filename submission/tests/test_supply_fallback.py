"""The window's fruit-brew fallback: a standing brew_drink_from_fruit order joins the pre-window supply, once.
No game or network is used."""
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

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {}}


def resp(hands_off=10, **over):
    obs = {"administrators": {"citizens": 8}, "stocks": {"logs_usable": 10},
           "map": {"surface_z": 10, "sites": []}}
    obs.update(over)
    return {"tick": 0, "day": 45, "hands_off_in_days": hands_off, "observation": obs}


def fruit_orders(calls):
    return [a for t, a in calls if t == "add_order" and a.get("recipe") == "brew_drink_from_fruit"]


class WindowFruitFallback(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, response):
        game = FakeGame()
        ov = harness.Overseer(game)
        ov.load(response)
        ov.count = 0
        return ov, game

    def test_window_prep_adds_the_fruit_standing_order_once(self):
        ov, game = self.overseer(resp())   # hands_off 10 d: inside the 14-day window prep
        ov.closer()
        added = fruit_orders(game.calls)
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["amount"], 3)
        self.assertEqual(added[0]["repeat"], "daily")
        # safe side: add_order's `when` has no fruit/growth stock name (gameapi/facts/tools.py ORDER_STOCKS), so
        # only the drink cap and an empty barrel gate it; DF finds the fruit itself
        self.assertEqual([c["stock"] for c in added[0]["when"]], ["drink", "barrels_empty"])
        self.assertIn("o_brew_fruit_win", ov.done)
        ov.load(resp())
        ov.closer()
        self.assertEqual(len(fruit_orders(game.calls)), 1)   # the done key keeps it a once-per-game order

    def test_no_fruit_order_when_a_fruit_standing_already_exists(self):
        ov, game = self.overseer(resp(orders=[{"recipe": "brew_drink_from_fruit", "repeat": "daily", "left": 0}]))
        ov.closer()
        self.assertEqual(fruit_orders(game.calls), [])   # the model's own standing order is left alone

    def test_no_fruit_order_outside_the_window_prep(self):
        ov, game = self.overseer(resp(hands_off=30))   # the window is still far away
        ov.closer()
        self.assertEqual(fruit_orders(game.calls), [])


if __name__ == "__main__":
    unittest.main()
