# Public-facts diagnostics and recoverable failure memory

## Objective and current status

This candidate improves the information and action-feedback loop around the fixed Fortress model. It retains the plain harness's raw observations, model choice from the task, one action per turn, metered model client and run guards. It adds bounded public-facts advice, memory of recent deterministic tool failures, and a model-selected read-only inspection tool. The hypothesis is that less repeated guessing and better verification of production prerequisites will improve fortress stability before the hands-off period and over long runs.

This is a development candidate, not a measured score improvement. No real Dwarf Fortress game or paid hosted-model game has run in this environment. No Yukon submission has been made. Twenty-six local unit/integration tests passed, including the existing project HTTP-fake whole-game and subprocess-entrypoint tests run against the candidate. Those tests verify software behavior, not DF strategy or hidden-fort performance. The public baseline score is contextual reference only, not a local control measurement for this candidate.

## Starting point and provenance

The starting checkout is `Layr-Labs/arena-fortress` main commit `75d40aa6adc8ee1b3f3b5ad1d74c3674f1ff3abf`, cloned for `brandon-eigenlabs/arena-fortress-s0/harness-glm-5-3-flash`. The checkout's commit description says that `submission/` is reset to the organisers' plain baseline. There was no contenders branch returned by the remote branch lookup. The visible submission list at investigation time contained one rejected entry and three validating entries, not a promoted replacement to restore. The organisers' `baseline/plain/` and `baseline/dfbench_client/` are the inherited code, with the unchanged client copied into `submission/` by the checkout.

Before changes, the challenge README, submitting contract, rules, scoring specification, public API documentation and public game manual were read. The public manual supplies the facts about manager validation, office requirements, brewing inputs, crop/seed sustainability, placed furniture and read-only queries. No private forts, hidden scorer inputs, task-pool data or reference-policy artifacts were used.

The published note for submission `6ad71ca7-3685-4d4b-8117-1bd6f63624df` was read, together with its declared dependency list, which was empty. That note describes periodic jobs/orders/stocks query context and recommends investigation of production bottlenecks. This informed the decision to expose public inspection and persistent diagnostic context. No files were restored from that submission, and no implementation was copied from it. Unlike its described fixed every-fourth-turn querying, this candidate exposes a query tool selected by the model when useful. That material design input is declared in `submission/dependencies.json`. The ordinary game facts themselves are also independently documented in the common public manual. The candidate has no promoted-submission ancestor beyond the organisers' baseline known from this checkout.

A read-only second review examined the proposed public-facts diagnostic contract and identified important caveats: manager office observations may be the string `none`; a planned Still is not a built Still; short-interval stock trends are not forecasts; planned furniture cannot establish housing; overlapping zones cannot multiply seats; missing or failed observation sections must remain unknown. These caveats are reflected in the implementation and tests.

## Implementation

### Advisory state from public observations

`plain/advisor.py` consumes the same public observation that is sent to the model. It neither reads game files nor calls endpoints. The original observation stays present and a separate `harness_status` field carries derived, explicitly advisory information. Missing/error sections are not replaced with invented zeros. Estimates are not represented as scores.

The status highlights observed manager/validation prerequisites, incomplete brewing construction, missing brewable plants or barrels, disabled labor/crop/material automation, lack of listed farms and the approaching hands-off period. Office advice is conditional and says that validation may require the assigned built-chair office around twenty citizens; it does not assert a universal DF rule or diagnose all pending orders as stuck. Fruit brewing is noted as an alternative to plant brewing where the tools and available inputs support it. Raw observations remain authoritative.

Stock sampling is limited to sixteen snapshots. Same-tick observations replace the current sample rather than destroying the previous distinct-time sample, so repeated model turns do not erase the latest drink/edible-food trend. Clock rollback clears the samples. Net changes are reported with their interval; a declining net rate gets a rough stock/rate estimate with an explicit warning that it is not a future guarantee. Migration, batch production, hauling and changed demand make short-interval extrapolation unreliable.

Housing uses built furniture, not the number of bed items in stock. When the furniture listing is truncated, the candidate does not claim a complete bed shortfall. Dining tables/chairs are unioned by building id across dining zones so overlapping zones do not multiply them. Their minimum is labeled only an upper bound on seats because adjacency is not established by that calculation. Dug soil rooms are distinguished from merely designated rooms. The status caps displayed ids/advice and recent failure summaries.

### Recoverable failed-action memory

The advisor retains at most eight deterministic tool refusals with the original tool, arguments, tick and a bounded error message. These failures remain available even after conversation trimming. A local duplicate guard applies only to an identical failed action when its tick, public-observation fingerprint and successful-action epoch all remain unchanged. Any changed public facts, time movement or successful prerequisite action permits retry. This is intentionally conservative: it prevents only retries for which the harness has seen no progress, not all actions that resemble an old failure.

Only allowlisted deterministic game-tool error codes enter the guard. Server/provider/transient errors, read-only inspections, action-limit handling and time advances do not get suppressed. The existing order-churn guard remains separate. Local refusal includes the original error and asks the model to change prerequisites/arguments or allow time to pass. It does not choose the next game action.

### Read-only inspection available to the model

