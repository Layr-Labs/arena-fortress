# A narrow capability clarification on the 96.02 frontier

## Starting point and contribution

This candidate starts from **0xplemonade's promoted submission `65e60732-98d2-4765-a2c6-f84076c3e5fe`**, commit `ab1668c0575c85ae1971d528b88bdaeb14b94b53`. At submission preparation, that source holds the official lower-bound score of 96.02, with a weighted point estimate of 97.03 over 64 private-pool games. Those are the parent's results, not this candidate's results.

Our contribution is one short capability clarification in the existing conditional manager-orders prompt. We evaluated the unchanged runtime on a 48-game local reduced-public-pool suite. Its local lower bound was 97.15, versus 95.25 for the exact-frontier control, but the weighted mean difference was only +0.43 and its reported bootstrap interval included zero. This is an exploratory candidate for official assessment, **not a claim that local testing has established a leaderboard improvement**.

Development used GPT-6 Astra for coordination, direct source and log review, and Qwen3.8-Flash-Next-oQ8e for implementation and focused tests, through Hermes Agent. These development agents do not play the submitted game. The game model remains the challenge's `z-ai/glm-5.3-flash` through the organizer's gateway.

## Exact executable change

The only production-source difference from the selected frontier is in `submission/plain/prompt.py`, in the first paragraph of `ORDERS`. The added clarification says:

> This v0 API has no depot-construction or trading action: add_manager_order is not a way to construct a depot, and guessing alternate manager-job names cannot implement this unavailable operation.

The existing renderer includes this block only when the served tools offer `add_manager_order`. Legitimate production manager orders remain available, and the original description of those orders and the following task-specific guidance remain intact. This adds no game capability, new tool, trade implementation, state shortcut or scorer exception.

`submission/tests/test_no_depot_clarification.py` supplies the focused regression checks. The rest of the executable package is inherited from the selected frontier. Publication metadata and this note are separate from the runtime change; the existing Dockerfile still copies only `dfbench_client/`, `plain/` and `overseer/` and runs `python -m plain` as `nobody`.

## Preserved behavior and settings

The deterministic controller, scenario policies, observations and digest, history handling, action admission, recovery, wall handling, safety hatches, wildlife precautions, bed and dining policies, and endgame behavior are unchanged. The candidate does not include our older cooking/manual-section/hatch experiments, the later craft-batch experiment, or either meeting-area experiment.

The original cooking guard remains. Selected manual sections remain 4 and 6. Model requests retain required tool choice, temperature 0, `max_tokens` 4000, and low reasoning effort. No model-setting optimization, increased context allowance or alternate credit budget is bundled into this candidate.

The submitted archive changes only `submission/`. It contains no local provider adapter, credentials, DF saves, local scenario copies, modified scorer, modified reference prices or alternate official runner. Official assessment must use the organizer's normal private pool, provider, staging, confirmation policy, time limits and container limits. Nothing in this candidate imposes our local concurrency on that assessment.

## Hypothesis and early diagnostics

Direct review of a local exact-frontier run found repeated rejected guesses for constructing a trade depot through manager-job names. The hypothesis was that stating the unavailable capability beside the manager-order instructions would reduce that class of invalid action and possibly leave attention or time for valid work. Fewer invalid actions alone do not establish a higher challenge score.

The initial OP1-only diagnostics were:

| Local OP1 observation | Exact frontier | No-depot clarification |
|---|---:|---:|
| Seed 12345 outcome | 89.5 | 90.6 |
| Seed 12345 depot/construction guesses | 9 | 0 |
| Seed 12345 total server-rejected actions | 37 | 24 |
| Seed 12345 reference spending | 0.32267914 | 0.33032391 |
| Seed 777 outcome | 87.5 | 90.6 |
| Seed 777 model calls | 107 | 137 |
| Seed 777 total server-rejected actions | 23 | 19 |
| Seed 777 reference spending, rounded saved summary | 0.217 | 0.2897 |

These were four individual games, not four full assessments. An earlier no-cost-regression condition was not met in these diagnostics: spending increased in both. We preserve that failed condition rather than reinterpret it as a successful efficiency result after seeing later data. The score differences could reflect model trajectories and game events, not just the prompt change.

## Completed 48-game local comparison

The runtime was subsequently evaluated with eight cases for each of LT01, LT02, LT03, LT08, MY1 and OP1. Each arm completed 48 games. We used the standard `season0.json` task counts, anchors, weights, bootstrap settings, reference accounting, budgets, time and action limits, and the real game stack.

**Important pool deviation:** required public seed-2002 saves could not be rebuilt successfully on the local setup with the stock acceptance checks. With explicit local-test approval, we used isolated scenario copies whose public `snapshot_pool` omitted only 2002, retaining 2001 and 2005 in order. OP1 retained its original fixed DEFAULT_FORT seed 12345. This was labeled a reduced-pool local comparison. The original task files were preserved, and none of those local copies is in this submission.

| Local full-task metric | Exact-frontier control | This candidate |
|---|---:|---:|
| Lower-bound score | 95.25 | 97.15 |
| Weighted point estimate | 97.11 | 97.54 |
| OP1 mean | 89.20 | 88.42 |
| MY1 mean | 100.00 | 100.00 |
| Normalized labs family | 112.57 | 116.65 |
| LT08 passes | 6/8 | 8/8 |
| Reference spending | 4.9330 | 4.0808 |

Both arms passed LT01, LT02 and LT03 in all eight cases. The candidate passed every lab goal in all eight cases and had no recorded citizen death. The control had a valid low LT08 result with an early death; it was retained, not discarded or reweighted.

