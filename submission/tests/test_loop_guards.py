"""Loop guards: the wall-clock handover to the layer, the layer-only gateway probe, and the adaptive advance caps.
No network is used; the layer's step() is stubbed (its behaviour is tested in the overseer's own tests)."""
import io
import json
import time
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

MAX_DAYS = harness.MAX_DAYS


class FakeGame:
    def __init__(self, limit=50):
        self.day = 0
        self.limit = limit
        self.hands_off = None   # mirrored into the responses, as the real server does
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
        self.last = {"day": self.day, "tick": self.day * 1200, "days_left": self.limit - self.day,
                     "game_over": self.day >= self.limit}
        if self.hands_off is not None:
            self.last["hands_off_in_days"] = self.hands_off
        return {**self.last, "observation": {"date": {"abs_tick": self.last["tick"]}}}

    def act(self, name, args):
        self.actions.append((name, dict(args)))
        if name == "advance_days":
            self.day += args["days"]
        self.last = {"day": self.day, "tick": self.day * 1200, "game_over": self.day >= self.limit}
        if self.hands_off is not None:
            self.last["hands_off_in_days"] = self.hands_off
        return {**self.last, "ok": True, "result": {}}


class FakeModel:
    def __init__(self, fail_calls=0):
        self.calls = 0
        self.fail_calls = fail_calls
        self.usage = {"cost_usd": 0}

    def chat(self, messages, **params):
        self.calls += 1
        if self.calls <= self.fail_calls:
            raise ModelError("simulated gateway error")
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [{
            "id": str(self.calls), "type": "function", "function": {"name": "enable_automation",
                "arguments": json.dumps({"name": "autochop"})}}]}}]}


def runner_with(game, model):
    return harness.Plain(SimpleNamespace(task={"days": 10}, days=10, credits=None), game, model)


