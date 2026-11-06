# Submitting (season 0)

> **Versioning.** The rules that apply to your submission are the ones in this repository at the commit your
> submission is based on. Changes during the season are announced and dated. `runner/README.md` has every runner
> flag.

## 1. The harness contract

A submission is the directory **`submission/`**:

```text
submission/
  Dockerfile        required: builds your harness image (any base image, any language)
  ...               your code, prompts, knowledge files, pinned dependency lists
```

- The image's `ENTRYPOINT`/`CMD` is your harness. The runner builds it, starts it once per game, and waits for it
  to exit (or for the game to end).
- **Input:** one environment variable, `DFBENCH_TASK`, a JSON document (`docs/GAME-API.md` §2.1):

  ```json
  {"schema": "dfbench-task/1", "run_id": "…", "api": "v0",
   "game_url": "http://game:8090",
   "model": {"base_url": "http://gateway:8080/v1", "name": "z-ai/glm-5.3-flash", "api": "openai-chat",
             "api_key": "placeholder"},
   "budget": {"credits": 0.50, "unit": "USD at the pinned reference prices", "per": "game"},
   "limits": {"wall_s": 5400, "actions_per_game_day": 40, "max_advance_days": 28},
   "task": {"name": "start-year", "days": 336, "goal": "…", "brief": "…", "hands_off": null}}
  ```

  Read `GET {game_url}/task` for the rules, the tool schemas (OpenAI function format), the query list and the
  reference manual. Then loop: `GET /observe` and `GET /query/...` for facts, model calls to `model.base_url`,
  `POST /act` for actions, `advance_days` to move time.
- **Output:** none required. The score comes from the game, not from anything your harness prints. Your stdout and
  stderr are kept with the game's artifacts (truncated if huge), so log what helps you debug.
- **Exit:** when your harness exits, the server runs the rest of the horizon with no actions. Exiting early is
  allowed and is rarely a good idea.
- **State:** each game starts a fresh container. Nothing persists between games except what is in your image.
- **Resources:** 1 vCPU, 2 GB RAM; network only to `game` and `gateway` (`RULES.md` §3). The
  container's filesystem is **read-only** except `/tmp`, a 1 GiB in-memory scratch that counts against the 2 GB
  (`HOME` and `TMPDIR` are `/tmp`, and `PYTHONDONTWRITEBYTECODE=1`). Write caches and logs there; anything that
  must exist at start goes in the image. At most 512 processes; output beyond 10 MB is dropped. At most 4 model
  calls run at once per game; the gateway queues the rest.

`baseline/` has the plain baseline harness and a minimal example harness, both in this shape, and a small Python
client for the API you may copy. `submission/` starts as a copy of the plain baseline (`submission/README.md`).

## 2. Running locally

Prerequisites: x86_64 Linux with Docker (or macOS on Apple Silicon with Docker Desktop, where DF runs under
Rosetta and is slower), your own download of DF 53.16 and DFHack 53.16-r2, and an OpenRouter API key (the local
gateway calls the model through OpenRouter with the provider pinned to Together, as the verifier does; another
OpenAI-compatible https endpoint serving the same model works with `--upstream`).

1. **Build the DF images** (`docker/README.md`): download the two tarballs, check their sha256, then build two
   images: the plain DF image (`docker/Dockerfile`, which the fort builders use) and on top of it the **game server
   image** (`docker/Dockerfile.game`, which the runner plays as `DFBENCH_GAME_IMAGE`). The plain image alone fails
   every real game at reset. Don't push either image anywhere public.
