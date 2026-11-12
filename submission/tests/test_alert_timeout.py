"""Regressions for civilian alert timing. No game or network is used."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class FakeGame:
    def __init__(self, responses=()):
        self.responses, self.calls = list(responses), []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if self.responses:
            return self.responses.pop(0)
        return {"ok": True, "result": {"civilian_alert": args["on"]}}


class AlertTimeout(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, responses=()):
        game = FakeGame(responses)
        overseer = harness.Overseer(game)
        overseer.count = 0
        return overseer, game

    def observe(self, overseer, day, alert, invaders=True):
        overseer.load({"tick": day * harness.DAY, "observation": {
            "administrators": {"citizens": 7}, "stocks": {}, "map": {"sites": []},
            "military": {"squads": []},
            "threats": {"visible_hostiles": int(invaders), "nearest_hostile_dist_to_wagon": 10,
                        "hostiles": [{"id": 42, "invader": True}] if invaders else []},
            "burrows": {"civilian_alert": alert, "list": [{"id": 1, "civ_alert_burrow": True}]},
        }})
        overseer.defend()

    def test_existing_alert_starts_timer_and_expires_after_ten_days(self):
        overseer, game = self.overseer()
        self.observe(overseer, 5, True)
        self.assertEqual(overseer.alert_since, 5 * harness.DAY)
        self.observe(overseer, 15, True)
        self.assertEqual(game.calls, [])
        self.observe(overseer, 16, True)
        self.assertEqual(game.calls, [("civilian_alert", {"on": False})])
        self.assertIsNone(overseer.alert_since)

    def test_observed_alert_preserves_successful_activation_time(self):
        overseer, game = self.overseer()
        self.observe(overseer, 5, False)
        self.assertEqual(overseer.alert_since, 5 * harness.DAY)
        self.observe(overseer, 6, True)
        self.assertEqual(overseer.alert_since, 5 * harness.DAY)
        self.observe(overseer, 15, True)
        self.assertEqual(game.calls, [("civilian_alert", {"on": True})])
        self.observe(overseer, 16, True)
        self.assertEqual(game.calls[-1], ("civilian_alert", {"on": False}))

    def test_failed_activation_keeps_timer_clear_and_one_day_retry(self):
        # cx: was a 20-day retry — a siege back in sight after a lift could not re-sound the alert for 20 days
        overseer, game = self.overseer([{"ok": False, "error_code": "no_burrow"}])
        self.observe(overseer, 5, False)
        self.assertIsNone(overseer.alert_since)
        self.assertEqual(overseer.tries["alert_on"], 1)
        self.observe(overseer, 5.5, False)
        self.assertEqual(len(game.calls), 1)
        self.assertIsNone(overseer.alert_since)
        self.observe(overseer, 6, False)
        self.assertEqual(len(game.calls), 2)
        self.assertEqual(overseer.alert_since, 6 * harness.DAY)

    def test_invaders_back_after_the_cap_lift_re_sound_after_the_drink_window(self):
        # cx invader drink window (owner 2026-11-10): was "on again the next day" — the window never completed
        overseer, game = self.overseer()
        self.observe(overseer, 5, False)                      # sounded
        self.observe(overseer, 16, True)                      # the 10-day cap lifts it, invaders or not
        self.assertEqual(game.calls[-1], ("civilian_alert", {"on": False}))
        self.observe(overseer, 17, False)                     # inside the ACCESS_WINDOW_DAYS window: held off
        self.assertEqual(game.calls[-1], ("civilian_alert", {"on": False}))
        self.observe(overseer, 18, False)                     # the window is over, still in sight: on again
        self.assertEqual(game.calls[-1], ("civilian_alert", {"on": True}))

    def test_failed_clear_keeps_timer_and_one_day_retry(self):
        overseer, game = self.overseer([{"ok": False, "error_code": "lua_error"}])
        overseer.alert_since = 5 * harness.DAY
        self.observe(overseer, 16, True)
        self.assertEqual(overseer.alert_since, 5 * harness.DAY)
        self.assertEqual(overseer.tries["alert_off"], 1)
        self.observe(overseer, 16.5, True)
        self.assertEqual(len(game.calls), 1)
        self.assertEqual(overseer.alert_since, 5 * harness.DAY)
        self.observe(overseer, 17, True)
        self.assertEqual(game.calls, [("civilian_alert", {"on": False})] * 2)
        self.assertIsNone(overseer.alert_since)

    def test_observed_clear_resets_timer_without_an_action(self):
        overseer, game = self.overseer()
        overseer.alert_since = 5 * harness.DAY
        self.observe(overseer, 6, False, invaders=False)
        self.assertIsNone(overseer.alert_since)
        self.assertEqual(game.calls, [])


if __name__ == "__main__":
    unittest.main()
