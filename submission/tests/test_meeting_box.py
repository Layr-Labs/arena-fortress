"""The meeting area's fallback box and the stress room's dig pick. No game or network is used.

The fort shape is hint hard MY1-3 on c44c96b, day 0: every dug room held a role, A2 (17x3, z142) lay under
DiningHall 38 (5x3), Dormitory 39 (11x3, 22 beds) and DiningHall 53 (17x3), A1 was 61x56 (past make_zone's gate).
The run kept meeting_areas 0 to day 216 and its stressed expedition leader never left the band."""
import copy
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__
sys.path.insert(0, str(Path(__file__).resolve().parent))
from real_maps import MapQueries  # noqa: E402


class FakeGame(MapQueries):
    grid = "hard_my1_3_0b49063_day5"   # the same snapshot's real map (A1's 20x20 corner is rock)

    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, copy.deepcopy(args)))
        return {"ok": True, "result": {"zone_id": 90 + len(self.calls), "at": [0, 0, 0]}}


def site(id, x, y, z, w, h, open_tiles, **kw):
    return {"id": id, "kind": id[0], "x": x, "y": y, "z": z, "w": w, "h": h, "open_tiles": open_tiles, **kw}


def zone(id, kind, x, y, z, w, h, **kw):
    return {"id": id, "type": kind, "x": x, "y": y, "z": z, "w": w, "h": h, **kw}


BEDS = [{"kind": "bed", "x": x, "y": y, "z": 142, "built": True} for x in range(96, 107) for y in (101, 103)]
TABLES = [{"kind": "table", "x": x, "y": 101, "z": 142, "built": True} for x in (90, 92, 94)]
ZONES = [zone(38, "DiningHall", 90, 101, 142, 5, 3), zone(39, "Dormitory", 96, 101, 142, 11, 3),
         zone(53, "DiningHall", 90, 101, 142, 17, 3)]
SITES = [site("A1", 67, 66, 143, 61, 56, 114), site("A2", 90, 101, 142, 17, 3, 49),
         site("R1", 92, 101, 143, 3, 3, 9, designated=True, dug=True, free=True),
         site("R2", 80, 90, 143, 9, 7, 63)]


def facts(sites=SITES, zones=ZONES, furniture=BEDS + TABLES, dwarves=(), day=0):
    return {"tick": 967200 + day * harness.DAY, "day": day, "observation": {
        "administrators": {"citizens": 9}, "map": {"sites": copy.deepcopy(sites)},
        "zones": copy.deepcopy(list(zones)), "furniture": copy.deepcopy(list(furniture)),
        "dwarves": copy.deepcopy(list(dwarves)), "stocks": {"furniture_free": {}}}}


