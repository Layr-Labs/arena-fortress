# Seed-built task forts: no DF save ships

Status: **built and validated on the Mac (2026-10-14, n = 4 per arm), not yet frozen as a suite** (the n = 8
re-validation on the frozen key and the suite label, `lab-3.0` or `lab-2.1`, are the user's call). Branch `seed-forts`. This is
YUKON-BUILD §5.1's blocker (build item 2, "B7 seed-only forts"): every lab-2.0 task started from a DF save in
`scenarios/snapshots/` (`scripted-y1`, `noop-y1`; licence `terms-unclear`, LICENSING.md), so nothing could ship.
Now each task's start is rebuilt from a world seed and committed scripts, by the competitor (`yukon setup`, train and
test-public) and by the verifier (its private pool), with the pinned image.

## 1. The construction

A start fort is **(world seed, embark rules, recipe)**:

1. **Embark** (the existing pipeline, `embark/make_embark.sh`): `dwarfort -gen` pinned to one CPU, site rules
   `embark/rules/TEMPERATE_SOIL.json`, "Play now!", the fort probe. A fresh 7-dwarf fort in early spring of year 2.
2. **Recipe** (`embark/forts/<name>.json`, run by `embark/build_fort.py`): the task's situation, made directly instead
   of by playing a policy for a year. About two game days of simulation in total.
3. **Check**: `embark/fort_summary.lua` summarizes the fort and `embark/fort_check.py` compares it with the recipe's
   `expect` ranges; a fort outside them is not saved.
4. **Save**: a quicksave plus `SNAPSHOT.json` (embark recipe and fingerprints, recipe and build-script hashes, the
   summary and layout, timings) in `scenarios/snapshots/fort-<recipe>-<seed>/`, which is gitignored like
   `embark-*`. `bench/key.py` identifies the fort by embark id + recipe hash + build-script hash, so a rebuilt pool
   keeps its task hash.

`embark/make_task_fort.sh <task|recipe> <seed> --out DIR` does 1-4 inside the image; `docker/task_forts.sh --seeds
... --recipes ...` runs it in throwaway containers (one embark per seed, every recipe built on it) and copies the
forts out. `embark/pool_task.py` turns a task into its train or test-private variant on a given seed list.

### 1.1 Recipe steps (`embark/build_fort.py`)

