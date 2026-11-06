# Persistent production and small-room capacity

## Objective and release scope

This release keeps routine fortress work progressing without requiring the playing model to select
every setup, production or furniture action. It starts from the organiser's plain baseline and uses
an observation-driven controller for common prerequisites. The fixed playing model remains
`z-ai/glm-5.3-flash` through the task's metered gateway. The model is consulted for unfamiliar or
unresolved situations. Ordinary management continues when advice is unavailable.

Implementation was developed with GPT-6 Astra at max reasoning through Codex. Earlier environment
setup and API probing used Claude Opus 5.5 through Claude Code. Separate local mechanics experiments
used GPT-6.1 Sol at xhigh reasoning through the locally authenticated Codex SDK on public forts.
The submitted program contains no Codex SDK, alternative playing-model adapter or credentials.
All real-model candidate measurements below used the challenge's GLM gateway and pinned provider.

The release selects the routine controller. Separate experiments with a Python planning kernel,
game-tree search and hand-written neural priorities have no demonstrated game benefit and are not
included. The release base is `1e86d20e3c87f322f522fa775de8f28ac2012fcd`; development began from
`75d40aa6adc8ee1b3f3b5ad1d74c3674f1ff3abf`.

## Inheritance and contribution

The organiser's plain baseline supplies the complete `dfbench_client` package, the package
entrypoint and the Docker build pattern. The controller and diagnostic loop were implemented
separately using the public game manual, the setup/dependency concepts in `policies.py`, and the
`MANUAL` in `harness2.py`. Those repository references explain manager validation, workshop inputs,
automation, seed recovery, furniture placement and time advancement. No reference-policy or Lua
implementation was copied into the controller.

