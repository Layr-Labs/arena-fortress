import io, unittest
from contextlib import redirect_stdout
from overseer.harness import Overseer

class Game:
    def __init__(self): self.calls=[]
    def act(self,name,args):
        self.calls.append((name,args)); return {"ok":True,"result":{"order_id":len(self.calls)}}

class YearReserve(unittest.TestCase):
    def order(self,days,cit):
        g=Game();o=Overseer(g,days=days);o.count=0
        o.load({"day":0,"tick":0,"observation":{"administrators":{"citizens":cit},"stocks":{"food_edible":100},"orders":[]}})
        with redirect_stdout(io.StringIO()):o.supply()
        return [a for n,a in g.calls if n=="add_order" and a.get("recipe")=="brew_drink"]
    def test_full_year_keeps_baseline_and_adds_food_protected_reserve(self):
        for cit,want in [(7,600),(25,750)]:
            with self.subTest(cit=cit):
                base,high=self.order(336,cit)
                self.assertIn({"stock":"drink","below":want},base["when"])
                self.assertIn({"stock":"plants_brewable","at_least":2},base["when"])
                self.assertIn({"stock":"barrels_empty","at_least":1},base["when"])
                self.assertIn({"stock":"drink","below":want},high["when"])
                self.assertIn({"stock":"food_edible","at_least":max(150,12*cit)},high["when"])
                self.assertEqual(len(high["when"]),3)
    def test_shorter_management_horizon_keeps_ordinary_reserve(self):
        self.assertIn({"stock":"drink","below":300},self.order(216,14)[0]["when"])
