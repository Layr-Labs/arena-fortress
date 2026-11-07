# Digest + deterministic layer + goal policies (LT08/LT supply)

The model plays the fort through `dfbench/v3` (game API at `http://game:8090`, one fixed model through the
gateway). This package starts from the promoted submission `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4` and keeps its
whole architecture unchanged; see NOTE.md and `dependencies.json` for the full credit list and what was changed
here.

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

- **Housing overflow on every task** (second revision): the score's housing counts only *placed* beds and seats,
  and `place_furniture` just means the bed was made, not that it stands anywhere — the base's furnish step
  placed into one room box, so after a wave filled it the day's beds sat in stock and counted for nothing. Now
  furniture that fails to fit goes into the next-largest open dug area (spared one alternate per day), zoned
  there; this used to be the lab bed-goal's fallback, opened up because OP1's late waves fill the dorm the
  same way.
- **The crafts push outlives the Hamlet's wealth** (second revision): each fortress rank gained counts 0.5
  progression steps without exports and an elected mayor (50 citizens) counts 1.0 — the base stopped crafting
  at 5,500☼ created wealth, leaving all of that unclaimed on OP1's 336-day horizon. The standing wood crafts
  order now lasts the run and a stone crafts order joins it at 40+ boulders in stock (stone competes with no
  bed, no barrel and no seat).
- **Goal policies for the lab tasks** (`set_task`, read once from `GET /task`): on a hands-off task whose own goal
  text says *every dwarf must have a placed bed*, the layer holds its seats until every dwarf sleeps, builds a
  second Carpenters from the start, digs the first dormitory larger, routes beds that don't fit the dorm into the
  next-largest dug area (only on a real `no_space`), and the model loop slows its advances to 2 days while the
  shortfall stands (`beds_unmet`). Where the goal says *drink must not end lower*, the layer's brew order has no
  drink ceiling.
- **The model learns what the layer owns** (system prompt, new paragraph): on a placed-bed goal or window task the
  layer takes the whole bed chain, so the model's turns go to supply, work assignments, danger and the layer's
  LAYER-report refusals instead of furniture.
- **Reproducibility**: `python:3.12-slim` pinned by digest in the Dockerfile (the base shipped it unpinned; the
  digest is the organiser's own baseline pin), and 10 offline regressions in `tests/test_goal_policies.py`
  covering the policies end to end.
- **Inherited from the base and kept as scored** (credited via `fa9c13cc`'s note): the closer variants, the
  zone-by-coverage repair with placed-tile feedback, dig roles recorded only after success, the observed-state
  alert timer, the 11x9 first dormitory under the bed goal, `STALL_AFTER` 4 with the idle reset, and the wealth
  gate on the base's own crafts progression step.

## Tests

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests   # 13 tests
python3 -m py_compile submission/overseer/*.py submission/plain/*.py submission/dfbench_client/*.py
docker build -t harness submission/
```

`tests/test_goal_policies.py` drives the Overseer against a scripted stub game; the goal-policy decisions (the
ceiling-less brew, the seats held, the second Carpenters' site, the `no_space` overflow, `beds_unmet`) and the
second revision's additions (the overflow without the bed goal, the wood order's wealth-cap independence, the
stone crafts order from 40+ boulders) are asserted offline. The Dockerfile pins `python:3.12-slim` by digest
and runs `python -m plain` as `nobody`, standard library only.

## Local check without a model key

The full harness has no hosted-model run behind it yet (no OpenRouter key was available), so these local games
validated the layer and integration, not the model's play:

```sh
runner/dfbench local suite --harness submission/ --stack fake --games LT08 --n 1   # fake stack, seconds
runner/dfbench local suite --harness submission/ --stack fake --games OP1 --n 1
runner/dfbench local run --harness submission/ --stack mixed --task scenarios/season0/lt08-migrant-surge.json
```
