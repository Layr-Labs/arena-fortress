"""Regression tests for public-facts advice and failed-action memory; no DF or model credits."""
import copy
import io
import json
import unittest
from contextlib import redirect_stdout

from dfbench_client.task import Task
from plain.harness import Plain


def fort():
    return {
        "date": {"abs_tick": 120000},
        "administrators": {"citizens": 25, "MANAGER": "Urist", "MANAGER_id": 7,
                           "manager_active_for_orders": True, "manager_office": "none"},
        "stocks": {"drink": 50, "food_edible": 40, "plants_brewable": 0,
                   "barrels_empty": 0, "logs_usable": 0, "beds": 99},
        "workshops": [{"id": 1, "type": "Still", "built": False}],
        "orders": [{"id": 4, "recipe": "brew_drink", "validated": False, "left": 10}],
        "plugins": {"autofarm": "off", "autolabor": "off", "autochop": "off"},
        "farm_plots": [], "furniture": [], "zones": [],
        "map": {"sites": [{"id": "R1", "kind": "R", "soil": True,
                            "designated": True, "dug": False, "free": False}]},
        "dwarves": [{"id": 7, "stress": 4}], "hands_off_in_days": 3,
    }


class Game:
    def __init__(self):
        self.last = {"tick": 120000}
        self.calls = []
        self.reply = {"ok": False, "error_code": "no_material", "error": "no usable log"}

    def task(self):
        return {"tools": [{"type": "function", "function": {"name": n, "parameters": {}}}
                          for n in ("build_workshop", "enable_automation", "advance_days")],
                "task": {"name": "practice", "days": 60}}

    def act(self, name, args):
        self.calls.append((name, args))
        return copy.deepcopy(self.reply)


class Model:
    usage = {}


def player():
    p = Plain(Task({"task": {"days": 60}}), Game(), Model())
    with redirect_stdout(io.StringIO()):
        p.setup()
    return p


def call(p, name="build_workshop", args=None):
    with redirect_stdout(io.StringIO()):
        p.run_call({"id": "c", "function": {"name": name, "arguments": json.dumps(
            args if args is not None else {"type": "Still", "site": "W1"})}})
    return json.loads(p.messages[-1]["content"])


