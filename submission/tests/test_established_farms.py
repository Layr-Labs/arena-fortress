import contextlib
import io
import unittest
from test_housing_reservation import Game
from overseer.harness import Overseer


class EstablishedFarmScope(unittest.TestCase):
    def test_midyear_retains_parent_farm_priority(self):
        game = Game()
        agent = Overseer(game, days=216)
        agent.count = 0
        agent.load({'tick': 1200, 'observation': {
            'administrators': {'citizens': 47},
            'farm_plots': [{'id': 1}, {'id': 2}],
            'map': {'sites': [{'kind': 'R', 'id': 'R' + str(i), 'soil': True}
                             for i in range(1, 7)]}}})
        with contextlib.redirect_stdout(io.StringIO()):
            agent.digging()
        self.assertEqual(set(agent.roles.values()), {'farm'})
        self.assertTrue(all('w' not in args for _, args in game.calls))
