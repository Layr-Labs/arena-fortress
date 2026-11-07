"""Tests for runner/ci/bin (dispatch, tier, ledger, verdict, prior, collect): no network, HTTP mocked.
Run: python3 -m unittest discover -s runner/ci/tests -t .
"""
import argparse, contextlib, datetime, io, json, os, re, subprocess, sys, tempfile, unittest, urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin"))
import collect, dispatch, early_judge, emit_score, gate, ledger, prior, tier  # noqa: E402

SUB = "11111111-2222-3333-4444-555555555555"
OURS = "aaaaaaaa-0000-0000-0000-000000000000"
NOW = datetime.datetime(2026, 10, 23, 12, tzinfo=datetime.timezone.utc)
ENV = {"DFBENCH_YUKON_API": "https://yukon.example"}


def fake_http(routes):
    calls = []

    def http(url, headers=None, **_):
        calls.append((url, headers))
        for k, v in routes.items():
            if url.endswith(k):
                if isinstance(v, Exception):
                    raise v
                return v
        raise tier.Infra(f"unrouted {url}")
    http.calls = calls
    return http


def routes(user="alice", created="2020-01-01T00:00:00Z", participations=(), deps=()):
    return {
        f"/api/submissions/{SUB}": {"submission": {"solverUsername": user, "coauthors": ["bob"], "note": "n",
                                                    "benchmarkId": OURS, "submissionCommitSha": "abc"}},
        f"/api/submissions/{SUB}/attribution": {"declaration": "provided", "dependencies": list(deps)},
        f"/api/solvers/{user}/profile": {"participations": list(participations)},
        f"/users/{user}": {"login": user, "created_at": created},
    }


def part(bench, status, challenge=None, promotion=None):
    return {"benchmark": {"id": bench, "challengeId": challenge},
            "contributions": [{"submission": {"status": status, "promotionStatus": promotion}}]}


def res(env, http, valid=False):
    return tier.resolve(SUB, env, http, NOW, valid_here=lambda u: valid)


class DispatchGuard(unittest.TestCase):
    """Only Yukon's App or a repo admin may start a scoring run (org members all have write)."""

    def test_apps_and_admins_pass(self):
        self.assertTrue(dispatch.guard("yukon-eigen[bot]")[0])
        self.assertTrue(dispatch.guard("yukon-autoresearch[bot]")[0])
        self.assertTrue(dispatch.guard("OWNER", permission="admin")[0])
        self.assertTrue(dispatch.guard("other-app[bot]", apps="other-app[bot]")[0])

    def test_writers_and_unknowns_refused(self):
        for perm in ("write", "maintain", "read", "unknown", None):
            ok, why = dispatch.guard("some-member", permission=perm)
            self.assertFalse(ok, perm)
            self.assertIn("repo admin", why)
        self.assertFalse(dispatch.guard("yukon-eigen[bot]", apps="yukon-autoresearch[bot]", permission="write")[0])
        self.assertFalse(dispatch.guard("yukon-eigen", permission="write")[0])   # the bot suffix matters

    def test_cli_exit_codes(self):
        bin_ = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "dispatch.py")
        ok = subprocess.run([sys.executable, "-I", bin_, "guard", "--actor", "yukon-eigen[bot]"], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0)
        bad = subprocess.run([sys.executable, "-I", bin_, "guard", "--actor", "x", "--permission", "write"],
                             capture_output=True, text=True)
        self.assertEqual(bad.returncode, 3)
        self.assertTrue(bad.stdout.startswith("::error::"))

    def test_guard_runs_before_the_ledger(self):
        wf = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "score.yml")).read()
        admit = wf.split("\n  admit:\n", 1)[1].split("\n  harness:\n", 1)[0]
        self.assertIn("dispatch.py guard", admit)
        self.assertLess(admit.index("dispatch.py guard"), admit.index("ledger.py"))


