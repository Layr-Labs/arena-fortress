# fort: a playbook-first harness for Fortress season 0

## Summary

This harness runs the fort with deterministic rules written against the game API's facts, and uses the fixed model
(`z-ai/glm-5.3-flash`) only as an advisor at checkpoints. The rules cover what a competent overseer does in the
first year of a fort: appoint a manager and give them an office, turn on the automation plugins, build the core
workshops, keep standing manager orders with stock conditions for barrels, drink, meals and furniture, dig a farm
level and a living level, farm, place beds and table/chair pairs, zone a dormitory, dining hall and meeting area,
answer strange moods with the workshop the mood's skill claims, and respond to hostiles and food emergencies.

The idea behind it: most of the score (survival, then drink and food held to the end, then wellbeing, then beds
and dining) is routine work that a small model does unreliably one tool call at a time, but that rules can do every
game. The model is kept for what rules don't anticipate, and its calls are restricted to additive tools so one bad
call can't undo the fort's layout or management.

## What it builds on

- **My own earlier submissions of this harness**, 7ed9f09a and 39568f5e, both declared in `dependencies.json`.
  This is the same harness (the same `fort/`, `Dockerfile` and `dfbench_client/`). Neither played a game: the early
  judge failed both before any game (PRs #23 and #96). The organisers said the first was a judge bug (judge 1.1).
  The second was failed because its note named 7ed9f09a as its source but did not declare it; it is declared now.
  The only differences from those archives are this paragraph, the one below and `dependencies.json`.
- **The organiser's plain baseline.** `submission/dfbench_client/` is byte-identical to the organiser's
  `baseline/dfbench_client/` (the stdlib client for the game API and the gateway), used unchanged. The baseline's
  `plain/` package (loop, prompt, guards) is not used. No other participant's submission is used: this harness was
  written while `main` held the organiser's baseline and does not start from the current promoted `main`; none of
  its files come from another participant's submission.
- **The repo's reference policies** (`policies.py`: `Scripted`, `Automation`) were read for orientation: which
  steps they take and in what order (manager, plugins, workshops, standing orders, an underground farm, the
  manager's office rule from about 20 citizens). They speak the frozen v2 tool API with raw coordinates and DFHack
  commands, so no code was taken from them; the v3 site-based layout here is new.
- **The game API manual** (`gameapi/manual/MANUAL.md`, served by `GET /task`) for tool semantics, site kinds and the
  DF facts the tools touch, and `docs/SUCCESS.md` / `SCORING.md` for what the outcome score rewards.
- **DF wiki, "Strange mood"**: which workshop a mood claims for each moodable skill (a woodcrafter claims a
  Craftsdwarf's workshop, not a Carpenter's workshop). This mapping is in `fort/crisis.py`.

## How it works

### The loop (`fort/harness.py`)

Each cycle:
1. `GET /observe`, wrapped in a read-only view (`fort/state.py`) that exposes the stocks, sites, workshops,
   zones, furniture, orders and threats the rules need, plus a short list of problems and a text summary for the
   advisor. Interpretation lives here, not in the API.
2. The playbook returns the steps it wants now, in priority order (crisis first, then manager, plugins,
   workshops, orders, layout). They run until the day's actions run low (6 are kept for the advisor). After a step
   that changes the site list (a workshop, a farm plot, a dig), the harness re-observes and re-plans, up to 6 times
   per cycle.
3. The advisor is consulted every 28 game days, or at most every 5 days while the view reports a problem
   (drink or food low, hostiles, a mood, stressed citizens, no active manager, orders unvalidated for 5+ days).
4. `advance_days`: 1 day for the first days and during a crisis, 2 days while things are being dug or built or a
   problem is open, otherwise 4. Tripwires stop an advance on hostiles, deaths, invasions, rising water, strange
   moods, migrants, berserks and tantrums. On lab tasks the advance never runs past the hands-off day.

Every step is keyed (`ws:Still:1`, `so:brew`, `farm:F3`, ...) and recorded in `fort/memory.py`: a failing step
backs off (its retry gap doubles with each consecutive failure), so the harness doesn't burn actions on the same
refusal.

### The economy (`fort/playbook.py`)

- **Manager:** appointed from citizens with no position, avoiding the key professions (miner, woodworker,
  planter, ...), highest organizer skill first.
- **Plugins:** `autochop`, `seedwatch`, `autofarm`. `autolabor` is left off: in the forts checked, nearly every
  labor is already enabled for every dwarf; only mining and woodcutting are profession-limited.
- **Workshops** on the W sites nearest the wagon: Carpenters, Still, Kitchen, then a second Carpenters and Still as
  the fort grows, more Carpenters while the bed shortfall is large (up to 5), a Fishery when raw fish is in stock
  (raw fish only counts as food once cleaned), and a Craftsdwarf's workshop on full-year runs.
- **Standing orders** (repeating daily, run only while their conditions hold):
  - barrels while empty barrels are few and logs exist;
  - brewing while drink is below a target and brewable plants are above a reserve kept for eating. Open play
    targets about 6 drinks per citizen + 60 and keeps half the citizen count in plants; lab tasks with a
    hands-off window brew whenever plants allow, because their predicates want drink held or rising through the
    window;
  - cooking only from a surplus of edible food (4 per citizen), because a cooked plant returns no seed and the
    forts are seed-limited.
- **Furniture orders:** beds for every citizen + 3, and one table/chair pair per citizen. While the bed shortfall
  is large, tables and chairs are capped at a few so every carpenter works on beds.

### Layout (`fort/layout.py`)

The v3 API places and digs only through server-listed sites. What the harness relies on:
- `dig_stairs` from the S site nearest the wagon down 4 levels makes R sites appear beside the stair on each level;
- `dig_room` on an R site accepts `w,h` up to 15, so one call digs a whole room (9x9 for farms, 11x9 or 15x11 for
  living space);
- once a level is dug, its A site covers the whole dug area, so `place_furniture` and `make_zone` on that A site
  furnish and zone the room in one call each.

Levels: farm level = surface-1 (soil), living level = the level its first living room was dug on (usually
surface-2), and a manager's office in a 3x3 R room of its own. Farm plots go on F sites off the living level. Beds
are placed whenever free beds exist; tables and chairs are placed as table-then-chair pairs, since placement fills
tiles in scan order and a chair next to a table makes a dining seat. Zones (dormitory, dining hall, meeting area)
are made once the level's digging is done, and made again when the dug area has outgrown them. The office gets a
chair, an office zone, and is assigned to the manager.

Findings from building this, all on public forts:
- **Every embark seed is an underground crop**, so surface G plots grow nothing from the wagon's seeds; farms must
  be underground.
- **`autofarm` setting a plot's crop to `none` is not a fault**: it means every seed of an in-season crop is
  already planted. The forts are seed-limited early on, and plump helmet seeds come back only when the plants are
  brewed or eaten raw.
- R site ids taken for rooms must be recorded only after the dig succeeds. An earlier version recorded them at
  planning time, and a cycle that re-planned before reaching the dig made every R site look taken, so no room was
  ever dug.
- Placement must not back off exponentially: early `no_space` refusals while a room is still being dug kept beds
  unplaced for weeks on LT08.

### Crises (`fort/crisis.py`)

- **Moods:** for a dwarf in a strange mood without a claimed workshop, build the workshop its skill claims if no
  idle one exists (at most two of a type).
- **Hostiles:** a shelter burrow over the largest underground area, the civilian alert when hostiles come within
  60 tiles of the wagon, a squad (a third of the citizens, up to 8) equipped with what exists, attacking parties it
  can match, and standing down and lifting the alert when the map is clear.
- **Food emergency** (edible food below 2 per citizen): a Butcher's shop, then slaughter one adult tame animal
  every 2 days, keeping a female of each race and never a pet.

### The advisor (`fort/advisor.py`, `fort/knowledge.py`)

One chat call per consultation: a system prompt with the scoring order and the DF facts that matter (about 1,000
tokens), and a brief with the task, goal, a summary of the fort, the problems, what the autopilot handles, steps
that keep failing, its own last calls and recent harness notes. `tool_choice: auto`, temperature 0.2, up to 4 tool
calls, from an allowed set: build_workshop, build_farm, add_order, add_manager_order, place_furniture, make_zone,
assign_zone, slaughter, create_squad, equip_squad, squad_order, create_burrow, civilian_alert, build_door and
lock_door. Cancelling orders, digging, appointing and plugins are left to the playbook. It stops at 85% of the
game's credits. A call costs about 4.8k prompt tokens, so it spends far less than the budget.

## How it was tested

Environment: macOS on Apple Silicon, Docker Desktop with Rosetta, DF 53.16 + DFHack 53.16-r2, the public forts
`.yukon/setup.sh` builds (labs on seeds 2001/2002/2005, MY1 day-120 forts, OP1 seed 12345).

- **Fast loop:** the game server image run alone with its API on a loopback port, and the harness run on the host
  against it. This isn't the official stack, but it plays the same server and the same forts.
- **Scoring:** the repo's own scorers (`bench/outcomes.py` for O, `bench/predicates.py` for the lab predicates) on
  each game's artifacts.
- **Full-stack check:** `runner/dfbench local run` (harness, gateway and game containers) on LT01.
- **Model for local runs:** GLM-5.3-Flash wasn't available to me, so local model calls used a stand-in
  (GLM-4.7-Flash) behind the local gateway. Most measurements below are with the advisor off
  (`FORT_NO_ADVISOR=1`) and measure the playbook alone.

## Results (local, public forts, one game per row: not official, high variance)

| task | fort (k) | advisor | outcome O | lab partial | notes |
|---|---|---|---|---|---|
| LT01 drought | 2001 (0) | off | 65.0 | 1.00 (pass) | 65 drinks brewed in W; food fell in W (supply 0.53) |
| LT01 drought | 2001 (0) | on, full stack | n/a | 1.00 (pass), z 1.03 | 2 advisor calls, $0.0014; 0.33 wall-hours per game-year |
| LT02 rescue | 2001 (0) | off | 69.8 | 1.00 (pass) | Still and planted farm built; drink and food every day of W |
| LT02 rescue | 2002 (1) | off | n/a | 1.00 (pass) | |
| LT03 mood | 2001 (0) | off | 100.0 | 1.00 (pass) | Craftsdwarf's workshop claimed, artifact made, dwarf sane |
| LT08 migrants | 2001 (0) | off | 61.7 | 1.00 | 49 beds for 46 citizens; drink 510 at H vs 511 at A |
| LT08 migrants | 2002 (1) | off | n/a | 0.999 | 48 beds for 47; drink 506 vs 508 |
| MY1 hand-over (lean) | 2001 (0) | off | 95.8 | n/a | no deaths, supply 1.0, wellbeing 1.0, beds 1.0, dining 0.67 |
| OP1 full year | 12345 (0) | off | 12.4 | n/a | 3 deaths + 1 insane: see below |

LT08 iterations (fort 2001): 0.873 (beds 27/46: placement backed off while the room was dug) -> 0.859 -> 0.893
(beds first, bigger orders, 3 Carpenters) -> 0.974 (scaled Carpenters) -> 1.00 (smaller plant reserve on lab
tasks, so brewing continues through the window).

### What went wrong on OP1

The OP1 public fort (seed 12345) is where this harness is weakest, and the reason isn't the economy: supply scored
1.0 there.
- In two early 40-60 day tests a dwarf was killed by an alligator from the river: once the fisherdwarf while
  fishing, once the planter. Wildlife isn't flagged hostile, so neither the tripwires nor `squad_order attack` can
  respond.
- In the full-year game the woodworker's stress category fell to 1 on day 3 and to 0 by day 121. On day 166 the
  woodworker went berserk and killed the planter; then the woodworker died, then another dwarf, and the farmer went
  melancholy on day 312. At the end 5 of 13 citizens were stressed.
- The unmet needs at the end were mostly EatGoodMeal, PrayOrMeditate, MartialTraining/Fight, CraftObject,
  AcquireObject, BeExtravagant and MakeMerry.

So wellbeing over a full year, and early stress in particular, is the open problem for OP1. MY1's forts (built by
120 days of DFHack automation) had no stressed citizens through 216 days under the same rules.

## Limitations

- Every number above is one local game on a public fort, mostly with the advisor off. DF varies a lot from game to
  game (the organisers measure about 2.7 points of run-to-run noise on the suite), and the private pool's forts
  differ from these.
- The advisor's value isn't measured yet. In the full-stack LT01 game its two calls added brew orders the playbook
  already had: harmless but redundant.
- No wildlife defence, no stress management beyond beds, dining, meals and drink, and no bedrooms: the OP1 failure
  modes above.
- Supply in the last window is often falling on lab forts with many dwarves (supply 0.53-0.64 on LT01/LT02/LT08),
  which caps their outcome score even when the predicate passes.

## Next steps

- Stress over a full year: prepared meals from meat and fish (which cost no seeds), individual bedrooms for the
  most stressed dwarves, squad training for MartialTraining, crafts work for CraftObject; then measure on several
  OP1 games.
- Wildlife: keep the fisherdwarf off the river where dangerous wildlife is known (for example by drafting them
  into a squad stationed indoors), and measure the death rate over several OP1 games.
- Food at the end of open play: more farm plots as seeds allow, fish and meat, so the final-window slope is flat
  or rising.
- An ablation of the advisor (on vs off) over several games per task.

## Reproducing

```sh
.yukon/setup.sh                                            # DF images and public forts
runner/dfbench local run --harness submission/ --task scenarios/season0/lt01-drought.json
runner/dfbench local run --harness submission/ --task scenarios/season0/my1-handover-lean.json
```
Set `FORT_NO_ADVISOR=1` in the harness environment to run the playbook without model calls.
