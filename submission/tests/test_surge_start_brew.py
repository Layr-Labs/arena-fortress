"""cx lt08seed: a surge fort books one one-shot brew of its starting brewable plants on its first pass (no `when`), so
the first validation look brews them before they rot (d17-19 in every record where nothing could fire at ~570 drink:
those forts ended drink[H] - drink[A] <= 0); the seed comes back and is sown for a harvest inside the window.
No game or network."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_surge_floor import Base, obs  # noqa: E402


def starts(game):
    return [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink" and "when" not in a]


class SurgeStartBrew(Base):
    def test_first_pass_books_the_starting_plants(self):
        # the LT08 forts' day 0: 7 plump helmets, food 58 for 18 citizens, drink 571
        o, game = self.ov(hands_off=39, cit=18, stocks={"plants_brewable": 7, "food_edible": 58, "drink": 571}, day=0)
        o.surge_start_brew()
        self.assertEqual(starts(game), [{"recipe": "brew_drink", "amount": 7}])

    def test_once_a_game(self):
        o, game = self.ov(hands_off=39, cit=18, stocks={"plants_brewable": 7, "food_edible": 58}, day=0)
        o.surge_start_brew()
        o.load(obs(hands_off=37, cit=38, stocks={"plants_brewable": 7, "food_edible": 60}, day=2))
        o.surge_start_brew()
        self.assertEqual(len(starts(game)), 1)

    def test_not_in_the_window_prep_nor_open_play(self):
        o, game = self.ov(hands_off=14)
        o.surge_start_brew()
        self.assertEqual(starts(game), [])
        o2, game2 = self.ov(surge=False)
        o2.surge_start_brew()
        self.assertEqual(starts(game2), [])

    def test_food_keeps_one_per_citizen(self):
        o, game = self.ov(hands_off=39, cit=46, stocks={"plants_brewable": 6, "food_edible": 50}, day=0)
        o.surge_start_brew()
        self.assertEqual(starts(game), [])
        o.load(obs(hands_off=38, cit=46, stocks={"plants_brewable": 6, "food_edible": 52}, day=1))
        o.surge_start_brew()
        self.assertEqual(starts(game), [{"recipe": "brew_drink", "amount": 6}])

    def test_no_plants_no_order(self):
        o, game = self.ov(hands_off=39, stocks={"plants_brewable": 0}, day=0)
        o.surge_start_brew()
        self.assertEqual(starts(game), [])


if __name__ == "__main__":
    unittest.main()