class EarlyJudge(unittest.TestCase):
    """The judge before any game (DFBENCH_JUDGE_EARLY): fail-open on the judge's own errors, final on fail/hold."""

    def test_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "dossier.json")
            self.assertEqual(early_judge.verdict(p), "error")                 # missing: the judge crashed
            open(p, "w").write("not json")
            self.assertEqual(early_judge.verdict(p), "error")
            for v in ("pass", "fail", "hold"):
                json.dump({"verdict": v}, open(p, "w"))
                self.assertEqual(early_judge.verdict(p), v)
            json.dump({"verdict": "hold", "hold_conditions": ["judge infrastructure failure: provider: 503"]}, open(p, "w"))
            self.assertEqual(early_judge.verdict(p), "error")                 # our outage: the games still run
            json.dump({"verdict": "hold", "hold_conditions": ["judge infrastructure failure: x", "size limit: diff"]},
                      open(p, "w"))
            self.assertEqual(early_judge.verdict(p), "hold")                  # a real condition: stop
            json.dump({"verdict": "hold", "hold_conditions": ["major finding(s) for an organiser: F1"]}, open(p, "w"))
            self.assertEqual(early_judge.verdict(p), "hold")
            json.dump({"verdict": "maybe"}, open(p, "w"))
            self.assertEqual(early_judge.verdict(p), "error")
        self.assertEqual(early_judge.STOPPED, ("fail", "hold"))

    def test_reuse(self):
        r = early_judge.reuse
        self.assertTrue(r("pass", "a" * 36, "a" * 36)[0])
        self.assertFalse(r("pass", "a" * 36, "b" * 36)[0])                     # the incumbent changed
        for lead in ("", "unknown", None):
            self.assertFalse(r("pass", lead, "a" * 36)[0]); self.assertFalse(r("pass", "a" * 36, lead)[0])
        for v in ("fail", "hold", "error", ""):
            self.assertFalse(r(v, "a" * 36, "a" * 36)[0])

    def test_stub_through_emit_score(self):
        for v in ("fail", "hold"):
            out = emit_score.emit(early_judge.stub(), dossier={"verdict": v})
            self.assertEqual((out["score"], out["partial"]), (0, True))
            m = out["metrics"]
            self.assertEqual((m["stage"], m["judge_verdict"], m["judge_stage"]), (0, v, "early"))
            self.assertTrue(all(not isinstance(x, (dict, list)) for x in m.values()))

    def test_workflow_wiring(self):
        ci = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        wf = open(os.path.join(ci, "score.yml")).read()
        jobs = dict((b.split(":", 1)[0].strip(), b) for b in re.split(r"\n(?=  [A-Za-z0-9_-]+:\n)", wf.split("\njobs:\n", 1)[1]))
        ej = jobs["early-judge"]
        self.assertIn("vars.DFBENCH_JUDGE_EARLY == 'true'", ej)
        self.assertIn("needs.admit.outputs.kind != 'baseline'", ej)
        # the judge's key appears in exactly one step of the job: the judge step
        steps = ej.split("\n      - ")
        with_key = [st for st in steps if "DFBENCH_JUDGE_OPENROUTER_KEY: ${{" in st]
        self.assertEqual(len(with_key), 1); self.assertIn("judge_run.sh judge", with_key[0])
        # games are gated on the early verdict, and only fail/hold stop them
        for j in ("s1", "s1-check"):
            self.assertIn("early-judge", jobs[j].split("needs:", 1)[1].split("\n", 1)[0])
            self.assertIn("needs.early-judge.outputs.go != 'false'", jobs[j])
        self.assertIn("needs.early-judge.outputs.go == 'false'", jobs["early-reject"])
        self.assertIn("--status rejected", jobs["early-reject"])
        self.assertIn("name: dfbench-score", jobs["early-reject"])
        self.assertIn("early-reject", jobs["release"].split("needs:", 1)[1].split("\n", 1)[0])
        # both judge jobs use the same script
        self.assertIn("judge_run.sh judge j j/scored.json", jobs["judge"])
        self.assertNotIn("python3 -I runner/judge/judge.py", wf)     # only judge_run.sh calls it


class Dispatch(unittest.TestCase):
    SHA = "0123456789abcdef0123456789abcdef01234567"

    def test_submission(self):
        r = dispatch.classify(f"submissions/{SUB}", self.SHA)
        self.assertEqual((r["kind"], r["submission"]), ("submission", SUB))

    def test_baseline_with_and_without_track(self):
        for ref in (f"yukon/baseline/{self.SHA}", f"yukon/baseline/{self.SHA}/harness-glm-5-3-flash",
                    f"yukon/baseline/{self.SHA[:12]}"):
            r = dispatch.classify(ref, self.SHA)
            self.assertEqual((r["kind"], r["tier"], r["submission"]), ("baseline", "baseline", "baseline-0123456789ab"))

    def test_refused(self):
        for ref in ("main", "submissions/not-a-uuid", f"yukon/baseline/{'f' * 40}", "yukon/other/x",
                    f"submissions/{SUB}/x"):
            with self.assertRaises(dispatch.NotScorable, msg=ref):
                dispatch.classify(ref, self.SHA)

    def test_baseline_files_match_tier_shape(self):
        with tempfile.TemporaryDirectory() as d:
            dispatch.baseline_files(dispatch.classify(f"yukon/baseline/{self.SHA}", self.SHA), self.SHA, d)
            sub = json.load(open(os.path.join(d, "submitter.json")))
            self.assertEqual(sub["limits"]["suite"], "full")
            self.assertEqual(sub["coauthors"], [])
            self.assertEqual(json.load(open(os.path.join(d, "deps.json")))["dependencies"], [])
            self.assertEqual(open(os.path.join(d, "note.md")).read(), "")


class Collect(unittest.TestCase):
    def test_retry_keeps_the_play_timeout(self):
        plan = {"include": [{"job": "j00-a", "games": "a", "timeout_min": 150, "play_timeout_min": 130},
                            {"job": "j01-b", "games": "b", "timeout_min": 90}]}
        with tempfile.TemporaryDirectory() as d:
            import io, contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                collect.retry(json.dumps(plan), d)
            inc = json.loads(buf.getvalue())["include"]
        self.assertEqual([(j["games"], j["play_timeout_min"]) for j in inc], [("a", 130), ("b", 90)])


    def _bundle(self, root, name, gid, status, cause):
        g = os.path.join(root, "cur", name, "games", gid)
        os.makedirs(os.path.join(g, "game"))
        rec = {"spec": {"game_id": gid}, "status": status}
        if cause:
            rec["infra_cause"] = cause
        json.dump(rec, open(os.path.join(g, "game.json"), "w"))

    def _merge(self, attempts):
        import io, contextlib
        with tempfile.TemporaryDirectory() as d:
            for i, (st, cause) in enumerate(attempts):
                self._bundle(os.path.join(d, "b"), f"games-s1-a{i + 1}-r1", "LT01-0", st, cause)
            with contextlib.redirect_stdout(io.StringIO()):
                collect.merge(os.path.join(d, "b"), os.path.join(d, "out"))
            return json.load(open(os.path.join(d, "out", "LT01-0", "game.json")))

    def test_crash_twice(self):
        # red team: DF crashed on the game and on its re-run -> scored at the state reached, not infra again
        self.assertTrue(self._merge([("infra", "game"), ("infra", "game")]).get("crash_twice"))
        self.assertFalse(self._merge([("infra", "game"), ("infra", "provider")]).get("crash_twice"))
        self.assertFalse(self._merge([("infra", "game")]).get("crash_twice"))
        self.assertFalse(self._merge([("infra", "game"), ("ok", None)]).get("crash_twice"))

    def test_crash_twice_counts_attempts_inside_a_job_and_is_final(self):
        import io, contextlib
        with tempfile.TemporaryDirectory() as d:
            self._bundle(os.path.join(d, "b"), "games-s1-a1-r1", "LT01-0", "infra", "game")
            g = os.path.join(d, "b", "cur", "games-s1-a1-r1", "games", "LT01-0")
            os.makedirs(os.path.join(g, "attempt-0"))
            json.dump({"spec": {"game_id": "LT01-0"}, "status": "infra", "infra_cause": "game"},
                      open(os.path.join(g, "attempt-0", "game.json"), "w"))
            with contextlib.redirect_stdout(io.StringIO()):
                collect.merge(os.path.join(d, "b"), os.path.join(d, "out"))
            self.assertTrue(json.load(open(os.path.join(d, "out", "LT01-0", "game.json")))["crash_twice"])
            # a job whose game crashed twice reports it final: the run-level retry skips it
            out = os.path.join(d, "o")
            os.makedirs(os.path.join(out, "LT01-0"))
            json.dump({"spec": {"game_id": "LT01-0"}, "status": "infra", "crash_twice": True},
                      open(os.path.join(out, "LT01-0", "game.json"), "w"))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                collect.status(out, 1, 1, "j")
            os.makedirs(os.path.join(d, "st"))
            open(os.path.join(d, "st", "status-j.json"), "w").write(buf.getvalue())
            buf = io.StringIO()
            plan = {"include": [{"job": "j", "games": "LT01-0", "timeout_min": 90}]}
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                collect.retry(json.dumps(plan), os.path.join(d, "st"))
            self.assertEqual(json.loads(buf.getvalue())["include"], [])


