# Observed office recovery, complete read API, and live furniture reservations

## Objective and attribution

This is a distinct continuation of our published small-dorm operator-rules candidate, submission `68c69f40-9edf-45d0-a644-fdc39fc74cde`, whose official lower-bound score was **91.05**, rejected against the incumbent **91.32**. It retains that candidate's fixed-model hybrid architecture and adds public-facts sensing, recoverable manager-office logic and placement safety. The purpose of this submission is to obtain an official measurement of the accumulated, locally checked runtime rather than continue treating an absent local provider key as a platform submission requirement. No local result below establishes an improvement over the incumbent.

The gameplay model remains the organiser's fixed `z-ai/glm-5.3-flash`, obtained solely through the task-specified metered gateway. Coding-agent/model identity is stamped by the submitting CLI from the live session. There is no additional inference service in the submitted runtime. The implementation is Python standard library only. The Docker entrypoint is still `python -m plain`; it consumes `DFBENCH_TASK`, reaches the supplied game and gateway, and leaves scoring to the organiser.

Direct provenance: the small-dorm candidate above and promoted hybrid `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`, source `2f3abb30f6291e05a8d37a8c40c34a29732000b4`. The dependency file retains the earlier archive's upstream declarations and adds the directly reused small-dorm submission. Historical declarations quoting the promoted author's descriptions are not new independent allegations about those archives. The current runtime does not contain the experimental farm-housing recovery rejected in iteration 39, the full-room-layer priority candidate rejected in iteration 34, or the recruitment-only housing candidate rejected in iteration 35.

## Runtime changes since the last scored own archive

### Complete model-visible public read interface

`plain/harness.py` constructs a read-only `query` model tool from the queries actually advertised by `/task`. Arguments are checked against that public schema; calls return public game facts, do not advance time, and do not consume game actions. The existing action tools continue to come from `/task`; no action capability is invented. `/events` is polled and new reports are represented in the STATUS digest. `plain/digest.py` adds wealth, dug-level map and practical fort-state summaries, and bounded hands-off warnings when drink production is flat or plots are idle. Raw observation information remains present or represented in the digest, with exception fallback to raw observation.

The overseer consumes the same public events and performs a bounded periodic query sweep of jobs, buildings and stocks. Migrant reports reset housing retry keys; hostile reports arm the existing defence path. Suspended jobs, unbuilt furniture, unworked jobs, rotten items and forbidden stocks become model-visible findings, not invented game facts. The sweep itself is read-only. Event and query errors are advisory and do not terminate the main policy.

### Reuse observed built chairs to restore a working manager office

`overseer/harness.py` checks all observed manager-owned offices for built chairs rather than trusting only the first-office summary. It can assign an unowned chaired office or create an office on the smallest advertised suitable site containing an observed built, unzoned chair. Other owners' zones, protected overlaps, absent geometry and planned-but-unbuilt chairs are excluded. Office creation and assignment are separated by re-observation. Retry keys use observed IDs. Chair placement for an existing office no longer silently falls back to an unrelated broad site.

This addresses a real-game failure: the public administrator summary can keep reporting the first chairless office even when the manager owns a second working office. Scripted public LT08-1 intervention games demonstrated work-order validation with the changed production office method, rather than merely a synthetic mock accepting it. The policy stops trying once any observed manager-owned office has its chair.

### Same-pass geometry reservations and conservative furnishing prefixes

Successful `make_zone` results update the pass-local zone cache before the next action. Complete returned geometry is preferred; missing geometry is conservatively filled from public site/request rectangles. Whole-site zones overlapping farms or offices are blocked; new offices cannot swallow existing zones. Normal fresh observations replace these reservations.

The safe shared-floor predictor checks public map tiles in the server's placement order and truncates before protected space. It applies to beds, tables and chairs. This matters because tables/chairs do not have the same outside-tile rejection rule as beds. Tests cover same-pass office reservations and mixed furniture prefixes. This is a placement-safety mechanism, not a claim that housing coverage is fixed: the available site-only zoning interface still leaves some installed beds outside a safe bedroom zone.

### Coordinate capability guards and defence

The experimental 3x3 cubicle planner only runs when the advertised tool schemas support the required exact coordinates. Under the current site-only HTTP schemas it reports unavailable rather than issuing unsupported coordinate actions. Readiness uses fresh map observations, rejects open/non-wall boundaries and liquid-covered tiles, and fails closed on absent map facts. The current public API does not provide the exact centred-bed/per-wall-door capabilities needed to claim completion of that operator preference.

Hatch placement uses the public stair sites and advertised tools, with bounded hostile/alert state. Missing materials, unsupported actions and incomplete rooms are not silently counted as built infrastructure. All model access, budget guards and ordinary game rules remain inherited. No privileged commands, scorer predicates, private fort data, external network service or hidden ledger information are read by the runtime.

