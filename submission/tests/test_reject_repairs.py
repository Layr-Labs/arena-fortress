"""Regressions for the measured rejection waste (REJECT_ANALYSIS.md): a full dining floor knocked day after day, a
farm site that keeps answering site_used, the model's identical same-day retries, and housing advice pointing at a
floor that just answered no_space. No game or network is used."""
import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness
from plain import harness as plain_harness
from plain import digest

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__
assert Path(digest.__file__).is_relative_to(VARIANT), digest.__file__


def site(id="A1", x=10, y=10, z=9, w=7, h=6, open_tiles=32, **kw):
    return {"id": id, "kind": id[0], "x": x, "y": y, "z": z, "w": w, "h": h,
            "open_tiles": open_tiles, **kw}


def facts(sites=(), cit=7, free=None, stocks=None, furniture=(), plots=(), day=0):
    return {"tick": day * harness.DAY, "observation": {
        "administrators": {"citizens": cit},
        "stocks": {"furniture_free": free or {}, **(stocks or {})},
        "map": {"sites": copy.deepcopy(list(sites))},
        "zones": [], "furniture": list(furniture), "farm_plots": list(plots)}}


class FakeGame:
    """place_furniture fails with no_space on the sites in `fail`; build_farm fails with site_used when set."""

    def __init__(self):
        self.calls = []
        self.fail = set()
        self.used = set()

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if tool == "place_furniture":
            if args["site"] in self.fail:
                return {"ok": False, "error_code": "no_space",
                        "error": "no free floor tile: every tile is wall, undug, built on or designated"}
        if tool == "build_farm":
            if args["site"] in self.used:
                return {"ok": False, "error_code": "site_used", "error": "room R1 is already used (farm plot 12)"}
        return {"ok": True, "result": {"n": args.get("count", 1), "at": [21, 11, 9]}}


class SeatOverflow(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, sites, **kw):
        game = FakeGame()
        ov = harness.Overseer(game)
        ov.load(facts(sites=sites, **kw))
        ov.count = 0
        return ov, game

    def test_full_dining_floor_diverts_the_pair_to_one_other_floor(self):
        sites = [site("A1"), site("A2", x=20, open_tiles=12)]
        ov, game = self.overseer(sites, free={"table": 4, "chair": 4})
        game.fail.add("A1")
        ov.furnish()
        self.assertEqual([(t, a["site"], a["kind"]) for t, a, in game.calls], [
            ("place_furniture", "A1", "table"), ("place_furniture", "A1", "chair"),
            ("place_furniture", "A2", "table"), ("place_furniture", "A2", "chair"),
            ("make_zone", "A2", "dining_hall")])   # both kinds share the overflow floor, and it is zoned
        self.assertIn(("table", "A1"), ov.seat_block)   # the refusing primary floor stays blocked while unchanged
        self.assertNotIn(("table", "A2"), ov.seat_block)   # the overflow floor took the pair

    def test_blocked_floor_is_not_knocked_again_until_it_changes(self):
        ov, game = self.overseer([site("A1")], free={"table": 4, "chair": 4}, day=0)
        game.fail.add("A1")
        ov.furnish()                       # A1 fails and no other floor exists: the blocks are recorded
        self.assertIn(("table", "A1"), ov.seat_block)
        game.calls.clear()
        ov.load(facts(sites=[site("A1")], free={"table": 4, "chair": 4}, day=1))
        ov.count = 0
        ov.furnish()
        self.assertEqual(game.calls, [])   # the same full floor is not knocked again the next day
        ov.load(facts(sites=[site("A1", open_tiles=40)], free={"table": 4, "chair": 4}, day=2))
        ov.count = 0
        ov.furnish()
        self.assertEqual([t for t, _ in game.calls], ["place_furniture"] * 2)   # a changed floor is tried again

    def test_dorm_beds_are_untouched_by_the_seat_block(self):
        ov, game = self.overseer([site("A1")], free={"bed": 5}, day=0)
        game.fail.add("A1")
        ov.furnish()
        game.calls.clear()
        ov.load(facts(sites=[site("A1")], free={"bed": 5}, day=1))
        ov.count = 0
        ov.furnish()
        self.assertEqual([t for t, _ in game.calls], ["place_furniture"])   # beds keep their own retry flow


class FarmSites(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, sites, plots=(), **kw):
        game = FakeGame()
        ov = harness.Overseer(game)
        ov.load(facts(sites=sites, plots=plots, **kw))
        ov.count = 0
        return ov, game

    def test_room_already_holding_a_plot_is_skipped(self):
        room = site("R1", w=5, h=5, dug=True, soil=True)
        spare = site("R2", x=30, w=5, h=5, dug=True, soil=True)
        plot = {"id": 4, "x": 10, "y": 10, "z": 9, "w": 3, "h": 3, "built": True}
        ov, game = self.overseer([room, spare], plots=[plot])
        ov.farms()
        self.assertEqual([(t, a["site"]) for t, a in game.calls], [("build_farm", "R2")])

    def test_site_used_is_never_attempted_twice(self):
        ov, game = self.overseer([site("R1", w=5, h=5, dug=True, soil=True)])
        game.used.add("R1")
        ov.farms()
        self.assertEqual(len(game.calls), 1)
        ov.load(facts(sites=[site("R1", w=5, h=5, dug=True, soil=True)], day=1))
        ov.count = 0
        game.calls.clear()
        ov.farms()
        self.assertEqual(game.calls, [])   # the plot is there to stay: the retry only burned an action


