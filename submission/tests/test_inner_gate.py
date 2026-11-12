"""cx inner gate (owner-approved 2026-11-10; hint hard MY1-4 on 5d8cf68: E1 (100,101,169) had a building on its stair
tile from day 0, build_door hatch answered tile_occupied, a kea flew down it into the Shelter on day 93.7 and a child
died). An entrance no hatch can close is shut one level down: a door on the D site that cuts the stair's landing off
from the rest of each level the shaft touches, built while no alert stands, locked during an alert once every
citizen is in the Shelter and nobody stands on the landing, unlocked like the hatches. The landing is never Shelter:
an A/R box touching it is not added (the level's inner R rooms are), and a shaft whose D sites are not surveyed yet
keeps its boxes out until the survey has run. No game or network."""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_shelter_hatches import FakeGame, Quiet, fort, overseer, SURFACE, WAGON  # noqa: E402
from overseer import harness  # noqa: E402

Z = SURFACE - 1   # 168, the landing level
# a synthetic level (x94..110, y96..100): a 3x3 landing x95-97 y97-99 round the up stair (96,98), a one-tile doorway
# (98,98) in the wall column x98, the fort's room x99-109 y97-99 behind it
X1, Y1 = 94, 96
ROWS = ["#################",
        "#...#...........#",
        "#.<.............#",
        "#...#...........#",
        "#################"]
# the observation's real site shapes (cxd769d66 hint std MY1-4 / cx4e5f701 hint hard MY1-0 harness api.jsonl):
# {id, w, h, soil, kind, x, y, z, designated, dug, free} plus the kind's own facts (E: building)
REAL = {"soil": None, "designated": None, "dug": None, "free": True}
E1 = dict(REAL, id="E1", kind="E", x=96, y=98, z=SURFACE, w=1, h=1, building=True)
E2 = dict(REAL, id="E2", kind="E", x=90, y=91, z=SURFACE, w=1, h=1, building=False)
D1 = dict(REAL, id="D1", kind="D", x=98, y=98, z=Z, w=1, h=1)
D2 = dict(REAL, id="D2", kind="D", x=104, y=98, z=Z, w=1, h=1)   # inside the big room: no gate
A1 = {"id": "A1", "kind": "A", "x": 95, "y": 97, "z": Z, "w": 15, "h": 3, "open_tiles": 42}
A2 = {"id": "A2", "kind": "A", "x": 95, "y": 100, "z": Z - 1, "w": 12, "h": 3, "open_tiles": 30}
R_IN = {"id": "R1", "kind": "R", "x": 103, "y": 97, "z": Z, "w": 3, "h": 3, "dug": True, "designated": True}
R_OUT = {"id": "R2", "kind": "R", "x": 95, "y": 97, "z": Z, "w": 3, "h": 3, "dug": True, "designated": True}
LANDING = {(x, y, Z) for x in (95, 96, 97) for y in (97, 98, 99)}
DOOR = {"id": 80, "kind": "door", "built": True, "locked": False, "x": 98, "y": 98, "z": Z}
INSIDE = {"id": 5, "name": "Urist", "profession": "Miner", "x": 105, "y": 98, "z": Z}
ON_LANDING = dict(INSIDE, id=6, x=96, y=99)


class MapGame(FakeGame):
    def __init__(self, levels=None, x1=X1, y1=Y1, answers=None, fail=False):
        super().__init__(answers=answers)
        self.levels = {Z: ROWS} if levels is None else levels
        self.x1, self.y1, self.fail, self.maps = x1, y1, fail, []

    def query(self, name, **kw):
        if name != "map":
            return super().query(name, **kw)
        self.maps.append(kw)
        env = {"day": 10, "tick": 12000, "days_left": 206, "game_over": False, "query": "map"}
        if self.fail:   # a refusal: the envelope with a top-level ok false and no result
            return dict(env, ok=False, error_code="internal_error", error="map query failed")
        # the real answer (/query/map, cx4e5f701 hint hard MY1-0): no top-level ok, the payload and its own ok under
        # "result", one {z, shape, light, material} row set per level
        width = max(len(r) for rows in self.levels.values() for r in rows)
        height = max(len(rows) for rows in self.levels.values())
        return dict(env, result={"ok": True, "x1": self.x1, "y1": self.y1, "x2": self.x1 + width - 1,
                                 "y2": self.y1 + height - 1, "rows": height, "liquid": [], "buildings": [],
                                 "designations": [], "legend": {}, "levels": [
            {"z": z, "shape": list(rows), "light": ["u" * len(r) for r in rows], "material": ["r" * len(r) for r in rows]}
            for z, rows in sorted(self.levels.items(), reverse=True)]})


