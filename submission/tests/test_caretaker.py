"""Unit tests for Caretaker, digest, and harness integration."""
import unittest
from plain.caretaker import Caretaker, MOOD_WORKSHOP
from plain.digest import build_status


class FakeGameClient:
    def __init__(self):
        self.log = []
        self.queries = {}

    def act(self, tool, args):
        self.log.append((tool, args))
        return {"ok": True, "result": {"id": 100}}

    def query(self, name, **kw):
        return self.queries.get(name, {"ok": True, "result": {}})


class CaretakerTests(unittest.TestCase):
    def setUp(self):
        self.game = FakeGameClient()
        self.caretaker = Caretaker(self.game)

    def test_manager_appointment_and_plugins(self):
        obs = {
            "observation": {
                "dwarves": [{"id": 1, "adult": True, "organizer_skill": 5}],
                "administrators": {"citizens": 7, "manager_active_for_orders": False},
                "plugins": {"autochop": "off", "seedwatch": "off"},
                "stocks": {"logs_usable": 10},
                "map": {"sites": []},
            }
        }
        self.caretaker.step(obs)
        tools = [x[0] for x in self.game.log]
        self.assertIn("appoint_manager", tools)
        self.assertIn("enable_automation", tools)

    def test_core_workshops_and_standing_orders(self):
        obs = {
            "observation": {
                "dwarves": [{"id": 1, "adult": True}],
                "administrators": {"citizens": 7, "manager_active_for_orders": True},
                "plugins": {"autochop": "on", "seedwatch": "on"},
                "stocks": {"logs_usable": 10, "drink": 50, "food_edible": 50},
                "workshops": [],
                "orders": [],
                "map": {"sites": [{"id": "W1", "kind": "W"}, {"id": "W2", "kind": "W"}]},
            }
        }
        self.caretaker.step(obs)
        tools = [x[0] for x in self.game.log]
        self.assertIn("build_workshop", tools)
        self.assertIn("add_order", tools)
        # Check that brew_drink standing order was added
        orders = [x[1] for x in self.game.log if x[0] == "add_order"]
        recipes = [o.get("recipe") for o in orders]
        self.assertIn("brew_drink", recipes)

    def test_mood_handling(self):
        obs = {
            "observation": {
                "dwarves": [{"id": 1, "adult": True}],
                "administrators": {"citizens": 7, "manager_active_for_orders": True},
                "stocks": {"logs_usable": 10},
                "workshops": [],
                "moods": [{"unit_id": 1, "mood": "Fey", "skill": "Carpentry", "claimed_building_id": None}],
                "map": {"sites": [{"id": "W1", "kind": "W"}]},
            }
        }
        self.caretaker.step(obs)
        tools = [x[0] for x in self.game.log]
        self.assertIn("build_workshop", tools)
        ws_types = [x[1].get("type") for x in self.game.log if x[0] == "build_workshop"]
        self.assertIn("Carpenters", ws_types)

    def test_housing_and_furniture(self):
        obs = {
            "observation": {
                "dwarves": [{"id": 1, "adult": True}],
                "administrators": {"citizens": 10, "manager_active_for_orders": True},
                "stocks": {"logs_usable": 10, "furniture_free": {"bed": 5, "table": 3, "chair": 3}},
                "furniture": [],
                "zones": [],
                "map": {"sites": [{"id": "R1", "kind": "R", "dug": True, "free": True}]},
            }
        }
        self.caretaker.roles["R1"] = "dorm"
        self.caretaker.step(obs)
        tools = [x[0] for x in self.game.log]
        self.assertIn("make_zone", tools)
        self.assertIn("place_furniture", tools)


class DigestTests(unittest.TestCase):
    def test_digest_summary(self):
        obs = {
            "dwarves": [{"id": 1}, {"id": 2}],
            "administrators": {"citizens": 2, "manager_active_for_orders": True},
            "stocks": {"drink": 100, "food_edible": 50, "logs_usable": 8, "barrels_empty": 4},
            "furniture": [{"kind": "bed"}, {"kind": "table"}, {"kind": "chair"}],
            "moods": [],
        }
        status = build_status(obs, recent_failures=[{"tool": "add_order", "error_code": "order_churn"}])
        self.assertEqual(status["citizens"], 2)
        self.assertEqual(status["supply"]["drink"], 100)
        self.assertEqual(status["housing"]["beds_placed"], 1)
        self.assertEqual(status["housing"]["dining_seats"], 1)
        self.assertTrue(status["management"]["manager_active"])
        self.assertEqual(len(status["recent_failed_actions"]), 1)


if __name__ == "__main__":
    unittest.main()
