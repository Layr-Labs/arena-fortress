# PR #248's three trees, with a hunger cull on the fresh embark that an empty check no longer postpones

This package holds three complete harness trees and a dispatcher that picks one per task. It is our PR #248 (PR #243 with
an office below ground for the expedition leader on the handed-over fort, marked `h4`, and one more release-guard
workshop past the game's allowance, marked `h5`) with one change in the tree that plays the fresh embark, also
marked `h5`: a hunger check that finds no animal to mark no longer starts the cull's cooldown. The handed-over fort
and the four labs are played exactly as in PR #248.

- `dispatch/` reads the task from `DFBENCH_TASK`.
  - A task with a hands-off window, which is each of the four labs, is played by the harness in `labs/`.
  - An open task (no hands-off window) shorter than a year, the handed-over fort (MY1, 216 days), is played by the
    harness in `ours/`.
  - Every other task, which is the fresh embark (OP1, 336 days), is played by the harness at `plain/` and `overseer/`.
    A task it can't read, or a tree that is not in place, also goes there; that harness plays every task.
  The chosen harness then runs as in its own package: `python -m plain`, in a fresh interpreter, from its own folder,
  with the shared `dfbench_client/` on the path. The first line of the harness log names the choice
  (`{"kind": "dispatch", "controller": "main" | "ours" | "labs"}`).
- `plain/`, `overseer/`, `tests/`: main's `submission/`, newjordan's `6fe223ed` (PR #233), with these changes, all
  marked `h2` in the code:
  - `overseer/openplay.py` (`reconnect`, `reindex_site`): when a wildlife lockdown is released, one Carpenters, one
    Masons and one Farmers workshop are ordered on free surface sites, and the release is watched until one of
    those kinds is seen finished: a finished workshop makes DF rebuild the path index that the API's `lock_door`
    leaves stale (challenge issue #238; `tests/test_h2_reconnect.py`). Marked `h5`: a game orders 18 such workshops
    at most, and past that a release orders one more only when no such workshop is waiting unbuilt and it has not
    ordered one itself (in one local game the allowance was gone by day 260 and the release of day 271 could order
    nothing);
  - `overseer/openplay.py` (`cull`), marked `h5`: the cooldown between hunger culls starts only when an animal was
    marked. Before, a check that found nothing to spare (only the animals kept for the feast, and food not yet at
    zero) started it too, and when the food ran out inside those days the kept animals could not be released
    (`tests/test_winner_fixes.py`). The tree in `ours/` already works this way;
  - `overseer/harness.py` (`meeting_area`): no underground meeting area on a full-year embark;
    `tests/test_winner_fixes.py` says so;
  - `overseer/harness.py` (`progression_push`): the wood-tool orders pause while a released lockdown waits for its
    workshop, as they already do for housing and hatch covers (`tests/test_h2_push.py`);
  - `plain/harness.py` (`read`, `attempt`, `look`, `advance_failed`, `seen`) and `Overseer.step`: a failing read of
    the game server is tried again for up to five minutes, and a lost answer to an advance is followed by a look
    at the clock, instead of ending the harness (`tests/test_h2_loop.py`).
  `tests/test_dispatch.py` is from PR #237, extended for the third tree.
- `ours/plain/`, `ours/overseer/`, `ours/tests/`: 0xplemonade's `e884d63b` (PR #229, arm d81), with the first and
  the last of those changes (its workshops are ordered Farmers, Carpenters, Masons) and, marked `h4`, the expedition
  leader's office (`ours/overseer/harness.py`: `leader_wants_office`, `leader_office`, and lines in `digging`,
  `reserved` and `office_chair_needed`): one more 3x3 room is dug after the others, zoned as an office and assigned
  to the expedition leader once the manager has a chair or a usable office zone of his own, and given a chair after
  the manager's has one. Nothing is done while the manager's post is vacant, when the leader is the manager, or on a
  lab; an unowned office is left to the manager until his has its chair; a room another zone took first is given
  up and one more is dug, two rooms and two zones at most (`ours/tests/test_h4_leader_office.py`).
- `labs/plain/`, `labs/overseer/`: main's `submission/plain/` and `submission/overseer/` at `d0929e6`, byte for byte.
  Nothing of ours is in them (`tests/test_dispatch.py` checks that no `h2`, `h4` or `h5` mark is).
- `dfbench_client/`: the challenge's client, the same for all three.

All three play with no model calls (`NO_MODEL = True` in each `plain/harness.py`). Standard-library Python, the game
API and the fixed gateway only. Sources and citations are in `dependencies.json`.

Tests:

    PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests
    cd ours && PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.. python3 -B -m unittest discover -s tests
