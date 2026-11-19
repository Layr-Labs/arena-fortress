"""Unit tests for open-play survival, housing, office, and grazing fixes (cand-winner)."""
import unittest

from support import DAY, StubGame, bare, overseer, resp, threat_resp
from overseer.harness import Overseer
from plain.harness import Plain


class CitizenGame(StubGame):
    def __init__(self, citizens, **kw):
        super().__init__(**kw)
        self.citizens = citizens
        self.custom_acts = {}

    def query(self, name, **kw):
        if name == "units" and kw.get("kind") == "citizens":
            self.queries += 1
            return {"result": {"units": [dict(u) for u in self.citizens], "total": len(self.citizens)}}
        return super().query(name, **kw)

    def act(self, tool, args):
        fn = self.custom_acts.get(tool)
        if fn is not None:
            self.calls.append((tool, dict(args)))
            return fn(args)
        return super().act(tool, args)


class FisherHoldTests(unittest.TestCase):
    def test_day0_fisher_stationed_and_released_when_fish_labor_gone(self):
        cits = [
            {"id": 80, "adult": True, "labors": ["MINE"], "positions": []},
            {"id": 83, "adult": True, "labors": ["FISH", "HAUL"], "positions": []},
        ]
        g = CitizenGame(cits)
        ov = Overseer(g, goal="Run the fortress", days=336)
        ov.set_task({"goal": "Run the fortress for 336 days."})
        r0 = bare(336, 0, fishing=False, cit=2)
        r0["observation"]["administrators"]["manager_active_for_orders"] = False
        r0["observation"]["dwarves"] = [{"id": 83, "adult": True, "organizer_skill": 5},
                                        {"id": 80, "adult": True, "organizer_skill": 1}]
        r0["observation"]["map"]["wagon"] = {"x": 95, "y": 95, "z": 151}
        ov.load(r0)
        ov.count = 0
        ov.management()
        # Manager must skip the fisherdwarf (id 83) and pick id 80
        self.assertEqual(g.tools("appoint_manager"), [{"dwarf_id": 80}])
        # Squad created for fisher and stationed at wagon
        self.assertEqual(g.tools("create_squad"), [{"dwarf_ids": [83]}])
        self.assertEqual(g.tools("squad_order"), [{"order": "station", "x": 95, "y": 95, "z": 151}])
        self.assertIsInstance(ov.fisher_hold, dict)
        self.assertEqual(ov.step_days(), 1)

        # defend() on Day 0 must NOT stand down the stationed fisherdwarf
        r0["observation"]["military"] = {"squads": [{"id": 1, "orders": [{"type": "Move"}], "armed": 0}]}
        ov.load(r0)
        ov.defend()
        self.assertEqual(g.tools("squad_order"), [{"order": "station", "x": 95, "y": 95, "z": 151}])

        # On Day 1, autolabor removed FISH -> stand_down
        g.citizens[1]["labors"] = ["HAUL"]
        r1 = bare(335, 1, fishing=False, cit=2)
        r1["observation"]["map"]["wagon"] = {"x": 95, "y": 95, "z": 151}
        ov.load(r1)
        ov.management()
        self.assertEqual(g.tools("squad_order")[-1], {"order": "stand_down"})
        self.assertFalse(ov.fisher_hold)

    def test_plain_refuses_squad_order_during_fisher_hold(self):
        class FakeTask:
            task = {"goal": "Run the fortress", "days": 336}
            days = 336
            credits = 0.5
        g = StubGame()
        p = Plain(FakeTask(), g, None)
        p.guard.fisher_hold = {"since": 0, "ids": [83]}
        ref = p.refuse("squad_order", {"order": "stand_down"}, 100)
        self.assertIsNotNone(ref)
        self.assertEqual(ref["error_code"], "layer_owned")


class TargetedAttackTests(unittest.TestCase):
    def test_open_play_only_attacks_invaders_with_target_ids(self):
        r = threat_resp(100, dist=40, n=2, invader=False)
        r["observation"]["military"] = {"squads": [{"id": 1, "armed": 2, "orders": [], "uniform": "leather"}]}
        ov, g = overseer(r)
        ov.wild_off = True
        ov.defend()
        self.assertEqual(g.tools("squad_order"), [])

        r2 = threat_resp(101, dist=40, n=2, invader=True)
        r2["observation"]["military"] = {"squads": [{"id": 1, "armed": 2, "orders": [], "uniform": "leather"}]}
        ov.load(r2)
        ov.defend()
        self.assertEqual(g.tools("squad_order"), [{"order": "attack", "target_ids": [900, 901]}])


