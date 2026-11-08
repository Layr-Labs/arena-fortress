"""Regressions for the dining room's no_space overflow: a floor that refuses seats gets that day's tables and
chairs together on another floor (seats count as min(tables, chairs) inside a dining zone, so one kind alone
seats nobody), on regular tasks as well as surge ones, while the successful path stays untouched. No game or
network is used."""
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


class FakeGame:
    def __init__(self, sites=()):
        self.sites = {s["id"]: s for s in sites}
        self.calls = []
        self.fail_sites = set()     # sites whose place_furniture comes back no_space
        self.fail_kinds = set()     # kinds refused wherever they go

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if tool == "place_furniture":
            if args["site"] in self.fail_sites or args["kind"] in self.fail_kinds:
                return {"ok": False, "error_code": "no_space",
                        "error": "could not place furniture: the game refused every free-looking tile"}
            s = self.sites.get(args["site"], {})
            return {"ok": True, "result": {"n": args.get("count", 1),
                                           "at": [s.get("x", 10) + 1, s.get("y", 10) + 1, s.get("z", 9)]}}
        return {"ok": True, "result": {"id": len(self.calls)}}


def site(id="A1", x=10, y=10, z=9, w=7, h=6, open_tiles=32, **kw):
    return {"id": id, "kind": id[0], "x": x, "y": y, "z": z,
            "w": w, "h": h, "open_tiles": open_tiles, **kw}


def facts(sites=(), cit=7, free=None, day=0):
    return {"tick": day * harness.DAY, "observation": {
        "administrators": {"citizens": cit},
        "stocks": {"furniture_free": free or {}},
        "map": {"sites": copy.deepcopy(list(sites))},
        "zones": [], "furniture": [], "workshops": []}}


