# gameapi/facts: in-game check

**Latest run (2026-10-24, obs schema 7: visible mood facts):** image `yukon-df:s0facts-4cbbea7ee`, scripted-y1.
41/41 unit tests and **64/64 in-game checks pass**.
- **Fey woodcrafter** (`mood.lua woodcrafter fey 0`):
  - just struck: `{job: StrangeMoodCrafter, waiting: false, collected_items: 0}`, with no claim and no demands;
  - after 3 days: claimed Craftsdwarfs, 2 items collected, gathering/working, so `waiting: false` and no `items_needed`.
- **Secretive mason** (after a fort reload, since DF has one mood at a time; a Masons was built; the fort has no
  stone): after 3 days `{claimed_workshop: Masons, waiting: true, items_needed: [{demand: "rock", quantity: null,
  collected: 0}]}`. That is the stone the workshop's clue names, with no material, flags or availability.
- **How `waiting` reads in game** (probe, job.flags in 53.16):
  - while gathering, the job has `fetching`, then `bringing`;
  - with all items in, it has `working` (the carpenter secretive case: one log, then works);
  - a mood that cannot find an item stands on the workshop tiles with only `special` set. That is the waiting state.
- `carpenter secretive 0` was tried too: on this fort the carpenter finds a log, so it never waits. `mason secretive`
  is the waiting case.


**Latest run (2026-10-24, after the add_order / add_manager_order split):** image `yukon-df:s0facts-997c184d6`, the same
fort. 40/40 unit tests and **59/59 in-game checks pass**. `tools()` lists 22 tools.
- `add_manager_order` made orders 60 (ConstructBlocks wood), 61 (MAKE_PEARLASH) and 62 (ConstructBin monthly with
  BIN, WOOD+unrotten and `ANY`+unrotten,cookable conditions).
- `add_order` (frozen) made order 63, cook_meal with `stock: food_edible`.
- The e2e glm call `{"amount":5,"repeat":"daily","when":[{"below":70,"at_least":0}]}` now fails with `add_order needs
  recipe (one of: brew_drink, …); for any other DF manager order use add_manager_order`. A `when` with no stock fails
  with `add_order when[0] needs stock (one of: …)`.
- The rest is as below (the step names now say add_manager_order where they said "add_order generic").

## First runs (2026-10-23)

- **Run:** `gameapi/facts/check_in_game.sh`.
  - Image: `yukon-df:s0facts-aa46db7fe`, built from this branch per `docker/README.md` (DF 53.16, DFHack 53.16-r2).
  - Container: one, `s0facts-check`, `--memory 2500m`.
  - Fort: `SNAPSHOT=scenarios/snapshots/scripted-y1 ./reset_fort.sh` (READY 1228020, 19 citizens).
- **Result:** 37/37 unit tests and **57/57 in-game checks pass**. The check itself took 22 s of wall time, including a 3-day advance.
- **Full log:** `gameapi/facts/in_game.jsonl` (one JSON object per check).
- **Earlier runs** on the same fort (probe container `yukon-df:p0mood`, then this image) found and fixed:
  - the site-kind clash between E/D candidates and the site letter;
  - the enum check order;
  - the advance stopping at the mood popup;
  - workshops[].jobs needing to stay observe2's strings for the starter harness.

## What was exercised

