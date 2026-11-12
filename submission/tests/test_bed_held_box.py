"""cx held box (hint std OP1-3 / OP1-0 on bb1feb6, growth 0.19 / 0.28): bed_room_hold kept R1 off F2 (day 14 / 8), the
model zoned a dormitory over R1, R1 left the farm count and house_blocked stayed False, so digging() never opened the
9x7 dorm / 7x5 dine boxes and every later soil room went 3x3 to the farms until the dry sites ran out. A room the hold
kept for the beds counts toward HOUSE_AFTER_FARMS and, while it holds no plot, the people boxes take the next R sites.
Replay of both records (5ba40eb -> patched): OP1-3 d33 R3 9x7 + R4 7x5 (was R3/R4 3x3 farms), OP1-0 d49 R3 9x7. No game."""
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

# the OP1-3 record's day-33 sites: R1 (held, Dormitory 12), R2 (F1's plot), R3/R4 undug soil
R1 = {"id": "R1", "kind": "R", "x": 99, "y": 95, "z": 149, "w": 3, "h": 3, "dug": True, "designated": True,
      "soil": True, "used_by": ["Dormitory 12"], "free": False}
R2 = dict(R1, id="R2", x=95, used_by=["Dormitory 12", "farm plot 10"])
R3 = {"id": "R3", "kind": "R", "x": 91, "y": 99, "z": 149, "w": 3, "h": 3, "dug": False, "designated": False,
      "soil": True, "free": True}
R4 = dict(R3, id="R4", x=97)
PLOT10 = {"id": 10, "x": 95, "y": 95, "z": 149, "w": 3, "h": 3}


class Base(unittest.TestCase):
    def setUp(self):
        out = redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)
        self.addCleanup(setattr, harness, "BED_HELD_BOX", harness.BED_HELD_BOX)

    def ov(self, held=("R1",), r1=R1, plots=(PLOT10,)):
        game = FakeGame()
        ov = harness.Overseer(game, days=336)
        people = [{"id": 87 + i, "stress": 3, "adult": True} for i in range(7)]
        r = resp(day=33, cit=7, extra={"dwarves": people, "farm_plots": list(plots),
                                       "map": {"sites": [dict(s) for s in (r1, R2, R3, R4)]}})
        r["observation"]["stocks"]["furniture_free"] = {"bed": 0, "table": 6, "chair": 6}
        ov.load(r)
        ov.count = 0
        ov.roles.update({"R1": "farm", "R2": "farm"})
        ov.bed_held |= set(held)
        for sid in ("R3", "R4"):
            ov.water_cache[sid], ov.water_cache_day[sid] = 0, 33
        ov.farm_target = lambda: 6
        ov.house_blocked = lambda full=False: False   # the beds stand in R1: nothing is blocked
        return ov, game

    @staticmethod
    def digs(game):
        return [a for t, a in game.calls if t == "dig_room"]


class HeldBox(Base):
    def test_held_room_opens_the_people_boxes(self):
        ov, game = self.ov()
        self.assertEqual([r["id"] for r in ov.bed_held_rooms()], ["R1"])
        ov.digging()
        self.assertIn({"site": "R3", "w": 9, "h": 7}, self.digs(game))
        self.assertIn({"site": "R4", "w": 7, "h": 5}, self.digs(game))
        self.assertEqual((ov.roles.get("R3"), ov.roles.get("R4")), ("dorm", "dine"))

    def test_switch_off_is_the_old_farm_dig(self):
        harness.BED_HELD_BOX = False
        ov, game = self.ov()
        ov.digging()
        self.assertEqual(self.digs(game), [{"site": "R3"}, {"site": "R4"}])
        self.assertEqual((ov.roles.get("R3"), ov.roles.get("R4")), ("farm", "farm"))

    def test_no_hold_no_change(self):
        ov, game = self.ov(held=())
        ov.digging()
        self.assertEqual(self.digs(game), [{"site": "R3"}, {"site": "R4"}])

    def test_a_plot_on_the_held_room_ends_the_stop_gap(self):
        plot = dict(PLOT10, id=11, x=99)
        ov, game = self.ov(r1=dict(R1, used_by=["farm plot 11"]), plots=(PLOT10, plot))
        self.assertEqual(ov.bed_held_rooms(), [])
        ov.digging()
        # two plots: the farm count alone meets HOUSE_AFTER_FARMS, but nothing is blocked: the soil rooms farm
        self.assertEqual(self.digs(game), [{"site": "R3"}, {"site": "R4"}])

    def test_held_room_in_use_claims_no_box(self):
        ov, _ = self.ov()
        box = dict(R4, x=97, y=93, w=9, h=7)   # covers R1
        self.assertFalse(ov.farm_claimed(box))
        harness.BED_HELD_BOX = False
        self.assertTrue(ov.farm_claimed(box))

    def test_hold_records_the_kept_room(self):
        ov, _ = self.ov(held=())
        ov.placed_dry = lambda kind: 0
        ov.free["bed"] = 1
        ov.my1_plan = lambda: False
        ov.f_drink_rate = lambda prior_only=False: 0.0
        f2 = {"id": "F2", "kind": "F", "x": 99, "y": 95, "z": 149, "w": 3, "h": 3, "soil": True}
        r1 = dict(R1, used_by=[])
        ov.sites = [s if s.get("id") != "R1" else r1 for s in ov.sites]
        ov.bed_room_hold([f2], [PLOT10])
        self.assertIn("R1", ov.bed_held)


if __name__ == "__main__":
    unittest.main()
