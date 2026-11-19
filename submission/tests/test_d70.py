"""d70: one more Carpenters on an open task while the beds lag a late wave. Measured: a 21-citizen OP1 year at
O 90.3 with housing 0.87 (growth 0.613) - one shop made the beds, chairs, tables, barrels and hatch covers, and the
second wave's beds did not come before the horizon. The surge path already builds up to three for the migrant task;
this is one extra for the open tasks, once a game, from 15 citizens, while beds are short by five or more."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import overseer, resp  # noqa: E402
from overseer.harness import EXTRA_CARP_BEDS  # noqa: E402

SITES = [{"id": "W1", "kind": "W"}, {"id": "W2", "kind": "W"}, {"id": "W3", "kind": "W"}, {"id": "W4", "kind": "W"}]


def fort(cit=21, beds=14, workshops=("Carpenters", "Still", "Kitchen"), logs=30):
    r = resp(336 - 120, 216, food=60, cit=cit)
    o = r["observation"]
    o["map"]["sites"] = [dict(s) for s in SITES]
    o["workshops"] = [{"type": w, "id": i + 1, "built": True} for i, w in enumerate(workshops)]
    o["stocks"]["logs_usable"] = logs
    o["furniture"] = [{"kind": "bed", "built": True} for _ in range(beds)]
    return r


def carps(g):
    return [a for a in g.tools("build_workshop") if a.get("type") == "Carpenters"]


class D70(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_five_beds_short_builds_a_second_shop(self):
        ov, g = overseer(fort())
        ov.workshops()
        self.assertEqual(len(carps(g)), 1)
        self.assertTrue(ov.extra_carp)

    def test_four_beds_short_does_not(self):
        ov, g = overseer(fort(beds=EXTRA_CARP_BEDS and 17))
        ov.workshops()
        self.assertEqual(carps(g), [])

    def test_a_small_fort_does_not(self):
        ov, g = overseer(fort(cit=12, beds=2))
        ov.workshops()
        self.assertEqual(carps(g), [])

    def test_only_once(self):
        ov, g = overseer(fort())
        ov.workshops()
        ov.extra_carp = True                       # the accepted build's record
        ov.workshops()
        self.assertEqual(len(carps(g)), 1)

    def test_a_lab_is_untouched(self):
        r = fort()
        r["hands_off_in_days"] = 10
        ov, g = overseer(r)
        ov.workshops()
        self.assertEqual(carps(g), [])


if __name__ == "__main__":
    unittest.main()
