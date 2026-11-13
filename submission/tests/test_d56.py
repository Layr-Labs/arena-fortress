"""d56: rooms are dug only where the map shows no water, ice or magma in the box or next to it on its level (open
tasks). dig_room measures w,h from the R site's top-left corner, so a 9x7 dormitory reached a river one level down on
MY1 1025-p and a dwarf drowned on day 3. A wet box shrinks from the same corner; a room with no dry box is left undug
and the next room takes its role; a failed map query digs as before; the labs never ask."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import resp  # noqa: E402
from test_d42 import PlaceGame, row  # noqa: E402
from overseer import harness as H  # noqa: E402
from overseer.harness import Overseer  # noqa: E402

SURFACE = 126
RIVER = [(x, y) for x in range(98, 104) for y in range(90, 100)]      # 1025-p: the river starts at x 98 on z 125


class MapGame(PlaceGame):
    """The map query answers the given water tiles (liquid) and, optionally, ice tiles (material 'i') on one level,
    each limited to the box the query asked for."""

    def __init__(self, sites, water=(), ice=(), level=SURFACE - 1, map_error=False, ok=True):
        super().__init__(sites)
        self.water, self.ice, self.level, self.map_error, self.ok = set(water), set(ice), level, map_error, ok
        self.maps = []

    def query(self, name, **kw):
        if name != "map":
            return super().query(name, **kw)
        self.maps.append(dict(kw))
        if self.map_error:
            raise H.GameAPIError("scripted")
        if not self.ok:
            return {"result": {"ok": False, "error_code": "bad_arguments"}}
        R, cx, cy, z = kw["radius"], kw["x"], kw["y"], kw["z"]
        x1, y1 = cx - R, cy - R
        inside = lambda p: x1 <= p[0] <= cx + R and y1 <= p[1] <= cy + R   # noqa: E731
        liquid = [{"x": x, "y": y, "z": z, "depth": 7} for x, y in sorted(self.water) if inside((x, y))] \
            if z == self.level else []
        rows = ["".join("i" if z == self.level and (x, y) in self.ice else "r" for x in range(x1, cx + R + 1))
                for y in range(y1, cy + R + 1)]
        return {"result": {"ok": True, "x1": x1, "y1": y1, "liquid": liquid,
                           "levels": [{"z": z, "material": rows, "shape": ["#" * len(rows[0])] * len(rows)}]}}


def room(rid, x, y, z=SURFACE - 1, soil=False):
    return {"id": rid, "kind": "R", "x": x, "y": y, "z": z, "w": 3, "h": 3, "soil": soil}


def fort(sites, lab=False, day=1, free=None, furniture=(), farm_plots=4, **kw):
    r = resp(216 - day, day, food=200, drink=300, cit=11)
    o = r["observation"]
    o["map"].update(surface_z=SURFACE, sites=[dict(s) for s in sites])
    o["farm_plots"] = [{"id": i, "x": 0, "y": 0, "z": 160} for i in range(farm_plots)]   # farms there already
    o["furniture"], o["furniture_total"], o["zones"] = [dict(f) for f in furniture], len(furniture), []
    o["stocks"]["furniture_free"] = dict(free or {})
    g = MapGame([dict(s) for s in sites], **kw)
    ov = Overseer(g, goal="Run the fortress", days=216)
    ov.set_task({"goal": "Run the fortress.", **({"hands_off": {"from_day": 30, "days": 10}} if lab else {})})
    ov.load(r)
    ov.count = 0
    return ov, g


def digs(g):
    return [a for t, a in g.calls if t == "dig_room"]


class D56(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_the_1025_dormitory_shrinks_to_a_dry_box(self):
        # R2 at 92,93: 9x7 reaches x 100 (river from 98), 7x5 reaches 98, 5x5 reaches 96 with 97 dry beside it
        ov, g = fort([room("R2", 92, 93), room("R3", 85, 93), room("R4", 92, 93, z=SURFACE - 2)], water=RIVER)
        ov.digging()
        self.assertEqual(digs(g)[0], {"site": "R2", "w": 5, "h": 5})
        self.assertEqual(ov.roles["R2"], "dorm")

    def test_a_dry_fort_digs_exactly_as_before(self):
        ov, g = fort([room("R2", 92, 93), room("R3", 85, 93), room("R4", 92, 93, z=SURFACE - 2)])
        ov.digging()
        self.assertEqual(digs(g), [{"site": "R2", "w": 9, "h": 7}, {"site": "R3", "w": 7, "h": 5}, {"site": "R4"}])

    def test_water_beside_a_3x3_box_leaves_the_room_undug_and_the_next_room_takes_the_role(self):
        ov, g = fort([room("R2", 97, 93), room("R3", 85, 93), room("R4", 85, 93, z=SURFACE - 2)], water=RIVER)
        ov.digging()
        self.assertEqual([a["site"] for a in digs(g)], ["R3", "R4"])
        self.assertNotIn("R2", ov.roles)
        self.assertEqual(ov.roles["R3"], "dorm")
        n = len(g.maps)
        ov.digging()                                   # decided once: no new query, still not dug
        self.assertEqual((len(g.maps), [a["site"] for a in digs(g)].count("R2")), (n, 0))

    def test_ice_beside_the_box_is_wet(self):
        ice = [(x, 98) for x in range(80, 110)]        # y 98: inside 9x7 (93..99), beside 5x5 (93..97), clear of 5x3
        ov, g = fort([room("R2", 92, 93), room("R3", 85, 90)], ice=ice)
        ov.digging()
        self.assertEqual(digs(g)[0], {"site": "R2", "w": 5, "h": 3})

    def test_a_failed_map_query_digs_as_before(self):
        for kw in ({"map_error": True}, {"ok": False}):
            ov, g = fort([room("R2", 92, 93), room("R3", 85, 93)], water=RIVER, **kw)
            ov.digging()
            self.assertEqual(digs(g)[:2], [{"site": "R2", "w": 9, "h": 7}, {"site": "R3", "w": 7, "h": 5}])

    def test_a_lab_task_never_asks_the_map(self):
        ov, g = fort([room("R2", 92, 93), room("R3", 85, 93)], water=RIVER, lab=True)
        ov.digging()
        self.assertEqual(g.maps, [])
        self.assertEqual(digs(g)[0], {"site": "R2", "w": 9, "h": 7})

    def test_a_farm_room_beside_water_is_not_dug(self):
        ov, g = fort([room("R2", 97, 93, soil=True), room("R3", 85, 93, soil=True)], water=RIVER, farm_plots=0)
        ov.digging()
        self.assertEqual([a for a in digs(g) if a["site"] == "R2"], [])
        self.assertIn({"site": "R3"}, digs(g))

    def test_an_extra_room_for_beds_skips_a_wet_room(self):
        wide = {"id": "A9", "kind": "A", "x": 60, "y": 60, "z": 150, "w": 45, "h": 12, "open_tiles": 140}
        ov, g = fort([wide, room("R6", 97, 93), room("R7", 85, 93)], water=RIVER, day=30, free={"bed": 5},
                     furniture=[row(i, "bed", 61 + i, 61, 150) for i in range(8)])
        ov.house_rooms()
        self.assertEqual(digs(g), [{"site": "R7"}])


if __name__ == "__main__":
    unittest.main()
