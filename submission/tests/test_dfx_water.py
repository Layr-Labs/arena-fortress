"""The dfx containment repairs (the runs/dfx-my15-v2/MY1-5 read, 2026-11-10): the wet-level scan must fit the
server's own query window (|z2 - z| <= 4, gameapi/facts/lua/query.lua:237 — the measured run lost every scan to
"bad_arguments" and its dry-floor exclusions ran on an empty record), a contained breach must not release halt
resumes (the d0 resume re-dug the flooded stratum and the d7-11 flood was the result), and a farm plot standing
on a wet level is dead and must not block a dry replacement. No network: a FakeGame that enforces the real
window, unlike the permissive stubs above."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer.harness import Overseer  # noqa: E402

DAY = 1200
SURFACE = 100
F1 = {"id": "F1", "kind": "F", "x": 20, "y": 20, "z": 97, "w": 3, "h": 3}
F2 = {"id": "F2", "kind": "F", "x": 30, "y": 20, "z": 99, "w": 3, "h": 3}
# cx (decision B): the fort's own dug levels the scan's water stands in (the scan's centre is (19, 19))
A99 = {"id": "A99", "kind": "A", "x": 18, "y": 18, "z": 99, "w": 5, "h": 5, "open_tiles": 20}
A93 = {"id": "A93", "kind": "A", "x": 18, "y": 18, "z": 93, "w": 5, "h": 5, "open_tiles": 20}


def obs(day, sites, water=None, farm_plots=()):
    o = {"date": {"abs_tick": day * DAY},
         "map": {"surface_z": SURFACE, "sites": list(sites)},
         "recent_events": [], "recent_cancellations": [], "dig_designations_pending": 0,
         "dwarves": [{"id": 1}, {"id": 2}, {"id": 3}]}
    if water is not None:
        o["water_on_fort_levels"] = water
    if farm_plots:
        o["farm_plots"] = list(farm_plots)
    return {"day": day, "tick": day * DAY, "days_left": 300 - day, "game_over": False, "observation": o}


def plot(pid, z, in_plot=3):
    return {"built": True, "id": pid, "x": 20, "y": 20, "z": z, "w": 3, "h": 3,
            "crops": {}, "seeds_or_crops_in_plot": in_plot}


class WindowGame:
    """A map query that answers only inside the server's 5-level window — every wider one is refused with the
    measured bad_arguments shape, so a single 8-level scan records nothing at all."""

    def __init__(self, wet_levels=()):
        self.wet_levels = set(wet_levels)
        self.queries, self.refused, self.actions = [], [], []

    def act(self, tool, args=None):
        self.actions.append((tool, dict(args or {})))
        return {"ok": True, "result": {}, "day": 0, "tick": 0, "game_over": False}

    def query(self, name, **params):
        self.queries.append((params["z"], params.get("z2", params["z"])))
        env = {"day": 8, "tick": 8 * DAY, "days_left": 292, "game_over": False}
        if abs(params["z"] - params.get("z2", params["z"])) > 4:
            self.refused.append((params["z"], params.get("z2")))
            # the measured refusal (f7f4716b hint std OP1-0 harness-0.api.jsonl): top-level ok false, no result
            return {**env, "ok": False, "error_code": "bad_arguments", "error": "at most 5 levels (|z2 - z| <= 4)"}
        z_top, z_low = params["z"], params.get("z2", params["z"])
        res = {"ok": True, "liquid": [{"x": params["x"], "y": params["y"], "z": z, "depth": 5, "magma": None}
                                      for z in sorted(self.wet_levels) if z_low <= z <= z_top]}
        return {**env, "query": name, "result": res}   # the real success shape: no top-level ok

    def events(self, since_tick=0):
        return {"events": [], "dropped": 0, "now": 0}


def fresh(game, day=0):
    ov = Overseer(game)
    with redirect_stdout(io.StringIO()):
        ov.load(obs(day, []))
    ov.count = 0
    return ov


class WetScanWindow(unittest.TestCase):
    """The dfx bug: one 8-level query is refused by the server, so the wet record stayed empty all run and no
    dry-floor exclusion ever had data. The scan now walks the window in spans."""

    def test_the_scan_bands_inside_the_five_level_window(self):
        game = WindowGame(wet_levels={99, 93})
        ov = fresh(game, day=8)
        ov.breach = {"day": 7, "z": SURFACE}
        with redirect_stdout(io.StringIO()):
            ov.load(obs(8, [dict(F1), dict(A99), dict(A93)], water={"tiles": 60, "deep_tiles": 30, "total_depth": 200}))
            ov.record_wet_levels()
        self.assertTrue(game.queries)
        self.assertEqual(game.refused, [])                       # nothing wider than the window was sent
        for z, z2 in game.queries:
            self.assertLessEqual(abs(z - z2), 4)
        self.assertEqual(ov.wet_z, {99, 93})                     # both bands' water lands in the record
        # 8 levels down = two spans from the surface: the surface level itself is never marked

    def test_a_refused_band_keeps_the_earlier_bands_record(self):
        game = WindowGame(wet_levels={99})

        def refuse_deep(params_z2):
            orig = game.query

            def query(name, **params):
                if params["z"] < 97:                             # the deeper band is refused
                    game.refused.append((params["z"], params.get("z2")))
                    return {"ok": False, "error_code": "bad_arguments", "error": "refused"}
                return orig(name, **params)
            game.query = query
        refuse_deep(None)
        ov = fresh(game, day=8)
        ov.breach = {"day": 7, "z": SURFACE}
        with redirect_stdout(io.StringIO()):
            ov.load(obs(8, [dict(F1), dict(A99), dict(A93)], water={"tiles": 60, "deep_tiles": 30, "total_depth": 200}))
            ov.record_wet_levels()
        self.assertEqual(ov.wet_z, {99})                         # the shallow band's reading survives the refusal

    def test_an_all_refused_scan_leaves_yesterdays_record(self):
        game = WindowGame(wet_levels={99})

        def always_refuse(name, **params):
            game.refused.append((params["z"], params.get("z2")))
            return {"ok": False, "error_code": "bad_arguments", "error": "refused"}
        game.query = always_refuse
        ov = fresh(game, day=8)
        ov.wet_z = {97}                                          # yesterday's reading
        with redirect_stdout(io.StringIO()):
            ov.load(obs(9, [], water={"tiles": 60, "deep_tiles": 30, "total_depth": 200}))
            ov.record_wet_levels()
        self.assertEqual(ov.wet_z, {97})                         # not overwritten with an empty one


class BreachHoldsTheHalt(unittest.TestCase):
    """The containment/resume conflict: while a breach is contained, water_ok releases nothing."""

    def test_no_resume_while_the_breach_is_active(self):
        game = WindowGame()                                      # every probe answers dry
        ov = fresh(game, day=8)
        ov.breach = {"day": 7, "z": SURFACE}
        ov.water_halts["R1"] = 1
        self.assertFalse(ov.water_ok({"id": "R1", "z": 98}))
        self.assertIn("R1", ov.water_halts)                      # a dry probe does not cut through containment
        ov.breach = None
        self.assertTrue(ov.water_ok({"id": "R1", "z": 98}))      # released once the flood has receded
        self.assertNotIn("R1", ov.water_halts)

    def test_no_resume_while_the_site_level_stands_in_water(self):
        game = WindowGame()                                      # the local box probes dry...
        ov = fresh(game, day=8)
        ov.wet_z = {98}                                          # ...but the level itself is recorded wet
        ov.water_halts["R1"] = 1
        self.assertFalse(ov.water_ok({"id": "R1", "z": 98}))
        self.assertIn("R1", ov.water_halts)


class DeadPlotCounts(unittest.TestCase):
    """A plot standing on a wet level grows nothing (the dfx farm): it must not block a dry replacement."""

    def test_a_wet_plot_does_not_count_towards_the_farm_target(self):
        game = WindowGame()
        ov = fresh(game, day=12)
        sites = [dict(F1), dict(F2)]
        plots = [plot(5, 97, in_plot=0), plot(6, 99, in_plot=3)]   # one drowned, one alive
        with redirect_stdout(io.StringIO()):
            ov.load(obs(12, sites, farm_plots=plots))
            ov.wet_z = {97}
            ov.farms()
        farms = [a["site"] for t, a in game.actions if t == "build_farm"]
        self.assertEqual(farms, ["F2"])    # the wet-z candidate (F1, z97) is skipped and F2 is built instead

    def test_alive_plots_still_satisfy_the_target_without_new_builds(self):
        game = WindowGame()
        ov = fresh(game, day=12)
        plots = [plot(5, 97, in_plot=3), plot(6, 99, in_plot=3)]   # both measured dry (97 not in wet_z)
        with redirect_stdout(io.StringIO()):
            ov.load(obs(12, [], farm_plots=plots))
            ov.farms()
        self.assertEqual([t for t, a in game.actions if t == "build_farm"], [])


if __name__ == "__main__":
    unittest.main()
