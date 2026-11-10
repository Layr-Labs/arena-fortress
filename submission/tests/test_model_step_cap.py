"""A routine model advance must not skip the controller's maintenance interval."""
import io,json,unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from plain import harness
from test_pacing import FakeGame
from test_periodic_diagnosis import Game,Guard

class ShortModelSteps(unittest.TestCase):
    def setUp(self):
        out=redirect_stdout(io.StringIO());out.__enter__();self.addCleanup(out.__exit__,None,None,None)
    def test_advertised_cap_matches_two_days_without_mutating_server_schema(self):
        original=FakeGame().task()['tools'];tools=harness.prepare_tools(original)
        a=next(t['function'] for t in tools if t['function']['name']=='advance_days')
        self.assertEqual(a['parameters']['properties']['days']['maximum'],2)
        self.assertEqual(original[1]['function']['parameters']['properties']['days']['maximum'],28)
    def test_model_advance_is_capped_but_one_day_request_is_preserved(self):
        for requested,expected in [(14,2),(7,2),(1,1)]:
            g=FakeGame();p=harness.Plain(SimpleNamespace(task={'days':336},days=336,credits=None),g,SimpleNamespace(usage={'cost_usd':0}));p.setup();p.guard.load(g.observe())
            p.run_call({'id':'short-step','function':{'name':'advance_days','arguments':json.dumps({'days':requested})}})
            self.assertEqual(g.actions[-1],('advance_days',{'days':expected}))
    def test_large_model_requests_still_leave_controller_passes_within_two_days(self):
        g=Game();p=harness.Plain(SimpleNamespace(task={'days':20},days=20,credits=1),g,SimpleNamespace(usage={'cost_usd':0}));p.guard=Guard();seen=[]
        def setup():p.tool_names={'advance_days'};p.messages=[{'role':'system','content':'test'}];p.extra={};p.tools=[]
        p.setup=setup;p.user_message=lambda r,o:'observation'
        def chat():
            seen.append(g.day);return {'role':'assistant','tool_calls':[{'id':str(len(seen)),'function':{'name':'advance_days','arguments':'{"days":14}'}}]}
        p.chat=chat;p.run();self.assertEqual(g.day,20);self.assertEqual(seen,[0,14]);self.assertLessEqual(max(b-a for a,b in zip(p.guard.days,p.guard.days[1:])),2)

if __name__=='__main__':unittest.main()
