"""harnessarena core tests (stdlib, no Docker):  python3 -m unittest discover -s framework/tests -t ."""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from harnessarena import adapter as A, env, episode, suite as SU   # noqa: E402


class EnvNames(unittest.TestCase):
    def test_precedence(self):
        e = {"DFBENCH_SEASON": "s0", "HA_SEASON": "x1"}
        self.assertEqual(env.get("SEASON", environ=e), "x1")
        self.assertEqual(env.get("SEASON", environ={"DFBENCH_SEASON": "s0"}), "s0")
        self.assertEqual(env.get("SEASON", "d", environ={"HA_SEASON": ""}), "d")
        self.assertEqual(env.names("SEASON"), ["HA_SEASON", "DFBENCH_SEASON"])


class SuiteAccessors(unittest.TestCase):
    def test_defaults_and_overrides(self):
        s = {"tasks": [{"id": "A", "stage": 1, "anchor": {"noop": 0, "witness": 1}}, {"id": "B", "stage": 2}]}
        self.assertEqual(SU.weights(s), {"OP1": 0.5, "MY1": 0.3, "labs": 0.2})
        self.assertEqual(SU.confirm_tasks(s), ["MY1", "OP1"])
        self.assertEqual(SU.stage2_tasks(s), ["B"])
        self.assertEqual(SU.anchors(s), {"A": {"noop": 0, "witness": 1}})
        self.assertEqual(SU.environment(s), "dfbench")
        s.update(weights={"main": 1.0}, confirm_tasks=["B"], environment="nethack")
        self.assertEqual((SU.weights(s), SU.confirm_tasks(s), SU.environment(s)), ({"main": 1.0}, ["B"], "nethack"))


class EpisodeManifest(unittest.TestCase):
    def test_validate(self):
        m = episode.from_fields("T1", "i0", 100, "horizon", actions_used=3)
        self.assertEqual(episode.validate(m), [])
        self.assertIn("missing instance_id", episode.validate({"schema": episode.SCHEMA, "task_id": "T1"}))
        self.assertTrue(episode.validate(dict(m, ended_by="exploded")))
        self.assertTrue(episode.validate(dict(m, actions_used=-1)))


class Registry(unittest.TestCase):
    def test_register_and_get(self):
        class Toy(A.Adapter):
            name = "toy-test"
        A.register(Toy())
        self.assertEqual(A.get("toy-test").env_url({}), "http://env:8090")
        self.assertEqual(A.get("toy-test").env_url({"env_url": "http://x:1"}), "http://x:1")
        with self.assertRaises(KeyError):
            A.get("nope")

    def test_df_adapter_registered(self):
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "runner"))
        from dfbenchlib import df_adapter  # noqa: F401
        self.assertEqual(A.get("dfbench").env_url({}), "http://game:8090")


if __name__ == "__main__":
    unittest.main()


class PoolCore(unittest.TestCase):
    def test_selection_rule(self):
        from harnessarena.pool import selection_check
        att = [{"seed": 3, "status": "rejected"}, {"seed": 5, "status": "accepted"}, {"seed": 9, "status": "accepted"}]
        self.assertEqual(selection_check([3, 5, 9, 12], att, 2, [9, 5]), ([5, 9], 1, True))
        self.assertFalse(selection_check([3, 5, 9, 12], att, 2, [5, 12])[2])       # used a non-first seed
        self.assertFalse(selection_check([1, 3, 5, 9], att, 2, [5, 9])[2])         # skipped an untried lower seed

    def test_commitment_is_deterministic_and_salted(self):
        from harnessarena.pool import commitment_of
        pub = {"rules_sha256": {"r": "1"}, "image_digest": "sha256:x", "task_def_sha256": {"T": "2"},
               "spec_sha256": "s", "repo_commit": "c", "seed_mode": "m", "seed_space": [0, 9], "forts": {"T": 1},
               "candidates": {"T": 2}}
        a = commitment_of("s9", "00" * 32, {"T": [2, 1]}, pub)
        self.assertEqual(a, commitment_of("s9", "00" * 32, {"T": [1, 2]}, pub))
        self.assertNotEqual(a, commitment_of("s9", "01" * 32, {"T": [1, 2]}, pub))
