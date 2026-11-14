"""d44: the review's fixes to the housing rooms. Beds stay off office and dining floors (place_furniture fills a box
row by row whatever zone a tile is in), rooms are not dug under another zone, a spent dig or bed key moves on to
the next room or site."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from test_d42 import fort, row, beds, WIDE, SMALL, ROOM, UNDUG  # noqa: E402
from overseer.harness import DAY  # noqa: E402


class TileStub:
    """Box occupancy and the zone refusals of the manual: place_furniture takes the first free floor tiles of the
    box in row order; make_zone refuses a box over 20 a side, and an R room a zone already overlaps."""

    def __init__(self, sites, floor, free):
        self.sites = {s["id"]: dict(s) for s in sites}
        self.floor, self.free = set(floor), dict(free)
        self.rows, self.zones, self.calls = [], [], []

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool not in ("make_zone", "place_furniture"):
            return {"ok": True, "result": {}}
        s = self.sites[args["site"]]
        side = 20 if tool == "make_zone" else 40
        if s["w"] > side or s["h"] > side:
            return {"ok": False, "error_code": "bad_arguments"}
        if tool == "make_zone":
            if s["kind"] == "R" and any(self.meets(z, s) for z in self.zones):
                return {"ok": False, "error_code": "site_used"}
            zid = 700 + len(self.zones)
            self.zones.append(dict(s, id=zid, type=args["kind"]))
            return {"ok": True, "result": {"zone_id": zid}}
        k, n = args["kind"], args.get("count", 1)
        if not self.free.get(k):
            return {"ok": False, "error_code": "no_material"}
        taken = {(r["x"], r["y"], r["z"]) for r in self.rows}
        free = sorted((p for p in self.floor - taken if self.inside(s, p)), key=lambda p: (p[1], p[0]))
        at = free[:min(n, self.free[k])]
        if not at:
            return {"ok": False, "error_code": "no_space"}
        for p in at:
            self.rows.append(row(len(self.rows), k, *p, built=False))
        self.free[k] -= len(at)
        return {"ok": True, "result": {"n": len(at), "at": [list(p) for p in at] if n > 1 else list(at[0])}}

    def tools(self, name):
        return [a for t, a in self.calls if t == name]

    @staticmethod
    def inside(s, p):
        return p[2] == s["z"] and s["x"] <= p[0] < s["x"] + s["w"] and s["y"] <= p[1] < s["y"] + s["h"]

    @staticmethod
    def meets(a, b):
        return (a["z"] == b["z"] and a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
                and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])


class D44(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_an_office_made_this_pass_keeps_its_floor(self):
        office_room = dict(ROOM, id="R8", x=80, y=90, z=149)
        office_level = dict(SMALL, w=3, h=4, open_tiles=10)
        ov, _ = fort([WIDE, office_level, office_room], cit=20, free={"bed": 10})
        ov.adm["MANAGER_id"] = 0
        ov.roles["R8"] = "office"
        floor = [(x, y, 149) for y in range(90, 93) for x in range(80, 83)]
        ov.game = g = TileStub(ov.sites, floor, {"bed": 10, "chair": 0})
        ov.office_open()
        self.assertEqual(g.tools("make_zone"), [{"kind": "office", "site": "R8"}])
        ov.furnish()
        self.assertEqual(beds(g), [])
        g.free["chair"] = 1
        self.assertTrue(g.act("place_furniture", {"kind": "chair", "site": "R8"})["ok"])

    def test_beds_leave_a_dining_room_alone(self):
        dine_room = dict(ROOM, id="R8", x=80, y=90, z=149)
        dine_level = dict(SMALL, w=21, h=4, open_tiles=50)
        ov, _ = fort([WIDE, dine_level, dine_room], cit=20, free={"bed": 10, "table": 3, "chair": 3})
        ov.roles["R8"] = "dine"
        self.assertNotIn("A3", [s["id"] for s in ov.bed_sites(ov.room_for("dorm"))])
        floor = [(x, y, 149) for y in range(90, 93) for x in range(80, 83)]
        ov.game = g = TileStub(ov.sites, floor, ov.free)
        ov.furnish()
        self.assertEqual(sorted(f["kind"] for f in g.rows), ["chair"] * 3 + ["table"] * 3)

    def test_no_room_is_dug_under_another_zone(self):
        r1 = dict(UNDUG, x=70, y=62, z=150)
        r2 = dict(r1, id="R7", x=74)
        dorm_zone = {"id": 42, "type": "Dormitory", "x": 65, "y": 60, "z": 150, "w": 15, "h": 10}
        furniture = [row(i, "bed", 61 + i, 61, 150) for i in range(12)]
        ov, g = fort([WIDE, r1, r2], free={"table": 2, "chair": 2}, furniture=furniture, zones=[dorm_zone])
        self.assertIsNone(ov.dine_site())
        ov.house_rooms()
        self.assertEqual(g.tools("dig_room"), [])

    def test_a_dining_zone_holding_the_whole_room_is_welcome(self):
        r1 = dict(UNDUG, x=70, y=62, z=150)
        dining = {"id": 43, "type": "DiningHall", "x": 68, "y": 61, "z": 150, "w": 6, "h": 5}
        ov, g = fort([WIDE, r1], free={"table": 2, "chair": 2}, zones=[dining])
        ov.house_rooms()
        self.assertEqual(g.tools("dig_room"), [{"site": "R6"}])

    def test_two_dig_refusals_move_on_to_the_next_room(self):
        nxt = dict(UNDUG, id="R7", x=80)
        ov, g = fort([WIDE, UNDUG, nxt], free={"bed": 5})
        original = g.act

        def refuse_r6(tool, args):
            if tool == "dig_room" and args["site"] == "R6":
                g.calls.append((tool, dict(args)))
                return {"ok": False, "error_code": "internal_error", "error": "scripted"}
            return original(tool, args)
        g.act = refuse_r6
        for _ in range(8):
            ov.house_rooms()
            ov.now += 4 * DAY
        self.assertEqual(g.tools("dig_room"), [{"site": "R6"}, {"site": "R6"}, {"site": "R7"}])
        self.assertEqual(ov.roles.get("R7"), "beds")

    def test_a_spent_bed_key_moves_on_to_the_next_site(self):
        ov, g = fort([SMALL, ROOM, UNDUG], free={"bed": 5})
        ov.tries["beds_A3"] = 98
        original = g.act

        def no_material(tool, args):
            if tool == "place_furniture" and args["kind"] == "bed" and args["site"] == "A3":
                g.calls.append((tool, dict(args)))
                return {"ok": False, "error_code": "no_material", "error": "scripted"}
            return original(tool, args)
        g.act = no_material
        ov.furnish()
        g.act = original
        ov.now += 2 * DAY
        ov.furnish()
        self.assertEqual([s["id"] for s in ov.bed_sites(ov.room_for("dorm"))], ["R5"])
        self.assertEqual(beds(g)[-1], ("R5", 5))

    def test_a_partial_placement_sends_only_the_rest_on(self):
        ov, g = fort([SMALL, ROOM], free={"bed": 5})
        original = g.act

        def partial(tool, args):
            if tool == "place_furniture" and args["kind"] == "bed" and args["site"] == "A3":
                g.calls.append((tool, dict(args)))
                return {"ok": True, "result": {"n": 2, "at": [[80, 90, 149], [81, 90, 149]]}}
            return original(tool, args)
        g.act = partial
        ov.furnish()
        self.assertEqual(beds(g), [("A3", 5), ("R5", 3)])
        self.assertIn("A3", ov.bed_full)

    def test_the_labs_and_goal_policies_skip_the_new_paths(self):
        for mode in ("lab", "hands_off", "beds_first", "drink_growth", "surge"):
            ov, g = fort([WIDE, UNDUG], free={"bed": 5})
            setattr(ov, mode, 5 if mode == "hands_off" else True)
            ov.house_rooms()
            ov.furnish()
            self.assertEqual(g.tools("dig_room"), [])
            self.assertEqual(beds(g), [("A9", 5)])


if __name__ == "__main__":
    unittest.main()
