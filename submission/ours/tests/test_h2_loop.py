"""h2: the layer's loop outlives a game server that fails for a while.

Before h2 one HTTP 500, one body that was not JSON, or a timeout that outlasted the client's retries on GET /observe,
or a lost answer to an advance, ended the harness (main() returned 1). The runner then has the server finish the game
unmanaged (POST /finish) and scores it like any other game. Now a read is tried again for up to SERVER_WAIT seconds
(time inside the client included; after that the harness ends as before), an advance whose answer is lost is followed
by a look at the clock, and an observation that can't be read costs one pass. No day is advanced without a look.
"""
import http.client
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))
from support import Task, resp  # noqa: E402
from dfbench_client import GameAPIError, GameOver, GameUnavailable  # noqa: E402
from overseer.harness import Overseer  # noqa: E402
from plain import harness as H  # noqa: E402
from plain.harness import ADVANCE_FAILS, SERVER_WAIT, Plain  # noqa: E402

DAY = 1200


class Clock:
    """time.monotonic() and time.sleep() for the loop: sleeping and (through ScriptedGame.io) failing calls take time."""

    def __init__(self):
        self.t, self.slept = 5000.0, []

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.t += seconds


class ScriptedGame:
    """observe() and advance_days answer from scripts; without one, observe follows the clock and an advance moves it.
    `io` is the seconds a failing call takes inside the client (its own retries and time-outs); `window` is the day a
    hands-off window starts."""

    retries, timeout = 5, 60.0              # as the challenge's client has them

    def __init__(self, clock=None, horizon=336, io=0.0, window=None):
        self.day, self.extra, self.horizon, self.last = 0, 0, horizon, {}
        self.clock, self.io, self.io_post, self.window = clock, io, None, window
        self.calls, self.looks, self.advances, self.tasks, self.tries = [], [], [], [], []

    def fail(self, error, post=False):
        """A failing call takes `io` seconds with the client's retries on, and no longer than its time-out without
        (`io_post` for an advance, whose time-out is its own)."""
        self.tries.append((self.retries, self.timeout))
        if self.clock is not None and post and self.io_post is not None:
            self.clock.t += self.io_post
        elif self.clock is not None:
            self.clock.t += self.io if self.retries else min(self.io, self.timeout)
        raise error

    def task(self):
        self.calls.append("task")
        if self.tasks:
            fault = self.tasks.pop(0)
            if isinstance(fault, Exception):
                self.fail(fault)
            return fault
        return {"task": {"days": self.horizon}, "tools": []}

    def observe(self):
        self.calls.append("observe")
        if self.looks:
            fault = self.looks.pop(0)
            if isinstance(fault, Exception):
                self.fail(fault)
            if fault is not None:
                return fault
        if self.day >= self.horizon:
            return {"day": self.day, "tick": self.day * DAY, "game_over": True}
        r = resp(self.horizon - self.day, self.day, food=50,
                 hands_off=None if self.window is None else self.window - self.day)
        r["tick"] = self.day * DAY + self.extra
        self.last = {k: r[k] for k in ("day", "tick", "hands_off_in_days") if k in r}
        return r

    def act(self, tool, args):
        self.calls.append(tool)
        if tool != "advance_days":
            return {"ok": True, "result": {}}
        step = self.advances.pop(0) if self.advances else "ok"
        if step == "lost_after":            # the game advanced, the answer never came
            self.day, self.extra = self.day + args["days"], 0
            self.fail(GameUnavailable("POST /act: timed out"), post=True)
        if step == "lost_stopped":          # the game stopped 350 ticks into the same day, and the answer was lost
            self.extra += 350
            self.fail(GameUnavailable("POST /act: timed out"), post=True)
        if step == "lost_before":           # nothing happened, and no answer either
            self.fail(GameUnavailable("POST /act: timed out"), post=True)
        if step == "not_json":
            self.fail(GameAPIError("POST /act: HTTP 502, body is not a JSON object", 502))
        if step == "refused":
            return {"ok": False, "error_code": "internal_error", "day": self.day}
        self.day, self.extra = self.day + args["days"], 0
        return {"ok": True, "day": self.day, "result": {"advanced_ticks": args["days"] * DAY, "stopped": None}}

    def query(self, *a, **kw):
        return {"result": {"units": [], "total": 0}}