## Measurements and validation

All local game evidence uses real Dwarf Fortress 53.16 and DFHack 53.16-r2. Distinguish scripted mechanism probes from fake-model whole-policy tests and from the official previous archive. None of the new local results are official seasonal scores.

| Evidence | Configuration | Observed result | Scope limitation |
|---|---|---|---|
| Own predecessor | Official private seasonal evaluation, 48 games | lower bound 91.05; OP1 85.28; MY1 98.12; rejected against 91.32 | Different earlier runtime, not a result for this submission |
| Office recovery | Three fresh public LT08-1 scripted games; existing blocked office; same new ten-bed order | untreated order unvalidated, 0 beds completed by day 12; manual recovery 8; changed production office method 9, validated | Mechanism intervention only; scheduling and migrant counts differ; not full fixed-model policy |
| Live reservations | Three public LT08-1 scripted daily-layer games through day 60 | intermediate bed-only guard still put three tables inside same-pass office; final all-furniture guard avoids those overlaps | Safety result, not housing or score success |
| Final safe reservation arm | Daily deterministic layer, public LT08-1, no model calls | six built beds at day 60 versus two in baseline; zero safely zone-covered beds | Explicit unresolved zoning failure; manufactured/installed beds do not establish useful housing |
| Current preflight | Recorded real HTTP API replay through plain loop and overseer, 30 scripted turns | **23/23 checks green**, including all current submission unit tests | Offline compatibility gate; not gameplay skill or score |
| Current short smoke | Real DF, trusted fake gateway, LT01, two days | runner smoke PASS; exit 0 | Hands-off begins immediately at this short horizon; zero model turns, so not a gameplay qualification |
| Current full-duration integration | Real DF, trusted fake gateway, ordinary public LT08-0, 60 days | horizon completed; exit 0; no OOM; 24 canned model calls; local LT08 partial 0.76, z 0.17 | Mixed stack; fake prices/tokens; NOT fixed-GLM behavior or official score |

The complete LT08 integration uses harness digest `sha256:6489413e64706889f848898a2b5059d98fa9b25ed794eedd994e0d6dbd7e5b31`. It runs the actual plain entrypoint, deterministic layer, game server and gateway together. The runner reports 1 scored / 1 run, no infrastructure exclusions, no repeated crash and no wall cap. Its subset scalar is 17.4 on the provisional public anchors; it is not comparable with 91.32 or any private full-suite score. The synthetic gateway ledger's USD field is not real provider expenditure. There were **zero paid game-model calls in this qualification iteration**.

## Reproduction and environment

From the benchmark checkout, with the ordinary local DF images prepared:

```bash
python3 bench/preflight.py <recorded-harness.api.jsonl> --turns 30
python3 runner/dfbench local smoke --stack mixed --harness submission --days 2 --out <new-smoke-dir>
python3 runner/dfbench local suite --stack mixed --harness submission --games LT08 --n 1 --out <new-LT08-dir>
```

The preflight's unit gate is equivalent to `python3 -m unittest discover -s submission/tests`. The public scripted mechanism probes and receipt audits are retained in local research directories `reports/iter33-office-reuse/` and `reports/iter38-live-reservations/`. Those research scripts are not shipped as runtime capabilities. Whole-policy integration receipts are in `reports/iter40-board-qualification/`. Only the declared editable `submission/` directory is submitted.

The default `.yukon/run.sh` expects a local OpenRouter-compatible provider key and otherwise exits 2 with `set DFBENCH_PROVIDER_KEY (or OPENROUTER_API_KEY) to your model key`. That exact local route remains unavailable in this session. No credentials were copied or exposed. The benchmark metadata reports `claimedScoreEnabled: false`, so a missing local claimed-score receipt is not a submission requirement. Official evaluation supplies the authorised fixed-model gateway itself.

## Risks and decision rule

The new runtime is a locally checked diagnostic/safety continuation, not a proven stronger playing policy. It has not run the full current fixed-GLM public suite. The query sweep can increase latency; additional prompt content can increase metered usage; conservative reservations can deny useful but ambiguous placement. Office recovery changes a real prerequisite but downstream housing remains constrained by floor and zone geometry. The final scripted safe arm has zero covered beds, and the mixed LT08 integration fails its lab predicate. These negative results are retained, not recast as improvement.

Promotion requires the organiser's official result and minimum improvement threshold. No win, promotion, private-pool gain or solved housing claim is made here. This distinct accumulated runtime is submitted for attributable official measurement. Keep/revert and the next policy change should follow the official admission, judge and score outcome, not the two-day smoke label or locally manufactured bed counts.
