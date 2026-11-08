# Current submission: executed replacement housing and durable dorm capacity

## Current state and request for official measurement

This archive submits the retained gameplay runtime from local checkpoint `c9e7555` for its first official measurement. It is NOT a resubmission of an unchanged published runtime. Later local experiments were rejected and reverted; none of their fish-throughput, second-office-digest, spatial-furniture, dining-only-guard, or earlier-livestock-trigger changes are present. The chronological notes below describe earlier checkpoints and rejected experiments; this section takes precedence when identifying this archive.

Coding agent: angelX. Underlying coding model: gpt-6.1-sol, as stamped by the live harness. The fortress-playing model remains exactly `z-ai/glm-5.3-flash`; no alternative game-playing model is bundled. Runtime changes are confined to submission. No game API, scorer, task pool, route budget, or trusted recorder changes are submitted.

## Distinct runtime mechanism

Compared with the last published office/soil repair, the retained runtime makes replacement dorm excavation reachable even when a missing dining role previously prevented it. Office remains first; full-dorm bed deficits can precede dining. Accepted nonfarm room rectangles remain reserved, excavation must be disjoint from observed plots and protected offices, and dining fallback cannot consume reserved future bed space merely because present beds are temporarily sufficient. For non-surge long games at day200 or later, initial dorm sizing anticipates a target of30 beds rather than spending all room sites on the starting seven citizens. Migrant-sized dorms, low-input hands-off brewing, bed-first production and earlier second-carpenter eligibility from preceding unpublished checkpoints are retained.

## Reproducible retained evidence and limits

`python3 -m unittest discover -s submission/tests -v` passes119/119 tests, re-run for this submission preparation. The source and receipt audit `python3 reports/iter47-replacement-capacity/audit.py` independently checks29 complete real-DF games and the frozen candidate. Three mixed-stack OP1 games improve mean58.33 to70.13, with19/19/21 built beds for17/17/19 citizens. However mixed stack means real DF with a fake model. The actual GLM local comparison is59.9 versus60.1: essentially flat and NOT confirmation of the mixed gain. Twelve final lab regressions passed, with source differences labelled by the retained audit. MY1 mixed means91.90 versus92.77, n3 each.

All those results use public forts and are NOT official-comparable. Actual-model local runs use the existing native Z.ai alias/reasoning compatibility route, not the organiser's pinned Together route. The organiser must supply the official private-pool result. Reference per-game credits and wall caps are unchanged. Full-year observations identify food replenishment as an unresolved weakness even when housing is adequate. Extra endpoint food, extra Fishery capacity and earlier slaughter triggers were each insufficient in subsequent local experiments, which are not in this archive.

A fresh actual-model LT08-0 bridge is frozen separately under reports/iter53-stage-gate. Its source identity and eventual result will be reported separately; a pending game is not claimed as validation success. This submission is an information-seeking official measurement of the best retained distinct runtime, not a claim that the public games establish promotion eligibility. Authenticated frontier at preparation is91.32, minimum nominal scalar93.603 plus organiser confirmation and paired-difference gates. The preceding official submission failed the stage-one screen; OP1-only local improvement cannot establish that screen has been repaired.

## Scope, recovery, and provenance

The Docker entrypoint, facts-only API access, model prompt lineage and existing dependency declarations remain. Runtime modules are byte-identical to c9e7555 at preparation. This disclosure replaces an older leading paragraph describing an already-rejected iter50 guard. The reports and frozen source trees are local research evidence, not extra evaluator code. Credentials and private machine paths are excluded from this public note. The exact official submission identifier and terminal score will be retained locally after upload. A queued or running submission will be described only as pending. No official win or score delta is claimed before that terminal result.

---

## Historical checkpoint notes (not the current-source specification)

## Iter50: spatial furniture guard rejected; c9 runtime unchanged

Actual-model public OP1 pairs: 64.2→87.5, then 90.6→68.0; mean +0.35, no reliable gain. Candidate eliminated model-caused incompatible furniture placements, but model-created DiningHall over a dorm still caused seven deterministic beds inside dining space in confirmation. Rejected; gameplay restored byte-for-byte c9e7555. ZERO NEW OFFICIAL SUBMISSIONS. See reports/iter50-spatial-guard/RESULT.md, audit.py --confirmation (PASS four complete 336-day real-DF actual-GLM games), and frozen guard tests (11/11). Candidate-stage full tests 130/130. Model zone-creation geometry guard is a newly evidenced but untested lead, not an accepted repair.

## Unsubmitted iter45 throughput candidate

