import unittest
from support import overseer,resp

class DiningGate(unittest.TestCase):
    def setUp(self):
        self.ov,self.g=overseer(resp(100,116,60,cit=10))
        self.site=dict(id='A1',kind='A',x=10,y=10,z=80,w=10,h=10,open_tiles=20,subterranean=True)
        self.ov.sites=[self.site]
    def call(self,key='zone',**extra):
        return self.ov.act(key,'make_zone',dict(kind='dining_hall',site='A1',**extra),retry=0)
    def test_direct_fallback_write_blocked(self):
        self.ov.zones=[dict(id=1,type='DiningHall',x=10,y=10,z=80,w=3,h=3)]
        self.assertIsNone(self.call());self.assertEqual(self.g.tools('make_zone'),[])
    def test_same_pass_second_write_blocked(self):
        self.assertTrue(self.call()['ok']);self.assertIsNone(self.call('second'))
        self.assertEqual(len(self.g.tools('make_zone')),1)
    def test_disjoint_same_pass_second_write_allowed(self):
        self.call();self.ov.sites.append(dict(self.site,id='A2',z=79))
        self.ov.act('second','make_zone',dict(kind='dining_hall',site='A2'),retry=0)
        self.assertEqual(len(self.g.tools('make_zone')),2)
    def test_explicit_failure_does_not_reserve_rectangle(self):
        self.g.refuse.add(('make_zone',None));self.assertFalse(self.call()['ok'])
        self.g.refuse.clear();self.assertTrue(self.call('second')['ok'])
        self.assertEqual(len(self.g.tools('make_zone')),2)
    def test_lost_answer_keeps_rectangle_reserved(self):
        original=self.g.act
        def lost(tool,args):original(tool,args);raise RuntimeError('lost response')
        self.g.act=lost
        with self.assertRaises(RuntimeError):self.call()
        self.g.act=original;self.assertIsNone(self.call('second'))
        self.assertEqual(len(self.g.tools('make_zone')),1)
    def test_explicit_action_limit_does_not_reserve_rectangle(self):
        from dfbench_client import ActionLimit
        original=self.g.act
        def limited(tool,args):raise ActionLimit('daily limit',body=dict(error_code='action_limit'))
        self.g.act=limited
        with self.assertRaises(ActionLimit):self.call()
        self.g.act=original;self.assertTrue(self.call('second')['ok'])
    def test_unknown_site_not_sent(self):
        self.ov.sites=[];self.assertIsNone(self.call());self.assertEqual(self.g.calls,[])
    def test_actual_clipped_dimensions_checked(self):
        self.ov.sites=[dict(self.site,x=0,y=0,w=40,h=30)]
        self.ov.zones=[dict(id=1,type='DiningHall',x=30,y=0,z=80,w=3,h=3)]
        self.assertTrue(self.call(w=20,h=20)['ok'])
    def test_capped_zone_listing_blocks_new_write(self):
        self.ov.o['zones_total']=201;self.assertIsNone(self.call());self.assertEqual(self.g.calls,[])
    def test_legacy_rezone_routes_cannot_bypass_gate(self):
        self.ov.zones=[dict(id=1,type='DiningHall',x=10,y=10,z=80,w=3,h=3)]
        self.ov.o['furniture']=[dict(id=10,kind='table',built=True,x=15,y=15,z=80,zone_ids=[]),dict(id=11,kind='chair',built=True,x=16,y=15,z=80,zone_ids=[])]
        self.ov.rezone();self.assertEqual(self.g.tools('make_zone'),[])

