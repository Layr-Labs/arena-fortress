"""d54: the review's fixes (review-sol-d53). The troop station stays this layer's until its clear is accepted, and a
squad freed from it attacks a hostile on the same pass; a second identical suspension report still marks the items
waiting then; zone totals used when the furniture list is cut short no longer count known stuck items."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from dfbench_client import ActionLimit  # noqa: E402
from support import threat_resp  # noqa: E402
from test_d42 import row  # noqa: E402
from test_d49 import SQUAD, WAGON, fort as troop_fort, monkey  # noqa: E402
from test_d50 import REPORT, dining_fort, placed, report  # noqa: E402
from overseer import harness as H  # noqa: E402

POST = {"order": "station", "x": 100, "y": 102, "z": 150}
STAND, ATTACK = {"order": "stand_down"}, {"order": "attack"}


def invader(day, orders):
    """An invader ten tiles from the wagon, the squad showing `orders`."""
    r = threat_resp(day, 10, invader=True, cit=16)
    r["observation"]["map"]["wagon"] = dict(WAGON)
    r["observation"]["military"] = {"squads": [dict(SQUAD, orders=list(orders))]}
    return r


class D54(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def posted(self):
        ov, g = troop_fort([monkey("GRAY_LANGUR", 30)])
        ov.defend()
        self.assertEqual(g.tools("squad_order"), [POST])
        g.calls.clear()
        return ov, g

    def test_a_freed_squad_attacks_on_the_same_pass(self):
        ov, g = self.posted()
        ov.load(invader(61, [POST]))
        ov.count = 0
        ov.defend()
        self.assertEqual((g.tools("squad_order"), ov.troop_post), ([STAND, ATTACK], None))

    def test_a_clear_cut_short_stays_this_layers_and_is_sent_again(self):
        ov, g = self.posted()
        original = g.act

        def spent(tool, args):
            if tool == "squad_order":
                raise ActionLimit("scripted: the day's actions are spent")
            return original(tool, args)
        g.act = spent
        ov.load(invader(61, [POST]))
        ov.count = 0
        with self.assertRaises(ActionLimit):
            ov.defend()
        self.assertIsNotNone(ov.troop_post)
        g.act = original
        ov.load(invader(62, [POST]))
        ov.count = 0
        ov.defend()
        self.assertEqual((g.tools("squad_order"), ov.troop_post), ([STAND, ATTACK], None))

    def test_a_refused_clear_lets_the_attack_replace_the_station(self):
        ov, g = self.posted()
        original = g.act

        def refuse(tool, args):
            if tool == "squad_order" and args.get("order") == "stand_down":
                g.calls.append((tool, dict(args)))
                return {"ok": False, "error_code": "internal_error", "error": "scripted"}
            return original(tool, args)
        g.act = refuse
        ov.load(invader(61, [POST]))
        ov.count = 0
        ov.defend()
        self.assertEqual((g.tools("squad_order"), ov.troop_post), ([STAND, ATTACK], None))

    def test_a_lockdown_takes_the_station_back_once(self):
        ov, g = self.posted()
        ov.lock = {"phase": "hold", "why": "wildlife"}
        r = threat_resp(61, None, cit=16)
        r["observation"]["map"]["wagon"] = dict(WAGON)
        r["observation"]["military"] = {"squads": [dict(SQUAD, orders=[POST])]}
        ov.load(r)
        ov.count = 0
        ov.troop_guard(dict(SQUAD, orders=[POST]), [POST], 0, True)
        self.assertEqual((g.tools("squad_order"), ov.troop_post), ([STAND], None))

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
