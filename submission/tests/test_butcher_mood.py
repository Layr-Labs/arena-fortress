"""Regression coverage for Overseer.butcher() in lab window_supply() and strange-mood bone demands."""
import unittest

from overseer.harness import Overseer
from support import StubGame, resp


class ButcherMoodTests(unittest.TestCase):
    def test_window_supply_butcher_runs_without_aborting_plan(self):
        r = resp(40, 20, food=10, drink=80, cit=10, hands_off=10, workshops=("Carpenters", "Still", "Kitchen"))
        r["observation"]["map"]["sites"] = [{"id": "W1", "kind": "W"}]
        game = StubGame()
        ov = Overseer(game, goal="Survive the window", days=60)
        ov.set_task({"goal": "Survive the window", "hands_off": 28})
        ov.load(r)
        ov.count = 0
        ov.plan()  # raises directly if AttributeError occurs (unlike step())
        self.assertIn({"type": "Butchers", "site": "W1"}, game.tools("build_workshop"))
        self.assertEqual(game.tools("slaughter"), [{"unit_id": 1}])

    def test_strange_mood_bone_demand_triggers_butcher(self):
        r = resp(200, 50, food=120, drink=120, cit=10, hands_off=20, workshops=("Carpenters", "Still", "Kitchen", "Craftsdwarfs"))
        r["observation"]["map"]["sites"] = [{"id": "W1", "kind": "W"}]
        r["observation"]["moods"] = [{
            "id": 4,
            "mood": "Fey",
            "skill": "BONE_CARVE",
            "claimed_building_id": 99,
            "items_needed": [{"demand": "bones", "item": "any bone"}],
        }]
        game = StubGame()
        ov = Overseer(game, goal="Handle strange moods", days=84)
        ov.set_task({"goal": "Handle strange moods", "hands_off": 28})
        ov.load(r)
        ov.count = 0
        ov.mood()
        self.assertIn({"type": "Butchers", "site": "W1"}, game.tools("build_workshop"))
        self.assertEqual(game.tools("slaughter"), [{"unit_id": 1}])


if __name__ == "__main__":
    unittest.main()
