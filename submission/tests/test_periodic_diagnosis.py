"""Consultation bounds must leave routine control and game time progressing."""
import io,json,unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from plain.harness import Plain
class Game:
 def __init__(self,horizon=20):self.day=0;self.horizon=horizon;self.last=self.response();self.calls=[]
 def response(self):return {'day':self.day,'tick':self.day*1200,'days_left':max(0,self.horizon-self.day),'game_over':self.day>=self.horizon,'observation':{'administrators':{'citizens':7},'stocks':{'food_edible':100},'moods':[]}}
 def observe(self):self.last=self.response();return self.last
 def act(self,n,a):
  self.calls.append((self.day,n,a))
  if n=='advance_days':self.day=min(self.horizon,self.day+a['days'])
  self.last={**self.response(),'ok':True};return self.last
class Guard:
 def __init__(self):self.o={};self.st={};self.cit=7;self.surge=False;self.placed={};self.owned=set();self.report=[];self.days=[];self.end=False
 def step(self,r):self.days.append(r['day']);self.o=r['observation'];self.st=self.o.get('stocks',{});return 0
 def in_endgame(self):return self.end
class Periodic(unittest.TestCase):
 def setUp(self):
  c=redirect_stdout(io.StringIO());c.__enter__();self.addCleanup(c.__exit__,None,None,None)
 def make(self):
  g=Game();task=SimpleNamespace(task={'days':20},days=20,credits=1);m=SimpleNamespace(usage={'cost_usd':0})
  p=Plain(task,g,m);p.guard=Guard();return p,g
 def test_unloaded_controller_observation_does_not_break_scheduler(self):
  from overseer.harness import Overseer
  p,g=self.make();p.guard=Overseer(g);self.assertTrue(p.model_ready({'day':0}))
  p.record_model_attempt({'day':0});self.assertFalse(p.model_ready({'day':1}));self.assertEqual(p.cadence_days({'day':100,'observation':{}}),2)
 def test_consultation_accepts_at_most_three_attempts_same_day(self):
  p,g=self.make();r={'day':0}
  for _ in range(3):self.assertTrue(p.model_ready(r));p.record_model_attempt(r)
  self.assertFalse(p.model_ready(r))
 def test_model_advance_closes_batch_until_interval(self):
  p,g=self.make();p.record_model_attempt({'day':0})
  self.assertFalse(p.model_ready({'day':1}));self.assertFalse(p.model_ready({'day':13}));self.assertTrue(p.model_ready({'day':14}))
 def test_visible_mood_shortens_interval_to_four_days(self):
  p,g=self.make();p.record_model_attempt({'day':0});p.guard.o={'moods':[{'mood':'Fey'}]}
  self.assertFalse(p.model_ready({'day':3}));self.assertTrue(p.model_ready({'day':4}))
 def test_new_batch_resets_attempts_and_rewound_clock_can_recover(self):
  p,g=self.make()
  for _ in range(3):p.record_model_attempt({'day':0})
  p.record_model_attempt({'day':14});self.assertEqual(p.consult_calls,1)
  self.assertTrue(p.model_ready({'day':1}));p.record_model_attempt({'day':1});self.assertEqual(p.consult_calls,1)
 def test_unknown_or_boolean_day_preserves_model_availability(self):
  p,g=self.make();p.record_model_attempt({'day':0})
  for day in [None,True,'1',1.5]:self.assertTrue(p.model_ready({'day':day}))
 def test_cadence_advance_preserves_critical_food_and_hands_off_pacing(self):
  p,g=self.make();p.guard.end=True;p.guard.st={'food_edible':27};p.guard.cit=7
  self.assertEqual(p.cadence_days({'day':100,'observation':{}}),1)
  p.guard.st={};self.assertEqual(p.cadence_days({'day':100,'observation':{}}),2)
  self.assertEqual(p.cadence_days({'day':100,'hands_off_in_days':3,'observation':{}}),1)
 def test_moods_and_hostiles_get_daily_control_between_consultations(self):
  p,g=self.make()
  for o in [{'moods':[{}]},{'threats':{'visible_hostiles':1}}]:p.guard.o=o;self.assertEqual(p.cadence_days({'day':100,'observation':{}}),1)
 def run_fake(self,advance):
  p,g=self.make();seen=[]
  def setup():p.tool_names={'enable_automation','advance_days'};p.messages=[{'role':'system','content':'test'}];p.extra={};p.tools=[]
  p.setup=setup;p.user_message=lambda r,o:'observation'
  def chat():
   seen.append(g.day);name='advance_days' if advance else 'enable_automation';args={'days':1} if advance else {'name':'autochop'}
   return {'role':'assistant','tool_calls':[{'id':str(len(seen)),'function':{'name':name,'arguments':json.dumps(args)}}]}
  p.chat=chat;p.run();return p,g,seen
 def test_full_loop_progresses_to_horizon_without_repeated_model_advances(self):
  p,g,seen=self.run_fake(False);self.assertEqual(g.day,20);self.assertEqual(seen,[0,0,0,14,14,14]);self.assertGreaterEqual(len(p.guard.days),10);self.assertGreater(p.stats['cadence_advances'],0)
 def test_full_loop_advance_ends_model_batch_but_keeps_daily_layer(self):
  p,g,seen=self.run_fake(True);self.assertEqual(g.day,20);self.assertEqual(seen,[0,14]);self.assertGreaterEqual(len(p.guard.days),10)
if __name__=='__main__':unittest.main()
