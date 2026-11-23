"""d53: the thaw of the water near the wagon, predicted from its freeze. Deep water seen in autumn and gone from a
full reading (ice is not water) records a freeze; the thaw is expected at the freeze's mirror image about midwinter,
and the civilian alert holds from a day before it to two days after the water is seen again (or a day and a half
past the prediction). A year is 336 days and starts with spring; the stub's tick is the day times 1200."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from overseer.harness import DAY, Overseer  # noqa: E402
from support import Lockdown, StubGame, threat_resp  # noqa: E402

ON, OFF = {"on": True}, {"on": False}


def wet(day, deep, alert=False, water="dict", drop=()):
    """An open-play reading on `day` with `deep` deep-water tiles near the wagon (0: the field left out, as the API
    does when there is none)."""
    r = threat_resp(day, None, alert=alert, drop=drop)
    if water == "err":
        r["observation"]["water_on_fort_levels"] = "ERR: scripted"
    elif deep:
        r["observation"]["water_on_fort_levels"] = {"tiles": deep, "deep_tiles": deep, "total_depth": 7 * deep}
    return r


class D53(Lockdown, unittest.TestCase):
    def run_days(self, plan, start=230):
        """Play `plan`: (day, deep tiles) in order, the alert shown as the layer left it."""
        ov, g = self.play(wet(start, 100))
        for day, deep in plan:
            self.again(ov, g, wet(day, deep, alert=bool(ov.thaw_alert)))
        return ov, g

    def test_a_late_thaw_is_predicted_and_the_alert_holds_across_it(self):
        ov, g = self.run_days([(236, 100), (238, 100), (240, 0)])        # last seen day 238, gone on day 240
        self.assertEqual(ov.freeze, (238 * DAY, 240 * DAY))
        a, b = ov.thaw_range()
        self.assertEqual((round(a / DAY, 1), round(b / DAY, 1)), (346.8, 348.8))   # spring days 10.8 to 12.8
        for day in (250, 300, 334):
            self.again(ov, g, wet(day, 0, alert=bool(ov.thaw_alert)))
        self.assertEqual(g.tools("civilian_alert"), [])
        for day in (335, 336, 337, 338, 339):                         # the spring window, as before
            self.again(ov, g, wet(day, 0, alert=bool(ov.thaw_alert)))
        self.assertEqual(g.tools("civilian_alert"), [ON, OFF])
        self.again(ov, g, wet(344, 0))
        self.assertEqual((g.tools("civilian_alert"), ov.step_days()), ([ON, OFF], 1))    # daily passes before it
        self.again(ov, g, wet(345, 0))
        self.assertEqual(g.tools("civilian_alert"), [ON, OFF])        # 345 is before a day ahead of 346.8
        self.again(ov, g, wet(346, 0))
        self.assertEqual((g.tools("civilian_alert"), ov.thaw_alert), ([ON, OFF, ON], True))
        self.again(ov, g, wet(347, 0, alert=True))
        self.again(ov, g, wet(348, 377, alert=True))                  # the water is back: two days more
        self.assertEqual((ov.thawed_at, ov.freeze), (348 * DAY, None))
        self.again(ov, g, wet(349, 377, alert=True))
        self.assertEqual(g.tools("civilian_alert"), [ON, OFF, ON])
        self.again(ov, g, wet(350, 377, alert=True))
        self.assertEqual((g.tools("civilian_alert"), ov.thaw_alert), ([ON, OFF, ON, OFF], False))

    def test_water_that_never_comes_back_ends_the_alert_after_the_prediction(self):
        ov, g = self.run_days([(238, 100), (240, 0)] + [(d, 0) for d in range(346, 351)])
        self.assertEqual(g.tools("civilian_alert"), [ON])             # 350 is within 348.8 + 1.5
        self.again(ov, g, wet(351, 0, alert=True))
        self.assertEqual(g.tools("civilian_alert"), [ON, OFF])

    def test_a_winter_thaw_gets_its_own_alert(self):
        ov, g = self.run_days([(271, 100), (273, 0), (312, 0)])        # mirrored: days 313.8 to 315.8
        self.assertEqual(g.tools("civilian_alert"), [])
        for day, deep in ((313, 0), (314, 124), (315, 124)):
            self.again(ov, g, wet(day, deep, alert=bool(ov.thaw_alert)))
        self.assertEqual(g.tools("civilian_alert"), [ON])
        self.again(ov, g, wet(316, 124, alert=True))
        self.assertEqual(g.tools("civilian_alert"), [ON, OFF])

    def test_no_deep_water_keeps_the_spring_window_alone(self):
        ov, g = self.play(wet(230, 0))
        for day in (240, 300, 335, 336, 339, 346, 348, 350):
            self.again(ov, g, wet(day, 0, alert=bool(ov.thaw_alert)))
        self.assertEqual((g.tools("civilian_alert"), ov.freeze), ([ON, OFF], None))

    def test_water_back_long_before_the_prediction_is_no_thaw(self):
        ov, g = self.run_days([(238, 100), (240, 0), (260, 100), (262, 100)])
        self.assertEqual((ov.freeze, ov.thawed_at), (None, None))
        for day in (346, 348):
            self.again(ov, g, wet(day, 100, alert=bool(ov.thaw_alert)))
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_only_an_autumn_loss_bracketed_closely_is_a_freeze(self):
        ov, _ = self.run_days([(150, 100), (152, 0)], start=148)       # summer: dug away or drained, not ice
        self.assertIsNone(ov.freeze)
        ov, _ = self.run_days([(238, 100), (245, 0)])                  # seven days apart: no prediction
        self.assertIsNone(ov.freeze)
        ov, _ = self.run_days([(238, 100), (240, 0), (242, 100), (244, 0)])   # a second loss after a sighting
        self.assertEqual(ov.freeze, (242 * DAY, 244 * DAY))

    def test_an_unreadable_or_partial_reading_records_nothing(self):
        ov, g = self.run_days([(238, 100)])
        self.again(ov, g, wet(239, 0, water="err"))
        self.again(ov, g, wet(240, 0, drop=("burrows",)))
        self.assertEqual((ov.freeze, ov.deep_seen), (None, 238 * DAY))
        self.again(ov, g, wet(241, 0))
        self.assertEqual(ov.freeze, (238 * DAY, 241 * DAY))

    def test_the_labs_record_the_water_and_act_on_none_of_it(self):
        g = StubGame()
        ov = Overseer(g, goal="Run the fortress", days=336)
        ov.set_task({"goal": "Run the fortress.", "hands_off": {"from_day": 30, "days": 10}})
        for day, deep in ((238, 100), (240, 0), (346, 0), (347, 0)):
            ov.load(wet(day, deep))
            ov.count = 0
            ov.defend()
        self.assertEqual(g.tools("civilian_alert"), [])


if __name__ == "__main__":
    unittest.main()