2. **Build the public forts** (`docs/SEED-FORTS.md`): `docker/task_forts.sh --seeds 2001,2002,2005` for the lab
   tasks; `docker/embark.sh --rules DEFAULT_FORT --seeds 12345` for OP1; `pool/dfpool build-public --task MY1
   --seeds 2001,2002,2005 --image <your DF image>` for MY1 (each MY1 fort is its seed's embark played to day 120 by
   DFHack's automation: one DF container, roughly 10-30 minutes a fort). Lab forts print `TASKFORT`.
   `.yukon/setup.sh` runs steps 1 and 2 (skipping forts already built) and checks that `submission/` builds. The MY1
   builder refuses to start while other containers run (the 120 automation days are slow on a busy host); set
   `DFBENCH_ALLOW_BUSY=1` if your machine has room.
3. **First, the smoke test (free):** `runner/dfbench local smoke`. It plays 3 game-days of LT01 on **real DF with a
   fake model**: no key and no cost, a few minutes. It prints PASS, or FAIL with the likely cause and the next step
   (a missing fort, the wrong DF image, too little Docker memory, a harness that won't start). `.yukon/setup.sh`
   runs it at the end (`DFBENCH_SMOKE=0` to skip). Run it before anything that spends model credits.
4. **Run one game** with the runner (`runner/README.md` has the exact flags):

   ```sh
   export OPENROUTER_API_KEY=...          # your OpenRouter key; only the local gateway container sees it
   runner/dfbench local run --harness submission/ --task scenarios/season0/lt01-drought.json
   ```

   This starts the same three containers as the verifier (your harness, the gateway, the game), on the same
   internal network with the same limits, and writes the game's artifacts and a `score.json` for that game.
   Use the task files in `scenarios/season0/`: a season task file brings the suite's settings with it (lab
   anchors, wall cap, moods, budget). `scenarios/seed/` holds older copies with other seed ranges and no anchors.
   `--stack fake` runs the same flow against toy stand-ins for the game and the model (no DF, no key, seconds):
   use it to check that your harness starts, talks to both services and exits cleanly. The fake takes the real
   tools' argument shapes and site kinds, but its fort is a toy.
   `--stack mixed` plays the **real game with a fake model** (no key, no model cost): the way to test a scripted or
   deterministic layer of your harness against real DF for free.
5. **Run the public suite** (several tasks and seeds, in parallel if you have the cores):
   `runner/dfbench local suite --harness submission/` (`.yukon/run.sh`, what `yukon run` runs, wraps it). Its score
   is computed exactly as the official
   one, on public forts instead of the private pool, so it is a guide, not a prediction.
   It checks that every start fort it needs is built before it starts a container, and names the missing ones.
   Part of the suite: `runner/dfbench local suite --harness submission/ --games LT01 --n 1`, or through the wrapper
   `DFBENCH_SUITE_ARGS="--games LT01 --n 1" yukon run` (`yukon run` itself takes no suite arguments).

**On Apple Silicon:** DF runs under Docker Desktop's Rosetta emulation: correct but noticeably slower than native
x86_64. Give Docker about 6–8 GB of memory per game at a time (DF plus the harness’s 2 GB). A seed can produce a
different embark under Rosetta than on native x86_64, so local forts are representative, not identical to the
official ones.

**What kind of result is this?** Every `score.json` says, and the runner prints it at the top and bottom of a run:
`result_kind` (`local`, or `official` from the scoring workflow), `stack` (`real`, `mixed` or `fake`), `scope`
(`full`, `partial`, `single-task` or `smoke`, with `tasks_played`), `anchors_id` (which suite's anchors, where they
were measured, and the run) and `official_comparable` (true only for a real-stack full suite on the season's private
pool, i.e. official scores). `dfbench-tk inspect` shows the same labels, and `dfbench-tk compare` warns when two
runs differ in them. Only compare like with like.

### Watching your games

Add `--watch` to `runner/dfbench local run`, `local suite` or `local smoke` to record each game you play locally:
the runner builds a watch image from your game image (`docker/Dockerfile.watch`), DF draws into a virtual display
instead of running headless, and after each game you get `<run>/<game>/video/<game>.mp4` and a 4x timelapse
`<game>-4x.mp4` (the runner prints the paths). `--watch-live` also lets you watch while it plays: a view-only VNC
on `127.0.0.1` only, with a password printed per game (on macOS, open the printed `vnc://127.0.0.1:5900` link).
Try it for free first: `runner/dfbench local smoke --watch`.

- **Local only**, on your own copy of the game. The runner refuses `--watch` in CI and it isn't part of any
  official run or of the Yukon flow.
- **Not comparable**: rendering changes how DF runs (it can be slower) and its display settings differ, so a watch
  run's `score.json` says `watch: true` and `comparable: false`, and its key carries `+watch`. Don't compare it with
  a headless run or report it as a result.
- Recordings show Dwarf Fortress, so they are subject to the game's own terms: whether and how you share them is
  your responsibility.

**What's there for diagnosis** (all of it stays available to you; it's how bugs get found):
- the whole trusted side in this repository: the game server (`gameapi/`), the gateway (`gateway/`), the runner
  (`runner/`), the scorers (`bench/outcomes.py`, `bench/predicates.py`) and the task files;
- per game, in the run directory: `game.json` (status and notes, including why a game counted as infra), the
  server's artifacts (`summary.jsonl`, `<run>.daily.json`, DF's events), every API call with its latency
  (`<run>.api.jsonl`), the gateway ledger (`usage.jsonl`: tokens, cost, throttling), your harness's output, and
  `score.json` / `score_detail.json` per run;
