"""d37: one meeting area below ground on open tasks, so idle dwarves leave the wagon."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import StubGame, overseer, resp  # noqa: E402
from overseer import harness as H  # noqa: E402

DINE_LEVEL = {"id": "A9", "kind": "A", "x": 97, "y": 93, "z": 128, "w": 13, "h": 7, "open_tiles": 83,
              "subterranean": True}
FARM_LEVEL = {"id": "A5", "kind": "A", "x": 97, "y": 93, "z": 130, "w": 7, "h": 3, "open_tiles": 19,
              "subterranean": True}
FARM_ROOM = {"id": "R2", "kind": "R", "x": 97, "y": 93, "z": 130, "w": 3, "h": 3, "dug": True,
             "subterranean": True, "used_by": ["farm plot 1"]}
SPARE_ROOM = {"id": "R7", "kind": "R", "x": 101, "y": 93, "z": 127, "w": 3, "h": 3, "dug": True,
              "subterranean": True}
BIG_LEVEL = {"id": "A10", "kind": "A", "x": 67, "y": 71, "z": 126, "w": 42, "h": 51, "open_tiles": 143,
             "subterranean": True}
DINING = {"id": 11, "type": "DiningHall", "x": 97, "y": 93, "z": 128, "w": 13, "h": 7, "furniture": {}}
DORM = {"id": 8, "type": "Dormitory", "x": 97, "y": 93, "z": 128, "w": 13, "h": 7, "furniture": {}}


def fort(sites, zones=(), day=60):
    r = resp(336 - day, day, food=60)
    o = r["observation"]
    o["map"].update(surface_z=131, sites=[dict(s) for s in sites])
    o["zones"] = [dict(z) for z in zones]
    return r


def made(g):
    return [a for t, a in g.calls if t == "make_zone" and a.get("kind") == "meeting_area"]


class D37(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_meeting_area_goes_on_the_dining_level(self):
        ov, g = overseer(fort([FARM_LEVEL, FARM_ROOM, SPARE_ROOM, DINE_LEVEL], [DINING, DORM]))
        ov.meeting()
        self.assertEqual(made(g), [{"kind": "meeting_area", "site": "A9"}])
        self.assertEqual(ov.meeting_made, "A9")

    def test_once_made_never_again(self):
        ov, g = overseer(fort([DINE_LEVEL], [DINING]))
        ov.meeting()
        ov.now += 5 * H.DAY
        ov.meeting()
        self.assertEqual(len(made(g)), 1)

    def test_a_standing_meeting_area_is_left_alone(self):
        hall = {"id": 30, "type": "MeetingHall", "x": 0, "y": 0, "z": 128, "w": 3, "h": 3}
        ov, g = overseer(fort([DINE_LEVEL], [DINING, hall]))
        ov.meeting()
        self.assertEqual(g.calls, [])

    def test_early_on_only_where_the_fort_eats_or_sleeps(self):
        ov, g = overseer(fort([SPARE_ROOM, DINE_LEVEL], [], day=12))
        ov.meeting()
        self.assertEqual(g.calls, [])                        # no dining or dormitory zone yet
        ov2, g2 = overseer(fort([SPARE_ROOM, DINE_LEVEL], [DORM], day=12))
        ov2.meeting()
        self.assertEqual(made(g2), [{"kind": "meeting_area", "site": "A9"}])

    def test_later_any_fitting_site_off_the_farm_levels(self):
        ov, g = overseer(fort([FARM_LEVEL, FARM_ROOM, BIG_LEVEL, SPARE_ROOM], [], day=60))
        ov.meeting()
        self.assertEqual(made(g), [{"kind": "meeting_area", "site": "R7"}])   # A10 is too big, A5 is a farm level

    def test_surface_and_unknown_surface_sites_are_not_used(self):
        top = dict(DINE_LEVEL, z=131)
        ov, g = overseer(fort([top], [dict(DINING, z=131)]))
        ov.meeting()
        self.assertEqual(g.calls, [])
        r = fort([DINE_LEVEL], [DINING])
        del r["observation"]["map"]["surface_z"]
        ov2, g2 = overseer(r)
        ov2.meeting()
        self.assertEqual(g2.calls, [])

    def test_lab_task_makes_none(self):
        r = fort([DINE_LEVEL], [DINING])
        g = StubGame()
        ov = H.Overseer(g, goal="Run the fortress", days=60)
        ov.set_task({"goal": "Keep the fort supplied.", "hands_off": {"from_day": 39}})
        r["hands_off_in_days"] = 20
        ov.load(r)
        ov.count = 0
        ov.meeting()
        self.assertEqual(g.calls, [])

    def test_refusals_are_asked_at_most_three_times(self):
        ov, g = overseer(fort([DINE_LEVEL, dict(SPARE_ROOM)], [DINING]), refuse=[("make_zone", None)])
        for _ in range(8):
            ov.meeting()
            ov.now += 2 * H.DAY
        self.assertEqual(len(made(g)), H.MEETING_TRIES)
        self.assertIsNone(ov.meeting_made)

    def test_plan_makes_it_in_a_pass(self):
        ov, g = overseer(fort([DINE_LEVEL], [DINING, DORM]))
        ov.plan()
        self.assertEqual(made(g), [{"kind": "meeting_area", "site": "A9"}])


if __name__ == "__main__":
    unittest.main()
