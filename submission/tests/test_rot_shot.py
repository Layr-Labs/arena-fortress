"""cx rot shot (hint std OP1-3 on ba93eee, 2026-11-11; ROT_SHOT_MAX in overseer/harness.py). OP1 has no food
stockpile: a harvest lies loose until a Still or Kitchen job takes it, empty barrels or not. Under a drink glut the
rot guard's one-shots were the only brews, ALLOC_BREW_MAX (8) a weekly pass, and plants_rotten rose 0 -> 18 while the
Stills idled between passes. The guard's one-shot now covers every plant at risk, up to 30; while a caravan stays the
merchants' barrelled plants are not counted at risk. No game or network."""
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

from test_rotting_reserve import Base, group, resp   # noqa: E402  (same fake game and observation)

PLUMP = {"plump helmet": {"n": 40, "seasons": ["spring", "summer", "autumn", "winter"], "underground": True}}
KINDS = {"plump helmet": {"brewable": True, "cookable": True}}


class RotShot(Base):
    def step(self, ov, day, **kw):
        r = resp(day, days=ov.days, **kw)
        r["observation"]["stocks"]["plants_by_kind"] = KINDS
        ov.load(r)
        ov.count = 0
        ov.plant_census()
        ov.hold_active()

    def run_loose(self, loose, last=176, groups=None, caravan=False):
        """An OP1 year: `loose` plump helmets lying loose and read on every census from d165 to `last`."""
        ov, game = self.ov(days=336)
        for day in range(165, last + 1):
            game.groups = groups or [group("MUSHROOM_HELMET_PLUMP", loose)]
            pb = sum(g["count"] for g in game.groups)
            ov.caravan_active = caravan
            self.step(ov, day, pb=pb, barrels=45, drink=625, food=367, cit=19, seeds=PLUMP)
        ov.caravan_active = caravan
        return ov, game

    def test_a_large_stuck_harvest_is_brewed_in_one_shot(self):
        ov, game = self.run_loose(20)
        self.assertEqual(ov.loose_stuck(), 20)
        game.calls.clear()
        ov.rot_guard()
        b = self.brews(game)
        self.assertEqual(len(b), 1)
        self.assertGreater(b[0]["amount"], harness.ALLOC_BREW_MAX)   # was 8 a pass
        self.assertEqual(b[0]["amount"], 20 - ov.rot_keep())

    def test_the_shot_stops_at_the_order_maximum(self):
        ov, game = self.run_loose(40)
        game.calls.clear()
        ov.rot_guard()
        self.assertEqual([x["amount"] for x in self.brews(game)], [harness.ROT_SHOT_MAX])

    def test_a_small_stuck_harvest_is_unchanged(self):
        ov, game = self.run_loose(3)
        game.calls.clear()
        ov.rot_guard()
        self.assertEqual([x["amount"] for x in self.brews(game)], [3])

    def test_caravan_barrels_are_not_at_risk(self):
        # the measured d172 PLANT answer: plump helmet count 68, items 32, 9 merchants' barrels (stacks of 5), 2 in
        # buildings, 1 rotten: 20 loose plump helmets, not 20 x 68/32 = 42
        mixed = [dict(group("MUSHROOM_HELMET_PLUMP", 32, rotten=1, inv=9, bld=2), count=68)]
        ov, game = self.run_loose(0, groups=mixed, caravan=True)
        self.assertEqual(ov.plant_loose["loose"], 20)
        self.assertEqual(ov.loose_stuck(), 20)
        game.calls.clear()
        ov.rot_guard()
        b = self.brews(game)
        self.assertEqual(len(b), 1)
        self.assertLessEqual(b[0]["amount"], 20)

    def test_without_a_caravan_a_mixed_group_keeps_its_unit_estimate(self):
        mixed = [dict(group("MUSHROOM_HELMET_PLUMP", 6, inv=5), count=30)]
        ov, _ = self.run_loose(0, last=166, groups=mixed)
        self.assertEqual(ov.plant_loose["loose"], 5)   # one stack of 5 out of the embark barrels, as before


if __name__ == "__main__":
    unittest.main()
