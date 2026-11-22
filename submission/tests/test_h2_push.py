"""h2: the wood-tool orders pause while a released lockdown waits for its workshop.

The orders keep every dwarf with carpentry at a Carpenters. In a local game with the path index rebuilt during a
lockdown, six of seven dwarves were above ground for fifteen days after the release, five of them making tools in
every look, and none of the three workshops ordered to join the fort was built. Main already pauses these orders
while housing or hatch covers need its carpenters; this is the same pause."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402

HATCH = {"id": 14, "kind": "hatch", "built": True, "locked": False, "x": 92, "y": 100, "z": 153}
SHOPS = ("Carpenters", "Carpenters", "Carpenters", "Still", "Kitchen")


def fort(day, orders=()):
    """A sealed full-year fort inside the tool orders' window, housed, with wood."""
    r = resp(336 - day, day, food=40, drink=100, cit=7, workshops=SHOPS, orders=orders)
    o = r["observation"]
    o["stocks"].update(logs_usable=60, beds=10, tables=5, chairs=6)
    o["wealth"] = {"created": 2000}
    o["map"]["sites"] = [{"id": "E1", "kind": "E", "x": 92, "y": 100, "z": 153}]
    o["doors"] = {"list": [dict(HATCH)]}
    return r


class Push(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def started(self):
        ov, g = overseer(fort(20))
        ov.progression_push()
        self.assertEqual(len(g.tools("add_manager_order")), 3)
        self.assertEqual(len(ov.wealth_ids), 3)
        return ov, g

    def standing(self, ov, day):
        return fort(day, orders=[{"id": i, "job": "MakeTool", "repeat": "daily"} for i in sorted(ov.wealth_ids)])

    def test_the_orders_stop_while_a_release_is_watched(self):
        ov, g = self.started()
        ids = sorted(ov.wealth_ids)
        ov.load(self.standing(ov, 30))
        ov.freed = {"at": ov.now, "n": 1}                      # a lockdown was released and nothing is built yet
        ov.progression_push()
        self.assertEqual([a["order_id"] for a in g.tools("cancel_order")], ids)
        ov.load(fort(32))                                      # the orders are gone from the list, the watch goes on
        ov.freed = {"at": ov.now, "n": 1}
        ov.progression_push()
        self.assertEqual(len(g.tools("add_manager_order")), 3)                 # and none is added meanwhile

    def test_the_orders_come_back_when_the_workshop_stands(self):
        ov, g = self.started()
        ov.load(self.standing(ov, 30))
        ov.freed = {"at": ov.now, "n": 1}
        ov.progression_push()
        ov.load(fort(32))                                      # the cancelled orders are gone from the list
        ov.freed = None                                        # the watch ended: a workshop was seen built
        ov.progression_push()
        self.assertEqual(len(g.tools("add_manager_order")), 6)

    def test_nothing_changes_without_a_release(self):
        ov, g = self.started()
        ov.load(self.standing(ov, 30))
        ov.progression_push()
        self.assertEqual(g.tools("cancel_order"), [])
        self.assertEqual(len(g.tools("add_manager_order")), 3)


if __name__ == "__main__":
    unittest.main()
