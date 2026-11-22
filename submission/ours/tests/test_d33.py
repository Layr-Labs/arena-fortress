"""d33: brewing from one plant, moving a manager's office that can't take a chair, and a stair site away from water."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import DAY, StubGame, overseer, resp  # noqa: E402
from overseer import harness as H  # noqa: E402


class ZoneGame(StubGame):
    """StubGame whose make_zone answers a zone id and whose map query lists the given water tiles."""

    def __init__(self, water=(), map_error=False, **kw):
        super().__init__(**kw)
        self.water, self.map_error = list(water), map_error

    def act(self, tool, args):
        r = super().act(tool, args)
        if tool == "make_zone":
            r["result"] = {"zone": args.get("kind"), "zone_id": 500 + len(self.calls)}
        return r

    def query(self, name, **kw):
        if name != "map":
            return super().query(name, **kw)
        if self.map_error:
            raise H.GameAPIError("scripted")
        return {"result": {"liquid": [{"x": x, "y": y, "z": kw.get("z"), "depth": 7, "magma": False}
                                      for x, y in self.water]}}


def office_fort(w=1, h=1, chair=False):
    r = resp(200, 100, food=60, cit=20)
    o = r["observation"]
    o["administrators"].update(MANAGER_id=5, manager_office={"zone_id": 9, "chair": chair})
    o["zones"] = [{"id": 9, "type": "Office", "x": 10, "y": 10, "z": 150, "w": w, "h": h, "owner": 5, "furniture": {}}]
    o["map"]["sites"] = [{"id": "R1", "kind": "R", "x": 20, "y": 20, "z": 149, "dug": True}]
    o["stocks"]["furniture_free"] = {"chair": 2}
    return r


def stair_fort():
    r = resp(336, 0, food=60)
    r["observation"]["map"].update(surface_z=150, sites=[{"id": "S1", "kind": "S", "x": 50, "y": 50, "z": 150},
                                                         {"id": "S2", "kind": "S", "x": 10, "y": 10, "z": 150}])
    return r


def with_game(r, game):
    ov, _ = overseer(r)
    ov.game = game
    return ov


class D33(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_brew_order_runs_from_one_plant(self):
        ov, g = overseer(resp(200, 100, food=60))
        ov.supply()
        brew = [a for a in g.tools("add_order") if a.get("recipe") == "brew_drink"]
        self.assertTrue(brew)
        self.assertIn({"stock": "plants_brewable", "at_least": 1}, brew[0]["when"])

    def test_office_with_a_chair_stays(self):
        g = ZoneGame()
        ov = with_game(office_fort(chair=True), g)
        ov.office()
        self.assertEqual(g.calls, [])

    def test_stair_moves_away_from_water(self):
        g = ZoneGame(water=[(12, 10), (13, 11)])
        ov = with_game(stair_fort(), g)
        self.assertEqual(ov.stair_site(ov.kind("S"))["id"], "S1")
        g.water = []                                            # decided once
        self.assertEqual(ov.stair_site(ov.kind("S"))["id"], "S1")

    def test_stair_keeps_default_without_near_water(self):
        ov = with_game(stair_fort(), ZoneGame(water=[(45, 48)]))
        self.assertEqual(ov.stair_site(ov.kind("S"))["id"], "S2")

    def test_stair_keeps_default_when_the_query_fails(self):
        ov = with_game(stair_fort(), ZoneGame(map_error=True))
        self.assertEqual(ov.stair_site(ov.kind("S"))["id"], "S2")


if __name__ == "__main__":
    unittest.main()
