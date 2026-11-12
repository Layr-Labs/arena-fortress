"""cx hard clock: the runner's backstop is real time (hint hard LT02-2 never finished).

Measured on the three hint hard LT02-2 runs (cxba93eee attempt 0 and retry, cxe33d381 attempt 0; harness
output.log, game.json ledger):
  all three ended "infra (runner_deadline)" at 8172-8195 s (deadline = wall_s 4500 + finish_grace_s 3600 from the
  harness start, runner/dfbenchlib/game.py), at game day 62-63 of 90; no score.
  13-15 model calls per run ended in HTTP 502 "glm upstream: TimeoutError" after ~306 s each; the client retries a
  5xx 4 times, so one turn cost 1531-1534 s (cxe33d381 day 60: 1533 s, then raised; day 62: hung 1700 s into the
  deadline). Concurrent MY1/OP1/LT08 games on the same relay had 0 such errors.
  The gateway excludes that time (throttle_wait_s 4993-5295 s): the server's clock showed 3115 s used of 4500 and
  the harness's model_hold logged left_s 1728 at day 61, while 1695 real seconds were left before the backstop.
  Not the game: advance_days 1-2 days ran 3-5 s, no repeated tripwire (water_rising once), 0 interruptions.
The fix: a model call may only spend the real time left after the layer's own pace to the horizon (attempts and
per-attempt timeout cut to fit); under one attempt the layer plays alone; the model share also reads the real
clock. No network: the shared fake clock of tests/test_model_cadence.py."""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from plain import harness  # noqa: E402
from dfbench_client import ModelError  # noqa: E402

DAY = 1200
WALL = 4500.0
BACKSTOP = WALL + harness.RUNNER_GRACE_S


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeGame:
    """advance_days costs `per_day` wall seconds a game day (LT02-2: 1 day 3-5 s)."""

    def __init__(self, clock, days=90, per_day=3.0):
        self.clock, self.days, self.per_day = clock, days, per_day
        self.day = 0
        self.actions = []
        self.last = {"tick": 0}

    def task(self):
        return {"task": {"days": self.days}, "tools": [
            {"type": "function", "function": {"name": "enable_automation", "parameters": {
                "type": "object", "properties": {"name": {"type": "string"}}}}},
            {"type": "function", "function": {"name": "advance_days", "parameters": {
                "type": "object", "properties": {"days": {"type": "integer", "maximum": 28}}}}}]}

    def envelope(self):
        return {"day": self.day, "tick": self.day * DAY, "days_left": max(0, self.days - self.day),
                "game_over": self.day >= self.days}

    def observe(self):
        self.clock.t += 0.5
        self.last = self.envelope()
        return {**self.last, "observation": {"date": {"abs_tick": self.last["tick"]}, "dig_designations_pending": 0}}

    def act(self, name, args):
        self.actions.append((name, dict(args)))
        if name == "advance_days":
            n = min(args["days"], self.days - self.day)
            self.clock.t += self.per_day * n
            self.day += n
        self.last = self.envelope()
        return {**self.last, "ok": True, "result": {"advanced_days": args.get("days")}}

    def query(self, name, **p):
        return {**self.envelope(), "query": name, "result": {}}

    def events(self, since_tick=0):
        return {**self.envelope(), "events": [], "dropped": 0, "now": 0}


