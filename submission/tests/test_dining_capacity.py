import io,unittest
from contextlib import redirect_stdout
from overseer.harness import Overseer

class Game:
    def __init__(self,error=None):self.calls=[];self.error=error
    def act(self,name,args):
        self.calls.append((name,args))
        if name=='place_furniture':
            if self.error:return {'ok':False,'error_code':self.error}
            return {'ok':True,'result':{'at':[[21,21,9]]}}
        return {'ok':True,'result':{'order_id':len(self.calls)}}

class DiningCapacity(unittest.TestCase):
    def make(self,error=None):
        g=Game(error);o=Overseer(g);o.count=0
        sites=[{'id':'A1','kind':'A','x':0,'y':0,'z':9,'w':45,'h':38,'open_tiles':120},
               {'id':'R1','kind':'R','x':20,'y':20,'z':9,'w':3,'h':3,'dug':True},
               {'id':'R2','kind':'R','x':30,'y':20,'z':9,'w':3,'h':3,'dug':True},
               {'id':'R3','kind':'R','x':40,'y':20,'z':9,'w':3,'h':3,'dug':True,'used_by':['farm plot 7']}]
        o.load({'day':180,'tick':216000,'observation':{'map':{'sites':sites},'administrators':{'citizens':10},
            'stocks':{'tables':8,'chairs':8,'logs_usable':20,'furniture_free':{'table':2,'chair':2}},
            'orders':[],'zones':[],'furniture':[]}})
        return g,o
    def test_oversized_area_and_occupied_farms_are_not_dining_candidates(self):
        g,o=self.make()
        self.assertEqual([s['id'] for s in o.dining_sites(o.kind('A')[0])],['R1','R2'])
    def test_outside_chairs_do_not_satisfy_dining_and_overlap_counts_each_item_once(self):
        g,o=self.make();z={'id':1,'type':'DiningHall','x':20,'y':20,'z':9,'w':3,'h':3}
        o.zones=[z,{**z,'id':2}]
        o.o['furniture']=[{'kind':'chair','x':21,'y':21,'z':9},{'kind':'chair','x':25,'y':21,'z':9}]
        self.assertEqual(o.dining_items('chair'),1)
        o.standing=lambda recipe:True
        with redirect_stdout(io.StringIO()):o.supply()
        recipes=[a['recipe'] for n,a in g.calls if n=='add_order']
        self.assertIn('make_table',recipes);self.assertIn('make_chair',recipes)
    def test_small_room_reserves_capacity_for_both_halves_of_a_seat(self):
        g,o=self.make();o.free={'table':10,'chair':10}
        with redirect_stdout(io.StringIO()):o.furnish()
        calls=[a for n,a in g.calls if n=='place_furniture']
        self.assertEqual([(a['kind'],a['site'],a['count']) for a in calls],[('table','R1',4),('chair','R1',4)])
        self.assertTrue(any(n=='make_zone' and a['site']=='R1' for n,a in g.calls))
    def test_missing_material_does_not_search_other_dining_rooms(self):
        g,o=self.make('no_material')
        with redirect_stdout(io.StringIO()):o.furnish()
        self.assertEqual([a['site'] for n,a in g.calls if n=='place_furniture'],['R1','R1'])
    def test_no_space_can_try_another_observed_bounded_room(self):
        g,o=self.make('no_space')
        with redirect_stdout(io.StringIO()):o.furnish()
        self.assertEqual([a['site'] for n,a in g.calls if n=='place_furniture'],['R1','R2','R1','R2'])
    def test_unpaired_tables_in_other_zones_do_not_block_a_new_usable_pair(self):
        g,o=self.make();o.cit=22
        o.zones=[{'id':1,'type':'DiningHall','x':20,'y':20,'z':9,'w':3,'h':3,'furniture':{'table':4,'chair':3}},
                 {'id':2,'type':'DiningHall','x':100,'y':100,'z':9,'w':12,'h':3,'furniture':{'table':8,'chair':6}}]
        o.o['furniture']=[{'kind':k,'x':20+i%3,'y':20+i//3,'z':9}
                          for k,n in [('table',4),('chair',3)] for i in range(n)]
        o.o['furniture'] += [{'kind':k,'x':100+i,'y':100,'z':9}
                            for k,n in [('table',8),('chair',6)] for i in range(n)]
        o.placed={'table':12,'chair':12};o.st.update(tables=14,chairs=14)
        o.standing=lambda recipe:True
        original=g.act
        def act(name,args):
            if name=='place_furniture' and args['site']=='R1':
                g.calls.append((name,args));return {'ok':False,'error_code':'no_space'}
            return original(name,args)
        g.act=act
        with redirect_stdout(io.StringIO()):o.supply();o.furnish()
        self.assertEqual(o.seats(),9)
        self.assertEqual(o.dining_items('table'),12)
        self.assertEqual([(a['kind'],a['count']) for n,a in g.calls if n=='place_furniture' and a['site']=='R2'],
                         [('table',2),('chair',2)])
    def test_rooms_already_at_their_furniture_quota_do_not_exhaust_the_action_search(self):
        g,o=self.make();o.cit=50;o.sites=[];o.o['furniture']=[]
        for i in range(5):
            room={'id':'R'+str(i+1),'kind':'R','x':20+i*10,'y':20,'z':9,'w':3,'h':3,'dug':True}
            o.sites.append(room)
            if i<4:
                o.o['furniture'] += [{'kind':kind,'x':room['x']+j%3,'y':20+j//3,'z':9}
                                     for kind in ('table','chair') for j in range(4)]
        with redirect_stdout(io.StringIO()):o.furnish()
        self.assertEqual([a['site'] for n,a in g.calls if n=='place_furniture'],['R5','R5'])
