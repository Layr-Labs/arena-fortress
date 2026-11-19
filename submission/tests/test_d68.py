"""d68: the cougar is a lockdown beast. It was kept only for the first felling's wait (openplay.PREDATORS), below
BEASTS' size rule; measured: one roamed the surface 55 tiles from the wagon for two weeks of a full local OP1 year
while the beast look, reading BEASTS, never saw it, and on day 200 it fought a dwarf - ten strike details,
exhaustion, knocked out - and the dwarf died (survival 0.762, O 67.5, tier 0). The lockdown would have shut the
stair while it passed."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from overseer.beasts import BEASTS, in_sight  # noqa: E402


WAGON = {"x": 100, "y": 95, "z": 106}


class D68(unittest.TestCase):
    def test_the_cougar_is_a_large_predator(self):
        self.assertIn("COUGAR", BEASTS)

    def test_a_cougar_fifty_five_tiles_out_is_found(self):
        found, sure = in_sight([{"id": 1, "race": "COUGAR", "x": 103, "y": 150, "z": 106}], 1, WAGON)
        self.assertEqual([(b["race"], b["dist"]) for b in found], [("COUGAR", 55)])
        self.assertTrue(sure)

    def test_the_water_lurkers_are_unchanged(self):
        from overseer.beasts import LURKERS, LURK_SCALE
        found, _ = in_sight([{"id": 2, "race": "ALLIGATOR", "x": 104, "y": 95, "z": 106}], 1, WAGON)
        self.assertEqual(found[0]["dist"], 4 * LURK_SCALE)


if __name__ == "__main__":
    unittest.main()
