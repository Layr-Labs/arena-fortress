"""d36: the office from any office the manager owns, on a site where a chair fits, and a chair ordered for it."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402
from test_d33 import ZoneGame, office_fort, with_game  # noqa: E402


def zone(zid, x, y, z, w, h, owner=5, chair=0):
    return {"id": zid, "type": "Office", "x": x, "y": y, "z": z, "w": w, "h": h, "owner": owner,
            "furniture": {"chair": chair} if chair else {}}


class D36(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_one_tile_office_gets_a_new_office_on_a_room(self):
        g = ZoneGame()
        ov = with_game(office_fort(), g)                 # the manager's only office is 1x1; R1 is a dug room
        ov.office()
        self.assertEqual([t for t, _ in g.calls], ["make_zone", "assign_zone", "place_furniture"])
        self.assertEqual(g.calls[0][1], {"kind": "office", "site": "R1"})
        self.assertEqual(g.calls[1][1], {"zone_id": 501, "dwarf_id": 5})
        self.assertEqual(g.calls[2][1], {"kind": "chair", "site": "R1"})

    def test_office_on_a_dug_room_just_gets_the_chair(self):
        r = office_fort()
        r["observation"]["zones"] = [zone(9, 20, 20, 149, 3, 3)]
        g = ZoneGame()
        ov = with_game(r, g)
        ov.office()
        self.assertEqual(g.calls, [("place_furniture", {"kind": "chair", "site": "R1"})])

    def test_any_owned_office_with_a_chair_counts(self):
        r = office_fort()
        r["observation"]["zones"] = [zone(9, 10, 10, 150, 1, 1), zone(13, 20, 20, 149, 3, 3, chair=1)]
        g = ZoneGame()
        ov = with_game(r, g)
        ov.office()
        self.assertEqual(g.calls, [])

    def test_one_tile_landing_is_never_an_office(self):
        r = office_fort()
        r["observation"]["zones"] = []
        r["observation"]["map"]["sites"] = [{"id": "A1", "kind": "A", "x": 10, "y": 10, "z": 150, "w": 1, "h": 1,
                                             "open_tiles": 1}]
        g = ZoneGame()
        ov = with_game(r, g)
        ov.office()
        self.assertNotIn("make_zone", [t for t, _ in g.calls])

    def test_open_task_orders_a_chair_for_the_office(self):
        r = office_fort()
        r["observation"]["stocks"]["furniture_free"] = {"chair": 0}
        ov, g = overseer(r)
        self.assertTrue(ov.office_chair_needed())
        ov.supply()
        self.assertTrue([a for a in g.tools("add_order") if a.get("recipe") == "make_chair"])


if __name__ == "__main__":
    unittest.main()
