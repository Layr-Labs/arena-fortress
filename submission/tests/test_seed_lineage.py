"""cx regressions: the OP1 seed lineage and the perishable food (2026-11-10).

- seed_wait: the seed recycle sizes its one-shot to the empty barrels, so the brews it wanted beyond them never
  reached the book and never pressed. Replayed hint std OP1-4 on b796327 (d37-93): wants of 5-30 brews against 5-19
  empty barrels while the first harvest of ~50 plants stood d40-74 and 24 rotted; barrels came ~0.6/day unpressed,
  ~1.1/day pressed. The wanted-but-unbarrelled brews now count as waiting for the barrel press.
- farm_target: a lineage that outgrew its plots (free seeds fill every unsown tile with a plot's worth to spare)
  gets one more plot on a full-year run, up to 12.
- meat_keep: hint hard MY1-1 on 6adf843 — slaughters on d177-184 lifted the perishable food (food_edible less meals
  less plants) 35 -> 114 just before F, the kitchen cooked 2 a day, and the perishable fell 110 -> 69 in one look
  inside F (supply 0.766 on the food leg). A one-shot cook batch keeps it, gated off the plants seedwatch no longer
  protects while the lineage is short, and off the merchants' goods.
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

ALL = ["spring", "summer", "autumn", "winter"]


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": 900 + len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {"units": []}}


def plot(i, n):
    return {"id": i, "built": True, "w": 3, "h": 3, "z": 159, "seeds_or_crops_in_plot": n,
            "crop_this_season": "none", "subterranean": True}


def resp(day, days=336, cit=7, food=75, meals=22, plump=16, seeds=None, plots=(5, 5, 5, 5, 5, 5), barrels=6,
         drink=226, orders=(), workshops=("Carpenters", "Still", "Kitchen"), hands_off=None, wealth=3000):
    seeds = {"plump helmet": {"n": 21, "seasons": ALL, "underground": True}} if seeds is None else seeds
    pbk = {"plump helmet": {"n": plump, "brewable": True, "cookable": True}} if plump else {}
    stocks = {"drink": drink, "food_edible": food, "prepared_meals": meals, "plants_brewable": plump,
              "plants_total": plump, "plants_rotten": 0, "barrels_empty": barrels, "logs_usable": 200,
              "seeds": sum(v["n"] for v in seeds.values()), "seeds_by_kind": seeds, "plants_by_kind": pbk,
              "beds": 13, "tables": 9, "chairs": 8, "furniture_free": {}}
    obs = {"date": {"abs_tick": day * harness.DAY, "day_of_year": (15 + day) % harness.YEAR_DAYS},
           "administrators": {"citizens": cit, "manager_active_for_orders": True}, "stocks": stocks,
           "map": {"sites": []}, "zones": [], "furniture": [], "wealth": {"created": wealth},
           "workshops": [{"id": i, "type": w, "built": True} for i, w in enumerate(workshops)],
           "orders": list(orders), "farm_plots": [plot(i, n) for i, n in enumerate(plots)]}
    r = {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": days - day}
    if hands_off is not None:
        r["hands_off_in_days"] = hands_off
    return r


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, days=336):
        game = FakeGame()
        return harness.Overseer(game, days=days), game

    @staticmethod
    def load(ov, r):
        ov.load(r)
        ov.count = 0

    @staticmethod
    def adds(game, recipe):
        return [a for t, a in game.calls if t == "add_order" and a.get("recipe") == recipe]


class SeedWaitPress(Base):
    # replayed b796327 OP1-4 d47: 34 of 54 tiles sown, plump helmet 16 standing, 6 empty barrels
    def test_recycle_wants_beyond_the_barrels_press(self):
        ov, game = self.ov()
        self.load(ov, resp(47, plump=16, barrels=6, plots=(6, 6, 6, 6, 5, 5)))
        ov.barrel_press()
        self.assertFalse(ov.press_stand)             # no brew on the book: the standing reading has nothing waiting
        self.assertTrue(ov.press_harv)               # (34 tiles sown + 16 standing beside 6 barrels: harvest press)
        ov.seed_recycle()
        brews = self.adds(game, "brew_drink")
        self.assertEqual(len(brews), 1)
        self.assertEqual(brews[0]["amount"], 6)      # sized to the 6 barrels
        self.assertGreaterEqual(ov.seed_wait, harness.PRESS_ON)   # the rest waits on barrels
        ov.recycle_brews.clear()                     # (the one-shot is not on the next load's book in this fixture)
        self.load(ov, resp(48, plump=16, barrels=2, plots=(6, 6, 6, 6, 5, 5)))
        self.assertTrue(ov.barrel_press())           # the next pass reads the last pass's wanted brews

    def test_no_recycle_want_leaves_the_press_reading_alone(self):
        ov, game = self.ov()
        self.load(ov, resp(47, plump=16, barrels=0, plots=(9, 9, 9, 9, 9, 9),
                           seeds={"plump helmet": {"n": 60, "seasons": ALL, "underground": True}}))
        ov.seed_recycle()                            # every tile sown: no recycle
        self.assertEqual(ov.seed_wait, 0)
        self.load(ov, resp(48, plump=16, barrels=0, plots=(9, 9, 9, 9, 9, 9)))
        ov.barrel_press()
        self.assertFalse(ov.press_stand)             # standing plants nobody plans to brew press nothing (P1-5)
        self.assertTrue(ov.press_harv)               # ... but 54 tiles of crops coming to 0 barrels do

    def test_seed_wait_resets_when_the_recycle_stands_down(self):
        ov, game = self.ov()
        self.load(ov, resp(47, plump=16, barrels=2, plots=(6, 6, 6, 6, 5, 5)))
        ov.seed_recycle()
        self.assertGreater(ov.seed_wait, 0)
        self.load(ov, resp(320, plump=16, barrels=2, plots=(6, 6, 6, 6, 5, 5)))   # inside F: the recycle stops
        ov.seed_recycle()
        self.assertEqual(ov.seed_wait, 0)

    def test_short_runs_and_labs_do_not_press_on_seed_wait(self):
        ov, game = self.ov(days=216)                 # MY1 without rot: no press, whatever the recycle wants
        self.load(ov, resp(47, days=216, plump=16, barrels=2, plots=(6, 6, 6, 6, 5, 5)))
        ov.seed_wait = 20
        self.assertFalse(ov.barrel_press())


class LineagePlots(Base):
    def test_a_lineage_over_its_plots_gets_one_more(self):
        ov, _ = self.ov()
        seeds = {"plump helmet": {"n": 54 + 10, "seasons": ALL, "underground": True}}
        self.load(ov, resp(120, cit=13, seeds=seeds, plots=(9,) * 6))
        ov.mig_waves = 1   # both waves in (13 at the first load: one before): the population forecast adds nothing
        self.assertEqual(ov.farm_target(), 7)        # 10 free seeds over 54 sown tiles: one more plot
        self.load(ov, resp(121, cit=13, seeds={"plump helmet": {"n": 54 + 8, "seasons": ALL, "underground": True}},
                           plots=(9,) * 6))
        self.assertEqual(ov.farm_target(), 6)        # 8 free: not a plot's worth

    def test_unsown_tiles_come_first(self):
        ov, _ = self.ov()
        seeds = {"plump helmet": {"n": 40, "seasons": ALL, "underground": True}}
        self.load(ov, resp(120, cit=13, seeds=seeds, plots=(9, 9, 9, 3, 0, 0)))
        ov.mig_waves = 1   # both waves in: the population forecast adds nothing
        self.assertEqual(ov.farm_target(), 6)        # 10 free seeds, 24 unsown tiles: no new plot

    def test_capped_at_twelve_and_census_rule_kept(self):
        ov, _ = self.ov()
        seeds = {"plump helmet": {"n": 108 + 30, "seasons": ALL, "underground": True}}
        self.load(ov, resp(200, cit=21, seeds=seeds, plots=(9,) * 12))
        self.assertEqual(ov.farm_target(), 12)
        self.load(ov, resp(201, cit=45, seeds={}, plots=(0,)))
        self.assertEqual(ov.farm_target(), 12)       # ceil(45/3) capped

    def test_short_runs_keep_the_leader_target(self):
        ov, _ = self.ov(days=216)
        seeds = {"plump helmet": {"n": 54 + 30, "seasons": ALL, "underground": True}}
        self.load(ov, resp(120, days=216, cit=13, seeds=seeds, plots=(9,) * 6))
        self.assertEqual(ov.farm_target(), max(4, min(10, -(-13 // 5))))


class MeatKeep(Base):
    # hint hard MY1-1 on 6adf843 d184: food 213, meals 57, plants 42, seeds 51 — 32 days left (no seed floor)
    def test_slaughter_meat_before_f_is_cooked(self):
        ov, game = self.ov(days=216)
        seeds = {"plump helmet": {"n": 51, "seasons": ALL, "underground": True}}
        self.load(ov, resp(184, days=216, cit=21, food=213, meals=57, plump=42, seeds=seeds, plots=(8, 8, 8, 8, 8)))
        ov.meat_keep()
        cooks = self.adds(game, "cook_meal")
        self.assertEqual(cooks, [{"recipe": "cook_meal", "amount": harness.MEAT_KEEP_MAX}])
        self.assertNotIn("repeat", cooks[0])         # one-shot: no meal cap stops it

    def test_one_batch_on_the_book_at_a_time(self):
        ov, game = self.ov(days=216)
        seeds = {"plump helmet": {"n": 51, "seasons": ALL, "underground": True}}
        self.load(ov, resp(184, days=216, food=213, meals=57, plump=42, seeds=seeds))
        ov.meat_keep()
        oid = ov.key_order["o_cook_meat"]
        mine = {"id": oid, "recipe": "cook_meal", "left": 6, "total": 10}
        self.load(ov, resp(186, days=216, food=200, meals=60, plump=42, seeds=seeds, orders=(mine,)))
        ov.meat_keep()
        self.assertEqual(len(self.adds(game, "cook_meal")), 1)

    def test_small_or_unread_perishable_is_left(self):
        ov, game = self.ov()
        self.load(ov, resp(100, food=40, meals=22, plump=5))      # 13 perishable
        ov.meat_keep()
        r = resp(101, food=90)
        del r["observation"]["stocks"]["prepared_meals"]          # an unread part is not taken for meat
        self.load(ov, r)
        ov.meat_keep()
        self.assertEqual(game.calls, [])

    def test_a_cookable_kind_with_a_short_lineage_waits(self):
        # the fresh OP1 fort at d40: plump helmet seeds 35 (seedwatch lets the kitchen take it), 50 of 54 tiles sown
        ov, game = self.ov()
        seeds = {"plump helmet": {"n": 35, "seasons": ALL, "underground": True}}
        self.load(ov, resp(40, food=69, meals=36, plump=4, seeds=seeds, plots=(9, 9, 9, 9, 9, 5)))
        ov.meat_keep()
        self.assertEqual(game.calls, [])

    def test_every_kind_under_seedwatch_lets_the_meat_cook(self):
        # replayed b796327 OP1-4 d135-146: perishable 62-68 after the slaughters, seeds 10-15 (all protected)
        ov, game = self.ov()
        seeds = {"plump helmet": {"n": 10, "seasons": ALL, "underground": True},
                 "cave wheat": {"n": 3, "seasons": ["summer", "autumn"], "underground": True}}
        self.load(ov, resp(135, cit=13, food=88, meals=26, plump=0, seeds=seeds, plots=(3, 3, 2, 2, 1, 1)))
        ov.meat_keep()
        self.assertEqual(self.adds(game, "cook_meal"), [{"recipe": "cook_meal", "amount": 62 // 4}]
                         if 62 // 4 <= harness.MEAT_KEEP_MAX else [{"recipe": "cook_meal",
                                                                     "amount": harness.MEAT_KEEP_MAX}])

    def test_no_batch_on_the_merchants_goods_or_a_lab_task(self):
        ov, game = self.ov()
        self.load(ov, resp(170, cit=13, food=255, meals=24, plump=0,
                           seeds={"plump helmet": {"n": 10, "seasons": ALL, "underground": True}}))
        ov.caravan_active = True
        ov.meat_keep()
        self.assertEqual(game.calls, [])
        ov, game = self.ov(days=90)
        self.load(ov, resp(40, days=90, food=120, meals=10, plump=0, hands_off=20,
                           seeds={"plump helmet": {"n": 10, "seasons": ALL, "underground": True}}))
        ov.meat_keep()
        self.assertEqual(game.calls, [])

    def test_no_kitchen_no_batch(self):
        ov, game = self.ov()
        self.load(ov, resp(135, food=120, meals=10, plump=0, workshops=("Carpenters", "Still"),
                           seeds={"plump helmet": {"n": 10, "seasons": ALL, "underground": True}}))
        ov.meat_keep()
        self.assertEqual(game.calls, [])


class LineageSpare(Base):
    def test_free_seeds_must_cover_the_unsown_tiles_and_a_plot(self):
        ov, _ = self.ov()
        self.load(ov, resp(60, seeds={"plump helmet": {"n": 60, "seasons": ALL, "underground": True}},
                           plots=(9, 9, 9, 9, 9, 5)))
        self.assertFalse(ov.lineage_spare())         # 60 - 50 = 10 free < 4 unsown + 9
        self.load(ov, resp(61, seeds={"plump helmet": {"n": 63, "seasons": ALL, "underground": True}},
                           plots=(9, 9, 9, 9, 9, 9)))
        self.assertTrue(ov.lineage_spare())          # 9 free, every tile sown

    def test_no_plot_is_not_spare_and_the_end_is(self):
        ov, _ = self.ov()
        self.load(ov, resp(7, seeds={"plump helmet": {"n": 5, "seasons": ALL, "underground": True}}, plots=()))
        self.assertFalse(ov.lineage_spare())         # embark: no plot yet, the seeds are the whole lineage
        self.load(ov, resp(320, seeds={"plump helmet": {"n": 5, "seasons": ALL, "underground": True}},
                           plots=(0, 0)))
        self.assertTrue(ov.lineage_spare())          # inside HOLD_GROW_DAYS of the end: nothing ripens in time


if __name__ == "__main__":
    unittest.main()
