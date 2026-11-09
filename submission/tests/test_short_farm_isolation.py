"""Prevent a housing level reservation from making a short rescue's crop rooms unusable."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
VARIANT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(VARIANT))
from overseer.harness import Overseer
from test_room_zones import FakeGame, facts, site

class FarmIsolation(unittest.TestCase):
    def setUp(self):
        capture=redirect_stdout(io.StringIO());capture.__enter__();self.addCleanup(capture.__exit__,None,None,None)
        self.game=FakeGame();self.guard=Overseer(self.game,days=90)
        self.rooms=[site('R1',z=9,soil=True),site('R2',z=9,soil=False),
                    site('R3',z=8,soil=True),site('R4',z=8,soil=True),
                    site('R5',z=7,soil=False),site('R6',z=7,soil=False),site('R7',z=6,soil=False)]
        self.guard.load(facts(self.rooms));self.guard.count=0
    def test_two_crop_levels_survive_housing_allocation(self):
        self.guard.digging()
        self.assertEqual(self.guard.roles,{'R1':'farm','R3':'farm','R5':'dorm','R6':'dine','R7':'office'})
        self.assertFalse(any(args['site'] in ['R2','R4'] for tool,args in self.game.calls))
    def test_short_migrant_layout_retains_earlier_policy(self):
        self.guard.surge=True;self.guard.digging()
        self.assertEqual(self.guard.roles['R2'],'dorm')
        self.assertEqual(self.guard.roles['R4'],'dine')
    def test_full_year_layout_retains_earlier_policy(self):
        self.guard.days=336;self.guard.digging()
        self.assertEqual(self.guard.roles['R2'],'dorm')
    def test_refused_farm_dig_does_not_reserve_the_level(self):
        original=self.game.act
        def act(tool,args):
            if args.get('site')=='R1':return {'ok':False,'error_code':'not_diggable'}
            return original(tool,args)
        self.game.act=act;self.guard.digging()
        self.assertEqual(self.guard.roles['R2'],'dorm')
        self.assertNotIn('R1',self.guard.roles)
    def test_existing_farm_reservation_blocks_same_level_housing(self):
        self.guard.roles['R1']='farm';self.guard.digging()
        self.assertNotIn('R2',self.guard.roles)
    def test_single_crop_level_does_not_force_housing_into_it(self):
        self.guard.load(facts(self.rooms[:2]));self.guard.digging()
        self.assertEqual(self.guard.roles,{'R1':'farm'})

if __name__=='__main__':unittest.main()
