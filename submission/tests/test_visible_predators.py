"""Bounded wildlife decision tests; not a native survival result."""
import sys,io,unittest
from pathlib import Path
from contextlib import redirect_stdout
from types import SimpleNamespace
p=Path(__file__).resolve().parents[1];sys.path.insert(0,str(p))
from overseer.harness import Overseer
from plain.harness import Plain
assert Path(sys.modules[Overseer.__module__].__file__).is_relative_to(p)
class Game:
 def __init__(self,others):self.others=others;self.queries=[];self.fail=False
 def query(self,name,**params):
  self.queries.append((name,params))
  if self.fail:raise RuntimeError('read failed')
  return {'result':{'units':self.others}}
class Predator(unittest.TestCase):
 def guard(self,others=None,day=0,days=336,goal='',food=60,drink=60,plugin=None):
  game=Game(others if others is not None else [{'id':12,'race':'ALLIGATOR','hostile':False,'x':50,'y':50,'z':20}]);g=Overseer(game,days=days,goal=goal)
  g.load({'day':day,'days_left':days-day,'observation':{'administrators':{'citizens':7},'stocks':{'food_edible':food,'drink':drink},'plugins':{'autochop':plugin}}});return g,game
 def scan(self,g):
  with redirect_stdout(io.StringIO()):g.scan_logging_risk()
 def test_nonhostile_visible_alligator_holds_initial_logging(self):
  g,game=self.guard();self.scan(g);self.assertTrue(g.logging_hold);self.assertEqual(game.queries,[('units',{'kind':'others','limit':300})])
 def test_harmless_visible_animals_do_not_hold_logging(self):
  g,_=self.guard([{'race':'OPOSSUM'},{'race':'BIRD_KESTREL'}]);self.scan(g);self.assertFalse(g.logging_hold)
 def test_migrant_short_and_already_enabled_cases_never_query(self):
  for kwargs in [{'goal':'migrant wave'},{'days':216},{'plugin':'on'}]:
   g,game=self.guard(**kwargs);self.scan(g);self.assertFalse(g.logging_hold);self.assertEqual(game.queries,[])
 def test_day56_and_low_supplies_release_hold(self):
  for kwargs in [{'day':56},{'food':13},{'drink':27}]:
   g,game=self.guard(**kwargs);g.logging_hold=True;self.scan(g);self.assertFalse(g.logging_hold);self.assertEqual(game.queries,[])
 def test_initial_scan_reused_same_day_then_clear_when_predator_leaves(self):
  g,game=self.guard();self.scan(g);self.scan(g);self.assertEqual(len(game.queries),1)
  game.others=[];g.day=1;self.scan(g);self.assertFalse(g.logging_hold);self.assertEqual(len(game.queries),2)
 def test_read_failure_preserves_game_progress(self):
  g,game=self.guard();g.logging_hold=True;game.fail=True;self.scan(g);self.assertFalse(g.logging_hold)
 def test_model_cannot_enable_logging_during_hold_but_other_automation_remains(self):
  p=Plain.__new__(Plain);p.guard=SimpleNamespace(logging_hold=True,owned=set())
  self.assertEqual(p.refuse('enable_automation',{'name':'autochop'},0)['error_code'],'wildlife_pause')
  self.assertIsNone(p.refuse('enable_automation',{'name':'autofarm'},0))
  p.guard.logging_hold=False;self.assertIsNone(p.refuse('enable_automation',{'name':'autochop'},0))
if __name__=='__main__':unittest.main()
