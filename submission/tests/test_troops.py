"""Troop thieves, wolves and cougars in the wildlife look (overseer/beasts.py)."""
import unittest

import support  # noqa: F401  (puts the package on the path)
from overseer.beasts import THIEF_SCALE, in_sight
from overseer.openplay import PREDATORS

WAGON = {"x": 100, "y": 100, "z": 150}


def langur(i, x):
    return {"id": i, "race": "GRAY_LANGUR", "hostile": False, "x": x, "y": 100, "z": 150}


class Troops(unittest.TestCase):
    def test_a_troop_counts_at_twice_its_distance(self):
        found, sure = in_sight([langur(1, 129), langur(2, 140)], 2, WAGON)
        self.assertTrue(sure)
        self.assertEqual(sorted(b["dist"] for b in found), [29 * THIEF_SCALE, 40 * THIEF_SCALE])

    def test_a_lone_thief_counts_for_nothing(self):
        found, sure = in_sight([langur(1, 115)], 1, WAGON)
        self.assertEqual(found, [])
        self.assertTrue(sure)

    def test_a_hostile_or_visiting_thief_is_not_a_troop_member(self):
        rows = [langur(1, 115), {**langur(2, 116), "hostile": True}, {**langur(3, 117), "visitor": True}]
        self.assertEqual(in_sight(rows, 3, WAGON)[0], [])

    def test_wolves_and_cougars_count_at_their_distance(self):
        rows = [{"id": 1, "race": "WOLF", "hostile": False, "x": 160, "y": 100, "z": 150},
                {"id": 2, "race": "COUGAR", "hostile": False, "x": 100, "y": 130, "z": 149}]
        self.assertEqual(sorted(b["dist"] for b in in_sight(rows, 2, WAGON)[0]), [33, 60])

    def test_snapping_turtle_is_a_lurker_that_holds_the_felling(self):
        rows = [{"id": 1, "race": "ALLIGATOR SNAPPING TURTLE", "hostile": False, "x": 110, "y": 100, "z": 150}]
        self.assertEqual([b["dist"] for b in in_sight(rows, 1, WAGON)[0]], [50])
        self.assertIn("ALLIGATOR SNAPPING TURTLE", PREDATORS)

    def test_thieves_do_not_hold_the_first_felling(self):
        self.assertNotIn("GRAY_LANGUR", PREDATORS)
        self.assertIn("WOLF", PREDATORS)
        self.assertIn("ALLIGATOR", PREDATORS)


if __name__ == "__main__":
    unittest.main()
