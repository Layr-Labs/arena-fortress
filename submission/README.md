# Two controllers: main's for the fresh embark and the labs, PR #229's for the handed-over fort, both hardened

This package holds two complete harnesses and a dispatcher that picks one per task, as our PR #237 did. Both
harnesses carry a few changes of ours, marked `h2` in the code.

- `dispatch/` reads the task from `DFBENCH_TASK`. An open task (no hands-off window) shorter than a year, the
  handed-over fort (MY1, 216 days), is played by the harness in `ours/`. Every other task, the fresh embark (OP1, 336
  days) and the four labs (each with a hands-off window), is played by main's harness at `plain/` and `overseer/`. A
  task it can't read also goes to main's harness. The chosen harness then runs as in its own package: `python -m
  plain`, in a fresh interpreter, from its own folder, with the shared `dfbench_client/` on the path. The first line
  of the harness log names the choice (`{"kind": "dispatch", "controller": "ours" | "main"}`).
- `plain/`, `overseer/`, `tests/`: main's `submission/`, newjordan's `6fe223ed` (PR #233), with these changes:
  - `overseer/openplay.py` (`reconnect`, `reindex_site`): when a wildlife lockdown is released, one Carpenters, one
    Masons and one Farmers workshop are ordered on free surface sites, and the release is watched until one of
    those kinds is seen finished: a finished workshop makes DF rebuild the path index that the API's `lock_door`
    leaves stale (challenge issue #238; `tests/test_h2_reconnect.py`);
  - `overseer/harness.py` (`meeting_area`): no underground meeting area on a full-year embark (the labs keep
    theirs); `tests/test_winner_fixes.py` says so;
  - `overseer/harness.py` (`progression_push`): the wood-tool orders pause while a released lockdown waits for its
    workshop, as they already do for housing and hatch covers (`tests/test_h2_push.py`);
  - `plain/harness.py` (`read`, `attempt`, `look`, `advance_failed`, `seen`) and `Overseer.step`: a failing read of
    the game server is tried again for up to five minutes, and a lost answer to an advance is followed by a look
    at the clock, instead of ending the harness (`tests/test_h2_loop.py`).
  `tests/test_dispatch.py` is from PR #237.
- `ours/plain/`, `ours/overseer/`, `ours/tests/`: 0xplemonade's `e884d63b` (PR #229, arm d81), with the first and
  the third of those changes (its workshops are ordered Farmers, Carpenters, Masons).
- `dfbench_client/`: the challenge's client, the same in both harnesses.

Both harnesses play with no model calls (`NO_MODEL = True` in each `plain/harness.py`). Standard-library Python, the
game API and the fixed gateway only. Sources and citations are in `dependencies.json`.

Tests:

    PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests
    cd ours && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.. python3 -B -m unittest discover -s tests
