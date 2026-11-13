"""Actual OP1 observation regressions plus explicit mutation/cache contracts. No live calls."""
import copy
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from overseer import harness


def observed(day):
    return json.loads((ROOT / 'tests/fixtures' / f'operator-op1-day{day}.json').read_text())


class Game:
    def __init__(self):
        self.actions, self.queries = [], []
        self.fail = set()
        self.query_fail = False

    def act(self, tool, args):
        self.actions.append((tool, copy.deepcopy(args)))
        return {'ok': tool not in self.fail, 'result': {}}

    def query(self, name, **kw):
        self.queries.append((name, kw))
        if self.query_fail:
            return {'ok': False}
        return {'ok': True, 'result': {'x1': 0, 'y1': 0, 'levels': [{'z': 9, 'shape': ['...']}],
                                       'buildings': [], 'liquid': [], 'designations': []}}


class Prerequisites(unittest.TestCase):
    def setUp(self):
        self.sink = redirect_stdout(io.StringIO())
        self.sink.__enter__()
        self.addCleanup(self.sink.__exit__, None, None, None)

    def make(self, facts=None):
        g = Game()
        o = harness.Overseer(g, days=336, advisory_sensing=False)
        o.load(copy.deepcopy(facts or observed(1)))
        o.count = 0
        return o, g

    def all_levels(self):
        # The day-5 tape supplies real coordinates/geometry. These deliberate
        # perturbations represent the candidate's earlier unallocated state,
        # NOT an observed game result or action-equivalence claim.
        r = observed(5)
        r['day'], r['tick'] = 2, observed(1)['tick'] + harness.DAY
        o = r['observation']
        o['date']['abs_tick'] = r['tick']
        o['zones'], o['farm_plots'] = [], []
        o['administrators']['manager_office'] = 'none'
        for s in o['map']['sites']:
            if s['kind'] == 'R':
                s.update(designated=False, dug=False, free=True)
                s.pop('used_by', None)
        return r

    def test_actual_day_one_never_zones_stair_office(self):
        o, g = self.make()
        o.office()
        self.assertEqual([a for t, a in g.actions if t == 'make_zone'], [])

    def test_actual_two_level_start_digs_before_hidden_third_level(self):
        o, g = self.make()
        o.digging()
        self.assertEqual(set(o.layout), {'office', 'dine'})
        self.assertEqual(set(o.roles.values()), {'office', 'dine'})
        self.assertEqual(o.layout['dine']['z'], o.surface - 1)
        r = self.all_levels()
        for role in ('office', 'dine'):
            for site in r['observation']['map']['sites']:
                if site['id'] == o.layout[role]['id']:
                    site.update(designated=True, dug=True)
        o.load(r)
        o.digging()
        self.assertIn('dorm', o.roles.values())

    def test_partial_layout_can_extend_an_unreached_third_level(self):
        o, g = self.make()
        o.digging()
        self.assertEqual(set(o.layout), {'office', 'dine'})
        first = sum(t == 'dig_stairs' for t, a in g.actions)
        self.assertEqual(first, 1)
        o.now += 12 * harness.DAY
        o.digging()
        self.assertEqual(sum(t == 'dig_stairs' for t, a in g.actions), first + 1)

    def test_three_level_geometry_reserves_housing_before_farms(self):
        o, g = self.make(self.all_levels())
        o.digging()
        self.assertIn('dorm', o.roles.values())
        self.assertIn('dine', o.roles.values())
        self.assertIn('office', o.roles.values())
        living = {role: o.room_reservations[rid] for rid, role in o.roles.items() if role in {'office', 'dorm', 'dine'}}
        self.assertEqual(living['dine']['z'], o.surface - 1)
        self.assertEqual(len({v['z'] for v in living.values()}), 3)
        for rid, role in o.roles.items():
            if role == 'farm':
                s = next(s for s in o.sites if s['id'] == rid)
                self.assertNotIn(s['z'], {living['dorm']['z'], living['dine']['z']})
                self.assertFalse(harness.overlaps(s, living['office']))

    def test_failed_dig_retains_intent_but_not_accepted_role(self):
        o, g = self.make(self.all_levels())
        g.fail.add('dig_room')
        o.digging()
        self.assertEqual(o.roles, {})
        self.assertTrue(o.layout)
        g.fail.clear()
        o.now += 3 * harness.DAY
        o.digging()
        self.assertIn('dorm', o.roles.values())

    def test_whole_level_handle_furnishes_expansion_not_only_nine_tile_room(self):
        o, g = self.make(self.all_levels())
        o.digging()
        self.assertTrue(getattr(o, 'layout', None))
        for role in ['dorm', 'dine']:
            box = o.layout[role]
            area = {**box, 'id': 'A_test_' + role, 'kind': 'A', 'open_tiles': box['w'] * box['h'], 'free': True}
            o.sites.append(area)
            self.assertEqual(o.room_for(role)['id'], area['id'])

    def test_active_farm_never_silently_reassigned(self):
        r = self.all_levels()
        room = next(s for s in r['observation']['map']['sites'] if s['kind'] == 'R')
        r['observation']['farm_plots'] = [{**room, 'id': 999, 'built': True}]
        o, g = self.make(r)
        o.digging()
        for rid, role in o.roles.items():
            if role in {'dorm', 'dine', 'office'}:
                self.assertFalse(harness.overlaps(o.room_reservations[rid], room))

    def test_discovered_farm_site_cannot_take_living_level(self):
        o, g = self.make(self.all_levels())
        o.digging()
        for role in ['dorm', 'dine']:
            box = o.layout[role]
            o.sites.append({**box, 'id': 'F_' + role, 'kind': 'F', 'x': box['x'] + 20, 'w': 3, 'h': 3})
        g.actions.clear()
        o.farms()
        bad = {a['site'] for t, a in g.actions if t == 'build_farm'}
        self.assertFalse(bad & {'F_dorm', 'F_dine'})

    def test_same_observation_map_reads_are_reused_defensively(self):
        o, g = self.make()
        a = o.q('map', x=1, y=1, z=9, radius=3)
        a['levels'].clear()
        b = o.q('map', radius=3, z=9, y=1, x=1)
        self.assertTrue(b['levels'])
        self.assertEqual(len(g.queries), 1)

    def test_map_cache_invalidated_by_action_and_fresh_observation(self):
        o, g = self.make()
        kw = dict(x=1, y=1, z=9, radius=3)
        o.q('map', **kw)
        o.act('order', 'add_order', {'recipe': 'make_bed', 'amount': 1})
        o.q('map', **kw)
        o.load(observed(1))  # even an identical tick is a new observation
        o.q('map', **kw)
        self.assertEqual(len(g.queries), 3)

    def test_failed_query_is_never_cached(self):
        o, g = self.make()
        g.query_fail = True
        o.q('map', x=1)
        g.query_fail = False
        self.assertIsNotNone(o.q('map', x=1))
        self.assertEqual(len(g.queries), 2)


if __name__ == '__main__':
    unittest.main()
