"""cx confirmed floor / audit 2, 3, 6 (harness.py FAR_FLOOR_MIN, NOFLOOR_DAYS): far, seat and meeting boxes on an A site
count only on floor a map query shows in the corner box the API addresses, a box that answered "no free floor tile"
is not knocked on again until its site reads differently, and a fort with no real far box keeps its dining near.
The sites, zones, plots and map shapes are the records' own (real_maps.py): hint hard MY1-3 on 0b49063 / d57f599
(s92315: A1 x67 y66 w61 h56, open_tiles 114, "no free floor tile in 67,66,143 (20x20)" every pass) and hint hard
MY1-4 on d57f599 (s93005: shaft_dine_wait days 0-20 with the handover DiningHall on A2, A4's far cut over the plot
rooms). No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_danger_marks import FakeGame, fort, Quiet  # noqa: E402
from real_maps import MapQueries  # noqa: E402
from overseer import harness  # noqa: E402

ROCK = "no free floor tile in 67,66,143 (20x20): every tile is wall, undug, built on or designated"

# hint hard MY1-3, day 0 (cx0b49063 harness-3.api.jsonl /observe)
E1_3 = {"id": "E1", "kind": "E", "x": 95, "y": 102, "z": 144, "w": 1, "h": 1, "building": True}
A1_3 = {"id": "A1", "kind": "A", "x": 67, "y": 66, "z": 143, "w": 61, "h": 56, "open_tiles": 114, "subterranean": True}
A2_3 = {"id": "A2", "kind": "A", "x": 90, "y": 101, "z": 142, "w": 17, "h": 3, "open_tiles": 49, "subterranean": True}
R1_3 = {"id": "R1", "kind": "R", "x": 92, "y": 101, "z": 143, "w": 3, "h": 3, "soil": True, "dug": False}
ZONES_3 = [{"id": 38, "type": "DiningHall", "x": 90, "y": 101, "z": 142, "w": 5, "h": 3,
            "furniture": {"table": 3, "chair": 3}},
           {"id": 39, "type": "Dormitory", "x": 96, "y": 101, "z": 142, "w": 11, "h": 3}]
BEDS_3 = [{"built": True, "kind": "bed", "x": x, "y": y, "z": 142, "zone_ids": [39]}
          for x in range(96, 107) for y in (101, 103)]
PLOTS_3 = [{"built": True, "id": i, "x": x, "y": 101, "z": 143, "w": 3, "h": 3} for i, x in ((9, 96), (7, 100), (8, 104))]

# hint hard MY1-4 on d57f599, day 20 (s93005 /observe)
E1_4 = {"id": "E1", "kind": "E", "x": 100, "y": 101, "z": 169, "w": 1, "h": 1, "building": True}
A2_4 = {"id": "A2", "kind": "A", "x": 95, "y": 100, "z": 167, "w": 17, "h": 3, "open_tiles": 49, "subterranean": True}
A4_4 = {"id": "A4", "kind": "A", "x": 94, "y": 90, "z": 168, "w": 18, "h": 13, "open_tiles": 53, "subterranean": True}
R2_4 = {"id": "R2", "kind": "R", "x": 98, "y": 90, "z": 168, "w": 3, "h": 3, "dug": True, "designated": True,
        "free": False, "used_by": ["farm plot 55"]}
R3_4 = {"id": "R3", "kind": "R", "x": 94, "y": 90, "z": 168, "w": 3, "h": 3, "dug": True, "designated": True,
        "free": False, "used_by": ["farm plot 54"]}
ZONES_4 = [{"id": 38, "type": "Dormitory", "x": 101, "y": 100, "z": 167, "w": 11, "h": 3},
           {"id": 39, "type": "DiningHall", "x": 95, "y": 100, "z": 167, "w": 5, "h": 3,
            "furniture": {"table": 3, "chair": 3}},
           {"id": 56, "type": "MeetingHall", "x": 94, "y": 90, "z": 168, "w": 18, "h": 6}]
BEDS_4 = [{"built": True, "kind": "bed", "x": x, "y": y, "z": 167, "zone_ids": [38]}
          for x in range(101, 112) for y in (100, 102)]
PLOTS_4 = [{"built": True, "id": i, "x": x, "y": y, "z": 168, "w": 3, "h": 3}
           for i, (x, y) in enumerate(((101, 100), (109, 100), (105, 100), (94, 90), (98, 90)))]


def look(day, sites, zones, beds, plots, surface, cit=15, free=None):
    r = fort(day, dwarves=[{"id": 95 + i, "name": "Urist", "x": 98, "y": 102, "z": surface - 2} for i in range(cit)])
    o = r["observation"]
    o["administrators"]["citizens"] = cit
    o["map"]["surface_z"] = surface
    o["map"]["sites"] = [dict(s) for s in sites]
    o["doors"] = {"list": [], "hatch_cover_items_free": 0, "door_items_free": 0}
    o["zones"] = [dict(z) for z in zones]
    o["farm_plots"] = [dict(p) for p in plots]
    o["furniture"] = [dict(b) for b in beds]
    o["stocks"]["furniture_free"] = dict(free or {"table": 6, "chair": 6})
    return r


class Game(MapQueries, FakeGame):
    """The record's map; place_furniture answers like place.lua: no free floor in a box with none."""
    def __init__(self, grid, plots):
        super().__init__([])
        self.grid, self.plots = grid, list(plots)
        self.answers = {}

    def act(self, tool, args):
        r = super().act(tool, args)
        if tool == "place_furniture":
            key = (args.get("site"), args.get("w"), args.get("h"))
            if key in self.answers:
                return self.answers[key]
            k = args.get("count", 1)
            r = {"ok": True, "result": {"n": k, "at": [[0, i, 0] for i in range(k)]}}
        return r


