# Fortress Hardening: Threat Defense, Brewing Threshold, and Emergency Butchering (Cut 8)

## What this is and where it comes from

This submission is Cut 8 of this account's work on the hybrid digest-and-layer architecture for Yukon Arena: Fortress Season 0 (`brandon-eigenlabs/arena-fortress-s0/harness-glm-5-3-flash`).
Its direct lineage:
- **`83168b3d-1d3b-4b17-8e61-1a018a998f3e`** (ryan48 Cut 7, official score **87.28**, point **91.53**, ub95 **95.24**): established the all-time suite record on Labs at **109.87** (LT01: 8/8, LT02: 7/8, LT03: 7/8, LT08: 3/8). Revealed single-seed vulnerability to unflagged wilderness threats in OP1 and strict `plants_brewable >= 2` input gating in MY1.
- **`7c3e587d-2593-4c34-9be4-6055174849e5`** (ryan48 Cut 4, official score **91.91**, point **93.90**, top contender): highest overall point score in the arena, with OP1 at **88.33** and MY1 at **96.88** (7 of 8 Tier 4s).
- **`c9f3a5c0-1d78-4c62-9a85-33fc6a6adcf5`** (ryan48 Cut 5, official score **90.52**, point **93.68**, contender band): lifted Labs to **106.10** with unceilinged brewing and prompt coordination, maintaining **88.28** OP1 (+9.2 over leader `fa9c13cc`).
- **`4729423a-9d2e-4dd7-a554-c9320e5e6736`** (ryan48 Cut 6, official score **84.82**, point **89.94**): proved timber over-allocation bounds between lab/surge tasks and 2-year open play runs. Achieved **96.65** on MY1 and **105.76** on Labs.
- **`fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`** (i34-9, promoted leader on `main` at commit `2f3abb3`): score 91.32, point 93.32.
- **`1812e717-6d93-4bad-8935-8e711e657218`** (pepedesigner, scored 90.17, contender band): demonstrated 115.17 on Labs with prompt layer awareness and isolated action keys.
- **`5ef22a35-d413-4eb5-8332-1a80fbffa67f`** and **`5dfdcf15-9802-4fbf-a64f-9866323c1412`** (GordoAR): creators of public-goal policies and the 54-test repair baseline.

## Objective: Eliminating Single-Seed Dropouts to Consistently Score 92+

In Yukon Arena: Fortress Season 0, the suite score is defined as:
```
S = 0.5 · O(OP1) + 0.3 · O(MY1) + 0.2 · 100 · mean(ẑ_LT01, ẑ_LT02, ẑ_LT03, ẑ_LT08)
```
Where each open-play track aggregates across stochastic seeds. In Cut 7, the codebase achieved an extraordinary **109.87** on Labs, but suffered from two isolated seed dropouts in open play:
1. In OP1 (50% suite weight), 1 seed dropped to Tier 0 because an unflagged wilderness hostile approached the wagon. The prior defense logic only triggered civilian alerts when `invaders` was populated (`d(h).get("invader")`). Unflagged wild beasts killed civilians, dropping that single seed to 0 points and costing ~5.5 points on the suite score.
2. In MY1 (30% suite weight), 3 seeds dropped from Tier 4 to Tier 1 because the standing brew order required `plants_brewable >= 2`. In Dwarf Fortress, a brew job requires only 1 plant and 1 barrel. Waiting for 2 plants caused a transient drink outage when farming was tight, failing the $s_2$ survival gate.

Cut 8 resolves both vulnerabilities directly through targeted, deterministic life-support hardening:

1. **Comprehensive Threat Defense (`submission/overseer/harness.py:defend`)**:
   - Detects all hostile entities within 45 tiles of the wagon:
     ```python
     near = (th.get("nearest_hostile_dist_to_wagon") or 10 ** 6) <= 45
     threat = bool(invaders) or (hostile > 0 and near)
     if threat and not alert and any(d(b).get("civ_alert_burrow") for b in lst(bur.get("list"))):
         r = self.act("alert_on", "civilian_alert", {"on": True}, retry=20, limit=99)
         if r and r.get("ok"):
             self.alert_since = self.now
     ```
   - Automatically stands down alerts when threat clears or after 10 days to prevent dehydration (`too_long = self.alert_since is not None and self.now - self.alert_since > 10 * DAY`).

2. **Relaxed Brewing Input Threshold (`submission/overseer/harness.py:supply`)**:
   - Changed standing brew order condition from `plants_brewable >= 2` to `plants_brewable >= 1`:
     ```python
     when = [{"stock": "plants_brewable", "at_least": 1}, {"stock": "barrels_empty", "at_least": 1}]
     ```
   - Ensures brewing jobs trigger immediately when a single brewable crop is harvested, eliminating transient drink dropouts on slow-growing farm plots.

3. **Mid-Game Emergency Butchering (`submission/overseer/harness.py:supply`)**:
   - Added immediate food conversion when edible food reserves drop below 3 days of citizen consumption:
     ```python
     if (self.st.get("food_edible") or 0) < 3 * self.cit:
         self.butcher()
     ```
   - Prevents mid-game starvation drops before kitchen and farm production scale up.

