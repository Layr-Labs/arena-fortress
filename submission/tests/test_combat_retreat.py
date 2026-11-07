import contextlib,copy,io,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.year import YearOverseer, DAY
class G:
 def __init__(self):self.calls=[]
 def act(self,t,a):self.calls.append((t,a));return {"ok":True,"result":{}}
class CombatRetreat(unittest.TestCase):
 def make(self):
  g=G();o=YearOverseer(g,days=336);r=json.loads((Path(__file__).parent/'fixtures/early-combat-observation.json').read_text());o.load(r);o.count=0;return g,o
 def test_actual_zero_danger_combat_gets_short_retreat(self):
  g,o=self.make()
  self.assertEqual(o.o['threats']['visible_hostiles'],0)
  with contextlib.redirect_stdout(io.StringIO()):o.defend()
  self.assertIn(('civilian_alert',{'on':True}),g.calls)
  self.assertEqual(o.combat_retreat_until,o.now+2*DAY)
 def test_retreat_expires_and_stale_events_do_not_reactivate(self):
  g,o=self.make()
  with contextlib.redirect_stdout(io.StringIO()):
   o.defend();o.o['burrows']['civilian_alert']=True;o.now+=2*DAY;g.calls=[];o.defend()
  self.assertIn(('civilian_alert',{'on':False}),g.calls)
  self.assertNotIn(('civilian_alert',{'on':True}),g.calls)
  self.assertIsNone(o.combat_retreat_until)
 def test_low_reserves_do_not_start_retreat(self):
  g,o=self.make();o.st['drink']=30
  with contextlib.redirect_stdout(io.StringIO()):o.defend()
  self.assertNotIn(('civilian_alert',{'on':True}),g.calls)
 def test_report_without_combat_does_not_start_retreat(self):
  g,o=self.make();o.o['recent_events']=['It has started raining.']
  with contextlib.redirect_stdout(io.StringIO()):o.defend()
  self.assertNotIn(('civilian_alert',{'on':True}),g.calls)
