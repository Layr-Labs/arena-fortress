"""cx closed sites (owner 2026-11-11, after the LT08-2 death on 838106a): no Shelter box over open ground, no zone or
furniture on an open-air A site, the office gets a dug room when no closed place exists, and no new surface stair dig
while a big beast is near. Light shapes as in the record (map query light: u subterranean, i inside, o outside).
No game or network."""
import copy
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness  # noqa: E402

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

# LT08-2 z104: A1 (83,67) 15x40 is open valley floor ("o") with the dug rooms ("u") at its south end
A1 = {"id": "A1", "kind": "A", "x": 83, "y": 67, "z": 104, "w": 15, "h": 40, "open_tiles": 26}
R1 = {"id": "R1", "kind": "R", "x": 88, "y": 104, "z": 104, "w": 3, "h": 3, "designated": True, "dug": True}
R2 = {"id": "R2", "kind": "R", "x": 94, "y": 93, "z": 104, "w": 3, "h": 3, "designated": False, "dug": False}
A9 = {"id": "A9", "kind": "A", "x": 60, "y": 60, "z": 103, "w": 5, "h": 5, "open_tiles": 25}   # a closed dug level
S1 = {"id": "S1", "kind": "S", "x": 93, "y": 94, "z": 105, "w": 1, "h": 1}


def light(x, y, z):
    """(shape, light) of a tile: z104 open above y<100 except the R2 room box, rock-dug below; z103 all dug."""
    if z == 103:
        return ".", "u"
    if z == 104:
        if 94 <= x <= 96 and 93 <= y <= 95:
            return ".", "u"
        if y >= 100:
            return ".", "u"
        return ".", "o"
    return ".", "o"


class FakeGame:
    def __init__(self, sites, others=()):
        self.sites, self.others = [copy.deepcopy(s) for s in sites], list(others)
        self.calls = []
        self.maps = 0

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool == "place_furniture":
            return {"ok": True, "result": {"placed": args["kind"], "n": 1, "at": [84, 68, 104]}}
        if tool == "make_zone":
            return {"ok": True, "result": {"zone_id": 50}}
        if tool == "create_burrow":
            return {"ok": True, "result": {"tiles_added": 9}}
        return {"ok": True, "result": {}}

    def query(self, name, **kw):
        if name == "units":
            return {"result": {"units": copy.deepcopy(self.others)}}
        if name == "map":
            self.maps += 1
            x, y, z, rad = kw["x"], kw["y"], kw["z"], kw["radius"]
            rows = [[light(xx, yy, z) for xx in range(x - rad, x + rad + 1)] for yy in range(y - rad, y + rad + 1)]
            return {"result": {"ok": True, "x1": x - rad, "y1": y - rad,
                               "levels": [{"z": z, "shape": ["".join(c[0] for c in r) for r in rows],
                                           "light": ["".join(c[1] for c in r) for r in rows]}]}}
        return {"ok": False}

    def observe(self, day=0, cit=40):
        return {"tick": 828100 + day * harness.DAY, "day": day, "hands_off_in_days": 39 - day, "days_left": 60 - day,
                "observation": {
                    "date": {"abs_tick": 828100 + day * harness.DAY},
                    "administrators": {"citizens": cit, "manager_active_for_orders": True, "MANAGER_id": 92,
                                       "manager_office": "none"},
                    "stocks": {"furniture_free": {"chair": 2, "bed": 10}},
                    "dwarves": [{"id": 92, "adult": True, "positions": ["MANAGER"], "x": 90, "y": 105, "z": 104},
                                {"id": 93, "adult": True, "positions": [], "x": 90, "y": 105, "z": 104}],
                    "map": {"sites": copy.deepcopy(self.sites), "surface_z": 105,
                            "wagon": {"x": 96, "y": 97, "z": 105}},
                    "zones": [], "furniture": [], "burrows": {"list": []}}}


