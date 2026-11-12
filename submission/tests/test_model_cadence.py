"""cx model cadence and the model's digs (hint OP1-2, never finished 336 days).

Measured on the hint OP1-2 runs (game/harness-2.api.jsonl, gateway/usage.jsonl):
  cxc44c96b hard: 8512 s for 88 days; advance_days 2.5-2.8 s a day all run (the game is not slow); 106 model calls,
    6855 s upstream (65 s a call, later 80-140 s), 1217 s throttle; 95% of the wall in the model.
  full2 std attempt 0: day 214 when the clock ran out (105 calls, 8357 s upstream).
The server counts the model's response time against the cap; only the gateway's reported throttle is excluded
(gameapi/server/rules.py wall_used). The old pace guard subtracted every model second and never fired.

The model's dig: cxc44c96b, the model's dig_room R1 (100,94,z162) on day 2 under the open river rows (y89-94 at
z162, RIVER material, depth-7 liquid, one level under the z163 surface); deep water stood indoors from day 3."""
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
from overseer.harness import Overseer  # noqa: E402

DAY = 1200


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeGame:
    """advance_days costs `per_day` wall seconds a game day on the shared clock (2.5 s measured)."""

    def __init__(self, clock, days=336, per_day=2.5):
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


class SlowModel:
    """`per_call` wall seconds a call; one action, then advance_days `adv` days every `every` calls (the measured
    OP1-2 shape: ~3 calls a model advance of 2-3 days). gateway_status reports `throttle` seconds."""

    def __init__(self, clock, per_call=80.0, adv=2, every=3, throttle=0.0):
        self.clock, self.per_call, self.adv, self.every, self.throttle = clock, per_call, adv, every, throttle
        self.calls = 0
        self.usage = {"cost_usd": 0, "rate_limit_wait_s": 0.0}
        self.status_reads = 0

    def gateway_status(self):
        self.status_reads += 1
        return {"throttle_wait_total_s": self.throttle}

    def chat(self, messages, **params):
        self.calls += 1
        self.clock.t += self.per_call
        if self.calls % self.every == 0:
            fn = {"name": "advance_days", "arguments": json.dumps({"days": self.adv})}
        else:
            fn = {"name": "enable_automation", "arguments": json.dumps({"name": "autochop"})}
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [
            {"id": str(self.calls), "type": "function", "function": fn}]}}]}


def build(wall_s=13500, days=336, **kw):
    clock = Clock()
    game, model = FakeGame(clock, days), SlowModel(clock, **kw)
    with patch.object(harness.time, "monotonic", clock):
        r = harness.Plain(SimpleNamespace(task={"days": days}, days=days, credits=None, wall_s=wall_s), game, model)
    return r, game, model, clock


def play(r, clock):
    with patch.object(harness.time, "monotonic", clock), redirect_stdout(io.StringIO()) as out, \
            patch.object(r, "chunked", lambda args: r.game.act("advance_days", args)):
        r.run()
    return out.getvalue()


class WallCounting(unittest.TestCase):
    def test_the_model_time_counts_and_only_the_reported_throttle_is_left_out(self):
        r, game, model, clock = build(throttle=300.0)
        with patch.object(harness.time, "monotonic", clock):
            clock.t += 1000.0
            r.model_wait = 900.0
            self.assertAlmostEqual(r.wall_used(), 700.0)       # 1000 elapsed − 300 throttle (gateway /status)
            self.assertAlmostEqual(r.wall_left(), 12800.0)
            model.throttle = 5000.0                            # never more than the model wait itself
            r.gw_read = None
            self.assertAlmostEqual(r.wall_used(), 100.0)

    def test_the_gateway_is_read_at_most_every_two_minutes(self):
        r, game, model, clock = build()
        with patch.object(harness.time, "monotonic", clock):
            r.wall_left()
            r.wall_left()
            clock.t += 30
            r.wall_left()
            self.assertEqual(model.status_reads, 1)
            clock.t += harness.WALL_GATEWAY_EVERY_S
            r.wall_left()
            self.assertEqual(model.status_reads, 2)

    def test_a_gateway_without_status_is_asked_three_times_only(self):
        r, game, model, clock = build()
        model.gateway_status = lambda: None
        with patch.object(harness.time, "monotonic", clock), redirect_stdout(io.StringIO()):
            for _ in range(10):
                clock.t += harness.WALL_GATEWAY_EVERY_S
                r.wall_left()
        self.assertEqual(r.gw_fails, harness.WALL_GATEWAY_FAILS)

    def test_a_model_without_gateway_status_counts_everything(self):
        r, game, model, clock = build()
        r.model = SimpleNamespace(usage={"cost_usd": 0})
        with patch.object(harness.time, "monotonic", clock):
            clock.t += 500
            r.model_wait = 400
            self.assertAlmostEqual(r.wall_used(), 500.0)


