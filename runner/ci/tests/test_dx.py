"""Tests for the second tester's feedback (2026-10-28): actionable admission failures, linked infra retries and
quota accounting, result labels, and the smoke test's verdict. No Docker, no network.
Run: python3 -m unittest discover -s runner/ci/tests -t .
"""
import argparse, contextlib, datetime, io, json, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bin"))
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", ".."))
import failure, ledger, tier  # noqa: E402
from dfbenchlib import cli, score as S  # noqa: E402

NOW = datetime.datetime(2026, 10, 28, 20, tzinfo=datetime.timezone.utc)


def adm(user="mmurrs", sub="s1", tree="t1", weekly=3, season_cap=8):
    return argparse.Namespace(submission=sub, user=user, in_flight=1, weekly=weekly, suite="full", global_cap=60,
                              rerun=False, run="1", tree=tree, season_cap=season_cap)


class Classify(unittest.TestCase):
    def test_attribution_404_is_yukon_and_retryable(self):
        r = failure.classify("/api/submissions/x/attribution", 404)
        self.assertEqual((r["owner"], r["retryable"]), ("Yukon", True))
        self.assertIn("not your fault", r["action"])
        self.assertIn("author", r["cause"])

    def test_refused_yukon_key_is_the_organisers(self):
        r = failure.classify("/api/submissions/x", 401)
        self.assertEqual((r["owner"], r["retryable"]), ("organiser", False))
        self.assertIn("resubmitting won't help", r["action"])

    def test_github_rate_limit(self):
        r = failure.classify("api.github.com/users/x", 403)
        self.assertEqual((r["owner"], r["retryable"]), ("GitHub", True))

    def test_misconfiguration(self):
        r = failure.classify("config:DFBENCH_YUKON_API")
        self.assertEqual((r["owner"], r["retryable"]), ("organiser", False))

    def test_renders_name_the_endpoint_status_and_owner(self):
        r = failure.classify("/api/solvers/x/profile", 503, "HTTP 503")
        for fmt in ("log", "summary", "comment"):
            out = failure.render(r, fmt)
            self.assertIn("/api/solvers/x/profile", out)
            self.assertIn("HTTP 503", out)
            self.assertIn("Yukon", out)


class ReportFailure(unittest.TestCase):
    def test_writes_record_partial_and_summary(self):
        with tempfile.TemporaryDirectory() as d:
            summ = os.path.join(d, "summary.md")
            env = {"DFBENCH_YUKON_API": "https://y", "GITHUB_STEP_SUMMARY": summ}
            http = lambda url, headers=None, **kw: {"submission": {"solverUsername": "mmurrs",
                                                                   "submissionCommitSha": "abc"}}
            e = tier.Infra("/api/solvers/mmurrs/profile: HTTP 503", "/api/solvers/mmurrs/profile", 503)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                tier.report_failure("s1", d, e, env=env, http=http)
            rec = json.load(open(os.path.join(d, "admit_error.json")))
            self.assertEqual((rec["owner"], rec["status"]), ("Yukon", 503))
            self.assertEqual(json.load(open(os.path.join(d, "partial.json")))["username"], "mmurrs")
            self.assertIn("Admission failed", open(summ).read())
            self.assertNotIn("cannot establish the submitter's tier", err.getvalue())
            self.assertIn("/api/solvers/mmurrs/profile", err.getvalue())

    def test_http_failures_carry_endpoint_and_status(self):
        import urllib.error

        def opener(req, timeout=20):
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
        with self.assertRaises(tier.Infra) as c:
            tier.http_json("https://y/api/submissions/x", opener=opener, sleep=lambda s: None)
        self.assertEqual((c.exception.endpoint, c.exception.status), ("/api/submissions/x", 401))


