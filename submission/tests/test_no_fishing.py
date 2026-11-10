"""Offline regressions for the labour rule on open play: the labour plugin, no Fishery, a late Butchers, and the
refusal of the model's build_workshop calls for those two types. Stub game; no DF and no model.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from overseer.harness import DAY, Overseer  # noqa: E402,F401
from overseer.openplay import FEAST_BATCH, WILD_DAYS, WILD_REST  # noqa: E402,F401
from plain.harness import Plain  # noqa: E402,F401
from support import (BOX, E1, HATCH, HERD, Lockdown, StubGame, Task, WalkGame, bare, hold, locked,  # noqa: E402,F401
                     overseer, plain, resp, threat_resp)

from dfbench_client import ActionLimit, GameAPIError  # noqa: E402,F401


class NoFishing(unittest.TestCase):
    def test_a_fort_with_neither_workshop_gets_autolabor_and_no_fishery(self):
        ov, g = overseer(bare(336, 0))
        ov.management()
        ov.workshops()
        self.assertIs(ov.calm, True)
        self.assertEqual(g.tools("enable_automation"), [{"name": "autolabor"}])
        self.assertEqual(g.tools("build_workshop"), [])          # no Fishery for the catch, no Butchers yet

    def test_autolabor_that_is_on_is_left_alone(self):
        r = bare(300, 36)
        r["observation"]["plugins"]["autolabor"] = "on"
        ov, g = overseer(r)
        ov.management()
        ov.workshops()
        self.assertIs(ov.calm, True)
        self.assertEqual(g.tools("enable_automation"), [])
        self.assertEqual(g.tools("build_workshop"), [])

    def test_butchers_waits_for_the_feast_when_nobody_hunts(self):
        ov, g = overseer(bare(18, 318))
        ov.management()
        ov.workshops()
        self.assertEqual(g.tools("build_workshop"), [])
        ov.load(bare(17, 319))
        ov.management()
        ov.workshops()
        self.assertEqual(g.tools("build_workshop"), [{"type": "Butchers", "site": "W1"}])

    def test_a_hunger_cull_still_builds_the_butchers_at_once(self):
        ov, g = overseer(bare(200, 136))
        ov.management()
        ov.load(dict(bare(200, 136), **{}))
        ov.o["stocks"]["food_edible"] = 0
        ov.st = ov.o["stocks"]
        ov.provision()
        self.assertEqual(g.tools("build_workshop"), [{"type": "Butchers", "site": "W1"}])
        self.assertEqual(len(g.tools("slaughter")), 1)

    def test_a_fort_that_already_fishes_or_butchers_is_left_as_it_was(self):
        for have in ("Fishery", "Butchers"):
            ov, g = overseer(bare(336, 0, workshops=("Carpenters", "Still", "Kitchen", have)))
            ov.management()
            ov.workshops()
            self.assertIs(ov.calm, False)
            self.assertEqual(g.tools("enable_automation"), [])
            other = "Butchers" if have == "Fishery" else "Fishery"
            self.assertEqual(g.tools("build_workshop"), [{"type": other, "site": "W1"}])   # the inherited rules

    def test_the_choice_is_made_once(self):
        ov, g = overseer(bare(336, 0))
        ov.management()
        ov.load(bare(300, 36, workshops=("Carpenters", "Still", "Kitchen", "Fishery")))   # the model built one
        ov.management()
        ov.workshops()
        self.assertIs(ov.calm, True)
        self.assertEqual(g.tools("build_workshop"), [])

    def test_no_choice_is_made_without_the_workshop_list(self):
        r = bare(336, 0)
        r["observation"]["workshops"] = "ERR: scripted"
        ov, g = overseer(r)
        ov.management()
        self.assertIsNone(ov.calm)
        self.assertEqual(g.tools("enable_automation"), [])

    def test_a_reply_without_the_task_clock_builds_no_fishery(self):
        ov, g = overseer(bare(336, 0))
        ov.management()
        self.assertIs(ov.calm, True)
        r = bare(330, 6)                                                 # the fisher has not been reassigned yet
        del r["days_left"]
        ov.load(r)
        self.assertFalse(ov.open_play())
        ov.management()
        ov.workshops()
        self.assertEqual(g.tools("build_workshop"), [])

    def test_the_choice_is_made_on_a_first_reply_without_the_task_clock(self):
        r = bare(336, 0)
        del r["days_left"]
        ov, g = overseer(r)
        ov.management()
        ov.workshops()
        self.assertIs(ov.calm, True)
        self.assertEqual(g.tools("enable_automation"), [{"name": "autolabor"}])
        self.assertEqual(g.tools("build_workshop"), [])

    def test_lab_task_keeps_its_fishery(self):
        ov, g = overseer(bare(60, 0, hands_off=40))
        ov.management()
        ov.workshops()
        self.assertIsNone(ov.calm)
        self.assertFalse(ov.open_task())
        self.assertEqual(g.tools("enable_automation"), [])
        self.assertEqual(g.tools("build_workshop"), [{"type": "Fishery", "site": "W1"}])

    def test_autolabor_that_will_not_turn_on_gives_the_fishery_back(self):
        ov, g = overseer(bare(336, 0), refuse={("enable_automation", None)})
        for day in range(0, 6):
            ov.load(bare(336 - day, day))
            ov.management()
            ov.workshops()
        self.assertEqual(len(g.tools("enable_automation")), 5)
        self.assertIs(ov.calm, False)
        self.assertEqual(g.tools("build_workshop")[0], {"type": "Fishery", "site": "W1"})

    def test_nothing_is_built_for_the_catch_while_the_choice_is_still_to_be_made(self):
        r = bare(336, 0)
        r["observation"]["workshops"] = "ERR: scripted"
        ov, g = overseer(r)
        ov.management()
        ov.workshops()
        self.assertIsNone(ov.calm)
        self.assertNotIn({"type": "Fishery", "site": "W1"}, g.tools("build_workshop"))
        self.assertNotIn({"type": "Butchers", "site": "W1"}, g.tools("build_workshop"))
        ov.load(bare(335, 1))                                            # readable on the next pass
        ov.management()
        ov.workshops()
        self.assertIs(ov.calm, True)
        self.assertEqual(g.tools("enable_automation"), [{"name": "autolabor"}])
        self.assertNotIn({"type": "Fishery", "site": "W1"}, g.tools("build_workshop"))

    def test_the_model_cannot_build_them_while_the_choice_is_still_to_be_made(self):
        p = plain(WalkGame())
        self.assertIsNone(p.guard.calm)
        self.assertTrue(p.open_play())
        self.assertEqual(p.refuse("build_workshop", {"type": "Fishery", "site": "W2"}, 100 * DAY)["error_code"],
                         "layer_owned")
        p.guard.calm = True
        p.guard.days_left = None                                         # the task clock missing from a reply
        self.assertFalse(p.open_play())
        self.assertEqual(p.refuse("build_workshop", {"type": "Fishery", "site": "W2"}, 100 * DAY)["error_code"],
                         "layer_owned")
        lab = Plain(Task(), WalkGame(), model=None)
        lab.guard.set_task({"goal": "x", "hands_off": 39})
        lab.guard.load(resp(40, 20, food=60, hands_off=19))
        self.assertIsNone(lab.refuse("build_workshop", {"type": "Fishery", "site": "W2"}, 20 * DAY))

    def test_the_model_cannot_build_a_fishery_before_the_choice_even_without_the_task_clock(self):
        p = plain(WalkGame())
        self.assertIsNone(p.guard.calm)
        p.guard.days_left = None
        self.assertFalse(p.open_play())
        self.assertEqual(p.refuse("build_workshop", {"type": "Fishery", "site": "W2"}, 100 * DAY)["error_code"],
                         "layer_owned")

    def test_the_model_cannot_build_the_two_workshops_meanwhile(self):
        p = plain(WalkGame())
        p.guard.calm = True
        for kind in ("Fishery", "Butchers"):
            out = p.refuse("build_workshop", {"type": kind, "site": "W2"}, 100 * DAY)
            self.assertEqual(out["error_code"], "layer_owned")
        self.assertIsNone(p.refuse("build_workshop", {"type": "Still", "site": "W2"}, 100 * DAY))
        p.guard.calm = False
        self.assertIsNone(p.refuse("build_workshop", {"type": "Fishery", "site": "W2"}, 100 * DAY))


if __name__ == "__main__":
    unittest.main()
