"""d66: the d63 feast reserve (a food-zero hunger cull leaves the FEAST_MIN largest animals for the feast) holds only
while more than RESERVE_LEFT days are left. Forced famines with one animal left on MY1 1000-p (plan t63): taken 24
days out the meat rotted before the horizon (O 73.4, kept 89.3); taken 20 days out it lasted (O 93.3), while keeping
it left the food at 0 for 7 days until the feast (O 82.8)."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402
from overseer.openplay import FEAST_DAYS, FINAL_STRETCH, HUNGER_BIG, RESERVE_LEFT  # noqa: E402


def animal(i, race):
    return {"id": i, "race": race, "tame": True, "adult": True, "pet_owner_id": -1}


DOG, PIG = animal(14, "DOG"), animal(16, "PIG")         # sizes 3 and 10


def marked(g):
    return [a["unit_id"] for a in g.tools("slaughter")]


def at(left, food, cit=10):
    return resp(left, 336 - left, food=food, cit=cit)


class D66(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def cull(self, left, food, herd, cit=10):
        ov, g = overseer(at(left, food=food, cit=cit), herd=herd)
        ov.provision()
        return marked(g)

    def test_the_cut(self):
        self.assertEqual(RESERVE_LEFT, FEAST_DAYS + 5)
        self.assertTrue(FEAST_DAYS < RESERVE_LEFT < FINAL_STRETCH)

    def test_above_the_cut_the_last_animal_waits(self):
        self.assertEqual(self.cull(RESERVE_LEFT + 1, 0, [PIG]), [])

    def test_at_the_cut_the_last_animal_goes(self):
        self.assertEqual(self.cull(RESERVE_LEFT, 0, [PIG]), [16])

    def test_between_the_cut_and_the_feast_it_goes(self):
        self.assertEqual(self.cull(FEAST_DAYS + 2, 0, [PIG]), [16])

    def test_with_some_food_left_it_still_waits(self):
        self.assertEqual(self.cull(RESERVE_LEFT, 2, [PIG]), [])        # only a food-zero cull takes the last one

    def test_a_big_fort_at_zero_food_takes_both_at_the_cut(self):
        self.assertEqual(self.cull(RESERVE_LEFT, 0, [DOG, PIG], cit=HUNGER_BIG), [14, 16])


if __name__ == "__main__":
    unittest.main()
