# Hybrid Caretaker and State-Aware Model Overseer

## Summary and Motivation

This submission builds an integrated hybrid harness around the fixed hosted model (`z-ai/glm-5.3-flash`) and game API v0 for Yukon Arena: Fortress Season 0.

The baseline harness (`baseline/plain/`, scoring lower-bound 77.10 on the seasonal benchmark pool) operates strictly as a one-tool-per-turn agent with a 12-message history window. Analyzing the gated scoring equation:
$$O = 100 \cdot \frac{s_1 + s_1 s_2 + s_1 s_2 s_3 + s_1 s_2 s_3 s_4}{4}$$
reveals where the baseline leaves significant points on the table:
1. **The Housing Bottleneck ($s_4$):** Baseline $s_4$ achieves only 0.46. The growth sub-score measures placed beds per citizen and zoned dining seats per two citizens ($\min(\text{tables}, \text{chairs})$ inside a dining hall zone). A model acting one turn at a time frequently forgets to designate bedrooms/dormitories, zone dining rooms, and place furniture after orders complete. Raising housing from 0.46 toward 0.90+ unlocks substantial gains across long horizons and lab challenges such as LT08.
2. **Supply Drops in Hands-Off Windows ($s_2$):** In lab tasks (e.g., LT01 with a 21-day hands-off period, LT02 with 21 days) and late-game unmanaged runs, all model actions are barred. If the harness has not established standing daily repeat orders with stock conditions, drink and food decline, lowering $s_2$ and pulling down the entire product.
3. **Manager Validation Stalls:** In Dwarf Fortress, work orders stall when population reaches approximately 14–20 citizens unless the manager is assigned an office zone containing a built chair. The baseline has no mechanism to ensure this requirement is met proactively.
4. **Strange Moods & Insanity ($s_1$ / $s_3$):** An unfulfilled strange mood causes dwarf insanity after 50,000 ticks (~41.7 days), permanently zeroing or severely depressing wellbeing ($s_3$) and survival ($s_1$). Building the exact workshop matching the dwarf's skill and providing bone materials via animal slaughter resolves this risk.

To address these vulnerabilities without increasing credit spend, this harness implements a zero-credit deterministic Caretaker layer that performs foundational fortress maintenance once per game day, coupled with an advisory status digest and failure memory that guides the hosted language model.

---

## Architectural Changes

All modifications are confined strictly to `submission/`:

### 1. The Caretaker Maintenance Layer (`submission/plain/caretaker.py`)
Executed once per in-game day before the model turn, `Caretaker` evaluates visible public facts from `GET /observe` and executes rate-limited, idempotent actions through standard game tools (`POST /act`):
- **Management & Office:** If no manager is active, appoints an adult citizen with the highest organizer skill. When population reaches $\ge 14$ citizens or when `manager_needs_office` is flagged, ensures an office zone is created, assigned to the manager, and equipped with a built chair. Enables automation plugins (`autochop`, `seedwatch`, and `autofarm` once plots exist).
- **Core Production Workshops:** Checks for `Carpenters`, `Still`, and `Kitchen`. If missing and usable material (logs or boulders) is available, constructs them on available `W` sites.
- **Farming & Excavation:** If underground access is needed, designates stairs on an `S` site down 4 levels into soil. Designates underground soil rooms for farming (`R` sites) and constructs farm plots. Designates dedicated rooms for dormitories (`9x7`) and dining halls (`7x5`).
- **Standing Supply Orders:** Establishes conditional daily repeat orders (`repeat: "daily"`) for:
  - `brew_drink`: amount 3, when drink $< 300$, brewable plants $\ge 2$, empty barrels $\ge 1$.
  - `make_barrel`: amount 2, when empty barrels $< 6$, usable logs $\ge 2$.
  - `cook_meal`: amount 2, when prepared meals $< 200$, total plants $\ge 10$.
  - Fallback fruit brewing (`brew_drink_from_fruit`) when drink is low and standard plants are unavailable.
  These standing orders continue executing autonomously during hands-off windows.
- **Housing & Furniture Placement ($s_4$):**
  - Queues furniture crafting for beds (up to $\text{citizens} + 3$), dining tables (up to $\lceil\text{citizens}/2\rceil + 2$), and dining chairs (up to $\lceil\text{citizens}/2\rceil + 3$).
  - Zones the designated dormitory room as `dormitory` and the dining room as `dining_hall`.
  - Places built beds into the dormitory zone and matching tables and chairs into the dining hall zone.
