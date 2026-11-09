import unittest,io
from contextlib import redirect_stdout
from overseer.harness import Overseer
class Game:
    def __init__(self):self.calls=[]
    def act(self,tool,args):self.calls.append((tool,args));return {'ok':True,'result':{'order_id':len(self.calls)}}
class HandoverTiers(unittest.TestCase):
    def make(self,days=216,goal='',window=None):
        g=Game();a=Overseer(g,days=days,goal=goal);a.count=0
        r={'day':days-64,'days_left':64,'tick':100000,'observation':{'administrators':{'citizens':20},'stocks':{'food_edible':1000,'drink':400},'orders':[]}}
        if window is not None:r['hands_off_in_days']=window
        a.load(r);return g,a
    def closer(self,a):
        with redirect_stdout(io.StringIO()):a.endgame_supply()
    def brew(self,g):return [args for tool,args in g.calls if tool=='add_order' and args.get('recipe')=='brew_drink']
    def test_handover_has_emergency_year_and_surplus_gates(self):
        g,a=self.make();self.closer(a);orders=self.brew(g);self.assertEqual(len(orders),3)
        self.assertIn({'stock':'drink','below':240},orders[0]['when']);self.assertIn({'stock':'plants_brewable','at_least':2},orders[0]['when'])
        self.assertIn({'stock':'drink','below':400},orders[1]['when']);self.assertIn({'stock':'food_edible','at_least':160},orders[1]['when'])
        self.assertIn({'stock':'drink','below':600},orders[2]['when']);self.assertIn({'stock':'food_edible','at_least':240},orders[2]['when'])
    def test_scope_is_half_year_nonwindow_nonmigrant_not_drink_growth(self):
        for kwargs in [{'days':60},{'days':167},{'days':336},{'goal':'migrant surge'},{'window':10},{'goal':'drink must not end lower'}]:
            with self.subTest(kwargs=kwargs):
                g,a=self.make(**kwargs);self.assertFalse(a.balanced_handover())
    def test_short_lab_keeps_legacy_plant_reserve(self):
        g,a=self.make(days=60);self.closer(a);orders=self.brew(g);self.assertEqual(len(orders),1);self.assertIn({'stock':'plants_brewable','at_least':20},orders[0]['when']);self.assertFalse(any(c.get('stock')=='food_edible' for c in orders[0]['when']))
    def test_full_year_keeps_existing_emergency_and_high_gate(self):
        g,a=self.make(days=336);self.closer(a);orders=self.brew(g);self.assertEqual(len(orders),2);self.assertIn({'stock':'food_edible','at_least':240},orders[1]['when']);self.assertFalse(any({'stock':'drink','below':400} in q['when'] for q in orders))
    def test_normal300_bank_and_foreign_orders_are_not_canceled(self):
        g,a=self.make();a.orders=[{'id':99,'recipe':'something_else'}]
        with redirect_stdout(io.StringIO()):a.supply();a.endgame_supply()
        orders=self.brew(g);self.assertIn({'stock':'drink','below':300},orders[0]['when']);self.assertIn({'stock':'plants_brewable','at_least':2},orders[0]['when']);self.assertFalse(any(tool=='cancel_order' for tool,_ in g.calls))
    def test_each_tier_fits_native_three_condition_limit(self):
        g,a=self.make();self.closer(a)
        for q in self.brew(g):self.assertEqual(len(q['when']),3);self.assertEqual(q['repeat'],'daily');self.assertEqual(q['amount'],4);self.assertIn({'stock':'barrels_empty','at_least':1},q['when'])
    def test_successful_closer_tiers_are_not_readded(self):
        g,a=self.make();self.closer(a);n=len(self.brew(g));self.closer(a);self.assertEqual(len(self.brew(g)),n)
