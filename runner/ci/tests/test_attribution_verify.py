"""Attribution judged with the formal list hidden, then verified after publication; ledger release. No network."""
import argparse, datetime, json, os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin"))
import attribution_verify as AV, emit_score, ledger, prior  # noqa: E402
import tempfile  # noqa: E402

T = datetime.datetime(2026, 10, 29, 12, tzinfo=datetime.timezone.utc)


def ns(**kw):
    base = dict(verified=None, basis=None, base_producers="", suspects="", result=None, reason=None)
    base.update(kw)
    return argparse.Namespace(**base)


def entry(sid, status="scored", user="u"):
    return {"submission": sid, "user": user, "status": status, "week": "2026-W44", "updated": T.isoformat()}


class LedgerTest(unittest.TestCase):
    def test_release_makes_resubmission_possible(self):
        led = {"entries": [entry("held", "rejected")], "users": {}}
        r = ledger.release_decision(led, argparse.Namespace(submission="held", reason="judge bug"), T)
        self.assertTrue(r["ok"])
        e = led["entries"][0]
        self.assertEqual(e["status"], "cancelled")
        self.assertEqual(e["released"]["from"], "rejected")
        self.assertNotIn(e["status"], ledger.SCORED)
        self.assertNotIn(e["status"], ledger.COUNTED)

    def test_attribution_record_and_result(self):
        led = {"entries": [entry("s1")], "users": {}}
        ledger.attribution_decision(led, ns(submission="s1", verified="false", basis="note+code",
                                            base_producers="lead", suspects="x,y"), T)
        rec = led["entries"][0]["attribution"]
        self.assertEqual((rec["verified"], rec["base_producers"], rec["suspects"]), (False, ["lead"], ["x", "y"]))
        ledger.attribution_decision(led, ns(submission="s1", result="verified_ok", reason="ok"), T)
        self.assertEqual(rec["checked"]["result"], "verified_ok")


class VerifyTest(unittest.TestCase):
    def led(self):
        e = entry("s1")
        e["attribution"] = {"verified": False, "basis": "note+code", "base_producers": ["lead"], "suspects": [],
                            "judged": T.isoformat()}
        done = entry("s2"); done["attribution"] = dict(e["attribution"], checked={"result": "verified_ok"})
        ok = entry("s3"); ok["attribution"] = {"verified": True, "basis": "yukon", "judged": T.isoformat()}
        return {"entries": [e, done, ok]}

    def test_pending_only_unverified_unchecked(self):
        self.assertEqual([e["submission"] for e in AV.pending(self.led(), 14, 20, T)], ["s1"])
        self.assertEqual(AV.pending(self.led(), 14, 20, T + datetime.timedelta(days=30)), [])

    def test_mmurrs_case_verifies_ok(self):
        e = self.led()["entries"][0]
        att = {"declaration": "provided", "dependencies": [{"submissionId": "lead", "rationale": "base"}]}
        self.assertEqual(AV.judge_entry(e, att)[0], "verified_ok")

    def test_missing_base_is_flagged(self):
        e = self.led()["entries"][0]
        r, why = AV.judge_entry(e, {"declaration": "none", "dependencies": []})
        self.assertEqual(r, "verify_flagged")
        self.assertIn("lead", why)


class EmitTest(unittest.TestCase):
    def test_attribution_metrics_from_dossier(self):
        out = emit_score.emit({"score": 80.0, "metrics": {"stage": 2}},
                              dossier={"verdict": "pass", "attribution": {"verified": False, "basis": "note+code"}})
        self.assertEqual(out["score"], 80.0)
        self.assertEqual((out["metrics"]["attribution_verified"], out["metrics"]["attribution_basis"]),
                         (False, "note+code"))


class PriorDepsTest(unittest.TestCase):
    def test_in_tree_used_only_while_hidden(self):
        with tempfile.TemporaryDirectory() as d:
            who, repo = os.path.join(d, "who"), os.path.join(d, "repo")
            os.makedirs(who); os.makedirs(os.path.join(repo, "submission"))
            json.dump({"declaration": "unavailable", "dependencies": []}, open(os.path.join(who, "deps.json"), "w"))
            json.dump([{"submissionId": "lead"}], open(os.path.join(repo, "submission", "dependencies.json"), "w"))
            self.assertEqual(prior.declared_dependencies({}, who, repo), [{"submissionId": "lead"}])
            json.dump({"declaration": "provided", "dependencies": [{"submissionId": "x"}]},
                      open(os.path.join(who, "deps.json"), "w"))
            self.assertEqual(prior.declared_dependencies({}, who, repo), [{"submissionId": "x"}])