class RepeatRefusal(unittest.TestCase):
    """The model's second identical failed call within a game day is refused locally (no API call)."""

    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    class Game:
        def __init__(self):
            self.day, self.actions, self.fails = 0, [], 0
            self.fail_code = "no_space"
            self.last = {"day": 0, "tick": 0}

        def task(self):
            return {"task": {"days": 10}, "tools": [
                {"type": "function", "function": {"name": "place_furniture", "parameters": {
                    "type": "object", "properties": {"kind": {"type": "string"}, "site": {"type": "string"},
                                                     "count": {"type": "integer"}}}}},
                {"type": "function", "function": {"name": "advance_days", "parameters": {
                    "type": "object", "properties": {"days": {"type": "integer", "maximum": 28}}}}}]}

        def observe(self):
            self.last = {"day": self.day, "tick": self.day * 1200, "game_over": False}
            return {**self.last, "observation": {"date": {"abs_tick": self.last["tick"]}}}

        def act(self, name, args):
            self.actions.append((name, dict(args)))
            self.last = {"day": self.day, "tick": self.day * 1200, "game_over": False}
            if name == "place_furniture" and self.fails > 0:
                self.fails -= 1
                return {**self.last, "ok": False, "error_code": self.fail_code,
                        "error": "failure answer"}
            return {**self.last, "ok": True, "result": {}}

    def call(self, name="place_furniture", **args):
        return {"id": "c", "function": {"name": name, "arguments": json.dumps(args)}}

    def runner(self):
        game, runner = self.Game(), None
        runner = plain_harness.Plain(SimpleNamespace(task={"days": 10}, days=10, credits=None), game, None)
        runner.setup()
        return runner, game

    def test_same_day_identical_failure_is_refused_locally_once_recorded(self):
        runner, game = self.runner()
        game.fails = 2
        c = self.call(kind="table", site="A8", count=4)
        self.assertFalse(runner.run_call(c))                  # the API answers no_space and it is recorded
        first = len(game.actions)
        self.assertEqual(runner.stats["rejected"], 1)
        runner.run_call(c)
        self.assertEqual(len(game.actions), first)            # refused before the API
        self.assertEqual(runner.stats["repeat_refused"], 1)
        self.assertIn("already failed today", runner.messages[-1]["content"])
        game.day, game.last = 1, {"day": 1, "tick": 1200}    # the next day: the attempt is allowed again
        runner.run_call(c)
        self.assertEqual(len(game.actions), first + 1)
        self.assertEqual(runner.stats["repeat_refused"], 1)

    def test_changed_arguments_are_not_refused(self):
        runner, game = self.runner()
        game.fails = 2
        runner.run_call(self.call(kind="table", site="A8", count=4))
        runner.run_call(self.call(kind="table", site="A8", count=2))
        self.assertEqual(len(game.actions), 2)

    def test_a_transient_failure_is_not_held_for_the_day(self):
        # no_material clears itself inside the day (a workshop produces the item; digging reveals tiles): the
        # identical retry must reach the API again instead of waiting for tomorrow
        runner, game = self.runner()
        game.fail_code = "no_material"
        game.fails = 2
        c = self.call(kind="bed", site="A8", count=4)
        runner.run_call(c)
        runner.run_call(c)
        self.assertEqual(len(game.actions), 2)   # both calls hit the API
        self.assertEqual(runner.stats["repeat_refused"], 0)


class HousingAdvice(unittest.TestCase):
    def digest_text(self, day, failed_day=3, failed_site="A1"):
        mem = digest.Memory()
        mem.record(failed_day, "place_furniture", {"kind": "bed", "site": failed_site},
                   {"ok": False, "error_code": "no_space", "error": "no free floor tile"})
        obs = {"administrators": {"citizens": 10},
               "stocks": {"furniture_free": {"bed": 5, "table": 2, "chair": 2}},
               "map": {"sites": [site("A1"), site("A2", x=20)]}, "zones": [], "furniture": []}
        return digest.digest(obs, {"day": day, "tick": day * digest.DAY}, memory=mem)

    def test_advice_prefers_a_floor_that_did_not_answer_no_space(self):
        text = self.digest_text(day=4)
        self.assertIn("place_furniture bed count=5 on A2", text)
        self.assertNotIn("on A1", text)

    def test_old_failures_stop_steering_the_advice(self):
        text = self.digest_text(day=10)
        self.assertIn("on A1", text)


if __name__ == "__main__":
    unittest.main()