class DiningOverflow(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, sites, **kw):
        game = FakeGame(sites)
        overseer = harness.Overseer(game)   # no goal: a regular task, not a migrant surge
        overseer.load(facts(sites=sites, **kw))
        overseer.count = 0
        return overseer, game

    def places(self, game, at_site=None):
        out = [(a["kind"], a["site"], a["count"]) for t, a in game.calls if t == "place_furniture"]
        return out if at_site is None else [p for p in out if p[1] == at_site]

    def test_no_space_moves_the_table_and_chair_pair_to_one_floor_and_zones_it(self):
        sites = [site("A1"), site("A2", x=20, open_tiles=12)]
        overseer, game = self.overseer(sites, free={"table": 4, "chair": 4})
        game.fail_sites.add("A1")
        overseer.furnish()
        self.assertEqual(self.places(game), [("table", "A1", 4), ("chair", "A1", 4),
                                             ("table", "A2", 4), ("chair", "A2", 4)])
        self.assertEqual([a for t, a in game.calls if t == "make_zone"], [{"kind": "dining_hall", "site": "A2"}])
        self.assertEqual({k for k in overseer.seat_block if "A2" in k}, set())   # the alt floor took the pair
        self.assertEqual({k for k in overseer.seat_block}, {("table", "A1"), ("chair", "A1")})
        self.assertEqual(overseer.overflow, set())   # the beds' record stays out of the dining divert

    def test_farm_level_stays_out_of_the_divert_even_when_it_looks_wide_open(self):
        sites = [site("A1"), site("R1", z=8, soil=True, dug=True),
                 site("Af", z=8, open_tiles=60), site("A2", z=7, open_tiles=10)]
        overseer, game = self.overseer(sites, free={"table": 2, "chair": 2})
        overseer.roles["R1"] = "farm"
        game.fail_sites.add("A1")
        overseer.furnish()
        self.assertEqual(self.places(game, "Af"), [])            # the farm level is refused however big it looks
        self.assertEqual(self.places(game, "A2"), [("table", "A2", 2), ("chair", "A2", 2)])

    def test_regular_tasks_divert_their_seats_but_still_not_their_beds(self):
        sites = [site("A1"), site("A2", x=20, open_tiles=12)]
        overseer, game = self.overseer(sites, free={"bed": 5, "table": 4, "chair": 4})
        game.fail_sites.add("A1")
        overseer.furnish()
        self.assertIs(overseer.surge, False)
        self.assertEqual(self.places(game, "A1"), [("bed", "A1", 5), ("table", "A1", 4), ("chair", "A1", 4)])
        self.assertEqual([p[0] for p in self.places(game, "A2")], ["table", "chair"])   # no bed on the alt floor
        self.assertEqual(overseer.overflow, set())   # beds keep needing a surge to divert (the dorm's own rule)

    def test_a_refusing_floor_is_not_knocked_again_while_it_stays_the_same(self):
        sites = [site("A1"), site("A2", x=20, open_tiles=12), site("A3", z=8, open_tiles=20)]
        overseer, game = self.overseer(sites, free={"table": 4, "chair": 4})
        game.fail_sites.add("A1")
        overseer.furnish()
        self.assertEqual(self.places(game, "A2"), [("table", "A2", 4), ("chair", "A2", 4)])
        game.calls.clear()
        overseer.load(facts(sites=sites, free={"table": 4, "chair": 4}, day=1))
        overseer.count = 0
        overseer.furnish()
        self.assertEqual(self.places(game, "A1"), [])   # the unchanged full floor is diverted around, not knocked
        self.assertEqual({k for k in overseer.seat_block}, {("table", "A1"), ("chair", "A1")})

    def test_a_floor_that_gains_space_is_asked_again(self):
        overseer, game = self.overseer([site("A1")], free={"table": 4, "chair": 4})
        game.fail_sites.add("A1")
        overseer.furnish()
        game.calls.clear()
        overseer.load(facts(sites=[site("A1", open_tiles=60)], free={"table": 4, "chair": 4}, day=1))
        overseer.count = 0
        overseer.furnish()
        self.assertEqual(len(self.places(game, "A1")), 2)   # the floor changed: the refusal is re-tested

    def test_successful_dining_placements_take_the_normal_path(self):
        overseer, game = self.overseer([site("A1")], free={"table": 4, "chair": 4})
        overseer.furnish()
        self.assertEqual(self.places(game), [("table", "A1", 4), ("chair", "A1", 4)])
        self.assertEqual([a for t, a in game.calls if t == "make_zone"], [{"kind": "dining_hall", "site": "A1"}])
        self.assertEqual([t for t, _ in game.calls], ["place_furniture", "place_furniture", "make_zone"])
        self.assertEqual(overseer.seat_block, {})
        self.assertEqual(overseer.overflow, set())

    def test_the_divert_carries_both_kinds_even_when_only_one_was_refused(self):
        sites = [site("A1"), site("A2", x=20, open_tiles=12)]
        overseer, game = self.overseer(sites, free={"table": 4, "chair": 4})
        game.fail_kinds.add("table")   # the full floor still took the chairs: the tables must not go alone
        overseer.furnish()
        self.assertEqual(self.places(game, "A2"), [("table", "A2", 4), ("chair", "A2", 4)])
        self.assertEqual(self.places(game, "A1"), [("table", "A1", 4), ("chair", "A1", 4)])   # chairs stayed too
        self.assertEqual({a["site"] for a in (a for t, a in game.calls if t == "make_zone")},
                         {"A1", "A2"})   # each floor's furniture gets its own dining hall

    def test_the_divert_skips_a_floor_already_zoned_dormitory(self):
        # the game answers site_used to a second zone over the same site, so a dormitory-zoned floor (the beds'
        # overflow, say) would take the tables and chairs and never earn them a zone: seats would never count
        sites = [site("A1"), site("A2", x=20, open_tiles=40), site("A3", x=40, open_tiles=12)]
        dorm_zone = {"id": 5, "type": "dormitory", "x": 20, "y": 10, "z": 9, "w": 7, "h": 6}
        resp = facts(sites=sites, free={"table": 4, "chair": 4})
        resp["observation"]["zones"] = [dorm_zone]
        game = FakeGame(sites)
        overseer = harness.Overseer(game)
        overseer.load(resp)
        overseer.count = 0
        game.fail_sites.add("A1")
        overseer.furnish()
        self.assertEqual(self.places(game, "A3"), [("table", "A3", 4), ("chair", "A3", 4)])
        self.assertEqual(self.places(game, "A2"), [])   # the zoned floor is not picked even though it is the biggest
        self.assertEqual([a for t, a in game.calls if t == "make_zone"], [{"kind": "dining_hall", "site": "A3"}])


if __name__ == "__main__":
    unittest.main()
