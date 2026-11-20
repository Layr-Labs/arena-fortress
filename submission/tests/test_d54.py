"""d54: the review's fixes (review-sol-d53) to the stuck-furniture rule: a second identical suspension report still
marks the items waiting then; zone totals used when the furniture list is cut short no longer count known stuck
items."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from test_d42 import row  # noqa: E402
from test_d50 import REPORT, dining_fort, placed, report  # noqa: E402
from overseer import harness as H  # noqa: E402

class D54(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_a_second_identical_suspension_report_marks_the_new_item(self):
        ov, g = dining_fort()
        report(ov)
        ov.o["furniture"].append(row(99, "table", 93, 93, 108, [12], built=False))
        ov.o["furniture_total"] += 1
        ov.o["recent_events"] = [REPORT, REPORT]
        ov.o["date"]["abs_tick"] += 2 * H.DAY
        ov.load({"observation": ov.o, "day": 32, "days_left": 184})
        self.assertEqual((ov.furn_suspects[34], ov.furn_suspects[99]), (30 * H.DAY, 32 * H.DAY))
        ov.now += 12 * H.DAY
        ov.furnish()
        self.assertIn(("table", 1), placed(g))

    def test_an_unchanged_report_still_marks_nothing_new(self):
        ov, _ = dining_fort()
        report(ov)
        since = dict(ov.furn_suspects)
        ov.o["furniture"].append(row(99, "table", 93, 93, 108, [12], built=False))
        ov.o["date"]["abs_tick"] += 2 * H.DAY
        ov.load({"observation": ov.o, "day": 32, "days_left": 184})
        self.assertEqual(ov.furn_suspects, since)

    def test_capped_zone_totals_leave_out_known_stuck_items(self):
        ov, g = dining_fort()
        ov.o["furniture"].extend(row(1000 + i, "cage", 0, 0, 108) for i in range(282))
        ov.o["furniture_total"] = 301
        ov.zones[0].update(furniture={"table": 8, "chair": 7}, furniture_planned={"table": 1, "chair": 2})
        self.assertEqual(ov.dining_kinds(), {"table": 9, "chair": 9})      # before the report: all count
        report(ov)
        ov.zones[0].update(furniture={"table": 8, "chair": 7}, furniture_planned={"table": 1, "chair": 2})
        ov.now += H.FURN_STUCK_DAYS * H.DAY
        self.assertEqual(ov.dining_kinds(), {"table": 8, "chair": 7})
        self.assertEqual(ov.dining_kinds(built_only=True), {"table": 8, "chair": 7})
        ov.furnish()
        self.assertEqual(placed(g), [("table", 1), ("chair", 2)])


if __name__ == "__main__":
    unittest.main()
