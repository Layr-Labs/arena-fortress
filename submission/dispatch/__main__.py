"""Which controller plays this task.

A fresh full-year embark (OP1) is played by the controller at plain/ and overseer/ (main's 6fe223ed with our changes,
marked `h2` and `h5`). A shorter open task, the handed-over fort (MY1), is played by ours/plain and ours/overseer
(0xplemonade's e884d63b with our changes, marked `h2`, `h4` and `h5`). A lab task (one with a hands-off window) is
played by labs/plain and labs/overseer: main's 6fe223ed byte for byte, with no change of ours, as the labs were
played in our PR #237. Each runs as it did in its own package: `python -m plain` in a fresh interpreter, from its own
folder, with the shared dfbench_client/ on the path. Anything that can't be read here, and any tree that is not where
it should be, goes to the controller at the root, which reads the task itself and plays every task.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the package root: plain/, overseer/, ours/, labs/
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


def lab(t):
    """A task with a hands-off window: the four lab tasks."""
    return bool(t.get("hands_off"))


def tree(name):
    """The folder a controller runs from; the root when its own is not there with a plain package in it."""
    root = HERE if name == "main" else os.path.join(HERE, name)
    if os.path.isfile(os.path.join(root, "plain", "__main__.py")):
        return root, name
    log(kind="dispatch_error", error="no plain package in %r" % name)
    return HERE, "main"


def main():
    name = "main"
    try:
        t = task()
        name = "labs" if lab(t) else "ours" if ours(t) else "main"
    except Exception as e:
        log(kind="dispatch_error", error=repr(e)[:200])
    root, name = tree(name)
    log(kind="dispatch", controller=name)
    env = dict(os.environ)
    env["PYTHONPATH"] = HERE + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    os.chdir(root)
    os.execve(sys.executable, [sys.executable, "-m", "plain"], env)


if __name__ == "__main__":
    main()
