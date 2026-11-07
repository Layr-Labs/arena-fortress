import contextlib,io,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path.cwd()))
from overseer.year import YearOverseer as Overseer
from gameapi.facts.tools import order_spec
class Game:
 def __init__(self):self.calls=[]
 def act(self,t,a):self.calls.append((t,a));return {"ok":True,"result":{"order_id":len(self.calls)}}
class YearBrewTests(unittest.TestCase):
 def policy(self,days,cit):
  g=Game();o=Overseer(g,days=days);o.load({"day":93,"tick":111600,"observation":{"administrators":{"citizens":cit},"stocks":{"drink":316,"plants_brewable":10,"logs_usable":200}}});o.count=0
  with contextlib.redirect_stdout(io.StringIO()):o.supply()
  return next(a for t,a in g.calls if a.get("recipe")=="brew_drink")
 def test_year_order_accepts_actual_converter_and_retains_input_guards(self):
  a=self.policy(336,7);order_spec(a);self.assertIn({"stock":"drink","below":600},a["when"]);self.assertIn({"stock":"plants_brewable","at_least":2},a["when"]);self.assertIn({"stock":"barrels_empty","at_least":1},a["when"]);self.assertEqual(a["amount"],3)
 def test_large_year_scales_reserve(self):
  self.assertIn({"stock":"drink","below":1500},self.policy(336,50)["when"])
 def test_midyear_and_lab_keep_inherited_cap(self):
  for days in (216,90,60):
   self.assertIn({"stock":"drink","below":300},self.policy(days,45)["when"])
if __name__=="__main__":unittest.main()
