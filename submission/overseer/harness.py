"""Overseer: a deterministic Dwarf Fortress manager for game API v0. Reads facts, acts through the public tools only.

Order of work follows the score's gates: survive, supply, wellbeing, housing. Every step is idempotent and rate
limited, so a refused action is retried later rather than looped on. Makes no model calls.
Run: python -m overseer   (reads DFBENCH_TASK)

Lineage: the layer and its regular steps are e-man07's submission 6e775ed2 as repaired by GordoAR's 5dfdcf15 (main).
Two housing-measurement steps (seats counted inside dining zones, re-zoning loose furniture) come from e-man07's
efac22bf. This copy adds the "closer" steps (endgame supply mode for the scored final stretch, the pre-window boost on
lab tasks, a housing check sized to the window), a progression step for full-year games (the Hamlet rank's created
wealth, from wood crafts made only from surplus logs), a bed target sized for a migrant wave, an action report for the
model loop, and the ownership record the model-loop guard reads (owned orders).

Integrated measures, each scoped to the task shape it was measured on:
- the LT08 surge cluster (mpjunior92's c1f36c62, lt08probe tree): the migrant measures (a plant-floor-2 window brew,
  make_bed batches of 30, dorm capacity dug ahead of the wave) arm only on a surge task's shape — migrant text AND a
  hands-off window — so the open-play and lab tasks keep the leader's bed behaviour (surge_dorm_rooms, load()'s surge);
- the OP1 supply guards (v4 tree), full-year runs only (days >= 336): the closer's cook gate drops to one floor of
  food per citizen and the farm target rises to the population-proportional branch; the cook standings'
  plants_brewable reserve (COOK_PLANTS_RESERVE) now arms at COOK_RESERVE_DAYS so a MY1-length run keeps it too;
- food security (w5food tree): measured consumption stages (butcher, a plant-free cook standing, a Fishery without a
  fisher) while edible food drains below FOOD_ALARM_DAYS of cover, on runs of 180 days and up;
- the adaptive closer (w5close tree): a 14-day OLS per stock arms endgame_supply while a stock drains toward the
  336-day horizon, on runs of 180 days and up (stock_sliding);
- glut banking (wave3 tree, MY1_AUTOPSY): the standing brew gate keeps a max(200, one year of drink per citizen)
  cap that re-cuts to the census (sync_brew) and a caravan-scale brewable stock draws a one-shot brew (glut_bank)
  — ungated, a caravan glut hits every task;
- the full-year growth chase (V1opg tree, days >= 336 only): the crafts chase a wave-wealth target through the autumn
  caravan's reporting window, the bed stock carries a FULL_YEAR_BEDS margin, and the model's STATUS digest gains a
  growth line;
- the water-loss avoidance rules (W4water tree): dig sites next to water are dug last, water signals halt a site's dig
  until the water recedes, and a water_rising advance stop halts the dig fronts (record_water, pick_dig_site);
- the dfx containment repairs (the dfx-my15-v2/MY1-5 read, 2026-11-10): the wet-level scan walks the 5-level query
  window in spans (the old single 8-level query was bad_arguments on every day of the measured run, so the
  dry-floor exclusions ran on an empty record), a contained breach no longer releases halts (the resume must not
  re-dig the flooded stratum), and a farm plot standing on a wet level stops counting towards the farm target so
  a replacement is built on a dry one;
- the OP1 supply-priority guards (the 2026-11-09 interference read, runs/dfull-op1-hard + df2-op1-hard): the wave
  chase yields to beds, seats and barrels while the wood on hand is under logs_guard() (no standing added, no extra
  bench opened), and the chase order's amount eases from CRAFT_AMOUNT_WAVE to CRAFT_AMOUNT_BASE once this run's own
  measured wealth rate already carries the remaining fund across the reporting window (craft_amount_chase) — the
  measured clean runs (df2 OP1-1/2: amount 12, supply 1.00, logs never under 168) bound the guard's cost at zero
  there, while a logs famine can no longer be led by the craft queue;
- the winter measures (ROOT_CAUSES §C/§D/§G, 2026-11-09): an internal calendar turns the day into a season (a DF year
  is 336 days, one season 84 — docs/SUCCESS.md T_STAR) and the cook standings' plants_brewable reserve drops out of
  their when in winter, where the reserve sat unreachable (pb = 0) and inactivated every cook order; the food-security
  guard counts only orders the game still marks active; a once-a-year winter plan at the growth season's end sizes the
  winter's pantry per citizen and full-opens brewing (and cooking) for the shortfall — uncapped for a fort whose seeds
  cannot grow through winter, capped at the need for one whose can; the cook standings also carry a seeds floor
  (SEEDS_PER_PLOT per plot) so the seed-bearing plants reach the Still — brewing returns seeds, cooking never does;
  the final stretch protects the score's min leg: the glut bank draws only while drink is the short leg and the
  closer's brew standing retires when food falls while drink holds, instead of feeding the Still the food stock;
- the caravan exclusion (ROOT_CAUSES §X): the observation's stocks sum the merchants' goods (observe.lua counts map
  items without owners), so the layer tracks the announcement stream (FIRST_CARAVAN_ARRIVAL / CARAVAN_ARRIVAL until
  MERCHANTS_EMBARKED, plus a short haul-out grace) in self.caravan_active and the stock rules hold off while the
  caravan stays — the glut bank, the slide and food alarms, and the standing brew/fruit adds, until the slope records
  have drained the arrival's jump;
- the chronic-stress bedroom (ROOT_CAUSES §J): a citizen the score already counts as stressed (obs dwarves[].stress,
  DFHack's stress category <= 1, observe.lua:44) gets a private 3x3 bedroom zone with a bed and the zone assigned —
  on an unused dug room or an uncovered site, never the shared dormitory; a noble (manager / expedition leader)
  also gets an office with a chair, provisioned the way office() does for the manager;
- the wildlife nuisance response (ROOT_CAUSES §K): "Interrupted by a <animal>" cancellations spanning two different
  days (the animal DF never surfaces in threats.hostiles, where defend() finds nothing to fight) put the squad on
  the animal via squad_order attack target_ids (gameapi/manual/MANUAL.md:297 — a kill list), or create one above
  12 citizens; defend() itself is untouched.
"""
import json
import math
import re
import sys
import time
from collections import deque

from dfbench_client import ActionLimit, GameAPIError, GameClient, GameOver, HandsOff, load_task

DAY = 1200
MAX_PER_PASS = 12
MAX_PASSES = 3
DRINK_PER_CIT_YEAR = 20











GLUT_JUMP = 10

GLUT_PB = 12

MEAL_CAP = 200


COOK_PLANTS_RESERVE = 6


COOK_RESERVE_DAYS = 180



WINTER_DRINK_PER_CIT = 20


WINTER_FOOD_PER_CIT = 10
DRINK_PER_CIT_DAY = 0.06
FOOD_PER_CIT_DAY = 8 / 336
WINTER_PLAN_LATE_DAY = 220
WINTER_PLAN_LOOKAHEAD = 116




WINTER_PLAN_DOY = 235
SEASON_DAYS = 84
YEAR_DAYS = 336
SEED_CENSUS_DAYS = 5

SEED_CENSUS_EARLY_DAYS = 8





SEED_RUSH_DAYS = 10

FRUIT_WIN_DRINK_PER_CIT = 3

SEEDS_PER_PLOT = 9

CARAVAN_ARRIVALS = ("FIRST_CARAVAN_ARRIVAL", "CARAVAN_ARRIVAL")
CARAVAN_EMBARK = "MERCHANTS_EMBARKED"

CARAVAN_GRACE_DAYS = 4
CARAVAN_MAX_DAYS = 30
CARAVAN_SETTLE_DAYS = 14

BREW_SPARE_DAYS = 40







ALLOC_DRINK_PER_CIT_DAY = 0.33

ALLOC_FOOD_PER_CIT_DAY = 0.16








RATE_WINDOW = 24
RATE_MIN_PAIRS = 4
RATE_MIN_DAYS = 8
RATE_CLAMP = {"drink": (0.02, 1.0), "food": (0.01, 0.6)}
ALLOC_AHEAD = 1.5

ALLOC_SHORT_DAYS = 60
ALLOC_HOLD_MARGIN = 10
ALLOC_DWELL_DAYS = 6
LAST_STRETCH_DAYS = 60
RESERVE_BUILD_DAYS = 56
PLANT_RESERVE_PER_CIT = 2
ALLOC_BREW_MAX = 8
ALLOC_COOK_MAX = 4
BREW_END_FLOOR = 4










LEAN_DAYS = 64
LEAN_AHEAD = 1.5
LEAN_EXIT = 1.15
LEAN_BREW_AMOUNT = 2













RECYCLE_GROW_DAYS = {"plump helmet": 25, "pig tail": 25}
RECYCLE_GROW_DEFAULT = 42
RECYCLE_LEAD_DAYS = 7
RECYCLE_MIN_EMPTY = 4
RECYCLE_FOOD_DAYS = 120



RECYCLE_KEEP = 2
RECYCLE_MAX = 30
AUTOFARM_THRESHOLD = 50








MEAT_KEEP_MIN = 20
MEAT_KEEP_PER_JOB = 4
MEAT_KEEP_MAX = 10
SEEDWATCH_TARGET = 30











HOLD_GROW_DAYS = 42

HOLD_DRY_DAYS = 5

HOLD_PREP_DAYS = 14




HOLD_COVER = 1.5
HOLD_CONFIRM_DAYS = 3
HOLD_MIN = 6
HOLD_STANDING_MARGIN = 10












HOLD_F_LEAD = 2
HOLD_MID_TOL = 3.5
HOLD_RATE_DAYS = 21
BREW_DRINKS = 5








BARREL_KEEP = 1










PLANT_BARREL_FRESH_DAYS = 2
PLANT_BARREL_WAIT_DAYS = 7
BARREL_KEEP_AMOUNT = 2
SEASON_NAMES = ("spring", "summer", "autumn", "winter")










ROT_ARM_RISE = 2

ROT_ARM_DAYS = 7
ROT_KEEP = 2
ROT_BARREL_MAX = 4






PLANT_USE_AGE = 8




























LOOSE_BREW_DAYS = 5
LOOSE_HIST_DAYS = 30










ROT_SHOT_MAX = 30







F_FOOD_COVER_DAYS = 336
F_SLAUGHTER_DAYS = 5
F_SLAUGHTER_TAIL = 2


















F_SLOPE_MARGIN = 0.15
F_PLAN_SPARE = 1
F_PLAN_MIN = 3
F_PLAN_MAX = 30
F_RESERVE_FOOD_PER_CIT = 6
F_SLAUGHTER_FROM = 3
F_REC_LEAD = 14
F_LAND_DAYS = 2
F_PLAN_KEYS = ("o_brew_dry", "o_brew_mid", "o_brew_midshot", "o_brew_prelift")
F_LOAD_GAP = 7
F_SPLIT_RATES = (0.85, 1.0, 1.15)


T_STAR = 336
SMALL_ANIMALS = ("CAT", "BIRD", "RABBIT", "CAVY", "GUINEAPIG", "CHICKEN", "DUCK", "TURKEY", "PEAFOWL", "HAMSTER")








DRINK_GLUT_MARGIN = 1.5




WOOD_DRY_DAYS = 20
WOOD_DRY_LOGS = 90


WILD_ALERT_DAYS = 3






CRAFT_CHECKPOINTS = ((90, 9000), (200, 16000))
CRAFT_CHECKPOINT_DOYS = (105, 215)

CRAFT_AMOUNT_POST = 6
ENDGAME_DAYS = 64

WINDOW_PREP_DAYS = 14



SURGE_BREW_LEAD = 2


SURGE_BREW_LEAD_MAX = 10













SURGE_BRIDGE_RATE = 0.071
SURGE_WINDOW_USE = 0.049








SURGE_START_FOOD = 1
SURGE_FOOD_SAFE = 2

SURGE_BED_SITES = 4








SURGE_FIRST_WAVE = 2.0


SURGE_WAVE_WAIT_DAYS = 10
SURGE_BED_MARGIN = 12
SURGE_CARPENTERS = 4
SURGE_CARP_CIT = 30






SURGE_FLOOR_MARGIN = 16

SURGE_FLOOR_ROOM = (9, 7)











CARP_PAUSE_WAIT_DAYS = 3
CARP_PAUSE_MAX_DAYS = 15
CARP_PAUSE_COOLDOWN_DAYS = 15
BARREL_SAFE_FLOOR = 4
BREW_CANCEL_LOOKBACK_DAYS = 3
DIG_UNSAFE_RADIUS = 3
CARP_PAUSE_JOBS = {"ConstructBed": "make_bed", "ConstructTable": "make_table", "ConstructThrone": "make_chair",
                   "MakeCrafts": None}
CARP_PAUSE_RECIPES = {"make_bed", "make_table", "make_chair"}
CARP_MINER_JOBS = {"ConstructBed", "ConstructTable", "ConstructThrone", "ConstructChest", "ConstructCabinet",
                   "ConstructDoor", "ConstructHatchCover", "ConstructBin", "ConstructBox", "ConstructBucket",
                   "ConstructCrutch", "ConstructSplint", "ConstructArmorStand", "ConstructWeaponRack",
                   "MakeBarrel", "MakeCrafts", "MakeGoblet", "MakeTool"}
STAIR_WAIT_CAP_DAYS = 14
SURGE_FLOOR_STAIR_DAYS = 4
SURGE_ROOM_SITE_ONLY = True
SURGE_BED_RETRY_DAYS = 3
SURGE_STALL_DAYS = 6

SLOPE_WINDOW = 14
SLOPE_MIN_PTS = 8
SLOPE_HORIZON = 336
FYIELD_LEAD = 3

FYIELD_MARGIN = 1.5


FLIFT_CUT_SPAN = 7

FOOD_HISTORY = 14
FOOD_ALARM_DAYS = 120
REPORT_KEEP = 24
WEALTH_TARGET = 5500
PROGRESS_FROM_DAY = 20

LOG_RESERVE = 25














WAVE_WEALTH_PER_CIT = 1000
WAVE_POP_TARGET = 20
WAVE_POP_BUFFER = 1
PROGRESS_LAST_DAY = 205
CRAFT_AMOUNT_WAVE = 12

CRAFT_AMOUNT_BASE = 3
CRAFT_RATE_MARGIN = 1.25




CRAFT_RATE_SPAN = 14

CRAFT_ADAPT_MIN_DAYS = 14

BARREL_GUARD = 8

WAVE_GAP_THIRD_SHOP = 8000

WAVE_GAP_FOURTH_SHOP = 13000























LIAISON_OFFICE_DAY = 120
LIAISON_OFFICE_DOY = 135
LIAISON_EVENTS = ("LIAISON_ARRIVAL", "DIPLOMAT_ARRIVAL", "TRADE_DIPLOMAT_ARRIVAL")
HEAD_POSITIONS = ("EXPEDITION_LEADER", "MAYOR", "BARON", "BARONESS", "COUNT", "COUNTESS", "DUKE", "DUCHESS",
                  "MONARCH")
CRAFT_STALL_DAYS = 7
CRAFT_STALL_RISE = 60
CRAFT_ALT_AMOUNT = 4
HAMLET_WEALTH = 5000

FULL_YEAR_BEDS = 6














HOUSE_AFTER_FARMS = 2
HOUSE_FULL_DAYS = 3
HOUSE_ROOM = (9, 7)
HOUSE_PENDING_MAX = 30
OVERFLOW_ERROR = "no_space"
OVERFLOW_MIN_TILES = 6
ZONE_MAX = 20



PLACE_MAX = 40


REBUILD_GAP_DAYS = 10


WATER_QUERY_RADIUS = 12
WATER_CACHE_DAYS = 3
WATER_PROBES_PER_DAY = 6

WATER_EVENT_LOOKBACK_DAYS = 7
WATER_SITE_MARGIN = 2
WATER_MATERIAL_CHARS = "Rkoi"





BREACH_DIG_WINDOW_DAYS = 10
BREACH_DEEP_GAIN = 50
BREACH_RELEASE_GAIN = 10








BREACH_FORT_MIN = 4
BREACH_CLEAR_SCANS = 3
WET_SCAN_LEVELS = 8
WET_QUERY_SPAN = 4


WET_DEPTH_MIN = 1






WATER_DIG_MARGIN = 1
WET_BOX_MARGIN = 1
DIG_BOX_R = (9, 7)






RISE_MARGIN = 3





STRESS_CATEGORY = 1
STRESS_ROOM_SIZE = 3
STRESS_ROOM_CAP = 3




STRESS_RISE_CATEGORY = 2









STRESS_CORNER = True






BED_ROOM_HOLD = True








BED_HELD_BOX = True
BED_ROOM_DRINK_DAYS = 20






DORM_CORNER_HOLD = True



STRESS_WATCH_CATEGORY = 2
STRESS_WATCH_NEEDS = 4




DORM_BED_ROOM_MAX = 6






BEDROOM_PASS_CAP = 2
BEDROOM_DIG_INFLIGHT = 2
BEDROOM_BED_BATCH = 4
MEETING_MIN_TILES = 6







BEDROOM_OWN_KINDS = ("bedroom", "bed", "office")







MEETING_USE_LOOKS = 60
MEETING_USE_MIN = 0.1
MEETING_USE_REACH = 12







MEETING_SHAFT_TILES = 6






MEETING_FAR_WAIT_DAY = 30



MEETING_NEAR_DAY = 15
MEETING_FOOT_TILES = 3
MEETING_SHAFT_LEVELS = 6







SHAFT_PEOPLE_MIN_TILES = 9







FAR_FLOOR_MIN = 6
FLOOR_PROBE_DAYS = 3
NOFLOOR_DAYS = 10
FLOOR_SHAPES = set(".,o\"sw")
FURNITURE_BUILDINGS = {"bed", "table", "chair", "door", "box", "cabinet", "armorstand", "weaponrack", "statue",
                       "coffin", "chest", "coffer", "hatch"}


WILDLIFE_GAP_DAYS = 4
WILDLIFE_MIN_CIT = 12
WILDLIFE_SQUAD_SIZE = 4
MOOD_WORKSHOP = {
    "WOODCRAFT": "Craftsdwarfs", "STONECRAFT": "Craftsdwarfs", "BONECARVE": "Craftsdwarfs", "CARPENTRY": "Carpenters",
    "MASONRY": "Masons", "WOOD_BURNING": "WoodFurnace", "GLASSMAKER": "GlassFurnace", "TANNER": "Leatherworks",
    "LEATHERWORK": "Leatherworks", "WEAVING": "Loom", "CLOTHESMAKING": "Clothiers", "FORGE_WEAPON": "MetalsmithsForge",
    "FORGE_ARMOR": "MetalsmithsForge", "FORGE_FURNITURE": "MetalsmithsForge", "METALCRAFT": "MetalsmithsForge",
    "CUTGEM": "Jewelers", "ENCRUSTGEM": "Jewelers", "MECHANICS": "Mechanics", "POTTERY": "Kiln", "BOWYER": "Bowyers",
}


def surge_dorm_rooms(cit):
    """Dorm rooms a migrant-wave fort needs: the wave lifts the fort to cit + 24 residents and a 9x7 room
    holds about 30 bed slots (2 open tiles per bed) — mpjunior92's c1f36c62 sizing (residents = cit + 24)."""
    return max(1, -(-(cit + 24) // 30))


def ols_slope(pts):
    """Ordinary least squares slope (units per day) of (day, value) points; 0 for fewer than two days or no spread.
    Real day values are used, so the cadence gaps (the loop advances two days a pass) do not tilt the fit."""
    n = len(pts)
    if n < 2:
        return 0.0
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    if not sxx:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in pts) / sxx


def log(kind, **kw):
    print(json.dumps({"t": round(time.time(), 2), "kind": kind, **kw}, default=str), flush=True)


def d(v):
    return v if isinstance(v, dict) else {}


def lst(v):
    return v if isinstance(v, list) else []


def query_result(r):
    """cx: the payload of a /query/<name> answer, or None when the server refused it. The real answers (every
    harness-*.api.jsonl, /query/map and /query/units, 2026-11-10) carry the envelope (day, tick, days_left,
    game_over, query) with the payload and its own ok under "result" and NO top-level ok; a refusal is the
    envelope with a top-level ok false and error_code, and no result (e.g. bad_arguments "at most 5 levels").
    Reading a top-level ok on a success — the old water_measure / record_wet_levels test — failed every answer."""
    r = d(r)
    if r.get("ok") is False or "result" not in r:
        return None
    res = r.get("result")
    if not isinstance(res, dict) or res.get("ok") is False:
        return None
    return res


def query_error(r):
    """The refusal's error_code (or a short reason) of a /query answer query_result() rejected."""
    r = d(r)
    return str(r.get("error_code") or d(r.get("result")).get("error_code") or
               ("no result" if "result" not in r else "result not ok"))[:80]


def covers(area, item):
    return (area["z"] == item["z"] and area["x"] <= item["x"] and area["y"] <= item["y"]
            and area["x"] + area["w"] >= item["x"] + item.get("w", 1)
            and area["y"] + area["h"] >= item["y"] + item.get("h", 1))



STOCK_ITEM = {
    "prepared_meals": {"item_type": "FOOD"},
    "plants_total": {"item_type": "PLANT", "flags": ["unrotten"]},
    "plants_brewable": {"item_type": "PLANT", "flags": ["unrotten"], "reaction_product": "DRINK_MAT"},
    "food_edible": {"item_type": "ANY", "flags": ["unrotten", "cookable"]},
    "drink": {"item_type": "DRINK"},
    "barrels_empty": {"item_type": "BARREL", "flags": ["empty"]},
}


def as_item(c):
    """One add_order when clause ({stock, below|at_least}) as an add_manager_order condition."""
    c = d(c)
    out = dict(STOCK_ITEM[c["stock"]])
    for k in ("below", "at_least"):
        if k in c:
            out[k] = c[k]
    return out


BARREL_AHEAD_MAX = 60


STILL_MAX = 3
STILL_BACKLOG = 15









KITCHEN_MAX = 2
KITCHEN_BACKLOG = 8









COOK_STALL_DAYS = 1








PRESS_ON = 4
PRESS_OFF = 0
PRESS_BARRELS_LOW = 4

PRESS_BARRELS_FREE = 10
PRESS_CARPENTERS = 4

PRESS_CRAFT_AMOUNT = 1
PRESS_BARREL_BATCH = 15
PRESS_JOBS_PER_BENCH = 2
PRESS_FROM_DAY = 20








HARVEST_YIELD = 1.2
HARVEST_CARP_SHORT = 8













HARVEST_PRESS_ON = HARVEST_CARP_SHORT
HARVEST_CARPENTERS = 6



HARVEST_CARP_SPARE_LOGS = 4






HARVEST_PRESS_FROM_DAY = 10

HARVEST_IDLE_PLANTS = 10











LABOR_FROM_DAY = 20








PLANT_CENSUS_DAYS = 1






BREW_SHOT_KEYS = ("o_brew_rot", "o_brew_seed", "o_brew_alloc", "o_brew_glut")




SEED_COND_TOL = 4
BREW_FLOOR_TOL = 0.25
HARVEST_STALL_MIN = 5
HARVEST_STALL_DAYS = 10





ALERT_QUIET_DAYS = 7



WAVES_EXPECTED = 2
WAVE_MEAN = 5.5
EMBARK_PARTY = 7
WILD_TROOP_CANCELS = 3










WILD_GONE_DAYS = 1
WILD_NEAR_TILES = 30
WILD_NEAR_Z = 3
WILD_REST_DAYS = 2
WILD_MEMORY_DAYS = 20









WILD_BUDGET_DAYS = 14
WILD_BUDGET_WINDOW = 28
WILD_EVIDENCE_DAYS = 3
WILD_CLOSE_TILES = 10
WILD_APPROACH_TILES = 3








BUDGET_FIGHT_DAYS = 1



















MARK_LEARN_INTERRUPTS = 3
DANGER_SEED = ("gray langur", "langur", "rhesus macaque", "macaque", "monkey", "baboon", "kea", "carnotaurus",
               "kingsnake", "sea lamprey", "lamprey", "alligator", "crocodile", "common snapping turtle",
               "alligator snapping turtle", "wolf", "badger", "bear", "cougar", "jaguar", "leopard", "lion", "tiger")



DANGER_WEAK = ("gray langur", "langur", "rhesus macaque", "macaque", "monkey", "kea")
MARK_SQUAD_MIN = 4













MARK_RESCUE_ARMED = 2
MARK_HOLD_DAYS = 3
CAP_DEFER_DAYS = 3














FIGHT_HOLD_DAYS = 1



















MUSTER_IDLE_CAP_DAYS = 3









SHAFT_GUARD_TILES = None
SHAFT_GUARD_HOLD_DAYS = 1












MUSTER_CLEAR_TILES = 30















MARK_WAIT_MAX_DAYS = 1




















STRANDED_WADE_DEPTH = 4
STRANDED_SCAN_DAYS = 3
STRANDED_FAR_TILES = 20
STRANDED_RADIUS = 20









STRANDED_JOIN_DAYS = 2
STRANDED_HOME_DAYS = 3









STRANDED_ALERT_TILES = 60
STRANDED_FLOOR = frozenset('.,"so<>X^bwt')




GATE_GONE_DAYS = 2









SHAFT_GUARD_TOP = True



























ACCESS_CAP_DAYS = 10













TRAP_POKE_DAYS = 2





POCKET_LEVELS = 5
POCKET_READS_PER_DAY = 4
TRAP_WOOD_SPARE = 10
TRAP_WATER_MARGIN = 3
TRAP_POKES = 4
TRAP_SHOP = "Carpenters"
TRAP_SEEN = 2


ACCESS_WINDOW_DAYS = 2










INVADER_ENTRANCE_TILES = 15









FIGHT_RATIO = 1.5
FIGHT_RETREAT_RATIO = 1.0
FIGHT_ENDGAME_DAYS = 15
FIGHT_ENDGAME_RATIO = 1.0
FIGHT_ARMED = 1.0
FIGHT_UNARMED = 0.75
FIGHT_UNARMED_VS_ARMED = 0.25
FOE_ARMED = 1.0
FOE_UNARMED = 0.4
FOE_OTHER = 1.0











BUCKET_KEEP = 2
BUCKET_WOOD_FLOOR = 2












CUP_FROM_DAY = 3
CUP_SPARE = 4
CUP_BATCH = 2
GIVE_WATER_RE = re.compile(r"cancels give water: ([a-z][a-z ]*)", re.I)



SPEAR_RETRY_DAYS = 5
SPEAR_LIFETIME = 12
SQUAD_MIN_CIT = 10
SQUAD_MILITARY = ("recruit", "soldier", "axedwarf", "speardwarf", "swordsdwarf", "macedwarf", "hammerdwarf",
                  "marksdwarf", "wrestler", "pikedwarf", "lasher", "bowdwarf", "crossbowdwarf", "militia",
                  "axeman", "spearman", "swordsman", "maceman", "hammerman", "marksman", "pikeman", "elite")
SQUAD_TOOL = ("miner", "woodcutter")
SQUAD_TOOL_LABORS = ("MINE", "CUTWOOD")
SQUAD_ESSENTIAL = ("woodworker", "carpenter", "brewer", "cook", "farmer", "planter", "mason", "manager",
                   "expedition leader", "bookkeeper", "broker", "doctor", "chief medical", "fisher")




SQUAD_SOLE_LABORS = ("FISH",)
SQUAD_COMBAT_SKILLS = ("AXE", "SWORD", "SPEAR", "MACE", "HAMMER", "DAGGER", "PIKE", "WHIP", "CROSSBOW", "BOW",
                       "MELEE_COMBAT", "WRESTLING", "DODGING", "SHIELD", "ARMOR")
MARK_RANGE = 60
MARK_RANGE_Z = 10











PREEMPT_TILES = MARK_RANGE
MARK_NEW_DAYS = 5
PREEMPT_WINDOW_DAYS = 1










SHELTER_SIDE_MAX = 40
SHELTER_PER_PASS = 3





BIG_FREE_DAYS = 6
DANGER_BIG = ("carnotaurus", "alligator", "crocodile", "bear", "wolf", "cougar", "jaguar", "leopard", "lion", "tiger")





ENTRANCE_MAX = 4









HATCH_SPARE = 1
HATCH_WOOD_FLOOR = 2
HATCH_ORDER_CAP = 4 * ENTRANCE_MAX









HATCH_FIRST_EARLY = True
HATCH_FIRST_DAYS = 3










ENTRANCE_LIST_MAX = 8

















GATE_RADIUS = 8
GATE_LEVELS = 4
GATE_QUERY_RADIUS = 10
GATE_LANDING_MAX = 40
GATE_DOWN = set("X> v")
GATE_SOLID = set("#?!FT")















OFFICE_BEAST_TILES = 15
OFFICE_BEAST_LEVEL_TILES = WILD_NEAR_TILES
OFFICE_CLEAR_DAYS = 1















OPEN_WALK = set(".,o\"sw^")
OPEN_PROBE_DAYS = 3
OPEN_SITE_TOOLS = ("place_furniture", "make_zone", "create_burrow")










SHELTER_TILES_PER_CIT = 3






OFFICE_TEMP_KEYS = ("office_box_chair", "office_box_zone", "office_temp_zone", "office_temp_chair")







OFFICE_FULL_CIT = 14







OFFICE_CHAIR_FIRST = True










LEVEL_RADIUS = 20
LEVEL_WALK = set(".,o\"sw^<>Xv_")











SHAFT_PEOPLE_GAP = 6






ROCK_DORM = True





ROCK_DORM_WAIT = False
SHAFT_HATCH_TRIES = 4


def big_race(race):
    """A units-query race of a large dangerous beast: one DANGER_BIG name as its last words
    (CARNOTAURUS, GRIZZLY_BEAR, GIANT_ALLIGATOR; not ALLIGATOR_SNAPPING_TURTLE, not WOLF_SPIDER)."""
    w = str(race or "").lower().replace("_", " ").split()
    return any(w[-len(n.split()):] == n.split() for n in DANGER_BIG if w)














GRAZER_RACES = ("HORSE", "REINDEER", "ALPACA", "DONKEY", "CAMEL", "BUFFALO", "LLAMA", "RABBIT", "CAVY", "YAK", "GOAT",
                "MULE", "COW", "SHEEP", "PIG")
GRAZER_CULL_PER_PASS = 2












BUTCHER_FRAME_IDLE_DAYS = 3









STRAY_CULL = True
STRAY_CULL_PER_PASS = 3
STRAY_RACE = {"guineahen": "GUINEAFOWL", "guineacock": "GUINEAFOWL", "keet": "GUINEAFOWL", "guineafowl": "GUINEAFOWL",
              "peahen": "PEAFOWL", "peacock": "PEAFOWL", "peachick": "PEAFOWL", "peafowl": "PEAFOWL",
              "turkey": "TURKEY", "poult": "TURKEY", "gobbler": "TURKEY", "goose": "GOOSE", "gander": "GOOSE",
              "gosling": "GOOSE", "duck": "DUCK", "drake": "DUCK", "duckling": "DUCK", "chicken": "CHICKEN",
              "rooster": "CHICKEN", "yak": "YAK", "sheep": "SHEEP", "ram": "SHEEP", "ewe": "SHEEP", "lamb": "SHEEP",
              "rabbit": "RABBIT", "bunny": "RABBIT", "dog": "DOG", "puppy": "DOG", "cat": "CAT", "kitten": "CAT",
              "horse": "HORSE", "stallion": "HORSE", "mare": "HORSE", "llama": "LLAMA", "alpaca": "ALPACA",
              "mule": "MULE", "donkey": "DONKEY", "reindeer": "REINDEER", "buffalo": "BUFFALO", "goat": "GOAT",
              "pig": "PIG", "piglet": "PIG", "cavy": "CAVY", "camel": "CAMEL", "emu": "EMU", "ostrich": "OSTRICH"}
STRAY_FEMALE = {"hen", "guineahen", "peahen", "doe", "ewe", "cow", "sow", "mare", "jenny", "nanny", "jill"}
STRAY_MALE = {"bull", "ram", "cock", "guineacock", "peacock", "rooster", "gobbler", "drake", "gander", "buck",
              "stallion", "boar", "billy", "jack", "tom", "hob"}
STRAY_YOUNG = {"keet", "peachick", "poult", "gosling", "duckling", "chick", "lamb", "bunny", "puppy", "kitten", "calf",
               "foal", "piglet", "kid", "cub", "pup", "kit", "hatchling", "joey"}


def stray_spec(name):
    """cx stray cull: (race fragment, female or None, adult or None) for a report's stray animal name ('blue peahen'
    -> ('PEAFOWL', True, True), 'yak bull' -> ('YAK', False, True), 'turkey hen' -> ('TURKEY', True, True)); the race
    is None when no word names one (then nothing is marked)."""
    w = str(name or "").lower().replace("stray ", " ").split()
    race = next((STRAY_RACE[x] for x in w if x in STRAY_RACE and x not in ("hen", "chick")), None)
    if race is None and any(x in ("hen", "chick") for x in w):
        race = "CHICKEN"
    female = True if any(x in STRAY_FEMALE for x in w) else False if any(x in STRAY_MALE for x in w) else None
    adult = False if any(x in STRAY_YOUNG for x in w) else (True if female is not None else None)
    return race, female, adult


def grazer_race(race):
    """A units-query race of a grazing animal: one GRAZER_RACES word in it (CAMEL_2_HUMP, WATER_BUFFALO; not GUINEAPIG)."""
    return any(w in GRAZER_RACES for w in str(race or "").upper().split("_"))


COMBAT_VERBS = ("bites", "scratches", "punches", "kicks", "strikes", "charges at", "attacks", "grabs", "snatches at",
                "gores", "stings", "slaps", "shakes", "strangles", "butts", "pushes", "rams", "claws", "tackles",
                "bashes", "hacks", "stabs", "slashes", "squeezes", "jumps on", "lunges at", "misses", "latches onto")
COMBAT_RE = re.compile(r"^the ([a-z][a-z' \-]*?) (?:%s)(?: at)? the ([a-z][a-z' \-]*?)(?: in | by | but | with | "
                       r"around | on |[!.,]|$)" % "|".join(re.escape(v) for v in COMBAT_VERBS))
SEX_AGE = {"boar", "sow", "cub", "pup", "calf", "kitten", "kit", "chick", "hatchling", "joey", "foal", "bull", "cow",
           "buck", "doe", "drake", "hen", "ram", "ewe", "stallion", "mare", "jack", "jenny", "billy", "nanny", "jill",
           "hob", "male", "female", "child", "baby"}
CITIZEN_WORDS = {"dwarf", "expedition leader", "militia commander", "militia captain", "manager", "bookkeeper",
                 "broker", "chief medical dwarf", "mayor", "baron", "baroness", "count", "countess", "duke", "duchess",
                 "king", "queen", "monarch", "sheriff", "captain of the guard", "recruit", "soldier", "hammerdwarf",
                 "axedwarf", "swordsdwarf", "speardwarf", "macedwarf", "marksdwarf", "wrestler", "peasant", "child"}









PROF_REPORT_NOUNS = {"diagnostician": "diagnoser"}
PROF_STEM = 7
PROF_STEM_TAIL = 4


def citizen_noun(noun, profs):
    """cx profession match: True when a combat report's noun names a citizen of this look (profs: lowercase
    professions, CITIZEN_WORDS included)."""
    n = str(noun or "").lower().strip()
    if not n or n.startswith("stray ") or "(tame)" in n:
        return False
    if n in profs or n in CITIZEN_WORDS:
        return True
    if PROF_REPORT_NOUNS.get(n) in profs:
        return True
    k = n.replace(" ", "").replace("-", "")
    for p in profs:
        q = str(p).replace(" ", "").replace("-", "")
        i = 0
        while i < min(len(k), len(q)) and k[i] == q[i]:
            i += 1
        if i >= PROF_STEM and min(len(k), len(q)) - i <= PROF_STEM_TAIL:
            return True
    return False


def map_tiles(answers):
    """cx stranded: ({(x, y, z): shape char}, {(x, y, z): water depth}, set of levels read) from /query/map answers
    (query_result payloads: x1, y1, levels[] {z, shape}, liquid[] {x, y, z, depth, magma}). A later answer wins."""
    shape, water, zs = {}, {}, set()
    for res in answers:
        res = d(res)
        x1, y1 = res.get("x1"), res.get("y1")
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (x1, y1)):
            continue
        for lv in lst(res.get("levels")):
            z = d(lv).get("z")
            if not isinstance(z, int) or isinstance(z, bool):
                continue
            zs.add(z)
            for i, row in enumerate(lst(d(lv).get("shape"))):
                for j, ch in enumerate(str(row)):
                    shape[(x1 + j, y1 + i, z)] = ch
        for q in lst(res.get("liquid")):
            q = d(q)
            if q.get("magma"):
                continue
            k = (q.get("x"), q.get("y"), q.get("z"))
            if all(isinstance(v, int) and not isinstance(v, bool) for v in k):
                water[k] = q.get("depth") or 0
    return shape, water, zs


def walk_region(shape, water, start, wade=None, limit=200000):
    """cx stranded: (tiles, open) — the walkable region from start (8-way on a level, ramps up/down, stairs) over the
    read tiles, a tile walkable when its shape is floor-like (STRANDED_FLOOR) and its water depth <= wade; open is
    True when the region reaches a way off the read levels (a ramp up from the top level, a ramp/stair down from the
    bottom one, a stair up from the top) or the limit, so nothing can be said about where it leads."""
    wade = STRANDED_WADE_DEPTH if wade is None else wade
    zs = {k[2] for k in shape}
    if not zs:
        return set(), True
    ztop, zbot = max(zs), min(zs)

    def walk(p):
        return shape.get(p) in STRANDED_FLOOR and (water.get(p) or 0) <= wade

    if not walk(start):
        return set(), True
    seen, todo, opened = {start}, [start], False
    while todo:
        x, y, z = p = todo.pop()
        ch = shape.get(p)
        if (ch == "^" and z == ztop) or (ch in ("<", "X") and z == ztop) or (ch in (">", "X") and z == zbot):
            opened = True
        nxt = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nxt.append((x + dx, y + dy, z))
                if ch == "^":
                    nxt.append((x + dx, y + dy, z + 1))
                if shape.get((x + dx, y + dy, z)) == "v":
                    if z == zbot:
                        opened = True
                    elif shape.get((x + dx, y + dy, z - 1)) == "^":
                        nxt.append((x + dx, y + dy, z - 1))
        if ch in ("<", "X") and shape.get((x, y, z + 1)) in (">", "X"):
            nxt.append((x, y, z + 1))
        if ch in (">", "X") and shape.get((x, y, z - 1)) in ("<", "X"):
            nxt.append((x, y, z - 1))
        for q in nxt:
            if q not in seen and walk(q):
                seen.add(q)
                todo.append(q)
        if len(seen) > limit:
            return seen, True
    return seen, opened


def stranded_of(shape, water, citizens, home, surface, wade=None):
    """cx stranded: the ids of the citizens on the surface (z >= surface) whose walkable region holds none of the home
    tiles (the wagon, the surface entrances: (x, y, z)) and is closed in the read levels. A citizen whose own tile was
    not read, or not walkable, or whose region is open, is not stranded (nothing measured)."""
    out, regions = set(), []
    for c in citizens:
        c = d(c)
        p = (c.get("x"), c.get("y"), c.get("z"))
        if c.get("id") is None or not all(isinstance(v, int) and not isinstance(v, bool) for v in p)\
                or not isinstance(surface, int) or p[2] < surface:
            continue
        known = next((r for r in regions if p in r[0]), None)
        if known is None:
            tiles, opened = walk_region(shape, water, p, wade)
            if not tiles:
                continue
            known = (tiles, opened, bool(tiles & set(home)))
            regions.append(known)
        tiles, opened, at_home = known
        if not opened and not at_home:
            out.add(c["id"])
    return out


def site_key(sid):
    """cx: a site id's sort key — letters, then the number as a number (E2 before E10; others as text)."""
    m = re.fullmatch(r"([A-Za-z]*)(\d+)", str(sid))
    return (m.group(1), int(m.group(2)), "") if m else (str(sid), -1, str(sid))


def mark_name(text):
    """A species name from a report, folded the way the units query's race folds: lowercase words, the sex/age word
    dropped ('badger boar' -> 'badger'). None for the fortress's own animals and for nothing left."""
    t = str(text or "").lower().replace("_", " ").strip()
    if not t or "stray" in t.split() or "(tame)" in t or t in ("dwarf", "combat"):
        return None
    w = [x for x in t.split() if x not in SEX_AGE]
    return " ".join(w) or None


def race_matches(race, name):
    """A units-query race against a marked name: every word of the name among the race's words
    (GRAY_LANGUR ~ 'langur', BIRD_KEA ~ 'kea')."""
    r = set(str(race or "").lower().replace("_", " ").split())
    n = str(name or "").lower().split()
    return bool(n) and set(n) <= r


def when_sig(items):
    """A comparable signature of a when list, in either the request form ({stock|item_type.., below|at_least}) or
    the observed form ({item_type, flags, test, value, stock?}, MANUAL.md orders[].when) — the observation never
    echoes below/at_least, so comparing the raw lists recut every standing on every check (the real game's
    sync_brew read when[0].below as None and cancelled o_brew every 4 days: dw6-lt08-hard o_brew_recut)."""
    out = []
    for c in lst(items):
        c = d(c)
        if "below" in c or "at_least" in c:
            test = "LessThan" if "below" in c else "AtLeast"
            val = c.get("below", c.get("at_least"))
        else:
            test, val = c.get("test"), c.get("value")
        stock = c.get("stock")
        if stock in STOCK_ITEM:
            it = STOCK_ITEM[stock]
            key = (it["item_type"], it.get("reaction_product"))
        else:
            it_t = str(c.get("item_type") or "ANY").upper()
            key = (it_t, c.get("reaction_product"))
        out.append((key, test, val))
    return out


def when_value(items, i=0):
    """The threshold of a when list's i-th clause in either form, or None."""
    s = when_sig(items)
    return s[i][2] if len(s) > i else None


class Overseer:
    def __init__(self, game, goal="", days=0):
        self.game = game
        self.surge_wish = "migrant" in str(goal).lower()


        self.days = days or 0
        self.tries, self.last = {}, {}
        self.roles = {}
        self.room_box = {}

        self.brew_orders = set()
        self.now = 0
        self.alert_since = None
        self.hands_off = None
        self.days_left = None
        self.day = None
        self.owned = set()
        self.overflow = set()
        self.last_place = {}
        self.report = []
        self.done = set()
        self.food_hist = deque(maxlen=FOOD_HISTORY)
        self.rate_hist = deque(maxlen=RATE_WINDOW)
        self.stock_hist = deque(maxlen=SLOPE_WINDOW)
        self.stock_day = None
        self.sliding = False
        self.glut_prev = None
        self.glut_jump = 0
        self.cup_target = None
        self.key_order = {}


        self.caravan_cursor = None
        self.caravan_probe_day = None
        self.caravan_active = False
        self.caravan_last_day = None
        self.caravan_arrival_day = None
        self.caravan_leave_day = None

        self.winter_plan_year = None
        self.craft_mark = None
        self.craft_amount_day = None
        self.craft_desired = None

        self.pop_prev = None
        self.waves = 0
        self.rank_note = False
        self.stall_note = False
        self.window_fund = None

        self.water_halts = {}
        self.water_cache = {}
        self.water_cache_day = {}
        self.water_probe_day = {}
        self.water_probes, self.water_probe_day_no = 0, None
        self.water_event_tick = None
        self.dig_at_water = []

        self.water_base = None
        self.breach = None
        self.wet_z = set()
        self.fort_water_memo = (None, None)
        self.gain_outside = False
        self.fort_dry_scans = 0
        self.fort_dry_day = None
        self.shafts = {}
        self.scan = (None, [])
        self.rise_watch = None
        self.wet_day = None
        self.hatch_id = None
        self.flood_locked = set()
        self.hatch_water_memo = {}
        self.wet_skip_day = {}

        self.shop_stuck = {}
        self.frame_idle = {}
        self.frame_seen = {}
        self.dead_w_sites = set()


        self.site_mem = {}
        self.wagon_seen = None
        self.mem_tried = set()

        self.zone_banned = set()
        self.place_banned = set()
        self.f_yield_food_t = None
        self.f_lift_base = None
        self.office_tile = None
        self.office_yield = None
        self.office_shelter_tried = set()
        self.open_maps = {}
        self.level_maps = {}
        self.shelter_level_in = set()



        self.stress_done = set()
        self.stress_zone = {}
        self.meeting_looks = [0, 0, 0]
        self.meeting_looks_tick = None
        self.stress_seen = {}
        self.bed_zone = {}
        self.stress_rooms = set()

        self.wild_day = {}
        self.wild_from = {}
        self.wild_act_stamp = None
        self.loads = 0

        self.alloc = None
        self.alloc_day = None
        self.seeds_cond_ok = True
        self.census_day = None
        self.census = {}
        self.fruit_seen = False
        self.hold_armed = False
        self.hold_seen_day = None
        self.hold_mode = None
        self.f_rec = []
        self.f_plan_key = None
        self.barrel_lost_day = None
        self.own_seeds = {}
        self.own_food = None
        self.own_plants = None
        self.merchant_plants = None
        self.f_dry_floor = None
        self.f_reserve_logged = False
        self.wild_alert_since = None
        self.wild_watch = {}
        self.wild_rest_until = None
        self.access_tick = None
        self.access_from = None
        self.access_drink = None
        self.access_log_day = None
        self.invader_window = None
        self.invader_guard = None
        self.invader_guard_foot = False
        self.invader_defer_day = None
        self.invader_unguarded_day = None
        self.fight_log_day = None
        self.guard_need_why = None
        self.muster = None
        self.muster_since = None
        self.muster_contact = None
        self.shaft_since = None
        self.shaft_contact = None
        self.gate_post = False
        self.shaft_rest = False
        self.mark_wait_since = None
        self.gate_waiting = False
        self.gate_mark_seen = None
        self.gear_cache = None
        self.gear_where = None
        self.squad_post = None
        self.armed_seen = {}
        self.duty_from = None
        self.duty_seen = False
        self.metal_refused = False
        self.equip_day = None
        self.spears_ordered = 0
        self.access_look = None
        self.safe_held = False
        self.safe_log_day = None
        self.wild_dist_prev = {}
        self.wild_dist_load = None
        self.lock_skip_day = None
        self.wild_units_memo = None
        self.wild_spans = []
        self.wild_evidence = {}
        self.wild_fight = {}
        self.wild_dist = {}
        self.event_seen = {}
        self.mark_interrupts = {}
        self.bed_full = {}
        self.seat_full = {}
        self.floor_maps = {}
        self.nofloor = {}
        self.house_full_day = None
        self.seat_nobox_day = None
        self.seat_refused_day = None
        self.new_zones = []
        self.pend_mark = None
        self.rot_seen = False
        self.pass_days = []
        self.rot_brews = set()
        self.recycle_brews = set()
        self.stall_brews = set()
        self.stall_memo = None
        self.stall_on = False
        self.cook_wait_since = None
        self.kitchen_busy_since = None
        self.brew_shots = {}
        self.fruit_census_day = None
        self.seed_wait = 0
        self.kind_seasons = {}
        self.rot_prev = None
        self.rot_hist = []
        self.press_on = False
        self.press_stand = False
        self.press_harv = False
        self.kind_brew = {}
        self.idle_days = []
        self.plant_age = []
        self.age_day = None
        self.wood_hist = []
        self.press_memo = None
        self.press_day = None
        self.labor_on = False
        self.labor_memo = None
        self.labor_nojob = 0
        self.plant_census_day = None
        self.in_plot = None
        self.plant_loose = None
        self.loose_hist = []
        self.stall_since = None
        self.stall_logged = False
        self.alert_seen_day = None
        self.mig_prev = None
        self.mig_start = None
        self.mig_waves = 0
        self.wealth_hist = deque(maxlen=CRAFT_STALL_DAYS * 4)
        self.plan_key = None
        self.liaison_seen = False
        self.head_zones = set()
        self.lean_drink = None

        self.marked = {n: "seed" for n in DANGER_SEED}
        self.mark_station = None
        self.mark_kind = None
        self.plot_rooms = set()
        self.bed_held = set()
        self.mark_hold = None
        self.mark_settled = {}
        self.mark_last_seen = {}
        self.mark_arrived = {}
        self.water_rise_tick = None
        self.risk = []
        self.mark_query = None
        self.shelter_made = False
        self.shelter_added = set()
        self.shelter_skip = set()
        self.entrances = {}
        self.alert_locked = set()
        self.trap_last = None
        self.pocket_memo = {}
        self.pocket_reads = (None, 0)
        self.trap_pokes = 0
        self.trap_seen = 0
        self.entrance_occupied = set()
        self.gate_top = False
        self.big_log_day = None
        self.hatch_ordered = 0
        self.shaft = None
        self.shaft_stop = False
        self.dig_batches = []
        self.dig_unsafe = set()
        self.order_src = {}
        self.carp_pause = None
        self.carp_capped_day = None
        self.brew_cancel_day = None
        self.batch_seen = {}
        self.floor_stair_sent = {}
        self.shaft_open_days = []
        self.stranded = set()
        self.stranded_day = None
        self.stranded_known = set()
        self.stranded_fort = set()
        self.home_call = None
        self.strand_skipped = {}
        self.gates = {}
        self.gate_seen = {}
        self.gate_probe_day = None
        self.gate_door_ordered = 0
        self.shelter_boxes = {}
        log("danger_list", seed=sorted(self.marked), weak=list(DANGER_WEAK))


    def may(self, key, retry=2, limit=6):
        return self.tries.get(key, 0) < limit and self.now - self.last.get(key, -10 ** 9) >= retry * DAY

    def act(self, key, tool, args, retry=2, limit=6):
        """One rate-limited action. Returns the response if it ran, else None."""
        if key in self.done or not self.may(key, retry, limit):
            return None
        if self.carp_paused_order(key, tool, args):

            self.last[key] = self.now
            if self.may("carp_hold_log_" + key, 1, 10 ** 6):
                self.last["carp_hold_log_" + key] = self.now
                log("carp_pause_hold", day=self.day, key=key, tool=tool, args=args)
            return {"ok": False, "error_code": "carp_pause", "local": True,
                    "error": "not run: the layer's carpentry orders wait while the miner digs"}
        if tool == "place_furniture" and self.floor_refused(args.get("site"), args.get("w"), args.get("h")):


            return {"ok": False, "error_code": OVERFLOW_ERROR, "local": True,
                    "error": "no free floor tile (this box answered so and nothing on its site changed since)"}
        if tool in OPEN_SITE_TOOLS and key not in OFFICE_TEMP_KEYS\
                and str(args.get("site") or "")[:1] in (("A", "R") if tool == "create_burrow" else ("A",)):

            n_open = self.box_open(self.call_box({"site": args["site"]} if str(args["site"])[:1] == "A" else args))
            if n_open:

                self.tries[key] = self.tries.get(key, 0) + 1
                self.last[key] = self.now
                if self.may("site_open_log_" + key, 1, 10 ** 6):
                    self.last["site_open_log_" + key] = self.now
                    log("site_open", day=self.day, key=key, tool=tool, args=args, outside=n_open)
                return {"ok": False, "error_code": "site_open", "local": True,
                        "error": "not run: %d walkable outside tile(s) in the box" % n_open}
        if tool == "dig_stairs" and str(args.get("site") or "")[:1] == "S":
            hold = "the fort already has %d surface entrances (the observation lists %d; an unlisted one takes no " \
                "hatch)" % (len(self.entrances), ENTRANCE_LIST_MAX) if len(self.entrances) >= ENTRANCE_LIST_MAX else None
            if hold:

                self.last[key] = self.now
                if self.may("entrance_hold_log_" + key, 1, 10 ** 6):
                    self.last["entrance_hold_log_" + key] = self.now
                    log("entrance_hold", day=self.day, key=key, args=args, why=hold)
                return {"ok": False, "error_code": "entrance_hold", "local": True, "error": "not run: " + hold}
            box = self.call_box({"site": args.get("site"), "w": 1, "h": 1})
            near = self.beasts_near(dict(zip(("x", "y", "z", "w", "h"), box)), WILD_NEAR_TILES, WILD_NEAR_Z)\
                if box else []
            if near:

                self.last[key] = self.now
                if self.may("dig_beast_log_" + key, 1, 10 ** 6):
                    self.last["dig_beast_log_" + key] = self.now
                    log("dig_beast_hold", day=self.day, key=key, args=args, near=near[:3])
                return {"ok": False, "error_code": "beast_near", "local": True,
                        "error": "not run: a big beast is near the stair site"}
        why = self.room_reserved(tool, args)
        if why:

            self.tries[key] = self.tries.get(key, 0) + 1
            self.last[key] = self.now
            if self.may("room_reserved_log_" + key, 7, 10 ** 6):
                self.last["room_reserved_log_" + key] = self.now
                log("room_reserved", day=self.day, key=key, tool=tool, args=args, why=why)
            return {"ok": False, "error_code": "room_reserved", "local": True, "error": "not run: " + why}
        self.tries[key] = self.tries.get(key, 0) + 1
        self.last[key] = self.now
        r = self.game.act(tool, args)
        if tool == "place_furniture" and not r.get("ok") and args.get("site") is not None\
                and "no free floor tile" in str(r.get("error") or ""):
            self.nofloor[self.nofloor_key(args["site"], args.get("w"), args.get("h"))] =\
                (self.obs_day(), self.site_sig(args["site"]))
        self.count += 1
        log("act", key=key, tool=tool, args=args, ok=r.get("ok"), code=r.get("error_code"),
            err=str(r.get("error") or "")[:160])
        if not r.get("ok") and tool in ("make_zone", "place_furniture") and args.get("site") is not None:


            m = re.search(r"\[1, ?(\d+)\]", str(r.get("error") or ""))
            if m:
                banned = self.zone_banned if tool == "make_zone" else self.place_banned
                if args["site"] not in banned:
                    banned.add(args["site"])
                    log("wide_site", day=self.day, tool=tool, site=args["site"], cap=int(m.group(1)))
        if not r.get("ok") and r.get("error_code") == "site_used" and args.get("site") is not None\
                and re.search(r"already used \(farm plot", str(r.get("error") or "")):




            sid = args["site"]
            self.plot_rooms.add(sid)
            if self.roles.get(sid) not in (None, "farm"):
                log("room_lost_to_plot", day=self.day, site=sid, role=self.roles.get(sid), tool=tool)
                self.roles.pop(sid, None)
        if r.get("ok"):
            self.tries[key] = max(0, self.tries[key] - 1)
            if tool == "create_burrow":
                self.shelter_made = True
            if tool == "make_zone" and str(args.get("site") or "").startswith("R"):



                label = {"dormitory": "Dormitory", "dining_hall": "DiningHall", "office": "Office",
                         "meeting_area": "MeetingHall", "bedroom": "Bedroom"}.get(args.get("kind"), "zone")
                for s_ in self.sites:
                    if s_.get("id") == args["site"]:
                        s_["free"] = False
                        s_["used_by"] = sorted(set(lst(s_.get("used_by"))) | {label + " (this pass)"})
            if tool == "make_zone":


                at = d(r.get("result")).get("at")
                if isinstance(at, list) and len(at) >= 5 and all(isinstance(v, int) for v in at[:5]):
                    label = {"dormitory": "Dormitory", "dining_hall": "DiningHall", "office": "Office",
                             "meeting_area": "MeetingHall", "bedroom": "Bedroom"}.get(args.get("kind"), "zone")
                    self.zones.append({"id": d(r.get("result")).get("zone_id"), "type": label, "x": at[0],
                                       "y": at[1], "z": at[2], "w": at[3], "h": at[4], "this_pass": True})
            if tool == "assign_zone" and args.get("zone_id") is not None:



                for z_ in self.zones:
                    if isinstance(z_, dict) and z_.get("id") == args["zone_id"]:
                        z_["owner"] = args.get("dwarf_id")
            zb = args.get("z_bottom")
            if tool == "dig_stairs" and args.get("site") is not None and isinstance(zb, int)\
                    and not isinstance(zb, bool):

                self.shafts[args["site"]] = min(zb, self.shafts.get(args["site"], zb))
            if tool == "civilian_alert" and isinstance(self.o.get("burrows"), dict):




                self.o["burrows"]["civilian_alert"] = bool(args.get("on"))
            if tool == "squad_order":
                if key != "squad_reassert":
                    self.squad_post = None if args.get("order") == "stand_down" else (key, dict(args))

                sq = next(iter(lst(d(self.o.get("military")).get("squads"))), None)
                if isinstance(sq, dict):
                    if args.get("order") == "stand_down":
                        sq["orders"] = []
                    elif args.get("order") == "station":
                        sq["orders"] = [{"order": "station", "x": args.get("x"), "y": args.get("y"),
                                         "z": args.get("z")}]
                    elif args.get("order") == "attack":
                        sq["orders"] = [{"order": "attack"}]
            if tool == "add_order" and args.get("recipe") == "brew_drink" and args.get("repeat") == "daily":
                order_id = d(r.get("result")).get("order_id")
                if type(order_id) is int:
                    self.brew_orders.add(order_id)
            if tool == "add_order" and args.get("recipe") == "brew_drink" and not args.get("repeat")\
                    and key in BREW_SHOT_KEYS:
                order_id = (r.get("result") if isinstance(r.get("result"), dict) else r).get("order_id")
                if type(order_id) is int:
                    self.brew_shots[order_id] = key
        if r.get("ok") and tool in ("add_order", "add_manager_order"):
            res = r.get("result") if isinstance(r.get("result"), dict) else r
            if res.get("order_id") is not None:
                self.owned.add(res.get("order_id"))
                self.key_order[key] = res.get("order_id")
                if isinstance(getattr(self, "order_src", None), dict):
                    self.order_src[res.get("order_id")] = (key, tool, dict(args))
            if args.get("repeat") and key.startswith("o_") and key.endswith(("_end", "_win", "_prog")):
                self.done.add(key)
        if r.get("ok") and tool in ("dig_room", "dig_stairs") and isinstance(getattr(self, "dig_batches", None), list):
            self.note_dig_batch(key, tool, args)
        self.report = (self.report + [{"day": self.day, "tool": tool, "args": args, "ok": bool(r.get("ok")),
                                       **({"error_code": r.get("error_code"), "error": str(r.get("error") or "")[:100]}
                                          if not r.get("ok") else {})}])[-REPORT_KEEP:]
        return r


    def load(self, resp):
        self.loads += 1
        self.o = d(resp.get("observation"))
        self.st, self.map = d(self.o.get("stocks")), d(self.o.get("map"))
        self.adm = d(self.o.get("administrators"))
        self.hands_off = resp.get("hands_off_in_days")
        self.surge = self.surge_wish and self.hands_off is not None
        self.days_left = resp.get("days_left") if isinstance(resp.get("days_left"), int) else None
        self.day = resp.get("day")
        if isinstance(self.day, (int, float)) and not isinstance(self.day, bool)\
                and (not self.pass_days or self.day > self.pass_days[-1]):
            self.pass_days = (self.pass_days + [self.day])[-4:]
        self.now = d(self.o.get("date")).get("abs_tick") or resp.get("tick") or 0
        self.people = [x for x in lst(self.o.get("dwarves")) if isinstance(x, dict)]
        seen_cat = getattr(self, "stress_seen", None)
        for x in self.people if isinstance(seen_cat, dict) else ():

            c = x.get("stress")
            if x.get("id") is not None and isinstance(c, int) and not isinstance(c, bool):
                seen_cat[x["id"]] = max(seen_cat.get(x["id"], c), c)
        self.cit = self.adm.get("citizens") or len(self.people)
        self.sites = [s for s in lst(self.map.get("sites")) if isinstance(s, dict)]
        self.note_w_sites()
        self.orders = [x for x in lst(self.o.get("orders")) if isinstance(x, dict)]
        if isinstance(self.o.get("orders"), list):
            self.brew_orders.intersection_update(x.get("id") for x in self.orders)
            self.owned.intersection_update(x.get("id") for x in self.orders)
            on_book = {x.get("id") for x in self.orders}
            self.brew_shots = {k: v for k, v in self.brew_shots.items() if k in on_book}
        self.zones = [z for z in lst(self.o.get("zones")) if isinstance(z, dict)]
        self.free = d(self.st.get("furniture_free"))
        self.placed = {}
        for f in lst(self.o.get("furniture")):
            if isinstance(f, dict):
                self.placed[f.get("kind")] = self.placed.get(f.get("kind"), 0) + 1
        self.surface = self.map.get("surface_z")




        self.record_caravan()

        if isinstance(self.day, (int, float)):
            rec = (self.day, self.st.get("food_edible") or 0, self.st.get("drink") or 0)
            if self.food_hist and self.food_hist[-1][0] == self.day:
                self.food_hist[-1] = rec
            else:
                self.food_hist.append(rec)
        if isinstance(self.day, (int, float)) and isinstance(self.st.get("drink"), (int, float)):
            rec = (self.day, self.st.get("drink") or 0, self.st.get("food_edible") or 0, self.cit or 0,
                   bool(self.caravan_settling()))
            if self.rate_hist and self.rate_hist[-1][0] == self.day:
                self.rate_hist[-1] = rec
            else:
                self.rate_hist.append(rec)
        self.f_record()
        if not self.caravan_settling() and isinstance(self.st.get("seeds_by_kind"), dict):
            self.own_seeds = {k: int(d(v).get("n") or 0) for k, v in self.live_seeds_by_kind().items()}
            self.own_food = self.st.get("food_edible")
            self.own_plants = {k: int(d(v).get("n") or 0) for k, v in d(self.st.get("plants_by_kind")).items()}
            self.merchant_plants = None
        elif self.caravan_active and self.merchant_plants is None and isinstance(self.own_plants, dict):


            self.merchant_plants = {k: max(0, int(d(v).get("n") or 0) - self.own_plants.get(k, 0))
                                    for k, v in d(self.st.get("plants_by_kind")).items()}
        if isinstance(self.day, int) and self.day != self.stock_day:
            self.stock_day = self.day
            self.stock_hist.append((self.day, self.st.get("drink") or 0, self.st.get("food_edible") or 0,
                                    self.st.get("prepared_meals") or 0))


        self.glut_jump = ((self.st.get("plants_brewable") or 0) - self.glut_prev) if self.glut_prev is not None else 0
        self.glut_prev = self.st.get("plants_brewable") or 0


        rot = self.st.get("plants_rotten")
        if not isinstance(rot, (int, float)) or isinstance(rot, bool):
            rot = None



        base = self.rot_prev
        if isinstance(self.day, (int, float)) and rot is not None:
            self.rot_hist = [h for h in self.rot_hist if self.day - h[0] <= ROT_ARM_DAYS and h[0] < self.day]
            if self.rot_hist:
                base = min(h[1] for h in self.rot_hist)
        if not self.rot_seen and rot is not None and base is not None\
                and rot - base >= ROT_ARM_RISE and self.alloc_on():
            self.rot_seen = True
            log("rot_seen", day=self.day, rotten=rot, prev=base, pb=self.st.get("plants_brewable"),
                seeds=self.st.get("seeds"), barrels=self.st.get("barrels_empty"))
        if rot is not None:
            self.rot_prev = rot
            if isinstance(self.day, (int, float)):
                self.rot_hist = [h for h in self.rot_hist if h[0] != self.day] + [(self.day, rot)]
        if d(self.o.get("burrows")).get("civilian_alert") and isinstance(self.day, (int, float)):
            self.alert_seen_day = self.day

        if isinstance(self.cit, int) and not isinstance(self.cit, bool) and self.cit > 0:
            if self.mig_start is None:
                self.mig_start = self.cit
            if self.mig_prev is not None and self.cit - self.mig_prev >= 2:
                self.mig_waves += 1
                log("pop_wave", day=self.day, arrived=self.cit - self.mig_prev, citizens=self.cit,
                    waves=self.mig_waves, forecast=self.pop_forecast())
            self.mig_prev = self.cit


        for name, v in d(self.st.get("seeds_by_kind")).items():
            if isinstance(d(v).get("seasons"), list):
                self.kind_seasons[name] = list(d(v)["seasons"])


        for name, v in d(self.st.get("plants_by_kind")).items():
            if isinstance(d(v).get("brewable"), bool):
                self.kind_brew[str(name)] = d(v)["brewable"]
        if isinstance(self.day, (int, float)) and self.day != self.age_day:
            self.age_day = self.day
            self.age_plants()
            if isinstance(self.st.get("logs_usable"), (int, float)):
                fell = any(p.get("job") == "FellTree" for p in self.people)
                self.wood_hist = (self.wood_hist + [(self.day, self.st.get("logs_usable"), fell)])[-60:]
        if isinstance(self.day, (int, float)) and isinstance(self.o.get("dwarves"), list):
            idle = sum(1 for p in self.people if p.get("job") == "idle")
            if self.idle_days and self.idle_days[-1][0] == self.day:
                self.idle_days[-1] = (self.day, idle)
            else:
                self.idle_days = (self.idle_days + [(self.day, idle)])[-2:]




        for w in lst(self.o.get("workshops")):
            if not isinstance(w, dict) or w.get("id") is None:
                continue
            stuck_now = (not w.get("built")) and any(
                isinstance(j, dict) and j.get("job") == "ConstructBuilding" and j.get("suspended")
                for j in lst(w.get("job_details")))
            if stuck_now:
                if self.shop_stuck.get(w["id"]) is None:
                    self.shop_stuck[w["id"]] = self.obs_day()
            else:
                self.shop_stuck.pop(w["id"], None)
        self.note_butcher_frames()
        self.record_water()
        self.record_caravan()
        self.record_wildlife(self.wild_stamp())
        self.note_wild_evidence(self.o)
        self.learn_marks(self.o)
        self.note_access(self.o, self.now)




    def safe_due(self):
        """The hands-off window starts before the next pass may come: hands_off_in_days within the longest of the
        last three day gaps between passes (at least 1)."""
        ho = self.hands_off
        if not isinstance(ho, (int, float)) or isinstance(ho, bool):
            return False
        gaps = [b - a for a, b in zip(self.pass_days, self.pass_days[1:])][-3:]
        return ho <= max([1] + gaps)

    def alert_barred(self):
        """No new civilian alert: the safe state holds (the last pass before a hands-off window)."""
        return self.safe_held

    def safe_state(self, why=None):
        """Lift the civilian alert and unlock every hatch/door this layer locked (never the flood's), and hold off
        new alerts and locks for this pass: on the last pass before a hands-off window, or when called with a reason
        (the standalone run's exit path)."""
        if why is None:
            self.safe_held = self.safe_due()
            if not self.safe_held:
                return
            why = "hands_off"
        else:
            self.safe_held = True
        lifted, opened = False, []
        if d(self.o.get("burrows")).get("civilian_alert"):
            r = self.act("safe_alert_off", "civilian_alert", {"on": False}, retry=0.25, limit=10 ** 6)
            if r and r.get("ok"):
                lifted = True
                if self.wild_alert_since is not None:
                    self.wild_alert_closed()
                self.alert_since = None
                self.wild_alert_since = None
        by_id = {d(x).get("id"): d(x) for x in lst(d(self.o.get("doors")).get("list"))}
        flood = self.hatch_id if self.breach else None
        for hid in sorted(self.alert_locked, key=str):
            x = by_id.get(hid)
            if hid == flood or (x is not None and not x.get("locked")):
                self.alert_locked.discard(hid)
                continue
            r = self.act("safe_unlock_" + str(hid), "lock_door", {"locked": False, "door_id": hid},
                         retry=0.25, limit=10 ** 6)
            if r and r.get("ok"):
                self.alert_locked.discard(hid)
                opened.append(hid)
        if lifted or opened or self.safe_log_day != self.day:
            self.safe_log_day = self.day
            log("safe_state", day=self.day, why=why, hands_off=self.hands_off, lifted=lifted, unlocked=opened)


    def access_free(self, obs):
        """No confinement on the switches: the civilian alert off and none of this layer's alert hatches locked."""
        obs = d(obs)
        if d(obs.get("burrows")).get("civilian_alert"):
            return False
        return not any(d(x).get("locked") and d(x).get("id") in self.alert_locked
                       for x in lst(d(obs.get("doors")).get("list")))

    def access_evidence(self, obs, drink=None):
        """Evidence on one look that the citizens get at the stores: one on the surface ("surface"), fewer inside the
        Shelter than there are citizens ("outside"), or the drink stock below the last look's ("drank"). None when
        the look shows none (all in the Shelter, the stock unmoved or rising — the MY1-1 days 127-147)."""
        obs = d(obs)
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        surface = d(obs.get("map")).get("surface_z", getattr(self, "surface", None))
        if num(surface) and any(c["z"] >= surface for c in self.citizen_spots(obs)):
            return "surface"
        bur = d(obs.get("burrows"))
        shelter = next((d(b) for b in lst(bur.get("list")) if d(b).get("civ_alert_burrow")), None)
        inside = (shelter or {}).get("citizens_inside")
        cit = d(obs.get("administrators")).get("citizens") or len(self.citizen_spots(obs))
        if num(inside) and num(cit) and inside < cit:
            return "outside"
        if num(drink) and num(self.access_drink) and drink < self.access_drink:
            return "drank"
        return None

    def note_access(self, obs, tick):
        """Advance the access clock on one look (load() and the chunked advance's danger look): a free look with
        evidence opens the access window, and a later free look with evidence ACCESS_WINDOW_DAYS on completes it;
        a confined look, or a free one without evidence, closes it. The first look of the run starts the clock."""
        if not isinstance(tick, (int, float)) or isinstance(tick, bool):
            return
        if self.access_tick is None:
            self.access_tick = tick
        if tick == self.access_look:
            return
        self.access_look = tick
        drink = d(d(obs).get("stocks")).get("drink")
        if self.access_free(obs):
            ev = self.access_evidence(obs, drink)
            if not ev:
                self.access_from = None
            elif self.access_from is None:
                self.access_from = tick
            if ev and self.access_from is not None and tick - self.access_from >= ACCESS_WINDOW_DAYS * DAY\
                    and tick > self.access_tick:
                if self.thirst_due(tick):
                    log("access_window", day=self.day, since_day=round(self.access_tick / DAY, 1),
                        from_day=round(self.access_from / DAY, 1), evidence=ev)
                self.access_tick = tick
        else:
            self.access_from = None
        if isinstance(drink, (int, float)) and not isinstance(drink, bool):
            self.access_drink = drink

    def thirst_due(self, now=None):
        """More than ACCESS_CAP_DAYS have passed since the last confirmed access window completed."""
        now = self.now if now is None else now
        return self.access_tick is not None and isinstance(now, (int, float))\
            and now - self.access_tick > ACCESS_CAP_DAYS * DAY

    def thirst_signs(self, obs=None):
        """Citizens shown wanting a drink or a meal they cannot reach: a DrinkItem job, or a Drink/Eat cancel for a
        path, a forbidden area or an inaccessible item (MY1-1: "cancels Drink: Could not find path." on days 26/38/
        161, "Drink: Forbidden area." on 29/162, DrinkItem jobs on 13 of 15 citizens on days 39-45 behind the locked
        hatches, the leader's DrinkItem on days 155 and 162 below hatch 64)."""
        obs = d(self.o if obs is None else obs)
        n = sum(1 for p in lst(obs.get("dwarves")) if isinstance(p, dict) and p.get("job") == "DrinkItem")
        n += sum(1 for t in lst(obs.get("recent_cancellations"))
                 if re.search(r"cancels (Drink|Eat)\b.*(find path|Forbidden area|inaccessible)", str(t)))
        return n

    def wild_stamp(self):
        """The stamp the wildlife streaks are kept on: the game day (the tick's day when the day field is missing),
        else the observation count — no day and no tick still shows persistence across consecutive loads."""
        s = self.obs_day()
        return self.loads if s is None else s

    def obs_day(self):
        """This observation's game day: the loop's day field when present, else the tick (one day = DAY ticks).
        None when neither is numeric — the stuck and rebuild marks then stay fail-open (never stale)."""
        if isinstance(self.day, (int, float)) and not isinstance(self.day, bool):
            return self.day
        if isinstance(self.now, (int, float)) and not isinstance(self.now, bool):
            return int(self.now) // DAY
        return None

    def shop_stale(self, w):
        """True while this workshop's construction has been observed unbuilt with the ConstructBuilding job
        suspended on two different observation days (ROOT_CAUSES §E: the wildlife-interrupted frame nobody
        resumes — dev OP1-4 kept four shops built:false, suspended:true from d5 to d336)."""
        first = self.shop_stuck.get(w.get("id"))
        cur = self.obs_day()
        return first is not None and cur is not None and cur > first

    def note_butcher_frames(self):
        """cx butcher frame (BUTCHER_FRAME_IDLE_DAYS above): per unbuilt Butchers frame, the observed days its
        ConstructBuilding had no worker while no civilian alert stood and building material was on hand; a frame
        seen unbuilt that is gone from the list unbuilt, or idle past the bound, leaves its place in dead_w_sites.
        Only a list that was observed counts (a look without a workshops list changes nothing)."""
        shops = self.o.get("workshops") if isinstance(self.o, dict) else None
        if not isinstance(shops, list):
            return
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        day = self.obs_day()
        alert = bool(d(self.o.get("burrows")).get("civilian_alert"))
        now = set()
        for w in shops:
            if not isinstance(w, dict) or w.get("id") is None or w.get("type") != "Butchers":
                continue
            if w.get("built") is not False:
                self.frame_idle.pop(w["id"], None)
                self.frame_seen.pop(w["id"], None)
                continue
            now.add(w["id"])
            if all(num(w.get(k)) for k in ("x", "y", "z")):
                self.frame_seen[w["id"]] = (w["x"], w["y"], w["z"])
            jobs = [j for j in lst(w.get("job_details")) if isinstance(j, dict) and j.get("job") == "ConstructBuilding"]
            worked = any(j.get("worker_id") not in (None, -1) for j in jobs)
            if worked:
                self.frame_idle.pop(w["id"], None)
            elif day is not None and not alert and self.material() >= 1:
                self.frame_idle.setdefault(w["id"], set()).add(day)
            if len(self.frame_idle.get(w["id"], ())) >= BUTCHER_FRAME_IDLE_DAYS and w["id"] in self.frame_seen:
                self.dead_w_sites.add(self.frame_seen[w["id"]])
        for fid in [k for k in self.frame_seen if k not in now]:
            self.dead_w_sites.add(self.frame_seen.pop(fid))
            self.frame_idle.pop(fid, None)

    def butcher_frame_dead(self, w):
        """cx butcher frame: an unbuilt Butchers frame idle on BUTCHER_FRAME_IDLE_DAYS observed days."""
        return w.get("type") == "Butchers" and w.get("built") is False\
            and len(self.frame_idle.get(w.get("id"), ())) >= BUTCHER_FRAME_IDLE_DAYS

    def butcher_key(self):
        """cx butcher frame: the build key — ws_Butchers until a frame died, then one fresh key per dead place, so a
        rebuild is not refused as done (act's key memory) and is tried once per new site."""
        n = len(getattr(self, "dead_w_sites", ()))
        return "ws_Butchers" if not n else "ws_Butchers_%d" % (n + 1)

    def butchers_ready(self):
        """cx butcher frame: a Butchers stands that can take a slaughter — built, or a frame that is neither idle past
        BUTCHER_FRAME_IDLE_DAYS nor suspended across two observed days (shop_stale)."""
        return any(isinstance(w, dict) and w.get("type") == "Butchers"
                   and not (w.get("built") is False and (self.butcher_frame_dead(w) or self.shop_stale(w)))
                   for w in lst(self.o.get("workshops")))

    def dead_site(self, site):
        """cx butcher frame: a Butchers frame idled or vanished unbuilt inside this W site's box."""
        x, y, z = site.get("x"), site.get("y"), site.get("z")
        for (wx, wy, wz) in getattr(self, "dead_w_sites", ()):
            if wz == z and isinstance(x, (int, float)) and isinstance(y, (int, float))\
                    and x <= wx < x + (site.get("w") or 1) and y <= wy < y + (site.get("h") or 1):
                return True
        return False

    def kind(self, k):
        return [s for s in self.sites if s.get("kind") == k]

    def pending(self, recipe):
        return any(x.get("recipe") == recipe and (x.get("left") or 0) > 0 for x in self.orders)

    def standing(self, recipe):
        return any(x.get("recipe") == recipe and x.get("repeat") for x in self.orders)

    def regular_cook_on_book(self):
        """A repeat cook order other than this layer's special ones (the plant-free emergency o_cook_food, the winter
        push, the endgame cook). Counting o_cook_food as "the" cook standing kept the regular o_cook — the one with
        the seeds and plant floors — from ever returning after a recut (cx hint MY1-3 2026-11-10: from day 22 only
        o_cook_food, when [FOOD<200], stayed on the book)."""
        skip = {self.key_order.get(k) for k in ("o_cook_food", "o_winter_cook", "o_cook_end")} - {None}
        mine = self.cook_standing(False)
        if mine is not None and mine.get("id") not in skip:
            return True




        cap = MEAL_CAP
        for x in self.orders:
            if x.get("recipe") != "cook_meal" or not x.get("repeat") or x.get("id") in skip:
                continue
            if self.seed_clause_dead(x):
                continue
            caps = [v for k, t, v in when_sig(x.get("when")) if k == ("FOOD", None) and t == "LessThan"
                    and isinstance(v, (int, float))]
            if caps and min(caps) < cap:
                continue
            return True
        return False

    def zone(self, word):
        return [z for z in self.zones if word in str(z.get("type")).lower()]

    def logs(self):
        return self.st.get("logs_usable", 0) or 0

    def material(self):
        return self.logs() + (self.st.get("boulders_usable", 0) or 0)

    def undug_rooms(self):
        return [r for r in self.kind("R") if not r.get("designated")]

    def dug_rooms(self, role=None):
        return [r for r in self.kind("R") if r.get("dug") and r.get("free", True)
                and (role is None or self.roles.get(r["id"]) == role)]







    def water_now(self):
        """Indoor water is standing on the fortress levels right now (obs water_on_fort_levels)."""
        return (d(self.o.get("water_on_fort_levels")).get("tiles") or 0) > 0

    def water_texts(self):
        """(drowned death seen, wet dig cancel seen, any found-dead seen) in the observation's own text lists."""
        texts = [str(t).lower() for t in lst(self.o.get("recent_events")) + lst(self.o.get("recent_cancellations"))]
        drowned = any("found dead" in t and "drown" in t for t in texts)




        wet_cancel = any(re.search(r"(cancels|unable to) (dig|carve|detail|channel|mine)\b[^:]*:.*\b(damp|wet|water)",
                                   t) for t in texts)
        found_dead = any("found dead" in t for t in texts)
        return drowned, wet_cancel, found_dead

    def water_probe_ok(self):
        """Spend one of today's water probes (map queries and /events pages share the budget)."""
        if self.water_probe_day_no != self.day:
            self.water_probe_day_no, self.water_probes = self.day, 0
        if self.water_probes >= WATER_PROBES_PER_DAY:
            return False
        self.water_probes += 1
        return True

    def site_near(self, x, y, z, margin=WATER_SITE_MARGIN):
        """The id of the site whose box (grown by margin) holds x,y,z, nearest first; None when no site is near."""
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (x, y, z)):
            return None
        best, dist = None, 10 ** 9
        for s in self.sites:
            if s.get("z") != z:
                continue
            sx, sy = s.get("x"), s.get("y")
            w, h = s.get("w", 1) or 1, s.get("h", 1) or 1
            dx = max((sx - margin) - x, x - (sx + w + margin - 1), 0)
            dy = max((sy - margin) - y, y - (sy + h + margin - 1), 0)
            near = max(dx, dy)
            if near <= margin and near < dist:
                best, dist = s.get("id"), near
        return best

    def water_death_sites(self):
        """Site ids within margin of a recent found-dead report /events places (a drowned miner's site), budgeted
        to one /events page per day; reports without a position contribute nothing here."""
        if not self.water_probe_ok():
            return set()
        try:
            r = self.game.events(since_tick=max(0, self.water_event_tick or self.now - WATER_EVENT_LOOKBACK_DAYS * DAY))
        except Exception as e:
            log("water_events_error", error=repr(e)[:160])
            return set()
        self.water_event_tick = self.now
        hits = set()
        for ev in lst(d(r).get("events")):
            ev = d(ev)
            text = str(ev.get("text") or "").lower()
            if "found dead" not in text:
                continue
            if not (ev.get("type") == "CITIZEN_DEATH" or "drown" in text or self.water_now()):
                continue
            sid = self.site_near(ev.get("x"), ev.get("y"), ev.get("z"))
            if sid is not None:
                hits.add(sid)
        return hits

    def count_water(self, res, boxes=None, margin=0, zs=None):
        """Water tiles in a map-query result: liquid tiles that are not magma, plus river/brook/pool/frozen-liquid
        material letters in the revealed grids (row i is y = y1 + i, character j is x = x1 + j). cx: with boxes
        [(x, y, w, h, z)] only the tiles touching one of them (the box grown by margin, z equal, or any z in zs when
        zs is given) count — the natural water elsewhere in the query's square is not the site's (owner decision B)."""
        res = d(res)

        def hit(x, y, z):
            if boxes is None:
                return True
            if not all(isinstance(v, int) and not isinstance(v, bool) for v in (x, y, z)):
                return False
            return any((z in zs if zs is not None else z == bz)
                       and bx - margin <= x <= bx + bw - 1 + margin and by - margin <= y <= by + bh - 1 + margin
                       for bx, by, bw, bh, bz in boxes)

        n = 0
        for liq in lst(res.get("liquid")):
            liq = d(liq)
            if not liq.get("magma") and (liq.get("depth") or 0) > 0 and hit(liq.get("x"), liq.get("y"), liq.get("z")):
                n += 1
        x1, y1 = res.get("x1"), res.get("y1")
        for level in lst(res.get("levels")):
            z = d(level).get("z")
            for i, row in enumerate(lst(d(level).get("material"))):
                for j, ch in enumerate(str(row)):
                    if ch in WATER_MATERIAL_CHARS and (boxes is None or (isinstance(x1, int) and isinstance(y1, int)
                                                                         and hit(x1 + j, y1 + i, z))):
                        n += 1
        return n

    def dig_box(self, site):
        """(x, y, w, h, z) of the box a dig at this site opens: an R site at the largest room digging() designates
        there (DIG_BOX_R from the site's corner — dig_room keeps the site's corner, w and h given), others its own."""
        x, y, z = int(site.get("x") or 0), int(site.get("y") or 0), int(site.get("z") or 0)
        w, h = max(1, int(site.get("w") or 1)), max(1, int(site.get("h") or 1))
        if site.get("kind") == "R":
            w, h = max(w, DIG_BOX_R[0]), max(h, DIG_BOX_R[1])
        return x, y, w, h, z

    def water_wetness(self, site):
        """Cached near-site water count, or None when the site was never measured."""
        return self.water_cache.get(site.get("id"))

    def water_rank(self, site):
        """0 = measured dry, 1 = unmeasured, 2 = measured wet: the dig order dry -> unmeasured -> wet."""
        w = self.water_wetness(site)
        return 1 if w is None else (2 if w > 0 else 0)

    def water_measure(self, site, levels=1, force=False, rise=False):
        """Water touching the site's dig box (dig_box grown by WATER_DIG_MARGIN; RISE_MARGIN and one level above
        while a local rising watch stands), from the site's level down `levels`, from one map query; cached. None
        when unmeasured (budget spent, the query lost or refused — a refusal is never read as dry)."""
        sid = site.get("id")
        if not force and self.water_wetness(site) is not None:
            return self.water_cache.get(sid)
        bx, by, bw, bh, z = self.dig_box(site)
        margin = RISE_MARGIN if rise else WATER_DIG_MARGIN
        span = max(0, min(int(levels), WET_QUERY_SPAN))
        z_top = min(300, max(0, z + (1 if rise else 0)))
        if isinstance(self.surface, int) and not isinstance(self.surface, bool):
            z_top = max(z, min(z_top, self.surface))
        z2 = max(0, z - span - (1 if rise else 0))
        z2 = max(z2, z_top - WET_QUERY_SPAN)
        n = self.scan_count((bx, by, bw, bh, z), margin, z2, z_top)
        if n is None:
            if not self.water_probe_ok():


                return None if force else self.water_cache.get(sid)
            n = self.probe_count(sid, (bx, by, bw, bh, z), margin, z2, z_top)
            if n is None:
                return None
        if not rise:
            self.water_cache[sid], self.water_cache_day[sid] = n, self.day
        if n > 0:
            self.dig_at_water = (self.dig_at_water + [sid])[-REPORT_KEEP:]
        return n

    def probe_count(self, sid, box, margin, z2, z_top):
        """One map query around box (levels z_top..z2): the water touching it, None when lost or refused."""
        bx, by, bw, bh, z = box
        cx, cy = bx + (bw - 1) // 2, by + (bh - 1) // 2
        radius = min(20, max(WATER_QUERY_RADIUS, max(bw, bh) // 2 + margin + 2))
        try:
            r = self.game.query("map", x=min(400, max(0, cx)), y=min(400, max(0, cy)),
                                z=z_top, z2=z2, radius=radius)
        except Exception as e:
            log("water_probe_error", site=sid, error=repr(e)[:160])
            return None
        res = query_result(r)
        if res is None:
            log("water_probe_error", site=sid, day=self.day, z=z_top, z2=z2, error=query_error(r))
            return None
        return self.count_water(res, boxes=[box], margin=margin, zs=set(range(z2, z_top + 1)))

    def scan_count(self, box, margin, z_low, z_high):
        """cx: the water touching box (grown by margin) on levels z_low..z_high from today's fort_reading answers,
        or None when they do not cover that whole region (then the site is probed on its own)."""
        day, answers = self.scan
        if day != self.day or not answers:
            return None
        bx, by, bw, bh, _ = box
        need = set(range(z_low, z_high + 1))
        n, seen = 0, set()
        for res in answers:
            x1, x2, y1, y2 = (res.get(k) for k in ("x1", "x2", "y1", "y2"))
            if not all(isinstance(v, int) and not isinstance(v, bool) for v in (x1, x2, y1, y2)):
                continue
            if not (x1 <= bx - margin and bx + bw - 1 + margin <= x2 and y1 <= by - margin and by + bh - 1 + margin <= y2):
                continue
            zs = {d(lv).get("z") for lv in lst(res.get("levels"))} & need
            zs -= seen
            if not zs:
                continue
            seen |= zs
            n += self.count_water(res, boxes=[box], margin=margin, zs=zs)
        return n if seen == need else None

    def water_ok(self, site):
        """False while the site's dig is halted. A halted site is re-probed once per day and released when the map
        shows no water near it and the site's level is not standing in the wet-level record — but never while a
        breach is contained (the dfx read, runs/dfx-my15-v2/MY1-5: the d0 resume released S4/R2/R3 on a probe that
        happened to be locally dry while the z141 stratum held the water, and the d7-11 flood was the re-dig;
        resuming into an active containment replays it)."""
        sid = site.get("id")
        if sid not in self.water_halts:
            return True
        if self.breach:
            return False
        if self.water_probe_day.get(sid) == self.day:
            return False
        self.water_probe_day[sid] = self.day
        n = self.water_measure(site, levels=1 if site.get("kind") != "S" else 2, force=True,
                               rise=self.rise_watch is not None)
        if n == 0 and not (isinstance(site.get("z"), int) and site.get("z") in self.wet_z):
            del self.water_halts[sid]
            log("water_resume", site=sid, day=self.day)
            return True
        return False

    def water_generic_halt(self, cause):
        """Halt the dig fronts (undug rooms and unstaired S sites) with no site attribution, e.g. a water_rising
        advance stop or a flood seen indoors. Already-halted sites keep their first halt day."""
        newly = []
        for s in self.undug_rooms() + self.kind("S"):
            sid = s.get("id")
            if sid not in self.water_halts:
                self.water_halts[sid] = self.day
                newly.append(sid)
        if newly:
            log("water_halt", day=self.day, cause=cause, sites=sorted(newly))

    def record_water(self):
        """Turn the observation's water signals into halt-set entries. Runs in load(), guarded: a surprise here
        must never stop the plan (the same guarantee plan() itself has)."""
        try:
            drowned, wet_cancel, found_dead = self.water_texts()
            causes = []
            if drowned:
                causes.append("drowned_death_text")
            if wet_cancel:
                causes.append("wet_dig_cancel_text")
            if (d(self.o.get("water_on_fort_levels")).get("deep_tiles") or 0) > 0:
                causes.append("deep_indoor_water")
            if causes:
                self.water_generic_halt("+".join(causes))
            if found_dead and (drowned or self.water_now()):
                for sid in sorted(self.water_death_sites()):
                    if sid not in self.water_halts:
                        self.water_halts[sid] = self.day
                        log("water_halt", day=self.day, site=sid, cause="death_near_site")
            self.check_breach()
        except Exception as e:
            log("water_record_error", error=repr(e)[:200])

    def last_dig_tick(self):
        """The tick of this layer's most recent successful dig (the stairs key and the dig_<room> keys)."""
        digs = [t for k, t in self.last.items() if k == "stairs" or k.startswith("dig_")]
        return max(digs) if digs else None

    def check_breach(self, rising=False):
        """B-2: a water_rising stop within BREACH_DIG_WINDOW_DAYS of a dig, or deep indoor water up
        BREACH_DEEP_GAIN over this run's first reading, is a stair-shaft breach — the W4water halt alone let the
        same flood replay on every measured run (ROOT_CAUSES §B: the water_ok re-probe released the front in the
        same second, and nothing sealed or moved afterwards). The breach releases only when the deep water
        recedes to near the first reading (in the measured collapse it never does).
        cx (owner decision C): the rising stop is read against the fort's own boxes first (a fresh fort_reading):
        water inside a box (any depth, below the surface) is the full breach — with or without a recent dig — and so
        is a stop after a dig that no reading could check ("water_rising_unread", re-checked daily: BREACH_CLEAR_SCANS
        complete readings with no water inside hand it down to the local watch, water inside confirms it). A stop
        whose water stands outside every box opens the local watch instead (rise_watch): the fronts stay halted
        (water_rising_stop's generic halt) but each site is released by its own dig box being dry with RISE_MARGIN
        and a level above and below (water_ok), so digging away from the water goes on; the fort is re-read daily
        and water inside a box escalates to the full breach."""
        deep = d(self.o.get("water_on_fort_levels")).get("deep_tiles") or 0
        if self.water_base is None:
            self.water_base = deep
            if not rising:
                return
        if self.breach:
            if deep <= self.water_base + BREACH_RELEASE_GAIN and not self.water_now():
                log("flood_recede", day=self.day, deep=deep, base=self.water_base)
                self.breach, self.wet_z, self.rise_watch = None, set(), None
                return
            cause = self.breach.get("cause")
            if cause == "deep_water_gain" and not rising:
                inside = self.fort_water()
                if inside is None or self.fort_dry_day == self.day:
                    return
                self.fort_dry_day = self.day
                self.fort_dry_scans = self.fort_dry_scans + 1 if inside == 0 else 0
                if self.fort_dry_scans >= BREACH_CLEAR_SCANS:
                    log("flood_outside", day=self.day, deep=deep, base=self.water_base, scans=self.fort_dry_scans)
                    self.breach, self.wet_z, self.fort_dry_scans = None, set(), 0
            elif cause == "water_rising_unread" and not rising:
                inside = self.fort_water(shallow=True)
                if inside is None or self.fort_dry_day == self.day:
                    return
                self.fort_dry_day = self.day
                if inside > 0:
                    self.breach["cause"] = "water_rising_after_dig"
                    log("flood_confirmed", day=self.day, inside=inside)
                    return
                self.fort_dry_scans += 1
                if self.fort_dry_scans >= BREACH_CLEAR_SCANS:
                    log("flood_outside", day=self.day, deep=deep, base=self.water_base, scans=self.fort_dry_scans,
                        to="rise_watch")
                    self.breach, self.wet_z, self.fort_dry_scans = None, set(), 0
                    self.rise_watch = {"day": self.day, "inside": 0}
            return
        if self.rise_watch is not None and deep <= self.water_base + BREACH_RELEASE_GAIN and not self.water_now():
            log("rise_watch_end", day=self.day, deep=deep, base=self.water_base)
            self.rise_watch = None
        last = self.last_dig_tick()
        dug_recent = last is not None and (self.now - last) <= BREACH_DIG_WINDOW_DAYS * DAY
        cause = None
        if rising:
            rd = self.fort_reading(force=True)
            inside = None if rd is None or not rd["complete"] and not rd["any"] else rd["any"]
            if inside:
                cause = "water_rising_after_dig" if dug_recent else "water_rising_in_fort"
            elif inside is None:
                if dug_recent:
                    cause = "water_rising_unread"
            else:
                if self.rise_watch is None:
                    log("water_rising_local", day=self.day, dug_recent=dug_recent, deep=deep, base=self.water_base,
                        halted=sorted(str(k) for k in self.water_halts))
                self.rise_watch = {"day": self.day, "inside": 0}
                return
        elif self.rise_watch is not None:
            inside = self.fort_water(shallow=True)
            rd = self.fort_water_memo[1] if self.fort_water_memo[0] == self.day else None
            if not inside and rd is not None and rd.get("any"):
                inside = rd["any"]
            if inside:
                cause = "water_in_fort"
        if cause is None and deep - self.water_base >= BREACH_DEEP_GAIN:
            inside = self.fort_water()
            if inside is not None and inside < BREACH_FORT_MIN:
                if not self.gain_outside:
                    log("deep_water_outside", day=self.day, deep=deep, base=self.water_base, inside=inside)
                    self.gain_outside = True
                return
            cause = "deep_water_gain"
        if cause is None:
            return
        self.gain_outside, self.fort_dry_scans, self.rise_watch = False, 0, None
        zs = [s.get("z") for s in self.kind("S") if isinstance(s.get("z"), int)]
        self.breach = {"day": self.day, "z": min(zs) if zs else None, "cause": cause}
        log("flood_breach", day=self.day, cause=cause, z=self.breach["z"], deep=deep, base=self.water_base,
            digs_pending=self.o.get("dig_designations_pending"))

    def fort_boxes(self):
        """cx: the fort's own boxes for fort_water(): dug R rooms, the A levels below the surface, the S/E stairs."""
        out = []
        for s in self.sites:
            if not all(isinstance(s.get(k), int) and not isinstance(s.get(k), bool) for k in ("x", "y", "z")):
                continue
            k = s.get("kind")
            if (k == "R" and s.get("dug")) or k in ("S", "E")\
                    or (k == "A" and (not isinstance(self.surface, int) or s["z"] < self.surface)):
                out.append(s)
        return out

    def fort_water(self, shallow=False):
        """cx: deep liquid tiles (depth 4+, no magma) inside the fort's own boxes (fort_boxes, grown by WET_BOX_MARGIN)
        — or, shallow=True, any water tile (depth WET_DEPTH_MIN+) there, and only from a reading that covered every
        box level. At most one reading a day (fort_reading); None when nothing could be measured (no boxes, no query
        client, the probe budget spent, a refused or lost query)."""
        rd = self.fort_reading()
        if rd is None or (shallow and not rd["complete"]):
            return None
        return rd["any"] if shallow else rd["deep"]

    def fort_box_list(self):
        """(x, y, w, h, z) of every fort box: fort_boxes() plus the boxes this layer dug its rooms as (room_box —
        a dorm is dug 9x7 from a 3x3 R site's corner, so the site box alone misses most of the room)."""
        out = [(b["x"], b["y"], max(1, b.get("w") or 1), max(1, b.get("h") or 1), b["z"]) for b in self.fort_boxes()]


        bottom = self.stair_bottom() if isinstance(self.surface, int) and not isinstance(self.surface, bool) else None
        for st in self.sites:
            if not all(isinstance(st.get(k), int) and not isinstance(st.get(k), bool) for k in ("x", "y", "z")):
                continue
            zb = self.shafts.get(st.get("id")) if st.get("kind") == "S" else (bottom if st.get("kind") == "E" else None)
            if isinstance(zb, int):
                for zz in range(max(zb, st["z"] - WET_SCAN_LEVELS), st["z"]):
                    out.append((st["x"], st["y"], 1, 1, zz))
        dug = {s.get("id") for s in self.sites if s.get("dug")}
        for rid, box in sorted(self.room_box.items(), key=lambda kv: str(kv[0])):
            vals = tuple(box.get(k) for k in ("x", "y", "w", "h", "z"))
            if rid in dug and all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
                out.append(vals)
        return out

    def fort_reading(self, force=False):
        """cx: one map-query reading a day over the fort's boxes (fort_box_list), level bands of WET_QUERY_SPAN+1:
        {"deep": depth-4+ tiles inside a box grown by WET_BOX_MARGIN, "any": depth-1+ tiles there, "complete": every
        box level was read, "wet": {z: tiles} of the "any" count}; None when no band could be read. The /query
        answer is read by query_result (no top-level ok on a success). force (a water_rising stop) reads again
        even when today's reading exists and outside the daily probe budget — a stop is rare and its decision (full
        breach or local halt) must stand on the water as it is now. Water on the surface level is never counted in
        "any" / "wet" (the surface is the river's, as in the wet-level record). The answers are kept for today
        (self.scan) so water_measure can answer a site from them instead of spending a probe."""
        if self.fort_water_memo[0] == self.day and not force:
            return self.fort_water_memo[1]
        boxes = self.fort_box_list()
        query = getattr(self.game, "query", None)
        if not boxes or query is None:
            return None
        xs = [b[0] for b in boxes] + [b[0] + b[2] - 1 for b in boxes]
        ys = [b[1] for b in boxes] + [b[1] + b[3] - 1 for b in boxes]
        cx, cy = (min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2
        radius = max(WATER_QUERY_RADIUS, min(20, max(max(xs) - min(xs), max(ys) - min(ys)) // 2 + 2))
        z = max(b[4] for b in boxes)
        z_low = min(b[4] for b in boxes)
        deep, wet, bands, complete, bands_kept = 0, {}, 0, False, False
        while bands < 3:
            if z < z_low:
                complete = True
                break
            if not force and not self.water_probe_ok():
                break
            z2 = max(z_low, z - WET_QUERY_SPAN)
            try:
                r = query("map", x=min(400, max(0, cx)), y=min(400, max(0, cy)), z=min(300, max(0, z)),
                          z2=max(0, z2), radius=radius)
            except Exception as e:
                log("fort_water_error", day=self.day, error=repr(e)[:160])
                break
            res = query_result(r)
            if res is None:
                log("fort_water_error", day=self.day, z=z, z2=z2, error=query_error(r))
                break
            bands += 1
            if self.scan[0] != self.day or not bands_kept:
                self.scan = (self.day, [])
                bands_kept = True
            self.scan[1].append(res)
            for liq in lst(res.get("liquid")):
                liq = d(liq)
                tx, ty, tz = liq.get("x"), liq.get("y"), liq.get("z")
                depth = liq.get("depth") or 0
                if liq.get("magma") or depth < WET_DEPTH_MIN\
                        or not all(isinstance(v, int) and not isinstance(v, bool) for v in (tx, ty, tz)):
                    continue
                if any(bz == tz and bx - WET_BOX_MARGIN <= tx <= bx + bw - 1 + WET_BOX_MARGIN
                       and by - WET_BOX_MARGIN <= ty <= by + bh - 1 + WET_BOX_MARGIN for bx, by, bw, bh, bz in boxes):
                    if depth >= 4:
                        deep += 1
                    if not (isinstance(self.surface, int) and tz >= self.surface):
                        wet[tz] = wet.get(tz, 0) + 1
            z = z2 - 1
        if z < z_low:
            complete = bands > 0
        val = {"deep": deep, "any": sum(wet.values()), "complete": complete, "wet": wet} if bands else None
        self.fort_water_memo = (self.day, val)
        return val

    def water_rising_stop(self):
        """A water_rising advance stop (the plain loop's advance hook and the standalone run): halt the dig
        fronts and let the breach check read the stop (B-2). Safe on a stale observation: the stop itself is the
        water evidence, the next load's check_breach re-runs anyway."""
        self.water_rise_tick = self.now
        self.water_generic_halt("water_rising_stop")
        self.check_breach(rising=True)

    def flooded_pending(self):
        """True while dig_designations_pending sits over an active breach: the flooded designations never clear
        (measured: pending on 67/67 and 76/76 observed days, ROOT_CAUSES §L), so they must not pin the pace to
        one day a pass — a pinning quiet_days/pace is what amplified the deadline misses."""
        o = getattr(self, "o", {})
        return bool(self.breach) and bool(o) and (o.get("dig_designations_pending") or 0) > 0

    def dry(self, z):
        """B-2(c): False while the level stands in water (the wet-level scan's record). An unmeasured level is dry."""
        return z not in self.wet_z

    def record_wet_levels(self):
        """B-2(c): which underground levels stand in water — budgeted map queries a day over the sites' box,
        z from the surface down to WET_SCAN_LEVELS below it, walked in spans of WET_QUERY_SPAN+1 levels because
        the server refuses a wider single query ("at most 5 levels (|z2 - z| <= 4)", gameapi query.lua:237 — the
        dfx read lost every scan this way: 81 of 85 map queries d11-215 answered bad_arguments, the wet record
        stayed empty and every dry-floor exclusion ran on nothing). water_on_fort_levels cannot attribute water
        to levels, and the measured wet levels (z140-141 of a surface 142) are exactly where placements must not
        go. A band the server refuses or a probe budget exhausted keeps the earlier bands' record.
        cx: the answers are read by query_result — the old top-level ok test failed every real answer (every hint
        run logged water_probe_error "not ok" daily and the record never filled) — and, owner decision B, only water
        touching a fort box (fort_box_list grown by WET_BOX_MARGIN) marks its level: the natural pools 2-12 tiles off
        the rooms (hint std OP1-0 / OP1-3) leave the living level dry."""
        if self.wet_day == self.day or not isinstance(self.surface, int):
            return
        xs = [s["x"] for s in self.sites if isinstance(s.get("x"), int)]
        ys = [s["y"] for s in self.sites if isinstance(s.get("y"), int)]
        if not xs or not ys:
            return
        self.wet_day = self.day
        boxes = self.fort_box_list()
        cx, cy = (min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2
        radius = max(WATER_QUERY_RADIUS, min(20, max(max(xs) - min(xs), max(ys) - min(ys)) // 2 + 1))
        z_stop = max(0, self.surface - WET_SCAN_LEVELS)
        wet, bands = set(), 0
        z = min(300, max(0, self.surface))
        while z >= z_stop and bands < 3:
            if not self.water_probe_ok():
                break
            z2 = max(z_stop, z - WET_QUERY_SPAN)
            try:
                r = self.game.query("map", x=min(400, max(0, cx)), y=min(400, max(0, cy)),
                                    z=z, z2=z2, radius=radius)
            except Exception as e:
                log("water_probe_error", day=self.day, error=repr(e)[:160])
                break
            res = query_result(r)
            if res is None:
                log("water_probe_error", day=self.day, z=z, z2=z2, error=query_error(r))
                break
            bands += 1
            for liq in lst(res.get("liquid")):
                liq = d(liq)
                tx, ty, zz = liq.get("x"), liq.get("y"), liq.get("z")
                if (not liq.get("magma") and (liq.get("depth") or 0) >= WET_DEPTH_MIN
                        and all(isinstance(v, int) and not isinstance(v, bool) for v in (tx, ty, zz))
                        and zz < self.surface
                        and any(bz == zz and bx - WET_BOX_MARGIN <= tx <= bx + bw - 1 + WET_BOX_MARGIN
                                and by - WET_BOX_MARGIN <= ty <= by + bh - 1 + WET_BOX_MARGIN
                                for bx, by, bw, bh, bz in boxes)):
                    wet.add(zz)
            z = z2 - 1
        if bands:
            self.wet_z = wet
            if wet:
                log("wet_levels", day=self.day, levels=sorted(wet, reverse=True))

    def contain_flood(self):
        """B-2's containment, run from digging() while a breach is active: (a) no new digs at all (the caller
        returns) — the designation spam over a flooded shaft is the pace amplifier; (b) the surface stair sealed
        with a hatch (build_door kind=hatch on the E site, ordered when the item is missing) and locked
        (lock_door, that hatch's own id so the fort's other doors stay open), a build_wall on a D site as the
        fallback when no E site is listed; (c) the wet-level record for the placement exclusions."""
        self.record_wet_levels()
        doors = d(self.o.get("doors"))
        hatches = [d(x) for x in lst(doors.get("list")) if d(x).get("kind") == "hatch"]
        stair = next(iter(self.kind("E")), None)



        hatch = next((x for x in hatches if self.hatch_id is not None and x.get("id") == self.hatch_id), None)
        if hatch is None and stair is not None:
            hatch = next((x for x in hatches if x.get("x") == stair.get("x") and x.get("y") == stair.get("y")
                          and x.get("z") == stair.get("z")), None)
        if hatch is not None or stair is not None:
            if hatch is not None:
                self.hatch_id = hatch.get("id")
                if hatch.get("locked") and self.hatch_id not in self.alert_locked:
                    self.flood_locked.add(self.hatch_id)
                if not hatch.get("locked") and self.flood_lock_wanted(hatch):
                    r = self.act("flood_lock", "lock_door", {"locked": True, "door_id": self.hatch_id}, retry=1, limit=8)
                    if r and r.get("ok"):
                        self.flood_locked.add(self.hatch_id)
                        log("flood_lock", day=self.day, door=self.hatch_id)
            else:
                free = doors.get("hatch_cover_items_free") or 0
                if free <= 0:
                    if not self.pending("make_hatch_cover"):
                        self.act("flood_hatch_order", "add_order", {"recipe": "make_hatch_cover", "amount": 2},
                                 retry=1, limit=30)
                else:
                    r = self.act("flood_hatch", "build_door", {"kind": "hatch", "site": stair["id"]}, retry=2, limit=8)
                    hid = d(d(r).get("result")).get("id") if r else None
                    if hid is not None:
                        self.hatch_id = hid
        else:
            wall = next(iter(self.kind("D")), None)
            if wall is not None:
                self.act("flood_wall", "build_wall", {"site": wall["id"]}, retry=2, limit=8)



    def season(self):
        """0 spring, 1 summer, 2 autumn, 3 winter, from the in-game calendar (date.day_of_year; the run day only
        when the observation has no date). The run-day form put a MY1 run (day 0 = day_of_year 135, summer) a
        season and a half off, so the winter rules never met the real MY1 winter (cx 2026-11-10)."""
        return self.game_doy() // SEASON_DAYS

    def winter(self):
        return self.season() == 3







    def record_caravan(self):
        """One /events page per game day (read-only, its own cursor — the water rules' probe budget is untouched);
        a lost page leaves the state as it was, and a game object without an events client (the unit fakes) skips."""
        if not hasattr(self.game, "events") or not isinstance(self.day, (int, float)):
            return
        if self.caravan_probe_day == self.day:
            return
        self.caravan_probe_day = self.day
        since = self.caravan_cursor if self.caravan_cursor is not None else max(0, self.now - 8 * DAY)
        try:
            page = self.game.events(since_tick=int(since))
        except Exception as e:
            log("caravan_events_error", error=repr(e)[:160])
            return
        self.caravan_cursor = self.now
        last_arrive = last_leave = None
        for ev in lst(d(page).get("events")):
            ev = d(ev)
            t = str(ev.get("type") or "")
            ev_tick = ev.get("tick") or 0
            if ev_tick > self.now:
                continue





            ev_day = (self.day + (ev_tick - self.now) // DAY) if isinstance(self.now, (int, float))\
                else ev_tick // DAY
            if t in CARAVAN_ARRIVALS:
                if last_arrive is None or ev_day >= last_arrive:
                    last_arrive = ev_day
            elif t == CARAVAN_EMBARK:
                if last_leave is None or ev_day >= last_leave:
                    last_leave = ev_day
            if t == "CANCEL_JOB" and "Dig" in str(ev.get("text") or "") and "Dangerous terrain" in str(ev.get("text"))\
                    and all(isinstance(ev.get(k), int) for k in ("x", "y", "z")):
                self.dig_unsafe.add((ev["x"], ev["y"], ev["z"]))
            if t in LIAISON_EVENTS and not self.liaison_seen:
                self.liaison_seen = True
                log("liaison_seen", day=self.day, type=t)
        if last_arrive is not None:
            self.caravan_arrival_day = last_arrive
        if last_leave is not None:
            self.caravan_leave_day = last_leave
        if last_arrive is not None or last_leave is not None:
            self.caravan_last_day = max(self.caravan_last_day or 0, last_arrive or 0, last_leave or 0)
        active = False
        arr, lea = self.caravan_arrival_day, self.caravan_leave_day
        if arr is not None:
            if lea is None or lea < arr:
                active = (self.day - arr) <= CARAVAN_MAX_DAYS
            else:
                active = (self.day - lea) <= CARAVAN_GRACE_DAYS
        if active != self.caravan_active:
            log("caravan", on=active, day=self.day, arrival=self.caravan_arrival_day, leave=self.caravan_leave_day)
            self.caravan_active = active

    def caravan_settling(self):
        """True while the caravan's visit — or the inflated history it left in the slope records — can still tilt a
        stock rule: the stay itself plus CARAVAN_SETTLE_DAYS (the alarms fit SLOPE_WINDOW days of samples)."""
        if self.caravan_active:
            return True
        return self.caravan_last_day is not None and (self.day or 0) - self.caravan_last_day < CARAVAN_SETTLE_DAYS



    def leg_slopes(self):
        """(drink, food) per-day slopes over the closer's stock record, or the food-security record when shorter."""
        for hist, di, fo in ((self.stock_hist, 1, 2), (self.food_hist, 2, 1)):
            if len(hist) >= 3:
                return (ols_slope([(p[0], p[di]) for p in hist]), ols_slope([(p[0], p[fo]) for p in hist]))
        return None, None

    def drink_secure(self, drink_slope):
        """The drink leg holds the horizon: flat or rising, or its stock outlasts SLOPE_HORIZON at the drain (the
        score's own projection, as stock_sliding computes it)."""
        if drink_slope is None or drink_slope >= 0:
            return True
        return (self.st.get("drink") or 0) / -drink_slope >= SLOPE_HORIZON

    def food_min_leg(self):
        """Food is the score's min leg and falling while drink holds (ROOT_CAUSES §G): a discretionary brew then
        only spends the food stock — the glut bank and the closer's brew standing yield."""
        drink, food = self.leg_slopes()
        if food is None or food >= 0:
            return False
        return self.drink_secure(drink)

    def f_keeper_yield(self):
        """cx F keeper yield: from FYIELD_LEAD days before F to the end of an open-play run, a brew (one plant of
        food for five drinks) helps the score's min leg only while drink's projected T without it stays under both
        the cap (SLOPE_HORIZON) and food's own T. Drink's T: the stock alone, no brew to the end, at the drain the
        last f_len days of looks show (fyield_drain: the steeper of the net slope and the summed drops over the
        span; the year's measured use only when that stretch shows no drain). Food's T: its stock over the same
        stretch's OLS slope (rate_hist, the caravan's settling left out; the closer's record when it holds fewer
        than 3), infinite while not falling. Once it holds it latches for the rest of the run (food's mid-F rises —
        fish, a slaughter — turned the unlatched rule off on days 315-333 of the replay) and lets go only if drink's T
        falls under the cap and under food's T at the latch. While it holds the keeper brew standing (o_brew) is
        cancelled and not re-added; the lead lands the cancel before F, since an order's jobs already in progress
        still finish. Hint hard OP1-0 on c44c96b: the food-lean keeper (drink below 374) fired on days 315-316 and
        335 with drink 394-401 while food went 65 -> 64 over F (-0.37/day, T 174, supply 0.76); without those 4
        brews F's own record gives drink T 394 and food T 257 (supply 0.88).
        It latches only on a falling food record (food's T finite) and with drink's T FYIELD_MARGIN times over: with
        food flat or rising its leg already scores full, a brew costs the score nothing and the yield buys nothing — hint
        hard OP1-5 on ba93eee latched on day 307
        (drink 285, drain read 0.75/day, T 352 >= 336, food rising), the keeper stayed off to day 322, drink fell
        285 -> 255 over F at 1.1/day (T 219, supply 0.826) while food rose 204 -> 233 and 19 plump helmets stood."""
        if not self.alloc_on():
            return False
        left = self.days_to_end()
        if left is None or left > self.f_len() + FYIELD_LEAD:
            return False
        drink = self.st.get("drink") or 0
        cit = max(1, self.cit or 0)
        today = self.day if isinstance(self.day, (int, float)) else (self.days or 0) - left
        pts = [p for p in self.rate_hist if p[0] >= today - self.f_len() and not p[4]]
        use = self.fyield_drain(pts)
        if use is None:
            use = self.use_rate("drink", ALLOC_DRINK_PER_CIT_DAY) * cit
        if use <= 0 or drink <= 0:
            return False
        t_drink = (drink - use * left) / use
        if self.f_yield_food_t is not None:
            if t_drink < min(SLOPE_HORIZON, self.f_yield_food_t):
                log("f_keeper_yield_off", day=self.day, drink=drink, t_drink=round(t_drink),
                    t_food=round(self.f_yield_food_t))
                self.f_yield_food_t = None
                return False
            return True
        if len(pts) >= 3:
            food_sl = ols_slope([(p[0], p[2]) for p in pts])
        else:
            food_sl = self.leg_slopes()[1]
            if food_sl is None:
                return False
        food = self.st.get("food_edible") or 0
        t_food = food / -food_sl if food_sl < 0 else float("inf")
        if t_food != float("inf") and t_drink >= FYIELD_MARGIN * min(SLOPE_HORIZON, t_food):
            self.f_yield_food_t = min(SLOPE_HORIZON, t_food)
            log("f_keeper_yield_on", day=self.day, drink=drink, food=food, drain=round(use, 3),
                t_drink=round(t_drink), t_food=None if t_food == float("inf") else round(t_food))
            return True
        return False

    def f_lift_level(self):
        """cx F drink lift: the drink level the lift standings (f_drink_lift) keep through F, or None while they should
        not stand. From FYIELD_LEAD days before F to the end of an open-play run, drink is held at or above the level
        of its first look in the window (about the score's own stock_A), so the score's F record starts at its low
        and does not sink under it while plants and barrels last (the mid-F step of f_drink_lift tilts it upward). It
        arms while drink's projected T without the lift (fyield_drain, the stock left at the end over it) stays
        under FYIELD_MARGIN times the cap — past that a brew buys the score nothing (replayed hint hard OP1-0 on
        c44c96b: drink 403 for 16 citizens, T 535, food 65 rising before F and falling in it; an armed lift took 4 of
        the min leg's plants) — and food can pay for it in the score's own terms: with the plants that would hold drink flat (its drain over BREW_DRINKS a day) taken
        from food, food's slope stays flat or rising, or drink's T sits under both the cap and food's T with the
        lift. Food's slope and drink's drain
        read F's own looks from the score's stock_A day once there are 3 spanning 3 days, the last f_len days of looks
        before that. A standing lift is cut only on F's own food record spanning FLIFT_CUT_SPAN days with food's T
        under the cap (the drink record it shapes no longer shows the drain), or on the F keeper yield's latch. The
        harvest-closed hold tends F itself (hold_supply) except under the food-lean keeper, which it leaves alone.
        Hint hard OP1-5 on ba93eee: food-lean armed on day 271 at drink 237 (gross leg days 230 vs 78, while food's net
        record was rising); a seed-recycle burst lifted drink to 306 by day 293, so the keeper (below 237) never fired
        in F, the allocation stayed cook-only, and drink fell 285 -> 255 (T 224, supply 0.826) beside 4-19 brewable
        plants and 14-18 empty barrels while food rose 204 -> 233. Its look-back read food at -0.47/day on day 310
        (a pre-F jump 176 -> 204 on day 281) while F's own record rose."""
        if not self.alloc_on():
            return None
        left = self.days_to_end()
        if left is None or left < 1 or left > self.f_len() + FYIELD_LEAD:
            return None
        if self.hold_armed and not self.food_lean():
            return None
        if self.f_lift_base is None:
            self.f_lift_base = max(1, int(self.st.get("drink") or 0))
        if self.f_yield_food_t is not None:
            return None
        today = self.day if isinstance(self.day, (int, float)) else (self.days or 0) - left
        a = today - (self.f_len() - left) - 1
        pts = [p for p in self.rate_hist if p[0] >= a and not p[4]]
        level = self.f_lift_base
        food = self.st.get("food_edible") or 0
        if self.hold_on_book("o_brew_flift") or self.hold_on_book("o_brew_flift_mid"):
            if len(pts) < 3 or pts[-1][0] - pts[0][0] < FLIFT_CUT_SPAN:
                return level
            food_sl = ols_slope([(p[0], p[2]) for p in pts])
            return None if food_sl < 0 and food / -food_sl < SLOPE_HORIZON else level
        if len(pts) < 3 or pts[-1][0] - pts[0][0] < 3:
            pts = [p for p in self.rate_hist if p[0] >= today - self.f_len() and not p[4]]
        if len(pts) < 3 or pts[-1][0] - pts[0][0] < 3:
            return None
        food_sl = ols_slope([(p[0], p[2]) for p in pts])
        drain = self.fyield_drain(pts) or 0.0
        cost = drain / BREW_DRINKS
        drink = self.st.get("drink") or 0
        t_drink = max(0.0, drink - drain * left) / drain if drain > 0 else float("inf")
        if t_drink >= FYIELD_MARGIN * SLOPE_HORIZON:
            return None
        if food_sl - cost >= 0:
            return level
        food_end = food + (food_sl - cost) * left
        t_food = max(0.0, food_end) / (cost - food_sl)
        return level if t_drink < min(SLOPE_HORIZON, t_food) else None

    def f_drink_lift(self):
        """cx F drink lift (f_lift_level): repeat brew standings, LEAN_BREW_AMOUNT a firing — o_brew_flift under the
        lift level from the window's start, o_brew_flift_mid two firings higher from HOLD_MID_TOL days before mid-F (a
        step at mid-F weighs most in the score's least-squares slope, and it keeps the slope above zero when the
        first standing only holds the level) — added while the level stands, cancelled when it falls away (food
        turned the falling leg, the yield latched). The food-lean keeper's cancel (lean_supply) leaves them alone;
        their levels never move, so they are never recut."""
        left = self.days_to_end()
        if left is None or left < 1:
            return
        level = self.f_lift_level()
        f = self.f_len()
        want = {"o_brew_flift": level, "o_brew_flift_mid": None}
        if level is not None and f - left >= f / 2.0 - HOLD_MID_TOL:
            want["o_brew_flift_mid"] = level + 2 * LEAN_BREW_AMOUNT * BREW_DRINKS
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        for key, lvl in want.items():
            on_book = self.hold_on_book(key)
            if lvl is None:
                if on_book and level is None:
                    r = self.act(key + "_cut", "cancel_order", {"order_id": self.key_order.get(key)}, retry=2, limit=4)
                    if r is not None:
                        log("f_drink_lift", day=self.day, order=key, on=False, drink=self.st.get("drink"),
                            food=self.st.get("food_edible"), ok=r.get("ok"))
                continue
            if on_book or self.caravan_active or "Still" not in have:
                continue
            r = self.act(key, "add_order", {"recipe": "brew_drink", "amount": LEAN_BREW_AMOUNT, "repeat": "daily",
                                            "when": [{"stock": "drink", "below": int(lvl)},
                                                     {"stock": "plants_brewable", "at_least": 1},
                                                     {"stock": "barrels_empty", "at_least": 1}]},
                         retry=2, limit=6)
            if r is not None:
                log("f_drink_lift", day=self.day, order=key, on=True, below=int(lvl), drink=self.st.get("drink"),
                    food=self.st.get("food_edible"), pb=self.st.get("plants_brewable"), ok=r.get("ok"))

    @staticmethod
    def fyield_drain(pts):
        """Drink's per-day drain over the looks `pts` ((day, drink, food, cit, settling)): the larger of minus the
        OLS slope and the drops summed over the span per day; None with fewer than 3 looks, a span under 3 days or
        no drain at all."""
        if len(pts) < 3 or pts[-1][0] - pts[0][0] < 3:
            return None
        span = pts[-1][0] - pts[0][0]
        drops = sum(max(0, a[1] - b[1]) for a, b in zip(pts, pts[1:]))
        net = -ols_slope([(p[0], p[1]) for p in pts])
        drain = max(net, drops / span)
        return drain if drain > 0 else None




    def alloc_on(self):
        return (self.days or 0) >= 180 and self.hands_off is None

    def measured_rate(self, leg):
        """cx stage A: this fort's gross use of `leg` ("drink" or "food") per citizen-day, or None before enough
        falling looks: sum of drops / sum of citizen-days over the consecutive looks where the stock fell (a rise or
        a flat look means production inside the interval, which hides the use), the caravan's settling excluded.
        Replayed on the cx/full2 records: drink 0.05-0.13 and food 0.14-0.33 per citizen-day (vs the 0.33/0.16
        priors) on the 100-point MY1 and the top OP1 forts."""
        i = 1 if leg == "drink" else 2
        drop = cit_days = days = 0.0
        pairs = 0
        h = list(self.rate_hist)
        for a, b in zip(h, h[1:]):
            dt = b[0] - a[0]
            if dt <= 0 or a[4] or b[4] or b[i] >= a[i]:
                continue
            c = max(1, (a[3] + b[3]) / 2)
            drop += a[i] - b[i]
            cit_days += c * dt
            days += dt
            pairs += 1
        if pairs < RATE_MIN_PAIRS or days < RATE_MIN_DAYS or cit_days <= 0:
            return None
        lo, hi = RATE_CLAMP[leg]
        return min(hi, max(lo, drop / cit_days))

    def use_rate(self, leg, prior):
        """Per citizen-day use of `leg`: measured once it stands, else the caller's prior."""
        m = self.measured_rate(leg)
        return prior if m is None else m

    def legs_run_out(self):
        """cx stage A: (drink, food) — the leg's own net drain (OLS over the closer's record, SLOPE_MIN_PTS looks,
        not while the caravan settles) empties it before the run ends. Gross cover days compare the legs' use; a leg
        whose net slope reaches zero inside the run keeps its side whatever the comparison (the score's T is the
        stock over that net slope)."""
        if len(self.stock_hist) < SLOPE_MIN_PTS or self.caravan_settling():
            return False, False
        left = self.days_to_end()
        if left is None:
            return False, False
        out = []
        for i in (1, 2):
            sl = ols_slope([(p[0], p[i]) for p in self.stock_hist])
            out.append(sl < 0 and self.stock_hist[-1][i] / -sl < left)
        return tuple(out)

    def leg_days(self):
        """(drink, food) days of gross cover: the stock over this fort's measured use (use_rate), the
        ALLOC_*_PER_CIT_DAY priors until it stands."""
        cit = max(1, self.cit or 0)
        return ((self.st.get("drink") or 0) / (self.use_rate("drink", ALLOC_DRINK_PER_CIT_DAY) * cit),
                (self.st.get("food_edible") or 0) / (self.use_rate("food", ALLOC_FOOD_PER_CIT_DAY) * cit))

    def days_to_end(self):
        if self.days_left is not None:
            return self.days_left
        if not isinstance(self.day, (int, float)):
            return None
        return max(0, (self.days or 0) - self.day)

    def last_stretch(self):
        """The last LAST_STRETCH_DAYS of an open-play run: the reserve is converted, both sides run."""
        left = self.days_to_end()
        return self.alloc_on() and left is not None and left <= LAST_STRETCH_DAYS

    def reserve_build(self):
        """The RESERVE_BUILD_DAYS before the last stretch: every plant consumer holds the reserve."""
        left = self.days_to_end()
        return (self.alloc_on() and left is not None
                and LAST_STRETCH_DAYS < left <= LAST_STRETCH_DAYS + RESERVE_BUILD_DAYS)

    def plant_reserve(self):
        """The reserve carried into the last stretch: PLANT_RESERVE_PER_CIT (the 100-point forts' F entry) or, when
        larger, the plants F's drink needs at this fort's measured use (f_need, cx stage C)."""
        return max(COOK_PLANTS_RESERVE, PLANT_RESERVE_PER_CIT * (self.cit or 0), self.f_need())

    def f_need(self):
        """cx stage C: brewable plants that keep the drink leg's F slope at zero or above — F's drink at the
        measured use (use_rate; the documented DRINK_PER_CIT_DAY until it stands), HOLD_COVER times over, in 5-drink
        brews."""
        return math.ceil(HOLD_COVER * self.use_rate("drink", DRINK_PER_CIT_DAY) * max(1, self.cit or 0)
                         * self.f_len() / 5)







    def plant_plan(self):
        dd, fd = self.leg_days()
        sides = self.allocation()
        lean = self.food_lean()
        hold = self.hold_active()
        dout, fout = self.legs_run_out()
        left = self.days_to_end()
        plan = {
            "sides": sides, "lean": lean, "hold": hold, "last": self.last_stretch(), "build": self.reserve_build(),
            "floor": self.plant_floor(),
            "rot_keep": self.rot_keep() if self.rot_seen or self.loose_stuck() else ROT_KEEP,
            "f_need": self.f_need(), "reserve": self.plant_reserve(), "run_out": (dout, fout),

            "food_first": self.food_min_leg(),
            "in_f": left is not None and left <= self.f_len(),
            "brew_ok": ("brew" in sides) and not lean,
            "drink_days": round(dd), "food_days": round(fd),
        }
        key = tuple((k, str(v)) for k, v in plan.items() if k not in ("drink_days", "food_days"))
        if key != self.plan_key:
            self.plan_key = key
            log("plant_plan", day=self.day, **{k: (sorted(v) if isinstance(v, frozenset) else v)
                                               for k, v in plan.items()})
        return plan

    def plant_floor(self):
        """The plants_brewable floor of the running side's discretionary orders (glut bank, allocation one-shots):
        2 in the last stretch (the reserve is converted), the reserve in the build window, else the cook reserve;
        the harvest-closed hold's reserve over all of them until F."""
        if self.hold_active():
            return max(self.base_plant_floor(), self.hold_reserve())
        return self.base_plant_floor()

    def base_plant_floor(self):
        """plant_floor() without the harvest-closed hold."""
        if self.last_stretch():
            return 2
        if self.reserve_build():
            return self.plant_reserve()
        return COOK_PLANTS_RESERVE

    def hold_floor(self):
        """The floor of a yielding side's standing: it only takes plants well above the reserve."""
        return self.plant_reserve() + ALLOC_HOLD_MARGIN

    def allocation(self):
        """The sides allowed to take plants now, a frozenset of "brew"/"cook". Both outside open play and in the last
        stretch; otherwise a side yields only while its leg is comfortably ahead (ALLOC_AHEAD times the other's
        days) and not itself short (ALLOC_SHORT_DAYS). A flip waits ALLOC_DWELL_DAYS (each flip re-cuts the
        standings once) and the caravan's goods (§X) never flip it."""
        both = frozenset(("brew", "cook"))
        if not self.alloc_on():
            return both
        if self.food_lean():
            want = frozenset(("cook",))
            if self.alloc != want:
                dd, fd = self.leg_days()
                log("alloc", day=self.day, sides=sorted(want), drink_days=round(dd), food_days=round(fd), lean=True)
                self.alloc, self.alloc_day = want, self.day
            return self.alloc
        last = self.last_stretch()
        if last:
            want = both
        else:
            dd, fd = self.leg_days()
            dout, fout = self.legs_run_out()
            want = set()
            if dd < ALLOC_SHORT_DAYS or dd < ALLOC_AHEAD * fd or dout:
                want.add("brew")
            if fd < ALLOC_SHORT_DAYS or fd < ALLOC_AHEAD * dd or fout:
                want.add("cook")
            want = frozenset(want) or both
        if self.alloc is None:
            self.alloc, self.alloc_day = want, self.day
            log("alloc", day=self.day, sides=sorted(want))
        elif want != self.alloc and (last or not self.caravan_active):
            day = self.day if isinstance(self.day, (int, float)) else 0
            if last or self.alloc_day is None or day - self.alloc_day >= ALLOC_DWELL_DAYS:
                dd, fd = self.leg_days()
                log("alloc", day=self.day, sides=sorted(want), drink_days=round(dd), food_days=round(fd))
                self.alloc, self.alloc_day = want, day
        return self.alloc

    def food_lean(self):
        """cx: the food-lean endgame (LEAN_* above). Open play (OP1's 336 days and, since hint std MY1-4 on 68bd4c7,
        MY1's 216; the lab tasks keep their shapes), inside LEAN_DAYS of the end: armed once drink's leg days reach
        LEAN_AHEAD times food's (not while the caravan's goods tilt the stocks), the drink level at arming becomes the
        keeper's; it lets go when the ratio falls under LEAN_EXIT (a later arming takes the drink of that day).
        MY1 (hint std MY1-4, 68bd4c7, supply 0.734 on the food leg): drink 567 -> 711 in F while food fell 189 -> 168
        — the last stretch's allocation (both sides), the glut bank and o_brew_end (drink below 600) put the plants
        through the Still every week of F with drink already 3x food's leg days."""
        if not self.alloc_on():
            return False
        left = self.days_to_end()
        if left is None or left > LEAN_DAYS:
            return False
        dd, fd = self.leg_days()
        drink_out = self.legs_run_out()[0]
        if self.lean_drink is not None and drink_out:
            log("food_lean", day=self.day, on=False, drink=self.st.get("drink"), food=self.st.get("food_edible"),
                reason="drink_runs_out")
            self.lean_drink = None
            return False
        if self.lean_drink is None:
            if self.caravan_settling() or dd < LEAN_AHEAD * fd or drink_out:
                return False
            self.lean_drink = max(1, int(self.st.get("drink") or 0))
            log("food_lean", day=self.day, on=True, keep=self.lean_drink, drink_days=round(dd), food_days=round(fd),
                food=self.st.get("food_edible"), pb=self.st.get("plants_brewable"))
            return True
        if dd < LEAN_EXIT * fd:
            log("food_lean", day=self.day, on=False, drink=self.st.get("drink"), food=self.st.get("food_edible"))
            self.lean_drink = None
            return False
        return True

    def lean_supply(self):
        """cx: while food-lean holds, every brew order but the keeper (o_brew) yields: the closer's o_brew_end, the
        winter push, the allocation / rot / glut one-shots still open, and another hand's brew orders — except a repeat
        standing whose drink cap already sits at or under the keeper's level (a keeper of its own)."""
        if not self.food_lean():
            return
        keep, level = self.key_order.get("o_brew"), self.lean_drink
        end = self.key_order.get("o_brew_end")
        lift = (self.key_order.get("o_brew_flift"), self.key_order.get("o_brew_flift_mid"))
        for x in self.orders:
            oid = x.get("id")
            if x.get("recipe") != "brew_drink" or oid is None or oid in (keep, end) + lift\
                    or oid in self.recycle_brews or oid in self.stall_brews:
                continue

            if not x.get("repeat") and (x.get("left") or 0) <= 0:
                continue
            if x.get("repeat") and any(k[0] == "DRINK" and t == "LessThan" and isinstance(v, (int, float))
                                       and v <= level for k, t, v in when_sig(x.get("when"))):
                continue
            r = self.act("lean_cancel_%s" % oid, "cancel_order", {"order_id": oid}, retry=2, limit=3)
            if r is not None:
                log("lean_cancel", day=self.day, order=oid, repeat=bool(x.get("repeat")), when=x.get("when"))
                for k, v in list(self.key_order.items()):
                    if v == oid:
                        self.done.discard(k)




    def f_len(self):
        """The score's final stretch F on an open-play run: the last quarter, clipped to 7..28 days."""
        return min(28, max(7, int(self.days or 0) // 4))

    def game_doy(self):
        v = d(d(getattr(self, "o", None)).get("date")).get("day_of_year")
        if isinstance(v, int) and not isinstance(v, bool):
            return v % YEAR_DAYS
        return int(self.day or 0) % YEAR_DAYS

    def calendar_day(self, doy, fallback):
        """cx stage B: the run day on which the game calendar reaches day-of-year `doy` (the next time, counted from
        the run's own start), or `fallback` (the old run-day constant) when the observation has no day_of_year."""
        v = d(d(getattr(self, "o", None)).get("date")).get("day_of_year")
        if not isinstance(v, int) or isinstance(v, bool) or not isinstance(self.day, (int, float)):
            return fallback
        start = (v - int(self.day)) % YEAR_DAYS
        return (doy - start) % YEAR_DAYS

    def fallow_closed(self):
        """cx stage B: autofarm's own verdict (set_farms fallows every plot when no stocked crop is plantable this
        season — is_plantable steps the growth across the seasons): every plot reads crop_this_season "none" with
        seeds in stock, and the run ends before the next season turn (when autofarm decides again). Plots without
        the field never count."""
        plots = [d(p) for p in lst(self.o.get("farm_plots")) if isinstance(p, dict)]
        if not plots or any("crop_this_season" not in p for p in plots):
            return False
        if any(str(p.get("crop_this_season") or "none").lower() != "none" for p in plots):
            return False
        if (self.st.get("seeds") or 0) <= 0:
            return False
        left = self.days_to_end()
        to_turn = SEASON_DAYS - self.game_doy() % SEASON_DAYS
        return left is not None and left <= to_turn

    def harvest_closed(self):
        """No seed kind in stock can be planted from today on and ripen (HOLD_GROW_DAYS later, in season at both
        ends — autofarm's is_plantable) before the run ends. A kind without season data, or no seeds_by_kind at all,
        leaves it open (unknown is not closed)."""
        left = self.days_to_end()
        if left is None or not d(self.st.get("seeds_by_kind")):
            return False
        kinds = []
        for v in self.live_seeds_by_kind().values():
            v = d(v)
            if (v.get("n") or 0) <= 0:
                continue
            seasons = v.get("seasons")
            if not isinstance(seasons, list):
                return False
            kinds.append(set(seasons))
        doy = self.game_doy()
        name = lambda t: SEASON_NAMES[((doy + t) % YEAR_DAYS) // SEASON_DAYS]
        for t in range(0, max(0, left - HOLD_GROW_DAYS) + 1):
            a, b = name(t), name(t + HOLD_GROW_DAYS)
            if any(a in k and b in k for k in kinds):
                return self.fallow_closed()
        return True

    def hold_reserve(self):
        """The brewable plants carried into F: F's drink at DRINK_PER_CIT_DAY, HOLD_COVER times over, in 5-drink
        brews, above the 2 the regular standing keeps. cx MY1 supply plan: on MY1 the plan's own reserve
        (my1_hold_reserve)."""
        if self.my1_plan():
            return self.my1_hold_reserve()
        need = HOLD_COVER * self.use_rate("drink", DRINK_PER_CIT_DAY) * max(1, self.cit or 0) * self.f_len() / 5
        return max(HOLD_MIN, 2 + math.ceil(need))

    def hold_active(self):
        """Open play, harvest closed (confirmed once before F, then sticky: seeds a late brew returns cannot ripen in
        time either), and drink not running dry before F starts (half the consumption to F's start at
        DRINK_PER_CIT_DAY: under that, the plants are brewed now). cx: it now holds through F to the end — the held
        plants reach the Still only through hold_supply's one-a-day standings, so every other consumer keeps its
        reserve floor inside F too (the old cut-off 2 days into F dropped every floor to 2 and front-loaded them)."""
        left = self.days_to_end()
        if not self.alloc_on() or left is None or left < 1:
            return False
        if not self.hold_armed and left <= self.f_len():
            return False
        if not self.hold_armed:


            if not self.harvest_closed():
                self.hold_seen_day = None
                return False
            day = self.day if isinstance(self.day, (int, float)) else 0
            if self.hold_seen_day is None:
                self.hold_seen_day = day
            if day - self.hold_seen_day < HOLD_CONFIRM_DAYS:
                return False


        rate = self.f_drink_rate() if self.my1_plan() else\
            self.use_rate("drink", DRINK_PER_CIT_DAY) * max(1, self.cit or 0)
        need = rate * max(0, left - self.f_len())
        if (self.st.get("drink") or 0) < 0.5 * need:
            return False
        if not self.hold_armed:
            self.hold_armed = True
            log("harvest_hold", day=self.day, doy=self.game_doy(), reserve=self.hold_reserve(),
                pb=self.st.get("plants_brewable"), drink=self.st.get("drink"))
        return True

    def hold_cook(self):
        """The hold also binds the kitchen only while food is not the shorter leg (leg_days): plants are food too,
        and a fort short of food cooks them."""
        if not self.hold_active():
            return False
        dd, fd = self.leg_days()
        return fd >= dd

    def hold_drink_rate(self):
        """The fort's drink consumption per day: measured (use_rate), DRINK_PER_CIT_DAY until it stands."""
        return self.use_rate("drink", DRINK_PER_CIT_DAY) * max(1, self.cit or 0)

    def hold_on_book(self, key):
        """This layer's order under `key` is still on the book (a standing stays added once)."""
        oid = self.key_order.get(key)
        return oid is not None and any(x.get("id") == oid for x in self.orders)

    def hold_standing(self, key, below, floor=1):
        """A one-brew-a-day standing under the drink level `below` that may take the held plants (down to `floor`
        - 1; 0 by default). It acts between loads (the plain loop's model advances 7-14 days a call: hint hard MY1-3
        loaded at days 178, 192, 206, 215), and one brew a day spreads the release instead of front-loading it.
        cx m13many: a standing on the book under another plant floor is cut and re-added at this one."""
        floor = max(1, int(floor))
        if self.hold_on_book(key):
            oid = self.key_order.get(key)
            x = next((o for o in self.orders if o.get("id") == oid), {})
            have = [v for k, t, v in when_sig(x.get("when")) if k == ("PLANT", "DRINK_MAT") and t == "AtLeast"]
            if not (have and have[0] != floor and not (x.get("jobs_in_progress") or 0) and self.may(key + "_cut", 2)):
                return
            r = self.act(key + "_cut", "cancel_order", {"order_id": oid}, retry=2, limit=8)
            self.done.discard(key)
            if not (r and r.get("ok")):
                return



            self.last.pop(key, None)
        self.act(key, "add_order", {"recipe": "brew_drink", "amount": 1, "repeat": "daily", "when": [
            {"stock": "drink", "below": int(below)}, {"stock": "plants_brewable", "at_least": floor},
            {"stock": "barrels_empty", "at_least": 1}]}, retry=2, limit=6)

    def hold_supply(self):
        """cx: the hold's own drink standings (HOLD_DRY_DAYS / HOLD_PREP_DAYS above), replacing the old F release
        one-shot (o_brew_release, up to 8 brews on the first load 2 days into F: measured hint MY1-3 loads land 4-14 days
        apart, and a least-squares slope over F credits an early jump little — 4 brews 2 days in still leave the
        slope at -0.47/day against ~0.9/day drunk). Once armed:
        - o_brew_dry: drink below HOLD_DRY_DAYS of consumption brews one held plant a day (coverage, any time);
        - o_brew_pre: inside HOLD_PREP_DAYS of F, drink below the level projected for F's start (so the stock
          flattens there even when no load falls near F's first day);
        - o_brew_f: inside F, drink below a high cap — one held plant a day until the plants run out, so drink
          rises through F (the score's slope);
        - while the hold is on before F, another hand's brew orders (the model's: hint hard MY1-3 order 87,
          "drink below 60", no plant floor) that could take the reserve are cancelled."""
        if not self.hold_armed or not self.alloc_on():
            return
        left = self.days_to_end()
        if left is None or left < 1:
            return
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        if "Still" not in have:
            return
        f = self.f_len()
        rate = self.hold_drink_rate()
        drink = self.st.get("drink") or 0
        lean = self.food_lean()
        if self.my1_plan():



            self.my1_hold_supply(left, f, lean)
            self.hold_standing("o_brew_dry", max(5, math.ceil(HOLD_DRY_DAYS * rate)), self.f_dry_floor or 1)
            return
        self.hold_standing("o_brew_dry", max(5, math.ceil(HOLD_DRY_DAYS * rate)))
        mid = self.hold_mid_plan()
        if mid is not None and self.hold_on_book("o_brew_pre") and self.may("o_brew_pre_cut", 4):
            self.act("o_brew_pre_cut", "cancel_order", {"order_id": self.key_order.get("o_brew_pre")}, retry=2,
                     limit=4)
        if f < left <= f + HOLD_PREP_DAYS and not lean and mid is None and not self.hold_on_book("o_brew_pre"):
            want = drink - rate * (left - f)
            if want > HOLD_DRY_DAYS * rate:
                self.hold_standing("o_brew_pre", math.ceil(want))
        cookable = any(d(v).get("brewable") and d(v).get("cookable") for v in d(self.st.get("plants_by_kind")).values())
        food_stays = cookable and self.food_min_leg()
        if mid is not None and left <= f + HOLD_PREP_DAYS and not lean and not food_stays:
            self.hold_mid(mid, f, left, drink)
        elif left <= f and not lean and not food_stays:
            self.hold_standing("o_brew_f", max(600, 30 * (self.cit or 0)))
        if left > f and self.hold_active():
            reserve = self.hold_reserve()
            for x in self.orders:
                if x.get("recipe") != "brew_drink" or x.get("id") in self.owned or x.get("id") is None:
                    continue
                if any(k == ("PLANT", "DRINK_MAT") and t == "AtLeast" and isinstance(v, (int, float))
                       and v >= reserve for k, t, v in when_sig(x.get("when"))):
                    continue
                self.act("hold_cancel_%s" % x.get("id"), "cancel_order", {"order_id": x.get("id")}, retry=2, limit=3)
                log("hold_cancel", day=self.day, order=x.get("id"), when=x.get("when"))

    def my1_hold_supply(self, left, f, lean):
        """cx MY1 supply plan: hold_supply's MY1 path — the drink plan's brews from HOLD_PREP_DAYS before F (no
        o_brew_pre / o_brew_f), and before F another hand's brew order that could take the reserve is cancelled
        (an order leaving the reserve — a floor at reserve + its firing — stays)."""
        if self.hold_on_book("o_brew_pre") and self.may("o_brew_pre_cut", 4):
            self.act("o_brew_pre_cut", "cancel_order", {"order_id": self.key_order.get("o_brew_pre")}, retry=2,
                     limit=4)
        cookable = any(d(v).get("brewable") and d(v).get("cookable") for v in d(self.st.get("plants_by_kind")).values())
        food_stays = cookable and self.food_min_leg()


        if left <= f + HOLD_PREP_DAYS and not food_stays:
            self.f_plan_brew()
        else:
            self.f_dry_floor = None
        if self.hold_active():
            reserve = self.hold_reserve()
            plan_ids = {self.key_order.get(k) for k in F_PLAN_KEYS} | set(self.recycle_brews)
            for x in self.orders:
                if x.get("recipe") != "brew_drink" or x.get("id") is None or x.get("id") in plan_ids:
                    continue
                if x.get("id") in self.owned and (x.get("jobs_in_progress") or 0) and not x.get("repeat")\
                        and (x.get("left") or 0) <= 1:
                    continue
                if x.get("repeat") and self.leaves_reserve(x.get("total") or x.get("left"), x.get("when"), True,
                                                           reserve):
                    continue
                if not x.get("repeat") and (x.get("left") or 0) <= 0:
                    continue
                if not x.get("repeat") and self.pb_free() - self.plan_queued() >= reserve:
                    continue
                self.act("hold_cancel_%s" % x.get("id"), "cancel_order", {"order_id": x.get("id")}, retry=2, limit=3)
                log("hold_cancel", day=self.day, order=x.get("id"), when=x.get("when"))

    def leaves_reserve(self, amount, when, repeat, reserve):
        """cx MY1 supply plan: a brew order leaves the hold's reserve — a standing whose plants_brewable floor is at
        least the reserve plus its firing, a one-shot no larger than the free plants over the queued jobs and the
        reserve."""
        a = amount if isinstance(amount, int) and not isinstance(amount, bool) and amount >= 1 else 1
        if repeat:
            floors = [v for k, t, v in when_sig(when) if k == ("PLANT", "DRINK_MAT") and t == "AtLeast"
                      and isinstance(v, (int, float)) and not isinstance(v, bool)]
            return bool(floors) and max(floors) >= reserve + a
        return a <= self.pb_free() - self.plan_queued() - reserve

    def hold_proj_rate(self):
        """cx small hold: the drink decline per day the mid-F projection uses — the drink record's net decline (least
        squares) over the last HOLD_RATE_DAYS (the hold brews nothing there, so it is the fort's drinking: the score's
        own slope), or the hold's rate (hold_drink_rate) without such a record. Replayed on the four MY1-3 records the
        gross use_rate read 1.3-1.7/day on loads where drink fell 0.5-1.0/day net."""
        if isinstance(self.day, (int, float)):
            pts = [(p[0], p[1]) for p in self.stock_hist if self.day - p[0] <= HOLD_RATE_DAYS]
            if len(pts) >= 3 and pts[-1][0] - pts[0][0] >= 7:
                net = -ols_slope(pts)
                if net > 0:
                    return net
        return self.hold_drink_rate()

    def hold_mid_plan(self):
        """cx small hold (HOLD_F_LEAD above): the held plants (pb_free) when one held plant a day from HOLD_F_LEAD days
        into F (or from today, inside F) would lift the score's F slope by less than the projected drink decline, so
        they are brewed together at mid-F instead; None for a larger hold, an unarmed one, no plant or no F length."""
        if not self.hold_armed or not self.alloc_on():
            return None
        left, f = self.days_to_end(), self.f_len()
        n = self.pb_free()
        if left is None or f < 2 or left > f + HOLD_PREP_DAYS:
            return None
        if self.hold_mode != "mid" and n >= 1 and (self.hold_mode is None or left > f):


            p0 = max(HOLD_F_LEAD, int(math.ceil(f - left)))
            gain = sum(6.0 * BREW_DRINKS * p * (f - p) / f ** 3 for p in range(p0, min(f, p0 + n)))
            rate = self.hold_proj_rate()
            mode = "mid" if gain < rate else "daily"
            if mode != self.hold_mode:
                log("hold_mode", day=self.day, mode=mode, held=n, gain=round(gain, 2), rate=round(rate, 2),
                    left=left)
            self.hold_mode = mode
        return n if self.hold_mode == "mid" and n >= 1 else None

    def hold_mid(self, n, f, left, drink):
        """cx small hold: before mid-F, a standing that brews the whole hold once drink falls to the level projected
        for mid-F (o_brew_mid; not when that level is under the dry floor: o_brew_dry takes the plants there); from
        HOLD_MID_TOL days before mid-F on, a one-shot of what the hold still has (o_brew_midshot)."""
        p = f - left
        rate = self.hold_proj_rate()
        if p >= f / 2.0 - HOLD_MID_TOL:
            amount = min(30, self.pb_free() - self.brew_planned())
            if amount >= 1 and not self.own_pending("o_brew_midshot"):
                r = self.act("o_brew_midshot", "add_order", {"recipe": "brew_drink", "amount": amount}, retry=1,
                             limit=4)
                if r is not None:
                    log("hold_midshot", day=self.day, amount=amount, held=n, into_f=p, drink=drink, ok=r.get("ok"))
            return
        if self.hold_on_book("o_brew_mid"):
            return
        below = drink - rate * (f / 2.0 - p)
        if below <= HOLD_DRY_DAYS * rate:
            return
        r = self.act("o_brew_mid", "add_order", {"recipe": "brew_drink", "amount": min(30, n), "repeat": "daily",
                                                 "when": [{"stock": "drink", "below": int(math.ceil(below))},
                                                          {"stock": "plants_brewable", "at_least": 1},
                                                          {"stock": "barrels_empty", "at_least": 1}]},
                     retry=2, limit=6)
        if r is not None:
            log("hold_mid", day=self.day, amount=min(30, n), below=int(math.ceil(below)), rate=round(rate, 2),
                into_f=p, drink=drink, ok=r.get("ok"))


    def my1_plan(self):
        """The MY1 supply plan runs on open play shorter than a year (MY1's 216 days); OP1 keeps its own paths."""
        return self.alloc_on() and (self.days or 0) < 336

    def plan_queued(self):
        """cx MY1 supply plan: the brew work actually queued — the one-shots' left and the repeat standings the game
        marks firing (active, or a job in progress), bounded by the brewable plants. brew_planned also counts an idle
        standing whose drink cap is above drink, though its plants floor keeps it from firing (simulated: the
        plan's free plants read 2 short and its mid-F brew came short by them)."""
        n = 0
        for x in self.orders:
            if x.get("recipe") != "brew_drink":
                continue
            left = x.get("left") if isinstance(x.get("left"), (int, float)) else 0
            if not x.get("repeat"):
                n += max(0, left)
            elif x.get("active") is True or (x.get("jobs_in_progress") or 0) > 0:
                n += max(0, left)
        return min(n, self.st.get("plants_brewable") or 0)

    def f_record(self):
        """The plan's own (day, drink, food) record from F_REC_LEAD days before F: the score reads every day of A..H,
        and stock_hist keeps only SLOPE_WINDOW looks."""
        if not isinstance(self.day, (int, float)) or not isinstance(self.st.get("drink"), (int, float)):
            return
        if self.day < (self.days or 0) - self.f_len() - F_REC_LEAD:
            return
        rec = (self.day, self.st.get("drink") or 0, self.st.get("food_edible") or 0)
        if self.f_rec and self.f_rec[-1][0] == self.day:
            self.f_rec[-1] = rec
        elif not self.f_rec or self.f_rec[-1][0] < self.day:
            self.f_rec.append(rec)

    def f_drink_rate(self, prior_only=False):
        """The drink decline per day the plan projects: DRINK_PER_CIT_DAY for the census (the forecast while waves may
        still come), or the record's net decline over HOLD_RATE_DAYS when larger (brews only lower a net reading; the
        caravan's departure is not drinking). prior_only: the census rate alone (the reserve's: a steady floor).
        cx m13many: the record leaves out every look taken while the caravan settled (rate_hist's flag), not only
        today's: the settle window (CARAVAN_SETTLE_DAYS) ends before HOLD_RATE_DAYS of looks forget the visit. Hint
        std MY1-3 on e33d381 (17 citizens): caravan goods out d74-79 (drink 204 -> 110), on d91 the stock_hist fit
        read 5.1 a day, hold_active's drink-to-F test (121 < half of 5.1 x 97) dropped the armed hold for d91-97,
        the model's "brew_drink 2 daily, plants_brewable >= 3" went through unvetoed and brewed 2 plants (pb 4 -> 1
        by d100); F got 3 brews (f_plan need 5), drink 50 -> 35 at -0.24/day, supply 0.713 (the record with one of
        those plants held to the mid-F brew instead reads drink 1.0)."""
        pop = max(self.cit or 0, self.pop_forecast() or 0)
        rate = DRINK_PER_CIT_DAY * max(1, pop)
        if not prior_only and isinstance(self.day, (int, float)) and not self.caravan_settling():
            pts = [(p[0], p[1]) for p in self.rate_hist if self.day - p[0] <= HOLD_RATE_DAYS and not p[4]]
            if len(pts) >= 3 and pts[-1][0] - pts[0][0] >= 7:
                rate = max(rate, -ols_slope(pts))
        return rate

    def f_project(self, idx, rate, adds=(), dry=None, dry_until=None):
        """(slope, stock_H, low) of leg idx (1 drink, 2 food) over the score's A..H, one point a day: the plan's record
        (linear between looks) up to today, then today's stock falling `rate` a day plus `adds` ((day, units)
        landing that day on). `low` is the projected minimum after today. With `dry`, the projected stock before
        `dry_until` never stays under it: a brew (o_brew_dry's one a day) lifts it BREW_DRINKS."""
        H = int(self.days or 0)
        A = H - self.f_len()
        now = int(self.day) if isinstance(self.day, (int, float)) else 0
        cur = (self.st.get("drink") if idx == 1 else self.st.get("food_edible")) or 0
        rec = [(r[0], r[idx]) for r in self.f_rec if r[0] <= now]

        def known(x):
            if not rec:
                return cur
            if x <= rec[0][0]:
                return rec[0][1]
            for (d0, v0), (d1, v1) in zip(rec, rec[1:]):
                if d0 <= x <= d1:
                    return v0 + (v1 - v0) * (x - d0) / float(d1 - d0) if d1 > d0 else v1
            return rec[-1][1]
        pts, low, lift = [], None, 0
        for x in range(min(A, now + 1), H + 1):
            if x <= now:
                v = known(x)
            else:
                v = cur - rate * (x - now) + sum(a for t, a in adds if t <= x) + lift
                if dry is not None and x < (dry_until or 0) and v < dry:
                    lift += BREW_DRINKS
                    v += BREW_DRINKS
                low = v if low is None else min(low, v)
            if x >= A:
                pts.append((x, v))
        return ols_slope(pts), pts[-1][1], (cur if low is None else low)

    def f_brew_need(self, prior_only=False):
        """(brews, landing day, rate, projected slope): the fewest brews landing at mid-F that put the projected drink
        slope over F F_SLOPE_MARGIN above the score's line (-stock_H / T_STAR). The brew jobs already queued land in
        F_LAND_DAYS; until mid-F o_brew_dry keeps the stock over HOLD_DRY_DAYS of use (a brew whenever it dips:
        those are coverage's, not the plan's — landing the plan's brews at the dip instead put them 2 days into F,
        where they lift the slope a fifth as much). Memoised per load."""
        key = (self.loads, self.day, self.st.get("drink"), self.st.get("plants_brewable"), self.cit, len(self.orders),
               prior_only)
        memo = getattr(self, "_f_need_memo", None)
        if not isinstance(memo, dict) or len(memo) > 16:
            memo = self._f_need_memo = {}
        if key in memo:
            return memo[key]
        H = int(self.days or 0)
        f = self.f_len()
        now = int(self.day) if isinstance(self.day, (int, float)) else 0
        rate = self.f_drink_rate(prior_only)
        land0 = now + F_LAND_DAYS
        queued = self.plan_queued()
        base = [(land0, BREW_DRINKS * queued)] if queued else []
        land = max(land0, H - f + int(round(f / 2.0)))
        dry = HOLD_DRY_DAYS * rate
        out = (0, land, rate, None)
        if land <= H - F_LAND_DAYS:
            for k in range(0, F_PLAN_MAX + 1):
                s, vh, _ = self.f_project(1, rate, base + ([(land, BREW_DRINKS * k)] if k else []), dry=dry,
                                          dry_until=land)
                out = (k, land, rate, s)
                if s >= -max(0.0, vh) / T_STAR + F_SLOPE_MARGIN:
                    break
        memo[key] = out
        return out

    def f_mid_need(self, rate):
        """The brews at mid-F that turn a drink stock falling `rate` a day and standing at the dry level
        (HOLD_DRY_DAYS of use) on the landing day into a slope F_SLOPE_MARGIN over the score's line: the hold's
        steady size (the plants that keep drink over the dry level before then are the plan's surplus or
        o_brew_dry's)."""
        f = self.f_len()
        land = int(round(f / 2.0))
        low = HOLD_DRY_DAYS * rate
        for k in range(0, F_PLAN_MAX + 1):
            pts = [(x, low + rate * (land - x) + (BREW_DRINKS * k if x >= land else 0)) for x in range(0, f + 1)]
            if ols_slope(pts) >= -max(0.0, pts[-1][1]) / T_STAR + F_SLOPE_MARGIN:
                return k
        return F_PLAN_MAX

    def my1_hold_reserve(self):
        """cx MY1 supply plan: the held plants — before F the mid-F need (f_mid_need at the census rate) plus
        F_PLAN_SPARE (at least F_PLAN_MIN); inside F every free plant (the plan's own orders take them, no other
        consumer). (Shrinking it by what drink needs to reach mid-F over the dry level was simulated worse: 60 of
        480 sweeps under 0.99 against 20, the pre-F brews' rounding taking the mid-F ones.)"""
        left = self.days_to_end()
        if left is not None and left <= self.f_len():
            return max(F_PLAN_MIN, self.pb_free())
        return max(F_PLAN_MIN, self.f_mid_need(self.f_drink_rate(prior_only=True)) + F_PLAN_SPARE)

    def f_plan_brew(self):
        """cx MY1 supply plan, from HOLD_PREP_DAYS before F: the drink plan's brews. A landing within HOLD_MID_TOL days
        is a one-shot now (o_brew_midshot); a later one a standing that fires the need once drink falls to the level
        projected for the landing day (o_brew_mid: it acts between the model's 7-14 day loads), re-cut when the need
        or the level moves and cancelled once nothing is needed (a fired standing's jobs count as queued)."""
        need, land, rate, slope = self.f_brew_need()
        now = int(self.day)
        drink = self.st.get("drink") or 0
        free = self.pb_free() - self.plan_queued()
        self.f_dry_floor = None
        plan = (need, land, min(need, max(0, free)))
        if plan != self.f_plan_key:
            self.f_plan_key = plan
            log("f_plan", day=self.day, need=need, land=land, rate=round(rate, 2), drink=drink,
                pb=self.st.get("plants_brewable"), free=free, slope=None if slope is None else round(slope, 2),
                food=self.st.get("food_edible"))
        mid_id = self.key_order.get("o_brew_mid")
        mid = next((x for x in self.orders if x.get("id") == mid_id), None) if mid_id is not None else None
        amount = min(need, F_PLAN_MAX, max(0, free))
        if amount < 1 or land - now <= HOLD_MID_TOL or self.f_shot_due(now, land, amount):
            if mid is not None and not (mid.get("jobs_in_progress") or 0) and self.may("o_brew_mid_cut", 2):
                self.act("o_brew_mid_cut", "cancel_order", {"order_id": mid_id}, retry=2, limit=8)
                self.done.discard("o_brew_mid")
            if amount >= 1 and not self.own_pending("o_brew_midshot"):
                r = self.act("o_brew_midshot", "add_order", {"recipe": "brew_drink", "amount": amount}, retry=1,
                             limit=8)
                if r is not None:
                    log("hold_midshot", day=self.day, amount=amount, need=need, land=land, drink=drink,
                        ok=r.get("ok"))
            return
        level = drink + BREW_DRINKS * self.plan_queued() - rate * (land - now)
        if level <= HOLD_DRY_DAYS * rate + rate * HOLD_MID_TOL:


            if mid is not None and not (mid.get("jobs_in_progress") or 0) and self.may("o_brew_mid_cut", 2):
                self.act("o_brew_mid_cut", "cancel_order", {"order_id": mid_id}, retry=2, limit=8)
                self.done.discard("o_brew_mid")
            self.f_prelift(max(0, free), rate, land, drink)
            return
        below = int(math.ceil(level))
        if mid is not None:
            have = [v for k, t, v in when_sig(mid.get("when")) if k == ("DRINK", None) and t == "LessThan"]
            tot = mid.get("total") or mid.get("left")
            if (have and abs(have[0] - below) > max(3, 0.15 * below)) or (isinstance(tot, int) and tot != amount):
                if not (mid.get("jobs_in_progress") or 0) and self.may("o_brew_mid_cut", 2):
                    self.act("o_brew_mid_cut", "cancel_order", {"order_id": mid_id}, retry=2, limit=8)
                    self.done.discard("o_brew_mid")
            return
        r = self.act("o_brew_mid", "add_order", {"recipe": "brew_drink", "amount": amount, "repeat": "daily",
                                                 "when": [{"stock": "drink", "below": below},
                                                          {"stock": "plants_brewable", "at_least": 1},
                                                          {"stock": "barrels_empty", "at_least": 1}]},
                     retry=2, limit=8)
        if r is not None:
            log("hold_mid", day=self.day, amount=amount, below=below, rate=round(rate, 2), land=land, drink=drink,
                ok=r.get("ok"))

    def f_load_gap(self):
        """cx m13many: the days between the plan's looks (the median of the last three gaps of f_rec), F_LOAD_GAP
        without such a record; 1..14."""
        days = [r[0] for r in self.f_rec]
        gaps = sorted(b - a for a, b in list(zip(days, days[1:]))[-3:] if b > a)
        g = gaps[len(gaps) // 2] if gaps else F_LOAD_GAP
        return max(1, min(14, g))

    def f_shot_due(self, now, land, amount):
        """cx m13many (std MY1-3 probe on 657e3d0, 17 citizens, supply 0.735): the mid-F batch goes now when its
        start (the Still brews about one a day, so a batch of k centres k/2 days after it starts: d207-211 drink
        0 -> 17 for 4 brews) is within HOLD_MID_TOL days, or when the next look (f_load_gap on) comes after it. On d198
        the plan wanted 5 brews landing d202 with drink 9; the next look was d205, the batch landed d207-211 and
        drink read 0 on d207 (coverage 0.964, slope over F negative).
        cx shotdue2 (std MY1-3 probe on e20ce56, 17 citizens): the start counts the whole batch — k brews at one a day
        centred on the landing start ceil(k/2) days before it — and the batch goes whenever the next look would come
        after that start (no tolerance on that side; a look on the start day itself still starts it on time, so it
        waits for that one: test_small_hold's d194 look, start d201, next d201). On d197 the plan wanted 3 landing
        d202 (start d200, next look d204): the old test (204 > 204.5) waited, the d204 midshot landed d208-212, 6
        days late."""
        start = land - (amount + 1) // 2
        return now >= start - HOLD_MID_TOL or now + self.f_load_gap() > start

    def f_leg_score(self, rate, adds):
        """cx m13many: the drink leg's score (bench/outcomes.py: 0.5 coverage + 0.5 min(1, T / T_STAR), T = stock_H
        over the least-squares decline of A..H) of the plan's record up to today and, from tomorrow, today's stock
        falling `rate` a day, never under 0 (the fort drinks water there), plus `adds` ((day, drinks)) landing."""
        H = int(self.days or 0)
        A = H - self.f_len()
        now = int(self.day) if isinstance(self.day, (int, float)) else 0
        rec = {r[0]: r[1] for r in self.f_rec if A <= r[0] <= now}
        v = float(self.st.get("drink") or 0)
        pts = sorted(rec.items())
        if not pts or pts[0][0] > A:
            pts = [(A, pts[0][1] if pts else v)] + pts
        for x in range(now + 1, H + 1):
            v = max(0.0, v - rate) + sum(a for t, a in adds if t == x)
            if x >= A:
                pts.append((x, v))
        if len(pts) < 2:
            return 1.0
        cov = sum(1 for x, y in pts if x > A and y > 0) / float(max(1, H - A))
        sl, vh = ols_slope(pts), pts[-1][1]
        t = float("inf") if sl >= 0 and vh > 0 else (0.0 if vh <= 0 else vh / -sl)
        return 0.5 * cov + 0.5 * min(1.0, t / T_STAR)

    def f_split(self, free, rate, land):
        """cx m13many: (pre, mid) — the free plants split into a lift brewed now (landing F_LAND_DAYS on) and the
        mid-F batch, by the best worst-case drink score over F_SPLIT_RATES x rate (the queued brews land with the lift;
        a tie keeps the smaller lift)."""
        now = int(self.day) if isinstance(self.day, (int, float)) else 0
        q = BREW_DRINKS * self.plan_queued()
        best = None
        for pre in range(0, max(0, free) + 1):
            adds = [(now + F_LAND_DAYS, q + BREW_DRINKS * pre), (land, BREW_DRINKS * (free - pre))]
            sc = min(self.f_leg_score(rate * m, adds) for m in F_SPLIT_RATES)
            if best is None or sc > best[0] + 1e-9:
                best = (sc, pre)
        return (0, 0) if best is None else (best[1], max(0, free) - best[1])

    def f_prelift(self, free, rate, land, drink):
        """cx m13many (hint hard MY1-3 on 838106a, supply 0.512): drink reaches o_brew_dry's floor before the mid-F
        landing. The plants o_brew_dry would spend one a day (d181-202: pb 5 -> 1, the d202 midshot got 1 of the plan's
        3; drink 8 -> 1 over F at -0.22/day) are split once by the score instead (f_split): a lift brewed now
        (o_brew_prelift, one-shot) and the mid-F batch, which o_brew_dry no longer takes (f_dry_floor = mid + 1).
        Replayed on its stock: the dribble 0.53, 1 brew on d180 + 4 landing d200 0.98."""
        pre, mid = self.f_split(free, rate, land)
        if mid >= 1:
            self.f_dry_floor = mid + 1
        if pre >= 1 and not self.own_pending("o_brew_prelift"):
            r = self.act("o_brew_prelift", "add_order", {"recipe": "brew_drink", "amount": min(F_PLAN_MAX, pre)},
                         retry=1, limit=8)
            if r is not None:
                log("f_prelift", day=self.day, pre=pre, mid=mid, land=land, drink=drink, rate=round(rate, 2),
                    ok=r.get("ok"))

    def f_reserve_hold(self):
        """cx MY1 supply plan (food): before F on MY1, the non-grazers are F's meat — the food slaughters leave them
        while food is not short: at least F_RESERVE_FOOD_PER_CIT per citizen, or a net drain (food_cover) that lasts
        to F."""
        if not self.my1_plan():
            return False
        left = self.days_to_end()
        if left is None or left <= self.f_len():
            return False
        food = self.st.get("food_edible") or 0
        if food >= F_RESERVE_FOOD_PER_CIT * max(1, self.cit or 0):
            return True
        cover = self.food_cover()
        return cover is None or cover >= left - self.f_len()

    def hold_veto(self, name, args):
        """cx hold veto (hint std MY1-3 on c44c96b: the model's "brew_drink 3 daily, plants_brewable >= 1" added on d116
        brewed 2 of the held pig tails before hold_supply cancelled it on the next layer pass, d117): a model brew order
        that could take the harvest-closed hold's plants before F is refused at the call — the same orders
        hold_supply cancels (no plants_brewable floor at the reserve). A message for the refusal, or None."""
        if name not in ("add_order", "add_manager_order") or not isinstance(args, dict):
            return None
        brew = args.get("recipe") == "brew_drink" or "BREW" in str(args.get("reaction") or "").upper()\
            or (name == "add_manager_order" and "BREW" in str(args.get("job") or "").upper())
        if not brew:
            return None
        if self.barrel_keep():
            return self.barrel_veto(name, args)
        left = self.days_to_end()


        if not self.hold_armed or left is None or (left <= self.f_len() and not self.my1_plan())\
                or not self.hold_active():
            return None
        reserve = self.hold_reserve()
        if self.my1_plan():


            amount = args.get("amount") if isinstance(args.get("amount"), int) else 1
            if self.leaves_reserve(amount, args.get("when"), bool(args.get("repeat")), reserve):
                return None
            log("hold_veto", day=self.day, tool=name, args=args, reserve=reserve, pb=self.st.get("plants_brewable"))
            return ("not run: no new crop can ripen before the run ends, so the deterministic layer keeps %d brewable "
                    "plants to brew at mid-F (the last %d days), where they lift the drink trend most. %d plants are "
                    "free now: a one-shot of at most that many runs, or a repeat order with a plants_brewable "
                    "at_least %d clause." % (reserve, self.f_len(),
                                             max(0, self.pb_free() - self.plan_queued() - reserve),
                                             reserve + max(1, amount)))
        if any(k == ("PLANT", "DRINK_MAT") and t == "AtLeast" and isinstance(v, (int, float)) and v >= reserve
               for k, t, v in when_sig(args.get("when"))):
            return None
        log("hold_veto", day=self.day, tool=name, args=args, reserve=reserve, pb=self.st.get("plants_brewable"))
        return ("not run: no new crop can ripen before the run ends, so the deterministic layer keeps the brewable "
                "plants for the last %d days and brews them there one a day (drink keeps rising to the end). A brew "
                "order now needs a plants_brewable at_least %d clause." % (self.f_len(), reserve))

    def keeps_barrel(self, amount, when, repeat):
        """cx plant barrel keep (BARREL_KEEP above): a brew order leaves the plant barrel its BARREL_KEEP plants — a
        standing whose plants_brewable floor is at least its firing plus BARREL_KEEP (a firing queues its whole
        amount once the floor holds), a one-shot no larger than the free plants no queued job holds, less
        BARREL_KEEP."""
        a = amount if isinstance(amount, int) and not isinstance(amount, bool) and amount >= 1 else 1
        if repeat:
            floors = [v for k, t, v in when_sig(when) if k == ("PLANT", "DRINK_MAT") and t == "AtLeast"
                      and isinstance(v, (int, float)) and not isinstance(v, bool)]
            return bool(floors) and max(floors) >= a + BARREL_KEEP
        return a <= self.pb_free() - self.brew_planned() - BARREL_KEEP

    def barrel_veto(self, name, args):
        """cx plant barrel keep (7c43df4 open point): a model brew order that could take the plant barrel's last
        plants is refused at the call while barrel_keep() holds (MY1 open play) — o_brew's own floor would be bypassed
        otherwise (brew_on_book took a model's floor-2 standing for o_brew, and its firing could empty the barrel,
        whose tile then went to the prepared meals). A message for the refusal, or None."""
        if self.keeps_barrel(args.get("amount"), args.get("when"), bool(args.get("repeat"))):
            return None
        need = (args.get("amount") if isinstance(args.get("amount"), int) else 1) + BARREL_KEEP
        log("barrel_veto", day=self.day, tool=name, args=args, pb=self.st.get("plants_brewable"))
        return ("not run: the deterministic layer keeps the fort's only plant barrel holding a plant (a barrel emptied "
                "of plants is taken by other food, and later harvests then lie loose and rot); its own brew standing "
                "already brews %d a day while drink is under its level. A brew order needs repeat with a "
                "plants_brewable at_least clause of at least amount + %d (%d here)." % (BARREL_KEEP_AMOUNT, BARREL_KEEP,
                                                                                         need))

    def barrel_cancel(self):
        """cx plant barrel keep: while barrel_keep() holds, a brew standing on the book that is not this layer's and
        would not keep the barrel (keeps_barrel) is cancelled — one added before the keep (inside the hold or the
        food-lean keeper, whose vetoes allowed other floors) would empty the barrel all the same."""
        if not self.barrel_keep():
            return
        for x in self.orders:
            if x.get("recipe") != "brew_drink" or not x.get("repeat") or x.get("id") in self.owned\
                    or x.get("id") is None:
                continue
            if self.keeps_barrel(x.get("total") or x.get("left"), x.get("when"), True):
                continue
            r = self.act("barrel_cancel_%s" % x.get("id"), "cancel_order", {"order_id": x.get("id")}, retry=2, limit=3)
            if r is not None:
                log("barrel_cancel", day=self.day, order=x.get("id"), when=x.get("when"), ok=r.get("ok"))

    def own_pending(self, key):
        """This layer's one-shot under `key` is still on the book with work left."""
        oid = self.key_order.get(key)
        return oid is not None and any(x.get("id") == oid and (x.get("left") or 0) > 0 for x in self.orders)

    def allocate_plants(self):
        """The allocation's own daily one-shots (no `when`: one-shot orders cannot carry one, so the gates are read
        here): a brew batch while drink is the shorter leg (or in the last stretch), a cook batch while food is,
        each down to plant_floor(). Not on lab tasks."""
        if not self.alloc_on() or not isinstance(self.day, (int, float)):
            return
        plan = self.plant_plan()
        sides, last, floor = plan["sides"], plan["last"], plan["floor"]
        dd, fd = self.leg_days()
        pb = self.st.get("plants_brewable") or 0
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        if "brew" in sides and (dd <= fd or last) and "Still" in have and not self.own_pending("o_brew_alloc"):

            n = min(ALLOC_BREW_MAX, self.brew_budget() - floor, (self.st.get("barrels_empty") or 0) - self.brew_queued())
            cap = self.barrel_brew_cap()
            if cap is not None:
                n = min(n, cap)
            if last and dd > fd:
                n = min(n, ALLOC_BREW_MAX // 2)
            if n >= 1:
                self.act("o_brew_alloc", "add_order", {"recipe": "brew_drink", "amount": n}, retry=1, limit=99)
        seeds_ok = self.seeds_banked()
        if "cook" in sides and (fd < dd or last) and "Kitchen" in have and seeds_ok\
                and not self.own_pending("o_cook_alloc"):
            other = (self.st.get("plants_total") or 0) - pb
            cfloor = floor if self.hold_cook() else self.base_plant_floor()

            n = min(ALLOC_COOK_MAX, max(0, self.brew_budget() - cfloor) + max(0, other) // 2)
            if last and fd >= dd:
                n = min(n, ALLOC_COOK_MAX // 2)
            if n >= 1 and self.meal_wait():
                log("meal_wait", day=self.day, source="o_cook_alloc", loose=d(self.plant_loose).get("loose"))
            elif n >= 1:
                self.act("o_cook_alloc", "add_order", {"recipe": "cook_meal", "amount": n}, retry=1, limit=99)

    def press_waiting(self):
        """cx barrel press: brews that no empty barrel can take now — the brew jobs on the book (brew_planned), or,
        once this fort's plants rot, every brewable plant over the rot guard's floor (it brews them all down). Plants
        the drink caps, the hold or the lean chose not to brew (CX_REVIEW P1-5: MY1 forts at pb 40-67 with drink at
        its cap; hint std OP1-1 on 68bd4c7 d169-197: pb 40-51 beside 14-21 empty barrels) wait on no barrel."""
        be = self.st.get("barrels_empty") or 0
        if self.rot_seen:
            waiting = (self.st.get("plants_brewable") or 0) - self.rot_keep() - be
        else:
            waiting = self.brew_planned() - be




        return max(waiting, self.seed_wait)

    def barrel_press(self):
        """cx: the barrel press (PRESS_* above). Open play only (alloc_on: no hands-off window), on a full-year run or
        once this fort's plants rot (the barrel-ahead gate in supply()), not while the food-lean keeper holds the
        plants. Two readings, either one presses:
        - standing (press_stand), not before PRESS_FROM_DAY unless the plants already rot: on at PRESS_ON brews
          waiting on barrels (press_waiting) with at most PRESS_BARRELS_LOW empty, off at PRESS_OFF waiting or
          PRESS_BARRELS_FREE empty;
        - harvest (press_harv, HARVEST_PRESS_* above), with crops in the plots, from HARVEST_PRESS_FROM_DAY unless the
          plants already rot: on at HARVEST_PRESS_ON empty barrels short of the coming harvest
          (harvest_barrels_short) with fewer than PRESS_BARRELS_FREE empty, off once they cover it (or the plants
          stand idle beside free barrels: harvest_barrels_short reads 0).
        Read once per load."""
        if self.press_memo == self.loads:
            return self.press_on
        self.press_memo = self.loads
        stand, harv = self.press_stand, self.press_harv
        short = None
        if not self.alloc_on() or not ((self.days or 0) >= 336 or self.rot_seen) or self.food_lean():
            stand = harv = False
        else:
            be = self.st.get("barrels_empty") or 0
            if not self.rot_seen and (self.day or 0) < PRESS_FROM_DAY:
                stand = False
            else:
                waiting = self.press_waiting()
                if not stand and waiting >= PRESS_ON and be <= PRESS_BARRELS_LOW and not self.caravan_active:
                    stand = True
                elif stand and (waiting <= PRESS_OFF or be >= PRESS_BARRELS_FREE):
                    stand = False
            if (not self.rot_seen and (self.day or 0) < HARVEST_PRESS_FROM_DAY) or self.harvest_growing() <= 0:
                harv = False
            else:
                short = self.harvest_barrels_short()
                if not harv and short >= HARVEST_PRESS_ON and be < PRESS_BARRELS_FREE and not self.caravan_active:
                    harv = True
                elif harv and short <= 0:
                    harv = False
        on = stand or harv
        if on != self.press_on or harv != self.press_harv:
            log("barrel_press", day=self.day, on=on, standing=stand, harvest=harv, short=short,
                pb=self.st.get("plants_brewable"), barrels=self.st.get("barrels_empty"),
                rotten=self.st.get("plants_rotten"), logs=self.logs())
        self.press_on, self.press_stand, self.press_harv = on, stand, harv
        if on and isinstance(self.day, (int, float)):
            self.press_day = self.day
        return on

    def labor_press(self):
        """cx brew labor press (LABOR_* above): brewable plants a Still job can take wait for a hand while empty barrels
        stand free. Open play, on a full-year run or once this fort's plants rot, from LABOR_FROM_DAY (unless they
        already rot), not while the food-lean keeper holds the plants, the merchants' plants stand in the stocks or a
        civilian alert confines the fort. On while at least PRESS_ON brews wait (the jobs on the book or wanted —
        brew_planned / seed_wait — or, once plants rot, every brewable plant over the rot guard's floor; bounded by
        pb_free), a Still job stands untaken (job_details with no worker) while fewer have a worker than the Stills
        and the waiting brews could keep busy, and someone is on the wood crafts; off at PRESS_OFF waiting, once no
        Still job stood on two loads in a row (DF made no job: a missing hand is not the reason; hint std OP1-1 on
        68bd4c7 d122-225 pb 4-51 with no Still job and drink over its cap), or on any of the gates. Read once per
        load."""
        if self.labor_memo == self.loads:
            return self.labor_on
        self.labor_memo = self.loads
        on, why = self.labor_on, None
        alert = bool(d(self.o.get("burrows")).get("civilian_alert"))
        if self.hands_off is not None or not ((self.days or 0) >= 336 or self.rot_seen) or self.food_lean()\
                or (not self.rot_seen and (self.day or 0) < LABOR_FROM_DAY) or self.caravan_active or alert:
            on = False
        else:
            free = self.pb_free()
            keep = self.rot_keep() if self.rot_seen else 0
            wanted = max(self.brew_planned(), self.seed_wait, free - keep if self.rot_seen else 0)
            waiting = max(0, min(wanted, free - keep))
            stills = [w for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Still"
                      and w.get("built") is not False]
            jobs = [d(j) for w in stills for j in lst(w.get("job_details"))]
            worked = sum(1 for j in jobs if isinstance(j.get("worker_id"), int) and j["worker_id"] >= 0)
            idle_jobs = len(jobs) - worked
            crafters = sum(1 for p in self.people if p.get("job") == "MakeCrafts")
            if not on and waiting >= PRESS_ON and (self.st.get("barrels_empty") or 0) >= 1 and idle_jobs >= 1\
                    and worked < min(len(stills), waiting) and crafters >= 1:
                on, why = True, dict(waiting=waiting, stills=len(stills), worked=worked, idle_jobs=idle_jobs,
                                     crafters=crafters)
            elif on and (waiting <= PRESS_OFF or (not jobs and self.labor_nojob >= 1)):
                on = False
            self.labor_nojob = 0 if jobs else self.labor_nojob + 1
        if on != self.labor_on:
            log("labor_press", day=self.day, on=on, pb=self.st.get("plants_brewable"), pb_free=self.pb_free(),
                barrels=self.st.get("barrels_empty"), **(why or {}))
        self.labor_on = on
        if on and isinstance(self.day, (int, float)):
            self.press_day = self.day
        return on

    def cook_stalled(self):
        """cx KITCHEN STALL (above): this layer's o_cook_rot has stood on the book with no job for COOK_STALL_DAYS, or
        every built Kitchen has held a job of another order that long. Read once per load."""
        if self.stall_memo == self.loads:
            return self.stall_on
        self.stall_memo = self.loads
        oid = self.key_order.get("o_cook_rot")
        mine = next((x for x in self.orders if oid is not None and x.get("id") == oid and (x.get("left") or 0) > 0),
                    None)
        if mine is not None and not (mine.get("jobs_in_progress") or 0):
            if self.cook_wait_since is None:
                self.cook_wait_since = self.now
        else:
            self.cook_wait_since = None
        kitchens = [w for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Kitchen"
                    and w.get("built") is not False]
        busy = bool(kitchens) and all(any(d(j).get("job") == "PrepareMeal" and (oid is None or d(j).get("order_id") != oid)
                                          for j in lst(w.get("job_details"))) for w in kitchens)
        if busy:
            if self.kitchen_busy_since is None:
                self.kitchen_busy_since = self.now
        else:
            self.kitchen_busy_since = None
        wait = COOK_STALL_DAYS * DAY
        on = (self.cook_wait_since is not None and self.now - self.cook_wait_since >= wait)\
            or (self.kitchen_busy_since is not None and self.now - self.kitchen_busy_since >= wait)
        if on != self.stall_on:
            log("kitchen_stall", day=self.day, on=on, rot_order=oid if mine is not None else None,
                rot_no_job=self.cook_wait_since is not None, busy=busy, pb=self.st.get("plants_brewable"),
                rotten=self.st.get("plants_rotten"))
        self.stall_on = on
        return on

    def f_food_falling(self):
        """cx KITCHEN STALL: food's least-squares slope over the score's final stretch F (the loads from its start,
        the last one before it included) is negative — a brewed plant then lowers the falling leg sooner than its rot
        would (replayed 014f7eb OP1-3: the 17 plants brewed on d319-321 instead of rotting on d320-335 take the food
        leg from 0.791 to 0.765, drink already 1.0). None-safe: under two points it reads not falling."""
        if not isinstance(self.day, (int, float)) or not self.days:
            return False
        start = self.days - self.f_len()
        pts = [(p[0], p[2]) for p in self.stock_hist if isinstance(p[0], (int, float))]
        before = [q for q in pts if q[0] <= start]
        pts = before[-1:] + [q for q in pts if q[0] > start]
        if len(pts) < 2:
            return False
        slope = ols_slope(pts)
        return slope is not None and slope < 0

    def rot_guard(self):
        """cx: on a fort whose plants rot (rot_seen, ROT_* above), a standing plant is a seed about to be lost: the
        Still is the only user that hands the seed back, so each load brews the brewable stock down to ROT_KEEP
        with a one-shot (no `when`: the drink caps, the allocation's yield and the reserve/hold floors all left the
        measured plants standing until they rotted), and a one-shot barrel batch covers what the empty barrels
        cannot take (the standing plants plus the seeds already in the plots, the next harvest). Open play only
        (alloc_on); skipped on the caravan's arrival jump (the merchants' goods, as glut_bank) and inside F while
        food is the falling min leg (a plant still counts as food there and the run ends before it rots)."""
        aged = self.aged_plants()
        stuck = self.loose_stuck()
        if not (self.rot_seen or aged >= 1 or stuck >= 1) or not self.alloc_on()\
                or not isinstance(self.day, (int, float)):
            return
        if self.caravan_active and self.glut_jump >= GLUT_JUMP and self.caravan_arrival_day is not None\
                and self.day - self.caravan_arrival_day <= 1:
            return
        plan = self.plant_plan()
        if plan["in_f"] and plan["food_first"]:
            return
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        pb = self.st.get("plants_brewable") or 0
        barrels = self.st.get("barrels_empty") or 0
        keep = plan["rot_keep"]

        glut = self.drink_glut()
        aged_only = not self.rot_seen or glut
        risk = max(aged, stuck)
        if self.caravan_active:


            p = d(self.plant_loose)
            risk = min(risk, p["loose"] if p.get("day") == self.day and isinstance(p.get("loose"), int) else 0)
        cap = max(0, risk - self.brew_planned()) if aged_only else ALLOC_BREW_MAX






        cook = plan["lean"] or (glut and (barrels < PRESS_BARRELS_FREE or self.wood_dry()))


        meal_ok = any(d(v).get("cookable") for v in d(self.st.get("plants_by_kind")).values())
        stuck_still = stuck >= 1 and not meal_ok
        if stuck_still:
            cook = False
        stall = False
        if cook and "Kitchen" in have and cap >= 1:


            stall = "Still" in have and self.cook_stalled() and not (plan["in_f"] and self.f_food_falling())
            n = min(cap, self.pb_free() - keep)
            if not stall:
                if n >= 2 and not self.own_pending("o_cook_rot"):
                    self.act("o_cook_rot", "add_order", {"recipe": "cook_meal", "amount": max(1, n // 2)},
                             retry=1, limit=99)
                    log("rot_cook", day=self.day, plants=n, aged=aged, sides=plan["sides"], lean=plan["lean"],
                        drink=self.st.get("drink"), food=self.st.get("food_edible"))
                return
            aged_only = True
            cap = max(0, risk - self.brew_planned())
        if "Still" in have and (not plan["lean"] or stuck_still or stall):




            pending = sum(max(0, x.get("left") or 0) for x in self.orders if x.get("id") in self.rot_brews)



            limit = min(ROT_SHOT_MAX, max(ALLOC_BREW_MAX, risk))
            n = min(limit - pending, self.brew_budget() - keep, barrels - self.brew_queued())
            if aged_only:
                n = min(n, cap - pending)
            bcap = self.barrel_brew_cap()
            if bcap is not None:
                n = min(n, bcap)
            if n >= 1:
                r = self.act("o_brew_rot", "add_order", {"recipe": "brew_drink", "amount": n}, retry=1, limit=99)
                oid = d(d(r).get("result")).get("order_id") if r and r.get("ok") else None
                if oid is not None:
                    self.rot_brews.add(oid)
                    if stall:
                        self.stall_brews.add(oid)
                        log("stall_brew", day=self.day, brews=n, risk=risk, aged=aged, stuck=stuck, keep=keep, pb=pb,
                            barrels=barrels, rot_order=self.key_order.get("o_cook_rot"))
                    if stuck >= 1:
                        log("stuck_brew", day=self.day, brews=n, stuck=stuck, keep=keep, pb=pb,
                            loose=d(self.plant_loose).get("loose"), barrels=barrels,
                            alert=d(self.o.get("burrows")).get("civilian_alert"))
                    if plan["hold"]:
                        log("rot_reserve_out", day=self.day, brews=n, keep=keep, floor=plan["floor"],
                            rotting=self.rotting_held(), pb=pb, loose=d(self.plant_loose).get("loose"))
        if not self.rot_seen and stuck < 1:
            return
        growing = sum(p.get("seeds_or_crops_in_plot") or 0 for p in lst(self.o.get("farm_plots"))
                      if isinstance(p, dict) and isinstance(p.get("seeds_or_crops_in_plot"), int))
        short = max(0, pb - keep) + growing - barrels
        if short >= 1 and "Carpenters" in have and self.logs() >= 4 and not self.own_pending("o_barrel_rot"):
            self.act("o_barrel_rot", "add_order", {"recipe": "make_barrel", "amount": min(ROT_BARREL_MAX, short)},
                     retry=1, limit=99)

    def age_plants(self):
        """cx pre-rot guard: move the free brewable plants' ages (first-in first-out) to this load's pb_free."""
        if not isinstance(self.st.get("plants_brewable"), (int, float)):
            return
        now, tot = self.pb_free(), sum(n for _, n in self.plant_age)
        if now > tot:

            self.plant_age.append([self.day if self.day >= 1 else None, now - tot])
        gone = max(0, tot - now)
        while gone > 0 and self.plant_age:
            take = min(gone, self.plant_age[0][1])
            self.plant_age[0][1] -= take
            gone -= take
            if self.plant_age[0][1] <= 0:
                self.plant_age.pop(0)

    def aged_plants(self):
        """cx pre-rot guard: the free brewable plants at least PLANT_USE_AGE days old. Full-year open play only: the
        OP1 embark has no stockpile, so a plant lies loose until a job takes it (all three measured lives above);
        MY1's handed-over forts kept pb 40-67 standing for 200 days without rot (CX_REVIEW P1-5), their stock in
        stockpiles turning over unseen, and keep the rot-seen arming — once a MY1 fort's own plants rot (rot_seen),
        its ages count too (cx rotting reserve: the held plants of hint std MY1-3 on c44c96b)."""
        if not isinstance(self.day, (int, float)) or self.hands_off is not None\
                or (self.days < 336 and not self.rot_seen):
            return 0
        return sum(n for d0, n in self.plant_age if d0 is not None and self.day - d0 >= PLANT_USE_AGE)

    def cover_336(self, leg, stock, prior):
        """cx: `stock` against DRINK_GLUT_MARGIN times a 336-day cover of `leg` (the measured use, never under the
        prior, for the census or the forecast waves, whichever is larger)."""
        rate = max(self.measured_rate(leg) or 0, prior)
        pop = max(self.cit or 0, self.pop_forecast() if self.alloc_on() else 0)
        return pop > 0 and stock >= DRINK_GLUT_MARGIN * 336 * rate * pop

    def drink_glut(self):
        """cx drink glut (above): drink past DRINK_GLUT_MARGIN 336-day covers while food is not, and the free seeds
        can sow every plot tile (a cooked plant hands no seed back)."""
        if not self.alloc_on() or not self.cover_336("drink", self.st.get("drink") or 0, DRINK_PER_CIT_DAY):
            return False
        if self.cover_336("food", self.st.get("food_edible") or 0, FOOD_PER_CIT_DAY):
            return False
        tiles, sown = self.plot_tiles()
        free = (self.st.get("seeds") or 0) - sown
        return free >= tiles - sown

    def wood_dry(self):
        """cx wood dry (above): full-year open play, WOOD_DRY_DAYS of daily readings with no citizen felling and no
        log rise, and the stock under WOOD_DRY_LOGS."""
        if self.days < 336 or self.hands_off is not None or not self.wood_hist\
                or not isinstance(self.day, (int, float)):
            return False
        span = [h for h in self.wood_hist if self.day - h[0] <= WOOD_DRY_DAYS]
        if not span or self.day - self.wood_hist[0][0] < WOOD_DRY_DAYS or span[-1][1] >= WOOD_DRY_LOGS:
            return False
        if any(f for _, _, f in span):
            return False
        return all(b[1] <= a[1] for a, b in zip(span, span[1:]))

    def rot_keep(self):
        """cx (CX_REVIEW P1-6 / §3-1): the rot guard's floor. ROT_KEEP (o_brew's own 2) on an ordinary day — a
        rotting plant is a seed lost, and brewing hands the seed back — but while the harvest-closed hold is armed,
        max(ROT_KEEP, plant_floor()) (the hold's F reserve), so the guard cannot brew the plants carried into F down
        to 2 before F starts (the hold's one-a-day standings then had nothing to hold). The food-lean endgame
        already stops the guard's brew. The reserve-build window alone does not raise it: the measured cx6f40047
        OP1-0 d218-249 (inside that window) had pb 12 -> 1 with 8 rotten under capped standings — a reserve that
        rots is not carried into F (test_capped_standings_do_not_keep_the_plants_from_the_still)."""
        if self.hold_active():


            keep, rotting = max(ROT_KEEP, self.plant_floor()), self.rotting_held()
            return max(0, min(keep, self.pb_free() - rotting)) if rotting > 0 else keep
        stuck = self.loose_stuck()
        return max(0, min(ROT_KEEP, self.pb_free() - stuck)) if stuck > 0 else ROT_KEEP

    def rotting_held(self):
        """cx rotting reserve (above): once this fort's plants rot, the free brewable plants at least PLANT_USE_AGE
        days old (aged_plants) that the last PLANT stock query found loose (plant_loose: not in a container, a job, a
        building or rotten) — without a fresh census reading, none (where they lie is unknown: the hold keeps them).
        cx stuck harvest: on any fort, rot seen or not, also the loose_stuck() plants (no barrel took them)."""
        stuck = self.loose_stuck()
        if not self.rot_seen:
            return stuck
        aged = self.aged_plants()
        p = d(self.plant_loose)
        fresh = isinstance(p.get("day"), (int, float)) and isinstance(self.day, (int, float))\
            and self.day - p["day"] <= PLANT_USE_AGE
        return max(stuck, min(aged, p["loose"]) if fresh and isinstance(p.get("loose"), int) else 0)

    def loose_stuck(self):
        """cx stuck harvest (LOOSE_BREW_DAYS above): the brewable plant units the PLANT census has read loose on every
        reading for LOOSE_BREW_DAYS — the fewest loose on the readings from the newest one at least that old to today
        (each of those readings > 0, today's reading fresh). 0 without such a span (a reading of 0 loose in between
        ends it: the plants found a barrel or a job). Any task: a loose plant has no barrel on any fort."""
        if not isinstance(self.day, (int, float)) or not self.loose_hist or self.loose_hist[-1][0] != self.day:
            return 0
        old = [h for h in self.loose_hist if self.day - h[0] >= LOOSE_BREW_DAYS]
        if not old:
            return 0
        span = [h for h in self.loose_hist if h[0] >= old[-1][0]]
        return max(0, min(n for _, n in span))


    def plot_tiles(self):
        """(tiles, sown) over the built farm plots that give their size: w*h, and seeds_or_crops_in_plot."""
        tiles = sown = 0
        for p in lst(self.o.get("farm_plots")):
            p = d(p)
            w, h = p.get("w"), p.get("h")
            if p.get("built") is False or not all(isinstance(v, int) and not isinstance(v, bool) for v in (w, h)):
                continue
            tiles += w * h
            n = p.get("seeds_or_crops_in_plot")
            sown += n if isinstance(n, int) and not isinstance(n, bool) else 0
        return tiles, sown

    def recycle_kind_ok(self, name, left):
        """A kind autofarm would plant once its seed is back: known seasons, in season when the seed is sown
        (RECYCLE_LEAD_DAYS from now) and when the crop ripens (its grow days later, autofarm's is_plantable), and
        ripe before the run ends."""
        seasons = self.kind_seasons.get(name)
        if not isinstance(seasons, list) or left is None:
            return False
        grow = RECYCLE_GROW_DAYS.get(name, RECYCLE_GROW_DEFAULT)
        if left < grow + RECYCLE_LEAD_DAYS:
            return False
        doy = self.game_doy()
        name_at = lambda t: SEASON_NAMES[((doy + t) % YEAR_DAYS) // SEASON_DAYS]
        return name_at(RECYCLE_LEAD_DAYS) in seasons and name_at(RECYCLE_LEAD_DAYS + grow) in seasons

    def regrow_cap(self):
        """cx regrow lend (MY1-3 records, cx{7c43df4,ba93eee,c44c96b,9444f41,68bd4c7}-hint-*: the plant budget of the
        year is the seed lineage - cave wheat ~5 and pig tail ~5-6 seeds, a sown tile coming back as one plant, the
        lineage flat at 10-12 all year while 27-54 plot tiles stood - times the cycles each seed runs before its sow
        window closes; pig tail already ran ~28-day cycles, 25 days' growth). Inside the harvest-closed hold a
        brewable plant of a kind still sowable (recycle_kind_ok) whose crop ripens RECYCLE_LEAD_DAYS + its growth +
        F's length before the end is lent, not spent: brewed now it is 5 drinks and a seed, sown it is back as a plant
        before F. A brew order takes any brewable plant, so the lend is open only while every standing brewable kind
        is such a kind; it is bounded by the unsown tiles less the free seeds autofarm can already sow. 0 otherwise
        (and outside the MY1 plan)."""
        if not self.my1_plan() or not self.hold_active():
            return 0
        left = self.days_to_end()
        if left is None:
            return 0
        tiles, sown = self.plot_tiles()
        if tiles <= sown:
            return 0
        pbk = d(self.st.get("plants_by_kind"))
        standing = {k: int(d(v).get("n") or 0) for k, v in pbk.items() if d(v).get("brewable") and (d(v).get("n") or 0) > 0}
        if not standing:
            return 0
        f = self.f_len()
        for k in standing:
            grow = RECYCLE_GROW_DAYS.get(k, RECYCLE_GROW_DEFAULT)
            if not self.recycle_kind_ok(k, left) or left < grow + RECYCLE_LEAD_DAYS + f:
                return 0
        seeds = d(self.live_seeds_by_kind())
        sowable = sum(int(d(v).get("n") or 0) for k, v in seeds.items()
                      if self.recycle_kind_ok(k, left) and standing.get(k, 0) < AUTOFARM_THRESHOLD)
        free = max(0, sowable - sown)
        return max(0, min(sum(standing.values()), min(self.pb_free(), sum(standing.values())), tiles - sown - free))

    def seed_recycle(self):
        """cx: the seed recycle (RECYCLE_* above). Open play (alloc_on), outside F, not while the caravan's goods
        stand in the stocks or the harvest-closed hold keeps the plants for F's drink: the unsown plot tiles less the
        free seeds autofarm can sow (seeds of a plantable kind under AUTOFARM_THRESHOLD standing plants, less the
        seeds already in the plots) are brewed back out of the standing brewable plants of plantable kinds, down to
        RECYCLE_KEEP (the plant floor while drink is the shorter leg and the food-lean is off), while edible food stays above RECYCLE_FOOD_DAYS of the fort's use, and a kind at the
        autofarm threshold is brewed under it. One-shot brew_drink (no `when`); a short barrel stock draws a barrel
        one-shot from the spare logs. Inside F the recycle's own unfinished brews are cancelled: a plant still
        counts as food there and its seed could not ripen in F's slope."""
        self.seed_wait = 0
        if not self.alloc_on() or not isinstance(self.day, (int, float)):
            return
        left = self.days_to_end()
        if left is None:
            return
        pending = [x for x in self.orders if x.get("id") in self.recycle_brews and (x.get("left") or 0) > 0]
        if left <= self.f_len():
            for x in pending:
                r = self.act("recycle_cancel_%s" % x.get("id"), "cancel_order", {"order_id": x.get("id")},
                             retry=2, limit=3)
                if r is not None and r.get("ok"):
                    log("seed_recycle_cancel", day=self.day, order=x.get("id"), left=x.get("left"))
            return
        held = self.hold_active()
        if held and self.regrow_cap() < 1:
            return






        caravan = self.caravan_active and not held
        if self.caravan_active and held:
            return
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        if "Still" not in have:
            return
        tiles, sown = self.plot_tiles()
        if tiles <= 0:
            return
        plants = {k: int(d(v).get("n") or 0) for k, v in d(self.st.get("plants_by_kind")).items()}
        merchant = d(self.merchant_plants) if caravan else {}
        if merchant:


            plants = {k: max(0, n - merchant.get(k, 0)) for k, n in plants.items()}
        seeds = d(self.live_seeds_by_kind())
        if caravan:
            seeds = {k: dict(d(v), n=min(int(d(v).get("n") or 0), self.own_seeds[k])) for k, v in seeds.items()
                     if k in self.own_seeds}
            seeds.update({k: {"n": 0} for k in self.own_seeds if k not in seeds})
        ok = {k for k in set(plants) | set(self.kind_seasons) if self.recycle_kind_ok(k, left)}
        sowable = sum(int(d(v).get("n") or 0) for k, v in seeds.items()
                      if k in ok and plants.get(k, 0) < AUTOFARM_THRESHOLD)
        free = max(0, sowable - sown)
        need = (tiles - sown) - free
        if need < RECYCLE_MIN_EMPTY:
            return
        brewable = {k: n for k, n in plants.items()
                    if k in ok and d(d(self.st.get("plants_by_kind")).get(k)).get("brewable") and n > 0}
        if not brewable:
            return
        over = sum(max(0, n - (AUTOFARM_THRESHOLD - 1)) for n in brewable.values())
        slope = self.food_slope()
        rate = max(FOOD_PER_CIT_DAY * max(1, self.cit or 0), -slope if slope is not None else 0.0)
        food = self.st.get("food_edible") or 0
        if caravan and isinstance(self.own_food, (int, float)):
            food = min(food, self.own_food)
        headroom = int(food - RECYCLE_FOOD_DAYS * rate)
        barrels = self.st.get("barrels_empty") or 0
        on_book = sum(max(0, x.get("left") or 0) for x in pending)


        dd, fd = self.leg_days()
        keep = RECYCLE_KEEP * len(brewable) if self.food_lean() or dd >= fd else max(RECYCLE_KEEP, self.plant_floor())
        if held:
            keep = 0


        queued = self.brew_queued()
        reach = min(sum(brewable.values()), self.pb_free() - sum(merchant.values())) - (queued - on_book)
        want = min(need + over, reach - keep, headroom) - on_book
        if held:
            want = min(want, self.regrow_cap() - on_book)
        n = min(want, barrels - queued, RECYCLE_MAX)
        bcap = self.barrel_brew_cap()
        if bcap is not None:
            n = min(n, bcap)
        self.seed_wait = max(0, min(want, RECYCLE_MAX) - max(0, n))
        if want >= 1 and barrels - queued < want and "Carpenters" in have\
                and not self.own_pending("o_barrel_seed"):
            spare = self.logs() - self.logs_guard()
            b = min(10, want - max(0, barrels - queued), spare)
            if b >= 1:
                self.act("o_barrel_seed", "add_order", {"recipe": "make_barrel", "amount": b}, retry=2, limit=99)
        if n < 1:
            return
        r = self.act("o_brew_seed", "add_order", {"recipe": "brew_drink", "amount": n}, retry=1, limit=99)
        oid = d(d(r).get("result")).get("order_id") if r and r.get("ok") else None
        if oid is not None:
            self.recycle_brews.add(oid)
            log("seed_recycle", day=self.day, amount=n, tiles=tiles, sown=sown, free=free, need=need, over=over,
                kinds=sorted(brewable), keep=keep, headroom=headroom, barrels=barrels, on_book=on_book, left=left)



    def food_slope(self):
        """OLS slope of edible food over the tracked days (units per day), or None with too few days."""
        pts = [(r[0], r[1]) for r in self.food_hist
               if isinstance(r[0], (int, float)) and isinstance(r[1], (int, float))]
        if len(pts) < 3:
            return None
        n = len(pts)
        mean_x = sum(x for x, _ in pts) / n
        mean_y = sum(y for _, y in pts) / n
        var = sum((x - mean_x) ** 2 for x, _ in pts)
        if var <= 0:
            return None
        return sum((x - mean_x) * (y - mean_y) for x, y in pts) / var

    def food_cover(self):
        """T: days of edible food left at the tracked drain rate (food / -slope), or None when not draining."""
        s = self.food_slope()
        if s is None or s >= 0:
            return None
        return (self.st.get("food_edible") or 0) / -s

    def food_alarm(self):
        """True while edible food is draining toward starvation inside FOOD_ALARM_DAYS (180-day runs and up).
        Held off while the caravan settles (ROOT_CAUSES §X): the merchants' goods inflate both the stock and the
        departure's apparent drop."""
        if self.days < 180 or self.caravan_settling():
            return False
        cover = self.food_cover()
        return cover is not None and cover < FOOD_ALARM_DAYS

    def food_security(self):
        """Food-security stages. The pseudo-production OP1 run lost an Administrator to starvation on day 85 with
        the pantry at zero (food_min 0, final 2): cooking stalls once plants run out, and nothing replaces the
        food. While edible food is draining below FOOD_ALARM_DAYS of cover, (a) fire the butcher outside the
        endgame, and (c) keep cooking past the usual meal cap with the plants condition dropped, so meat and fish
        still become meals (building a Fishery for the fisher-less case lives in workshops). Every stage reuses
        the regular steps, their gates and their retry control."""
        cover = self.food_cover()
        drink_days, food_days = self.leg_days()








        drink_short = drink_days < min(food_days, ALLOC_SHORT_DAYS)
        oid = self.key_order.get("o_cook_food")
        mine_on_book = oid is not None and oid in self.owned and any(x.get("id") == oid for x in self.orders)
        if mine_on_book:
            cur = next(x for x in self.orders if x.get("id") == oid)
            floored = any(k == ("PLANT", "DRINK_MAT") and t == "AtLeast" for k, t, _ in when_sig(cur.get("when")))
            if floored != drink_short and "when" in cur:
                r = self.act("o_cook_food_retire", "cancel_order", {"order_id": oid}, retry=4, limit=8)
                if r is not None and r.get("ok"):
                    log("cook_food_recut", day=self.day, order=oid, floored=floored, drink_short=drink_short,
                        drink_days=round(drink_days), food_days=round(food_days))
                    self.done.discard("o_cook_food")
                    return
        if cover is None or cover >= FOOD_ALARM_DAYS:


            oid = self.key_order.get("o_cook_food")
            if cover is not None and oid is not None and oid in self.owned and any(
                    x.get("id") == oid for x in self.orders):
                self.act("o_cook_food_retire", "cancel_order", {"order_id": oid}, retry=4, limit=8)
                self.done.discard("o_cook_food")
            return
        if self.may("food_butcher", 1, 40):
            self.last["food_butcher"] = self.now
            self.butcher()
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}







        mine = self.key_order.get("o_cook_food")
        if mine is not None and any(x.get("id") == mine for x in self.orders):
            return
        if "Kitchen" in have and not self.ordered_now("o_cook_food") and not any(
                x.get("recipe") == "cook_meal" and x.get("repeat") and x.get("active") is not False
                and not any(d(w).get("stock") == "plants_total"
                            or str(d(w).get("item_type") or "").upper() == "SEEDS" for w in lst(x.get("when")))
                for x in self.orders):
            when = [{"stock": "prepared_meals", "below": max(MEAL_CAP, 3 * self.cit)}]
            if drink_short:
                when.append({"stock": "plants_brewable", "at_least": self.hold_floor()})
            if self.hands_off is not None:



                tool, args = self.cook_order(when)
                self.cook_act("o_cook_food", tool, args, retry=2, limit=10)
            else:
                self.act("o_cook_food", "add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily",
                                                      "when": when}, retry=2, limit=10)

    def perishable(self):
        """Edible food that rots uncooked: food_edible less prepared meals and standing plants (meat, fish, fruit). 0
        when the observation lacks any of the three (an unread part is not taken for meat)."""
        s = self.st
        vals = [s.get(k) for k in ("food_edible", "prepared_meals", "plants_total")]
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
            return 0
        return vals[0] - vals[1] - vals[2]

    def lineage_spare(self):
        """cx: a plant the kitchen takes costs no harvest: no seed floor any more (seed_floor 0: nothing planted now
        ripens in the run), or the free seeds (seeds less those sown in the plots — seeds_by_kind and seeds count
        both) already fill every unsown plot tile with a plot's worth to spare. The seeds total alone is not enough:
        the fresh OP1 fort reads seeds 55-60 at d24-41 with 50 of them in the plots and 4-10 free."""
        left = self.days_to_end()
        if (left is not None and left <= HOLD_GROW_DAYS) or self.harvest_closed():
            return True
        tiles, sown = self.plot_tiles()
        seeds = self.st.get("seeds")
        if not isinstance(seeds, (int, float)) or isinstance(seeds, bool) or tiles <= 0:
            return False
        return seeds - sown >= max(0, tiles - sown) + SEEDS_PER_PLOT

    def meat_keep(self):
        """cx: the meat keep (MEAT_KEEP_* above). Open play (alloc_on), a Kitchen, not while the merchants' goods
        stand in the stocks (their meat is not the fort's and cannot be cooked): a perishable stock of MEAT_KEEP_MIN
        and up draws a one-shot cook batch sized to it, one batch on the book at a time. The kitchen may take plants
        too (a cooked plant hands no seed back): seedwatch keeps a kind under SEEDWATCH_TARGET seeds out of the kitchen,
        so while any kind sits at or over it the batch waits for a spare lineage (lineage_spare) and for the
        harvest-closed hold to leave the kitchen free (the fresh OP1 fort: plump helmet seeds 35 at d40, its first
        harvest coming in — a batch then would cook it)."""
        if not self.alloc_on() or self.caravan_active or not isinstance(self.day, (int, float)):
            return
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        if "Kitchen" not in have:
            return
        meat = self.perishable()
        if meat < MEAT_KEEP_MIN or self.own_pending("o_cook_meat"):
            return
        if self.meal_wait():
            log("meal_wait", day=self.day, source="o_cook_meat", perishable=meat, loose=d(self.plant_loose).get("loose"))
            return
        plants = self.st.get("plants_total") or 0
        cookable = [k for k, v in self.live_seeds_by_kind().items() if int(d(v).get("n") or 0) >= SEEDWATCH_TARGET]
        if cookable and (self.hold_cook() or not self.lineage_spare()):
            return
        n = min(MEAT_KEEP_MAX, max(1, meat // MEAT_KEEP_PER_JOB))
        r = self.act("o_cook_meat", "add_order", {"recipe": "cook_meal", "amount": n}, retry=1, limit=99)
        if r is not None and r.get("ok"):
            log("meat_keep", day=self.day, amount=n, perishable=meat, meals=self.st.get("prepared_meals"),
                plants=plants, seeds=self.st.get("seeds"))



    def stock_sliding(self):
        """A stock is draining toward the horizon when its fitted slope over the record is negative and
        stock / -slope < SLOPE_HORIZON (the score's projection: full credit only if the stock lasts 336 days).
        Either drink or food (the score's min, its food_edible) may trip it. Open-play tasks only: a lab task's
        window_supply is the sole manager of a hands-off run, so the alarm stays off when hands_off is set."""
        if self.days < 180 or self.hands_off is not None or len(self.stock_hist) < SLOPE_MIN_PTS:
            return False
        drink = ols_slope([(p[0], p[1]) for p in self.stock_hist])
        food = ols_slope([(p[0], p[2]) for p in self.stock_hist])
        now = self.stock_hist[-1]
        hit = ((drink < 0 and now[1] / -drink < SLOPE_HORIZON)
               or (food < 0 and now[2] / -food < SLOPE_HORIZON))
        if self.caravan_settling():
            hit = False
        if hit != self.sliding:
            log("slide_alarm", on=hit, day=self.day, days_left=self.days_left, slope_drink=round(drink, 4),
                slope_food=round(food, 4), drink=now[1], food=now[2], meals=now[3])
            self.sliding = hit
        return hit


    def plan(self):


        for f in (self.safe_state, self.stranded_survey, self.home_call_alert, self.mood, self.defend, self.wildlife_response, self.mark_guard,
                  self.squad_hold, self.shaft_hatch, self.entrance_hatches, self.office_guard):
            try:
                f()
            except (ActionLimit, HandsOff, GameOver):
                raise
            except Exception as e:
                log("guard_step_error", step=f.__name__, error=repr(e)[:300])
        self.management()
        self.workshops()
        self.digging()
        self.carp_pause_step()
        self.farms()
        self.seed_census()
        self.plant_census()
        self.seed_guard()
        self.brew_shot_trim()
        self.supply()
        self.surge_start_brew()
        self.allocate_plants()
        self.rot_guard()
        self.seed_recycle()
        self.hold_supply()
        self.barrel_cancel()
        self.lean_supply()
        self.f_drink_lift()
        self.food_security()
        self.f_livestock()
        self.meat_keep()
        self.glut_bank()
        self.winter_plan()
        self.furnish()
        self.cup_supply()
        self.meeting_area()
        self.meeting_far()
        self.meeting_use()
        self.grazer_cull()
        self.stray_cull()
        self.stress_watch()
        self.stress_housing()
        self.house_everyone()
        self.patient_water()
        self.head_offices()
        self.rezone()
        self.progress()
        self.closer()

    def management(self):
        if not self.adm.get("manager_active_for_orders"):
            free = [p for p in self.people if not p.get("positions") and p.get("adult", True)]
            free.sort(key=lambda p: -(p.get("organizer_skill") or 0))
            self.act("manager", "appoint_manager", {"dwarf_id": free[0]["id"]} if free else {}, retry=1, limit=8)
        plugins = d(self.o.get("plugins"))
        for name in ("autochop", "seedwatch"):
            if plugins.get(name) != "on":
                self.act("plug_" + name, "enable_automation", {"name": name}, retry=5)
        if self.o.get("farm_plots") and plugins.get("autofarm") != "on":
            self.act("plug_autofarm", "enable_automation", {"name": "autofarm"}, retry=5)
        self.office()

    def office(self):
        """DF stops validating orders around 20 citizens unless the manager has an office with a chair."""
        if self.office_yield is not None:



            if self.office_shelter():
                self.office_yield = None
                return
            self.office_yield_move()
            return
        if not self.cit or not self.adm.get("manager_active_for_orders"):
            return
        small = self.cit < OFFICE_FULL_CIT
        if small and not self.my1_plan():
            return
        mo = self.adm.get("manager_office")
        mgr = self.adm.get("MANAGER_id")
        if self.office_release(mgr):
            return
        if self.office_shelter():
            return
        offices = self.zone("office")
        mine = next((z for z in offices if mgr is not None and z.get("owner") == mgr), None)
        if isinstance(mo, dict) and mo.get("chair"):
            if mine is not None and (not small or self.dug_rooms("office")):
                self.office_move(mine, mgr)
            return
        if not mine:



            spare = next((z for z in offices if z.get("owner") is None and z.get("id") not in self.head_zones), None)
            if spare and mgr is not None:
                if self.office_beasts(spare):
                    return
                self.act("office_assign", "assign_zone", {"zone_id": spare["id"], "dwarf_id": mgr})
                return





            spare_dine = self.dug_rooms("dine") if self.zone("dining") else []
            closed = [s for s in self.closed_a() if self.area_fits(s, ZONE_MAX) and not self.site_open(s)]
            if small:
                closed = [s for s in closed if self.site_open(s) == 0]
            if small and self.shaft_people():

                closed.sort(key=lambda s: bool(self.shaft_near(self.site_box(s, ZONE_MAX))))
            room = next(iter(self.dug_rooms("office") + closed + spare_dine), None)
            if room:
                result = self.act("office_zone", "make_zone", {"kind": "office", "site": room["id"]})
                if result and result.get("ok") and (self.free.get("chair") or 0) > 0:
                    self.act("office_chair", "place_furniture", {"kind": "chair", "site": room["id"]})



                zid = d(d(result).get("result")).get("zone_id") if result and result.get("ok") else None
                if zid is not None and mgr is not None:



                    at = lst(d(d(result).get("result")).get("at"))
                    box = dict(zip(("x", "y", "z", "w", "h"), at)) if len(at) >= 5 else\
                        {k: room.get(k) for k in ("x", "y", "z", "w", "h")}
                    if not self.office_beasts(box):
                        self.act("office_assign", "assign_zone", {"zone_id": zid, "dwarf_id": mgr})
            elif not small and self.office_temp_small(mgr):
                pass
            else:
                self.office_box(ready_only=small)
            return
        if (not small or self.dug_rooms("office")) and self.office_move(mine, mgr):
            return
        if d(mine.get("furniture")).get("chair") or d(mine.get("furniture_planned")).get("chair"):
            return
        if (self.free.get("chair") or 0) > 0:
            room = next((s for s in self.sites if s.get("kind") in "RA" and s.get("z") == mine.get("z")
                         and s.get("x") == mine.get("x") and s.get("y") == mine.get("y")
                         and self.area_fits(s, PLACE_MAX)), None)
            room = room or next(iter(self.dug_rooms("office")
                                     + [s for s in self.closed_a() if self.area_fits(s, PLACE_MAX)]), None)
            if room:


                temp = not small and room.get("kind") == "A" and bool(self.site_open(room))
                self.act("office_temp_chair" if temp else "office_chair", "place_furniture",
                         {"kind": "chair", "site": room["id"]})

    def shelter_office_rooms(self):
        """cx lt082beds: the Shelter's closed boxes an office can take — added to the Shelter (shelter_boxes) not as a
        level-open box (shelter_level_in), the site still listed, its level read closed (level_open 0), within
        place_furniture's gate, not tried before. [(site, (x1, y1, x2, y2, z))]."""
        out = []
        for sid, b in sorted(self.shelter_boxes.items(), key=lambda kv: str(kv[0])):
            if sid in self.shelter_level_in or sid in self.office_shelter_tried\
                    or not (isinstance(b, tuple) and len(b) == 5):
                continue
            s = next((x for x in self.sites if isinstance(x, dict) and x.get("id") == sid), None)
            if s is None or s.get("kind") not in ("A", "R") or (s.get("x"), s.get("y"), s.get("z")) != (b[0], b[1], b[4]):
                continue
            w, h = b[2] - b[0] + 1, b[3] - b[1] + 1
            if not (1 <= w <= PLACE_MAX and 1 <= h <= PLACE_MAX):
                continue
            if self.level_open((b[0], b[1], b[4], w, h)) != 0:
                continue
            out.append((s, b))
        return out

    def in_shelter_box(self, zone):
        """cx lt082beds: an office zone's corner tile lies inside a closed Shelter box (not a level-open one)."""
        if not self._ints(zone, ("x", "y", "z")):
            return False
        return any(isinstance(b, tuple) and len(b) == 5 and sid not in self.shelter_level_in and b[4] == zone["z"]
                   and b[0] <= zone["x"] <= b[2] and b[1] <= zone["y"] <= b[3]
                   for sid, b in self.shelter_boxes.items())

    def office_shelter(self):
        """cx lt082beds (hint hard LT08-2 on 7be81c2: 128.75; beds 41/47, drink 464 < 488): the manager validates
        work orders only at his office, on DF's own round (~8.4-10 days: 13.96 / 22.36 / 30.76 / 39.98 there). The
        office stood on the open A1 corner, outside the Shelter (R1, the one closed room), and every round but the
        last fell inside an alligator alert or an office yield — d5.6 yielded, d13.96 "Manage work orders: Need
        office." (alert on), d22.36 nothing (alert on) — so all 11 orders (40 beds, barrels, hatch covers, brews)
        waited to d31 and 18 beds were made too late to place. 17dad3a (150) had its office inside the Shelter and
        validated at d7 under the alert. So once the Shelter holds a closed room, the manager's office goes there:
        a free chair placed in the room's box (the tool takes the first free floor tile from its corner — before the
        beds, which furnish() places later in the pass), an office zone from the corner over that tile (never over a
        built bed or other furniture), assigned to the manager in the same pass unless a big beast is near it, and
        the manager's other offices handed to a citizen without a position. Alerts, the yield and its return are
        unchanged. Fort size as office() (OFFICE_FULL_CIT, or a MY1 plan). True when it acted."""
        mgr = self.adm.get("MANAGER_id")
        if mgr is None or not self.adm.get("manager_active_for_orders") or not self.cit:
            return False
        if self.cit < OFFICE_FULL_CIT and not self.my1_plan():
            return False
        owned = [z for z in self.zone("office") if z.get("owner") == mgr and z.get("id") is not None]
        if any(self.in_shelter_box(z) for z in owned):
            return False
        if (self.free.get("chair") or 0) <= 0:
            return False
        rooms = [(s, b) for s, b in self.shelter_office_rooms()
                 if not self.office_beasts({"x": b[0], "y": b[1], "z": b[4], "w": b[2] - b[0] + 1, "h": b[3] - b[1] + 1})]
        if not rooms:
            return False
        s, b = rooms[0]
        x1, y1, z = b[0], b[1], b[4]
        built = [d(f) for f in lst(self.o.get("furniture")) if d(f).get("built") is not False]
        if any(f.get("x") == x1 and f.get("y") == y1 and f.get("z") == z for f in built):
            self.office_shelter_tried.add(s["id"])
            log("office_shelter_skip", day=self.day, site=s["id"], why="corner_taken")
            return False
        self.office_shelter_tried.add(s["id"])
        r = self.act("office_shelter_chair", "place_furniture",
                     {"kind": "chair", "site": s["id"], "w": b[2] - x1 + 1, "h": b[3] - y1 + 1}, retry=1, limit=4)
        at = d(r.get("result")).get("at") if r and r.get("ok") else None
        if isinstance(at, list) and at and isinstance(at[0], list):
            at = at[0]
        if not (isinstance(at, list) and len(at) == 3 and all(isinstance(v, int) and not isinstance(v, bool)
                                                               for v in at)):
            return r is not None
        w, h = at[0] - x1 + 1, at[1] - y1 + 1
        inside = lambda f: x1 <= (f.get("x") if isinstance(f.get("x"), int) else -1) <= at[0]\
            and y1 <= (f.get("y") if isinstance(f.get("y"), int) else -1) <= at[1] and f.get("z") == z
        if not (1 <= w <= ZONE_MAX and 1 <= h <= ZONE_MAX) or at[2] != z or any(inside(f) for f in built):
            log("office_shelter_skip", day=self.day, site=s["id"], why="chair_far", at=at)
            return True
        zr = self.act("office_shelter_zone", "make_zone", {"kind": "office", "site": s["id"], "w": w, "h": h},
                      retry=1, limit=4)
        zid = d(d(zr).get("result")).get("zone_id") if zr and zr.get("ok") else None
        if zid is None:
            return True
        a = self.act("office_shelter_assign", "assign_zone", {"zone_id": zid, "dwarf_id": mgr}, retry=0.25, limit=10)
        ok = bool(a and a.get("ok"))
        log("office_shelter", day=self.day, site=s["id"], zone=zid, at=at, w=w, h=h, ok=ok,
            old=[z.get("id") for z in owned])
        if ok:
            holder = self.office_holder(mgr)
            for z in owned:
                if holder is not None and z.get("id") != zid:
                    rr = self.act("office_release_%s" % z["id"], "assign_zone",
                                  {"zone_id": z["id"], "dwarf_id": holder}, retry=1, limit=6)
                    log("office_release", day=self.day, zone=z["id"], holder=holder, manager=mgr,
                        ok=bool(rr and rr.get("ok")))
        return True

    def office_temp_small(self, mgr):
        """cx audit (642f253's promise, "order validation is never blocked"): with no closed place, no dug office room
        and no A / dug site wider than ZONE_MAX for office_box, an open A site that fits make_zone's gate takes the
        temporary office as it did before 941b64a (zone, chair, the manager in the same pass unless a big beast is near
        its box); office_room digs the closed room and office_move moves it there. Without this a fort whose open A
        sites all fit ZONE_MAX read manager_office "none" until the office room was dug (and, before its first dorm
        room, never). True when it acted."""
        wide = [x for x in self.kind("A") + self.dug_rooms()
                if not self.area_fits(x, ZONE_MAX) and self.area_fits(x, PLACE_MAX)]
        if wide:
            return False
        site = next((x for x in self.kind("A") if self.area_fits(x, ZONE_MAX) and self.site_open(x)), None)
        if site is None:
            return False
        self.office_room()
        r = self.act("office_temp_zone", "make_zone", {"kind": "office", "site": site["id"]}, retry=2, limit=4)
        if not (r and r.get("ok")):
            return r is not None
        if self.may("office_temp_log", 5, 10 ** 6):
            self.last["office_temp_log"] = self.now
            log("office_temp", day=self.day, site=site["id"], small=True)
        if (self.free.get("chair") or 0) > 0:
            self.act("office_temp_chair", "place_furniture", {"kind": "chair", "site": site["id"]})
        zid = d(d(r).get("result")).get("zone_id")
        if zid is not None and mgr is not None:
            at = lst(d(d(r).get("result")).get("at"))
            box = dict(zip(("x", "y", "z", "w", "h"), at)) if len(at) >= 5 else\
                {k: site.get(k) for k in ("x", "y", "z", "w", "h")}
            if not self.office_beasts(box):
                self.act("office_assign", "assign_zone", {"zone_id": zid, "dwarf_id": mgr})
        return True

    def call_box(self, args):
        """cx closed sites: the box a site tool call covers — the listed site's corner with the call's w/h, else the
        site's own extent; None for an unlisted site or one without coordinates."""
        sid = args.get("site")
        s = next((x for x in getattr(self, "sites", None) or [] if isinstance(x, dict) and x.get("id") == sid), None)
        num = lambda v: isinstance(v, int) and not isinstance(v, bool)
        if s is None or not all(num(s.get(k)) for k in ("x", "y", "z")):
            return None
        w = args.get("w") if num(args.get("w")) else (s.get("w") if num(s.get("w")) else 1)
        h = args.get("h") if num(args.get("h")) else (s.get("h") if num(s.get("h")) else 1)
        return (s["x"], s["y"], s["z"], max(1, w), max(1, h))

    def box_open(self, box):
        """cx closed sites: the walkable outside tiles (OPEN_WALK shapes, map light "o") inside box (x, y, z, w, h)
        from one map query, cached OPEN_PROBE_DAYS; None when unread (no box, a failed query, no reading)."""
        if box is None:
            return None
        today = self.obs_day()
        hit = self.open_maps.get(box)
        if hit is not None and isinstance(today, (int, float)) and isinstance(hit[0], (int, float))\
                and today - hit[0] < OPEN_PROBE_DAYS:
            return hit[1]
        x0, y0, z, w, h = box
        n = None
        try:
            r = self.game.query("map", x=min(400, max(0, x0 + (w - 1) // 2)), y=min(400, max(0, y0 + (h - 1) // 2)),
                                z=z, z2=z, radius=min(20, max(w, h) // 2 + 1))
            res = query_result(r)
        except Exception as e:
            log("box_open_error", box=list(box), error=repr(e)[:160])
            res = None
        if isinstance(res, dict) and isinstance(res.get("x1"), int) and isinstance(res.get("y1"), int):
            lv = next((d(v) for v in lst(res.get("levels")) if d(v).get("z") == z), None)
            if lv is not None and isinstance(lv.get("shape"), list) and isinstance(lv.get("light"), list):
                n = 0
                for i, (row, lrow) in enumerate(zip(lv["shape"], lv["light"])):
                    ty = res["y1"] + i
                    if not (y0 <= ty < y0 + h) or not isinstance(row, str) or not isinstance(lrow, str):
                        continue
                    for j, (ch, li) in enumerate(zip(row, lrow)):
                        if x0 <= res["x1"] + j < x0 + w and ch in OPEN_WALK and li == "o":
                            n += 1
        self.open_maps[box] = (today, n)
        return n

    def site_open(self, s, args=None):
        """cx closed sites: walkable outside tiles in a site's box (its corner with args' w/h, or its extent)."""
        if not isinstance(s, dict) or s.get("id") is None:
            return None
        return self.box_open(self.call_box(dict(d(args), site=s["id"])))

    def beasts_near(self, zone, tiles, levels):
        """The marked DANGER_BIG units within `tiles` (x/y, to the box) and `levels` of a box {x, y, z, w, h}."""
        return [u for u in self.office_beasts(zone, ((tiles, levels),))]

    def office_beasts(self, zone, rules=None):
        """cx office yield: the marked DANGER_BIG units near an office zone's box (OFFICE_BEAST_* above), each as
        (race, x, y, z, tiles). A zone without a position counts nothing."""
        rules = rules or ((OFFICE_BEAST_TILES, WILD_NEAR_Z), (OFFICE_BEAST_LEVEL_TILES, 1))
        num = lambda v: isinstance(v, int) and not isinstance(v, bool)
        if not all(num(zone.get(k)) for k in ("x", "y", "z")):
            return []
        x1, y1, oz = zone["x"], zone["y"], zone["z"]
        x2 = x1 + max(1, zone["w"] if num(zone.get("w")) else 1) - 1
        y2 = y1 + max(1, zone["h"] if num(zone.get("h")) else 1) - 1
        out = []
        for u in self.others():
            if not big_race(u.get("race")) or not self.mark_of(u) or not all(num(u.get(k)) for k in ("x", "y", "z")):
                continue
            tiles = max(x1 - u["x"], u["x"] - x2, y1 - u["y"], u["y"] - y2, 0)
            dz = abs(u["z"] - oz)
            if any(tiles <= t and dz <= lv for t, lv in rules):
                out.append((str(u.get("race")), u["x"], u["y"], u["z"], tiles))
        return out

    def office_holder(self, mgr):
        """cx office yield: a citizen who never goes to an office — an adult with no position, not the manager."""
        for p in sorted(self.people, key=lambda p: p.get("id") if isinstance(p.get("id"), int) else 10 ** 9):
            if isinstance(p.get("id"), int) and p["id"] != mgr and not p.get("positions") and p.get("adult", True):
                return p["id"]
        return None

    def office_guard(self):
        """cx office yield (OFFICE_* above): while a marked big beast is near the manager's office, the office is
        owned by a citizen without a position; once none has been near for OFFICE_CLEAR_DAYS it goes back to the
        manager. office() makes and assigns nothing while it is yielded."""
        mgr = self.adm.get("MANAGER_id")
        y = self.office_yield
        if y is not None:
            zone = next((z for z in self.zone("office") if z.get("id") == y["zone"]), None)
            if zone is None:
                log("office_yield_end", day=self.day, zone=y["zone"], why="zone_gone")
                self.office_yield = None
                return
            near = self.office_beasts(zone)
            if near:
                y["clear"] = None
                if zone.get("owner") == mgr and mgr is not None:
                    holder = self.office_holder(mgr)
                    if holder is not None:
                        r = self.act("office_yield", "assign_zone", {"zone_id": zone["id"], "dwarf_id": holder},
                                     retry=0.25, limit=10 ** 6)
                        if r and r.get("ok"):
                            y["holder"] = holder
                            log("office_yield", day=self.day, zone=zone["id"], holder=holder, near=near[:3],
                                again=True)
                return
            if y.get("clear") is None:
                y["clear"] = self.now
            if self.now - y["clear"] < OFFICE_CLEAR_DAYS * DAY:
                return
            if mgr is None:
                return
            r = self.act("office_return", "assign_zone", {"zone_id": zone["id"], "dwarf_id": mgr},
                         retry=0.25, limit=10 ** 6)
            if r and r.get("ok"):
                log("office_return", day=self.day, zone=zone["id"], manager=mgr,
                    days=round((self.now - y["since"]) / DAY, 2))
                self.office_yield = None
            return
        if mgr is None:
            return
        zone = next((z for z in self.zone("office") if z.get("owner") == mgr), None)
        if zone is None:
            return
        near = self.office_beasts(zone)
        if not near:
            return
        holder = self.office_holder(mgr)
        if holder is None:
            if self.may("office_yield_none", 1, 10 ** 6):
                self.last["office_yield_none"] = self.now
                log("office_yield_none", day=self.day, zone=zone.get("id"), near=near[:3])
            return
        r = self.act("office_yield", "assign_zone", {"zone_id": zone["id"], "dwarf_id": holder},
                     retry=0.25, limit=10 ** 6)
        if r and r.get("ok"):
            self.office_yield = {"zone": zone["id"], "holder": holder, "since": self.now, "clear": None}
            log("office_yield", day=self.day, zone=zone["id"], holder=holder, manager=mgr, near=near[:3])

    def office_open(self, zone):
        """cx office valid: the office zone's box holds a walkable outside tile (None unread). cx lt082beds: or its
        level runs out onto open ground (level_open, the Shelter's own enclosed rule) — hint hard LT08-2 on 7be81c2:
        the temporary office was the 1x1 A1 corner (83,67,104), a roofed tile ("i") 1-2 tiles from the open floor
        where the alligators stood (81,68 on d15); the box read 0, so office_move never moved it and office_release
        never released it. An unread level keeps the box's answer."""
        if not self._ints(zone, ("x", "y", "z")):
            return None
        box = (zone["x"], zone["y"], zone["z"], zone.get("w") or 1, zone.get("h") or 1)
        n = self.box_open(box)
        if n:
            return n
        lv = self.level_open(box)
        return lv if lv else n

    def office_on_room(self, zone):
        """cx lt082beds: an office zone's corner lies on a dug office-role room (its dug box, else its site box) —
        office_move's own destination, which office_open may now read level-open (LT08-2's R2 opens onto the ramps)."""
        if not self._ints(zone, ("x", "y", "z")):
            return False
        for r in self.kind("R"):
            if self.roles.get(r.get("id")) != "office" or not self._ints(r, ("x", "y", "z")):
                continue
            b = self.room_box.get(r["id"])
            b = b if isinstance(b, dict) and self._ints(b, ("x", "y", "z")) else r
            if b["z"] == zone["z"] and b["x"] <= zone["x"] < b["x"] + (b.get("w") or 3)\
                    and b["y"] <= zone["y"] < b["y"] + (b.get("h") or 3):
                return True
        return False

    def office_settled(self, zone):
        """cx lt082beds: an office that stays put — read closed (box and level), or on the dug office room."""
        return self.office_open(zone) == 0 or self.office_on_room(zone)

    def office_move(self, mine, mgr):
        """cx office valid: the manager's office on open ground moves into a dug office room once one stands — an
        office zone on the room, assigned to the manager, a chair from the free stock. True when it acted."""
        if mgr is None or not self.office_open(mine) or self.office_on_room(mine):
            return False
        room = next(iter(self.dug_rooms("office")), None)
        if room is None:
            self.office_room()
            return False
        if OFFICE_CHAIR_FIRST and (self.free.get("chair") or 0) <= 0 and not self.room_chair(room):

            if self.may("office_move_wait_log", 2, 10 ** 6):
                self.last["office_move_wait_log"] = self.now
                log("office_move_wait", day=self.day, site=room["id"], old=mine.get("id"), why="no_chair")
            return False
        r = self.act("office_move_zone", "make_zone", {"kind": "office", "site": room["id"]}, retry=2, limit=4)
        zid = d(r.get("result")).get("zone_id") if r and r.get("ok") else None
        if zid is None:
            return r is not None
        a = self.act("office_move_assign", "assign_zone", {"zone_id": zid, "dwarf_id": mgr}, retry=0.5, limit=6)
        if (self.free.get("chair") or 0) > 0:
            c = self.act("office_move_chair", "place_furniture", {"kind": "chair", "site": room["id"]}, retry=2, limit=4)
            if c and c.get("ok"):
                self.office_chair_zones = getattr(self, "office_chair_zones", set()) | {zid}
        elif self.room_chair(room):
            self.office_chair_zones = getattr(self, "office_chair_zones", set()) | {zid}
        log("office_move", day=self.day, site=room["id"], zone=zid, old=mine.get("id"), ok=bool(a and a.get("ok")))
        if a and a.get("ok"):


            self.office_release(mgr)
        return True

    def office_yield_move(self):
        """cx audit (HEAD replay of std LT08-2: the yielded open-ground office stayed yielded d3-d9 while alligators
        came and went within 15 tiles — no manager office, no order validated for 6 days; office() waited even with a
        closed place ready): while the office is yielded and the manager owns none, a dug office room, else an A site
        read closed, with no big beast near its box takes a new office zone for the manager (and a free chair). The
        yield ends there: the yielded open zone stays its holder's. True when it acted."""
        mgr = self.adm.get("MANAGER_id")
        if mgr is None or not self.adm.get("manager_active_for_orders") or self.zone_of("office", mgr) is not None:
            return False
        cands = self.dug_rooms("office") + [s_ for s_ in self.closed_a() if self.area_fits(s_, ZONE_MAX)
                                            and self.site_open(s_) == 0]


        room = next((s_ for s_ in cands if self._ints(s_, ("x", "y", "z")) and not self.site_level_open(s_)
                     and not self.office_beasts({k: s_.get(k) for k in ("x", "y", "z", "w", "h")})), None)
        if room is None:
            return False
        r = self.act("office_yield_zone", "make_zone", {"kind": "office", "site": room["id"]}, retry=1, limit=6)
        zid = d(d(r).get("result")).get("zone_id") if r and r.get("ok") else None
        if zid is None:
            return r is not None
        a = self.act("office_yield_assign", "assign_zone", {"zone_id": zid, "dwarf_id": mgr}, retry=0.25, limit=10)
        if (self.free.get("chair") or 0) > 0:
            self.act("office_yield_chair", "place_furniture", {"kind": "chair", "site": room["id"]}, retry=1, limit=6)
        ok = bool(a and a.get("ok"))
        log("office_yield_move", day=self.day, site=room["id"], zone=zid, old=(self.office_yield or {}).get("zone"),
            ok=ok)
        if ok:
            self.office_yield = None
        return True

    def office_release(self, mgr):
        """cx audit (office_move left the manager owning the old open-ground office too; the game reports and uses
        the first one — std LT08-2 on 642f253: all 7 ManageWorkOrders looks stood on the temporary office's tile on
        open A1): once the manager owns an office on closed ground, every other office the manager owns that holds a
        walkable outside tile is handed to a citizen who never goes to an office (office_holder). True when it acted."""
        if mgr is None:
            return False
        owned = [z for z in self.zone("office") if z.get("owner") == mgr and z.get("id") is not None]
        if len(owned) < 2 or not any(self.office_settled(z) for z in owned):
            return False
        if OFFICE_CHAIR_FIRST and not any(self.office_settled(z) and self.office_chaired(z) for z in owned)\
                and any(self.office_chaired(z) for z in owned):

            if self.may("office_release_hold_log", 2, 10 ** 6):
                self.last["office_release_hold_log"] = self.now
                log("office_release_hold", day=self.day, owned=[z.get("id") for z in owned], why="no_chair")
            return False
        holder = self.office_holder(mgr)
        acted = False
        for z in owned:
            if self.office_settled(z) or not self.office_open(z) or holder is None:
                continue
            r = self.act("office_release_%s" % z["id"], "assign_zone", {"zone_id": z["id"], "dwarf_id": holder},
                         retry=1, limit=6)
            if r is not None:
                acted = True
                log("office_release", day=self.day, zone=z["id"], holder=holder, manager=mgr, ok=bool(r.get("ok")))
        return acted

    def office_chaired(self, zone):
        """cx office chair first: an office zone whose box holds a chair (built or planned), or one office_move gave a
        chair this run (the same-pass copy of the new zone carries no furniture yet)."""
        return bool(d(d(zone).get("furniture")).get("chair") or d(d(zone).get("furniture_planned")).get("chair")
                    or d(zone).get("id") in getattr(self, "office_chair_zones", ()))

    def room_chair(self, room):
        """cx office chair first: a built chair stands inside the room's dug box (else its site box)."""
        b = self.room_box.get(room.get("id"))
        b = b if isinstance(b, dict) and self._ints(b, ("x", "y", "z")) else room
        if not self._ints(b, ("x", "y", "z")):
            return False
        w, h = b.get("w") or 3, b.get("h") or 3
        return any(d(f).get("kind") == "chair" and d(f).get("built") is not False and d(f).get("z") == b["z"]
                   and isinstance(d(f).get("x"), int) and isinstance(d(f).get("y"), int)
                   and b["x"] <= d(f)["x"] < b["x"] + w and b["y"] <= d(f)["y"] < b["y"] + h
                   for f in lst(self.o.get("furniture")))

    def office_wants_room(self):
        """cx office valid: the manager's office has no closed place — none, or one on open ground — and no office
        room is dug or designated yet."""
        if "office" in self.roles.values() or (self.cit or 0) < OFFICE_FULL_CIT\
                or not self.adm.get("manager_active_for_orders"):
            return False
        mgr = self.adm.get("MANAGER_id")
        mine = next((z for z in self.zone("office") if mgr is not None and z.get("owner") == mgr), None)
        if mine is not None and self.office_settled(mine):
            return False
        if self.shelter_office_rooms():
            return False
        return not self.dug_rooms("office") and not any(self.site_open(a) == 0 and self.area_fits(a, ZONE_MAX)
                                                         for a in self.kind("A"))

    def office_room(self):
        """cx closed sites: the manager's office has no closed place (every A site wide enough is open ground, no dug
        office room): once a dorm room is dug, the next listed undug R site is dug for it (role office), as a SURGE_FLOOR_ROOM box in a surge
        so the beds keep the floor (surge_bed_sites takes an office room too). office() zones it once it is dug."""
        if "office" in self.roles.values() or "dorm" not in self.roles.values():
            return
        spare = [r for r in self.undug_rooms() if r["id"] not in self.roles and self.dry(r.get("z"))
                 and not self.room_taken(r)]
        r = self.pick_dig_site(spare) if spare else None
        if r is None:
            return
        size = {"w": SURGE_FLOOR_ROOM[0], "h": SURGE_FLOOR_ROOM[1]} if self.surge else {}
        res = self.act("dig_office_room", "dig_room", {"site": r["id"], **size}, retry=2, limit=4)
        if res and res.get("ok"):
            self.roles[r["id"]] = "office"
            self.note_room_box(r, size)
            log("office_room", day=self.day, site=r["id"], **size)

    def open_refusal(self, tool, args):
        """cx closed fallback: the model's own calls get the layer's closed-site rules (plain.harness refuse): a
        Shelter / zone / furniture box over outside floor, or a surface stair dig with a big beast near. A reason
        text, or None; any surprise answers None (the model's call goes on)."""
        try:
            args = d(args)
            sid = str(args.get("site") or "")
            if tool in OPEN_SITE_TOOLS and sid[:1] in (("A", "R") if tool == "create_burrow" else ("A",)):
                n = self.box_open(self.call_box({"site": args["site"]} if sid[:1] == "A" else args))
                if n:
                    return "site %s holds %d walkable outside tile(s) (open ground, no roof): no Shelter, zone or " \
                           "furniture goes there; use a dug room" % (sid, n)
            if tool == "dig_stairs" and sid[:1] == "S":



                why = self.entrance_hold()
                if why:
                    return why
                box = self.call_box({"site": args.get("site"), "w": 1, "h": 1})
                near = self.beasts_near(dict(zip(("x", "y", "z", "w", "h"), box)), WILD_NEAR_TILES, WILD_NEAR_Z)\
                    if box else []
                if near:
                    return "a big beast (%s) is within %d tiles of stair site %s on the surface" % (
                        near[0][0].lower(), WILD_NEAR_TILES, sid)
        except Exception as e:
            log("open_refusal_error", error=repr(e)[:160])
        return None

    def closed_a(self):
        """cx closed fallback: the A sites whose box holds no walkable outside tile (unread boxes kept); cx enclosed:
        the ones whose level reaches no outdoor tile first, the level-open ones after (never nothing)."""
        inside = [x for x in self.kind("A") if not self.site_open(x)]
        shut = [x for x in inside if not self.site_level_open(x)]
        rest = [x for x in inside if x not in shut]
        if rest and not shut and self.may("people_level_log", 1, 10 ** 6):
            self.last["people_level_log"] = self.now
            log("people_level_fallback", day=self.day, sites=[x.get("id") for x in rest][:6])
        return shut + rest

    def site_level_open(self, s, wh=None):
        """cx enclosed: the site's box (its extent, or wh) reaches an outdoor walkable tile on its own level."""
        if not self._ints(s, ("x", "y", "z")):
            return None
        w, h = wh if wh else (s.get("w") or 1, s.get("h") or 1)
        return self.level_open((s["x"], s["y"], s["z"], w, h))

    def level_open(self, box):
        """cx enclosed (LEVEL_* above): 1 when a flood over walkable tiles from the box on its own level reaches an
        outdoor tile, 0 when it closes inside the reading, None unread (no reading, or the flood ran off the read
        window without finding one). Cached OPEN_PROBE_DAYS."""
        today = self.obs_day()
        hit = self.level_maps.get(box)
        if hit is not None and isinstance(today, (int, float)) and isinstance(hit[0], (int, float))\
                and today - hit[0] < OPEN_PROBE_DAYS:
            return hit[1]
        x0, y0, z, w, h = box
        out = None
        try:
            res = query_result(self.game.query("map", x=min(400, max(0, x0 + (w - 1) // 2)),
                                               y=min(400, max(0, y0 + (h - 1) // 2)), z=z, z2=z, radius=LEVEL_RADIUS))
        except Exception as e:
            log("level_open_error", box=list(box), error=repr(e)[:160])
            res = None
        if isinstance(res, dict) and isinstance(res.get("x1"), int) and isinstance(res.get("y1"), int):
            lv = next((d(v) for v in lst(res.get("levels")) if d(v).get("z") == z), None)
            if lv is not None and isinstance(lv.get("shape"), list) and isinstance(lv.get("light"), list):
                rows, lights, x1, y1 = lv["shape"], lv["light"], res["x1"], res["y1"]
                stop = set()
                for b in lst(res.get("buildings")):
                    b = d(b)
                    if str(b.get("type")) in ("Door", "Hatch") and self._ints(b, ("x1", "y1")):
                        for bx in range(b["x1"], (b.get("x2") if isinstance(b.get("x2"), int) else b["x1"]) + 1):
                            for by in range(b["y1"], (b.get("y2") if isinstance(b.get("y2"), int) else b["y1"]) + 1):
                                stop.add((bx, by))

                def cell(x, y):
                    i, j = y - y1, x - x1
                    if 0 <= i < len(rows) and 0 <= i < len(lights) and isinstance(rows[i], str)\
                            and isinstance(lights[i], str) and 0 <= j < len(rows[i]) and j < len(lights[i]):
                        return rows[i][j], lights[i][j]
                    return None
                start = [(x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + h)
                         if (cell(x, y) or ("#", ""))[0] in LEVEL_WALK and (x, y) not in stop]
                seen, todo, edge, found = set(start), list(start), False, False
                while todo and not found:
                    x, y = todo.pop()
                    c = cell(x, y)
                    if c[1] == "o":
                        found = True
                        break
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            n = (x + dx, y + dy)
                            if n in seen or n in stop:
                                continue
                            cn = cell(*n)
                            if cn is None:
                                edge = True
                                continue
                            if cn[0] in LEVEL_WALK:
                                seen.add(n)
                                todo.append(n)
                out = 1 if found else (None if edge or not start else 0)
        self.level_maps[box] = (today, out)
        return out

    def shelter_box_of(self, s):
        """cx enclosed: the box a Shelter add covers (an R room as dug, an A site's extent)."""
        wh = self.box_wh(s, SHELTER_SIDE_MAX) if s.get("kind") == "R" else {}
        return (s.get("x"), s.get("y"), s.get("z"), wh.get("w", s.get("w") or 1), wh.get("h", s.get("h") or 1))

    def open_a(self):
        """cx closed fallback: some listed A site is open ground (the reason a people zone may lack a place)."""
        return any(self.site_open(x) for x in self.kind("A"))

    def people_room(self, role):
        """cx closed fallback: dig the next listed undug R site for `role` (meeting / dine / house) when an open A
        site left it without a closed place: after the first dorm room, one room per role (house: SHELTER_ROOMS_MAX
        pending at a time), SURGE_FLOOR_ROOM in a surge or for a house room, else the site's 3x3."""
        if "dorm" not in self.roles.values():
            return None
        if role != "house" and role in self.roles.values():
            return None
        if role == "house" and any(self.roles.get(r["id"]) == "house" and not r.get("dug") for r in self.kind("R")):
            return None
        spare = [r for r in self.undug_rooms() if r["id"] not in self.roles and self.dry(r.get("z"))
                 and not self.room_taken(r)]
        r = self.pick_dig_site(spare) if spare else None
        if r is None:
            return None
        size = {"w": SURGE_FLOOR_ROOM[0], "h": SURGE_FLOOR_ROOM[1]} if (self.surge or role == "house") else {}
        res = self.act("dig_%s_room" % role, "dig_room", {"site": r["id"], **size}, retry=2, limit=6)
        if res and res.get("ok"):
            self.roles[r["id"]] = role
            self.note_room_box(r, size)
            log("people_room", day=self.day, role=role, site=r["id"], **size)
            return r
        return None

    def shelter_tiles(self):
        """cx closed fallback: tiles in the Shelter's boxes (shelter_boxes, as added)."""
        return sum((b[2] - b[0] + 1) * (b[3] - b[1] + 1) for b in self.shelter_boxes.values()
                   if isinstance(b, tuple) and len(b) == 5)

    def shelter_room(self, pending):
        """cx closed fallback: a Shelter built of closed rooms (an A box was skipped as open) grows with the census —
        under SHELTER_TILES_PER_CIT tiles a citizen, a spare listed R site is dug as a house room."""
        if self.breach or not any(isinstance(k, tuple) and k[0] in ("open", "level") for k in self.shelter_skip):
            return
        if not isinstance(pending, int) or isinstance(pending, bool)\
                or pending >= SURGE_FLOOR_ROOM[0] * SURGE_FLOOR_ROOM[1] // 2:
            return
        have, want = self.shelter_tiles(), SHELTER_TILES_PER_CIT * (self.cit or 0)
        if have >= want:
            return
        if self.may("shelter_short_log", 2, 10 ** 6):
            self.last["shelter_short_log"] = self.now
            log("shelter_short", day=self.day, tiles=have, want=want, cit=self.cit)


        if self.people_room("house") is None and self.shaft is None\
                and not any(self.roles.get(r["id"]) == "house" and not r.get("dug") for r in self.kind("R"))\
                and not any(r["id"] not in self.roles for r in self.undug_rooms()):
            self.shelter_shaft()

    def entrance_hold(self):
        """cx entrances: why the model may dig no new surface stair now (None: it may) — 642f253's rule: ENTRANCE_MAX
        entrances already, or no free hatch cover beyond the hatchless entrances' own."""
        if len(self.entrances) >= ENTRANCE_MAX:
            return "the fort already has %d surface entrances (at most %d); use the existing stairs" % (
                len(self.entrances), ENTRANCE_MAX)
        if self.hatch_free_spare() < 1:
            return "no free hatch cover is in hand for a new surface stair (the open entrances need theirs first); " \
                   "the layer keeps covers on order"
        return None

    def hatch_free_spare(self):
        """cx shelter shaft: free hatch covers beyond the hatchable entrances still waiting for one."""
        doors = d(self.o.get("doors"))
        free = doors.get("hatch_cover_items_free")
        if not isinstance(free, int) or isinstance(free, bool):
            return 0
        at = {(x.get("x"), x.get("y"), x.get("z")) for x in map(d, lst(doors.get("list"))) if x.get("kind") == "hatch"}
        blocked = {d(x).get("id") for x in self.kind("E") if d(x).get("building")} | self.entrance_occupied
        waiting = [sid for sid, p in sorted(self.entrances.items(), key=lambda kv: site_key(kv[0]))
                   if p not in at and sid not in blocked]
        return free - len(waiting)

    def column_rock(self, s, z_low, z_high):
        """cx shelter shaft: the S site's column is rock (shape # or hidden) on levels z_low..z_high — None unread."""
        try:
            res = query_result(self.game.query("map", x=s["x"], y=s["y"], z=z_high, z2=z_low, radius=0))
        except Exception as e:
            log("column_rock_error", error=repr(e)[:160])
            return None
        if not isinstance(res, dict) or not isinstance(res.get("x1"), int):
            return None
        seen = {}
        for lv in lst(res.get("levels")):
            lv = d(lv)
            rows = lv.get("shape") if isinstance(lv.get("shape"), list) else []
            i, j = s["y"] - res["y1"], s["x"] - res["x1"]
            if 0 <= i < len(rows) and isinstance(rows[i], str) and 0 <= j < len(rows[i]):
                seen[lv.get("z")] = rows[i][j]
        if any(z not in seen for z in range(z_low, z_high + 1)):
            return None
        return all(seen[z] in "#?" for z in range(z_low, z_high + 1))

    def people_gap(self, s):
        """cx shelter shaft: x/y tiles from site s to the nearest meeting, dining or dormitory zone box."""
        best = None
        for z in self.zones:
            if not any(k in str(z.get("type")).lower() for k in ("meeting", "dining", "dormitory")):
                continue
            if not self._ints(z, ("x", "y", "w", "h")):
                continue
            g = max(z["x"] - s["x"], s["x"] - (z["x"] + z["w"] - 1), z["y"] - s["y"], s["y"] - (z["y"] + z["h"] - 1), 0)
            best = g if best is None else min(best, g)
        return 10 ** 6 if best is None else best

    def shelter_shaft(self, why="shelter"):
        """cx shelter shaft (SHAFT_* above): one new stair from a surface S site, its hatch cover reserved first.
        `why`: "shelter" (a short closed-room Shelter) or "seats" (cx seat shaft: house_floor)."""
        if self.shaft_stop or self.shaft is not None or self.surface is None or self.breach:
            return
        if len(self.entrances) + 1 > ENTRANCE_MAX:
            return
        if self.hatch_free_spare() < 1:
            return
        zs = [a.get("z") for a in self.kind("A") if self.dry(a.get("z")) and isinstance(a.get("z"), int)]
        if not zs:
            return
        zb = min(zs) - 1
        cands = [x for x in self.kind("S") if self._ints(x, ("x", "y", "z")) and 0 < x["z"] - zb <= 20
                 and self.people_gap(x) >= SHAFT_PEOPLE_GAP]
        cands = [x for x in cands if self.column_rock(x, zb + 1, x["z"] - 1)]
        site = self.pick_dig_site(cands, levels=2) if cands else None
        if site is None:
            return
        res = self.act("stairs_shelter", "dig_stairs", {"site": site["id"], "z_bottom": zb},
                       retry=SURGE_FLOOR_STAIR_DAYS, limit=6)
        if res and res.get("ok"):
            self.shaft = {"site": site["id"], "x": site["x"], "y": site["y"], "z": site["z"], "day": self.day,
                          "e": None, "listed": None, "sent": None}
            log("shelter_shaft", day=self.day, why=why, site=site["id"], z_bottom=zb, tiles=self.shelter_tiles(),
                gap=self.people_gap(site), spare_covers=self.hatch_free_spare())

    def shaft_hatch(self):
        """cx shelter shaft: hatch the shaft's top on the pass its E site lists (alert or not); a refusal stops new
        shafts; a built hatch ends the shaft (its open days logged)."""
        sh = self.shaft
        if sh is None:
            return
        e = next((x for x in self.kind("E") if x.get("x") == sh["x"] and x.get("y") == sh["y"]
                  and x.get("z") == sh["z"]), None)
        if e is None and sh.get("e") is None:
            return
        if e is not None:
            sh["e"] = e.get("id")
        if sh.get("listed") is None:
            sh["listed"] = self.day
            log("shaft_entrance", day=self.day, site=sh["e"], at=[sh["x"], sh["y"], sh["z"]])
        doors = d(self.o.get("doors"))
        hatch = next((x for x in map(d, lst(doors.get("list"))) if x.get("kind") == "hatch"
                      and (x.get("x"), x.get("y"), x.get("z")) == (sh["x"], sh["y"], sh["z"])), None)
        if hatch is not None and hatch.get("built", True):
            days = round((self.day or 0) - (sh["listed"] or 0), 2) if isinstance(self.day, (int, float)) else None
            self.shaft_open_days.append(days)
            log("shaft_hatched", day=self.day, site=sh["e"], open_days=days)
            self.shaft = None
            return
        if hatch is not None:
            return
        if d(self.o.get("burrows")).get("civilian_alert") is True and not self.hatch_safe((sh["x"], sh["y"], sh["z"])):


            if self.may("shaft_hatch_hold_log", 1, 10 ** 6):
                self.last["shaft_hatch_hold_log"] = self.now
                log("shaft_hatch_hold", day=self.day, site=sh["e"])
            return
        r = self.act("shaft_hatch_" + str(sh["e"]), "build_door", {"kind": "hatch", "site": sh["e"]},
                     retry=0.25, limit=SHAFT_HATCH_TRIES)
        if r is None:
            return
        if r.get("ok"):
            sh["sent"] = self.day
            log("shaft_hatch", day=self.day, site=sh["e"])
            return
        self.shaft_stop = True
        self.shaft = None
        log("shaft_stop", day=self.day, site=sh["e"], code=r.get("error_code"), err=str(r.get("error") or "")[:120])

    def office_box(self, ready_only=False):
        """cx office box: no dug office room and no A site under make_zone's ZONE_MAX — the manager's office is
        carved out of a wider A / dug R site: one free chair placed inside the site's first ZONE_MAX x ZONE_MAX box
        (place_furniture's site + w/h; the tool picks a free roofed floor tile from the site's corner), then an office
        zone from the site's corner over that chair's tile (make_zone's site + w/h: a zone box always starts at the
        site's own x, y — the API requires `site`, raw coordinates answer "args.site is required": probe fdprb
        LT08-2 on fe1831a). office() assigns the spare zone on a later pass. Hint hard LT08-2 on c44c96b: A1 was the
        fort's only site (15x40), the manager's required office stood "none" days 0-21 and no work order validated
        until day 30 (beds 19 the whole time; 29 ordered on day 0), so 41 beds were made on days 30-39 and the fort
        ended 47 placed / 48 citizens; the model's own make_zone office on A1 answered "w must be an integer in
        [1,20]" 31 times."""
        if self.office_tile is None:
            cands = [s for s in self.kind("A") + self.dug_rooms()
                     if not self.area_fits(s, ZONE_MAX) and self.area_fits(s, PLACE_MAX)
                     and all(isinstance(s.get(k), int) and not isinstance(s.get(k), bool) for k in ("x", "y"))]


            ok = (lambda s: self.site_open(s) == 0) if ready_only\
                else (lambda s: s.get("kind") != "A" or not self.site_open(s))
            room = next((s for s in cands if ok(s)), None)
            if room is None:
                if ready_only:
                    return
                self.office_room()

                room = next(iter(cands), None)
                if room is None:
                    return
                if self.may("office_temp_log", 5, 10 ** 6):
                    self.last["office_temp_log"] = self.now
                    log("office_temp", day=self.day, site=room["id"])
            if (self.free.get("chair") or 0) <= 0:
                return
            box = {"kind": "chair", "site": room["id"], "w": min(ZONE_MAX, room.get("w") or 1),
                   "h": min(ZONE_MAX, room.get("h") or 1)}
            r = self.act("office_box_chair", "place_furniture", box, retry=2, limit=4)
            at = d(r.get("result")).get("at") if r and r.get("ok") else None
            if isinstance(at, list) and at and isinstance(at[0], list):
                at = at[0]
            if not (isinstance(at, list) and len(at) == 3 and all(isinstance(v, int) and not isinstance(v, bool)
                                                                   for v in at)):
                return
            w, h = at[0] - room["x"] + 1, at[1] - room["y"] + 1
            if not (1 <= w <= ZONE_MAX and 1 <= h <= ZONE_MAX):
                log("office_box_far", day=self.day, site=room["id"], at=at)
                return
            self.office_tile = (room["id"], w, h)
            log("office_box", day=self.day, site=room["id"], at=at, w=w, h=h)
        sid, w, h = self.office_tile
        if ready_only and any(x.get("id") == sid and x.get("kind") == "A" and self.site_open(x)
                              for x in self.kind("A")):
            return
        r = self.act("office_box_zone", "make_zone", {"kind": "office", "site": sid, "w": w, "h": h},
                     retry=2, limit=4)
        if r and r.get("ok"):
            self.done.add("office_box_zone")

    def frame_on(self, site):
        """True while an unbuilt workshop frame stands inside the site's box (ROOT_CAUSES §E): a suspended
        construction keeps its W site, so the rebuild goes to the next one."""
        x, y, z = site.get("x"), site.get("y"), site.get("z")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (x, y, z)):
            return False
        for w in lst(self.o.get("workshops")):
            w = d(w)
            if w.get("built") or w.get("z") != z:
                continue
            wx, wy = w.get("x"), w.get("y")
            if isinstance(wx, (int, float)) and isinstance(wy, (int, float))\
                    and not isinstance(wx, bool) and not isinstance(wy, bool)\
                    and x <= wx < x + (site.get("w") or 1) and y <= wy < y + (site.get("h") or 1):
                return True
        return False

    def harvest_bench_wanted(self, shops):
        """cx harvest press: another Carpenters past PRESS_CARPENTERS pays only when the benches, not the hands, bind
        the barrels — every standing Carpenters holds a MakeBarrel job, a citizen stood idle on each of the last two
        observed days, and HARVEST_CARP_SPARE_LOGS logs stand over logs_guard()."""
        carps = [w for w in shops if w.get("type") == "Carpenters" and not self.shop_stale(w)]
        if not carps or self.logs() - self.logs_guard() < HARVEST_CARP_SPARE_LOGS:
            return False
        for w in carps:
            jobs = [str(d(j).get("job")) for j in lst(w.get("job_details"))] + [str(j) for j in lst(w.get("jobs"))]
            if not any(j.startswith("MakeBarrel") for j in jobs):
                return False
        return len(self.idle_days) >= 2 and all(n >= 1 for _, n in self.idle_days)

    def build(self, wtype, retry=3, key=None):
        sites = [s for s in self.kind("W") if not self.frame_on(s)]
        if not sites:

            sites = [s for s in self.remembered("W") if not self.shop_clash(s)]
        if wtype == "Butchers":
            sites = [s for s in sites if not self.dead_site(s)]
        if not sites or not self.material():
            return
        result = self.act(key or ("ws_" + wtype), "build_workshop", dict(self.site_args(sites[0]), type=wtype),
                          retry=retry)
        if result and result.get("ok") and not sites[0].get("_mem"):
            self.sites.remove(sites[0])
        self.mem_used(sites[0], result)

    def workshops(self):
        """Types the fort can work with, built or still under construction. A construction whose frame has stood
        suspended across two observed days (shop_stale, ROOT_CAUSES §E) is treated as absent: the type is rebuilt
        on the next W site, paced to one attempt per REBUILD_GAP_DAYS per type."""
        shops = [w for w in lst(self.o.get("workshops")) if isinstance(w, dict)]
        have = {w.get("type") for w in shops if not self.shop_stale(w)}
        stale = {w.get("type") for w in shops if self.shop_stale(w)}
        for t in ("Carpenters", "Still", "Kitchen"):
            if t not in have:
                if t not in stale:
                    self.done.discard("ws_" + t)
                self.build(t, key="ws_rebuild_" + str(t) if t in stale else None,
                           retry=REBUILD_GAP_DAYS if t in stale else 3)



        if self.hands_off is None and "Still" in have:
            stills = sum(1 for w in shops if w.get("type") == "Still" and not self.shop_stale(w))
            backlog = sum((x.get("left") or 0) for x in self.orders
                          if x.get("recipe") == "brew_drink" and not x.get("repeat") and x.get("active") is not False)
            if stills < STILL_MAX and (backlog >= STILL_BACKLOG or self.rot_seen) and self.logs() >= 4:
                self.build("Still", key="ws_Still_%d" % (stills + 1), retry=3)
            self.kitchen_backlog(shops)
            carp = sum(1 for w in shops if w.get("type") == "Carpenters" and not self.shop_stale(w))


            if carp == 1 and (backlog >= STILL_BACKLOG or self.rot_seen
                              or self.harvest_barrels_short() >= HARVEST_CARP_SHORT) and self.logs() >= 4\
                    and not self.surge:
                self.build("Carpenters", key="ws_Carpenters_2", retry=3)
            elif self.barrel_press() and 1 <= carp < PRESS_CARPENTERS and self.logs() >= 4 and not self.surge:
                self.build("Carpenters", key="ws_Carpenters_%d" % (carp + 1), retry=3)
            elif self.barrel_press() and self.press_harv and PRESS_CARPENTERS <= carp < HARVEST_CARPENTERS\
                    and not self.surge and self.harvest_bench_wanted(shops):
                self.build("Carpenters", key="ws_Carpenters_%d" % (carp + 1), retry=3)
        if "Fishery" not in have and (self.food_alarm()
                                      or any(p.get("job") == "Fish" for p in self.people)):
            self.build("Fishery", key="ws_rebuild_Fishery" if "Fishery" in stale else None,
                       retry=REBUILD_GAP_DAYS if "Fishery" in stale else 3)

    def kitchen_backlog(self, shops):
        """cx KITCHEN BACKLOG (above): full-year open play, a Kitchen standing, fewer than KITCHEN_MAX, and at least
        KITCHEN_BACKLOG one-shot cook jobs on the book while this fort's plants rot (rot_seen) or age (aged_plants):
        another Kitchen, so the queued batches cook beside the daily standing before the plants rot."""
        if self.hands_off is not None or (getattr(self, "days", 0) or 0) < 336 or getattr(self, "surge", False):
            return False
        kitchens = sum(1 for w in shops if w.get("type") == "Kitchen" and not self.shop_stale(w))
        if not 1 <= kitchens < KITCHEN_MAX or self.logs() < 4:
            return False
        backlog = sum(max(0, x.get("left") or 0) for x in self.orders
                      if x.get("recipe") == "cook_meal" and not x.get("repeat"))
        if backlog < KITCHEN_BACKLOG or not (self.rot_seen or self.aged_plants() >= 1):
            return False
        key = "ws_Kitchen_%d" % (kitchens + 1)
        if key not in self.done:
            log("kitchen_backlog", day=self.day, kitchens=kitchens, backlog=backlog, rot_seen=self.rot_seen,
                aged=self.aged_plants(), rotten=self.st.get("plants_rotten"), pb=self.st.get("plants_brewable"))
        self.build("Kitchen", key=key, retry=3)
        return True

    def bed_target(self):
        """Beds per citizen is read at the horizon; a migrant task's wave is bigger than the fort's bed stock, and a
        full-year run's spring wave (sized by the wealth reported to the autumn caravan) can land in the horizon's
        last fortnight — the stock carries a margin for it (FULL_YEAR_BEDS)."""
        if self.surge:
            return self.surge_pop() + SURGE_BED_MARGIN
        return self.cit + (FULL_YEAR_BEDS if self.days >= 336 else 3)

    def surge_pop(self):
        """The census a surge fort's beds are sized to: the census itself, or — before the first wave has shown, early
        in the run — SURGE_FIRST_WAVE times the run's starting census (the task's text says a large wave is coming;
        the order book is validated only every ~10 days, so the wave's beds must be on it before the wave lands)."""
        cit = self.cit if isinstance(self.cit, (int, float)) and not isinstance(self.cit, bool) else 0
        start = self.mig_start
        if self.mig_waves == 0 and isinstance(start, (int, float)) and cit <= start\
                and isinstance(self.day, (int, float)) and self.day <= SURGE_WAVE_WAIT_DAYS:
            return max(cit, int(math.ceil(SURGE_FIRST_WAVE * start)))
        return cit

    def surge_beds_short(self):
        """A surge fort whose beds (items, or placed against the census) still fall short: the Carpenters are the
        beds' (no table or chair orders of this layer; more benches)."""
        return self.surge and ((self.st.get("beds") or 0) < self.bed_target()
                               or (self.placed.get("bed") or 0) < (self.cit or 0))

    def surge_bed_orders(self, have, want):
        """The surge's bed book: the beds on hand plus every one-shot make_bed still left (validated or not) are
        topped up to bed_target at once — two orders of up to 30 per pass. pending() alone froze the book at the
        pre-wave order (LT08 bed supply above)."""
        queued = sum(max(0, x.get("left") or 0) for x in self.orders
                     if x.get("recipe") == "make_bed" and not x.get("repeat"))
        gap = min(want - have - queued, self.logs())
        for key in ("o_make_bed", "o_make_bed_2"):
            if gap < 1:
                break
            amount = min(30, gap)
            result = self.act(key, "add_order", {"recipe": "make_bed", "amount": amount}, retry=1, limit=99)
            if not (result and result.get("ok")):
                break
            gap -= amount
            log("surge_bed_book", day=self.day, have=have, queued=queued, want=want, added=amount)

    def farm_target(self):



        pop = self.pop_forecast()
        if self.days >= 336:
            base = max(6, min(12, math.ceil(pop / 3)))





            tiles, sown = self.plot_tiles()
            built = sum(1 for p in lst(self.o.get("farm_plots")) if isinstance(p, dict) and p.get("built") is not False)
            seeds = self.st.get("seeds")
            if tiles > 0 and isinstance(seeds, (int, float)) and not isinstance(seeds, bool)\
                    and seeds - sown >= SEEDS_PER_PLOT + max(0, tiles - sown):
                base = max(base, min(12, built + 1))
            return base
        return max(4, min(10, math.ceil(pop / 5)))

    def pop_forecast(self):
        """cx population forecast (WAVES_* above): the census plus the expected waves still to come — WAVES_EXPECTED
        from the embark, less one already taken by a fort that started above the EMBARK_PARTY, less the waves seen
        this run, each WAVE_MEAN dwarves. Open play only, and none once less than a crop's growth (HOLD_GROW_DAYS)
        is left: a plot added then never feeds anyone in the run. A lab task keeps its census."""
        cit = self.cit if isinstance(self.cit, (int, float)) and not isinstance(self.cit, bool) else 0
        if self.hands_off is not None:
            return cit
        left = self.days_to_end()
        if left is not None and left <= HOLD_GROW_DAYS:
            return cit
        start = self.mig_start if self.mig_start is not None else cit
        prior = 1 if start > EMBARK_PARTY else 0
        waves = max(0, WAVES_EXPECTED - prior - self.mig_waves)
        return int(math.ceil(cit + WAVE_MEAN * waves))

    def pick_dig_site(self, cands, levels=1):
        """The first candidate the water rules let dig (W4water): a halted site waits, and a site that measured wet
        next to water yields while a drier or unmeasured one is left. Measures the first unmeasured candidate while
        the probe budget lasts; with no measurement possible the plain order stands (fail-open, baseline behaviour)."""
        for i, site in enumerate(cands):
            if not self.water_ok(site):
                continue
            if self.water_wetness(site) is None:
                self.water_measure(site, levels)
            if self.water_rank(site) == 2:




                continue
            return site
        return None

    def dig_refusal(self, tool, args):
        """cx (hint OP1-2, river at z162 one level under the surface): the model's own dig_room / dig_stairs passed
        none of the layer's water rules. On cxc44c96b hard the model dug R1 (box y 94-100) on day 2 right under the
        open river rows (y 89-94, RIVER material, depth-7 liquid): deep water stood indoors from day 3 (3 tiles),
        grew to 7 by day 35 and 37 after day 39, the water sign then held the run to 1-day pieces for the rest of
        the game. The same rules as pick_dig_site: no new dig over a contained breach, none at a halted site and
        none whose dig box (grown by WATER_DIG_MARGIN) touches water. The reason text, or None (dig allowed;
        unknown sites and unmeasurable ones fail open like the layer's own order)."""
        if tool not in ("dig_room", "dig_stairs") or not isinstance(args, dict):
            return None
        if self.breach:
            return "a flood breach is contained (water rose after a dig); no new digs until it recedes"
        sid = args.get("site")
        site = next((s for s in getattr(self, "sites", None) or [] if s.get("id") == sid), None)
        if site is None:
            return None
        if not self.water_ok(site):
            return f"site {sid} is halted: water stands at or near it"
        try:
            n = self.water_measure(site, levels=2 if site.get("kind") == "S" else 1)
        except Exception as e:
            log("water_probe_error", site=sid, error=repr(e)[:160])
            return None
        if n:
            return f"site {sid}: {n} water tiles (river, pool or liquid) touch its dig box; digging it lets the water in"
        return None

    def stair_bottom(self):
        """B-1: the stairs' z_bottom is the deepest level of the rooms the fort actually uses (role-assigned or
        dug), one level under the surface before any room is in use — never the baseline's blind surface-4, whose
        unused shaft tapped a perched water pocket (ROOT_CAUSES §B: dev MY1-5 d0 dig_stairs z_bottom 138 on a
        surface of 142, d7 water_rising, the bedroom level z140 flooded). A room designated deeper down extends
        the shaft to it and no further."""
        zs = [r.get("z") for r in self.kind("R")
              if isinstance(r.get("z"), int) and (self.roles.get(r["id"]) or r.get("dug"))]
        if not zs:
            return max(0, self.surface - 1)
        return max(0, min(self.surface, min(zs)))

    def digging(self):
        if self.breach:
            self.contain_flood()
            return
        rooms = self.kind("R")
        pending = self.o.get("dig_designations_pending") or 0
        if self.office_wants_room():
            self.office_room()
        if pending <= 90:
            self.surge_capacity()
            farms = len(lst(self.o.get("farm_plots"))) + sum(1 for r, v in self.roles.items() if v == "farm" and not any(z.get("id") == r and z.get("used_by") for z in self.kind("R")))
            remaining = self.undug_rooms()
            shaft = self.shaft_people()
            if shaft:
                remaining.sort(key=lambda r: self.shaft_near(dict(r, w=r.get("w") or 3, h=r.get("h") or 3)))
            plots_up = self.shaft_plots_held(sum(1 for p in lst(self.o.get("farm_plots"))
                                                 if isinstance(p, dict) and self.dry(p.get("z"))))
            while remaining:
                r = self.pick_dig_site(remaining)
                if r is None:
                    break
                remaining.remove(r)
                rid = r["id"]
                if rid in self.roles:
                    continue
                need = [x for x in ("dorm", "dine", "office") if x not in self.roles.values()]



                people = [x for x in need if x != "office"]
                held = self.bed_held_rooms() if BED_HELD_BOX else []
                house_first = bool(people) and farms + sum(1 for h in held if h.get("used_by")) >= HOUSE_AFTER_FARMS\
                    and (self.house_blocked() or bool(held))\
                    and not self.rush_holds_digs()
                if r.get("soil") and farms < self.farm_target() and not house_first:
                    if shaft and plots_up and self.shaft_dig_waits(r, {}):
                        continue
                    result = self.act("dig_" + rid, "dig_room", {"site": rid}, retry=3, limit=2)
                    if result and result.get("ok"):
                        self.roles[rid] = "farm"
                        farms += 1
                elif need and not self.rush_holds_digs():
                    role = people[0] if house_first else need[0]
                    size = {"dorm": {"w": 9, "h": 7}, "dine": {"w": 7, "h": 5}, "office": {}}[role]
                    if size and self.hands_off is None and self.farm_claimed(dict(r, **size)):








                        continue
                    if shaft and (role == "dine" or (role == "dorm" and self.placed_dry("bed") >= (self.cit or 0)))\
                            and self.shaft_dig_waits(r, size):
                        continue
                    result = self.act("dig_" + rid, "dig_room", {"site": rid, **size}, retry=3, limit=2)
                    if result and result.get("ok"):
                        self.roles[rid] = role
                        self.note_room_box(r, size)
        self.surge_stair(pending)
        self.shelter_room(pending)
        self.house_floor(pending)


        stairs = self.kind("S")
        if stairs and self.surface is not None and (len(rooms) < 2 or (not any(r.get("soil") for r in rooms)
                                                                       and not self.o.get("farm_plots"))):
            stair = self.pick_dig_site(list(reversed(stairs)), levels=2)
            if stair is None and self.water_rank(stairs[-1]) != 2:
                stair = stairs[-1]
            if stair is not None and self.water_ok(stair):


                self.act("stairs", "dig_stairs", {"site": stair["id"], "z_bottom": self.stair_bottom()},
                         retry=2, limit=3)

    def reserved_hit(self, box, kind=""):
        """cx room claim: the bedroom zone (id, owner) a box shares a tile with, unless `kind` is a bedroom's own
        (BEDROOM_OWN_KINDS); None when clear. Only a standing bedroom zone counts — a room merely dug for one yields
        to the far meeting box (people_boxes keeps the bedroom planners off those)."""
        if not isinstance(box, dict) or not self._ints(box, ("x", "y", "z", "w", "h")) or kind in BEDROOM_OWN_KINDS:
            return None
        for z in self.zone("bedroom"):
            if self._ints(z, ("x", "y", "z", "w", "h")) and self.rects_overlap(z, box):
                return z.get("id"), z.get("owner")
        return None

    def people_boxes(self):
        """cx room claim: on a shaft fort, the boxes the meeting and dining pickers hold or would take — the standing
        meeting and dining zones, and every A site's far cut (far_cut off the sleepers, MEETING_SHAFT_TILES off the
        shaft, on mapped floor). The private-bedroom planners keep off them. [] off a shaft fort."""
        if not self.shaft_people():
            return []
        out = [z for z in self.zone("meeting") + self.zone("dining") if self._ints(z, ("x", "y", "z", "w", "h"))]
        beds = [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
                if isinstance(f, dict) and f.get("kind") == "bed" and self._ints(f)]
        sleep = [z for z in self.zones if any(k in str(z.get("type")).lower() for k in ("dormitory", "bedroom"))]
        surface = d(self.o.get("map")).get("surface_z", getattr(self, "surface", None))


        for s_ in self.closed_a():
            if s_.get("id") in self.zone_banned or not self.dry(s_.get("z"))\
                    or (isinstance(surface, (int, float)) and isinstance(s_.get("z"), (int, float))
                        and s_["z"] >= surface):
                continue
            floor = self.site_floor(s_, walk=True)
            if floor is None:
                continue
            cut = self.far_cut(self.site_box(s_, ZONE_MAX), sleep + beds, MEETING_MIN_TILES, floor=floor,
                               placing=False)
            if cut is not None:
                out.append({"x": s_["x"], "y": s_["y"], "z": s_["z"], "w": cut[0], "h": cut[1], "site": s_["id"]})
        return out

    def people_later(self, room):
        """cx room claim: whether an undug R room would fall under a far meeting / dining cut once dug — the dig
        joins the level's A site, whose corner (make_zone's addressing) then moves to the union's top-left (e33d381
        MY1-4: A4 at x97 y91 became A5 at x94 y90 once R3 was dug, and the far cut A5 4x6 took R3). The union box of
        each A site on the room's level and the room, cut by far_cut on geometry alone. False off a shaft fort."""
        if not self.shaft_people() or not self._ints(room, ("x", "y", "z")):
            return False
        rb = {"x": room["x"], "y": room["y"], "z": room["z"], "w": room.get("w") or 3, "h": room.get("h") or 3}
        beds = [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
                if isinstance(f, dict) and f.get("kind") == "bed" and self._ints(f)]
        sleep = [z for z in self.zones if any(k in str(z.get("type")).lower() for k in ("dormitory", "bedroom"))]
        for a in self.closed_a():
            if a.get("z") != rb["z"] or not self._ints(a, ("x", "y", "z", "w", "h")):
                continue
            x1, y1 = min(a["x"], rb["x"]), min(a["y"], rb["y"])
            x2, y2 = max(a["x"] + a["w"], rb["x"] + rb["w"]), max(a["y"] + a["h"], rb["y"] + rb["h"])
            u = {"x": x1, "y": y1, "z": rb["z"], "w": min(ZONE_MAX, x2 - x1), "h": min(ZONE_MAX, y2 - y1)}
            cut = self.far_cut(u, sleep + beds, MEETING_MIN_TILES, placing=False)
            if cut is not None and self.rects_overlap(dict(u, w=cut[0], h=cut[1]), rb):
                return True
        return False

    def under_people(self, box, boxes=None):
        """cx room claim: whether a room / corner box shares a tile with people_boxes()."""
        boxes = self.people_boxes() if boxes is None else boxes
        return any(self.rects_overlap(b, box) for b in boxes)

    def room_reserved(self, tool, args):
        """cx room claim: the reason a make_zone / build_farm / place_furniture call would cover a room dug for a
        private bedroom with something else (its own bedroom zone, bed and noble office pass), or None."""
        if tool not in ("make_zone", "build_farm", "place_furniture") or not isinstance(args, dict):
            return None
        sid = args.get("site")
        site = next((x for x in getattr(self, "sites", None) or [] if x.get("id") == sid), None)
        if site is None:
            return None
        box = self.site_box(site, PLACE_MAX)
        w, h = args.get("w"), args.get("h")
        if isinstance(w, int) and isinstance(h, int) and not isinstance(w, bool) and not isinstance(h, bool):
            box = dict(box, w=w, h=h)
        kind = "farm" if tool == "build_farm" else str(args.get("kind") or "")
        hit = self.reserved_hit(box, kind)
        if hit is None:
            if tool == "build_farm":
                rid = self.dorm_corner_hit(box)
                if rid is not None:
                    return "site %s covers the corner of room %s, the dormitory the beds still wait for (a plot " \
                           "there closes the whole room to beds)" % (sid, rid)
            return None
        return "site %s covers room %s, dug for a private bedroom (%s)" % (sid, hit[0], hit[1])

    def dorm_corner_hit(self, box):
        """cx dorm corner (DORM_CORNER_HOLD above): the id of a dug dorm/house room whose own 3x3 site box a farm plot
        box would cover while the beds are short (placed under the census, a bed free or on order), or None. The API
        marks a room used by a plot only over that 3x3 box, and then answers every place_furniture on the room with
        site_used. Off: the switch, the MY1 plan, drink on hand short of BED_ROOM_DRINK_DAYS."""
        if not DORM_CORNER_HOLD or not self._ints(box, ("x", "y", "z", "w", "h")):
            return None
        try:
            need = self.surge_pop() if getattr(self, "surge", None) else (self.cit or 0)
            if self.placed_dry("bed") >= need\
                    or not ((self.free.get("bed") or 0) > 0 or self.pending("make_bed")) or self.my1_plan()\
                    or (self.st.get("drink") or 0) < self.f_drink_rate(prior_only=True) * BED_ROOM_DRINK_DAYS:
                return None
        except Exception as e:
            log("dorm_corner_error", error=repr(e)[:160])
            return None
        plots = [p for p in lst(self.o.get("farm_plots")) if self._ints(p, ("x", "y", "z", "w", "h"))]
        for r in self.kind("R"):
            if self.roles.get(r.get("id")) not in ("dorm", "house") or not r.get("dug")\
                    or not self._ints(r, ("x", "y", "z")):
                continue
            if any("farm plot" in str(u).lower() for u in lst(r.get("used_by"))) or r.get("id") in self.plot_rooms:
                continue
            corner = {"x": r["x"], "y": r["y"], "z": r["z"], "w": 3, "h": 3}
            if any(self.rects_overlap(corner, p) for p in plots):
                continue
            if self.rects_overlap(corner, box):
                return r.get("id")
        return None

    def dorm_lost(self):
        """cx dorm corner: a dorm-role room a farm plot closed (its used_by names the plot) holds no bed any more —
        surge_bed_sites never knocks on it, so the site_used answer that dropped the role never came (hint std LT08-2
        on b167a15: R2 kept its dorm role from day 10 to H, surge_capacity counted it). The role goes, once logged."""
        for r in self.kind("R"):
            rid = r.get("id")
            if self.roles.get(rid) == "dorm" and any("farm plot" in str(u).lower() for u in lst(r.get("used_by"))):
                self.roles.pop(rid, None)
                log("surge_dorm_lost", day=self.day, site=rid, why="used_by")

    def shaft_refusal(self, tool, args):
        """cx shaft people: the model's own tables/chairs, dining/meeting zones, farm plots and farm/dining-sized room
        digs near an open shaft column, refused while shaft_wait or while a far box exists (probe pdn1, std MY1-4:
        the model put 5 tables and 5 chairs on A2 at x96-106 z167 on days 0-3, past the layer's wait). Beds and a
        dormitory dig pass while beds are short. The reason text, or None."""
        if not isinstance(args, dict) or not self.shaft_people():
            return None
        kind = str(args.get("kind") or "")
        sid = args.get("site")
        site = next((x for x in getattr(self, "sites", None) or [] if x.get("id") == sid), None)
        if site is None:
            return None
        w, h = args.get("w"), args.get("h")
        box = self.site_box(site, PLACE_MAX)
        if isinstance(w, int) and isinstance(h, int) and not isinstance(w, bool) and not isinstance(h, bool):
            box = dict(box, w=w, h=h)
        if not self.shaft_near(box):
            return None
        why = "site %s lies within %d tiles of the open shaft at %s" % (
            sid, MEETING_SHAFT_TILES, ",".join("%d,%d" % c[:2] for c in self.shaft_cols()))
        if (tool == "place_furniture" and kind in ("table", "chair"))\
                or (tool == "make_zone" and kind in ("dining_hall", "meeting_area")):
            if kind != "meeting_area" and any(self.rects_overlap(z, box) for z in self.zone("dining")):
                return None
            beds = [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
                    if isinstance(f, dict) and f.get("kind") == "bed" and self._ints(f)]
            sleep = [z for z in self.zones if any(k in str(z.get("type")).lower() for k in ("dormitory", "bedroom"))]
            far = self.far_box(sleep + beds, min_tiles=SHAFT_PEOPLE_MIN_TILES, rooms=True,
                               skip_roles=("dorm", "house", "office", "stress", "bedroom"))
            if far is not None:
                return why + "; use site %s with w=%d h=%d (far from it)" % (far[0].get("id"), far[1], far[2])
            if kind == "meeting_area" and self.shaft_wait():
                return why + "; wait for the digging to open a room further from it"
            return None
        if not self.shaft_wait():
            return None
        if tool == "build_farm" and self.shaft_plots_held(
                sum(1 for p in lst(self.o.get("farm_plots")) if isinstance(p, dict) and self.dry(p.get("z")))):
            return why + "; plant a farm site further from it"
        if tool == "dig_room" and self.placed_dry("bed") >= (self.cit or 0):
            return why + "; dig a room further from it"
        return None

    def shaft_dig_waits(self, r, size):
        """cx shaft people: a farm or dining room dig whose box (the R site's corner and `size`, 3x3 by default)
        lies near an open shaft column waits while shaft_wait (MY1-4 on the probe: R1, x97-99 y100-102, dug as a
        farm on day 0 and planted on day 5, one tile off the E1 foot; pdn1: R1 dug 9x7 as the dormitory on day 3
        with 22 beds standing for 15). A dormitory dig waits only while every citizen has a bed."""
        box = {"x": r.get("x"), "y": r.get("y"), "z": r.get("z"), "w": size.get("w", 3), "h": size.get("h", 3)}
        if not (self.shaft_near(box) and self.shaft_wait()):
            return False
        if self.may("shaft_dig_wait_" + str(r.get("id")), 10, 10 ** 6):
            self.last["shaft_dig_wait_" + str(r.get("id"))] = self.now
            log("shaft_dig_wait", day=self.day, site=r.get("id"), size=size or None)
        return True

    def surge_capacity(self):
        """mpjunior92's c1f36c62 surge measure: dig the dormitory capacity the wave needs BEFORE the beds exist, so
        placement never runs out of floor. A 9x7 dorm room is 63 floor tiles; the wave makes the fort need cit+24
        residents' worth (surge_dorm_rooms). It runs ahead of the farm allocation: the measured forts' R rooms were
        all soil, so the farm loop took every one of them first and this block (then after it, restricted to R
        rooms nobody had a role for) never found a spare one — dw6 LT08-1 logged no dig_dorm_cap at all, R1-R3 all
        farm, and the dorm role never existed (furnish then had no dormitory to fill: no layer bed placement in the
        whole run). Surge-scoped (LT08's shape): open-play tasks never dig it."""
        if not self.surge:
            return
        self.dorm_lost()
        have = sum(1 for rid, role in self.roles.items() if role == "dorm")
        added = 0
        spare = [r for r in self.undug_rooms() if r["id"] not in self.roles]
        rock = self.rock_rooms(spare)


        extra = bool(ROCK_DORM and rock and self.surge_beds_due() and not self.rock_rooms(self.dorm_rooms()))
        if have < surge_dorm_rooms(self.cit) or extra:
            r = self.pick_dig_site(rock) if rock and ROCK_DORM else None
            if r is None and not (extra and have >= surge_dorm_rooms(self.cit)):
                r = self.pick_dig_site(spare) if spare else None
            if r is not None and extra and have >= surge_dorm_rooms(self.cit):
                log("rock_dorm_dig", day=self.day, site=r.get("id"), have=have)
            if r is not None and have == 1 and self.rock_dorm_wait(r):
                r = None
            if r is not None:
                box = self.surge_room_box(r)
                result = self.act("dig_dorm_cap", "dig_room", box, retry=3, limit=6)
                if result and result.get("ok"):
                    self.roles[r["id"]] = "dorm"
                    self.note_room_box(r, box)
                    added = d(result.get("result")).get("designated")

        self.surge_floor(added if isinstance(added, int) and not isinstance(added, bool) else 0)
        self.rock_dorm_stair()

    def rock_rooms(self, rooms):
        """cx rock dorm: the rooms of a list the game reads as rock (soil False: no F site, so no plot, lands there)."""
        return [r for r in rooms if r.get("soil") is False]

    def dorm_rooms(self):
        """cx rock dorm: the listed R rooms this layer holds as dormitories."""
        return [r for r in self.kind("R") if self.roles.get(r.get("id")) == "dorm"]

    def surge_beds_due(self):
        """cx rock dorm: a surge fort before its hands-off window whose placed beds are under the forecast census."""
        return bool(self.surge) and isinstance(self.hands_off, int) and self.hands_off > 0\
            and self.placed_dry("bed") < self.surge_pop()

    def rock_dorm_wait(self, r):
        """cx rock dorm: a soil room is not dug as a further dorm while no bed item waits for floor and a rock-room
        stair can still come (no shaft stop, an entrance left under ENTRANCE_MAX, a listed S site on a rock column);
        a soil dorm's zone would also keep that stair SHAFT_PEOPLE_GAP away (b167a15: Dormitory 35 on R2 stood 1-5
        tiles from every S site). Once a bed waits, the soil room is dug as before."""
        if not ROCK_DORM or not ROCK_DORM_WAIT or r.get("soil") is not True or not self.surge_beds_due()\
                or self.beds_wait_floor():
            return False
        if self.rock_rooms(self.kind("R")) or self.shaft_stop or len(self.entrances) + 1 > ENTRANCE_MAX\
                or self.surface is None:
            return False
        zs = [a.get("z") for a in self.kind("A") if self.dry(a.get("z")) and isinstance(a.get("z"), int)]
        if not zs:
            return False
        zb = min(zs) - 1
        if self.shaft is None and not any(self._ints(x, ("x", "y", "z")) and 0 < x["z"] - zb <= 20
                                          and self.column_rock(x, zb + 1, x["z"] - 1) for x in self.kind("S")):
            return False
        if self.may("rock_dorm_wait_log", 2, 10 ** 6):
            self.last["rock_dorm_wait_log"] = self.now
            log("rock_dorm_wait", day=self.day, site=r.get("id"), spare_covers=self.hatch_free_spare())
        return True

    def beds_wait_floor(self):
        """cx rock dorm: a free bed item waits for floor — a dorm room's last bed placement (bed_full, within
        SURGE_BED_RETRY_DAYS) took fewer beds than it was offered, or no dorm room stands at all."""
        if (self.free.get("bed") or 0) <= 0:
            return False
        rooms = [rid for rid, v in self.roles.items() if v == "dorm"]
        if not rooms:
            return True
        today = self.obs_day()
        for rid in rooms:
            mark = self.bed_full.get(rid)
            if mark and isinstance(today, (int, float)) and isinstance(mark[0], (int, float))\
                    and today - mark[0] < SURGE_BED_RETRY_DAYS:
                return True
        return False

    def rock_dorm_stair(self):
        """cx rock dorm (ROCK_DORM above): on a surge fort with beds due, while every listed R room is soil (dug or
        not) and no dorm room is rock, one new surface stair under exactly shelter_shaft's conditions (a cover in stock
        and reserved, entrances within ENTRANCE_MAX, no big beast near, SHAFT_PEOPLE_GAP off the people zones, a rock
        column, hatched the pass its E site lists, any hatch refusal stops new shafts), so its levels list rock rooms
        (hint std LT08-2 on b167a15: S6 stayed listed d4-38, every room soil; the 150 runs dug it on day 3 for the rock
        R3 that held 27 beds)."""
        if not ROCK_DORM or not self.surge_beds_due() or self.breach:
            return
        rooms = self.kind("R")
        if not rooms or self.rock_rooms(rooms):
            return
        if self.may("rock_dorm_log", 2, 10 ** 6):
            self.last["rock_dorm_log"] = self.now
            log("rock_dorm_short", day=self.day, rooms=[r.get("id") for r in rooms][:8],
                spare_covers=self.hatch_free_spare(), entrances=len(self.entrances), shaft=bool(self.shaft))
        self.shelter_shaft(why="rock_dorm")

    def surge_room_box(self, r):
        """dig_room arguments for a surge dorm on R site r: the SURGE_FLOOR_ROOM box laid on the room's far side of
        its stair (observe.lua lists an R box east/west/south/north of the stair it touches), so the dig cuts new
        rock instead of running back over the dug level from the R box's top-left corner (LT08-0: R1 9x7 designated
        1 tile, R4 9x7 designated 2). The box still covers the R box, so the site leaves the candidate list the
        same way. Without a stair position, or off the map's edge, the site's own corner is kept (the old call)."""
        w, h = SURGE_FLOOR_ROOM
        plain = {"site": r["id"], "w": w, "h": h}




        if SURGE_ROOM_SITE_ONLY:
            return plain
        st = d(r.get("stair"))
        vals = (r.get("x"), r.get("y"), r.get("z"), st.get("x"), st.get("y"))
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
            return plain
        x, y, z, sx, sy = vals
        if x == sx + 1:
            x0, y0 = x, y - (h - 3) // 2
        elif x + 2 == sx - 1:
            x0, y0 = sx - w, y - (h - 3) // 2
        elif y == sy + 1:
            x0, y0 = x - (w - 3) // 2, y
        elif y + 2 == sy - 1:
            x0, y0 = x - (w - 3) // 2, sy - h
        else:
            return plain
        if x0 < 0 or y0 < 0:
            return plain
        return {"x": x0, "y": y0, "z": z, "w": w, "h": h}

    def surge_floor_free(self):
        """Free floor on the dry dug levels: each level's A open_tiles less its furniture, farm plots (w*h) and
        workshops (3x3). LT08-0 day 16: 139 open - 43 furniture - 7 plots*9 = 33 for 30 beds still to place."""
        out = 0
        for a in self.kind("A"):
            z = a.get("z")
            if not self.dry(z) or not isinstance(a.get("open_tiles"), int):
                continue
            used = sum(1 for f in lst(self.o.get("furniture")) if d(f).get("z") == z)
            used += sum((d(p).get("w") or 3) * (d(p).get("h") or 3) for p in lst(self.o.get("farm_plots"))
                        if d(p).get("z") == z)
            used += sum(9 for w in lst(self.o.get("workshops")) if d(w).get("z") == z)
            out += max(0, a["open_tiles"] - used)


        plots = [p for p in lst(self.o.get("farm_plots")) if self._ints(p, ("x", "y", "z", "w", "h"))]
        furn = [f for f in lst(self.o.get("furniture")) if self._ints(f)]
        for r in self.kind("R"):
            box = self.room_box.get(r.get("id"))
            if not any("farm plot" in str(u).lower() for u in lst(r.get("used_by")))\
                    or not self._ints(box, ("x", "y", "z", "w", "h")) or not self.dry(box["z"]):
                continue
            tiles = {(x, y) for x in range(box["x"], box["x"] + box["w"]) for y in range(box["y"], box["y"] + box["h"])}
            for p in plots:
                if p["z"] == box["z"]:
                    tiles -= {(x, y) for x in range(p["x"], p["x"] + p["w"]) for y in range(p["y"], p["y"] + p["h"])}
            tiles -= {(f["x"], f["y"]) for f in furn if f["z"] == box["z"]}
            out -= len(tiles)
        return max(0, out)

    def surge_floor_short(self, pending=0):
        """Surge only, before the window: the beds still to place (cit + 2 - placed) plus SURGE_FLOOR_MARGIN do not
        fit on the free floor plus the tiles still designated. No dug level yet = nothing to measure (False)."""
        if not self.surge or not isinstance(self.hands_off, int) or self.hands_off <= 0:
            return False
        if not any(self.dry(a.get("z")) for a in self.kind("A")):
            return False
        need = self.surge_pop() + 2 - self.placed_dry("bed")
        if need <= 0:
            return False
        return self.surge_floor_free() + max(0, pending) < need + SURGE_FLOOR_MARGIN

    def surge_floor(self, added=0):
        """The surge's floor capacity, measured in tiles (surge_capacity counts rooms): while surge_floor_short, a
        spare R site gets a SURGE_FLOOR_ROOM dorm dig (surge_room_box); with none listed — LT08-0 listed no R site
        from day 8 to day 38: R candidates need 3x3 of wall beside a stair, and the one level was dug out around
        every stair — a shaft is extended one level under the deepest dug level, so the new level's stair lists
        fresh R sites. The extension starts at a surface down stair (E: an existing shaft, its bottom up stair
        becomes up/down), then, if no R site listed within SURGE_FLOOR_STAIR_DAYS, at an S site's column from the
        deepest dug level down. Waits while a room's worth of tiles is still
        designated (the dig in progress will add floor; `added` = tiles designated earlier in this pass)."""
        pending = self.o.get("dig_designations_pending") or 0
        if not isinstance(pending, int):
            return
        pending += max(0, added)
        if not self.surge_floor_short(pending):
            return
        spare = [r for r in self.undug_rooms() if r["id"] not in self.roles and self.dry(r.get("z"))]
        rock = self.rock_rooms(spare) if ROCK_DORM else []

        r = (self.pick_dig_site(rock) if rock else None) or (self.pick_dig_site(spare) if spare else None)
        if r is not None and any(v == "dorm" for v in self.roles.values()) and self.rock_dorm_wait(r):
            return
        if r is not None:
            box = self.surge_room_box(r)
            res = self.act("dig_floor_cap", "dig_room", box, retry=1, limit=8)
            if res and res.get("ok"):
                self.roles[r["id"]] = "dorm"
                self.note_room_box(r, box)
                log("surge_floor_dig", day=self.day, site=r["id"], free=self.surge_floor_free(), pending=pending)
            return
        if pending >= SURGE_FLOOR_ROOM[0] * SURGE_FLOOR_ROOM[1] // 2 or self.surface is None:
            return
        zs = [a.get("z") for a in self.kind("A") if self.dry(a.get("z")) and isinstance(a.get("z"), int)]
        if not zs:
            return
        zb = min(zs) - 1






        last = self.last.get("stairs_floor_s")
        if last is not None and self.now - last < SURGE_FLOOR_STAIR_DAYS * DAY:
            return
        cands = [s for s in self.kind("S") if all(isinstance(s.get(k), int) for k in ("x", "y", "z"))
                 and 0 < s["z"] - zb <= 20 and not self.column_dug(s, zb + 1, s["z"] - 1)]
        site = self.pick_dig_site(cands, levels=2) if cands else None
        if site is None:
            return
        res = self.act("stairs_floor_s", "dig_stairs", {"site": site["id"], "z_bottom": zb},
                       retry=SURGE_FLOOR_STAIR_DAYS, limit=3)
        if res is None:
            return
        log("surge_floor_stair", day=self.day, site=site.get("id"), z_bottom=zb, ok=res.get("ok"),
            free=self.surge_floor_free())

    def column_dug(self, s, z_low, z_high):
        """cx: the x,y of site s lies inside a dug A box on some level z_low..z_high (the shaft would cross a dug
        floor there)."""
        for a in self.kind("A"):
            if isinstance(a.get("z"), int) and z_low <= a["z"] <= z_high\
                    and all(isinstance(a.get(k), int) for k in ("x", "y", "w", "h"))\
                    and a["x"] <= s["x"] < a["x"] + a["w"] and a["y"] <= s["y"] < a["y"] + a["h"]:
                return True
        return False

    def over_dug(self, s, z):
        """The x,y of site s lies inside the bounding box of level z's A site (the dug footprint there), so a stair
        started on that level at s is on or beside its floor, not sealed in rock."""
        for a in self.kind("A"):
            if a.get("z") == z and all(isinstance(a.get(k), int) for k in ("x", "y", "w", "h"))\
                    and a["x"] <= s["x"] < a["x"] + a["w"] and a["y"] <= s["y"] < a["y"] + a["h"]:
                return True
        return False

    def surge_stair(self, pending):
        """Surge only: designations that never finish leave the wave without floor. dw6 LT08-1 sat at pending 9-11
        from day 4 to day 38 ("manager cancels Dig: Dangerous terrain" beside indoor water) with no other R room
        listed — R sites only appear beside a dug stair, and the fort had one. When the pending count has not moved
        for SURGE_STALL_DAYS, no undesignated R room is left and the dorm capacity is still short, a second staircase
        is dug from another surface S site (water-ranked, pick_dig_site) to the level the rooms use, so new R rooms
        are listed away from the stuck ones. Never under a breach (digging() returns before this)."""
        if not self.surge or not isinstance(self.day, (int, float)):
            return
        if self.pend_mark is None or self.pend_mark[1] != pending:
            self.pend_mark = (self.day, pending)
            return
        if pending <= 0 or self.day - self.pend_mark[0] < SURGE_STALL_DAYS:
            return
        dug_dorms = sum(1 for r in self.kind("R") if self.roles.get(r["id"]) == "dorm" and r.get("dug"))
        if dug_dorms >= surge_dorm_rooms(self.cit) or any(r["id"] not in self.roles for r in self.undug_rooms()):
            return
        stairs = self.kind("S")
        site = self.pick_dig_site(list(stairs), levels=2) if stairs else None
        if site is None or self.surface is None:
            return
        result = self.act("stairs_surge", "dig_stairs", {"site": site["id"], "z_bottom": self.stair_bottom()},
                          retry=SURGE_STALL_DAYS, limit=3)
        if result and result.get("ok"):
            self.pend_mark = (self.day, pending)

    def farms(self):



        plots = [p for p in lst(self.o.get("farm_plots")) if self.dry(p.get("z"))]
        target = self.farm_target()
        if len(plots) >= target:
            return


        cands = (self.kind("F") or self.remembered("F")) + [r for r in self.dug_rooms() if r.get("soil") and self.roles.get(r["id"], "farm") == "farm"
                                  and r["id"] not in self.plot_rooms
                                  and not any("farm plot" in str(u).lower() for u in lst(r.get("used_by")))]
        seeds = self.live_seeds_by_kind()
        if any(not d(v).get("underground") for v in seeds.values()):
            cands += (self.kind("G") or self.remembered("G"))[:2]
        cands = [s for s in cands if self.dry(s.get("z"))]






        free = [s for s in cands if not self.room_taken(s)]
        if len(free) < len(cands):
            skipped = [s.get("id") for s in cands if s not in free]
            if skipped != getattr(self, "farm_skip_logged", None):
                self.farm_skip_logged = skipped
                log("farm_site_in_room", day=self.day, skipped=skipped, fallback=not free and not plots)
            spare = [] if free or not plots else self.surge_room_plots([s for s in cands if s not in free])
            cands = free or spare if free or plots else cands[:1]
        rush = self.seed_rush()
        cands = self.shaft_plots(cands, plots, target)
        cands = self.bed_room_hold(cands, plots)
        for s in cands[:target - len(plots)]:
            r = self.act("farm_" + s["id"], "build_farm", self.site_args(s, box=True), retry=4, limit=3)
            self.mem_used(s, r)
            if rush and r is not None and r.get("ok") and d(self.o.get("plugins")).get("autofarm") != "on":

                self.act("plug_autofarm", "enable_automation", {"name": "autofarm"}, retry=5)

    def bed_held_rooms(self):
        """cx held box (BED_HELD_BOX): the dug R rooms bed_room_hold kept for the beds that still hold no farm plot
        (a plot built there later ends the stop-gap)."""
        if not getattr(self, "bed_held", None):
            return []
        boxes = [p for p in lst(self.o.get("farm_plots")) if isinstance(p, dict)]
        return [r for r in self.kind("R") if r.get("id") in self.bed_held and r.get("dug")
                and r.get("id") not in self.plot_rooms
                and not any("farm plot" in str(u).lower() for u in lst(r.get("used_by")))
                and not any(self.rects_overlap(b, r) for b in boxes)]

    def bed_room_hold(self, cands, plots):
        """cx bed room (BED_ROOM_HOLD above): while the beds are short (placed under the census) and a bed is free or
        on order, a plot never takes the last dug room floor no plot holds — such a site is dropped once a plot
        stands or an earlier candidate this pass would make one (the first plot is never held). Off: the open play
        exceptions (surge, hands-off window), the MY1 plan (every plant is its drink), drink on hand short of
        BED_ROOM_DRINK_DAYS at the fort's rate, or the switch."""
        if not BED_ROOM_HOLD or getattr(self, "surge", None) or getattr(self, "hands_off", None) is not None\
                or not cands:
            return cands
        try:
            if self.placed_dry("bed") >= (self.cit or 0)\
                    or not ((self.free.get("bed") or 0) > 0 or self.pending("make_bed")) or self.my1_plan()\
                    or (self.st.get("drink") or 0) < self.f_drink_rate(prior_only=True) * BED_ROOM_DRINK_DAYS:
                return cands
        except Exception as e:
            log("bed_room_hold_error", error=repr(e)[:160])
            return cands
        boxes = [p for p in lst(self.o.get("farm_plots")) if isinstance(p, dict)
                 and all(isinstance(p.get(k), int) and not isinstance(p.get(k), bool) for k in ("x", "y", "z", "w", "h"))]
        rooms = [r for r in self.kind("R") if r.get("dug") and self.dry(r.get("z"))
                 and r.get("id") not in self.plot_rooms
                 and not any("farm plot" in str(u).lower() for u in lst(r.get("used_by")))
                 and not any(self.rects_overlap(b, r) for b in boxes)]
        out, held, n = [], [], len(plots)
        for c in cands:
            hits = [r for r in rooms if r.get("id") == c.get("id") or self.rects_overlap(r, dict(c, w=c.get("w") or 3,
                                                                                             h=c.get("h") or 3))]
            if hits and n >= 1 and not [r for r in rooms if r not in hits]:
                held.append(c.get("id"))
                self.bed_held |= {r.get("id") for r in hits if r.get("id")}
                continue
            out.append(c)
            n += 1
            rooms = [r for r in rooms if r not in hits]
        if held and self.may("bed_room_hold_log", 3, 10 ** 6):
            self.last["bed_room_hold_log"] = self.now
            log("bed_room_hold", day=self.day, held=held, rooms=[r.get("id") for r in rooms],
                beds_placed=self.placed_dry("bed"), free_beds=self.free.get("bed") or 0)
        return out

    def shaft_plots(self, cands, plots, target):
        """cx shaft people: farm plot sites on a fort with an open shaft — the sites MEETING_SHAFT_TILES from every
        open shaft column first (planting and harvest stand the farmers on the plot); a near one waits while
        shaft_wait and half the plot target already stands (shaft_plots_held: a fort short of food never waits).
        Other forts: unchanged."""
        if not self.shaft_people() or not cands:
            return cands
        box = lambda c: self.site_box(c, PLACE_MAX) if c.get("kind") == "R" else dict(c, w=c.get("w") or 3,
                                                                                         h=c.get("h") or 3)
        far = [c for c in cands if not self.shaft_near(box(c))]
        near = [c for c in cands if self.shaft_near(box(c))]
        if near and self.shaft_plots_held(len(plots), target) and self.shaft_wait():
            if self.may("shaft_plot_wait_log", 10, 10 ** 6):
                self.last["shaft_plot_wait_log"] = self.now
                log("shaft_plot_wait", day=self.day, near=[c.get("id") for c in near][:4],
                    far=[c.get("id") for c in far][:4])
            return far
        return far + near

    def shaft_plots_held(self, plots, target=None):
        """cx shaft people: at least one dry plot and half the plot target stand — a near-shaft plot or farm-room
        dig may wait for a far site then (MY1-4: 3 of 4 standing from the snapshot)."""
        target = self.farm_target() if target is None else target
        if self.plots_needed():
            return False
        return plots >= max(1, math.ceil(target / 2))

    def plots_needed(self):
        """cx audit 5: new farm plots never wait for a far site on a fort whose plants are its drink — the MY1 plan
        (every plant is a brew: hard MY1-3 on d57f599 had pb 4 and its model's build_farm F1 refused on day 3), or a
        fort whose drink plus its brewable plants' drinks fall short of the census need to the end."""
        try:
            if self.my1_plan():
                return True
            left = self.days_to_end()
            if not isinstance(left, (int, float)) or left <= 0:
                return False
            have = (self.st.get("drink") or 0) + (self.st.get("plants_brewable") or 0) * BREW_DRINKS
            return have < self.f_drink_rate(prior_only=True) * left
        except Exception as e:
            log("plots_needed_error", error=repr(e)[:160])
            return True

    def surge_room_plots(self, skipped):
        """cx surge room plot: on the migrant surge (LT08's shape), before its hands-off window, with plots standing
        but below farm_target and every listed F site on the floor of a room dug for people, one such site a pass may
        take a plot when (1) it shares no tile with any R site's own 3x3 box (the API marks a room "used" only by a
        plot over that box: gameapi/facts/sites.py update — so the room's beds and zones are still placed), (2) a
        crop sown now ripens before the run ends (HOLD_GROW_DAYS), and (3) the free floor less the plot's 9 tiles
        still holds the beds to place plus SURGE_FLOOR_MARGIN (surge_floor_short's own measure). Hint hard LT08-2 on
        c44c96b: three plots (27 tiles, 8 of them quarry bush / dimple cup) fed 48 citizens; F4/F5/F7/F8 were
        listed free on days 10-38 and skipped as room floor, 13 bed items stayed unplaced for want of beds made, not
        floor, and drink ended 476 under day 39's 484 (two brews short)."""
        if not self.surge or not isinstance(self.hands_off, int) or self.hands_off <= 0 or not skipped:
            return []
        left = self.days_to_end()
        if left is None or left < HOLD_GROW_DAYS:
            return []
        boxes = [{"x": r.get("x"), "y": r.get("y"), "z": r.get("z"), "w": 3, "h": 3} for r in self.kind("R")]
        ok = [s for s in skipped if not any(self.rects_overlap(dict(s, w=s.get("w") or 3, h=s.get("h") or 3), b)
                                            for b in boxes)]
        if not ok:
            return []
        pending = self.o.get("dig_designations_pending") or 0
        pending = pending if isinstance(pending, int) and not isinstance(pending, bool) else 0
        need = self.surge_pop() + 2 - self.placed_dry("bed")
        if self.surge_floor_free() + pending - 9 < max(0, need) + SURGE_FLOOR_MARGIN:
            return []
        log("surge_room_plot", day=self.day, site=ok[0].get("id"), free=self.surge_floor_free(), need=need)
        return ok[:1]

    def seed_rush(self):
        """cx: a lab fort with no drink, no brewable plant, no built farm plot and an underground seed kind in season
        now (seeds_by_kind), through SEED_RUSH_DAYS. hint hard LT02 (9a8a399 LT02-0 / 6adf843 LT02-1): plump helmet 3,
        dimple cup 2, pig tail 2, sweet pod 2 were in the SEEDS query on day 0 and gone on day 6-7 — before any plot
        stood (plots placed day 7-8; the R sites showed on day 2, their digs were designated on day 3-4 together with
        a 9x7 dormitory). Plump helmets ripen in ~25 days (std LT02-0), so a plot planted in the first days brews
        before the window; the rush only moves the plot ahead, it never adds a cost after it."""
        if not isinstance(self.hands_off, int) or self.surge or not isinstance(self.day, (int, float))\
                or self.day > SEED_RUSH_DAYS:
            return False
        if (self.st.get("plants_brewable") or 0) > 0 or (self.st.get("drink") or 0) >= max(1, self.cit or 0):
            return False
        if any(d(p).get("built") for p in lst(self.o.get("farm_plots"))):
            return False
        season = SEASON_NAMES[(self.game_doy() // SEASON_DAYS) % 4]
        return any((d(v).get("n") or 0) > 0 and d(v).get("underground") and season in lst(d(v).get("seasons"))
                   for v in self.live_seeds_by_kind().values())

    def rush_holds_digs(self):
        """cx seed rush: the non-farm room digs wait while a soil room is left to dig for a farm or a farm room is
        designated without its plot — the miners dig the plot's room alone."""
        if not self.seed_rush():
            return False
        soil_left = any(r.get("soil") and r["id"] not in self.roles for r in self.undug_rooms())
        farm_waiting = any(v == "farm" for v in self.roles.values()) and not lst(self.o.get("farm_plots"))
        return soil_left or farm_waiting

    def rush_signs(self, obs):
        """cx seed rush: the chunked advance's stop signs (read from the look's own observation): an undug soil R
        with no role yet ("farm_room:<id>") and a listed F site while no plot exists ("farm_site:<id>"), so the layer
        acts on the day the site appears instead of after the model's 2-3 day advance."""
        if not self.seed_rush():
            return set()
        out = set()
        sites = [d(x) for x in lst(d(obs.get("map")).get("sites"))]
        for x in sites:
            if x.get("kind") == "R" and x.get("soil") and not x.get("designated") and x.get("id") not in self.roles:
                out.add("farm_room:%s" % x.get("id"))
            if x.get("kind") == "F" and not lst(obs.get("farm_plots")):
                out.add("farm_site:%s" % x.get("id"))
        return out

    def cook_when(self, endgame=False):
        """A cook standing's when (add_order form, at most 3 clauses — the API rejects a fourth), kept in step with the
        season and the allocation:
        - the plants_brewable floor (cook_floor) guards the seed lineage only while brewing can return seeds — in
          winter, where pb sits at 0 on the measured farms, it is unreachable and inactivates every cook order, so
          it drops out (ROOT_CAUSES §D-1, df2-op1-hard/OP1-1 d302-330);
        - the seeds floor (ROOT_CAUSES §C-2) is not an add_order stock ("seeds" is answered "stock must be one of
          ...", and as a fourth clause "args.when has more than 3 items": every o_cook / o_cook_end / o_winter_cook
          with farm plots was rejected in the measured runs, dfx-my15-v2 among them, leaving only the model's and
          the plant-free emergency cook orders — no reserve, no seeds floor). cook_order() adds it as a SEEDS item
          condition through add_manager_order."""
        if endgame:
            food_gate = max(30, self.cit if self.days >= 336 else 4 * self.cit)
            when = [{"stock": "prepared_meals", "below": max(300, 10 * self.cit)},
                    {"stock": "food_edible", "at_least": food_gate}]
        else:
            when = [{"stock": "prepared_meals", "below": MEAL_CAP}, {"stock": "plants_total", "at_least": 10}]
        if self.days >= COOK_RESERVE_DAYS and COOK_PLANTS_RESERVE > 0 and (not self.winter() or self.hold_cook()):
            when.append({"stock": "plants_brewable", "at_least": self.cook_floor()})
        return when

    def cook_floor(self):
        """The cook standings' plants_brewable floor: COOK_PLANTS_RESERVE, the plant reserve in the build window,
        and the hold floor while the allocation has the kitchen yield to a short drink leg; the harvest-closed
        hold's reserve plus a standing's amount (2) while that holds and food is not the short leg (hold_cook)."""
        if self.hold_cook():
            base = self.hold_floor() if "cook" not in self.allocation() else COOK_PLANTS_RESERVE
            return max(base, self.hold_reserve() + 2)
        if not self.alloc_on() or self.last_stretch():
            return COOK_PLANTS_RESERVE
        if "cook" not in self.allocation():
            return self.hold_floor()
        return max(COOK_PLANTS_RESERVE, self.base_plant_floor())

    def seed_floor(self):
        """Seeds kept from the kitchen for replanting — none once nothing planted now could ripen before the run
        ends (harvest_closed, or the last HOLD_GROW_DAYS): the seeds can't feed the score any more, while the
        floor kept the final-stretch cook off with food the short leg (cx hint hard MY1-1 2026-11-10: seeds 27-30
        under the 45 floor, plants 27-32 unused, food 165 -> 152 in F, supply 0.81)."""
        left = self.days_to_end()
        if self.hands_off is None and ((left is not None and left <= HOLD_GROW_DAYS) or self.harvest_closed()):
            return 0
        plots = len(lst(self.o.get("farm_plots")))
        cit = getattr(self, "cit", None)
        if self.hands_off is not None and isinstance(cit, (int, float))\
                and (d(getattr(self, "st", None)).get("drink") or 0) < 3 * cit:




            plots = max(plots, self.farm_target())
        return plots * SEEDS_PER_PLOT

    def seed_guard(self):
        """cx: on a lab task, while the seeds are under the bank (seed_floor), a cook order this layer does not own and
        whose when holds no SEEDS floor above the stock is cancelled — DF cooks seeds (seedwatch's own deny call is
        plant AND seed cookery), the order cannot be given the clause after the fact, and with the plants at 0 the
        seeds are the only way back to a brewable harvest (hint hard LT02-0: the model's [prepared_meals < 34] cook
        ran on days 14-16 while 9 seeds went, none planted). Raw fish, meat and plants still feed the fort; this
        layer's own cook carries the SEEDS clause (cook_order)."""
        if self.hands_off is None:
            return
        floor, seeds = self.seed_floor(), self.st.get("seeds")
        if floor <= 0 or not isinstance(seeds, (int, float)) or isinstance(seeds, bool) or self.seeds_banked():
            return
        need = self.seed_need(floor)
        for x in self.orders:
            oid = x.get("id")
            if x.get("recipe") != "cook_meal" and x.get("job") != "PrepareMeal":
                continue
            if oid is None or oid in self.owned or not (x.get("repeat") or (x.get("left") or 0) > 0):
                continue
            if any(k[0] == "SEEDS" and t == "AtLeast" and isinstance(v, (int, float)) and v >= need
                   for k, t, v in when_sig(x.get("when"))):
                continue
            r = self.act("seed_guard_%s" % oid, "cancel_order", {"order_id": oid}, retry=1, limit=3)
            if r is not None and r.get("ok"):
                log("seed_guard_cancel", day=self.day, order=oid, seeds=seeds, floor=floor)

    def seed_census(self):
        """cx: on a lab task with no brewable plant, the SEEDS and PLANT_GROWTH stocks are read through the query
        (read-only, not an action) every SEED_CENSUS_DAYS: the observation's seeds_by_kind drops only forbidden
        seeds, while autofarm (DFHack 53.16-r2 find_plantable_plants) drops dump/forbid/garbage_collect/hostile/
        on_fire/rotten/trader/in_building/construction/artifact ones and fallows every plot when none is left
        (hint hard LT01-0 on 82d1ec1: 25 seeds incl. plump helmet 5 / sweet pod 5, every plot 'none' from day 1, no
        planting in 19 days). The flags go to the log (the next record says which), and a free fruit lets the
        fruit brew in (supply's o_fruit read only plants_by_kind, which never lists a growth)."""
        if self.hands_off is None or (self.st.get("plants_brewable") or 0) > 0:
            return
        early = isinstance(self.day, (int, float)) and self.day <= SEED_CENSUS_EARLY_DAYS
        if self.census_day is not None and isinstance(self.day, (int, float))\
                and self.day - self.census_day < (1 if early else SEED_CENSUS_DAYS):
            return
        query = getattr(self.game, "query", None)
        if query is None:
            return
        self.census_day = self.day
        out = {}
        for item_type in ("SEEDS", "PLANT_GROWTH"):
            try:
                raw = query("stocks", item_type=item_type)
            except Exception as e:
                log("seed_census_error", item_type=item_type, error=repr(e)[:160])
                continue
            r = query_result(raw)
            if r is None:
                log("seed_census_error", item_type=item_type, error=query_error(raw))
                continue
            groups = [d(g) for g in lst(r.get("groups"))]
            keys = ("rotten", "forbidden", "in_job", "in_building", "in_inventory", "construction")
            tot = {k: sum(int(g.get(k) or 0) for g in groups) for k in ("items", "count") + keys}
            free = sum(max(0, int(g.get("items") or 0) - sum(int(g.get(k) or 0) for k in
                                                           ("rotten", "forbidden", "in_building", "construction")))
                       for g in groups)
            out[item_type] = {**tot, "free_items": free,
                              "by_material": [{k: g.get(k) for k in ("material", "items", "count") + keys}
                                              for g in groups[:12]]}
        if not out:
            return
        self.census = out
        self.fruit_seen = d(out.get("PLANT_GROWTH")).get("free_items", 0) > 0
        log("seed_census", day=self.day, seeds=self.st.get("seeds"), **out)
        gone = self.seeds_not_in_query()
        if gone:
            log("seed_ghosts", day=self.day, kinds=gone)

    def plant_census(self):
        """cx plant census (PLANT_CENSUS_* above): once a game day while the fort has farm plots, the PLANT stock query
        (read-only, not an action) gives the plant items in buildings — the ripe crops standing in the plots, which
        plants_brewable counts but no Still or Kitchen job can take until a farmer harvests them. Kept as
        self.in_plot {"total", "brewable"} (a kind is brewable when plants_by_kind says so for the name the plant id's
        words match, as seeds_not_in_query matches seeds); brewable crops left unharvested HARVEST_STALL_DAYS are
        logged once per stall (harvest_stall) with what the record needs to say why. A refused or missing query
        leaves the last reading (None before the first)."""
        if not lst(self.o.get("farm_plots")) or not isinstance(self.day, (int, float)):
            return
        if self.plant_census_day is not None and self.day - self.plant_census_day < PLANT_CENSUS_DAYS:
            return
        query = getattr(self.game, "query", None)
        if query is None:
            return
        self.plant_census_day = self.day
        try:
            raw = query("stocks", item_type="PLANT")
        except Exception as e:
            log("plant_census_error", error=repr(e)[:160])
            return
        r = query_result(raw)
        if r is None or not isinstance(r.get("groups"), list):
            return
        kinds = d(self.st.get("plants_by_kind"))
        total = brew = items = 0
        loose = boxed = 0
        for g in r.get("groups"):
            g = d(g)
            n_items, n_count = int(g.get("items") or 0), int(g.get("count") or 0)


            m = str(g.get("material") or "")
            pid = set((m.split(":")[1] if m.count(":") >= 2 else m).lower().split("_"))
            if n_items > 0 and any(d(v).get("brewable") and set(str(k).lower().split()) <= pid
                                   for k, v in kinds.items()):
                per = n_count / n_items if n_count >= n_items else 1
                inv = int(g.get("in_inventory") or 0)
                if self.caravan_active and inv > 0:
                    per = 1
                out = n_items - inv - int(g.get("in_building") or 0) - int(g.get("in_job") or 0)\
                    - int(g.get("rotten") or 0)
                loose += round(max(0, out) * per)
                boxed += round(max(0, inv) * per)
            if int(g.get("rotten") or 0) >= n_items > 0:
                continue
            ib = int(g.get("in_building") or 0)
            n = max(0, ib - int(g.get("in_job") or 0))
            if n <= 0:
                continue




            units = (n_count * n + n_items // 2) // n_items if ib >= n_items > 0 and n_count >= n_items\
                else min(n, max(0, n_count - (n_items - ib)) if n_count else n)
            items += n
            total += units
            m = str(g.get("material") or "")
            pid = set((m.split(":")[1] if m.count(":") >= 2 else m).lower().split("_"))
            if any(d(v).get("brewable") and set(str(k).lower().split()) <= pid for k, v in kinds.items()):
                brew += units
        self.plant_loose = {"loose": loose, "contained": boxed, "day": self.day}
        self.loose_hist = [h for h in self.loose_hist if self.day - h[0] <= LOOSE_HIST_DAYS and h[0] < self.day]
        self.loose_hist.append([self.day, loose])
        prev = self.in_plot
        self.in_plot = {"total": total, "brewable": brew, "items": items}
        if prev is None or prev != self.in_plot:
            log("plant_census", day=self.day, in_plots=total, brewable=brew, pb=self.st.get("plants_brewable"),
                seeds=self.st.get("seeds"), sown=self.plot_tiles()[1])
        if brew >= HARVEST_STALL_MIN:
            if self.stall_since is None:
                self.stall_since = self.day
            if not self.stall_logged and self.day - self.stall_since >= HARVEST_STALL_DAYS:
                self.stall_logged = True
                jobs = {}
                for p in self.people:
                    jobs[p.get("job")] = jobs.get(p.get("job"), 0) + 1
                log("harvest_stall", day=self.day, since=self.stall_since, in_plots=total, brewable=brew,
                    seeds=self.st.get("seeds"), plots=self.plot_tiles(), barrels=self.st.get("barrels_empty"),
                    alert=d(self.o.get("burrows")).get("civilian_alert"), plugins=self.o.get("plugins"),
                    jobs=jobs, cancels=lst(self.o.get("recent_cancellations"))[:4])
        else:
            self.stall_since, self.stall_logged = None, False

    def pb_free(self):
        """cx plant census: the brewable plants a Still job can take — plants_brewable less the ripe crops still in the
        plots (plant_census). Without a census reading, plants_brewable as before."""
        pb = self.st.get("plants_brewable") or 0
        return max(0, pb - int(d(self.in_plot).get("brewable") or 0))

    def fruit_census(self):
        """cx: a free fruit stands (fruit_seen). A lab task reads it through seed_census; on open play the PLANT_GROWTH
        stock query (read-only) runs at most once a game day, only when supply's other o_fruit gates hold. A refused
        query leaves the last reading."""
        if self.hands_off is not None or not isinstance(self.day, (int, float)):
            return self.fruit_seen
        if self.fruit_census_day is not None and self.day - self.fruit_census_day < 1:
            return self.fruit_seen
        query = getattr(self.game, "query", None)
        if query is None:
            return self.fruit_seen
        self.fruit_census_day = self.day
        try:
            raw = query("stocks", item_type="PLANT_GROWTH")
        except Exception as e:
            log("fruit_census_error", error=repr(e)[:160])
            return self.fruit_seen
        r = query_result(raw)
        if r is None or not isinstance(r.get("groups"), list):
            return self.fruit_seen
        free = sum(max(0, int(d(g).get("items") or 0) - sum(int(d(g).get(k) or 0) for k in
                                                            ("rotten", "forbidden", "in_building", "construction")))
                   for g in r.get("groups"))
        self.fruit_seen = free > 0
        log("fruit_census", day=self.day, free=free, drink=self.st.get("drink"))
        return self.fruit_seen


    def sown_seeds(self):
        """Seeds standing in the farm plots: seeds_or_crops_in_plot (seed and plant items alike) less the ripe crops
        the plant census found in buildings (none without a reading: the plots then count as all seeds)."""
        tiles, sicp = self.plot_tiles()
        ripe = int(d(self.in_plot).get("items", d(self.in_plot).get("total")) or 0)
        return max(0, sicp - ripe)

    def free_seeds(self):
        """The seeds a SEEDS item condition counts: the observation's seeds (it counts the sown ones too) less the
        seeds in the plots."""
        seeds = self.st.get("seeds")
        if not isinstance(seeds, (int, float)) or isinstance(seeds, bool):
            return 0
        return max(0, int(seeds) - self.sown_seeds())

    def seed_need(self, floor=None):
        """The free seeds the bank (seed_floor: the whole bank, sown seeds included — its size is the owner's) still
        needs: what a SEEDS condition must ask for so the kitchen stops where the bank would fall under its floor.
        The measured dead clause: hint hard MY1-4 on d769d66 order 116 (o_winter_cook, FOOD < 300, PLANT >= 10,
        SEEDS >= 36) inactive days 101-216 with seeds 41-58, 17-36 of them sown — the bank stood over 36 throughout."""
        floor = self.seed_floor() if floor is None else floor
        if floor <= 0:
            return 0
        return max(0, floor - self.sown_seeds())

    def seeds_banked(self):
        """The bank holds its floor: the free seeds cover what it still needs (seed_need)."""
        return self.free_seeds() >= self.seed_need()

    def seed_clause_dead(self, x):
        """A cook order's SEEDS floor is above the free seeds: the game will not activate it now."""
        floors = [v for k, t, v in when_sig(x.get("when")) if k[0] == "SEEDS" and t == "AtLeast"
                  and isinstance(v, (int, float))]
        return bool(floors) and max(floors) > self.free_seeds()


    def brew_shots_queued(self):
        """[(order, key)] of this layer's brew one-shots still on the book with work left, oldest first."""
        out = [(x, self.brew_shots[x.get("id")]) for x in self.orders
               if x.get("id") in self.brew_shots and not x.get("repeat") and (x.get("left") or 0) > 0]
        return sorted(out, key=lambda p: p[0].get("id") or 0)

    def brew_queued(self):
        return sum(max(0, x.get("left") or 0) for x, _ in self.brew_shots_queued())

    def brew_budget(self):
        """The brewable plants no queued one-shot of this layer has claimed yet (may be negative)."""
        return self.pb_free() - self.brew_queued()

    def brew_shot_allow(self, key):
        """The plants a source's one-shots may hold at most now (pb_free less the floor its producer keeps), 0 where
        its producer would order nothing: the allocation's and the glut's while the plan has the Still yield (no
        "brew" side, or the food-lean keeper), the recycle's inside the hold (seed_recycle stands down there) and
        every one inside F while food is the falling min leg (rot_guard's own skip). cx plant barrel guard: never
        more than the barrelled plants less BARREL_KEEP."""
        allow = self._brew_shot_allow(key)
        pb = self.plant_barrel()
        if pb is not None and pb[0] > 0:
            allow = min(allow, max(0, pb[0] - BARREL_KEEP))
        return allow

    def _brew_shot_allow(self, key):
        free = self.pb_free()
        if not self.alloc_on():
            return free
        plan = self.plant_plan()
        if plan["lean"]:
            return free
        if key == "o_brew_rot":
            if plan["in_f"] and plan["food_first"]:
                return 0
            return free - plan["rot_keep"]
        if key == "o_brew_seed":
            return self.regrow_cap() if plan["hold"] else free
        if "brew" not in plan["sides"]:
            return 0
        return free - plan["floor"]

    def brew_shot_trim(self):
        """cx: cancel this layer's queued brew one-shots that lie wholly beyond what their sources may hold now
        (brew_shot_allow, in BREW_SHOT_KEYS priority: the rot guard's first, the glut's last) — a flip to cook-only
        takes the allocation's and the glut's back, the build window and the hold take back what eats into the
        reserve. An order only partly beyond stays (no cancel-and-re-add churn)."""
        queued = self.brew_shots_queued()
        if not queued:
            return
        rank = {k: i for i, k in enumerate(BREW_SHOT_KEYS)}
        queued.sort(key=lambda p: (rank.get(p[1], len(rank)), p[0].get("id") or 0))
        allow = {}
        held = 0
        for x, key in queued:
            if key not in allow:
                allow[key] = self.brew_shot_allow(key)
            left = max(0, x.get("left") or 0)
            if held >= allow[key]:
                oid = x.get("id")
                r = self.act("brew_trim_%s" % oid, "cancel_order", {"order_id": oid}, retry=2, limit=3)
                if r is not None and r.get("ok"):
                    log("brew_trim", day=self.day, order=oid, source=key, left=left, held=held, allow=allow[key],
                        pb=self.st.get("plants_brewable"), pb_free=self.pb_free(), sides=sorted(self.allocation()))
                continue
            held += left

    def seeds_not_in_query(self):
        """cx: {kind: n} of the observation's seeds_by_kind beyond what the last SEEDS census holds. The census groups
        carry the material (PLANT:<ID>:SEED) and the observation the plant's name, so the match is by the census's
        count against the observation total per kind when the plant id's words appear in the name (MUSHROOM_HELMET_PLUMP
        -> plump helmet). A kind with no census group at all is reported whole. Empty without a census."""
        groups = lst(d(d(self.census).get("SEEDS")).get("by_material"))
        if not d(self.census).get("SEEDS"):
            return {}
        have = {}
        for g in groups:
            m = str(d(g).get("material") or "")
            pid = m.split(":")[1] if m.count(":") >= 2 else m
            have[pid] = have.get(pid, 0) + int(d(g).get("count") or 0)
        out = {}
        for name, k in d(self.st.get("seeds_by_kind")).items():
            n = int(d(k).get("n") or 0)
            words = set(str(name).lower().split())
            got = sum(c for pid, c in have.items() if words and words <= set(pid.lower().split("_")))
            if n > got:
                out[name] = n - got
        return out

    def live_seeds_by_kind(self):
        """cx: the observation's seeds_by_kind less the ghosts (seeds_not_in_query) while the census is fresh (read
        within SEED_CENSUS_DAYS): the observation counts garbage-flagged seeds until DF collects them, the query
        and autofarm do not. hint hard LT02-2 on 02a3eea: the SEEDS query held all 14 seeds on day 0 and only cave
        wheat 3 / quarry bush 2 on day 1 — before any kitchen, plot or job (LT02-0 on 02a3eea: by day 2) — while
        seeds_by_kind listed all six kinds until day 14-17; the plump helmet / dimple cup / sweet pod plots set on
        those ghosts (9a8a399 day 10, plots 9-11 and 20) never received a seed. A stale or missing census leaves the
        observation as it is (a harvest may have returned seeds since)."""
        seeds = d(self.st.get("seeds_by_kind"))
        fresh = self.census_day is not None and isinstance(self.day, (int, float))\
            and self.day - self.census_day <= SEED_CENSUS_DAYS
        if not fresh:
            return seeds
        gone = self.seeds_not_in_query()
        if not gone:
            return seeds
        out = {}
        for name, v in seeds.items():
            n = int(d(v).get("n") or 0) - gone.get(name, 0)
            if n > 0:
                out[name] = {**d(v), "n": n}
        return out

    def note_room_box(self, site, args):
        """cx: remember the box a people room was dug as (room_taken): the args' x,y,w,h where given (a surge box),
        else the site's corner with the args' or the site's size."""
        a, s = d(args), d(site)
        box = {k: a.get(k, s.get(k)) for k in ("x", "y", "z")}
        box["w"] = a.get("w", s.get("w", 3))
        box["h"] = a.get("h", s.get("h", 3))
        if s.get("id") is not None:
            self.room_box[s["id"]] = box

    def room_taken(self, s):
        """cx: whether site s shares a tile with a room this layer dug for a non-farm role (note_room_box)."""
        for rid, box in self.room_box.items():
            if rid == s.get("id") or str(self.roles.get(rid) or "").startswith("farm"):
                continue
            if self.rects_overlap(box, s):
                return True
        return False

    def cook_order(self, when, amount=2):
        """(tool, args) of a repeat cook standing with `when`. With farm plots the seeds floor (plots x
        SEEDS_PER_PLOT, ROOT_CAUSES §C-2) joins as a SEEDS item condition through add_manager_order (job
        PrepareMeal — the cook_meal recipe's own job; the observation still names it cook_meal), replacing the
        second clause (plants_total / the endgame food gate) when the list is full: the plants floor implies
        plants. A rejected SEEDS condition (seeds_cond_ok) falls back to the bare add_order form."""
        sf = self.seed_floor()
        if sf <= 0 or not self.seeds_cond_ok:
            return "add_order", {"recipe": "cook_meal", "amount": amount, "repeat": "daily", "when": list(when)}
        items = [as_item(c) for c in when]


        seeds = {"item_type": "SEEDS", "at_least": self.seed_need(sf)}
        if len(items) >= 3:
            items[1] = seeds
        else:
            items.append(seeds)
        return "add_manager_order", {"job": "PrepareMeal", "amount": amount, "repeat": "daily", "when": items}

    def cook_act(self, key, tool, args, retry=3, limit=6):
        r = self.act(key, tool, args, retry=retry, limit=limit)
        if r is not None and not r.get("ok") and tool == "add_manager_order"\
                and r.get("error_code") == "bad_arguments":
            self.seeds_cond_ok = False
            self.last.pop(key, None)
            log("seeds_cond_off", key=key, err=str(r.get("error") or "")[:160])
        return r

    def cook_standing(self, endgame):
        """This layer's own repeat cook order: by the id act() recorded (o_cook / o_cook_end), else — after a
        restart — by shape: the endgame one carries a food_edible clause, the regular one a plants_total clause
        (o_cook_food, the plant-free emergency standing, matches neither; the winter plan's push standing is
        skipped by its own id — its higher meal cap is deliberate)."""
        oid = self.key_order.get("o_cook_end" if endgame else "o_cook")
        if oid is not None:
            x = next((x for x in self.orders if x.get("id") == oid and x.get("repeat")), None)
            if x is not None:
                return x
        skip = {oid for oid in (self.key_order.get("o_winter_cook"), self.key_order.get("o_cook"),
                                self.key_order.get("o_cook_end")) if oid is not None}
        for x in self.orders:
            if x.get("recipe") != "cook_meal" or not x.get("repeat") or x.get("id") not in self.owned:
                continue
            if x.get("id") in skip:
                continue
            stocks = {d(w).get("stock") for w in lst(x.get("when"))}
            if ("food_edible" in stocks) == endgame and (endgame or "plants_total" in stocks):
                return x
        return None

    def cook_when_same(self, have, want):
        """cx: a cook standing's when matches the wanted one: every clause equal but the SEEDS floor, which moves with
        every seed sown or harvested (seed_need) — it only counts as stale while the standing sits dead under a bank
        that allows cooking by SEED_COND_TOL free seeds, or asks SEED_COND_TOL under what the bank needs."""
        hs, ws = when_sig(have), when_sig(want)
        if hs == ws:
            return True
        if len(hs) != len(ws):
            return False
        free = self.free_seeds()
        for (hk, ht, hv), (wk, wt, wv) in zip(hs, ws):
            if (hk, ht) != (wk, wt):
                return False
            if hv == wv:
                continue
            if hk[0] != "SEEDS" or not all(isinstance(v, (int, float)) for v in (hv, wv)):
                return False
            if (hv > free and free - wv >= SEED_COND_TOL) or hv < wv - SEED_COND_TOL:
                return False
        return True

    def sync_cook(self, key, desired):
        """Keep an owned cook standing's when in step with the season and the allocation (a change re-cuts it once,
        and the re-add waits for a later load). The comparison reads both when forms (when_sig): the observation
        echoes test/value, never below/at_least. Returns True while a stale standing of this shape is on the book."""
        st = self.cook_standing(key == "o_cook_end")
        if st is None or self.cook_when_same(st.get("when"), desired):
            return False
        if self.may(key + "_recut", 4):
            self.act(key + "_recut", "cancel_order", {"order_id": st.get("id")}, retry=2, limit=8)
            self.done.discard(key)
        return True

    def brew_cap(self):
        """The regular brew standing's drink cap, adaptive to the census (the adaptive-cap fix, ROOT_CAUSES §H/§C):
        one scored year of consumption per citizen (DRINK_PER_CIT_YEAR, docs/SUCCESS.md §1.2), floored at 200 for
        the caravan glut (the wave3 fix, runs/w3-my1-s0). The former max(200, 6 * cit) was a 100-day buffer that
        sat under the measured LT08 surge's drink 571 -> 439 the whole run — the standing never fired while 47
        dwarves drank 940 a year (NOTES.md hard LT08-0). cx MY1 supply plan: inside the MY1 hold, the drink the rest
        of the run drinks at the plan's rate (the plants over the reserve brew while drink is under it)."""
        if self.my1_plan() and self.hold_active():
            left = self.days_to_end() or 0
            return max(HOLD_DRY_DAYS, int(math.ceil(self.f_drink_rate() * left)))
        return max(200, DRINK_PER_CIT_YEAR * self.cit)

    def brew_amount(self):
        """The standing's per-fire amount, proportional to the drink gap the cap measures (the adaptive-amount
        fix, same origin): a ten-days-of-consumption shortfall a brew, bounded 1..10. A recovered stock narrows
        the gap, so every add and census recut sizes it afresh; between recuts the standing's cap itself bounds
        how far the stock is pushed, so a refill simply stops the firing."""
        if self.my1_plan() and self.hold_active():


            return 1
        if self.food_lean():
            return LEAN_BREW_AMOUNT
        gap = max(0, self.brew_cap() - (self.st.get("drink") or 0))
        if self.barrel_keep():
            return max(1, min(BARREL_KEEP_AMOUNT, gap // 10))
        return max(1, min(10, gap // 10))

    def barrel_keep(self):
        """cx plant barrel keep (BARREL_KEEP above): a short open-play run (MY1) outside the hold, the food-lean
        keeper and the last stretch — o_brew fires BARREL_KEEP_AMOUNT over a floor that leaves BARREL_KEEP plants."""
        return self.alloc_on() and (self.days or 0) < 336 and not self.food_lean() and not self.hold_active()\
            and not self.last_stretch()

    def plant_barrel(self):
        """cx plant barrel guard: (barrelled, loose) brewable units on a fresh PLANT census on MY1 open play, else None."""
        if not self.alloc_on() or (self.days or 0) >= 336 or not isinstance(self.day, (int, float)):
            return None
        p = d(self.plant_loose)
        if not isinstance(p.get("day"), (int, float)) or self.day - p["day"] > PLANT_BARREL_FRESH_DAYS:
            return None
        if not isinstance(p.get("contained"), int) or not isinstance(p.get("loose"), int):
            return None
        return p["contained"], p["loose"]

    def barrel_brew_cap(self):
        """cx plant barrel guard: the layer brews the plant barrel can give now — its plants less BARREL_KEEP less the
        layer's brews already queued (the Still takes barrelled plants first); None when the guard is off (no fresh
        census, no barrelled plant: then there is no barrel to keep, and the stuck harvest is brewed as before)."""
        pb = self.plant_barrel()
        if pb is None or pb[0] <= 0:
            return None
        return max(0, pb[0] - BARREL_KEEP - self.brew_queued())

    def meal_wait(self):
        """cx plant barrel guard: plants lie loose with none barrelled — the layer's meal batches wait, at most
        PLANT_BARREL_WAIT_DAYS from the first such census, so the next barrel freed on the food stockpile goes to a
        plant."""
        pb = self.plant_barrel()
        if pb is None or pb[0] > 0 or pb[1] <= 0:
            self.barrel_lost_day = None
            return False
        if self.barrel_lost_day is None:
            self.barrel_lost_day = self.day
        return self.day - self.barrel_lost_day < PLANT_BARREL_WAIT_DAYS

    def brew_planned(self):
        """cx: the brew jobs on the book that want a barrel now: the one-shots' `left` (allocation, rot, glut, end,
        the model's) plus each repeat brew standing's amount while it can fire (not marked active: false by the game
        and, when its drink clause reads, drink still under it), bounded by the brewable plants (a job takes one)."""
        drink = self.st.get("drink") or 0
        n = 0
        for x in self.orders:
            if x.get("recipe") != "brew_drink":
                continue
            if not x.get("repeat"):
                n += max(0, x.get("left") or 0)
                continue
            if x.get("active") is False:
                continue
            caps = [v for k, t, v in when_sig(x.get("when")) if k == ("DRINK", None) and t == "LessThan"
                    and isinstance(v, (int, float))]
            if caps and drink >= min(caps):
                continue


            left = x.get("left") if isinstance(x.get("left"), (int, float)) else 0
            n += max(0, left if left > 0 else (x.get("total") or 0))
        return min(n, self.st.get("plants_brewable") or 0)

    def harvest_growing(self):
        """cx harvest barrels: the brewable plants the crops in the plots come back as — the sown seeds at
        HARVEST_YIELD each, a ripe crop (plant census) as itself — over the plots whose crop this season is a kind
        seen brewable or never seen standing (kind_brew; a 'none' or unknown crop counts), so a plot of quarry bush or
        dimple cup wants no barrel."""
        tiles, sown = self.plot_tiles()
        if sown <= 0:
            return 0.0
        brew_sown = 0
        for p in lst(self.o.get("farm_plots")):
            p = d(p)
            w, h, n = p.get("w"), p.get("h"), p.get("seeds_or_crops_in_plot")
            if p.get("built") is False or not all(isinstance(v, int) and not isinstance(v, bool) for v in (w, h, n)):
                continue
            if self.crop_brewable(p.get("crop_this_season")):
                brew_sown += n


        ripe_items = int(d(self.in_plot).get("items", d(self.in_plot).get("total")) or 0)
        ripe = int(d(self.in_plot).get("total") or 0)
        growing = max(0, sown - ripe_items) * HARVEST_YIELD + min(ripe, sown)
        return growing * brew_sown / sown

    def crop_brewable(self, crop):
        """A plot's crop id (MUSHROOM_HELMET_PLUMP) is brewable unless a kind whose name's words all appear in it (plump
        helmet) was seen standing non-brewable (kind_brew); unknown or no crop counts as brewable."""
        pid = set(str(crop or "").lower().split("_"))
        for name, ok in self.kind_brew.items():
            words = set(str(name).lower().split())
            if words and words <= pid:
                return bool(ok)
        return True

    def harvest_furniture_lean(self):
        """cx harvest press, furniture (above): the furniture targets fall to the census's scored need while the
        harvest press holds, outside the last ENDGAME_DAYS (where the margins for a late wave come back) and not on a
        migrant surge."""
        if self.surge or not self.barrel_press() or not self.press_harv:
            return False
        left = self.days_to_end()
        return left is None or left > ENDGAME_DAYS

    def harvest_barrels_short(self):
        """cx harvest barrels (HARVEST_* above): the empty barrels short of what the coming harvest wants — the
        brewable plants a job can take now (pb_free) plus the brewable crops in the plots (harvest_growing), capped at
        BARREL_AHEAD_MAX, less the empty barrels. Full-year open play, or once this fort's plants rot (the
        barrel-ahead gate in supply()); 0 otherwise, while the food-lean keeper holds the plants, and while
        HARVEST_IDLE_PLANTS no brew job takes stand beside PRESS_BARRELS_FREE empty barrels (not barrel-bound)."""
        if self.hands_off is not None or not (self.days >= 336 or self.rot_seen) or self.food_lean():
            return 0
        be = self.st.get("barrels_empty") or 0
        if be >= PRESS_BARRELS_FREE and self.pb_free() - self.brew_planned() >= HARVEST_IDLE_PLANTS:
            return 0
        want = min(BARREL_AHEAD_MAX, int(math.ceil(self.pb_free() + self.harvest_growing())))
        return max(0, want - be)

    def brew_standing(self):
        """This layer's own repeat brew standing (o_brew), found by the id act() recorded under the key — the
        closer's o_brew_end, the winter push o_winter_brew and the window's o_brew_win carry their own caps and
        shapes and are never recut here. After a restart, where key_order is empty, the observation still shows
        the standing but this returns None: an order this layer cannot attribute is left alone (it still
        suppresses the re-add through standing(), as before)."""
        oid = self.key_order.get("o_brew")
        if oid is None:
            return None
        return next((x for x in self.orders if x.get("id") == oid and x.get("recipe") == "brew_drink"
                     and x.get("repeat")), None)

    def sync_brew(self):
        """Keep the regular brew standing's drink cap in step with the census (the adaptive-cap fix). A repeat
        standing's when freezes at add time, so a cap sized for one census arms the gate for that census only —
        the LT08 surge's 12 -> 47-citizen wave left the 240 gate under drink 439 for the run (NOTES.md hard
        LT08-0). Like sync_cook (the wave-wealth recut), the stale standing is cancelled and supply() re-adds it
        on a later load, with the re-add waiting until the observation shows the cancellation; the +-30%
        tolerance keeps a one-dwarf census move from churning the Still. Returns True while a stale standing of
        this shape is on the book."""
        st = self.brew_standing()

        if st is None or (self.caravan_active and not self.hold_active()):
            return False
        want = self.brew_when()
        have_sig, want_sig = when_sig(st.get("when")), when_sig(want)
        gate, cap = (have_sig[0][2] if have_sig else None), want_sig[0][2]
        if isinstance(gate, (int, float)) and not isinstance(gate, bool)\
                and abs(gate - cap) <= 0.3 * cap and self.brew_rest_same(have_sig[1:], want_sig[1:]):
            return False
        if self.may("o_brew_recut", 4):
            self.act("o_brew_recut", "cancel_order", {"order_id": st.get("id")}, retry=2, limit=8)
        return True

    @staticmethod
    def brew_rest_same(have, want):
        """cx: o_brew's clauses after the drink cap match: the plants floor within BREW_FLOOR_TOL of the wanted one (a
        floor of 1-2 exactly), the rest equal. The floor rides the measured drink use (hold_reserve / plant_reserve), and an exact match
        re-cut the standing on every drift — hint std OP1-1 on 68bd4c7: 9 adds and 8 re-cuts, floors 40 -> 40 -> 48,
        the standing off the book 7-43 days after each cut until the next load re-added it. A move between the
        regimes (2 and a reserve of 20+) still re-cuts."""
        if len(have) != len(want):
            return False
        for (hk, ht, hv), (wk, wt, wv) in zip(have, want):
            if (hk, ht) != (wk, wt):
                return False
            if hv == wv:
                continue
            if hk != ("PLANT", "DRINK_MAT") or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                       for v in (hv, wv)):
                return False
            if min(hv, wv) <= 2 or abs(hv - wv) > BREW_FLOOR_TOL * max(hv, wv):
                return False
        return True

    def brew_on_book(self):
        """cx: a brew standing that stands in for o_brew: this layer's own (sync_brew keeps it in step), or another one
        that fires wherever o_brew would — a drink cap at or over o_brew's, a plants floor at or under its, an empty
        barrels floor at or under 1 and no other clause. A model's low-capped standing locked the layer's own out
        (hint std OP1-3 on e60d4ce: from day 214 o_brew never came back for 120+ days)."""
        if self.brew_standing() is not None:
            return True
        want = when_sig(self.brew_when())
        cap, floor = want[0][2], want[1][2]
        for x in self.orders:
            if x.get("recipe") != "brew_drink" or not x.get("repeat"):
                continue
            ok = True
            for k, t, v in when_sig(x.get("when")):
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    ok = False
                elif k == ("DRINK", None) and t == "LessThan":
                    ok = ok and v >= cap
                elif k == ("PLANT", "DRINK_MAT") and t == "AtLeast":
                    ok = ok and v <= floor
                elif k == ("BARREL", None) and t == "AtLeast":
                    ok = ok and v <= 1
                else:
                    ok = False
            if ok and self.barrel_keep() and not self.keeps_barrel(x.get("total") or x.get("left"), x.get("when"), True):
                ok = False
            if ok:
                return True
        return False

    def brew_floor(self):
        """o_brew's plants_brewable floor: 2 while the allocation runs the Still (or outside open play), the hold
        floor while it yields to a short food leg, and the harvest-closed hold's reserve plus the standing's largest
        firing (HOLD_STANDING_MARGIN) while that holds."""
        if self.my1_plan() and self.hold_active():




            return self.hold_reserve() + 1
        if self.food_lean():
            return 1
        if self.hold_active():
            if self.my1_plan():
                return self.hold_reserve() + 1
            return self.hold_reserve() + HOLD_STANDING_MARGIN
        if self.alloc_on() and "brew" not in self.allocation():
            return self.hold_floor()
        if self.hands_off is not None:






            return 1
        if self.barrel_keep():


            pb = self.plant_barrel()
            return BARREL_KEEP_AMOUNT + BARREL_KEEP + (pb[1] if pb is not None and pb[0] > 0 else 0)
        return 2

    def brew_when(self):
        cap = self.lean_drink if self.food_lean() else self.brew_cap()
        return [{"stock": "drink", "below": cap},
                {"stock": "plants_brewable", "at_least": self.brew_floor()},
                {"stock": "barrels_empty", "at_least": 1}]

    def surge_start_brew(self):
        """cx lt08seed (SURGE_START_FOOD above): a surge fort's first pass books a one-shot brew of the brewable
        plants in stock (no `when`, so the manager's first look validates it and no drink cap holds it back), once a
        game, before the window prep. Skipped when brewing them would leave food_edible under SURGE_START_FOOD per
        citizen. The seed comes back from the Still and autofarm sows it."""
        if not self.surge or "o_brew_start" in self.done or not isinstance(self.hands_off, int)\
                or self.hands_off <= WINDOW_PREP_DAYS:
            return
        pb = self.st.get("plants_brewable")
        food = self.st.get("food_edible")
        if not isinstance(pb, int) or isinstance(pb, bool) or pb <= 0 or not isinstance(food, (int, float)):
            return
        if food - pb < SURGE_START_FOOD * (self.cit or 0):
            return
        r = self.act("o_brew_start", "add_order", {"recipe": "brew_drink", "amount": min(pb, RECYCLE_MAX)},
                     retry=1, limit=4)
        if r is not None and r.get("ok"):
            self.done.add("o_brew_start")
            log("surge_start_brew", day=self.day, amount=min(pb, RECYCLE_MAX), food=food, cit=self.cit)

    def supply(self):
        """Standing orders that keep working in a hands-off window, then one-shot furniture sized to the population.
        While a caravan stays (ROOT_CAUSES §X) the observed brewable plants are the merchants': no new brew standing
        or fruit one-shot is added until the visit ends — the stocks they read are not the fort's own."""
        f_yield = self.f_keeper_yield()
        if f_yield:
            st = self.brew_standing()
            if st is not None:
                r = self.act("o_brew_fyield", "cancel_order", {"order_id": st.get("id")}, retry=1, limit=4)
                if r is not None and r.get("ok"):
                    log("f_keeper_yield", day=self.day, order=st.get("id"), drink=self.st.get("drink"),
                        food=self.st.get("food_edible"))
        if not f_yield and not self.surge_hold() and not self.sync_brew() and not self.brew_on_book()\
                and not self.caravan_active:






            self.act("o_brew", "add_order", {"recipe": "brew_drink", "amount": self.brew_amount(),
                                             "repeat": "daily", "when": self.brew_when()}, retry=3)
        if not self.standing("make_barrel"):
            self.act("o_barrel", "add_order", {"recipe": "make_barrel", "amount": 2, "repeat": "daily", "when": [
                {"stock": "barrels_empty", "below": 4}, {"stock": "logs", "at_least": 2}]}, retry=3)






        be = self.st.get("barrels_empty") or 0
        need = self.brew_planned() - be
        if self.hands_off is None and (self.days >= 336 or self.rot_seen) and not self.food_lean():




            need = max(need, self.harvest_barrels_short())
        spare = self.logs() - self.logs_guard()
        pend = sum(max(0, x.get("left") or 0) for x in self.orders
                   if x.get("recipe") == "make_barrel" and not x.get("repeat"))
        if self.hands_off is None and self.barrel_press():


            carp = sum(1 for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Carpenters")
            room = min(need, PRESS_JOBS_PER_BENCH * max(1, carp)) - pend
            if room >= 1 and spare >= 1:
                self.act("o_barrel_need", "add_order", {"recipe": "make_barrel",
                                                        "amount": min(PRESS_BARREL_BATCH, max(room, need - pend), spare)},
                         retry=1, limit=99)
        elif self.hands_off is None and need >= 4 and spare >= 1 and not pend:
            self.act("o_barrel_need", "add_order", {"recipe": "make_barrel", "amount": min(10, need, spare)},
                     retry=2, limit=99)
        tool, args = self.cook_order(self.cook_when())
        if not self.surge_hold() and not self.sync_cook("o_cook", args["when"]) and not self.regular_cook_on_book():
            self.cook_act("o_cook", tool, args, retry=3)


        if (self.st.get("drink") or 0) < 3 * self.cit and not self.st.get("plants_brewable")\
                and not self.caravan_active and not self.pending("brew_drink_from_fruit") and self.fruit_census():
            self.act("o_fruit", "add_order", {"recipe": "brew_drink_from_fruit", "amount": 3}, retry=4)
        seats = math.ceil(self.cit / 2) + 2



        cap = math.ceil(self.cit / 2)
        lean_furn = self.harvest_furniture_lean()
        full = self.seats_full()
        for recipe, have, want in (("make_bed", self.st.get("beds") or 0, self.bed_target()),
                                   ("make_table", self.st.get("tables") or 0,
                                    max(seats, full) + min(cap, self.stray("table"))),
                                   ("make_chair", self.st.get("chairs") or 0,
                                    self.chair_target(max(seats, full)) + min(cap, self.stray("chair")))):
            if lean_furn:

                want = min(want, {"make_bed": self.cit, "make_table": cap}.get(recipe) or self.chair_target(cap))
                key = "o_" + recipe
                oid = self.key_order.get(key)
                mine = next((x for x in self.orders if oid is not None and x.get("id") == oid), None)
                if mine is not None and have >= want and (mine.get("left") or 0) > 0:
                    r = self.act("furn_yield_" + recipe, "cancel_order", {"order_id": oid}, retry=1, limit=99)
                    if r is not None and r.get("ok"):
                        log("furniture_yield", day=self.day, recipe=recipe, order=oid, left=mine.get("left"),
                            have=have, want=want, barrels=self.st.get("barrels_empty"))
                    continue
            if self.surge and recipe == "make_bed":
                self.surge_bed_orders(have, want)
                continue
            if self.surge and self.surge_beds_short():
                continue
            if have < want and not self.pending(recipe) and self.logs():
                batch = 30 if (recipe == "make_bed" and self.surge) else 8
                self.act("o_" + recipe, "add_order", {"recipe": recipe, "amount": min(batch, want - have)}, retry=1, limit=99)

    def glut_bank(self):
        """Glut banking (MY1_AUTOPSY.md §3, runs/w3-my1-s0), redesigned by ROOT_CAUSES §G/§X. A brewable mountain
        (a caravan-scale jump over the last load, GLUT_JUMP — farm drip moves 1-4 plants a week — or a stock at
        GLUT_PB and up) draws a one-shot brew order, converting it into drink and returned seeds. Two gates now hold:
        the observed mountain is the merchants' while the caravan stays (caravan_active, §X) — no banking then; and a
        bank only feeds the Still while drink is the short leg — when food is the min leg and falling (food_min_leg,
        §G) the plants stay on the table, where the score's min actually reads them. No `when` on the order: the
        game rejects a one-shot with when — "add_order when needs repeat" (dfull-my1-hard 2026-11-09: 0 of 151
        o_brew_glut attempts succeeded across 6 runs, every reject bad_arguments; the bare one-shot MY1-4 order 28
        brewed 5). The act gate paces it to one attempt a day and carries the pb floor instead; no done record —
        gluts return, and each one deserves its own banking."""





        if self.caravan_active and self.glut_jump >= GLUT_JUMP and self.caravan_arrival_day is not None\
                and (self.day or 0) - self.caravan_arrival_day <= 1:
            return
        if self.days_left is not None and self.days_left <= BREW_SPARE_DAYS and self.food_min_leg():
            return
        if self.drink_glut():
            return
        plan = self.plant_plan() if self.alloc_on() else None
        if plan is not None and "brew" not in plan["sides"]:
            return
        pb = self.st.get("plants_brewable") or 0


        amount = min(5, self.brew_budget() - (plan["floor"] if plan is not None else 0))
        bcap = self.barrel_brew_cap()
        if bcap is not None:
            amount = min(amount, bcap)
        if amount < 1:
            return
        if self.glut_jump >= GLUT_JUMP or pb >= GLUT_PB:
            self.act("o_brew_glut", "add_order", {"recipe": "brew_drink", "amount": amount},
                     retry=1, limit=99)







    def window_days(self):
        """Days of consumption between now and the F window's start: a lab task's own countdown, else the endgame's
        calendar start."""
        if isinstance(self.hands_off, int) and 0 < self.hands_off:
            return self.hands_off
        if self.days_left is not None:
            return max(0, self.days_left - ENDGAME_DAYS)
        return max(0, (self.days or 0) - ENDGAME_DAYS - (self.day or 0))

    def winter_needs(self):
        """(drink, food) the winter should open with: citizens x (drink 20, food 10) plus what the fort consumes
        until the window opens at the measured rates (SCORING: ~5 drinks and 2 meals a season per dwarf)."""
        w = self.window_days()
        return (int(WINTER_DRINK_PER_CIT * self.cit + self.use_rate("drink", DRINK_PER_CIT_DAY) * self.cit * w),
                int(WINTER_FOOD_PER_CIT * self.cit + self.use_rate("food", FOOD_PER_CIT_DAY) * self.cit * w))

    def winter_plan(self):
        if self.days < 180 or self.caravan_active or self.day is None or self.winter():
            return
        plan_day = self.calendar_day(WINTER_PLAN_DOY, min(WINTER_PLAN_LATE_DAY, self.days - WINTER_PLAN_LOOKAHEAD))
        if (self.day or 0) < plan_day:
            return
        year = int(self.day) // YEAR_DAYS
        if self.winter_plan_year == year:
            return
        drink_need, food_need = self.winter_needs()
        short_drink = drink_need - (self.st.get("drink") or 0)
        short_food = food_need - (self.st.get("food_edible") or 0)
        seeds = d(self.st.get("seeds_by_kind"))
        winter_seeds = any(isinstance(k, dict) and "winter" in lst(k.get("seasons")) for k in seeds.values())
        ok = True
        if short_drink > 0:
            when = [{"stock": "plants_brewable", "at_least": 2}, {"stock": "barrels_empty", "at_least": 1}]
            if self.hold_active():
                when[0]["at_least"] = self.hold_reserve() + 4
            if winter_seeds:
                when.insert(0, {"stock": "drink", "below": drink_need})
            ok &= bool(d(self.act("o_winter_brew", "add_order", {"recipe": "brew_drink", "amount": 4,
                                                                 "repeat": "daily", "when": when},
                                  retry=3, limit=6)).get("ok"))
        if short_food > 0:
            plants = {"stock": "plants_total", "at_least": 10}
            if self.hold_cook():
                plants = {"stock": "plants_brewable", "at_least": max(10, self.hold_reserve() + 2)}
            tool, args = self.cook_order([{"stock": "prepared_meals", "below": max(300, food_need)}, plants])
            ok &= bool(d(self.cook_act("o_winter_cook", tool, args, retry=3, limit=6)).get("ok"))
        if ok:
            self.winter_plan_year = year
        log("winter_plan", day=self.day, cit=self.cit, drink_need=drink_need, food_need=food_need,
            short_drink=short_drink, short_food=short_food, winter_seeds=winter_seeds, planned=ok)


    def in_endgame(self):
        """Open-play tasks: the scored final stretch (the last quarter of the run, 7-28 days) is near."""
        return self.hands_off is None and self.days_left is not None and self.days_left <= ENDGAME_DAYS

    def in_window_prep(self):
        """Lab tasks: the hands-off window starts soon; after it begins only standing orders keep working."""
        return isinstance(self.hands_off, int) and 0 < self.hands_off <= WINDOW_PREP_DAYS

    def closer(self):
        slide = self.stock_sliding()
        if self.in_endgame() or slide:
            self.endgame_supply()
            if self.in_endgame():
                self.housing_check()
        elif self.in_window_prep():
            self.surge_window_hold()
            self.window_supply()
            self.housing_check()
        if self.surge:
            carp = sum(1 for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Carpenters")
            if carp == 1 and self.cit >= 15 and self.logs() >= 5:
                self.build("Carpenters", retry=3)
            elif 2 <= carp < SURGE_CARPENTERS and self.cit >= SURGE_CARP_CIT and self.logs() >= 5\
                    and self.surge_beds_short():

                self.build("Carpenters", key="ws_Carpenters_surge_%d" % (carp + 1), retry=3)

    def endgame_supply(self):
        """The supply sub-score credits a stock by its projected days left: a draining stock is credited only as far
        as it lasts, and a flat or rising one in full. From ENDGAME_DAYS before the horizon, a second brew order with a
        cap well above the usual one keeps drink rising through the final stretch (while plants stay above a reserve
        that protects the food count, since plants are food too), and cooking keeps meals rising from surplus food.
        Meat is added when edible food is short of a few days per citizen. Inside BREW_SPARE_DAYS of the horizon the
        brew standing also yields to the score's min leg (ROOT_CAUSES §G): with drink holding and food falling, every
        plant pushed through the Still is a plant the food leg needed — the standing is retired and held off, the
        plants staying food instead."""
        cap = max(600, 30 * self.cit)
        reserve = BREW_END_FLOOR
        if self.hold_active():
            reserve = self.hold_reserve() + 4
        spare = (self.days_left is not None and self.days_left <= BREW_SPARE_DAYS and self.food_min_leg())\
            or (self.alloc_on() and "brew" not in self.allocation())
        if spare:
            end_id = self.key_order.get("o_brew_end")
            if end_id is not None and end_id in self.owned:
                self.act("o_brew_end_retire", "cancel_order", {"order_id": end_id}, retry=4, limit=8)
                self.done.discard("o_brew_end")
        else:
            self.act("o_brew_end", "add_order", {"recipe": "brew_drink", "amount": 4, "repeat": "daily", "when": [
                {"stock": "drink", "below": cap}, {"stock": "plants_brewable", "at_least": reserve},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=3, limit=4)
        self.act("o_barrel_end", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 8}, {"stock": "logs", "at_least": 4}]}, retry=3, limit=4)






        tool, args = self.cook_order(self.cook_when(endgame=True))
        if not self.sync_cook("o_cook_end", args["when"]):
            self.cook_act("o_cook_end", tool, args, retry=3, limit=4)
        if (self.st.get("food_edible") or 0) < 4 * self.cit:
            self.butcher()

    def surge_hold(self):
        """LT08 shape, inside the window prep: the brewable plants are kept for the window (surge_window_hold)."""
        return self.surge and self.in_window_prep()

    def surge_window_hold(self):
        """The surge's plant hold before the window. Measured (dw6 LT08-0/1/2): plants_brewable 0/0/3 at day 38 while
        the model's repeat cook_meal ("prepared_meals below ~76", no plant floor) turned every plump helmet into
        meals (food_edible 103/116/212); inside the window drink rose ~10 days on the harvest, then fell, ending
        6-20 under drink[39]. From WINDOW_PREP_DAYS before the window: this layer's own o_brew and o_cook are
        retired (supply() holds their re-add, surge_hold), and while edible food covers SURGE_FOOD_SAFE per citizen
        the other repeat cook standings with no plants_brewable floor are cancelled (and any other repeat brew
        standing that can fire at today's drink), so the plants reach the
        window's brew standing (added on the window's eve, window_supply). Food stays: raw plants and the meals
        already cooked are edible, and the window brew keeps its own food floor."""
        if not self.surge_hold():
            return
        for key in ("o_brew", "o_cook"):
            oid = self.key_order.get(key)
            if oid is not None and any(x.get("id") == oid for x in self.orders):
                self.act(key + "_hold", "cancel_order", {"order_id": oid}, retry=1, limit=4)
        food_ok = (self.st.get("food_edible") or 0) >= SURGE_FOOD_SAFE * self.cit
        mine = {self.key_order.get(k) for k in ("o_cook_food", "o_brew_win", "o_brew_bridge_win")} - {None}
        drink = self.st.get("drink") or 0
        for x in self.orders:
            if not x.get("repeat") or x.get("id") in mine or x.get("recipe") not in ("cook_meal", "brew_drink"):
                continue
            stocks = {d(w).get("stock") for w in lst(x.get("when"))}
            if x.get("recipe") == "cook_meal" and ("plants_brewable" in stocks or not food_ok):
                continue
            if x.get("recipe") == "brew_drink" and any(
                    t == "LessThan" and isinstance(v, (int, float)) and v <= drink and k[0] == "DRINK"
                    for k, t, v in when_sig(x.get("when"))):
                continue
            self.act("plant_hold_%s" % x.get("id"), "cancel_order", {"order_id": x.get("id")}, retry=2, limit=3)

    def window_supply(self):
        """Before a hands-off window: brew whenever a plant and a barrel allow, so drink keeps rising while nobody
        can act (LT08 wants drink at the end above drink at the window's start; LT01 wants a batch brewed inside
        it). Plants are food too, and food must also hold through the window, so half a plant per citizen stays
        unbrewed. Barrels are the usual limit: an extra barrel order runs alongside."""









        if not self.surge or not isinstance(self.hands_off, int) or self.hands_off <= self.surge_brew_lead():
            self.act("o_brew_win", "add_order", {"recipe": "brew_drink", "amount": 5, "repeat": "daily", "when": [
                {"stock": "plants_brewable", "at_least": 2},
                {"stock": "food_edible", "at_least": max(3, self.cit // 2)},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=1 if self.surge else 2, limit=5)
        self.act("o_barrel_win", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 10}, {"stock": "logs", "at_least": 3}]}, retry=2, limit=5)
        self.window_bridge()
        self.fruit_watch()
        if (self.st.get("food_edible") or 0) < 4 * self.cit:
            self.butcher()

    def window_bridge(self):
        """cx lt08drink (SURGE_BRIDGE_RATE above): the surge's window brew bridge — one daily brew standing added once,
        at the start of the window prep, that fires only while drink is below the projected drink[A] (so it brews
        nothing before the window and holds drink at A inside it until o_brew_win, validated later, brews the rest).
        Its plant and food floors are o_brew_win's own (plants_brewable >= 2, food_edible >= max(3, cit // 2)); the
        barrel clause gives way to the drink cap (the API takes three clauses; o_barrel_win keeps 10 empty barrels —
        barrels_empty read 10-25 at d38 in every LT08 record)."""
        if not self.surge or not isinstance(self.hands_off, int) or self.hands_off <= 0 or "o_brew_bridge_win" in self.done:
            return
        drink, cit = self.st.get("drink"), self.cit or 0
        if not isinstance(drink, (int, float)) or isinstance(drink, bool) or cit <= 0:
            return
        cap = int(round(drink - SURGE_BRIDGE_RATE * cit * self.hands_off))
        win = (self.days_left - self.hands_off) if isinstance(self.days_left, int) and self.days_left > self.hands_off\
            else 21
        need = math.ceil(SURGE_WINDOW_USE * cit * win / BREW_DRINKS)
        amount = max(2, min(5, math.ceil(3 * need / win)))
        r = self.act("o_brew_bridge_win", "add_order", {"recipe": "brew_drink", "amount": amount, "repeat": "daily",
                                                        "when": [{"stock": "drink", "below": cap},
                                                                 {"stock": "plants_brewable", "at_least": 2},
                                                                 {"stock": "food_edible", "at_least": max(3, cit // 2)}]},
                     retry=1, limit=5)
        if r is not None:
            log("window_bridge", day=self.day, cap=cap, drink=drink, cit=cit, hands_off=self.hands_off, window=win,
                need=need, amount=amount, ok=bool(r.get("ok")))

    def surge_brew_lead(self):
        """cx: hands_off days at which the surge's window brew arms: SURGE_BREW_LEAD, plus the longest of the last
        three day gaps between this layer's passes (the model's stride: a pass may not come again before the window),
        capped at SURGE_BREW_LEAD_MAX."""
        gaps = [b - a for a, b in zip(self.pass_days, self.pass_days[1:])][-3:]
        return min(SURGE_BREW_LEAD_MAX, SURGE_BREW_LEAD + max([0] + gaps))

    def fruit_watch(self):
        """cx: a lab fort short of drink leaves a fruit brew standing for the window: one BREW_DRINK_FROM_PLANT_GROWTH
        a day, only while an unrotten fermentable growth, an empty barrel and a drink shortfall are all there (DF checks
        them at each repeat, so no job is made — and none cancelled — while no fruit exists). Every other window brew
        reads plants_brewable >= 2 and the one-shot o_fruit needs the fruit seen before the window; inside the window
        nobody can add either. hint hard LT02 (9a8a399 / 6adf843 / the leader's harness): the fort's only seeds left
        by day 6-7 are cave wheat 3 (summer / autumn, so not before run day 66) and quarry bush 2 (no drink), plants 0
        and PLANT_GROWTH 0 in every census through day 67, drink 0 for all 90 days. Not on the LT08 surge (its window
        brew waits for the eve on purpose)."""
        if self.surge or not isinstance(self.hands_off, int):
            return
        cap = max(1, FRUIT_WIN_DRINK_PER_CIT * self.cit)
        if (self.st.get("drink") or 0) >= cap:
            return
        self.act("o_fruit_win", "add_manager_order", {
            "job": "CustomReaction", "reaction": "BREW_DRINK_FROM_PLANT_GROWTH", "amount": 1, "repeat": "daily",
            "when": [{"item_type": "PLANT_GROWTH", "flags": ["unrotten"], "reaction_product": "DRINK_MAT",
                      "at_least": 1},
                     {"item_type": "BARREL", "flags": ["empty"], "at_least": 1},
                     {"item_type": "DRINK", "below": cap}]}, retry=2, limit=5)

    def ordered_now(self, key):
        """The regular supply step already ran this key in this pass (the observation's order list is stale then)."""
        return self.last.get(key) == self.now

    def housing_check(self):
        """Housing is read at the horizon: placed (built) beds per citizen and seats inside dining zones per two
        citizens. Near the end, order the shortfall at once (a built bed needs the item, a carpenter and an installer)
        and place whatever is free; the regular furnish step then zones it."""
        beds_short = self.cit - (self.placed.get("bed") or 0)
        if beds_short > 0 and (self.st.get("beds") or 0) < self.cit + 2 and self.logs() >= 2\
                and not self.pending("make_bed") and not self.ordered_now("o_make_bed"):
            self.act("o_bed_close", "add_order", {"recipe": "make_bed", "amount": min(30, max(2, beds_short + 2))},
                     retry=2, limit=10)
        if self.surge and beds_short > 0:
            return
        seats_short = math.ceil(self.cit / 2) - self.seats()
        if seats_short > 0 and self.logs() >= 2:
            want = math.ceil(self.cit / 2) + 1
            for recipe, kind in (("make_table", "table"), ("make_chair", "chair")):




                have = (self.placed_dry(kind) if self.breach else self.dine_count(kind)) + (self.free.get(kind) or 0)
                goal = max(want, self.dine_count("table")) if kind == "chair" and not self.breach else want
                if have < goal and not self.pending(recipe) and not self.ordered_now("o_" + recipe):
                    r = self.act("o_%s_close" % recipe, "add_order", {"recipe": recipe, "amount": min(30, goal - have)},
                                 retry=2, limit=10)
                    if r is not None:
                        log("housing_close", day=self.day, item=kind, have=have, stock=self.st.get(kind + "s"),
                            want=want, seats=self.seats(), cit=self.cit)

    def seats_full(self):
        """cx seats for all: one table and one chair per citizen (LackTables — eating without a table — measured on
        hint hard MY1-4, probe pmy14p), as long as the logs above logs_guard() pay for the pairs still missing; off
        while the harvest press runs lean, on a surge (beds first) and over a breach. 0 when off."""
        if self.surge or self.breach or self.harvest_furniture_lean():
            return 0
        cit = self.cit or 0
        short = max(0, cit - (self.st.get("tables") or 0)) + max(0, cit - (self.st.get("chairs") or 0))
        if short and self.logs() - self.logs_guard() < short:
            return 0
        return cit

    def seats(self):
        """Seats as the score counts them: tables and chairs inside dining zones."""
        n = 0
        for z in self.zone("dining"):
            f = d(z.get("furniture"))
            n += min(f.get("table") or 0, f.get("chair") or 0)
        return n

    def rezone(self):
        """Only furniture inside a zone counts or gets used. Zone each level's loose built tables, chairs and beds, and
        put a dining zone over a level whose tables and chairs sit in no dining zone (a dormitory's seats earn nothing)."""
        loose, by_z, handled = {}, {}, set()
        dining = {z.get("id") for z in self.zone("dining")}
        for f in lst(self.o.get("furniture")):
            f = d(f)
            if not f.get("built") or f.get("kind") not in ("bed", "table", "chair"):
                continue
            if not f.get("zone_ids"):
                loose.setdefault(f.get("z"), set()).add(f.get("kind"))
            if f.get("kind") != "bed" and not dining & set(lst(f.get("zone_ids"))):
                by_z.setdefault(f.get("z"), {}).setdefault(f["kind"], 0)
                by_z[f.get("z")][f["kind"]] += 1
        for z, kinds in loose.items():



            site = next((x for x in self.closed_a() if x.get("z") == z and self.area_fits(x, ZONE_MAX)
                         and not self.farm_claimed(x)), None)
            if not site:


                site = next((x for x in self.dug_rooms() if x.get("z") == z
                             and not self.roles.get(x["id"], "").startswith("farm")
                             and self.roles.get(x["id"]) != "office" and not self.farm_claimed(x)), None)
            if not site:
                continue
            if kinds & {"table", "chair"}:
                r = self.act("rz_dine_%s" % site["id"], "make_zone", {"kind": "dining_hall", "site": site["id"]}, retry=2, limit=3)
                if r and r.get("ok"):
                    handled.add(("lz_dine_", z))
            if "bed" in kinds:
                r = self.act("rz_dorm_%s" % site["id"], "make_zone", {"kind": "dormitory", "site": site["id"]}, retry=2, limit=3)
                if r and r.get("ok"):
                    handled.add(("lz_dorm_", z))
        for z, kinds in by_z.items():
            if kinds.get("table") and kinds.get("chair"):
                site = next((x for x in self.closed_a() if x.get("z") == z and (x.get("open_tiles") or 0) >= 6
                             and self.area_fits(x, ZONE_MAX) and not self.farm_claimed(x)), None)
                if site:
                    r = self.act("dx_dine_%s" % site["id"], "make_zone", {"kind": "dining_hall", "site": site["id"]}, retry=3, limit=2)
                    if r and r.get("ok"):
                        handled.add(("lz_dine_", z))
        self.zone_loose(handled)

    def wealth_created(self):
        return d(self.o.get("wealth")).get("created") or 0

    def wealth_target(self):
        """The created-wealth target the crafts chase. Full-year runs, until the caravan window closes: the Hamlet
        floor, raised to the census-free wave level (WAVE_POP_TARGET + buffer)·1000 — the DF2014 formula desired =
        wealth/1000 − citizens puts the post-wave census at about reported wealth/1000, so the target depends on the
        20 the rank needs, not on the current census. Once 20 citizens hold, the rank is already granted and the
        chase stops; after PROGRESS_LAST_DAY the report is gone until next year, so only the floor remains."""
        if self.days < 336 or (self.day or 0) > PROGRESS_LAST_DAY or self.cit >= 20:
            return WEALTH_TARGET
        return max(WEALTH_TARGET, (WAVE_POP_TARGET + WAVE_POP_BUFFER) * WAVE_WEALTH_PER_CIT)

    def furniture_logs_needed(self):
        """Logs the beds, seats and barrels still need before crafts may compete: the open furniture shortfalls
        (supply() sizes each at 1 log) plus BARREL_GUARD empty barrels of margin for the brew cycle. The chase
        pauses while the wood on hand is under this — the inventory first, the fund second (the measured OP1 board
        never starved: logs_usable min 167-269 after day 7 across runs/dfull-op1-hard, df2-op1-hard and
        cmp-base-op1-s0-r2, 2026-11-09 — so this is a guard, not a throttle, on the clean runs)."""
        seats = math.ceil(self.cit / 2) + 2
        beds_short = max(0, self.bed_target() - (self.st.get("beds") or 0))
        seats_short = max(0, seats - (self.st.get("tables") or 0)) + max(0, seats + 1 - (self.st.get("chairs") or 0))
        barrels_short = max(0, BARREL_GUARD - (self.st.get("barrels_empty") or 0))
        return beds_short + seats_short + barrels_short

    def logs_guard(self):
        """The log stock under which the wave chase yields to beds, seats and barrels."""
        return LOG_RESERVE + self.furniture_logs_needed()

    def craft_amount_chase(self):
        """The chase order's daily amount, adapted to this run's measured wealth production: while a mark spans
        CRAFT_RATE_SPAN days, the measured (wealth_created) rate must carry the remaining fund across the rest of
        the reporting window by CRAFT_RATE_MARGIN before the amount eases to CRAFT_AMOUNT_BASE — the fund is the
        goal, max throttle is not; an on-track fort stops burning logs into surplus crafts (measured: df2 OP1-1/2
        crossed the 21k fund with supply 1.00 and logs 168-363, so easing there protects the stock, not the rank)."""
        gap = self.wealth_target() - self.wealth_created()
        window_left = max(1, PROGRESS_LAST_DAY - (self.day or 0))
        cday, cfund = self.craft_checkpoint()
        cgap, cleft = cfund - self.wealth_created(), max(1, cday - (self.day or 0))
        if self.craft_mark is not None:
            d0, w0 = self.craft_mark
            span = (self.day or 0) - d0
            if span >= CRAFT_RATE_SPAN:
                rate = (self.wealth_created() - w0) / span


                if rate * window_left * CRAFT_RATE_MARGIN >= gap and rate * cleft * CRAFT_RATE_MARGIN >= cgap:
                    return CRAFT_AMOUNT_BASE
        return CRAFT_AMOUNT_WAVE

    def craft_checkpoint(self):
        """(day, created wealth) of the next wave checkpoint (CRAFT_CHECKPOINTS), else the window's end and fund."""
        day = self.day or 0
        for (cday, fund), doy in zip(CRAFT_CHECKPOINTS, CRAFT_CHECKPOINT_DOYS):
            cday = self.calendar_day(doy, cday)
            if day < cday:
                return cday, min(fund, self.wealth_target())
        return PROGRESS_LAST_DAY, self.wealth_target()

    def progress(self):
        """Full-year games only. The growth gate on a 336-day horizon also needs a DF progression step, and the only
        one in reach is the Hamlet rank: 20 citizens and 5000 created wealth. Citizens come with the year's migrant
        waves; wealth is made. Wood crafts are the cheapest wealth per log (several crafts from one log), so from
        PROGRESS_FROM_DAY a Craftsdwarfs is built and one standing order makes crafts whenever logs are above a
        reserve that keeps beds, barrels and seats first — the explicit order is furnish() then this, and when the
        wood on hand is under logs_guard() this layer neither adds the standing nor opens extra benches. On
        full-year runs the order's amount and the workshop count rise while the caravan-reported wave fund
        (wealth_target) is short — a fund farther than WAVE_GAP_THIRD_SHOP keeps a third bench behind the two, and
        the amount eases back once this run's measured wealth rate carries the remaining fund (craft_amount_chase) —
        both stop once the fund is met or the reporting window has closed."""
        if self.days < 336 or (self.day or 0) < PROGRESS_FROM_DAY or self.cit < 7:
            return
        self.progress_record()
        met = self.wealth_created() >= self.wealth_target()
        chasing = (self.day or 0) <= PROGRESS_LAST_DAY and self.cit < 20 and not met
        shops = [w for w in lst(self.o.get("workshops"))
                 if isinstance(w, dict) and w.get("type") == "Craftsdwarfs"]
        if not shops:
            self.build("Craftsdwarfs", retry=5)
            return
        if self.craft_press():
            self.craft_stalled()
            return
        self.craft_fallback()
        if met and any(x.get("job") == "MakeCrafts" and x.get("repeat")
                       and "bone" not in lst(x.get("material_category")) for x in self.orders):
            return
        low_logs = self.logs() < self.logs_guard()
        want = 1
        if chasing and not low_logs:
            gap = self.wealth_target() - self.wealth_created()
            want = 4 if gap > WAVE_GAP_FOURTH_SHOP else 3 if gap > WAVE_GAP_THIRD_SHOP else 2
        if len(shops) < want:
            self.build("Craftsdwarfs", retry=5)
        standing = next((x for x in self.orders if x.get("job") == "MakeCrafts" and x.get("repeat")
                         and "bone" not in lst(x.get("material_category"))), None)


        post = (self.day or 0) > PROGRESS_LAST_DAY
        desired = self.craft_amount_chase() if chasing else CRAFT_AMOUNT_POST if post else CRAFT_AMOUNT_BASE
        if standing is None:


            amount = self.craft_desired if self.craft_desired in (CRAFT_AMOUNT_BASE, CRAFT_AMOUNT_WAVE) else desired
            if self.logs() >= self.logs_guard():
                self.mark_craft_flip(amount)
                self.act("o_crafts_prog", "add_manager_order", {"job": "MakeCrafts",
                         "amount": amount, "repeat": "daily", "material_category": ["wood"],
                         "when": [{"item_type": "WOOD", "at_least": LOG_RESERVE}]}, retry=4, limit=6)
            return
        if chasing and (standing.get("total") or desired) != desired and not low_logs\
                and (self.craft_amount_day is None
                     or (self.day or 0) - self.craft_amount_day >= CRAFT_ADAPT_MIN_DAYS):
            self.mark_craft_flip(desired)
            r = self.act("o_crafts_recut", "cancel_order", {"order_id": standing.get("id")}, retry=2, limit=4)
            if r is not None and r.get("ok"):
                self.done.discard("o_crafts_prog")



    def craft_press(self):
        """cx barrel press: while brewable plants wait on barrels (barrel_press) or on a hand at the Still
        (labor_press), the wood crafts standing runs at
        PRESS_CRAFT_AMOUNT a day — a heavier standing is cancelled and re-added at that amount on a later load (the
        cancellation must show first: two standings would both run), no bench is added and the chase's re-cuts wait.
        On release this layer's throttled standing is cancelled and progress() re-adds the regime's own amount
        (o_crafts_prog may come back: it was retired by the press, not by the chase). Returns True while progress()
        must not touch the crafts."""
        wood = [x for x in self.orders if x.get("job") == "MakeCrafts" and x.get("repeat")
                and "bone" not in lst(x.get("material_category"))]
        mine = self.key_order.get("o_crafts_press")
        dry = self.wood_dry()
        if dry and self.may("wood_dry_log", WOOD_DRY_DAYS, 10 ** 6):
            self.last["wood_dry_log"] = self.now
            log("wood_dry", day=self.day, logs=self.logs(), since=self.wood_hist[0][0])
        if self.barrel_press() or self.labor_press() or dry:
            heavy = [x for x in wood if (x.get("total") or 0) > PRESS_CRAFT_AMOUNT]
            if heavy:
                for x in heavy:
                    r = self.act("o_crafts_hold_%s" % x.get("id"), "cancel_order", {"order_id": x.get("id")},
                                 retry=1, limit=4)
                    if r is not None and r.get("ok"):
                        self.done.discard("o_crafts_prog")
                        log("craft_press", day=self.day, held=x.get("id"), amount=x.get("total"),
                            pb=self.st.get("plants_brewable"), barrels=self.st.get("barrels_empty"))
            elif dry:
                for x in wood:
                    r = self.act("o_crafts_dry_%s" % x.get("id"), "cancel_order", {"order_id": x.get("id")},
                                 retry=1, limit=4)
                    if r is not None and r.get("ok"):
                        self.done.discard("o_crafts_prog")
            elif not wood:
                self.act("o_crafts_press", "add_manager_order", {"job": "MakeCrafts", "amount": PRESS_CRAFT_AMOUNT,
                         "repeat": "daily", "material_category": ["wood"],
                         "when": [{"item_type": "WOOD", "at_least": LOG_RESERVE}]}, retry=1, limit=99)
            return True
        if mine is not None and any(x.get("id") == mine for x in wood):
            r = self.act("o_crafts_free", "cancel_order", {"order_id": mine}, retry=1, limit=99)
            if r is not None and r.get("ok"):
                self.key_order.pop("o_crafts_press", None)
                self.done.discard("o_crafts_prog")
                log("craft_press", day=self.day, released=mine, pb=self.st.get("plants_brewable"),
                    barrels=self.st.get("barrels_empty"))
            return True
        return False

    def craft_stalled(self):
        """cx: created wealth rose under CRAFT_STALL_RISE over the last CRAFT_STALL_DAYS (one sample a day) while a
        wood MakeCrafts standing is on the book with work left — the wood the standing waits on is gone."""
        day = self.day
        if not isinstance(day, (int, float)) or isinstance(day, bool):
            return False
        w = self.wealth_created()
        if self.wealth_hist and self.wealth_hist[-1][0] == day:
            self.wealth_hist[-1] = (day, w)
        else:
            self.wealth_hist.append((day, w))
        wood = any(x.get("job") == "MakeCrafts" and x.get("repeat") and (x.get("left") or 0) > 0
                   and "wood" in lst(x.get("material_category")) for x in self.orders)

        if wood and any("wooden crafts" in str(t).lower() and "needs logs" in str(t).lower()
                        for t in lst(self.o.get("recent_cancellations"))):
            return True
        old = [p for p in self.wealth_hist if day - p[0] >= CRAFT_STALL_DAYS]
        if not old:
            return False
        d0, w0 = old[-1]
        return wood and w - w0 < CRAFT_STALL_RISE

    def craft_fallback(self):
        """cx: full-year runs, a stalled wood supply (craft_stalled) opens a bone crafts standing once (the _prog key)
        beside the wood one, which stays: wood that comes back is crafted again."""
        if not self.craft_stalled():
            return
        if self.press_day is not None and isinstance(self.day, (int, float))\
                and self.day - self.press_day < CRAFT_STALL_DAYS:
            return
        cats = {tuple(lst(x.get("material_category"))) for x in self.orders if x.get("job") == "MakeCrafts"}
        for cat in ("bone",):
            if (cat,) in cats:
                continue
            r = self.act("o_crafts_%s_prog" % cat, "add_manager_order", {
                "job": "MakeCrafts", "amount": CRAFT_ALT_AMOUNT, "repeat": "daily", "material_category": [cat]},
                retry=4, limit=3)
            if r is not None:
                log("craft_fallback", day=self.day, material=cat, ok=bool(r.get("ok")), wealth=self.wealth_created(),
                    logs=self.logs())

    def progress_record(self):
        """Record-only trace of the rank race, for post-run diagnosis (the scoring reads the recorder's daily
        prog.fortress_rank; this is the harness-side view of the same race). Log lines only — the AI-facing layers
        are deliberately untouched, so nothing here steers the model. Three facts, each once:
        - a migrant jump (citizens rose between loads) with the running wave sum;
        - the pop-20 crossing against the Hamlet wealth leg: the rank follows within ~2 d (measured 7/7 in the 24
          OP1 runs read 2026-11-09; no run stayed pop>=20 and rank 0 past 2 daily samples);
        - the stall after the second wave's window: under 20 citizens at day 214 with the fund the caravan last
          reported from — the run now rides the spring wealth wave or stops at rank 0."""
        if self.pop_prev is not None and self.cit > self.pop_prev:
            self.waves += self.cit - self.pop_prev
            log("prog_wave", day=self.day, arrived=self.cit - self.pop_prev, citizens=self.cit,
                waves=self.waves, wealth=self.wealth_created())
        self.pop_prev = self.cit
        if self.window_fund is None and (self.day or 0) > PROGRESS_LAST_DAY:
            self.window_fund = self.wealth_created()
        if not self.rank_note and self.cit >= WAVE_POP_TARGET and self.wealth_created() >= HAMLET_WEALTH:
            self.rank_note = True
            log("prog_rank_race", day=self.day, citizens=self.cit, wealth=self.wealth_created(),
                note="pop >= 20 with the Hamlet created wealth: the rank follows within ~2 d (7/7 measured)")
        if not self.stall_note and (self.day or 0) > 214 and self.cit < WAVE_POP_TARGET:
            self.stall_note = True
            log("prog_wave_stall", day=self.day, citizens=self.cit, waves=self.waves,
                window_fund=self.window_fund,
                note="both hard-coded waves are in and the census is under 20: the spring wealth wave is all "
                     "that is left, and its arrival lands ~19+ days into the season on the measured lag")

    def mark_craft_flip(self, desired):
        """Record an amount regime change: the measured-rate mark restarts (the old span blended two amounts) and
        the dwell clock restarts. A flip to the same amount keeps both (nothing changed)."""
        if desired != self.craft_desired:
            self.craft_desired = desired
            self.craft_amount_day = self.day
        self.craft_mark = (self.day, self.wealth_created())

    def area_fits(self, site, cap):
        """The zone/place tools' own size gates on a site (ROOT_CAUSES §I): make_zone answers
        "w must be an integer in [1,20]" and place_furniture "[1,40]" when the site's own extent is wider
        (facts/game.py validates the injected site w,h), so pick nothing wider — and nothing that has already
        answered the error. cap None keeps every site (the tools that have no such gate)."""
        if cap is None or not isinstance(site, dict):
            return True
        if site.get("id") in (self.zone_banned if cap <= ZONE_MAX else self.place_banned):
            return False
        return (site.get("w") or 1) <= cap and (site.get("h") or 1) <= cap

    def room_for(self, role, max_wh=None):
        """The dug level of a role's big room (its A site covers the whole dig), else the room itself. While a
        flood breach is active, wet levels are skipped (B-2c: the measured flood drowned the bedroom level while
        z141 stayed dry), the fallback prefers the highest — the driest, nearest-surface — A site, and max_wh
        caps the A side for the zone/place tools' own gates (ROOT_CAUSES §I): an A site wider than the cap is
        skipped in favour of the dug R room, whose extent the dig itself kept inside the limits."""
        rooms = [r for r in self.kind("R") if self.roles.get(r["id"]) == role and self.dry(r.get("z"))
                 and r["id"] not in self.plot_rooms]
        for r in rooms:
            a = next((s for s in self.closed_a() if s.get("z") == r.get("z") and s.get("id") not in self.plot_rooms
                      and self.dry(s.get("z")) and self.area_fits(s, max_wh) and not self.farm_claimed(s)), None)
            if a and role != "farm" and (r.get("dug") or a.get("open_tiles", 0) >= 6):
                return a
        dug = [r for r in rooms if r.get("dug")]
        if dug:
            return dug[0]
        taken = {r.get("z") for r in self.kind("R") if self.roles.get(r["id"], "").startswith("farm")}
        return next((s for s in sorted(self.closed_a(), key=lambda s: -(s.get("z") or 0))
                     if s.get("z") not in taken and s.get("open_tiles", 0) >= 6 and s.get("id") not in self.plot_rooms
                     and self.dry(s.get("z")) and self.area_fits(s, max_wh)), None)

    def dine_usable(self, dine, dorm=None):
        """Whether tables and chairs placed on `dine` can sit inside a dining zone: an A site always (its tiles take
        a second zone; only a dug R room is refused once a zone covers it, facts/sites.py USED_BY), a dug R room only
        while it is free, or a dining zone is all that holds it — never the dormitory room of this same pass."""
        if not isinstance(dine, dict) or dine.get("kind") != "R":
            return isinstance(dine, dict)
        used = [str(u) for u in lst(dine.get("used_by"))]
        box = self.site_box(dine, ZONE_MAX)
        if used:
            return all(u.startswith("DiningHall") for u in used)\
                or (self._ints(box, ("x", "y", "z", "w", "h"))
                    and any(self._ints(z, ("x", "y", "z", "w", "h")) and covers(z, box) for z in self.zone("dining")))
        if isinstance(dorm, dict) and dorm.get("id") == dine.get("id"):
            return False
        return dine.get("free", True) is not False

    def needs_zone(self, room, zones, kinds, placed=()):
        if any(covers(z, room) for z in zones):
            return False
        return any(f.get("kind") in kinds and covers(room, f)
                   and not any(covers(z, f) for z in zones)
                   for f in lst(self.o.get("furniture")) + list(placed))

    def place(self, key, kind, room, count):
        args = {"kind": kind, "site": room["id"], "count": count}
        args.update(self.box_wh(room, PLACE_MAX))
        result = d(self.act(key, "place_furniture", args, retry=1, limit=99))
        self.last_place = result
        if not result.get("ok"):
            return []
        points = d(result.get("result")).get("at") or []
        if points and not isinstance(points[0], list):
            points = [points]
        return [{"kind": kind, "x": x, "y": y, "z": z} for x, y, z in points]

    def floor_full(self):
        """Whether the last place_furniture was refused for lack of floor (the room is full, not busy or hidden)."""
        return d(self.last_place).get("error_code") == OVERFLOW_ERROR\
            or OVERFLOW_ERROR in str(d(self.last_place).get("error") or "")

    def overflow_site(self, dorm):
        """Where beds go when the primary dormitory's floor answered no_space: a dug dorm-role room first (the
        surge's extra dormitories — their dig exists for exactly this capacity, on any level), then the largest
        other dug area on the dormitory's own level (farm rooms and their levels stay out of the bedrooms), else
        the largest unused area site on another level. Floors already tried as overflow are not considered again."""
        farm_z = {r.get("z") for r in self.kind("R") if self.roles.get(r["id"], "").startswith("farm")}

        def free_floor(s, allow_rooms):
            return (s.get("id") != dorm.get("id") and s.get("id") not in self.overflow
                    and s.get("z") not in farm_z and (s.get("open_tiles") or 0) >= OVERFLOW_MIN_TILES
                    and (s.get("kind") == "A" or (allow_rooms and s.get("dug"))))

        dorms = [r for r in self.kind("R") if self.roles.get(r["id"]) == "dorm" and r.get("z") != dorm.get("z")
                 and r.get("dug") and free_floor(r, True)]
        same = [s for s in self.sites if s.get("z") == dorm.get("z") and free_floor(s, True)]
        other = [s for s in self.closed_a() if s.get("z") != dorm.get("z") and free_floor(s, False)]
        biggest = lambda pool: max(pool, key=lambda s: s.get("open_tiles") or 0, default=None)
        return biggest(dorms) or biggest(same) or biggest(other)

    def overflow_beds(self, dorm, n):
        """The primary dormitory's floor is full: put this day's free beds on the next floor instead and zone it (a
        dormitory zone already there is reused). The act gate allows one attempt a day; a floor is marked as tried as
        soon as it is attempted, so the next pass knocks somewhere else instead of on the same full one."""
        alt = self.overflow_site(dorm)
        if not alt:
            return
        result = d(self.act("beds_ov", "place_furniture", {"kind": "bed", "site": alt["id"], "count": n},
                            retry=1, limit=30))
        if not result:
            return
        self.overflow.add(alt["id"])
        points = d(result.get("result")).get("at") or []
        if points and not isinstance(points[0], list):
            points = [points]
        placed = [{"kind": "bed", "x": x, "y": y, "z": z} for x, y, z in points]
        if placed and self.needs_zone(alt, self.zone("dorm") + self.zone("bedroom"), ("bed",), placed):
            self.act("z_dorm_ov", "make_zone", {"kind": "dormitory", "site": alt["id"]}, retry=3)
    def placed_dry(self, kind):
        """Placed furniture of a kind that is not standing on a wet level: under a breach the furniture on a
        flooded level is dropped from the count, so furnish orders and places its replacement on a dry one
        (B-2c: the measured run kept beds counted on a drowned bedroom and never replaced them)."""
        if not self.breach:
            return self.placed.get(kind) or 0
        return sum(1 for f in lst(self.o.get("furniture"))
                   if d(f).get("kind") == kind and self.dry(f.get("z")))

    def meeting_area(self):
        """cx: a meeting area before the first migrant wave (~day 90). DF wiki (Immigration, known bug): with no meeting
        area a migrant can stall at the map edge and hold the rest of the wave off the map; every measured hint OP1/MY1 run
        had meeting_areas 0. One zone over the dining room (or the dorm level), once; any task shape."""
        if self.zone("meeting") or self.breach:
            return
        site = self.stress_site(meeting=True)
        near_shaft = self.shaft_cols() and MEETING_SHAFT_TILES is not None and (
            site is None or self.shaft_gap(self.site_box(site, ZONE_MAX)) < MEETING_SHAFT_TILES)
        if near_shaft:

            far = self.meeting_far_box()
            if far is None and isinstance(self.day, (int, float)) and self.day < MEETING_NEAR_DAY:
                if self.may("meeting_wait_log", 10, 10 ** 6):
                    self.last["meeting_wait_log"] = self.now
                    log("meeting_wait", day=self.day, site=(site or {}).get("id"))
                return
            if far is not None and self.meeting_in_pocket(*far):
                far = None
            if far is not None:
                s_, w_, h_ = far
                args = {"kind": "meeting_area", "site": s_["id"]}
                if (w_, h_) != (s_.get("w"), s_.get("h")):
                    args.update(w=w_, h=h_)
                r = self.act("z_meeting_far", "make_zone", args, retry=3, limit=4)
                if r is not None:
                    log("meeting_far", day=self.day, site=s_["id"], w=w_, h=h_, first=True, ok=bool(r.get("ok")))
                return


            near = self.meeting_far_box(gap=MEETING_FOOT_TILES)
            if near is not None and self.meeting_in_pocket(*near):
                near = None
            if near is not None:
                s_, w_, h_ = near
                args = {"kind": "meeting_area", "site": s_["id"]}
                if (w_, h_) != (s_.get("w"), s_.get("h")):
                    args.update(w=w_, h=h_)
                r = self.act("z_meeting_near", "make_zone", args, retry=3, limit=4)
                if r is not None:
                    log("meeting_near", day=self.day, site=s_["id"], w=w_, h=h_, ok=bool(r.get("ok")),
                        gap=self.shaft_gap({"x": s_["x"], "y": s_["y"], "z": s_["z"], "w": w_, "h": h_}))
                return
            if site is None or self.shaft_gap(self.site_box(site, ZONE_MAX)) < MEETING_FOOT_TILES:
                if self.may("meeting_foot_log", 10, 10 ** 6):
                    self.last["meeting_foot_log"] = self.now
                    log("meeting_foot_skip", day=self.day, site=(site or {}).get("id"))
                return
        if site is not None and self.meeting_in_pocket(site):
            site = None
        if site is not None and (getattr(self, "tries", None) or {}).get("z_meeting", 0) < 4:
            r = self.act("z_meeting", "make_zone", {"kind": "meeting_area", "site": site["id"]}, retry=3, limit=4)
            if r and r.get("ok") and isinstance(getattr(self, "stress_rooms", None), set):


                self.stress_rooms.add(site["id"])
            return






        mb = self.meeting_box()
        if mb is not None:
            s, w, h = mb
            args = {"kind": "meeting_area", "site": s["id"]}
            if (w, h) != (s.get("w"), s.get("h")):
                args.update(w=w, h=h)
            r = self.act("z_meeting_box", "make_zone", args, retry=3, limit=4)
            if r is not None:
                log("meeting_box", day=self.day, site=s["id"], w=w, h=h, ok=bool(r.get("ok")))
        elif self.open_a():
            self.people_room("meeting")

    def meeting_in_pocket(self, s, w=None, h=None):
        """cx shelter pocket: the meeting area this site's box would cover lies in a sole-exit pocket (pocket_box)."""
        box = {"x": d(s).get("x"), "y": d(s).get("y"), "z": d(s).get("z"),
               "w": w or d(s).get("w") or 3, "h": h or d(s).get("h") or 3}
        if not self.pocket_box(box):
            return False
        if self.may("meeting_pocket_log", 1, 10 ** 6):
            self.last["meeting_pocket_log"] = self.now
            log("meeting_pocket_skip", day=self.day, site=d(s).get("id"), w=box["w"], h=box["h"])
        return True

    def shaft_cols(self):
        """cx shaft child: open_entrances(), [] before any site list is loaded."""
        return self.open_entrances() if isinstance(getattr(self, "sites", None), list) else []

    def shaft_people(self):
        """cx shaft people: a fort with an open (unhatchable) entrance and the far-box rule on (MEETING_SHAFT_TILES),
        no flood breach (B-2's own placement rules win then)."""
        return MEETING_SHAFT_TILES is not None and not getattr(self, "breach", None) and bool(self.shaft_cols())

    def shaft_near(self, box):
        """cx shaft people: a box closer than MEETING_SHAFT_TILES (x/y) to an open shaft column on its levels."""
        return self.shaft_gap(box) < MEETING_SHAFT_TILES

    def shaft_wait(self):
        """cx shaft people: early open play (before MEETING_FAR_WAIT_DAY, no surge, no hands-off window) — near-shaft
        dining seats, farm plots and room digs wait for the digging to open a far box."""
        return self.shaft_people() and not getattr(self, "surge", None) and getattr(self, "hands_off", None) is None\
            and isinstance(self.day, (int, float)) and not isinstance(self.day, bool) and self.day < MEETING_FAR_WAIT_DAY

    def site_sig(self, sid):
        """cx confirmed floor: what of a site's own observation changes when its floor can (a dig opens tiles, a
        designation clears): its open_tiles, its dug-tile reading and the pending digs on its level."""
        s = next((x for x in getattr(self, "sites", None) or [] if isinstance(x, dict) and x.get("id") == sid), None)
        if s is None:
            return None
        pend = d(self.o.get("dig_pending_by_z")) if isinstance(getattr(self, "o", None), dict) else {}
        z = s.get("z")
        return (s.get("x"), s.get("y"), z, s.get("w"), s.get("h"), s.get("open_tiles"),
                d(s.get("tiles")).get("floor"), pend.get(z, pend.get(str(z))))

    def nofloor_key(self, sid, w=None, h=None):
        """(site, w, h) of a place_furniture box, a missing w/h read as the site's own extent (the tool's default)."""
        if w is None or h is None:
            s = next((x for x in getattr(self, "sites", None) or [] if isinstance(x, dict) and x.get("id") == sid), {})
            w = s.get("w") if w is None else w
            h = s.get("h") if h is None else h
        return (sid, w, h)

    def floor_refused(self, sid, w=None, h=None):
        """cx confirmed floor: the box (site, w, h) answered "no free floor tile" within NOFLOOR_DAYS and its site
        reads the same since (site_sig)."""
        mark = self.nofloor.get(self.nofloor_key(sid, w, h)) if sid is not None else None
        if mark is None:
            return False
        day, sig = mark
        today = self.obs_day()
        if isinstance(today, (int, float)) and isinstance(day, (int, float)) and today - day >= NOFLOOR_DAYS:
            return False
        return sig == self.site_sig(sid)

    def site_floor(self, site, walk=False):
        """cx confirmed floor: the floor tiles {(x, y)} of an A site's ZONE_MAX corner box from a map query (shape
        FLOOR-like and revealed, no dig designation, no building other than furniture on it), cached FLOOR_PROBE_DAYS
        while the site reads the same; None when the query failed or gave no reading of the level (unconfirmed).
        walk: the floor a zone can gather people on — tiles under a farm plot or a stockpile count too (a meeting
        area; nothing is placed there)."""
        num = lambda v: isinstance(v, int) and not isinstance(v, bool)
        if not isinstance(site, dict) or not all(num(site.get(k)) for k in ("x", "y", "z")):
            return None
        sid = site.get("id")
        x0, y0, z = site["x"], site["y"], site["z"]
        w = min(site["w"] if num(site.get("w")) else 3, ZONE_MAX)
        h = min(site["h"] if num(site.get("h")) else 3, ZONE_MAX)
        sig = (x0, y0, z, w, h, site.get("open_tiles"))
        today = self.obs_day()
        hit = self.floor_maps.get(sid)
        if hit is not None and hit[0] == sig and isinstance(today, (int, float)) and isinstance(hit[1], (int, float)):
            if today - hit[1] < (FLOOR_PROBE_DAYS if hit[2] is not None else 1):
                return hit[3] if walk else hit[2]
        tiles = walks = None
        try:
            r = self.game.query("map", x=min(400, max(0, x0 + (w - 1) // 2)), y=min(400, max(0, y0 + (h - 1) // 2)),
                                z=z, z2=z, radius=min(20, max(w, h) // 2 + 1))
            res = query_result(r)
        except Exception as e:
            log("site_floor_error", site=sid, error=repr(e)[:160])
            res = None
        if res is not None and num(res.get("x1")) and num(res.get("y1")):
            lv = next((d(v) for v in lst(res.get("levels")) if d(v).get("z") == z), None)
            if lv is not None and isinstance(lv.get("shape"), list):
                light = lv.get("light") if isinstance(lv.get("light"), list) else []
                busy, solid = set(), set()
                for b in lst(res.get("buildings")):
                    b = d(b)
                    kind = str(b.get("type") or "").lower()
                    if b.get("z") != z or kind in FURNITURE_BUILDINGS:
                        continue
                    if all(num(b.get(k)) for k in ("x1", "x2", "y1", "y2")):
                        cover = {(bx, by) for bx in range(b["x1"], b["x2"] + 1) for by in range(b["y1"], b["y2"] + 1)}
                        busy |= cover
                        if kind not in ("farmplot", "stockpile"):
                            solid |= cover
                for g in lst(res.get("designations")):
                    g = d(g)
                    if g.get("z", z) == z and num(g.get("x")) and num(g.get("y")):
                        busy.add((g["x"], g["y"]))
                tiles, walks = set(), set()
                for i, row in enumerate(lv["shape"]):
                    ty = res["y1"] + i
                    if not (y0 <= ty < y0 + h) or not isinstance(row, str):
                        continue
                    lrow = light[i] if i < len(light) and isinstance(light[i], str) else ""
                    for j, ch in enumerate(row):
                        tx = res["x1"] + j
                        if x0 <= tx < x0 + w and ch in FLOOR_SHAPES and (j >= len(lrow) or lrow[j] != "?"):
                            if (tx, ty) not in busy:
                                tiles.add((tx, ty))
                            if (tx, ty) not in solid:
                                walks.add((tx, ty))
        self.floor_maps[sid] = (sig, today, tiles, walks)
        if tiles is not None and self.may("site_floor_log_" + str(sid), 5, 10 ** 6):
            self.last["site_floor_log_" + str(sid)] = self.now
            log("site_floor", day=self.day, site=sid, box=[x0, y0, z, w, h], floor=len(tiles), walk=len(walks))
        return walks if walk else tiles

    @staticmethod
    def floor_in(tiles, b):
        """The floor tiles of `tiles` inside box b's x,y extent."""
        return sum(1 for (x, y) in tiles if b["x"] <= x < b["x"] + b["w"] and b["y"] <= y < b["y"] + b["h"])

    def far_site(self, site, avoid, min_tiles=SHAFT_PEOPLE_MIN_TILES, role=None, skip_roles=()):
        """cx shaft people: on a shaft fort, the site itself when its zone box already lies far from every open shaft
        column, else a copy of the far box's site (far_box, A sites and free dug rooms) carrying its w,h (far_wh, sent
        by box_wh); None when there is none. Off a shaft fort: the site unchanged."""
        if not self.shaft_people():
            return site
        if isinstance(site, dict) and not self.shaft_near(self.site_box(site, ZONE_MAX)):
            return site
        far = self.far_box(avoid, min_tiles=min_tiles, rooms=True, role=role, skip_roles=skip_roles)
        if far is None:
            return None
        s, w, h = far
        return dict(s, far_wh=(w, h))

    def shaft_gap(self, box):
        """cx shaft child: the x/y tiles (Chebyshev) between a box and the nearest open shaft column (an open
        entrance's x,y on the levels MEETING_SHAFT_LEVELS under it; 0 when the box holds it). A large number when
        there is no open entrance or the box is on no shaft level."""
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        if not isinstance(box, dict) or not all(num(box.get(k)) for k in ("x", "y", "z", "w", "h")):
            return 10 ** 6
        best = 10 ** 6
        for ex, ey, ez in self.shaft_cols():
            if not (ez - MEETING_SHAFT_LEVELS <= box["z"] <= ez):
                continue
            dx = max(box["x"] - ex, 0, ex - (box["x"] + box["w"] - 1))
            dy = max(box["y"] - ey, 0, ey - (box["y"] + box["h"] - 1))
            best = min(best, max(dx, dy))
        return best

    def meeting_far_box(self, gap=None, avoid=()):
        """cx shaft child: (A site, w, h) — a dry dug A site below the surface with no plot on it, its corner box
        (make_zone's addressing) cut back until it lies MEETING_SHAFT_TILES from every open shaft column and over no
        dormitory, bedroom or bed, at least MEETING_MIN_TILES tiles; the biggest such box (Shelter levels first).
        None when no site gives one."""
        if MEETING_SHAFT_TILES is None:
            return None
        beds = [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
                if isinstance(f, dict) and f.get("kind") == "bed"]
        sleep = [z for z in self.zones if any(k in str(z.get("type")).lower() for k in ("dormitory", "bedroom"))]
        return self.far_box(sleep + beds + list(avoid), walk=True, gap=gap)

    def far_cut(self, box, avoid, min_tiles, floor=None, placing=True, gap=None):
        """cx shaft people: (w, h) of the biggest corner box of `box` (make_zone's / place_furniture's addressing:
        the site corner and a w,h) that lies MEETING_SHAFT_TILES from every open shaft column, shares no tile with
        `avoid` and no farm-claimed room, at least min_tiles tiles; None when no cut gives one. cx confirmed floor:
        with `floor` (site_floor's tiles of an A site) a cut must hold FAR_FLOOR_MIN of them and the one holding the
        most floor wins (then the bigger); a cut that answered "no free floor tile" (floor_refused) is skipped."""
        if not all(isinstance(box.get(k), int) and not isinstance(box.get(k), bool) for k in ("x", "y", "z", "w", "h")):
            return None
        best, best_key = None, None
        sid = box.get("id")
        for h in range(box["h"], 0, -1):
            for w in range(box["w"], 0, -1):
                if w * h < min_tiles:
                    break
                b = dict(box, w=w, h=h)


                if self.shaft_gap(b) < (MEETING_SHAFT_TILES if gap is None else gap)\
                        or any(self.rects_overlap(z, b) for z in avoid) or self.farm_claimed(b)\
                        or self.reserved_hit(b) is not None:
                    continue
                n = self.floor_in(floor, b) if floor is not None else 0
                if floor is not None and n < FAR_FLOOR_MIN:
                    break
                if placing and sid is not None and self.floor_refused(sid, w, h):
                    continue
                key = (n, w * h)
                if best_key is None or key > best_key:
                    best, best_key = (w, h), key
                break
        return best

    def far_box(self, avoid, min_tiles=MEETING_MIN_TILES, rooms=False, cap=ZONE_MAX, role=None, skip_roles=(),
                walk=False, gap=None):
        """cx shaft child / shaft people: (site, w, h) — a dry dug A site below the surface with no plot on it (with
        `rooms`, also a dug R room make_zone still takes — a farm room or one of `skip_roles` never: a zone there makes
        the room read used and its own role's zone is refused), cut by far_cut; the biggest such box,
        a room of `role` first, then the higher level (Shelter levels first). None when no site gives one."""
        if MEETING_SHAFT_TILES is None:
            return None
        surface = d(self.o.get("map")).get("surface_z", getattr(self, "surface", None))
        cands = list(self.closed_a())
        if rooms:
            cands += [r for r in self.kind("R") if r.get("dug") and self.zoneable(r)
                      and not str(self.roles.get(r.get("id")) or "").startswith("farm")
                      and self.roles.get(r.get("id")) not in skip_roles]
        best = None
        for s in cands:
            if s.get("id") in self.plot_rooms or s.get("id") in self.zone_banned or not self.dry(s.get("z")):
                continue
            if s.get("kind") == "A" and (s.get("open_tiles") or 0) < min_tiles:
                continue
            if isinstance(surface, (int, float)) and isinstance(s.get("z"), (int, float)) and s["z"] >= surface:
                continue
            floor = None
            if s.get("kind") == "A":


                floor = self.site_floor(s, walk=walk)
                if floor is None:
                    continue
            cut = self.far_cut(self.site_box(s, cap), avoid, min_tiles, floor=floor, placing=not walk, gap=gap)
            if cut is None:
                continue
            w, h = cut
            size = self.floor_in(floor, dict(s, w=w, h=h)) if floor is not None else w * h
            key = (role is not None and self.roles.get(s.get("id")) == role, size, s.get("z") or 0)
            if best is None or key > best[0]:
                best = (key, s, w, h)
        return None if best is None else best[1:]

    def meeting_far(self):
        """cx shaft child (MEETING_SHAFT_TILES above): every meeting area stands within MEETING_SHAFT_TILES of an
        open shaft column and a far box exists — zone a second meeting area there (once; no tool removes the
        first)."""
        if MEETING_SHAFT_TILES is None or self.breach or not self.shaft_cols():
            return
        meets = self.zone("meeting")
        if not meets or any(self.shaft_gap(z) >= MEETING_SHAFT_TILES for z in meets):
            return
        far = self.meeting_far_box()
        if far is None or self.meeting_in_pocket(*far):
            return
        s, w, h = far
        args = {"kind": "meeting_area", "site": s["id"]}
        if (w, h) != (s.get("w"), s.get("h")):
            args.update(w=w, h=h)
        r = self.act("z_meeting_far", "make_zone", args, retry=3, limit=4)
        if r is not None:
            log("meeting_far", day=self.day, site=s["id"], w=w, h=h, first=False, ok=bool(r.get("ok")),
                near=[(z.get("x"), z.get("y"), z.get("z")) for z in meets][:3])

    def meeting_use(self):
        """cx rain shelter: counts the idle citizens' looks (observation dwarves[], job idle) — inside a meeting area,
        on the surface level — and, once MEETING_USE_LOOKS looks show fewer than MEETING_USE_MIN of them inside any
        meeting area while most stand on the surface, zones one more meeting area below the surface (meeting_far_box's
        dense box off the shaft, else the near box off the foot, else meeting_box), never over an existing one.
        Once a run; off over a breach."""
        meets = self.zone("meeting")
        surface = d(self.o.get("map")).get("surface_z", getattr(self, "surface", None))
        if self.breach or not meets or "z_meeting_use" in self.done or not isinstance(surface, (int, float)):
            return
        if self.meeting_looks_tick == self.now:
            return
        self.meeting_looks_tick = self.now
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        for p in self.people:
            if str(p.get("job") or "").lower() != "idle" or not all(num(p.get(k)) for k in ("x", "y", "z")):
                continue
            self.meeting_looks[0] += 1
            spot = {"x": p["x"], "y": p["y"], "z": p["z"], "w": 1, "h": 1}
            if any(self.rects_overlap(z, spot) for z in meets):
                self.meeting_looks[1] += 1
            if p["z"] >= surface:
                self.meeting_looks[2] += 1
        n, inside, up = self.meeting_looks
        if n < MEETING_USE_LOOKS or inside >= MEETING_USE_MIN * n or up * 2 < n:
            return


        homes = self.zone("dining") + [z for z in self.zones if any(k in str(z.get("type")).lower()
                                                                   for k in ("dormitory", "bedroom"))]
        def reach(b):
            for z in homes:
                if not all(num(z.get(k)) for k in ("x", "y", "z", "w", "h")) or abs(z["z"] - b["z"]) > 1:
                    continue
                dx = max(z["x"] - (b["x"] + b["w"] - 1), 0, b["x"] - (z["x"] + z["w"] - 1))
                dy = max(z["y"] - (b["y"] + b["h"] - 1), 0, b["y"] - (z["y"] + z["h"] - 1))
                if max(dx, dy) <= MEETING_USE_REACH:
                    return True
            return False
        box = None
        for pick in (lambda: self.meeting_far_box(avoid=meets),
                     lambda: self.meeting_far_box(gap=MEETING_FOOT_TILES, avoid=meets),
                     lambda: self.meeting_box(avoid=meets)):
            got = pick()
            if got is None:
                continue
            s_, w_, h_ = got
            b = {"x": s_.get("x"), "y": s_.get("y"), "z": s_.get("z"), "w": w_, "h": h_}
            if not all(num(b[k]) for k in b) or b["z"] >= surface or not reach(b)\
                    or self.shaft_gap(b) < MEETING_FOOT_TILES:
                continue
            box = got
            break
        if self.may("meeting_use_log", 5, 10 ** 6):
            self.last["meeting_use_log"] = self.now
            log("meeting_unused", day=self.day, looks=n, inside=inside, surface=up,
                site=box[0].get("id") if box else None)
        if box is None:
            return
        s_, w_, h_ = box
        args = {"kind": "meeting_area", "site": s_["id"]}
        if (w_, h_) != (s_.get("w"), s_.get("h")):
            args.update(w=w_, h=h_)
        r = self.act("z_meeting_use", "make_zone", args, retry=3, limit=4)
        if r is not None and r.get("ok"):
            self.done.add("z_meeting_use")

    def meeting_box(self, avoid=()):
        """The meeting area's fallback box: (A site, w, h) — a dry A site with no plot on it, a level holding a dining
        zone first (the dining room doubles as the meeting hall), then the higher level; the box is the site's corner
        box within make_zone's gate, cut back (width first, then height) until no dormitory or bedroom zone and no bed
        lies under it (idle socializers stay out of the sleepers' room). At least MEETING_MIN_TILES tiles; None when
        no site gives one."""
        beds = [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
                if isinstance(f, dict) and f.get("kind") == "bed"]
        sleep = [z for z in self.zones if any(k in str(z.get("type")).lower() for k in ("dormitory", "bedroom"))]
        dines = self.zone("dining")
        cands = []
        for s in self.closed_a():
            if s.get("id") in self.plot_rooms or s.get("id") in self.zone_banned or not self.dry(s.get("z"))\
                    or (s.get("open_tiles") or 0) < MEETING_MIN_TILES:
                continue
            box = self.site_box(s, ZONE_MAX)
            if not all(isinstance(box.get(k), int) and not isinstance(box.get(k), bool) for k in ("x", "y", "z"))\
                    or self.farm_claimed(box):
                continue
            cands.append((s, box))
        cands.sort(key=lambda e: (not any(self.rects_overlap(z, e[1]) for z in dines), -(e[0].get("z") or 0)))
        for s, box in cands:
            floor = self.site_floor(s, walk=True)
            if floor is None:
                continue
            if self.meeting_in_pocket(s, box["w"], box["h"]):
                continue
            for h in range(box["h"], 0, -1):
                for w in range(box["w"], 0, -1):
                    if w * h < MEETING_MIN_TILES:
                        break
                    b = dict(box, w=w, h=h)
                    if not any(self.rects_overlap(z, b) for z in sleep + beds + list(avoid))\
                            and self.reserved_hit(b) is None:
                        if self.floor_in(floor, b) >= min(FAR_FLOOR_MIN, MEETING_MIN_TILES):
                            return s, w, h
                        break
        return None

    def furnish(self):
        self.new_zones = []


        dorm, dine = self.room_for("dorm", ZONE_MAX), self.room_for("dine", ZONE_MAX) or self.room_for("dorm", ZONE_MAX)
        if dine is not None and not self.dine_usable(dine, dorm):




            log("dine_skip", day=self.day, site=dine.get("id"), used_by=dine.get("used_by"),
                dorm=(dorm or {}).get("id"))
            dine = None
        if dine is None and self.open_a() and (self.free.get("table") or 0) > 0\
                and not (self.surge and self.placed_dry("bed") < self.cit):
            self.people_room("dine")
        seat_wait = False
        if self.shaft_people() and not self.surge:

            dorm, dine, seat_wait = self.shaft_rooms(dorm, dine)
        if self.surge:
            self.surge_beds(dorm)
        else:
            short = self.cit + 2 - self.placed_dry("bed")
            n = min(self.free.get("bed") or 0, short, 30)
            placed = self.place("beds", "bed", dorm, n) if (dorm and n > 0) else []
            if n > 0 and len(placed) < n:



                self.surge_beds(dorm, already=len(placed))
            if dorm and self.needs_zone(self.site_box(dorm, ZONE_MAX), self.zone("dorm") + self.zone("bedroom"),
                                        ("bed",), placed):
                self.act("z_dorm", "make_zone", {"kind": "dormitory", "site": dorm["id"],
                                                 **self.box_wh(dorm, ZONE_MAX)}, retry=3)
        if not (self.surge and self.placed_dry("bed") < self.cit):


            want = math.ceil(self.cit / 2) + 1
            full = self.seats_full()
            placed = []
            for kind in ("table", "chair"):
                if not dine or dine.get("id") in self.plot_rooms:
                    break


                have = self.placed_dry(kind) if self.breach else self.dine_count(kind)
                goal = max(want, full)
                if kind == "chair" and not self.breach:


                    goal = max(want, self.dine_count("table") + sum(1 for f in placed if f["kind"] == "table"))
                n = min(self.free.get(kind) or 0, goal - have, 15)
                if n > 0:
                    placed += self.place("f_" + kind, kind, dine, n)
            if dine and self.needs_zone(self.site_box(dine, ZONE_MAX), self.zone("dining"), ("table", "chair"),
                                        placed):
                self.act("z_dine", "make_zone", {"kind": "dining_hall", "site": dine["id"],
                                                 **self.box_wh(dine, ZONE_MAX)}, retry=3)
            if not seat_wait:




                self.seat_spread(max(want, full), sum(1 for f in placed if f["kind"] == "table"),
                                 sum(1 for f in placed if f["kind"] == "chair"), half=want)

    def shaft_rooms(self, dorm, dine):
        """cx shaft people (SHAFT_PEOPLE_MIN_TILES above): (dorm, dine, seat_wait) for furnish on a fort with an open
        shaft. A dormitory whose box lies near the shaft is swapped for a far box (far_site: off the dining and
        meeting zones, tables and chairs) when beds are to be placed, else kept (beds never wait); the dining site
        for a far box off the sleepers and the new dormitory, else None while shaft_wait (seat_wait: seat_spread
        waits too) and kept after it."""
        def furn(kinds):
            return [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
                    if isinstance(f, dict) and f.get("kind") in kinds and self._ints(f)]
        zones_of = lambda words: [z for z in self.zones if any(k in str(z.get("type")).lower() for k in words)]



        beds_due = min(self.free.get("bed") or 0, self.cit + 2 - self.placed_dry("bed")) > 0
        if dorm is not None and beds_due:
            far = self.far_site(dorm, zones_of(("dining", "meeting")) + furn(("table", "chair")),
                                role="dorm", skip_roles=("dine", "office", "stress", "bedroom"))
            if far is not None and far is not dorm:
                log("shaft_dorm", day=self.day, near=dorm.get("id"), site=far.get("id"), wh=far.get("far_wh"))
                dorm = far
        sleep = zones_of(("dormitory", "bedroom")) + furn(("bed",))
        if isinstance(dorm, dict) and beds_due:
            sleep.append(self.site_box(dorm, ZONE_MAX))
        far = self.far_site(dine, sleep, role="dine", skip_roles=("dorm", "house", "office", "stress", "bedroom"))
        if far is not None:
            if far is not dine:
                if self.may("shaft_dine_log", 10, 10 ** 6):
                    self.last["shaft_dine_log"] = self.now
                    log("shaft_dine", day=self.day, near=(dine or {}).get("id"), site=far.get("id"),
                        wh=far.get("far_wh"))
            return dorm, far, False



        halls = self.zone("dining")
        if halls and not (isinstance(dine, dict) and any(self.rects_overlap(self.site_box(dine, ZONE_MAX), z)
                                                          for z in halls)):

            stand = [x for x in self.closed_a() + self.kind("R")
                     if x.get("id") not in self.plot_rooms and self.dry(x.get("z"))
                     and (x.get("kind") == "A" or x.get("dug"))
                     and any(self.rects_overlap(self.site_box(x, ZONE_MAX), z) for z in halls)]
            if stand:
                dine = stand[0]
        if self.may("shaft_dine_near_log", 10, 10 ** 6):
            self.last["shaft_dine_near_log"] = self.now
            log("shaft_dine_near", day=self.day, near=(dine or {}).get("id"))
        return dorm, dine, False

    def surge_bed_sites(self, dorm):
        """Where a surge fort's beds may go, in order: the primary dormitory (room_for), dug dorm-role R rooms, every
        dry A site inside place_furniture's own gate (PLACE_MAX 40 — not make_zone's 20: a bed counts as placed with
        or without a zone), largest floor first, then other dug free R rooms with no role. Farm levels are not
        excluded: every measured surge fort had ONE dug level and its farm plots on it (dw6 LT08-0 z169, LT08-1
        z148, LT08-2 z157), so the old farm-level exclusion left no site at all (LT08-0: the layer knocked on R2
        — a farm plot by then, site_used — from day 9 to the window, 19 beds placed with 17 free). A site that
        refused is skipped for SURGE_BED_RETRY_DAYS unless its open floor grew since (bed_full)."""
        out, seen, today = [], set(), self.obs_day()

        def full(s):
            mark = self.bed_full.get(s.get("id"))
            if mark is None:
                return False
            day, tiles = mark
            grown = isinstance(s.get("open_tiles"), int) and isinstance(tiles, int) and s["open_tiles"] > tiles
            fresh = isinstance(today, (int, float)) and isinstance(day, (int, float))\
                and today - day < SURGE_BED_RETRY_DAYS
            return fresh and not grown



        areas = []
        for a in sorted(self.kind("A"), key=lambda s: -(s.get("open_tiles") or 0)):
            if not self.dry(a.get("z")) or (a.get("open_tiles") or 0) < OVERFLOW_MIN_TILES:
                continue
            if self.area_fits(a, PLACE_MAX):
                areas.append(a)
            else:
                areas.extend(self.surge_chunks(a))

        areas = [a for a in areas if not self.box_open((a["x"], a["y"], a["z"], a.get("w") or 1, a.get("h") or 1)
                                                       if all(isinstance(a.get(k), int) for k in ("x", "y", "z"))
                                                       else None)]

        live = {a.get("parent", a.get("id")) for a in areas}
        full_z = {a.get("z") for a in self.kind("A") if full(a) and a.get("id") in live}
        by_z = {}
        for a in areas:
            by_z.setdefault(a.get("z"), []).append(full(a))
        full_z |= {z for z, marks in by_z.items() if all(marks)}

        def add(s):
            if not isinstance(s, dict) or s.get("id") in seen:
                return
            seen.add(s.get("id"))
            if full(s) or (s.get("kind") == "R" and s.get("z") in full_z):
                return
            out.append(s)

        add(dorm)
        for r in sorted(self.kind("R"), key=lambda s: -(s.get("open_tiles") or 0)):
            if (self.roles.get(r["id"]) in ("dorm", "house") or (self.surge and self.roles.get(r["id"]) == "office"))\
                    and r.get("dug") and self.dry(r.get("z"))\
                    and "farm" not in str(r.get("used_by") or "").lower() and r["id"] not in self.plot_rooms:
                add(r)
        for a in areas:
            add(a)
        for r in self.kind("R"):
            if r.get("dug") and r.get("free", True) and r["id"] not in self.roles and self.dry(r.get("z"))\
                    and r["id"] not in self.plot_rooms:
                add(r)
        return out

    def surge_chunks(self, a):
        """An A box wider than PLACE_MAX as boxes place_furniture takes (plain x,y,z,w,h, each side <= PLACE_MAX),
        carrying the parent's open_tiles for the bed_full growth check. Their ids are this layer's own (act keys,
        bed_full): the API never sees them. No coordinates = no chunks."""
        vals = [a.get(k) for k in ("x", "y", "z", "w", "h")]
        if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in vals):
            return []
        x, y, z, w, h = vals
        return [{"id": "%s@%d,%d" % (a.get("id"), x0, y0), "kind": "A", "chunk": True, "x": x0, "y": y0, "z": z,
                 "w": min(PLACE_MAX, x + w - x0), "h": min(PLACE_MAX, y + h - y0), "open_tiles": a.get("open_tiles"),
                 "parent": a.get("id"), "corner": x0 == x and y0 == y}
                for y0 in range(y, y + h, PLACE_MAX) for x0 in range(x, x + w, PLACE_MAX)]

    def chunk_where(self, site):
        """The surge site's place_furniture arguments (chunk_at); cx housing boxes: a dug room is addressed as the box
        it was dug (room_box, clamped to PLACE_MAX), not its 3x3 R corner."""
        where = self.chunk_at(site)
        if where is not None and not site.get("chunk"):
            where.update(self.box_wh(site, PLACE_MAX))
        return where

    @staticmethod
    def chunk_at(site):
        """cx: the place_furniture arguments for a surge site. The server requires `site` and the facts layer takes
        the site's own corner, keeping a given w/h (gameapi/server/rules.py, gameapi/facts/sites.py resolve; the raw
        x,y,z,w,h form answers "args.site is required"), so a chunk is addressed as its parent A site with the
        chunk's w/h — only the chunk at the parent's corner can be; None for the others."""
        if not site.get("chunk"):
            return {"site": site["id"]}
        if site.get("parent") is None or not site.get("corner"):
            return None
        return {"site": site["parent"], "w": site["w"], "h": site["h"]}

    def surge_beds(self, dorm, already=0):
        """The surge's bed placement: every free bed goes onto the first site that still takes beds, up to
        SURGE_BED_SITES sites a pass, until placed beds reach cit + 2. The primary dormitory is zoned as before;
        a full or refused site is recorded (bed_full) and the next one is tried in the same pass. cx housing boxes:
        open play's furnish() calls it too when its dormitory took fewer than the free beds (`already` = the beds
        that dormitory just took this pass); a pass that finds no site with floor marks house_full_day."""
        free = (self.free.get("bed") or 0) - already
        n = min(free, self.cit + 2 - self.placed_dry("bed") - already, 30)
        n0 = n
        tried, skip_z = 0, set()
        for site in self.surge_bed_sites(dorm):
            if n <= 0 or tried >= SURGE_BED_SITES:
                break
            if site.get("kind") == "R" and site.get("z") in skip_z:
                continue
            key = "beds" if dorm is not None and site.get("id") == dorm.get("id") else "beds_" + str(site.get("id"))
            where = self.chunk_where(site)
            if where is None:
                continue
            result = self.act(key, "place_furniture", {"kind": "bed", **where, "count": n}, retry=1, limit=99)
            if result is None:
                continue
            tried += 1
            self.last_place = result
            points = (d(result.get("result")).get("at") or []) if result.get("ok") else []
            if points and not isinstance(points[0], list):
                points = [points]
            placed = [{"kind": "bed", "x": x, "y": y, "z": z} for x, y, z in points]
            if result.get("ok") and placed and site.get("kind") in ("A", "R") and not site.get("chunk")\
                    and self.area_fits(site, ZONE_MAX) and self.needs_zone(site, self.zone("dorm") + self.zone("bedroom"), ("bed",), placed):
                self.act("z_dorm" if key == "beds" else "z_dorm_" + str(site.get("id")), "make_zone",
                         {"kind": "dormitory", "site": site["id"]}, retry=3)
            if not result.get("ok") or len(placed) < n:
                self.bed_full[site.get("id")] = (self.obs_day(), site.get("open_tiles"))
                if site.get("kind") == "A" and not result.get("ok") and result.get("error_code") != "site_open":
                    skip_z.add(site.get("z"))
                if result.get("error_code") == "site_used" and self.roles.get(site.get("id")) == "dorm":
                    self.roles.pop(site.get("id"), None)
                    log("surge_dorm_lost", day=self.day, site=site.get("id"))
            avail = d(result.get("result")).get("available")
            if result.get("ok") and not (isinstance(avail, int) and avail >= n > len(placed)):
                n -= len(placed)
                break
            n -= len(placed)
        if n > 0 and n == n0 and tried and not self.surge:
            self.house_full_day = self.obs_day()
        if dorm is not None and n > 0 and self.needs_zone(self.site_box(dorm, ZONE_MAX),
                                                          self.zone("dorm") + self.zone("bedroom"), ("bed",)):
            self.act("z_dorm", "make_zone", {"kind": "dormitory", "site": dorm["id"],
                                             **self.box_wh(dorm, ZONE_MAX)}, retry=3)


    @staticmethod
    def _ints(s, keys=("x", "y", "z")):
        return isinstance(s, dict) and all(isinstance(s.get(k), int) and not isinstance(s.get(k), bool) for k in keys)

    def box_wh(self, site, cap):
        """The w,h to send with a site tool call: {} when the site's own extent already is the box (the tool's
        default), else a dug R room's room_box size (it was dug wider than its 3x3 corner) and any extent past the
        tool's gate (`cap`: ZONE_MAX for make_zone, PLACE_MAX for place_furniture) clamped to it — the site's corner
        box, which the API addresses (facts/sites.py resolve keeps a given w,h)."""
        if not isinstance(site, dict):
            return {}
        w0, h0 = site.get("w"), site.get("h")
        w, h = (w0 if isinstance(w0, int) else 3), (h0 if isinstance(h0, int) else 3)
        fw = site.get("far_wh")
        if isinstance(fw, tuple) and len(fw) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in fw):
            w, h = max(1, min(fw[0], cap)), max(1, min(fw[1], cap))
            return {} if (w, h) == (w0, h0) else {"w": w, "h": h}
        if site.get("kind") == "R":
            b = self.room_box.get(site.get("id"))
            if isinstance(b, dict) and all(b.get(k) == site.get(k) for k in ("x", "y", "z"))\
                    and isinstance(b.get("w"), int) and isinstance(b.get("h"), int):
                w, h = b["w"], b["h"]
        w, h = max(1, min(w, cap)), max(1, min(h, cap))
        return {} if (w, h) == (w0, h0) else {"w": w, "h": h}

    def site_box(self, site, cap):
        """The x,y,z,w,h box a site call with box_wh() covers (needs_zone and covers read it)."""
        box = {k: site.get(k) for k in ("id", "x", "y", "z", "w", "h")}
        box["w"] = box["w"] if isinstance(box["w"], int) else 3
        box["h"] = box["h"] if isinstance(box["h"], int) else 3
        box.update(self.box_wh(site, cap))
        return box

    def dine_count(self, kind):
        """Built and planned items of a kind inside dining zones (seats() counts the built pairs). cx: each item once
        — two dining zones over the same tables (cup probe std MY1-4: zone 39 5x3 inside zone 57 17x3) counted 4 of
        the chairs twice, so 11 "chairs" stood for 7 and the 5 free chairs in stock were never placed (11 tables,
        8 chairs at the horizon, LackTables). The observation's furniture[].zone_ids give the unique count; a
        fixture without them keeps the zones' sum."""
        dine = {z.get("id") for z in self.zone("dining") if z.get("id") is not None}
        items = [f for f in map(d, lst(self.o.get("furniture"))) if f.get("kind") == kind and f.get("zone_ids")]
        if dine and items:
            return sum(1 for f in items if any(i in dine for i in lst(f.get("zone_ids"))))
        n = 0
        for z in self.zone("dining"):
            n += (d(z.get("furniture")).get(kind) or 0) + (d(z.get("furniture_planned")).get(kind) or 0)
        return n

    def stray(self, kind):
        """Built tables/chairs outside every zone that uses them (dining; an office for a chair): items the stock
        counts that seat nobody until a zone box reaches them (b796327 OP1-4: 10 tables, 13 chairs to H)."""
        types = {z.get("id"): str(z.get("type")).lower() for z in self.zones}
        uses = ("dining", "office") if kind == "chair" else ("dining",)
        n = 0
        for f in lst(self.o.get("furniture")):
            f = d(f)
            if f.get("kind") == kind and f.get("built")\
                    and not any(u in types.get(i, "") for i in lst(f.get("zone_ids")) for u in uses):
                n += 1
        return n

    def placeable(self, s):
        """A site place_furniture takes: an A site, or a dug R room with no farm plot (facts/sites.py USED_BY)."""
        if not self._ints(s) or not self.dry(s.get("z")) or s.get("id") in self.plot_rooms:
            return False
        if s.get("kind") == "A":
            return True
        return s.get("kind") == "R" and bool(s.get("dug")) and "farm" not in str(s.get("used_by") or "").lower()

    def zoneable(self, s):
        """A site make_zone takes: an A site, or a dug R room no plot and no zone stands on."""
        return self.placeable(s) and (s.get("kind") == "A" or s.get("free", True))

    def seat_boxes(self):
        """Boxes a table and its chair can be placed into AND that a dining zone covers or can be made over (so the
        pair is a seat at H), in order: a dining zone whose corner is a placeable site's (the zone's own box); the
        dug people rooms (house/dine/dorm) as dug; every dry A box with floor, a wide one by its ZONE_MAX corner box;
        other dug free R rooms. A box over a farm room still waiting for its plot is left out (farm_claimed)."""
        out, seen = [], set()

        def add(s, w, h, zoned):
            w, h = max(1, min(w, ZONE_MAX)), max(1, min(h, ZONE_MAX))
            bid = "%s:%dx%d" % (s["id"], w, h)
            box = {"id": bid, "site": s["id"], "x": s["x"], "y": s["y"], "z": s["z"], "w": w, "h": h,
                   "zoned": zoned, "open_tiles": s.get("open_tiles")}
            if bid in seen or (not zoned and self.farm_claimed(box)):
                return
            seen.add(bid)
            out.append(box)

        for zn in self.zone("dining"):
            if not self._ints(zn, ("x", "y", "z", "w", "h")):
                continue
            for s in self.sites:
                if s.get("kind") in ("A", "R") and self.placeable(s)\
                        and (s.get("x"), s.get("y"), s.get("z")) == (zn["x"], zn["y"], zn["z"]):
                    add(s, zn["w"], zn["h"], True)
                    break
        for r in self.kind("R"):
            if self.roles.get(r.get("id")) in ("house", "dine", "dorm") and self.zoneable(r):
                b = self.site_box(r, ZONE_MAX)
                add(r, b["w"], b["h"], False)
        for a in sorted(self.closed_a(), key=lambda s: -(s.get("open_tiles") or 0)):
            if self.zoneable(a) and (a.get("open_tiles") or 0) >= OVERFLOW_MIN_TILES:
                add(a, a.get("w") or 1, a.get("h") or 1, False)
        for r in self.kind("R"):
            if r.get("id") not in self.roles and self.zoneable(r):
                b = self.site_box(r, ZONE_MAX)
                add(r, b["w"], b["h"], False)
        return out

    def seat_spread(self, want, used_t=0, used_c=0, half=None):
        """cx housing boxes (2): while dining seats (tables and chairs inside dining zones) are short of `want` and
        free pairs wait, place the pairs into the first seat box with floor and zone that same box a dining hall —
        one box a pass (a refused box rests SURGE_BED_RETRY_DAYS unless its floor grew). `used_*` = the items the
        dine room took this pass. A pass that knocks only on full boxes marks house_full_day (house_floor digs)."""
        need = want - self.seats() - min(used_t, used_c)
        n = min(need, (self.free.get("table") or 0) - used_t, (self.free.get("chair") or 0) - used_c, 15)
        if n <= 0:
            return
        today = self.obs_day()
        tried = 0
        boxes = self.shaft_seats(self.seat_boxes())
        if not boxes:



            if self.seat_nobox_day != today:
                log("seat_no_box", day=self.day, need=n, seats=self.seats(), want=want)
            self.seat_nobox_day = today
            return
        for b in boxes:
            mark = self.seat_full.get(b["id"])
            if mark is not None:
                day, tiles = mark
                grown = isinstance(b.get("open_tiles"), int) and isinstance(tiles, int) and b["open_tiles"] > tiles
                if isinstance(today, (int, float)) and isinstance(day, (int, float))\
                        and today - day < SURGE_BED_RETRY_DAYS and not grown:
                    continue
            where = {"site": b["site"], "w": b["w"], "h": b["h"]}
            rt = self.act("seat_t_" + b["id"], "place_furniture", {"kind": "table", **where, "count": n},
                          retry=1, limit=99)
            if rt is None:
                continue
            tried += 1
            tp = (d(rt.get("result")).get("at") or []) if rt.get("ok") else []
            if tp and not isinstance(tp[0], list):
                tp = [tp]
            if not tp:
                self.seat_full[b["id"]] = (today, b.get("open_tiles"))
                continue
            rc = self.act("seat_c_" + b["id"], "place_furniture", {"kind": "chair", **where, "count": len(tp)},
                          retry=1, limit=99)
            cp = (d(rc.get("result")).get("at") or []) if (rc and rc.get("ok")) else []
            if cp and not isinstance(cp[0], list):
                cp = [cp]
            if len(cp) < len(tp):
                self.seat_full[b["id"]] = (today, b.get("open_tiles"))
            placed = [{"kind": "table", "x": x, "y": y, "z": z} for x, y, z in tp]\
                + [{"kind": "chair", "x": x, "y": y, "z": z} for x, y, z in cp]
            if not b["zoned"] and self.needs_zone(b, self.zone("dining"), ("table", "chair"), placed):
                rz = self.act("seat_z_" + b["id"], "make_zone", {"kind": "dining_hall", **where}, retry=2, limit=4)
                if rz and rz.get("ok"):
                    self.done.add("seat_z_" + b["id"])
                    self.new_zones.append({"type": "DiningHall", **{k: b[k] for k in ("x", "y", "z", "w", "h")}})
            log("seat_spread", day=self.day, box=b["id"], tables=len(tp), chairs=len(cp), seats=self.seats(),
                want=want)
            return
        if tried:
            if half is None or self.seats() < half:
                self.house_full_day = today
            else:

                self.seat_refused_day = today

    def shaft_seats(self, boxes):
        """cx shaft people: seat_boxes on a fort with an open shaft — each box near a shaft column cut to its far
        corner box (far_cut: off the sleepers and the plots) first, the boxes that stay near after them, and those
        only once shaft_wait is over. Other forts: unchanged."""
        if not self.shaft_people():
            return boxes
        avoid = [z for z in self.zones if any(k in str(z.get("type")).lower() for k in ("dormitory", "bedroom"))]
        avoid += [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
                  if isinstance(f, dict) and f.get("kind") == "bed" and self._ints(f)]
        far, near, seen = [], [], set()
        for b in boxes:
            if not self.shaft_near(b):
                if b["id"] not in seen:
                    seen.add(b["id"])
                    far.append(b)
                continue
            site = next((x for x in self.sites if isinstance(x, dict) and x.get("id") == b.get("site")), None)
            floor = self.site_floor(site) if isinstance(site, dict) and site.get("kind") == "A" else None
            if isinstance(site, dict) and site.get("kind") == "A" and floor is None:
                near.append(b)
                continue
            cut = self.far_cut(dict(b, id=b.get("site")), avoid, SHAFT_PEOPLE_MIN_TILES, floor=floor)
            if cut is not None:
                w, h = cut
                bid = "%s:%dx%d" % (b["site"], w, h)
                if bid not in seen:
                    seen.add(bid)
                    zoned = any(self._ints(z, ("x", "y", "z", "w", "h"))
                                and (z["x"], z["y"], z["z"], z["w"], z["h"]) == (b["x"], b["y"], b["z"], w, h)
                                for z in self.zone("dining"))
                    far.append(dict(b, id=bid, w=w, h=h, zoned=zoned))
            else:
                near.append(b)
        return far + near

    def zone_loose(self, handled=()):
        """cx housing boxes (2): built tables/chairs outside any dining zone, and beds outside any dormitory or
        bedroom, on a level `handled` (rezone's whole-site zones) left out — a zone box from a zoneable site's corner
        (make_zone's ZONE_MAX gate) covering the most of them: seat pairs for a dining hall, beds for a dormitory."""
        types = {z.get("id"): str(z.get("type")).lower() for z in self.zones}
        fresh = [z for z in self.new_zones if self._ints(z, ("x", "y", "z", "w", "h"))]
        for kinds, words, zkind, key in ((("table", "chair"), ("dining",), "dining_hall", "lz_dine_"),
                                         (("bed",), ("dorm", "bedroom"), "dormitory", "lz_dorm_")):
            by_z = {}
            for f in lst(self.o.get("furniture")):
                f = d(f)
                if not f.get("built") or f.get("kind") not in kinds or not self._ints(f):
                    continue
                if any(w in types.get(i, "") for i in lst(f.get("zone_ids")) for w in words):
                    continue
                if (key, f["z"]) in handled:
                    continue
                if any(covers(z, f) for z in fresh if any(w in str(z.get("type")).lower() for w in words)):
                    continue
                by_z.setdefault(f["z"], []).append(f)
            for z, items in by_z.items():
                best = None
                for s in self.sites:
                    if s.get("kind") not in ("A", "R") or s.get("z") != z or not self.zoneable(s):
                        continue
                    inside = [f for f in items if s["x"] <= f["x"] < s["x"] + ZONE_MAX
                              and s["y"] <= f["y"] < s["y"] + ZONE_MAX]
                    if kinds == ("bed",):
                        score = len(inside)
                    else:
                        score = min(sum(1 for f in inside if f["kind"] == "table"),
                                    sum(1 for f in inside if f["kind"] == "chair"))
                    if score <= 0:
                        continue
                    w = max(f["x"] for f in inside) - s["x"] + 1
                    h = max(f["y"] for f in inside) - s["y"] + 1
                    box = {"id": "%s:lz" % s["id"], "x": s["x"], "y": s["y"], "z": z, "w": w, "h": h}
                    if self.farm_claimed(box):
                        continue
                    cand = (score, -(w * h), s["id"], w, h)
                    if best is None or cand[:2] > best[:2]:
                        best = cand
                if best is not None:
                    _, _, sid, w, h = best
                    k = "%s%s_%dx%d" % (key, sid, w, h)
                    r = self.act(k, "make_zone", {"kind": zkind, "site": sid, "w": w, "h": h}, retry=2, limit=3)
                    if r and r.get("ok"):
                        self.done.add(k)

    def house_waiting(self, full=False):
        """(beds wait, seats wait): free beds while placed beds are under cit + 2; free table+chair pairs while
        dining seats are under half the census + 1 (furnish's own targets) — with `full`, under seats_full() too
        (cx seats spread for all: house_floor's spare-room dig and the seat shaft; the farm order keeps half)."""
        beds = (self.free.get("bed") or 0) > 0 and self.placed_dry("bed") < self.cit + 2
        goal = math.ceil(self.cit / 2) + 1
        if full:
            goal = max(goal, self.seats_full())
        seats = min(self.free.get("table") or 0, self.free.get("chair") or 0) > 0 and self.seats() < goal
        return beds, seats

    def farms_met(self):
        """cx seats spread for all: the farm rooms the plot target asks for are dug or standing (management's own
        count), so a spare R room dug for seats past half the census never takes a farm room's place."""
        try:
            farms = len(lst(self.o.get("farm_plots"))) + sum(
                1 for r, v in self.roles.items() if v == "farm"
                and not any(z.get("id") == r and z.get("used_by") for z in self.kind("R")))
            return farms >= self.farm_target()
        except Exception as e:
            log("farms_met_error", error=repr(e)[:200])
            return False

    def house_blocked(self, full=False):
        """Open play (no surge, no hands-off window): free beds or seat pairs wait and the last placement pass that
        found no box with floor (house_full_day) is at most HOUSE_FULL_DAYS old."""
        if self.surge or self.hands_off is not None:
            return False
        today, day = self.obs_day(), self.house_full_day
        for mark in ((self.seat_nobox_day, self.seat_refused_day) if full else ()):
            if isinstance(mark, (int, float)) and (not isinstance(day, (int, float)) or mark > day):
                day = mark
        if day is None or not isinstance(today, (int, float)) or today - day > HOUSE_FULL_DAYS:
            return False
        return any(self.house_waiting(full))

    def house_floor(self, pending):
        """cx housing boxes (3): open play (not the surge, which has its own floor digs; no hands-off window) — free
        beds or seat pairs wait while beds or dining seats are short and the last placement pass found no box with
        floor (house_full_day within HOUSE_FULL_DAYS): dig a HOUSE_ROOM people room on a spare R site, or, with none
        listed, a new shaft one level under the deepest dug level so its stair lists fresh R sites (surge_floor's
        stair step). Waits while a room's worth of designations is still pending."""
        if not self.house_blocked(full=True) or self.breach:
            return
        beds_wait, seats_wait = self.house_waiting(full=True)
        if not isinstance(pending, int) or isinstance(pending, bool) or pending >= HOUSE_PENDING_MAX:
            return
        spare = [r for r in self.undug_rooms() if r["id"] not in self.roles and self.dry(r.get("z"))
                 and not self.room_taken(r)
                 and not self.farm_claimed(dict(r, w=HOUSE_ROOM[0], h=HOUSE_ROOM[1]))]
        if not any(self.house_waiting()) and not self.farms_met():


            spare = [r for r in spare if not r.get("soil")]
        r = self.pick_dig_site(spare) if spare else None
        if r is not None:
            box = {"site": r["id"], "w": HOUSE_ROOM[0], "h": HOUSE_ROOM[1]}
            res = self.act("dig_house_" + str(r["id"]), "dig_room", box, retry=3, limit=2)
            if res and res.get("ok"):
                self.roles[r["id"]] = "house"
                self.note_room_box(r, box)
                log("house_floor_dig", day=self.day, site=r["id"], beds_wait=beds_wait, seats_wait=seats_wait)
            return
        if self.house_blocked():


            self.floor_stair("stairs_house", "house_floor_stair")
        elif seats_wait and self.seat_shaft_due()\
                and not any(self.roles.get(x["id"]) == "house" and not x.get("dug") for x in self.kind("R")):





            self.shelter_shaft(why="seats")

    def seat_shaft_due(self):
        """cx seat shaft: the last seat pass found no seat box at all within HOUSE_FULL_DAYS."""
        today, mark = self.obs_day(), self.seat_nobox_day
        return isinstance(today, (int, float)) and isinstance(mark, (int, float)) and today - mark <= HOUSE_FULL_DAYS


    def note_dig_batch(self, key, tool, args):
        """Record one of the layer's dig acts as a batch of tiles (dig_room: the site's box with the act's w/h;
        dig_stairs: the S site's column down to z_bottom)."""
        site = next((x for x in self.sites if x.get("id") == args.get("site")), None)
        if site is None or not self._ints(site, ("x", "y", "z")):
            return
        x0, y0, z0 = site["x"], site["y"], site["z"]
        if tool == "dig_room":
            w = args.get("w") or site.get("w") or 3
            h = args.get("h") or site.get("h") or 3
            tiles = {(x, y, z0) for x in range(x0, x0 + w) for y in range(y0, y0 + h)}
        else:
            zb = args.get("z_bottom") if isinstance(args.get("z_bottom"), int) else z0 - 1
            tiles = {(x0, y0, z) for z in range(zb, z0 + 1)}
        bid = "%s:%s:%s" % (key, args.get("site"), self.day)
        self.dig_batches.append({"id": bid, "key": key, "day": self.day, "tiles": tiles, "paused": False})

    def batch_pending(self, b):
        """The batch's tiles still designated (a map query over its box, at most once a game day; tiles near a
        "Dangerous terrain" cancel left out), or None when unread."""
        seen = self.batch_seen.get(b["id"])
        if seen is not None and seen[0] == self.day:
            return seen[1]
        tiles = {t for t in b["tiles"] if not any(u[2] == t[2] and abs(u[0] - t[0]) <= DIG_UNSAFE_RADIUS
                                                   and abs(u[1] - t[1]) <= DIG_UNSAFE_RADIUS for u in self.dig_unsafe)}
        if not tiles:
            self.batch_seen[b["id"]] = (self.day, 0)
            return 0
        xs, ys, zs = [t[0] for t in tiles], [t[1] for t in tiles], [t[2] for t in tiles]
        cx, cy = (min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2
        radius = min(20, max(max(xs) - cx, cx - min(xs), max(ys) - cy, cy - min(ys)) + 1)
        z_hi = max(zs)
        z_lo = max(min(zs), z_hi - 4)
        try:
            res = query_result(self.game.query("map", x=cx, y=cy, z=z_hi, z2=z_lo, radius=radius))
        except Exception as e:
            log("carp_batch_query_error", error=repr(e)[:160])
            res = None
        if not isinstance(res, dict) or not isinstance(res.get("designations"), list):
            self.batch_seen[b["id"]] = (self.day, None)
            return None
        des = {(q.get("x"), q.get("y"), q.get("z")) for q in map(d, res["designations"])}
        n = len({t for t in tiles if z_lo <= t[2] <= z_hi} & des)
        self.batch_seen[b["id"]] = (self.day, n)
        return n

    def mine_citizen(self):
        """(id, job) of the fort's one MINE citizen (units query: labors), or None with none or several."""
        try:
            res = query_result(self.game.query("units", kind="citizens", limit=300))
        except Exception as e:
            log("carp_units_error", error=repr(e)[:160])
            return None
        mine = [d(u) for u in lst(d(res).get("units")) if "MINE" in {str(x).upper() for x in lst(d(u).get("labors"))}]
        if len(mine) != 1:
            return None
        return mine[0].get("id"), str(mine[0].get("job") or "")

    def barrels_pausable(self):
        """(bool, reason): barrels may pause only at BARREL_SAFE_FLOOR+ empty and no recent want-of-barrel brew cancel."""
        empty = self.st.get("barrels_empty")
        if not isinstance(empty, int) or isinstance(empty, bool) or empty < BARREL_SAFE_FLOOR:
            return False, "empty_barrels_%s_below_%d" % (empty, BARREL_SAFE_FLOOR)
        if isinstance(self.brew_cancel_day, (int, float)) and isinstance(self.day, (int, float))\
                and self.day - self.brew_cancel_day <= BREW_CANCEL_LOOKBACK_DAYS:
            return False, "brew_cancel_d%s" % self.brew_cancel_day
        return True, "empty_barrels_%d" % empty

    def carp_paused_order(self, key, tool, args):
        """An add of the layer's own that the active pause holds (re-adds by the pause itself pass)."""
        p = getattr(self, "carp_pause", None)
        if p is None or key.startswith("carp_") or tool not in ("add_order", "add_manager_order"):
            return False
        recipe, job = args.get("recipe"), args.get("job")
        if recipe in CARP_PAUSE_RECIPES or job in ("MakeCrafts", "ConstructBed", "ConstructTable", "ConstructThrone"):
            return True
        return bool(p.get("barrels")) and (recipe == "make_barrel" or job == "MakeBarrel")

    def carp_pause_step(self):
        if not isinstance(self.day, (int, float)):
            return
        for t in lst(self.o.get("recent_cancellations")):
            if "Brew" in str(t) and "Needs empty food storage item" in str(t):
                self.brew_cancel_day = self.day
        p = self.carp_pause
        if p is not None:
            b = next((x for x in self.dig_batches if x["id"] == p["batch"]), None)
            n = self.batch_pending(b) if b is not None else 0
            if p.get("barrels"):
                ok, why = self.barrels_pausable()
                if not ok:
                    self.carp_resume(p, kinds=("MakeBarrel",), why="barrels:" + why)
            if n == 0:
                self.carp_resume(p, why="batch_clear")
            elif self.day - p["day"] >= CARP_PAUSE_MAX_DAYS:
                self.carp_resume(p, why="cap_%d_days" % CARP_PAUSE_MAX_DAYS)
                self.carp_capped_day = self.day
            return
        if d(self.o.get("burrows")).get("civilian_alert") is True or self.breach:
            return
        if isinstance(self.carp_capped_day, (int, float)) and self.day - self.carp_capped_day < CARP_PAUSE_COOLDOWN_DAYS:
            return
        waiting = [b for b in self.dig_batches if not b["paused"] and self.day - b["day"] >= CARP_PAUSE_WAIT_DAYS]
        if not waiting:
            return
        live = []
        for b in waiting:
            n = self.batch_pending(b)
            if n == 0:
                self.dig_batches.remove(b)
            elif n:
                live.append((b, n))
        if not live:
            return
        miner = self.mine_citizen()
        if miner is None or miner[1] not in CARP_MINER_JOBS:
            return
        b, n = live[0]
        b["paused"] = True
        barrels, bwhy = self.barrels_pausable()
        jobs = dict(CARP_PAUSE_JOBS, **({"MakeBarrel": "make_barrel"} if barrels else {}))
        saved = []
        for o in self.orders:
            oid = o.get("id")
            if oid not in self.owned or o.get("job") not in jobs:
                continue
            r = self.act("carp_pause_%s" % oid, "cancel_order", {"order_id": oid}, retry=0.25, limit=4)
            if r and r.get("ok"):
                saved.append({"id": oid, "job": o.get("job"), "left": o.get("left"), "src": self.order_src.get(oid),
                              "recipe": o.get("recipe") or jobs.get(o.get("job")), "repeat": o.get("repeat"),
                              "mat": o.get("material_category")})
                self.owned.discard(oid)
        self.carp_pause = {"day": self.day, "batch": b["id"], "saved": saved, "barrels": barrels}
        log("carp_pause", day=self.day, batch=b["id"], batch_key=b["key"], batch_day=b["day"], pending=n,
            miner=miner[0], miner_job=miner[1], cancelled=[(x["id"], x["job"], x["left"]) for x in saved],
            barrels=barrels, barrels_why=bwhy)

    def carp_resume(self, p, kinds=None, why=""):
        """Re-add the paused orders (all, or only `kinds` jobs) as the layer first added them (one-shots with what
        was left), and end the pause when nothing is held any more."""
        keep, back = [], []
        for x in p["saved"]:
            if kinds is not None and x["job"] not in kinds:
                keep.append(x)
                continue
            src = x.get("src")
            if src is not None:
                key0, tool, args = src
                args = dict(args)
                if not args.get("repeat") and isinstance(x.get("left"), int) and x["left"] > 0:
                    args["amount"] = min(30, x["left"])
            elif x.get("recipe"):
                key0, tool, args = None, "add_order", {"recipe": x["recipe"], "amount": max(1, min(30, x.get("left") or 1))}
            elif x.get("job"):

                key0, tool, args = None, "add_manager_order", {"job": x["job"], "amount": max(1, min(30, x.get("left") or 1)),
                                                               **({"material_category": x["mat"]} if x.get("mat") else {})}
            else:
                continue
            r = self.act("carp_resume_%s" % x["id"], tool, args, retry=0.25, limit=4)
            if r and r.get("ok"):
                res = r.get("result") if isinstance(r.get("result"), dict) else r
                if key0 and res.get("order_id") is not None:
                    self.key_order[key0] = res.get("order_id")
                    self.order_src[res.get("order_id")] = (key0, tool, args)
                back.append((x["id"], x["job"], args.get("amount")))
            else:
                keep.append(x)
        if kinds is not None:
            p["barrels"] = False
            p["saved"] = keep
            log("carp_resume", day=self.day, why=why, batch=p["batch"], readded=back, partial=True)
            return
        self.carp_pause = None
        log("carp_resume", day=self.day, why=why, batch=p["batch"], readded=back, failed=[x["id"] for x in keep],
            paused_days=round(self.day - p["day"], 2))

    def pending_at(self, z):
        """cx stair wait: dig designations still standing on level z (observation dig_pending_by_z; 0 unread)."""
        v = d(self.o.get("dig_pending_by_z")).get(str(z))
        return v if isinstance(v, int) and not isinstance(v, bool) else 0

    def floor_stair(self, key, kind):
        """A new shaft from a listed S site to one level under the deepest dry dug level, on a column clear of every
        dug A box, so the new level's stair lists fresh R sites (surge_floor's stair step; see its comments)."""
        if self.surface is None:
            return
        zs = [a.get("z") for a in self.kind("A") if self.dry(a.get("z")) and isinstance(a.get("z"), int)]
        if not zs:
            return
        zb = min(zs) - 1
        last = self.last.get(key)
        if last is not None and self.now - last < SURGE_FLOOR_STAIR_DAYS * DAY:
            return
        sent = self.floor_stair_sent.get(key)
        capped = False
        if sent is not None and sent[1] == zb and self.pending_at(zb) > 0 and len(sent) > 3 and not sent[3]\
                and isinstance(self.day, (int, float)) and isinstance(sent[2], (int, float))\
                and self.day - sent[2] >= STAIR_WAIT_CAP_DAYS:


            capped = True
            log("floor_stair_wait_cap", day=self.day, key=key, site=sent[0], z_bottom=zb, since=sent[2])
        if sent is not None and sent[1] == zb and self.pending_at(zb) > 0 and not capped:



            if self.may("floor_stair_wait_log_" + key, 7, 10 ** 6):
                self.last["floor_stair_wait_log_" + key] = self.now
                log("floor_stair_wait", day=self.day, key=key, site=sent[0], z_bottom=zb, pending=self.pending_at(zb))
            return
        cands = [s for s in self.kind("S") if all(isinstance(s.get(k), int) for k in ("x", "y", "z"))
                 and 0 < s["z"] - zb <= 20 and not self.column_dug(s, zb + 1, s["z"] - 1)]
        site = self.pick_dig_site(cands, levels=2) if cands else None
        if site is None:
            return
        res = self.act(key, "dig_stairs", {"site": site["id"], "z_bottom": zb}, retry=SURGE_FLOOR_STAIR_DAYS, limit=3)
        if res is None:
            return
        if res.get("ok"):

            self.floor_stair_sent[key] = (site.get("id"), zb, self.day, capped or bool(
                sent is not None and sent[1] == zb and len(sent) > 3 and sent[3]))
        log(kind, day=self.day, site=site.get("id"), z_bottom=zb, ok=res.get("ok"), free=self.surge_floor_free())






    def stressed(self):
        """The citizens in the score's stressed band that this layer has not housed yet: stress category
        <= STRESS_CATEGORY, no bedroom zone owned (re-read from the zones' owners, so a restart re-derives it),
        and not in this run's assigned record."""
        owned = {z.get("owner") for z in self.zone("bedroom") if z.get("owner") is not None} | self.stress_done
        out = []
        for p in self.people:
            s = p.get("stress")
            if p.get("id") is None or not isinstance(s, int) or isinstance(s, bool):
                continue
            if p["id"] in owned:
                continue


            seen = self.stress_seen.get(p["id"])
            if s <= STRESS_CATEGORY or (s <= STRESS_RISE_CATEGORY and seen is not None and seen > s):
                out.append(p)
        out.sort(key=lambda p: p.get("stress") or 0)
        return out

    def zone_of(self, word, owner):
        return next((z.get("id") for z in self.zone(word) if z.get("owner") == owner), None)

    def farm_claimed(self, s):
        """cx: whether a site shares a tile with a farm-role R room (other than itself) that holds no farm plot yet.
        A zone there makes the room read used_by and build_farm answers "room is already used" (hint hard LT01-0 on
        82d1ec1: R1, the fort's only soil room, went to Dormitory 18 by day 8 and no plot was ever built on it).
        A room whose plot stands is the plot's own; a site without coordinates claims nothing."""
        plots = [p for p in lst(self.o.get("farm_plots")) if isinstance(p, dict)]
        for r in self.kind("R"):
            if r.get("id") == s.get("id") or not str(self.roles.get(r.get("id")) or "").startswith("farm"):
                continue
            if any(self.rects_overlap(r, p) for p in plots):
                continue
            if BED_HELD_BOX and r.get("id") in (getattr(self, "bed_held", None) or ()) and lst(r.get("used_by")):
                continue
            if self.rects_overlap(r, s):
                return True
        return False

    @staticmethod
    def rects_overlap(a, b):
        """Whether two x,y,z,w,h boxes share a tile: a 3x3 private bedroom inside a big room does not contain the
        room, so covers() alone would offer the room again and pile a second zone onto the first."""
        v = [a.get(k) for k in ("x", "y", "z")] + [b.get(k) for k in ("x", "y", "z")]\
            + [(a.get("w"), a.get("h"), b.get("w"), b.get("h"))]
        nums = [x for t in v for x in (t if isinstance(t, tuple) else (t,))]
        if any(not isinstance(n, (int, float)) or isinstance(n, bool) for n in nums):
            return False
        return (a["z"] == b["z"] and a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
                and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])

    def grazer_cull(self):
        """cx grazer cull (GRAZER_* above): a tame, unowned grazer standing below the surface (no grass there, and no
        tool zones a pasture) is marked for slaughter before it starves where the idle citizens gather — at most
        GRAZER_CULL_PER_PASS a pass, once a game day. Owned pets are never taken; nothing waits on the food alarm or
        the meat window (the corpse, not the meat, is the reason)."""
        if not self.may("grazer_cull", 1, 10 ** 6):
            return
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        surface = self.surface if num(getattr(self, "surface", None)) else d(self.map).get("surface_z")
        if not num(surface):
            return
        self.last["grazer_cull"] = self.now
        try:
            q = query_result(self.game.query("units", kind="animals"))
        except Exception as e:
            log("grazer_query_error", error=repr(e)[:160])
            return
        cand = []
        for a in map(d, lst(d(q).get("units") or d(q).get("animals"))):
            if not a.get("tame") or a.get("pet_owner_id") not in (None, -1) or a.get("marked_for_slaughter"):
                continue
            if not grazer_race(a.get("race")) or not num(a.get("z")) or a["z"] >= surface:
                continue
            cand.append(a)
        if not cand:
            return
        if not self.butchers_ready():
            self.build("Butchers", key=self.butcher_key())
        cand.sort(key=lambda a: (not a.get("adult"), a.get("id") or 0))
        marked = []
        for a in cand[:GRAZER_CULL_PER_PASS]:
            r = self.act("grazer_cull_%s" % a.get("id"), "slaughter", {"unit_id": a.get("id")}, retry=1, limit=3)
            if r and r.get("ok"):
                marked.append(a.get("id"))
        if marked:
            log("grazer_cull", day=self.day, marked=marked, races=sorted({str(a.get("race")) for a in cand}),
                below=len(cand), surface=surface)

    def stray_attacks(self, obs):
        """cx stray cull: the stray animal names in this observation's combat reports where the stray strikes a
        citizen ("The stray guineahen snatches at the carpenter ..."), each report text counted once per run."""
        obs = d(obs)
        profs = {str(p.get("profession") or "").lower() for p in lst(obs.get("dwarves")) if isinstance(p, dict)}
        profs = {p for p in profs if p} | CITIZEN_WORDS
        seen = self.__dict__.setdefault("stray_seen", set())
        out = []
        for t in lst(obs.get("recent_events")):
            t = str(t)
            m = COMBAT_RE.match(t.lower().strip())
            if not m or t in seen:
                continue
            a, b = m.group(1).strip(), m.group(2).strip()
            if a.startswith("stray ") and citizen_noun(b, profs):
                seen.add(t)
                out.append((a[len("stray "):], t))
        return out

    def stray_cull(self):
        """cx stray cull (STRAY_CULL above): every unowned tame animal of the species, sex and age a fresh report
        shows striking a citizen is marked for slaughter (STRAY_CULL_PER_PASS a pass; the rest on later passes),
        and a Butchers is built when none can take it."""
        if not STRAY_CULL:
            return
        pend = self.__dict__.setdefault("stray_pending", [])
        for name, text in self.stray_attacks(self.o):
            spec = stray_spec(name)
            if spec[0] is None:
                continue
            if spec not in pend:
                pend.append(spec)
            log("stray_attack", day=self.day, name=name, race=spec[0], text=text[:160])
        if not pend:
            return
        if not self.butchers_ready():
            self.build("Butchers", key=self.butcher_key())
        try:
            q = query_result(self.game.query("units", kind="animals"))
        except Exception as e:
            log("stray_query_error", error=repr(e)[:160])
            return
        marked, left = [], []
        animals = [d(a) for a in lst(d(q).get("units") or d(q).get("animals"))]
        for race, female, adult in pend:
            cand = [a for a in animals if a.get("tame") and a.get("pet_owner_id") in (None, -1)
                    and not a.get("marked_for_slaughter") and a.get("id") not in marked
                    and race in str(a.get("race") or "").upper().split("_")
                    and (female is None or a.get("female") is None or bool(a.get("female")) == female)
                    and (adult is None or a.get("adult") is None or bool(a.get("adult")) == adult)]
            for a in cand:
                if len(marked) >= STRAY_CULL_PER_PASS:
                    left.append((race, female, adult))
                    break
                r = self.act("stray_cull_%s" % a.get("id"), "slaughter", {"unit_id": a.get("id")}, retry=1, limit=3)
                if r and r.get("ok"):
                    marked.append(a.get("id"))
        pend[:] = list(dict.fromkeys(left))
        if marked:
            log("stray_cull", day=self.day, marked=marked)

    def stress_site(self, meeting=False):
        """Where the next private room goes: a dug R room no role claims, no zone covers and no bedroom claims a
        corner of, else an uncovered A site the zone tool's own gate accepts (area_fits, ROOT_CAUSES §I) with room
        for the 3x3. Reserved sites never come back (one room per dwarf, one dwarf per room). cx room claim: on a
        shaft fort a private room (meeting=False) never lies under a box the far meeting / dining pickers take
        (people_boxes); the meeting area's own pick (meeting=True) keeps the old rule."""
        zapped = lambda s: any(covers(z, s) or self.rects_overlap(z, s) for z in self.zones)
        people = [] if meeting else self.people_boxes()
        roles = (None, "stress", "bedroom", "meeting") if meeting else (None, "stress", "bedroom")
        mine = [r for r in self.dug_rooms() if meeting and self.roles.get(r["id"]) == "meeting"]
        room = next((r for r in mine + self.dug_rooms() if r["id"] not in self.stress_rooms
                     and self.roles.get(r["id"]) in roles and not zapped(r)
                     and self.dry(r.get("z")) and not self.room_near_shaft(r)
                     and not self.under_people(dict(r, w=r.get("w") or 3, h=r.get("h") or 3), people)), None)
        if room:
            return room
        return next((s for s in self.closed_a() if s.get("id") not in self.stress_rooms and self.dry(s.get("z"))
                     and self.area_fits(s, ZONE_MAX) and (s.get("open_tiles") or 0) >= STRESS_ROOM_SIZE ** 2
                     and not zapped(s) and not self.farm_claimed(s) and not self.room_near_shaft(s)
                     and (meeting or not self.under_people(dict(s, w=STRESS_ROOM_SIZE, h=STRESS_ROOM_SIZE),
                                                             people))
                     and self.corner_floor(s)), None)

    def stress_corner_site(self):
        """cx stress corner (STRESS_CORNER above): the stressed citizen's private room when stress_site() has nothing
        and no room is left to dig — a copy of a closed A site carrying the zone's w/h (make_zone lays it from the
        site's corner) and `_bed`: the smallest box from the site's corner to a standing bed that holds that bed and
        no other furniture. DF gives a bed to the newest bedroom zone over it (pbfx1/pbfx2), so the citizen owns that
        one bed and no other bed is taken or placed; the bed's own dorm / dining / office zones stay as they are. The
        box keeps clear of every bedroom zone and meeting area, of the meeting / dining far boxes (people_boxes,
        b6927c2) and of an open shaft (MEETING_SHAFT_TILES); dry; never a site reserved before."""
        people = self.people_boxes()
        num = lambda v: isinstance(v, int) and not isinstance(v, bool)
        stuff = [dict(f, w=1, h=1) for f in lst(self.o.get("furniture"))
                 if isinstance(f, dict) and f.get("kind") != "hatch" and all(num(f.get(k)) for k in ("x", "y", "z"))]
        keep_off = [z for z in self.zone("bedroom") + self.zone("meeting")
                    if all(num(z.get(k)) for k in ("x", "y", "z", "w", "h"))]
        best = None
        for s in self.closed_a():
            if s.get("id") in self.stress_rooms or s.get("id") in self.zone_banned or not self.dry(s.get("z"))\
                    or not all(num(s.get(k)) for k in ("x", "y", "z", "w", "h")):
                continue
            ax, ay, az = s["x"], s["y"], s["z"]
            for f in stuff:
                if f.get("kind") != "bed" or f["z"] != az or not (ax <= f["x"] < ax + min(s["w"], ZONE_MAX)
                                                                   and ay <= f["y"] < ay + min(s["h"], ZONE_MAX)):
                    continue
                box = {"x": ax, "y": ay, "z": az, "w": f["x"] - ax + 1, "h": f["y"] - ay + 1}
                if sum(1 for g in stuff if self.rects_overlap(g, box)) != 1\
                        or any(self.rects_overlap(z, box) for z in keep_off) or self.under_people(box, people)\
                        or self.shaft_near(box):
                    continue
                key = (box["w"] * box["h"], f["y"], f["x"])
                if best is None or key < best[0]:
                    best = (key, dict(s, w=box["w"], h=box["h"], _bed=True))
        return best[1] if best else None

    def corner_floor(self, s):
        """cx confirmed floor: an A site's private-room corner (STRESS_ROOM_SIZE square, the bedroom zone's and its
        bed's box) shows free floor on the map and has not answered "no free floor tile" since its site changed."""
        if s.get("kind") != "A":
            return True
        if self.floor_refused(s.get("id"), STRESS_ROOM_SIZE, STRESS_ROOM_SIZE):
            return False
        w, h = s.get("w"), s.get("h")
        if isinstance(w, int) and isinstance(h, int) and (s.get("open_tiles") or 0) >= w * h:
            return True
        tiles = self.site_floor(s)
        return tiles is not None and self.floor_in(tiles, {"x": s["x"], "y": s["y"], "w": STRESS_ROOM_SIZE,
                                                           "h": STRESS_ROOM_SIZE}) >= 1

    def room_near_shaft(self, s):
        """cx shaft people: a private room's 3x3 box (the site's corner) closer than MEETING_SHAFT_TILES to an open
        shaft column — beds stand far from the shaft's foot like the dormitory's (d57f599). Off a shaft fort: False."""
        if not self.shaft_people():
            return False
        box = {k: s.get(k) for k in ("x", "y", "z")}
        box.update(w=STRESS_ROOM_SIZE, h=STRESS_ROOM_SIZE)
        return self.shaft_near(box)

    def stress_noble_office(self, p):
        """§J's noble clause: a stressed manager or expedition leader also gets an office with a chair, in the
        very shape office() provisions the manager's (an unowned office zone assigned, else a new office zone and
        a chair from the free stock). office() keeps caring for the manager's order-validating desk either way."""
        did = p.get("id")
        if did not in (self.adm.get("MANAGER_id"), self.adm.get("EXPEDITION_LEADER_id")):
            return
        if self.zone_of("office", did):
            return
        spare = next((z for z in self.zone("office") if z.get("owner") is None), None)
        if spare:
            self.act("stress_office_as_%s" % did, "assign_zone", {"zone_id": spare["id"], "dwarf_id": did},
                     retry=1, limit=10)
            return
        site = self.stress_site()
        if site is None:
            return
        self.stress_rooms.add(site["id"])
        r = self.act("stress_office_z_%s" % did, "make_zone", {"kind": "office", "site": site["id"]}, retry=3, limit=4)
        if r and r.get("ok") and (self.free.get("chair") or 0) > 0:
            self.act("stress_office_c_%s" % did, "place_furniture", {"kind": "chair", "site": site["id"]},
                     retry=1, limit=6)

    def head_ids(self):
        """The citizens the liaison meets or who hold a civ title: the expedition leader by the administrators'
        id, then anyone whose positions carry a HEAD_POSITIONS code (a mayor, a land holder, the monarch)."""
        out = []
        el = self.adm.get("EXPEDITION_LEADER_id")
        if el is not None:
            out.append(el)
        for p in self.people:
            if p.get("id") is not None and p.get("id") not in out\
                    and any(str(x).upper() in HEAD_POSITIONS for x in lst(p.get("positions"))):
                out.append(p.get("id"))
        return out

    def head_offices(self):
        """cx: the liaison's meeting room (LIAISON_OFFICE_DAY above). Full-year open play only (MY1 and the
        hands-off labs keep their behaviour): from LIAISON_OFFICE_DAY each head (head_ids) who owns no office gets
        one — an unowned office zone assigned (one is left for a manager still without a desk, since office()
        takes the first), else a new office zone on a free room (stress_site, reserved like a private room) with a
        chair from the free stock; a head's office without a chair gets one. The manager's own desk stays office()'s.
        Held off over a flood breach, like the private rooms."""
        if self.days < 336 or self.hands_off is not None or self.breach:
            return


        due = (self.day or 0) >= self.calendar_day(LIAISON_OFFICE_DOY, LIAISON_OFFICE_DAY)\
            or self.liaison_seen or self.caravan_arrival_day is not None
        if not due:
            return
        mgr = self.adm.get("MANAGER_id")
        offices = self.zone("office")
        spares = [z for z in offices if z.get("owner") is None]
        if mgr is not None and self.zone_of("office", mgr) is None and spares\
                and spares[0].get("id") not in self.head_zones:
            spares = spares[1:]
        for did in self.head_ids():
            if did == mgr:
                continue
            mine = next((z for z in offices if z.get("owner") == did), None)
            if mine is not None:
                if d(mine.get("furniture")).get("chair") or d(mine.get("furniture_planned")).get("chair")\
                        or (self.free.get("chair") or 0) <= 0:
                    continue
                room = next((s for s in self.sites if s.get("kind") in "RA" and s.get("z") == mine.get("z")
                             and s.get("x") == mine.get("x") and s.get("y") == mine.get("y")
                             and self.area_fits(s, PLACE_MAX)), None)
                if room is not None:
                    self.act("head_office_c_%s" % did, "place_furniture", {"kind": "chair", "site": room["id"]},
                             retry=2, limit=6)
                continue
            if spares:
                z = spares.pop(0)
                self.act("head_office_as_%s" % did, "assign_zone", {"zone_id": z["id"], "dwarf_id": did},
                         retry=1, limit=10)
                continue
            if not self.may("head_office_z_%s" % did, 3, 4):
                continue
            site = self.stress_site() or self.head_office_site()
            if site is None:
                continue
            self.stress_rooms.add(site["id"])
            r = self.act("head_office_z_%s" % did, "make_zone", {"kind": "office", "site": site["id"]},
                         retry=3, limit=4)
            log("head_office", day=self.day, dwarf=did, site=site["id"], ok=bool(r and r.get("ok")))
            zid = d(r.get("result")).get("zone_id") if r and r.get("ok") else None
            if zid is not None:


                self.head_zones.add(zid)
                self.act("head_office_as_%s" % did, "assign_zone", {"zone_id": zid, "dwarf_id": did},
                         retry=1, limit=10)
            if r and r.get("ok") and (self.free.get("chair") or 0) > 0:
                self.act("head_office_cz_%s" % did, "place_furniture", {"kind": "chair", "site": site["id"]},
                         retry=1, limit=6)

    def chair_target(self, seats):
        """The chair stock furnish keeps: the dining seats + 1 (the manager's desk), plus one per head on full-year
        open play, where head_offices() takes a chair for each head's office from the same free stock."""
        heads = len(self.head_ids()) if self.days >= 336 and self.hands_off is None else 0
        return seats + 1 + heads

    def head_office_site(self):
        """head_offices()' fallback when no free room is left: an A site the zone tool accepts, the way office()
        puts the manager's desk over a dug level (the measured manager office zones cover the dormitory level,
        beds and all — DF keeps overlapping zones). A level no office zone covers yet comes first; reserved
        sites never come back."""
        cands = [s for s in self.closed_a() if s.get("id") not in self.stress_rooms and self.dry(s.get("z"))
                 and self.area_fits(s, ZONE_MAX)]
        offices = self.zone("office")
        clear = [s for s in cands if not any(covers(z, s) or self.rects_overlap(z, s) for z in offices)]
        return next(iter(clear + cands), None)

    def stress_watch(self):
        """cx stress watch: once a game day, while any citizen reads stress category <= STRESS_WATCH_CATEGORY, one
        "stress_watch" log line with each such citizen's category, job, position, squad and their most unmet needs
        (the units query's needs: focus_level x need_level, the lowest first). The API carries no thoughts, so this
        is what a game's own record can say about why one citizen drifted (hint hard MY1-4 on d57f599: nothing in
        the records said why Iden rose at day 191). Read-only: a query, no action."""
        low = [p for p in self.people if isinstance(p.get("stress"), int) and not isinstance(p.get("stress"), bool)
               and p["stress"] <= STRESS_WATCH_CATEGORY]
        if not low or not self.may("stress_watch", 1, 10 ** 6):
            return
        self.last["stress_watch"] = self.now
        want = {p.get("id") for p in low}
        units = {}
        try:
            res = query_result(self.game.query("units", kind="citizens", limit=300))
            units = {d(u).get("id"): d(u) for u in lst(d(res).get("units"))} if res is not None else {}
        except Exception as e:
            log("stress_watch_error", error=repr(e)[:160])
        rows = []
        for p in sorted(low, key=lambda p: (p["stress"], p.get("id") or 0)):
            u = units.get(p.get("id")) or {}
            needs = []
            for n in lst(u.get("needs")):
                n = d(n)
                f, lv = n.get("focus_level"), n.get("need_level")
                if isinstance(f, (int, float)) and isinstance(lv, (int, float)) and f < 0:
                    needs.append((f * lv, str(n.get("need")), f, lv))
            needs.sort()
            rows.append({"id": p.get("id"), "cat": p["stress"], "job": p.get("job"), "squad": p.get("squad_id"),
                         "at": [p.get("x"), p.get("y"), p.get("z")],
                         "unmet": [[n, f, lv] for _, n, f, lv in needs[:STRESS_WATCH_NEEDS]]})
        log("stress_watch", day=self.day, alert=bool(d(self.o.get("burrows")).get("civilian_alert")),
            n=len(rows), cits=rows, ids=sorted(x for x in want if x is not None))

    def stress_housing(self):
        """The chronic-stress bedroom: each citizen in the stressed band (category <= 1, the score's own band) gets
        a private 3x3 bedroom zone on an unused dug room or an uncovered site, a bed placed inside that zone, and
        the zone assigned to them — one dwarf, one room, the shared dormitory untouched (ROOT_CAUSES §J: the
        measured hint MY1 forts carried one permanently stressed citizen and never assigned a bedroom). Idempotent
        through the zones' owners (a restart re-reads who already holds one), this run's assigned record, and the
        per-room reservation. No free bed orders one (make_bed), so the room completes when the shop catches up.
        Held off over a flood breach, where contain_flood() owns the placements."""
        if self.breach:
            return
        for p in self.stressed()[:STRESS_ROOM_CAP]:
            did = p.get("id")
            zone = self.stress_zone.get(did)
            if zone is None:
                zid = self.zone_of("bedroom", did)
                if zid is not None:
                    zone = next(z for z in self.zone("bedroom") if z.get("id") == zid)
            if zone is None:
                site = self.stress_site()
                if site is None:




                    if not any(self.roles.get(r["id"]) == "stress" and not r.get("dug") for r in self.kind("R")):






                        cand = next((r for r in self.undug_rooms() if self.dry(r.get("z")) and self.water_ok(r)
                                     and self.roles.get(r["id"]) is None and not self.room_near_shaft(r)
                                     and not self.people_later(r)), None)
                        if cand is not None:
                            res = self.act("dig_stress_" + cand["id"], "dig_room", {"site": cand["id"]}, retry=3, limit=4)
                            if res and res.get("ok"):
                                self.roles[cand["id"]] = "stress"
                                self.note_room_box(cand, {})
                        else:
                            site = self.stress_corner_site() if STRESS_CORNER else None
                            if site is None and self.may("stress_no_site_log", 7, 10 ** 6):



                                self.last["stress_no_site_log"] = self.now
                                log("stress_no_site", day=self.day, dwarf=did, stress=p.get("stress"))
                            elif site is not None:
                                log("stress_corner", day=self.day, dwarf=did, site=site["id"],
                                    at=[site.get("x"), site.get("y"), site.get("z")])
                    if site is None:
                        continue
                self.stress_rooms.add(site["id"])
                zw, zh = (site["w"], site["h"]) if "_bed" in site else (STRESS_ROOM_SIZE, STRESS_ROOM_SIZE)
                r = self.act("stress_zone_%s" % did, "make_zone",
                             {"kind": "bedroom", "site": site["id"], "w": zw, "h": zh}, retry=3, limit=4)
                at = d(d(r).get("result")).get("at") if r and r.get("ok") else None
                if not (r and r.get("ok")) or not (isinstance(at, list) and len(at) >= 3):
                    continue
                zone = {"id": d(d(r).get("result")).get("zone_id"), "x": at[0], "y": at[1], "z": at[2],
                        "site": site["id"]}
                if site.get("_bed"):
                    zone["has_bed"] = True
                self.stress_zone[did] = zone
            if zone.get("id") is None:
                continue
            if zone.get("has_bed"):
                pass
            elif (self.free.get("bed") or 0) > 0:




                sid = next((x.get("id") for x in self.sites if x.get("kind") in ("R", "A")
                            and all(x.get(k) == zone.get(k) for k in ("x", "y", "z"))), None) or zone.get("site")
                if sid is not None:
                    self.act("stress_bed_%s" % did, "place_furniture",
                             {"kind": "bed", "site": sid, "w": STRESS_ROOM_SIZE, "h": STRESS_ROOM_SIZE, "count": 1},
                             retry=1, limit=10)
            elif not self.pending("make_bed"):
                self.act("stress_o_bed", "add_order", {"recipe": "make_bed", "amount": 1}, retry=2, limit=6)
            r = self.act("stress_assign_%s" % did, "assign_zone", {"zone_id": zone["id"], "dwarf_id": did},
                         retry=1, limit=10)
            if r and r.get("ok"):
                self.stress_done.add(did)
            self.stress_noble_office(p)

    def house_everyone(self):
        """cx bedrooms for everyone (BEDROOM_* above): the citizens no bedroom zone belongs to, after the stressed
        ones stress_housing() serves, each get a private 3x3 bedroom zone (stress_site: a free dug room or an
        uncovered site, never the shared dormitory, off an open shaft), one bed placed in it and the zone assigned.
        Adults newest first (the migrants), children last; BEDROOM_PASS_CAP a pass. No room left: an R room is dug
        under the "bedroom" role (BEDROOM_DIG_INFLIGHT at once, dry and water-safe). Zoned rooms without a free bed
        order make_bed. Open play only: a hands-off window, a surge fort (scored on beds; beds wait for the wave)
        and a flood breach leave it off."""
        if self.breach or self.surge or self.hands_off is not None:
            return
        owned = {z.get("owner") for z in self.zone("bedroom") if z.get("owner") is not None}
        owned |= self.stress_done | set(self.stress_zone)
        stressed = {p.get("id") for p in self.stressed()}
        cands = [p for p in self.people if p.get("id") is not None and p.get("id") not in owned
                 and p.get("id") not in stressed]
        cands.sort(key=lambda p: (p.get("adult") is False, -(p.get("id") if isinstance(p.get("id"), int) else 0)))
        waiting_bed = 0
        for p in cands[:BEDROOM_PASS_CAP]:
            did = p.get("id")
            zone = self.bed_zone.get(did)
            if zone is None:
                site = self.stress_site()
                if site is None:
                    inflight = sum(1 for r in self.kind("R") if self.roles.get(r["id"]) == "bedroom" and not r.get("dug"))
                    if inflight >= BEDROOM_DIG_INFLIGHT:
                        continue






                    farms_short = not self.farms_met()
                    cand = self.pick_dig_site([r for r in self.undug_rooms() if self.dry(r.get("z"))
                                               and self.roles.get(r["id"]) is None and not self.room_near_shaft(r)
                                               and not (farms_short and r.get("soil"))
                                               and not self.people_later(r)])
                    if cand is not None:
                        res = self.act("dig_bedroom_" + cand["id"], "dig_room", {"site": cand["id"]}, retry=3, limit=4)
                        if res and res.get("ok"):
                            self.roles[cand["id"]] = "bedroom"
                            self.note_room_box(cand, {})
                            log("bedroom_dig", day=self.day, dwarf=did, site=cand["id"])
                    elif self.may("bedroom_no_site_log", 7, 10 ** 6):
                        self.last["bedroom_no_site_log"] = self.now
                        log("bedroom_no_site", day=self.day, dwarf=did, unhoused=len(cands))
                    continue
                self.stress_rooms.add(site["id"])
                r = self.act("bedroom_zone_%s" % did, "make_zone",
                             {"kind": "bedroom", "site": site["id"], "w": STRESS_ROOM_SIZE, "h": STRESS_ROOM_SIZE},
                             retry=3, limit=4)
                at = d(d(r).get("result")).get("at") if r and r.get("ok") else None
                if not (r and r.get("ok")) or not (isinstance(at, list) and len(at) >= 3):
                    continue
                zone = {"id": d(d(r).get("result")).get("zone_id"), "x": at[0], "y": at[1], "z": at[2],
                        "site": site["id"]}
                self.bed_zone[did] = zone
                log("bedroom", day=self.day, dwarf=did, site=site["id"], zone=zone.get("id"))
            if zone.get("id") is None:
                continue
            seen = next((z for z in self.zones if z.get("id") == zone["id"]), {})
            has_bed = (d(seen.get("furniture")).get("bed") or 0) + (d(seen.get("furniture_planned")).get("bed") or 0) > 0
            if not has_bed and "bedroom_bed_%s" % did not in self.done:
                if (self.free.get("bed") or 0) > 0:
                    self.act("bedroom_bed_%s" % did, "place_furniture",
                             {"kind": "bed", "site": zone["site"], "w": STRESS_ROOM_SIZE, "h": STRESS_ROOM_SIZE,
                              "count": 1}, retry=1, limit=10)
                else:
                    waiting_bed += 1
            r = self.act("bedroom_assign_%s" % did, "assign_zone", {"zone_id": zone["id"], "dwarf_id": did},
                         retry=1, limit=10)
            if r and r.get("ok"):
                self.done.add("bedroom_assign_%s" % did)
        if waiting_bed and not self.pending("make_bed") and self.logs():
            self.act("bedroom_o_bed", "add_order", {"recipe": "make_bed", "amount": min(BEDROOM_BED_BATCH,
                                                                                         waiting_bed + 1)},
                     retry=2, limit=99)

    def mood(self):
        for m in lst(self.o.get("moods")):
            m = d(m)
            if m.get("mood") in ("Melancholy", "Raving", "Berserk", "Traumatized"):
                continue
            if not m.get("claimed_building_id"):
                want = MOOD_WORKSHOP.get(str(m.get("skill")).upper(), "Craftsdwarfs")
                stuck = getattr(self, "shop_stuck", None) or {}




                have = {w.get("type") for w in lst(self.o.get("workshops"))
                        if isinstance(w, dict) and (w.get("built") or w.get("id") not in stuck)}
                if want not in have:



                    self.done.discard("ws_" + want)
                    key = "ws_mood_%s_%d" % (want, int(self.now // (3 * DAY)))
                    if not self.mood_build(want, key):
                        self.build(want, retry=1, key=key)
            for need in lst(m.get("items_needed")):
                if "bone" in str(d(need).get("item") or d(need).get("demand")).lower():
                    self.butcher(for_food=False)

    def note_w_sites(self):
        """cx toppled wagon: remembers every W, G and F site listed, and the wagon's position while it stands.
        observe.lua anchors those candidates on the wagon; once a tantrum topples it the lists stay empty for the rest
        of the run (hint hard LT03-0 on f2bd283 and LT03-3 on c44c96b: wagon toppled on day 1-2, only R sites listed
        to the horizon; every workshop rebuild then answered site_used)."""
        if not hasattr(self, "site_mem"):
            self.site_mem, self.wagon_seen, self.mem_tried = {}, None, set()
        wag = d(d(getattr(self, "map", None)).get("wagon"))
        xyz = tuple(wag.get(k) for k in ("x", "y", "z"))
        if wag.get("present") and all(isinstance(v, int) and not isinstance(v, bool) for v in xyz):
            self.wagon_seen = xyz
        for s in lst(getattr(self, "sites", None)):
            if isinstance(s, dict) and str(s.get("id", ""))[:1] in ("W", "G", "F") and all(
                    isinstance(s.get(k), int) and not isinstance(s.get(k), bool) for k in ("x", "y", "z")):
                self.site_mem[s["id"]] = {k: s.get(k) for k in ("id", "x", "y", "z", "w", "h")}
                self.site_mem[s["id"]]["kind"] = s["id"][:1]

    def remembered(self, kind):
        """After a toppled wagon (map.wagon.present false): remembered sites of `kind` the observation no longer lists
        and no coordinate call used yet, each marked _mem (site_args then gives coordinates: the tools take x,y,z
        without a site id, and act.lua checks the tiles itself — floor, soil, no building)."""
        if d(d(getattr(self, "map", None)).get("wagon")).get("present", True):
            return []
        listed = {s.get("id") for s in lst(getattr(self, "sites", None)) if isinstance(s, dict)}
        tried = getattr(self, "mem_tried", None) or set()
        return [dict(s, _mem=True) for sid, s in sorted((getattr(self, "site_mem", None) or {}).items(),
                                                       key=lambda e: (e[0][:1], int(e[0][1:]) if e[0][1:].isdigit() else 0))
                if s.get("kind") == kind and sid not in listed and sid not in tried]

    @staticmethod
    def site_args(s, box=False):
        """The tool's location for site s: its id while listed, its coordinates (and w,h for a box) when remembered."""
        if not s.get("_mem"):
            return {"site": s["id"]}
        a = {"x": s["x"], "y": s["y"], "z": s["z"]}
        if box:
            a.update(w=s.get("w") or 3, h=s.get("h") or 3)
        return a

    def mem_used(self, s, r):
        """A remembered site that got an answer (placed, or refused at those tiles) is not offered again."""
        if s.get("_mem") and r is not None:
            if not hasattr(self, "mem_tried"):
                self.mem_tried = set()
            self.mem_tried.add(s["id"])

    def shop_clash(self, s):
        """A 3x3 workshop centred on site s would overlap a workshop (built or a frame) standing now."""
        for w in lst(self.o.get("workshops")):
            w = d(w)
            wx, wy = w.get("x"), w.get("y")
            if w.get("z") == s.get("z") and isinstance(wx, int) and isinstance(wy, int)\
                    and abs(wx - s["x"]) <= 2 and abs(wy - s["y"]) <= 2:
                return True
        return False

    def mood_sites(self):
        """Where a mood shop may go: the listed W sites without a frame on them, then the remembered W sites whose
        footprint touches no workshop standing now. Farthest from the wagon first: the embark's loose items lie
        around it, and a frame on them is suspended ("Item blocking site", hint hard LT03-3 W1 and W3)."""
        out = [s for s in lst(getattr(self, "sites", None)) if isinstance(s, dict)
               and str(s.get("id", "")).startswith("W") and not self.frame_on(s)]
        out += [s for s in self.remembered("W") if not self.shop_clash(s)]
        wag = getattr(self, "wagon_seen", None)
        if wag:
            out.sort(key=lambda e: -max(abs(e["x"] - wag[0]), abs(e["y"] - wag[1])))
        return out

    def mood_build(self, want, key):
        """Places the mood's workshop on mood_sites()' first choice. False when there is no site (the caller falls
        back to build()); True when an attempt was made (or held back by act()'s pacing)."""
        if not isinstance(getattr(self, "o", None), dict):
            return False
        cands = self.mood_sites()
        if not cands or not self.material():
            return False
        s = cands[0]
        r = self.act(key, "build_workshop", dict(self.site_args(s), type=want), retry=1)
        if r and r.get("ok"):
            if not s.get("_mem"):
                self.sites = [x for x in self.sites if x.get("id") != s["id"]]
            log("mood_shop", day=self.day, type=want, site=s["id"], listed=not s.get("_mem"))
        self.mem_used(s, r)
        return True

    def kitchen_sheltered(self):
        """cx meat and alerts: a Kitchen stands inside the civilian-alert burrow's bounding box (the Shelter), so the
        cooks reach it while the alert confines them."""
        boxes = [d(b.get("bbox")) for b in lst(d(self.o.get("burrows")).get("list"))
                 if isinstance(b, dict) and b.get("civ_alert_burrow")]
        for w in lst(self.o.get("workshops")):
            if not isinstance(w, dict) or w.get("type") != "Kitchen":
                continue
            x, y, z = w.get("x"), w.get("y"), w.get("z")
            for bb in boxes:
                try:
                    if bb["x1"] <= x <= bb["x2"] and bb["y1"] <= y <= bb["y2"] and bb["z1"] <= z <= bb["z2"]:
                        return True
                except (KeyError, TypeError):
                    continue
        return False

    def slaughter_wait(self):
        """cx meat and alerts (ALERT_QUIET_DAYS above): a food slaughter waits — its meat would rot before the cooks
        reach it — while a civilian alert is on or ended within ALERT_QUIET_DAYS and the Kitchen stands outside the
        Shelter. Returns the reason or None. (Uncooked meat already in stock is no reason: the OP1 embark stock reads
        perishable 30-40 for weeks — preserved food in the embark barrels — and the slaughter is the food alarm's.)"""
        alert = bool(d(self.o.get("burrows")).get("civilian_alert"))
        recent = self.alert_seen_day is not None and isinstance(self.day, (int, float))\
            and self.day - self.alert_seen_day <= ALERT_QUIET_DAYS
        if (alert or recent) and not self.kitchen_sheltered():
            return "alert"
        return None

    def f_livestock(self):
        """cx F livestock (above): inside F on open play, a tame unowned animal every F_SLAUGHTER_DAYS while food's
        cover at the fort's gross use is under F_FOOD_COVER_DAYS."""
        if not self.alloc_on() or not isinstance(self.day, (int, float)):
            return
        left = self.days_to_end()
        if left is None or left > self.f_len() or left < F_SLAUGHTER_TAIL:
            return
        if self.my1_plan() and self.f_len() - left < F_SLAUGHTER_FROM:
            return
        food = self.st.get("food_edible") or 0
        use = self.use_rate("food", ALLOC_FOOD_PER_CIT_DAY) * max(1, self.cit or 0)
        if use <= 0 or food / use >= F_FOOD_COVER_DAYS:
            return
        if self.slaughter_wait() is not None or not self.may("f_slaughter", F_SLAUGHTER_DAYS, 99):
            return
        if not self.butchers_ready():
            self.build("Butchers", key=self.butcher_key())
        try:
            q = query_result(self.game.query("units", kind="animals"))
        except Exception as e:
            log("butcher_query_error", error=repr(e)[:160])
            return
        units = [d(a) for a in lst(d(q).get("units") or d(q).get("animals"))]
        if self.my1_plan():
            units.sort(key=lambda a: any(w in SMALL_ANIMALS for w in str(a.get("race") or "").upper().split("_")))
        for a in units:
            if a.get("tame") and a.get("pet_owner_id") in (None, -1) and not a.get("marked_for_slaughter"):
                r = self.act("f_slaughter", "slaughter", {"unit_id": a.get("id")}, retry=F_SLAUGHTER_DAYS, limit=99)
                if r is not None:
                    log("f_slaughter", day=self.day, unit=a.get("id"), race=a.get("race"), food=food,
                        cover=round(food / use), left=left, ok=r.get("ok"))
                return

    def butcher(self, for_food=True):
        """Marks one tame unowned animal for slaughter (every 5 days at most). A food slaughter (every caller but the
        strange mood's bone need) first passes slaughter_wait."""
        if not self.butchers_ready():
            self.build("Butchers", key=self.butcher_key())
        if for_food:
            why = self.slaughter_wait()
            if why is not None:
                if self.may("slaughter_wait_log", 1, 99):
                    self.last["slaughter_wait_log"] = self.now
                    log("slaughter_wait", day=self.day, why=why, perishable=self.perishable(),
                        alert_seen=self.alert_seen_day)
                return
        if not self.may("slaughter", 5, 3):
            return
        try:
            q = query_result(self.game.query("units", kind="animals"))
        except Exception as e:
            log("butcher_query_error", error=repr(e)[:160])
            return

        keep = for_food and self.f_reserve_hold()

        for a in sorted(map(d, lst(d(q).get("units") or d(q).get("animals"))), key=lambda a: not grazer_race(a.get("race"))):
            if keep and not grazer_race(a.get("race")):
                if not self.f_reserve_logged:
                    self.f_reserve_logged = True
                    log("f_reserve_keep", day=self.day, unit=a.get("id"), race=a.get("race"),
                        food=self.st.get("food_edible"), cit=self.cit)
                continue
            if a.get("tame") and a.get("pet_owner_id") in (None, -1) and not a.get("marked_for_slaughter"):
                self.act("slaughter", "slaughter", {"unit_id": a.get("id")}, retry=5, limit=3)
                return

    def defend(self):
        th, mil = d(self.o.get("threats")), d(self.o.get("military"))
        bur = d(self.o.get("burrows"))
        alert = bur.get("civilian_alert")
        if alert and self.alert_since is None:
            self.alert_since = self.now
        elif alert is False:
            self.alert_since = None
            if self.wild_spans and self.wild_spans[-1][1] is None and self.wild_alert_since is not None\
                    and self.now - self.wild_alert_since > DAY:
                self.wild_alert_closed()
                self.wild_alert_since = None
        squads = lst(mil.get("squads"))
        squad = d(squads[0]) if squads else None
        foes = [d(h) for h in lst(th.get("hostiles")) if d(h).get("invader")]
        if squad:
            self.arm_record(squad)
        if not squad and foes and self.cit >= SQUAD_MIN_CIT:



            self.create_squad("squad", self.fight_squad_size(th))
        elif not squad and self.cit >= SQUAD_MIN_CIT:



            self.create_squad("squad", 4)
        if squad and squad.get("uniform") == "none" and self.equip_day is None:



            tpl = self.uniform_choice()
            r = self.act("equip", "equip_squad", {"uniform": tpl}, retry=1, limit=3)
            if r is not None:
                if not r.get("ok") and tpl == "metal":
                    self.metal_refused = True
                    self.tries["equip"] = max(0, self.tries.get("equip", 1) - 1)
                    self.last.pop("equip", None)
                if r.get("ok"):
                    self.equip_day = self.day
                log("equip_once", day=self.day, uniform=tpl, ok=r.get("ok"), invaders=bool(foes))
        if squad and squad.get("uniform") not in (None, "none"):
            self.spear_supply(squad)






        self.gate_survey()
        self.shelter_grow()
        invaders = [h for h in lst(th.get("hostiles")) if d(h).get("invader")]
        hostile = th.get("visible_hostiles") or 0

        window = self.invader_window is not None and self.now < self.invader_window
        if self.invader_window is not None and not window:
            log("invader_window_end", day=self.day, invaders=len(invaders), hostile=hostile,
                guard=list(self.invader_guard) if self.invader_guard else None)
            self.invader_window = None
        orders = lst((squad or {}).get("orders"))
        odds = self.fight_odds(squad, th) if hostile and squad else None
        if hostile and squad and odds["go"] and not window\
                and (not orders or self.mark_station is not None or self.invader_guard is not None
                     or self.muster is not None):
            args = {"order": "attack"}
            if odds["targets"] is not None:
                args["target_ids"] = odds["targets"]
            r = self.act("attack", "squad_order", args, retry=1, limit=99)
            if r and r.get("ok"):
                self.mark_station = None
                self.gate_post = False
                self.invader_guard = None
                self.muster = None
                log("fight_go", day=self.day, ours=odds["ours"], theirs=odds["theirs"], endgame=odds["endgame"],
                    armed=odds["armed"], members=odds["members"], foes=odds["foes"])
        elif hostile and squad and not odds["go"] and not window:
            attacking = any(d(o).get("order") == "attack" for o in orders)



            armable = len(self.armable_ids(squad))
            odds_arm = self.fight_odds(dict(squad, armed=max(squad.get("armed") or 0, armable)), th)
            if invaders and not attacking and self.invader_guard is None\
                    and squad.get("uniform") not in (None, "none") and odds_arm["why"] != "big_only"\
                    and (odds_arm["go"] or not self.duty_seen or self.muster is not None):
                self.guard_muster(squad, force="invaders")
            elif (attacking and odds["retreat"]) or self.invader_guard is not None:


                r = self.act("fight_retreat", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
                if r and r.get("ok"):
                    self.invader_guard = None
                    log("fight_retreat", day=self.day, ours=odds["ours"], theirs=odds["theirs"], why=odds["why"])
            elif self.fight_log_day != self.day:
                self.fight_log_day = self.day
                log("fight_hold", day=self.day, ours=odds["ours"], theirs=odds["theirs"], why=odds["why"],
                    armed=odds["armed"], members=odds["members"], foes=odds["foes"], endgame=odds["endgame"],
                    attacking=attacking)
        if not hostile and orders and self.mark_station is None and self.muster is None:
            r = self.act("stand_down", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
            if r and r.get("ok"):
                self.invader_guard = None
        if not hostile and squad:
            self.guard_muster(squad)
        if window and hostile:
            self.invader_guard_station(squad, invaders)
        near = (th.get("nearest_hostile_dist_to_wagon") or 10 ** 6) <= 45
        if invaders and near and not alert and not self.alert_barred() and not window\
                and self.shelter_listed(bur):

            r = self.act("alert_on", "civilian_alert", {"on": True}, retry=1, limit=10 ** 6)
            if r and r.get("ok"):
                self.alert_since = self.now

        too_long = self.alert_since is not None and self.now - self.alert_since > 10 * DAY

        thirst = self.thirst_due()
        if thirst and alert:
            too_long = True
        elif thirst and self.access_from is not None:

            until = self.access_from + ACCESS_WINDOW_DAYS * DAY
            if self.wild_rest_until is None or self.wild_rest_until < until:
                self.wild_rest_until = until
                log("access_hold", day=self.day, until_day=round(until / DAY, 1),
                    since_day=round(self.access_tick / DAY, 1))
        elif thirst and self.access_log_day != self.day:
            self.access_log_day = self.day
            inside = next((d(b).get("citizens_inside") for b in lst(bur.get("list"))
                           if d(b).get("civ_alert_burrow")), None)
            log("access_unseen", day=self.day, since_day=round(self.access_tick / DAY, 1), inside=inside,
                citizens=self.cit, drink=self.st.get("drink"), wanting=self.thirst_signs(),
                locked=sorted(str(d(x).get("id")) for x in lst(d(self.o.get("doors")).get("list"))
                              if d(x).get("locked")))
            self.trap_seen += 1
            self.shelter_trap()
        if not thirst:
            self.trap_pokes, self.trap_last, self.trap_seen = 0, None, 0
        big = self.big_units() if alert else []



        if big and self.alert_since is not None and self.now - self.alert_since > BIG_FREE_DAYS * DAY\
                and not self.wild_approaching(big):
            log("big_hold_aged", day=self.day, animals=sorted({u["_mark"] for u in big}))
            big = []
        if alert and big and not too_long and not invaders:
            for u in big:
                self.wild_watch[u["_mark"]] = self.now
            if self.big_log_day != self.day:
                self.big_log_day = self.day
                log("big_hold", day=self.day, animals=sorted({u["_mark"] for u in big}), near=len(big))
        lift = alert and ((not invaders and not big and not self.wild_alert_hold()) or too_long)
        if lift and not too_long and self.home_holding():
            lift = False
        if lift and not invaders and self.alert_since is not None\
                and self.now - self.alert_since <= (10 + CAP_DEFER_DAYS) * DAY\
                and not (thirst and self.now - self.access_tick > (ACCESS_CAP_DAYS + CAP_DEFER_DAYS) * DAY):
            pressing = self.mark_pressing()
            if too_long and not pressing:
                pressing = self.fight_pressing()
            if pressing:
                if self.may("cap_defer_log", 1, 10 ** 6):
                    self.last["cap_defer_log"] = self.now
                    log("cap_defer", day=self.day, animals=pressing, cap=too_long)
                lift = False
        if lift and not invaders and not thirst and self.gate_waiting:



            close = self.shaft_wait_close()
            if close:
                if self.may("shaft_wait_defer_log", 1, 10 ** 6):
                    self.last["shaft_wait_defer_log"] = self.now
                    log("shaft_wait_defer", day=self.day, animals=sorted({u["_mark"] for u in close}), cap=too_long)
                lift = False
        if lift and invaders:


            if thirst:
                budget = self.now - self.access_tick <= (ACCESS_CAP_DAYS + CAP_DEFER_DAYS) * DAY
            else:
                budget = self.alert_since is not None and self.now - self.alert_since <= (10 + CAP_DEFER_DAYS) * DAY
            at_door = self.invaders_at_entrance(invaders) if budget else []
            if at_door:
                if self.invader_defer_day != self.day:
                    self.invader_defer_day = self.day
                    log("invader_defer", day=self.day, invaders=at_door,
                        since_day=round(self.access_tick / DAY, 1) if self.access_tick is not None else None)
                lift = False
        if lift:
            r = self.act("alert_off", "civilian_alert", {"on": False}, retry=1, limit=99)
            if r and r.get("ok"):




                if isinstance(self.o.get("burrows"), dict):
                    self.o["burrows"]["civilian_alert"] = False
                if self.wild_alert_since is not None or big:


                    self.wild_rest_until = self.now + WILD_REST_DAYS * DAY
                    self.wild_alert_closed()
                    log("wild_rest", day=self.day, cap=too_long, until_day=self.day + WILD_REST_DAYS
                        if isinstance(self.day, (int, float)) else None)
                if thirst:
                    until = self.now + ACCESS_WINDOW_DAYS * DAY
                    if self.wild_rest_until is None or self.wild_rest_until < until:
                        self.wild_rest_until = until
                    log("access_lift", day=self.day, since_day=round(self.access_tick / DAY, 1),
                        wanting=self.thirst_signs(), drink=self.st.get("drink"))
                if invaders:
                    self.invader_window = self.now + ACCESS_WINDOW_DAYS * DAY
                    if self.wild_rest_until is None or self.wild_rest_until < self.invader_window:
                        self.wild_rest_until = self.invader_window
                    self.invader_guard = None
                    log("invader_window", day=self.day, until_day=round(self.invader_window / DAY, 1),
                        invaders=len(invaders), thirst=bool(thirst),
                        squad=len(lst(squad.get("members"))) if squad else 0,
                        armed=(squad.get("armed") or 0) if squad else 0)
                    if hostile:
                        self.invader_guard_station(squad, invaders)
                self.alert_since = None
                self.wild_alert_since = None

    def create_squad(self, key, n):
        """cx squad pick: create_squad with the members squad_pick() chooses (dwarf_ids, the first one the militia
        commander), or with size n when the pick has nobody (the tool's own choice). One act either way (the key's
        retry and limit as before: retry 5, limit 3)."""
        if key in self.done or not self.may(key, 5, 3):
            return None
        ids = self.squad_pick(n)
        args = {"dwarf_ids": ids} if ids else {"size": n}
        return self.act(key, "create_squad", args, retry=5, limit=3)

    def squad_pick(self, n):
        """cx squad pick (owner 2026-11-10): up to n eligible citizens (adult, no position, no squad, not in a mood —
        act.lua's eligibility: getNoblePositions empty, squad_id -1) in this order: (1) a military profession
        (SQUAD_MILITARY); (2) no tool labor (MINE, CUTWOOD) and no essential profession (SQUAD_ESSENTIAL); (3) an
        essential profession without a tool labor; (4) miners and woodcutters (SQUAD_TOOL, or the MINE/CUTWOOD
        labor) — only while tiers 1-3 hold fewer than MARK_SQUAD_MIN (a smaller squad never guards: mark_guard),
        and then only up to MARK_SQUAD_MIN. Each tier by combat skill (SQUAD_COMBAT_SKILLS summed, no MINING), then
        id. From the units query (citizens: labors, skills, positions, squad_id, adult, mood); without it, the
        observation's dwarves (profession, positions, squad_id, adult; no labors or skills). [] when nobody."""
        mood_ids = {d(m).get("unit_id") for m in lst(self.o.get("moods"))}
        units = None
        try:
            res = query_result(self.game.query("units", kind="citizens", limit=300))
            if res is not None:
                units = [d(u) for u in lst(res.get("units"))]
        except Exception as e:
            log("squad_pick_query_error", error=repr(e)[:160])
        src = "units" if units else "observe"
        if not units:
            units = [d(p) for p in self.people]
        tiers = {1: [], 2: [], 3: [], 4: []}
        holders = {}
        for u in units:
            for lab in {str(x).upper() for x in lst(u.get("labors"))} & set(SQUAD_SOLE_LABORS):
                holders.setdefault(lab, []).append(u.get("id"))
        sole = {ids[0] for ids in holders.values() if len(ids) == 1}
        for u in units:
            if u.get("id") is None or u.get("adult") is False or u.get("squad_id") is not None\
                    or lst(u.get("positions")) or u.get("id") in mood_ids or u.get("mood"):
                continue
            if u.get("id") in self.stranded:
                continue
            prof = str(u.get("profession") or "").lower()
            labors = {str(x).upper() for x in lst(u.get("labors"))}
            skills = d(u.get("skills"))
            combat = sum(v for k, v in skills.items() if k in SQUAD_COMBAT_SKILLS and isinstance(v, (int, float)))
            if any(t in prof for t in SQUAD_TOOL) or labors & set(SQUAD_TOOL_LABORS):
                tier = 4
            elif any(t in prof for t in SQUAD_MILITARY):
                tier = 1
            elif any(t in prof for t in SQUAD_ESSENTIAL) or u["id"] in sole:
                tier = 3
            else:
                tier = 2
            tiers[tier].append((-combat, u["id"]))
        out = []
        for t in (1, 2, 3):
            out += [i for _, i in sorted(tiers[t])]
        out = out[:n]
        drafted = []
        if len(out) < MARK_SQUAD_MIN:
            drafted = [i for _, i in sorted(tiers[4])][:max(0, min(n, MARK_SQUAD_MIN) - len(out))]
            out += drafted
        log("squad_pick", day=self.day, n=n, ids=out, source=src, tool_workers=drafted,
            tiers={k: len(v) for k, v in tiers.items()})
        return out[:10]

    def arm_record(self, squad):
        """cx arming (probe p4, 2026-11-10): which members are armable. observe's weapon_assigned counts the uniform
        specs' assigned lists, which a later equip_squad deletes while DF keeps the items assigned to the positions
        (position.equipment.assigned_items) — after such a call it reads false for good, though the members still
        fetch those weapons on duty (stationed: armed 3). And off duty nobody carries one (armed 0 is normal). So a
        member is armable once seen with weapon_assigned (our single call keeps it truthful) or holding a non-pick
        weapon while the squad holds an order; duty_seen records that the squad has been on duty since its uniform
        (one pass with an order and a look a day later)."""
        if squad.get("uniform") in (None, "none"):
            return
        on = bool(lst(squad.get("orders")))
        for m in map(d, lst(squad.get("members"))):
            w = str(m.get("weapon") or "").lower()
            if m.get("weapon_assigned") or (on and w and "pick" not in w):
                self.armed_seen[m.get("id")] = self.day
        if on:
            if self.duty_from is None:
                self.duty_from = self.now
            elif self.now - self.duty_from >= DAY:
                self.duty_seen = True
        else:
            self.duty_from = None

    def armable_ids(self, squad):
        """cx arming: the current members known to be armable (arm_record)."""
        ids = {d(m).get("id") for m in lst(squad.get("members"))}
        return sorted(i for i in self.armed_seen if i in ids)

    def guard_muster(self, squad, force=None):
        """cx guard muster (2026-11-10): soldiers carry their uniform's weapons only on duty (probe p4: off duty
        armed 0; stationed, armed 3 two days later; stood down, 0 again). Hint std MY1-4 on d769d66: armed stayed at
        the miner's own pick until mark_rescue's station on day 58, all four carried copper weapons on day 59.
        mark_rescue / mark_gate wait for MARK_RESCUE_ARMED carried weapons, so without a duty spell the closure of an
        unhatchable shaft never comes. Now, while a wildlife alert of this layer stands or a DANGER_WEAK marked animal
        is within MARK_RANGE (guard_need) — or invaders are in sight and the armable members would give the odds
        (force="invaders", from defend()) — and fewer than MARK_RESCUE_ARMED members carry a weapon, while more
        members are armable than carry one or the squad has not yet been on duty since its uniform (nothing known),
        the squad is stationed on a sheltered citizen's tile (below the surface, the one farthest from any surface
        entrance): on duty, away from the stair — no guard post, the alert-only defence stands — so the members
        fetch their weapons and mark_guard's readiness (or the attack) can pass. It stands down when the need is
        gone, or after a day on duty with nobody armable; mark_guard's own station or the attack replaces it."""
        if self.mark_station is not None or self.invader_guard is not None:
            self.muster = None
            return
        orders = lst(squad.get("orders"))
        need = force or self.guard_need()
        threat = need in ("wild_alert", "weak_mark", "invaders")
        if need in ("wild_alert", "weak_mark") and not self.open_entrances():






            threat = False
        armed = squad.get("armed") or 0





        present = bool(self.marked_units(MARK_RANGE, MARK_RANGE_Z))
        wild = threat and need in ("wild_alert", "weak_mark") and not self.muster_big()
        lingering = self.muster_lingering(wild and not present)\
            or (wild and self.shaft_rest)
        if self.muster is not None:
            idle = self.duty_seen and not self.armable_ids(squad) and armed == 0
            close = self.muster_crossing(squad)\
                if threat and need in ("wild_alert", "weak_mark") and armed < MARK_RESCUE_ARMED else []
            if close:





                r = self.act("muster_stand_down", "squad_order", {"order": "stand_down"}, retry=0.25, limit=10 ** 6)
                if r and r.get("ok"):
                    log("guard_muster_end", day=self.day, armed=armed, at=list(self.muster), why="clear_wait",
                        animals=sorted({u["_mark"] for u in close}), tiles=min(u["_tiles"] for u in close))
                    self.muster = None
                return
            if threat and not idle and not lingering:
                return
            r = self.act("muster_stand_down", "squad_order", {"order": "stand_down"}, retry=0.25, limit=10 ** 6)
            if r and r.get("ok"):
                log("guard_muster_end", day=self.day, armed=armed, at=list(self.muster),
                    why="no_weapons" if idle else "lingering" if threat else "need_gone")
                self.muster = None
            return
        if orders or not threat or squad.get("uniform") in (None, "none")\
                or (need != "invaders" and armed >= MARK_RESCUE_ARMED):
            return
        if lingering:


            if self.may("muster_linger_log", 1, 10 ** 6):
                self.last["muster_linger_log"] = self.now
                log("muster_linger", day=self.day, need=need,
                    since=None if self.muster_since is None else round((self.now - self.muster_since) / DAY, 1),
                    contact=None if self.muster_contact is None else round((self.now - self.muster_contact) / DAY, 1))
            return
        if need in ("wild_alert", "weak_mark"):
            close = self.muster_crossing(squad)
            if close:

                if self.may("muster_wait_log", 1, 10 ** 6):
                    self.last["muster_wait_log"] = self.now
                    log("muster_wait", day=self.day, need=need, animals=sorted({u["_mark"] for u in close}),
                        tiles=min(u["_tiles"] for u in close))
                return
        armable = self.armable_ids(squad)
        if len(armable) <= armed and (self.duty_seen or need != "invaders"):


            return
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        surface = self.surface if num(self.surface) else d(self.map).get("surface_z")
        if not num(surface):
            return
        ids = {d(m).get("id") for m in lst(squad.get("members"))}
        spots = [c for c in self.citizen_spots() if c["z"] < surface and c.get("id") not in ids]
        if not spots:
            return
        ents = self.invader_entrances()
        far = lambda c: min((max(abs(c["x"] - x), abs(c["y"] - y)) + 3 * abs(c["z"] - z) for x, y, z in ents),
                            default=0)
        c = max(spots, key=lambda c: (far(c), -c["z"]))
        r = self.act("guard_muster", "squad_order", {"order": "station", "x": c["x"], "y": c["y"], "z": c["z"]},
                     retry=1, limit=99)
        if r and r.get("ok"):
            self.muster = (c["x"], c["y"], c["z"])
            log("guard_muster", day=self.day, need=need, armed=armed, x=c["x"], y=c["y"], z=c["z"],
                armable=len(armable), duty_seen=self.duty_seen)

    def wild_contact(self, units, gates, tiles):
        """cx muster length: a marked unit approaching a citizen (wild_approaching), a fight or interrupt of a marked
        species near or watched (wild_evidenced), or a marked unit within `tiles` (x/y, WILD_NEAR_Z levels) of an
        open shaft."""
        names = sorted({u["_mark"] for u in units} | set(self.wild_watched()))
        if units and self.wild_approaching(units):
            return True
        if names and self.wild_evidenced(names):
            return True
        return any(max(abs(u["x"] - gx), abs(u["y"] - gy)) <= tiles and abs(u["z"] - gz) <= WILD_NEAR_Z
                   for u in units for gx, gy, gz in gates)

    def mark_clear_wait(self, squad, armed, standing=False, gate=False):
        """cx muster clear for mark_guard's own stations (mark_gate at the shaft foot, mark_station on the animal):
        a station puts the members on duty, and on duty an unarmed member walks out to fetch his uniform — past the
        marked animal when it is near the entrance (hint hard MY1-4 on b092a1d day 5.0: "Pickup equipment:
        Interrupted by a kea" at the E1 stair top, the guard_muster case; mark_gate counts armable members, so it went
        out with armed 0 the same way). While fewer than MARK_RESCUE_ARMED members carry a weapon and a marked animal
        stands within MUSTER_CLEAR_TILES of the members' way to their gear (muster_crossing: the surface entrances
        and gear sites, or a member) no such station is ordered, and a standing one stands down (`standing`); the
        alert keeps everyone below meanwhile and the station goes once the animal is farther or gone. True when it
        held (the caller orders nothing). mark_rescue (a citizen under attack) is not held here.
        cx shaft wait (`gate`: the open-shaft foot guard, SHAFT WAIT above): the wait holds at most
        MARK_WAIT_MAX_DAYS from its first look, then the guard goes even unarmed; while it holds, gate_waiting tells
        the lift to keep the alert on (the drink-access clock aside)."""
        if armed >= MARK_RESCUE_ARMED:
            self.mark_wait_since = None
            return False
        close = self.muster_crossing(squad)
        if not close:
            if gate:
                self.mark_wait_since = None
            return False
        animals, tiles = sorted({u["_mark"] for u in close}), min(u["_tiles"] for u in close)
        if gate:
            if self.mark_wait_since is None:
                self.mark_wait_since = self.now
            waited = self.now - self.mark_wait_since
            if MARK_WAIT_MAX_DAYS is not None and waited >= MARK_WAIT_MAX_DAYS * DAY:

                if self.may("mark_wait_over_log", 1, 10 ** 6):
                    self.last["mark_wait_over_log"] = self.now
                    log("mark_wait_over", day=self.day, armed=armed, animals=animals, tiles=tiles,
                        waited=round(waited / DAY, 1), gear=self.gear_where, standing=standing)
                self.gate_waiting = False
                return False
            self.gate_waiting = True
        if standing:
            r = self.act("mark_clear_stand_down", "squad_order", {"order": "stand_down"}, retry=0.25, limit=10 ** 6)
            if r and r.get("ok"):
                log("mark_stand_down", day=self.day, why="clear_wait", station=self.mark_kind, armed=armed,
                    animals=animals, tiles=tiles, gear=self.gear_where)
                self.mark_station = None
                self.gate_post = False
            return True
        if self.may("mark_wait_log", 1, 10 ** 6):
            self.last["mark_wait_log"] = self.now
            log("mark_wait", day=self.day, armed=armed, animals=animals, tiles=tiles, gear=self.gear_where,
                armable=len(self.armable_ids(squad)) if squad else 0)
        return True

    def gear_sites(self):
        """cx shaft wait: where the members fetch their uniform — the boxes (x1, y1, x2, y2, z) of the fort's gear
        sites (Stockpile, Weaponrack, Armorstand buildings) on or above the surface level; [] when every such site
        lies below it; None when unknown (no surface level, the query refused, no site listed). The facts API lists
        no item positions, so the sites stand for the items (a uniform item lying loose elsewhere is not seen).
        One buildings query a game day at most; gear_where keeps the answer for the logs."""
        day = self.day if isinstance(self.day, (int, float)) else None
        if self.gear_cache is not None and day is not None and self.gear_cache[0] == day:
            return self.gear_cache[1]
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        surface = self.surface if num(getattr(self, "surface", None))\
            else d(getattr(self, "map", None)).get("surface_z")
        out = None
        if num(surface):
            try:
                res = query_result(self.game.query("buildings", limit=1000))
            except Exception as e:
                log("gear_query_error", error=repr(e)[:160])
                res = None
            sites = [b for b in map(d, lst(d(res).get("buildings")))
                     if b.get("type") in ("Stockpile", "Weaponrack", "Armorstand") and num(b.get("z"))]
            if sites:
                box = lambda b: (b.get("x1", b.get("x")), b.get("y1", b.get("y")), b.get("x2", b.get("x")),
                                 b.get("y2", b.get("y")), b["z"])
                out = [box(b) for b in sites if b["z"] >= surface and all(num(v) for v in box(b))]
        self.gear_where = "unknown" if out is None else "surface" if out else "below"
        if day is not None:
            self.gear_cache = (day, out)
        return out

    def muster_crossing(self, squad):
        """cx muster clear: the marked units (weak or big) within MUSTER_CLEAR_TILES (x/y, WILD_NEAR_Z levels) of the
        members' way to their gear, each with its nearest distance under "_tiles". [] with MUSTER_CLEAR_TILES None.
        cx shaft wait: the way is gear_sites()' — every gear site below the surface: only a member on the surface
        (the fetch stays below); a gear site on the surface: the surface entrances (invader_entrances), those sites
        and the members; unknown: the entrances and the members, as before."""
        if MUSTER_CLEAR_TILES is None:
            return []
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        members = [(m["x"], m["y"], m["z"]) for m in (d(m) for m in lst(d(squad).get("members")))
                   if all(num(m.get(k)) for k in ("x", "y", "z"))]
        gear = self.gear_sites()
        boxes = []
        if gear == []:
            surface = self.surface if num(getattr(self, "surface", None))\
                else d(getattr(self, "map", None)).get("surface_z")
            spots = [p for p in members if num(surface) and p[2] >= surface]
        else:
            spots = [p for p in self.invader_entrances() if all(num(v) for v in p)] + members
            boxes = list(gear or [])
        out = []
        for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z):
            ds = [max(abs(u["x"] - x), abs(u["y"] - y)) for x, y, z in spots if abs(u["z"] - z) <= WILD_NEAR_Z]
            ds += [max(x1 - u["x"], 0, u["x"] - x2, y1 - u["y"], u["y"] - y2)
                   for x1, y1, x2, y2, z in boxes if abs(u["z"] - z) <= WILD_NEAR_Z]
            if ds and min(ds) <= MUSTER_CLEAR_TILES:
                out.append({**u, "_tiles": min(ds)})
        return out

    def shaft_wait_close(self):
        """cx shaft wait: the marked units within MUSTER_CLEAR_TILES (x/y, WILD_NEAR_Z levels) of an open shaft
        (open_entrances) — while mark_guard's clear wait holds the foot guard, these keep the alert on."""
        tiles = MUSTER_CLEAR_TILES if MUSTER_CLEAR_TILES is not None else WILD_CLOSE_TILES
        gates = self.open_entrances()
        return [u for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z)
                if any(max(abs(u["x"] - gx), abs(u["y"] - gy)) <= tiles and abs(u["z"] - gz) <= WILD_NEAR_Z
                       for gx, gy, gz in gates)]

    def station_held(self, squad, x, y, z):
        """cx gate keep: the squad already holds a station order on (x, y, z)."""
        return any(o.get("order") == "station" and (o.get("x"), o.get("y"), o.get("z")) == (x, y, z)
                   for o in map(d, lst(d(squad).get("orders"))))

    def muster_big(self):
        """cx muster length: a DANGER_BIG beast is part of the standing wildlife reason — the open alert span is a
        big_alert's, a marked unit of a DANGER_BIG race is within MARK_RANGE, or a DANGER_BIG species was watched
        (sounded or held the alert) since the alert began. Hint hard MY1-4 on b092a1d: a carnotaurus's mark_alert
        (pre) on day 184 and its big_hold day 186 — the muster stood down 'lingering' on day 191 with the beast near
        for 5 days (near is no contact: wild_contact counts approach, fight, shaft)."""
        span = self.wild_spans[-1] if self.wild_spans else None
        if span is not None and span[1] is None and len(span) > 2 and span[2] == "big":
            return True
        if any(big_race(u.get("race")) or big_race(u.get("_mark"))
               for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z)):
            return True
        since = self.wild_alert_since
        return since is not None and any(big_race(n) and isinstance(t, (int, float)) and t >= since
                                         for n, t in self.wild_watch.items())

    def muster_lingering(self, wild):
        """cx muster length (MUSTER_IDLE_CAP_DAYS above): True when a wildlife reason has stood more than the cap with
        no contact (wild_contact, the shaft at WILD_CLOSE_TILES) — counted from the reason's start, then from the last
        contact. A reason that is gone resets the count."""
        if not wild or MUSTER_IDLE_CAP_DAYS is None:
            self.muster_since = None
            return False
        if self.muster_since is None:
            self.muster_since = self.now
        units = self.marked_units(MARK_RANGE, MARK_RANGE_Z)
        if self.wild_contact(units, self.open_entrances(), WILD_CLOSE_TILES):
            self.muster_contact = self.now
        ref = self.muster_since if self.muster_contact is None else max(self.muster_since, self.muster_contact)
        return self.now - ref > MUSTER_IDLE_CAP_DAYS * DAY

    def shaft_guard_due(self, units, gates):
        """cx shaft guard length (SHAFT_GUARD_* above): the open-shaft guard is due — always with SHAFT_GUARD_TILES
        None; else for SHAFT_GUARD_HOLD_DAYS from the reason's start and from each contact (a weak marked animal within
        SHAFT_GUARD_TILES of the shaft, an approach, a fight or interrupt)."""
        if SHAFT_GUARD_TILES is None:
            return True
        if self.shaft_since is None:
            self.shaft_since = self.now
        if self.wild_contact(units, gates, SHAFT_GUARD_TILES):
            self.shaft_contact = self.now
        ref = self.shaft_since if self.shaft_contact is None else max(self.shaft_since, self.shaft_contact)
        return self.now - ref <= SHAFT_GUARD_HOLD_DAYS * DAY

    def squad_hold(self):
        """cx squad hold (owner 2026-11-11): every station or attack this layer sends stands until its own owner ends
        it. The hint runs: on 11 of the 15 runs with a guard_muster the model's squad_order stand_down came 0-2 days
        after the layer's station (c44c96b hard OP1-3: musters on days 217 and 259, stood down on days 220/222 and
        260/264; armed 4 -> 1 -> 0), and the layer kept self.muster set without looking at the squad again. The
        model's squad_order is refused now (plain LAYER_TOOLS); this pass is the defence against any other canceller.
        When the observation shows the squad without an order while the owner's need stands — guard_muster's muster,
        mark_guard's station (mark_rescue / mark_gate / mark_station), the invader window's guard (window open,
        hostiles in sight), defend()'s attack (hostiles in sight, the odds go, no window) or wildlife_response's kill
        list (a target still in sight) — the same order goes out again (squad_reassert). A need that is gone drops
        the record (the owners' own stand_down already ran on their pass; an attack ends with its targets)."""
        post = getattr(self, "squad_post", None)
        if post is None:
            return
        squad = next(iter(lst(d(self.o.get("military")).get("squads"))), None)
        if not isinstance(squad, dict):
            self.squad_post = None
            return
        if lst(squad.get("orders")):
            return
        key, args = post
        th = d(self.o.get("threats"))
        hostile = th.get("visible_hostiles") or 0
        window = self.invader_window is not None and self.now < self.invader_window
        if key == "guard_muster":
            need = self.muster is not None
        elif key in ("mark_rescue", "mark_gate", "mark_station"):
            need = self.mark_station is not None
        elif key == "invader_guard":
            need = self.invader_guard is not None and window and bool(hostile)
            if not need:
                self.invader_guard = None
        elif key == "attack":
            odds = self.fight_odds(squad, th) if hostile else None
            need = bool(odds and odds["go"]) and not window
            if need:
                args = {"order": "attack"}
                if odds["targets"] is not None:
                    args["target_ids"] = odds["targets"]
        elif key == "wild_attack":
            seen = {d(h).get("id") for h in lst(th.get("hostiles"))}
            ids = [i for i in lst(args.get("target_ids")) if i in seen]
            need = bool(ids)
            args = {"order": "attack", "target_ids": ids}
        else:
            need = False
        if not need:
            self.squad_post = None
            return
        r = self.act("squad_reassert", "squad_order", args, retry=0.25, limit=10 ** 6)
        if r is not None:
            log("squad_reassert", day=self.day, owner=key, order=args.get("order"), ok=r.get("ok"),
                code=r.get("error_code"))

    def spear_supply(self, squad):
        """cx spear supply (probe p6, 2026-11-10): the members without a weapon get wooden spears made at the
        Carpenters — add_manager_order MakeWeapon, material wood, ITEM_WEAPON_SPEAR, a one-shot of the shortfall (the
        probe: accepted, made within a day; DF filled the empty melee slot with it, no equip_squad re-call; the dev
        MY1 forts have no bars or ore). Shortfall = members - armable (arm_record: weapon_assigned on the day after
        the single call, or a non-pick weapon held on duty), read from the day after the uniform (or once the squad
        has been on duty). Only with a Carpenters workshop, none of the spear order still on the book, at least
        SPEAR_RETRY_DAYS since the last, logs above logs_guard() + the amount (beds, seats and barrels first) and no
        barrel press (brewable plants waiting on barrels); at most SPEAR_LIFETIME spears a run."""
        members = len(lst(squad.get("members")))
        known = (self.equip_day is not None and self.day is not None and self.day >= self.equip_day + 1)\
            or self.duty_seen
        if not members or not known:
            return
        short = members - len(self.armable_ids(squad))
        n = min(short, SPEAR_LIFETIME - self.spears_ordered)
        if n <= 0 or self.own_pending("spear") or not self.may("spear", SPEAR_RETRY_DAYS, 10 ** 6):
            return
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        why = None
        if "Carpenters" not in have:
            why = "no_carpenters"
        elif self.logs() < self.logs_guard() + n:
            why = "logs"
        elif self.barrel_press() and self.press_stand:
            why = "barrel_press"
        if why is not None:
            if self.may("spear_wait_log", 1, 10 ** 6):
                self.last["spear_wait_log"] = self.now
                log("spear_wait", day=self.day, short=short, why=why, logs=self.logs(), guard=self.logs_guard())
            return
        r = self.act("spear", "add_manager_order", {"job": "MakeWeapon", "material_category": ["wood"],
                                                     "item_subtype": "ITEM_WEAPON_SPEAR", "amount": n},
                     retry=SPEAR_RETRY_DAYS, limit=10 ** 6)
        if r is not None:
            if r.get("ok"):
                self.spears_ordered += n
            log("spear_order", day=self.day, amount=n, short=short, members=members, ok=r.get("ok"),
                ordered=self.spears_ordered, logs=self.logs())

    def patient_cancels(self):
        """{reason: lines} of the "Give water" cancels in the observation's text lists — a citizen who cannot reach
        water himself lies near the canceller (DF's carers' job for a patient)."""
        out = {}
        for t in lst(self.o.get("recent_cancellations")) + lst(self.o.get("recent_events")):
            m = GIVE_WATER_RE.search(str(t))
            if m:
                why = m.group(1).strip().lower()
                out[why] = out.get(why, 0) + 1
        return out

    def cup_supply(self):
        """cx cups (CUP_* above): one Craftsdwarfs and a daily MakeGoblet standing (wood) while the fort holds fewer
        goblets than citizens + CUP_SPARE and WOOD stands at logs_guard(). Open play only; a census that outgrows the
        standing's target re-cuts it (cancel, then re-add on a later pass)."""
        if self.hands_off is not None or (self.day or 0) < CUP_FROM_DAY or not self.cit:
            return
        target = self.cit + CUP_SPARE
        standing = next((x for x in self.orders if x.get("job") == "MakeGoblet" and x.get("repeat")), None)
        if standing is not None and "o_cups_prog" not in self.done and self.cup_target is None:
            return
        if "o_cups_prog" in self.done:
            oid = self.key_order.get("o_cups_prog")
            if self.cup_target is not None and target > self.cup_target + 1 and oid is not None:
                r = self.act("o_cups_recut", "cancel_order", {"order_id": oid}, retry=2, limit=4)
                if r is not None and r.get("ok"):
                    self.done.discard("o_cups_prog")
                    self.tries.pop("o_cups_prog", None)
                    self.last.pop("o_cups_prog", None)
                    log("cup_recut", day=self.day, old=self.cup_target, new=target)
            return
        shops = [w for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Craftsdwarfs"
                 and not self.shop_stale(w)]
        if not shops:

            owned = self.days >= 336 and (self.day or 0) >= PROGRESS_FROM_DAY and self.cit >= 7
            if not owned and self.logs() >= self.logs_guard():
                self.build("Craftsdwarfs", key="ws_Craftsdwarfs_cup", retry=5)
            return
        guard = self.logs_guard()
        if self.logs() < guard:
            return
        r = self.act("o_cups_prog", "add_manager_order", {
            "job": "MakeGoblet", "material_category": ["wood"], "amount": CUP_BATCH, "repeat": "daily",
            "when": [{"item_type": "GOBLET", "below": target}, {"item_type": "WOOD", "at_least": guard}]},
            retry=3, limit=4)
        if r is not None:
            if r.get("ok"):
                self.cup_target = target
            log("cup_standing", day=self.day, ok=r.get("ok"), target=target, logs=self.logs(), guard=guard,
                err=str(r.get("error") or "")[:120])

    def patient_water(self):
        """cx patient water: one standing MakeBucket (wood, amount BUCKET_KEEP, monthly) while fewer than BUCKET_KEEP
        empty buckets exist and WOOD stands at BUCKET_WOOD_FLOOR — placed once a Carpenters stands and a "Give water"
        cancel was seen (any reason: a patient exists now; a healthy fort's plan stays the leader's). The carers
        retry the job, so the bucket is a few days behind the first cancel (c44c96b hard OP1-0: the first one came
        74 days after the injury). Each day with a "Give water" cancel is logged (patient_water) with the reasons
        and the alert state, the evidence for what this layer cannot supply (a water source, a hospital)."""
        why = self.patient_cancels()
        if why and self.may("patient_water_log", 1, 10 ** 6):
            self.last["patient_water_log"] = self.now
            log("patient_water", day=self.day, reasons=why,
                alert=bool(d(self.o.get("burrows")).get("civilian_alert")))
        if "o_bucket_prog" in self.done:
            return
        shops = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("built")}
        if not why or "Carpenters" not in shops or self.logs() < BUCKET_WOOD_FLOOR:
            return
        r = self.act("o_bucket_prog", "add_manager_order", {
            "job": "MakeBucket", "material_category": ["wood"], "amount": BUCKET_KEEP, "repeat": "monthly",
            "when": [{"item_type": "BUCKET", "flags": ["empty"], "below": BUCKET_KEEP},
                     {"item_type": "WOOD", "at_least": BUCKET_WOOD_FLOOR}]}, retry=2, limit=5)
        if r is not None:
            log("bucket_standing", day=self.day, ok=r.get("ok"), patient=bool(why), logs=self.logs(),
                guard=self.logs_guard(), err=str(r.get("error") or "")[:120])

    def uniform_choice(self):
        """cx equip once: the template for the single equip_squad. "metal" when free metal body armour lies in the
        fort (stocks ARMOR, an INORGANIC material, not forbidden / in a job / in a building) and the template was not
        refused before; else "leather" — its armour specs only fill from leather armour that exists (probe p4: no
        armour assigned, weapons as with weapon_only; d769d66 MY1-4 assigned weapons under it from day 5)."""
        if self.metal_refused:
            return "leather"
        try:
            res = query_result(self.game.query("stocks", item_type="ARMOR"))
        except Exception as e:
            log("uniform_query_error", error=repr(e)[:160])
            return "leather"
        metal = 0
        for g in map(d, lst((res or {}).get("groups"))):
            if str(g.get("material") or "").upper().startswith("INORGANIC"):
                metal += max(0, (g.get("items") or 0) - (g.get("forbidden") or 0) - (g.get("in_job") or 0)
                             - (g.get("in_building") or 0))
        return "metal" if metal > 0 else "leather"

    def guard_need(self):
        """cx guard equip: why the fort needs the squad's closure now (None: it does not) — a surface entrance no hatch
        or inner gate closes (open_entrances: the squad at its foot is the closure, mark_gate), a wildlife alert of
        this layer standing, or a DANGER_WEAK marked animal within MARK_RANGE (mark_rescue / mark_gate answer it).
        Kept in guard_need_why for the log."""
        why = None
        if self.wild_alert_since is not None:
            why = "wild_alert"
        elif any(u["_mark"] in DANGER_WEAK for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z)):
            why = "weak_mark"
        elif self.open_entrances():
            why = "open_entrance"
        self.guard_need_why = why
        return why

    def fight_left(self):
        """cx fight odds: game days this layer still has to act before H — the end of the run, or the start of a
        hands-off window when one is announced (no pass runs inside it). None when neither is known."""
        left = self.days_to_end()
        ho = self.hands_off
        if isinstance(ho, (int, float)) and not isinstance(ho, bool):
            left = ho if left is None else min(left, ho)
        return left

    def fight_odds(self, squad, th):
        """cx fight odds (FIGHT_* above): the squad's strength against the hostiles in sight. -> dict: ours, theirs,
        go (attack now), retreat (call a standing attack off), why (the reason when not go), targets (the kill list
        when a DANGER_BIG beast is in sight with other hostiles, else None: every visible hostile), endgame, armed,
        members, foes (armed, unarmed, other, big)."""
        squad = d(squad)
        members = len(lst(squad.get("members")))
        armed = min(members, squad.get("armed") or 0) if members else (squad.get("armed") or 0)
        unarmed = max(0, members - armed)
        listed = [d(h) for h in lst(th.get("hostiles"))]
        big = [h for h in listed if not h.get("invader") and big_race(h.get("race"))]
        rest = [h for h in listed if h not in big]
        f_armed = sum(1 for h in rest if h.get("invader") and h.get("weapon"))
        f_unarmed = sum(1 for h in rest if h.get("invader") and not h.get("weapon"))
        f_other = sum(1 for h in rest if not h.get("invader"))
        f_other += max(0, (th.get("visible_hostiles") or 0) - len(listed))
        foes_armed = f_armed + f_other > 0
        ours = armed * FIGHT_ARMED + unarmed * (FIGHT_UNARMED_VS_ARMED if foes_armed else FIGHT_UNARMED)
        theirs = f_armed * FOE_ARMED + f_unarmed * FOE_UNARMED + f_other * FOE_OTHER
        left = self.fight_left()
        endgame = bool(listed) and any(h.get("invader") for h in listed) and left is not None\
            and left <= FIGHT_ENDGAME_DAYS
        ratio = FIGHT_ENDGAME_RATIO if endgame else FIGHT_RATIO
        why = None
        if not squad:
            why = "no_squad"
        elif armed < 1:
            why = "unarmed"
        elif theirs <= 0:
            why = "big_only" if big else "no_target"
        elif foes_armed and unarmed > armed:
            why = "unarmed_majority"
        elif ours < ratio * theirs:
            why = "outmatched"
        retreat = armed < 1 or theirs <= 0 or ours < FIGHT_RETREAT_RATIO * theirs
        return {"ours": round(ours, 2), "theirs": round(theirs, 2), "go": why is None, "retreat": retreat, "why": why,
                "targets": [h.get("id") for h in rest][:20] if big and rest else None, "endgame": endgame,
                "armed": armed, "members": members,
                "foes": {"armed": f_armed, "unarmed": f_unarmed, "other": f_other, "big": len(big)}}

    def fight_squad_size(self, th):
        """cx fight odds: create_squad's size with invaders in sight — enough armed members for FIGHT_RATIO against
        them, at least 4 (the default), at most a third of the citizens and 10 (the schema's cap)."""
        listed = [d(h) for h in lst(th.get("hostiles"))]
        theirs = sum(FOE_ARMED if h.get("weapon") else FOE_UNARMED for h in listed if h.get("invader"))\
            + FOE_OTHER * sum(1 for h in listed if not h.get("invader") and not big_race(h.get("race")))\
            + FOE_OTHER * max(0, (th.get("visible_hostiles") or 0) - len(listed))
        need = int(-(-FIGHT_RATIO * theirs // FIGHT_ARMED))
        return max(4, min(10, (self.cit or 0) // 3, need))

    def invader_entrances(self):
        """cx invader drink window: (x, y, z) of each known surface entrance (E sites, listed or remembered)."""
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        out = {p: None for _, p in sorted(self.entrances.items(), key=lambda kv: site_key(kv[0]))}
        for s in self.kind("E"):
            p = (s.get("x"), s.get("y"), s.get("z"))
            if all(num(v) for v in p):
                out.setdefault(p, None)
        return list(out)

    def invaders_at_entrance(self, invaders):
        """cx invader drink window: ids of the invaders within INVADER_ENTRANCE_TILES (x/y) and WILD_NEAR_Z levels of
        a surface entrance. An invader without a position, or no entrance known, counts as not there."""
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        ents = self.invader_entrances()
        out = []
        for h in map(d, invaders):
            if not all(num(h.get(k)) for k in ("x", "y", "z")):
                continue
            if any(max(abs(h["x"] - x), abs(h["y"] - y)) <= INVADER_ENTRANCE_TILES and abs(h["z"] - z) <= WILD_NEAR_Z
                   for x, y, z in ents):
                out.append(h.get("id"))
        return out

    def invader_guard_station(self, squad, invaders):
        """cx invader drink window: station the squad on the hatch tile of the surface entrance nearest the invaders
        (the stair foot one level down if the hatch tile refuses a station); once per window unless refused. No
        squad, none armed, or no entrance known: no station, logged once a day (the window stands regardless)."""
        if self.invader_guard is not None:
            return
        why = None
        if not squad:
            why = "no_squad"
        elif (squad.get("armed") or 0) < 1:
            why = "unarmed" if squad.get("uniform") not in (None, "none") else "unequipped"
        ents = self.invader_entrances()
        if why is None and not ents:
            why = "no_entrance"
        if why is not None:
            if self.invader_unguarded_day != self.day:
                self.invader_unguarded_day = self.day
                log("invader_unguarded", day=self.day, why=why, invaders=len(invaders),
                    until_day=round(self.invader_window / DAY, 1) if self.invader_window is not None else None)
            return
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        pos = [d(h) for h in invaders if all(num(d(h).get(k)) for k in ("x", "y"))]
        gx, gy, gz = min(ents, key=lambda p: min((max(abs(p[0] - h["x"]), abs(p[1] - h["y"])) for h in pos),
                                                 default=0))
        z = gz - 1 if self.invader_guard_foot else gz
        r = self.act("invader_guard", "squad_order", {"order": "station", "x": gx, "y": gy, "z": z},
                     retry=0.25, limit=10 ** 6)
        if r and r.get("ok"):
            self.invader_guard = (gx, gy, z)
            self.mark_station = None
            self.gate_post = False
            log("invader_guard", day=self.day, x=gx, y=gy, z=z, invaders=len(invaders),
                armed=squad.get("armed") or 0)
        elif r is not None:
            self.invader_guard_foot = not self.invader_guard_foot









    def cancel_animals(self):
        """The animal names in this observation's "Interrupted by a <animal>" cancels, folded to lowercase words
        (the query's race id folds the same way: ALLIGATOR_SNAPPING_TURTLE -> 'alligator snapping turtle')."""
        out = []
        for t in lst(self.o.get("recent_cancellations")):
            m = re.search(r"interrupted by an? ([a-z][a-z '\-]*[a-z])", str(t).lower())
            if m:
                out.append(m.group(1).strip())
        return out

    def record_wildlife(self, stamp):
        """Advance the per-animal interrupt streaks from this observation's cancels (run in load(), so every
        observation is stamped — a day the response itself is gated still counts). A sighting within
        WILDLIFE_GAP_DAYS of the last one continues its streak; anything stale is dropped, so an animal that left
        weeks ago cannot keep a squad mobilised. A stampless observation records nothing."""
        seen = set(self.cancel_animals())
        if stamp is None:
            return seen
        for name in seen:
            last = self.wild_day.get(name)
            if last is None or not isinstance(last, (int, float)) or stamp - last > WILDLIFE_GAP_DAYS:
                self.wild_from[name] = stamp
            self.wild_day[name] = stamp
        for name, last in list(self.wild_day.items()):
            if name not in seen and isinstance(last, (int, float)) and stamp - last > WILDLIFE_GAP_DAYS:
                self.wild_day.pop(name, None)
                self.wild_from.pop(name, None)
        return seen

    def wild_units(self, names, hostile_only=True):
        """The units-query (kind=others) units matching the interrupting animals — hostile-flagged ones only unless
        hostile_only is False. One query per observation (memoised on the load count); a lost query answers empty
        and is not memoised, so the next look asks again."""
        if self.wild_units_memo is not None and self.wild_units_memo[0] == self.loads:
            units = self.wild_units_memo[1]
        else:
            try:
                q = self.game.query("units", kind="others", limit=300)
            except Exception as e:
                log("wild_query_error", error=repr(e)[:160])
                return []
            res = query_result(q)
            if res is None:
                log("wild_query_error", error=query_error(q))
                return []
            units = [d(u) for u in lst(res.get("units"))]
            self.wild_units_memo = (self.loads, units)
        out = []
        for u in units:
            race = str(u.get("race") or "").lower().replace("_", " ")
            if not u.get("visitor") and race and (u.get("hostile") or not hostile_only)\
                    and any(race in name or name in race for name in names):
                out.append(u)
        return out

    def wild_targets(self, names, hostile_only=True):
        """Unit ids on the map matching the interrupting animals, from the units query (kind=others). Only the
        hostile-flagged matches are returned: squad_order's kill list rejects anything else (not_a_hostile,
        MANUAL.md:297). A lost query answers empty and the response waits for the next day."""
        return [u.get("id") for u in self.wild_units(names, hostile_only)][:20]

    def wild_near(self, names):
        """cx troop hold: ids of the named animals (any hostile flag) within WILD_NEAR_TILES (x/y) and WILD_NEAR_Z
        levels of the wagon. Without a wagon position or a unit position nothing counts as near (no hold)."""
        return [u.get("id") for u in self.wild_near_units(names)]

    def wild_near_units(self, names):
        """wild_near()'s units."""
        wag = d(self.map.get("wagon"))
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        if not names or not all(num(wag.get(k)) for k in ("x", "y", "z")):
            return []
        out = []
        for u in self.wild_units(names, hostile_only=False):
            if all(num(u.get(k)) for k in ("x", "y", "z"))\
                    and max(abs(u["x"] - wag["x"]), abs(u["y"] - wag["y"])) <= WILD_NEAR_TILES\
                    and abs(u["z"] - wag["z"]) <= WILD_NEAR_Z:
                out.append(u)
        return out

    def wild_watched(self):
        """cx troop hold: the animals that sounded this layer's alert (or were seen near since) within
        WILD_MEMORY_DAYS."""
        return sorted(n for n, t in self.wild_watch.items()
                      if isinstance(t, (int, float)) and self.now - t <= WILD_MEMORY_DAYS * DAY)

    def wild_resting(self):
        return self.wild_rest_until is not None and self.now < self.wild_rest_until


    def wild_alert_on(self, now=None, big=False):
        """This layer sounded a wildlife/mark alert: the tick its hold counts from, and a budget span opens (a
        big-beast alert's span is tagged and left out of the wildlife budget)."""
        now = self.now if now is None else now
        self.wild_alert_since = now
        self.alert_since = now
        if not self.wild_spans or self.wild_spans[-1][1] is not None:
            self.wild_spans.append([now, None, "big"] if big else [now, None])

    def wild_alert_closed(self):
        """The wildlife alert is off (lifted by defend() or seen off): its budget span closes."""
        if self.wild_spans and self.wild_spans[-1][1] is None:
            self.wild_spans[-1][1] = self.now

    def wild_budget_used(self):
        """Days of this layer's wildlife alerts inside the last WILD_BUDGET_WINDOW (an open span counts to now)."""
        lo = self.now - WILD_BUDGET_WINDOW * DAY
        used = 0
        for sp in self.wild_spans:
            if len(sp) > 2:
                continue
            a, b = sp[0], sp[1]
            b = self.now if b is None else b
            used += max(0, min(b, self.now) - max(a, lo))
        self.wild_spans = [sp for sp in self.wild_spans if sp[1] is None or sp[1] > lo]
        return used / DAY

    def wild_budget_left(self):
        return self.wild_budget_used() < WILD_BUDGET_DAYS

    def budget_fight(self, names):
        """cx BUDGET FIGHT: one of these species fought a citizen within BUDGET_FIGHT_DAYS (the load its report first
        showed, wild_fight) — a spent alert budget does not bar or lift a wildlife/mark alert for it meanwhile."""
        if not BUDGET_FIGHT_DAYS or not names:
            return False
        fought = [set(n.split()) for n, t in self.wild_fight.items()
                  if isinstance(t, (int, float)) and self.now - t <= BUDGET_FIGHT_DAYS * DAY]
        hit = any(w and f and (w <= f or f <= w) for f in fought for w in (set(str(n).split()) for n in names))
        if hit and not self.wild_budget_left() and self.may("budget_fight_log", 1, 10 ** 6):
            self.last["budget_fight_log"] = self.now
            log("budget_fight", day=self.day, animals=sorted(names), used=round(self.wild_budget_used(), 1))
        return hit

    def note_wild_evidence(self, obs):
        """Stamp the species of this observation's interrupts and of its fresh citizen combat reports (a report text
        counts on the load it first shows: recent_events keeps old reports) in wild_evidence."""
        obs = d(obs)
        for n in self.cancel_animals_of(obs):
            self.wild_evidence[n] = self.now
            m = mark_name(n)
            if m:
                self.wild_evidence[m] = self.now
        fresh = []
        for t in lst(obs.get("recent_events")):
            t = str(t)
            if t not in self.event_seen:
                self.event_seen[t] = self.now
            if self.now - self.event_seen[t] <= WILD_EVIDENCE_DAYS * DAY:
                fresh.append(t)
        if len(self.event_seen) > 2000:
            for t, _ in sorted(self.event_seen.items(), key=lambda kv: kv[1])[:1000]:
                self.event_seen.pop(t, None)
        for name in self.combat_species(obs, fresh):
            self.wild_evidence[name] = self.now

        for name in self.combat_species(obs, [t for t in fresh if self.event_seen.get(t) == self.now]):
            self.wild_fight[name] = self.now

    def cancel_animals_of(self, obs):
        out = []
        for t in lst(d(obs).get("recent_cancellations")):
            m = re.search(r"interrupted by an? ([a-z][a-z '\-]*[a-z])", str(t).lower())
            if m:
                out.append(m.group(1).strip())
        return out

    def combat_species(self, obs, events):
        """The animal species in combat reports between a citizen and an animal among `events`."""
        obs = d(obs)
        profs = {str(p.get("profession") or "").lower() for p in lst(obs.get("dwarves")) if isinstance(p, dict)}
        profs = {p for p in profs if p} | CITIZEN_WORDS
        out = []
        for t in events:
            m = COMBAT_RE.match(str(t).lower().strip())
            if not m:
                continue
            a, b = m.group(1).strip(), m.group(2).strip()
            ca, cb = citizen_noun(a, profs), citizen_noun(b, profs)
            other = b if ca and not cb else a if cb and not ca else None
            name = mark_name(other) if other else None
            if name and name not in profs:
                out.append(name)
        return out

    def wild_evidenced(self, names):
        """A combat report or an interrupt of one of these species within WILD_EVIDENCE_DAYS."""
        def same(a, b):
            wa, wb = set(a.split()), set(b.split())
            return bool(wa) and bool(wb) and (wa <= wb or wb <= wa)
        return any(isinstance(t, (int, float)) and self.now - t <= WILD_EVIDENCE_DAYS * DAY and same(n, e)
                   for n in names for e, t in self.wild_evidence.items())

    def wild_approaching(self, units):
        """One of these units is within WILD_CLOSE_TILES of a citizen, or WILD_APPROACH_TILES nearer the nearest
        citizen than at its last look (each unit's distance is remembered). No citizen positions: False."""
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        cits = [(p["x"], p["y"], p["z"]) for p in lst(self.o.get("dwarves"))
                if isinstance(p, dict) and all(num(p.get(k)) for k in ("x", "y", "z"))]
        if not cits:
            return False
        if self.wild_dist_load != self.loads:
            self.wild_dist_load = self.loads
            self.wild_dist_prev = dict(self.wild_dist)
        hit = False
        for u in units:
            u = d(u)
            if not all(num(u.get(k)) for k in ("x", "y", "z")):
                continue
            dist = min(max(abs(u["x"] - x), abs(u["y"] - y)) for x, y, z in cits if abs(u["z"] - z) <= WILD_NEAR_Z)\
                if any(abs(u["z"] - z) <= WILD_NEAR_Z for _, _, z in cits) else None
            if dist is None:
                continue
            prev = self.wild_dist_prev.get(u.get("id"))
            if dist <= WILD_CLOSE_TILES or (prev is not None and prev - dist >= WILD_APPROACH_TILES):
                hit = True
            self.wild_dist[u.get("id")] = dist
        return hit

    def wildlife_response(self):
        """Send the squad at the animal whose 'Interrupted by a <animal>' cancellations have now spanned two
        different game days (a chronic nuisance of waterside and outdoor work, ROOT_CAUSES §K — the survival gate
        loses about 18 O a citizen when it ends in a death): squad_order attack with the matched unit ids when a
        squad exists, create_squad above WILDLIFE_MIN_CIT citizens when none does. One response round a day; the
        animal must still be visible and hostile-flagged for the kill list, else the round waits. defend() is
        untouched — it keeps its own stand_down, and this step simply re-asserts while the interrupts keep coming
        (once the cancels stop past the gap, the streak is pruned and the squad stands down for good)."""
        if d(self.o.get("burrows")).get("civilian_alert"):
            return
        self.wildlife_alert()
        stamp = self.wild_stamp()
        names = [n for n in self.wild_day
                 if self.wild_from.get(n) is not None and self.wild_day[n] != self.wild_from[n]]
        if not names or self.wild_act_stamp == stamp:
            return
        squad = next(iter(lst(d(self.o.get("military")).get("squads"))), None)
        if squad is None:
            if self.cit >= WILDLIFE_MIN_CIT:
                r = self.create_squad("wild_squad", WILDLIFE_SQUAD_SIZE)
                if r:
                    self.wild_act_stamp = stamp
            return
        orders = lst(d(squad).get("orders"))
        if any(d(o).get("order") == "attack" and (d(o).get("targets_alive") or 0) > 0 for o in orders):
            self.wild_act_stamp = stamp
            return
        targets = self.wild_targets(sorted(names))
        if targets:
            self.act("wild_attack", "squad_order", {"order": "attack", "target_ids": targets}, retry=1, limit=99)
        self.wild_act_stamp = stamp

    def wild_alert_hold(self):
        """The wildlife alert this layer sounded is still within WILD_ALERT_DAYS, or (cx troop hold) one of the
        animals that sounded it still stands near the wagon (defend() keeps it on meanwhile although no invader is
        in sight; its 10-day cap still lifts it)."""
        if self.wild_alert_since is None:
            return False
        if not self.wild_budget_left() and not self.budget_fight(self.wild_watched()):


            log("wild_budget_out", day=self.day, used=round(self.wild_budget_used(), 1))
            return False
        if self.now - self.wild_alert_since <= WILD_ALERT_DAYS * DAY:


            watched = self.wild_watched()
            last = max((self.wild_watch.get(n) or 0 for n in watched), default=self.wild_alert_since)
            far_ok = not self.marked_units(MARK_RANGE, MARK_RANGE_Z) and not (
                self.wild_near_units(watched) if watched else [])
            gone = self.now - max(last, self.wild_alert_since) > WILD_GONE_DAYS * DAY
            if not (far_ok and gone):
                return True
            log("wild_gone", day=self.day, animals=watched)
            return False
        names = self.wild_watched()
        near = self.wild_near_units(names) if names else []
        marked = self.marked_units(WILD_NEAR_TILES, WILD_NEAR_Z)
        if marked:
            names = sorted(set(names) | {u["_mark"] for u in marked})
            near = near + marked
        if near:

            approach = self.wild_approaching(near)
            if not (self.wild_evidenced(names) or approach):
                log("wild_hold_no_evidence", day=self.day, animals=names, near=len(near))
                return False
            for n in names:
                self.wild_watch[n] = self.now
            log("wild_hold", day=self.day, animals=names, near=len(near), approach=approach)
            return True
        return False

    def wildlife_alert(self):
        """§K addendum (OP1 41.8: a carnotaurus killed a dwarf working outside on day 80 — 7 citizens, so neither
        defend()'s squad (14) nor the wildlife squad (WILDLIFE_MIN_CIT) existed, and defend() sounds the civilian
        alert for invaders only). On the first "Interrupted by" sighting whose animal the units query confirms
        hostile and visible, with no armed squad to answer, the civilian alert sends the civilians into the
        shelter burrow for WILD_ALERT_DAYS (defend() lifts it afterwards; its 10-day cap still holds)."""
        if self.wild_alert_since is not None or self.wild_resting()\
                or (not self.wild_budget_left() and not self.budget_fight(self.wild_watched()))\
                or self.alert_barred():
            return
        squad = next(iter(lst(d(self.o.get("military")).get("squads"))), None)
        armed = squad is not None and (d(squad).get("armed") or 0) >= 1
        bur = d(self.o.get("burrows"))
        if not self.shelter_listed(bur):
            return
        watched = self.wild_watched()
        if watched and self.may("wild_return_q", 1, 10 ** 6):



            self.last["wild_return_q"] = self.now
            near_u = self.wild_near_units(watched)
            near = [u.get("id") for u in near_u]


            if near and not (armed and self.wild_targets(watched))\
                    and (self.wild_evidenced(watched) or self.wild_approaching(near_u)):
                if self.shelter_wet("wild_return"):
                    return
                r = self.act("wild_return", "civilian_alert", {"on": True}, retry=1, limit=99)
                if r and r.get("ok"):
                    self.wild_alert_on()
                    for n in watched:
                        self.wild_watch[n] = self.now
                    log("wild_alert", day=self.day, animals=watched, reason="return", near=len(near))
                return
        seen = [n for n, last in self.wild_day.items() if last == self.wild_stamp()]
        if not seen:
            return
        if not self.may("wild_alert", 7, 99) or not self.may("wild_alert_q", 1, 10 ** 6):
            return
        self.last["wild_alert_q"] = self.now




        if armed and self.wild_targets(sorted(seen)):
            return
        animals = sorted(seen)
        if not self.wild_targets(animals):


            counts = {}
            for n in self.cancel_animals():
                counts[n] = counts.get(n, 0) + 1
            troop = sorted(n for n in seen if counts.get(n, 0) >= WILD_TROOP_CANCELS)
            if not troop or not self.wild_targets(troop, hostile_only=False):
                return
            animals = troop
        if self.shelter_wet("wild_alert"):
            return
        r = self.act("wild_alert", "civilian_alert", {"on": True}, retry=7, limit=99)
        if r and r.get("ok"):
            self.wild_alert_on()
            for n in animals:
                self.wild_watch[n] = self.now
            log("wild_alert", day=self.day, animals=sorted(seen))


    def learn_marks(self, obs):
        """Mark the species of this observation's "Interrupted by a <animal>" cancels and of its combat reports
        between a citizen and an animal ("The kea bites the mason", "The stonecrafter punches the gray langur");
        each newly marked species is logged once."""
        obs = d(obs)
        profs = {str(p.get("profession") or "").lower() for p in lst(obs.get("dwarves")) if isinstance(p, dict)}
        profs = {p for p in profs if p} | CITIZEN_WORDS
        found = []
        for t in lst(obs.get("recent_cancellations")):
            m = re.search(r"interrupted by an? ([a-z][a-z '\-]*[a-z])", str(t).lower())
            if m:
                found.append((mark_name(m.group(1)), "interrupt", str(t)))
        for t in lst(obs.get("recent_events")):
            m = COMBAT_RE.match(str(t).lower().strip())
            if not m:
                continue
            a, b = m.group(1).strip(), m.group(2).strip()
            ca, cb = citizen_noun(a, profs), citizen_noun(b, profs)
            if ca and not cb:
                found.append((mark_name(b), "combat", str(t)))
            elif cb and not ca:
                found.append((mark_name(a), "combat", str(t)))
        for name, src, text in found:
            if not name or name in profs or name in self.marked:
                continue
            if src == "interrupt":
                seen = self.mark_interrupts.setdefault(name, set())
                if len(seen) < 50:
                    seen.add(text)
                if len(seen) < MARK_LEARN_INTERRUPTS:
                    continue
            self.marked[name] = src
            log("danger_mark", day=self.day, species=name, source=src, text=text[:160])
        return found

    def others(self, day=None):
        """The units query's kind=others list. With day None: once per observation (shared with wild_units);
        with a day (the chunked advance's check, which runs without load()): once per game day."""
        if day is None:
            if self.wild_units_memo is not None and self.wild_units_memo[0] == self.loads:
                return self.wild_units_memo[1]
        elif self.mark_query is not None and self.mark_query[0] == day:
            return self.mark_query[1]
        try:
            q = self.game.query("units", kind="others", limit=300)
        except Exception as e:
            log("mark_query_error", error=repr(e)[:160])
            return []
        res = query_result(q)
        if res is None:
            log("mark_query_error", error=query_error(q))
            return []
        units = [d(u) for u in lst(res.get("units"))]
        if day is None:
            self.wild_units_memo = (self.loads, units)
        else:
            self.mark_query = (day, units)
        return units

    def mark_of(self, u):
        """The marked species name a unit matches (the longest match), or None; visitors never count."""
        if d(u).get("visitor"):
            return None
        hits = [n for n in self.marked if race_matches(d(u).get("race"), n)]
        return max(hits, key=len) if hits else None

    def marked_units(self, tiles, z, obs=None, units=None):
        """Marked units within `tiles` (x/y) and `z` levels of the wagon or a citizen, each with its mark under
        "_mark". A unit without a position, or a fort without wagon and citizen positions, counts nothing."""
        obs = d(self.o if obs is None else obs)
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        anchors = [d(d(obs.get("map")).get("wagon"))] + [p for p in lst(obs.get("dwarves")) if isinstance(p, dict)]
        anchors = [(a["x"], a["y"], a["z"]) for a in anchors if all(num(a.get(k)) for k in ("x", "y", "z"))]
        if not anchors:
            return []
        out = []
        for u in (self.others() if units is None else units):
            name = self.mark_of(u)
            if not name or not all(num(u.get(k)) for k in ("x", "y", "z")):
                continue
            if any(max(abs(u["x"] - x), abs(u["y"] - y)) <= tiles and abs(u["z"] - zz) <= z for x, y, zz in anchors):
                out.append({**u, "_mark": name})
        return out

    def danger_signs(self, resp, query=True):
        """The danger signs in one observation, as short strings: a visible game hostile, an animal's interrupt,
        the civilian alert, an insane or fell mood, a recent water_rising stop or an open breach, and a marked
        animal within MARK_RANGE ("marked:<name>") or WILD_NEAR_TILES ("near:<name>") of the wagon or a citizen.
        query=True (the chunked advance, no load()) asks the units query at most once a game day; query=False
        (after a plan pass) reuses this observation's query when the pass made one."""
        obs = d(resp.get("observation"))
        self.learn_marks(obs)
        signs = set()
        if d(obs.get("threats")).get("visible_hostiles"):
            signs.add("hostile")
        for t in lst(obs.get("recent_cancellations")):
            m = re.search(r"interrupted by an? ([a-z][a-z '\-]*[a-z])", str(t).lower())
            if m and mark_name(m.group(1)):
                signs.add("interrupt:" + mark_name(m.group(1)))
        if d(obs.get("burrows")).get("civilian_alert"):
            signs.add("alert")
        for m in lst(obs.get("moods")):
            if d(m).get("mood") in ("Berserk", "Raving", "Melancholy", "Traumatized", "Fell", "Macabre"):
                signs.add("mood:" + str(d(m).get("mood")))
        tick = d(obs.get("date")).get("abs_tick") or resp.get("tick")

        self.note_access(obs, tick)
        if self.thirst_due(tick) and not self.access_free(obs):
            signs.add("thirst")
        if self.breach or (self.water_rise_tick is not None and isinstance(tick, (int, float))
                           and tick - self.water_rise_tick <= 3 * DAY):
            signs.add("water")
        day = resp.get("day")
        if query:
            units = self.others(day if isinstance(day, int) else -1)
        elif self.wild_units_memo is not None and self.wild_units_memo[0] == self.loads:
            units = self.wild_units_memo[1]
        else:
            units = []
        for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z, obs=obs, units=units):
            signs.add("marked:" + u["_mark"])
        for u in self.marked_units(WILD_NEAR_TILES, WILD_NEAR_Z, obs=obs, units=units):
            signs.add("near:" + u["_mark"])

            surface = d(obs.get("map")).get("surface_z", getattr(self, "surface", None))
            if isinstance(surface, (int, float)) and any(
                    c["z"] >= surface and abs(c["z"] - u["z"]) <= WILD_NEAR_Z
                    and max(abs(c["x"] - u["x"]), abs(c["y"] - u["y"])) <= WILD_CLOSE_TILES
                    for c in self.citizen_spots(obs)):
                signs.add("exposed:" + u["_mark"])
        for name in self.combat_species(obs, lst(obs.get("recent_events"))):
            if name in self.marked:
                signs.add("fight:" + name)
        try:
            signs |= self.rush_signs(obs)
        except Exception as e:
            log("rush_sign_error", error=repr(e)[:160])
        return sorted(signs)

    def big_units(self):
        """cx big-beast hold: the marked units of a DANGER_BIG race within WILD_NEAR_TILES / WILD_NEAR_Z of the
        wagon or a citizen (one units query per observation, shared with the other wildlife looks)."""
        return [u for u in self.marked_units(WILD_NEAR_TILES, WILD_NEAR_Z) if big_race(u.get("race"))]

    def big_alert(self, bur, alert):
        """cx big-beast hold: a large dangerous beast near the wagon or a citizen sounds the alert with no evidence
        rule and no wildlife budget. During WILD_REST_DAYS (after the 10-day cap) only an approach re-sounds it
        (within WILD_CLOSE_TILES of a citizen, or WILD_APPROACH_TILES closer than at the last look), and that ends
        the rest. True when this pass sounded it."""
        if alert or self.wild_alert_since is not None or self.alert_barred()\
                or not self.shelter_listed(bur):
            return False
        big = self.big_units()
        if not big:
            return False
        resting = self.wild_resting()
        if resting and not self.wild_approaching(big):
            return False
        if self.shelter_wet("big_alert"):
            return False
        r = self.act("big_alert", "civilian_alert", {"on": True}, retry=0.25, limit=10 ** 6)
        if not (r and r.get("ok")):
            return False
        self.wild_alert_on(big=True)
        self.wild_rest_until = None
        for u in big:
            self.wild_watch[u["_mark"]] = self.now
        log("big_alert", day=self.day, animals=sorted({u["_mark"] for u in big}), near=len(big),
            reason="approach_in_rest" if resting else "near")
        return True

    def shelter_grow(self):
        """cx shelter: add every dug level to the Shelter burrow — each listed A site below the surface (a grown
        level box comes back under a new id and is added again; only its new tiles count), and each dug R room on a
        level whose A box is wider than create_burrow's gate or that has no A site. Wet levels are skipped. At most
        SHELTER_PER_PASS calls a pass, highest level first; an answer of nothing_designated also counts as done."""
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        below = lambda z: num(z) and (not num(self.surface) or z < self.surface)
        todo, a_levels, level_open = [], set(), []




        open_z = {b[4] for sid, b in self.shelter_boxes.items() if sid in self.shelter_level_in
                  and isinstance(b, tuple) and len(b) == 5}
        short = self.shelter_tiles() < SHELTER_TILES_PER_CIT * (self.cit or 0)
        same_open = lambda z: short and z in open_z
        level_in = set()


        landing = self.gate_landings()
        held = self.gate_pending()

        def gated(s):
            if not all(num(s.get(k)) for k in ("x", "y", "z")):
                return False
            x1, y1 = s["x"], s["y"]
            x2, y2 = x1 + max(1, int(s.get("w") or 1)) - 1, y1 + max(1, int(s.get("h") or 1)) - 1
            if any(c == s["z"] and x1 <= a <= x2 and y1 <= b <= y2 for a, b, c in landing):
                return True
            r = GATE_QUERY_RADIUS
            return any(zs - GATE_LEVELS <= s["z"] < zs and x1 <= a + r and a - r <= x2 and y1 <= b + r and b - r <= y2
                       for a, b, zs in held)

        for s in sorted(self.kind("A"), key=lambda s: -(s.get("z") or 0)):
            z = s.get("z")
            if not below(z) or not self.dry(z) or s.get("id") is None:
                continue
            if s["id"] not in self.shelter_added and gated(s):
                if s["id"] not in self.shelter_skip:
                    self.shelter_skip.add(s["id"])
                    log("shelter_gate_skip", day=self.day, site=s["id"], z=z, held=bool(held))
                continue
            if (s.get("w") or 0) > SHELTER_SIDE_MAX or (s.get("h") or 0) > SHELTER_SIDE_MAX:
                if s["id"] not in self.shelter_skip:
                    self.shelter_skip.add(s["id"])
                    log("shelter_wide", day=self.day, site=s["id"], z=z, w=s.get("w"), h=s.get("h"))
                continue
            if s["id"] not in self.shelter_added:
                n_open = self.site_open(s)
                if n_open:
                    if ("open", s["id"]) not in self.shelter_skip:
                        self.shelter_skip.add(("open", s["id"]))
                        log("shelter_open_skip", day=self.day, site=s["id"], z=z, outside=n_open)
                    continue
                if self.level_open(self.shelter_box_of(s)):
                    if ("level", s["id"]) not in self.shelter_skip:
                        self.shelter_skip.add(("level", s["id"]))
                        log("shelter_level_skip", day=self.day, site=s["id"], z=z)
                    if not same_open(z):
                        level_open.append(s)
                        continue
                    level_in.add(s["id"])
            a_levels.add(z)
            todo.append(s)
        for r in sorted(self.kind("R"), key=lambda s: -(s.get("z") or 0)):
            z = r.get("z")
            if r.get("dug") and below(z) and self.dry(z) and z not in a_levels and r.get("id") is not None\
                    and (r["id"] in self.shelter_added or not gated(r)):
                if r["id"] not in self.shelter_added and self.level_open(self.shelter_box_of(r)):
                    if ("level", r["id"]) not in self.shelter_skip:
                        self.shelter_skip.add(("level", r["id"]))
                        log("shelter_level_skip", day=self.day, site=r["id"], z=z)
                    if not same_open(z):
                        level_open.append(r)
                        continue
                    level_in.add(r["id"])
                todo.append(r)
        if not self.shelter_added and not todo and level_open:

            todo.append(level_open[0])
            level_in.add(level_open[0].get("id"))
            if self.may("shelter_level_fallback_log", 1, 10 ** 6):
                self.last["shelter_level_fallback_log"] = self.now
                log("shelter_level_fallback", day=self.day, site=level_open[0].get("id"))
        n = 0
        for s in todo:
            if s["id"] in self.shelter_added or n >= SHELTER_PER_PASS:
                continue
            args = {"site": s["id"]}
            if s.get("kind") == "R":
                args.update(self.box_wh(s, SHELTER_SIDE_MAX))
            if self.shelter_added and self.pocket_box(dict(s, **{k: args[k] for k in ("w", "h") if k in args})):
                if ("pocket", s["id"]) not in self.shelter_skip:
                    self.shelter_skip.add(("pocket", s["id"]))
                    log("shelter_pocket_skip", day=self.day, site=s["id"], z=s.get("z"))
                continue
            res = self.act("shelter_" + str(s["id"]), "create_burrow", args, retry=1, limit=3)
            if res is None:
                continue
            n += 1
            if res.get("ok") or res.get("error_code") == "nothing_designated":
                self.shelter_added.add(s["id"])
                if s["id"] in level_in:
                    self.shelter_level_in.add(s["id"])
                if all(num(s.get(k)) for k in ("x", "y", "z")):
                    bw, bh = args.get("w", s.get("w") or 1), args.get("h", s.get("h") or 1)
                    self.shelter_boxes[s["id"]] = (s["x"], s["y"], s["x"] + max(1, int(bw)) - 1,
                                                   s["y"] + max(1, int(bh)) - 1, s["z"])
                log("shelter_add", day=self.day, site=s["id"], z=s.get("z"),
                    tiles=d(res.get("result")).get("tiles_added", res.get("tiles_added")))

    def shelter_listed(self, bur):
        """cx same-pass Shelter (hint hard OP1-3 on 6c42bb2: the leader dead of INFECTION on d78 from a d0.9-2.2
        rhesus macaque beating at the wagon): a civilian-alert burrow stands, in the observation or made by a
        create_burrow this layer sent (the tool's burrow is the civ-alert Shelter). defend()'s shelter_grow made A1 on
        the d1.33 pass, but mark_guard read the pass's observation from before it, so no alert went out until the
        d2.42 pass and the leader took a second beating (28 head wounds, d2.08-2.21) in that lost day."""
        return any(d(b).get("civ_alert_burrow") for b in lst(d(bur).get("list"))) or bool(getattr(self, "shelter_made", False))

    def shelter_wet(self, what=None):
        """cx: the Shelter stands over a flood — an active breach, or a Shelter box on a level the wet-level record
        holds. No new wildlife alert sounds and no alert lock closes the hatches into it (no tool removes a level from
        a burrow). `what` names the held-back act for a once-a-day log."""
        wet = bool(self.breach) or any(box[4] in self.wet_z for box in self.shelter_boxes.values()
                                       if isinstance(box, tuple) and len(box) == 5)
        if wet and what is not None and self.wet_skip_day.get(what) != self.day:
            self.wet_skip_day[what] = self.day
            log("shelter_wet_hold", day=self.day, held=what, breach=bool(self.breach), wet_z=sorted(self.wet_z))
        return wet

    def shelter_counts(self):
        """(citizens inside the Shelter, citizens) from the observation, or (None, cit) when unknown."""
        bur = d(self.o.get("burrows"))
        shelter = next((d(b) for b in lst(bur.get("list")) if d(b).get("civ_alert_burrow")), None)
        inside = (shelter or {}).get("citizens_inside")
        ok = isinstance(inside, (int, float)) and not isinstance(inside, bool)
        return (inside if ok else None), self.cit

    def hatch_water(self, hatch):
        """cx: water tiles at a hatch's column — its tile grown by WATER_DIG_MARGIN, its level and the two below (the
        shaft it closes) — once a day, from today's fort scan or one probe; None when unmeasured."""
        hid = hatch.get("id")
        memo = self.hatch_water_memo.get(hid)
        if memo is not None and memo[0] == self.day:
            return memo[1]
        x, y, z = hatch.get("x"), hatch.get("y"), hatch.get("z")
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (x, y, z)):
            return None
        box = (x, y, 1, 1, z)
        z2 = max(0, z - 2)
        n = self.scan_count(box, WATER_DIG_MARGIN, z2, z)
        if n is None and getattr(self.game, "query", None) is not None and self.water_probe_ok():
            n = self.probe_count("hatch_%s" % hid, box, WATER_DIG_MARGIN, z2, z)
        if n is not None:
            self.hatch_water_memo[hid] = (self.day, n)
        return n

    def flood_lock_wanted(self, hatch):
        """cx: the flood lock closes the shaft only while water is measured at the hatch's column — or, unmeasured,
        while every citizen is inside the Shelter. A lock against water that is not coming through the hatch only
        shuts citizens out (cxe60d4ce OP1-3: hatch 12 locked days 13-336 on a breach whose water never reached a
        room; cxb595466 hard OP1-1: hatch 65 flood-locked with 0/14 inside on day 295)."""
        n = self.hatch_water(hatch)
        if n is not None:
            return n > 0
        inside, cit = self.shelter_counts()
        return inside is not None and isinstance(cit, (int, float)) and cit > 0 and inside >= cit

    def flood_hatch_release(self, doors):
        """cx: unlock the hatches this layer locked for a flood — every one once no breach stands (flood_recede /
        flood_outside / the local hand-down; before this nothing ever unlocked them: cxe538c50 std OP1-0 hatches
        33 and 39 locked to day 336, cx6adf843 MY1-1 hatch 64 flood-locked over an alert lock), and during a breach
        any whose column measures dry while a citizen is outside the Shelter. A hatch gone from the list is
        forgotten."""
        if not self.flood_locked:
            return
        by_id = {d(x).get("id"): d(x) for x in lst(doors.get("list")) if d(x).get("id") is not None}
        inside, cit = self.shelter_counts()
        outside = inside is None or (isinstance(cit, (int, float)) and inside < cit)
        for hid in sorted(self.flood_locked, key=lambda v: (str(type(v)), str(v).zfill(12))):
            x = by_id.get(hid)
            if x is None or not x.get("locked"):
                self.flood_locked.discard(hid)
                continue
            if self.breach and not (outside and self.hatch_water(x) == 0):
                continue
            r = self.act("flood_unlock_" + str(hid), "lock_door", {"locked": False, "door_id": hid},
                         retry=0.25, limit=10 ** 6)
            if r and r.get("ok"):
                self.flood_locked.discard(hid)
                log("flood_unlock", day=self.day, door=hid, breach=bool(self.breach), inside=inside, citizens=cit)
        if not self.breach and not self.flood_locked:
            self.hatch_id = None

    def entrance_hatches(self):
        """cx entrance hatches: (a) while no alert stands, a hatch cover goes on every surface entrance (E site, at
        most ENTRANCE_MAX) that has none — make_hatch_cover ordered when no item is free; (b) while the alert is on
        and the Shelter holds every citizen, those hatches are locked; (c) when the alert clears, or anyone is
        outside the Shelter (citizens_inside < citizens: a migrant, a soldier, a straggler), the hatches this layer
        locked are unlocked. A hatch already locked (the flood containment's) is never claimed, and the flood's own
        hatch is left alone while a breach is active."""
        doors = self.o.get("doors")
        if not isinstance(doors, dict):
            return
        self.flood_hatch_release(doors)
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        for s in self.kind("E"):
            if s.get("id") is not None and all(num(s.get(k)) for k in ("x", "y", "z")):
                self.entrances[s["id"]] = (s["x"], s["y"], s["z"])
        dl = [d(x) for x in lst(doors.get("list"))]
        by_id = {x.get("id"): x for x in dl if x.get("id") is not None}
        at = {(x.get("x"), x.get("y"), x.get("z")): x for x in dl if x.get("kind") == "hatch"}
        ents_all = sorted(self.entrances.items(), key=lambda kv: site_key(kv[0]))
        ents = ents_all
        hatches = [at[p] for _, p in ents if p in at]




        blocked = {d(x).get("id") for x in self.kind("E") if d(x).get("building")} | self.entrance_occupied
        for sid, p in ents:
            if p not in at and sid in blocked and sid not in self.entrance_occupied:
                self.entrance_occupied.add(sid)
                log("entrance_open", day=self.day, site=sid, at=p, why="building")
        missing = [sid for sid, p in ents if p not in at and sid not in blocked]
        sh = getattr(self, "shaft", None)
        if sh is not None:

            missing = [sid for sid in missing if sid != sh.get("e")
                       and self.entrances.get(sid) != (sh.get("x"), sh.get("y"), sh.get("z"))]
        bur = d(self.o.get("burrows"))
        alert = bur.get("civilian_alert") is True
        shelter = next((d(b) for b in lst(bur.get("list")) if d(b).get("civ_alert_burrow")), None)
        free = doors.get("hatch_cover_items_free") or 0
        if sh is not None and not any(p == (sh.get("x"), sh.get("y"), sh.get("z")) for p in at):
            free -= 1
        if shelter is not None and missing and not self.breach and free > 0:

            ok = [sid for sid in missing if not alert or self.hatch_safe(self.entrances.get(sid))]
            for sid in ok[:free]:
                r = self.act("entrance_hatch_" + str(sid), "build_door", {"kind": "hatch", "site": sid},
                             retry=1 if alert else 3, limit=6)
                if r and r.get("ok"):
                    log("entrance_hatch", day=self.day, site=sid, **({"alert": True} if alert else {}))
                elif r and r.get("error_code") == "tile_occupied" and sid not in self.entrance_occupied:
                    self.entrance_occupied.add(sid)
                    log("entrance_open", day=self.day, site=sid, at=self.entrances.get(sid))
            if alert and len(ok) < len(missing) and self.may("hatch_hold_log", 1, 10 ** 6):
                self.last["hatch_hold_log"] = self.now
                log("hatch_hold", day=self.day, held=[sid for sid in missing if sid not in ok])
        self.hatch_order(missing, free)
        if shelter is not None:
            self.gate_build(doors, alert)
        inside = (shelter or {}).get("citizens_inside")
        all_in = alert and num(inside) and num(self.cit) and self.cit > 0 and inside >= self.cit
        flood = self.hatch_id if self.breach else None
        if all_in and self.shelter_wet("alert_lock"):
            all_in = False
        if all_in:
            skip = self.lock_skip(ents_all, at)
            if skip:
                all_in = False
                if self.lock_skip_day != self.day:
                    self.lock_skip_day = self.day
                    log("alert_lock_skip", day=self.day, why=skip)
        if all_in:
            spots = {(c["x"], c["y"], c["z"]) for c in self.citizen_spots()}
            gates = [g for g, land in self.gate_locks() if not (spots & land)]
            for h in hatches + gates:
                hid = h.get("id")
                if hid is None or h.get("locked") or hid == flood or hid in self.flood_locked:
                    continue
                r = self.act("alert_lock_" + str(hid), "lock_door", {"locked": True, "door_id": hid},
                             retry=0.25, limit=10 ** 6)
                if r and r.get("ok"):
                    self.alert_locked.add(hid)
                    log("alert_lock", day=self.day, door=hid, inside=inside, citizens=self.cit)
            return
        for hid in sorted(self.alert_locked, key=lambda v: (str(type(v)), str(v).zfill(12))):
            x = by_id.get(hid)
            if x is None or hid == flood or hid in self.flood_locked or not x.get("locked"):
                self.alert_locked.discard(hid)
                continue
            r = self.act("alert_unlock_" + str(hid), "lock_door", {"locked": False, "door_id": hid},
                         retry=0.25, limit=10 ** 6)
            if r and r.get("ok"):
                self.alert_locked.discard(hid)
                log("alert_unlock", day=self.day, door=hid, alert=alert, inside=inside, citizens=self.cit)

    def hatch_safe(self, p):
        """cx hatch early: an entrance's stair top (x, y, z) a hatch may be built over during an alert — inside a
        Shelter box, or no marked animal within WILD_NEAR_TILES (x/y) and WILD_NEAR_Z of it."""
        if not (isinstance(p, tuple) and len(p) == 3):
            return False
        x, y, z = p
        if any(isinstance(b, tuple) and len(b) == 5 and b[4] == z and b[0] <= x <= b[2] and b[1] <= y <= b[3]
               for b in self.shelter_boxes.values()):
            return True
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)


        hostiles = [d(h) for h in lst(d(self.o.get("threats")).get("hostiles"))]
        for u in list(self.others()) + hostiles:
            if (self.mark_of(u) or u.get("hostile") or u in hostiles) and all(num(u.get(k)) for k in ("x", "y", "z"))\
                    and max(abs(u["x"] - x), abs(u["y"] - y)) <= WILD_NEAR_TILES and abs(u["z"] - z) <= WILD_NEAR_Z:
                return False
        return True

    def hatch_order(self, missing, free):
        """cx hatch early: covers on order for every hatchless entrance (the first ENTRANCE_MAX) plus HATCH_SPARE ahead
        of a new E site while fewer than ENTRANCE_MAX are listed, from day 0, alert or not, wood permitting."""
        if self.breach or self.hatch_ordered >= HATCH_ORDER_CAP:
            return
        queued = sum(max(0, x.get("left") or 0) for x in self.orders if x.get("recipe") == "make_hatch_cover")
        want = len(missing) + (HATCH_SPARE if len(self.entrances) < ENTRANCE_MAX else 0)
        need = want - max(0, free) - queued
        if need <= 0:
            return
        amount = min(need, ENTRANCE_MAX, HATCH_ORDER_CAP - self.hatch_ordered)
        if HATCH_FIRST_EARLY and self.hatch_ordered == 0 and isinstance(self.day, (int, float))\
                and self.day <= HATCH_FIRST_DAYS and self.logs() < amount + HATCH_WOOD_FLOOR:


            amount = 1
        elif self.logs() < amount + HATCH_WOOD_FLOOR:
            if self.may("hatch_wood_log", 2, 10 ** 6):
                self.last["hatch_wood_log"] = self.now
                log("hatch_wood_wait", day=self.day, need=amount, logs=self.logs())
            return
        r = self.act("hatch_early_order", "add_order", {"recipe": "make_hatch_cover", "amount": amount},
                     retry=1, limit=4 * ENTRANCE_MAX)
        if r and r.get("ok"):
            self.hatch_ordered += amount
            log("hatch_order", day=self.day, amount=amount, missing=len(missing), free=free, queued=queued)

    def squad_out(self):
        """cx: the squad holds an order that sends it to the surface: an attack (its targets are up there), or a
        station on a tile at or above the surface (or with no level read). A locked hatch would keep it from them."""
        surface = self.surface
        for sq in lst(d(self.o.get("military")).get("squads")):
            for o in lst(d(sq).get("orders")):
                o = d(o)
                if o.get("order") == "attack" and (o.get("targets_alive") is None or o.get("targets_alive") > 0):
                    return True
                if o.get("order") == "station":
                    z = o.get("z")
                    if not isinstance(z, (int, float)) or not isinstance(surface, (int, float)) or z >= surface:
                        return True
        return False

    def shelter_trap(self):
        """cx SHELTER TRAP (TRAP_* above): on an access_unseen look, poke the game into re-indexing its walkable
        groups — one workshop first (any reachable builder merges every group; a second one would find no builder
        either), then stairs from free S sites down into the citizens' part (the trapped miner digs from inside). One poke per TRAP_POKE_DAYS, TRAP_POKES an
        episode, never with drink out of stock (then thirst is not the trap)."""
        drink = self.st.get("drink")
        if not isinstance(drink, (int, float)) or isinstance(drink, bool) or drink <= 0:
            return
        if self.trap_seen < TRAP_SEEN or self.trap_pokes >= TRAP_POKES:
            return
        if self.trap_last is not None and isinstance(self.now, (int, float))\
                and self.now - self.trap_last < TRAP_POKE_DAYS * DAY:
            return
        how, r = None, None
        if self.trap_pokes == 0 and self.logs() - self.logs_guard() >= TRAP_WOOD_SPARE:
            sites = [s for s in self.kind("W") if not self.frame_on(s)]
            if sites:
                how = "workshop"
                r = self.act("trap_shop", "build_workshop", dict(self.site_args(sites[0]), type=TRAP_SHOP), retry=1,
                             limit=10 ** 6)
                if r and r.get("ok"):
                    self.sites.remove(sites[0])
        if how is None:
            pick = self.trap_stair()
            if pick is not None:
                how = "stair"
                sid, zb = pick
                r = self.act("trap_stair_" + str(sid), "dig_stairs", {"site": sid, "z_bottom": zb}, retry=1,
                             limit=10 ** 6)
        self.trap_last = self.now
        self.trap_pokes += 1
        log("trap_poke", day=self.day, how=how, ok=bool(r and r.get("ok")),
            err=(r or {}).get("error_code") if r and not r.get("ok") else None, pokes=self.trap_pokes,
            drink=drink, logs=self.logs())

    def trap_stair(self):
        """cx shelter trap: (S site id, z_bottom) for a stair from the surface into the citizens' walkable part, or
        None. One map read around the citizens below the surface; the part is walk_region from their tiles. A free S
        site qualifies at the highest level zb where its tile is a wall with an 8-neighbour in that part, every level
        between zb and the surface is wall (dig_stairs refuses a step that designates nothing) and its surface tile
        is open; and no water within TRAP_WATER_MARGIN of the column on any of those levels (probe_count; an
        unmeasured column never qualifies), and the site's dig not held by the water rules (water_ok)."""
        num = lambda v: isinstance(v, int) and not isinstance(v, bool)
        surf = self.surface
        query = getattr(self.game, "query", None)
        if not num(surf) or query is None:
            return None
        cits = [(c["x"], c["y"], c["z"]) for c in self.citizen_spots()
                if all(num(c.get(k)) for k in ("x", "y", "z")) and c["z"] < surf]
        if not cits:
            return None
        zlow = max(min(c[2] for c in cits), surf - 4)
        cx = sorted(c[0] for c in cits)[len(cits) // 2]
        cy = sorted(c[1] for c in cits)[len(cits) // 2]
        try:
            res = query_result(query("map", x=min(400, max(0, cx)), y=min(400, max(0, cy)), z=surf, z2=zlow,
                                     radius=14))
        except Exception as e:
            log("trap_map_error", day=self.day, error=repr(e)[:160])
            return None
        if res is None:
            return None
        shape, water, _ = map_tiles([res])
        under = {p: ch for p, ch in shape.items() if p[2] < surf}
        part = set()
        for c in cits:
            if c not in part:
                tiles, _ = walk_region(under, water, c)
                part |= tiles
        if not part:
            return None
        best = None
        for s in sorted(self.kind("S"), key=lambda s: site_key(s.get("id"))):
            if not s.get("free", True) or not all(num(s.get(k)) for k in ("x", "y")):
                continue
            if not self.water_ok(s):
                continue
            x, y = s["x"], s["y"]
            if shape.get((x, y, surf)) not in STRANDED_FLOOR:
                continue
            for zb in range(surf - 1, zlow - 1, -1):
                if shape.get((x, y, zb)) != "#":
                    break
                if any((x + dx, y + dy, zb) in part for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    n = self.probe_count("trap_" + str(s.get("id")), (x, y, 1, 1, surf), TRAP_WATER_MARGIN, zb,
                                         surf)
                    if n == 0 and not any(z in self.wet_z for z in range(zb, surf)):
                        cand = (surf - zb, site_key(s.get("id")), s.get("id"), zb)
                        best = cand if best is None or cand < best else best
                    break
        return (best[2], best[3]) if best else None

    def pocket_box(self, box):
        """cx SHELTER POCKET (above): True when every walkable tile of box (dict x, y, z, w, h; below the surface)
        lies in a part with exactly one entrance stair while another part holds two or more (the fort's main part). One
        map query of the entrances and the box, the surface level read as wall (the part is the underground one); a
        part that runs off the read levels or window, a box with no walkable tile, or a fort with fewer than two
        entrances is no pocket. Memoised per box and day."""
        num = lambda v: isinstance(v, int) and not isinstance(v, bool)
        if not all(num(d(box).get(k)) for k in ("x", "y", "z")):
            return False
        bx, by, bz = box["x"], box["y"], box["z"]
        bw = box.get("w") if num(box.get("w")) else 1
        bh = box.get("h") if num(box.get("h")) else 1
        key = (bx, by, bz, bw, bh)
        memo = self.pocket_memo.get(key)
        if memo is not None and memo[0] == self.day:
            return memo[1]
        out = False
        surf = self.surface
        query = getattr(self.game, "query", None)
        ents = [(e["x"], e["y"]) for e in self.kind("E") if num(e.get("x")) and num(e.get("y"))]
        if num(surf) and query is not None and len(ents) >= 2 and bz < surf:
            xs = [x for x, _ in ents] + [bx, bx + bw - 1]
            ys = [y for _, y in ents] + [by, by + bh - 1]
            cx, cy = (min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2
            radius = max(max(xs) - min(xs), max(ys) - min(ys)) // 2 + 3
            z2 = max(0, surf - POCKET_LEVELS)
            res = None
            reads = self.pocket_reads[1] if self.pocket_reads[0] == self.day else 0
            if radius <= 20 and bz >= z2 and reads < POCKET_READS_PER_DAY:
                self.pocket_reads = (self.day, reads + 1)
                try:
                    res = query_result(query("map", x=min(400, max(0, cx)), y=min(400, max(0, cy)), z=surf, z2=z2,
                                             radius=radius))
                except Exception as e:
                    log("pocket_map_error", day=self.day, error=repr(e)[:160])
            if res is not None:
                shape, water, _ = map_tiles([res])
                under = {p: ("#" if p[2] >= surf else ch) for p, ch in shape.items()}
                parts, ok = [], True
                for x in range(bx, bx + bw):
                    for y in range(by, by + bh):
                        p = (x, y, bz)
                        if under.get(p) not in STRANDED_FLOOR or any(p in q for q in parts):
                            continue
                        tiles, opened = walk_region(under, water, p)
                        edge = any((t[0] + dx, t[1] + dy, t[2]) not in under for t in tiles
                                   for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                        if opened or edge or not tiles:
                            ok = False
                            break
                        parts.append(tiles)
                    if not ok:
                        break
                if ok and parts:
                    stairs = [(x, y, surf - 1) for x, y in ents]
                    pocket = []
                    for q in parts:
                        mine = [t for t in stairs if t in q]
                        if len(mine) != 1:
                            pocket.append(False)
                            continue


                        rest, best = [t for t in stairs if t not in q and under.get(t) in STRANDED_FLOOR], 0
                        while rest:
                            tiles, opened = walk_region(under, water, rest[0])
                            best = max(best, sum(1 for t in rest if t in tiles))
                            rest = [t for t in rest[1:] if t not in tiles]

                        pocket.append(best >= 2)
                    out = all(pocket)
        self.pocket_memo[key] = (self.day, out)
        return out

    def lock_skip(self, ents, at):
        """cx: why the alert lock must not go on now (None: it may): the safe state before a hands-off window; the
        squad sent to the surface (squad_out); or an entrance into the Shelter that a lock would not close — no built
        hatch over it and no closed inner gate (with more entrances than ENTRANCE_MAX, or one still open, locking the
        rest seals nothing and only blocks those who would come in or go out)."""
        if self.safe_held:
            return "safe_state"
        if self.squad_out():
            return "squad_out"
        open_ = [sid for sid, p in ents
                 if not (p in at and d(at[p]).get("built", True)) and not self.gate_closed(sid)]
        if open_:
            return "open:" + ",".join(str(s) for s in open_[:6])
        return None

    def mark_guard(self):
        """Treat a marked animal near the fort like a game enemy. Within WILD_NEAR_TILES of the wagon or a
        citizen: the civilian alert (the wildlife alert's hold keeps it while one stays near, its 10-day cap and
        rest still let the civilians eat, and it re-sounds when one comes back). An armed squad of MARK_SQUAD_MIN+
        (every member armed, a uniform on) is stationed on the nearest marked animal of a DANGER_WEAK species only
        (squad_order attack refuses a non-hostile unit: not_a_hostile); it stands down once no marked animal is
        within MARK_RANGE. A large or unknown species gets no soldiers (a soldier is a citizen too).
        cx rescue station: a squad of MARK_SQUAD_MIN+ with MARK_RESCUE_ARMED+ armed is stationed on the citizen a weak
        marked animal is on (within WILD_CLOSE_TILES of one on the surface, or of any after a fight/interrupt), and
        at the foot of an unhatchable entrance while the alert stands with a weak marked animal near."""
        self.mark_arrivals()
        self.gate_waiting = False
        near = self.marked_units(WILD_NEAR_TILES, WILD_NEAR_Z)
        near_all = list(near)
        bur = d(self.o.get("burrows"))
        alert = bur.get("civilian_alert")
        sounded = self.big_alert(bur, alert)
        watched = set(self.wild_watched())
        if near and all(u["_mark"] in watched for u in near):



            if not (self.wild_evidenced(sorted({u["_mark"] for u in near})) or self.wild_approaching(near)):
                near = []
        pre = [] if near else self.mark_preempt(watched)
        sound = near or pre
        if sound and not alert and not sounded and self.wild_alert_since is None and not self.wild_resting()\
                and not self.alert_barred()\
                and (self.wild_budget_left() or self.budget_fight(sorted({u["_mark"] for u in sound})))\
                and self.shelter_listed(bur)\
                and not self.shelter_wet("mark_alert") and not self.stranded_only(sound, pre=bool(pre)):
            r = self.act("mark_alert", "civilian_alert", {"on": True}, retry=1, limit=99)
            if r and r.get("ok"):
                self.wild_alert_on()
                for u in sound:
                    self.wild_watch[u["_mark"]] = self.now
                log("mark_alert", day=self.day, animals=sorted({u["_mark"] for u in sound}), near=len(sound),
                    **({"pre": True} if pre else {}))




        alert = alert or bool(d(self.o.get("burrows")).get("civilian_alert"))
        squad = d(next(iter(lst(d(self.o.get("military")).get("squads"))), None))
        weak = [u for u in near if u["_mark"] in DANGER_WEAK and not u.get("hostile")]
        weak_all = [u for u in near_all if u["_mark"] in DANGER_WEAK and not u.get("hostile")]
        members = lst(squad.get("members"))
        armed = squad.get("armed") or 0
        uniform = squad.get("uniform") not in (None, "none")
        ready = bool(squad) and len(members) >= MARK_SQUAD_MIN and armed >= len(members) and uniform

        rescue = bool(squad) and len(members) >= MARK_SQUAD_MIN and armed >= MARK_RESCUE_ARMED and uniform
        hostile_now = d(self.o.get("threats")).get("visible_hostiles")


        squad_ids = {d(m).get("id") for m in members}



        far_off = set(self.stranded) if self.stranded and not (squad_ids & self.stranded) else set()
        threats = self.mark_threats(weak_all, skip=squad_ids | far_off) if rescue and not hostile_now else []
        if threats:
            u, c = min(threats, key=lambda uc: max(abs(uc[0]["x"] - uc[1]["x"]), abs(uc[0]["y"] - uc[1]["y"])))
            r = self.act("mark_rescue", "squad_order", {"order": "station", "x": c["x"], "y": c["y"], "z": c["z"]},
                         retry=0.25, limit=10 ** 6)
            if r and r.get("ok"):
                self.mark_station = self.now
                self.mark_kind = "mark_rescue"
                self.gate_post = False
                log("mark_rescue", day=self.day, species=u["_mark"], unit=u.get("id"), citizen=c.get("id"),
                    name=str(c.get("name") or "")[:40], x=c["x"], y=c["y"], z=c["z"])
            self.mark_hold = self.now
            return
        gates = self.open_entrances()
        if gates and [u for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z) if u["_mark"] in DANGER_WEAK]:
            self.gate_mark_seen = self.now
        if self.mark_station is not None and self.mark_kind in ("mark_gate", "mark_station") and not hostile_now\
                and self.mark_clear_wait(squad, armed, standing=True, gate=self.mark_kind == "mark_gate"):
            return



        armable = len(self.armable_ids(squad)) if squad else 0
        gate_ready = bool(squad) and len(members) >= MARK_SQUAD_MIN and max(armed, armable) >= MARK_RESCUE_ARMED\
            and uniform
        weak_range = [u for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z)
                      if u["_mark"] in DANGER_WEAK and not u.get("hostile")] if gates else []
        if gates and weak_range and not weak_all:
            weak_all = sorted(weak_range, key=lambda u: min(max(abs(u["x"] - g[0]), abs(u["y"] - g[1]))
                                                             for g in gates))
        after_lift = isinstance(self.day, (int, float)) and self.alert_seen_day is not None\
            and self.day - self.alert_seen_day <= WILD_REST_DAYS
        if not (weak_all and gates and gate_ready and not hostile_now and (alert or sounded or after_lift)):
            self.shaft_since = None
            self.shaft_rest = False
            if not (self.mark_station is not None and self.mark_kind == "mark_gate"):
                self.mark_wait_since = None
        elif not self.shaft_guard_due(weak_all, gates):
            self.shaft_rest = True


            if self.mark_station is not None and self.gate_post:
                r = self.act("shaft_stand_down", "squad_order", {"order": "stand_down"}, retry=0.25, limit=10 ** 6)
                if r and r.get("ok"):
                    self.mark_station = None
                    self.gate_post = False
                    log("shaft_guard_rest", day=self.day, species=weak_all[0]["_mark"],
                        since=round((self.now - self.shaft_since) / DAY, 1))
            return
        else:
            self.shaft_rest = False
        if weak_all and gates and gate_ready and not hostile_now and (alert or sounded or after_lift):






            if self.mark_clear_wait(squad, armed, gate=True):
                return
            wx, wy = weak_all[0]["x"], weak_all[0]["y"]
            gx, gy, gz = min(gates, key=lambda p: max(abs(p[0] - wx), abs(p[1] - wy)))

            first, other = (gz, gz - 1) if SHAFT_GUARD_TOP else (gz - 1, gz)
            z = other if self.gate_top else first
            if self.mark_station is not None and self.mark_kind == "mark_gate" and self.station_held(squad, gx, gy, z):

                self.gate_post = True
                self.mark_hold = self.now
                return
            r = self.act("mark_gate", "squad_order", {"order": "station", "x": gx, "y": gy, "z": z}, retry=1, limit=99)
            if r and r.get("ok"):
                self.mark_station = self.now
                self.mark_kind = "mark_gate"
                self.gate_post = True
                self.mark_hold = self.now
                log("mark_gate", day=self.day, species=weak_all[0]["_mark"], x=gx, y=gy, z=z)
            elif r is not None:
                self.gate_top = not self.gate_top
            return






        pressing = bool(weak) and (self.wild_evidenced(sorted({u["_mark"] for u in weak}))
                                   or self.wild_approaching(weak))
        if pressing:
            self.mark_hold = self.now
            for u in weak:
                self.mark_settled.pop(u["_mark"], None)
        held = self.mark_hold is not None and self.now - self.mark_hold <= MARK_HOLD_DAYS * DAY
        fresh = [u for u in weak if pressing or self.now - self.mark_settled.get(u["_mark"], -10 ** 12)
                 > WILD_MEMORY_DAYS * DAY]



        keep_gate = self.mark_station is not None and self.mark_kind == "mark_gate" and self.gate_post\
            and bool(gates) and not hostile_now and self.gate_mark_seen is not None\
            and self.now - self.gate_mark_seen <= GATE_GONE_DAYS * DAY
        if keep_gate:
            if self.may("gate_keep_log", 1, 10 ** 6):
                self.last["gate_keep_log"] = self.now
                log("gate_keep", day=self.day, seen=round((self.now - self.gate_mark_seen) / DAY, 1), alert=bool(alert))
            return
        if fresh and ready and not hostile_now and (pressing or held or self.mark_station is None)\
                and not self.mark_clear_wait(squad, armed):
            wag = d(d(self.o.get("map")).get("wagon"))
            wx, wy = wag.get("x", fresh[0]["x"]), wag.get("y", fresh[0]["y"])
            u = min(fresh, key=lambda v: max(abs(v["x"] - wx), abs(v["y"] - wy)))
            r = self.act("mark_station", "squad_order", {"order": "station", "x": u["x"], "y": u["y"], "z": u["z"]},
                         retry=1, limit=99)
            if r and r.get("ok"):
                if self.mark_station is None:
                    self.mark_hold = self.now
                self.mark_station = self.now
                self.mark_kind = "mark_station"
                self.gate_post = False
                log("mark_station", day=self.day, species=u["_mark"], unit=u.get("id"), x=u["x"], y=u["y"], z=u["z"])
            return
        near_weak = [v for v in self.marked_units(MARK_RANGE, MARK_RANGE_Z) if v["_mark"] in DANGER_WEAK]
        if self.mark_station is not None and not hostile_now and (not near_weak or not held):
            r = self.act("mark_stand_down", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
            if r and r.get("ok"):
                self.mark_station = None
                self.gate_post = False
                for v in near_weak:
                    self.mark_settled[v["_mark"]] = self.now
                log("mark_stand_down", day=self.day, settled=sorted({v["_mark"] for v in near_weak}))

    def mark_arrivals(self):
        """cx pre-emptive alert: stamps each marked species seen within MARK_RANGE (of the wagon or a citizen) this
        pass, and its arrival tick when it was not seen there for MARK_NEW_DAYS (or ever, in this process)."""
        seen = getattr(self, "mark_last_seen", None)
        if seen is None:
            self.mark_last_seen, self.mark_arrived = {}, {}
            seen = self.mark_last_seen
        for n in sorted({u["_mark"] for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z)}):
            t = seen.get(n)
            if t is None or self.now - t > MARK_NEW_DAYS * DAY:
                self.mark_arrived[n] = self.now
            seen[n] = self.now

    def stranded_only(self, units, pre=False):
        """cx STRANDED ALERT SKIP (above): True (and logged) when every one of these marked units stands farther than
        STRANDED_ALERT_TILES (x/y) or WILD_NEAR_Z levels from the wagon and from every citizen not in the stranded set,
        and within that range of a stranded citizen. False with nobody stranded, with a game-hostile unit among them or
        game hostiles in sight, or when a reachable anchor is within range."""
        if not self.stranded or not units:
            return False
        if any(d(u).get("hostile") for u in units) or d(self.o.get("threats")).get("visible_hostiles"):
            return False
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        wag = d(d(self.o.get("map")).get("wagon"))
        cits = self.citizen_spots()
        reach = [c for c in cits if c.get("id") not in self.stranded]
        if all(num(wag.get(k)) for k in ("x", "y", "z")):
            reach.append({"id": "wagon", "x": wag["x"], "y": wag["y"], "z": wag["z"]})
        cut = [c for c in cits if c.get("id") in self.stranded]

        def nearest(u, group):
            ds = [max(abs(c["x"] - u["x"]), abs(c["y"] - u["y"])) for c in group if abs(c["z"] - u["z"]) <= WILD_NEAR_Z]
            return min(ds) if ds else None

        rows, near_cut = [], False
        for u in units:
            if not all(num(u.get(k)) for k in ("x", "y", "z")):
                return False
            dr, dc = nearest(u, reach), nearest(u, cut)
            if dr is not None and dr <= STRANDED_ALERT_TILES:
                return False
            near_cut = near_cut or (dc is not None and dc <= STRANDED_ALERT_TILES)
            rows.append({"unit": u.get("id"), "animal": u.get("_mark"), "at": (u["x"], u["y"], u["z"]),
                         "to_stranded": dc, "to_reachable": dr})
        if not near_cut:
            return False
        for u in units:
            self.strand_skipped[u.get("_mark")] = self.now
        if self.may("alert_skip_stranded_log", 1, 10 ** 6):
            self.last["alert_skip_stranded_log"] = self.now
            log("alert_skip_stranded", day=self.day, pre=pre, animals=sorted({r["animal"] for r in rows}),
                stranded=sorted(self.stranded, key=str), units=rows[:12])
        return True

    def mark_preempt(self, watched=()):
        """cx pre-emptive alert (PREEMPT_* above): the marked units of a species that arrived within
        PREEMPT_WINDOW_DAYS and is not watched, standing within PREEMPT_TILES (x/y) and WILD_NEAR_Z levels of a
        citizen on the surface (z at or above surface_z: outside the Shelter's dug levels)."""
        arrived = getattr(self, "mark_arrived", None) or {}
        surface = d(self.o.get("map")).get("surface_z", getattr(self, "surface", None))
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        if not num(surface):
            return []
        out_c = [c for c in self.citizen_spots() if c["z"] >= surface]
        if not out_c:
            return []
        out = []
        for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z):
            n = u["_mark"]
            t = arrived.get(n)
            if t is not None and n in self.strand_skipped:
                t = max(t, self.strand_skipped[n])
            if n in watched or t is None or self.now - t > PREEMPT_WINDOW_DAYS * DAY:
                continue
            if any(max(abs(c["x"] - u["x"]), abs(c["y"] - u["y"])) <= PREEMPT_TILES
                   and abs(c["z"] - u["z"]) <= WILD_NEAR_Z for c in out_c):
                out.append(u)
        return out

    def citizen_spots(self, obs=None):
        """The citizens' positions in an observation (the dwarves list: children too)."""
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        return [p for p in lst(d(self.o if obs is None else obs).get("dwarves"))
                if isinstance(p, dict) and all(num(p.get(k)) for k in ("x", "y", "z"))]

    def stranded_home(self):
        """cx stranded: the fort's own surface tiles — the wagon and the surface entrances (E sites)."""
        num = lambda v: isinstance(v, int) and not isinstance(v, bool)
        home = []
        wag = d(d(self.o.get("map")).get("wagon"))
        if wag.get("present", True) and all(num(wag.get(k)) for k in ("x", "y", "z")):
            home.append((wag["x"], wag["y"], wag["z"]))
        for s_ in self.kind("E"):
            if all(num(s_.get(k)) for k in ("x", "y", "z")):
                home.append((s_["x"], s_["y"], s_["z"]))
        return home

    def home_holding(self):
        """cx STRANDED HOME: True while a citizen the alert called home still stands on the surface more than
        STRANDED_FAR_TILES from every home tile, within STRANDED_HOME_DAYS of the call. Clears the call otherwise."""
        hc = self.home_call
        if not hc:
            return False
        if self.now - hc["since"] > STRANDED_HOME_DAYS * DAY:
            log("home_call_end", day=self.day, why="days", ids=sorted(hc["ids"], key=str))
            self.home_call = None
            return False
        home = self.stranded_home()
        surface = self.surface
        out = []
        for c in self.citizen_spots():
            if c.get("id") in hc["ids"] and isinstance(surface, int) and c["z"] >= surface and home\
                    and min(max(abs(c["x"] - h[0]), abs(c["y"] - h[1])) for h in home) > STRANDED_FAR_TILES:
                out.append(c["id"])
        if not out:
            log("home_call_end", day=self.day, why="home", ids=sorted(hc["ids"], key=str))
            self.home_call = None
            return False
        return True

    def home_call_alert(self):
        """cx STRANDED HOME: sound the civilian alert for a fresh call (the Shelter is where the alert sends them)."""
        if not self.home_holding():
            return
        bur = d(self.o.get("burrows"))
        if bur.get("civilian_alert") or self.alert_barred()\
                or not self.shelter_listed(bur) or self.shelter_wet("home_call"):
            return
        r = self.act("home_call", "civilian_alert", {"on": True}, retry=1, limit=10 ** 6)
        if r and r.get("ok"):
            self.alert_since = self.now
            if isinstance(self.o.get("burrows"), dict):
                self.o["burrows"]["civilian_alert"] = True
            log("home_call", day=self.day, ids=sorted(self.home_call["ids"], key=str))

    def stranded_survey(self):
        """cx STRANDED (above): every STRANDED_SCAN_DAYS, while a citizen stands on the surface more than
        STRANDED_FAR_TILES (x/y) from every home tile, one map survey of the surface level and the one above and
        below it (STRANDED_RADIUS squares over the map), and self.stranded is set from it. A survey that loses a
        query keeps the last answer (nothing new is measured). A stranded citizen seen below the surface or within
        the home tiles' reach is dropped at once."""
        surface = self.surface
        num = lambda v: isinstance(v, int) and not isinstance(v, bool)
        if not num(surface) or not isinstance(self.day, (int, float)):
            return
        home = self.stranded_home()
        cits = self.citizen_spots()
        by_id = {c.get("id"): c for c in cits}
        for i in sorted(self.stranded, key=str):
            c = by_id.get(i)
            if c is None or c["z"] < surface or (c["x"], c["y"], c["z"]) in self.stranded_fort\
                    or (home and min(max(abs(c["x"] - h[0]), abs(c["y"] - h[1])) for h in home) <= STRANDED_FAR_TILES):
                self.stranded.discard(i)
                log("stranded_back", day=self.day, citizen=i, at=None if c is None else (c["x"], c["y"], c["z"]))
        if not home:
            return
        far = [c for c in cits if c["z"] >= surface
               and min(max(abs(c["x"] - h[0]), abs(c["y"] - h[1])) for h in home) > STRANDED_FAR_TILES]


        far = [c for c in far if (c["x"], c["y"], c["z"]) not in self.stranded_known or c.get("id") in self.stranded]
        if not far:
            return
        gap = STRANDED_JOIN_DAYS if any(c.get("id") in self.stranded for c in far) else STRANDED_SCAN_DAYS
        if self.stranded_day is not None and self.day - self.stranded_day < gap:
            return
        query = getattr(self.game, "query", None)
        size = d(self.o.get("map")).get("size_tiles")
        if query is None or not (isinstance(size, (list, tuple)) and len(size) >= 2 and num(size[0]) and num(size[1])):
            return
        self.stranded_day = self.day
        step = 2 * STRANDED_RADIUS + 1
        answers = []
        for cy in range(STRANDED_RADIUS, size[1] + STRANDED_RADIUS, step):
            for cx in range(STRANDED_RADIUS, size[0] + STRANDED_RADIUS, step):
                try:
                    r = query("map", x=min(400, max(0, cx)), y=min(400, max(0, cy)), z=min(300, surface + 1),
                              z2=max(0, surface - 1), radius=STRANDED_RADIUS)
                except Exception as e:
                    log("stranded_survey_error", day=self.day, error=repr(e)[:160])
                    return
                res = query_result(r)
                if res is None:
                    log("stranded_survey_error", day=self.day, error=query_error(r))
                    return
                answers.append(res)
        shape, water, _ = map_tiles(answers)
        checked = {c["id"] for c in far}
        found = (self.stranded - checked) | stranded_of(shape, water, far, home, surface)
        fort_tiles = set()
        for p_ in home:
            if p_ not in fort_tiles:
                fort_tiles |= walk_region(shape, water, p_)[0]
        known = set(fort_tiles)
        for p_ in [(by_id[i]["x"], by_id[i]["y"], by_id[i]["z"]) for i in sorted(found, key=str) if i in by_id]:
            if p_ not in known:
                known |= walk_region(shape, water, p_)[0]
        self.stranded_fort = fort_tiles
        self.stranded_known = known

        joined = sorted((i for i in (self.stranded & checked) - found if i in by_id
                         and walk_region(shape, water, (by_id[i]["x"], by_id[i]["y"], by_id[i]["z"]))[0] & set(home)),
                        key=str)
        if joined:

            log("stranded_joined", day=self.day, citizens=joined,
                at={str(i): (by_id[i]["x"], by_id[i]["y"], by_id[i]["z"]) for i in joined if i in by_id})
            ids = set(joined) | set((self.home_call or {}).get("ids") or ())
            self.home_call = {"ids": ids, "since": self.now}
        if found != self.stranded:
            log("stranded", day=self.day, citizens=sorted(found, key=str), queries=len(answers),
                at={str(i): (by_id[i]["x"], by_id[i]["y"], by_id[i]["z"]) for i in sorted(found, key=str)
                    if i in by_id})
        self.stranded = set(found)

    def mark_threats(self, units, obs=None, skip=()):
        """cx rescue station: (unit, citizen) pairs — a marked unit and the nearest citizen within WILD_CLOSE_TILES
        (x/y) and WILD_NEAR_Z levels of it, when that citizen is on the surface (outside: the Shelter is the dug
        levels) or the species fought or interrupted a citizen within WILD_EVIDENCE_DAYS."""
        obs = d(self.o if obs is None else obs)
        surface = d(obs.get("map")).get("surface_z", getattr(self, "surface", None))
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        cits = [c for c in self.citizen_spots(obs) if c.get("id") not in skip]
        out = []
        for u in units:
            if not all(num(u.get(k)) for k in ("x", "y", "z")):
                continue
            close = [c for c in cits if max(abs(c["x"] - u["x"]), abs(c["y"] - u["y"])) <= WILD_CLOSE_TILES
                     and abs(c["z"] - u["z"]) <= WILD_NEAR_Z]
            if not close:
                continue
            outside = [c for c in close if num(surface) and c["z"] >= surface]
            pool = outside or (close if self.wild_evidenced([u.get("_mark") or ""]) else [])
            if pool:
                out.append((u, min(pool, key=lambda c: max(abs(c["x"] - u["x"]), abs(c["y"] - u["y"])))))
        return out

    def mark_pressing(self):
        """cx rescue station: the marked species that keep the 10-day cap waiting — one within WILD_CLOSE_TILES of a
        citizen, or within WILD_NEAR_TILES of one with a citizen fight or interrupt within WILD_EVIDENCE_DAYS."""
        cits = self.citizen_spots()
        if not cits:
            return []
        out = set()
        for u in self.marked_units(WILD_NEAR_TILES, WILD_NEAR_Z):
            near_c = [c for c in cits if abs(c["z"] - u["z"]) <= WILD_NEAR_Z]
            dist = min((max(abs(c["x"] - u["x"]), abs(c["y"] - u["y"])) for c in near_c), default=None)
            if dist is None or dist > WILD_NEAR_TILES:
                continue
            if dist <= WILD_CLOSE_TILES or self.wild_evidenced([u["_mark"]]):
                out.add(u["_mark"])

        for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z):
            if any(max(abs(u["x"] - gx), abs(u["y"] - gy)) <= WILD_CLOSE_TILES and abs(u["z"] - gz) <= WILD_NEAR_Z
                   for gx, gy, gz in self.open_entrances()):
                out.add(u["_mark"])
        return sorted(out)

    def fight_pressing(self):
        """cx FIGHT HOLD: the marked species that fought a citizen within FIGHT_HOLD_DAYS (the load its report first
        showed) with a unit of it anywhere within MARK_RANGE (fliers cross 50 tiles between daily looks)."""
        if not FIGHT_HOLD_DAYS:
            return []
        fought = [set(n.split()) for n, t in self.wild_fight.items()
                  if isinstance(t, (int, float)) and self.now - t <= FIGHT_HOLD_DAYS * DAY]
        if not fought:
            return []
        out = set()
        for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z):
            w = set(u["_mark"].split())
            if any(w and f and (w <= f or f <= w) for f in fought):
                out.add(u["_mark"])
        return sorted(out)

    def open_entrances(self):
        """cx rescue station: the surface entrances (E sites) with no hatch over them that cannot get one — a
        building stands on the stair tile (the site's building flag, or build_door answered tile_occupied)."""
        doors = d(getattr(self, "o", None)).get("doors")
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        at = set()
        if isinstance(doors, dict):
            at = {(x.get("x"), x.get("y"), x.get("z")) for x in map(d, lst(doors.get("list")))
                  if x.get("kind") == "hatch"}
        out = []
        for s in self.kind("E"):
            p = (s.get("x"), s.get("y"), s.get("z"))
            if all(num(v) for v in p) and p not in at\
                    and (s.get("building") or s.get("id") in self.entrance_occupied)\
                    and not self.gate_closed(s.get("id")):
                out.append(p)
        return sorted(out)


    def unhatchable(self):
        """cx inner gate: (E id, (x, y, z)) of each surface entrance with a building on its stair tile (the site's
        flag, or build_door answered tile_occupied) and no hatch over it."""
        doors = d(getattr(self, "o", None)).get("doors")
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        at = set()
        if isinstance(doors, dict):
            at = {(x.get("x"), x.get("y"), x.get("z")) for x in map(d, lst(doors.get("list")))
                  if x.get("kind") == "hatch"}
        out = []
        for s in self.kind("E"):
            p = (s.get("x"), s.get("y"), s.get("z"))
            if s.get("id") is not None and all(num(v) for v in p) and p not in at\
                    and (s.get("building") or s.get("id") in self.entrance_occupied):
                out.append((s["id"], p))
        return sorted(out, key=lambda kv: str(kv[0]))

    def gate_doors(self, sid):
        """cx inner gate: {z: the built door (doors.list entry) on that level's gate tile, or None}."""
        dl = [d(x) for x in lst(d(d(getattr(self, "o", None)).get("doors")).get("list"))]
        at = {(x.get("x"), x.get("y"), x.get("z")): x for x in dl if x.get("kind") == "door"}
        return {z: at.get(g["at"]) for z, g in self.gates.get(sid, {}).items()}

    def gate_closed(self, sid):
        """cx inner gate: every level the entrance's shaft touches has its separating door standing (built)."""
        doors = self.gate_doors(sid)
        return bool(doors) and all(x is not None and x.get("built", True) for x in doors.values())

    def gate_landings(self):
        """cx inner gate: every (x, y, z) tile outside a chosen gate door (the stair side) — never Shelter."""
        out = set()
        for g in self.gates.values():
            for lv in g.values():
                out |= lv["landing"]
        return out

    def gate_candidates(self, pos):
        """cx inner gate: the listed D sites within GATE_RADIUS (x/y) of the shaft on the GATE_LEVELS below it."""
        x, y, zs = pos
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        return [s for s in self.kind("D") if s.get("id") is not None and all(num(s.get(k)) for k in ("x", "y", "z"))
                and zs - GATE_LEVELS <= s["z"] < zs and max(abs(s["x"] - x), abs(s["y"] - y)) <= GATE_RADIUS]

    def gate_pending(self):
        """cx inner gate: the shafts (x, y, z of the surface stair) whose D sites have not been surveyed yet — the
        Shelter waits on their boxes until the survey says where the landing is."""
        out = []
        for sid, pos in self.unhatchable():
            ds = self.gate_candidates(pos)
            if ds and tuple(sorted(str(s["id"]) for s in ds)) != self.gate_seen.get(sid)\
                    and not self.gate_closed(sid):
                out.append(pos)
        return out

    @staticmethod
    def gate_plan(levels, x1, y1, pos, ds):
        """cx inner gate (pure): from a map query's shape rows, the doors that shut the shaft at pos=(x, y, zs) off
        from the rest of each level it touches. levels: {z: [row strings]} (row i is y1 + i, char j is x1 + j);
        ds: D sites. Returns ({z: {"site", "at", "landing"}}, reason): an empty plan with the reason when any level
        of the shaft has no D site that separates a landing of at most GATE_LANDING_MAX tiles, holding no other way
        down, from a larger inner side."""
        def shape(z, x, y):
            rows = levels.get(z)
            if not rows or y < y1 or y - y1 >= len(rows) or x < x1 or x - x1 >= len(rows[y - y1]):
                return "?"
            return rows[y - y1][x - x1]

        def flood(z, start, block):
            seen, todo = {start}, [start]
            while todo:
                cx, cy = todo.pop()
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        p = (cx + dx, cy + dy)
                        if p in seen or p == block or shape(z, *p) in GATE_SOLID:
                            continue
                        seen.add(p)
                        todo.append(p)
            return seen

        x, y, zs = pos
        shaft, z = [], zs - 1
        while shape(z, x, y) in ("X", "<"):
            shaft.append(z)
            if shape(z, x, y) == "<":
                break
            z -= 1
        if not shaft:
            return {}, "no_shaft"
        if shape(shaft[-1], x, y) == "X" and shaft[-1] - 1 not in levels:
            return {}, "shaft_deeper"
        plan = {}
        for z in shaft:
            full = flood(z, (x, y), None)
            best = None
            for s in ds:
                if s.get("z") != z or (s["x"], s["y"]) not in full:
                    continue
                door = (s["x"], s["y"])
                land = flood(z, (x, y), door)
                rest = full - land - {door}
                if len(land) > GATE_LANDING_MAX or len(rest) <= len(land):
                    continue
                if any(shape(z, *p) in GATE_DOWN for p in land if p != (x, y)):
                    continue
                if best is None or len(land) < len(best[1]):
                    best = (s, land)
            if best is None:
                return {}, "no_door_z%d" % z
            s, land = best
            plan[z] = {"site": s["id"], "at": (s["x"], s["y"], z), "landing": frozenset((a, b, z) for a, b in land)}
        return plan, "ok"

    @staticmethod
    def gate_doorways(levels, x1, y1, pos):
        """cx inner gate (pure): the one-tile doorways a map query's shape rows show on the shaft's levels within
        GATE_RADIUS of it — observe.lua's own D test (a FLOOR tile with walls on two opposite sides and a walkable
        tile on each of the other two), as pseudo-sites {"id": "doorway", x, y, z} for gate_plan."""
        walk = set(".<>X")
        x, y, zs = pos
        out = []
        for z in sorted(levels, reverse=True):
            rows = levels.get(z) or []
            if not isinstance(z, int) or not zs - GATE_LEVELS <= z < zs:
                continue

            def at(a, b):
                return rows[b - y1][a - x1] if 0 <= b - y1 < len(rows) and 0 <= a - x1 < len(rows[b - y1]) else "?"
            for j, row in enumerate(rows):
                for i, ch in enumerate(row):
                    a, b = x1 + i, y1 + j
                    if ch != "." or max(abs(a - x), abs(b - y)) > GATE_RADIUS:
                        continue
                    ns = at(a, b - 1) == "#" and at(a, b + 1) == "#" and at(a - 1, b) in walk and at(a + 1, b) in walk
                    ew = at(a - 1, b) == "#" and at(a + 1, b) == "#" and at(a, b - 1) in walk and at(a, b + 1) in walk
                    if ns or ew:
                        out.append({"id": "doorway", "kind": "doorway", "x": a, "y": b, "z": z})
        return out

    def gate_survey(self):
        """cx inner gate: for each entrance no hatch can close, once per new set of nearby D sites (one map query a
        game day), find the door on every level its shaft touches that cuts the landing off; a full plan is kept
        (a gate's D site drops out of the list once its door is built, so the plan is never re-derived from it)."""
        for sid, pos in self.unhatchable():
            if sid in self.gates:
                continue
            ds = self.gate_candidates(pos)
            key = tuple(sorted(str(s["id"]) for s in ds))
            if key == self.gate_seen.get(sid):
                continue
            if self.gate_probe_day == self.day:
                return
            self.gate_probe_day = self.day
            x, y, zs = pos
            try:
                r = self.game.query("map", x=min(400, max(0, x)), y=min(400, max(0, y)), z=min(300, max(0, zs - 1)),
                                    z2=max(0, zs - GATE_LEVELS), radius=GATE_QUERY_RADIUS)
            except Exception as e:
                log("gate_probe_error", day=self.day, site=sid, error=repr(e)[:160])
                return
            res = d(query_result(r))
            if not lst(res.get("levels")):
                log("gate_probe_error", day=self.day, site=sid, error=query_error(r) if query_result(r) is None
                    else "no levels")
                return
            levels = {d(lv).get("z"): lst(d(lv).get("shape")) for lv in lst(res.get("levels"))}
            plan, why = self.gate_plan(levels, res.get("x1") or 0, res.get("y1") or 0, pos, ds)
            self.gate_seen[sid] = key
            if not plan:






                spots = self.gate_doorways(levels, res.get("x1") or 0, res.get("y1") or 0, pos)
                alt, alt_why = self.gate_plan(levels, res.get("x1") or 0, res.get("y1") or 0, pos, spots)
                log("gate_none", day=self.day, site=sid, at=pos, reason=why, d_sites=list(key),
                    doorways=[[p["x"], p["y"], p["z"]] for p in spots][:12],
                    unlisted_gate=({z: list(g["at"]) for z, g in alt.items()} if alt else alt_why))
                continue
            self.gates[sid] = plan
            log("gate_plan", day=self.day, site=sid, at=pos,
                doors={z: [g["site"], list(g["at"])] for z, g in plan.items()},
                landing={z: len(g["landing"]) for z, g in plan.items()})
            for aid, (bx1, by1, bx2, by2, bz) in sorted(self.shelter_boxes.items(), key=lambda kv: str(kv[0])):
                if any(bz == c and bx1 <= a <= bx2 and by1 <= b <= by2 for a, b, c in self.gate_landings()):
                    log("gate_landing_sheltered", day=self.day, site=sid, box=aid)


    def gate_build(self, doors, alert):
        """cx inner gate: while no alert stands, the planned doors are built (make_door ordered when none is free);
        a door the game refuses for good (its D site gone) drops the plan so the next survey can find another."""
        if alert or self.breach:
            return
        free = doors.get("door_items_free") or 0
        for sid in sorted(self.gates, key=str):
            for z, door in sorted(self.gate_doors(sid).items(), reverse=True):
                if door is not None or sid not in self.gates:
                    continue
                g = self.gates[sid][z]
                if free <= 0:
                    if not self.pending("make_door") and self.gate_door_ordered < 2 * ENTRANCE_MAX:
                        r = self.act("gate_door_order", "add_order", {"recipe": "make_door", "amount": 1},
                                     retry=7, limit=8)
                        if r and r.get("ok"):
                            self.gate_door_ordered += 1
                    return
                r = self.act("gate_door_" + str(g["site"]), "build_door", {"kind": "door", "site": g["site"]},
                             retry=1, limit=4)
                if r and r.get("ok"):
                    free -= 1
                    log("gate_door", day=self.day, entrance=sid, site=g["site"], at=list(g["at"]))
                elif r and r.get("error_code") in ("site_used", "unknown_site", "wrong_tile_shape", "tile_occupied"):
                    log("gate_drop", day=self.day, entrance=sid, site=g["site"], code=r.get("error_code"))
                    del self.gates[sid]
                    self.gate_seen.pop(sid, None)

    def gate_locks(self):
        """cx inner gate: [(door entry, landing tiles)] of the built gate doors of closed gates."""
        out = []
        for sid in sorted(self.gates, key=str):
            if self.gate_closed(sid):
                for z, door in self.gate_doors(sid).items():
                    out.append((door, self.gates[sid][z]["landing"]))
        return out

    def step(self, resp):
        """One pass of the deterministic layer for the plain loop. Returns the number of actions it ran."""
        self.count = 0
        try:
            self.load(resp)
        except (HandsOff, GameOver):
            raise
        except Exception as e:
            log("guard_load_error", error=repr(e)[:300])
            return 0
        try:
            self.plan()
        except (HandsOff, GameOver):
            raise
        except ActionLimit:
            log("guard_action_limit")
        except Exception as e:
            log("guard_error", error=repr(e)[:300])
        try:
            self.risk = self.danger_signs(resp, query=False)
        except Exception as e:
            log("risk_error", error=repr(e)[:200])
            self.risk = []
        return self.count

    def pace(self, resp):
        if d(self.o.get("threats")).get("visible_hostiles") or self.o.get("moods") or self.risk:
            return 1

        if ((self.o.get("dig_designations_pending") or 0) > 0 and not self.flooded_pending())\
                or (resp.get("day") or 0) < 14:
            return 1
        return 2

    def run(self):
        self.game.task()
        while True:
            resp = self.game.observe()
            if resp.get("game_over"):
                return "game_over"
            for _ in range(MAX_PASSES):
                self.load(resp)
                self.count = 0
                try:
                    self.plan()
                except (ActionLimit, HandsOff, GameOver):
                    raise
                except Exception as e:
                    log("plan_error", error=repr(e)[:300])
                if not self.count:
                    break
                resp = self.game.observe()
            self.load(resp)
            self.risk = self.danger_signs(resp, query=False)
            r = self.game.act("advance_days", {"days": self.pace(resp)})
            log("advance", day=r.get("day"), stopped=d(r.get("result")).get("stopped"), cit=self.cit,
                drink=self.st.get("drink"), food=self.st.get("food_edible"))
            if d(d(r.get("result")).get("stopped")).get("reason") == "water_rising":
                self.water_rising_stop()
            if r.get("game_over") or d(r.get("result")).get("hands_off"):
                return "over"


def main():
    task = load_task()
    game = GameClient(task.game_url)
    log("start", task=repr(task))


    ov = Overseer(game, goal=(task.task or {}).get("goal", ""), days=(task.task or {}).get("days") or task.days)
    while True:
        try:
            reason = ov.run()
            log("done", reason=reason)
            return 0
        except ActionLimit as e:
            log("action_limit", error=str(e)[:200])
            game.act("advance_days", {"days": 1})
        except (HandsOff, GameOver) as e:
            log("done", reason=type(e).__name__)
            return 0
        except GameAPIError as e:
            log("game_error", error=str(e)[:300])
            exit_safe(ov, "game_error")
            return 1
        except Exception as e:
            log("run_error", error=repr(e)[:300])
            exit_safe(ov, "run_error")
            raise


def exit_safe(ov, why):
    """cx safe state on the standalone run's exit path: lift the alert and open this layer's locks if the game still
    answers (best effort; nothing may raise from here)."""
    try:
        resp = ov.game.observe()
        if resp.get("game_over"):
            return
        ov.load(resp)
        ov.count = 0
        ov.safe_state(why)
    except Exception as e:
        log("exit_safe_error", why=why, error=repr(e)[:200])


if __name__ == "__main__":
    sys.exit(main())
