"""Overseer: a deterministic Dwarf Fortress manager for game API v0. Reads facts, acts through the public tools only.

Order of work follows the score's gates: survive, supply, wellbeing, housing. Every step is idempotent and rate
limited, so a refused action is retried later rather than looped on. Makes no model calls.
Run: python -m overseer   (reads DFBENCH_TASK)

Lineage: the layer and its regular steps are e-man07's submission 6e775ed2, unchanged. Three housing-measurement
steps (seats counted inside dining zones, re-zoning loose furniture, a dining zone over seats placed elsewhere) and
the extra Carpenters for a migrant wave come from that author's efac22bf revision; both are declared in
dependencies.json. This copy adds the "closer" steps (endgame supply mode for the scored final stretch, the
pre-window boost on lab tasks, a housing check sized to the window), an action report for the model loop, and the
ownership record the model-loop guard reads (owned orders).

This build adds goal policies for the lab tasks' own goal text (the approach and the thresholds are
GordoAR's 5ef22a35 and its source 0bc9b753, adapted to this digest+layer architecture; both are declared): on a
hands-off task whose goal says drink must not end lower, brew without a drink ceiling; where it says every dwarf
must have a placed bed, the carpenters' queue holds beds only, a second Carpenters builds from the start, beds that
don't fit the dorm go to the next-largest dug area, and the model's advances are slowed so the layer can keep up
(`beds_unmet()`, read by the model loop).
"""
import json
import math
import re
from collections import Counter
import sys
import time

from dfbench_client import ActionLimit, GameAPIError, GameClient, GameOver, HandsOff, load_task
from overseer.openplay import OpenPlayRules, BUTCHER_LEAD, FEAST_DAYS

DAY = 1200
MAX_PER_PASS = 12
MAX_PASSES = 3
DRINK_CAP = 300
MEAL_CAP = 200
WINTER_PREP_DAYS = 150  # full-year open play: the endgame brew and barrel orders from this many days out (about day
                        #   186, autumn), so drink builds up before the frozen winter that holds the scored stretch (d35)
ENDGAME_DAYS = 64       # closer: the scored final stretch is the last quarter of a long run, clipped to 28 days;
                        #   the supply slope over it must be >= 0, so production is raised a month before it starts
WINDOW_PREP_DAYS = 14   # closer: days before a lab task's hands-off window when its orders and beds are secured
REPORT_KEEP = 24        # action report lines kept for the model loop
MOOD_WORKSHOP = {
    "WOODCRAFT": "Craftsdwarfs", "STONECRAFT": "Craftsdwarfs", "BONECARVE": "Craftsdwarfs", "CARPENTRY": "Carpenters",
    "MASONRY": "Masons", "WOOD_BURNING": "WoodFurnace", "GLASSMAKER": "GlassFurnace", "TANNER": "Leatherworks",
    "LEATHERWORK": "Leatherworks", "WEAVING": "Loom", "CLOTHESMAKING": "Clothiers", "FORGE_WEAPON": "MetalsmithsForge",
    "FORGE_ARMOR": "MetalsmithsForge", "FORGE_FURNITURE": "MetalsmithsForge", "METALCRAFT": "MetalsmithsForge",
    "CUTGEM": "Jewelers", "ENCRUSTGEM": "Jewelers", "MECHANICS": "Mechanics", "POTTERY": "Kiln", "BOWYER": "Bowyers",
}

PROG_FROM_DAY = 40      # wealth for the Hamlet rank (20 citizens and 5000 created wealth), full-year games only:
PROG_WEALTH = 5500      #   from this day, until created wealth reaches this, a Craftsdwarfs and one daily order of
PROG_LOGS = 25          #   wood crafts that runs only while this many logs are in stock (i34-9's fa9c13cc progress())
SQUAD_NEAR = 45         # d64, open tasks: the squad fights only a hostile this close to the wagon, all members armed
ZONE_SIDE = 20          # make_zone refuses a site box wider or taller than this
PLACE_SIDE = 40         # place_furniture refuses a site box wider or taller than this
ZONE_RECHECK = 3        # days after which a dining site this layer zoned may be zoned again for furniture still
ZONE_TRIES = 3          #   outside every dining zone, at most this many times a site
ZONE_FAILS = 3          # refusals of a site's dining make_zone after which it is not asked again
HOUSE_ROOMS = 4         # open tasks (d42): extra 3x3 rooms dug for beds or dining seats when no site can take them
FURN_STUCK_DAYS = 10    # open tasks (d52): furniture unbuilt when DF reported a suspended construction and still
                        #   unbuilt this many days later is not counted (no tool resumes a suspended construction)
SUSPENDED = re.compile(r"suspended the construction of .*\b(Table|Chair|Throne|Bed)\.")
HOUSE_FROM_DAY = 10     # ... not before this task day (the layer's own rooms are designated first)
BED_TRIES = 3           # open tasks (d42): bed sites tried in one pass
BED_REFUSED = ("no_space", "bad_arguments", "site_used", "unknown_site", "wrong_site_kind")
BED_LIMIT = 99          # place_furniture bed calls one site's key may make (d44: a spent key is no bed site)
STUCK_DAYS = 3          # a workshop construction suspended this long is built again elsewhere (no tool resumes it;
STUCK_REBUILDS = 2      #   a stuck Carpenters left a full-year fort with no bed, table or chair), this many times
BREW_MIN = 1            # brewable plants the standing brew order needs (2 before d33: one plant waited unbrewed;
                        #   ryan48's 6954125a brews from one)
OFFICE_ZONES = 3        # new office zones this layer makes at most in a game (d36)
OFFICE_ZONE_GAP = 2     # days after a new office zone before another may be made: the zone list may lag a pass
OFFICE_LEVEL_DAY = 10   # d39: a level is an office site only from this task day (a room before): a level being dug
                        #   changes its A site's id and box, and an office zoned over it early was lost track of
OFFICE_EARLY = True     # open tasks: the manager's office and its chair before anything else wants the chairs, at any
                        #   population (d34; before, from 14 citizens)
WATER_STAIRS = True     # the first staircase avoids water (mpjunior92's 58eec0ff water-aware stair site):
STAIR_WATER = 8         #   a default S site with water this near, on the surface or the level below, is replaced
                        #   by the listed S site farthest from water
DRY_ROOMS = True        # d56, open tasks: a room is dug only where its box and the tiles around it on its level show no
                        #   revealed water, ice or magma (map query); else the next smaller box from the same corner,
                        #   else not at all. dig_room measures w,h from the R site's top-left corner: a 9x7 dormitory ran
                        #   into a river one level down and drowned a dwarf on day 3 (MY1 1025-p, both games there)
ROOM_SIZES = {(9, 7): ((9, 7), (7, 5), (5, 5), (5, 3), (3, 3)), (7, 5): ((7, 5), (5, 5), (5, 3), (3, 3))}
SITE_ANY_TYPE = True    # d59, open tasks: a W site a workshop was placed on is not offered to any other type (build)
WET_MATERIAL = "iRkoM"  # map query material layer: frozen liquid, river, brook, pool, magma
WET_SHAPE = "_~"        # ... shape layer: brook bed, brook top

MEETING = True          # d37, open tasks: idle dwarves gather at the wagon on the surface while no meeting area exists
                        #   (d32 games: 91% of idle sightings on the surface, median 2 tiles from the wagon; no game
                        #   made one). One meeting_area zone over the dug dining or dormitory level keeps them below
MEETING_TRIES = 3       #   ground. make_zone answers that may be asked for it in a game
MEETING_SITE_TRIES = 2  #   ... of them a site, before the next site is asked
MEETING_ANY_DAY = 40    #   before this day only a site a dining or dormitory zone overlaps; from it any fitting site
SURGE_BEDS = 50
SURGE_CARPENTERS = 3
SURGE_DORM_DEPTH = 3

def log(kind, **kw):
    print(json.dumps({"t": round(time.time(), 2), "kind": kind, **kw}, default=str), flush=True)


def d(v):
    return v if isinstance(v, dict) else {}


def lst(v):
    return v if isinstance(v, list) else []


def num(v):
    """An int field of the observation, or None when it is missing or unreadable (a section can read 'ERR: ...')."""
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def overlap(a, b):
    """The boxes `a` and `b` (top-left x, y, z, w, h) share a tile."""
    try:
        return (a["z"] == b["z"] and a["x"] < b["x"] + (b.get("w") or 1) and b["x"] < a["x"] + (a.get("w") or 1)
                and a["y"] < b["y"] + (b.get("h") or 1) and b["y"] < a["y"] + (a.get("h") or 1))
    except (KeyError, TypeError):
        return False


def covers(area, item):
    """The box `area` (top-left x, y, z, w, h) holds the box or tile `item` whole (GordoAR's 5dfdcf15 check)."""
    try:
        return (area["z"] == item["z"] and area["x"] <= item["x"] and area["y"] <= item["y"]
                and area["x"] + (area.get("w") or 1) >= item["x"] + (item.get("w") or 1)
                and area["y"] + (area.get("h") or 1) >= item["y"] + (item.get("h") or 1))
    except (KeyError, TypeError):
        return False


