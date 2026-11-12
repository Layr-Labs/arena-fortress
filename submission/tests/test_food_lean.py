"""cx regressions: the food-lean endgame and the crafts' bone fallback (hint hard OP1-0 on e538c50, O 89.0: supply
0.891 — drink 399 -> 406 in F, 20 per citizen, while food sat at 79, 3.95 per citizen, slope a little negative; growth
0.875 — created wealth stopped at ~17.3k from day 279 with the wood crafts cancelled "Needs logs"). Inside LEAN_DAYS of
a full-year open-play run, once drink's leg days are LEAN_AHEAD times food's, o_brew becomes a keeper at the drink of
that day and every other brew order yields, so the harvest's plump helmets stay food; a wood stall opens a bone crafts
standing. No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

PLUMP = {"plump helmet": {"n": 10, "seasons": ["spring", "summer", "autumn", "winter"], "underground": True},
         "sweet pod": {"n": 2, "seasons": ["spring", "summer"], "underground": True}}


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": 700 + len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {"units": []}}


def resp(day, days=336, cit=20, drink=380, food=73, pb=4, seeds=12, barrels=7, rot=0, orders=(), wealth=17244,
         workshops=("Carpenters", "Still", "Kitchen", "Craftsdwarfs"), hands_off=None, plots=(0, 0, 0, 2, 3, 7)):
    stocks = {"drink": drink, "food_edible": food, "prepared_meals": 31, "plants_brewable": pb, "plants_total": pb,
              "plants_rotten": rot, "barrels_empty": barrels, "logs_usable": 43, "seeds": seeds,
              "seeds_by_kind": PLUMP, "plants_by_kind": {"plump helmet": {"n": pb, "brewable": True, "cookable": True}},
              "furniture_free": {}}
    obs = {"date": {"abs_tick": day * harness.DAY, "day_of_year": (day + 15) % harness.YEAR_DAYS},
           "administrators": {"citizens": cit}, "stocks": stocks, "map": {"sites": []}, "zones": [],
           "furniture": [], "workshops": [{"type": w, "built": True} for w in workshops], "orders": list(orders),
           "farm_plots": [{"id": i, "z": 161, "seeds_or_crops_in_plot": n} for i, n in enumerate(plots)],
           "wealth": {"created": wealth}}
    r = {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": days - day}
    if hands_off is not None:
        r["hands_off_in_days"] = hands_off
    return r


def brew(oid, repeat=True, below=None, left=4):
    when = [] if below is None else [{"item_type": "DRINK", "test": "LessThan", "value": below, "stock": "drink"}]
    x = {"id": oid, "recipe": "brew_drink", "job": "CustomReaction", "left": left, "when": when}
    if repeat:
        x["repeat"] = "daily"
    return x


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, day=279, days=336, **kw):
        game = FakeGame()
        ov = harness.Overseer(game, days=days)
        ov.load(resp(day, days=days, **kw))
        ov.count = 0
        return ov, game

    @staticmethod
    def adds(game, recipe):
        return [a for t, a in game.calls if t == "add_order" and a.get("recipe") == recipe]

    @staticmethod
    def cancels(game):
        return [a["order_id"] for t, a in game.calls if t == "cancel_order"]


class FoodLean(Base):
    # the measured day 279: drink 380 / food 73 for 20 citizens — leg days 57.6 / 22.8
    def test_measured_endgame_arms_and_the_still_yields(self):
        ov, _ = self.ov()
        self.assertTrue(ov.food_lean())
        self.assertEqual(ov.lean_drink, 380)
        self.assertEqual(ov.allocation(), frozenset({"cook"}))
        self.assertEqual(ov.brew_when(), [{"stock": "drink", "below": 380}, {"stock": "plants_brewable", "at_least": 1},
                                          {"stock": "barrels_empty", "at_least": 1}])
        self.assertEqual(ov.brew_amount(), harness.LEAN_BREW_AMOUNT)

    def test_arming_waits_for_the_window_the_ratio_and_full_year_open_play(self):
        self.assertFalse(self.ov(day=336 - harness.LEAN_DAYS - 1)[0].food_lean())   # before the window
        self.assertFalse(self.ov(drink=200, food=100)[0].food_lean())               # 30 vs 31 days: no lead
        self.assertFalse(self.ov(days=216, day=216 - harness.LEAN_DAYS - 1)[0].food_lean())   # MY1: its window too
        self.assertFalse(self.ov(hands_off=10)[0].food_lean())                        # a lab task's window
        ov, _ = self.ov(day=280)
        ov.caravan_active = True
        self.assertFalse(ov.food_lean())                                              # the merchants' goods

    def test_the_level_stays_and_the_lean_lets_go_once_food_catches_up(self):
        ov, _ = self.ov()
        self.assertTrue(ov.food_lean())
        ov.load(resp(286, drink=390, food=90))
        self.assertTrue(ov.food_lean())
        self.assertEqual(ov.lean_drink, 380)           # armed once: the level is the arming day's drink
        ov.load(resp(293, drink=380, food=170))        # 57.6 vs 53.1 days: under LEAN_EXIT
        self.assertFalse(ov.food_lean())
        self.assertIsNone(ov.lean_drink)
        ov.load(resp(300, drink=410, food=70))         # a later arming takes that day's drink
        self.assertTrue(ov.food_lean())
        self.assertEqual(ov.lean_drink, 410)

    def test_no_brew_one_shots_from_the_allocation_the_rot_guard_or_the_glut_bank(self):
        ov, game = self.ov(pb=14, seeds=40)
        ov.rot_seen = True
        ov.allocate_plants()
        ov.rot_guard()
        ov.glut_bank()
        self.assertEqual(self.adds(game, "brew_drink"), [])

    def test_without_the_lean_the_last_stretch_still_brews(self):
        ov, game = self.ov(drink=200, food=100, pb=14)   # no lead: the old last-stretch shape
        self.assertFalse(ov.food_lean())
        ov.allocate_plants()
        self.assertTrue(self.adds(game, "brew_drink"))

    def test_other_brew_orders_yield_and_the_keepers_stay(self):
        orders = [brew(15, below=600), brew(30, below=462), brew(40, below=300), brew(54, repeat=False, left=2),
                  brew(55, repeat=False, left=0), brew(60)]
        ov, game = self.ov(orders=orders)
        ov.key_order["o_brew"] = 60                     # this layer's o_brew is the keeper itself
        ov.lean_supply()
        self.assertEqual(sorted(self.cancels(game)), [15, 30, 54])

    def test_the_closer_retires_its_own_brew_standing(self):
        ov, game = self.ov(orders=[brew(15, below=600)])
        ov.key_order["o_brew_end"] = 15
        ov.owned.add(15)
        ov.lean_supply()
        self.assertEqual(self.cancels(game), [])        # lean_supply leaves it to the closer
        ov.endgame_supply()
        self.assertEqual(self.cancels(game), [15])
        self.assertEqual(self.adds(game, "brew_drink"), [])

    def test_o_brew_is_recut_into_the_keeper(self):
        old = brew(0, below=400)
        old["when"] += [{"item_type": "PLANT", "test": "AtLeast", "value": 2, "reaction_product": "DRINK_MAT",
                         "stock": "plants_brewable"},
                        {"item_type": "BARREL", "test": "AtLeast", "value": 1, "stock": "barrels_empty"}]
        ov, game = self.ov(orders=[old])
        ov.key_order["o_brew"] = 0
        self.assertTrue(ov.sync_brew())                 # the floor 2 -> 1 re-cuts it
        self.assertEqual(self.cancels(game), [0])
        ov2, game2 = self.ov()                          # nothing on the book: supply adds the keeper
        ov2.supply()
        self.assertEqual(self.adds(game2, "brew_drink")[0]["when"][0], {"stock": "drink", "below": 380})
        self.assertEqual(self.adds(game2, "brew_drink")[0]["amount"], harness.LEAN_BREW_AMOUNT)

    def test_the_hold_does_not_brew_into_f_while_lean(self):
        ov, game = self.ov(day=320)
        ov.hold_armed = True
        ov.hold_supply()
        keys = [k for k, v in ov.key_order.items()]
        self.assertNotIn("o_brew_f", keys)
        self.assertNotIn("o_brew_pre", keys)


class CraftFallback(Base):
    WOOD = {"id": 10, "job": "MakeCrafts", "repeat": "daily", "left": 3, "total": 12, "material_category": ["wood"]}

    def bone_adds(self, game):
        return [a for t, a in game.calls if t == "add_manager_order" and a.get("material_category") == ["bone"]]

    # the measured stall: 17,244 on day 279, 17,291 on day 293 with the wood standing at left 3, 0 jobs
    def test_a_wood_stall_opens_one_bone_standing(self):
        ov, game = self.ov(orders=[self.WOOD], wealth=17244)
        ov.craft_fallback()
        self.assertEqual(self.bone_adds(game), [])      # one sample: no span yet
        ov.load(resp(286, orders=[self.WOOD], wealth=17290))
        ov.craft_fallback()
        self.assertEqual(len(self.bone_adds(game)), 1)
        self.assertEqual(self.bone_adds(game)[0]["repeat"], "daily")
        bone = {"id": 99, "job": "MakeCrafts", "repeat": "daily", "left": 4, "material_category": ["bone"]}
        ov.load(resp(293, orders=[self.WOOD, bone], wealth=17291))
        ov.craft_fallback()
        self.assertEqual(len(self.bone_adds(game)), 1)

    def test_rising_wealth_or_no_wood_standing_keeps_it_closed(self):
        ov, game = self.ov(orders=[self.WOOD], wealth=15000)
        ov.load(resp(286, orders=[self.WOOD], wealth=15400))
        ov.craft_fallback()
        self.assertEqual(self.bone_adds(game), [])
        ov2, game2 = self.ov(orders=[], wealth=17244)
        ov2.load(resp(286, orders=[], wealth=17250))
        ov2.craft_fallback()
        self.assertEqual(self.bone_adds(game2), [])

    def test_the_bone_standing_is_not_the_wood_one(self):
        bone = {"id": 99, "job": "MakeCrafts", "repeat": "daily", "left": 4, "total": 4, "material_category": ["bone"]}
        ov, game = self.ov(day=100, cit=14, orders=[bone], wealth=6000)
        ov.st["logs_usable"] = 500                      # the logs guard is clear
        ov.progress()
        woods = [a for t, a in game.calls if t == "add_manager_order" and a.get("material_category") == ["wood"]]
        self.assertEqual(len(woods), 1)                 # the wood standing is still added beside it
        self.assertNotIn(99, self.cancels(game))


class MY1Lean(Base):
    """cx hint std MY1-4 on 68bd4c7 (O 61.0, supply 0.734 on the food leg): drink 567 -> 711 in F while food fell
    189 -> 168 — the last stretch's allocation (both sides), the glut bank and o_brew_end (drink below 600) brewed every
    week of F. The record's own looks: day 157 drink 399 / food 119 / 19 citizens (leg days 63.6 / 39.1), day 188
    drink 567 / food 189 / 18 (95.5 / 65.6), pb 24."""

    def test_the_record_arms_on_day_157_with_the_drink_of_that_day(self):
        ov, _ = self.ov(day=157, days=216, cit=19, drink=399, food=119, pb=50, seeds=9)
        self.assertTrue(ov.food_lean())
        self.assertEqual(ov.lean_drink, 399)
        self.assertEqual(ov.allocation(), frozenset({"cook"}))

    def test_f_brews_nothing_but_the_keeper(self):
        ov, game = self.ov(day=157, days=216, cit=19, drink=399, food=119, pb=50, seeds=9)
        self.assertTrue(ov.food_lean())
        ov.load(resp(188, days=216, cit=18, drink=567, food=189, pb=24, seeds=39, barrels=26))
        game.calls.clear()
        ov.count = 0
        self.assertTrue(ov.food_lean())
        ov.allocate_plants()
        ov.glut_bank()
        ov.closer()
        self.assertEqual(self.adds(game, "brew_drink"), [])
        self.assertEqual(ov.brew_when()[0], {"stock": "drink", "below": 399})

    def test_a_drink_short_my1_fort_never_arms(self):
        # hint MY1-3 shape (the harvest-closed hold forts): drink 100 / food 145 for 12 citizens
        self.assertFalse(self.ov(day=190, days=216, cit=12, drink=100, food=145)[0].food_lean())
        # the 100-point std MY1-4 (full2): drink 495 / food 266 for 17 citizens — 88 vs 98 days, no lead
        self.assertFalse(self.ov(day=188, days=216, cit=17, drink=495, food=266)[0].food_lean())


if __name__ == "__main__":
    unittest.main()
