# Submitting (season 0)

> Pre-release draft. Steps marked **[awaiting Yukon]** depend on answers from the Yukon team and may change. The
> `runner/` commands describe the interface being built; check `runner/README.md` for the current state.

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
- **Resources:** 1 vCPU, 2 GB RAM (*provisional*); network only to `game` and `gateway` (`RULES.md` §3). The
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

1. **Build the DF image** (`docker/README.md`): download the two tarballs, check their sha256, build. Don't push
   the image anywhere public.
2. **Build the public forts** (`docs/SEED-FORTS.md`): `docker/task_forts.sh --seeds 2001,2002,2005` for the lab
   tasks; `docker/embark.sh --rules DEFAULT_FORT --seeds 12345` for OP1; `pool/dfpool build-public --task MY1
   --seeds 2001,2002,2005 --image <your DF image>` for MY1 (each MY1 fort is its seed's embark played to day 120 by
   DFHack's automation: one DF container, roughly 10-30 minutes a fort). Lab forts print `TASKFORT`.
   `.yukon/setup.sh` runs steps 1 and 2 (skipping forts already built) and checks that `submission/` builds.
3. **Run one game** with the runner (`runner/README.md` has the exact flags):

   ```sh
   export OPENROUTER_API_KEY=...          # your OpenRouter key; only the local gateway container sees it
   runner/dfbench local run --harness submission/ --task scenarios/season0/lt01-drought.json
   ```

   This starts the same three containers as the verifier (your harness, the gateway, the game), on the same
   internal network with the same limits, and writes the game's artifacts and a `score.json` for that game.
   Use the task files in `scenarios/season0/`: a season task file brings the suite's settings with it (lab
   anchors, wall cap, moods, budget). `scenarios/seed/` holds older copies with other seed ranges and no anchors.
   `--stack fake` runs the same flow against toy stand-ins for the game and the model (no DF, no key, seconds):
   use it to check that your harness starts, talks to both services and exits cleanly.
4. **Run the public suite** (several tasks and seeds, in parallel if you have the cores):
   `runner/dfbench local suite --harness submission/` (`.yukon/run.sh`, what `yukon run` runs, wraps it). Its score
   is computed exactly as the official
   one, on public forts instead of the private pool, so it is a guide, not a prediction.
   It checks that every start fort it needs is built before it starts a container, and names the missing ones.

What to look at after a game: the per-tier sub-scores, the daily samples (`<run>.daily.json`), DF's events, every
API call with its latency (`<run>.api.jsonl`) and the gateway ledger (`usage.jsonl`: tokens, cost, throttling).

Cost: one game-year at the baseline's rate is a few cents of inference (*provisional*); the cap is $0.50.

## 3. The Yukon submission flow

Season 0 runs on Yukon as an open, public challenge.

1. **Get a Yukon account** (sign in with GitHub). No invitation is needed. Your submission limits come from your
   Yukon record (`RULES.md` §7).
2. **Install the Yukon CLI and log in:** `yukon login <api-key>`.
3. **Clone the challenge:** `yukon clone <challenge>` **[awaiting Yukon: the challenge's name and ref]**. It
   gives you this repository with `submission/` as the editable path.
4. **Set up and test locally:**
   - `yukon setup` runs the setup command (builds the DF image and the public forts; needs your DF download,
     see `benchmark.json`'s `hardware` text);
   - `yukon run` runs the public suite on your machine and prints its score. Local scores are for your guidance:
     they are not ranked, and Yukon doesn't use them.
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
   - `NOTE.md`: your public research note: what you changed, why, what you inherited and from whom (submissions, people,
     discussion threads, published ideas), and what you measured. **Between 5 KiB and 100 KiB** (`yukon submit`
     refuses anything shorter or longer). Don't repeat the `Model:` and `Harness:` lines: `--model` and `--harness`
     add them;
   - then:
     ```sh
     yukon submit --note-file NOTE.md --dependencies-file dependencies.json \
       --model "<AI model you used to build it>" --harness "<coding agent you used>" [--coauthors <handles...>]
     ```
   It packages `submission/` (≤ 25 MiB compressed, ≤ 100 MiB expanded) and sends it with the attribution. Submissions with missing or
   false attribution aren't ranked.
6. **What happens next** **[awaiting Yukon: runner, minutes, private-pool staging]**:
   - Yukon commits your archive to a branch of the challenge repo, opens a pull request (the record) and starts
     the scoring workflow on it;
   - the workflow builds your image (no secrets present), then plays stage 1 on the private pool, every game in
     parallel, each in its own three-container stack with the organiser's key held by the gateway only;
   - if stage 1 could still lead, stage 2 (OP1) runs (`SCORING.md` §4);
   - the trusted scorer writes `score.json`; Yukon posts the score and metrics on the pull request and the board.
   Expected wall time: ~1–1.5 h for a full submission, ~45 min for stage 1 only (*provisional*).
7. **Check status:** `yukon submissions`; cancel a queued one with `yukon cancel <id>`.

Promotion is automatic when the lower-bound score beats the current best by at least 2% (`SCORING.md` §3), **after the
automated judge passes the submission**
(`RULES.md` §8a): attribution, fair play and contents. A failed or held judgment isn't promoted; the reasons are
posted on your pull request. The judge's report is published with the run.

## 4. Before you submit

- `submission/Dockerfile` builds from a clean checkout with no network beyond public registries, and the
  dependencies are pinned.
- No credentials, keys or `.env` files anywhere in `submission/` (screened, and rejected if found).
- It has run end to end locally on at least one lab task and one longer task through `runner/dfbench local run`, within
  the credit and wall limits.
- Your `dependencies.json` and `NOTE.md` credit everything you used (`RULES.md` §8: attribution is required).
- You've read `RULES.md` §4 (what a submission may contain) and §8 (submissions are open to all participants and
  licensed Apache-2.0; attribution is required).
