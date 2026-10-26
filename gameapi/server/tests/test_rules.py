"""The game server's rules (docs/GAME-API.md §4) on a fake DF and a fake facts layer. No DF.
Run: python3 -m unittest discover -s gameapi/server/tests -t ."""
import json, os, tempfile, threading, unittest, urllib.request, urllib.error

from gameapi.server import rules as R
from gameapi.server.fake import FakeBackend, FakeFacts
from gameapi.server.rules import ApiError, Game

DAY = R.DAY


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make(task=None, **kw):
    d = tempfile.mkdtemp()
    b, f, clock = FakeBackend(**{k: kw.pop(k) for k in ("stops", "die_at") if k in kw}), FakeFacts(), Clock()
    g = Game(b, f, dict({"name": "t", "days": 60}, **(task or {})), out=d, clock=clock, **kw)
    g.start()
    return g, b, f, clock, d


def act(g, tool, args=None):
    try:
        return g.act(tool, args or {})
    except ApiError as e:
        return e.body()


class TestActionLimit(unittest.TestCase):
    def test_k_per_game_day(self):
        g, b, f, *_ = make(K=3)
        for i in range(3):
            self.assertTrue(act(g, "add_order", {"recipe": "brew_drink", "amount": 1})["ok"])
        r = act(g, "add_order", {"recipe": "brew_drink", "amount": 1})
        self.assertEqual(r["error_code"], "action_limit")
        self.assertEqual(len(f.calls), 3)            # the 4th never reached the game
        self.assertEqual(g.actions_left(), 0)
        self.assertTrue(act(g, "advance_days", {"days": 1})["ok"])   # advance is always accepted
        self.assertEqual(g.actions_left(), 3)
        self.assertTrue(act(g, "add_order", {"recipe": "brew_drink", "amount": 1})["ok"])
        self.assertEqual((g.actions_used, g.limit_rejections), (4, 1))

    def test_failed_and_malformed_actions_count(self):
        g, *_ = make(K=2)
        self.assertEqual(act(g, "cancel_order", {"order_id": 9})["error_code"], "no_such_order")
        self.assertEqual(act(g, "add_order", {"recipe": "nope", "amount": 1})["error_code"], "bad_arguments")
        self.assertEqual(act(g, "add_order", {"recipe": "brew_drink", "amount": 1})["error_code"], "action_limit")
        self.assertEqual(g.actions_rejected, 3)

    def test_unknown_tool_does_not_count(self):
        g, *_ = make(K=1)
        self.assertEqual(act(g, "dig_everything")["error_code"], "unknown_tool")
        self.assertTrue(act(g, "add_order", {"recipe": "brew_drink", "amount": 1})["ok"])

    def test_same_day_after_tripwire_keeps_count(self):
        """K is per game-day: an advance a tripwire stops within the same day doesn't reset it."""
        g, b, *_ = make(K=1, stops={1_000_000 + 300: {"reason": "hostile_visible"}})
        self.assertTrue(act(g, "add_order", {"recipe": "brew_drink", "amount": 1})["ok"])
        r = act(g, "advance_days", {"days": 2})
        self.assertEqual(r["result"]["stopped"]["reason"], "hostile_visible")
        self.assertEqual(g.day(), 0)
        self.assertEqual(act(g, "add_order", {"recipe": "brew_drink", "amount": 1})["error_code"], "action_limit")

    def test_undeclared_argument_rejected(self):
        g, *_ = make()
        r = act(g, "add_order", {"recipe": "brew_drink", "amount": 1, "x": 3})
        self.assertEqual(r["error_code"], "bad_arguments")


