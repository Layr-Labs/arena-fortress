"""The wall guard (ROOT_CAUSES §L): five dev games died at runner_deadline advancing one day a turn. When the
wall time the rest of the run needs at the measured pace crosses ~85% of the clock left, the model loop hands the
run to the deterministic layer, which advances 7 days a pass — and flood-caused pending digs never pin the pace
to one day. No network (the same fake shapes as tests/test_pacing.py)."""
import io
import json
import sys
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from plain import harness  # noqa: E402

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class FakeGame:
    def __init__(self, days=300):
        self.days = days
        self.day = 0
        self.actions, self.observed = [], []
        self.last = {"tick": 0}
        self.advance_result = {}

    def task(self):
        return {"task": {"days": self.days}, "tools": [
            {"type": "function", "function": {"name": "enable_automation", "parameters": {
                "type": "object", "properties": {"name": {"type": "string"}}}}},
            {"type": "function", "function": {"name": "advance_days", "parameters": {
                "type": "object", "properties": {"days": {"type": "integer", "maximum": 28}}}}}]}

    def observe(self):
        self.observed.append(self.day)
        self.last = {"day": self.day, "tick": self.day * 1200, "days_left": self.days - self.day,
                     "game_over": self.day >= self.days}
        return {**self.last, "observation": {"date": {"abs_tick": self.last["tick"]},
                                             "dig_designations_pending": 0}}

    def act(self, name, args):
        self.actions.append((name, dict(args)))
        if name == "advance_days":
            self.day += args["days"]
        self.last = {"day": self.day, "tick": self.day * 1200, "game_over": self.day >= self.days}
        return {**self.last, "ok": True, "result": dict(self.advance_result)}


class FakeModel:
    def __init__(self):
        self.calls = 0
        self.usage = {"cost_usd": 0}

    def chat(self, messages, **params):
        self.calls += 1
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [{
            "id": str(self.calls), "type": "function", "function": {"name": "enable_automation",
                "arguments": json.dumps({"name": "autochop"})}}]}}]}


def runner(days=300, wall_s=1000):
    game, model = FakeGame(days), FakeModel()
    r = harness.Plain(SimpleNamespace(task={"days": days}, days=days, credits=None, wall_s=wall_s), game, model)
    return r, game, model


class PaceProjection(unittest.TestCase):
    """(elapsed wall − throttle) per advanced day × the days left, against ~85% of the clock left."""

    def test_a_slow_pace_projects_past_the_remaining_budget(self):
        r, game, model = runner(wall_s=1000)
        r.t0 = time.monotonic() - 500   # 500 s of the 1000 s budget spent
        r.model_wait = 0.0
        r.day0 = 0
        self.assertTrue(r.wall_pace_due({"day": 100, "days_left": 200}))
        # 500/100 days = 5 s a day; 5 × 200 left = 1000 > 0.85 × 500 left

    def test_a_pace_inside_the_budget_stays_with_the_model(self):
        r, game, model = runner(wall_s=1000)
        r.t0 = time.monotonic() - 500
        r.day0 = 0
        self.assertFalse(r.wall_pace_due({"day": 100, "days_left": 10}))   # 5 × 10 = 50 < 425
        self.assertFalse(r.wall_pace_due({"day": 3, "days_left": 297}))    # too few days measured: noise

    def test_the_model_wait_is_subtracted_as_the_throttle_term(self):
        r, game, model = runner(wall_s=1000)
        r.t0 = time.monotonic() - 500
        r.model_wait = 450.0   # the throttled gateway: the layer needs none of it
        r.day0 = 0
        self.assertFalse(r.wall_pace_due({"day": 100, "days_left": 200}))   # 0.5 × 200 = 100 < 425

    def test_no_wall_limit_never_switches(self):
        game, model = FakeGame(), FakeModel()
        r = harness.Plain(SimpleNamespace(task={"days": 300}, days=300, credits=None), game, model)
        r.t0 = time.monotonic() - 10 ** 6
        r.day0 = 0
        self.assertFalse(r.wall_pace_due({"day": 100, "days_left": 200}))


