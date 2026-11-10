# Housing capacity, batched furniture orders, and food-aware brewing

This is i34-9's promoted harness (`fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`) with six changes (and a conservative-digging revision) to the deterministic
layer in `overseer/harness.py`; see the submission note for the evidence and the credits (`dependencies.json`).

- **Housing capacity:** placements that find no free floor mark the area full; beds overflow to the next level with
  free floor (the expansion room or any dug level when no room has the dorm role); tables and chairs take only the
  floor the remaining beds don't need (none while beds are short on a migrant task); `expand()` digs one 9x7 room on
  an existing room site only on a migrant task or after floor has run out, never with water on the fort's levels and
  never a deeper staircase.
- **Furniture orders:** the whole bed shortfall in one order (up to 30; tables and chairs up to 15), beds first on a
  migrant task (GordoAR's `5ef22a35` idea), so the manager's validation wait is paid once.
- **Pre-window plant reserve:** sized to the food the rest of the run needs, not half a plant per citizen.
- **End-of-run brewing:** three tiered orders, so surplus brewing never drains the food the final stretch is scored on.
- **Manager's office:** never on a one-tile stair landing; an office that can't take a chair is replaced and
  reassigned, so orders keep being validated past 20 citizens.
- **Late food:** in the last 14 days of a long open run, while food is under 40 per citizen, slaughter a spare tame
  animal every few days (e-man07's `1e6cbe5e` idea as extended by mpjunior92's `07b5e1e3`).

Tests: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests` (the
inherited suite plus `tests/test_housing_capacity.py`).

---

The README of the base follows.

# Hybrid repairs, brew protection, and early office chairs

This uses e-man07's controller from `6e775ed2-93b1-4d27-b591-6d3b4f3de8aa` and our V1
`41cfa9eb-6548-4618-96aa-fa4f3f990701`. Added work covers alerts, zones, lookup checks from peer PR 27, Fishery
support, and controller brew protection. See [NOTE.md](NOTE.md) for credits, evidence, and experiment limits.
The current promoted base is `9b597a76-9bf9-4923-a9d4-1c8ee83067a9`; its source credit is also declared.

## Operation

On each new observed game day, the controller handles routine management, defence, supply, farms, rooms, and
furniture. It makes no model calls. The model then receives the current facts and recent history. The harness runs
its first tool call. Controller and model actions share the game's daily allowance.

The model loop keeps a 12-message history, temperature 0, low effort, and 4,000 maximum output tokens. It advances
a day after four model turns without a time advance. Model advances are capped at 14 days. The 92% credit stop,
five-failure exit, and order-churn checks remain.

## Repairs

- Store a room role only after a successful dig.
- Remove a workshop site from the pass only after a successful build.
- Clear the stall counter after a successful model-error advance.
- Record successful controller daily brew IDs. Refuse model cancellation of those integer IDs as `order_churn`.
  Other orders keep their existing paths.
- Start a missing alert timer from the observed state. Failed alert actions do not change it.
- Place one available chair in a new office immediately after successful zone creation.
- After core workshops, attempt a missing Fishery when a dwarf's job is `Fish`. A planned Fishery prevents
  another build.
- Reject nonstring tool names before set lookup. Send list/dictionary cancel IDs to normal API rejection.
  Other hashable-ID behavior, including `7.0`, is unchanged.
- Skip small stair areas. Place furniture first, then use successful returned coordinates and existing furniture
  to check coverage. Add a zone only for uncovered items. Failed or retry-blocked placement creates no empty zone.
  The check adds no observation call.

Old overlapping zones remain because the API cannot delete them. Use unique furniture IDs for physical dining
counts. Farm logic is unchanged. Catalog, bins, capacity, and one-day pacing variants remain outside this runtime.

## Checks

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests
docker build --platform linux/amd64 -t fortress-room-alert submission/
```

All 54 tests pass. The current fake check in `.yukon/runs/office-chair-container-check` exited 0 at hands-off
day 39; the server reached day 60, with no OOM, crash, or wall cap. It used toy facts and a canned model.
The package uses pinned Python 3.12 and `USER nobody`.

Isolated pace-one LT08 reached day 60 but failed its goal (partial 0.8677). The bed-batch trial never exercised its
changed cap. Early-bins O 89.1 includes 129 unmanaged days and has no causal proof. None is adopted or measures
the current runtime. See NOTE for exact source and control limits; all local Qwen results are unpriced.
