"""d39: offices on dug rooms before day 10, and an office whose level grew is still found by a room inside it."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from test_d33 import ZoneGame, with_game  # noqa: E402
from test_d38 import fort, office_zone  # noqa: E402
from overseer import harness as H  # noqa: E402

DORM_LEVEL_EARLY = {"id": "A8", "kind": "A", "x": 94, "y": 97, "z": 158, "w": 9, "h": 6, "open_tiles": 30,
                    "subterranean": True}
DORM_LEVEL = {"id": "A9", "kind": "A", "x": 93, "y": 97, "z": 158, "w": 13, "h": 7, "open_tiles": 83,
              "subterranean": True}
DORM_ROOM = {"id": "R5", "kind": "R", "x": 97, "y": 97, "z": 158, "w": 3, "h": 3, "dug": True}


class D39(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_no_office_on_a_level_before_day_10(self):
        g = ZoneGame()
        ov = with_game(fort([DORM_LEVEL_EARLY, DORM_ROOM], day=3), g)
        ov.roles.update(R5="dorm")
        ov.office()
        self.assertNotIn("make_zone", [t for t, _ in g.calls])

    def test_a_level_from_day_10(self):
        g = ZoneGame()
        ov = with_game(fort([DORM_LEVEL, DORM_ROOM], day=10), g)
        ov.roles.update(R5="dorm")
        ov.office()
        self.assertEqual(g.calls[0], ("make_zone", {"kind": "office", "site": "A9"}))

    def test_office_over_a_grown_level_gets_its_chair_in_a_room_inside(self):
        z = office_zone(6, DORM_LEVEL_EARLY)             # zoned over the 9x6 box; the level is now A9, 13x7
        g = ZoneGame()
        ov = with_game(fort([DORM_LEVEL, DORM_ROOM], zones=[z], day=6), g)
        ov.office()
        self.assertEqual(g.calls, [("place_furniture", {"kind": "chair", "site": "R5"})])

    def test_exact_site_still_first(self):
        z = office_zone(8, DORM_LEVEL)
        g = ZoneGame()
        ov = with_game(fort([DORM_LEVEL, DORM_ROOM], zones=[z], day=12), g)
        ov.office()
        self.assertEqual(g.calls, [("place_furniture", {"kind": "chair", "site": "A9"})])


if __name__ == "__main__":
    unittest.main()
