import contextlib,copy,io,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));sys.path.insert(0,str(Path.cwd()))
from overseer.harness import Overseer
from gameapi.facts.tools import order_spec
class Game:
 def __init__(self):self.calls=[]
 def act(self,t,a):self.calls.append((t,copy.deepcopy(a)));return {'ok':True,'result':{'order_id':77}}
class CommittedBeds(unittest.TestCase):
 def agent(self):
  r=json.loads((Path(__file__).parent/'fixtures/public-migrant-pending-bed-order.json').read_text());g=Game();o=Overseer(g,goal='Migrants are arriving');o.load(r);o.count=0;return r,g,o
 def supply(self,o):
  with contextlib.redirect_stdout(io.StringIO()):o.supply()
 def beds(self,g):return [a for t,a in g.calls if t=='add_order' and a.get('recipe')=='make_bed']
 def test_public_wave_queues_uncommitted_deficit_before_old_order_finishes(self):
  r,g,o=self.agent();before=copy.deepcopy(r);self.supply(o);self.assertEqual(self.beds(g),[{'recipe':'make_bed','amount':28}]);order_spec(self.beds(g)[0]);self.assertEqual(r,before)
 def test_newly_visible_queue_prevents_duplicate_even_before_validation(self):
  r,g,o=self.agent();o.orders.append({'id':77,'recipe':'make_bed','left':28,'validated':False});self.supply(o);self.assertEqual(self.beds(g),[])
 def test_finished_items_and_in_progress_jobs_are_each_counted_once(self):
  r,g,o=self.agent();o.st['beds']=35
  o.orders=[{'recipe':'make_bed','left':20,'jobs_in_progress':2,'validated':True}];self.supply(o);self.assertEqual(self.beds(g),[])
 def test_later_population_growth_only_adds_the_new_shortage(self):
  r,g,o=self.agent();o.cit=51;o.st['beds']=27;o.orders=[{'recipe':'make_bed','left':28}];self.supply(o);self.assertEqual(self.beds(g),[{'recipe':'make_bed','amount':8}])
 def test_open_run_and_repeat_order_keep_the_original_pending_guard(self):
  for mode in ['open','repeat']:
   r,g,o=self.agent()
   if mode=='open':o.hands_left=None
   else:
    next(q for q in o.orders if q.get('recipe')=='make_bed')['repeat']='daily'
   self.supply(o);self.assertEqual(self.beds(g),[])
 def test_unknown_quantities_do_not_create_speculative_topups(self):
  r,g,o=self.agent();next(q for q in o.orders if q.get('recipe')=='make_bed')['left']=None;self.supply(o);self.assertEqual(self.beds(g),[])
 def test_large_deficit_still_uses_actual_thirty_job_limit(self):
  r,g,o=self.agent();o.cit=500;self.supply(o);a=self.beds(g)[0];order_spec(a);self.assertEqual(a['amount'],30)
 def test_same_observation_cannot_add_a_second_batch_in_same_pass(self):
  r,g,o=self.agent();self.supply(o);self.supply(o);self.assertEqual(len(self.beds(g)),1)
if __name__=='__main__':unittest.main()
