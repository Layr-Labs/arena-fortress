import unittest
from support import overseer, resp
from test_manager_office import ZoneGame

class OfficeBootstrap(unittest.TestCase):
    def state(self, validated=False):
        orders=[dict(id=1,recipe="brew_drink",validated=validated)]
        r=resp(60,0,food=60,drink=0,cit=19,hands_off=39,orders=orders)
        r["observation"]["stocks"]["furniture_free"]={"chair":12}
        r["observation"]["administrators"]["MANAGER_id"]=91
        r["observation"]["map"]={"surface_z":150,"sites":[dict(id="R1",kind="R",x=90,y=90,z=149,w=3,h=3,soil=True,dug=False,free=True),dict(id="R2",kind="R",x=94,y=90,z=149,w=3,h=3,soil=True,dug=False,free=True)]}
        ov,g=overseer(r);ov.set_task(dict(hands_off=dict(from_day=39,days=21),goal="Have one drink per dwarf."))
        ov.game=ZoneGame()
        return ov,ov.game
    def test_unvalidated_start_excavates_only_one_three_by_three_office(self):
        ov,g=self.state();ov.digging()
        self.assertEqual(g.tools("dig_room"),[dict(site="R1",w=3,h=3)])
        self.assertEqual(ov.roles,{"R1":"office"})
    def test_bootstrap_room_in_progress_prevents_more_excavation(self):
        ov,g=self.state();ov.startup_office="R1";ov.o["dig_designations_pending"]=9
        ov.sites[0]["designated"]=True;ov.digging();self.assertEqual(g.tools("dig_room"),[])
    def test_dug_bootstrap_room_is_zoned_assigned_and_furnished(self):
        ov,g=self.state();ov.startup_office="R1";ov.sites[0]["dug"]=True
        ov.digging();self.assertEqual(g.tools("dig_room"),[])
        self.assertEqual(g.tools("make_zone"),[dict(kind="office",site="R1",w=3,h=3)])
        self.assertEqual(g.tools("assign_zone"),[dict(zone_id=701,dwarf_id=91)])
        self.assertEqual(g.tools("place_furniture"),[dict(kind="chair",site="R1")])
    def test_pending_chair_does_not_trigger_duplicate_placement(self):
        ov,g=self.state();ov.startup_office="R1";ov.sites[0]["dug"]=True
        ov.o["furniture"]=[dict(kind="chair",built=False,x=90,y=90,z=149)]
        ov.digging();self.assertEqual(g.tools("place_furniture"),[])
    def test_refused_bootstrap_zone_does_not_place_an_unzoned_chair(self):
        ov,g=self.state();ov.startup_office="R1";ov.sites[0]["dug"]=True;g.refuse.add(("make_zone",None))
        ov.digging();self.assertEqual(g.tools("place_furniture"),[])
    def test_exhausted_bootstrap_chair_calls_fall_back_to_original_planner(self):
        ov,g=self.state();ov.startup_office="R1";ov.sites[0]["dug"]=True;ov.tries["boot_chair_R1"]=3
        self.assertFalse(ov.office_bootstrap())
    def test_owned_usable_office_waits_without_new_dig(self):
        ov,g=self.state();ov.zones=[dict(type="Office",owner=91,furniture=dict(chair=1))]
        ov.digging();self.assertEqual(g.tools("dig_room"),[])
    def test_validated_brew_resumes_original_excavation(self):
        ov,g=self.state(validated=True);ov.digging()
        self.assertEqual(g.tools("dig_room"),[dict(site="R1"),dict(site="R2")])
    def test_missing_spare_chair_uses_original_planner(self):
        ov,g=self.state();ov.free["chair"]=0;ov.digging()
        self.assertEqual(g.tools("dig_room"),[dict(site="R1"),dict(site="R2")])
    def test_bounded_bootstrap_refusals_do_not_stall_all_future_digging(self):
        ov,g=self.state();ov.tries.update(boot_office_R1=2,boot_office_R2=2)
        ov.digging();self.assertEqual(g.tools("dig_room"),[dict(site="R1"),dict(site="R2")])
    def test_other_goal_keeps_original_digging(self):
        ov,g=self.state();ov.set_task(dict(goal="Run the fortress"));ov.digging()
        self.assertEqual(g.tools("dig_room"),[dict(site="R1"),dict(site="R2")])

if __name__=="__main__":unittest.main()
