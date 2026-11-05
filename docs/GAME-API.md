# Game API v0 and the season-0 stack: the contract (draft, 2026-10-23)

This file is the interface every season-0 component builds against. Spec and rationale: `docs/HARNESS-CHALLENGE.md`
(§2.1 limits, §3 architecture, §3.2 the facts/interpretation boundary, §4 suite). Inputs: `docs/game-api-audit.md`
(what the agent sees today), the Phase 0 runs, and the user's decisions of 2026-10-23:
- fixed model **glm-5.3-flash** (Together pinned);
- strange moods **off** (`[ARTIFACTS:NO]`) except in the dedicated mood tasks;
- season 0 adds **read-only queries**, **build_workshop for every workshop type**, **add_order for DF's manager
  orders**, and a **slaughter** action;
- no trade, no new site classes (season 1).

Changes to this file are contract changes: say so in the commit, and update the components.

## 1. Version and key

- Benchmark id **`dfbench/v3`**. The game API replaces the frozen v2.1.1 loop (`smoke.py`, model2): a v3 key is
  never comparable with v2.x rows.
- The v3 key (`bench/key.py`, extended) hashes:
  - the API version;
  - the tool schemas and their semantics (the server's act code and the Lua it runs);
  - the observation and query schemas, and their probe Lua;
  - the **task-relevant DF settings** (`d_init`/`init` tokens the server sets, including `ARTIFACTS`) and the
    DFHack init (`docker/dfhack-onMapLoad.init`);
  - the game-server rules (§4: K, max advance, wall cap);
  - the score version, the task (scenario JSON + start snapshot + setup scripts, as today);
  - the model condition: model id plus the gateway's `price_table_hash` (sha256 of `gateway/prices.json`, which
    also holds the provider pin);
  - and the budget.
- The key does **not** cover the harness: the harness is the submission. Its identity is its source digest,
  recorded with every game.

## 2. Process model (one game)

One Docker Compose project per game (`runner/`):

```text
harness   untrusted submission; net game_internal only; ≤ 1 vCPU, 2 GB (configurable); env DFBENCH_TASK
gateway   trusted (gateway/); nets game_internal + egress to the model provider only; holds the real key
game      trusted (gameapi/ + the DF image); net game_internal only, no egress; DFHack port never published
```

- The harness reaches the game at `http://game:8090` and the model at `http://gateway:8080/v1` (OpenAI-compatible
  chat completions, tools allowed). Nothing else is reachable.
- The runner builds the harness image, starts `game` and waits for `GET /task` to answer. Then it starts `gateway`
  (with the key) and then `harness`.
- The game ends when:
  - the horizon is reached;
  - the fort is lost;
  - the wall cap is hit;
  - or the harness exits.

  "Credits run out" means the gateway's `GET /status` reports a non-null `blocked_reason`: the budget is spent, a
  call returned content without usable usage (fail closed), or the provider hung or lost more than 5 calls in the
  game (`upstream_unreliable`). The runner flags `usage_unknown_calls > 0` and `upstream_unreliable` as infra.
  A single hung or lost call is not a block: the gateway charges an estimate and answers 504 `upstream_timeout`
  (`retryable: true`), and the harness may retry (`gateway/README.md` "Hung and lost calls").
  Only text message content and function tools are forwarded, a lone call over the remaining budget has its
  `max_tokens` clamped to fit, and a hung call that asked for more than 8,192 output tokens is the harness's own
  timeout (not excluded from the wall cap, never an infra re-run) (`gateway/README.md` "Requests", "Budget semantics").
  If the harness exits or the credits run out before the horizon, the server advances the rest of the horizon
  itself with no actions (an unmanaged fort, as the frozen loop does after its cap), so every game is scored at H.
- The runner then collects the game's artifacts (§6) and the gateway ledger, and scores on the trusted side.

The game server starts as `python3 -m gameapi.server --port 8090` and reads its own input from `DFBENCH_GAME` (JSON:
the task file, the start fort (seed-built, mounted read-only under `scenarios/snapshots`), k and seed, the rules,
the artifact dir `/artifacts`). `--seed` in the CLI and `DFBENCH_GAME` means the run index's setup seed, as in
smoke.py (`setup_seeds[0] + k`). A fort is chosen by its task's `snapshot_pool[(seed + k) mod n]`, never by `--seed`
alone.

