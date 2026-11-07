# Hybrid repairs and public-goal policies

## Scope and status

This package retains the 106-test public-goal source and adds six tests for a larger first dormitory dig. All 112 software tests pass. Its fake LT08 container check completed without a harness failure. This source also passed one full local LT08 game. This 112-test source has no official game result.

Local game results below use DF 53.16, DFHack 53.16-r2, and `Qwen3.8-Flash-Next-oQ8e` through TensorFold on public seed 12345, instance 0, with moods off. The route is unpriced and does not enforce the official credit budget. It uses a 32,768-token context, low reasoning effort, a 1,024-token thinking budget, and at most 4,000 output tokens. New LT08 trials allow 80 model calls and 1,800 seconds; the capacity/brew OP1 trial allows 160 calls and 5,400 seconds. These checks use different source versions and control times. They are not GLM comparisons and do not prove that one change caused a score.

## Source and credit

The controller, plain-loop integration, and automatic-work prompt come from e-man07's submission `6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`, commit `4dc38df894d7e6bbe1656b7b0525d355b2d554de` ([PR 11](https://github.com/Layr-Labs/arena-fortress/pull/11)). That source credits Claude Opus 5.5 and Claude Code.

This work retains our V1 submission `41cfa9eb-6548-4618-96aa-fa4f3f990701` ([PR 25](https://github.com/Layr-Labs/arena-fortress/pull/25)) and the later 54-test source `5dfdcf15-9802-4fbf-a64f-9866323c1412` ([PR 30](https://github.com/Layr-Labs/arena-fortress/pull/30)). The direct parent is our 106-test submission `5ef22a35-d413-4eb5-8332-1a80fbffa67f`, candidate commit `aa74a2874a952c4b85b074bc10123eecb35ceac1` ([PR 36](https://github.com/Layr-Labs/arena-fortress/pull/36)). It supplies the public-goal brew and bed policies, second Carpenter, alternate bed area, and two-day bed-progress checks. The current trusted base is our promoted 54-test submission `5dfdcf15-9802-4fbf-a64f-9866323c1412`, commit `1afa775bbd08645aa6f43dfe6ec76563cad8fa66`. The earlier promoted base `9b597a76-9bf9-4923-a9d4-1c8ee83067a9`, commit `3ed866583d0cab5a7392701f02939d7e8707f1f4`, was used during the parent version’s development. The five `dfbench_client` files and plain entry files are common organizer-baseline files. This package does not include the promoted source's STATUS digest, digest memory, compacted observation, or PLAYBOOK. It makes no digest-adoption claim.

The malformed-input cases and validate-before-cache idea came from `f577e8a7-5faa-4ce5-b83f-8717cd1399f9`, commit `62195aa386b9cfa0be8f95029198116bbe588c9b` ([PR 27](https://github.com/Layr-Labs/arena-fortress/pull/27)). This package uses two lookup checks and four tests. It does not copy that source's validator or controller.

The second-Carpenter idea cites `0bc9b753-d53c-4c1d-b23f-92e645821a02`, commit `719b05bae904f21b81a7d2350741e49cd1a7b9cc` ([caretaker.py, lines 88–95](https://github.com/Layr-Labs/arena-fortress/blob/719b05bae904f21b81a7d2350741e49cd1a7b9cc/submission/plain/caretaker.py#L88-L95)). That source scales workshop count with population. This package uses a fixed target of two Carpenters, only for the bed goal. The larger first-room design also draws on its [initial room digs, lines 108–119 and 130–144](https://github.com/Layr-Labs/arena-fortress/blob/719b05bae904f21b81a7d2350741e49cd1a7b9cc/submission/plain/caretaker.py#L108-L144). This package changes the bed-goal dormitory from 9 by 7 to 11 by 9. It does not copy the population formula, all caretaker policies, or a resize operation.

The current coding model is GPT 6.1 Sol. The coding agent is Codex. Earlier repair and public-goal work used GPT 6 Astra at ultra effort. Recent agent work used GPT 6.1 Sol at high effort or GPT 6 Luna at max effort.

Two published scores provide context only: `d74e941b-d9b0-4fa8-bcec-3c79d548e3e8` scored 73.86; `5fc9efef-b4b0-4644-b8c7-e5b7ed24cd60` scored 70.33. The organizer baseline is 77.10. This package copies no comparison code. These scores do not show the effect of its changes.

## Retained repairs

- **Room and workshop state:** Save a room role only after a successful dig. Keep a workshop site available after a failed build. Retain the three-day dig retry and two-failure limit.
- **Pacing:** Advance one day after four idle model turns, not ten. Clear the idle count after a successful advance that follows a model error. Model advances remain capped at 14 days.
- **Civilian alerts:** Start a missing timer from an observed active alert. Change timer state only after a successful action or an observation that confirms the alert is off. Keep the retry delays and clear after invader departure.
- **Furniture zones:** Require at least six open tiles in fallback A areas. Use successful placement coordinates and existing furniture to check room coverage. Use separate zones as needed. Partial placement can need a zone. A failed or retry-blocked placement does not create an empty zone. No extra observation call is added.
- **Lookup inputs:** Reject non-string tool names before set lookup. Let list and dictionary cancel IDs reach normal API rejection. Keep existing behavior for other hashable IDs.
- **Fishery:** Build a missing Fishery only when an observed dwarf's current job is `Fish`. A fisher profession alone is not enough. Existing and planned workshops and core-workshop site priority remain in effect.
- **Controller brew ownership:** Record returned integer IDs for successful daily brew orders, including ID zero. Refuse model cancellation of an owned integer ID locally. Failed adds and missing IDs claim no ownership. Missing or failed order probes do not clear ownership. An explicit public order list clears absent IDs. Other orders keep their existing paths.
- **Office chair:** After a successful office-zone action, place one available chair in the same pass. Keep the current assignment and retry rules.

The 54-test suite covers these repairs: `test_repairs` 7, `test_pacing` 2, `test_alert_timeout` 5, `test_room_zones` 17, `test_typed_arguments` 4, `test_fishery` 5, `test_protect_brew` 8, and `test_office_chair_first` 6.

## Public-goal policies

- **Drink growth:** Apply only when the task has a hands-off window and its goal contains “drink must not end lower.” Create the daily three-job brew order without the `drink < 300` condition. Keep the brewable-plant and empty-barrel conditions. Other tasks keep the drink ceiling.
- **Bed priority:** Apply only when the task has a hands-off window and its goal contains “every dwarf must have a placed bed.” Skip controller dining table and chair orders and dining-furniture placement. Keep the manager-office chair rule. Use one-turn stall pacing only for this goal; other tasks keep four-turn pacing.
- **Second Carpenter:** For the bed goal only, request a second Carpenters workshop if fewer than two are planned or built. Keep material, site, and retry checks. The first Carpenters, Still, Kitchen, and any needed Fishery use sites first.
- **Bed progress checks:** While the bed goal is active and observed placed beds are fewer than citizens, limit model-requested advances to two days. A requested one-day advance stays one day. Other tasks and a satisfied bed goal retain the 14-day limit. Preserve the requested stop conditions and invalid-input behavior.
- **Larger first dormitory:** For the bed goal only, the first dormitory-role dig requests 11 by 9 instead of 9 by 7. Other tasks keep 9 by 7. This adds 36 candidate tiles; it does not prove that all tiles are dry or free. The public site resolver rejects another `dig_room` on an already designated or dug R site. This policy makes the first rectangle larger; it does not resize a used room. Existing retry, role-commit, farm, dining, and office rules remain.
- **Bed fallback:** Try the primary dormitory area first. Use one alternate observed `A` area only after the primary bed placement returns actual `no_space`, and only when bed placement is not blocked by its retry or failure limit. Exclude the primary area; choose the alternate with the most open tiles, then site ID. Require six open tiles. Farm levels may qualify. Open-tile count selects an area; it does not prove bed capacity or limit the requested bed count. The API decides if placement succeeds. Do not try a third area. Use returned bed coordinates and existing beds to add a zone only when coverage is missing.

In the completed bed-first LT08 trace, primary A7 is at `(93, 91, 75)`, size `9×7`, with 63 open tiles. Bed placement returned `no_space` on days 36–38 while 3, 5, then 7 bed items were spare. Alternate A2 is at `(90, 86, 77)`, size `10×14`, with 85 open tiles. It is on the level of a stored `3×3` farm. The floor-only trial later accepted one bed on an A2 area of height eight. That does not prove capacity across the larger extension.

The offline fallback test uses a returned bed point `(91, 96, 77)` at A2. The existing A2 dormitory zone is `(90, 86, 77)`, size `10×8`; it ends at y=93 and does not cover that point. The test requires a new A2 dormitory zone. This is a fake response, not proof of live placement acceptance.

The parent added 52 tests: `test_beds_first` 8, `test_brew_growth` 6, `test_goal_pacing` 3, `test_two_carpenters` 7, `test_bed_fallback` 17, and `test_bed_checkpoints` 11. The checkpoint replay verifies controller passes on days 27 and 29 before the hands-off boundary. This version adds six `test_bed_room` tests. Two checks failed before the two-line room-size change. All 112 tests pass.

The 112-test source passed the fake LT08 container integration check: build success, harness exit 0 at day 39, server completion at day 60, and 12.8 seconds elapsed. It used toy game facts and a canned model. The tested image was `dfb-harness:2909c85ec22008d7`, digest `sha256:2909c85ec22008d7ab0c41b93f5b877f12615330b1a19c9b94d0983f6d151f26`. The fake lab predicate did not pass. This check verifies startup, API integration, and clean exit; it does not measure real-game performance.

Software checks from the benchmark root:

```sh
python3 -B -m unittest discover -s submission/tests
runner/dfbench local suite --harness submission/ --stack fake --games LT08 --n 1 --retries 0 --out runs/goal-fake
```

## Official predecessor results

The 54-test parent scored 86.07 over 64 official games, with point estimate 88.28. MY1 was O 80.6 and OP1 was O 87.2. LT08 passed 0/8, partial 0.89. Those results measure the 54-test source, before the public-goal policies.

The direct 106-test parent then scored 79.8 over 48 official games, with point estimate 87.25. It was not promoted because the current best remained 86.07. LT08 passed 7/8 with partial 0.99; LT02 passed 5/8 with partial 0.90. MY1 was O 81.1 over eight games; OP1 was O 80.4 over eight games. No run reached the wall or credit limit. These whole-source results have different game counts and do not identify the cause of a score difference.

## Completed local trials

| Trial source | Result | Limit |
|---|---|---|
| Larger first dormitory, current 112-test source | LT08 passed all four clauses at day 60: 54 built beds for 48 citizens, no deaths, supplies positive, drink 548 to 560. It used 38 model calls and 1,203 seconds. The native first dormitory dig accepted 11 by 9, with 98 tiles designated and one stair retained. | One unpriced public-seed Qwen game; no paired GLM comparison. The 106-test parent also passed its separate public case. No score gain is established. |
| Bed checkpoints, 106-test parent | LT08 passed all four clauses at day 60: 50 built beds for 48 citizens, no deaths, supplies positive, drink 539 to 556. It used 37 model calls and 1,231 seconds. | One unpriced public-seed Qwen game; no paired GLM comparison. |
| Bed-first, 63-test source; global one-turn pacing; before office-chair fix | LT08 reached day 60; partial result 0.984; 44 beds for 47 citizens; no deaths; supplies stayed positive; drink rose from 544 to 567. | Bed clause failed. It is not the combined 95-test result. |
| Combined 95-test source; before the two-day bed-gap limit | LT08 reached day 60 in 9 model calls; partial result 0.8696; 22 beds for 46 citizens; drink rose from 547 to 586. | A 14-day request at day 27 crossed into hands-off. Day 60 had 57 spare bed items. This motivates more controller checks. |
| Floor fallback, 88-test source | LT08 reached day 60; partial result 0.9457; 36 beds for 46 citizens; drink rose from 545 to 564. | The alternate API call placed one of two requested beds on day 37, then returned `no_space` on day 38. The full bed clause still failed. |
| Two-Carpenters, 78-test source | Wall cap at day 37.3; 51 placed beds and 16 spare bed items at the last full observation. | The run ended before day 39, so no full LT08 predicate is available. |
| Brew-growth, 55-test source; global one-turn pacing | 30 calls; wall cap at day 34.3. | Hands-off starts at day 39, so no valid LT08 predicate. |
| Fishery OP1, older source | Control ended at day 201; runout continued unmanaged to day 336. Local result O 58, tier 1; 19 citizens, 17 beds, 23 drinks, 29 food. | Late brew cause is unresolved. This does not isolate the Fishery effect. |
| Pace-one LT08, older 40-test source | Day 60; partial result 0.8677; 26 beds for 46 citizens; no deaths; supplies stayed positive; drink fell from 488 to 442. | Global fast pacing did not meet the full goal. |
| Bed-batch-30 LT08 | Wall cap at day 19.3. | Hands-off starts at day 39; changed bed cap was not used. |
| Other earlier local runs | Room-only O 86.7, early-bins O 89.1, manager-catalog O 85.6, and V1 O 87.5. | Different sources and unmanaged tails; no causal comparison. |

These trials use unpriced Qwen, seed 12345, instance 0, and moods off. They are not official GLM results. The full local pass is evidence for this public case and does not establish private-pool performance.
