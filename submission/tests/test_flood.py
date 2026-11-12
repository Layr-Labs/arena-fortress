"""The flood fixes (ROOT_CAUSES §B): the opening stairs go no deeper than the rooms in use (B-1), and a
water_rising stop soon after a dig — or deep indoor water far over the first reading — is a breach whose
containment stops new digs, seals the stair shaft with a locked hatch, and moves placements off the wet levels
(B-2). No network: FakeGame replays the server's shapes (the same contract as tests/test_water.py)."""
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
S1 = {"id": "S1", "kind": "S", "x": 10, "y": 10, "z": SURFACE}
E1 = {"id": "E1", "kind": "E", "x": 10, "y": 10, "z": SURFACE}
D1 = {"id": "D1", "kind": "D", "x": 12, "y": 10, "z": 97}


def room(rid, z, soil=False, designated=False, dug=False):
    return {"id": rid, "kind": "R", "x": 10, "y": 10, "z": z, "w": 3, "h": 3,
            "soil": soil, "free": True, "designated": designated, "dug": dug}


def area(aid, z, open_tiles=8):
    return {"id": aid, "kind": "A", "x": 9, "y": 9, "z": z, "w": 5, "h": 5, "open_tiles": open_tiles}


def obs(day, sites, water=None, doors=None, furniture=(), dwarves=3, pending=0):
    o = {"date": {"abs_tick": day * DAY}, "map": {"surface_z": SURFACE, "sites": sites},
         "recent_events": [], "recent_cancellations": [], "dig_designations_pending": pending,
         "dwarves": [{"id": i} for i in range(dwarves)]}
    if water is not None:
        o["water_on_fort_levels"] = water
    if doors is not None:
        o["doors"] = doors
    if furniture:
        o["furniture"] = list(furniture)
    return {"day": day, "tick": day * DAY, "days_left": 300 - day, "game_over": False, "observation": o}


def envelope(name, result):
    """The real /query/<name> answer (every harness-*.api.jsonl, e.g. /query/map): the envelope with the payload and
    its own ok under "result" — no top-level ok on a success."""
    return {"day": 0, "tick": 0, "days_left": 300, "game_over": False, "query": name, "result": {"ok": True, **result}}


class FakeGame:
    """Records act/query; the map query reports liquid standing on configured levels at the query's own centre
    (wet_levels) and at fixed tiles (x, y, z, depth), in the real answer shape (envelope)."""

    def __init__(self, wet_levels=(), tiles=()):
        self.wet_levels = set(wet_levels)
        self.tiles = list(tiles)
        self.actions, self.queries = [], []

    def act(self, tool, args=None):
        self.actions.append((tool, dict(args or {})))
        return {"ok": True, "result": {}, "day": 0, "tick": 0, "game_over": False}

    def query(self, name, **params):
        self.queries.append((name, params))
        res = {"x1": params["x"] - params["radius"], "y1": params["y"] - params["radius"],
               "x2": params["x"] + params["radius"], "y2": params["y"] + params["radius"],
               "z": params["z"], "z2": params.get("z2", params["z"]), "levels": [], "liquid": [],
               "designations": [], "buildings": []}
        z_top, z_low = params["z"], params.get("z2", params["z"])
        for z in sorted(self.wet_levels):
            if z_low <= z <= z_top:
                res["liquid"].append({"x": params["x"], "y": params["y"], "z": z, "depth": 5, "magma": None})
        for x, y, z, depth in self.tiles:
            if z_low <= z <= z_top and res["x1"] <= x <= res["x2"] and res["y1"] <= y <= res["y2"]:
                res["liquid"].append({"x": x, "y": y, "z": z, "depth": depth, "magma": None})
        res["levels"] = [{"z": z, "shape": [], "material": [], "light": []} for z in range(z_top, z_low - 1, -1)]
        return envelope(name, res)

    def events(self, since_tick=0):
        return {"events": [], "dropped": 0, "now": 0}

    def dig_actions(self):
        return [(t, a) for t, a in self.actions if t.startswith("dig")]

    def tools(self, name):
        return [a for t, a in self.actions if t == name]


