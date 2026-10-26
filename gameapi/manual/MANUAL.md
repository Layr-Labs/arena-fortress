# Game API v0 reference manual

The `manual` that `GET /task` serves. It describes what the game server, the tools, the observation, the queries
and the events are and do, and how Dwarf Fortress (DF 53.16, DFHack 53.16-r2, fortress mode) behaves where the tools
touch it. It gives no advice: what to do, in which order, and with which targets is the harness's business.
Scoring is not described here: the task's `goal` says what a game is scored on, and `challenge/SCORING.md` defines
the score. Where this text and the served schemas (`GET /task` `tools`) differ, the schemas are what the server
checks. Points marked *(unverified)* have not been checked in game.

## 1. Conventions

- **Time.** 1 game day = 1200 ticks; 1 season = 84 days = 100800 ticks; 1 year = 336 days = 403200 ticks.
  `tick` and `abs_tick` are absolute (`year * 403200 + tick of the year`). `day` in the envelope counts game days
  since the game's start; `days_left` counts days to the horizon. Time moves only during `advance_days` (and when
  the server runs the fort itself, §2.3); between calls DF is paused.
- **Positions** are tile coordinates `x, y, z`. `z` grows upwards: "below the surface" means a lower z. The wagon's
  level (`map.surface_z`) is the embark surface. Boxes are given by their top-left corner `x, y` plus `w, h`, or by
  `x1, y1, x2, y2` (inclusive), except where a field says "centre".
- **Distance to the wagon** (`dist_to_wagon`): `max(|dx|, |dy|) + 3·|dz|` from the wagon's centre.
- **Ids.** `unit_id`/`dwarf_id`/`id` of a unit is DF's unit id. Buildings (workshops, furniture, doors, farm plots),
  zones, orders, squads, burrows and reports have DF's own ids, each in its own number space. Site ids (`W2`, `R3`,
  …) are the server's (§4).
- **Names.** Item types, job types, skills, labors, materials, moods and announcement types are DF's enum names
  (`DRINK`, `ConstructBed`, `MINING`, `INORGANIC:GRANITE`, `Fey`, `STRANGE_MOOD`).
- **Compactness.** A field whose value is unknown or not set is left out (or `null`). A section of the observation
  whose probe failed reads `"ERR: <message>"` instead of its value.

## 2. The game server

### 2.1 Endpoints

| | |
|---|---|
| `GET /task` | the task (`name`, `days`, `goal`, `brief`, `hands_off {from_day, days}` or null, `strange_moods`), `rules`, `limits`, `tools` (OpenAI function schemas), `queries` (name, params), this `manual`, `obs_schema`, `api` (`v0`), `key`, `model` (name, prices in USD per million tokens), `budget`. Does not start the wall clock |
| `GET /observe` | `{"observation": {...}}` (§6) |
| `POST /act` `{"tool": name, "args": {...}}` | one action (§5): `{"ok": true, "result": {...}}` or `{"ok": false, "error_code", "error", ...}`, plus `actions_left_today` |
| `GET /query/<name>?k=v&…` | `{"query", "result"}` (§7). Numeric strings are passed as numbers. Never moves time, never counts as an action |
| `GET /events?since_tick=N` | DF's reports after tick N (§8) |
| `GET /health` | phase (`starting`, `ready`, `running_out`, `over`, `finalized`, `failed`), and once over `finished`, `finished_by` |

Every response carries the envelope `day`, `tick`, `days_left`, `game_over`, and `hands_off_in_days` on tasks with
a hands-off window. Game-level errors come back as HTTP 200 with `ok: false`. `/task` answers 503 (`not_ready`)
until the game is ready.

### 2.2 Rules the server enforces

- **K actions per game day** (`rules.actions_per_game_day`, 40). Every `/act` other than `advance_days` that passes
  the limit check counts, whether DF accepts it or not (rejected and malformed calls too; an unknown tool name
  does not). The count belongs to the game-day index `(tick - start) // 1200`, so an advance that stops within the
  same day does not reset it. After K, every tool except `advance_days` gets `action_limit` until the day changes.
- **`advance_days`** runs 1 to `max_advance_days` (28) days, clamped to the horizon. It does not count as an action.
- **Hands-off window** (lab tasks): from day A = `days - hands_off.days`, actions get `hands_off`. No advance runs
  past A; the advance that reaches A returns `hands_off: true` after the server has run the window itself with no
  actions, and the game is then over.
- **Wall cap** (`limits.wall_s`): wall-clock seconds from the harness's first `/observe`, `/act`, `/query` or
  `/events` call. Provider throttling reported by the gateway and the server's own unmanaged running are excluded.
  At the cap an advance in progress returns with `wall_capped: true`, and the game ends at the tick reached.
- **The game ends** at the horizon, when the fort has no living citizens after an advance (`fort_lost`), at the
  wall cap, or if DF crashes. After the end, calls get `game_over`.
