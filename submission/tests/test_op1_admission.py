"""OP1 late arrivals may use an existing lockdown's locally clear hatch.

No new lockdown trigger: the alert, local clearance and bounded admission lifecycle still apply.
"""
import copy
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import unittest

from support import DAY, HATCH, Lockdown, hold, locked, overseer, threat_resp


class OP1Admission(Lockdown, unittest.TestCase):
    def setUp(self):
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def frame(self, day=190, wagon_dist=78, hatch_dist=75, **kw):
        r = threat_resp(day, wagon_dist, n=1, alert=True, inside=9,
                        at=(HATCH["x"] + hatch_dist, HATCH["y"], HATCH["z"]),
                        doors=locked(HATCH["id"]), **kw)
        for p in r["observation"]["dwarves"]:
            p.update(x=93, y=100, z=153 if p["id"] == 3 else 151)
        return r

    def held(self, r, days=336, **state):
        ov, game = overseer(r)
        ov.days = days
        ov.lock = hold(186, due=187 * DAY, **state)
        ov.own_locks = {HATCH["id"]}
        ov.defend()
        return ov, game

    def test_task_days_gate_preserves_shorter_tasks(self):
        for days, opens in ((None, False), (216, False), (335, False), (336, True), (672, True)):
            with self.subTest(days=days):
                ov, game = self.held(self.frame(), days)
                self.assertEqual(game.tools("lock_door"),
                                 [{"door_id": HATCH["id"], "locked": False}] if opens else [])
                self.assertEqual(ov.lock["phase"], "hold")
                self.assertEqual(game.tools("civilian_alert"), [])

    def test_both_wagon_and_hatch_clearance_are_strict(self):
        for wagon, hatch, opens in ((60, 75, False), (61, 75, True), (78, 60, False), (78, 61, True)):
            with self.subTest(wagon=wagon, hatch=hatch):
                ov, game = self.held(self.frame(wagon_dist=wagon, hatch_dist=hatch))
                self.assertEqual(bool(game.tools("lock_door")), opens)
                self.assertEqual(ov.lock["open"], {HATCH["id"]} if opens else set())

    def test_unplaced_or_unlisted_hostiles_and_incomplete_look_still_block_admission(self):
        for failure in ("unplaced", "unlisted", "look"):
            with self.subTest(failure=failure):
                r = self.frame()
                th = r["observation"]["threats"]
                if failure == "unplaced":
                    del th["hostiles"][0]["x"]
                if failure == "unlisted":
                    th["visible_hostiles"] = 2
                ov, game = overseer(r)
                ov.lock = hold(186, due=187 * DAY)
                if failure == "look":
                    game.query_error = True
                ov.defend()
                self.assertEqual(game.tools("lock_door"), [])  # hatch already locked; never open it
                self.assertEqual(ov.lock["open"], set())

    def test_admission_relocks_on_approach_and_when_citizen_is_below(self):
        for below in (False, True):
            with self.subTest(below=below):
                ov, game = self.held(self.frame())
                r = self.frame(day=191, hatch_dist=75 if below else 60)
                r["observation"]["doors"]["list"][0]["locked"] = False
                if below:
                    r["observation"]["dwarves"][3]["z"] = 151
                self.again(ov, game, r)
                self.assertEqual(game.tools("lock_door")[-1], {"door_id": HATCH["id"], "locked": True})
                self.assertEqual(game.tools("civilian_alert"), [])

    def test_recorded_victims_get_an_admission_window_before_their_attacks(self):
        fixtures = json.loads((Path(__file__).parent / "fixtures/op1_admission.json").read_text())
        for case in fixtures:
            with self.subTest(record=case["record"], day=case["response"]["day"]):
                r = copy.deepcopy(case["response"])
                ov, game = overseer(r)
                game.others = case["others"]
                ov.lock = hold(0, since=case["since_tick"], due=case["since_tick"] + DAY)
                ov.defend()
                self.assertEqual(ov.lock["open"], {13})
                self.assertEqual(game.tools("civilian_alert"), [])
                self.assertTrue(set(case["victims"]) <= {p[0] for p in ov.lock["outside"]})


if __name__ == "__main__":
    unittest.main()
