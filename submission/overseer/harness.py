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
from overseer.openplay import OpenPlayRules, BUTCHER_LEAD, FEAST_DAYS

DAY = 1200
MAX_PER_PASS = 12
MAX_PASSES = 3
DRINK_CAP = 300
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
PROG_LOGS = 12          #   wood crafts that runs only while this many logs are in stock (i34-9's fa9c13cc progress(),
                        #   amount raised and the log floor lowered: the official runs show the push too slow —
                        #   wealth crossed 5000 late or never, and 8 of 16 OP1 games missed the Hamlet rank)
ZONE_SIDE = 20          # make_zone refuses a site box wider or taller than this
PLACE_SIDE = 40         # place_furniture refuses a site box wider or taller than this
ZONE_RECHECK = 3        # days after which a dining site this layer zoned may be zoned again for furniture still
ZONE_TRIES = 3          #   outside every dining zone, at most this many times a site
ZONE_FAILS = 3          # refusals of a site's dining make_zone after which it is not asked again
STUCK_DAYS = 3          # a workshop construction suspended this long is built again elsewhere (no tool resumes it;
STUCK_REBUILDS = 2      #   a stuck Carpenters left a full-year fort with no bed, table or chair), this many times

SURGE_BEDS = 50
SURGE_CARPENTERS = 3
SURGE_DORM_DEPTH = 3

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
        self.built_n = {}        # workshop type -> build_workshop calls the game accepted
        self.dorm_box = None
        self.lab = False         # the task has a hands-off window (set_task); open play is everything else
        self.culled = {}         # cull key -> tick of its last pass
        self.brew_stopped = False
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

    def set_task(self, info):
        """Goal policies from the task's own public text (GET /task). A hands_off field means a lab task."""
        t = d(info)
        goal = str(t.get("goal") or "").casefold()
        self.lab = bool(t.get("hands_off"))
        self.drink_growth = bool(t.get("hands_off")) and "drink must not end lower" in goal
        self.beds_first = bool(t.get("hands_off")) and "every dwarf must have a placed bed" in goal

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
        self.farms()
        self.supply()
        if self.open_play():
            self.provision()
        self.furnish()
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
        if self.open_task():
            self.no_fishing(plugins)
        self.office()

    def office(self):
        """DF stops validating orders around 20 citizens unless the manager has an office with a chair."""
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

    def build(self, wtype, retry=3):
        """One workshop of `wtype`: the first W site this run has not built this type on yet (the site the last
        build consumed is unusable, and moving on keeps a second Carpenters from retrying the first)."""
        for s in self.kind("W"):
            if (s.get("id"), wtype) in self.full_sites:
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
        # is still to be made (the workshop list could not be read yet) and never where nobody is to fish
        if "Fishery" not in have and any(p.get("job") == "Fish" for p in self.people) \
                and (self.calm is False if self.open_task() else True):
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

    def digging(self):
        rooms = self.kind("R")
        pending = self.o.get("dig_designations_pending") or 0
        stairs = self.kind("S")
        need_dorm_access = self.surge and "dorm" not in self.roles.values() and not any(
            self.dorm_depth_ok(r) for r in self.undug_rooms() if r["id"] not in self.roles)
        if stairs and self.surface is not None and (len(rooms) < 2 or (not any(r.get("soil") for r in rooms)
                                                                       and not self.o.get("farm_plots")) or need_dorm_access):
            self.act("stairs", "dig_stairs", {"site": stairs[-1]["id"], "z_bottom": self.surface - 4}, retry=12, limit=3)
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
                result = self.act("dig_" + rid, "dig_room", {"site": rid}, retry=3, limit=2)
                if result and (not self.surge or result.get("ok")):
                    self.roles[rid] = "farm"
                    farms += 1
            elif need:
                role = need[0]
                if self.surge and role == "dorm" and not self.dorm_depth_ok(r):
                    continue
                size = {"dorm": {"w": 9, "h": 7}, "dine": {"w": 7, "h": 5}, "office": {}}[role]
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
            when = [{"stock": "plants_brewable", "at_least": 2}, {"stock": "barrels_empty", "at_least": 1}]
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
                     {"job": "MakeCrafts", "amount": 8, "repeat": "daily", "material_category": ["wood"],
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
                if any(u.startswith("farm") for u in used) or (alt and not s.get("dug")):
                    return False
                if used:
                    return zoned(s)
                return not alt or self.roles.get(s.get("id")) in (None, "dine")
            return (s.get("open_tiles") or 0) >= 6 and (zoned(s) or (w <= ZONE_SIDE and h <= ZONE_SIDE))

        if fits(first, False):
            return first
        alts = [s for s in self.kind("A") + self.kind("R") if fits(s, True)]
        alts.sort(key=lambda s: (not zoned(s), s.get("kind") != "A", -(s.get("open_tiles") or 0), str(s.get("id"))))
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
            if "bed" in kinds:
                self.act("rz_dorm_%s" % site["id"], "make_zone", {"kind": "dormitory", "site": site["id"]}, retry=2, limit=3)
        for z, kinds in by_z.items():
            if kinds.get("table") and kinds.get("chair"):
                site = next((x for x in self.kind("A") if x.get("z") == z and (x.get("open_tiles") or 0) >= 6
                             and (x.get("w") or 0) <= 20 and (x.get("h") or 0) <= 20), None)
                if site and not self.zoned_now(site):
                    self.act("dx_dine_%s" % site["id"], "make_zone", {"kind": "dining_hall", "site": site["id"]}, retry=3, limit=2)

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

    def furnish(self):
        dorm, dine = self.room_for("dorm"), self.room_for("dine") or self.room_for("dorm")
        if dorm:
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
