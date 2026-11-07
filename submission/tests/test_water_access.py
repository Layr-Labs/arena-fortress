import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer
class MapGame:
 def __init__(self,response):self.response=response;self.calls=[]
 def query(self,name,**args):self.calls.append((name,args));return self.response
class WaterAccess(unittest.TestCase):
 def setUp(self):
  self.fixture=json.loads((Path(__file__).parent/'fixtures/public2009-initial-water-map.json').read_text())
 def policy(self,response=None,hands=39):
  g=MapGame(self.fixture['response'] if response is None else response);o=Overseer(g,goal='Migrants are arriving',days=60);o.surface=self.fixture['surface'];o.hands_left=hands;return g,o
 def test_captured_pre_dig_water_avoids_actual_flooded_column(self):
  g,o=self.policy();before=copy.deepcopy(self.fixture);chosen=o.water_aware_stair_site(self.fixture['stairs']);self.assertEqual(chosen['id'],'S3');self.assertIn(chosen,self.fixture['stairs']);self.assertEqual(self.fixture,before);self.assertEqual(g.calls[0][0],'map');self.assertEqual(g.calls[0][1]['z2'],82)
 def test_open_play_does_not_query_or_change_legacy_choice(self):
  for hands in (None,0,-1,True):
   g,o=self.policy(hands=hands);self.assertEqual(o.water_aware_stair_site(self.fixture['stairs']),self.fixture['stairs'][-1]);self.assertFalse(g.calls)
 def test_no_water_and_malformed_results_keep_legacy_choice(self):
  for response in ({'result':{'liquid':[]}},{'result':None},{'result':{'liquid':[{'depth':7}]}}):
   g,o=self.policy(response);self.assertEqual(o.water_aware_stair_site(self.fixture['stairs']),self.fixture['stairs'][-1])
 def test_query_failure_keeps_legacy_choice(self):
  g,o=self.policy()
  def unavailable(*args,**kwargs):raise RuntimeError('unavailable')
  g.query=unavailable;self.assertEqual(o.water_aware_stair_site(self.fixture['stairs']),self.fixture['stairs'][-1])
if __name__=='__main__':unittest.main()
