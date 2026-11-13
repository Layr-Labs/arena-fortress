"""Offline regressions for the rock-crafts half of the full-year growth push: next to i34-9's daily wood-crafts order,
a second daily MakeCrafts order of any stone (material INORGANIC) that runs only while boulders are in stock. Each
order is tracked by its own id set, so one standing does not hide the other's absence. Stub game; no DF, no model.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from overseer.harness import PROG_BOULDERS, PROG_LOGS
from support import overseer, resp

SHOPS = ("Carpenters", "Still", "Kitchen", "Craftsdwarfs")


def crafts(g):
    return [a for a in g.tools("add_manager_order") if a.get("job") == "MakeCrafts"]


class RockCrafts(unittest.TestCase):
    def test_both_orders_with_their_own_stock_conditions(self):
        ov, g = overseer(resp(290, 46, food=80, workshops=SHOPS))
        ov.progression_push()
        wood, stone = crafts(g)
        self.assertEqual((wood["material_category"], wood["when"]), (["wood"], [{"item_type": "WOOD",
                                                                                   "at_least": PROG_LOGS}]))
        self.assertEqual((stone["material"], stone["repeat"], stone["when"]),
                         ("INORGANIC", "daily", [{"item_type": "BOULDER", "at_least": PROG_BOULDERS}]))
        self.assertEqual((len(ov.craft_ids), len(ov.stone_ids)), (1, 1))

    def test_a_standing_wood_order_does_not_hide_a_missing_rock_order(self):
        ov, g = overseer(resp(290, 46, food=80, workshops=SHOPS))
        ov.progression_push()
        wood_id, = ov.craft_ids
        r = resp(289, 47, food=80, workshops=SHOPS, orders=[{"id": wood_id, "job": "MakeCrafts", "repeat": "daily"}])
        ov.load(r)
        ov.last = {}
        ov.progression_push()
        again = crafts(g)[2:]
        self.assertEqual([a.get("material") for a in again], ["INORGANIC"])

    def test_not_before_the_push_day_nor_on_short_games(self):
        ov, g = overseer(resp(310, 26, food=80, workshops=SHOPS))
        ov.progression_push()
        self.assertEqual(crafts(g), [])
        ov, g = overseer(resp(40, 46, food=80, workshops=SHOPS))
        ov.days = 60
        ov.progression_push()
        self.assertEqual(crafts(g), [])


if __name__ == "__main__":
    unittest.main()
