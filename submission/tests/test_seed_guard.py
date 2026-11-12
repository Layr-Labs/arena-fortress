"""cx: a lab fort short of drink keeps its seeds out of the kitchen and reads the seed / fruit stock through the query.

Measured shapes: hint hard LT02-0 on f2bd283 (14 seeds, plants 0, no plot on day 0; the model's [prepared_meals < 34]
cook ran on days 14-16 while 9 seeds went, none planted; autofarm fallowed every plot from day 16) and hint hard
LT01-0 on 82d1ec1 (25 seeds, plants 0, every plot 'none' from day 1). No game or network is used."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class FakeGame:
    def __init__(self, stocks=None):
        self.calls, self.queries = [], []
        self.stocks = stocks or {}

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {"order_id": 900 + len(self.calls)}}

    def query(self, name, **params):
        self.queries.append((name, params))
        return {"ok": True, "result": {"ok": True, "groups": self.stocks.get(params.get("item_type"), [])}}


MODEL_COOK = {"id": 6, "job": "PrepareMeal", "recipe": "cook_meal", "repeat": "daily", "left": 3, "active": True,
              "when": [{"item_type": "FOOD", "test": "LessThan", "value": 34, "flags": [], "stock": "prepared_meals"}]}
FLOORED_COOK = {"id": 7, "job": "PrepareMeal", "recipe": "cook_meal", "repeat": "daily", "left": 2,
                "when": [{"item_type": "FOOD", "test": "LessThan", "value": 200, "flags": []},
                         {"item_type": "SEEDS", "test": "AtLeast", "value": 40, "flags": []}]}


def fort(day=11, seeds=14, drink=0, pb=0, orders=(), plots=(), hands_off=58, cit=17):
    return {"day": day, "tick": day * harness.DAY, "hands_off_in_days": hands_off, "days_left": 90 - day,
            "observation": {
                "administrators": {"citizens": cit}, "map": {"sites": [], "surface_z": 137},
                "orders": [dict(o) for o in orders], "farm_plots": [dict(p) for p in plots],
                "stocks": {"seeds": seeds, "drink": drink, "plants_brewable": pb, "plants_total": pb,
                           "food_edible": 30, "furniture_free": {}}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, game=None, days=90):
        ov = harness.Overseer(game or FakeGame(), days=days)
        ov.count = 0
        return ov

    def cancels(self, game):
        return [a["order_id"] for t, a in game.calls if t == "cancel_order"]


class SeedFloor(Base):
    def test_lab_drink_short_banks_seeds_for_the_target_plots(self):
        ov = self.overseer()
        ov.load(fort())
        self.assertEqual(ov.seed_floor(), ov.farm_target() * harness.SEEDS_PER_PLOT)

    def test_lab_with_drink_keeps_the_built_plots_floor(self):
        ov = self.overseer()
        ov.load(fort(drink=200, plots=[{"id": 1}]))
        self.assertEqual(ov.seed_floor(), 1 * harness.SEEDS_PER_PLOT)

    def test_open_play_is_unchanged(self):
        ov = self.overseer(days=336)
        ov.load(fort(hands_off=None, plots=[{"id": 1}]))
        ov.days_to_end = lambda: 200
        ov.harvest_closed = lambda: False
        self.assertEqual(ov.seed_floor(), 1 * harness.SEEDS_PER_PLOT)


class SeedGuard(Base):
    def test_model_cook_without_a_seeds_floor_is_cancelled(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(fort(orders=[MODEL_COOK]))
        ov.seed_guard()
        self.assertEqual(self.cancels(game), [6])

    def test_own_cook_is_left(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.owned.add(6)
        ov.load(fort(orders=[MODEL_COOK]))
        ov.seed_guard()
        self.assertEqual(self.cancels(game), [])

    def test_a_seeds_floor_above_the_stock_is_left(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(fort(orders=[FLOORED_COOK]))
        ov.seed_guard()
        self.assertEqual(self.cancels(game), [])

    def test_seeds_over_the_bank_leave_the_kitchen_alone(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(fort(seeds=200, orders=[MODEL_COOK]))
        ov.seed_guard()
        self.assertEqual(self.cancels(game), [])

    def test_open_play_never_cancels(self):
        game = FakeGame()
        ov = self.overseer(game, days=336)
        ov.load(fort(hands_off=None, orders=[MODEL_COOK], plots=[{"id": 1}]))
        ov.seed_guard()
        self.assertEqual(self.cancels(game), [])

    def test_drink_in_stock_drops_the_guard(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(fort(drink=200, orders=[MODEL_COOK]))
        ov.seed_guard()
        self.assertEqual(self.cancels(game), [])


class EmergencyCook(Base):
    def test_lab_emergency_cook_carries_the_seeds_clause(self):
        game = FakeGame()
        ov = self.overseer(game)
        obs = fort(orders=[])
        obs["observation"]["workshops"] = [{"type": "Kitchen", "built": True}]
        ov.load(obs)
        ov.food_cover = lambda: 20
        ov.leg_days = lambda: (5, 40)
        ov.food_security()
        adds = [(t, a) for t, a in game.calls if t in ("add_order", "add_manager_order")]
        self.assertEqual(len(adds), 1)
        tool, args = adds[0]
        self.assertEqual(tool, "add_manager_order")
        seeds = [c for c in args["when"] if c.get("item_type") == "SEEDS"]
        self.assertEqual(seeds, [{"item_type": "SEEDS", "at_least": ov.seed_floor()}])


class SeedCensus(Base):
    def test_census_reads_seeds_and_growths_and_sees_free_fruit(self):
        game = FakeGame({"SEEDS": [{"material": "PLANT:MUSHROOM_HELMET_PLUMP:SEED", "items": 3, "count": 5,
                                    "rotten": 3, "forbidden": 0, "in_job": 0, "in_building": 0, "in_inventory": 0}],
                         "PLANT_GROWTH": [{"material": "PLANT:BERRIES_STRAW:FRUIT", "items": 2, "count": 4,
                                           "rotten": 0, "forbidden": 0, "in_building": 0}]})
        ov = self.overseer(game)
        ov.load(fort())
        ov.seed_census()
        self.assertEqual([p.get("item_type") for _, p in game.queries], ["SEEDS", "PLANT_GROWTH"])
        self.assertEqual(ov.census["SEEDS"]["free_items"], 0)
        self.assertEqual(ov.census["SEEDS"]["rotten"], 3)
        self.assertTrue(ov.fruit_seen)
        ov.seed_census()   # once per SEED_CENSUS_DAYS
        self.assertEqual(len(game.queries), 2)

    def test_free_fruit_lets_the_fruit_brew_in_with_no_plant(self):
        game = FakeGame({"PLANT_GROWTH": [{"material": "PLANT:BERRIES_STRAW:FRUIT", "items": 2, "count": 4}]})
        ov = self.overseer(game)
        ov.load(fort())
        ov.seed_census()
        ov.supply()
        self.assertIn(("add_order", {"recipe": "brew_drink_from_fruit", "amount": 3}), game.calls)

    def test_no_fruit_no_fruit_order(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(fort())
        ov.seed_census()
        ov.supply()
        self.assertNotIn("brew_drink_from_fruit", [a.get("recipe") for _, a in game.calls])

    def test_open_play_and_brewable_plants_skip_the_census(self):
        game = FakeGame()
        ov = self.overseer(game, days=336)
        ov.load(fort(hands_off=None))
        ov.seed_census()
        ov2 = self.overseer(game)
        ov2.load(fort(pb=4))
        ov2.seed_census()
        self.assertEqual(game.queries, [])

    def test_a_game_without_query_is_skipped(self):
        class NoQuery:
            def act(self, tool, args):
                return {"ok": True}
        ov = self.overseer(NoQuery())
        ov.load(fort())
        ov.seed_census()
        self.assertEqual(ov.census, {})


if __name__ == "__main__":
    unittest.main()
