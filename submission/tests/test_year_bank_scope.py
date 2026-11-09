"""Scope the restored early reserve; isolate banking from the last-plant change."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer import harness
class Game:
    def __init__(self):self.calls=[]
    def act(self,n,a):self.calls.append((n,a));return {'ok':True,'result':{'order_id':len(self.calls)}}
class BankScope(unittest.TestCase):
    def guard(self,days=336,goal='',window=None):
        g=Game();a=harness.Overseer(g,days=days,goal=goal)
        r={'day':0,'tick':0,'observation':{'administrators':{'citizens':7},'stocks':{'food_edible':100},'orders':[]}}
        if window is not None:r['hands_off_in_days']=window
        a.load(r);a.count=0
        with redirect_stdout(io.StringIO()):a.supply()
        return next(q for n,q in g.calls if q.get('recipe')=='brew_drink')
    def test_ordinary_year_banks600_but_keeps_two_plant_gate(self):
        q=self.guard();self.assertIn({'stock':'drink','below':600},q['when'])
        self.assertIn({'stock':'plants_brewable','at_least':2},q['when'])
    def test_shorter_tasks_keep300(self):
        for days in [45,60,216]:
            with self.subTest(days=days):self.assertIn({'stock':'drink','below':300},self.guard(days=days)['when'])
    def test_migrant_and_window_scopes_do_not_get_the_new_bank(self):
        for args in [{'goal':'migrant surge'},{'window':40},{'goal':'drink must not end lower'}]:
            with self.subTest(args=args):self.assertIn({'stock':'drink','below':300},self.guard(**args)['when'])
if __name__=='__main__':unittest.main()
