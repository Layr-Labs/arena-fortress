import unittest
from support import overseer,resp
class BatchDining(unittest.TestCase):
    def state(self,pairs=1):
        ov,g=overseer(resp(100,116,food=80,drink=200,cit=20))
        plan=dict(id='R8',kind='R',x=80,y=80,z=76,w=3,h=7,soil=False,dug=True)
        ov.sites=[dict(plan,w=3,h=3)];ov.dining_expansions['R8']=plan
        rows=[]
        for i in range(pairs*2):
            rows.append(dict(id=100+i,kind='table'if i%2==0 else'chair',x=80+i%3,y=80+i//3,z=76,built=True,zone_ids=[]))
        ov.o['furniture']=rows
        return ov,g,plan
    def request(self,ov,**kw):
        return ov.act('batch_zone','make_zone',dict(kind='dining_hall',site='R8',w=3,h=7,**kw),retry=0)
    def test_first_pair_does_not_freeze_underfilled_extra_room(self):
        ov,g,p=self.state(1);self.assertIsNone(self.request(ov));self.assertEqual(g.calls,[])
        self.assertEqual(ov.dining_created,[]);self.assertNotIn('batch_zone',ov.tries)
    def test_nine_built_pairs_commit_one_complete_room(self):
        ov,g,p=self.state(9);self.assertTrue(self.request(ov)['ok']);self.assertEqual(len(g.calls),1)
        ov.act('other_key','make_zone',dict(kind='dining_hall',site='R8',w=3,h=7),retry=0)
        self.assertEqual(len(g.calls),1)
    def test_legacy_small_box_cannot_commit_partial_room(self):
        ov,g,p=self.state(9);self.assertIsNone(ov.act('legacy','make_zone',dict(kind='dining_hall',site='R8'),retry=0))
        self.assertEqual(g.calls,[])
    def test_unbuilt_furniture_does_not_satisfy_target(self):
        ov,g,p=self.state(9);ov.o['furniture'][-1]['built']=False
        self.assertIsNone(self.request(ov));self.assertEqual(g.calls,[])
    def test_full_floor_with_finished_partial_batch_can_commit(self):
        ov,g,p=self.state(3);ov.dine_full['R8']=ov.fill_mark(p)
        self.assertTrue(self.request(ov)['ok'])
    def test_last_three_days_commit_observed_built_pairs(self):
        ov,g,p=self.state(2);ov.days_left=3
        self.assertTrue(self.request(ov)['ok'])
    def test_wait_does_not_delay_late_commit_by_recheck_interval(self):
        ov,g,p=self.state(2)
        args=dict(kind='dining_hall',site='R8',w=3,h=7)
        self.assertIsNone(ov.act('same','make_zone',args,retry=8))
        ov.now+=1200;ov.days_left=3
        self.assertTrue(ov.act('same','make_zone',args,retry=8)['ok'])
    def test_ordinary_initial_dining_policy_is_unchanged(self):
        ov,g,p=self.state(1);ov.dining_expansions.clear()
        self.assertTrue(self.request(ov)['ok'])
if __name__=='__main__':unittest.main()