class Tier(unittest.TestCase):
    def test_new(self):
        r = res(ENV, fake_http(routes()))
        self.assertEqual((r["tier"], r["limits"]["weekly"], r["limits"]["suite"]), ("new", 2, "stage1_until_first_valid"))
        self.assertEqual(r["username"], "alice")
        self.assertEqual(r["coauthors"], ["bob"])

    def test_established_only_elsewhere(self):
        r = res(ENV, fake_http(routes(participations=[part(OURS, "accepted")])))
        self.assertEqual(r["tier"], "new")                       # an accepted result here doesn't count
        r = res(ENV, fake_http(routes(participations=[part("other", "rejected")])))
        self.assertEqual(r["tier"], "new")
        r = res(ENV, fake_http(routes(participations=[part("other", "accepted")])))
        self.assertEqual((r["tier"], r["limits"]["weekly"]), ("established", 7))

    def test_same_challenge_other_track_not_established(self):
        env = {**ENV, "DFBENCH_YUKON_CHALLENGE_ID": "ch1"}
        r = res(env, fake_http(routes(participations=[part("other", "accepted", "ch1")])))
        self.assertEqual(r["tier"], "new")

    def test_probation_unless_established(self):
        young = "2026-10-10T00:00:00Z"
        r = res(ENV, fake_http(routes(created=young)))
        self.assertEqual((r["tier"], r["limits"]["suite"]), ("probation", "stage1"))
        r = res(ENV, fake_http(routes(created=young, participations=[part("other", "accepted")])))
        self.assertEqual(r["tier"], "established")
        # probation lasts the whole window: a scored stage-1 run here doesn't lift it
        r = res(ENV, fake_http(routes(created=young)), valid=True)
        self.assertEqual((r["tier"], r["limits"]["suite"]), ("probation", "stage1"))
        # an older account with a valid score here is established
        r = res(ENV, fake_http(routes()), valid=True)
        self.assertEqual((r["tier"], r["reason"]), ("established", "valid score on this benchmark"))
        # an organiser override still wins over probation
        env = {**ENV, "DFBENCH_TIER_OVERRIDES": json.dumps({"alice": "established"})}
        r = res(env, fake_http(routes(created=young)))
        self.assertEqual(r["tier"], "established")

    def test_promoted_or_superseded_counts(self):
        r = res(ENV, fake_http(routes(participations=[part("other", "rejected", promotion="superseded")])))
        self.assertEqual(r["tier"], "established")

    def test_override_and_config(self):
        env = {**ENV, "DFBENCH_TIER_OVERRIDES": json.dumps({"alice": "established"}),
               "DFBENCH_TIERS": json.dumps({"established": {"weekly": 9}})}
        r = res(env, fake_http(routes(created="2026-10-20T00:00:00Z")))
        self.assertEqual((r["tier"], r["reason"], r["limits"]["weekly"], r["limits"]["in_flight"]),
                         ("established", "organiser override", 9, 1))
        with self.assertRaises(tier.Infra):
            res({**ENV, "DFBENCH_TIER_OVERRIDES": '{"alice": "vip"}'}, fake_http(routes()))

    def test_fail_closed(self):
        for bad in ({f"/users/alice": tier.Infra("HTTP 503")}, {f"/api/solvers/alice/profile": tier.Infra("x")}):
            with self.assertRaises(tier.Infra):
                res(ENV, fake_http({**routes(), **bad}))
        with self.assertRaises(tier.Infra):
            tier.resolve("not-a-uuid", ENV, fake_http(routes()), NOW, valid_here=lambda u: False)
        with self.assertRaises(tier.Infra):
            res({}, fake_http(routes()))
        r = routes(); r[f"/api/submissions/{SUB}"]["submission"]["solverUsername"] = None
        with self.assertRaises(tier.Infra):
            res(ENV, fake_http(r))

    def test_yukon_headers_optional_bearer(self):
        self.assertEqual(tier.yukon_headers({}), {})
        self.assertEqual(tier.yukon_headers({"YUKON_API_KEY": "yk"}), {"Authorization": "Bearer yk"})

    def test_gate_leader_sends_key(self):
        seen = []

        def http(url, headers, **_):
            seen.append(headers)
            return {"benchmark": {"currentBestScore": 70.0, "currentBestMetrics": {"stage1_point": 71.0}}}
        env = {"DFBENCH_YUKON_API": "https://yukon.example"}
        self.assertEqual(gate.leader("b", env, http), (71.0, 70.0))
        self.assertEqual(seen[-1], {})
        gate.leader("b", {**env, "YUKON_API_KEY": "yk"}, http)
        self.assertEqual(seen[-1], {"Authorization": "Bearer yk"})

    def test_prior_main_sends_key(self):
        import inspect
        self.assertIn("yukon_headers()", inspect.getsource(prior.main))

    def test_key_sent_to_yukon_not_github(self):
        h = fake_http(routes())
        res({**ENV, "YUKON_API_KEY": "yk"}, h)
        for url, headers in h.calls:
            if "yukon.example" in url:
                self.assertEqual(headers.get("Authorization"), "Bearer yk")
            else:
                self.assertNotIn("yk", json.dumps(headers))

    def test_http_retries_then_infra(self):
        n = []

        def opener(req, timeout):
            n.append(1)
            raise urllib.error.HTTPError(req.full_url, 503, "x", {}, None)
        tier.time.sleep = lambda s: None
        with self.assertRaises(tier.Infra):
            tier.http_json("https://x.example/a", opener=opener)
        self.assertEqual(len(n), 3)

        def opener404(req, timeout):
            n.append(1)
            raise urllib.error.HTTPError(req.full_url, 404, "x", {}, None)
        n.clear()
        with self.assertRaises(tier.Infra):
            tier.http_json("https://x.example/a", opener=opener404)
        self.assertEqual(len(n), 1)


