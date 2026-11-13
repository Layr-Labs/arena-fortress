import unittest
import test_invader_only as gate_tests
class ScopedDefense(unittest.TestCase):
    def state(self):return gate_tests.InvaderOnly().state()
    def test_known_invader_is_targeted_without_distant_wildlife(self):
        ov,g=self.state();ov.o['threats']['hostiles']=[dict(id=12,invader=True),dict(id=13,invader=False)]
        ov.defend();self.assertEqual(g.tools('squad_order'),[dict(order='attack',target_ids=[12])])
    def test_hostile_inside_the_shelter_still_receives_defensive_response(self):
        ov,g=self.state();ov.o['threats']['hostiles']=[dict(id=12,invader=False,in_shelter=True),dict(id=13,invader=False)]
        ov.defend();self.assertEqual(g.tools('squad_order'),[dict(order='attack',target_ids=[12])])
    def test_duplicate_invader_intruder_id_is_sent_only_once(self):
        ov,g=self.state();ov.o['threats']['hostiles']=[dict(id=12,invader=True,in_shelter=True)]
        ov.defend();self.assertEqual(g.tools('squad_order'),[dict(order='attack',target_ids=[12])])
    def test_laboratory_keeps_original_unscoped_attack_call(self):
        ov,g=self.state();ov.hands_off=20;ov.lab=True;ov.o['threats']['hostiles']=[dict(id=12,invader=True)]
        ov.defend();self.assertEqual(g.tools('squad_order'),[dict(order='attack')])
if __name__=='__main__':unittest.main()
