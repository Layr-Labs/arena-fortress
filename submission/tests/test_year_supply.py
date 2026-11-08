import contextlib
import io
import unittest
from test_housing_reservation import Game
from overseer.harness import Overseer


class YearSupplyScope(unittest.TestCase):
    def test_reserve_and_cooking_changes_are_limited_to_full_year(self):
        for days, stock, drink_cap, end_cap in [(336, 'food_edible', 1000, 1000),
                                               (216, 'plants_total', 300, 600),
                                               (60, 'plants_total', 300, 600)]:
            with self.subTest(days=days):
                game = Game()
                agent = Overseer(game, days=days)
                agent.count = 0
                agent.load({'tick': 1200, 'observation': {
                    'administrators': {'citizens': 7},
                    'stocks': {'food_edible': 1000}}})
                with contextlib.redirect_stdout(io.StringIO()):
                    agent.supply()
                    agent.endgame_supply()
                orders = [args for tool, args in game.calls if tool == 'add_order']
                brew = [o for o in orders if o['recipe'] == 'brew_drink']
                cook = [o for o in orders if o['recipe'] == 'cook_meal']
                self.assertEqual(brew[0]['when'][0]['below'], drink_cap)
                self.assertEqual(brew[1]['when'][0]['below'], end_cap)
                self.assertEqual(cook[0]['when'][1]['stock'], stock)
                self.assertTrue(all(len(o.get('when', [])) <= 3 for o in orders))
