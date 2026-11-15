"""The wealth push should finish once its target is met, and restart if needed."""
import unittest
from support import resp, overseer


class CraftStop(unittest.TestCase):
    def controller(self, wealth):
        response = resp(100, 236, food=50, cit=21,
                        workshops=('Carpenters', 'Still', 'Kitchen', 'Craftsdwarfs'),
                        orders=[{'id': 41, 'job': 'MakeCrafts', 'repeat': 'daily', 'left': 3},
                                {'id': 42, 'job': 'MakeCrafts', 'repeat': 'daily', 'left': 3}])
        response['observation']['wealth'] = {'created': wealth}
        controller, game = overseer(response)
        controller.craft_ids = {41}
        return controller, game, response

    def test_target_met_cancels_own_order_but_preserves_model_order(self):
        controller, game, _ = self.controller(5500)
        controller.progression_push()
        self.assertEqual(game.tools('cancel_order'), [{'order_id': 41}])

    def test_target_not_met_keeps_the_existing_wealth_push(self):
        controller, game, _ = self.controller(5499)
        controller.progression_push()
        self.assertEqual(game.calls, [])

    def test_wealth_drop_after_cancellation_can_restart_production(self):
        controller, game, response = self.controller(5500)
        controller.progression_push()
        response['observation']['orders'] = []
        response['observation']['wealth']['created'] = 5000
        controller.load(response)
        controller.progression_push()
        orders = game.tools('add_manager_order')
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]['job'], 'MakeCrafts')
        self.assertEqual(orders[0]['repeat'], 'daily')


if __name__ == '__main__':
    unittest.main()
