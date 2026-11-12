"""Offline regressions for the troop animals added to the wildlife lockdown: small wild animals that come in troops
(rhesus macaques, keas, giant keas, gray langurs, buzzards) and any species a game's combat reports show attacking
a citizen are found by the same look as the large predators, start the same lockdown, and, within TROOP_QUICK of the
wagon, have the hatches due at once. Stub game; no DF and no model.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from overseer.beasts import TROOPS, fought, in_sight, words  # noqa: E402
from overseer.harness import DAY  # noqa: E402
from overseer.openplay import ADMIT_FAR, PREDATORS, TROOP_QUICK  # noqa: E402
from plain.digest import ATTACK  # noqa: E402
from support import HATCH, WAGON, beast, hold, overseer, quiet  # noqa: E402

CARNO = "CRETACEOUS_CARNOTAURUS"
ON = {"on": True}
LOCK = {"locked": True, "door_id": 14}


class Words(unittest.TestCase):
    def test_race_ids_match_report_names(self):
        for race in ("BIRD_KEA", "GIANT_KEA", "GRAY_LANGUR", "BIRD_BUZZARD", "MACAQUE_RHESUS", "RHESUS_MACAQUE"):
            self.assertIn(words(race), TROOPS, race)
        for race in ("GIANT_GRAY_LANGUR", "KEA_MAN", "BADGER", "BIRD_GUINEAFOWL", "DOG", "", None, 7):
            self.assertNotIn(words(race), TROOPS, race)

    def test_in_sight_marks_troops_and_keeps_the_beasts(self):
        units = [beast("BIRD_KEA", 50), beast("MACAQUE_RHESUS", 70), beast(CARNO, 90), beast("BADGER", 20),
                 beast("BIRD_KEA", 10, tame=True), beast("GRAY_LANGUR", 5, hostile=True),
                 beast("BIRD_BUZZARD", 30, visitor=True)]
        found, sure = in_sight(units, len(units), WAGON)
        self.assertTrue(sure)
        self.assertEqual([(b["race"], b["dist"], b["troop"]) for b in found],
                         [("BIRD_KEA", 50, True), ("MACAQUE_RHESUS", 70, True), (CARNO, 90, False)])

    def test_the_old_call_still_sees_troops_and_an_empty_set_sees_none(self):
        units = [beast("GIANT_KEA", 40), beast(CARNO, 90)]
        self.assertEqual(len(in_sight(units, 2, WAGON)[0]), 2)
        self.assertEqual([b["race"] for b in in_sight(units, 2, WAGON, frozenset())[0]], [CARNO])

    def test_felling_still_waits_only_for_the_large_predators(self):
        self.assertFalse({"BIRD_KEA", "GIANT_KEA", "GRAY_LANGUR", "MACAQUE_RHESUS", "BIRD_BUZZARD"} & PREDATORS)


class Fought(unittest.TestCase):
    CIT = {"dwarf", "woodcrafter", "miner", "urist"}

    def test_an_attack_on_a_citizen_names_the_species(self):
        events = ["The rhesus macaque bites the woodcrafter in the left hand, tearing the skin!",
                  "The badger scratches The Miner in the right foot!",
                  "The gray langur grabs Urist's left arm",
                  "The kea attacks the dwarf"]
        self.assertEqual(fought(events, self.CIT, ATTACK),
                         {words("rhesus macaque"), words("badger"), words("kea")})

    def test_not_a_citizen_attacking_nor_an_animal_attacking_an_animal(self):
        events = ["The woodcrafter punches the rhesus macaque in the head!",
                  "The rhesus macaque bites the stray dog in the leg!",
                  "The Stray Dog (Tame) bites the miner",
                  "Urist McMiner, Miner: I am ecstatic!", None, 5,
                  "The dwarf strikes the miner"]
        self.assertEqual(fought(events, self.CIT, ATTACK), set())
        self.assertEqual(fought(None, self.CIT, ATTACK), set())


def at_risk(day, others, events=(), people=None, **kw):
    r = quiet(day, others, **kw)
    o = r["observation"]
    if events:
        o["recent_events"] = list(events)
    for p in o["dwarves"]:
        p.update(x=95, y=101, z=151, profession="Mason")      # below, in the shelter's levels
    for i in people or ():
        o["dwarves"][i].update(x=93, y=100, z=153, profession="Miner")   # beside the hatch, on the surface
    return r


class TroopLockdown(unittest.TestCase):
    def play(self, r, **state):
        ov, g = overseer(r)
        g.others = r.get("others", [])
        for k, v in state.items():
            setattr(ov, k, v)
        ov.defend()
        return ov, g

    def again(self, ov, g, r):
        g.others = r.get("others", [])
        ov.load(r)
        ov.count = 0
        ov.defend()

    def test_a_troop_within_reach_starts_the_lockdown_and_shuts_the_hatch_at_once(self):
        ov, g = self.play(at_risk(100, [beast("BIRD_KEA", TROOP_QUICK - 4)]))
        self.assertEqual(g.tools("civilian_alert"), [ON])
        self.assertEqual(g.tools("lock_door"), [LOCK])
        self.assertEqual((ov.lock["phase"], ov.lock["due"]), ("hold", 100 * DAY))

    def test_a_troop_farther_off_starts_it_and_gathers_as_before(self):
        ov, g = self.play(at_risk(100, [beast("MACAQUE_RHESUS", TROOP_QUICK + 5)]))
        self.assertEqual(g.tools("civilian_alert"), [ON])
        self.assertEqual(g.tools("lock_door"), [])
        self.assertIsNone(ov.lock["due"])

    def test_a_large_predator_still_gathers_for_a_day(self):
        ov, g = self.play(at_risk(100, [beast(CARNO, 60)]))
        self.assertEqual(g.tools("civilian_alert"), [ON])
        self.assertEqual(g.tools("lock_door"), [])

    def test_no_lockdown_for_a_troop_beyond_the_old_distance(self):
        ov, g = self.play(at_risk(100, [beast("GRAY_LANGUR", 120)]))
        self.assertEqual((g.tools("civilian_alert"), ov.lock), ([], None))

    def test_a_citizen_outside_is_let_in_while_the_troop_is_far_from_the_hatch(self):
        ov, g = self.play(at_risk(100, [beast("BIRD_KEA", 70)], people=(3,)))     # 74 tiles from the hatch
        self.assertEqual(g.tools("lock_door"), [])
        self.assertEqual(ov.lock["open"], {14})
        ov, g = self.play(at_risk(100, [beast("BIRD_KEA", ADMIT_FAR - 10)], people=(3,)))
        self.assertEqual(g.tools("lock_door"), [LOCK])

    def test_a_species_that_fought_a_citizen_counts_for_the_rest_of_the_game(self):
        ov, g = self.play(at_risk(100, [beast("BADGER", 50)]))
        self.assertEqual((g.tools("civilian_alert"), ov.lock), ([], None))             # unlisted: nothing
        ov, g = self.play(at_risk(100, [beast("BADGER", 50)],
                                  events=["The badger bites The Miner in the left foot!"], people=(2,)))
        self.assertEqual(ov.fought, {words("badger")})
        self.assertEqual(g.tools("civilian_alert"), [ON])
        self.assertTrue(ov.lock["beast"] is not None)
        # later passes: the report is gone, the species is still counted, and its going ends the lockdown
        self.again(ov, g, at_risk(101, [beast("BADGER", 40)], alert=True, doors=(dict(HATCH, locked=True),)))
        self.assertEqual(ov.lock["phase"], "hold")
        self.again(ov, g, at_risk(102, [], alert=True, doors=(dict(HATCH, locked=True),)))
        self.assertIsNone(ov.lock)

    def test_a_held_lockdown_ends_when_the_troop_is_gone(self):
        ov, g = self.play(at_risk(101, [beast("GIANT_KEA", 150)], alert=True, doors=(dict(HATCH, locked=True),)),
                          lock=hold(100, beast=100 * DAY, due=100 * DAY), own_locks={14})
        self.assertIsNone(ov.lock)
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])

    def test_troops_count_against_the_beast_budget(self):
        ov, g = self.play(at_risk(100, [beast("BIRD_KEA", 40)]), beast_spent=60 * DAY)
        self.assertEqual((g.tools("civilian_alert"), ov.lock), ([], None))

    def test_a_failing_report_reader_costs_nothing_else(self):
        r = at_risk(100, [beast("BIRD_KEA", 40)])
        r["observation"]["recent_events"] = "ERR: scripted"
        ov, g = self.play(r)
        self.assertEqual(g.tools("civilian_alert"), [ON])
        self.assertEqual(ov.fought, set())


if __name__ == "__main__":
    unittest.main()
