"""Offline regressions for the first felling on open play: the tree-felling plugin is not enabled while a large
predator is in sight, and is enabled for good when it has left, when time, drink or food runs short, or when the
look fails twice. Stub game; no DF and no model.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from overseer.harness import DAY, Overseer  # noqa: E402,F401
from overseer.openplay import FELL_WAIT_DAYS  # noqa: E402
from plain.harness import Plain  # noqa: E402
from support import StubGame, Task, WalkGame, overseer, plain, resp  # noqa: E402

GATOR = {"id": 500, "race": "ALLIGATOR", "hostile": False, "x": 60, "y": 97, "z": 131}
OTTER = {"id": 501, "race": "RIVER OTTER", "hostile": False, "x": 70, "y": 97, "z": 131}


def fresh(day, others=(), chop="off", **kw):
    """A fort on its first days: the felling plugin off, the given creatures in sight."""
    r = resp(336 - day, day, food=kw.pop("food", 60), drink=kw.pop("drink", 60), cit=7, workshops=(), **kw)
    r["observation"]["plugins"] = {"autochop": chop, "seedwatch": "on", "autofarm": "on", "autolabor": "on"}
    ov, g = overseer(r)
    g.others = list(others)
    return ov, g, r


def chop(g):
    return {"name": "autochop"} in g.tools("enable_automation")


class FirstFelling(unittest.TestCase):
    def test_no_predator_in_sight_and_the_trees_are_felled_at_once(self):
        ov, g, _ = fresh(0, others=(OTTER,))
        ov.management()
        self.assertTrue(chop(g))
        self.assertIs(ov.fell, False)

    def test_an_alligator_in_sight_and_the_felling_waits(self):
        ov, g, _ = fresh(0, others=(GATOR, OTTER))
        ov.management()
        self.assertFalse(chop(g))
        self.assertIsInstance(ov.fell, dict)
        self.assertIn("others", g.asked)

    def test_it_starts_when_the_alligator_has_left_and_does_not_wait_again(self):
        ov, g, _ = fresh(0, others=(GATOR,))
        ov.management()
        g.others = []
        r = resp(326, 10, food=50, drink=60, cit=7, workshops=())
        r["observation"]["plugins"]["autochop"] = "off"
        ov.load(r)
        ov.management()
        self.assertTrue(chop(g))
        self.assertIs(ov.fell, False)
        g.others = [GATOR]                                  # back again, and the plugin reported off once more
        n = len(g.asked)
        ov.load(r)
        ov.management()
        self.assertEqual(len(g.asked), n)                   # no further look: the wait is over for good

    def test_it_waits_no_longer_than_the_limit(self):
        ov, g, _ = fresh(0, others=(GATOR,))
        ov.management()
        r = resp(336 - FELL_WAIT_DAYS + 1, FELL_WAIT_DAYS - 1, food=60, drink=60, cit=7, workshops=())
        r["observation"]["plugins"]["autochop"] = "off"
        ov.load(r)
        ov.management()
        self.assertFalse(chop(g))
        r = resp(336 - FELL_WAIT_DAYS, FELL_WAIT_DAYS, food=60, drink=60, cit=7, workshops=())
        r["observation"]["plugins"]["autochop"] = "off"
        ov.load(r)
        ov.management()
        self.assertTrue(chop(g))

    def test_short_drink_or_food_ends_the_wait(self):
        for stock in ({"drink": 27}, {"food": 13}):
            ov, g, _ = fresh(0, others=(GATOR,))
            ov.management()
            self.assertFalse(chop(g))
            r = resp(316, 20, cit=7, workshops=(), **{"food": 60, "drink": 60, **stock})
            r["observation"]["plugins"]["autochop"] = "off"
            ov.load(r)
            ov.management()
            self.assertTrue(chop(g), stock)

    def test_one_failed_look_waits_and_a_second_does_not(self):
        ov, g, _ = fresh(0)
        g.query_error = True
        ov.management()
        self.assertFalse(chop(g))
        ov.load(resp(334, 2, food=60, drink=60, cit=7, workshops=()) | {})
        ov.o["plugins"]["autochop"] = "off"
        ov.management()
        self.assertTrue(chop(g))

    def test_a_look_that_breaks_in_an_unforeseen_way_does_not_stop_the_pass(self):
        ov, g, _ = fresh(0, others=(GATOR,))
        g.query = lambda *a, **kw: (_ for _ in ()).throw(TypeError("unforeseen"))
        ov.management()                                     # no exception: the look counts as failed
        self.assertFalse(chop(g))
        self.assertEqual(ov.fell["blind"], 1)

    def test_a_visitor_of_that_kind_is_not_waited_for(self):
        ov, g, _ = fresh(0, others=(dict(GATOR, visitor=True),))
        ov.management()
        self.assertTrue(chop(g))

    def test_a_fort_that_is_felling_already_is_not_looked_at(self):
        ov, g, _ = fresh(0, others=(GATOR,), chop="on")
        ov.management()
        self.assertNotIn("others", getattr(g, "asked", []))
        self.assertIsNone(ov.fell)

    def test_a_lab_task_fells_at_once_without_a_look(self):
        r = resp(60, 0, food=60, drink=60, cit=7, workshops=(), hands_off=40)
        r["observation"]["plugins"]["autochop"] = "off"
        g = StubGame()
        g.others = [GATOR]
        ov = Overseer(g, goal="x", days=60)
        ov.set_task({"goal": "x", "hands_off": 39})
        ov.load(r)
        ov.count = 0
        ov.management()
        self.assertTrue(chop(g))
        self.assertNotIn("others", getattr(g, "asked", []))

    def test_the_model_cannot_start_the_felling_during_the_wait(self):
        p = plain(WalkGame())
        p.guard.fell = {"since": 0, "blind": 0}
        out = p.refuse("enable_automation", {"name": "autochop"}, 2 * DAY)
        self.assertEqual(out["error_code"], "layer_owned")
        self.assertIsNone(p.refuse("enable_automation", {"name": "autofarm"}, 2 * DAY))
        p.guard.fell = False
        self.assertIsNone(p.refuse("enable_automation", {"name": "autochop"}, 2 * DAY))
        lab = Plain(Task(), WalkGame(), model=None)
        self.assertIsNone(lab.refuse("enable_automation", {"name": "autochop"}, 2 * DAY))


if __name__ == "__main__":
    unittest.main()
