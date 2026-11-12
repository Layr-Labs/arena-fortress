"""d48: on open tasks, farm plots up to one per two citizens (at most FARM_OPEN_MAX), the extra ones below ground."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import StubGame, resp  # noqa: E402
from overseer import harness as H  # noqa: E402
from overseer.harness import Overseer  # noqa: E402

F = [{"id": "F%d" % i, "kind": "F", "x": 10 * i, "y": 10, "z": 150, "w": 3, "h": 3} for i in range(1, 5)]
G = [{"id": "G%d" % i, "kind": "G", "x": 10 * i, "y": 40, "z": 160, "w": 3, "h": 3} for i in range(1, 3)]


def fort(cit, plots, lab=False, surface_seeds=True):
    r = resp(186, 40, food=10, drink=100, cit=cit, hands_off=(5 if lab else None))
    o = r["observation"]
    o["map"]["sites"] = [dict(s) for s in F + G]
    o["farm_plots"] = [{"id": i, "x": 0, "y": i, "z": 150, "w": 3, "h": 3, "built": True} for i in range(plots)]
    o["stocks"]["seeds_by_kind"] = {"plump helmet": {"n": 20, "underground": True}}
    if surface_seeds:
        o["stocks"]["seeds_by_kind"]["strawberry"] = {"n": 10, "underground": False}
    g = StubGame(herd=[])
    ov = Overseer(g, goal="Run the fortress", days=216)
    ov.set_task({"goal": "Run the fortress.", **({"hands_off": {"from_day": 30, "days": 10}} if lab else {})})
    ov.load(r)
    ov.count = 0
    return ov, g


class D48(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_a_big_fort_farms_the_dug_sites_but_not_more_of_the_surface(self):
        ov, g = fort(cit=19, plots=4)                  # usual target 4 is met; one plot per two dwarves wants 10
        ov.farms()
        self.assertEqual([a["site"] for a in g.tools("build_farm")], ["F1", "F2", "F3", "F4"])

    def test_below_the_usual_target_the_usual_order_holds(self):
        ov, g = fort(cit=19, plots=0)
        ov.farms()
        self.assertEqual([a["site"] for a in g.tools("build_farm")][:4], ["F1", "F2", "F3", "F4"])
        self.assertNotIn("G1", [a["site"] for a in g.tools("build_farm")])   # extra plots stay below ground

    def test_a_small_fort_keeps_four_plots(self):
        ov, g = fort(cit=7, plots=4)
        ov.farms()
        self.assertEqual(g.tools("build_farm"), [])

    def test_the_cap(self):
        ov, g = fort(cit=40, plots=H.FARM_OPEN_MAX)
        ov.farms()
        self.assertEqual(g.tools("build_farm"), [])

    def test_the_labs_keep_their_target(self):
        ov, g = fort(cit=19, plots=4, lab=True)
        ov.farms()
        self.assertEqual(g.tools("build_farm"), [])


if __name__ == "__main__":
    unittest.main()
