"""Regressions for resource accounting and real API partial-placement behavior."""
import copy
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overseer.migrant import MigrantOverseer, applies, bed_facts
from plain import harness, prompt


def area(name, z, open_tiles=20):
    return {"id": name, "kind": "A", "x": 10, "y": 10, "z": z,
            "w": 10, "h": 5, "open_tiles": open_tiles}


def state(day=0, free=8, furniture=None):
    return {"day": day, "tick": day * 1200, "days_left": 60 - day, "hands_off_in_days": 39 - day,
            "observation": {
                "administrators": {"citizens": 19, "manager_active_for_orders": True},
                "stocks": {"furniture_free": {"bed": free}, "logs_usable": 20},
                "map": {"sites": [area("A1", 10), area("A2", 9), area("A3", 8)]},
                "furniture": furniture or [], "orders": [], "zones": [],
                "workshops": [{"type": "Carpenters", "built": True}, {"type": "Still", "built": True},
                              {"type": "Kitchen", "built": True}]}}


class Game:
    def __init__(self):
        self.calls = []
        self.answers = {}
        self.current = state()
        self.last = self.current

    def observe(self):
        self.last = self.current
        return copy.deepcopy(self.current)

    def act(self, tool, args):
        self.calls.append((tool, copy.deepcopy(args)))
        if tool == "place_furniture":
            return self.answers.get(args["site"], {"ok": False, "error_code": "no_space"})
        return {"ok": True, "result": {"order_id": len(self.calls)}}