The retained candidate adds low-input window brewing (two plants), migrant-sized
dorm capacity, conflict-aware early housing reservation and protection of its
shared placement prefix, earlier second-carpenter eligibility, larger pending-
deduplicated migrant bed batches, and bed-before-dining production. Public
real-DF/fake-model lab regression is 11/12 passes; housing remains unreliable
in one LT08 variant. A native Z.ai actual-model LT08-0 bridge versus promoted
2f3abb30 yields partial .998 vs .9341, but outcome61.7 vs64.1 and different
populations. Candidate still fails drink replenishment504→500. Therefore this
is NOT official qualification. Native pair used83 calls,$.160622 reference
credits; zero provider errors; no official submissions.113 unit tests pass.
Reports/iter45-capacity-throughput/RESULT.md and audits retain all34 real-game
receipts, negative results, source identities, and translation limitations.
Prior iter44 notes below describe the previous checkpoint, not this runtime.

## Unsubmitted iter44 housing reservation repair

Local public real-DF/fake-gateway runs found three allocator conflicts: waiting
for four *built* farms misses early site assignment; anonymous F sites consume
expanded dorm footprints; dining fallback fills that dorm before beds finish.
The current candidate counts committed farm rooms, retains accepted nonfarm
excavation rectangles, excludes overlapping farm sites, and defers dining on
reserved housing while beds are short. Office and initial four-farm priority
remain. Final LT08-0 runs built 44 and 42 beds (baseline 2), but BOTH still fail
bed-per-citizen and drink-replenishment clauses. LT01-0 passes; 101 unit tests
pass. This is NOT an official score improvement or submission qualification.
See reports/iter44-balanced-soil/RESULT.md and audit.py for frozen sources,
seven full-game receipts, nonempty/scorer/hash/coordinate verification, and
random-population caveats. No new submissions or provider calls in iter44.

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


## Local follow-up: idle-repeat emergency brewing (not submitted)

A targeted runtime follow-up changes only the emergency drink-floor pending
check: validated inactive daily repeats without spawned jobs no longer count as
brewing underway. Active, unvalidated, unknown-state, and unfinished one-shot
orders still suppress duplicates. In a controlled public LT01 drought-fort
comparison with only the existing window-prep repeat present, the submitted
runtime stayed at zero drinks while this patch reached 35 by day 10. Eight
focused unit tests and the source/receipt audit pass. This deliberately isolated
counterexample is **not** a full-policy game, predicate pass, suite improvement
or official result; normal standing orders may avoid the failure. No new
submission or model call was made for the follow-up. Full evidence and limits:
`reports/iter41-idle-brew/RESULT.md`. The existing official submission
`b2c46c0b-e931-43d2-9c80-8c150b029250` evaluated the older runtime; its terminal result is recorded below.

## Mandatory evidence review (iter43; supersedes pending-status language above)

The official submission is **rejected**, score **0**, stage 1 only. Its stage-1
upper bound **99.85** was below the leader's stage-1 point **100.6**, so OP1 was
not played. Its partial-suite lower bound **90.96** is not a comparable full-suite
score. The leader remains **91.32** at `2f3abb30f6291e05a8d37a8c40c34a29732000b4`.
The minimum full-suite promotion score is **93.603** (91.32 × 1.025), plus the
organiser's confirmation and positive paired-lower-bound requirement. The earlier
full-suite candidate scored **91.05**, leaving a **2.553** lower-bound gap.

Current runtime is the unsubmitted `f9a119c` soil-office follow-up, not the submitted
`a79f719` runtime. Its retained mixed-stack LT08-0 game validates all five remaining
orders and builds an office chair, but still fails: **2 built beds / 45 citizens**,
and drinks decline **565 → 525** during the hands-off window. Local `home.beds_placed`
is a built-bed count, **not zone-covered beds**. The lab predicate counts all built
beds without requiring a bedroom/dorm zone. The older safe arm's six built beds
therefore count even with zero zone coverage; it still lacks 41 beds for 47 citizens.
Operator bedroom requirements remain separate and are not relaxed by this scoring fact.

The idle-repeat repair remains a controlled robustness result (35 vs 0 drinks), not
a demonstrated full-policy gain: natural LT01 passed for both arms, while local O
was **93.3 baseline vs 84.2 candidate**. No causal/generalized regression estimate is
claimed from that single mixed-stack pair. Lowering the window plant threshold did
not fix LT08. Old audit scripts that compare to the mutable live runtime must be
anchored to their historical Git object, not interpreted as disproving frozen receipts.

Nine historical receipt audits and six retained LT08 predicate recomputations pass
in `reports/iter43-evidence-review/verification.json`; report and reproducible offline
command are in that directory. No new game, model call or submission was made for
this review. No win or score improvement is established.


## Iter47 unsubmitted capacity follow-up (2026-11-08)

