# Dependency-based Fortress overseer

This submission adds a compact strategic prompt and one public-task-specific card to the organizer's plain baseline. The model still sees the live observation and calls exactly one native game action per turn. The harness does not add planner or critic model calls.

## Prompt structure

- `plain/prompts/overseer.txt`: common decision order, production prerequisites, sustainable supplies, built furniture, and time management.
- `plain/prompts/{OP1,MY1,LT01,LT02,LT03,LT08}.txt`: focused objectives selected from the explicit public task name or ID. Unknown tasks receive the common prompt.
- `plain/prompt.py`: prompt assembly and a compact observation guide. It retains section 4 of the live manual for site geometry. Its mood guide uses the current visible-demand fields instead of the obsolete availability fields in manual section 6.

The cards do not inspect seeds, private state, or evaluator files. Live server metadata takes precedence over startup metadata, as in the baseline. Advice about construction and production is conditional on observed state rather than a fixed sequence of coordinates or actions.

## Runtime

`python -m plain` reads `DFBENCH_TASK`. The organizer's stdlib `dfbench_client` handles the game API and model gateway. The Docker image pins Python 3.12 by digest and runs as an unprivileged user. There are no extra packages or build secrets.

The baseline loop and guards remain: one model call per turn, 12-message history, old-observation truncation, 14-day advance cap, automatic one-day progress after 10 stalled actions, daily action enforcement, recent-order churn protection, five consecutive model failures before exit, and a credit stop at 92% of the game's allowance. The server advances the fort unmanaged after the harness stops.

## Validation

From the repository root, run `python3 -m unittest discover -s submission/tests -v`. The tests cover all six task-card selections, fallback for unknown metadata, current mood-field guidance, native-tool execution through fake HTTP game/model services, live metadata precedence, advance and stall guards, order churn, hands-off termination, and packaged prompt discovery. These tests validate integration; they do not establish gameplay quality.

Build with `docker build -t fortress-overseer submission/`. Use the repository's public `runner/dfbench local smoke` and real-model local run commands for gameplay validation. The public submission note records the checks actually completed and their limitations.

## Provenance

Derived directly from the organizer's plain baseline at repository commit `1e86d20e3c87f322f522fa775de8f28ac2012fcd`. The new strategic prompts were written for this submission. `dependencies.json` explicitly declares no reused competitor submission.
