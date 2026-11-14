"""d62: a hunger cull that finds nothing it may mark no longer starts its cooldown. Before d62 such a check (every
animal left was kept for the feast and the food was still above 0) started the HUNGER_GAP (8 days) or
HUNGER_GAP_FINAL (5 days) wait as if a meal had been marked, so a food-zero emergency or the d60 final floor a pass
later waited it out. yukonautominer found it in a public MY1 trace (5f9b0fa4, PR #168): nothing was marked on day 191
at food 2, the food stood at 0 on days 193 and 195, and the next mark came on day 197. In 366 full local games of ours
it held back a cull the fixed rule would make in 18, 7 of them inside the scored last 28 days."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402
from overseer.openplay import FEAST_DAYS, FINAL_FLOOR, FINAL_STRETCH, HUNGER_GAP  # noqa: E402


def animal(i, race, **kw):
    return {"id": i, "race": race, "tame": True, "adult": True, "pet_owner_id": -1, **kw}


KEPT = [animal(14, "DOG"), animal(15, "BIRD_TURKEY"), animal(16, "PIG")]     # the three a hunger cull keeps
YAK = animal(10, "YAK")                                                       # a grazer: a hunger cull's first pick
EARLY = FINAL_STRETCH + 60      # days left before the final stretch: HUNGER_GAP between culls
LATE = FEAST_DAYS + 10          # days left in the stretch, before the feast: HUNGER_GAP_FINAL and the d60 floor


def marked(g):
    return [a["unit_id"] for a in g.tools("slaughter")]


def at(left, food, cit=10):
    """The observation `336 - left` days into a 336-day game."""
    return resp(left, 336 - left, food=food, cit=cit)


def again(ov, g, r):
    """The next pass on the same controller, its cooldowns kept. Returns the animals that pass tried to mark."""
    before = len(marked(g))
    ov.load(r)
    ov.count = 0
    ov.provision()
    return marked(g)[before:]


class D62(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_an_empty_check_does_not_hold_back_the_food_zero_cull(self):
        ov, g = overseer(at(EARLY, food=2), herd=KEPT)
        ov.provision()
        self.assertEqual(marked(g), [])                                      # food above 0 and all three kept
        self.assertEqual(again(ov, g, at(EARLY - 2, food=0)), [15])          # two days later at 0: the smallest goes

    def test_an_empty_check_does_not_hold_back_the_final_floor(self):
        ov, g = overseer(at(LATE, food=FINAL_FLOOR + 3, cit=11), herd=KEPT)
        ov.provision()
        self.assertEqual(marked(g), [])                                      # above the floor: the kept animals stay
        self.assertEqual(again(ov, g, at(LATE - 2, food=FINAL_FLOOR - 1, cit=11)), [15])   # at the floor: one goes

    def test_repeated_empty_checks_keep_looking(self):
        ov, g = overseer(at(EARLY, food=2), herd=KEPT)
        ov.provision()
        self.assertEqual(again(ov, g, at(EARLY - 2, food=1)), [])           # still above 0: nothing, and no wait
        self.assertEqual(again(ov, g, at(EARLY - 4, food=0)), [15])

    def test_a_confirmed_mark_still_starts_the_cooldown(self):
        ov, g = overseer(at(EARLY, food=2), herd=KEPT + [YAK])
        ov.provision()
        self.assertEqual(marked(g), [10])                                    # the grazer
        g.herd = KEPT + [dict(YAK, marked_for_slaughter=True)]
        self.assertEqual(again(ov, g, at(EARLY - 2, food=0)), [])            # inside HUNGER_GAP of a real mark
        self.assertEqual(again(ov, g, at(EARLY - HUNGER_GAP, food=0)), [15])

    def test_a_refused_mark_does_not_start_the_cooldown(self):
        ov, g = overseer(at(EARLY, food=2), herd=KEPT + [YAK], refuse={("slaughter", 10)})
        ov.provision()
        self.assertEqual(marked(g), [10])                                    # tried and refused (unchanged by d62)
        self.assertEqual(again(ov, g, at(EARLY - 2, food=0)), [10])          # tried again on the next pass

    def test_a_failed_read_does_not_start_the_cooldown(self):
        ov, g = overseer(at(EARLY, food=0), herd=KEPT, query_error=True)
        ov.provision()
        self.assertEqual(marked(g), [])
        g.query_error = False
        self.assertEqual(again(ov, g, at(EARLY - 2, food=0)), [15])


if __name__ == "__main__":
    unittest.main()
