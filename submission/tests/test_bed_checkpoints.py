"""Check model advance limits from observed bed counts with offline clients."""
import copy
import io
import json
from contextlib import redirect_stdout
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_brew_growth import public_task
from test_pacing import FakeGame, FakeModel, harness


def observed(day=27, beds=22, citizens=46, free=0):
    return {"day": day, "tick": day * 1200, "observation": {
        "date": {"abs_tick": day * 1200},
        "administrators": {"citizens": citizens},
        "stocks": {"beds": beds + free, "furniture_free": {"bed": free}},
        "furniture": [{"kind": "bed", "x": n, "y": 1, "z": 1} for n in range(beds)]}}


class CheckpointGame(FakeGame):
    def __init__(self, task_name="lt08-migrant-surge.json"):
        super().__init__()
        self.info = public_task(task_name)
        self.day = 27
        self.last = {"tick": self.day * 1200}

    def task(self):
        return {**super().task(), "task": copy.deepcopy(self.info)}

    def observe(self):
        self.observed_days.append(self.day)
        self.last = {"day": self.day, "tick": self.day * 1200, "game_over": self.day >= 39}
        return {**observed(self.day), **self.last}

    def act(self, name, args):
        resp = super().act(name, args)
        if self.day >= 39:
            self.day = 60
            self.last = {"day": 60, "tick": 60 * 1200, "game_over": True}
            return {**resp, **self.last}
        return resp


class AdvanceModel(FakeModel):
    def chat(self, messages, **params):
        self.calls += 1
        return {"choices": [{"message": {"role": "assistant", "tool_calls": [{
            "id": str(self.calls), "type": "function", "function": {
                "name": "advance_days", "arguments": json.dumps({"days": 14})}}]}}]}


class BedCheckpoints(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def agent(self, task_name="lt08-migrant-surge.json", **kw):
        game = CheckpointGame(task_name)
        agent = harness.Plain(SimpleNamespace(task={}, days=60, credits=None), game, None)
        agent.setup()
        agent.guard.load(observed(**kw))
        return agent, game

    def call(self, agent, args, name="advance_days"):
        return agent.run_call({"id": "checkpoint", "function": {
            "name": name, "arguments": json.dumps(args)}})

    def test_recorded_day27_gap_caps14_at2_independent_of_bed_item_stock(self):
        for free in (0, 57):
            with self.subTest(free=free):
                agent, game = self.agent(free=free)
                self.assertTrue(agent.guard.beds_first)
                self.assertTrue(self.call(agent, {"days": 14}))
                self.assertEqual(game.actions, [("advance_days", {"days": 2})])
                self.assertEqual(game.day, 29)

    def test_normal_public_goal_keeps14_despite_housing_gap(self):
        agent, game = self.agent("op1-start-year.json")
        self.assertFalse(agent.guard.beds_first)
        self.call(agent, {"days": 14})
        self.assertEqual(game.actions, [("advance_days", {"days": 14})])

    def test_bed_goal_with_enough_placed_beds_keeps14(self):
        for beds in (46, 47):
            with self.subTest(beds=beds):
                agent, game = self.agent(beds=beds)
                self.call(agent, {"days": 14})
                self.assertEqual(game.actions, [("advance_days", {"days": 14})])

    def test_requested_one_remains_one(self):
        agent, game = self.agent()
        self.call(agent, {"days": 1})
        self.assertEqual(game.actions, [("advance_days", {"days": 1})])

    def test_invalid_or_missing_days_keep_one_day_fallback(self):
        for args in ({}, {"days": None}, {"days": "invalid"}, {"days": []}, {"days": {}}, {"days": [14]}):
            with self.subTest(args=args):
                agent, game = self.agent()
                self.call(agent, args)
                self.assertEqual(game.actions, [("advance_days", {"days": 1})])

    def test_stop_on_argument_is_preserved(self):
        agent, game = self.agent()
        self.call(agent, {"days": 14, "stop_on": ["hostiles", "migrants"]})
        self.assertEqual(game.actions, [("advance_days", {
            "days": 2, "stop_on": ["hostiles", "migrants"]})])

    def test_existing_integer_conversion_and_lower_bound_are_preserved(self):
        for request, expected in (("14", 2), (28, 2), (2, 2), (0, 1), (-4, 1)):
            with self.subTest(request=request):
                agent, game = self.agent()
                self.call(agent, {"days": request})
                self.assertEqual(game.actions, [("advance_days", {"days": expected})])

    def test_nonadvance_arguments_do_not_change(self):
        agent, game = self.agent()
        self.assertFalse(self.call(agent, {"name": "autochop", "days": 14}, "enable_automation"))
        self.assertEqual(game.actions, [("enable_automation", {"name": "autochop", "days": 14})])

    def test_harness_initiated_advance_does_not_use_model_cap(self):
        agent, game = self.agent()
        agent.advance(14, "test")
        self.assertEqual(game.actions, [("advance_days", {"days": 14})])

    def test_new_observed_bed_count_removes_cap(self):
        agent, game = self.agent()
        self.call(agent, {"days": 14})
        agent.guard.load(observed(day=29, beds=46))
        self.call(agent, {"days": 14})
        self.assertEqual(game.actions, [("advance_days", {"days": 2}),
                                       ("advance_days", {"days": 14})])

    def test_loop_runs_another_controller_pass_before_hands_off(self):
        game, model = CheckpointGame(), AdvanceModel()
        agent = harness.Plain(SimpleNamespace(task={}, days=60, credits=None), game, model)
        with patch.object(agent.guard, "plan", return_value=None) as plan:
            agent.run(max_turns=2)
        self.assertEqual(game.observed_days, [27, 29])
        self.assertEqual(plan.call_count, 2)
        self.assertEqual(game.actions, [("advance_days", {"days": 2})] * 2)
        self.assertEqual((game.day, model.calls, agent.stats["stall_advances"]), (31, 2, 0))


if __name__ == "__main__":
    unittest.main()
