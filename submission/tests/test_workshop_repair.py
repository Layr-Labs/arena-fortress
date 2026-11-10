"""Essential workshop recovery requires explicit suspended construction and stays bounded."""
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
    def __init__(self,fail=False):self.calls=[];self.fail=fail
    def act(self,tool,args):
        self.calls.append((tool,args))
        if self.fail:return {"ok":False,"error_code":"no_material"}
        return {"ok":True,"result":{"id":len(self.calls)}}

class WorkshopRepair(unittest.TestCase):
    def setUp(self):
        out=redirect_stdout(io.StringIO());out.__enter__();self.addCleanup(out.__exit__,None,None,None)
    def guard(self,workshops,fail=False):
        game=Game(fail);g=harness.Overseer(game,days=336)
        sites=[{"id":"W"+str(i),"kind":"W","free":True,"x":10*i,"y":10,"z":10} for i in range(1,5)]
        g.load({"day":0,"tick":0,"observation":{"administrators":{"citizens":7},"stocks":{"logs_usable":100},"map":{"surface_z":10,"sites":sites},"workshops":workshops}})
        g.count=0;return g,game
    def pending(self,suspended=True):
        return {"type":"Carpenters","built":False,"job_details":[{"job":"ConstructBuilding","suspended":suspended}]}
    def test_built_instance_suppresses_replacement_of_other_suspended_copy(self):
        g,game=self.guard([self.pending(),{"type":"Carpenters","built":True}]);g.ensure_workshop("Carpenters");g.now=100*harness.DAY;g.ensure_workshop("Carpenters")
        self.assertEqual(game.calls,[])
    def test_active_pending_construction_is_not_replaced(self):
        g,game=self.guard([self.pending(False)]);g.ensure_workshop("Carpenters");g.now=100*harness.DAY;g.ensure_workshop("Carpenters")
        self.assertEqual(game.calls,[])
    def test_unknown_status_is_not_inferred_suspended(self):
        for w in [{"type":"Carpenters"},{"type":"Carpenters","built":False,"jobs":["ConstructBuilding"]}]:
            with self.subTest(w=w):
                g,game=self.guard([w]);g.ensure_workshop("Carpenters");g.now=100*harness.DAY;g.ensure_workshop("Carpenters");self.assertEqual(game.calls,[])
    def test_seven_day_grace_and_two_accepted_replacement_limit(self):
        g,game=self.guard([self.pending()]);g.ensure_workshop("Carpenters")
        g.now=6*harness.DAY;g.ensure_workshop("Carpenters");self.assertEqual(game.calls,[])
        g.now=7*harness.DAY;g.ensure_workshop("Carpenters");g.ensure_workshop("Carpenters");self.assertEqual(len(game.calls),1)
        g.now=14*harness.DAY;g.ensure_workshop("Carpenters");self.assertEqual(len(game.calls),2)
        g.now=100*harness.DAY;g.ensure_workshop("Carpenters");self.assertEqual(len(game.calls),2)
        self.assertEqual([args["site"] for _,args in game.calls],["W1","W2"])
        self.assertEqual(g.workshop_replacements["Carpenters"],2)
    def test_failed_request_does_not_count_as_accepted_replacement(self):
        g,game=self.guard([self.pending()],fail=True);g.ensure_workshop("Carpenters");g.now=7*harness.DAY;g.ensure_workshop("Carpenters")
        self.assertEqual(g.workshop_replacements.get("Carpenters",0),0)
        game.fail=False;g.now=10*harness.DAY;g.ensure_workshop("Carpenters");self.assertEqual(g.workshop_replacements["Carpenters"],1)
    def test_production_job_suspension_does_not_qualify(self):
        w={"type":"Carpenters","built":False,"job_details":[{"job":"ConstructBed","suspended":True}]};g,game=self.guard([w]);g.ensure_workshop("Carpenters");g.now=100*harness.DAY;g.ensure_workshop("Carpenters");self.assertEqual(game.calls,[])
    def test_completion_clears_stall_without_extra_request(self):
        w=self.pending();g,game=self.guard([w]);g.ensure_workshop("Carpenters");self.assertIn("Carpenters",g.workshop_stalls)
        w["built"]=True;g.now=100*harness.DAY;g.ensure_workshop("Carpenters");self.assertNotIn("Carpenters",g.workshop_stalls);self.assertEqual(game.calls,[])

if __name__=="__main__":unittest.main()