- **Strange moods** are on only when the task says `strange_moods: true` (DF's `[ARTIFACTS:YES]`); otherwise DF
  starts with `[ARTIFACTS:NO]` and no strange moods occur.

### 2.3 When the harness stops

If the harness exits or its model credits run out before the horizon, the server advances the rest of the horizon
itself (7 days at a time, tripwires ignored, no actions), so every game reaches its horizon unless the fort is lost
or the wall cap is hit.

### 2.4 Error codes

Server: `unknown_tool`, `bad_arguments` (the tool's JSON schema, or a value the tool rejects; undeclared arguments
are rejected), `action_limit`, `hands_off`, `game_over`, `unknown_query` (HTTP 404), `not_ready` (503),
`internal_error`, and `bad_request`/`not_found`/`forbidden` at the HTTP level.

Tools: `tile_hidden`, `tile_occupied`, `not_open_floor`, `not_soil_floor`, `needs_stone`, `no_material`,
`nothing_designated`, `no_space`, `already_assigned`, `not_a_citizen`, `no_such_order`, `no_position`,
`squad_exists`, `not_eligible`, `no_squad`, `not_a_hostile`, `no_hostiles`, `not_walkable`, `no_burrow`,
`wrong_tile_shape`, `no_doors`, `no_such_door`, `no_such_zone`, `not_assignable`, `not_enabled`, `game_refused`
(DF itself refused), `missing_location`, `wrong_site_kind`, `unknown_site`, `site_used`, `room_not_dug_yet`,
`no_such_unit`, `not_slaughterable`, `server_tool`, `failed` (an error with no more specific code). An error may
carry `allowed` (an enum's values), `detail` (DF's or quickfort's own output) or `steps`.

## 3. What the API shows (hidden information)

Every fact, query and event follows the same rules, which match what a player can see:
- an item on an unrevealed tile is not known (an item in a container or carried by a unit has its holder's tile);
- a unit is known when it is on a revealed tile and not sneaking or in ambush;
- a tile's shape and material are not known while it is hidden;
- a report about something on an unrevealed tile is not shown, unless DF put it in the announcement list.

Exceptions, because they are the player's own orders or DF's own records: citizens are always listed;
`dig_designations_pending` counts designations on hidden tiles too; the `jobs`, `orders` and `zones` lists are
complete (job positions only on revealed tiles); `threats.dead_citizens_total` counts every dead citizen.

## 4. Sites

Tools that place or dig things take `site=<id>`. The server keeps a list of candidate places, found by fixed
searches around the wagon, and gives each an id the first time it is listed: a letter for its kind and a number
per kind (`W1`, `W2`, …). An id is never reused within a game and keeps pointing at the same place. The searches
are capped, so the list is not every possible place; the `map` query is the raw view.

| kind | what it is | anchor | cap | taken by |
|---|---|---|---|---|
| W | free 3x3 floor on the wagon's level, clear of the wagon | centre | 8 | build_workshop |
| G | 3x3 soil or grass floor on the surface | top-left | 4 | build_farm |
| F | 3x3 dug soil floor 1-6 levels below the surface | top-left | 4 | build_farm |
| E | a down stair (or up/down stair) on the surface level | tile | 8 | build_door (hatch) |
| A | the dug, revealed, indoor area of one level 1-6 below the surface: the bounding box of its floor and stair tiles | box | 1 per level | place_furniture, make_zone, create_burrow |
| S | a free surface floor tile where a stair can start (clear of the wagon and of W sites) | tile | 4 | dig_stairs |
| R | a 3x3 box of revealed, undesignated solid wall beside a dug stair 1-8 levels below the surface; the row next to the stair is revealed, the far rows may be hidden. `soil: true` = that near row is soil | top-left | 4 | dig_room; once dug: build_farm, place_furniture, make_zone, create_burrow |
| D | a one-tile doorway below the surface: floor with wall on two opposite sides and walkable tiles on the other two | tile | 6 | build_door (door), build_wall |

"Free" here means: floor shape (not a tree), revealed, no building, no dig designation, not under the wagon.

- **Listed or not.** A candidate stays listed while the search still finds it. When it stops qualifying (built on,
  dug, designated) it drops out, and its id then gets `site_used` ("no longer listed").
- **R rooms.** An R site is undug while listed. Once dug it is no longer a candidate, but its id keeps working for
  build_farm, place_furniture, make_zone and create_burrow (before that, they get `room_not_dug_yet`). A dug room
  is `used` once a farm plot covers it (then build_farm, place_furniture and make_zone get `site_used`) or a zone
  covers it (then make_zone gets `site_used`).
- **`map.sites[]`**: every listed candidate and every R room of the game, ordered by kind and number, unranked:
  `{id, kind, x, y, z, w, h, soil (null = not checked), free, dug (R only, else null), used_by?, anchor? (W:
  "centre"), subterranean?, tiles? (R: {tiles, floor, soil_floor, designated, hidden} for the 3x3 box), stair? (R:
  the stair's x,y), open_tiles? (A), building? (E: a building on the stair tile)}`.
- **Resolution.** A tool given `site` re-reads the candidates first, so a site seen in an older observation is
  checked against the current map. A site resolves to the tool's coordinates (W: the centre; boxes: top-left plus
  the site's w,h; S for dig_stairs: `z_top` = the site's z). Raw `x, y, z` (and `w, h`, `z_top`) are also accepted
  in place of `site` by the site tools, though the schemas don't list them. With neither: `missing_location`.

## 5. Tools

Each tool's arguments are in its schema. "Free item" below means a revealed item that is not forbidden, not part of
a building or construction, not claimed by a job and not carried. Most tools that place something (workshops,
farm plots, furniture, doors, walls) create DF's building or construction site at once (`built: false`): a dwarf
with the matching labor then brings the material and builds it, which takes game time. The tools never move
time.

### Production

**`add_order {recipe, amount 1-30, repeat?, when?}`**: queues a DF manager (work) order from a named recipe.

| recipe | DF order | workshop | input | output |
|---|---|---|---|---|
| brew_drink | CustomReaction BREW_DRINK_FROM_PLANT | Still | a brewable plant + an empty barrel | 5 drinks |
| brew_drink_from_fruit | CustomReaction BREW_DRINK_FROM_PLANT_GROWTH | Still | a brewable fruit/growth + an empty barrel | 5 drinks |
| cook_meal | PrepareMeal | Kitchen | 2+ cookable ingredients | prepared meals |
| make_barrel, make_bed, make_door, make_table, make_chair, make_bin, make_hatch_cover | MakeBarrel, ConstructBed, ConstructDoor, ConstructTable, ConstructThrone (a chair), ConstructBin, ConstructHatchCover, material category wood | Carpenters | 1 log | 1 item |
| make_charcoal | MakeCharcoal | WoodFurnace | 1 log | charcoal (a bar) |

- `repeat` (`daily`, `monthly`, `seasonally`, `yearly`) makes it a repeating order: DF re-queues `amount` every
  period. Without it the order is one-time.
- `when` (needs `repeat`): 1-3 conditions `{stock, below | at_least}`. DF checks them at each repeat, and the
  order runs that period only if all hold. Each `stock` name stands for a DF item condition, counted by DF itself
  (so its meaning can differ from the observation field of the same name):

  | stock | DF condition |
  |---|---|
  | drink | item type DRINK |
  | prepared_meals | FOOD |
  | barrels_empty | BARREL, flag empty |
  | logs, logs_usable | WOOD (every log DF counts) |
  | food, food_edible | any item type, flags unrotten + cookable |
  | plants_total | PLANT, unrotten |
  | plants_brewable | PLANT, unrotten, reaction product DRINK_MAT |
  | boulders | BOULDER |
  | beds, tables, chairs, doors, bins | BED, TABLE, CHAIR, DOOR, BIN |

- Result: `order_id`, `job`, `reaction`, `amount`, `repeat`, `conditions` (count), `recipe`.

**`add_manager_order {job, amount 1-30, reaction?, material_category?, item_subtype?, material?, repeat?,
when?}`**: queues any DF manager order. `job` is a DF job type name from `manager_order_types.job_types` (DF's
Manufacture and Improvement job classes, plus CustomReaction, MilkCreature, ShearCreature, SpinThread,
CollectSand, CollectClay). `reaction` goes only with `job: CustomReaction`, and must be one the fortress's
civilisation may use (`manager_order_types.reactions`, with the workshops each runs at). `material_category` takes
DF's names (`manager_order_types.material_categories`, e.g. `wood`, `bone`, `cloth`); `material` a DF material token;
`item_subtype` a DF item subtype id. `when` conditions: `{item_type, flags?, item_subtype?, material?,
reaction_product?, reaction_class?, below | at_least}`, `item_type` a DF item type or `ANY` (then `flags` are
required; flag names in `manager_order_types.condition_flags`). The order is built by DFHack `workorder`'s own code,
as `workorder <json>` would; its "Invalid …" errors come back as `bad_arguments`, other refusals as `game_refused`.
Orders needing an item category (encrusting) or art specs can't be made. Result as add_order (no `recipe`).

**`cancel_order {order_id}`**: removes the order from DF's manager order list. Result `order_id`; `no_such_order`.
Jobs the order already created are not removed by the tool *(unverified what DF does with them)*.

**How a DF manager order runs.** A new order has `validated: false`. The fortress's manager validates pending
orders (DF does this about once a day; with no manager they stay unvalidated). A validated order becomes `active`
and DF creates jobs from it at a built workshop of a type that can do the job (any such workshop unless the order
names one), up to the order's limits. A dwarf with the job's labor who can reach the workshop and the inputs takes
the job; `left` counts down as jobs finish. Jobs that can't proceed are cancelled by the dwarf, and DF reports why
(`recent_cancellations`, `/events`). `jobs_in_progress` counts the order's existing jobs.

**The manager's office.** The manager position's noble raws carry a required office value
(`administrators.manager_required_office`). In the frozen harness's runs DF stopped validating orders from about
20 citizens until the manager had an office: an office zone with a built chair, assigned to the manager
(`administrators.manager_office`) *(measured in game, not a documented DF rule)*.

**`build_workshop {type, site W}`**: places a workshop or furnace centred on the site. `type` is one of DF's types
(the schema's enum, from DF; in 53.16: Ashery, Bowyers, Butchers, Carpenters, Clothiers, Craftsdwarfs, Dyers,
Farmers, Fishery, GlassFurnace, Jewelers, Kennels, Kiln, Kitchen, Leatherworks, Loom, MagmaForge,
MagmaGlassFurnace, MagmaKiln, MagmaSmelter, Masons, Mechanics, MetalsmithsForge, Millstone, Quern, SCREW_PRESS,
SOAP_MAKER, Siege, Smelter, Still, Tanners, WoodFurnace). The `workshop_types` query gives each one's footprint and
the inputs DF's build menu asks for. Checks, in order: every footprint tile revealed (`tile_hidden`), open floor
and not a tree (`not_open_floor`), no building (`tile_occupied`); then each input: a specific item type needs that
many free items of it (`no_material`, e.g. a quern for a Quern); a fire-safe or magma-safe input needs usable stone
boulders (`needs_stone`); any other input needs a usable log or boulder (`no_material`). Usable = revealed, not
forbidden, not in a building, not in a job. Magma is not checked for the Magma types. Footprints come from DF (`workshop_types` `w, h`):
Siege and Kennels are 5x5, larger than a W site, and need raw `x, y, z`. Result: `id`, `type`, `x1, y1, x2, y2, z`.
In the frozen harness's runs, a workshop placed with no usable material was cancelled by the builder and not
retried *(observed, not a documented DF rule)*; the material check exists for that reason.

What the frozen recipes and common jobs use: Carpenters (wood furniture, barrels, bins), Still (brewing),
Kitchen (cooking), Masons (stone furniture, from boulders), Craftsdwarfs (crafts from stone, wood, bone),
Farmers (plant processing), Butchers (butchering slaughtered animals), Fishery (processing fish), WoodFurnace
(charcoal; built from stone).

**`build_farm {site F|G|R}`**: places a farm plot on the box (3x3 from the site). Every tile must be revealed
(`tile_hidden`), floor with soil or grass material (`not_soil_floor`), with no building (`tile_occupied`). Result:
`id`, `subterranean` (DF's tile flag at the plot's corner). DF grows each crop only on plots of its kind:
crops with an underground growth requirement (`seeds_by_kind[].underground`) only on subterranean plots, surface
crops only on non-subterranean ones, each in its growing seasons. No tool chooses a plot's crop; the `autofarm`
plugin sets it each season from the seeds in stock, and `farm_plots[].crops` shows what is set.

**`enable_automation {name}`**: enables a DFHack plugin, with its default settings:
- `autochop`: designates trees for felling to keep a stock of logs;
- `autofarm`: sets each farm plot's crop every season from the seeds in stock;
- `seedwatch`: keeps seeds of each crop from being cooked or brewed below a threshold;
- `autolabor`: assigns labors to dwarves automatically;
- `autoclothing`: queues clothing orders.

Result: `name`, `was`, `now` (`on`/`off`/`unknown`); `not_enabled` if it didn't turn on. No tool disables a plugin.
`plugins` in the observation shows each one's state.

**`slaughter {unit_id}`**: marks a tame animal of the fortress for slaughter (`unit.flags2.slaughter`, what the
creature list's Slaughter button and DFHack's autobutcher set). The unit must be living and visible
(`no_such_unit`), an animal and not a citizen, tame and of the fortress's civilisation, and not a pet with an owner
(`not_slaughterable`). DF then makes the job: a dwarf with the butchery labor takes the animal to a Butchers
workshop. Checked in game: a marked dog was slaughtered within 3 days. Result: `unit_id`, `race`, `marked`,
`was_marked`. The `units?kind=animals` query lists the fortress's animals.

### Nobles, rooms and furniture

**`appoint_manager {dwarf_id?}`**: gives the MANAGER position to a citizen; with no `dwarf_id`, the first citizen
in DF's unit list who holds no position. `already_assigned` if the fortress has a manager or the dwarf holds a
position; `not_a_citizen`. Result: `manager`, `manager_id`, `citizens`, `required_office`. No tool removes a
manager.

**`place_furniture {kind, site A|R, count 1-30 = 1}`**: places up to `count` free furniture items, one per tile, on
tiles of the site's box. Kinds: `bed`, `table`, `chair`, `door`, `container` (DF's BOX: a chest or coffer). A tile
qualifies when it is revealed, floor-like (floor, boulder, pebbles, twig, sapling, shrub), holds liquid depth ≤ 1,
has no building, no dig designation and no stair; beds only on tiles that are not outside (under a roof); doors
only next to a wall. Each placement is a quickfort `#build`, which DF may still refuse for a tile
(`tiles_rejected`). `no_material` with no free item of the kind; `no_space` when nothing could be placed. Result:
`placed` (kind), `n`, `requested`, `available` (free items before placing), `at` (one x,y,z, or a list when
count > 1), `tiles_rejected`.

**`make_zone {kind, site A|R}`**: makes a DF activity zone over the site's box: `bedroom`, `dormitory`,
`dining_hall`, `meeting_area` or `office`. Result: `zone` (kind), `tiles`, `at` [x, y, z, w, h], `zone_id`;
`no_space` if quickfort made no zone. The zone covers the whole box; for an A site that is the bounding box of the
level's dug area. DF uses zones this way: a bedroom zone with a bed is one dwarf's room once assigned (or claimed);
a dormitory's beds are shared; a dining hall's tables and chairs are shared seats for eating; an office is a
noble's workroom (a chair in it); a meeting area is where idle dwarves gather. Furniture counts for a zone when DF
says the building is in it (`zones[].furniture`, `furniture[].zone_ids`).

**`assign_zone {zone_id, dwarf_id}`**: assigns an office or bedroom zone to a citizen (the zone sheet's Assign).
`no_such_zone`, `not_assignable` (other zone kinds are shared), `not_a_citizen`, `game_refused`. Result: `zone_id`,
`kind`, `owner`, `owner_name`, `changed` (false if already theirs), `chair` (a built chair is in the zone).

### Digging

**`dig_room {site R, w 1-15 = 3, h 1-15 = 3}`**: designates the box (top-left x,y) for digging (quickfort `d`),
leaving tiles that carry a stair or a stair designation. Result: `designated` (tiles), `steps [{at, tiles}]`,
`kept_stair_tiles`; `nothing_designated` if no tile took the designation. Miners (mining labor, with a pick) then
dig it out over game time; `dig_designations_pending` and `dig_pending_by_z` count what is left.

**`dig_stairs {site S, z_bottom = z - 1}`**: designates a staircase from the site's tile down to `z_bottom` (1-20
levels): a down stair at the top, up/down stairs between, an up stair at the bottom. Result as dig_room, one step
per level; `nothing_designated` names the levels where nothing was designated.

### Defence

**`create_squad {dwarf_ids? | size 1-10 = 4}`**: creates the fortress's squad (one squad is supported:
`squad_exists`). Members are adult citizens with no position and no squad (`not_eligible`). With `size`, the N
eligible citizens with the highest summed combat skills (weapon skills, melee, wrestling, dodging, shield, armour,
and mining), then strength. The first member becomes the militia commander (`no_position` if the fortress has no
such position; `already_assigned` if someone else holds it), which is a position. The squad is named "Guard".
Members keep their civilian work until the squad has an order. Result: `squad_id`, `members`, `member_ids`.

