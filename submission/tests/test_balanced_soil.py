"""Do not exhaust advertised soil rooms on crops while farms are committed."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer

class API:
    def __init__(self): self.calls=[]
    def act(self,tool,args):
        self.calls.append((tool,args))
        return {'ok':True,'result':{}}

class BalancedSoil(unittest.TestCase):
    def allocate(self,nplots,roles):
        api=API(); layer=Overseer(api);layer.count=0;layer.roles=dict(roles)
        layer.load({'tick':0,'observation':{'administrators':{'citizens':30},
            'farm_plots':[{'id':i,'built':True} for i in range(nplots)],
            'map':{'surface_z':10,'sites':[{'id':'R9','kind':'R','soil':True,
                'x':10,'y':10,'z':9,'w':3,'h':3,'dug':False,'free':True}]}}})
        with contextlib.redirect_stdout(io.StringIO()):layer.digging()
        return layer,api
    def test_four_plots_reserve_a_dorm(self):
        layer,api=self.allocate(4,{'R1':'office'})
        self.assertEqual(layer.roles['R9'],'dorm')
        self.assertGreater(api.calls[0][1]['w'],3)
    def test_three_plots_reserve_clear_housing(self):
        layer,_=self.allocate(3,{'R1':'office'})
        self.assertEqual(layer.roles['R9'],'dorm')
    def test_two_built_and_two_committed_reserve_dorm(self):
        layer,api=self.allocate(2,{'R1':'office','R2':'farm','R3':'farm'})
        self.assertEqual(layer.roles['R9'],'dorm')
        self.assertGreater(api.calls[0][1]['w'],3)
    def test_anonymous_farm_cannot_consume_expanded_dorm(self):
        layer,api=self.allocate(2,{'R1':'office','R2':'farm','R3':'farm'})
        layer.sites=[{'id':'F1','kind':'F','x':13,'y':10,'z':9,'w':3,'h':3},
                     {'id':'F2','kind':'F','x':50,'y':50,'z':9,'w':3,'h':3}]
        with contextlib.redirect_stdout(io.StringIO()):layer.farms()
        self.assertEqual([a['site'] for t,a in api.calls if t=='build_farm'],['F2'])
    def test_dining_does_not_fill_reserved_housing(self):
        layer,_=self.allocate(2,{'R1':'office','R2':'farm','R3':'farm'})
        area=layer.room_reservations['R9'];layer.room_for=lambda role:area
        layer.free={'bed':0,'table':20,'chair':20};layer.placed={'bed':2}
        layer.needs_zone=lambda *args:False
        calls=[];layer.place=lambda *args:calls.append(args) or []
        layer.furnish()
        self.assertEqual(calls,[])
    def test_bed_surplus_does_not_release_dorm_to_dining(self):
        layer,_=self.allocate(4,{'R1':'office'})
        area=layer.room_reservations['R9'];layer.room_for=lambda role:area
        layer.free={'bed':0,'table':20,'chair':20};layer.placed={'bed':20}
        layer.needs_zone=lambda *args:False
        calls=[];layer.place=lambda *args:calls.append(args) or []
        layer.furnish()
        self.assertEqual(calls,[])

    def test_two_plots_keep_food_priority(self):
        layer,_=self.allocate(2,{'R1':'office'})
        self.assertEqual(layer.roles['R9'],'farm')
    def test_dorm_does_not_expand_into_committed_room(self):
        api=API();layer=Overseer(api);layer.count=0
        layer.roles={'R1':'office','R2':'farm'}
        rooms=[{'id':'R2','kind':'R','soil':True,'x':13,'y':10,'z':9,'w':3,'h':3,'dug':True},
               {'id':'R9','kind':'R','soil':True,'x':10,'y':10,'z':9,'w':3,'h':3,'dug':False}]
        layer.load({'tick':0,'observation':{'administrators':{'citizens':30},
                   'farm_plots':[{'id':1},{'id':2}], 'map':{'surface_z':10,'sites':rooms}}})
        with contextlib.redirect_stdout(io.StringIO()):layer.digging()
        self.assertNotEqual(layer.roles.get('R9'),'dorm')
    def test_reserved_dorm_level_is_not_committed_to_farms(self):
        layer,api=self.allocate(3,{'R1':'office'})
        layer.sites.append({'id':'R10','kind':'R','soil':True,'x':6,'y':10,'z':9,'w':3,'h':3,'dug':False})
        with contextlib.redirect_stdout(io.StringIO()):layer.digging()
        self.assertNotIn('R10',layer.roles)
    def test_full_dorm_allows_disjoint_replacement_on_its_level(self):
        layer,api=self.allocate(3,{'R1':'office'})
        old=dict(layer.room_reservations['R9'])
        layer.roles['R8']='dine'
        layer.full['R9']=layer.now
        layer.sites[0]['dug']=True
        layer.sites.append({'id':'R10','kind':'R','soil':True,'x':0,'y':10,
                            'z':9,'w':3,'h':3,'dug':False,'free':True})
        with contextlib.redirect_stdout(io.StringIO()):layer.digging()
        self.assertEqual(layer.roles.get('R10'),'dorm')
        self.assertEqual(layer.room_reservations['R9'],old)

    def test_full_dorm_does_not_allow_overlapping_replacement(self):
        layer,api=self.allocate(3,{'R1':'office'})
        layer.roles['R8']='dine'
        layer.full['R9']=layer.now
        layer.sites[0]['dug']=True
        layer.sites.append({'id':'R10','kind':'R','soil':True,'x':12,'y':10,
                            'z':9,'w':3,'h':3,'dug':False,'free':True})
        with contextlib.redirect_stdout(io.StringIO()):layer.digging()
        self.assertNotIn('R10',layer.roles)

    def test_missing_dining_does_not_block_full_dorm_replacement(self):
        layer,api=self.allocate(4,{'R1':'office'})
        layer.full['R9']=layer.now
        layer.sites[0]['dug']=True
        layer.sites[0]['designated']=True
        layer.sites.append({'id':'R10','kind':'R','soil':True,'x':30,'y':10,
                            'z':9,'w':3,'h':3,'dug':False,'free':True})
        self.assertNotIn('dine',layer.roles.values())
        with contextlib.redirect_stdout(io.StringIO()):layer.digging()
        self.assertEqual(layer.roles.get('R10'),'dorm')
        self.assertEqual(api.calls[-1][1]['site'],'R10')

    def test_missing_dining_keeps_waiting_when_dorm_not_full(self):
        layer,api=self.allocate(4,{'R1':'office'})
        layer.sites[0]['dug']=True
        layer.sites[0]['designated']=True
        layer.sites.append({'id':'R10','kind':'R','soil':True,'x':30,'y':10,
                            'z':9,'w':3,'h':3,'dug':False,'free':True})
        with contextlib.redirect_stdout(io.StringIO()):layer.digging()
        self.assertNotIn('R10',layer.roles)

    def test_office_still_first(self):
        layer,_=self.allocate(4,{})
        self.assertEqual(layer.roles['R9'],'office')
    def test_existing_dorm_does_not_suppress_food(self):
        layer,_=self.allocate(4,{'R1':'office','R2':'dorm'})
        self.assertEqual(layer.roles['R9'],'farm')

if __name__=='__main__':unittest.main()