class ModelShare(unittest.TestCase):
    def test_the_measured_op1_2_pace_does_not_fit_and_thins_the_model(self):
        # cxc44c96b at day 10: ~12 calls x 60 s, the layer and the API ~5 s a game day
        r, game, model, clock = build()
        with patch.object(harness.time, "monotonic", clock):
            clock.t += 770
            r.day0, r.model_wait, r.model_days, r.model_calls = 0, 720.0, 10, 12
            share = r.model_share({"day": 10, "days_left": 326})
            self.assertGreater(share, 0.2)
            self.assertLess(share, 0.7)

    def test_a_fast_model_keeps_every_turn(self):
        r, game, model, clock = build()
        with patch.object(harness.time, "monotonic", clock):
            clock.t += 120
            r.day0, r.model_wait, r.model_days, r.model_calls = 0, 60.0, 10, 12   # 6 s a day of model
            self.assertEqual(r.model_share({"day": 10, "days_left": 326}), 1.0)

    def test_too_little_measured_trusts_the_model(self):
        r, game, model, clock = build()
        with patch.object(harness.time, "monotonic", clock):
            clock.t += 600
            r.day0, r.model_wait, r.model_days, r.model_calls = 0, 590.0, 3, 8
            self.assertEqual(r.model_share({"day": 3, "days_left": 333}), 1.0)


class FullYear(unittest.TestCase):
    def test_the_op1_2_shape_plays_all_336_days_inside_the_cap(self):
        # 80 s a call, 3 calls a 2-day model advance: 120 s a game day, 40320 s for the year at the model's pace
        r, game, model, clock = build(per_call=80.0, adv=2, every=3)
        out = play(r, clock)
        self.assertEqual(game.day, 336)
        with patch.object(harness.time, "monotonic", clock):
            self.assertLess(r.wall_used(), 13500)
        self.assertIn("model_hold", out)
        self.assertGreater(model.calls, 60)                    # the model kept playing all year, thinned
        self.assertGreater(r.model_days, 40)
        holds = [a["days"] for n, a in game.actions if n == "advance_days"]
        self.assertLessEqual(max(holds), harness.MAX_DAYS)

    def test_a_slower_model_late_in_the_run_still_finishes(self):
        r, game, model, clock = build(per_call=60.0, adv=3, every=3)
        orig = model.chat

        def chat(messages, **params):
            if game.day > 100:
                model.per_call = 140.0   # the prompt grows, the calls slow (cxc44c96b: 65 s → 140 s)
            return orig(messages, **params)
        model.chat = chat
        play(r, clock)
        self.assertEqual(game.day, 336)
        with patch.object(harness.time, "monotonic", clock):
            self.assertLess(r.wall_used(), 13500)

    def test_a_fast_model_is_never_held(self):
        r, game, model, clock = build(per_call=3.0, adv=2, every=3)
        out = play(r, clock)
        self.assertEqual(game.day, 336)
        self.assertNotIn("model_hold", out)

    def test_the_old_accounting_would_have_run_past_the_cap(self):
        # the model share off and the model seconds left out of the clock (the pre-fix pace guard): 3x the cap
        r, game, model, clock = build(per_call=80.0)
        r.model_share = lambda resp: 1.0
        r.wall_left = lambda: r.wall_s - (clock.t - r.t0 - r.model_wait)
        r.hard_left = lambda: None   # and no hard clock (test_hard_clock: it alone stops this inside the backstop)
        play(r, clock)
        self.assertGreater(clock.t - r.t0, 3 * 13500)

    def test_the_counted_clock_alone_hands_the_run_to_the_layer_in_time(self):
        # without the model share, the corrected clock still hands the rest to the layer before the cap
        # (the model then plays no more: the share keeps it playing all year instead)
        r, game, model, clock = build(per_call=80.0)
        r.model_share = lambda resp: 1.0
        out = play(r, clock)
        self.assertEqual(game.day, 336)
        self.assertIn('"layer_only"', out)   # the reserve (or pace) guard took the rest without the model
        self.assertLess(clock.t - r.t0, 13500)

    def test_no_hold_into_a_close_hands_off_window(self):
        r, game, model, clock = build(per_call=80.0)
        r.hold_left = 10.0
        orig = game.observe

        def observe():
            resp = orig()
            resp["hands_off_in_days"] = 3
            return resp
        game.observe = observe
        with patch.object(harness.time, "monotonic", clock), redirect_stdout(io.StringIO()), \
                patch.object(r, "chunked", lambda args: r.game.act("advance_days", args)):
            r.run(max_turns=1)
        self.assertEqual(model.calls, 1)
        self.assertEqual(r.hold_left, 0.0)

    def test_the_reported_throttle_buys_the_model_more_turns(self):
        a, ga, ma, ca = build(per_call=80.0)
        play(a, ca)
        b, gb, mb, cb = build(per_call=80.0)
        mb.throttle = 4000.0
        play(b, cb)
        self.assertEqual(gb.day, 336)
        self.assertGreater(mb.calls, ma.calls)


