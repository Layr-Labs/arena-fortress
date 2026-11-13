import unittest
from support import overseer,resp
class ExtraRoom(unittest.TestCase):
    def setUp(self):
        self.ov,self.g=overseer(resp(80,136,50,drink=80,cit=20))
        self.ov.dining_pairs=lambda built_only=False:7
        self.area=dict(id='A1',kind='A',x=80,y=80,z=76,w=30,h=30,open_tiles=25,subterranean=True)
        self.room=dict(id='R1',kind='R',x=95,y=92,z=76,w=3,h=3,soil=True,designated=False,dug=False)
        self.ov.sites=[self.area,self.room]
    def test_named_room_dig_records_plan_after_success(self):
        self.ov.expand_dining()
        self.assertEqual(self.g.tools('dig_room'),[dict(site='R1',w=7,h=5)])
        self.assertEqual(self.ov.roles['R1'],'dine')
    def test_pending_room_prevents_duplicate_dig(self):
        self.ov.expand_dining();self.ov.expand_dining()
        self.assertEqual(len(self.g.tools('dig_room')),1)
    def test_no_actual_shortage_does_not_dig(self):
        self.ov.dining_pairs=lambda built_only=False:10
        self.ov.expand_dining();self.assertEqual(self.g.calls,[])
    def test_low_food_or_drink_or_short_horizon_blocks(self):
        for attr,val in [('food_edible',2),('drink',1)]:
            with self.subTest(attr=attr):
                old=self.ov.st.get(attr);self.ov.st[attr]=val;self.ov.expand_dining();self.ov.st[attr]=old
        self.ov.days_left=5;self.ov.expand_dining()
        self.assertEqual(self.g.calls,[])
    def test_existing_hall_footprint_blocks_dig(self):
        self.ov.zones=[dict(id=9,type='DiningHall',x=95,y=92,z=76,w=3,h=3)]
        self.ov.expand_dining();self.assertEqual(self.g.calls,[])
    def test_farm_footprint_blocks_dig(self):
        self.ov.o['farm_plots']=[dict(x=95,y=92,z=76,w=3,h=3)]
        self.ov.expand_dining();self.assertEqual(self.g.calls,[])
    def test_waits_for_whole_dig_before_expanded_placement(self):
        self.ov.expand_dining()
        self.assertEqual(self.ov.dining_bounds(self.room)['w'],0)
        dug=dict(self.room,designated=True,dug=True)
        self.ov.o['dig_designations_pending']=4
        self.assertEqual(self.ov.dining_bounds(dug)['w'],0)
        self.ov.o['dig_designations_pending']=0
        box=self.ov.dining_bounds(dug)
        self.assertEqual((box['id'],box['x'],box['y'],box['w'],box['h']),('R1',95,92,7,5))
    def test_refused_dig_does_not_claim_room_or_role(self):
        self.g.refuse.add(('dig_room',None));self.ov.expand_dining()
        self.assertEqual(self.ov.dining_expansions,{})
        self.assertNotIn('R1',self.ov.roles)
    def test_second_room_only_after_first_hall_observed_and_two_max(self):
        self.ov.expand_dining()
        second=dict(self.room,id='R2',y=102);self.ov.sites.append(second)
        self.ov.dining_created.append(dict(self.room,w=7,h=5))
        self.ov.expand_dining()
        self.assertEqual(len(self.g.tools('dig_room')),1)
        self.ov.zones.append(dict(self.room,id=500,type='DiningHall',w=7,h=5))
        self.ov.expand_dining()
        self.assertEqual(len(self.g.tools('dig_room')),2)
        self.ov.sites.append(dict(self.room,id='R3',y=112));self.ov.expand_dining()
        self.assertEqual(len(self.g.tools('dig_room')),2)
    def test_narrow_shape_avoids_neighbor_hall(self):
        self.ov.zones=[dict(id=9,type='DiningHall',x=98,y=92,z=76,w=3,h=3)]
        self.ov.expand_dining()
        self.assertEqual(self.g.tools('dig_room'),[dict(site='R1',w=3,h=7)])
    def test_small_shape_can_fit_between_existing_halls(self):
        self.ov.zones=[dict(id=9,type='DiningHall',x=98,y=92,z=76,w=3,h=3),
                       dict(id=10,type='DiningHall',x=95,y=95,z=76,w=3,h=3)]
        self.ov.expand_dining()
        self.assertEqual(self.g.tools('dig_room'),[dict(site='R1',w=3,h=3)])
    def test_no_new_unobserved_level(self):
        self.ov.sites=[self.room];self.ov.expand_dining();self.assertEqual(self.g.calls,[])

if __name__=='__main__':unittest.main()
