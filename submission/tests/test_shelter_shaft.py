"""cx shelter shaft (owner via coordinator, after 8032c7a): a short closed-room Shelter with no spare R site may grow
through one new stair from the surface — a free hatch cover reserved first, entrances within ENTRANCE_MAX, no big
beast near, SHAFT_PEOPLE_GAP from the people zones, a rock column — and its top is hatched on the pass it lists; a
refused hatch ends new shafts. Fixture: tests/test_closed_sites.py (LT08-2 z104 shapes). No game or network."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_closed_sites import A1, R1, FakeGame, Quiet, light  # noqa: E402
from overseer import harness  # noqa: E402

E1 = {"id": "E1", "kind": "E", "x": 91, "y": 105, "z": 105, "w": 1, "h": 1, "building": True}
S1 = {"id": "S1", "kind": "S", "x": 93, "y": 94, "z": 105, "w": 1, "h": 1}
S9 = {"id": "S9", "kind": "S", "x": 90, "y": 108, "z": 105, "w": 1, "h": 1}   # 0 tiles from the R1 dorm box
HATCH_E1 = {"id": 48, "kind": "hatch", "x": 91, "y": 105, "z": 105, "built": True, "locked": False}
DORM = {"id": 26, "type": "Dormitory", "x": 88, "y": 104, "z": 104, "w": 9, "h": 7}


class ShaftGame(FakeGame):
    rock = {(93, 94), (90, 108)}

    def query(self, name, **kw):
        if name == "map" and kw.get("radius") == 0:
            x, y = kw["x"], kw["y"]
            levels = [{"z": z, "shape": ["#" if (x, y) in self.rock else "."], "light": ["u"]}
                      for z in range(kw["z2"], kw["z"] + 1)]
            return {"result": {"ok": True, "x1": x, "y1": y, "levels": levels}}
        return super().query(name, **kw)

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool == "build_door" and getattr(self, "occupied", False):
            return {"ok": False, "error_code": "tile_occupied", "error": "a building stands there"}
        return {"ok": True, "result": {}}


class Shaft(Quiet):
    def fort(self, sites=(A1, R1, E1, S1, S9), covers=2, hatches=(HATCH_E1,), zones=(DORM,), others=(), day=16,
             alert=False):
        game = ShaftGame(list(sites), others)
        agent = harness.Overseer(game, goal="migrant surge", days=60)
        agent.count = 0
        game.covers, game.hatches, game.zones_, game.alert = covers, list(hatches), list(zones), alert
        self.look(agent, game, day)
        agent.room_box["R1"] = {"x": 88, "y": 104, "z": 104, "w": 9, "h": 7}
        agent.roles["R1"] = "dorm"
        agent.shelter_grow()   # A1 open: the Shelter is R1 9x7 (63 tiles) for 48
        return agent, game

    def look(self, agent, game, day):
        o = game.observe(day=day, cit=48)
        ob = o["observation"]
        ob["doors"] = {"hatch_cover_items_free": game.covers, "door_items_free": 0, "list": copy.deepcopy(game.hatches)}
        ob["zones"] = copy.deepcopy(game.zones_)
        ob["burrows"] = {"civilian_alert": game.alert,
                         "list": [{"id": 0, "civ_alert_burrow": True, "name": "Shelter", "citizens_inside": 48}]}
        ob["dig_designations_pending"] = 0
        agent.load(o)
        agent.entrance_hatches()   # records the E sites (entrances), as the guard step does

    def digs(self, game):
        return [c for c in game.calls if c[0] == "dig_stairs"]

    def test_short_shelter_with_a_spare_cover_digs_one_shaft_off_the_people_boxes(self):
        agent, game = self.fort()
        agent.shelter_room(0)
        self.assertEqual(self.digs(game), [("dig_stairs", {"site": "S1", "z_bottom": 103})])   # not S9 by the dorm
        self.assertEqual(agent.shaft["site"], "S1")
        agent.shelter_room(0)   # one at a time
        self.assertEqual(len(self.digs(game)), 1)

    def test_no_spare_cover_digs_nothing(self):
        # cx hatch early: the covers ahead of a new entrance come from hatch_order (HATCH_SPARE), not from here
        agent, game = self.fort(covers=0)
        n = len(game.calls)
        agent.shelter_room(0)
        self.assertEqual(self.digs(game), [])
        self.assertEqual(game.calls[n:], [])

    def test_a_cover_needed_by_a_hatchless_entrance_is_not_spare(self):
        e2 = {"id": "E2", "kind": "E", "x": 100, "y": 100, "z": 105, "w": 1, "h": 1, "building": False}
        agent, game = self.fort(sites=(A1, R1, E1, e2, S1), covers=1, alert=True)
        self.assertEqual(agent.hatch_free_spare(), 0)
        agent.shelter_room(0)
        self.assertEqual(self.digs(game), [])

    def test_entrance_cap(self):
        es = [{"id": "E%d" % i, "kind": "E", "x": 80 + i, "y": 120, "z": 105, "w": 1, "h": 1, "building": True}
              for i in range(1, 5)]
        hs = [{"id": 40 + i, "kind": "hatch", "x": 80 + i, "y": 120, "z": 105, "built": True} for i in range(1, 5)]
        agent, game = self.fort(sites=[A1, R1, S1] + es, hatches=hs, covers=3)
        agent.shelter_room(0)
        self.assertEqual(self.digs(game), [])

    def test_a_big_beast_near_holds_the_dig_and_reserves_nothing(self):
        agent, game = self.fort(others=[{"id": 113, "race": "ALLIGATOR", "x": 80, "y": 94, "z": 104}])
        agent.shelter_room(0)
        self.assertEqual(self.digs(game), [])
        self.assertIsNone(agent.shaft)

    def test_a_column_over_open_floor_is_not_dug(self):
        agent, game = self.fort()
        game.rock = set()
        agent.shelter_room(0)
        self.assertEqual(self.digs(game), [])

    def test_the_top_is_hatched_on_the_pass_it_lists_even_in_an_alert_then_ends(self):
        agent, game = self.fort()
        agent.shelter_room(0)
        game.alert = True
        e2 = {"id": "E2", "kind": "E", "x": 93, "y": 94, "z": 105, "w": 1, "h": 1, "building": False}
        game.sites.append(e2)
        self.look(agent, game, 18)
        agent.shaft_hatch()
        self.assertIn(("build_door", {"kind": "hatch", "site": "E2"}), game.calls)
        # entrance_hatches never spends a cover on it (and skips it in the alert anyway)
        self.assertEqual(sum(1 for c in game.calls if c == ("build_door", {"kind": "hatch", "site": "E2"})), 1)
        game.hatches.append({"id": 60, "kind": "hatch", "x": 93, "y": 94, "z": 105, "built": False})
        self.look(agent, game, 18.5)
        agent.shaft_hatch()
        self.assertIsNotNone(agent.shaft)
        game.hatches[-1]["built"] = True
        self.look(agent, game, 19)
        agent.shaft_hatch()
        self.assertIsNone(agent.shaft)
        self.assertEqual(agent.shaft_open_days, [1])

    def test_in_an_alert_a_game_hostile_near_the_top_holds_the_hatch_without_stopping_shafts(self):
        # cx audit: the shaft's own hatch follows entrance_hatches' alert rule (hatch_safe)
        gob = {"id": 501, "race": "GOBLIN", "hostile": True, "x": 96, "y": 94, "z": 105}
        agent, game = self.fort()
        agent.shelter_room(0)
        game.alert = True
        game.others = [gob]
        game.sites.append({"id": "E2", "kind": "E", "x": 93, "y": 94, "z": 105, "w": 1, "h": 1, "building": False})
        self.look(agent, game, 18)
        agent.shaft_hatch()
        self.assertNotIn(("build_door", {"kind": "hatch", "site": "E2"}), game.calls)
        self.assertFalse(agent.shaft_stop)
        self.assertIsNotNone(agent.shaft)
        game.others = []
        self.look(agent, game, 19)
        agent.shaft_hatch()
        self.assertIn(("build_door", {"kind": "hatch", "site": "E2"}), game.calls)

    def test_a_refused_hatch_stops_new_shafts(self):
        agent, game = self.fort()
        agent.shelter_room(0)
        game.occupied = True
        game.sites.append({"id": "E2", "kind": "E", "x": 93, "y": 94, "z": 105, "w": 1, "h": 1, "building": True})
        self.look(agent, game, 18)
        agent.shaft_hatch()
        self.assertTrue(agent.shaft_stop)
        self.assertIsNone(agent.shaft)
        n = len(self.digs(game))
        game.covers = 3
        self.look(agent, game, 30)
        agent.shelter_room(0)
        self.assertEqual(len(self.digs(game)), n)


if __name__ == "__main__":
    unittest.main()