### 2.1 `DFBENCH_TASK` (JSON, the harness's only input besides the network)

```json
{"schema": "dfbench-task/1", "run_id": "…", "api": "v0",
 "game_url": "http://game:8090",
 "model": {"base_url": "http://gateway:8080/v1", "name": "z-ai/glm-5.3-flash", "api": "openai-chat",
           "api_key": "placeholder"},
 "budget": {"credits": 0.50, "unit": "USD at the pinned reference prices", "per": "game"},
 "limits": {"wall_s": 5400, "actions_per_game_day": 40, "max_advance_days": 28},
 "task": {"name": "start-year", "days": 336, "goal": "…", "brief": "…", "hands_off": null}}
```

## 3. HTTP API (`game`, port 8090, JSON in and out)

Every response carries `{"day", "tick", "days_left", "game_over": bool}`, plus `"hands_off_in_days"` where the task has
a window.

| method, path | what it does |
|---|---|
| `GET /task` | the task (as in `DFBENCH_TASK.task`), the rules (§4), the tool schemas (`tools`, OpenAI function format), the query list, the API version, and `manual`: the reference text describing tools and observation facts. The frozen MANUAL minus its advice; the advice moves to the baseline harness. The text is `gameapi/manual/MANUAL.md`, served verbatim and hashed into the v3 key (2026-10-23) |
| `GET /observe` | the observation: **facts only** (§5), obs schema 8 = #85's schema 5 minus interpretation, plus the mood facts (only what a vanilla player sees; schema 7), plus the score's edible-food count and excavated R rooms (schema 8) |
| `POST /act` `{"tool": name, "args": {...}}` | one action. `{"ok": true, "result": {...}}` or `{"ok": false, "error_code": "...", "error": "..."}`. Also `actions_left_today`. `advance_days` returns when the days have run, or earlier at a tripwire (its result says which) or at the wall cap |
| `GET /query/<name>?…` | read-only queries (§5.2). Never move time, never count as actions |
| `GET /events?since_tick=N` | DF's announcements and reports since a tick, with ids and ticks (the report stream the audit found missing) |
| `GET /health` | liveness, for the runner; also `finished` and `finished_by` once the game is over |
| `POST /finish` | runner only in practice (the harness can reach it too, which only ends its own game early): stop accepting actions, advance the rest of the horizon unmanaged, write the artifacts |

Error codes: today's `ERROR_CODES` plus `unknown_tool`, `bad_arguments` (schema), `action_limit` (K reached today:
only `advance_days` is accepted), `hands_off` (the window has begun), `game_over`.

### 3.1 Shapes pinned for v0 (2026-10-23, from the organiser's reference harness's assumptions)

- **`GET /observe`:** `{"day", "tick", "days_left", "game_over", "hands_off_in_days"?, "observation": {...}}`. The
  observation uses observe2.lua's keys and shapes except where §5 changes them.
- **Order conditions:** `when: [{"item_type", "flags": [...], "test", "value"}]`. `recipe` is present when the order
  matches a frozen recipe name, else `job`/`reaction`. Also `created_tick` (so a harness needn't remember it).
- **Moods (obs schema 7, 2026-10-24):** `moods[] = {unit_id, mood, skill, job (StrangeMood*), collected_items, waiting, claimed_building_id?, claimed_workshop?, items_needed? [{demand, quantity, collected, material? / cloth? (Fey only)}]}`, with no `workshop_needed`.
  - `waiting`: the dwarf is idle in its claimed workshop (on its tiles, and the job is not fetching, bringing or working).
  - `items_needed` appears only while it waits, worded as the workshop's clues word it (`rock`, `logs`, `bars`, `cloth`, `bones`, …).
  - `quantity` is null for the primary material (element 0).
  - Fey moods add the bar/glass `material` and the `cloth` kind (silk, plant, yarn).
  - No raw flags, exact materials or availability counts (`gameapi/manual/MOOD-VISIBILITY.md`). The manager's office: `administrators.manager_required_office` (DF's flag) plus the citizen count.
