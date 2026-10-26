"""dfbench_client against the fake game server and the fake gateway."""
import json
import os
import socket
import tempfile
import threading
import time
import unittest

from tests import _path  # noqa: F401
from dfbench_client import (ActionLimit, BudgetExhausted, ContextTooLong, GameClient, GameOver, GameUnavailable,
                            HandsOff, ModelClient, ModelError, load_task)
from dfbench_client.game import _safe_to_retry
from tests.fakes import FakeGame, FakeModel


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Game(unittest.TestCase):
    def test_task_observe_act(self):
        with FakeGame(days=5) as g:
            c = GameClient(g.url)
            t = c.task()
            self.assertEqual(t["api"], "v0")
            self.assertIn("advance_days", {x["function"]["name"] for x in t["tools"]})
            o = c.observe()
            self.assertEqual(o["days_left"], 5)
            self.assertFalse(o["game_over"])
            r = c.act("appoint_manager", {})
            self.assertTrue(r["ok"])
            self.assertEqual(r["actions_left_today"], 39)
            r = c.act("appoint_manager", {})
            self.assertFalse(r["ok"])
            self.assertEqual(r["error_code"], "already_assigned")
            r = c.advance(2)
            self.assertEqual(r["result"]["advanced_ticks"], 2400)
            self.assertEqual(c.last["day"], 2)

    def test_tool_failure_with_http_error_status_is_a_result(self):
        with FakeGame(days=5, status_on_error=400) as g:
            r = GameClient(g.url).act("cancel_order", {"order_id": 999})
            self.assertFalse(r["ok"])
            self.assertEqual(r["error_code"], "no_such_order")

    def test_action_limit(self):
        with FakeGame(days=5, k=2) as g:
            c = GameClient(g.url)
            c.act("enable_automation", {"name": "autochop"})
            c.act("enable_automation", {"name": "autofarm"})
            with self.assertRaises(ActionLimit) as e:
                c.act("enable_automation", {"name": "seedwatch"})
            self.assertEqual(e.exception.error_code, "action_limit")
            self.assertTrue(c.advance(1)["ok"])   # advance_days is still accepted
            self.assertTrue(c.act("enable_automation", {"name": "seedwatch"})["ok"])

    def test_hands_off_and_game_over(self):
        with FakeGame(days=4, hands_off_day=2) as g:
            c = GameClient(g.url)
            c.advance(3)                         # cut at day A
            self.assertEqual(c.last["day"], 2)
            with self.assertRaises(HandsOff):
                c.act("appoint_manager")
        for status in (200, 409):
            with FakeGame(days=2, status_on_error=status) as g:
                c = GameClient(g.url)
                c.advance(5)
                with self.assertRaises(GameOver):
                    c.act("appoint_manager")

    def test_query_and_events(self):
        with FakeGame(days=12, mood_day=1) as g:
            c = GameClient(g.url)
            self.assertIn("drink", c.query("stocks")["stocks"])
            self.assertEqual(c.query("units")["animals"][0]["race"], "COW")
            r = c.advance(3)
            self.assertEqual(r["result"]["stopped"]["reason"], "strange_mood")
            ev = c.events(since_tick=0)["events"]
            self.assertTrue(any("fey mood" in e["text"] for e in ev))
            self.assertEqual(c.events(since_tick=ev[-1]["tick"] + 1)["events"], [])
            from dfbench_client import GameAPIError
            with self.assertRaises(GameAPIError) as e:
                c.query("nope")
            self.assertEqual(e.exception.status, 404)

    def test_connection_refused_is_retried_then_raises(self):
        c = GameClient(f"http://127.0.0.1:{free_port()}", retries=2, backoff_s=0.01)
        t0 = time.time()
        with self.assertRaises(GameUnavailable):
            c.observe()
        self.assertLess(time.time() - t0, 5)

    def test_retry_reaches_a_server_that_starts_late(self):
        g = FakeGame(days=3)
        c = GameClient(g.url, retries=6, backoff_s=0.05)
        port = g.port
        g.httpd.server_close()   # free the port, then bring a server up on it a moment later
        late = {}

        def start():
            time.sleep(0.3)
            from http.server import ThreadingHTTPServer
            from tests.fakes import _GameHandler
            h = ThreadingHTTPServer(("127.0.0.1", port), _GameHandler)
            h.owner = g
            late["h"] = h
            h.serve_forever()
        threading.Thread(target=start, daemon=True).start()
        try:
            self.assertEqual(c.observe()["days_left"], 3)
        finally:
            for _ in range(50):
                if "h" in late:
                    break
                time.sleep(0.05)
            late["h"].shutdown(); late["h"].server_close()

    def test_post_is_retried_only_when_refused(self):
        import urllib.error
        self.assertTrue(_safe_to_retry("POST", urllib.error.URLError(ConnectionRefusedError())))
        self.assertFalse(_safe_to_retry("POST", urllib.error.URLError(ConnectionResetError())))
        self.assertFalse(_safe_to_retry("POST", socket.timeout()))
        self.assertTrue(_safe_to_retry("GET", socket.timeout()))


