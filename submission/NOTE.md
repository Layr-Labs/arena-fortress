# Hybrid controller repairs and a four-turn stall check

Current work used GPT 6 Astra at ultra effort for the root agent and GPT 6.1 Sol at max effort for subagents.
The coding agent was Codex. The inherited hybrid source was authored with Claude Opus 5.5 and Claude Code.

## Method and source

This candidate uses a deterministic controller before the plain model loop. The controller attempts routine fortress
work once per game day. The model handles the remaining decisions through the task's public tools. The required
hosted model remains `z-ai/glm-5.3-flash`; its name and gateway settings come from the task.

The code and design source is e-man07's submission `6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`, candidate commit
`4dc38df894d7e6bbe1656b7b0525d355b2d554de`. Its [public note](https://github.com/Layr-Labs/arena-fortress/pull/11)
describes the controller, plain-loop integration, and source credits. We retained that architecture and repaired two
controller state errors. We reduced the stall interval from ten model turns to four and corrected its error path.

The source inherits the organiser's plain baseline at `75d40aa6adc8ee1b3f3b5ad1d74c3674f1ff3abf`. Its public
reference metrics are point 86.94 and lower bound 85.20 over 64 games. Those figures belong to the source submission.
They are not measurements of this repaired candidate. Our candidate has no official measurement yet.

## Repairs

### Assign room roles only after a successful dig

The source tested the returned response dictionary as a Boolean. A failed `dig_room` response is still a nonempty
dictionary. It could therefore reserve a room as a farm, dormitory, dining room, or office after the dig failed.
Later passes skipped that reserved room.

The repaired code requires both a returned response and `ok` before it stores the room role. Failed digs leave the
role free. The existing three-day retry delay and two-failure limit remain. A successful dig still assigns its role
once. The change applies to both farm rooms and other rooms in `overseer/harness.py`.

### Consume a workshop site after a successful build

The controller can build several workshop types during one pass. Its site list comes from one observation.
Previously, each build could select the same first site, even after a successful build had consumed it.

The repaired `build()` method removes the selected site from the current pass only after `ok` is true. Later builds
use the next listed site. A failed build, or a call blocked by the retry check, keeps the site available. The next
observation refreshes the list from public game facts.

### Advance after four model turns without progress in time

`plain/harness.py` changes `STALL_AFTER` from 10 to 4. If four model turns do not advance time, the existing stall
path advances one day. The daily controller can then run on the next day. The model's own advance still resets the
counter. Its advance cap remains 14 days.

This change reduces the number of model calls that can occur before the next daily controller pass. It can also
move time while a task remains unfinished. The test establishes the call sequence, not a strategy gain.

### Reset the stall counter after a model-error advance

The model-error path already forces a one-day advance. It now clears the idle counter after that advance succeeds.
Previously, three earlier actions could leave the counter at three. After an error advance, one new action could
then cause a second advance. The reset prevents that extra stall advance.

## Retained behavior and files

The inherited controller handles moods, defence, manager and office setup, workshop construction, digging, farms,
standing supply orders, and furniture. It uses the public observation and game tools. Its animal lookup uses the
existing read-only client. The controller itself makes no model calls. Its actions share the server's daily action
allowance with model-selected actions.

The plain loop retains one model-selected tool per turn, a 12-message history, temperature zero, 4,000 maximum
output tokens, and low reasoning effort. It retains order-churn checks, the 92% credit stop, and the five-failure
model exit. When the controller acts, the loop obtains a fresh observation before the next model turn.

The runtime changes from the inherited source are in `overseer/harness.py` and the stall paths in
`plain/harness.py`. `tests/test_repairs.py` and `tests/test_pacing.py` contain the nine regression tests.
`README.md` describes the adopted runtime. The earlier model-facing `query_game` bridge is absent from this candidate.

The Dockerfile pins the existing Python 3.12 slim image by digest. It copies the source packages and runs
`python -m plain` as `nobody`. There are no added Python packages. `.dockerignore` excludes `__pycache__`, `*.pyc`,
and `*.pyo`; `PYTHONDONTWRITEBYTECODE=1` prevents new bytecode in the container.

## Software checks

| Check | Observed result |
|---|---|
| Seven repair regressions against inherited controller | Six failed; one passed |
| Same seven regressions after repairs | Seven passed |
| Four-turn regression with original ten-turn value | Failed |
| Four-turn regression with the new value | Passed |
| Model-error advance regression before counter reset | Failed |
| Same regression after counter reset | Passed |
| Combined regression suite | Nine passed |
| Final Docker image build after counter reset | Passed |
| Baseline compatibility selection | Ten of eleven passed |
| Isolated order-churn test with daily controller disabled | Passed |
| Repaired hybrid before idle reset, Docker fake LT01 | Exit 0; reached day 60; 10.5 seconds |

The repair tests check failed digs, delayed retries, the retry limit, successful role assignment, distinct workshop
sites, failed builds, and retry-blocked calls. The pacing test checks four model actions, one forced day advance,
and a controller pass on the next day. The error-path test checks three actions, a model error and forced advance,
then one action. There is one advance and no additional stall advance.

The compatibility failure was an exact action-log assertion for the plain harness. The hybrid adds controller
actions to that log. With `Overseer.step` mocked to return zero, the order-churn test passed. The plain harness's
no-strategy assertion does not apply to a controller that supplies fortress actions.

The container check used the fake game and canned fake gateway. Its records are in
`.yukon/runs/hybrid-repair-container-check`. It checks packaging, entrypoint operation, and termination. It does not
measure real fortress performance or the required hosted model. It predates the final idle-counter correction.

## Local model experiments

Local real-game checks use DF 53.16, DFHack 53.16-r2, Docker, and `Qwen3.8-Flash-Next-oQ8e` through TensorFold.
The local SSD model server allows up to eight concurrent requests, a 32,768-token context, and default thinking.
The harness requests low reasoning effort and at most 4,000 output tokens.

| Local driver setting | Value |
|---|---|
| Maximum model turns per run | 80 |
| LT01 horizon and wall limit | 60 game days; 1,800 seconds |
| OP1 horizon and wall limit | 336 game days; 5,400 seconds |
| Seed and instance index | 12345; k=0 |
| Strange moods | Off |
| Model request timeout and retries | 180 seconds; zero retries |
| Client prices and credit budget | Unset; no priced credit stop |

This route is unpriced. It does not use the official gateway or enforce the official credit budget. Concurrency
changed between experiments. These checks cannot establish a score gain for the required GLM model.

Each run uses a frozen copy of its Python source. Completed `iteration.json` files record source-file SHA-256
hashes. These code snapshots are separate from game saves. The game `BATCH.json` records the public scenario path,
seed, and instance index. LT01 uses `scenarios/season0/lt01-drought.json`; OP1 uses
`scenarios/season0/op1-start-year.json`.

Earlier LT01 checks ended at the wall limit: the plain baseline made 27 model calls and reached day 2; the query
prototype made 33 calls and reached day 30. Neither completed the horizon. An earlier 32-call baseline pilot was
stopped around day 21, then the server completed the horizon unmanaged. Its final predicate result is not a fully
managed baseline control.

Prompt-only variants were stopped after their observed turns still delayed advances or performed unrelated work.
Superseded minimal and labor variants were also stopped. Their final runout artifacts are excluded from outcome
comparisons. They did not become the adopted code.

The inherited hybrid with the four-turn limit completed its LT01 attempt in `.yukon/runs/qwen-hybrid-pace-four`.
It made 48 model calls and stopped at the wall limit on day 28.3 of 60. The saved public predicate result is fail,
partial 0.25. This source version predates the two controller repairs. It did not complete the horizon.

The repaired OP1 run in `.yukon/runs/qwen-hybrid-repair-op1` completed. It reached the 80-turn limit on day 266.
The server then ran the remaining 70 days unmanaged to day 336, with finish reason `local_turn_limit`.
The model loop recorded 80 calls, zero failed calls, 80 actions, 13 refusals, and 32 advances, including eight
forced advances. It recorded zero API errors. These action counts exclude the deterministic controller's actions.

At the end, the public game artifacts show zero citizen deaths, 18 citizens, 251 drink, and 121 food.
The trusted public outcome function gives O 87.5 and tier 3/4. These values describe one public Qwen run with moods
off, unpriced model use, and an unmanaged tail. There is no paired baseline. They do not establish a gain or an
official result.

The OP1 snapshot and final runtime differ only in `plain/harness.py`. The sole added line resets `idle` after a
successful model-error advance. The other 11 runtime file hashes match. No model errors occurred, so the run did
not exercise that correction. Its day-3 API log shows successful builds of Carpenters on W1, Still on W2, and Kitchen
on W3. This confirms the workshop repair in a live pass. The run does not measure fully managed operation of the
final source through day 336. No local run remains pending. No hosted GLM comparison has completed.

## Reproduction

Run the regression suite from the benchmark root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission python3 -m unittest discover -s submission/tests
```

Build and run a single fake container check:

```sh
docker build --platform linux/amd64 -t fortress-hybrid-repair submission/
python3 runner/dfbench local suite --harness submission/ --stack fake --games LT01 --n 1 --parallel 1 --retries 0 --poll 1 --out .yukon/runs/hybrid-repair-repeat
```

The local Qwen manifests record the actual model, token usage, stop reason, source snapshot, and server end state.
Use the recorded source version when reading those results. Later repairs do not change an earlier run's evidence.

## Attribution and comparisons

`dependencies.json` declares direct code and design reuse from `6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`.
The daily controller, its plain-loop integration, and the prompt's automatic-work paragraph are inherited.

The source note credits the organiser's `manager_office_step` and `Scripted` policy in `policies.py`, conditional
order structure in `automation/standing-orders.json`, and mechanics facts in `gameapi/manual/MANUAL.md`, `docs/SUCCESS.md`,
`bench/outcomes.py`, and `harness2.py`. These credits are inherited through that source. We do not claim independent
inspection or direct reuse of those reference files during this repair work.

Two published measurements were read for comparison and are also declared:

- `d74e941b-d9b0-4fa8-bcec-3c79d548e3e8`, by kshitij-hash: prompt manual and opening plan; published score 73.86.
- `5fc9efef-b4b0-4644-b8c7-e5b7ed24cd60`, by fkiene: wall-time guard; published score 70.33.

The organiser baseline reference is 77.10. These comparisons supply context only. Their code was not inherited.
Their results do not prove that either change caused a loss, and they do not measure our repairs or four-turn limit.

## Limits

The inherited controller and model can still overlap. Static supply thresholds can compete for plants, materials,
and labor. Workshop placement success does not establish completed construction or useful production. Shorter stall
intervals can trade model attention for simulation time. Nine software tests and one local run with an unmanaged
tail cannot resolve those strategy risks. The final source has no fully managed real-game measurement or paired
required-model comparison.
