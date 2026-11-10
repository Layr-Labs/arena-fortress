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

PROG_CIT = 25        # progression push: citizens from which wealth ranks matter (rank thresholds 20 / 50)
PROG_DAYS = 240      # ... and the run has this many days or fewer left
PROG_LOGS = 25

SURGE_BEDS = 50
SURGE_CARPENTERS = 3
SURGE_DORM_DEPTH = 3

# Open play (MY1, OP1: no hands-off window). Measured in game: these forts have next to no stockpile space, and every
# perishable (raw meat, cleaned fish, plants, prepared meals too) rots 16-19 days after it is made. The food count is
# therefore a moving sum of the last two and a half weeks' production, and an animal slaughtered a month before the
# horizon becomes a drop inside the scored final stretch. Live animals are the one food store that can't rot.
FEAST_DAYS = 14         # animals are slaughtered from this many days before the horizon: none of that meat can rot in time
FEAST_BATCH = 3         # animals marked per pass during the feast
FEAST_KEEP = 3          # the largest animals a hunger cull leaves alone, so a feast is left to have
HUNGER = 0.25           # edible food per citizen (at least 3) below which one small animal is slaughtered: a week or
                        #   two of eating. A higher trigger empties the herd long before the feast on a food-poor fort
HUNGER_FINAL = 1.0      # ... (at least 8) from FINAL_STRETCH days out, where a day at zero costs coverage: an
                        #   earlier cull's meat rots all at once, and a game went from 14 food to none in three days
FINAL_STRETCH = 30      # the scored 28 days plus the time a cull takes to become food
HUNGER_GAP = 8          # days between hunger culls
HUNGER_GAP_FINAL = 5    # ... from FINAL_STRETCH days out
COOK_RAW = 6            # meat, fish, cheese and eggs in stock (food that is neither a plant nor a meal) from which the
                        #   feast cooks: with less, a cook would only take the plants the still needs
DRINK_SAFE = 28         # drink per citizen at which brewing stops for the feast, so the plants harvested in those
                        #   days stay in the food count. A year's drinking is about 20; with no brewing at all over the
                        #   final stretch, 28 still projects past a year at a fifth more than that rate
DRINK_REOPEN = 22       # ... and below which brewing is allowed again

# Open play: dangerous wildlife. Measured on a training embark: three undead harpies were visible two to eight days
# before they struck, every dwarf stood at the wagon on the surface, and the inherited alert never sounded because
# they were not invaders. Four and five citizens died in the two games played there with no defence. Sounding the
# alert without sealing the stairs was worse (fourteen and nine dead in two of three games: the harpies follow the
# dwarves down). With a hatch over the stair, locked while the alert holds, nobody died in three games. So a
# wildlife lockdown starts only when every surface stair this layer knows of has a built hatch, it locks those
# hatches and nothing else, and it ends at once if that seal is lost or a hostile is inside the shelter. The
# inherited shelter burrow is made before the dormitory is dug and covered one tile; it is grown as the fort is dug.
WILD_NEAR = 100         # tiles from the wagon at which any visible hostile starts a lockdown
WILD_CLEAR = 130        # ... and the lockdown holds while one is this close
WILD_DAYS = 20          # the longest a lockdown is held: the harpies stayed within 35 tiles for up to 20 days.
                        #   Workshops, drink and the wagon are above ground, so a lockdown stops production and
                        #   nobody below can drink or eat
WILD_REST = 1           # days above ground for food and drink after a lockdown that ran its full length. In game
                        #   most of a fort that had been shut for three weeks drank and ate within a day of being
                        #   let out, the harpies were back at the wagon within hours, and two dwarves died on the
                        #   third and fourth day above ground: one day, then the fort may be shut again
