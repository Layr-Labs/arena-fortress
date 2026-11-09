# Scoring (season 0)

> **Versioning.** The scoring that applies to your submission is the one in this file (and in the scorers and
> `runner/suites/season0.json`) at the commit your submission is based on. Changes during the season are announced
> and dated; affected scores are re-run (`RULES.md` §9).

Scoring runs on the trusted side only: the game server writes the game's artifacts, the runner scores them with
`bench/outcomes.py` and `bench/predicates.py`, and writes `score.json`. Your harness never sees the scorer's inputs
beyond what the game API shows any player.

## 1. Per game

### 1.1 Outcome score O (OP1, MY1)

The gated outcome score (score version 7; full definition and the DF mechanics behind it in
[`docs/SUCCESS.md`](docs/SUCCESS.md) §2):

```
O = 100 · (s1 + s1·s2 + s1·s2·s3 + s1·s2·s3·s4) / 4
```

| tier | sub-score | in short |
|---|---|---|
| s1 survival | `s_surv · s_sec` | deaths and insanities against the founding population; 0 if the fort is lost; halved while raiders are still on the map at the horizon |
| s2 supply | `min(drink, food)` | food counts edible items only (not seeds, empty containers or raw fish), the same count as the observation's `food_edible` (schema 8). Each: half the share of days in stock over the final window, half the projected days of stock left (full at 336 d) |
| s3 wellbeing | `w_stress · w_events` | the share of citizen-days stressed; tantrums, berserks and insanity zero it quickly. Needs met is reported, not scored (score version 7) |
| s4 growth | housing (+ progression at 336 d) | placed beds per citizen, zoned dining seats per two citizens; on full-year games, DF progression steps weighted toward exports |

A tier pays only as far as the tiers below it hold: a fort that runs dry can't buy points with furniture. Items
made are not counted; only outcomes are. The **tier reached** (0–4 gates passed) is reported next to O.

### 1.2 Lab predicates (LT01, LT02, LT03, LT08)

Each lab task has a pass/fail predicate with partial credit (`bench/predicates.py`), scored over its hands-off
window W:

| task | predicate | partial credit |
|---|---|---|
| LT01 drought | no deaths; drink in stock every day of W; ≥ 1 drink per dwarf at the end; ≥ 5 drink brewed in W | 0.5·(share of W with drink) + 0.25·min(1, drink per dwarf) + 0.25·min(1, drink brewed in W / 5), minus 0.25 per death |
| LT02 rescue | no deaths; drink and food in stock every day of W; a built Still and a planted farm plot | 0.4·(W days with drink) + 0.3·(W days with food) + 0.15·Still + 0.15·planted farm |
| LT03 mood | artifact made; the mood dwarf alive, sane and out of the mood at the end; no deaths | 0.2·workshop claimed + 0.3·artifact begun + 0.5·artifact made; 0 if the dwarf went insane |
| LT08 migrant surge | no deaths; drink and food every day of W; drink at the end ≥ drink at A; placed beds ≥ citizens | mean of the four parts |

A lost fort scores 0 on every task.

**Normalisation:** a lab task's score is `ẑ = (p̄ − p̄_noop) / (p̄_anchor − p̄_noop)`, where p̄ is the mean partial
credit over the task's games, `noop` is the do-nothing policy and `anchor` is the organiser's reference witness on
the same private forts. ẑ is capped at 1.5 and not floored. Both reference values are published in
`runner/suites/season0.json` (each lab task's `anchor`: `noop` and `witness`, measured on the private pool).

**Strange moods are off except in the mood task.** On the season-0 sites many moods can't be satisfied with the
tools: many sites have no stone reachable with the season-0 tools, and a mood that demands stone can't be met. So every task
except LT03 runs with DF's own `[ARTIFACTS:NO]` setting, and no strange moods occur. LT03 (and any later mood task)
runs with moods on and uses moods that can be won on its fort; there a failed mood counts normally.

**Read horizons and windows from the task, not from this file.** Each game's horizon and hands-off window are in
`DFBENCH_TASK.task` (`days`, `hands_off`) and `GET /task`, and every response carries `days_left` (plus
`hands_off_in_days` on a lab task). Season 0's official tasks use the published values (OP1 336 days, LT08 hands-off
from day 39, and so on), but later seasons may vary them, for example by a few days, on games your harness hasn't
seen. A harness that times its plans to the exact published numbers may lose points then.

## 2. Suite score

```
S = 0.5 · O(OP1) + 0.3 · O(MY1) + 0.2 · 100 · mean(ẑ_LT01, ẑ_LT02, ẑ_LT03, ẑ_LT08)
```

- O per task is the mean over the task's games. 80% of the weight is on long horizons; OP1, the full year, has the most room above
  the baseline.
- The lab tasks carry 20%. LT01 and LT03 are easy to complete, so for most harnesses they guard against regressions
  rather than separate harnesses; LT02 and LT08 have room above the organiser's witness (ẑ is capped at 1.5).