# ---- the model's digs pass the layer's water rules (cxc44c96b hard OP1-2: the river one level under the surface)
SURFACE = 163
RIVER = {(x, y) for y in range(89, 94) for x in range(88, 113)} | {(x, 94) for x in range(88, 97)}
R1 = {"id": "R1", "kind": "R", "x": 100, "y": 94, "z": 162, "w": 3, "h": 3, "soil": True, "free": True}
R3 = {"id": "R3", "kind": "R", "x": 96, "y": 98, "z": 162, "w": 3, "h": 3, "soil": True, "free": True}
S4 = {"id": "S4", "kind": "S", "x": 99, "y": 95, "z": SURFACE, "w": 1, "h": 1}


class RiverGame:
    """/query/map over the recorded river: RIVER material letters and depth-7 liquid at z162, soil elsewhere."""

    def __init__(self):
        self.actions, self.queries = [], []

    def env(self):
        return {"day": 2, "tick": 2 * DAY, "days_left": 334, "game_over": False}

    def act(self, tool, args=None):
        self.actions.append((tool, dict(args or {})))
        return {**self.env(), "ok": True, "result": {}}

    def events(self, since_tick=0):
        return {**self.env(), "events": [], "dropped": 0, "now": 0}

    def query(self, name, **p):
        self.queries.append((name, p))
        z, z2, r = p["z"], p.get("z2", p["z"]), p.get("radius", 12)
        x1, x2, y1, y2 = p["x"] - r, p["x"] + r, p["y"] - r, p["y"] + r
        levels, liquid = [], []
        for zz in range(z, z2 - 1, -1):
            rows = []
            for y in range(y1, y2 + 1):
                rows.append("".join("R" if zz == 162 and (x, y) in RIVER else "s" for x in range(x1, x2 + 1)))
                liquid += [{"x": x, "y": y, "z": zz, "depth": 7} for x in range(x1, x2 + 1)
                           if zz == 162 and (x, y) in RIVER]
            levels.append({"z": zz, "material": rows, "shape": [], "light": []})
        return {**self.env(), "query": "map", "result": {"ok": True, "x1": x1, "x2": x2, "y1": y1, "y2": y2,
                                                          "levels": levels, "liquid": liquid, "buildings": [],
                                                          "designations": []}}


def river_guard(sites=(R1, R3, S4)):
    ov = Overseer(RiverGame())
    o = {"date": {"abs_tick": 2 * DAY}, "map": {"surface_z": SURFACE, "sites": [dict(s) for s in sites]},
         "recent_events": [], "recent_cancellations": [], "dig_designations_pending": 0,
         "dwarves": [{"id": i} for i in range(7)]}
    with redirect_stdout(io.StringIO()):
        ov.load({"day": 2, "tick": 2 * DAY, "days_left": 334, "game_over": False, "observation": o})
    return ov


class ModelDigWater(unittest.TestCase):
    def test_the_model_dig_under_the_river_is_refused(self):
        ov = river_guard()
        with redirect_stdout(io.StringIO()):
            why = ov.dig_refusal("dig_room", {"site": "R1"})
        self.assertTrue(why)
        self.assertIn("water", why)

    def test_a_dry_site_off_the_river_digs(self):
        ov = river_guard()
        with redirect_stdout(io.StringIO()):
            self.assertIsNone(ov.dig_refusal("dig_room", {"site": "R3"}))
            self.assertIsNone(ov.dig_refusal("dig_room", {"site": "R9"}))   # unknown site: fail open
            self.assertIsNone(ov.dig_refusal("build_farm", {"site": "R1"}))

    def test_no_model_dig_over_a_contained_breach(self):
        ov = river_guard()
        ov.breach = {"day": 37, "z": 162, "cause": "water_rising_after_dig"}
        with redirect_stdout(io.StringIO()):
            self.assertIn("breach", ov.dig_refusal("dig_room", {"site": "R3"}))

    def test_the_plain_loop_refuses_it_locally(self):
        clock = Clock()
        game, model = FakeGame(clock), SlowModel(clock)
        r = harness.Plain(SimpleNamespace(task={"days": 336}, days=336, credits=None, wall_s=None), game, model)
        r.guard = river_guard()
        with redirect_stdout(io.StringIO()):
            out = r.refuse("dig_room", {"site": "R1"}, 2 * DAY)
            self.assertEqual(out["error_code"], "water_risk")
            self.assertIsNone(r.refuse("dig_room", {"site": "R3"}, 2 * DAY))


if __name__ == "__main__":
    unittest.main()
