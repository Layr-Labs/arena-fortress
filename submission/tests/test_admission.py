"""Offline regressions for citizens shut out of a wildlife lockdown: the hatch is left open, or opened again, for
citizens on the surface while every hostile and large predator in sight is far from it, and locked again when they
are below, when the danger comes nearer, when the observation can't be read, or when the openings are spent. Stub
game; no DF and no model.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from overseer.harness import DAY  # noqa: E402
from overseer.openplay import ADMIT_DAYS, ADMIT_FAR, ADMIT_MAX  # noqa: E402
from support import HATCH, Lockdown, beast, hold, locked, overseer, quiet, threat_resp  # noqa: E402

CARNO = "CRETACEOUS_CARNOTAURUS"
UNLOCK, LOCK = {"locked": False, "door_id": 14}, {"locked": True, "door_id": 14}


def outside(r, *ids, z=153):
    """Citizens `ids` stand beside the hatch (on its level, or at z); the rest are below, in the shelter."""
    for p in r["observation"]["dwarves"]:
        p.update(x=93, y=100, z=z, profession="Mason") if p["id"] in ids else p.update(x=95, y=101, z=151)
    return r


def shut(day, dist, *ids, race=CARNO, doors=None, **kw):
    """A lockdown pass: the alert on, a large predator `dist` tiles east of the wagon (its distance to the hatch is
    dist + 4), citizens `ids` outside."""
    r = quiet(day, [beast(race, dist)] if dist is not None else [], alert=True, inside=10 - len(ids),
              doors=doors or (HATCH,), **kw)
    return outside(r, *ids)


class Admission(Lockdown, unittest.TestCase):
    def play(self, r, **state):
        ov, g = overseer(r)
        g.others = r.get("others", [])
        for k, v in state.items():
            setattr(ov, k, v)
        ov.defend()
        return ov, g

    def again(self, ov, g, r):
        g.others = r.get("others", [])
        ov.load(r); ov.count = 0
        ov.defend()

    def held(self, r, **state):
        return self.play(r, lock=hold(186, beast=186 * DAY, **state.pop("lock", {})), **state)

    def test_citizens_asleep_on_the_surface_are_not_locked_out(self):
        ov, g = self.held(shut(187, 80, 3, 4))                       # due by the clock; the animal 84 tiles off
        self.assertEqual(g.tools("lock_door"), [])
        self.assertEqual((ov.lock["open"], ov.lock["admit"]["n"]), ({14}, 1))
        self.again(ov, g, shut(188, 80))                             # they are below: locked now
        self.assertEqual(g.tools("lock_door"), [LOCK])
        self.assertEqual((ov.lock["open"], ov.lock["tries"], ov.own_locks), (set(), 0, {14}))
        self.assertEqual(g.tools("civilian_alert"), [])              # the alert was never touched

    def test_a_locked_hatch_is_opened_for_a_citizen_outside_and_locked_behind_them(self):
        ov, g = self.held(shut(190, 80, 3, doors=locked(14)), lock={"due": 187 * DAY}, own_locks={14})
        self.assertEqual(g.tools("lock_door"), [UNLOCK])
        self.assertEqual(ov.own_locks, set())
        self.again(ov, g, shut(191, 80))
        self.assertEqual(g.tools("lock_door"), [UNLOCK, LOCK])
        self.assertEqual((ov.lock["phase"], ov.lock["tries"]), ("hold", 0))

    def test_not_while_the_danger_is_near_or_cannot_be_placed(self):
        near = shut(190, ADMIT_FAR - 4, 3)                           # the animal ADMIT_FAR tiles from the hatch
        hostile = outside(threat_resp(190, 100, alert=True, inside=9), 3)   # a hostile of the API's, not wildlife
        unsure = shut(190, 80, 3)
        unsure["others"].append({"id": 701})                         # a row that can't be read: the look is unsure
        unplaced = shut(190, 80, 3)
        del unplaced["others"][0]["x"]
        for r in (near, hostile, unsure, unplaced):
            ov, g = self.held(r, lock={"due": 187 * DAY})
            self.assertEqual(g.tools("lock_door"), [LOCK])
            self.assertEqual(ov.lock.get("open"), set())

    def test_a_lurker_counts_at_five_times_its_distance(self):
        ov, g = self.held(shut(190, 9, 3, race="ALLIGATOR"), lock={"due": 187 * DAY})     # 13 tiles: 65
        self.assertEqual(g.tools("lock_door"), [])
        ov, g = self.held(shut(190, 7, 3, race="ALLIGATOR"), lock={"due": 187 * DAY})     # 11 tiles: 55
        self.assertEqual(g.tools("lock_door"), [LOCK])

    def test_openings_are_limited_in_length_and_number(self):
        ov, g = self.held(shut(187, 80, 3))                          # someone who never comes in
        for day in range(188, 190 + ADMIT_MAX * (ADMIT_DAYS + 1)):  # inside the lockdown's 20 days
            self.again(ov, g, shut(day, 80, 3, doors=locked(14) if g.tools("lock_door")[-1:] == [LOCK] else None))
        self.assertEqual(ov.lock["admit"]["n"], ADMIT_MAX)
        self.assertEqual(g.tools("lock_door").count(UNLOCK), ADMIT_MAX - 1)   # the first opening needed no call
        self.assertEqual(g.tools("lock_door")[-1], LOCK)
        self.assertEqual((ov.lock["phase"], ov.wild_off), ("hold", False))

    def test_an_unreadable_pass_locks_what_was_opened(self):
        ov, g = self.held(shut(187, 80, 3))
        self.again(ov, g, shut(188, 80, 3, drop=("doors",)))
        self.assertEqual(g.tools("lock_door"), [LOCK])
        self.assertEqual((ov.lock["open"], ov.own_locks), (set(), {14}))

    def test_a_hatch_it_opened_and_finds_locked_is_unlocked_at_the_end(self):
        ov, g = self.held(shut(190, 80, 3, doors=locked(14)), lock={"due": 187 * DAY}, own_locks={14})
        self.again(ov, g, shut(191, 50, doors=locked(14)))          # answered ok, yet shown locked
        self.assertEqual(ov.own_locks, {14})
        self.again(ov, g, shut(192, 150, doors=locked(14)))         # gone: the fort is opened
        self.assertEqual(g.tools("lock_door")[-1], UNLOCK)
        self.assertIsNone(ov.lock)

    def test_invaders_during_an_opening_get_the_hatch_shut_again(self):
        ov, g = self.held(shut(190, 80, 3, doors=locked(14)), lock={"due": 187 * DAY}, own_locks={14})
        invaders = outside(threat_resp(191, 30, invader=True, alert=True, inside=9), 3)
        self.again(ov, g, invaders)                                  # the shelter is open as invaders arrive
        self.assertEqual((ov.lock["why"], g.tools("lock_door")), ("invaders", [UNLOCK, LOCK]))
        self.again(ov, g, outside(threat_resp(192, 30, invader=True, alert=True, inside=9, doors=locked(14)), 3))
        self.assertEqual((g.tools("lock_door")[-1], ov.own_locks, ov.lock["reclose"]), (LOCK, {14}, set()))
        self.again(ov, g, threat_resp(193, None, alert=False, inside=10, doors=locked(14)))   # the invaders left
        self.assertEqual(g.tools("lock_door")[-1], UNLOCK)
        self.assertIsNone(ov.lock)

    def test_an_animal_that_cannot_be_placed_stops_nothing(self):
        ov, g = self.held(shut(190, 80, 3, doors=locked(14)), lock={"due": 187 * DAY}, own_locks={14})
        r = shut(191, 80, 3)
        r["others"].append(dict(beast(CARNO, 90), id=702, x=None))   # placed and unplaced in one answer
        self.again(ov, g, r)
        self.assertEqual(g.tools("lock_door"), [UNLOCK, LOCK])       # shut again: the danger can't be placed
        self.assertEqual([s for s in ov.beast_view["seen"]], [(80, CARNO), (None, CARNO)])

    def test_opened_then_shown_locked_as_the_animal_leaves_is_unlocked(self):
        ov, g = self.held(shut(190, 80, 3, doors=locked(14)), lock={"due": 187 * DAY}, own_locks={14})
        self.again(ov, g, shut(191, None, doors=locked(14)))         # gone, and the hatch shows locked
        self.assertEqual(g.tools("lock_door"), [UNLOCK, UNLOCK])
        self.assertEqual((ov.lock, ov.own_locks), (None, set()))

    def test_the_digest_is_told_the_hatches_and_the_opening(self):
        ov, g = self.held(shut(190, 50, 3, doors=locked(14)), lock={"due": 187 * DAY}, own_locks={14})
        s = ov.status()["lockdown"]
        self.assertEqual((s["since_day"], s["hatches"], s["opening"], s["gathering"]), (186, [14], [], False))
        self.assertEqual(ov.status()["beasts"]["seen"], [(50, CARNO)])


if __name__ == "__main__":
    unittest.main()