- **Strange Mood Handling:** When an active strange mood appears in `observation.moods`, identifies the required workshop type from the dwarf's skill and constructs it immediately. If the demand includes bone, ensures a `Butchers` workshop exists and calls `slaughter` on a tame, unowned animal.
- **Defense & Alert Management:** Creates a 4-dwarf squad and equips leather armor once population reaches 14; designates a shelter burrow over the dormitory level. Triggers civilian alerts only when hostile invaders approach within 45 tiles of the wagon, and automatically rescinds alerts after threats clear or after 10 days to prevent civilian dehydration.

Every action in `Caretaker` is bounded by a rate-limiting cooldown (2–5 days between retries) and capped at 15 actions per day, leaving ample budget within the server's 40 actions/day limit for the model. Exceptions are caught internally so that unexpected observation shapes never interrupt the harness loop.

### 2. State Digest and Failure Memory (`submission/plain/digest.py`)
Interprets the raw observation into a structured `harness_status` object appended to the observation payload:
- Aggregates population, estimated days of remaining drink and edible food, usable logs, and empty barrels.
- Compares placed beds against total citizens, and placed dining seats against the required ratio ($\lceil\text{citizens}/2\rceil$).
- Reports active strange moods and required items.
- Maintains a rolling memory of the last 15 failed actions with their associated error codes (`order_churn`, `action_limit`, `bad_arguments`, etc.), giving the model explicit visibility into recent rejections to suppress unproductive retry loops.

### 3. Harness Loop Integration (`submission/plain/harness.py` & `submission/plain/prompt.py`)
- Detects in-game day changes and invokes `Caretaker.step()` before calling the model.
- Appends `harness_status` to the user message observation.
- Cleans and formats the system prompt to guide the model on fort status, operating priorities, and coordination with the automated maintenance layer.
- Retains existing safety guards: the order-churn guard, the 10-turn stall advance guard, context trimming on large prompts, and the 92% credit stop.

---

## Provenance and Attribution

This submission is based on the challenge repository's plain baseline (`submission/plain/` and `submission/dfbench_client/` at commit `75d40aa6adc8ee1b3f3b5ad1d74c3674f1ff3abf`).

In accordance with `RULES.md` §8 and `SUBMITTING.md` §3, the following published submissions are formally declared in `dependencies.json` and `submission/dependencies.json`:
1. **`6ad71ca7-3685-4d4b-8117-1bd6f63624df` (jungjipdo):**
   - *Rationale:* Introduced the concept of tracking recent failed actions and tool outcomes to prevent model churn.
   - *Evidence:* Implemented in `submission/plain/digest.py` and `submission/plain/harness.py`, which record failed action error codes and surface them in `harness_status`.
2. **`d74e941b-d9b0-4fa8-bcec-3c79d548e3e8` (kshitij-hash):**
   - *Rationale:* Informed the analysis of Dwarf Fortress production dependencies and manager order validation chains.
   - *Evidence:* Influenced the concise operating guidance in `submission/plain/prompt.py`.

Additional architectural concepts:
- The deterministic management procedures in `submission/plain/caretaker.py` (manager appointment, office setup, workshop and farming setup) are adapted from the repository's open reference policies in `policies.py` (`Scripted` and `manager_office_step`).
- Public discussions and candidate pull requests (notably e-man07's pending candidate PR on hybrid architectures) highlighted the value of running daily deterministic maintenance prior to model invocation.

---

## Local Verification and Testing

All verification was conducted using standard Python unit and integration testing without requiring proprietary game assets:
1. **Compilation Check:** All Python source files in `submission/plain/` and `submission/dfbench_client/` compiled cleanly under `py_compile` without warnings or syntax errors.
2. **Caretaker Unit Suite (`submission/tests/test_caretaker.py`):**
   - Verified manager appointment and automated plugin activation.
   - Verified workshop placement and standing conditional repeat order creation.
   - Verified strange mood detection and matching workshop construction.
   - Verified housing furniture placement and dormitory/dining hall zoning.
   - Verified state digest extraction, stock day estimations, and failure memory retention.
   - All 5 unit tests passed.
3. **End-to-End Integration Suite (`submission/tests/test_integration.py`):**
   - Simulated a multi-day game using the repository's `FakeGame` and `FakeModel` HTTP test doubles.
   - Verified that `Plain.run` executed the daily `Caretaker` maintenance pass, passed the enriched `harness_status` to the model, handled mock tool calls, advanced in-game days, and terminated cleanly upon game completion with exit reason `game_over`.
   - Test passed in 0.69 seconds.
4. **Dockerfile & Packaging Inspection:**
   - The container definition in `submission/Dockerfile` relies exclusively on the Python 3.12 standard library with no external unpinned dependencies.
   - Total uncompressed package size remains well within the 25 MiB upload threshold.

---

## Test Execution Commands

To reproduce the local verification suite:
```sh
export PYTHONPATH="submission:baseline"
python -m unittest discover submission/tests
```