- MY1 is admitted: doing nothing clearly fails on it (about 17 points against 65–76 for the references and the organiser's reference harness).

## 3. The published scalar: a lower bound

DF varies a lot from game to game, so one lucky batch shouldn't top the board. The **published score is the
one-sided 95% lower confidence bound (LCB) of S**: a stratified bootstrap that resamples games within each task,
10,000 resamples, RNG seeded per submission. Every submission plays **the same private forts with the same
seeds** (common random numbers), so differences between submissions are mostly differences between harnesses.

Games per submission: 8 per lab task, 8 MY1, 8 OP1; 16 MY1 and 16 OP1 for a submission that goes to confirmation
(§4.1).

**How noisy is it?** Measured on the private pool (three runs of the same harness on the same 48 games): the
published score of one harness moves by about 2.7 points (one standard deviation) from run to run, and **two runs of
the same harness differ by about 3.8 points**. Playing the same forts and seeds barely helps: DF's own run-to-run
randomness dominates. So a gain of a point or two can't be told apart from luck in one run, and the season handles
that in three ways rather than with very long runs or a very high bar:

- **Promotion threshold:** a submission is promoted only if its published score beats the current best by at least
  **2.5% of the current best** (Yukon's `minScoreImprovementBips: 250`; about 1.5 points at S ≈ 60, 1.8 at S ≈ 72).
- **Confirmation** before promotion (§4.1).
- **The contender band:** everything near the top is listed, pooled across runs and re-scored (§4.2).

## 4. Staging

1. **Stage 1, every submission:** the four lab tasks and MY1.
2. **Stage 2, OP1 (full year):** unless even a perfect OP1 couldn't make the submission lead: OP1 is played if
   0.5 × the stage-1 upper bound + 0.5 × 100 reaches the current leader's score (OP1's weight is 0.5). In practice
   every harness with a reasonable stage 1 plays OP1. (Until 9 November the bar was the leader's stage-1 point; with
   stage 1 near its ceiling that skipped OP1 for harnesses that could have led on it.)

A stage-1-only result is shown with its stage-1 numbers and marked **not promotable** (it is recorded as
`score: 0, partial: true` with `metrics.stage = 1`, which Yukon treats as a non-improving result, not a failure).
Yukon's PR comment then reads "Scored **0**"; the first rows of its table, `stage2` and `leader_stage1_point`,
say why OP1 wasn't played (your tier plays stage 1 only, or even a perfect OP1 couldn't reach the leader's score)
and what the bar was.

### 4.1 Confirmation (only for a submission that would be promoted)

When the complete score would be promoted (it clears the threshold against the current best), the same scoring
run plays a **second batch of MY1 and OP1**: 8 more games each, on the same private forts with the same seeds. The
published score is then the lower bound over **both batches pooled** (16 MY1 and 16 OP1 games, the labs once):

- if the pooled score still clears the threshold, the confirmation **passed**: the judge checks the submission and
  Yukon promotes it (`metrics.confirmation: passed`);
- if not, it **failed**: the pooled score is still the published score, and Yukon records it as non-improving
  (`metrics.confirmation: failed`, with `metrics.score_first_batch` showing the first batch alone).

A lucky draw has to be lucky twice; a real gain of a few points survives. Only would-be winners pay for it (about an
hour more). Submissions that wouldn't be promoted are scored exactly as before (`metrics.confirmation: not_run`).

**The leader plays alongside.** In the same scoring run, while the confirmation batch plays, the **current leader's
harness** (the `submission/` on `main`) plays the very same confirmation games: the same tasks, forts and seeds, at the
same time. The model provider's behaviour can shift from day to day (we measured a drop of 20 OP1 points for the same
harness between two days, `runs/s0-op1-native-2026-10-28`), and a same-window comparison cancels that. Promotion then
also needs the **paired difference** (your games minus the leader's, game by game) to be above zero at its lower
bound. If it isn't, Yukon records the submission as non-improving (`metrics.confirmation: failed_paired`, published
score 0, with `metrics.score_pooled` keeping the pooled value). Your published score is still your own pooled lower
bound; `metrics.paired_diff_point`, `paired_diff_lb` and `leader_window_point` show the comparison. It costs the
organiser one more batch (about $4–5) per would-be promotion; nothing for you.

### 4.2 The contender band, pooled scores and weekly re-scores


**Attribution during scoring.** The judge sees your formal dependency list only if `submission/dependencies.json`
exists or Yukon has published the submission; otherwise it judges attribution from the note and the code, records
`attribution_verified: false` and `attribution_basis: note+code` in the metrics, and the formal list is checked after
publication (`RULES.md` §8a). A failed check is flagged to the organisers; it never changes the recorded score by
itself.

