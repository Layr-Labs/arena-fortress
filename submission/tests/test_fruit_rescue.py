"""Fruit-only fallback decisions; native gates remain authoritative for real ingredients."""
import io
import sys
import unittest
from pathlib import Path
from contextlib import redirect_stdout
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer
class Game:
    def __init__(self):self.calls=[]
    def act(self,tool,args):
        self.calls.append((tool,args));return {"ok":True,"result":{"order_id":len(self.calls)}}
class FruitRescue(unittest.TestCase):
    def setUp(self):
        cap=redirect_stdout(io.StringIO());cap.__enter__();self.addCleanup(cap.__exit__,None,None,None)
        self.g=Game();self.o=Overseer(self.g,days=216);self.o.count=0
        self.o.load({"day":0,"tick":0,"observation":{"administrators":{"citizens":10},"stocks":{"drink":0,"food_edible":100,"plants_brewable":0,"plants_by_kind":{},"furniture_free":{}},"orders":[]}})
    def fruit_calls(self):
        return [(t,a)for t,a in self.g.calls if a.get("reaction")=="BREW_DRINK_FROM_PLANT_GROWTH"]
    def test_fruit_only_counterexample_no_longer_needs_plant_map(self):
        self.o.supply();calls=self.fruit_calls();self.assertEqual(len(calls),1)
        tool,a=calls[0];self.assertEqual(tool,"add_manager_order");self.assertEqual(a["amount"],3);self.assertEqual(a["repeat"],"daily")
        self.assertEqual(a["when"],[{"item_type":"DRINK","flags":["unrotten"],"below":30},{"item_type":"PLANT_GROWTH","flags":["unrotten"],"reaction_product":"DRINK_MAT","at_least":1}])
    def test_no_barrel_only_prerequisite_blocks_native_pot_path(self):
        self.o.st["barrels_empty"]=0
        self.o.supply()
        calls=self.fruit_calls();self.assertEqual(len(calls),1)
        self.assertFalse(any(x["item_type"]in("BARREL","TOOL")for x in calls[0][1]["when"]))
    def test_available_brewable_plants_keep_primary_path(self):
        self.o.st["plants_brewable"]=5;self.o.supply();self.assertEqual(self.fruit_calls(),[])
    def test_adequate_drink_does_not_create_fruit_order(self):
        self.o.st["drink"]=30;self.o.supply();self.assertEqual(self.fruit_calls(),[])
    def test_pending_fruit_order_avoids_duplicate(self):
        self.o.orders=[{"recipe":"brew_drink_from_fruit","left":1}];self.o.supply();self.assertEqual(self.fruit_calls(),[])
    def test_dormant_standing_fruit_order_also_avoids_duplicate(self):
        self.o.orders=[{"recipe":"brew_drink_from_fruit","left":0,"repeat":"daily"}];self.o.supply();self.assertEqual(self.fruit_calls(),[])
    def test_owned_standing_order_is_not_readded_before_refresh(self):
        self.o.supply();self.o.supply();self.assertEqual(len(self.fruit_calls()),1)
if __name__=="__main__":unittest.main()
