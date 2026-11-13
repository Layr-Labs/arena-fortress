import unittest
from support import overseer, resp, DAY

HERD=[dict(id=i,race=r,tame=True,adult=True,pet_owner_id=-1) for i,r in [(1,'YAK'),(2,'COW'),(3,'HORSE')]]
class EmptyCullCooldown(unittest.TestCase):
    def test_protected_check_does_not_delay_emergency(self):
        ov,g=overseer(resp(24,191,2),herd=HERD)
        self.assertEqual(ov.cull('hunger',1,True,5),0)
        self.assertNotIn('hunger',ov.culled)
        ov.load(resp(22,193,0));ov.count=0
        self.assertEqual(ov.cull('hunger',1,True,5),1)
        self.assertEqual(len(g.tools('slaughter')),1)
        self.assertEqual(ov.culled['hunger'],ov.now)
    def test_success_still_throttles_next_mark(self):
        ov,g=overseer(resp(24,191,0),herd=HERD)
        self.assertEqual(ov.cull('hunger',1,True,5),1)
        ov.load(resp(22,193,0));ov.count=0
        self.assertEqual(ov.cull('hunger',1,True,5),0)
        self.assertEqual(len(g.tools('slaughter')),1)
    def test_empty_herd_does_not_claim_meal(self):
        ov,g=overseer(resp(24,191,2),herd=[])
        self.assertEqual(ov.cull('hunger',1,True,5),0)
        self.assertNotIn('hunger',ov.culled)
    def test_herd_protection_is_unchanged(self):
        ov,g=overseer(resp(24,191,2),herd=HERD)
        self.assertEqual(ov.cull('hunger',1,True,5),0)
        self.assertEqual(g.tools('slaughter'),[])
    def test_refused_marks_do_not_start_cooldown(self):
        ov,g=overseer(resp(24,191,0),herd=HERD,refuse=[('slaughter',i)for i in [1,2,3]])
        self.assertEqual(ov.cull('hunger',1,True,5),0)
        self.assertNotIn('hunger',ov.culled)
        self.assertEqual(len(g.tools('slaughter')),3)

if __name__=='__main__':unittest.main()
