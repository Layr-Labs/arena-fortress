import contextlib,io,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.year import YearOverseer
from overseer.frontier import Overseer as Frontier
class BoundedCrafts(unittest.TestCase):
 def make(self):
  o=YearOverseer.__new__(YearOverseer);o.days=336;o.cit=20;o.o={'wealth':{'created':10000}};o.orders=[{'id':8,'job':'MakeCrafts','repeat':'daily','material_category':['wood']}];o.owned={8};o.done={'o_crafts_prog'};o.act=Mock(return_value={'ok':True});return o
 def test_pauses_owned_order_and_marks_state_only_after_success(self):
  o=self.make();o.progress();self.assertEqual(o.act.call_args.args[:3],('pause_crafts_8','cancel_order',{'order_id':8}));self.assertTrue(o.crafts_paused);self.assertNotIn(8,o.owned)
 def test_external_order_is_untouched(self):
  o=self.make();o.owned=set();o.progress();o.act.assert_not_called();self.assertFalse(getattr(o,'crafts_paused',False))
 def test_failed_cancellation_does_not_pause_or_remove_ownership(self):
  o=self.make();o.act.return_value={'ok':False};o.progress();self.assertIn(8,o.owned);self.assertFalse(getattr(o,'crafts_paused',False))
 def test_below_wealth_threshold_preserves_original_policy(self):
  for cit,wealth in [(19,9999),(20,9999)]:
   o=self.make();o.cit=cit;o.o['wealth']['created']=wealth
   with patch.object(Frontier,'progress') as original:o.progress();original.assert_called_once_with()
   o.act.assert_not_called()
 def test_paused_hysteresis_and_restart_below_rank_requirement(self):
  o=self.make();o.crafts_paused=True;o.o['wealth']['created']=6000
  with patch.object(Frontier,'progress') as original:o.progress();original.assert_not_called()
  o.o['wealth']['created']=4999
  with patch.object(Frontier,'progress') as original:o.progress();original.assert_called_once_with()
  self.assertFalse(o.crafts_paused);self.assertNotIn('o_crafts_prog',o.done)
 def test_short_horizon_is_original(self):
  o=self.make();o.days=216
  with patch.object(Frontier,'progress') as original:o.progress();original.assert_called_once_with()
  o.act.assert_not_called()
 def test_lower_population_also_pauses_after_wealth_goal(self):
  o=self.make();o.cit=19;o.progress();self.assertTrue(o.crafts_paused);self.assertEqual(o.act.call_args.args[1],'cancel_order')
 def test_other_owned_recipe_is_untouched(self):
  o=self.make();o.orders[0]['job']='MakeBarrel';o.progress();o.act.assert_not_called()
if __name__=='__main__':unittest.main()
