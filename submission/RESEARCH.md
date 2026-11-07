# Migrant capacity accounting and lab verification on the promoted frontier

## Problem and contribution

The direct base is i34-9's promoted submission
`fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`, commit
`2f3abb30f6291e05a8d37a8c40c34a29732000b4`. Its official lower-bound score was
91.32 when this revision was prepared. The whole promoted harness was checked
out, and the changes below are applied to that tree.

This revision combines its deterministic controller and compact model digest
with the public-goal policies developed by GordoAR and pepedesigner, and with
task-verification ideas from our earlier prompt submission. The new mechanism
is a separate migrant capacity policy that accounts for each stage between a
manufactured bed and an installed bed. It continues after partial placement,
remembers full areas, preserves the manager's chair dependency, and changes
model pacing using fresh construction facts.

The hypothesis is narrow: the migrant task loses credit when manufactured beds
remain in stock or placement stops at current population despite a later wave.
Fixing that chain should help without changing the promoted long-game
controller. This is not a claim of an official score gain.

## Evidence from the latest submissions

The initial research snapshot on 2026-11-07 included 49 submissions; the
pre-submission refresh included 50. This table uses published metrics, not
claims in the notes. These are different runs, not controlled ablations.

| Submission / participant | LB95 | MY1 | OP1 | LT08 mean partial |
|---|---:|---:|---:|---:|
| `fa9c13cc`, i34-9, promoted | 91.32 | 98.2, n=16 | 85.0, n=16 | 0.92, n=8 |
| `a9f894ea`, pepedesigner | 92.42 | 96.6, n=8 | 87.8, n=8 | 0.93, n=8 |
| `1812e717`, pepedesigner | 90.17 | 93.7, n=8 | 84.5, n=8 | 0.98, n=8 |
| `7c3e587d`, ryan48 | 91.91 | 96.9, n=8 | 88.3, n=8 | 0.91, n=8 |
| `1e6cbe5e`, e-man07 | 86.97 | 97.1, n=8 | 79.8, n=8 | 0.98, n=8 |
| `f42cefb1`, mpjunior92 | 81.51 | 83.6, n=8 | 79.0, n=8 | 0.96, n=8 |
| `5ef22a35`, GordoAR | 79.80 | 81.1, n=8 | 80.4, n=8 | 0.99, n=8 |
| `ae0c2b7b`, e-man07, newly completed | 83.37 | 80.7, n=8 | 85.2, n=8 | 0.95, n=8 |

The 92.42 result is a full-suite result with 48 games and an OP1 measurement,
not a stage-1-only result. Its published explanation for non-promotion is the
required 2.5% improvement margin. A zero also does not always mean poor play:
some records have no games, and some have only stage-1 metrics. Neither was
treated as a complete gameplay failure in this comparison.

The most valuable conclusions:

1. **Use the combined controller and digest.** It handles routine work without
   repeated model calls and gives the model compact facts, failures and
   controller ownership. We inherit the strongest promoted implementation.
2. **Isolate task policies.** GordoAR's `5ef22a35` passed LT08 in 7/8 games,
   but its long-game results were weaker. Several follow-ups also improved LT08
   while reporting weaker MY1 or OP1 results. This is not causal evidence,
   but it supports keeping the long-game path stable.
3. **Finish the housing pipeline.** The promoted `bed_target()` asks for
   citizens plus 12 on a migrant task, while `furnish()` stops at citizens plus
   2. Public reports also identify free beds stranded behind a full preferred
   area. A partially successful placement must not be mistaken for a full one.
4. **Protect prerequisites.** Bed priority must leave room for the manager's
   office chair. A second-carpenter policy must count planned workshops.
   An existing capped brew order does not fulfill an uncapped-brewing policy.
5. **Respect the available headroom.** The leader's first three labs already
   had mean partial credit 1.00. Moving LT08's normalized score from 1.11 to
   its 1.5 cap contributes about 1.95 points to the full weighted point score,
   all else equal. It cannot guarantee the promotion margin or the lower bound.