class TestAdvance(unittest.TestCase):
    def test_bounds(self):
        g, b, *_ = make()
        for bad in (0, 29, -1, "3", 2.5, None):
            self.assertEqual(act(g, "advance_days", {"days": bad})["error_code"], "bad_arguments", bad)
        self.assertEqual(act(g, "advance_days", {})["error_code"], "bad_arguments")
        self.assertEqual(b.advances, [])
        self.assertEqual(act(g, "advance_days", {"days": 28})["result"]["advanced_days"], 28)

    def test_clamped_to_horizon_and_ends(self):
        g, b, *_ = make({"days": 10})
        r = act(g, "advance_days", {"days": 28})
        self.assertEqual(r["result"]["advanced_ticks"], 10 * DAY)
        self.assertEqual((g.end_reason, g.phase), ("horizon", "finalized"))
        self.assertEqual(act(g, "advance_days", {"days": 1})["error_code"], "game_over")
        self.assertEqual(act(g, "add_order", {"recipe": "brew_drink", "amount": 1})["error_code"], "game_over")

    def test_stop_on(self):
        t0 = 1_000_000
        stops = {t0 + DAY: {"reason": "announcement:MIGRANT_ARRIVAL"}, t0 + 2 * DAY: {"reason": "hostile_visible"}}
        g, b, *_ = make(stops=dict(stops))
        r = act(g, "advance_days", {"days": 5, "stop_on": ["hostile_visible"]})["result"]
        self.assertEqual(r["stopped"]["reason"], "hostile_visible")
        self.assertEqual([s["reason"] for s in r["tripwires_ignored"]], ["announcement:MIGRANT_ARRIVAL"])
        self.assertEqual(g.tick, t0 + 2 * DAY)
        g, b, *_ = make(stops=dict(stops))
        r = act(g, "advance_days", {"days": 5, "stop_on": []})["result"]
        self.assertIsNone(r["stopped"])
        self.assertEqual(g.tick, t0 + 5 * DAY)
        g, b, *_ = make(stops=dict(stops))
        r = act(g, "advance_days", {"days": 5})["result"]            # default: every tripwire
        self.assertEqual(r["stopped"]["reason"], "announcement:MIGRANT_ARRIVAL")
        g, b, *_ = make(stops=dict(stops))
        r = act(g, "advance_days", {"days": 5, "stop_on": ["announcement:STRANGE_MOOD"]})["result"]
        self.assertEqual(g.tick, t0 + 5 * DAY)
        self.assertEqual(g.stats["tripwire_stops"], {"announcement": 1, "hostile_visible": 1})
        self.assertEqual(act(g, "advance_days", {"days": 1, "stop_on": ["bogus"]})["error_code"], "bad_arguments")

    def test_lost_fort_ends(self):
        g, b, *_ = make(die_at=1_000_000 + 3 * DAY)
        r = act(g, "advance_days", {"days": 10})
        self.assertEqual(g.end_reason, "fort_lost")
        self.assertTrue(r["game_over"] if "game_over" in r else g.over)
        self.assertEqual(g.summary["days_played"], 3.0)
        self.assertFalse(g.summary["survived_horizon"])


class TestHandsOff(unittest.TestCase):
    def test_window(self):
        g, b, *_ = make({"days": 60, "hands_off_days": 21})
        self.assertEqual(g.envelope()["hands_off_in_days"], 39)
        act(g, "advance_days", {"days": 28})
        r = act(g, "advance_days", {"days": 28})           # cut at A = day 39, then the server runs W
        self.assertTrue(r["result"]["hands_off"])
        self.assertEqual(r["result"]["advanced_days"], 11)
        self.assertEqual(b.advances[1], (1_000_000 + 28 * DAY, 11 * DAY))
        self.assertTrue(all(t <= 7 * DAY for _, t in b.advances[2:]))   # W in 7-day chunks, no harness
        self.assertEqual((g.end_reason, g.tick), ("horizon", 1_000_000 + 60 * DAY))
        self.assertEqual(g.summary["hands_off_from_day"], 39)
        self.assertEqual(g.summary["hands_off_advances"], 3)
        self.assertIsNone(g.summary["cap_hit_day"])

    def test_action_at_a_rejected(self):
        g, *_ = make({"days": 60, "hands_off_days": 21})
        g.tick = g.ho_tick                                    # as if an advance had stopped exactly at A
        self.assertEqual(act(g, "add_order", {"recipe": "brew_drink", "amount": 1})["error_code"], "hands_off")


