"""Dorm dig sized to the beds still needed. No game or network."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overseer import harness


class DormSize(unittest.TestCase):
    def size(self, cit, beds):
        o = harness.Overseer(None)
        o.cit, o.placed = cit, {"bed": beds} if beds else {}
        return o.dorm_size()

    def test_full_year_reserves_future_migrants(self):
        o = harness.Overseer(None, days=336)
        o.cit, o.placed = 7, {}
        size = o.dorm_size()
        self.assertGreaterEqual(size['w'] * size['h'], 30)

    def test_migrant_reserve_fits_before_sites_are_exhausted(self):
        o = harness.Overseer(None, goal="migrants arriving")
        o.cit, o.placed = 36, {"bed": 2}
        size = o.dorm_size()
        self.assertGreaterEqual(size["w"] * size["h"], o.bed_target() - 2)

    def test_size_fits_citizens_plus_spare(self):
        for cit, beds, want in ((7, 0, {"w": 4, "h": 3}), (3, 0, {"w": 3, "h": 3}), (19, 3, {"w": 5, "h": 4}),
                                (19, 21, {"w": 3, "h": 3}), (200, 0, {"w": 15, "h": 14})):
            with self.subTest(cit=cit, beds=beds):
                got = self.size(cit, beds)
                self.assertEqual(got, want)
                self.assertGreaterEqual(got["w"] * got["h"], min(225, cit + harness.DORM_SPARE - beds))


if __name__ == "__main__":
    unittest.main()
