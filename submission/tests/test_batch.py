"""Independent model-selected actions must not need one paid call apiece."""
import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace

from dfbench_client.errors import ActionLimit, GameOver, HandsOff
from dfbench_client.task import Task
from plain.harness import Plain


def tool(name, args=None, ident=None):
    return {"id": ident or name, "type": "function", "function": {
        "name": name, "arguments": json.dumps(args or {})}}


class Game:
    def __init__(self, replies=()):
        self.last = {"tick": 120000}
        self.calls = []
        self.replies = iter(replies)

    def task(self):
        return {"tools": [{"type": "function", "function": {"name": n, "parameters": {}}}
                          for n in ("enable_automation", "build_workshop", "advance_days")],
                "task": {"days": 60}}

    def observe(self):
        return {"tick": self.last["tick"], "days_left": 60, "observation": {}}

    def act(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        reply = next(self.replies, {"ok": True})
        if isinstance(reply, Exception):
            raise reply
        if name == "advance_days":
            self.last["tick"] += 1200
        return reply


def run(calls, replies=(), turns=1, offered=None):
    game = Game(replies)
    if offered is not None:
        game.task = lambda: {"tools": [{"type": "function", "function": {"name": n, "parameters": {}}}
                                       for n in offered], "task": {"days": 60}}
    requests = []
    def chat(messages, **kwargs):
        requests.append(copy.deepcopy(messages))
        return {"choices": [{"message": {"role": "assistant", "content": None,
                                         "tool_calls": calls}}]}
    model = SimpleNamespace(usage={}, chat=chat)
    player = Plain(Task({"task": {"days": 60}}), game, model)
    with redirect_stdout(io.StringIO()):
        player.run(max_turns=turns)
    results = [json.loads(m["content"]) for m in player.messages if m["role"] == "tool"]
    return player, game, requests, results


class BatchTests(unittest.TestCase):
    def test_three_independent_actions_use_one_model_request(self):
        calls = [tool("enable_automation", {"name": n}, str(i))
                 for i, n in enumerate(("autolabor", "autofarm", "seedwatch"))]
        p, g, requests, results = run(calls)
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(g.calls), 3)
        self.assertTrue(all(r["ok"] for r in results))
        self.assertEqual(p.stats["actions"], 3)

    def test_failure_stops_suffix_and_preserves_all_call_ids(self):
        calls = [tool("enable_automation", ident=str(i)) for i in range(3)]
        p, g, _, results = run(calls, [{"ok": False, "error_code": "bad_arguments"}])
        self.assertEqual(len(g.calls), 1)
        self.assertEqual([m["tool_call_id"] for m in p.messages if m["role"] == "tool"], ["0", "1", "2"])
        self.assertEqual([r.get("error_code") for r in results],
                         ["bad_arguments", "batch_stopped", "batch_stopped"])

    def test_advance_is_a_barrier_even_before_batch_cap(self):
        calls = [tool("enable_automation", ident="a"), tool("advance_days", {"days": 1}),
                 tool("enable_automation", ident="b")]
        _, g, _, results = run(calls)
        self.assertEqual([n for n, _ in g.calls], ["enable_automation", "advance_days"])
        self.assertTrue(results[1]["ok"])
        self.assertEqual(results[2].get("error_code"), "batch_stopped")

    def test_at_most_four_actions_are_executed(self):
        _, g, _, results = run([tool("enable_automation", ident=str(i)) for i in range(6)])
        self.assertEqual(len(g.calls), 4)
        self.assertEqual(len(results), 6)
        self.assertEqual(results[-1].get("error_code"), "batch_stopped")

    def test_action_limit_advances_once_then_discards_suffix(self):
        _, g, _, results = run([tool("enable_automation", ident=str(i)) for i in range(3)],
                               [ActionLimit("quota reached"), {"ok": True}])
        self.assertEqual([n for n, _ in g.calls], ["enable_automation", "advance_days"])
        self.assertEqual(results[0]["error_code"], "action_limit")
        self.assertEqual(results[1].get("error_code"), "batch_stopped")

    def test_terminal_errors_complete_tool_protocol_without_more_actions(self):
        for error in (HandsOff("handover"), GameOver("finished")):
            with self.subTest(error=type(error).__name__):
                p, g, _, results = run([tool("enable_automation", ident=str(i)) for i in range(3)], [error])
                self.assertEqual(len(g.calls), 1)
                self.assertEqual(p.stop_reason, type(error).__name__)
                self.assertEqual(len(results), 3)
                self.assertTrue(all(not r["ok"] for r in results))

    def test_failed_validation_is_a_batch_barrier(self):
        calls = [tool("not_offered"), tool("enable_automation")]
        _, g, _, results = run(calls)
        self.assertEqual(g.calls, [])
        self.assertEqual(results[0]["error_code"], "unknown_tool")
        self.assertEqual(results[1].get("error_code"), "batch_stopped")

    def test_prompt_describes_independence_and_observation_barriers(self):
        from plain.prompt import system_prompt
        text = system_prompt(None, {"enable_automation"})
        self.assertIn("up to 4", text)
        self.assertIn("independent", text)
        self.assertNotIn("one tool call per turn", text)

    def test_fresh_batch_results_are_whole_in_next_request(self):
        payload = {"ok": True, "information": "x" * 900}
        _, _, requests, _ = run([tool("enable_automation", ident=str(i)) for i in range(3)],
                                [payload] * 6, turns=2)
        results = [json.loads(m["content"]) for m in requests[1] if m["role"] == "tool"]
        self.assertEqual(results, [payload] * 3)

    def test_long_skipped_suffix_does_not_orphan_tool_results(self):
        _, _, requests, _ = run([tool("not_offered", ident=str(i)) for i in range(16)], turns=2)
        received = requests[1]
        assistant = next(m for m in received if m["role"] == "assistant")
        results = [m for m in received if m["role"] == "tool"]
        self.assertEqual(len(assistant["tool_calls"]), 16)
        self.assertEqual(len(results), 16)

    def test_stall_guard_counts_actions_and_stops_mid_batch(self):
        p, g, _, results = run([tool("enable_automation", ident=str(i)) for i in range(4)], turns=3)
        self.assertEqual([n for n, _ in g.calls], ["enable_automation"] * 10 + ["advance_days"])
        self.assertEqual(p.stats["stall_advances"], 1)
        self.assertEqual(results[-1].get("error_code"), "batch_stopped")


if __name__ == "__main__":
    unittest.main()
