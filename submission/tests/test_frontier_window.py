import contextlib,io,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path.cwd()))
from overseer.harness import Overseer
from gameapi.facts.tools import order_spec
class Game:
 def __init__(self):self.calls=[]
 def act(self,t,a):self.calls.append((t,a));return {'ok':True,'result':{'order_id':len(self.calls)}}
class WindowTests(unittest.TestCase):
 def run_policy(self,pop):
  g=Game();o=Overseer(g);o.load({'day':25,'tick':30000,'hands_off_in_days':14,'observation':{'administrators':{'citizens':pop},'stocks':{'food_edible':1000}}});o.count=0
  with contextlib.redirect_stdout(io.StringIO()):o.window_supply();o.window_supply()
  return g,o
 def test_managed_order_is_once_protected_and_actual_converter_accepts_it(self):
  g,o=self.run_policy(45);orders=[a for t,a in g.calls if a.get('recipe')=='brew_drink'];self.assertEqual(len(orders),1);a=orders[0];order_spec(a);self.assertEqual(a['amount'],4);self.assertIn({'stock':'plants_brewable','at_least':2},a['when']);self.assertIn({'stock':'drink','below':1440},a['when']);self.assertEqual(o.brew_orders,{1});self.assertIn(1,o.owned)
 def test_smaller_lab_keeps_frontier_parameters(self):
  g,o=self.run_policy(18);a=next(a for t,a in g.calls if a.get('recipe')=='brew_drink');self.assertEqual(a['amount'],5);self.assertIn({'stock':'plants_brewable','at_least':9},a['when']);self.assertIn({'stock':'drink','below':2000},a['when'])
if __name__=='__main__':unittest.main()
