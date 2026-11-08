"""V0op's only changes are three supply guards that activate on full-year runs (days >= 336) alone: on every
stage-1 task (labs 45-90 d, MY1 216 d) the overseer must behave exactly like the leader's. No game or network."""
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
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": len(self.calls)}}


def facts(days, cit=10, stocks=None):
    return {"tick": 0, "observation": {
        "administrators": {"citizens": cit, "manager_active_for_orders": True, "MANAGER_id": 1},
        "stocks": stocks if stocks is not None else {"plants_brewable": 20, "plants_total": 40,
                                                     "prepared_meals": 0, "food_edible": 200},
        "map": {"sites": []}, "zones": [], "furniture": [], "workshops": [],
        "orders": [], "plugins": {"autochop": "on", "seedwatch": "on", "autofarm": "on"},
        "date": {"abs_tick": 0},
    }}


class Op1Gate(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, days, cit=10, stocks=None):
        game = FakeGame()
        overseer = harness.Overseer(game, days=days)
        overseer.load(facts(days, cit=cit, stocks=stocks))
        overseer.count = 0
        return overseer, game

    def whens(self, game, tool="add_order"):
        return [a["when"] for t, a in game.calls if t == tool and a.get("recipe") == "cook_meal"]

    def test_cook_reserve_only_on_full_year(self):
        overseer, game = self.overseer(336)
        overseer.supply()
        self.assertIn({"stock": "plants_brewable", "at_least": harness.COOK_PLANTS_RESERVE}, self.whens(game)[0])
        for days in (216, 60, 90):   # MY1 and the labs: the leader's bare cook when
            overseer2, game2 = self.overseer(days)
            overseer2.supply()
            self.assertNotIn({"stock": "plants_brewable", "at_least": harness.COOK_PLANTS_RESERVE},
                             self.whens(game2)[0])

    def test_endgame_food_gate_only_on_full_year(self):
        overseer, game = self.overseer(336)
        overseer.endgame_supply()
        end = [a["when"] for t, a in game.calls if t == "add_order" and a.get("recipe") == "cook_meal"][0]
        self.assertIn({"stock": "food_edible", "at_least": max(30, overseer.cit)}, end)
        self.assertIn({"stock": "plants_brewable", "at_least": harness.COOK_PLANTS_RESERVE}, end)
        for days in (216, 60):
            overseer2, game2 = self.overseer(days)
            overseer2.endgame_supply()
            end2 = [a["when"] for t, a in game2.calls if t == "add_order" and a.get("recipe") == "cook_meal"][0]
            self.assertIn({"stock": "food_edible", "at_least": max(30, 4 * overseer2.cit)}, end2)
            self.assertNotIn({"stock": "plants_brewable", "at_least": harness.COOK_PLANTS_RESERVE}, end2)

    def test_farm_target_only_on_full_year(self):
        overseer, _ = self.overseer(336, cit=18)
        self.assertEqual(overseer.farm_target(), 6)          # ceil(18/3), min 6
        overseer2, _ = self.overseer(336, cit=7)
        self.assertEqual(overseer2.farm_target(), 6)         # the floor
        overseer3, _ = self.overseer(336, cit=45)
        self.assertEqual(overseer3.farm_target(), 12)        # the cap
        for days in (216, 60, 90):   # stage-1 tasks: the leader's sizing
            overseer4, _ = self.overseer(days, cit=18)
            self.assertEqual(overseer4.farm_target(), 4)


if __name__ == "__main__":
    unittest.main()
