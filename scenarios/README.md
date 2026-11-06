# Scenarios

A scenario is one JSON file. Run any arm on it with `smoke.py --scenario scenarios/<name>.json`.
`analyze.py` groups results by scenario and scores each with its own `metrics`.

```json
{
  "name": "start-year",
  "description": "What this tests and why (for humans).",
  "snapshot": "fort_start_snapshot",
  "setup": [["force", "Migrants"]],
  "days": 336,
  "goal": "Run the fortress for {days} days. Scored on credited production (see SCORE), days with drink in stock, and citizen deaths (fewer is better).",
  "brief": "Shown to v2 agents as obs.scenario. Say what's happening, not how to solve it.",
  "metrics": {"citizen_deaths": -1, "credited_value_final": 1, "days_drink_positive": 1},
  "provenance": "How the snapshot was made: source run, arm, day, commit."
}
```

| Field | Meaning |
|---|---|
| `snapshot` | A save folder, relative to the repo root (or absolute). Must contain `world.sav` and a `SNAPSHOT.json` (`abs_tick`, `citizens`) so `reset_fort.sh` can assert that the right state loaded (`smoke.py --snapshot-days` writes it). Omit to use `fort_start_snapshot`; without its save (a public checkout) that resolves to the seed-built `scenarios/snapshots/embark-default-fort-12345` (`embark/make_default_fort.sh`, `docs/SEED-FORTS.md` §6). |
| `snapshot_pool` | Instead of `snapshot`: a list of save folders; run k starts on `pool[(seed + k) mod n]` (LT09/LT10 embark sites). `smoke.py` prints which one. |
| `setup` | `dfhack-run` argument lists, run after loading, after the daily recorder starts (so injected events are counted) and after the starting baselines are taken. A command that exits non-zero fails the run (recorded as crashed). Paths starting with `scenarios/` resolve against the repo root, e.g. `["lua", "-f", "scenarios/lua/flood.lua"]`. |
| `days` | Horizon. `--days` overrides it. |
| `goal` | Plain-language success condition, shown to agents as `obs.goal` (`{days}` becomes the actual horizon). Say what is scored and which way, not the weights or formula, and nothing the agent can't see in game (spawn times, invader ids). |
| `brief` | Optional text for v2 agents. |
| `split` | `train`, or absent (= test-public; BENCHMARK-v1 §5.4). |
| `setup_seeds` | `[lo, hi]`: run k gets setup seed `lo + k`, substituted for `{seed}` in `setup` (refused outside the range). Train: within 0–999. `scenarios/lua/seeded.lua SEED SCRIPT ARGS` runs a script with `math.random` seeded |
| `metrics` | Summary fields to score, each `1` (higher is better) or `-1` (lower is better). Any numeric field in a summary row works; see `smoke.py` `summary` and `daily_metrics`. Default: `analyze.METRICS`. Agents never see it; they get `goal`. For wealth use `credited_value_final`: it credits only production from orders the arm created and workshops it built during the run, so a snapshot's existing orders, workshops and order-creating automation earn the arm nothing (`produced_value_final` counts them; `wealth_crafted_final` counts placed furniture three times). `credit.lua` starts after `setup`, so buildings or orders a setup script creates count as pre-existing. Runs are pooled only when both `name` and `metrics` match. |

## Library status
| Scenario | Status | Separating metrics |
|---|---|---|
| `start-year` | validated (5/arm; 60 d re-checked 2026-10-10) | credited_value, days_drink_positive (year only) |
| `drought-y2` | validated (5/arm; re-checked 2026-10-10) | days_drink_positive |
| `rescue-neglected-y2` | validated (5/arm; re-checked 2026-10-10) | days_drink_positive, credited_value |
| `famine-y2` | failed: retired | none (farms + inherited automation regrow food) |
| `goblin-raid-y2` | validated (5/arm; re-checked 2026-10-10) | citizen_deaths, pop_final |
| `thief-raid-y1` | experimental: the thief is spotted on day 1 and flees with nothing (thefts 0 in 8/8 noop, 2026-10-10b) | none; needs a snapshot where the thief can steal |
| `lt03-mood-artifact` | lab task LT03, validated (n=8, 2026-10-10): noop 0/8, witness 8/8 | `bench/predicates.py LT03` |
| `lt08-migrant-surge` | lab task LT08, built, not admitted: noop 0/8, best witness 2/8 | `bench/predicates.py LT08` (and `LT08-items`) |
| `lt04-stress-relief` | lab task LT04, dropped: no witness passes (`calib/` holds the stress sweep) | `bench/predicates.py LT04` |
| `seed/lt01-drought` (`lt01-drought-seed`) | seed-built LT01 on `worked-y1` forts (2026-10-14, Mac, n=4): see docs/SEED-FORTS.md §3 | `bench/predicates.py LT01` |
| `seed/lt02-rescue-neglected` | seed-built LT02 on `neglected-y1` forts: see docs/SEED-FORTS.md §3 | `bench/predicates.py LT02` |
| `seed/lt03-mood-artifact` | seed-built LT03 on `worked-y1`: see docs/SEED-FORTS.md §3 | `bench/predicates.py LT03` |
| `seed/lt05-goblin-raid` | seed-built LT05 on `worked-y1`, spawn from the map (`invade_edge.lua`): see docs/SEED-FORTS.md §3 | `bench/predicates.py LT05` |
| `seed/lt08-migrant-surge` | seed-built LT08 on `worked-y1`: see docs/SEED-FORTS.md §3 | `bench/predicates.py LT08` |
| `lt09-embark-production` | lab task LT09, draft (split train): 4 generated TEMPERATE_SOIL forts; 90-day reference runs below; no predicate or witness yet | credited_value, drink_final (days_drink_positive does not separate within 90 d) |

