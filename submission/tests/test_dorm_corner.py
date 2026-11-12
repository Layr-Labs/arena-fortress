"""cx dorm corner (hint std LT08-2 on b167a15, 2026-11-12: beds 20 for 45 at H, 38 bed items free from day 27). R2, the
9x7 dorm at (94,93,104) with Dormitory 35 on its corner, took the model's build_farm F7 on day 10 — plot 39 over R2's
own 3x3 box — and every bed for R2 then answered site_used; R2 kept its dorm role (surge_capacity counted it) and its
unreachable floor kept surge_floor_free at 42-51 for 28 beds to place. Shapes are the record's day-10 observation.
No game or network."""
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

R1 = {"id": "R1", "kind": "R", "x": 88, "y": 104, "z": 104, "w": 3, "h": 3, "soil": True, "dug": True,
      "designated": True, "stair": {"x": 91, "y": 105}, "free": False, "used_by": ["Office 11"]}
R2 = {"id": "R2", "kind": "R", "x": 94, "y": 93, "z": 104, "w": 3, "h": 3, "soil": True, "dug": True,
      "designated": True, "stair": {"x": 97, "y": 94}, "free": False, "used_by": ["Dormitory 35"]}
F7 = {"id": "F7", "kind": "F", "x": 94, "y": 93, "z": 104, "w": 3, "h": 3, "soil": True, "subterranean": True}
F10 = {"id": "F10", "kind": "F", "x": 97, "y": 95, "z": 104, "w": 3, "h": 3, "soil": True, "subterranean": True}
A1 = {"id": "A1", "kind": "A", "x": 83, "y": 67, "z": 104, "w": 41, "h": 44, "open_tiles": 135}
PLOTS = [{"id": i, "x": x, "y": y, "z": 104, "w": 3, "h": 3}
         for i, (x, y) in ((4, (92, 104)), (5, (95, 104)), (34, (88, 108)), (36, (91, 108)), (37, (94, 108)),
                           (38, (94, 96)))]
PLOT39 = {"id": 39, "x": 94, "y": 93, "z": 104, "w": 3, "h": 3}


