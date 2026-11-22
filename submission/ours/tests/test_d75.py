"""d75: a hunger cull takes the smallest animal that is still a meal and keeps the three largest for the feast, as up
to PR #154. d58's grazers-first order answered grazers starving at the meeting area below ground, which d70 removed."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402
from overseer import openplay as O  # noqa: E402
from overseer.openplay import FEAST_BATCH, FEAST_DAYS, HUNGER_BIG  # noqa: E402


def animal(i, race, **kw):
    return {"id": i, "race": race, "tame": True, "adult": True, "pet_owner_id": -1, **kw}


# an OP1 herd as the games show it: embark grazers (low ids), a calf born later, and the fort's other animals
HERD = [animal(10, "YAK"), animal(11, "WATER_BUFFALO"), animal(12, "DONKEY"), animal(13, "CAT"), animal(14, "DOG"),
        animal(15, "BIRD_TURKEY"), animal(16, "PIG"), animal(40, "REINDEER", adult=False), animal(41, "RABBIT")]


def marked(g):
    return [a["unit_id"] for a in g.tools("slaughter")]


class D75(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_there_is_no_grazer_rule(self):
        self.assertFalse(hasattr(O, "GRAZERS"))
        self.assertFalse(hasattr(O, "GRAZERS_FIRST"))

    def test_a_hunger_cull_takes_the_smallest_meal(self):
        ov, g = overseer(resp(120, 215, food=1), herd=HERD)
        ov.provision()
        self.assertEqual(marked(g), [13])                 # the cat; the rabbit is next to no food and goes last

    def test_the_order_is_by_size_and_the_three_largest_stay(self):
        order = []
        for _ in range(9):
            herd = [a for a in HERD if a["id"] not in order]
            ov, g = overseer(resp(120, 215, food=1), herd=herd)
            ov.provision()
            if not marked(g):
                break
            order += marked(g)
        # cat, turkey, dog, the reindeer calf, pig, then the rabbit; buffalo, yak and donkey are kept for the feast
        self.assertEqual(order, [13, 15, 14, 40, 16, 41])

    def test_nothing_left_but_the_kept_and_no_food_takes_the_smallest_of_them(self):
        kept = [a for a in HERD if a["id"] in (10, 11, 12)]
        ov, g = overseer(resp(120, 215, food=0), herd=kept)
        ov.provision()
        self.assertEqual(marked(g), [12])                 # the donkey

    def test_a_big_fort_at_no_food_takes_a_kept_one_with_the_last_spare(self):
        herd = [a for a in HERD if a["id"] in (10, 11, 12, 13)]
        ov, g = overseer(resp(120, 215, food=0, cit=HUNGER_BIG), herd=herd)
        ov.provision()
        self.assertEqual(marked(g), [13])                 # before the final stretch a hunger cull marks one a pass
        left = FEAST_DAYS + 10
        ov, g = overseer(resp(left, 336 - left, food=0, cit=HUNGER_BIG), herd=herd)
        ov.provision()
        self.assertEqual(marked(g), [13, 12])             # in it, two: the spare cat, then the smallest kept

    def test_the_feast_still_takes_the_largest_first(self):
        ov, g = overseer(resp(FEAST_DAYS, 336 - FEAST_DAYS - 1, food=40, plants=40), herd=HERD)
        ov.provision()
        self.assertEqual(marked(g), [11, 10, 12][:FEAST_BATCH])


if __name__ == "__main__":
    unittest.main()
