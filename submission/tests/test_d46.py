"""d46: rezone() leaves a dining room waiting for its zone alone, as beds_open does (loose beds on its level)."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from test_d42 import fort, row, WIDE, SMALL, UNDUG  # noqa: E402
from test_d44 import TileStub  # noqa: E402


class D46(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_rezone_makes_no_dormitory_over_a_dining_room_waiting_for_its_zone(self):
        level = dict(SMALL, open_tiles=9)
        undug = dict(UNDUG, x=83, y=92, z=149)
        ov, _ = fort([WIDE, level, undug], free={"bed": 5, "table": 5, "chair": 5},
                     furniture=[row(1, "bed", 80, 90, 149)])
        ov.dine_full[level["id"]] = ov.fill_mark(level)
        ov.game = g = TileStub(ov.sites, [], ov.free)
        ov.house_rooms()
        self.assertEqual(ov.roles[undug["id"]], "dine_more")
        ov.furnish()
        ov.meeting()
        ov.rezone()
        self.assertNotIn({"kind": "dormitory", "site": level["id"]}, g.tools("make_zone"))

    def test_rezone_still_zones_loose_beds_elsewhere(self):
        level = dict(SMALL, open_tiles=9)
        ov, _ = fort([WIDE, level], furniture=[row(1, "bed", 80, 90, 149)])
        ov.game = g = TileStub(ov.sites, [], ov.free)
        ov.rezone()
        self.assertEqual(g.tools("make_zone"), [{"kind": "dormitory", "site": level["id"]}])


if __name__ == "__main__":
    unittest.main()
