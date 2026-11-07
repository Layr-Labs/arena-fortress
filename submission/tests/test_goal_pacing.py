"""Check one-turn pacing for the public bed goal. No network is used."""
import io
import json
from contextlib import redirect_stdout
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_brew_growth import public_task
from test_pacing import FakeGame, FakeModel, harness


class GoalGame(FakeGame):
    def __init__(self, info, stop_early=False):
        super().__init__()
        self.info, self.stop_early = info, stop_early

    def task(self):
        return {**super().task(), "task": self.info}

    def act(self, name, args):
        if name != "advance_days" or not self.stop_early:
            return super().act(name, args)
        self.actions.append((name, args.copy()))
        self.day += 1
        self.last = {"day": self.day, "tick": self.day * 1200, "game_over": False}
        return {**self.last, "ok": True, "result": {"advanced_ticks": 1200,
            "stopped": {"reason": "hostiles", "detail": {}, "after_ticks": 1200}}}


class AdvanceModel(FakeModel):
    def chat(self, messages, **params):
        self.calls += 1
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [{
            "id": str(self.calls), "type": "function", "function": {"name": "advance_days",
                "arguments": json.dumps({"days": 3})}}]}}]}


class GoalPacing(unittest.TestCase):
    def run_agent(self, game, model, turns):
        runner = harness.Plain(SimpleNamespace(task={}, days=10, credits=None), game, model)
        with patch.object(runner.guard, "step", side_effect=runner.guard.load) as step, redirect_stdout(io.StringIO()):
            runner.run(max_turns=turns)
        return runner, [call.args[0]["day"] for call in step.call_args_list]

    def test_bed_goal_uses_one_turn_then_the_next_daily_pass(self):
        game, model = GoalGame(public_task("lt08-migrant-surge.json")), FakeModel()
        runner, guard_days = self.run_agent(game, model, 2)
        self.assertTrue(runner.guard.beds_first)
        self.assertEqual(game.actions, [("enable_automation", {"name": "autochop"}),
                                       ("advance_days", {"days": 1})] * 2)
        self.assertEqual(game.observed_days, [0, 1])
        self.assertEqual(guard_days, [0, 1])
        self.assertEqual((game.day, model.calls, runner.stats["stall_advances"]), (2, 2, 2))

    def test_model_error_adds_only_one_advance_before_the_next_daily_pass(self):
        game, model = GoalGame(public_task("lt08-migrant-surge.json")), FakeModel(fail_on=2)
        runner, guard_days = self.run_agent(game, model, 3)
        self.assertEqual([name for name, _ in game.actions],
                         ["enable_automation", "advance_days", "advance_days", "enable_automation", "advance_days"])
        self.assertEqual(game.observed_days, [0, 1, 2])
        self.assertEqual(guard_days, [0, 1, 2])
        self.assertEqual((game.day, model.calls, runner.stats["api_errors"]), (3, 3, 1))
        self.assertEqual((runner.stats["advances"], runner.stats["stall_advances"]), (3, 2))

    def test_normal_and_event_stopped_advances_do_not_add_a_stall(self):
        for name in ("lt08-migrant-surge.json", "op1-start-year.json"):
            for stop_early, elapsed in ((False, 3), (True, 1)):
                with self.subTest(task=name, stop_early=stop_early):
                    game, model = GoalGame(public_task(name), stop_early), AdvanceModel()
                    runner, guard_days = self.run_agent(game, model, 2)
                    self.assertEqual(game.actions, [("advance_days", {"days": 3})] * 2)
                    self.assertEqual(game.observed_days, [0, elapsed])
                    self.assertEqual(guard_days, [0, elapsed])
                    self.assertEqual((game.day, model.calls), (elapsed * 2, 2))
                    self.assertEqual((runner.stats["advances"], runner.stats["stall_advances"]), (2, 0))


if __name__ == "__main__":
    unittest.main()
