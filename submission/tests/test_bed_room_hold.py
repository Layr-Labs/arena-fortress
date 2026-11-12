"""cx bed room (hint hard OP1-3 on 014f7eb): on day 16 farms() built F1/F2 over R2/R1, the fort's only dug rooms, in
the pass the first bed stood free; every bed placement answered no_space until day 84. While beds are short and one
is free or on order, a plot never takes the last unplotted dug room once a plot stands. No game."""
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

# the record's day-16 sites: R1/R2 dug beside the stair, the game's F1/F2 soil sites on their floors
R1 = {"id": "R1", "kind": "R", "x": 99, "y": 95, "z": 149, "w": 3, "h": 3, "dug": True, "designated": True,
      "soil": True, "used_by": ["Dormitory 8"], "free": False}
R2 = dict(R1, id="R2", x=95)
F1 = {"id": "F1", "kind": "F", "x": 95, "y": 95, "z": 149, "w": 3, "h": 3, "soil": True, "subterranean": True}
F2 = dict(F1, id="F2", x=99)


class Base(unittest.TestCase):
    def setUp(self):
        out = redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def ov(self, sites=(R1, R2, F1, F2), beds_free=1, drink=60, plots=(), furniture=(), orders=()):
        game = FakeGame()
        ov = harness.Overseer(game, days=336)
        people = [{"id": 87 + i, "stress": 3} for i in range(7)]
        r = resp(day=16, cit=7, drink=drink, orders=orders,
                 extra={"dwarves": people, "map": {"sites": [dict(s) for s in sites]},
                        "farm_plots": list(plots), "furniture": list(furniture)})
        r["observation"]["stocks"]["furniture_free"] = {"bed": beds_free}
        ov.load(r)
        ov.count = 0
        ov.my1_plan = lambda: False
        ov.f_drink_rate = lambda prior_only=False: 7 * 0.25   # ~1.75/day: 60 drink lasts 34 days
        return ov, game

    @staticmethod
    def ids(cands):
        return [c.get("id") for c in cands]


class Hold(Base):
    def test_measured_day_16_keeps_one_room(self):
        ov, _ = self.ov()
        self.assertEqual(self.ids(ov.bed_room_hold([F1, F2], [])), ["F1"])

    def test_farms_builds_one_plot_and_leaves_r1_for_the_beds(self):
        ov, game = self.ov()
        ov.farm_target = lambda: 6
        ov.seed_rush = lambda: False
        ov.live_seeds_by_kind = lambda: {"MUSHROOM_HELMET_PLUMP": {"underground": True}}
        ov.farms()
        self.assertEqual([a.get("site") for t, a in game.calls if t == "build_farm"], ["F1"])

    def test_first_plot_is_never_held(self):
        ov, _ = self.ov(sites=(R1, F2))
        self.assertEqual(self.ids(ov.bed_room_hold([F2], [])), ["F2"])

    def test_a_standing_plot_counts(self):
        plot = {"id": 10, "x": 95, "y": 95, "z": 149, "w": 3, "h": 3}
        ov, _ = self.ov(plots=[plot])
        self.assertEqual(self.ids(ov.bed_room_hold([F2], [plot])), [])

    def test_another_free_room_lets_it_go(self):
        r3 = dict(R1, id="R3", x=120, used_by=[])
        ov, _ = self.ov(sites=(R1, R2, r3, F1, F2))
        self.assertEqual(self.ids(ov.bed_room_hold([F1, F2], [])), ["F1", "F2"])

    def test_no_bed_free_or_on_order(self):
        ov, _ = self.ov(beds_free=0)
        self.assertEqual(self.ids(ov.bed_room_hold([F1, F2], [])), ["F1", "F2"])
        ov, _ = self.ov(beds_free=0, orders=[{"id": 5, "recipe": "make_bed", "left": 3}])
        self.assertEqual(self.ids(ov.bed_room_hold([F1, F2], [])), ["F1"])

    def test_beds_placed_for_everyone(self):
        beds = [{"kind": "bed", "x": 120 + i, "y": 5, "z": 149} for i in range(7)]
        ov, _ = self.ov(furniture=beds)
        ov.placed = {"bed": 7}
        self.assertEqual(self.ids(ov.bed_room_hold([F1, F2], [])), ["F1", "F2"])

    def test_drink_short_or_my1_plan_or_switch_off(self):
        ov, _ = self.ov(drink=20)   # 20 / 1.75 = 11 days < BED_ROOM_DRINK_DAYS
        self.assertEqual(self.ids(ov.bed_room_hold([F1, F2], [])), ["F1", "F2"])
        ov, _ = self.ov()
        ov.my1_plan = lambda: True
        self.assertEqual(self.ids(ov.bed_room_hold([F1, F2], [])), ["F1", "F2"])
        old = harness.BED_ROOM_HOLD
        harness.BED_ROOM_HOLD = False
        try:
            ov, _ = self.ov()
            self.assertEqual(self.ids(ov.bed_room_hold([F1, F2], [])), ["F1", "F2"])
        finally:
            harness.BED_ROOM_HOLD = old


if __name__ == "__main__":
    unittest.main()
