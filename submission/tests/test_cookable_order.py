"""Black-box emitted payloads: the standing cook order must not demand plants.

Cooking takes 2+ cookable ingredients (tools.py), not specifically plants; fish
and meat count and prepared meals keep while raw fish/meat rot (MANUAL.md).
Brew guards, cap, amount, repeat and dedup must be untouched.
"""
import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from dfbench_client import Task
from overseer.harness import MEAL_CAP
from plain import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

BREW = {"recipe": "brew_drink", "amount": 3, "repeat": "daily", "when": [
    {"stock": "drink", "below": 300}, {"stock": "plants_brewable", "at_least": 2},
    {"stock": "barrels_empty", "at_least": 1}]}


class FakeGame:
    def __init__(self):
        self.next_id, self.calls, self.orders = 20, [], set()

    def act(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        if name == "add_order":
            self.orders.add(self.next_id)
            return {"ok": True, "result": {"order_id": self.next_id}}
        return {"ok": True, "result": {}}


class Cookable(unittest.TestCase):
    def setUp(self):
        out = redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def supply(self, orders=()):
        agent = harness.Plain(Task({}), FakeGame(), None)
        agent.messages = []
        agent.guard.load({"tick": 823200 + 131 * 1200, "observation": {
            "administrators": {"citizens": 10}, "stocks": {"drink": 411},
            "orders": list(orders)}})
        agent.guard.supply()
        return agent.game.calls

    def orders_for(self, calls, recipe):
        return [a for n, a in calls if n == "add_order" and a.get("recipe") == recipe]

    def test_standing_cook_order_issued_with_no_plants_in_view(self):
        cook = self.orders_for(self.supply(), "cook_meal")
        self.assertEqual(len(cook), 1)
        self.assertNotIn("plants_total", json.dumps(cook[0]))
        self.assertEqual(cook[0]["when"], [{"stock": "prepared_meals", "below": MEAL_CAP}])

    def test_cook_order_keeps_amount_repeat_and_meal_cap(self):
        cook = self.orders_for(self.supply(), "cook_meal")[0]
        self.assertEqual(cook["amount"], 2)
        self.assertEqual(cook["repeat"], "daily")
        self.assertEqual(MEAL_CAP, 200)

    def test_existing_standing_cook_order_is_not_duplicated(self):
        calls = self.supply(orders=[{"id": 5, "recipe": "cook_meal", "repeat": "daily"}])
        self.assertEqual(self.orders_for(calls, "cook_meal"), [])

    def test_brew_and_barrel_orders_and_guards_are_unchanged(self):
        calls = self.supply()
        self.assertEqual(self.orders_for(calls, "brew_drink"), [BREW])
        barrel = self.orders_for(calls, "make_barrel")
        self.assertEqual(len(barrel), 1)
        self.assertEqual(barrel[0]["when"], [{"stock": "barrels_empty", "below": 4},
                                             {"stock": "logs", "at_least": 2}])


if __name__ == "__main__":
    unittest.main()
