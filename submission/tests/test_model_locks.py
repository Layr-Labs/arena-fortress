"""Offline regressions for the refusal of the model's own lock_door calls on open play: calls that would shut a
way to the surface, and calls that would undo a standing lockdown. Stub game; no DF and no model.
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


class ModelLocks(Lockdown, unittest.TestCase):
    def test_the_model_cannot_open_a_stair_hatch_this_layer_has_not_locked_yet(self):
        other = dict(HATCH, id=15, x=120, y=100)
        ov, g = self.play(threat_resp(190, 30, alert=True, inside=10, doors=locked(14) + [other]),
                          lock=hold(186), own_locks={14}, stairs={"E1": (92, 100, 153), "E2": (120, 100, 153)})
        self.assertTrue(ov.owns_lock({"locked": True, "door_id": 15}))   # a second stair's hatch, not yet owned
        self.assertFalse(ov.owns_lock({"locked": True, "door_id": 30}))

    def test_which_model_lock_calls_would_undo_a_lockdown(self):
        ov, g = self.play(threat_resp(190, 30, alert=True, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14})
        self.assertTrue(ov.owns_lock({"locked": False}))             # every door at once
        self.assertTrue(ov.owns_lock({"locked": False, "door_id": 14}))
        self.assertFalse(ov.owns_lock({"locked": True, "door_id": 30}))
        ov, g = self.play(threat_resp(190, None))
        self.assertFalse(ov.owns_lock({"locked": True}))             # no lockdown: the doors are the model's

    def test_the_model_cannot_shut_a_surface_stair_itself(self):
        mine = {"id": 30, "kind": "door", "built": True, "locked": False, "x": 95, "y": 101, "z": 151}
        ov, g = self.play(threat_resp(190, None, doors=(HATCH, mine)))
        self.assertIsNone(ov.lock)
        self.assertTrue(ov.seals_stair({"locked": True}))                    # every door at once
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 14}))     # the hatch on the stair
        self.assertFalse(ov.seals_stair({"locked": True, "door_id": 30}))    # its own door somewhere else
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 99}))     # not in the list: it cannot be placed
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": "14"}))
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": True}))
        self.assertFalse(ov.seals_stair({"locked": False}))                  # opening is never refused here
        self.assertFalse(ov.seals_stair({"locked": False, "door_id": 14}))
        self.assertEqual(g.tools("lock_door"), [])

    def test_a_door_of_any_kind_on_a_stair_that_left_the_list_still_counts(self):
        door = {"id": 21, "kind": "door", "built": True, "locked": False, "x": 92, "y": 100, "z": 153}
        ov, g = self.play(threat_resp(190, None))
        self.again(ov, g, threat_resp(192, None, doors=(door,), sites=()))
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 21}))

    def test_the_guard_on_the_stairs_outlives_a_reply_without_the_task_clock(self):
        ov, g = self.play(threat_resp(190, None))
        r = threat_resp(192, None)
        del r["days_left"]
        self.again(ov, g, r)
        self.assertFalse(ov.open_play())
        self.assertTrue(ov.seals_stair({"locked": True}))
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 14}))

    def test_a_hatch_on_the_surface_that_no_stair_list_has_is_not_locked_for_the_model(self):
        far = dict(HATCH, id=77, x=131)                  # a surface stair outside the 30 tiles the stair list covers
        deep = {"id": 30, "kind": "hatch", "built": True, "locked": False, "x": 95, "y": 101, "z": 151}
        ov, g = self.play(threat_resp(100, None, doors=(far, deep), sites=()))
        self.assertEqual(ov.stairs, {})
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 77}))
        self.assertFalse(ov.seals_stair({"locked": True, "door_id": 30}))    # below the surface: the model's own
        hill = dict(far, id=78, z=155)
        self.again(ov, g, threat_resp(102, None, doors=(far, deep, hill), sites=()))
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 78}))     # above the wagon's level too

    def test_the_surface_level_is_remembered_through_a_reply_without_it(self):
        far = dict(HATCH, id=77, x=131)
        deep = {"id": 30, "kind": "door", "built": True, "locked": False, "x": 95, "y": 101, "z": 151}
        ov, g = self.play(threat_resp(100, None, doors=(far, deep), sites=()))
        r = threat_resp(102, None, doors=(far, deep), sites=())
        del r["observation"]["map"]["surface_z"]
        self.again(ov, g, r)
        self.assertEqual(ov.surface_seen, 153)
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 77}))
        self.assertFalse(ov.seals_stair({"locked": True, "door_id": 30}))

    def test_without_a_surface_level_no_lock_is_passed_on(self):
        deep = {"id": 30, "kind": "door", "built": True, "locked": False, "x": 95, "y": 101, "z": 151}
        r = threat_resp(100, None, doors=(HATCH, deep))
        del r["observation"]["map"]["surface_z"]
        ov, g = self.play(r)
        self.assertIsNone(ov.surface_seen)
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 30}))
        self.assertFalse(ov.seals_stair({"locked": False, "door_id": 30}))

    def test_the_guard_on_the_stairs_is_up_before_any_stair_is_known_and_without_the_clock(self):
        r = threat_resp(100, None, sites=())
        del r["days_left"]
        ov, g = self.play(r)
        self.assertEqual(ov.stairs, {})
        self.assertFalse(ov.open_play())
        self.assertTrue(ov.open_task())
        self.assertTrue(ov.seals_stair({"locked": True}))

    def test_without_a_door_list_no_lock_is_passed_on(self):
        ov, g = self.play(threat_resp(190, None, drop=("doors",)))
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 30}))
        self.assertFalse(ov.seals_stair({"locked": False, "door_id": 30}))

    def test_on_a_lab_task_the_doors_stay_the_models(self):
        r = threat_resp(30, None)
        r["hands_off_in_days"] = 9
        ov, g = self.play(r)
        self.assertFalse(ov.seals_stair({"locked": True}))
        self.assertFalse(ov.seals_stair({"locked": True, "door_id": 14}))

    def test_the_model_cannot_lock_a_surface_stair_on_open_play(self):
        p = plain(WalkGame())
        r = threat_resp(100, None)
        p.guard.load(r); p.guard.count = 0
        p.guard.defend()
        self.assertTrue(p.open_play())
        self.assertFalse(p.guard_holds())
        for args in ({"locked": True}, {"locked": True, "door_id": 14}, {"locked": True, "door_id": 77}):
            self.assertEqual(p.refuse("lock_door", args, 100 * DAY)["error_code"], "layer_owned")
        self.assertIsNone(p.refuse("lock_door", {"locked": False}, 100 * DAY))
        self.assertIsNone(p.refuse("lock_door", {"locked": False, "door_id": 14}, 100 * DAY))
        lab = Plain(Task(), WalkGame(), model=None)
        lab.guard.set_task({"goal": "x", "hands_off": 39})
        lab.guard.load(resp(40, 20, food=60, hands_off=19))
        self.assertIsNone(lab.refuse("lock_door", {"locked": True}, 20 * DAY))


if __name__ == "__main__":
    unittest.main()
