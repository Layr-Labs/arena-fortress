"""d79: the alert at the start of spring is left out on a fort whose own water tells another thaw time. The water near
the wagon was seen to freeze, and either it has been seen again this winter or its predicted thaw comes after the
spring window. A year is 336 days and starts with spring; the stub's tick is the day times 1200."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from overseer.harness import DAY  # noqa: E402
from overseer import openplay as O  # noqa: E402
from support import Lockdown, threat_resp  # noqa: E402

ON, OFF = {"on": True}, {"on": False}


def wet(day, deep, alert=False):
    """An open-play reading on `day` with `deep` deep-water tiles near the wagon (0: the field left out, as the API
    does when there is none)."""
    r = threat_resp(day, None, alert=alert)
    if deep:
        r["observation"]["water_on_fort_levels"] = {"tiles": deep, "deep_tiles": deep, "total_depth": 7 * deep}
    return r


class D79(Lockdown, unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def run_days(self, plan, start=230, water=100):
        ov, g = self.play(wet(start, water))
        for day, deep in plan:
            self.again(ov, g, wet(day, deep, alert=bool(ov.thaw_alert)))
        return ov, g

    def test_a_fort_with_no_water_in_sight_keeps_the_spring_window(self):
        ov, g = self.run_days([(d, 0) for d in (300, 334, 335, 336, 338, 339)], water=0)
        self.assertEqual(g.tools("civilian_alert"), [ON, OFF])
        self.assertFalse(ov.thaw_elsewhere())

    def test_water_that_never_froze_keeps_the_spring_window(self):
        ov, g = self.run_days([(d, 100) for d in (260, 300, 334, 335, 336, 338, 339)])
        self.assertEqual(g.tools("civilian_alert"), [ON, OFF])

    def test_a_thaw_predicted_after_the_window_leaves_the_window_out(self):
        ov, g = self.run_days([(238, 100), (240, 0), (300, 0), (334, 0)])       # mirrored: days 346.8 to 348.8
        for day in (335, 336, 337, 338, 339, 344):
            self.again(ov, g, wet(day, 0))
            self.assertTrue(ov.thaw_elsewhere() or day == 344, day)
        self.assertEqual(g.tools("civilian_alert"), [])               # the fort works through the start of spring
        self.again(ov, g, wet(346, 0))                                # a day before the predicted thaw, as before
        self.assertEqual((g.tools("civilian_alert"), ov.thaw_alert), ([ON], True))
        self.again(ov, g, wet(348, 377, alert=True))                  # the water is back: two days more
        self.again(ov, g, wet(350, 377, alert=True))
        self.assertEqual(g.tools("civilian_alert"), [ON, OFF])

    def test_a_thaw_seen_in_winter_leaves_the_window_out(self):
        ov, g = self.run_days([(271, 100), (273, 0), (312, 0), (313, 0), (314, 124), (315, 124), (316, 124)])
        self.assertEqual(g.tools("civilian_alert"), [ON, OFF])        # its own alert, around day 314
        self.assertEqual((ov.freeze, ov.thaw_seen), (None, 314 * DAY))
        for day in (334, 335, 336, 337, 338, 339):
            self.again(ov, g, wet(day, 124))
        self.assertEqual(g.tools("civilian_alert"), [ON, OFF])        # and none at the start of spring

    def test_a_thaw_seen_outside_its_predicted_time_counts_too(self):
        ov, g = self.run_days([(271, 100), (273, 0), (300, 0), (302, 124)])       # eleven days early
        self.assertEqual((ov.thawed_at, ov.thaw_seen), (None, 302 * DAY))
        for day in (335, 336, 338):
            self.again(ov, g, wet(day, 124))
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_a_freeze_whose_time_has_passed_tells_nothing(self):
        ov, g = self.run_days([(271, 100), (273, 0), (312, 0), (314, 0), (316, 0), (318, 0), (334, 0)])
        self.assertEqual(g.tools("civilian_alert"), [ON, OFF])        # the predicted thaw came and went, no water seen
        self.assertFalse(ov.thaw_elsewhere())
        for day in (335, 336, 338, 339):
            self.again(ov, g, wet(day, 0, alert=bool(ov.thaw_alert)))
        self.assertEqual(g.tools("civilian_alert"), [ON, OFF, ON, OFF])           # so the spring window stands

    def test_a_thaw_at_the_start_of_spring_is_covered_as_before(self):
        ov, g = self.run_days([(248, 100), (250, 0), (300, 0), (333, 0)])       # mirrored: days 336.8 to 338.8
        self.assertFalse(ov.thaw_elsewhere())
        for day in (334, 335, 336, 337, 338):
            self.again(ov, g, wet(day, 0, alert=bool(ov.thaw_alert)))
        self.assertEqual((g.tools("civilian_alert"), ov.thaw_alert), ([ON], True))

    def test_a_second_freeze_forgets_the_first_thaw(self):
        ov, g = self.run_days([(232, 0), (236, 100), (238, 100), (240, 0), (334, 0)])    # gone and back, then frozen
        self.assertEqual((ov.thaw_seen, ov.freeze), (None, (238 * DAY, 240 * DAY)))
        self.assertTrue(ov.thaw_elsewhere())                          # by the second freeze's prediction

    def test_an_old_thaw_is_forgotten(self):
        ov, g = self.run_days([(271, 100), (273, 0), (300, 0), (302, 124)])
        ov.thaw_seen -= (O.THAW_MEMORY - 30) * DAY                     # as if seen long ago
        self.again(ov, g, wet(335, 124))
        self.assertEqual(g.tools("civilian_alert"), [ON])


if __name__ == "__main__":
    unittest.main()
