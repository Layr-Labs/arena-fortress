"""Reuse only a previously observed manager office during an actual managed replacement."""
import io
import sys
import unittest
from pathlib import Path
from contextlib import redirect_stdout
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer
class Game:
    def __init__(self):self.calls=[];self.ok=True
    def act(self,t,a):self.calls.append((t,dict(a)));return {'ok':self.ok}
class Handoff(unittest.TestCase):
    def facts(self,mgr,mo,owner=94,chair=True,left=14):
        return {'tick':30000,'hands_off_in_days':left,'observation':{
            'administrators':{'citizens':44,'manager_active_for_orders':True,'MANAGER_id':mgr,'manager_office':mo},
            'zones':[{'id':6,'type':'Office','owner':owner,'furniture':{'chair':int(chair)}}]}}
    def setup_agent(self):
        g=Game();o=Overseer(g);o.load(self.facts(94,{'chair':True,'zone_id':6}));o.count=0;o.office();return g,o
    def invoke(self,o,r):
        o.load(r)
        with redirect_stdout(io.StringIO()):o.office()
    def test_previous_manager_office_transfers_to_replacement(self):
        g,o=self.setup_agent();self.invoke(o,self.facts(95,'none'))
        self.assertEqual(g.calls,[('assign_zone',{'zone_id':6,'dwarf_id':95})])
        self.assertEqual(o.previous_manager_office,(6,95))
    def test_other_owner_is_not_dispossessed(self):
        g,o=self.setup_agent();self.invoke(o,self.facts(95,'none',owner=96));self.assertEqual(g.calls,[])
    def test_missing_chair_does_not_transfer(self):
        g,o=self.setup_agent();self.invoke(o,self.facts(95,'none',chair=False));self.assertEqual(g.calls,[])
    def test_long_game_keeps_original_office_policy(self):
        g,o=self.setup_agent();self.invoke(o,self.facts(95,'none',left=None));self.assertEqual(g.calls,[])
    def test_no_recorded_former_manager_means_no_transfer(self):
        g=Game();o=Overseer(g);o.count=0;self.invoke(o,self.facts(95,'none'));self.assertEqual(g.calls,[])
    def test_failed_transfer_keeps_recorded_owner(self):
        g,o=self.setup_agent();g.ok=False;self.invoke(o,self.facts(95,'none'))
        self.assertEqual(o.previous_manager_office,(6,94))
if __name__=='__main__':unittest.main()
