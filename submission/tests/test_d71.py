"""d71: the migrant-surge task preps four weeks out. Its window scores drink as a RATIO to its first day; measured
locally at 47-50 citizens the ratio came out 0.947 (partial 0.9868) and one official draw scored LT08 partial 0.97.
The plots harvest about every 25 days, so two more prep weeks buy two more harvests brewed before the window."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402

SURGE = {"goal": "Migrants are arriving. From day 39 you can't act for 21 days. By day 60 every dwarf must have a "
                 "placed bed, drink and food must be in stock every day from day 39, and drink must not end lower "
                 "than it was on day 39. No dwarf may die.",
         "days": 60, "hands_off": 21}
RESCUE = {"goal": "From day 69 you can't act for 21 days. Keep drink and food in stock every day of that window.",
          "days": 90, "hands_off": 21}


def with_task(goal, days, hands_off):
    ov, g = overseer(resp(hands_off, days - hands_off, food=60, cit=47, hands_off=hands_off))
    ov.set_task(goal)
    return ov


class D71(unittest.TestCase):
    def test_the_surge_task_preps_four_weeks_out(self):
        ov = with_task(SURGE, 60, 21)
        ov.hands_off = 26
        self.assertTrue(ov.in_window_prep())

    def test_the_other_labs_keep_fourteen(self):
        ov = with_task(RESCUE, 90, 21)
        ov.hands_off = 20
        self.assertFalse(ov.in_window_prep())

    def test_the_surge_policy_is_distinct_from_the_droughts(self):
        ov = with_task(SURGE, 60, 21)
        self.assertTrue(ov.drink_growth)
        self.assertFalse(ov.drought)


if __name__ == "__main__":
    unittest.main()
