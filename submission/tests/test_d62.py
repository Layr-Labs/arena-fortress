"""d62: the office site search counts a dug room whose 'farm' role is stale - the observation shows nothing using it -
as free. The digging step marks a soil room 'farm' when it designates the dig; the farms then go to the F sites (or
the room's own build is refused) and the room stays dug and unused while the role alone excludes it. On a fort where
every level also holds a farm there is then no site at all: no office is ever made, and from about 20 citizens the
manager validates no new order, so the bed and seat orders sit pending to the horizon (a 22-citizen fort frozen at
19 beds and 10 seats from day 117 scored O 89.2 tier 3 where the beds and the Hamlet rank were worth 90.6 tier 4)."""
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import StubGame, overseer, resp  # noqa: E402
from overseer.harness import Overseer  # noqa: E402


def room(rid, dug=True, soil=True, used_by=None):
    return {"id": rid, "kind": "R", "x": 10, "y": 10, "z": 105, "w": 3, "h": 3, "dug": dug, "soil": soil,
            "open_tiles": 9 if dug else 0, "used_by": used_by, "free": True}


def level(aid, w=13, h=7, open_tiles=83):
    return {"id": aid, "kind": "A", "x": 8, "y": 8, "z": 105, "w": w, "h": h, "open_tiles": open_tiles,
            "subterranean": True}


def stale_farm_resp(cit=7, farms_on_levels=True):
    """A fort whose dug rooms all carry farm roles (two with real plots, one unused) and whose levels all hold farms."""
    r = resp(336 - 16, 16, food=60, cit=cit)
    o = r["observation"]
    o["administrators"]["MANAGER_id"] = 79
    o["map"]["sites"] = [
        room("R1", used_by=["farm plot 4"]),
        room("R2", used_by=["farm plot 6"]),
        room("R4"),                                   # dug, unused: the stale farm role
        level("A7"),
    ]
    o["farm_plots"] = ([{"site": None, "z": 105, "w": 3, "h": 3}] * 4 if farms_on_levels else [])
    o["zones"] = {"list": []}
    return r


class D62(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def ov(self, r, roles):
        g = StubGame()
        ov = Overseer(g, goal="Run the fortress for 336 days.", days=336)
        ov.set_task({"goal": "Run the fortress for 336 days."})
        ov.load(r)
        ov.count = 0
        ov.roles.update(roles)
        return ov, g

    def test_the_stale_farm_room_is_free_for_the_office(self):
        ov, _ = self.ov(stale_farm_resp(), {"R1": "farm", "R2": "farm", "R4": "farm"})
        self.assertTrue(ov.office_room_free(ov_kind(ov, "R4")))
        self.assertEqual(ov.office_site().get("id"), "R4")

    def test_no_site_without_the_fix(self):
        # the old rule: a role of any kind excluded the room; with every room farmed and every level a farm level,
        # there was no site at all
        ov, _ = self.ov(stale_farm_resp(), {"R1": "farm", "R2": "farm", "R4": "farm"})
        rooms = ov.dug_rooms("office") + [r for r in ov.dug_rooms() if ov.roles.get(r.get("id")) is None]
        self.assertEqual(rooms, [])
        self.assertTrue(all(a.get("z") in ov.farm_levels() for a in ov.kind("A")))

    def test_a_room_with_a_real_plot_stays_excluded(self):
        ov, _ = self.ov(stale_farm_resp(), {"R1": "farm", "R2": "farm", "R4": "farm"})
        self.assertFalse(ov.office_room_free(ov_kind(ov, "R1")))

    def test_used_rooms_of_other_roles_stay_excluded(self):
        ov, _ = self.ov(stale_farm_resp(), {"R1": "farm", "R2": "dorm", "R4": "farm"})
        r2 = ov_kind(ov, "R2")
        r2["used_by"] = None                      # a dorm room the game shows unused: the role still holds it
        self.assertFalse(ov.office_room_free(r2))

    def test_the_office_is_made_on_the_stale_room(self):
        ov, g = self.ov(stale_farm_resp(), {"R1": "farm", "R2": "farm", "R4": "farm"})
        ov.free["chair"] = 0
        ov.office_open()
        zoned = [a for t, a in g.calls if t == "make_zone" and a.get("kind") == "office"]
        self.assertEqual([a.get("site") for a in zoned], ["R4"])
        self.assertEqual(ov.roles.get("R4"), "office")


def ov_kind(ov, rid):
    return next(s for s in ov.kind("R") if s.get("id") == rid)


if __name__ == "__main__":
    unittest.main()