def doors(lst=(), free=4):
    return {"door_items_free": free, "hatch_cover_items_free": 0, "list": [dict(x) for x in lst]}


def look(day, sites=(E1, D1, A1, R_IN, R_OUT), alert=False, inside=None, citizens=1, door_list=(), free=4,
         dwarves=(INSIDE,), orders=()):
    return fort(day, sites, alert=alert, inside=inside, citizens=citizens, doors=doors(door_list, free),
                dwarves=dwarves, orders=orders)


class Plan(Quiet):
    def test_the_doorway_next_to_the_landing_is_chosen_and_the_landing_drawn(self):
        plan, why = harness.Overseer.gate_plan({Z: ROWS}, X1, Y1, (96, 98, SURFACE), [D2, D1])
        self.assertEqual(why, "ok")
        self.assertEqual(plan[Z]["site"], "D1")
        self.assertEqual(plan[Z]["at"], (98, 98, Z))
        self.assertEqual(set(plan[Z]["landing"]), LANDING)

    def test_a_d_site_that_cuts_nothing_off_is_no_gate(self):
        plan, why = harness.Overseer.gate_plan({Z: ROWS}, X1, Y1, (96, 98, SURFACE), [D2])
        self.assertEqual((plan, why), ({}, "no_door_z%d" % Z))

    def test_a_landing_with_another_way_down_is_no_gate(self):
        rows = list(ROWS)
        rows[1] = "#X..#...........#"   # an up/down stair at (95,97) on the stair side
        plan, why = harness.Overseer.gate_plan({Z: rows, Z - 1: ["#" * 17] * 5}, X1, Y1, (96, 98, SURFACE), [D1])
        self.assertEqual(why, "no_door_z%d" % Z)

    def test_a_shaft_through_two_levels_needs_a_door_on_both(self):
        upper = [r.replace("<", "X") for r in ROWS]
        both = {Z: upper, Z - 1: ROWS}
        d_low = dict(D1, id="D7", z=Z - 1)
        plan, why = harness.Overseer.gate_plan(both, X1, Y1, (96, 98, SURFACE), [D1, d_low])
        self.assertEqual(why, "ok")
        self.assertEqual({z: g["site"] for z, g in plan.items()}, {Z: "D1", Z - 1: "D7"})
        plan, why = harness.Overseer.gate_plan(both, X1, Y1, (96, 98, SURFACE), [D1])
        self.assertEqual((plan, why), ({}, "no_door_z%d" % (Z - 1)))
        plan, why = harness.Overseer.gate_plan({Z: upper}, X1, Y1, (96, 98, SURFACE), [D1])
        self.assertEqual((plan, why), ({}, "shaft_deeper"))

    def test_the_my1_4_stair_has_no_doorway_to_shut(self):
        # cx5d8cf68 hint hard MY1-4 harness-4.api.jsonl line 51 (day 5 map query x86..110): the E1 shaft (100,101)
        # is itself the one-tile gap between R1 (x97-99) and the farm corridor at z168, and between the dining room
        # and the beds at z167; no D site is ever listed. z166 is not in that query: walled here (no A site ever
        # covered a z166 level). Even a D on either side of the stair would cut nothing off.
        z168 = ["??????????###############", "??????????#...#..........", "??????????#...X..........",
                "??????????#...#.........."]
        z167 = ["????????#################", "????????#.....#..........", "????????#.....X..........",
                "????????#.....#.........."]
        levels = {168: z168, 167: z167, 166: ["#" * 25] * 4}
        ds = [{"id": "Dw", "kind": "D", "x": 99, "y": 101, "z": 168}, {"id": "De", "kind": "D", "x": 101, "y": 101,
                                                                       "z": 168}]
        plan, why = harness.Overseer.gate_plan(levels, 86, 99, (100, 101, 169), ds)
        self.assertEqual((plan, why), ({}, "no_door_z168"))


