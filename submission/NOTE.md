# Public-facts diagnostics, failure memory and a sustainable standing guard

## Objective and current status

This candidate improves the information and action-feedback loop around the fixed Fortress model. The inherited version retained the plain harness's raw observations, task-provided model choice, one action per turn, metered client and run guards. The current iteration adds bounded batches and farm-capacity advice as documented below. It adds bounded public-facts advice, memory of recent deterministic tool failures, and a model-selected read-only inspection tool. The hypothesis is that less repeated guessing and better verification of production prerequisites will improve fortress stability before the hands-off period and over long runs.

This is a development candidate, not a measured score improvement. The initial version passed twenty-six local unit/integration tests and subsequently completed real DF smoke and one seven-day game with native Z.ai GLM-5.3-Flash. That game preceded the standing-guard changes described below. It ended at the horizon with harness exit 0, 25 successful model calls, zero provider errors/timeouts and $0.02140337 in reference-price token accounting. It used a local-only gateway image to translate the model name and reasoning field for the participant's configured Z.ai route, not the official pinned Together provider. It is therefore not an official-comparable score or a baseline comparison. An earlier candidate was submitted as `5faab6dc-f71f-4c7d-beb3-fc6bded39aa4`; no official result is claimed for the new military changes. The public baseline score is contextual reference only, not a local control measurement.

## Starting point and provenance

The starting checkout is `Layr-Labs/arena-fortress` main commit `75d40aa6adc8ee1b3f3b5ad1d74c3674f1ff3abf`, cloned for `brandon-eigenlabs/arena-fortress-s0/harness-glm-5-3-flash`. The checkout's commit description says that `submission/` is reset to the organisers' plain baseline. There was no contenders branch returned by the remote branch lookup. The visible submission list at investigation time contained one rejected entry and three validating entries, not a promoted replacement to restore. The organisers' `baseline/plain/` and `baseline/dfbench_client/` are the inherited code, with the unchanged client copied into `submission/` by the checkout.

Before changes, the challenge README, submitting contract, rules, scoring specification, public API documentation and public game manual were read. The public manual supplies the facts about manager validation, office requirements, brewing inputs, crop/seed sustainability, placed furniture and read-only queries. No private forts, hidden scorer inputs, task-pool data or reference-policy artifacts were used.

The published note for submission `6ad71ca7-3685-4d4b-8117-1bd6f63624df` was read, together with its declared dependency list, which was empty. That note describes periodic jobs/orders/stocks query context and recommends investigation of production bottlenecks. This informed the decision to expose public inspection and persistent diagnostic context. No files were restored from that submission, and no implementation was copied from it. Unlike its described fixed every-fourth-turn querying, this candidate exposes a query tool selected by the model when useful. That material design input is declared in `submission/dependencies.json`. The ordinary game facts themselves are also independently documented in the common public manual. The candidate has no promoted-submission ancestor beyond the organisers' baseline known from this checkout.

A read-only second review examined the proposed public-facts diagnostic contract and identified important caveats: manager office observations may be the string `none`; a planned Still is not a built Still; short-interval stock trends are not forecasts; planned furniture cannot establish housing; overlapping zones cannot multiply seats; missing or failed observation sections must remain unknown. These caveats are reflected in the implementation and tests.

The participant subsequently proposed an underground, happiness-focused fortress with armored defenders constantly training at the upper and lower stairheads, misted entrances, vertically separated social/farm/living/service levels and cavern fungus. This is the source of the standing military-readiness emphasis. The implemented change is deliberately narrower: the public API has one squad, equipment templates and attack/station/stand-down orders, but no training schedule, second squad, member removal, barracks designation, water machinery or full tavern/temple/pasture controls. A GLM-5.3-Flash consultation through AngelX helped identify worker and equipment risks; unsupported rotation, fictional training and incorrect stress interpretations were not adopted. Public manual and observation implementation checks confirmed that stress categories 0-1 are the most stressed and `military.armed` counts members carrying weapons.

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

`plain/harness.py` attaches status to each observation, installs the synthetic tool when supported, routes read-only calls separately, and records only real deterministic action refusals for duplicate suppression. The existing model client, budget stop at 92%, maximum advance of fourteen days, order-churn rules, action-limit handling and hands-off behavior are retained; the current iteration repairs context trimming for fresh batch groups. The harness never changes the task-provided hosted model name or gateway URL.

`plain/prompt.py` adds a concise public-manual-based operating checklist. It prioritizes the current task and survival/production over a rigid scripted opening, emphasizes built rather than planned infrastructure, sustainable seed routes, verification after a short wait and appropriate response to visible threats/moods. It explains both advisory status and inspection. The model continues to select game actions; no fixed farm, site, dwarf or order ids are hard-coded.

`Dockerfile` pins the Linux amd64 Python 3.12.16 slim-trixie manifest to `sha256:05a994d2344eb364cc186910f4fc8786a38215f39f00d0acc25bff33a08f4177`, obtained from the public registry's `python:3.12-slim` image inspection. The image remains stdlib-only, runs as nobody and keeps the original module entrypoint. There are no new third-party Python packages. Image builds and real-game execution now work with rootless Docker.

### Sustainable standing guard, not simulated training

The prompt adds a military doctrine only when the squad tools are offered. It favors a small equipped guard after essential supply is stable, with station orders at a revealed walkable choke facing the actual threat. One order cannot cover both stairheads simultaneously; the model must not bounce between two stations or open caverns to manufacture fights. Stationing is explicitly not training and no skill gains are asserted. Existing squads are not recreated, recruitment cannot be undone through the API, and stressed or labor-starved peacetime guards should stand down for recovery before resuming sustainable duty.

The pure public-facts advisor reports listed squads/members, the observed carried-weapon count, free weapons and at most ten eligible adult ids. Missing or failed sections stay unknown. It never infers worn armor or carried weapons from a uniform template or `weapon_assigned`. Its optional recruitment cap is at most four, bounded by observed free weapons and known eligible adults. It preserves seven civilians in peace or five during a visible threat, and at least five known adult workers outside squads. Children, officials, existing members, unknown eligibility and the most stressed dwarves are not suggested for recruitment. These are conservative heuristics rather than DF rules or commands; the model still must preserve essential professions and choose all actions. Visible-hostile advice precedes the bounded production checklist so emergency shelter is not truncated away. Doors and hatches also block citizens when locked.

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

