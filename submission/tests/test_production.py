"""Public-manual production-cadence advice; no game or provider calls."""
import unittest

from plain.prompt import system_prompt


class ProductionPrompt(unittest.TestCase):
    def test_periodic_checks_small_batches_and_shared_food_reserve(self):
        text = system_prompt(tool_names={"add_order", "advance_days"})
        for phrase in ("at each repeat", "small daily", "amount 1", "NOT drinks",
                       "plant stack", "food_edible at_least 2*N", "three conditions",
                       "reserve heuristics", "can differ from observed stocks",
                       "Seedwatch", "not a new food source", "immediate danger"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
