"""Check public-goal bed priority with offline clients only."""
import copy
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from dfbench_client import Task
from plain import harness
from test_brew_growth import public_task

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class FakeGame:
    def __init__(self, info):
        self.info = copy.deepcopy(info)
        self.calls = []
        self.last = {"tick": 0}

    def task(self):
        return {"task": copy.deepcopy(self.info), "tools": [{"type": "function", "function": {
            "name": name, "parameters": {"type": "object", "properties": {}}}}
            for name in ("add_order", "place_furniture")]}

    def act(self, tool, args):
        self.calls.append((tool, copy.deepcopy(args)))
        if tool == "place_furniture":
            at = {"bed": [11, 11, 9], "table": [12, 11, 9], "chair": [11, 12, 9]}[args["kind"]]
            return {"ok": True, "result": {"n": 1, "at": at}}
        return {"ok": True, "result": {"order_id": len(self.calls), "zone_id": len(self.calls)}}


def facts():
    return {"tick": 0, "observation": {
        "administrators": {"citizens": 19, "manager_active_for_orders": True, "MANAGER_id": 72,
                           "manager_office": {"zone_id": 6, "chair": False}},
        "map": {"sites": [{"id": "A1", "kind": "A", "x": 10, "y": 10, "z": 9,
                            "w": 7, "h": 6, "open_tiles": 32}]},
        "stocks": {"drink": 100, "plants_brewable": 7, "barrels_empty": 6, "logs_usable": 30,
                   "beds": 1, "tables": 1, "chairs": 1,
                   "furniture_free": {"bed": 1, "table": 1, "chair": 1}},
        "orders": [{"recipe": "make_barrel", "repeat": "daily"},
                   {"recipe": "cook_meal", "repeat": "daily"}],
        "zones": [], "furniture": [],
    }}


class BedsFirst(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.lt08 = public_task("lt08-migrant-surge.json")
        self.op1 = public_task("op1-start-year.json")

    def agent(self, info=None, resp=None):
        game = FakeGame(self.lt08 if info is None else info)
        agent = harness.Plain(Task({}), game, None)
        agent.setup()
        agent.guard.load(resp or facts())
        agent.guard.count = 0
        return agent

    def recipes(self, agent):
        return [args["recipe"] for tool, args in agent.game.calls if tool == "add_order"]

    def test_actual_public_goal_selects_both_policies_before_work(self):
        agent = self.agent()
        self.assertTrue(agent.guard.beds_first)
        self.assertTrue(agent.guard.drink_growth)
        agent.guard.supply()
        self.assertEqual(self.recipes(agent), ["brew_drink", "make_bed"])
        brew = agent.game.calls[0][1]
        self.assertEqual(brew["when"], [{"stock": "plants_brewable", "at_least": 2},
                                        {"stock": "barrels_empty", "at_least": 1}])

    def test_new_beds_are_still_placed_and_zoned(self):
        agent = self.agent()
        agent.guard.furnish()
        self.assertEqual(agent.game.calls, [
            ("place_furniture", {"kind": "bed", "site": "A1", "count": 1}),
            ("make_zone", {"kind": "dormitory", "site": "A1"}),
        ])

    def test_manager_office_chair_is_still_placed(self):
        resp = facts()
        resp["observation"]["zones"] = [{"id": 6, "type": "Office", "owner": 72,
            "x": 10, "y": 10, "z": 9, "w": 3, "h": 3, "furniture": {}}]
        agent = self.agent(resp=resp)
        agent.guard.office()
        self.assertEqual(agent.game.calls, [("place_furniture", {"kind": "chair", "site": "A1"})])

    def test_existing_dining_furniture_and_coverage_are_preserved(self):
        resp = facts()
        existing = [{"kind": kind, "x": x, "y": 11, "z": 9, "built": True}
                    for kind, x in (("table", 13), ("chair", 14))]
        resp["observation"]["furniture"] = copy.deepcopy(existing)
        agent = self.agent(resp=resp)
        agent.guard.furnish()
        self.assertEqual(agent.guard.o["furniture"], existing)
        self.assertEqual([args["kind"] for tool, args in agent.game.calls if tool == "place_furniture"], ["bed"])
        self.assertIn(("make_zone", {"kind": "dining_hall", "site": "A1"}), agent.game.calls)
        self.assertFalse(any(tool == "cancel_order" for tool, _ in agent.game.calls))

    def test_priority_remains_for_the_task_after_bed_stock_catches_up(self):
        resp = facts()
        resp["observation"]["stocks"]["beds"] = 100
        agent = self.agent(resp=resp)
        agent.guard.supply()
        self.assertEqual(self.recipes(agent), ["brew_drink"])
        self.assertTrue(agent.guard.beds_first)

    def test_normal_year_behavior_remains(self):
        agent = self.agent(self.op1)
        self.assertFalse(agent.guard.beds_first)
        agent.guard.supply()
        self.assertEqual(self.recipes(agent), ["brew_drink", "make_bed", "make_table", "make_chair"])
        agent.game.calls.clear()
        agent.guard.furnish()
        self.assertEqual([args["kind"] for tool, args in agent.game.calls if tool == "place_furniture"],
                         ["bed", "table", "chair"])

    def test_goal_phrase_and_hands_off_are_both_required_and_reset(self):
        for info in ({**self.lt08, "hands_off": None},
                     {**self.lt08, "goal": "Supply all dwarves."}):
            with self.subTest(info=info):
                agent = self.agent(info)
                self.assertFalse(agent.guard.beds_first)
                agent.guard.supply()
                self.assertIn("make_table", self.recipes(agent))
                self.assertIn("make_chair", self.recipes(agent))
        agent.guard.set_task(self.lt08)
        self.assertTrue(agent.guard.beds_first)
        agent.guard.set_task(self.op1)
        self.assertFalse(agent.guard.beds_first)

    def test_model_tools_can_still_request_dining_work(self):
        agent = self.agent()
        self.assertEqual(agent.tool_names, {"add_order", "place_furniture"})
        agent.run_call({"id": "model-table", "function": {"name": "add_order",
            "arguments": '{"recipe":"make_table","amount":1}'}})
        self.assertEqual(agent.game.calls, [("add_order", {"recipe": "make_table", "amount": 1})])


if __name__ == "__main__":
    unittest.main()
