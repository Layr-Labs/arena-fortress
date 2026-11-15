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

- **My own earlier submissions of this harness**: 7ed9f09a and 39568f5e (failed by the early judge before any game,
  PRs #23 and #96) and 252898ac (the same harness, which played stage 1: labs z 0.97 / 1.13 / 1.00 / 0.88 for
  LT01 / LT02 / LT03 / LT08, MY1 O 82.3). This submission is that harness with the changes in "Changes since the
  first archive" below. All three are declared in `dependencies.json`.
- **i34-9's promoted submission fa9c13cc** (the `main` at the time of this revision), declared: its endgame supply
  step was read, and the idea is reimplemented in `fort/playbook.py` (`endgame_orders`): from about two months
  before an open-play horizon, a second daily brew order with a high cap above a plant reserve, an extra barrel
  order and a meal order from surplus food; and in `fort/crisis.py`, butchering from 4 food per citizen instead of
  2 in that period. No code was taken. fa9c13cc credits the brewing idea to **mpjunior92's note (0bc9b753)**, also
  declared.
- **The organiser's plain baseline.** `submission/dfbench_client/` is byte-identical to the organiser's
  `baseline/dfbench_client/` (the stdlib client for the game API and the gateway), used unchanged. The baseline's
  `plain/` package (loop, prompt, guards) is not used. This harness does not start from the promoted `main`: apart
  from the idea above, nothing is taken from another participant's submission.