- **Furniture:** `zones[].furniture` counts, plus `furniture_unzoned` counts for placed furniture outside any zone.
- **Sites:** `map.sites: [{"id", "kind", "x", "y", "z", "w", "h", "soil", "free", "designated", "dug"}]`. For R rooms
  (schema 8): `designated` = `dig_room` ordered it; `dug` = every tile of the box is floor.
- **Advance result:** `{"ok": true, "result": {"advanced_ticks", "stopped": null | {"reason", "detail",
  "after_ticks"}}}`.
- **Events:** `GET /events` → `{"events": [{"id", "tick", "type", "text"}]}`.
- **Prices for harnesses:** `DFBENCH_TASK.model.prices` (the gateway's pinned prices, in USD per million tokens: input,
  cached_input, output), so a harness can estimate its own spend. The gateway's `GET /status` (`spent`, `budget`) is reachable at
  `model.base_url` minus `/v1` + `/status`.

### 3.2 Facts-layer details (2026-10-23, from `gameapi/facts/`)

- **`advance_days` belongs to the server.** The facts layer's `act()` returns `error_code: server_tool` for it, and the
  server builds the §3.1 advance result.
- **`add_order` and `add_manager_order` (contract change, 2026-10-24).** A weak model left both keys out of an
  `add_order` that took either `recipe` or `job`, so the tool is split in two:
  - `add_order` is the frozen form exactly: required `recipe` + `amount`; `when` items require `stock` (the frozen
    names) plus `below` or `at_least`.
  - `add_manager_order` takes any DF manager order: required `job` + `amount`, plus `reaction`,
    `material_category`, `material`, `item_subtype`. `when` items require `item_type` (`ANY` with `flags` for a
    flag-only condition) plus `below` or `at_least`.
  - Both results carry `order_id`. bad_arguments errors name the missing or invalid field.
- **New error codes:** `server_tool`, `unknown_query`, `no_such_unit`, `not_slaughterable`.
- **Structured results:** e.g. dig tools return `{designated, steps}`.
- **`created_tick`:** the tick `add_order` made the order, else the first observation that saw it (DF stores no
  creation tick).
- **`workshops[].jobs`:** stays observe2's strings; the detail is in `job_details`.
- **Open:**
  - there's no mood start tick other than the `STRANGE_MOOD` event.

## 4. Rules the server enforces

- **K = 40** actions per game-day between advances. `advance_days` itself doesn't count. After K, only
  `advance_days` is accepted until the day changes.
- **`advance_days`**: 1 to 28 days (`max_advance_days`). It stops early on tripwires; the call's `stop_on` argument
  (optional, default all) chooses which tripwires.
- **Hands-off windows** (lab tasks): actions are rejected from day A. The advance that reaches A stops there, and the server then runs the window itself, as today.
- **Wall cap:** the clock starts at the harness's first `observe`/`act`/`query`/`events` call (not at `/task`). The game is scored at the tick reached and flagged `wall_capped`. The server's own unmanaged run-out after `/finish` doesn't count. Time the gateway reports as
  provider throttling (429 or 5xx waits) or as a hung or lost call (`upstream_timeout`) is excluded. The gateway runs
  at most 4 of a game's calls at once (the rest queue, and queue time counts); 429 waits on a call admitted with more
  than 2 of the game's calls in flight are the harness's (`throttle_wait_harness_s`) and count too.
- **A lost fort ends the game.**
- **Strange moods:** the task JSON field `"strange_moods": true|false` (default false; the mood tasks `scenarios/seed/lt03-*.json` and `scenarios/lt03-{carpenter,bonecarver,mason}.json` set true). The server sets
  `[ARTIFACTS:YES|NO]` before DF starts.

## 5. Facts (observation and queries)

