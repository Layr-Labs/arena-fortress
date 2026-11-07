# Fortress harness: public-facts advisor and recoverable failure memory

Starts from the organisers' plain baseline at main commit `75d40aa6adc8ee1b3f3b5ad1d74c3674f1ff3abf`.
Only `submission/` is modified. The task still supplies the fixed model and metered gateway.

## Changes

- Retains all observation facts and adds bounded `harness_status`: manager/office and production prerequisites,
  distinct-time stock trends, built-furniture housing facts, dug soil rooms, and hands-off reminders.
- Remembers at most eight deterministic action failures beyond the conversation window. Refuses identical retries
  only while tick, public facts and successful-action epoch remain unchanged. Progress unlocks retries.
- Offers `inspect_fort` for the intersection of documented read-only query names and `/task` capabilities.
  Query arguments are allowlisted; output is bounded valid JSON with explicit truncation.
- Adds a public-manual-based production/verification checklist. The model still chooses all game actions.
- Adds a standing-guard doctrine and bounded public `defense` diagnostics: carried weapons, eligible adults,
  worker-preserving recruitment caps, immediate threat/shelter advice and relief for stressed or labor-starved guards.
  This API offers one squad and no training command. Stationing is not training; armor templates are not worn armor.
- Executes at most four model-selected independent calls sequentially, stopping on failure, inspection or time
  advance. Every skipped call gets a result. Fresh batch results stay intact for the next request; the stall
  guard still counts individual actions. The model chooses the actions; the harness does not invent them.
- Pins the Python Linux amd64 image digest; no extra Python dependencies.
- Losslessly packs consecutive same-key public `dwarves` and `map.sites` records into explicit column/row tables
  when they pay for their model-visible explanation plus a margin. Other fields and all cell values remain
  unchanged. The advisor still receives the original API objects; model-selected actions/guards are unchanged.

## Verification status

Latest offline candidate (supersedes historical frontier references below): authenticated promoted leader
`3ed866583d0cab5a7392701f02939d7e8707f1f4`, submission `9b597a76-9bf9-4923-a9d4-1c8ee83067a9`, scored **81.30**.
Our rejected official predecessor `d8164ec2` scored **75.84** (-5.46). The new packing candidate has no gameplay
or official score. Eleven existing batch tests pass. Paired rendering of 1,240 nonterminal public observations
across 33 retained traces reconstructs all parent facts exactly and reduces UTF-8 message bytes 21.96%, including
its explanation. Those traces include repeated seeds and provider-contaminated games: this measures encoding,
not independent trials or survival. Fake model actions were held fixed; model comprehension, token/cost savings
and strategic benefit remain unmeasured. No new builds, gateway calls or submissions were made.

52 focused regression/existing HTTP-fake integration tests passed for the cadence candidate (5.163 s).
These include the original 38 cases, 11 bounded-batch/history/stall regressions, two farm-capacity
regressions, and a production-cadence prompt regression. Later fishery/growth prompt additions passed
the focused prompt entry point; those unit checks are not evidence of strategic improvement.
The standing-guard candidate also completed a native-Z.ai real-DF 14-day public MY1 run: 15/15 survivors,
14 successful model calls, no provider errors, and $0.02184109 reference-price usage under a custom $0.05 cap.
That fort had zero free weapons throughout; no squad was formed, so armed deployment remains unverified.
See `NOTE.md` for the exact test reproducer. Fake games are not strategy or score evidence.

Rootless Docker setup, image builds and real DF smoke are complete. Before the military changes, the candidate
completed a seven-day OP1 game with native Z.ai GLM-5.3-Flash: 25 successful model calls, no provider errors,
horizon finish, exit 0, and $0.02140337 at reference token prices. A local-only gateway image translated model and
reasoning fields; it is not part of the submission and is not the pinned official Together provider. Neither that
short run nor unit tests establish a score gain. Matched native-provider LT08 comparisons now exist: the inherited advisor/guard version failed 0/2 with
mean partial 0.82 and local subset lower bound 37.28; the untouched plain baseline failed 0/2 with
mean partial 0.86 and local subset lower bound 47.98. These small single-task, native-provider results
are NOT official-comparable and cannot be compared numerically to the 77.10 full official frontier.
The corrected batching version completed at local subset LB95 60.39, mean partial 0.87, 0/2 passes,
and $0.134389 reference credits. A separate farm-capacity-advice variant (current code) passes 51 tests
and is in a new matched local A/B; it has no score yet. Official predecessor d8164ec2 was rejected
at 75.84 vs 77.10, with MY1 gains but OP1 regression; these official results are not for the new code.

`NOTE.md` is the candidate method note; `dependencies.json` declares material published-note inspiration.
Use these files directly with `--note-file submission/NOTE.md --dependencies-file submission/dependencies.json`
when a measured candidate is ready. Do not copy credentials into this directory.


## Current public development evidence

Official predecessor remains rejected at 75.84 versus frontier 77.10. No new official score or win is claimed.
Completed local native-Z.ai paired public OP1: batching/farm candidate point 61.2, LB95 57.8 versus
untouched baseline point 63.1, LB95 45.9 (two games each). Candidate supply regressed despite better
housing/growth and fewer zero-food days; credits were 0.3018 versus 0.1654. This is not an official-provider
comparison and n=2 does not establish a lower-tail gain.

Matched LT08 farm-capacity advice versus frozen batching control: 0/2 passes in each, partial 0.8844 versus
0.8934. Adding farms did not establish sustainable production. Current experimental prompt additions explain
periodic manager checks and stack-based brew jobs, small daily batches, conditional raw-fish/Fishery diagnosis,
and explicit drink-growth targets above the handover stock when the task requires that. Ordinary stock-reserve
thresholds can leave brewing idle throughout hands-off. These additions remain local strategy hypotheses;
model-selected actions and all batch/guard semantics are unchanged. See NOTE.md for exact limitations.

