"""The dispatcher: MY1 (an open task shorter than a year) runs ours/, everything else main's controller, and an
unreadable task falls back to main's."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dispatch import __main__ as D  # noqa: E402

OP1 = {"name": "op1-start-year-s0", "days": 336, "goal": "Run the fortress for 336 days.", "hands_off": None}
MY1 = {"name": "my1-handover-lean-s0", "days": 216, "goal": "Run the fortress for 216 days.", "hands_off": None}
LT01 = {"name": "lt01-drought-s0", "days": 60, "goal": "From day 39 you can't act for 21 days.",
        "hands_off": {"from_day": 39, "days": 21}}


def env(task):
    return json.dumps({"schema": "dfbench-task/1", "game_url": "http://game:8090", "task": task})


class Dispatch(unittest.TestCase):
    def run_main(self, value):
        calls = {}
        with mock.patch.dict(os.environ, {"DFBENCH_TASK": value}), \
                mock.patch.object(D.os, "chdir", lambda p: calls.setdefault("cwd", p)), \
                mock.patch.object(D.os, "execve", lambda exe, argv, e: calls.update(argv=argv, env=e)), \
                redirect_stdout(io.StringIO()) as out:
            D.main()
        lines = [json.loads(x) for x in out.getvalue().splitlines()]
        return calls, lines

    def test_routes(self):
        self.assertFalse(D.ours(OP1))
        self.assertTrue(D.ours(MY1))
        self.assertFalse(D.ours(LT01))
        self.assertFalse(D.ours({"days": True}))
        self.assertFalse(D.ours({}))

    def test_my1_runs_ours_with_the_shared_client_on_the_path(self):
        calls, lines = self.run_main(env(MY1))
        self.assertEqual(calls["cwd"], os.path.join(D.HERE, "ours"))
        self.assertEqual(calls["argv"][1:], ["-m", "plain"])
        self.assertEqual(calls["env"]["PYTHONPATH"].split(os.pathsep)[0], D.HERE)
        self.assertEqual(lines[-1]["controller"], "ours")

    def test_op1_and_labs_run_main(self):
        for t in (OP1, LT01):
            calls, lines = self.run_main(env(t))
            self.assertEqual(calls["cwd"], D.HERE)
            self.assertEqual(lines[-1]["controller"], "main")

    def test_task_from_a_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(env(MY1))
        try:
            self.assertTrue(D.ours(D.task(f.name)))
            self.assertTrue(D.ours(D.task("@" + f.name)))
        finally:
            os.unlink(f.name)

    def test_unreadable_task_runs_main(self):
        for bad in ("{not json", "/no/such/file.json", json.dumps({"task": "x"})):
            calls, lines = self.run_main(bad)
            self.assertEqual(calls["cwd"], D.HERE)
            self.assertEqual(lines[-1]["controller"], "main")

    def test_both_trees_are_where_the_dispatcher_looks(self):
        for tree in (D.HERE, os.path.join(D.HERE, "ours")):
            for pkg in ("plain", "overseer"):
                self.assertTrue(os.path.isfile(os.path.join(tree, pkg, "__init__.py")), (tree, pkg))


if __name__ == "__main__":
    unittest.main()
