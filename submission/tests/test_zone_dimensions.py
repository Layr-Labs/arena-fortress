"""Zone size overrides cross the real public dispatcher; no DF process or network."""
import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace

from gameapi.facts.game import Game as FactsGame
from gameapi.facts.sites import SiteState
from gameapi.facts.tools import tool_schemas
from plain.harness import Plain, prepare_tools
from dfbench_client.task import Task
from test_batch import Game, tool


def facts_game(w=22, h=7):
    game = object.__new__(FactsGame)
    game.sites = SiteState()
    game.sites.current['A1'] = {'id': 'A1', 'kind': 'A', 'x': 30, 'y': 40,
                                'z': 10, 'w': w, 'h': h, 'free': True}
    game.refresh_sites = lambda: None
    game.tools = tool_schemas
    game.blueprints = []
    def quickfort(*args):
        game.blueprints.append(args)
        return 'Zones designated: 1\nZone tiles designated: 140'
    game._quickfort = quickfort
    game._lua = lambda *args: {'zone_id': 99}
    return game


class ZoneDimensionsTests(unittest.TestCase):
    def test_schema_exposes_only_zone_size_without_mutating_task(self):
        source = tool_schemas()
        before = copy.deepcopy(source)
        prepared = prepare_tools(source)
        self.assertEqual(source, before)
        for old, new in zip(source, prepared):
            name = old['function']['name']
            if name not in ('make_zone', 'advance_days'):
                self.assertEqual(old, new)
        zone = next(t['function'] for t in prepared if t['function']['name'] == 'make_zone')
        for axis in ('w', 'h'):
            size = zone['parameters']['properties'][axis]
            self.assertEqual((size['type'], size['minimum'], size['maximum']), ('integer', 1, 20))
        self.assertEqual(zone['parameters']['required'], ['kind', 'site'])
        self.assertNotIn('x', zone['parameters']['properties'])
        self.assertIn('No automatic resizing', zone['description'])
        self.assertEqual(prepare_tools(prepared), prepared)

    def test_absent_zone_tool_is_not_invented(self):
        self.assertEqual(prepare_tools([]), [])
        other = [{'type': 'function', 'function': {'name': 'make_zone', 'parameters': {}}}]
        self.assertEqual(prepare_tools(other), other)

    def test_oversized_default_fails_before_df_explicit_size_reaches_emitter(self):
        game = facts_game()
        bad = game.act('make_zone', {'kind': 'office', 'site': 'A1'})
        self.assertFalse(bad['ok'])
        self.assertEqual(bad['error_code'], 'bad_arguments')
        self.assertIn('[1,20]', bad['error'])
        self.assertEqual(game.blueprints, [])
        good = game.act('make_zone', {'kind': 'office', 'site': 'A1', 'w': 20, 'h': 7})
        self.assertTrue(good['ok'])
        self.assertEqual(good['result']['at'], [30, 40, 10, 20, 7])
        name, blueprint, x, y, z = game.blueprints[0]
        self.assertEqual((name, x, y, z), ('gameapi_zone.csv', 30, 40, 10))
        rows = blueprint.splitlines()[1:]
        self.assertEqual(len(rows), 7)
        self.assertTrue(all(len(row.split(',')) == 20 for row in rows))

    def test_in_range_default_is_unchanged_and_one_axis_keeps_other_default(self):
        game = facts_game(w=3, h=4)
        self.assertEqual(game.act('make_zone', {'kind': 'office', 'site': 'A1'})['result']['at'],
                         [30, 40, 10, 3, 4])
        game = facts_game(w=22, h=4)
        self.assertEqual(game.act('make_zone', {'kind': 'office', 'site': 'A1', 'w': 2})['result']['at'],
                         [30, 40, 10, 2, 4])

    def test_invalid_sizes_remain_rejected_not_coerced(self):
        for axis in ('w', 'h'):
            for value in (0, 21, True, '20', 2.5):
                with self.subTest(axis=axis, value=value):
                    game = facts_game(w=4, h=4)
                    response = game.act('make_zone', {'kind': 'office', 'site': 'A1', axis: value})
                    self.assertFalse(response['ok'])
                    self.assertEqual(game.blueprints, [])

    def test_zone_schema_preserves_future_advertised_dimension_contract(self):
        source = tool_schemas()
        zone = next(t['function'] for t in source if t['function']['name'] == 'make_zone')
        zone['parameters']['properties']['w'] = {'type': 'integer', 'maximum': 15}
        new = next(t['function'] for t in prepare_tools(source) if t['function']['name'] == 'make_zone')
        self.assertEqual(new['parameters']['properties']['w'], {'type': 'integer', 'maximum': 15})

    def test_model_arguments_and_results_pass_through_harness_unchanged(self):
        game = Game([{'ok': True, 'result': {'zone_id': 99, 'at': [30, 40, 10, 20, 7]}}])
        game.task = lambda: {'tools': tool_schemas(), 'task': {'days': 60}}
        args = {'kind': 'office', 'site': 'A1', 'w': 20, 'h': 7}
        requests = []
        def chat(messages, **kwargs):
            requests.append(kwargs['tools'])
            return {'choices': [{'message': {'role': 'assistant', 'content': None,
                                             'tool_calls': [tool('make_zone', args)]}}]}
        model = SimpleNamespace(usage={}, chat=chat)
        task = Task({'version': 'dfbench/v3', 'game': {'url': 'http://game'},
                           'model': {'url': 'http://model', 'name': 'fixed'}, 'seed': 4,
                           'budget': {'credits': 0.5}, 'task': {'days': 60}})
        player = Plain(task, game, model, 4)
        with redirect_stdout(io.StringIO()):
            player.run(max_turns=1)
        self.assertEqual(game.calls, [('make_zone', args)])
        zone = next(t for t in requests[0] if t['function']['name'] == 'make_zone')
        self.assertIn('w', zone['function']['parameters']['properties'])
        reply = json.loads(next(m['content'] for m in player.messages if m['role'] == 'tool'))
        self.assertEqual(reply['result']['at'], [30, 40, 10, 20, 7])
        self.assertEqual(player.stats['actions'], 1)


if __name__ == '__main__':
    unittest.main()
