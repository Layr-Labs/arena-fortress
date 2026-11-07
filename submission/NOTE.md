# Short public-combat retreats, accurate office context, and late food provision

This revision adds short wildlife retreats, corrects the model's office summary when a second owned office is usable, and revisits a credited late-food policy. The ordinary six-family local run completed at 94.19. Its year game scored 85.4 with no citizen deaths and full supply, but persistent stress reduced wellbeing. That local aggregate is lower than the earlier parent's 95.24 on a different cohort. These are unpaired public games with a canned gateway; no local aggregate improvement, real-GLM improvement, ranked lower bound, or promotion is claimed.

The concrete improvements are reviewable mechanics and information: native alerts now last two game-days rather than seven; the model is no longer told that the manager needs a chair when another observed owned office already has built chairs; late provision produces food through ordinary public game actions. Their combined seasonal performance requires an admitted official evaluation. The negative outcomes below are retained.

The author used GPT 6.1 Sol in Codex, without subagents or direct collaborators. The gameplay model remains the task-provided z-ai/glm-5.3-flash through the organiser gateway. Every local result here used actual Dwarf Fortress 53.16 and DFHack 53.16-r2 with the runner's canned fake gateway, stack=mixed. Fake token ledgers are not provider bills. No additional inference service or gameplay model was used.

## Actual predecessor and published context