- what to look at first: the per-tier sub-scores, the daily samples and DF's events.
  Official runs keep per-game data sealed (the private forts), but their aggregate `score.json` and the run's log
  are public.

Cost: one game-year at the baseline's rate is a few cents of inference; the cap is $0.50.

## 3. The Yukon submission flow

Season 0 runs on Yukon as an open, public challenge.

1. **Get a Yukon account** (sign in with GitHub). The season is open to anyone with a Yukon account, subject to
   the Terms of Service: there is no allowlist, invitation or application. Your submission limits come from your
   Yukon record (`RULES.md` §7, and *Your limits* below).
2. **Install the Yukon CLI and log in:** `yukon login <api-key>`.
3. **Clone the challenge:**
   ```sh
   yukon clone OWNER/arena-fortress-s0/harness-glm-5-3-flash
   ```
   It gives you this repository (in `arena-fortress-s0/` unless you name a directory) with `submission/` as the
   editable path.
4. **Set up and test locally:**
   - `yukon setup` runs the setup command (builds the DF image and the public forts; needs your DF download,
     see `benchmark.json`'s `hardware` text);
   - `yukon run` runs the public suite on your machine and prints its score. Local scores are for your guidance:
     they are not ranked, and Yukon doesn't use them.

> **Your limits** (`RULES.md` §7; read this before your first submission)
>
> - **Tiers, set automatically at each submission:** **established** (a promoted result on another Yukon challenge,
>   or a scored submission here): 7 submissions a week, full suite. **New** (everyone else): 2 a week. **Probation**
>   (a GitHub account younger than 30 days): 1 a week, stage 1 only, for the full 30 days (new GitHub account? Ask the organisers (a known person can be moved to established)). One submission in flight per account; Yukon's
>   own limits (1 in flight, 10 an hour) apply too.
> - **A new account's first submission plays stage 1 only** (the four lab tasks and MY1), so it **can't be
>   promoted**, however well it does. Once it has been scored you are established, and your next submission plays
>   the full suite. Treat your first submission as the one that unlocks the full suite.
> - **A global weekly allowance** covers all accounts. When it's used up, new submissions wait until the next week
>   (Monday 00:00 UTC); the refusal on your pull request says when.
> - **Counts against your week:** a scored submission, a judge fail or hold, a harness that doesn't build.
>   **Doesn't count:** a refusal at admission (a limit, the global allowance, an unchanged harness), a submission
>   you cancel, infra failures on our side.

5. **Write your attribution, then submit.** Attribution is required (`RULES.md` §8) and it is what the season is
   for:
   - `dependencies.json`: every prior submission your harness uses, including the submission(s) that produced the
     `main` you started from (while `main` still holds the organiser's plain baseline there is none to declare: say
     so in the note). The file is a JSON array of `{"submissionId": "<full uuid>", "rationale": "what you used",
     "evidence": "where, e.g. submission/plain/harness.py:20-60 against the predecessor"}`, 64 KiB at most;
     `--no-dependencies` only if you truly use none. A dependency
     must be a submission on this challenge that Yukon has published (any submission with a candidate commit:
     promoted or not, scored or not); at most 20. Ideas from elsewhere (another challenge, a paper, a thread) go in
     the note;
   - **Recommended:** also put a copy at `submission/dependencies.json`. Yukon hides your declared list from the
     organisers until your submission is published, so the judge can only see this copy while scoring (`RULES.md`
     §8a). Without it, the judge relies on `NOTE.md`, so name what you build on there either way.
   - `NOTE.md`: your public research note: what you changed, why, what you inherited and from whom (submissions, people,
     discussion threads, published ideas), and what you measured. **Between 5 KiB and 100 KiB** (`yukon submit`
     refuses anything shorter or longer). Don't repeat the `Model:` and `Harness:` lines: `--model` and `--harness`
     add them. Write it for readers: **don't predict or describe the automated judge's verdict, and don't claim special
     status** (e.g. "this is an official test"); the judge treats text aimed at the review as manipulation (`RULES.md`
     §5) and fails the submission;
   - then:
     ```sh
     yukon submit --note-file NOTE.md --dependencies-file dependencies.json \
       --model "<AI model you used to build it>" --harness "<coding agent you used>" [--coauthors <handles...>]
     ```
   It packages `submission/` (≤ 25 MiB compressed, ≤ 100 MiB expanded) as it is on disk, including files `.gitignore`
   lists, and sends it with the attribution. Python `__pycache__/` folders from local runs are harmless (scoring
   deletes them before the build and the judge skips them), but other build output and large files count against the
   limits: remove them first. Submissions with missing or
   false attribution aren't ranked.
6. **What happens next:**
   - Yukon commits your archive to the branch `submissions/<id>` of the challenge repo, opens a pull request (the
     record) and dispatches the scoring workflow (`score.yml`, GitHub Actions) on it. Scoring runs on GitHub-hosted
     runners; when several submissions are scoring at once, yours may wait in Yukon's queue first;
   - **admission:** the workflow checks that the pull request changes only `submission/` and is based on the
     current challenge tree, screens `submission/`, reads your tier and checks your limits. It comments on the pull
     request either way: admitted (with what this attempt costs you this week) or not admitted (why, and that it
     doesn't count);
   - it builds your image on a fresh VM with no secrets present, then plays stage 1 on the season's **private
     pool**: 40 games (8 per lab task and 8 MY1), each in its own job and its own three-container stack, with the
     organiser's model key held by the gateway only. A game lost to the infrastructure is played again;
   - if stage 1 could still lead and your tier plays the full suite, stage 2 runs: 8 OP1 games (`SCORING.md` §4);
   - the trusted scorer writes `score.json`. A score that would be promoted then plays the confirmation batch (8
     more MY1 and 8 more OP1, with the leader's harness alongside; `SCORING.md` §4.1) and goes to the judge
     (`RULES.md` §8a). Yukon posts the score and metrics on the pull request and the board.
   Expected wall time: about 1–1.5 h for a full submission, about 45 min for stage 1 only, and about an hour more
   for a confirmation batch.
7. **Check status:** `yukon submissions`; cancel a queued one with `yukon cancel <id>`.

Promotion is automatic when the lower-bound score beats the current best by at least 2.5% (`SCORING.md` §3), **after the
automated judge passes the submission**
(`RULES.md` §8a): attribution, fair play and contents. A failed or held judgment isn't promoted; the reasons are
posted on your pull request. The judge's report is published with the run.
With the early judge on (announced on the challenge page), the judge reviews every submission before its games and
posts its verdict on the pull request within minutes; a fail or hold stops the run before any game (`RULES.md` §8a).

## 3a. Building on the leader and the contenders

You start from the leader (`main` holds its `submission/`), but you don't have to stop there. Every scored submission,
promoted or not, stays public and can be your starting point, as long as you credit it (`RULES.md` §8) and add a
substantive improvement of your own (re-submitting someone else's harness with cosmetic changes is a cross-account
redraw: Terms of Service §4).

**The contender list** (`CONTENDERS.md` on this repo's `contenders` branch, linked from the challenge page) shows
the submissions that are statistically as good as the leader: every complete, judge-valid submission whose score
is within 3.8 points of the leader's pooled score (`SCORING.md` §4.2). How it's made:
- each scoring run tags its submission's band (`leader`, `contender` or `none`; `metrics.band` on your PR);
- once a week the organiser re-plays the leader and the contenders most likely to be ahead of it, pools each one's
  games across runs, and publishes the list (aggregates only: pooled score, bounds, runs, games, gap to the leader,
  a link to the PR);
- it is information, not a ranking change: only Yukon's board promotes. A contender *leading on pooled games* is
  flagged there.

**How to use it:** a contender's pooled score is a better estimate of how good it is than its single run, so the
list tells you which ideas are worth reading even when they weren't promoted (several differ from the leader by less
than the noise of one run). For any submission id on the list (or in `yukon submissions --all`):

```sh
yukon submission-note <id>          # its public research note: what it changed and what it measured
yukon attribution declared <id>     # what it declared it builds on
yukon reset <id>                    # restore your submission/ from its commit (accepted or not; commit first)
git fetch origin submissions/<id>   # or read it in git: its branch, and its pull request, stay public
```

Then measure locally (`runner/dfbench local suite`, or the toolkit's `compare`), and when you submit, declare every
submission you used in `dependencies.json` and say what you took from each in `NOTE.md`.

## 4. Before you submit

- `submission/Dockerfile` builds from a clean checkout with no network beyond public registries, and the
  dependencies are pinned.
- No credentials, keys or `.env` files anywhere in `submission/` (screened, and rejected if found).
- It has run end to end locally on at least one lab task and one longer task through `runner/dfbench local run`, within
  the credit and wall limits.
- Your `dependencies.json` and `NOTE.md` credit everything you used (`RULES.md` §8: attribution is required).
- You've read `RULES.md` §4 (what a submission may contain) and §8 (submissions are open to all participants and
  licensed Apache-2.0; attribution is required).
