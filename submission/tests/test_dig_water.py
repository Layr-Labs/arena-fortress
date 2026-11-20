"""Digging clear of revealed water (overseer.harness WATER_RING, Overseer.dry_dig, the model loop's refusal)."""
import types
import unittest

from support import Overseer, StubGame, resp  # noqa: F401  (support puts the package on the path)
from plain.harness import Plain
from dfbench_client import GameAPIError

# The local MY1 game where three dwarves drowned: the surface is z155, a brook bed with water runs north-south at
# x104-107 on z154, and R2 (a 3x3 site at 96,91,154) was dug as a 9x7 dormitory reaching x104.
BROOK = [{"x": x, "y": y, "z": 154, "depth": 7} for x in range(104, 108) for y in range(80, 110)]


class MapGame(StubGame):
    def __init__(self, liquid=(), fail=False):
        super().__init__()
        self.liquid, self.fail, self.maps = list(liquid), fail, []

    def query(self, name, **kw):
        if name != "map":
            return super().query(name, **kw)
        self.maps.append(kw)
        if self.fail:
            raise GameAPIError("scripted")
        x, y, r = kw["x"], kw["y"], kw["radius"]
        lo, hi = min(kw["z"], kw["z2"]), max(kw["z"], kw["z2"])
        rows = [t for t in self.liquid if abs(t["x"] - x) <= r and abs(t["y"] - y) <= r and lo <= t["z"] <= hi]
        return {"result": {"ok": True, "liquid": rows, "levels": []}}


def overseer(game, sites):
    ov = Overseer(game)
    r = resp(100, 14, food=60)
    r["observation"]["map"] = {"surface_z": 155, "sites": sites}
    ov.load(r)
    ov.count = 0
    return ov


R2 = {"id": "R2", "kind": "R", "x": 96, "y": 91, "z": 154, "w": 3, "h": 3}
R9 = {"id": "R9", "kind": "R", "x": 101, "y": 91, "z": 154, "w": 3, "h": 3}   # its 3x3 ends at x103, beside the brook
R4 = {"id": "R4", "kind": "R", "x": 96, "y": 91, "z": 153, "w": 3, "h": 3}
S5 = {"id": "S5", "kind": "S", "x": 95, "y": 92, "z": 155}


class DryDig(unittest.TestCase):
    def test_dormitory_is_cut_back_from_the_brook(self):
        ov = overseer(MapGame(BROOK), [R2])
        self.assertEqual(ov.dry_dig("dig_room", {"site": "R2", "w": 9, "h": 7}), {"site": "R2", "w": 7, "h": 7})

    def test_cut_dig_is_what_the_game_is_sent(self):
        game = MapGame(BROOK)
        ov = overseer(game, [R2])
        ov.act("dig_R2", "dig_room", {"site": "R2", "w": 9, "h": 7})
        self.assertEqual(game.tools("dig_room"), [{"site": "R2", "w": 7, "h": 7}])
        self.assertEqual(ov.dug_size["R2"], (7, 7))

    def test_site_beside_water_is_not_dug(self):
        game = MapGame(BROOK)
        ov = overseer(game, [R9])
        self.assertIsNone(ov.act("dig_R9", "dig_room", {"site": "R9"}))
        self.assertEqual(game.tools("dig_room"), [])
        self.assertIn("R9", ov.wet_sites)

    def test_water_a_level_below_does_not_cut_a_room(self):
        ov = overseer(MapGame(BROOK), [{**R2, "id": "R8", "z": 155}])      # the brook is on 154, the room on 155
        self.assertEqual(ov.dry_dig("dig_room", {"site": "R8", "w": 9, "h": 7}), {"site": "R8", "w": 9, "h": 7})

    def test_water_a_level_above_does_not_cut_a_room(self):
        ov = overseer(MapGame(BROOK), [{**R4, "x": 98}])         # the brook is on 154, the room on 153
        self.assertEqual(ov.dry_dig("dig_room", {"site": "R4", "w": 9, "h": 3}), {"site": "R4", "w": 9, "h": 3})

    def test_dry_ground_is_dug_as_asked(self):
        ov = overseer(MapGame([]), [R2])
        self.assertEqual(ov.dry_dig("dig_room", {"site": "R2", "w": 9, "h": 7}), {"site": "R2", "w": 9, "h": 7})

    def test_failed_look_digs_as_asked(self):
        ov = overseer(MapGame(BROOK, fail=True), [R2])
        self.assertEqual(ov.dry_dig("dig_room", {"site": "R2", "w": 9, "h": 7}), {"site": "R2", "w": 9, "h": 7})

    def test_unknown_site_digs_as_asked(self):
        ov = overseer(MapGame(BROOK), [])
        self.assertEqual(ov.dry_dig("dig_room", {"site": "R7", "w": 9}), {"site": "R7", "w": 9})

    def test_one_look_per_box_per_tick(self):
        game = MapGame(BROOK)
        ov = overseer(game, [R2])
        ov.dry_dig("dig_room", {"site": "R2", "w": 9, "h": 7})
        ov.dry_dig("dig_room", {"site": "R2", "w": 9, "h": 7})
        self.assertEqual(len(game.maps), 1)

    def test_stair_stops_above_wet_level(self):
        game = MapGame([{"x": 96, "y": 93, "z": 152, "depth": 7}])
        ov = overseer(game, [S5])
        self.assertEqual(ov.dry_dig("dig_stairs", {"site": "S5", "z_bottom": 151}), {"site": "S5", "z_bottom": 153})

    def test_stair_beside_surface_water_is_not_dug(self):
        ov = overseer(MapGame([{"x": 94, "y": 92, "z": 155, "depth": 3}]), [S5])
        self.assertIsNone(ov.dry_dig("dig_stairs", {"site": "S5", "z_bottom": 151}))

    def test_deep_stair_is_looked_at_in_five_level_parts(self):
        game = MapGame([{"x": 95, "y": 92, "z": 146, "depth": 7}])
        ov = overseer(game, [S5])
        self.assertEqual(ov.dry_dig("dig_stairs", {"site": "S5", "z_bottom": 140}), {"site": "S5", "z_bottom": 147})
        self.assertTrue(all(abs(q["z"] - q["z2"]) <= 4 for q in game.maps))

    def test_digging_skips_a_wet_site(self):
        game = MapGame(BROOK)
        ov = overseer(game, [R9, R2])
        ov.digging()
        ov.digging()
        self.assertNotIn({"site": "R9"}, game.tools("dig_room"))
        self.assertTrue(any(a["site"] == "R2" for a in game.tools("dig_room")))


class ModelLoop(unittest.TestCase):
    def loop(self, ov):
        return types.SimpleNamespace(guard=ov, open_play=lambda: True, guard_owns_lock=lambda a: False,
                                     guard_seals_stair=lambda a: False, guard_felling_waits=lambda: False,
                                     guard_calm=lambda: False, cancelled=[], added={})

    def test_model_dig_beside_water_is_refused(self):
        ov = overseer(MapGame(BROOK), [R9])
        r = Plain.refuse(self.loop(ov), "dig_room", {"site": "R9"}, None)
        self.assertEqual(r["error_code"], "water_near")

    def test_model_dig_is_cut_back_in_place(self):
        ov = overseer(MapGame(BROOK), [R2])
        args = {"site": "R2", "w": 9, "h": 7}
        self.assertIsNone(Plain.refuse(self.loop(ov), "dig_room", args, None))
        self.assertEqual(args, {"site": "R2", "w": 7, "h": 7})


if __name__ == "__main__":
    unittest.main()
