"""cx surge room plot (hint hard LT08-2 on c44c96b): three plots fed 48 citizens while F4/F5/F7/F8 stood listed on days
10-38, skipped as room floor; drink ended two brews under day 39's. On the surge, before the window, one F site off
every R site's own 3x3 box may take a plot while the floor still holds the beds. No game or network is used."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

R = [{"id": "R1", "kind": "R", "x": 88, "y": 104, "z": 104, "w": 3, "h": 3, "dug": True},
     {"id": "R3", "kind": "R", "x": 90, "y": 93, "z": 104, "w": 3, "h": 3, "dug": True}]
F4 = {"id": "F4", "kind": "F", "x": 90, "y": 93, "z": 104, "w": 3, "h": 3}   # R3's own box
F5 = {"id": "F5", "kind": "F", "x": 90, "y": 96, "z": 104, "w": 3, "h": 3}


class G:
    def act(self, tool, args):
        return {"ok": True, "result": {}}


class SurgeRoomPlot(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, floor=115, need=22, left=50, hands_off=29, surge=True):
        ov = harness.Overseer(G(), days=60)
        ov.sites = [dict(r) for r in R] + [dict(F4), dict(F5)]
        ov.o = {"dig_designations_pending": 0}
        ov.surge, ov.hands_off = surge, hands_off
        ov.days_to_end = lambda: left
        ov.surge_floor_free = lambda: floor
        ov.surge_pop = lambda: need - 2
        ov.placed_dry = lambda kind: 0
        return ov

    def test_takes_the_site_off_the_room_boxes(self):
        self.assertEqual([s["id"] for s in self.ov().surge_room_plots([F4, F5])], ["F5"])

    def test_never_the_room_box_itself(self):
        self.assertEqual(self.ov().surge_room_plots([F4]), [])

    def test_floor_for_the_beds_comes_first(self):
        self.assertEqual(self.ov(floor=40, need=22).surge_room_plots([F5]), [])   # 40 - 9 < 22 + 16
        self.assertEqual(len(self.ov(floor=47, need=22).surge_room_plots([F5])), 1)

    def test_too_late_to_ripen_or_not_a_surge(self):
        self.assertEqual(self.ov(left=harness.HOLD_GROW_DAYS - 1).surge_room_plots([F5]), [])
        self.assertEqual(self.ov(surge=False).surge_room_plots([F5]), [])
        self.assertEqual(self.ov(hands_off=0).surge_room_plots([F5]), [])


if __name__ == "__main__":
    unittest.main()
