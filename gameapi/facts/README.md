# gameapi/facts: the facts layer of game API v0

This package covers the observation, the queries, the tools and the events of `docs/GAME-API.md` §5. It contains facts only:
anything that judges, summarises or advises belongs in the harness (spec §3.2). It is stdlib-only Python plus
DFHack Lua (`lua/`), and it runs inside the DF image next to DFHack, as `harness2.py` does. Each call is one
`dfhack-run lua -f gameapi/facts/lua/<script>.lua …` (plus `quickfort` and `enable` for the tools that use them).

## Module interface (what `gameapi/server` calls)

```python
from gameapi.facts import Game, DFHack, FactsError, OBS_SCHEMA, QUERIES, TOOL_NAMES, SERVER_TOOLS

g = Game(df=DFHack(df_dir=None))   # one per game; df_dir defaults to $DFBENCH_DF_DIR, else <repo>/df
g.observe() -> dict                # obs schema 8 (below); raises FactsError if the probe fails as a whole
g.query(name: str, **args) -> dict # {"ok": true, ...} or {"ok": false, "error_code", "error"[, "allowed"]}
g.tools() -> list                  # 22 OpenAI function schemas; build_workshop's enum comes from DF (cached)
g.act(tool: str, args: dict) -> dict
    # {"ok": true, "result": {...}} or {"ok": false, "error_code": str, "error": str[, "allowed": [...], "detail": str]}
g.events(since_tick: int, limit=200) -> list            # DF reports after since_tick, oldest first
g.events_page(since_tick, limit=200, since_id=None) -> {"events": [...], "dropped": n, "now": tick}
g.plugin_state() -> {"autochop": "on"|"off"|"unknown", ...}
g.refresh_sites()                  # act() calls it before resolving a site; the server never needs to
```

- **`advance_days` is the server's.** It is in `tools()` (1 to 28 days, plus `stop_on`). `Game.act("advance_days", …)`
  returns `error_code: server_tool`, because the server owns K, tripwires, hands-off and the wall cap. `SERVER_TOOLS` lists it.
- **State held per game:** site ids, which add_order call made which order (its recipe and `when` stock names), and
  each order's first-seen tick. If the game tick goes backwards (a new game from the same save), it resets.
- **Sites resolve server-side** against the current map. `act()` re-reads the site candidates before it resolves `site=…`, so a
  harness doesn't have to observe before acting. Raw `x,y,z` (and `w,h`, `z_top`) are still accepted, but not
  advertised (frozen behaviour).
