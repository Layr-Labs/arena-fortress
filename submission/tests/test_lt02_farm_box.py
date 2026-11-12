"""cx LT02 farm box (hint std LT02-4 on 5c14f02, 2026-11-12): on day 17 the layer dug R3 (soil) as a farm room and,
in the same pass, skipped R4's 9x7 dorm box because it covered R3 still waiting for its plot (bb1feb6's OP1-2 rule).
R4 was dug 3x3 and zoned a bedroom; the fort stood at 3 plots and drink read 0 from d35 to d49. On b092a1d the same
box was dug 9x7 on d12, F3-F9 were listed on its floor and the model built 4 plots there (5 plots, drink from d33 to
the end in all 6 std LT02 forts). The skip stays for open play (OP1/MY1). Shapes are the record's day-17
observation. No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness
from test_cx_alloc import FakeGame, resp

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


def room(rid, x, y, soil=True, dug=False, used_by=None):
    return {"id": rid, "kind": "R", "x": x, "y": y, "z": 135, "w": 3, "h": 3, "soil": soil, "subterranean": True,
            "designated": dug, "dug": dug, "free": not used_by, "used_by": used_by}


R1 = room("R1", 100, 92, soil=False, dug=True, used_by=["MeetingHall 7", "farm plot 10"])
R2 = room("R2", 96, 92, dug=True, used_by=["DiningHall 11", "farm plot 6"])
R3 = room("R3", 94, 98)
R4 = room("R4", 90, 98, soil=False)
PLOTS = [{"id": 6, "x": 96, "y": 92, "z": 135, "w": 3, "h": 3}, {"id": 10, "x": 100, "y": 92, "z": 135, "w": 3, "h": 3}]


class LabFarmBox(unittest.TestCase):
    def setUp(self):
        out = redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def ov(self, hands_off=52, days=90):
        game = FakeGame()
        ov = harness.Overseer(game, goal="", days=days)
        r = resp(day=17, days=days, cit=17, drink=0, pb=0, hands_off=hands_off,
                 extra={"map": {"sites": [dict(s) for s in (R1, R2, R3, R4)]},
                        "farm_plots": [dict(p) for p in PLOTS]})
        ov.load(r)
        ov.count = 0
        ov.roles.update({"R2": "farm"})   # R1 holds the meeting area (the record: z_meeting)
        return ov, game

    @staticmethod
    def digs(game):
        return [a for t, a in game.calls if t == "dig_room"]

    def test_lab_digs_the_grown_box_over_the_new_farm_room(self):
        ov, game = self.ov()
        ov.digging()
        digs = self.digs(game)
        self.assertIn({"site": "R3"}, digs)                   # the farm room first (soil, farms short)
        self.assertEqual(ov.roles.get("R3"), "farm")
        self.assertIn({"site": "R4", "w": 9, "h": 7}, digs)   # then R4's people box, as on b092a1d
        self.assertTrue(ov.farm_claimed(dict(R4, w=9, h=7)))  # the box does cover the waiting farm room

    def test_open_play_keeps_the_op12_skip(self):
        ov, game = self.ov(hands_off=None, days=336)
        ov.digging()
        self.assertNotIn({"site": "R4", "w": 9, "h": 7}, self.digs(game))


if __name__ == "__main__":
    unittest.main()