Preloading `plain.harness` and asserting its path ensures the inherited test helper cannot silently switch the implementation under test back to `baseline/`. The subprocess entrypoint test is explicitly pointed at `submission/`. The existing tests exercise actual local HTTP clients/fake servers, credit exhaustion and the near-budget stop, model timeout retry, action/time guards, order churn, hands-off termination and the module entrypoint. The added cases cover unknown data, built/planned/truncated furniture, room readiness, same-tick trend retention, time rollback, bounded memory, retry unlocking, original-error retention, query allowlisting, read-only routing, valid truncated JSON and status attachment in the real loop.

After the military changes, this combined verifier passed all 38 tests. The twelve new readiness regressions were first run against the old advisor/prompt and failed for the missing behavior, then passed with the implementation. They cover peacetime founder preservation, limited growth recruitment, adult/position/member eligibility, weapon-limited emergency recruitment, carried-vs-assigned weapons, missing armed data, urgent advice surviving a full production checklist, peacetime stress relief, bounded immutable observations and tool-dependent prompt injection. A separate read-only GLM-5.3-Flash review found no blocking correctness issue.

The military candidate then completed a real DF public MY1 handover run using native Z.ai GLM-5.3-Flash, seed 2001, shortened to 14 days with a custom $0.05 local model cap and 900-second wall cap. It reached the horizon in 146 seconds with harness exit 0, 14 successful model calls, no refusals/provider errors/timeouts and $0.02184109 at reference token prices. All fifteen citizens survived. Observed drink changed from 328 to 319 and edible food from 30 to 27. Flash restored automation and standing food/drink orders, then furnished and assigned a manager office. The fort had zero free weapons at both the start and final observation, and no squad was created. This exercises the policy's restraint with missing equipment, not successful armed deployment, military skill growth or a score improvement. The custom short horizon/budget and native provider make it a developmental smoke measurement, not an official comparison. Run artifacts remain outside the submitted tree under `.yukon/runs/standing-guard-glm-flash-14d/`.

## Available local environment and remaining measurements

The initial Docker/download blockers were resolved: rootless Docker, participant-supplied DF 53.16 and DFHack 53.16-r2, all ten required public saves and official real-game fake-model smoke now work. The participant's existing native Z.ai key can exercise GLM-5.3-Flash locally through the explicitly labeled test gateway image described above. It is not interchangeable with an OpenRouter credential or evidence of provider equivalence. No key or test-gateway implementation is included in the submission.

Compare this candidate to the untouched baseline on the same public task seeds and provider with multiple repetitions. Start with LT01/LT02/LT08 and MY1, inspect stock trajectories, validation delays, refused actions, costs, housing, actual carried equipment and civilian labor before expanding to OP1 and the full suite. Measure the standing guard on a grown public fort, not just the seven-founder opening where the conservative peacetime cap is zero. Suggested standard commands are `python3 runner/dfbench local suite --harness submission/ --games LT01 --n 1` and `yukon run --track harness-glm-5-3-flash`; these require credentials accepted by the configured provider. A single game is not evidence of a gain given the documented variance.

In particular, measure whether the extra system/status/query tokens outweigh any reduction in repeated failures. The guard saves game API attempts but does not refund an already-made model call. The failure cache is deliberately short, and successful actions can unlock an otherwise redundant retry. These limitations require real model/game comparison, not more fake-game score claims. No claim of improvement, promotion or contender status is made here.

All candidate modifications, tests, the note and dependency declaration are kept inside `submission/`, the only editable path. If eventually submitting this candidate, pass this note and dependency file directly from there; the CLI accepts file arguments without requiring root-level copies. Determine and supply the exact underlying coding-model identity separately from the coding-agent name before submission. No credentials or local environment files belong in the archive. For a new account, the first scored submission is stage 1 only and cannot promote; scarce submission quota should be reserved until the candidate has meaningful local comparison evidence.


## Current iteration: bounded sequential actions and measured negative control

The iteration directly inherits published submission `d8164ec2-7202-4383-8dcf-caa164ef70fd`, whose official result is now rejected at 75.84 versus frontier 77.10. The dependency file now declares this direct reuse as well as the earlier published-note input. No new official submission or win is claimed here.

### Hypothesis and implementation

The inherited executor took only the first tool call in a model response and rejected the remainder, even when actions were independent. A one-response reproduction requested three valid actions and showed only one game API action. The new executor permits at most four sequential model-selected actions per response. Each still goes through the same API and validation/churn/retry guards; no concurrent actions or new server endpoint exists. A failed call, read-only inspection, time advance or terminal exception stops the suffix, which receives explicit `batch_stopped` results. Returned IDs must be observed before being used in a later decision.

Independent review reproduced two integration issues in the first batching draft: the context window trimmed fresh earlier batch results before delivery, and the idle counter counted batches instead of calls. Both were repaired. The window preserves the latest assistant/result group intact, including skipped suffix results. The stall guard counts attempted calls individually and a guard-driven advance stops the batch. Skipped calls do not count as attempts. New multi-turn regressions exercise whole-result delivery, long suffix protocol completeness and the ten-action stall boundary. The combined focused verifier passed 49 tests in 5.163 seconds.

### Controlled local evidence so far

All runs use real DF 53.16/DFHack 53.16-r2, the public LT08 scenario, two repetitions, the suite's 60-day horizon and $0.0893 task budget. `--n 2` selects public snapshot variants through the standard runner; the run spec's RNG seed remains its default 12345. Both arms use the same local-only native-Z.ai gateway translation described above, not the official Together provider. There were no provider errors or timeouts in the completed control runs. No provider equivalence or statistical significance is claimed.

| Harness | Local subset LB95 | Mean partial | Task passes | Reference-price credits (two games) |
|---|---:|---:|---:|---:|
| Untouched organisers' plain baseline | 47.98 | 0.86 | 0/2 | $0.143013 |
| Inherited advisor + standing guard, serial execution | 37.28 | 0.82 | 0/2 | $0.163039 |
| First batching draft | 45.46 | 0.91 | 1/2 | $0.144919 |
| Corrected batching candidate | 60.39 | 0.87 | 0/2 | $0.134389 |

