import sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.year import YearOverseer
from overseer.frontier import Overseer as FrontierOverseer
class LateFood(unittest.TestCase):
 def invoke(self,left,food,days=336):
  o=YearOverseer.__new__(YearOverseer);o.days=days;o.days_left=left;o.st={'food_edible':food};o.cit=20;o.butcher=Mock()
  with patch.object(FrontierOverseer,'endgame_supply',autospec=True) as original:o.endgame_supply();original.assert_called_once_with(o)
  return o.butcher.call_count
 def test_late_low_food_reuses_existing_butcher(self):self.assertEqual(self.invoke(14,100),1)
 def test_outside_late_range_keeps_original_only(self):
  for left in (1,15,60):self.assertEqual(self.invoke(left,100),0)
 def test_ample_food_keeps_original_only(self):self.assertEqual(self.invoke(10,800),0)
 def test_shorter_horizon_keeps_original_only(self):self.assertEqual(self.invoke(10,100,216),0)
