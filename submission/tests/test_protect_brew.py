"""Replay public OP1 API lines 125 and 160. No game or network is used."""
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

BREW = {"recipe": "brew_drink", "amount": 3, "repeat": "daily", "when": [
    {"stock": "drink", "below": 300}, {"stock": "plants_brewable", "at_least": 2},
    {"stock": "barrels_empty", "at_least": 1}]}


class FakeGame:
    def __init__(self, next_id=12, add_response=None):
        self.next_id, self.add_response = next_id, add_response
        self.orders, self.calls = set(), []
        self.last = {"tick": 980400}

    def act(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        if name == "add_order":
            result = copy.deepcopy(self.add_response) if self.add_response is not None else {
                "ok": True, "result": {"order_id": self.next_id}}
            self.next_id += 1
            order_id = result.get("result", {}).get("order_id")
            if result.get("ok") and type(order_id) is int:
                self.orders.add(order_id)
            return result
        order_id = args.get("order_id")
        if type(order_id) is not int:
            return {"ok": False, "error_code": "bad_arguments"}
        if order_id not in self.orders:
            return {"ok": False, "error_code": "no_such_order"}
        self.orders.remove(order_id)
        return {"ok": True, "result": {"order_id": order_id}}


class ProtectBrew(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def agent(self, **kw):
        agent = harness.Plain(Task({}), FakeGame(**kw), None)
        agent.messages = []
        agent.tool_names = {"add_order", "cancel_order"}
        self.load(agent, 131)
        agent.guard.count = 0
        return agent

    def load(self, agent, day, orders=()):
        tick = 823200 + day * 1200
        agent.game.last = {"tick": tick}
        agent.guard.load({"tick": tick, "observation": {
            "administrators": {"citizens": 10}, "stocks": {"drink": 411},
            "orders": [{"id": 1, "recipe": "make_barrel", "repeat": "daily"},
                       {"id": 7, "recipe": "cook_meal", "repeat": "daily"}] + list(orders)}})

    def call(self, agent, name, args):
        agent.run_call({"id": "order-check", "function": {"name": name, "arguments": json.dumps(args)}})
        return json.loads(agent.messages[-1]["content"])

    def test_day_131_controller_brew_survives_day_202_cancel_without_duplicate(self):
        agent = self.agent()
        agent.guard.supply()
        self.assertEqual(agent.game.calls, [("add_order", BREW)])
        self.assertEqual(agent.added, {})
        self.load(agent, 202, [{"id": 12, **BREW}])
        agent.game.calls.clear()
        result = self.call(agent, "cancel_order", {"order_id": 12})
        self.assertEqual(result.get("error_code"), "order_churn")
        self.assertEqual(agent.game.calls, [])
        self.assertEqual(agent.game.orders, {12})
        self.assertEqual(agent.stats["churn_refused"], 1)
        agent.guard.supply()
        self.assertEqual(agent.game.calls, [])

    def test_model_created_daily_brew_remains_cancellable(self):
        agent = self.agent(next_id=18)
        self.assertTrue(self.call(agent, "add_order", BREW)["ok"])
        self.load(agent, 202, [{"id": 18, **BREW}])
        agent.game.calls.clear()
        self.assertTrue(self.call(agent, "cancel_order", {"order_id": 18})["ok"])
        self.assertEqual(agent.game.calls, [("cancel_order", {"order_id": 18})])
        self.assertEqual(agent.stats["churn_refused"], 0)

    def test_other_controller_orders_remain_cancellable(self):
        for args in ({"recipe": "cook_meal", "amount": 2, "repeat": "daily"},
                     {"recipe": "brew_drink", "amount": 1},
                     {"recipe": "brew_drink", "amount": 1, "repeat": "monthly"}):
            with self.subTest(args=args):
                agent = self.agent()
                agent.guard.act("other", "add_order", args)
                agent.game.calls.clear()
                self.assertTrue(self.call(agent, "cancel_order", {"order_id": 12})["ok"])
                self.assertEqual(agent.game.calls, [("cancel_order", {"order_id": 12})])

    def test_failed_or_missing_id_responses_do_not_claim_manual_order(self):
        for response in ({"ok": False, "result": {"order_id": 12}}, {"ok": True, "result": {}}):
            with self.subTest(response=response):
                agent = self.agent(add_response=response)
                agent.game.orders.add(12)
                agent.guard.supply()
                agent.game.calls.clear()
                self.assertTrue(self.call(agent, "cancel_order", {"order_id": 12})["ok"])
                self.assertEqual(agent.game.calls, [("cancel_order", {"order_id": 12})])

    def test_unknown_or_removed_order_retains_no_such_order_result(self):
        for removed in (False, True):
            with self.subTest(removed=removed):
                agent = self.agent()
                agent.guard.supply()
                order_id = 99
                if removed:
                    agent.game.orders.remove(12)
                    self.load(agent, 202)
                    order_id = 12
                agent.game.calls.clear()
                result = self.call(agent, "cancel_order", {"order_id": order_id})
                self.assertEqual(result.get("error_code"), "no_such_order")
                self.assertEqual(agent.game.calls, [("cancel_order", {"order_id": order_id})])

    def test_missing_or_failed_order_probe_preserves_owned_brew(self):
        for observation in ({}, {"orders": "ERR: probe failed"}):
            with self.subTest(observation=observation):
                agent = self.agent()
                agent.guard.supply()
                agent.guard.load({"tick": 1065600, "observation": observation})
                agent.game.calls.clear()
                self.assertEqual(self.call(agent, "cancel_order", {"order_id": 12}).get("error_code"), "order_churn")
                self.assertEqual(agent.game.calls, [])

    def test_zero_is_a_valid_returned_owned_order_id(self):
        agent = self.agent(next_id=0)
        agent.guard.supply()
        agent.game.calls.clear()
        self.assertEqual(self.call(agent, "cancel_order", {"order_id": 0}).get("error_code"), "order_churn")
        self.assertEqual(agent.game.calls, [])

    def test_malformed_owned_id_attempts_keep_api_argument_errors(self):
        for order_id in ([], {}, 12.0, True, "12", None):
            with self.subTest(order_id=order_id):
                agent = self.agent()
                agent.guard.supply()
                agent.game.calls.clear()
                result = self.call(agent, "cancel_order", {"order_id": order_id})
                self.assertEqual(result.get("error_code"), "bad_arguments")
                self.assertEqual(agent.game.calls, [("cancel_order", {"order_id": order_id})])


if __name__ == "__main__":
    unittest.main()
