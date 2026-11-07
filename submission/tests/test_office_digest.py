import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from plain.digest import _manager
class OfficeDigest(unittest.TestCase):
 def make(self):
  obs=json.loads((Path(__file__).parent/'fixtures/repaired-year-office-observation.json').read_text())['observation'];return {'obs':obs,'citizens':len(obs['dwarves']),'next':[]}
 def test_actual_first_office_false_does_not_hide_valid_owned_office(self):
  c=self.make();before=copy.deepcopy(c['obs']);text=_manager(c)
  self.assertIn('chair=NO',text);self.assertIn('owned office zone',text);self.assertTrue(c['office_ok']);self.assertEqual(c['next'],[]);self.assertEqual(c['obs'],before)
 def test_planned_chair_does_not_suppress_repair(self):
  c=self.make()
  for z in c['obs']['zones']:
   if z.get('type')=='Office':z['furniture']={};z['furniture_planned']={'chair':1}
  _manager(c);self.assertFalse(c['office_ok']);self.assertTrue(c['next'])
 def test_other_managers_chair_does_not_suppress_repair(self):
  c=self.make()
  for z in c['obs']['zones']:
   if z.get('type')=='Office' and z.get('furniture',{}).get('chair',0)>0:z['owner']+=1
  _manager(c);self.assertFalse(c['office_ok']);self.assertTrue(c['next'])
 def test_no_reported_office_can_still_show_an_owned_chaired_one(self):
  c=self.make();c['obs']['administrators']['manager_office']='none';text=_manager(c);self.assertTrue(c['office_ok']);self.assertIn('none reported',text);self.assertNotIn('REQUIRED',text);self.assertEqual(c['next'],[])
