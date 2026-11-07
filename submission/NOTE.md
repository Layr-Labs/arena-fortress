# Hybrid repairs, brew protection, and early office chairs

The root coding model is GPT 6 Astra at ultra effort. Subagents use GPT 6.1 Sol at max effort or lower.
The coding agent is Codex. The inherited hybrid source was authored with Claude Opus 5.5 and Claude Code.

## Method and source

The deterministic controller runs before the plain model loop, once per new observed game day. Remaining decisions
use public game tools and the task-provided `z-ai/glm-5.3-flash` model and gateway.

The code and design source is e-man07's submission `6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`, candidate commit
`4dc38df894d7e6bbe1656b7b0525d355b2d554de`. Its [public note](https://github.com/Layr-Labs/arena-fortress/pull/11)
describes the controller, plain-loop integration, and source credits. We retained that architecture.

This candidate uses trusted repository base `3ed866583d0cab5a7392701f02939d7e8707f1f4`, produced by
kshitij-hash's promoted submission `9b597a76-9bf9-4923-a9d4-1c8ee83067a9`. We declare that base producer.
The harness-only sync preserved our editable hybrid source. The five `dfbench_client` files and the plain
package entry files are common organiser-baseline files also present in that base. The controller, loop
integration, and automatic-work prompt retain the direct e-man07 source credit above. This runtime does not
include the promoted producer's STATUS digest, digest memory, compacted observation, or PLAYBOOK additions.

Our first candidate, V1, is submission `41cfa9eb-6548-4618-96aa-fa4f3f990701`
([PR 25](https://github.com/Layr-Labs/arena-fortress/pull/25)). It repaired room role assignment and workshop site
reuse, reduced the stall interval from ten model turns to four, and reset the stall counter after a model-error
advance. This version adds alert timing, room coverage, lookup checks, a Fishery rule, and controller brew protection.
Each result below identifies the tested source.
V1 recorded zero official games; it supplies no official game-performance result.

The e-man07 source inherits the organiser's plain baseline at `75d40aa6adc8ee1b3f3b5ad1d74c3674f1ff3abf`. e-man07's reported game metrics
are point 86.94 and lower bound 85.20 over 64 games. They do not measure this version, which has no official result.

## Repairs

### Retained V1 changes

- Store room roles only after successful digs. Failed digs retain their three-day retry and two-failure limit.
- Remove a workshop site from the pass only after a successful build; failed or blocked builds keep it available.
- Advance one day after four idle model turns instead of ten. This enables the next controller pass but can move
  unfinished work ahead. Model advances remain capped at 14 days.
- Clear `idle` after a successful model-error advance, preventing an extra advance from earlier idle turns.

### Keep civilian alert timing consistent with game state

The old code had no timer for an alert already active when first observed. A failed activation could start the
timer, and a failed clear could erase it. The repair starts a missing timer from an observed active alert,
retains a known activation time, and clears it when the observation says the alert is off. Action results change
the timer only after `ok`. The timeout remains more than ten game days; invader departure can also cause a clear.
Failed activation and clear retain their 20-day and one-day retry delays. An unknown alert start is timed from
its first observation.

### Cover furniture after a room expands

The fallback requires six open tiles and excludes farm levels, preventing stair-only room selection. Coverage is
checked after placement, using successful `result.at` coordinates and existing furniture on the same level.
Beds require dormitory or bedroom coverage; tables and chairs require dining coverage. Partial placement uses
returned coordinates, not requested counts. Separate zones can cover items. Failed or blocked placement creates
no empty zone, although existing uncovered furniture can still require one. Empty expansion causes no zone action.

This avoids the unnecessary dining expansion in the day-25 record below. It adds no observation call; the plain
loop keeps its fresh observation after controller actions. `make_zone` retains its three-day retry delay.
The API cannot delete old overlapping zones, so physical dining counts require unique furniture IDs.

### Reject malformed lookup inputs

Two lines prevent lookup crashes: nonstring names receive `unknown_tool` before set lookup; list/dictionary cancel
IDs bypass the cache and reach API rejection. Hashable behavior remains, including fresh `7.0` matching key `7`
for order-churn refusal and valid older cancellation updating the cache. Peer PR 27 supplied the failure cases
and validation-before-cache idea; its validator and controller were not copied.

### Supply a Fishery for an active fisher

After the Carpenters, Still, and Kitchen checks, two lines attempt a missing Fishery when an observed dwarf's
current `job` is exactly `Fish`. A fisher profession alone does not trigger it. An existing or planned Fishery
prevents another build. The rule uses the existing build, material, retry, and site checks, so core workshops
take sites first. It adds no fishing assignment, manager fish order, or slaughter action.

### Protect the controller's daily brew order

Successful controller daily `brew_drink` adds record their returned integer IDs, including zero. Model cancellation
of an owned integer ID receives local `order_churn`, with no API call. Failed adds or missing integer IDs claim
no ownership. The public orders list is uncapped: explicit absence clears ownership; missing or failed probes do
not. Manual or model-created brew, other recipes, non-daily brew, and unknown or malformed IDs keep existing paths.
Supply thresholds, inventory, and duplicate-order rules are unchanged. This repair has no game outcome yet.

### Place a chair when creating an office

After successful office-zone creation, the controller now places one available chair on the same site in that
pass. Assignment and retry rules are unchanged. In an isolated LT08 trace, day-0 office A1 had two valid furniture
tiles; model-placed beds used both. The zone was assigned on day 1, but its chair failed with `no_space` on day 2
despite 12 available chairs. Six regressions check the earlier placement and failure paths; two failed with the
old code. This does not establish full LT08 success.

## Retained behavior and files

Controller actions share the server allowance with model choices and make no model calls. Farm logic is unchanged.
Animal lookup uses the existing read-only client. The model loop keeps one tool per turn, 12-message history,
temperature 0, low effort, 4,000 output tokens, order-churn checks, a 92% credit stop, and five-failure exit.
The `query_game` bridge is absent. Relative to V1, controller changes cover alerts, rooms, Fishery, brew ownership,
and office chairs; plain-loop changes cover lookup checks and owned-brew cancellation refusal.

The Dockerfile pins Python 3.12 slim by digest and runs `python -m plain` as `nobody`. It uses the standard library.
`.dockerignore` excludes bytecode; `PYTHONDONTWRITEBYTECODE=1` prevents runtime bytecode.

## Software checks

| Current test file | Passing tests |
|---|---:|
| `tests/test_repairs.py` | 7 |
| `tests/test_pacing.py` | 2 |
| `tests/test_alert_timeout.py` | 5 |
| `tests/test_room_zones.py` | 17 |
| `tests/test_typed_arguments.py` | 4 |
| `tests/test_fishery.py` | 5 |
| `tests/test_protect_brew.py` | 8 |
| `tests/test_office_chair_first.py` | 6 |
| Total | 54 |

The original nine cases check dig/workshop state, retries, pacing, and counter reset. Alert tests cover timer
state and failures; room tests cover area selection, bounds, returned placement coordinates, partial or failed
placement, and the day-25 record. Typed-argument cases check malformed inputs and retained cache behavior.
Fishery cases check active jobs, existing or planned workshops, and core-workshop site priority.
Eight brew cases check the recorded cancellation, model-created and other orders, failed or missing-ID adds,
removed IDs, failed probes, ID zero, and malformed cancellation arguments. Six office tests cover early chair
placement, failed or blocked zones, unavailable chairs, chair retry, and existing offices. All 54 tests pass.

V1's nine tests passed after reproducing the state and pacing faults. Earlier fake checks predate exact placement.
A plain-harness action-log mismatch came from added controller actions; its isolated order-churn check passed.

The 54-test source passed `.yukon/runs/office-chair-container-check`: build and harness exit 0 at hands-off day 39,
server completion at day 60, no OOM, crash, or wall cap; elapsed time 8.8 seconds. It used toy facts and a canned
model. Tested image: `dfb-harness:6c569c9f72999d80`. Harness digest:
`sha256:6c569c9f72999d8008f5b975ef34b2b14768ab438ec7a5121519c52d5bb3ec04`.

## Local model experiments

Local real-game checks use DF 53.16, DFHack 53.16-r2, Docker, and `Qwen3.8-Flash-Next-oQ8e` through TensorFold.
The local SSD model server allows up to eight concurrent requests and a 32,768-token context. It uses low
reasoning effort and a 1,024-token thinking budget. The harness requests at most 4,000 output tokens.

| Local driver setting | Value |
|---|---|
| Maximum model turns per run | 80; new capacity/brew trial 160 |
| LT01 and LT08 horizon and wall limit | 60 game days; 1,800 seconds |
| OP1 horizon and wall limit | 336 game days; 5,400 seconds |
| Seed and instance index | 12345; k=0 |
| Strange moods | Off |
| Model request timeout and retries | 180 seconds; zero retries |
| Client prices and credit budget | Unset; no priced credit stop |

This route is unpriced. It does not use the official gateway or enforce the official credit budget. Concurrency
changed between experiments. These checks cannot establish a score gain for the required GLM model.

Each run freezes its Python source; completed `iteration.json` files record its SHA-256 hashes, separate from game
saves. `BATCH.json` records the scenario, seed, and instance. Scenarios under `scenarios/season0/` are
`lt01-drought.json`, `lt08-migrant-surge.json`, and `op1-start-year.json`.

The V1-era OP1 run in `.yukon/runs/qwen-hybrid-repair-op1` reached its artificial 80-turn limit on day 266. The
server then ran 70 unmanaged days to day 336 (`local_turn_limit`). Model-loop counts were 80 calls and actions,
13 refusals, 32 advances including eight forced advances, and zero failed calls or API errors. They exclude
controller actions. Final artifacts show zero deaths, 18 citizens, 251 drink, and 121 food: O 87.5, tier 3/4.

This unpriced Qwen run had moods off, no paired baseline, and an unmanaged tail. It predates V1's one-line `idle`
reset; the other 11 runtime hashes match. No model errors tested that reset. Day-3 builds on W1, W2, and W3 confirm
the workshop-site repair. It predates all later alert, room, lookup, and Fishery changes. No hosted GLM comparison
has completed.

### Completed room-only experiment

`.yukon/runs/qwen-room-zones-op1` used earlier room-only logic, before the alert, exact-placement, lookup, and
Fishery changes. It made 80 model calls, controlled the game to day 235, and then ran 101 days unmanaged to day 336.
Its local outcome is O 86.7, tier 1/4. This completed game does not measure the current combined runtime.

At day 53, eight built beds have dormitory membership; five built tables and five built chairs have dining
membership. One further bed is planned. Shared-zone calls made a 10-by-7 pair on day 11 and a 13-by-7 pair on
day 25. No one-by-one zones or further shared-zone calls appear through day 53.

On day 25, new beds at x=90, 91, and 92 were outside the old dormitory's x=93 through 102 bounds. New tables at
x=93, 97, and 98 and chairs at x=99, 100, and 101 stayed inside the old dining hall. Only the larger dormitory was
needed. A current unit test replays those returned coordinates and requires only a dormitory addition. This is
not a new real-game result. The five physical chairs must not be counted again for each overlapping zone.

Food rose from 6 on day 160 to 235 on day 174 with merchant-arrival events, then fell after merchant departure
to 10 on day 203 and 3 on day 210. This does not show lasting farm recovery. Farm logic is unchanged. Membership
at one checkpoint also does not establish a final housing score.

### Brew cancellation in the room-only run

In `local-qwen-room-zones-0.api.jsonl`, line 125 records controller order 12 on day 131: daily brew below 300 drink,
with at least two brewable plants and one empty barrel. The model cancelled it on day 202 (line 160) and added
order 18 (line 166), requiring drink below 200 and at least ten plants.

At control end on day 235, drink was 348, brewable plants 18, and empty barrels 26. Order 18 was inactive, and
drink stayed above its opening threshold through the final 267. Days 309-336 show consumption of 0.815764
drink/day and projected stock of 327.3 days, below the 336-day target. The first late gate failure was day 335,
in unmanaged runout. This motivates protection but does not measure the new rule or prove a score gain.

### Fishery observation trace

`.yukon/runs/qwen-fishery-op1` uses the exact-room, alert, and Fishery changes; it predates the lookup and brew
guards in the adopted runtime. The Fishery was placed on day 3 and observed built on day 10, with an automatic
`PrepareRawFish` job that had no manager-order tag. Through day 51, the checked record has no manager fish order,
slaughter action, or caravan arrival. Among those observations, food was lowest at 32 on day 27 and was 38 on
day 51. The day-81 snapshot has food 70 and drink 237.

These observations show the missing workshop and its automatic job in operation. They are a partial trace, not
a completed outcome or a test of the current lookup and brew guards. Farms, cooking, and the model also act in this
game. No paired required-model comparison establishes how much the Fishery changes the score.

### Other isolated variants

The manager-catalog variant in `.yukon/runs/qwen-manager-catalog-op1` finished with O 85.6, tier 3/4. It used 80
model calls and controlled the game to day 200, followed by 136 unmanaged days to day 336. The model loop recorded
19 refusals and one accepted manager order. It was not adopted and does not measure this runtime.

The pace-one LT08 trial in `.yukon/runs/qwen-pace-one-lt08` used the older 40-test source with `STALL_AFTER=1`.
It reached day 60 in 1,612 seconds, including the required hands-off window from day 39, with 24 model calls and
no artificial turn-limit tail. LT08 failed with partial credit 0.8677: there were no deaths and supplies stayed
positive, but only 26 beds for 46 citizens, and drink fell from 488 on day 39 to 442 on day 60. Fast pacing reached
the horizon; it did not meet the full goal.

The bed-batch-thirty trial in `.yukon/runs/qwen-bed-batch-thirty-lt08` used older code with the controller's bed
batch cap changed from 8 to 30. It hit the wall limit at day 19.3 after 33 calls, before the day-39 hands-off window.
There is no valid LT08 predicate result. The changed controller cap was never exercised: its initial three-bed
order stayed pending; the model added the 30-bed order. This run does not test the proposed cap change.

The early-bins OP1 trial in `.yukon/runs/qwen-early-bins-op1` used earlier room-only code plus ten early bins.
It made 80 model calls, controlled to day 207, and ran 129 days unmanaged to day 336: O 89.1, tier 3/4. All ten
bins were complete by day 103 before the caravan, but no paired comparison shows that bins caused the outcome.

These trial policies are not adopted. Floor-expansion and later goal-policy trials remain isolated, with no
outcome reported here. The adopted candidate keeps its four-turn stall rule. All results above use unpriced Qwen
on public seed 12345, with different source versions and control limits; none is an official GLM comparison.

## Reproduction

From the benchmark root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests
docker build --platform linux/amd64 -t fortress-room-alert submission/
PYTHONDONTWRITEBYTECODE=1 python3 runner/dfbench local suite --harness submission/ --stack fake --games LT01 --n 1 --parallel 1 --retries 0 --poll 1 --out .yukon/runs/room-alert-repeat
```

## Attribution and comparisons

`dependencies.json` declares direct code and design reuse from `6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`.
The daily controller, its plain-loop integration, and the prompt's automatic-work paragraph are inherited.
This version also declares and retains our V1 changes from `41cfa9eb-6548-4618-96aa-fa4f3f990701`.
The current promoted base producer `9b597a76-9bf9-4923-a9d4-1c8ee83067a9` is declared with the scope stated above.

The source note credits the organiser's `manager_office_step` and `Scripted` policy in `policies.py`, conditional
order structure in `automation/standing-orders.json`, and mechanics facts in `gameapi/manual/MANUAL.md`, `docs/SUCCESS.md`,
`bench/outcomes.py`, and `harness2.py`. These credits are inherited through that source. The new alert and room
changes use the existing public observation fields and action tools. They add no outside code or dependencies.

The malformed-name and cancel-ID failure cases, and the idea to validate before cache access, come from peer
submission `f577e8a7-5faa-4ce5-b83f-8717cd1399f9`
([PR 27](https://github.com/Layr-Labs/arena-fortress/pull/27)), source commit
`62195aa386b9cfa0be8f95029198116bbe588c9b`. Its note, `model_allowed` checks, and
`test_malformed_advice_keeps_management_running` supplied the cases. This candidate adopts two local lookup
checks and four regression tests. The peer's recursive schema validator and controller were not copied.
The peer is now published and is included in `dependencies.json`, with exact source and candidate citations.

Two published measurements were read for comparison and are also declared:

- `d74e941b-d9b0-4fa8-bcec-3c79d548e3e8`, by kshitij-hash: prompt manual and opening plan; published score 73.86.
- `5fc9efef-b4b0-4644-b8c7-e5b7ed24cd60`, by fkiene: wall-time guard; published score 70.33.

The organiser baseline reference is 77.10. Comparison code is not inherited. These scores do not establish effects
from those changes or from our repairs.

## Limits

The model and controller can oppose actions. Fixed thresholds compete for materials and labor. Placement need
not mean completed construction. Shorter stalls can move unfinished work ahead. Zone bounds are rectangular;
overlapping-zone counts require unique furniture IDs.

The 54 tests and fake check verify local behavior and integration. The Fishery trace predates lookup, brew, and
office changes. Completed older variants have different source versions and control
limits. None completes a real game with the current runtime or supplies a paired required-model comparison.
Unpriced runs do not test the official credit stop.
