"""Positive food stock alone does not establish the year's projected supply."""
import io
import unittest
from contextlib import redirect_stdout
import test_food_slaughter as base
from overseer.harness import Overseer

class YearFoodReserve(unittest.TestCase):
    def run_food(self, food, animals, days=336):
        game = base.Game(animals)
        guard = Overseer(game, days=days)
        guard.count = 0
        guard.load({"day": days - 20, "days_left": 20, "observation": {
            "administrators": {"citizens": 13}, "stocks": {"food_edible": food},
            "workshops": [{"type": "Butchers"}]}})
        with redirect_stdout(io.StringIO()):
            guard.endgame_supply()
        return [(tool, args) for tool, args in game.calls if tool == "slaughter"]

    def test_year_reserve_uses_adult_livestock_above_the_old_emergency_threshold(self):
        calls = self.run_food(60, [base.animal(1, "RABBIT"), base.animal(2, "MULE")])
        self.assertEqual(calls, [("slaughter", {"unit_id": 2})])

    def test_proactive_reserve_keeps_small_juvenile_and_owned_animals(self):
        animals = [base.animal(1, "RABBIT"), base.animal(2, "YAK", adult=False),
                   base.animal(3, "COW", pet_owner_id=0), base.animal(4, "HORSE", tame=False)]
        self.assertEqual(self.run_food(60, animals), [])

    def test_short_handover_does_not_gain_the_year_reserve_branch(self):
        self.assertEqual(self.run_food(60, [base.animal(2, "MULE")], days=216), [])

    def test_ample_year_food_does_not_slaughter_for_reserve(self):
        self.assertEqual(self.run_food(200, [base.animal(2, "MULE")]), [])

    def test_existing_low_food_emergency_retains_its_small_animal_fallback(self):
        self.assertEqual(self.run_food(40, [base.animal(1, "RABBIT")]),
                         [("slaughter", {"unit_id": 1})])

if __name__ == "__main__":
    unittest.main()
