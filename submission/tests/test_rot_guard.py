"""cx regressions: OP1 seed starvation. Every full OP1 record lost its seed lineage (seeds + plants_total, 60 at
embark) to rot, not to the kitchen: plants_rotten increments summed 38-59 a run while the lineage fell to 1-20, the
harvests sat with no empty barrel (barrels_empty 0, d48-62) or under capped brew standings (d218-249, barrels 12-22
free, pb 12 -> 1, rot 8), and seedwatch keeps a crop under 30 seeds out of the kitchen. Once the fort's own plants
rot, the rot guard brews the standing plants down to ROT_KEEP with one-shots and orders the barrels the plants and
the plots' growing seeds need. Also: o_cook_food was added twice (cx6f40047 OP1-0 orders 43 and 44), because a
freshly added order reads active: false. No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

PLUMP = {"plump helmet": {"n": 9, "seasons": ["spring", "summer", "autumn", "winter"], "underground": True}}


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": 500 + len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {"units": []}}


def resp(day, days=336, cit=7, drink=229, food=81, pb=27, rot=3, barrels=0, growing=(2, 0, 0, 0, 5, 4),
         orders=(), workshops=("Carpenters", "Still", "Kitchen"), logs=195, hands_off=None):
    stocks = {"drink": drink, "food_edible": food, "prepared_meals": 21, "plants_brewable": pb,
              "plants_total": pb, "plants_rotten": rot, "barrels_empty": barrels, "logs_usable": logs,
              "seeds": 21, "seeds_by_kind": PLUMP, "furniture_free": {}}
    obs = {"date": {"abs_tick": day * harness.DAY, "day_of_year": (15 + day) % harness.YEAR_DAYS},
           "administrators": {"citizens": cit}, "stocks": stocks, "map": {"sites": []}, "zones": [],
           "furniture": [], "workshops": [{"type": w, "built": True} for w in workshops], "orders": list(orders),
           "farm_plots": [{"id": i, "z": 161, "seeds_or_crops_in_plot": n} for i, n in enumerate(growing)]}
    r = {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": days - day}
    if hands_off is not None:
        r["hands_off_in_days"] = hands_off
    return r


class RotGuard(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, days=336):
        game = FakeGame()
        return harness.Overseer(game, days=days), game

    def step(self, ov, day, days=336, **kw):
        ov.load(resp(day, days=days, **kw))
        ov.count = 0
        ov.rot_guard()

    def ov_base(self, days=336, game=None):
        """An overseer that has seen the d55 load (rot 0): the baseline the arming rise is read against."""
        ov, game = self.ov(days)
        self.step(ov, 55, days=days, rot=0, pb=29, barrels=0)
        self.assertEqual(game.calls, [])
        return ov, game

    @staticmethod
    def orders(game, recipe):
        return [a for t, a in game.calls if t == "add_order" and a.get("recipe") == recipe]

    # the measured cx6f40047 OP1-0 d62: harvest standing at pb 27, rot 3, barrels 0
    def test_first_rot_arms_and_orders_barrels_for_the_harvest(self):
        ov, game = self.ov_base()
        self.step(ov, 62)
        self.assertTrue(ov.rot_seen)
        self.assertEqual(self.orders(game, "brew_drink"), [])   # no empty barrel: nothing to brew into yet
        self.assertEqual(self.orders(game, "make_barrel"), [{"recipe": "make_barrel", "amount": 4}])

    # d218-249: barrels free, every brew standing capped under drink ~400, pb 12 left to rot
    def test_capped_standings_do_not_keep_the_plants_from_the_still(self):
        ov, game = self.ov_base()
        self.step(ov, 62)
        game.calls.clear()
        self.step(ov, 232, drink=407, food=79, cit=23, pb=12, rot=4, barrels=17, growing=(0, 0, 0, 0, 2, 2))
        # cx rot shot: all 12 are aged (harvested by d62), so the one-shot takes every plant above ROT_KEEP at once
        self.assertEqual(self.orders(game, "brew_drink"), [{"recipe": "brew_drink", "amount": 12 - harness.ROT_KEEP}])
        self.assertEqual(self.orders(game, "make_barrel"), [])   # 10 + 4 to fill, 17 empty

    def test_the_brew_is_sized_by_plants_above_the_keep_and_by_barrels(self):
        ov, game = self.ov_base()
        self.step(ov, 62, pb=5, barrels=9)
        self.assertEqual(self.orders(game, "brew_drink"), [{"recipe": "brew_drink", "amount": 3}])
        ov2, game2 = self.ov_base()
        self.step(ov2, 62, pb=20, barrels=2)
        self.assertEqual(self.orders(game2, "brew_drink"), [{"recipe": "brew_drink", "amount": 2}])

    def test_rot_seen_is_sticky_after_the_rotten_plants_go(self):
        ov, game = self.ov_base()
        self.step(ov, 62, barrels=0)
        self.step(ov, 104, rot=0, pb=9, barrels=8)
        self.assertTrue(ov.rot_seen)
        self.assertEqual(self.orders(game, "brew_drink"), [{"recipe": "brew_drink", "amount": 7}])

    def test_a_pending_one_shot_is_not_stacked(self):
        ov, game = self.ov_base()
        self.step(ov, 62, pb=20, barrels=5)
        self.assertEqual(len(self.orders(game, "brew_drink")), 1)
        oid = ov.key_order["o_brew_rot"]
        bid = ov.key_order["o_barrel_rot"]
        # the pending one-shot already takes every free barrel: nothing is stacked on it (the top-up below orders
        # only what the pending one does not cover)
        pend = [{"id": oid, "recipe": "brew_drink", "left": 5}, {"id": bid, "recipe": "make_barrel", "left": 2}]
        self.step(ov, 64, pb=20, barrels=5, orders=pend)
        self.assertEqual(len(self.orders(game, "brew_drink")), 1)
        self.assertEqual(len(self.orders(game, "make_barrel")), 1)
        self.step(ov, 66, pb=17, barrels=2, orders=[dict(pend[0], left=0), dict(pend[1], left=0)])
        self.assertEqual(len(self.orders(game, "brew_drink")), 2)

    def test_a_pending_one_shot_is_topped_up_by_the_harvest_it_does_not_cover(self):
        # hint std OP1-4 on b796327: the 3-brew one-shot sat at left 1 from day 84 to 100 while the brewable stock
        # rose 5 -> 17 beside 19 empty barrels and rotted; the guard tops up the uncovered excess
        ov, game = self.ov_base()
        self.step(ov, 62, pb=5, barrels=9)
        self.assertEqual(self.orders(game, "brew_drink"), [{"recipe": "brew_drink", "amount": 3}])
        oid = ov.key_order["o_brew_rot"]
        pend = [{"id": oid, "recipe": "brew_drink", "left": 1}]
        self.step(ov, 64, pb=17, barrels=19, orders=pend)
        # min(8 - 1, 17 - 2 - 1, 19 - 1) = 7 on top of the 1 still pending
        self.assertEqual(self.orders(game, "brew_drink")[-1], {"recipe": "brew_drink", "amount": 7})
        oid2 = ov.key_order["o_brew_rot"]
        both = pend + [{"id": oid2, "recipe": "brew_drink", "left": 7}]
        self.step(ov, 66, pb=17, barrels=19, orders=both)
        self.assertEqual(len(self.orders(game, "brew_drink")), 2)   # 8 pending: the one-shot cap is full

    # embark stock already rotten (hint MY1-2 starts at plants_rotten 8): the first load is only the baseline
    def test_the_first_load_is_the_baseline(self):
        ov, game = self.ov()
        self.step(ov, 0, rot=8, pb=17, barrels=40)
        self.assertFalse(ov.rot_seen)
        self.step(ov, 3, rot=8, pb=13, barrels=40)
        self.assertFalse(ov.rot_seen)
        self.assertEqual(game.calls, [])
        self.step(ov, 8, rot=11, pb=10, barrels=40)
        self.assertTrue(ov.rot_seen)

    # the hint MY1-3 fort's lone rotten plant (0 -> 1 on d127) does not arm it
    def test_a_single_rotten_plant_does_not_arm(self):
        ov, game = self.ov(days=216)
        self.step(ov, 120, days=216, rot=0, pb=3)
        self.step(ov, 127, days=216, rot=1, pb=3)
        self.assertFalse(ov.rot_seen)
        self.assertEqual(game.calls, [])

    # the 100-point MY1 forts: plants 40-67 standing for 200 days, never rotten — nothing changes
    def test_a_fort_without_rot_is_untouched(self):
        ov, game = self.ov(days=216)
        for day in (40, 80, 120):
            self.step(ov, day, days=216, rot=0, pb=50, barrels=3)
        self.assertFalse(ov.rot_seen)
        self.assertEqual(game.calls, [])

    def test_lab_tasks_never_arm(self):
        ov, game = self.ov(days=60)
        self.step(ov, 28, days=60, hands_off=22, rot=0)
        self.step(ov, 30, days=60, hands_off=20)
        self.assertFalse(ov.rot_seen)
        self.assertEqual(game.calls, [])
        ov2, game2 = self.ov(days=336)
        self.step(ov2, 28, hands_off=22, rot=0)
        self.step(ov2, 30, hands_off=20)   # a hands-off window keeps window_supply its sole manager
        self.assertEqual(game2.calls, [])

    def test_no_still_or_carpenter_no_orders(self):
        ov, game = self.ov_base()
        self.step(ov, 62, barrels=5, workshops=("Kitchen",))
        self.assertTrue(ov.rot_seen)
        self.assertEqual(game.calls, [])

    def test_no_logs_no_barrel_order(self):
        ov, game = self.ov_base()
        self.step(ov, 62, logs=3)
        self.assertEqual(self.orders(game, "make_barrel"), [])

    def test_caravan_arrival_jump_is_skipped(self):
        ov, game = self.ov_base()
        self.step(ov, 160, pb=2, barrels=4)
        game.calls.clear()
        ov.load(resp(162, pb=40, barrels=4))
        ov.caravan_active, ov.caravan_arrival_day = True, 162
        ov.count = 0
        ov.rot_guard()
        self.assertEqual(game.calls, [])

    def test_inside_f_a_falling_food_leg_keeps_its_plants(self):
        ov, game = self.ov_base()
        self.step(ov, 62)
        game.calls.clear()
        ov.load(resp(320, pb=10, barrels=10, drink=400, food=60))
        ov.stock_hist.clear()
        for i in range(10):   # food falling, drink holding: food is the min leg
            ov.stock_hist.append((311 + i, 400, 90 - 3 * i, 20))
        ov.count = 0
        ov.rot_guard()
        self.assertEqual(self.orders(game, "brew_drink"), [])

    # CX_REVIEW P1-6: an armed harvest-closed hold (or the reserve build) bounds the guard by the F reserve
    def test_an_armed_hold_keeps_its_reserve_from_the_rot_guard(self):
        ov, game = self.ov_base()
        self.step(ov, 62)
        game.calls.clear()
        ov.load(resp(240, pb=30, barrels=20, cit=10))
        ov.count = 0
        ov.hold_armed = True
        ov.hold_active = lambda: True
        floor = ov.plant_floor()
        self.assertGreater(floor, harness.ROT_KEEP)
        risk = max(harness.ALLOC_BREW_MAX, ov.aged_plants())   # cx rot shot: every aged plant over the floor
        ov.rot_guard()
        self.assertEqual(self.orders(game, "brew_drink"),
                         [{"recipe": "brew_drink", "amount": min(risk, 30 - floor)}]
                         if 30 - floor >= 1 else [])
        ov2, game2 = self.ov_base()
        self.step(ov2, 62)
        game2.calls.clear()
        ov2.load(resp(240, pb=8, barrels=20, cit=10))
        ov2.count = 0
        ov2.hold_active = lambda: True
        ov2.rot_guard()
        self.assertEqual(self.orders(game2, "brew_drink"), [])   # 8 plants, all inside the hold's reserve

    def test_the_reserve_build_window_alone_keeps_rot_keep(self):
        """The record case (OP1-0 d232 sits in the reserve-build window): a rotting reserve is still brewed."""
        ov, game = self.ov_base()
        self.step(ov, 62)
        game.calls.clear()
        self.step(ov, 232, drink=407, food=79, cit=23, pb=12, rot=4, barrels=17)
        self.assertTrue(ov.reserve_build())
        self.assertEqual(ov.rot_keep(), harness.ROT_KEEP)

    def test_plan_runs_the_guard(self):
        ov, game = self.ov_base()
        ov.load(resp(62, pb=20, barrels=6))
        ov.count = 0
        ov.plan()
        self.assertIn("o_brew_rot", ov.key_order)


class CookFoodNotDuplicated(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def test_an_unvalidated_own_o_cook_food_blocks_the_re_add(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=336)
        ov.load(resp(232, cit=23, drink=2000, food=79, pb=0, rot=0))
        ov.food_hist.clear()
        for i in range(14):
            ov.food_hist.append((219 + i, 120 - 3 * i, 2000))
        ov.count = 0
        ov.food_security()
        cooks = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "cook_meal"]
        self.assertEqual(len(cooks), 1)
        oid = ov.key_order["o_cook_food"]
        # a week later the order is on the book, not yet validated: active false
        ov.load(resp(239, cit=23, drink=2000, food=79, pb=0, rot=0, orders=[
            {"id": oid, "recipe": "cook_meal", "repeat": "daily", "active": False, "validated": False, "left": 2,
             "when": [{"item_type": "FOOD", "test": "LessThan", "value": 200, "stock": "prepared_meals"}]}]))
        ov.food_hist.clear()
        for i in range(14):
            ov.food_hist.append((226 + i, 120 - 3 * i, 2000))
        ov.count = 0
        ov.last.pop("o_cook_food", None)
        ov.food_security()
        cooks = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "cook_meal"]
        self.assertEqual(len(cooks), 1)


if __name__ == "__main__":
    unittest.main()


class BarrelNeed(unittest.TestCase):
    """CX_REVIEW P1-5: o_barrel_need sizes the batch to the brew on the book (brew_planned) minus the empty
    barrels, and takes logs only above logs_guard() (beds, tables, chairs first)."""
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def run_supply(self, orders=(), pb=50, barrels=2, logs=300, drink=229, cit=7, beds=None, days=216):
        game = FakeGame()
        ov = harness.Overseer(game, days=days)
        r = resp(100, pb=pb, barrels=barrels, logs=logs, drink=drink, cit=cit, orders=orders)
        if beds is not None:
            r["observation"]["stocks"].update(beds=beds, tables=20, chairs=20)
        ov.load(r)
        ov.count = 0
        ov.supply()
        return ov, [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "make_barrel"
                    and not a.get("repeat")]

    def test_standing_plants_alone_order_no_barrels(self):
        # the 100-point MY1 shape: plants standing, no brew job on the book (drink at its cap)
        ov, one = self.run_supply(orders=[{"id": 1, "recipe": "brew_drink", "repeat": "daily", "left": 5, "total": 5,
                                           "when": [{"item_type": "DRINK", "test": "LessThan", "value": 200}]}])
        self.assertEqual(ov.brew_planned(), 0)
        self.assertEqual(one, [])

    def test_the_backlog_sets_the_batch(self):
        # the OP1-4 shape: one-shot brew jobs waiting with barrels at 1
        ov, one = self.run_supply(barrels=1, orders=[{"id": 1, "recipe": "brew_drink", "left": 7},
                                                     {"id": 2, "recipe": "brew_drink", "left": 5}])
        self.assertEqual(ov.brew_planned(), 12)
        self.assertEqual(one, [{"recipe": "make_barrel", "amount": 10}])
        ov, one = self.run_supply(barrels=1, orders=[{"id": 1, "recipe": "brew_drink", "left": 6}])
        self.assertEqual(one, [{"recipe": "make_barrel", "amount": 5}])

    def test_a_firing_standing_counts(self):
        ov, one = self.run_supply(barrels=0, drink=100, orders=[
            {"id": 1, "recipe": "brew_drink", "repeat": "daily", "left": 6, "total": 6,
             "when": [{"item_type": "DRINK", "test": "LessThan", "value": 200}]}])
        self.assertEqual(ov.brew_planned(), 6)
        self.assertEqual(one, [{"recipe": "make_barrel", "amount": 6}])

    def test_full_year_keeps_barrels_ahead_of_the_harvest(self):
        # cx: OP1 (336 days) — the standing plants alone call for barrels before any rot shows
        ov, one = self.run_supply(barrels=2, pb=12, days=336)
        self.assertEqual(one, [{"recipe": "make_barrel", "amount": 10}])

    def test_housing_keeps_its_logs(self):
        ov, one = self.run_supply(barrels=0, logs=30, beds=0, orders=[{"id": 1, "recipe": "brew_drink", "left": 9}])
        self.assertGreaterEqual(ov.logs_guard(), 30)
        self.assertEqual(one, [])
