"""cx stage C (CX_REVIEW P1-2/§3-2, owner-approved): the plant budget. One plan answers the allocation's one-shots,
the rot guard and the glut bank from one reading of both legs; the reserve carried into the last stretch covers F's
drink at the fort's measured use (f_need) when that is above the 2 per citizen the 100-point forts carried; the
food-lean keeper never arms on a drink leg whose own net drain empties it before the end. No game or network."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {"order_id": len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {"units": []}}


def resp(day, drink, food, cit=20, pb=30, days=216):
    obs = {"date": {"abs_tick": day * harness.DAY}, "administrators": {"citizens": cit},
           "stocks": {"drink": drink, "food_edible": food, "plants_brewable": pb, "plants_total": pb,
                      "barrels_empty": 10, "seeds": 40},
           "map": {"sites": []}, "workshops": [{"type": t, "built": True} for t in ("Still", "Kitchen")],
           "orders": []}
    return {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": days - day}


class PlantPlan(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        self.output = redirect_stdout(self.stream)
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def feed(self, series, cit=20, days=216):
        ov = harness.Overseer(FakeGame(), days=days)
        for day, drink, food in series:
            ov.load(resp(day, drink, food, cit=cit, days=days))
        ov.count = 0
        return ov

    def test_f_need_follows_the_measured_drink_use(self):
        ov = self.feed([(100 + 2 * i, 900 - 2 * 20 * i, 300) for i in range(8)])   # 1.0 per citizen-day
        self.assertAlmostEqual(ov.measured_rate("drink"), 1.0)
        need = harness.math.ceil(harness.HOLD_COVER * 1.0 * 20 * ov.f_len() / 5)
        self.assertEqual(ov.f_need(), need)
        self.assertEqual(ov.plant_reserve(), max(harness.PLANT_RESERVE_PER_CIT * 20, need))
        ov2 = self.feed([(100 + 2 * i, 300, 300) for i in range(3)])   # prior: the documented 0.06
        self.assertEqual(ov2.plant_reserve(), harness.PLANT_RESERVE_PER_CIT * 20)   # 2/citizen stays the floor

    def test_lean_does_not_arm_on_a_drink_leg_running_out(self):
        # last 64 days, drink far ahead of food on cover days, but draining 8/day: empty in ~36 days of 50 left
        series = [(152 + i, 400 - 8 * i, 60) for i in range(15)]
        ov = self.feed(series)
        dd, fd = ov.leg_days()
        self.assertGreaterEqual(dd, harness.LEAN_AHEAD * fd)
        self.assertTrue(ov.legs_run_out()[0])
        self.assertFalse(ov.food_lean())
        ov.lean_drink = 300   # armed earlier: it lets go once the drain shows
        self.assertFalse(ov.food_lean())
        self.assertIsNone(ov.lean_drink)

    def test_one_plan_is_logged_and_read_by_the_consumers(self):
        ov = self.feed([(100 + 2 * i, 300, 300 - i) for i in range(4)])
        plan = ov.plant_plan()
        for k in ("sides", "lean", "hold", "last", "floor", "rot_keep", "f_need", "reserve", "food_first", "in_f"):
            self.assertIn(k, plan)
        logged = [json.loads(l) for l in self.stream.getvalue().splitlines() if '"plant_plan"' in l]
        self.assertEqual(len(logged), 1)
        ov.plant_plan()   # unchanged: not logged again
        logged = [json.loads(l) for l in self.stream.getvalue().splitlines() if '"plant_plan"' in l]
        self.assertEqual(len(logged), 1)
        ov.allocate_plants()
        brew = [a for t, a in ov.game.calls if a.get("recipe") == "brew_drink"]
        if "brew" in plan["sides"] and brew:
            self.assertLessEqual(brew[0]["amount"], 30 - plan["floor"])


if __name__ == "__main__":
    unittest.main()