**Lab tasks** (`lt*.json`, `docs/BENCHMARK-v1.md` §2) add `id`, `active_days`, `hands_off_days`, `decision_cap`,
`predicate` and `references`. Run them with `docker/batch.sh --entry bench/labrun.py` (the reference arms get the
hands-off window and a `witness` arm) and score them with `bench/predicates.py <task> <dirs>`. A fort that grows past
20 citizens needs an *assigned* manager office before new orders validate, which the tool API can't do. Use
`lua/manager_office.lua` in the setup (LT08 does). Results: `runs/lab-tasks-2026-10-10`.

Each file's `validation` field has the numbers and points to the runs under `runs/scenario-validation-*`; the 2026-10-10 re-check on `main` is `runs/validation-2026-10-10`, and the random / LT05 / theft follow-up is `runs/validation-2026-10-10b`.

**Thefts** are in every summary row: `thefts` (items stolen from the fort during the run: `ITEM_STOLEN` history
events at the fort's site), `theft_items`, `thief_held_items_final` (loot a thief still on the map carries),
`thieves_killed`, `thieves_caged_final`. `<arm>-<k>.final.json` keeps the full `score.lua` output at the start and
the end (`F0`, `F`) for rescoring.

**The random arm is a floor near noop.** It doesn't draw `create_burrow` or `civilian_alert` (since 2026-10-10):
with them it confined civilians to a tiny Shelter burrow and starved forts that noop keeps alive. A scenario should
still separate scripted from random, but random isn't expected to beat noop.

**Snapshots keep DFHack plugin state.** A mid-game snapshot keeps whatever automation was on (autofarm,
seedwatch, autochop...), so `noop` on it means "the fort's existing automation keeps running", not "nothing
happens". Design crises the existing automation can't absorb, or turn the plugins off in `setup`.

## Rules for adding one
1. **Validate it with the reference arms before using it on models:** at least 5 runs each of `noop`, `random`
   and `scripted`. A scenario is only useful if its metrics separate them (`analyze.py` shows CIs and p-values).
   If scripted doesn't beat noop on a metric, that metric drops out of the normalized score.
2. **Keep it short:** 30–90 days where possible. Short scenarios give more samples per hour of compute.
3. **Record provenance:** which run, arm, day and commit produced the snapshot, and what `setup` does.
4. **Snapshots** are DF save folders (~5 MB). Put them in `scenarios/snapshots/<name>/` with their `SNAPSHOT.json`. Generated embark snapshots (`scenarios/snapshots/embark-*`) are not committed; regenerate them from their seeds (below).

## Task forts (seed-built lab-task starts; docs/SEED-FORTS.md)
`scenarios/seed/*.json` are the lab tasks LT01, LT02, LT03, LT05 and LT08 on starts rebuilt from a world seed, so no
DF save ships. `embark/make_task_fort.sh <task> <seed>` makes the embark (above), turns it into the task's situation
with a recipe (`embark/forts/worked-y1.json` for LT01/03/05/08, `neglected-y1.json` for LT02: migrants, the scripted
policy's own build calls completed with `dig-now` / `build-now`, three settle days, exact stocks, orders, plugins,
stress, the caravan report and a pending Migrants event), checks it against the recipe's `expect` ranges and saves it
as `scenarios/snapshots/fort-<recipe>-<seed>/` (gitignored). `docker/task_forts.sh` runs it in containers:

```sh
docker/task_forts.sh --image yukon-df --seeds 2001,2002,2005 --recipes worked-y1,neglected-y1   # the test-public pool
python3 embark/pool_task.py scenarios/seed/lt01-drought.json --split train --seeds 1000,1002 --out scenarios/seed/train/lt01.json
```
Each task's `fort` block gives the recipe and the seed range per split (train 1000-1999, test-public 2000-2099,
test-private 9000+, drawn by the maintainers and never written here); `snapshot_pool` lists the test-public forts.
About 1.5-4 min per seed for both recipes on the Mac (most of it the embark search). The layout and every pinned stock
count reproduce on one host type; the migrants, the three settle days and the run after load don't. The embark site
for a seed can differ between host types (seed 1000: Mac vs Lambda), see docs/SEED-FORTS.md §2. The snapshot-based
`lt0*.json` stay as they were (lab-2.0, the `dfbench/v2.1.1` results); the seed-built ones have new names
(`-seed`) and task hashes.

