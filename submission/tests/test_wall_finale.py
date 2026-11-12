"""Check the wall-budget exit: no model call starts without enough wall budget left.

The saved evidence: every local MY1 game hit the server wall cap before the horizon
(end days 85.8, 143, 145.7 and 162.7 of 216). Model-call latency alone took 2942-2964
of the 3600-3645 seconds used; median 40-50 s per call, p90 42-75 s, max 89.5 s.

The rule that decides the fix (server rules.py, RULES.md §6, SCORING.md §6): when the
harness exits, POST /finish runs the fort on unmanaged to the horizon and the score is
taken there; when the wall watchdog fires first, the game ends at the cap tick with no
run-out at all. So the last thing the harness should do is start a model call that
will not finish before the cap: the answer lands after the cap, useless, and staying
in the loop until the watchdog throws away the run-out.

The change under test: before each model call the loop compares the wall budget left
(server /health wall_used_s against the task's wall_s) with an estimate from this
run's own recent latencies (WALL_CALL_DEFAULT before the first result, then the
slowest of the last WALL_CALL_RECENT calls) plus WALL_MARGIN. When the budget no
longer covers one call, the loop stops calling the model and exits with stop_reason
"wall_budget". No wall_s (or a client without /health) keeps the old behaviour.

A fake clock drives time: each model call costs its latency, each act costs 1 s,
observe and health cost 0. No network is used.
"""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from plain import harness  # noqa: E402
from test_pacing import FakeGame, FakeModel  # noqa: E402

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

MARGIN = harness.WALL_MARGIN


class Clock:
    """A monotonic clock that only moves when the harness acts or calls the model."""

    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    def spend(self, s):
        self.t += s


class WallGame(FakeGame):
    """FakeGame on the shared clock: 1 s per act; /health reports wall_used_s."""

    def __init__(self, clock, horizon=216, wall_s=None):
        super().__init__()
        self.clock = clock
        self.horizon = horizon
        self.wall_s = wall_s
        self.health_calls = 0

    def observe(self):
        self.observed_days.append(self.day)
        self.last = {"day": self.day, "tick": self.day * 1200,
                     "days_left": max(0, self.horizon - self.day),
                     "game_over": self.day >= self.horizon}
        return {**self.last, "observation": {"date": {"abs_tick": self.last["tick"]}}}

    def task(self):
        t = super().task()
        t["task"] = {"days": self.horizon}
        t["limits"] = {"wall_s": self.wall_s}
        return t

    def health(self):
        self.health_calls += 1
        h = {"phase": "running", "ok": True}
        if self.wall_s is not None:
            h["wall_used_s"] = round(self.clock.t, 3)
        return h

    def act(self, name, args):
        self.clock.spend(1.0)
        if name == "advance_days":
            args = {**args, "days": min(args["days"], self.horizon - self.day)}
        return super().act(name, args)


class LatencyModel(FakeModel):
    """FakeModel whose every call costs a fixed latency on the shared clock."""

    def __init__(self, clock, latency=50.0):
        super().__init__()
        self.clock = clock
        self.latency = latency

    def chat(self, messages, **params):
        self.clock.spend(self.latency)
        return super().chat(messages, **params)


class AdvanceOnlyModel(LatencyModel):
    """Requests a 14-day advance on every turn."""

    def chat(self, messages, **params):
        self.clock.spend(self.latency)
        self.calls += 1
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [{
            "id": str(self.calls), "type": "function", "function": {
                "name": "advance_days", "arguments": '{"days": 14}'}}]}}]}


def run_plain(horizon, wall_s, latency, turns=500, model=None):
    """Run the plain loop on the fake clock. Returns (runner, game, model, clock)."""
    clock = Clock()
    game = WallGame(clock, horizon, wall_s)
    model = model(clock) if model else LatencyModel(clock, latency)
    runner = harness.Plain(SimpleNamespace(task={"days": horizon}, days=horizon,
                                           credits=None), game, model)
    with patch.object(runner.guard, "step", return_value=0), redirect_stdout(io.StringIO()):
        with patch.object(harness.time, "monotonic", clock.monotonic):
            runner.run(max_turns=turns)
    return runner, game, model, clock


