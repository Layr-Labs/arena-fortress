"""Partial API success must not be mistaken for completed furniture placement."""
import copy
import json
import unittest

from test_batch import run, tool


def placement(n=2, requested=18, available=19, **extra):
    return {"ok": True, "result": {"placed": "bed", "n": n, "requested": requested,
                                     "available": available, "tiles_rejected": 0, **extra}}


class PlacementTests(unittest.TestCase):
    def test_space_limited_partial_success_is_a_batch_barrier(self):
        response = placement()
        before = copy.deepcopy(response)
        calls = [tool("place_furniture", {"kind": "bed", "site": "A1", "count": 18}),
                 tool("enable_automation", {"name": "autolabor"})]
        p, game, _, results = run(calls, [response], offered=("place_furniture", "enable_automation"))
        self.assertEqual([name for name, _ in game.calls], ["place_furniture"])
        self.assertTrue(results[0]["ok"])  # Do not rewrite the successful API result as a refusal.
        self.assertEqual(results[0]["result"], response["result"])
        self.assertEqual(results[1]["error_code"], "batch_stopped")
        diagnostic = results[0]["harness_placement"]
        self.assertEqual(diagnostic["not_designated"], 16)
        self.assertEqual(diagnostic["limitation"], "space_or_tile_rejection")
        self.assertIn("not completed", diagnostic["advice"])
        self.assertIn("smaller count", diagnostic["advice"])
        self.assertEqual(p.stats["rejected"], 0)
        self.assertEqual(response, before)

    def test_stock_limited_partial_success_reports_unplaced_not_missing_space(self):
        calls = [tool("place_furniture", {"kind": "bed", "site": "A2", "count": 30}),
                 tool("enable_automation")]
        _, game, _, results = run(calls, [placement(17, 30, 17)], offered=("place_furniture", "enable_automation"))
        self.assertEqual(len(game.calls), 1)
        diagnostic = results[0]["harness_placement"]
        self.assertEqual(diagnostic["not_designated"], 13)
        self.assertEqual(diagnostic["limitation"], "free_items")
        self.assertIn("free furniture", diagnostic["advice"].lower())
        self.assertIn("not completed", diagnostic["advice"])

    def test_full_placement_preserves_independent_batching_and_exact_response(self):
        calls = [tool("place_furniture", {"kind": "bed", "site": "A2", "count": 2}),
                 tool("enable_automation")]
        response = placement(2, 2, 17)
        _, game, _, results = run(calls, [response], offered=("place_furniture", "enable_automation"))
        self.assertEqual(len(game.calls), 2)
        self.assertEqual(results[0], response)

    def test_partial_diagnostic_is_whole_in_the_next_model_request(self):
        calls = [tool("place_furniture", {"kind": "bed", "site": "A1", "count": 18})]
        _, _, requests, _ = run(calls, [placement(), placement()], turns=2, offered=("place_furniture",))
        results = [json.loads(m["content"]) for m in requests[1] if m["role"] == "tool"]
        self.assertEqual(results[0]["harness_placement"]["not_designated"], 16)
        self.assertEqual(results[0]["result"]["n"], 2)

    def test_failed_unrelated_or_malformed_results_are_not_interpreted(self):
        from plain.harness import placement_shortfall
        for response in ({"ok": False, "result": placement()["result"]},
                         {"ok": True}, {"ok": True, "result": "unavailable"},
                         placement(True), placement(-1), placement(20, 18),
                         placement(2, "18"), placement(2, 18, "19")):
            with self.subTest(response=response):
                self.assertIsNone(placement_shortfall("place_furniture", response))
        self.assertIsNone(placement_shortfall("other_tool", placement()))

    def test_rejected_tiles_do_not_create_certainty_that_more_items_would_help(self):
        from plain.harness import placement_shortfall
        diagnostic = placement_shortfall("place_furniture", placement(2, 18, 2, tiles_rejected=3))
        self.assertEqual(diagnostic["limitation"], "free_items")
        self.assertIn("space", diagnostic["advice"])


if __name__ == "__main__":
    unittest.main()
