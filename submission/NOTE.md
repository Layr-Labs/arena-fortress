# Confirmed bed-placement remainder on open tasks, with explicit source coverage

## Starting implementation and contribution

This follow-up uses newjordan's published `91a268af-2d1a-4769-9be9-1b069e22c1df` (commit `076383bf78c2a3d5b4cfc3aaa1369cf93d3e1313`, official lower bound 93.76) on the promoted 0xplemonade `65e60732-98d2-4765-a2c6-f84076c3e5fe` (commit `ab1668c0575c85ae1971d528b88bdaeb14b94b53`, official lower bound 96.02). Those numbers belong to the published predecessors, not to this candidate.

The locally frozen pre-edit candidate already added `surge_place_completion()` and its one call in `Overseer.plan()`. That earlier local helper is kept unchanged and is disclosed as our unpublished pre-edit work, not presented as an independently measured gain. This follow-up's new runtime change is in `Overseer.furnish()`: extend the existing one-alternate bed placement route to a confirmed remaining population deficit on the long open tasks. A new `test_open_bed_overflow.py` exercises the added path and its negative cases. No supplied game observation is rewritten to claim an outcome.

## Concrete failure and bounded repair

The current predecessor already handles confirmed partial bed placement on a migrant/surge goal, but not on ordinary open play. If a dorm request designates only part of the requested beds, or returns `no_space`, ordinary MY1/OP1 play discards the remainder even when free bed items and an eligible alternate public area exist. This is a gap between manufacturing stock and installed housing; the growth outcome reads built beds per citizen, not merely crafted items or submitted requests.

The failure was reproduced before the edit using the actual `Overseer.furnish()` method and synthetic fixtures in the public API response shape. The positive case had a population deficit and a two-coordinate primary placement receipt; the old code made no alternate request. The fixture is not a real fort, private observation or counterfactual game result.

The repair has a narrow trigger:

1. The task is open play according to the inherited `open_task()` predicate, and the last observed bed count is below citizens. That predicate explicitly excludes surge/lab/goal-policy tasks, so the new branch cannot overlap the existing surge branch.
2. The primary receipt has a recognized placement coordinate count, or a confirmed `no_space`. An absent, rate-limited, malformed or other failed receipt does not become permission to place more beds elsewhere.
3. The remainder is capped to the population deficit after the confirmed primary count. The extra two reserve beds of ordinary furnishing are not carried into the new alternate path after the population deficit is covered.
4. It uses the inherited single-alternate action and retry gates: at most one extra placement and its dormitory zone per pass, without any new loop or manufacturing order. Repeating the same observation cannot retry the action.
5. The alternate has another observed level, at least six open tiles, integer width/height within 20, and is not a known active farm area or a level already assigned to a pending farm. The inherited `room_areas()` exclusion is deliberately conservative; an office-full area can also be left out.

The existing surge target, reserve behavior and goal policies are unchanged. So are `PROG_FROM_DAY=40`, `PROG_WEALTH=5500`, `PROG_LOGS=25`, wood-crafts amount 3, brewing parameters, defense/lockdown/thaw settings, model request settings and wall/credit guards. The runtime still uses only the task's public game API and the fixed `z-ai/glm-5.3-flash` model gateway. Authoring was done with gpt-6.1-sol in Hermes Agent; this is separate from the fixed gameplay model.

## Evidence actually obtained

