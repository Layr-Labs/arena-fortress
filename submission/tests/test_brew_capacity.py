import unittest
from support import overseer, resp

class BrewCapacity(unittest.TestCase):
    def state(self,goal=True):
        r=resp(60,0,food=60,drink=0,cit=19,hands_off=39)
        r["observation"]["map"]["sites"]=[dict(id="W1",kind="W",x=90,y=90,z=100),dict(id="W2",kind="W",x=94,y=90,z=100)]
        ov,g=overseer(r)
        ov.set_task(dict(hands_off=dict(from_day=39,days=21),goal="Have one drink per dwarf."if goal else"Restore the industry."))
        return ov,g
    def test_one_built_still_on_drink_floor_goal_gets_second(self):
        ov,g=self.state();ov.brew_capacity();self.assertEqual(g.tools("build_workshop"),[dict(type="Still",site="W1")])
    def test_success_is_remembered_across_stale_observation(self):
        ov,g=self.state();ov.brew_capacity();ov.brew_capacity()
        self.assertEqual(len(g.tools("build_workshop")),1)
    def test_unbuilt_first_still_waits_for_the_core(self):
        ov,g=self.state();next(w for w in ov.o["workshops"]if w["type"]=="Still")["built"]=False
        ov.brew_capacity();self.assertEqual(g.tools("build_workshop"),[])
    def test_second_listed_still_prevents_third(self):
        ov,g=self.state();ov.o["workshops"].append(dict(type="Still",built=False))
        ov.brew_capacity();self.assertEqual(g.tools("build_workshop"),[])
    def test_other_goal_keeps_original_capacity(self):
        ov,g=self.state(False);ov.brew_capacity();self.assertEqual(g.tools("build_workshop"),[])
    def test_refusal_does_not_record_success(self):
        ov,g=self.state();g.refuse.add(("build_workshop",None));ov.brew_capacity()
        self.assertFalse(ov.capacity_still)

if __name__=="__main__":unittest.main()