**`equip_squad {uniform}`**: sets every squad position's uniform from the fortress's uniform templates:
`weapon_only` (the weapon of "Melee, leather armor"), `leather` ("Melee, leather armor"), `metal` ("Melee, metal
armor"). DF assigns only items that exist; members fetch them over game time. `no_squad`, `game_refused` (no such
template). Result: `template`, `weapons_not_carried` (revealed weapons not forbidden, carried, in a job or held by a
trader).

**`squad_order {order, target_ids?, x?, y?, z?}`**: replaces the squad's orders. `attack`: a kill order on
`target_ids` (each a visible, living, hostile unit: `not_a_hostile`), or on every visible hostile (`no_hostiles` if
none). `station`: move to x,y,z, which must be revealed (`tile_hidden`) and walkable (`not_walkable`).
`stand_down`: clears the orders. Result: `order`, `targets` (attack).

**`create_burrow {site A|R, levels 1-5 = 1}`**: adds the site's box on `levels` levels, from the site's level
downwards, to the burrow "Shelter", creating it if needed as the civilian-alert burrow. Result: `burrow`,
`tiles_added`, `created`; `nothing_designated` if no tile was added.

**`civilian_alert {on}`**: sounds or clears DF's civilian alert (DFHack `gui/civ-alert`). While it is on, civilians
are restricted to the alert burrow, so work outside it stops. `no_burrow` without a civilian-alert burrow. Result:
`civilian_alert`.

