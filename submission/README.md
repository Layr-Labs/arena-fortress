# Hybrid controller repairs and a four-turn stall check

This harness inherits e-man07's hybrid controller from submission `6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`.
It repairs room role assignment and workshop site reuse. It advances one day after four model turns without a time
advance, instead of ten. A forced advance after a model error resets that stall counter.

## Operation

1. Read the public game observation.
2. On a new game day, run the deterministic controller. It handles routine management, supply, farms, rooms,
   furniture, moods, and defence. If it acts, read the observation again.
3. Send the current observation and recent history to the task-provided model. Run its first tool call.
4. Apply the existing action, credit, order-churn, and model-failure checks. Advance one day after four model turns
   without an advance.

The controller makes no model calls. Its actions share the game's daily action allowance. The model retains one
selected tool per turn, a 12-message history, temperature zero, low reasoning effort, and 4,000 maximum output
tokens. Model advances remain capped at 14 days. The credit stop remains 92%.

## Repairs

- A room receives a role only after `dig_room` returns `ok`. Failed digs retain their retry delay and failure limit.
- A successful workshop build removes its site from the current pass. Failed or retry-blocked builds keep the site.
- The four-turn stall check lets the daily controller run sooner when the model does not advance time.
- A successful model-error advance clears the counter. Earlier idle turns cannot cause an immediate second advance.

| File | Purpose |
|---|---|
| `overseer/harness.py` | Inherited controller and two state repairs |
| `plain/harness.py` | Model loop, daily controller call, four-turn limit, and error-path counter reset |
| `plain/prompt.py` | Inherited prompt, including the controller's work list |
| `dfbench_client/` | Existing game and model clients |
| `tests/` | Seven controller repair tests and two pacing tests |
| `NOTE.md` | Evidence, limits, source credits, and experiment records |
| `dependencies.json` | Code reuse and measured comparison declarations |

The image uses a pinned Python 3.12 slim digest, standard-library code, and `USER nobody`. Its entrypoint is
`python -m plain`. The build excludes generated Python bytecode. The earlier `query_game` bridge is not included.

## Checks

From the benchmark root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests
docker build --platform linux/amd64 -t fortress-hybrid-repair submission/
```

Nine regressions pass, and the final Docker image builds. Before the final counter reset, a Docker fake LT01 check
exited 0 and reached day 60.

The local repaired OP1 run used 80 model calls through day 266. The server then ran 70 days unmanaged to day 336.
Its public outcome is O 87.5, tier 3/4, with zero citizen deaths. It is one unpriced Qwen run with moods off and no
paired baseline. Its source predates the counter reset. It does not establish a gain or fully managed operation
of the final source through day 336. No local run remains pending.

The inherited hybrid with the four-turn limit stopped at the LT01 wall limit after 48 model calls, on day 28.3
of 60. Its public predicate failed with partial 0.25. That version predates the two controller repairs.
Local Qwen runs have an 80-turn limit, with 1,800 seconds for LT01 and 5,400 seconds for OP1. They are unpriced
and do not measure the required hosted GLM model. See `NOTE.md` for source snapshots, limits, and inherited credits.