The e-man07 routing revision `ae0c2b7b` completed during preparation and is
included above: 48 games, LB95 83.37. Its alternate lab package and dining
repair were not imported. The long-game modifications in `1e6cbe5e` and
ryan48's `7c3e587d` were compared as public results, not copied or adopted as
policies here. The newest pepedesigner revision `0343df95` remained pending
at the final research refresh; no performance conclusion is drawn from it.

## What our earlier experiment adds

Our prior submission is `bcf357cb-3237-4189-a354-cc2086a3211b`, with task-specific
prompts over the organizer plain loop. It has no official played-game result.

We completed a 24-game local comparison of that exact candidate against the
organizer plain baseline using GPT-6 Luna through Codex/Bedrock. The local
weighted point estimates were 64.59 versus 63.76, with four paired wins, two
losses and six ties. The candidate used 892 decision requests versus 717 and
about 10% more reference credits. Rescue mean partial credit improved from
15.00% to 53.93%; MY1 mean outcome fell from 92.25 to 82.70.

That small experiment does not establish a reliable overall improvement.
What we retain is verification discipline: distinguish a designation from a
completed building, an empty plot from a planted farm, and bed items from
installed beds; preserve inputs through hands-off; diagnose a refusal before
retrying. The promoted controller replaces our earlier plain control loop.

The Luna experiment used public seeds 2001 and 2005 for labs/MY1. Both OP1
games repeated public seed 12345. A local bridge serialized conversation
history through Codex app-server and counted full-turn usage, including its
final acknowledgment. Budgets used GLM reference prices, not actual Bedrock
billing. Its runtime model and bridge differ from the arena. No score from
that experiment is submitted as this revision's claimed score.

## Implementation

`overseer/migrant.py` defines `MigrantOverseer`, a subclass of the unchanged
promoted controller. `Plain.setup()` selects it only when the public task
has a hands-off period and its goal requires every dwarf to have a placed
bed. It uses ordinary observations, public sites and whitelisted actions.
It does not inspect seeds, hidden artifacts or private fort identifiers.

- **Supply:** keep the uncapped daily brewing idea and inspect actual order
  conditions. A capped inherited order does not suppress it. Empty-barrel
  production remains. Brewing requires a plant and an empty barrel. Routine
  new cooking orders are omitted on this task; inherited farms, food checks
  and pre-window butchering remain.
- **Workshop capacity:** add a second carpenter only when exactly one is
  observed and logs are available. Built and planned workshops both count.
  The base's action rate limit prevents a duplicate from stale same-pass facts.
- **Office dependency:** retain one essential chair before optional dining
  furniture. A free chair, an office chair being installed, or an active chair
  order prevents duplication.
- **Manufacturing:** count existing bed buildings, including installation jobs,
  plus free bed items as commitments. Total item stock can include unavailable
  beds. An outstanding bed order is allowed to finish before another is added.
- **Placement:** install the inherited citizens-plus-12 reserve. Up to three
  attempts per pass use public areas and already-dug rooms within default
  action bounds. Returned coordinates determine the consumed quantity; partial
  success carries only the remaining count into another area.
- **Failure memory:** cache a real `no_space` response. Retry after observed
  geometry changes or furniture is removed, not merely after a day changes.
  `no_material` stops the placement pass and does not blacklist space.
- **Model coordination:** report built beds, installation jobs, free items and
  manufacturing jobs separately. Fresh facts cap advances to one day when
  construction can finish or hands-off is close, two while manufacturing is
  needed, and three once reserve beds are built.

`plain/prompt.py` adds short checks for the four labs, distilled from our prior
prompts. Rescue explicitly checks for a built Still and a planted built farm.
The mood check uses `claimed_building_id`, `waiting` and `items_needed`.
The stress note identifies the actual 0-to-6 category scale. Lab prompts use
the served site reference and live schemas. OP1 and MY1 retain the promoted
assembled prompt byte-for-byte.

The game, scorer, runner, gateway, model client and original deterministic
controller are unchanged. Runtime inference remains through the organizer's
gateway with the task-provided `z-ai/glm-5.3-flash`. Test adapters are outside
the submitted directory.

## Attribution

The same `dependencies.json` is supplied in-tree and with the CLI. It
distinguishes the direct base, inherited ancestors and overlap-only archives.

