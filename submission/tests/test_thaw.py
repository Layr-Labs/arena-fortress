"""Offline regressions for the spring-thaw guard on open play: the civilian alert holds from the last day of winter
to the third day of spring (no hatch is locked), the inherited rule does not clear it, a lockdown can still start and
takes the alert over, the day above ground owed after a full lockdown comes first, and the harness's exit clears
it. A year is 336 days and starts with spring, so day 335 is the last day of winter. Stub game; no DF and no model.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from overseer.harness import DAY, Overseer  # noqa: E402
from support import Lockdown, beast, quiet, threat_resp  # noqa: E402

from dfbench_client import GameAPIError  # noqa: E402

ON, OFF = {"on": True}, {"on": False}


class Thaw(Lockdown, unittest.TestCase):
    def test_the_alert_holds_across_the_thaw_and_is_then_cleared(self):
        ov, g = self.play(threat_resp(334, None))                    # two days before spring: not yet
        self.assertEqual((g.tools("civilian_alert"), ov.step_days()), ([], 1))
        self.again(ov, g, threat_resp(335, None))                    # the last day of winter
        self.assertEqual((g.tools("civilian_alert"), ov.thaw_alert), ([ON], True))
        for day in (336, 337, 338):                                  # spring days 0 to 2: held, not cleared
            self.again(ov, g, threat_resp(day, None, alert=True))
        self.assertEqual((g.tools("civilian_alert"), g.tools("lock_door"), ov.status()["thaw"]), ([ON], [], True))
        self.again(ov, g, threat_resp(339, None, alert=True))        # spring day 3
        self.assertEqual((g.tools("civilian_alert"), ov.thaw_alert, ov.step_days()), ([ON, OFF], False, 2))

    def test_the_window_reads_real_ticks(self):
        r = threat_resp(322, None)                                   # a recorded game's spring day 1, year 3
        r["observation"]["date"]["abs_tick"] = r["tick"] = 3 * 336 * DAY + 600
        ov, g = self.play(r)
        self.assertEqual(g.tools("civilian_alert"), [ON])

    def test_not_in_a_games_first_month_nor_off_the_window(self):
        for day in (0, 1, 200):
            ov, g = self.play(threat_resp(day, None))
            self.assertEqual(g.tools("civilian_alert"), [], day)

    def test_a_refused_clear_is_tried_again(self):
        ov, g = self.play(threat_resp(339, None, alert=True), thaw_alert=True, refuse={("civilian_alert", None)})
        self.assertEqual((g.tools("civilian_alert"), ov.thaw_alert), ([OFF], True))
        g.refuse = set()
        self.again(ov, g, threat_resp(340, None, alert=True))
        self.assertEqual((g.tools("civilian_alert"), ov.thaw_alert), ([OFF, OFF], False))

    def test_a_lockdown_takes_the_alert_over_and_the_rest_day_comes_first(self):
        r = quiet(336, [beast("CRETACEOUS_CARNOTAURUS", 70)], alert=True)
        ov, g = self.play(r, thaw_alert=True)
        g.others = r["others"]
        ov.load(r); ov.count = 0
        ov.defend()                                                  # the look runs now that the stub lists it
        self.assertEqual((ov.lock is not None, ov.thaw_alert), (True, False))
        ov, g = self.play(threat_resp(336, None), rest_until=337 * DAY)
        self.assertEqual(g.tools("civilian_alert"), [])              # owed its day above ground: no thaw alert

    def test_a_lost_answer_still_leaves_it_to_clear_and_a_stale_invader_clock_gives_way(self):
        class Lost(type(self.play(threat_resp(200, None))[1])):
            def act(self, tool, args):
                if tool == "civilian_alert" and args.get("on"):
                    self.calls.append((tool, dict(args)))
                    raise GameAPIError("no answer")
                return super().act(tool, args)
        g = Lost()
        ov = Overseer(g, goal="Run the fortress", days=336)
        ov.set_task({"goal": "Run the fortress for 336 days."})
        ov.step(threat_resp(335, None))                              # sent, unanswered: still this layer's
        self.assertTrue(ov.thaw_alert)
        ov.release()
        self.assertEqual(g.tools("civilian_alert")[-1], OFF)
        ov, g = self.play(threat_resp(335, None), alert_since=300 * DAY)   # shown off, no lockdown, an old clock
        self.assertEqual((g.tools("civilian_alert"), ov.alert_since), ([ON], None))

    def test_the_exit_clears_it(self):
        ov, g = self.play(threat_resp(336, None, alert=True), thaw_alert=True)
        ov.release()
        self.assertEqual((g.tools("civilian_alert")[-1], ov.thaw_alert), (OFF, False))

    def test_the_inherited_rule_still_clears_an_alert_nobody_owns(self):
        ov, g = self.play(threat_resp(200, None, alert=True))
        self.assertEqual(g.tools("civilian_alert"), [OFF])


if __name__ == "__main__":
    unittest.main()