**`build_door {kind, site E|D}`**: places a hatch cover (`hatch`) over a down stair, up/down stair, ramp top or open
space, or a door (`door`) on a floor tile (`wrong_tile_shape`), using a free hatch cover or door item
(`no_material`). Result: `id`.

**`build_wall {site D}`**: places a wall construction on a revealed floor tile with no building, from a usable log
or boulder (`no_material`). Once built, nothing in the tool API removes it. Result: `id`.

**`lock_door {locked, door_id?}`**: locks or unlocks one door or hatch, or all of them (built or not). A locked door
is forbidden: the fortress's own dwarves and animals don't pass it either. *(Unverified here: DF lets building
destroyers break doors.)* `no_such_door`, `no_doors`. Result: `locked`, `doors` (ids), `unbuilt`.

### Time

**`advance_days {days, stop_on?}`**: lets 1-28 days pass (§2.2). It stops early at a tripwire, checked every 100
ticks; only changes since the advance began count:
- `hostile_visible`: a dangerous non-citizen became visible;
- `hostile_approaching`: a visible hostile got 25+ tiles closer to the nearest citizen;
- `hostile_near_citizens`: a visible hostile came within 30 tiles (and 3 levels) of a citizen;
- `citizen_died`: fewer living citizens than at the start;
- `invasion`: an invasion became active;
- `water_rising`: revealed water on the fortress's indoor tiles (within 30 tiles of the wagon, the surface level
  and 8 below) grew by 50% and by at least 50 depth units;
