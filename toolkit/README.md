# Yukon Arena: Fortress toolkit (`dfbench-toolkit`)

Analysis tools for your **local** runs of Yukon Arena: Fortress, a harness challenge played in the game Dwarf
Fortress. "dfbench" is the name of the challenge's tooling, so the package is `dfbench-toolkit` and the command
`dfbench-tk`. It reads the directories `runner/dfbench local run` and `local suite` write, and answers three questions:

- **What happened in my games?** `dfbench-tk inspect`
- **Is my change real, or DF's noise?** `dfbench-tk compare`
- **Can I iterate on a mid-game state instead of replaying from day 0?** `dfbench-tk snapshot`

It never needs anything private: it works on your own runs of the public forts. It reads only the trusted artifacts
the official scorer reads (the game server's files, the gateway ledger, the runner's `game.json`), never your
harness's own output.

## Install

Python 3.11+, no dependencies.

```sh
pip install -e toolkit/      # from your clone of the challenge repo
dfbench-tk --version
```

Run it from inside your clone of the challenge repo (or set `DFBENCH_CHALLENGE_DIR`). It then scores with the
challenge's own scorer (`runner/dfbenchlib/score.py`, `bench/outcomes.py`), so its numbers are the official
method's. Outside a clone it falls back to a pinned copy of the suite aggregation (`s0-score/1`) and the per-game
records in each run's `score_detail.json`.

## inspect

```sh
dfbench-tk inspect runs/my-suite                       # Markdown to stdout: the suite table, then every game
dfbench-tk inspect runs/my-suite --game MY1-1,OP1       # some games, or whole tasks
dfbench-tk inspect runs/my-suite --html -o report.html  # self-contained HTML with sparklines
dfbench-tk inspect runs/my-suite --summary-only
dfbench-tk inspect runs/my-suite --json                 # everything, for your own analysis
```

Real output (the plain baseline on the public forts, one MY1 game):

```
**S = 65.69**, one-sided 95% lower bound **58.42** (upper 71.43). Families: labs 88.4, MY1 74.6, OP1 51.2.

| task | n | score | detail | credits/game | wall min/game |
|---|---|---|---|---|---|
| LT08 | 4/4 | 51.9 | pass 0/4, partial 0.84 ± 0.02 | $0.068 | 6.5 |
| MY1 | 4/4 | 74.6 | O 74.6 ± 6.0, tiers 0-4 0,2,0,2,0 | $0.064 | 10.7 |
| OP1 | 4/4 | 51.2 | O 51.2 ± 18.0, tiers 0-4 0,4,0,0,0 | $0.107 | 14.8 |

## MY1-1  (task MY1, k 1, seed 12345)

- outcome **O 68.6**, tier 1/4: survival 1.00, supply 0.73, wellbeing 0.74, growth 0.85
- gates: G1 ✓ G2 ✗ G3 ✓ G4 ✗
- first gate not passed: G2 supply: drink and food in stock every day of the final window, with enough days of stock left
  - G2: drink: in stock 100% of the final days, 157.5 days of stock left, score 0.734; food: ...
  - G4: beds 22 for 20 citizens, dining seats 7 (need 10), progression steps 0.5

**Actions:** 40 calls (1 rejected); 20 advances covering 220 days; actions on 6 days, at most 10 a day (K hit on 0 days); ...
- rejections: bad_arguments 1 (by tool: add_order 1)

**Model:** 39 calls (ok 39); $0.0453 of $0.321; tokens: prompt 483,087 (246,272 cached), ...; latency p50 1.5 s, p90 7.0 s, ...
- credits by phase: days 0-28 $0.027 (60%, 24 calls), days 28-56 $0.002 (5%, 2 calls), ...

| event | n | first day | first text |
|---|---|---|---|
| **MERCHANTS_NEED_DEPOT** | 1 | 48.3 | The merchants need a trade depot to unload their goods. |
```

