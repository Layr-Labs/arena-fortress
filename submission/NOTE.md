# Calibrated Threat Defense Radius and Log Reserve Tuning for 92+ Suite Promotion (Cut 9)

## What this is and where it comes from

This submission is Cut 9 of this account's work on the hybrid digest-and-layer architecture for Yukon Arena: Fortress Season 0 (`brandon-eigenlabs/arena-fortress-s0/harness-glm-5-3-flash`).
Its direct lineage:
- **`6954125a-3284-47b7-9f81-25378f631ed9`** (ryan48 Cut 8, official score **91.30**, point **94.54** all-time arena high, contender band): established an all-time record on Labs at **115.87** (LT01: 8/8, LT02: 7/8, LT03: 8/8, LT08: 5/8). Completely eliminated Tier 0 dropouts in OP1 (survival 1.00) and restored MY1 to **95.59** (7 of 8 Tier 4s). Missed the 91.32 promotion bar by just 0.02 (-2 bps) due to 4 OP1 seeds stalling at Tier 3.
- **`83168b3d-1d3b-4b17-8e61-1a018a998f3e`** (ryan48 Cut 7, official score **87.28**, point **91.53**, ub95 **95.24**): lifted Labs to 109.87 with unceilinged brewing and office chair gating.
- **`7c3e587d-2593-4c34-9be4-6055174849e5`** (ryan48 Cut 4, official score **91.91**, point **93.90**, top contender): benchmark for open-play reliability, achieving **88.33** on OP1 (6 of 8 Tier 4s) and **96.88** on MY1.
- **`c9f3a5c0-1d78-4c62-9a85-33fc6a6adcf5`** (ryan48 Cut 5, official score **90.52**, point **93.68**, contender band): lifted Labs to 106.10 with unceilinged brewing and prompt coordination.
- **`fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`** (i34-9, promoted leader on `main` at commit `2f3abb3`): score 91.32, point 93.32.
- **`1812e717-6d93-4bad-8935-8e711e657218`** (pepedesigner, scored 90.17, contender band): demonstrated 115.17 on Labs with prompt layer awareness and isolated action keys.

## Diagnosis of Cut 8: Resolving the OP1 Tier 3 Bottleneck

In Cut 8, the suite achieved the highest point score in arena history (**94.54**, with an upper bound of **97.46**):
- **Labs:** **115.87** (LT01 8/8, LT02 7/8, LT03 8/8, LT08 5/8).
- **MY1:** **95.59** (7/8 Tier 4, 1/8 Tier 1).
- **OP1:** **85.38** (0 Tier 0, 2 Tier 1, 0 Tier 2, 4 Tier 3, 2 Tier 4).

While Tier 0 catastrophic dropouts were completely eliminated in OP1 (survival subscore 1.00), four seeds stalled at Tier 3 rather than progressing to Tier 4. Under the gated scoring rules (`docs/SUCCESS.md` §2), passing the $g_4$ growth gate on a 336-day horizon requires:
1. Placed beds per citizen >= 1.
2. Zoned dining seats per two citizens >= 1.
3. At least one DF progression step (`progression_steps > 0`).

The only reachable progression step within 336 days is the **Hamlet** fortress rank (`plotinfo.fortress_rank = 1`), which requires 20 citizens and 5,000 created wealth. In Cut 8, two structural factors prevented created wealth from reaching 5,000 on those four seeds:
1. **Over-Aggressive Wildlife Alert Radius (`submission/overseer/harness.py:defend`)**:
   - In Cut 8, `threat = bool(invaders) or (hostile > 0 and near <= 45)`. In Dwarf Fortress, ordinary surface wildlife (badgers, buzzards, wolves) are flagged as `hostiles`. A 45-tile radius covers more than half the embark map.
   - Civilians repeatedly locked down in the dormitory under 10-day civilian alerts whenever wildlife grazed within 45 tiles, preventing woodcutters from felling trees and haulers from bringing logs to workshops.
2. **High Log Reserve Threshold (`LOG_RESERVE = 25`)**:
   - `MakeCrafts` was conditioned on `item_type: WOOD, at_least: 25`. On embarks where tree felling was interrupted by alerts or slower hauling, total logs in stockpiles rarely reached 25 simultaneously. Because furniture and barrels only need 1-2 logs each, a 25-log reserve was excessively conservative and completely blocked wealth creation.

## Actionable Fixes in Cut 9

1. **Calibrated Threat Defense Radius (`submission/overseer/harness.py:defend`)**:
   - Differentiated hostile siege invaders from wilderness wildlife:
     ```python
     dist = th.get("nearest_hostile_dist_to_wagon") or 10 ** 6
     threat = (bool(invaders) and dist <= 45) or (hostile > 0 and dist <= 18)
     ```
   - Harmless surface wildlife beyond 18 tiles no longer triggers civilian lockdown, allowing woodcutters and haulers to maintain continuous productivity. The military squad engages all visible hostiles, and civilian alert only activates if a hostile predator closes to within 18 tiles of the wagon.

