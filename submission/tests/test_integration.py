"""Prompt integration and inherited guards, using the public fake HTTP services.

Run from the repository root:
  python3 -m unittest discover -s submission/tests -v
These checks do not measure the real model's playing strength.
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SUBMISSION = Path(__file__).resolve().parents[1]
REPO = SUBMISSION.parent
sys.path.insert(0, str(SUBMISSION))

from dfbench_client import GameClient, ModelClient, load_task
from plain import harness, prompt

spec = importlib.util.spec_from_file_location(
    "public_fakes", REPO / "baseline/tests/fakes.py")
fakes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fakes)


def config(game, model, name="lt01-drought-s0", credits=0.5):
    return json.dumps({
        "schema": "dfbench-task/1", "run_id": "test", "api": "v0",
        "game_url": game.url,
        "model": {"base_url": model.url, "name": "fake", "api_key": "placeholder"},
        "budget": {"credits": credits},
        "limits": {"wall_s": 600, "actions_per_game_day": game.k, "max_advance_days": 28},
        "task": {"name": name, "days": game.days, "goal": "Use the supplied horizon."},
    })


def play(game, model, server_task=None, **kwargs):
    task = load_task(config(game, model, **kwargs))
    client = ModelClient(task.model_base_url, task.model_name,
                         retry_sleep_s=0, rate_limit_base_s=0)
    game_client = GameClient(task.game_url)
    if server_task is not None:
        response = game_client.task()
        response["task"].update(server_task)
        game_client.task = lambda: response
    player = harness.Plain(task, game_client, client)
    with redirect_stdout(io.StringIO()):
        player.run(max_turns=60)
    return player


class PromptIntegration(unittest.TestCase):
    def test_each_public_task_receives_only_its_card(self):
        cases = {
            "op1-start-year-s0": "FRESH EMBARK",
            "my1-handover-lean-s0": "MID-YEAR TAKEOVER",
            "lt01-drought-s0": "DROUGHT",
            "lt02-rescue-neglected-s0": "RESCUE",
            "lt03-mood-artifact-s0": "STRANGE MOOD",
            "lt08-migrant-surge-s0": "MIGRANT SURGE",
        }
        for name, label in cases.items():
            with self.subTest(name=name):
                text = prompt.system_prompt(task={"name": name})
                self.assertEqual(text.count("TASK POLICY:"), 1)
                self.assertIn("TASK POLICY: " + label, text)

    def test_unknown_and_malformed_names_do_not_select_paths_or_guess_tasks(self):
        for task in (None, {}, {"name": None}, {"name": ["LT01"]},
                     {"name": "../../LT01"}, {"name": "LT010-other"},
                     {"name": "custom", "goal": "Migrants and a strange mood"}):
            with self.subTest(task=task):
                self.assertEqual(prompt.task_card(task), "")
        self.assertIn("TASK POLICY: DROUGHT",
                      prompt.task_card({"name": None, "id": "LT01-drought"}))

    def test_obsolete_mood_reference_is_not_injected(self):
        api = ("## 4. Sites\nCurrent W-site geometry.\n"
               "## 5. Tools\nRaw tool list.\n"
               "## 6. The observation\nobsolete_available_approx\n")
        text = prompt.system_prompt(api)
        self.assertIn("Current W-site geometry.", text)
        self.assertNotIn("obsolete_available_approx", text)
        self.assertNotIn("Raw tool list.", text)

    def test_http_loop_receives_card_and_still_uses_native_actions(self):
        with fakes.FakeGame(days=5) as game, fakes.FakeModel() as model:
            player = play(game, model, server_task={"name": "lt01-drought-s0"})
            self.assertEqual(player.stop_reason, "game_over")
            self.assertIn("TASK POLICY: DROUGHT", model.requests[0]["messages"][0]["content"])
            self.assertTrue(game.log)
            self.assertEqual(model.requests[0]["tool_choice"], "required")
            self.assertEqual(harness.MAX_DAYS, 14)

    def test_live_task_overrides_startup_name(self):
        with fakes.FakeGame(days=2) as game, fakes.FakeModel() as model:
            play(game, model, name="lt01-drought-s0",
                 server_task={"name": "lt08-migrant-surge-s0"})
            text = model.requests[0]["messages"][0]["content"]
            self.assertIn("TASK POLICY: MIGRANT SURGE", text)
            self.assertNotIn("TASK POLICY: DROUGHT", text)

    def test_stall_guard_and_advance_cap_remain(self):
        with fakes.FakeGame(days=2) as game, fakes.FakeModel(
                policy=lambda _: ("appoint_manager", {})) as model:
            player = play(game, model)
            self.assertGreater(player.stats["stall_advances"], 0)
        with fakes.FakeGame(days=30) as game, fakes.FakeModel(
                policy=lambda _: ("advance_days", {"days": 28})) as model:
            play(game, model)
            self.assertTrue(all(call["args"]["days"] <= 14 for call in game.log))

    def test_fresh_order_cannot_be_cancelled(self):
        step = 0

        def policy(messages):
            nonlocal step
            step += 1
            if step == 1:
                return "add_order", {"recipe": "brew_drink", "amount": 2}
            if step == 2:
                result = json.loads(next(
                    m["content"] for m in reversed(messages) if m["role"] == "tool"))
                order = result.get("result", result)
                return "cancel_order", {"order_id": order.get("order_id", order.get("id"))}
            return "advance_days", {"days": 14}

        with fakes.FakeGame(days=3) as game, fakes.FakeModel(policy=policy) as model:
            player = play(game, model)
            self.assertEqual(player.stats["churn_refused"], 1)
            self.assertFalse(any(call["tool"] == "cancel_order" for call in game.log))

    def test_hands_off_terminates(self):
        with fakes.FakeGame(days=8, hands_off_day=3) as game, fakes.FakeModel() as model:
            player = play(game, model)
            self.assertEqual(player.stop_reason, "HandsOff")
            self.assertEqual(game.day, 3)

    def test_packaged_entrypoint_loads_prompt_files(self):
        with fakes.FakeGame(days=4) as game, fakes.FakeModel() as model:
            result = subprocess.run(
                [sys.executable, "-m", "plain"], cwd=SUBMISSION,
                env={**os.environ, "DFBENCH_TASK": config(game, model),
                     "PYTHONPATH": str(SUBMISSION)}, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(game.game_over)


if __name__ == "__main__":
    unittest.main()