class TestWallCap(unittest.TestCase):
    def test_between_calls(self):
        g, b, f, clock, d = make(wall_s=100)
        g.touch()
        act(g, "advance_days", {"days": 2})
        clock.t = 101
        R.Watchdog(g).check()
        self.assertEqual((g.end_reason, g.wall_capped), ("wall_cap", True))
        s = json.loads(open(os.path.join(d, "summary.jsonl")).read().splitlines()[-1])
        self.assertTrue(s["wall_capped"])
        self.assertEqual(s["days_played"], 2.0)                # scored at the tick reached
        self.assertEqual(act(g, "advance_days", {"days": 1})["error_code"], "game_over")

    def test_during_advance(self):
        g, b, f, clock, d = make(wall_s=100)
        g.touch()
        dog = R.Watchdog(g)

        def slow(backend, ticks):   # the cap passes while DF runs: the watchdog pauses it
            clock.t = 200
            dog.check()
        b.on_advance = slow
        r = act(g, "advance_days", {"days": 5})
        self.assertEqual(b.interrupted, 1)
        self.assertTrue(r["result"]["wall_capped"])
        self.assertEqual(g.end_reason, "wall_cap")

    def test_throttle_excluded(self):
        g, b, f, clock, d = make(wall_s=100)
        g.touch()
        clock.t = 150
        g.add_throttle(60)                                     # the gateway waited 60 s on provider 429s
        R.Watchdog(g).check()
        self.assertFalse(g.over)
        clock.t = 161
        R.Watchdog(g).check()
        self.assertEqual(g.end_reason, "wall_cap")

    def test_throttle_total_capped_at_elapsed(self):
        g, b, f, clock, d = make(wall_s=100)
        g.touch()
        clock.t = 50
        g.add_throttle(total_s=80)                             # overlapping waits of parallel calls
        self.assertEqual(g.wall_used(), 0)
        g.add_throttle(total_s=30)                             # a lower total never shrinks the exclusion
        self.assertEqual(g.throttle_s, 80)

    def test_gateway_poll(self):
        g, b, f, clock, d = make({"days": 20}, wall_s=100)
        g.touch()
        dog = R.Watchdog(g, gateway_status_url="http://gw/status", finish_on_blocked=True)
        dog.poll_gateway(lambda u: {"throttle_wait_total_s": 12.5, "blocked_reason": None})
        self.assertEqual(g.throttle_s, 12.5)
        self.assertFalse(g.over)
        dog.poll_gateway(lambda u: {"throttle_wait_total_s": 12.5, "blocked_reason": "budget_exhausted"})
        for _ in range(100):
            if g.phase == "finalized":
                break
            threading.Event().wait(0.02)
        self.assertEqual((g.finish_reason, g.end_reason), ("credits_exhausted", "horizon"))

    def test_clock_starts_at_first_call(self):
        g, b, f, clock, d = make(wall_s=100)
        clock.t = 500
        R.Watchdog(g).check()
        self.assertFalse(g.over)


class TestFinish(unittest.TestCase):
    def test_runs_out_horizon(self):
        g, b, *_ = make({"days": 30})
        act(g, "advance_days", {"days": 3})
        h = g.finish("credits_exhausted")
        self.assertEqual((h["phase"], g.end_reason, g.finish_reason), ("finalized", "horizon", "credits_exhausted"))
        self.assertEqual(g.tick, 1_000_000 + 30 * DAY)
        self.assertEqual(g.summary["cap_hit_day"], 3)
        self.assertEqual(g.summary["days_played"], 30.0)
        self.assertTrue(all(t <= 7 * DAY for _, t in b.advances[1:]))
        g.finish("harness_exited")                              # idempotent
        self.assertEqual(g.finish_reason, "credits_exhausted")

    def test_runout_ignores_tripwires_and_stops_on_lost_fort(self):
        g, b, *_ = make({"days": 30}, stops={1_000_000 + DAY: {"reason": "citizen_died"}}, die_at=1_000_000 + 9 * DAY)
        g.finish()
        self.assertEqual(g.end_reason, "fort_lost")
        self.assertEqual(g.tick, 1_000_000 + 9 * DAY)

    def test_runout_time_not_counted(self):
        g, b, f, clock, d = make({"days": 30}, wall_s=100)
        g.touch()
        b.on_advance = lambda *_: setattr(clock, "t", clock.t + 50)
        g.finish()
        self.assertLess(g.wall_used(), 100)
        self.assertFalse(g.wall_capped)


