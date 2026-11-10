"""Offline regressions for the wildlife lockdown on open play: when it starts, how the stair hatches are locked,
each way it ends, the invader rule beside it, and the upkeep of hatches and shelter. Stub game; no DF and no
model. The regressions for refused and unanswered calls and unreadable observations are kept with the study.
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


class Wildlife(Lockdown, unittest.TestCase):
    def test_nearby_wildlife_starts_a_lockdown_when_the_fort_can_be_shut(self):
        ov, g = self.play(threat_resp(186, 74))
        self.assertEqual(g.tools("civilian_alert"), [{"on": True}])
        self.assertEqual((ov.lock["since"], ov.lock["phase"]), (186 * DAY, "hold"))
        self.assertEqual(g.tools("lock_door"), [])                   # nobody is inside yet and no day has passed

    def test_everyone_already_inside_is_locked_in_the_same_pass(self):
        ov, g = self.play(threat_resp(186, 74, inside=10))
        self.assertEqual(g.tools("civilian_alert"), [{"on": True}])
        self.assertEqual(g.tools("lock_door"), [{"locked": True, "door_id": 14}])

    def test_distant_wildlife_does_not(self):
        ov, g = self.play(threat_resp(184, 141))
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_no_lockdown_unless_every_stair_has_its_own_built_hatch(self):
        for doors, sites in (((), (E1,)),                                             # no hatch at all
                             ((dict(HATCH, built=False),), (E1,)),                     # placed, not built
                             ((HATCH,), (E1, dict(E1, id="E2", x=98))),               # a second stair is open
                             ((dict(HATCH, x=98),), (E1,)),                           # a hatch, but somewhere else
                             ((HATCH,), None),                                        # no site list this pass
                             ((HATCH,), [dict(E1, id="E%d" % i, x=60 + i) for i in range(8)])):   # list at its cap
            ov, g = self.play(threat_resp(186, 74, doors=doors, sites=sites))
            self.assertEqual(g.tools("civilian_alert"), [], (doors, sites))
            self.assertIsNone(ov.lock)

    def test_a_stair_that_dropped_out_of_the_list_still_needs_its_hatch(self):
        ov, g = self.play(threat_resp(100, None, sites=(E1, dict(E1, id="E2", x=98))))
        self.again(ov, g, threat_resp(186, 74, sites=(E1,)))         # E2 is no longer listed and has no hatch
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_no_lockdown_into_a_shelter_that_is_too_small(self):
        ov, g = self.play(threat_resp(186, 74, tiles=1))
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_no_lockdown_when_the_hostile_list_is_cut_short(self):
        r = threat_resp(186, 74, n=3)
        r["observation"]["threats"]["visible_hostiles"] = 21         # more in sight than listed
        ov, g = self.play(r)
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_no_lockdown_on_an_incomplete_observation(self):
        for name in ("threats", "burrows", "doors"):
            ov, g = self.play(threat_resp(186, 74, drop=(name,)))
            self.assertEqual(g.tools("civilian_alert"), [], name)

    def test_a_refused_start_is_not_a_lockdown(self):
        ov, g = self.play(threat_resp(186, 74), refuse={("civilian_alert", None)})
        self.assertEqual(g.tools("civilian_alert"), [{"on": True}])
        self.assertIsNone(ov.lock)

    def test_lab_task_keeps_the_inherited_rule(self):
        r = threat_resp(30, 20)
        r["hands_off_in_days"] = 9
        ov, g = self.play(r)
        self.assertEqual(g.calls, [])                                # not an invader: nothing, as before

    def test_only_the_stair_hatch_is_locked_and_only_by_id(self):
        ov, g = self.play(threat_resp(187, 30, alert=True, inside=9, doors=locked(30)), lock=hold(186))
        self.assertEqual(g.tools("lock_door"), [{"locked": True, "door_id": 14}])     # door 30 is not this layer's
        self.assertEqual(ov.own_locks, {14})

    def test_locking_waits_for_the_civilians_or_a_day(self):
        ov, g = self.play(threat_resp(186, 30, alert=True, inside=5), lock=hold(186))
        self.assertEqual(g.tools("lock_door"), [])
        self.again(ov, g, threat_resp(187, 30, alert=True, inside=5))
        self.assertEqual(g.tools("lock_door"), [{"locked": True, "door_id": 14}])

    def test_a_lock_whose_answer_was_lost_is_still_owned(self):
        class Lost(StubGame):
            def act(self, tool, args):
                if tool == "lock_door" and args.get("locked"):
                    self.calls.append((tool, dict(args)))
                    raise GameAPIError("no answer")
                return super().act(tool, args)
        g = Lost()
        ov = Overseer(g, goal="Run the fortress", days=336)
        ov.set_task({"goal": "Run the fortress for 336 days."})
        ov.lock = hold(186)
        ov.step(threat_resp(187, 30, alert=True, inside=10))         # step() swallows the error, as in play
        self.assertEqual(ov.own_locks, {14})                         # sent, unanswered: it must be undone later

    def test_a_hatch_that_will_not_lock_ends_the_lockdown_for_good(self):
        ov, g = self.play(threat_resp(187, 30, alert=True, inside=10), lock=hold(186),
                          refuse={("lock_door", None)})
        self.assertEqual(ov.own_locks, set())                        # refused outright: nothing to undo
        self.again(ov, g, threat_resp(188, 30, alert=True, inside=10))
        self.assertEqual(ov.lock["phase"], "hold")                   # one more try
        self.again(ov, g, threat_resp(189, 30, alert=True, inside=10))
        self.assertIsNone(ov.lock)                                   # given up: alert off, nothing was locked
        self.assertTrue(ov.wild_off)
        self.assertEqual(g.tools("civilian_alert")[-1], {"on": False})

    def test_squad_is_stood_down_only_during_a_hold(self):
        squad = {"squads": [{"id": 1, "uniform": "leather", "armed": 2, "orders": [{"order": "attack"}]}]}
        r = threat_resp(187, 30, alert=True, inside=10, doors=locked(14))
        r["observation"]["military"] = squad
        ov, g = self.play(r, lock=hold(186), own_locks={14})
        self.assertEqual(g.tools("squad_order"), [{"order": "stand_down"}])
        r = threat_resp(187, 140)                                    # in sight but far: the inherited rule stands
        r["observation"]["military"] = {"squads": [{"id": 1, "uniform": "leather", "armed": 2, "orders": []}]}
        ov, g = self.play(r)
        self.assertEqual(g.tools("squad_order"), [{"order": "attack"}])

    def test_a_failed_section_is_not_read_as_safe(self):
        for name in ("threats", "burrows", "doors"):
            ov, g = self.play(threat_resp(190, 30, alert=True, inside=10, doors=locked(14), drop=(name,)),
                              lock=hold(186), own_locks={14})
            self.assertEqual(g.tools("civilian_alert") + g.tools("lock_door"), [], name)
            self.assertEqual((ov.lock["phase"], ov.own_locks), ("hold", {14}), name)

    def test_ends_and_unlocks_when_the_wildlife_has_gone(self):
        ov, g = self.play(threat_resp(190, 150, alert=True, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)
        self.assertEqual((ov.rest_until, ov.wild_off), (0, False))

    def test_a_refused_clear_keeps_the_hatch_shut_and_is_carried_through(self):
        ov, g = self.play(threat_resp(207, 30, alert=True, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14}, refuse={("civilian_alert", None)})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [])                   # still confined: do not open the stair
        self.assertEqual((ov.lock["since"], ov.lock["phase"], ov.lock["why"]), (186 * DAY, "release", "cap"))
        g.refuse = set()
        self.again(ov, g, threat_resp(208, 30, alert=True, inside=10, doors=locked(14)))
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)
        self.assertEqual(ov.rest_until, (208 + WILD_REST) * DAY)

    def test_a_decided_release_is_not_undone_when_its_reason_passes(self):
        ov, g = self.play(threat_resp(190, 5, alert=True, inside=10, doors=locked(14), at=(95, 101, 151)),
                          lock=hold(186), own_locks={14}, refuse={("civilian_alert", None)})
        self.assertTrue(ov.wild_off)                                 # decided at once, whatever the API answered
        self.assertEqual(ov.lock["why"], "inside")
        g.refuse = set()
        self.again(ov, g, threat_resp(191, 30, alert=True, inside=10, doors=locked(14)))     # it has moved out
        self.assertEqual(g.tools("civilian_alert")[-1], {"on": False})
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)

    def test_a_refused_unlock_blocks_a_new_lockdown_until_it_is_done(self):
        ov, g = self.play(threat_resp(190, 150, alert=True, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14}, refuse={("lock_door", None)})
        self.assertEqual(ov.lock["phase"], "release")                # alert off, hatch still shut
        self.again(ov, g, threat_resp(191, 30, alert=False, inside=10, doors=locked(14)))    # it is back already
        self.assertEqual(len(g.tools("civilian_alert")), 1)          # no new lockdown over an unfinished release
        g.refuse = set()
        self.again(ov, g, threat_resp(192, 30, alert=False, inside=10, doors=locked(14)))
        self.assertEqual(g.tools("lock_door")[-1], {"locked": False, "door_id": 14})
        self.assertIsNone(ov.lock)
        self.again(ov, g, threat_resp(193, 30, alert=False, inside=10))
        self.assertEqual(g.tools("civilian_alert")[-1], {"on": True})

    def test_a_missing_door_list_does_not_forget_a_lock(self):
        ov, g = self.play(threat_resp(206, 30, alert=True, inside=10, doors=locked(14), drop=("doors",)),
                          lock=hold(186), own_locks={14})                 # day 20: the cap needs no observation
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])     # sent blind, by id
        self.assertIsNone(ov.lock)
        ov, g = self.play(threat_resp(206, 30, alert=True, inside=10, doors=locked(14), drop=("doors",)),
                          lock=hold(186), own_locks={14}, refuse={("lock_door", None)})
        self.assertEqual(ov.own_locks, {14})                         # refused and unseen: still owed

    def test_cap_then_a_day_above_ground_then_it_may_start_again(self):
        day = 100 + WILD_DAYS
        ov, g = self.play(threat_resp(day, 10, alert=True, inside=10, doors=locked(14)), lock=hold(100),
                          own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertEqual(ov.rest_until, (day + WILD_REST) * DAY)
        r = threat_resp(day, 10)
        r["tick"] = r["observation"]["date"]["abs_tick"] = day * DAY + DAY // 2      # half a day later
        self.again(ov, g, r)
        self.assertEqual(len(g.tools("civilian_alert")), 1)          # owed its day above ground
        self.again(ov, g, threat_resp(day + WILD_REST, 10))
        self.assertEqual(g.tools("civilian_alert")[-1], {"on": True})

    def test_a_lockdown_that_ended_early_owes_no_time_above_ground(self):
        ov, g = self.play(threat_resp(105, None, n=0, alert=True, inside=10, doors=locked(14)), lock=hold(100),
                          own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(ov.rest_until, 0)
        self.again(ov, g, threat_resp(106, 40))
        self.assertEqual(g.tools("civilian_alert")[-1], {"on": True})

    def test_a_hostile_inside_the_shelter_ends_it_for_good(self):
        ov, g = self.play(threat_resp(190, 5, alert=True, inside=10, doors=locked(14), at=(95, 101, 151)),
                          lock=hold(186), own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertTrue(ov.wild_off)
        self.again(ov, g, threat_resp(192, 30))
        self.assertEqual(len(g.tools("civilian_alert")), 1)          # no second lockdown this game

    def test_a_lost_seal_ends_it_for_good(self):
        ov, g = self.play(threat_resp(190, 30, alert=True, inside=10, doors=()), lock=hold(186), own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertTrue(ov.wild_off)
        self.assertEqual(ov.own_locks, set())                        # a complete list without it: it is gone

    def test_an_alert_switched_off_by_something_else_ends_it(self):
        ov, g = self.play(threat_resp(190, 30, alert=False, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [])              # already off: nothing to clear
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)

    def test_invaders_take_the_alert_over_and_the_stair_stays_shut_until_it_ends(self):
        ov, g = self.play(threat_resp(190, 30, invader=True, alert=True, inside=10, doors=locked(14)),
                          lock=hold(186), own_locks={14})
        self.assertEqual(g.tools("civilian_alert") + g.tools("lock_door"), [])     # alert on, hatch shut
        self.assertEqual((ov.lock["why"], ov.alert_since), ("invaders", 186 * DAY))
        self.again(ov, g, threat_resp(197, 30, invader=True, alert=True, inside=10, doors=locked(14)))
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])     # ten days from the start, as inherited
        self.assertEqual(g.tools("lock_door"), [])
        self.again(ov, g, threat_resp(198, None, alert=False, inside=10, doors=locked(14)))
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)

    def test_invaders_among_more_hostiles_than_are_listed_still_take_over(self):
        r = threat_resp(190, 30, alert=True, inside=10, doors=locked(14))
        r["observation"]["threats"]["by_race"]["GOBLIN"] = {"n": 1, "invader": True}     # not in the cut list
        ov, g = self.play(r, lock=hold(186), own_locks={14})
        self.assertEqual(ov.lock["why"], "invaders")

    def test_invaders_alone_are_handled_as_before(self):
        ov, g = self.play(threat_resp(186, 40, invader=True))
        self.assertEqual(g.tools("civilian_alert"), [{"on": True}])
        self.assertIsNone(ov.lock)
        self.assertEqual(g.tools("lock_door"), [])
        ov, g = self.play(threat_resp(186, 80, invader=True))        # invaders: only within 45 tiles
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_a_lock_this_layer_did_not_make_is_left_alone(self):
        ov, g = self.play(threat_resp(190, 20, invader=True, alert=True, inside=10, doors=locked(14, 30)),
                          alert_since=188 * DAY)
        self.assertEqual(g.tools("lock_door"), [])
        ov, g = self.play(threat_resp(190, None, doors=locked(14, 30)))
        self.assertEqual(g.tools("lock_door"), [])

    def test_shelter_grows_with_the_dig_and_refusals_are_retried(self):
        a = {"id": "A1", "kind": "A", "z": 150, "open_tiles": 40}
        ov, g = self.play(threat_resp(50, None, sites=(E1, a)), refuse={("create_burrow", None)})
        for day in (56, 62, 68):
            self.again(ov, g, threat_resp(day, None, sites=(E1, a)))
        self.assertEqual(len(g.tools("create_burrow")), 4)           # four refusals: still trying
        self.assertEqual(ov.sheltered, {})
        g.refuse = set()
        self.again(ov, g, threat_resp(74, None, sites=(E1, a)))
        self.assertEqual(ov.sheltered, {"A1": 40})
        self.again(ov, g, threat_resp(80, None, sites=(E1, dict(a, open_tiles=45))))
        self.assertEqual(len(g.tools("create_burrow")), 5)           # five more tiles: not worth another call
        self.again(ov, g, threat_resp(86, None, sites=(E1, dict(a, open_tiles=90))))
        self.assertEqual(len(g.tools("create_burrow")), 6)

    def test_hatch_cover_is_ordered_then_placed_on_the_surface_stair(self):
        ov, g = self.play(threat_resp(20, None, doors=()))
        self.assertEqual(g.tools("add_order"), [{"recipe": "make_hatch_cover", "amount": 1}])
        ov, g = self.play(threat_resp(24, None, doors=(), free_hatch=1))
        self.assertEqual(g.tools("build_door"), [{"kind": "hatch", "site": "E1"}])
        ov, g = self.play(threat_resp(28, None, doors=(dict(HATCH, built=False),)))
        self.assertEqual(g.tools("add_order") + g.tools("build_door"), [])       # placed and waiting to be built

    def test_one_day_steps_hold_while_a_lockdown_stands_even_without_the_task_clock(self):
        p = plain(WalkGame())
        p.guard.lock = hold(99)
        p.guard.days_left = None
        self.assertFalse(p.open_play())
        r = resp(236, 100, food=60)
        self.assertEqual(p.quiet_days(r), 1)
        p.guard.lock = None
        self.assertEqual(p.quiet_days(r), 2)

    def test_a_dug_level_too_large_for_one_burrow_call_is_left_out(self):
        big = {"id": "A2", "kind": "A", "z": 149, "w": 42, "h": 51, "open_tiles": 43}
        fits = {"id": "A1", "kind": "A", "z": 150, "w": 40, "h": 12, "open_tiles": 40}
        ov, g = self.play(threat_resp(50, None, sites=(E1, big, fits)))
        self.again(ov, g, threat_resp(56, None, sites=(E1, big, fits)))
        self.assertEqual(g.tools("create_burrow"), [{"site": "A1"}])
        self.assertEqual(ov.sheltered, {"A1": 40})

    def test_a_standing_lockdown_is_still_ended_if_the_task_clock_goes_missing(self):
        r = threat_resp(190, 150, alert=True, inside=10, doors=locked(14))
        del r["days_left"]
        ov, g = self.play(r, lock=hold(186), own_locks={14})
        self.assertFalse(ov.open_play())
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])

    def test_one_day_passes_while_a_hostile_is_in_sight(self):
        ov, g = self.play(threat_resp(190, 140))
        self.assertEqual(ov.step_days(), 1)
        ov, g = self.play(threat_resp(190, None))
        self.assertEqual(ov.step_days(), 2)


if __name__ == "__main__":
    unittest.main()
