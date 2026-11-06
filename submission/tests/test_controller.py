import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

CANDIDATE = Path(__file__).resolve().parents[1]
REPO = CANDIDATE.parent
sys.path.insert(0, str(REPO / 'baseline' / 'tests'))
sys.path.insert(0, str(CANDIDATE))
from fakes import FakeGame, FakeModel
from plain.controller import Controller
from plain.harness import Steward
from dfbench_client import GameClient, ModelClient, Task, ActionLimit

TOOLS = json.loads((REPO / 'runner/fakes/tool_schemas.json').read_text())
SCHEMAS = {t['function']['name']: t['function']['parameters'] for t in TOOLS}


def observation(**extra):
    o = dict(dwarves=[{'id': i, 'name': str(i), 'positions': [], 'profession': 'Farmer'} for i in range(7)],
             stocks={'logs_usable': 20, 'furniture_free': {}, 'plants_brewable': 50, 'drink': 100, 'food_edible': 100},
             plugins={p: 'on' for p in ('autolabor', 'autochop', 'seedwatch', 'autofarm')},
             administrators={'manager_active_for_orders': True, 'MANAGER_id': 0, 'manager_office': {'chair': True}},
             workshops=[{'type': t, 'built': True} for t in ('Carpenters', 'Still', 'Kitchen')],
             map={'sites': []}, orders=[])
    o.update(extra)
    return {'day': 10, 'observation': o, 'days_left': 326}


def controller(**extra):
    c = Controller({'days': 336})
    c.update(observation(**extra))
    return c


