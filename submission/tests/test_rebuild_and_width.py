"""Regressions for the suspended-workshop rebuild (ROOT_CAUSES §E) and the zone/place width gates (§I).
No game or network is used."""
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

WIDE_ZONE = "w must be an integer in [1,20]"   # facts/game.py _t_make_zone, T.opt_int
WIDE_PLACE = "w must be an integer in [1,40]"  # facts/game.py _t_place_furniture, T.as_int


class FakeGame:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = dict(fail or {})   # (tool, site) -> error text

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if (tool, args.get("site")) in self.fail:
            return {"ok": False, "error_code": "bad_arguments", "error": self.fail[(tool, args.get("site"))]}
        if tool == "place_furniture":
            return {"ok": True, "result": {"n": 1, "at": [11, 11, 9]}}
        return {"ok": True, "result": {"id": len(self.calls)}}


def site(id="A1", x=10, y=10, z=9, w=7, h=6, open_tiles=32, **kw):
    return {"id": id, "kind": id[0], "x": x, "y": y, "z": z, "w": w, "h": h, "open_tiles": open_tiles, **kw}


def shop(sid, type, built=False, suspended=False, x=None, y=None, z=9):
    jd = [{"job": "ConstructBuilding", "suspended": True}] if suspended else [{"job": "ConstructBuilding"}]
    return {"id": sid, "type": type, "built": built, "x": x, "y": y, "z": z,
            "jobs": ["ConstructBuilding"], "job_details": [] if built else jd}


def facts(day=0, sites=(), workshops=(), zones=(), furniture=(), stocks=None, admins=None):
    return {"tick": day * harness.DAY, "observation": {
        "administrators": dict(admins or {"citizens": 7}), "dwarves": [],
        "map": {"sites": copy.deepcopy(list(sites))}, "zones": copy.deepcopy(list(zones)),
        "furniture": copy.deepcopy(list(furniture)), "orders": [],
        "workshops": copy.deepcopy(list(workshops)),
        "stocks": dict(stocks or {"logs_usable": 10})}}


