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

    def test_select_single_run_contenders_first(self):
        def ent(sid, ub, runs, status="contender", lb=80.0):
            return {"submission": sid, "status": status, "pooled": {"ub95": ub, "lb95": lb, "runs": runs}}
        # the dev board before the 2026-11-04 re-score: leader lb95 86.45; five single-run contenders reached it
        st = {"leader": "8ead", "entries": {e["submission"]: e for e in [
            ent("8ead", 88.06, 1, "leader", 86.45), ent("8f65", 87.94, 1), ent("13c0", 87.84, 1),
            ent("5041", 87.76, 1), ent("6b86", 87.73, 1), ent("33c7", 87.72, 1), ent("c447", 86.42, 3)]}}
        self.assertEqual(band.select(st, k=4), ["8ead", "8f65", "13c0", "5041", "6b86", "33c7"])   # 33c7 was missed
        self.assertEqual(band.select(st, k=2, cap=2), ["8ead", "8f65", "13c0"])                   # the cap binds
        self.assertEqual(band.select(st, k=4, cap=2), ["8ead", "8f65", "13c0", "5041", "6b86"])   # k still fills
        self.assertEqual(band.select(st, k=7), ["8ead", "8f65", "13c0", "5041", "6b86", "33c7", "c447"])
        # after the re-score everyone has two runs: back to the top K by ub95
        for e in st["entries"].values():
            e["pooled"]["runs"] = 2
        self.assertEqual(band.select(st, k=4), ["8ead", "8f65", "13c0", "5041", "6b86"])
        # a single-run contender below the leader's lb95 isn't forced in, but can still fill a slot
        st["entries"]["new1"] = ent("new1", 86.0, 1)
        st["entries"]["new2"] = ent("new2", 87.0, 1)
        self.assertEqual(band.select(st, k=2), ["8ead", "new2", "8f65"])
        self.assertEqual(band.select(st, k=0, cap=0), ["8ead"])
        # dropped entries are never picked
        st["entries"]["new2"]["status"] = "dropped"
        self.assertEqual(band.select(st, k=1), ["8ead", "8f65"])

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
        # rescore.yml's drift and route metrics ride on the run record (flat values only)
        d = {"drift_flag": "none", "drift_basis": "same-harness", "route_consistent": True, "nested": {"x": 1}}
        band.record_decision(st, args(submission="sub-a", source="rescore", drift=d), shift(games(60), 8), SUITE)
        last = st["entries"]["sub-a"]["runs"][-1]
        self.assertEqual(last["drift"], {"drift_flag": "none", "drift_basis": "same-harness", "route_consistent": True})
        self.assertEqual(st["entries"]["sub-a"]["drift_last"]["drift_basis"], "same-harness")

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


class SuiteDefaultsTest(unittest.TestCase):
    """The DF defaults that used to be hardcoded (weights in score.py/band.py, the MY1/OP1 confirmation tasks in
    score.yml/gate.py) come from the suite files; the season-0 suites carry the same values, so nothing changes."""

    def test_season0_suites_carry_the_old_defaults(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        sys.path.insert(0, os.path.join(root, "framework"))
        from harnessarena import suite as SU
        for f in ("season0.json", "season0-public.json", "season0-int.json"):
            s = json.load(open(os.path.join(root, "runner", "suites", f)))
            self.assertEqual(SU.weights(s), SU.LEGACY_WEIGHTS, f)
            self.assertEqual(SU.confirm_tasks(s), SU.LEGACY_CONFIRM_TASKS, f)


class LeaderElect(unittest.TestCase):
    """band.py tag runs before Yukon reads the score: a submission Yukon will promote is tagged leader-elect, not
    contender (the reset board's first promotion, 7df400f3, was tagged contender), and becomes the leader once the
    next run sees Yukon's incumbent."""

    def promoted_score(self, lb, confirmation="passed"):
        s = score_with(lb)
        s["metrics"]["confirmation"] = confirmation
        return s

    def test_elect_then_leader(self):
        st = band.empty()
        band.tag_decision(st, args(kind="baseline", submission="baseline"), score_with(55), games(60), SUITE)
        g = shift(games(60), 10)
        r = band.tag_decision(st, args(submission="sub-a", leader_score="55", bips=250), self.promoted_score(70), g, SUITE)
        self.assertEqual(r["band"], "leader-elect", r)
        self.assertEqual(st["entries"]["sub-a"]["status"], "leader-elect")
        # another submission scored before Yukon promotes: sub-a keeps its tag
        band.tag_decision(st, args(submission="sub-b", leader_score="55", bips=250), score_with(54), games(60), SUITE)
        self.assertEqual(st["entries"]["sub-a"]["status"], "leader-elect")
        # the next run sees Yukon's incumbent = sub-a
        band.tag_decision(st, args(submission="sub-c", leader="sub-a", leader_score="70", bips=250), score_with(50),
                          games(55), SUITE)
        self.assertEqual(st["entries"]["sub-a"]["status"], "leader")
        self.assertNotEqual(st["entries"]["baseline"]["status"], "leader")

    def test_not_elect_when_held_unconfirmed_or_not_improving(self):
        st = band.empty()
        band.tag_decision(st, args(kind="baseline", submission="baseline"), score_with(55), games(60), SUITE)
        g = shift(games(60), 10)
        for sc, why in ((self.promoted_score(70, "failed_paired"), "paired"),
                        (score_with(70, verdict="hold"), "hold"),
                        (self.promoted_score(55.5), "under the bips margin")):
            r = band.tag_decision(st, args(submission="x-" + why, leader_score="55", bips=250), sc, g, SUITE)
            self.assertNotEqual(r["band"], "leader-elect", why)
        self.assertNotEqual(band.tag_decision(st, args(submission="y"), self.promoted_score(70), g, SUITE)["band"],
                            "leader-elect")      # incumbent unknown: no guess

    def test_stale_elect_is_rebanded(self):
        st = band.empty()
        band.tag_decision(st, args(kind="baseline", submission="baseline"), score_with(55), games(60), SUITE)
        g = shift(games(60), 10)
        band.tag_decision(st, args(submission="sub-a", leader_score="55", bips=250), self.promoted_score(70), g, SUITE)
        # Yukon promoted someone else instead: sub-a is banded against that leader
        band.tag_decision(st, args(submission="sub-z", kind="submission", leader="sub-z", leader_score="80"),
                          score_with(80), shift(games(60), 20), SUITE)
        self.assertIn(st["entries"]["sub-a"]["status"], ("contender", "dropped"))