The direct program source is my ninth submission c29a81ea-a9e1-438d-8c37-ebf235f3032e, published at [8b71abf8f4890429f574090255ee9e6ff36cd5a2](https://github.com/Layr-Labs/arena-fortress/tree/8b71abf8f4890429f574090255ee9e6ff36cd5a2/submission). Its exact public controller, loop and digest files were checked against the frozen upload. The promoted producer remains i34-9's fa9c13cc-2503-4df4-b989-6a0f49b3cbd4 at 2f3abb30f6291e05a8d37a8c40c34a29732000b4, last verified lower bound 91.32. The original controller remains byte-identical in overseer/frontier.py, SHA-256 ee13a95e6663fc4b6facc7872b43d7764d1df37c40be540cdb3c7d7b75db3e19.

Published9 received no judge or game result. Its [PR64 admission comment](https://github.com/Layr-Labs/arena-fortress/pull/64#issuecomment-6705835488) says the global weekly allowance of 40 was exhausted, admission stopped before image build, and the attempt was neither scored nor counted. Workflow 42365568222 failed at Weekly cap (cost control), with the stated next window 2026-11-09 00:00 UTC. This was not a performance rejection.

The parent retains structured hands-off routing, the managed water-aware shaft selector, committed-bed production, bounded housing/office geometry, one model loop and ownership guards, the exact promoted open controller, and the normal year-brew reserve. Its year-only required-office repair is also retained. The new runtime changes are confined to overseer/year.py, plain/harness.py and plain/digest.py; tests and public fixtures accompany them. The Docker entrypoint, fixed model interface, prompts and original frontier file remain unchanged.

## Native year and full-suite measurement

The ordinary selected-track run is .yukon/runs/20261107-115835. All 42 Python/test/Dockerfile hashes and 49 non-metadata payload hashes stayed unchanged through the run. There are 52 payload files. The selected program passed 116 software checks before the run.

| family | completed local result |
|---|---|
| LT01 | full predicate pass, all four clauses true, partial 1.0 |
| LT02 | full predicate pass, all four clauses true, partial 1.0 |
| LT03 | full predicate pass, all three clauses true, partial 1.0 |
| LT08 | full predicate pass, all four clauses true, partial 1.0 |
| MY1 | O100.0, all component scores 1.0, 17 citizens, zero deaths |
| OP1 | O85.4, survival 1.0, supply 1.0, wellbeing .944, growth .5 |

MY1 took 537 seconds. OP1 took 1124 seconds and ended with 18 citizens, 20 placed beds, 17 dining seats, no insanity or breakdown, rank 0 and created wealth 12,835. All four completed citizen-death sources agreed zero. Final-window drink went 607 to 599, with fitted projected days-left 2854.4 and full drink credit; food went 114 to 190 with full food credit. The final-window stressed share was .056. The unresolved stress reduced wellbeing despite adequate housing and supply.

The local wrapper reported 94.19 on provisional public anchors, family_labs 107.47, MY1 100.0 and OP1 85.4, with 6 scored / 6 run games. There were no wall caps, credit exhaustion or infrastructure exclusions. official_comparable=false. This wrapper score is not the seasonal lower bound, and it cannot be compared directly with the promoted 91.32. The earlier parent8 local wrapper result 95.24 was higher; the public cohorts are not paired, so neither a causal regression nor a causal aggregate gain follows from that difference.

The measured image is dfb-harness:6178c9a83d45b553, with package digest sha256:6178c9a83d45b55375e44f71289577135a76dbec24e38016132634063a51e88c. The earlier integration prototype c8cae19a7c95c357 and this ordinary image have identical RootFS and full Config. Root note, README and dependency metadata are outside Docker COPY. Final packaging is compared against the measured filesystem layers and complete runtime configuration after metadata finalization; differing image IDs alone do not establish a runtime change.

## Why a short wildlife retreat was added

Recorded public combat reports described an alligator biting or shaking animals or citizens while threats.visible_hostiles was zero. The inherited policy acts on the danger/invader fields, so it did not react to those reports. Two earlier office-only trials lost a citizen before reaching 20 population: O60.7 with an alligator death at day25 and O66.7 with an early death at day8. Neither activated the office extension. These negatives motivated the wildlife experiment; they do not prove a new retreat prevents the corresponding deaths.

The year-only addition recognizes generic public combat wording: bites, strikes, gores, latches on, or attack. It uses an existing civilian-alert burrow, or a currently observed dug underground room if no shelter exists. It starts only with at least 40 drink and 20 edible food, avoids starting its own pulse in the presence of known invaders, remembers reports to avoid stale-message retriggers, and uses a cooldown. It clears on expiry or falling reserves. It reads normal public observations and issues normal public actions.

An initial prototype had a real integration defect: a nominal two-day alert lasted seven days because the model loop advanced seven days between controller passes. Its completed default years scored 66.8, 76.9 and 87.5. All had zero citizen deaths and full wellbeing, but food supply scores were .669, .831 and 1.0. That version was rejected. One case also received three extra read-only public diagnostic queries at day121 (seeds, jobs, citizens), without any manual action or time advance; that annotation is retained.

The corrected version caps both model-requested and fallback advances at one day while its own timed retreat is active. Other controllers and inactive advances keep their previous limits. Both native default cases showed alert on at16, one-day advances to17 and18, and alert off at18. Public observations showed all seven citizens inside by17. This verifies both reachability and actual timing through the real model-call path.

Those two corrected component years scored 90.6 and 90.6, ending with 21 and 20 citizens, zero deaths by all four completed sources, full survival/supply/wellbeing and growth .625. Final stocks were 619 drink / 114 food and 557 drink / 106 food. A separate public2004 case scored 85.3 with 17 citizens, zero deaths and full supply, but wellbeing .941 from persistent stress. Its food went 184 to211; drink607 to603. These unpaired cohorts are mechanism and robustness evidence, not a causal ranking estimate.

The integration also hands control straight back to the original defense method if a visible invader appears during an existing wildlife pulse, keeping the current alert. A synthetic regression calls the actual base method and checks that handoff. No native invasion benefit is claimed. Temporary wildlife handling is not used on the shorter midyear or managed-window controllers.

## Correct office information for the model

The API's administrators.manager_office reports the first owned office. A captured public case continued to report chair=false for office31 after manager86 had received another owned office45 with built chairs and stalled orders began validating. The old STATUS section consequently recommended putting a chair in the old office even though the public zone list showed a usable owned office.

The new STATUS manager section preserves the raw first-office report and separately lists the observed owned office with its actual built-chair count. It uses MANAGER_id, Office zone ownership/type and built furniture counts. Planned chairs and another citizen's office do not qualify. It suppresses the contradicted missing-chair NEXT recommendation and sets the order context's office_ok accordingly. It does not rewrite the raw observation or the game API.

On the captured post-repair observation, the old summary said office31 chair=NO and recommended placing a chair there. The revised summary retains that report, adds owned office45 with 10 built chairs, and has no missing-chair NEXT. Four checks cover that observation, unchanged raw facts, planned-only and other-owner exclusions, and an absent first-office report. This is a factual model-context correction; canned native runs cannot measure how the actual GLM reacts to the corrected wording.

## Late food provision and its credited source

This revision revisits the final-food timing/threshold from e-man07's 1e6cbe5e-e6e0-4821-977c-562cc7cf941e: with 2 to14 days left, invoke slaughter unless food reaches 40 per citizen. Authentic published commit 88830055ad859a27b797cf40fcd2323945ffdcb6 has MEAT_DAYS=14 at line26 and final_meat starting at343. The declaration now credits this newly reused food material as well as the already credited architecture input.

The candidate adapts that timing/threshold only on year horizons. It runs the original endgame method first, then calls the existing butcher helper. It retains the original first-tame-animal-without-observed-pet-owner selection, workshop preparation and five-day retry gate. It does not copy the peer's largest-animal ranking, separate slaughter_end key, three-day cadence or five-attempt policy. The existing limit3 counts failed attempts, not three successful marks. The shared action key prevents two successful marks in one pass.

Re-reading completed older component records mattered. V74 scored69.8 because drink fell178 to149, scoring .717, while food83 to145 scored1. V76 scored65.1 with an early citizen death and wellbeing .944 but full supply: drink471 to473, food107 to172. Its repeat87.5 also had full supply: drink602 to600, food107 to181. These unpaired food-positive components motivated a narrow retest after parent9 showed a food decline. The ae0c2b7b negative optional-food analysis remains credited; it is not erased or treated as a causal experiment.

The new food-only public2004 year completed87.5 with17 citizens, zero deaths and full survival/supply/wellbeing. It accepted a tame unowned dog mark at325 and cat mark at332. Final-window food141 to200 and drink591 to610 scored full supply; wall1341 seconds. Its separate default-fort validation scored85.0 with15 citizens, zero deaths and full supply: food115 to192, drink610 to600. Wellbeing was .933. A stressed adult Fisherdwarf had already been present before the added late-food action; that establishes temporal order of the onset, not the final causal effect. Persistent stress remains unresolved.

The current combined year likewise had full food supply, but it did not achieve full wellbeing. Publication shares an operational provision mechanism and mixed complete outcomes, without claiming that adding meat guarantees a ranked gain.

## Additional public-fort regression

An own worked-y1 fort was generated from public seed2010 with the unchanged organiser builder and TEMPERATE_SOIL rules. It passed the recipe on the first attempt with19 citizens:104 seconds to embark,17 seconds recipe construction and131 seconds total including save. The extra LT08 task changed public seed/snapshot references only; setup migrant_surge.lua100000, horizon60, active39, hands-off21 and the standard predicate were retained.

The same measured image6178 completed all four extra LT08 clauses:49 placed beds for47 citizens, drink547 at the window start to560 at the end, continuous positive food/drink and zero citizen deaths. This is an extra public regression, separate from the six-family wrapper score. The current program therefore has two measured full LT08 passes on its ordinary and newly built public forts.

The inherited water-aware parent8 evidence is historical and separate: three public2009 cases passed with52/50,55/53 and46/44 beds/citizens, plus public2007 and2008 passes at45/43 and47/45. Earlier parent7 cases on2009 had failed at10/45,10/45 and1/52 despite many free bed items and51 stalled digging designations. Public map observations showed the chosen shaft entered revealed depth7 water. Deferring squads and enabling autolabor did not solve those cases. The retained selector chooses greater clearance from revealed water among listed shafts when the default is close to known water; unknown ground is not classified dry. No new mining/labor change is included here.

## Reproduction and measured limits

All scratch artifacts were kept in the checkout's sibling cache. The ordinary commands were, from the repository root:

    python3 -m unittest discover -s submission/tests
    DFBENCH_PROVIDER_KEY=mixed-stack-unused DFBENCH_PARALLEL=3 DFBENCH_SUITE_ARGS="--stack mixed --games LT01,LT02,LT03,LT08,MY1,OP1 --n 1 --game-mem 2g --harness-mem 256m" yukon run --track harness-glm-5-3-flash

TMPDIR was set to the sibling cache's cli-tmp directory. The placeholder provider variable only satisfies the wrapper's nonempty-key check; mixed uses the canned gateway. The actual run path, image and digest are given above. No scored request was sent to a second model.

The extra public fort used:

    bash docker/task_forts.sh --image yukon-df:s0-base --recipes worked-y1 --seeds 2010 --out <sibling-cache>/public-labs-2010 --parallel 1 --memory 3g --prefix codex-v89-extra

Then runner/dfbench local run used --stack mixed, the standard LT08 task pointing to that own public snapshot, --n 1 --parallel 1, the measured image and digest, --game-mem 2g --harness-mem 256m, and DFBENCH_SNAPSHOTS_DIR pointing to the snapshot parent. Component year runs used the same runner, disclosed public default or2004 task, n1/2/3 as reported, and at most three concurrent native games. The program does not route by fort name, seed or expected score. It reads public task horizon/window structure and current game facts.

116 software checks include retained typed order contracts, model-order ownership, window isolation, bounded geometry, water access and committed beds. The prior exact-endgame-identity check was intentionally replaced by four checks that the base endgame still executes first and the added food call obeys horizon/time/stock bounds. New tests cover combat expiry and reserves, both real Plain advancement paths, captured office context and invader handoff. These checks are not a substitute for native or official gameplay.

A separate growth-only trial is rejected. Starting from9, it tried up to three craft workshops,12 daily wooden crafts after day14 with a40-log reserve and one free workshop site retained. It finished O67.6 with21 citizens, no deaths, full wellbeing and drink, but food106 to84 scored .649. Created wealth22,039 and rank1 did not improve growth beyond .625. That capacity change is excluded. Larger search or more code is not evidence of improvement.

Remaining limits include unresolved stress, partial year progression, unpaired public cohorts, stochastic DF behavior and the lack of real-GLM local measurement. Canned ledgers are not model bills. Only admitted official evaluation can establish a seasonal score or promotion.

## Attribution coverage and older negative results

The declaration contains20 unique published targets and45 full-file-SHA256/inclusive-LF citations across four cited entries. Each cited new relationship has source and candidate endpoints; the other16 entries retain legacy or analysis credit without invented code passages. The CLI prepared citations offline from exact authentic public files and exact candidate files. The direct-source entry has24 passages, the CLI maximum, with adjacent timing-helper/fallback context merged without dropping it. These are source-identity/navigation checks, not an official attribution verdict.

Direct9 obtains the whole predecessor program through8. Audits verified8 to9 has all managed methods and the whole plain file identical, old year supply identical, and only a new year-office method;7 to8 retained all managed methods except digging plus the added water selector, with whole plain/year files identical;6 to7 retained all managed methods except the documented bed-commitment supply change and retained Plain.run_call. Earlier credit remains preserved. No existing accepted relationship is requested removed.

Own7 e63b5619-8511-47ec-96ee-fd06dd4f0117 at2bbb1bbed888d4d9ceb8e2ec3de7af4e858995f2 and8 73e6a32f-2256-4ea8-8f14-ac6c22fa9023 at331c12dbe7997b03e5298ba3ae3ea2c89e858e41 were globally refused before games. Own6 f42cefb1-76a9-458b-880d-755a47b967e6 atd4699d5b3e046fc775394dfe3931988a7097d4b2 passed early judging but was performance-rejected after48 official games: LB81.51/point86.93, LT081/8/partial.96, MY183.64,OP178.96. That negative does not isolate a cause. Own5 0e538cbc-76b7-4a0a-af89-320ecd2232ca at09860b16dbb785f0186a4c0800031f4a03f46a50 was held before games for an undeclared current producer, not a game-performance loss. Canceled4 0662d244-d665-45d0-a7e6-d49b9806de2d has public Git3ddf9d8c5f4a134cb5abdee329a9cda9e89875aa but no eligible platform candidate commit; that relationship remains deferred under the unpublished-source rule, with credit preserved.

The retained declarations and feature credit follow. They include current producer, actual direct source, new food reuse and earlier architecture/analysis/implementation lineage:

- fa9c13cc-2503-4df4-b989-6a0f49b3cbd4: i34-9 is the actual promoted producer, at2f3abb30f6291e05a8d37a8c40c34a29732000b4. Its daily layer, STATUS/PLAYBOOK loop, closer, progression, ownership guard, fallback, surge manufacturing reserve and Docker pin are retained through the direct ninth source. Its original controller is byte-identical in submission/overseer/frontier.py for open mid-year play and as the base of the full-year normal-brew subclass. The revision starts from9 and claims no independent reconstruction of this producer.

- c29a81ea-a9e1-438d-8c37-ebf235f3032e: Actual direct program predecessor, published at8b71abf8f4890429f574090255ee9e6ff36cd5a2. Retains the complete ninth program: public-map water clearance, structured controller routing, committed-bed and bounded housing/office helpers, one-loop model ownership, exact promoted frontier base, year normal-brew reserve and required-office repair. New code in this submission is described separately; no independent reconstruction of the retained program is claimed. The new retreat override delegates unchanged military/standard defense behavior to the retained frontier method outside its own short alert interval. The original STATUS manager section and shared numeric/list helpers are retained with a new own correction: report a second observed manager-owned chaired office while preserving the raw first-office report and suppressing the contradicted missing-chair recommendation.

- 1e6cbe5e-e6e0-4821-977c-562cc7cf941e: The public note informed the split-policy architecture after the predecessor regressed on long runs. That source routes whole loops by a 100-day horizon threshold. This candidate instead selects a controller using the public task hands_off structure and preserves one plain loop; its open controller is the exact promoted fa9 source. No peer source code was copied. Additional newly reused material: the public final-food idea of invoking slaughter with2to14days remaining unless edible food reaches40percitizen. The research candidate adapts that timing/threshold to the retained original butcher helper on year horizons; it does not copy this source's largest-animal ranking, separate slaughter_end key, three-day cadence or five-attempt limit.

- ae0c2b7b-522c-4d4b-b161-bd8d663cb009: The public negative-evidence note informed the earlier exclusion of optional late-food work from retained7/8/9. That analysis remains credited while this revision re-tests a narrow late-food addition against newly observed source9 food decline. No ae0c code is copied, and the earlier negative is not erased.

- 7662723d-6c2d-4b44-add3-fc22131d2261: i34-9: STATUS integration with the deterministic layer, layer-aware digest, closer, layer-only fallback and owned-order/alert guard, retained through fa9c13cc.

- 5dfdcf15-9802-4fbf-a64f-9866323c1412: GordoAR: the prior promoted daily-controller and model-loop repairs, typed checks, alerts, Fishery, office chairs, zone coverage, Docker pin and tests retained through fa9c13cc.

- 41cfa9eb-6548-4618-96aa-fa4f3f990701: GordoAR: success-only room/site bookkeeping and stall/idle repairs retained through5dfdcf15 and fa9c13cc.

- 9b597a76-9bf9-4923-a9d4-1c8ee83067a9: kshitij-hash: STATUS digest, recent action/failure memory, compact observation and PLAYBOOK lineage retained through7662723d and fa9c13cc.

- d74e941b-d9b0-4fa8-bcec-3c79d548e3e8: kshitij-hash: the PLAYBOOK prompt inherited through cut2 and the new promoted base.

- 514f4ac8-81e7-428a-b6d9-4ac3dfbad08c: kshitij-hash: retained the promoted base's declared shared-ancestry/overlap credit; no newly copied independent policy is claimed. kshitij-hash's earlier archive of cut 2, the same files as 9b597a76; declared because its lines overlap this tree's digest, prompt and loop.

- 0e977ac9-e067-4c40-9955-be65f3fcc2e4: kshitij-hash: retained the promoted base's declared shared-ancestry/overlap credit; no newly copied independent policy is claimed. kshitij-hash's later submission on the same digest lineage. Nothing was taken from it, but its digest, prompt and loop share most of their lines with the cut-2 files this tree carries, so it is declared as an overlapping archive.

- 6e775ed2-93b1-4d27-b591-6d3b4f3de8aa: e-man07: the founding deterministic Overseer and daily hybrid architecture; its regular policy steps remain beneath the port.

- efac22bf-c49a-480c-95cd-3c252df6886e: e-man07: dining seat counting/re-zoning, extra migrant carpenter, window pacing and continued layer play retained through the promoted base.

- 44352f28-6fb9-4c03-9a81-21f569629639: e-man07: retained the promoted base's declared shared-ancestry/overlap credit; no newly copied independent policy is claimed. e-man07's earlier archive of the efac22bf revision (never scored). The pieces credited to efac22bf first appeared there, so it is declared as an overlapping archive.

- 0bc9b753-d53c-4c1d-b23f-92e645821a02: mpjunior92 (this solver): earlier published late-game brewing-target idea acknowledged by the inherited closer; no broad old Caretaker is copied into this candidate.

- 56a42567-54de-4238-8e7b-8be1081d134c: ryan48: retained the promoted base's declared shared-ancestry/overlap credit; no newly copied independent policy is claimed. ryan48's submission. Nothing was taken from it, but it builds on the same e-man07 layer and the same cut-2 digest lineage, so its overseer, loop and prompt share lines with this tree; declared as an overlapping archive.

- 7d23a133-1e48-4825-b42a-d7e664e2c1e2: ryan48: retained the promoted base's declared shared-ancestry/overlap credit; no newly copied independent policy is claimed. ryan48's earlier archive of 56a42567 (not scored). Same overlap, same reason.

- 7ed9f09a-43e3-4544-aaab-ccbbbb0c0d3e: akhilc08: retained the promoted base's declared shared-ancestry/overlap credit; no newly copied independent policy is claimed. akhilc08's playbook-first harness. Nothing was taken from it beyond what both inherit from the organiser's baseline (dfbench_client) and a few layer lines of common ancestry; declared because the attribution check flagged the overlap.

- f577e8a7-5faa-4ce5-b83f-8717cd1399f9: 0xplemonade: malformed tool-name/cancel-id failure cases and validate-before-cache lesson behind the inherited typed checks and tests; its recursive schema validator is not copied.

- 7d62bc3f-9ee2-417d-886c-9267863a97dc: newjordan: public optional bounded zone-dimension idea already credited in my fifth source; adapted to the public site resolver and accepted40-tile furniture/20-tile zone limits. No provider wrapper or inspect-tool code is copied.

Canonical model and harness lines are supplied by the Yukon flags exactly once. The organiser game API and scoring documents supply the task contract. No coauthors or new independent peer policy beyond the credited food reuse are claimed.
