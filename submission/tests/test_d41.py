"""d41: the review's fixes: office sites inside the zone, chair retries that give a site up, meeting rooms a zone
already uses, farm plots outside the layer's rooms, the winter brew order replaced at the endgame, unreadable fields."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import StubGame, overseer, resp  # noqa: E402
from test_d33 import ZoneGame, with_game  # noqa: E402
from test_d38 import fort, office_zone  # noqa: E402
from test_d37 import DINING, DORM, made  # noqa: E402
from test_d37 import fort as meeting_fort  # noqa: E402
from overseer import harness as H  # noqa: E402


class NoMaterialGame(ZoneGame):
    def act(self, tool, args):
        if tool == "place_furniture":
            self.calls.append((tool, dict(args)))
            return {"ok": False, "error_code": "no_material", "error": "scripted"}
        return super().act(tool, args)


class D41(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_grown_level_with_the_same_corner_is_not_the_office_site(self):
        grown = {"id": "A9", "kind": "A", "x": 10, "y": 10, "z": 149, "w": 13, "h": 7, "open_tiles": 60}
        room = {"id": "R5", "kind": "R", "x": 12, "y": 11, "z": 149, "w": 3, "h": 3, "dug": True}
        zone = {"id": 6, "type": "Office", "x": 10, "y": 10, "z": 149, "w": 9, "h": 6, "owner": 5, "furniture": {}}
        g = ZoneGame()
        ov = with_game(fort([grown, room], zones=[zone], day=12), g)
        ov.office()
        self.assertEqual(g.calls, [("place_furniture", {"kind": "chair", "site": "R5"})])

    def test_chair_failures_give_the_site_up_and_a_new_office_follows(self):
        room = {"id": "R5", "kind": "R", "x": 12, "y": 11, "z": 149, "w": 3, "h": 3, "dug": True}
        other = {"id": "R7", "kind": "R", "x": 20, "y": 11, "z": 147, "w": 3, "h": 3, "dug": True}
        g = NoMaterialGame()
        ov = with_game(fort([room, other], zones=[office_zone(6, room)], day=12), g)
        for _ in range(12):
            ov.office()
            ov.now += 2 * H.DAY
        chairs = [a["site"] for t, a in g.calls if t == "place_furniture"]
        self.assertEqual(chairs[:4], ["R5"] * 4)
        self.assertIn("R5", ov.office_bad)
        self.assertIn(("make_zone", {"kind": "office", "site": "R7"}), g.calls)

    def test_meeting_skips_rooms_a_zone_already_uses(self):
        big = {"id": "A9", "kind": "A", "x": 60, "y": 60, "z": 128, "w": 43, "h": 51, "open_tiles": 150,
               "subterranean": True}
        r1 = {"id": "R1", "kind": "R", "x": 97, "y": 93, "z": 128, "w": 3, "h": 3, "dug": True, "subterranean": True,
              "used_by": ["DiningHall 11"], "free": False}
        r3 = {"id": "R3", "kind": "R", "x": 101, "y": 93, "z": 127, "w": 3, "h": 3, "dug": True, "subterranean": True,
              "free": True}
        ov, g = overseer(meeting_fort([big, r1, r3], [DINING, DORM], day=60))
        ov.meeting()
        self.assertEqual(made(g), [{"kind": "meeting_area", "site": "R3"}])

    def test_a_farm_plot_outside_the_layers_rooms_marks_its_level(self):
        plot_level = {"id": "A1", "kind": "A", "x": 50, "y": 50, "z": 140, "w": 3, "h": 3, "open_tiles": 9}
        r = fort([plot_level], day=12)
        r["observation"]["farm_plots"] = [{"id": 3, "x": 50, "y": 50, "z": 140, "w": 3, "h": 3, "built": True}]
        g = ZoneGame()
        ov = with_game(r, g)
        self.assertIn(140, ov.farm_levels())
        ov.office()
        self.assertNotIn("make_zone", [t for t, _ in g.calls])

    def test_a_farm_room_taken_for_dining_is_no_farm(self):
        dine_room = {"id": "R5", "kind": "R", "x": 93, "y": 97, "z": 128, "w": 3, "h": 3, "dug": True,
                     "used_by": ["DiningHall 12"], "free": False}
        level = {"id": "A9", "kind": "A", "x": 89, "y": 97, "z": 128, "w": 7, "h": 5, "open_tiles": 35,
                 "subterranean": True}
        dining = {"id": 12, "type": "DiningHall", "x": 89, "y": 97, "z": 128, "w": 7, "h": 5}
        ov, g = overseer(meeting_fort([dine_room, level], [dining], day=12))
        ov.roles["R5"] = "farm"                      # given at designation, then the dining hall took the room
        self.assertNotIn(128, ov.farm_levels())
        ov.meeting()
        self.assertEqual(made(g), [{"kind": "meeting_area", "site": "A9"}])

    def test_winter_brew_order_gives_way_to_the_endgames(self):
        ov, g = overseer(resp(150, 186, food=60, cit=10))
        ov.closer()
        brew = [a for t, a in g.calls if t == "add_order" and a.get("recipe") == "brew_drink"]
        self.assertEqual(len(brew), 1)
        self.assertIn({"stock": "drink", "below": 600}, brew[0]["when"])
        wid = ov.winter_brew_id
        self.assertIsNotNone(wid)
        r = resp(30, 306, food=60, cit=30, orders=[{"id": wid, "recipe": "brew_drink", "repeat": "daily", "left": 4}])
        ov.load(r)
        ov.count = 0
        ov.closer()
        self.assertIn(("cancel_order", {"order_id": wid}), g.calls)
        brew = [a for t, a in g.calls if t == "add_order" and a.get("recipe") == "brew_drink"]
        self.assertEqual(len(brew), 2)
        self.assertIn({"stock": "drink", "below": 900}, brew[1]["when"])
        self.assertIn({"stock": "plants_brewable", "at_least": 30}, brew[1]["when"])

    def test_unreadable_site_fields_skip_only_that_site(self):
        bad = {"id": "A1", "kind": "A", "x": 50, "y": 50, "z": 140, "w": "ERR: probe failed", "h": 3,
               "open_tiles": "ERR: probe failed", "subterranean": True}
        good = {"id": "R7", "kind": "R", "x": 20, "y": 11, "z": 127, "w": 3, "h": 3, "dug": True, "free": True,
                "subterranean": True}
        g = ZoneGame()
        ov = with_game(fort([bad, good], day=60), g)
        ov.office()                                           # must not raise
        self.assertIn(("make_zone", {"kind": "office", "site": "R7"}), g.calls)
        ov2, g2 = overseer(meeting_fort([bad, good], [], day=60))
        ov2.meeting()                                         # must not raise
        self.assertEqual(made(g2), [{"kind": "meeting_area", "site": "R7"}])


if __name__ == "__main__":
    unittest.main()
