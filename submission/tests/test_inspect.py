"""Read-only query routing must never send synthetic tools through /act."""
import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from test_advisor import Game, Model, call
from dfbench_client.task import Task
from plain.harness import Plain
from plain import inspect


class QueryGame(Game):
    def __init__(self):
        super().__init__()
        self.queries = []

    def task(self):
        return {**super().task(), "queries": ["stocks", "orders", "map"]}

    def query(self, name, **params):
        self.queries.append((name, params))
        return {"groups": [{"item_type": "WOOD", "count": 4}], "total": 1}


class InspectTests(unittest.TestCase):
    def player(self):
        p = Plain(Task({"task": {"days": 60}}), QueryGame(), Model())
        with redirect_stdout(io.StringIO()):
            p.setup()
        return p

    def test_only_advertised_public_queries_are_offered(self):
        p = self.player()
        tool = next((t for t in p.tools if t["function"]["name"] == "inspect_fort"), None)
        self.assertIsNotNone(tool)
        schema = tool["function"]["parameters"]["properties"]
        self.assertEqual(set(schema["name"]["enum"]), {"stocks", "orders", "map"})
        self.assertNotIn("url", schema)

    def test_query_is_read_only_and_does_not_unlock_failed_action(self):
        p = self.player()
        call(p)
        result = call(p, "inspect_fort", {"name": "stocks", "item_type": "WOOD", "limit": 20})
        self.assertTrue(result["ok"])
        self.assertEqual(p.game.queries, [("stocks", {"item_type": "WOOD", "limit": 20})])
        self.assertEqual(len(p.game.calls), 1)
        self.assertEqual(call(p)["error_code"], "unchanged_failure")

    def test_query_does_not_accept_arbitrary_paths_or_unsupported_args(self):
        p = self.player()
        result = call(p, "inspect_fort", {"name": "../finish"})
        self.assertFalse(result["ok"])
        result = call(p, "inspect_fort", {"name": "stocks", "url": "https://example.invalid"})
        self.assertFalse(result["ok"])
        self.assertEqual(p.game.queries, [])
        self.assertEqual(p.game.calls, [])

    def test_cut_queries_stay_valid_json_and_preserve_total(self):
        p = self.player()
        p.game.query = lambda *a, **kw: {"groups": [{"text": "x" * 1000} for _ in range(100)], "total": 100}
        result = call(p, "inspect_fort", {"name": "stocks"})
        self.assertTrue(result["truncated"])
        self.assertEqual(result["totals"]["total"], 100)
        self.assertLess(len(json.dumps(result)), 3800)

    def test_missing_query_list_does_not_create_fake_capability(self):
        p = Plain(Task({}), Game(), Model())
        with redirect_stdout(io.StringIO()):
            p.setup()
        self.assertNotIn("inspect_fort", p.tool_names)

    def test_catalogue_search_reaches_entries_after_old_preview(self):
        p = self.player()
        p.query_names = ["manager_order_types"]
        payload = {"day": 17, "result": {"ok": True,
            "condition_flags": ["padding_" + str(i) for i in range(400)],
            "job_types": [{"job": "PrepareRawFish", "caption": "Prepare a Raw Fish"}],
            "recipes": {"brew_drink": {"job": "CustomReaction", "reaction": "BREW_DRINK_FROM_PLANT"}}}}
        before = copy.deepcopy(payload)
        p.game.query = lambda name, **params: (p.game.queries.append((name, params)) or payload)
        result = call(p, "inspect_fort", {"name": "manager_order_types", "section": "job_types", "search": "fish"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["entries"], payload["result"]["job_types"])
        self.assertEqual(p.game.queries, [("manager_order_types", {})])  # local selectors never reach the API
        self.assertEqual(payload, before)

    def test_catalogue_pages_are_bounded_and_lossless(self):
        rows = [{"job": f"MakeItem{i}", "caption": "furniture " * 15} for i in range(85)]
        queries = []
        p = self.player()
        p.game.query = lambda name, **kw: (queries.append(kw) or {"result": {"ok": True, "job_types": rows}})
        collected, offset = [], 0
        for _ in range(100):
            result = inspect.run(p.game, {"name": "manager_order_types", "section": "job_types",
                                         "offset": offset, "limit": 50}, ["manager_order_types"])
            self.assertTrue(result["ok"])
            self.assertLessEqual(len(json.dumps(result, ensure_ascii=False)), inspect.LIMIT)
            page = result["result"]
            self.assertEqual(page["total"], len(rows))
            self.assertEqual(page["matches"], len(rows))
            collected.extend(page["entries"])
            nxt = page["next_offset"]
            if nxt is None:
                break
            self.assertGreater(nxt, offset)
            offset = nxt
        self.assertEqual(collected, rows)
        self.assertTrue(all(q == {} for q in queries))

    def test_catalogue_index_dict_sections_and_empty_search(self):
        p = self.player()
        payload = {"result": {"ok": True, "job_types": [{"job": "PrepareRawFish"}],
                             "recipes": {"brew_drink": {"reaction": "BREW_DRINK_FROM_PLANT"}}}}
        p.game.query = lambda *a, **kw: copy.deepcopy(payload)
        names = ["manager_order_types"]
        result = inspect.run(p.game, {"name": names[0]}, names)
        self.assertEqual(result["result"]["sections"], {"job_types": 1, "recipes": 1})
        result = inspect.run(p.game, {"name": names[0], "section": "recipes", "search": "BREW"}, names)
        self.assertEqual(result["result"]["entries"], [{"key": "brew_drink", "value": payload["result"]["recipes"]["brew_drink"]}])
        result = inspect.run(p.game, {"name": names[0], "section": "job_types", "search": "no match"}, names)
        self.assertEqual(result["result"]["entries"], [])
        self.assertIsNone(result["result"]["next_offset"])

    def test_catalogue_local_arguments_are_validated_before_query(self):
        p = self.player()
        for args in ({"name": "stocks", "section": "job_types"},
                     {"name": "manager_order_types", "section": "unknown"},
                     {"name": "manager_order_types", "offset": -1},
                     {"name": "manager_order_types", "offset": True},
                     {"name": "manager_order_types", "limit": 0},
                     {"name": "manager_order_types", "search": "fish"}):
            with self.subTest(args=args):
                result = inspect.run(p.game, args, ["stocks", "manager_order_types"])
                self.assertFalse(result["ok"])
        self.assertEqual(p.game.queries, [])

    def test_workshop_catalogue_preserves_inputs_and_oversize_is_explicit(self):
        p = self.player()
        rows = [{"type": "Fishery", "w": 3, "h": 3, "inputs": [{"item_type": "WOOD", "quantity": 1}]}]
        p.game.query = lambda *a, **kw: {"result": {"workshop_types": rows}}
        args = {"name": "workshop_types", "section": "workshop_types", "search": "fish"}
        result = inspect.run(p.game, args, ["workshop_types"])
        self.assertEqual(result["result"]["entries"], rows)
        rows[0]["inputs"][0]["description"] = "x" * 5000
        result = inspect.run(p.game, args, ["workshop_types"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "catalogue_entry_too_large")

    def test_real_loop_attaches_status_and_routes_inspection(self):
        p = self.player()
        obs = {"tick": 120000, "days_left": 5, "observation": {"stocks": {"drink": 12}, "dwarves": []}}
        p.game.observe = lambda: copy.deepcopy(obs)
        seen = []
        def chat(messages, **kw):
            seen.append(copy.deepcopy(messages))
            return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [{
                "id": "q", "function": {"name": "inspect_fort", "arguments": '{"name":"orders"}'}}]}}]}
        p.model.chat = chat
        with redirect_stdout(io.StringIO()):
            p.run(max_turns=1)
        user = next(x for x in seen[0] if x["role"] == "user")
        self.assertIn("harness_status", json.loads(user["content"].removeprefix("OBSERVATION ")))
        self.assertEqual(p.game.queries, [("orders", {})])
        self.assertEqual(p.game.calls, [])


if __name__ == "__main__":
    unittest.main()
