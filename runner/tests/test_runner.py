"""Runner tests: the fake game's rules, trusted scoring on fake artifacts, compose isolation, and (DFBENCH_E2E=1) one
fake game end to end through Docker Compose.

  python3 -m unittest discover -s runner/tests -v          # from the repo root
  DFBENCH_E2E=1 python3 -m unittest runner.tests.test_runner.E2E -v
"""
import argparse, json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.dirname(HERE)
ROOT = os.path.dirname(RUNNER)
sys.path[:0] = [RUNNER, os.path.join(RUNNER, "fakes")]

import fake_game  # noqa: E402
from dfbenchlib import score as S  # noqa: E402
from dfbenchlib.suite import expand, load_suite  # noqa: E402

SUITE = os.path.join(RUNNER, "suites", "season0.json")


def make_game(spec, out):
    sc = json.load(open(os.path.join(ROOT, spec["scenario"])))
    cfg = {"arm": "harness", "k": spec["k"], "days": spec["days"], "artifacts_dir": out,
           "rules": {"wall_s": spec["wall_s"]}, "harness_digest": "sha256:test"}
    return fake_game.Game(cfg, sc)


def play(g, policy):
    """policy 'good': the fake gateway's opening then 7-day advances; 'noop': advances only."""
    if policy == "good":
        for tool, args in [("add_order", {"recipe": "brew_drink", "amount": 10}),
                           ("build_workshop", {"type": "Still", "site": "W1"}),
                           ("build_farm", {"site": "F1"}), ("build_farm", {"site": "F2"}),
                           ("place_furniture", {"kind": "bed", "site": "A1", "count": 30}),
                           ("place_furniture", {"kind": "chair", "site": "A1", "count": 30}),
                           ("build_workshop", {"type": "Craftsdwarfs", "site": "W2"})]:
            assert g.act(tool, args)["ok"], tool
    while not g.game_over:
        g.act("advance_days", {"days": 7})


def write_game_dir(run_dir, spec, policy, cost=0.01):
    d = os.path.join(run_dir, spec["game_id"])
    os.makedirs(os.path.join(d, "gateway"), exist_ok=True)
    g = make_game(spec, os.path.join(d, "game"))
    play(g, policy)
    with open(os.path.join(d, "gateway", "usage.jsonl"), "w") as f:
        for _ in range(10):
            f.write(json.dumps({"schema": "dfbench-usage/1", "outcome": "ok", "cost_usd": cost / 10,
                                "throttle_wait_s": 0.5, "price_table_hash": "sha256:t"}) + "\n")
    json.dump({"spec": spec, "status": "ok", "notes": []}, open(os.path.join(d, "game.json"), "w"))
    return d


class FakeGameRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        suite = load_suite(SUITE)
        self.lt01 = expand(suite, only={"LT01-0"})[0]

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_k_actions_per_day(self):
        g = make_game(self.lt01, self.tmp)
        g.rules["actions_per_game_day"] = 3
        for _ in range(3):
            self.assertTrue(g.act("build_farm", {"site": "F1"})["ok"])
        r = g.act("build_farm", {"site": "F1"})
        self.assertEqual(r["error_code"], "action_limit")
        self.assertTrue(g.act("advance_days", {"days": 1})["ok"])
        self.assertTrue(g.act("build_farm", {"site": "F1"})["ok"])

    def test_errors_and_limits(self):
        g = make_game(self.lt01, self.tmp)
        self.assertEqual(g.act("nope", {})["error_code"], "unknown_tool")
        self.assertEqual(g.act("advance_days", {"days": 29})["error_code"], "bad_arguments")
        self.assertEqual(g.act("build_workshop", {"type": "Castle", "site": "W1"})["error_code"], "bad_arguments")
        for k in ("day", "tick", "days_left", "game_over", "hands_off_in_days", "observation"):
            self.assertIn(k, g.observe())

    def test_real_argument_shapes(self):
        """The fake takes the real server's v0 shapes (gameapi/facts/tools.py), so a harness that passes the fake
        doesn't send arguments the real server rejects (tester feedback V6, 2026-10-28)."""
        g = make_game(self.lt01, self.tmp)
        r = g.act("make_zone", {"kind": "bedroom"})
        self.assertEqual((r["error_code"], r["error"]), ("bad_arguments", "args.site is required"))
        self.assertEqual(g.act("place_furniture", {"item": "bed", "n": 3})["error_code"], "bad_arguments")
        self.assertFalse(g.act("place_furniture", {"kind": "bed", "site": "R1"})["ok"])      # not dug yet
        self.assertTrue(g.act("dig_room", {"site": "R1"})["ok"])
        self.assertTrue(g.act("place_furniture", {"kind": "bed", "site": "R1", "count": 2})["ok"])
        kinds = {e["kind"] for e in g.observe()["observation"]["map"]["sites"]}
        self.assertTrue({"R", "A", "W", "S"} <= kinds)
        r1 = next(e for e in g.observe()["observation"]["map"]["sites"] if e["id"] == "R1")
        self.assertIs(r1["dug"], True)

    def test_vendored_schemas_match_server(self):
        try:
            sys.path.insert(0, ROOT)
            from gameapi.facts.tools import tool_schemas
        except ImportError:
            self.skipTest("no gameapi/facts")
        vendored = json.load(open(os.path.join(ROOT, "runner", "fakes", "tool_schemas.json")))
        self.assertEqual(vendored, json.loads(json.dumps(tool_schemas())),
                         "run: python3 -I runner/fakes/gen_tool_schemas.py")

    def test_order_tools_and_stop_on(self):
        g = make_game(self.lt01, self.tmp)
        self.assertEqual(g.act("add_order", {"recipe": "brew_drink"})["error_code"], "bad_arguments")
        self.assertEqual(g.act("add_order", {"recipe": "brew_drink", "amount": 5,
                                             "when": [{"item_type": "DRINK"}]})["error_code"], "bad_arguments")
        self.assertTrue(g.act("add_order", {"recipe": "brew_drink", "amount": 5,
                                            "when": [{"stock": "drink", "below": 50}]})["ok"])
        self.assertEqual(g.act("add_manager_order", {"job": "BrewDrink", "amount": 1,
                                                     "when": [{"stock": "drink"}]})["error_code"], "bad_arguments")
        self.assertTrue(g.act("add_manager_order", {"job": "ConstructBlocks", "amount": 2,
                                                    "when": [{"item_type": "BOULDER", "at_least": 5}]})["ok"])
        self.assertEqual(g.act("advance_days", {"days": 1, "stop_on": ["death"]})["error_code"], "bad_arguments")
        self.assertTrue(g.act("advance_days", {"days": 1, "stop_on": ["citizen_died"]})["ok"])

    def test_stop_on_matches_server(self):
        try:
            sys.path.insert(0, ROOT)
            from gameapi.server.rules import STOP_ON_VALUES
        except ImportError:
            self.skipTest("no gameapi/server")
        self.assertEqual(fake_game.STOP_ON_VALUES, list(STOP_ON_VALUES))

    def test_hands_off_and_game_over(self):
        g = make_game(self.lt01, self.tmp)
        while g.day < g.A:
            g.act("advance_days", {"days": 28})
        self.assertEqual(g.day, 39)                        # cut at the window
        self.assertEqual(g.act("build_farm", {"site": "F1"})["error_code"], "hands_off")
        while not g.game_over:
            g.act("advance_days", {"days": 28})
        self.assertEqual(g.finished_by, "horizon")
        self.assertEqual(g.act("advance_days", {"days": 1})["error_code"], "game_over")
        self.assertEqual(len(g.samples), 61)

    def test_finish_runs_the_horizon(self):
        g = make_game(self.lt01, self.tmp)
        g.act("advance_days", {"days": 3})
        g.finish()
        self.assertEqual((g.day, g.finished_by, g.finished), (60, "harness_exit", True))
        row = json.loads(open(os.path.join(self.tmp, "summary.jsonl")).read().splitlines()[-1])
        for k in ("api", "key", "harness_digest", "wall_capped", "actions_used", "actions_rejected"):
            self.assertIn(k, row)

    def test_wall_cap(self):
        t = [0.0]
        sc = json.load(open(os.path.join(ROOT, self.lt01["scenario"])))
        g = fake_game.Game({"arm": "harness", "k": 0, "artifacts_dir": self.tmp, "rules": {"wall_s": 10}}, sc,
                           clock=lambda: t[0])
        g.act("advance_days", {"days": 5})
        t[0] = 11
        r = g.act("advance_days", {"days": 5})
        self.assertTrue(g.wall_capped and g.game_over)
        self.assertEqual(r["result"]["stopped"]["reason"], "wall_cap")