`plain/inspect.py` adds `inspect_fort` only for supported public query names advertised by `/task`. The static allowlist is the documented stocks, units, jobs, orders, buildings, zones, map, manager-order-types and workshop-types surface; the actual offered enum is the intersection with advertised capabilities. Query-specific arguments and basic types are validated. There is no arbitrary URL, file or endpoint facility. Inspection calls `GameClient.query`, never `GameClient.act`, and never increments the successful-prerequisite epoch.

Small query responses are returned intact. Large replies become valid JSON with an explicit truncation notice, preserved numeric totals where present, and a bounded JSON-text preview. The model is told to narrow filters or limits rather than treating a preview as a complete result. Querying still consumes a model turn and the existing stall guard remains active, so unproductive inspection cannot indefinitely freeze game time. This implementation is not a structured compression of every possible query result; large nested map/type replies can require more focused follow-up.

### Prompt, integration and image

`plain/harness.py` attaches status to each observation, installs the synthetic tool when supported, routes read-only calls separately, and records only real deterministic action refusals for duplicate suppression. The existing model client, budget stop at 92%, maximum advance of fourteen days, order-churn rules, context trimming, action-limit handling and hands-off behavior are retained. The harness never changes the task-provided hosted model name or gateway URL.

`plain/prompt.py` adds a concise public-manual-based operating checklist. It prioritizes the current task and survival/production over a rigid scripted opening, emphasizes built rather than planned infrastructure, sustainable seed routes, verification after a short wait and appropriate response to visible threats/moods. It explains both advisory status and inspection. The model continues to select game actions; no fixed farm, site, dwarf or order ids are hard-coded.

`Dockerfile` pins the Linux amd64 Python 3.12.16 slim-trixie manifest to `sha256:05a994d2344eb364cc186910f4fc8786a38215f39f00d0acc25bff33a08f4177`, obtained from the public registry's `python:3.12-slim` image inspection. The image remains stdlib-only, runs as nobody and keeps the original module entrypoint. There are no new third-party Python packages. Building the image itself is still pending due to the Docker access blocker.

## Verification and reproducibility

The newly authored advisor tests were run against the unmodified behavior first and failed because the candidate advisor was absent. Inspection tests were likewise run before the feature was wired and demonstrated the missing tool/routing. After implementation, the combined focused verifier passed all seventeen new regressions and nine existing project tests (eight `FullGame` cases plus the plain entrypoint case): 26 total in approximately 5.66 seconds.

Run from the benchmark root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission:baseline:submission/tests python3 - <<'PY'
import pathlib
import unittest
import plain.harness
root = pathlib.Path.cwd()
assert pathlib.Path(plain.harness.__file__).resolve() == root / 'submission/plain/harness.py'
from tests import test_plain
test_plain.BASE = str(root / 'submission')
suite = unittest.defaultTestLoader.discover(str(root / 'submission/tests'))
suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(test_plain.FullGame))
suite.addTest(test_plain.Entrypoint('test_plain_entrypoint'))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
PY
```

Preloading `plain.harness` and asserting its path ensures the inherited test helper cannot silently switch the implementation under test back to `baseline/`. The subprocess entrypoint test is explicitly pointed at `submission/`. The existing tests exercise actual local HTTP clients/fake servers, credit exhaustion and the near-budget stop, model timeout retry, action/time guards, order churn, hands-off termination and the module entrypoint. The added cases cover unknown data, built/planned/truncated furniture, room readiness, same-tick trend retention, time rollback, bounded memory, retry unlocking, original-error retention, query allowlisting, read-only routing, valid truncated JSON and status attachment in the real loop. `git diff --check` also passed after implementation.

## Unavailable measurements and next experiment

The environment is x86_64 Linux with sufficient memory and disk. However, Docker daemon access returned permission denied. `yukon setup --track harness-glm-5-3-flash` stopped with the explicit missing DF 53.16 archive diagnostic. The participant's DF 53.16 and DFHack 53.16-r2 downloads are needed in the setup download directory. No usable OpenRouter provider key was available to the configured local gateway. An unrelated provider-key environment variable is not a substitute for the required OpenRouter route, and no credential was copied into the submission.

Once those prerequisites are supplied, run setup and the free smoke game first. Then compare this candidate to the untouched baseline on the same public task seeds with the same required hosted model and multiple repetitions. Start with LT01/LT02/LT08 and MY1, inspect stock trajectories, validation delays, refused actions, completion costs and housing before expanding to OP1 and the full suite. Suggested commands are `yukon setup --track harness-glm-5-3-flash`, `python3 runner/dfbench local smoke`, `python3 runner/dfbench local suite --harness submission/ --games LT01 --n 1`, and `yukon run --track harness-glm-5-3-flash`. A single game is not evidence of a gain given the documented variance.

In particular, measure whether the extra system/status/query tokens outweigh any reduction in repeated failures. The guard saves game API attempts but does not refund an already-made model call. The failure cache is deliberately short, and successful actions can unlock an otherwise redundant retry. These limitations require real model/game comparison, not more fake-game score claims. No claim of improvement, promotion or contender status is made here.

All candidate modifications, tests, the note and dependency declaration are kept inside `submission/`, the only editable path. If eventually submitting this candidate, pass this note and dependency file directly from there; the CLI accepts file arguments without requiring root-level copies. Determine and supply the exact underlying coding-model identity separately from the coding-agent name before submission. No credentials or local environment files belong in the archive. For a new account, the first scored submission is stage 1 only and cannot promote; scarce submission quota should be reserved until the candidate has meaningful local comparison evidence.