Latest terminal LT08 result: the goal-aware handover pair passed 1/2 with mean partial 0.9694, versus the
preceding fishery-advice pair 0/2, partial 0.8702 (identical first observations, native provider, n=2). Exact-image
MY1/OP1 regression checks are pending. This is a measured local lead, not an official-comparable improvement.


### Current blocker and offline candidate

Weighted checks are no longer pending: native Z.ai returned HTTP429/code1113 insufficient balance. Cadence
OP1 model control stopped early; its generated scores are contaminated despite ordinary runner finish and
zero infra exclusions. Goal-aware MY1 received zero successful calls, was cancelled, and OP1 was not launched.
Correction after endpoint inspection: those runs explicitly used the standard API base
`https://api.z.ai/api/paas/v4`, NOT the Coding Plan base `https://api.z.ai/api/coding/paas/v4`.
The operator's screenshot shows abundant Coding Plan quota. Standard API error1113 does not demonstrate
exhausted subscription quota. Z.ai's current FAQ and usage policy restrict subscription benefits to supported
tools/products; this custom game harness is not listed. Do not silently reroute or impersonate a supported
client. Confirm supported use with Z.ai or authorize funded standard API access before resuming live checks.
No credentials, billing, or provider settings have been changed.
No new official submission.

The current source also adds bounded geometry-specific office-repair diagnostics: observed built chaired
offices/owners and advertised site boxes containing built chairs. It makes no game calls or readiness claims.
13 existing advisor tests and the public trace replay passed; no live gameplay or score gain is measured for
this latest change. The frozen goal-aware image remains a separate candidate from this unbuilt source.

### Searchable catalogue repair (offline verified)

`inspect_fort` previously truncated the approximately30KB manager-order catalogue to a2600-character text
prefix. Real retained LT08 and OP1 queries had102job types and126reactions, but their prefix exposed flag
and item-type lists, not `PrepareRawFish` or the brewing reaction. There was no way to narrow this query.
Catalogues now return a section index; select a `section`, optional case-insensitive `search`, and `offset` /
`limit` to retrieve complete public entries. Follow `next_offset` until null. These selectors stay local and
are never sent to the game API. Dictionary entries preserve both key and value; single overlarge records
fail explicitly rather than being silently truncated. Ordinary query behavior is unchanged.

Focused verifier:11inspection tests passed. Replay of all3retained manager-order query responses recovered
every catalogue entry exactly in16pages per response; maximum page3383characters under the3400bound.
Searching job_types for fish retrieves `PrepareRawFish` / `ExtractFromRawFish`; brewing reactions are also
accessible. Inputs remained unchanged. No live-model run, score improvement, build or official submission
is claimed for the catalogue repair. Reproduction artifacts are in `reports/iter3-catalogue/` in the local
research checkout (not part of the submission archive).


### Partial furniture success barrier (offline verified)

`place_furniture` can return `ok:true` with `n < requested`. The harness now preserves
that result, adds `harness_placement` with the unplaced count and an item-cap versus
space/tile diagnostic, and stops the remaining batch for a fresh observation.
Designations are never counted as built furniture. A site's `free` flag is not a
free-floor count. Full placements retain independent batching. The model still
chooses every action; smaller-count retries are not automatically blocked.

17 focused batch/placement tests pass. A paired emitter replay of 259 real retained
public results across 14 traces finds 50 partial successes: frozen control set no
barrier on them; candidate sets 50/50. Twelve smaller-count same-day follow-ups
failed `no_space`; this is not a prediction of saved calls or a measured score gain.
No build (`ANGEL_NO_BUILD=1`), model call, or official submission was made for this
change. See `NOTE.md` for reproduction and pending authorized gameplay checks.

### Explicit zone dimensions (offline verified)

`make_zone`'s public dispatcher accepts optional `w` and `h`, and its emitter
requires each dimension to be 1–20. Some advertised site boxes are larger, while
the task schema omits these overrides. `prepare_tools` now exposes those two
optional integers only on an advertised `make_zone` site tool. The model chooses
the dimensions; the harness never clips or moves a rectangle. Omitted axes keep
the site's default dimension. The schema and prompt warn that the rectangle starts
at the site's top-left and must include the intended built furniture. If it cannot,
choose another site. Coordinates, kinds, required fields and API validation remain
unchanged; task schemas are deep-copied, not mutated.

18 focused zone/batching tests pass. Frozen-parent replay of 147 retained public
zone calls across 25 traces preserves actions/results exactly with fixed model
outputs. Seven separate, explicit test interventions reproduce an oversized-site
rejection, then reach the real Python zone emitter with legal dimensions that
include all observed built chairs in each original site box. DF/quickfort and zone
lookup are stubbed: this does **not** establish successful in-game placement,
real-model selection, score gain or saved cost. A counterexample with a chair
outside the first 20 columns documents why automatic clipping is not safe.
No builds, gameplay/model calls or official submissions were made for this change.


### Office assignment is not order validation

If the public office reports a built chair but observed orders remain explicitly
unvalidated, the advisory warns that production has not been established. Inspect
the manager's public job/needs/access and order state, allow a short interval, and
recheck; do not infer a fixed validation delay or rebuild/cancel/re-add to refresh.
A model-free real-DF check observed six unvalidated orders two days after successful
chaired-office assignment. No model/score improvement is inferred from that check.