class Scoring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.suite = load_suite(SUITE)
        cls.suite["bootstrap"]["resamples"] = 2000
        specs = expand(cls.suite, n=3)
        cls.good, cls.noop = os.path.join(cls.tmp, "good"), os.path.join(cls.tmp, "noop")
        for s in specs:
            write_game_dir(cls.good, s, "good")
            write_game_dir(cls.noop, s, "noop")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_score_json(self):
        sc, detail = S.score_dir(self.good, self.suite)
        m = sc["metrics"]
        for k in ("model_latency_s_per_call", "reasoning_tokens_per_call", "completion_tokens_per_call"):
            self.assertIn(k, m)
            self.assertTrue(m[k] is None or isinstance(m[k], (int, float)), k)
        for k, v in m.items():   # collect.py finalize refuses nested metrics (Yukon shows one row per flat key)
            self.assertFalse(isinstance(v, (dict, list)) and k != "harness_digest", k)
        self.assertEqual(m["stage"], 2)
        self.assertNotIn("partial", sc)
        self.assertTrue(m["promotable"])
        self.assertLessEqual(sc["score"], m["point"])
        self.assertLessEqual(m["point"], m["ub95"])
        for k in ("LT01", "LT02", "LT03", "LT08", "MY1", "OP1", "credits_per_game_year", "calls_per_game_year",
                  "wall_h_per_game_year", "wall_capped", "throttle_wait_s", "subscores", "tiers"):
            self.assertIn(k, m)
        for v in m.values():                                # flat: Yukon shows one row per top-level key
            self.assertNotIsInstance(v, (dict, list))
        self.assertTrue(os.path.exists(os.path.join(self.good, "score.json")))
        self.assertEqual(len(detail["games"]), 18)

    def test_good_beats_noop(self):
        g, _ = S.score_dir(self.good, self.suite, write=False)
        n, _ = S.score_dir(self.noop, self.suite, write=False)
        self.assertGreater(g["metrics"]["point"], n["metrics"]["point"])
        self.assertIn("pass 3/3", g["metrics"]["LT01"])
        self.assertIn("pass 0/3", n["metrics"]["LT01"])

    def test_bootstrap_seeded(self):
        a, _ = S.score_dir(self.good, self.suite, write=False)
        b, _ = S.score_dir(self.good, self.suite, write=False)
        self.assertEqual(a["score"], b["score"])

    def test_weights(self):
        _, d = S.score_dir(self.good, self.suite, write=False)
        f = d["families"]
        want = (0.5 * f["OP1"] + 0.3 * f["MY1"] + 0.2 * f["labs"])
        self.assertAlmostEqual(d["score"]["metrics"]["point"], round(want, 2), places=2)

    def test_stage1_only_not_promotable(self):
        d = os.path.join(self.tmp, "s1")
        for s in expand(self.suite, stages={1}, n=2):
            write_game_dir(d, s, "good")
        sc, _ = S.score_dir(d, self.suite, write=False)
        self.assertEqual(sc["metrics"]["stage"], 1)
        self.assertFalse(sc["metrics"]["promotable"])
        self.assertEqual((sc["score"], sc["partial"]), (0, True))
        self.assertIsNotNone(sc["metrics"]["lb95"])
        self.assertNotIn("OP1", sc["metrics"])

    def test_low_z_listed_and_attempts_skipped(self):
        d = os.path.join(self.tmp, "lowz")
        sp = expand(self.suite, only={"LT08-0"})[0]
        g = write_game_dir(d, sp, "noop")
        os.makedirs(os.path.join(g, "attempt-0"))
        shutil.copytree(os.path.join(g, "game"), os.path.join(g, "attempt-0", "game"))
        rec = json.load(open(os.path.join(g, "game.json")))
        json.dump({**rec, "status": "infra"}, open(os.path.join(g, "attempt-0", "game.json"), "w"))
        sc, _ = S.score_dir(d, self.suite, write=False)
        self.assertIn("LT08-0 -", sc["metrics"]["lab_z_below_minus1"])
        self.assertEqual(sc["metrics"]["infra_excluded"], 0)
        self.assertEqual(sc["metrics"]["games"], "1 scored / 1 run")

    def test_infra_games_excluded_and_harness_output_ignored(self):
        d = os.path.join(self.tmp, "infra")
        specs = expand(self.suite, only={"LT01-0", "LT01-1"})
        write_game_dir(d, specs[0], "good")
        g1 = write_game_dir(d, specs[1], "good")
        rec = json.load(open(os.path.join(g1, "game.json")))
        rec["status"] = "infra"
        json.dump(rec, open(os.path.join(g1, "game.json"), "w"))
        os.makedirs(os.path.join(d, specs[0]["game_id"], "harness"))
        open(os.path.join(d, specs[0]["game_id"], "harness", "summary.jsonl"), "w").write('{"bogus": 1}\n')
        sc, _ = S.score_dir(d, self.suite, write=False)
        self.assertEqual(sc["metrics"]["infra_excluded"], 1)
        self.assertIn("pass 1/1", sc["metrics"]["LT01"])