class TestArtifacts(unittest.TestCase):
    def test_row_fields(self):
        g, b, f, clock, d = make({"days": 5, "metrics": {"x": 1}}, key="dfbench/v3|x", harness_digest="sha256:ab")
        act(g, "add_order", {"recipe": "brew_drink", "amount": 1})
        act(g, "advance_days", {"days": 5})
        s = json.loads(open(os.path.join(d, "summary.jsonl")).read())
        for k in ("arm", "k", "crashed", "scenario", "days_played", "days_target", "pop_start", "hands_off_from_day",
                  "citizen_deaths", "food_min", "drink_min", "credited_value_final", "days_sampled",
                  "api", "key", "harness_digest", "wall_capped", "actions_used", "actions_rejected"):
            self.assertIn(k, s)
        self.assertEqual((s["arm"], s["k"], s["api"], s["actions_used"]), ("harness", 0, "v0", 1))
        for ext in ("daily.json", "credit.json", "final.json", "api.jsonl"):
            self.assertTrue(os.path.exists(os.path.join(d, f"harness-0.{ext}")), ext)

    def test_settings_artifacts_token(self):
        from gameapi.server.backend import set_artifacts
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "prefs"))
            p = os.path.join(d, "prefs", "d_init.txt")
            open(p, "w").write("[AUTOSAVE:NONE]\n[ARTIFACTS:YES]\n[X:1]\n")
            self.assertEqual(set_artifacts(d, False), "NO")
            self.assertEqual(open(p).read(), "[AUTOSAVE:NONE]\n[ARTIFACTS:NO]\n[X:1]\n")
            set_artifacts(d, True)
            self.assertIn("[ARTIFACTS:YES]", open(p).read())


class TestSchema(unittest.TestCase):
    def test_subset(self):
        s = {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer", "minimum": 1},
                                                                 "b": {"type": "array", "maxItems": 2,
                                                                       "items": {"type": "string", "enum": ["x"]}}}}
        self.assertIsNone(R.check_schema({"a": 1, "b": ["x"]}, s))
        self.assertIn("required", R.check_schema({}, s))
        self.assertIn(">=", R.check_schema({"a": 0}, s))
        self.assertIn("integer", R.check_schema({"a": True}, s))
        self.assertIn("one of", R.check_schema({"a": 1, "b": ["y"]}, s))
        self.assertIn("more than", R.check_schema({"a": 1, "b": ["x", "x", "x"]}, s))
        self.assertIn("unexpected", R.check_schema({"a": 1, "c": 2}, s))


