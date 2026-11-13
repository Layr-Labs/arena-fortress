"""An office must contain a chair before the manager can use it."""
import unittest

from support import StubGame, bare
from overseer.harness import Overseer


class ZoneGame(StubGame):
    def act(self, tool, args):
        result = super().act(tool, args)
        if tool == 'make_zone' and result.get('ok'):
            result['result']['zone_id'] = 701
        return result


class ManagerOffice(unittest.TestCase):
    def setup_controller(self, offices=()):
        response = bare(140, 196, fishing=False, cit=22)
        o = response['observation']
        o['administrators'].update(MANAGER_id=94, manager_office={'zone_id': 31, 'chair': False})
        o['zones'] = list(offices)
        o['furniture'] = [{'id': 50, 'kind': 'chair', 'built': True, 'x': 95, 'y': 97, 'z': 103}]
        o['map']['sites'] = [
            {'id': 'A6', 'kind': 'A', 'x': 89, 'y': 94, 'z': 105, 'w': 7, 'h': 3},
            {'id': 'A8', 'kind': 'A', 'x': 89, 'y': 94, 'z': 103, 'w': 13, 'h': 7},
        ]
        game = ZoneGame()
        controller = Overseer(game, days=336)
        controller.load(response)
        controller.count = 0
        return controller, game

    def test_office_uses_level_with_built_chair_and_assigns_returned_zone(self):
        controller, game = self.setup_controller()
        controller.office()
        self.assertEqual(game.tools('make_zone'), [{'kind': 'office', 'site': 'A8'}])
        self.assertEqual(game.tools('assign_zone'), [{'zone_id': 701, 'dwarf_id': 94}])
        self.assertEqual(game.tools('place_furniture'), [])

    def test_chairless_owned_office_does_not_hide_usable_spare(self):
        controller, game = self.setup_controller([
            {'id': 31, 'type': 'Office', 'owner': 94, 'furniture': {}},
            {'id': 32, 'type': 'Office', 'furniture': {'chair': 1}},
        ])
        controller.office()
        self.assertEqual(game.tools('assign_zone'), [{'zone_id': 32, 'dwarf_id': 94}])
        self.assertEqual(game.tools('make_zone'), [])

    def test_lab_chooses_chaired_spare_before_chairless_spare(self):
        controller, game = self.setup_controller([
            {'id': 31, 'type': 'Office', 'furniture': {}},
            {'id': 32, 'type': 'Office', 'furniture': {'chair': 1}},
        ])
        controller.hands_off = 4
        controller.lab = True
        controller.office()
        self.assertEqual(game.tools('assign_zone'), [{'zone_id': 32, 'dwarf_id': 94}])

    def test_usable_owned_office_prevents_repeated_repair(self):
        controller, game = self.setup_controller([
            {'id': 31, 'type': 'Office', 'owner': 94, 'furniture': {}},
            {'id': 32, 'type': 'Office', 'owner': 94, 'furniture': {'chair': 1}},
        ])
        controller.office()
        self.assertEqual(game.calls, [])


class OfficeDigest(unittest.TestCase):
    def check_digest(self, owner=94, chairs=1):
        from plain import digest
        context = {'citizens': 22, 'next': [], 'obs': {
            'administrators': {'MANAGER_id': 94, 'MANAGER': 'Manager',
                               'manager_active_for_orders': True,
                               'manager_office': {'zone_id': 31, 'chair': False}},
            'zones': [{'id': 32, 'type': 'Office', 'owner': owner, 'furniture': {'chair': chairs}}],
        }}
        line = digest._manager(context)
        return context, line

    def test_later_owned_chaired_office_clears_false_missing_chair_diagnosis(self):
        context, line = self.check_digest()
        self.assertTrue(context['office_ok'])
        self.assertEqual(context['next'], [])
        self.assertIn('office zone 32 chair=yes', line)

    def test_other_citizens_office_does_not_satisfy_manager(self):
        context, _ = self.check_digest(owner=95)
        self.assertFalse(context['office_ok'])
        self.assertTrue(context['next'])

    def test_chairless_owned_zone_still_reports_shortfall(self):
        context, _ = self.check_digest(chairs=0)
        self.assertFalse(context['office_ok'])
        self.assertTrue(context['next'])


if __name__ == '__main__':
    unittest.main()
