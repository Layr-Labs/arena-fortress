"""d42: housing that outgrows its rooms (open tasks). Beds go to the first site place_furniture takes when the dorm
level is too wide or full; when no site can take more beds or dining seats, one more 3x3 room is dug for them, one at
a time; the labs are untouched."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import StubGame, resp  # noqa: E402
from overseer import harness as H  # noqa: E402
from overseer.harness import Overseer  # noqa: E402


class PlaceGame(StubGame):
    """place_furniture answers with the tiles it used from the site's top-left, or no_space for a site in `full`;
    make_zone answers a zone id."""

    def __init__(self, sites, full=()):
        super().__init__(herd=[])
        self.sites, self.full = {s["id"]: s for s in sites}, set(full)

    def act(self, tool, args):
        r = super().act(tool, args)
        if tool == "place_furniture":
            if args["site"] in self.full:
                return {"ok": False, "error_code": "no_space", "error": "scripted"}
            s, n = self.sites[args["site"]], args.get("count", 1)
            at = [[s["x"] + i % 3, s["y"] + i // 3, s["z"]] for i in range(n)]
            return {"ok": True, "result": {"placed": args["kind"], "n": n, "at": at if n > 1 else at[0]}}
        if tool == "make_zone":
            return {"ok": True, "result": {"zone": args["kind"], "zone_id": 700 + len(self.calls)}}
        return r


WIDE = {"id": "A9", "kind": "A", "x": 60, "y": 60, "z": 150, "w": 45, "h": 12, "open_tiles": 140}
SMALL = {"id": "A3", "kind": "A", "x": 80, "y": 90, "z": 149, "w": 12, "h": 6, "open_tiles": 50}
ROOM = {"id": "R5", "kind": "R", "x": 70, "y": 95, "z": 148, "w": 3, "h": 3, "dug": True, "designated": True,
        "free": True}
UNDUG = {"id": "R6", "kind": "R", "x": 74, "y": 95, "z": 148, "w": 3, "h": 3}


def fort(sites, day=30, cit=12, free=None, furniture=(), zones=(), lab=False):
    r = resp(186, day, food=200, drink=300, cit=cit)
    o = r["observation"]
    o["map"].update(surface_z=155, sites=[dict(s) for s in sites])
    o["furniture"] = [dict(f) for f in furniture]
    o["furniture_total"] = len(furniture)
    o["zones"] = [dict(z) for z in zones]
    o["stocks"]["furniture_free"] = dict(free or {})
    g = PlaceGame([dict(s) for s in sites])
    ov = Overseer(g, goal="Run the fortress", days=216)
    ov.set_task({"goal": "Run the fortress.", **({"hands_off": {"from_day": 30, "days": 10}} if lab else {})})
    ov.load(r)
    ov.count = 0
    return ov, g


def beds(g):
    return [(a["site"], a.get("count")) for t, a in g.calls if t == "place_furniture" and a["kind"] == "bed"]


def row(i, kind, x, y, z, zones=(), built=True):
    return {"id": i, "kind": kind, "x": x, "y": y, "z": z, "built": built, "zone_ids": list(zones)}


class D42(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_beds_go_to_a_level_place_furniture_takes_when_the_dorm_level_is_too_wide(self):
        ov, g = fort([WIDE, SMALL], free={"bed": 6})
        self.assertEqual(ov.room_for("dorm")["id"], "A9")          # the usual dorm site: 45 wide
        ov.furnish()
        self.assertEqual(beds(g), [("A3", 6)])

    def test_a_refusal_moves_the_beds_on_in_the_same_pass(self):
        ov, g = fort([SMALL, ROOM], free={"bed": 5})
        g.full = {"A3"}
        ov.furnish()
        self.assertEqual(beds(g), [("A3", 5), ("R5", 5)])
        self.assertIn("A3", ov.bed_full)
        ov.now += 2 * H.DAY
        ov.furnish()
        self.assertEqual(beds(g)[-1], ("R5", 5))                   # the full level waits for its box to change

    def test_a_room_another_role_uses_takes_no_beds(self):
        farm = dict(ROOM, id="R7", used_by=["farm plot 4"], free=False)
        office = dict(ROOM, id="R8", x=90)
        ov, g = fort([WIDE, farm, office], free={"bed": 5})
        ov.roles.update(R8="office")
        ov.furnish()
        self.assertEqual(beds(g), [])

    def test_a_room_is_dug_for_beds_when_no_site_takes_them(self):
        ov, g = fort([WIDE, UNDUG], free={"bed": 5}, furniture=[row(i, "bed", 61 + i, 61, 150) for i in range(8)])
        ov.house_rooms()
        self.assertEqual(g.tools("dig_room"), [{"site": "R6"}])
        self.assertEqual(ov.roles.get("R6"), "beds")
        ov.now += 4 * H.DAY
        ov.house_rooms()                                           # one at a time: R6 is not dug yet
        self.assertEqual(len(g.tools("dig_room")), 1)

    def test_no_room_before_the_layers_own_rooms_or_when_nothing_is_short(self):
        ov, g = fort([WIDE, UNDUG], day=5, free={"bed": 5})
        ov.house_rooms()
        ov2, g2 = fort([WIDE, UNDUG], free={"bed": 5}, furniture=[row(i, "bed", 61 + i, 61, 150) for i in range(12)])
        ov2.house_rooms()
        self.assertEqual(g.tools("dig_room") + g2.tools("dig_room"), [])

    def test_a_full_dining_room_gets_a_new_room_its_chairs_and_a_dining_zone(self):
        level = {"id": "A6", "kind": "A", "x": 90, "y": 94, "z": 160, "w": 37, "h": 8, "open_tiles": 114}
        dine = {"id": "R3", "kind": "R", "x": 90, "y": 95, "z": 160, "w": 3, "h": 3, "dug": True, "designated": True,
                "free": False, "used_by": ["DiningHall 49"]}
        new = {"id": "R7", "kind": "R", "x": 90, "y": 95, "z": 158, "w": 3, "h": 3}
        zone = {"id": 49, "type": "DiningHall", "x": 90, "y": 95, "z": 160, "w": 3, "h": 3}
        furn = ([row(i, "table", 90 + i % 3, 95 + i // 3, 160, [49]) for i in range(4)]
                + [row(10 + i, "chair", 90 + (4 + i) % 3, 95 + (4 + i) // 3, 160, [49]) for i in range(4)])
        ov, g = fort([level, dine, new], cit=16, free={"table": 3, "chair": 5}, furniture=furn, zones=[zone])
        ov.roles.update(R3="dine")
        ov.dine_full["R3"] = ov.fill_mark(dine)                   # place_furniture answered no_space there
        self.assertIsNone(ov.dine_site())
        ov.house_rooms()
        self.assertEqual(g.tools("dig_room"), [{"site": "R7"}])
        self.assertEqual(ov.roles.get("R7"), "dine_more")
        dug = dict(new, dug=True, designated=True, free=True)
        r = resp(170, 46, food=200, drink=300, cit=16)
        o = r["observation"]
        o["map"].update(surface_z=161, sites=[dict(level), dict(dine), dug])
        o["furniture"], o["furniture_total"] = [dict(f) for f in furn], len(furn)
        o["zones"] = [dict(zone)]
        o["stocks"]["furniture_free"] = {"table": 3, "chair": 5}
        g.sites["R7"] = dug
        ov.load(r)
        self.assertEqual(ov.dine_site()["id"], "R7")
        ov.furnish()
        placed = [(a["kind"], a["site"], a.get("count")) for t, a in g.calls if t == "place_furniture"]
        self.assertEqual(placed, [("table", "R7", 3), ("chair", "R7", 5)])
        self.assertIn({"kind": "dining_hall", "site": "R7"}, g.tools("make_zone"))

    def test_at_most_house_rooms_extra_rooms(self):
        extra = [dict(ROOM, id="R%d" % (10 + i), x=10 * i) for i in range(H.HOUSE_ROOMS)]
        ov, g = fort([WIDE, UNDUG] + extra, free={"bed": 5})
        for i in range(H.HOUSE_ROOMS):
            ov.roles["R%d" % (10 + i)] = "beds"
            ov.bed_full["R%d" % (10 + i)] = ov.fill_mark(extra[i])
        ov.house_rooms()
        self.assertEqual(g.tools("dig_room"), [])

    def test_the_labs_keep_their_bed_step_and_dig_no_rooms(self):
        ov, g = fort([WIDE, SMALL, UNDUG], free={"bed": 6}, lab=True)
        ov.house_rooms()
        ov.furnish()
        self.assertEqual(g.tools("dig_room"), [])
        self.assertEqual(beds(g), [("A9", 6)])                    # the labs' step: the dorm site, as before

    def test_unreadable_site_fields_skip_that_site(self):
        bad = dict(SMALL, id="A4", w="ERR", open_tiles="ERR")
        ov, g = fort([WIDE, bad, ROOM], free={"bed": 4})
        ov.furnish()
        self.assertEqual(beds(g), [("R5", 4)])


if __name__ == "__main__":
    unittest.main()
