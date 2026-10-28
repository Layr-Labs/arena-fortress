# Scoring (season 0)

> Pre-release draft. Numbers marked *provisional* may change before the season opens; the version that applies is
> the one in this file when the season opens, and every change after that is announced.

Scoring runs on the trusted side only: the game server writes the game's artifacts, the runner scores them with
`bench/outcomes.py` and `bench/predicates.py`, and writes `score.json`. Your harness never sees the scorer's inputs
beyond what the game API shows any player.

## 1. Per game

### 1.1 Outcome score O (OP1, MY1)

The gated outcome score (score version 6; full definition and the DF mechanics behind it in
[`docs/SUCCESS.md`](docs/SUCCESS.md) §2):

```
O = 100 · (s1 + s1·s2 + s1·s2·s3 + s1·s2·s3·s4) / 4
```

| tier | sub-score | in short |
|---|---|---|
| s1 survival | `s_surv · s_sec` | deaths and insanities against the founding population; 0 if the fort is lost; halved while raiders are still on the map at the horizon |
| s2 supply | `min(drink, food)` | food counts edible items only (not seeds or empty containers; the observation's `food_edible` is broader). Each: half the share of days in stock over the final window, half the projected days of stock left (full at 336 d) |
| s3 wellbeing | `w_calm · w_events` | stress and needs met; tantrums, berserks and insanity zero it quickly |
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
the same private forts. ẑ is capped at 1.5 and not floored. Both reference scores are published at season open.

**Strange moods are off except in the mood task.** On the season-0 sites many moods can't be satisfied with the
tools: many sites have no stone reachable with the season-0 tools, and a mood that demands stone can't be met. So every task
except LT03 runs with DF's own `[ARTIFACTS:NO]` setting, and no strange moods occur. LT03 (and any later mood task)
runs with moods on and uses moods that can be won on its fort; there a failed mood counts normally.

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
2. **Stage 2, OP1 (full year):** only if stage 1's upper bound reaches the current leader's stage-1 point
   estimate, i.e. only if the submission could still lead.

A stage-1-only result is shown with its stage-1 numbers and marked **not promotable** (it is recorded as
`score: 0, partial: true` with `metrics.stage = 1`, which Yukon treats as a non-improving result, not a failure).

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

### 4.2 The contender band, pooled scores and weekly re-scores

**Contenders.** Every complete, judge-valid submission whose published score is within **3.8 points** (about one
standard deviation of the difference between two runs) of the leader's pooled point estimate is a **contender**
(`metrics.band: contender`, with `metrics.band_gap`, the distance to the leader). The leader is `band: leader`.
Contenders are as good as the leader within the noise of one run, so they're worth learning from too; their PRs, notes
and attribution are as public as the leader's.

**Pooled scores.** For each contender the organiser keeps all of its scored games: its scoring run, any confirmation
batch, and its re-scores. The **pooled score** is the same suite score and lower bound computed over all of them. More
games, less noise.

**Weekly re-scores.** Each week the organiser re-plays the leader and up to four contenders (those most likely to be
ahead of it) on the full private suite, and adds the games to their pools. A contender whose pooled lower bound falls
out of the band is dropped from the list.

**Leading on pooled games.** A contender whose pooled point estimate is above the leader's, with both re-scored at
least once, is flagged as *leading on pooled games*. This is information, not a promotion: **Yukon's board alone
decides promotion**, and the published list doesn't change it (the organiser may ask Yukon about this case).

**The published list** (`CONTENDERS.md`, on the challenge repo's `contenders` branch, linked from the challenge page)
shows for each contender: its pooled score, lower and upper bounds, number of runs and games, the gap to the leader,
and a link to its PR (note, dependencies and coauthors). Aggregates only, as everywhere else.

## 5. What `score.json` reports

Next to the scalar, every submission reports (per task and overall):
- O and the tier distribution; the four sub-scores (survival, supply, wellbeing, growth);
- lab pass counts (k/n), mean partial credit and ẑ;
- model credits used per game-year, model calls per game-year, wall time per game-year, the number of
  `wall_capped` games, actions used and rejected;
- the stage reached, the comparability key (`dfbench/v3`) and your harness's source digest.
- `confirmation` (passed, failed or not_run) and, after a confirmation, `score_first_batch`;
- `band` (leader, contender or none), `band_gap`, `band_leader_point`, `pooled_point`, `pooled_lb95`, `pooled_runs`.

Per-game and per-seed details of the private pool are not published during the season.

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
