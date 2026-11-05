# runner/: the season-0 runner, `dfbench` CLI and trusted scoring

Runs games of the harness challenge (`docs/GAME-API.md` §2, §6; `challenge/SCORING.md`): one Docker Compose project
per game, suites in stages, artifact collection, and the trusted scorer that writes `score.json` for Yukon. Python 3
stdlib plus `docker compose` (v2) through `subprocess`. It runs real games (the DF image with `gameapi/server/`
and the real gateway, `gateway/`) and, for tests, the same flow against **fakes** of the game server and the
gateway (`runner/fakes/`, `--stack fake`). The server interface it relies on is below ("Interfaces and fakes").

## Architecture

```text
dfbench (trusted, on the host; the only process with Docker access)
  1. docker build <harness dir>          no secrets in the env; image tag = <prefix>-harness:<source digest>
  2. compose up game                     wait for GET /health and GET /task  (via `compose exec game python3 ...`)
                                         a failed start (/health phase failed) or an exited game container
                                         fails at once, with its last log lines, instead of waiting out the timeout
  3. compose up gateway                  the key enters here only (OPENROUTER_API_KEY in the gateway container)
  4. compose up harness                  env DFBENCH_TASK (contract §2.1), built from the server's /task
  5. poll: harness exited? game finished? gateway blocked_reason (credits out / usage unknown / upstream_unreliable)?
     harness exited early or credits out -> POST /finish (the server runs the fort on, unmanaged, to H)
     runner deadline (wall cap + grace) -> stop harness, POST /finish
  6. copy bounded logs, compose down -v; write <game>/game.json (status ok | infra)
  7. dfbench score: game server artifacts + gateway ledger -> score.json
```

Per-game Compose project (`compose/compose.yml` + an overlay: `compose.fake.yml` or `compose.real.yml`):

| service | networks | mounts | limits |
|---|---|---|---|
| `harness` (untrusted) | `game_internal` | none | `--harness-cpus` (1), `--harness-mem` (2g, no swap), pids 1024, `cap_drop: ALL`, `no-new-privileges`, log 10 MB |
| `gateway` (trusted, `gateway/`) | `game_internal`, `egress` | `<game>/gateway` → `/out` (ledger, status) | 512 MB |
| `game` (trusted, DF image + `gameapi/server`) | `game_internal` | scenario JSON (ro), `<game>/game` → `/artifacts`, `<game>/gateway` → `/ledger` (ro), start forts (ro, real only) | `--game-mem` (3g, no swap) |

`game_internal` is `internal: true` (no route out). No port is published. The harness reaches only
`http://game:8090` and `http://gateway:8080/v1` (checked: no internet, no DNS, DFHack's 5000 refused since
`df/dfhack-config/remote-server.json` keeps `allow_remote: false`).

## CLI

```sh
runner/dfbench local run   --harness DIR --task scenarios/season0/lt01-drought.json [--seed K] [--n N] [--parallel P]
                           [--budget 0.50] [--out DIR] [--wall-s S]
runner/dfbench local suite --harness DIR [--suite runner/suites/season0-public.json] [--games LT01,MY1-0] [--stages 1]
runner/dfbench suite run   --harness DIR --suite runner/suites/season0.json [--stages 1,2] [--games IDS]
                           [--leader-stage1 X]
runner/dfbench suite plan  --suite FILE [--stages 1] [--per-job 2] [--per-job-long 1]   # CI matrix JSON
runner/dfbench score DIR   [--suite FILE]                                             # DIR/score.json + score_detail.json
```

