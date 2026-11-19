"""d60: from FINAL_STRETCH days out until the feast, a hunger cull may take the smallest of the animals kept for the
feast once nothing else is left and the food is at FINAL_FLOOR (or a fifth of the citizens) or less: one a pass, and
never the last FEAST_MIN. Before d60 a kept animal went only at 0 food. The pass reads the food every two days, and in
9 of the 10 games of d50-d59 whose food coverage fell short the food stood at 0 for one to seven scored days before
the feast while one to three animals were kept."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402
from overseer.openplay import FEAST_BATCH, FEAST_DAYS, FEAST_MIN, FINAL_FLOOR, FINAL_STRETCH  # noqa: E402


def animal(i, race, adult=True):
    return {"id": i, "race": race, "tame": True, "adult": adult, "pet_owner_id": -1}


KEPT = [animal(14, "DOG"), animal(15, "BIRD_TURKEY"), animal(16, "PIG")]     # the three a hunger cull keeps
LEFT = 25                                                                    # days left: in the stretch, before the feast


def marked(g):
    return [a["unit_id"] for a in g.tools("slaughter")]


class D60(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_the_window_is_the_stretch_before_the_feast(self):
        self.assertTrue(FEAST_DAYS < LEFT <= FINAL_STRETCH)
        self.assertEqual((FINAL_FLOOR, FEAST_MIN), (3, 1))

    def test_one_food_in_the_stretch_takes_the_smallest_kept_animal(self):
        ov, g = overseer(resp(LEFT, 216 - LEFT - 1, food=1, cit=15), herd=KEPT)
        ov.provision()
        self.assertEqual(marked(g), [15])          # the turkey; one only although a fort this size culls two a pass

    def test_food_above_the_floor_keeps_them(self):
        ov, g = overseer(resp(LEFT, 216 - LEFT - 1, food=FINAL_FLOOR + 1, cit=11), herd=KEPT)
        ov.provision()
        self.assertEqual(marked(g), [])

    def test_the_floor_grows_with_the_fort(self):
        ov, g = overseer(resp(LEFT, 216 - LEFT - 1, food=5, cit=25), herd=KEPT)       # a fifth of 25
        ov.provision()
        self.assertEqual(marked(g), [15])
        ov, g = overseer(resp(LEFT, 216 - LEFT - 1, food=6, cit=25), herd=KEPT)
        ov.provision()
        self.assertEqual(marked(g), [])

    def test_the_last_animal_is_left_for_the_feast(self):
        ov, g = overseer(resp(LEFT, 216 - LEFT - 1, food=1, cit=15), herd=[animal(16, "PIG")])
        ov.provision()
        self.assertEqual(marked(g), [])

    def test_before_the_stretch_nothing_changes(self):
        ov, g = overseer(resp(FINAL_STRETCH + 1, 216 - FINAL_STRETCH - 2, food=1, cit=15), herd=KEPT)
        ov.provision()
        self.assertEqual(marked(g), [])

    def test_no_food_still_takes_one_as_before(self):
        ov, g = overseer(resp(FINAL_STRETCH + 10, 160, food=0, cit=15), herd=KEPT)
        ov.provision()
        self.assertEqual(marked(g), [15])

    def test_spare_animals_still_go_first(self):
        herd = KEPT + [animal(10, "YAK")]                     # a grazer: never kept while non-grazers fill the three
        ov, g = overseer(resp(LEFT, 216 - LEFT - 1, food=1, cit=11), herd=herd)
        ov.provision()
        self.assertEqual(marked(g), [10])

    def test_the_feast_is_unchanged(self):
        ov, g = overseer(resp(FEAST_DAYS, 216 - FEAST_DAYS - 1, food=1, cit=15), herd=KEPT)
        ov.provision()
        self.assertEqual(marked(g), [16, 14, 15][:FEAST_BATCH])   # largest first: pig, dog, turkey


if __name__ == "__main__":
    unittest.main()
