import contextlib,io,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from plain.harness import Plain
class G:
 last={}
 def __init__(self):self.calls=[]
 def act(self,t,a):self.calls.append((t,a));return {"ok":True}
class RetreatAdvance(unittest.TestCase):
 def make(self,until=2400):
  p=Plain.__new__(Plain);p.guard=SimpleNamespace(combat_retreat_until=until,now=0,o={});p.game=G();p.tool_names={'advance_days'};p.stats={'advances':0};p.tick=lambda:0;p.refuse=lambda *a:None;p.remember=lambda *a:None;p.result=lambda *a:None;return p
 def test_model_seven_day_call_is_clipped_during_retreat(self):
  p=self.make()
  with contextlib.redirect_stdout(io.StringIO()):p.run_call({'function':{'name':'advance_days','arguments':json.dumps({'days':7})}})
  self.assertEqual(p.game.calls,[('advance_days',{'days':1})])
 def test_fallback_is_also_clipped(self):
  p=self.make()
  with contextlib.redirect_stdout(io.StringIO()):p.advance(14,'fallback')
  self.assertEqual(p.game.calls,[('advance_days',{'days':1})])
 def test_inactive_retreat_preserves_model_cadence(self):
  p=self.make(None)
  with contextlib.redirect_stdout(io.StringIO()):p.run_call({'function':{'name':'advance_days','arguments':json.dumps({'days':7})}})
  self.assertEqual(p.game.calls,[('advance_days',{'days':7})])
