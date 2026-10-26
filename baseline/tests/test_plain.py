"""The plain baseline against the fake game and the fake gateway: whole (short) games, and its guards."""
import io
import json
import os
import re
import subprocess
import sys
import unittest
from contextlib import redirect_stdout

from tests import _path  # noqa: F401
from dfbench_client import GameClient, ModelClient, load_task
from plain import harness, prompt
from tests.fakes import FakeGame, FakeModel

BASE = _path.BASE


def task_json(g, m, days, credits=0.5):
    return json.dumps({"schema": "dfbench-task/1", "run_id": "t", "api": "v0", "game_url": g.url,
                       "model": {"base_url": m.url, "name": "fake", "api": "openai-chat", "api_key": "placeholder"},
                       "budget": {"credits": credits, "unit": "USD", "per": "game"},
                       "limits": {"wall_s": 600, "actions_per_game_day": g.k, "max_advance_days": 28},
                       "task": {"name": "fake", "days": days}})


def play(g, m, days, credits=0.5, max_turns=200):
    t = load_task(task_json(g, m, days, credits))
    model = ModelClient(t.model_base_url, t.model_name, retry_sleep_s=0.0, rate_limit_base_s=0.0)
    p = harness.Plain(t, GameClient(t.game_url), model)
    buf = io.StringIO()
    with redirect_stdout(buf):
        stats = p.run(max_turns=max_turns)
    return p, stats, [json.loads(x) for x in buf.getvalue().splitlines()]


class Prompt(unittest.TestCase):
    def test_api_sections(self):
        manual = "# M\n\n## 3. Hidden\nno\n\n## 4. Sites\nW sites\n\n## 5. Tools\nno\n\n## 6. The observation\nobs\n"
        ref = prompt.api_sections(manual)
        self.assertIn("## 4. Sites", ref)
        self.assertIn("## 6. The observation", ref)
        self.assertNotIn("Tools", ref)
        self.assertEqual(prompt.api_sections(None), "")

    def test_no_interpretation(self):
        s = prompt.system_prompt("## 4. Sites\nx\n", {"add_order"})
        self.assertNotIn("stuck_because", s)
        self.assertNotIn("ORDERS BEYOND", s)
        self.assertIn("ORDERS BEYOND", prompt.system_prompt("", {"add_manager_order"}))

    def test_no_strategy(self):
        s = prompt.system_prompt("", {"add_order", "add_manager_order"}).lower()
        for word in ("autochop", "barrel", "brew", "office", "seedwatch", "squad", "civilian_alert", "farm"):
            self.assertNotIn(word, s)


