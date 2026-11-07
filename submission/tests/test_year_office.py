import contextlib,io,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.year import YearOverseer
class G:
 def __init__(self):self.calls=[]
 def act(self,t,a):self.calls.append((t,a));return {'ok':True,'result':{'zone_id':700}}
class YearOffice(unittest.TestCase):
 def make(self):
  g=G();o=YearOverseer(g,days=336);r=json.loads((Path(__file__).parent/'fixtures/year-office-public-failure.json').read_text());o.load(r);o.count=0;return g,o
 def test_captured_required_chairless_office_reuses_actual_chair_floor(self):
  g,o=self.make()
  with contextlib.redirect_stdout(io.StringIO()):o.office()
  self.assertEqual(g.calls[0],('make_zone',{'kind':'office','site':'A6','w':13,'h':7}));self.assertEqual(g.calls[1],('assign_zone',{'zone_id':700,'dwarf_id':86}));self.assertEqual(len(g.calls),2)
 def test_under_twenty_keeps_original_office_policy(self):
  g,o=self.make();o.cit=19
  with contextlib.redirect_stdout(io.StringIO()):o.office()
  self.assertFalse(g.calls)
 def test_healthy_office_is_not_reassigned(self):
  g,o=self.make();o.adm['manager_office']['chair']=True
  with contextlib.redirect_stdout(io.StringIO()):o.office()
  self.assertFalse(g.calls)
if __name__=='__main__':unittest.main()