class Survey(Quiet):
    def test_no_d_site_one_survey_logs_the_unlisted_doorway_and_the_squad_fallback_stays(self):
        # the real MY1-4 shape: no D site listed all run. The shaft is still surveyed once (a doorway the map shows
        # is logged), no door can be placed (build_door takes a listed site only) and the open shaft stays the
        # squad's to guard
        game = MapGame()
        ov = overseer(game)
        ov.load(look(10, sites=(E1, A1)))
        out = io.StringIO()
        with redirect_stdout(out):
            ov.gate_survey()
            ov.gate_survey()
        self.assertEqual(len(game.maps), 1)
        self.assertNotIn("E1", ov.gates)
        self.assertEqual(ov.open_entrances(), [(96, 98, SURFACE)])
        none = [json.loads(x) for x in out.getvalue().splitlines() if '"gate_none"' in x]
        self.assertEqual(none[0]["doorways"], [[98, 98, Z]])
        self.assertEqual(none[0]["unlisted_gate"], {str(Z): [98, 98, Z]})
        ov.load(look(11, sites=(E1, A1)))
        ov.gate_survey()
        self.assertEqual(len(game.maps), 1)   # the same (empty) D set is not surveyed again

    def test_the_doorway_test_matches_observe_lua(self):
        spots = harness.Overseer.gate_doorways({Z: ROWS}, X1, Y1, (96, 98, SURFACE))
        self.assertEqual([(p["x"], p["y"], p["z"]) for p in spots], [(98, 98, Z)])
        z168 = ["??????????###############", "??????????#...#..........", "??????????#...X..........",
                "??????????#...#.........."]
        self.assertEqual(harness.Overseer.gate_doorways({168: z168}, 86, 99, (100, 101, 169)), [])

    def test_one_query_per_new_d_set_and_a_hatched_entrance_is_left_alone(self):
        game = MapGame()
        ov = overseer(game)
        ov.load(look(10, sites=(E1, E2, D1, A1)))
        ov.gate_survey()
        self.assertEqual(len(game.maps), 1)
        self.assertEqual(game.maps[0]["z"], Z)
        self.assertEqual(ov.gates["E1"][Z]["site"], "D1")
        ov.load(look(11, sites=(E1, E2, D1, A1)))
        ov.gate_survey()
        self.assertEqual(len(game.maps), 1)

    def test_no_gate_is_surveyed_again_only_when_the_d_sites_change_and_once_a_day(self):
        game = MapGame()
        ov = overseer(game)
        ov.load(look(10, sites=(E1, D2, A1)))
        ov.gate_survey()
        ov.gate_survey()
        self.assertEqual(len(game.maps), 1)
        self.assertNotIn("E1", ov.gates)
        ov.load(look(10, sites=(E1, D1, D2, A1)))
        ov.gate_survey()
        self.assertEqual(len(game.maps), 1)   # one map query a game day
        ov.load(look(11, sites=(E1, D1, D2, A1)))
        ov.gate_survey()
        self.assertEqual(len(game.maps), 2)
        self.assertEqual(ov.gates["E1"][Z]["site"], "D1")

    def test_a_failed_query_is_retried_the_next_day(self):
        game = MapGame(fail=True)
        ov = overseer(game)
        ov.load(look(10))
        ov.gate_survey()
        self.assertNotIn("E1", ov.gate_seen)
        game.fail = False
        ov.load(look(11))
        ov.gate_survey()
        self.assertIn("E1", ov.gates)


