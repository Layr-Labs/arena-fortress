"""d74: on a migrant task the layer places the beds it makes. It made max(citizens + 12, 50) and placed citizens + 2, so
a wave arriving inside the hands-off window had beds in stock and none to sleep in (newjordan's a6dcf695)."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import StubGame, resp  # noqa: E402
from overseer import harness as H  # noqa: E402

LT08 = ("Migrants are arriving. From day 39 you can't act for 21 days. By day 60 every dwarf must have a placed bed, "
        "drink and food must be in stock every day from day 39, and drink must not end lower than it was on day 39. "
        "No dwarf may die.")
LT02 = ("From day 69 you can't act for 21 days. Keep drink in stock every day of that window, with your own built "
        "Still and a planted farm plot, and keep food in stock every day of that window too. No dwarf may die.")
DORM = {"id": "R1", "kind": "R", "x": 97, "y": 93, "z": 128, "w": 9, "h": 7, "dug": True, "subterranean": True}


def lab(goal, cit, placed, free, day=30):
    r = resp(60 - day, day, food=60, cit=cit)
    r["hands_off_in_days"] = 39 - day
    o = r["observation"]
    o["map"].update(surface_z=131, sites=[dict(DORM)])
    o["furniture"] = [{"kind": "bed", "id": i, "built": True} for i in range(placed)]
    o["stocks"]["furniture_free"] = {"bed": free}
    o["zones"] = [{"id": 8, "type": "Dormitory", "x": 97, "y": 93, "z": 128, "w": 9, "h": 7}]
    g = StubGame()
    ov = H.Overseer(g, goal=goal, days=60)
    ov.set_task({"goal": goal, "hands_off": {"from_day": 39}})
    ov.load(r)
    ov.count = 0
    ov.roles["R1"] = "dorm"
    return ov, g


def beds(g):
    return [a.get("count") for a in g.tools("place_furniture") if a.get("kind") == "bed"]


class D74(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_a_migrant_task_places_its_spare_beds(self):
        ov, g = lab(LT08, cit=45, placed=47, free=10)      # the goal is 57: the ten in stock go down
        self.assertTrue(ov.surge)
        ov.furnish()
        self.assertEqual(beds(g), [10])

    def test_up_to_the_number_it_makes(self):
        ov, g = lab(LT08, cit=45, placed=55, free=10)
        ov.furnish()
        self.assertEqual(beds(g), [2])
        ov, g = lab(LT08, cit=20, placed=22, free=40)      # a small fort: SURGE_BEDS, thirty a pass
        ov.furnish()
        self.assertEqual(beds(g), [min(30, H.SURGE_BEDS - 22)])

    def test_at_the_goal_nothing_more(self):
        ov, g = lab(LT08, cit=45, placed=57, free=5)
        ov.furnish()
        self.assertEqual(beds(g), [])

    def test_another_lab_keeps_two_spare(self):
        ov, g = lab(LT02, cit=10, placed=12, free=6, day=50)
        self.assertFalse(ov.surge)
        ov.furnish()
        self.assertEqual(beds(g), [])
        ov, g = lab(LT02, cit=10, placed=9, free=6, day=50)
        ov.furnish()
        self.assertEqual(beds(g), [3])


if __name__ == "__main__":
    unittest.main()
