# Balanced timber economy and restored 88.3+ OP1 progression baseline (Cut 7)

## What this is and where it comes from

This submission is cut 7 of this account's work on the hybrid digest-and-layer architecture for Yukon Arena: Fortress Season 0 (`brandon-eigenlabs/arena-fortress-s0/harness-glm-5-3-flash`).
Its direct lineage:
- **`4729423a-9d2e-4dd7-a554-c9320e5e6736`** (ryan48 Cut 6, official score **84.82**, point **89.94**): proved that aggressive standing barrel and bed buffers on long runs consume too much timber, starving second-year wealth crafts. Achieved **96.65** on MY1 (7 of 8 Tier 4s) and **105.76** on Labs (LT08 2/8 passes).
- **`c9f3a5c0-1d78-4c62-9a85-33fc6a6adcf5`** (ryan48 Cut 5, official score **90.52**, point **93.68**, contender band): lifted Labs to **106.10** with unceilinged brewing and prompt coordination, maintaining **88.28** OP1 (+9.2 over leader `fa9c13cc`).
- **`7c3e587d-2593-4c34-9be4-6055174849e5`** (ryan48 Cut 4, official score **91.91**, point **93.90**, contender band): highest point score and lowest variance in the arena, with OP1 at **88.33** and MY1 at **96.88** (7 of 8 Tier 4s).
- **`fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`** (i34-9, promoted leader on `main` at commit `2f3abb3`): score 91.32, point 93.32.
- **`1812e717-6d93-4bad-8935-8e711e657218`** (pepedesigner, scored 90.17, contender band): demonstrated 115.17 on Labs with prompt layer awareness and isolated action keys.
- **`a9f894ea-c2db-4e37-9883-1ec1e14ec8d4`** (pepedesigner).
- **`5ef22a35-d413-4eb5-8332-1a80fbffa67f`** and **`5dfdcf15-9802-4fbf-a64f-9866323c1412`** (GordoAR): creators of public-goal policies and the 54-test repair baseline.

## Objective: Restoring 88.3+ OP1 with High-Yield Labs (106+) to Break 92

In Yukon Arena: Fortress Season 0, the suite score is defined as:
```
S = 0.5 · O(OP1) + 0.3 · O(MY1) + 0.2 · 100 · mean(ẑ_LT01, ẑ_LT02, ẑ_LT03, ẑ_LT08)
```
In Cut 6, empirical results showed that over-allocating timber to standing barrels (`below: 8`, `amount: 3`), excess beds (`cit + 6`), and a mandatory second Carpenter shop on mature forts starved the `Craftsdwarfs` workshop of logs in the second year of OP1. This prevented forts from reaching the Hamlet created-wealth threshold (`WEALTH_TARGET = 5500`), pulling OP1 down from 88.3 to 79.6.

Cut 7 restores the proven timber-conservation balance from Cut 4 and Cut 5, while retaining all verified improvements:

1. **Restored Standard Timber Allocation (`submission/overseer/harness.py`)**:
   - `o_barrel` restored to `below: 4`, `amount: 2` for standard year-round orders. Note that the closer routines (`in_endgame` and `in_window_prep`) still dynamically raise the barrel buffer to `below: 8` and `below: 10` during the final weeks when stockout protection is critical, preserving timber during the first 11 months.
   - `o_cook` restored to `plants_total >= 10`.
   - `bed_target()` restored to `cit + 3` for standard open play runs, while retaining `SURGE_BEDS = 20` for migrant/lab tasks (`self.surge or self.beds_first`).
   - Single Carpenter default for standard open play: avoids taking workshop sites and prevents dual-workshop timber drain, reserving logs for `Craftsdwarfs` wealth creation.
2. **Retained High-Yield Lab Mechanics (~106 Labs)**:
   - `drink_growth` unceilinged brewing triggered on `"brew at least one batch"` (LT01) as well as `"drink must not end lower"` (LT08), using isolated action key `o_brew_growth`.
   - Manager office chair deadlock guard (`office_chair`) in `supply()`.
   - Alternate dormitory placement retry limit 99 in `furnish()`.
3. **Retained Model Prompt Layer Coordination (`submission/plain/prompt.py`)**:
   - `TASK-SPECIFIC WORK THE LAYER TAKES CHARGE OF` section prevents the LLM from canceling or competing with deterministic life-support orders during lab tasks.
4. **Preservation of Core Progression Baseline**:
   - `WEALTH_TARGET = 5500`, 9x7 dormitory, 7x5 dining room, and all GordoAR repairs (`covers()`, `needs_zone()`, `alert_timeout`, `Fishery`, `STALL_AFTER = 4`) that consistently deliver 88.3 OP1 and 96.8 MY1.