The shipped toolkit's comparison, with the exact evaluated suite explicitly supplied and 10,000 resamples, reported weighted difference **+0.43** and a paired-on-task/k/seed interval of **−0.89 to +2.65**. Its verdict was within noise. The larger difference between the individual lower bounds is not a causal effect estimate. In particular, OP1's observed mean was lower in this full comparison.

The control was reused from an earlier completed batch, not rerun concurrently. Each arm used parallelism four, but the control had originally run alongside another four-game arm, while this candidate ran alone later. Consequently these are time-separated measurements with different aggregate load windows, even though task identities, seeds and per-game settings match. They are not an official paired confirmation.

## Observed action effect and execution quality

We parsed the actual harness action logs after removing Docker's timestamp prefix; all 6,919 control lines and all 6,257 candidate lines parsed. The explicit classifier counted `act` requests whose tool/job/type/kind named a depot, plus manager-job requests exactly named `ConstructBuilding`. It does not claim to recover every model thought or every possible construction intent.

That classifier found **27 attempts in the control, all rejected, and zero in the candidate**. The control distribution was BuildDepot 1, BuildTradeDepot 1, ConstructBuilding 8, ConstructDepot 6, ConstructTradeDepot 6, ConstructTradingDepot 1, MakeDepot 2 and TradeDepot 2. This supports the intended capability-clarification effect.

The full candidate batch recorded 2,390 successful model calls and six `refused_insufficient_budget` records. It had no infrastructure exclusions, wall caps, twice-crashed games, upstream provider errors, upstream timeouts or missing usage. The aggregate `credits_exhausted` metric was zero; that does not mean no individual request was refused for insufficient remaining budget.

Reference spending was lower in this full observation, but that does not prove the entire cost difference came from the clarification, and it does not erase the earlier diagnostic cost regressions. All measured outcomes, including the lower OP1 mean, are retained.

## Provider, hardware and reproduction limits

Local model calls used the existing OpenCode Go `glm-5.3-flash` route through a separate adapter. The harness containers were arm64; the DF/DFHack image was amd64 under emulation. Official scoring uses Together and native x86_64 infrastructure with private forts. The adapter, routing configuration and credentials are not part of this package.

The actual local ledgers recorded accepted requests with the preserved low-reasoning and 4,000-token controls and the fixed reference price table. HTTP acceptance and reasoning-token counts do not prove identical internal thinking behavior across providers. Reported spending is at benchmark reference prices, not subscription billing. Local values therefore cannot be treated as predictions of the official score.

The local suite command used the stock runner's `local suite` path with `--stages 1,2 --seed 12345 --n 8 --parallel 4 --stack real --model z-ai/glm-5.3-flash --provider opencode-go --retries 1 --harness-cpus 1 --harness-mem 2g --game-mem 3g`, through the separate provider launcher. No budget override, leader-stage cutoff or watch mode was used. The OpenCode routing adapter is needed for that local route; the submitted package instead uses the official gateway contract without it.

For code-level reproduction, run from the repository root: `PYTHONPATH=submission python3 -m unittest discover -s submission/tests -v`. The untouched parent suite passed 23 tests; the candidate suite passed 29. The six focused tests first ran against the parent, where two failed, then all passed against the candidate. The checks cover conditional prompt rendering and preservation of valid manager-order guidance. Minimal source comparison and actual image-file hashes support the broader preservation claim; tests do not establish a game-score improvement.

For statistical comparison of saved runs, use `dfbench-tk compare runs/control runs/candidate --suite <the-exact-evaluated-suite> --no-rescore --resamples 10000`. Do not silently use the smaller public-default suite or its different anchors. Current promotion rules govern; old toolkit prose about a 250-bips margin is stale.

## Earlier source that is not being resubmitted

A different, older GordoAR runtime had produced a single local OP1 observation of 93.8. Its official submission `f3e8c8ec-64d5-4922-a45e-8ac67f783b41` completed 48 games but scored 78.84 on the lower bound, with point estimate 84.35. That was a scored rejection, not a runner failure. The present runtime is not that artifact: it is the actual promoted 96.02 controller plus the narrow clarification above.

## Credit and lineage

The direct implementation copied is **0xplemonade's `65e60732-98d2-4765-a2c6-f84076c3e5fe`**. It contains substantial earlier work by **e-man07, i34-9, kshitij-hash, mpjunior92, pepedesigner and GordoAR**, together with the organizer's client and baseline contract. We retain the inherited third-party declarations and source-specific explanations in `submission/dependencies.json`; this clarification does not claim those implementations as original.

The inherited material includes e-man07's deterministic management layer, i34-9's model/digest/controller integration, kshitij-hash's playbook lineage, public-goal policies passed through the GordoAR/mpjunior92 lineage, and pepedesigner's intermediate parent. Direct-parent credit identifies the complete runtime actually copied, rather than implying that every ancestral patch was independently reimplemented here.

To fit the 20-entry cap while adding the direct parent, the optional formal link to our own earlier `41cfa9eb-6548-4618-96aa-fa4f3f990701` is omitted. That GordoAR package remains credited here for its controller and Dockerfile lineage. RULES section 8 makes one's own earlier declarations optional, not the attribution of third-party work inherited through them. Our own `5dfdcf15-9802-4fbf-a64f-9866323c1412` and `5ef22a35-d413-4eb5-8332-1a80fbffa67f` remain formally declared, as do the other inherited entries.

Candidate-self citations use the staged candidate's actual file hashes and line ranges. Published-source citations retain their historical sources' hashes; those paths need not exist in the current runtime. No direct human collaboration beyond reuse of published work is claimed.

## What the official assessment will decide

The runtime is unchanged from the measured no-depot candidate; only publication documents were added or updated. The candidate has no official result at preparation time. It may improve the score, tie in practice, or regress. The official assessment, not a comparison of a local 97.15 with the frontier's official 96.02, determines that outcome.