The inherited serial candidate exhausted model access at days 20 and 16, before the day-39 hands-off window. Its final predicate clauses were `[true,false,false,false]` and `[true,true,false,false]`; the baseline's were both `[true,true,false,false]`. This negative result invalidates any presumption that the inherited extra advice improves performance. Cheaper action throughput is only a mechanism hypothesis until final scores arrive. This subset scale is not comparable to the full official 77.10 frontier.

The frozen first-batch and corrected-batch Docker harness digests are respectively `sha256:aee1d68edd0cdd9994ff1e2ec2dd5df8cc691a5b5ddef5a860c321d0e6df0dc9` and `sha256:e3ddd875a53fbbc452e8be795442690a0e5452dbcf002c1429a8f57f21cdf756`. Corrected-batch source hashes and the test receipt are retained in the local research report directory. No reports or provider adapter are part of the submitted Docker image.

Reproduce the public two-game experiment with a pre-existing native provider adapter image (development-only):

```sh
DFBENCH_GATEWAY_IMAGE=dfbench-gateway:zai-low-local \
python3 runner/dfbench local suite --harness submission --games LT08 --n 2 --parallel 2 \
  --retries 0 --key-env ZAI_API_KEY --upstream https://api.z.ai/api/paas/v4 \
  --out .yukon/runs/iter1-lt08-batch-fixed
```

The adapter changes the forwarded model identifier and translates the reasoning parameter only; it is outside `submission/`. The model key is read from the gateway-only environment, never from the harness. For official-comparable local measurements an official supported provider key remains necessary; the unconfigured standard `yukon run --track harness-glm-5-3-flash --json` stops with exit 2 requesting that key.

The first batch draft completed with per-game partials `1.0` (pass, all four clauses true) and `0.8269` (fail, final two clauses false). Its point estimate was 84.37 but local LB95 only 45.46: two repetitions are too variable to establish an advantage over baseline LB95 47.98. The successful game added eight farm plots at day 21 (18 to 90 built farm tiles by its last active observation); the failing game added none. This is a concrete next hypothesis, not proof that more farms caused the pass. The successful game's last active observation still had zero edible food, so a snapshot cannot substitute for the handover/run-out predicate.

### Terminal update and current, separately unscored strategy candidate

The official predecessor `d8164ec2-7202-4383-8dcf-caa164ef70fd` completed 48 games and was rejected at official LB95 75.84 versus incumbent 77.10 (point 82.12). Its MY1 outcome was 89.9 versus baseline 78.6, but OP1 was 70.7 versus baseline 76.5, with LT08 still 0/8. Judge verdict pass; zero infra exclusions and wall caps. Confirmation was not run because it did not clear the required improvement. This official full-suite result concerns the inherited serial implementation, NOT the new batching or farm-advice code.

The corrected batch version completed the same native-provider public LT08 two-repetition comparison: local LB95 60.39, mean partial 0.87, no complete passes. Per-game partials were 0.8601 and 0.8820. Both exited normally with no provider errors or timeouts. It cost $0.134389 at reference token prices, versus $0.143013 for the baseline, and executed 127 scored actions versus 90. These are small developmental subset results, not official evidence or a reliable estimate of full-suite gain.

The current files add a separate strategy hypothesis: bounded known built farm area, planned-vs-built counts, per-citizen area, fallow crop ids and free sites whose season/light matches observed seeds. A warning below two built farm tiles per citizen is explicitly an expansion heuristic, not a DF rule or yield guarantee. It prioritizes early compatible farm expansion over optional dining decor while retaining actual supply/harvest verification. Missing dimensions stay unknown; planned plots do not count as built area; autofarm on is not treated as proof of crops or force-refresh. The model still selects every action. The combined verifier passed 51 tests in 5.664 seconds, including compatibility/missing-data/non-mutation cases.

This farm-advice variant is being compared with the frozen corrected-batch image in `.yukon/runs/iter1-farm-capacity` and `.yukon/runs/iter1-farm-control`; results remain pending. Both arms use the same current public snapshot cache. A setup invocation was intentionally stopped after it unexpectedly regenerated seed-2001 worked/neglected snapshots; the older completed experiments had all loaded before that regeneration. Do not compare a new single arm against an older arm on the assumption that the rebuilt save is identical; the new paired experiment hashes the inputs. The higher-priority official follow-up is to reproduce and repair the OP1 regression without losing the MY1/lab gains. No new submission was spent this iteration.

The current strategy candidate is also running two native-provider OP1 repetitions against two untouched-baseline repetitions on the same pinned public embark save. OP1 carries 50% of the official objective, so recovery of the official OP1 regression is the main remaining priority. Those measurements are pending and no acceptance or promotion is inferred from starting them.


## Iteration 2: terminal paired evidence and isolated production experiments

No new official submission was spent. The rejected official predecessor remains 75.84 against frontier 77.10.
The local results below use native Z.ai GLM-5.3-Flash through the external development adapter, not the
organiser's pinned provider. They are not comparable to the official full-suite frontier. Same cached public
saves were used within the paired arms after seed-2001 cache regeneration; old pre-regeneration measurements
are not paired controls. Harness identities are image digests, not note versions or receipt timestamps.

### Farm-capacity advice did not establish a gain

| Arm (two public LT08 games) | Point | LB95 | Mean partial | Passes | Credits |
|---|---:|---:|---:|---:|---:|
| Bounded batching, no extra farm advice | 75.38 | 53.15 | 0.8934 | 0/2 | 0.1561 |
| Batching plus farm-capacity advice | 71.29 | 26.30 | 0.8844 | 0/2 | 0.1391 |

Farm-arm drink margins (final minus day-39 stock) were -8 and -47; control margins were -26 and -50.
Farm arm placed 49 beds for 48 citizens in one game but edible food reached zero. Its other game placed only
11 beds for 47 citizens and lacked a valid chaired manager office. Control placed 41/50 and 24/50 beds.
The control's first game built a Fishery at day 16; its item-credit log recorded 22 PrepareRawFish starts and
11 FISH item outputs, and food remained positive during hands-off. This association does not prove causality.
An older first-batch pass also had a Fishery, many farms and a daily brew threshold of 600, but used a
different earlier save and cannot be treated as a matched experiment.

### Paired OP1: less food failure, but drinks constrain the outcome

