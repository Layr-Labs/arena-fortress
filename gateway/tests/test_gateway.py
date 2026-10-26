"""Gateway tests against a fake upstream (local HTTP server). No network, no key.

  python3 -m unittest discover -s gateway/tests -v
"""
import hashlib, json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import gateway  # noqa: E402

MODEL = "z-ai/glm-5.3-flash"
KEY = "sk-test-SECRET-123"  # gitleaks:allow (a fake key: the tests check it never appears in logs)
PRICES = os.path.join(os.path.dirname(HERE), "prices.json")


def read(path, mode="r"):
    with open(path, mode) as f:
        return f.read()


def usage(pt=1000, cached=0, ct=100, reasoning=0, cost=None):
    u = {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct,
         "prompt_tokens_details": {"cached_tokens": cached}, "completion_tokens_details": {"reasoning_tokens": reasoning}}
    if cost is not None:
        u["cost"] = cost
    return u


def ok_body(u=None, provider="Together"):
    b = {"id": "gen-1", "provider": provider, "model": MODEL, "object": "chat.completion",
         "choices": [{"index": 0, "finish_reason": "tool_calls",
                      "message": {"role": "assistant", "content": "", "tool_calls": [
                          {"id": "c1", "type": "function", "function": {"name": "observe", "arguments": "{}"}}]}}]}
    if u is not False:
        b["usage"] = u or usage()
    return b