class FullGame(unittest.TestCase):
    def test_a_few_game_days(self):
        with FakeGame(days=12) as g, FakeModel() as m:
            p, stats, lines = play(g, m, 12)
            self.assertTrue(g.game_over)
            self.assertEqual(p.stop_reason, "game_over")
            tools = [x["tool"] for x in g.log]
            self.assertIn("appoint_manager", tools)
            self.assertIn("add_order", tools)
            self.assertEqual(lines[-1]["kind"], "done")
            obs = [x for x in m.requests[-1]["messages"] if x["role"] == "user"]
            self.assertTrue(obs[-1]["content"].startswith("OBSERVATION {"))
            self.assertIn("days_left_in_run", obs[-1]["content"])
            self.assertTrue(all(x["content"] == "OBSERVATION (older, omitted)" for x in obs[:-1]))
            self.assertNotIn("status", json.loads(obs[-1]["content"][len("OBSERVATION "):]))

    def test_order_churn_guard(self):
        order = {"recipe": "brew_drink", "amount": 5, "repeat": "daily", "when": [{"stock": "drink", "below": 40}]}
        other = {**order, "amount": 8}
        seen = {"n": 0, "id": None}

        def churn(messages):
            seen["n"] += 1
            n = seen["n"]
            tools = [x for x in messages if x["role"] == "tool"]
            if n == 1:
                return "add_order", order
            if n == 2:   # cancel the new order at once: refused (fresh)
                seen["id"] = int(re.search(r'"(?:order_)?id": ?(\d+)', tools[-1]["content"]).group(1))
                return "cancel_order", {"order_id": seen["id"]}
            if n == 3:
                return "advance_days", {"days": 3}
            if n == 4:   # 3 days old now: the cancel goes through
                return "cancel_order", {"order_id": seen["id"]}
            if n == 5:   # identical re-add right after: refused
                return "add_order", order
            if n == 6:
                return "add_order", other
            return "advance_days", {"days": 14}
        with FakeGame(days=30) as g, FakeModel(policy=churn) as m:
            _, stats, _ = play(g, m, 30)
            log = [(x["tool"], x["args"]) for x in g.log if x["tool"] != "advance_days"]
            self.assertEqual(log, [("add_order", order), ("cancel_order", {"order_id": seen["id"]}),
                                   ("add_order", other)])
            self.assertEqual(stats["churn_refused"], 2)

    def test_stall_guard(self):
        with FakeGame(days=4) as g, FakeModel(policy=lambda msgs: ("appoint_manager", {})) as m:
            _, stats, _ = play(g, m, 4, max_turns=40)
            self.assertGreaterEqual(stats["stall_advances"], 1)
            self.assertTrue(any(x["tool"] == "advance_days" for x in g.log))

    def test_advance_is_capped(self):
        with FakeGame(days=40) as g, FakeModel(policy=lambda msgs: ("advance_days", {"days": 28})) as m:
            play(g, m, 40, max_turns=3)
            self.assertTrue(all(x["args"]["days"] <= harness.MAX_DAYS for x in g.log if x["tool"] == "advance_days"))

    def test_budget_exhausted_stops(self):
        with FakeGame(days=10) as g, FakeModel(script=[("http", 503, {"error": {"code": "gateway_blocked",
                                                                                 "message": "credits used"}})]) as m:
            p, _, _ = play(g, m, 10)
            self.assertIn(p.stop_reason, ("budget_exhausted", "budget"))

    def test_budget_guard_stops_before_the_gateway_does(self):
        with FakeGame(days=30) as g, FakeModel(price_in=2000.0) as m:
            p, _, _ = play(g, m, 30, credits=0.5)
            self.assertEqual(p.stop_reason, "budget")
            self.assertLess(len(m.requests), 30)

    def test_upstream_timeout_is_retried(self):
        body = {"error": {"code": "upstream_timeout", "message": "provider hung", "retryable": True}}
        with FakeGame(days=6) as g, FakeModel(script=[("http", 504, body, {"Retry-After": "0"})]) as m:
            p, stats, _ = play(g, m, 6)
            self.assertTrue(g.game_over)
            self.assertEqual(stats["api_errors"], 0)

    def test_hands_off_ends_the_harness(self):
        with FakeGame(days=10, hands_off_day=4) as g, FakeModel() as m:
            p, _, _ = play(g, m, 10)
            self.assertEqual(p.stop_reason, "HandsOff")
            self.assertEqual(g.day, 4)


class Entrypoint(unittest.TestCase):
    def test_plain_entrypoint(self):
        with FakeGame(days=8) as g, FakeModel() as m:
            env = {**os.environ, "DFBENCH_TASK": task_json(g, m, 8), "PYTHONPATH": BASE}
            r = subprocess.run([sys.executable, "-m", "plain"], cwd=BASE, env=env, capture_output=True, text=True,
                               timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            lines = [json.loads(x) for x in r.stdout.splitlines()]
            self.assertEqual(lines[0]["kind"], "start")
            self.assertEqual(lines[-1]["kind"], "done")
            self.assertTrue(g.game_over)

    def test_minimal_entrypoint(self):
        with FakeGame(days=8) as g, FakeModel() as m:
            env = {**os.environ, "DFBENCH_TASK": task_json(g, m, 8), "PYTHONPATH": BASE}
            r = subprocess.run([sys.executable, os.path.join("minimal", "harness.py")], cwd=BASE, env=env,
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            self.assertTrue(g.game_over)

    def test_minimal_stops_near_the_credits(self):
        with FakeGame(days=30) as g, FakeModel() as m:
            m.budget_usd = 1e-9                  # spent after the first call
            env = {**os.environ, "DFBENCH_TASK": task_json(g, m, 30), "PYTHONPATH": BASE}
            r = subprocess.run([sys.executable, os.path.join("minimal", "harness.py")], cwd=BASE, env=env,
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr[-2000:])
            self.assertLessEqual(len(m.requests), 2)
            self.assertFalse(g.game_over)

    def test_minimal_prompt_is_small(self):
        with FakeGame(days=2) as g, FakeModel() as m:
            env = {**os.environ, "DFBENCH_TASK": task_json(g, m, 2), "PYTHONPATH": BASE}
            subprocess.run([sys.executable, os.path.join("minimal", "harness.py")], cwd=BASE, env=env,
                           capture_output=True, text=True, timeout=120)
            system = m.requests[0]["messages"][0]["content"]
            self.assertLess(len(system), 300)


if __name__ == "__main__":
    unittest.main()