class MeetingBox(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.game = FakeGame()
        self.ov = harness.Overseer(self.game)
        self.ov.count = 0

    def load(self, resp, roles=True):
        self.ov.load(resp)
        if roles:
            for s in self.ov.kind("R"):
                self.ov.roles[s["id"]] = "dorm"   # the real run: digging() had given every room a role

    def zones_made(self):
        return [a for t, a in self.game.calls if t == "make_zone"]

    def test_my1_3_shape_gets_a_meeting_area_off_the_beds(self):
        self.load(facts())
        self.assertIsNone(self.ov.stress_site())
        self.ov.meeting_area()
        made = self.zones_made()
        self.assertEqual(len(made), 1, self.game.calls)
        a = made[0]
        self.assertEqual((a["kind"], a["site"]), ("meeting_area", "A2"))
        box = {"x": 90, "y": 101, "z": 142, "w": a.get("w", 17), "h": a.get("h", 3)}
        self.assertFalse(any(harness.Overseer.rects_overlap(box, dict(b, w=1, h=1)) for b in BEDS))
        self.assertFalse(harness.Overseer.rects_overlap(box, ZONES[1]))   # not over the dormitory
        self.assertGreaterEqual(box["w"] * box["h"], harness.MEETING_MIN_TILES)

    def test_existing_meeting_zone_makes_nothing(self):
        self.load(facts(zones=ZONES + [zone(60, "MeetingHall", 90, 101, 142, 3, 3)]))
        self.ov.meeting_area()
        self.assertEqual(self.zones_made(), [])

    def test_free_room_still_comes_first(self):
        self.load(facts(), roles=False)   # R1 dug, no role, no zone: stress_site's pick, as before
        self.ov.meeting_area()
        self.assertEqual(self.zones_made(), [{"kind": "meeting_area", "site": "R1"}])

    def test_no_box_clear_of_beds_makes_nothing(self):
        beds = [{"kind": "bed", "x": x, "y": y, "z": 142, "built": True} for x in range(90, 107) for y in (101, 103)]
        self.load(facts(sites=[s for s in SITES if s["id"] != "A1"], furniture=beds))
        self.ov.meeting_area()
        self.assertEqual(self.zones_made(), [])

    def test_a_wide_sites_rock_corner_gets_no_meeting_area(self):
        # cx confirmed floor: A1 (61x56, open_tiles 114) has its floor at x90-107; the clamped 20x20 corner box
        # (x67-86 y66-85) is rock — the old pass zoned the fort's meeting area there (0b49063 z_meeting_far A1 20x20)
        self.load(facts(sites=[s for s in SITES if s["id"] != "A2"]))
        self.ov.meeting_area()
        self.assertEqual(self.zones_made(), [])
        self.assertEqual(self.ov.site_floor(self.ov.kind("A")[0], walk=True), set())

    def test_wide_site_is_clamped_to_the_zone_gate(self):
        # a wide site whose corner holds floor: the record's level read with its floor moved under the corner
        a1 = site("A1", 90, 101, 143, 61, 56, 114)
        self.load(facts(sites=[s for s in SITES if s["id"] not in ("A1", "A2")] + [a1]))
        self.ov.meeting_area()
        made = self.zones_made()
        self.assertEqual(len(made), 1, self.game.calls)
        self.assertEqual(made[0]["site"], "A1")
        self.assertLessEqual(made[0]["w"], harness.ZONE_MAX)
        self.assertLessEqual(made[0]["h"], harness.ZONE_MAX)

    def test_one_meeting_area_across_passes(self):
        self.load(facts())
        self.ov.meeting_area()
        self.ov.now += 10 * harness.DAY
        self.load(facts(zones=ZONES + [zone(91, "MeetingHall", 90, 101, 142, 6, 3)], day=10))
        self.ov.meeting_area()
        self.assertEqual(len(self.zones_made()), 1)

    def test_meeting_site_is_not_the_stress_room_too(self):
        leader = {"id": 84, "stress": 1, "adult": True, "positions": ["EXPEDITION_LEADER"]}
        sites = SITES + [site("R3", 70, 70, 143, 3, 3, 9, designated=True, dug=True, free=True)]
        self.ov.load(facts(sites=sites, dwarves=[leader]))
        self.ov.roles.update(R1="dorm")   # R3 is free: the meeting area takes it first
        self.ov.meeting_area()
        self.ov.stress_housing()
        made = self.zones_made()
        self.assertEqual(made[0], {"kind": "meeting_area", "site": "R3"})
        self.assertFalse(any(a.get("kind") == "bedroom" and a.get("site") == "R3" for a in made), made)

    def test_breach_holds_it(self):
        self.load(facts())
        self.ov.breach = {"z": 142}
        self.ov.meeting_area()
        self.assertEqual(self.zones_made(), [])


class StressDigPick(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.game = FakeGame()
        self.ov = harness.Overseer(self.game)
        self.ov.count = 0

    def test_room_another_planner_took_this_pass_is_skipped(self):
        undug = [site("R1", 92, 101, 143, 3, 3, 9), site("R2", 80, 90, 143, 3, 3, 9)]
        leader = {"id": 84, "stress": 1, "adult": True, "positions": ["EXPEDITION_LEADER"]}
        self.ov.load(facts(sites=undug, zones=ZONES, dwarves=[leader]))
        self.ov.roles["R1"] = "dorm"   # digging() ordered R1 from this same observation
        self.ov.stress_housing()
        digs = [a for t, a in self.game.calls if t == "dig_room"]
        self.assertEqual(digs, [{"site": "R2"}])
        self.assertEqual(self.ov.roles.get("R2"), "stress")


if __name__ == "__main__":
    unittest.main()