class MigrantCapacity(unittest.TestCase):
    def setUp(self):
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)
        self.game = Game()
        self.guard = MigrantOverseer(self.game, goal="Migrants are arriving", days=60)
        self.guard.load(self.game.current)
        self.guard.count = 0

    def placements(self):
        return [a for t, a in self.game.calls if t == "place_furniture"]

    def test_partial_success_uses_actual_remainder_across_three_areas(self):
        self.game.answers = {
            "A1": {"ok": True, "result": {"n": 2, "at": [[10, 10, 10], [11, 10, 10]]}},
            "A2": {"ok": True, "result": {"n": 3, "at": [[10, 10, 9], [11, 10, 9], [12, 10, 9]]}},
            "A3": {"ok": True, "result": {"n": 3, "at": [[10, 10, 8], [11, 10, 8], [12, 10, 8]]}}}
        self.guard.furnish()
        self.assertEqual([a["count"] for a in self.placements()], [8, 6, 3])

    def test_full_area_is_skipped_until_geometry_changes(self):
        self.guard.furnish()
        self.assertEqual(len(self.placements()), 3)
        self.game.calls.clear()
        self.guard.load(state(day=1))
        self.guard.furnish()
        self.assertEqual(self.placements(), [])
        changed = state(day=2)
        changed["observation"]["map"]["sites"][1]["open_tiles"] += 1
        self.guard.load(changed)
        self.guard.furnish()
        self.assertEqual([a["site"] for a in self.placements()], ["A2"])

    def test_removed_furniture_reopens_a_full_area(self):
        furniture = [{"kind": "chair", "x": 10, "y": 10, "z": 10}]
        self.guard.load(state(furniture=furniture))
        self.guard.furnish()
        self.game.calls.clear()
        self.guard.load(state(day=1))
        self.guard.furnish()
        self.assertEqual([a["site"] for a in self.placements()], ["A1"])

    def test_missing_material_does_not_blacklist_space_or_try_other_areas(self):
        self.game.answers["A1"] = {"ok": False, "error_code": "no_material"}
        self.guard.furnish()
        self.assertEqual(len(self.placements()), 1)
        self.assertEqual(self.guard.full_areas, {})

    def test_places_reserve_beyond_current_citizens(self):
        furniture = [{"kind": "bed", "built": True, "x": 11, "y": 11, "z": 7} for _ in range(21)]
        self.guard.load(state(free=15, furniture=furniture))
        self.guard.furnish()
        self.assertEqual(self.placements()[0]["count"], 10)

    def test_planned_beds_count_against_production_but_not_completion(self):
        furniture = [{"kind": "bed", "built": False, "x": 11, "y": 11, "z": 7} for _ in range(23)]
        resp = state(free=8, furniture=furniture)
        self.guard.load(resp)
        self.guard.supply()
        beds = [a for t, a in self.game.calls if t == "add_order" and a.get("recipe") == "make_bed"]
        self.assertEqual(beds, [])
        self.assertEqual(bed_facts(resp)["built"], 0)
        self.assertEqual(bed_facts(resp)["planned"], 23)
        self.assertEqual(self.guard.advance_cap(resp), 1)

    def test_capped_existing_brew_does_not_block_uncapped_order(self):
        self.guard.orders = [{"id": 1, "recipe": "brew_drink", "repeat": "daily",
                              "when": [{"stock": "drink", "below": 300}]}]
        self.guard.supply()
        brew = [a for t, a in self.game.calls if t == "add_order" and a.get("recipe") == "brew_drink"]
        self.assertEqual(len(brew), 1)
        self.assertNotIn("drink", [c.get("stock") for c in brew[0]["when"]])
        self.guard.orders.append({"id": 2, **brew[0]})
        self.game.calls.clear()
        self.guard.now += 4 * 1200
        self.guard.supply()
        self.assertFalse(any(a.get("recipe") == "brew_drink" for _, a in self.game.calls))

    def test_bed_priority_preserves_exactly_one_manager_chair(self):
        self.guard.supply()
        furniture = [a for t, a in self.game.calls if t == "add_order"
                     and a.get("recipe") in ("make_chair", "make_table")]
        self.assertEqual(furniture, [{"recipe": "make_chair", "amount": 1}])
        self.guard.zones = [{"type": "Office", "furniture_planned": {"chair": 1}}]
        self.game.calls.clear()
        self.guard.now += 4 * 1200
        self.guard.supply()
        self.assertFalse(any(a.get("recipe") == "make_chair" for _, a in self.game.calls))

    def test_two_carpenters_including_unfinished_are_enough(self):
        self.guard.o["workshops"].append({"type": "Carpenters", "built": False})
        with patch.object(self.guard, "build") as build:
            self.guard.workshops()
        build.assert_not_called()

    def test_pending_manufacture_is_not_duplicated(self):
        self.guard.orders = [{"recipe": "make_bed", "left": 1}]
        self.guard.supply()
        self.assertFalse(any(a.get("recipe") == "make_bed" for _, a in self.game.calls))

    def test_migrant_selection_requires_public_goal_and_hands_off(self):
        goal = "Every dwarf must have a placed bed"
        self.assertTrue(applies({"goal": goal, "hands_off": {"from_day": 39}}))
        self.assertFalse(applies({"goal": goal, "hands_off": None}))
        self.assertFalse(applies({"goal": "Make a thriving fortress", "hands_off": {"from_day": 39}}))

    def test_model_advance_uses_fresh_construction_facts(self):
        task = SimpleNamespace(task={"days": 60}, days=60, credits=None)
        agent = harness.Plain(task, self.game, SimpleNamespace(usage={}))
        agent.guard = self.guard
        agent.tool_names = {"advance_days"}
        agent.messages = []
        agent.run_call({"id": "x", "function": {"name": "advance_days", "arguments": '{"days": 14}'}})
        self.assertEqual(self.game.calls[-1], ("advance_days", {"days": 1}))

    def test_long_game_prompt_is_identical_with_or_without_task_info(self):
        manual = "## 4. Sites\nsites\n## 6. Observation\nobservation"
        for days in (216, 336):
            self.assertEqual(prompt.system_prompt(manual),
                             prompt.system_prompt(manual, task_info={"name": "start-year", "days": days}))


if __name__ == "__main__":
    unittest.main()
