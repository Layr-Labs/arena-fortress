import unittest

from test_controller import Controller, controller, observation


class CapacityTests(unittest.TestCase):
    def test_workshops_scale_with_citizens(self):
        c = controller(dwarves=[{'id': i} for i in range(46)])
        self.assertEqual(c.workshop_target('Carpenters'), 5)
        self.assertEqual(c.workshop_target('Still'), 2)
        self.assertEqual(c.workshop_target('Kitchen'), 1)

    def test_planned_workshops_count_toward_capacity(self):
        c = controller(workshops=[{'type': 'Carpenters', 'built': True},
                                  {'type': 'Carpenters', 'built': False}],
                       map={'sites': [{'id': 'W1', 'kind': 'W', 'free': True}]})
        self.assertIsNone(c.build('Carpenters', target=2))
        self.assertEqual(c.build('Carpenters', target=3), ('build_workshop', {'type': 'Carpenters', 'site': 'W1'}))

    def test_one_shot_brewing_does_not_replace_standing_production(self):
        c = controller(orders=[{'id': 1, 'recipe': 'brew_drink', 'left': 5}])
        action = c.recipe('brew_drink', 5, [{'stock': 'drink', 'below': 500}])
        self.assertEqual(action[0], 'add_order')
        self.assertEqual(action[1]['repeat'], 'daily')

    def test_old_standing_threshold_is_resized_after_migration(self):
        order = {'id': 1, 'recipe': 'brew_drink', 'left': 5, 'repeat': 'daily',
                 'when': [{'item_type': 'DRINK', 'test': 'LessThan', 'value': 100}]}
        c = controller(orders=[order])
        c.update({**observation(orders=[order]), 'day': 18})
        self.assertEqual(c.recipe('brew_drink', 5, [{'stock': 'drink', 'below': 800}]),
                         ('cancel_order', {'order_id': 1}))

    def test_young_or_adequate_order_is_not_churned(self):
        order = {'id': 1, 'recipe': 'brew_drink', 'left': 5, 'repeat': 'daily',
                 'when': [{'stock': 'drink', 'test': 'LessThan', 'value': 500}]}
        c = controller(orders=[order])
        self.assertIsNone(c.recipe('brew_drink', 5, [{'stock': 'drink', 'below': 1000}]))
        c.update({**observation(orders=[order]), 'day': 30})
        self.assertIsNone(c.recipe('brew_drink', 5, [{'stock': 'drink', 'below': 600}]))

    def test_drink_target_grows_before_hands_off(self):
        c = Controller({'days': 60, 'hands_off': {'from_day': 39, 'days': 21}})
        c.update({**observation(dwarves=[{'id': i} for i in range(46)]), 'hands_off_in_days': 13})
        self.assertEqual(c.drink_target(), 1472)
        c.update({**observation(dwarves=[{'id': i} for i in range(46)]), 'hands_off_in_days': 20})
        self.assertEqual(c.drink_target(), 828)

    def test_finished_small_room_does_not_delay_new_access_for_ten_days(self):
        c = controller(map={'sites': [{'id': 'S2', 'kind': 'S', 'free': True, 'soil': True,
                                      'x': 10, 'y': 10, 'z': 20}]}, dig_designations_pending=0)
        c.rooms_started['R1'] = 7
        self.assertEqual(c.digging(), ('dig_stairs', {'site': 'S2', 'z_bottom': 18}))

    def test_full_room_does_not_retry_when_only_bed_count_changes(self):
        area = {'id': 'A1', 'kind': 'A', 'x': 0, 'y': 0, 'z': 1, 'w': 3, 'h': 3, 'open_tiles': 9}
        c = controller(map={'sites': [area]})
        c.remember('place_furniture', {'kind': 'bed', 'site': 'A1', 'count': 10},
                   {'ok': False, 'error_code': 'no_space'})
        self.assertFalse(c.available('place_furniture', {'kind': 'bed', 'site': 'A1', 'count': 20}))
        c.update(observation(map={'sites': [{**area, 'w': 6, 'open_tiles': 18}]}))
        self.assertTrue(c.available('place_furniture', {'kind': 'bed', 'site': 'A1', 'count': 20}))

    def test_reopened_room_retries_the_same_count(self):
        area = {'id': 'A1', 'kind': 'A', 'x': 0, 'y': 0, 'z': 1, 'w': 3, 'h': 3, 'open_tiles': 9}
        c = controller(map={'sites': [area]})
        args = {'kind': 'bed', 'site': 'A1', 'count': 10}
        c.remember('place_furniture', args, {'ok': False, 'error_code': 'no_space'})
        c.update(observation(map={'sites': [{**area, 'w': 6, 'open_tiles': 18}]}))
        self.assertTrue(c.available('place_furniture', args))