class RebuildAndWidth(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, fail=None):
        game = FakeGame(fail)
        ov = harness.Overseer(game)
        ov.count = 0
        return ov, game

    def builds(self, game):
        return [a for t, a in game.calls if t == "build_workshop"]

    # ---- ROOT_CAUSES §E: the suspended construction is rebuilt on the next W site

    def test_suspended_shop_rebuilds_on_the_next_w_site_after_two_observed_days(self):
        sites = [site("W1", x=10, y=10, z=9, w=3, h=3), site("W2", x=30, y=10, z=9, w=3, h=3)]
        shops = [shop("S1", "Still", suspended=True, x=11, y=10),
                 shop("S2", "Carpenters", built=True), shop("S3", "Kitchen", built=True)]
        ov, game = self.overseer()
        for day in (5, 7):
            ov.load(facts(day=day, sites=sites, workshops=shops))
        ov.workshops()
        self.assertEqual(self.builds(game), [{"type": "Still", "site": "W2"}])   # W1 holds the stuck frame

    def test_rebuild_is_paced_to_once_per_ten_days_per_type(self):
        sites = [site("W1", x=10, y=10, z=9, w=3, h=3), site("W2", x=30, y=10, z=9, w=3, h=3)]
        shops = [shop("S1", "Still", suspended=True, x=11, y=10),
                 shop("S2", "Carpenters", built=True), shop("S3", "Kitchen", built=True)]
        ov, game = self.overseer()
        for day in (5, 7):
            ov.load(facts(day=day, sites=sites, workshops=shops))
        ov.workshops()
        ov.workshops()                                   # same pass: the act gate blocks a repeat
        self.assertEqual(len(self.builds(game)), 1)
        ov.load(facts(day=12, sites=sites, workshops=shops))
        ov.workshops()                                   # five days later: still inside the gap
        self.assertEqual(len(self.builds(game)), 1)
        ov.load(facts(day=17, sites=sites, workshops=shops))
        ov.workshops()                                   # ten days after the attempt: it may try again
        self.assertEqual(len(self.builds(game)), 2)

    def test_progressing_and_built_shops_are_never_rebuilt(self):
        sites = [site("W1"), site("W2")]
        shops = [shop("S1", "Still", suspended=False),                   # under construction, no suspension
                 shop("S2", "Carpenters", built=True), shop("S3", "Kitchen", built=True)]
        ov, game = self.overseer()
        for day in (5, 7):
            ov.load(facts(day=day, sites=sites, workshops=shops))
        ov.workshops()
        self.assertEqual(self.builds(game), [])

    def test_one_observed_day_of_suspension_is_not_enough(self):
        ov, game = self.overseer()
        ov.load(facts(day=5, sites=[site("W1"), site("W2")],
                      workshops=[shop("S1", "Still", suspended=True, x=11, y=10)]))
        ov.workshops()
        self.assertEqual(self.builds(game), [])

    def test_recovery_clears_the_stuck_mark(self):
        sites = [site("W1"), site("W2")]
        core = [shop("S2", "Carpenters", built=True), shop("S3", "Kitchen", built=True)]
        ov, game = self.overseer()
        ov.load(facts(day=5, sites=sites, workshops=[shop("S1", "Still", suspended=True)] + core))
        ov.load(facts(day=7, sites=sites, workshops=[shop("S1", "Still", built=True)] + core))
        self.assertEqual(ov.shop_stuck, {})
        ov.workshops()   # Still is built again: no rebuild, and no core shop is missing either
        self.assertEqual(self.builds(game), [])

    # ---- ROOT_CAUSES §I-1: zone site selection stays inside make_zone's own [1,20]

    def test_wide_area_site_yields_to_the_dug_room_for_zones_and_beds(self):
        sites = [site("A1", w=30, h=25), site("R1", kind="R", w=9, h=7, dug=True, designated=True)]
        ov, game = self.overseer()
        ov.load(facts(sites=sites, stocks={"logs_usable": 10, "furniture_free": {"bed": 1}}))
        ov.roles["R1"] = "dorm"
        ov.furnish()
        self.assertEqual([(t, a.get("site")) for t, a in game.calls],
                         [("place_furniture", "R1"), ("make_zone", "R1")])

    def test_room_for_keeps_the_uncapped_choice_without_a_cap(self):
        sites = [site("A1", w=30, h=25), site("R1", kind="R", w=9, h=7, dug=True, designated=True)]
        ov, _ = self.overseer()
        ov.load(facts(sites=sites))
        ov.roles["R1"] = "dorm"
        self.assertEqual(ov.room_for("dorm")["id"], "A1")
        self.assertEqual(ov.room_for("dorm", harness.ZONE_MAX)["id"], "R1")

    def test_rezone_picks_an_area_inside_the_zone_cap(self):
        sites = [site("A9", w=25, h=25), site("A2", w=7, h=6)]
        furniture = [{"kind": "table", "x": 11, "y": 11, "z": 9, "built": True},
                     {"kind": "chair", "x": 11, "y": 12, "z": 9, "built": True}]
        ov, game = self.overseer()
        ov.load(facts(sites=sites, furniture=furniture))
        ov.rezone()
        self.assertEqual({a["site"] for t, a in game.calls if t == "make_zone"}, {"A2"})

    # ---- ROOT_CAUSES §I-2: furniture placement stays inside place_furniture's own [1,40]

    def test_wide_area_site_yields_for_the_office_chair(self):
        sites = [site("A1", w=50, h=8), site("R1", kind="R", w=3, h=3, dug=True, designated=True)]
        zones = [{"id": "Z1", "type": "office", "x": 10, "y": 10, "z": 9, "w": 3, "h": 3, "owner": 5,
                  "furniture": {}}]
        admins = {"citizens": 14, "manager_active_for_orders": True, "MANAGER_id": 5, "manager_office": {}}
        ov, game = self.overseer()
        ov.load(facts(sites=sites, zones=zones, admins=admins,
                      stocks={"furniture_free": {"chair": 1}}))
        ov.roles["R1"] = "office"
        ov.office()
        self.assertEqual([(t, a.get("site")) for t, a in game.calls if t == "place_furniture"],
                         [("place_furniture", "R1")])
        self.assertTrue(all(a.get("site") != "A1" for _, a in game.calls))

    def test_place_furniture_width_error_bans_the_site(self):
        ov, game = self.overseer(fail={("place_furniture", "A7"): WIDE_PLACE})
        ov.load(facts(sites=[site("A7", w=41, h=6)]))
        r = ov.act("p", "place_furniture", {"kind": "bed", "site": "A7", "count": 1})
        self.assertFalse(r.get("ok"))
        self.assertIn("A7", ov.place_banned)
        self.assertFalse(ov.area_fits(site("A7", w=41, h=6), harness.PLACE_MAX))
        self.assertTrue(ov.area_fits(site("A7", w=41, h=6), None))

    # ---- ROOT_CAUSES §I-3: a width error is recorded and the site avoided afterwards

    def test_zone_width_error_records_the_site_and_moves_off_it(self):
        sites = [site("A1", w=20, h=20), site("R1", kind="R", w=9, h=7, dug=True, designated=True)]
        ov, game = self.overseer(fail={("make_zone", "A1"): WIDE_ZONE})
        ov.load(facts(day=1, sites=sites, stocks={"furniture_free": {"bed": 1}}))
        ov.roles["R1"] = "dorm"
        ov.furnish()
        self.assertEqual(ov.zone_banned, {"A1"})
        self.assertEqual(sum(1 for t, a in game.calls if t == "make_zone" and a.get("site") == "A1"), 1)
        game.calls.clear()
        ov.load(facts(day=5, sites=sites, stocks={"furniture_free": {"bed": 1}}))
        ov.furnish()
        self.assertEqual([(t, a.get("site")) for t, a in game.calls if t == "make_zone"],
                         [("make_zone", "R1")])


if __name__ == "__main__":
    unittest.main()
