import copy,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.year import YearOverseer
from overseer.frontier import Overseer as Frontier
class YearWaterAccess(unittest.TestCase):
 def setUp(self):self.f=json.loads((Path(__file__).parent/'fixtures/public2009-initial-water-map.json').read_text())
 def policy(self):
  g=Mock();g.query.return_value=self.f['response'];o=YearOverseer(g,goal='',days=336);o.surface=self.f['surface'];o.sites=copy.deepcopy(self.f['stairs']);o.o={};return g,o
 def test_observed_water_selects_farther_offered_site(self):
  g,o=self.policy();before=copy.deepcopy(o.sites);self.assertEqual(o.water_aware_year_stair_site(o.sites)['id'],'S3');self.assertEqual(o.sites,before);self.assertEqual(g.query.call_args.kwargs['z2'],82)
 def test_original_dig_receives_selected_site_and_order_restores(self):
  g,o=self.policy();original=o.sites;seen=[]
  with patch.object(Frontier,'digging',lambda s:seen.append(s.kind('S')[-1]['id'])):o.digging()
  self.assertEqual(seen,['S3']);self.assertIs(o.sites,original)
 def test_original_list_restores_after_action_exception(self):
  g,o=self.policy();original=o.sites
  with patch.object(Frontier,'digging',side_effect=RuntimeError('action failed')):
   with self.assertRaises(RuntimeError):o.digging()
  self.assertIs(o.sites,original)
 def test_no_query_when_short_horizon_or_gate_closed_or_no_shaft_needed(self):
  for state in ('short','gate','rooms','done'):
   g,o=self.policy()
   if state=='short':o.days=216
   if state=='gate':o.last['stairs']=o.now
   if state=='done':o.done.add('stairs')
   if state=='rooms':o.sites.extend([{'id':'R1','kind':'R','soil':True},{'id':'R2','kind':'R'}])
   with patch.object(Frontier,'digging') as inherited:o.digging();inherited.assert_called_once_with()
   g.query.assert_not_called()
 def test_missing_water_malformed_and_failure_keep_default(self):
  for response in ({'result':{'liquid':[]}},{'result':None},{'result':{'liquid':[{'depth':7}]}}):
   g,o=self.policy();g.query.return_value=response;self.assertIs(o.water_aware_year_stair_site(o.sites),o.sites[-1])
  g,o=self.policy();g.query.side_effect=RuntimeError('map unavailable');self.assertIs(o.water_aware_year_stair_site(o.sites),o.sites[-1])
if __name__=='__main__':unittest.main()
