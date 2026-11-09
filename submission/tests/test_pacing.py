"""Check that the four-turn limit starts the next daily guard pass. No network is used."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from dfbench_client import ModelError
from plain import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class FakeGame:
    def __init__(self):
        self.day = 0
        self.actions, self.observed_days = [], []
        self.last = {"tick": 0}

    def task(self):
        return {"task": {"days": 10}, "tools": [
            {"type": "function", "function": {"name": "enable_automation", "parameters": {
                "type": "object", "properties": {"name": {"type": "string"}}}}},
            {"type": "function", "function": {"name": "advance_days", "parameters": {
                "type": "object", "properties": {"days": {"type": "integer", "maximum": 28}}}}}]}

    def observe(self):
        self.observed_days.append(self.day)
        self.last = {"day": self.day, "tick": self.day * 1200, "days_left": 10 - self.day, "game_over": False}
        return {**self.last, "observation": {"date": {"abs_tick": self.last["tick"]}}}

    def act(self, name, args):
        self.actions.append((name, args.copy()))
        if name == "advance_days":
            self.day += args["days"]
        self.last = {"day": self.day, "tick": self.day * 1200, "game_over": False}
        return {**self.last, "ok": True, "result": {}}


class FakeModel:
    def __init__(self, fail_on=None):
        self.calls = 0
        self.fail_on = fail_on
        self.usage = {"cost_usd": 0}

    def chat(self, messages, **params):
        self.calls += 1
        if self.calls == self.fail_on:
            raise ModelError("Simulated gateway error")
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [{
            "id": str(self.calls), "type": "function", "function": {"name": "enable_automation",
                "arguments": json.dumps({"name": "autochop"})}}]}}]}


class Pacing(unittest.TestCase):
    def test_four_model_turns_advance_then_run_the_next_daily_guard(self):
        game, model = FakeGame(), FakeModel()
        runner = harness.Plain(SimpleNamespace(task={"days": 10}, days=10, credits=None), game, model)
        # Isolate the unchanged stall/error fallback from the new consultation scheduler.
        with patch.object(runner, "model_ready", return_value=True), \
                patch.object(runner.guard, "step", return_value=0) as step, redirect_stdout(io.StringIO()):
            runner.run(max_turns=5)
        self.assertEqual([name for name, _ in game.actions],
                         ["enable_automation"] * 4 + ["advance_days", "enable_automation"])
        self.assertEqual(game.actions[4], ("advance_days", {"days": 1}))
        self.assertEqual(game.observed_days, [0, 0, 0, 0, 1])
        self.assertEqual([call.args[0]["day"] for call in step.call_args_list], [0, 1])
        self.assertEqual((model.calls, runner.stats["stall_advances"]), (5, 1))

    def test_migrant_shortfall_caps_only_unhoused_advances(self):
        for migrant, beds, expected in ((True, 9, 2), (True, 10, 14), (False, 9, 14)):
            with self.subTest(migrant=migrant, beds=beds):
                game, model = FakeGame(), FakeModel()
                task = SimpleNamespace(task={"days": 60, "goal": "migrants" if migrant else "fort"},
                                       days=60, credits=None)
                runner = harness.Plain(task, game, model)
                with redirect_stdout(io.StringIO()):
                    runner.setup()
                    runner.guard.cit = 10
                    runner.guard.placed = {"bed": beds}
                    runner.run_call({"id": "advance", "function": {
                        "name": "advance_days", "arguments": '{"days": 14}'}})
                self.assertEqual(game.actions[-1], ("advance_days", {"days": expected}))

    def test_model_error_advance_resets_idle_before_the_next_model_turn(self):
        game, model = FakeGame(), FakeModel(fail_on=4)
        runner = harness.Plain(SimpleNamespace(task={"days": 10}, days=10, credits=None), game, model)
        # Isolate the unchanged stall/error fallback from the new consultation scheduler.
        with patch.object(runner, "model_ready", return_value=True), \
                patch.object(runner.guard, "step", return_value=0) as step, redirect_stdout(io.StringIO()):
            runner.run(max_turns=5)
        self.assertEqual([name for name, _ in game.actions],
                         ["enable_automation"] * 3 + ["advance_days", "enable_automation"])
        self.assertEqual(game.actions[3], ("advance_days", {"days": 1}))
        self.assertEqual(game.observed_days, [0, 0, 0, 0, 1])
        self.assertEqual([call.args[0]["day"] for call in step.call_args_list], [0, 1])
        self.assertEqual((game.day, model.calls, runner.stats["api_errors"]), (1, 5, 1))
        self.assertEqual((runner.stats["advances"], runner.stats["stall_advances"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