def adm(user="alice", sub="s1", in_flight=1, weekly=2, suite="stage1_until_first_valid", glob=None, rerun=False,
        tree=None, season_cap=0):
    return argparse.Namespace(submission=sub, user=user, in_flight=in_flight, weekly=weekly, suite=suite,
                              global_cap=glob, rerun=rerun, run="1", tree=tree, season_cap=season_cap)


def fin(sub, status):
    return argparse.Namespace(submission=sub, status=status, score=None, stage=None, run=None)


class Ledger(unittest.TestCase):
    def test_season_cap(self):
        """A tier's `season` caps counted submissions over the whole season (the per-season ledger), across weeks;
        infra failures and cancellations don't count; 0 means no cap."""
        led = {}
        weeks = [datetime.datetime(2026, 11, d, 12, tzinfo=datetime.timezone.utc) for d in (2, 9, 16)]
        for i, t in enumerate(weeks[:2]):
            self.assertTrue(ledger.admit_decision(led, adm(sub=f"s{i}", season_cap=2, weekly=5), t)["admitted"])
            ledger.finish_decision(led, fin(f"s{i}", "scored"))
        r = ledger.admit_decision(led, adm(sub="s2", season_cap=2, weekly=5), weeks[2])
        self.assertFalse(r["admitted"]); self.assertIn("season limit", r["reason"])
        self.assertTrue(ledger.admit_decision(led, adm(sub="s2", season_cap=0, weekly=5), weeks[2])["admitted"])
        led = {}
        ledger.admit_decision(led, adm(sub="a", season_cap=1, weekly=5), weeks[0])
        ledger.finish_decision(led, fin("a", "infra_failed"))
        self.assertTrue(ledger.admit_decision(led, adm(sub="b", season_cap=1, weekly=5), weeks[0])["admitted"])

    def test_tester_tier_defaults(self):
        t = tier.tiers_config({})["tester"]
        self.assertEqual((t["weekly"], t["in_flight"], t["season"], t["suite"]), (3, 1, 8, "full"))

    def test_flow(self):
        led = {}
        r = ledger.admit_decision(led, adm(sub="s1"), NOW)
        self.assertTrue(r["admitted"]); self.assertFalse(r["full_suite"])
        self.assertFalse(ledger.admit_decision(led, adm(sub="s2"), NOW)["admitted"])   # in flight
        ledger.finish_decision(led, fin("s1", "scored"), NOW)
        r = ledger.admit_decision(led, adm(sub="s2"), NOW)
        self.assertTrue(r["admitted"]); self.assertTrue(r["full_suite"])                 # first valid unlocks
        ledger.finish_decision(led, fin("s2", "infra_failed"), NOW)
        self.assertTrue(ledger.admit_decision(led, adm(sub="s3"), NOW)["admitted"])     # infra doesn't count
        ledger.finish_decision(led, fin("s3", "rejected"), NOW)
        r = ledger.admit_decision(led, adm(sub="s4"), NOW)
        self.assertFalse(r["admitted"]); self.assertIn("weekly limit", r["reason"]); self.assertIn("2026-10-26", r["reason"])
        self.assertTrue(ledger.admit_decision(led, adm(sub="s3", rerun=True), NOW)["admitted"])
        nxt = NOW + datetime.timedelta(days=4)
        ledger.finish_decision(led, fin("s3", "cancelled"), NOW)
        self.assertTrue(ledger.admit_decision(led, adm(sub="s5"), nxt)["admitted"])     # new week

    def test_identical_tree_refused_not_counted(self):
        # red team: resubmitting an unchanged harness for another draw of DF's variance
        led = {}
        self.assertTrue(ledger.admit_decision(led, adm(sub="s1", tree="t1", weekly=5), NOW)["admitted"])
        ledger.finish_decision(led, fin("s1", "infra_failed"), NOW)
        self.assertTrue(ledger.admit_decision(led, adm(sub="s2", tree="t1", weekly=5), NOW)["admitted"])  # not scored
        ledger.finish_decision(led, fin("s2", "scored"), NOW)
        r = ledger.admit_decision(led, adm(sub="s3", tree="t1", weekly=5), NOW)
        self.assertFalse(r["admitted"]); self.assertIn("identical to your submission s2", r["reason"])
        r = ledger.admit_decision(led, adm("bob", "s4", tree="t1", weekly=5), NOW)
        self.assertFalse(r["admitted"]); self.assertIn("alice's submission s2", r["reason"])
        self.assertEqual(len(led["entries"]), 2)                                       # neither counted
        self.assertTrue(ledger.admit_decision(led, adm(sub="s2", tree="t1", rerun=True), NOW)["admitted"])
        ledger.finish_decision(led, fin("s2", "scored"), NOW)
        self.assertTrue(ledger.admit_decision(led, adm(sub="s5", tree="t2", weekly=5), NOW)["admitted"])

    def test_global_allowance(self):
        led = {}
        self.assertTrue(ledger.admit_decision(led, adm("a", "s1", glob=2), NOW)["admitted"])
        self.assertTrue(ledger.admit_decision(led, adm("b", "s2", glob=2), NOW)["admitted"])
        r = ledger.admit_decision(led, adm("c", "s3", glob=2), NOW)
        self.assertFalse(r["admitted"]); self.assertIn("global allowance", r["reason"]); self.assertIn("doesn't count", r["reason"])
        self.assertEqual(len(led["entries"]), 2)

    def test_suites(self):
        self.assertTrue(ledger.full_suite("full", None))
        self.assertFalse(ledger.full_suite("stage1", {"first_valid": {"x": 1}}))
        self.assertTrue(ledger.full_suite("stage1_until_first_valid", {"first_valid": {"x": 1}}))


