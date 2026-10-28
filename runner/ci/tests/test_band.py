"""Tests for the noise-handling package: confirmation decisions (gate.py, collect.py pool-verdict), the contender
band and re-score selection (band.py), and game ids past a task's n (dfbenchlib.suite). No network, no Docker.
Run: python3 -m unittest discover -s runner/ci/tests -t .
"""
import argparse, json, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CI = os.path.dirname(HERE)
RUNNER = os.path.dirname(CI)
sys.path[:0] = [os.path.join(CI, "bin"), RUNNER]
import band, collect, gate  # noqa: E402
from dfbenchlib import score as S  # noqa: E402
from dfbenchlib.suite import expand, load_suite  # noqa: E402

SUITE = load_suite(os.path.join(RUNNER, "suites", "season0.json"))
SUITE["bootstrap"]["resamples"] = 2000


def games(level, n=8, spread=6.0):
    """Per-task game values for a harness of a given strength (deterministic spread)."""
    out = {}
    for t in SUITE["tasks"]:
        tid, kind = t["id"], t.get("kind", "outcome")
        vals = []
        for k in range(n):
            d = (k - (n - 1) / 2) / ((n - 1) / 2)          # -1 .. 1
            if kind == "lab":
                vals.append({"kind": "lab", "O": None, "partial": max(0.0, min(1.0, level / 100 + 0.1 * d))})
            else:
                vals.append({"kind": "outcome", "O": max(0.0, level + spread * d), "partial": None})
        out[tid] = vals
    return out


def shift(g, d):
    """The same games with every outcome O moved by d points (labs unchanged)."""
    return {t: [{**v, "O": None if v["O"] is None else max(0.0, v["O"] + d)} for v in vs] for t, vs in g.items()}


def detail_of(g):
    return {"games": [{"task": tid, "status": "ok", **v} for tid, vs in g.items() for v in vs]}


def args(**kw):
    base = dict(kind="submission", submission="sub-a", solver="alice", tree="t1", branch=None, run="1",
                source="score", leader=None, leader_point=None, band_pts=3.8)
    base.update(kw)
    return argparse.Namespace(**base)


def score_with(lb, stage=2, verdict="pass"):
    return {"score": lb, "metrics": {"stage": stage, "lb95": lb, "judge_verdict": verdict}}


class GameIdsPastN(unittest.TestCase):
    def test_second_batch_ids_share_forts(self):
        sp = expand(SUITE, only={"MY1-8", "MY1-15", "OP1-11"})
        self.assertEqual([(s["game_id"], s["k"]) for s in sp], [("MY1-8", 8), ("MY1-15", 15), ("OP1-11", 11)])
        self.assertEqual(len(expand(SUITE)), sum(t.get("n", 8) for t in SUITE["tasks"]))   # unchanged otherwise
        self.assertEqual(len(expand(SUITE, only={"MY1"})), 8)


class Confirmation(unittest.TestCase):
    PLAN1 = {"include": [{"job": "j00-MY1-0", "games": "MY1-0", "timeout_min": 60, "play_timeout_min": 40},
                         {"job": "j01-LT01-0", "games": "LT01-0", "timeout_min": 30}]}
    PLAN2 = {"include": [{"job": "j00-OP1-0", "games": "OP1-0", "timeout_min": 120, "play_timeout_min": 100}]}
    N = {t["id"]: t.get("n", 8) for t in SUITE["tasks"]}

    def test_yukon_rule(self):
        self.assertAlmostEqual(gate.improvement_bips(61.5, 60.0), 250.0)
        self.assertTrue(gate.would_promote(61.5, 60.0, 250)[0])
        self.assertFalse(gate.would_promote(61.49, 60.0, 250)[0])
        self.assertFalse(gate.would_promote(60.0, 60.0, 0)[0])             # equal never promotes
        self.assertTrue(gate.would_promote(60.01, 60.0, 0)[0])
        self.assertTrue(gate.would_promote(10, None, 250)[0])               # no incumbent known: fail safe

    def test_decisions(self):
        c = lambda sc, **kw: gate.confirm(sc, [self.PLAN1, self.PLAN2], self.N, ["MY1", "OP1"], **kw)
        go, why, mx = c(score_with(62), leader_score=60, bips=250)
        self.assertTrue(go, why)
        self.assertEqual([j["games"] for j in mx["include"]], ["MY1-8", "OP1-8"])   # labs never re-played
        self.assertEqual(mx["include"][1]["play_timeout_min"], 100)
        self.assertFalse(c(score_with(61), leader_score=60, bips=250)[0])
        self.assertFalse(c(score_with(0, stage=1), leader_score=60, bips=250)[0])
        self.assertFalse(c(score_with(70), leader_score=60, bips=250, off=True)[0])
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "MY1-9"))
            go, why, _ = c(score_with(70), leader_score=60, bips=250, games_dir=d)
            self.assertFalse(go)
            self.assertIn("already pooled", why)

    def test_judge_follows_yukon_rule(self):
        self.assertFalse(gate.judge_needed(score_with(61), 60, bips=250)[0])
        self.assertTrue(gate.judge_needed(score_with(62), 60, bips=250)[0])

    def test_pool_verdict(self):
        with tempfile.TemporaryDirectory() as d:
            first, pooled = os.path.join(d, "f.json"), os.path.join(d, "p.json")
            json.dump({"score": 63.0, "metrics": {"lb95": 63.0}}, open(first, "w"))
            for lb, want in ((62.0, "passed"), (61.0, "failed")):
                json.dump({"score": lb, "metrics": {"lb95": lb, "infra_excluded": 0}}, open(pooled, "w"))
                collect.pool_verdict(pooled, first, "60", "250", "2")
                m = json.load(open(pooled))["metrics"]
                self.assertEqual((m["confirmation"], m["score_first_batch"]), (want, 63.0))
                self.assertEqual(json.load(open(pooled))["score"], lb)       # the pooled bound is always the score


