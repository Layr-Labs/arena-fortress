"""Conditional reserve lifetime, native three-condition budget, and goal scope."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
VARIANT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(VARIANT))
from overseer import harness
assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

class Game:
    def __init__(self):self.calls=[];self.fail_high=False
    def query(self, name, **params):
        assert name == "units" and params == {"kind": "animals"}
        return {"result": {"units": []}}
    def act(self,name,args):
        self.calls.append((name,args))
        high=args.get("recipe")=="brew_drink" and any(v.get("stock")=="food_edible" for v in args.get("when",[]))
        if high and self.fail_high:return {"ok":False,"error_code":"bad_arguments"}
        return {"ok":True,"result":{"order_id":len(self.calls)}}

class FoodGatedReserve(unittest.TestCase):
    def setUp(self):
        out=redirect_stdout(io.StringIO());out.__enter__();self.addCleanup(out.__exit__,None,None,None)
    def guard(self,days=336,cit=14,goal="",window=None):
        game=Game();g=harness.Overseer(game,days=days,goal=goal)
        resp={"day":0,"tick":0,"days_left":days,"observation":{"administrators":{"citizens":cit},"stocks":{"food_edible":200},"orders":[]}}
        if window is not None:resp["hands_off_in_days"]=window
        g.load(resp);g.count=0;return g,game
    def highs(self,game):
        return [a for n,a in game.calls if a.get("recipe")=="brew_drink" and any(v.get("stock")=="food_edible" for v in a.get("when",[]))]
    def test_accepted_surplus_added_once_with_stale_observed_orders(self):
        g,game=self.guard();g.supply();g.now=10*harness.DAY;g.supply()
        self.assertEqual(len(self.highs(game)),1)
        self.assertIn("o_brew_surplus_end",g.done)
    def test_failed_surplus_is_retried_and_only_success_marks_done(self):
        g,game=self.guard();game.fail_high=True;g.supply();self.assertNotIn("o_brew_surplus_end",g.done)
        game.fail_high=False;g.now=3*harness.DAY;g.supply();self.assertIn("o_brew_surplus_end",g.done)
        self.assertEqual(len(self.highs(game)),2)
    def test_shorter_horizon_has_no_surplus_and_keeps_late_plant_gate(self):
        g,game=self.guard(days=216);g.supply();self.assertEqual(self.highs(game),[])
        g.endgame_supply();late=next(a for n,a in game.calls if a.get("recipe")=="brew_drink" and a.get("amount")==4)
        self.assertIn({"stock":"plants_brewable","at_least":14},late["when"])
    def test_full_year_late_reserve_has_food_gate_and_three_conditions(self):
        g,game=self.guard();g.supply();g.endgame_supply()
        late=next(a for n,a in game.calls if a.get("recipe")=="brew_drink" and a.get("amount")==4 and any(v.get("stock")=="food_edible" for v in a.get("when",[])))
        self.assertIn({"stock":"food_edible","at_least":168},late["when"])
        self.assertIn({"stock":"barrels_empty","at_least":1},late["when"])
        self.assertEqual(len(late["when"]),3)
        self.assertTrue(all(len(a.get("when",[]))<=3 for n,a in game.calls))
    def test_large_full_year_fort_has_low_drink_emergency_without_food_gate(self):
        g,game=self.guard(cit=30);g.endgame_supply()
        emergency=next(a for n,a in game.calls if a.get("recipe")=="brew_drink" and {"stock":"drink","below":360} in a.get("when",[]))
        self.assertIn({"stock":"plants_brewable","at_least":2},emergency["when"])
        self.assertFalse(any(v.get("stock")=="food_edible" for v in emergency["when"]))
        self.assertEqual(len(emergency["when"]),3)
    def test_drink_growth_window_keeps_ceilingless_order_without_extra_tier(self):
        g,game=self.guard(goal="drink must not end lower",window=40);g.supply()
        orders=[a for n,a in game.calls if a.get("recipe")=="brew_drink"]
        self.assertEqual(len(orders),1);self.assertFalse(any(v.get("stock")=="drink" for v in orders[0]["when"]))
    def test_existing_foreign_brew_does_not_suppress_distinct_owned_surplus(self):
        g,game=self.guard();g.orders=[{"id":99,"recipe":"brew_drink","job":"CustomReaction","reaction":"BREW_DRINK_FROM_PLANT","repeat":"daily"}];g.supply()
        self.assertEqual(len(self.highs(game)),1);self.assertNotIn(99,g.owned)

if __name__=="__main__":unittest.main()