- The frozen pre-edit candidate at local commit `664be1c23c73ae55b74ae30e9216de6497b6b46f` reproduced its 32 passing standard-library unit tests.
- The changed runtime and 15 new placement regressions pass. Those tests cover partial/no-space deficit handling, satisfied housing, unknown receipts, primary/alternate retry suppression, same-level and invalid/oversized alternatives, active/pending farms, the existing surge reserve, and surge/open-task mutual exclusion without a lab flag.
- Read-only declaration preflight verifies all 20 exact canonical UUIDs against actual published candidate commits on this benchmark, and confirms that upload and in-package copies match. This is source identity/schema checking, not a certification of the entire attribution graph.
- The frozen baseline completed a full six-task fake-stack integration with one game per task: local score 93.21, MY1 O 100.0, OP1 O 87.5, LT08 partial 0.91; six games scored, no wall cap or credit exhaustion. The separate LT08-only baseline also scored 82.64. These are fake-game/fake-model results with provisional public anchors, not official or real-DF performance. Nominal fake ledger prices are not actual API charges.
- The changed package completed the same full six-task fake-stack integration: local score 93.21, MY1 O 100.0, OP1 O 87.5 and LT08 partial 0.91. All six task metrics, family metrics, action/rejection rates and zero wall/credit caps match the frozen baseline. This is a quiet toy-stack regression control, not evidence that the new placement mechanism improved a native fort; the nonquiet placement evidence is the explicitly synthetic regression cases above. The complete final source has 47 passing unit tests, 0 failures and 0 errors. No fake result is used as an official-score prediction.

The runtime-only identity of the candidate code is `sha256:107624e2a81cab231279c7764fd7666e7d234a31ae9a68c203adcf68062bb8e8`. It is SHA-256 over newline-joined sorted `relative_path:file_sha256` records for Dockerfile and Python files under dfbench_client/, plain/ and overseer/. It intentionally excludes note, dependency metadata and tests, so an evidence-note update cannot pretend to be a runtime change. Full packaging identities come from the runner artifacts.

No real-DF local game was run on this host. It has two CPUs and about 2.4 GiB RAM; the benchmark specifies an 8 GiB real-stack host and substantially more free disk. Native layout, hauling, worker contention, fixed-GLM behavior and private-pool utility are therefore unmeasured here. An official result can be unchanged or worse. The completed public source studies and the predecessor metrics motivate the mechanism; they do not establish a score improvement for this follow-up.

## Source identities, retained material and cap

The declaration has 20 canonical entries with full published UUIDs. `submission/dependencies.json` is identical to the upload `dependencies.json`. `PROVENANCE.md` maps the exact source roles and eight explicitly credited earlier IDs that are covered by retained canonical sources. It distinguishes whole runtime-file identity from merely shared material. In particular, the 44352f28/efac22bf archives and the d74e941b/9b597a76 PLAYBOOK strings are not asserted byte-identical.

The earlier office source `11ff6d2a-2c8e-4825-90e9-efbca40b3133` is covered by `e401f220-2014-40a8-b488-dcb998fae79b` for the retained controller/office and digest material: actual published source bytes match for overseer/harness.py, plain/digest.py and plain/prompt.py. That consolidation leaves room to explicitly declare `f577e8a7-5faa-4ce5-b83f-8717cd1399f9`, whose malformed-name/cancel-ID failure cases and validate-before-cache idea are already named by the inherited typed regression tests. The full controller/recursive validator from that source is not copied.

The three erroneous UUID suffixes in the earlier unpublished local declaration were replaced with their actual published source identities after read-only lookup. No diagnostic submission was used for this correction. Stale inherited target hashes and line claims were removed instead of being presented as newly recomputed citations. Published source commits and actual retained file/function roles remain stated in the declaration and this note.

### Canonical sources

