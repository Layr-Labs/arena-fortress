# Two controllers: main's for the fresh embark and the labs, PR #229's for the handed-over fort

This package holds two complete harnesses and a dispatcher that picks one per task. Neither harness is changed.

- `dispatch/` reads the task from `DFBENCH_TASK`. An open task (no hands-off window) shorter than a year, the
  handed-over fort (MY1, 216 days), is played by the harness in `ours/`. Every other task, the fresh embark (OP1, 336
  days) and the four labs (each with a hands-off window), is played by main's harness at `plain/` and `overseer/`. A
  task it can't read also goes to main's harness. The chosen harness then runs exactly as in its own package:
  `python -m plain`, in a fresh interpreter, from its own folder, with the shared `dfbench_client/` on the path. The
  first line of the harness log names the choice (`{"kind": "dispatch", "controller": "ours" | "main"}`).
- `plain/`, `overseer/`, `tests/`: main's `submission/`, newjordan's `6fe223ed` (PR #233), byte-identical.
  `tests/test_dispatch.py` is the only file added there.
- `ours/plain/`, `ours/overseer/`, `ours/tests/`: 0xplemonade's `e884d63b` (PR #229, arm d81), byte-identical.
- `dfbench_client/`: the challenge's client, the same in both harnesses.

Both harnesses play with no model calls (`NO_MODEL = True` in each `plain/harness.py`). Standard-library Python, the
game API and the fixed gateway only. Sources and citations are in `dependencies.json`.

Tests:

    PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests
    cd ours && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.. python3 -B -m unittest discover -s tests