class OfficeAndHousingTests(unittest.TestCase):
    def test_office_starts_at_cit7_skips_oversized_and_farm_sites_and_reserves_chair(self):
        r = resp(300, 36, food=40, drink=100, cit=7)
        o = r["observation"]
        o["administrators"]["MANAGER_id"] = 1
        o["stocks"]["furniture_free"] = {"chair": 1, "table": 1}
        o["farm_plots"] = [{"x": 10, "y": 10, "z": 149, "w": 3, "h": 3}]
        o["map"]["sites"] = [
            {"id": "A1", "kind": "A", "x": 0, "y": 0, "z": 150, "w": 25, "h": 25, "open_tiles": 100},  # >20x20
            {"id": "R1", "kind": "R", "x": 10, "y": 10, "z": 149, "w": 3, "h": 3, "dug": True},       # overlaps farm
            {"id": "R2", "kind": "R", "x": 20, "y": 20, "z": 149, "w": 3, "h": 3, "dug": True},       # valid office!
            {"id": "A2", "kind": "A", "x": 30, "y": 30, "z": 148, "w": 10, "h": 10, "open_tiles": 40},
        ]
        ov, g = overseer(r)
        ov.roles["R2"] = "office"
        ov.office()
        self.assertEqual(g.tools("make_zone"), [{"kind": "office", "site": "R2"}])
        self.assertEqual(g.tools("place_furniture"), [{"kind": "chair", "site": "R2"}])

    def test_furnish_reserves_last_free_chair_for_office(self):
        r = resp(300, 36, food=40, drink=100, cit=7)
        o = r["observation"]
        o["administrators"]["MANAGER_id"] = 1
        o["stocks"]["furniture_free"] = {"chair": 1, "table": 1}
        o["map"]["sites"] = [{"id": "A1", "kind": "A", "x": 10, "y": 10, "z": 149, "w": 8, "h": 8, "open_tiles": 30}]
        ov, g = overseer(r)
        ov.furnish()
        kinds = [a["kind"] for a in g.tools("place_furniture")]
        self.assertIn("table", kinds)
        self.assertNotIn("chair", kinds)

    def test_bed_placement_skips_over40_and_overflows_on_partial(self):
        r = resp(200, 136, food=40, drink=100, cit=20)
        o = r["observation"]
        o["stocks"]["furniture_free"] = {"bed": 10}
        o["map"]["sites"] = [
            {"id": "A1", "kind": "A", "x": 0, "y": 0, "z": 150, "w": 45, "h": 12, "open_tiles": 200},  # >40 wide!
            {"id": "R1", "kind": "R", "x": 5, "y": 5, "z": 150, "w": 9, "h": 7, "dug": True},          # valid dorm R
            {"id": "A2", "kind": "A", "x": 5, "y": 5, "z": 149, "w": 12, "h": 12, "open_tiles": 60},   # overflow A
        ]
        g = CitizenGame([])
        def fake_place(args):
            if args["site"] == "R1":
                return {"ok": True, "result": {"at": [[5, 5, 150], [6, 5, 150], [7, 5, 150], [8, 5, 150]]}}
            return {"ok": True, "result": {"at": [[5 + i, 5, 149] for i in range(args["count"])]}}
        g.custom_acts["place_furniture"] = fake_place
        ov = Overseer(g, goal="Run the fortress", days=336)
        ov.set_task({"goal": "Run the fortress for 336 days."})
        ov.roles["R1"] = "dorm"
        ov.load(r)
        ov.count = 0
        ov.furnish()
        beds = [a for a in g.tools("place_furniture") if a["kind"] == "bed"]
        self.assertEqual(beds, [{"kind": "bed", "site": "R1", "count": 10},
                                {"kind": "bed", "site": "A2", "count": 6}])
        zones = [a["site"] for a in g.tools("make_zone") if a["kind"] == "dormitory"]
        self.assertIn("R1", zones)
        self.assertIn("A2", zones)


class GrazerAndReserveCullTests(unittest.TestCase):
    def test_hunger_cull_keeps_non_grazers_and_culls_grazers_first(self):
        herd = [
            {"id": 1, "race": "COW", "tame": True, "adult": True, "pet_owner_id": -1},          # grazer (60)
            {"id": 2, "race": "PIG", "tame": True, "adult": True, "pet_owner_id": -1},          # non-grazer (10)
            {"id": 3, "race": "DOG", "tame": True, "adult": True, "pet_owner_id": -1},          # non-grazer (3)
            {"id": 4, "race": "BIRD_TURKEY", "tame": True, "adult": True, "pet_owner_id": -1},  # non-grazer (1.5)
            {"id": 5, "race": "BIRD_GOOSE", "tame": True, "adult": True, "pet_owner_id": -1},   # non-grazer (1.3)
        ]
        ov, g = overseer(resp(150, 186, food=2, drink=100, cit=10), herd=herd)
        ov.cull("hunger", 1, smallest=True, retry=8)
        # Non-grazers PIG, DOG, TURKEY are protected in FEAST_KEEP=3; COW (grazer) is culled before GOOSE!
        self.assertEqual(g.tools("slaughter"), [{"unit_id": 1}])