class PolicyTests(unittest.TestCase):
    def test_automation_call_has_no_name_collision(self):
        c = controller(plugins={})
        self.assertEqual(c.next(), ('enable_automation', {'name': 'autolabor'}))

    def test_success_without_observation_change_not_repeated_while_paused(self):
        c = controller(plugins={})
        name, args = c.next()
        c.remember(name, args, {'ok': True})
        self.assertNotEqual(c.next(), (name, args))

    def test_action_counter_change_is_not_fort_progress(self):
        c = controller(plugins={}, actions_left_today=40)
        name, args = c.next()
        c.remember(name, args, {'ok': True})
        c.update(observation(plugins={}, actions_left_today=39))
        self.assertFalse(c.available(name, args))

    def test_changed_observation_allows_another_placement(self):
        c = controller()
        args = {'kind': 'table', 'site': 'A1', 'count': 1}
        c.remember('place_furniture', args, {'ok': True})
        self.assertFalse(c.available('place_furniture', args))
        c.update(observation(furniture=[{'kind': 'table', 'id': 81}]))
        self.assertTrue(c.available('place_furniture', args))

    def test_built_office_not_repeated(self):
        self.assertIsNone(controller().office())

    def test_assign_existing_office_before_making_another(self):
        c = controller(administrators={'manager_active_for_orders': True, 'MANAGER_id': 0},
                       zones=[{'id': 20, 'type': 'Office', 'furniture': {'chair': 1}}])
        self.assertEqual(c.office(), ('assign_zone', {'zone_id': 20, 'dwarf_id': 0}))

    def test_new_office_contains_an_existing_chair(self):
        c = controller(administrators={'manager_active_for_orders': True, 'MANAGER_id': 0},
                       furniture=[{'kind': 'chair', 'x': 4, 'y': 4, 'z': 10}],
                       map={'sites': [{'id': 'A1', 'kind': 'A', 'x': 3, 'y': 3, 'z': 10,
                                       'w': 5, 'h': 5, 'open_tiles': 25}]})
        self.assertEqual(c.office(), ('make_zone', {'kind': 'office', 'site': 'A1'}))

    def test_no_office_before_chair_location_known(self):
        c = controller(administrators={'manager_active_for_orders': True, 'MANAGER_id': 0},
                       map={'sites': [{'id': 'A1', 'kind': 'A', 'x': 3, 'y': 3, 'z': 10,
                                       'w': 5, 'h': 5, 'open_tiles': 25}]})
        self.assertEqual(c.office()[0], 'add_order')

    def test_pending_chair_construction_gets_time(self):
        c = controller(administrators={'manager_active_for_orders': True, 'MANAGER_id': 0},
                       zones=[{'id': 20, 'type': 'Office', 'owner': 0, 'furniture_planned': {'chair': 1}}])
        self.assertIsNone(c.office())

    def test_failed_sites_back_off_and_other_sites_are_available(self):
        c = controller(workshops=[], map={'sites': [{'kind': 'W', 'id': 'W1'}, {'kind': 'W', 'id': 'W2'}]})
        action = c.build('Carpenters')
        c.remember(*action, {'ok': False, 'error_code': 'tile_occupied'})
        self.assertEqual(c.build('Carpenters')[1]['site'], 'W2')
        c.day += 3
        self.assertEqual(c.build('Carpenters')[1]['site'], 'W1')

    def test_duplicate_recipes_not_readded(self):
        c = controller(orders=[{'id': 1, 'recipe': 'brew_drink', 'left': 0, 'repeat': 'daily'}])
        self.assertIsNone(c.recipe('brew_drink', 5))

    def test_migrant_goal_does_not_queue_dining_while_beds_are_being_made(self):
        c = Controller({'days': 60, 'hands_off': {'from_day': 39}, 'goal': 'Every dwarf must have a placed bed.'})
        c.update(observation(orders=[{'recipe': r, 'left': 5, 'repeat': 'daily'}
                                     for r in ('make_barrel', 'brew_drink', 'make_bed')]))
        self.assertEqual(c.production()[1]['recipe'], 'cook_meal')

    def test_migrant_bed_order_is_recurring_to_avoid_validation_gaps(self):
        c = Controller({'days': 60, 'hands_off': {'from_day': 39}, 'goal': 'Every dwarf must have a placed bed.'})
        c.update(observation(orders=[{'recipe': r, 'left': 5, 'repeat': 'daily'}
                                     for r in ('make_barrel', 'brew_drink')]))
        name, args = c.production()
        self.assertEqual(args['recipe'], 'make_bed')
        self.assertEqual(args['repeat'], 'daily')
        self.assertEqual(args['when'][0]['stock'], 'beds')

    def test_final_active_days_are_observed_daily(self):
        c = controller()
        c.response['hands_off_in_days'] = 2
        self.assertEqual(c.advance_days(), 1)

    def test_one_time_done_order_can_be_replaced(self):
        c = controller(orders=[{'id': 1, 'recipe': 'make_bed', 'left': 0}])
        self.assertEqual(c.recipe('make_bed', 5)[0], 'add_order')

    def test_farms_require_revealed_soil(self):
        c = controller(map={'sites': [{'kind': 'R', 'id': 'R1', 'soil': True, 'dug': False},
                                     {'kind': 'F', 'id': 'F1', 'subterranean': False}]})
        self.assertIsNone(c.farming())

    def test_dug_soil_can_be_farmed(self):
        c = controller(map={'sites': [{'kind': 'R', 'id': 'R1', 'soil': True, 'dug': True,
                                      'tiles': {'soil_floor': 9, 'tiles': 9}}]})
        self.assertEqual(c.farming(), ('build_farm', {'site': 'R1'}))

    def test_dining_furniture_is_placed_in_pairs(self):
        c = controller(furniture=[{'kind': 'bed'} for _ in range(11)] + [{'kind': 'chair'}],
                       map={'sites': [{'kind': 'A', 'id': 'A1', 'open_tiles': 40}]})
        c.free = {'table': 10, 'chair': 10}
        self.assertEqual(c.housing(), ('place_furniture', {'kind': 'table', 'site': 'A1', 'count': 1}))
        c.placed['table'] += 1
        # A successful table placement in this paused state cannot be duplicated.
        c.remember('place_furniture', {'kind': 'table', 'site': 'A1', 'count': 1}, {'ok': True})
        self.assertEqual(c.housing(), ('place_furniture', {'kind': 'chair', 'site': 'A1', 'count': 1}))

    def test_construction_beds_count_towards_capacity(self):
        c = controller(furniture=[{'kind': 'bed', 'built': False} for _ in range(11)])
        c.free = {'bed': 10}
        c.areas = [{'id': 'A1', 'open_tiles': 20}]
        self.assertIsNone(c.housing())

    def test_mood_skill_chooses_workshop(self):
        c = controller(moods=[{'skill': 'WOODCRAFT'}], map={'sites': [{'kind': 'W', 'id': 'W1'}]})
        self.assertEqual(c.mood(), ('build_workshop', {'type': 'Craftsdwarfs', 'site': 'W1'}))

    def test_room_does_not_extend_beyond_the_listed_box(self):
        c = controller(map={'sites': [{'kind': 'R', 'id': 'R1', 'x': 11, 'y': 9, 'z': 100,
                                      'stair': {'x': 10, 'y': 10}, 'soil': True}]})
        self.assertEqual(c.digging(), ('dig_room', {'site': 'R1', 'w': 3, 'h': 3}))

    def test_small_rooms_can_get_additional_access_for_large_population(self):
        c = controller(dwarves=[{'id': i} for i in range(50)],
                       map={'sites': [{'kind': 'S', 'id': 'S5', 'z': 100, 'soil': True}]})
        c.stairs_started = {'S1': -20, 'S2': -20, 'S3': -20, 'S4': -20}
        self.assertEqual(c.digging(), ('dig_stairs', {'site': 'S5', 'z_bottom': 98}))

    def test_stalled_digging_does_not_block_every_other_site_forever(self):
        c = controller(dig_designations_pending=50,
                       map={'sites': [{'kind': 'S', 'id': 'S2', 'z': 100, 'soil': True}]})
        self.assertIsNone(c.digging())
        later = observation(dig_designations_pending=50,
                            map={'sites': [{'kind': 'S', 'id': 'S2', 'z': 100, 'soil': True}]})
        later['day'] = 23
        c.update(later)
        self.assertEqual(c.digging(), ('dig_stairs', {'site': 'S2', 'z_bottom': 98}))

    def test_uncertain_observation_does_not_crash(self):
        c = controller(stocks='ERR: probe', zones='ERR', map='ERR', orders='ERR')
        self.assertIsNone(c.production())
        c.next()