| Arm (two public OP1 games) | Outcomes | Point | LB95 | Supply | Growth | Credits |
|---|---|---:|---:|---:|---:|---:|
| Untouched plain baseline | 80.3, 45.9 | 63.1 | 45.9 | 0.69 | 0.27 | 0.1654 |
| Batching/farm advice | 64.6, 57.8 | 61.2 | 57.8 | 0.56 | 0.56 | 0.3018 |

Candidate digest: sha256:9a26e1e5372bcfe913ecc7a1b60eeb83220447c1ea935e18402f1da31d5bcee2.
Baseline digest: sha256:2fd4aed7eebd12f047d8381291183b46d1bdb53ce06455e6f3d673c1c4661759.
Both arms had zero infrastructure exclusions, zero wall caps and zero credit exhaustion. Candidate had four and
zero zero-food days versus baseline five and 72, with final food supply subscores 1.0 in both candidate games.
But candidate drink supply subscores were 0.603 and 0.525 (baseline 1.0 and 1.0). No survival deaths occurred.
The higher n=2 lower bound is a narrower spread, not proof of higher objective performance: mean fell 1.9.

### Concrete production errors and current isolated hypotheses

At public OP1 day 21 a one-time ten-job brew order was followed by plants 30 to 0, food 60 to 30, and drinks
53 to 203. The served manual documents that amount counts jobs, not finished drink units; conditions are
checked per repeat, not continuously through a batch. The prompt now cautions against large catch-up and
overlapping brew batches and suggests starting with one daily job and verifying actual stock changes.

A replay of farm-arm LT08-1 finds a monthly brew threshold drink<300 false for every day 39 through 60: stock
was 486 at handover and 439 at horizon. A comfortable stock reserve cannot satisfy final>=handover drink if
production remains idle. Current prompt distinguishes explicit growth goals from ordinary reserve goals and
suggests a higher target plus a consumption buffer, conditional on sustainable plant/barrel/food supply.
No automatic orders, hidden-state inspection or direct DFHack access were added.

Separate frozen native-provider experiments: cadence/reserve (digest 4a6c2433393c32b23c6361f7b6d289843ae7bdd580202eb15f37b07b3e7f01c3),
conditional Fishery advice (be68183e98ec36c1243b477e810397d1e353ce8bb9367f138b3b4d8e49e8dafc), then explicit
handover-growth targeting (42e24f93dcb7840e2e2aed788b89beab628e121ea3ec4ff8f5e7886673b987be).
Cadence/reserve LT08 is complete at 0/2, mean partial 0.8475, drink margins -45 and -46. Its OP1 games and
the later two LT08 pairs were still pending at this checkpoint. No subset or prompt presence implies adoption:
the first completed fishery-advice game used slaughter/Butchers instead, so it did not test fish-processing
throughput. Chair-in-office assignment, actual result.n versus requested furniture count, validated orders and
input availability remain critical verifications.

Verification: 52 regression/existing fake-HTTP integration tests passed in 5.163 s after the cadence edit; later
fishery and handover additions passed the focused pre-existing unittest entry point. All action execution,
failure memory, fresh tool-result and stall guards remain unchanged from the corrected batch checkpoint.
The trusted runner was safely refreshed with yukon sync --harness-only; submission files were preserved.
These are candid local development results, not a winning submission.


### Terminal LT08 update: goal-aware pair, still no official submission

The goal-aware handover pair completed: pass 1/2, partial 0.9694, local LT08 point 109.55/LB95 95.82,
credits 0.1361. Fishery-only advice completed at pass 0/2, partial 0.8702, point 64.93/LB95 24.73, credits 0.1188.
These lab-normalized subset scores can exceed 100 and must not be compared with the full official frontier.
All five current LT08 arms had identical first-observation hashes for each repetition. The passing goal-aware
game had 63 beds for 48 citizens, food positive throughout, no deaths, and drinks 523 to 535 during hands-off.
It built a Fishery at day 18; the credit log recorded 23 FISH item outputs and 11 DRINK outputs during hands-off.
Its daily amount-one brew order had a drink<600 target, plants>=5 and food>=30. Cooking was conditional on
plants>=25, preventing it from indiscriminately consuming the last plant inputs. These are observed choices,
not hard-coded actions. The other repetition still failed bed coverage and drink growth. One pass is not
evidence of general reliability; exact frozen-image MY1/OP1 tests have been started to check weighted regressions.
No new official submission was spent; frontier remains 77.10.


## Post-checkpoint correction: provider balance blocker and unmeasured office repair

The earlier statement that weighted checks were pending is superseded by retained provider evidence. Both
cadence OP1 games received native-provider HTTP429/code1113, "Insufficient balance or no resource package",
at reference spends0.03241887 and0.04018621. The harness classified these as budget_exhausted and quit
model control at API days36/91. The runner later scored them as ordinary harness exits, with infra_excluded0
and credits_exhausted0; those fields do NOT rule out an upstream balance problem. Thus the generated
mixed cadence suite point52.96/LB95 25.62 and OP1 mean52.25 are contaminated, not a fair cadence strategy
measurement. The already-terminal cadence LT08 results are unchanged. No scoring code or ledgers modified.

The exact goal-aware candidate MY1 pair received zero successful calls: each first call retried six times,
then returned HTTP429 with the same balance error and zero spend. That suite was cancelled before OP1
started; only its four orphan compose containers and four empty networks were removed. It provides no
weighted regression result. No recharge, credential change, new provider, or paid-resource expansion occurred.
To continue weighted testing, the operator must restore the existing native provider's balance/resource
package or approve a funded alternative route for the same fixed model. No new official submission.

Offline replay of the known chairless-office traces showed the old generic office warning was already
present23/23 chair-false cadence observations and31/32 fishery observations; omission was not the main
problem. Added a bounded manager_office_repair diagnostic in plain/advisor.py: existing office zones with
built chairs and owners, or currently advertised free A/dug R site boxes containing actual built chairs.
At most three candidates per list and four chair IDs per candidate; planned chairs and used/undug R rooms
are excluded. Furniture truncation is explicit. Missing geometry supplies no invented placement. The model
still chooses all actions, uses returned zone_id for assignment, and must verify manager_office.chair and
order validation. No crop, brew, batch, model-client or action execution logic changed.