class WealthEngineTests(unittest.TestCase):
    def test_wheelbarrow_wealth_engine_waits_for_hatches_then_runs_and_cancels(self):
        r = resp(316, 20, food=40, drink=100, cit=7, workshops=("Carpenters", "Carpenters", "Still", "Kitchen"))
        r["observation"]["stocks"]["logs_usable"] = 60
        r["observation"]["stocks"]["beds"] = 10
        r["observation"]["stocks"]["tables"] = 5
        r["observation"]["stocks"]["chairs"] = 6
        r["observation"]["wealth"] = {"created": 2000}
        r["observation"]["map"]["sites"] = [{"id": "E1", "kind": "E", "x": 92, "y": 100, "z": 153}]
        r["observation"]["doors"] = {"list": []}  # stair hatch NOT built yet!
        ov, g = overseer(r)
        ov.progression_push()
        self.assertEqual(g.tools("add_manager_order"), [])  # must wait for surface hatches!

        # Once stair hatch is built (sealed), Wheelbarrows & Minecarts start cleanly
        r["observation"]["doors"] = {"list": [{"id": 14, "kind": "hatch", "built": True, "locked": False, "x": 92, "y": 100, "z": 153}]}
        ov.load(r)
        ov.progression_push()
        orders = g.tools("add_manager_order")
        subs = [o.get("item_subtype") for o in orders]
        self.assertEqual(subs, ["ITEM_TOOL_WHEELBARROW", "ITEM_TOOL_MINECART"])
        self.assertTrue(len(ov.wealth_ids) == 2)

        # Pause if chairs fall short after migrants arrive
        oids = sorted(ov.wealth_ids)
        r_short = resp(200, 136, food=40, drink=200, cit=14, workshops=("Carpenters", "Carpenters", "Still", "Kitchen"),
                       orders=[{"id": i, "job": "MakeTool", "repeat": "daily"} for i in oids])
        r_short["observation"]["map"]["sites"] = [{"id": "E1", "kind": "E", "x": 92, "y": 100, "z": 153}]
        r_short["observation"]["doors"] = {"list": [{"id": 14, "kind": "hatch", "built": True, "locked": False, "x": 92, "y": 100, "z": 153}]}
        r_short["observation"]["stocks"]["beds"] = 14
        r_short["observation"]["stocks"]["tables"] = 7
        r_short["observation"]["stocks"]["chairs"] = 6  # needs 8!
        r_short["observation"]["wealth"] = {"created": 12000}
        ov.load(r_short)
        ov.progression_push()
        self.assertEqual([a["order_id"] for a in g.tools("cancel_order")], oids)

        # Caravan departs -> stays cancelled
        r2 = resp(140, 196, food=40, drink=200, cit=14, workshops=("Carpenters", "Carpenters", "Still", "Kitchen"),
                  orders=[])
        r2["observation"]["map"]["sites"] = [{"id": "E1", "kind": "E", "x": 92, "y": 100, "z": 153}]
        r2["observation"]["doors"] = {"list": [{"id": 14, "kind": "hatch", "built": True, "locked": False, "x": 92, "y": 100, "z": 153}]}
        r2["observation"]["stocks"]["beds"] = 14
        r2["observation"]["stocks"]["tables"] = 8
        r2["observation"]["stocks"]["chairs"] = 9
        r2["observation"]["wealth"] = {"created": 28000}
        r2["observation"]["recent_events"] = ["The merchants have embarked on their journey."]
        ov.load(r2)
        ov.progression_push()
        self.assertTrue(ov.caravan_out)
        self.assertEqual(len(g.tools("add_manager_order")), 2)  # no new wealth orders after caravan leaves

    def test_extra_carpenters_capped_at_three_builds(self):
        r = resp(316, 20, food=40, drink=100, cit=7, workshops=("Carpenters", "Still", "Kitchen"))
        r["observation"]["stocks"]["logs_usable"] = 60
        r["observation"]["stocks"]["beds"] = 10
        r["observation"]["stocks"]["tables"] = 5
        r["observation"]["stocks"]["chairs"] = 6
        r["observation"]["wealth"] = {"created": 2000}
        r["observation"]["map"]["sites"] = [
            {"id": "E1", "kind": "E", "x": 92, "y": 100, "z": 153},
            {"id": "W2", "kind": "W"},
        ]
        r["observation"]["doors"] = {"list": [{"id": 14, "kind": "hatch", "built": True, "locked": False, "x": 92, "y": 100, "z": 153}]}
        ov, g = overseer(r)
        ov.built_n["Carpenters"] = 3
        ov.progression_push()
        self.assertEqual(g.tools("build_workshop"), [])

    def test_urgent_final_stretch_cull_marks_two_animals(self):
        herd = [
            {"id": i, "race": "PIG", "tame": True, "adult": True, "pet_owner_id": -1}
            for i in range(1, 9)
        ]
        ov, g = overseer(resp(22, 314, food=4, drink=300, cit=18), herd=herd)
        ov.provision()
        self.assertEqual(len(g.tools("slaughter")), 2)


if __name__ == "__main__":
    unittest.main()