## Attribution — what was inherited, and from whom

All 20 predecessor submissions and lineages are declared in `dependencies.json` and mirrored in `submission/dependencies.json`:

1. **`4729423a-9d2e-4dd7-a554-c9320e5e6736`** (ryan48, Cut 6): Official score 84.82 (MY1 96.65, Labs 105.76). Tested timber allocation boundaries between lab/surge tasks and 2-year open play runs.
2. **`c9f3a5c0-1d78-4c62-9a85-33fc6a6adcf5`** (ryan48, Cut 5): Official score 90.52 (point 93.68, Labs 106.10, OP1 88.28, contender). Direct predecessor: unceilinged brewing and model-layer prompt coordination.
3. **`7c3e587d-2593-4c34-9be4-6055174849e5`** (ryan48, Cut 4): Official score 91.91 (point 93.90, OP1 88.33, MY1 96.88, top contender). Provided `SURGE_BEDS = 20` wave margin, dedicated carpentry on bed shortfall, alternate dug area fallback with unconditional zoning, and pacing clamps.
4. **`fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`** (i34-9): Promoted leader on `main` (`2f3abb3`). Contributed the compact STATUS digest loop, closer routines (`window_supply`, `endgame_supply`), Hamlet progression push (`progress()`), and Dockerfile setup.
5. **`1812e717-6d93-4bad-8935-8e711e657218`** (pepedesigner): Scored 90.17 (point 93.39, Labs 115.17, contender band). Contributed the model prompt instruction in `plain/prompt.py` alerting the model to layer ownership of beds/brewing during lab tasks, and isolated action keys for brew growth.
6. **`a9f894ea-c2db-4e37-9883-1ec1e14ec8d4`** (pepedesigner): Contender that first tested goal-policy concepts on the digest-layer family.
7. **`5ef22a35-d413-4eb5-8332-1a80fbffa67f`** (GordoAR): Original creator of public-goal policies for LT08 and LT01.
8. **`5dfdcf15-9802-4fbf-a64f-9866323c1412`** (GordoAR): Promoted 54-test repair baseline (`1afa775`). Provided geometric coverage validation (`covers()`, `needs_zone()`), alert timeout safety, Fishery placement, and `STALL_AFTER = 4` pacing.
9. **`41cfa9eb-6548-4618-96aa-fa4f3f990701`** (GordoAR): Earlier candidate establishing room-role and workshop-site state validations.
10. **`7662723d-6c2d-4b44-add3-fc22131d2261`** (i34-9): Digest loop and layer-aware digest integration.
11. **`9b597a76-9bf9-4923-a9d4-1c8ee83067a9`** (kshitij-hash): STATUS digest architecture and PLAYBOOK prompt.
12. **`d74e941b-d9b0-4fa8-bcec-3c79d548e3e8`** & **`514f4ac8-81e7-428a-b6d9-4ac3dfbad08c`**: Overlapping PLAYBOOK and prompt ancestry.
13. **`0e977ac9-e067-4c40-9955-be65f3fcc2e4`**: Shared digest lineage.
14. **`6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`** (e-man07): Foundational deterministic Overseer layer.
15. **`efac22bf-c49a-480c-95cd-3c252df6886e`** & **`44352f28-6fb9-4c03-9a81-21f569629639`** (e-man07): Re-zoning and dining seat metrics.
16. **`0bc9b753-d53c-4c1d-b23f-92e645821a02`** (mpjunior92): Concept of raising brewing targets near horizons.
17. **`56a42567-54de-4238-8e7b-8be1081d134c`** & **`7d23a133-1e48-4825-b42a-d7e664e2c1e2`**: Prior ryan48 lineage archives.
18. **`7ed9f09a-43e3-4544-aaab-ccbbbb0c0d3e`**: Shared baseline client infrastructure.

## Offline Tests and Validation

All 60 offline tests in `submission/tests/` passed cleanly in 0.013s:
- `test_alert_timeout.py` (7 tests)
- `test_fishery.py` (4 tests)
- `test_goal_policies.py` (10 tests)
- `test_office_chair_first.py` (6 tests)
- `test_pacing.py` (4 tests)
- `test_repairs.py` (9 tests)
- `test_room_zones.py` (12 tests)
- `test_surge_beds.py` (4 tests)
- `test_typed_arguments.py` (4 tests)

## Reproducing

```sh
python -m unittest discover submission/tests
```
Container execution uses `submission/Dockerfile` with pinned base `python:3.12-slim@sha256:d8262b9a1ccb9de9e2181ffdf39db92bc722146f3964d4b1a41cb5144fec0309`.