Live runtime now retains the verified replacement-capacity follow-up, not b21a431.
Missing dining no longer blocks full-dorm replacement, disjoint replacement
excavation is permitted, dining cannot consume reserved dorm space after a
short-lived bed surplus, and non-surge full-year dorm sizing reserves at least
30 beds of initial capacity. Manager/office remains first; excavation overlap
checks and operator-rule tests remain. Bedroom operator requirements remain
partial as documented; no new claim of full bedroom compliance.

Real-DF/fake-model OP1 n3 mean58.33 ->70.13; built beds8/8/8 ->19/19/21.
Actual GLM-5.3-flash native Z.ai OP1 pair59.9 ->60.1, housing13/13 ->15/15,
reference spend0.259920 ->0.198654. This does NOT confirm the fake-model gain.
Both native arms fail supply (0.558/0.561), with full housing: further housing
work alone is not justified. Mixed MY1 n3 mean91.90 ->92.77; 12 local lab passes
(3 LT08 reservation-only same short-horizon behavior,9 LT01/02/03 final source).
119 unit tests pass; score/source/API audit passes across29 real-DF games.
Exact sources and receipts: reports/iter47-replacement-capacity/RESULT.md,
audit.py, verification.json, evidence-hashes.json. ZERO SUBMISSIONS; unqualified
candidate retained for supply follow-up, not a competition score improvement.
Authenticated frontier still91.32, source2f3abb30, nominal target93.603 plus
organiser qualification. No win or promotion claimed.

## Iter48 — fish throughput rejected, runtime restored
See `reports/iter48-fish-throughput/RESULT.md` and `audit.py` (PASS, 12 real-DF games). New explicit daily raw-fish cleaning plus a second Fishery dispatches two manager jobs but does not qualify: mixed confirmation mean 69.83→74.80 is variable, and fresh native actual-GLM OP1 comparison is **90.6 baseline → 66.3 candidate**. Raw-stock trigger also mixed stack counts with flagged-item counts; rejected. Runtime restored byte-for-byte c9e7555; no official submission. Two actual-model games: 287 calls, $0.496727 reference cost. Frontier checked 91.32. No promotion/win claimed. Next distinct observed lead: 20 no-space furniture rejections in native baseline; performance benefit of repair is untested.

## Iter49 — second-office digest repair rejected after native pair
`reports/iter49-manager-digest/RESULT.md` documents a new factual digest bug: the API manager summary reports only the first owned office, hiding a second owned built-chair office. Replay removes seven false repair prompts in retained iter48 baseline observations; raw facts remain unchanged. Focused tests 11/11 passed. Fresh complete336d real-DF actual-GLM native pair **87.5 baseline →67.7 candidate**, calls124→112 and rejected actions17→7. No objective gain; earlier office setup precedes the candidate's first correction and cannot be attributed to it. Frozen-source/receipt/replay audit PASS. Runtime restored byte-for-byte c9e7555; ZERO NEW OFFICIAL SUBMISSIONS. Frontier91.32. Next distinct unverified lead: enforce the deterministic layer's spatial reservations on model-issued furniture/zoning rather than trusting the model not to occupy future bed/office space.


## Iter51 — dining-only model zone guard rejected; c9 gameplay restored
Four complete actual-GLM native-Z.ai public OP1 games, audit PASS. OP1-1 73.5→59.2; OP1-0 87.5→89.3; mean80.50→74.25. Guard executed (3/1 local refusals), but model offices still overlaid dorms and candidate calls rose146→222 /116→196. Food runway, not bed count, explains the negative seed:25 built beds/22 citizens, housing1, drink1, food.537. Detailed source/receipts and eight-prior-game food attribution: reports/iter51-zone-overlay/RESULT.md and verification.json. Frozen candidate12 tests, existing119 tests PASS; restored existing119 PASS. No official-comparable gain. Gameplay byte-identical c9e7555; ZERO NEW SUBMISSIONS; frontier91.32. Cross-zone/cross-layer ownership and ingredient-vs-edible food semantics remain unqualified leads, not fixes.

## Iter52 — earlier livestock fallback rejected (2026-11-08)
Frozen actual-GLM real-DF pairs: OP1-1 87.5->60.4; OP1-0 90.6->90.6, all336d. Threshold4->8 food/citizen executed six/four extra-band accepted deterministic slaughter actions; no reliable improvement. Candidate123 tests; restored119. Audit `reports/iter52-food-buffer/audit.py --confirmation` PASS. Runtime restored byte-for-byte c9e7555; ZERO NEW SUBMISSIONS, frontier91.32. New evidence: candidate OP1-1 ends with5.62 food/citizen vs baseline5.57 yet only45.1d fitted runway; final-window trend, not endpoint stock, fails supply. No causal score penalty inferred from stochastic games. See frozen RESULT.md/outcome-breakdown.json/verification.json.
