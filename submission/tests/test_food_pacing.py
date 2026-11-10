import io,json,unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from plain.harness import Plain
from unittest.mock import patch
from plain import harness

class Game:
    def __init__(self,window):
        self.last={'tick':360000,'day':300,'days_left':36,'hands_off_in_days':window};self.calls=[]
    def act(self,name,args):
        self.calls.append((name,args.copy()))
        return {'ok':True,'day':300+args.get('days',0),'result':{}}

class FoodPacing(unittest.TestCase):
    def advance(self,food,left=36,window=None,requested=7):
        g=Game(window);p=Plain(SimpleNamespace(task={'days':336},days=336,credits=None),g,SimpleNamespace(usage={'cost_usd':0}))
        p.tool_names={'advance_days'};p.messages=[]
        p.guard.load({'day':300,'tick':360000,'days_left':left,'hands_off_in_days':window,
                      'observation':{'administrators':{'citizens':21},'stocks':{'food_edible':food}}})
        # Isolate inherited food thresholds from the new global two-day cap.
        with patch.object(harness,"MAX_DAYS",14), redirect_stdout(io.StringIO()):
            p.run_call({'id':'food-pacing','function':{'name':'advance_days','arguments':json.dumps({'days':requested})}})
        self.assertEqual(len(g.calls),1)
        return g.calls[0][1]['days']
    def test_critical_and_warning_reserves_get_earlier_controller_passes(self):
        for food,want in [(83,1),(84,2),(125,2),(126,7)]:
            with self.subTest(food=food):self.assertEqual(self.advance(food),want)
    def test_unknown_or_noninteger_food_does_not_invent_an_emergency(self):
        for food in [None,False,'83']:
            with self.subTest(food=food):self.assertEqual(self.advance(food),7)
    def test_early_game_and_lab_windows_keep_existing_pacing(self):
        self.assertEqual(self.advance(83,left=65),7)
        self.assertEqual(self.advance(83,window=5),7)
        self.assertEqual(self.advance(83,window=3),1)
    def test_food_feedback_never_lengthens_a_requested_short_advance(self):
        self.assertEqual(self.advance(125,requested=1),1)
