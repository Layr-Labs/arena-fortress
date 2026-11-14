"""d67/d69: (a) the drought lab (LT01: its goal asks for a brew and nothing of food) plays without fishing, as open
play does; LT02 and LT08 count food every day of their window, and in LT03 the labour plugin's day-0 reshuffle once
left the mood's workshop unbuilt (plan y67), so those three fish as before. (b) After a lockdown that
ran its full length the fort has WILD_REST_FAR days above ground: none at all may start in the first WILD_REST, and
after that only a hostile within WILD_NEAR_REST of the wagon ends the rest. Leader's code on OP1 fort 1004 (plan
x66): harpies 53 tiles out from day 202 to the end, six 20-day lockdowns one day apart, three dead of thirst."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import Lockdown, bare, hold, locked, overseer, threat_resp  # noqa: E402
from overseer.harness import DAY  # noqa: E402
from overseer.openplay import WILD_DAYS, WILD_NEAR, WILD_NEAR_REST, WILD_REST, WILD_REST_FAR  # noqa: E402

LT01 = ("From day 39 you can't act for 21 days. Keep drink in stock every day of that window, brew at least one batch "
        "of drink inside it, and end with at least one drink per dwarf. No dwarf may die.")
LT02 = ("From day 69 you can't act for 21 days. Keep drink in stock every day of that window, with your own built "
        "Still and a planted farm plot, and keep food in stock every day of that window too. No dwarf may die.")
LT03 = ("A dwarf has been taken by a strange mood. The artifact must be finished and the dwarf sane and alive at the "
        "end (day 45). No dwarf may die.")
LT08 = ("Migrants are arriving. From day 39 you can't act for 21 days. By day 60 every dwarf must have a placed bed, "
        "drink and food must be in stock every day from day 39, and drink must not end lower than it was on day 39. "
        "No dwarf may die.")


def built(g):
    return [a.get("type") for a in g.tools("build_workshop")]


class Quiet:
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)


class LabFishing(Quiet, unittest.TestCase):
    def play(self, goal, **kw):
        ov, g = overseer(bare(51, 9, hands_off=30, **kw))
        ov.set_task({"goal": goal, "hands_off": {"from_day": 39}})
        self.assertFalse(ov.open_task())
        ov.management()
        ov.workshops()
        return ov, g

    def test_the_drought_lab_gets_autolabor_and_no_fishery(self):
        ov, g = self.play(LT01)
        self.assertTrue(ov.lab_no_fish)
        self.assertIs(ov.calm, True)
        self.assertEqual(g.tools("enable_automation"), [{"name": "autolabor"}])
        self.assertNotIn("Fishery", built(g))

    def test_the_other_labs_fish_as_before(self):
        for goal in (LT02, LT03, LT08):
            ov, g = self.play(goal)
            self.assertFalse(ov.lab_no_fish)
            self.assertIsNone(ov.calm)
            self.assertEqual(g.tools("enable_automation"), [])
            self.assertIn("Fishery", built(g))

    def test_a_lab_whose_goal_is_unknown_is_left_as_it_was(self):
        ov, g = self.play("")
        self.assertFalse(ov.lab_no_fish)
        self.assertEqual(g.tools("enable_automation"), [])
        self.assertIn("Fishery", built(g))

    def test_a_lab_fort_that_already_has_a_fishery_is_left_alone(self):
        ov, g = self.play(LT01, workshops=("Carpenters", "Still", "Kitchen", "Fishery"))
        self.assertIs(ov.calm, False)
        self.assertEqual(g.tools("enable_automation"), [])

    def test_open_play_is_unchanged(self):
        ov, g = overseer(bare(336, 0))
        self.assertFalse(ov.lab_no_fish)
        ov.management()
        ov.workshops()
        self.assertIs(ov.calm, True)
        self.assertEqual(g.tools("enable_automation"), [{"name": "autolabor"}])
        self.assertNotIn("Fishery", built(g))


class FarRest(Quiet, Lockdown, unittest.TestCase):
    def test_the_constants(self):
        self.assertTrue(0 < WILD_REST < WILD_REST_FAR)
        self.assertTrue(0 < WILD_NEAR_REST < WILD_NEAR)

    def capped(self, dist=53):
        day = 100 + WILD_DAYS
        ov, g = self.play(threat_resp(day, dist, alert=True, inside=10, doors=locked(14)), lock=hold(100),
                          own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)
        self.assertEqual((ov.rest_until, ov.rest_far_until), ((day + WILD_REST) * DAY, (day + WILD_REST_FAR) * DAY))
        return ov, g, day

    def test_a_hostile_that_keeps_its_distance_does_not_end_the_rest(self):
        ov, g, day = self.capped()
        self.again(ov, g, threat_resp(day + WILD_REST, 53))
        self.assertEqual(len(g.tools("civilian_alert")), 1)          # still above ground
        self.again(ov, g, threat_resp(day + WILD_REST_FAR - 1, WILD_NEAR_REST + 1))
        self.assertEqual(len(g.tools("civilian_alert")), 1)
        self.again(ov, g, threat_resp(day + WILD_REST_FAR, 53))      # the rest is over: shut again
        self.assertEqual(g.tools("civilian_alert")[-1], {"on": True})

    def test_a_close_hostile_ends_it_after_the_first_day(self):
        ov, g, day = self.capped()
        r = threat_resp(day, 10)
        r["tick"] = r["observation"]["date"]["abs_tick"] = day * DAY + DAY // 2      # half a day later
        self.again(ov, g, r)
        self.assertEqual(len(g.tools("civilian_alert")), 1)          # the first day stays above ground, as before
        self.again(ov, g, threat_resp(day + WILD_REST, WILD_NEAR_REST))
        self.assertEqual(g.tools("civilian_alert")[-1], {"on": True})

    def test_a_lockdown_that_ended_early_owes_no_rest(self):
        ov, g = self.play(threat_resp(105, None, n=0, alert=True, inside=10, doors=locked(14)), lock=hold(100),
                          own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual((ov.rest_until, ov.rest_far_until), (0, 0))
        self.again(ov, g, threat_resp(106, 53))
        self.assertEqual(g.tools("civilian_alert")[-1], {"on": True})


if __name__ == "__main__":
    unittest.main()
