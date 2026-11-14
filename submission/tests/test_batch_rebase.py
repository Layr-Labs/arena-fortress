import unittest
from support import overseer,resp
class BatchRebase(unittest.TestCase):
    def state(self):
        ov,g=overseer(resp(200,16,food=60,cit=15))
        def box(sid,x,h=7,z=1):return dict(id=sid,kind='A',x=x,y=0,z=z,w=20,h=h,open_tiles=100,subterranean=True)
        a,b,new=box('A3',3,3),box('A4',2),box('A6',0)
        ov.dining_batches={'A3':a,'A4':b};ov.sites=[new]
        ov.o['furniture']=[dict(id=i+1,kind=kind,x=i%10,y=row,z=1,built=True,zone_ids=[])for row,kind in enumerate(('table','chair'))for i in range(row*10,(row+1)*10)]
        ov.o['furniture_total']=20;ov.o['dig_designations_pending']=0
        return ov,g,new
    def test_shifted_origins_do_not_require_union_wider_than_native_limit(self):
        ov,g,new=self.state();self.assertFalse(ov.extra_dining_ready(new))
        ov.remember_dining_batch(new)
        self.assertEqual(set(ov.dining_batches),{'A6'});self.assertTrue(ov.extra_dining_ready(new))
    def test_completed_real_furniture_batch_can_commit_one_disjoint_zone(self):
        ov,g,new=self.state();ov.remember_dining_batch(new)
        ov.act('commit','make_zone',dict(kind='dining_hall',site='A6',w=20,h=7))
        self.assertEqual(g.tools('make_zone'),[dict(kind='dining_hall',site='A6',w=20,h=7)])
    def test_other_level_and_disjoint_batch_are_retained(self):
        ov,g,new=self.state();ov.dining_batches['B']=dict(new,id='B',z=2)
        ov.dining_batches['C']=dict(new,id='C',x=40)
        ov.remember_dining_batch(new)
        self.assertEqual(set(ov.dining_batches),{'A6','B','C'})
    def test_existing_dining_zone_still_blocks_overlap(self):
        ov,g,new=self.state();ov.zones=[dict(new,id=90,type='DiningHall',w=3,h=3)]
        ov.remember_dining_batch(new);self.assertNotIn('A6',ov.dining_batches)
        ov.act('commit','make_zone',dict(kind='dining_hall',site='A6',w=20,h=7))
        self.assertEqual(g.calls,[])
    def test_legacy_small_rectangle_cannot_zone_only_first_pair(self):
        ov,g,new=self.state();ov.remember_dining_batch(new)
        self.assertFalse(ov.extra_dining_ready(dict(new,w=3,h=3)))
    def test_extra_room_accounting_and_batch_target_unchanged(self):
        ov,g,new=self.state();ov.dining_expansions['R1']=dict(new,id='R1',x=50,w=7,h=3)
        ov.remember_dining_batch(new);self.assertIn('R1',ov.dining_expansions)
        self.assertEqual(ov.extra_dining_goal(new),10)
    def test_small_room_cannot_retire_larger_area_batch(self):
        ov,g,new=self.state();ov.remember_dining_batch(new)
        small=dict(new,id='R1',kind='R',w=3,h=3,dug=True)
        ov.remember_dining_batch(small)
        self.assertIn('A6',ov.dining_batches)
        self.assertFalse(ov.extra_dining_ready(small))
    def test_smaller_activity_box_cannot_lower_pending_batch_goal(self):
        ov,g,new=self.state();ov.remember_dining_batch(new)
        small=dict(new,id='A7',w=3,h=3)
        ov.remember_dining_batch(small)
        self.assertIn('A6',ov.dining_batches)
        self.assertFalse(ov.extra_dining_ready(small))
if __name__=='__main__':unittest.main()
