# gameapi/server in game (2026-10-23)

`gameapi/server/check_in_game.sh runs/s0server-check`, image `yukon-df:s0server-game` (docker/Dockerfile.game on
docker/Dockerfile from branch s0-server), Docker Desktop on Apple Silicon (Rosetta), one container, `--memory 2500m`,
facts layer `gameapi.facts` (merged cab298db3). Outputs: `runs/s0server-check/` (`check.log` has every request and
response; `start-year/`, `lt01/` the server's artifacts; `ref/` the frozen loop's).

## 1. start-year, 10 days, driven with curl

| step | result |
|---|---|
| start-up (prefs `[ARTIFACTS:NO]`, reset_fort.sh, recorder, credit) | `/task` answered after 12 s |
| `GET /task` | 21 tools (the facts layer's 20 incl. `slaughter`, plus the server's `advance_days`), rules K 40 / 28 days / 5400 s, the v3 key |
| `GET /observe` | schema 6, `map.sites` with ids |
| `GET /query/stocks`, `/query/workshop_types`, `/query/units?limit=3` | facts results; `/query/nope` → 404 `unknown_query` |
| `GET /events?since_tick=0` | DF's reports with ids and ticks (`dropped: 0`) |
| `appoint_manager`, `enable_automation autochop`, `add_order brew_drink 2` | ok, `actions_left_today` 39, 38, 37 |
| `cancel_order 999999`, `dig_room R999`, `slaughter 1` | `no_such_order`, `unknown_site`, `no_such_unit`; each counts (36, 35, 34) |
| unknown tool | `unknown_tool`, doesn't count (34) |
| `advance_days 29` | `bad_arguments` (`args.days must be <= 28`), no time passed |
| `advance_days 2, stop_on []`; `advance_days 1, stop_on [hostile_visible, announcement:STRANGE_MOOD]` | 2400 and 1200 ticks, `stopped: null`; the day counter reset to 40 |
| 40 × `cancel_order`, then a 41st | the 41st → `action_limit`, `actions_left_today` 0 |
| `advance_days 3`, then an action | 3600 ticks; the action is accepted again (39 left) |
| `POST /finish {"reason": "harness_exited"}` | `accepted`, phase `running_out`; ~4 s later `finalized`, end_reason `horizon`, day 10 |

Then `smoke.py --only noop --runs 1 --days 10 --scenario scenarios/start-year.json` in the same container: the
frozen loop's row and files for the same task and horizon.

**Field comparison (server vs frozen loop):**
- `summary.jsonl`: every field of the frozen row is present, with the same types. Added: `api`, `key`,
  `harness_digest`, `run_id`, `wall_capped`, `actions_used` (47), `actions_rejected` (47), `action_limit_rejections`,
  `end_reason`, `finish_reason`, `wall_used_s`, `throttle_s`, `unmanaged_s`, `advances`, `runout_advances`,
  `tripwires_ignored`, `observes`, `queries`, `strange_moods`, `rules`, `facts`. `cap_hit_day` = 6 (the day of `/finish`).
- `.daily.json`, `.credit.json`, `.final.json`: the same top-level keys; 11 daily samples each, same sample keys.
- Same values where the play is the same: days_played 10.0, pop 7 → 7, food_min 101, drink_min 60, days_sampled 11,
  credited 0, deaths 0.

**Scores, unchanged scorers:** `bench/outcomes.py`: server 74.3 (tier 3/4; survival 1.00, supply 1.00, wellbeing
0.97, growth 0.00) = frozen noop 74.3.

## 2. lt01-drought (hands-off from day 39)

| step | result |
|---|---|
| `add_order brew_drink 5, repeat daily, when drink below 100` | ok, order 60 |
| `advance_days 28` | day 28, `hands_off_in_days` 11 |
| `advance_days 28` | cut at A: 11 days, `hands_off: true`; the server ran W (21 days, 7 at a time) and ended at day 60, `end_reason: horizon` |
| an action after it | `game_over` |

`bench/predicates.py LT01`: **pass 1/1**, clauses [1, 1, 1, 1], partial 1.00 (drink_H 58, 19 citizens, 35 drinks
brewed in W, no deaths). `bench/outcomes.py`: 68.4 (tier 3/4).

## 3. Through the runner (`runner/dfbench local run`, real stack)

- `--task scenarios/lt01-drought.json --harness baseline/` with the legacy adapter (an earlier build):
  `DFBENCH_GAME` read (k, seed, rules, artifacts dir `/artifacts`, scenario copy), `/health` and `/task` answered,
  the starter harness observed and advanced; with no model reachable (the gateway refused an http upstream) it
  exited at day 4, the runner sent `POST /finish {"reason": "harness_exit"}`, the server ran the fort to day 60,
  `finished_by: harness_exit`, and `dfbench score` scored the artifacts (LT01 fail: nothing brewed; credits 0).
  Artifacts: `runs/s0server-e2e/LT01-0/`.
- `--task scenarios/start-year.json --harness baseline/` with the facts adapter (this build), the upstream pointed at
  an unreachable https address (no model calls): the starter harness observed, and on each model error the
  gateway's retries took ~5 min (counted as throttling: the server's `throttle_s` reached 1488 s, and the excluded
  time stayed capped at the elapsed wall time, `wall_used_s` ~120 s at day 4). The harness advanced one day per
  error and exited after 5 at day 5; the runner sent `/finish`, the server ran the fort to day 336 and reported
  `finished` (`finished_by: harness_exit`) after 2090 s in all. The runner then classed the game as infra (every
  model call an upstream error, as designed) and started a retry, which I stopped; its rmtree removed attempt 0's
  artifacts.
- What the runner needs for a model-free e2e: pass `GATEWAY_ALLOW_HTTP_UPSTREAM=1` through compose (the gateway
  refuses an http upstream such as `runner/fakes/fake_gateway.py` on the host), or a `--stack` mixing the real game
  with the fake gateway; and `--retries 0` for tests.

## Not tested in game

- The wall cap (unit-tested with a fake clock: between calls and inside an advance, where the watchdog pauses DF).
- A tripwire stop (none fired in 10 days of start-year; `stop_on` filtering is unit-tested).
- A lost fort; `--finish-on-blocked`; gateway status-file polling (unit-tested).
- Strange-mood tasks with `strange_moods: true` (no scenario sets it yet).