class Band(unittest.TestCase):
    def test_pooled_matches_scorer_on_concatenated_games(self):
        a, b = games(60), games(64)
        st = band.pooled([{"games": a}, {"games": b}], SUITE)
        both = {t: a[t] + b[t] for t in a}
        tasks, w, anc = band.suite_parts(SUITE)
        self.assertAlmostEqual(st["point"], round(S.suite_value(both, tasks, w, anc)[0], 2))
        self.assertEqual((st["runs"], st["games"]), (2, 96))
        self.assertLess(st["lb95"], st["point"])

    def test_band_of(self):
        self.assertEqual(band.band_of({"lb95": 58}, 60, 3.8), ("contender", -2))
        self.assertEqual(band.band_of({"lb95": 55}, 60, 3.8), ("none", -5))
        self.assertEqual(band.band_of({"lb95": 70}, 60, 3.8, valid=False)[0], "none")

    def test_flow_baseline_contenders_rescore_select(self):
        st = band.empty()
        r = band.tag_decision(st, args(kind="baseline", submission="baseline"), score_with(55), games(60), SUITE)
        self.assertEqual(r["band"], "leader")
        # a submission just under the leader is a contender and is stored
        g = shift(games(60), -1)
        lb = band.pooled([{"games": g}], SUITE)["lb95"]
        r = band.tag_decision(st, args(submission="sub-a"), score_with(lb), g, SUITE)
        self.assertEqual(r["band"], "contender", r)
        self.assertIn("sub-a", st["entries"])
        # far below: not stored
        r = band.tag_decision(st, args(submission="sub-b"), score_with(1), games(20), SUITE)
        self.assertEqual(r["band"], "none")
        self.assertTrue(r.get("_nowrite"))
        self.assertNotIn("sub-b", st["entries"])
        # judge fail or hold: never a contender
        r = band.tag_decision(st, args(submission="sub-c"), score_with(lb, verdict="hold"), shift(games(60), 5), SUITE)
        self.assertEqual(r["band"], "none")
        # re-scores: sub-a strong, the leader weak -> sub-a leads on pooled games
        band.record_decision(st, args(submission="sub-a", source="rescore"), shift(games(60), 8), SUITE)
        band.record_decision(st, args(submission="baseline", source="rescore"), shift(games(60), -6), SUITE)
        self.assertTrue(st["entries"]["sub-a"]["leading_on_pooled"])
        self.assertEqual(band.select(st, k=4), ["baseline", "sub-a"])
        # the leader changes (Yukon promoted sub-a): the old leader is banded like everyone else
        band.record_decision(st, args(submission="sub-a", leader="sub-a"), shift(games(60), 8), SUITE)
        self.assertEqual(st["entries"]["sub-a"]["status"], "leader")
        self.assertIn(st["entries"]["baseline"]["status"], ("contender", "dropped"))

    def test_publish_is_aggregates_only(self):
        st = band.empty()
        band.tag_decision(st, args(kind="baseline", submission="baseline"), score_with(55), games(60), SUITE)
        band.tag_decision(st, args(submission="sub-a", branch="submissions/sub-a"), score_with(56), shift(games(60), -1), SUITE)
        md = band.publish(st, "Layr-Labs/dfbench-challenge", "s0")
        self.assertIn("leader", md)
        self.assertIn("head%3Asubmissions/sub-a", md)
        self.assertNotIn("partial", md)
        self.assertNotIn("MY1-", md)


if __name__ == "__main__":
    unittest.main()
