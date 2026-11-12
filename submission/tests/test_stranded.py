"""cx STRANDED (hint hard MY1-3 on d57f599: the furnace operator bled to death on day 65 at (103,10,144), north of the
river that cuts the MY1-3 fort in two). The trio 84/212/213 stood on the north bank from day 0 (no walkable path to the
fort at wading depth <= 4: probe p13d's day-0 survey), the pre-emptive mark alert could not shelter them, and on
e33d381 the layer's squad pick took two of them. Here: the survey finds them on the real map, squad_pick passes over
them, and the rescue station is not sent across the water from a squad standing on the fort's side. No game or
network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from river_maps import answers as river_answers  # noqa: E402
from test_danger_marks import Quiet, fort  # noqa: E402
from overseer import harness  # noqa: E402

SURFACE = 144
WAGON = {"present": True, "x": 97, "y": 96, "z": SURFACE}
E_SITES = [{"id": "E1", "kind": "E", "x": 95, "y": 102, "z": SURFACE, "w": 1, "h": 1},
           {"id": "E2", "kind": "E", "x": 93, "y": 98, "z": SURFACE, "w": 1, "h": 1},
           {"id": "E3", "kind": "E", "x": 94, "y": 93, "z": SURFACE, "w": 1, "h": 1}]
# the day-0 look of d57f599 hint hard MY1-3 (the trio) and the day-65 look (213 at the fight's tile)
LEADER = {"id": 84, "name": "Datan Kuletsakrith, expedition leader", "profession": "expedition leader",
          "positions": ["EXPEDITION_LEADER"], "x": 162, "y": 19, "z": SURFACE}
BOWYER = {"id": 212, "name": "Tosid Thothoslan, Bowyer", "profession": "Bowyer", "x": 3, "y": 55, "z": SURFACE}
FURNACE = {"id": 213, "name": "ushrir Rigothag, Furnace Operator", "profession": "Furnace Operator",
           "x": 2, "y": 57, "z": SURFACE}
FURNACE_65 = dict(FURNACE, x=103, y=10)
MINER = {"id": 78, "name": "Kadol, Miner", "profession": "Miner", "x": 99, "y": 100, "z": SURFACE}
FISHER = {"id": 82, "name": "Iton, Fisherdwarf", "profession": "Fisherdwarf", "x": 100, "y": 103, "z": 142}
MASON = {"id": 83, "name": "Reg, Mason", "profession": "Mason", "x": 104, "y": 101, "z": 142}
GEM = {"id": 253, "name": "a migrant, Gem Cutter", "profession": "Gem Cutter", "x": 98, "y": 99, "z": SURFACE}


class MapGame:
    """Serves the real day-0 map squares for /query/map and a units list for /query/units."""
    def __init__(self, units=(), citizens=()):
        self.calls, self.units, self.citizens, self.maps = [], list(units), list(citizens), 0

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {}}

    def query(self, name, **kw):
        if name == "map":
            self.maps += 1
            return {"result": river_answers(kw["x"], kw["y"], kw["radius"], kw["z"], kw["z2"])}
        if kw.get("kind") == "citizens":
            return {"result": {"units": [dict(u) for u in self.citizens]}}
        return {"result": {"units": list(self.units)}}


def my1_3(day, dwarves, alert=False, squads=()):
    r = fort(day, alert=alert, dwarves=dwarves, squads=squads)
    o = r["observation"]
    o["map"].update({"wagon": dict(WAGON), "surface_z": SURFACE, "size_tiles": [192, 192, 161],
                     "sites": [dict(s) for s in E_SITES]})
    o["administrators"]["citizens"] = len(dwarves)
    o["burrows"]["list"] = [{"id": 0, "civ_alert_burrow": True, "name": "Shelter",
                             "citizens_inside": sum(1 for x in dwarves if x["z"] < SURFACE)}]
    return r


class RealMap(unittest.TestCase):
    def setUp(self):
        self.shape, self.water, self.zs = harness.map_tiles([river_answers()])

    def test_the_river_cuts_the_trio_off(self):
        home = [(97, 96, SURFACE)] + [(s["x"], s["y"], s["z"]) for s in E_SITES]
        got = harness.stranded_of(self.shape, self.water, [LEADER, BOWYER, FURNACE, FURNACE_65, MINER], home,
                                  SURFACE)
        self.assertEqual(got, {84, 212, 213})

    def test_the_two_regions_as_measured(self):
        fort_, fort_open = harness.walk_region(self.shape, self.water, (97, 96, SURFACE))
        north, north_open = harness.walk_region(self.shape, self.water, (103, 10, SURFACE))
        self.assertFalse(north_open)                 # flat: all on z144, no way off the read levels
        self.assertEqual(len(north), 13619)
        self.assertNotIn((97, 96, SURFACE), north)
        self.assertIn((3, 55, SURFACE), north)
        self.assertIn((162, 19, SURFACE), north)
        self.assertNotIn((103, 10, SURFACE), fort_)
        self.assertGreater(len(fort_), 20000)

    def test_only_the_east_mouth_joins_them(self):
        # depth 5-6 at x185-191 y84-87 is the only water under 7: wading 6 deep would join the banks
        north6, _ = harness.walk_region(self.shape, self.water, (103, 10, SURFACE), wade=6)
        self.assertIn((97, 96, SURFACE), north6)
        north5, _ = harness.walk_region(self.shape, self.water, (103, 10, SURFACE), wade=5)
        self.assertNotIn((97, 96, SURFACE), north5)

    def test_an_open_region_says_nothing(self):
        # a ramp up from the top read level: the region may go on above — never called stranded
        shape = {(x, 0, 10): "." for x in range(5)}
        shape[(4, 0, 10)] = "^"
        tiles, opened = harness.walk_region(shape, {}, (0, 0, 10))
        self.assertTrue(opened)
        self.assertEqual(harness.stranded_of(shape, {}, [{"id": 1, "x": 0, "y": 0, "z": 10}], [(50, 50, 10)], 10),
                         set())

    def test_unread_or_underground_citizens_are_not_stranded(self):
        home = [(97, 96, SURFACE)]
        self.assertEqual(harness.stranded_of(self.shape, self.water, [FISHER, MASON], home, SURFACE), set())
        self.assertEqual(harness.stranded_of({}, {}, [FURNACE], home, SURFACE), set())


class Survey(Quiet):
    def test_the_survey_finds_them_and_waits_its_days(self):
        game = MapGame()
        ov = harness.Overseer(game, days=216)
        ov.load(my1_3(0, [LEADER, BOWYER, FURNACE, MINER, FISHER]))
        ov.stranded_survey()
        self.assertEqual(ov.stranded, {84, 212, 213})
        self.assertEqual(game.maps, 25)                      # 5 x 5 squares of radius 20 over 192 x 192
        # cx STRANDED HOME: while anyone is stranded the survey runs every STRANDED_JOIN_DAYS whatever the cache (the
        # ice is a floor the cache never placed); with nobody stranded the cache holds (woodcutters far on the fort's side)
        cutter = dict(MINER, x=120, y=150)
        ov.load(my1_3(1, [LEADER, BOWYER, FURNACE_65, cutter, FISHER]))
        ov.stranded_survey()
        self.assertEqual(game.maps, 25)                      # not STRANDED_JOIN_DAYS yet
        ov.load(my1_3(2, [LEADER, BOWYER, FURNACE_65, cutter, FISHER]))
        ov.stranded_survey()
        self.assertEqual((game.maps, ov.stranded), (50, {84, 212, 213}))

    def test_the_cache_holds_with_nobody_stranded(self):
        game = MapGame()
        ov = harness.Overseer(game, days=216)
        cutter = dict(MINER, x=120, y=150)
        ov.load(my1_3(0, [cutter, FISHER]))
        ov.stranded_survey()
        self.assertEqual((game.maps, ov.stranded), (25, set()))
        ov.load(my1_3(5, [dict(cutter, x=125, y=140), FISHER]))
        ov.stranded_survey()
        self.assertEqual(game.maps, 25)                      # a placed fort tile: no new survey
        odd = dict(MINER, x=40, y=61)    # over the west channel: no walkable reading
        ov.load(my1_3(6, [odd, FISHER]))
        ov.stranded_survey()
        self.assertEqual(game.maps, 50)
        ov.load(my1_3(7, [odd, FISHER]))
        ov.stranded_survey()
        self.assertEqual(game.maps, 50)                      # STRANDED_SCAN_DAYS between surveys

    def test_a_citizen_who_crossed_is_dropped_on_the_fort_side(self):
        game = MapGame()
        ov = harness.Overseer(game, days=216)
        ov.load(my1_3(0, [LEADER, BOWYER, FURNACE, MINER]))
        ov.stranded_survey()
        # the bowyer on the fort's bank 70 tiles from the wagon (the east mouth crossing): dropped, no survey
        ov.load(my1_3(1, [LEADER, dict(BOWYER, x=150, y=150), FURNACE, MINER]))
        ov.stranded_survey()
        self.assertEqual((ov.stranded, game.maps), ({84, 213}, 25))

    def test_nobody_far_no_survey(self):
        game = MapGame()
        ov = harness.Overseer(game, days=216)
        ov.load(my1_3(0, [MINER, FISHER, MASON]))
        ov.stranded_survey()
        self.assertEqual((ov.stranded, game.maps), (set(), 0))

    def test_a_crossed_citizen_is_dropped_at_once(self):
        game = MapGame()
        ov = harness.Overseer(game, days=216)
        ov.load(my1_3(0, [LEADER, BOWYER, FURNACE, MINER]))
        ov.stranded_survey()
        # day 88: the bowyer reached the fort (d57f599: (102,101,144)), the furnace operator is in the Shelter
        ov.load(my1_3(1, [LEADER, dict(BOWYER, x=102, y=101), dict(FURNACE, x=100, y=101, z=142), MINER]))
        ov.stranded_survey()
        self.assertEqual(ov.stranded, {84})

    def test_a_lost_query_measures_nothing(self):
        class Lost(MapGame):
            def query(self, name, **kw):
                if name == "map" and self.maps == 3:
                    raise RuntimeError("gone")
                return MapGame.query(self, name, **kw)
        game = Lost()
        ov = harness.Overseer(game, days=216)
        ov.load(my1_3(0, [LEADER, BOWYER, FURNACE, MINER]))
        ov.stranded_survey()
        self.assertEqual(ov.stranded, set())

    def test_the_plan_runs_it_with_the_guard_steps(self):
        game = MapGame()
        ov = harness.Overseer(game, days=216)
        ov.load(my1_3(0, [LEADER, BOWYER, FURNACE, MINER]))
        ov.count = 0
        try:
            ov.plan()
        except Exception:   # noqa: BLE001  the rest of the plan may want more of the observation
            pass
        self.assertEqual(ov.stranded, {84, 212, 213})


class SquadAndRescue(Quiet):
    def test_squad_pick_passes_over_the_stranded(self):
        # e33d381 hint hard MY1-3 day 71: squad_pick took [213, 212, 253, 82] — 213 and 212 on the north bank
        cits = [dict(FURNACE, labors=[]), dict(BOWYER, labors=[]), dict(GEM, labors=[]),
                dict(FISHER, labors=["FISH"]), dict(MASON, labors=[]), dict(MINER, labors=["MINE"]),
                dict(LEADER, labors=[])]
        game = MapGame(citizens=cits)
        ov = harness.Overseer(game, days=216)
        ov.load(my1_3(71, [FURNACE, BOWYER, GEM, FISHER, MASON, MINER, LEADER]))
        before = ov.squad_pick(4)
        self.assertIn(213, before)
        self.assertIn(212, before)
        ov.stranded = {84, 212, 213}
        after = ov.squad_pick(4)
        self.assertNotIn(213, after)
        self.assertNotIn(212, after)
        self.assertIn(253, after)

    def rescue_calls(self, ov, game, dwarves, squad):
        ov.load(my1_3(65, dwarves, alert=True, squads=[squad]))
        ov.count = 0
        game.calls.clear()
        ov.mark_guard()
        return [a for t, a in game.calls if t == "squad_order"]

    def test_no_rescue_across_the_water_from_a_fort_side_squad(self):
        # the day-65 look: a langur one tile from the furnace operator at (103,10); the squad stands in the fort
        squad = {"id": 0, "armed": 2, "uniform": "leather", "orders": [],
                 "members": [{"id": 78}, {"id": 82}, {"id": 83}, {"id": 253}]}
        langur = [{"id": 250, "race": "GRAY_LANGUR", "hostile": False, "x": 104, "y": 10, "z": SURFACE}]
        dwarves = [FURNACE_65, MINER, FISHER, MASON, GEM]
        game = MapGame(units=langur)
        ov = harness.Overseer(game, days=216)
        calls = self.rescue_calls(ov, game, dwarves, squad)
        self.assertIn({"order": "station", "x": 103, "y": 10, "z": SURFACE}, calls)   # before: sent across
        game = MapGame(units=langur)
        ov = harness.Overseer(game, days=216)
        ov.stranded = {213}
        calls = self.rescue_calls(ov, game, dwarves, squad)
        self.assertNotIn({"order": "station", "x": 103, "y": 10, "z": SURFACE}, calls)

    def test_a_reachable_citizen_is_still_rescued(self):
        squad = {"id": 0, "armed": 2, "uniform": "leather", "orders": [],
                 "members": [{"id": 82}, {"id": 83}, {"id": 253}, {"id": 80}]}
        langur = [{"id": 250, "race": "GRAY_LANGUR", "hostile": False, "x": 101, "y": 99, "z": SURFACE}]
        game = MapGame(units=langur)
        ov = harness.Overseer(game, days=216)
        ov.stranded = {213}
        calls = self.rescue_calls(ov, game, [FURNACE_65, MINER, FISHER, MASON, GEM], squad)
        self.assertIn({"order": "station", "x": 99, "y": 100, "z": SURFACE}, calls)

    def test_a_squad_stranded_with_them_keeps_the_old_rule(self):
        squad = {"id": 0, "armed": 2, "uniform": "leather", "orders": [],
                 "members": [{"id": 212}, {"id": 82}, {"id": 83}, {"id": 253}]}
        langur = [{"id": 250, "race": "GRAY_LANGUR", "hostile": False, "x": 104, "y": 10, "z": SURFACE}]
        game = MapGame(units=langur)
        ov = harness.Overseer(game, days=216)
        ov.stranded = {212, 213}
        calls = self.rescue_calls(ov, game, [FURNACE_65, BOWYER, MINER, FISHER, MASON, GEM], squad)
        self.assertIn({"order": "station", "x": 103, "y": 10, "z": SURFACE}, calls)


if __name__ == "__main__":
    unittest.main()
