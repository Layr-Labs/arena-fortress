"""Five forecast/prequeue cases copied from published 937a7b6c.

Its dining-dig policy is not adopted here, so that separate case is excluded.
"""
import io,unittest
from contextlib import redirect_stdout
from overseer.harness import Overseer
class Game:
    def __init__(self,ok=True):self.calls=[];self.ok=ok
    def act(self,name,args):self.calls.append((name,args));return {'ok':self.ok,'result':{'order_id':len(self.calls)}}
class BedForecast(unittest.TestCase):
    def make(self,surge=True,ok=True):
        g=Game(ok);o=Overseer(g,goal='Migrants are arriving' if surge else 'Maintain this fort');o.count=0
        o.load({'day':0,'tick':0,'observation':{'administrators':{'citizens':19},'stocks':{'beds':19,'logs_usable':200,'food_edible':200},'orders':[]}})
        return g,o
    def beds(self,g):return [a['amount'] for n,a in g.calls if n=='add_order' and a.get('recipe')=='make_bed']
    def test_initial_demand_queues_both_legal_batches_before_a_late_manager_visit(self):
        g,o=self.make()
        with redirect_stdout(io.StringIO()):o.supply()
        self.assertEqual(self.beds(g),[30,8]);self.assertEqual(o.bed_target(),57)
    def test_forecast_is_anchored_to_initial_population_and_actual_growth_still_counts(self):
        g,o=self.make();o.cit=43;self.assertEqual(o.bed_target(),57)
        o.cit=60;self.assertEqual(o.bed_target(),72)
    def test_shortfall_with_a_pending_bed_order_does_not_duplicate_work(self):
        g,o=self.make();o.orders=[{'recipe':'make_bed','left':20}]
        with redirect_stdout(io.StringIO()):o.supply()
        self.assertEqual(self.beds(g),[])
    def test_failed_first_batch_does_not_queue_another_batch(self):
        g,o=self.make(ok=False)
        with redirect_stdout(io.StringIO()):o.supply()
        self.assertEqual(self.beds(g),[30])
    def test_non_migrant_goal_keeps_current_population_target(self):
        g,o=self.make(surge=False)
        with redirect_stdout(io.StringIO()):o.supply()
        self.assertEqual(self.beds(g),[3]);self.assertEqual(o.bed_target(),22)
