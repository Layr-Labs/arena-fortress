import contextlib
import io
import unittest
from test_housing_reservation import Game
from overseer.harness import Overseer


class DigDimensions(unittest.TestCase):
    def test_large_population_stays_within_frozen_dig_room_limit(self):
        for citizens in [7, 47, 80, 130]:
            with self.subTest(citizens=citizens):
                game = Game()
                agent = Overseer(game, days=336)
                agent.count = 0
                agent.load({'tick': 1200, 'observation': {
                    'administrators': {'citizens': citizens},
                    'farm_plots': [{'id': 1}, {'id': 2}],
                    'map': {'sites': [{'id': 'R1', 'kind': 'R', 'soil': False}]}}})
                with contextlib.redirect_stdout(io.StringIO()):
                    agent.digging()
                tool, args = game.calls[0]
                self.assertEqual(tool, 'dig_room')
                self.assertLessEqual(args['w'], 15)
                self.assertLessEqual(args['h'], 15)
