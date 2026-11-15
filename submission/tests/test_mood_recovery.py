import unittest
from support import bare,overseer
class MoodRecovery(unittest.TestCase):
    def observation(self,day,built=False,suspended=True):
        r=bare(45-day,day,workshops=('Carpenters','Still','Kitchen'),fishing=False)
        r['observation']['moods']=[dict(unit_id=9,mood='Fey',skill='WOODCRAFT')]
        r['observation']['workshops'].append(dict(id=6,type='Craftsdwarfs',x=99,y=94,z=78,built=built,job_details=[dict(job='ConstructBuilding',suspended=suspended)]))
        return r
    def test_suspended_mood_workshop_rebuilt_after_three_days(self):
        ov,g=overseer(self.observation(1));ov.mood();self.assertEqual(g.calls,[])
        ov.load(self.observation(4));ov.count=0;ov.mood()
        self.assertEqual(g.tools('build_workshop'),[dict(type='Craftsdwarfs',site='W1')])
    def test_working_or_built_copy_prevents_recovery(self):
        for built,suspended in ((False,False),(True,True)):
            ov,g=overseer(self.observation(1,built,suspended));ov.load(self.observation(9,built,suspended));ov.mood();self.assertEqual(g.calls,[])
    def test_recovery_remains_bounded(self):
        ov,g=overseer(self.observation(1));ov.built_n['Craftsdwarfs']=3
        ov.load(self.observation(9));ov.mood();self.assertEqual(g.calls,[])
    def test_healthy_second_copy_prevents_rebuild(self):
        ov,g=overseer(self.observation(1));r=self.observation(9)
        r['observation']['workshops'].append(dict(id=8,type='Craftsdwarfs',built=True))
        ov.load(r);ov.mood();self.assertEqual(g.calls,[])
    def test_claimed_mood_never_requests_replacement(self):
        ov,g=overseer(self.observation(1));r=self.observation(9)
        r['observation']['moods'][0]['claimed_building_id']=6
        ov.load(r);ov.mood();self.assertEqual(g.calls,[])
if __name__=='__main__':unittest.main()
