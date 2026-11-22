"""The dispatcher: MY1 (an open task shorter than a year) runs ours/, a lab (a task with a hands-off window) runs
labs/ (main's tree with no change of ours), everything else the controller at the root, and an unreadable task or a
missing tree falls back to the root."""
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
LT02 = {"name": "lt02-rescue-neglected-s0", "days": 90, "goal": "From day 69 you can't act for 21 days.",
        "hands_off": {"from_day": 69, "days": 21}}
LT03 = {"name": "lt03-mood-artifact-s0", "days": 45, "goal": "A dwarf has been taken by a strange mood.",
        "hands_off": {"from_day": 38, "days": 7}, "strange_moods": True}
LT08 = {"name": "lt08-migrant-surge-s0", "days": 60, "goal": "Migrants are arriving.",
        "hands_off": {"from_day": 39, "days": 21}}
LABS = (LT01, LT02, LT03, LT08)


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
        for t in LABS:
            self.assertTrue(D.lab(t), t["name"])
            self.assertFalse(D.ours(t), t["name"])
        for t in (OP1, MY1, {}, {"hands_off": None}, {"hands_off": {}}):
            self.assertFalse(D.lab(t))

    def test_my1_runs_ours_with_the_shared_client_on_the_path(self):
        calls, lines = self.run_main(env(MY1))
        self.assertEqual(calls["cwd"], os.path.join(D.HERE, "ours"))
        self.assertEqual(calls["argv"][1:], ["-m", "plain"])
        self.assertEqual(calls["env"]["PYTHONPATH"].split(os.pathsep)[0], D.HERE)
        self.assertEqual(lines[-1]["controller"], "ours")

    def test_op1_runs_the_root(self):
        calls, lines = self.run_main(env(OP1))
        self.assertEqual(calls["cwd"], D.HERE)
        self.assertEqual(lines[-1]["controller"], "main")

    def test_labs_run_labs_with_the_shared_client_on_the_path(self):
        for t in LABS:
            calls, lines = self.run_main(env(t))
            self.assertEqual(calls["cwd"], os.path.join(D.HERE, "labs"), t["name"])
            self.assertEqual(calls["argv"][1:], ["-m", "plain"])
            self.assertEqual(calls["env"]["PYTHONPATH"].split(os.pathsep)[0], D.HERE)
            self.assertEqual(lines[-1]["controller"], "labs")

    def test_a_missing_tree_runs_the_root(self):
        real = os.path.isfile
        for t, gone in ((LT08, "labs"), (MY1, "ours")):
            hide = os.path.join(D.HERE, gone) + os.sep
            with mock.patch.object(D.os.path, "isfile", lambda p: not p.startswith(hide) and real(p)):
                calls, lines = self.run_main(env(t))
            self.assertEqual(calls["cwd"], D.HERE, gone)
            self.assertEqual([x["kind"] for x in lines], ["dispatch_error", "dispatch"])
            self.assertEqual(lines[-1]["controller"], "main")

    def test_the_lab_tree_has_none_of_our_changes(self):
        """labs/ is main's tree as published; the changes of this package are marked `h2`, `h4` or `h5` and live in
        the other two."""
        marks = {}
        for tree in ("", "ours", "labs"):
            n = 0
            for pkg in ("plain", "overseer"):
                folder = os.path.join(D.HERE, tree, pkg)
                for name in sorted(os.listdir(folder)):
                    if name.endswith(".py"):
                        with open(os.path.join(folder, name)) as f:
                            text = f.read()
                        n += text.count("h2:") + text.count("h4") + text.count("h5:")
            marks[tree] = n
        self.assertEqual(marks["labs"], 0)
        self.assertGreater(marks[""], 5)
        self.assertGreater(marks["ours"], 5)

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

    def test_the_trees_are_where_the_dispatcher_looks(self):
        for tree in (D.HERE, os.path.join(D.HERE, "ours"), os.path.join(D.HERE, "labs")):
            for pkg in ("plain", "overseer"):
                self.assertTrue(os.path.isfile(os.path.join(tree, pkg, "__init__.py")), (tree, pkg))


if __name__ == "__main__":
    unittest.main()
