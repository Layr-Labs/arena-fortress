"""cx regressions: the small hold and the plant barrel keep (hint hard MY1-3 on ba93eee, supply 0.552). The hold
carried 2 barrelled pig tails into the pre-F window and o_brew_pre brewed them on d178/d185, so F held no plant
(drink 64 -> 36 over F). The score's drink slope is least squares over A + F, so a pre-F brew earns nothing and a
brew at mid-F the most; a hold too small for the one-a-day F release goes to mid-F together. And o_brew (amount 10,
floor 2) emptied the hand-over's plant barrel on days 0-6 of all four MY1-3 records; on MY1 it now fires 2 over a
floor of 3. No game or network."""
import sys
import unittest
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness
from test_harvest_hold import Base, FakeGame, resp, FORT3_SEEDS

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


def slope_gain(days, f=28, s=5):
    """The least-squares slope over F (points at 0..f) of s-drink steps at the given days into F."""
    xs = list(range(f + 1))
    mx = sum(xs) / len(xs)
    vx = sum((x - mx) ** 2 for x in xs)
    ys = [s * sum(1 for p in days if x >= p) for x in xs]
    my = sum(ys) / len(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / vx


class SlopeArithmetic(unittest.TestCase):
    # the arithmetic the plan stands on, against the score's own least squares
    def test_pre_f_and_first_day_brews_earn_nothing_mid_f_the_most(self):
        self.assertAlmostEqual(slope_gain([0, 0]), 0.0)
        self.assertGreater(slope_gain([14, 14]), slope_gain([2, 3]) * 2)
        self.assertGreater(slope_gain([14] * 4), 1.0)          # 4 plants at mid-F turn a 1.0/day decline
        self.assertLess(slope_gain(list(range(2, 8))), 1.0)    # 6 one a day from day 2 do not

    def test_the_plan_formula_matches_the_least_squares(self):
        f = 28
        for days in ([5], [14], [3, 9, 20]):
            want = sum(6.0 * 5 * p * (f - p) / f ** 3 for p in days)
            self.assertAlmostEqual(slope_gain(days), want, delta=0.03)


class SmallHold(Base):
    def armed17(self, **kw):
        ov, game = self.ov()
        self.step(ov, 75, cit=17, **kw)
        self.assertTrue(self.step(ov, 78, cit=17, **kw))
        return ov, game

    def standings(self, game):
        return {a["when"][0]["below"]: a for t, a in game.calls
                if t == "add_order" and a.get("recipe") == "brew_drink" and a.get("repeat") == "daily"}

    def shots(self, game):
        return [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"
                and "repeat" not in a]

    # ba93eee hard d180: 2 held, 17 citizens, drink 66 -> no pre-F brew; the whole hold at the mid-F level
    def test_two_held_plants_wait_for_mid_f(self):
        ov, game = self.armed17()
        self.assertTrue(self.step(ov, 180, cit=17, pb=2, drink=66, barrels=5))
        self.assertEqual(ov.hold_mid_plan(), 2)
        ov.hold_supply()
        self.assertNotIn("o_brew_pre", ov.key_order)
        self.assertNotIn("o_brew_f", ov.key_order)
        mid = self.standings(game)
        # 17 x 0.06 = 1.02/day over 36 - 28 + 14 = 22 days: 66 - 22.4 = 43.6 -> 44
        self.assertIn(44, mid)
        self.assertEqual(mid[44]["amount"], 2)
        self.assertEqual(mid[44]["when"][1:], [{"stock": "plants_brewable", "at_least": 1},
                                               {"stock": "barrels_empty", "at_least": 1}])

    def test_inside_f_before_mid_no_one_a_day_standing(self):
        ov, game = self.armed17()
        self.assertTrue(self.step(ov, 194, cit=17, pb=2, drink=56, barrels=5))   # 6 days into F
        ov.hold_supply()
        self.assertNotIn("o_brew_f", ov.key_order)
        self.assertIn("o_brew_mid", ov.key_order)
        self.assertFalse(self.shots(game))

    def test_a_load_near_mid_f_brews_the_hold_now(self):
        ov, game = self.armed17()
        self.assertTrue(self.step(ov, 201, cit=17, pb=3, drink=50, barrels=5))   # 13 days into F
        ov.hold_supply()
        self.assertEqual([a["amount"] for a in self.shots(game)], [3])
        self.assertNotIn("o_brew_f", ov.key_order)

    def test_a_prep_standing_on_the_book_is_cut_on_my1(self):
        # cx MY1 supply plan: o_brew_pre is never placed on MY1; one on the book (an older layer's) is cut
        ov, game = self.armed17()
        self.step(ov, 175, cit=17, pb=12, drink=70, barrels=5)
        ov.hold_supply()
        self.assertNotIn("o_brew_pre", ov.key_order)
        ov.key_order["o_brew_pre"] = 77
        self.step(ov, 182, cit=17, pb=2, drink=64, barrels=5,
                  orders=[{"id": 77, "recipe": "brew_drink", "repeat": "daily"}])
        ov.hold_supply()
        self.assertIn(("cancel_order", {"order_id": 77}), game.calls)

    # cx MY1 supply plan: a large hold (ba93eee std: 10 held, 14 citizens) brews only the plan's need at mid-F —
    # the rest stays food (each plant brewed inside F is a food unit lost at the same weight)
    def test_a_large_hold_brews_only_the_need(self):
        ov, game = self.ov()
        self.step(ov, 75, cit=14)
        self.assertTrue(self.step(ov, 78, cit=14))
        self.assertTrue(self.step(ov, 178, cit=14, pb=10, drink=70, barrels=20))
        ov.hold_supply()
        self.assertNotIn("o_brew_pre", ov.key_order)
        need = ov.f_brew_need()[0]
        self.assertLess(need, 10)
        self.assertEqual([a["amount"] for a in self.standings(game).values() if a["amount"] > 1], [need])
        self.assertTrue(self.step(ov, 199, cit=14, pb=10, drink=55, barrels=20))
        ov.hold_supply()
        self.assertNotIn("o_brew_f", ov.key_order)
        self.assertEqual([a["amount"] for a in self.shots(game)], [ov.f_brew_need()[0]])

    def test_the_record_s_net_decline_is_the_projected_rate(self):
        ov, _ = self.armed17()
        for day, drink in ((166, 81), (173, 71), (180, 66)):
            self.step(ov, day, cit=17, pb=2, drink=drink, barrels=5)
        ov.stock_hist.clear()
        for day, drink in ((166, 90), (173, 75), (180, 60)):
            ov.stock_hist.append((day, drink, 150, 100))
        self.assertAlmostEqual(ov.hold_proj_rate(), 30 / 14.0, places=2)
        ov.stock_hist.clear()
        for day, drink in ((166, 60), (173, 60), (180, 61)):   # flat or rising: the hold's rate stands in
            ov.stock_hist.append((day, drink, 150, 100))
        self.assertAlmostEqual(ov.hold_proj_rate(), ov.hold_drink_rate())

    def test_unarmed_forts_have_no_mid_plan(self):
        ov, _ = self.ov()
        self.step(ov, 180, cit=17, pb=2, seeds={"plump helmet": {"n": 12, "seasons": list(harness.SEASON_NAMES)}})
        self.assertIsNone(ov.hold_mid_plan())

    def test_no_mid_standing_when_mid_f_is_projected_dry(self):
        # cx MY1 supply plan: drink 26 at 1.02/day meets the dry level (5.1) about mid-F: a drink trigger there
        # would fire at o_brew_dry's first dip, so the plan waits for the load nearest mid-F (the one-shot)
        ov, game = self.armed17()
        self.assertTrue(self.step(ov, 180, cit=17, pb=2, drink=26, barrels=5))
        ov.hold_supply()
        need, land, rate, _ = ov.f_brew_need()
        self.assertEqual(land, 202)
        self.assertNotIn("o_brew_mid", ov.key_order)
        self.assertFalse(self.shots(game))


class BarrelKeep(Base):
    def test_my1_day_0_brews_two_and_leaves_the_barrel_a_plant(self):
        ov, _ = self.ov()
        ov.load(resp(0, cit=9, drink=23, pb=4))
        self.assertEqual(ov.brew_amount(), harness.BARREL_KEEP_AMOUNT)
        pb = [c for c in ov.brew_when() if c["stock"] == "plants_brewable"][0]
        self.assertEqual(pb["at_least"], harness.BARREL_KEEP_AMOUNT + harness.BARREL_KEEP)

    def test_full_year_runs_keep_the_old_standing(self):
        ov, _ = self.ov(days=336)
        ov.load(resp(0, days=336, cit=7, drink=23, pb=4))
        self.assertEqual(ov.brew_amount(), 10)
        pb = [c for c in ov.brew_when() if c["stock"] == "plants_brewable"][0]
        self.assertEqual(pb["at_least"], 2)

    def test_the_hold_floor_wins(self):
        ov, _ = self.armed()
        self.assertEqual(ov.brew_floor(), ov.hold_reserve() + 1)   # cx MY1 supply plan
        self.assertFalse(ov.barrel_keep())

    # cx 7c43df4 open point: the model's own floor-2 standing stood in for o_brew and could empty the plant barrel
    @staticmethod
    def model_standing(oid=40, amount=3, floor=2, cap=200):
        return {"id": oid, "recipe": "brew_drink", "job": "CustomReaction", "repeat": "daily", "left": amount,
                "total": amount, "active": True, "validated": True,
                "when": [{"stock": "drink", "item_type": "DRINK", "test": "LessThan", "value": cap, "flags": []},
                         {"stock": "plants_brewable", "item_type": "PLANT", "reaction_product": "DRINK_MAT",
                          "test": "AtLeast", "value": floor, "flags": []},
                         {"stock": "barrels_empty", "item_type": "BARREL", "test": "AtLeast", "value": 1,
                          "flags": ["empty"]}]}

    def test_a_low_floor_model_standing_does_not_stand_in_for_o_brew(self):
        ov, game = self.ov()
        ov.load(resp(0, cit=9, drink=23, pb=4, orders=[self.model_standing(amount=3, floor=2, cap=900)]))
        self.assertTrue(ov.barrel_keep())
        self.assertFalse(ov.brew_on_book())
        ov.load(resp(0, cit=9, drink=23, pb=4, orders=[self.model_standing(amount=2, floor=3, cap=900)]))
        self.assertTrue(ov.brew_on_book())          # a firing of 2 over a floor of 3 keeps the barrel's plant

    def test_the_model_brew_that_could_empty_the_barrel_is_refused(self):
        ov, _ = self.ov()
        ov.load(resp(0, cit=9, drink=23, pb=4))
        low = {"recipe": "brew_drink", "amount": 3, "repeat": "daily",
               "when": [{"stock": "plants_brewable", "at_least": 2}]}
        self.assertIn("plants_brewable", ov.hold_veto("add_order", low))
        self.assertIsNotNone(ov.hold_veto("add_order", {"recipe": "brew_drink", "amount": 4}))   # 4 of pb 4
        self.assertIsNotNone(ov.hold_veto("add_manager_order", {"job": "CustomReaction",
                                                                "reaction": "BREW_DRINK_FROM_PLANT", "amount": 4}))
        self.assertIsNone(ov.hold_veto("add_order", {"recipe": "brew_drink", "amount": 3}))      # leaves one
        self.assertIsNone(ov.hold_veto("add_order", dict(low, when=[{"stock": "plants_brewable", "at_least": 4}])))
        self.assertIsNone(ov.hold_veto("add_order", {"recipe": "cook_meal", "amount": 4}))

    def test_a_model_standing_on_the_book_that_would_empty_the_barrel_is_cancelled(self):
        ov, game = self.ov()
        ov.load(resp(5, cit=9, drink=23, pb=4, orders=[self.model_standing(oid=41, amount=3, floor=2),
                                                       self.model_standing(oid=42, amount=2, floor=3)]))
        ov.count = 0
        ov.barrel_cancel()
        self.assertEqual([a for t, a in game.calls if t == "cancel_order"], [{"order_id": 41}])

    def test_no_barrel_veto_on_full_year_or_inside_the_hold(self):
        low = {"recipe": "brew_drink", "amount": 3, "repeat": "daily",
               "when": [{"stock": "plants_brewable", "at_least": 2}]}
        ov, game = self.ov(days=336)
        ov.load(resp(0, days=336, cit=7, drink=23, pb=4, orders=[self.model_standing(amount=3, floor=2)]))
        self.assertIsNone(ov.hold_veto("add_order", low))
        ov.count = 0
        ov.barrel_cancel()
        self.assertEqual(game.calls, [])
        ov, _ = self.armed()
        self.assertFalse(ov.barrel_keep())
        msg = ov.hold_veto("add_order", low)
        self.assertIn(str(ov.hold_reserve()), msg)   # the hold's own veto, not the barrel's

    def test_lab_tasks_unchanged(self):
        ov, _ = self.ov(days=60)
        ov.hands_off = 30
        ov.load(resp(0, days=60, pb=4))
        self.assertFalse(ov.barrel_keep())


if __name__ == "__main__":
    unittest.main()