class CrashTwice(unittest.TestCase):
    """Red team: a harness that can crash DF on purpose mustn't re-roll its bad games (SCORING.md §6)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.suite = load_suite(SUITE)
        self.spec = expand(self.suite, only={"LT01-0"})[0]

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _crash(self, d):
        p = os.path.join(d, "game", "summary.jsonl")
        rows = [json.loads(l) for l in open(p) if l.strip()]
        rows[-1]["crashed"] = "DFCrash: test"
        open(p, "w").write("".join(json.dumps(r) + "\n" for r in rows))

    def test_crash_detected_as_game_infra_with_last_actions(self):
        from dfbenchlib.game import Game
        d = write_game_dir(self.tmp, self.spec, "good")
        self._crash(d)
        with open(os.path.join(d, "game", "harness-0.api.jsonl"), "w") as f:
            for i in range(30):
                f.write(json.dumps({"method": "POST", "path": "/act", "day": i, "status": 200,
                                    "request": {"tool": "build_farm", "args": {"site": "F1"}}}) + "\n")
        g = Game(self.spec, {}, self.tmp)
        g.rec["status"] = "ok"
        g._check_artifacts()
        self.assertEqual((g.rec["status"], g.rec["infra_cause"]), ("infra", "game"))
        self.assertEqual(len(g.rec["crash"]["last_actions"]), 20)
        self.assertEqual(g.rec["crash"]["last_actions"][-1]["day"], 29)

    def test_crash_twice_scored_at_state_reached(self):
        d = write_game_dir(self.tmp, self.spec, "good")
        self._crash(d)
        rec = json.load(open(os.path.join(d, "game.json")))
        json.dump({**rec, "status": "infra", "infra_cause": "game"}, open(os.path.join(d, "game.json"), "w"))
        self.assertEqual(S.score_game(d)["status"], "infra")          # once: an infra re-run
        json.dump({**rec, "status": "infra", "infra_cause": "game", "crash_twice": True},
                  open(os.path.join(d, "game.json"), "w"))
        r = S.score_game(d)
        self.assertEqual((r["status"], r["crash_twice"]), ("ok", True))
        self.assertGreater(r["partial"], 0)
        sc, _ = S.score_dir(self.tmp, self.suite, write=False)
        self.assertEqual((sc["metrics"]["crash_twice"], sc["metrics"]["infra_excluded"]), (1, 0))

    def test_crash_twice_without_samples_is_a_lost_fort(self):
        d = write_game_dir(self.tmp, self.spec, "good")
        shutil.rmtree(os.path.join(d, "game"))
        os.makedirs(os.path.join(d, "game"))
        rec = json.load(open(os.path.join(d, "game.json")))
        json.dump({**rec, "status": "infra", "infra_cause": "game", "crash_twice": True},
                  open(os.path.join(d, "game.json"), "w"))
        r = S.score_game(d)
        self.assertEqual((r["status"], r["O"], r["partial"]), ("ok", 0.0, 0.0))

    def test_local_retry_rule(self):
        from dfbenchlib.game import crash_twice
        self.assertTrue(crash_twice(["game", "game"]))
        self.assertFalse(crash_twice(["game", "provider"]))


class Robustness(unittest.TestCase):
    """Hung provider calls (gateway upstream_timeout) and a game server that fails to start."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.suite = load_suite(SUITE)
        self.spec = expand(self.suite, only={"LT01-0"})[0]

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_client_errors_are_not_provider_errors(self):
        # red team: a harness can send requests the provider rejects (4xx) at will; only 5xx, 429 and unreachable
        # count towards the provider-error infra rule
        from dfbenchlib.game import ledger_summary
        p = os.path.join(self.tmp, "usage.jsonl")
        rows = [{"outcome": "upstream_error", "upstream_status": 400}] * 5 + \
               [{"outcome": "upstream_error", "upstream_status": s} for s in (500, 429, None)] + \
               [{"outcome": "upstream_error", "upstream_status": None, "harness_attributable": True}]
        with open(p, "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in rows)
        u = ledger_summary(p)
        self.assertEqual((u["upstream_errors"], u["upstream_errors_provider"]), (9, 3))

    def test_a_few_timeouts_score_too_many_are_infra(self):
        from dfbenchlib.game import ledger_summary
        d = write_game_dir(self.tmp, self.spec, "good")
        with open(os.path.join(d, "gateway", "usage.jsonl"), "a") as f:
            f.write(json.dumps({"outcome": "upstream_timeout", "cost_usd": 0.001, "throttle_wait_s": 300}) + "\n")
        self.assertEqual(ledger_summary(os.path.join(d, "gateway", "usage.jsonl"))["upstream_timeouts"], 1)
        st = os.path.join(d, "gateway", "gateway-status.json")
        json.dump({"blocked_reason": None, "upstream_timeouts": 1, "usage_unknown_calls": 0}, open(st, "w"))
        self.assertEqual(S.score_game(d)["status"], "ok")
        json.dump({"blocked_reason": "upstream_unreliable", "upstream_timeouts": 6, "usage_unknown_calls": 0},
                  open(st, "w"))
        self.assertEqual(S.score_game(d)["status"], "infra")

    def test_failed_game_start_fails_fast(self):
        from dfbenchlib import game as G
        g = G.Game(self.spec, {"harness_image": "x"}, self.tmp)
        g.game_http = lambda *a, **k: {"ok": False, "phase": "failed", "ready": True, "error": "no fort"}
        with self.assertRaisesRegex(RuntimeError, "failed to start: no fort"):
            g._game_ready()
        g.game_http = lambda *a, **k: None
        g.container_state = lambda svc: {"status": "exited", "exit_code": 1, "oom": False}
        g.compose = lambda *a, **k: subprocess.CompletedProcess(a, 0, "ModuleNotFoundError: gameapi\n", "")
        with self.assertRaisesRegex(RuntimeError, r"exited \(code 1\).*ModuleNotFoundError"):
            g._game_ready()
        g.container_state = lambda svc: {"status": "running", "exit_code": 0, "oom": False}
        self.assertIsNone(g._game_ready())                                    # still starting: keep waiting
        g.game_http = lambda *a, **k: {"ok": True, "phase": "starting", "ready": False}
        self.assertIsNone(g._game_ready())
        g.game_http = lambda *a, **k: {"ok": True, "phase": "ready", "ready": True}
        self.assertTrue(g._game_ready())


class Resolve(unittest.TestCase):
    def test_bare_task_names(self):
        from dfbenchlib.suite import resolve_scenario
        self.assertTrue(resolve_scenario("start-year").endswith("scenarios/start-year.json"))
        self.assertTrue(resolve_scenario("scenarios/seed/lt01-drought.json").endswith("seed/lt01-drought.json"))
        self.assertTrue(resolve_scenario("lt01-drought-seed").endswith("seed/lt01-drought.json"))


class SuiteLoading(unittest.TestCase):
    def test_only_selected_tasks_are_loaded(self):
        suite = load_suite(SUITE)
        bad = dict(suite, tasks=[dict(t, scenario="scenarios/season0/missing.json") if t["id"] == "MY1" else t
                                 for t in suite["tasks"]])
        self.assertTrue(all(s["task_id"] == "LT01" for s in expand(bad, only={"LT01"}, n=1)))
        self.assertTrue(expand(bad, only={"LT01-0"}, n=1))
        with self.assertRaises(SystemExit) as cm:
            expand(bad, n=1)
        self.assertIn("MY1", str(cm.exception))

    def test_missing_forts_named_before_any_container(self):
        from dfbenchlib.suite import check_forts, missing_forts
        specs = expand(load_suite(SUITE), only={"LT01-0", "MY1-0", "OP1-0"}, n=1)
        with tempfile.TemporaryDirectory() as d:
            old = os.environ.get("DFBENCH_SNAPSHOTS_DIR")
            os.environ["DFBENCH_SNAPSHOTS_DIR"] = d
            try:
                miss = missing_forts(specs)
                self.assertEqual({t for t, _ in miss}, {"LT01", "MY1"} | ({"OP1"} if any(t == "OP1" for t, _ in miss)
                                                                             else set()))
                with self.assertRaises(SystemExit) as cm:
                    check_forts(specs, "real")
                self.assertIn(".yukon/setup.sh", str(cm.exception))
                check_forts(specs, "fake")                   # the fake stack needs no forts
                for t, p in miss:
                    if p.startswith(d):
                        os.makedirs(p, exist_ok=True)
                        open(os.path.join(p, "world.sav"), "w").close()
                self.assertEqual([t for t, p in missing_forts(specs) if p.startswith(d)], [])
            finally:
                if old is None:
                    os.environ.pop("DFBENCH_SNAPSHOTS_DIR", None)
                else:
                    os.environ["DFBENCH_SNAPSHOTS_DIR"] = old


class ComposeIsolation(unittest.TestCase):
    """The rendered compose file: the key only in the gateway, no published ports, the harness on the internal net."""

    def test_config(self):
        if not shutil.which("docker"):
            self.skipTest("no docker")
        tmp = tempfile.mkdtemp()
        try:
            env = {**os.environ, "DFBENCH_PROJECT": "s0run-cfgtest", "DFBENCH_SCENARIO_FILE": os.path.join(tmp, "s.json"),
                   "DFBENCH_GAME_DIR": tmp, "DFBENCH_LEDGER_DIR": tmp, "DFBENCH_HARNESS_IMAGE": "x:y",
                   "DFBENCH_PROVIDER_KEY": "sk-SECRET-123", "DFBENCH_TASK": "{}", "DFBENCH_SNAPSHOTS_DIR": tmp}
            c = os.path.join(RUNNER, "compose")
            r = subprocess.run(["docker", "compose", "-f", f"{c}/compose.yml", "-f", f"{c}/compose.real.yml",
                                "--project-directory", tmp, "config", "--format", "json"],
                               env=env, capture_output=True, text=True, check=True)
            cfg = json.loads(r.stdout)
        finally:
            shutil.rmtree(tmp)
        sv = cfg["services"]
        self.assertEqual(sv["gateway"]["environment"]["OPENROUTER_API_KEY"], "sk-SECRET-123")
        for s in ("harness", "game"):
            self.assertNotIn("sk-SECRET-123", json.dumps(sv[s]))
        for s in sv.values():
            self.assertFalse(s.get("ports"))
        self.assertEqual(set(sv["harness"]["networks"]), {"game_internal"})
        self.assertEqual(set(sv["game"]["networks"]), {"game_internal"})
        self.assertEqual(set(sv["gateway"]["networks"]), {"game_internal", "egress"})
        self.assertTrue(cfg["networks"]["game_internal"]["internal"])
        self.assertEqual(sv["harness"]["cap_drop"], ["ALL"])
        self.assertNotIn("GATEWAY_DEBUG", sv["gateway"]["environment"])
        self.assertEqual(float(sv["harness"]["cpus"]), 1.0)
        self.assertEqual(int(sv["harness"]["mem_limit"]), 2 * 2 ** 30)
        # red team: no fillable disk (read-only rootfs, bounded in-memory /tmp), bounded processes and logs
        self.assertTrue(sv["harness"]["read_only"])
        self.assertTrue(any(str(t).startswith("/tmp:") and "size=1g" in str(t) for t in sv["harness"]["tmpfs"]))
        self.assertLessEqual(int(sv["harness"]["pids_limit"]), 512)
        self.assertEqual(sv["harness"]["logging"]["options"]["max-size"], "10m")
        self.assertNotIn("volumes", sv["harness"])


@unittest.skipUnless(os.environ.get("DFBENCH_E2E") == "1", "set DFBENCH_E2E=1 (builds small images, runs 3 containers)")
class E2E(unittest.TestCase):
    def run_cli(self, *args, env=None):
        return subprocess.run([sys.executable, os.path.join(RUNNER, "dfbench"), *args], cwd=ROOT,
                              env={**os.environ, **(env or {})}, capture_output=True, text=True, timeout=900)

    def test_one_fake_game(self):
        out = tempfile.mkdtemp(prefix="s0run-e2e-")
        try:
            r = self.run_cli("local", "run", "--stack", "fake", "--run-prefix", "s0run",
                             "--harness", os.path.join(RUNNER, "fakes", "example_harness"),
                             "--task", "scenarios/lt01-drought.json", "--n", "1", "--out", out, "--poll", "1",
                             env={"FAKE_REQUIRE_KEY": "1", "DFBENCH_PROVIDER_KEY": "sk-fake-e2e", "FAKE_THROTTLE_S": "0.2"})
            self.assertEqual(r.returncode, 0, r.stderr[-3000:])
            sc = json.load(open(os.path.join(out, "score.json")))
            self.assertIn("pass 1/1", sc["metrics"]["LT01"])
            self.assertIsNotNone(sc["score"])
            g = os.path.join(out, "LT01-0")
            rec = json.load(open(os.path.join(g, "game.json")))
            self.assertEqual(rec["status"], "ok")
            self.assertEqual(rec["finished_by"], "horizon")
            self.assertGreater(rec["ledger"]["ok_calls"], 5)
            self.assertGreater(sc["metrics"]["throttle_wait_s"], 0)
            self.assertTrue(os.path.exists(os.path.join(g, "gateway", "gateway-status.json")))
            self.assertTrue(os.path.getsize(os.path.join(g, "harness", "output.log")) > 0)
            for f in ("summary.jsonl", "harness-0.daily.json", "harness-0.credit.json", "harness-0.final.json",
                      "harness-0.api.jsonl"):
                self.assertTrue(os.path.exists(os.path.join(g, "game", f)), f)
            task = json.load(open(os.path.join(g, "task", "dfbench_task.json")))
            self.assertEqual(task["schema"], "dfbench-task/1")
            self.assertNotIn("sk-fake-e2e", json.dumps(task))
            self.assertEqual(task["model"]["prices"]["input"], 0.15)
            self.assertTrue(task["model"]["prices"]["price_table_hash"].startswith("sha256:"))
            left = subprocess.run(["docker", "ps", "-aq", "--filter", "name=^s0run-"], capture_output=True, text=True)
            self.assertEqual(left.stdout.strip(), "")
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_budget_exhausted_harness_exits_server_finishes(self):
        out = tempfile.mkdtemp(prefix="s0run-e2e-")
        try:
            r = self.run_cli("local", "run", "--stack", "fake", "--run-prefix", "s0run",
                             "--harness", os.path.join(RUNNER, "fakes", "example_harness"),
                             "--task", "scenarios/season0/op1-start-year.json", "--n", "1", "--out", out, "--poll", "1",
                             "--budget", "0.05", env={"FAKE_COST_PER_CALL": "0.01"})
            self.assertEqual(r.returncode, 0, r.stderr[-3000:])
            rec = json.load(open(os.path.join(out, "OP1-0", "game.json")))
            self.assertIn(rec["finished_by"], ("credits_budget_exhausted", "harness_exit"))
            self.assertEqual(rec["ledger"]["ok_calls"], 5)
            self.assertGreaterEqual(rec["ledger"]["refused"], 1)
            sc = json.load(open(os.path.join(out, "score.json")))
            self.assertIn("OP1", sc["metrics"])
            self.assertEqual(sc["metrics"]["credits_exhausted"], 1)
            self.assertEqual(rec["gateway_status"]["blocked_reason"], "budget_exhausted")
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_baseline_harness(self):
        """The plain baseline, staged as submission/ is (Dockerfile + dfbench_client/ + plain/), through the runner on
        the fake stack, task given by name."""
        base = os.path.join(ROOT, "baseline")
        if not os.path.exists(os.path.join(base, "plain", "Dockerfile")):
            self.skipTest("no baseline/plain/")
        out = tempfile.mkdtemp(prefix="s0run-e2e-")
        sub = tempfile.mkdtemp(prefix="s0run-sub-")
        try:
            shutil.copy(os.path.join(base, "plain", "Dockerfile"), os.path.join(sub, "Dockerfile"))
            for d in ("dfbench_client", "plain"):
                shutil.copytree(os.path.join(base, d), os.path.join(sub, d),
                                ignore=shutil.ignore_patterns("__pycache__"))
            r = self.run_cli("local", "run", "--stack", "fake", "--run-prefix", "s0run",
                             "--harness", sub, "--task", "lt01-drought-seed",
                             "--out", out, "--poll", "1")
            self.assertEqual(r.returncode, 0, r.stderr[-3000:])
            rec = json.load(open(os.path.join(out, "LT01-0", "game.json")))
            self.assertEqual((rec["status"], rec["harness"]["exit_code"]), ("ok", 0))
            self.assertGreater(rec["ledger"]["ok_calls"], 5)
        finally:
            shutil.rmtree(out, ignore_errors=True)
            shutil.rmtree(sub, ignore_errors=True)

    def test_confirmation_batch_pools(self):
        """The confirmation batch (challenge/SCORING.md §4.1): game ids past a task's n play on the fake stack as
        their own games (k past n, the same forts by k mod the pool), and a run dir holding both batches scores
        them pooled."""
        suite = os.path.join(RUNNER, "suites", "season0-public.json")
        n = {t["id"]: t.get("n", 8) for t in json.load(open(suite))["tasks"]}["MY1"]
        first, second, pooled = (tempfile.mkdtemp(prefix=f"s0run-e2e-{x}-") for x in ("a", "b", "p"))
        try:
            harness = os.path.join(RUNNER, "fakes", "example_harness")
            for out, ids in ((first, [f"MY1-{k}" for k in range(n)]), (second, [f"MY1-{k + n}" for k in range(n)])):
                r = self.run_cli("suite", "run", "--suite", suite, "--stack", "fake", "--run-prefix", "s0run",
                                 "--harness", harness, "--games", ",".join(ids), "--out", out, "--poll", "1",
                                 "--parallel", "2")
                self.assertEqual(r.returncode, 0, r.stderr[-3000:])
                for g in ids:
                    rec = json.load(open(os.path.join(out, g, "game.json")))
                    self.assertEqual((rec["status"], rec["spec"]["k"]), ("ok", int(g.split("-")[1])))
            for out in (first, second):
                for g in os.listdir(out):
                    if g.startswith("MY1-"):
                        shutil.copytree(os.path.join(out, g), os.path.join(pooled, g))
            r = self.run_cli("score", pooled, "--suite", suite)
            self.assertEqual(r.returncode, 0, r.stderr[-3000:])
            sc = json.load(open(os.path.join(pooled, "score.json")))
            self.assertIn(f"(n {2 * n};", sc["metrics"]["MY1"])
        finally:
            for d in (first, second, pooled):
                shutil.rmtree(d, ignore_errors=True)

    def test_paired_confirmation_same_window(self):
        """D26 on the fake stack: the challenger's confirmation games and the leader's on the same games (same k,
        forts and seeds), scored, paired (runner/ci/bin/paired.py) and checked for drift (drift.py) against each
        other. The same harness on both sides is a tie: never a paired win, and no drift."""
        sys.path.insert(0, os.path.join(RUNNER, "ci", "bin"))
        import drift, paired
        suite_p = os.path.join(RUNNER, "suites", "season0-public.json")
        with open(suite_p) as f:
            suite = json.load(f)
        n = {t["id"]: t.get("n", 8) for t in suite["tasks"]}["MY1"]
        ids = [f"MY1-{k + n}" for k in range(3)]
        chal, lead = (tempfile.mkdtemp(prefix=f"s0run-e2e-{x}-") for x in ("c", "l"))
        try:
            harness = os.path.join(RUNNER, "fakes", "example_harness")
            for out in (chal, lead):
                r = self.run_cli("suite", "run", "--suite", suite_p, "--stack", "fake", "--run-prefix", "s0run",
                                 "--harness", harness, "--games", ",".join(ids), "--out", out, "--poll", "1",
                                 "--parallel", "2")
                self.assertEqual(r.returncode, 0, r.stderr[-3000:])
                r = self.run_cli("score", out, "--suite", suite_p)
                self.assertEqual(r.returncode, 0, r.stderr[-3000:])
            details = []
            for out in (chal, lead):
                with open(os.path.join(out, "score_detail.json")) as f:
                    details.append(json.load(f))
            d = paired.paired_diff(paired.pairs(details[0], details[1], ["MY1", "OP1"]), suite)
            self.assertEqual(d["n"], 3)
            scored = {"score": 70.0, "metrics": {}}
            self.assertNotEqual(paired.decide(scored, d), "passed")
            ref = drift.build_reference(lead, "t", "1")
            self.assertTrue(ref["calls"])
            self.assertIn(drift.check(chal, ref)["drift_flag"], ("none", "n/a"))
        finally:
            for x in (chal, lead):
                shutil.rmtree(x, ignore_errors=True)

    def test_usage_missing_is_infra(self):
        out = tempfile.mkdtemp(prefix="s0run-e2e-")
        try:
            r = self.run_cli("local", "run", "--stack", "fake", "--run-prefix", "s0run", "--retries", "1",
                             "--harness", os.path.join(RUNNER, "fakes", "example_harness"),
                             "--task", "scenarios/lt01-drought.json", "--n", "1", "--out", out, "--poll", "1",
                             env={"FAKE_USAGE_MISSING_AT": "2"})
            self.assertEqual(r.returncode, 0, r.stderr[-3000:])
            rec = json.load(open(os.path.join(out, "LT01-0", "game.json")))
            self.assertEqual(rec["status"], "infra")
            self.assertEqual(rec["attempt"], 1)
            self.assertTrue(os.path.exists(os.path.join(out, "LT01-0", "attempt-0", "game", "summary.jsonl")))
            sc = json.load(open(os.path.join(out, "score.json")))
            self.assertIsNone(sc["score"])
            self.assertEqual(sc["metrics"]["infra_excluded"], 1)
        finally:
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


class SuiteKeyTest(unittest.TestCase):
    """Real suites have one comparability key per task (the key hashes the task), and collect.py finalize refuses any
    nested metric (Yukon shows one row per flat key): the suite key must always be a single string. The fake stack
    uses one key for every task, so only this test covers it (found on the first real Yukon baseline, 2026-10-28)."""

    def test_suite_key_is_flat(self):
        self.assertIsNone(S.suite_key([]))
        self.assertEqual(S.suite_key(["dfbench/v3|a"]), "dfbench/v3|a")
        k = S.suite_key(sorted(["dfbench/v3|lt01", "dfbench/v3|my1", "dfbench/v3|op1"]))
        self.assertIsInstance(k, str)
        self.assertRegex(k, r"^dfbench/v3\|suite:[0-9a-f]{16}\|keys:3$")
        self.assertEqual(k, S.suite_key(sorted(["dfbench/v3|op1", "dfbench/v3|lt01", "dfbench/v3|my1"])))
        self.assertNotEqual(k, S.suite_key(["dfbench/v3|lt01", "dfbench/v3|my1"]))


class RunPrefixTest(unittest.TestCase):
    """--run-prefix goes into Docker image names, which must be lowercase (`--run-prefix mcA` failed at the harness
    build with "repository name must be lowercase", 2026-10-29)."""

    def test_lowercased_and_validated(self):
        from dfbenchlib import cli
        self.assertEqual(cli.run_prefix("mcA"), "mca")
        self.assertEqual(cli.run_prefix(" s0PP2 "), "s0pp2")
        for bad in ("", "-x", "a b", "a/b", "x" * 50, "é"):
            with self.assertRaises(argparse.ArgumentTypeError, msg=bad):
                cli.run_prefix(bad)