class Loop(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)
        self.clock = Clock()
        for name in ("sleep", "monotonic"):
            p = patch.object(H.time, name, side_effect=getattr(self.clock, name))
            p.start()
            self.addCleanup(p.stop)
        self.start = self.clock.t
        self.g = ScriptedGame(self.clock)
        self.p = Plain(Task(), self.g, model=None)
        self.passes = []
        self.p.guard.step = lambda r: self.passes.append(r["day"]) or 0
        self.p.quiet_days = lambda r: 1

    def run_to_end(self):
        self.assertFalse(self.p.layer_only("no_model"))
        self.assertEqual(self.p.stop_reason, "game_over")

    def advances_before(self, call):
        """advance_days calls made before the n-th observe call (1-based)."""
        seen = 0
        for i, c in enumerate(self.g.calls):
            seen += c == "observe"
            if seen == call:
                return self.g.calls[:i].count("advance_days")
        return self.g.calls.count("advance_days")

    # reads
    def test_an_http_error_on_observe_is_waited_out(self):
        self.g.horizon = 3
        self.g.looks = [GameAPIError("GET /observe: HTTP 500: internal_error", 500), None]
        self.run_to_end()
        self.assertEqual(self.passes, [0, 1, 2])               # no day lost, no exit
        self.assertEqual(len(self.clock.slept), 1)

    def test_an_answer_without_an_observation_is_waited_out(self):
        self.g.horizon = 2
        self.g.looks = [{"day": 0, "tick": 0}, GameUnavailable("GET /observe: timed out"), None]
        self.run_to_end()
        self.assertEqual(self.passes, [0, 1])

    def test_a_body_cut_short_is_waited_out(self):
        self.g.horizon = 2                                     # what escapes the client while it reads an HTTP error
        self.g.looks = [http.client.IncompleteRead(b""), ConnectionResetError("reset"), None]
        self.run_to_end()
        self.assertEqual(self.passes, [0, 1])

    def test_a_server_silent_for_too_long_ends_the_harness_as_before(self):
        self.g.looks = [GameAPIError("GET /observe: HTTP 500", 500)] * 60      # quick failures, more than 300 s of them
        with self.assertRaises(GameAPIError):
            self.p.layer_only("no_model")
        self.assertLessEqual(self.clock.t - self.start, SERVER_WAIT + 1)
        self.assertEqual(self.g.calls.count("advance_days"), 0)                # and no day was advanced unseen

    def test_time_inside_the_client_counts(self):
        self.g.io = 391.0                                      # six 60 s time-outs and the client's own backoff
        self.g.looks = [GameUnavailable("GET /observe: timed out")] * 30
        with self.assertRaises(GameAPIError):
            self.p.layer_only("no_model")
        self.assertEqual(self.g.calls.count("observe"), 1)     # one try, as before h2: not twenty-five
        self.assertLess(self.clock.t - self.start, 400)

    def test_later_tries_are_single_and_cut_to_what_is_left(self):
        self.g.io = 100.0                                      # every try hangs
        self.g.looks = [GameUnavailable("GET /observe: timed out")] * 30
        with self.assertRaises(GameAPIError):
            self.p.layer_only("no_model")
        self.assertLessEqual(self.clock.t - self.start, SERVER_WAIT + 1)
        self.assertEqual(self.g.tries[0], (5, 60.0))           # the first try is the client's own
        self.assertTrue(all(r == 0 and t <= 60.0 for r, t in self.g.tries[1:]))
        self.assertLess(self.g.tries[-1][1], 60.0)             # the last one had less than a full time-out left
        self.assertEqual((self.g.retries, self.g.timeout), (5, 60.0))          # and the client is as it was

    def test_no_day_is_advanced_without_a_look(self):
        self.g.horizon = 2
        self.g.looks = [GameAPIError("GET /observe: HTTP 500", 500)] * 10      # under a minute of failures
        self.run_to_end()
        self.assertEqual(self.advances_before(11), 0)
        self.assertEqual(self.passes, [0, 1])

    def test_the_task_is_waited_for_too(self):
        self.g.tasks = [GameAPIError("GET /task: HTTP 500", 500)]
        self.p.setup()
        self.assertEqual(self.g.calls, ["task", "task"])

    def test_a_task_that_never_comes_ends_the_harness(self):
        self.g.tasks = [GameAPIError("GET /task: HTTP 500", 500)] * 60
        with self.assertRaises(GameAPIError):
            self.p.setup()

    # advances
    def test_a_lost_answer_to_an_advance_is_followed_by_a_look(self):
        self.g.horizon = 4
        self.g.advances = ["lost_before", "lost_after", "not_json"]
        self.run_to_end()
        self.assertEqual(sorted(set(self.passes)), [0, 1, 2, 3])               # every day that came got its pass
        self.assertEqual(self.p.advance_fails, 0)              # reset by the first answered advance

    def test_a_lost_answer_with_a_stop_behind_it(self):
        self.g.horizon = 2                                     # the game stopped 350 ticks on (a tripwire), answer lost
        self.g.advances = ["lost_stopped"]
        self.p.open_play = lambda: True
        self.run_to_end()
        if hasattr(self.p, "last_stop"):                       # the controller that gives a stop a pass of its own
            self.assertEqual(self.passes, [0, 0, 1])
        else:                                                  # main's passes once a game day, as it always did
            self.assertEqual(self.passes, [0, 1])

    def test_a_lost_answer_with_nothing_behind_it_gets_no_second_pass(self):
        self.g.horizon = 2                                     # the advance never ran: the same tick again
        self.g.advances = ["lost_before"]
        self.p.open_play = lambda: True
        self.run_to_end()
        self.assertEqual(self.passes, [0, 1])

    def test_a_look_without_its_clock_does_not_settle_a_lost_answer(self):
        self.g.horizon = 2
        self.g.advances = ["lost_stopped"]
        self.p.open_play = lambda: True
        blind = resp(336, 0, food=50)
        del blind["tick"]                                      # an observation, and no clock on it
        self.g.looks = [None, blind]
        self.run_to_end()
        self.assertEqual(self.advances_before(3), 1)           # no second advance on the clockless answer
        self.assertEqual(self.passes, [0, 0, 1] if hasattr(self.p, "last_stop") else [0, 1])

    def test_the_look_after_a_pass_is_waited_for_too(self):
        self.g.horizon = 2
        self.p.guard.step = lambda r: self.passes.append(r["day"]) or 1        # the pass acted: main's looks again
        self.g.looks = [None, GameAPIError("GET /observe: HTTP 500", 500)]
        self.run_to_end()
        self.assertEqual(self.passes, [0, 1])

    def test_a_lab_keeps_its_one_pass_a_day(self):
        self.g.horizon = 2
        self.g.advances = ["lost_stopped"]
        self.p.open_play = lambda: False
        self.run_to_end()
        self.assertEqual(self.passes, [0, 1])

    def test_no_second_advance_while_the_first_is_unresolved(self):
        self.g.horizon = 2
        self.g.advances = ["lost_after"]
        self.g.looks = [None] + [GameAPIError("GET /observe: HTTP 500", 500)] * 10     # then reads fail for a while
        self.run_to_end()
        self.assertEqual(self.advances_before(12), 1)          # only the lost one, until the clock could be read
        self.assertEqual(self.passes, [0, 1])

    def test_a_refused_advance_is_paced_not_spun(self):
        self.g.horizon = 2
        self.g.advances = ["refused", "refused"]
        self.run_to_end()
        self.assertEqual(self.passes, [0, 1])
        self.assertEqual(self.clock.slept, [0.5, 1.0])

    def test_a_server_that_never_answers_an_advance_is_given_up(self):
        self.g.advances = ["lost_before"] * (ADVANCE_FAILS + 5)
        with self.assertRaises(GameAPIError):                  # after the look that followed the last lost answer
            self.p.layer_only("no_model")
        self.assertEqual(self.g.calls.count("advance_days"), ADVANCE_FAILS + 1)
        self.assertEqual(self.g.calls[-1], "observe")

    def test_refusals_alone_never_end_the_harness(self):
        self.g.horizon = 2                                     # answered every time: main's loop went on too
        self.g.advances = ["refused"] * (ADVANCE_FAILS + 5)
        self.run_to_end()
        self.assertEqual(self.passes, [0, 1])

    def test_progress_between_lost_answers_is_not_a_dead_server(self):
        self.g.horizon = ADVANCE_FAILS + 10                    # every answer is lost, and every advance worked
        self.g.advances = ["lost_after"] * self.g.horizon
        self.run_to_end()
        self.assertEqual(sorted(set(self.passes)), list(range(self.g.horizon)))

    def test_a_hung_advance_is_survived_when_the_server_comes_back(self):
        self.g.horizon, self.g.io_post = 3, 1800.0             # the client's time-out for an advance
        self.g.advances = ["lost_after"]
        self.run_to_end()
        self.assertEqual(self.passes, [0, 1, 2])

    def test_a_dead_server_after_a_hung_advance_ends_the_harness(self):
        self.g.io, self.g.io_post = 391.0, 1800.0              # the client's cycle for a GET, its time-out for an advance
        self.g.advances = ["lost_before"]
        self.g.looks = [None] + [GameUnavailable("GET /observe: timed out")] * 30
        with self.assertRaises(GameAPIError):
            self.p.layer_only("no_model")
        self.assertEqual(self.g.calls.count("advance_days"), 1)
        self.assertEqual(self.g.calls.count("observe"), 2)     # the first look, and one try after the lost answer
        self.assertEqual(self.clock.t - self.start, 1800.0 + 0.5 + 391.0)      # what main's loop could spend, and one look

    def test_game_over_still_ends_the_loop(self):
        self.g.horizon = 1
        with patch.object(self.g, "act", side_effect=GameOver("game_over")):
            self.assertFalse(self.p.layer_only("no_model"))
        self.assertEqual(self.p.stop_reason, "GameOver")

    def test_a_pacing_error_costs_nothing(self):
        self.g.horizon = 2
        self.p.quiet_days = lambda r: 1 / 0
        self.run_to_end()
        self.assertEqual(self.passes, [0, 1])


class Step(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_an_observation_that_cannot_be_read_costs_one_pass(self):
        ov = Overseer(ScriptedGame(), days=336)
        planned, plan = [], ov.plan
        ov.plan = lambda: planned.append(ov.day) or plan()
        bad = resp(200, 136, food=50)
        bad["observation"]["orders"] = [{"id": [], "recipe": "?"}]          # an unhashable id: load() raised before h2
        self.assertEqual(ov.step(bad), 0)
        self.assertEqual(planned, [])                                         # nothing was planned on what it could not read
        ov.step(resp(199, 137, food=50))
        self.assertEqual(planned, [137])                                      # and the next pass runs in full


if __name__ == "__main__":
    unittest.main()