The principle (spec §3.2): **facts only.** Anything that judges, summarises or advises is harness code. Concretely,
relative to today's observation:
- **removed** (moves to the baseline harness):
  - `diagnose()`'s `stuck_because`, `shares_inputs`, cancellation summaries and validation waits;
  - `ERROR_HINTS` and tool-result `note`/`hint`/`reminder`/`warning`/`nearest_free_centre`;
  - `manager_needs_office`, replaced by the fact: citizen count and the manager's office state;
  - `moods.workshop_needed`, replaced by the mood job type (DF's own);
  - the map's ranked site suggestions (heuristics). Raw site facts stay (§5.1).
- **kept or added as facts:**
  - DF's own cancellation reasons;
  - order `when` conditions with item type, flags and value (the "NONE" bug fixed);
  - zone membership of placed furniture (and furniture outside any zone);
  - zone lists with their true length;
  - per-dwarf adult, squad and position facts, labors and skills (as a query);
  - mood facts: job type, claimed workshop, `waiting`, and while waiting the demands as the UI words them (§3.1;
    both observe2.lua mood bugs fixed; audit d11 closed by `gameapi/manual/MOOD-VISIBILITY.md`);
  - pending digging;
  - revealed tiles only (#85's hidden-information rules apply to every fact and query).

### 5.1 Sites

The action API keeps site ids (`A2`, `R3`, `S1`, …), because tools take them. The server owns the site state (today
it lives harness-side, `harness2._assign_sites`). The observation lists every site with its facts (kind, position,
size, soil/stone, free or used), without ranking.

### 5.2 Queries (read-only)

`stocks` (item counts by type, subtype and material; flags such as rotten, forbidden, in a job), `units` (citizens
and animals: professions, labors, skills, needs, stress, positions), `jobs` (the job queue), `orders` (full
conditions), `buildings`, `zones`, `map` (revealed region: tile kinds by level around a point, bounded),
`manager_order_types` (what `add_order` accepts, §5.3), `workshop_types`. Each query has a bounded result size.

### 5.3 Tools in v0

- The 20 frozen tools, same names and arguments, results without advice. Plus:
- **`build_workshop`**: every DF workshop type the game allows on the site (the enum comes from DF, not a fixed list).
- **`add_order`** (frozen: a recipe name such as `brew_drink`, with `when` stock names) and **`add_manager_order`**
  (`{"job": <df.job_type name>, "reaction": <reaction name>, "material_category": [...], "item_subtype": ...}` for any
  manager order DF accepts; its `when` conditions take an item type plus flags, with no lossy stock names). Both are validated by DF
  through DFHack's `workorder`, as today (§3.2).
- **`slaughter`** `{"unit_id": id}`: marks a tame animal for slaughter, as the animal screen's button does.
  Butchering happens at a Butchers workshop.
- `enable_automation` stays: the same plugins as today.

## 6. Artifacts (what the server writes per game, for the trusted scorer)

The same files the frozen loop writes, so `bench/outcomes.py` and `bench/predicates.py` score v3 games unchanged:
`summary.jsonl` (one row, the v2 fields plus `api`, `key`, `harness_digest`, `wall_capped`, `actions_used`,
`actions_rejected`), `<run>.daily.json` (the recorder's samples), `<run>.credit.json`, `<run>.final.json`, and
`<run>.api.jsonl` (every API call with tick, request, response and latency). The gateway writes `usage.jsonl` (one
line per model call, refused ones included, with an `outcome` field: tokens, cost at the pinned prices, latency,
throttling waits) and `gateway-status.json` (its final `/status`). Throttle waits from parallel calls overlap, so the
server caps the time it excludes from the wall cap at the game's wall time.

## 7. Components and owners (season-0 build)

| dir | what | depends on |
|---|---|---|
| `gameapi/server/` | the HTTP server, task lifecycle, rules (§4), artifacts (§6), site state | `gameapi/facts/`; reuses `bench/env.py` / `smoke.run_one` pieces |
| `gameapi/facts/` | facts-only observation, queries, mood facts, new tools (Lua + Python, §5) | #85's probe files |
| `gateway/` | metering proxy: model allowlist, provider pin, pinned prices, per-game credits, ledger, throttle accounting | — |
| `runner/` | compose template, `dfbench` CLI (local run, suite), artifact collection, trusted scoring, `score.json`, CI workflow | all |
| `baseline/` | the plain baseline (`plain/`: frozen prompt, raw observation, basic guards; `submission/` in season 0), a minimal example harness, a small Python client for the API; the organiser's reference harness is withheld until its code is released (`README.md`, "What's private") | §3 |
| `challenge/` | the competitor-facing repo's docs, scope, rules, `benchmark.json`, export config | all |

Each component has tests runnable without DF where possible (fakes), and a short README.
