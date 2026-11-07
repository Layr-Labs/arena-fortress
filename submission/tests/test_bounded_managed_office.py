"""A known real chair or a same-footprint placement is required before assigning a new office."""
import io
import sys
import unittest
from pathlib import Path
from contextlib import redirect_stdout
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer
class Game:
    def __init__(self,fail=None):self.calls=[];self.fail=fail
    def act(self,t,a):
        self.calls.append((t,dict(a)))
        return {'ok':t!=self.fail,'result':{'zone_id':70,'at':[104,99,107]}}
class BoundedOffice(unittest.TestCase):
    def agent(self,chair=True,free=0,tiny=False,ready=False,fail=None):
        g=Game(fail);o=Overseer(g);o.load({'tick':0,'hands_off_in_days':30,'observation':{
            'administrators':{'citizens':44,'manager_active_for_orders':True,'MANAGER_id':77,'manager_office':{'chair':True,'zone_id':6} if ready else 'none'},
            'stocks':{'furniture_free':{'chair':free}},
            'furniture':[{'kind':'chair','built':True,'x':104,'y':99,'z':107}] if chair else [],
            'map':{'sites':[{'id':'A1','kind':'A','x':90,'y':90,'z':107,'w':1 if tiny else 37,'h':1 if tiny else 21,'open_tiles':1 if tiny else 22}]}}});o.count=0;return g,o
    def run_office(self,o):
        with redirect_stdout(io.StringIO()):o.office()
    def test_existing_chair_gets_a_bounded_office_and_assignment(self):
        g,o=self.agent();self.run_office(o)
        self.assertEqual(g.calls,[('make_zone',{'kind':'office','site':'A1','w':20,'h':20}),('assign_zone',{'zone_id':70,'dwarf_id':77})])
    def test_free_chair_uses_exact_zone_footprint(self):
        g,o=self.agent(chair=False,free=1);self.run_office(o)
        self.assertEqual(g.calls[1],('place_furniture',{'kind':'chair','count':1,'site':'A1','w':20,'h':20}))
        self.assertEqual(g.calls[-1][0],'assign_zone')
    def test_tiny_stair_area_does_not_get_an_office(self):
        g,o=self.agent(chair=False,free=1,tiny=True);self.run_office(o);self.assertEqual(g.calls,[])
    def test_existing_ready_office_is_retained(self):
        g,o=self.agent(ready=True);self.run_office(o);self.assertEqual(g.calls,[])
    def test_failed_chair_is_not_assigned_as_a_ready_new_office(self):
        g,o=self.agent(chair=False,free=1,fail='place_furniture');self.run_office(o)
        self.assertFalse(any(t=='assign_zone' for t,a in g.calls))
    def test_failed_zone_has_no_chair_or_assignment_side_effect(self):
        g,o=self.agent(fail='make_zone');self.run_office(o)
        self.assertEqual([t for t,a in g.calls],['make_zone'])
if __name__=='__main__':unittest.main()
