"""d58: a hunger cull takes grazers first, the oldest first, and keeps the largest non-grazers for the feast. No tool
makes a pasture, so grazers starve (every local OP1 game lost 3-9 tame animals that way, all grazers); the old order
kept the three largest animals, which are grazers, and ate the cats, dogs and birds, and two games came to the feast
with no animal left. The feast itself still takes the largest first."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402
from overseer.openplay import FEAST_BATCH, GRAZERS  # noqa: E402


def animal(i, race, adult=True):
    return {"id": i, "race": race, "tame": True, "adult": adult, "pet_owner_id": -1}


# an OP1 herd as the games show it: embark grazers (low ids), a calf born later, and the fort's non-grazers
HERD = [animal(10, "YAK"), animal(11, "WATER_BUFFALO"), animal(12, "DONKEY"), animal(13, "CAT"), animal(14, "DOG"),
        animal(15, "BIRD_TURKEY"), animal(16, "PIG"), animal(40, "REINDEER", adult=False), animal(41, "RABBIT")]


def marked(g):
    return [a["unit_id"] for a in g.tools("slaughter")]


class D58(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_the_grazer_list_is_the_raws_and_holds_the_fort_animals(self):
        self.assertEqual(len(GRAZERS), 49)
        for race in ("COW", "YAK", "WATER_BUFFALO", "HORSE", "DONKEY", "MULE", "LLAMA", "ALPACA", "SHEEP", "GOAT",
                     "REINDEER", "RABBIT", "CAVY"):
            self.assertIn(race, GRAZERS)
        for race in ("CAT", "DOG", "PIG", "BIRD_TURKEY", "BIRD_CHICKEN", "BIRD_GUINEAFOWL", "BIRD_PEAFOWL_BLUE"):
            self.assertNotIn(race, GRAZERS)

    def test_a_hunger_cull_takes_the_oldest_grazer_first(self):
        ov, g = overseer(resp(200, 136, food=1), herd=HERD)
        ov.provision()
        self.assertEqual(marked(g), [10])                  # the yak: the first grazer to arrive, the first to starve

    def test_grazers_go_in_arrival_order_before_any_non_grazer(self):
        herd = list(HERD)
        order = []
        for day in range(136, 136 + 8 * 6, 8):             # one hunger cull every HUNGER_GAP days
            ov, g = overseer(resp(336 - day, day, food=1), herd=herd)
            ov.provision()
            order += marked(g)
            herd = [a for a in herd if a["id"] not in marked(g)]
        # the grazers by arrival: yak, buffalo, donkey, the reindeer calf (four non-grazers fill the kept three)
        self.assertEqual(order[:4], [10, 11, 12, 40])
        self.assertEqual(order[4], 41)                     # the rabbit: a grazer, but next to no food, so last of them
        self.assertNotIn(14, order)                        # the dog, pig and turkey are kept for the feast
        self.assertNotIn(16, order)

    def test_the_feast_keeps_the_three_largest_non_grazers(self):
        herd = [a for a in HERD if a["race"] not in GRAZERS]          # cat, dog, turkey, pig
        ov, g = overseer(resp(200, 136, food=1), herd=herd)
        ov.provision()
        self.assertEqual(marked(g), [13])                  # the cat: pig, dog and turkey are the three kept

    def test_with_few_non_grazers_the_youngest_grazers_are_kept(self):
        herd = [animal(10, "YAK"), animal(11, "COW"), animal(30, "HORSE"), animal(31, "GOAT"), animal(13, "CAT")]
        ov, g = overseer(resp(200, 136, food=1), herd=herd)
        ov.provision()
        self.assertEqual(marked(g), [10])                  # kept: the cat, the goat (31) and the horse (30)
        ov, g = overseer(resp(200, 136, food=1), herd=[a for a in herd if a["id"] != 10])
        ov.provision()
        self.assertEqual(marked(g), [11])
        ov, g = overseer(resp(200, 136, food=1), herd=[a for a in herd if a["id"] not in (10, 11)])
        ov.provision()
        self.assertEqual(marked(g), [])                    # only the kept three are left, and there is some food

    def test_nothing_left_but_the_kept_and_no_food_takes_the_smallest_meal(self):
        herd = [animal(14, "DOG"), animal(15, "BIRD_TURKEY"), animal(16, "PIG")]
        ov, g = overseer(resp(200, 136, food=0), herd=herd)
        ov.provision()
        self.assertEqual(marked(g), [15])                  # as before d58: the smallest animal that is a meal

    def test_the_feast_still_takes_the_largest_first(self):
        ov, g = overseer(resp(15, 321, food=40, plants=40), herd=HERD)
        ov.provision()
        self.assertEqual(marked(g), [11, 10, 12][:FEAST_BATCH])   # buffalo, yak, donkey


if __name__ == "__main__":
    unittest.main()
