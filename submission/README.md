# Digest + deterministic layer + goal policies (LT08/LT supply)

The model plays the fort through `dfbench/v3` (game API at `http://game:8090`, one fixed model through the
gateway). This package starts from submission `7662723d-6c2d-4b44-add3-fc22131d2261` and keeps its whole
architecture; see NOTE.md and `dependencies.json` for the full credit list and what was changed here.

## Operation

Each game day, before the model loop's first turn:

1. **The deterministic layer** (`overseer/harness.py` `Overseer.step`) reads the observation and runs the day's
   mechanical work through the public tools (no model calls, no credits): manager and office, automation plugins,
   Carpenters/Still/Kitchen and (on the observed job) a Fishery, stairs and rooms, farm plots, standing orders for
   drink/barrels/meals/beds/tables/chairs, placement into the dormitory and dining zones, the shelter burrow and
   squad, the workshop a strange mood asks for, and the closer (endgame supply, pre-window boost, a housing check).
2. **The model** then receives a STATUS digest (what is low, what is stuck and why, what the layer did), the
   compacted raw observation, its memory of recent failed actions, and calls one tool per turn.

## This build's additions

- **Goal policies for the lab tasks** (`set_task`, read once from `GET /task`): on a hands-off task whose own goal
  text says *every dwarf must have a placed bed*, the layer holds its seats until every dwarf sleeps, builds a
  second Carpenters from the start, routes beds that don't fit the dorm into the next-largest dug area (only on a
  real `no_space`), and the model loop slows its advances to 2 days while the shortfall stands (`beds_unmet`). Where
  the goal says *drink must not end lower*, the layer's brew order has no drink ceiling.
- **A growth push for open runs** (`progression_push`): from 25 citizens and mid-run with spare logs, a daily wood
  crafts order (Craftsdwarfs) builds created wealth for the score's progression steps and a larger migrant wave.
- **Workshop site occupancy** is remembered after a successful build, so a second workshop of one type takes the
  next site.
- **Robustness:** non-string tool names and non-hashable cancel ids are rejected locally instead of reaching a set
  lookup (the failure cases are credited to peer submission `f577e8a7`).

## Tests

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests   # 10 tests
python3 -m py_compile submission/overseer/*.py submission/plain/*.py submission/dfbench_client/*.py
docker build --platform linux/amd64 -t harness submission/
```

`tests/test_goal_policies.py` drives the Overseer against a scripted stub game; the goal-policy decisions (the
ceiling-less brew, the seats held, the second Carpenters' site, the `no_space` fallback, `beds_unmet`) are asserted
offline. The Dockerfile pins `python:3.12-slim` by digest and runs `python -m plain` as `nobody`, standard library
only.

## Local check without a model key

The full harness has no hosted-model run behind it yet (no OpenRouter key was available), so these local games
validated the layer and integration, not the model's play:

```sh
runner/dfbench local suite --harness submission/ --stack fake --games LT08 --n 1   # fake stack, seconds
runner/dfbench local run --harness submission/ --stack mixed --task scenarios/season0/lt08-migrant-surge.json
```
