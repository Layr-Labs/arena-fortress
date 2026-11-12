"""cx F keeper yield (hint hard OP1-0 on c44c96b, supply 0.76 on the food leg): inside F the food-lean keeper o_brew
(drink below 374) fired on days 315 and 334-335 with drink 394-401 — 900 days at F's drain — while food fell 65 -> 64
over F (-0.37/day, T 174 days). With food falling and the drink stock alone (no brew to the end, drained at the
measured use) still outlasting food's own T, the keeper is cancelled and not re-added. No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

PLUMP = {"plump helmet": {"n": 10, "seasons": ["spring", "summer", "autumn", "winter"], "underground": True}}


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": 700 + len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {"units": []}}


def resp(day, days=336, cit=16, drink=394, food=65, pb=4, orders=()):
    stocks = {"drink": drink, "food_edible": food, "prepared_meals": 50, "plants_brewable": pb, "plants_total": pb,
              "plants_rotten": 0, "barrels_empty": 20, "logs_usable": 43, "seeds": 12, "seeds_by_kind": PLUMP,
              "plants_by_kind": {"plump helmet": {"n": pb, "brewable": True, "cookable": True}},
              "furniture_free": {}}
    obs = {"date": {"abs_tick": day * harness.DAY, "day_of_year": (day + 15) % harness.YEAR_DAYS},
           "administrators": {"citizens": cit}, "stocks": stocks, "map": {"sites": []}, "zones": [],
           "furniture": [], "workshops": [{"type": w, "built": True} for w in ("Carpenters", "Still", "Kitchen")],
           "orders": list(orders), "farm_plots": [{"id": 1, "z": 161, "seeds_or_crops_in_plot": 5}],
           "wealth": {"created": 17000}}
    return {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": days - day}


KEEPER = {"id": 84, "recipe": "brew_drink", "job": "CustomReaction", "left": 2, "repeat": "daily",
          "when": [{"item_type": "DRINK", "test": "LessThan", "value": 374, "stock": "drink"},
                   {"item_type": "PLANT", "test": "AtLeast", "value": 1, "reaction_product": "DRINK_MAT",
                    "stock": "plants_brewable"},
                   {"item_type": "BARREL", "test": "AtLeast", "value": 1, "stock": "barrels_empty"}]}


class FKeeperYield(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def run_to(self, looks, orders=(KEEPER,)):
        game = FakeGame()
        ov = harness.Overseer(game, days=336)
        for day, drink, food in looks:
            ov.load(resp(day, drink=drink, food=food, orders=orders))
        ov.key_order["o_brew"] = 84
        ov.count = 0
        return ov, game

    def brews_added(self, game):
        return [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"]

    def test_food_falling_in_f_with_drink_far_ahead_cancels_the_keeper(self):
        ov, game = self.run_to([(310, 402, 67), (312, 401, 60), (314, 398, 56), (315, 394, 55)])
        self.assertTrue(ov.f_keeper_yield())
        ov.supply()
        self.assertIn(("cancel_order", {"order_id": 84}), game.calls)
        self.assertEqual(self.brews_added(game), [])
        ov2, game2 = self.run_to([(310, 402, 67), (312, 401, 60), (314, 398, 56), (315, 394, 55)], orders=())
        ov2.supply()
        self.assertEqual(self.brews_added(game2), [])     # not re-added while it holds

    def test_before_f_the_keeper_stays(self):
        ov, game = self.run_to([(290, 402, 67), (292, 401, 60), (294, 398, 56), (296, 394, 55)])   # left 40
        self.assertFalse(ov.f_keeper_yield())
        ov.supply()
        self.assertNotIn(("cancel_order", {"order_id": 84}), game.calls)

    def test_food_rising_keeps_the_keeper(self):
        ov, _ = self.run_to([(310, 402, 55), (312, 401, 60), (314, 398, 64), (315, 394, 70)])
        self.assertFalse(ov.f_keeper_yield())

    def test_short_drink_keeps_the_keeper(self):
        # drink 60 for 16 citizens: the stock alone would not outlast food's own T
        ov, _ = self.run_to([(310, 70, 67), (312, 66, 60), (314, 63, 56), (315, 60, 55)])
        self.assertFalse(ov.f_keeper_yield())

    def test_lab_task_never_yields(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=60)
        for day in (50, 52, 54):
            r = resp(day, days=60, food=70 - day)
            r["hands_off_in_days"] = 0
            ov.load(r)
        self.assertFalse(ov.f_keeper_yield())

    def test_latched_through_a_mid_f_food_rise(self):
        # the replay: food rose 55 -> 96 on days 315-320 (fish, a slaughter) and the unlatched rule let the keeper back
        ov, game = self.run_to([(310, 402, 67), (312, 401, 60), (314, 398, 56), (315, 394, 55)])
        self.assertTrue(ov.f_keeper_yield())
        for day, food in ((317, 70), (319, 85), (320, 96)):
            ov.load(resp(day, drink=394 - (day - 315), food=food, orders=()))
            self.assertTrue(ov.f_keeper_yield())
        game.calls.clear()
        ov.supply()
        self.assertEqual(self.brews_added(game), [])

    def test_the_latch_lets_go_when_drink_falls_under_food(self):
        ov, _ = self.run_to([(310, 402, 67), (312, 401, 60), (314, 398, 56), (315, 394, 55)])
        self.assertTrue(ov.f_keeper_yield())
        for day, drink in ((317, 300), (319, 200), (321, 100)):   # drink drains 50/day without brewing
            ov.load(resp(day, drink=drink, food=50, orders=()))
        self.assertFalse(ov.f_keeper_yield())
        self.assertIsNone(ov.f_yield_food_t)

    def test_the_lead_starts_before_f(self):
        # F starts at left 28; the yield may start FYIELD_LEAD days earlier so in-progress brews finish before F
        ov, _ = self.run_to([(300, 402, 67), (302, 401, 60), (304, 398, 56), (305, 397, 55)])
        self.assertTrue(ov.f_keeper_yield())
        ov2, _ = self.run_to([(296, 402, 67), (298, 401, 60), (300, 398, 56), (301, 397, 55)])
        self.assertFalse(ov2.f_keeper_yield())

    def test_drain_from_the_stretch(self):
        pts = [(310, 402, 0, 16, False), (312, 401, 0, 16, False), (314, 398, 0, 16, False),
               (315, 394, 0, 16, False)]
        self.assertAlmostEqual(harness.Overseer.fyield_drain(pts), 8 / 5)
        self.assertIsNone(harness.Overseer.fyield_drain(pts[:2]))
        flat = [(p[0], 400, 0, 16, False) for p in pts]
        self.assertIsNone(harness.Overseer.fyield_drain(flat))


if __name__ == "__main__":
    unittest.main()
