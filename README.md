# Yukon Arena: Fortress, season 0

A harness challenge played in the game Dwarf Fortress, on Yukon (`https://www.yukon.org/arena-fortress`).

> **Versioning.** The rules that apply to your submission are the ones in this repository at the commit your
> submission is based on (the `main` you cloned or synced). Changes during the season are announced and dated.

> **Season 0 dates:** opens **Friday 6 November 2026** and closes **Monday 23 November 2026, 23:59:59 UTC** (about 2.5 weeks). Submissions after the close aren't accepted.

> **Attribution is the point of this challenge, and it is required.** Season 0 is collaborative, with no cash prizes or
> rewards of any kind (you compete for rank and credit):
> every submission is open to all participants, the leading harness becomes everyone's starting point, and you're
> encouraged to build on anyone's work. What we want to learn is *which ideas move the score and where they came
> from*, so every submission must say what it builds on (prior submissions, people, published ideas) and what it
> adds. A submission that doesn't credit what it uses isn't ranked. See `RULES.md` §8 and `SUBMITTING.md` §3.

> **Start here.** You edit one directory, `submission/` (your harness); everything else is the fixed challenge
> (the game server, the model gateway, the runner and the scorers). The `.lua`, `.py` and `.sh` files at the repo root
> are the game server's internals: you never need to touch them.
>
> 1. `yukon clone OWNER/arena-fortress-s0/harness-glm-5-3-flash`, then `yukon setup` (builds the game
>    image and the practice forts from your own Dwarf Fortress download; `SUBMITTING.md` §2).
> 2. `runner/dfbench local smoke`: a free check that your harness runs against the real game (fake model, no key).
> 3. Improve `submission/`, test with `yukon run` (your own OpenRouter key), and read the contenders for ideas
>    (`SUBMITTING.md` §3a).
> 4. Write `NOTE.md` and `dependencies.json`, then `yukon submit` (`SUBMITTING.md` §3).
>
> **Credit the leader you start from.** Once someone has been promoted, `submission/` on `main` (what `yukon clone`
> and `yukon sync` give you) is the leader's harness. If you build on it, list that submission in
> `dependencies.json` and say so in `NOTE.md`; the judge holds a submission that keeps the leader's code without
> crediting it (`RULES.md` §8). A harness you write from scratch owes the leader nothing.

> **Limits at a glance** (full rules: `RULES.md` §2 and §7)
>
> - **Who can enter:** anyone with a Yukon account (sign in with GitHub), subject to the [Terms](TERMS.md). There is
>   no allowlist, invitation or application.
> - **Per account, by tier.** Your tier is set automatically at each submission; there's nothing to apply for.
>
>   | tier | who | submissions per week | suite |
>   |---|---|---|---|
>   | **established** | a promoted result on another Yukon challenge, or a scored submission here already | 7 | full |
>   | **new** | everyone else | 2 | your **first** scored submission here plays **stage 1 only**, then full |
>   | **probation** | a GitHub account younger than 30 days | 1 | stage 1 only |
>
>   Stage 1 is the four lab tasks and MY1. A stage-1-only result is shown but **can't be promoted**, so a new
>   account's first submission can't top the board. Once a submission of yours has been scored here, you are
>   established: 7 a week and the full suite from your next submission. **Probation lasts the full 30 days**, even
>   after a scored submission (new GitHub account? Ask the organisers (a known person can be moved to established)).
> - **One submission in flight** per account. Yukon's own limits apply too: 1 in flight and 10 submissions an hour.
> - **A global weekly allowance** covers everyone (the organiser pays for the model and the runners). When it's used
>   up, new submissions wait until the next week; the refusal says when. Weeks start Monday 00:00 UTC, so season 0
>   has a short first week (6-8 Nov), two full weeks (9-15 and 16-22 Nov) and its last day (23 Nov), each with
>   its own weekly limits.
> - **What counts against your week:** a submission that is scored, one the judge fails or holds, and one whose
>   image doesn't build. **What doesn't:** a submission refused at admission (over a limit, an unchanged harness),
>   one you cancel, and infra failures on our side.
> - **Per game:** $0.50 of model credits and 90 minutes of wall time per game-year, 40 actions per game-day, a
>   1 vCPU / 2 GB harness container with no network except the game API and the model gateway.

