"""Regressions for the cook standings' plants_brewable reserve (COOK_PLANTS_RESERVE): cooking returns no seeds, so
both cook standings (the regular o_cook and the closer's o_cook_end) hold the brewable plants above the reserve the
way o_brew's own when already does. Amounts, caps and the other conditions stay untouched. No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {}}


def facts(cit=8, stocks=None, orders=()):
    return {"tick": 45 * harness.DAY, "day": 45, "observation": {
        "administrators": {"citizens": cit},
        "stocks": {"furniture_free": {}, **(stocks or {})},
        "map": {"sites": []}, "zones": [], "furniture": [],
        "workshops": [{"type": "Carpenters"}, {"type": "Still"}, {"type": "Kitchen"}],
        "orders": list(orders)}}


def cook_orders(calls, key="o_cook"):
    return [a for t, a in calls if t == "add_order" and a.get("recipe") == "cook_meal"]


class CookReserve(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, **kw):
        game = FakeGame()
        ov = harness.Overseer(game, days=336)
        ov.load(facts(**kw))
        ov.count = 0
        return ov, game

    # (a) the regular cook standing carries the brewable floor alongside the untouched stock conditions
    def test_o_cook_when_carries_the_brewable_reserve(self):
        ov, game = self.overseer()
        ov.supply()
        added = cook_orders(game.calls)
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["amount"], 2)              # amount/cap untouched
        self.assertEqual(added[0]["when"], [
            {"stock": "prepared_meals", "below": harness.MEAL_CAP},
            {"stock": "plants_total", "at_least": 10},
            {"stock": "plants_brewable", "at_least": harness.COOK_PLANTS_RESERVE}])

    # (b) the toggle: COOK_PLANTS_RESERVE = 0 restores the bare cook when
    def test_o_cook_without_the_reserve_when_toggled_off(self):
        ov, game = self.overseer()
        with patch.object(harness, "COOK_PLANTS_RESERVE", 0):
            ov.supply()
        added = cook_orders(game.calls)
        self.assertEqual(added[0]["when"], [
            {"stock": "prepared_meals", "below": harness.MEAL_CAP},
            {"stock": "plants_total", "at_least": 10}])

    # (c) the closer's cook standing carries the same floor
    def test_o_cook_end_when_carries_the_brewable_reserve(self):
        ov, game = self.overseer(stocks={"food_edible": 100})   # above the meat threshold: no butcher call
        ov.endgame_supply()
        added = cook_orders(game.calls)
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["amount"], 2)
        self.assertEqual(added[0]["when"], [
            {"stock": "prepared_meals", "below": max(300, 10 * ov.cit)},
            {"stock": "food_edible", "at_least": max(30, ov.cit)},
            {"stock": "plants_brewable", "at_least": harness.COOK_PLANTS_RESERVE}])

    def test_o_cook_end_without_the_reserve_when_toggled_off(self):
        ov, game = self.overseer(stocks={"food_edible": 100})
        with patch.object(harness, "COOK_PLANTS_RESERVE", 0):
            ov.endgame_supply()
        added = cook_orders(game.calls)
        self.assertEqual(added[0]["when"], [
            {"stock": "prepared_meals", "below": max(300, 10 * ov.cit)},
            {"stock": "food_edible", "at_least": max(30, ov.cit)}])

    # (d) regressions: an existing cook standing still suppresses o_cook, and the other standings keep their when
    def test_existing_cook_standing_still_suppresses_o_cook(self):
        ov, game = self.overseer(orders=[{"id": 5, "recipe": "cook_meal", "repeat": "daily", "left": 0,
                                          "when": [{"stock": "prepared_meals", "below": harness.MEAL_CAP}]}])
        ov.supply()
        self.assertEqual(cook_orders(game.calls), [])
        self.assertEqual(len([a for t, a in game.calls if a.get("recipe") == "brew_drink"]), 1)

    def test_brew_and_barrel_standings_are_untouched_by_the_change(self):
        ov, game = self.overseer()
        ov.supply()
        brew = next(a for t, a in game.calls if a.get("recipe") == "brew_drink")
        barrel = next(a for t, a in game.calls if a.get("recipe") == "make_barrel")
        self.assertEqual(brew["when"], [{"stock": "drink", "below": harness.DRINK_CAP},
                                        {"stock": "plants_brewable", "at_least": 2},
                                        {"stock": "barrels_empty", "at_least": 1}])
        self.assertEqual(barrel["when"], [{"stock": "barrels_empty", "below": 4},
                                          {"stock": "logs", "at_least": 2}])

    def test_endgame_brew_barrel_keep_their_when_and_the_window_supply_has_no_cook(self):
        ov, game = self.overseer(stocks={"food_edible": 100})
        ov.window_supply()
        self.assertEqual(cook_orders(game.calls), [])   # the window's food>0 predicate stays as it is
        game.calls.clear()
        ov.endgame_supply()
        brew = next(a for t, a in game.calls if a.get("recipe") == "brew_drink")
        barrel = next(a for t, a in game.calls if a.get("recipe") == "make_barrel")
        self.assertEqual(brew["when"], [{"stock": "drink", "below": max(600, 30 * ov.cit)},
                                        {"stock": "plants_brewable", "at_least": max(12, ov.cit)},
                                        {"stock": "barrels_empty", "at_least": 1}])
        self.assertEqual(barrel["when"], [{"stock": "barrels_empty", "below": 8},
                                          {"stock": "logs", "at_least": 4}])


if __name__ == "__main__":
    unittest.main()
