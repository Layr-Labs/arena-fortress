"""Decision checks only; native food preservation remains to be measured."""
import sys,unittest,io
from pathlib import Path
from contextlib import redirect_stdout
p=Path(__file__).resolve().parents[1];sys.path.insert(0,str(p))
from overseer.harness import Overseer,DAY
assert Path(sys.modules[Overseer.__module__].__file__).is_relative_to(p)
class Game:
 def __init__(self):self.calls=[]
 def act(self,t,a):self.calls.append((t,a));return {'ok':True,'result':{'order_id':len(self.calls)}}
class FishCook(unittest.TestCase):
 def run_guard(self,days=336,goal='',hands_off=None):
  game=Game();g=Overseer(game,days=days,goal=goal);g.count=0
  g.load({'day':50,'tick':50*DAY,'days_left':days-50,'hands_off_in_days':hands_off,'observation':{'administrators':{'citizens':7},'stocks':{'food_edible':60,'logs_usable':3}}})
  with redirect_stdout(io.StringIO()):g.supply()
  return g,game
 def fish_orders(self,game):return [a for t,a in game.calls if a.get('job')=='PrepareMeal']
 def test_long_fort_has_fish_condition_without_plant_requirement(self):
  _,game=self.run_guard();orders=self.fish_orders(game);self.assertEqual(len(orders),1)
  a=orders[0];self.assertEqual(a['amount'],2);self.assertEqual(a['repeat'],'daily')
  self.assertEqual(a['when'][0],{'item_type':'FISH','flags':['unrotten','cookable'],'at_least':2})
  self.assertEqual(a['when'][1],{'item_type':'FOOD','flags':['unrotten'],'below':200})
 def test_short_tasks_keep_existing_orders(self):
  _,game=self.run_guard(days=120);self.assertEqual(self.fish_orders(game),[])
 def test_ordinary_midyear_handover_gets_fish_order(self):
  _,game=self.run_guard(days=216);self.assertEqual(len(self.fish_orders(game)),1)
 def test_handover_length_with_hands_off_is_not_extended(self):
  _,game=self.run_guard(days=216,hands_off=30);self.assertEqual(self.fish_orders(game),[])
 def test_migrant_task_keeps_existing_orders(self):
  _,game=self.run_guard(goal='Migrant wave');self.assertEqual(self.fish_orders(game),[])
 def test_standing_order_not_duplicated_even_when_observation_is_stale(self):
  g,game=self.run_guard();g.now+=4*DAY
  with redirect_stdout(io.StringIO()):g.supply()
  self.assertEqual(len(self.fish_orders(game)),1)
if __name__=='__main__':unittest.main()
