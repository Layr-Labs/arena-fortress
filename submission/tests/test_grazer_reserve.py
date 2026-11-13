import unittest
from support import overseer,resp
DOG=dict(id=98,race="DOG",tame=True,adult=True,pet_owner_id=None)
BUFFALO=dict(id=416,race="WATER_BUFFALO",tame=True,adult=True,pet_owner_id=None)
class GrazerReserve(unittest.TestCase):
    def state(self,left=30,food=8,herd=None):
        return overseer(resp(left,215-left,food=food,drink=298,cit=16),herd=[DOG,BUFFALO]if herd is None else herd)
    def test_actual_late_hunger_herd_uses_grazer_and_keeps_dog(self):
        ov,g=self.state(food=2);ov.provision();self.assertEqual(g.tools("slaughter"),[dict(unit_id=416)])
    def test_outside_final_month_keeps_original_reserves(self):
        ov,g=self.state(left=31,food=2);ov.provision();self.assertEqual(g.tools("slaughter"),[])
    def test_pet_grazer_is_never_spent(self):
        ov,g=self.state(herd=[DOG,dict(BUFFALO,pet_owner_id=77)]);ov.provision();self.assertEqual(g.tools("slaughter"),[])
    def test_no_non_grazer_reserve_keeps_original_policy(self):
        ov,g=self.state(herd=[BUFFALO,dict(BUFFALO,id=417)]);ov.provision();self.assertEqual(g.tools("slaughter"),[])
    def test_sufficient_food_does_not_spend_a_grazer(self):
        ov,g=self.state(food=33);ov.provision();self.assertEqual(g.tools("slaughter"),[])
if __name__=="__main__":unittest.main()
