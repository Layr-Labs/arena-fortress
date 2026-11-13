"""A controller pass must not send two buildings to one observed free site."""
import unittest

from support import bare, overseer


class WorkshopReservations(unittest.TestCase):
    def test_core_workshops_share_stale_observation_without_colliding(self):
        response = bare(336, 0, workshops=(), fishing=False)
        response['observation']['map']['sites'] = [
            {'id': f'W{i}', 'kind': 'W'} for i in range(1, 4)
        ]
        controller, game = overseer(response)
        controller.workshops()
        builds = game.tools('build_workshop')
        self.assertEqual([(b['type'], b['site']) for b in builds], [
            ('Carpenters', 'W1'), ('Still', 'W2'), ('Kitchen', 'W3')
        ])

    def test_refused_build_leaves_site_available_for_other_workshop(self):
        controller, game = overseer(bare(336, 0, workshops=(), fishing=False),
                                   refuse=[('build_workshop', None)])
        controller.build('Carpenters')
        game.refuse.clear()
        controller.build('Still')
        self.assertEqual(game.tools('build_workshop')[-1], {'type': 'Still', 'site': 'W1'})


if __name__ == '__main__':
    unittest.main()