Validation: 13 existing test_advisor.py tests passed in0.003s; all three public trace replays passed, including
no input mutation and no repair diagnostic on24 ready-office observations. An initial replay assertion
incorrectly assumed the goal-aware run had a valid office at every prior day; corrected it to use each
observation's explicit state. In fishery LT08-1 the diagnostic identifies A2/chairs9,10,11,12, manager91,
chairless assigned office8. This is diagnostic verification, NOT measured game/score improvement. No live
provider test or Docker build was spent on the new office candidate.

## Iteration3: endpoint correction and complete searchable catalogue pages

Endpoint diagnosis corrects the earlier overly broad balance-blocker interpretation: the failing native
runs explicitly passed `--upstream https://api.z.ai/api/paas/v4`, the standard API base, while the operator's
Coding Plan screenshot shows99%remaining quota. Z.ai's current FAQ specifically lists incorrect base URL
as a cause of1113after a Coding Plan purchase and identifies `https://api.z.ai/api/coding/paas/v4` as the
OpenAI-compatible Coding Plan endpoint. This establishes a route/entitlement mismatch, not depleted
Coding Plan quota. The screenshot cannot establish that the environment's key belongs to the same account.
References: https://docs.z.ai/devpack/faq.md (Technical Support),
https://docs.z.ai/devpack/tool/others.md (Supported Tools / Coding Endpoint), and
https://docs.z.ai/devpack/usage-policy.md. These docs limit subscription benefits to supported tools/products;
the custom gameplay harness is not listed. No subscription reroute, credentials change, recharge, provider
switch, or new paid call was performed. Verify permitted use with Z.ai or provision authorized standard API
access; the organiser's official gateway remains independent. Historical provider-contaminated scores remain
invalid strategy evidence regardless of this diagnosis correction.

New source mechanism, separate from office-repair advice: fixed catalogue information loss in
plain/inspect.py. On each of3retained real public manager_order_types queries, the response is about30KB
and starts with condition_flags / item_types. The old3400-character wrapper only contains a2600-character
preview; it does not expose PrepareRawFish, and provides no local filter or page mechanism. The same
read-only query can now be inspected by section, optional case-insensitive substring search, offset and
limit. The model's tool schema documents this interface. Catalogues without a section return section sizes.
Whole source entries are copied into pages under3400characters; dictionary entries retain key/value, empty
or out-of-range pages end with next_offset=null, and a nonterminal page always advances. Oversize single
entries produce an explicit error, not an impossible continuation. Selectors are validated locally and not
forwarded to the API. Only currently advertised query names are available. No execution policy, orders,
batching, stock heuristics, fixed model or gateway settings changed.

Verification command:
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission:submission/tests python3 -m unittest discover -s submission/tests -p test_inspect.py -v`.
Before the repair, new inspection regressions exposed2failures and2errors; after repair, all11focused tests
passed. Retained real trace replay from iter1-farm-control LT08-0 day16, iter1-farm-capacity LT08-0 day35,
and iter1-op1-candidate OP1-0 day209 reconstructed all444entries in7sections in16bounded pages per response:
83condition flags,93item types,102job types,14material categories,126reactions,11recipes,15stock conditions.
Maximum page3383characters. Fish search returns PrepareRawFish and ExtractFromRawFish, and brewing search
exposes BREW_DRINK_FROM_PLANT. Replay confirms zero input mutation and zero selector leakage to the API.
These three records share catalogue content; they are not three independent gameplay trials. Source of the
interface is the public API docs plus gameapi/facts/lua/query.lua; no private seed/scorer state is used.
This repair is offline-verified functional behavior, NOT measured gameplay improvement. No new official
submission was spent. The previous official submission remains rejected75.84 versus frontier77.10 (delta
-1.26points), and unchanged candidates are not eligible for a redraw. Next: matched live OP1 / MY1 checks
under an explicitly authorized route before deciding whether a distinct candidate warrants a submission.


## Partial furniture placement is now an observation barrier (offline candidate)

This source extends the saved `82003f9bb686549325b5367d4d9ed24c7082824a` catalogue/office candidate.
It does not have a new game result. The inherited official submission remains
`d8164ec2-7202-4383-8dcf-caa164ef70fd`, rejected at 75.84 versus frontier 77.10.
The current frontier source, checked again from Yukon, is
`dfa2f068e42d2651d79eaedeb026b364ce755bb5`. No new official submission is claimed.

### Mechanism and public evidence

The public API's `gameapi/facts/game.py:373-397` counts furniture **designations** and
returns `ok:true` whenever any were made, even when `n < requested`. Its `available`
field reports free items before placement. `gameapi/facts/sites.py:102-103` computes
`free` from site-level use conflicts, not free floor-tile capacity. Bounding-box area
and `free:true` therefore do not establish room for the requested furniture count.

For example, the retained public LT08 trace
`.yukon/runs/iter2-handover-growth/LT08-0/game/harness-0.api.jsonl` shows a day-0
request for 18 beds at A1 returning `n:2, requested:18, available:19`, followed by
smaller-count 16 and 10 attempts in the same area failing `no_space`. Those events
are evidence of response-handling/space confusion, not a claim that this fix makes
that fort pass or that the repeat requests would disappear in a new game.

`plain/harness.py` now interprets only successful, well-formed partial
`place_furniture` results. It preserves the API result and annotates it with bounded
`harness_placement`: designated, requested, not_designated, free_items_before,
limitation, and next-inspection advice. Reaching the item cap does not rule out a
simultaneous space limitation. When items remain, advice points to floor/tile
eligibility rather than automatically producing more items. Neither branch claims
built furniture, fulfilled housing, or exact remaining site capacity.

Partial success sets the existing batch barrier: later calls receive
`batch_stopped`, then the usual loop obtains fresh public facts. The model chooses
all subsequent actions. Full placements keep ordinary independent batching;
failures and malformed/unrelated responses retain prior behavior. A smaller-count
retry is advised against, not prohibited. Stall guards and per-action accounting
remain active. `plain/prompt.py` documents these semantics and the site's `free`
flag distinction. No new endpoint, hidden data, scorer input, or automatic game
action is introduced.

### Validation and limitations

Reproducer (stdlib, no paid calls):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission:submission/tests \
  python3 -m unittest test_batch test_placement -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission \
  python3 reports/iter4-grounding/replay_placement.py
```

