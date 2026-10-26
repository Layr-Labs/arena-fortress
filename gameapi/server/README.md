# gameapi/server: the season-0 game server

The `game` service of `docs/GAME-API.md` (§2-§4, §6): one DF game per process, an HTTP API on port 8090, the rules
the harness can't bypass, and the artifacts the trusted scorer reads. Stdlib only (it runs inside the DF image).

| file | what |
|---|---|
| `__main__.py` | `python3 -m gameapi.server`: options, the v3 key, start-up, watchdog |
| `http_api.py` | the endpoints (ThreadingHTTPServer; one game lock, since DF is single-threaded) |
| `rules.py` | `Game`: lifecycle, K, advances, hands-off, wall cap, finish, the end; `Watchdog` |
| `backend.py` | the DF side: `ARTIFACTS` token, `reset_fort.sh`, recorder, setup, credit, advance, final reads (smoke.py's functions) |
| `task.py` | scenario loading as smoke.py does (snapshot resolution, `{seed}` setup, snapshot pool) |
| `artifacts.py` | the `summary.jsonl` row: smoke.run_one's fields plus the v3 ones |
| `adapter.py` | **the facts adapter**: the only file that touches the facts layer |
| `legacy_events.lua` | DF's report stream for the legacy adapter's `events()` |
| `fake.py` | a fake DF and a fake facts layer (tests, `--fake`) |
| `check_in_game.sh` | the in-game smoke test (results in `IN_GAME.md`) |

## Running it

In the image (`docker/Dockerfile.game`, built on `docker/Dockerfile`):

```sh
docker buildx build --platform linux/amd64 --build-context dl=$HOME/df-dl --build-context harness=. \
  -f docker/Dockerfile -t yukon-df:53.16 --load docker
docker buildx build --platform linux/amd64 --build-context harness=. --build-arg BASE=yukon-df:53.16 \
  -f docker/Dockerfile.game -t yukon-df:game --load docker
docker run -d --init --name game1 --platform linux/amd64 --security-opt seccomp=unconfined --memory 2500m \
  -p 127.0.0.1:8090:8090 -e GAMEAPI_TASK=scenarios/start-year.json -e GAMEAPI_ADMIN_TOKEN=secret yukon-df:game
until curl -sf localhost:8090/task >/dev/null; do sleep 3; done       # ~30-60 s: reset + setup
docker cp game1:/root/dfprobe/runs/game ./runs/game1                  # after the game: the artifacts
```

`--init` reaps the DF processes `reset_fort.sh` kills. Without Docker (next to a running DF, as smoke.py runs):
`python3 -m gameapi.server --task scenarios/lt01-drought.json --out runs/x`. With no DF at all:
`python3 -m gameapi.server --fake --task scenarios/start-year.json --port 8090` serves the same API on a fake game
(time and a few stocks only), for developing a harness or the runner.

Options (`--help`; each also reads `GAMEAPI_<NAME>`): `--task`, `--days` (default the scenario's), `--k` (run index:
setup seed and snapshot pool member, as smoke.py), `--seed`, `--arm` (artifact stem `<arm>-<k>`, default `harness`),
`--out` (default `runs/game`), `--port`, `--actions-per-day` (K, 40), `--max-advance-days` (28), `--wall-s` (5400;
0 = none), `--run-id`, `--harness-digest`, `--model`, `--price-table-hash` (default sha256 of `gateway/prices.json`),
`--credits`, `--facts auto|legacy|facts`, `--gateway-status-url`, `--finish-on-blocked`, `--exit-when-done`.

The process binds the port at once (`/health` says `phase: starting`), then resets DF and runs the setup; `/task`
answers once the game is `ready`. After the game it keeps serving (the artifacts are written when the game ends)
until SIGTERM, or exits by itself with `--exit-when-done`.

## Endpoints

Every response carries `day` (since the start), `tick` (absolute), `days_left`, `game_over`, and
`hands_off_in_days` on tasks with a window.

| | |
|---|---|
| `GET /task` | the task (name, days, goal, brief, hands_off `{from_day, days}`, strange_moods), `rules`, `tools` (OpenAI function format; the facts layer's plus the server's `advance_days`), `queries`, `manual`, `obs_schema`, `api`, `key`, `model` (name, `prices` in USD per million tokens from gateway/prices.json, `price_table_hash`), `budget`, `limits`. 503 until ready |
| `GET /observe` | `{"observation": {...}}` from the facts layer (legacy: observe2.lua keys, `map.sites` [{id, kind, x, y, z, w, h, soil, free, dug}]) |
| `POST /act` `{"tool", "args"}` | `{"ok": true, "result": ...}` or `{"ok": false, "error_code", "error"}`, plus `actions_left_today` |
| `GET /query/<name>?k=v` | `{"query", "result"}`; numbers in the query string are passed as numbers. Never moves time, never counts |
| `GET /events?since_tick=N` | `{"events": [{id, tick, type, text, ...}]}` |
| `GET /health` | phase (`starting`, `ready`, `running_out`, `over`, `finalized`, `failed`), end and finish reasons, wall used. Never waits for the game lock |

Admin (the runner and the gateway; header `X-Admin-Token: $GAMEAPI_ADMIN_TOKEN`, or from localhost when no token is
set: the harness shares the network, so set a token in compose):

| | |
|---|---|
| `POST /finish` `{"reason": "harness_exited" \| "credits_exhausted" \| "runner"}` | **the harness is gone or out of credits.** Harness calls get `game_over` from now on; the server advances the rest of the horizon with no actions (7 days at a time, tripwires ignored) and writes the artifacts. Returns at once (`accepted`); poll `/health` until `phase` is `finalized`. `?wait=1` blocks until done. A no-op once the game is over |
| `POST /admin/throttle` `{"total_s": x}` or `{"seconds": s}` | provider throttling to exclude from the wall cap: the gateway's running `throttle_wait_total_s`, or an increment |
| `GET /admin/summary` | the summary row once written |

With `--gateway-status-url http://gateway:8080/status` the server polls the gateway itself every 10 s for
`throttle_wait_total_s`, and with `--finish-on-blocked` treats a non-null `blocked_reason` as `/finish
credits_exhausted`. The default is that the runner calls `/finish`.

Error codes added by the server: `unknown_tool`, `bad_arguments` (the tool's JSON schema; undeclared arguments are
rejected), `action_limit`, `hands_off`, `game_over`, `unknown_query`, `not_ready`, plus `bad_request`/`not_found`/
`forbidden` at the HTTP level. Game-level errors come back as HTTP 200 with `ok: false`.

## Rules (contract §4)

- **K actions per game-day** (default 40). Every `/act` other than `advance_days` that passes the limit check
  counts, whether the game accepts it or not (failed and malformed calls too; an unknown tool name doesn't). The
  count is per game-day index (`(tick - start) // 1200`), so an advance a tripwire stops within the same day does
  not reset it. After K, only `advance_days` is accepted until the day changes.
- **`advance_days {days, stop_on?}`**: 1-28 days, clamped to the horizon. It runs frozen `advance.lua` via
  `smoke.advance` (popup dismissal, hang guard). `stop_on` lists tripwire families (`hostile_visible`,
  `hostile_approaching`, `hostile_near_citizens`, `citizen_died`, `invasion`, `water_rising`, `announcement`) or
  single announcements (`announcement:STRANGE_MOOD`); default all, `[]` none. A tripwire not in `stop_on` is
  recorded (`tripwires_ignored`) and the advance continues from there (advance.lua re-baselines, so the same
  event doesn't fire again).
- **Hands-off window** (`hands_off_days` w): no advance runs past day A = days - w. The advance that reaches A
  returns `hands_off: true` after the server has run the window itself (7 days at a time, no actions) and ended
  the game; actions at or after A get `hands_off`.
- **Wall cap**: the clock starts at the harness's first `/observe`, `/act`, `/query` or `/events` (not `/task`,
  which the runner uses for readiness). Excluded: gateway-reported throttling (capped at the elapsed time, since
  parallel calls' waits overlap) and the time the server runs the fort unmanaged. At the cap the watchdog pauses DF
  inside an advance (the call returns with `wall_capped: true`) or ends the game between calls; the game is
  scored at the tick reached, `wall_capped: true`.
- **A lost fort** (no citizens after an advance) ends the game. So does the horizon. DF hanging or dying ends it
  as `crashed` (the row has `crashed` set, as run_one's: an infra re-run).

## Artifacts (contract §6)

In `--out`, with stem `<arm>-<k>` (default `harness-0`): `summary.jsonl` (one row), `<stem>.daily.json`,
`<stem>.credit.json`, `<stem>.final.json`, `<stem>.api.jsonl` (every call except `/health`: time, tick, day,
method, path, request, status, response, latency) and `BATCH.json` (the v3 key, `bench/key.record_batch`).
The row has every field smoke.run_one writes (the frozen loop's model counters are `0`/`None`: the gateway's
ledger has them) plus `api`, `key`, `harness_digest`, `run_id`, `wall_capped`, `actions_used`, `actions_rejected`,
`action_limit_rejections`, `end_reason`, `finish_reason`, `wall_used_s`, `throttle_s`, `unmanaged_s`, `advances`,
`runout_advances`, `tripwires_ignored`, `observes`, `queries`, `strange_moods`, `rules`, `facts`. `cap_hit_day` is
the day `/finish` came. `bench/outcomes.py <out>` and `bench/predicates.py <task> <out>` score it unchanged.

## The facts adapter

`adapter.load()` returns `Facts`, over `gameapi.facts` (one `gameapi.facts.Game(df=DFHack())` per game), when that
package is present; else `Legacy`, the temporary adapter over `harness2.observe()`/`act()` with the interpretation
stripped. `--facts legacy|facts` forces one. Interface the server uses (adapter.py's docstring):

```python
reset()                          # new game (Facts: a new gameapi.facts.Game)
tools() -> [schema]              # served; any advance_days is replaced by the server's
key_tools() -> [schema]          # what the v3 key hashes: static schemas (build_workshop's DF enum: pinned by df version)
queries() -> [{"name", "description", "params"}]
manual() -> str                  # Facts: gameapi/manual/MANUAL.md, verbatim
observe() -> dict                # schema 6; a probe failure -> internal_error
query(name, **params) -> dict    # KeyError -> 404 unknown_query, TypeError -> bad_arguments
act(tool, args) -> {"ok": True, "result": ...} | {"ok": False, "error_code", "error", ...}
events(since_tick) -> {"events": [...], "dropped": n, ...}   # Facts: Game.events_page
OBS_SCHEMA, NAME, STRICT_ARGS    # STRICT_ARGS False: undeclared arguments are left to the facts layer
```

The server validates arguments against the served schemas before calling `act` (types, enums, bounds, required),
owns `advance_days`, K, hands-off and the end of the game; the facts layer owns the site state and everything
DF-side of a tool. `adapter.key_files()` names the files the key hashes (the facts layer's Python minus its in-game
check, `lua/*.lua` and `gameapi/manual/MANUAL.md`, plus adapter.py).

## Runner input (`DFBENCH_GAME`)

runner/ starts the service as `python3 -m gameapi.server --port 8090` with `DFBENCH_GAME` (JSON). The server takes
its defaults from it (command-line options still win): `scenario_path` (the runner's copy: days and strange_moods
applied; else `scenario`), `scenario` (repo-relative; names the key's task hash), `k`, `seed`, `days`,
`strange_moods`, `arm`, `artifacts_dir` (→ `--out`), `run_id`, `harness_digest`, `budget.credits`,
`rules.{actions_per_game_day, max_advance_days, wall_s}`, `gateway_status_path` and `ledger_path` (throttle
exclusion: the status file's `throttle_wait_total_s`, else the ledger's `throttle_wait_s` summed, polled every 10 s).
`seed` is smoke.py's: the setup seed is `setup_seeds[0] + k`, the fort `snapshot_pool[(seed + k) mod n]`. The runner
talks to the server with `compose exec game` (localhost, so the admin endpoints need no token there) and reads
`/health`'s `finished` and `finished_by` (`horizon`, `fort_lost`, `wall_cap`, `crashed`, or the `/finish` reason
when the server ran out the horizon: `harness_exit`, `credits_<why>`, `runner_deadline`). The image's entrypoint
runs a given command as is, so compose's `command:` works.

## The v3 key (bench/key.py `compute_v3`)

```
dfbench/v3|api=v0|tools=<8>|sem=<8>|obs=<obs_schema>:<8>|dfset=noart|art:<8>|rules=K40.A28.W5400:<8>|
score=5:<8>|task=<name>:<8>|df=53.16|dfhack=53.16-r2|model=<model id>:<8>|budget=<8>
```

`tools`: the schemas (`key_tools()` + the server's `advance_days`). `sem` and `obs`: gameapi/facts' Python and
`lua/*.lua` plus adapter.py (one package serves both; with the legacy adapter: harness2.py, harness.py, act2.lua,
place.lua, digplan.lua, wo_lib.lua / observe2.lua, legacy_events.lua); `obs` adds the query list.
`dfset`: the image's init/d_init token edits plus `ARTIFACTS`, and `docker/dfhack-onMapLoad.init`. `rules`: K, max
advance, wall cap, the server's rule and DF-side files, advance.lua/recorder.lua/credit.lua and smoke's advance
functions. `score` and `task` as in v2. `model`: model id + the gateway's `price_table_hash`. `budget`: credits,
unit, per, days. `python3 bench/key.py --v3 --scenario scenarios/x.json --model z-ai/glm-5.3-flash --credits 0.5`
prints it. v2.x keys are unchanged.

## Tests

`python3 -m unittest discover -s gameapi/server/tests -t .` (no DF: K counting, advance bounds and `stop_on`,
hands-off, wall cap inside and between advances, throttle exclusion, finish and run-out, lost fort, artifacts,
the HTTP layer). `python3 -m unittest discover -s bench/tests -t .` covers the key. In game:
`gameapi/server/check_in_game.sh` (see `IN_GAME.md`).

## Known gaps

- `manual()`: the Facts adapter serves `gameapi/manual/MANUAL.md` (the frozen MANUAL minus its advice, for the
  season-0 tools; in the v3 key). The legacy fallback still serves the frozen MANUAL, advice included.
- Strange moods: `strange_moods` defaults to false, so the mood lab tasks (`scenarios/lt03-*.json`) need
  `"strange_moods": true` in their JSON, or they run with `[ARTIFACTS:NO]` (whether `strangemood --force` still
  works then is untested).
- The run-out after `/finish` has no wall cap of its own (a slow fort makes it long).
- `interruptions` (popups dismissed during an advance) are returned in the advance's result, not in `/events`.
- One game per process; a new game needs a new container.
- The wall clock starts at the harness's first call; the runner's own backstop starts when it starts the harness.
- Compose's `game` service has no `init: true`; the server only resets DF once per game, so no zombie builds up,
  but `init: true` would be cleaner.
