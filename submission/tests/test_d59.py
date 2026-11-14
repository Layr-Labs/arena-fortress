"""d59, open tasks: a W site a workshop was placed on is not offered to another type in the same pass (the
observation is a pass old: OP1's Still and Kitchen were refused on the Carpenters' site and stood on days 4-5 and 7-8);
the end bed order counts beds stuck after a suspension report as missing. The labs keep both old behaviours."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import StubGame, resp  # noqa: E402
from overseer import harness as H  # noqa: E402
from overseer.harness import Overseer  # noqa: E402

SITES = [{"id": "W%d" % i, "kind": "W", "x": 80 + 4 * i, "y": 90, "z": 150, "w": 3, "h": 3, "free": True}
         for i in (1, 2, 3)]


def fort(lab=False, workshops=(), **kw):
    r = resp(330, 1, food=60, workshops=workshops, **kw)
    r["observation"]["map"]["sites"] = [dict(s) for s in SITES]
    g = StubGame(herd=[])
    ov = Overseer(g, goal="Run the fortress", days=336)
    ov.set_task({"goal": "Run the fortress.", **({"hands_off": {"from_day": 30, "days": 10}} if lab else {})})
    ov.load(r)
    ov.count = 0
    return ov, g


def builds(g):
    return [(a["type"], a["site"]) for a in g.tools("build_workshop")]


class D59(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_the_core_workshops_take_three_sites_in_one_pass(self):
        ov, g = fort()
        ov.workshops()
        self.assertEqual(builds(g)[:3], [("Carpenters", "W1"), ("Still", "W2"), ("Kitchen", "W3")])

    def test_a_lab_task_keeps_the_old_order(self):
        ov, g = fort(lab=True)
        ov.workshops()
        self.assertEqual(builds(g)[:3], [("Carpenters", "W1"), ("Still", "W1"), ("Kitchen", "W1")])

    def test_a_refused_build_does_not_reserve_its_site(self):
        ov, g = fort()
        original = g.act

        def refuse_first(tool, args):
            if tool == "build_workshop" and args.get("type") == "Carpenters":
                g.calls.append((tool, dict(args)))
                return {"ok": False, "error_code": "needs_materials", "error": "scripted"}
            return original(tool, args)
        g.act = refuse_first
        ov.workshops()
        self.assertEqual(builds(g)[:2], [("Carpenters", "W1"), ("Still", "W1")])

    def _beds(self, lab):
        ov, g = fort(lab=lab, workshops=("Carpenters", "Still", "Kitchen"))
        ov.o["furniture"] = [{"id": 200 + i, "kind": "bed", "x": 60 + i, "y": 61, "z": 150, "built": i < 7,
                              "zone_ids": []} for i in range(10)]
        ov.o["furniture_total"] = 10
        ov.load({"observation": ov.o, "day": 300, "days_left": 36})
        ov.count = 0
        for i in range(7, 10):
            ov.furn_suspects[200 + i] = ov.now - (H.FURN_STUCK_DAYS + 1) * H.DAY      # reported, still unbuilt
        ov.housing_check()
        return [a for a in g.tools("add_order") if a.get("recipe") == "make_bed"]

    def test_stuck_beds_are_ordered_again_at_the_end(self):
        self.assertEqual(self._beds(lab=False), [{"recipe": "make_bed", "amount": 5}])   # 3 short + 2

    def test_a_lab_task_counts_the_placed_beds(self):
        self.assertEqual(self._beds(lab=True), [])


if __name__ == "__main__":
    unittest.main()
