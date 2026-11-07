import contextlib,io,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.year import YearOverseer
class Game:
 def __init__(self,brew_ok):self.calls=[];self.brew_ok=brew_ok
 def act(self,t,a):
  self.calls.append((t,a))
  ok=self.brew_ok if a.get("recipe")=="brew_drink" else True
  return {"ok":ok,"result":{"order_id":len(self.calls)}}
class YearGate(unittest.TestCase):
 def run_policy(self,brew_ok):
  g=Game(brew_ok);o=YearOverseer(g,days=336)
  o.load({"day":0,"tick":0,"observation":{"administrators":{"citizens":7},"stocks":{"food_edible":60,"logs_usable":100}}});o.count=0
  with contextlib.redirect_stdout(io.StringIO()):o.supply();o.supply()
  return g,o
 def test_stale_observation_creates_only_one_high_cap_brew_order(self):
  g,o=self.run_policy(True);a=[a for t,a in g.calls if a.get("recipe")=="brew_drink"]
  self.assertEqual(len(a),1);self.assertIn({"stock":"drink","below":600},a[0]["when"]);self.assertIn(1,o.owned)
 def test_failed_high_cap_attempt_does_not_fall_back_to_second_order(self):
  g,o=self.run_policy(False);a=[a for t,a in g.calls if a.get("recipe")=="brew_drink"]
  self.assertEqual(len(a),1);self.assertEqual(o.tries["o_brew"],1);self.assertNotIn(1,o.owned)
if __name__=="__main__":unittest.main()
