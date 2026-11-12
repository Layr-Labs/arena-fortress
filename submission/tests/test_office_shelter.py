"""cx lt082beds (hint hard LT08-2 on 7be81c2: 128.75, beds 41/47, drink 464 < 488 at A): no work order validated
until d31 — the manager's office stood on the roofed A1 corner (83,67,104), outside the Shelter (R1, closed) and
1-2 tiles from the open floor the alligators walked; DF's validation rounds at d5.6 / 13.96 / 22.36 fell on an office
yield or an alert ("Manage work orders: Need office."). The office goes into a closed Shelter room; office_open reads
the level (the Shelter's enclosed rule), so the roofed corner is open ground; rezone never takes the office room.
Fixture: a z104 level like LT08-2's — the R1 room box (88-96, 104-110) walled in and roofed, the rest of the level
open floor with a roofed strip on row 67 (the A1 corner). No game or network."""
from pathlib import Path
import copy
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_closed_sites import A1, Quiet, FakeGame, harness  # noqa: E402

R1 = {"id": "R1", "kind": "R", "x": 88, "y": 104, "z": 104, "w": 3, "h": 3, "designated": True, "dug": True}
R2 = {"id": "R2", "kind": "R", "x": 94, "y": 93, "z": 104, "w": 3, "h": 3, "designated": True, "dug": True}
CORNER = {"id": 7, "type": "Office", "x": 83, "y": 67, "z": 104, "w": 1, "h": 1, "owner": 92,
          "furniture": {"chair": 1}}


def cell(x, y, z):
    if z != 104:
        return ".", "o"
    if 88 <= x <= 96 and 104 <= y <= 110:
        return ".", "u"            # the Shelter room, dug and roofed
    if 87 <= x <= 97 and 103 <= y <= 111:
        return "#", "u"            # its walls
    if y == 67 and 83 <= x <= 86:
        return ".", "i"            # the roofed A1 corner strip, open floor beside it
    if 94 <= x <= 96 and 93 <= y <= 95:
        return ".", "u"            # R2's 3x3, roofed, its level open
    return ".", "o"


class LevelGame(FakeGame):
    def query(self, name, **kw):
        if name != "map":
            return super().query(name, **kw)
        self.maps += 1
        x, y, z, rad = kw["x"], kw["y"], kw["z"], kw["radius"]
        rows = [[cell(xx, yy, z) for xx in range(x - rad, x + rad + 1)] for yy in range(y - rad, y + rad + 1)]
        return {"result": {"ok": True, "x1": x - rad, "y1": y - rad,
                           "levels": [{"z": z, "shape": ["".join(c[0] for c in r) for r in rows],
                                       "light": ["".join(c[1] for c in r) for r in rows]}]}}

    def act(self, tool, args):
        r = super().act(tool, args)
        if tool == "place_furniture" and args.get("kind") == "chair" and args.get("site") == "R1":
            r = {"ok": True, "result": {"placed": "chair", "n": 1, "at": [88, 104, 104]}}
        return r


