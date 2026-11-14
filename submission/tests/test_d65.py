"""d65: fixes from the second code review (13 November), three of them to d64's own changes.
1. No hatch is opened for a citizen outside while a hostile the API lists is within ADMIT_CITIZEN of him: the game's
   hostile_near_citizens tripwire fires only for one that comes nearer, so nothing would stop the advance.
2. The lockdown's failure counts (a hatch still open when due, unreadable passes, failed looks) count once a game day:
   d64's extra passes for tripwire stops could otherwise use them up within hours.
3. The squad's kill order names the hostiles at the wagon; a squad whose members aren't listed doesn't fight.
4. At 0 food the kept animals make up what the spare ones can't (two a pass at HUNGER_BIG citizens)."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import HATCH, hold, overseer, resp, threat_resp  # noqa: E402
from overseer.harness import DAY  # noqa: E402
from overseer.openplay import ADMIT_CITIZEN, ADMIT_FAR, FEAST_DAYS, HUNGER_BIG  # noqa: E402

LOCK = {"locked": True, "door_id": 14}


def animal(i, race):
    return {"id": i, "race": race, "tame": True, "adult": True, "pet_owner_id": -1}


def marked(g):
    return [a["unit_id"] for a in g.tools("slaughter")]


def later(r, ticks):
    """The same observation `ticks` later within the same game day."""
    r["tick"] += ticks
    r["observation"]["date"]["abs_tick"] += ticks
    return r


class D65(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    # 1. admission and a hostile already near the citizen outside
    def outside_far(self, at):
        """A lockdown pass: citizen 3 outside, 58 tiles east of the hatch; two hostiles at `at`."""
        r = threat_resp(190, 87, n=2, alert=True, inside=9, at=at)
        for p in r["observation"]["dwarves"]:
            p.update(x=150, y=100, z=153, profession="Craftsdwarf") if p["id"] == 3 else p.update(x=95, y=101, z=151)
        ov, g = overseer(r)
        ov.lock = hold(189, due=189 * DAY)
        ov.defend()
        return ov, g

    def test_no_opening_for_a_citizen_a_hostile_is_already_near(self):
        ov, g = self.outside_far(at=(160, 100, 153))          # 68 from the hatch, 10 from the citizen
        self.assertIn(LOCK, g.tools("lock_door"))
        self.assertEqual(ov.lock["open"], set())

    def test_an_opening_when_the_hostiles_are_far_from_both(self):
        far = 150 + ADMIT_CITIZEN + 30                         # well clear of the citizen and the hatch
        ov, g = self.outside_far(at=(far, 100 + ADMIT_FAR + 20, 153))
        self.assertNotIn(LOCK, g.tools("lock_door"))
        self.assertEqual(ov.lock["open"], {HATCH["id"]})

    # 2. failure counts once a day
    def test_two_passes_in_a_day_count_one_failed_close(self):
        r = threat_resp(190, 30, alert=True, inside=10)
        ov, g = overseer(r, refuse={("lock_door", None)})      # every lock is refused
        ov.lock = hold(188, due=189 * DAY)
        ov.defend()
        self.assertEqual(ov.lock["tries"], 1)
        r2 = later(threat_resp(190, 30, alert=True, inside=10), 300)
        ov.load(r2)
        ov.count = 0
        ov.defend()                                            # a tripwire pass the same day
        self.assertIsNotNone(ov.lock)
        self.assertEqual((ov.lock["phase"], ov.lock["tries"], ov.wild_off), ("hold", 1, False))

    # 3. the squad's kill order
    def test_the_kill_order_names_the_hostile_at_the_wagon(self):
        r = threat_resp(200, 30, n=2, doors=(), cit=16)
        r["observation"]["threats"]["hostiles"][1].update(dist_to_wagon=132)    # one near, one far
        r["observation"]["military"] = {"squads": [{"id": 1, "members": [{"id": i} for i in range(4)], "armed": 4,
                                                    "uniform": "leather", "orders": []}]}
        ov, g = overseer(r)
        ov.defend()
        self.assertEqual(g.tools("squad_order"), [{"order": "attack", "target_ids": [900]}])

    def test_no_fight_without_a_member_list(self):
        r = threat_resp(200, 30, n=2, doors=(), cit=16)
        r["observation"]["military"] = {"squads": [{"id": 1, "armed": 1, "uniform": "leather", "orders": []}]}
        ov, g = overseer(r)
        ov.defend()
        self.assertEqual(g.tools("squad_order"), [])

    # 4. two a pass at 0 food
    def test_a_big_fort_at_zero_food_takes_two_with_one_spare(self):
        left = FEAST_DAYS + 10
        herd = [animal(14, "DOG"), animal(15, "BIRD_TURKEY"), animal(16, "PIG"), animal(10, "YAK")]
        ov, g = overseer(resp(left, 336 - left, food=0, cit=HUNGER_BIG), herd=herd)
        ov.provision()
        self.assertEqual(marked(g), [10, 15])                  # the grazer, then the smallest kept; the pig stays


if __name__ == "__main__":
    unittest.main()