class Model(unittest.TestCase):
    def client(self, m, **kw):
        return ModelClient(m.url, "fake", rate_limit_base_s=0.0, retry_sleep_s=0.0, **kw)

    def test_chat_with_tools_and_usage(self):
        with FakeModel(script=[("call", "advance_days", {"days": 2})]) as m:
            c = self.client(m)
            r = c.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function", "function": {"name": "x"}}],
                       tool_choice="required", temperature=0)
            call = r["choices"][0]["message"]["tool_calls"][0]
            self.assertEqual(json.loads(call["function"]["arguments"]), {"days": 2})
            self.assertEqual(m.requests[0]["tool_choice"], "required")
            self.assertEqual(c.usage["calls"], 1)
            self.assertGreater(c.usage["cost_usd"], 0)
            self.assertEqual(c.usage["cost_source"], "gateway")
            self.assertAlmostEqual(c.gateway_status()["spent_usd"], c.usage["cost_usd"], places=5)

    def test_estimated_cost_without_gateway_cost(self):
        with FakeModel(report_cost=False) as m:
            c = self.client(m, prices={"input": 1.0, "output": 4.0})
            c.chat([{"role": "user", "content": "x" * 400}])
            u = c.usage
            self.assertAlmostEqual(u["cost_usd"], (u["prompt_tokens"] * 1 + u["completion_tokens"] * 4) / 1e6)
            self.assertEqual(u["cost_source"], "estimate")

    def test_429_and_5xx_are_retried(self):
        script = [("http", 429, {"error": "slow down"}, {"Retry-After": "0"}), ("http", 503, {"error": "busy"})]
        with FakeModel(script=script) as m:
            c = self.client(m)
            r = c.chat([{"role": "user", "content": "hi"}])
            self.assertTrue(r["choices"])
            self.assertEqual(len(m.requests), 3)
            self.assertEqual(c.usage["rate_limit_waits"], 1)

    def test_gateway_upstream_timeout_is_retried(self):
        t504 = ("http", 504, {"error": {"code": "upstream_timeout", "retryable": True}}, {"Retry-After": "0"})
        with FakeModel(script=[t504, t504]) as m:
            r = self.client(m).chat([{"role": "user", "content": "hi"}])
            self.assertTrue(r["choices"])
            self.assertEqual(len(m.requests), 3)

    def test_gateway_blocked_is_not_retried(self):
        blocked = ("http", 503, {"error": {"code": "gateway_blocked", "reason": "upstream_unreliable"}})
        with FakeModel(script=[blocked] * 3) as m:
            with self.assertRaises(BudgetExhausted):
                self.client(m).chat([{"role": "user", "content": "hi"}])
            self.assertEqual(len(m.requests), 1)

    def test_retries_are_bounded(self):
        with FakeModel(script=[("http", 500, {"error": "down"})] * 10) as m:
            c = self.client(m, max_retries=2)
            with self.assertRaises(ModelError):
                c.chat([{"role": "user", "content": "hi"}])
            self.assertEqual(len(m.requests), 3)

    def test_budget_and_context_errors_are_typed_and_not_retried(self):
        with FakeModel(script=[("http", 402, {"error": {"message": "game credits exhausted"}})]) as m:
            with self.assertRaises(BudgetExhausted):
                self.client(m).chat([{"role": "user", "content": "hi"}])
            self.assertEqual(len(m.requests), 1)
        with FakeModel(script=[("http", 429, {"error": "budget exhausted for this game"})]) as m:
            with self.assertRaises(BudgetExhausted):
                self.client(m).chat([{"role": "user", "content": "hi"}])
        with FakeModel(script=[("http", 400, {"error": "maximum context length is 1000 tokens"})]) as m:
            with self.assertRaises(ContextTooLong):
                self.client(m).chat([{"role": "user", "content": "hi"}])
            self.assertEqual(len(m.requests), 1)

    def test_unreachable_gateway(self):
        c = ModelClient(f"http://127.0.0.1:{free_port()}/v1", "fake", max_retries=1, retry_sleep_s=0.0)
        with self.assertRaises(ModelError):
            c.chat([{"role": "user", "content": "hi"}])
        self.assertIsNone(c.gateway_status())


class TaskEnv(unittest.TestCase):
    T = {"schema": "dfbench-task/1", "run_id": "r1", "api": "v0", "game_url": "http://game:8090",
         "model": {"base_url": "http://gateway:8080/v1", "name": "z-ai/glm-5.3-flash", "api": "openai-chat",
                   "api_key": "placeholder"},
         "budget": {"credits": 0.5, "unit": "USD at the pinned reference prices", "per": "game"},
         "limits": {"wall_s": 5400, "actions_per_game_day": 40, "max_advance_days": 28},
         "task": {"name": "start-year", "days": 336, "goal": "g", "brief": "b", "hands_off": None}}

    def test_json_and_file(self):
        t = load_task(json.dumps(self.T))
        self.assertEqual((t.game_url, t.model_name, t.credits, t.days, t.wall_s),
                         ("http://game:8090", "z-ai/glm-5.3-flash", 0.5, 336, 5400))
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(self.T, f)
        try:
            self.assertEqual(load_task("@" + f.name).run_id, "r1")
            self.assertEqual(load_task(f.name).run_id, "r1")
        finally:
            os.unlink(f.name)

    def test_env_and_errors(self):
        old = os.environ.get("DFBENCH_TASK")
        os.environ["DFBENCH_TASK"] = json.dumps(self.T)
        try:
            self.assertEqual(load_task().task["name"], "start-year")
        finally:
            if old is None:
                del os.environ["DFBENCH_TASK"]
            else:
                os.environ["DFBENCH_TASK"] = old
        with self.assertRaises(ValueError):
            load_task(json.dumps({**self.T, "schema": "other/9"}))
        with self.assertRaises(ValueError):
            load_task("")


if __name__ == "__main__":
    unittest.main()
