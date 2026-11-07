import copy,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from collections import defaultdict
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from plain.harness import Plain
class OwnedDailyDuplicates(unittest.TestCase):
 def make(self):
  f=json.loads((Path(__file__).parent/'fixtures/public-owned-daily-orders.json').read_text());p=Plain.__new__(Plain);p.guard=SimpleNamespace(orders=f['orders'],owned=set(f['owned_ids']));p.cancelled=[];p.added={};return p,f['tick']
 def test_captured_owned_basic_daily_recipes_are_protected_even_with_changed_amount(self):
  for recipe in ['brew_drink','cook_meal','make_barrel']:
   p,t=self.make();before=copy.deepcopy(p.guard.orders);r=p.refuse('add_order',{'recipe':recipe,'amount':30,'repeat':'daily'},t);self.assertEqual(r['error_code'],'layer_owned');self.assertEqual(p.guard.orders,before)
 def test_owned_daily_wood_crafts_are_protected(self):
  p,t=self.make();r=p.refuse('add_manager_order',{'job':'MakeCrafts','amount':30,'repeat':'daily','material_category':['wood']},t);self.assertEqual(r['error_code'],'layer_owned')
 def test_oneoff_and_other_frequency_are_left_to_existing_flow(self):
  for repeat in [None,'monthly']:
   p,t=self.make();a={'recipe':'brew_drink','amount':3}
   if repeat:a['repeat']=repeat
   self.assertIsNone(p.refuse('add_order',a,t))
 def test_foreign_orders_are_not_claimed(self):
  p,t=self.make();p.guard.owned.clear();self.assertIsNone(p.refuse('add_order',{'recipe':'brew_drink','amount':3,'repeat':'daily'},t))
 def test_unobserved_owned_ids_and_nondaily_observed_orders_do_not_block(self):
  for state in ['missing','notdaily']:
   p,t=self.make()
   if state=='missing':p.guard.orders=[]
   else:
    for o in p.guard.orders:o['repeat']='monthly'
   self.assertIsNone(p.refuse('add_order',{'recipe':'brew_drink','amount':3,'repeat':'daily'},t))
 def test_distinct_advanced_material_and_reaction_are_allowed(self):
  for change in [{'material':'OAK:WOOD'},{'reaction':'OTHER'},{'material_category':['bone']},{'item_subtype':'OTHER'}]:
   p,t=self.make();a={'job':'MakeCrafts','amount':3,'repeat':'daily','material_category':['wood'],**change};self.assertIsNone(p.refuse('add_manager_order',a,t))
 def test_other_recipe_and_malformed_recipe_do_not_get_misclassified(self):
  for recipe in ['brew_drink_from_fruit',None,{},[]]:
   p,t=self.make();self.assertIsNone(p.refuse('add_order',{'recipe':recipe,'amount':3,'repeat':'daily'},t))
 def test_run_call_refuses_locally_before_any_game_action(self):
  p,t=self.make();p.tick=Mock(return_value=t);p.tool_names={'add_order'};p.stats=defaultdict(int);p.game=SimpleNamespace(act=Mock());p.result=Mock();call={'id':'duplicate','function':{'name':'add_order','arguments':json.dumps({'recipe':'brew_drink','amount':30,'repeat':'daily'})}};self.assertFalse(p.run_call(call));p.game.act.assert_not_called();self.assertEqual(p.result.call_args.args[-1]['error_code'],'layer_owned');self.assertEqual(p.stats['churn_refused'],1)
 def test_intentional_explicitly_bounded_requests_remain_available(self):
  for name,args in [('add_order',{'recipe':'brew_drink','amount':8,'repeat':'daily','when':[{'stock':'drink','below':900}]}),('add_manager_order',{'job':'MakeCrafts','amount':6,'repeat':'daily','material_category':['wood'],'when':[{'item_type':'WOOD','at_least':40}]})]:
   p,t=self.make();self.assertIsNone(p.refuse(name,args,t))
if __name__=='__main__':unittest.main()
