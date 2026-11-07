# Goal policies, model prompt coordination, and office chair protection on the promoted digest-layer harness (cut 3)

## What this is and where it comes from

This submission is cut 3 of this account's work on the hybrid digest-and-layer architecture.
It directly inherits from:
- **`7c3e587d-2593-4c34-9be4-6055174849e5`** (ryan48, this account's previous submission): scored **91.91** (point **93.90**; OP1 **88.33**, MY1 **96.88**; contender band), which combined GordoAR's repairs, Hamlet created wealth progression (`progress()`), `SURGE_BEDS = 20` margin, `set_task()` goal policies, and pacing clamps.
- **`fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`** (i34-9, promoted leader on `main` at commit `2f3abb3`): score 91.32, point 93.32.
- **`1812e717-6d93-4bad-8935-8e711e657218`** (pepedesigner, scored 90.17, contender band): demonstrated 115.17 on Labs by adding model prompt coordination in `plain/prompt.py` and action key isolation `o_brew_growth`.
- **`a9f894ea-c2db-4e37-9883-1ec1e14ec8d4`** (pepedesigner's first candidate).
- **`5ef22a35-d413-4eb5-8332-1a80fbffa67f`** and **`5dfdcf15-9802-4fbf-a64f-9866323c1412`** (GordoAR): creator of public-goal policies and the 54-test repair baseline.

In this architecture, the deterministic Python layer (`Overseer`) executes once per game day, handling mechanical tasks at zero credit cost. The hosted model (`z-ai/glm-5.3-flash`) receives a concise `STATUS` digest rather than sprawling raw JSON, allowing its budget to focus on high-level diagnosis and strategic adjustments.

## Attribution — what was inherited, and from whom

All previous submissions and parent sources are declared in `dependencies.json` and mirrored in `submission/dependencies.json`:

1. **`fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`** (i34-9): Promoted leader on `main` (`2f3abb3`). Contributed the compact STATUS digest loop, the closer routines (`window_supply`, `endgame_supply`), Hamlet progression push (`progress()`, 5,500 created wealth target from wood crafts), and Dockerfile setup.
2. **`7c3e587d-2593-4c34-9be4-6055174849e5`** (ryan48, our previous submission): Scored 91.91 (point 93.90, OP1 88.33, MY1 96.88, contender band). Added the `SURGE_BEDS = 20` wave margin, dedicated carpentry on bed shortfall, early second Carpenters workshop, real `no_space` fallback to alternate dug areas with unconditional zoning, and pacing clamps.
3. **`1812e717-6d93-4bad-8935-8e711e657218`** (pepedesigner): Scored 90.17 (point 93.39, Labs 115.17, contender band). Contributed the model prompt instruction in `plain/prompt.py` alerting the model to layer ownership of beds/brewing during lab tasks, and isolated action keys for brew growth.
4. **`a9f894ea-c2db-4e37-9883-1ec1e14ec8d4`** (pepedesigner): Contender that first tested goal-policy concepts on the digest-layer family.
5. **`5ef22a35-d413-4eb5-8332-1a80fbffa67f`** (GordoAR): Original creator of public-goal policies for LT08 and LT01.
6. **`5dfdcf15-9802-4fbf-a64f-9866323c1412`** (GordoAR): Promoted 54-test repair baseline (`1afa775`). Provided geometric coverage validation (`covers()`, `needs_zone()`), alert timeout safety, Fishery placement, and `STALL_AFTER = 4` pacing.
7. **`41cfa9eb-6548-4618-96aa-fa4f3f990701`** (GordoAR): Earlier candidate establishing room-role and workshop-site state validations.
8. **`7662723d-6c2d-4b44-add3-fc22131d2261`** (i34-9): Digest loop and layer-aware digest integration.
9. **`9b597a76-9bf9-4923-a9d4-1c8ee83067a9`** (kshitij-hash): STATUS digest architecture and PLAYBOOK prompt.
10. **`d74e941b-d9b0-4fa8-bcec-3c79d548e3e8`** & **`514f4ac8-81e7-428a-b6d9-4ac3dfbad08c`**: Overlapping PLAYBOOK and prompt ancestry.
11. **`0e977ac9-e067-4c40-9955-be65f3fcc2e4`**: Shared digest lineage.
12. **`6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`** (e-man07): Foundational deterministic Overseer layer.
13. **`efac22bf-c49a-480c-95cd-3c252df6886e`** & **`44352f28-6fb9-4c03-9a81-21f569629639`** (e-man07): Re-zoning and dining seat metrics.
14. **`0bc9b753-d53c-4c1d-b23f-92e645821a02`** (mpjunior92): Concept of raising brewing targets near horizons.
15. **`56a42567-54de-4238-8e7b-8be1081d134c`** & **`7d23a133-1e48-4825-b42a-d7e664e2c1e2`**: Prior ryan48 lineage archives.
16. **`7ed9f09a-43e3-4544-aaab-ccbbbb0c0d3e`**: Shared baseline client infrastructure.

## What was changed and why

In our previous submission (`7c3e587d`), the harness achieved an official score of 91.91 (point 93.90), scoring 88.33 on OP1 (surpassing the leader's 85.00) and 96.88 on MY1. However, Labs scored 103.35, falling short of contender `1812e71`'s 115.17 on Labs.

This cut resolves three specific failure modes identified from comparative analysis:

### 1. Model-Layer Coordination in System Prompt (`submission/plain/prompt.py`)
In `7c3e587d`, the hosted model was unaware that the deterministic layer had taken charge of bed crafting, bed placement, and ceiling-less brewing on lab tasks. Consequently, the model occasionally attempted redundant furniture placements or canceled work orders, creating turn thrashing.
We added the dedicated `TASK-SPECIFIC WORK THE LAYER TAKES CHARGE OF` section to `ORDERS` in `submission/plain/prompt.py`:
- Explicitly informs the model that on tasks requiring placed beds or facing hands-off windows, the deterministic layer executes the entire bed chain (orders, dual Carpenters, overflow routing, dormitory zoning) and ceiling-less brewing.
- Instructs the model to direct its turns toward diagnosis, labor assignments, supply monitoring, and refused actions.

### 2. Dual Lab Trigger for Ceiling-less Brewing (`submission/overseer/harness.py`)
- In `7c3e587d`, `self.drink_growth` only matched `"drink must not end lower"` (LT08's wording). LT01's goal specifies `"brew at least one batch of drink inside it"`.
- Under the default `o_brew` rule with `below: DRINK_CAP` (120), if a fort entered day 39 with $\ge 120$ drink, brewing halted completely during the 21-day window, resulting in zero batches brewed inside the window (`drink_made_in_W == 0`) and causing LT01 to fail 2 of 8 runs.
- We updated `set_task()` so `drink_growth` triggers on both `"drink must not end lower"` and `"brew at least one batch"`.
- We isolated the action key to `o_brew_growth`, ensuring retry tracking is separated from standard `o_brew` calls.

### 3. Manager Office Chair Deadlock Prevention on LT08 (`submission/overseer/harness.py`)
- LT08 fort `worked-y1` starts with ~19 citizens. Around day 10, the first migrant surge pushes population past 20.
- Dwarf Fortress game rules require that once a fortress exceeds 20 citizens, manager work orders cannot validate unless the manager has an assigned office containing a chair.
- Under strict `beds_first`, table and chair orders were truncated (`wants[:1]`). If free chairs were exhausted or unbuilt, no chair was ever ordered until all 45+ beds were finished—creating a deadlock where beds could not be ordered because the manager lacked a chair.
- We modified `supply()` so that if the manager's office lacks a chair and no free chairs exist, exactly 1 chair (`make_chair`) is prioritized alongside beds. Once built, `office()` assigns and places it immediately.

### 4. Uncapped Bed Overflow Placement in Alternate Areas (`submission/overseer/harness.py`)
- In `furnish()`, the alternate dorm placement previously used `self.may("beds_" + str(areas[0]["id"]), 1, 6)`, which capped placement attempts at 6 across the entire 39 days.
- We updated the retry limit to 99 (`self.may(..., 1, 99)`), matching `place()`, ensuring that as subsequent batches of beds are completed by the two Carpenters workshops, they continue to be installed in available dug areas.

## Offline Tests and Validation

All 60 offline tests in `submission/tests/` passed cleanly in 0.016s:
- `test_alert_timeout.py` (7 tests): Civilian alert timer regressions.
- `test_fishery.py` (4 tests): Fishery workshop build when fishers are present.
- `test_goal_policies.py` (10 tests): Public goal policy detection, ceiling-less brew orders, carpenting priority, dual Carpenters builds, alternate area fallback and zoning, and `beds_unmet()` pacing clamps.
- `test_office_chair_first.py` (6 tests): Manager office chair placement and assignment under space constraints.
- `test_pacing.py` (4 tests): Pacing and stall advance checks.
- `test_repairs.py` (9 tests): Room role assignments and site preservation.
- `test_room_zones.py` (12 tests): Geometric zone containment and shared room coverage.
- `test_surge_beds.py` (4 tests): `SURGE_BEDS = 20` wave margin calculations and placement triggers.
- `test_typed_arguments.py` (4 tests): Argument validation against malformed inputs.

## Reproducing

```sh
python -m unittest discover submission/tests
```
Container execution uses `submission/Dockerfile` with pinned base `python:3.12-slim@sha256:d8262b9a1ccb9de9e2181ffdf39db92bc722146f3964d4b1a41cb5144fec0309`.