| step | outcome |
|---|---|
| `tools()` | 21 schemas. The build_workshop enum, from DF, has 32 types: Ashery, Bowyers, Butchers, Carpenters, Clothiers, Craftsdwarfs, Dyers, Farmers, Fishery, GlassFurnace, Jewelers, Kennels, Kiln, Kitchen, Leatherworks, Loom, MagmaForge, MagmaGlassFurnace, MagmaKiln, MagmaSmelter, Masons, Mechanics, MetalsmithsForge, Millstone, Quern, SCREW_PRESS, SOAP_MAKER, Siege, Smelter, Still, Tanners, WoodFurnace (`Tool` has no build filters in DF 53.16, so it is left out) |
| `observe()` | schema 6, no `ERR` fields, 10.2 kB JSON. No `manager_needs_office`, `threats.note` or ranked site lists. `administrators.manager_required_office = 1`, `citizens = 19`, `furniture_unzoned = {}`, `zones_total = 0`, plugins read from `enable` |
| every query | stocks (114 groups, 992 revealed items; WOOD by material), units (citizens with labors, skills, needs; 19 animals; visible others), jobs, orders, buildings, zones, map (surface and a level below), manager_order_types, workshop_types: all `ok` |
| query validation | an unknown query gives `unknown_query`; `limit` 10^6 gives `bad_arguments`. The map 12 levels down is `?` on every tile (hidden) |
| `events()` | reports with id, tick, type, text, announcement and position |
| build_workshop | **Leatherworks**, **Craftsdwarfs** and **Butchers** were placed on W1-W3, and all three were built within 3 days. Siege (5x5) on a 3x3 W site gives `not_open_floor`, and an unknown type gives `bad_arguments` with `allowed` |
| add_order (generic) | `{job: ConstructBlocks, material_category: [wood]}` became order 60 (jobs in progress); `{job: CustomReaction, reaction: MAKE_PEARLASH}` order 61; `ConstructBin` monthly `when [{item_type: BIN, below: 5}, {item_type: WOOD, flags: [unrotten], at_least: 10}]` order 62 |
| add_order (refusals) | `job: Dig` gives `bad_arguments` (not a manager order job). A bad material_category and a bad `when` flag also give `bad_arguments`, from DFHack workorder's own "Invalid …" errors |
| the "NONE" bug | `cook_meal` daily `when food_edible at_least 20` now reads `{"item_type": null, "flags": ["cookable","unrotten"], "test": "AtLeast", "value": 20, "stock": "food_edible"}`, with `recipe: cook_meal` and `created_tick` |
| slaughter | Dog 93 was marked (`marked_for_slaughter` true in the units query). A pet with an owner gives `not_slaughterable`, as does a citizen. **Within 3 days a dwarf slaughtered it at the new Butchers**: event `PET_DEATH` "The Stray Dog (Tame) has been slaughtered." |
| frozen tools | No advice fields in any result. appoint_manager gives `already_assigned`, cancel_order(999999) `no_such_order` and lock_door `no_doors`. enable_automation autochop gives `{was: on, now: on}` with no note. build_farm R1 gives `room_not_dug_yet`, dig_room X9 `wrong_site_kind`, and dig_stairs S1 designates 2 tiles `{designated, steps}`. advance_days gives `server_tool`, an unknown tool `unknown_tool` |
| strange mood | `scenarios/lua/mood.lua woodcrafter fey 0` struck unit 331. At once: `{job: StrangeMoodCrafter, mood: Fey, skill: WOODCRAFT, items_needed: [{item: WOOD, quantity: 1, collected: 0, available: 236, flags: []}]}`. After 3 days: `claimed_building_id: 7, claimed_workshop: Craftsdwarfs`, collected 1. Events `STRANGE_MOOD`, `MOOD_BUILDING_CLAIMED`, `ARTIFACT_BEGUN` |
| reference harness | the organiser's reference harness read the live observation. Sites by kind came through (W4-W11, G, E, A1, S2-S5, R1-R3), the mood's workshop came through, and orders carried their recipes |

## Excerpts

```json
{"step": "observe moods after 3 days", "moods": [{"claimed_building_id": 7, "claimed_workshop": "Craftsdwarfs",
  "items_needed": [{"available": 234, "collected": 1, "flags": [], "item": "WOOD", "quantity": 1}],
  "job": "StrangeMoodCrafter", "mood": "Fey", "skill": "WOODCRAFT", "unit_id": 331}]}
{"step": "events since start", "n": 4, "events": [
  {"id": 233, "tick": 1228020, "type": "STRANGE_MOOD", "text": "Ingish Ducimlegon \"Workwandered\", Woodcutter is taken by a fey mood!", "announcement": true, "x": 99, "y": 99, "z": 106},
  {"id": 234, "tick": 1230017, "type": "MOOD_BUILDING_CLAIMED", "text": "Ingish Ducimlegon has claimed a Craftsdwarf's Workshop.", ...},
  {"id": 235, "tick": 1230282, "type": "PET_DEATH", "text": "The Stray Dog (Tame) has been slaughtered.", ...},
  {"id": 236, "tick": 1231463, "type": "ARTIFACT_BEGUN", "text": "Ingish Ducimlegon has begun a mysterious construction!", ...}]}
{"step": "add_order bad when flag refused by workorder", "result": {"ok": false, "error_code": "bad_arguments",
  "error": "the game refused the order: lua: Invalid item condition flags for manager order: notaflag"}}
{"step": "build_workshop Leatherworks at W1", "result": {"ok": true, "result": {"id": 6, "type": "Leatherworks",
  "x1": 92, "y1": 91, "x2": 94, "y2": 93, "z": 106}}}
```

## Not covered in game

- A furnace or custom workshop build: the material path was checked on the Siege refusal only.
- Zone and furniture membership with real zones: scripted-y1 has no activity zones (`zones_total 0`); the starter's
  normalise ran with it empty.
- squad/door/burrow tools beyond the error paths shown: they are the copied #85 code, changed only by removing advice.
