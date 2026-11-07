"""Keep large managed bed production separate from the inherited long-game policy."""
import io
import sys
import unittest
from pathlib import Path
from contextlib import redirect_stdout
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer
class Game:
    def __init__(self):self.calls=[]
    def act(self,t,a):self.calls.append((t,dict(a)));return {'ok':True,'result':{}}
class Production(unittest.TestCase):
    def agent(self,left=30,pop=46,carp=1,logs=20,chair=1):
        g=Game();o=Overseer(g);o.load({'tick':0,'hands_off_in_days':left,'observation':{
            'administrators':{'citizens':pop},'stocks':{'logs_usable':logs,'beds':8,'chairs':chair,'tables':1},
            'orders':[{'recipe':r,'repeat':'daily'} for r in ('brew_drink','cook_meal','make_barrel')],
            'workshops':[{'type':t} for t in ['Carpenters']*carp+['Still','Kitchen']],
            'map':{'sites':[{'id':'W1','kind':'W'}]}}});o.count=0;return g,o
    def supply(self,o):
        with redirect_stdout(io.StringIO()):o.supply()
    def test_managed_beds_receive_larger_batch_without_replacement_seats(self):
        g,o=self.agent();self.supply(o)
        self.assertEqual(g.calls,[('add_order',{'recipe':'make_bed','amount':30})])
    def test_long_game_keeps_three_eight_item_batches(self):
        g,o=self.agent(left=None);self.supply(o)
        self.assertEqual([a['amount'] for t,a in g.calls],[8,8,8])
    def test_first_chair_still_ordered_for_office(self):
        g,o=self.agent(chair=0);self.supply(o)
        self.assertIn(('add_order',{'recipe':'make_chair','amount':8}),g.calls)
    def test_frontier_closer_remains_the_only_second_carpenter_path(self):
        for surge,pop,carp,logs,expected in [(True,46,1,20,1),(False,46,1,20,0),(True,14,1,20,0),(True,24,1,20,1),(True,46,2,20,0),(True,46,1,4,0)]:
            g,o=self.agent(30,pop,carp,logs);o.surge=surge
            with redirect_stdout(io.StringIO()):
                o.workshops()
                self.assertEqual(g.calls,[])
                o.closer()
            self.assertEqual(len(g.calls),expected)
if __name__=='__main__':unittest.main()
