"""Keep a model's new crop plot from taking a floor already reserved for ordinary housing."""
import io,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stdout
VARIANT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(VARIANT))
from plain.harness import Plain
import plain.harness as module
assert Path(module.__file__).is_relative_to(VARIANT)

class Game:
    def __init__(self):self.calls=[];self.last={"day":14,"tick":16800}
    def task(self):
        return {"task":{"days":216},"tools":[{"type":"function","function":{"name":"build_farm","parameters":{"type":"object","properties":{"site":{"type":"string"}}}}}]}
    def query(self,*args,**kwargs):return {"result":{"units":[]}}
    def act(self,name,args):
        self.calls.append((name,args));return {"ok":True,"result":{}}

class HousingFloorGuard(unittest.TestCase):
    def setUp(self):
        quiet=redirect_stdout(io.StringIO());quiet.__enter__();self.addCleanup(quiet.__exit__,None,None,None)
    def player(self,days=216,goal="",hands_off=None):
        g=Game();p=Plain(SimpleNamespace(task={"days":days,"goal":goal},days=days,credits=None),g,SimpleNamespace(usage={"cost_usd":0}))
        p.setup()
        sites=[{"id":"R2","kind":"R","x":99,"y":92,"z":159,"w":3,"h":3,"dug":True},
               {"id":"F2","kind":"F","x":99,"y":92,"z":159,"w":3,"h":3},
               {"id":"F6","kind":"F","x":99,"y":92,"z":158,"w":3,"h":3}]
        p.guard.load({"day":14,"tick":16800,"days_left":days-14,"hands_off_in_days":hands_off,
            "observation":{"map":{"sites":sites},"administrators":{"citizens":12},"stocks":{"food_edible":70}}})
        p.guard.roles={"R2":"dine"}
        return p,g
    def call(self,p,site):
        p.run_call({"id":"farm","function":{"name":"build_farm","arguments":json.dumps({"site":site})}})
        return json.loads(p.messages[-1]["content"])
    def test_real_f2_alias_on_dining_floor_is_refused_before_game_action(self):
        p,g=self.player();r=self.call(p,"F2")
        self.assertFalse(r["ok"]);self.assertEqual(r["error_code"],"layer_owned");self.assertEqual(g.calls,[])
    def test_observed_crop_floor_remains_available(self):
        p,g=self.player();r=self.call(p,"F6")
        self.assertTrue(r["ok"]);self.assertEqual(g.calls,[("build_farm",{"site":"F6"})])
    def test_room_site_itself_cannot_be_converted_to_farm(self):
        p,g=self.player();self.assertEqual(self.call(p,"R2")["error_code"],"layer_owned");self.assertEqual(g.calls,[])
    def test_newly_exposed_farm_alias_uses_latest_model_visible_catalog(self):
        p,g=self.player();p.guard.sites=[s for s in p.guard.sites if s["kind"]=="R"]
        obs={"map":{"sites":[{"id":"F9","kind":"F","z":159,"x":120,"y":100}]},"administrators":{"citizens":12}}
        p.user_message({"day":14,"tick":16800,"days_left":202},obs)
        self.assertEqual(self.call(p,"F9")["error_code"],"layer_owned");self.assertEqual(g.calls,[])
    def test_dormitory_and_office_reservations_are_protected_too(self):
        for role in("dorm","office"):
            with self.subTest(role=role):
                p,g=self.player();p.guard.roles={"R2":role}
                self.assertEqual(self.call(p,"F2")["error_code"],"layer_owned");self.assertEqual(g.calls,[])
    def test_existing_crop_roles_do_not_claim_housing_ownership(self):
        p,g=self.player();p.guard.roles={"R2":"farm"}
        self.assertTrue(self.call(p,"F2")["ok"]);self.assertEqual(len(g.calls),1)
    def test_short_and_hands_off_tasks_keep_their_existing_model_behavior(self):
        for days,window in((60,39),(90,None),(336,28)):
            with self.subTest(days=days,window=window):
                p,g=self.player(days=days,hands_off=window)
                self.assertTrue(self.call(p,"F2")["ok"]);self.assertEqual(len(g.calls),1)
    def test_migrant_goal_is_not_changed_even_on_long_horizon(self):
        p,g=self.player(days=336,goal="A migrant surge is coming")
        self.assertTrue(self.call(p,"F2")["ok"]);self.assertEqual(len(g.calls),1)
    def test_unknown_or_malformed_sites_are_left_to_native_argument_validation(self):
        p,g=self.player()
        self.assertIsNone(p.refuse("build_farm",{"site":"F_UNKNOWN"},16800))
        self.assertIsNone(p.refuse("build_farm",{"site":[]},16800))
    def test_other_model_tools_keep_existing_authority(self):
        p,g=self.player()
        self.assertIsNone(p.refuse("build_workshop",{"site":"R2","type":"Kitchen"},16800))
if __name__=="__main__":unittest.main()