class OfficeShelter(Quiet):
    def agent(self, sites, others=(), goal="migrant surge", day=1):
        game = LevelGame(sites, others)
        agent = harness.Overseer(game, goal=goal, days=60)
        agent.count = 0
        agent.load(game.observe(day=day))
        return agent, game

    def sheltered(self, sites=(A1, R1), zones=(CORNER,), others=()):
        agent, game = self.agent(list(sites), others=others)
        agent.zones = [dict(z) for z in zones]
        agent.adm["manager_office"] = {"zone_id": 7, "chair": True} if zones else "none"
        agent.roles["R1"] = "dorm"
        agent.shelter_added.add("R1")
        agent.shelter_boxes["R1"] = (88, 104, 96, 110, 104)
        return agent, game

    def test_the_roofed_corner_office_reads_open_by_its_level(self):
        agent, _ = self.sheltered()
        self.assertEqual(agent.box_open((83, 67, 104, 1, 1)), 0)   # the tile itself is roofed
        self.assertTrue(agent.office_open(CORNER))                    # its level runs onto open floor
        self.assertEqual(agent.office_open(dict(CORNER, x=88, y=104)), 0)   # inside the walled room

    def test_the_office_moves_into_the_closed_shelter_room_and_the_corner_is_released(self):
        agent, game = self.sheltered()
        agent.office()
        self.assertEqual(game.calls[:3], [
            ("place_furniture", {"kind": "chair", "site": "R1", "w": 9, "h": 7}),
            ("make_zone", {"kind": "office", "site": "R1", "w": 1, "h": 1}),
            ("assign_zone", {"zone_id": 50, "dwarf_id": 92})])
        self.assertIn(("assign_zone", {"zone_id": 7, "dwarf_id": 93}), game.calls)   # the corner handed away

    def test_no_office_yet_takes_the_shelter_room_not_the_open_corner(self):
        agent, game = self.sheltered(zones=())
        agent.office()
        self.assertEqual(game.calls[1], ("make_zone", {"kind": "office", "site": "R1", "w": 1, "h": 1}))

    def test_an_office_inside_the_shelter_stays(self):
        agent, game = self.sheltered(zones=(dict(CORNER, x=88, y=104),))
        agent.office()
        self.assertEqual(game.calls, [])
        self.assertFalse(agent.office_wants_room())

    def test_a_yielded_office_goes_to_the_shelter_room(self):
        agent, game = self.sheltered(zones=(dict(CORNER, owner=93),))
        agent.office_yield = {"zone": 7, "holder": 93, "since": agent.now, "clear": None}
        agent.office()
        self.assertEqual(game.calls[2], ("assign_zone", {"zone_id": 50, "dwarf_id": 92}))
        self.assertIsNone(agent.office_yield)

    def test_not_with_a_big_beast_near_the_room(self):
        gator = {"id": 700, "race": "ALLIGATOR", "x": 92, "y": 100, "z": 104}
        agent, game = self.sheltered(others=[gator])
        agent.mark_of = lambda u: True
        agent.office()
        self.assertNotIn(("make_zone", {"kind": "office", "site": "R1", "w": 1, "h": 1}), game.calls)

    def test_not_over_a_bed_on_the_corner(self):
        agent, game = self.sheltered()
        agent.o["furniture"] = [{"built": True, "kind": "bed", "x": 88, "y": 104, "z": 104, "zone_ids": []}]
        agent.office()
        self.assertFalse([c for c in game.calls if c[1].get("site") == "R1"])

    def test_a_level_open_shelter_fallback_is_not_taken(self):
        agent, game = self.sheltered()
        agent.shelter_level_in.add("R1")
        agent.office()
        self.assertFalse([c for c in game.calls if c[1].get("site") == "R1"])

    def test_one_try_a_room(self):
        agent, game = self.sheltered()
        agent.office()
        n = len(game.calls)
        agent.zones = [dict(CORNER)]   # the assignment did not land
        agent.office()
        self.assertFalse([c for c in game.calls[n:] if c[0] == "place_furniture" and c[1].get("site") == "R1"])

    def test_small_labs_keep_waiting(self):
        agent, game = self.sheltered()
        agent.cit = harness.OFFICE_FULL_CIT - 1
        self.assertFalse(agent.office_shelter())
        self.assertEqual(game.calls, [])


class RezoneOfficeRoom(Quiet):
    def test_rezone_never_zones_the_office_room(self):
        game = LevelGame([A1, dict(R1, free=False, used_by=["Dormitory 22"]), R2])   # as d12: R1 the zoned dorm
        agent = harness.Overseer(game, goal="migrant surge", days=60)
        agent.count = 0
        agent.load(game.observe(day=12))
        agent.roles.update(R1="dorm", R2="office")
        agent.o["furniture"] = [{"built": True, "kind": "bed", "x": 92, "y": 107, "z": 104, "zone_ids": []}]
        agent.rezone()
        self.assertNotIn(("make_zone", {"kind": "dormitory", "site": "R2"}), game.calls)
        agent.roles["R2"] = "dorm"
        agent.rezone()
        self.assertIn(("make_zone", {"kind": "dormitory", "site": "R2"}), game.calls)


if __name__ == "__main__":
    unittest.main()