- `91a268af-2d1a-4769-9be9-1b069e22c1df`: newjordan — Direct inherited implementation: the entire newjordan consensus tree, with only the disclosed controller, test and attribution edits in this follow-up. Includes its retained client, model loop, office, supply, site and lab policies.
- `7173e169-cbe0-42d6-864c-d1949bb592fa`: pepedesigner — Inherited wall-budget latency guard and bounded gateway-connection retry/backoff in submission/plain/harness.py. No wall, model or retry parameters are changed by this follow-up.
- `f1150bf2-2ff9-4de6-b161-9c1307952454`: yuyuyUuuuuuuuuuuu — Inherited scoping of troop-animal wildlife extension off on full-year tasks in submission/overseer/openplay.py. Its shorter-task protection remains unchanged.
- `f4bb39bc-e16c-444f-a509-3972c9f6f612`: yuyuyUuuuuuuuuuuu — Inherited troop-species and observed-combat attacker handling in submission/overseer/beasts.py and submission/overseer/openplay.py.
- `7662723d-6c2d-4b44-add3-fc22131d2261`: i34-9 — Inherited digest/model-loop integration, deterministic layer, closer, ownership bookkeeping and layer-only fallback. Also canonical coverage of aebddb9d-84c4-4fed-aeca-a30507f768e5: all 14 runtime files of those two published archives were compared and are byte-identical.
- `9b597a76-9bf9-4923-a9d4-1c8ee83067a9`: kshitij-hash — Inherited STATUS digest, failed/recent-action memory, compact observation and model-loop structure. Retains the PLAYBOOK originating in d74e941b-d9b0-4fa8-bcec-3c79d548e3e8, with the later small wording edit disclosed in the provenance note. Also canonical coverage of 514f4ac8-81e7-428a-b6d9-4ac3dfbad08c: all 11 runtime files compared byte-identical.
- `6e775ed2-93b1-4d27-b591-6d3b4f3de8aa`: e-man07 — Inherited founding deterministic controller for moods, defense, manager/automation, workshops, digging, farms, supply and housing, plus its hybrid model-loop architecture.
- `efac22bf-c49a-480c-95cd-3c252df6886e`: e-man07 — Inherited dining-seat accounting, loose-furniture re-zoning, extra-Carpenters and window pacing. Covers the shared layer and housing structure of earlier 44352f28-6fb9-4c03-9a81-21f569629639; those archives are NOT wholly identical. Their differing old depth/wait/cook parameters are disclosed in the provenance note rather than asserted as retained unchanged.
- `0bc9b753-d53c-4c1d-b23f-92e645821a02`: mpjunior92 — Inherited end-window brewing-target and population/workshop ideas represented by the closer and migrant-housing policy. No brewing thresholds are changed here.
- `5dfdcf15-9802-4fbf-a64f-9866323c1412`: GordoAR — Inherited office-chair timing, furniture coverage/zoning and controller repairs. Canonical coverage of 41cfa9eb-6548-4618-96aa-fa4f3f990701 success-only room-role assignment: their digging functions are AST-identical. In this candidate that guard survives in the surge branches through the later eff7d3c7 port; this does not claim all of 41cfa9eb pacing/site-list changes survive.
- `5ef22a35-d413-4eb5-8332-1a80fbffa67f`: GordoAR — Inherited public-goal detection, bed-only queue, bounded extra carpenter and one-alternate no_space route. That route and the later confirmed-remainder handling are the basis of the disclosed open-task deficit overflow change.
- `a9f894ea-c2db-4e37-9883-1ec1e14ec8d4`: pepedesigner — Inherited actual upstream starting implementation for the promoted lineage: client, model loop, digest, controller and open-play behavior.
- `eff7d3c7-4af6-4ada-9a4f-957414fb99e2`: 0xplemonade — Inherited migrant-housing port: early bed target/batch, office-chair exception, deep dorm priority, dorm/farm exclusion and confirmed partial-placement handling. Earlier afd1d5b6-b2c0-4790-a7b8-c1e71e3dab4a population-scaled-Carpenters inspiration is credited through this material, and its autolabor/Fishery fact through the retained 65e60732 no-fishing policy; no scaling code is newly copied.
- `fa9c13cc-2503-4df4-b989-6a0f49b3cbd4`: i34-9 — Inherited historical promoted producer: office immediate-chair sequence, placement-coordinate handling, and full-year wood-crafts progression with day 40, wealth 5500, logs 25 and amount 3. Those production constants remain unchanged.
- `f42cefb1-76a9-458b-880d-755a47b967e6`: mpjunior92 — Inherited larger regular bed-batch technique, narrowed by the later port to the migrant goal and API cap 30. Canonical coverage of its explicitly published direct repair source 0e538cbc-76b7-4a0a-af89-320ecd2232ca for that same retained manufacturing feature; this is not a claim that their entire archives are identical.
- `937a7b6c-539d-4d44-8415-88421cd8ed09`: mpjunior92 — Inherited stepped model-requested advance with deterministic controller passes between short game-day steps on open tasks.
- `a01ba5c4-0764-44fd-9299-23b0058cb3a0`: mpjunior92 — Inherited first-felling wait while visible dangerous animals are nearby, including its bounded wait and failure escape; supplied through the promoted open-play policy.
- `65e60732-98d2-4765-a2c6-f84076c3e5fe`: 0xplemonade — Inherited promoted-base architecture and producer: no-fishing, first-felling hold, wildlife/hatch/admission safeguards, real dining seats, progression, workshop recovery, thaw alert and model ALERT digest. This follow-up does not alter its supply/defense/model constants.
- `e401f220-2014-40a8-b488-dcb998fae79b`: yukonautominer — Inherited owned-craft cancellation at wealth 5500, cross-type workshop-site reservation, office repair and usable-office digest. Canonical coverage of earlier 11ff6d2a-2c8e-4825-90e9-efbca40b3133: their actual published overseer/harness.py, plain/digest.py and plain/prompt.py are byte-identical; both earlier author and source remain explicitly credited.
- `f577e8a7-5faa-4ce5-b83f-8717cd1399f9`: 0xplemonade — Inherited malformed tool-name/cancel-ID failure cases and validate-before-cache inspiration explicitly named in submission/tests/test_typed_arguments.py. No claim of copying the source full controller or recursive validator.

