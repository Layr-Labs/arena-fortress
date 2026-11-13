"""Role transitions must close into safe executable dining/farm actions."""
import contextlib
import copy
import io
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overseer import harness


def room(n, x, z, **kw):
    return dict(id='R'+str(n), kind='R', x=x, y=97, z=z, w=3, h=3,
                soil=True, free=True, dug=False, **kw)


class API:
    def __init__(self): self.calls = []; self.fail = False
    def act(self, tool, args):
        self.calls.append((tool, copy.deepcopy(args)))
        return dict(ok=not self.fail, result={})


class TransitionClosure(unittest.TestCase):
    def setUp(self):
        self.sink = contextlib.redirect_stdout(io.StringIO())
        self.sink.__enter__(); self.addCleanup(self.sink.__exit__, None, None, None)
        self.api = API(); self.o = harness.Overseer(self.api, goal='migrant', days=60)
        self.o.count = 0
        self.o.load(dict(day=1, tick=1200, observation=dict(
            administrators=dict(citizens=40), farm_plots=[dict(id=4), dict(id=5)],
            map=dict(surface_z=78, sites=[room(2,95,77), room(3,91,77),
                room(4,95,76),room(5,91,76),room(6,95,75),room(7,91,75)]))))
        self.o.roles = dict(R1='office')

    def test_last_slot_reserved_and_disjoint_lower_farm_admitted(self):
        self.o.digging()
        self.assertEqual(self.o.roles['R2'], 'farm')
        self.assertEqual(self.o.roles['R3'], 'dine')
        self.assertEqual(self.o.roles['R4'], 'dorm')
        self.assertEqual(self.o.roles['R5'], 'farm')
        self.assertEqual(self.o.room_reservations['R3']['w'], 3)
        a = next(a for t,a in self.api.calls if a.get('site') == 'R5')
        self.assertEqual(a, dict(site='R5'))

    def test_failed_dining_dig_is_not_a_committed_role(self):
        self.o.roles['R2'] = 'farm'
        self.api.fail = True
        self.o.digging()
        self.assertNotIn('R3',self.o.roles)
        self.assertNotIn('R3',self.o.room_reservations)

    def test_only_housing_slot_not_stolen(self):
        self.o.sites = [room(3,91,77)]
        self.assertFalse(self.o.last_dining_slot(self.o.sites[0]))

    def test_exact_farm_overlap_rejected(self):
        self.o.roles.update(R2='dine',R4='dorm')
        self.o.room_reservations['R4'] = dict(x=90,y=97,z=76,w=10,h=7)
        self.o.digging()
        self.assertNotIn('R5',self.o.roles)

    def test_exact_dining_precedes_broad_protected_area(self):
        self.o.roles = dict(R3='dine')
        r = room(3,91,77);r['dug'] = True
        self.o.sites = [dict(id='A1',kind='A',x=90,y=97,z=77,w=30,h=3,open_tiles=70),r]
        self.o.o['farm_plots'] = [dict(x=105,y=97,z=77,w=3,h=3)]
        self.assertEqual(self.o.room_for('dine')['id'],'R3')

    def test_small_room_reserves_equal_pair_capacity(self):
        r=room(3,91,77);r['dug']=True
        self.o.roles = dict(R3='dine');self.o.sites = [r]
        self.o.room_for = lambda role: r if role=='dine' else None
        self.o.free = dict(table=30,chair=30)
        self.o.placed = dict(table=20,chair=20)
        self.o.needs_zone = lambda *args: False
        self.o.furnish()
        placements = [a for t,a in self.api.calls if t=='place_furniture']
        self.assertEqual([(a['kind'],a['count']) for a in placements], [('table',4),('chair',4)])
        self.o.o['furniture']=[dict(kind='table',x=91+i%3,y=97+i//3,z=77) for i in range(4)]
        self.api.calls.clear();self.o.now += harness.DAY
        self.o.furnish()
        self.assertEqual([(a['kind'],a['count']) for t,a in self.api.calls if t=='place_furniture'], [('chair',4)])


if __name__ == '__main__': unittest.main()
