import sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.year import MidyearFoodOverseer,YearOverseer
from overseer.frontier import Overseer as Frontier
from overseer.harness import Overseer as Managed
from plain.harness import overseer_class
from dfbench_client.task import Task
class MidyearLateFood(unittest.TestCase):
 def invoke(self,left,food=69,days=216):
  o=MidyearFoodOverseer.__new__(MidyearFoodOverseer);o.days=days;o.days_left=left;o.st={'food_edible':food};o.cit=17;o.butcher=Mock()
  with patch.object(Frontier,'endgame_supply',autospec=True) as original:o.endgame_supply();original.assert_called_once_with(o)
  return o.butcher.call_count
 def test_public_day206_above_original_four_per_citizen_trigger_gets_late_food(self):self.assertEqual(self.invoke(9,69),1)
 def test_outside_late_range_unknown_clock_and_other_horizons_preserve_original(self):
  for left,days in [(1,216),(15,216),(None,216),(True,216),(10,120),(10,336)]:self.assertEqual(self.invoke(left,69,days),0)
 def test_ample_food_keeps_original_only(self):self.assertEqual(self.invoke(9,680),0)
 def test_router_is_structured_and_window_priority_is_preserved(self):
  for days,expected in [(120,Frontier),(167,Frontier),(168,MidyearFoodOverseer),(216,MidyearFoodOverseer),(335,MidyearFoodOverseer),(336,YearOverseer)]:
   self.assertIs(overseer_class(Task({'task':{'days':days,'hands_off':None,'name':'arbitrary','seed':999}})),expected)
  self.assertIs(overseer_class(Task({'task':{'days':216,'hands_off':{'from_day':195,'days':21}}})),Managed)
if __name__=='__main__':unittest.main()
