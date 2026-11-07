"""Unit tests for pre-window boost, second carpenter, and layer-only fallback."""
import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from dfbench_client import GameOver, HandsOff, Task
from overseer import harness as ov_harness
from plain import harness as plain_harness


class FakeGame:
    def __init__(self, observation=None):
        self.obs = observation or {}
        self.calls = []
        self.day = 1
        self.orders = set()
        self.next_order_id = 100

    def observe(self):
        return copy.deepcopy(self.obs)

    def act(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        if name == "add_order":
            oid = self.next_order_id
            self.next_order_id += 1
            self.orders.add(oid)
            return {"ok": True, "result": {"order_id": oid}}
        if name == "build_workshop":
            return {"ok": True, "result": {"site": args.get("site")}}
        if name == "advance_days":
            days = args.get("days", 1)
            self.day += days
            self.obs["day"] = self.day
            if self.day >= 10:
                return {"ok": True, "result": {"hands_off": True}}
            return {"ok": True, "day": self.day}
        return {"ok": True}


class TestEndgameAndFallback(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def test_pre_window_brew_and_barrel_boost(self):
        obs = {
            "tick": 12000,
            "hands_off_in_days": 10,
            "observation": {
                "administrators": {"citizens": 25},
                "stocks": {
                    "drink": 150,
                    "plants_brewable": 10,
                    "barrels_empty": 2,
                    "logs_usable": 5,
                    "furniture_free": {},
                },
                "orders": [
                    {"id": 1, "recipe": "brew_drink", "repeat": "daily"},
                    {"id": 2, "recipe": "make_barrel", "repeat": "daily"},
                    {"id": 3, "recipe": "cook_meal", "repeat": "daily"},
                ],
                "map": {"sites": []},
                "dwarves": [{"id": i, "adult": True} for i in range(25)],
            },
        }
        game = FakeGame(obs)
        overseer = ov_harness.Overseer(game)
        overseer.load(obs)
        overseer.supply()
        added_recipes = [c[1].get("recipe") for c in game.calls if c[0] == "add_order"]
        self.assertIn("brew_drink", added_recipes)
        self.assertIn("make_barrel", added_recipes)

    def test_second_carpenters_when_cit_ge_20(self):
        obs = {
            "tick": 12000,
            "observation": {
                "administrators": {"citizens": 22},
                "stocks": {"logs_usable": 5, "boulders_usable": 5},
                "workshops": [
                    {"type": "Carpenters"},
                    {"type": "Still"},
                    {"type": "Kitchen"},
                ],
                "map": {
                    "sites": [
                        {"id": "W1", "kind": "W"},
                        {"id": "W2", "kind": "W"},
                    ]
                },
                "dwarves": [{"id": i, "adult": True} for i in range(22)],
            },
        }
        game = FakeGame(obs)
        overseer = ov_harness.Overseer(game)
        overseer.load(obs)
        overseer.workshops()
        built = [c[1].get("type") for c in game.calls if c[0] == "build_workshop"]
        self.assertEqual(built, ["Carpenters"])

    def test_batch_beds_scaled_for_migrant_surge(self):
        obs = {
            "tick": 12000,
            "observation": {
                "administrators": {"citizens": 30},
                "stocks": {
                    "beds": 5,
                    "logs_usable": 20,
                    "furniture_free": {},
                },
                "orders": [
                    {"id": 1, "recipe": "brew_drink", "repeat": "daily"},
                    {"id": 2, "recipe": "make_barrel", "repeat": "daily"},
                    {"id": 3, "recipe": "cook_meal", "repeat": "daily"},
                ],
                "map": {"sites": []},
                "dwarves": [{"id": i, "adult": True} for i in range(30)],
            },
        }
        game = FakeGame(obs)
        overseer = ov_harness.Overseer(game)
        overseer.load(obs)
        overseer.supply()
        bed_orders = [c[1] for c in game.calls if c[0] == "add_order" and c[1].get("recipe") == "make_bed"]
        self.assertEqual(len(bed_orders), 1)
        self.assertEqual(bed_orders[0]["amount"], 16)

    def test_layer_only_fallback_advances_to_completion(self):
        obs = {
            "day": 1,
            "tick": 1200,
            "observation": {
                "administrators": {"citizens": 7},
                "stocks": {"drink": 100, "furniture_free": {}},
                "map": {"sites": []},
                "dwarves": [{"id": i, "adult": True} for i in range(7)],
            },
        }
        game = FakeGame(obs)
        agent = plain_harness.Plain(Task({}), game, None)
        agent.layer_only()
        self.assertIn(agent.stop_reason, ("hands_off", "GameOver", "HandsOff"))
        self.assertGreaterEqual(game.day, 10)


if __name__ == "__main__":
    unittest.main()