class Emit(unittest.TestCase):
    S = {"score": 61.0, "metrics": {"stage": 2, "lb95": 61.0, "credits_per_game_year": 0.21}}

    def test_scalar(self):
        self.assertEqual(emit_score.emit(self.S, dossier={"verdict": "pass"})["score"], 61.0)
        for v in ("fail", "hold", "maybe", None):
            s = emit_score.emit(self.S, dossier={"verdict": v} if v else None)
            self.assertEqual((s["score"], s["partial"], s["metrics"]["score_if_accepted"]), (0, True, 61.0))
        self.assertEqual(emit_score.emit(self.S, dossier={"verdict": "maybe"})["metrics"]["judge_verdict"], "hold")
        s = emit_score.emit(self.S, dossier={"verdict": "fail"}, override="pass", actor="org")
        self.assertEqual((s["score"], s["metrics"]["judge_verdict"]), (61.0, "pass"))
        self.assertEqual(emit_score.emit(self.S, override="fail")["score"], 0)
        s = emit_score.emit(self.S, not_run="does not beat the leader", extra={"tier": "new"})
        self.assertEqual((s["score"], s["metrics"]["judge_verdict"], s["metrics"]["tier"]),
                         (61.0, "not_run: does not beat the leader", "new"))

    def test_pareto_shape(self):
        p = emit_score.emit(self.S, "pareto", dossier={"verdict": "pass"})
        self.assertEqual((p["valid"], p["scores"]), (True, [61.0, 0.21]))
        p = emit_score.emit(self.S, "pareto", dossier={"verdict": "fail"})
        self.assertFalse(p["valid"]); self.assertTrue(p["reason"])
        p = emit_score.emit({"score": 0, "metrics": {"stage": 1, "lb95": 40.0, "credits_per_game_year": 0.2}},
                            "pareto", dossier={"verdict": "pass"})
        self.assertEqual((p["valid"], p["reason"]), (False, "stage 1 only"))