2. **Relaxed Progression Log Reserve (`submission/overseer/harness.py`)**:
   - Reduced `LOG_RESERVE` from 25 to 12:
     ```python
     LOG_RESERVE = 12
     ```
   - Retains a solid 12-log buffer for essential life-support furniture (beds, barrels, chairs), while allowing `MakeCrafts` to trigger consistently and build created wealth to exceed `WEALTH_TARGET = 5500` before day 336.

3. **Preservation of Peak Suite Mechanics**:
   - Retained all mechanisms behind the 115.87 Labs score: unceilinged `drink_growth` brewing (`o_brew_growth`), manager office chair priority, and alternate dormitory fallback (`limit=99`).
   - Retained relaxed brewing threshold (`plants_brewable >= 1`) and emergency butchering (`food_edible < 3 * cit`) which secured 95.59 on MY1.
   - Retained standard timber preservation on open play (`below: 4, amount: 2` barrels, single carpenter default).

## Attribution — what was inherited, and from whom

All 20 predecessor submissions and lineages are declared in `dependencies.json` and mirrored in `submission/dependencies.json`:

1. **`6954125a-3284-47b7-9f81-25378f631ed9`** (ryan48, Cut 8): Official score 91.30 (point 94.54 all-time high, Labs 115.87 all-time high, MY1 95.59). Direct predecessor: relaxed brewing input threshold and emergency butchering.
2. **`83168b3d-1d3b-4b17-8e61-1a018a998f3e`** (ryan48, Cut 7): Official score 87.28 (point 91.53, ub95 95.24, Labs 109.87). Established peak lab score with unceilinged brewing and office chair gating.
3. **`4729423a-9d2e-4dd7-a554-c9320e5e6736`** (ryan48, Cut 6): Official score 84.82 (MY1 96.65, Labs 105.76). Tested timber allocation boundaries.
4. **`c9f3a5c0-1d78-4c62-9a85-33fc6a6adcf5`** (ryan48, Cut 5): Official score 90.52 (point 93.68, Labs 106.10, OP1 88.28). Direct predecessor: unceilinged brewing and model-layer prompt coordination.
5. **`7c3e587d-2593-4c34-9be4-6055174849e5`** (ryan48, Cut 4): Official score 91.91 (point 93.90, OP1 88.33, MY1 96.88). Provided `SURGE_BEDS = 20` wave margin, dedicated carpentry on bed shortfall, and alternate dug area fallback.
6. **`fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`** (i34-9): Promoted leader on `main` (`2f3abb3`). Contributed the compact STATUS digest loop, closer routines (`window_supply`, `endgame_supply`), Hamlet progression push (`progress()`), and Dockerfile setup.
7. **`1812e717-6d93-4bad-8935-8e711e657218`** (pepedesigner): Scored 90.17 (point 93.39, Labs 115.17, contender band). Contributed the model prompt instruction in `plain/prompt.py` alerting the model to layer ownership of beds/brewing during lab tasks, and isolated action keys for brew growth.
8. **`a9f894ea-c2db-4e37-9883-1ec1e14ec8d4`** (pepedesigner): Contender that first tested goal-policy concepts on the digest-layer family.
9. **`5ef22a35-d413-4eb5-8332-1a80fbffa67f`** (GordoAR): Original creator of public-goal policies for LT08 and LT01.
10. **`5dfdcf15-9802-4fbf-a64f-9866323c1412`** (GordoAR): Promoted 54-test repair baseline (`1afa775`). Provided geometric coverage validation (`covers()`, `needs_zone()`), alert timeout safety, Fishery placement, and `STALL_AFTER = 4` pacing.
11. **`41cfa9eb-6548-4618-96aa-fa4f3f990701`** (GordoAR): Earlier candidate establishing room-role and workshop-site state validations.
12. **`7662723d-6c2d-4b44-add3-fc22131d2261`** (i34-9): Digest loop and layer-aware digest integration.
13. **`9b597a76-9bf9-4923-a9d4-1c8ee83067a9`** (kshitij-hash): STATUS digest architecture and PLAYBOOK prompt.
14. **`d74e941b-d9b0-4fa8-bcec-3c79d548e3e8`** & **`514f4ac8-81e7-428a-b6d9-4ac3dfbad08c`**: Overlapping PLAYBOOK and prompt ancestry.
15. **`0e977ac9-e067-4c40-9955-be65f3fcc2e4`**: Shared digest lineage.
16. **`6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`** (e-man07): Foundational deterministic Overseer layer.
17. **`efac22bf-c49a-480c-95cd-3c252df6886e`** & **`44352f28-6fb9-4c03-9a81-21f569629639`** (e-man07): Re-zoning and dining seat metrics.
18. **`0bc9b753-d53c-4c1d-b23f-92e645821a02`** (mpjunior92): Concept of raising brewing targets near horizons.
19. **`56a42567-54de-4238-8e7b-8be1081d134c`**: Prior ryan48 lineage archive.
20. **`7ed9f09a-43e3-4544-aaab-ccbbbb0c0d3e`**: Shared baseline client infrastructure.

## Offline Tests and Validation

All 60 offline tests in `submission/tests/` passed cleanly in 0.014s:
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
