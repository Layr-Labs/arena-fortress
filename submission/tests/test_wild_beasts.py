"""Offline regressions for large wild predators on open play: the units query is read against the list in
overseer/beasts.py, one in reach of the wagon starts the wildlife lockdown, and a lockdown that has had one in
sight is not ended as "gone" while one is there. Stub game; no DF and no model. The regressions for a look that fails, is cut short or cannot be
parsed are kept with the study.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from overseer.beasts import BEASTS, LURKERS, in_sight  # noqa: E402
from overseer.harness import DAY  # noqa: E402
from overseer.openplay import BEAST_BUDGET, PREDATORS, WILD_DAYS  # noqa: E402
from support import E1, HATCH, Lockdown, bare, hold, locked, overseer, threat_resp  # noqa: E402

WAGON = {"x": 96, "y": 96, "z": 153}


def beast(race, dist, **kw):
    return {"id": 700, "race": race, "hostile": False, "x": WAGON["x"] + dist, "y": WAGON["y"], "z": 153, **kw}


def quiet(day, others=(), drink=50, **kw):
    """An open-play observation with no hostile in the threats list; `others` is what the units query will list."""
    r = threat_resp(day, None, **kw)
    r["observation"]["map"]["wagon"] = dict(WAGON)
    r["observation"]["stocks"]["drink"] = drink
    r["others"] = [dict(u) for u in others]
    return r


class Beasts(Lockdown, unittest.TestCase):
    def play(self, r, refuse=(), query_error=False, **state):
        ov, g = overseer(r, refuse=refuse, query_error=query_error)
        g.others = r.get("others", [])
        for k, v in state.items():
            setattr(ov, k, v)
        ov.defend()
        return ov, g

    def again(self, ov, g, r, query_error=False):
        g.others, g.query_error = r.get("others", []), query_error
        ov.load(r); ov.count = 0
        ov.defend()

    def test_the_list_reads_the_units_query(self):
        units = [beast("CRETACEOUS_CARNOTAURUS", 80), beast("ALLIGATOR", 15), beast("DINGO", 5), beast("BIRD_RAVEN", 3),
                 beast("TIGER", 10, hostile=True), beast("BEAR_BLACK", 10, visitor=True)]
        found, sure = in_sight(units, len(units), WAGON)
        self.assertEqual(([(b["race"], b["dist"]) for b in found], sure),
                         ([("CRETACEOUS_CARNOTAURUS", 80), ("ALLIGATOR", 75)], True))
        self.assertEqual(in_sight(None, None, WAGON), ([], False))
        self.assertEqual(in_sight([beast("DINGO", 5)], 1, None), ([], True))         # nothing listed: no wagon needed
        self.assertTrue(LURKERS <= BEASTS <= PREDATORS)

    def test_distance_is_the_apis_measure_with_three_for_every_level(self):
        high = dict(beast("CRETACEOUS_QUETZALCOATLUS", 0), z=203)
        self.assertEqual(in_sight([high], 1, WAGON)[0][0]["dist"], 150)
        ov, g = self.play(quiet(60, [high]))
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_a_large_predator_in_reach_starts_a_lockdown(self):
        ov, g = self.play(quiet(60, [beast("CRETACEOUS_CARNOTAURUS", 93)]))
        self.assertEqual(g.tools("civilian_alert"), [{"on": True}])
        self.assertEqual((ov.lock["phase"], ov.lock["beast"]), ("hold", 60 * DAY))
        self.assertEqual(ov.step_days(), 1)

    def test_a_lurker_counts_only_beside_the_wagon(self):
        ov, g = self.play(quiet(60, [beast("ALLIGATOR", 35)]))
        self.assertEqual(g.tools("civilian_alert"), [])
        self.assertEqual(ov.step_days(), 2)                          # out of reach: the pace is not changed for it
        ov, g = self.play(quiet(60, [beast("ALLIGATOR", 18)]))
        self.assertEqual(g.tools("civilian_alert"), [{"on": True}])

    def test_smaller_and_harmless_animals_do_not(self):
        ov, g = self.play(quiet(60, [beast("DINGO", 10), beast("WOLF", 10), beast("WILD_BOAR", 5), beast("HIPPO", 5)]))
        self.assertEqual(g.tools("civilian_alert"), [])
        self.assertEqual(ov.step_days(), 2)

    def test_no_look_while_the_fort_cannot_be_shut(self):
        ov, g = self.play(quiet(60, [beast("CRETACEOUS_CARNOTAURUS", 20)], doors=()))
        self.assertEqual((g.tools("civilian_alert"), g.queries), ([], 0))

    def test_one_inside_the_shelter_or_one_that_cannot_be_placed_is_not_locked_in_with_the_fort(self):
        inside = dict(beast("CRETACEOUS_CARNOTAURUS", 0), x=95, y=101, z=151)
        ov, g = self.play(quiet(60, [inside]))
        self.assertEqual(g.tools("civilian_alert"), [])
        ov, g = self.play(quiet(60, [dict(beast("CRETACEOUS_CARNOTAURUS", 20), z=None)]))
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_not_for_animals_alone_when_drink_is_short_or_the_budget_is_spent(self):
        ov, g = self.play(quiet(60, [beast("CRETACEOUS_CARNOTAURUS", 93)], drink=5))         # ten citizens
        self.assertEqual(g.tools("civilian_alert"), [])
        ov, g = self.play(quiet(60, [beast("CRETACEOUS_CARNOTAURUS", 93)]), beast_spent=BEAST_BUDGET * DAY)
        self.assertEqual(g.tools("civilian_alert"), [])
        r = threat_resp(60, 74)                                      # a hostile of the API's is not held to either
        r["observation"]["stocks"]["drink"] = 5
        ov, g = self.play(r, beast_spent=BEAST_BUDGET * DAY)
        self.assertEqual(g.tools("civilian_alert"), [{"on": True}])

    def test_the_days_shut_for_an_animal_are_counted_from_its_first_sight_to_the_opening(self):
        r = quiet(72, [], alert=True, inside=10, doors=locked(14))
        ov, g = self.play(r, lock=hold(60, beast=62 * DAY), own_locks={14})
        self.assertEqual((ov.lock, ov.beast_spent), (None, 10 * DAY))
        ov, g = self.play(r, lock=hold(60, beast=None), own_locks={14})          # a lockdown for hostiles is not
        self.assertEqual(ov.beast_spent, 0)
        ov, g = self.play(r, refuse={("lock_door", None)}, lock=hold(60, beast=62 * DAY), own_locks={14})
        self.assertEqual(ov.beast_spent, 0)                          # the hatch would not open: nothing counted yet
        self.again(ov, g, quiet(75, [], alert=False, inside=10, doors=locked(14)))
        self.assertEqual(ov.beast_spent, 0)
        g.refuse = set()
        self.again(ov, g, quiet(76, [], alert=False, inside=10, doors=locked(14)))
        self.assertEqual((ov.lock, ov.beast_spent), (None, 14 * DAY))            # once, and to the day it opened

    def test_a_lockdown_for_animals_alone_ends_when_the_budget_or_the_stocks_run_out(self):
        near = [beast("CRETACEOUS_CARNOTAURUS", 50)]
        r = quiet(70, near, alert=True, inside=10, doors=locked(14))
        ov, g = self.play(r, lock=hold(60, beast=60 * DAY, shut=True), own_locks={14},
                          beast_spent=(BEAST_BUDGET - 10) * DAY)
        self.assertEqual((ov.lock, g.tools("civilian_alert")), (None, [{"on": False}]))
        self.assertEqual(ov.beast_spent, BEAST_BUDGET * DAY)
        self.assertGreater(ov.rest_until, ov.now)
        ov, g = self.play(quiet(70, near, alert=True, inside=10, doors=locked(14), drink=5),
                          lock=hold(60, beast=60 * DAY, shut=True), own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        r = threat_resp(70, 74, alert=True, inside=10, doors=locked(14))         # a hostile of the API's as well:
        r["observation"]["stocks"]["drink"] = 5                                  # neither limit applies
        r["observation"]["map"]["wagon"] = dict(WAGON)
        r["others"] = near
        ov, g = self.play(r, lock=hold(60, beast=60 * DAY, shut=True), own_locks={14},
                          beast_spent=BEAST_BUDGET * DAY)
        self.assertEqual((ov.lock["phase"], g.tools("civilian_alert")), ("hold", []))

    def test_a_lockdown_holds_while_the_predator_is_in_sight_and_ends_when_it_is_gone(self):
        ov, g = self.play(quiet(60, [beast("CRETACEOUS_CARNOTAURUS", 93)], inside=10))
        self.assertEqual(g.tools("lock_door"), [{"locked": True, "door_id": 14}])
        self.again(ov, g, quiet(61, [beast("CRETACEOUS_CARNOTAURUS", 40)], alert=True, inside=10, doors=locked(14)))
        self.assertEqual(ov.lock["phase"], "hold")
        self.again(ov, g, quiet(62, [], alert=True, inside=10, doors=locked(14)), query_error=True)
        self.assertEqual(ov.lock["phase"], "hold")                   # the look failed: not read as "gone"
        self.again(ov, g, quiet(63, [], alert=True, inside=10, doors=locked(14)))
        self.assertEqual(g.tools("civilian_alert"), [{"on": True}, {"on": False}])
        self.assertEqual(g.tools("lock_door")[-1], {"locked": False, "door_id": 14})

    def test_it_is_let_out_after_the_limit_like_any_lockdown(self):
        r = quiet(60 + WILD_DAYS, [beast("CRETACEOUS_CARNOTAURUS", 50)], alert=True, inside=10, doors=locked(14))
        ov, g = self.play(r, lock=hold(60, beast=60 * DAY), own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertGreater(ov.rest_until, ov.now)

    def test_the_first_felling_waits_for_a_carnotaurus(self):
        r = bare(336, 0)
        r["observation"]["plugins"] = {"autochop": "off", "seedwatch": "on", "autofarm": "on", "autolabor": "on"}
        ov, g = overseer(r)
        g.others = [beast("CRETACEOUS_CARNOTAURUS", 90)]
        self.assertTrue(ov.felling_waits())

    def test_a_spare_hatch_cover_is_ordered_with_the_first(self):
        ov, g = self.play(quiet(3, doors=(), free_hatch=0))
        self.assertEqual(g.tools("add_order"), [{"recipe": "make_hatch_cover", "amount": 2}])
        ov, g = self.play(quiet(9, doors=(HATCH,), sites=(E1, dict(E1, id="E2", x=98)), free_hatch=0))
        self.assertEqual(g.tools("add_order"), [{"recipe": "make_hatch_cover", "amount": 1}])
        below = dict(HATCH, id=30, z=150)                            # a hatch that is on no surface stair
        ov, g = self.play(quiet(3, doors=(below,), free_hatch=0))
        self.assertEqual(g.tools("add_order"), [{"recipe": "make_hatch_cover", "amount": 2}])


if __name__ == "__main__":
    unittest.main()
