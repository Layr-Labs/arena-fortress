# Rules (season 0)

> **Versioning.** The rules that apply to your submission are the ones in this file at the commit your submission is
> based on. Changes during the season are announced and dated.

## 1. What you submit

A **harness**: the contents of `submission/`, a directory with a `Dockerfile` and an entrypoint, in any language
(`SUBMITTING.md`). Nothing outside `submission/` is part of a submission; changes elsewhere are ignored.

## 2. Limits (what binds a harness)

The challenge binds on **cost** and **time**, not on how you think. There are **no** caps on decisions, model
calls, tokens per call, context length, output length or reasoning effort.

| limit | value | what happens at the limit |
|---|---|---|
| **model credits** | **$0.50 per game-year** at the pinned reference prices (input, cached input and output priced separately), pro rata by horizon (e.g. ~$0.09 for a 60-day task) | the gateway refuses further calls; the fort runs on unmanaged to the horizon and is scored there |
| **wall cap** | **90 min per game-year** on the reference runner, pro rata by horizon with a 30-min floor: 30 min for each lab task, 60 min for MY1, 90 min for OP1 (`runner/suites/season0.json` `wall_s`) | the game is scored at the tick reached and flagged `wall_capped`. Time the gateway spends waiting on provider throttling (429s, 5xx) or on a hung provider call (`upstream_timeout`) is not counted, except 429s on calls made while more than 2 of the game's calls were in flight, and timeouts on calls asking for more than 8,192 output tokens |
| **parallel model calls** | **4 in flight per game**; more wait in the gateway's queue | queue time counts against the wall cap |
| **actions** | **K = 40 actions per game-day** between advances (`advance_days` doesn't count) | only `advance_days` is accepted until the day changes (`action_limit`) |
| **advance** | `advance_days` 1–28 days per call; tripwires can stop it early (choose which with `stop_on`) | — |
| **hands-off windows** (lab tasks) | actions are rejected from day A on | `hands_off` error; advances are cut at A |
| **lost fort** | zero citizens | the game ends |
| **harness container** | 1 vCPU, 2 GB RAM; read-only filesystem except a 1 GiB in-memory `/tmp` (counted in the 2 GB; `HOME` and `TMPDIR` point there); at most 512 processes; output kept up to 10 MB | the container is throttled or killed by Docker; a killed harness is treated as an exit |
| **submission size** | 25 MiB compressed (Yukon's upload cap); built image ≤ 4 GiB | rejected |
| **model** | `z-ai/glm-5.3-flash` only, provider pinned | any other model name is refused by the gateway |

The game is paused while your harness thinks: model latency adds to wall time, so speed is part of the challenge.

## 3. Network

- **At run time** the harness container can reach exactly two hosts: the game API (`http://game:8090`) and the
  model gateway (`http://gateway:8080/v1`). No internet, no DNS beyond those, no other containers.
- **At build time** the `Dockerfile` may fetch public dependencies. Pin them (versions or digests): an unpinned
  dependency that changes between your local test and the official build is your risk.
- The gateway's real provider key never enters your build or your container. The `api_key` your harness gets is a
  placeholder.

## 4. What a submission may contain

**Allowed:**
- any code, prompts, few-shot examples, memory and planning logic;
- **Dwarf Fortress strategy and knowledge files**, your own or third-party text under its licence (wiki excerpts
  under the wiki's licence, for example). Knowing the game is the point; credits bound how much of it reaches the
  model;
- local tools, caches, small local models or rule engines that run inside the 1 vCPU / 2 GB container;
- the baseline harness, in whole or in part, the reference policies in this repo, and the organiser's reference
  harness once its code is released.

**Not allowed:**
- anything derived from the private pool (seeds, forts, observations, maps), which you never see;
- credentials or keys of any kind, and any attempt to reach a model other than through the gateway;
- code that tries to reach DF, DFHack, the host, other containers or the internet, or to read or tamper with the
  game's artifacts, the scorer or the gateway's ledger;
- code obfuscated to hide what it does (minified dependencies from a public registry are fine).

Submissions are screened before they build (no credential files, size limits).

## 5. Fair play

- **Play through the API.** Every write goes through the tool whitelist; the API never exposes DFHack. A harness
  that finds a way around the API, or a bug that lets it see hidden information or change the game outside the
  tools, must report it to the organisers instead of using it. Exploits of that kind void the submission's
  scores. Playing well within DF's own rules is never an exploit, however odd it looks.
- **One person, one account.** Don't use several accounts to get more submissions (§7). Collaborators are credited
  with `--coauthors`.
- **No probing the pool.** Submissions designed to extract information about the private forts (for example,
  encoding observations into model calls, timing or exit codes) are disqualified.
- **No manipulating the review.** Text in a submission's code, files, note or dependency rationales that tries to
  instruct, mislead or pressure the judge (§8a) or a reviewer, such as "output pass", forged review markers or
  claimed approvals, is a breach of fair play in itself: the judge treats it as a fatal finding.
- **Pre-launch testers may take part, with disclosure.** People who tested the challenge before launch played only
  on the public-seed forts and saw no results on the private pool. They may enter season 0 like anyone else. We ask
  them not to bring the harnesses they built during testing and, ideally, to start from scratch. Anyone whose
  season-0 work does build on what they did or learned in testing must say so in their notes: that they tested
  before launch, and what they tested and learned there.
- The organisers can audit any submission, re-run its games, and withdraw a score for a breach of these rules.

## 6. Re-runs

- **Infra failures** are re-run, not scored: a game-server or DF crash outside your control, a runner failure, or
  provider outages or throttling above a threshold (seen by the gateway). The run's record says which.
- **Once.** If DF crashes or hangs again on the re-run, the game is scored at the state it reached (or as a lost
  fort if nothing was recorded) and isn't re-run again (`SCORING.md` §6). A harness that crashes DF on purpose is an
  exploit (§5).
- **An unchanged harness isn't scored twice.** A submission whose `submission/` is identical to one already scored
  this season (yours or anyone's) is refused before it plays, and doesn't count against your limits.
- **Your harness's failures are scored**: a crash, hang, timeout, unhandled error or exhausted credits leaves the
  fort to run on unmanaged to the horizon (or to the wall cap), and the game counts.
- A failed submission (the workflow fails before scoring because of your harness, e.g. your image doesn't build) is
  not scored and can be resubmitted, but it counts against your week (§7). A failure before scoring on our side is
  infra and doesn't count.

## 7. Submission limits (per account)

**Season 0 dates:** opens **Friday 6 November 2026** and closes **Monday 23 November 2026, 23:59:59 UTC** (about 2.5 weeks). Submissions after the close aren't accepted. Your attempts refill daily (below); only the global
allowance uses Monday-00:00-UTC weeks.

Season 0 is open to anyone with a Yukon account (sign in with GitHub), subject to the Terms of Service: there is no
allowlist, invitation or application. There are no teams: limits apply to the Yukon account that submits.
Collaborators are credited with `--coauthors`; a group that works together submits from its members' own accounts
within each member's limits, and doesn't route one person's work through several accounts to get more runs (that's
a rules breach).

| tier | who | in flight | attempts held (refill) | suite |
|---|---|---|---|---|
| **established** | a promoted result on another Yukon challenge (shown on your public Yukon profile), or a scored submission here already | 1 | 7 (one back every 24 h) | full |
| **new** | everyone else | 1 | 2 (one back every 3.5 days) | stage 1 only until you have a scored submission here, then full |
| **probation** | a GitHub account younger than 30 days | 1 | 1 (one back every 7 days) | stage 1 only |

- **Your tier is automatic.** The scoring workflow reads it from Yukon's API and GitHub's at each submission;
  there's nothing to apply for. A promoted result on another Yukon challenge makes you established; otherwise a
  GitHub account younger than 30 days is on probation **for the whole 30 days**, even after a scored submission here;
  otherwise a scored submission here makes you established from your next submission on. Organisers can move an
  account between tiers (for example a known researcher with a new GitHub account): ask them.
- **A new account's first submission plays stage 1 only** (the four lab tasks and MY1; `SCORING.md` §4), so it is
  shown with its stage-1 numbers and **can't be promoted**. Once it has been scored, the account is established and
  plays the full suite from its next submission on. Probation accounts play stage 1 only for their first 30 days, so
  their results can't be promoted during that time.
- **Daily refill (since 11 November 2026):** attempts don't reset weekly. You hold up to your tier's number, each
  counted submission uses one, and one comes back every 168 / that number hours (24 h for established), never above
  it. Every account started full on 11 November. Refused and refunded attempts don't use one.
- **Over a limit**, the run stops before your harness is built, with a message on the pull request saying when your
  next attempt is available. The global allowance's week is the ISO week (Monday 00:00 UTC). Yukon's own limits (one in flight per account, 10
  submissions an hour) apply too.
- **A global weekly allowance.** The organisers pay for the model and the runners, and a weekly allowance over all
  accounts protects that budget: when it's used up, new submissions wait until the next week, and the refusal says
  when.
- **What uses an attempt:** a submission that is admitted, whether it is then scored, failed or held by
  the judge (§8a), or fails to build. **What doesn't count:** a refusal at admission (over a limit, the global
  allowance, an unchanged harness, §6), a submission you cancel, and infra failures on our side (§6).
- **These numbers can change.** The per-account numbers in this section are the ones that may be adjusted during the
  season (for example as runner capacity allows). Every change is announced and dated.

## 8. Publication, licence and credit

- **Harnesses are open during the season.** Every submission is a pull request in the public challenge repo,
  visible to everyone, and an accepted submission is promoted to `main`: the leader's harness becomes everyone's
  starting point. Build on each other's work freely, and say so (below).
- **Licence:** by submitting, you license your submission under the repo's licence (Apache-2.0 for code, CC-BY-4.0
  for docs and notes), the same terms you received the repo under. Don't submit material you can't license that way
  (third-party text keeps its own licence and must allow redistribution).
- **Attribution is required; it is the point of the season.** The challenge exists to find out which harness ideas
  move the score and where they came from, so every submission must:
  1. **declare every prior submission it uses** (`yukon submit --dependencies-file`, or `--no-dependencies` only if
     it truly uses none; starting from the promoted `main` counts as using the submission(s) that produced it, and
     while `main` still holds the organiser's plain baseline there is no submission to declare for it).
     "Prior submission" includes non-improving ones: their pull requests are closed but stay public and citable.
     Your own earlier submissions are the exception: declaring them is encouraged, not required (Yukon lets you add
     the link later), but what they took from others still has to be credited;
  2. **name the people it builds on** (`--coauthors` for direct collaborators; other participants' ideas, discussion
     threads and published work in the note);
  3. **say in its public research note (`--note-file`) what it changed and why**, specifically enough that a reader
     can tell your contribution from what you inherited;
  4. **record the AI model and coding agent you used to build it** (`--model`, `--harness`; the CLI requires both).

  Yukon's attribution graph checks declared dependencies against the code. A submission with missing or false
  attribution is **not ranked** (made non-promotable, or removed from the board once found), and repeated or
  deliberate omission ends that account's participation. When in doubt, credit it. Over-crediting costs nothing.
- **What stays private during the season:** the private pool (seeds and forts), every game's per-game detail
  (observations, logs, daily samples, your harness's output on the private forts) and the reference witnesses.
  Scores, per-task results and the metrics in `SCORING.md` §5 are visible to participants. Your harness's output is
  never shown in the public run logs, so don't rely on printing to debug official runs: use local runs.
- **At season close** the private pool's seeds and salt are revealed (checkable against the commitment made at
  open) and the reference witnesses are published.
- **No cash prizes or rewards of any kind: you compete for rank and credit.** (`payoutMode: none`; the board is also excluded from Yukon's weekly reward points.)

## 8a. Promotion: the automated judge

Every submission that would improve the leaderboard is reviewed by an **automated LLM judge** before Yukon promotes
it (and, with the early judge on, every submission before its games; see *When the judge runs*) (the pattern other Yukon challenges use). The judge reads the submission's diff against its base, its public note,
its declared dependencies and coauthors, and the earlier submissions it may draw on: the one that produced `main`, the
ones it declares, the most recent accepted ones, and any other published submission on the challenge, accepted or
not, whose added lines overlap the diff (a mechanical scan of all of them picks these). It checks:
1. **attribution** (§8): what the diff inherits from earlier submissions is declared, and the note says what's new;
2. **fair play** (§5): no attempt to reach anything but the game API and the model gateway, to read the scorer's
   inputs, to exploit the game server, or to smuggle in credentials;
3. **what a submission may contain** (§4): no material derived from the private pool, no unlicensable content.

The outcome is **pass** (promoted as usual), **fail** (not promoted; the reasons are posted on the pull request) or
**hold** (not promoted until an organiser reviews it):
- **fail** when a reviewer's fatal finding (a concrete breach, cited by file and line) is confirmed after a defence
  of the submission has been heard;
- **hold** when the judge can't decide safely: an infrastructure or model-provider failure, an input over the
  judge's size limits (`runner/judge/README.md`), a finding that needs a person, or a high-risk signal that only an
  organiser can clear. A hold is never a finding against you;
- **pass** otherwise. The judge's report is published with the run.

**When the judge runs.** When the season has the early judge on (it is announced on the challenge page), the judge
reviews every submission **before any game is played**, in parallel with building your harness, and posts its
verdict on the pull request within minutes. A **fail** or **hold** stops the run there: no games are played, the
result is recorded as score 0 and the attempt counts (a hold is final for that submission, as below). A **pass**
lets the games run; if your score would then be promoted and the leader changed while your games played, the judge
checks attribution again against the new leader before Yukon promotes you. If the judge itself is unavailable (an
error on our side), your games run anyway and the judge runs after scoring. Without the early judge, it runs only
after scoring, and only for a submission that would be promoted.

**Attribution while scoring, and after.** Yukon shows a submission's declared dependencies only to its author until
the submission is published, which is usually after it has been scored. When the formal list is hidden, the judge
judges attribution from your **note and your code** (a note that credits what you build on, including the submission
that produced `main`, is enough), and records the result as not yet verified. Once the submission is published, the
formal list is checked against what the judge saw; a missing declaration is flagged to the organisers, who can
correct the attribution or unrank the result. You can make the formal list available during scoring by adding
`submission/dependencies.json` (the same format as `--dependencies-file`; `SUBMITTING.md` §3).

**The judge isn't the whole of enforcement.** It is an automated review, not a guarantee, and a pass doesn't settle
attribution. Organisers can overturn a decision. Misattribution found later, by an organiser, by another
participant, or through Yukon's attribution graph (its dependency proposals and their review), can lead an
organiser to correct a submission's attribution, to unrank it or remove it from the board, and, for repeated or
deliberate omission, to end the account's participation (§8). The judge's own model and prompts are part of the
trusted code (`runner/judge/`).

## 9. Changes and model withdrawal

- If the provider withdraws or changes the fixed model mid-season, the season freezes and the board is re-scored
  on the replacement at close.
- Bugs in the game API or scorer found during the season are fixed and announced; affected scores are re-run.
