import unittest
from support import overseer,resp
class GlobalDining(unittest.TestCase):
    def setUp(self):
        self.ov,self.g=overseer(resp(100,116,60,cit=18))
        self.site=dict(id='A2',kind='A',x=87,y=88,z=76,w=17,h=9,subterranean=True,open_tiles=40)
        self.zone=dict(id=39,type='DiningHall',x=87,y=88,z=76,w=5,h=3)
        self.ov.zones=[self.zone]
    def test_ordinary_partial_overlap_rejected(self):
        self.assertFalse(self.ov.dining_disjoint(self.site))
        self.ov.zone_dining(self.site)
        self.assertEqual(self.g.tools('make_zone'),[])
    def test_fully_covered_site_is_not_reused(self):
        s=dict(self.site,w=3,h=3)
        self.assertFalse(self.ov.dining_disjoint(s))
    def test_touching_edge_is_disjoint(self):
        self.assertTrue(self.ov.dining_disjoint(dict(self.site,x=92)))
    def test_other_level_is_disjoint(self):
        self.assertTrue(self.ov.dining_disjoint(dict(self.site,z=77)))
    def test_unknown_zone_level_blocks_conservatively(self):
        self.ov.zones=[dict(self.zone,z=None)]
        self.assertFalse(self.ov.dining_disjoint(self.site))
    def test_unknown_site_box_blocks(self):
        s=dict(self.site);s.pop('x')
        self.assertFalse(self.ov.dining_disjoint(s))
    def test_planner_chooses_fresh_site_instead_of_expanding_hall(self):
        alt=dict(self.site,id='A1',z=77,w=12,h=4)
        self.ov.sites=[self.site,alt];self.ov.room_for=lambda role:self.site
        self.assertEqual(self.ov.dine_site()['id'],'A1')

if __name__=='__main__':unittest.main()
