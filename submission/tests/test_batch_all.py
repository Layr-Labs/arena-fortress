import unittest
from support import overseer,resp
class BatchAll(unittest.TestCase):
    def state(self):
        ov,g=overseer(resp(200,40,food=80,drink=200,cit=12))
        site=dict(id='A1',kind='A',x=80,y=80,z=76,w=7,h=5,open_tiles=35,subterranean=True)
        ov.sites=[site];return ov,g,site
    def test_selected_fresh_hall_registers_bounded_batch(self):
        ov,g,site=self.state();self.assertEqual(ov.dine_site()['id'],'A1')
        self.assertEqual(ov.extra_dining_goal(site),10);self.assertIn('A1',ov.dining_batches)
    def test_larger_fresh_box_replaces_contained_old_box(self):
        ov,g,site=self.state();ov.remember_dining_batch(dict(site,id='A0',w=3,h=3));ov.remember_dining_batch(site)
        self.assertEqual(set(ov.dining_batches),{'A1'})
    def test_excavation_blocks_premature_initial_zone(self):
        ov,g,site=self.state();ov.remember_dining_batch(site);ov.o['dig_designations_pending']=1
        self.assertFalse(ov.extra_dining_ready(site))
    def test_lab_does_not_register_new_policy(self):
        ov,g,site=self.state();ov.lab=True;ov.hands_off=9
        ov.remember_dining_batch(site);self.assertEqual(ov.dining_batches,{})
    def test_sufficient_existing_capacity_does_not_start_another_batch(self):
        ov,g,site=self.state();ov.dining_pairs=lambda built_only=False:10
        ov.remember_dining_batch(site);self.assertEqual(ov.dining_batches,{})
        ov.supply()
        self.assertEqual([a for a in g.tools('add_order')if a.get('recipe')in('make_table','make_chair')],[])
    def test_an_existing_batch_can_finish_after_other_capacity_arrives(self):
        ov,g,site=self.state();ov.remember_dining_batch(site)
        ov.dining_pairs=lambda built_only=False:10;ov.remember_dining_batch(site)
        self.assertIn('A1',ov.dining_batches)
    def test_one_batch_does_not_take_the_whole_global_shortfall(self):
        ov,g,site=self.state();site.update(w=3,h=7)
        ov.dining_expansions['A1']=dict(site);ov.dining_batches['A1']=dict(site)
        ov.dining_pairs=lambda built_only=False:0
        ov.room_for=lambda role:site;ov.dine_site=lambda:site
        ov.dining_local=lambda unused:{'table':8,'chair':8}
        ov.free={'table':20,'chair':20};ov.needs_zone=lambda *args:False
        placed=[]
        def place(key,kind,site,count):
            placed.append(kind);return [dict(kind=kind,x=80,y=80,z=76)]
        ov.place=place;ov.furnish()
        self.assertEqual(placed,['table','chair'])
if __name__=='__main__':unittest.main()
