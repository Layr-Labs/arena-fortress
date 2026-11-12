"""cx regressions: the harvest press (hint std OP1-0 on 9c4ec71, 2026-11-10, api record d0-80).

harvest_barrels_short read 22-30 on every load from day 0 to 47 (36-49 of 54 tiles sown with plump helmets, 0-5
plants standing) while the empty barrels stood 0-5: it only sized a one-shot supply() never added (the top-up waits
for no one-shot barrel work on the book, and the setup's 10-barrel one-shot sat 10 -> 5 left from day 5 to 46). The
barrel press — Carpenters up to 4, a barrel job per bench, crafts held to one a day — read only the plants already
standing and armed on day 47 with the harvest in: barrels 0.2/day unpressed (15 -> 24 total d0-46), 0.8-0.9/day
pressed (24 -> 50 d47-80); the harvest found 4 empty barrels and plants_rotten went 0 -> 15 by day 71. Every OP1 hint
record on 80e9f9d/0c8ca4b/a7b2833 shows the same pre-harvest 0.25-0.4 barrels/day.

The press now also arms on the crops in the ground (press_harv), from HARVEST_PRESS_FROM_DAY, while the empty barrels
are fewer than PRESS_BARRELS_FREE; it holds until they cover the want. The want counts brewable crops only (a plot of
a kind seen non-brewable wants no barrel) and is capped at BARREL_AHEAD_MAX (60: the measured first harvest ~59).
No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness
from test_harvest_levers import FakeGame, crafts_order, plot, resp

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


def barrel_once(oid=4, left=10):
    return {"id": oid, "job": "MakeBarrel", "recipe": "make_barrel", "material_category": ["wood"], "left": left,
            "total": 10, "active": True, "validated": True, "jobs_in_progress": 1, "repeat": None}


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, days=336, **kw):
        game = FakeGame(**kw)
        return harness.Overseer(game, days=days), game

    @staticmethod
    def load(ov, r):
        ov.load(r)
        ov.count = 0


class HarvestPress(Base):
    # the record's d20-46 shape: 36-49 tiles sown, no plant standing, 0-5 empty barrels, 2 Carpenters, the setup's
    # 10-barrel one-shot on the book
    def test_crops_in_the_ground_press_before_the_harvest(self):
        ov, game = self.ov()
        self.load(ov, resp(22, pb=0, barrels=1, plots=(9, 9, 9, 5, 0, 0), carpenters=2, orders=(barrel_once(),)))
        self.assertGreaterEqual(ov.harvest_barrels_short(), harness.HARVEST_PRESS_ON)
        self.assertTrue(ov.barrel_press())
        self.assertTrue(ov.press_harv)
        self.assertFalse(ov.press_stand)   # nothing stands yet: the old reading alone never pressed
        ov.workshops()
        self.assertTrue(any(t == "build_workshop" and a.get("type") == "Carpenters" for t, a in game.calls))

    def test_the_crafts_hold_while_the_harvest_presses(self):
        ov, game = self.ov()
        self.load(ov, resp(30, pb=0, barrels=2, plots=(9,) * 5, carpenters=4, orders=(crafts_order(),)))
        self.assertTrue(ov.barrel_press())
        self.assertTrue(ov.craft_press())
        self.assertIn(("cancel_order", {"order_id": 15}), game.calls)

    def test_holds_until_the_barrels_cover_the_harvest(self):
        ov, _ = self.ov()
        self.load(ov, resp(30, pb=0, barrels=2, plots=(9,) * 5))      # 45 sown -> 54 wanted
        self.assertTrue(ov.barrel_press())
        self.load(ov, resp(40, pb=0, barrels=30, plots=(9,) * 5))     # past PRESS_BARRELS_FREE, still short: holds
        self.assertTrue(ov.barrel_press())
        self.load(ov, resp(44, pb=0, barrels=54, plots=(9,) * 5))     # covered
        self.assertFalse(ov.barrel_press())
        self.load(ov, resp(46, pb=0, barrels=40, plots=(9,) * 5))     # short 14 but 40 free: no re-arm
        self.assertFalse(ov.barrel_press())
        self.load(ov, resp(60, pb=0, barrels=4, plots=(9,) * 5))      # barrel-poor again: re-arms
        self.assertTrue(ov.barrel_press())

    def test_not_before_its_day_nor_without_crops(self):
        ov, _ = self.ov()
        self.load(ov, resp(harness.HARVEST_PRESS_FROM_DAY - 1, pb=30, barrels=0, plots=(9, 9, 0, 0, 0, 0)))
        self.assertFalse(ov.barrel_press())
        ov2, _ = self.ov()
        self.load(ov2, resp(harness.HARVEST_PRESS_FROM_DAY, pb=0, barrels=0, plots=(0,) * 6))
        self.assertFalse(ov2.barrel_press())
        self.load(ov2, resp(harness.HARVEST_PRESS_FROM_DAY + 1, pb=0, barrels=0, plots=(9, 0, 0, 0, 0, 0)))
        self.assertTrue(ov2.barrel_press())

    def test_not_on_labs_short_runs_or_my1_without_rot(self):
        ov, _ = self.ov(days=90)
        self.load(ov, resp(30, days=90, pb=0, barrels=0, plots=(9,) * 6, hands_off=40))
        self.assertFalse(ov.barrel_press())
        ov2, _ = self.ov(days=216)
        self.load(ov2, resp(30, days=216, pb=0, barrels=0, plots=(9,) * 6))
        self.assertFalse(ov2.barrel_press())

    def test_plants_idle_beside_free_barrels_do_not_press(self):
        # CX_REVIEW P1-5 / hint std OP1-1 on 68bd4c7 d169-197: pb 40-51 beside 14-21 empty barrels, no brew planned
        ov, _ = self.ov()
        self.load(ov, resp(170, pb=44, barrels=19, plots=(9,) * 6))
        self.assertEqual(ov.brew_planned(), 0)
        self.assertEqual(ov.harvest_barrels_short(), 0)
        self.assertFalse(ov.barrel_press())

    def test_the_harvest_press_alone_lets_go_when_idle(self):
        ov, _ = self.ov()
        self.load(ov, resp(40, pb=0, barrels=5, plots=(9,) * 6))
        self.assertTrue(ov.barrel_press())
        self.load(ov, resp(60, pb=30, barrels=12, plots=(9,) * 6))   # 30 plants nobody brews beside 12 free barrels
        self.assertFalse(ov.barrel_press())


class HarvestWant(Base):
    def test_non_brewable_crops_want_no_barrel_once_seen(self):
        ov, _ = self.ov()
        r = resp(30, pb=0, barrels=0, plots=(9, 9, 0, 0, 0, 0))
        r["observation"]["farm_plots"][1]["crop_this_season"] = "BUSH_QUARRY"
        self.load(ov, r)
        self.assertEqual(ov.harvest_barrels_short(), 22)   # unseen kinds count: 18 * 1.2 = 21.6 -> 22
        seen = resp(31, pb=0, barrels=0, plots=(9, 9, 0, 0, 0, 0))
        seen["observation"]["farm_plots"][1]["crop_this_season"] = "BUSH_QUARRY"
        seen["observation"]["stocks"]["plants_by_kind"] = {
            "quarry bush": {"n": 4, "brewable": False, "cookable": False}}
        self.load(ov, seen)
        self.assertEqual(ov.harvest_barrels_short(), 11)   # 9 * 1.2 = 10.8 -> 11: the quarry bush plot wants none
        later = resp(32, pb=0, barrels=0, plots=(9, 9, 0, 0, 0, 0))   # the kind no longer stands: still known
        later["observation"]["farm_plots"][1]["crop_this_season"] = "BUSH_QUARRY"
        self.load(ov, later)
        self.assertEqual(ov.harvest_barrels_short(), 11)

    def test_the_first_harvest_is_wanted_whole(self):
        # the record's d40: 49 tiles of plump helmets sown, 3 empty barrels -> ~59 plants coming
        ov, _ = self.ov()
        self.load(ov, resp(40, pb=0, barrels=3, plots=(9, 9, 9, 9, 9, 4)))
        self.assertEqual(ov.harvest_barrels_short(), 59 - 3)
        self.assertLessEqual(59, harness.BARREL_AHEAD_MAX)


class SupplyUnderHarvestPress(Base):
    def test_a_barrel_batch_goes_in_once_the_setup_one_shot_drains(self):
        ov, game = self.ov()
        self.load(ov, resp(30, pb=0, barrels=2, plots=(9,) * 5, carpenters=4, orders=(barrel_once(left=2),)))
        self.assertTrue(ov.barrel_press())
        ov.supply()
        batch = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "make_barrel"
                 and not a.get("repeat")]
        self.assertTrue(batch)
        self.assertGreaterEqual(batch[0]["amount"], harness.PRESS_JOBS_PER_BENCH * 4 - 2)


if __name__ == "__main__":
    unittest.main()