The regression initially failed with 2 failures and 3 errors. After implementation,
a case-sensitive text assertion was corrected; the final focused verifier passed
17 tests in 0.002s (11 existing batch cases and 6 placement cases). These checks
exercise real loop suffix handling, tool-call IDs, next-request preservation,
accounting, malformed results and unchanged full-success batching.

The retained public-API replay compares the exact frozen control result emitter
from commit `82003f9` against the new emitter on identical inputs: 259 placement
responses across 14 traces, 50 partial successes (34 with free items remaining,
16 reaching the item cap). Control barriers on partial results: 0/50; candidate:
50/50. All candidate diagnostics preserve the original result and valid bounded
JSON; unrelated and full responses remain unchanged. Twelve smaller-count
same-day attempts after a partial space-limited result failed `no_space`. This
last figure is observational, not estimated saved calls, credits, or actions.

Reports, source hashes, exact trace paths and API line numbers are retained under
`reports/iter4-grounding/` for local audit; they are not needed in the runtime image
and are not bundled by the `submission/` archive. The selected cadence OP1 traces
had provider failure elsewhere; replaying their already-returned placement results
does not rehabilitate their contaminated outcome scores.

No image build was attempted: the operator's environment has `ANGEL_NO_BUILD=1`.
No provider call, billing change, credential change, subscription reroute, or
new official submission was made. Authorized live paired OP1/MY1 validation
against the exact frozen candidate remains necessary before claiming score gains.
The standard-API quota error is not evidence that the operator's Coding Plan was
exhausted; supported custom-harness access or funded standard API access still
needs resolution. Extra diagnostics and a new observation barrier may cost tokens
and model calls, so their net gameplay value is unmeasured.

## Iteration 5: lossless public-observation record packing (offline candidate)

### Updated official comparator, not a new result for this candidate

The authenticated Yukon frontier is now **81.30**, promoted submission
`9b597a76-9bf9-4923-a9d4-1c8ee83067a9`, source
`3ed866583d0cab5a7392701f02939d7e8707f1f4`. This supersedes historical
77.10 frontier references above. Our last scored submission `d8164ec2` remains
rejected at **75.84**, a **-5.46** gap to the current frontier. That official
result concerns source `1bbc2ef6`, not the subsequent local changes. The new
packing candidate has **ZERO SUBMISSIONS** and no gameplay score.

### One causal change

Parent: `fb56696954f20b7ab95b31c8fadfdbe554cc6e18` (the partial-placement
barrier candidate). New `plain/packing.py` removes repeated JSON field names
only in the public `dwarves` and `map.sites` lists. Consecutive records with
identical key sets become explicit `columns` / `rows` tables. A changed key set
starts another table instead of filling missing fields with null. A short
model-visible explanation names exactly the encoded paths; arbitrary nested
cell values remain literal values. Empty, malformed and small lists remain
unchanged. Each path must save its entire explanation plus a 64-character
margin before it is converted. Other observation fields are unchanged.

`Plain.run` still gives the advisor the original observation dictionaries,
then formats the message using the codec. The `OBSERVATION {` prefix is retained
so the inherited history window continues omitting old observations and their
explanations. No schema/tool, model, action choice, batching barrier, retry,
advance, budget or stop policy changes. There are no new dependencies.

### Checks and measured encoding result

Existing pre-existing test entry point:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission:submission/tests \
  python3 -m unittest test_batch -v
```

**11/11 passed**, 0.002 seconds, exit 0. This tests batching/protocol, not
fortress performance. A read-only independent static review found no concrete
codec/history issue; it did not establish gameplay fitness.

Paired offline replay:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission:submission/tests \
  python3 reports/iter5-frontier/replay_packing.py
```

The frozen parent and candidate each run their actual one-turn harness through
a capturing fake model on the same retained public `/observe` response. The fake
model's `advance_days(1)` choice is deliberately fixed; unchanged emitted
actions do **not** mean the real model will choose the same actions. JSON
reconstruction compares serialized, sorted-key values to preserve type
semantics, not Python's permissive false/zero equality. Codec boundary checks
cover nested table-shaped values, missing/null, booleans, Unicode, key-order
changes, empty/malformed fallback, input preservation and history stubbing.

| Offline encoding measurement | Frozen parent | Candidate |
|---|---:|---:|
| Nonterminal observations, 33 retained traces | 1,240 | 1,240 |
| Message characters, including explanation/advisor | 20,782,235 | 16,212,376 |
| Message UTF-8 bytes | 20,809,366 | 16,239,507 |
| Exact reconstructed parent observations | — | 1,240/1,240 |
| Nonexpanding messages | — | 1,240/1,240 |

UTF-8 reduction is **21.9606%** (4,569,859 bytes across the replay). These
observations contain repeated seeds and provider-contaminated games; they are
valid encoding fixtures, not 33 independent gameplay trials. Fourteen terminal
observations were excluded because the real harness exits before rendering.
No actual token count, provider cost, latency, new game outcome, or score delta
has been measured. Column-position reading may be worse for the fixed model;
only a fresh matched gameplay test can test comprehension and strategic value.

### Untouched promoted leader comparison and provenance

The promoted source was fetched read-only into retained comparator files. Its
published digest and harness `user_message` emitter produce 19,583,664
characters (19,611,704 UTF-8 bytes) on these observations with fresh memory,
`units=None`, no query and no error fallback. Candidate messages are 17.2148%
smaller in characters in that restricted comparison. The leader intentionally
uses a different advisory digest and drops/summarizes some raw fields; these are
not equal-information contexts or actual leader trajectories. There is **no
claim** that smaller messages beat the official leader.

The leader code/note informed comparator selection and were used as comparison
source, not copied into the runtime candidate. Any future publication must
attribute that measured comparator use precisely, separately from inherited
runtime code and earlier dependencies. Exact comparator hashes, replay inputs,
trace paths and checks are under `reports/iter5-frontier/` outside the runtime
submission archive. The native research-run launcher failed before execution
because the outer workspace is not a Git repository; its result is not counted.

### Separate verified API finding and remaining gate

Seven retained `make_zone` failures used advertised A sites wider than 20 tiles.
`SiteState.resolve` copies the site's dimensions (`sites.py:143-151`) and the
real `_t_make_zone` emitter validates width/height in 1..20 (`game.py:399-401`).
The exact seven retained dimension errors are reproduced before any DF call by
`reports/iter5-frontier/reproduce_zone_dimensions.py`. No official API source
was edited, no site was automatically resized, and no harness behavior change
for this separate finding is bundled here. The organiser should reconcile its
advertised site footprints with the tool's limit. Another legal site remains a
model choice; raw coordinate/dimension arguments are internally accepted but
not advertised by the current tool schema.