class TestHTTP(unittest.TestCase):
    def setUp(self):
        from gameapi.server import http_api
        self.g, self.b, *_ = make({"days": 10})
        self.srv = http_api.serve(self.g, "127.0.0.1", 0, admin_token="s3cret")
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()

    def req(self, path, body=None, headers=None):
        r = urllib.request.Request(self.url + path, data=None if body is None else json.dumps(body).encode(),
                                   headers=headers or {}, method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_endpoints(self):
        st, t = self.req("/task")
        self.assertEqual(st, 200)
        names = [x["function"]["name"] for x in t["tools"]]
        self.assertEqual(names.count("advance_days"), 1)       # the server's, not the facts layer's
        self.assertEqual(t["rules"]["actions_per_game_day"], 40)
        for k in ("day", "tick", "days_left", "game_over"):
            self.assertIn(k, t)
        self.assertIsNone(self.g.t_first)                       # /task doesn't start the wall clock
        st, o = self.req("/observe")
        self.assertEqual(o["observation"]["obs_schema"], "6-fake")
        self.assertIsNotNone(self.g.t_first)
        st, a = self.req("/act", {"tool": "add_order", "args": {"recipe": "brew_drink", "amount": 1}})
        self.assertEqual((a["ok"], a["actions_left_today"]), (True, 39))
        st, q = self.req("/query/stocks?n=3")
        self.assertEqual(q["result"]["params"], {"n": 3})
        st, q = self.req("/query/nope")
        self.assertEqual((st, q["error_code"]), (404, "unknown_query"))
        st, e = self.req("/events?since_tick=7")
        self.assertEqual(e["events"][0]["tick"], 7)
        st, _ = self.req("/finish", {"reason": "harness_exited"})
        self.assertEqual(st, 403)                               # admin only
        st, h = self.req("/finish?wait=1", {"reason": "harness_exited"}, {"X-Admin-Token": "s3cret"})
        self.assertEqual((st, h["phase"], h["end_reason"]), (200, "finalized", "horizon"))
        log = [json.loads(l) for l in open(os.path.join(self.g.out, "harness-0.api.jsonl"))]
        self.assertEqual([x["path"] for x in log][:3], ["/task", "/observe", "/act"])
        self.assertTrue(all("latency_ms" in x and "tick" in x for x in log))

    def test_bad_body(self):
        r = urllib.request.Request(self.url + "/act", data=b"{nope", method="POST")
        try:
            urllib.request.urlopen(r)
            self.fail("expected 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_async_finish(self):
        st, h = self.req("/finish", {"reason": "credits_exhausted"}, {"X-Admin-Token": "s3cret"})
        self.assertTrue(h["accepted"])
        for _ in range(100):
            if self.g.phase == "finalized":
                break
            threading.Event().wait(0.05)
        self.assertEqual(self.req("/health")[1]["phase"], "finalized")


if __name__ == "__main__":
    unittest.main()


class TestFactsAdapter(unittest.TestCase):
    """The adapter over gameapi/facts, statically (no DF): what the server serves and the key hashes."""

    def setUp(self):
        from gameapi.server import adapter
        if not adapter.facts_available():
            self.skipTest("no gameapi/facts")
        self.A = adapter

    def test_load_prefers_facts(self):
        f = self.A.load()
        from gameapi.facts import OBS_SCHEMA
        self.assertEqual((f.NAME, f.OBS_SCHEMA, f.STRICT_ARGS), ("gameapi.facts", OBS_SCHEMA, False))
        names = {t["function"]["name"] for t in f.key_tools()}
        self.assertNotIn("advance_days", names)              # the server's
        self.assertTrue({"slaughter", "build_workshop", "add_order"} <= names)
        self.assertEqual({q["name"] for q in f.queries()}, set(f.F.QUERIES))
        self.assertEqual(self.A.load("legacy").NAME if False else "legacy-harness2", self.A.Legacy.NAME)

    def test_key_files(self):
        name, tools, obs = self.A.key_files()
        self.assertEqual(name, "gameapi.facts")
        self.assertIn("gameapi/facts/lua/act.lua", tools)
        self.assertIn("gameapi/facts/lua/observe.lua", obs)
        self.assertFalse(any("check_in_game" in p or "/tests/" in p for p in tools))
        self.assertEqual(self.A.key_files("legacy")[0], "legacy-harness2")

    def test_manual_is_the_reference_manual(self):
        with open(os.path.join(self.A.ROOT, "gameapi", "manual", "MANUAL.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(self.A.load().manual(), text)
        self.assertIn("gameapi/manual/MANUAL.md", self.A.key_files()[1])   # the served text is in the v3 key
        for tool in ("add_manager_order", "slaughter", "build_workshop", "advance_days", "create_burrow"):
            self.assertIn(f"`{tool} ", text)                                # every tool is described
        for q in self.A.load().F.QUERIES:
            self.assertIn(f"| `{q}` |", text)                               # every query is described

    def test_task_serves_the_manual(self):
        """GET /task returns gameapi/manual/MANUAL.md as `manual` (the Facts adapter, DF stubbed out)."""
        from gameapi.server import http_api
        A = self.A

        class NoDF:   # dfhack-run stand-in: every probe fails, so build_workshop's enum falls back to the frozen 9
            def run(self, *a, **k):
                return ""

        class StubbedFacts(A.Facts):
            def reset(self):
                self.g = self.F.Game(df=NoDF())

        d = tempfile.mkdtemp()
        g = Game(FakeBackend(), StubbedFacts(), {"name": "t", "days": 10}, out=d, clock=Clock())
        g.start()
        srv = http_api.serve(g, "127.0.0.1", 0, admin_token="s3cret")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/task") as r:
                t = json.loads(r.read())
        finally:
            srv.shutdown()
        self.assertEqual(t["manual"], A.reference_manual())
        self.assertTrue(t["manual"].startswith("# Game API v0 reference manual"))
        names = {x["function"]["name"] for x in t["tools"]}
        self.assertTrue({"add_manager_order", "slaughter", "advance_days"} <= names)

    def test_non_strict_args_left_to_facts(self):
        sch = {"type": "object", "properties": {"site": {"type": "string"}}}
        self.assertIsNone(R.check_schema({"x": 1, "y": 2, "z": 3}, sch, strict=False))
        self.assertIsNotNone(R.check_schema({"x": 1}, sch, strict=True))
