import unittest
import test_meeting
class MeetingClip(unittest.TestCase):
    def state(self):return test_meeting.Meeting().state()
    def test_unrelated_farm_on_same_level_does_not_exclude_living_space(self):
        ov,g,site=self.state();ov.o['farm_plots']=[dict(x=100,y=100,z=77,w=3,h=3)]
        ov.meeting();self.assertEqual(len(g.tools('make_zone')),1)
    def test_actual_two_farms_leave_named_origin_two_column_strip(self):
        ov,g,site=self.state();site.update(x=89,y=96,z=150);ov.surface=153;ov.zones=[dict(site,id=9,type='Dormitory')]
        ov.o['farm_plots']=[dict(x=91,y=98,z=150,w=3,h=3),dict(x=94,y=96,z=150,w=3,h=3)]
        ov.meeting();self.assertEqual(g.tools('make_zone'),[dict(kind='meeting_area',site='A1',w=2,h=7)])
    def test_farm_covering_anchor_leaves_no_valid_native_box(self):
        ov,g,site=self.state();ov.o['farm_plots']=[dict(x=80,y=80,z=77,w=3,h=3)]
        ov.meeting();self.assertEqual(g.calls,[])
    def test_box_must_keep_nine_tiles(self):
        ov,g,site=self.state();site.update(w=3,h=3);ov.zones=[dict(site,id=9,type='Dormitory')]
        ov.o['farm_plots']=[dict(x=82,y=82,z=77,w=3,h=3)]
        ov.meeting();self.assertEqual(g.calls,[])
if __name__=='__main__':unittest.main()
