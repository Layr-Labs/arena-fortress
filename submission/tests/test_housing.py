"""Offline regressions for installed-bed accounting on the housing gate.

The scorer reads **installed** beds (`outcome.lua` counts bed buildings whose
build stage is complete), not beds that merely sit on a tile waiting for a dwarf
to install them. The controller used to count every bed furniture row, so six
uninstalled beds on a ten-dwarf fort could look like full housing and the
endgame order that would have closed the gap never fired. Stub game; no DF and
no model.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from support import overseer, resp  # noqa: E402


def furniture(built, unbuilt, flagged=True):
    """An open-play observation with `built` installed beds and `unbuilt` placed ones."""
    r = resp(days_left=40, day=300, food=60, cit=built + unbuilt)
    rows = [{"kind": "bed", "built": True} for _ in range(built)]
    rows += [{"kind": "bed", "built": False} for _ in range(unbuilt)]
    if not flagged:
        rows = [{"kind": "bed"} for _ in range(built + unbuilt)]
    r["observation"]["furniture"] = rows
    r["observation"]["stocks"]["beds"] = 0
    return r


def bed_orders(game):
    return [a for a in game.tools("add_order") if a.get("recipe") == "make_bed"]


class InstalledBeds(unittest.TestCase):
    def test_uninstalled_beds_do_not_satisfy_the_housing_gate(self):
        ov, g = overseer(furniture(built=4, unbuilt=6))
        self.assertEqual((ov.placed.get("bed"), ov.installed("bed")), (10, 4))
        ov.housing_check()
        beds = bed_orders(g)
        self.assertEqual(len(beds), 1, "a six-bed shortfall must be ordered")
        self.assertEqual(beds[0]["amount"], 8)

    def test_installed_beds_need_nothing(self):
        ov, g = overseer(furniture(built=10, unbuilt=0))
        ov.housing_check()
        self.assertEqual(bed_orders(g), [])

    def test_an_observation_without_the_flag_keeps_the_old_count(self):
        ov, g = overseer(furniture(built=10, unbuilt=0, flagged=False))
        self.assertEqual(ov.installed("bed"), 10)
        ov.housing_check()
        self.assertEqual(bed_orders(g), [])

    def test_the_lab_bed_goal_reads_installed_beds(self):
        ov, g = overseer(furniture(built=4, unbuilt=6))
        ov.beds_first = True
        self.assertTrue(ov.beds_unmet())
        ov.load(furniture(built=10, unbuilt=0))
        self.assertFalse(ov.beds_unmet())


def dining(*zones):
    """A lab observation with one DiningHall zone per (tables, chairs) pair, as `outcome.lua` lists them."""
    r = resp(days_left=40, day=300, food=60, cit=10, hands_off=10)
    r["observation"]["zones"] = [{"id": "Z%d" % i, "type": "DiningHall", "furniture": {"table": t, "chair": c}}
                                  for i, (t, c) in enumerate(zones)]
    return r


def dining_overseer(*zones):
    """A lab task (hands-off window): housing_check counts seats with `seats()`, not `real_seats()`."""
    ov, g = overseer(dining(*zones))
    ov.set_task({"goal": "Run the fortress.", "hands_off": 10})
    return ov, g


def seat_orders(game):
    return [a for a in game.tools("add_order") if a.get("recipe") in ("make_table", "make_chair")]


class DiningSeats(unittest.TestCase):
    def test_tables_and_chairs_in_separate_zones_are_seats(self):
        ov, _ = overseer(dining((5, 0), (0, 5)))
        self.assertEqual(ov.seats(), 5, "the score takes one min over the fort, not a min per zone")

    def test_the_minimum_is_over_the_fort_totals(self):
        ov, _ = overseer(dining((3, 1), (1, 3)))
        self.assertEqual(ov.seats(), 4)

    def test_no_seat_order_when_the_fort_has_enough(self):
        ov, g = dining_overseer((5, 0), (0, 5))   # ten dwarves need five seats
        self.assertFalse(ov.open_task())
        ov.housing_check()
        self.assertEqual(seat_orders(g), [])

    def test_a_short_fort_still_orders(self):
        ov, g = dining_overseer((2, 2))           # four seats, five needed
        ov.housing_check()
        self.assertEqual({a["recipe"] for a in seat_orders(g)}, {"make_table", "make_chair"})


if __name__ == "__main__":
    unittest.main()