Common flags: `--stack real|fake|mixed` (fake = `runner/fakes` for game and gateway, no DF, no key; mixed = the real
game server with the fake gateway, to test the server without a model: `compose.real.yml` + `compose.mixed.yml`), `--model`
(`z-ai/glm-5.3-flash`), `--key-env NAME` (default `DFBENCH_PROVIDER_KEY`, else `OPENROUTER_API_KEY`), `--upstream URL`
(the gateway's upstream), `--harness-cpus`, `--harness-mem`, `--game-mem`, `--retries N` (re-runs of infra
failures; earlier attempts are kept in `<game>/attempt-<n>/`, which the scorer skips), `--resume` (skip games whose `game.json` says ok), `--harness-image TAG --harness-digest D` (skip the
build; CI builds once), `--run-prefix` (Compose project and container prefix), `--log-cap BYTES` (harness output
kept, 5 MiB), `--poll`, `--startup-timeout`. Env: `DFBENCH_GAME_IMAGE` (default `yukon-df:s0`),
`DFBENCH_GATEWAY_IMAGE` (default: built from `gateway/` by digest), `DFBENCH_SNAPSHOTS_DIR` (start forts; default
`scenarios/snapshots`), `GATEWAY_ALLOW_HTTP_UPSTREAM=1` (passed to the real gateway: allow an `http://` `--upstream`,
for tests against a fake upstream only).

Watch mode (`local run`, `local suite` and `local smoke` only; `runner/dfbenchlib/watch.py`): `--watch` builds (or
reuses) `dfbench-watch:<hash>` from the game image (`DFBENCH_GAME_IMAGE`; `docker/Dockerfile.watch`: DF rendered into
Xvfb at 1200x800, `PRINT_MODE:SOFTWARE`, `G_FPS_CAP:20`, windowed, no sound, recorded by ffmpeg at 10 fps), plays
with it, and after each game writes `<game>/video/<game>.mp4` (faststart H.264) and `<game>-4x.mp4`
(`--watch-no-4x` skips it). `--watch-live` adds a view-only, password-protected VNC per game on `127.0.0.1:<port>`
(`--watch-port`, default 5900, one port per game playing at once): the runner listens on the host's loopback and
relays each connection through `docker compose exec game`, so the game container still publishes no port and stays
on the internal network. Refused when `GITHUB_ACTIONS` is set, with `DFBENCH_RESULT_KIND` other than `local`, with
`--stack fake`, and on `suite run` (no such flag). A watch run is labelled: `run.json`, each `game.json` (`watch`:
image, frames, duration) and `score.json` (`watch: true`, `comparable: false`, `watch_note`, and `+watch` after
the key's `dfset` hash; the per-game keys can't tell, since the server derives `dfset` from
`docker/prefs_overrides.py`, which the watch image leaves alone). Without `--watch` nothing changes.

`--task` takes a path or a bare scenario name (`start-year`, `lt01-drought-seed`: tried as `scenarios/<x>.json`,
`scenarios/seed/<x>.json`, then by `name`/`id`). `--harness` is the directory holding the Dockerfile (in the challenge repo, the baseline:
`--harness submission/`).

`local run` on a scenario that a season-0 suite task uses takes that task's settings (anchor, wall cap,
`strange_moods`, budget rule). Budget per game: `--budget`, else the task's `budget_usd`, else
`budget_usd_per_game_year × days / 336` ($0.50 per game-year: LT01 60 d = $0.089).

Output, per run dir:

```text
<out>/suite.json run.json score.json score_detail.json
<out>/<task>-<k>/game.json                 runner record: spec, status ok|infra, finished_by, notes, ledger and
                                           gateway status totals, harness exit code / OOM, wall
              /game/                       the server's §6 artifacts: summary.jsonl, harness-<k>.daily.json,
                                           .credit.json, .final.json, .api.jsonl
              /gateway/usage.jsonl gateway-status.json
              /task/scenario.json game_input.json server_task.json dfbench_task.json
              /harness/output.log          untrusted, bounded; never read by the scorer
              /logs/game.log gateway.log
              /video/<task>-<k>.mp4 -4x.mp4  --watch only (local)
```

### Yukon wrappers (`runner/yukon/`; `.yukon/` in the challenge repo)