class ConfirmedFloor(Quiet):
    def ov(self, resp, grid):
        game = Game(grid, resp["observation"]["farm_plots"])
        ov = harness.Overseer(game, days=216)
        ov.load(resp)
        ov.count = 0
        game.calls.clear()
        return ov, game

    def places(self, game):
        return [a for t, a in game.calls if t == "place_furniture"]

    def my13(self, day=0):
        return self.ov(look(day, (E1_3, A1_3, A2_3, R1_3), ZONES_3, BEDS_3, PLOTS_3, 144), "hard_my1_3_0b49063_day5")

    def test_my1_3_the_rock_corner_of_a1_is_no_far_box(self):
        ov, game = self.my13()
        self.assertTrue(ov.shaft_people())
        self.assertEqual(ov.site_floor(A1_3), set())   # x67-86 y66-85: no reading ever saw floor there
        self.assertIsNone(ov.far_box([], min_tiles=harness.SHAFT_PEOPLE_MIN_TILES, rooms=True))
        self.assertIsNone(ov.meeting_far_box())

    def test_my1_3_seats_go_to_the_standing_hall_not_the_rock(self):
        ov, game = self.my13()
        ov.furnish()
        tables = [a for a in self.places(game) if a["kind"] in ("table", "chair")]
        self.assertTrue(tables)   # the old pass: f_table/f_chair/seat_t on A1 20x20, refused every pass
        self.assertNotIn("A1", {a["site"] for a in tables})
        self.assertIsNone(ov.shaft_refusal("place_furniture", {"kind": "table", "site": "A2", "count": 2}))
        self.assertIsNone(ov.shaft_refusal("place_furniture", {"kind": "table", "site": "A1", "count": 2}))

    def test_the_map_query_is_the_real_shape_and_cached(self):
        ov, game = self.my13()
        a2 = ov.site_floor(A2_3)
        self.assertEqual(len(a2), 48)   # 17x3: 51 tiles less the stair X and the walls at x95 (open_tiles 49 = + X)
        ov.closed_a()   # cx closed fallback: the open-ground reading of each A site (one query each, cached) first
        n = game.map_queries
        ov.site_floor(A2_3)
        ov.far_box([], rooms=True)
        self.assertEqual(game.map_queries, n + 1)   # A1 once more, A2 from the cache

    def test_a_box_that_answered_no_floor_rests_until_its_site_changes(self):
        ov, game = self.my13()
        game.answers[("A1", 20, 20)] = {"ok": False, "error_code": "no_space", "error": ROCK}
        args = {"kind": "table", "site": "A1", "count": 3, "w": 20, "h": 20}
        r = ov.act("f_table", "place_furniture", dict(args), retry=0, limit=99)
        self.assertFalse(r["ok"])
        r2 = ov.act("seat_t_A1:20x20", "place_furniture", dict(args), retry=0, limit=99)
        self.assertTrue(r2.get("local"))
        self.assertEqual(r2["error_code"], harness.OVERFLOW_ERROR)   # the callers' full-box path still reads it
        self.assertEqual(len(self.places(game)), 1)   # one game call, not one a pass
        # a bed in another box of the site is its own box
        ov.act("beds_A1", "place_furniture", {"kind": "bed", "site": "A1", "count": 2}, retry=0, limit=99)
        self.assertEqual(len(self.places(game)), 2)
        # the site's floor changed (a dig opened tiles): knock again
        a1 = dict(A1_3, open_tiles=166)
        ov.load(look(1, (E1_3, a1, A2_3, R1_3), ZONES_3, BEDS_3, PLOTS_3, 144))
        ov.act("f_table", "place_furniture", dict(args), retry=0, limit=99)
        self.assertEqual(len(self.places(game)), 3)

    def test_the_ban_ages_out(self):
        ov, game = self.my13()
        ov.nofloor[("A1", 20, 20)] = (0, ov.site_sig("A1"))
        self.assertTrue(ov.floor_refused("A1", 20, 20))
        ov.load(look(harness.NOFLOOR_DAYS, (E1_3, A1_3, A2_3, R1_3), ZONES_3, BEDS_3, PLOTS_3, 144))
        self.assertFalse(ov.floor_refused("A1", 20, 20))

    def test_a_failed_query_is_unconfirmed(self):
        ov, game = self.my13()
        game.grid = None   # the base fake answers no map
        self.assertIsNone(ov.site_floor(A1_3))
        self.assertIsNone(ov.far_box([], rooms=True))

    def my14(self, day=20):
        return self.ov(look(day, (E1_4, A2_4, A4_4, R2_4, R3_4), ZONES_4, BEDS_4, PLOTS_4, 169),
                       "hard_my1_4_d57f599_day17")

    def test_my1_4_a4_floor_is_the_plots(self):
        ov, game = self.my14()
        cut = {"x": 94, "y": 90, "w": 18, "h": 6}   # the far cut z_meeting_far took (s93005 day 14)
        self.assertEqual(ov.floor_in(ov.site_floor(A4_4), cut), 0)   # free floor: every dug tile there is a plot
        self.assertEqual(ov.floor_in(ov.site_floor(A4_4, walk=True), cut), 18)   # people still gather there
        self.assertIsNone(ov.far_site(None, [], role="dine"))

    def test_my1_4_no_real_far_box_keeps_the_handover_dining_hall_and_never_waits(self):
        for day in (0, 10, 20):
            ov, game = self.my14(day)
            ov.furnish()
            tables = [a for a in self.places(game) if a["kind"] == "table"]
            self.assertTrue(tables, day)   # the old pass: shaft_dine_wait days 0/10/20, tables only on day 30
            self.assertEqual({a["site"] for a in tables}, {"A2"}, day)
            self.assertIsNone(ov.shaft_refusal("make_zone", {"kind": "dining_hall", "site": "A2"}))

    def test_a_private_bedroom_needs_floor_in_its_corner(self):
        # 97d3466's house_everyone/stress_site: A4's 3x3 corner (x94-96 y90-92) is R3's farm plot — no bed fits
        resp = look(20, (E1_4, A2_4, A4_4, R2_4, R3_4), ZONES_4[:2], BEDS_4, PLOTS_4, 169)
        ov, game = self.ov(resp, "hard_my1_4_d57f599_day17")
        self.assertFalse(ov.room_near_shaft(A4_4))
        self.assertFalse(ov.corner_floor(A4_4))
        self.assertNotEqual((ov.stress_site() or {}).get("id"), "A4")
        plots = [p for p in PLOTS_4 if (p["x"], p["y"]) != (94, 90)]
        ov, game = self.ov(look(20, (E1_4, A2_4, A4_4, R2_4), ZONES_4[:2], BEDS_4, plots, 169),
                           "hard_my1_4_d57f599_day17")
        # cx room claim: the plot gone, A4's corner is the far meeting / dining cut (people_boxes) — the private
        # room yields to it (the far meeting area is the shaft-child fix), so no bedroom goes there
        self.assertNotEqual((ov.stress_site() or {}).get("id"), "A4")
        self.assertTrue(ov.under_people(dict(A4_4, w=harness.STRESS_ROOM_SIZE, h=harness.STRESS_ROOM_SIZE)))

    def test_a_real_far_box_takes_the_dining_when_one_exists(self):
        # the same fort once R3's plot is gone (the plot rooms' floor free again): A4's corner holds free floor
        plots = [p for p in PLOTS_4 if (p["x"], p["y"]) != (94, 90)]
        r3 = dict(R3_4, free=True, used_by=None)
        resp = look(20, (E1_4, A2_4, A4_4, R2_4, r3), ZONES_4[:2], BEDS_4, plots, 169)
        ov, game = self.ov(resp, "hard_my1_4_d57f599_day17")
        ov.furnish()
        tables = [a for a in self.places(game) if a["kind"] == "table"]
        self.assertTrue(tables)
        self.assertEqual(tables[0]["site"], "A4")
        box = {"x": 94, "y": 90, "z": 168, "w": tables[0]["w"], "h": tables[0]["h"]}
        self.assertGreaterEqual(ov.shaft_gap(box), harness.MEETING_SHAFT_TILES)
        self.assertGreaterEqual(ov.floor_in(ov.site_floor(A4_4), box), harness.FAR_FLOOR_MIN)


if __name__ == "__main__":
    unittest.main()
