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
SEED_KIND_STAY_DAYS = 40
CARAVAN_DROP_MIN = 10
CARAVAN_DROP_RATE = 3
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
    return max(1, -(-(cit + 24) // 30))
def ols_slope(pts):
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
    r = d(r)
    if r.get("ok") is False or "result" not in r:
        return None
    res = r.get("result")
    if not isinstance(res, dict) or res.get("ok") is False:
        return None
    return res
def query_error(r):
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
SURFACE_GUARD = True
SQUAD_PREARM = True
PREARM_HOLD_DAYS = 3
SURFACE_GUARD_TILES = 30
SURFACE_GUARD_EVIDENCE = True
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
    w = str(name or "").lower().replace("stray ", " ").split()
    race = next((STRAY_RACE[x] for x in w if x in STRAY_RACE and x not in ("hen", "chick")), None)
    if race is None and any(x in ("hen", "chick") for x in w):
        race = "CHICKEN"
    female = True if any(x in STRAY_FEMALE for x in w) else False if any(x in STRAY_MALE for x in w) else None
    adult = False if any(x in STRAY_YOUNG for x in w) else (True if female is not None else None)
    return race, female, adult
def grazer_race(race):
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
    out, regions = set(), []
    for c in citizens:
        c = d(c)
        p = (c.get("x"), c.get("y"), c.get("z"))
        if c.get("id") is None or not all(isinstance(v, int) and not isinstance(v, bool) for v in p) \
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
    m = re.fullmatch(r"([A-Za-z]*)(\d+)", str(sid))
    return (m.group(1), int(m.group(2)), "") if m else (str(sid), -1, str(sid))
def mark_name(text):
    t = str(text or "").lower().replace("_", " ").strip()
    if not t or "stray" in t.split() or "(tame)" in t or t in ("dwarf", "combat"):
        return None
    w = [x for x in t.split() if x not in SEX_AGE]
    return " ".join(w) or None
def race_matches(race, name):
    r = set(str(race or "").lower().replace("_", " ").split())
    n = str(name or "").lower().split()
    return bool(n) and set(n) <= r
def when_sig(items):
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
    s = when_sig(items)
    return s[i][2] if len(s) > i else None
def _overseer_body(name):
    """Compile one file of the Overseer class body (harness_body_N.py, next to this file)."""
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    with open(path, encoding="utf-8") as f:
        return compile(f.read(), path, "exec")


class Overseer:
    exec(_overseer_body('harness_body_1.py'), globals(), locals())
    exec(_overseer_body('harness_body_2.py'), globals(), locals())
    exec(_overseer_body('harness_body_3.py'), globals(), locals())
    exec(_overseer_body('harness_body_4.py'), globals(), locals())


del _overseer_body
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
