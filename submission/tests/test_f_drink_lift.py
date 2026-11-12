"""cx F drink lift (hint hard OP1-5 on ba93eee, O 79.2, supply 0.826 on the drink leg): food-lean armed on day 271 at
drink 237 and the F keeper yield latched on day 307 (drink T 352 projected at a 0.75/day drain read off a stretch with
brewing in it, food rising), so nothing brewed in F: drink fell 285 -> 255 (-1.14/day, T 224) beside 4-19 brewable
plump helmets and 14-18 empty barrels while food rose 204 -> 233. From FYIELD_LEAD days before F, while drink's T is
under FYIELD_MARGIN times the cap and food can pay the plants, repeat standings hold drink at its F-entry level
(o_brew_flift) and two firings higher from mid-F (o_brew_flift_mid); the yield latches only on a falling food record
with drink's T FYIELD_MARGIN times over. No game or network."""
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


def resp(day, days=336, cit=21, drink=285, food=204, pb=10, orders=()):
    stocks = {"drink": drink, "food_edible": food, "prepared_meals": 190, "plants_brewable": pb, "plants_total": pb,
              "plants_rotten": 0, "barrels_empty": 15, "logs_usable": 43, "seeds": 12, "seeds_by_kind": PLUMP,
              "plants_by_kind": {"plump helmet": {"n": pb, "brewable": True, "cookable": True}},
              "furniture_free": {}}
    obs = {"date": {"abs_tick": day * harness.DAY, "day_of_year": (day + 15) % harness.YEAR_DAYS},
           "administrators": {"citizens": cit}, "stocks": stocks, "map": {"sites": []}, "zones": [],
           "furniture": [], "workshops": [{"type": w, "built": True} for w in ("Carpenters", "Still", "Kitchen")],
           "orders": list(orders), "farm_plots": [{"id": 1, "z": 161, "seeds_or_crops_in_plot": 5}],
           "wealth": {"created": 17000}}
    return {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": days - day}


def standing(oid, below, amount=2):
    return {"id": oid, "recipe": "brew_drink", "job": "CustomReaction", "left": amount, "total": amount,
            "repeat": "daily",
            "when": [{"item_type": "DRINK", "test": "LessThan", "value": below, "stock": "drink"},
                     {"item_type": "PLANT", "test": "AtLeast", "value": 1, "reaction_product": "DRINK_MAT",
                      "stock": "plants_brewable"},
                     {"item_type": "BARREL", "test": "AtLeast", "value": 1, "flags": ["empty"],
                      "stock": "barrels_empty"}]}


# hint hard OP1-5 on ba93eee, the logged looks (day, drink, food): the pre-F hump of a seed-recycle burst, then F
OP15 = [(277, 237, 183), (278, 237, 187), (279, 237, 182), (280, 237, 176), (281, 235, 204), (282, 228, 210), (284, 244, 214), (286, 258, 219), (287, 264, 214), (289, 276, 218),
        (291, 291, 212), (293, 306, 215), (296, 306, 218), (298, 306, 203), (300, 296, 196), (301, 294, 198),
        (303, 292, 198), (305, 288, 205), (307, 285, 204), (308, 285, 200), (309, 285, 201), (310, 285, 202),
        (311, 285, 204), (312, 285, 206), (313, 285, 201), (315, 285, 202), (317, 276, 209), (319, 275, 215),
        (321, 271, 212), (322, 269, 210), (324, 266, 211), (326, 264, 208)]


class FDrinkLift(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, looks, days=336, lean=None):
        game = FakeGame()
        ov = harness.Overseer(game, days=days)
        for day, drink, food in looks:
            ov.load(resp(day, days=days, drink=drink, food=food))
        if lean is not None:
            ov.lean_drink = lean
        ov.count = 0
        return ov, game

    def lifts(self, game):
        return [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"
                and a.get("repeat") == "daily" and a.get("amount") == harness.LEAN_BREW_AMOUNT]

    def test_op15_the_yield_does_not_latch_on_a_rising_food_record(self):
        # day 307 of the run: drink T 352 >= 336 at the 0.75/day drain, food's T infinite -> it latched (the fault)
        ov, _ = self.overseer([p for p in OP15 if p[0] <= 307], lean=237)
        self.assertFalse(ov.f_keeper_yield())
        self.assertIsNone(ov.f_yield_food_t)

    def test_op15_the_lift_stands_at_the_window_entry_level(self):
        ov, game = self.overseer([p for p in OP15 if p[0] <= 305], lean=237)
        ov.f_drink_lift()
        lifts = self.lifts(game)
        self.assertEqual(len(lifts), 1)
        self.assertEqual(lifts[0]["when"][0], {"stock": "drink", "below": 288})
        self.assertEqual(lifts[0]["when"][1], {"stock": "plants_brewable", "at_least": 1})
        self.assertEqual(ov.key_order.get("o_brew_flift"), 701)

    def test_op15_the_level_freezes_at_the_first_look_in_the_window(self):
        ov, _ = self.overseer([p for p in OP15 if p[0] <= 305])
        self.assertEqual(ov.f_lift_level(), 288)
        ov.load(resp(310, drink=280, food=215))
        self.assertEqual(ov.f_lift_level(), 288)

    def test_op15_mid_f_adds_the_step(self):
        ov, game = self.overseer([p for p in OP15 if p[0] <= 305])
        ov.f_drink_lift()
        lift = ov.key_order["o_brew_flift"]
        for day, drink, food in [p for p in OP15 if 305 < p[0] <= 319]:
            ov.load(resp(day, drink=drink, food=food, orders=[standing(lift, 288)]))
            ov.f_drink_lift()
        lifts = self.lifts(game)
        self.assertEqual([a["when"][0]["below"] for a in lifts], [288, 308])
        self.assertIn("o_brew_flift_mid", ov.key_order)

    def test_not_before_the_window(self):
        ov, game = self.overseer([p for p in OP15 if p[0] <= 301])   # left 35 > 28 + FYIELD_LEAD
        self.assertIsNone(ov.f_lift_level())
        ov.f_drink_lift()
        self.assertEqual(self.lifts(game), [])

    def test_falling_food_keeps_the_plants_food(self):
        # food falls 2/day over F (T ~ 80): the lift would spend the min leg
        looks = [(305 + i, 290 - i, 160 - 2 * i) for i in range(0, 12)]
        ov, game = self.overseer(looks)
        self.assertIsNone(ov.f_lift_level())
        ov.f_drink_lift()
        self.assertEqual(self.lifts(game), [])

    def test_a_standing_lift_is_cut_when_food_turns_the_falling_leg(self):
        ov, game = self.overseer([p for p in OP15 if p[0] <= 305])
        ov.f_drink_lift()
        lift = ov.key_order["o_brew_flift"]
        looks = [(307 + i, 285, 204 - 3 * i) for i in range(0, 9)]   # F's own record: food -3/day over 8 days
        for day, drink, food in looks:
            ov.load(resp(day, drink=drink, food=food, orders=[standing(lift, 288)]))
            ov.f_drink_lift()
        self.assertIn(("cancel_order", {"order_id": lift}), game.calls)

    def test_a_short_f_record_does_not_cut_it(self):
        # F's first looks, food 204/200/201/202 (the run's own), read T 337 < FLIFT_FOOD_T: too short to cut
        ov, game = self.overseer([p for p in OP15 if p[0] <= 305])
        ov.f_drink_lift()
        lift = ov.key_order["o_brew_flift"]
        for day, drink, food in [p for p in OP15 if 305 < p[0] <= 310]:
            ov.load(resp(day, drink=drink, food=food, orders=[standing(lift, 288)]))
            ov.f_drink_lift()
        self.assertNotIn(("cancel_order", {"order_id": lift}), game.calls)

    def test_the_lean_keeper_cancel_leaves_the_lift(self):
        ov, game = self.overseer([p for p in OP15 if p[0] <= 305])
        ov.f_drink_lift()
        lift = ov.key_order["o_brew_flift"]
        ov.lean_drink = 237
        ov.load(resp(307, drink=285, food=204, orders=[standing(lift, 288), standing(55, 464)]))
        ov.lean_drink = ov.lean_drink or 237
        game.calls.clear()
        ov.lean_supply()
        if ov.food_lean():
            self.assertIn(("cancel_order", {"order_id": 55}), game.calls)
        self.assertNotIn(("cancel_order", {"order_id": lift}), game.calls)

    def test_the_latched_yield_holds_the_lift_off(self):
        ov, game = self.overseer([p for p in OP15 if p[0] <= 305])
        ov.f_yield_food_t = 200.0
        self.assertIsNone(ov.f_lift_level())
        ov.f_drink_lift()
        self.assertEqual(self.lifts(game), [])

    def test_the_harvest_hold_tends_f_itself_unless_lean(self):
        ov, game = self.overseer([p for p in OP15 if p[0] <= 305])
        ov.hold_armed = True
        ov.lean_drink = None
        if not ov.food_lean():
            self.assertIsNone(ov.f_lift_level())

    def test_lab_task_never_lifts(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=60)
        for day in (50, 52, 54):
            r = resp(day, days=60, food=70 + day)
            r["hands_off_in_days"] = 0
            ov.load(r)
        self.assertIsNone(ov.f_lift_level())

    def test_the_last_look_neither_adds_nor_cuts(self):
        ov, game = self.overseer([p for p in OP15 if p[0] <= 305])
        ov.f_drink_lift()
        lift = ov.key_order["o_brew_flift"]
        ov.f_yield_food_t = 100.0
        ov.load(resp(336, drink=255, food=233, orders=[standing(lift, 288)]))
        game.calls.clear()
        ov.f_drink_lift()
        self.assertEqual(game.calls, [])

    def test_drink_far_past_the_cap_does_not_lift(self):
        # hint hard OP1-0 on c44c96b before F: drink 403 for 16 citizens draining ~0.7/day (T ~535), food 30 -> 65
        looks = [(276, 374, 30), (278, 378, 39), (280, 380, 42), (282, 378, 43), (283, 375, 44), (285, 375, 58),
                 (287, 373, 62), (289, 383, 59), (290, 383, 58), (292, 398, 70), (294, 416, 70), (296, 411, 68),
                 (297, 409, 68), (299, 407, 67), (301, 405, 64), (303, 403, 65), (304, 403, 65)]
        game = FakeGame()
        ov = harness.Overseer(game, days=336)
        for day, drink, food in looks:
            ov.load(resp(day, cit=16, drink=drink, food=food))
        self.assertIsNone(ov.f_lift_level())
        ov.f_drink_lift()
        self.assertEqual(self.lifts(game), [])

    def test_margin_still_latches_the_c44c96b_case(self):
        # hint hard OP1-0 on c44c96b: food 67 -> 55 falling fast, drink 402 -> 394 for 16 citizens
        game = FakeGame()
        ov = harness.Overseer(game, days=336)
        for day, drink, food in [(310, 402, 67), (312, 401, 60), (314, 398, 56), (315, 394, 55)]:
            ov.load(resp(day, cit=16, drink=drink, food=food))
        self.assertTrue(ov.f_keeper_yield())
        self.assertIsNone(ov.f_lift_level())


if __name__ == "__main__":
    unittest.main()