class LinkedRetries(unittest.TestCase):
    def test_infra_attempt_is_recorded_not_counted_and_linked(self):
        led = {"entries": [], "users": {}}
        ledger.infra_decision(led, argparse.Namespace(submission="old", user="mmurrs", tree="t1", run="9",
                                                      reason="attribution 404"), NOW)
        self.assertEqual(led["entries"][0]["status"], "infra_failed")
        r = ledger.admit_decision(led, adm(sub="new"), NOW)
        self.assertTrue(r["admitted"])
        self.assertEqual(r["retry_of"], "old")
        self.assertEqual(led["entries"][-1]["retry_of"], "old")
        self.assertEqual((r["quota"]["weekly_used"], r["quota"]["counts"]), (1, True))   # the failed one didn't count

    def test_identical_tree_refusal_exempts_infra_failed(self):
        led = {"entries": [], "users": {}}
        ledger.infra_decision(led, argparse.Namespace(submission="old", user="mmurrs", tree="t1", run="9", reason=""), NOW)
        self.assertTrue(ledger.admit_decision(led, adm(sub="new"), NOW)["admitted"])

    def test_scored_tree_is_still_refused(self):
        led = {"entries": [{"submission": "x", "user": "mmurrs", "week": ledger.week_of(NOW.isoformat()),
                            "status": "scored", "tree": "t1"}], "users": {}}
        r = ledger.admit_decision(led, adm(sub="new"), NOW)
        self.assertFalse(r["admitted"])

    def test_refusal_reports_quota_and_does_not_count(self):
        led = {"entries": [], "users": {}}
        for i in range(3):
            ledger.admit_decision(led, adm(sub=f"s{i}", tree=f"t{i}"), NOW)
            led["entries"][-1]["status"] = "scored"
        r = ledger.admit_decision(led, adm(sub="s9", tree="t9"), NOW)
        self.assertFalse(r["admitted"])
        self.assertEqual(r["quota"], {"counts": False, "weekly_used": 3, "weekly_limit": 3, "season_used": 3,
                                      "season_cap": 8})

    def test_infra_record_is_idempotent(self):
        led = {"entries": [], "users": {}}
        a = argparse.Namespace(submission="old", user="u", tree="t", run="1", reason="")
        ledger.infra_decision(led, a, NOW)
        self.assertTrue(ledger.infra_decision(led, a, NOW).get("_nowrite"))
        self.assertEqual(len(led["entries"]), 1)


class Labels(unittest.TestCase):
    TASKS = [{"id": t} for t in ("LT01", "LT02", "MY1", "OP1")]

    def labels(self, played, suite_name="season0", kind=None, stack="real", smoke=False):
        env = {k: v for k, v in (("DFBENCH_RESULT_KIND", kind), ("DFBENCH_STACK", stack)) if v}
        old = {k: os.environ.pop(k, None) for k in ("DFBENCH_RESULT_KIND", "DFBENCH_STACK")}
        os.environ.update(env)
        try:
            with tempfile.TemporaryDirectory() as d:
                suite = {"name": suite_name, "smoke": smoke,
                         "anchors_note": "Native x86_64, GitHub-hosted, run 40598507498"}
                return S.result_labels(d, suite, self.TASKS, {t: [1] for t in played}, [])
        finally:
            for k, v in old.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v

    def test_only_an_official_full_real_run_on_the_private_pool_is_comparable(self):
        self.assertTrue(self.labels(["LT01", "LT02", "MY1", "OP1"], kind="official")["official_comparable"])
        self.assertFalse(self.labels(["LT01", "LT02", "MY1", "OP1"])["official_comparable"])         # local
        self.assertFalse(self.labels(["LT01", "LT02", "MY1", "OP1"], kind="official", stack="fake")["official_comparable"])
        self.assertFalse(self.labels(["LT01", "LT02", "MY1", "OP1"], "season0-int", "official")["official_comparable"])

    def test_scopes(self):
        self.assertEqual(self.labels(["LT01", "LT02", "MY1", "OP1"])["scope"], "full")
        self.assertEqual(self.labels(["LT01", "MY1"])["scope"], "partial")
        self.assertEqual(self.labels(["LT01"])["scope"], "single-task")
        self.assertEqual(self.labels(["LT01"], smoke=True)["scope"], "smoke")

    def test_anchors_id(self):
        self.assertEqual(S.anchors_id({"name": "season0", "anchors_note": "Native x86_64 … run 40598507498"}),
                         "season0/native/final/run40598507498")
        self.assertEqual(S.anchors_id({"name": "local-LT01", "anchors_from": "season0-public",
                                       "anchors_note": "PROVISIONAL-v6 anchors, Rosetta"}),
                         "season0-public/rosetta/provisional")
        self.assertIn("NOT an official result", S.labels_banner({"official_comparable": False}))


class SmokeVerdict(unittest.TestCase):
    def verdict(self, ok, detail):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            cli._smoke_verdict(ok, detail, "/tmp/x")
        return out.getvalue() + err.getvalue()

    def test_pass(self):
        self.assertIn("PASS", self.verdict(True, ""))

    def test_known_failures_get_a_cause_and_next_step(self):
        for detail, want in (("reset failed: df/save missing", "Dockerfile.game"),
                             ("start forts not built yet: LT01", "setup.sh"),
                             ("container oom", "memory"),
                             ("/x/submission: no Dockerfile", "--harness")):
            v = self.verdict(False, detail)
            self.assertIn("FAIL", v)
            self.assertIn(want, v)


if __name__ == "__main__":
    unittest.main()
