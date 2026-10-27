"""Tests for runner/ci/bin/anchors.py and testers.py: no Docker, no network.
Run: python3 -m unittest discover -s runner/ci/tests -t .
"""
import json, os, re, sys, tarfile, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin"))
import anchors, testers, tier  # noqa: E402


class Plan(unittest.TestCase):
    def test_counts_and_shape(self):
        inc = anchors.plan(8)["include"]
        by = {}
        for e in inc:
            by[(e["task"], e["arm"])] = by.get((e["task"], e["arm"]), 0) + 1
        for t in ("LT01", "LT02", "LT03", "LT08"):
            self.assertEqual(by[(t, "noop")], 8); self.assertEqual(by[(t, "witness")], 8)
        for t in ("MY1", "OP1"):
            self.assertEqual(by[(t, "noop")], 8)
            self.assertEqual(by[(t, "automation")], 4); self.assertEqual(by[(t, "scripted")], 4)
        self.assertEqual(len(inc), 4 * 16 + 2 * 16)
        self.assertEqual(len({e["job"] for e in inc}), len(inc))           # unique job ids
        self.assertTrue(all(e["moods"] == (e["task"] == "LT03") for e in inc))
        self.assertTrue(all(e["entry"] == ("bench/labrun.py" if e["task"].startswith("LT") else "smoke.py") for e in inc))

    def test_only(self):
        inc = anchors.plan(2, {"LT01"})["include"]
        self.assertEqual({e["task"] for e in inc}, {"LT01"}); self.assertEqual(len(inc), 4)
        with self.assertRaises(SystemExit):
            anchors.main(["plan", "--only", "LT99"])


class Aggregate(unittest.TestCase):
    def setUp(self):
        from bench import outcomes, predicates
        self.o, self.p = outcomes, predicates
        self.saved = (predicates.score, outcomes.discover, outcomes.for_run)
        predicates.score = lambda task, ds: {"noop": [{"partial": 0.0, "pass": False}] * len(ds),
                                             "witness": [{"partial": 0.9, "pass": True}, {"partial": 0.8, "pass": False}]}
        outcomes.discover = lambda ds: {("b", "my1", "noop"): [({"arm": "noop", "k": 0}, "d0"), ({"arm": "noop", "k": 1}, "d1")],
                                        ("b", "my1", "automation"): [({"arm": "automation", "k": 0}, "d2")],
                                        ("b", "my1", "scripted"): [({"arm": "scripted", "k": 0}, "d3")]}
        vals = {"d0": 10.0, "d1": 20.0, "d2": 70.0, "d3": 60.0}
        outcomes.for_run = lambda d, r: {"outcome": vals[d]}
        self.tmp = tempfile.mkdtemp()
        self.dirs = []
        for name in ("LT02-noop-0", "LT02-witness-0", "MY1-noop-0"):
            os.makedirs(os.path.join(self.tmp, name)); self.dirs.append(os.path.join(self.tmp, name))

    def tearDown(self):
        self.p.score, self.o.discover, self.o.for_run = self.saved

    def test_aggregates_only(self):
        suite = os.path.join(self.tmp, "suite.json")
        json.dump({"tasks": [{"id": "LT02", "anchor": {"noop": 0.0, "witness": 0.9126}}]}, open(suite, "w"))
        r = anchors.aggregate(self.dirs, suite)
        self.assertEqual(r["tasks"]["LT02"]["witness"], {"n": 2, "p_mean": 0.85, "pass": 1})
        self.assertEqual(r["tasks"]["MY1"]["noop"]["O_mean"], 15.0)
        self.assertEqual(r["tasks"]["MY1"]["references"], {"n": 2, "O_mean": 65.0, "O_min": 60.0})
        self.assertEqual(r["delta_vs_suite"]["LT02"]["witness"]["delta"], round(0.85 - 0.9126, 4))
        text = json.dumps(r)
        for leak in ("d0", "LT02-noop-0", self.tmp):                # no run dir, fort or per-game id in the output
            self.assertNotIn(leak, text)


class Kit(unittest.TestCase):
    def test_refuses_export_stub_and_packs_research(self):
        tmp = tempfile.mkdtemp()
        open(os.path.join(tmp, "policies.py"), "w").write(
            "# Withheld from the public release while a season is running\nWITNESSES = {}\n")
        with self.assertRaises(SystemExit):
            anchors.kit(os.path.join(tmp, "k.tgz"), root=tmp)
        open(os.path.join(tmp, "policies.py"), "w").write("WITNESSES = {'LT01': object}\n")
        out = anchors.kit(os.path.join(tmp, "k.tgz"), root=tmp)
        self.assertEqual(tarfile.open(out).getnames(), ["policies.py"])


class Testers(unittest.TestCase):
    def test_add_keeps_others_and_tier_reads_it(self):
        t, o = testers.add({"new": {"weekly": 3}}, {"carol": "established"}, ["alice", "bob"], weekly=12)
        self.assertEqual(t["new"], {"weekly": 3})
        self.assertEqual(t["tester"], {"in_flight": 2, "weekly": 12, "suite": "full"})
        self.assertEqual(o, {"carol": "established", "alice": "tester", "bob": "tester"})
        cfg = tier.tiers_config({"DFBENCH_TIERS": json.dumps(t)})
        self.assertEqual(tier.decide("alice", {}, {"created_at": "2026-10-20T00:00:00Z"}, "b", cfg, o)[0], "tester")
        self.assertEqual(cfg["tester"]["suite"], "full")

    def test_remove_and_bad_logins(self):
        self.assertEqual(testers.remove({"a": "tester", "b": "tester"}, ["a"]), {"b": "tester"})
        with self.assertRaises(SystemExit):
            testers.users("ok,-bad,also bad")

    def test_cli_prints_without_repo(self):
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            testers.main(["add", "alice", "--overrides", '{"x":"new"}'])
        out = json.loads(buf.getvalue())
        self.assertEqual(out["DFBENCH_TIER_OVERRIDES"], {"x": "new", "alice": "tester"})


if __name__ == "__main__":
    unittest.main()


class WorkflowPermissionsTest(unittest.TestCase):
    """Every job that calls play.yml must grant what play.yml asks for (packages: read), or GitHub refuses to
    start the run (startup_failure, no jobs; actionlint doesn't check it)."""

    def test_play_callers_grant_packages_read(self):
        ci = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for wf in ("score.yml", "anchors.yml"):
            text = open(os.path.join(ci, wf)).read()
            blocks = re.split(r"\n(?=  [A-Za-z0-9_-]+:\n)", text.split("\njobs:\n", 1)[1])
            callers = [b for b in blocks if "uses: ./.github/workflows/play.yml" in b]
            for b in callers:
                with self.subTest(workflow=wf, job=b.split(":", 1)[0].strip()):
                    self.assertRegex(b, r"permissions: \{[^}]*packages: read")
        self.assertIn("packages: read", open(os.path.join(ci, "play.yml")).read())