class SwitchAndStride(unittest.TestCase):
    """The switch to layer-only, and the 7-day advances it runs the horizon down with."""

    def test_the_pace_guard_switches_to_layer_only_and_advances_seven_days(self):
        r, game, model = runner(days=300)
        with patch.object(r, "wall_pace_due", return_value=True), redirect_stdout(io.StringIO()):
            r.run(max_turns=1)
        advances = [a["days"] for name, a in game.actions if name == "advance_days"]
        self.assertTrue(advances)
        self.assertEqual(set(advances), {7})          # the wall-pace stride, to the horizon
        self.assertEqual(r.stats["wall_switches"], 1)
        self.assertEqual(r.stop_reason, "game_over")

    def test_a_close_hands_off_window_steps_one_day_even_on_the_pace_guard(self):
        r, game, model = runner(days=300)
        with patch.object(r, "wall_pace_due", return_value=True), redirect_stdout(io.StringIO()):
            game.days_left_holder = None
            # the first observation inside layer_only reports a hands-off window 3 days out
            orig = game.observe

            def observe():
                resp = orig()
                resp["hands_off_in_days"] = 3
                return resp
            game.observe = observe
            r.run(max_turns=1)
        advances = [a["days"] for name, a in game.actions if name == "advance_days"]
        self.assertTrue(advances)
        self.assertEqual(set(advances), {1})

    def test_layer_days_picks_the_stride_by_reason(self):
        r, game, model = runner()
        resp = {"day": 20, "hands_off_in_days": None}
        self.assertEqual(r.layer_days(resp, pace=True), 7)
        self.assertEqual(r.layer_days(resp, pace=False), 2)   # the quiet pacing, past day 14
        self.assertEqual(r.layer_days({"day": 20, "hands_off_in_days": 3}, pace=True), 1)


class FloodedPendingPace(unittest.TestCase):
    """(d) flood-caused pending digs never pin the quiet pace to one day."""

    def test_pending_digs_over_a_breach_do_not_force_one_day(self):
        r, game, model = runner()
        with redirect_stdout(io.StringIO()):
            r.guard.load({"day": 20, "tick": 20 * 1200,
                          "observation": {"date": {"abs_tick": 20 * 1200}, "dig_designations_pending": 5}})
        resp = {"day": 20, "hands_off_in_days": None,
                "observation": {"dig_designations_pending": 5}}
        self.assertEqual(r.quiet_days(resp), 1)   # plain pending digs keep the one-day pace
        r.guard.breach = {"day": 8, "z": None}
        r.guard.wet_z = {97}
        self.assertEqual(r.quiet_days(resp), 2)   # the flood's designations never clear: the pace frees up
        self.assertEqual(r.quiet_days({"day": 10, "hands_off_in_days": None, "observation": {
            "dig_designations_pending": 5}}), 1)  # the early-game rule still pins day < 14


class WaterRisingHook(unittest.TestCase):
    """B-2's link into the plain loop: a water_rising stop arms the overseer's breach check."""

    def test_an_advance_that_stops_on_water_rising_calls_the_breach_check(self):
        r, game, model = runner()
        game.advance_result = {"stopped": {"reason": "water_rising"}}
        with patch.object(r.guard, "water_rising_stop") as hook, redirect_stdout(io.StringIO()):
            r.advance(2, "test")
        self.assertEqual(hook.call_count, 1)

    def test_a_plain_advance_does_not_touch_the_breach_check(self):
        r, game, model = runner()
        with patch.object(r.guard, "water_rising_stop") as hook, redirect_stdout(io.StringIO()):
            r.advance(2, "test")
        self.assertEqual(hook.call_count, 0)


if __name__ == "__main__":
    unittest.main()