class Shelter(Quiet):
    def test_the_landing_box_stays_out_and_the_inner_room_goes_in(self):
        game = MapGame()
        ov = overseer(game)
        ov.load(look(10, sites=(E1, D1, A1, A2, R_IN, R_OUT)))
        ov.gate_survey()
        ov.shelter_grow()
        self.assertEqual(game.tools("create_burrow"), [{"site": "A2"}, {"site": "R1"}])

    def test_an_unsurveyed_shaft_holds_its_boxes(self):
        game = MapGame()
        ov = overseer(game)
        ov.gate_probe_day = 10   # today's query is spent
        ov.load(look(10, sites=(E1, D1, A1, A2, R_IN, R_OUT)))
        ov.gate_survey()
        ov.shelter_grow()
        self.assertEqual(game.tools("create_burrow"), [])   # every box near the shaft on its levels waits
        self.assertEqual(game.maps, [])
        game.calls.clear()
        ov.load(look(11, sites=(E1, D1, A1, A2, R_IN, R_OUT)))
        ov.gate_survey()
        ov.shelter_grow()
        self.assertEqual(game.tools("create_burrow"), [{"site": "A2"}, {"site": "R1"}])

    def test_with_no_gate_the_level_box_goes_in_as_before(self):
        game = MapGame()
        ov = overseer(game)
        ov.load(look(10, sites=(E1, D2, A1, R_IN, R_OUT)))
        ov.gate_survey()
        ov.shelter_grow()
        self.assertEqual(game.tools("create_burrow"), [{"site": "A1"}])

    def test_defend_surveys_before_the_shelter_grows(self):
        game = MapGame()
        ov = overseer(game)
        ov.load(look(10, sites=(E1, D1, A1, R_IN, R_OUT)))
        ov.defend()
        self.assertEqual(game.tools("create_burrow"), [{"site": "R1"}])


class Door(Quiet):
    def ready(self, game=None):
        game = game or MapGame()
        ov = overseer(game)
        ov.load(look(10))
        ov.gate_survey()
        game.calls.clear()
        return game, ov

    def test_the_door_is_built_while_no_alert_stands(self):
        game, ov = self.ready()
        ov.entrance_hatches()
        self.assertEqual(game.tools("build_door"), [{"kind": "door", "site": "D1"}])
        game.calls.clear()
        ov.load(look(11, alert=True, inside=1))
        ov.entrance_hatches()
        self.assertEqual(game.tools("build_door"), [])

    def test_no_door_item_orders_one(self):
        game, ov = self.ready()
        ov.load(look(10, free=0))
        ov.entrance_hatches()
        self.assertEqual([a for a in game.tools("add_order") if a["recipe"] == "make_door"],
                         [{"recipe": "make_door", "amount": 1}])
        self.assertEqual(game.tools("build_door"), [])

    def test_a_refused_site_drops_the_plan(self):
        game, ov = self.ready(MapGame(answers={("build_door", "D1"): {"ok": False, "error_code": "site_used"}}))
        ov.entrance_hatches()
        self.assertNotIn("E1", ov.gates)
        self.assertNotIn("E1", ov.gate_seen)

    def test_locked_with_everyone_inside_and_nobody_on_the_landing_then_unlocked(self):
        game, ov = self.ready()
        ov.load(look(12, sites=(E1, A1), alert=True, inside=1, door_list=(DOOR,)))
        self.assertEqual(ov.open_entrances(), [])   # the squad no longer holds this stair's foot
        ov.entrance_hatches()
        self.assertEqual(game.tools("lock_door"), [{"locked": True, "door_id": 80}])
        game.calls.clear()
        ov.load(look(13, sites=(E1, A1), alert=False, inside=1, door_list=(dict(DOOR, locked=True),)))
        ov.entrance_hatches()
        self.assertEqual(game.tools("lock_door"), [{"locked": False, "door_id": 80}])

    def test_a_citizen_on_the_landing_keeps_it_open(self):
        game, ov = self.ready()
        ov.load(look(12, sites=(E1, A1), alert=True, inside=2, citizens=2, door_list=(DOOR,),
                     dwarves=(INSIDE, ON_LANDING)))
        ov.entrance_hatches()
        self.assertEqual(game.tools("lock_door"), [])

    def test_someone_outside_the_shelter_keeps_it_open(self):
        game, ov = self.ready()
        ov.load(look(12, sites=(E1, A1), alert=True, inside=1, citizens=2, door_list=(DOOR,)))
        ov.entrance_hatches()
        self.assertEqual(game.tools("lock_door"), [])

    def test_an_unbuilt_door_is_not_a_closed_gate(self):
        game, ov = self.ready()
        ov.load(look(12, sites=(E1, A1), alert=True, inside=1, door_list=(dict(DOOR, built=False),)))
        self.assertEqual(ov.open_entrances(), [(96, 98, SURFACE)])
        ov.entrance_hatches()
        self.assertEqual(game.tools("lock_door"), [])


if __name__ == "__main__":
    unittest.main()
