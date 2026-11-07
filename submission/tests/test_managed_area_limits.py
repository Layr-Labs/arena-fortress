"""Use the actual public site resolver and integer converter on an observed oversized area."""
import io
import sys
import unittest
from pathlib import Path
from contextlib import redirect_stdout
sys.path.insert(0,str(Path.cwd()))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gameapi.facts.sites import SiteState
from gameapi.facts.tools import as_int
from overseer.harness import Overseer
AREA={'id':'A1','kind':'A','x':85,'y':93,'z':107,'w':42,'h':34,'open_tiles':109}
class Game:
    def __init__(self):
        self.calls=[];self.resolved=[];self.sites=SiteState();self.sites.update({'A':[AREA]})
    def act(self,t,a):
        self.calls.append((t,dict(a)));r,e=self.sites.resolve(t,a);assert e is None,e
        cap=40 if t=='place_furniture' else 20
        as_int(r,'w',1,cap);as_int(r,'h',1,cap)
        self.resolved.append(r)
        return {'ok':True,'result':{'n':1,'at':[97,94,107],'zone_id':70}}
class AreaLimits(unittest.TestCase):
    def agent(self,left=14):
        g=Game();o=Overseer(g);o.load({'tick':0,'hands_off_in_days':left,'observation':{
            'administrators':{'citizens':45},'stocks':{'furniture_free':{'bed':22}},
            'furniture':[{'kind':'bed','x':97,'y':94,'z':107} for _ in range(19)],'map':{'sites':[dict(AREA)]}}});o.count=0;return g,o
    def test_resolver_preserves_bounded_dimensions_and_observed_origin(self):
        g,o=self.agent()
        with redirect_stdout(io.StringIO()):o.furnish()
        self.assertEqual(g.calls[0][1]['w'],40)
        self.assertEqual(g.calls[0][1]['h'],34)
        self.assertTrue(any(t=='make_zone' and a['w']==20 and a['h']==20 for t,a in g.calls))
        self.assertTrue(all((r['x'],r['y'],r['z'])==(85,93,107) for r in g.resolved))
    def test_bounding_does_not_mutate_observed_area(self):
        g,o=self.agent();o.area_args(o.sites[0],40)
        self.assertEqual(o.sites[0]['w'],42);self.assertEqual(o.sites[0]['h'],34)
    def test_long_game_retains_original_site_arguments(self):
        g,o=self.agent(None);self.assertEqual(o.area_args(o.sites[0],40),{'site':'A1'})
if __name__=='__main__':unittest.main()
