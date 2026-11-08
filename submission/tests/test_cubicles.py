"""Cell network: 3x3 cells on a 4-tile lattice around a stair hub, a one-tile doorway in every shared wall,
map-checked growth ring by ring, dig -> bed in the middle -> bedroom zone -> doors."""
import io
import unittest
from contextlib import redirect_stdout
from overseer.harness import Overseer, DAY, CELL_RING

SX, SY, Z, R = 50, 50, 140, 11
hub = (SX, SY)


def grid(dug=(), extra=None):
    rows = ["".join("X" if (x, y) == hub else "." if (x, y) in dug else (extra or {}).get((x, y), "#")
                    for x in range(SX - R, SX + R + 1)) for y in range(SY - R, SY + R + 1)]
    return {"ok": True, "x1": SX - R, "y1": SY - R, "liquid": [], "designations": [],
            "levels": [{"z": Z, "shape": rows, "material": ["r" * len(rows[0])] * len(rows)}]}


class FakeGame:
    def __init__(self, m):
        self.calls, self.m = [], m

    def act(self, tool, args):
        self.calls.append((tool, args))
        return {"ok": True, "result": {}}

    def query(self, name, **kw):
        return {"query": name, "result": self.m}


def obs(beds=0, doors=0, day=30, cit=9):
    return {"tick": day * DAY, "day": day, "observation": {
        "administrators": {"citizens": cit}, "stocks": {"logs_usable": 10, "furniture_free": {"bed": beds}},
        "doors": {"list": [], "door_items_free": doors}, "dig_designations_pending": 0,
        "map": {"surface_z": 150, "sites": [{"id": "R9", "kind": "R", "x": SX + 1, "y": SY - 1, "z": Z, "w": 3, "h": 3,
                                             "soil": False, "designated": False, "stair": {"x": SX, "y": SY}}]}}}


def run(ov, o):
    ov.load(o)
    ov.count = 0
    with redirect_stdout(io.StringIO()):
        ov.cubicles()


def coordinate_tools():
    # Coordinate-capable API for geometry tests, NOT the season-0 HTTP schema.
    return [{'function': {'name': name, 'parameters': {'properties': {k: {} for k in fields}}}}
            for name, fields in {
                'dig_room': ('x', 'y', 'z', 'w', 'h'),
                'place_furniture': ('x', 'y', 'z', 'w', 'h'),
                'make_zone': ('x', 'y', 'z', 'w', 'h'),
                'build_door': ('x', 'y', 'z')}.items()]


def fresh(m):
    g = FakeGame(m)
    ov = Overseer(g, goal="", days=336)
    ov.configure_tools(coordinate_tools())
    ov.roles = {"Ra": "office", "Rb": "dorm", "Rc": "dine"}
    return g, ov