No Docker build, gateway/model call, billing/credential/provider change or
new official submission was made. `ANGEL_NO_BUILD=1` remains active. Standard
API funding/permitted custom-harness subscription use still needs resolution;
prior standard-API error1113 is not Coding Plan exhaustion evidence. Next gate:
authorize the build and permitted API access, then fresh exact-parent/candidate
paired OP1 and MY1 gameplay at matched seeds/budgets, recording tokens, credits,
comprehension failures and official-scorer outcomes. Keep the candidate offline
until that gate; do not claim a win from this codec check.

## Iteration6: explicit zone footprint overrides, no automatic resizing

### Bottleneck and public contract

Parent is local candidate `731af919fffc6548f0d953501d948c4f72ea2c43`.
`gameapi/facts/tools.py` advertises `make_zone {kind, site}` with no size override.
However `Game.act` in `gameapi/facts/game.py` explicitly accepts `w` and `h` for
site tools, `SiteState.resolve` preserves supplied dimensions and defaults omitted
axes to the site's box, and `_t_make_zone` validates each dimension in `[1,20]`.
The public manual's A sites are bounding boxes of revealed indoor floor/stair
tiles, not guaranteed 20-by-20 rectangles. A site may therefore be advertised and
accepted by the site resolver but deterministically rejected for its default width.
This uses the ordinary whitelisted action/arguments on public facts. It changes no
game API, scorer, game artifact, hidden state, server limits or allowed endpoints.

Seven retained failures were already reproduced in the preceding iteration.
This iteration tests a model-visible repair and verifies geometry, rather than
merely repeating that diagnosis. It does **not** assume that free sites represent
fully usable floor rectangles, or that a furniture designation is built furniture.

### Candidate

`plain/harness.py::prepare_tools` deep-copies the task's schemas and exposes
optional integer `w` and `h` in `[1,20]` on an advertised `make_zone` with a site
property. Existing size properties, required fields and all unrelated tools are
preserved; no missing action is invented. A bounded description and
`plain/prompt.py` explain the size/default mismatch and anchored rectangle.
The transformation is idempotent. Existing advance caps are unchanged.

Every zone is still model-selected. There is **no** automatic clipping, coordinate
translation, tool execution, retry, fallback site choice, or suppression of API
errors. The explicit arguments pass through unchanged to the ordinary game API.
An omitted dimension still uses the original API default (and may still fail).
The candidate advises checking built furniture at the same z using the actual
rectangle bounds. If no legal anchored rectangle can include it, choose another
site. It does not fabricate successful zones or infer actual tile suitability.

### Reproduction and measured scope

From the benchmark Git root (not its non-Git parent):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:submission:submission/tests \
  python3 -m unittest test_zone_dimensions test_batch -v
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:submission:submission/tests \
  python3 reports/iter6-zone-footprints/replay_zone_dimensions.py
