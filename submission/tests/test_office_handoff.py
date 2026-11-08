"""A manager replaced after a noble appointment must recover a furnished office."""
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


class OfficeHandoff(unittest.TestCase):
    def test_reuses_old_managers_chair_even_if_new_empty_office_exists(self):
        for empty in [False, True]:
            with self.subTest(empty=empty):
                game = Game()
                agent = Overseer(game)
                agent.count = 0
                zones = [{'id': 6, 'type': 'Office', 'owner': 94, 'furniture': {'chair': 1}}]
                if empty:
                    zones.append({'id': 63, 'type': 'Office', 'owner': 95, 'furniture': {}})
                agent.load({'tick': 10000, 'observation': {
                    'administrators': {'citizens': 50, 'MANAGER_id': 95,
                                       'manager_active_for_orders': True,
                                       'manager_office': {'chair': False} if empty else 'none'},
                    'zones': zones}})
                with contextlib.redirect_stdout(io.StringIO()):
                    agent.office()
                self.assertEqual(game.calls, [('assign_zone', {'zone_id': 6, 'dwarf_id': 95})])
