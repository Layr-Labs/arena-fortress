"""d50/d52: on open tasks, placed furniture that was unbuilt when DF reported a suspended construction and is still
unbuilt FURN_STUCK_DAYS later is not counted as coming (no tool resumes it), so free items are placed in its stead;
a slow backlog with no such report always counts."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from test_d42 import fort, row, beds, SMALL  # noqa: E402
from overseer import harness as H  # noqa: E402

LEVEL = {"id": "A11", "kind": "A", "x": 90, "y": 92, "z": 108, "w": 11, "h": 5, "open_tiles": 45}
ZONE = {"id": 12, "type": "DiningHall", "x": 90, "y": 92, "z": 108, "w": 11, "h": 5}


REPORT = "The dwarves suspended the construction of cherry wood Table."


def report(ov):
    """The suspension report arrives on the next observation."""
    ov.o["recent_events"] = [REPORT]
    ov.load({"observation": ov.o, "day": ov.day, "days_left": ov.days_left, "tick": ov.now})


def dining_fort(lab=False):
    furn = ([row(i, "table", 92 + i, 94, 108, [12]) for i in range(8)]
            + [row(20 + i, "chair", 92 + i, 95, 108, [12]) for i in range(7)]
            + [row(34, "table", 90, 93, 108, [12], built=False), row(35, "chair", 91, 93, 108, [12], built=False),
               row(36, "chair", 92, 93, 108, [12], built=False)])
    return fort([LEVEL], cit=15, free={"table": 1, "chair": 2}, furniture=furn, zones=[ZONE], lab=lab)


def placed(g):
    return [(a["kind"], a.get("count")) for t, a in g.calls if t == "place_furniture"]


class D50(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_items_waiting_a_few_days_still_count(self):
        ov, g = dining_fort()
        ov.furnish()
        self.assertEqual(placed(g), [])                      # 9 tables and 9 chairs counted: nothing more wanted

    def test_items_stuck_for_days_are_replaced_from_free_stock(self):
        ov, g = dining_fort()
        report(ov)
        ov.now += H.FURN_STUCK_DAYS * H.DAY
        ov.furnish()
        self.assertEqual(placed(g), [("table", 1), ("chair", 2)])

    def test_stuck_beds_are_not_counted(self):
        furn = [row(i, "bed", 80 + i % 9, 90 + i // 9, 149) for i in range(14)] + [row(50, "bed", 85, 93, 149, built=False)]
        ov, g = fort([SMALL], cit=15, free={"bed": 3}, furniture=furn)
        ov.furnish()
        self.assertEqual(beds(g), [("A3", 2)])               # 15 placed + 2 wanted - 15
        ov2, g2 = fort([SMALL], cit=15, free={"bed": 3}, furniture=furn)
        report(ov2)
        ov2.now += H.FURN_STUCK_DAYS * H.DAY
        ov2.furnish()
        self.assertEqual(beds(g2), [("A3", 3)])              # the stuck one does not count: 14 + 3 free

    def test_a_slow_backlog_with_no_report_always_counts(self):
        ov, g = dining_fort()
        ov.now += 40 * H.DAY
        ov.furnish()
        self.assertEqual(placed(g), [])

    def test_the_labs_count_as_before(self):
        ov, g = dining_fort(lab=True)
        ov.now += H.FURN_STUCK_DAYS * H.DAY
        self.assertFalse(ov.stuck({"id": 35, "built": False}))


if __name__ == "__main__":
    unittest.main()
