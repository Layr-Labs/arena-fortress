"""cx surge floor, measured in tiles (LT08 shape only), from the hint std LT08 records at e538c50 (2026-11-10):
- LT08-0: one dug level (A5 13x18, 141 open) held 7 farm plots and 74 furniture; every bed answered no_space from
  day 27 (37 placed for 47 citizens, 50 bed items) and no R site was listed from day 8 to day 38, while the room
  count (2 dorm rooms) looked met; the dorm digs from an R site's corner ran back over the dug level (R1 9x7
  designated 1 tile, R4 2);
- LT08-1: the level's A box grew to 42x34 then 57x56 (past place_furniture's 40) with ~78 free tiles, so the only
  surge bed site left was the 3x3 R1 (no_space 8 times; 21 placed for 44 citizens, 48 bed items).
Each measure must leave the windowless and non-migrant shapes exactly as before."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

GOAL_LT08 = "Migrants are arriving. From day 39 you can't act for 21 days."
GOAL_OPEN = "Run the fortress for 60 days."


class FakeGame:
    def __init__(self):
        self.calls = []
        self.room = {}      # box key -> beds it still takes (default 99)
        self.avail = 50     # the API's "available" (free bed items)

    @staticmethod
    def box(args):
        return args.get("site") or "%s,%s,%s" % (args.get("x"), args.get("y"), args.get("z"))

    def act(self, tool, args):
        args = dict(args)
        self.calls.append((tool, args))
        if tool == "place_furniture":
            k = min(args.get("count", 1), self.room.get(self.box(args), 99))
            if k <= 0:
                return {"ok": False, "error_code": "no_space", "error": "no free floor tile"}
            self.room[self.box(args)] = self.room.get(self.box(args), 99) - k
            return {"ok": True, "result": {"n": k, "available": self.avail, "at": [[i, 1, 9] for i in range(k)]}}
        return {"ok": True, "result": {"order_id": 100 + len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {}}


def A(id="A5", x=92, y=91, z=153, w=13, h=18, open_tiles=139):
    return {"id": id, "kind": "A", "x": x, "y": y, "z": z, "w": w, "h": h, "open_tiles": open_tiles}


def R(id, x, y, z=153, stair=None, dug=False, designated=False, **kw):
    s = {"id": id, "kind": "R", "x": x, "y": y, "z": z, "w": 3, "h": 3, "soil": True, "dug": dug,
         "designated": designated, "free": True, **kw}
    if stair:
        s["stair"] = {"x": stair[0], "y": stair[1]}
    return s


def furniture(n, z=153):
    return [{"kind": "bed" if i % 2 else "table", "x": i, "y": 1, "z": z} for i in range(n)]


def plots(n, z=153):
    return [{"id": i, "x": i * 3, "y": 0, "z": z, "w": 3, "h": 3, "built": True} for i in range(n)]


def obs(cit=47, hands_off=23, sites=(), furn=(), farms=(), pending=0, day=16, beds_free=10):
    return {"tick": 0, "day": day, "hands_off_in_days": hands_off, "observation": {
        "administrators": {"citizens": cit, "manager_active_for_orders": True, "MANAGER_id": 1},
        "stocks": {"plants_brewable": 4, "food_edible": 80, "drink": 550, "beds": 60, "barrels_empty": 12,
                   "logs_usable": 170, "furniture_free": {"bed": beds_free}},
        "map": {"sites": list(sites), "surface_z": 154}, "zones": [], "furniture": list(furn),
        "workshops": [], "orders": [], "farm_plots": list(farms), "dig_designations_pending": pending,
        "plugins": {"autochop": "on", "seedwatch": "on", "autofarm": "on"}, "date": {"abs_tick": 0}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, surge=True, hands_off=23, **kw):
        game = FakeGame()
        o = harness.Overseer(game, goal=GOAL_LT08 if surge else GOAL_OPEN, days=60)
        o.load(obs(hands_off=hands_off if surge else None, **kw))
        o.water_ok = lambda s: True
        o.water_wetness = lambda s: 0
        o.water_rank = lambda s: 0
        o.count = 0
        return o, game

    @staticmethod
    def calls(game, tool):
        return [a for t, a in game.calls if t == tool]


class RoomBox(Base):
    def test_the_dorm_box_is_the_site_call_even_with_a_stair(self):
        """cx (hint hard LT08-0 on f2bd283): the server requires `site` and resolves x,y,z from it, so the far-side
        box ({"x", "y", "z", "w", "h"}) answered bad_arguments on every call; the site call keeps w and h."""
        o, _ = self.ov()
        w, h = harness.SURGE_FLOOR_ROOM
        for r in (R("R4", 90, 95, stair=(93, 96)), R("R", 94, 95, stair=(93, 96)), R("R", 92, 97, stair=(93, 96))):
            box = o.surge_room_box(r)
            self.assertEqual(box, {"site": r["id"], "w": w, "h": h})
            self.assertIn("site", box)

    def test_no_stair_keeps_the_site_call(self):
        o, _ = self.ov()
        self.assertEqual(o.surge_room_box(R("R1", 90, 95)), {"site": "R1", "w": 9, "h": 7})
        self.assertEqual(o.surge_room_box(R("R1", 1, 1, stair=(6, 2))), {"site": "R1", "w": 9, "h": 7})  # off the edge


class FloorShort(Base):
    def test_lt08_0_day16_is_short(self):
        """139 open - 43 furniture - 7 plots*9 = 33 free for 49 - 19 = 30 beds still to place (+ the margin)."""
        o, _ = self.ov(sites=[A()], furn=furniture(43), farms=plots(7))
        o.placed = {"bed": 19}
        self.assertEqual(o.surge_floor_free(), 33)
        self.assertTrue(o.surge_floor_short())

    def test_lt08_1_day18_has_floor(self):
        o, _ = self.ov(cit=44, sites=[A("A5", w=46, h=35, open_tiles=170)], furn=furniture(38), farms=plots(9))
        o.placed = {"bed": 21}
        self.assertEqual(o.surge_floor_free(), 51)
        self.assertFalse(o.surge_floor_short())

    def test_pending_tiles_count_as_floor_to_come(self):
        o, _ = self.ov(sites=[A()], furn=furniture(43), farms=plots(7), pending=40)
        o.placed = {"bed": 19}
        self.assertFalse(o.surge_floor_short(40))

    def test_other_shapes_and_the_window_never_measure(self):
        o, _ = self.ov(surge=False, sites=[A()], furn=furniture(43), farms=plots(7))
        self.assertFalse(o.surge_floor_short())
        o2, _ = self.ov(hands_off=0, sites=[A()], furn=furniture(43), farms=plots(7))
        self.assertFalse(o2.surge_floor_short())
        o3, _ = self.ov(sites=[])                      # nothing dug yet: nothing to measure
        self.assertFalse(o3.surge_floor_short())


class FloorDig(Base):
    def short_fort(self, extra=(), **kw):
        sites = [A(), R("R1", 94, 102, dug=True, designated=True), R("R2", 96, 91, dug=True, designated=True),
                 {"id": "E2", "kind": "E", "x": 95, "y": 92, "z": 154, "w": 1, "h": 1},
                 {"id": "S3", "kind": "S", "x": 93, "y": 98, "z": 154, "w": 1, "h": 1}] + list(extra)
        o, game = self.ov(sites=sites, furn=furniture(43), farms=plots(7), **kw)
        o.placed = {"bed": 19}
        o.roles = {"R1": "dorm", "R2": "dorm", "R0": "dorm"}   # the room count is met: surge_dorm_rooms(47) = 3
        return o, game

    def test_a_spare_room_gets_the_floor_dig_by_its_site(self):
        o, game = self.short_fort(extra=[R("R4", 90, 95, stair=(93, 96))])
        o.surge_capacity()
        digs = self.calls(game, "dig_room")
        self.assertEqual(digs, [{"site": "R4", "w": 9, "h": 7}])
        self.assertEqual(o.roles.get("R4"), "dorm")

    def test_room_count_met_but_floor_gone_still_digs(self):
        """LT08-0: have 2 dorm rooms >= surge_dorm_rooms(18) — the old check returned before any floor test."""
        o, game = self.short_fort(extra=[R("R4", 90, 95, stair=(93, 96))], cit=18)
        o.placed = {"bed": 0}
        self.assertGreaterEqual(2, harness.surge_dorm_rooms(18))
        o.surge_capacity()
        self.assertEqual(len(self.calls(game, "dig_room")), 1)

    def test_no_spare_room_digs_a_fresh_s_shaft_one_level_under_the_dug_one(self):
        """cx (hint hard LT08-0 on f2bd283: 6 E-site / raw-coordinate stair calls, all bad_arguments): an S site
        (the API's only dig_stairs kind) on a column clear of the dug boxes, from its own z to one under the level."""
        rock = {"id": "S4", "kind": "S", "x": 120, "y": 95, "z": 154, "w": 1, "h": 1}
        o, game = self.short_fort(extra=[rock])
        o.day = 16
        o.surge_capacity()
        self.assertEqual(self.calls(game, "dig_stairs"), [{"site": "S4", "z_bottom": 152}])
        o.now += harness.DAY
        o.day += 1
        o.surge_capacity()                               # its R sites have not listed yet: wait
        self.assertEqual(len(self.calls(game, "dig_stairs")), 1)
        o.now += harness.SURGE_FLOOR_STAIR_DAYS * harness.DAY
        o.day += harness.SURGE_FLOOR_STAIR_DAYS
        o.surge_capacity()                               # still short, still no R site: another try
        self.assertEqual(self.calls(game, "dig_stairs")[-1], {"site": "S4", "z_bottom": 152})
        for a in self.calls(game, "dig_stairs") + self.calls(game, "dig_room"):
            self.assertIn("site", a)

    def test_a_shaft_never_runs_through_a_dug_floor(self):
        """S3 (93,98) stands over A5's dug box on z153: an up/down stair there would break at the floor."""
        o, game = self.short_fort()
        o.surge_capacity()
        self.assertEqual(self.calls(game, "dig_stairs"), [])

    def test_this_passes_dorm_dig_counts_as_floor_to_come(self):
        o, game = self.short_fort()
        o.placed = {"bed": 30}                    # 19 beds still to place: short by 2 against 33 free
        self.assertTrue(o.surge_floor_short())
        o.surge_floor(added=40)
        self.assertEqual(self.calls(game, "dig_stairs"), [])

    def test_a_room_dig_in_progress_waits(self):
        o, game = self.short_fort(cit=40, pending=40)
        o.placed = {"bed": 0}
        o.surge_capacity()
        self.assertEqual(self.calls(game, "dig_stairs"), [])

    def test_enough_floor_or_open_play_digs_nothing(self):
        o, game = self.short_fort(extra=[R("R4", 90, 95, stair=(93, 96))], cit=30)
        o.o["furniture"], o.o["farm_plots"] = [], []
        o.placed = {"bed": 30}
        o.surge_capacity()
        self.assertEqual(game.calls, [])
        o2, game2 = self.ov(surge=False, sites=[A(), R("R4", 90, 95, stair=(93, 96)),
                                                {"id": "E2", "kind": "E", "x": 95, "y": 92, "z": 154}],
                            furn=furniture(43), farms=plots(7))
        o2.surge_capacity()
        o2.surge_floor()
        self.assertEqual(game2.calls, [])


class WideBox(Base):
    def test_a_box_past_place_max_takes_beds_in_chunks(self):
        """LT08-1 day 35: A5 57x56 (197 open) beside a 3x3 dorm R1 that refuses."""
        big = A("A5", x=70, y=60, z=164, w=57, h=56, open_tiles=197)
        o, game = self.ov(cit=44, sites=[big, R("R1", 94, 102, z=164, dug=True, designated=True)], beds_free=19)
        o.placed = {"bed": 21}
        o.roles = {"R1": "dorm"}
        game.room["R1"] = 0
        o.furnish()
        beds = [a for a in self.calls(game, "place_furniture") if a["kind"] == "bed"]
        self.assertEqual(beds[0].get("site"), "R1")
        # cx: the server requires `site` (raw x,y,z,w,h answers "args.site is required"); the facts layer takes the
        # site's corner and keeps a given w/h, so the corner chunk goes as the A site with the chunk's w/h
        self.assertEqual(beds[1], {"kind": "bed", "site": "A5", "w": 40, "h": 40, "count": 19})
        for a in self.calls(game, "place_furniture"):
            self.assertIn("site", a)
            self.assertNotIn("@", str(a.get("site")))
        for a in self.calls(game, "make_zone"):
            self.assertNotIn("@", str(a.get("site")))   # a chunk id never reaches the API

    def test_chunks_cover_the_box_inside_the_gate(self):
        o, _ = self.ov()
        cs = o.surge_chunks(A("A5", x=70, y=60, w=57, h=56))
        self.assertEqual([(c["x"], c["y"], c["w"], c["h"]) for c in cs],
                         [(70, 60, 40, 40), (110, 60, 17, 40), (70, 100, 40, 16), (110, 100, 17, 16)])
        self.assertEqual(sum(c["w"] * c["h"] for c in cs), 57 * 56)
        self.assertEqual(o.surge_chunks({"id": "A9", "kind": "A"}), [])

    def test_a_floor_limited_part_fill_goes_on_to_the_next_site(self):
        """LT08-0 day 27: 5 of 6 placed with items to spare, then no_space; the rest goes on in the same pass."""
        o, game = self.ov(cit=40, sites=[A("A5", z=153, open_tiles=139), A("A6", z=152, w=9, h=7, open_tiles=63)],
                          beds_free=6)
        o.placed = {"bed": 34}
        game.room["A5"] = 5
        o.furnish()
        beds = [(a.get("site"), a["count"]) for a in self.calls(game, "place_furniture") if a["kind"] == "bed"]
        self.assertEqual(beds, [("A5", 6), ("A6", 1)])

    def test_open_play_never_chunks(self):
        big = A("A5", x=70, y=60, z=164, w=57, h=56, open_tiles=197)
        o, game = self.ov(surge=False, sites=[big])
        o.furnish()
        self.assertFalse([a for a in self.calls(game, "place_furniture") if "site" not in a])


if __name__ == "__main__":
    unittest.main()
