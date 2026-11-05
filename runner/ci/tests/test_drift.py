"""Tests for the drift defences (D26): runner/ci/bin/drift.py (routing fingerprint, in-run drift check) and
runner/ci/bin/paired.py (leader-alongside-challenger confirmation). No network, no Docker.
Run: python3 -m unittest discover -s runner/ci/tests -t .
"""
import json, os, random, shutil, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin"))
import drift, paired  # noqa: E402

GEN = {"data": {"model": "z-ai/glm-5.3-flash-20260826", "provider_name": "Together",
                "upstream_id": "f7b62c6d-aws_ue1",
                "provider_responses": [{"endpoint_id": "1f64afbd-4c77", "id": "f7b62c6d-aws_ue1", "status": 200,
                                        "model_permaslug": "z-ai/glm-5.3-flash-20260826",
                                        "provider_name": "Together"}]}}


def write_games(root, games):
    """games: {game_id: [(request_digest, reasoning_tokens, tool, generation_id)]} -> a run dir like the runner's."""
    for gid, calls in games.items():
        g = os.path.join(root, gid)
        os.makedirs(os.path.join(g, "gateway"), exist_ok=True)
        os.makedirs(os.path.join(g, "game"), exist_ok=True)
        with open(os.path.join(g, "gateway", "usage.jsonl"), "w") as f:
            for i, (d, r, t, gen) in enumerate(calls):
                f.write(json.dumps({"seq": i + 1, "outcome": "ok", "request_digest": d, "reasoning_tokens": r,
                                    "tools_called": [t] if t else [], "generation_id": gen}) + "\n")
        with open(os.path.join(g, "game", "summary.jsonl"), "w") as f:
            f.write(json.dumps({"harness_digest": "sha256:h1"}) + "\n")


class Stats(unittest.TestCase):
    def test_ks(self):
        r = random.Random(3)
        a = [r.gauss(140, 40) for _ in range(300)]
        self.assertEqual(drift.ks_2samp(a, list(a))[1], 1.0)
        self.assertGreater(drift.ks_2samp(a, [r.gauss(140, 40) for _ in range(300)])[1], 0.001)
        self.assertLess(drift.ks_2samp(a, [r.gauss(200, 40) for _ in range(300)])[1], 0.001)

    def test_chi2(self):
        self.assertGreater(drift.chi2_2xk({"x": 50, "y": 50}, {"x": 48, "y": 52}), 0.5)
        self.assertLess(drift.chi2_2xk({"x": 80, "y": 20}, {"x": 40, "y": 60}), 1e-6)
        self.assertIsNone(drift.chi2_2xk({"x": 5}, {"x": 7}))


class Fingerprint(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="drift-")
        write_games(self.d, {f"MY1-{k}": [(f"d{k}", 100, "add_order", f"gen-{k}-{i}") for i in range(4)]
                             for k in range(4)})

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_parse(self):
        p = drift.parse_generation(GEN)
        self.assertEqual((p["snapshot"], p["provider"], p["attempts"], p["region"]),
                         ("z-ai/glm-5.3-flash-20260826", "Together", 1, "aws_ue1"))

    def test_consistent_and_flat(self):
        out = drift.fingerprint(self.d, k=6, key="k", fetch=lambda url, key: GEN)
        self.assertEqual(out["route_samples"], 6)
        self.assertTrue(out["route_consistent"])
        self.assertFalse(out["route_fallbacks"])
        self.assertTrue(all(not isinstance(v, (dict, list)) for v in out.values()))
        ref = {"route": {"route_model_snapshot": "z-ai/glm-5.3-flash-20250101"}}
        self.assertFalse(drift.fingerprint(self.d, k=2, key="k", ref=ref, fetch=lambda u, k: GEN)["route_consistent"])

    def test_fallback_and_soft_failure(self):
        fb = json.loads(json.dumps(GEN))
        fb["data"]["provider_responses"].insert(0, {"provider_name": "Other", "status": 503, "endpoint_id": "x"})
        out = drift.fingerprint(self.d, k=2, key="k", fetch=lambda u, k: fb)
        self.assertTrue(out["route_fallbacks"])
        self.assertFalse(out["route_consistent"])

        def boom(url, key):
            raise OSError("down")
        self.assertTrue(drift.fingerprint(self.d, k=2, key="k", fetch=boom)["route_unknown"])
        self.assertTrue(drift.fingerprint(self.d, k=2, key="", fetch=boom)["route_unknown"])


