"""d57: the feast starts a pass earlier (15 days left, was 14), the pass before the spring alert, so its first batch is
butchered before the civilians are kept in the shelter. Both open tasks end on spring day 14: the alert turned on in
the feast's first pass and the meat came five days late, with food at 3 to 10 in OP1's scored stretch."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402
from overseer.openplay import FEAST_BATCH, FEAST_DAYS  # noqa: E402


class D57(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_the_feast_starts_with_15_days_left(self):
        self.assertEqual(FEAST_DAYS, 15)
        ov, g = overseer(resp(15, 321, food=40, plants=40))
        ov.provision()
        self.assertEqual(len(g.tools("slaughter")), FEAST_BATCH)

    def test_16_days_left_is_still_before_the_feast(self):
        ov, g = overseer(resp(16, 320, food=40, plants=40))    # food above the final-stretch trigger: no cull
        ov.provision()
        self.assertEqual(g.tools("slaughter"), [])

    def test_the_feast_pass_comes_before_the_spring_alert(self):
        # OP1: day 0 is abs_tick 823200 (year 2, day 14 of the year counted from 0); the harness reads days_left as
        # days - day - 1, so day 320 has 15 left and day 321, the last day of winter, 14
        def at(day):
            r = resp(336 - day - 1, day, food=40, plants=40)
            r["observation"]["date"]["abs_tick"] = 823200 + day * 1200
            return r
        ov, g = overseer(at(320))
        self.assertFalse(ov.thaw_window())
        ov.provision()
        self.assertEqual(len(g.tools("slaughter")), FEAST_BATCH)
        ov.load(at(321))
        self.assertTrue(ov.thaw_window())


if __name__ == "__main__":
    unittest.main()