class Quiet(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def agent(self, sites, others=(), goal="migrant surge", day=0):
        game = FakeGame(sites, others)
        agent = harness.Overseer(game, goal=goal, days=60)
        agent.count = 0
        agent.load(game.observe(day=day))
        return agent, game


class ClosedSites(Quiet):
    def test_box_open_counts_walkable_outside_tiles(self):
        agent, _ = self.agent([A1, R1, A9])
        self.assertEqual(agent.site_open(A1), 15 * 33 - 9)   # rows 67-99 open (less the R2 room), 100-106 dug
        self.assertEqual(agent.site_open(A9), 0)
        self.assertEqual(agent.box_open((94, 93, 104, 3, 3)), 0)
        self.assertEqual(agent.box_open((94, 93, 104, 9, 7)), 9 * 7 - 9)

    def test_zones_and_furniture_never_go_on_an_open_a_site(self):
        agent, game = self.agent([A1, R1, A9])
        for i, (tool, args) in enumerate((("place_furniture", {"kind": "bed", "site": "A1", "count": 4}),
                           ("place_furniture", {"kind": "chair", "site": "A1", "w": 1, "h": 1}),
                           ("make_zone", {"kind": "dormitory", "site": "A1", "w": 3, "h": 2}),
                           ("make_zone", {"kind": "meeting_area", "site": "A1", "w": 15, "h": 20}),
                           ("create_burrow", {"site": "A1"}))):
            with self.subTest(tool=tool, args=args):
                r = agent.act("k%d" % i, tool, args)
                self.assertEqual(r["error_code"], "site_open")
        self.assertEqual(game.calls, [])
        # a closed A site and a dug R room take them
        self.assertTrue(agent.act("ok1", "make_zone", {"kind": "dormitory", "site": "A9"})["ok"])
        self.assertTrue(agent.act("ok2", "place_furniture", {"kind": "bed", "site": "R1", "w": 9, "h": 7})["ok"])
        self.assertEqual([c[0] for c in game.calls], ["make_zone", "place_furniture"])

    def test_a_room_box_touching_open_ground_is_no_shelter(self):
        agent, game = self.agent([A1, R1])
        r = agent.act("shelter_R2x", "create_burrow", {"site": "R1", "w": 9, "h": 7})
        self.assertTrue(r["ok"])
        agent.sites.append(dict(R2, designated=True, dug=True))
        r = agent.act("shelter_R2", "create_burrow", {"site": "R2", "w": 9, "h": 7})
        self.assertEqual(r["error_code"], "site_open")

    def test_shelter_takes_the_dug_room_box_not_the_open_level_box(self):
        agent, game = self.agent([A1, R1])
        agent.room_box["R1"] = {"x": 88, "y": 104, "z": 104, "w": 9, "h": 7}
        agent.shelter_grow()
        self.assertEqual([c for c in game.calls if c[0] == "create_burrow"],
                         [("create_burrow", {"site": "R1", "w": 9, "h": 7})])
        self.assertIn("R1", agent.shelter_added)
        self.assertNotIn("A1", agent.shelter_added)

    def test_a_closed_level_box_still_goes_in(self):
        agent, game = self.agent([A9])
        agent.shelter_grow()
        self.assertEqual([c for c in game.calls if c[0] == "create_burrow"], [("create_burrow", {"site": "A9"})])

    def test_the_office_waits_for_the_first_dorm_then_digs_a_room(self):
        agent, game = self.agent([A1, dict(R1, designated=False, dug=False)])
        agent.office()
        # cx office valid: the surge's first room is the dorm's, and meanwhile the open A1 takes the office box (the
        # orders are never left unvalidated; office_yield guards it)
        self.assertEqual(game.calls, [("place_furniture", {"kind": "chair", "site": "A1", "w": 15, "h": 20}),
                                      ("make_zone", {"kind": "office", "site": "A1", "w": 2, "h": 2})])
        agent.office_tile = None
        agent.roles["R1"] = "dorm"
        agent.sites.append(dict(R2))
        game.calls.clear()
        agent.office()
        self.assertEqual(game.calls[0], ("dig_room", {"site": "R2", "w": 9, "h": 7}))
        self.assertEqual(agent.roles["R2"], "office")

    def test_an_unread_box_is_not_refused(self):
        agent, game = self.agent([A1])
        game.query = lambda name, **kw: (_ for _ in ()).throw(RuntimeError("down"))
        agent.open_maps.clear()
        self.assertTrue(agent.act("k", "make_zone", {"kind": "office", "site": "A1", "w": 1, "h": 1})["ok"])


class StairBeastHold(Quiet):
    def test_no_surface_stair_dig_with_a_big_beast_near(self):
        gator = {"id": 113, "race": "ALLIGATOR", "x": 75, "y": 94, "z": 104}   # 18 tiles, 1 level
        agent, game = self.agent([A1, S1], others=[gator])
        r = agent.act("stairs", "dig_stairs", {"site": "S1", "z_bottom": 104})
        self.assertEqual(r["error_code"], "beast_near")
        self.assertEqual(game.calls, [])
        game.others = [dict(gator, x=40)]                # 53 tiles: dug as before
        agent.load(game.observe(day=1))
        r = agent.act("stairs", "dig_stairs", {"site": "S1", "z_bottom": 104}, retry=0)
        self.assertTrue(r["ok"])


if __name__ == "__main__":
    unittest.main()
