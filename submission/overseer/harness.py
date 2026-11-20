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
import sys
import time

from dfbench_client import ActionLimit, GameAPIError, GameClient, GameOver, HandsOff, load_task
from overseer.openplay import OpenPlayRules, BUTCHER_LEAD, FEAST_DAYS, FINAL_STRETCH

DAY = 1200
MAX_PER_PASS = 12
MAX_PASSES = 3
DRINK_CAP = 300
BREW_KEEP = 6           # full-year embarks: plants left unbrewed as food. Their brew order has no drink ceiling: with
                        #   one, drink reached DRINK_CAP near day 80, brewing stopped, and the harvest lay on the
                        #   plots until it rotted (17 rotten to 4 fresh on one fort at day 147 in a live game). A
                        #   rotten plant gives no seed back, and the seeds in the plots fell from 25 to 7-9 by
                        #   midsummer, so the farms ran a quarter planted into the scored winter
MEAL_CAP = 200
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
WEALTH_FROM_DAY = 5     # full-year embarks: build created wealth via wooden Wheelbarrows/Minecarts/Stepladders
WEALTH_STOP_DAY = 202   #   (all 50 base value in DF 53.16) before the autumn caravan departs (~day 192-200) and
WEALTH_TARGET = 250000  #   reports home, maximizing Wave 2 migrant rolls; stop once caravan departs
WEALTH_LOGS = 60        #   minimum usable logs (>= 3 * 15 batch) so Butchers/housing/barrels are NEVER log-starved
ZONE_SIDE = 20          # make_zone refuses a site box wider or taller than this
PLACE_SIDE = 40         # place_furniture refuses a site box wider or taller than this
ZONE_RECHECK = 3        # days after which a dining site this layer zoned may be zoned again for furniture still
ZONE_TRIES = 3          #   outside every dining zone, at most this many times a site
ZONE_FAILS = 3          # refusals of a site's dining make_zone after which it is not asked again
STUCK_DAYS = 3          # a workshop construction suspended this long is built again elsewhere (no tool resumes it;
STUCK_REBUILDS = 2      #   a stuck Carpenters left a full-year fort with no bed, table or chair), this many times.
FURN_STUCK_DAYS = 10    # placed furniture still unbuilt this long is treated as suspended and not counted (#173)
                        #   A Butchers counts as stuck after the same days unbuilt, suspended or not: on some sites
                        #   nobody ever took the job, in every recorded game that used them (0 of 16 built, never
                        #   suspended; in a live game no log could be walked to from the site), while the other
                        #   sites of the same maps were built on within two days. And it is built again for as long
                        #   as a free site is listed, not STUCK_REBUILDS times: it is ordered months in, when the
                        #   logs near the wagon are used up, and on a river map each job reserved a log on the far
                        #   bank and kept it once suspended (three stuck shops held three logs of one felled tree),
                        #   so the next job takes another log

SURGE_BEDS = 50
SURGE_CARPENTERS = 3
SURGE_DORM_DEPTH = 3
WATER_RING = 1          # revealed liquid within this many tiles of a dig (a room's box on its own level, a stair
                        #   shaft level by level) cuts the dig back clear of it, or stops it. A 9x7
                        #   dormitory dug from a 3x3 site one level below the surface took in the bed of a brook, and
                        #   three dwarves drowned in it within a week (local MY1 game, leader's harness, 2026-11-15)

def log(kind, **kw):
    print(json.dumps({"t": round(time.time(), 2), "kind": kind, **kw}, default=str), flush=True)


def d(v):
    return v if isinstance(v, dict) else {}


