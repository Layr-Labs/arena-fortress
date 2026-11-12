"""Anticipated migrant beds must be queued before the hands-off deadline."""
import contextlib
import io
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer

class API:
    def __init__(self):self.calls=[]
    def act(self,tool,args):
        self.calls.append((tool,args))
        return {'ok':True,'result':{}}

class Production(unittest.TestCase):
    def layer(self,surge=True,active=True):
        api=API();o=Overseer(api,goal='migrants arriving' if surge else '')
        o.count=0
        o.load({'tick':1200,'observation':{'administrators':{'citizens':36,'manager_active_for_orders':active},
          'stocks':{'logs_usable':100,'beds':19,'tables':30,'chairs':30,'drink':600,'prepared_meals':100},
          'orders':[{'recipe':r,'repeat':'daily','left':1} for r in ['brew_drink','make_barrel','cook_meal']],
          'workshops':[{'type':t,'built':True} for t in ['Carpenters','Kitchen','Still']],
          'map':{'sites':[{'id':'W1','kind':'W'}]}}})
        return o,api
    def test_surge_queues_observed_deficit_up_to_thirty(self):
        o,api=self.layer()
        with contextlib.redirect_stdout(io.StringIO()):o.supply()
        self.assertEqual([a['amount'] for t,a in api.calls if t=='add_order' and a['recipe']=='make_bed'],[29])
    def test_non_surge_retains_small_bed_batch(self):
        o,api=self.layer(surge=False)
        with contextlib.redirect_stdout(io.StringIO()):o.supply()
        self.assertEqual([a['amount'] for t,a in api.calls if t=='add_order' and a['recipe']=='make_bed'],[8])
    def test_existing_pending_beds_do_not_duplicate(self):
        o,api=self.layer();o.orders.append({'recipe':'make_bed','left':20})
        with contextlib.redirect_stdout(io.StringIO()):o.supply()
        self.assertFalse(any(a.get('recipe')=='make_bed' for _,a in api.calls))
    def test_second_carpenter_requires_active_manager(self):
        for active in [False,True]:
            o,api=self.layer(active=active)
            with contextlib.redirect_stdout(io.StringIO()):o.workshops()
            self.assertEqual(sum(t=='build_workshop' and a['type']=='Carpenters' for t,a in api.calls),int(active))
    def test_no_extra_carpenter_outside_migrant_goal(self):
        o,api=self.layer(surge=False)
        with contextlib.redirect_stdout(io.StringIO()):o.workshops()
        self.assertFalse(api.calls)
if __name__=='__main__':unittest.main()

class FurniturePriority(unittest.TestCase):
    def test_migrant_dining_waits_while_beds_are_in_production(self):
        o,api=Production().layer();o.st['tables']=o.st['chairs']=0
        o.orders.append({'recipe':'make_bed','left':20})
        with contextlib.redirect_stdout(io.StringIO()):o.supply()
        self.assertFalse(any(a.get('recipe') in ('make_table','make_chair') for _,a in api.calls))
    def test_sufficient_bed_inventory_allows_dining(self):
        o,api=Production().layer();o.st['beds']=o.bed_target();o.st['tables']=o.st['chairs']=0
        with contextlib.redirect_stdout(io.StringIO()):o.supply()
        self.assertEqual({a.get('recipe') for _,a in api.calls},{'make_table','make_chair'})
