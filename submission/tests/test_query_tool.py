"""Contract checks for the model's read-only fact transport."""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from dfbench_client import GameAPIError
from plain import harness

assert Path(harness.__file__).is_relative_to(VARIANT)


class Game:
    def __init__(self):
        self.last = {"day": 7, "tick": 8400}
        self.reads = []
        self.failure = None
        self.response = {"result": {"units": [{"id": 42}]}}

    def task(self):
        return {"tools": []}

    def act(self, *args):
        raise AssertionError("a fact query must never call /act")

    def query(self, name, **params):
        self.reads.append((name, params))
        if self.failure:
            raise self.failure
        return self.response


class QueryTool(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.game = Game()
        task = SimpleNamespace(task={"days": 60}, days=60, credits=None)
        self.runner = harness.Plain(task, self.game, SimpleNamespace(usage={"cost_usd": 0}))
        self.runner.setup()

    def call(self, args):
        moved = self.runner.run_call({"id": "read-1", "function": {
            "name": "query_game", "arguments": json.dumps(args)}})
        self.assertFalse(moved)
        result = self.runner.messages[-1]
        self.assertEqual(result["tool_call_id"], "read-1")
        self.assertEqual(self.runner.stats["actions"], 0)
        self.assertEqual(self.game.last, {"day": 7, "tick": 8400})
        return json.loads(result["content"])

    def test_advertises_only_the_fixed_read_queries(self):
        tools = harness.prepare_tools([])
        q = next(t["function"] for t in tools if t["function"]["name"] == "query_game")
        self.assertEqual(set(q["parameters"]["properties"]["which"]["enum"]), {
            "stocks", "units", "jobs", "orders", "buildings", "zones", "map",
            "manager_order_types", "workshop_types"})
        self.assertIn("which", q["parameters"]["required"])

    def test_dispatches_facts_without_consuming_actions_or_time(self):
        result = self.call({"which": "units", "params": {"kind": "animals", "limit": 20}})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"], {"units": [{"id": 42}]})
        self.assertEqual(self.game.reads, [("units", {"kind": "animals", "limit": 20})])
        self.assertEqual(self.runner.stats["queries"], 1)
        self.assertEqual(self.runner.stats["query_errors"], 0)

    def test_rejects_paths_and_write_tool_names_locally(self):
        result = self.call({"which": "../act"})
        self.assertFalse(result["ok"])
        self.assertEqual(self.game.reads, [])
        self.assertEqual(self.runner.stats["query_errors"], 1)

    def test_rejects_nonscalar_filters_and_reserved_keyword(self):
        for params in (["animals"], {"kind": {"value": "animals"}}, {"name": "units"}):
            with self.subTest(params=params):
                result = self.call({"which": "units", "params": params})
                self.assertFalse(result["ok"])
        self.assertEqual(self.game.reads, [])

    def test_reports_transport_error_as_a_query_result(self):
        self.game.failure = GameAPIError("temporarily unavailable")
        result = self.call({"which": "stocks"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "query_failed")
        self.assertEqual(self.runner.stats["query_errors"], 1)

    def test_preserves_server_query_denials(self):
        self.game.response = {"result": {"ok": False, "error_code": "bad_kind", "error": "invalid kind"}}
        result = self.call({"which": "units", "params": {"kind": "invalid"}})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "bad_kind")
        self.assertEqual(self.runner.stats["query_errors"], 1)

    def test_nonfinite_query_filters_never_reach_transport(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            self.assertFalse(self.call({"which": "map", "params": {"x": value}})["ok"])
        self.assertEqual(self.game.reads, [])

    def test_top_level_denial_keeps_the_server_error(self):
        self.game.response = {"ok": False, "error_code": "unknown_query", "error": "endpoint unavailable", "result": {"detail": "unavailable"}}
        result = self.call({"which": "stocks"})
        self.assertEqual(result["error_code"], "unknown_query")
        self.assertEqual(result["error"], "endpoint unavailable")

    def test_focused_query_can_return_detailed_facts_beyond_action_limit(self):
        detail = "observed " * 700
        self.game.response = {"result": {"units": [{"id": 42, "facts": detail}]}}
        result = self.call({"which": "units", "params": {"limit": 1}})
        self.assertEqual(result["result"]["units"][0]["facts"], detail)
        self.assertEqual(harness.TOOL_RESULT_MAX, 4000)



if __name__ == "__main__":
    unittest.main()