**Contenders.** Every complete, judge-valid submission whose published score is within **3.8 points** (about one
standard deviation of the difference between two runs) of the leader's pooled point estimate is a **contender**
(`metrics.band: contender`, with `metrics.band_gap`, the distance to the leader). The leader is `band: leader`. A
submission whose run Yukon is about to promote (judge pass, confirmation passed, and Yukon's improvement rule met) is
`band: leader-elect`: the band is computed before Yukon reads the score, and the next run re-bands everyone
against the new leader.
Contenders are as good as the leader within the noise of one run, so they're worth learning from too; their PRs, notes
and attribution are as public as the leader's.

**Pooled scores.** For each contender the organiser keeps all of its scored games: its scoring run, any confirmation
batch, and its re-scores. The **pooled score** is the same suite score and lower bound computed over all of them. More
games, less noise.

**Weekly re-scores.** Each week the organiser re-plays the leader and the contenders most likely to be ahead of it:
every contender with only one run whose upper bound reaches the leader's lower bound (up to eight), and otherwise up
to four in all. They play the full private suite, and the games are added to their pools. A contender whose pooled lower bound falls
out of the band is dropped from the list.

**Leading on pooled games.** A contender whose pooled point estimate is above the leader's, with both re-scored at
least once, is flagged as *leading on pooled games*. This is information, not a promotion: **Yukon's board alone
decides promotion**, and the published list doesn't change it (the organiser may ask Yukon about this case).

**The published list** (`CONTENDERS.md`, on the challenge repo's `contenders` branch, linked from the challenge page)
shows for each contender: its pooled score, lower and upper bounds, number of runs and games, the gap to the leader,
and a link to its PR (note, dependencies and coauthors). Aggregates only, as everywhere else. How to read a contender's note, dependencies and code, and build on it: `SUBMITTING.md` §3a.

## 5. What `score.json` reports

Next to the scalar, every submission reports (per task and overall):
- O and the tier distribution; the four sub-scores (survival, supply, wellbeing, growth);
- lab pass counts (k/n), mean partial credit and ẑ;
- model credits used per game-year, model calls per game-year, wall time per game-year, the number of
  `wall_capped` games, actions used and rejected;
- the stage reached, the comparability key (`dfbench/v3`) and your harness's source digest.
- `confirmation` (passed, failed or not_run) and, after a confirmation, `score_first_batch`;
- `band` (leader, leader-elect, contender or none), `band_gap`, `band_leader_point`, `pooled_point`, `pooled_lb95`, `pooled_runs`.
- after a confirmation, the paired comparison with the leader: `paired_diff_point`, `paired_diff_lb`,
  `leader_window_point`, `challenger_window_point`, `paired_games`, `leader_verified`;
- provider evidence (§6.1): `model_latency_s_per_call`, `reasoning_tokens_per_call`, `completion_tokens_per_call`,
  `route_*` and `drift_*`.

Per-game and per-seed details of the private pool are not published during the season.

### 6.1 Provider drift (report only)

The model is served by one pinned provider (Together, no fallbacks), and we check that it was: every run records a
**routing fingerprint** from a sample of its calls (`route_model_snapshot`, `route_endpoint_id`, `route_providers`,
`route_regions`, `route_attempts_max`, `route_fallbacks`, and `route_consistent`). What a pin can't fix is the
deployment behind the provider's endpoint, so every run also compares its own early-game calls with the season's
reference run (the import baseline): reasoning tokens and which tool the model chose, on identical requests
(`drift_reasoning_ratio`, `drift_ks_p`, `drift_tool_mix_p`, `drift_flag`: none, watch, alert or n/a; `drift_basis` says
what it compared: `same-harness`, `matched:<n>` identical requests, `no-matching-requests` or `no-reference`). The
check is for **re-scores of the same harness** (the baseline, the weekly re-scores): a different submission sends
different requests, so it normally gets `n/a` with `no-matching-requests`. These metrics
never change a score. They tell the organiser and you when official numbers were taken in a different provider
"weather" than earlier ones; the leader-alongside confirmation (§4.1) is what protects promotions from it. Compare
your own local runs in the same session (`dfbench-tk compare`).

## 6. Infra failures

A game is an **infra re-run**, not a score, when the fault is ours or the provider's: the game server or DF
crashed outside your harness's control, or the gateway saw provider outages or throttling above a threshold. Your
harness crashing, hanging or running out of credits is not infra: the fort runs on unmanaged to the horizon and is
scored as it stands (`RULES.md` §6).

A provider error counts only if it is the provider's (5xx, 429 after retries, unreachable). A request the provider
rejects (4xx), a response over the gateway's size limit, or a timeout on a call that asked for more than 8,192 output
tokens is your harness's, and the game is scored as it stands: infra re-runs are for faults a harness can't cause on
purpose.

**DF crashing twice.** An infra game is re-run once, on the same fort and seed. If DF crashes or hangs on the re-run
too, the game is not re-run again: it is scored at the state it reached (from its last daily sample, like a
wall-capped game), or as a lost fort (0) if there's no sample, and `crash_twice` counts it in `score.json`. A harness
that can crash DF on purpose would otherwise re-roll its worst games. The last harness actions before each crash are
kept with the organiser's per-game data, so a crash a harness can trigger is found and fixed.

**Throttling** counts as the provider's only for calls made with at most 2 of the game's calls in flight. The gateway
runs at most 4 calls of a game at once and queues the rest; time in that queue, and 429s caused by the game's own
parallel calls, count against the wall cap like any other harness time.
