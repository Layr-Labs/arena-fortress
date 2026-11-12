"""cx office box: the manager's office carved out of a site wider than make_zone's gate.

Measured shape: hint hard LT08-2 on c44c96b — A1 (15x40) was the only A/R site, office() found no room, the manager's
office stood "none" through day 21 and no work order validated until day 30 (29 beds ordered on day 0, beds 19 until
day 30, placed 47 / citizens 48 at H). No game or network is used."""
import copy
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

WIDE = {"id": "A1", "kind": "A", "x": 83, "y": 67, "z": 104, "w": 15, "h": 40, "open_tiles": 26}


class FakeGame:
    def __init__(self, chairs=12, chair_ok=True, zone_ok=True, sites=None, chair_at=(84, 68, 104)):
        self.chairs, self.chair_ok, self.zone_ok, self.chair_at = chairs, chair_ok, zone_ok, list(chair_at)
        self.sites = [WIDE.copy()] if sites is None else sites
        self.calls, self.zones = [], []

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool == "place_furniture":
            if not self.chair_ok:
                return {"ok": False, "error_code": "no_space"}
            self.chairs -= 1
            return {"ok": True, "result": {"placed": "chair", "n": 1, "at": list(self.chair_at)}}
        if tool == "make_zone":
            if not self.zone_ok:
                return {"ok": False, "error_code": "no_space"}
            if "site" not in args:   # the server's schema check (probe fdprb LT08-2 on fe1831a)
                return {"ok": False, "error_code": "bad_arguments", "error": "args.site is required"}
            if args["site"] != "A1":
                self.zones.append({"id": 35, "type": "Office"})   # cx: the same pass assigns it (smalloffice2)
                return {"ok": True, "result": {"zone_id": 35}}
            if args.get("w", 15) > 20 or args.get("h", 40) > 20:
                return {"ok": False, "error_code": "bad_arguments", "error": "w must be an integer in [1,20]"}
            self.zones.append({"id": 34, "type": "Office", "x": 83, "y": 67, "z": 104, "w": args["w"],
                               "h": args["h"], "furniture": {"chair": 1}})
            return {"ok": True, "result": {"zone_id": 34, "at": [83, 67, 104, args["w"], args["h"]]}}
        if tool == "assign_zone":
            self.zones[0]["owner"] = args["dwarf_id"]
            return {"ok": True, "result": {"zone_id": 34, "owner": args["dwarf_id"]}}
        return {"ok": True, "result": {}}

    def observe(self, day=0):
        return {"tick": 828100 + day * harness.DAY, "observation": {
            "administrators": {"citizens": 39, "manager_active_for_orders": True, "MANAGER_id": 92,
                               "manager_office": {"zone_id": 34, "chair": True}
                               if self.zones and self.zones[0].get("owner") == 92 else "none"},
            "stocks": {"furniture_free": {"chair": self.chairs}},
            "map": {"sites": copy.deepcopy(self.sites)}, "zones": copy.deepcopy(self.zones), "furniture": []}}


class OfficeBox(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def agent(self, **kw):
        game = FakeGame(**kw)
        agent = harness.Overseer(game)
        agent.load(game.observe())
        agent.count = 0
        return agent, game

    def test_wide_site_gets_a_chair_then_a_one_tile_office_then_the_manager(self):
        agent, game = self.agent()
        agent.office()
        self.assertEqual(game.calls, [
            ("place_furniture", {"kind": "chair", "site": "A1", "w": 15, "h": 20}),
            ("make_zone", {"kind": "office", "site": "A1", "w": 2, "h": 2})])
        agent.load(game.observe(day=1))
        agent.office()
        self.assertEqual(game.calls[-1], ("assign_zone", {"zone_id": 34, "dwarf_id": 92}))
        self.assertEqual(game.chairs, 11)   # one chair, never a second
        n = len(game.calls)
        agent.load(game.observe(day=2))
        agent.office()
        self.assertEqual(len(game.calls), n)

    def test_failed_zone_retries_on_the_same_chair_tile(self):
        agent, game = self.agent(zone_ok=False)
        agent.office()
        game.zone_ok = True
        agent.load(game.observe(day=3))
        agent.office()
        self.assertEqual([c[0] for c in game.calls], ["place_furniture", "make_zone", "make_zone"])
        self.assertEqual(game.calls[-1][1], {"kind": "office", "site": "A1", "w": 2, "h": 2})

    def test_chair_at_the_site_corner_gives_a_one_tile_office(self):
        # probe fdprb LT08-2: the tool put the chair on A1's own corner (83,67,104)
        agent, game = self.agent(chair_at=(83, 67, 104))
        agent.office()
        self.assertEqual(game.calls[-1], ("make_zone", {"kind": "office", "site": "A1", "w": 1, "h": 1}))

    def test_a_chair_outside_the_zone_gate_makes_no_zone(self):
        agent, game = self.agent(chair_at=(88, 104, 104))
        agent.office()
        self.assertEqual([c[0] for c in game.calls], ["place_furniture"])

    def test_no_free_chair_does_nothing(self):
        agent, game = self.agent(chairs=0)
        agent.office()
        self.assertEqual(game.calls, [])

    def test_a_fitting_site_keeps_the_old_path(self):
        small = {"id": "A2", "kind": "A", "x": 126, "y": 127, "z": 103, "w": 3, "h": 3, "open_tiles": 9}
        agent, game = self.agent(sites=[WIDE.copy(), small])
        agent.office()
        self.assertEqual(game.calls[0], ("make_zone", {"kind": "office", "site": "A2"}))
        self.assertFalse([c for c in game.calls if c[1].get("site") == "A1"])

    def test_small_fort_waits(self):
        agent, game = self.agent()
        agent.adm["citizens"] = 7
        agent.cit = 7
        agent.office()
        self.assertEqual(game.calls, [])


if __name__ == "__main__":
    unittest.main()