You write the **harness**: the program that runs a Dwarf Fortress fortress for a year by calling **one fixed, cheap,
hosted language model** and a **fixed game API**. Everything inside the harness is yours: prompts, memory and
context policy, planning loop, how often it acts or advances time, sub-calls, sampling parameters, knowledge files,
local tools and caches. The model, the game API, the tasks, the budget and the scoring are fixed. The question the
challenge measures: **how much can a harness get out of one fixed model?**

Why it's interesting: in our early experiments, a better harness around the same fixed model gained about 15 outcome
points over a frozen harness on the full-year task, reaching the level of DFHack's built-in automation. The baseline
you start from has none of that. There is room above both.

- [`RULES.md`](RULES.md): limits, what a submission may contain, network, fair play, publication.
- [`SCORING.md`](SCORING.md): the outcome score, lab predicates, suite weights, the lower bound, staging.
- [`SUBMITTING.md`](SUBMITTING.md): the harness contract, local runs, the submission flow.
- [`ROADMAP.md`](ROADMAP.md): what later seasons may add (non-binding).
- [`docs/GAME-API.md`](docs/GAME-API.md): the game API contract (tools, observation, queries, rules, artifacts).
- [`docs/SUCCESS.md`](docs/SUCCESS.md): the outcome score in full, with the DF mechanics behind each tier.

"dfbench" is the name of the challenge's tooling: the `runner/dfbench` CLI, the `dfbench/v3` comparability key, the
`DFBENCH_*` environment variables and the `dfbench-*` images and artifacts keep that name.

## Scope (season 0)

Season 0's scope is stated here in full so that nobody has to guess. Only the season's seeds, forts and our
reference solutions are private. Anything not listed as in scope is out.

### The game

- **Dwarf Fortress 53.16 with DFHack 53.16-r2**, headless on x86_64 Linux, **fortress mode only** (no adventure
  mode, no legends, no world generation choices).
- Your harness never touches DF or DFHack directly. It plays only through the game API (below), which the game
  server enforces.

### The fixed model

- **`z-ai/glm-5.3-flash`**, provider pinned to Together, OpenAI-compatible chat completions with tool calling.
- Reached only through the trusted gateway at `http://gateway:8080/v1`. The gateway accepts only this model,
  meters every call at pinned reference prices, and charges it against the game's credits. The organiser pays for
  official games; you use your own key for local runs.
- No caps on decisions, tokens per call, context length or output length. You choose reasoning effort,
  `max_tokens`, temperature and how much context to send. Credits and wall time bound all of it (`RULES.md`).

### The game API (v0)

The contract is [`docs/GAME-API.md`](docs/GAME-API.md). In short:

- `GET /task`, `GET /observe`, `POST /act`, `GET /query/<name>`, `GET /events`, `GET /health` on
  `http://game:8090`.
- **The observation and queries are facts only.** Nothing in the API judges, ranks, summarises or advises: no
  "stuck because" diagnoses, no hints in tool results, no ranked site suggestions. Interpreting the fort is the
  harness's job. The baseline sends the raw facts to the model and leaves interpretation to you.
- **Read-only queries:** `stocks`, `units`, `jobs`, `orders`, `buildings`, `zones`, `map` (revealed tiles only),
  `manager_order_types`, `workshop_types`. They never move time and never count as actions.
