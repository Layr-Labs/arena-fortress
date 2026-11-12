"""d35: the endgame brew and barrel orders from autumn on a full-year open task (drink keeps; food rots)."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402


class D35(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def brews(self, days_left, day):
        ov, g = overseer(resp(days_left, day, food=60, cit=20))
        ov.closer()
        return [a for a in g.tools("add_order") if a.get("recipe") == "brew_drink"]

    def test_autumn_brew_order_on_a_full_year(self):
        b = self.brews(140, 196)
        self.assertEqual(len(b), 1)
        self.assertIn({"stock": "drink", "below": 600}, b[0]["when"])
        self.assertIn({"stock": "plants_brewable", "at_least": 20}, b[0]["when"])

    def test_nothing_before_the_autumn(self):
        self.assertEqual(self.brews(200, 136), [])

    def test_short_task_waits_for_the_endgame(self):
        ov, g = overseer(resp(140, 76, food=60, cit=20))
        ov.days = 216
        ov.closer()
        self.assertEqual([a for a in g.tools("add_order") if a.get("recipe") == "brew_drink"], [])


if __name__ == "__main__":
    unittest.main()