Per game you get: the timeline (citizens, drink, food, stress, deaths, beds, seats) and notable first days; the
outcome score O, its tier and sub-scores, the gates (`bench/outcomes.py`) and, for the first one that failed, the
numbers behind it; lab predicate clauses; actions by tool, rejections by error code and K usage per day; model
calls, tokens, latency percentiles, throttling (provider vs your own parallel calls), timeouts and credits by
28-day phase; and DF's events and announcements. Gate evidence needs a challenge clone.

## compare

```sh
dfbench-tk compare runs/before runs/after               # B (after) vs A (before)
dfbench-tk compare runs/base runs/try1 runs/try2         # each vs the first
dfbench-tk compare runs/a runs/b --suite runner/suites/season0-public.json
```

Both runs are scored against one suite's anchors and weights: by default the clone's
`runner/suites/season0-public.json` (what local runs are scored against). The difference's 95% CI comes from a
bootstrap: **paired** when the runs played the same forts and seeds (the same task, k and seed: the default when
you use the same `--seed`), independent otherwise.

Real output (the plain baseline before and after its game-strategy advice was removed, 4 games per task):

```
- S point: A 69.99, B 65.69: **difference -4.30**
- 95% lower bound (the published scalar): A 63.01, B 58.42
- 95% CI of the difference, **paired** on 24 same-fort-and-seed games: -11.61 to +4.46 (independent: -15.90 to +6.49)

**Verdict: within noise: the runs can't tell A and B apart.**
About 14 games per task in each run would be needed to resolve a difference this size (now 4).
```

**Why this matters:** DF isn't deterministic. In season 0, two runs of the *same* harness on the same forts differed
by about 3.8 S points (SD of the difference), and playing the same forts and seeds barely reduces that. A single
batch of 4 games per task rarely tells two harnesses apart unless they differ by 10 points or more. Official
promotion needs the lower bound to beat the leader's by 250 bips (2.5%) and then a confirmation batch of MY1 and
OP1. `compare` tells you whether your local evidence is anywhere near that.

Runs recorded with `dfbench local ... --watch` (DF rendered and recorded: `challenge/SUBMITTING.md`, "Watching your
games") are labelled watch mode by `inspect`, and `compare` warns when one run is a watch run and the other isn't:
compare watch runs with nothing but each other, and only to see what changed, not to score it.

## snapshot

```sh
dfbench-tk snapshot --task scenarios/season0/op1-start-year.json --day 120              # DFHack automation plays to day 120
dfbench-tk snapshot --task scenarios/season0/lt08-migrant-surge.json --day 20 --arm noop
dfbench-tk snapshot --task ... --day 120 --dry-run                                     # print the command only
```

It runs the challenge's `docker/batch.sh` (your DF image, `--image`, default `yukon-df`), which plays the task's
public start fort for N days with a built-in arm (`automation`: DFHack's automation; `noop`: nobody) and quicksaves
(`smoke.py --snapshot-days`). The toolkit installs the save under `scenarios/snapshots/` (or `DFBENCH_SNAPSHOTS_DIR`)
and writes `scenarios/local/<name>.json`, a copy of the task that starts there: setup already applied, horizon
shortened by N, a lab's hands-off window shifted. Then:

```sh
runner/dfbench local run --harness submission/ --task scenarios/local/<name>.json --n 1
```

Build the public forts first (`.yukon/setup.sh`). A snapshot task has its own task hash: its scores are for
iteration, not comparable with the official tasks.

## export --commons

```sh
dfbench-tk export runs/my-suite --commons --out-dir my-batch
```

Writes `games.csv` (one row per game: scores, cost, wall time, comparability key, harness digest; no harness
output, no DF saves) and `batch.json`, and prints the `commons publish dataset` command for a
[research-commons](https://github.com/research-common/research-commons) hub. Publishing is yours to run: it signs
with your key and pushes to the hub you choose. Citing a published batch in your submission note is a good way to
show the evidence behind a change.

## Licence

Apache-2.0 (`LICENSE`). Dwarf Fortress and DFHack are not included.
