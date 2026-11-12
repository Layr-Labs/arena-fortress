"""cx rescue station (hint hard MY1-4 on 5d8cf68, survival 0.8). A kea came down the E1 stair — an E site with a
building on its tile, so build_door answered tile_occupied all run and only E2's hatch was ever locked — into the
sheltered fort on day 93.7; a dwarven child (a citizen: counted in citizens and citizens_inside, sheltered at z168
days 88-93) fled up E1 to the surface, where the kea knocked it out (tick 1079938) and beat it to death by tick
1082200, inside the alert (day 86 on; the 10-day cap only lifted it on day 98) and inside one model advance (the
signs alert/marked/near never changed between pieces). The squad (4 members, 2 armed) never met the all-armed
station gate. Now the chunk look stops on a citizen fight with a marked species and on a marked animal at a citizen's
side on the surface; a half-armed squad of 4 is stationed on the threatened citizen, and at the foot of an
unhatchable entrance while the alert holds for a weak marked animal; the cap waits a little while one presses a
citizen. No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_danger_marks import FakeGame, Quiet, fort, plain_runner, ChunkGame  # noqa: E402
from overseer import harness  # noqa: E402

# the record's own numbers (cx5d8cf68 hint hard MY1-4, harness-4.api.jsonl lines 340-352)
CHILD_IN = {"id": 361, "name": "Mörul Tadalåth, Dwarven Child", "profession": "Dwarven Child", "adult": False,
            "x": 104, "y": 100, "z": 168}
CHILD_OUT = dict(CHILD_IN, x=117, y=99, z=169)
MINER = {"id": 95, "name": "Solon Onolem, Miner", "profession": "Miner", "x": 105, "y": 100, "z": 168}
KEA_BY_CHILD = {"id": 351, "race": "BIRD_KEA", "hostile": False, "x": 117, "y": 98, "z": 169}
KEA_OVER_FORT = {"id": 346, "race": "BIRD_KEA", "hostile": False, "x": 101, "y": 105, "z": 169}
FIGHT = ["The kea snatches at the dwarven child in the head with his first toe, left foot, tearing the fat!",
         "The kea bites the dwarven child in the head, denting the fat and bruising the muscle!"]
SQUAD_HALF = {"id": 0, "armed": 2, "uniform": "weapon+armor", "orders": [], "members": [{"id": i} for i in range(4)]}
SQUAD_ONE = dict(SQUAD_HALF, armed=1)
SHELTER = {"id": 0, "civ_alert_burrow": True, "name": "Shelter", "citizens_inside": 2}
E1 = {"id": "E1", "kind": "E", "x": 100, "y": 101, "z": 169, "w": 1, "h": 1, "building": True}
E2 = {"id": "E2", "kind": "E", "x": 97, "y": 91, "z": 169, "w": 1, "h": 1, "building": False}
HATCH = {"id": 67, "kind": "hatch", "built": True, "locked": False, "x": 97, "y": 91, "z": 169}


def my14(day, dwarves, alert=True, events=(), squads=(SQUAD_HALF,), sites=(E1, E2), doors=(HATCH,)):
    r = fort(day, alert=alert, events=events, dwarves=dwarves, squads=squads)
    o = r["observation"]
    o["administrators"]["citizens"] = len(dwarves)
    o["map"]["surface_z"] = 169
    o["map"]["sites"] = [dict(s) for s in sites]
    o["doors"] = {"list": [dict(x) for x in doors], "hatch_cover_items_free": 0, "door_items_free": 0}
    o["burrows"]["list"] = [dict(SHELTER, citizens_inside=sum(1 for x in dwarves if x["z"] < 169))]
    return r


class Look(Quiet):
    def look(self, ov, game, resp):
        ov.load(resp)
        ov.count = 0
        game.calls.clear()
        ov.defend()
        ov.wildlife_response()
        ov.mark_guard()
        ov.entrance_hatches()
        return [(t, a) for t, a in game.calls if t in ("civilian_alert", "squad_order")]


class Signs(Look):
    def test_the_childs_attack_is_a_new_sign_for_the_chunk_look(self):
        game = FakeGame([KEA_OVER_FORT])
        ov = harness.Overseer(game, days=216)
        day93 = set(ov.danger_signs(my14(93, [CHILD_IN, MINER]), query=False))
        self.assertNotIn("exposed:kea", day93)   # everyone sheltered on z168
        self.assertNotIn("fight:kea", day93)
        game.units = [KEA_BY_CHILD]
        day94 = set(ov.danger_signs(my14(94, [CHILD_OUT, MINER], events=FIGHT), query=True))
        self.assertIn("exposed:kea", day94 - day93)
        self.assertIn("fight:kea", day94 - day93)

    def test_the_chunked_advance_stops_on_it(self):
        game = FakeGame([KEA_OVER_FORT])
        ov = harness.Overseer(game, days=216)
        ov.risk = ov.danger_signs(my14(93, [CHILD_IN, MINER]), query=False)
        cg = ChunkGame()
        looks = iter([my14(94, [CHILD_OUT, MINER], events=FIGHT)])
        cg.observe = lambda: next(looks)
        game.units = [KEA_BY_CHILD]
        runner = plain_runner(cg, ov)
        resp = runner.chunked({"days": 7})
        self.assertEqual(resp["result"]["stopped"]["reason"], "danger_sign")
        self.assertIn("fight:kea", resp["result"]["stopped"]["detail"])


class Rescue(Look):
    def test_a_half_armed_squad_is_stationed_on_the_child(self):
        game = FakeGame([KEA_BY_CHILD])
        ov = harness.Overseer(game, days=216)
        calls = self.look(ov, game, my14(94, [CHILD_OUT, MINER], events=FIGHT))
        self.assertIn(("squad_order", {"order": "station", "x": 117, "y": 99, "z": 169}), calls)
        self.assertIsNotNone(ov.mark_station)

    def test_one_armed_soldier_is_not_sent(self):
        game = FakeGame([KEA_BY_CHILD])
        ov = harness.Overseer(game, days=216)
        calls = self.look(ov, game, my14(94, [CHILD_OUT, MINER], events=FIGHT, squads=(SQUAD_ONE,)))
        self.assertFalse([c for c in calls if c[0] == "squad_order"])

    def test_a_kea_over_a_sheltered_fort_with_no_fight_sends_no_rescue(self):
        game = FakeGame([KEA_OVER_FORT])
        ov = harness.Overseer(game, days=216)
        calls = self.look(ov, game, my14(93, [CHILD_IN, MINER], sites=(E2,)))   # every entrance hatched
        self.assertFalse([c for c in calls if c[0] == "squad_order"])


class Gate(Look):
    def test_the_unhatchable_entrance_is_guarded_while_the_alert_holds(self):
        game = FakeGame([KEA_OVER_FORT])
        ov = harness.Overseer(game, days=216)
        calls = self.look(ov, game, my14(93, [CHILD_IN, MINER]))
        self.assertEqual(ov.open_entrances(), [(100, 101, 169)])
        self.assertIn(("squad_order", {"order": "station", "x": 100, "y": 101, "z": 169}), calls)   # SHAFT_GUARD_TOP: the stair top

    def test_no_alert_no_gate(self):
        game = FakeGame([KEA_OVER_FORT])
        ov = harness.Overseer(game, days=216)
        ov.wild_rest_until = 10 ** 9   # resting: no alert sounds this pass
        calls = self.look(ov, game, my14(93, [CHILD_IN, MINER], alert=False))
        self.assertFalse([c for c in calls if c[0] == "squad_order"])

    def test_a_refused_top_falls_back_to_the_stair_foot(self):
        game = FakeGame([KEA_OVER_FORT])
        refuse = {"n": 0}
        base = game.act

        def act(tool, args):
            if tool == "squad_order" and args.get("z") == 169 and refuse["n"] == 0:
                refuse["n"] += 1
                game.calls.append((tool, dict(args)))
                return {"ok": False, "error_code": "not_walkable"}
            return base(tool, args)
        game.act = act
        ov = harness.Overseer(game, days=216)
        self.look(ov, game, my14(93, [CHILD_IN, MINER]))
        calls = self.look(ov, game, my14(94, [CHILD_IN, MINER]))
        self.assertIn(("squad_order", {"order": "station", "x": 100, "y": 101, "z": 168}), calls)

    def test_shaft_guard_top_false_keeps_the_foot_first(self):
        game = FakeGame([KEA_OVER_FORT])
        ov = harness.Overseer(game, days=216)
        old = harness.SHAFT_GUARD_TOP
        harness.SHAFT_GUARD_TOP = False
        try:
            calls = self.look(ov, game, my14(93, [CHILD_IN, MINER]))
        finally:
            harness.SHAFT_GUARD_TOP = old
        self.assertIn(("squad_order", {"order": "station", "x": 100, "y": 101, "z": 168}), calls)
        self.assertNotIn(("squad_order", {"order": "station", "x": 100, "y": 101, "z": 169}), calls)

    def test_tile_occupied_marks_the_entrance_open(self):
        game = FakeGame([])
        base = game.act
        game.act = lambda tool, args: ({"ok": False, "error_code": "tile_occupied"} if tool == "build_door"
                                       else base(tool, args))
        ov = harness.Overseer(game, days=216)
        plain_e1 = dict(E1, building=False)
        r = my14(14, [CHILD_IN, MINER], alert=False, sites=(plain_e1,), doors=())
        r["observation"]["doors"]["hatch_cover_items_free"] = 1
        self.look(ov, game, r)
        self.assertIn("E1", ov.entrance_occupied)
        self.assertEqual(ov.open_entrances(), [(100, 101, 169)])


class Cap(Look):
    def test_the_cap_waits_while_a_kea_is_at_a_citizens_side_then_lifts(self):
        game = FakeGame([KEA_OVER_FORT])
        ov = harness.Overseer(game, days=216)
        self.look(ov, game, my14(0, [CHILD_IN, MINER], squads=()))
        ov.alert_since = 0
        ov.wild_alert_on(now=0)   # this layer's kea alert, as on day 86 of the record
        ov.wild_watch["kea"] = 0
        calls = self.look(ov, game, my14(11, [CHILD_IN, MINER], squads=()))
        self.assertNotIn(("civilian_alert", {"on": False}), calls)   # kea 5 tiles from the sheltered child
        calls = self.look(ov, game, my14(14, [CHILD_IN, MINER], squads=()))
        self.assertIn(("civilian_alert", {"on": False}), calls)      # past 10 + CAP_DEFER_DAYS: lifted anyway

    def test_the_cap_lifts_on_time_with_the_animal_far_from_everyone(self):
        game = FakeGame([dict(KEA_OVER_FORT, x=125, y=125)])
        ov = harness.Overseer(game, days=216)
        self.look(ov, game, my14(0, [CHILD_IN, MINER], squads=()))
        ov.alert_since = 0
        calls = self.look(ov, game, my14(11, [CHILD_IN, MINER], squads=()))
        self.assertIn(("civilian_alert", {"on": False}), calls)


if __name__ == "__main__":
    unittest.main()
