# PR #249's three trees, with the underground meeting area made from a game's first lockdown on

This package holds three complete harness trees and a dispatcher that picks one per task. It is our PR #249 (PR #243 with
an office below ground for the expedition leader on the handed-over fort, marked `h4`; one more release-guard
workshop past the game's allowance and, on the fresh embark, a hunger check that starts no cooldown when it marks
nothing, both marked `h5`) with two changes, also marked `h5`. On the fresh embark the underground meeting area is
made once every known surface stair has a built hatch cover, which is main's rule, and the game's first wildlife
lockdown has begun, which is ours (our packages from PR #240 to PR #249 made no such zone).
In both open-task trees the invader warning reads a distance of 0 as a hostile on the wagon's tile instead of a
missing value, and a refused warning may be tried again a day later instead of twenty days later. The four labs
are played exactly as in PR #243 to PR #249.

- `dispatch/` reads the task from `DFBENCH_TASK`.
  - A task with a hands-off window, which is each of the four labs, is played by the harness in `labs/`.
  - An open task (no hands-off window) shorter than a year, the handed-over fort (MY1, 216 days), is played by the
    harness in `ours/`.
  - Every other task, which is the fresh embark (OP1, 336 days), is played by the harness at `plain/` and `overseer/`.
    A task it can't read, or a tree that is not in place, also goes there; that harness plays every task.
  The chosen harness then runs as in its own package: `python -m plain`, in a fresh interpreter, from its own folder,
  with the shared `dfbench_client/` on the path. The first line of the harness log names the choice
  (`{"kind": "dispatch", "controller": "main" | "ours" | "labs"}`).
- `plain/`, `overseer/`, `tests/`: main's `submission/`, newjordan's `6fe223ed` (PR #233), with these changes,
  marked `h2` or `h5` in the code:
  - `overseer/openplay.py` (`reconnect`, `reindex_site`): when a wildlife lockdown is released, up to three
    workshops (a Carpenters, a Masons and a Farmers) are ordered on free surface sites, as far as sites and
    building material allow, and the release is watched, for twelve days at most, until one of those kinds is
    seen finished: a finished workshop makes DF rebuild the path index that the API's `lock_door` leaves stale
    (challenge issue #238; `tests/test_h2_reconnect.py`). Nothing is ordered on a pass whose workshop list cannot
    be read. Marked `h5`: a game's allowance is 18 accepted orders, and past it a release may still order one,
    only when no workshop of those kinds is waiting unbuilt and unsuspended and the release has not tried one
    itself (in one local game the allowance was gone by day 260 and the release of day 271 could order nothing);
  - `overseer/openplay.py` (`cull`), marked `h5`: the cooldown between hunger culls starts only when an animal was
    marked. Before, a check that found nothing to spare (only the animals kept for the feast, and food not yet at
    zero) started it too, and when the food ran out inside those days the kept animals could not be released
    (`tests/test_winner_fixes.py`). The tree in `ours/` already works this way;
  - `overseer/harness.py` (`defend`), marked `h5`: `near` was `(distance or 10 ** 6) <= 45`, which reads a hostile
    on the wagon's own tile (distance 0) as no reading at all; and a refused `civilian_alert` started the same
    20-day wait as an accepted one (`tests/test_h2_reconnect.py`). The same change is in `ours/`, with one more
    line there: a hostile at distance 0 was also dropped from the squad's targets;
  - `overseer/harness.py` (`meeting_area`) and one line of `overseer/openplay.py` that counts the lockdowns, marked
    `h5`: main's rule with one condition added, that on a full-year embark the zone waits for the game's first
    wildlife lockdown (counted when a lockdown's alert is accepted; from then on the controller tries to make the
    zone on a pass that finds a suitable site, three tries a site at most, which can be during that first
    lockdown). From PR #240 to PR #249 this tree made no underground meeting area there, because a fort
    whose path index is rebuilt during a lockdown stays below after the release when everybody idles below; in
    ordinary games that proved rare, and on the public fort where flying predators return all year idle dwarves
    at the wagon were lost far more often than with the zone. On a public fort that hardly ever locks down the
    zone made early went with losses, hence the condition; the note has the counts (`tests/test_winner_fixes.py`);
  - `overseer/harness.py` (`progression_push`): the wood-tool orders pause while a released lockdown waits for its
    workshop, as they already do for housing and hatch covers (`tests/test_h2_push.py`);
  - `plain/harness.py` (`read`, `attempt`, `look`, `advance_failed`, `seen`) and `Overseer.step`: a failing read of
    the game server is tried again for up to five minutes, and a lost answer to an advance is followed by a look
    at the clock, instead of ending the harness (`tests/test_h2_loop.py`).
  `tests/test_dispatch.py` is from PR #237, extended for the third tree.
- `ours/plain/`, `ours/overseer/`: 0xplemonade's `e884d63b` (PR #229, arm d81), with the first and
  the last of those changes (its workshops are ordered Farmers, Carpenters, Masons) and, marked `h4`, the expedition
  leader's office (`ours/overseer/harness.py`: `leader_wants_office`, `leader_office`, and lines in `digging`,
  `reserved` and `office_chair_needed`): one more 3x3 room is dug after the others, zoned as an office and assigned
  to the expedition leader once the manager has a chair or a usable office zone of his own, and given a chair after
  the manager's has one. Nothing is done while the manager's post is vacant, when the leader is the manager, or on a
  lab; an unowned office is left to the manager until his has its chair; a room another zone took first is given
  up and one more is dug, two rooms and two zones at most. This tree's own tests are not shipped any more, to
  keep the package small for review: they are the 29 files of `submission/ours/tests/` in our PR #250, whose
  `ours/plain/` and `ours/overseer/` are byte-identical to these; its 223 tests pass there.
- `labs/plain/`, `labs/overseer/`: main's `submission/plain/` and `submission/overseer/` at `d0929e6`, byte for byte.
  Nothing of ours is in them (`tests/test_dispatch.py` checks that no `h2`, `h4` or `h5` mark is).
- `dfbench_client/`: the challenge's client, the same for all three.

All three play with no model calls (`NO_MODEL = True` in each `plain/harness.py`). Standard-library Python, the game
API and the fixed gateway only. Sources and citations are in `dependencies.json`, which has an entry for each
other entrant's submission that a comment in the controllers' files (`plain/` and `overseer/`, in all three trees)
names by its id.

Tests (the tree at the root and the dispatcher):

    PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests
