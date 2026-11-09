import io
import unittest
from contextlib import redirect_stdout
from overseer.harness import Overseer, WEALTH_TARGET

class Game:
    def __init__(self): self.calls=[]
    def act(self,tool,args):
        self.calls.append((tool,args))
        return {"ok":True,"result":{"order_id":41}} if tool=="add_manager_order" else {"ok":True,"result":{}}

class StopCrafts(unittest.TestCase):
    def make(self):
        g=Game(); o=Overseer(g);o.days=336;o.count=0
        o.load({"day":60,"tick":72000,"observation":{"administrators":{"citizens":10},"wealth":{"created":1000},"workshops":[{"type":"Craftsdwarfs"}],"orders":[]}})
        return g,o
    def test_cancels_only_its_own_progression_order_at_target(self):
        g,o=self.make()
        with redirect_stdout(io.StringIO()):o.progress()
        self.assertEqual(o.progress_orders,{41})
        o.o["wealth"]["created"]=WEALTH_TARGET
        o.orders=[{"id":41,"job":"MakeCrafts","repeat":"daily"},{"id":99,"job":"MakeCrafts","repeat":"daily"}]
        with redirect_stdout(io.StringIO()):o.progress()
        self.assertEqual(g.calls[-1],("cancel_order",{"order_id":41}))
        self.assertEqual(sum(t=="cancel_order" for t,a in g.calls),1)
    def test_does_not_cancel_foreign_crafts_at_target(self):
        g,o=self.make();o.o["wealth"]["created"]=WEALTH_TARGET;o.orders=[{"id":99,"job":"MakeCrafts","repeat":"daily"}]
        with redirect_stdout(io.StringIO()):o.progress()
        self.assertEqual(g.calls,[])
    def test_leaves_own_order_running_below_target(self):
        g,o=self.make();o.progress_orders={41};o.orders=[{"id":41,"job":"MakeCrafts","repeat":"daily"}]
        with redirect_stdout(io.StringIO()):o.progress()
        self.assertEqual(g.calls,[])
    def test_missing_order_is_forgotten_after_refresh(self):
        g,o=self.make();o.progress_orders={41}
        o.load({"observation":{"orders":[]}})
        self.assertEqual(o.progress_orders,set())