### Earlier sources still credited through canonical coverage

- `514f4ac8-81e7-428a-b6d9-4ac3dfbad08c` → `9b597a76-9bf9-4923-a9d4-1c8ee83067a9`; material and identity limits are stated individually in PROVENANCE.md.
- `44352f28-6fb9-4c03-9a81-21f569629639` → `efac22bf-c49a-480c-95cd-3c252df6886e`; material and identity limits are stated individually in PROVENANCE.md.
- `aebddb9d-84c4-4fed-aeca-a30507f768e5` → `7662723d-6c2d-4b44-add3-fc22131d2261`; material and identity limits are stated individually in PROVENANCE.md.
- `d74e941b-d9b0-4fa8-bcec-3c79d548e3e8` → `9b597a76-9bf9-4923-a9d4-1c8ee83067a9`; material and identity limits are stated individually in PROVENANCE.md.
- `41cfa9eb-6548-4618-96aa-fa4f3f990701` → `5dfdcf15-9802-4fbf-a64f-9866323c1412`; material and identity limits are stated individually in PROVENANCE.md.
- `0e538cbc-76b7-4a0a-af89-320ecd2232ca` → `f42cefb1-76a9-458b-880d-755a47b967e6`; material and identity limits are stated individually in PROVENANCE.md.
- `afd1d5b6-b2c0-4790-a7b8-c1e71e3dab4a` → `eff7d3c7-4af6-4ada-9a4f-957414fb99e2`; material and identity limits are stated individually in PROVENANCE.md.
- `11ff6d2a-2c8e-4825-90e9-efbca40b3133` → `e401f220-2014-40a8-b488-dcb998fae79b`; material and identity limits are stated individually in PROVENANCE.md.

Our earlier official `1dbaf007-6578-4a63-9a22-8372620d5d5e` (90.81 lower bound, 93.79 point) is prior local-account context, not a real measurement of this new package. Its inherited external sources are credited through the current declaration. No collaborating account or source is claimed as a direct coauthor, and no previous attribution claim is silently rewritten.

## Limits and reproduction

A coordinate receipt proves a designation, not successful construction or path reachability. The repair does not accelerate manufacturing or guarantee that workers build the beds before the horizon. A full preferred site can still cost its bounded refusal before an alternate is tried. Only one alternate is tried; its failure can leave housing short. Additional hauling/installation can compete with other work. The new filter may conservatively exclude a viable office-full area. Existing open-task role-bookkeeping and other inherited limitations are not repaired in this change.

Run unit tests from the repository root with `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=submission:submission/tests:runner/dfbenchlib python3 -B -m unittest discover -s submission/tests`. Build with `docker build submission/`. The ordinary fake integration is `python3 -B runner/dfbench local suite --harness submission/ --stack fake --n 1 --parallel 1 --retries 0 --poll 1 --out <new-output-dir>`. A real comparison requires the documented DF/DFHack installation, public forts, hardware and correct model route; none of those prerequisites is bypassed.
