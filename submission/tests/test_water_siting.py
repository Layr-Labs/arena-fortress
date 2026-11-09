"""Visible brook/liquid geometry and conservative startup fallbacks."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness
assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

class MapGame:
    def __init__(self, result=None, fail=False):
        self.result, self.fail, self.queries, self.calls = result or {}, fail, [], []
    def query(self, name, **args):
        self.queries.append((name, args))
        if self.fail:
            raise RuntimeError("diagnostic query unavailable")
        return {"result": self.result}
    def act(self, tool, args):
        self.calls.append((tool, args))
        return {"ok": True}

class WaterSiting(unittest.TestCase):
    def setUp(self):
        out=redirect_stdout(io.StringIO());out.__enter__();self.addCleanup(out.__exit__, None, None, None)
        self.far={"id":"S3","kind":"S","x":96,"y":92}
        self.near={"id":"S4","kind":"S","x":96,"y":98}
    def guard(self, result=None, fail=False):
        game=MapGame(result, fail);g=harness.Overseer(game,days=336);g.surface=83
        return g,game
    def test_observed_depth7_below_brook_prefers_farther_existing_site(self):
        g,game=self.guard({"liquid":[{"x":96,"y":100,"z":82,"depth":7}]})
        self.assertEqual(g.stair_site([self.far,self.near]),self.far)
        self.assertEqual(game.queries[0][0],"map")
        self.assertEqual(game.queries[0][1]["z2"],82)
    def test_visible_brook_top_also_supplies_water_location(self):
        g,_=self.guard({"x1":96,"y1":100,"levels":[{"shape":["~"],"material":["k"]}]})
        self.assertEqual(g.stair_site([self.far,self.near]),self.far)
    def test_hidden_cells_are_not_inferred_to_be_water(self):
        g,_=self.guard({"x1":96,"y1":100,"levels":[{"shape":["???"],"material":["???"]}]})
        self.assertEqual(g.stair_site([self.far,self.near]),self.near)
    def test_empty_query_retains_previous_site_choice(self):
        g,_=self.guard()
        self.assertEqual(g.stair_site([self.far,self.near]),self.near)
    def test_failed_query_retains_previous_choice(self):
        g,_=self.guard(fail=True)
        self.assertEqual(g.stair_site([self.far,self.near]),self.near)
    def test_equal_distances_retain_last_site_tie_break(self):
        g,_=self.guard({"liquid":[{"x":0,"y":0,"depth":1}]})
        a={"id":"S1","x":3,"y":4};b={"id":"S2","x":4,"y":3}
        self.assertEqual(g.stair_site([a,b]),b)
    def test_bounded_radius_and_nonnegative_query_level(self):
        g,game=self.guard();g.surface=0
        g.stair_site([{"id":"S1","x":1,"y":1},{"id":"S2","x":40,"y":40}])
        self.assertEqual(game.queries[0][1]["radius"],20)
        self.assertEqual(game.queries[0][1]["z2"],0)
    def test_short_established_fort_keeps_previous_stair_without_water_query(self):
        g, game = self.guard({"liquid": [{"x": 96, "y": 100, "depth": 7}]})
        g.days = 216
        self.assertEqual(g.stair_site([self.far, self.near]), self.near)
        self.assertEqual(game.queries, [])

    def test_migrant_goal_keeps_previous_stair_even_with_long_horizon(self):
        g, game = self.guard({"liquid": [{"x": 96, "y": 100, "depth": 7}]})
        g.surge = True
        self.assertEqual(g.stair_site([self.far, self.near]), self.near)
        self.assertEqual(game.queries, [])

    def test_stair_retry_gate_suppresses_repeated_map_queries(self):
        g,game=self.guard({"liquid":[{"x":96,"y":100,"depth":7}]})
        g.load({"day":0,"tick":0,"observation":{"map":{"surface_z":83,"sites":[self.far,self.near]},"administrators":{"citizens":7}}})
        g.count=0;g.digging();g.digging()
        self.assertEqual(len(game.queries),1)
        self.assertEqual(game.calls,[("dig_stairs",{"site":"S3","z_bottom":79})])

if __name__ == "__main__":unittest.main()
