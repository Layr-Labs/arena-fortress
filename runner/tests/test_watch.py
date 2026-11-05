"""Local watch mode (runner/dfbenchlib/watch.py): CLI plumbing, the CI / official refusals and the labels. No Docker.

  python3 -m unittest runner.tests.test_watch -v          # from the repo root
"""
import io, json, os, shutil, sys, tempfile, unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.dirname(HERE)
sys.path[:0] = [RUNNER, HERE]

from dfbenchlib import cli, watch  # noqa: E402
from dfbenchlib import score as S  # noqa: E402
from dfbenchlib.suite import expand, load_suite  # noqa: E402
from test_runner import SUITE, write_game_dir  # noqa: E402


def run_main(argv, env=None):
    """cli.main with every command stubbed out: -> (the parsed args the command got, or the SystemExit code)."""
    got = {}

    def grab(a, argv_):
        got["a"] = a
    stubs = {f: grab for f in ("cmd_local_smoke", "cmd_local_run", "cmd_suite_run")}
    env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_ACTIONS", "DFBENCH_RESULT_KIND")} | (env or {})
    with mock.patch.dict(os.environ, env, clear=True), mock.patch.multiple(cli, **stubs), \
            mock.patch("sys.stderr", new=io.StringIO()):
        try:
            cli.main(argv)
        except SystemExit as e:
            return None, e.code
    return got.get("a"), None


class Flags(unittest.TestCase):
    def test_local_commands_take_watch(self):
        for argv in (["local", "smoke", "--watch"], ["local", "run", "--task", "x.json", "--watch"],
                     ["local", "suite", "--harness", "h", "--watch"]):
            a, code = run_main(argv)
            self.assertIsNone(code, argv)
            self.assertTrue(a.watch, argv)
            self.assertFalse(a.watch_live, argv)

    def test_default_off(self):
        a, _ = run_main(["local", "smoke"])
        self.assertFalse(a.watch)
        self.assertFalse(a.watch_live)

    def test_watch_live_implies_watch(self):
        a, _ = run_main(["local", "smoke", "--watch-live", "--watch-port", "5910"])
        self.assertTrue(a.watch and a.watch_live)
        self.assertEqual(a.watch_port, 5910)

    def test_not_on_official_suite_run(self):
        self.assertEqual(run_main(["suite", "run", "--suite", SUITE, "--watch"])[1], 2)   # no such flag

    def test_refused_in_ci(self):
        for argv in (["local", "smoke", "--watch"], ["local", "smoke", "--watch-live"],
                     ["local", "run", "--task", "x.json", "--watch"]):
            self.assertEqual(run_main(argv, {"GITHUB_ACTIONS": "true"})[1], 2, argv)
        a, code = run_main(["local", "smoke"], {"GITHUB_ACTIONS": "true"})   # without --watch: unchanged
        self.assertIsNone(code)

    def test_refused_for_official_and_fake(self):
        self.assertEqual(run_main(["local", "smoke", "--watch"], {"DFBENCH_RESULT_KIND": "official"})[1], 2)
        self.assertEqual(run_main(["local", "smoke", "--watch", "--stack", "fake"])[1], 2)

    def test_refuse_reason_outside_local(self):
        a = mock.Mock(cmd="suite", watch=True, watch_live=False, stack="real")
        self.assertIn("local", watch.refuse_reason(a, {}))
        a.cmd = "local"
        self.assertIsNone(watch.refuse_reason(a, {}))
        self.assertIn("CI", watch.refuse_reason(a, {"GITHUB_ACTIONS": "1"}))


class Opt(unittest.TestCase):
    """_opt with --watch swaps the game image for the watch image built from the configured one."""

    def _opt(self, argv, env):
        a, _ = run_main(argv)
        with mock.patch.dict(os.environ, env), mock.patch.object(cli, "build_fakes", return_value="fakes:x"), \
                mock.patch.object(cli, "build_harness", return_value=("h:1", "sha256:h")), \
                mock.patch.object(watch, "ensure_image", side_effect=lambda b: f"dfbench-watch:from-{b}") as ei, \
                mock.patch("sys.stderr", new=io.StringIO()):
            return cli._opt(a), ei

    def test_watch_uses_watch_image(self):
        opt, ei = self._opt(["local", "smoke", "--watch"], {"DFBENCH_GAME_IMAGE": "dfbench-df:mine"})
        ei.assert_called_once_with("dfbench-df:mine")
        self.assertEqual(opt["DFBENCH_GAME_IMAGE"], "dfbench-watch:from-dfbench-df:mine")
        self.assertTrue(opt["watch"])
        self.assertEqual(opt["watch_base_image"], "dfbench-df:mine")
        self.assertFalse(opt["watch_live"])

    def test_default_base_is_the_runner_default(self):
        env = {k: v for k, v in os.environ.items() if k != "DFBENCH_GAME_IMAGE"}
        with mock.patch.dict(os.environ, env, clear=True):
            opt, ei = self._opt(["local", "smoke", "--watch"], {})
        ei.assert_called_once_with("yukon-df:s0")

    def test_no_watch_untouched(self):
        opt, ei = self._opt(["local", "smoke"], {"DFBENCH_GAME_IMAGE": "dfbench-df:mine"})
        ei.assert_not_called()
        self.assertEqual(opt["DFBENCH_GAME_IMAGE"], "dfbench-df:mine")
        self.assertNotIn("watch", opt)

    def test_image_tag_follows_base(self):
        self.assertNotEqual(watch.image_tag("sha256:a"), watch.image_tag("sha256:b"))
        self.assertEqual(watch.image_tag("sha256:a"), watch.image_tag("sha256:a"))
        self.assertTrue(watch.image_tag("sha256:a").startswith("dfbench-watch:"))


class Labels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.suite = load_suite(SUITE)
        cls.spec = expand(cls.suite, only={"LT01-0"})[0]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def _run(self, name, meta):
        d = os.path.join(self.tmp, name)
        write_game_dir(d, self.spec, "good")
        json.dump(meta, open(os.path.join(d, "run.json"), "w"))
        return S.score_dir(d, self.suite, write=False)[0]["metrics"]

    def test_watch_run_is_labelled(self):
        m = self._run("watch", {"stack": "mixed", "watch": True, "watch_note": watch.NOTE})
        self.assertIs(m["watch"], True)
        self.assertIs(m["comparable"], False)
        self.assertIs(m["official_comparable"], False)
        self.assertIn("NOT comparable", m["watch_note"])
        self.assertIn("WATCH MODE", S.labels_banner(m))
        if m.get("key"):
            self.assertIn("watch", m["key"])
        for v in m.values():                                # still flat for Yukon
            self.assertNotIsInstance(v, (dict, list))

    def test_normal_run_has_no_watch_fields(self):
        m = self._run("plain", {"stack": "mixed"})
        for k in ("watch", "comparable", "watch_note"):
            self.assertNotIn(k, m)
        self.assertNotIn("WATCH", S.labels_banner(m))

    def test_watch_key(self):
        k = "dfbench/v3|api=v0|dfset=noart:abcd1234|rules=K40"
        self.assertEqual(S.watch_key(k), "dfbench/v3|api=v0|dfset=noart:abcd1234+watch|rules=K40")
        self.assertEqual(S.watch_key(S.watch_key(k)), S.watch_key(k))
        self.assertEqual(S.watch_key("dfbench/v3|suite:ab|keys:6"), "dfbench/v3|suite:ab|keys:6|watch")


if __name__ == "__main__":
    unittest.main()