class Overseer(OpenPlayRules):
    def __init__(self, game, goal="", days=0):
        self.game = game
        self.surge = "migrant" in str(goal).lower()   # the task's own text says more dwarves are on the way
        self.days = days or 0
        self.drink_growth = False   # goal policy (set from GET /task by set_task): brew with no drink ceiling
        self.beds_first = False     # goal policy: the carpenters' queue holds beds only until everyone sleeps
        self.tries, self.last = {}, {}
        self.roles = {}          # room id -> farm | dorm | dine | office
        self.now = 0
        self.alert_since = None
        self.hands_off = None
        self.days_left = None
        self.day = None
        self.owned = set()       # order ids this layer added: the model loop refuses to cancel them
        self.brew_own = set()    # of `owned`: its daily brew orders (the ceiling-less goal policy reads this)
        self.craft_ids = set()   # of `owned`: its repeating wood-crafts orders (the growth push reads this)
        self.dine_full = {}      # site id -> (box, open tiles) when it had no room for dining furniture
        self.zoned = {}          # site id -> {mark, at, n}: when this layer last made a dining zone over it
        self.dine_placed = {}    # site id -> tiles this layer placed dining tables and chairs on
        self.dine_retired = set()   # site ids no longer used for dining (retired_site)
        self.bed_full = {}       # open tasks (d42): site id -> (box, open tiles) when it refused beds for size or room
        self.report = []         # the layer's recent actions (day, tool, args, outcome), for the model loop
        self.done = set()        # closer keys whose order was accepted once: never re-added
        self.full_sites = set()  # W site ids a workshop was built on, so the next build takes another site
        self.stuck_since = {}    # (workshop id, type, x, y, z) -> tick its construction was first seen suspended
        self.built_n = {}        # workshop type -> build_workshop calls the game accepted
        self.dorm_box = None
        self.lab = False         # the task has a hands-off window (set_task); open play is everything else
        self.lab_no_fish = False   # d69: the drought lab (LT01): nobody fishes there either
        self.culled = {}         # cull key -> tick of its last pass
        self.brew_stopped = False
        self.sheltered = {}      # A site id -> its open tiles when it was last added to the shelter burrow
        self.stairs = {}         # E site id -> (x, y, z): every surface stair ever listed
        self.office_tried = set()   # site ids a new office zone has used (OFFICE_ZONES)
        self.stair_pick = None   # the S site id chosen for the first staircase (stair_site), decided once
        self.room_fit = {}       # d56: (room id, w, h) -> the dry box size dug there, or None (wet), decided once
        self.wet_rooms = set()   # d56: R site ids whose 3x3 box has water, ice or magma in or beside it: never dug
        self.office_made_at = -10 ** 9   # tick of the last office zone this layer made (OFFICE_ZONE_GAP)
        self.office_bad = set()  # site ids where the game refused the office chair (d38): never an office site again
        self.office_zoned = set()   # d45: site ids an office zone was made on (the observation lags this pass)
        self.furn_suspects = {}  # d52: furniture id -> tick of a suspension report it was still unbuilt at
        self.prev_events = Counter()  # d52: the last observation's recent_events, by text (d54: with their counts)
        self.deep_seen = None    # d53: tick of the last reading with deep water near the wagon (openplay.see_water)
        self.freeze = None       # d53: (last tick with it, first tick without) when it froze, until it is seen again
        self.thawed_at = None    # d53: tick it was seen again after a freeze, near the predicted thaw
        self.winter_brew_id = None   # order id of winter_supply's brew order, until endgame_supply replaces it
        self.meeting_made = None   # the site id of the meeting area this layer made (MEETING)
        self.meeting_tries = 0     # ... make_zone answers for it this game
        self.surface_seen = None   # the surface level (the wagon's z) as last reported: kept through a reply without it
        self.lock = None         # the standing wildlife lockdown: {since, phase: hold|release, why, alert_off, ...}
        self.wild_off = False    # a lockdown could not protect once: no more of them this game
        self.own_locks = set()   # door ids of hatches this layer sent a lock for and has not confirmed open again
        self.rest_until = 0      # tick before which a lockdown may not begin again
        self.rest_far_until = 0  # d67: tick before which only a hostile within WILD_NEAR_REST may begin one
        self.alert_pending = False   # an alert was asked for and the answer never came: it is still this layer's
        self.calm = None         # open play: True while nobody may fish or hunt (the labour plugin, no Fishery, a
                                 #   late Butchers); False where a Fishery or Butchers stood already; None unread
        self.calm_fail = 0       # refusals of the labour plugin
        self.calm_ok = False     # the labour plugin accepted the request once
        self.beast_seen = False  # open play: a large wild predator was in sight at the last look
        self.beast_view = None   # ... that look for the model loop's digest: {day, sure, seen: [(tiles, race)]}
        self.thaw_alert = False  # open play: the civilian alert is this layer's, for the spring thaw (openplay.thaw)
        self.beast_told = []     # ... and the species last logged
        self.beast_fail = 0      # ... looks that failed in a row
        self.beast_spent = 0     # ... ticks spent shut from the first sight of one to the opening of the fort
        self.fell = None         # open play, the first felling: None undecided, {"since", "blind"} waiting for a
                                 #   large predator to leave, False no longer waiting

    def set_task(self, info):
        """Goal policies from the task's own public text (GET /task). A hands_off field means a lab task."""
        t = d(info)
        goal = str(t.get("goal") or "").casefold()
        self.lab = bool(t.get("hands_off"))
        self.drink_growth = bool(t.get("hands_off")) and "drink must not end lower" in goal
        self.beds_first = bool(t.get("hands_off")) and "every dwarf must have a placed bed" in goal
        # d69: the drought lab (LT01: its goal asks for a brew and nothing of food) plays without fishing, as open play
        # does: the fisher's risk without the catch's use. Plan y67: an alligator killed the fishing militia commander
        # on day 17 of an LT01 game on 1501-p (partial 0.75); without fishing 16 of 16 LT01 games scored 1.00. Not
        # LT03 (d67 had it): there the mood's Craftsdwarf's workshop stayed suspended from day 1 ("item blocking
        # site") after the labour plugin's day-0 reshuffle, and the moody dwarf went insane (partial 0; 8 of 8 LT03
        # games full without the plugin). Not LT02 and LT08: they count food every day of their window, and the
        # lowest food in it was 3 to 5 in three of eight recorded LT02 games even with the catch.
        self.lab_no_fish = self.lab and "brew" in goal and "food" not in goal

    def beds_unmet(self):
        """True while the bed goal still has a shortfall on the last observation the layer saw."""
        return self.beds_first and self.cit > 0 and (self.placed.get("bed") or 0) < self.cit

    # ---- the action gate
    def may(self, key, retry=2, limit=6):
        return self.tries.get(key, 0) < limit and self.now - self.last.get(key, -10 ** 9) >= retry * DAY

    def act(self, key, tool, args, retry=2, limit=6):
        """One rate-limited action. Returns the response if it ran, else None."""
        if key in self.done or not self.may(key, retry, limit):
            return None
        self.tries[key] = self.tries.get(key, 0) + 1
        self.last[key] = self.now
        r = self.game.act(tool, args)
        self.count += 1
        log("act", key=key, tool=tool, args=args, ok=r.get("ok"), code=r.get("error_code"),
            err=str(r.get("error") or "")[:160])
        if r.get("ok"):
            self.tries[key] = max(0, self.tries[key] - 1)
        if r.get("ok") and tool in ("add_order", "add_manager_order"):
            res = r.get("result") if isinstance(r.get("result"), dict) else r
            oid = res.get("order_id")
            if oid is not None:
                self.owned.add(oid)
            if (oid is not None and isinstance(args, dict) and args.get("recipe") == "brew_drink"
                    and args.get("repeat") == "daily"):
                self.brew_own.add(oid)
            if oid is not None and isinstance(args, dict) and args.get("job") == "MakeCrafts" \
                    and args.get("repeat") == "daily":
                self.craft_ids.add(oid)
            if args.get("repeat") and key.startswith("o_") and key.endswith(("_end", "_win")):
                self.done.add(key)   # a standing closer order is added once per game
        self.report = (self.report + [{"day": self.day, "tool": tool, "args": args, "ok": bool(r.get("ok")),
                                       **({"error_code": r.get("error_code"), "error": str(r.get("error") or "")[:100]}
                                          if not r.get("ok") else {})}])[-REPORT_KEEP:]
        return r

    # ---- facts
    def load(self, resp):
        self.o = d(resp.get("observation"))
        self.st, self.map = d(self.o.get("stocks")), d(self.o.get("map"))
        self.adm = d(self.o.get("administrators"))
        self.hands_off = resp.get("hands_off_in_days")
        self.days_left = resp.get("days_left") if isinstance(resp.get("days_left"), int) else None
        self.day = resp.get("day")
        self.now = d(self.o.get("date")).get("abs_tick") or resp.get("tick") or 0
        self.people = [x for x in lst(self.o.get("dwarves")) if isinstance(x, dict)]
        self.cit = self.adm.get("citizens") or len(self.people)
        self.sites = [s for s in lst(self.map.get("sites")) if isinstance(s, dict)]
        self.orders = [x for x in lst(self.o.get("orders")) if isinstance(x, dict)]
        if isinstance(self.o.get("orders"), list):
            present = {x.get("id") for x in self.orders}
            self.brew_own.intersection_update(present)
            self.craft_ids.intersection_update(present)
        self.zones = [z for z in lst(self.o.get("zones")) if isinstance(z, dict)]
        self.free = d(self.st.get("furniture_free"))
        self.placed = {}
        for f in lst(self.o.get("furniture")):
            if isinstance(f, dict):
                self.placed[f.get("kind")] = self.placed.get(f.get("kind"), 0) + 1
        if isinstance(self.o.get("furniture"), list):     # d52: which unbuilt items a suspension report may concern
            waiting = {f.get("id") for f in self.o["furniture"] if isinstance(f, dict) and f.get("built") is False
                       and f.get("id") is not None}
            self.furn_suspects = {i: t for i, t in self.furn_suspects.items() if i in waiting}
            # d54: reports carry no id or tick, and two suspensions of the same kind and wood read the same: a report is
            # new when its line shows more often than on the last observation (one that replaces an identical line
            # leaving the 7-day window on the same pass goes unseen)
            events = Counter(t for t in (e if isinstance(e, str) else d(e).get("text")
                                         for e in lst(self.o.get("recent_events"))) if isinstance(t, str))
            if any(n > self.prev_events.get(t, 0) and SUSPENDED.search(t) for t, n in events.items()):
                for i in waiting:      # the report names no building: every item waiting then is a suspect
                    self.furn_suspects.setdefault(i, self.now)
            self.prev_events = events
        if isinstance(self.o.get("workshops"), list):
            seen = set()
            for w in lst(self.o.get("workshops")):
                w = d(w)
                if w.get("id") is not None and not w.get("built") and any(
                        d(j).get("job") == "ConstructBuilding" and d(j).get("suspended") for j in lst(w.get("job_details"))):
                    key = self.shop_key(w)
                    self.stuck_since.setdefault(key, self.now)
                    seen.add(key)
            self.stuck_since = {k: v for k, v in self.stuck_since.items() if k in seen}
        else:
            self.stuck_since = {}    # an unreadable listing breaks the record: suspensions are timed afresh
        self.surface = self.map.get("surface_z")
        if isinstance(self.surface, int) and not isinstance(self.surface, bool):
            self.surface_seen = self.surface
        self.see_water()         # d53: the water near the wagon, for the thaw (openplay.thaw_due)

    def kind(self, k):
        return [s for s in self.sites if s.get("kind") == k]

    def pending(self, recipe):
        return any(x.get("recipe") == recipe and (x.get("left") or 0) > 0 for x in self.orders)

    def standing(self, recipe):
        return any(x.get("recipe") == recipe and x.get("repeat") for x in self.orders)

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

    # ---- the work, most urgent first
    def plan(self):
        self.mood()
        self.defend()
        self.management()
        self.workshops()
        self.digging()
        self.house_rooms()
        self.farms()
        self.supply()
        if self.open_play():
            self.provision()
        self.furnish()
        self.meeting()
        self.rezone()
        self.closer()
        self.progression_push()

    def management(self):
        if not self.adm.get("manager_active_for_orders"):
            free = [p for p in self.people if not p.get("positions") and p.get("adult", True)]
            free.sort(key=lambda p: -(p.get("organizer_skill") or 0))
            self.act("manager", "appoint_manager", {"dwarf_id": free[0]["id"]} if free else {}, retry=1, limit=8)
        plugins = d(self.o.get("plugins"))
        for name in ("autochop", "seedwatch"):
            if plugins.get(name) != "on":
                if name == "autochop" and self.open_task() and self.felling_waits():
                    continue          # open play: the first trees wait while a large predator is in sight
                self.act("plug_" + name, "enable_automation", {"name": name}, retry=5)
        if self.o.get("farm_plots") and plugins.get("autofarm") != "on":
            self.act("plug_autofarm", "enable_automation", {"name": "autofarm"}, retry=5)
        if self.open_task() or self.lab_no_fish:
            self.no_fishing(plugins)
        self.office()

    def office(self):
        if not self.open_task():
            return self.office_lab()
        return self.office_open()

    def office_lab(self):
        """Lab tasks: d32's office step unchanged (labs replay identically to the promoted harness). DF stops
        validating orders around 20 citizens unless the manager has an office with a chair."""
        if self.cit < 14 or not self.adm.get("manager_active_for_orders"):
            return
        mo = self.adm.get("manager_office")
        if isinstance(mo, dict) and mo.get("chair"):
            return
        mgr = self.adm.get("MANAGER_id")
        offices = self.zone("office")
        mine = next((z for z in offices if mgr is not None and z.get("owner") == mgr), None)
        if not mine:
            spare = next((z for z in offices if z.get("owner") is None), None)
            if spare and mgr is not None:
                self.act("office_assign", "assign_zone", {"zone_id": spare["id"], "dwarf_id": mgr})
                return
            room = next(iter(self.dug_rooms("office") + self.dug_rooms("dine") + self.kind("A")), None)
            if room:
                result = self.act("office_zone", "make_zone", {"kind": "office", "site": room["id"]})
                if self.surge and result and result.get("ok") and (self.free.get("chair") or 0) > 0:
                    self.act("office_chair", "place_furniture", {"kind": "chair", "site": room["id"]})
            return
        if d(mine.get("furniture")).get("chair") or d(mine.get("furniture_planned")).get("chair"):
            return
        if (self.free.get("chair") or 0) > 0:
            room = next((s for s in self.sites if s.get("kind") in "RA" and s.get("z") == mine.get("z")
                         and s.get("x") == mine.get("x") and s.get("y") == mine.get("y")), None)
            room = room or next(iter(self.dug_rooms("office") + self.kind("A")), None)
            if room:
                self.act("office_chair", "place_furniture", {"kind": "chair", "site": room["id"]})


    def office_open(self):
        """DF validates orders from about 20 citizens only while the manager has an office with a built chair. Any office
        zone assigned to the manager counts (in game, 2026-11-11: orders validated at 30 citizens with the first of
        three offices chairless), though the observation's manager_office names only the first one, so the layer
        reads every office zone the manager owns. While none holds a chair, the office gets the first free chair, on
        a site where one fits: a dug room, else a level with open floor, never a one-tile stair landing. On the long
        open tasks this starts at once (OFFICE_EARLY): one wave can take a fort from 10 citizens to 20, and an office
        made then finds every chair placed for dining while the chair order itself is no longer validated."""
        early = OFFICE_EARLY and self.open_task()
        if (self.cit < 14 and not early) or not self.adm.get("manager_active_for_orders"):
            return
        mgr = self.adm.get("MANAGER_id")
        if mgr is None:
            return
        offices = self.zone("office")
        mine = [z for z in offices if z.get("owner") == mgr]
        mo = self.adm.get("manager_office")
        if any(self.office_has_chair(z) for z in mine) or (isinstance(mo, dict) and mo.get("chair")):
            return
        free = (self.free.get("chair") or 0) > 0
        fit = [(z, st) for z in mine for st in [self.zone_site(z)] if st is not None]
        if fit:
            if free:
                self.office_chair(fit[0][1]["id"], retry=2, limit=4)
            return            # else the chair is ordered (supply: office_chair_needed) and placed when it is made
        spare = [(z, st) for z in offices if z.get("owner") is None
                 for st in [self.zone_site(z)] if st is not None]
        if spare:
            self.act("office_assign", "assign_zone", {"zone_id": spare[0][0]["id"], "dwarf_id": mgr})
            return
        if len(self.office_tried) >= OFFICE_ZONES or self.now - self.office_made_at < OFFICE_ZONE_GAP * DAY:
            return
        site = self.office_site()
        if site is None:
            return
        self.office_tried.add(site["id"])
        r = self.act("office_zone_%s" % site["id"], "make_zone", {"kind": "office", "site": site["id"]}, retry=0, limit=1)
        res = d(r.get("result")) if isinstance(r, dict) else {}
        zid = res.get("zone_id", (r or {}).get("zone_id") if isinstance(r, dict) else None)
        if not (r and r.get("ok")):
            return
        self.office_made_at = self.now
        self.office_zoned.add(site["id"])
        if site.get("kind") == "R":
            self.roles[site["id"]] = "office"
        if zid is not None:         # without the id the next pass assigns it (a spare office where a chair fits)
            self.act("office_assign_%s" % zid, "assign_zone", {"zone_id": zid, "dwarf_id": mgr}, retry=0, limit=2)
        if free and (self.surge or self.open_task()):    # other labs keep the zone, assign, chair sequence
            self.office_chair(site["id"], retry=0, limit=2)
        log("office_made", site=site["id"], zone=zid, day=self.day)

    def office_chair(self, site_id, retry, limit):
        """Place the office's chair. A refusal (no free floor there: d36 games zoned the office over a farm level whose
        plots cover every tile, and asked for its chair there all game) retires the site for offices (office_bad)."""
        key = "office_chair_%s" % site_id
        if self.tries.get(key, 0) >= limit:          # refused `limit` times for any reason (no_material while a chair
            self.office_bad.add(site_id)              #   reads free, internal_error): give the site up, not the office
            log("office_site_retired", site=site_id, code="tries", day=self.day)
            return None
        r = self.act(key, "place_furniture", {"kind": "chair", "site": site_id}, retry=retry, limit=limit)
        if r is not None and not r.get("ok") and r.get("error_code") in ("no_space", "site_used", "unknown_site", "wrong_site_kind"):
            self.office_bad.add(site_id)
            log("office_site_retired", site=site_id, code=r.get("error_code"), day=self.day)
        return r

    def office_fits(self, st):
        """An office site where a chair can stand: a chair fits it, the game has not refused a chair there, and it is
        not a farm level (a level with a farm room or plot) or a farm room."""
        if not self.chair_fits(st) or st.get("id") in self.office_bad:
            return False
        if st.get("kind") == "A":
            return st.get("z") not in self.farm_levels()
        return not self.farm_room(st, for_office=True)      # d64: a spare farm room may hold the office (office_site)

    def farm_room(self, r, for_office=False):
        """A room a farm plot uses, or one this layer designated as a farm that nothing else uses yet (a soil room
        given the farm role at designation can become a dining room instead: then it is no farm). For the office
        (d64), a farm-role room no plot uses stops counting once the fort has its plots (spare_farm_room)."""
        used = [str(u) for u in lst(r.get("used_by"))]
        if any(u.startswith("farm") for u in used):
            return True
        if for_office and self.spare_farm_room(r):
            return False
        return str(self.roles.get(r.get("id"), "")).startswith("farm") and not used

    def spare_farm_room(self, r):
        """d64, open tasks: a room given the farm role that no plot uses, once the fort has farm_target() plots (they
        went to F sites). The office may take it. Before d64 such a room still counted as a farm, and made its level a
        farm level, so on maps where every dug room had the farm role no office site was left: four local OP1 games
        (v57 1003-p, 1004, 1006-p; v59 1004) never had an office, validated no new order from 20 citizens on, and
        ended with 17 beds for 20 to 23 citizens."""
        return (self.open_task() and str(self.roles.get(r.get("id"), "")).startswith("farm")
                and not lst(r.get("used_by")) and len(lst(self.o.get("farm_plots"))) >= self.farm_target())

    def farm_levels(self):
        """z of every level with a farm room (this layer's farm role, given when its digging is designated), a room a
        farm plot uses, or a farm plot (a handed-over fort's own, or one built on an F site)."""
        return ({r.get("z") for r in self.kind("R") if self.farm_room(r)}
                | {p.get("z") for p in lst(self.o.get("farm_plots")) if isinstance(p, dict)})

    @staticmethod
    def office_has_chair(z):
        return bool(d(z.get("furniture")).get("chair") or d(z.get("furniture_planned")).get("chair"))

    def zone_site(self, z):
        """A site inside the office zone `z` where its chair can go (office_fits): the site make_zone zoned (same corner)
        if the zone still covers it whole, else a dug room, then a level, the zone holds whole. A level's A site
        changes id and box as its digging grows (d38 game: the office zoned over A8, 9x6, on day 3; A9, 13x7, on day
        5): a chair placed on the grown site could land outside the zone, so only sites the zone covers count."""
        cands = [st for st in self.sites if st.get("kind") in ("R", "A") and st.get("z") == z.get("z")
                 and st.get("x") == z.get("x") and st.get("y") == z.get("y")]
        cands += [st for st in self.kind("R") if st.get("dug")] + self.kind("A")
        return next((st for st in cands if covers(z, st) and self.office_fits(st)), None)

    @staticmethod
    def chair_fits(st):
        if st.get("kind") == "R":
            return bool(st.get("dug"))
        return (num(st.get("open_tiles")) or 0) >= 2 and (num(st.get("w")) or 1) * (num(st.get("h")) or 1) > 1

    def office_site(self):
        """A site for a new office zone where a chair fits: a dug room with the office role, then a dug room with no
        role, then a level with open floor in a box make_zone accepts, then (d64, the last resort) a farm-role room no
        plot uses once the plots are made; never a one-tile site, never one tried before."""
        rooms = self.dug_rooms("office") + [r for r in self.dug_rooms() if self.roles.get(r.get("id")) is None]
        levels = [a for a in self.kind("A") if (num(a.get("w")) or 99) <= ZONE_SIDE and (num(a.get("h")) or 99) <= ZONE_SIDE
                  and (not self.open_task() or (self.day or 0) >= OFFICE_LEVEL_DAY)]
        spare = [r for r in self.dug_rooms() if self.spare_farm_room(r)]    # a farm room a fifth plot may still want
        return next((st for st in rooms + levels + spare if st.get("id") is not None and st["id"] not in self.office_tried
                     and self.office_fits(st)), None)

    def build(self, wtype, retry=3):
        """One workshop of `wtype`: the first W site this run has not built this type on yet (the site the last
        build consumed is unusable, and moving on keeps a second Carpenters from retrying the first). d59, open
        tasks: nor any type, since the observation is a pass old: after Carpenters went on W1, the Still and Kitchen
        were sent to W1 in the same pass, refused (site_used) and held back by the key's retry, so OP1's Still stood
        on day 4-5 and its Kitchen on day 7-8 (yukonautominer's bbbb6c26 reserves the site the same way)."""
        used = {sid for sid, _ in self.full_sites} if SITE_ANY_TYPE and self.open_task() else set()
        for s in self.kind("W"):
            if (s.get("id"), wtype) in self.full_sites or s.get("id") in used:
                continue
            if not self.material():
                return None
            r = self.act("ws_" + wtype, "build_workshop", {"type": wtype, "site": s["id"]}, retry=retry)
            if r and r.get("ok"):
                self.full_sites.add((s.get("id"), wtype))
                self.built_n[wtype] = self.built_n.get(wtype, 0) + 1
            return r
        return None

    def shops(self):
        """Listed workshop types, except one whose every copy has had its construction suspended for STUCK_DAYS (build
        it elsewhere), until STUCK_REBUILDS more are listed or 1 + STUCK_REBUILDS builds were accepted."""
        rows = [d(w) for w in lst(self.o.get("workshops"))]
        have, stuck = set(), {}
        for w in rows:
            since = self.stuck_since.get(self.shop_key(w))
            if since is not None and self.now - since >= STUCK_DAYS * DAY:
                stuck[w.get("type")] = stuck.get(w.get("type"), 0) + 1
            else:
                have.add(w.get("type"))
        for t, n in stuck.items():
            if t not in have and (n > STUCK_REBUILDS or self.built_n.get(t, 0) > STUCK_REBUILDS):
                have.add(t)
        return have

    @staticmethod
    def shop_key(w):
        return (w.get("id"), w.get("type"), w.get("x"), w.get("y"), w.get("z"))

    def listed(self):
        return {d(w).get("type") for w in lst(self.o.get("workshops"))}

    def core_missing(self):
        """A core workshop is not listed at all: it gets the free sites before any stuck one is built again."""
        return not {"Carpenters", "Still", "Kitchen"} <= self.listed()

    def workshops(self):
        have, listed = self.shops(), self.listed()
        core = ("Carpenters", "Still", "Kitchen")
        for t in [t for t in core if t not in listed] + [t for t in core if t in listed and t not in have]:
            self.build(t)
        open_play = self.open_play()
        # open play: the Fishery only where the fort is played as inherited (calm is False), not while the choice
        # is still to be made (the workshop list could not be read yet) and never where nobody is to fish (d69: the
        # same on the drought lab)
        if "Fishery" not in have and any(p.get("job") == "Fish" for p in self.people) \
                and (self.calm is False if self.open_task() or self.lab_no_fish else True):
            self.build("Fishery")
        if open_play and "Butchers" not in have and have >= {"Carpenters", "Still", "Kitchen"} \
                and (self.calm is False or self.days_left <= FEAST_DAYS + BUTCHER_LEAD):
            self.build("Butchers")   # the feast must not wait for a workshop (building one took a week in game)
        if self.beds_first or self.surge:
            n = sum(1 for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Carpenters")
            target = SURGE_CARPENTERS if self.surge and self.beds_unmet() and self.cit >= 15 and self.logs() >= 5 else 2
            if n < target and have:
                self.build("Carpenters")

    def office_chair_needed(self):
        if (self.cit < 14 and not (OFFICE_EARLY and self.open_task())) or not self.adm.get("manager_active_for_orders"):
            return False
        if d(self.adm.get("manager_office")).get("chair") or (self.free.get("chair") or 0):
            return False
        manager = self.adm.get("MANAGER_id")
        return not any(z.get("owner") == manager and
                       (d(z.get("furniture")).get("chair") or d(z.get("furniture_planned")).get("chair"))
                       for z in self.zone("office"))

    def dorm_depth_ok(self, room):
        if self.surface is None or room.get("z") is None:
            return False
        depth = SURGE_DORM_DEPTH - (1 if (self.day or 0) >= 8 else 0)
        return room["z"] <= self.surface - depth

    def in_dorm_box(self, site):
        box = self.dorm_box
        if not box or None in box or site.get("z") != box[2] or site.get("x") is None or site.get("y") is None:
            return False
        x, y, w, h = site["x"], site["y"], site.get("w") or 3, site.get("h") or 3
        return not (x + w <= box[0] or x >= box[0] + box[3] or y + h <= box[1] or y >= box[1] + box[4])

    def placement_count(self, response):
        if not isinstance(response, dict):
            return None
        if not response.get("ok"):
            return 0 if response.get("error_code") == "no_space" else None
        points = d(response.get("result")).get("at")
        if not isinstance(points, list) or not points:
            return None
        if len(points) == 3 and all(type(v) is int for v in points):
            return 1
        if all(isinstance(point, list) and len(point) == 3 and all(type(v) is int for v in point)
               for point in points):
            return len(points)
        return None

    def farm_target(self):
        return max(4, min(10, math.ceil(self.cit / 5)))

    def stair_site(self, stairs):
        """The S site for a staircase: the default (the last listed) unless water lies within STAIR_WATER tiles of it on
        the surface or the level below; then the listed S site farthest from water. Decided once a game; a failed map
        query, or no water in it, keeps the default."""
        default = stairs[-1]
        if not WATER_STAIRS or not self.open_task() or len(stairs) < 2 or not isinstance(self.surface, int):
            return default
        by_id = {s.get("id"): s for s in stairs}
        if self.stair_pick is not None:
            return by_id.get(self.stair_pick, default)
        pick = default
        try:
            q = self.game.query("map", x=default["x"], y=default["y"], z=self.surface, radius=20, z2=self.surface - 1)
            res = d(q.get("result", q))
            wet = [(w["x"], w["y"]) for w in lst(res.get("liquid")) if isinstance(w, dict) and not w.get("magma")
                   and (w.get("depth") or 0) >= 1 and w.get("x") is not None and w.get("y") is not None]
            if wet:
                near = lambda s: min(max(abs(s["x"] - x), abs(s["y"] - y)) for x, y in wet)
                if near(default) <= STAIR_WATER:
                    pick = max(stairs, key=near)
                log("stair_site", default=default.get("id"), pick=pick.get("id"), water=len(wet),
                    near_default=near(default), near_pick=near(pick))
        except Exception as e:   # the map query is optional: the default site stays
            log("stair_site_error", error=repr(e)[:200])
        self.stair_pick = pick.get("id")
        return pick

    def wet_box(self, x, y, z, w, h):
        """d56: True when the map shows water, ice or magma in the box (top-left x,y on level z, w by h) or on a tile
        next to it on that level; False when it shows none (hidden tiles show nothing); None when the query fails or
        answers neither liquid nor levels."""
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (x, y, z, w, h)):
            return None
        try:
            q = self.game.query("map", x=x + w // 2, y=y + h // 2, z=z, radius=min(20, max(w, h) // 2 + 2))
        except Exception as e:   # the map query is optional: the room is dug as before
            log("room_water_error", error=repr(e)[:200])
            return None
        res = d(d(q).get("result", q))
        if res.get("ok") is False or ("liquid" not in res and "levels" not in res):
            return None
        near = lambda px, py: x - 1 <= px <= x + w and y - 1 <= py <= y + h   # noqa: E731
        for t in lst(res.get("liquid")):
            t = d(t)
            if t.get("z", z) == z and isinstance(t.get("x"), int) and isinstance(t.get("y"), int) \
                    and (t.get("depth") or 0) >= 1 and near(t["x"], t["y"]):
                return True
        x1, y1 = res.get("x1"), res.get("y1")
        if isinstance(x1, int) and isinstance(y1, int):
            for lv in lst(res.get("levels")):
                lv = d(lv)
                if lv.get("z") != z:
                    continue
                for layer, wet in (("material", WET_MATERIAL), ("shape", WET_SHAPE)):
                    for i, row in enumerate(lst(lv.get(layer))):
                        if isinstance(row, str) and any(ch in wet and near(x1 + j, y1 + i) for j, ch in enumerate(row)):
                            return True
        return False

    def room_size(self, room, w, h):
        """d56, open tasks: the box to dig at an R site for a room of w by h: (w, h) when it is dry, else the first
        dry smaller box (ROOM_SIZES), else None (no room here). Anything else, and a failed query: (w, h) as before.
        Decided once per room and size."""
        if not DRY_ROOMS or not self.open_task():
            return (w, h)
        key = (room.get("id"), w, h)
        if room.get("id") in self.wet_rooms:
            return None               # every size holds the 3x3 box, which is wet
        if key in self.room_fit:
            return self.room_fit[key]
        fit = None
        for bw, bh in ROOM_SIZES.get((w, h), ((w, h),)):
            wet = self.wet_box(room.get("x"), room.get("y"), room.get("z"), bw, bh)
            if wet is None and (bw, bh) == (w, h):
                fit = (w, h)          # no map: as before
                break
            if wet is False:
                fit = (bw, bh)
                break
        if fit != (w, h):
            log("room_wet", site=room.get("id"), want=[w, h], dig=list(fit) if fit else None, day=self.day)
        if fit is None:
            self.wet_rooms.add(room.get("id"))
        self.room_fit[key] = fit
        return fit

    def digging(self):
        rooms = self.kind("R")
        pending = self.o.get("dig_designations_pending") or 0
        stairs = self.kind("S")
        need_dorm_access = self.surge and "dorm" not in self.roles.values() and not any(
            self.dorm_depth_ok(r) for r in self.undug_rooms() if r["id"] not in self.roles)
        if stairs and self.surface is not None and (len(rooms) < 2 or (not any(r.get("soil") for r in rooms)
                                                                       and not self.o.get("farm_plots")) or need_dorm_access):
            self.act("stairs", "dig_stairs", {"site": self.stair_site(stairs)["id"], "z_bottom": self.surface - 4},
                     retry=12, limit=3)
        if pending > 90:
            return
        farms = len(lst(self.o.get("farm_plots"))) + sum(1 for r, v in self.roles.items() if v == "farm" and not any(z.get("id") == r and z.get("used_by") for z in self.kind("R")))
        for r in self.undug_rooms():
            rid = r["id"]
            if rid in self.roles:
                continue
            need = [x for x in ("dorm", "dine", "office") if x not in self.roles.values()]
            if self.surge and "dorm" in need and self.dorm_depth_ok(r):
                result = self.act("dig_" + rid, "dig_room", {"site": rid, "w": 9, "h": 7}, retry=3, limit=2)
                if result and result.get("ok"):
                    self.roles[rid] = "dorm"
                    self.dorm_box = (r.get("x"), r.get("y"), r.get("z"), 9, 7)
            elif r.get("soil") and farms < self.farm_target():
                if self.room_size(r, 3, 3) is None:     # d56: water, ice or magma at the box: not this room
                    continue
                result = self.act("dig_" + rid, "dig_room", {"site": rid}, retry=3, limit=2)
                if result and (not self.surge or result.get("ok")):
                    self.roles[rid] = "farm"
                    farms += 1
            elif need:
                role = need[0]
                if self.surge and role == "dorm" and not self.dorm_depth_ok(r):
                    continue
                size = {"dorm": {"w": 9, "h": 7}, "dine": {"w": 7, "h": 5}, "office": {}}[role]
                fit = self.room_size(r, size.get("w", 3), size.get("h", 3))
                if fit is None:                         # d56: the next room takes the role
                    continue
                if fit != (size.get("w", 3), size.get("h", 3)):
                    size = {} if fit == (3, 3) else {"w": fit[0], "h": fit[1]}
                result = self.act("dig_" + rid, "dig_room", {"site": rid, **size}, retry=3, limit=2)
                if result and (not self.surge or result.get("ok")):
                    self.roles[rid] = role
                    if self.surge and role == "dorm":
                        self.dorm_box = (r.get("x"), r.get("y"), r.get("z"), 9, 7)

    def farms(self):
        plots = lst(self.o.get("farm_plots"))
        target = self.farm_target()
        if len(plots) >= target:
            return
        cands = self.kind("F") + [r for r in self.dug_rooms() if r.get("soil") and self.roles.get(r["id"], "farm") == "farm"]
        if self.surge:
            cands = [site for site in cands if not self.in_dorm_box(site)]
        seeds = d(self.st.get("seeds_by_kind"))
        if any(not d(v).get("underground") for v in seeds.values()):
            cands += self.kind("G")[:2]
        for s in cands[:target - len(plots)]:
            self.act("farm_" + s["id"], "build_farm", {"site": s["id"]}, retry=4, limit=3)

    def supply(self):
        """Standing orders that keep working in a hands-off window, then one-shot furniture sized to the population.
        Goal policies: with the "drink must not end lower" goal the brew order keeps no drink ceiling (the window
        must see batches brewed); with the placed-bed goal the carpenters' queue holds beds only."""
        brew = self.standing("brew_drink") or (self.drink_growth and bool(self.brew_own)) or self.brew_stopped
        if not brew:
            when = [{"stock": "plants_brewable", "at_least": BREW_MIN if self.open_task() else 2},
                    {"stock": "barrels_empty", "at_least": 1}]
            if not self.drink_growth:
                when.insert(0, {"stock": "drink", "below": DRINK_CAP})
            key = "o_brew_growth" if self.drink_growth else "o_brew"
            self.act(key, "add_order", {"recipe": "brew_drink", "amount": 3, "repeat": "daily", "when": when}, retry=3)
        if not self.standing("make_barrel"):
            self.act("o_barrel", "add_order", {"recipe": "make_barrel", "amount": 2, "repeat": "daily", "when": [
                {"stock": "barrels_empty", "below": 4}, {"stock": "logs", "at_least": 2}]}, retry=3)
        if not self.standing("cook_meal") and not self.beds_first:
            self.act("o_cook", "add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily", "when": [
                {"stock": "prepared_meals", "below": MEAL_CAP}, {"stock": "plants_total", "at_least": 10}]}, retry=3)
        plants = d(self.st.get("plants_by_kind"))
        if (self.st.get("drink") or 0) < 3 * self.cit and not self.st.get("plants_brewable") and plants \
                and not self.pending("brew_drink_from_fruit"):
            self.act("o_fruit", "add_order", {"recipe": "brew_drink_from_fruit", "amount": 3}, retry=4)
        seats = math.ceil(self.cit / 2) + 2
        bed_target = max(self.cit + 12, SURGE_BEDS) if self.surge else self.cit + 3
        if self.open_task():          # dining furniture counted where it seats someone (real_seats)
            site = self.dine_site()
            tables, chairs = self.dine_stock("table", site), self.dine_stock("chair", site)
        else:
            tables, chairs = self.st.get("tables") or 0, self.st.get("chairs") or 0
        wants = (("make_bed", self.st.get("beds") or 0, bed_target),
                 ("make_table", tables, seats),
                 ("make_chair", chairs, seats + 1))
        if self.beds_first:
            wants = wants[:1]
            if self.surge and self.office_chair_needed():
                wants += (("make_chair", self.free.get("chair") or 0, 1),)
        elif self.open_task() and self.office_chair_needed():   # d36: one chair for the office before dining wants it
            wants += (("make_chair", self.free.get("chair") or 0, 1),)
        for recipe, have, want in wants:
            if have < want and not self.pending(recipe) and self.logs():
                batch = 30 if self.surge and recipe == "make_bed" else 8
                self.act("o_" + recipe, "add_order", {"recipe": recipe, "amount": min(batch, want - have)}, retry=1, limit=99)

    # ---- the closer: what the score reads at the end of the run
    def in_endgame(self):
        """Open-play tasks: the scored final stretch (the last quarter of the run, 7-28 days) is near."""
        return self.hands_off is None and self.days_left is not None and self.days_left <= ENDGAME_DAYS

    def in_window_prep(self):
        """Lab tasks: the hands-off window starts soon; after it begins only standing orders keep working."""
        return isinstance(self.hands_off, int) and 0 < self.hands_off <= WINDOW_PREP_DAYS

    # ---- the growth push: created wealth for the Hamlet rank on full-year games
    def progression_push(self):
        """Full-year games: the Hamlet rank needs 20 citizens and 5000 created wealth. Our wealth passed 5000 on days
        186-322 or never, after the second migrant wave (days 174-207). i34-9's rule (fa9c13cc progress()): from
        PROG_FROM_DAY until PROG_WEALTH, a Craftsdwarfs and one standing daily order of wood crafts while at least
        PROG_LOGS logs are in stock."""
        if self.hands_off is not None or self.lab or self.beds_first or (self.days or 0) < 336:
            return
        if not isinstance(self.day, int) or self.day < PROG_FROM_DAY or self.cit < 7:
            return
        if (d(self.o.get("wealth")).get("created") or 0) >= PROG_WEALTH:
            return
        if "Craftsdwarfs" not in self.shops():
            if "Craftsdwarfs" not in self.listed() or not self.core_missing():
                self.build("Craftsdwarfs", retry=5)
            return
        if not self.craft_standing():
            self.act("o_crafts", "add_manager_order",
                     {"job": "MakeCrafts", "amount": 3, "repeat": "daily", "material_category": ["wood"],
                      "when": [{"item_type": "WOOD", "at_least": PROG_LOGS}]}, retry=4, limit=6)

    def craft_standing(self):
        """A repeating wood-crafts order the layer added is still standing: its recipe is None, so `standing()` can
        not see it, and the confirmed ids are the record."""
        return any(o.get("id") in self.craft_ids for o in self.orders)

    def winter_prep(self):
        """Full-year open play, from WINTER_PREP_DAYS before the horizon until the endgame: drink doesn't rot, so it is
        brewed up before winter instead of only from ENDGAME_DAYS out (food does rot, and comes from the herd)."""
        return (WINTER_PREP_DAYS > ENDGAME_DAYS and self.open_play() and (self.days or 0) >= 336
                and self.days_left <= WINTER_PREP_DAYS)

    def winter_supply(self):
        """The endgame's brew order, early, under its own key: endgame_supply cancels it and adds its own with the
        population of that day (a wave between them would otherwise leave this cap and plant reserve in force)."""
        cap = max(600, 30 * self.cit)
        reserve = max(12, self.cit)
        if not self.brew_stopped:
            r = self.act("o_brewpre_end", "add_order", {"recipe": "brew_drink", "amount": 4, "repeat": "daily", "when": [
                {"stock": "drink", "below": cap}, {"stock": "plants_brewable", "at_least": reserve},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=3, limit=4)
            res = d(r.get("result")) if isinstance(r, dict) and r.get("ok") else {}
            if res.get("order_id") is not None:
                self.winter_brew_id = res.get("order_id")
        self.act("o_barrel_end", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 8}, {"stock": "logs", "at_least": 4}]}, retry=3, limit=4)

    def closer(self):
        if self.in_endgame():
            self.endgame_supply()
            self.housing_check()
        elif self.winter_prep():
            self.winter_supply()
        elif self.in_window_prep():
            self.window_supply()
            self.housing_check()

    def endgame_supply(self):
        """The supply sub-score credits a stock by its projected days left: a draining stock is credited only as far
        as it lasts, and a flat or rising one in full. From ENDGAME_DAYS before the horizon, a second brew order with a
        cap well above the usual one keeps drink rising through the final stretch (while plants stay above a reserve
        that protects the food count, since plants are food too), and cooking keeps meals rising from surplus food.
        Meat is added when edible food is short of a few days per citizen."""
        cap = max(600, 30 * self.cit)
        reserve = max(12, self.cit)
        wid = self.winter_brew_id
        if wid is not None and isinstance(self.o.get("orders"), list):
            if any(x.get("id") == wid for x in self.orders):
                r = self.act("o_brewpre_cancel", "cancel_order", {"order_id": wid}, retry=1, limit=3)
                if r is not None and (r.get("ok") or r.get("error_code") == "no_such_order"):
                    self.winter_brew_id = None
            else:
                self.winter_brew_id = None
        if not self.brew_stopped:
            self.act("o_brew_end", "add_order", {"recipe": "brew_drink", "amount": 4, "repeat": "daily", "when": [
                {"stock": "drink", "below": cap}, {"stock": "plants_brewable", "at_least": reserve},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=3, limit=4)
        self.act("o_barrel_end", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 8}, {"stock": "logs", "at_least": 4}]}, retry=3, limit=4)
        self.act("o_cook_end", "add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily", "when": [
            {"stock": "prepared_meals", "below": max(300, 10 * self.cit)},
            {"stock": "food_edible", "at_least": max(30, 4 * self.cit)}]}, retry=3, limit=4)
        if (self.st.get("food_edible") or 0) < 4 * self.cit and not self.open_play():
            self.butcher()

    # ---- open play: when the animals are slaughtered
    def open_task(self):
        """A long open task (MY1, OP1): no hands-off window and none of the lab goal policies. What the task is
        does not depend on whether this reply carries the task clock."""
        return (self.hands_off is None and not self.lab
                and not self.surge and not self.beds_first and not self.drink_growth)

    def open_play(self):
        """An open task on a reply that has its clock: everything timed in days left needs this one."""
        return self.open_task() and isinstance(self.days_left, int)

    def window_supply(self):
        """Before a hands-off window: brew whenever a plant and a barrel allow, at a cap the window can't reach, so
        drink keeps rising while nobody can act (LT08 wants drink at the end above drink at the window's start;
        LT01 wants a batch brewed inside it). Plants are food too, and food must also hold through the window, so
        half a plant per citizen stays unbrewed. Barrels are the usual limit: an extra barrel order runs alongside.
        Beds come first in the carpenters' queue on a migrant task, with a second Carpenters to make them."""
        self.act("o_brew_win", "add_order", {"recipe": "brew_drink", "amount": 5, "repeat": "daily", "when": [
            {"stock": "drink", "below": 2000}, {"stock": "plants_brewable", "at_least": max(3, self.cit // 2)},
            {"stock": "barrels_empty", "at_least": 1}]}, retry=2, limit=5)
        self.act("o_barrel_win", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 10}, {"stock": "logs", "at_least": 3}]}, retry=2, limit=5)
        if (self.st.get("food_edible") or 0) < 4 * self.cit:
            self.butcher()
        if self.surge:
            carp = sum(1 for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Carpenters")
            if carp == 1 and self.cit >= 15 and self.logs() >= 5:
                self.build("Carpenters", retry=3)

    def ordered_now(self, key):
        """The regular supply step already ran this key in this pass (the observation's order list is stale then)."""
        return self.last.get(key) == self.now

    def housing_check(self):
        """Housing is read at the horizon: placed (built) beds per citizen and seats inside dining zones per two
        citizens. Near the end, order the shortfall at once (a built bed needs the item, a carpenter and an installer)
        and place whatever is free; the regular furnish step then zones it."""
        # d59, open tasks: less the beds whose construction DF suspended (beds_counted), so their replacements are
        # ordered too; the labs keep the placed count
        beds_short = self.cit - (self.beds_counted() if self.open_task() else (self.placed.get("bed") or 0))
        if beds_short > 0 and (self.st.get("beds") or 0) < self.cit + 2 and self.logs() >= 2 \
                and not self.pending("make_bed") and not self.ordered_now("o_make_bed"):
            self.act("o_bed_close", "add_order", {"recipe": "make_bed", "amount": min(30, max(2, beds_short + 2))},
                     retry=2, limit=10)
        if self.beds_first and beds_short > 0:
            return   # a migrant task scored on beds only: the carpenters' queue stays with the beds
        if self.surge and beds_short > 0:
            return
        open_task = self.open_task()
        seats_short = math.ceil(self.cit / 2) - (self.real_seats() if open_task else self.seats())
        if seats_short > 0 and self.logs() >= 2:
            site = self.dine_site() if open_task else None
            for recipe, kind in (("make_table", "table"), ("make_chair", "chair")):
                want = math.ceil(self.cit / 2) + 1
                have = self.dine_stock(kind, site) if open_task else (self.st.get(kind + "s") or 0)
                if have < want and not self.pending(recipe) and not self.ordered_now("o_" + recipe):
                    self.act("o_%s_close" % recipe, "add_order", {"recipe": recipe, "amount": min(30, want - have)},
                             retry=2, limit=10)

    def seats(self):
        """Seats as the score counts them: tables and chairs inside dining zones."""
        n = 0
        for z in self.zone("dining"):
            f = d(z.get("furniture"))
            n += min(f.get("table") or 0, f.get("chair") or 0)
        return n

    # ---- dining seats on the long open tasks (MY1, OP1), where housing is scored; lab tasks keep the steps above
    def real_seats(self):
        """min(built tables, built chairs) in dining zones, each building once (never above the score's count)."""
        n = self.dining_kinds(built_only=True)
        return min(n["table"], n["chair"])

    @staticmethod
    def box(s):
        return (s.get("x"), s.get("y"), s.get("z"), s.get("w"), s.get("h"))

    def fill_mark(self, s):
        """What a site looked like when it had no room: its box and its open area (a dug level grows)."""
        return self.box(s), s.get("open_tiles")

    def stuck(self, f):
        """d52, open tasks: a placed item that was unbuilt when DF reported a suspended construction ("The dwarves
        suspended the construction of ... Table.": a kea that keeps interrupting the builders does it) and is still
        unbuilt FURN_STUCK_DAYS later. No tool resumes a suspended construction: it is not counted as coming, and
        free items are placed in its stead. A slow backlog with no such report is never counted out."""
        if not self.open_task() or f.get("built") is not False:
            return False
        since = self.furn_suspects.get(f.get("id"))
        return since is not None and self.now - since >= FURN_STUCK_DAYS * DAY

    def beds_counted(self):
        """Placed beds, built or coming; on open tasks less the stuck ones (d50)."""
        n = self.placed.get("bed") or 0
        if self.open_task():
            n -= sum(1 for f in lst(self.o.get("furniture")) if isinstance(f, dict) and f.get("kind") == "bed"
                     and self.stuck(f))
        return n

    def dining_kinds(self, built_only=False, site=None):
        """Tables and chairs in a dining zone by DF's membership (`zone_ids`: a zone's rectangle is not membership),
        once each, planned ones too unless built_only; plus non-members inside `site` while it may still be zoned
        (or was zoned on this observation). From zone totals when the furniture list is cut short."""
        n = {"table": 0, "chair": 0}
        dining = {z.get("id") for z in self.zone("dining")}
        rows = [d(f) for f in lst(self.o.get("furniture"))]
        total = self.o.get("furniture_total")
        capped = isinstance(total, int) and not isinstance(total, bool) and total > len(rows)
        if capped:
            for z in self.zone("dining"):
                for k in n:
                    n[k] += d(z.get("furniture")).get(k) or 0
                    if not built_only:
                        n[k] += d(z.get("furniture_planned")).get(k) or 0
        prospective = site is not None and not built_only and (self.may_zone(site) or self.zoned_now(site))
        for f in rows:
            k = f.get("kind")
            if k not in n or (built_only and not f.get("built")):
                continue
            member_of = dining & set(lst(f.get("zone_ids")))
            if self.stuck(f):
                if capped and not built_only:
                    n[k] -= len(member_of)      # d54: each of its zones' planned totals counted it
                continue
            if member_of and not capped:
                n[k] += 1
            elif not member_of and prospective and covers(site, f):
                n[k] += 1
        return {k: max(0, v) for k, v in n.items()}

    def dine_stock(self, kind, site):
        """Tables or chairs that are or will be dining seats (dining_kinds), plus the free ones."""
        return self.dining_kinds(site=site)[kind] + (self.free.get(kind) or 0)

    def may_zone(self, site):
        """make_zone takes `site` (no side over ZONE_SIDE; a room nothing touches) and this layer may zone it now:
        never yet, or its box or dug area changed, or ZONE_RECHECK days on, fewer than ZONE_TRIES times, and its
        make_zone refused fewer than ZONE_FAILS times."""
        w, h = num(site.get("w")) or 0, num(site.get("h")) or 0
        if not (0 < w <= ZONE_SIDE and 0 < h <= ZONE_SIDE):
            return False
        if site.get("kind") == "R" and lst(site.get("used_by")):
            return False
        if self.tries.get("z_dine_%s" % site.get("id"), 0) >= ZONE_FAILS:
            return False
        z = self.zoned.get(site.get("id"))
        if not z:
            return True
        if z["n"] >= ZONE_TRIES:
            return False
        return z["mark"] != self.fill_mark(site) or self.now - z["at"] >= ZONE_RECHECK * DAY

    def zoned_now(self, site):
        """This layer zoned the site on the current observation: its furniture is still listed outside the zone."""
        z = self.zoned.get(site.get("id"))
        return bool(z) and z["at"] == self.now

    def dine_site(self):
        """Where dining furniture goes: only a seat in a dining zone counts, make_zone refuses a box over ZONE_SIDE and
        place_furniture one over PLACE_SIDE (handed-over forts' dining levels were 21x4 to 51x58). The usual site
        while a dining zone holds it or it can be zoned; else another level, else a dug room a dining zone holds
        whole or nothing touches. Full sites wait for a change; retired ones are left. None if nothing qualifies."""
        first = self.room_for("dine") or self.room_for("dorm")
        if not first:
            return None
        zones = self.zone("dining")

        def zoned(s):
            return any(covers(z, s) for z in zones)

        def fits(s, alt):
            w, h = num(s.get("w")) or 0, num(s.get("h")) or 0   # d42: an unreadable size skips the site only
            if not (0 < w <= PLACE_SIDE and 0 < h <= PLACE_SIDE) or self.dine_full.get(s.get("id")) == self.fill_mark(s):
                return False
            if self.retired_site(s):
                return False
            if s.get("kind") == "R":
                used = [str(u) for u in lst(s.get("used_by"))]
                if any(u.startswith("farm") for u in used) or (alt and not s.get("dug")):
                    return False
                if used:
                    return zoned(s)
                return not alt or self.roles.get(s.get("id")) in (None, "dine", "dine_more")
            return (num(s.get("open_tiles")) or 0) >= 6 and (zoned(s) or (w <= ZONE_SIDE and h <= ZONE_SIDE))

        if fits(first, False):
            return first
        alts = [s for s in self.kind("A") + self.kind("R") if fits(s, True)]
        alts.sort(key=lambda s: (not zoned(s), s.get("kind") != "A", -(num(s.get("open_tiles")) or 0), str(s.get("id"))))
        return alts[0] if alts else None

    def needs_zone(self, site, placed=()):
        """GordoAR's coverage check (5dfdcf15, kept by fa9c13cc), on membership: may_zone, and a table or chair in
        the site is in no dining zone, or was just placed where no dining zone's box reaches."""
        if not self.may_zone(site):
            return False
        dining = {z.get("id") for z in self.zone("dining")}
        if any(d(f).get("kind") in ("table", "chair") and covers(site, d(f)) and not dining & set(lst(d(f).get("zone_ids")))
               for f in lst(self.o.get("furniture"))):
            return True
        return any(covers(site, p) and not any(covers(z, p) for z in self.zone("dining")) for p in placed)

    def zone_dining(self, site):
        """make_zone dining_hall over the site (may_zone bounds how often): a refused room is passed over."""
        r = self.act("z_dine_%s" % site["id"], "make_zone", {"kind": "dining_hall", "site": site["id"]},
                     retry=ZONE_RECHECK, limit=ZONE_FAILS)
        if isinstance(r, dict) and r.get("ok"):
            z = self.zoned.setdefault(site["id"], {"n": 0})
            z.update(mark=self.fill_mark(site), at=self.now, n=z["n"] + 1)
        elif isinstance(r, dict) and r.get("error_code") == "site_used":
            self.dine_full[site["id"]] = self.fill_mark(site)

    def place(self, key, kind, site, count):
        """place_furniture; returns the tiles it used as furniture rows. A site with no room left is passed over
        until its box or open area changes."""
        r = self.act(key, "place_furniture", {"kind": kind, "site": site["id"], "count": count}, retry=1, limit=99)
        if not isinstance(r, dict) or not r.get("ok"):
            if isinstance(r, dict) and r.get("error_code") == "no_space":
                self.dine_full[site.get("id")] = self.fill_mark(site)
            return []
        points = d(r.get("result")).get("at") or []
        if points and not isinstance(points[0], list):
            points = [points]
        rows = [{"kind": kind, "x": p[0], "y": p[1], "z": p[2]} for p in points
                if isinstance(p, list) and len(p) == 3 and all(type(v) is int for v in p)]
        self.dine_placed.setdefault(site.get("id"), set()).update((f["x"], f["y"], f["z"]) for f in rows)
        return rows

    def retired_site(self, site):
        """Left for good: its dining make_zone refused ZONE_FAILS times and a table or chair this layer placed there
        is in no dining zone (more placed there would seat nobody)."""
        sid = site.get("id")
        if sid in self.dine_retired:
            return True
        spots = self.dine_placed.get(sid)
        if not spots or self.tries.get("z_dine_%s" % sid, 0) < ZONE_FAILS:
            return False
        dining = {z.get("id") for z in self.zone("dining")}
        for f in lst(self.o.get("furniture")):
            f = d(f)
            if f.get("kind") in ("table", "chair") and (f.get("x"), f.get("y"), f.get("z")) in spots \
                    and not dining & set(lst(f.get("zone_ids"))):
                self.dine_retired.add(sid)
                log("dining_site_retired", site=sid, day=self.day)
                return True
        return False

    def rezone(self):
        """Only furniture inside a zone counts or gets used. Zone each level's loose tables, chairs and beds, and put
        a dining zone over a level whose tables and chairs sit in no dining zone (a dormitory's seats earn nothing)."""
        loose, by_z = {}, {}
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
            site = next((x for x in self.kind("A") if x.get("z") == z and (x.get("w") or 0) <= 20 and (x.get("h") or 0) <= 20), None)
            if not site:
                site = next((x for x in self.dug_rooms() if x.get("z") == z), None)
            if not site:
                continue
            if kinds & {"table", "chair"} and not self.zoned_now(site):   # furnish zoned it on this observation
                self.act("rz_dine_%s" % site["id"], "make_zone", {"kind": "dining_hall", "site": site["id"]}, retry=2, limit=3)
            if "bed" in kinds and not any(overlap(r, site) for r in self.pending_dine()):   # d46: as in beds_open
                self.act("rz_dorm_%s" % site["id"], "make_zone", {"kind": "dormitory", "site": site["id"]}, retry=2, limit=3)
        for z, kinds in by_z.items():
            if kinds.get("table") and kinds.get("chair"):
                site = next((x for x in self.kind("A") if x.get("z") == z and (x.get("open_tiles") or 0) >= 6
                             and (x.get("w") or 0) <= 20 and (x.get("h") or 0) <= 20), None)
                if site and not self.zoned_now(site):
                    self.act("dx_dine_%s" % site["id"], "make_zone", {"kind": "dining_hall", "site": site["id"]}, retry=3, limit=2)

    def meeting(self):
        """Open tasks: one meeting area below ground (MEETING), once a dug level or room can take it. Never again
        once a meeting area stands or this layer's own was accepted."""
        if not (MEETING and self.open_task()) or self.meeting_made or self.meeting_tries >= MEETING_TRIES:
            return
        if self.zone("meeting"):
            return
        site = self.meeting_site()
        if site is None:
            return
        r = self.act("meeting_%s" % site["id"], "make_zone", {"kind": "meeting_area", "site": site["id"]},
                     retry=1, limit=MEETING_SITE_TRIES)
        if r is None:
            return
        self.meeting_tries += 1
        if r.get("ok"):
            self.meeting_made = site["id"]
            log("meeting_made", site=site["id"], day=self.day)

    def meeting_site(self):
        """Where the meeting area goes: an underground dug level (A) or dug room (R) make_zone takes (ZONE_SIDE), with
        room to stand, off the levels that hold a farm plot. A site a dining zone overlaps first, then a dormitory's,
        then levels before rooms and the most open tiles; before MEETING_ANY_DAY only sites one of those zones
        overlaps. None if no site qualifies."""
        surface = self.surface if isinstance(self.surface, int) and not isinstance(self.surface, bool) \
            else self.surface_seen
        farm_z = self.farm_levels()
        dining, dorms = self.zone("dining"), self.zone("dormitor")
        held = self.pending_dine() + [r for r in self.kind("R") if self.roles.get(r.get("id")) == "beds"
                                      and self.bed_full.get(r.get("id")) != self.fill_mark(r)]

        def fits(s):
            w, h, z = num(s.get("w")) or 0, num(s.get("h")) or 0, num(s.get("z"))
            if not (0 < w <= ZONE_SIDE and 0 < h <= ZONE_SIDE) or s.get("subterranean") is False or s.get("id") is None:
                return False
            if any(overlap(r, s) for r in held):   # d44: a zone over a housing room makes it `used` (site_used)
                return False
            if z is None or not isinstance(surface, int) or z >= surface or z in farm_z:
                return False
            if s.get("kind") == "A":
                return (num(s.get("open_tiles")) or 0) >= 9
            # a dug room a zone or farm plot already uses: make_zone answers site_used (manual, R rooms)
            return bool(s.get("dug")) and w * h >= 9 and not lst(s.get("used_by")) and s.get("free") is not False

        def touches(zones, s):
            return any(overlap(z, s) for z in zones)

        found = [s for s in self.kind("A") + self.kind("R") if fits(s)
                 and self.tries.get("meeting_%s" % s.get("id"), 0) < MEETING_SITE_TRIES]   # refused twice: the next
        if (self.day or 0) < MEETING_ANY_DAY:      # early on, only where the fort eats or sleeps: a level zoned before
            found = [s for s in found if touches(dining, s) or touches(dorms, s)]   # its rooms are dug stays small
        found.sort(key=lambda s: (not touches(dining, s), not touches(dorms, s), s.get("kind") != "A",
                                  -(num(s.get("open_tiles")) or (num(s.get("w")) or 0) * (num(s.get("h")) or 0)),
                                  str(s.get("id"))))
        return found[0] if found else None

    def room_for(self, role):
        """The dug level of a role's big room (its A site covers the whole dig), else the room itself."""
        rooms = [r for r in self.kind("R") if self.roles.get(r["id"]) == role]
        for r in rooms:
            a = next((s for s in self.kind("A") if s.get("z") == r.get("z")), None)
            if a and role != "farm" and (r.get("dug") or a.get("open_tiles", 0) >= 6):
                return a
        dug = [r for r in rooms if r.get("dug")]
        if dug:
            return dug[0]
        taken = {r.get("z") for r in self.kind("R") if self.roles.get(r["id"], "").startswith("farm")}
        return next((s for s in self.kind("A") if s.get("z") not in taken), None)

    # ---- d42, open tasks: housing that outgrows its rooms
    def reserved(self):
        """d44: boxes the bed fallback leaves alone. place_furniture fills a box row by row from its top-left,
        whatever zone a tile is in, so beds placed over a whole level can take an office's or a dining room's floor:
        office and dining zones, sites this layer gave the office or a dining role, and sites an office zone was made
        on this game (the zone list is the observation's, from before this pass's own actions). A site that is only where
        dining furniture would go next is not held: beds may need it as much."""
        boxes = [z for z in self.zones if any(w in str(z.get("type")).lower() for w in ("office", "dining"))]
        boxes += [st for st in self.sites if self.roles.get(st.get("id")) in ("office", "dine", "dine_more")
                  or st.get("id") in self.office_zoned]
        return boxes

    def pending_dine(self):
        """d45: rooms dug for more dining seats that no dining zone holds whole yet: any other zone over them makes
        them `used`, and make_zone then refuses their dining zone (site_used)."""
        dining = self.zone("dining")
        return [r for r in self.kind("R") if self.roles.get(r.get("id")) == "dine_more"
                and not any(covers(z, r) for z in dining)]

    def bed_sites(self, dorm):
        """Where beds can go, best first. The score counts placed beds wherever they stand, but place_furniture takes
        a box of at most PLACE_SIDE a side (handed-over forts' dug levels can be wider) and answers no_space when it
        is full. The dorm site, then other dug levels (no farm level, no office on them), most open first, then dug
        rooms nothing uses that are not this layer's farm, office or dining rooms. A site that refused beds for its
        size or for room is passed over until its box or open area changes."""
        farm_z = self.farm_levels()
        keep = self.reserved()

        def ok(s):
            w, h = num(s.get("w")), num(s.get("h"))
            if s.get("id") is None or not (w and h and w <= PLACE_SIDE and h <= PLACE_SIDE):
                return False
            if self.tries.get("beds_%s" % s.get("id"), 0) >= BED_LIMIT:   # d44: its key is spent
                return False
            return self.bed_full.get(s.get("id")) != self.fill_mark(s)

        out = [dorm] if dorm is not None and ok(dorm) else []
        levels = [s for s in self.kind("A") if ok(s) and s not in out and s.get("z") not in farm_z
                  and (num(s.get("open_tiles")) or 0) >= 3 and not any(overlap(b, s) for b in keep)]
        levels.sort(key=lambda s: (-(num(s.get("open_tiles")) or 0), str(s.get("id"))))
        def unused(r):   # a room only a dormitory zone uses still takes beds (d45)
            used = [str(u) for u in lst(r.get("used_by"))]
            return all(u.lower().startswith("dormitor") for u in used) if used else r.get("free") is not False

        rooms = [r for r in self.kind("R") if ok(r) and r not in out and r.get("dug") and unused(r)
                 and self.roles.get(r.get("id")) in (None, "dorm", "beds") and not any(overlap(b, r) for b in keep)]
        rooms.sort(key=lambda r: (self.roles.get(r.get("id")) != "beds", str(r.get("id"))))
        return out + levels + rooms

    def beds_open(self, dorm):
        """Open tasks: the beds a fort is short of go to the first site that takes them (bed_sites); a refusal for
        size or room moves on to the next site in the same pass. The dorm site keeps its dormitory zone."""
        n = min(self.free.get("bed") or 0, self.cit + 2 - self.beds_counted(), 30)
        if n <= 0:
            return
        self.place_beds(dorm, n)
        if dorm is not None and not self.zone("dorm") and not self.zone("bedroom") \
                and not any(overlap(r, dorm) for r in self.pending_dine()):   # d45: it would make that room `used`
            self.act("z_dorm", "make_zone", {"kind": "dormitory", "site": dorm["id"]}, retry=3)

    def place_beds(self, dorm, n):
        asked = 0
        for site in self.bed_sites(dorm):
            if asked >= BED_TRIES:
                return
            r = self.act("beds_%s" % site["id"], "place_furniture", {"kind": "bed", "site": site["id"], "count": n},
                         retry=1, limit=BED_LIMIT)
            if not isinstance(r, dict):
                continue                     # this site's key rests: another site may still be asked
            asked += 1
            if r.get("ok"):
                placed = self.placement_count(r)
                if placed is None or placed >= n:
                    return
                n -= placed
                self.bed_full[site["id"]] = self.fill_mark(site)   # took fewer than asked: no room left there
                continue
            if r.get("error_code") not in BED_REFUSED:
                return
            self.bed_full[site["id"]] = self.fill_mark(site)
            log("bed_site_full", site=site["id"], code=r.get("error_code"), day=self.day)

    def house_rooms(self):
        """Open tasks: beds or dining seats are short and no site can take them (the dining room is full, the
        levels are too big to zone or to furnish): dig one more 3x3 room for them, one at a time, at most HOUSE_ROOMS
        a game, from task day HOUSE_FROM_DAY. A dug room's id keeps working for place_furniture and make_zone; a
        level's box is the bounding box of everything dug on it, so a big level never fits."""
        if not self.open_task() or not isinstance(self.day, int) or self.day < HOUSE_FROM_DAY:
            return
        if (num(self.o.get("dig_designations_pending")) or 0) > 90:
            return
        extra = [r for r in self.kind("R") if self.roles.get(r.get("id")) in ("dine_more", "beds")]
        if len(extra) >= HOUSE_ROOMS or any(not r.get("dug") for r in extra):
            return
        role = None
        if self.real_seats() < math.ceil(self.cit / 2) + 1 and \
                (self.free.get("table") or 0) + (self.free.get("chair") or 0) > 0 and self.dine_site() is None:
            role = "dine_more"
        elif self.beds_counted() < self.cit and (self.free.get("bed") or 0) > 0 \
                and not self.bed_sites(self.room_for("dorm")):
            role = "beds"
        if role is None:
            return
        keep, dining = self.reserved(), self.zone("dining")

        def clear(r):
            """d44: a zone over the room's box makes the dug room `used` (make_zone answers site_used, and bed_sites
            passes a used room over): only a dining zone holding the whole box is welcome, for dining."""
            if not self.may("dig_" + r["id"], 3, 2):      # a refused room's key rests or is spent: try the next room
                return False
            for z in self.zones:
                if overlap(z, r) and not (role == "dine_more" and z in dining and covers(z, r)):
                    return False
            return not any(overlap(b, r) for b in keep if b not in self.zones)

        rooms = [r for r in self.undug_rooms() if r.get("id") is not None and r["id"] not in self.roles and clear(r)]
        if not rooms:
            return
        rooms.sort(key=lambda r: (bool(r.get("soil")), str(r.get("id"))))   # soil rooms are the farms' first choice
        r = next((r for r in rooms if self.room_size(r, 3, 3) is not None), None)   # d56: a dry room
        if r is None:
            return
        result = self.act("dig_" + r["id"], "dig_room", {"site": r["id"]}, retry=3, limit=2)
        if isinstance(result, dict) and result.get("ok"):
            self.roles[r["id"]] = role
            log("house_room", site=r["id"], role=role, day=self.day)

    def furnish(self):
        dorm, dine = self.room_for("dorm"), self.room_for("dine") or self.room_for("dorm")
        if self.open_task():
            self.beds_open(dorm)
        elif dorm:
            short = self.cit + 2 - (self.placed.get("bed") or 0)
            n = min(self.free.get("bed") or 0, short, 30)
            if n > 0:
                r = self.act("beds", "place_furniture", {"kind": "bed", "site": dorm["id"], "count": n},
                             retry=1, limit=99)
                # GordoAR's one-alternate route; the surge transfer also handles confirmed partial placement.
                alt_zone = None
                remaining = n
                overflow = self.beds_first and isinstance(r, dict) and not r.get("ok") and r.get("error_code") == "no_space"
                if self.surge:
                    placed = self.placement_count(r)
                    remaining = max(0, n - placed) if placed is not None else 0
                    overflow = remaining > 0
                if overflow:
                    areas = sorted((s for s in self.kind("A") if s.get("id") != dorm.get("id")
                                    and (s.get("open_tiles") or 0) >= 6
                                    and (not self.surge or (s.get("z") != dorm.get("z")
                                         and 0 < (s.get("w") or 0) <= 20 and 0 < (s.get("h") or 0) <= 20))),
                                   key=lambda s: (-(s.get("open_tiles") or 0), str(s.get("id"))))
                    if areas and self.may("beds_" + areas[0]["id"], 1, 6):
                        alt = areas[0]
                        rr = self.act("beds_" + alt["id"], "place_furniture",
                                      {"kind": "bed", "site": alt["id"], "count": remaining}, retry=1, limit=99)
                        if isinstance(rr, dict) and rr.get("ok"):
                            alt_zone = alt
                if not self.zone("dorm") and not self.zone("bedroom"):
                    self.act("z_dorm", "make_zone", {"kind": "dormitory", "site": dorm["id"]}, retry=3)
                if alt_zone is not None:
                    self.act("z_dorm_" + alt_zone["id"], "make_zone",
                             {"kind": "dormitory", "site": alt_zone["id"]}, retry=3)
        if dine and not self.beds_first and self.open_task():
            site = self.dine_site()
            if site:
                want = math.ceil(self.cit / 2) + 1
                placed = []
                for kind in ("table", "chair"):
                    n = min(self.free.get(kind) or 0, want - self.dining_kinds(site=site)[kind], 15)
                    if n > 0 and self.dine_full.get(site.get("id")) != self.fill_mark(site):
                        placed += self.place("f_" + kind, kind, site, n)
                if self.needs_zone(site, placed):
                    self.zone_dining(site)
        elif dine and not self.beds_first:
            if not self.zone("dining"):
                self.act("z_dine", "make_zone", {"kind": "dining_hall", "site": dine["id"]}, retry=3)
            want = math.ceil(self.cit / 2) + 1
            for kind in ("table", "chair"):
                n = min(self.free.get(kind) or 0, want - (self.placed.get(kind) or 0), 15)
                if n > 0:
                    self.act("f_" + kind, "place_furniture", {"kind": kind, "site": dine["id"], "count": n},
                             retry=1, limit=99)

    def mood(self):
        for m in lst(self.o.get("moods")):
            m = d(m)
            if m.get("mood") in ("Melancholy", "Raving", "Berserk", "Traumatized"):
                continue
            if not m.get("claimed_building_id"):
                want = MOOD_WORKSHOP.get(str(m.get("skill")).upper(), "Craftsdwarfs")
                have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
                if want not in have:
                    self.build(want, retry=2)
            for need in lst(m.get("items_needed")):
                if "bone" in str(d(need).get("item") or d(need).get("demand")).lower():
                    self.butcher()

    def butcher(self):
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        if "Butchers" not in have:
            self.build("Butchers")
        if not self.may("slaughter", 5, 3):
            return
        q = self.game.query("units", kind="animals")
        for a in lst(d(q.get("result")).get("units") or d(q.get("result")).get("animals")):
            a = d(a)
            if a.get("tame") and a.get("pet_owner_id") in (None, -1) and not a.get("marked_for_slaughter"):
                self.act("slaughter", "slaughter", {"unit_id": a.get("id")}, retry=5, limit=3)
                return


    def defend(self):
        th, mil = d(self.o.get("threats")), d(self.o.get("military"))
        bur = d(self.o.get("burrows"))
        open_play = self.open_play()
        alert = bur.get("civilian_alert")
        if open_play or self.lock is not None or self.own_locks:
            alert = self.wildlife(alert, open_play)   # first, while the day's actions are unspent
        if open_play or self.thaw_alert:
            alert = self.thaw(alert, bur)
        squads = lst(mil.get("squads"))
        squad = d(squads[0]) if squads else None
        if not squad and self.cit >= 14:
            self.act("squad", "create_squad", {"size": 4}, retry=5, limit=3)
        if squad and squad.get("uniform") == "none":
            self.act("equip", "equip_squad", {"uniform": "leather"}, retry=5, limit=3)
        shelter = self.room_for("dorm")
        if shelter and not any(d(b).get("civ_alert_burrow") for b in lst(bur.get("list"))):
            self.act("burrow", "create_burrow", {"site": shelter["id"]}, retry=5, limit=3)
        if open_play:
            self.grow_shelter(bur)
            self.place_hatches()
        invaders = [h for h in lst(th.get("hostiles")) if d(h).get("invader")]
        hostile = th.get("visible_hostiles") or 0
        orders = lst((squad or {}).get("orders"))
        holding = self.lock is not None and self.lock["phase"] == "hold"   # civilians are below: the squad stays in
        ours = (self.lock is not None and self.lock["why"] != "invaders") or self.thaw_alert   # this layer's to clear
        near = (th.get("nearest_hostile_dist_to_wagon") or 10 ** 6) <= 45
        if self.open_task():
            # d64: on the open tasks the squad fights only a hostile at the wagon (within 45 tiles) and only with every
            # member armed; otherwise it stands down. Before d64 it was sent at any visible hostile once one member
            # had a weapon: v58 MY1 1004, day 130, two harpies 132 tiles out, the leader with a pick and three
            # recruits unarmed; the squad chased them about 120 tiles across the map for four days and an unarmed
            # recruit bled to death (8 such attacks in 3 local games). The lockdown and the alert are the defence.
            # d65: the kill order names those hostiles (target_ids), since an attack without them is a kill order on
            # every visible hostile, near or far; and a squad whose members the observation does not list never fights
            members = lst((squad or {}).get("members"))
            at_wagon = sorted(h["id"] for h in lst(th.get("hostiles")) if isinstance(h, dict)
                              and type(h.get("id")) is int and (num(h.get("dist_to_wagon")) or 10 ** 6) <= SQUAD_NEAR)
            fight = bool(hostile and squad and at_wagon and members and not holding
                         and (squad.get("armed") or 0) >= len(members))
            if fight and not orders:
                self.act("attack", "squad_order", {"order": "attack", "target_ids": at_wagon}, retry=1, limit=99)
            if orders and not fight:
                self.act("stand_down", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
        else:                                        # lab tasks: unchanged
            if hostile and squad and (squad.get("armed") or 0) >= 1 and not orders and not holding:
                self.act("attack", "squad_order", {"order": "attack"}, retry=1, limit=99)
            if (not hostile or holding) and orders:
                self.act("stand_down", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
        # a fort that is being let out, or was just let out after a full lockdown or an invader alert, stays out:
        # the inherited invader alert does not sound over a release or over the day above ground that follows
        owed = self.lock is not None or self.now < self.rest_until   # (a lab task has neither)
        if invaders and near and not alert and not owed \
                and any(d(b).get("civ_alert_burrow") for b in lst(bur.get("list"))):
            if self.act("alert_on", "civilian_alert", {"on": True}, retry=20, limit=99):
                self.alert_since = self.now
        # civilians can't reach drink or food under a long alert: never hold it more than 10 days
        too_long = self.alert_since is not None and self.now - self.alert_since > 10 * DAY
        if alert and not ours and (not invaders or too_long):
            r = self.act("alert_off", "civilian_alert", {"on": False}, retry=1, limit=99)
            if not self.open_task() or (r is not None and r.get("ok")):   # open task: a refused clear is tried again
                self.alert_since = None

    def step_days(self):
        """Game days between this layer's passes on open play: one while a hostile is in sight or a lockdown is
        standing, else two."""
        if d(self.o.get("threats")).get("visible_hostiles") or self.lock is not None or self.own_locks \
                or self.beast_seen or self.thaw_alert or self.thaw_window(lead=2):
            return 1
        return 2

    def step(self, resp):
        """One pass of the deterministic layer for the plain loop. Returns the number of actions it ran."""
        self.load(resp)
        self.count = 0
        try:
            self.plan()
        except (HandsOff, GameOver):
            raise
        except ActionLimit:
            log("guard_action_limit")
        except Exception as e:   # a surprise in this layer must never stop the model loop
            log("guard_error", error=repr(e)[:300])
        return self.count

    def pace(self, resp):
        if d(self.o.get("threats")).get("visible_hostiles") or self.o.get("moods"):
            return 1
        if (self.o.get("dig_designations_pending") or 0) > 0 or (resp.get("day") or 0) < 14:
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
                except Exception as e:   # a surprise in one step must never stop time
                    log("plan_error", error=repr(e)[:300])
                if not self.count:
                    break
                resp = self.game.observe()
            self.load(resp)
            r = self.game.act("advance_days", {"days": self.pace(resp)})
            log("advance", day=r.get("day"), stopped=d(r.get("result")).get("stopped"), cit=self.cit,
                drink=self.st.get("drink"), food=self.st.get("food_edible"))
            if r.get("game_over") or d(r.get("result")).get("hands_off"):
                return "over"


def main():
    task = load_task()
    game = GameClient(task.game_url)
    log("start", task=repr(task))
    ov = Overseer(game)
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
            return 1


if __name__ == "__main__":
    sys.exit(main())
