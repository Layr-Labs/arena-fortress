"""cx stage A (CX_REVIEW §0, owner-approved): one measured use rate per fort replaces the two constant families
(ALLOC_* 0.33/0.16 vs DRINK/FOOD_PER_CIT_DAY 0.06/0.024, 5-7x apart); the constants are only the priors until the
fort's own falling looks give a rate. No game or network."""
import io
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


def resp(day, drink, food, cit=10, days=336):
    obs = {"date": {"abs_tick": day * harness.DAY}, "administrators": {"citizens": cit},
           "stocks": {"drink": drink, "food_edible": food}, "map": {"sites": []}, "workshops": [], "orders": []}
    return {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": days - day}


class MeasuredRates(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def feed(self, series, cit=10):
        ov = harness.Overseer(FakeGame(), days=336)
        for day, drink, food in series:
            ov.load(resp(day, drink, food, cit))
        return ov

    def test_priors_until_enough_falling_looks(self):
        ov = self.feed([(10, 300, 200), (12, 299, 199), (14, 298, 198)])
        self.assertIsNone(ov.measured_rate("drink"))
        self.assertAlmostEqual(ov.leg_days()[0], 298 / (harness.ALLOC_DRINK_PER_CIT_DAY * 10))
        self.assertAlmostEqual(ov.hold_drink_rate(), harness.DRINK_PER_CIT_DAY * 10)

    def test_the_mY1_3_shape_reads_its_own_rate(self):
        # ~0.05 drink per citizen-day (hint MY1-3's F), 10 citizens: 1 a day, looks 2 days apart
        ov = self.feed([(100 + 2 * i, 300 - 2 * i, 200 - i) for i in range(8)])
        self.assertAlmostEqual(ov.measured_rate("drink"), 0.1)
        self.assertAlmostEqual(ov.measured_rate("food"), 0.05)
        dd, fd = ov.leg_days()
        self.assertAlmostEqual(dd, 286 / 1.0)   # real days at the fort's own use
        self.assertAlmostEqual(fd, 193 / 0.5)
        self.assertAlmostEqual(ov.hold_drink_rate(), 1.0)   # the hold reads the same rate

    def test_production_intervals_are_left_out(self):
        # brewing lifts drink every other look: only the falling looks measure the use
        series, drink = [], 300
        for i in range(12):
            drink += 10 if i % 2 else -4
            series.append((100 + 2 * i, drink, 200 - i))
        ov = self.feed(series)
        self.assertAlmostEqual(ov.measured_rate("drink"), 0.2)   # 4 per 2 days for 10 citizens

    def test_the_rate_is_clamped(self):
        ov = self.feed([(100 + 2 * i, 1000 - 100 * i, 200) for i in range(8)])
        self.assertLessEqual(ov.measured_rate("drink"), harness.RATE_CLAMP["drink"][1])
        ov = self.feed([(100 + 2 * i, 300 - (i % 2), 200) for i in range(12)], cit=100)   # 0.005 a citizen-day
        self.assertEqual(ov.measured_rate("drink"), harness.RATE_CLAMP["drink"][0])
        ov = self.feed([(100 + 2 * i, 300, 200) for i in range(8)])   # flat (capped and refilled): no measure
        self.assertIsNone(ov.measured_rate("drink"))

    def test_a_leg_draining_out_before_the_end_keeps_its_side(self):
        # drink measured at 0.1 per citizen-day is "ahead" of food on gross days, but its net drain (-1/day)
        # empties it with 120 days of the run left: the brew side stays
        ov = self.feed([(100 + i, 114 - i, 90) for i in range(15)])
        dd, fd = ov.leg_days()
        self.assertGreater(dd, harness.ALLOC_AHEAD * fd)
        self.assertEqual(ov.legs_run_out(), (True, False))
        self.assertIn("brew", ov.allocation())

    def test_the_caravan_settling_is_left_out(self):
        ov = harness.Overseer(FakeGame(), days=336)
        ov.caravan_settling = lambda: True
        for i in range(8):
            ov.load(resp(100 + 2 * i, 300 - 20 * i, 200))
        self.assertIsNone(ov.measured_rate("drink"))


if __name__ == "__main__":
    unittest.main()
