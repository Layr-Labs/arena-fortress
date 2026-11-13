"""MY1 final-month provisions, using public observations and the existing action stub."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp

ARRIVE = 'The merchants need a trade depot to unload their goods.'
LEAVE = 'The merchants from Elisvucar have embarked on their journey.'
HERD = [{'id': i, 'race': race, 'tame': True, 'pet_owner_id': -1}
        for i, race in enumerate(('WATER_BUFFALO', 'YAK', 'COW', 'DONKEY', 'DOG', 'CAT', 'CAT'), 1)]


class Food(unittest.TestCase):
    def make(self, day=150, food=50, days=216, lab=False, **kw):
        ov, g = overseer(resp(216-day, day, food, cit=21, **kw), herd=HERD)
        ov.days, ov.lab = days, lab
        return ov, g

    def observe(self, ov, day, food, events=(), **kw):
        r = resp(216-day, day, food, cit=21, **kw)
        r['observation']['recent_events'] = events
        ov.load(r)
        ov.count = 0
        ov.provision()

    def cooking(self, g):
        return [x for x in g.tools('add_order') if x.get('repeat') == 'daily' and x.get('recipe') == 'cook_meal']

    def test_caravan_masks_low_food_before_feast(self):
        ov, g = self.make()
        ov.provision()
        self.observe(ov, 164, 287, [ARRIVE])
        self.observe(ov, 186, 285)
        self.assertEqual(ov.food_caravan['offset'], 237)
        self.assertEqual(g.tools('slaughter'), [{'unit_id': 6}])
        self.assertEqual(self.cooking(g), [{'recipe': 'cook_meal', 'amount': 2, 'repeat': 'daily',
                                         'when': [{'stock': 'prepared_meals', 'below': 100}]}])
        self.assertEqual(ov.st['food_edible'], 285)  # observations and defence thresholds are untouched

    def test_cook_does_not_need_plants_or_counted_raw_food(self):
        ov, g = self.make(day=186, food=40, meals=40, plants=0)
        ov.provision()
        self.assertEqual(len(self.cooking(g)), 1)
        self.assertEqual(len(g.tools('slaughter')), 1)

    def test_plenty_of_owned_food_leaves_policy_idle(self):
        ov, g = self.make(day=186, food=100, meals=90)
        ov.provision()
        self.assertEqual(g.calls, [])

    def test_no_extra_production_before_final_month(self):
        ov, g = self.make(day=150)
        ov.provision()
        self.observe(ov, 164, 287, [ARRIVE])
        self.observe(ov, 185, 285)
        self.assertEqual(g.calls, [])

    def test_repeated_observation_does_not_duplicate_standing_order(self):
        ov, g = self.make(day=186, food=50)
        ov.provision()
        self.observe(ov, 186, 50)
        self.observe(ov, 188, 50)
        self.assertEqual(len(self.cooking(g)), 1)
        self.assertEqual(len(g.tools('slaughter')), 1)
        self.observe(ov, 191, 50)
        self.assertEqual(len(g.tools('slaughter')), 2)

    def test_hunger_cull_still_reserves_largest_three(self):
        ov, g = self.make(day=186, food=50)
        g.herd = HERD[:3]
        ov.provision()
        self.assertEqual(g.tools('slaughter'), [])
        self.assertEqual(len(self.cooking(g)), 1)

    def test_feast_still_takes_largest_three(self):
        ov, g = self.make(day=202, food=50, meals=50)
        ov.provision()
        self.assertEqual(g.tools('slaughter'), [{'unit_id': 1}, {'unit_id': 2}, {'unit_id': 3}])
        self.assertEqual(len(self.cooking(g)), 1)

    def test_embarkation_keeps_discount_for_thirty_days_and_clamps_at_zero(self):
        ov, g = self.make()
        ov.provision()
        self.observe(ov, 164, 287, [ARRIVE])
        self.observe(ov, 180, 184, [LEAVE])
        self.observe(ov, 190, 44, [LEAVE])  # stale report must not extend the deadline
        self.assertEqual(ov.provision_food(44), 0)
        self.observe(ov, 210, 50)
        self.assertEqual(ov.provision_food(50), 0)
        self.observe(ov, 211, 50)
        self.assertEqual(ov.provision_food(50), 50)

    def test_missed_departure_has_bounded_fallback(self):
        ov, g = self.make(day=0)
        ov.provision()
        self.observe(ov, 20, 287, [ARRIVE])
        self.observe(ov, 111, 50)
        self.assertEqual(ov.provision_food(50), 50)

    def test_missing_or_non_string_events_are_safe(self):
        ov, g = self.make(day=186)
        for events in (None, 'ERR', [None, 7, {}]):
            self.observe(ov, 186, 50, events)
        self.assertEqual(len(self.cooking(g)), 1)

    def test_first_observation_during_caravan_does_not_invent_offset(self):
        ov, g = self.make(day=180, food=287)
        ov.o['recent_events'] = [ARRIVE]
        ov.provision()
        self.assertEqual(ov.food_caravan['offset'], 0)

    def test_unreadable_stocks_do_not_replace_arrival_baseline(self):
        ov, g = self.make()
        ov.provision()
        ov.st = {}
        self.assertEqual(ov.provision_food(0), 0)
        self.observe(ov, 164, 287, [ARRIVE])
        self.assertEqual(ov.food_caravan['offset'], 237)

    def test_op1_and_labs_do_not_enter_new_policy(self):
        for days, lab in ((336, False), (400, False), (216, True), (90, True)):
            ov, g = self.make(day=186, days=days, lab=lab)
            ov.o['recent_events'] = [ARRIVE]
            ov.provision()
            self.assertEqual(g.calls, [], (days, lab))
            self.assertIsNone(ov.food_caravan['last'])

    def test_missing_clock_and_non_open_goal_do_not_enter_new_policy(self):
        for attribute, value in (('days_left', None), ('hands_off', 10), ('surge', True)):
            ov, g = self.make(day=186)
            setattr(ov, attribute, value)
            # plan() only calls provision() with an open-play clock.
            if ov.open_play():
                ov.provision()
            self.assertEqual(g.calls, [])
            self.assertIsNone(ov.food_caravan['last'])

    def test_refused_cook_order_is_retried(self):
        ov, g = self.make(day=186)
        g.refuse.add(('add_order', None))
        ov.provision()
        self.observe(ov, 187, 50)
        self.assertEqual(len(self.cooking(g)), 1)
        g.refuse.clear()
        self.observe(ov, 189, 50)
        self.assertEqual(len(self.cooking(g)), 2)
        self.observe(ov, 192, 50)
        self.assertEqual(len(self.cooking(g)), 2)


if __name__ == '__main__':
    unittest.main()