| step | how | deterministic given the seed? |
|---|---|---|
| sites | `embark/fort_site.lua sites`: free 3x3 surface sites around the **map's centre** by observe2.lua's rules, with a 9x9 keep-out box for the wagon | yes. Anchored at the map centre because DF places the wagon at a random tile of the centre (±1 from one embark of a seed to the next) |
| population | one migrant wave: the civ gets a caravan report (`activity_stats`, a copy of the fort's own statistics; a fresh embark has none, and a forced Migrants event without one brings nobody), its reported wealth is set, a Migrants event is queued, one game day runs (`embark/fort_events.lua wave`) | **no**: DF picks the migrants and the wave size varies (18500 -> +10..+12 from 7 founders over 16 builds; 18 citizens in every final worked-y1 build on seeds 1000, 2001, 2002 and 2005). A fort outside the recipe's range is rebuilt from the embark (up to 3 tries). An arrived citizen can't be sent away (`flags1.left` doesn't remove a citizen) |
| logs | `fort_stock.lua logs`: free logs of the tree species nearest the map centre, so the workshops have material | yes |
| structures | the **scripted policy's own tool calls** through `harness2.act` (appoint_manager, build_workshop on the first sites, dig_stairs + a 7x3 dig_room one level down at the farthest site whose room box is all soil, build_farm on its two 3x3 plots), completed at once with DFHack `dig-now` and `build-now` | yes (layout identical in two independent builds of a seed). Tree-root walls are never dug (DF cancels digging a root wall under a living tree; `dig-now` skips it), so the stair site is chosen where the room box has none |
| automation | enable_automation autochop / seedwatch / autofarm | yes |
| settle | 3 game days, so farmers plant the plots and the migrants walk in | **no** (DF's simulation, BENCHMARK-v2 §7.1) |
| stocks | `fort_stock.lua`: exact counts, items created by DFHack (`dfhack.items.createItem`), dropped 10-16 tiles from the map centre in a fixed scan order, removals highest item id first | the counts yes; which items the settle days consumed no |
| orders, stress, events | add_order; `fort_events.lua stress` (seeded pick of citizens); the caravan report and a pending Migrants event as on the legacy snapshot | yes, except which dwarves exist |

### 1.2 Recipes and tasks

| task | recipe | replaces | run-time setup (unchanged unless noted) |
|---|---|---|---|
| LT01 drought | `worked-y1` | scripted-y1 | `shortage.lua 1 0` |
| LT02 rescue-neglected | `neglected-y1` | noop-y1 | none |
| LT03 mood-artifact | `worked-y1` | scripted-y1 | `mood.lua woodcrafter fey 0` |
| LT08 migrant surge | `worked-y1` | scripted-y1 | `migrant_surge.lua 100000`; the second wave comes from the recipe's pending spring Migrants event, as scripted-y1's own |
| LT05 goblin raid (later) | `worked-y1` | scripted-y1 | `invade_edge.lua`: invade.lua with the spawn tile picked from the map (southern edge, fort's walkable group; on scripted-y1 the rule gives 97,188,106 vs the hard-coded 96,189,106) |

**worked-y1** (scripted-y1 after 336 scripted days): Carpenters, Still, Kitchen; stair + 7x3 farm room, two planted
underground plump-helmet plots; manager; autochop/autofarm/seedwatch; 571 drink in 88 barrels, 3 empty barrels,
7 plump helmets, the legacy seed mix (62 plump helmet, 8 cave wheat, 4 pig tail, 3 sweet pod), food 166, ~237 logs,
19 unplaced beds, 12 tables, 12 chairs; orders make_barrel 4, cook_meal 5; 11 dwarves made content (stress); caravan
report 3,330 and a Migrants event at spring tick 4087. Population 17-19: from 20 citizens the v2 harness's manager
needs an assigned office (BENCHMARK-v2 decision 5), which would change LT01/LT03.

**neglected-y1** (noop-y1 after 336 noop days): nothing built or dug, no manager, no automation, no drink, no plants,
15 empty barrels, the legacy seed mix (49 plump helmet, 5 each of five others), food as left by the embark (~118),
no free logs or furniture; 11 dwarves unhappy, 2 of them stressed; caravan report 133 and the pending Migrants event.
Population 16-19.

### 1.3 Compared with the legacy snapshots (fort_summary.lua)

| | scripted-y1 | worked-y1 (2001 / 2002 / 2005) | noop-y1 | neglected-y1 (2001 / 2002 / 2005) |
|---|---|---|---|---|
| citizens | 19 | 18 / 18 / 18 | 18 | 17 / 17 / 18 |
| stress categories 0-6 (stressed) | 0,0,3,7,8,1,0 (0) | 0,0,0,8,9,1,0 (0) and similar | 0,2,9,4,2,1,0 (2) | 0,2,9,6,0,0,0 (2) and similar |
| workshops | Carpenters, Still, Kitchen | same | none | none |
| farm plots (underground, planted) | 2, 2 | 2, 2 | 0 | 0 |
| drink / food / brewable plants / seeds | 571 / 166 / 7 / 77 | 571 / 166 / 7 / 95 (18 seeds held by planting jobs) | 0 / 98 / 0 / 74 | 0 / 115-120 / 0 / 74 |
| barrels (empty) / free logs | 91 (3) / 230 | 93 (3) / 237 | 15 (15) / 0 | 17 (15) / 0 |
| beds / tables / chairs (free) | 19 / 12 / 12 | same | 0 / 0 / 0 | same |
| orders / nobles / automation | 2 / leader, manager / chop, farm, seedwatch | same | 0 / leader / none | same |
| pending Migrants, caravan report | 1, 3,330 | same | 1, 133 | same |
| date | spring day 16, year 3 | spring day 19, year 2 | spring day 16, year 3 | spring day 19, year 2 |
| dug below the wagon level | 32 tiles | 21 | 11 | 0 |
| map | the old fort (Land of Destiny) | a fresh TEMPERATE_SOIL embark per seed | old fort | fresh embark |

What differs in kind: the map is new for every seed (the legacy tasks all ran on one map), the migrants have a year
less history (no relationships, no year-1 skill gains), there are no year-1 corpses, animals or stray items, food is
fish rather than mussels and meals, and the seed-built fort is a year "younger" (year 2). Legacy wealth counted the
year's production; the new forts' created items count as pre-existing for `credit.lua` like the snapshot's did.

## 2. Determinism (what is and isn't reproducible)

Reproducible on one host type, checked by building seed 2001 twice in independent containers (`fort_compare.py`):
the embark id (world tile, rectangle, map / plants / loadout fingerprints), the layout (every workshop and plot at
the same tiles), every stock count the recipe pins, orders, nobles, plugins, events. Not reproducible: which dwarves
arrive and how many (17-19 / 16-19 by the recipes' ranges), stress values in detail, food above the target, the
tick the build ends on (±100), world.sav's bytes, and everything DF simulates after load (BENCHMARK-v2 §7.1; tasks are
judged on pooled n).

> **Update 2026-10-16 (`research/seed-portability.md`):** investigated, and the picture below is incomplete.
> - `-gen` uses only the seed's low 8 bits (seed 1256 = seed 1000; seed 9000 = seed 1064), so every test seed
>   collides with a train seed mod 256.
> - Emulated x86 (Rosetta and QEMU, which agree with each other) and native x86 (three CPU models, which agree)
>   generate different worlds for every seed tried. The Lambda VM matched neither on two of three seeds.
> - Native world gen isn't fully repeatable on one host (the canonical embark id in ~5 of 6 rebuilds).
> - Recommended: define forts by their verifier-built embark id (rebuild and check locally), put the full seed in
>   the param set (`EMBARK_SEED_IN_PARAMS`), and screen pool seeds across native hosts.

**New finding: embark site choice differs between hosts.** Seed 1000 on the Mac (Docker Desktop, Rosetta, 16 CPUs)
embarks at world tile (15,7)+(6,5), map fingerprint `ab401907`, in 3 of 3 embarks; the LT09 train pool generated on
the Lambda VM (native x86_64) has seed 1000 at (13,8)+(5,9), map `d5359c2c`. On the Mac the (13,8) tile gets no
valid 4x4 rectangle, so the world history (sites, which the rectangle avoids) differs between the hosts. Not yet
explained (CPU count visible to DF, Rosetta floating point, ...). Consequences:
- A pool is reproducible on the host type that made it. The verifier must build its private pool on its own
  machine (it does), and a published seed list regenerates the same forts only on the same image *and* host type.
- Competitors on another host get different test-public forts from the same seeds, and a different task hash for
  test-public (`bench/key.py` hashes the embark's tile and map). Harmless for local scores, but `yukon run` should
  print a note when a local pool's embark ids don't match the published ones.
- Before season 0: run `docker/embark.sh --check` for the pool seeds on the verifier box itself, and measure a
  Lambda-vs-Mac pair on purpose (same seed, `--cpuset-cpus`, native x86 vs Rosetta) to find the cause.

Also: **the wagon is placed ±1 tile at random** at embark (seed 2001: (95,96) in one embark, (96,95) in the next),
which observe2.lua's wagon-relative sites inherit. `embark/compare.py` doesn't check it; the build anchors at the map
centre for that reason.

## 3. Validation (Mac Docker, ≤ 3 containers, 2026-10-14; `runs/seedforts-2026-10-14`)

Pool: test-public seeds 2001, 2002, 2005 (the first three of 2000-2006 with an accepted embark on the Mac; 2000,
2003 and 2004 have none). n = 4 per arm, `--seed 12345`, so k = 0..3 ran on 2001, 2002, 2005, 2001. Image
`yukon-df:sf-pool` = the branch on the v2.1.1 harness (key fields unchanged: `tools=138ac75f|sem=8ca731bb|
manual=42d48428|obs=4:60303cb2|loop=b4884c6b|score=5:f045d340`). 60 runs, 0 crashed. Legacy = the snapshot-based
task on the frozen key (VM, n = 8: `runs/v211val-2026-10-14` for LT01/LT02/LT05, `runs/v21val-2026-10-14` for
LT03/LT08, carried over under the regression gate).

| task (task hash) | noop | scripted | witness | witness vs noop p (n=4) | legacy noop / scripted / witness (n=8) | drop-rule direction |
|---|---|---|---|---|---|---|
| LT01 drought (`lt01-drought-seed:f74fb170`) | 0/4, 0.00 | 3/4, 0.94 | **4/4**, 1.00 | 0.029 | 0/8 / 8/8 / 8/8 | holds |
| LT02 rescue (`lt02-rescue-neglected-seed:90413c18`) | 0/4, 0.30 | 4/4, 1.00 | **4/4**, 1.00 | 0.029 | 0/8 (0.30) / 4/8 (0.87) / 8/8 | holds |
| LT03 mood (`lt03-mood-artifact-seed:32ce569b`) | 0/4, 0.00 | 0/4, 0.00 | **4/4**, 1.00 | 0.029 | 0/8 / 0/8 / 8/8 | holds |
| LT08 migrants (`lt08-migrant-surge-seed:8fbc68bf`) | 0/4, 0.73 | 0/4, 0.74 | **4/4**, 1.00 | 0.029 | 0/8 (0.72) / 0/8 (0.74) / 6/8 | holds |
| LT05 raid, later (`lt05-goblin-raid-seed:85f096b8`) | 0/4, 0.34 | 1/4, 0.42 | 2/4, 0.70 | 0.086 | 0/8 (0.24) / 2/8 (0.35) / 5/8 (0.66) | as legacy: not admitted |

(pass count, mean partial. p = 0.029 is the smallest a 4-vs-4 permutation test can give; the drop rule's p < 0.01
needs the n = 8 re-validation on the VM.)

Differences from the snapshot-based versions:
- **LT01:** the same picture. Scripted missed one run (fort 2002: no drink brewed inside the window, drink 22 at H;
  the recipe-v1 batch had one such miss on 2005), legacy 8/8. The witness brews 50-55 drinks in W (legacy
  witness 55-70). Population stays at 18: the pending spring Migrants event brings nobody at report 3,330, as on
  scripted-y1.
- **LT02:** scripted passes 4/4 here vs 4/8 on noop-y1: the seed-built neglected forts are easier to rescue for a
  policy that builds (a fresh embark's trees are all standing and its soil site is near the wagon; noop-y1 is a
  year-old map). Noop's partial is exactly the legacy 0.30.
- **LT03:** identical outcome; the mood dwarf went insane in all 8 noop/scripted runs, no deaths.
- **LT08:** population peaks 42-49 (legacy 43-50); witness 4/4 vs 6/8. The first build of the recipe (recipe-v1,
  `runs/seedforts-2026-10-14/recipe-v1`) reached only 24-28: its caravan report still counted the build's own
  migrant wave (`migrant_wave_idx` 1), and DF shrinks later waves by it. The recipe now leaves the report as a
  caravan would (wealth 3,330, population = citizens, no wave since), and the surge is back (18 -> 34-41 on day 1,
  -> 42-49 on day 16, from the pending event; scripted-y1: 19 -> 36-41, -> 45-48 around day 19).
- **LT05:** within noise of legacy; still short of the drop rule, as before.
- **Fewer dwarves:** 18 (worked) and 17 (neglected) instead of 19 and 18: one wave of +10..+12 is all a build can
  use (an extra wave overshoots, and the office rule starts at 20).
- **Run wall time** on the Mac, mean per run: LT01 118-138 s, LT02 174-220 s, LT03 98-115 s, LT05 74-93 s,
  LT08 209-220 s.


## 4. Build time per fort (Mac, Docker Desktop + Rosetta, 3 containers in parallel)

Measured from 29 builds on seeds 1000, 2001, 2002, 2005 and 2006 (`docker/task_forts.sh`, Mac Docker Desktop with
Rosetta, 3 containers in parallel; the VM was busy with round-3 training and wasn't used):

| step | time |
|---|---|
| embark (`make_embark.sh`: world gen ~5 s, site search, "Play now!", probe) | 50-190 s, mean 98 s; seed-dependent: each rejected candidate costs ~30-45 s (2002: 160-190 s every time) |
| reload the embark for the second recipe | 10-12 s |
| build, worked-y1 (wave + structures + 3 settle days + stocks) | 17-34 s, mean 23 s |
| build, neglected-y1 | 12-22 s, mean 15 s |
| check + quicksave + copy | 10-16 s |
| **one seed, both recipes** | **116-257 s wall** |
| a seed with no acceptable site | 20 s (2003: no tile passes the region rules), 95 s (2000: 2 candidates, both shallow aquifers), 821 s (2004: 40 candidates rejected) |

So `yukon setup` for a 3-seed test-public pool takes ~4-5 min at 3 wide (plus any rejected seeds), and the
verifier's season pool (4 seeds × 2 recipes, YUKON-CHALLENGE §3.1) ~5 min at 4 wide, ~15 min serially. The embark
step is about what the Lambda x86_64 VM measured (50-80 s when an early candidate passes, scenarios/README "Cost"). A recipe that fails
its `expect` (a migrant wave out of range) is rebuilt from the saved embark at the build step's cost; no build
needed a second try in these 29.


## 5. What is still a save

- **OP1 start-year / the default start** now has a seed-built replacement (§6), used automatically when
  `fort_start_snapshot/` has no save. Its task hash differs from the legacy save's, so OP1 references need re-running
  on it before it can replace the legacy rows.
- **The v1 panel and other legacy scenarios** (`drought-y2`, `rescue-neglected-y2`, `goblin-raid-y2`, `thief-raid-y1`,
  `famine-y2`, the `*-y2` snapshots) keep their saves; they're not in season 0.
- **The repo split** (YUKON-BUILD build item 9) must copy `scenarios/snapshots/` and `fort_start_snapshot/` out
  entirely: they are committed in this private repo's history.
- **Not seed-reproducible across host types** (§2): which forts a seed gives depends on the host that runs world
  gen. Seed-only, but per host type.
- Every run still starts from a save, made locally from the seed: what changed is that nobody ships one.


## 6. The default start fort from its seed (2026-10-16, branch `seed-default-fort`)

`fort_start_snapshot` (start-year / OP1, `reset_fort.sh`'s default, the CONTRIBUTING quick start) was a "Play now!"
embark in world PINNED POCKET, seed 12345, at world tile (4,5), local rectangle (8,8): "The Land of Destiny",
SHRUBLAND_TEMPERATE. `embark/rules/DEFAULT_FORT.json` rebuilds it: the same param set and seed, the site pinned (no
search, no rejected warnings, the probe checks only 7 citizens), the standard embark. `embark/make_default_fort.sh`
(inside the image) or `docker/embark.sh --rules DEFAULT_FORT --seeds 12345` (host) writes
`scenarios/snapshots/embark-default-fort-12345/` (gitignored, like every `embark-*`), about 80 s on the Mac.

**Which fort is used.** `bench/key.py` `start_snapshot()`: `fort_start_snapshot` if its `world.sav` exists (this
private repo: nothing changes, and every key and task hash is the same as on main), else the seed-built fort.
`reset_fort.sh` (SNAPSHOT unset) and `smoke.py` (a scenario naming `fort_start_snapshot`) follow the same rule. On
the seed-built fort the task names and hashes change: no scenario -> `start-default-seed:4ad12949`, start-year ->
`start-year:224d75a7` (legacy `start-default:2aff52b8`, `start-year:e1ef87c8`). The harness key fields are unchanged.

**Two make_embark.sh findings.**
- **`-gen` keeps only the low byte of a numeric seed.** `-gen 7 12345 "PINNED POCKET"` logs `Seed: 9` (0x39 =
  12345 mod 256) and made a different world, with a mountain at (4,5); `1000` and `1256` both log 0xE8. So numeric
  seeds give at most 256 world seeds, and the seed recorded in SNAPSHOT.json is not DF's seed. Passing `RANDOM`
  makes DF use the param set's `*_SEED` fields; rules with `"gen_seed": "paramset"` do that, and make_embark.sh
  fails unless the gamelog shows the expected seed. The existing pools (TEMPERATE_SOIL, seeds 1000+, 2000+) are
  unchanged by this; whether two of their seeds that share a low byte give the same map isn't checked yet.
- **A pinned site needs the click aimed.** Without the search, the embark screen is reached within a second of the
  map drawing: the "On your own!" popup arrives late, the first click is often lost, and DF's hover handling moves
  the struct's rectangle to the one under the mouse. For a pinned site make_embark.sh clicks where the pinned
  rectangle is drawn (screen centre plus its offset from `zoom_cent`) and fails if the fort isn't at the pinned
  site. The search path is unchanged apart from dismissing that popup before clicking Embark.

**Compared with the legacy save** (Mac Docker Desktop, Rosetta, 16 CPUs; `runs/seed-default-fort-2026-10-16`;
`embark/fort_summary.lua` and `embark/fort_probe.lua` on both):

| | legacy fort_start_snapshot | seed-built (4 builds) |
|---|---|---|
| world, site, biome | The Land of Destiny, (4,5)+(8,8), rect 72,88-75,91, shrubland (veg 64, sav 57, evil 38) | same |
| date, citizens | spring day 15 year 2, abs_tick 823201, 7 | abs_tick 823200 (one tick earlier), 7 |
| stocks, buildings, nobles, orders, stress | drink 60, food 101, 15 barrels, ...; nothing built; expedition leader; none; 7 in category 3 | identical (fort_summary `stocks`, `pop`, `buildings`, `nobles`, `orders`, `events` all equal) |
| wagon loadout | fingerprint `204c04cc` | same |
| roster_core | `d016540d` (crafter slot METALCRAFTER) | `d016540d` in 3 of 4 builds; the crafter slot varies, as on every embark |
| aquifer under the wagon | 4 levels down (`aquifer_depth_near`) | same |
| map / plants fingerprints | `f2ead5b2` / `0888be32`; trees 1012; flow tiles 18549 (surface 1972) | `8fd05da2` / `7de46b30` in all 4 builds; trees 1284; flow 18566 (surface 1972) |
| wagon | (97,96,106) | (96..97, 95..96, 106): DF's ±1 at embark |
| fort name, weapons, world.sav | Scoureddike | random per build (as for every embark) |

So the seed-built fort is the same site and the same starting state, but not the same map: about 27% more trees
and slightly different water. The legacy world was generated on an internal x86_64 box (x86_64, 8 cores, not pinned to one
CPU) and the seed-built one on the Mac under Rosetta, pinned; world-gen history and vegetation differ between hosts
(§2), and that is the likely cause. Not tested: building it on native x86_64 to see whether it then matches
`f2ead5b2`.

**Validated** (image `yukon-df:sdf-1` = this branch, `fort_start_snapshot` moved away to act as a public checkout):
`reset_fort.sh` without any start fort fails with the build command; after `make_default_fort.sh`, `READY 823200
pop=7`; `harness.py --selftest` passes; two builds compared with `embark/compare.py`: DETERMINISTIC (tile, rectangle,
tick, citizens, world name, map, plants, loadout). 20-day runs, n = 1 each, 0 crashed:

| start | noop: credited / drink_final / days drink+ | scripted: credited / drink_final / days drink+ / decisions |
|---|---|---|
| default (no scenario) | 0 / 53 / 21 | 451 / 128 / 21 / 26 |
| `--scenario scenarios/start-year.json` | 0 / 53 / 21 | 410 / 128 / 21 / 26 |

7 citizens and 0 deaths at the end of all four. **Not validated:** any run longer than 20 days, n > 1, model arms,
the start-year 336-day references on this fort (needed before it replaces the legacy rows), `docker/batch.sh`
with the fort baked into an image, and native x86_64 builds.

