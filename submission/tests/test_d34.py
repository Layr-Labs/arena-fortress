"""d34: the manager's office from the start on open tasks, and two hunger culls a pass for a big fort at the end."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import StubGame, overseer, resp  # noqa: E402


def small_fort(cit=10, zones=(), chairs=1):
    r = resp(200, 100, food=60, cit=cit)
    o = r["observation"]
    o["administrators"].update(MANAGER_id=5, manager_office="none")
    o["zones"] = list(zones)
    o["map"]["sites"] = [{"id": "R1", "kind": "R", "x": 20, "y": 20, "z": 149, "dug": True}]
    o["stocks"]["furniture_free"] = {"chair": chairs}
    return r


class D34(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_office_is_made_below_14_citizens_on_an_open_task(self):
        ov, g = overseer(small_fort())
        ov.roles["R1"] = "office"       # the digging step gives the third dug room this role, at any population
        ov.office()
        self.assertIn(("make_zone", {"kind": "office", "site": "R1"}), g.calls)

    def test_spare_office_is_assigned_then_gets_a_chair(self):
        spare = {"id": 9, "type": "Office", "x": 20, "y": 20, "z": 149, "w": 3, "h": 3, "owner": None, "furniture": {}}
        ov, g = overseer(small_fort(zones=[spare]))
        ov.office()
        self.assertEqual(g.calls[-1], ("assign_zone", {"zone_id": 9, "dwarf_id": 5}))
        mine = dict(spare, owner=5)
        ov2, g2 = overseer(small_fort(zones=[mine]))
        ov2.office()
        self.assertEqual(g2.calls[-1][0], "place_furniture")
        self.assertEqual(g2.calls[-1][1]["kind"], "chair")

    def test_lab_task_keeps_the_14_citizen_rule(self):
        r = small_fort()
        g = StubGame()
        from overseer.harness import Overseer
        ov = Overseer(g, goal="Run the fortress", days=60)
        ov.set_task({"goal": "Keep the fort supplied.", "hands_off": {"from_day": 39}})
        r["hands_off_in_days"] = 20
        ov.load(r)
        ov.count = 0
        ov.office()
        self.assertEqual(g.calls, [])

    def test_big_fort_culls_two_animals_in_the_final_stretch(self):
        ov, g = overseer(resp(20, 316, food=5, cit=20))
        ov.provision()
        self.assertEqual(len(g.tools("slaughter")), 2)

    def test_small_fort_culls_one(self):
        ov, g = overseer(resp(20, 316, food=5, cit=10))
        ov.provision()
        self.assertEqual(len(g.tools("slaughter")), 1)


if __name__ == "__main__":
    unittest.main()