class FakeUpstream:
    """Replies from a script: each item is (status, body_dict_or_bytes, headers, delay_s[, body_delay_s]):
    delay_s before the headers, body_delay_s between the headers and the body (a provider that hangs after its 200),
    with a few whitespace bytes trickled every 0.1 s when body_delay_s is negative."""

    def __init__(self):
        self.requests, self.script, self.default = [], [], (200, ok_body(), {}, 0)
        self.lock = threading.Lock()
        self.active = self.max_active = 0
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                with fake.lock:
                    fake.requests.append({"path": self.path, "headers": dict(self.headers), "body": json.loads(body)})
                    item = fake.script.pop(0) if fake.script else fake.default
                    fake.active += 1
                    fake.max_active = max(fake.max_active, fake.active)
                try:
                    status, b, hdrs, delay, *rest = item
                    body_delay = rest[0] if rest else 0
                    time.sleep(delay)
                    data = b if isinstance(b, bytes) else json.dumps(b).encode()
                    pad = b" " * 40 if body_delay < 0 else b""
                    self.send_response(status)
                    for k, v in hdrs.items():
                        self.send_header(k, v)
                    self.send_header("Content-Length", str(len(data) + len(pad)))
                    self.end_headers()
                    self.wfile.flush()
                    if body_delay < 0:                  # trickle keep-alive whitespace, then the body
                        for i in range(len(pad)):
                            self.wfile.write(b" ")
                            self.wfile.flush()
                            time.sleep(-body_delay / len(pad))
                    else:
                        time.sleep(body_delay)
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):  # the gateway abandoned the call
                    pass
                finally:
                    with fake.lock:
                        fake.active -= 1

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/api/v1"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class GatewayTest(unittest.TestCase):
    def setUp(self):
        self.up = FakeUpstream()
        self.tmp = tempfile.mkdtemp()
        self.ledger = os.path.join(self.tmp, "usage.jsonl")
        self.status_file = os.path.join(self.tmp, "status.json")
        self.start()

    def start(self, *extra, budget="0.50"):
        os.environ["TEST_GW_KEY"] = KEY
        cfg = gateway.parse_config([
            "--listen", "127.0.0.1:0", "--upstream", self.up.url, "--allow-http-upstream", "--key-env", "TEST_GW_KEY",
            "--prices", PRICES, "--budget", budget, "--ledger", self.ledger, "--status-file", self.status_file,
            "--run-id", "t", "--retry-base", "0.05", "--retry-after-cap", "0.3", *extra])
        self.srv = gateway.make_server(cfg)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()

    def tearDown(self):
        self.stop()
        self.up.close()

    def post(self, body, path="/v1/chat/completions", raw=None):
        data = raw if raw is not None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data, {"Content-Type": "application/json",
                                                              "Authorization": "Bearer placeholder"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def status(self):
        with urllib.request.urlopen(self.base + "/status", timeout=10) as r:
            return json.loads(r.read())

    def rows(self):
        if not os.path.exists(self.ledger):
            return []
        with open(self.ledger) as f:
            return [json.loads(l) for l in f]

    def chat(self, **kw):
        b = {"model": MODEL, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 50}
        b.update(kw)
        return self.post(b)

    # ---- tests ------------------------------------------------------------------------------------------------
    def test_pass_through(self):
        tools = [{"type": "function", "function": {"name": "observe", "parameters": {"type": "object"}}}]
        st, resp = self.chat(tools=tools, tool_choice="required", temperature=0.3, seed=7,
                             reasoning={"effort": "high"})
        self.assertEqual(st, 200)
        self.assertEqual(resp, ok_body())                       # body returned unchanged
        r = self.up.requests[0]
        self.assertEqual(r["path"], "/api/v1/chat/completions")
        self.assertEqual(r["headers"]["Authorization"], "Bearer " + KEY)  # placeholder replaced
        b = r["body"]
        self.assertEqual((b["tools"], b["tool_choice"], b["temperature"], b["seed"], b["max_tokens"], b["reasoning"]),
                         (tools, "required", 0.3, 7, 50, {"effort": "high"}))
        self.assertEqual(b["usage"], {"include": True})
        self.assertIs(b["stream"], False)
        row = self.rows()[0]
        self.assertEqual(row["outcome"], "ok")
        self.assertEqual(row["provider"], "Together")
        self.assertFalse(row["provider_mismatch"])
        self.assertEqual(row["reasoning"], {"effort": "high"})
        self.assertNotIn('"messages"', json.dumps(row))           # no prompt text by default
        self.assertNotIn("hi\"", json.dumps(row))

    def test_model_allowlist(self):
        for m in ("openai/gpt-4o", "z-ai/glm-5.3-flash:nitro", "z-ai/glm-5.3", None):
            st, resp = self.chat(model=m)
            self.assertEqual(st, 400)
            self.assertEqual(resp["error"]["code"], "model_not_allowed")
        self.assertEqual(self.up.requests, [])
        self.assertEqual([r["outcome"] for r in self.rows()], ["refused_model"] * 4)

    def test_provider_override_and_stripping(self):
        st, _ = self.chat(provider={"order": ["openai"], "allow_fallbacks": True}, models=["openai/gpt-4o"],
                          route="fallback", transforms=["middle-out"], user="x", plugins=[{"id": "web"}],
                          web_search_options={}, preset="p", usage={"include": False}, api_key="k", foo=1)
        self.assertEqual(st, 200)
        b = self.up.requests[0]["body"]
        self.assertEqual(b["provider"], {"order": ["together"], "allow_fallbacks": False})
        for k in ("models", "route", "transforms", "user", "plugins", "web_search_options", "preset", "api_key", "foo"):
            self.assertNotIn(k, b)
        self.assertEqual(b["usage"], {"include": True})
        self.assertEqual(self.rows()[0]["dropped_fields"],
                         sorted(["provider", "models", "route", "transforms", "user", "plugins", "web_search_options",
                                 "preset", "usage", "api_key", "foo"]))

    def test_provider_mismatch_recorded(self):
        self.up.default = (200, ok_body(provider="Fireworks"), {}, 0)
        self.chat()
        self.assertTrue(self.rows()[0]["provider_mismatch"])
        self.assertEqual(self.status()["provider_mismatches"], 1)

    def test_pricing(self):
        self.up.default = (200, ok_body(usage(1_000_000, 200_000, 100_000, 40_000, cost=0.1761)), {}, 0)
        self.chat()
        row = self.rows()[0]
        self.assertAlmostEqual(row["cost_usd"], 0.8 * 0.15 + 0.2 * 0.03 + 0.1 * 0.50, places=12)   # 0.176
        self.assertEqual(row["openrouter_cost_usd"], 0.1761)
        self.assertEqual((row["prompt_tokens"], row["cached_tokens"], row["completion_tokens"],
                          row["reasoning_tokens"]), (1_000_000, 200_000, 100_000, 40_000))
        h = "sha256:" + hashlib.sha256(read(PRICES, "rb")).hexdigest()
        self.assertEqual(row["price_table_hash"], h)
        s = self.status()
        self.assertEqual(s["price_table_hash"], h)
        self.assertAlmostEqual(s["spent_usd"], 0.176)
        self.assertEqual(s["tokens"], {"prompt": 1_000_000, "cached": 200_000, "completion": 100_000,
                                       "reasoning": 40_000})

    def test_budget_crossing_and_refusal(self):
        self.stop()
        self.start(budget="0.01")
        self.up.default = (200, ok_body(usage(20_000, 0, 10_000)), {}, 0)       # 0.003 + 0.005 = 0.008
        self.assertEqual(self.chat()[0], 200)
        self.assertEqual(self.chat()[0], 200)                                   # crosses: 0.016, counted in full
        st, resp = self.chat()
        self.assertEqual(st, 402)
        self.assertEqual(resp["error"]["code"], "budget_exhausted")
        self.assertEqual(len(self.up.requests), 2)
        s = self.status()
        self.assertAlmostEqual(s["spent_usd"], 0.016)
        self.assertEqual((s["blocked"], s["blocked_reason"], s["calls"], s["calls_refused"]),
                         (True, "budget_exhausted", 2, 1))
        self.assertEqual([r["outcome"] for r in self.rows()], ["ok", "ok", "refused_budget_exhausted"])
        self.assertEqual(json.loads(read(self.status_file))["blocked_reason"], "budget_exhausted")

    def test_missing_usage_fails_closed(self):
        self.up.script = [(200, ok_body(False), {}, 0)]
        st, resp = self.chat()
        self.assertEqual((st, resp["error"]["code"]), (502, "usage_missing"))
        st, resp = self.chat()
        self.assertEqual((st, resp["error"]["code"], resp["error"]["reason"]), (503, "gateway_blocked", "usage_missing"))
        self.assertEqual(len(self.up.requests), 1)
        s = self.status()
        self.assertEqual((s["blocked_reason"], s["usage_unknown_calls"]), ("usage_missing", 1))
        row = self.rows()[0]
        self.assertEqual(row["outcome"], "usage_missing")
        self.assertIsNone(row["cost_usd"])
        self.assertGreater(row["cost_upper_bound_usd"], 0)

    def test_bad_usage_fails_closed(self):
        self.up.script = [(200, ok_body({"prompt_tokens": "12", "completion_tokens": 3}), {}, 0)]
        self.assertEqual(self.chat()[0], 502)
        self.assertEqual(self.status()["blocked_reason"], "usage_missing")

    def test_hung_call_is_charged_and_retryable(self):
        # no headers within the idle limit: abandoned, charged the prompt bound plus capped output, 504, not blocked
        self.stop()
        self.start("--upstream-timeout", "0.3", "--abandon-output-tokens", "1000")
        self.up.script = [(200, ok_body(), {}, 1.0)]
        st, resp = self.chat(max_tokens=4000)
        self.assertEqual((st, resp["error"]["code"], resp["error"]["failure"]), (504, "upstream_timeout", "idle_timeout"))
        self.assertTrue(resp["error"]["retryable"])
        row = self.rows()[0]
        self.assertEqual((row["outcome"], row["cost_basis"]), ("upstream_timeout", "abandoned_estimate"))
        in_tok = row["request_bytes"] + 256 + 16 * row["n_messages"]
        self.assertAlmostEqual(row["cost_usd"], (in_tok * 0.15 + 1000 * 0.50) / 1e6, places=9)
        self.assertGreaterEqual(row["throttle_wait_s"], 0.29)      # hung time is provider time (wall cap)
        s = self.status()
        self.assertEqual((s["blocked_reason"], s["upstream_timeouts"], s["usage_unknown_calls"]), (None, 1, 0))
        self.assertAlmostEqual(s["spent_usd"], row["cost_usd"], places=8)
        self.assertGreaterEqual(s["throttle_wait_total_s"], 0.29)
        self.assertEqual(self.chat()[0], 200)                       # the harness retries and goes on

    def test_deadline_after_early_headers(self):
        # a 200 sent at once, then whitespace trickled for longer than the deadline: abandoned at the deadline
        self.stop()
        self.start("--upstream-timeout", "5", "--upstream-deadline", "0.5")
        self.up.script = [(200, ok_body(), {}, 0, -3.0)]
        t = time.monotonic()
        st, resp = self.chat()
        self.assertLess(time.monotonic() - t, 2.5)
        self.assertEqual((st, resp["error"]["failure"]), (504, "deadline"))
        self.assertEqual(self.rows()[0]["outcome"], "upstream_timeout")

    def test_provider_reported_timeout_charges_prompt_only(self):
        # OpenRouter's own cut-off: a 200 whose body is an error, no choices, no usage
        self.up.script = [(200, {"error": {"code": 524, "message": "A Timeout Occurred"}}, {}, 0)]
        st, resp = self.chat()
        self.assertEqual((st, resp["error"]["code"], resp["error"]["failure"]), (504, "upstream_timeout", "provider_reported"))
        row = self.rows()[0]
        in_tok = row["request_bytes"] + 256 + 16 * row["n_messages"]
        self.assertEqual(row["cost_basis"], "prompt_estimate")
        self.assertAlmostEqual(row["cost_usd"], in_tok * 0.15 / 1e6, places=9)
        self.assertEqual(row["error"], "A Timeout Occurred")
        self.assertIsNone(self.status()["blocked_reason"])

    def test_content_without_usage_still_fails_closed(self):
        self.up.script = [(200, ok_body(False), {}, 0)]
        self.assertEqual(self.chat()[1]["error"]["code"], "usage_missing")
        self.assertEqual(self.status()["blocked_reason"], "usage_missing")

    def test_too_many_timeouts_block_the_game(self):
        self.stop()
        self.start("--max-upstream-timeouts", "2")
        fail = (200, {"error": {"message": "Upstream error from Together: stream ended unexpectedly"}}, {}, 0)
        self.up.script = [fail] * 3
        self.assertEqual([self.chat()[0] for _ in range(3)], [504, 504, 504])
        self.assertEqual(self.status()["blocked_reason"], "upstream_unreliable")
        st, resp = self.chat()
        self.assertEqual((st, resp["error"]["reason"]), (503, "upstream_unreliable"))
        self.assertEqual(len(self.up.requests), 3)
        # a restarted gateway replays the ledger: still blocked
        self.stop()
        self.start("--max-upstream-timeouts", "2")
        self.assertEqual(self.status()["blocked_reason"], "upstream_unreliable")

    def test_long_output_timeouts_are_the_harness_s(self):
        # red team: asking for long generations on purpose must not re-roll a game as infra, nor buy wall time
        self.stop()
        self.start("--max-upstream-timeouts", "2", "--infra-max-output-tokens", "8192")
        fail = (200, {"error": {"code": 524, "message": "A Timeout Occurred"}}, {}, 0)
        self.up.script = [fail] * 4
        for _ in range(4):
            st, resp = self.chat(max_tokens=200_000)
            self.assertEqual(st, 504)
            self.assertFalse(resp["error"]["counted_as_infra"])
        s = self.status()
        self.assertEqual((s["blocked_reason"], s["upstream_timeouts"]), (None, 0))
        self.assertTrue(all(r["harness_attributable"] for r in self.rows()))
        st, resp = self.chat()                                   # an omitted max_tokens is the model's maximum
        self.assertEqual(st, 200)
        self.up.script = [fail]
        self.assertTrue(self.chat(max_tokens=None)[1]["error"]["counted_as_infra"] is False)

    def test_lone_call_is_clamped_to_the_budget(self):
        # red team: an idle gateway used to admit one call of any size, so a huge max_tokens or n ran past the budget
        self.stop()
        self.start(budget="0.01")
        st, _ = self.chat(max_tokens=900_000, n=4)
        self.assertEqual(st, 200)
        b = self.up.requests[0]["body"]
        row = self.rows()[0]
        self.assertEqual(b["max_tokens"], row["clamped_max_tokens"])
        self.assertLess(b["max_tokens"], 900_000)
        self.assertLessEqual(row["reservation_usd"], 0.01 + 1e-12)
        # nothing fits: refused for this call, the game is not blocked
        self.stop()
        self.ledger = os.path.join(self.tmp, "usage2.jsonl")      # a fresh game
        self.start(budget="0.0000001")
        st, resp = self.chat()
        self.assertEqual((st, resp["error"]["code"]), (402, "insufficient_budget"))
        self.assertIsNone(self.status()["blocked_reason"])
        self.assertEqual(len(self.up.requests), 1)

    def test_only_text_and_function_tools_are_forwarded(self):
        # red team: image_url / file parts make the provider fetch a URL (a channel out of the game network)
        bad = [{"messages": [{"role": "user", "content": [{"type": "image_url",
                                                            "image_url": {"url": "https://x.example/?d=1"}}]}]},
               {"messages": [{"role": "user", "content": [{"type": "file", "file": {"file_data": "x"}}]}]},
               {"tools": [{"type": "web_search"}]},
               {"messages": [{"role": "user", "content": {"type": "text", "text": "hi"}}]}]
        for kw in bad:
            st, resp = self.chat(**kw)
            self.assertEqual((st, resp["error"]["code"]), (400, "content_not_allowed"), kw)
        self.assertEqual(self.up.requests, [])
        st, _ = self.chat(messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]},
                                    {"role": "assistant", "content": None, "tool_calls": []}])
        self.assertEqual(st, 200)

    def test_oversized_response_is_charged_not_infra(self):
        # red team: n and logprobs can inflate a response past the size limit; that used to block the game as infra
        self.stop()
        self.start("--max-response-bytes", "2000")
        big = ok_body()
        big["choices"][0]["message"]["content"] = "x" * 5000
        self.up.script = [(200, big, {}, 0)]
        st, resp = self.chat(max_tokens=100)
        self.assertEqual((st, resp["error"]["code"]), (502, "response_too_large"))
        row = self.rows()[0]
        self.assertEqual((row["cost_basis"], row["harness_attributable"]), ("reservation_oversized", True))
        self.assertAlmostEqual(row["cost_usd"], row["reservation_usd"], places=8)
        s = self.status()
        self.assertEqual((s["blocked_reason"], s["usage_unknown_calls"]), (None, 0))
        self.assertEqual(self.chat()[0], 200)

    def test_429_retry_and_throttle_accounting(self):
        self.up.script = [(429, {"error": {"message": "rate limited"}}, {"Retry-After": "0.2"}, 0),
                          (503, {"error": {"message": "busy"}}, {}, 0.1)]
        t = time.monotonic()
        st, _ = self.chat()
        self.assertEqual(st, 200)
        row = self.rows()[0]
        self.assertEqual((row["attempts"], row["retry_statuses"]), (3, [429, 503]))
        # 0.2 (Retry-After) + 0.1 (503 attempt) + 0.1 (backoff 0.05 * 2) of throttle
        self.assertGreaterEqual(row["throttle_wait_s"], 0.39)
        self.assertLess(row["throttle_wait_s"], time.monotonic() - t)
        self.assertEqual(self.status()["throttle_wait_total_s"], row["throttle_wait_s"])
        self.assertEqual(self.status()["retries"], 2)
        # retries exhausted: the last 429 goes back to the harness, all of it counted as throttling
        self.up.script = [(429, {"error": {"message": "rate limited"}}, {}, 0)] * 6
        st, resp = self.chat()
        self.assertEqual((st, resp["error"]["message"]), (429, "rate limited"))
        row = self.rows()[1]
        self.assertEqual((row["outcome"], row["attempts"], row["cost_usd"]), ("upstream_error", 6, 0.0))
        self.assertGreaterEqual(row["throttle_wait_s"], 0.05 + 0.1 + 0.2 + 0.3 + 0.3)
        self.assertFalse(self.status()["blocked"])

    def test_concurrency_capped_at_four_and_queue_time_is_the_harness_s(self):
        self.up.default = (200, ok_body(usage(100, 0, 10)), {}, 0.3)
        with ThreadPoolExecutor(8) as ex:
            results = list(ex.map(lambda _: self.chat(max_tokens=20)[0], range(8)))
        self.assertEqual(results, [200] * 8)
        self.assertEqual(self.up.max_active, 4)
        rows = self.rows()
        self.assertTrue(any(r["queue_wait_s"] > 0.2 for r in rows))
        self.assertTrue(all(r["throttle_wait_s"] == 0 for r in rows))     # queueing is not throttling

    def test_429s_under_the_game_s_own_parallelism_are_the_harness_s(self):
        # red team: a harness driving 429s on the shared key with many parallel calls must not buy wall time or
        # an infra re-run; a 429 on a call admitted with <= 2 of the game's calls in flight is the provider's
        self.up.default = (200, ok_body(usage(100, 0, 10)), {}, 0.8)
        with ThreadPoolExecutor(4) as ex:
            slow = [ex.submit(self.chat, max_tokens=20) for _ in range(3)]
            time.sleep(0.3)
            self.up.script = [(429, {"error": {"message": "rate limited"}}, {"Retry-After": "0.2"}, 0),
                              (200, ok_body(usage(100, 0, 10)), {}, 0)]
            st, _ = self.chat(max_tokens=20)
            [f.result() for f in slow]
        self.assertEqual(st, 200)
        row = [r for r in self.rows() if r.get("retry_statuses") == [429]][0]
        self.assertEqual(row["inflight_at_admit"], 4)
        self.assertEqual(row["throttle_wait_s"], 0)
        self.assertGreaterEqual(row["throttle_wait_harness_s"], 0.2)
        self.assertEqual(self.status()["throttle_wait_total_s"], 0)
        # alone: the provider's (excluded from the wall cap, counted towards the throttling infra rule)
        self.up.script = [(429, {"error": {"message": "rate limited"}}, {"Retry-After": "0.2"}, 0)]
        self.up.default = (200, ok_body(usage(100, 0, 10)), {}, 0)
        self.chat(max_tokens=20)
        row = self.rows()[-1]
        self.assertEqual((row["inflight_at_admit"], row["throttle_wait_harness_s"]), (1, 0))
        self.assertGreaterEqual(row["throttle_wait_s"], 0.2)

    def test_client_error_not_retried_not_billed(self):
        self.up.script = [(400, {"error": {"message": "bad tool schema"}}, {}, 0)]
        st, resp = self.chat()
        self.assertEqual((st, resp["error"]["message"]), (400, "bad tool schema"))
        self.assertEqual(len(self.up.requests), 1)
        self.assertEqual(self.status()["spent_usd"], 0)

    def test_redirect_not_followed(self):
        self.up.script = [(302, b"", {"Location": "http://example.invalid/steal"}, 0)]
        st, resp = self.chat()
        self.assertEqual((st, resp["error"]["code"]), (502, "upstream_redirect"))
        self.assertEqual(len(self.up.requests), 1)

    def test_concurrency_bounded_overshoot(self):
        # each call: reservation ~ (body+272)*0.15e-6 + 1000*0.5e-6 ~ 0.00056; actual 0.0005
        self.stop()
        self.start(budget="0.002")
        self.up.default = (200, ok_body(usage(1000, 0, 700)), {}, 0.2)   # 0.00015 + 0.00035 = 0.0005
        with ThreadPoolExecutor(12) as ex:
            results = list(ex.map(lambda _: self.chat(max_tokens=1000)[0], range(12)))
        s = self.status()
        self.assertLessEqual(s["spent_usd"], 0.002 + 0.0005 + 1e-12)       # at most one call's worth over
        self.assertGreater(self.up.max_active, 1)                            # tight max_tokens: parallel
        self.assertEqual(results.count(200), s["calls"])
        self.assertEqual(results.count(402), 12 - s["calls"])
        self.assertEqual(s["reserved_usd"], 0)
        self.assertEqual(s["inflight"], 0)

    def test_concurrency_without_max_tokens_serialises(self):
        self.up.default = (200, ok_body(usage(1000, 0, 100)), {}, 0.1)
        with ThreadPoolExecutor(4) as ex:
            results = list(ex.map(lambda _: self.chat(max_tokens=None)[0], range(4)))
        self.assertEqual(results, [200] * 4)
        self.assertEqual(self.up.max_active, 1)   # reservation = model max output: can't fit two in $0.50

    def test_restart_replays_ledger(self):
        self.stop()
        self.start(budget="0.01")
        self.up.default = (200, ok_body(usage(20_000, 0, 10_000)), {}, 0)
        self.chat(); self.chat()
        self.stop()
        self.start(budget="0.01")
        s = self.status()
        self.assertAlmostEqual(s["spent_usd"], 0.016)
        self.assertEqual(self.chat()[0], 402)
        self.assertEqual(self.rows()[-1]["seq"], 3)

    def test_request_limits_and_endpoints(self):
        self.stop()
        self.start("--max-body-bytes", "1000")
        st, resp = self.chat(messages=[{"role": "user", "content": "x" * 2000}])
        self.assertEqual((st, resp["error"]["code"]), (413, "request_too_large"))
        self.assertEqual(self.chat(stream=True)[1]["error"]["code"], "stream_unsupported")
        self.assertEqual(self.post(None, raw=b"not json")[0], 400)
        self.assertEqual(self.post({"model": MODEL}, path="/v1/models")[0], 404)
        for p in ("/v1/models", "/", "/status/../x"):
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(self.base + p, timeout=5)
            self.assertEqual(e.exception.code, 404)
        self.assertEqual(self.up.requests, [])

    def test_key_never_written(self):
        self.up.script = [(200, ok_body(False), {}, 0)]
        self.chat(); self.chat()
        for path in (self.ledger, self.status_file):
            self.assertNotIn(KEY, read(path))
        self.assertNotIn(KEY, json.dumps(self.status()))
        self.assertNotIn("TEST_GW_KEY", os.environ)    # popped at start

    def test_debug_flag_logs_prompts(self):
        self.stop()
        self.start("--debug")
        self.chat()
        row = self.rows()[0]
        self.assertEqual(row["debug_request"]["messages"][0]["content"], "hi")
        self.assertNotIn(KEY, read(self.ledger))

    def test_bad_price_table_rejected(self):
        bad = os.path.join(self.tmp, "p.json")
        json.dump({"unit": "per_million_tokens", "models": {MODEL: {"input": 1, "cached_input": 1, "output": 1,
                   "max_output_tokens": 10, "provider": {"order": ["together"], "allow_fallbacks": True}}}},
                  open(bad, "w"))  # noqa: SIM115
        with self.assertRaises(ValueError):
            gateway.load_prices(bad)


if __name__ == "__main__":
    unittest.main()