STAIR_CAP = 8           # the API lists at most this many surface stairs: at the cap the list may be incomplete
SHUT_TRIES = 2          # passes a hatch may stay open after it was due to be locked before the lockdown is given up
BLIND_TRIES = 3         # passes in a row without a readable observation, before any has shown every stair hatch
                        #   locked, after which the lockdown is given up: the alert is not held over an open stair
RELEASE_ROUNDS = 3      # tries at each call when the harness lets go of a lockdown on its way out
BURROW_SIDE = 40        # create_burrow refuses a box wider or taller than this, so a dug level that large is
                        #   left out of the shelter: each call for one was refused, every six days, to the end
FOREVER = 10 ** 9       # a failure limit for actions that must be retried for as long as they are needed
BUTCHER_LEAD = 3        # with nobody hunting: days before the feast at which the Butchers is built
CALM_TRIES = 5          # refusals of the labour plugin after which the inherited workshop rules return
ANIMAL_RANK = {"WATER_BUFFALO": 100, "YAK": 70, "COW": 60, "HORSE": 50, "CAMEL_1_HUMP": 50, "CAMEL_2_HUMP": 50,
               "MULE": 40, "DONKEY": 30, "REINDEER": 20, "LLAMA": 18, "PIG": 10, "ALPACA": 7, "SHEEP": 5, "GOAT": 5,
               "DOG": 3, "BIRD_TURKEY": 1.5, "BIRD_GOOSE": 1.3, "BIRD_PEAFOWL_BLUE": 1.2, "BIRD_CHICKEN": 0.7,
               "BIRD_DUCK": 0.6, "BIRD_GUINEAFOWL": 0.6, "RABBIT": 0.5, "CAVY": 0.2}
                        # relative adult size (unlisted: 1, a cat). Measured yields are flatter than size: a dog or a
                        #   cow gives 20-40 food, a turkey 10, a cat 7, a rabbit or cavy next to nothing


def log(kind, **kw):
    print(json.dumps({"t": round(time.time(), 2), "kind": kind, **kw}, default=str), flush=True)


def d(v):
    return v if isinstance(v, dict) else {}


def lst(v):
    return v if isinstance(v, list) else []


