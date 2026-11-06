# What success means in fortress mode, and how it is scored

This document defines the per-game outcome score O and its gates (`bench/outcomes.py`; the recorder fields are in
`outcome.lua`). `SCORING.md` builds the season's suite score on it.

## Why

Credited production, even with diminishing returns (`bench/dr.py`, score v3), scores an intermediate state: the
value of items the agent's orders made. A player doesn't win Dwarf Fortress by making things. They win by keeping a
fort alive, supplied, sane and growing, and DF tracks its own milestones for that. This document:

- defines success as **outcomes** of play;
- grounds each outcome in DF 53.x mechanics, with the memory fields that measure it (each one read in game);
- proposes a **gated** score in place of a weighted sum;
- maps the lab tasks onto the outcomes;

Sources:
- DF wiki main namespace, which is the v50+ text. The `DF2014:` pages describe 0.47 and give different numbers.
- df-structures and DFHack at tag `53.16-r2`.
- `research/failure-modes.md`.
- In-game probes on `scenarios/snapshots/scripted-y1` (DF 53.16, DFHack 53.16-r2, image `yukon-df:main-543ec1d19`).

DS = `https://github.com/DFHack/df-structures/blob/53.16-r2/`.

---

## 1. Outcome dimensions

### 1.1 Survival

**What it is:** citizens alive, and the fort not lost.

**DF mechanics:**
- Death incidents persist in the save (`world.incidents.all`), so a snapshot carries its own dead.
- `plotinfo.tasks.total_deaths` and `total_insanities` (DS `df.report.xml`, `entity_activity_statistics`) are
  fort-lifetime counters.
- The game ends at zero citizens (`plotinfo.game_over`; `game_state` / `end_cause_type`).

**Measured:**
- Deaths during the run are `score.lua`'s `citizen_deaths` at the end minus the same at the start (as before).
- **New:** the recorder keeps a **citizen ledger** (`cit_log`). Every citizen it sees gets
  `kind = start | migrant | born`. When a citizen leaves the list it is classified as `gone = died | insane | left`
  by its unit (`dfhack.units.isDead`, or `unit.mood` ∈ {Melancholy, Raving, Berserk, Traumatized}).
- **Finding: `score.lua` misses some deaths.** On LT04 noop (in game, 2026-10-13) a stressed dwarf went berserk and
  was killed on day 1. `citizen_deaths` stayed 0, because the victim was no longer `isOwnGroup` when it died. The
  ledger recorded `died`.
  - The lab predicates that read `citizen_deaths` share this blind spot. LT04's "Δdeaths == 0" clause passed on
    that run.
- **Fixed in `SCORE_VERSION` 5:**
  - `score.lua` also counts Death incidents whose victim is in the recorder's ledger.
  - The ledger re-labels an `insane` citizen who later dies as `died`.
  - `bench/outcomes.run_deaths` (used by `outcomes.py` and every lab predicate) takes the largest of `score.lua`'s
    count, the ledger's deaths and the `CITIZEN_DEATH` announcements in `ev`. The announcements are the fallback for
    runs recorded before the ledger.
  - Checked in game on LT04 noop, k = 1 of 3 short runs: one citizen died and one went insane and then died. Fixed
    `score.lua` reports 2, matching the 2 `CITIZEN_DEATH` announcements.
  - The ledger's re-label is checked in code only: the one later run without a death had an insane citizen still
    alive, correctly `insane`.

**Fort lost:** no citizens at H.

### 1.2 Sustainability: drink and food

**What it is:** a working supply system, not a stockpile.