class PoolGame(FakeGame):
    """cx: the real /query shape (no top-level ok; the answer under result) with six deep tiles either inside the
    stair's box (a flooded shaft) or 15 tiles off it on the same level (a natural pool beside the fort)."""

    def __init__(self, inside, z=SURFACE):
        super().__init__()
        self.inside, self.fail, self.z = inside, False, z

    def query(self, name, **params):
        self.queries.append((name, params))
        if self.fail:
            raise RuntimeError("GET /query/map: HTTP 500")
        x0 = S1["x"] if self.inside else S1["x"] + 15
        liquid = [{"x": x0 + (i % 2), "y": S1["y"] + i // 2 - 1, "z": self.z, "depth": 7} for i in range(6)
                  if params.get("z2", params["z"]) <= self.z <= params["z"]]
        return {"day": 0, "tick": 0, "days_left": 300, "game_over": False, "query": "map",
                "result": {"ok": True, "liquid": liquid if self.inside is not None else [], "levels": [],
                           "buildings": [], "designations": []}}


def fresh(game, day=0):
    ov = Overseer(game)
    with redirect_stdout(io.StringIO()):
        ov.load(obs(day, []))
    ov.count = 0
    return ov


def quiet(fn):
    with redirect_stdout(io.StringIO()):
        return fn()


WATER = {"tiles": 60, "deep_tiles": 30, "total_depth": 200}   # standing flood water: a breach survives a load


class StairsDepth(unittest.TestCase):
    """B-1: the shaft stops at the deepest room in use instead of the blind surface-4."""

    def test_stairs_reach_only_the_room_in_use(self):
        game = FakeGame()
        ov = fresh(game)
        with redirect_stdout(io.StringIO()):
            ov.load(obs(0, [dict(S1), room("R1", 98)]))
            ov.digging()
        bottom = game.tools("dig_stairs")[0]["z_bottom"]
        self.assertEqual(bottom, 98)   # the dorm room's own level, not the baseline's surface-4 (96)

    def test_a_deeper_room_extends_the_shaft_one_level_at_a_time(self):
        game = FakeGame()
        ov = fresh(game)
        with redirect_stdout(io.StringIO()):
            ov.load(obs(0, [dict(S1), room("R1", 98)]))
            ov.digging()
        self.assertEqual(game.tools("dig_stairs")[0]["z_bottom"], 98)
        # day 2: a second room two levels deeper is designated; the shaft now reaches exactly it
        game.actions.clear()
        with redirect_stdout(io.StringIO()):
            ov.load(obs(2, [dict(S1), room("R1", 98, designated=True), room("R3", 96)]))
            ov.digging()
        self.assertEqual(game.tools("dig_stairs")[-1]["z_bottom"], 96)

    def test_no_room_in_use_yet_means_one_level_below_the_surface(self):
        game = FakeGame()
        ov = fresh(game)
        # no room designated or dug: the single act of this pass is the shallow starter shaft
        with redirect_stdout(io.StringIO()):
            ov.load(obs(0, [dict(S1)]))
            ov.digging()
        bottoms = [a["z_bottom"] for a in game.tools("dig_stairs")]
        self.assertEqual(bottoms, [SURFACE - 1])


class BreachDetection(unittest.TestCase):
    """B-2: a water_rising stop within ~10 days of a dig, or deep water up 50 over the first reading."""

    def test_water_rising_stop_soon_after_a_dig_is_a_breach(self):
        game = FakeGame()
        ov = fresh(game)
        with redirect_stdout(io.StringIO()):
            ov.load(obs(0, [dict(S1), room("R1", 98)]))
            ov.digging()   # day-0 digs: the breach window starts here
        game.tiles = [(10, 10, 99, 3)]   # cx: the water then rises in the shaft S1 was dug down (z99)
        water = {"tiles": 60, "deep_tiles": 30, "total_depth": 200}
        with redirect_stdout(io.StringIO()):
            ov.load(obs(7, [dict(S1), room("R1", 98, designated=True)], water=water))
            ov.water_rising_stop()   # the plain loop's advance hook (or the standalone run) saw the stop
        self.assertTrue(ov.breach)
        self.assertEqual(ov.breach["z"], SURFACE)   # the stair top

    def test_deep_water_gain_is_a_breach_even_without_a_rising_hook(self):
        game = PoolGame(inside=True)   # cx: the gain is confirmed by water inside the fort's own boxes
        ov = fresh(game)
        with redirect_stdout(io.StringIO()):
            ov.load(obs(0, [dict(S1)]))   # first reading: deep_tiles 0
        water = {"tiles": 300, "deep_tiles": 60, "total_depth": 900}
        with redirect_stdout(io.StringIO()):
            ov.load(obs(12, [dict(S1)], water=water))
        self.assertTrue(ov.breach)
        self.assertEqual(ov.breach["day"], 12)

    def test_old_shallow_water_is_not_a_breach(self):
        game = FakeGame()
        ov = fresh(game)
        with redirect_stdout(io.StringIO()):
            ov.load(obs(0, [dict(S1), room("R1", 98)]))
            ov.digging()
        with redirect_stdout(io.StringIO()):
            ov.load(obs(40, [dict(S1), room("R1", 98, designated=True)],
                        water={"tiles": 8, "deep_tiles": 6, "total_depth": 20}))
        self.assertFalse(ov.breach)


class Containment(unittest.TestCase):
    """B-2(a)+(b): no new digs over a breach; the shaft sealed with a hatch and locked."""

    def test_a_breach_stops_every_new_dig_and_orders_the_hatch(self):
        game = FakeGame()
        ov = fresh(game)
        with redirect_stdout(io.StringIO()):
            ov.load(obs(0, [dict(S1), room("R1", 98)]))
            ov.digging()
        game.tiles = [(10, 10, 99, 3)]   # cx: water inside the fort (the S1 shaft): the full response
        doors = {"list": [], "door_items_free": 0, "hatch_cover_items_free": 1}
        with redirect_stdout(io.StringIO()):
            ov.load(obs(7, [dict(S1), dict(E1), room("R1", 98, designated=True)],
                        water={"tiles": 60, "deep_tiles": 30, "total_depth": 200}, doors=doors))
            ov.water_rising_stop()
            game.actions.clear()
            ov.digging()
        self.assertEqual(game.dig_actions(), [])            # (a) no new dig_room / dig_stairs at all
        self.assertEqual(game.tools("build_door"), [{"kind": "hatch", "site": "E1"}])   # (b) the shaft sealed

    def test_an_uncovered_stair_orders_hatch_covers_instead(self):
        game = FakeGame()
        ov = fresh(game)
        ov.breach = {"day": 7, "z": SURFACE}
        with redirect_stdout(io.StringIO()):
            ov.load(obs(8, [dict(E1)], water=WATER, doors={"list": [], "hatch_cover_items_free": 0}))
            ov.digging()
        self.assertEqual(game.tools("add_order"), [{"recipe": "make_hatch_cover", "amount": 2}])
        self.assertEqual(game.tools("build_door"), [])

    def test_a_built_hatch_is_locked_once_and_left_locked(self):
        game = FakeGame(tiles=[(10, 10, 99, 4)])   # cx: water at the hatch's column: the lock closes the shaft
        ov = fresh(game)
        ov.breach = {"day": 7, "z": SURFACE}
        doors = {"list": [{"id": 9, "kind": "hatch", "x": 10, "y": 10, "z": SURFACE, "built": True,
                           "locked": False}], "door_items_free": 0, "hatch_cover_items_free": 0}
        # the hatch is matched to the stair tile itself, not just the level: a hatch on another surface stair
        # must not satisfy this one
        with redirect_stdout(io.StringIO()):
            ov.load(obs(8, [dict(E1), {"id": "E2", "kind": "E", "x": 40, "y": 40, "z": SURFACE}],
                        water=WATER, doors=doors))
            ov.digging()
        self.assertEqual(game.tools("lock_door"), [{"locked": True, "door_id": 9}])
        doors["list"][0]["locked"] = True
        game.actions.clear()
        with redirect_stdout(io.StringIO()):
            ov.load(obs(10, [dict(E1)], water=WATER, doors=doors))
            ov.digging()
        self.assertEqual(game.tools("lock_door"), [])   # already locked: no repeat
        self.assertEqual(ov.flood_locked, {9})

    def test_without_an_e_site_the_doorway_gets_a_wall(self):
        game = FakeGame()
        ov = fresh(game)
        ov.breach = {"day": 7, "z": SURFACE}
        with redirect_stdout(io.StringIO()):
            ov.load(obs(8, [dict(D1)], water=WATER))
            ov.digging()
        self.assertEqual(game.tools("build_wall"), [{"site": "D1"}])


class WetLevels(unittest.TestCase):
    """B-2(c): the wet-level record and the placement exclusions."""

    def test_the_scan_marks_liquid_levels_below_the_surface(self):
        # cx (decision B): water at the scan's centre stands inside the dug room (z97) and the A level (z96); the
        # pool at (25, 10) on z98 is 13 tiles off every box and marks nothing
        game = FakeGame(wet_levels={97, 96, SURFACE}, tiles=[(25, 10, 98, 7)])
        ov = fresh(game)
        ov.breach = {"day": 7, "z": SURFACE}
        with redirect_stdout(io.StringIO()):
            ov.load(obs(8, [dict(S1), dict(E1), room("R1", 97, dug=True), area("A1", 96)], water=WATER))
            ov.digging()
        self.assertEqual(ov.wet_z, {97, 96})   # the surface level itself is the river's, not the flood's

    def test_water_off_the_rooms_marks_no_level(self):
        # cx (decision B, hint std OP1-0 / OP1-3): natural water 2+ tiles off every fort box leaves its level dry
        game = FakeGame(tiles=[(10, 15, 97, 7), (16, 10, 97, 7), (4, 4, 96, 7)])
        ov = fresh(game)
        ov.breach = {"day": 7, "z": SURFACE}
        with redirect_stdout(io.StringIO()):
            ov.load(obs(8, [dict(S1), dict(E1), room("R1", 97, dug=True), area("A1", 96)], water=WATER))
            ov.digging()
        self.assertEqual(ov.wet_z, set())
        self.assertTrue(ov.dry(97) and ov.dry(96))

    def test_room_for_skips_wet_levels_and_prefers_the_highest_dry_site(self):
        game = FakeGame()
        ov = fresh(game)
        sites = [room("R1", 97, designated=True, dug=True), area("A1", 97), area("A2", 98)]
        with redirect_stdout(io.StringIO()):
            ov.load(obs(8, sites))
        ov.roles = {"R1": "dorm"}
        self.assertEqual(ov.room_for("dorm")["id"], "A1")   # the dorm's own level when it is dry
        ov.breach = {"day": 8, "z": SURFACE}
        ov.wet_z = {97}
        self.assertEqual(ov.room_for("dorm")["id"], "A2")   # moved off the wet level, highest dry first

    def test_farms_skip_wet_levels(self):
        game = FakeGame()
        ov = fresh(game)
        f1 = {"id": "F1", "kind": "F", "x": 20, "y": 20, "z": 97, "w": 3, "h": 3}
        f2 = {"id": "F2", "kind": "F", "x": 30, "y": 20, "z": 98, "w": 3, "h": 3}
        with redirect_stdout(io.StringIO()):
            ov.load(obs(8, [f1, f2]))
            ov.farms()
        self.assertEqual([a["site"] for a in game.tools("build_farm")], ["F1", "F2"])
        with redirect_stdout(io.StringIO()):
            ov.load(obs(12, [f1, f2]))   # past the farm act's retry spacing
        ov.breach = {"day": 12, "z": SURFACE}
        ov.wet_z = {97}
        game.actions.clear()
        with redirect_stdout(io.StringIO()):
            ov.farms()
        self.assertEqual([a["site"] for a in game.tools("build_farm")], ["F2"])

    def test_furnish_replaces_beds_lost_to_a_wet_level(self):
        game = FakeGame()
        ov = fresh(game)
        sites = [room("R1", 98, designated=True, dug=True), area("A1", 98)]
        beds = [{"kind": "bed", "built": True, "x": 10 + i, "y": 11, "z": 97, "id": i} for i in range(4)]
        with redirect_stdout(io.StringIO()):
            ov.load(obs(8, sites, furniture=beds))
            ov.free = {"bed": 3}
            ov.furnish()
        self.assertEqual(game.tools("place_furniture")[0]["count"], 1)   # 4 placed beds counted while dry
        with redirect_stdout(io.StringIO()):
            ov.load(obs(13, sites, furniture=beds))   # past the place act's retry spacing
        ov.free = {"bed": 3}
        ov.breach = {"day": 13, "z": SURFACE}
        ov.wet_z = {97}
        game.actions.clear()
        with redirect_stdout(io.StringIO()):
            ov.furnish()
        self.assertEqual(game.tools("place_furniture")[0]["count"], 3)   # the wet beds no longer count


class PaceNotPinned(unittest.TestCase):
    """Flood-caused pending digs must not pin the pace to one day a pass (ROOT_CAUSES §L)."""

    def test_flooded_pending_does_not_force_pace_one(self):
        game = FakeGame()
        ov = fresh(game)
        resp = {"day": 20}
        with redirect_stdout(io.StringIO()):
            ov.load(obs(20, [], pending=7))
            self.assertEqual(ov.pace(resp), 1)   # plain pending digs keep the one-day pace
            ov.breach = {"day": 8, "z": SURFACE}
            self.assertTrue(ov.flooded_pending())
            self.assertEqual(ov.pace(resp), 2)   # the flood's designations never clear: the pace frees up
        early = {"day": 10}
        with redirect_stdout(io.StringIO()):
            self.assertEqual(ov.pace(early), 1)   # the early-game rule still pins day < 14


if __name__ == "__main__":
    unittest.main()


class DeepGainNeedsWaterInTheFort(unittest.TestCase):
    """cx (hint std OP1-0, three runs): water_on_fort_levels counts a natural pool beside the fort; the deep-gain
    trigger froze every dig from day 63-66 with no water in any dug box until day ~207 (std OP1-0 ended with 10 beds
    for 20 citizens). The gain is confirmed by a map query of the fort's own boxes; no answer keeps the old trigger."""
    GAIN = {"tiles": 300, "deep_tiles": 60, "total_depth": 900}

    def start(self, game):
        ov = fresh(game)
        with redirect_stdout(io.StringIO()):
            ov.load(obs(0, [dict(S1)]))   # first reading: deep_tiles 0
        return ov

    def test_a_pool_outside_the_fort_is_no_breach(self):
        game = PoolGame(inside=False)
        ov = self.start(game)
        buf = io.StringIO()
        with redirect_stdout(buf):
            ov.load(obs(66, [dict(S1)], water=self.GAIN))
            ov.load(obs(67, [dict(S1)], water=self.GAIN))
        self.assertIsNone(ov.breach)
        self.assertEqual(buf.getvalue().count("deep_water_outside"), 1)   # logged once, not every load
        self.assertTrue(game.queries)

    def test_water_inside_the_fort_still_breaches(self):
        game = PoolGame(inside=True)
        ov = self.start(game)
        with redirect_stdout(io.StringIO()):
            ov.load(obs(66, [dict(S1)], water=self.GAIN))
        self.assertTrue(ov.breach)
        self.assertEqual(ov.breach["cause"], "deep_water_gain")

    def test_a_lost_query_keeps_the_old_trigger(self):
        game = PoolGame(inside=False)
        game.fail = True
        ov = self.start(game)
        with redirect_stdout(io.StringIO()):
            ov.load(obs(66, [dict(S1)], water=self.GAIN))
        self.assertTrue(ov.breach)

    def test_a_deep_gain_breach_releases_after_three_dry_scan_days(self):
        game = PoolGame(inside=True)
        ov = self.start(game)
        with redirect_stdout(io.StringIO()):
            ov.load(obs(66, [dict(S1)], water=self.GAIN))
        self.assertTrue(ov.breach)
        game.inside = False
        buf = io.StringIO()
        with redirect_stdout(buf):
            for day in (67, 67, 68, 68):
                ov.load(obs(day, [dict(S1)], water=self.GAIN))
            self.assertTrue(ov.breach)   # two scan days so far (two loads a day count once)
            ov.load(obs(69, [dict(S1)], water=self.GAIN))
        self.assertIsNone(ov.breach)
        self.assertIn("flood_outside", buf.getvalue())

    def test_a_rising_stop_breach_is_not_released_by_the_scan(self):
        game = PoolGame(inside=None, z=SURFACE - 1)   # no water on day 0: S1 is dug
        ov = self.start(game)
        with redirect_stdout(io.StringIO()):
            ov.load(obs(0, [dict(S1), room("R1", 98)]))
            ov.digging()
            game.inside = True   # cx: then the water stands in the S1 shaft dug on day 0
            ov.load(obs(3, [dict(S1)], water=WATER))   # under the deep-gain trigger: the stop alone decides
            ov.water_rising_stop()
        self.assertEqual(ov.breach["cause"], "water_rising_after_dig")
        game.inside = False
        with redirect_stdout(io.StringIO()):
            for day in (4, 5, 6, 7):
                ov.load(obs(day, [dict(S1)], water=self.GAIN))
        self.assertTrue(ov.breach)
