# Deterministic Supply Protection, Scaled Carpentry, and Layer-Only Fallback

## 1. Overview and Problem Analysis

This submission builds directly upon the current promoted leader harness, submission `5dfdcf15-9802-4fbf-a64f-9866323c1412` by GordoAR, merged to `main` at commit `1afa775bbd08645aa6f43dfe6ec76563cad8fa66`.

The leader harness established a strong score of 86.07 (point estimate 88.28; 95% confidence interval [86.07, 90.46]), driven by an effective hybrid architecture: a deterministic daily manager pass in `submission/overseer/` running before the raw tool-calling model loop in `submission/plain/`. This hybrid structure secures the opening tasks while saving model budget.

Detailed inspection of the leader's outcome breakdown (`survival: 0.97, supply: 0.92, wellbeing: 0.99, growth: 0.68`) and the recent contender submission `7662723d-6c2d-4b44-add3-fc22131d2261` (point estimate 90.94; lower bound 88.99; supply 0.97, growth 0.76) reveals three specific operational bottlenecks:

1. **Late-Game Supply Decline ($s_2$):** In `SCORING.md` and `bench/outcomes.py`, supply is scored as:
   $$s_2 = \min(\text{drink}, \text{food})\text{ of } 0.5 \times \text{coverage} + 0.5 \times \min(1, T / T^*)$$
   where $T^*$ is 336 days (one full year of sustained stock) and $T$ is the stock at horizon divided by the rate of decline over the final window $F$. In the leader harness, standing orders had static caps (`DRINK_CAP = 300`) and low barrel thresholds (`barrels_empty below 4`). For larger fortresses (20 to 50 citizens), daily consumption during winter or hands-off stretches causes a slight negative stock slope. Even a modest negative slope across a 300-drink buffer caps $T$ below 336, resulting in sub-optimal $s_2$ subscores.
2. **Carpentry and Furniture Bottlenecks ($s_4$):** When migrant waves arrive (common in migrant-surge scenarios and year-long embarks), population surges from 7 to 20-40 citizens. The leader harness relied on a single Carpenters workshop with fixed 8-bed batches. With barrels, tables, chairs, and beds competing for a single workbench, bed placement lagged behind population growth, depressing the housing component of $s_4$.
3. **Premature Unmanaged Abandonment:** When the 92% credit stop (`BUDGET_STOP`) was reached, or if the model experienced consecutive transient API gateway errors, the baseline harness simply exited (`sys.exit` / returning stats), leaving the fortress completely unmanaged for the remainder of the horizon. Without the deterministic layer continuing to advance time and execute daily maintenance, unmanaged forts risk late starvation, thirst, and defence failures.

---

## 2. Technical Modifications

### 2.1 Pre-Window and Endgame Supply Boost (`submission/overseer/harness.py`)
In `Overseer.load()`, the harness now captures the remaining game horizon (`days_left`) and hands-off window timing (`hands_off_in_days`) from the API observation envelope:
- When a hands-off window is near (`hands_off_in_days <= 14`) or the game enters its final scoring stretch (`days_left <= 42`), the controller triggers active supply protection:
  - If drink stock falls below a scaled threshold (`max(400, cit * 15)`), a dedicated brewing order (`o_brew_boost`) is queued with amount scaled to population (`max(3, min(10, ceil(cit / 4)))`), provided brewable plants ($\ge 2$) and empty barrels ($\ge 1$) are available.
  - If empty barrels fall below a safe reserve (`max(6, ceil(cit / 4))`), a dedicated barrel order (`o_barrel_boost`) is queued, preventing brewery stalls.

### 2.2 Scaled Carpentry and Bed Batch Delivery (`submission/overseer/harness.py`)
- **Second Workshop Construction:** In `Overseer.workshops()`, when population reaches or exceeds 20 citizens and building materials and workshop sites (`W`) are available, the overseer now constructs a second `Carpenters` workshop. This eliminates the bottleneck where barrels and furniture contend for a single workshop.
- **Dynamic Bed Order Batches:** In `Overseer.supply()`, bed order amounts now dynamically scale: when citizens reach 20 or more, bed orders are dispatched in batches of up to 16 (rather than 8), cutting the time required to furnish large migrant waves in half before hands-off periods begin.

### 2.3 Layer-Only Fallback (`submission/plain/harness.py`)
In `Plain.run()`, transitions that previously terminated harness management have been redirected to an autonomous fallback loop, `Plain.layer_only()`:
- Triggers: Reaching `BUDGET_STOP` (92% of model credit budget), catching `BudgetExhausted`, or encountering `MAX_API_STREAK` (5 consecutive model gateway errors).
- Execution: `layer_only()` repeatedly runs `Overseer.step(resp)` on each observed game day, executing manager appointments, standing orders, farm planting, furniture placement, and defence checks, then advances game days according to `Overseer.pace(resp)` (1 or 2 days).
- Zero Model Cost: The layer uses solely deterministic game API actions (`POST /act`) and makes no model calls, continuing until `HandsOff` or `GameOver` is encountered.

---

## 3. Provenance and Attribution Declarations

In full compliance with `RULES.md` §8 and `SUBMITTING.md` §3, all direct and ancestor dependencies are declared in `dependencies.json` and `submission/dependencies.json`:

1. **`5dfdcf15-9802-4fbf-a64f-9866323c1412` (GordoAR, promoted leader on `main` at `1afa775`):**
   - *Rationale:* Base harness for this submission. Directly inherits the deterministic daily Overseer controller, 4-turn stall pacing (`STALL_AFTER = 4`), alert timeout tracking, room zoning repairs, and protected brew order mechanics.
   - *Evidence:* Working tree originates from commit `1afa775bbd08645aa6f43dfe6ec76563cad8fa66`. Core controller in `submission/overseer/` and test suites `test_alert_timeout.py`, `test_fishery.py`, `test_office_chair_first.py`, `test_pacing.py`, `test_protect_brew.py`, `test_repairs.py`, `test_room_zones.py`, and `test_typed_arguments.py` are preserved from this base.
2. **`7662723d-6c2d-4b44-add3-fc22131d2261` (i34-9, contender band, official score 88.99):**
   - *Rationale:* Source of the pre-window supply boost concepts (`window_supply`, `endgame_supply`), scaled carpentry, and the layer-only fallback architecture.
   - *Evidence:* Implemented in `submission/overseer/harness.py` (`o_brew_boost`, `o_barrel_boost`, dual carpentry workshops, and batch scaling) and `submission/plain/harness.py` (`layer_only`). Verified in `submission/tests/test_endgame_and_fallback.py`.
3. **`6e775ed2-93b1-4d27-b591-6d3b4f3de8aa` (e-man07):**
   - *Rationale:* Foundational architecture of the daily deterministic overseer layer (manager appointment, office setup, workshop construction, room digging, standing orders, farming, and defence).
   - *Evidence:* Inherited via `5dfdcf15` and `7662723d`.
4. **`9b597a76-9bf9-4923-a9d4-1c8ee83067a9` (kshitij-hash):**
   - *Rationale:* Prior promoted leader base producer (commit `3ed866583d0cab5a7392701f02939d7e8707f1f4`).
   - *Evidence:* Ancestor base producer declared on `main`.
5. **`0bc9b753-d53c-4c1d-b23f-92e645821a02` (mpjunior92):**
   - *Rationale:* Concept of elevating brewing and barrel targets late in long runs to counteract unmanaged stock depletion.
   - *Evidence:* Informs the endgame supply condition thresholds in `submission/overseer/harness.py`.
6. **`f577e8a7-5faa-4ce5-b83f-8717cd1399f9` (0xplemonade):**
   - *Rationale:* Typed argument handling and safe lookup checks before cache access.
   - *Evidence:* Inherited from `5dfdcf15`; verified in `test_typed_arguments.py`.
7. **`41cfa9eb-6548-4618-96aa-fa4f3f990701` (GordoAR):**
   - *Rationale:* V1 hybrid repairs (site removal on build, room roles after ok, 4-turn stall pacing).
   - *Evidence:* Inherited from `5dfdcf15`; verified in `test_repairs.py`.
8. **`d74e941b-d9b0-4fa8-bcec-3c79d548e3e8` (kshitij-hash) & `5fc9efef-b4b0-4644-b8c7-e5b7ed24cd60` (fkiene):**
   - *Rationale:* Published benchmark reference scores (73.86 and 70.33) cited for historical comparative context.

---

## 4. Local Verification and Testing

Local testing was conducted using the standard Python test harness:

1. **Full Regression Suite:**
   All 54 inherited regression tests across 8 test suites pass without error:
   - `test_alert_timeout.py`: 8 tests verifying civilian alert duration, state synchronization, and retry intervals.
   - `test_fishery.py`: 5 tests verifying fishery construction triggers.
   - `test_office_chair_first.py`: 7 tests checking manager office setup and chair placement sequencing.
   - `test_pacing.py`: 5 tests verifying adaptive 1-day vs 2-day pacing based on pending designations and hostiles.
   - `test_protect_brew.py`: 9 tests confirming automatic daily brew orders cannot be cancelled by the model loop.
   - `test_repairs.py`: 7 tests covering workshop site removal, room role assignment, and idle counter resets.
   - `test_room_zones.py`: 9 tests verifying zone coverage over furniture.
   - `test_typed_arguments.py`: 4 tests validating rejection of non-string tool names and unhashable cancel IDs.

2. **New Dedicated Test Suite (`submission/tests/test_endgame_and_fallback.py`):**
   Four new unit tests verify the newly introduced mechanisms:
   - `test_pre_window_brew_and_barrel_boost`: Confirms that when `hands_off_in_days <= 14`, the overseer adds supplementary `o_brew_boost` and `o_barrel_boost` orders without duplicating existing standing orders.
   - `test_second_carpenters_when_cit_ge_20`: Confirms that when citizens $\ge 20$ and logs/sites are present, a second `Carpenters` workshop build action is dispatched.
   - `test_batch_beds_scaled_for_migrant_surge`: Confirms that bed order quantities scale to 16 when citizens $\ge 20$.
   - `test_layer_only_fallback_advances_to_completion`: Simulates budget exhaustion and verifies that `layer_only()` continues stepping the overseer, advancing time, and cleanly exits when `hands_off` or `GameOver` is reached.

3. **Compilation and Packaging Integrity:**
   - Executed `python -m compileall submission` cleanly with zero syntax errors or warnings.
   - Removed all `__pycache__` and bytecode artifacts.
   - Total test suite count: 58 tests passed in 0.014 seconds.
