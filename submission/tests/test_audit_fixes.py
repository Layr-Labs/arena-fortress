"""cx audit fixes (2026-11-10 rule-layer audit over the hint records). Each case is the record's own shape:
- a station on a resident weak animal stands down without fresh evidence and is not re-sent on the same species
  (cxd769d66 hint std MY1-4: 4 soldiers stationed on a resident kea days 70-110);
- the open-shaft guard comes ahead of the station on the animal while the alert holds (MY1-4: no D site ever listed;
  build_door/build_wall take a listed site only);
- a room a farm plot took loses its people role and is not offered again (d56d5b8 hint hard MY1-2: "room R3 is
  already used (farm plot 64)" 26 times);
- the office does not take the dug dine room (4e5f701 / 9fcba39 / 5c4cf96 MY1: z_dine "already used (Office 65)");
- only a dig job's own cancel is a wet dig ("cancels Give Water: Need empty bucket." matched 241 times);
- an entrance with another building on its stair is not retried and spends no free hatch cover;
- the plain loop no longer offers the layer-owned tools to the model, and still answers them with layer_owned.
No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_danger_marks import FakeGame, Quiet, fort, SQUAD_READY  # noqa: E402
from test_rescue_station import my14, CHILD_IN, MINER, KEA_OVER_FORT, SQUAD_HALF  # noqa: E402
from overseer import harness  # noqa: E402
from plain import harness as plain  # noqa: E402

KEA_RESIDENT = {"id": 272, "race": "BIRD_KEA", "hostile": False, "x": 100, "y": 105, "z": 169}
STATION = ("squad_order", {"order": "station", "x": 100, "y": 105, "z": 169})
STAND_DOWN = ("squad_order", {"order": "stand_down"})


class StationHold(Quiet):
    def look(self, ov, game, day, evidence=False, **kw):
        ov.load(fort(day, **kw))
        if evidence:
            ov.wild_evidence["kea"] = ov.now   # a citizen fight / interrupt with the species this look
        ov.count = 0
        game.calls.clear()
        ov.mark_guard()
        return [(t, a) for t, a in game.calls if t == "squad_order"]

    def test_a_resident_kea_is_stood_down_after_the_hold_and_not_re_sent(self):
        game = FakeGame([KEA_RESIDENT])
        ov = harness.Overseer(game, days=216)
        ov.count = 0
        self.assertIn(STATION, self.look(ov, game, 68, squads=[SQUAD_READY]))
        busy = [dict(SQUAD_READY, orders=[{"order": "station"}])]
        self.assertNotIn(STAND_DOWN, self.look(ov, game, 70, alert=True, squads=busy))   # inside the hold
        self.assertIn(STAND_DOWN, self.look(ov, game, 72, squads=busy))                  # no evidence since day 68
        self.assertIsNone(ov.mark_station)
        self.assertEqual(self.look(ov, game, 74, squads=[SQUAD_READY]), [])              # settled: not re-sent
        self.assertEqual(self.look(ov, game, 80, squads=[SQUAD_READY]), [])

    def test_fresh_evidence_sends_and_holds_the_station(self):
        game = FakeGame([KEA_RESIDENT])
        ov = harness.Overseer(game, days=216)
        ov.count = 0
        self.look(ov, game, 68, squads=[SQUAD_READY])
        busy = [dict(SQUAD_READY, orders=[{"order": "station"}])]
        self.look(ov, game, 72, squads=busy)                                            # stood down, settled
        self.assertIn(STATION, self.look(ov, game, 76, evidence=True, squads=[SQUAD_READY]))
        self.assertNotIn(STAND_DOWN, self.look(ov, game, 78, evidence=True, squads=busy))   # evidence holds it

    def test_an_animal_gone_past_range_still_stands_the_squad_down_at_once(self):
        game = FakeGame([KEA_RESIDENT])
        ov = harness.Overseer(game, days=216)
        ov.count = 0
        self.look(ov, game, 68, squads=[SQUAD_READY])
        game.units = [dict(KEA_RESIDENT, x=10, y=10)]
        busy = [dict(SQUAD_READY, orders=[{"order": "station"}])]
        self.assertIn(STAND_DOWN, self.look(ov, game, 69, squads=busy))


class OpenShaftFirst(Quiet):
    def test_a_ready_squad_guards_the_open_shaft_not_the_animal_while_the_alert_holds(self):
        game = FakeGame([KEA_OVER_FORT])
        ov = harness.Overseer(game, days=216)
        ov.count = 0
        ov.load(my14(93, [CHILD_IN, MINER], squads=(dict(SQUAD_HALF, armed=4),)))
        game.calls.clear()
        ov.mark_guard()
        orders = [a for t, a in game.calls if t == "squad_order"]
        self.assertEqual(orders, [{"order": "station", "x": 100, "y": 101, "z": 169}])   # E1's top (SHAFT_GUARD_TOP)

    def test_build_door_takes_only_a_listed_site(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from gameapi.facts import tools as T   # the frozen tool rules the open-shaft fallback rests on
        self.assertEqual(T.SITE_KINDS["build_door"], ("E", "D"))
        self.assertEqual(T.SITE_KINDS["build_wall"], ("D",))
        door = next(t for t in T.tool_schemas() if t["function"]["name"] == "build_door")["function"]
        self.assertIn("site", door["parameters"]["required"])
        self.assertNotIn("x", door["parameters"]["properties"])


def obs(day, sites, roles_dug=(), zones=(), citizens=15, chairs=4):
    o = fort(day)
    ob = o["observation"]
    ob["map"]["sites"] = [dict(s) for s in sites]
    ob["zones"] = [dict(z) for z in zones]
    ob["administrators"] = {"citizens": citizens, "manager_active_for_orders": True, "MANAGER_id": 7,
                            "manager_office": "none"}
    ob["stocks"]["furniture_free"] = {"chair": chairs, "table": 4, "bed": 4}
    return o


R3 = {"id": "R3", "kind": "R", "x": 100, "y": 95, "z": 167, "w": 7, "h": 5, "soil": False, "designated": True,
      "dug": True, "free": True}
A1 = {"id": "A1", "kind": "A", "x": 95, "y": 100, "z": 168, "w": 12, "h": 3, "open_tiles": 34, "soil": None,
      "designated": None, "dug": None, "free": True}


class PlotRoom(Quiet):
    def test_a_plot_refusal_drops_the_role_and_the_room_is_not_offered_again(self):
        class Game(FakeGame):
            def act(self, tool, args):
                self.calls.append((tool, dict(args)))
                if args.get("site") == "R3":
                    return {"ok": False, "error_code": "site_used", "error": "room R3 is already used (farm plot 64)"}
                return {"ok": True, "result": {}}
        game = Game()
        ov = harness.Overseer(game, days=216)
        ov.count = 0
        ov.load(obs(100, [R3]))
        ov.roles = {"R3": "dine"}
        ov.furnish()
        self.assertEqual([a["site"] for t, a in game.calls if t == "place_furniture"], ["R3"])
        self.assertNotIn("R3", ov.roles)
        self.assertIn("R3", ov.plot_rooms)
        game.calls.clear()
        ov.load(obs(102, [R3]))
        ov.furnish()
        ov.farms()
        self.assertFalse([a for t, a in game.calls if a.get("site") == "R3"])


class Office(Quiet):
    def test_the_office_takes_an_a_site_not_the_dine_room(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        ov.count = 0
        ov.load(obs(100, [R3, A1]))
        ov.roles = {"R3": "dine"}
        ov.office()
        self.assertEqual([a for t, a in game.calls if t == "make_zone"], [{"kind": "office", "site": "A1"}])

    def test_the_dine_room_only_once_a_dining_zone_stands(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        ov.count = 0
        ov.load(obs(100, [R3]))
        ov.roles = {"R3": "dine"}
        ov.office()
        self.assertEqual([a for t, a in game.calls if t == "make_zone"], [])
        ov.load(obs(101, [R3], zones=[{"id": 9, "type": "DiningHall", "x": 80, "y": 80, "z": 167, "w": 5, "h": 5}]))
        ov.office()
        self.assertEqual([a for t, a in game.calls if t == "make_zone"], [{"kind": "office", "site": "R3"}])


class WetText(Quiet):
    def test_only_a_dig_cancel_is_a_wet_dig(self):
        ov = harness.Overseer(FakeGame(), days=216)
        ov.count = 0
        for text in ("Urist cancels Give Water: Need empty bucket.", "Urist cancels Give Water: No water source.",
                     "Urist cancels Drink: Water source contaminated.", "Urist cancels Drink: Water source vanished."):
            ov.load(fort(10, cancels=[text]))
            self.assertFalse(ov.water_texts()[1], text)
        ov.load(fort(11, cancels=["Urist cancels Dig: Damp stone located."]))
        self.assertTrue(ov.water_texts()[1])


class BlockedEntrance(Quiet):
    def test_a_built_on_stair_is_not_retried_and_spends_no_hatch_cover(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        ov.count = 0
        e1 = {"id": "E1", "kind": "E", "x": 100, "y": 101, "z": 169, "w": 1, "h": 1, "building": True}
        e2 = {"id": "E2", "kind": "E", "x": 97, "y": 91, "z": 169, "w": 1, "h": 1, "building": False}
        r = my14(16, [CHILD_IN, MINER], alert=False, sites=(e1, e2), doors=())
        r["observation"]["doors"]["hatch_cover_items_free"] = 1
        ov.load(r)
        game.calls.clear()
        ov.entrance_hatches()
        self.assertEqual([a for t, a in game.calls if t == "build_door"], [{"kind": "hatch", "site": "E2"}])
        self.assertIn("E1", ov.entrance_occupied)
        self.assertEqual(ov.open_entrances(), [(100, 101, 169)])


class LayerTools(unittest.TestCase):
    def test_the_layer_owned_tools_are_not_offered(self):
        tools = [{"type": "function", "function": {"name": n, "parameters": {}}}
                 for n in ("civilian_alert", "lock_door", "build_door", "advance_days")]
        names = [t["function"]["name"] for t in plain.prepare_tools(tools)]
        self.assertEqual(names, ["build_door", "advance_days"])


if __name__ == "__main__":
    unittest.main()