class IntegrationTests(unittest.TestCase):
    def run_fake(self, days=20, hands_off=None, script=None, k=40):
        with FakeGame(days=days, hands_off_day=hands_off, k=k) as g, FakeModel(script=script) as m:
            task = Task({'game_url': g.url, 'task': {'days': days}, 'budget': {'credits': 0.1},
                         'limits': {'actions_per_game_day': k},
                         'model': {'base_url': m.url, 'name': 'z-ai/glm-5.3-flash'}})
            client = ModelClient(m.url, task.model_name, max_retries=0)
            agent = Steward(task, GameClient(g.url), client)
            with contextlib.redirect_stdout(io.StringIO()):
                agent.run(max_steps=300)
            return g, m, agent

    def test_fake_http_game_completes(self):
        g, m, a = self.run_fake()
        self.assertEqual(a.stop_reason, 'game_over')
        self.assertEqual(g.day, 20)
        self.assertGreater(a.stats['advances'], 0)
        self.assertLess(a.stats['actions'], 120)

    def test_hands_off_stops_actions(self):
        g, m, a = self.run_fake(days=60, hands_off=10)
        self.assertEqual(a.stop_reason, 'hands_off')
        self.assertEqual(g.day, 10)

    def test_model_failure_keeps_management_running(self):
        g, m, a = self.run_fake(script=[('http', 500, {'error': 'unavailable'})] * 3)
        self.assertEqual(a.stop_reason, 'game_over')
        self.assertGreater(a.stats['model_errors'], 0)

    def test_bad_model_json_is_recoverable(self):
        g, m, a = self.run_fake(script=[('badjson',)])
        self.assertEqual(a.stop_reason, 'game_over')

    def test_malformed_advice_keeps_management_running(self):
        cases = [
            ('place_furniture', {'kind': 'bed', 'site': ['A1'], 'count': 1}),
            ('enable_automation', {'name': ['autofarm']}),
            ('cancel_order', {'order_id': [3]}),
            (['place_furniture'], {'kind': 'bed', 'site': 'A1', 'count': 1}),
        ]
        for name, args in cases:
            with self.subTest(name=name):
                g, m, a = self.run_fake(script=[('call', name, args)])
                self.assertGreater(len(m.requests), 0)
                self.assertEqual(a.stop_reason, 'game_over')
                self.assertEqual(g.day, 20)
                self.assertGreater(a.stats['advances'], 0)
                self.assertFalse(any(entry['tool'] == name and entry['args'] == args for entry in g.log))

    def test_budget_block_is_recoverable(self):
        g, m, a = self.run_fake(script=[('http', 402, {'error': 'budget'})])
        self.assertTrue(a.model_disabled)
        self.assertEqual(a.stop_reason, 'game_over')

    def test_action_limit_does_not_end_the_run(self):
        g, m, a = self.run_fake(k=3)
        self.assertEqual(a.stop_reason, 'game_over')
        self.assertEqual(g.day, 20)

    def test_model_cannot_restore_oversized_excavation(self):
        agent = Steward(Task({}), Mock(), Mock())
        agent.tool_names = {'dig_room'}
        agent.schemas = SCHEMAS
        agent.control = controller()
        self.assertFalse(agent.model_allowed('dig_room', {'site': 'R1', 'w': 9, 'h': 9}))
        self.assertTrue(agent.model_allowed('dig_room', {'site': 'R1'}))

    def test_different_custom_reaction_is_not_a_duplicate(self):
        agent = Steward(Task({}), Mock(), Mock())
        agent.tool_names = {'add_manager_order'}
        agent.schemas = SCHEMAS
        agent.control = controller(orders=[{'job': 'CustomReaction', 'reaction': 'BREW_DRINK_FROM_PLANT', 'left': 5}])
        self.assertTrue(agent.model_allowed('add_manager_order', {'job': 'CustomReaction', 'reaction': 'PROCESS_PLANTS_TO_BAG', 'amount': 2}))
        self.assertFalse(agent.model_allowed('add_manager_order', {'job': 'CustomReaction', 'reaction': 'BREW_DRINK_FROM_PLANT', 'amount': 2}))

    def test_actual_action_limit_exception_advances(self):
        task = Task({})
        game = Mock()
        game.act.side_effect = [ActionLimit('limit'), {'ok': True, 'result': {'advanced_ticks': 1200}}]
        agent = Steward(task, game, Mock())
        agent.tool_names = {'add_order', 'advance_days'}
        agent.control = controller()
        with contextlib.redirect_stdout(io.StringIO()):
            result = agent.action('add_order', {'recipe': 'brew_drink', 'amount': 5}, 'test')
        self.assertTrue(result['ok'])
        game.act.assert_called_with('advance_days', {'days': 1})


class AdviceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.game, self.model = Mock(), Mock()
        self.game.query.return_value = {'jobs': []}
        self.model.usage = {'cost_usd': 0}
        self.agent = Steward(Task({}), self.game, self.model)
        self.agent.tools = TOOLS
        self.agent.tool_names = set(SCHEMAS)
        self.agent.schemas = SCHEMAS
        self.agent.info = {'days': 336}
        self.agent.control = controller()

    def consult(self, name, args):
        def reply(tool, arguments):
            return {'choices': [{'message': {'role': 'assistant', 'tool_calls': [
                {'id': 'test', 'type': 'function',
                 'function': {'name': tool, 'arguments': json.dumps(arguments)}}]}}]}
        self.model.chat.side_effect = [reply(name, args), reply('advance_days', {'days': 1})]
        with contextlib.redirect_stdout(io.StringIO()):
            self.agent.consult()

    def test_invalid_nested_conditions_never_reach_policy_checks(self):
        cases = [
            {'when': 'drink'}, {'when': [['drink']]},
            {'when': [{'stock': ['drink'], 'below': 100}]},
            {'when': [{'stock': 'drink', 'below': True}]},
            {'when': [{'stock': 'drink', 'below': '100'}]},
            {'when': [{'below': 100}]},
            {'when': [{'stock': 'drink', 'below': 100, 'invented': 1}]},
            {'when': []}, {'when': [{'stock': 'drink', 'below': 100}] * 4},
            {'amount': True}, {'amount': 1.5}, {'amount': 0}, {'amount': 31},
            {'recipe': 'invented'}, {'invented': 1},
        ]
        self.agent.control.available = Mock(return_value=True)
        for change in cases:
            with self.subTest(change=change):
                self.assertFalse(self.agent.model_allowed('add_order',
                    {'recipe': 'brew_drink', 'amount': 5, **change}))
        self.agent.control.available.assert_not_called()

    def test_valid_nested_orders_are_preserved(self):
        self.assertTrue(self.agent.model_allowed('add_order', {
            'recipe': 'brew_drink', 'amount': 5, 'repeat': 'daily',
            'when': [{'stock': 'drink', 'below': 100}]}))
        self.assertTrue(self.agent.model_allowed('add_manager_order', {
            'job': 'CustomReaction', 'reaction': 'BREW_DRINK_FROM_PLANT', 'amount': 5,
            'when': [{'item_type': 'PLANT', 'flags': ['unrotten'], 'at_least': 1}]}))

    def test_malformed_query_arguments_never_reach_game(self):
        for args in ({'query': ['jobs']}, {'query': 'jobs', 'limit': []},
                     {'query': 'jobs', 'limit': True}, {'query': 'jobs', 'name': 'stocks'},
                     {'query': 'invented'}, {}):
            with self.subTest(args=args):
                self.game.reset_mock()
                self.consult('read_query', args)
                self.game.query.assert_not_called()
                self.game.act.assert_not_called()

    def test_valid_query_preserves_parameters(self):
        self.game.query.return_value = {'jobs': []}
        self.consult('read_query', {'query': 'jobs', 'limit': 5})
        self.game.query.assert_called_once_with('jobs', limit=5)

    def test_valid_action_reaches_game(self):
        self.game.act.return_value = {'ok': True, 'result': {'placed': 'bed', 'n': 1}}
        self.game.observe.return_value = observation()
        self.consult('place_furniture', {'kind': 'bed', 'site': 'A1', 'count': 1})
        self.game.act.assert_called_once_with('place_furniture', {'kind': 'bed', 'site': 'A1', 'count': 1})


if __name__ == '__main__':
    unittest.main()