class Overseer:
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
        self.report = []         # the layer's recent actions (day, tool, args, outcome), for the model loop
        self.done = set()        # closer keys whose order was accepted once: never re-added
        self.full_sites = set()  # W site ids a workshop was built on, so the next build takes another site
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
                self.act("plug_" + name, "enable_automation", {"name": name}, retry=5)
        if self.o.get("farm_plots") and plugins.get("autofarm") != "on":
            self.act("plug_autofarm", "enable_automation", {"name": "autofarm"}, retry=5)
        if self.open_task():
            self.no_fishing(plugins)
        self.office()

    def no_fishing(self, plugins):
        """Open play: nobody fishes, and nobody hunts until the feast needs a Butchers.

        Measured on the training forts: every embark has one Fisherdwarf, the only dwarf with the fishing labour,
        who fishes 70 to 100 tiles from the wagon. River predators killed that dwarf in recorded games (a sea
        lamprey made the fisher dodge into the water and drown; alligators come ashore). No tool sets a labour, but
        DFHack's autolabor gives the fishing labour to nobody while the fort has no Fishery, and the hunting labour
        to nobody while it has no Butchers (its documentation; checked in game: the fishing labour went from one
        dwarf to none the day after it was enabled, and the dwarf took farm and hauling jobs at the wagon). So on
        a fort that starts with neither workshop this layer enables autolabor, builds no Fishery and builds the
        Butchers only just before the feast. A fort that already has one of them is left as it was."""
        ws = self.o.get("workshops")
        if self.calm is None and isinstance(ws, list):
            self.calm = not ({"Fishery", "Butchers"} & {d(w).get("type") for w in ws})
            log("calm", on=self.calm)
        if self.calm and plugins.get("autolabor") != "on":
            # daily until the game accepts it; after that only a slow reminder, in case the state is misreported
            r = self.act("plug_autolabor", "enable_automation", {"name": "autolabor"},
                         retry=10 if self.calm_ok else 1, limit=FOREVER)
            if r is not None and r.get("ok"):
                self.calm_ok = True
            elif r is not None:
                self.calm_fail += 1
                if self.calm_fail >= CALM_TRIES and not self.calm_ok:   # it will not turn on: the fisher fishes,
                    self.calm = False                                    # so the catch needs its Fishery again
                    log("calm", on=False, why="autolabor did not turn on")

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
            return r
        return None

    def workshops(self):
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        for t in ("Carpenters", "Still", "Kitchen"):
            if t not in have:
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
        wants = (("make_bed", self.st.get("beds") or 0, bed_target),
                 ("make_table", self.st.get("tables") or 0, seats),
                 ("make_chair", self.st.get("chairs") or 0, seats + 1))
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

    # ---- the growth push: created wealth for the ranks and a bigger migrant wave on open, year-plus runs
    def progression_push(self):
        """This build's own contribution: on a horizons without a hands-off window, the growth tier's last half is
        progression, and with no trade the steps pay on created wealth (each rank 0.5, the mayoralty 1.0,
        bench/outcomes.py progression_steps). Created wealth is furniture and crafts: the wood economy already runs
        for supply and housing, so from mid-run and 25 citizens the leftover wood becomes crafts, which also sizes
        later migrant waves by the wealth the caravan reports. Gated hard (population, days left, spare logs) so it
        competes with nothing the closer needs; every step stays inside the usual rate limits."""
        if self.hands_off is not None or self.beds_first or self.cit < PROG_CIT:
            return
        if self.days_left is None or self.days_left > PROG_DAYS or self.logs() < PROG_LOGS:
            return
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        if "Craftsdwarfs" not in have:
            self.build("Craftsdwarfs")
        if "Craftsdwarfs" in have and not self.craft_standing():
            self.act("o_crafts", "add_manager_order",
                     {"job": "MakeCrafts", "amount": 4, "repeat": "daily", "material_category": ["wood"],
                      "when": [{"item_type": "WOOD", "below": 80}]}, retry=5, limit=3)

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

    def provision(self):
        """The supply sub-score reads the food count's trend over the final stretch (the last quarter of the run, at
        most 28 days): flat or rising is full credit, falling is credited only as far as the stock would last. Food
        rots in about 17 days here, so meat from a month before the horizon is a fall inside that stretch. The
        animals are therefore kept for the last FEAST_DAYS days, when nothing slaughtered can rot before the horizon,
        and slaughtered then, a few per pass, with cooking alongside (it turns tallow into counted meals). Before
        that, one small animal goes only when the fort is nearly out of food."""
        food = self.st.get("food_edible") or 0
        if self.days_left <= FEAST_DAYS:
            self.feast()
        elif self.days_left <= FINAL_STRETCH:
            if food < max(8, HUNGER_FINAL * self.cit):
                self.cull("hunger", 1, smallest=True, retry=HUNGER_GAP_FINAL)
        elif food < max(3, HUNGER * self.cit):
            self.cull("hunger", 1, smallest=True, retry=HUNGER_GAP)

    def feast(self):
        self.cull("feast", FEAST_BATCH, smallest=False, retry=1)
        st = self.st
        raw = (st.get("food_edible") or 0) - (st.get("prepared_meals") or 0) - (st.get("plants_total") or 0)
        if raw >= COOK_RAW and not any(x.get("recipe") == "cook_meal" and not x.get("repeat")
                                       and (x.get("left") or 0) > 0 for x in self.orders):
            self.act("o_cook_feast", "add_order", {"recipe": "cook_meal", "amount": int(min(6, max(2, raw // 10)))},
                     retry=1, limit=99)
        drink = st.get("drink") or 0
        if drink >= DRINK_SAFE * self.cit:
            self.brew_stopped = True
        elif self.brew_stopped and drink < DRINK_REOPEN * self.cit:
            self.brew_stopped = False        # the regular supply step adds its brew order again
        if self.brew_stopped:                # every pass: a refused or cut-short cancellation is tried again
            for oid in sorted(self.brew_own):
                self.act("brew_stop_%s" % oid, "cancel_order", {"order_id": oid}, retry=1, limit=4)

    def cull(self, key, n, smallest, retry):
        """Mark up to n of the fortress's unowned tame animals for slaughter. The feast takes the largest first. A
        hunger cull takes the smallest animal that is still a meal and leaves the FEAST_KEEP largest alone unless
        the food is gone and nothing else is left. Returns how many were marked."""
        if self.now - self.culled.get(key, -10 ** 9) < retry * DAY:
            return 0
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        if "Butchers" not in have:
            self.build("Butchers")
        try:
            q = self.game.query("units", kind="animals")
        except GameAPIError as e:     # a failed read costs this pass, not the rest of the plan
            log("cull_query_error", error=str(e)[:160])
            return 0
        herd = [d(a) for a in lst(d(d(q).get("result")).get("units") or d(d(q).get("result")).get("animals"))]
        herd = [a for a in herd if a.get("tame") and a.get("pet_owner_id") in (None, -1)
                and not a.get("marked_for_slaughter") and a.get("id") is not None]
        size = lambda a: ANIMAL_RANK.get(str(a.get("race")), 1) * (1 if a.get("adult", True) else 0.3)   # noqa: E731
        herd.sort(key=lambda a: (-size(a), str(a.get("id"))))          # largest first
        pick = herd
        if smallest:
            spare = herd[FEAST_KEEP:]
            if not spare and (self.st.get("food_edible") or 0) <= 0:
                spare = herd
            pick = sorted(spare, key=lambda a: (size(a) < 1, size(a), str(a.get("id"))))
        marked = 0
        for a in pick:                # an animal the API refuses does not block the next one
            if marked >= n:
                break
            r = self.act("cull_%s" % a["id"], "slaughter", {"unit_id": a["id"]}, retry=1, limit=2)
            marked += bool(r and r.get("ok"))
        if marked or not pick:
            self.culled[key] = self.now
        log("cull", key=key, day=self.day, days_left=self.days_left, herd=len(herd), marked=marked,
            food=self.st.get("food_edible"), drink=self.st.get("drink"), cit=self.cit)
        return marked

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
        seats_short = math.ceil(self.cit / 2) - self.seats()
        if seats_short > 0 and self.logs() >= 2:
            for recipe, have in (("make_table", self.st.get("tables") or 0), ("make_chair", self.st.get("chairs") or 0)):
                want = math.ceil(self.cit / 2) + 1
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
            if kinds & {"table", "chair"}:
                self.act("rz_dine_%s" % site["id"], "make_zone", {"kind": "dining_hall", "site": site["id"]}, retry=2, limit=3)
            if "bed" in kinds:
                self.act("rz_dorm_%s" % site["id"], "make_zone", {"kind": "dormitory", "site": site["id"]}, retry=2, limit=3)
        for z, kinds in by_z.items():
            if kinds.get("table") and kinds.get("chair"):
                site = next((x for x in self.kind("A") if x.get("z") == z and (x.get("open_tiles") or 0) >= 6
                             and (x.get("w") or 0) <= 20 and (x.get("h") or 0) <= 20), None)
                if site:
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
        if dine and not self.beds_first:
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
        ours = self.lock is not None and self.lock["why"] != "invaders"    # the alert is this lockdown's to clear
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

    # ---- open play: dangerous wildlife
    def surface_hatches(self):
        """(sealed, hatches): the built hatch over each surface stair this layer has ever seen listed. Sealed only
        when every one of them has its own built hatch on the same tile, the site and door lists are present and
        the stair list is under the API's cap (at the cap it may be incomplete)."""
        doors = self.o.get("doors")
        if not isinstance(self.map.get("sites"), list) or not isinstance(doors, dict) \
                or not isinstance(doors.get("list"), list):
            return False, []
        listed = self.kind("E")
        for s in listed:
            if s.get("id") is not None and None not in (s.get("x"), s.get("y"), s.get("z")):
                self.stairs[s["id"]] = (s["x"], s["y"], s["z"])
        entries = [d(x) for x in lst(doors.get("list"))]
        found = []
        for pos in self.stairs.values():
            h = next((x for x in entries if x.get("kind") == "hatch" and x.get("built") and x.get("id") is not None
                      and (x.get("x"), x.get("y"), x.get("z")) == pos), None)
            if h is None:
                return False, []
            found.append(h)
        return bool(found) and len(listed) < STAIR_CAP, found

    def place_hatches(self):
        """A hatch cover over each stair that opens on the surface. Unlocked it changes nothing."""
        doors = d(self.o.get("doors"))
        taken = {(d(x).get("x"), d(x).get("y"), d(x).get("z")) for x in lst(doors.get("list"))
                 if d(x).get("kind") == "hatch"}
        gaps = [s for s in self.kind("E") if (s.get("x"), s.get("y"), s.get("z")) not in taken]
        if not gaps:
            return
        free = doors.get("hatch_cover_items_free") or 0
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        if free < len(gaps) and "Carpenters" in have and self.logs() >= 3 and not self.pending("make_hatch_cover"):
            self.act("o_hatch", "add_order", {"recipe": "make_hatch_cover", "amount": min(3, len(gaps) - free)},
                     retry=4, limit=4)
        for s in gaps[:free]:
            self.act("hatch_%s" % s["id"], "build_door", {"kind": "hatch", "site": s["id"]}, retry=3, limit=3)

    def grow_shelter(self, bur):
        """The shelter burrow follows the dig: each dug level is added again once it has grown, so a lockdown
        sends civilians somewhere they fit. (create_burrow adds a site's box to the same burrow.)"""
        if not any(d(b).get("civ_alert_burrow") for b in lst(bur.get("list"))):
            return
        for a in self.kind("A"):
            tiles = a.get("open_tiles") or 0
            side = max([v for v in (a.get("w"), a.get("h")) if isinstance(v, int)] or [0])
            if tiles >= 6 and tiles >= self.sheltered.get(a["id"], 0) + 10 and side <= BURROW_SIDE:
                r = self.act("shelter_%s" % a["id"], "create_burrow", {"site": a["id"]}, retry=6, limit=FOREVER)
                if r and r.get("ok"):
                    self.sheltered[a["id"]] = tiles

    def wildlife(self, alert, open_play=True):
        """One pass of the wildlife lockdown. Returns the civilian alert as this pass leaves it.

        A lockdown is this layer's own state, in two phases. HOLD: the alert is on and each surface stair's hatch is
        locked by its own id. RELEASE: the decision to end is made and is carried out until the game confirms it,
        the alert first and then the hatches; nothing new starts meanwhile. A missing or failed part of the
        observation is never read as "the danger is gone": while one is missing a hold only runs its clock, and it
        is given up if no observation has yet shown the stair shut.

        It starts when a visible hostile that is not an invader is within WILD_NEAR of the wagon, every hostile is
        listed and none is inside the shelter, the fort can be sealed, the shelter has room and the fort is owed no
        time above ground. It ends when none is within WILD_CLEAR; after WILD_DAYS (a day above ground follows);
        when invaders arrive (their inherited rule takes the alert, for no longer than WILD_DAYS from the start);
        and, for the rest of the game, when a hostile is inside the shelter, the seal is lost, or a hatch will not
        lock. With more hostiles in sight than the API lists, a standing lockdown is held to its limit: the ones
        that are not listed can be shown neither gone nor inside."""
        th, bur, doors = self.o.get("threats"), self.o.get("burrows"), self.o.get("doors")
        alert_known = isinstance(bur, dict) and isinstance(bur.get("civilian_alert"), bool)
        seen = th.get("visible_hostiles") if isinstance(th, dict) else None
        dist = th.get("nearest_hostile_dist_to_wagon") if isinstance(th, dict) else None
        dist = dist if isinstance(dist, (int, float)) and not isinstance(dist, bool) else None
        counted = isinstance(seen, int) and not isinstance(seen, bool)
        known = (isinstance(th, dict) and isinstance(doors, dict) and alert_known and counted
                 and isinstance(th.get("hostiles"), list) and isinstance(bur.get("list"), list)
                 and isinstance(doors.get("list"), list) and isinstance(self.map.get("sites"), list)
                 and (not seen or dist is not None))      # hostiles in sight and no distance: not readable
        th, bur = d(th), d(bur)
        seen = seen if counted else 0
        hostiles = [d(h) for h in lst(th.get("hostiles"))]
        listed = len(hostiles) >= seen       # the API lists twenty at most
        invaders = any(h.get("invader") for h in hostiles) or any(d(v).get("invader")
                                                                  for v in d(th.get("by_race")).values())
        shelter = next((d(b) for b in lst(bur.get("list")) if d(b).get("civ_alert_burrow")), None)
        box = d((shelter or {}).get("bbox"))
        inside = [h for h in hostiles if h.get("in_shelter") or (
            box and None not in (h.get("x"), h.get("y"), h.get("z"))
            and (box.get("x1") or 0) <= h["x"] <= (box.get("x2") or -1)
            and (box.get("y1") or 0) <= h["y"] <= (box.get("y2") or -1)
            and (box.get("z1") or 0) <= h["z"] <= (box.get("z2") or -1))]
        sealed, hatches = self.surface_hatches()
        if self.alert_pending and alert_known and not alert:
            self.alert_pending = False       # the unanswered alert is seen off
        threats_read = (isinstance(self.o.get("threats"), dict) and isinstance(th.get("hostiles"), list)
                        and isinstance(self.o.get("burrows"), dict) and isinstance(bur.get("list"), list))
        stairs_read = (isinstance(self.map.get("sites"), list) and isinstance(doors, dict)
                       and isinstance(doors.get("list"), list))
        if self.lock is not None and ((threats_read and inside) or (stairs_read and not sealed)):
            self.wild_off = True             # the scheme failed once, whatever else ends this lockdown

        if self.lock is None:
            if self.own_locks:           # a hatch still shut from an earlier lockdown: that comes first
                self.unlock_own(known)
                return alert
            if (not open_play or not known or self.wild_off or alert or invaders or not seen
                    or dist > WILD_NEAR or not listed or inside or not sealed or not shelter
                    or (shelter.get("tiles") or 0) < max(20, 2 * self.cit) or self.now < self.rest_until):
                return alert
            self.alert_pending = True    # before the call: if the answer is lost the alert is still to be cleared
            r = self.act("lockdown_on", "civilian_alert", {"on": True}, retry=0, limit=FOREVER)
            self.alert_pending = False   # answered: a lockdown below owns it, or it was refused
            if not (r and r.get("ok")):
                return alert
            self.lock = {"since": self.now, "phase": "hold", "why": None, "alert_off": False, "rest": False,
                         "due": None, "tries": 0, "fresh": True, "blind": 0, "shut": False}
            log("lockdown", event="on", day=self.day, dist=dist, hostiles=seen, cit=self.cit)
            alert = True

        lock = self.lock
        if lock["phase"] == "hold":
            age = self.now - lock["since"]
            fresh, lock["fresh"] = lock.get("fresh"), False
            if known:
                lock["blind"] = 0
                lock["shut"] = bool(hatches) and all(h.get("locked") is True for h in hatches)
                if lock["due"] is not None and lock["due"] < self.now and any(h.get("locked") is False
                                                                              for h in hatches):
                    lock["tries"] += 1           # due on an earlier pass and still open
            else:
                lock["blind"] += 1
            why = None
            if age >= WILD_DAYS * DAY:
                why = "cap"
            elif known:
                if invaders:
                    why = "invaders"
                elif inside:
                    why = "inside"
                elif not sealed:
                    why = "seal"
                elif not alert and not fresh:
                    why = "alert_off"
                elif listed and (not seen or dist > WILD_CLEAR):
                    why = "gone"
                elif lock["tries"] >= SHUT_TRIES:
                    why = "cannot_close"
            elif not lock["shut"] and lock["blind"] >= BLIND_TRIES:
                why = "cannot_close"             # alert on, nothing readable, the stair never seen shut
            if why is None:
                indoors = (shelter or {}).get("citizens_inside") or 0
                if known and (lock["due"] is not None or indoors >= self.cit - 1 or age >= DAY):
                    if lock["due"] is None:
                        lock["due"] = self.now
                    for h in hatches:            # each stair's own hatch, by id: no other door is touched
                        if h.get("locked") is not True:
                            mine = h["id"] in self.own_locks
                            self.own_locks.add(h["id"])      # before the call: a lost answer must still be undone
                            r = self.act("lock_%s" % h["id"], "lock_door", {"locked": True, "door_id": h["id"]},
                                         retry=0, limit=FOREVER)
                            if r is not None and not r.get("ok") and not mine:
                                self.own_locks.discard(h["id"])      # refused outright: it is not locked
                return True
            lock.update(phase="release", why=why, rest=(why in ("cap", "invaders")),
                        alert_off=(why in ("invaders", "alert_off")))
            if why in ("inside", "seal", "cannot_close"):
                self.wild_off = True
            if why == "invaders":            # the inherited invader rule owns the alert from here, on its own clock
                self.alert_since = lock["since"]
            log("lockdown", event="release", why=why, day=self.day, days=round(age / DAY, 1))

        # release: the alert first, then the hatches, until both are confirmed
        if lock["why"] == "invaders":
            if self.now - lock["since"] >= WILD_DAYS * DAY:
                # the invader alert has outlasted what a lockdown may: this layer takes it back and opens the fort
                lock.update(why="cap", alert_off=False, rest=True)
                log("lockdown", event="release", why="cap", day=self.day, after="invaders")
            elif not alert_known or alert:
                return alert             # the invader alert is on: the stair stays shut until it is seen off
        if lock["why"] != "invaders" and lock["alert_off"] and alert_known and alert:
            lock["alert_off"] = False    # it is on again: an earlier "off" is not taken on trust
        if not lock["alert_off"]:
            r = self.act("lockdown_off", "civilian_alert", {"on": False}, retry=0, limit=FOREVER)
            if not (r and r.get("ok")):
                return True              # still confined: the hatches stay shut, the next pass tries again
            lock["alert_off"] = True
            alert = False
        self.unlock_own(known)
        if not self.own_locks:
            if lock["rest"]:
                self.rest_until = self.now + WILD_REST * DAY
            self.lock = None
            log("lockdown", event="off", day=self.day)
        return alert

    def unlock_own(self, known=False):
        """Open every hatch this layer sent a lock for, by id. An id is dropped only when the unlock is answered ok
        or a complete door list shows it gone or says it is not locked: a missing list or field proves nothing."""
        doors = {d(x).get("id"): d(x) for x in lst(d(self.o.get("doors")).get("list"))} if known else None
        for i in sorted(self.own_locks):
            if doors is not None and (i not in doors or doors[i].get("locked") is False):
                self.own_locks.discard(i)
                continue
            r = self.act("unlock_%s" % i, "lock_door", {"locked": False, "door_id": i}, retry=0, limit=FOREVER)
            if r and r.get("ok"):
                self.own_locks.discard(i)

    def release(self):
        """On the way out: the server plays on unmanaged after an exit, and nothing in the game ends a lockdown.
        The alert is cleared and each owned hatch unlocked, every call on its own, and a call that is refused or
        fails is tried again, RELEASE_ROUNDS times in all. When the day's actions are spent, a day is advanced to
        get new ones. What is still not confirmed after that stays as it is."""
        clear = self.lock is not None or self.alert_pending
        for n in range(RELEASE_ROUNDS):
            if not clear and not self.own_locks:
                break
            spent = False
            calls = ([("civilian_alert", {"on": False}, None)] if clear else []) + \
                [("lock_door", {"locked": False, "door_id": i}, i) for i in sorted(self.own_locks)]
            for tool, args, door in calls:
                try:
                    ok = bool(d(self.game.act(tool, args)).get("ok"))
                except (GameOver, HandsOff) as e:
                    log("release_error", tool=tool, error=repr(e)[:120])
                    return                   # the game is over or out of reach: nothing more can be done
                except ActionLimit as e:
                    ok, spent = False, True
                    log("release_error", tool=tool, error=repr(e)[:120])
                except Exception as e:
                    ok = False
                    log("release_error", tool=tool, error=repr(e)[:120])
                if ok and door is None:
                    clear, self.alert_pending = False, False
                elif ok:
                    self.own_locks.discard(door)
            if spent and (clear or self.own_locks) and n + 1 < RELEASE_ROUNDS:
                try:
                    self.game.act("advance_days", {"days": 1})
                except Exception as e:
                    log("release_error", tool="advance_days", error=repr(e)[:120])
                    return
        if not clear and not self.own_locks:
            self.lock = None

    def owns_lock(self, args):
        """A model lock_door call that would undo a standing lockdown: one of this layer's hatches by id, the hatch
        on any surface stair this layer knows, or every door at once."""
        if self.lock is None and not self.own_locks:
            return False
        i = args.get("door_id") if isinstance(args, dict) else None
        if i is None or i in self.own_locks:
            return True
        spots = set(self.stairs.values())
        return any(d(x).get("id") == i and d(x).get("kind") == "hatch"
                   and (d(x).get("x"), d(x).get("y"), d(x).get("z")) in spots
                   for x in lst(d(self.o.get("doors")).get("list")))

    def seals_stair(self, args):
        """A model lock_door call on an open task that would shut a way to the surface: every door at once, a door
        on a surface stair this layer knows, any door or hatch on the surface level or above it (the stair list
        covers 30 tiles around the wagon and eight stairs, the door list covers the map), or a door that cannot
        be placed (the door list is unreadable or does not have it, or the surface level was never reported).
        This layer puts a hatch on every surface stair and shuts it itself, with the alert on and the civilians
        below. Shut at any other time it cuts the dwarves off from the food and drink on the surface, and nothing
        here would open it again: in one game the model locked all three stair hatches with one call. A lab
        task never records a stair, so there the doors stay the model's."""
        if not (self.open_task() or self.stairs) or not isinstance(args, dict) or args.get("locked") is False:
            return False
        i = args.get("door_id")
        doors = d(self.o.get("doors")).get("list")
        if i is None or not isinstance(doors, list):
            return True
        spots = set(self.stairs.values())
        for x in doors:
            if d(x).get("id") == i and not isinstance(i, bool):
                z = d(x).get("z")
                if (d(x).get("x"), d(x).get("y"), z) in spots:
                    return True
                return self.surface_seen is None or not isinstance(z, int) or z >= self.surface_seen
        return True

    def step_days(self):
        """Game days between this layer's passes on open play: one while a hostile is in sight or a lockdown is
        standing, else two."""
        if d(self.o.get("threats")).get("visible_hostiles") or self.lock is not None or self.own_locks:
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
