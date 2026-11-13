"""Tests for Master Pareto upgrades on top of leader-harness (65e60732)."""
import types
import unittest

from overseer import beasts
from overseer.openplay import FEAST_DAYS
from plain import digest
from plain.harness import MAX_API_STREAK, Plain
from tests.support import HATCH, overseer, resp, threat_resp


class TestMasterPareto(unittest.TestCase):
    def test_wealth_push_cancels_owned_wood_crafts_at_5500(self):
        r = resp(days_left=290, day=46, food=45, drink=90, cit=7,
                 workshops=("Carpenters", "Still", "Kitchen"))
        r["observation"]["stocks"].update(logs_usable=30)
        r["observation"]["wealth"] = {"created": 1200}
        r["observation"]["map"]["sites"] = [{"id": "W1", "kind": "W"}]
        ov, g = overseer(r)
        ov.days = 336
        ov.progression_push()
        self.assertEqual([a["type"] for a in g.tools("build_workshop")], ["Craftsdwarfs"])

        # Once Craftsdwarfs exists and wealth < 5500, add repeating daily wood MakeCrafts
        r2 = resp(days_left=288, day=48, food=45, drink=90, cit=7,
                  workshops=("Carpenters", "Still", "Kitchen", "Craftsdwarfs"))
        r2["observation"]["stocks"].update(logs_usable=30)
        r2["observation"]["wealth"] = {"created": 3200}
        ov.load(r2)
        ov.count = 0
        g.calls.clear()
        ov.progression_push()
        mgr_orders = g.tools("add_manager_order")
        self.assertEqual(len(mgr_orders), 1)
        self.assertEqual(mgr_orders[0]["job"], "MakeCrafts")
        self.assertEqual(mgr_orders[0]["material_category"], ["wood"])
        self.assertEqual(len(ov.craft_ids), 1)
        oid = next(iter(ov.craft_ids))

        # As soon as created wealth reaches >= 5500, cancel owned craft_ids immediately
        r3 = resp(days_left=240, day=96, food=80, drink=160, cit=14,
                  workshops=("Carpenters", "Still", "Kitchen", "Craftsdwarfs"),
                  orders=[{"id": oid, "job": "MakeCrafts", "repeat": "daily"},
                          {"id": 999, "job": "MakeCrafts", "repeat": "daily"}])
        r3["observation"]["wealth"] = {"created": 5600}
        ov.load(r3)
        ov.count = 0
        g.calls.clear()
        ov.progression_push()
        self.assertEqual(g.tools("cancel_order"), [{"order_id": oid}])
        self.assertNotIn(oid, ov.craft_ids)

    def test_cross_type_workshop_site_reservation_in_single_pass(self):
        r = resp(days_left=334, day=2, food=50, drink=60, cit=7, workshops=())
        r["observation"]["stocks"].update(logs_usable=20)
        r["observation"]["map"]["sites"] = [
            {"id": "W1", "kind": "W"},
            {"id": "W2", "kind": "W"},
            {"id": "W3", "kind": "W"},
        ]
        ov, g = overseer(r)
        ov.build("Carpenters")
        ov.build("Still")
        ov.build("Kitchen")
        self.assertEqual(
            g.tools("build_workshop"),
            [
                {"type": "Carpenters", "site": "W1"},
                {"type": "Still", "site": "W2"},
                {"type": "Kitchen", "site": "W3"},
            ],
        )

    def test_stair_safe_and_chairless_office_repair_plus_digest(self):
        # At cit=8 with only a 1x1 stair A1, do NOT zone A1
        r = resp(days_left=330, day=6, food=50, drink=60, cit=8)
        r["observation"]["administrators"]["MANAGER_id"] = 2
        r["observation"]["stocks"]["furniture_free"] = {"chair": 1}
        r["observation"]["map"]["sites"] = [{"id": "A1", "kind": "A", "x": 10, "y": 10, "z": 100, "w": 1, "h": 1}]
        ov, g = overseer(r)
        ov.office()
        self.assertEqual(g.tools("make_zone"), [])

        # Lab/handover fort where manager owns a 1x1 chairless office Z1, while A2 already holds a built chair:
        # office() zones A2 as office and assigns it to manager; digest recognises the second chaired office.
        r2 = resp(days_left=58, day=2, food=60, drink=80, cit=22)
        r2["observation"]["administrators"].update(
            MANAGER="Urist", MANAGER_id=2, manager_active_for_orders=True,
            manager_office={"zone_id": 10, "chair": False},
        )
        r2["observation"]["zones"] = [
            {"id": 10, "type": "Office", "owner": 2, "x": 10, "y": 10, "z": 100, "w": 1, "h": 1, "furniture": {}},
        ]
        r2["observation"]["furniture"] = [
            {"kind": "chair", "built": True, "x": 14, "y": 14, "z": 99, "zone_ids": []},
        ]
        r2["observation"]["map"]["sites"] = [
            {"id": "A1", "kind": "A", "x": 10, "y": 10, "z": 100, "w": 1, "h": 1},
            {"id": "A2", "kind": "A", "x": 12, "y": 12, "z": 99, "w": 5, "h": 5, "open_tiles": 20},
        ]
        ov2, g2 = overseer(r2)
        ov2.lab = True
        ov2.office()
        self.assertEqual(g2.tools("make_zone"), [{"kind": "office", "site": "A2"}])

        # Next pass once DF lists the newly zoned chaired office (unowned), office() assigns it to MANAGER_id=2
        r2["observation"]["zones"].append(
            {"id": 11, "type": "Office", "owner": None, "x": 12, "y": 12, "z": 99, "w": 5, "h": 5,
             "furniture": {"chair": 1}}
        )
        ov2.load(r2)
        ov2.count = 0
        g2.calls.clear()
        ov2.office()
        self.assertEqual(g2.tools("assign_zone"), [{"zone_id": 11, "dwarf_id": 2}])
        r2["observation"]["zones"][-1]["owner"] = 2
        text = digest.digest(r2["observation"], {"day": 2, "tick": 2400, "days_left": 58})
        self.assertIn("office zone 11 chair=yes", text)

    def test_rot_safe_feast_window_and_drink_safe_threshold(self):
        self.assertEqual(FEAST_DAYS, 14)
        # During FINAL_STRETCH (days_left=22), drink=260 (< 28*15=420) must NOT stop brewing (prevents MY1 T<336 Tier-1)
        r = resp(days_left=22, day=314, food=6, drink=260, cit=15)
        ov, g = overseer(r)
        ov.brew_own = {501}
        ov.provision()
        self.assertFalse(ov.brew_stopped)
        self.assertEqual(g.tools("cancel_order"), [])

        # Inside FEAST_DAYS=14, brewing stops only once drink >= 28*cit (420), and slaughters feast batch
        r2 = resp(days_left=13, day=323, food=0, drink=430, cit=15,
                  orders=[{"id": 501, "recipe": "brew_drink", "repeat": "daily"}])
        r2["units"] = []
        ov.load(r2)
        ov.count = 0
        g.calls.clear()
        ov.provision()
        self.assertTrue(ov.brew_stopped)
        self.assertEqual(g.tools("cancel_order"), [{"order_id": 501}])

    def test_wood_crafts_amount3_and_openplay_office_dining_guard(self):
        r = resp(days_left=280, day=56, food=60, drink=120, cit=10,
                 workshops=("Carpenters", "Still", "Kitchen", "Craftsdwarfs"))
        r["observation"]["stocks"].update(logs_usable=30, boulders_usable=20)
        r["observation"]["wealth"] = {"created": 3200}
        ov, g = overseer(r)
        ov.days = 336
        ov.progression_push()
        orders = g.tools("add_manager_order")
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["material_category"], ["wood"])
        self.assertEqual(orders[0]["amount"], 3)

        # Open-play office() (MY1/OP1, lab=False) must NOT hijack an existing dining chair on A2 even at cit=20
        for cit in (10, 20):
            ro = resp(days_left=180, day=156, food=90, drink=180, cit=cit)
            ro["observation"]["administrators"].update(
                MANAGER="Urist", MANAGER_id=2, manager_active_for_orders=True,
                manager_office={"zone_id": 10, "chair": False},
            )
            ro["observation"]["stocks"]["furniture_free"] = {"chair": 0}
            ro["observation"]["zones"] = [
                {"id": 10, "type": "Office", "owner": 2, "x": 5, "y": 5, "z": 99, "w": 3, "h": 3, "furniture": {}},
                {"id": 5, "type": "DiningHall", "x": 12, "y": 12, "z": 99, "w": 7, "h": 5},
            ]
            ro["observation"]["furniture"] = [{"kind": "chair", "built": True, "x": 14, "y": 14, "z": 99, "zone_ids": [5]}]
            ro["observation"]["map"]["sites"] = [{"id": "A2", "kind": "A", "x": 12, "y": 12, "z": 99, "w": 7, "h": 5, "open_tiles": 30}]
            ovo, go = overseer(ro)
            ovo.lab = False
            ovo.office()
            self.assertEqual(go.tools("make_zone"), [])

    def test_primate_troops_and_reactive_citizen_attackers(self):
        wagon = {"x": 100, "y": 100, "z": 153}
        units = [
            {"race": "MACAQUE_RHESUS", "x": 170, "y": 100, "z": 153},
            {"race": "BIRD_BUZZARD", "x": 120, "y": 100, "z": 153},
            {"race": "GRAY_LANGUR", "x": 110, "y": 100, "z": 153, "tame": True},
        ]
        found, sure = beasts.in_sight(units, len(units), wagon)
        self.assertTrue(sure)
        self.assertEqual([b["race"] for b in found], ["MACAQUE_RHESUS"])
        self.assertTrue(found[0].get("troop"))

        r = threat_resp(day=50, dist=None, n=0, cit=10)
        r["observation"]["dwarves"][0].update(name="Urist McMiner", profession="Miner")
        r["observation"]["recent_events"] = [
            "The badger bites the Miner in the lower right leg, bruising the muscle!"
        ]
        r["observation"]["burrows"]["list"][0]["citizens_inside"] = 3
        ov, g = overseer(r)
        g.others = [{"race": "BADGER", "x": 175, "y": 100, "z": 153}]
        r["observation"]["map"]["wagon"] = wagon
        ov.load(r)
        ov.count = 0
        ov.defend()
        self.assertIn({"on": True}, g.tools("civilian_alert"))
        self.assertIn({"locked": True, "door_id": HATCH["id"]}, g.tools("lock_door"))

    def test_office_skips_farm_plots_and_walks_past_no_space_to_a6(self):
        r = resp(200, 136, 120, drink=250, cit=15)
        r["observation"]["administrators"].update(MANAGER="Urist", MANAGER_id=89, manager_active_for_orders=True)
        r["observation"]["stocks"]["furniture_free"] = {"chair": 1}
        r["observation"]["zones"] = [{"id": 39, "type": "Office", "owner": 89, "x": 10, "y": 10, "z": 105, "w": 7, "h": 3}]
        r["observation"]["farm_plots"] = [{"id": 1, "x": 10, "y": 10, "z": 104, "w": 7, "h": 3}]
        r["observation"]["map"]["sites"] = [
            {"id": "A4", "kind": "A", "x": 10, "y": 10, "z": 105, "w": 7, "h": 3, "open_tiles": 21},
            {"id": "A5", "kind": "A", "x": 10, "y": 10, "z": 104, "w": 7, "h": 3, "open_tiles": 21},
            {"id": "A6", "kind": "A", "x": 10, "y": 10, "z": 103, "w": 7, "h": 5, "open_tiles": 35},
        ]
        ov, g = overseer(r)
        orig_act = g.act
        def fake_act(tool, args=None):
            if tool == "place_furniture" and isinstance(args, dict) and args.get("site") == "A4":
                g.calls.append((tool, args))
                return {"ok": False, "error_code": "no_space", "error": "no free floor tile"}
            if tool == "make_zone":
                g.calls.append((tool, args))
                return {"ok": True, "result": {"zone_id": 55}}
            return orig_act(tool, args)
        g.act = fake_act
        ov.lab = False
        ov.load(r)
        ov.office()
        self.assertIn("A4", ov.office_full)
        self.assertEqual(g.tools("make_zone"), [{"kind": "office", "site": "A6"}])
        self.assertIn({"kind": "chair", "site": "A6"}, g.tools("place_furniture"))

    def test_surge_furnish_places_beds_past_current_citizens_before_hands_off(self):
        r = resp(55, 5, 120, drink=400, cit=22)
        r["observation"]["stocks"].update({"beds": 40, "furniture_free": {"bed": 15}, "furniture_placed": {"bed": 25}})
        r["observation"]["map"]["sites"] = [
            {"id": "A1", "kind": "A", "x": 10, "y": 10, "z": 99, "w": 12, "h": 12, "open_tiles": 80}
        ]
        ov, g = overseer(r)
        ov.surge = True
        ov.load(r)
        ov.furnish()
        beds_calls = [c for c in g.tools("place_furniture") if c.get("kind") == "bed"]
        self.assertEqual(beds_calls, [{"kind": "bed", "site": "A1", "count": 15}])

    def test_wall_budget_guard_and_api_streak(self):
        self.assertEqual(MAX_API_STREAK, 8)
        task = types.SimpleNamespace(task={"goal": "Survive", "days": 336}, days=336, credits=1.0, wall_seconds=1800)
        dummy_game = types.SimpleNamespace()
        dummy_model = types.SimpleNamespace(usage={"cost_usd": 0.0})
        p = Plain(task, dummy_game, dummy_model)
        self.assertFalse(p.wall_low({"days_left": 100}))
        p.started_at -= 1500  # 300s left < 360s WALL_MIN_RESERVE
        self.assertTrue(p.wall_low({"days_left": 100}))


if __name__ == "__main__":
    unittest.main()