## Embark snapshots (generated from a seed)
`embark/make_embark.sh` makes a fresh fort from (world seed, world-gen param set, site rules) and saves it as a
snapshot; `docker/embark.sh` runs it in throwaway containers and copies the result to
`scenarios/snapshots/embark-<rules>-<seed>/`:

```sh
docker/embark.sh --image yukon-df --rules TEMPERATE_SOIL --seeds 1000,1002,1003,1004          # the LT09 train pool
docker/embark.sh --image yukon-df --rules TEMPERATE_SOIL --seeds 1000 --check                  # make twice, compare
```
Steps: `dwarfort -gen` (headless) -> site screen -> `embark/site_select.lua` ranks world tiles by the rules' `region`
filters (biome, river, salinity, savagery, evil, vegetation) and picks a 4x4 rectangle with a river cell (`rect`,
avoiding existing sites) -> embark, rejecting the rules' `reject_warn` warnings (heavy aquifer, salt water, savage,
evil) -> "Play now!" -> `embark/fort_probe.lua` checks the real map (`accept`: >= 75% of wagon-level ground has
>= 2 soil levels, trees, surface water, no aquifer in the top 3 levels) and fingerprints it -> quicksave. A rejected
fort is discarded and the next candidate tried. `SNAPSHOT.json` holds the recipe, the probe and the fingerprints,
plus the world and fort names `reset_fort.sh` clicks. Rules: `embark/rules/*.json`; extra param sets:
`embark/world_gen.txt`. The probe reads hidden tiles, so it runs at capture time only (BENCHMARK-v1 §4.3).

**Cost** (Lambda x86_64, shared host): world gen 5-12 s; embark 50-80 s when an early candidate passes, up to 4.5 min
when several are rejected (each rejected embark costs ~45 s); save 15 s. Seed 1001 had no acceptable site among its
40 best candidates (mostly shallow aquifers or no surface water), so the pool is the first four seeds from 1000 that
yield one.

**Determinism.** World gen must run on one CPU (`taskset`, `EMBARK_CPU`): unpinned, DF 53.16's world-gen history
(sites, names, populations, roads) differs run to run; pinned, two gens of a seed match. With that, `--check` on
seeds 1000/1002/1003/1004 gave the same world tile, rectangle, world name, map fingerprint (every tile's type, liquid
and aquifer flags), plants and wagon loadout every time. DF rolls these at embark from an RNG we can't seed (fixing
the clock with libfaketime didn't help), so they differ between regenerations: the fort's name; one of the 7
"Play now!" professions (the crafter slot: stonecrafter or metalcrafter; the other six and their work skills are
fixed); performance skills (dance, music); the number (6-8) and kinds of the loadout's weapons; spider webs and
cavern/wildlife units; world.sav's bytes. `bench/key.py` therefore identifies an embark snapshot by its recipe and
reproducible fingerprints, not by world.sav, so a regenerated pool keeps the task hash.

**The default start fort** (start-year / OP1) is fort_start_snapshot's own world and site rebuilt the same way:
`embark/rules/DEFAULT_FORT.json` pins the site (world tile (4,5), local (8,8)) and has `"gen_seed": "paramset"`, so
world gen runs with `RANDOM` and the param set's own seeds (12345). **DF keeps only the low byte of `-gen`'s numeric
seed** (12345 -> "9", 1000 -> 0xE8; gamelog `Seed:`), so numeric seeds give at most 256 distinct world seeds
(1000 and 1256 both log 0xE8; whether their maps match is not yet checked). `embark/make_default_fort.sh` (inside the image) or `docker/embark.sh --rules DEFAULT_FORT
--seeds 12345` (host) writes `scenarios/snapshots/embark-default-fort-12345/`; `reset_fort.sh` and `smoke.py` use it
when `fort_start_snapshot/` has no `world.sav`. Comparison with the legacy save: `docs/SEED-FORTS.md` §6.