class Check(unittest.TestCase):
    def run_dir(self, mult, tool="add_order", n_games=40, seed=1):
        r = random.Random(seed)
        d = tempfile.mkdtemp(prefix="drift-")
        write_games(d, {f"OP1-{k}": [(f"first-{k}", int(r.gauss(140, 40) * mult), tool, f"g{k}")] +
                        [(f"later-{k}-{i}-{seed}", int(r.gauss(140, 40) * mult), "advance_days", f"g{k}{i}")
                         for i in range(4)] for k in range(n_games)})
        return d

    def test_flags(self):
        base = self.run_dir(1.0, seed=1)
        try:
            ref = drift.build_reference(base, "s0", "1")
            self.assertEqual(drift.check(base, None)["drift_flag"], "n/a")
            same = self.run_dir(1.0, seed=2)
            big = self.run_dir(1.6, seed=3)
            tool = self.run_dir(1.0, tool="build_farm", seed=4)
            try:
                got = drift.check(same, ref)
                self.assertEqual(got["drift_basis"], "matched:40")
                other = dict(ref, calls=[{**c, "d": "other-" + c["d"]} for c in ref["calls"]],
                             harness_digests=["sha256:another-harness"])
                diff = drift.check(same, other)
                self.assertEqual((diff["drift_basis"], diff["drift_flag"]), ("no-matching-requests", "n/a"))
                self.assertEqual(drift.check(same, None)["drift_basis"], "no-reference")
                self.assertEqual(got["drift_calls"], 40)
                self.assertIn(got["drift_flag"], ("none", "watch"))
                self.assertEqual(drift.check(big, ref)["drift_flag"], "alert")
                self.assertEqual(drift.check(tool, ref)["drift_flag"], "alert")
            finally:
                for x in (same, big, tool):
                    shutil.rmtree(x, ignore_errors=True)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_few_calls_is_na(self):
        a, b = self.run_dir(1.0, n_games=5, seed=1), self.run_dir(1.0, n_games=5, seed=2)
        try:
            # same harness digest: falls back to the first-5-calls basis (25 calls), which is enough
            got = drift.check(b, drift.build_reference(a, "s0", "1"))
            self.assertEqual(got["drift_basis"], "same-harness")
            self.assertNotEqual(got["drift_flag"], "n/a")
        finally:
            shutil.rmtree(a, ignore_errors=True); shutil.rmtree(b, ignore_errors=True)

    def test_evidence_merges_and_writes_reference_once(self):
        d = self.run_dir(1.0)
        sc = os.path.join(d, "scored.json")
        json.dump({"score": 50.0, "metrics": {"stage": 2}}, open(sc, "w"))
        saved = {}

        def load(name):
            return (saved.get(name), "sha") if name in saved else (None, None)

        def save(name, obj, sha, msg):
            if name in saved and sha is None:
                return False
            saved[name] = obj
            return True
        try:
            drift.evidence(d, sc, "101", write_reference=True, store=(load, save))
            self.assertIn("drift_reference.json", saved)
            first = saved["drift_reference.json"]["source_run"]
            drift.evidence(d, sc, "102", write_reference=True, store=(load, save))
            self.assertEqual(saved["drift_reference.json"]["source_run"], first)        # first write wins
            m = json.load(open(sc))["metrics"]
            self.assertEqual(m["stage"], 2)
            self.assertIn("drift_flag", m)
            self.assertTrue(m["route_unknown"])                                         # no key in tests
            self.assertTrue(all(not isinstance(v, (dict, list)) for v in m.values()))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class RescoreDrift(unittest.TestCase):
    """rescore.yml's same-harness check: each harness against its own first scored run (drift_refs/<id>.json)."""

    def store(self):
        saved = {}

        def load(name):
            return (saved.get(name), "sha") if name in saved else (None, None)

        def save(name, obj, sha, msg):
            if name in saved and sha is None:
                return False
            saved[name] = obj
            return True
        return saved, (load, save)

    def test_own_reference_then_same_harness_check(self):
        mk = Check().run_dir
        first, again = mk(1.0, seed=1), mk(1.0, seed=2)
        try:
            saved, st = self.store()
            sc = os.path.join(first, "scored.json")
            json.dump({"score": 80.0, "metrics": {"stage": 2}}, open(sc, "w"))
            drift.evidence(first, sc, "200", store=st, submission="abc")        # its first scoring run
            self.assertIn("drift_refs/abc.json", saved)
            self.assertNotIn("drift_reference.json", saved)                     # only the baseline writes that
            got = drift.rescore(again, "abc", "201", store=st)
            self.assertIn(got["drift_basis"], ("same-harness", "matched:40"))
            self.assertIn(got["drift_flag"], ("none", "watch"))
            self.assertEqual(drift.own_ref_name("baseline"), "drift_reference.json")
        finally:
            shutil.rmtree(first, ignore_errors=True); shutil.rmtree(again, ignore_errors=True)

    def test_rescore_without_reference_writes_it(self):
        d = Check().run_dir(1.0, seed=3)
        try:
            saved, st = self.store()
            got = drift.rescore(d, "xyz", "300", store=st)
            self.assertEqual((got["drift_flag"], got["drift_basis"]), ("n/a", "no-reference"))
            self.assertTrue(got["drift_reference_written"])
            self.assertIn("drift_refs/xyz.json", saved)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_ratio_band_needs_a_real_median(self):
        # mmurrs's first weekly re-scores (runs/s0-rescore-noise-2026-10-29): early-call medians 64 -> 90, x1.4,
        # KS p 0.16-0.76: not a drift signal
        self.assertFalse(drift.ratio_out(90, 64, 90 / 64))
        self.assertFalse(drift.ratio_out(115, 100, 1.15))                       # inside the band
        self.assertFalse(drift.ratio_out(108, 95, 108 / 95))                    # differ by < 20 tokens
        self.assertTrue(drift.ratio_out(200, 140, 200 / 140))                   # x1.43 on real medians
        self.assertTrue(drift.ratio_out(100, 160, 100 / 160))


