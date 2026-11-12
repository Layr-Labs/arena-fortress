"""cx (owner decisions B and C, 2026-11-10).

B: every /query reader takes the real answer shape — the envelope (day, tick, days_left, game_over, query) with the
payload and its own ok under "result" and NO top-level ok on a success; a refusal is the envelope with a top-level
ok false and an error_code and no result. The old water_measure / record_wet_levels read a top-level ok, so every
hint run logged water_probe_error "not ok" daily and every site measured 0. "Wet" is water touching the fort's own
boxes (dug rooms, A levels, stairs and their shafts; a 1-tile margin) — never the natural pool 2+ tiles off them.

C: a water_rising stop soon after a dig halts only the digs near the water when the water stands outside every fort
box (hint std OP1-3 cxe60d4ce: the d0 stop froze all digging for the whole year while the pool sat 10 tiles off every
room); water inside a box is still the full breach (no digs at all, the shaft sealed).

Fixtures are the recorded answers of finished hint runs (map/query shapes and the OP1-0 day-177 pool)."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer.harness import (Overseer, query_result, BREACH_CLEAR_SCANS, RISE_MARGIN)  # noqa: E402

DAY = 1200
SURFACE = 162
ENV = {"day": 177, "tick": 177 * DAY, "days_left": 159, "game_over": False}
# cxe538c50 hint std OP1-0, harness-0.api.jsonl, the last /query/map before day 177 (x 81-105, y 82-106, z162-158):
# the z161 pool north of the dwelling rows (every tile depth 7)
POOL = ([(91, 82), (91, 83)] + [(92, y) for y in range(82, 88)] + [(93, y) for y in range(82, 89)]
        + [(94, y) for y in range(84, 90)] + [(x, y) for x in range(95, 105) for y in range(86, 90)])
# that day's sites: the A level and dug rooms of the dwelling level (A4's top row y91 is 2 tiles off the pool's
# y89), and R9 whose 3x3 box (y90) touches it — the AI dug R9 on d177 and R10 on d182; 98 tiles stood inside by d187
A4 = {"id": "A4", "kind": "A", "x": 89, "y": 91, "z": 161, "w": 13, "h": 11, "open_tiles": 100}
R4 = {"id": "R4", "kind": "R", "x": 95, "y": 91, "z": 161, "w": 3, "h": 3, "dug": True, "designated": True}
R1 = {"id": "R1", "kind": "R", "x": 99, "y": 95, "z": 161, "w": 3, "h": 3, "dug": True, "designated": True}
R9 = {"id": "R9", "kind": "R", "x": 100, "y": 90, "z": 161, "w": 3, "h": 3, "free": True}
R11 = {"id": "R11", "kind": "R", "x": 90, "y": 103, "z": 161, "w": 3, "h": 3, "free": True}   # south, away
S1 = {"id": "S1", "kind": "S", "x": 97, "y": 96, "z": SURFACE, "w": 1, "h": 1}
E1 = {"id": "E1", "kind": "E", "x": 97, "y": 96, "z": SURFACE, "w": 1, "h": 1}


class MapGame:
    """The real /query/map: answers inside the server's 5-level window, liquid from a tile table, the success
    shape without a top-level ok and the measured refusal shape."""

    def __init__(self, tiles=(), refuse=False):
        self.tiles = {(x, y, z): dep for x, y, z, dep in tiles}
        self.refuse, self.raise_error = refuse, False
        self.actions, self.queries = [], []

    def act(self, tool, args=None):
        self.actions.append((tool, dict(args or {})))
        return {**ENV, "ok": True, "result": {}}

    def events(self, since_tick=0):
        return {**ENV, "events": [], "dropped": 0, "now": 0}

    def query(self, name, **p):
        self.queries.append((name, p))
        if self.raise_error:
            raise RuntimeError("GET /query/map: HTTP 500")
        z, z2 = p["z"], p.get("z2", p["z"])
        if self.refuse or abs(z - z2) > 4:
            return {**ENV, "ok": False, "error_code": "bad_arguments", "error": "at most 5 levels (|z2 - z| <= 4)"}
        r = p.get("radius", 12)
        x1, x2, y1, y2 = p["x"] - r, p["x"] + r, p["y"] - r, p["y"] + r
        liquid = [{"x": x, "y": y, "z": zz, "depth": dep} for (x, y, zz), dep in sorted(self.tiles.items())
                  if x1 <= x <= x2 and y1 <= y <= y2 and z2 <= zz <= z]
        levels = [{"z": zz, "material": ["g" * (x2 - x1 + 1)] * (y2 - y1 + 1), "shape": [], "light": []}
                  for zz in range(z, z2 - 1, -1)]
        return {**ENV, "query": "map", "result": {"ok": True, "x1": x1, "x2": x2, "y1": y1, "y2": y2, "levels": levels,
                                                  "liquid": liquid, "buildings": [], "designations": []}}

    def digs(self):
        return [(t, a) for t, a in self.actions if t.startswith("dig")]


def pool(z=161, depth=7):
    return [(x, y, z, depth) for x, y in POOL]


def obs(day, sites, water=None, doors=None, pending=0):
    o = {"date": {"abs_tick": day * DAY}, "map": {"surface_z": SURFACE, "sites": [dict(s) for s in sites]},
         "recent_events": [], "recent_cancellations": [], "dig_designations_pending": pending,
         "dwarves": [{"id": i} for i in range(3)]}
    if water is not None:
        o["water_on_fort_levels"] = water
    if doors is not None:
        o["doors"] = doors
    return {"day": day, "tick": day * DAY, "days_left": 336 - day, "game_over": False, "observation": o}


def fresh(game, day=0, sites=()):
    ov = Overseer(game)
    with redirect_stdout(io.StringIO()):
        ov.load(obs(day, sites))
    ov.count = 0
    return ov


def quiet(fn, *a, **kw):
    buf = io.StringIO()
    with redirect_stdout(buf):
        out = fn(*a, **kw)
    return out, buf.getvalue()


WATER = {"tiles": 30, "deep_tiles": 20, "total_depth": 140}   # the stop's own reading: under the deep-gain trigger


class RealQueryShape(unittest.TestCase):
    def test_success_refusal_and_nested_failure(self):
        ok = {**ENV, "query": "map", "result": {"ok": True, "liquid": []}}
        self.assertEqual(query_result(ok), {"ok": True, "liquid": []})   # no top-level ok on a success
        refused = {**ENV, "ok": False, "error_code": "bad_arguments", "error": "at most 5 levels (|z2 - z| <= 4)"}
        self.assertIsNone(query_result(refused))
        self.assertIsNone(query_result({**ENV, "result": {"ok": False}}))
        self.assertIsNone(query_result(None))

    def test_the_site_probe_reads_the_real_answer(self):
        # the old reader took r.get("ok") (absent on every real success) and counted 0 for every site
        game = MapGame(tiles=pool())
        ov = fresh(game, day=177, sites=[A4, R4, R1, R9, R11])
        self.assertGreater(ov.water_measure(R9, force=True), 0)   # the pool touches R9's dig box
        self.assertEqual(ov.water_measure(R11, force=True), 0)    # the south site is clear of it

    def test_a_refused_probe_is_unmeasured_not_dry(self):
        game = MapGame(tiles=pool(), refuse=True)
        ov = fresh(game, day=177, sites=[A4, R9])
        _, out = quiet(ov.water_measure, R9, force=True)
        self.assertIsNone(ov.water_wetness(R9))
        self.assertIn("bad_arguments", out)
        ov.water_halts["R9"] = 170
        self.assertFalse(quiet(ov.water_ok, R9)[0])   # no reading is no release
        self.assertIn("R9", ov.water_halts)

    def test_a_wet_site_is_never_dug_and_a_dry_one_is(self):
        game = MapGame(tiles=pool())
        ov = fresh(game, day=177, sites=[A4, R4, R1, R9, R11])
        self.assertEqual(quiet(ov.pick_dig_site, [dict(R9), dict(R11)])[0]["id"], "R11")
        self.assertIsNone(quiet(ov.pick_dig_site, [dict(R9)])[0])   # the R9 dig would open the pool


class WetMeansInTheFort(unittest.TestCase):
    def scan(self, tiles, sites):
        game = MapGame(tiles=tiles)
        ov = fresh(game, day=177, sites=sites)
        ov.breach = {"day": 170, "z": SURFACE, "cause": "deep_water_gain"}
        quiet(ov.record_wet_levels)
        return ov

    def test_the_pool_two_tiles_off_the_dwelling_level_marks_nothing(self):
        ov = self.scan(pool(), [A4, R4, R1, S1])
        self.assertEqual(ov.wet_z, set())
        self.assertTrue(ov.dry(161))
        self.assertEqual(ov.fort_water(shallow=True), 0)

    def test_water_inside_a_dug_box_marks_its_level(self):
        # cxe538c50 d187: the pool ran into the dwelling level (98 tiles inside A4 / the rooms)
        inside = [(x, y, 161, 7) for x in range(94, 104) for y in range(90, 95)]
        ov = self.scan(pool() + inside, [A4, R4, R1, S1])
        self.assertEqual(ov.wet_z, {161})
        self.assertFalse(ov.dry(161))
        self.assertGreater(ov.fort_water(shallow=True), 0)

    def test_the_surface_level_is_never_wet(self):
        ov = self.scan([(97, 96, SURFACE, 4)], [A4, S1])
        self.assertEqual(ov.wet_z, set())


class LocalRisingHalt(unittest.TestCase):
    """Decision C. Day 0: the stairs are dug (S1 down to 160), then a water_rising stop."""

    def start(self, tiles=(), sites=(S1, R11, A4)):
        game = MapGame()
        ov = fresh(game, sites=list(sites))
        quiet(ov.load, obs(0, list(sites)))
        ov.shafts["S1"] = 160
        ov.last["stairs"] = 0     # the day-0 dig
        game.tiles = {(x, y, z): dep for x, y, z, dep in tiles}
        return game, ov

    def test_water_outside_every_box_halts_only_the_digs_near_it(self):
        game, ov = self.start(tiles=pool(), sites=(S1, R11, R9, A4))
        quiet(ov.load, obs(1, [S1, R11, R9, A4], water=WATER))
        _, out = quiet(ov.water_rising_stop)
        self.assertIsNone(ov.breach)                       # no fort-wide freeze
        self.assertIsNotNone(ov.rise_watch)
        self.assertIn("water_rising_local", out)
        self.assertEqual(sorted(ov.water_halts), ["R11", "R9", "S1"])   # the stop halts the fronts first...
        game.actions.clear()
        quiet(ov.load, obs(2, [S1, R11, R9, A4], water=WATER))
        quiet(ov.digging)
        dug = [a.get("site") for t, a in game.digs()]
        self.assertIn("R11", dug)                          # ...the site away from the water digs again
        self.assertNotIn("R9", dug)                        # the one beside it stays halted
        self.assertIn("R9", ov.water_halts)

    def test_the_rise_margin_keeps_a_near_site_halted_that_the_plain_margin_would_dig(self):
        near = dict(R11, id="R12", x=88, y=92)             # dig box x88-96, y92-98 (DIG_BOX_R from its corner)
        tiles = [(85, y, 161, 7) for y in range(92, 99)]   # x85: 3 off its x88 edge, outside WATER_DIG_MARGIN
        game, ov = self.start(tiles=tiles, sites=(S1, near, A4))
        self.assertEqual(ov.water_measure(near, force=True), 0)                # the plain dig margin reads dry
        self.assertGreater(ov.water_measure(near, force=True, rise=True), 0)   # RISE_MARGIN sees it
        self.assertGreaterEqual(RISE_MARGIN, 3)
        quiet(ov.load, obs(1, [S1, near, A4], water=WATER))
        quiet(ov.water_rising_stop)
        self.assertIsNone(ov.breach)
        quiet(ov.load, obs(2, [S1, near, A4], water=WATER))
        quiet(ov.digging)
        self.assertNotIn("R12", [a.get("site") for t, a in game.digs()])

    def test_a_real_flood_inside_the_fort_still_halts_everything(self):
        inside = [(x, y, 161, 5) for x in range(92, 100) for y in range(93, 99)]   # in A4, the dwelling level
        game, ov = self.start(tiles=pool() + inside, sites=(S1, E1, R11, A4))
        doors = {"list": [], "door_items_free": 0, "hatch_cover_items_free": 1}
        quiet(ov.load, obs(1, [S1, E1, R11, A4], water=WATER, doors=doors))
        quiet(ov.water_rising_stop)
        self.assertEqual(ov.breach["cause"], "water_rising_after_dig")
        self.assertIsNone(ov.rise_watch)
        game.actions.clear()
        quiet(ov.load, obs(2, [S1, E1, R11, A4], water=WATER, doors=doors))
        quiet(ov.digging)
        self.assertEqual(game.digs(), [])                                  # no dig anywhere
        self.assertIn(("build_door", {"kind": "hatch", "site": "E1"}), game.actions)   # the shaft sealed
        self.assertEqual(ov.wet_z, {161})

    def test_water_in_the_shaft_is_inside_the_fort(self):
        game, ov = self.start(tiles=[(97, 96, 161, 2)])    # the S1 shaft dug to 160
        quiet(ov.load, obs(1, [S1, R11, A4], water=WATER))
        quiet(ov.water_rising_stop)
        self.assertEqual(ov.breach["cause"], "water_rising_after_dig")

    def test_the_local_watch_escalates_when_water_enters_a_box(self):
        game, ov = self.start(tiles=pool(), sites=(S1, R11, A4))
        quiet(ov.load, obs(1, [S1, R11, A4], water=WATER))
        quiet(ov.water_rising_stop)
        self.assertIsNone(ov.breach)
        for x in range(94, 100):                          # day 5: the pool has reached the A level
            game.tiles[(x, 91, 161)] = 3
        game.actions.clear()
        _, out = quiet(ov.load, obs(5, [S1, R11, A4], water=WATER))
        self.assertEqual(ov.breach["cause"], "water_in_fort")
        quiet(ov.digging)
        self.assertEqual(game.digs(), [])

    def test_a_stop_without_a_reading_is_the_full_breach_until_the_fort_reads_dry(self):
        game, ov = self.start(tiles=pool())
        quiet(ov.load, obs(1, [S1, R11, A4], water=WATER))
        game.raise_error = True
        quiet(ov.water_rising_stop)
        self.assertEqual(ov.breach["cause"], "water_rising_unread")   # unknown is never read as safe
        game.raise_error = False
        for day in range(2, 2 + BREACH_CLEAR_SCANS - 1):
            quiet(ov.load, obs(day, [S1, R11, A4], water=WATER))
            self.assertTrue(ov.breach)
        _, out = quiet(ov.load, obs(2 + BREACH_CLEAR_SCANS - 1, [S1, R11, A4], water=WATER))
        self.assertIsNone(ov.breach)
        self.assertIsNotNone(ov.rise_watch)                            # handed down to the local watch
        self.assertIn("flood_outside", out)

    def test_an_unread_stop_with_water_found_inside_is_confirmed(self):
        game, ov = self.start(tiles=pool())
        quiet(ov.load, obs(1, [S1, R11, A4], water=WATER))
        game.raise_error = True
        quiet(ov.water_rising_stop)
        game.raise_error = False
        game.tiles[(97, 96, 161)] = 4                     # in the shaft
        quiet(ov.load, obs(2, [S1, R11, A4], water=WATER))
        self.assertEqual(ov.breach["cause"], "water_rising_after_dig")
        for day in range(3, 3 + BREACH_CLEAR_SCANS + 1):
            game.tiles.pop((97, 96, 161), None)
            quiet(ov.load, obs(day, [S1, R11, A4], water=WATER))
        self.assertTrue(ov.breach)                         # a confirmed rising breach is not released by the scan

    def test_a_rising_stop_with_water_in_the_fort_and_no_recent_dig_is_a_breach(self):
        game, ov = self.start(tiles=[(95, 95, 161, 4)])  # inside A4
        ov.last.clear()
        quiet(ov.load, obs(40, [S1, R11, A4], water=WATER))
        quiet(ov.water_rising_stop)
        self.assertEqual(ov.breach["cause"], "water_rising_in_fort")


class FloodHatch(unittest.TestCase):
    """Audit 4/5: the flood's hatch lock follows water at its column and is released with the breach."""

    def breach_fort(self, tiles, sites, doors, inside=None):
        game = MapGame(tiles=tiles)
        ov = fresh(game, day=13, sites=sites)
        resp = obs(13, sites, water=WATER, doors=doors)
        if inside is not None:
            resp["observation"]["burrows"] = {"civilian_alert": False,
                                              "list": [{"id": 0, "civ_alert_burrow": True, "citizens_inside": inside}]}
            resp["observation"]["administrators"] = {"citizens": 14}
        quiet(ov.load, resp)
        ov.breach = {"day": 12, "z": SURFACE, "cause": "water_rising_after_dig"}
        game.actions.clear()
        return game, ov

    def test_no_lock_while_the_water_is_not_at_the_shaft(self):
        # cxe60d4ce OP1-3: hatch 12 (the only E) was locked days 13-336 for a pool that never reached a room
        doors = {"list": [{"id": 12, "kind": "hatch", "x": 97, "y": 96, "z": SURFACE, "locked": False}],
                 "hatch_cover_items_free": 0}
        game, ov = self.breach_fort(pool(), [E1, A4], doors, inside=0)
        quiet(ov.contain_flood)
        self.assertNotIn("lock_door", [t for t, a in game.actions])

    def test_water_at_the_shaft_locks_it(self):
        doors = {"list": [{"id": 12, "kind": "hatch", "x": 97, "y": 96, "z": SURFACE, "locked": False}],
                 "hatch_cover_items_free": 0}
        game, ov = self.breach_fort([(97, 96, 161, 5)], [E1, A4], doors, inside=0)
        quiet(ov.contain_flood)
        self.assertIn(("lock_door", {"locked": True, "door_id": 12}), game.actions)
        self.assertEqual(ov.flood_locked, {12})

    def test_no_second_hatch_when_the_e_site_leaves_the_list(self):
        # cxe538c50 std OP1-0: E1 left the list on day 169 and a second hatch was built at E2 and locked on day 176
        doors = {"list": [{"id": 33, "kind": "hatch", "x": 97, "y": 96, "z": SURFACE, "locked": True}],
                 "hatch_cover_items_free": 2}
        e2 = dict(E1, id="E2", x=101, y=99)
        game, ov = self.breach_fort([(97, 96, 161, 5)], [e2, A4], doors)
        ov.hatch_id, ov.flood_locked = 33, {33}
        quiet(ov.contain_flood)
        self.assertEqual([a for t, a in game.actions if t == "build_door"], [])
        self.assertEqual(ov.hatch_id, 33)

    def test_no_wildlife_alert_into_a_breach(self):
        game, ov = self.breach_fort([], [E1, A4], {"list": []})
        self.assertTrue(ov.shelter_wet())
        ov.big_units = lambda: [{"_mark": "carnotaurus", "id": 5}]
        bur = {"list": [{"id": 0, "civ_alert_burrow": True}]}
        self.assertFalse(quiet(ov.big_alert, bur, False)[0])
        self.assertNotIn("civilian_alert", [t for t, a in game.actions])
        ov.breach = None
        quiet(ov.big_alert, bur, False)
        self.assertIn("civilian_alert", [t for t, a in game.actions])   # dry again: the beast alert sounds


if __name__ == "__main__":
    unittest.main()