**Test-private pools** (LT09 test, LT10) use the same command with seeds 9000+ chosen by the maintainers, run off the
public repo; only the pool's task hash is published (BENCHMARK-v1 §5.4). Don't generate them into this repo.

**90-day reference runs on the train pool** (2026-10-11, Lambda x86_64, n=2 per arm and fort; each cell is
`credited_value_final / drink_final` for k=0, k=1; deaths 0 and `days_drink_positive` 91/91 in every run; results
copied to `<persistent-filesystem>/embark/` while the VM lasts):

| fort (seed, biome, world tile) | noop | scripted | automation |
|---|---|---|---|
| 1000, shrubland (13,8) | 0, 0 / 26, 26 | 1612, 1790 / 267, 287 | 2146, 2155 / 281, 271 |
| 1002, shrubland (7,7) | 0, 0 / 26, 26 | 1808, 1765 / 288, 301 | 2172, 2040 / 276, 277 |
| 1003, shrubland (6,10) | 0, 0 / 26, 26 | 916, 1542 / 26, 292 | 40, 40 / 46, 46 |
| 1004, shrubland (11,11) | 0, 0 / 26, 26 | 1467, 1495 / 248, 247 | 2301, 1903 / 281, 267 |

- **scripted** (refs_version 2) built Carpenters/Still/Kitchen and 2 underground farm plots on every fort. On 1003 a
  brook runs beside the wagon: the old policy's stair site (the farthest free 3x3 site) put its room in the brook bed,
  so no soil farm site ever appeared and it never farmed (0 plots in 2/2 runs, refs_version 1). It now re-picks a
  stair at least 8 tiles away once the room is dug (or 15 days on) without a soil farm site; on 1003 that gave 2 plots
  by day 20 in 2/2 runs. start-year 60 d with the change: credited 1238, 1134 (validated range 1150 [1124, 1176]).
  The 1003 k=0 run brewed nothing: the kitchen cooked the wagon's 6 brewable plants before the still used them (a
  cook-vs-brew race the tool API can't prevent; see v1.1 below).
- The table ran on the pre-freeze harness (`dfbench/v0-dev`). Re-checked on the rebased branch (`dfbench/v1`,
  refs_version 2, k=0): scripted 1606 / 277 on 1000 and 1640 / 287 on 1003; automation 1894 / 271 and 50 / 52.
- **automation** fails on 1003 (credited 40): its fixed `library/embark.csv` workshop layout lands on the brook
  ("Unsuitable tiles for building: 11"), so no Carpenters, no barrels. A site-aware layout origin would fix it.
  It credits no food anywhere (it doesn't cook; harvests aren't credited yet).
- **noop** drinks the wagon's 60 down to 26 and keeps drink all 90 days (7 dwarves), so `days_drink_positive`
  doesn't separate on this horizon; `credited_value_final` and `drink_final` do (noop 0 / 26 everywhere).
- All four sites came out SHRUBLAND_TEMPERATE: the ranking (deep soil, vegetation near 60, central tiles) favours
  it. Widen with per-pool biome quotas if biome variety matters.

**v1.1 candidates (harness changes, not made: the harness is frozen).** (1) No tool keeps brewable plants out of the
kitchen (DFHack `ban-cooking`); an agent, like scripted on 1003 k=0, can lose its first brew to cooking. (2) A dug
room's floor can turn out to be a brook bed; the observation shows only that no soil farm site appeared, not why.

**LT10 (SHALLOW_ROCK_COOL) notes, not built.** `embark/rules/SHALLOW_ROCK_COOL.json` and the `COOL POCKET` param set
(PINNED POCKET with TEMPERATURE 0-45) are drafts. On a dev seed (5000, outside both pools) every world tile's geology
has 4 soil layers and every probed cool site had >= 2 soil levels under the wagon, so "1 soil level over stone"
doesn't occur with these param sets; cold sites' rivers were frozen at embark (surface water 0, so the probe should
count ice too). LT10 needs either a param set that thins soil (not found among DF's world-gen tokens; erosion and
elevation are candidates to test) or a different shift that does occur: a light aquifer 2-3 levels down, a frozen
river (no drink source until thaw), or a treeless site.