class AdvisorTests(unittest.TestCase):
    def test_chaired_office_does_not_establish_order_validation(self):
        p = player()
        obs = fort()
        obs["administrators"]["manager_office"] = {"zone_id": 8, "chair": True}
        before = copy.deepcopy(obs)
        status = p.advisor.observe(obs, 120000)
        self.assertEqual(obs, before)
        self.assertEqual(status["unvalidated_order_ids"], [4])
        text = " ".join(status["priorities"])
        self.assertIn("still unvalidated", text)
        self.assertIn("no fixed validation delay", text)
        self.assertNotIn("manager_office_repair", status)
        for office in ("none", {}, {"chair": False}):
            obs["administrators"]["manager_office"] = office
            text = " ".join(p.advisor.observe(obs, 120000)["priorities"])
            self.assertNotIn("still unvalidated", text)
        obs["administrators"]["manager_office"] = {"chair": True}
        obs["orders"][0]["validated"] = True
        self.assertNotIn("still unvalidated", " ".join(p.advisor.observe(obs, 120000)["priorities"]))

    def test_manager_office_and_production_prerequisites_are_visible(self):
        p = player()
        status = p.advisor.observe(fort(), 120000)
        text = json.dumps(status).lower()
        self.assertIn("office", text)
        self.assertIn("barrel", text)
        self.assertIn("brewable", text)
        self.assertIn("autofarm", text)
        self.assertEqual(status["housing"]["built_beds"], 0)  # item stock is not placed beds
        self.assertEqual(status["housing"]["bed_shortfall"], 25)

    def test_unknown_sections_are_not_interpreted_as_zero(self):
        p = player()
        status = p.advisor.observe({"stocks": "ERR: probe failed", "furniture": "ERR: probe failed",
                                    "administrators": "ERR: probe failed", "farm_plots": None}, 120000)
        self.assertNotIn("built_beds", status.get("housing", {}))
        self.assertNotIn("drink", status.get("supply", {}))
        self.assertNotIn("appoint", json.dumps(status).lower())

    def test_same_tick_observations_do_not_destroy_stock_trend(self):
        p = player()
        obs = fort()
        p.advisor.observe(obs, 120000)
        obs["stocks"]["drink"] = 40
        p.advisor.observe(obs, 122400)
        status = p.advisor.observe(obs, 122400)
        self.assertEqual(status["supply"]["drink"]["net_per_day"], -5)
        self.assertEqual(status["supply"]["drink"]["estimated_days_at_net_rate"], 8)
        self.assertNotIn("net_per_day", p.advisor.observe(fort(), 119000)["supply"]["drink"])

    def test_farm_area_warns_only_with_known_compatible_expansion(self):
        obs = fort()
        obs["date"]["season"] = "spring"
        obs["administrators"]["citizens"] = 40
        obs["farm_plots"] = [{"id": 4, "built": True, "w": 3, "h": 3, "crop_this_season": "none"},
                             {"id": 5, "built": True, "w": 3, "h": 3},
                             {"id": 6, "built": False, "w": 3, "h": 3}]
        obs["stocks"]["seeds_by_kind"] = {"plump helmet": {"n": 60, "underground": True,
                                                                  "seasons": ["spring"]}}
        obs["map"]["sites"] = [{"id": "F1", "kind": "F", "free": True, "soil": True,
                                  "subterranean": True},
                                 {"id": "G1", "kind": "G", "free": True, "soil": True,
                                  "subterranean": False}]
        before = copy.deepcopy(obs)
        status = player().advisor.observe(obs, 120000)
        self.assertEqual(status["farms"]["built_area_tiles"], 18)
        self.assertEqual(status["farms"]["tiles_per_citizen"], 0.45)
        self.assertEqual(status["farms"]["planned"], 1)
        self.assertEqual(status["farms"]["seed_compatible_free_sites"], ["F1"])
        self.assertEqual(status["farms"]["fallow_built_ids"], [4])
        self.assertIn("heuristic", status["priorities"][0])
        self.assertEqual(obs, before)
        obs["date"]["season"] = "winter"
        status = player().advisor.observe(obs, 120000)
        self.assertNotIn("Food capacity risk", json.dumps(status))

    def test_farm_area_missing_dimensions_is_unknown_not_zero(self):
        obs = fort()
        obs["farm_plots"] = [{"id": 4, "built": True, "h": 3}]
        status = player().advisor.observe(obs, 120000)
        self.assertNotIn("built_area_tiles", status["farms"])
        self.assertNotIn("Food capacity risk", json.dumps(status))
        obs["farm_plots"] = None
        self.assertNotIn("farms", player().advisor.observe(obs, 120000))

    def test_planned_furniture_is_not_built_and_duplicate_zone_seats_not_counted(self):
        p = player()
        obs = fort()
        obs["furniture"] = [{"id": 1, "kind": "bed", "built": True},
                            {"id": 2, "kind": "bed", "built": False},
                            {"id": 3, "kind": "table", "built": True, "zone_ids": [8, 9]},
                            {"id": 4, "kind": "chair", "built": True, "zone_ids": [8, 9]}]
        obs["zones"] = [{"id": 8, "type": "DiningHall"}, {"id": 9, "type": "DiningHall"}]
        status = p.advisor.observe(obs, 120000)
        self.assertEqual(status["housing"]["built_beds"], 1)
        self.assertEqual(status["housing"]["dining_seats_upper_bound"], 1)

    def test_truncated_furniture_is_a_lower_bound_not_a_shortfall(self):
        obs = fort()
        obs["furniture_total"] = 400
        status = player().advisor.observe(obs, 120000)
        self.assertTrue(status["housing"]["truncated"])
        self.assertNotIn("bed_shortfall", status["housing"])

    def test_room_readiness_uses_dug_and_not_designated(self):
        p = player()
        obs = fort()
        status = p.advisor.observe(obs, 120000)
        self.assertEqual(status["sites"]["dug_soil_rooms"], [])
        obs["map"]["sites"][0]["dug"] = True
        self.assertEqual(p.advisor.observe(obs, 121200)["sites"]["dug_soil_rooms"], ["R1"])

    def test_identical_failure_is_not_sent_twice_without_progress(self):
        p = player()
        p.advisor.observe(fort(), 120000)
        self.assertEqual(call(p)["error_code"], "no_material")
        self.assertEqual(call(p)["error_code"], "unchanged_failure")
        self.assertEqual(len(p.game.calls), 1)
        self.assertEqual(p.stats["retry_refused"], 1)

    def test_changed_public_inputs_and_successful_prerequisite_allow_retry(self):
        p = player()
        obs = fort()
        p.advisor.observe(obs, 120000)
        call(p)
        obs["stocks"]["logs_usable"] = 1
        p.advisor.observe(obs, 120000)
        self.assertEqual(call(p)["error_code"], "no_material")
        p.game.reply = {"ok": True, "result": {"now": "on"}}
        call(p, "enable_automation", {"name": "autochop"})
        p.game.reply = {"ok": False, "error_code": "no_material"}
        self.assertEqual(call(p)["error_code"], "no_material")
        self.assertEqual(len(p.game.calls), 4)

    def test_time_movement_allows_retry_but_failure_remains_in_context(self):
        p = player()
        p.advisor.observe(fort(), 120000)
        call(p)
        p.game.last["tick"] += 1200
        status = p.advisor.observe(fort(), 121200)
        self.assertIn("no_material", json.dumps(status["recent_failures"]))
        self.assertEqual(call(p)["error_code"], "no_material")
        self.assertEqual(len(p.game.calls), 2)

    def test_transient_failures_and_advance_are_not_suppressed(self):
        p = player()
        p.game.reply = {"ok": False, "error_code": "internal_error"}
        call(p)
        call(p)
        p.game.reply = {"ok": False, "error_code": "failed"}
        call(p, "advance_days", {"days": 1})
        call(p, "advance_days", {"days": 1})
        self.assertEqual(len(p.game.calls), 4)

    def test_failure_memory_is_bounded_and_remembers_original_error(self):
        p = player()
        for i in range(100):
            call(p, args={"type": "Still", "site": f"W{i}"})
        status = p.advisor.observe(fort(), 120000)
        self.assertLessEqual(len(status["recent_failures"]), 8)
        self.assertLess(len(json.dumps(status)), 10000)
        self.assertIn("no usable log", json.dumps(status["recent_failures"]))


if __name__ == "__main__":
    unittest.main()
