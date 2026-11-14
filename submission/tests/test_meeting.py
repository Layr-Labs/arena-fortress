import unittest
from support import overseer,resp
class Meeting(unittest.TestCase):
    def state(self):
        ov,g=overseer(resp(200,40,food=80,drink=200,cit=12));ov.surface=80
        site=dict(id='A1',kind='A',x=80,y=80,z=77,w=13,h=7,open_tiles=91,subterranean=True)
        ov.sites=[site];ov.zones=[dict(site,id=9,type='Dormitory')];return ov,g,site
    def test_one_native_zone_over_existing_underground_living_space(self):
        ov,g,site=self.state();ov.meeting();ov.meeting()
        self.assertEqual(g.tools('make_zone'),[dict(kind='meeting_area',site='A1',w=13,h=7)])
    def test_pending_dining_batch_is_not_marked_used(self):
        ov,g,site=self.state();ov.dining_batches['A1']=dict(site)
        ov.meeting();self.assertEqual(g.calls,[])
    def test_only_area_sites_are_used_not_already_owned_R_sites(self):
        ov,g,site=self.state();ov.sites=[dict(site,id='R1',kind='R',dug=True,used_by=['Dormitory 9'])]
        ov.meeting();self.assertEqual(g.calls,[])
    def test_unzoned_area_is_not_claimed_even_after_day40(self):
        ov,g,site=self.state();ov.zones=[];ov.meeting();self.assertEqual(g.calls,[])
    def test_farm_level_is_not_a_meeting_site(self):
        ov,g,site=self.state();ov.o['farm_plots']=[dict(z=77)]
        ov.meeting();self.assertEqual(g.calls,[])
    def test_labs_are_unchanged(self):
        ov,g,site=self.state();ov.hands_off=9;ov.lab=True;ov.meeting();self.assertEqual(g.calls,[])
    def test_clip_cannot_claim_new_floor_outside_existing_zone_box(self):
        ov,g,site=self.state();ov.zones[0].update(w=3,h=3);ov.meeting()
        self.assertEqual(g.tools('make_zone'),[dict(kind='meeting_area',site='A1',w=3,h=3)])
    def test_existing_meeting_zone_prevents_duplicate(self):
        ov,g,site=self.state();ov.zones.append(dict(site,id=10,type='MeetingHall'));ov.meeting()
        self.assertEqual(g.calls,[])
if __name__=='__main__':unittest.main()
