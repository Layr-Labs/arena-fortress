import contextlib
import io
import unittest
from overseer.harness import Overseer


class Game:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args))
        return {'ok': True}


class SuspendedWorkshop(unittest.TestCase):
    def test_mood_replaces_explicitly_suspended_construction_only(self):
        for built, suspended, expected in [(False, True, True), (False, False, False),
                                           (True, True, False), (False, None, False)]:
            with self.subTest(built=built, suspended=suspended):
                game = Game()
                agent = Overseer(game)
                agent.count = 0
                agent.load({'tick': 10000, 'observation': {
                    'stocks': {'logs_usable': 20},
                    'map': {'sites': [{'id': 'W2', 'kind': 'W'}]},
                    'moods': [{'mood': 'Fey', 'skill': 'WOODCRAFT'}],
                    'workshops': [{'type': 'Craftsdwarfs', 'built': built,
                        'job_details': [{'job': 'ConstructBuilding', 'suspended': suspended}]}]}})
                with contextlib.redirect_stdout(io.StringIO()):
                    agent.mood()
                self.assertEqual(bool(game.calls), expected)
                if expected:
                    self.assertEqual(game.calls[0], ('build_workshop', {'type': 'Craftsdwarfs', 'site': 'W2'}))
