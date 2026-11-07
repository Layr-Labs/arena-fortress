"""Fresh-start brew policy from the public LT08 goal. Offline fakes only."""
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
from plain import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

PUBLIC = VARIANT.parent / "scenarios/season0"
if not PUBLIC.is_dir():
    PUBLIC = Path.cwd() / "scenarios/season0"
INPUTS = [{"stock": "plants_brewable", "at_least": 2}, {"stock": "barrels_empty", "at_least": 1}]
NORMAL = [{"stock": "drink", "below": 300}] + INPUTS


def public_task(filename):
    scenario = json.loads((PUBLIC / filename).read_text())
    task = {k: scenario[k] for k in ("name", "days", "goal")}
    if scenario.get("hands_off_days"):
        task["hands_off"] = {"from_day": scenario["active_days"], "days": scenario["hands_off_days"]}
    return task


class FakeGame:
    def __init__(self, info, orders=()):
        self.info = copy.deepcopy(info)
        self.orders = [{"id": 90, "recipe": "make_barrel", "repeat": "daily"},
                       {"id": 91, "recipe": "cook_meal", "repeat": "daily"}] + copy.deepcopy(list(orders))
        self.calls, self.next_id, self.fail_brew = [], 0, False
        self.last = {"tick": 0}

    def task(self):
        return {"task": copy.deepcopy(self.info), "tools": [{"type": "function", "function": {
            "name": "cancel_order", "parameters": {"type": "object", "properties": {
                "order_id": {"type": "integer"}}, "required": ["order_id"]}}}]}

    def observe(self, day):
        self.last = {"day": day, "tick": day * 1200}
        return {**self.last, "observation": {"date": {"abs_tick": self.last["tick"]},
            "administrators": {"citizens": 7}, "orders": copy.deepcopy(self.orders),
            "stocks": {"drink": 571, "plants_brewable": 7, "barrels_empty": 6,
                       "beds": 100, "tables": 100, "chairs": 100}}}

    def act(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        if name == "add_order":
            if self.fail_brew:
                return {"ok": False, "error_code": "no_material"}
            order_id = self.next_id
            self.next_id += 1
            self.orders.append({"id": order_id, **copy.deepcopy(args)})
            return {"ok": True, "result": {"order_id": order_id}}
        order_id = args["order_id"]
        self.orders = [o for o in self.orders if o["id"] != order_id]
        return {"ok": True, "result": {"order_id": order_id}}


class BrewGrowth(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.lt08 = public_task("lt08-migrant-surge.json")
        self.op1 = public_task("op1-start-year.json")

    def agent(self, info=None, orders=()):
        game = FakeGame(self.lt08 if info is None else info, orders)
        agent = harness.Plain(Task({}), game, None)
        agent.setup()
        return agent

    def supply(self, agent, day=0):
        agent.guard.load(agent.game.observe(day))
        agent.guard.count = 0
        agent.guard.supply()

    def brew_calls(self, agent):
        return [args for tool, args in agent.game.calls if tool == "add_order" and args.get("recipe") == "brew_drink"]

    def test_actual_public_lt08_goal_is_set_before_first_supply(self):
        agent = self.agent()
        self.assertTrue(agent.guard.drink_growth)
        self.supply(agent)
        self.assertEqual(self.brew_calls(agent), [{"recipe": "brew_drink", "amount": 3,
                                                 "repeat": "daily", "when": INPUTS}])

    def test_normal_goal_and_creation_gate_are_unchanged(self):
        for info in (self.op1, {**self.lt08, "hands_off": None},
                     {**self.op1, "hands_off": self.lt08["hands_off"]}):
            with self.subTest(info=info):
                agent = self.agent(info)
                self.assertFalse(agent.guard.drink_growth)
                self.supply(agent)
                self.assertEqual(self.brew_calls(agent)[0]["when"], NORMAL)
        foreign = {"id": 17, "recipe": "brew_drink", "repeat": "monthly", "when": NORMAL}
        agent = self.agent(self.op1, [foreign])
        self.supply(agent)
        self.assertEqual(self.brew_calls(agent), [])

    def test_foreign_capped_repeat_cannot_suppress_goal_order(self):
        foreign = {"id": 17, "recipe": "brew_drink", "repeat": "daily", "when": NORMAL}
        agent = self.agent(orders=[foreign])
        self.supply(agent)
        self.assertEqual(len(self.brew_calls(agent)), 1)
        self.assertEqual(self.brew_calls(agent)[0]["when"], INPUTS)
        self.assertIn(foreign, agent.game.orders)

    def test_one_owned_order_remains_through_later_observations(self):
        agent = self.agent()
        for day in (0, 1, 4, 39):
            self.supply(agent, day)
        self.assertEqual(len(self.brew_calls(agent)), 1)
        self.assertEqual(agent.guard.brew_orders, {0})
        self.assertTrue(agent.guard.drink_growth)

    def test_failed_creation_keeps_existing_three_day_retry(self):
        agent = self.agent()
        agent.game.fail_brew = True
        self.supply(agent, 0)
        self.assertEqual(agent.guard.brew_orders, set())
        agent.game.fail_brew = False
        self.supply(agent, 1)
        self.assertEqual(len(self.brew_calls(agent)), 1)
        self.supply(agent, 3)
        self.assertEqual(len(self.brew_calls(agent)), 2)
        self.assertEqual(agent.guard.brew_orders, {0})

    def test_owned_order_is_protected_but_foreign_cancel_is_unchanged(self):
        foreign = {"id": 17, "recipe": "brew_drink", "repeat": "daily", "when": NORMAL}
        agent = self.agent(orders=[foreign])
        self.supply(agent)
        agent.game.calls.clear()
        for order_id, code in ((0, "order_churn"), (17, None)):
            agent.run_call({"id": "cancel-check", "function": {"name": "cancel_order",
                "arguments": json.dumps({"order_id": order_id})}})
            result = json.loads(agent.messages[-1]["content"])
            self.assertEqual(result.get("error_code"), code)
        self.assertEqual(agent.game.calls, [("cancel_order", {"order_id": 17})])
        self.assertEqual(agent.guard.brew_orders, {0})
        self.assertIn(0, [o["id"] for o in agent.game.orders])


if __name__ == "__main__":
    unittest.main()
