"""cx regressions: the harvest-closed hold (hint MY1-3, std and hard: supply 0.59). The fort's only seeds (cave wheat
and pig tail summer-autumn, sweet pod spring-summer) cannot ripen after autumn day 42 (DFHack autofarm's
is_plantable), F (days 188-216, day_of_year 323-351) is winter, and every late harvest went through the Still at
pb >= 2 so nothing brewed inside F. The hold keeps a brewable reserve from the confirmed close to F and brews it
inside F. No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

FORT3_SEEDS = {"cave wheat": {"n": 6, "seasons": ["summer", "autumn"], "underground": True},
               "pig tail": {"n": 5, "seasons": ["summer", "autumn"], "underground": True},
               "sweet pod": {"n": 3, "seasons": ["spring", "summer"], "underground": True}}
PLUMP = {"plump helmet": {"n": 12, "seasons": ["spring", "summer", "autumn", "winter"], "underground": True}}
MY1_DOY0 = 135   # the measured MY1 run starts at day_of_year 135 (summer)


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": 500 + len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {"units": []}}


def resp(day, days=216, cit=16, drink=116, food=132, pb=0, barrels=6, seeds=FORT3_SEEDS, doy0=MY1_DOY0,
         orders=(), workshops=("Carpenters", "Still", "Kitchen")):
    stocks = {"drink": drink, "food_edible": food, "prepared_meals": 10, "plants_brewable": pb,
              "plants_total": pb, "barrels_empty": barrels, "logs_usable": 60,
              "seeds": sum((v.get("n") or 0) for v in (seeds or {}).values()), "furniture_free": {}}
    if seeds is not None:
        stocks["seeds_by_kind"] = seeds
    obs = {"date": {"abs_tick": day * harness.DAY, "day_of_year": (doy0 + day) % harness.YEAR_DAYS},
           "administrators": {"citizens": cit}, "stocks": stocks, "map": {"sites": []}, "zones": [],
           "furniture": [], "workshops": [{"type": w} for w in workshops], "orders": list(orders),
           "farm_plots": [{"id": i, "z": 143} for i in range(4)]}
    return {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": days - day}


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, days=216, game=None):
        game = game or FakeGame()
        return harness.Overseer(game, days=days), game

    def step(self, ov, day, **kw):
        ov.load(resp(day, days=ov.days, **kw))
        ov.count = 0
        return ov.hold_active()

    def armed(self, day=78, **kw):
        ov, game = self.ov()
        self.step(ov, 75, **kw)
        self.assertTrue(self.step(ov, day, **kw))
        return ov, game


class HarvestClosed(Base):
    # measured: autofarm set pig tail at day 68 (doy 203, autumn day 35), every plot "none" from day 75 (doy 210)
    def test_fort3_closes_at_autumn_day_42_not_before(self):
        ov, _ = self.ov()
        ov.load(resp(68))
        self.assertFalse(ov.harvest_closed())
        ov.load(resp(75))
        self.assertTrue(ov.harvest_closed())

    def test_summer_is_open(self):
        ov, _ = self.ov()
        ov.load(resp(10))
        self.assertFalse(ov.harvest_closed())

    # the 100-point MY1-4 fort: plump helmet grows in every season — never closed
    def test_an_all_season_crop_keeps_it_open(self):
        ov, _ = self.ov()
        for day in (75, 120, 180):
            ov.load(resp(day, seeds=dict(FORT3_SEEDS, **PLUMP)))
            self.assertFalse(ov.harvest_closed(), day)

    def test_missing_seed_data_is_not_closed(self):
        ov, _ = self.ov()
        ov.load(resp(100, seeds=None))
        self.assertFalse(ov.harvest_closed())
        ov.load(resp(100, seeds={"cave wheat": {"n": 4}}))   # no seasons: unknown
        self.assertFalse(ov.harvest_closed())

    # the last 15 days of spring cannot ripen a sweet pod before the run ends
    def test_a_season_too_short_to_ripen_does_not_reopen(self):
        ov, _ = self.ov()
        ov.load(resp(150))
        self.assertTrue(ov.harvest_closed())

    def test_without_day_of_year_the_run_day_stands_in(self):
        ov, _ = self.ov()
        r = resp(75)
        del r["observation"]["date"]["day_of_year"]
        ov.load(r)
        self.assertEqual(ov.game_doy(), 75)


class Hold(Base):
    def test_arming_needs_a_second_closed_load(self):
        ov, _ = self.ov()
        self.assertFalse(self.step(ov, 75))
        self.assertFalse(self.step(ov, 76))   # under HOLD_CONFIRM_DAYS
        self.assertTrue(self.step(ov, 78))

    # OP1 fort 1 day 224: one load read the winter crop's seeds at 0, the next had them back
    def test_a_lone_closed_sample_does_not_arm(self):
        ov, _ = self.ov()
        self.assertFalse(self.step(ov, 75))
        self.assertFalse(self.step(ov, 79, seeds=dict(FORT3_SEEDS, **PLUMP)))
        self.assertFalse(self.step(ov, 82))
        self.assertFalse(ov.hold_armed)

    def test_reserve_covers_f_with_margin(self):
        ov, _ = self.armed()
        # cx MY1 supply plan: the mid-F brews that turn the drink decline (from the dry level) into a slope
        # F_SLOPE_MARGIN over the score's line, plus F_PLAN_SPARE. 16 citizens: 0.96/day -> 5; the forecast's wave
        # still to come (a 16-citizen start took one already, WAVES_EXPECTED 2): 22 x 0.06 = 1.32/day -> 6
        self.assertEqual(ov.f_mid_need(0.96), 5)
        self.assertEqual(ov.f_mid_need(0.84), 4)
        self.assertEqual(ov.pop_forecast(), 22)
        self.assertEqual(ov.f_mid_need(1.32), 6)
        self.assertEqual(ov.hold_reserve(), 6 + harness.F_PLAN_SPARE)

    def test_floors_while_holding(self):
        ov, _ = self.armed()
        r = ov.hold_reserve()
        self.assertEqual(ov.brew_floor(), r + 1)   # cx MY1 supply plan: one a firing over the reserve
        self.assertEqual(ov.brew_amount(), 1)
        self.assertGreaterEqual(ov.plant_floor(), r)
        self.assertEqual(ov.cook_floor(), r + 2)
        pb = [c for c in ov.brew_when() if c["stock"] == "plants_brewable"][0]
        self.assertEqual(pb["at_least"], r + 1)
        # the cap: the rest of the run's drink at the plan's rate (22 x 0.06 x 138 days left)
        self.assertEqual(ov.brew_when()[0], {"stock": "drink", "below": 183})

    def test_the_standing_brew_is_added_with_the_hold_floor(self):
        ov, game = self.armed()
        ov.supply()
        brew = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"]
        self.assertEqual(len(brew), 1)
        pb = [c for c in brew[0]["when"] if c["stock"] == "plants_brewable"][0]
        self.assertEqual(pb["at_least"], ov.hold_reserve() + 1)

    def test_sticky_once_armed(self):
        ov, _ = self.armed()
        self.assertTrue(self.step(ov, 120, seeds=dict(FORT3_SEEDS, **PLUMP)))

    def test_a_fort_drinking_dry_before_f_brews_now(self):
        ov, _ = self.armed()
        # 0.06 x 16 x (216 - 100 - 28) = 84 to F's start: under half of it the plants go to the Still now
        self.assertFalse(self.step(ov, 100, drink=40))
        # the plant barrel keep's floor (MY1): o_brew brews 2 a day and leaves one plant in the barrel
        self.assertEqual(ov.brew_floor(), harness.BARREL_KEEP_AMOUNT + harness.BARREL_KEEP)
        self.assertEqual(ov.brew_amount(), harness.BARREL_KEEP_AMOUNT)

    def test_a_short_food_leg_keeps_the_kitchen_open(self):
        ov, _ = self.armed(food=20)
        self.assertTrue(ov.hold_active())
        self.assertEqual(ov.cook_floor(), harness.COOK_PLANTS_RESERVE)

    def test_allocation_cook_one_shot_cooks_the_hold_only_for_a_short_food_leg(self):
        many = dict(FORT3_SEEDS, **{"cave wheat": {"n": 40, "seasons": ["summer", "autumn"]}})   # seeds floor 36
        ov, game = self.armed(food=20, pb=14, seeds=many)
        ov.allocate_plants()
        cook = [a for t, a in game.calls if a.get("recipe") == "cook_meal" and "repeat" not in a]
        brew = [a for t, a in game.calls if a.get("recipe") == "brew_drink"]
        self.assertTrue(cook)
        self.assertFalse(brew)   # the Still side holds the reserve (14 - 11 = 3 only if drink were short)

    def test_lab_tasks_never_hold(self):
        ov, _ = self.ov()
        r = resp(75)
        r["hands_off_in_days"] = 30
        ov.load(r)
        ov.load(dict(resp(78), hands_off_in_days=27))
        self.assertFalse(ov.hold_active())

    def test_endgame_brew_keeps_the_reserve(self):
        ov, game = self.armed()
        self.assertTrue(self.step(ov, 160, pb=5))   # 56 days left: endgame, before F
        ov.endgame_supply()
        end = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"
               and a.get("repeat") == "daily"]
        self.assertTrue(end)
        pb = [c for c in end[-1]["when"] if c["stock"] == "plants_brewable"][0]
        self.assertEqual(pb["at_least"], ov.hold_reserve() + 4)

    def test_winter_plan_brew_keeps_the_reserve(self):
        ov, game = self.armed()
        self.step(ov, 100, drink=140)
        ov.winter_plan()
        wb = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"]
        self.assertTrue(wb)
        self.assertEqual(wb[0]["when"][0], {"stock": "plants_brewable", "at_least": ov.hold_reserve() + 4})


class Release(Base):
    """cx: hold_supply's one-brew-a-day standings replace the one-shot release 2 days into F (hint hard MY1-3
    cxe538c50: loads at days 178/192/206/215, drink 75 -> 49 in F)."""

    def brews(self, game):
        return {a["when"][0]["below"]: a for t, a in game.calls
                if t == "add_order" and a.get("recipe") == "brew_drink" and a.get("repeat") == "daily"
                and a.get("amount") == 1}

    def test_the_dry_floor_standing_is_added_on_arming(self):
        ov, game = self.armed()
        ov.hold_supply()
        self.assertEqual(list(self.brews(game)), [5])   # 5 days x 16 x 0.06 = 4.8 -> floor 5
        a = self.brews(game)[5]
        self.assertEqual(a["when"][1:], [{"stock": "plants_brewable", "at_least": 1},
                                         {"stock": "barrels_empty", "at_least": 1}])

    def test_a_standing_on_the_book_is_not_added_again(self):
        ov, game = self.armed()
        ov.hold_supply()
        oid = ov.key_order["o_brew_dry"]
        self.step(ov, 90, orders=[{"id": oid, "recipe": "brew_drink", "repeat": "daily"}])
        n = len(game.calls)
        ov.hold_supply()
        self.assertEqual(len(game.calls), n)

    def test_no_f_standing_before_f(self):
        ov, game = self.armed()
        self.step(ov, 150, pb=10, barrels=20)   # 66 left: not yet inside HOLD_PREP_DAYS of F
        ov.hold_supply()
        self.assertEqual(list(self.brews(game)), [5])

    def test_no_prep_standing_on_my1(self):
        # cx MY1 supply plan: a pre-F brew earns the slope nothing; the plan's brews land at mid-F
        ov, game = self.armed()
        self.step(ov, 178, pb=12, drink=60, barrels=20)
        ov.hold_supply()
        self.assertEqual(sorted(self.brews(game)), [5])
        self.assertNotIn("o_brew_pre", ov.key_order)
        # drink 60 at 0.96/day stands at 36.96 on mid-F (d202): the standing fires there
        mid = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink" and a["when"][0]["below"] == 37]
        self.assertEqual([a["amount"] for a in mid], [ov.f_brew_need()[0]])

    def test_no_prep_standing_when_the_projection_is_dry(self):
        ov, game = self.armed()
        self.step(ov, 178, pb=12, drink=12, barrels=20)
        ov.hold_supply()
        self.assertEqual(sorted(self.brews(game)), [5])

    def test_inside_f_one_held_plant_a_day(self):
        ov, game = self.armed()
        self.assertTrue(self.step(ov, 192, pb=11, drink=20, barrels=20))   # 24 left: inside F, still holding
        # cx MY1 supply plan: inside F every free plant is the plan's (no other consumer)
        self.assertEqual(ov.hold_reserve(), 11)
        self.assertEqual(ov.brew_floor(), 11 + 1)
        self.assertEqual(ov.plant_floor(), 11)
        ov.hold_supply()
        self.assertNotIn(600, self.brews(game))
        # drink 20 at 0.96/day stays over the dry level (4.8) to mid-F (d202): the need lands there
        need, land, rate, _ = ov.f_brew_need()
        self.assertEqual(land, 202)
        self.assertGreaterEqual(need, 4)
        mid = [a for t, a in game.calls if a.get("recipe") == "brew_drink" and a.get("repeat") and a.get("amount") > 1
               or (a.get("recipe") == "brew_drink" and a.get("repeat") and a["when"][0]["below"] > 5)]
        self.assertEqual([a["amount"] for a in mid], [need])

    def test_unarmed_forts_get_no_hold_standings(self):
        ov, game = self.ov()
        self.step(ov, 199, pb=10, barrels=20, seeds=PLUMP)
        ov.hold_supply()
        self.assertFalse(game.calls)

    def test_a_fort_without_a_still_gets_none(self):
        ov, game = self.armed(workshops=("Carpenters", "Kitchen"))
        ov.hold_supply()
        self.assertFalse(game.calls)

    def test_plan_runs_the_hold_supply(self):
        ov, game = self.armed()
        self.step(ov, 199, pb=6, barrels=20)
        ov.plan()
        self.assertIn("o_brew_midshot", ov.key_order)   # 11 days into F: the plan's one-shot

    def test_no_arming_inside_f(self):
        ov, _ = self.ov()
        self.assertFalse(self.step(ov, 190))
        self.assertFalse(self.step(ov, 195))
        self.assertFalse(ov.hold_armed)


class HoldMisc(Base):
    def test_food_plants_stay_food_while_food_is_the_falling_min_leg(self):
        ov, game = self.armed()
        r = resp(200, pb=10, barrels=20)
        r["observation"]["stocks"]["plants_by_kind"] = {"plump helmet": {"n": 10, "brewable": True, "cookable": True}}
        ov.load(r)
        ov.food_min_leg = lambda: True
        ov.hold_supply()
        self.assertNotIn("o_brew_midshot", ov.key_order)
        ov.food_min_leg = lambda: False
        ov.hold_supply()
        self.assertIn("o_brew_midshot", ov.key_order)

    def test_non_food_plants_brew_whatever_the_food_leg(self):
        ov, game = self.armed()
        r = resp(200, pb=10, barrels=20)
        r["observation"]["stocks"]["plants_by_kind"] = {"cave wheat": {"n": 10, "brewable": True, "cookable": False}}
        ov.load(r)
        ov.food_min_leg = lambda: True
        ov.hold_supply()
        self.assertIn("o_brew_midshot", ov.key_order)

    # the hold's recut only raises o_brew's plant floor, so the caravan does not hold it off
    def test_the_hold_recuts_the_standing_while_a_caravan_stays(self):
        ov, game = self.armed()
        ov.key_order["o_brew"] = 83
        when = [{"item_type": "DRINK", "test": "LessThan", "value": 320, "stock": "drink"},
                {"item_type": "PLANT", "flags": ["unrotten"], "reaction_product": "DRINK_MAT", "test": "AtLeast",
                 "value": 2, "stock": "plants_brewable"},
                {"item_type": "BARREL", "flags": ["empty"], "test": "AtLeast", "value": 1, "stock": "barrels_empty"}]
        self.step(ov, 82, orders=[{"id": 83, "recipe": "brew_drink", "repeat": "daily", "when": when}])
        ov.caravan_active = True
        self.assertTrue(ov.sync_brew())
        self.assertIn(("cancel_order", {"order_id": 83}), game.calls)

    def test_without_the_hold_the_caravan_still_holds_the_recut(self):
        ov, game = self.ov()
        ov.key_order["o_brew"] = 83
        self.step(ov, 82, seeds=PLUMP, orders=[{"id": 83, "recipe": "brew_drink", "repeat": "daily", "when": [
            {"item_type": "DRINK", "test": "LessThan", "value": 100, "stock": "drink"}]}])
        ov.caravan_active = True
        self.assertFalse(ov.sync_brew())
        self.assertFalse(game.calls)


class ForeignBrew(Base):
    """cx: hint hard MY1-3 cxe538c50 order 87, the model's "brew_drink 5 daily, drink below 60" with no plant floor,
    would take the held plants once drink sags under 60 before F."""

    def model_order(self, oid=87, when=None):
        return {"id": oid, "recipe": "brew_drink", "repeat": "daily", "left": 5, "when": when if when is not None else
                [{"item_type": "DRINK", "test": "LessThan", "value": 60, "flags": [], "stock": "drink"}]}

    def test_a_floorless_model_brew_is_cancelled_while_holding(self):
        ov, game = self.armed()
        self.step(ov, 120, pb=12, orders=[self.model_order()])
        ov.hold_supply()
        self.assertIn(("cancel_order", {"order_id": 87}), game.calls)

    def test_a_model_brew_with_a_reserve_floor_stays(self):
        ov, game = self.armed()
        floor = [{"item_type": "DRINK", "test": "LessThan", "value": 60, "stock": "drink"},
                 {"item_type": "PLANT", "flags": ["unrotten"], "reaction_product": "DRINK_MAT", "test": "AtLeast",
                  "value": 20, "stock": "plants_brewable"}]
        self.step(ov, 120, pb=12, orders=[self.model_order(when=floor)])
        ov.hold_supply()
        self.assertNotIn("cancel_order", [t for t, _ in game.calls])

    def test_the_plan_s_own_orders_are_never_cancelled(self):
        # cx m13many: the plan's keys (F_PLAN_KEYS) and the regrow lend's brews stay; another layer order is trimmed
        # like the model's (838106a hard: o_brew_alloc's one-shot of 5 brewed on after the hold armed on d88)
        for keep in ("o_brew_dry", "o_brew_mid", "recycle"):
            ov, game = self.armed()
            self.step(ov, 120, pb=12, orders=[self.model_order()])
            ov.owned.add(87)
            if keep == "recycle":
                ov.recycle_brews.add(87)
            else:
                ov.key_order[keep] = 87
            ov.hold_supply()
            self.assertNotIn(("cancel_order", {"order_id": 87}), game.calls, keep)

    def test_another_layer_order_is_trimmed_to_the_hold(self):
        ov, game = self.armed()
        self.step(ov, 120, pb=12, orders=[self.model_order()])
        ov.owned.add(87)
        ov.key_order["o_brew_alloc"] = 87
        ov.hold_supply()
        self.assertIn(("cancel_order", {"order_id": 87}), game.calls)

    def test_inside_f_the_model_brew_is_cancelled_on_my1(self):
        # cx MY1 supply plan: inside F every free plant is the plan's (one a day from F's start brewed 8 of 11 on
        # 7c43df4 std: drink's slope paid for with food's)
        ov, game = self.armed()
        self.step(ov, 200, pb=12, orders=[self.model_order()])
        ov.hold_supply()
        self.assertIn(("cancel_order", {"order_id": 87}), game.calls)

    def test_unarmed_forts_keep_the_model_brew(self):
        ov, game = self.ov()
        self.step(ov, 120, pb=12, seeds=PLUMP, orders=[self.model_order()])
        ov.hold_supply()
        self.assertFalse(game.calls)


if __name__ == "__main__":
    unittest.main()