- `announcement:<TYPE>`: one of `rules.announcement_types` was announced (strange moods, berserks, tantrums,
  deaths, migrants, caravans, diplomats, nobles, megabeasts, werebeasts, ambushes, cave-ins).

`stop_on` lists the tripwires that stop this call (`announcement` = every announcement type); default all, `[]`
none. A tripwire not listed is recorded and the advance goes on. Result: `advanced_ticks`, `advanced_days`,
`stopped` (null or `{reason, detail, after_ticks, abs_tick}`), `tripwires_ignored?`, `interruptions?` (DF popups
dismissed during the advance), `wall_capped?`, `hands_off?`, `end_reason?` (when the game ended).

## 6. The observation (obs schema 6)

`GET /observe` → `{"observation": {...}}`. Empty lists may be left out.

- **`date`**: `year`, `day_of_year` (1-336), `season`, `abs_tick`.
- **`dwarves[]`** (every citizen): `id`, `name`, `profession` (DF's profession name; DFHack's default gives a noble's position title instead *(unverified)*),
  `job` (current DF job type, or `idle`), `positions` (position codes), `organizer_skill` (ORGANIZATION skill
  level), `stress` (DF's stress category, 0 = most stressed … 6 = content), `adult`, `squad_id`, `x, y, z`.
- **`stressed_citizens`**: citizens with stress category ≤ 1 (the definition the trusted recorder uses).
- **`administrators`**: `citizens` (count); for MANAGER, BOOKKEEPER, EXPEDITION_LEADER, CHIEF_MEDICAL_DWARF and
  BROKER, the holder's name or `VACANT`, and `<CODE>_id`; `manager_active_for_orders` (DF has someone with the
  manage-production responsibility); `manager_required_office`; `manager_office` (`{zone_id, chair}` or `none`).
- **`stocks`** (revealed items; counts are stack sums unless noted):
  - `drink`; `food_edible` (DF's good-food item list *(unverified whether rotten items are in it)*);
    `prepared_meals` (FOOD items);
  - `plants_total` (unrotten, unforbidden plants), `plants_brewable` (of those, with a DRINK_MAT product),
    `plants_rotten`, `plants_by_kind {name: {n, brewable, cookable}}`;
  - `seeds` (all), `seeds_by_kind {name: {n, underground, seasons}}` (unforbidden only);
  - `logs_usable` (logs not in a building, forbidden or in a job), `logs_unusable` (the rest: the embark wagon's
    logs count here);
  - `boulders`, `boulders_usable`; `charcoal` (bars of coal);
  - `barrels_total`, `barrels_empty` (nothing inside, not in a job; the embark barrels hold supplies);
  - item counts `beds`, `tables`, `chairs`, `bins` (every item, wherever it is), and `furniture_free {bed, table,
    chair, door, container}` (items not in a building, forbidden, in a job or part of a construction).
- **`wealth`**: DF's fortress wealth: `total`, `created` (weapons + armour + furniture + other + architecture +
  displayed), `crafted` (the same without other), `furniture`, `architecture`, `other`, `raw_logs_value`.
- **`workshops[]`** (workshops and furnaces): `id`, `type`, `x, y, z` (centre), `built`, `jobs` (strings
  `"JobType"`, `"(order)"` appended when it came from a manager order), `job_details[] {job, reaction, order_id,
  by_manager, worker_id, suspended, do_now}`.
- **`zones[]`** (≤ 200; `zones_total` is the true count): `id`, `type`, `x, y, z, w, h`, `owner` (unit id),
  `furniture {kind: n}` (built buildings in it), `furniture_planned` (not yet built), `building_ids`.
- **`furniture[]`** (≤ 300; `furniture_total`): every placed bed, table, chair, box, cabinet, armour stand, weapon
  rack, statue, coffin, slab, traction bench, bookcase, display, chain, cage, door and hatch on a revealed tile:
  `id`, `kind`, `x, y, z`, `built`, `zone_ids`. `furniture_unzoned {kind: n}` counts those in no zone.
- **`farm_plots[]`**: `id`, `x, y, z, w, h`, `built`, `seeds_or_crops_in_plot`, `crop_this_season`, `crops
  {spring, summer, autumn, winter}` (plant id or `none`), `subterranean`.
- **`orders[]`**: `id`, `job`, `reaction`, `recipe` (when it matches a recipe of add_order), `material_category`,
  `meal_kind`, `left`, `total`, `validated`, `active`, `jobs_in_progress`, `repeat`, `created_tick` (the tick
  add_order made it, else the first observation that saw it: DF keeps no creation tick), `when[] {item_type (null =
  any), flags[], test (LessThan, AtLeast, …), value, item_subtype?, material?, reaction_class?, reaction_product?,
  tool_use?, stock? (the add_order name)}`.
- **`recent_cancellations`**: up to 8 of DF's job-cancellation and "unable to" reports from the last 3 days, newest
  first, as DF wrote them.
- **`recent_events`**: up to 6 other reports from the last 7 days, newest first. The full stream is `/events`.
- **`threats`**: `visible_hostiles`, `nearest_hostile_dist_to_wagon`, `by_race {race: {n, invader}}`,
  `hostiles[]` (≤ 20) `{id, race, invader, x, y, z, dist_to_wagon, weapon, in_shelter}`, `dead_citizens_total`,
  `invaders_dead` (dead invaders on revealed tiles).
- **`moods[]`** (present when a citizen is in a mood; any DF mood type except none: `Fey`, `Secretive`,
  `Possessed`, `Macabre`, `Fell`, and the insane ones `Melancholy`, `Raving`, `Berserk`, …): `unit_id`, `mood`,
  `skill` (the mood's skill), `job` (the DF job: `StrangeMood…` while the mood's work is under way), and for a
  StrangeMood job `claimed_building_id`, `claimed_workshop` (type) and `items_needed[] {item (item type, `any` =
  none), material, flags[], quantity, collected (items brought so far), available, available_approx}`. `available`
  counts revealed, unclaimed items that DFHack's suitability tests accept: an upper bound, since the mood may
  still refuse some; `available_approx` marks requirements with no item type, where corpses also pass the test.
  DF: a dwarf in a strange mood claims a workshop of the kind its skill needs, collects its items, then makes an
  artifact. A strange mood left too long without its workshop or items ends in insanity. The `STRANGE_MOOD`
  report's tick is the mood's start.
- **`water_on_fort_levels`** (present when > 0): revealed indoor tiles with water within 30 tiles of the wagon,
  from 8 levels below the surface up: `tiles`, `deep_tiles` (depth ≥ 4 of 7), `total_depth`.
- **`military`**: `squads[] {id, name, members[] {id, name, leader, weapon, weapon_assigned, x, y, z}, armed,
  uniform (none, weapon_only, weapon+armor), orders[] (attack {targets, targets_alive}, station {x, y, z}),
  on_duty}`, `weapons_free`.
- **`burrows`**: `list[] {id, name, tiles, civ_alert_burrow, citizens_inside, bbox}`, `civilian_alert`.
- **`doors`**: `list[] {id, kind (door, hatch), x, y, z, built, locked}`, `door_items_free`,
  `hatch_cover_items_free`.
- **`dig_designations_pending`**, **`dig_pending_by_z {z: n}`**: tiles designated and not yet dug, map-wide.
- **`map`**: `size` (in 16x16-tile blocks, and z-levels), `size_tiles`, `wagon {x, y, z, present}`, `surface_z`,
  `sites[]` (§4).
- **`plugins`**: `{autochop, autofarm, seedwatch, autolabor, autoclothing}`: `on`, `off` or `unknown`.
- **`schema`**: 6.

## 7. Queries

`GET /query/<name>?arg=value`. Every list is bounded; `total` says how many matched, so a cut is never silent.
Bad arguments get `bad_arguments`.

| name | args (max; default) | returns |
|---|---|---|
| `stocks` | `item_type`, `limit` (1000; 200) | `groups[] {item_type, item_subtype, material, count (stack sum), items, rotten, forbidden, in_job, in_building, in_inventory, construction}` (item counts per flag), sorted by type then count; `total` groups, `items` |
| `units` | `kind` = citizens \| animals \| others, `id`, `limit` (300; 100) | citizens: `id, name, profession, adult, positions, squad_id, job, stress, x, y, z, mood, labors[], skills {SKILL: level}, needs[] {need, focus_level, need_level}`; animals (the fortress's, visible): `id, race, tame, adult, female, pet_owner_id, marked_for_slaughter, x, y, z`; others (visible, not the fortress's): `id, race, hostile, visitor, x, y, z` |
| `jobs` | `limit` (500; 200) | DF's job list: `id, job, reaction, worker_id, building_id, order_id, suspended, do_now, by_manager, repeat, items_attached, x, y, z` (position on revealed tiles only) |
| `orders` | `limit` (500; 200) | every manager order with every field: `item_type, item_subtype, material, meal_kind, material_category, left, total, validated, active, frequency, workshop_id, max_workshops, jobs_in_progress, item_conditions[]` (as `when`, plus `bearing`), `order_conditions[] {order_id, condition}`, `recipe`, `created_tick` |
| `buildings` | `type` (building type or subtype), `limit` (1000; 300) | buildings on revealed tiles, zones excluded: `id, type, subtype, x1, y1, x2, y2, z, x, y, built, stage, max_stage, jobs (count), zone_ids, material` |
| `zones` | `limit` (1000; 300) | every zone: `id, type, x1, y1, x2, y2, z, tiles, owner, active, buildings[] {id, type, subtype, built, x, y}` |
| `map` | `x, y, z` (default the wagon), `radius` (20; 10), `z2` (another level; ≤ 5 levels in all) | `x1, y1, x2, y2`; `levels[] {z, shape[], material[], light[]}`: one string per row (row i is y = y1 + i, character j is x = x1 + j), one character per tile, with a `legend` for each layer; `?` = hidden. Light: `u` subterranean, `o` outside, `i` inside above ground. Also `buildings` (≤ 300), `designations` (≤ 500, `hidden` flagged) and `liquid` (≤ 500, `depth`, `magma`) |
| `manager_order_types` | none | `job_types[] {job, caption, class, item_type, skill, labor}`, `reactions[] {reaction, name, skill, buildings}` (permitted to the civilisation), `material_categories`, `condition_flags`, `item_types`, `recipes` (add_order's), `when_stocks` (add_order's stock names and their DF conditions) |
| `workshop_types` | none | every buildable workshop and furnace type and permitted custom workshop: `type, building_type, w, h, inputs[] {item_type?, flags?, quantity}, needs_magma, custom` |

Skill levels are DF's ratings (0 = dabbling … 15+ = legendary). Needs: `need_level` is how much the dwarf needs it,
`focus_level` how well it is met (negative = unmet, DF's scale).

## 8. Events

`GET /events?since_tick=N` → `{"since_tick", "events": [...], "dropped", "now"}`: DF's reports (the announcement
and report log) with tick > N, oldest first, at most 200 per call. When more match, the newest 200 are returned and
`dropped` counts the older ones left out (they can't be fetched: there is no upper bound, so a harness that wants
every report asks often enough to stay under 200). Each event: `id`
(DF's report id, increasing), `tick`, `type` (DF's announcement type, e.g. `STRANGE_MOOD`,
`MOOD_BUILDING_CLAIMED`, `ARTIFACT_BEGUN`, `CITIZEN_DEATH`), `text`, `announcement` (DF put it in the
announcement list), `repeat_count?`, `x, y, z?` (revealed tiles only). Continuation lines are joined to their
report.

## 9. DF facts the tools touch

- **Materials.** Building most things takes a log, a boulder or a specific item. The logs and barrels in the
  embark wagon are counted as unusable (`logs_unusable`); usable logs come from felled trees (by a woodcutter;
  `autochop` designates trees), boulders from digging stone (not soil).
- **Drink and food.** Dwarves drink water when they can reach it and none is in stock, and get unhappy thoughts
  and work slower without alcohol. Brewing needs a brewable plant and an empty barrel; cooking and brewing can use
  up the same plants. Dwarves get a happier thought from eating prepared meals than raw food. Rotten and forbidden
  items aren't used.
- **Rooms.** Dwarves get unhappy thoughts sleeping without a bed and eating without a table and chair.
- **Labors.** A job is done only by a dwarf with its labor enabled (`units` query: `labors[]`); no tool sets labors
  except `autolabor`.
- **Military.** Civilians without weapons fight unarmed. A squad member with no weapon assigned fights unarmed.
  Squads use only weapons and armour that exist in the fortress.
- **Moods.** See `moods[]` (§6). Each strange mood type requires a workshop type matching its skill, and its
  items; DF names the claimed workshop in a `MOOD_BUILDING_CLAIMED` report.

## 10. Known limits of v0

- Site searches are capped and heuristic (§4); `map` is the raw view.
- `recent_cancellations` and `recent_events` are capped; `/events` is the full stream.
- `build_workshop` checks input item types but not their flags, and doesn't check magma.
- `manager_order_types` lists DF's job classes, not the work-order screen's own list.
- `created_tick` depends on when an order was first observed.
- No trade, no labor tool, no crop choice tool, no tool to remove a building, wall, zone, squad member or position.
