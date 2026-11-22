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
    def test_tool_wealth_engine_waits_for_hatches_then_runs_and_cancels(self):
        r = resp(316, 20, food=40, drink=100, cit=7, workshops=("Carpenters", "Carpenters", "Carpenters", "Still", "Kitchen"))
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

        # Once stair hatch is built (sealed), Wheelbarrow + Minecart + Stepladder start cleanly
        r["observation"]["doors"] = {"list": [{"id": 14, "kind": "hatch", "built": True, "locked": False, "x": 92, "y": 100, "z": 153}]}
        ov.load(r)
        ov.progression_push()
        orders = g.tools("add_manager_order")
        self.assertEqual([o.get("item_subtype") for o in orders],
                         ["ITEM_TOOL_WHEELBARROW", "ITEM_TOOL_MINECART", "ITEM_TOOL_STEPLADDER"])
        self.assertEqual(len(ov.wealth_ids), 3)

        # Pause if chairs fall short after migrants arrive
        oids = sorted(ov.wealth_ids)
        r_short = resp(200, 136, food=40, drink=200, cit=14, workshops=("Carpenters", "Carpenters", "Carpenters", "Still", "Kitchen"),
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

        # Real DF 53.16 caravan departure message ("from <Civ>") -> stays cancelled
        r2 = resp(140, 196, food=40, drink=200, cit=14, workshops=("Carpenters", "Carpenters", "Carpenters", "Still", "Kitchen"),
                  orders=[])
        r2["observation"]["map"]["sites"] = [{"id": "E1", "kind": "E", "x": 92, "y": 100, "z": 153}]
        r2["observation"]["doors"] = {"list": [{"id": 14, "kind": "hatch", "built": True, "locked": False, "x": 92, "y": 100, "z": 153}]}
        r2["observation"]["stocks"]["beds"] = 14
        r2["observation"]["stocks"]["tables"] = 8
        r2["observation"]["stocks"]["chairs"] = 9
        r2["observation"]["wealth"] = {"created": 28000}
        r2["observation"]["recent_events"] = ["The merchants from Shorast Mezum have embarked on their journey."]
        ov.load(r2)
        ov.progression_push()
        self.assertTrue(ov.caravan_out)
        self.assertEqual(len(g.tools("add_manager_order")), 3)  # no new wealth orders after caravan leaves

    def test_extra_carpenters_reserve_w_sites_for_butchers_and_cap_at_five(self):
        r = resp(316, 20, food=40, drink=100, cit=7, workshops=("Carpenters", "Still", "Kitchen"))
        r["observation"]["stocks"]["logs_usable"] = 60
        r["observation"]["stocks"]["beds"] = 10
        r["observation"]["stocks"]["tables"] = 5
        r["observation"]["stocks"]["chairs"] = 6
        r["observation"]["wealth"] = {"created": 2000}
        r["observation"]["map"]["sites"] = [
            {"id": "E1", "kind": "E", "x": 92, "y": 100, "z": 153},
            {"id": "W2", "kind": "W"},
            {"id": "W3", "kind": "W"},  # only 2 free W sites -> both reserved for Butchers!
        ]
        r["observation"]["doors"] = {"list": [{"id": 14, "kind": "hatch", "built": True, "locked": False, "x": 92, "y": 100, "z": 153}]}
        ov, g = overseer(r)
        ov.progression_push()
        self.assertEqual(g.tools("build_workshop"), [])

        # With a 3rd free W site, builds Carpenters #2 cleanly
        r["observation"]["map"]["sites"].append({"id": "W4", "kind": "W"})
        ov.load(r)
        ov.progression_push()
        self.assertEqual(g.tools("build_workshop"), [{"type": "Carpenters", "site": "W2"}])

    def test_snapping_turtle_in_beasts_and_lurkers(self):
        from overseer.beasts import BEASTS, LURKERS
        self.assertIn("SNAPPING TURTLE", BEASTS)
        self.assertIn("SNAPPING TURTLE", LURKERS)

    def test_lockdown_waits_for_last_dwarf_unless_threat_at_hatch(self):
        # 5 of 6 indoors on full-year OP1, threat 20 tiles away -> do NOT lock hatch on tick 0
        r = threat_resp(116, dist=26, n=2, invader=False, inside=5, cit=6)
        r["observation"]["threats"]["hostiles"][0].update({"x": 115, "y": 100, "z": 153})
        r["observation"]["threats"]["hostiles"][1].update({"x": 116, "y": 100, "z": 153})
        ov, g = overseer(r)
        ov.days = 336
        ov.wildlife(False, open_play=True)
        self.assertEqual(g.tools("civilian_alert"), [{"on": True}])
        self.assertEqual(g.tools("lock_door"), [])

        # Threat within 12 tiles of hatch (92, 100, 153) -> lock IMMEDIATELY even with 5 of 6 indoors
        r["observation"]["threats"]["hostiles"][0].update({"x": 98, "y": 100, "z": 153})
        ov.load(r)
        ov.wildlife(True, open_play=True)
        self.assertEqual(g.tools("lock_door"), [{"locked": True, "door_id": 14}])

        # On MY1 (days=168, not full_year), 5 of 6 indoors locks immediately (edc27809 behavior)
        r_my = threat_resp(116, dist=26, n=2, invader=False, inside=5, cit=6)
        r_my["observation"]["threats"]["hostiles"][0].update({"x": 115, "y": 100, "z": 153})
        r_my["observation"]["threats"]["hostiles"][1].update({"x": 116, "y": 100, "z": 153})
        ov_my, g_my = overseer(r_my)
        ov_my.days = 168
        ov_my.wildlife(False, open_play=True)
        self.assertEqual(g_my.tools("lock_door"), [{"locked": True, "door_id": 14}])

    def test_urgent_final_stretch_cull_marks_two_animals(self):
        herd = [
            {"id": i, "race": "PIG", "tame": True, "adult": True, "pet_owner_id": -1}
            for i in range(1, 9)
        ]
        ov, g = overseer(resp(22, 314, food=4, drink=300, cit=18), herd=herd)
        ov.provision()
        self.assertEqual(len(g.tools("slaughter")), 2)

    def test_no_model_routing_runs_layer_only_except_lt01_brew_in_window(self):
        from types import SimpleNamespace
        from plain.harness import Plain

        class FakeModel:
            def __init__(self):
                self.usage = {"cost_usd": 0.0}
                self.calls = 0

            def chat(self, messages, tools=None, **kw):
                self.calls += 1
                return {"choices": [{"message": {"role": "assistant", "tool_calls": [
                    {"id": "c1", "function": {"name": "advance_days", "arguments": "{\"days\": 1}"}}
                ]}}]}

        class FakeGame:
            def __init__(self, task_info):
                self.task_info = task_info
                self.last = None
                self.n = 0

            def task(self):
                return {"task": self.task_info, "tools": [{"function": {"name": "advance_days", "parameters": {"properties": {"days": {"maximum": 28}}}}}]}

            def observe(self):
                self.n += 1
                r = resp(10, self.n, food=50, drink=50, cit=10)
                if self.task_info.get("hands_off"):
                    r["hands_off_in_days"] = 10
                if self.n >= 2:
                    r["game_over"] = True
                self.last = r
                return r

            def act(self, tool, args):
                self.last = {"ok": True, "day": self.n, "tick": self.n * 1200, "game_over": True, "result": {}}
                return self.last

            def query(self, *a, **kw):
                return {"ok": True, "result": {"units": []}}

        cases = [
            ("OP1", {"name": "op1", "days": 336, "goal": "Grow a fortress."}, True),
            ("MY1", {"name": "my1", "days": 168, "goal": "Stabilize the fortress."}, True),
            ("LT02", {"name": "lt02", "days": 90, "hands_off": {"from_day": 69, "days": 21},
                      "goal": "Keep drink in stock every day of that window, with your own built Still."}, True),
            ("LT03", {"name": "lt03", "days": 45, "hands_off": {"from_day": 38, "days": 7},
                      "goal": "A dwarf has been taken by a strange mood. The artifact must be finished."}, True),
            ("LT08", {"name": "lt08", "days": 60, "hands_off": {"from_day": 39, "days": 21},
                      "goal": "Migrants are arriving. By day 60 every dwarf must have a placed bed, and drink must not end lower."}, True),
            ("LT01", {"name": "lt01", "days": 60, "hands_off": {"from_day": 39, "days": 21},
                      "goal": "From day 39 you can't act for 21 days. Keep drink in stock every day of that window, brew at least one batch of drink inside it, and end with at least one drink per dwarf."}, False),
        ]
        for label, info, _ in cases:
            task = SimpleNamespace(task=info, days=info["days"], credits=1.0)
            game = FakeGame(info)
            model = FakeModel()
            p = Plain(task, game, model)
            p.run(max_turns=1)
            self.assertEqual(model.calls, 0, f"{label} should run deterministic layer_only with 0 model calls")
            self.assertEqual(p.guard.brew_in_window, label == "LT01", label)

    def test_lt01_brew_in_window_brews_at_one_plant_plus_fruit_and_avoids_early_butcher(self):
        r = resp(35, 25, food=40, drink=350, cit=19, hands_off=14)
        r["observation"]["stocks"]["logs_usable"] = 30
        ov, g = overseer(r)
        ov.days = 60
        ov.set_task({"hands_off": {"from_day": 39, "days": 21},
                     "goal": "Keep drink in stock, brew at least one batch of drink inside it."})
        ov.supply()
        ov.window_supply()
        orders = g.tools("add_order")
        cook = [o for o in orders if o.get("recipe") == "cook_meal"]
        self.assertEqual(len(cook), 1)
        self.assertIn({"stock": "plants_total", "at_least": 25}, cook[0]["when"])
        self.assertEqual(g.tools("build_workshop"), [])  # food=40 >= 1*19 -> no Butchers/hunting risk on LT01
        brew_win = [o for o in orders if o.get("recipe") == "brew_drink" and o.get("amount") == 5]
        self.assertEqual(len(brew_win), 1)
        self.assertIn({"stock": "plants_brewable", "at_least": 1}, brew_win[0]["when"])
        fruit_win = [o for o in orders if o.get("recipe") == "brew_drink_from_fruit" and o.get("repeat") == "daily"]
        self.assertEqual(len(fruit_win), 1)

    def test_my1_keeps_batch8_and_7x5_dining(self):
        r = resp(140, 28, food=80, drink=100, cit=20)
        r["observation"]["stocks"]["logs_usable"] = 50
        r["observation"]["stocks"]["beds"] = 0
        ov, g = overseer(r)
        ov.days = 168
        ov.supply()
        bed_orders = [o for o in g.tools("add_order") if o.get("recipe") == "make_bed"]
        self.assertEqual(bed_orders, [{"recipe": "make_bed", "amount": 8}])


class Win7BreakthroughTests(unittest.TestCase):
    def test_underground_meeting_area_labs_only_excludes_op1_and_my1(self):
        r = resp(300, 36, food=60, drink=120, cit=10)
        o = r["observation"]
        o["map"]["surface_z"] = 152
        o["map"]["sites"] = [
            {"id": "E1", "kind": "E", "x": 92, "y": 100, "z": 152},
            {"id": "A_surf", "kind": "A", "x": 10, "y": 10, "z": 152, "w": 10, "h": 10, "open_tiles": 50},
            {"id": "A_ug", "kind": "A", "x": 10, "y": 10, "z": 150, "w": 9, "h": 7, "open_tiles": 45},
        ]
        o["doors"] = {"list": []}  # NOT sealed yet on OP1!
        o["zones"] = [{"id": 1, "type": "Dormitory", "x": 10, "y": 10, "z": 150, "w": 9, "h": 7}]
        ov, g = overseer(r)
        ov.furnish()
        self.assertEqual([a for a in g.tools("make_zone") if a.get("kind") == "meeting_area"], [])

        # h2: nor once the stair hatch is built. Idle dwarves gathered below never walk up to the hatch, and a fort
        # whose path index was rebuilt during a lockdown then stays below after the release (openplay.reconnect)
        o["doors"] = {"list": [{"id": 14, "kind": "hatch", "built": True, "locked": False, "x": 92, "y": 100, "z": 152}]}
        ov.load(r)
        ov.furnish()
        self.assertEqual([a for a in g.tools("make_zone") if a.get("kind") == "meeting_area"], [])

        # On MY1 (days=216), meeting_area MUST NOT activate underground (keeps grazing feast herd on surface grass)
        r_my = resp(200, 16, food=60, drink=120, cit=10)
        r_my["observation"]["map"]["surface_z"] = 152
        r_my["observation"]["map"]["sites"] = o["map"]["sites"]
        r_my["observation"]["doors"] = {"list": []}
        r_my["observation"]["zones"] = o["zones"]
        ov_my, g_my = overseer(r_my)
        ov_my.days = 216
        ov_my.furnish()
        self.assertEqual([a for a in g_my.tools("make_zone") if a.get("kind") == "meeting_area"], [])

        # On LT01/LT02 (no_fish_lab=True), meeting_area activates underground immediately
        r_lab = resp(50, 10, food=60, drink=120, cit=7, hands_off=29)
        r_lab["observation"]["map"]["surface_z"] = 152
        r_lab["observation"]["map"]["sites"] = o["map"]["sites"]
        r_lab["observation"]["doors"] = {"list": []}
        r_lab["observation"]["zones"] = o["zones"]
        ov_lab, g_lab = overseer(r_lab)
        ov_lab.days = 60
        ov_lab.set_task({"hands_off": {"from_day": 39, "days": 21},
                         "goal": "Keep drink in stock every day of that window, brew at least one batch of drink inside it."})
        ov_lab.furnish()
        self.assertEqual([a for a in g_lab.tools("make_zone") if a.get("kind") == "meeting_area"],
                         [{"kind": "meeting_area", "site": "A_ug"}])

    def test_late_winter_thaw_around_day_293_sounds_alert_on_full_year_only(self):
        r = threat_resp(292, None)
        r["observation"]["date"]["abs_tick"] = r["tick"] = 3 * 336 * DAY + 292 * DAY + 100
        ov, g = overseer(r)
        ov.defend()
        self.assertEqual(g.tools("civilian_alert"), [{"on": True}])
        self.assertTrue(ov.thaw_alert)

        # On MY1 (days=216), day 292 must NOT sound a late-winter alert (protects MY1 FINAL_STRETCH/FEAST_DAYS)
        r_my = threat_resp(158, None)
        r_my["observation"]["date"]["abs_tick"] = r_my["tick"] = 3 * 336 * DAY + 292 * DAY + 100
        ov_my, g_my = overseer(r_my)
        ov_my.days = 216
        ov_my.defend()
        self.assertEqual(g_my.tools("civilian_alert"), [])
        self.assertFalse(ov_my.thaw_alert)

    def test_caravan_in_blocks_brew_rest_then_restores_drink_safe_28_on_departure(self):
        order = {"id": 7, "recipe": "brew_drink", "repeat": "daily", "left": 3}
        r = resp(12, 204, food=15, drink=400, cit=10, orders=[order])
        r["observation"]["recent_events"] = ["The merchants need a trade depot to unload their goods."]
        ov, g = overseer(r)
        ov.days = 216
        ov.brew_own = {7}
        ov.feast()
        self.assertTrue(ov.caravan_in)
        self.assertFalse(ov.brew_stopped)
        self.assertEqual(g.tools("cancel_order"), [])

        # Caravan departs, MY1 drink=300 (30/cit >= DRINK_SAFE=28): stops brewing to protect food plants!
        r2 = resp(10, 206, food=15, drink=300, cit=10, orders=[order])
        r2["observation"]["recent_events"] = [
            "The merchants from TestCiv have embarked on their journey.",
            "The merchants from TestCiv will be leaving soon.",
        ]
        ov.load(r2)
        self.assertFalse(ov.caravan_in)
        self.assertTrue(ov.caravan_out)
        ov.feast()
        self.assertTrue(ov.brew_stopped)
        self.assertEqual(g.tools("cancel_order"), [{"order_id": 7}])

    def test_lt02_enables_no_fishing_and_fisher_hold(self):
        cits = [
            {"id": 80, "adult": True, "labors": ["MINE"], "positions": []},
            {"id": 83, "adult": True, "labors": ["FISH", "HAUL"], "positions": []},
        ]
        g = CitizenGame(cits)
        ov = Overseer(g, goal="Rescue", days=90)
        ov.set_task({"hands_off": {"from_day": 69, "days": 21},
                     "goal": "Keep drink in stock every day of that window, with your own built Still."})
        self.assertTrue(ov.no_fish_lab)
        self.assertFalse(ov.open_task())
        ov_lt01 = Overseer(g, goal="Drought", days=60)
        ov_lt01.set_task({"hands_off": {"from_day": 39, "days": 21},
                          "goal": "Keep drink in stock every day of that window, brew at least one batch of drink inside it."})
        self.assertTrue(ov_lt01.no_fish_lab)
        self.assertTrue(ov_lt01.brew_in_window)
        r0 = bare(90, 0, fishing=False, cit=2)
        r0["hands_off_in_days"] = 69
        r0["observation"]["map"]["wagon"] = {"x": 95, "y": 95, "z": 151}
        ov.load(r0)
        ov.count = 0
        ov.management()
        self.assertIn({"name": "autolabor"}, g.tools("enable_automation"))
        self.assertEqual(g.tools("create_squad"), [{"dwarf_ids": [83]}])
        self.assertEqual(g.tools("squad_order"), [{"order": "station", "x": 95, "y": 95, "z": 151}])

    def test_lt01_brew_in_window_skips_furniture_orders(self):
        r = resp(35, 25, food=80, drink=100, cit=15, hands_off=14)
        r["observation"]["stocks"]["logs_usable"] = 30
        r["observation"]["stocks"]["beds"] = 0
        r["observation"]["stocks"]["tables"] = 0
        r["observation"]["stocks"]["chairs"] = 0
        ov, g = overseer(r)
        ov.days = 60
        ov.set_task({"hands_off": {"from_day": 39, "days": 21},
                     "goal": "Keep drink in stock, brew at least one batch of drink inside it."})
        ov.supply()
        ov.housing_check()
        recipes = [o.get("recipe") for o in g.tools("add_order")]
        for f in ("make_bed", "make_table", "make_chair"):
            self.assertNotIn(f, recipes)

    def test_three_slot_amount15_maketool_wealth_engine_cancels_on_caravan_out(self):
        r = resp(300, 36, food=60, drink=200, cit=10,
                 workshops=("Carpenters",) * 6 + ("Still", "Kitchen"))
        r["observation"]["stocks"].update({"logs_usable": 80, "beds": 12, "tables": 7, "chairs": 8})
        r["observation"]["wealth"] = {"created": 4000}
        r["observation"]["map"]["sites"] = [{"id": "E1", "kind": "E", "x": 92, "y": 100, "z": 153}]
        r["observation"]["doors"] = {"list": [{"id": 14, "kind": "hatch", "built": True, "locked": False, "x": 92, "y": 100, "z": 153}]}
        ov, g = overseer(r)
        ov.progression_push()
        orders = g.tools("add_manager_order")
        self.assertEqual(len(orders), 3)
        self.assertTrue(all(o.get("job") == "MakeTool" and o.get("amount") == 15 for o in orders))
        self.assertEqual([o["when"][0]["at_least"] for o in orders], [60, 65, 70])
        all_ids = sorted(ov.wealth_ids)
        self.assertEqual(len(all_ids), 3)

        # Caravan departs -> all 3 wealth orders cancelled
        r2 = resp(140, 196, food=60, drink=200, cit=10,
                  workshops=("Carpenters",) * 6 + ("Still", "Kitchen"),
                  orders=[{"id": i, "job": "MakeTool", "repeat": "daily"} for i in all_ids])
        r2["observation"]["recent_events"] = ["The merchants from TestCiv have embarked on their journey."]
        ov.load(r2)
        ov.progression_push()
        self.assertEqual(sorted(a["order_id"] for a in g.tools("cancel_order")), all_ids)

    def test_suspended_furniture_unbuilt_over_10_days_stops_being_counted(self):
        r0 = resp(200, 136, food=60, drink=200, cit=10)
        r0["observation"]["furniture"] = [
            {"kind": "bed", "built": True, "x": 10, "y": 10, "z": 150},
            {"kind": "bed", "built": False, "x": 11, "y": 10, "z": 150},
        ]
        ov, _ = overseer(r0)
        self.assertEqual(ov.placed.get("bed"), 2)  # freshly planned bed still counts
        r1 = resp(189, 147, food=60, drink=200, cit=10)
        r1["observation"]["furniture"] = r0["observation"]["furniture"]
        ov.load(r1)
        self.assertEqual(ov.placed.get("bed"), 1)  # still unbuilt after 11 days -> excluded!


if __name__ == "__main__":
    unittest.main()
