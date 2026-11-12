"""The W4water rules: dig sites next to water are dug last, water signals halt a site's dig_room until the water
recedes, and a water_rising stop halts the dig fronts. No network: FakeGame replays the server's shapes, and every
stub key is one the facts layer really sends (gameapi/facts/lua/observe.lua, query.lua, events.lua)."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer.harness import Overseer, WATER_PROBES_PER_DAY  # noqa: E402

DAY = 1200
R1 = {"id": "R1", "kind": "R", "x": 10, "y": 10, "z": 100, "w": 3, "h": 3, "soil": False, "free": True}
R2 = {"id": "R2", "kind": "R", "x": 50, "y": 50, "z": 100, "w": 3, "h": 3, "soil": False, "free": True}


def obs(day, sites, water=None, recent_events=(), cancellations=()):
    o = {"date": {"abs_tick": day * DAY},
         "map": {"surface_z": 100, "sites": sites},
         "recent_events": list(recent_events), "recent_cancellations": list(cancellations),
         "dig_designations_pending": 0}
    if water is not None:
        o["water_on_fort_levels"] = water
    return {"day": day, "tick": day * DAY, "days_left": 100 - day, "game_over": False, "observation": o}


def water_at(res, coords):
    """coords: {(x, y): depth} water tiles near the queried box (mixed into the map query's real liquid shape)."""
    res["liquid"] = [{"x": x, "y": y, "z": res["z"], "depth": depth, "magma": None} for (x, y), depth in coords.items()]


class FakeGame:
    """Records act/query/events; water is scripted per tile, so a site near (12, 10) digs into water."""

    def __init__(self, water_tiles=(), material_rows=None):
        self.water_tiles = dict(water_tiles)
        self.material_rows = material_rows or {}
        self.actions, self.queries, self.events_pages = [], [], []
        self.events_result = {"events": [], "dropped": 0, "now": 0}

    def act(self, tool, args=None):
        self.actions.append((tool, dict(args or {})))
        return {"ok": True, "result": {}, "day": 0, "tick": 0, "game_over": False}

    def query(self, name, **params):
        self.queries.append((name, params))
        res = {"x1": params["x"] - params["radius"], "y1": params["y"] - params["radius"],
               "x2": params["x"] + params["radius"], "y2": params["y"] + params["radius"],
               "z": params["z"], "z2": params.get("z2", params["z"]), "levels": [], "liquid": [],
               "designations": [], "buildings": []}
        z2 = params.get("z2", params["z"])
        for z in range(params["z"], z2 - 1, -1):
            level = {"z": z, "shape": [], "material": [], "light": []}
            for y in range(res["y1"], res["y2"] + 1):
                level["material"].append(self.material_rows.get(z, "." * (res["x2"] - res["x1"] + 1)))
                level["shape"].append("." * (res["x2"] - res["x1"] + 1))
                level["light"].append("i" * (res["x2"] - res["x1"] + 1))
            res["levels"].append(level)
        water_at(res, {xy: depth for xy, depth in self.water_tiles.items()
                       if res["x1"] <= xy[0] <= res["x2"] and res["y1"] <= xy[1] <= res["y2"]
                       and z2 <= params["z"]})
        # the real /query/map answer: the envelope, the payload and its own ok under "result", no top-level ok
        return {"day": 0, "tick": 0, "days_left": 100, "game_over": False, "query": name, "result": {"ok": True, **res}}

    def events(self, since_tick=0):
        self.events_pages.append(since_tick)
        return self.events_result


def fresh(game, day=0):
    ov = Overseer(game)
    ov.load(obs(day, []))
    ov.count = 0
    return ov


def digs(game):
    return [a for t, a in game.actions if t == "dig_room"]


class HaltAndResume(unittest.TestCase):
    def test_deep_indoor_water_halts_the_dig_front_until_the_water_recedes(self):
        game = FakeGame()
        ov = fresh(game)
        ov.load(obs(0, [dict(R1), dict(R2)]))
        ov.digging()                                   # day 0: no water anywhere; R1 is dug first (dorm), then R2
        self.assertEqual([a["site"] for a in digs(game)], ["R1", "R2"])
        game.water_tiles = {(52, 50): 7}               # then water stands next to R2 only
        # day 1: deep indoor water + a wet dig cancel -> the undug front (R2) is halted, and R2's map box is wet
        ov.load(obs(1, [dict(R1, designated=True), dict(R2)], water={"tiles": 30, "deep_tiles": 30, "total_depth": 120},
                    cancellations=["Urist McDwarf, Miner cancels Dig: wet stone"]))
        game.actions.clear()
        ov.digging()
        self.assertEqual(digs(game), [])
        self.assertIn("R2", ov.water_halts)
        # day 2: the water has receded (no signal, and the box now probes dry) -> the halt is released. R2's room
        # role was already assigned on day 0 (the stub marks nothing designated), so no new dig_room is queued.
        game.water_tiles.clear()
        ov.load(obs(2, [dict(R1, designated=True), dict(R2)]))
        game.actions.clear()
        ov.digging()
        self.assertEqual(digs(game), [])
        self.assertNotIn("R2", ov.water_halts)

    def test_a_halted_site_is_probed_at_most_once_per_day(self):
        game = FakeGame(water_tiles={((52, 50)): 7})
        ov = fresh(game)
        ov.load(obs(1, [dict(R2)], water={"tiles": 30, "deep_tiles": 30, "total_depth": 120}))
        probes = len(game.queries)
        for _ in range(3):
            self.assertFalse(ov.water_ok(R2))
        self.assertEqual(len(game.queries), probes + 1)   # one re-probe that day, no matter how often asked


class DryFirst(unittest.TestCase):
    def test_a_site_next_to_water_yields_to_a_drier_site(self):
        game = FakeGame(water_tiles={((12, 10)): 7})   # water in R1's box, R2's is dry
        ov = fresh(game)
        ov.load(obs(0, [dict(R1), dict(R2)]))
        ov.digging()
        # R2 (dry) is dug; R1 (water touching its dig box) is never dug while the water touches it — cx: the old
        # "dug last" fail-open never ran (the measure read 0 on every real answer) and the measured OP1-0 R9/R10
        # digs beside the pool were the flood. Skipping is not a halt: R1 stays measurable, unhalted.
        self.assertEqual([a["site"] for a in digs(game)], ["R2"])
        self.assertEqual(ov.water_halts, {})
        self.assertEqual(ov.water_rank(R1), 2)

    def test_magma_liquid_and_magma_stone_are_not_water(self):
        game = FakeGame()
        ov = fresh(game)
        res = {"z": 100, "levels": [{"z": 100, "material": ["....RR......M.....", ], "shape": [], "light": []}],
               "liquid": [{"x": 1, "y": 1, "z": 100, "depth": 7, "magma": None},
                          {"x": 2, "y": 1, "z": 100, "depth": 7, "magma": 1}]}
        n = ov.count_water(res)
        self.assertEqual(n, 3)   # two RIVER letters + one water liquid tile; the magma pair is ignored


class DrownedMiner(unittest.TestCase):
    def test_a_drowned_miner_halts_the_dig_front_and_the_site_the_body_was_found_at(self):
        game = FakeGame(water_tiles={((52, 50)): 7})   # R2's box is still wet, R1's has receded
        game.events_result = {"events": [{"id": 7, "tick": 5 * DAY, "type": "CITIZEN_DEATH", "announcement": True,
                                          "text": "Urist McDwarf, Miner has been found dead, drowned.",
                                          "x": 11, "y": 11, "z": 100}], "dropped": 0, "now": 5 * DAY}
        ov = fresh(game)
        ov.load(obs(5, [dict(R1), dict(R2)],
                    recent_events=["Urist McDwarf, Miner has been found dead, drowned."]))
        self.assertIn("R1", ov.water_halts)            # the site the body was found at...
        self.assertIn("R2", ov.water_halts)            # ...and the rest of the front (the text alone is generic)
        ov.digging()
        self.assertEqual([a["site"] for a in digs(game)], ["R1"])   # R1 probed dry: released and dug; R2 stays halted
        game.actions.clear()
        ov.load(obs(6, [dict(R1, designated=True), dict(R2)],
                    recent_events=["Urist McDwarf, Miner has been found dead, drowned."]))
        ov.digging()
        self.assertEqual(digs(game), [])               # day 6: R2's box still measures wet: the halt stands
        game.water_tiles.clear()
        ov.load(obs(7, [dict(R1, designated=True), dict(R2)]))
        game.actions.clear()
        ov.digging()
        self.assertEqual([a["site"] for a in digs(game)], ["R2"])   # the water receded: R2 resumes on day 7

    def test_site_near_maps_report_positions_with_margin(self):
        ov = fresh(FakeGame())
        ov.load(obs(0, [dict(R1)]))
        self.assertEqual(ov.site_near(11, 11, 100), "R1")
        self.assertEqual(ov.site_near(13, 10, 100), "R1")    # 3 wide + margin 2
        self.assertIsNone(ov.site_near(30, 30, 100))
        self.assertIsNone(ov.site_near("x", 11, 100))        # reports without integer positions map nowhere


class TripwireAndBudget(unittest.TestCase):
    def test_a_water_rising_stop_halts_the_dig_fronts(self):
        game = FakeGame(water_tiles={((12, 10)): 7})
        ov = fresh(game)
        ov.load(obs(3, [dict(R1), dict(R2)]))
        with redirect_stdout(io.StringIO()):
            ov.water_generic_halt("water_rising_stop")
        self.assertEqual(sorted(ov.water_halts), ["R1", "R2"])
        ov.digging()
        # R1's box still measures wet, so R1 stays halted; R2's has no water: the once-a-day probe releases it
        # (resume rule: the water has receded) and R2 is dug
        self.assertEqual([a["site"] for a in digs(game)], ["R2"])
        self.assertEqual(sorted(ov.water_halts), ["R1"])

    def test_probe_budget_caps_the_water_queries_per_day(self):
        ov = fresh(FakeGame())
        outcomes = [ov.water_probe_ok() for _ in range(WATER_PROBES_PER_DAY + 2)]
        self.assertEqual(outcomes, [True] * WATER_PROBES_PER_DAY + [False, False])


if __name__ == "__main__":
    unittest.main()