**DF mechanics** ([Food](https://dwarffortresswiki.org/index.php/Food), [Thirst](https://dwarffortresswiki.org/index.php/Thirst),
[Alcohol](https://dwarffortresswiki.org/index.php/Alcohol)):
- Hunger and thirst counters rise 1 per tick. Each meal or drink takes 50,000 off.
- Dwarves drink about 5 times a season (about 20 a year) and eat about 2 units a season (about 8 a year).
- Dehydration kills at 75,000.
- One brew job makes 5 drinks.
- The harness counts stock as `items.other.DRINK` and `ANY_GOOD_FOOD` stack sizes. The same counts are in
  `plotinfo.tasks.food.{drink,total}`.
- **Since `SCORE_VERSION` 6 the score's food count is edible items only** (`score.lua`, `recorder.lua`): of
  `ANY_GOOD_FOOD`, the item types FOOD, MEAT, FISH, CHEESE, EGG, PLANT and PLANT_GROWTH, not rotten. Seeds
  (planted ones too), empty bags and raw fish no longer count; on MY1 fort 2001 they were about 20 of 66, and recorded
  food never reached 0 while dwarves starved (`runs/s0-compute-2026-10-23`). Since obs schema 8 the observation's
  `food_edible` is this same count (`food_any_good` keeps the old `ANY_GOOD_FOOD` total).

**Measured:**
- Daily `drink` and `food` (existing samples).
- Over the **final stretch F** (the hands-off window where the task has one, else the last quarter of the run,
  7–28 days):
  - **coverage**: the share of days with stock > 0;
  - **projected days left**: `T = stock_H / decline`, where decline is minus the least-squares slope of the daily
    stock over F. `T` is infinite if the stock is flat or rising.

Why this resists stockpiling:
- A big stock that is draining shows a positive decline. It is credited only as far as it lasts.
- Stock above what lasts `T* = 336 d` (one DF year) earns nothing more.
- A working brewery holds the slope at ≥ 0 at any stock level.

### 1.3 Wellbeing

**What it is:** stress, breakdowns, insanity, moods and needs.

**DF mechanics** ([Stress](https://dwarffortresswiki.org/index.php/Stress), [Mental breakdown](https://dwarffortresswiki.org/index.php/Mental_breakdown),
[Insanity](https://dwarffortresswiki.org/index.php/Insanity), [Strange mood](https://dwarffortresswiki.org/index.php/Strange_mood),
[Personality need](https://dwarffortresswiki.org/index.php/Personality_need)):
- **Stress.** `unit.status.current_soul.personality.stress` runs from −100k to 100k. `longterm_stress` (since
  v50.01) runs from −50k to 120k. The warnings are stressed at 25k, haggard at 50k and harrowed at 100k (long-term).
- **Stress categories.** `dfhack.units.getStressCategory` cuts at 50k / 25k / 10k / −10k / −25k / −50k, giving 0
  (most stressed) to 6 (DFHack `Units.cpp` L2174). Checked in game: 11,700 → 2, −8,520 → 3, −17,321 → 4, −37,863 → 5.
- **Breakdowns.** These are tantrum, depression and obliviousness: `unit.counters.soldier_mood` ∈ {Tantrum,
  Depressed, Oblivious} (enum `soldier_mood_type`; `MartialTrance` and `Enraged` are combat states). They need both
  short- and long-term stress to be high.
- **Insanity.** Repeated breakdowns lead to insanity (`unit.mood` Berserk / Raving / Melancholy), and a harrowed
  dwarf who sees a death goes insane.
- **Strange moods.** These need ≥ 20 eligible dwarves. The dwarf goes insane after 50,000 ticks (41.7 d) waiting for
  an item (`unit.job.mood_timeout`). Success makes an artifact (`plotinfo.tasks.num_artifacts`; announcements
  `STRANGE_MOOD`, `MOOD_BUILDING_CLAIMED`, `ARTIFACT_BEGUN`, `MADE_ARTIFACT`).
- **Needs.** Each of `personality.needs[]` has a `focus_level`: −1,000 to −9,999 is "unfocused", ≤ −10,000
  "distracted" and ≤ −100,000 "badly distracted". `flags.has_unmet_needs` is set below −999.
  - Overall focus is `current_focus / undistracted_focus`, shown as "Distracted" at 61–80% and "Badly distracted"
    at ≤ 60%. It changes effective skill by up to ±50%.
- **Breakdown announcements:** `CITIZEN_TANTRUM`, `BERSERK_CITIZEN`, `CITIZEN_LOST_TO_STRESS`, `POSSESSED_TANTRUM`
  (enum names checked in game).

**Measured (new, daily `wb`):**
- stress min/median/p90/max and long-term stress median/p90/max;
- counts at ≥ 25k / 50k / 100k for both;
- the category histogram;
- citizens in each breakdown state, and in each insane mood;
- focus median and min, and the number of citizens with focus ≤ 80%;
- unmet needs (focus_level ≤ −1,000) over all needs.

The per-day announcement histogram `ev` and the `moods` list already existed.

### 1.4 Security

**What it is:** raids and sieges survived, and losses relative to the threat.

**DF mechanics** ([Siege](https://dwarffortresswiki.org/index.php/Siege), [Ambush](https://dwarffortresswiki.org/index.php/Ambush),
[Difficulty](https://dwarffortresswiki.org/index.php/Difficulty)):
- Ambushes and thieves come from the start.
- Sieges need population 80 (normal enemies) and at least 2 raids first. After that, 25% of invasions are sieges.
- Enemy triggers are population 20/50/80/110/140 and created wealth 5k/25k/100k/200k/300k.
- Undead sieges can come at any time.
- **There is no siege announcement type.** Invasions are in `plotinfo.invasions.list[]` (`invasion_info`:
  `civ_id`, `size`, `mission`, `flags.active` / `flags.siege`, `created_year`).
- `tasks.invaders_repelled` counts repelled invasions.

**Measured (new):**
- `prog.invasions` (n, active, siege) each day, and one row per invasion in `S`. In game, `thief-raid-y1`'s kobold
  raid is `{active: true, siege: false, civ_id: 16, mission: 0}`.
- Threats spawned by scenario setup (`invade.lua`) are not in that list. They are counted from the
  `invaders_killed` / `invaders_alive` unit flags, which already existed.

### 1.5 Growth

**What it is:** population sustained as migrants arrive, and capacity per capita.

**DF mechanics** ([Immigration](https://dwarffortresswiki.org/index.php/Immigration), [Zone](https://dwarffortresswiki.org/index.php/Zone),
[Dining room](https://dwarffortresswiki.org/index.php/Dining_room), [Thought](https://dwarffortresswiki.org/index.php/Thought)):
- Two hard-coded waves come in year 1. Later waves are sized by the created wealth the last caravan reported home,
  up to `d_init.dwarf.population_cap` (200).
- Dwarves without a bed sleep on the ground, and that is a negative thought. Eating without chairs or tables is
  negative too.
- Dining needs a chair with an adjacent table per diner.
- Bedrooms are `Bedroom` civzones with an `assigned_unit_id`.

**Measured (new):**
- `pop`: arrived, born, died, insane and left, cumulative from the ledger. LT08 automation in game: 19 → 50
  citizens, `arrived` 31.
- `home`:
  - placed beds;
  - bedrooms and bedrooms owned by a citizen;
  - dining tables, chairs and seats, from the zone's `contained_buildings` (it matches the box test in game);
  - offices and meeting areas;
  - site locations (temple, tavern, ...: abstract buildings of the site).

### 1.6 DF's own progression

**Fortress rank** ([Fortress](https://dwarffortresswiki.org/index.php/Fortress#Nomenclature), [Difficulty](https://dwarffortresswiki.org/index.php/Difficulty)):
- Each rank needs its population **and** either its created or its exported wealth.

| Rank | Population | Created ☼ | Exported ☼ |
|---|---|---|---|
| Hamlet | 20 | 5,000 | 500 |
| Village | 50 | 25,000 | 2,500 |
| Town | 80 | 100,000 | 10,000 |
| City | 110 | 200,000 | 20,000 |
| Metropolis | 140 | 300,000 | 30,000 |

- Hard economy multiplies the wealth requirements by 5.
- In memory: `plotinfo.fortress_rank`, plus `progress_population` / `progress_trade` / `progress_production` (DS
  `df.plotinfo.xml` L824-827).
- **Checked in game:** LT08 automation went from rank 0 to 1 (Hamlet) around day 10, when population passed 20 with
  created wealth already above 5,000. `progress_population` became 2 and `progress_production` 1.

**Land holders** ([Noble](https://dwarffortresswiki.org/index.php/Noble), [Baron](https://dwarffortresswiki.org/index.php/Baron)):

| Title | Population | Created ☼ | Exported ☼ |
|---|---|---|---|
| Baron | 20 | 100k | 10k |
| Count | 20 | 200k | 20k |
| Duke | 20 | 300k | 30k |

- The liaison offers the title, and you nominate a citizen.

**Monarch** ([Monarch](https://dwarffortresswiki.org/index.php/Monarch)):
- Needs a duchy with a living duke and enough happiness. The wiki gives both City and Metropolis as the rank.
- In memory: `plotinfo.king_arrived`.
- Then Mountainhome, an endgame quest.

**Positions:**
- The expedition leader appoints manager, bookkeeper, broker, chief medical dwarf, militia commander and sheriff.
- At population 50 a **mayor** is elected, and the captain of the guard and dungeon master open up.
- Site positions are on the `plotinfo.group_id` entity (`SiteGovernment`). Land holders and the monarch are on the
  civ entity. `dfhack.units.getNoblePositions(u)` returns both for a unit.
- Measured as `prog.positions`, the position codes citizens hold. `scripted-y1`: `EXPEDITION_LEADER, MANAGER`.
- Announcements: `ELECTION_RESULTS`, `LAND_GAINS_STATUS`, `LAND_ELEVATED_STATUS`, `NOBLE_ARRIVAL`,
  `MONARCH_ARRIVAL`, `FORT_POSITION_SUCCESSION`.

**Wealth:** `plotinfo.tasks.wealth.{total, weapons, armor, furniture, other, architecture, displayed, imported,
offered, exported}`. Created wealth is the first six summed.

**Caveat:** progression can be bought. Created wealth counts furniture spam and felled logs (`score.lua`'s comments:
243 logs were 729 of 754☼). That is why it is only scored behind the other tiers, and only on year-plus horizons.

---

## 2. The gated score

Each tier is a sub-score in [0, 1], and **a tier counts only as far as the tiers below it hold**:

```
O = 100 · (s1 + s1·s2 + s1·s2·s3 + s1·s2·s3·s4) / 4
```

A fort that loses everyone scores 0. A fort that survives but runs dry gets at most about 25 plus a little.
Wellbeing only pays on a supplied fort, and growth only on a supplied and sane one. This is a soft lexicographic
order, not a weighted sum: a weighted sum lets surplus in one dimension buy off failure in another.

| Tier | Sub-score | Formula |
|---|---|---|
| s1 survival | `s_surv · s_sec` | `s_surv = 0` if the fort is lost, else `0.5·max(0, 1 − X/3) + 0.5·max(0, 1 − X/C0)`, with X = deaths during the run (the larger of `score.lua` and the ledger) + citizens lost to insanity, and C0 = citizens at the start. The first term punishes the first few deaths, and the second separates a wipe-out from a partial loss (the `goblin_raid_v2` shape). `s_sec` = 1 with no threat or a threat that is over at H; 0.5 while raiders are still on the map at H |
| s2 supply | `min(drink, food)` | each resource scores `0.5·coverage_F + 0.5·min(1, T / 336)` |
| s3 wellbeing | `w_calm · w_events` | `w_stress = 1 − mean_F(stressed / citizens)`, with stressed = DFHack category ≤ 1, i.e. stress ≥ 25k. `w_calm = w_stress` since `SCORE_VERSION` 7 (2026-11-05): the share of needs met at H (`inputs.needs_met`, formerly half of `w_calm`) is reported, not scored, because about half the needs can't be met through the game API and the share steps with time since arrival rather than with play (`runs/s0-wellbeing-needs-2026-11-05`). `w_events = max(0, 1 − E / max(3, C̄/10))`, with E = tantrums + berserks + lost-to-stress + possessed tantrums + citizens seen insane (failed moods and stress insanity) |
| s4 growth | `housing`, or `0.5·housing + 0.5·progression` when H ≥ 336 d | `housing = mean(min(1, placed beds / citizens), min(1, 2·dining seats / citizens))` at H. `progression = min(1, steps / 2)` (§2.2) |

**Gates and the tier reached.** The headline next to O is the number of consecutive gates passed (0–4):

- **G1 survive:** nobody died or went insane, the fort stands, and no raider is left on the map.
- **G2 supply:** drink and food were in stock every day of F, and `T ≥ 336 d` for both.
- **G3 sane:** no breakdown event or insane citizen, and at most 10% of citizen-days in F stressed.
- **G4 grow:** placed beds ≥ citizens and dining seats ≥ citizens / 2 at H. On horizons of 336 d or more it also
  needs a progression step.

Tier is a strict reading ("a tier-2 fort is safe and supplied"). O is the continuous score for statistics.

**Parameters** (`bench/outcomes.py`):

| Parameter | Value | Note |
|---|---|---|
| `T_STAR` | 336 d | One DF year of supply in hand counts as sustained. At 84 d (one season), a 60 d embark fort living off its wagon stock nearly passes: held-out 60 d noop scores 69.9 vs scripted 75.0 (55.0 vs 72.8 at 336 d). |
| `STRESSED_OK` | 10% | for G3 |
| `F` | the hands-off window, else the last quarter (7–28 d) | |
| breakdown scale | `max(3, C̄/10)` | so a 100-dwarf fort isn't zeroed by 3 tantrums a year |

### 2.1 Why this resists the gaming we've seen

| Exploit seen | What credited / DR did | What the outcome score does |
|---|---|---|
| Furniture and order spam (fort-gym's 26 chairs) | Counted at full value up to 2 per citizen per type (DR), then at 10% | Nothing counts items. Only **placed** beds and **zoned** dining seats count, capped at per-capita need, and only behind three other tiers |
| Drink stockpiling before the window | DR caps drink at 2× consumption, but the stock is still credited when it is made | A draining stock is credited only through its projected days left. A big stock past one year earns nothing, and a working system earns as much as a stockpile |
| Queueing barrels or bins with nothing to fill | DR barrel cap | Ignored |
| Orders that never produce (the ≥ 20-citizen stall) | 0 credit | Shows up where it matters: drink runs out in F |
| Brewing for credit while dwarves starve or tantrum | Not seen at all | s2 takes the min of drink and food, and s3 breakdowns zero wellbeing |
| Progression bought with created wealth | n/a | Gated last and scored only on year-plus horizons. Reported separately |

Residual risks:
- Housing could be met by dumping beds into one dormitory. DF accepts that as sleeping in a bed, so it isn't an
  exploit in the game's terms.
- The decline estimate is noisy over a 7-day F (LT03), where a brew batch on the last day reads as "infinite". Use
  coverage there.

### 2.2 Progression rule (decision 3)

Progression is scored only on horizons of at least 336 d, and full credit takes `PROG_CAP` = 2 steps
(`bench/outcomes.progression_steps`):

| Step | Weight |
|---|---|
| each fortress rank gained (`plotinfo.fortress_rank`, 1 Hamlet … 5 Metropolis) | 1 if `wealth.exported` at H reaches that rank's export threshold (500 / 2,500 / 10k / 20k / 30k☼), else 0.5 |
| each new land-holder title held by a citizen (BARON, COUNT, DUKE and the female forms) | 1 if exports reach 10k / 20k / 30k☼, else 0.5 |
| a new MAYOR (elected at 50 citizens) | 1 |
| the monarch's arrival (`king_arrived`) | 1 |

- DF grants a rank or title on population plus **either** created or exported wealth, so the memory doesn't say
  which route was taken.
- The rule weights by whether the export route was met at H. A step reached only on created wealth (furniture,
  logs) counts half, so two steps bought with created wealth earn half credit.
- The thresholds are the normal-economy defaults. Hard economy multiplies them by 5 (`custom_difficulty`, not yet
  recorded).

---

## 3. Recorder fields (scoring side, never in the observation)

These are added by commit `f850070ed`: `outcome.lua`, which `recorder.lua` and `final_state.lua` load. They don't
change the harness key (`tools`, `obs`, `loop` and `manual` are unchanged). They change `score_hash`
(`SCORE_VERSION` 5 after the merge with v2-harness, whose 4 is the LT01/LT02/LT05 predicates).

| Field (daily sample unless noted) | Source | Checked in game |
|---|---|---|
| `wb.stress{min,med,p90,max}`, `wb.lt_stress{med,p90,max}`, `wb.stress_ge[25k,50k,100k]`, `wb.lt_stress_ge[...]` | `personality.stress` / `longterm_stress` | LT04 noop: p90 rises from 13k to 60k after setup; `lt_stress_ge` [4,4,4] |
| `wb.stress_cat[0..6]` | `dfhack.units.getStressCategory` | scripted-y1 `[0,0,3,7,8,1,0]` |
| `wb.breakdown{Tantrum,Depressed,Oblivious,Enraged}` | `unit.counters.soldier_mood` | LT04 noop day 1: one each of Tantrum, Depressed, Oblivious |
| `wb.insane{Melancholy,Raving,Berserk,Traumatized}` | `unit.mood` | (no insane citizen was alive at a sample in the checks) |
| `wb.focus{min,med,distracted}`, `wb.needs{n,unmet}` | `current_focus / undistracted_focus`; `needs[].focus_level ≤ −1000` | scripted-y1 focus med 103%, 188 of 407 needs unmet |
| `home.{beds_placed, bedrooms, bedrooms_owned, dining_zones, dining_tables, dining_chairs, dining_seats, offices, meeting_areas, locations}` | `buildings.other.BED`, `ACTIVITY_ZONE` (`civzone_type`, `assigned_unit_id`, `contained_buildings`), `world_site.buildings` | LT08 automation: 19 beds, 1 dining zone with 3 tables and 3 chairs, 1 office |
| `prog.{fortress_rank, progress_population, progress_trade, progress_production, king_arrived, game_over}` | `plotinfo` | LT08 automation: rank 0 → 1 |
| `prog.{wealth_created, wealth_total, exported, imported, offered}` | `plotinfo.tasks.wealth` | scripted-y1: created 4,727, exported 0 |
| `prog.positions` | `getNoblePositions` over citizens | `EXPEDITION_LEADER, MANAGER` |
| `prog.{deaths_total, insanities_total, artifacts_total, invaders_repelled, migrant_wave_idx}` | `plotinfo.tasks` | LT04 noop: `insanities_total` 0 → 1; LT03 automation: `artifacts_total` 0 → 1 (with `STRANGE_MOOD`, `MOOD_BUILDING_CLAIMED`, `ARTIFACT_BEGUN`, `MADE_ARTIFACT` in `ev`) |
| `prog.invasions{n,active,siege}`; `S.invasions[]` (id, civ_id, active, siege, undead, size, mission, created_year) | `plotinfo.invasions.list` | thief-raid-y1: 1 active, not a siege |
| `pop{arrived,born,died,insane,left}`; dump `cit_log[]` | the recorder's ledger | LT08: 31 migrants; LT04: the berserk death |
| `S.citizens[].{focus, needs_unmet, positions, soldier_mood, age}` | as above | scripted-y1 |
| `S.wb`, `S.home`, `S.prog` (and the same in `S0`) | outcome.lua at start / end | all three runs |

**Cost:** one pass over citizens and zones per day, under 1 ms at 50 citizens. A 3-year run adds about 1 KB per
day to `daily.json`.

**Not measured:**
- Room value (DF computes it per zone; there is no cheap reader).
- Mandate and demand satisfaction (`NEW_MANDATE` and the others are counted in `ev`).
- Caravan trade value (`plotinfo.caravans[]` has `import_value` and `export_value_total`, a candidate).

---

## 4. Which dimensions each task should score

The outcome score is the same formula everywhere, so play is judged the same way on every task. The task's
predicate stays as its pass/fail. The columns say which tiers the task is **about**: where a good and a bad policy
should differ. The others are guard rails.

| Task | Survival | Supply | Wellbeing | Security | Growth / progression | Current predicate vs outcomes |
|---|---|---|---|---|---|---|
| LT01 drought | guard | **core** (drink in W, days left) | guard | – | – | The predicate is drink > 0 in W, end ≥ 1 per dwarf, and credited drink in W. Outcomes add the projection (a W-end stock that is falling fast fails G2) and the food min |
| LT02 rescue | guard | **core** | **core** (starts stressed) | – | guard | v1 rewarded credited value ≥ 300 and a built Still and farm. **rescue_v2** (score_version 5) replaces the credited clause with "food > 0 every day of W", next to drink > 0 every day of W. Partial `0.4·drink days in W + 0.3·food days in W + 0.15·Still + 0.15·planted farm` |
| LT03 mood | guard | guard | **core** (artifact vs insanity) | – | – | Close to an outcome already (artifact made, dwarf sane). Outcomes add the death ledger |
| LT04 stress | **core** | guard | **core** | – | guard | Breakdowns after day 7 and stressed ≤ 1. Outcomes see the berserk death the predicate's Δdeaths misses |
| LT05 goblin raid | **core** | guard | guard | **core** | – | `goblin_raid_v2` is survival-only, as here. Outcomes add "raiders gone at H" |
| LT06 thief | guard | – | – | **core** | – | Theft is not in the outcome score: stolen goods are a loss, but not of life, supply or sanity. Keep the predicate |
| LT07 flood | **core** | guard | guard | – | – | Not built. Drownings are survival; flooded fraction stays in the predicate |
| LT08 migrant surge | guard | **core** | guard | – | **core** (beds and dining per capita) | Closest to outcomes already. Outcomes replace "beds ≥ citizens" with beds plus dining, and add the projection |
| LT09 / LT10 embark | guard | **core** | guard | – | **core** | **embark_production_v2** (score_version 5, now implemented as `predicates.lt09`): Δdeaths 0; drink and food > 0 every day of W (in place of the spec's credited-in-W clause); drink_H ≥ 2·citizens; Still, Kitchen, Carpenters and ≥ 2 planted plots. Not yet validated (no 120 d runs exist) |
| OP1 start-year | **core** | **core** | **core** | **core** | **core** (with progression) | Headline was credited value. Outcomes judge the year end. At 336 d none of the references reaches a progression step (old runs have no `prog` anyway) |

Adopted (decisions 1 and 6):
- O and the tier are the **headline** on OP1 and the long-horizon arm, and `analyze.py`'s normalized score is on O.
  Credited value (gross and DR) are info columns.
- On lab tasks, pass@k on the predicate stays the score, with O next to it.
- LT02's and LT09's credited clauses are now supply-over-W clauses (`bench/predicates.py`). The task JSONs (the
  predicate names `rescue_v2` / `embark_production_v2`, and LT02's goal text, which still mentions credited value)
  are edited by the v2 agent: requested through the orchestrator. That is a suite minor.

---

## 5. Implementation

- `bench/outcomes.py`:
  - `score_run(row, daily, final)` returns `outcome`, `tier`, `gates`, `s{survival,supply,wellbeing,growth}`, the
    parts and inputs, and `missing` (inputs a run predates).
  - `for_run(dir)`, and the CLI (`--json`, `--groups`).
- `analyze.py`:
  - **headline** `outcome` per arm, with CIs and the permutation p vs noop;
  - the normalized score `(O − noop) / (scripted − noop)` on outcome alone;
  - the tier and sub-scores as outcome detail;
  - the scenario's metrics, credited value and DR as info.
- `bench/summarize_run.py` adds an outcome line (`outcome 35.2 (tier 0/4; survival 0.81, ...); gates ....`) to the
  digest, and `outcome` and `tier` columns to `--compare`.
- `scripts/rescore_outcomes.py` writes the back-computation (`runs/outcome-rescore-2026-10-13/table.md`,
  `rescore.json`) and the `T_STAR` = 84 / 168 / 336 comparisons (`sensitivity.md`). DR comes from `bench/dr.py`.

---

