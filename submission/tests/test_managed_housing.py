"""Replay a soil-only managed opening; preserve the existing long-game room policy."""
import sys
import io
import unittest
from pathlib import Path
from contextlib import redirect_stdout
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer
class Game:
    def __init__(self):self.calls=[]
    def act(self,t,a):
        self.calls.append((t,dict(a)))
        return {'ok':True,'result':{}}
class Housing(unittest.TestCase):
    def agent(self,left=20,pop=46):
        g=Game();o=Overseer(g)
        o.load({'tick':0,'hands_off_in_days':left,'observation':{
            'administrators':{'citizens':pop},'farm_plots':[{'id':1},{'id':2}],
            'map':{'sites':[{'kind':'R','id':'R'+str(i),'soil':True,'z':10-i//2,'x':10*i,'y':10,'w':3,'h':3} for i in range(1,7)]}}})
        o.count=0;return g,o
    def test_large_managed_opening_reserves_rooms_after_two_farms(self):
        g,o=self.agent()
        with redirect_stdout(io.StringIO()):o.digging()
        self.assertEqual([o.roles['R'+str(i)] for i in range(1,4)],['dorm','dine','office'])
        self.assertEqual(g.calls[0],('dig_room',{'site':'R1','w':9,'h':7}))
    def test_long_game_and_small_lab_retain_farm_priority(self):
        for left,pop in [(None,46),(20,18),(0,46)]:
            g,o=self.agent(left,pop)
            with redirect_stdout(io.StringIO()):o.digging()
            self.assertEqual(o.roles['R1'],'farm')
            self.assertEqual(o.roles['R2'],'farm')
            if pop >= 25:self.assertEqual(set(o.roles.values()),{'farm'})
    def test_floor_candidate_cannot_steal_housing_level(self):
        g,o=self.agent();o.roles={'R1':'dorm'}
        o.sites += [{'id':'F1','kind':'F','z':10},{'id':'F2','kind':'F','z':8}]
        with redirect_stdout(io.StringIO()):o.farms()
        sites=[a['site'] for t,a in g.calls if t=='build_farm']
        self.assertNotIn('F1',sites);self.assertIn('F2',sites)
if __name__=='__main__':unittest.main()
