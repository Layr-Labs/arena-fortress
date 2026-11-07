"""Replay the public full-year chairless-office geometry before population requires validation."""
import contextlib, copy, io, json, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer, covers
class Game:
    def __init__(self): self.calls=[]
    def act(self,t,a):
        self.calls.append((t,copy.deepcopy(a)))
        return {"ok": True, "result": {"zone_id":900}}
class OpenOffice(unittest.TestCase):
    def setup_agent(self):
        self.resp=json.loads((Path(__file__).parent/'fixtures/public-op1-chairless-office.json').read_text())
        self.g=Game();self.o=Overseer(self.g);self.o.load(self.resp);self.o.count=0
    def run_office(self):
        with contextlib.redirect_stdout(io.StringIO()): self.o.office()
    def test_public_wrong_level_office_is_replaced_on_a_known_chair(self):
        self.setup_agent(); before=copy.deepcopy(self.resp);self.run_office()
        zone=next(a for t,a in self.g.calls if t=='make_zone');site=next(s for s in self.o.sites if s['id']==zone['site'])
        box={**site,**zone}
        self.assertTrue(any(f.get('built') is True and f.get('kind')=='chair' and covers(box,f) for f in self.o.o['furniture']))
        self.assertLessEqual(zone['w'],20);self.assertLessEqual(zone['h'],20)
        self.assertEqual(self.g.calls[-1],('assign_zone',{'zone_id':900,'dwarf_id':self.o.adm['MANAGER_id']}))
        self.assertFalse(any(t=='place_furniture' for t,a in self.g.calls));self.assertEqual(self.resp,before)
    def test_ready_office_never_moves(self):
        self.setup_agent();self.o.adm['manager_office']['chair']=True;self.run_office();self.assertEqual(self.g.calls,[])
    def test_another_owned_chaired_office_avoids_churn(self):
        self.setup_agent();f=next(f for f in self.o.o['furniture'] if f['kind']=='chair');self.o.zones.append({'id':901,'owner':self.o.adm['MANAGER_id'],'type':'Office','x':f['x'],'y':f['y'],'z':f['z'],'w':1,'h':1})
        self.run_office();self.assertEqual(self.g.calls,[])
if __name__=='__main__':unittest.main()
