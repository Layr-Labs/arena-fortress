"""cx regressions: the rotting reserve (hint std MY1-3 on c44c96b, O 68.2, supply 0.576 on the drink leg). The
harvest-closed hold kept the last autumn cohort for F, but those plants lay loose (PLANT stock query: cave wheat 5,
in_inventory 0 from d92) and rotted 16-18 days after harvest (rotten 1/3/5 on d104/109/116) while the rot guard's
floor stood at the hold reserve (26 over pb 6-7): F held no plant and drink fell 61 -> 39 over F. The same version's
hard MY1-3 kept its plants in barrels (in_inventory 4 of 5, d141-190) and brewed them inside F (supply 1.0). Once the
fort's plants rot, the aged loose plants leave the hold's floor and go to the Still; barrelled and fresh ones stay.
Also: the rot guard's arming rise is read over ROT_ARM_DAYS, not over one load (a load a day read 1 -> 1 -> 2 -> 3).
No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

FORT3_SEEDS = {"cave wheat": {"n": 1, "seasons": ["summer", "autumn"], "underground": True},
               "sweet pod": {"n": 2, "seasons": ["spring", "summer"], "underground": True}}
KINDS = {"cave wheat": {"brewable": True, "cookable": False}, "pig tail": {"brewable": True, "cookable": False}}
MY1_DOY0 = 135


class FakeGame:
    def __init__(self):
        self.calls = []
        self.groups = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": 700 + len(self.calls)}}

    def query(self, name, **kw):
        if name == "stocks" and kw.get("item_type") == "PLANT":
            return {"result": {"groups": [dict(g) for g in self.groups]}}
        return {"result": {"units": []}}


def group(mat, items, rotten=0, inv=0, bld=0, job=0):
    return {"item_type": "PLANT", "material": "PLANT:%s:STRUCTURAL" % mat, "items": items, "count": items,
            "rotten": rotten, "in_inventory": inv, "in_building": bld, "in_job": job, "forbidden": 0,
            "construction": 0}


def resp(day, days=216, cit=13, drink=107, food=156, pb=0, rot=0, barrels=9, seeds=FORT3_SEEDS):
    stocks = {"drink": drink, "food_edible": food, "prepared_meals": 85, "plants_brewable": pb, "plants_total": pb,
              "plants_rotten": rot, "barrels_empty": barrels, "logs_usable": 150, "plants_by_kind": KINDS,
              "seeds": sum(v["n"] for v in seeds.values()), "seeds_by_kind": seeds, "furniture_free": {}}
    obs = {"date": {"abs_tick": day * harness.DAY, "day_of_year": (MY1_DOY0 + day) % harness.YEAR_DAYS},
           "administrators": {"citizens": cit}, "stocks": stocks, "map": {"sites": []}, "zones": [],
           "furniture": [], "workshops": [{"type": w, "built": True} for w in ("Carpenters", "Still", "Kitchen")],
           "orders": [], "farm_plots": [{"id": i, "z": 143, "w": 3, "h": 3, "built": True,
                                         "crop_this_season": "none", "seeds_or_crops_in_plot": 0} for i in range(5)]}
    return {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": days - day}


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, days=216):
        game = FakeGame()
        return harness.Overseer(game, days=days), game

    def step(self, ov, day, **kw):
        ov.load(resp(day, days=ov.days, **kw))
        ov.count = 0
        ov.plant_census()
        ov.hold_active()   # the hold arms on two confirmed loads (as plan() reads it every pass)

    @staticmethod
    def brews(game):
        return [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"]


class RotArming(Base):
    # replayed std MY1-3 on c44c96b with a load a day: rot 0 (d100) 1 (d104-106) 2 (d107) — the record's 7-day loads
    # read 1 -> 3 and armed; daily loads never rose 2 in one load
    def test_daily_loads_arm_on_a_rise_inside_the_window(self):
        ov, _ = self.ov()
        for day, rot in ((100, 0), (104, 1), (105, 1), (106, 1)):
            self.step(ov, day, rot=rot, pb=6)
            self.assertFalse(ov.rot_seen)
        self.step(ov, 107, rot=2, pb=6)
        self.assertTrue(ov.rot_seen)

    def test_a_rise_spread_past_the_window_does_not_arm(self):
        ov, _ = self.ov()
        for day, rot in ((100, 0), (108, 1), (116, 2), (124, 3)):
            self.step(ov, day, rot=rot, pb=6)
        self.assertFalse(ov.rot_seen)

    def test_a_lone_rotten_plant_still_does_not_arm(self):
        ov, _ = self.ov()
        for day in range(42, 58):
            self.step(ov, day, rot=0 if day == 42 else 1, pb=1)
        self.assertFalse(ov.rot_seen)


class Census(Base):
    def test_loose_and_contained_brewable_units(self):
        ov, game = self.ov()
        game.groups = [group("GRASS_WHEAT_CAVE", 5, rotten=3), group("GRASS_TAIL_PIG", 4, inv=1, bld=1),
                       group("MUSHROOM_CUP_DIMPLE", 6)]   # not brewable here: not counted
        self.step(ov, 109, pb=7, rot=3)
        self.assertEqual(ov.plant_loose, {"loose": 2 + 2, "contained": 1, "day": 109})

    def test_no_groups_reads_none_loose(self):
        ov, game = self.ov()
        self.step(ov, 160, pb=0)
        self.assertEqual(ov.plant_loose, {"loose": 0, "contained": 0, "day": 160})


class RottingReserve(Base):
    def held(self, inv):
        """The record's shape: the hold armed in autumn, the cave wheat cohort harvested d89-98 (pb 1 -> 6) lying
        loose (inv 0) or barrelled (inv = all), rot 0 -> 2 on d104-107."""
        ov, game = self.ov()
        harvest = ((80, 0), (85, 0), (89, 1), (91, 2), (92, 3), (96, 5), (98, 6), (100, 6))
        for day, pb in harvest:
            game.groups = [group("GRASS_WHEAT_CAVE", pb, inv=pb if inv else 0)] if pb else []
            self.step(ov, day, pb=pb)
        self.assertTrue(ov.hold_active())
        for day, rot in ((104, 1), (107, 2)):
            game.groups = [group("GRASS_WHEAT_CAVE", 6, rotten=rot, inv=6 - rot if inv else 0)]
            self.step(ov, day, pb=6 - rot, rot=rot)
        self.assertTrue(ov.rot_seen)
        game.calls.clear()
        return ov, game

    def test_aged_loose_plants_of_a_rotting_fort_go_to_the_still(self):
        ov, game = self.held(inv=False)
        floor = ov.plant_floor()
        self.assertGreater(floor, ov.pb_free())          # the hold's reserve is over everything standing
        self.assertGreaterEqual(ov.rotting_held(), 1)
        self.assertLess(ov.rot_keep(), ov.pb_free())
        ov.rot_guard()
        b = self.brews(game)
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0]["amount"], ov.pb_free() - ov.rot_keep())
        self.assertNotIn("repeat", b[0])

    def test_barrelled_plants_stay_the_holds(self):
        ov, game = self.held(inv=True)
        self.assertEqual(ov.rotting_held(), 0)
        self.assertEqual(ov.rot_keep(), max(harness.ROT_KEEP, ov.plant_floor()))
        ov.rot_guard()
        self.assertEqual(self.brews(game), [])

    def test_fresh_loose_plants_stay_the_holds(self):
        ov, game = self.held(inv=True)
        # a new cohort comes in loose on d108 on a fort whose plants were barrelled: it is not PLANT_USE_AGE days old
        # and no census before today read a loose plant (cx stuck harvest: nothing has been loose LOOSE_BREW_DAYS)
        ov.plant_age = [[108, 4]]
        game.groups = [group("GRASS_TAIL_PIG", 4)]
        self.step(ov, 108, pb=4, rot=2)
        self.assertEqual(ov.loose_stuck(), 0)
        self.assertEqual(ov.rotting_held(), 0)
        ov.rot_guard()
        self.assertEqual(self.brews(game), [])

    def test_a_stale_census_keeps_the_hold(self):
        ov, game = self.held(inv=False)
        ov.plant_loose = dict(ov.plant_loose, day=ov.day - harness.PLANT_USE_AGE - 1)
        ov.loose_hist = [h for h in ov.loose_hist if h[0] <= ov.plant_loose["day"]]   # no census since then either
        self.assertEqual(ov.rotting_held(), 0)

    # the hard MY1-3 / cx68bd4c7 std MY1-3 shape: plants standing for weeks, never rotten — in barrels, nothing
    # changes (cx stuck harvest: the old records had no PLANT census; standing LOOSE is test_stuck_harvest.py's case)
    def test_no_rot_no_release(self):
        ov, game = self.ov()
        for day, pb in ((80, 0), (85, 0), (89, 1), (92, 3), (98, 6), (110, 6), (130, 6), (150, 6)):
            game.groups = [group("GRASS_WHEAT_CAVE", pb, inv=pb)] if pb else []
            self.step(ov, day, pb=pb)
        self.assertTrue(ov.hold_active())
        self.assertFalse(ov.rot_seen)
        self.assertEqual(ov.aged_plants(), 0)   # MY1 ages count only once the fort's plants rot
        self.assertEqual(ov.rotting_held(), 0)
        game.calls.clear()
        ov.rot_guard()
        self.assertEqual(self.brews(game), [])


if __name__ == "__main__":
    unittest.main()
