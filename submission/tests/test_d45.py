"""d45: the re-check's fixes. Tables and chairs in pairs for today's population in a new dining room, no dormitory
zone over a dining room still waiting for its zone, the meeting area free again once that room's dining zone stands,
only offices actually made hold floor, and a room only a dormitory uses still takes beds."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from test_d42 import fort, row, beds, WIDE, SMALL, ROOM, UNDUG  # noqa: E402
from test_d44 import TileStub  # noqa: E402
from overseer.harness import DAY  # noqa: E402


class D45(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_a_new_dining_room_gets_tables_and_chairs_in_pairs(self):
        old = dict(ROOM, id="R1", x=10, y=10, z=147, free=False, used_by=["DiningHall 49"])
        dining = dict(old, id=49, type="DiningHall")
        furniture = ([row(i, "table", 10 + i, 10, 147, [49]) for i in range(3)]
                     + [row(10 + i, "chair", 10 + i, 11, 147, [49]) for i in range(3)])
        ov, _ = fort([WIDE, old, ROOM], cit=12, free={"table": 12, "chair": 12}, furniture=furniture, zones=[dining])
        ov.days_left = 40
        ov.roles.update(R1="dine", R5="dine_more")
        ov.dine_full["R1"] = ov.fill_mark(old)
        self.assertEqual(ov.dine_site()["id"], "R5")
        floor = [(x, y, ROOM["z"]) for y in range(ROOM["y"], ROOM["y"] + 3) for x in range(ROOM["x"], ROOM["x"] + 3)]
        ov.game = g = TileStub(ov.sites, floor, ov.free)
        ov.furnish()
        self.assertEqual({k: sum(f["kind"] == k for f in g.rows) for k in ("table", "chair")}, {"table": 4, "chair": 4})

    def test_no_dormitory_zone_over_a_dining_room_waiting_for_its_zone(self):
        level = dict(SMALL, w=12, h=6, open_tiles=9)
        undug = dict(UNDUG, x=83, y=92, z=149)
        ov, _ = fort([level, undug], free={"bed": 5, "table": 5, "chair": 5})
        ov.dine_full[level["id"]] = ov.fill_mark(level)
        ov.game = g = TileStub(ov.sites, [], ov.free)
        ov.house_rooms()
        self.assertEqual(ov.roles[undug["id"]], "dine_more")
        ov.furnish()
        self.assertNotIn({"kind": "dormitory", "site": level["id"]}, g.tools("make_zone"))

    def test_the_meeting_area_may_use_the_level_once_the_room_has_its_dining_zone(self):
        level = dict(SMALL, x=70, y=95, z=148, w=12, h=6, open_tiles=50)
        room = dict(ROOM, id="R6", free=False, used_by=["DiningHall 49"])
        zone = dict(room, id=49, type="DiningHall")
        ov, _ = fort([WIDE, level, room], day=60, zones=[zone])
        ov.roles["R6"] = "dine_more"
        self.assertEqual(ov.meeting_site()["id"], level["id"])
        ov2, _ = fort([WIDE, level, dict(ROOM, id="R6")], day=60)
        ov2.roles["R6"] = "dine_more"                          # no dining zone yet: the level waits
        self.assertIsNone(ov2.meeting_site())

    def test_a_failed_office_zone_holds_no_floor(self):
        undug = dict(UNDUG, x=83, y=92, z=SMALL["z"])
        ov, g = fort([WIDE, SMALL, undug], free={"bed": 5})
        ov.adm["MANAGER_id"] = 0
        original = g.act

        def refuse_zone(tool, args):
            if tool == "make_zone":
                g.calls.append((tool, dict(args)))
                return {"ok": False, "error_code": "internal_error"}
            return original(tool, args)
        g.act = refuse_zone
        ov.office_open()
        self.assertEqual(ov.office_tried, {"A3"})
        self.assertEqual([s["id"] for s in ov.bed_sites(WIDE)], ["A3"])

    def test_a_room_only_a_dormitory_uses_still_takes_beds(self):
        dorm_room = dict(ROOM, free=False, used_by=["Dormitory 71"])
        ov, g = fort([WIDE, dorm_room], free={"bed": 4})
        ov.furnish()
        self.assertEqual(beds(g), [("R5", 4)])


if __name__ == "__main__":
    unittest.main()