class Gate(unittest.TestCase):
    def test_leader(self):
        h = fake_http({f"/api/benchmarks/{OURS}": {"benchmark": {"currentBestScore": 52.5,
                                                                  "currentBestMetrics": {"stage1_point": 63.0}}}})
        self.assertEqual(gate.leader(OURS, ENV, h), (63.0, 52.5))
        with self.assertRaises(tier.Infra):
            gate.leader(OURS, ENV, fake_http({}))

    def test_stage2(self):
        s1 = {"metrics": {"ub95": 60.0, "point": 55.0}}
        self.assertTrue(gate.stage2(s1, None)[0]); self.assertTrue(gate.stage2(s1, "59.9")[0])
        self.assertFalse(gate.stage2(s1, "60.1")[0]); self.assertTrue(gate.stage2(s1, "70", force=True)[0])
        self.assertFalse(gate.stage2({"metrics": {}}, None)[0])

    def test_stage2_note(self):
        n = gate.stage2_note
        # PR 23 on the dev repo (2026-11-02): full suite, stage-1 ub95 94.27 under the leader's 94.52
        t = n(1, "true", "tester", "false", "94.27", "94.52")
        self.assertTrue(t.startswith("skipped: stage-1 upper bound 94.27 < leader's stage-1 point 94.52"), t)
        self.assertIn("could not lead", t); self.assertIn("not a failure", t)
        self.assertTrue(n(1, "false", "new", "true", "99", "94.5").startswith("skipped: tier new plays stage 1 only"))
        self.assertTrue(n(1, "false", "probation", "false", "90", "94.5").startswith("skipped: tier probation"))
        self.assertTrue(n(1, "true", "tester", "false", "", "94.5").startswith("skipped: no stage-1 score"))
        self.assertTrue(n(1, "true", "tester", "true", "95", "94.5").startswith("not completed"))
        self.assertEqual(n(2, "true", "tester", "true", "95.2", "94.52"),
                         "played (stage-1 upper bound 95.2 >= leader's stage-1 point 94.52)")
        self.assertEqual(n(2, "true", "", "true", "80", ""), "played (no leader yet)")
        self.assertEqual(n(2, "true", "", "true", "80", "94.5"), "played (forced by the organiser)")

    def test_finalize_stage2_metric(self):
        base = {"score": 0, "partial": True, "metrics": {"stage": 1, "point": 91.6, "ub95": 94.27, "lb95": 88.71}}
        env = {"DFBENCH_FULL_SUITE": "true", "DFBENCH_TIER": "tester", "DFBENCH_RUN_STAGE2": "false",
               "DFBENCH_STAGE1_UB95": "94.27", "DFBENCH_LEADER_S1": "94.52", "GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1"}
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "score.json"), os.path.join(d, "o", "scored.json")
            json.dump(base, open(src, "w"))
            with contextlib.redirect_stdout(io.StringIO()):
                collect.finalize(src, "91.6", out, env)
            m = json.load(open(out))["metrics"]
            self.assertEqual(list(m)[:2], ["stage2", "leader_stage1_point"])   # first rows of Yukon's table
            self.assertEqual(m["leader_stage1_point"], 94.52); self.assertEqual(m["stage1_point"], 91.6)
            self.assertTrue(all(not isinstance(v, (dict, list)) for v in m.values()))
            full = {"score": 87.2, "metrics": {"stage": 2, "point": 87.57}}     # complete: appended, not first
            json.dump(full, open(src, "w"))
            with contextlib.redirect_stdout(io.StringIO()):
                collect.finalize(src, "94.99", out, {**env, "DFBENCH_RUN_STAGE2": "true", "DFBENCH_STAGE1_UB95": "95.6"})
            m = json.load(open(out))["metrics"]
            self.assertEqual(list(m)[0], "stage"); self.assertTrue(m["stage2"].startswith("played"))
            with contextlib.redirect_stdout(io.StringIO()):
                collect.finalize(src, "94.99", out, {"GITHUB_RUN_ID": "1"})     # older callers: unchanged
            self.assertNotIn("stage2", json.load(open(out))["metrics"])

    def test_judge_needed(self):
        self.assertFalse(gate.judge_needed({"score": 0, "metrics": {"stage": 1}})[0])
        self.assertTrue(gate.judge_needed({"score": 50, "metrics": {"stage": 2}}, "")[0])
        self.assertTrue(gate.judge_needed({"score": 50, "metrics": {"stage": 2}}, "49")[0])
        self.assertFalse(gate.judge_needed({"score": 50, "metrics": {"stage": 2}}, "50")[0])


class PriorBaseFromGit(unittest.TestCase):
    """The base producer is the promotion in the submission's own history, not the incumbent at judging time."""

    def test_baseline_promotion_and_later_export(self):
        d = tempfile.mkdtemp(prefix="prior-git-")
        g = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True, text=True).stdout.strip()
        g("init", "-q"); g("config", "user.email", "t@example.com"); g("config", "user.name", "t")

        def commit(msg, path, text):
            os.makedirs(os.path.dirname(os.path.join(d, path)) or d, exist_ok=True)
            with open(os.path.join(d, path), "w") as f:
                f.write(text)
            g("add", "-A"); g("commit", "-qm", msg)
            return g("rev-parse", "HEAD")
        uid = "9b597a76-9bf9-4923-a9d4-1c8ee83067a9"
        plain = commit("dfbench s0 trusted tree @ abc, submission/ reset to the plain baseline", "submission/a.py", "1")
        promo = commit(f"Validate submission {uid}", "submission/a.py", "2")
        export = commit("dfbench s0 trusted tree @ def (research main)", "README.md", "docs")
        self.assertEqual(prior.base_producer_from_git(d, plain), [])
        self.assertEqual(prior.base_producer_from_git(d, promo), [uid])
        self.assertEqual(prior.base_producer_from_git(d, export), [uid])     # an export keeps main's submission/
        self.assertIsNone(prior.base_producer_from_git(d, "0" * 40))         # git can't tell -> the incumbent
        self.assertIsNone(prior.base_producer_from_git(d, None))


