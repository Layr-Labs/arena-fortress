"""reset_hint: the reason a reset failed, from the two usual causes (gameapi/server/__main__.py)."""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
from gameapi.server import __main__ as M  # noqa: E402


class ResetHint(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.root, M.ROOT = M.ROOT, self.d

    def tearDown(self):
        M.ROOT = self.root

    def test_missing_df_save(self):
        self.assertIn("df/save is missing", M.reset_hint("RuntimeError: reset failed: FAIL: copy x", {}))

    def test_missing_fort(self):
        os.makedirs(os.path.join(self.d, "df", "save"))
        self.assertIn("not found", M.reset_hint("reset failed: FAIL", {"snapshot": "scenarios/snapshots/nope"}))

    def test_other_errors_and_healthy_setup(self):
        os.makedirs(os.path.join(self.d, "df", "save"))
        self.assertIsNone(M.reset_hint("scenario setup failed", {}))
        self.assertIsNone(M.reset_hint("reset failed: FAIL", {"snapshot": self.d}))


if __name__ == "__main__":
    unittest.main()
