import unittest
from support import overseer,resp
from test_empty_cull import HERD
class FoodFloor(unittest.TestCase):
    def state(self,left=24,food=2,herd=HERD,cit=10):return overseer(resp(left,216-left,food,cit=cit),herd=herd)
    def test_one_small_reserve_animal_before_zero(self):
        ov,g=self.state();self.assertEqual(ov.cull('hunger',2,True,5),1)
        self.assertEqual(g.tools('slaughter'),[dict(unit_id=3)])
    def test_last_animal_still_saved_at_positive_food(self):
        ov,g=self.state(herd=HERD[:1]);self.assertEqual(ov.cull('hunger',1,True,5),0)
        self.assertNotIn('hunger',ov.culled)
    def test_no_change_before_final_stretch(self):
        ov,g=self.state(left=31);self.assertEqual(ov.cull('hunger',1,True,5),0)
    def test_above_threshold_still_protects_reserve(self):
        ov,g=self.state(food=4);self.assertEqual(ov.cull('hunger',1,True,5),0)
    def test_population_floor_scales(self):
        ov,g=self.state(food=5,cit=25);self.assertEqual(ov.cull('hunger',1,True,5),1)
    def test_labs_do_not_enable_floor(self):
        ov,g=self.state();ov.hands_off=20;ov.lab=True;self.assertFalse(ov.final_floor(3))
    def test_existing_success_cooldown_is_preserved(self):
        ov,g=self.state();self.assertEqual(ov.cull('hunger',1,True,5),1)
        ov.load(resp(22,194,1));ov.count=0;self.assertEqual(ov.cull('hunger',1,True,5),0)
if __name__=='__main__':unittest.main()
