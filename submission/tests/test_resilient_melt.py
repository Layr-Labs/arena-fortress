"""Check recovery from a gateway melt: creep forward safely instead of giving up.

The saved evidence (qwen-f54wx-my1-INFRAFAILED-gateway-melt): five consecutive
'gateway unreachable: timed out' at day 4 of a 216-day MY1 abandoned the run at
wall 970/3600 while the standing orders could still carry the fort 200+ days.
Melts recover in minutes; the fix is patience, bounded.

The change under test (plain loop only): on ModelError with the guard reporting
quiet(), from the third consecutive failure the harness runs recover_turn() —
one safe advance with the quiet pacing's stop_on tripwires — and lets the next
loop iteration's model call serve as the gateway probe. It gives up with
model_failing only when the fort is not quiet (the model's judgement is needed
and cannot be had) or after RECOVER_MAX recovery days. The measured wall gate
still runs at the top of every iteration, so a melt can never burn past the cap.

Clock and games are the wall-finale fakes: model calls cost latency, acts cost
1 s, observe/health are free. No network is used.
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
from dfbench_client import ModelError  # noqa: E402
from plain import harness  # noqa: E402
from test_wall_finale import Clock, WallGame, LatencyModel  # noqa: E402

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class MeltModel(LatencyModel):
    """Fails every call for the first `melt` calls (costing latency each time,
    like a timeout), then answers normally."""

    def __init__(self, clock, latency=50.0, melt=10 ** 9):
        super().__init__(clock, latency)
        self.melt = melt

    def chat(self, messages, **params):
        self.clock.spend(self.latency)
        self.calls += 1
        if self.calls <= self.melt:
            raise ModelError("gateway unreachable: timed out")
        return super(LatencyModel, self).chat(messages, **params)


def run_melt(horizon, wall_s, latency, melt, quiet=True, safe_days=1, turns=500):
    clock = Clock()
    game = WallGame(clock, horizon, wall_s)
    model = MeltModel(clock, latency, melt)
    runner = harness.Plain(SimpleNamespace(task={"days": horizon}, days=horizon,
                                           credits=None), game, model)
    with patch.object(runner.guard, "step", return_value=0), \
            patch.object(runner.guard, "quiet", return_value=quiet), \
            patch.object(runner.guard, "safe_days", return_value=safe_days), \
            redirect_stdout(io.StringIO()):
        with patch.object(harness.time, "monotonic", clock.monotonic):
            runner.run(max_turns=turns)
    return runner, game, model, clock


class GatewayMelt(unittest.TestCase):
    def test_melt_then_recovery_continues_and_uses_the_model(self):
        # 4 timeouts on a quiet fort: creep forward, stay alive, and once the
        # gateway answers, normal control resumes (the answer's action runs).
        runner, game, model, clock = run_melt(60, None, 10.0, melt=4)
        self.assertNotEqual(runner.stop_reason, "model_failing")
        self.assertGreater(model.calls, 4)                  # probed past the melt
        self.assertGreater(runner.stats["recover_days"], 0)  # crept while it was down
        self.assertEqual(runner.recover_streak, 0)           # recovery reset the streak
        # after recovery the model's tool call ran: an action after call 5 exists
        self.assertGreater(len(game.actions), 0)
        self.assertGreater(runner.stats["actions"] + runner.stats["advances"], 0)

    def test_unsafe_fort_still_gives_up_at_the_old_streak(self):
        # guard says NOT quiet: the model's judgement is needed; the old
        # MAX_API_STREAK give-up must still fire, with no recovery advances.
        runner, game, model, clock = run_melt(60, None, 10.0, melt=10 ** 9,
                                              quiet=False)
        self.assertEqual(runner.stop_reason, "model_failing")
        self.assertEqual(runner.stats["recover_days"], 0)
        self.assertEqual(model.calls, harness.MAX_API_STREAK)

    def test_wall_gate_beats_resilience_during_an_endless_melt(self):
        # quiet fort, melt never ends: recovery creep must stop at the measured
        # wall budget, exactly like a model call would.
        runner, game, model, clock = run_melt(216, 300, 50.0, melt=10 ** 9,
                                              quiet=True, safe_days=1)
        self.assertEqual(runner.stop_reason, "wall_budget")
        self.assertGreater(runner.stats["recover_days"], 0)      # it did creep
        self.assertLess(clock.t, 300.0)                          # never past the cap
        # every accepted probe call started while left > estimate + margin; the
        # estimate came from this run's own melt latencies (50 s), not the default.
        self.assertEqual(runner.call_estimate(), 50.0)

    def test_recovery_is_bounded_by_recover_max(self):
        # endless melt on a quiet fort: after RECOVER_MAX recovery days the run
        # gives up rather than skipping the model for the whole game.
        runner, game, model, clock = run_melt(10 ** 6 // 1, 10 ** 9, 1.0,
                                              melt=10 ** 9, quiet=True,
                                              safe_days=1, turns=10 ** 5)
        self.assertEqual(runner.stop_reason, "model_failing")
        self.assertLessEqual(runner.stats["recover_days"], harness.RECOVER_MAX)

    def test_recovery_advances_one_day_even_when_guard_offers_more(self):
        # safe_days() may offer a 14-day blind skip; recovery must still creep
        # ONE day per turn, so RECOVER_MAX bounds elapsed no-model days too
        # (reports/recovery-semantics.md finding b/c).
        import json
        buf = io.StringIO()
        clock = Clock()
        game = WallGame(clock, 216, 10 ** 9)
        model = MeltModel(clock, 1.0, melt=6)
        runner = harness.Plain(SimpleNamespace(task={"days": 216}, days=216,
                                               credits=None), game, model)
        with patch.object(runner.guard, "step", return_value=0), \
                patch.object(runner.guard, "quiet", return_value=True), \
                patch.object(runner.guard, "safe_days", return_value=14), \
                redirect_stdout(buf):
            with patch.object(harness.time, "monotonic", clock.monotonic):
                runner.run(max_turns=500)
        rec = [json.loads(l) for l in buf.getvalue().splitlines()
               if '"recover_advance"' in l]
        self.assertTrue(rec, "melt of 6 must trigger recovery turns")
        self.assertEqual({r["days"] for r in rec}, {1},
                         "recovery must request exactly one day per turn")


if __name__ == "__main__":
    unittest.main()
