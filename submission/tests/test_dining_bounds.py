import unittest
from support import overseer, resp

class DiningBounds(unittest.TestCase):
    def setUp(self):
        self.ov, self.g = overseer(resp(80, 136, 60, cit=18))
        self.site = dict(id='A2', kind='A', x=83, y=93, z=92, w=45, h=34,
                         subterranean=True, open_tiles=119)
        self.ov.sites=[self.site]
    def test_clip_keeps_named_origin_and_source(self):
        b=self.ov.dining_bounds(self.site)
        self.assertEqual((b['id'],b['x'],b['y'],b['z'],b['w'],b['h']),('A2',83,93,92,20,20))
        self.assertEqual(self.site['w'],45)
        self.assertNotIn('_dining_bounds',self.site)
    def test_small_site_unchanged(self):
        s=dict(self.site,w=5,h=3)
        self.assertIs(self.ov.dining_bounds(s),s)
    def test_surface_site_unchanged(self):
        s=dict(self.site,subterranean=False)
        self.assertIs(self.ov.dining_bounds(s),s)
    def test_enough_physical_seats_unchanged(self):
        self.ov.real_seats=lambda:9
        self.assertIs(self.ov.dining_bounds(self.site),self.site)
    def test_placement_and_zone_match(self):
        b=self.ov.dining_bounds(self.site)
        self.ov.place('p_test','chair',b,4)
        self.ov.zone_dining(b)
        for tool in ('place_furniture','make_zone'):
            args=self.g.tools(tool)[0]
            self.assertEqual((args['site'],args['w'],args['h']),('A2',20,20))
    def test_legacy_arguments_unchanged(self):
        self.ov.place('p_test','chair',self.site,2)
        self.ov.zone_dining(self.site)
        self.assertEqual(self.g.tools('place_furniture'),[dict(kind='chair',site='A2',count=2)])
        self.assertEqual(self.g.tools('make_zone'),[dict(kind='dining_hall',site='A2')])
    def test_capped_overlap_does_not_duplicate(self):
        self.ov.zone=lambda kind:[dict(id=50,building_ids=[1,2,3,4],furniture=dict(table=2,chair=2)),
                                 dict(id=54,building_ids=[1,2,3,4,5,6],furniture=dict(table=3,chair=3))]
        self.ov.o['furniture']=[]
        self.ov.o['furniture_total']=100
        self.assertEqual(self.ov.dining_kinds(True),dict(table=3,chair=3))
    def test_visible_extra_capped_member_counted_once(self):
        self.ov.zone=lambda kind:[dict(id=54,building_ids=[1,2],furniture=dict(table=1,chair=1))]
        self.ov.o['furniture']=[dict(id=2,kind='chair',built=True,zone_ids=[54]),
                                dict(id=3,kind='chair',built=True,zone_ids=[54])]
        self.ov.o['furniture_total']=100
        self.assertEqual(self.ov.dining_kinds(True),dict(table=1,chair=2))

class DisjointDining(unittest.TestCase):
    setUp = DiningBounds.setUp
    def test_existing_zone_at_origin_blocks_new_box(self):
        self.ov.zone=lambda kind:[dict(x=83,y=93,z=92,w=5,h=3)]
        self.assertIs(self.ov.dining_bounds(self.site),self.site)
    def test_trim_prefix_avoids_existing_zone(self):
        self.ov.zone=lambda kind:[dict(x=83,y=101,z=92,w=5,h=3)]
        b=self.ov.dining_bounds(self.site)
        self.assertEqual((b['w'],b['h']),(20,8))
        self.assertEqual(b['y']+b['h'],101)
    def test_other_level_does_not_block(self):
        self.ov.zone=lambda kind:[dict(x=83,y=93,z=91,w=5,h=3)]
        b=self.ov.dining_bounds(self.site)
        self.assertEqual((b['w'],b['h']),(20,20))
    def test_incomplete_zone_box_blocks_conservatively(self):
        self.ov.zone=lambda kind:[dict(z=92)]
        self.assertIs(self.ov.dining_bounds(self.site),self.site)

if __name__=='__main__':unittest.main()