class RelayModel:
    """The dfbench_client ModelClient's retry shape against the LT02-2 relay: an answered call costs `per_call` s;
    from day `hang_from` every `hang_every`-th call hangs — each attempt min(timeout, 306) s, then the client sleeps
    min(2 s x n, 20) and retries, max_retries times, then raises ModelError (HTTP 502). The hung seconds are the
    gateway's reported throttle (gateway_status)."""

    def __init__(self, clock, game, per_call=86.0, hang_from=20, hang_every=3, hang_s=306.0, adv=2, every=3):
        self.clock, self.game = clock, game
        self.per_call, self.hang_from, self.hang_every, self.hang_s = per_call, hang_from, hang_every, hang_s
        self.adv, self.every = adv, every
        self.max_retries, self.timeout = 4, 600.0
        self.calls = self.hung = self.attempts = 0
        self.throttle = 0.0
        self.usage = {"cost_usd": 0, "rate_limit_wait_s": 0.0}
        self.seen = []   # (max_retries, timeout) per call

    def gateway_status(self):
        return {"throttle_wait_total_s": self.throttle}

    def chat(self, messages, **params):
        self.calls += 1
        self.seen.append((self.max_retries, self.timeout))
        if self.game.day >= self.hang_from and self.calls % self.hang_every == 0:
            self.hung += 1
            for n in range(self.max_retries + 1):
                self.attempts += 1
                wait = min(self.timeout, self.hang_s)
                self.clock.t += wait
                self.throttle += wait
                if n < self.max_retries:
                    self.clock.t += min(2.0 * (n + 1), 20.0)
            raise ModelError('HTTP 502: {"error": {"message": "glm upstream: TimeoutError"}}', 502, "")
        self.attempts += 1
        self.clock.t += self.per_call
        if self.calls % self.every == 0 or self.calls % self.every == 1:
            fn = {"name": "advance_days", "arguments": json.dumps({"days": self.adv})}
        else:
            fn = {"name": "enable_automation", "arguments": json.dumps({"name": "autochop"})}
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [
            {"id": str(self.calls), "type": "function", "function": fn}]}}]}


def build(days=90, wall_s=WALL, **kw):
    clock = Clock()
    game = FakeGame(clock, days)
    model = RelayModel(clock, game, **kw)
    with patch.object(harness.time, "monotonic", clock):
        r = harness.Plain(SimpleNamespace(task={"days": days}, days=days, credits=None, wall_s=wall_s), game, model)
    r.messages, r.tools = [{"role": "system", "content": ""}], []   # run() sets them up again (setup)
    return r, game, model, clock


def play(r, clock):
    with patch.object(harness.time, "monotonic", clock), redirect_stdout(io.StringIO()) as out, \
            patch.object(r, "chunked", lambda args: r.game.act("advance_days", args)):
        r.run()
    return out.getvalue()


class Lt02Shape(unittest.TestCase):
    def test_hung_relay_calls_run_past_the_runner_backstop_without_the_hard_clock(self):
        # the pre-fix harness: the server's clock (throttle excluded) said there was time; the real clock ran out
        r, game, model, clock = build()
        r.hard_left = lambda: None
        play(r, clock)
        self.assertGreater(clock.t - r.t0, BACKSTOP)
        with patch.object(harness.time, "monotonic", clock):
            self.assertLess(r.wall_used(), WALL)   # the counted clock never hit the cap: no wall guard fired

    def test_the_hard_clock_finishes_all_days_inside_the_backstop(self):
        r, game, model, clock = build()
        out = play(r, clock)
        self.assertEqual(game.day, 90)
        self.assertLess(clock.t - r.t0, BACKSTOP - harness.HARD_SLACK_S + harness.MODEL_RETRY_SLEEP_S * 5)
        self.assertGreater(model.hung, 0)         # the relay did hang, and the model still played
        self.assertGreater(model.calls - model.hung, 10)
        self.assertIn('"model_bound"', out)                   # the late calls were cut to the real time left
        self.assertIn('"model_hold"', out)                    # and the model thinned on the real clock

    def test_a_relay_that_hangs_every_call_hands_the_rest_to_the_layer(self):
        r, game, model, clock = build(hang_from=10, hang_every=1)
        out = play(r, clock)
        self.assertEqual(game.day, 90)
        self.assertLess(clock.t - r.t0, BACKSTOP - harness.HARD_SLACK_S + harness.MODEL_RETRY_SLEEP_S * 5)
        self.assertIn('"model_bound"', out)
        self.assertIn('"layer_only"', out)

    def test_a_healthy_relay_is_untouched(self):
        # no hang, no throttle: the hard clock is 3300 s past the counted one and never binds; the counted clock
        # (wall_left) cuts the late calls' retries/timeout to what it has left, never below one full attempt
        # (MODEL_TRY_S), and every call is answered
        r, game, model, clock = build(hang_from=10 ** 6)
        out = play(r, clock)
        self.assertEqual(game.day, 90)
        self.assertNotIn('"phase": "hard"', out)
        self.assertEqual(model.seen[0], (4, 600.0))
        self.assertTrue(all(t >= harness.MODEL_TRY_S for _, t in model.seen))
        self.assertEqual(model.hung, 0)
        with patch.object(harness.time, "monotonic", clock):
            self.assertLess(r.wall_used(), WALL)


