import contextlib,io,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from overseer.year import YearOverseer,DAY
from overseer.frontier import Overseer as FrontierOverseer
class G:
 def __init__(self):self.calls=[]
 def act(self,t,a):self.calls.append((t,a));return {'ok':True,'result':{}}
class InvasionHandoff(unittest.TestCase):
 def test_observed_invaders_relinquish_temporary_retreat_without_clearing_alert(self):
  g=G();o=YearOverseer(g,days=336);o.load(json.loads((Path(__file__).parent/'fixtures/early-combat-observation.json').read_text()));o.count=0;o.combat_retreat_until=o.now+2*DAY;o.o['burrows']['civilian_alert']=True;o.o['burrows']['list']=[{'civ_alert_burrow':True}];o.o['threats']['hostiles']=[{'invader':True}];o.o['threats']['visible_hostiles']=1
  original=FrontierOverseer.defend
  with patch.object(FrontierOverseer,'defend',autospec=True,side_effect=original) as base,contextlib.redirect_stdout(io.StringIO()):o.defend();base.assert_called_once_with(o)
  self.assertIsNone(o.combat_retreat_until);self.assertEqual(o.alert_since,o.now);self.assertNotIn(('civilian_alert',{'on':False}),g.calls)