class LoopGuards(unittest.TestCase):
    def test_wall_reserve_hands_the_run_to_the_layer(self):
        game, model = FakeGame(limit=5), FakeModel()
        runner = runner_with(game, model)
        runner.wall_s = 100
        runner.t0 = time.monotonic() - 90.5   # 9.5 s of 100 s left: under WALL_RESERVE, over the sprint threshold
        buf = io.StringIO()
        with patch.object(runner.guard, "step", return_value=0), \
                patch.object(runner, "probe", return_value=False), redirect_stdout(buf):
            runner.run()
        out = buf.getvalue()
        self.assertIn('"kind": "wall_guard"', out)
        self.assertIn('"kind": "layer_only"', out)
        self.assertIn('"reason": "wall"', out)
        self.assertEqual(model.calls, 0)   # not a single model turn under the wall guard
        self.assertEqual(game.day, 5)      # the layer still ran the fort to the horizon
        self.assertTrue(game.actions and all(n == "advance_days" and a["days"] == 1
                                             for n, a in game.actions))   # quiet_days pacing unchanged
        self.assertEqual(runner.stats["api_errors"], 0)

    def test_wall_sprint_runs_big_advances_to_the_horizon(self):
        game, model = FakeGame(limit=50), FakeModel()
        runner = runner_with(game, model)
        runner.wall_s = 100
        runner.t0 = time.monotonic() - 99   # 1% left: inside the sprint reserve
        buf = io.StringIO()
        with patch.object(runner.guard, "step", return_value=0), \
                patch.object(runner, "probe", return_value=False), redirect_stdout(buf):
            runner.run()
        days = [a["days"] for n, a in game.actions if n == "advance_days"]
        self.assertTrue(days and days[0] == 14 and all(d >= 8 for d in days))   # min(MAX_DAYS, days_left), not quiet
        self.assertEqual(runner.stats["wall_sprints"], len(days))
        self.assertIn('"phase": "sprint"', buf.getvalue())
        self.assertEqual(game.day, 50)

    def test_probe_success_returns_to_the_model_loop(self):
        game, model = FakeGame(), FakeModel(fail_calls=5)   # 5 failed turns, then the gateway recovers
        runner = runner_with(game, model)
        with patch.object(runner.guard, "step", return_value=0), redirect_stdout(io.StringIO()):
            runner.run(max_turns=6)
        self.assertEqual(model.calls, 7)   # 5 failed turns + 1 probe (its success) + 1 real turn after resume
        self.assertEqual(runner.stats["probe_ok"], 1)
        self.assertEqual(runner.stats["probe_fails"], 0)
        self.assertEqual(runner.stats["api_errors"], 5)
        self.assertEqual([n for n, _ in game.actions].count("enable_automation"), 1)   # the loop resumed and acted

    def test_surge_bed_shortfall_clamps_advance_to_two_days(self):
        game, model = FakeGame(), FakeModel()
        runner = runner_with(game, model)
        runner.setup()
        g = runner.guard
        g.surge, g.cit = True, 20
        g.placed, g.st = {"bed": 5}, {"beds": 3}   # 8 beds against the wave's 20 + 12 target
        g.o, g.hands_off = {"threats": {"visible_hostiles": 0}, "moods": []}, None
        self.assertEqual(runner.advance_cap(), 2)
        with redirect_stdout(io.StringIO()):
            moved = runner.run_call({"id": "t1", "function": {
                "name": "advance_days", "arguments": json.dumps({"days": 14})}})
        self.assertTrue(moved)
        self.assertEqual(game.actions[-1], ("advance_days", {"days": 2}))
        self.assertEqual(runner.stats["adv_clamped"], 1)

    def test_near_hands_off_window_clamps_advance_to_three_days(self):
        game, model = FakeGame(), FakeModel()
        runner = runner_with(game, model)
        runner.setup()
        g = runner.guard
        g.surge, g.cit = False, 10
        g.placed, g.st = {"bed": 12}, {"beds": 10}
        g.o = {"threats": {"visible_hostiles": 0}, "moods": []}
        g.hands_off = game.hands_off = 10   # inside HANDS_OFF_NEAR: the layer preps the window daily
        self.assertEqual(runner.advance_cap(), 3)
        with redirect_stdout(io.StringIO()):
            runner.run_call({"id": "t1", "function": {
                "name": "advance_days", "arguments": json.dumps({"days": 14})}})
        self.assertEqual(game.actions[-1], ("advance_days", {"days": 3}))
        g.hands_off = game.hands_off = 3   # under 4 days: the existing one-day-at-a-time rule wins over the cap
        game.observe()   # refresh the harness's view of the last server response, as the real loop would
        with redirect_stdout(io.StringIO()):
            runner.run_call({"id": "t2", "function": {
                "name": "advance_days", "arguments": json.dumps({"days": 14})}})
        self.assertEqual(game.actions[-1], ("advance_days", {"days": 1}))
        g.hands_off = game.hands_off = None   # nothing pressing: the full cap stands
        self.assertEqual(runner.advance_cap(), MAX_DAYS)

    def test_other_guard_states_cap_advances(self):
        game, model = FakeGame(), FakeModel()
        runner = runner_with(game, model)
        runner.setup()
        g = runner.guard
        g.surge, g.cit = False, 10
        g.placed, g.st = {"bed": 12}, {"beds": 10}
        g.hands_off = None
        g.o = {"threats": {"visible_hostiles": 3}, "moods": []}
        self.assertEqual(runner.advance_cap(), MAX_DAYS)   # hostiles ride the advance tripwire, not a call-taxing clamp
        g.o = {"threats": {"visible_hostiles": 0}, "moods": [{"mood": "Fey"}]}
        self.assertEqual(runner.advance_cap(), 1)   # a strange mood beats everything but itself
        g.o = {"threats": {"visible_hostiles": 0}, "moods": []}
        self.assertEqual(runner.advance_cap(), MAX_DAYS)   # calm fort: no clamp


if __name__ == "__main__":
    unittest.main()
