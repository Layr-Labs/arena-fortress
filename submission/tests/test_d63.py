"""d63: from FINAL_STRETCH days out until the feast, a food-zero hunger cull leaves the FEAST_MIN largest animals for
the feast, as the d60 final floor does. Before d63 it took any animal at 0 food. In a forced famine on MY1 1000-p
(plan t62, tools/cull_trigger.lua) it took the last one 21 days before the horizon: the meat rotted before the
horizon, the feast had nothing, and supply fell to 0.58 (O 68.6), while the same seed on d61 kept one and scored 100.
Earlier in the game the food-zero cull is unchanged."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402
from overseer.openplay import FEAST_DAYS, FEAST_MIN, FINAL_STRETCH, HUNGER_BIG  # noqa: E402


def animal(i, race):
    return {"id": i, "race": race, "tame": True, "adult": True, "pet_owner_id": -1}


DOG, TURKEY, PIG = animal(14, "DOG"), animal(15, "BIRD_TURKEY"), animal(16, "PIG")     # sizes 3, 1.5, 10
LATE = FEAST_DAYS + 10          # days left: in the stretch, before the feast
EARLY = FINAL_STRETCH + 10      # days left: before the stretch


def marked(g):
    return [a["unit_id"] for a in g.tools("slaughter")]


def at(left, food, cit=10):
    return resp(left, 336 - left, food=food, cit=cit)


class D63(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_the_window_and_the_reserve(self):
        self.assertTrue(FEAST_DAYS < LATE <= FINAL_STRETCH < EARLY)
        self.assertEqual(FEAST_MIN, 1)

    def test_the_last_animal_waits_for_the_feast(self):
        ov, g = overseer(at(LATE, food=0), herd=[PIG])
        ov.provision()
        self.assertEqual(marked(g), [])

    def test_the_largest_is_the_one_kept(self):
        ov, g = overseer(at(LATE, food=0), herd=[DOG, TURKEY, PIG])
        ov.provision()
        self.assertEqual(marked(g), [15])                    # the smallest meal goes; the pig stays for the feast

    def test_a_big_fort_takes_all_but_the_reserve(self):
        ov, g = overseer(at(LATE, food=0, cit=HUNGER_BIG), herd=[DOG, PIG])    # two a pass at this size
        ov.provision()
        self.assertEqual(marked(g), [14])

    def test_before_the_stretch_the_last_one_still_goes(self):
        ov, g = overseer(at(EARLY, food=0), herd=[PIG])
        ov.provision()
        self.assertEqual(marked(g), [16])

    def test_the_feast_still_takes_the_last(self):
        ov, g = overseer(at(FEAST_DAYS, food=0), herd=[PIG])
        ov.provision()
        self.assertEqual(marked(g), [16])


if __name__ == "__main__":
    unittest.main()