class DiningPairs(unittest.TestCase):
    def setUp(self):self.ov,self.g=overseer(resp(100,116,60,cit=10))
    def add_hall(self,zid,tables,chairs):
        rows=self.ov.o.setdefault('furniture',[]);ids=[]
        for kind,n in [('table',tables),('chair',chairs)]:
            for _ in range(n):
                bid=len(rows)+1;ids.append(bid);rows.append(dict(id=bid,kind=kind,built=True,zone_ids=[zid],x=bid,y=1,z=zid))
        self.ov.zones.append(dict(id=zid,type='DiningHall',x=0,y=0,z=zid,w=20,h=20,building_ids=ids,furniture=dict(table=tables,chair=chairs)))
    def test_surplus_types_in_different_halls_do_not_pair(self):
        self.add_hall(1,3,1);self.add_hall(2,1,3)
        self.assertEqual(self.ov.real_seats(),2)
    def test_complete_disjoint_pairs_add(self):
        self.add_hall(1,2,2);self.add_hall(2,3,3)
        self.assertEqual(self.ov.real_seats(),5)
    def test_shared_members_count_once(self):
        self.add_hall(1,2,2);self.ov.zones.append(dict(self.ov.zones[0],id=2))
        for row in self.ov.o['furniture']:row['zone_ids'].append(2)
        self.assertEqual(self.ov.real_seats(),2)
    def test_planned_pairs_not_built_seats(self):
        self.add_hall(1,1,1);self.ov.o['furniture'][1]['built']=False
        self.assertEqual(self.ov.real_seats(),0);self.assertEqual(self.ov.dining_pairs(),1)
    def test_capped_disjoint_summaries_add_pairs(self):
        self.add_hall(1,3,3);self.add_hall(2,2,2);self.ov.o['furniture']=[];self.ov.o['furniture_total']=100
        self.assertEqual(self.ov.real_seats(),5)
    def test_capped_overlapping_summaries_not_doubled(self):
        self.add_hall(1,3,3);self.ov.zones.append(dict(self.ov.zones[0],id=2))
        self.ov.o['furniture']=[];self.ov.o['furniture_total']=100
        self.assertEqual(self.ov.real_seats(),3)
    def test_unusable_surplus_does_not_block_item_orders(self):
        self.add_hall(1,10,0);self.ov.free=dict(table=3,chair=4)
        self.assertEqual(self.ov.dine_stock('table',None),3)
        self.assertEqual(self.ov.dine_stock('chair',None),4)
    def test_local_nonmembers_count_toward_pair_inputs(self):
        site=dict(x=0,y=0,z=3,w=10,h=10)
        self.ov.o['furniture']=[dict(id=1,kind='table',built=True,zone_ids=[],x=1,y=1,z=3),dict(id=2,kind='chair',built=False,zone_ids=[],x=2,y=1,z=3)]
        self.assertEqual(self.ov.dining_local(site),dict(table=1,chair=1))

class MatchedPlacement(unittest.TestCase):
    def setUp(self):
        self.ov,self.g=overseer(resp(100,116,60,cit=10))
        self.site=dict(id='A1',kind='A',x=10,y=10,z=80,w=10,h=10,open_tiles=20,subterranean=True)
        self.ov.sites=[self.site];self.ov.room_for=lambda role:self.site if role=='dine'else None
        self.ov.dine_site=lambda:self.site;self.ov.free=dict(table=3,chair=3)
        self.orig=self.g.act;self.n=0
        def place(tool,args):
            ret=self.orig(tool,args)
            if tool=='place_furniture':
                self.n+=1;ret['result']['at']=[10+self.n,11,80]
            return ret
        self.g.act=place
    def test_interleaves_real_pairs(self):
        self.ov.furnish()
        self.assertEqual([a['kind']for a in self.g.tools('place_furniture')],['table','chair']*3)
        self.assertEqual(len(self.g.tools('make_zone')),1)
    def test_no_chairs_only_new_hall_when_tables_missing(self):
        self.ov.free=dict(table=0,chair=5);self.ov.furnish()
        self.assertEqual(self.g.tools('place_furniture'),[]);self.assertEqual(self.g.tools('make_zone'),[])
    def test_one_free_floor_failure_never_zones_zero_pairs(self):
        real=self.g.act
        def one(tool,args):
            if tool=='place_furniture'and args['kind']=='chair':
                self.orig(tool,args);return dict(ok=False,error_code='no_space')
            return real(tool,args)
        self.g.act=one;self.ov.furnish()
        self.assertEqual(len(self.g.tools('place_furniture')),2)
        self.assertEqual(self.g.tools('make_zone'),[])

if __name__=='__main__':unittest.main()
