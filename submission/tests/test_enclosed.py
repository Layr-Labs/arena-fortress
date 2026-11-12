"""cx enclosed: a box whose own level runs out onto an outdoor walkable tile (map light "o") is no Shelter; the people
pickers take level-closed A sites first and fall back to the rest, and the Shelter keeps a level-open box only when no
other candidate exists. Shapes after LT08-2 838106a z104: R1 (88,104) 9x7 walled in except its own stair, R2 (94,93)
opening on the ramps at (97,92). No game or network."""
import copy
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness  # noqa: E402

R1 = {"id": "R1", "kind": "R", "x": 88, "y": 104, "z": 104, "w": 3, "h": 3, "designated": True, "dug": True}
R2 = {"id": "R2", "kind": "R", "x": 94, "y": 93, "z": 104, "w": 3, "h": 3, "designated": True, "dug": True}
A5 = {"id": "A5", "kind": "A", "x": 60, "y": 60, "z": 103, "w": 5, "h": 5, "open_tiles": 25}   # closed level
A6 = {"id": "A6", "kind": "A", "x": 30, "y": 30, "z": 102, "w": 5, "h": 5, "open_tiles": 25}   # opens at its edge


def tile(x, y, z):
    if z == 104:
        if 88 <= x <= 96 and 104 <= y <= 110:
            return ".", "u"                          # R1 dug, walled all round
        if 94 <= x <= 102 and 93 <= y <= 99:
            return ".", "u"                          # R2 dug
        if 97 <= x <= 102 and y == 92:
            return "^", "o"                          # the open ramps above R2
        return "#", "u"
    if z == 103:
        return (".", "u") if 60 <= x <= 64 and 60 <= y <= 64 else ("#", "u")
    if z == 102:
        if 30 <= x <= 34 and 30 <= y <= 34:
            return ".", "u"
        if x == 35 and y == 32:
            return ".", "o"                          # one open tile beside A6
        return "#", "u"
    return "#", "u"


class Game:
    def __init__(self, sites):
        self.sites, self.calls = [copy.deepcopy(s) for s in sites], []

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {"tiles_added": 9}}

    def query(self, name, **kw):
        if name != "map":
            return {"result": {"units": []}}
        x, y, z, r = kw["x"], kw["y"], kw["z"], kw["radius"]
        rows = [[tile(xx, yy, z) for xx in range(x - r, x + r + 1)] for yy in range(y - r, y + r + 1)]
        return {"result": {"ok": True, "x1": x - r, "y1": y - r, "buildings": [],
                           "levels": [{"z": z, "shape": ["".join(c[0] for c in rw) for rw in rows],
                                       "light": ["".join(c[1] for c in rw) for rw in rows]}]}}

    def observe(self):
        return {"tick": 850000, "day": 16, "hands_off_in_days": 23, "days_left": 44,
                "observation": {"date": {"abs_tick": 850000}, "administrators": {"citizens": 48},
                                "map": {"sites": copy.deepcopy(self.sites), "surface_z": 105}, "zones": [],
                                "furniture": [], "burrows": {"list": []}, "stocks": {}}}


class Enclosed(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def agent(self, sites):
        game = Game(sites)
        ov = harness.Overseer(game, goal="migrant surge", days=60)
        ov.count = 0
        ov.load(game.observe())
        return ov, game

    def test_level_reach(self):
        ov, _ = self.agent([R1, R2, A5, A6])
        self.assertEqual(ov.level_open((88, 104, 104, 9, 7)), 0)
        self.assertEqual(ov.level_open((94, 93, 104, 3, 3)), 1)
        self.assertEqual(ov.level_open((60, 60, 103, 5, 5)), 0)
        self.assertEqual(ov.level_open((30, 30, 102, 5, 5)), 1)

    def test_shelter_takes_the_closed_room_and_skips_the_open_one(self):
        ov, game = self.agent([R1, R2])
        ov.room_box.update(R1={"x": 88, "y": 104, "z": 104, "w": 9, "h": 7},
                           R2={"x": 94, "y": 93, "z": 104, "w": 9, "h": 7})
        ov.shelter_grow()
        self.assertEqual([c[1]["site"] for c in game.calls if c[0] == "create_burrow"], ["R1"])
        self.assertIn(("level", "R2"), ov.shelter_skip)

    def test_only_level_open_candidates_keep_the_first_as_before(self):
        ov, game = self.agent([R2])
        ov.shelter_grow()
        self.assertEqual([c[1]["site"] for c in game.calls if c[0] == "create_burrow"], ["R2"])

    def test_a_level_open_shelter_takes_its_own_level_s_other_rooms_while_short(self):
        # cx audit (HEAD replay std LT08-2 on 642f253: Shelter R1 only, 63 tiles for 37 citizens): R2 is the fallback
        # (level-open); R3 on the same level is no new way in, so it goes in while the Shelter is short
        R3 = dict(R2, id="R3", x=98, y=94)
        ov, game = self.agent([R2])
        ov.shelter_grow()
        self.assertEqual([c[1]["site"] for c in game.calls if c[0] == "create_burrow"], ["R2"])
        game.sites = [copy.deepcopy(R2), copy.deepcopy(R3)]
        ov.load(game.observe())
        ov.shelter_grow()
        self.assertEqual([c[1]["site"] for c in game.calls if c[0] == "create_burrow"], ["R2", "R3"])

    def test_a_level_open_room_stays_out_of_a_closed_shelter_and_of_a_full_one(self):
        ov, game = self.agent([R1, R2])
        ov.room_box.update(R1={"x": 88, "y": 104, "z": 104, "w": 9, "h": 7})
        ov.shelter_grow()
        ov.shelter_grow()
        self.assertEqual([c[1]["site"] for c in game.calls if c[0] == "create_burrow"], ["R1"])   # closed R1 only
        R3 = dict(R2, id="R3", x=98, y=94)
        ov2, game2 = self.agent([R2])
        ov2.cit = 1   # 3 tiles a citizen: R2's 9 tiles are enough
        ov2.shelter_grow()
        game2.sites = [copy.deepcopy(R2), copy.deepcopy(R3)]
        ov2.load(game2.observe())
        ov2.cit = 1
        ov2.shelter_grow()
        self.assertEqual([c[1]["site"] for c in game2.calls if c[0] == "create_burrow"], ["R2"])

    def test_people_pickers_take_closed_a_sites_first_then_the_rest(self):
        ov, _ = self.agent([A6, A5])
        self.assertEqual([s["id"] for s in ov.closed_a()], ["A5", "A6"])
        ov2, _ = self.agent([A6])
        self.assertEqual([s["id"] for s in ov2.closed_a()], ["A6"])   # never nothing


if __name__ == "__main__":
    unittest.main()