class BoundedChat(unittest.TestCase):
    def test_attempts_and_timeout_fit_the_budget_and_come_back(self):
        r, game, model, clock = build()
        model.hang_from, model.hang_every = 0, 1
        with patch.object(harness.time, "monotonic", clock), redirect_stdout(io.StringIO()):
            r.last_look = {"day": 60, "days_left": 30}
            r.day0 = 0
            clock.t = r.t0 + 6400.0   # cxe33d381 day 61: 6405 s real
            r.model_wait = 6139.7
            model.throttle = 3632.0   # the gateway excluded 3632 s: the counted clock (1732 s left) does not bind
            budget = r.model_budget(r.last_look)
            # 8100 − 300 − 6400 = 1400 real; the layer needs 30 days x max(7 s, 260/60 s) = 210
            self.assertAlmostEqual(budget, 1400.0 - 210.0, places=3)
            t = clock.t
            with self.assertRaises(ModelError):
                r.bounded_chat({})
            self.assertEqual(model.seen[-1][0], 2)               # 3 attempts of 350 s fit 1190 s, not 5
            self.assertLessEqual(clock.t - t, budget)
            self.assertEqual((model.max_retries, model.timeout), (4, 600.0))   # the client's own settings back

    def test_the_timeout_is_cut_when_one_attempt_is_all_that_fits(self):
        r, game, model, clock = build()
        with patch.object(harness.time, "monotonic", clock), redirect_stdout(io.StringIO()):
            r.last_look = {"day": 80, "days_left": 10}
            r.model_wait = model.throttle = 5000.0   # LT02-2: the counted clock shows ~2300 s and does not bind
            clock.t = r.t0 + harness.RUNNER_GRACE_S + WALL - harness.HARD_SLACK_S - 70.0 - 420.0
            r.bounded_chat({})
            retries, timeout = model.seen[-1]
            self.assertEqual(retries, 0)
            self.assertAlmostEqual(timeout, 400.0)              # 420 s budget − the retry sleep

    def test_no_wall_limit_calls_the_client_as_is(self):
        r, game, model, clock = build(wall_s=None)
        with patch.object(harness.time, "monotonic", clock):
            r.bounded_chat({})
        self.assertEqual(model.seen, [(4, 600.0)])


class HardShare(unittest.TestCase):
    def test_excluded_throttle_no_longer_reads_as_a_free_model(self):
        # cxe33d381 day 61: model_wait 6139.7 s, the gateway excluded 3632 s; real elapsed 6405 s, 28 days left
        r, game, model, clock = build()
        model.throttle = 6139.7   # everything excluded: the counted clock alone would give the model share 1.0
        with patch.object(harness.time, "monotonic", clock):
            clock.t = r.t0 + 6405.0
            r.day0, r.model_wait, r.model_days, r.model_calls = 0, 6139.7, 38, 40
            share = r.model_share({"day": 61, "days_left": 28})
            self.assertLess(share, 0.3)
            r.hard_left = lambda: None
            self.assertEqual(r.model_share({"day": 61, "days_left": 28}), 1.0)


class HardGuard(unittest.TestCase):
    def test_under_one_attempt_the_layer_plays_the_rest_alone(self):
        r, game, model, clock = build()
        game.day = 62
        with patch.object(harness.time, "monotonic", clock):
            clock.t = r.t0 + 7300.0   # 8100 − 300 − 7300 = 500 real s; the layer needs 28 x 7 = 196: 304 < 350
            r.model_wait = model.throttle = 5000.0   # the gateway excluded it all: the counted clock shows 2300 s
            self.assertTrue(r.hard_low({"day": 62, "days_left": 28}))
            self.assertFalse(r.hard_low({"day": 62, "days_left": 1}))   # 497 s: one attempt still fits
            self.assertFalse(r.wall_low())
        out = play(r, clock)
        self.assertEqual(model.calls, 0)
        self.assertEqual(game.day, 90)
        self.assertIn('"phase": "hard"', out)
        self.assertIn('"reason": "hard_clock"', out)
        self.assertLess(clock.t - r.t0, BACKSTOP)
        strides = [a["days"] for n, a in game.actions if n == "advance_days"]
        self.assertIn(harness.WALL_STEP_DAYS, strides)   # the wall-pace stride, not a day at a time


