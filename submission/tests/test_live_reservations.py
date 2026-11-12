"""Same-pass zoning is visible to the row-major safe placement predictor."""
import copy
import io
import sys
import unittest
from pathlib import Path
from contextlib import redirect_stdout
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overseer import harness

SITE = dict(id='A1',kind='A',x=0,y=0,z=9,w=5,h=1,open_tiles=5)
OFFICE = dict(id='R1',kind='R',x=2,y=0,z=9,w=1,h=1,dug=True)
class API:
    def __init__(self): self.calls=[]; self.fail=False
    def act(self,tool,args):
        self.calls.append((tool,copy.deepcopy(args)))
        if self.fail: return dict(ok=False,error_code='no_space')
        if tool=='place_furniture': return dict(ok=True,result=dict(at=[[0,0,9],[1,0,9]],n=2))
        return dict(ok=True,result=dict(at=[2,0,9,1,1],zone='office',zone_id=42))
    def query(self,name,**kw):
        return dict(x1=0,y1=0,levels=[dict(z=9,shape=['.....'],light=['uuuuu'])], buildings=[],liquid=[],designations=[])
class Reservations(unittest.TestCase):
    def setUp(self):
        self.sink=redirect_stdout(io.StringIO());self.sink.__enter__();self.addCleanup(self.sink.__exit__,None,None,None)
        self.api=API();self.o=harness.Overseer(self.api);self.o.count=0
        self.obs=dict(tick=0,observation=dict(administrators=dict(citizens=7),map=dict(sites=[SITE,OFFICE]),zones=[],farm_plots=[]))
        self.o.load(copy.deepcopy(self.obs))
    def test_same_pass_office_stops_prefix_before_any_refresh(self):
        self.assertEqual(self.o.safe_shared_capacity(SITE),5)
        self.o.act('office','make_zone',dict(kind='office',site='R1'))
        self.assertEqual(self.o.safe_shared_capacity(SITE),2)
        self.assertEqual(self.o.zone('office')[0]['id'],42)
    def test_whole_area_dorm_cannot_swallow_new_office(self):
        self.o.act('office','make_zone',dict(kind='office',site='R1'))
        self.assertIsNone(self.o.act('dorm','make_zone',dict(kind='dormitory',site='A1')))
        self.assertEqual(len(self.api.calls),1)
    def test_tables_also_stop_before_new_office(self):
        self.o.act('office','make_zone',dict(kind='office',site='R1'))
        self.o.place('table','table',SITE,12)
        self.assertEqual(self.api.calls[-1][1]['count'],2)
    def test_outdoor_nonbeds_follow_server_scan(self):
        original=self.api.query
        def query(*a,**kw):
            r=original(*a,**kw); r['levels'][0]['light']=['ouuuu']; return r
        self.api.query=query
        self.o.act('office','make_zone',dict(kind='office',site='R1'))
        self.assertEqual(self.o.safe_shared_capacity(SITE,'table'),2)
        self.assertEqual(self.o.safe_shared_capacity(SITE,'bed'),1)
    def test_failed_zone_does_not_reserve(self):
        self.api.fail=True;self.o.act('office','make_zone',dict(kind='office',site='R1'))
        self.assertEqual(self.o.safe_shared_capacity(SITE),5)
    def test_observation_replaces_reservation(self):
        self.o.act('office','make_zone',dict(kind='office',site='R1'))
        self.o.load(copy.deepcopy(self.obs))
        self.assertEqual(self.o.zone('office'),[])
    def test_partial_overlap_farm_blocks_zone(self):
        self.o.o['farm_plots']=[dict(x=4,y=0,z=9,w=3,h=1)]
        self.assertIsNone(self.o.act('dorm','make_zone',dict(kind='dormitory',site='A1')))
        self.assertEqual(self.api.calls,[])
    def test_adjacent_office_does_not_block(self):
        self.o.zones=[dict(x=5,y=0,z=9,w=1,h=1,type='office')]
        self.assertIsNotNone(self.o.act('dorm','make_zone',dict(kind='dormitory',site='A1')))
if __name__=='__main__':unittest.main()
