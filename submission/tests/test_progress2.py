"""Regressions for the staged progression push (progress): stage 1 stays as it was, stage 2 carries the wealth push
on to the Village rank. No game or network is used."""
import copy
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
    def __init__(self, fail_tools=()):
        self.calls = []
        self.fail_tools = set(fail_tools)
        self.ids = 100

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if tool in self.fail_tools:
            return {"ok": False, "error_code": "game_refused", "error": "refused for the test"}
        self.ids += 1
        return {"ok": True, "result": {"order_id": self.ids, "id": self.ids}}

    def query(self, name, **kw):
        return {"ok": True, "result": {}}


def facts(created=0, cit=12, day=60, workshops=("Craftsdwarfs",), stocks=None, orders=(), sites=()):
    return {"tick": day * harness.DAY, "day": day, "observation": {
        "administrators": {"citizens": cit},
        "wealth": {"created": created},
        "stocks": {"furniture_free": {}, **(stocks or {})},
        "map": {"sites": list(sites)},
        "zones": [], "furniture": [],
        "workshops": [{"type": t} for t in workshops],
        "orders": copy.deepcopy(list(orders))}}


def crafts_standing(oid=7, reserve=None):
    o = {"id": oid, "job": "MakeCrafts", "repeat": "daily", "left": 0, "total": 3}
    if reserve is not None:
        o["when"] = [{"item_type": "WOOD", "at_least": reserve}]
    return o