def lst(v):
    return v if isinstance(v, list) else []


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
        self.brew_in_window = False # goal policy: hands-off task requiring a brewed batch inside the window
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
        self.report = []         # the layer's recent actions (day, tool, args, outcome), for the model loop
        self.done = set()        # closer keys whose order was accepted once: never re-added
        self.full_sites = set()  # W site ids a workshop was built on, so the next build takes another site
        self.stuck_since = {}    # (workshop id, type, x, y, z) -> tick its construction was first seen suspended
        self.unbuilt_since = {}  # the same key -> tick a Butchers was first seen listed and not yet built
        self.furn_unbuilt_since = {}  # (kind, x, y, z) -> first tick seen with built is False (#173)
        self.built_n = {}        # workshop type -> build_workshop calls the game accepted
        self.dorm_box = None
        self.lab = False         # the task has a hands-off window (set_task); open play is everything else
        self.culled = {}         # cull key -> tick of its last pass
        self.brew_stopped = False
        self.stretch_rest = False   # a full-year embark's one stop of brewing at DRINK_REOPEN was used (brew_rest)
        self.sheltered = {}      # A site id -> its open tiles when it was last added to the shelter burrow
        self.stairs = {}         # E site id -> (x, y, z): every surface stair ever listed
        self.surface_seen = None   # the surface level (the wagon's z) as last reported: kept through a reply without it
        self.lock = None         # the standing wildlife lockdown: {since, phase: hold|release, why, alert_off, ...}
        self.wild_off = False    # a lockdown could not protect once: no more of them this game
        self.own_locks = set()   # door ids of hatches this layer sent a lock for and has not confirmed open again
        self.rest_until = 0      # tick before which a lockdown may not begin again
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
        self.wet_sites = set()   # site ids not dug at all: revealed liquid lies within WATER_RING of them
        self.dug_size = {}       # site id -> (w, h) of the room box the game accepted (after any cut for water)
        self.wet_seen, self.wet_tick = {}, None   # map query answers of this tick, by box
        self.fisher_hold = None  # open play: None undecided, {"since", "ids"} stationed at wagon, False done
        self.fisher_ids = set()  # starting citizens with FISH labor (excluded from appoint_manager while undecided)
        self.bad_offices = set()           # office zone ids that cannot hold a chair (abandoned for a fresh site)
        self.bad_office_zone_sites = set() # site ids refused for office make_zone
        self.bad_office_chair_sites = set()# site ids refused for office chair placement
        self.bed_full = {}                 # site id -> fill_mark when bed placement failed or hit no_space
        self.w_used_now, self.w_used_tick = set(), None   # W site ids consumed on this tick (open play)
        self.wealth_ids = {}               # order id -> key for repeating MakeTool wealth orders
        self.caravan_out = False           # full-year embark: autumn caravan departure seen in recent_events
        self.caravan_in = False            # visiting caravan on map: stocks.food_edible/drink include caravan goods (#173)
        self.caravan_in_since = None       # tick caravan presence was first observed (42-day auto-expire safety net)

    def set_task(self, info):
        """Goal policies from the task's own public text (GET /task). A hands_off field means a lab task."""
        t = d(info)
        goal = str(t.get("goal") or "").casefold()
        self.lab = bool(t.get("hands_off"))
        self.drink_growth = bool(t.get("hands_off")) and "drink must not end lower" in goal
        self.beds_first = bool(t.get("hands_off")) and "every dwarf must have a placed bed" in goal
        self.brew_in_window = bool(t.get("hands_off")) and "brew at least one batch of drink" in goal

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
        if tool in ("dig_room", "dig_stairs"):
            safe = self.dry_dig(tool, args)
            if safe is None:
                self.wet_sites.add(args.get("site"))
                log("dig_wet", key=key, tool=tool, args=args)
                return None
            if safe != args:
                log("dig_cut", key=key, tool=tool, asked=args, now=safe)
                args = safe
        self.tries[key] = self.tries.get(key, 0) + 1
        self.last[key] = self.now
        r = self.game.act(tool, args)
        if tool == "dig_room" and r.get("ok") and isinstance(args, dict):
            self.dug_size[args.get("site")] = (args.get("w") or 3, args.get("h") or 3)
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
            if oid is not None and isinstance(args, dict) and args.get("job") == "MakeTool" \
                    and args.get("repeat") == "daily":
                self.wealth_ids[oid] = key
            if args.get("repeat") and key.startswith("o_") and key.endswith(("_end", "_win", "_final")):
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
            self.wealth_ids = {oid: k for oid, k in self.wealth_ids.items() if oid in present}
        evs = [ev.lower() for ev in lst(self.o.get("recent_events")) if isinstance(ev, str)]
        if any("have embarked on their journey" in ev or "caravan has left" in ev for ev in evs):
            self.caravan_out = True
            self.caravan_in = False
            self.caravan_in_since = None
        elif any("merchants need a trade depot" in ev
                 or ("merchants" in ev and ("arrived" in ev or "leaving soon" in ev))
                 or ("caravan" in ev and "arrived" in ev) for ev in evs):
            if not self.caravan_in:
                self.caravan_in = True
                self.caravan_in_since = self.now
        if self.caravan_in and self.caravan_in_since is not None and self.now - self.caravan_in_since > 42 * DAY:
            self.caravan_in = False
            self.caravan_in_since = None
        self.zones = [z for z in lst(self.o.get("zones")) if isinstance(z, dict)]
        self.free = d(self.st.get("furniture_free"))
        self.placed = {}
        unbuilt_f = set()
        for f in lst(self.o.get("furniture")):
            if not isinstance(f, dict):
                continue
            fk = (f.get("kind"), f.get("x"), f.get("y"), f.get("z"))
            if f.get("built") is False and None not in fk:
                self.furn_unbuilt_since.setdefault(fk, self.now)
                unbuilt_f.add(fk)
                if self.now - self.furn_unbuilt_since[fk] >= FURN_STUCK_DAYS * DAY:
                    continue   # suspended furniture (#173): stop counting it so replacements get placed
            self.placed[f.get("kind")] = self.placed.get(f.get("kind"), 0) + 1
        if isinstance(self.o.get("furniture"), list):
            self.furn_unbuilt_since = {k: v for k, v in self.furn_unbuilt_since.items() if k in unbuilt_f}
        if isinstance(self.o.get("workshops"), list):
            seen, unbuilt = set(), set()
            for w in lst(self.o.get("workshops")):
                w = d(w)
                if w.get("id") is not None and not w.get("built") and any(
                        d(j).get("job") == "ConstructBuilding" and d(j).get("suspended") for j in lst(w.get("job_details"))):
                    key = self.shop_key(w)
                    self.stuck_since.setdefault(key, self.now)
                    seen.add(key)
                if w.get("id") is not None and not w.get("built") and w.get("type") == "Butchers":
                    self.unbuilt_since.setdefault(self.shop_key(w), self.now)
                    unbuilt.add(self.shop_key(w))
            self.stuck_since = {k: v for k, v in self.stuck_since.items() if k in seen}
            self.unbuilt_since = {k: v for k, v in self.unbuilt_since.items() if k in unbuilt}
        else:
            self.stuck_since = {}    # an unreadable listing breaks the record: suspensions are timed afresh
                                     # (a shop does not go back to unbuilt, so unbuilt_since keeps its ticks)
        self.surface = self.map.get("surface_z")
        if isinstance(self.surface, int) and not isinstance(self.surface, bool):
            self.surface_seen = self.surface
        if self.w_used_tick != self.now:
            self.w_used_now, self.w_used_tick = set(), self.now

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

    # ---- digging clear of water
    def wet_near(self, x, y, z_top, z_bot, radius):
        """Revealed liquid tiles {(x, y, z)} within `radius` of (x, y) on levels z_bot..z_top (the map query, at
        most 5 levels a call), or None when the query fails or its answer can't be read."""
        if self.wet_tick != self.now:
            self.wet_seen, self.wet_tick = {}, self.now
        key = (x, y, z_top, z_bot, radius)
        if key not in self.wet_seen:
            try:
                q = d(self.game.query("map", x=x, y=y, z=z_top, z2=z_bot, radius=radius))
                res = d(q.get("result")) if isinstance(q.get("result"), dict) else q
                liq = res.get("liquid")
                self.wet_seen[key] = None if not isinstance(liq, list) else {
                    (t.get("x"), t.get("y"), t.get("z")) for t in liq if isinstance(t, dict)}
            except Exception as e:     # a failed look leaves the dig as asked (the inherited behaviour)
                log("wet_query_error", error=repr(e)[:160])
                self.wet_seen[key] = None
        return self.wet_seen[key]

    def dry_dig(self, tool, args):
        """A dig_room or dig_stairs as it may go ahead clear of revealed liquid, or None to dig nothing.

        A room box (from the site's top-left, as large as asked) is cut back to the largest box, no smaller than
        the site's own 3x3, with no liquid within WATER_RING tiles of it on its own level; None if there is none.
        (Water on the level above stays there: the leader's harness dug a room under a brook without a flood.) A
        stair stops above the first level of its shaft with liquid within WATER_RING; None if that is its first
        level. What the map can't show (hidden tiles, an aquifer not yet breached) is not judged here; a failed
        look leaves the dig as asked."""
        if tool not in ("dig_room", "dig_stairs") or not isinstance(args, dict):
            return args
        site = next((s for s in self.sites if s.get("id") == args.get("site")), None)
        if not site or not all(type(site.get(k)) is int for k in ("x", "y", "z")):
            return args
        x0, y0, z, ring = site["x"], site["y"], site["z"], WATER_RING
        if tool == "dig_room":
            try:
                w, h = max(1, min(15, int(args.get("w") or 3))), max(1, min(15, int(args.get("h") or 3)))
            except (TypeError, ValueError):
                return args
            wet = self.wet_near(x0 + w // 2, y0 + h // 2, z, z, min(20, max(w, h) // 2 + ring + 1))
            if wet is None:
                return args

            def clear(ww, hh):     # its own level only: a room dug under water keeps the floor of the level above
                return not any(zz == z and x0 - ring <= x <= x0 + ww - 1 + ring
                               and y0 - ring <= y <= y0 + hh - 1 + ring for x, y, zz in wet)
            if clear(w, h):
                return args
            fits = [(ww * hh, ww, hh) for ww in range(w, min(3, w) - 1, -1) for hh in range(h, min(3, h) - 1, -1)
                    if clear(ww, hh)]          # never below the site's own 3x3: a sliver beside water is no room
            if not fits:
                return None
            _, ww, hh = max(fits)
            return {**args, "w": ww, "h": hh}
        try:
            bottom = int(args.get("z_bottom", z - 1))
        except (TypeError, ValueError):
            return args
        if bottom >= z:
            return args
        wet = set()
        for top in range(z, bottom - 1, -5):
            part = self.wet_near(x0, y0, top, max(bottom, top - 4), ring + 1)
            if part is None:
                return args
            wet |= part
        levels = {zz for x, y, zz in wet if abs(x - x0) <= ring and abs(y - y0) <= ring and bottom <= zz <= z}
        if not levels:
            return args
        if z in levels or max(levels) + 1 >= z:
            return None
        return {**args, "z_bottom": max(levels) + 1}

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
        self.farms()
        self.supply()
        if self.open_play():
            self.provision()
        self.furnish()
        self.rezone()
        self.closer()
        self.progression_push()

    def management(self):
        if self.open_task():
            self.fisher_check()
        if not self.adm.get("manager_active_for_orders"):
            free = [p for p in self.people if not p.get("positions") and p.get("adult", True)]
            if self.open_task() and self.fisher_ids:
                non_fish = [p for p in free if p.get("id") not in self.fisher_ids]
                if non_fish:
                    free = non_fish
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
        if self.open_task():
            self.no_fishing(plugins)
            self.fisher_protect()
        self.office()

    def farm_overlap(self, site):
        """True if site overlaps any existing farm plot or is an R site marked used by a farm."""
        if site.get("kind") == "R" and any(str(u).startswith("farm") for u in lst(site.get("used_by"))):
            return True
        if not all(type(site.get(k)) is int for k in ("x", "y", "z")):
            return False
        sx, sy, sz = site["x"], site["y"], site["z"]
        sw, sh = site.get("w") or 1, site.get("h") or 1
        for fp in lst(self.o.get("farm_plots")):
            fp = d(fp)
            if fp.get("z") != sz or not all(type(fp.get(k)) is int for k in ("x", "y")):
                continue
            fx, fy, fw, fh = fp["x"], fp["y"], fp.get("w") or 3, fp.get("h") or 3
            if not (sx + sw <= fx or sx >= fx + fw or sy + sh <= fy or sy >= fy + fh):
                return True
        return False

    def office_sites_in(self, zone):
        """Sites wholly covered by `zone` that can accept a placed chair."""
        out = []
        for s in self.kind("R") + self.kind("A"):
            w, h = s.get("w") or 0, s.get("h") or 0
            if s.get("id") in self.bad_office_chair_sites or not (0 < w <= PLACE_SIDE and 0 < h <= PLACE_SIDE):
                continue
            if s.get("kind") == "R" and not s.get("dug"):
                continue
            if self.farm_overlap(s) or not covers(zone, s):
                continue
            out.append(s)
        out.sort(key=lambda s: (s.get("kind") != "R", (s.get("w") or 0) * (s.get("h") or 0), str(s.get("id"))))
        return out

    def office_zone_candidates(self):
        """Legal <=20x20 non-farm sites for a new manager office zone (open play)."""
        farm_zs = {d(fp).get("z") for fp in lst(self.o.get("farm_plots"))}
        out = []
        for s in self.kind("R") + self.kind("A"):
            w, h = s.get("w") or 0, s.get("h") or 0
            if s.get("id") in self.bad_office_zone_sites or not (0 < w <= ZONE_SIDE and 0 < h <= ZONE_SIDE):
                continue
            if self.farm_overlap(s):
                continue
            if s.get("kind") == "R":
                if not s.get("dug") or lst(s.get("used_by")):
                    continue
                role = self.roles.get(s.get("id"))
                if role == "farm":
                    continue
                pri = 0 if role == "office" else 1 if role is None else 2
                out.append((pri, 0, w * h, str(s.get("id")), s))
            else:
                if self.cit < 14 and "office" in self.roles.values():
                    continue
                if (s.get("open_tiles") or 0) < 4:
                    continue
                pri = 3 if s.get("z") not in farm_zs else 4
                out.append((pri, 1, w * h, str(s.get("id")), s))
        out.sort(key=lambda t: t[:4])
        return [t[4] for t in out]

    def office_needs_free_chair(self):
        """Open play: True when the manager does not yet have a built or planned chair in a valid office."""
        if not self.open_task() or self.cit < 7 or not self.adm.get("manager_active_for_orders"):
            return False
        if d(self.adm.get("manager_office")).get("chair"):
            return False
        mgr = self.adm.get("MANAGER_id")
        return not any(z.get("owner") == mgr and z.get("id") not in self.bad_offices
                       and (d(z.get("furniture")).get("chair") or d(z.get("furniture_planned")).get("chair"))
                       for z in self.zone("office"))

    def office(self):
        """DF stops validating orders around 20 citizens unless the manager has an office with a chair."""
        if not self.open_task():
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
            return

        # Open play: establish the manager's office + chair from cit >= 7 (long before Wave 2 hits 20),
        # checking <=20x20 bounds, farm overlap, and per-site retries so it never deadlocks.
        if self.cit < 7 or not self.adm.get("manager_active_for_orders"):
            return
        mo = self.adm.get("manager_office")
        if isinstance(mo, dict) and mo.get("chair"):
            return
        mgr = self.adm.get("MANAGER_id")
        offices = self.zone("office")
        owned = [z for z in offices if mgr is not None and z.get("owner") == mgr and z.get("id") not in self.bad_offices]
        if any(d(z.get("furniture")).get("chair") or d(z.get("furniture_planned")).get("chair") for z in owned):
            return
        for mine in owned:
            cands = self.office_sites_in(mine)
            if not cands:
                self.bad_offices.add(mine.get("id"))
                continue
            if (self.free.get("chair") or 0) > 0:
                s = cands[0]
                r = self.act("office_chair_%s_%s" % (mine.get("id"), s["id"]), "place_furniture",
                             {"kind": "chair", "site": s["id"]}, retry=1, limit=2)
                if r and not r.get("ok") and r.get("error_code") in ("no_space", "bad_arguments", "site_used"):
                    self.bad_office_chair_sites.add(s["id"])
            return
        spares = [z for z in offices if z.get("owner") is None and z.get("id") not in self.bad_offices
                  and (d(z.get("furniture")).get("chair") or d(z.get("furniture_planned")).get("chair")
                       or self.office_sites_in(z))]
        if spares and mgr is not None:
            spares.sort(key=lambda z: (not (d(z.get("furniture")).get("chair") or d(z.get("furniture_planned")).get("chair")),
                                       z.get("id") or 0))
            self.act("office_assign_%s" % spares[0]["id"], "assign_zone",
                     {"zone_id": spares[0]["id"], "dwarf_id": mgr}, retry=1, limit=3)
            return
        for room in self.office_zone_candidates():
            r = self.act("office_zone_%s" % room["id"], "make_zone", {"kind": "office", "site": room["id"]},
                         retry=1, limit=2)
            if r is None:
                continue
            if r.get("ok"):
                zid = d(r.get("result")).get("zone_id") or d(r.get("result")).get("id")
                if zid is not None and mgr is not None:
                    self.act("office_assign_%s" % zid, "assign_zone", {"zone_id": zid, "dwarf_id": mgr}, retry=1, limit=3)
                if (self.free.get("chair") or 0) > 0:
                    self.act("office_chair_new_%s" % room["id"], "place_furniture",
                             {"kind": "chair", "site": room["id"]}, retry=1, limit=2)
                return
            self.bad_office_zone_sites.add(room["id"])

    def build(self, wtype, retry=3, key=None):
        """One workshop of `wtype`: the first W site this run has not built this type on yet (the site the last
        build consumed is unusable, and moving on keeps a second Carpenters from retrying the first)."""
        for s in self.kind("W"):
            if (s.get("id"), wtype) in self.full_sites:
                continue
            if self.open_task() and s.get("id") in self.w_used_now:
                continue
            if not self.material():
                return None
            r = self.act(key or ("ws_" + wtype), "build_workshop", {"type": wtype, "site": s["id"]}, retry=retry)
            if r and r.get("ok"):
                self.full_sites.add((s.get("id"), wtype))
                if self.open_task():
                    self.w_used_now.add(s.get("id"))
                self.built_n[wtype] = self.built_n.get(wtype, 0) + 1
            return r
        return None

    def shops(self):
        """Listed workshop types, except one whose every copy has had its construction suspended for STUCK_DAYS (build
        it elsewhere), until STUCK_REBUILDS more are listed or 1 + STUCK_REBUILDS builds were accepted. A Butchers
        left unbuilt for STUCK_DAYS is stuck too, suspended or not, and has no such limit."""
        rows = [d(w) for w in lst(self.o.get("workshops"))]
        have, stuck = set(), {}
        for w in rows:
            since = self.stuck_since.get(self.shop_key(w))
            idle = self.unbuilt_since.get(self.shop_key(w))
            if (since is not None and self.now - since >= STUCK_DAYS * DAY) \
                    or (idle is not None and self.now - idle >= STUCK_DAYS * DAY):
                stuck[w.get("type")] = stuck.get(w.get("type"), 0) + 1
            else:
                have.add(w.get("type"))
        for t, n in stuck.items():
            if t not in have and t != "Butchers" and (n > STUCK_REBUILDS or self.built_n.get(t, 0) > STUCK_REBUILDS):
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
        # is still to be made (the workshop list could not be read yet) and never where nobody is to fish
        if "Fishery" not in have and any(p.get("job") == "Fish" for p in self.people) \
                and (self.calm is False if self.open_task() else True):
            self.build("Fishery")
        if open_play and "Butchers" not in have and have >= {"Carpenters", "Still", "Kitchen"} \
                and (self.calm is False or self.days_left <= FEAST_DAYS + BUTCHER_LEAD or "Butchers" in listed):
            self.build("Butchers")   # the feast must not wait for a workshop (building one took a week in game);
                                     # one that was started and is stuck is not left to the next cull either
        if self.beds_first or self.surge:
            n = sum(1 for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Carpenters")
            target = SURGE_CARPENTERS if self.surge and self.beds_unmet() and self.cit >= 15 and self.logs() >= 5 else 2
            if n < target and have:
                self.build("Carpenters")

    def office_chair_needed(self):
        if self.cit < 14 or not self.adm.get("manager_active_for_orders"):
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

    def extra_room_needs(self):
        """Open play: roles that still need a newly dug room because existing sites cannot hold them."""
        if not self.open_task():
            return []
        extra = []
        if self.cit > (self.placed.get("bed") or 0) and not self.bed_sites():
            extra.append("dorm")
        if self.real_seats() < math.ceil(self.cit / 2) and self.dine_site() is None:
            extra.append("dine")
        if self.office_needs_free_chair():
            mgr = self.adm.get("MANAGER_id")
            has_usable = any(z.get("id") not in self.bad_offices and (z.get("owner") in (None, mgr))
                             and (d(z.get("furniture")).get("chair") or d(z.get("furniture_planned")).get("chair")
                                  or self.office_sites_in(z))
                             for z in self.zone("office"))
            if not has_usable and not self.office_zone_candidates():
                extra.append("office")
        return extra

    def digging(self):
        rooms = self.kind("R")
        pending = self.o.get("dig_designations_pending") or 0
        stairs = [s for s in self.kind("S") if s.get("id") not in self.wet_sites] or self.kind("S")
        extra_need = self.extra_room_needs()
        need_dorm_access = self.surge and "dorm" not in self.roles.values() and not any(
            self.dorm_depth_ok(r) for r in self.undug_rooms() if r["id"] not in self.roles)
        need_more_r = bool(extra_need) and not [r for r in self.undug_rooms()
                                                if r["id"] not in self.roles and r["id"] not in self.wet_sites]
        if stairs and self.surface is not None and (len(rooms) < 2 or (not any(r.get("soil") for r in rooms)
                                                                       and not self.o.get("farm_plots")) or need_dorm_access):
            self.act("stairs", "dig_stairs", {"site": stairs[-1]["id"], "z_bottom": self.surface - 4}, retry=12, limit=3)
        elif need_more_r and stairs and self.surface is not None:
            self.act("stairs_extra", "dig_stairs", {"site": stairs[-1]["id"], "z_bottom": self.surface - 6}, retry=12, limit=2)
        if pending > 90:
            return
        farms = len(lst(self.o.get("farm_plots"))) + sum(1 for r, v in self.roles.items() if v == "farm" and not any(z.get("id") == r and z.get("used_by") for z in self.kind("R")))
        for r in self.undug_rooms():
            rid = r["id"]
            if rid in self.roles or rid in self.wet_sites:
                continue
            need = [x for x in ("dorm", "dine", "office") if x not in self.roles.values()]
            for x in extra_need:
                if x not in need:
                    need.append(x)
            if self.surge and "dorm" in need and self.dorm_depth_ok(r):
                result = self.act("dig_" + rid, "dig_room", {"site": rid, "w": 9, "h": 7}, retry=3, limit=2)
                if result and result.get("ok"):
                    self.roles[rid] = "dorm"
                    self.dorm_box = (r.get("x"), r.get("y"), r.get("z"), *self.dug_size.get(rid, (9, 7)))
            elif r.get("soil") and farms < self.farm_target():
                result = self.act("dig_" + rid, "dig_room", {"site": rid}, retry=3, limit=2)
                if result and (not self.surge or result.get("ok")):
                    self.roles[rid] = "farm"
                    farms += 1
            elif need:
                role = need[0]
                if self.surge and role == "dorm" and not self.dorm_depth_ok(r):
                    continue
                dine_sz = {"w": 9, "h": 7} if self.full_year() else {"w": 7, "h": 5}
                size = {"dorm": {"w": 9, "h": 7}, "dine": dine_sz, "office": {}}[role]
                result = self.act("dig_" + rid, "dig_room", {"site": rid, **size}, retry=3, limit=2)
                if result and (not self.surge or result.get("ok")):
                    self.roles[rid] = role
                    if role in extra_need:
                        extra_need.remove(role)
                    if self.surge and role == "dorm":
                        self.dorm_box = (r.get("x"), r.get("y"), r.get("z"), *self.dug_size.get(rid, (9, 7)))

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
        brew = self.standing("brew_drink") or ((self.drink_growth or self.brew_in_window) and bool(self.brew_own)) or self.brew_stopped
        if not brew:
            when = [{"stock": "plants_brewable", "at_least": 2}, {"stock": "barrels_empty", "at_least": 1}]
            if self.full_year():
                when[0] = {"stock": "plants_brewable", "at_least": BREW_KEEP}
            elif self.brew_in_window:
                # Hold a 5-plant reserve before the window so brew_in_window never drains plants to 0 on day 38
                when[0] = {"stock": "plants_brewable", "at_least": 5}
            elif not self.drink_growth:
                when.insert(0, {"stock": "drink", "below": DRINK_CAP})
            key = "o_brew_growth" if (self.drink_growth or self.brew_in_window) else "o_brew"
            self.act(key, "add_order", {"recipe": "brew_drink", "amount": 3, "repeat": "daily", "when": when}, retry=3)
        if not self.standing("make_barrel"):
            b_amt, b_below = (3, 6) if self.full_year() else (2, 4)
            self.act("o_barrel", "add_order", {"recipe": "make_barrel", "amount": b_amt, "repeat": "daily", "when": [
                {"stock": "barrels_empty", "below": b_below}, {"stock": "logs", "at_least": 2}]}, retry=3)
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
        chair_want = seats + 1
        if self.open_task() and self.office_needs_free_chair() and (self.free.get("chair") or 0) == 0:
            chair_want = max(chair_want, chairs + 1)
        wants = (("make_bed", self.st.get("beds") or 0, bed_target),
                 ("make_table", tables, seats),
                 ("make_chair", chairs, chair_want))
        if self.brew_in_window:
            wants = ()
        elif self.beds_first:
            wants = wants[:1]
            if self.surge and self.office_chair_needed():
                wants += (("make_chair", self.free.get("chair") or 0, 1),)
        for recipe, have, want in wants:
            if have < want and not self.pending(recipe) and self.logs():
                batch = 30 if self.surge and recipe == "make_bed" else (16 if self.full_year() else 8)
                self.act("o_" + recipe, "add_order", {"recipe": recipe, "amount": min(batch, want - have)}, retry=1, limit=99)

    # ---- the closer: what the score reads at the end of the run
    def in_endgame(self):
        """Open-play tasks: the scored final stretch (the last quarter of the run, 7-28 days) is near."""
        return self.hands_off is None and self.days_left is not None and self.days_left <= ENDGAME_DAYS

    def in_window_prep(self):
        """Lab tasks: the hands-off window starts soon; after it begins only standing orders keep working."""
        return isinstance(self.hands_off, int) and 0 < self.hands_off <= WINDOW_PREP_DAYS

    # ---- the growth push: created wealth for Hamlet + autumn Wave 2 boost on full-year games
    def progression_push(self):
        """Full-year games: build extra Carpenters early (accelerating housing, hatches, and wealth) while reserving
        free W sites for Butchers, then run up to six daily wooden MakeTool orders (Wheelbarrows, Minecarts,
        Stepladders — all 50 base value in DF 53.16, amount=30) from WEALTH_FROM_DAY until the autumn caravan leaves
        (or WEALTH_STOP_DAY / WEALTH_TARGET), pausing whenever housing or surface hatches need carpenters. Saturating
        multiple workshops keeps autolabor assigning idle dwarves to CARPENTRY without diluting into lower-value jobs."""
        if self.hands_off is not None or self.lab or self.beds_first or (self.days or 0) < 336:
            return
        if not isinstance(self.day, int) or self.cit < 7:
            return
        w_cr = d(self.o.get("wealth")).get("created") or 0
        seats_need = math.ceil(self.cit / 2)
        housing_ok = ((self.st.get("beds") or 0) >= self.cit
                      and (self.st.get("tables") or 0) >= seats_need
                      and (self.st.get("chairs") or 0) >= seats_need + 1)
        sealed, _ = self.surface_hatches()
        hatches_ok = (sealed or self.day >= 60) and not self.pending("make_hatch_cover")
        in_window = WEALTH_FROM_DAY <= self.day <= WEALTH_STOP_DAY and not self.caravan_out and w_cr < WEALTH_TARGET
        if self.wealth_ids and (not in_window or not housing_ok or not hatches_ok):
            for oid in sorted(self.wealth_ids):
                self.act("wealth_stop_%s" % oid, "cancel_order", {"order_id": oid}, retry=1, limit=4)
        # Scale Carpenters early once core shops are up, reserving W sites for Butchers
        core_up = {"Carpenters", "Still", "Kitchen"} <= self.shops()
        if core_up and not self.caravan_out and 4 <= self.day <= 185 and w_cr < WEALTH_TARGET:
            carp = sum(1 for w in lst(self.o.get("workshops"))
                       if isinstance(w, dict) and w.get("type") == "Carpenters")
            keep_w = 1 if "Butchers" in self.shops() else 2
            free_w = sum(1 for s in self.kind("W") if s.get("free", True) and not lst(s.get("used_by"))
                         and s.get("id") not in self.w_used_now and (s.get("id"), "Carpenters") not in self.full_sites)
            target = 4 if self.logs() >= 40 else 1
            if housing_ok and hatches_ok and self.logs() >= WEALTH_LOGS:
                target = min(8, max(4, self.cit - 2))
            if carp < target and self.built_n.get("Carpenters", 0) < 9 and free_w > keep_w:
                self.build("Carpenters", retry=1, key="ws_carp_extra")
        if in_window:
            if not core_up or not housing_ok or not hatches_ok:
                return
            carp = sum(1 for w in lst(self.o.get("workshops"))
                       if isinstance(w, dict) and w.get("type") == "Carpenters")
            active_keys = set(self.wealth_ids.values())
            slots = (
                (1, "o_wheelbarrow", "ITEM_TOOL_WHEELBARROW", WEALTH_LOGS),
                (2, "o_minecart", "ITEM_TOOL_MINECART", WEALTH_LOGS + 5),
                (3, "o_stepladder", "ITEM_TOOL_STEPLADDER", WEALTH_LOGS + 10),
            )
            for min_carp, key, sub, min_logs in slots:
                if carp >= min_carp and key not in active_keys:
                    self.act(key, "add_manager_order",
                             {"job": "MakeTool", "item_subtype": sub,
                              "material_category": ["wood"], "amount": 15, "repeat": "daily",
                              "when": [{"item_type": "WOOD", "at_least": min_logs}]},
                             retry=3, limit=20)
            return
        if self.day < PROG_FROM_DAY or w_cr >= PROG_WEALTH:
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

    def closer(self):
        if self.in_endgame():
            self.endgame_supply()
            self.housing_check()
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
        if not self.brew_stopped:
            self.act("o_brew_end", "add_order", {"recipe": "brew_drink", "amount": 4, "repeat": "daily", "when": [
                {"stock": "drink", "below": cap}, {"stock": "plants_brewable", "at_least": reserve},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=3, limit=4)
            if self.open_play() and not self.full_year() and self.days_left <= FINAL_STRETCH \
                    and (self.st.get("food_edible") or 0) >= max(10, self.cit):
                # the scored stretch itself (non-full-year open tasks like MY1): drink must not fall across it.
                # Full-year embarks already have ceiling-less o_brew with BREW_KEEP=6; adding a 2-plant order there
                # drains food plants into drink. Keep <=3 `when` conditions and gate food in Python.
                self.act("o_brew_final", "add_order", {"recipe": "brew_drink", "amount": 3, "repeat": "daily", "when": [
                    {"stock": "drink", "below": cap}, {"stock": "plants_brewable", "at_least": 2},
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
                and not self.surge and not self.beds_first and not self.drink_growth
                and not self.brew_in_window)

    def full_year(self):
        """A full-year game on a new embark."""
        return self.open_task() and (self.days or 0) >= 336

    def open_play(self):
        """An open task on a reply that has its clock: everything timed in days left needs this one."""
        return self.open_task() and isinstance(self.days_left, int)

    def window_supply(self):
        """Before a hands-off window: brew whenever a plant and a barrel allow, at a cap the window can't reach, so
        drink keeps rising while nobody can act (LT08 wants drink at the end above drink at the window's start;
        LT01 wants a batch brewed inside it). Plants are food too, and food must also hold through the window, so
        half a plant per citizen stays unbrewed. Barrels are the usual limit: an extra barrel order runs alongside.
        Beds come first in the carpenters' queue on a migrant task, with a second Carpenters to make them."""
        plant_min = 1 if self.brew_in_window else max(3, self.cit // 2)
        open_brew_win = (not self.brew_in_window
                         or (isinstance(self.hands_off, int) and self.hands_off <= 3)
                         or (self.st.get("drink") or 0) < max(20, 2 * self.cit))
        if open_brew_win:
            self.act("o_brew_win", "add_order", {"recipe": "brew_drink", "amount": 5, "repeat": "daily", "when": [
                {"stock": "drink", "below": 2000}, {"stock": "plants_brewable", "at_least": plant_min},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=2, limit=5)
            if self.brew_in_window:
                self.act("o_fruit_win", "add_order", {"recipe": "brew_drink_from_fruit", "amount": 3, "repeat": "daily", "when": [
                    {"stock": "drink", "below": 2000}, {"stock": "barrels_empty", "at_least": 1}]}, retry=2, limit=5)
        self.act("o_barrel_win", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 10}, {"stock": "logs", "at_least": 3}]}, retry=2, limit=5)
        butcher_floor = (2 if self.brew_in_window else 4) * self.cit
        if (self.st.get("food_edible") or 0) < butcher_floor:
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
        if self.brew_in_window:
            return
        beds_short = self.cit - (self.placed.get("bed") or 0)
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
            if not built_only and f.get("built") is False:
                fk = (k, f.get("x"), f.get("y"), f.get("z"))
                since = self.furn_unbuilt_since.get(fk)
                if since is not None and self.now - since >= FURN_STUCK_DAYS * DAY:
                    continue
            member = bool(dining & set(lst(f.get("zone_ids"))))
            if member and not capped:
                n[k] += 1
            elif not member and prospective and covers(site, f):
                n[k] += 1
        return n

    def dine_stock(self, kind, site):
        """Tables or chairs that are or will be dining seats (dining_kinds), plus the free ones."""
        return self.dining_kinds(site=site)[kind] + (self.free.get(kind) or 0)

    def may_zone(self, site):
        """make_zone takes `site` (no side over ZONE_SIDE; a room nothing touches) and this layer may zone it now:
        never yet, or its box or dug area changed, or ZONE_RECHECK days on, fewer than ZONE_TRIES times, and its
        make_zone refused fewer than ZONE_FAILS times."""
        w, h = site.get("w") or 0, site.get("h") or 0
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
            w, h = s.get("w") or 0, s.get("h") or 0
            if not (0 < w <= PLACE_SIDE and 0 < h <= PLACE_SIDE) or self.dine_full.get(s.get("id")) == self.fill_mark(s):
                return False
            if self.retired_site(s):
                return False
            if s.get("kind") == "R":
                used = [str(u) for u in lst(s.get("used_by"))]
                if any(u.startswith("farm") for u in used) or self.farm_overlap(s) or (alt and not s.get("dug")):
                    return False
                if used:
                    return zoned(s)
                if not (w <= ZONE_SIDE and h <= ZONE_SIDE):
                    return False
                return not alt or self.roles.get(s.get("id")) in (None, "dine")
            return (s.get("open_tiles") or 0) >= 6 and (zoned(s) or (w <= ZONE_SIDE and h <= ZONE_SIDE))

        if fits(first, False):
            return first
        alts = [s for s in self.kind("A") + self.kind("R") if fits(s, True)]
        alts.sort(key=lambda s: (not zoned(s), s.get("kind") != "A", -(s.get("open_tiles") or 0), str(s.get("id"))))
        if alts:
            return alts[0]
        # Last resort on open play: any dug, non-farm, unused <=20x20 R site (even one initially dug as dorm/office)
        # so dining placement never stalls permanently if every A site has grown past 20x20.
        if self.open_task():
            fb = [s for s in self.kind("R") if s.get("dug") and not lst(s.get("used_by"))
                  and not self.farm_overlap(s) and not self.retired_site(s)
                  and self.dine_full.get(s.get("id")) != self.fill_mark(s)
                  and 0 < (s.get("w") or 0) <= ZONE_SIDE and 0 < (s.get("h") or 0) <= ZONE_SIDE]
            if fb:
                fb.sort(key=lambda s: (-(s.get("w") or 0) * (s.get("h") or 0), str(s.get("id"))))
                return fb[0]
        return None

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
                site = next((x for x in self.dug_rooms() if x.get("z") == z
                             and (x.get("w") or 0) <= 20 and (x.get("h") or 0) <= 20), None)
            if not site:
                continue
            if kinds & {"table", "chair"} and not self.zoned_now(site):   # furnish zoned it on this observation
                self.act("rz_dine_%s" % site["id"], "make_zone", {"kind": "dining_hall", "site": site["id"]}, retry=2, limit=3)
            if "bed" in kinds:
                self.act("rz_dorm_%s" % site["id"], "make_zone", {"kind": "dormitory", "site": site["id"]}, retry=2, limit=3)
        for z, kinds in by_z.items():
            if kinds.get("table") and kinds.get("chair"):
                site = next((x for x in self.kind("A") if x.get("z") == z and (x.get("open_tiles") or 0) >= 6
                             and (x.get("w") or 0) <= 20 and (x.get("h") or 0) <= 20), None)
                if not site and self.open_task():
                    site = next((x for x in self.dug_rooms() if x.get("z") == z and not lst(x.get("used_by"))
                                 and (x.get("w") or 0) <= 20 and (x.get("h") or 0) <= 20), None)
                if site and not self.zoned_now(site):
                    self.act("dx_dine_%s" % site["id"], "make_zone", {"kind": "dining_hall", "site": site["id"]}, retry=3, limit=2)

    def bed_sites(self):
        """Open play: legal <=PLACE_SIDE sites for placing beds, ordered by preference (existing dorm zone, dorm R
        room, non-farm A site, other dug R rooms, fallback A sites). Prevents the >40x40 place_furniture deadlock."""
        farm_zs = {d(fp).get("z") for fp in lst(self.o.get("farm_plots"))}
        dorms = self.zone("dorm") + self.zone("bedroom")
        pref = self.room_for("dorm")
        pref_id = pref.get("id") if isinstance(pref, dict) else None
        out = []
        for s in self.kind("A") + self.kind("R"):
            w, h = s.get("w") or 0, s.get("h") or 0
            if not (0 < w <= PLACE_SIDE and 0 < h <= PLACE_SIDE):
                continue
            if self.bed_full.get(s.get("id")) == self.fill_mark(s) or self.farm_overlap(s):
                continue
            if s.get("kind") == "R":
                if not s.get("dug"):
                    continue
                is_zoned = any(covers(z, s) for z in dorms)
                role = self.roles.get(s.get("id"))
                pri = 0 if s.get("id") == pref_id else 1 if is_zoned else 2 if role == "dorm" else 4
                area = (s.get("open_tiles") or (w * h))
                out.append((pri, -area, str(s.get("id")), s))
            else:
                tiles = s.get("open_tiles") or 0
                if tiles < 6:
                    continue
                is_zoned = any(covers(z, s) for z in dorms)
                pri = 0 if s.get("id") == pref_id else 1 if is_zoned else (3 if s.get("z") not in farm_zs else 5)
                out.append((pri, -tiles, str(s.get("id")), s))
        out.sort(key=lambda t: t[:3])
        return [t[3] for t in out]

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

    def meeting_area(self):
        """Open play: an underground meeting_area zone draws idle dwarves off the surface wagon into the shelter (#171)."""
        if not self.open_task() or self.zone("meeting") or self.surface_seen is None:
            return
        zoned_zs = {z.get("z") for z in self.zone("dorm") + self.zone("bedroom") + self.zone("dining")
                    if isinstance(z.get("z"), int) and not isinstance(z.get("z"), bool) and z["z"] < self.surface_seen}
        cands = []
        for s in self.kind("A") + self.kind("R"):
            w, h, z = s.get("w") or 0, s.get("h") or 0, s.get("z")
            if not (isinstance(z, int) and not isinstance(z, bool) and z < self.surface_seen):
                continue
            if not (0 < w <= ZONE_SIDE and 0 < h <= ZONE_SIDE) or self.farm_overlap(s):
                continue
            if s.get("kind") == "R":
                if not s.get("dug"):
                    continue
                role = self.roles.get(s.get("id"))
                if role == "farm" or (role not in ("dorm", "dine") and z not in zoned_zs):
                    continue
                pri = 0 if z in zoned_zs else 2
            else:
                if (s.get("open_tiles") or 0) < 6:
                    continue
                pri = 0 if z in zoned_zs else 1
            cands.append((pri, s.get("kind") != "A", -(s.get("open_tiles") or w * h), str(s.get("id")), s))
        if not cands:
            return
        cands.sort(key=lambda t: t[:4])
        site = cands[0][4]
        self.act("z_meet_" + site["id"], "make_zone", {"kind": "meeting_area", "site": site["id"]}, retry=3, limit=3)

    def furnish(self):
        dorm, dine = self.room_for("dorm"), self.room_for("dine") or self.room_for("dorm")
        if self.open_task():
            self.meeting_area()
            short = self.cit + 2 - (self.placed.get("bed") or 0)
            rem = min(self.free.get("bed") or 0, short, 30)
            dorms = self.zone("dorm") + self.zone("bedroom")
            if rem > 0:
                for site in self.bed_sites():
                    if rem <= 0:
                        break
                    r = self.act("beds_" + site["id"], "place_furniture",
                                 {"kind": "bed", "site": site["id"], "count": rem}, retry=1, limit=99)
                    if r is None:
                        continue
                    if not r.get("ok"):
                        if r.get("error_code") in ("no_space", "bad_arguments", "site_used"):
                            self.bed_full[site["id"]] = self.fill_mark(site)
                        continue
                    placed = self.placement_count(r)
                    if placed is None:
                        placed = rem
                    if placed < rem:
                        self.bed_full[site["id"]] = self.fill_mark(site)
                    rem = max(0, rem - placed)
                    w, h = site.get("w") or 0, site.get("h") or 0
                    if placed > 0 and 0 < w <= ZONE_SIDE and 0 < h <= ZONE_SIDE \
                            and not any(covers(z, site) for z in dorms):
                        self.act("z_dorm_" + site["id"], "make_zone", {"kind": "dormitory", "site": site["id"]}, retry=3)
            elif not dorms:
                for site in self.bed_sites():
                    w, h = site.get("w") or 0, site.get("h") or 0
                    if 0 < w <= ZONE_SIDE and 0 < h <= ZONE_SIDE:
                        self.act("z_dorm_" + site["id"], "make_zone", {"kind": "dormitory", "site": site["id"]}, retry=3)
                        break
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
        if not self.beds_first and self.open_task():
            site = self.dine_site()
            if site:
                want = math.ceil(self.cit / 2) + 2
                placed = []
                reserve_chair = 1 if self.office_needs_free_chair() else 0
                for kind in ("table", "chair"):
                    avail = (self.free.get(kind) or 0) - (reserve_chair if kind == "chair" else 0)
                    n = min(max(0, avail), want - self.dining_kinds(site=site)[kind], 15)
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
        fisher_stationed = isinstance(self.fisher_hold, dict)
        ours = (self.lock is not None and self.lock["why"] != "invaders") or self.thaw_alert   # this layer's to clear
        if self.open_task():
            inv_ids = [d(h).get("id") for h in invaders if isinstance(d(h).get("id"), int) and not isinstance(d(h).get("id"), bool)]
            if inv_ids and squad and (squad.get("armed") or 0) >= 1 and not orders and not holding and not fisher_stationed:
                self.act("attack", "squad_order", {"order": "attack", "target_ids": inv_ids[:20]}, retry=1, limit=99)
            if (not inv_ids or holding) and orders and not fisher_stationed:
                self.act("stand_down", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
        else:
            if hostile and squad and (squad.get("armed") or 0) >= 1 and not orders and not holding:
                self.act("attack", "squad_order", {"order": "attack"}, retry=1, limit=99)
            if (not hostile or holding) and orders:
                self.act("stand_down", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
        near = (th.get("nearest_hostile_dist_to_wagon") or 10 ** 6) <= 45
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
                or self.beast_seen or self.thaw_alert or self.thaw_window(lead=2) \
                or isinstance(self.fisher_hold, dict):
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