class Prior(unittest.TestCase):
    dep, acc, inc = ("d" * 8 + "-0000-0000-0000-000000000000", "e" * 8 + "-0000-0000-0000-000000000000",
                     "f" * 8 + "-0000-0000-0000-000000000000")

    def http(self, listing=True):
        routes = {
            f"/api/submissions/{self.dep}": {"submission": {"benchmarkId": "other", "note": "dep note"}},
            f"/api/submissions/{self.acc}": {"submission": {"benchmarkId": OURS, "note": "acc note",
                                                             "submissionCommitSha": None, "solverUsername": "bob"}},
            f"/api/submissions/{self.inc}": {"submission": {"benchmarkId": OURS, "status": "accepted",
                                                             "promotionStatus": "promoted", "coauthors": ["c"]}},
        }
        if listing:
            routes[f"/api/benchmarks/{OURS}/submissions"] = {"submissions": [
                {"id": self.acc, "status": "accepted", "promotionStatus": "superseded", "promotionFinishedAt": "2026-10-21"},
                {"id": self.inc, "status": "accepted", "promotionStatus": "promoted", "promotionFinishedAt": "2026-10-22"},
                {"id": "x", "status": "rejected"}]}
        return fake_http(routes)

    def test_build(self):
        sub = {"submission": SUB, "benchmark_id": OURS, "dependencies": [{"submissionId": self.dep, "rationale": "r"}]}
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(prior.build(sub, d, "https://y", {}, ".", 5, 1000, http=self.http()), 3)
            # judge's context format: base producer first, then dependencies, then recent accepted
            self.assertEqual(sorted(n for n in os.listdir(d) if n[0].isdigit()),
                             [f"00-{self.inc}", f"01-{self.dep}", f"02-{self.acc}"])
            self.assertEqual(open(os.path.join(d, "base_producers.txt")).read(), self.inc)
            m = json.load(open(os.path.join(d, f"00-{self.inc}", "meta.json")))
            self.assertEqual((m["submission_id"], m["produced_base"], m["status"], m["coauthors"]),
                             (self.inc, True, "promoted", ["c"]))
            m = json.load(open(os.path.join(d, f"01-{self.dep}", "meta.json")))
            self.assertEqual((m["why"], m["diff_missing"], m["produced_base"]), ("dependency", "another benchmark", False))
            m = json.load(open(os.path.join(d, f"02-{self.acc}", "meta.json")))
            self.assertEqual(m["submitter"], "bob")
            self.assertEqual(open(os.path.join(d, f"02-{self.acc}", "note.md")).read(), "acc note")
            self.assertFalse(any(n.endswith("-x") for n in os.listdir(d)))

    def test_fallback_producer_when_yukon_list_unreadable(self):
        sub = {"submission": SUB, "benchmark_id": OURS, "dependencies": []}
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(prior.build(sub, d, "https://y", {}, ".", 5, 1000, http=self.http(listing=False),
                                         fallback_producers=[self.inc, ""]), 1)
            self.assertEqual(open(os.path.join(d, "base_producers.txt")).read(), self.inc)
            self.assertTrue(os.path.exists(os.path.join(d, "_errors.json")))

    def test_starter_base_has_no_producer(self):
        sub = {"submission": SUB, "benchmark_id": OURS, "dependencies": []}
        h = fake_http({f"/api/benchmarks/{OURS}/submissions": {"submissions": []}})
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(prior.build(sub, d, "https://y", {}, ".", 5, 1000, http=h, fallback_producers=["z"]), 0)
            self.assertEqual(open(os.path.join(d, "base_producers.txt")).read(), "")


class OverlapScan(unittest.TestCase):
    """prior.py's overlap scan over every published submission (accepted or not) and the judge's signal on it."""
    alice, own, unpub = ("a1" * 4 + "-0000-0000-0000-000000000000", "b2" * 4 + "-0000-0000-0000-000000000000",
                         "c3" * 4 + "-0000-0000-0000-000000000000")
    PLANNER = "".join(f"def drink_rule_{i}(fort):  return fort.stocks['drink'] < {i} * fort.citizens\n"
                      for i in range(26))

    def git(self, *a):
        r = subprocess.run(["git", "-C", self.repo, *a], capture_output=True, text=True,
                           env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def commit(self, files, msg):
        for path, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(self.repo, path)), exist_ok=True)
            with open(os.path.join(self.repo, path), "w") as f:
                f.write(text)
        self.git("add", "-A")
        self.git("commit", "-qm", msg)
        return self.git("rev-parse", "HEAD")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        self.git("init", "-q", "-b", "main")
        self.base = self.commit({"submission/agent.py": "print('starter harness main loop here')\n"}, "starter")
        # alice's non-improving submission (closed PR, still published): the planner module
        self.git("checkout", "-q", "-b", "alice")
        self.alice_sha = self.commit({"submission/planner.py": self.PLANNER}, "alice")
        self.git("update-ref", f"refs/remotes/origin/submissions/{self.alice}", self.alice_sha)
        # bob's own earlier submission with the same module (bob may reuse his own work)
        self.git("checkout", "-q", "-b", "own", self.base)
        self.own_sha = self.commit({"submission/planner.py": self.PLANNER}, "own")
        # bob's current submission copies the module without declaring alice
        self.git("checkout", "-q", "-b", "head", self.base)
        self.commit({"submission/planner.py": self.PLANNER + "# tuned by bob\n"}, "bob")
        self.rows = [
            {"id": self.alice, "status": "rejected", "solverUsername": "alice", "createdAt": "2026-10-20",
             "submissionCommitSha": self.alice_sha},
            {"id": self.own, "status": "rejected", "solverUsername": "bob", "createdAt": "2026-10-21",
             "submissionCommitSha": self.own_sha},
            {"id": self.unpub, "status": "running", "solverUsername": "carol", "createdAt": "2026-10-22",
             "submissionCommitSha": None},
        ]
        self.sub = {"submission": SUB, "benchmark_id": OURS, "username": "bob", "dependencies": []}

    def tearDown(self):
        self.tmp.cleanup()

    def http(self):
        routes = {f"/api/benchmarks/{OURS}/submissions": {"submissions": self.rows}}
        for r in self.rows:
            routes[f"/api/submissions/{r['id']}"] = {"submission": {**r, "benchmarkId": OURS, "note": "n"}}
        return fake_http(routes)

    def opts(self, **kw):
        return {"base": self.base, "head": "HEAD", "fetch": False, **kw}

    def test_uncredited_copy_of_non_improving_submission_is_found_and_raises_high_signal(self):
        out = os.path.join(self.tmp.name, "prior")
        n = prior.build(self.sub, out, "https://y", {}, self.repo, 5, 200_000, http=self.http(),
                        scan_opts=self.opts())
        self.assertEqual(n, 1)
        self.assertEqual(sorted(x for x in os.listdir(out) if x[0].isdigit()), [f"00-{self.alice}"])
        m = json.load(open(os.path.join(out, f"00-{self.alice}", "meta.json")))
        self.assertEqual((m["why"], m["overlap_shared_lines"], m["status"]), ("overlap_scan", 26, "rejected"))
        st = json.load(open(os.path.join(out, "_scan.json")))
        self.assertTrue(st["ran"])
        self.assertEqual(st["skipped"], {"own": [self.own], "unpublished": [self.unpub]})
        # the judge's deterministic rule applies to the scan hit: high, which no model can clear
        from judgelib import evidence as E, signals
        ctx = E.load_context(out, set(), set(), "bob")
        head = E.collect_submission(self.repo, self.base, "HEAD")["scan_lines"]
        sig = signals.deterministic_signals(ctx, E.overlap(head, ctx), [])
        self.assertEqual([(s["kind"], s["level"]) for s in sig], [("undeclared_overlap", "high")])
        self.assertEqual(ctx[0]["why"], "overlap_scan")
        self.assertEqual(E.load_context_status(out)["scan"]["hits"][0]["id"], self.alice)
        # declared: no signal
        ctx = E.load_context(out, {self.alice}, set(), "bob")
        self.assertEqual(signals.deterministic_signals(ctx, E.overlap(head, ctx), []), [])

    def test_own_earlier_submission_is_not_undeclared_copying(self):
        from judgelib import evidence as E, signals
        out = os.path.join(self.tmp.name, "own")
        os.makedirs(os.path.join(out, f"00-{self.own}"))
        json.dump({"submission_id": self.own, "submitter": "Bob", "why": "recent_accepted"},
                  open(os.path.join(out, f"00-{self.own}", "meta.json"), "w"))
        with open(os.path.join(out, f"00-{self.own}", "diff.patch"), "w") as f:
            f.write(self.git("diff", f"{self.own_sha}^", self.own_sha, "--", "submission/") + "\n")
        ctx = E.load_context(out, set(), set(), "bob")
        self.assertTrue(ctx[0]["own"])
        head = E.collect_submission(self.repo, self.base, "HEAD")["scan_lines"]
        self.assertEqual(signals.deterministic_signals(ctx, E.overlap(head, ctx), []), [])

    def test_scan_cap_and_timeout(self):
        rows = [dict(self.rows[0], id=f"{i:08d}-0000-0000-0000-000000000000", createdAt=f"2026-10-{10 + i}")
                for i in range(3)]
        hits, st = prior.scan(self.sub, rows, set(), self.repo, **self.opts(max_scan=2, top=1))
        self.assertEqual(st["scanned"], 2)
        self.assertEqual(st["skipped"]["over_scan_cap"], [rows[0]["id"]])       # the oldest
        self.assertEqual(st["skipped"]["below_top"], [rows[1]["id"]])
        self.assertEqual([r["id"] for r, _ in hits], [rows[2]["id"]])
        ticks = iter([0, 0, 1000, 1000, 1000])
        _, st = prior.scan(self.sub, rows, set(), self.repo, **self.opts(timeout=10, clock=lambda: next(ticks)))
        self.assertEqual(st["scanned"], 1)
        self.assertEqual(len(st["skipped"]["timeout"]), 2)

    def test_yukon_unreachable_degrades_and_says_so(self):
        out = os.path.join(self.tmp.name, "deg")
        h = fake_http({})
        prior.build(self.sub, out, "https://y", {}, self.repo, 5, 200_000, http=h, scan_opts=self.opts())
        st = json.load(open(os.path.join(out, "_scan.json")))
        self.assertFalse(st["ran"])
        self.assertIn("couldn't be read", st["degraded"])