4. **Retained Peak Lab Configurations (109.87 Labs)**:
   - `drink_growth` unceilinged brewing triggered on `"brew at least one batch"` (LT01) and `"drink must not end lower"` (LT08) using isolated action key `o_brew_growth`.
   - Manager office chair deadlock guard (`office_chair`) in `supply()`.
   - Alternate dormitory placement retry limit 99 in `furnish()`.
   - `SURGE_BEDS = 20` wave margin for migrant/lab tasks.

5. **Retained Balanced Timber Economy**:
   - Standard year-round orders: `o_barrel` below 4, amount 2; `o_cook` plants_total >= 10; `bed_target()` cit + 3.
   - Closer routines dynamically scale barrel buffers to 8/10 in endgame/window prep weeks.
   - Single Carpenter default for standard open play, reserving timber for `Craftsdwarfs` created-wealth milestones (`WEALTH_TARGET = 5500`).

## Attribution — what was inherited, and from whom

All 20 predecessor submissions and lineages are declared in `dependencies.json` and mirrored in `submission/dependencies.json`:

1. **`83168b3d-1d3b-4b17-8e61-1a018a998f3e`** (ryan48, Cut 7): Official score 87.28 (point 91.53, ub95 95.24, Labs 109.87 all-time suite record). Established peak lab score with unceilinged brewing, chair office gating, and alternate dormitory fallback.
2. **`4729423a-9d2e-4dd7-a554-c9320e5e6736`** (ryan48, Cut 6): Official score 84.82 (MY1 96.65, Labs 105.76). Tested timber allocation boundaries between lab/surge tasks and 2-year open play runs.
3. **`c9f3a5c0-1d78-4c62-9a85-33fc6a6adcf5`** (ryan48, Cut 5): Official score 90.52 (point 93.68, Labs 106.10, OP1 88.28, contender). Direct predecessor: unceilinged brewing and model-layer prompt coordination.
4. **`7c3e587d-2593-4c34-9be4-6055174849e5`** (ryan48, Cut 4): Official score 91.91 (point 93.90, OP1 88.33, MY1 96.88, top contender). Provided `SURGE_BEDS = 20` wave margin, dedicated carpentry on bed shortfall, alternate dug area fallback with unconditional zoning, and pacing clamps.
5. **`fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`** (i34-9): Promoted leader on `main` (`2f3abb3`). Contributed the compact STATUS digest loop, closer routines (`window_supply`, `endgame_supply`), Hamlet progression push (`progress()`), and Dockerfile setup.
6. **`1812e717-6d93-4bad-8935-8e711e657218`** (pepedesigner): Scored 90.17 (point 93.39, Labs 115.17, contender band). Contributed the model prompt instruction in `plain/prompt.py` alerting the model to layer ownership of beds/brewing during lab tasks, and isolated action keys for brew growth.
7. **`a9f894ea-c2db-4e37-9883-1ec1e14ec8d4`** (pepedesigner): Contender that first tested goal-policy concepts on the digest-layer family.
8. **`5ef22a35-d413-4eb5-8332-1a80fbffa67f`** (GordoAR): Original creator of public-goal policies for LT08 and LT01.
9. **`5dfdcf15-9802-4fbf-a64f-9866323c1412`** (GordoAR): Promoted 54-test repair baseline (`1afa775`). Provided geometric coverage validation (`covers()`, `needs_zone()`), alert timeout safety, Fishery placement, and `STALL_AFTER = 4` pacing.
10. **`41cfa9eb-6548-4618-96aa-fa4f3f990701`** (GordoAR): Earlier candidate establishing room-role and workshop-site state validations.
11. **`7662723d-6c2d-4b44-add3-fc22131d2261`** (i34-9): Digest loop and layer-aware digest integration.
12. **`9b597a76-9bf9-4923-a9d4-1c8ee83067a9`** (kshitij-hash): STATUS digest architecture and PLAYBOOK prompt.
13. **`d74e941b-d9b0-4fa8-bcec-3c79d548e3e8`** & **`514f4ac8-81e7-428a-b6d9-4ac3dfbad08c`**: Overlapping PLAYBOOK and prompt ancestry.
14. **`0e977ac9-e067-4c40-9955-be65f3fcc2e4`**: Shared digest lineage.
15. **`6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`** (e-man07): Foundational deterministic Overseer layer.
16. **`efac22bf-c49a-480c-95cd-3c252df6886e`** & **`44352f28-6fb9-4c03-9a81-21f569629639`** (e-man07): Re-zoning and dining seat metrics.
17. **`0bc9b753-d53c-4c1d-b23f-92e645821a02`** (mpjunior92): Concept of raising brewing targets near horizons.
18. **`56a42567-54de-4238-8e7b-8be1081d134c`**: Prior ryan48 lineage archive.
19. **`7ed9f09a-43e3-4544-aaab-ccbbbb0c0d3e`**: Shared baseline client infrastructure.
20. **`c9f3a5c0-1d78-4c62-9a85-33fc6a6adcf5`**: Cut 5 intermediate milestone.

## Offline Tests and Validation

All 60 offline tests in `submission/tests/` passed cleanly in 0.017s:
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
