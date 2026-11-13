import unittest
from support import overseer,resp

def animal(uid,race):return dict(id=uid,race=race,tame=True,adult=True,pet_owner_id=None)
class GrazerPriority(unittest.TestCase):
    def state(self,herd):return overseer(resp(116,99,food=1,drink=300,cit=16),herd=herd)
    def test_ordinary_midyear_hunger_uses_grazer_spare_before_dog_or_cat(self):
        herd=[animal(98,"CAT"),animal(99,"DOG"),animal(416,"WATER_BUFFALO"),animal(417,"YAK"),animal(418,"COW")]
        ov,g=self.state(herd);ov.provision();self.assertEqual(g.tools("slaughter"),[dict(unit_id=416)])
    def test_tiny_older_grazer_does_not_precede_a_substantial_grazer_spare(self):
        herd=[animal(98,"CAT"),animal(99,"DOG"),animal(80,"CAVY"),animal(416,"WATER_BUFFALO"),animal(500,"COW")]
        ov,g=self.state(herd);ov.provision();self.assertEqual(g.tools("slaughter"),[dict(unit_id=416)])
    def test_all_non_grazer_spare_order_is_unchanged(self):
        ov,g=self.state([animal(i,"DOG")for i in range(1,6)]);ov.provision();self.assertEqual(g.tools("slaughter"),[dict(unit_id=4)])
    def test_protected_mixed_herd_above_old_floor_is_not_spent_earlier(self):
        ov,g=overseer(resp(30,185,food=8,drink=300,cit=16),herd=[animal(98,"DOG"),animal(416,"WATER_BUFFALO")]);ov.provision()
        self.assertEqual(g.tools("slaughter"),[])
    def test_existing_zero_food_emergency_preserves_non_grazer_in_mixed_herd(self):
        ov,g=overseer(resp(116,99,food=0,drink=300,cit=16),herd=[animal(98,"DOG"),animal(416,"WATER_BUFFALO")]);ov.provision()
        self.assertEqual(g.tools("slaughter"),[dict(unit_id=416)])
if __name__=="__main__":unittest.main()
