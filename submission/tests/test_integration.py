"""End-to-end integration test with FakeGame and FakeModel."""
import io
import json
import unittest
from contextlib import redirect_stdout

from dfbench_client import GameClient, ModelClient, load_task
from plain import harness
from tests.fakes import FakeGame, FakeModel


def task_json(g, m, days, credits=0.5):
    return json.dumps({
        "schema": "dfbench-task/1", "run_id": "integration-test", "api": "v0", "game_url": g.url,
        "model": {"base_url": m.url, "name": "fake", "api": "openai-chat", "api_key": "placeholder"},
        "budget": {"credits": credits, "unit": "USD", "per": "game"},
        "limits": {"wall_s": 600, "actions_per_game_day": g.k, "max_advance_days": 28},
        "task": {"name": "fake-integration", "days": days}
    })


class IntegrationTest(unittest.TestCase):
    def test_full_game_run(self):
        with FakeGame(days=14) as g, FakeModel() as m:
            t = load_task(task_json(g, m, 14))
            model = ModelClient(t.model_base_url, t.model_name, retry_sleep_s=0.0, rate_limit_base_s=0.0)
            p = harness.Plain(t, GameClient(t.game_url), model)
            buf = io.StringIO()
            with redirect_stdout(buf):
                stats = p.run(max_turns=50)

            self.assertTrue(g.game_over)
            self.assertEqual(p.stop_reason, "game_over")
            self.assertGreater(stats["turns"], 0)
            # Verify caretaker and model acted
            tool_names = [x["tool"] for x in g.log]
            self.assertIn("appoint_manager", tool_names)
            # Verify harness_status was included in observation messages
            user_msgs = [x for x in m.requests[-1]["messages"] if x["role"] == "user"]
            last_obs = json.loads(user_msgs[-1]["content"][len("OBSERVATION "):])
            self.assertIn("harness_status", last_obs)
            self.assertIn("supply", last_obs["harness_status"])
            self.assertIn("housing", last_obs["harness_status"])


if __name__ == "__main__":
    unittest.main()