```

The first test attempt had 17 passing cases and one fixture error because the
new test incorrectly called nonexistent `Task.parse`. That fixture was corrected
to `Task(...)`, the budget field corrected to `credits`, and the schema
transformation made idempotent before the conclusive run. No failed receipt is
hidden. The final run: **18 tests passed in 0.003 seconds, explicit exit 0**.
Seven new tests exercise the actual public dispatcher with DF stubbed: exact
schema changes, no task mutation, missing-action behavior, default rejection,
valid/invalid dimension handling, untouched origin, preserved existing dimension
contracts, and one-turn harness pass-through. Eleven existing batch tests pass.

The separate frozen-parent/candidate replay found **147 zone calls in 25 retained
public traces**, with **147 identical action/result pairs** under fixed fake-model
outputs. Original returned JSON, errors and batching are preserved. This is a
behavioral replay, not a model-comprehension measurement or independent new games.

For the **seven oversized-site failures**, the real dispatcher reproduces the
original rejection before any DF call. Deliberate test-only explicit dimensions
`min(site.w,20)` and `min(site.h,20)` are rejected by the frozen schema and allowed
by the candidate schema; the real dispatcher reaches the Python zone blueprint
emitter in all seven. In each case, those rectangles include all the observed
built chairs inside the original site box. Emitted row/column counts and original
x/y/z are asserted. Those minima are an **experimental intervention**, not a
runtime resizing policy. The successful quickfort output and zone lookup are
stubbed; no claim is made that DF accepts the tiles or actually creates a zone.

A synthetic counterexample puts a built chair in column 23 of a width-23 site.
No legal width-20 rectangle anchored at the same origin includes it. This is why
blind clipping is expressly excluded; a model must choose another site. Furniture
coverage alone does not prove suitable zone floor tiles, assignment, value, or
production readiness.

Detailed local artifacts are in `reports/iter6-zone-footprints/`: exact frozen
parent harness/prompt, replay source/results, per-trace and per-request SHA-256,
initial/final test receipts, and checkpoint validation. These local reports are
not part of the submission runtime/archive. Only files under `submission/` change
the candidate; no organiser-owned source is edited.

### Frontier, provenance and next real gate

Authenticated exact-ID status confirms promoted leader
`9b597a76-9bf9-4923-a9d4-1c8ee83067a9`, score **81.30**, source
`3ed866583d0cab5a7392701f02939d7e8707f1f4`. Our last scored submission
`d8164ec2-7202-4383-8dcf-caa164ef70fd` is rejected at **75.84**, 5.46 points
behind. The leader's LT08 has 0/8 passes but 0.85 partial; that is context for an
office/zone defect, not evidence that this candidate beats the leader. Prior
public comparisons and published baseline inheritance remain declared in
`dependencies.json`; unpublished local checkpoints are not invented dependencies.
This change is independently implemented from the public API code, not copied
from the promoted leader's zone behavior.

The outer experiment service failed at Git discovery in the workspace parent,
before any experiment execution. This iteration uses direct commands with
`cd arena-fortress-s0` and frozen files from that repository; it does not initialize
an unrelated parent repository or report a fictitious successful service retry.
All eleven file hashes from the previous checkpoint match their saved manifest;
the retained packing replay log reports explicit exit 0. Those are provenance and
offline-check receipts, not official score verification.

**ZERO SUBMISSIONS this iteration.** No Docker builds, gameplay calls, model calls,
credential changes, paid-resource expansion, provider changes or subscription
rerouting. `ANGEL_NO_BUILD=1` remains active and the standard local runner's
`DFBENCH_PROVIDER_KEY`/`OPENROUTER_API_KEY` are absent. An earlier standard API
error1113 still says nothing conclusive about Coding Plan quota. Do not redirect
the custom harness to subscription endpoints without confirmed permitted use.
Next gate is authorized build and model access, followed by matched exact-parent/
candidate OP1/MY1 and targeted office/zone gameplay with real model outputs,
actual zone results, tokens, credits and official-scorer outcomes. No official
improvement or win is claimed from these offline tests.


## Iteration 7: real-DF emitter gate and validation is not office readiness

This candidate accumulates the unsubmitted repairs documented above: bounded searchable
public recipe pages; reobservation after partial furniture designation; lossless record
packing of full observations; optional explicitly model-selected bounded zone dimensions;
and, in this iteration, a narrowly conditional blocked-order diagnostic. None of these
repairs has an attributable official score yet. This submission requests that measurement;
it does not claim a local win, a private-pool result, or a reproducible numerical gain.

### New evidence and resulting change

A model-free diagnostic started the existing public `yukon-df:s0` image and exercised
only the public HTTP API. No image was built, no model gateway was started, and no
model call was made. Four implementation files in the image (facts game.py, act.lua,
observe.lua and server __main__.py) matched the checkout's SHA-256 exactly. The diagnostic
replayed the retained public LT08-0 action sequence, then explicitly made an office zone,
assigned the returned zone_id to the *currently observed* manager, and advanced two days.
DF reported successful zone creation and assignment with `chair:true`. After two days,
`manager_office` still reported that chaired zone, but all six existing orders remained
`validated:false`, `active:false` and with unchanged remaining quantities. This shows that
successful office assignment is not sufficient evidence that order validation actually ran.
It does not establish a cause for the manager's delay or any upper bound on that delay.

The new production change is seven lines in `plain/advisor.py`. When a manager exists,
`manager_office.chair` is explicitly true, and one or more observed orders explicitly have
`validated:false`, the bounded advisory priorities warn that production is not established.
The advice is to inspect the manager's public job/needs/access, order state and cancellations,
allow a short interval and recheck validation. It discourages rebuilding/reassigning an
already chaired office or cancel/re-add churn and explicitly guarantees no fixed validation
delay. Raw observations, action selection, action arguments, API results, batching barriers,
model identity, sampling settings and budget policy are unchanged. No new automated action,
private input, hidden DF access or unsupported query is introduced.

### Measurements and limits

* Existing `test_advisor.py` entry point: 14 tests passed, exit 0. One added regression
  covers chaired/unvalidated, chairless/missing/unknown office, already validated orders,
  and input preservation. Existing `test_zone_dimensions.py`: 7 tests passed, exit 0,
  with the correct `PYTHONPATH=submission`. The first invocation without that environment
  failed to import `plain`; this was a launch-path error, not a successful test.
* Frozen-parent paired interpretation over 1,254 retained public observations: 179 new
  warnings across 16 traces. Every added warning had the explicit chaired-office and
  unvalidated-order preconditions; all non-priority interpreted fields were identical.
  Existing priority order was preserved except bounded-tail truncation where insertion
  reaches the existing advisory cap. These are interpretation checks, not model outcomes.
* The fresh live state's site geometry differed from the retained trace (the current A5
  was 20x9, not the historical 22x7), and initial citizens were 18 rather than 19. The live
  run is therefore NOT an exact paired historical replay and NOT evidence that the
  historical oversized failure disappeared. Coordinates-only zone requests were separately
  rejected with `args.site is required`; no submission code attempts that bypass.
* No further token savings, behavior improvement, local score or official improvement is
  claimed from this iteration. A chaired zone with still-unvalidated orders is precisely
  the observed remaining failure, not a production success.

### Reproduction and official measurement request

From the repository root, run:

```sh
PYTHONPATH=submission python3 -m unittest discover -s submission/tests -p test_advisor.py -v
PYTHONPATH=submission python3 -m unittest discover -s submission/tests -p test_zone_dimensions.py -v
```

The required local `.yukon/run.sh` was exercised and exited 2 with the documented missing
provider-key message. The official provider credentials are not configured in this session;
a different provider endpoint was not substituted. Local builds are disabled, so neither
new harness images nor game images were built. The official runner can build the submitted
Dockerfile and perform the required fixed-model, pinned-price evaluation. No claimed-score
flag is based on these offline or model-free checks. The historical local subset score
37.28 belongs to an earlier candidate and must not be attributed to this candidate.

Immediately before preparation, the official promoted frontier remained 81.30 from
submission `9b597a76-9bf9-4923-a9d4-1c8ee83067a9`, promoted source `3ed8665`.
Our last scored published predecessor `d8164ec2-7202-4383-8dcf-caa164ef70fd` was rejected
at 75.84. The target is the current official frontier plus the platform's promotion margin,
not a better offline byte count. Trusted non-editable files were refreshed with
`yukon sync --harness-only`, preserving this submission tree, to avoid a stale trusted base.
Prior dependency declarations are retained: direct runtime inheritance from our published
predecessor, public diagnostic design inspiration from the cited peer note, and measured
comparison use of the promoted renderer (not copied runtime or design inheritance).

Artifacts for the diagnostic live under local `reports/iter7-gate/`; they are not runtime
inputs and are not read by the submitted harness. The official outcome, once terminal,
is the only evidence that can establish a competitive improvement.

### Terminal site-bound real-DF gate

The corrected site-based real-DF diagnostic completed with exit 0. On current advertised
site A5, an explicit width22/height7 request was rejected with the exact width1..20
validation error. An explicit width20/height7 request reached real quickfort, returned
`ok:true`, created 69 zone tiles with returned box
`[91, 91, 77, 20, 7]` and zone_id50.
Separate assignment returned `chair:true`.
This is a legal-bounds/emitter/assignment gate, not identical historical geometry.
After two further days all six orders were still unvalidated; no production or score
improvement is claimed. The full candidate test entry point completed 62 tests, exit0.