if __name__ == "__main__":
    unittest.main()


class SealTests(unittest.TestCase):
    SEAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin", "seal.sh")

    def test_round_trip_big_file(self):
        # > the pipe buffer: `tail | head` under pipefail used to SIGPIPE (exit 141) on the 130 MB pool bundle
        with tempfile.TemporaryDirectory() as d:
            key, src, enc, out = (os.path.join(d, n) for n in ("k", "in", "in.enc", "out"))
            data = os.urandom(4 << 20)
            open(src, "wb").write(data)
            for args in (["newkey", key], ["seal", src, enc, key], ["open", enc, out, key]):
                subprocess.run(["bash", self.SEAL, *args], check=True, capture_output=True)
            self.assertEqual(open(out, "rb").read(), data)


class AttributionLagTest(unittest.TestCase):
    """Yukon's attribution record can lag the dispatch: a 404 is retried before admit fails closed (dev, 2026-10-29)."""

    def test_404_then_200_is_retried(self):
        import io, urllib.error
        calls = []

        def opener(req, timeout=20):
            calls.append(req.full_url)
            if len(calls) < 3:
                raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
            return io.BytesIO(b'{"declaration": "none", "dependencies": []}')
        out = tier.http_json("https://y/api/submissions/x/attribution", tries=10, opener=opener, retry_404=True,
                             sleep=lambda s: None)
        self.assertEqual(out["declaration"], "none")
        self.assertEqual(len(calls), 3)

    def test_404_is_final_without_retry_404(self):
        import urllib.error

        def opener(req, timeout=20):
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
        with self.assertRaises(tier.Infra):
            tier.http_json("https://y/api/submissions/x", opener=opener, sleep=lambda s: None)


class AttributionAccessTest(unittest.TestCase):
    """Only the author can read a submission's attribution until it's published, so the organiser key gets 404 while
    the submission is still validating (dev, 2026-10-28): admit records it as unavailable instead of failing."""

    def test_404_becomes_unavailable(self):
        def http(url, headers=None, **kw):
            raise tier.Infra("/api/submissions/x/attribution: HTTP 404")
        self.assertEqual(tier.attribution("https://y", "x", {}, http), tier.UNAVAILABLE)

    def test_other_errors_still_fail_closed(self):
        def http(url, headers=None, **kw):
            raise tier.Infra("/api/submissions/x/attribution: HTTP 503")
        with self.assertRaises(tier.Infra):
            tier.attribution("https://y", "x", {}, http)

    def test_published_record_is_returned(self):
        rec = {"declaration": "provided", "dependencies": [{"submissionId": "a"}]}
        self.assertEqual(tier.attribution("https://y", "x", {}, lambda url, headers=None, **kw: rec), rec)
