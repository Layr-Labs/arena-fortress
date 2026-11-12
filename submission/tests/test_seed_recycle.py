"""cx regressions: the seed recycle (hint hard MY1-5 on d56d5b8, O 80.7, supply 0.742 on the food leg: food 127 -> 110
over F with 17-19 of 19 citizens idle). From day ~150 the plump helmet lineage stood as 38-46 plants with 0-4 free
seeds while 0-17 of the 45 plot tiles were sown: seedwatch kept the plants out of the kitchen, the allocation and the
food-lean keeper kept them out of the Still, so nothing handed the seeds back and the plots produced nothing through
F. Open play, outside F: the unsown tiles less the free seeds autofarm can sow are brewed back out of the standing
plants of a kind that can be planted now and ripen before the end, within a food floor; inside F the recycle's own
unfinished brews are cancelled. No game or network."""
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
MY1_DOY0 = 135   # a MY1 run starts at day_of_year 135 (summer)


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": 700 + len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {"units": []}}


def plot(i, n, w=3, h=3):
    return {"id": i, "built": True, "w": w, "h": h, "z": 116, "seeds_or_crops_in_plot": n,
            "crop_this_season": "none", "subterranean": True}


def resp(day, days=216, cit=19, drink=680, food=140, plump=43, seeds=None, plots=(0, 0, 0, 0, 0), barrels=28,
         orders=(), workshops=("Carpenters", "Still", "Kitchen"), hands_off=None, other=None, doy0=MY1_DOY0):
    seeds = {} if seeds is None else seeds
    pbk = {"plump helmet": {"n": plump, "brewable": True, "cookable": True}} if plump else {}
    pbk.update(other or {})
    pb = sum(v["n"] for v in pbk.values() if v.get("brewable"))
    stocks = {"drink": drink, "food_edible": food, "prepared_meals": max(0, food - plump), "plants_brewable": pb,
              "plants_total": sum(v["n"] for v in pbk.values()), "plants_rotten": 0, "barrels_empty": barrels,
              "logs_usable": 200, "seeds": sum(v["n"] for v in seeds.values()), "seeds_by_kind": seeds,
              "plants_by_kind": pbk, "furniture_free": {}}
    obs = {"date": {"abs_tick": day * harness.DAY, "day_of_year": (day + doy0) % harness.YEAR_DAYS},
           "administrators": {"citizens": cit}, "stocks": stocks, "map": {"sites": []}, "zones": [],
           "furniture": [], "workshops": [{"type": w, "built": True} for w in workshops], "orders": list(orders),
           "farm_plots": [plot(i, n) for i, n in enumerate(plots)], "wealth": {"created": 10000}}
    r = {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": days - day}
    if hands_off is not None:
        r["hands_off_in_days"] = hands_off
    return r


def plump_seeds(n):
    return {"plump helmet": {"n": n, "seasons": ALL, "underground": True}}


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, day=157, days=216, learn=True, **kw):
        """An overseer that saw plump helmet seeds (and their seasons) on an earlier load, then loads `day`."""
        game = FakeGame()
        ov = harness.Overseer(game, days=days)
        if learn:
            ov.load(resp(100, days=days, seeds=plump_seeds(31), plots=(9, 9, 9, 0, 0), plump=3, food=40))
        ov.load(resp(day, days=days, **kw))
        ov.count = 0
        return ov, game

    @staticmethod
    def brews(game):
        return [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"]

    @staticmethod
    def cancels(game):
        return [a["order_id"] for t, a in game.calls if t == "cancel_order"]


class SeedRecycle(Base):
    # the measured day 157: 5 plots of 3x3 all empty, plump helmet 43 standing, its seeds all gone into plants
    def test_measured_fallow_plots_brew_the_standing_plants_back_into_seeds(self):
        ov, game = self.ov()
        self.assertEqual(ov.plot_tiles(), (45, 0))
        self.assertEqual(ov.kind_seasons.get("plump helmet"), ALL)   # remembered from the earlier load
        ov.seed_recycle()
        b = self.brews(game)
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0]["amount"], 28)                          # min(45 tiles, 43 - 2, food floor, 28 barrels)
        self.assertNotIn("repeat", b[0])
        self.assertIn(ov.key_order["o_brew_seed"], ov.recycle_brews)

    def test_barrels_short_draws_a_barrel_one_shot(self):
        ov, game = self.ov(barrels=5)
        ov.seed_recycle()
        self.assertEqual(self.brews(game)[0]["amount"], 5)
        barrels = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "make_barrel"]
        self.assertEqual(len(barrels), 1)
        self.assertGreaterEqual(barrels[0]["amount"], 1)

    def test_the_food_floor_bounds_the_dip(self):
        # 19 citizens: RECYCLE_FOOD_DAYS of FOOD_PER_CIT_DAY = ~54 kept
        floor = harness.RECYCLE_FOOD_DAYS * harness.FOOD_PER_CIT_DAY * 19
        ov, game = self.ov(food=70)
        ov.seed_recycle()
        self.assertEqual(self.brews(game)[0]["amount"], int(70 - floor))
        ov2, game2 = self.ov(food=50)
        ov2.seed_recycle()
        self.assertEqual(self.brews(game2), [])

    def test_the_brews_on_the_book_count(self):
        ov, game = self.ov()
        ov.seed_recycle()
        oid = ov.key_order["o_brew_seed"]
        order = {"id": oid, "recipe": "brew_drink", "job": "CustomReaction", "left": 28, "when": []}
        ov.load(resp(160, orders=[order]))
        ov.last.clear()
        ov.seed_recycle()
        self.assertEqual(len(self.brews(game)), 1)                    # 28 on the book cover the barrels

    def test_a_short_drink_leg_keeps_the_reserve_its_own_consumers_keep(self):
        # day 120 of 216 (left 96): the reserve-build window; drink 30 is the shorter leg
        ov, game = self.ov(day=120, drink=30, food=140)
        self.assertTrue(ov.reserve_build())
        ov.seed_recycle()
        b = self.brews(game)
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0]["amount"], 43 - ov.plant_floor())
        ov2, game2 = self.ov(day=120, drink=30, food=140, plump=30)   # under the reserve: nothing spent
        ov2.seed_recycle()
        self.assertEqual(self.brews(game2), [])

    def test_full_plots_or_free_seeds_need_no_recycle(self):
        ov, game = self.ov(plots=(9, 9, 9, 9, 9), seeds=plump_seeds(45))
        ov.seed_recycle()
        self.assertEqual(self.brews(game), [])
        ov2, game2 = self.ov(plots=(9, 9, 0, 0, 0), seeds=plump_seeds(18 + 25))   # 25 free seeds for 27 tiles
        ov2.seed_recycle()
        self.assertEqual(self.brews(game2), [])

    def test_a_kind_at_the_autofarm_threshold_is_brewed_under_it(self):
        # 60 standing: autofarm plants none of it even with 30 free seeds in stock
        ov, game = self.ov(plump=60, seeds=plump_seeds(30), barrels=40)
        ov.seed_recycle()
        b = self.brews(game)
        self.assertEqual(len(b), 1)
        self.assertGreaterEqual(b[0]["amount"], 60 - (harness.AUTOFARM_THRESHOLD - 1))

    def test_inside_f_no_recycle_and_the_open_brews_are_cancelled(self):
        ov, game = self.ov()
        ov.seed_recycle()
        oid = ov.key_order["o_brew_seed"]
        order = {"id": oid, "recipe": "brew_drink", "job": "CustomReaction", "left": 20, "when": []}
        ov.load(resp(190, orders=[order]))                            # left 26 <= F's 28
        ov.last.clear()
        ov.seed_recycle()
        self.assertEqual(len(self.brews(game)), 1)
        self.assertEqual(self.cancels(game), [oid])

    def test_a_crop_that_cannot_ripen_before_the_end_stays_food(self):
        # left 31 < 25 grow + 7 lead (and not yet F)
        ov, game = self.ov(day=185)
        ov.seed_recycle()
        self.assertEqual(self.brews(game), [])

    def test_out_of_season_kinds_are_not_recycled(self):
        # winter (doy 292): pig tail grows summer-autumn only
        summer = {"pig tail": {"n": 2, "seasons": ["summer", "autumn"], "underground": True}}
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        ov.load(resp(100, seeds=summer, plump=0, plots=(2, 0, 0, 0, 0)))
        ov.load(resp(157, plump=0, seeds=summer, other={"pig tail": {"n": 40, "brewable": True, "cookable": False}},
                     plots=(2, 0, 0, 0, 0)))
        ov.seed_recycle()
        self.assertEqual(self.brews(game), [])

    def test_unknown_seasons_leave_it_alone(self):
        ov, game = self.ov(learn=False)                               # plump helmet seeds never seen
        ov.seed_recycle()
        self.assertEqual(self.brews(game), [])

    def test_lab_tasks_short_runs_the_caravan_and_no_still(self):
        ov, game = self.ov(hands_off=10)
        ov.seed_recycle()
        self.assertEqual(self.brews(game), [])
        ov2, game2 = self.ov(days=120, day=60)
        ov2.seed_recycle()
        self.assertEqual(self.brews(game2), [])
        # cx m13many (838106a hard MY1-3): the caravan no longer stops it — it reads the fort's own seeds (no more
        # than on the last look before the merchants: their 40 seeds of the same kind leave the brew as it was)
        ov0, game0 = self.ov()
        ov0.seed_recycle()
        ov3, game3 = self.ov()
        ov3.caravan_active = True
        sbk = {k: dict(v) for k, v in ov3.st["seeds_by_kind"].items()}
        for v in sbk.values():
            v["n"] = (v.get("n") or 0) + 40
        ov3.st["seeds_by_kind"] = sbk
        ov3.seed_recycle()
        self.assertTrue(self.brews(game0))
        self.assertEqual(self.brews(game3), self.brews(game0))
        ov4, game4 = self.ov(workshops=("Carpenters", "Kitchen"))
        ov4.seed_recycle()
        self.assertEqual(self.brews(game4), [])

    def test_plots_without_a_size_are_not_counted(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        ov.load(resp(100, seeds=plump_seeds(31), plump=3, food=40))
        r = resp(157)
        r["observation"]["farm_plots"] = [{"id": 1, "z": 116, "seeds_or_crops_in_plot": 0}]
        ov.load(r)
        self.assertEqual(ov.plot_tiles(), (0, 0))
        ov.seed_recycle()
        self.assertEqual(self.brews(game), [])

    def test_the_food_lean_spares_the_recycle_brews(self):
        ov, game = self.ov(day=160, drink=680, food=140)
        ov.seed_recycle()
        oid = ov.key_order["o_brew_seed"]
        order = {"id": oid, "recipe": "brew_drink", "job": "CustomReaction", "left": 20, "when": []}
        other = {"id": 5, "recipe": "brew_drink", "job": "CustomReaction", "left": 3, "when": []}
        ov.load(resp(162, drink=680, food=120, orders=[order, other]))
        self.assertTrue(ov.food_lean())
        ov.lean_supply()
        self.assertEqual(self.cancels(game), [5])

    def test_the_plan_pass_runs_it_before_the_lean_cancels(self):
        import inspect
        src = inspect.getsource(harness.Overseer.plan)
        self.assertLess(src.index("self.seed_recycle()"), src.index("self.lean_supply()"))


if __name__ == "__main__":
    unittest.main()


class RegrowLend(Base):
    """cx regrow lend: inside the MY1 harvest-closed hold, a plant of a kind that is still sowable and ripens before F
    is lent to the Still (5 drinks and a seed now, a plant again before F); a kind that cannot come back keeps the
    whole lend closed (a brew order takes any brewable plant)."""

    def pig(self, n):
        return {"pig tail": {"n": n, "brewable": True, "cookable": False}}

    def held(self, day, other, seeds, plots=(0, 0, 0, 0)):
        ov, game = self.ov(day=day, learn=False, plump=0, other=other, seeds=seeds, plots=plots, drink=60, food=300,
                           cit=17)
        ov.hold_active = lambda: True
        return ov, game

    SEEDS = {"pig tail": {"n": 0, "seasons": ["summer", "autumn"], "underground": True}}

    def test_sowable_kind_is_lent_in_the_hold(self):
        ov, game = self.held(60, self.pig(3), self.SEEDS)   # day 60 = doy 195 (autumn): +7+25 still autumn
        self.assertEqual(ov.regrow_cap(), 3)
        self.assertEqual(ov.brew_shot_allow("o_brew_seed"), 3)

    def test_a_kind_past_its_sow_window_closes_the_lend(self):
        ov, game = self.held(90, self.pig(3), self.SEEDS)   # doy 225: the crop would ripen in winter
        self.assertEqual(ov.regrow_cap(), 0)
        self.assertEqual(ov.brew_shot_allow("o_brew_seed"), 0)

    def test_a_kind_that_cannot_come_back_keeps_the_hold(self):
        other = dict(self.pig(3), **{"cave wheat": {"n": 4, "brewable": True, "cookable": False}})
        seeds = dict(self.SEEDS, **{"cave wheat": {"n": 0, "seasons": ["summer", "autumn"], "underground": True}})
        ov, game = self.held(80, other, seeds)   # cave wheat (42 days) cannot ripen in autumn from doy 215
        self.assertEqual(ov.regrow_cap(), 0)

    def test_outside_the_hold_nothing_changes(self):
        ov, game = self.ov(day=60, learn=False, plump=0, other=self.pig(3), seeds=self.SEEDS, plots=(0, 0, 0, 0))
        ov.hold_active = lambda: False
        self.assertEqual(ov.regrow_cap(), 0)
