"""Boundary and real-loop integration checks for the managed-window reserve and STATUS."""
import io
import sys
import unittest
from pathlib import Path
from contextlib import redirect_stdout
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer
from plain.harness import Plain, window
from dfbench_client import Task

class Game:
    def __init__(self):
        self.last = {"day": 25, "tick": 30000}
        self.calls = []
    def act(self, name, args):
        self.calls.append((name, args))
        return {"ok": True, "result": {"order_id": 30 + len(self.calls)}}
    def query(self, *a, **kw):
        return {"ok": True, "result": {"units": []}}

class Reserve(unittest.TestCase):
    def state(self, left, pop=46, drink=550):
        return {"day": 25, "tick": 30000, "hands_off_in_days": left, "observation": {
            "administrators": {"citizens": pop}, "stocks": {"drink": drink}, "orders": [
                {"recipe": r, "repeat": "daily"} for r in ("brew_drink", "make_barrel", "cook_meal")]}}
    def agent(self, left, pop=46, drink=550):
        g=Game(); o=Overseer(g); o.load(self.state(left,pop,drink)); o.count=0
        return g,o
    def run_supply(self,o):
        with redirect_stdout(io.StringIO()):o.supply()
    def test_long_game_and_boundaries_do_not_add(self):
        for left,pop,drink in [(None,46,550),(15,46,550),(0,46,550),(-1,46,550),(14,24,550),(14,46,1472)]:
            g,o=self.agent(left,pop,drink);self.run_supply(o);self.assertEqual(g.calls,[])
    def test_window_reserve_is_single_and_protected(self):
        g,o=self.agent(14);self.run_supply(o);self.run_supply(o)
        self.assertEqual(len(g.calls),1)
        name,args=g.calls[0];self.assertEqual(name,'add_order')
        self.assertEqual(args['when'][0],{'stock':'drink','below':1472})
        self.assertEqual(o.brew_orders,{31})
        self.assertEqual(len(o.report),1)
    def test_failed_activation_can_retry_on_later_day(self):
        g,o=self.agent(14)
        real_act=g.act
        def refusal(name,args):
            g.calls.append((name,args))
            return {"ok":False,"error_code":"action_limit"}
        g.act=refusal;self.run_supply(o)
        self.assertFalse(o.window_brew_added)
        self.assertEqual(o.brew_orders,set())
        o.now += 1200;g.act=real_act;self.run_supply(o)
        self.assertTrue(o.window_brew_added)
        self.assertEqual(len(g.calls),2)
    def test_digest_reports_actual_controller_action(self):
        g=Game();p=Plain(Task({}),g,None)
        resp=self.state(14);p.guard.load(resp);p.guard.count=0;self.run_supply(p.guard)
        text=p.user_message(resp,resp['observation'])
        self.assertTrue(text.startswith('STATUS'))
        self.assertIn('LAYER (deterministic',text)
        self.assertIn('add_order',text)
        self.assertIn('OBSERVATION {',text)
    def test_managed_advance_uses_cached_facts_not_envelope_observation(self):
        import json
        for left,pending,expected in [(None,20,7),(20,20,1),(20,0,2),(4,0,1),(0,0,7)]:
            g=Game();p=Plain(Task({}),g,None);p.messages=[];p.tool_names={'advance_days'}
            r=self.state(left);r['observation']['dig_designations_pending']=pending
            p.guard.load(r);g.last={'day':25,'tick':30000,'hands_off_in_days':left}
            with redirect_stdout(io.StringIO()):
                p.run_call({'id':'a','function':{'name':'advance_days','arguments':json.dumps({'days':7})}})
            self.assertEqual(g.calls[0],('advance_days',{'days':expected}))
    def test_history_drops_old_digest(self):
        m=[{'role':'system','content':'system'}, {'role':'user','content':'STATUS old'},
           {'role':'assistant','content':'ok'}, {'role':'user','content':'STATUS latest'}]
        out=window(m);self.assertEqual(out[1]['content'],'OBSERVATION (older, omitted)')
        self.assertEqual(out[-1]['content'],'STATUS latest')

if __name__=='__main__':unittest.main()