- **The repo's reference policies** (`policies.py`: `Scripted`, `Automation`) were read for orientation: which
  steps they take and in what order (manager, plugins, workshops, standing orders, an underground farm, the
  manager's office rule from about 20 citizens). They speak the frozen v2 tool API with raw coordinates and DFHack
  commands, so no code was taken from them; the v3 site-based layout here is new.
- **The game API manual** (`gameapi/manual/MANUAL.md`, served by `GET /task`) for tool semantics, site kinds and the
  DF facts the tools touch, and `docs/SUCCESS.md` / `SCORING.md` for what the outcome score rewards.
- **DF wiki, "Strange mood"**: which workshop a mood claims for each moodable skill (a woodcrafter claims a
  Craftsdwarf's workshop, not a Carpenter's workshop). This mapping is in `fort/crisis.py`.

## Changes since the first archive

The first archive to play (252898ac, stage 1 only) scored labs z 0.97 / 1.13 / 1.00 / 0.88 (LT01 / LT02 / LT03 /
LT08) and MY1 O 82.3, with 6 of 8 MY1 games stopping at tier 1 (supply) and about 685 of 954 actions per game-year
rejected. This revision changes:

1. **Endgame supply (open play).** From 60 days before the horizon on MY1/OP1, a second set of standing orders:
   brewing to a high cap above a plant reserve, extra barrels, and meals from surplus food; butchering starts at 4
   food per citizen instead of 2 in that period (`playbook.endgame_orders`, `crisis.food_steps`). The scored final
   stretch wants drink and food flat or rising, and the everyday drink target (6 per citizen + 60) made drink fall
   there. The idea is i34-9's / mpjunior92's (see above).
2. **Standing orders follow the fort's size.** Thresholds were fixed when an order was made (at 7 citizens on OP1).
   Each standing order now has a key and a signature; when the fort grows by a step of 4 citizens, the old order is
   cancelled and the new one added on the next cycle (`playbook.standing`), never within 5 days of a hands-off
   window. A second brew order brews from any plant when drink falls below 3 per citizen + 10.
3. **Zones that fit.** `make_zone` takes a box of at most 20x20, and a level's A site is the bounding box of
   everything dug there: a second living room or the manager's office beside the first made it 24 wide, so every
   dormitory/dining/meeting zone was refused (`w must be an integer in [1,20]`). Now one living room per level, the
   office goes on the farm level, and a level whose box can't be zoned isn't furnished (`layout.zonable`).
4. **No retrying a full level.** Table/chair placement on a level that answered `no_space` was retried every day:
   most of the rejected actions. Such a level is marked full and the next level is used (`layout.after`).
5. **Farms stay off the office.** A farm plot built on the office room would have taken it.
6. **Food on open play: meals, meat, and drink first.** On fresh embarks the farms are seed-limited, not
   plot-limited: the seed count includes seeds already planted, and on OP1-like forts every plump helmet seed was
   in the ground (about 30 of 72 tiles planted), which feeds 10-15 dwarves; the forts reach about 20 by autumn.
   Raw plants rot and meals keep, so the kitchen now keeps about four meals per citizen while there are two food
   per citizen; butchering starts at 3 food per citizen on open play; and the kitchen only cooks while drink is
   at least 3 per citizen + 10, because the kitchen and the still compete for the same plants and drink lost
   that race (`playbook.order_steps`, `crisis.food_steps`).
7. **The advisor has no order tools.** `add_order` and `add_manager_order` were removed from its allowed tools:
   an extra order upsets the plant balance above. It keeps workshops, farm plots, furniture, zones, squads,
   burrows, alerts, doors and slaughter.

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
- **Standing orders** (repeating daily, run only while their conditions hold; re-issued when the fort grows by a
  step of 4 citizens, `standing`):
  - barrels while empty barrels are few and logs exist;
  - brewing while drink is below a target and brewable plants are above a reserve kept for eating. Open play
    targets about 6 drinks per citizen + 60 and keeps half the citizen count in plants; lab tasks with a
    hands-off window brew whenever plants allow, because their predicates want drink held or rising through the
    window;
  - a second brew order from any plant while drink is below 3 per citizen + 10;
  - cooking while meals are below 4 per citizen, edible food is at least 2 per citizen and drink at least 3 per
    citizen + 10 (meals keep, raw plants rot; the still comes first);
  - from 60 days before an open-play horizon: brewing to a high cap, extra barrels and more meals (change 1).
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
- **Food emergency** (edible food below 2 per citizen on lab tasks, 3 on open play, 4 in the last 60 days of open
  play): a Butcher's shop, then slaughter one adult tame animal every 2 days, keeping a female of each race and
  never a pet.

### The advisor (`fort/advisor.py`, `fort/knowledge.py`)

One chat call per consultation: a system prompt with the scoring order and the DF facts that matter (about 1,000
tokens), and a brief with the task, goal, a summary of the fort, the problems, what the autopilot handles, steps
that keep failing, its own last calls and recent harness notes. `tool_choice: auto`, temperature 0.2, up to 4 tool
calls, from an allowed set: build_workshop, build_farm, place_furniture, make_zone, assign_zone, slaughter,
create_squad, equip_squad, squad_order, create_burrow, civilian_alert, build_door and lock_door. Orders,
cancelling, digging, appointing and plugins are left to the playbook (change 7). It stops at 85% of the
game's credits. A call costs about 4.8k prompt tokens, so it spends far less than the budget.

## How it was tested

- **Forts.** The public forts `.yukon/setup.sh` builds: lab forts on seeds 2001/2002/2005 and the MY1 day-120
  forts. For OP1 I didn't use the public OP1 fort (seed 12345, DEFAULT_FORT shrubland with alligators), because
  the private OP1 forts are fresh TEMPERATE_SOIL embarks; instead `local/op1-ts.json` (not submitted) is OP1 on
  the three fresh TEMPERATE_SOIL embarks that the MY1 forts were built from (`scenarios/snapshots/my1-d120-*.embark`).
- **Runs.** Each game: the game server image alone with its API on a loopback port and the harness on the host
  against it, advisor off (`FORT_NO_ADVISOR=1`), so the numbers measure the playbook. Batches of 12-20 games ran
  in parallel on an x86 EC2 instance (native, no emulation).
- **Scoring.** The repo's own scorers on each game's artifacts: `bench/outcomes.py` (O) and
  `bench/predicates.py` (lab predicates).

## Results (local, public forts, advisor off; not official)

OP1 on the three TEMPERATE_SOIL embarks, 12 games per variant (4 per fort), mean O:

| variant | OP1 mean O | games with supply failing |
|---|---|---|
| A: changes 1-5 | 75.0 | 7 / 12 (mostly food) |
| B: A + more meals, butcher at 3 food per citizen | 80.4, rerun 80.2 | 4-8 / 12 (mostly drink) |
| C: B + lower plant reserve for the endgame brew | 79.1 | 6 / 12 |
| D: C + cook only while drink holds (this submission) | 86.2 | 2 / 12 |

No deaths in D's 12 OP1 games; 4 of them reached Hamlet (growth 0.625).

This submission on the other tasks (one game per row unless noted):

| task | result |
|---|---|
| MY1 lean | 6 games: O 100, 100, 100, 100, 96.4, 78.6 (a badger killed the blacksmith) |
| LT01 drought | 2 games: pass, partial 1.00 |
| LT02 rescue | 2 games: pass on 2001; on 2002 alligators killed three dwarves (clause "no deaths" failed) |
| LT03 mood | 2 games: pass, partial 1.00 |
| LT08 migrants | 3 games: partial 0.975-0.981 (beds >= citizens; drink at H about 9% below drink at A) |

Rejected actions per game: 0-2 (the first archive's MY1 game had 92).

### What didn't work

- A bigger plant reserve before brewing (two plants per citizen): drink fell through the final stretch and food
  didn't improve (OP1 61-70).
- Cooking only from a large surplus, to keep seeds: raw plants rot and meals don't, so food fell faster (OP1 mean
  69, 6 games).
- A lower plant reserve for the endgame brew (variant C): no change.

## Limitations

- These are local numbers on public forts, with the advisor off. The private forts differ, and DF varies a lot
  between games of the same fort (OP1 games on one fort range from 60 to 97).
- Wildlife: dangerous animals that aren't flagged hostile (alligators, badgers) can't be targeted by the squad,
  and nothing here keeps dwarves away from them. They caused every death in these tests.
- LT08: drink at the end of the window is about 9% below its start with ~47 citizens: plants, not stills, limit
  brewing there.
- The advisor's value is unmeasured: GLM-5.3-Flash wasn't available locally, and the batches ran with it off.

## Next steps

- Wildlife: shelter civilians when a dangerous animal is near, with a time limit so food and drink stay reachable.
- Seeds: process quarry bushes, pig tails and cave wheat (their seeds come back only that way), so more crops
  than plump helmets can be grown year after year.
- An advisor on/off comparison with the real model.

## Reproducing

```sh
.yukon/setup.sh                                            # DF images and public forts
runner/dfbench local run --harness submission/ --task scenarios/season0/lt01-drought.json
runner/dfbench local run --harness submission/ --task scenarios/season0/my1-handover-lean.json
```
Set `FORT_NO_ADVISOR=1` in the harness environment to run the playbook without model calls.
