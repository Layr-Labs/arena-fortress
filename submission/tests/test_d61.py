"""d61: the hunger cull triggers read the food a dwarf can eat, not the score's count. `food_edible` counts the five
brewed-or-milled crops (issue #140: cave wheat, pig tail, sweet pod, dimple cup, quarry bush carry EDIBLE_COOKED),
and a dwarf never eats one raw: a fort whose counted food is all pig tail starves its hunters to stress while the
count says it is fed. real_food() takes those kinds out; the hunger triggers, the final floor and the cull's
nothing-left check read it. Lab tasks keep the old count (their predicates read the score's count)."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402
from overseer.openplay import FEAST_DAYS, FEAST_KEEP, FINAL_STRETCH, HUNGER  # noqa: E402


def animal(i, race, adult=True):
    return {"id": i, "race": race, "tame": True, "adult": adult, "pet_owner_id": -1}


KEPT = [animal(14, "DOG"), animal(15, "BIRD_TURKEY"), animal(16, "PIG")]     # the three a hunger cull keeps
GRAZERS = [animal(20, "COW"), animal(21, "YAK"), animal(22, "GOAT"), animal(23, "SHEEP")]
LEFT = 25                                                                    # days left: in the stretch, before the feast


def crops(resp_r, kinds):
    """Give the observation's stocks `plants_by_kind` (name -> {n, brewable, cookable})."""
    stocks = resp_r["observation"]["stocks"]
    stocks["plants_by_kind"] = {name: {"n": n, "brewable": True, "cookable": True} for name, n in kinds.items()}
    return resp_r


def marked(g):
    return [a["unit_id"] for a in g.tools("slaughter")]


class D61(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_real_food_takes_the_brewed_crops_out_and_keeps_everything_else(self):
        r = crops(resp(336 - 200, 200, food=100), {"pig tail": 60, "plump helmet": 30})
        ov, _ = overseer(r)
        self.assertEqual(ov.real_food(), 40)               # 100 counted less 60 nobody eats raw

    def test_a_stock_of_brewed_crops_is_not_fed(self):
        r = crops(resp(336 - 200, 200, food=60), {"pig tail": 60})
        ov, _ = overseer(r)
        self.assertEqual(ov.real_food(), 0)

    def test_an_unreadable_count_reads_as_before(self):
        r = resp(336 - 200, 200, food=60)
        del r["observation"]["stocks"]["food_edible"]
        ov, _ = overseer(r)
        self.assertEqual(ov.real_food(), 0)
        r = crops(resp(336 - 200, 200, food=60), {"pig tail": 60})
        r["observation"]["stocks"]["plants_by_kind"] = "ERR: scripted"
        ov, _ = overseer(r)
        self.assertEqual(ov.real_food(), 60)               # no plant list: the count stands

    def test_a_hunger_cull_fires_on_fake_food_in_the_stretch(self):
        r = crops(resp(LEFT, 216 - LEFT - 1, food=60, cit=15), {"cave wheat": 60})
        ov, g = overseer(r, herd=KEPT + GRAZERS)
        ov.provision()
        self.assertTrue(marked(g), "real food is gone: the grazers go")

    def test_no_hunger_cull_on_the_same_real_food(self):
        r = crops(resp(LEFT, 216 - LEFT - 1, food=60, cit=15), {"plump helmet": 60})
        ov, g = overseer(r, herd=KEPT + GRAZERS)
        ov.provision()
        self.assertFalse(marked(g), "raw-edible plants feed: nothing goes")

    def test_the_final_floor_reads_the_real_food(self):
        r = crops(resp(LEFT, 216 - LEFT - 1, food=3, cit=15), {"pig tail": 3})
        ov, _ = overseer(r, herd=KEPT)
        self.assertTrue(ov.final_floor(len(KEPT)))         # 3 counted, 0 eatable: the floor is met

    def test_the_window_is_unchanged(self):
        self.assertTrue(FEAST_DAYS < LEFT <= FINAL_STRETCH)
        self.assertEqual(HUNGER, 0.25)


if __name__ == "__main__":
    unittest.main()