`setup.sh` and `run.sh` are the sources of the challenge repo's `.yukon/setup.sh` and `.yukon/run.sh`
(`challenge/benchmark.json` setupCommand / benchmarkCommand). `setup.sh` builds the plain DF image from the competitor's
DF download (`DFBENCH_DF_BASE_IMAGE`, default `yukon-df:s0-base`: the fort builders' image), the game server image on
top of it (`docker/Dockerfile.game`, `DFBENCH_GAME_IMAGE`, default `yukon-df:s0`: what the real stack plays), the
gateway image, the public forts (`docker/task_forts.sh`, `docker/embark.sh`, `pool/dfpool build-public` with
`--allow-busy` when `DFBENCH_ALLOW_BUSY=1`) and checks that `submission/` builds; a MY1 fort that doesn't build is
reported at the end instead of skipping the check. `run.sh` runs `dfbench local suite --harness submission/` (plus
`DFBENCH_SUITE_ARGS`, since `yukon run` passes no arguments) and copies the score to `.yukon/score.json`. A game
server that fails at reset adds a hint to its error when the cause is a missing `df/save` (the plain image used as the
game image) or a start fort missing from the mount (`gameapi/server/__main__.py` `reset_hint`). The challenge workflow is `runner/ci/score.yml` (installed as `.github/workflows/score.yml`).

## Suite file (`dfbench-suite/1`)

```json
{"schema": "dfbench-suite/1", "name": "season0", "seed": 12345,
 "rules": {"actions_per_game_day": 40, "max_advance_days": 28},
 "budget_usd_per_game_year": 0.50, "wall_s_per_game_year": 5400,
 "weights": {"OP1": 0.4, "MY1": 0.3, "labs": 0.3},
 "bootstrap": {"resamples": 10000, "seed": 20261023, "alpha": 0.05},
 "lab_z": {"cap": 1.5, "floor": null},
 "infra": {"max_upstream_error_share": 0.10, "max_throttle_share": 0.5},
 "tasks": [{"id": "LT03", "kind": "lab", "family": "labs", "predicate": "LT03",
            "scenario": "scenarios/seed/lt03-mood-artifact.json", "n": 8, "stage": 1, "wall_s": 1800,
            "strange_moods": true, "anchor": {"noop": 0.0, "witness": 1.0}},
           {"id": "OP1", "kind": "outcome", "family": "OP1", "scenario": "scenarios/start-year.json", "days": 336,
            "n": 8, "stage": 2, "wall_s": 5400}]}
```

Task fields: `kind` `lab` (scored by `bench/predicates.py` `predicate`) or `outcome` (`bench/outcomes.py`);
`family` (the weight key; lab tasks share `labs`); `days` (overrides the scenario's); `wall_s`; `budget_usd`;
`strange_moods` (merged into the task JSON the server gets); `anchor` (lab normalisation). Game ids are
`<task id>-<k>`, k = 0..n-1; every game gets `seed` and `k` (common random numbers across submissions).
`season0.json` is the official suite (48 games: LT01/LT02/LT03/LT08/MY1 ×8 in stage 1, OP1 ×8 in stage 2);
`season0-public.json` is the same with fewer games for `local suite`.

## score.json

```json
{"score": 41.2,
 "metrics": {"stage": 2, "promotable": true, "point": 55.0, "lb95": 41.2, "ub95": 66.3,
  "LT01": "pass 6/8, partial 0.91, z 0.91", "LT02": "...", "LT03": "...", "LT08": "...",
  "MY1": "O 71.3 (n 8; tiers 0-4 0,1,2,4,1)", "OP1": "O 58.0 (n 8; tiers 0-4 ...)",
  "family_labs": 80.1, "family_MY1": 71.3, "family_OP1": 58.0,
  "credits_per_game_year": 0.21, "calls_per_game_year": 410.0, "wall_h_per_game_year": 0.9,
  "wall_capped": 0, "actions_per_game_year": 900.0, "actions_rejected_per_game_year": 12.0,
  "throttle_wait_s": 30.5, "credits_exhausted": 1,
  "subscores": "survival 0.95 supply 0.71 wellbeing 0.80 growth 0.40", "tiers": "0,1,3,6,6",
  "games": "56 scored / 56 run", "infra_excluded": 0, "game_years": 19.2, "credits_usd": 4.03,
  "harness_digest": "sha256:...", "key": "dfbench/v3|...", "price_table_hash": "sha256:...",
  "suite": "season0", "score_version": "s0-score/1", "runner": "s0-runner/1", "anchors": "...", "bootstrap": "..."}}
```

- Flat metrics (Yukon shows one PR-table row per top-level key; per-task values are short strings).
- **S** = Σ w_f·F_f / Σ w_f over the families present: F_OP1, F_MY1 = mean O (0–100); F_labs = mean over lab tasks
  of 100·ẑ, ẑ = (p̄ − p̄_noop)/(p̄_anchor − p̄_noop), capped at 1.5, not floored (BENCHMARK-v1 §3.2, SCORING.md §1.2).
- **score** = the one-sided 95% lower bound (5th percentile) of S over a stratified bootstrap: each task's games
  resampled with replacement within the task, 10,000 resamples, fixed seed. `ub95` = the 95th percentile (staging).
- `stage`: 2 = complete; 1 = stage 1 only, published as `score: 0, partial: true` (not promotable, SCORING.md §4);
  `"subset"` = any other incomplete run (local runs), `partial: true`, score = the bound over the families present.
- `stage2` (scoring workflow only): why OP1 was or wasn't played, e.g. `skipped: stage-1 upper bound 94.27 <
  leader's stage-1 point 94.52 …`, `skipped: tier new plays stage 1 only …` or `played (…)`; with
  `leader_stage1_point`. On a stage-1-only result both come first in `metrics`, so they head Yukon's PR table
  (Yukon's headline says "Scored 0" and ignores `partial`; yukon `src/execution/github-actions.ts`
  `scoreReportComment`).
- `lab_z_below_minus1`: the lab games whose own ẑ is below −1 (e.g. `LT08-3 -2.64`), listed while the floor is a
  pending decision; S stays unfloored.
- Infra games (`game.json` status `infra`, or usage unknown on any gateway call) are excluded and counted.
- `score_detail.json` (not for publication): the per-game records (O, tier, sub-scores, partial, clauses, ledger).

Lab anchors used now (PROVISIONAL-v6, outcome score v6, mean partial, n = 6 per arm: `runs/s0-rc-2026-10-23/labs`, the
reference arms on the public seed-built forts 2001/2002/2005): LT01 noop 0.00 / witness 1.00, LT02 0.00 / 0.9383, LT03
0.00 / 1.00, LT08 0.7258 / 0.9482 (PROVISIONAL-v3 under score v5 were LT02 0.30 / 1.00 and LT08 0.6946 / 0.9998). They
must be re-measured on the private pool before the season (SCORING.md: "published at season open").

## Security notes

- **Network:** harness and game only on `game_internal` (`internal: true`); the gateway alone on `egress`. Compose can't
  restrict `egress` to the provider host: on the verifier, add a firewall rule (e.g. `DOCKER-USER` allowing only
  openrouter.ai:443 from the egress bridge). No published ports; the runner reaches the game with `compose exec`.
- **Secrets:** the harness image is built first, with secret-looking env vars stripped. The key is read from the
  host env (`--key-env`) and set only in the env of `compose up gateway`, which interpolates it into the gateway's
  `OPENROUTER_API_KEY`; every other compose call runs without it (`clean_env`). It never appears in
  `DFBENCH_TASK`, the game's input or any artifact (tested). It is visible to `docker inspect` of the gateway, so only
  the runner may have Docker access: the harness gets no Docker socket and no host mounts. `GATEWAY_DEBUG` is never set.
- **Harness limits:** 1 vCPU, 2 GB, no swap, 1024 pids, all capabilities dropped, no-new-privileges, bounded logs.
  Its stdout/stderr is kept (≤ 5 MiB) for the competitor and never read by the scorer.
- **Trusted scoring:** `dfbench score` reads only `<game>/game/` (server artifacts), `<game>/gateway/` (ledger and
  status) and the runner's `game.json`. Harness output can't change a score (tested).

## Tests

Every suite in the repo, each run its intended way: `scripts/run_tests.sh` (a few suites, e.g. `gateway/tests`,
`baseline/tests` and `gameapi/facts/tests`, import their own directory's modules by name and must run with that
directory as the top, not `-t .`; the script knows which).

```sh
python3 -m unittest discover -s runner/tests -t .                          # fake rules, scoring, compose isolation
DFBENCH_E2E=1 python3 -m unittest runner.tests.test_runner.E2E -v         # 4 fake games through compose (~1.5 min)
```

For quick manual runs add `--retries 0` (no infra re-run) and `--poll 1`; `--stack mixed` checks the real
server (DF image) without a model.

E2E: (1) LT01 through compose with the example harness: score.json, artifacts, ledger, throttle accounting, the key
injected into the gateway only, no containers left; (2) OP1 with a $0.05 budget: the gateway blocks, the runner calls
`/finish`, the server runs on to the horizon, scored; (3) a fail-closed `usage_missing` call: the game is infra,
re-run once (the first attempt kept in `attempt-0/`) and excluded; (4) the plain baseline (`baseline/plain/`, staged as `submission/` is) plays LT01 on the fake stack.

## Interfaces and fakes

- **Game server (`gameapi/server`)**: started by `compose.real.yml` as `python3 -m gameapi.server --port 8090`
  in `/root/dfprobe` of the DF image; reads `DFBENCH_GAME` (JSON: `run_id, arm="harness", k, seed, scenario,
  scenario_path=/dfbench/scenario.json, days, strange_moods, artifacts_dir=/artifacts, ledger_path,
  gateway_status_path, gateway_url, harness_digest, budget, rules{actions_per_game_day, max_advance_days, wall_s}`);
  writes the §6 artifacts as `harness-<k>.*` in `artifacts_dir`; `GET /health` returns `finished` (artifacts
  written) and `finished_by`; `POST /finish {"reason"}` runs the rest of the horizon unmanaged (may return before it
  is done; the runner polls `/health`). Python 3 in the image (for `compose exec`). Start forts mounted read-only at
  `/root/dfprobe/scenarios/snapshots`.
- **DFBENCH_TASK** (contract §2.1, §3.1), built by the runner from the server's `GET /task`: `schema, run_id, api,
  game_url, model{base_url, name, api, api_key: "placeholder", prices{input, cached_input, output, unit: "USD per
  million tokens", price_table_hash}}, budget, limits` (from `/task` `rules`, else the suite) and `task` (from `/task`).
  Prices are per million tokens (as `gateway/prices.json` and `baseline/dfbench_client` read them).
- **Fakes:** `fakes/fake_game.py` (contract §3/§4 with a toy fort; writes artifacts the real scorers accept),
  `fakes/fake_gateway.py` (gateway/'s env, `/status`, ledger and status file, canned tool calls),
  `fakes/example_harness/` (reads DFBENCH_TASK, observes, calls the model, acts, advances).
- **CI** (`ci/score.yml`): a template; private pool staging, the leader's stage-1 point and artifact visibility need
  Yukon answers (see the file's header).
- **Not built:** the 3-year close task, and a ticks/s floor per game (the server should report it).
- **Start forts:** `local run`, `local suite` and `suite run` check before starting any container that every start
  fort the selected games need is on disk (under `DFBENCH_SNAPSHOTS_DIR`, default `scenarios/snapshots/`), and stop
  with the list of missing ones (`--stack fake` needs none). Public forts: `.yukon/setup.sh` (labs via
  `docker/task_forts.sh`, MY1 via `pool/dfpool build-public --task MY1`, OP1 via `docker/embark.sh --rules
  DEFAULT_FORT`). `local suite --games` loads only the selected tasks' files.