SUITE = {"tasks": [{"id": "MY1", "kind": "outcome", "family": "MY1", "n": 2},
                   {"id": "OP1", "kind": "outcome", "family": "OP1", "n": 2}],
         "weights": {"OP1": 0.5, "MY1": 0.3, "labs": 0.2}, "confirm_tasks": ["MY1", "OP1"],
         "bootstrap": {"resamples": 2000, "seed": 0}}


def detail(values, ks):
    return {"games": [{"task": t, "k": k, "status": "ok", "kind": "outcome", "O": v}
                      for t, vs in values.items() for k, v in zip(ks, vs)]}


class Paired(unittest.TestCase):
    def test_clear_win_passes(self):
        ks = list(range(2, 10))
        c = detail({"MY1": [70 + i for i in range(8)], "OP1": [60 + i for i in range(8)]}, ks)
        l = detail({"MY1": [50 + i for i in range(8)], "OP1": [40 + i for i in range(8)]}, ks)
        d = paired.paired_diff(paired.pairs(c, l, ["MY1", "OP1"]), SUITE)
        self.assertEqual(d["n"], 16)
        self.assertAlmostEqual(d["point"], 20.0)
        self.assertGreater(d["lb"], 0)
        s = {"score": 60.0, "metrics": {}}
        self.assertEqual(paired.decide(s, d), "passed")
        self.assertEqual(s["score"], 60.0)

    def test_tie_fails_and_keeps_the_pooled_value(self):
        ks = list(range(2, 10))
        r = random.Random(5)
        vals = {"MY1": [r.uniform(30, 90) for _ in ks], "OP1": [r.uniform(20, 80) for _ in ks]}
        lead = {t: [v + r.uniform(-15, 15) for v in vs] for t, vs in vals.items()}
        d = paired.paired_diff(paired.pairs(detail(vals, ks), detail(lead, ks), ["MY1", "OP1"]), SUITE)
        self.assertLessEqual(d["lb"], 0)
        s = {"score": 61.5, "metrics": {"confirmation": "passed"}}
        self.assertEqual(paired.decide(s, d), "failed")
        self.assertEqual((s["score"], s["partial"]), (0, True))
        self.assertEqual(s["metrics"]["confirmation"], "failed_paired")
        self.assertEqual(s["metrics"]["score_pooled"], 61.5)

    def test_pairs_only_on_shared_games_and_tasks(self):
        c = detail({"MY1": [1, 2, 3], "OP1": [1, 2, 3]}, [0, 1, 2])
        l = detail({"MY1": [1, 2], "OP1": [9, 9]}, [1, 2])
        p = paired.pairs(c, l, ["MY1"])
        self.assertEqual([(a["k"], b["k"]) for a, b in p["MY1"]], [(1, 1), (2, 2)])
        self.assertNotIn("OP1", p)

    def test_skips(self):
        empty = paired.paired_diff({}, SUITE)
        s = {"score": 60.0, "metrics": {}}
        self.assertEqual(paired.decide(s, empty), "skipped")
        self.assertEqual(s["score"], 60.0)
        d = {"point": -5.0, "lb": -9.0, "leader_point": 70, "challenger_point": 65, "n": 16}
        for kw in ({"on": False}, {"verified": "false"}):
            s = {"score": 60.0, "metrics": {}}
            self.assertEqual(paired.decide(s, d, **kw), "skipped")
            self.assertEqual(s["score"], 60.0)
            self.assertEqual(s["metrics"]["paired_diff_lb"], -9.0)


if __name__ == "__main__":
    unittest.main()
