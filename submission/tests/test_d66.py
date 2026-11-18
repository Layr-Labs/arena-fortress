"""d66: on the drought task's drink-only goal (LT01) the window brew floor is one plant and the prep starts 21
days out. The task's predicates read drink only (no clause on food), so keeping plants back as food - the reason
for max(3, cit // 2) on the other labs - costs nothing there and starves the brewer. Measured on two official
draws: one private LT01 game in eight ran its drink dry mid-window (partial 0.28 in the worse draw) while every
public fort passed 6 of 6. The other labs keep the old floor and the old 14-day prep exactly."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402
from overseer.harness import WINDOW_PREP_DAYS  # noqa: E402

DROUGHT = {"goal": "From day 39 you can't act for 21 days. Keep drink in stock every day of that window, brew at "
                   "least one batch of drink inside it, and end with at least one drink per dwarf. No dwarf may die.",
           "days": 60, "hands_off": 21}
RESCUE = {"goal": "From day 69 you can't act for 21 days. Keep drink and food in stock every day of that window.",
          "days": 90, "hands_off": 21}


def tasks(goal, days, hands_off):
    r = resp(hands_off, days - hands_off, food=60, cit=14, hands_off=hands_off)
    ov, g = overseer(r)
    ov.set_task(goal)
    return ov, g


class D66(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def brew(self, ov, g):
        ov.closer()
        return [a for a in g.tools("add_order") if a.get("recipe") == "brew_drink"]

    def test_the_drought_goal_brews_from_one_plant(self):
        ov, g = tasks(DROUGHT, 60, 21)
        b = self.brew(ov, g)
        self.assertIn({"stock": "plants_brewable", "at_least": 1}, b[0]["when"])

    def test_the_rescue_goal_keeps_the_food_floor(self):
        ov, g = tasks(RESCUE, 90, 14)          # inside the old 14-day prep
        b = self.brew(ov, g)
        self.assertIn({"stock": "plants_brewable", "at_least": max(3, 14 // 2)}, b[0]["when"])

    def test_the_drought_goal_preps_three_weeks_out(self):
        ov, _ = tasks(DROUGHT, 60, 21)
        ov.hands_off = 18
        self.assertTrue(ov.in_window_prep())          # 18 days: inside the d66 run-up, outside the old 14
        self.assertGreater(18, WINDOW_PREP_DAYS)

    def test_the_other_labs_keep_the_fourteen_day_prep(self):
        ov, _ = tasks(RESCUE, 90, 14)
        ov.hands_off = 18                     # 18 days: inside the drought run-up, outside the old 14
        self.assertFalse(ov.in_window_prep())


if __name__ == "__main__":
    unittest.main()