class UnreportedRelay(RelayModel):
    """A slow relay whose hung seconds the gateway does NOT report as throttle (hint hard LT02-1 on 5c14f02:
    throttle_wait_s 0.0, 142.9 s a call): every model second counts on the server's wall clock."""

    def gateway_status(self):
        return {"throttle_wait_total_s": 0.0}


class CountedClock(unittest.TestCase):
    """Hint hard LT02-1 on 5c14f02 (score 17.0, partial 0.15): end_reason wall_cap, wall_used_s 4500.8, days 63 of 90.
    The harness log stops at day 63 (model_hold ended, wall left ~1270 s, 27 days to play, hands_off_in_days 6);
    the next model call went out with the client's own 4 retries x 600 s (the hard clock had ~4400 s) and ran into
    the server's cap. LT02's window W is days 70..H: with H = 63 it is empty, so drink and food fractions read 0/1
    and the plot (cave wheat, summer/autumn only, not sowable before run day 66) was never sown."""

    def run_lt02_1(self, old):
        clock = Clock()
        game = FakeGame(clock, 90, per_day=4.0)
        model = UnreportedRelay(clock, game, per_call=142.0, hang_from=60, hang_every=4, hang_s=600.0)
        with patch.object(harness.time, "monotonic", clock):
            r = harness.Plain(SimpleNamespace(task={"days": 90}, days=90, credits=None, wall_s=WALL), game, model)
        r.messages, r.tools = [{"role": "system", "content": ""}], []
        if old:   # the pre-fix budget: the runner's real clock only
            r.model_budget = lambda resp: r.hard_left() - r.layer_need(resp)
        out = play(r, clock)
        with patch.object(harness.time, "monotonic", clock):
            return r, game, model, r.wall_used(), out

    def test_hard_clock_alone_lets_a_late_call_run_into_the_server_cap(self):
        r, game, model, used, out = self.run_lt02_1(old=True)
        self.assertEqual(model.hung, 1)
        self.assertGreater(used, WALL)   # the server would have ended the game at its cap, before the horizon
        self.assertNotIn('"model_bound"', out)

    def test_the_counted_clock_bounds_the_call_and_the_layer_reaches_the_horizon(self):
        r, game, model, used, out = self.run_lt02_1(old=False)
        self.assertEqual(model.hung, 1)  # the relay still hung, at the same call
        self.assertEqual(game.day, 90)
        self.assertLessEqual(used, WALL)
        self.assertIn('"model_bound"', out)
        self.assertTrue(all(t >= harness.MODEL_TRY_S for _, t in model.seen))
        self.assertGreater(model.calls - model.hung, 10)   # the model still played

    def test_budget_reads_the_smaller_clock(self):
        r, game, model, clock = build()
        with patch.object(harness.time, "monotonic", clock), redirect_stdout(io.StringIO()):
            r.day0 = 0
            clock.t = r.t0 + 3230.0          # 5c14f02 day 63: ~3230 s real, throttle 0
            r.model_wait = 3000.0
            look = {"day": 63, "days_left": 27}
            # wall_left 1270, hard_left 4570: the counted clock binds; the layer needs 27 x 7 = 189
            self.assertAlmostEqual(r.model_budget(look), 1270.0 - 189.0, places=3)
            r.last_look = look
            model.hang_from, model.hang_every = 0, 1
            t = clock.t
            with self.assertRaises(ModelError):
                r.bounded_chat({})
            self.assertEqual(model.seen[-1][0], 2)        # 3 attempts of ~340 s, not 5 of 600 s
            self.assertLessEqual(clock.t - t, 1270.0 - 189.0)
            self.assertEqual((model.max_retries, model.timeout), (4, 600.0))


if __name__ == "__main__":
    unittest.main()