- **Error codes:**
  - today's codes: `tile_hidden`, `tile_occupied`, `not_open_floor`, `not_soil_floor`, `needs_stone`, `no_material`,
    `nothing_designated`, `no_space`, `already_assigned`, `not_a_citizen`, `no_such_order`, `no_position`,
    `squad_exists`, `not_eligible`, `no_squad`, `not_a_hostile`, `no_hostiles`, `not_walkable`, `no_burrow`,
    `wrong_tile_shape`, `no_doors`, `no_such_door`, `no_such_zone`, `not_assignable`, `not_enabled`,
    `game_refused`, `missing_location`, `wrong_site_kind`, `unknown_site`, `site_used`, `room_not_dug_yet`,
    `bad_arguments`, `unknown_tool`, `internal_error`;
  - new: `server_tool`, `unknown_query`, `no_such_unit`, `not_slaughterable`.
  - Errors carry no `hint`, `valid` or `nearest_free_centre`. `allowed` (an enum's values) stays.

Shapes the organiser's reference harness reads (`docs/GAME-API.md` §3.1) are matched. `check_in_game.py` runs that
harness's observation adapter on a live schema-6 observation when it's in the checkout. The server
wraps the observation in the §3.1 envelope (`day`, `tick`, `days_left`, `game_over`, `observation`). It also
formats the advance result itself (`{"advanced_ticks", "stopped"}`), since advance_days is the server's.
`/events` is `{"events": events_page()["events"], …}`.

Tests: `python3 -m unittest discover -s gameapi/facts/tests` (37 tests, fake DF, no DF needed). In game:
`gameapi/facts/check_in_game.sh` (builds `yukon-df:s0facts-<sha>`, one container, scripted-y1). Output: `IN_GAME.md`.

## Observation: obs schema 8 (7 + `stocks.food_edible` as the score counts it, `food_any_good`, R rooms' `designated`/`dug`)

Schema 7 (2026-10-24) is schema 6 with the mood facts cut to the visible subset (the moods row below); everything
else is as in schema 6.

Schema 6 is #85's schema 5 minus interpretation, plus the facts the contract adds. Categories are the audit's
(`docs/game-api-audit.md` §b): RAW, DER (derived fact), INT (interpretation, removed), IFC (interface), PRES.

**Removed (INT/PRES, now the baseline harness's job):**

| field (schema 5) | why | replaced by (fact) |
|---|---|---|
| `administrators.manager_needs_office` | INT: a threshold measured in game (20 citizens) | `administrators.citizens`, `administrators.manager_required_office` (DF's noble raw), `manager_office {zone_id, chair}` |
| `moods[].workshop_needed` | INT: a wiki table | `moods[].job` (DF's `StrangeMood*` job type), `claimed_workshop` |
| `threats.note` | PRES | — (the metric is documented here: `dist_to_wagon` = max(\|dx\|,\|dy\|) + 3·\|dz\| from the wagon) |
| `map.free_3x3_sites_near_wagon`, `surface_soil_sites_NOT_for_starting_seeds`, `underground_soil_farm_sites`, `surface_entrances`, `underground_dug_areas`, `stair_sites`, `room_sites`, `doorways` | INT/IFC: lists under ranked, advice-bearing names | `sites[]` (below), ordered by id |
| harness2 `diagnose()`: `orders[].stuck_because`, `shares_inputs`, `recent_cancellations` (per order), `waiting_for_validation_days` | INT | never added here. Facts: `orders[].created_tick`, `recent_cancellations` (DF's text), `events()` |

**Kept from #85 (same meaning, same hidden-information rules):** `date`, `dwarves`, `stressed_citizens`,
`administrators` (names, `manager_active_for_orders`, `manager_office`), `stocks` (#85's "usable" definitions, DER),
`wealth`, `workshops`, `zones`, `farm_plots`, `orders`, `recent_cancellations` (≤ 8, 3 days), `recent_events` (≤ 6,
7 days), `threats`, `water_on_fort_levels`, `military`, `burrows`, `doors`, `dig_designations_pending`,
`map.{size, wagon, surface_z}`, `plugins` (as harness2 added it).

**Added or fixed:**

| field | cat | what |
|---|---|---|
| `schema: 6` | IFC | |
| `dwarves[].{adult, squad_id, x, y, z}` | RAW | audit §c-7: what create_squad's eligibility and shelter checks need |
| `administrators.{citizens, manager_required_office, <CODE>_id}` | RAW | replaces `manager_needs_office`; unit ids next to names |
| `stocks.{tables, chairs, bins, charcoal}` | RAW | audit §c-10 (charcoal = BAR items of the COAL material) |
| `workshops[].job_details[] = {job, reaction, order_id, by_manager, worker_id, suspended, do_now}` | RAW | audit §c-14 (`jobs` keeps observe2's `"Type(order)"` strings, contract §3.1) |
| `zones` uncapped (≤ 200 listed) + `zones_total`; `zones[].furniture` always an object (built counts); `zones[].{furniture_planned, building_ids}` | RAW | audit §c-6: #85 cut at 12 silently |
| `furniture_unzoned {kind: n}` (contract §3.1), `furniture[] = {id, kind, x, y, z, built, zone_ids}` (≤ 300), `furniture_total` | RAW | audit §c-5: every placed furniture building (bed, table, chair, box, cabinet, door, hatch, …), built or not, with the zones DF says it is in (`building.relations`) |
| `farm_plots[].{crops {spring..winter}, subterranean}` | RAW | audit §c-18 |
| `orders[].when[] = {item_type (null = any), flags[], test, value}` always, plus `item_subtype, material, reaction_class, reaction_product, tool_use, stock` when set | RAW (fix) | audit §c-1: the "NONE" bug. A flag-only condition (`food_edible` → `unrotten, cookable`) now reads `{"item_type": null, "flags": ["cookable","unrotten"], …}`. `stock` echoes the frozen name when add_order made it |
| `orders[].{material_category, recipe?, created_tick}`; `when` for one-time orders too | RAW/IFC | `recipe` only when the order matches a frozen recipe (job/reaction always there); `created_tick`: see gaps |
| `moods[] = {unit_id, mood, skill, job (StrangeMood*), collected_items, waiting, claimed_building_id?, claimed_workshop?, items_needed? [{demand, quantity, collected, material? / cloth? (Fey only)}]}` | RAW (visible subset) | **schema 7**: what a vanilla DF 53 player sees (`gameapi/manual/MOOD-VISIBILITY.md`; DFHack tags `showmood` armok). `waiting` = on the claimed workshop's tiles and the job not fetching/bringing/working (checked in game). `items_needed` appears only while waiting: `demand` as the UI's clues word it, `quantity` null for the primary material, `collected` per element. Fey adds bar/glass `material` and `cloth` kind. Schema 6's `item`, `material`, `flags`, `available`, `available_approx` are gone |
| `dig_pending_by_z {z: n}` | RAW | audit §c-16 (designations are the player's orders, so hidden tiles count) |
| `map.size_tiles`, `map.wagon.present` | RAW | `size` is in 16-tile blocks (as #85); #85 fell back to 97,96,106 silently |
| `map.sites[] = {id, kind, x, y, z, w, h, soil (null = not checked), free, dug (R; null otherwise), used_by?, anchor? (W: centre), subterranean?, tiles? (R: {tiles, floor, soil_floor, designated, hidden}), stair? (R), open_tiles? (A), building? (E)}` | IFC + RAW | contracts §3.1 and §5.1: every listed candidate and every R room of the game, by id, with no ranking |

Sites are the frozen candidate searches (#85, unchanged), so they stay heuristic and capped (W ≤ 8, G ≤ 4, F ≤ 4,
E ≤ 8, A one per level, S ≤ 4, R ≤ 4, D ≤ 6). The `map` query is the raw alternative. Kinds: W free 3x3 floor on the
wagon level (x,y = centre), G surface soil 3x3, F dug soil 3x3 below ground, E down stair on the surface, A dug area per level,
S surface tile for a stair, R 3x3 box beside a dug stair, D doorway below ground.

## Queries (`query(name, **args)`)

| name | args (bounds) | returns |
|---|---|---|
| `stocks` | `item_type`, `limit` ≤ 1000 (200) | revealed items grouped by type, subtype, material: `count` (stack sum), `items`, and counts of `rotten, forbidden, in_job, in_building, in_inventory, construction`; `total` groups |
| `units` | `kind` citizens\|animals\|others, `id`, `limit` ≤ 300 (100) | citizens: profession, adult, positions, squad, job, stress, mood, x,y,z, `labors[]`, `skills {SKILL: rating}`, `needs[] {need, focus_level, need_level}`; animals (visible, the fort's): race, tame, adult, female, `pet_owner_id`, `marked_for_slaughter`; others: visible non-fort units, `hostile` |
| `jobs` | `limit` ≤ 500 (200) | the job list: id, job, reaction, worker, building, order, suspended/do_now/by_manager/repeat, x,y,z (revealed only) |
| `orders` | `limit` ≤ 500 (200) | every field: item type/subtype, material, material_category, frequency, workshop_id, max_workshops, full `item_conditions` (+ bearing), `order_conditions`, recipe, created_tick |
| `buildings` | `type`, `limit` ≤ 1000 (300) | buildings on revealed tiles (zones excluded): type, subtype, box, built/stage, jobs, zone_ids, material |
| `zones` | `limit` ≤ 1000 (300) | every zone: box, tiles, owner, active, buildings in it |
| `map` | `x,y,z` (default wagon), `radius` ≤ 20 (10), `z2` (≤ 5 levels) | per level, rows of one character per tile for `shape`, `material` and `light` (u subterranean, o outside, i inside), each with a legend; `?` = hidden. Also `buildings` (≤ 300), `designations` (≤ 500, hidden ones flagged) and `liquid` (≤ 500) |
| `manager_order_types` | — | `job_types[]` (job, caption, class, item_type, skill, labor), `reactions[]` permitted to the civilisation (with skill and buildings), `material_categories`, `condition_flags`, `item_types`, `recipes`, `when_stocks` |
| `workshop_types` | — | every workshop/furnace type DF can build (DFHack has filters for it) and the civilisation's permitted custom workshops: footprint `w,h`, `inputs` (item type, flags, quantity), `needs_magma` |

## Tools (v0)

- **The 20 frozen tools:** same names and arguments. Results carry no `note`, `hint`, `reminder`, `warning`, `valid`,
  `nearest_free_centre` or `short`. Facts that were phrased as advice became fields:
  - appoint_manager: `citizens`, `required_office`;
  - build_farm: `subterranean`;
  - assign_zone: `chair`, `changed`;
  - lock_door: `unbuilt`;
  - place_furniture: `requested`, `available`, `n`;
  - create_squad: `member_ids`;
  - dig_room/dig_stairs: `designated`, `steps[]`, `kept_stair_tiles`.

  add_order and add_manager_order return `order_id`. create_squad keeps its frozen "size N = best fighters" rule.
- **`build_workshop`:** the enum is DF's (query `workshop_types`): 32 types in DF 53.16 (30 workshop and furnace types, plus
  SOAP_MAKER and SCREW_PRESS). x,y is the footprint's centre. The material check generalises the frozen rule
  from DFHack's input filters: free items of a required item type (e.g. QUERN); boulders for fire-safe or magma-safe;
  else a log or boulder.
- **Two order tools** (split 2026-10-24: in the first end-to-end game, glm-5.3-flash sent 68 add_order calls with
  neither recipe nor job, because both were optional):
  - **`add_order`** is the frozen form exactly: required `["recipe", "amount"]`; `when` items require `stock` (the
    frozen names) plus one of `below` / `at_least`.
  - **`add_manager_order`** takes any DF manager order: required `["job", "amount"]`, plus `reaction`,
    `material_category`, `item_subtype`, `material`. `when` items require `item_type` (`ANY` = no item type, then
    `flags` are required), plus `flags`, `item_subtype`, `material`, `reaction_product`, `reaction_class` and one of
    `below` / `at_least`.
  - Each tool's description points to the other. Every bad_arguments error names the tool and the missing or invalid
    field, e.g. `add_order needs recipe (one of: brew_drink, ...); for any other DF manager order use add_manager_order`
    or `add_order when[0] needs stock (one of: ...)`. The server's schema check runs first and says
    `args.recipe is required` for the same call.
  - The job must be in `manager_order_types`, and a reaction must be permitted to the civilisation. Both tools then go
    through DFHack workorder's own code (`reqscript('workorder')`: `preprocess_orders`, `fillin_defaults`,
    `create_orders`, the path `workorder <json>` takes, checked on 53.16-r2). Its "Invalid …" errors come back as
    `bad_arguments`.
- **`slaughter {unit_id}`:** sets `unit.flags2.slaughter`, as the creature list's Slaughter button and DFHack's
  autobutcher do. The unit must be a visible, living, tame animal of the fortress and not a pet with an owner. Checked
  in game: a dwarf slaughtered the marked dog at a Butchers workshop within 3 days.

## What came from #85 (re-sync if #85 changes)

The source is `origin/obs-leaks` at **33b334813** (PR #85, `dfbench/v2.2-dev`). `harness2.py` is unchanged in #85, so the
Python ports below are from season0's `harness2.py`.

| here | from | changes |
|---|---|---|
| `lua/observe.lua` | #85 `observe2.lua` | interpretation removed, facts added (tables above); the helpers moved to `lua/common.lua` (#85's `seen`, `visible_unit`, `report_seen`, verbatim) |
| `lua/act.lua` | #85 `act2.lua` | `hint`/`note`/`nearest_free_centre` removed; build_workshop generalised; add_order (both order tools), slaughter added |
| `lua/place.lua` | #85 `place.lua` | `hint` removed |
| `lua/digplan.lua` | #85 `digplan.lua` | unchanged |
| `lua/observe.lua` moods | `bench/variants/mood_probe.lua` | the job test and `job_items.elements`; schema 7 keeps only the visible subset |
| `sites.py` | `harness2._assign_sites/_mark_used/_resolve_site` | no `valid`/hint; the box facts are new |
| `game.py` tool bodies | `harness2._act_raw`, `harness.validate/act` (dig) | structured results, no advice |
| `tools.py` | `harness2.RECIPES/ORDER_STOCKS/FURNITURE/ZONES/REPEATS/TOOLS` | descriptions without advice; new tools |

## Known gaps

- **Mood demand categories** come from the item type and the job-item flags, mapped to the wiki's clue wording
  (`rock`, `logs`, `bars`, `bones`, `cloth`, …); a category missing from the table reads as the item type in lower
  case. The 2-second clue timing (and so whether a player sees the non-primary quantities) is the wiki's, and is unchecked in v53.
- **No mood start tick.** The `STRANGE_MOOD` report in `events()` carries one. `unit.job.mood_timeout` exists, but DF
  doesn't show it, so it stays out.
- **`manager_order_types` is DF's job classes** (Manufacture, Improvement, plus CustomReaction and five gathering jobs),
  not the work-order screen's own list, which a script can't read. Orders that need `item_category` (encrusting) or art
  specs can't be made.
- **build_workshop doesn't check magma**, and the material check counts item types but not item flags (e.g. a fire-safe
  anvil). The 5x5 types (Siege, Kennels) never fit a 3x3 W site; use raw x,y,z.
- **Site candidates stay #85's heuristics, capped.** The `map` query is the raw view.
- **Recent lists stay capped:** `recent_cancellations` and `recent_events` keep #85's caps. `events()` is the full stream (≤ 1000 a
  call; `dropped` counts the rest).
- **`created_tick` depends on observation:** DF keeps no creation tick. It is the tick at which add_order made the order, or else the
  first observation that saw it (orders from the start save get the first observe's tick).
- **The `invasion` tripwire leak** (audit) belongs to the server's advance, not to this layer.
