"""Regressions for the migrant surge's bed supply: the no_space overflow floor, the wave-sized bed target and the
second Carpentry. No game or network is used."""
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
        self.fail = set()       # sites whose place_furniture comes back no_space

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if tool == "place_furniture":
            if args["site"] in self.fail:
                return {"ok": False, "error_code": "no_space",
                        "error": "could not place a bed: the game refused all free-looking tiles"}
            s = self.sites.get(args["site"], {})
            return {"ok": True, "result": {"n": args.get("count", 1),
                                           "at": [s.get("x", 10) + 1, s.get("y", 10) + 1, s.get("z", 9)]}}
        return {"ok": True, "result": {"id": len(self.calls)}}


def site(id="A1", x=10, y=10, z=9, w=7, h=6, open_tiles=32, **kw):
    return {"id": id, "kind": id[0], "x": x, "y": y, "z": z,
            "w": w, "h": h, "open_tiles": open_tiles, **kw}


def facts(sites=(), cit=7, free=None, stocks=None, furniture=(), workshops=(), day=0):
    return {"tick": day * harness.DAY, "observation": {
        "administrators": {"citizens": cit},
        "stocks": {"furniture_free": free or {}, **(stocks or {})},
        "map": {"sites": copy.deepcopy(list(sites))},
        "zones": [], "furniture": list(furniture), "workshops": list(workshops)}}


class OverflowBeds(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, sites=(), surge=True, **kw):
        game = FakeGame(sites)
        overseer = harness.Overseer(game, goal="lt08 migrant surge" if surge else "")
        overseer.load(facts(sites=sites, **kw))
        overseer.count = 0
        return overseer, game

    def test_no_space_diverts_beds_to_another_floor_and_zones_it(self):
        sites = [site("A1"), site("A2", x=20, open_tiles=12)]
        overseer, game = self.overseer(sites, free={"bed": 5})
        game.fail.add("A1")
        overseer.furnish()
        self.assertEqual(game.calls[0][1], {"kind": "bed", "site": "A1", "count": 5})
        self.assertEqual(game.calls[1][1], {"kind": "bed", "site": "A2", "count": 5})
        self.assertEqual(game.calls[2][1], {"kind": "dormitory", "site": "A2"})
        self.assertEqual([t for t, _ in game.calls], ["place_furniture", "place_furniture", "make_zone"])
        self.assertEqual(overseer.overflow, {"A2"})
        game.calls.clear()
        overseer.load(facts(sites=sites, free={"bed": 5}, day=1))
        overseer.count = 0
        overseer.furnish()
        self.assertEqual([t for t, _ in game.calls], ["place_furniture"])   # the full floor is not tried again

    def test_cross_level_area_site_is_the_last_resort_floor(self):
        overseer, game = self.overseer([site("A1"), site("A2", z=8, open_tiles=9)], free={"bed": 2})
        game.fail.add("A1")
        overseer.furnish()
        self.assertEqual(game.calls[1][1], {"kind": "bed", "site": "A2", "count": 2})

    def test_bed_target_grows_to_the_wave_peak_on_a_migrant_task(self):
        for surge, want in ((True, 39), (False, 22)):
            with self.subTest(surge=surge):
                overseer, _ = self.overseer([], surge=surge, cit=19)
                self.assertIs(overseer.surge, surge)
                self.assertEqual(overseer.bed_target(), want)

    def test_bed_shortage_builds_the_second_carpenters_at_ten_citizens(self):
        sites = [site("W1")]
        cases = ((12, 0, True), (12, 32, False), (14, 36, False), (16, 36, True))
        for cit, beds, want in cases:
            with self.subTest(cit=cit, beds=beds):
                overseer, game = self.overseer(sites, cit=cit, stocks={"logs_usable": 5, "beds": beds},
                                               workshops=[{"type": "Carpenters"}])
                overseer.closer()
                calls = [a for t, a in game.calls if t == "build_workshop"]
                self.assertEqual(bool(calls), want)
                if calls:
                    self.assertEqual(calls[0], {"type": "Carpenters", "site": "W1"})

    def test_normal_tasks_do_not_divert_on_no_space(self):
        overseer, game = self.overseer([site("A1"), site("A2", x=20, open_tiles=12)],
                                       surge=False, free={"bed": 5})
        game.fail.add("A1")
        overseer.furnish()
        self.assertEqual([t for t, _ in game.calls], ["place_furniture"])
        self.assertEqual(game.calls[0][1]["site"], "A1")
        self.assertEqual(overseer.overflow, set())

    def test_beds_divert_skips_a_floor_already_zoned_dining(self):
        # the game answers site_used to a second zone over the same site: a dining-zoned floor (the seats' overflow)
        # would take the beds and never earn them a dormitory zone
        sites = [site("A1"), site("A2", x=20, open_tiles=40), site("A3", x=40, open_tiles=12)]
        resp = facts(sites=sites, free={"bed": 5})
        resp["observation"]["zones"] = [{"id": 5, "type": "dining_hall", "x": 20, "y": 10, "z": 9, "w": 7, "h": 6}]
        game = FakeGame(sites)
        overseer = harness.Overseer(game, goal="lt08 migrant surge")
        overseer.load(resp)
        overseer.count = 0
        game.fail.add("A1")
        overseer.furnish()
        self.assertEqual(game.calls[1][1], {"kind": "bed", "site": "A3", "count": 5})
        self.assertEqual([a for t, a in game.calls if t == "make_zone"], [{"kind": "dormitory", "site": "A3"}])
        self.assertEqual(overseer.overflow, {"A3"})


if __name__ == "__main__":
    unittest.main()