class Progress2(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, fail_tools=(), **kw):
        game = FakeGame(fail_tools=fail_tools)
        overseer = harness.Overseer(game, days=336)
        overseer.load(facts(**kw))
        overseer.count = 0
        return overseer, game

    def manager_orders(self, game):
        return [a for t, a in game.calls if t == "add_manager_order"]

    def added_orders(self, game):
        return [a for t, a in game.calls if t == "add_order"]

    # (d) regression: below the Hamlet target the step behaves exactly as the batch-1 one
    def test_below_hamlet_keeps_the_batch1_step(self):
        overseer, game = self.overseer(created=3000)
        overseer.progress()
        self.assertEqual(self.manager_orders(game), [
            {"job": "MakeCrafts", "amount": 3, "repeat": "daily", "material_category": ["wood"],
             "when": [{"item_type": "WOOD", "at_least": harness.LOG_RESERVE}]}])
        self.assertEqual(self.added_orders(game), [])          # no cook push in stage 1
        self.assertFalse([c for c in game.calls if c[0] == "cancel_order"])

    def test_stage1_standing_means_no_new_order(self):
        overseer, game = self.overseer(created=3000, orders=[crafts_standing(reserve=25)])
        overseer.progress()
        self.assertEqual(game.calls, [])

    # (a) the 5500..25000 band runs stage 2: wider log reserve + (with the toggle on) the meal push
    def test_stage2_raises_the_crafts_reserve_and_adds_the_meal_push(self):
        overseer, game = self.overseer(created=6000)
        with patch.object(harness, "MEALS_FOR_WEALTH", False):
            overseer.progress()
        self.assertEqual(self.manager_orders(game), [
            {"job": "MakeCrafts", "amount": 3, "repeat": "daily", "material_category": ["wood"],
             "when": [{"item_type": "WOOD", "at_least": harness.LOG_RESERVE2}]}])
        self.assertEqual(self.added_orders(game), [])   # the meal push is off by default (it sags the drink stock)

    def test_stage2_meal_push_when_enabled(self):
        overseer, game = self.overseer(created=6000)
        with patch.object(harness, "MEALS_FOR_WEALTH", True):
            overseer.progress()
        cooks = self.added_orders(game)
        self.assertEqual(len(cooks), 1)
        self.assertEqual(cooks[0]["recipe"], "cook_meal")
        self.assertEqual(cooks[0]["repeat"], "daily")
        whens = cooks[0]["when"]
        self.assertIn({"stock": "prepared_meals", "below": harness.MEAL_CAP_STAGE2}, whens)
        plants = [w for w in whens if w.get("stock") == "plants_total"]
        food = [w for w in whens if w.get("stock") == "food_edible"]
        self.assertTrue(plants and plants[0]["at_least"] >= 12)          # plants kept for brew + future food
        self.assertTrue(food and food[0]["at_least"] >= 4 * overseer.cit)  # the endgame reserve's style

    def test_stage2_retires_only_the_layer_owned_low_crafts_standing(self):
        overseer, game = self.overseer(created=6000, orders=[crafts_standing(oid=7, reserve=25),
                                                             crafts_standing(oid=8, reserve=25)])
        overseer.owned = {7}                    # order 8 belongs to the model: never touched
        overseer.progress()
        self.assertEqual(self.manager_orders(game), [
            {"job": "MakeCrafts", "amount": 3, "repeat": "daily", "material_category": ["wood"],
             "when": [{"item_type": "WOOD", "at_least": harness.LOG_RESERVE2}]}])
        cancels = [a for t, a in game.calls if t == "cancel_order"]
        self.assertEqual(cancels, [{"order_id": 7}])

    def test_stage2_swap_keeps_the_old_standing_until_the_replacement_is_accepted(self):
        overseer, game = self.overseer(created=6000, orders=[crafts_standing(oid=7, reserve=25)],
                                       fail_tools=("add_manager_order",))
        overseer.owned = {7}
        overseer.progress()
        self.assertFalse([c for c in game.calls if c[0] == "cancel_order"])   # no gap in the crafts supply

    def test_stage2_does_not_duplicate_standings_on_the_next_pass(self):
        overseer, game = self.overseer(created=6000)
        overseer.progress()
        overseer.load(facts(created=6000, orders=[
            crafts_standing(oid=101, reserve=harness.LOG_RESERVE2),
            {"id": 102, "recipe": "cook_meal", "repeat": "daily", "left": 0,
             "when": [{"stock": "prepared_meals", "below": harness.MEAL_CAP_STAGE2}]}]))
        overseer.owned = {101, 102}
        game.calls.clear()
        overseer.progress()
        self.assertEqual(game.calls, [])        # both standings are recognized from the observation's when

    def test_stage2_recognizes_its_own_add_even_without_readout_conditions(self):
        overseer, game = self.overseer(created=6000)
        overseer.progress()                     # first pass adds; the observation carries no when copy
        overseer.load(facts(created=6000, orders=[crafts_standing(oid=101)]))   # no when field
        overseer.owned = {101}
        game.calls.clear()
        overseer.progress()
        self.assertEqual(game.calls, [])        # prog_reserve remembers the accepted reserve

    # (c) the crafts gate: DF only runs the standing above LOG_RESERVE2, and the observation shows that condition
    def test_stage2_crafts_order_carries_the_log_gate(self):
        overseer, game = self.overseer(created=6000, stocks={"logs_usable": 10})
        overseer.progress()
        order = self.manager_orders(game)[0]
        self.assertEqual(order["when"], [{"item_type": "WOOD", "at_least": harness.LOG_RESERVE2}])
        self.assertGreater(harness.LOG_RESERVE2, 10)   # the gate holds the order back at this stock

    # (b) at the Village wealth the whole push stops
    def test_wealth_push_stops_at_the_village_target(self):
        overseer, game = self.overseer(created=harness.WEALTH_TARGET2)
        overseer.progress()
        self.assertEqual(game.calls, [])
        overseer, game = self.overseer(created=harness.WEALTH_TARGET2 + 500)
        overseer.progress()
        self.assertEqual(game.calls, [])

    # the meal push is a toggle: the unmeasured meals-in-created-wealth assumption can be switched off
    def test_meal_push_is_togglable(self):
        overseer, game = self.overseer(created=6000)
        with patch.object(harness, "MEALS_FOR_WEALTH", False):
            overseer.progress()
        self.assertEqual(self.manager_orders(game), [
            {"job": "MakeCrafts", "amount": 3, "repeat": "daily", "material_category": ["wood"],
             "when": [{"item_type": "WOOD", "at_least": harness.LOG_RESERVE2}]}])
        self.assertEqual(self.added_orders(game), [])

    def test_existing_big_cap_cook_standing_blocks_a_second_push(self):
        overseer, game = self.overseer(created=6000, orders=[
            {"id": 9, "recipe": "cook_meal", "repeat": "daily", "left": 0,
             "when": [{"stock": "prepared_meals", "below": harness.MEAL_CAP_STAGE2}]}])
        overseer.progress()
        self.assertEqual(self.added_orders(game), [])
        self.assertEqual(len(self.manager_orders(game)), 1)   # the crafts half still runs

    def test_craftsdwarfs_is_built_before_any_push(self):
        overseer, game = self.overseer(created=6000, workshops=(), stocks={"logs_usable": 3},
                                       sites=[{"id": "W1", "kind": "W"}])
        overseer.progress()
        self.assertEqual(game.calls, [("build_workshop", {"type": "Craftsdwarfs", "site": "W1"})])

    def test_absorb_days_fills_the_task_length_for_the_standalone_entry_point(self):
        overseer = harness.Overseer(FakeGame(), days=0)
        overseer.absorb_days({"task": {"days": 336}})
        self.assertEqual(overseer.days, 336)
        overseer = harness.Overseer(FakeGame(), days=216)
        overseer.absorb_days({"task": {"days": 336}})
        self.assertEqual(overseer.days, 216)    # an explicit constructor value wins
        overseer = harness.Overseer(FakeGame(), days=0)
        overseer.absorb_days({})
        self.assertEqual(overseer.days, 0)


class DigestGrowthNote(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def digest(self, cit):
        from plain import digest as digest_mod
        obs = {"administrators": {"citizens": cit}, "dwarves": [], "stocks": {},
               "map": {"sites": []}, "zones": [], "workshops": [], "orders": []}
        return digest_mod.digest(obs, {"day": 100, "tick": 100 * harness.DAY}, units=None)

    def test_next_names_the_missing_citizens_between_46_and_49(self):
        for cit in (46, 48, 49):
            with self.subTest(cit=cit):
                text = self.digest(cit)
                self.assertIn(f"{harness_soon(cit)} more citizens to Village", text)

    def test_no_growth_line_at_45_or_50(self):
        for cit in (7, 45, 50, 60):
            with self.subTest(cit=cit):
                self.assertNotIn("more citizens to Village", self.digest(cit))


def harness_soon(cit):
    return 50 - cit


if __name__ == "__main__":
    unittest.main()
