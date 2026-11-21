"""Which controller plays this task.

A fresh full-year embark (OP1) and the lab tasks are played by the controller at plain/ and overseer/ (main's,
unchanged). A shorter open task, the handed-over fort (MY1), is played by ours/plain and ours/overseer (unchanged
from 0xplemonade's e884d63b). Each runs exactly as it did in its own package: `python -m plain` in a fresh
interpreter, from its own folder, with the shared dfbench_client/ on the path. Anything that can't be read here goes
to main's controller, which reads the task itself.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the package root: plain/, overseer/, ours/
FULL_YEAR = 336                                                       # days of a fresh embark's task (OP1)


def task(value=None):
    """The task part of DFBENCH_TASK: the JSON itself, a path to it, or '@path' (dfbench_client.task.load_task)."""
    v = (os.environ.get("DFBENCH_TASK") if value is None else value or "").strip()
    if v and not v.startswith("{"):
        with open(v[1:] if v.startswith("@") else v) as f:
            v = f.read()
    t = json.loads(v).get("task")
    return t if isinstance(t, dict) else {}


def ours(t):
    """An open task (no hands-off window) shorter than a fresh embark's year: the handed-over fort."""
    days = t.get("days")
    return (not t.get("hands_off") and isinstance(days, (int, float)) and not isinstance(days, bool)
            and 0 < days < FULL_YEAR)


def log(**kv):
    print(json.dumps({"t": round(time.time(), 2), **kv}), flush=True)


def main():
    root = HERE
    try:
        if ours(task()):
            root = os.path.join(HERE, "ours")
    except Exception as e:
        log(kind="dispatch_error", error=repr(e)[:200])
    log(kind="dispatch", controller="ours" if root != HERE else "main")
    env = dict(os.environ)
    env["PYTHONPATH"] = HERE + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    os.chdir(root)
    os.execve(sys.executable, [sys.executable, "-m", "plain"], env)


if __name__ == "__main__":
    main()
