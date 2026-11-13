import unittest
from support import overseer,resp
from test_empty_cull import HERD
SPARES=[dict(id=i,race=r,tame=True,adult=True,pet_owner_id=-1)for i,r in((4,'DOG'),(5,'CAT'))]
class FinalFoodBuffer(unittest.TestCase):
    def state(self,food=19,left=25,herd=None):
        return overseer(resp(left,216-left,food=food,drink=200,cit=14),herd=HERD+SPARES if herd is None else herd)
    def test_moderate_final_stock_requests_one_small_spare_before_cliff(self):
        ov,g=self.state();ov.provision();self.assertEqual(g.tools('slaughter'),[dict(unit_id=5)])
    def test_moderate_stock_cannot_spend_protected_reserves_or_delay_later_emergency(self):
        ov,g=self.state(herd=HERD);ov.provision();self.assertEqual(g.tools('slaughter'),[]);self.assertNotIn('hunger',ov.culled)
        ov.load(resp(23,193,food=0,drink=200,cit=14));ov.count=0;ov.provision()
        self.assertEqual(g.tools('slaughter'),[dict(unit_id=3)])
    def test_early_game_moderate_stock_still_preserves_spares(self):
        ov,g=self.state(left=31);ov.provision();self.assertEqual(g.tools('slaughter'),[])
    def test_above_final_buffer_does_not_mark_animal(self):
        ov,g=self.state(food=29);ov.provision();self.assertEqual(g.tools('slaughter'),[])
if __name__=='__main__':unittest.main()
