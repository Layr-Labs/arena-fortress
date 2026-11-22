"""d70: the layer makes no meeting area. The one d37 made below ground drew every tame animal there, and the grazers
starved (the note has the counts); idle dwarves gather at the wagon again, as in PR #124."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402
from overseer import harness as H  # noqa: E402

DINE_LEVEL = {"id": "A9", "kind": "A", "x": 97, "y": 93, "z": 128, "w": 13, "h": 7, "open_tiles": 83,
              "subterranean": True}
SPARE_ROOM = {"id": "R7", "kind": "R", "x": 101, "y": 93, "z": 127, "w": 3, "h": 3, "dug": True,
              "subterranean": True}
DINING = {"id": 11, "type": "DiningHall", "x": 97, "y": 93, "z": 128, "w": 13, "h": 7, "furniture": {}}
DORM = {"id": 8, "type": "Dormitory", "x": 97, "y": 93, "z": 128, "w": 13, "h": 7, "furniture": {}}


def fort(sites, zones=(), day=60, days=336):
    r = resp(days - day, day, food=60)
    o = r["observation"]
    o["map"].update(surface_z=131, sites=[dict(s) for s in sites])
    o["zones"] = [dict(z) for z in zones]
    return r


def meeting_zones(g):
    return [a for t, a in g.calls if t == "make_zone" and a.get("kind") == "meeting_area"]


class D70(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_a_full_pass_makes_no_meeting_area(self):
        for day in (12, 60, 200):
            ov, g = overseer(fort([SPARE_ROOM, DINE_LEVEL], [DINING, DORM], day=day))
            ov.plan()
            self.assertEqual(meeting_zones(g), [])

    def test_nor_do_later_passes(self):
        ov, g = overseer(fort([SPARE_ROOM, DINE_LEVEL], [DINING, DORM]))
        for _ in range(6):
            ov.plan()
            ov.now += 2 * H.DAY
        self.assertEqual(meeting_zones(g), [])

    def test_the_layer_has_no_meeting_rule(self):
        self.assertFalse(hasattr(H.Overseer, "meeting"))
        self.assertFalse(hasattr(H, "MEETING"))


if __name__ == "__main__":
    unittest.main()