class Base(unittest.TestCase):
    def setUp(self):
        out = redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def ov(self, sites=(R1, R2, F7, F10, A1), plots=PLOTS, beds_free=0, placed=19, cit=36, drink=560,
           orders=({"id": 9, "recipe": "make_bed", "left": 20},), surge=False):
        game = FakeGame()
        ov = harness.Overseer(game, goal="Migrants are arriving." if surge else "", days=60)
        beds = [{"kind": "bed", "x": 88 + i % 9, "y": 104 + i // 9, "z": 104} for i in range(placed)]
        r = resp(day=10, days=60, cit=cit, drink=drink, orders=orders, hands_off=29 if surge else None,
                 extra={"map": {"sites": [dict(s) for s in sites]}, "farm_plots": [dict(p) for p in plots],
                        "furniture": beds})
        r["observation"]["stocks"]["furniture_free"] = {"bed": beds_free}
        ov.load(r)
        ov.count = 0
        ov.placed = {"bed": placed}
        ov.roles.update({"R1": "dorm", "R2": "dorm"})
        ov.room_box.update({"R1": {"x": 88, "y": 104, "z": 104, "w": 9, "h": 7},
                            "R2": {"x": 94, "y": 93, "z": 104, "w": 9, "h": 7}})
        ov.my1_plan = lambda: False
        ov.f_drink_rate = lambda prior_only=False: 36 * 0.25
        return ov, game


class Corner(Base):
    def test_measured_day_10_model_f7_refused(self):
        ov, _ = self.ov()
        why = ov.room_reserved("build_farm", {"site": "F7"})
        self.assertIsNotNone(why)
        self.assertIn("R2", why)

    def test_surge_fort_measured_shape(self):
        ov, _ = self.ov(surge=True)
        self.assertTrue(ov.surge)
        self.assertIsNotNone(ov.room_reserved("build_farm", {"site": "F7"}))
        ov, _ = self.ov(surge=True, placed=ov.surge_pop())   # the forecast wave's beds all stand
        self.assertIsNone(ov.room_reserved("build_farm", {"site": "F7"}))

    def test_other_f_site_on_the_room_floor_passes(self):
        ov, _ = self.ov()
        self.assertIsNone(ov.room_reserved("build_farm", {"site": "F10"}))

    def test_layer_act_refused_locally(self):
        ov, game = self.ov()
        r = ov.act("farm_F7", "build_farm", {"site": "F7"})
        self.assertEqual(r.get("error_code"), "room_reserved")
        self.assertEqual(game.calls, [])

    def test_beds_placed_for_everyone(self):
        ov, _ = self.ov(placed=36)
        self.assertIsNone(ov.room_reserved("build_farm", {"site": "F7"}))

    def test_no_bed_free_or_on_order(self):
        ov, _ = self.ov(orders=())
        self.assertIsNone(ov.room_reserved("build_farm", {"site": "F7"}))
        ov, _ = self.ov(orders=(), beds_free=3)
        self.assertIsNotNone(ov.room_reserved("build_farm", {"site": "F7"}))

    def test_drink_short_my1_plan_or_switch(self):
        ov, _ = self.ov(drink=100)   # 100 / 9 a day < BED_ROOM_DRINK_DAYS
        self.assertIsNone(ov.room_reserved("build_farm", {"site": "F7"}))
        ov, _ = self.ov()
        ov.my1_plan = lambda: True
        self.assertIsNone(ov.room_reserved("build_farm", {"site": "F7"}))
        old = harness.DORM_CORNER_HOLD
        harness.DORM_CORNER_HOLD = False
        try:
            ov, _ = self.ov()
            self.assertIsNone(ov.room_reserved("build_farm", {"site": "F7"}))
        finally:
            harness.DORM_CORNER_HOLD = old

    def test_farm_role_room_not_held(self):
        ov, _ = self.ov()
        ov.roles["R2"] = "farm"
        self.assertIsNone(ov.room_reserved("build_farm", {"site": "F7"}))

    def test_zones_untouched(self):
        ov, _ = self.ov()
        self.assertIsNone(ov.room_reserved("make_zone", {"kind": "dormitory", "site": "R2"}))
        self.assertIsNone(ov.room_reserved("place_furniture", {"kind": "bed", "site": "R2", "w": 9, "h": 7}))


class Lost(Base):
    def closed(self):
        r2 = dict(R2, used_by=["Dormitory 35", "farm plot 39"])
        return self.ov(sites=(R1, r2, F10, A1), plots=PLOTS + [PLOT39], beds_free=21, cit=45)

    def test_role_dropped_once_closed(self):
        ov, _ = self.closed()
        ov.dorm_lost()
        self.assertNotIn("R2", ov.roles)
        self.assertEqual(ov.roles.get("R1"), "dorm")

    def test_open_room_keeps_role(self):
        ov, _ = self.ov()
        ov.dorm_lost()
        self.assertEqual(ov.roles.get("R2"), "dorm")

    def test_floor_measure_drops_closed_room_floor(self):
        ov, _ = self.ov()
        before = ov.surge_floor_free()
        ov2, _ = self.closed()
        after = ov2.surge_floor_free()
        # plot 39 itself takes 9; the rest of R2's 9x7 (63 - 4 plots' 3x3 inside it... ) is no bed's floor now
        self.assertLess(after, before - 9)
        self.assertGreaterEqual(after, 0)

    def test_closed_room_never_reached_by_bed_sites(self):
        ov, _ = self.closed()
        ids = [s.get("id") for s in ov.surge_bed_sites(ov.room_for("dorm", harness.ZONE_MAX))]
        self.assertNotIn("R2", ids)


if __name__ == "__main__":
    unittest.main()
