"""A hands-off brew order must not wait for a population-sized plant pile."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer

class API:
    def __init__(self): self.calls = []
    def act(self, tool, args):
        self.calls.append((tool, args))
        return {"ok": True, "result": {"order_id": len(self.calls)}}

class WindowInput(unittest.TestCase):
    def test_brew_threshold_does_not_scale_with_population(self):
        for citizens in (7, 18, 46, 100):
            with self.subTest(citizens=citizens):
                api = API()
                layer = Overseer(api)
                layer.count = 0
                layer.load({"tick": 1200, "observation": {
                    "administrators": {"citizens": citizens},
                    "stocks": {"food_edible": 1000, "plants_brewable": 3}}})
                with contextlib.redirect_stdout(io.StringIO()): layer.window_supply()
                orders = [args for _, args in api.calls if args.get("recipe") == "brew_drink"]
                self.assertEqual(len(orders), 1)
                self.assertEqual(orders[0]["repeat"], "daily")
                self.assertEqual(orders[0]["when"], [
                    {"stock": "drink", "below": 2000},
                    {"stock": "plants_brewable", "at_least": 2},
                    {"stock": "barrels_empty", "at_least": 1}])

if __name__ == '__main__': unittest.main()