- **Tools:** the 20 tools of the frozen `dfbench/v2.1.1` tool set (`appoint_manager`, `build_workshop`,
  `build_farm`, `add_order`, `cancel_order`, `enable_automation`, `create_squad`, `equip_squad`, `squad_order`,
  `create_burrow`, `civilian_alert`, `build_door`, `build_wall`, `lock_door`, `dig_room`, `dig_stairs`,
  `place_furniture`, `make_zone`, `assign_zone`, `advance_days`), plus for season 0:
  - `build_workshop` for **every workshop type** DF allows on the site;
  - **`add_manager_order`** for **any manager order DF accepts** (by job type, reaction, material and subtype), next
    to the frozen `add_order` with its named recipes;
  - **`slaughter`**: mark a tame animal for slaughter (butchering then happens at a Butcher's shop).
- **Hidden information:** the observation and queries show only what a player could see (revealed tiles, known
  units, DF's own announcements).

### Mechanics: in and out

| in season 0 | out of season 0 |
|---|---|
| digging rooms and stairs on the provided sites; workshops of every type; farms; manager orders of every kind DF accepts; zones and furniture; the manager and his office; DFHack automation plugins through `enable_automation` | **trade** (caravans may arrive; there is no trade tool) |
| slaughter of tame animals | **strange-mood tools** (claiming, item fetching, workshop choice beyond what DF does by itself) |
| squads, equipment, burrows, civilian alerts, doors, walls and locked doors (defensive play) | arbitrary designations (free-form digging, mining for ore, channels, constructions beyond walls and doors) |
| read-only queries and the event stream | anything outside fortress mode; direct DFHack, Lua or console access |
| migrants, births, deaths, stress, needs, weather and seasons as DF runs them | sieges as a scored task family (raids can still happen; see known limits) |

- **Strange moods are off** (`[ARTIFACTS:NO]`) in every task **except the mood task** (LT03), where one is
  triggered at the start. Moods are DF's own; season 0 adds no mood-specific tools.

### Tasks and horizons

Every task starts from a fort built from a **world seed** by committed scripts (no DF save is distributed).
Public seeds are in the task files so you can build the same kind of fort locally; official games use private
seeds of the same site class.

| task | family | start | horizon | what it's about |
|---|---|---|---|---|
| **LT01** drought | supply | a worked year-1 fort | 60 d (hands off from day 39) | keep drink flowing through a 21-day window you can't act in |
| **LT02** rescue | supply, wellbeing | a neglected, stressed fort | 90 d (hands off from day 69) | bring drink and food back and hold them |
| **LT03** mood | wellbeing | a fort with a dwarf in a strange mood | 45 d (hands off from day 38) | the artifact made, the dwarf sane and alive |
| **LT08** migrant surge | supply, growth | a fort hit by a migrant wave | 60 d | beds, dining and supply for many more dwarves |
| **MY1** mid-year | management | a day-~120 fort whose previous overseer's orders and automation were switched off | ~216 d, to year end | re-establish management and hold the fort to year end |
| **OP1** full year | everything | a fresh 7-dwarf embark | 336 d (one DF year) | the primary long-horizon task |

- **One year max.** No season-0 game runs longer than 336 game-days.
- Lab tasks (LT01–LT08) have hands-off windows: actions are rejected from day A on, and the window is scored.

### Site class

- **Temperate, soil-heavy embarks** (`embark/rules/TEMPERATE_SOIL.json`): temperate forest, grassland, savanna or
  shrubland with a river or brook, at least 3 soil layers, trees, no near-surface aquifer, no salt water, not
  savage or evil. OP1 uses the default start fort's rules (`embark/rules/DEFAULT_FORT.json`).
- **Stone is not always reachable** with the season-0 tools on these sites. Plan for wood, soil and what the
  wagon brings.

### Limits (summary; `RULES.md` has the full list)

- **Model credits:** $0.50 per game-year at the pinned reference prices, pro rata by horizon. When they run out
  the gateway refuses calls and the fort runs on unmanaged to the horizon.
- **Wall cap:** 90 min per game-year on the reference runner, scored at the tick reached. Provider throttling is
  not counted against you.
- **K = 40 actions per game-day** between advances; `advance_days` moves 1–28 days at a time and can stop early
  on tripwires.
- **Harness container:** 1 vCPU, 2 GB RAM, no network except the gateway and the game API.

### Known limits (season 0)

- **Some strange moods can't be won** on these sites: a mood that demands stone may find none reachable. Bone moods
  need butchering (now possible through `slaughter`), and every mood workshop can now be built. Moods are off
  outside LT03, and LT03 uses moods that can be won on its fort (`SCORING.md` §1.2).
- **DF is nondeterministic** run to run: the same harness on the same fort gives different games. Scores are pooled
  over many games and reported as a lower confidence bound (`SCORING.md`).
- **Same seed, different host:** a seed can give a different embark on Apple Silicon (Rosetta) than on native
  x86_64. Local forts from the public seeds are representative, not identical to the verifier's. Official games
  run on native x86_64.
- **Raids** can happen on any task (DF's own invasions); there is no scored siege task in season 0.
- **Provider-side nondeterminism** of the hosted model: the same prompt can get different answers.
- The game is paused while your harness thinks, so model latency adds directly to wall time.

### What's private

- The season's **private seeds and forts** (the official task pool). A salted commitment to the pool is published
  (`pool/seasons/s0/COMMITMENT.json`); the seeds and the salt are revealed at close.
- The organiser's **reference witnesses** (scripted solutions for the lab tasks). Their scores are published.
- The organiser's **reference harness** (status_v3: the frozen prompt plus a deterministic layer that interprets the
  observation, diagnoses stuck orders, remembers failures and says what to fix first). Whether and when its code is
  released is decided during the season. Once released, anything built from it credits it like any other source.
- Everything else that decides your score is in this repo: the game API and its server, the gateway, the runner,
  the scorers, the task definitions and the public seeds.

## How to take part

Season 0 is an **open, public** challenge on Yukon: anyone with a Yukon account can take part, alone or with
collaborators (credited with `--coauthors`; there are no formal teams). There is no allowlist or application.
Submission limits are per account and depend on your Yukon track record (`RULES.md` §7, and *Limits at a glance*
above). Every improving submission is checked by an automated judge before it's
promoted (`RULES.md` §8a). No cash prizes or rewards of any kind: you compete for rank and credit. `SUBMITTING.md` has the flow.

## The dev loop

1. **Build the DF image** from your own download of DF 53.16 and DFHack 53.16-r2 (`docker/README.md`). Don't push
   that image to a public registry: it contains the game.
2. **Build public forts** from the public seeds: `docker/task_forts.sh --seeds 2001,2002,2005` for the lab tasks,
   `docker/embark.sh --rules DEFAULT_FORT --seeds 12345` for OP1 (`docs/SEED-FORTS.md`). `.yukon/setup.sh` (what
   `yukon setup` runs) does steps 1 and 2 for you.
3. **Start from the baseline:** `submission/` begins as a copy of the plain baseline (`baseline/plain/`): the model
   reads the raw observation and calls one tool per turn, with basic guards (time keeps moving, no order churn, stop
   near the end of the credits) and nothing that interprets the fort. A minimal API demo is there too (not a starting point).
   `submission/README.md` lists the obvious directions.
4. **Run a game locally** with your own model key: `runner/dfbench local run` starts the same three-container
   stack the verifier uses (harness, gateway, game) and scores the game the same way (`SUBMITTING.md`). Use the
   short lab tasks (45–90 days, minutes each) for iteration and OP1 for the real test. One game-year costs cents in
   inference.
5. **Look at why a fort failed:** the run's artifacts (daily samples, events, every API call, the gateway ledger)
   and the per-tier sub-scores in `score.json`.
6. **Submit** when a change holds up over several games, not one: DF's variance is large.

## Repository layout

| path | what |
|---|---|
| `submission/` | your harness (the only path a submission may change) |
| `baseline/` | the plain baseline (`plain/`, copied to `submission/`), a minimal example harness, a small Python API client |
| `gameapi/` | the game server: HTTP API, rules, facts-only observation and queries, artifacts |
| `gateway/` | the model gateway: allowlist, provider pin, pinned prices, credits, ledger |
| `runner/` | the per-game Compose stack, the `dfbench` CLI, trusted scoring |
| `bench/outcomes.py`, `bench/predicates.py` | the scorers |
| `scenarios/` | task definitions with public seeds; `scenarios/lua/` holds their setup scripts |
| `embark/` | world generation, embark rules and fort recipes (seed → fort) |
| `docker/` | the DF image recipe |
| root `*.py`, `*.lua` | the frozen game layer the server wraps (tool implementations, probes, recorder) |
| `framework/` | the reusable harness-arena package the runner and scorer are built on |
| `pool/` | the season pools' public commitments and the fort-pool tooling (`dfpool`) |
| `automation/` | the DFHack automation reference (MY1's mid-year forts are played to day 120 with it) |
| `.yukon/` | what `yukon setup` and `yukon run` call |
| `df/` | the DF settings the game image applies |
| `docs/` | the API contract, the outcome score, seed-built forts |

## Licence

Code: Apache-2.0 (`LICENSE`). Docs: CC-BY-4.0 (`LICENSES/CC-BY-4.0.txt`). Task definitions and other data: CC0-1.0
(`LICENSES/CC0-1.0.txt`). `NOTICE` says which applies to which path. Dwarf Fortress and DFHack are not included and
not ours to license.

## Terms and privacy

Taking part means agreeing to the challenge's [Terms of Service](TERMS.md) and [Privacy Policy](PRIVACY.md)
(Eigen Labs, Inc.; standalone documents for Yukon Arena: Fortress, also on the challenge page).
