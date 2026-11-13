import unittest
from support import overseer,resp
class InvaderOnly(unittest.TestCase):
    def state(self,orders=None,invader=False):
        ov,g=overseer(resp(120,216,food=80,drink=200,cit=12))
        ov.o['threats']=dict(visible_hostiles=3,hostiles=[dict(invader=invader)],by_race=dict(BIRD_RAVEN=dict(invader=invader,n=3)),nearest_hostile_dist_to_wagon=121)
        ov.o['military']=dict(squads=[dict(id=1,uniform='leather',armed=4,orders=orders or [])])
        ov.o['burrows']=dict(civilian_alert=False,list=[])
        ov.wildlife=lambda alert,open_play:alert
        ov.thaw=lambda alert,bur:alert
        ov.grow_shelter=lambda bur:None
        ov.place_hatches=lambda:None
        return ov,g
    def test_noninvader_ravens_do_not_launch_pursuit(self):
        ov,g=self.state();ov.defend();self.assertEqual(g.tools('squad_order'),[])
    def test_existing_wildlife_pursuit_is_recalled(self):
        ov,g=self.state([dict(order='attack')]);ov.defend()
        self.assertEqual(g.tools('squad_order'),[dict(order='stand_down')])
    def test_known_invader_still_receives_attack_order(self):
        ov,g=self.state(invader=True);ov.defend()
        self.assertEqual(g.tools('squad_order'),[dict(order='attack')])
    def test_aggregate_preserves_invader_response_when_list_is_capped(self):
        ov,g=self.state();ov.o['threats']['by_race']['GOBLIN']=dict(invader=True,n=2);ov.defend()
        self.assertEqual(g.tools('squad_order'),[dict(order='attack')])
    def test_laboratory_response_is_retained(self):
        ov,g=self.state();ov.hands_off=20;ov.lab=True;ov.defend()
        self.assertEqual(g.tools('squad_order'),[dict(order='attack')])
    def test_no_unsupported_attack_on_unclassified_hostile(self):
        ov,g=self.state();ov.o['threats'].pop('hostiles');ov.o['threats'].pop('by_race');ov.defend()
        self.assertEqual(g.tools('squad_order'),[])
if __name__=='__main__':unittest.main()