class Cells(unittest.TestCase):
    def test_site_only_api_skips_all_cubicle_actions(self):
        g, ov = fresh(grid())
        tools = coordinate_tools()
        for t in tools:
            t['function']['parameters']['required'] = ['site']
        ov.configure_tools(tools)
        def unexpected_query(*args, **kw):
            self.fail('site-only API must not discover a cubicle network')
        g.query = unexpected_query
        run(ov, obs())
        run(ov, obs(day=36))
        self.assertFalse(ov.cell_coordinates)
        self.assertIsNone(ov.net)
        self.assertEqual(g.calls, [])
        self.assertEqual(sum('cubicles unavailable' in s for _, s in ov.findings), 1)

    def test_missing_coordinate_operation_fails_closed(self):
        for omitted in ('dig_room', 'place_furniture', 'make_zone', 'build_door'):
            tools = [t for t in coordinate_tools() if t['function']['name'] != omitted]
            g, ov = fresh(grid())
            ov.configure_tools(tools)
            run(ov, obs())
            self.assertFalse(ov.cell_coordinates)
            self.assertEqual(g.calls, [])
        g, ov = fresh(grid())
        ov.configure_tools([])
        run(ov, obs())
        self.assertEqual(g.calls, [])

    def test_dry_soil_hub_can_start(self):
        # Public real DF OP1 map: revealed 3x3 soil around an excavated stair.
        m = grid()
        m['levels'][0]['material'] = ['s' * len(row) for row in m['levels'][0]['shape']]
        g, ov = fresh(m)
        run(ov, obs())
        self.assertIsNotNone(ov.net)
        self.assertTrue(any(tool == 'dig_room' for tool, _ in g.calls))
        # Soil permission must not relax the independent water exclusion.
        wet = grid()
        wet['levels'][0]['material'] = m['levels'][0]['material']
        wet['liquid'] = [{'x': SX, 'y': SY, 'z': Z, 'depth': 1}]
        g, ov = fresh(wet)
        run(ov, obs())
        self.assertIsNone(ov.net)
        self.assertEqual(g.calls, [])

    def test_start_recovers_after_missing_map(self):
        for missing in (None, {}, {"ok": False}, {"levels": []},
                        {"levels": [{"z": Z - 1, "shape": [], "material": []}]},
                        {"levels": [{"z": Z, "shape": ["#"], "material": ["r"]}]}):
            with self.subTest(missing=missing):
                g, ov = fresh(missing)
                run(ov, obs())
                self.assertIsNone(ov.net)
                self.assertEqual(g.calls, [])
                self.assertNotIn("R9", ov.net_rejected)
                g.m = grid()
                run(ov, obs(day=33))
                self.assertIsNotNone(ov.net)
                self.assertTrue(any(t == "dig_room" for t, _ in g.calls))

    def test_start_outages_do_not_exhaust_lifetime_retry_budget(self):
        g, ov = fresh(None)
        for day in range(30, 66, 3):
            run(ov, obs(day=day))
        self.assertEqual(g.calls, [])
        g.m = grid()
        run(ov, obs(day=66))
        self.assertIsNotNone(ov.net)

    def test_start_still_rate_limited_while_map_missing(self):
        g, ov = fresh(None)
        run(ov, obs())
        g.m = grid()
        run(ov, obs(day=31))
        self.assertIsNone(ov.net)
        run(ov, obs(day=33))
        self.assertIsNotNone(ov.net)

    def test_start_rejects_known_unsafe_terrain(self):
        g, ov = fresh(grid(extra={(SX + 2, SY): "^"}))
        run(ov, obs())
        self.assertIsNone(ov.net)
        self.assertIn("R9", ov.net_rejected)
        self.assertEqual(g.calls, [])

    def test_nonwall_boundary_cannot_seal_a_cell(self):
        for shape in (" ", "^", "v", "P", "F", "b", "t"):
            with self.subTest(shape=shape):
                m = grid(extra={(SX + 2, SY): shape})
                tiles = [t for t in Overseer.cell_tiles(hub, (0, 0)) if t != hub]
                self.assertFalse(Overseer.cell_fits(tiles, [], hub, Z, m))

    def test_flooded_floor_not_ready_for_furniture(self):
        g, ov = fresh(grid())
        run(ov, obs())
        g.m = grid(dug=set(ov.net_tiles()))
        # Shape remains FLOOR under water; water is a separate map field.
        g.m["liquid"] = [{"x": x, "y": y, "z": Z, "depth": 7}
                         for x, y in ov.net_tiles()]
        g.calls.clear()
        run(ov, obs(beds=4, doors=4, day=33))
        self.assertFalse(any(t in ("place_furniture", "make_zone", "build_door") for t, _ in g.calls))

    def test_flood_after_completed_dig_rechecks_readiness(self):
        g, ov = fresh(grid())
        run(ov, obs())
        # Simulate a finished network with no furniture available yet.
        for v in list(ov.net["cells"].values()) + list(ov.net["doors"].values()):
            v["dug"] = True
        ov.last["net_grow"] = 33 * DAY  # isolate readiness from further growth
        g.m = grid(dug=set(ov.net_tiles()))
        g.m["liquid"] = [{"x": x, "y": y, "z": Z, "depth": 7}
                         for x, y in ov.net_tiles()]
        g.calls.clear()
        run(ov, obs(beds=4, doors=4, day=33))
        self.assertFalse(any(t in ("place_furniture", "make_zone", "build_door") for t, _ in g.calls))

    def test_missing_map_does_not_reuse_completed_floor(self):
        g, ov = fresh(grid())
        run(ov, obs())
        for v in list(ov.net["cells"].values()) + list(ov.net["doors"].values()):
            v["dug"] = True
        ov.last["net_grow"] = 33 * DAY
        g.m = {}
        g.calls.clear()
        run(ov, obs(beds=4, doors=4, day=33))
        self.assertFalse(any(t in ("place_furniture", "make_zone", "build_door") for t, _ in g.calls))

    def test_flooded_cell_can_recover_after_drain(self):
        g, ov = fresh(grid())
        run(ov, obs())
        tiles = set(ov.net_tiles())
        g.m = grid(dug=tiles)
        g.m["liquid"] = [{"x": x, "y": y, "z": Z, "depth": 7} for x, y in tiles]
        run(ov, obs(beds=4, day=33))
        g.m = grid(dug=tiles)
        g.calls.clear()
        run(ov, obs(beds=4, day=34))
        self.assertEqual(sum(t == "place_furniture" for t, _ in g.calls), 4)

    def test_lattice_every_wall_has_a_doorway(self):
        T = Overseer.cell_tiles
        near = lambda a, b: max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 1
        cells = [(i, j) for i in range(-CELL_RING, CELL_RING + 1) for j in range(-CELL_RING, CELL_RING + 1)]
        for c in cells:
            for e in cells:
                if c < e:
                    self.assertFalse(set(T(hub, c)) & set(T(hub, e)))
                    if abs(c[0] - e[0]) + abs(c[1] - e[1]) == 1:
                        t = Overseer.door_tile(hub, c, e)
                        # the doorway touches both rooms orthogonally and is flanked by wall on its other two sides
                        self.assertTrue(any(abs(t[0] - u[0]) + abs(t[1] - u[1]) == 1 for u in T(hub, c)))
                        self.assertTrue(any(abs(t[0] - u[0]) + abs(t[1] - u[1]) == 1 for u in T(hub, e)))
                        ax = (t[0], t[1] - 1), (t[0], t[1] + 1) if c[0] != e[0] else ((t[0] - 1, t[1]), (t[0] + 1, t[1]))
                        flanks = ((t[0], t[1] - 1), (t[0], t[1] + 1)) if c[0] != e[0] else ((t[0] - 1, t[1]), (t[0] + 1, t[1]))
                        for f in flanks:
                            self.assertFalse(any(f in T(hub, q) for q in cells))
        self.assertEqual(Overseer.cell_centre(hub, (1, -1)), (SX + 4, SY - 4))

    def test_growth_and_furnish(self):
        g, ov = fresh(grid())
        run(ov, obs())
        n = ov.net
        self.assertEqual(sorted(n["cells"]), [(-1, 0), (0, -1), (0, 0), (0, 1), (1, 0)])
        self.assertEqual(len(n["doors"]), 4)                                     # each cross cell opens onto the hub
        self.assertEqual(sum(1 for t, _ in g.calls if t == "dig_room"), 5 + 4)
        dug = set(ov.net_tiles())
        g.m = grid(dug=dug)
        g.calls.clear()
        run(ov, obs(beds=4, day=33))
        tools = [t for t, _ in g.calls]
        self.assertEqual([(a["x"], a["y"]) for t, a in g.calls if t == "place_furniture"],
                         [Overseer.cell_centre(hub, c) for c in [(-1, 0), (0, -1), (0, 1), (1, 0)]])
        self.assertEqual(tools.count("make_zone"), 4)
        self.assertIn(("add_order", {"recipe": "make_door", "amount": 4}), g.calls)
        # the corners joined: each touches two cross cells, so it gets two doorways
        self.assertEqual(len(n["cells"]), 9)
        self.assertEqual(len(n["doors"]), 12)
        g.calls.clear()
        run(ov, obs(doors=6, day=36))
        built = sorted((a["x"], a["y"]) for t, a in g.calls if t == "build_door")
        self.assertEqual(built, sorted(Overseer.door_tile(hub, (0, 0), c) for c in [(-1, 0), (0, -1), (0, 1), (1, 0)]))

    def test_leak_and_water_rejected(self):
        g, ov = fresh(grid(dug={(SX + 6, SY)}))                                 # an old dig beside cell (1,0)
        run(ov, obs())
        self.assertNotIn((1, 0), ov.net["cells"])
        self.assertIn((0, 1), ov.net["cells"])
        wet = grid()
        wet["liquid"] = [{"x": SX + 3, "y": SY + 3, "z": Z - 1, "depth": 4}]
        g, ov = fresh(wet)
        run(ov, obs())
        self.assertIsNone(ov.net)
        self.assertEqual([t for t, _ in g.calls], [])


if __name__ == "__main__":
    unittest.main()
