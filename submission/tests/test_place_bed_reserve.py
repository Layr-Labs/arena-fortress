"""Decision counterexamples only: no claim about native migration timing."""
import io,sys,unittest
from pathlib import Path
from contextlib import redirect_stdout
p=Path(__file__).resolve().parents[1];sys.path.insert(0,str(p))
from overseer.harness import Overseer,DAY
assert Path(sys.modules[Overseer.__module__].__file__).is_relative_to(p)
class Game:
 def __init__(self):self.calls=[]
 def act(self,tool,args):
  self.calls.append((tool,dict(args)))
  if tool=='place_furniture':
   n=args['count'];return {'ok':True,'result':{'n':n,'at':[[i%20,i//20,9] for i in range(n)]}}
  return {'ok':True,'result':{}}
class PlaceForecastBeds(unittest.TestCase):
 def scenario(self,surge=True,free=38):
  game=Game();g=Overseer(game,goal='Migrants are arriving' if surge else 'Maintain the fort',days=60);g.count=0
  g.load({'day':20,'tick':20*DAY,'hands_off_in_days':19,'observation':{'administrators':{'citizens':19},'stocks':{'furniture_free':{'bed':free}},'furniture':[{'kind':'bed','x':i%20,'y':i//20,'z':9} for i in range(19)]}})
  room={'id':'R1','kind':'R','x':0,'y':0,'z':9,'w':20,'h':20}
  g.room_for=lambda role:room
  g.dining_sites=lambda preferred:[]
  g.needs_zone=lambda *a:False
  return g,game
 def placed(self,game):return sum(a['count'] for t,a in game.calls if t=='place_furniture' and a.get('kind')=='bed')
 def run_furnish(self,g):
  with redirect_stdout(io.StringIO()):g.furnish()
 def test_stocked_beds_are_placed_before_a_later_wave_can_exceed_two(self):
  g,game=self.scenario();self.run_furnish(g)
  self.assertGreaterEqual(19+self.placed(game),27) # a wave of8 after control ends
  first=self.placed(game);self.assertLessEqual(first,30)
  g.placed['bed']=19+first;g.free['bed']=38-first;g.now+=DAY;g.day+=1;g.count=0
  self.run_furnish(g)
  self.assertGreaterEqual(19+self.placed(game),g.bed_target())
 def test_existing_inventory_bounds_the_reserve_placement(self):
  g,game=self.scenario(free=3);self.run_furnish(g)
  self.assertEqual(self.placed(game),3)
 def test_without_stock_the_policy_does_not_invent_beds(self):
  g,game=self.scenario(free=0);self.run_furnish(g)
  self.assertEqual(self.placed(game),0)
 def test_ordinary_goal_retains_two_bed_placement_buffer(self):
  g,game=self.scenario(surge=False);self.run_furnish(g)
  self.assertEqual(self.placed(game),2)
if __name__=='__main__':unittest.main()
