"""cx stress corner (hint hard OP1-3 on 014f7eb): on a one-level fort whose dug rooms all lie under the shared dorm /
dining / office zones and whose undug rooms answer water_risk, the stressed citizen's private room is a bedroom zone
from the A site's corner to one standing bed (that bed and no other furniture), so DF hands them that bed. No game."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness
from test_cx_alloc import FakeGame, resp

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class CornerGame(FakeGame):
    def act(self, tool, args):
        if tool == "make_zone":
            self.calls.append((tool, args.copy()))
            return {"ok": True, "result": {"zone_id": 700 + len(self.calls), "at": [0, 0, 149, 1, 1]}}
        return super().act(tool, args)


# the measured d100 level of the record (A5 and the zones over it, the beds/tables/chairs of the dorm and dining)
A5 = {"id": "A5", "kind": "A", "x": 91, "y": 91, "z": 149, "w": 11, "h": 11, "open_tiles": 73, "subterranean": True}
ZONES = [{"id": 33, "type": "Dormitory", "x": 91, "y": 93, "z": 149, "w": 9, "h": 7},
         {"id": 38, "type": "DiningHall", "x": 91, "y": 91, "z": 149, "w": 11, "h": 11},
         {"id": 55, "type": "Dormitory", "x": 91, "y": 91, "z": 149, "w": 8, "h": 1}]
BEDS = [(91, 93), (91, 94), (92, 93), (92, 94), (93, 93), (93, 94), (94, 93), (95, 91), (95, 93), (96, 91),
        (96, 93), (97, 91), (98, 91)]
TABLES = [(95, 92), (96, 92), (97, 92), (98, 92), (99, 91), (99, 92), (101, 91)]
CHAIRS = [(97, 93), (98, 93), (99, 93), (100, 91), (100, 92), (100, 93), (101, 92), (101, 93)]


def furniture(beds=BEDS, tables=TABLES, chairs=CHAIRS, z=149):
    return ([{"kind": "bed", "x": x, "y": y, "z": z} for x, y in beds]
            + [{"kind": "table", "x": x, "y": y, "z": z} for x, y in tables]
            + [{"kind": "chair", "x": x, "y": y, "z": z} for x, y in chairs])


class Base(unittest.TestCase):
    def setUp(self):
        out = redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def ov(self, people, sites=(A5,), zones=ZONES, furn=None, beds_free=0):
        game = CornerGame()
        ov = harness.Overseer(game, days=336)
        r = resp(day=100, cit=len(people), extra={"dwarves": people, "map": {"sites": list(sites)},
                                                   "zones": [dict(z) for z in zones],
                                                   "furniture": furniture() if furn is None else furn})
        r["observation"]["stocks"]["furniture_free"] = {"bed": beds_free}
        ov.load(r)
        ov.count = 0
        ov.site_open = lambda s: 0
        ov.level_open = lambda box: 0
        return ov, game

    @staticmethod
    def made(game):
        return [a for t, a in game.calls if t == "make_zone" and a.get("kind") == "bedroom"]


class CornerRoom(Base):
    def test_measured_level_gives_the_one_bed_box(self):
        ov, game = self.ov([{"id": 90, "stress": 1}])
        ov.stress_housing()
        self.assertEqual(self.made(game), [{"kind": "bedroom", "site": "A5", "w": 1, "h": 3}])
        self.assertIn(("assign_zone", 90), [(t, a.get("dwarf_id")) for t, a in game.calls if t == "assign_zone"])
        self.assertEqual([a for t, a in game.calls if t == "place_furniture"], [])   # the bed stands already
        self.assertEqual([a for t, a in game.calls if t == "add_order" and a.get("recipe") == "make_bed"], [])

    def test_no_room_twice_and_no_bed_on_later_passes(self):
        ov, game = self.ov([{"id": 90, "stress": 1}])
        ov.stress_housing()
        ov.free["bed"] = 3
        ov.stress_housing()
        self.assertEqual(len(self.made(game)), 1)
        self.assertEqual([a for t, a in game.calls if t == "place_furniture"], [])

    def test_box_with_two_beds_is_not_taken(self):
        # the only beds lie so that every corner box reaching one also holds another (or a table)
        furn = furniture(beds=[(91, 91), (92, 91)], tables=[], chairs=[])
        ov, _ = self.ov([{"id": 90, "stress": 1}], furn=furn)
        self.assertEqual((ov.stress_corner_site() or {}).get("w"), 1)   # (91,91) alone
        furn = furniture(beds=[(92, 92)], tables=[(91, 91)], chairs=[])
        ov, game = self.ov([{"id": 90, "stress": 1}], furn=furn)
        self.assertIsNone(ov.stress_corner_site())
        ov.stress_housing()
        self.assertEqual(self.made(game), [])

    def test_meeting_area_and_bedrooms_are_kept_off(self):
        zones = ZONES + [{"id": 12, "type": "MeetingHall", "x": 91, "y": 92, "z": 149, "w": 2, "h": 2}]
        ov, game = self.ov([{"id": 90, "stress": 1}], zones=zones)
        got = ov.stress_corner_site()
        self.assertEqual((got["w"], got["h"]), (5, 1))   # along row 91 to the bed at (95,91), above the meeting area
        zones = ZONES + [{"id": 70, "type": "Bedroom", "x": 91, "y": 91, "z": 149, "w": 1, "h": 1, "owner": 5}]
        ov, game = self.ov([{"id": 90, "stress": 1}], zones=zones)
        self.assertIsNone(ov.stress_corner_site())

    def test_free_room_or_dig_still_comes_first(self):
        room = {"id": "R9", "kind": "R", "dug": True, "designated": True, "x": 120, "y": 5, "z": 149, "w": 3, "h": 3}
        ov, game = self.ov([{"id": 90, "stress": 1}], sites=(A5, room))
        ov.stress_housing()
        self.assertEqual([a["site"] for a in self.made(game)], ["R9"])
        undug = dict(room, dug=False, designated=False)
        ov, game = self.ov([{"id": 90, "stress": 1}], sites=(A5, undug))
        ov.water_ok = lambda r: True
        ov.stress_housing()
        self.assertEqual(self.made(game), [])
        self.assertEqual([a["site"] for t, a in game.calls if t == "dig_room"], ["R9"])

    def test_unstressed_citizens_take_nothing(self):
        ov, game = self.ov([{"id": 90, "stress": 3}, {"id": 91, "stress": 4}])
        ov.stress_housing()
        self.assertEqual(self.made(game), [])

    def test_switch_off_keeps_stress_no_site(self):
        old = harness.STRESS_CORNER
        harness.STRESS_CORNER = False
        try:
            ov, game = self.ov([{"id": 90, "stress": 1}])
            ov.stress_housing()
            self.assertEqual(self.made(game), [])
        finally:
            harness.STRESS_CORNER = old


class BedSiteLookup(Base):
    def test_bed_goes_to_the_site_on_the_zone_corner_now(self):
        """an A site's id changes as its level is dug (A4 -> A5): the stress bed goes to the site standing on the
        zone's corner now, the remembered id only when none does."""
        room = {"id": "R9", "kind": "R", "dug": True, "designated": True, "x": 120, "y": 5, "z": 149, "w": 3, "h": 3}
        ov, game = self.ov([{"id": 90, "stress": 1}], sites=(A5, room), beds_free=1)
        ov.stress_zone[90] = {"id": 800, "x": 91, "y": 91, "z": 149, "site": "A4"}
        ov.stress_housing()
        self.assertEqual([a["site"] for t, a in game.calls if t == "place_furniture"], ["A5"])


if __name__ == "__main__":
    unittest.main()
