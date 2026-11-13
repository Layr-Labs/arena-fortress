"""d38: the manager's office never goes on a farm level, and a site the game refuses the chair on is given up."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import resp  # noqa: E402
from test_d33 import ZoneGame, with_game  # noqa: E402
from overseer import harness as H  # noqa: E402

FARM_LEVEL = {"id": "A6", "kind": "A", "x": 93, "y": 97, "z": 160, "w": 7, "h": 3, "open_tiles": 19,
              "subterranean": True}
FARM_ROOMS = [{"id": "R1", "kind": "R", "x": 93, "y": 97, "z": 160, "w": 3, "h": 3, "dug": True},
              {"id": "R2", "kind": "R", "x": 97, "y": 97, "z": 160, "w": 3, "h": 3, "dug": True}]
OFFICE_ROOM = {"id": "R7", "kind": "R", "x": 97, "y": 97, "z": 157, "w": 3, "h": 3, "dug": True}


class RefuseChairGame(ZoneGame):
    """The game answers no_space to a chair on the listed sites (every tile built on), as on a farm level."""

    def __init__(self, full=(), **kw):
        super().__init__(**kw)
        self.full = set(full)

    def act(self, tool, args):
        if tool == "place_furniture" and args.get("site") in self.full:
            self.calls.append((tool, dict(args)))
            return {"ok": False, "error_code": "no_space", "error": "no free floor tile"}
        return super().act(tool, args)


def fort(sites, zones=(), chairs=1, day=2):
    r = resp(336 - day, day, food=60, cit=7)
    o = r["observation"]
    o["administrators"].update(MANAGER_id=5, manager_office="none")
    o["map"].update(surface_z=161, sites=[dict(s) for s in sites])
    o["zones"] = [dict(z) for z in zones]
    o["stocks"]["furniture_free"] = {"chair": chairs}
    return r


def office_zone(zid, site, owner=5):
    return {"id": zid, "type": "Office", "x": site["x"], "y": site["y"], "z": site["z"], "w": site["w"],
            "h": site["h"], "owner": owner, "furniture": {}}


class D38(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_farm_level_is_never_an_office_even_before_its_plots(self):
        g = ZoneGame()
        ov = with_game(fort([FARM_LEVEL] + FARM_ROOMS), g)
        ov.roles.update(R1="farm", R2="farm")        # roles are given when the digging is designated
        ov.office()
        self.assertNotIn("make_zone", [t for t, _ in g.calls])

    def test_office_goes_to_the_office_room_once_dug(self):
        g = ZoneGame()
        ov = with_game(fort([FARM_LEVEL] + FARM_ROOMS + [OFFICE_ROOM]), g)
        ov.roles.update(R1="farm", R2="farm", R7="office")
        ov.office()
        self.assertEqual(g.calls[0], ("make_zone", {"kind": "office", "site": "R7"}))
        self.assertIn(("place_furniture", {"kind": "chair", "site": "R7"}), g.calls)

    def test_refused_chair_retires_the_site_and_a_new_office_follows(self):
        g = RefuseChairGame(full={"A6"})
        r = fort([FARM_LEVEL, OFFICE_ROOM], zones=[office_zone(2, FARM_LEVEL)])   # d36's office over a farm level
        ov = with_game(r, g)
        ov.office()
        self.assertEqual(g.calls, [("place_furniture", {"kind": "chair", "site": "A6"})])
        self.assertIn("A6", ov.office_bad)
        ov.now += H.DAY
        ov.office()
        self.assertEqual(g.calls[1], ("make_zone", {"kind": "office", "site": "R7"}))
        self.assertEqual(g.calls[2][0], "assign_zone")
        self.assertEqual(g.calls[3], ("place_furniture", {"kind": "chair", "site": "R7"}))

    def test_missing_chair_is_not_a_bad_site(self):
        g = ZoneGame(refuse=[("place_furniture", None)])        # game_refused: not a site problem
        r = fort([OFFICE_ROOM], zones=[office_zone(2, OFFICE_ROOM)])
        ov = with_game(r, g)
        ov.office()
        self.assertEqual(ov.office_bad, set())

    def test_office_with_a_chair_is_left_alone(self):
        z = dict(office_zone(2, OFFICE_ROOM), furniture={"chair": 1})
        g = ZoneGame()
        ov = with_game(fort([OFFICE_ROOM], zones=[z]), g)
        ov.office()
        self.assertEqual(g.calls, [])


if __name__ == "__main__":
    unittest.main()
