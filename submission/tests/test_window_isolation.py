import hashlib,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dfbench_client.task import Task
from plain.harness import Plain,overseer_class
from overseer.harness import Overseer
from overseer.year import YearOverseer
from overseer.frontier import Overseer as FrontierOverseer
class WindowIsolation(unittest.TestCase):
 def task(self,days=336,hands=None,**extras):
  return Task({"task":{"days":days,"hands_off":hands,**extras}})
 def test_explicit_window_uses_managed_repairs_at_any_horizon(self):
  for days in (45,60,90,336):
   self.assertIs(overseer_class(self.task(days,{"from_day":days-7,"days":7})),Overseer)
 def test_no_window_uses_original_frontier_at_any_horizon(self):
  for days in (45,60,216,336):
   self.assertIs(overseer_class(self.task(days)),YearOverseer if days >= 336 else FrontierOverseer)
 def test_malformed_or_past_horizon_window_is_conservative(self):
  for h in ({},{"from_day":True,"days":21},{"from_day":39,"days":True},{"from_day":-1,"days":21},{"from_day":60,"days":21},{"from_day":39,"days":0},{"from_day":39,"days":-1},"window",[]):
   self.assertIs(overseer_class(self.task(60,h)),FrontierOverseer)
 def test_plain_constructs_the_selected_controller(self):
  for h,c in ((None,FrontierOverseer),({"from_day":39,"days":21},Overseer)):
   o=Plain(self.task(60,h),object(),object());self.assertIs(type(o.guard),c)
 def test_names_goals_and_unrelated_seed_fields_do_not_select_policy(self):
  for name in ("LT08","OP1","arbitrary"):
   t=self.task(60,None,name=name,goal="migrants",seed=999)
   self.assertIs(overseer_class(t),FrontierOverseer)
 def test_open_controller_is_exact_published_fa9_source(self):
  source=(Path(__file__).resolve().parents[1]/"overseer/frontier.py").read_bytes()
  self.assertEqual(hashlib.sha256(source).hexdigest(),"ee13a95e6663fc4b6facc7872b43d7764d1df37c40be540cdb3c7d7b75db3e19")
if __name__=="__main__":unittest.main()