After the initial controller was implemented, it adapted three ideas from mpjunior92's public
submission `afd1d5b6-b2c0-4790-a7b8-c1e71e3dab4a`,
[PR #15](https://github.com/Layr-Labs/arena-fortress/pull/15):

- Increase carpenter and still capacity with population, counting planned workshops toward targets.
- Increase the drink target before a hands-off window.
- Distinguish one-time orders from persistent production, and replace an older repeating order
  when population growth makes its threshold substantially too small.

The source is `submission/plain/caretaker.py` at commit
`624ad1d12d34aaa96e782126249f19d6285ff70a`, verified Git blob
`ca09ca67b2840746e0c8e8771d5a9967ba04a219`. The adaptations are in
`Controller.workshop_target`, `drink_target`, `recipe`, and the workshop-selection loop.
`dependencies.json` contains both-endpoint file hashes and line citations. Our implementation uses
a seven-day observation/addition age guard and can match the API's item-type condition fields as
well as named stock conditions.

The source's large-room excavation, initial reserve squad and sixty-action journal were not used.
The shorter action/failure memory was already implemented independently. The source declares a
journal dependency on `6ad71ca7`; this release does not use that implementation or its
sixty/twenty-five-record design. There are no direct human coauthors. Later public candidates were
read during research, but their new farm-goal, cooking, military and digest implementations are
not included here.

## Controller behavior

Each iteration observes the current public state. Routine checks handle visible threats and moods,
enable labor/material/crop automation, appoint a manager, build workshops, provide an assigned
office chair, prepare farms, queue production, place furniture and expand space. Planned structures
are remembered to avoid duplicates. Acceptance of an order or construction is not treated as
completion: dwarves must still validate, build, carry materials and do the work.

Brewing and barrels use conditional daily orders. An unfinished one-time brew is not sufficient
reason to omit a standing order. New orders are not cancelled repeatedly while waiting for
validation. Population changes can cause a threshold replacement; small changes within the
tolerance leave the existing order alone. A migrant-task bed objective prioritizes bed production.
A standing bed order avoids late one-time batches waiting for another validation. Planned furniture
counts as a commitment when deciding whether to order more, not as completed housing. Dining
furniture is placed in alternating table/chair order and checked against zones. The office is
established around a placed chair and assigned to the observed manager.

Excavation stays within each listed 3x3 R candidate. Extra capacity comes from more small rooms and
access shafts, with at most eight shafts started by this controller. Once previous work has had time
to expose candidates, a two-day pause allows another access instead of waiting ten days. That matters
in a short migrant window: bed items provide no housing when farms and existing furniture occupy
every available floor tile.

Identical successful actions are suppressed while the relevant observation is unchanged. Ordinary
failed actions have bounded retry delays. A `no_space` placement is remembered by furniture kind and
site, independent of the requested count. A new count or another day does not establish more space.
Room evidence includes its box, observed floor count, furniture/farm occupancy and visible water.
Changed evidence permits another attempt. The final release corrects an interaction with the older
per-action cache: `no_space` uses room evidence, so an exponential delay does not keep blocking the
same count after excavation changes the room. Its regression test failed before the correction and
passed afterward. Earlier v6 results below precede that one-line correction.

An unavailable stocks probe defers production selection instead of inventing empty inventory. Model
inspection uses the documented read-only query allowlist. The model sees current facts, recent
actions and stock history. Visible merchant cargo can inflate those counts, so the prompt cautions
that a caravan stock spike does not establish successful fortress production.

Model arguments are checked against the served schema before controller caches or policy checks.
The check covers field types, required and unknown keys, enums, numeric bounds and nested arrays
and objects. Booleans do not count as integer IDs or amounts. Read-only query arguments pass the
same check before dispatch. A malformed tool name or call ID ends that consultation safely.
This fixes four reproduced crashes caused by lists in the furniture site, automation name,
order ID or tool name. The full-loop regression injects each bad response and verifies that
management still advances the fake fort to day 20. The tests also preserve valid actions,
queries and conditional orders. This input-boundary fix was added after the six-game validation
started; the results below identify which runtime each check exercised.

Consultations normally occur fourteen game days apart, or four days apart while a mood is visible.
Each permits at most three calls, low reasoning and 1,800 output tokens per call. Advice stops at a
local estimate of 65 percent of the task's model allowance; the gateway remains authoritative.
Budget refusal and repeated model errors leave routine management active. The loop reserves daily
action capacity and advances when its own limit is reached. Advances shorten around unfinished
work, threats, low stocks and the final active lab days. Horizons and hands-off timing come from
the task/envelope. The inherited clients do not blindly retry uncertain game mutations.

## Development measurements

Every row is one local public-fort game. These are not official lower-bound estimates. Identical
seeds do not eliminate DF variation. LT08 uses its lab partial and clauses; its continuous outcome
O is not interchangeable with the lab result.

| Task and public fixture | Version | Local result |
| --- | --- | --- |
| OP1 default public fort | Plain baseline | O 75.6 |
| OP1 default public fort | Separate model-led playbook/status branch | O 85.2; not selected |
| OP1 default public fort | Early controller v2 | O 81.2 |
| OP1 fresh TEMPERATE_SOIL 2005 | Plain baseline | O 82.6 |
| OP1 fresh TEMPERATE_SOIL 2005 | Controller v4 | O 87.5 |
| LT08 regenerated worked fort 2005 | Plain baseline | Partial 0.8909; failed |
| LT08 same regenerated fort | Controller v4 | Partial 0.8865; failed |
| LT08 same regenerated fort | v5 capacity/order changes | Partial 0.8469; failed |
| LT08 same regenerated fort | v6 with faster small-room capacity | Partial 1.0; passed all clauses |
| MY1 public day-120 fort 2001 | Plain baseline | O 81.9 |
| MY1 same fort | Controller v6 | O 100.0 |

The negative LT08 results motivated the space change. In v4, 61 bed items existed near the window,
but 33 remained unplaced; the run recorded 70 `no_space` placement failures. More production alone
did not solve this. The subsequent expansion version met every lab clause, although its continuous
O was only 68.9. We retain the actual lab metric rather than substitute a more flattering number.

The v6 LT08 and MY1 runs used source digest
`sha256:4175107bd050d29af454602dddb9dc3ed63d83af82ad84655e3423cb070784b1`.
Their wall times were 439 and 1,240 seconds. Earlier v2 OP1 and LT08 model runs together spent
0.03614958 reference-price dollars. Fake-gateway charges are simulated and excluded from real-model
spend accounting. Final release validation is recorded separately from these developmental versions.

The documented setup wrapper regenerated the lab fixtures. Earlier v1/v2 lab results used the prior
fixtures and are not controls for the regenerated v4/v5/v6 sequence above. Fresh OP1 and MY1 snapshots
were retained unchanged for their paired comparisons. Public seed 2002 failed to build because its
attempted sites failed the shallow-aquifer requirement; another seed was not substituted under its name.

## Release validation

The configured `yukon run --track harness-glm-5-3-flash` completed a real-model suite with one
game per task on the public fixtures described above. The selected controller included the
room-cache correction and preceded the final model-argument check. Its recorded harness-directory
digest was `sha256:188075d23245440983dda430dcac7199e82297acd01b0ffa4d0d05b80b48d82f`.

| Task | Lab partial / pass | Outcome O | Wall seconds | Model credits, USD |
| --- | --- | --- | --- | --- |
| LT01 | 1.0 / pass | 73.4 | 300.3 | 0.004194 |
| LT02 | 1.0 / pass | 62.7 | 353.8 | 0.008769 |
| LT03 | 1.0 / pass | 100.0 | 243.0 | 0.009728 |
| LT08 | 1.0 / pass | 74.5 | 413.3 | 0.003869 |
| MY1 | not a lab | 100.0 | 713.9 | 0.018108 |
| OP1 | not a lab | 90.6 | 1718.1 | 0.033532 |

All six games completed without a harness error, wall cap, model-budget refusal or recorded upstream
error. Total reference-price model spend was $0.0782. The wrapper reported 96.79 for this local
six-game selection with provisional public anchors. With one game per task, its bootstrap cannot
measure repeat-run variation or support a hidden-pool lower-bound claim. Per-task results above
are the useful evidence. OP1 reached tier 4 with survival, supply and wellbeing at 1.0 and growth
at 0.625; growth remains the gap on this public embark.

After adding model-argument validation, the corrected runtime passed 48 offline tests and another
real-DF smoke test with the fake gateway. A further real-model LT08 game passed all four clauses,
partial 1.0, O 73.4, in 436.6 seconds, with five calls costing $0.004812. No gateway or harness errors
were recorded. Its harness-directory digest was
`sha256:940073e9d832058e54ffb64b1c4d67d2ddda789af0fe68ccee615d5a013462e2`.
These tests used the final runtime Python files; later note edits change the directory digest
without changing the Docker runtime. The other five real-game tasks were not repeated after the
input-boundary fix. It changes rejection of malformed advice, not routine controller policy.

The suite used three parallel games and `--retries 0`. To repeat the selected public inputs, use
the usual wrapper with a suite whose task paths select those public snapshots:

```sh
DFBENCH_PARALLEL=3 DFBENCH_SUITE_ARGS="--suite $PUBLIC_TASKS/release-suite.json --retries 0" \
  yukon run --track harness-glm-5-3-flash
runner/dfbench local run --harness submission/ --task "$PUBLIC_TASKS/lt08-migrant-surge.json" --retries 0
```

## Public mechanics experiment

A separate Codex-SDK Sol player explored fresh public seeds 2001 and 2005 for an 84-day horizon.
Its 9x9 excavation on 2005 opened a flooded room and a miner drowned. We replayed the same opening
through the game API with only the first room dimensions changed. Two 3x3 replays reached day 14
with seven citizens alive and visible fort-level water-depth totals of 7 and 7. Two 9x9 replays had
totals of 259 and 399; one lost two citizens and the other lost none. These are summed visible
water-depth units, not every tile on the map.

That reproduces increased flooding, not certain mortality. Small rooms are not universally safe;
hidden terrain, access and later designations still matter. It supports keeping excavation within
the advertised footprint and creating capacity incrementally. No Sol program, saved game, local
credential or direct game-process access is part of this release.

## Reproduction and remaining limits

The local environment was x86_64 Linux, rootless Docker, DF 53.16 and DFHack 53.16-r2. Images and forts
were built using the repository's unmodified scripts. Local scenario copies restricted lab pools
to completed public 2005 forts, MY1 to the public 2001 day-120 fort, and the extra OP1 comparison to
the retained fresh 2005 embark. Setup, horizons, hands-off windows, game API, scorer and playing-model
condition were preserved. These copies are run inputs; trusted scenario sources were not edited.

After standard setup and model-key configuration, use:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s submission/tests -v
runner/dfbench local smoke --harness submission/ --task "$PUBLIC_TASKS/lt01-drought.json"
runner/dfbench local run --harness submission/ --task "$PUBLIC_TASKS/lt08-migrant-surge.json"
runner/dfbench local run --harness submission/ --task "$PUBLIC_TASKS/my1.json"
```

`PUBLIC_TASKS` denotes the reader's local copies with explicitly selected public snapshot pools.
`DFBENCH_SNAPSHOTS_DIR` can point to existing public saves. Supply the participant's model key through
the normal runner environment; the image has no key. The pinned image is stdlib-only and runs the
original Python module entrypoint as nobody. Local tests use the repository's HTTP fakes and are not
copied into the game image.

This remains a heuristic controller. Farm diversity, seed recovery, shared inputs and wildlife can
still cause failure. More workshops do not guarantee available workers. Crop choice belongs to the
exposed automation, and no trade action solves exports. Defence and moods have limited coverage.
The meal rule can be conservative when plants are scarce, and stock slopes can reflect traders.
Repeated public-fort comparisons are needed before attributing small score differences to a single
change. The local results justify another measurement, not a prediction of the seasonal ranking.
