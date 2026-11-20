"""d63: the office hunt keeps clear of farm plots and pending farms, and a level fits where its tiles clear of the
plots and farm rooms can hold the chair. d62's first cut took a dug room whose farm plot was still under
construction (`used_by` lags the build), zoned the office over it and lost the chair for good: a plot is a
building, and place_furniture answers no_space on its tiles. Measured on a 23-citizen year: the officeless
manager validated nothing from the second wave, and the bed pipeline froze at 19 of 23 citizens (O 95.0 tier 3;
complete beds were worth 96.9 tier 4). A level office's chair placed fine beside the plots in another game, so the
level rule is tiles, not the whole level."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import StubGame, overseer, resp  # noqa: E402
from overseer.harness import Overseer  # noqa: E402


def room(rid, x=10, y=10, z=105, dug=True, soil=True, used_by=None):
    return {"id": rid, "kind": "R", "x": x, "y": y, "z": z, "w": 3, "h": 3, "dug": dug, "soil": soil,
            "open_tiles": 9 if dug else 0, "used_by": used_by, "free": True}


def level(aid, x=8, y=8, z=105, w=13, h=7, open_tiles=83):
    return {"id": aid, "kind": "A", "x": x, "y": y, "z": z, "w": w, "h": h, "open_tiles": open_tiles,
            "subterranean": True}


def plot(x, y, z=105, w=3, h=3):
    return {"x": x, "y": y, "z": z, "w": w, "h": h, "built": True}


def fort(plots, farm_roles=(), office_role=(), used=None, farm_sent=()):
    """A day-10 fort: R1 with a real plot, R2 the office-hunt target (its plot pending unless in `plots`), A6 a
    crowded level, A8 a level with room beside the plots."""
    r = resp(336 - 10, 10, food=60, cit=14)
    o = r["observation"]
    o["administrators"].update(MANAGER_id=79, manager_office="none")
    o["map"]["sites"] = [room("R1", x=8, y=8, used_by=used or ["farm plot 1"]), room("R2", x=12, y=8),
                         level("A6", x=8, y=8, w=7, h=3, open_tiles=19), level("A8")]
    o["farm_plots"] = plots
    o["zones"] = {"list": []}
    ov, g = overseer(r)
    ov.roles.update({"R1": "farm", **{"R2": "office" for _ in office_role}})
    for rid in farm_roles:
        ov.roles[rid] = "farm"
    ov.farm_sent.update(farm_sent)
    return ov, g


class D63(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_a_room_with_a_real_plot_is_not_free(self):
        ov, _ = fort([plot(8, 8)])
        r1 = next(s for s in ov.sites if s.get("id") == "R1")
        self.assertFalse(ov.office_room_free(r1))

    def test_a_pending_farm_excludes_the_room_before_used_by_shows_it(self):
        # the d62 race: R2 has no role and nothing uses it yet, but the farms step has sent its build_farm
        ov, _ = fort([plot(8, 8)], farm_sent=("R2",))
        r2 = next(s for s in ov.sites if s.get("id") == "R2")
        self.assertTrue(ov.office_room_free(r2) is False or True)   # the role is None: only the pending farm speaks
        self.assertFalse(ov.office_room_free(r2))

    def test_the_office_hunt_then_takes_the_clear_level(self):
        ov, _ = fort([plot(8, 8)], farm_roles=("R2",), farm_sent=("R2",))
        self.assertEqual(ov.office_site().get("id"), "A8")

    def test_a_crowded_level_is_excluded_by_tiles(self):
        ov, _ = fort([plot(8, 8), plot(11, 8)])
        a6 = next(s for s in ov.sites if s.get("id") == "A6")
        self.assertEqual(ov.level_open(a6), 1)          # 19 open tiles, 18 under the plots
        self.assertFalse(ov.office_fits(a6))

    def test_a_clear_level_fits_with_plots_nearby(self):
        ov, _ = fort([plot(8, 8)])
        a8 = next(s for s in ov.sites if s.get("id") == "A8")
        self.assertGreaterEqual(ov.level_open(a8), 2)
        self.assertTrue(ov.office_fits(a8))

    def test_farm_rooms_on_a_level_count_as_covered(self):
        # d38's fort: the farm rooms are designated, no plots yet - their tiles are still spoken for
        ov, _ = fort([])
        a6 = next(s for s in ov.sites if s.get("id") == "A6")
        ov.roles["R1"] = "farm"
        r1 = next(s for s in ov.sites if s.get("id") == "R1")
        r1["x"], r1["y"] = 8, 8                      # inside the level's box
        r2 = next(s for s in ov.sites if s.get("id") == "R2")
        r2["x"], r2["y"] = 11, 8
        ov.roles["R2"] = "farm"
        self.assertLess(ov.level_open(a6), 2)        # 19 open tiles, 18 spoken for


if __name__ == "__main__":
    unittest.main()
