"""Offline regressions suggested by peer PR27.

Peer: f577e8a7-5faa-4ce5-b83f-8717cd1399f9.
Source commit: 62195aa386b9cfa0be8f95029198116bbe588c9b.
"""
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


class FakeGame:
    def __init__(self):
        self.last = {"tick": 12000}
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if type(args.get("order_id")) is not int:
            return {"ok": False, "error_code": "bad_arguments", "error": "order_id must be an integer"}
        return {"ok": True, "result": {}}


class TypedArguments(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def run_call(self, name, args, added=None):
        game = FakeGame()
        agent = harness.Plain(Task({}), game, None)
        agent.tool_names = {"cancel_order"}
        agent.messages = []
        agent.added = dict(added or {})
        moved = agent.run_call({"id": "typed-check", "function": {
            "name": name, "arguments": json.dumps(args)}})
        return agent, game, json.loads(agent.messages[-1]["content"]), moved

    def test_nonstring_tool_names_are_unknown_without_api_calls(self):
        for name in ([], {}, 42, None):
            with self.subTest(name=name):
                _, game, result, moved = self.run_call(name, {})
                self.assertEqual(result["error_code"], "unknown_tool")
                self.assertEqual(game.calls, [])
                self.assertFalse(moved)

    def test_container_cancel_ids_reach_api_rejection_without_cache_changes(self):
        added = {7: ("order", 0)}
        for order_id in ([], {}, [7], {"id": 7}):
            with self.subTest(order_id=order_id):
                agent, game, result, moved = self.run_call("cancel_order", {"order_id": order_id}, added)
                self.assertEqual(result["error_code"], "bad_arguments")
                self.assertEqual(game.calls, [("cancel_order", {"order_id": order_id})])
                self.assertEqual(agent.added, added)
                self.assertEqual(agent.cancelled, [])
                self.assertEqual(agent.stats["churn_refused"], 0)
                self.assertFalse(moved)

    def test_fresh_hashable_cancel_still_uses_churn_guard(self):
        for order_id in (7, 7.0):
            with self.subTest(order_id=order_id):
                agent, game, result, _ = self.run_call("cancel_order", {"order_id": order_id}, {7: ("order", 12000)})
                self.assertEqual(result["error_code"], "order_churn")
                self.assertEqual(game.calls, [])
                self.assertEqual(agent.stats["churn_refused"], 1)

    def test_old_integer_cancel_still_updates_cache(self):
        agent, game, result, _ = self.run_call("cancel_order", {"order_id": 7}, {7: ("order", 0)})
        self.assertTrue(result["ok"])
        self.assertEqual(game.calls, [("cancel_order", {"order_id": 7})])
        self.assertEqual(agent.added, {})
        self.assertEqual(agent.cancelled, [(12000, "order", 7)])


if __name__ == "__main__":
    unittest.main()
