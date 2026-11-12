"""Regressions for the cook standings' plants_brewable reserve (COOK_PLANTS_RESERVE): cooking returns no seeds, so
both cook standings (the regular o_cook and the closer's o_cook_end) hold the brewable plants above the reserve the
way o_brew's own when already does. Amounts, caps and the other conditions stay untouched. On this FULL tree the
reserve arms at days >= COOK_RESERVE_DAYS (180, the MY1 guard: both measured MY1-5 collapses died with seeds 2-4
while the brewable plants got eaten or cooked instead of brewed); the short lab runs (days < 180) keep the leader's
bare cook when, and the endgame food gate itself stays full-year shaped (4 per citizen below 336). No game or
network."""
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
        days = kw.pop("days", 336)
        game = FakeGame()
        ov = harness.Overseer(game, days=days)
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
        ov, game = self.overseer(stocks={"food_edible": 100, "drink": 300})   # above the meat threshold: no butcher call
        ov.endgame_supply()
        added = cook_orders(game.calls)
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0]["amount"], 2)
        self.assertEqual(added[0]["when"], [
            {"stock": "prepared_meals", "below": max(300, 10 * ov.cit)},
            {"stock": "food_edible", "at_least": max(30, ov.cit)},
            {"stock": "plants_brewable", "at_least": harness.COOK_PLANTS_RESERVE}])

    def test_o_cook_end_without_the_reserve_when_toggled_off(self):
        ov, game = self.overseer(stocks={"food_edible": 100, "drink": 300})
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
        # the adaptive-cap fix re-sized this cap to max(200, a year of drink per citizen); at cit=8 the 200
        # floor wins, and the barrel standing keeps its own when
        self.assertEqual(brew["when"], [{"stock": "drink", "below": max(200, harness.DRINK_PER_CIT_YEAR * ov.cit)},
                                        {"stock": "plants_brewable", "at_least": 2},
                                        {"stock": "barrels_empty", "at_least": 1}])
        self.assertEqual(barrel["when"], [{"stock": "barrels_empty", "below": 4},
                                          {"stock": "logs", "at_least": 2}])

    def test_endgame_brew_barrel_keep_their_when_and_the_window_supply_has_no_cook(self):
        ov, game = self.overseer(stocks={"food_edible": 100, "drink": 300})
        ov.window_supply()
        self.assertEqual(cook_orders(game.calls), [])   # the window's food>0 predicate stays as it is
        game.calls.clear()
        ov.endgame_supply()
        brew = next(a for t, a in game.calls if a.get("recipe") == "brew_drink")
        barrel = next(a for t, a in game.calls if a.get("recipe") == "make_barrel")
        self.assertEqual(brew["when"], [{"stock": "drink", "below": max(600, 30 * ov.cit)},
                                        {"stock": "plants_brewable", "at_least": harness.BREW_END_FLOOR},
                                        {"stock": "barrels_empty", "at_least": 1}])
        self.assertEqual(barrel["when"], [{"stock": "barrels_empty", "below": 8},
                                          {"stock": "logs", "at_least": 4}])

    # (e) the days gate: a short lab run (days < 336) keeps the leader's bare cook when, the leader's 4-per-citizen
    # endgame food gate, and the leader's farm target — the OP1 guards do not move the labs
    def test_lab_run_keeps_the_bare_cook_when_and_the_leader_farm_target(self):
        ov, game = self.overseer(days=60)
        self.assertEqual(ov.farm_target(), max(4, min(10, -(-ov.cit // 5))))   # the leader's ceil(cit/5) branch
        ov.supply()
        added = cook_orders(game.calls)
        self.assertEqual(added[0]["when"], [
            {"stock": "prepared_meals", "below": harness.MEAL_CAP},
            {"stock": "plants_total", "at_least": 10}])   # no reserve clause below 336 days

    def test_farm_target_branch_is_full_year_proportional(self):
        ov, _ = self.overseer(days=336, cit=45)
        self.assertEqual(ov.farm_target(), max(6, min(12, -(-45 // 3))))   # ceil(cit/3), capped at 12
        ov2, _ = self.overseer(days=336, cit=9)
        self.assertEqual(ov2.farm_target(), 6)                             # and floored at 6
        ov3, _ = self.overseer(days=216, cit=45)                           # MY1: the leader's branch
        # cx population forecast (2026-11-10): the census the expected wave brings — a 45-citizen fort at its first
        # load is past the embark party, so one wave of WAVE_MEAN is still to come: ceil((45 + 5.5) / 5) = 11 -> 10
        self.assertEqual(ov3.farm_target(), max(4, min(10, -(-51 // 5))))

    def test_endgame_food_gate_stays_leader_shaped_below_336_days(self):
        ov, game = self.overseer(days=216, stocks={"food_edible": 100, "drink": 300})
        ov.endgame_supply()
        added = cook_orders(game.calls)
        self.assertEqual(added[0]["when"], [
            {"stock": "prepared_meals", "below": max(300, 10 * ov.cit)},
            {"stock": "food_edible", "at_least": max(30, 4 * ov.cit)},   # the leader's 4-per-citizen gate
            {"stock": "plants_brewable", "at_least": harness.COOK_PLANTS_RESERVE}])   # the MY1 guard: reserve at 216

    def test_endgame_cook_stays_bare_below_the_reserve_days(self):
        ov, game = self.overseer(days=60, stocks={"food_edible": 100})
        ov.endgame_supply()
        added = cook_orders(game.calls)
        self.assertEqual(added[0]["when"], [
            {"stock": "prepared_meals", "below": max(300, 10 * ov.cit)},
            {"stock": "food_edible", "at_least": max(30, 4 * ov.cit)}])   # a lab run keeps the bare when


if __name__ == "__main__":
    unittest.main()