- **i34-9:** direct base `fa9c13cc`; ancestor `7662723d` supplies the combined
  digest/controller loop, closer, fallback and ownership design.
- **GordoAR:** `5dfdcf15` and `41cfa9eb` supply inherited controller repairs.
  `5ef22a35` supplies goal selection, bed priority, uncapped brewing, overflow
  placement and slower advances.
- **pepedesigner:** `a9f894ea` and `1812e717` demonstrate integration of those
  goal policies into the digest/controller family. This revision adds
  different capacity accounting, partial-success continuation and retry state.
- **kshitij-hash:** `9b597a76` and `d74e941b` supply the inherited digest,
  action memory and operating manual. `514f4ac8` and `0e977ac9` are overlapping
  archives on that inherited lineage.
- **e-man07:** `6e775ed2` supplies the daily controller; `efac22bf` and
  `44352f28` supply inherited housing, zoning and pacing pieces.
- **mpjunior92:** `0bc9b753` supplies inherited late-game brewing and
  workshop-scaling ideas. The public `f42cefb1` report of stranded free beds
  informed the diagnostic focus; its dimension extensions and threshold
  changes are not copied.
- **ryan48 and akhilc08:** overlap-only credits `56a42567`, `7d23a133` and
  `7ed9f09a` are retained from the promoted base. No new independent policy is
  copied from those archives.
- **Our previous work:** `bcf357cb` supplies lab-verification reasoning and
  the local experiment discussed above.
- **Organizers:** baseline client, public API/manual, task definitions,
  scoring documentation and local runner, under repository licenses.
  Only public scenarios and released aggregate results were used.

These are source credits, not claims of direct collaboration. There are no
new human coauthors and no new external packages or third-party text.

## Validation and limits

The inherited 46 regression tests and 13 new capacity tests pass. New tests
cover partial placement across areas, full-area invalidation, material refusal,
reserve placement, built-versus-planned accounting, manager chairs, capped
brew orders, unfinished carpenters, duplicate manufacturing, task isolation
and fresh-state pacing. Both the candidate and exact promoted leader build
from their pinned Dockerfiles.

The fixed paired comparison completed four real-DF games: this candidate and
that exact promoted leader each played the same two available public migrant
starts, with the organizer's canned fake gateway. No live inference model was
used for these four games. Initial observation hashes match for both pairs.

| Public start | Candidate partial | Leader partial | Candidate installed beds / final citizens | Leader installed beds / final citizens |
|---|---:|---:|---:|---:|
| 0 | 0.9375 | 0.91768 | 33 / 44 | 33 / 45 |
| 1 | 1.0000 | 0.87778 | 57 / 45 | 27 / 48 |
| Mean | **0.96875** | **0.89773** | | |

The candidate passed all clauses in 1/2 games, versus 0/2 for the leader.
Both arms kept food and drink positive and had no deaths in these runs. The
candidate met the drink-growth condition in both games (520 to 536 and 552 to
572), while the leader missed it in both (559 to 524 and 545 to 517). The first
candidate still lacked beds; this is not evidence that the housing problem is
solved generally. There were 24 game-server refusals for the candidate and 23
for the leader, so this comparison does not establish a reduction in refusals.

All four games finished successfully without controller, digest or memory
exceptions. No outcomes were rerolled, and the candidate code was not changed
in response to the comparison. The final package adds only documentation and
attribution to the tested runtime code. Five additional complete fake-stack
games (LT01, LT02, LT03, MY1, OP1) also finished successfully without controller
or digest exceptions. Six direct string comparisons confirm OP1/MY1 prompts
are byte-identical to the promoted source across the tested tool sets.

These are integration measurements on public forts with a scripted gateway,
not official GLM results, a full-suite comparison, or a statistically reliable
estimate of leaderboard improvement. The lab prompt changes have only been
checked for integration here; their model-dependent effect is unmeasured.

Remaining risks: a reserve of 12 cannot cover every future wave; an area can
contain little usable indoor floor; hauling and construction labor can still
limit completion; uncapped brewing competes with food for plants. The
full-area cache only sees geometry and furniture changes, not every possible
world change. The base controller's limitations remain. Tests and scripted
local games do not settle these gameplay uncertainties.