class WallBudget(unittest.TestCase):
    def test_exits_before_the_cap_instead_of_running_into_it(self):
        # 216-day MY1-style task, 300 s budget, 50 s calls plus 1 s per act: the
        # gate fires when one more estimated call plus margin no longer fits, and
        # the loop exits with the budget still unspent — the run-out is the
        # runner's /finish, outside the harness.
        runner, game, model, clock = run_plain(216, 300, 50.0)
        self.assertEqual(runner.stop_reason, "wall_budget")
        self.assertGreater(model.calls, 0)
        self.assertLessEqual(clock.t, 300.0 - MARGIN)     # a real margin, not a hair's width
        self.assertLessEqual(len(game.actions), model.calls * 2)  # one act per call, each may add a stall day
        self.assertLess(game.day, 216)                    # the horizon is the server's job now

    def test_no_wall_s_keeps_the_old_behaviour(self):
        # No server wall_s: wall_left() is always None so the gate can never fire;
        # the turn limit stops the loop as before. (/health is still read once per
        # game day by frontier54's quiet pacing — that predates the gate and is
        # not a gate read.)
        runner, game, model, clock = run_plain(216, None, 50.0, turns=6)
        self.assertIsNone(runner.stop_reason)
        self.assertEqual(model.calls, 6)
        self.assertIsNone(runner.wall_left())

    def test_generous_budget_never_fires(self):
        # A horizon the budget comfortably reaches (LT08-style) must be unchanged:
        # the game ends at the horizon, not at the gate.
        runner, game, model, clock = run_plain(20, 1800, 50.0, model=AdvanceOnlyModel)
        self.assertEqual(runner.stop_reason, "game_over")
        self.assertEqual(game.day, 20)
        self.assertLess(clock.t, 200)

    def test_estimate_follows_a_latency_jump(self):
        # Calls start at 20 s then jump to 90 s. The gate must count with the slow
        # calls: no call may finish after the cap, and the exit keeps a margin.
        clock = Clock()
        game = WallGame(clock, 216, 300)

        class Mixed(FakeModel):
            def __init__(self):
                super().__init__()
                self.lat = [20.0] * 3 + [90.0] * 30

            def chat(self, messages, **params):
                clock.spend(self.lat[min(self.calls, len(self.lat) - 1)])
                return super().chat(messages, **params)

        model = Mixed()
        runner = harness.Plain(SimpleNamespace(task={"days": 216}, days=216,
                                               credits=None), game, model)
        with patch.object(runner.guard, "step", return_value=0), redirect_stdout(io.StringIO()):
            with patch.object(harness.time, "monotonic", clock.monotonic):
                runner.run(max_turns=500)
        self.assertEqual(runner.stop_reason, "wall_budget")
        self.assertLessEqual(clock.t, 300.0 - MARGIN)
        self.assertGreater(model.calls, 3)   # the fast phase was not cut short

    def test_first_calls_always_fire_on_a_fresh_game(self):
        # 500 s budget, unknown latency: the default estimate must not stop the
        # first calls of a fresh game.
        runner, game, model, clock = run_plain(216, 500, 10.0, turns=4)
        self.assertEqual(model.calls, 4)
        self.assertNotEqual(runner.stop_reason, "wall_budget")

    def test_a_client_without_health_never_fires_the_gate(self):
        # wall_s is set but the client has no /health: wall_left yields None and the
        # loop runs on; a broken health probe must not stop the game.
        clock = Clock()

        class LimitOnlyGame(FakeGame):
            def task(self):
                t = super().task()
                t["limits"] = {"wall_s": 300}
                return t

        game = LimitOnlyGame()
        model = LatencyModel(clock, 50.0)
        runner = harness.Plain(SimpleNamespace(task={"days": 10}, days=10, credits=None), game, model)
        with patch.object(runner.guard, "step", return_value=0), redirect_stdout(io.StringIO()):
            with patch.object(harness.time, "monotonic", clock.monotonic):
                runner.run(max_turns=500)
        self.assertNotEqual(runner.stop_reason, "wall_budget")
        self.assertEqual(model.calls, 500)


if __name__ == "__main__":
    unittest.main()
