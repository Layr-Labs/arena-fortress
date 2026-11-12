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
"""
import json
import math
import sys
import time

from dfbench_client import ActionLimit, GameAPIError, GameClient, GameOver, HandsOff, load_task

DAY = 1200
FULL_DAYS = 10
DORM_SPARE = 3        # beds beyond the current citizens, for the next migrants
MAX_DORM = 15         # dig_room w/h cap
MAX_PER_PASS = 12
MAX_PASSES = 3
DRINK_CAP = 300
MEAL_CAP = 200
ENDGAME_DAYS = 64       # closer: the scored final stretch is the last quarter of a long run, clipped to 28 days;
                        #   the supply slope over it must be >= 0, so production is raised a month before it starts
WINDOW_PREP_DAYS = 14   # closer: days before a lab task's hands-off window when its orders and beds are secured
REPORT_KEEP = 24        # action report lines kept for the model loop
WEALTH_TARGET = 5500    # progression: the Hamlet rank needs 20 citizens and 5000 created wealth (docs/SUCCESS.md)
PROGRESS_FROM_DAY = 40  # progression: crafts start once the core setup has had its logs
MEAL_FLOOR = 10         # operator rule: at least 10 prepared meals at all times, so there is always food
DRINK_FLOOR = 10        # operator rule: same for drink (per citizen floor below)
STONE_MIN = 4           # stone work (statues, stone crafts) only from boulders above this stock
LOG_RESERVE = 25        # progression: crafts take logs only above this stock, so beds and barrels come first
MOOD_WORKSHOP = {
    "WOODCRAFT": "Craftsdwarfs", "STONECRAFT": "Craftsdwarfs", "BONECARVE": "Craftsdwarfs", "CARPENTRY": "Carpenters",
    "MASONRY": "Masons", "WOOD_BURNING": "WoodFurnace", "GLASSMAKER": "GlassFurnace", "TANNER": "Leatherworks",
    "LEATHERWORK": "Leatherworks", "WEAVING": "Loom", "CLOTHESMAKING": "Clothiers", "FORGE_WEAPON": "MetalsmithsForge",
    "FORGE_ARMOR": "MetalsmithsForge", "FORGE_FURNITURE": "MetalsmithsForge", "METALCRAFT": "MetalsmithsForge",
    "CUTGEM": "Jewelers", "ENCRUSTGEM": "Jewelers", "MECHANICS": "Mechanics", "POTTERY": "Kiln", "BOWYER": "Bowyers",
}


def log(kind, **kw):
    print(json.dumps({"t": round(time.time(), 2), "kind": kind, **kw}, default=str), flush=True)


def d(v):
    return v if isinstance(v, dict) else {}


def lst(v):
    return v if isinstance(v, list) else []


def overlaps(a, b):
    """Positive-area intersection of public site/zone boxes (not edge contact)."""
    return (a["z"] == b["z"] and a["x"] < b["x"] + b.get("w", 1)
            and b["x"] < a["x"] + a.get("w", 1)
            and a["y"] < b["y"] + b.get("h", 1)
            and b["y"] < a["y"] + a.get("h", 1))


def covers(area, item):
    return (area["z"] == item["z"] and area["x"] <= item["x"] and area["y"] <= item["y"]
            and area["x"] + area["w"] >= item["x"] + item.get("w", 1)
            and area["y"] + area["h"] >= item["y"] + item.get("h", 1))


CELL = 4                 # cell lattice pitch: a 3x3 room plus one shared wall
CELL_RING = 2            # cells at most 2 lattice steps from the hub: a 5x5 network, 24 bedrooms
CELL_BATCH = 4           # cells added per growth pass
WET_MATERIALS = tuple("kRoiMH")   # brook, river, pool, ice, magma, HFS; dry soil is diggable
WALKABLE = set(".<>X,o\"sw")   # map query shapes a dwarf can stand on (floor, stairs, boulder, pebbles, shrub...)
SENSE_EVERY = 3          # days between the layer's read-only query sweeps (jobs, buildings, stocks)
FINDINGS_KEEP = 8
HOSTILE_EVENTS = ("AMBUSH", "MEGABEAST", "WEREBEAST", "BEAST_AMBUSH", "SIEGE", "INVASION")
MIGRANT_EVENTS = ("MIGRANT_ARRIVAL", "D_MIGRANT")


class Overseer:
    def __init__(self, game, goal="", days=0):
        self.game = game
        self.surge = "migrant" in str(goal).lower()   # the task's own text says more dwarves are on the way
        self.days = days or 0
        self.tries, self.last = {}, {}
        self.roles = {}          # room id -> farm | dorm | dine | office
        self.full = {}           # site id -> time placement said no_space; skipped for FULL_DAYS (rooms may still be digging)
        self.brew_orders = set()
        self.now = 0
        self.alert_since = None
        self.hands_off = None
        self.days_left = None
        self.day = None
        self.owned = set()       # order ids this layer added: the model loop refuses to cancel them
        self.report = []         # the layer's recent actions (day, tool, args, outcome), for the model loop
        self.done = set()        # closer keys whose order was accepted once: never re-added
        self.events_tick = 0     # /events polled from here
        self.event_ids = set()
        self.sense_day = None    # day of the last query sweep
        self.findings = []       # what the sweep and the events found, for the model's STATUS
        self.migrants_at = None  # tick of the last migrant announcement
        self.hostile_at = None   # tick of the last hostile announcement
        self.locked = False      # this layer locked the fort's doors/hatches
        self.room_reservations = {}  # requested footprints, wider than later R site boxes
        self.net_rejected = set()    # R sites whose stair failed the hub check
        self.net = None          # cell network: hub stair, z, cells {(i, j): state}, doors {(x, y): state}
        self.cell_coordinates = False  # fail closed until configured from /task
        self.cell_api_warned = False

    def configure_tools(self, tools):
        """Cubicles need exact boxes; site-only schemas cannot express this lattice.

        Backend coordinate support is not enough: the HTTP schema requires `site`
        before the facts resolver runs. Fail closed on missing/unknown schemas.
        """
        schemas = {d(t.get("function")).get("name"): d(d(t.get("function")).get("parameters"))
                   for t in lst(tools) if isinstance(t, dict)}
        required = {"dig_room": {"x", "y", "z", "w", "h"},
                    "place_furniture": {"x", "y", "z", "w", "h"},
                    "make_zone": {"x", "y", "z", "w", "h"},
                    "build_door": {"x", "y", "z"}}
        self.cell_coordinates = all(name in schemas and "site" not in lst(schemas[name].get("required"))
                                    and fields <= set(d(schemas[name].get("properties")))
                                    for name, fields in required.items())

    # ---- the action gate
    def may(self, key, retry=2, limit=6):
        return self.tries.get(key, 0) < limit and self.now - self.last.get(key, -10 ** 9) >= retry * DAY

    def act(self, key, tool, args, retry=2, limit=6):
        """One rate-limited action. Returns the response if it ran, else None."""
        if key in self.done or not self.may(key, retry, limit):
            return None
        # Site-only zoning covers the whole advertised box. Do not swallow a
        # farm or an office (nor create an office over a shared living zone).
        if tool == "make_zone" and args.get("site"):
            site = next((s for s in self.sites if s.get("id") == args["site"]), None)
            if site:
                protected = lst(self.o.get("farm_plots")) + [z for z in self.zones
                    if "office" in str(z.get("type")).lower() or args.get("kind") == "office"]
                if any(overlaps(site, area) for area in protected):
                    return None
        self.tries[key] = self.tries.get(key, 0) + 1
        self.last[key] = self.now
        r = self.game.act(tool, args)
        self.count += 1
        log("act", key=key, tool=tool, args=args, ok=r.get("ok"), code=r.get("error_code"),
            err=str(r.get("error") or "")[:160])
        if r.get("ok"):
            # Keep accepted zone receipts visible to later steps in this pass.
            # load() replaces this cache with fresh facts at the next observation.
            if tool == "make_zone":
                result = d(r.get("result"))
                at = result.get("at")
                if isinstance(at, list) and len(at) == 5 and all(type(v) is int for v in at):
                    x, y, z, w, h = at
                    zone = {"id": result.get("zone_id"), "type": result.get("zone") or args.get("kind"),
                            "x": x, "y": y, "z": z, "w": w, "h": h}
                    self.zones.append(zone)
                else:
                    # Older responses may omit `at`; the public request/site
                    # still supplies a conservative reservation rectangle.
                    box = (next((v for v in self.sites if v.get("id") == args.get("site")), None)
                           if args.get("site") else args)
                    if box and all(type(box.get(k)) is int for k in ("x", "y", "z", "w", "h")):
                        self.zones.append({**{k: box[k] for k in ("x", "y", "z", "w", "h")},
                                           "id": result.get("zone_id"), "type": args.get("kind")})
            self.tries[key] = max(0, self.tries[key] - 1)
            if tool == "add_order" and args.get("recipe") == "brew_drink" and args.get("repeat") == "daily":
                order_id = d(r.get("result")).get("order_id")
                if type(order_id) is int:
                    self.brew_orders.add(order_id)
        if r.get("ok") and tool in ("add_order", "add_manager_order"):
            res = r.get("result") if isinstance(r.get("result"), dict) else r
            if res.get("order_id") is not None:
                self.owned.add(res.get("order_id"))
            if args.get("repeat") and key.startswith("o_") and key.endswith(("_end", "_win", "_prog")):
                self.done.add(key)   # a standing closer or progression order is added once per game
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
            self.brew_orders.intersection_update(x.get("id") for x in self.orders)
            self.owned.intersection_update(x.get("id") for x in self.orders)   # a removed order is nobody's
        self.zones = [z for z in lst(self.o.get("zones")) if isinstance(z, dict)]
        self.free = d(self.st.get("furniture_free"))
        self.placed = {}
        for f in lst(self.o.get("furniture")):
            if isinstance(f, dict):
                self.placed[f.get("kind")] = self.placed.get(f.get("kind"), 0) + 1
        self.surface = self.map.get("surface_z")

    def kind(self, k):
        return [s for s in self.sites if s.get("kind") == k]

    def pending(self, recipe):
        return any(x.get("recipe") == recipe and (x.get("left") or 0) > 0 for x in self.orders)

    def brewing_pending(self):
        """An idle, validated repeat is not emergency brewing in progress.

        DF retains positive `left` on conditional repeats even while their
        conditions block them. Keep unvalidated/new and one-shot orders pending
        so manager latency cannot spawn duplicate emergency orders.
        """
        return any(x.get("recipe") == "brew_drink" and (
            (x.get("jobs_in_progress") or 0) > 0 or
            ((x.get("left") or 0) > 0 and not (
                x.get("repeat") and x.get("validated") is True and x.get("active") is False))
        ) for x in self.orders)

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
    def q(self, name, **params):
        """A read-only query; None when the game client has none or it fails (never an action, never time)."""
        fn = getattr(self.game, "query", None)
        if fn is None:
            return None
        try:
            r = fn(name, **params)
        except Exception as e:
            log("query_error", query=name, error=repr(e)[:160])
            return None
        r = r.get("result", r) if isinstance(r, dict) else None
        return r if isinstance(r, dict) and r.get("ok") is not False else None

    def find(self, text):
        if text not in [f for _, f in self.findings]:
            self.findings = (self.findings + [(self.day, text)])[-FINDINGS_KEEP:]

    def events(self):
        """DF's reports since the last pass: migrants re-open housing at once, hostile reports arm the hatches,
        deaths and cancellation reasons become findings."""
        fn = getattr(self.game, "events", None)
        if fn is None:
            return
        try:
            r = fn(since_tick=self.events_tick)
        except Exception as e:
            log("events_error", error=repr(e)[:160])
            return
        cancels = {}
        for e in lst(d(r).get("events")):
            e = d(e)
            if e.get("id") in self.event_ids:
                continue
            self.event_ids.add(e.get("id"))
            if isinstance(e.get("tick"), int):
                self.events_tick = max(self.events_tick, e["tick"])
            t, text = str(e.get("type") or ""), str(e.get("text") or "")
            if t.startswith(MIGRANT_EVENTS):
                self.migrants_at = self.now
                for k in [k for k in self.last if k.startswith(("o_make_bed", "o_make_table", "o_make_chair", "bed",
                                                                 "place", "dorm"))]:
                    self.last.pop(k, None)   # housing keys run again this pass, not after their retry delay
                self.find(f"migrants arrived: {text[:80]}")
            elif any(h in t for h in HOSTILE_EVENTS):
                self.hostile_at = self.now
                self.find(f"hostile report {t}: {text[:80]}")
            elif t == "CITIZEN_DEATH":
                self.find(f"death: {text[:100]}")
            elif not e.get("announcement") and " cancels " in text and ":" in text:
                why = text.split(":", 1)[1].strip()[:60]
                cancels[why] = cancels.get(why, 0) + 1
        for why, n in sorted(cancels.items(), key=lambda x: -x[1])[:3]:
            if n >= 2:
                self.find(f"{n} jobs cancelled: {why}")
            if "barrel" in why.lower() and self.logs() and not self.pending("make_barrel"):
                self.act("o_barrel_ev", "add_order", {"recipe": "make_barrel", "amount": 3}, retry=3, limit=20)

    def sweep(self):
        """Every SENSE_EVERY days: jobs (suspended, unworked), buildings (placed but unbuilt), stocks (rotten,
        forbidden). Findings for the model; nothing here acts."""
        if isinstance(self.day, int) and self.sense_day is not None and self.day - self.sense_day < SENSE_EVERY:
            return
        self.sense_day = self.day
        jobs = self.q("jobs", limit=500)
        if jobs:
            rows = [d(j) for j in lst(jobs.get("jobs"))]
            susp = {}
            for j in rows:
                if j.get("suspended"):
                    susp[str(j.get("job"))] = susp.get(str(j.get("job")), 0) + 1
            if susp:
                self.find("suspended jobs: " + ", ".join(f"{k} x{v}" for k, v in sorted(susp.items(), key=lambda x: -x[1])[:5]))
            idle = sum(1 for j in rows if j.get("worker_id") in (None, -1) and not j.get("suspended"))
            if rows and idle >= max(8, len(rows) // 2):
                self.find(f"{idle} of {len(rows)} jobs have no worker (labor or hauling short)")
        bld = self.q("buildings", limit=1000)
        if bld:
            unbuilt = {}
            for b in lst(bld.get("buildings")):
                b = d(b)
                if b.get("built") is False:
                    unbuilt[str(b.get("type"))] = unbuilt.get(str(b.get("type")), 0) + 1
            if sum(unbuilt.values()) >= 3:
                self.find("placed but not built: " + ", ".join(f"{k} x{v}" for k, v in sorted(unbuilt.items(), key=lambda x: -x[1])[:5]))
        st = self.q("stocks", limit=1000)
        if st:
            rot = sum(int(d(g).get("rotten") or 0) for g in lst(st.get("groups")))
            forb = sum(int(d(g).get("forbidden") or 0) for g in lst(st.get("groups")))
            if rot >= 5:
                self.find(f"{rot} rotten items in stock (spoiled food or corpses)")
            if forb >= 10:
                self.find(f"{forb} forbidden items (dwarves won't use or haul them)")

    def plan(self):
        try:
            self.events()
            self.sweep()
        except (ActionLimit, HandsOff, GameOver):
            raise
        except Exception as e:   # the senses are advisory
            log("sense_error", error=repr(e)[:200])
        self.mood()
        self.defend()
        self.management()
        self.workshops()
        self.digging()
        self.farms()
        self.supply()
        self.cubicles()
        self.furnish()
        self.rezone()
        self.progress()
        self.stonework()
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
        # operator rule: manager + office first so delegation is automated, then roles are assigned (autolabor is the
        # API's only labor-assignment tool)
        if self.adm.get("manager_active_for_orders") and plugins.get("autolabor") != "on":
            self.act("plug_autolabor", "enable_automation", {"name": "autolabor"}, retry=5)

    def office_reuse(self, mgr, offices):
        """Recover with observed built chairs, without stealing another zone's seats."""
        chaired = lambda z: (d(z.get("furniture")).get("chair") or 0) > 0
        # The public manager_office summary reports only the first owned office.
        # A second chaired office works in DF even while that summary stays false.
        if any(z.get("owner") == mgr and chaired(z) for z in offices):
            return True
        spare = next((z for z in offices if z.get("owner") is None and chaired(z)), None)
        if spare:
            self.act(f"office_assign_{spare['id']}", "assign_zone", {"zone_id": spare["id"], "dwarf_id": mgr})
            return True

        def box(b):
            return (all(isinstance(b.get(k), int) for k in ("x", "y", "z", "w", "h"))
                    and b["w"] > 0 and b["h"] > 0)

        def overlaps(a, b):
            return (box(b) and a["z"] == b["z"]
                    and a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"]
                    and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"])

        chairs = [f for f in lst(self.o.get("furniture")) if isinstance(f, dict) and f.get("kind") == "chair"
                  and f.get("built") is True and not f.get("zone_ids")
                  and all(isinstance(f.get(k), int) for k in ("x", "y", "z"))]
        candidates = [s for s in self.sites if s.get("kind") in ("A", "R") and s.get("free") is True
                      and (s.get("kind") == "A" or s.get("dug") is True) and box(s)
                      and any(s["z"] == f["z"] and s["x"] <= f["x"] < s["x"] + s["w"]
                              and s["y"] <= f["y"] < s["y"] + s["h"] for f in chairs)
                      and not any(overlaps(s, b) for b in self.zones + [f for f in lst(self.o.get("farms")) if isinstance(f, dict)])]
        if candidates:
            room = min(candidates, key=lambda s: s["w"] * s["h"])
            self.act(f"office_reuse_{room['id']}", "make_zone", {"kind": "office", "site": room["id"]})
            return True  # Reobserve zone furniture before assigning on the next pass.
        return False

    def office(self):
        """Operator rule: the manager's office (zone + chair) is built as soon as a manager exists, not at ~14 citizens.
        DF stops validating orders around 20 citizens unless the manager has an office with a chair."""
        if not self.adm.get("manager_active_for_orders"):
            return
        mo = self.adm.get("manager_office")
        if isinstance(mo, dict) and mo.get("chair"):
            return
        mgr = self.adm.get("MANAGER_id")
        offices = self.zone("office")
        if mgr is None:
            return
        if self.office_reuse(mgr, offices):
            return
        mine = next((z for z in offices if mgr is not None and z.get("owner") == mgr), None)
        if not mine:
            spare = next((z for z in offices if z.get("owner") is None), None)
            if spare and mgr is not None:
                self.act(f"office_assign_{spare['id']}", "assign_zone", {"zone_id": spare["id"], "dwarf_id": mgr})
                return
            room = next(iter(self.dug_rooms("office") + self.dug_rooms("dine") + self.kind("A")), None)
            if room:
                result = self.act("office_zone", "make_zone", {"kind": "office", "site": room["id"]})
                if result and result.get("ok") and (self.free.get("chair") or 0) > 0:
                    self.act("office_chair", "place_furniture", {"kind": "chair", "site": room["id"]})
            return
        if d(mine.get("furniture")).get("chair") or d(mine.get("furniture_planned")).get("chair"):
            return
        if (self.free.get("chair") or 0) > 0:
            room = next((s for s in self.sites if s.get("kind") in "RA" and s.get("z") == mine.get("z")
                         and s.get("x") == mine.get("x") and s.get("y") == mine.get("y")), None)
            # Placement scans the entire site's box, so the box must fit in this
            # office; a matching top-left or unrelated fallback is not sufficient.
            if room and all(isinstance(b.get(k), int) for b in (room, mine) for k in ("w", "h")):
                if room["w"] > mine["w"] or room["h"] > mine["h"]:
                    return
                self.act(f"office_chair_{mine['id']}_{room['id']}", "place_furniture", {"kind": "chair", "site": room["id"]})

    def build(self, wtype, retry=3):
        sites = self.kind("W")
        if not sites or not self.material():
            return
        result = self.act("ws_" + wtype, "build_workshop", {"type": wtype, "site": sites[0]["id"]}, retry=retry)
        if result and result.get("ok"):
            self.sites.remove(sites[0])

    def workshops(self):
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        for t in ("Carpenters", "Still", "Kitchen"):
            if t not in have:
                self.build(t)
        if "Fishery" not in have and any(p.get("job") == "Fish" for p in self.people):
            self.build("Fishery")
        if (self.surge and self.adm.get("manager_active_for_orders") and self.cit >= 15 and self.logs() >= 5
                and sum(w.get("type") == "Carpenters" for w in lst(self.o.get("workshops")) if isinstance(w, dict)) == 1):
            self.build("Carpenters", retry=3)

    def bed_target(self):
        """Beds per citizen is read at the horizon; a migrant task's wave is bigger than the fort's bed stock."""
        return self.cit + (12 if self.surge else 3)

    def farm_target(self):
        """Operator: farm heavily on full-year forts (food + plump helmet drink). Short lab tasks keep the old count:
        on LT08 the extra plots took rooms and labour from the migrant wave's beds (iteration 22)."""
        if self.days >= 200 and not self.surge:
            return max(6, min(14, math.ceil(self.cit / 3)))
        return max(4, min(10, math.ceil(self.cit / 5)))

    def digging(self):
        rooms = self.kind("R")
        pending = self.o.get("dig_designations_pending") or 0
        stairs = self.kind("S")
        if stairs and self.surface is not None and (len(rooms) < 2 or (not any(r.get("soil") for r in rooms)
                                                                       and not self.o.get("farm_plots"))):
            self.act("stairs", "dig_stairs", {"site": stairs[-1]["id"], "z_bottom": self.surface - 4}, retry=12, limit=3)
        if pending > 90:
            return
        farms = len(lst(self.o.get("farm_plots"))) + sum(1 for r, v in self.roles.items() if v == "farm" and not any(z.get("id") == r and z.get("used_by") for z in self.kind("R")))
        for r in self.undug_rooms():
            rid = r["id"]
            if rid in self.roles:
                continue
            need = [x for x in ("office", "dorm", "dine") if x not in self.roles.values()]   # operator: office asap
            # A missing dining role must not starve replacement housing. Keep the
            # office first, but a full dorm and bed deficit outrank dining.
            if (not need or need[0] == "dine") and self.cit + 2 > (self.placed.get("bed") or 0) and not any(
                    v == "dorm" and not self.is_full(k) for k, v in self.roles.items()):
                need = ["dorm"]   # every dorm is full and beds are short: dig another
            # Farms can block the shared placement prefix. A disjoint replacement
            # dorm, however, may be the only housing site after this dorm fills.
            reserved_level = any(area.get("z") == r.get("z") and self.roles.get(key) == "dorm"
                                 for key, area in self.room_reservations.items())
            if reserved_level and not (need and need[0] == "dorm"):
                continue
            if need and need[0] == "dine" and not self.tavern_level(r):
                need = []   # operator rule: the tavern (dining hall) goes on the first level down, nowhere else
            # Count committed rooms, not just built plots: excavation can reserve
            # every offered site before the first new farm finishes. Leave a
            # clear expandable room while the initial farms finish.
            proposed_dorm = {**r, **self.dorm_size()}
            protected_rooms = [s for s in rooms if self.roles.get(s["id"]) in ("farm", "office")]
            protected_rooms += lst(self.o.get("farm_plots")) + list(self.room_reservations.values())
            dorm_clear = not any(overlaps(proposed_dorm, s) for s in protected_rooms
                                 if all(k in s for k in ("x", "y", "z")))
            # Reserve a clear expansion before the adjacent room becomes a farm.
            # Additional farm rooms still follow; do not excavate living space
            # through a plot or a previously committed room.
            if reserved_level and not dorm_clear:
                continue
            housing_room = bool(need and need[0] == "dorm" and farms >= 3 and dorm_clear)
            if r.get("soil") and farms < self.farm_target() and (not need or need[0] != "office") and not housing_room:
                result = self.act("dig_" + rid, "dig_room", {"site": rid}, retry=3, limit=2)
                if result and result.get("ok"):
                    self.roles[rid] = "farm"
                    farms += 1
            elif need:
                role = need[0]
                if role == "dorm" and not dorm_clear:
                    continue
                size = {"dorm": self.dorm_size(), "dine": {"w": 7, "h": 5}, "office": {}}[role]
                result = self.act("dig_" + rid, "dig_room", {"site": rid, **size}, retry=3, limit=2)
                if result and result.get("ok"):
                    self.roles[rid] = role
                    self.room_reservations[rid] = {**r, **size}

    def dorm_size(self):
        """A dorm with one tile per anticipated bed still needed, 3x3 at least.
        Replaces a fixed 9x7 dig: smaller digs finish sooner and open less wet rock; a full dorm digs the next one."""
        target = self.bed_target()
        if self.days >= 200 and not self.surge:
            # A start-year fort has very few room sites: size for the year's
            # migrants before the last disjoint excavation site is spent.
            target = max(target, 30)
        n = max(9, target - (self.placed.get("bed") or 0))
        w = min(MAX_DORM, max(3, math.ceil(math.sqrt(n))))
        return {"w": w, "h": min(MAX_DORM, max(3, math.ceil(n / w)))}

    def tavern_level(self, r):
        """True when room r is on the first level below the surface, or no such room is offered at all."""
        if self.surface is None:
            return True
        top = self.surface - 1
        if r.get("z") == top:
            return True
        return not any(x.get("z") == top for x in self.undug_rooms() if x["id"] not in self.roles)

    def farms(self):
        plots = lst(self.o.get("farm_plots"))
        target = self.farm_target()
        if len(plots) >= target:
            return
        cands = self.kind("F") + [r for r in self.dug_rooms() if r.get("soil") and self.roles.get(r["id"], "farm") == "farm"]
        reserved = list(self.room_reservations.values()) + self.zone("office") + self.zone("dorm") + self.zone("bedroom") + self.zone("dining")
        cands = [s for s in cands if not any(overlaps(s, area) for area in reserved)]
        seeds = d(self.st.get("seeds_by_kind"))
        if any(not d(v).get("underground") for v in seeds.values()):
            cands += self.kind("G")[:2]
        for s in cands[:target - len(plots)]:
            self.act("farm_" + s["id"], "build_farm", {"site": s["id"]}, retry=4, limit=3)

    def supply(self):
        """Standing orders that keep working in a hands-off window, then one-shot furniture sized to the population."""
        if not self.standing("brew_drink"):
            self.act("o_brew", "add_order", {"recipe": "brew_drink", "amount": 3, "repeat": "daily", "when": [
                {"stock": "drink", "below": DRINK_CAP}, {"stock": "plants_brewable", "at_least": 2},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=3)
        if not self.standing("make_barrel"):
            self.act("o_barrel", "add_order", {"recipe": "make_barrel", "amount": 2, "repeat": "daily", "when": [
                {"stock": "barrels_empty", "below": 4}, {"stock": "logs", "at_least": 2}]}, retry=3)
        if not self.standing("cook_meal"):
            self.act("o_cook", "add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily", "when": [
                {"stock": "prepared_meals", "below": MEAL_CAP}, {"stock": "food", "at_least": 4}]}, retry=3)
        self.floors()
        plants = d(self.st.get("plants_by_kind"))
        if (self.st.get("drink") or 0) < 3 * self.cit and not self.st.get("plants_brewable") and plants \
                and not self.pending("brew_drink_from_fruit"):
            self.act("o_fruit", "add_order", {"recipe": "brew_drink_from_fruit", "amount": 3}, retry=4)
        seats = math.ceil(self.cit / 2) + 2
        for recipe, have, want in (("make_bed", self.st.get("beds") or 0, self.bed_target()),
                                   ("make_table", self.st.get("tables") or 0, seats),
                                   ("make_chair", self.st.get("chairs") or 0, seats + 1)):
            if (self.surge and recipe != "make_bed" and self.housing_short()
                    and (self.st.get("beds") or 0) < self.bed_target()):
                continue  # carpenter throughput belongs to beds before migrant hands-off
            if have < want and not self.pending(recipe) and self.logs():
                batch = 30 if self.surge and recipe == "make_bed" else 8
                self.act("o_" + recipe, "add_order", {"recipe": recipe, "amount": min(batch, want - have)}, retry=1, limit=99)

    def floors(self):
        """Operator rule: never run out. Below 10 prepared meals cook a batch now; drink below its floor brews now."""
        meals = self.st.get("prepared_meals") or 0
        if meals < MEAL_FLOOR and (self.st.get("food_edible") or 0) >= 2 and not self.pending("cook_meal"):
            self.act("o_cook_floor", "add_order", {"recipe": "cook_meal", "amount": min(15, MEAL_FLOOR + 5 - meals)},
                     retry=1, limit=99)
        if (self.st.get("drink") or 0) < max(DRINK_FLOOR, 2 * self.cit) and self.st.get("plants_brewable") \
                and not self.brewing_pending():
            self.act("o_brew_floor", "add_order", {"recipe": "brew_drink", "amount": 5}, retry=1, limit=99)

    def stonework(self):
        """Operator rule: miners' stone goes to masons: statues and stone crafts (never wood for anything traded)."""
        if (self.st.get("boulders_usable") or 0) < STONE_MIN:
            return
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        if "Masons" not in have:
            self.build("Masons", retry=4)
            return
        if not any(x.get("job") == "ConstructStatue" and x.get("repeat") for x in self.orders):
            self.act("o_statue_prog", "add_manager_order", {"job": "ConstructStatue", "amount": 1, "repeat": "daily",
                     "material": "INORGANIC", "when": [{"item_type": "BOULDER", "at_least": STONE_MIN}]},
                     retry=5, limit=4)
        if "Craftsdwarfs" in have:   # "_prog" key: added once per game (observed orders don't report material)
            self.act("o_stonecraft_prog", "add_manager_order", {"job": "MakeCrafts", "amount": 2, "repeat": "daily",
                     "material": "INORGANIC", "when": [{"item_type": "BOULDER", "at_least": STONE_MIN}]},
                     retry=5, limit=4)

    # ---- the closer: what the score reads at the end of the run
    def in_endgame(self):
        """Open-play tasks: the scored final stretch (the last quarter of the run, 7-28 days) is near."""
        return self.hands_off is None and self.days_left is not None and self.days_left <= ENDGAME_DAYS

    def in_window_prep(self):
        """Lab tasks: the hands-off window starts soon; after it begins only standing orders keep working."""
        return isinstance(self.hands_off, int) and 0 < self.hands_off <= WINDOW_PREP_DAYS

    def closer(self):
        if self.in_endgame():
            self.endgame_supply()
            self.housing_check()
        elif self.in_window_prep():
            self.window_supply()
            self.housing_check()
        if self.surge:
            carp = sum(1 for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Carpenters")
            if carp == 1 and self.cit >= 15 and self.logs() >= 5:
                self.build("Carpenters", retry=3)   # one shop can't make a wave's beds before the window

    def endgame_supply(self):
        """The supply sub-score credits a stock by its projected days left: a draining stock is credited only as far
        as it lasts, and a flat or rising one in full. From ENDGAME_DAYS before the horizon, a second brew order with a
        cap well above the usual one keeps drink rising through the final stretch (while plants stay above a reserve
        that protects the food count, since plants are food too), and cooking keeps meals rising from surplus food.
        Meat is added when edible food is short of a few days per citizen."""
        cap = max(600, 30 * self.cit)
        reserve = max(12, self.cit)
        self.act("o_brew_end", "add_order", {"recipe": "brew_drink", "amount": 4, "repeat": "daily", "when": [
            {"stock": "drink", "below": cap}, {"stock": "plants_brewable", "at_least": reserve},
            {"stock": "barrels_empty", "at_least": 1}]}, retry=3, limit=4)
        self.act("o_barrel_end", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 8}, {"stock": "logs", "at_least": 4}]}, retry=3, limit=4)
        self.act("o_cook_end", "add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily", "when": [
            {"stock": "prepared_meals", "below": max(300, 10 * self.cit)},
            {"stock": "food_edible", "at_least": max(30, 4 * self.cit)}]}, retry=3, limit=4)
        if (self.st.get("food_edible") or 0) < 4 * self.cit:
            self.butcher()
        if self.days_left <= 10:
            self.finish_food()

    def finish_food(self):
        """Open-play food tail: bounded late cull and cook raw food before it rots.

        Adapted from the measured zero-model branch's feast/cull, without replacing
        this operator-rule layer or changing hands-off task preparation.
        """
        if "Butchers" not in {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}:
            self.build("Butchers")
        q = self.game.query("units", kind="animals")
        herd = [d(a) for a in lst(d(d(q).get("result")).get("units") or d(d(q).get("result")).get("animals"))]
        herd = [a for a in herd if a.get("tame") and a.get("pet_owner_id") in (None, -1)
                and not a.get("marked_for_slaughter") and a.get("id") is not None]
        marked = 0
        for animal in sorted(herd, key=lambda a: str(a["id"])):
            if marked >= 3:
                break
            r = self.act("food_tail_%s" % animal["id"], "slaughter", {"unit_id": animal["id"]}, retry=1, limit=2)
            marked += bool(r and r.get("ok"))
        raw = ((self.st.get("food_edible") or 0) - (self.st.get("prepared_meals") or 0)
               - (self.st.get("plants_total") or 0))
        if raw >= 10 and not self.pending("cook_meal"):
            self.act("o_cook_tail", "add_order", {"recipe": "cook_meal", "amount": int(min(6, max(2, raw // 10)))},
                     retry=1, limit=99)

    def window_supply(self):
        """Before a hands-off window: brew whenever a plant and a barrel allow, at a cap the window can't reach, so
        drink keeps rising while nobody can act (LT08 wants drink at the end above drink at the window's start;
        LT01 wants a batch brewed inside it). Plants are food too, and food must also hold through the window, so
        keep two brewable plants as the input floor rather than a population-scaled
        reserve that can exceed the entire harvest. Barrels get a parallel order."""
        self.act("o_brew_win", "add_order", {"recipe": "brew_drink", "amount": 5, "repeat": "daily", "when": [
            {"stock": "drink", "below": 2000}, {"stock": "plants_brewable", "at_least": 2},
            {"stock": "barrels_empty", "at_least": 1}]}, retry=2, limit=5)
        self.act("o_barrel_win", "add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 10}, {"stock": "logs", "at_least": 3}]}, retry=2, limit=5)
        if (self.st.get("food_edible") or 0) < 4 * self.cit:
            self.butcher()

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
        if self.surge and beds_short > 0:
            return   # a migrant task is scored on beds, not seats: the carpenters' queue stays with the beds
        seats_short = math.ceil(self.cit / 2) - self.seats()
        if seats_short > 0 and self.logs() >= 2:
            for recipe, have in (("make_table", self.st.get("tables") or 0), ("make_chair", self.st.get("chairs") or 0)):
                want = math.ceil(self.cit / 2) + 1
                if self.surge and self.housing_short() and (self.st.get("beds") or 0) < self.bed_target():
                    continue
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
        """Only furniture inside a zone counts or gets used. Zone each level's loose built tables, chairs and beds, and
        put a dining zone over a level whose tables and chairs sit in no dining zone (a dormitory's seats earn nothing)."""
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

    def progress(self):
        """Full-year games only. The growth gate on a 336-day horizon also needs a DF progression step, and the only
        one in reach is the Hamlet rank: 20 citizens and 5000 created wealth. Citizens come with the year's migrant
        waves; wealth is made. Wood crafts are the cheapest wealth per log (several crafts from one log), so from
        PROGRESS_FROM_DAY a Craftsdwarfs is built and one standing order makes crafts whenever logs are above a
        reserve that keeps beds, barrels and seats first. It stops once the wealth is there."""
        if self.days < 336 or (self.day or 0) < PROGRESS_FROM_DAY or self.cit < 7:
            return
        if (d(self.o.get("wealth")).get("created") or 0) >= WEALTH_TARGET:
            return
        have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
        if "Craftsdwarfs" not in have:
            self.build("Craftsdwarfs", retry=5)
            return
        if not any(x.get("job") == "MakeCrafts" and x.get("repeat") for x in self.orders):
            self.act("o_crafts_prog", "add_manager_order", {"job": "MakeCrafts", "amount": 3, "repeat": "daily",
                     "material_category": ["wood"], "when": [{"item_type": "WOOD", "at_least": LOG_RESERVE}]},
                     retry=4, limit=6)

    def housing_short(self):
        return self.cit > (self.placed.get("bed") or 0)

    def is_full(self, sid):
        return self.now - self.full.get(sid, -1e18) < FULL_DAYS * DAY

    def safe_shared_capacity(self, site, kind="bed"):
        """Safe *prefix* of the server's row-major placement scan, never a tile wishlist.

        Site-only placement cannot skip an unoccupied protected tile. Stop there,
        rather than counting later dry floor that the server cannot target safely.
        This experimental fallback preserves farms, offices and non-bedroom zones.
        """
        if max(site.get("w", 0), site.get("h", 0)) > 41:
            return 0
        q = self.q("map", x=site["x"] + site["w"] // 2,
                   y=site["y"] + site["h"] // 2, z=site["z"],
                   radius=(max(site["w"], site["h"]) + 1) // 2)
        if not q:
            return 0
        level = next((v for v in lst(q.get("levels")) if v.get("z") == site["z"]), None)
        if not level:
            return 0
        buildings = lst(q.get("buildings"))
        if len(buildings) >= 300 or len(lst(q.get("liquid"))) >= 500 or len(lst(q.get("designations"))) >= 500:
            return 0  # query lists may be truncated
        wet = {(v.get("x"), v.get("y"), v.get("z")) for v in lst(q.get("liquid"))}
        digs = {(v.get("x"), v.get("y"), v.get("z")) for v in lst(q.get("designations"))}
        protected = lst(self.o.get("farm_plots")) + self.zone("office")
        protected += [r for r in self.kind("R") if self.roles.get(r["id"], "").startswith("farm")
                      or self.roles.get(r["id"]) in ("office", "dine")]
        count = 0
        for y in range(site["y"], site["y"] + site["h"]):
            for x in range(site["x"], site["x"] + site["w"]):
                dx, dy = x - q.get("x1", x + 1), y - q.get("y1", y + 1)
                try:
                    if min(dx, dy) < 0:
                        return 0
                    shape, light = level["shape"][dy][dx], level["light"][dy][dx]
                except (KeyError, IndexError, TypeError):
                    return 0
                if shape not in '.o"sw,' or light not in (("u", "i") if kind == "bed" else ("u", "i", "o")):
                    continue
                point = {"x": x, "y": y, "z": site["z"]}
                occupied = any(b.get("z") == site["z"] and b.get("x1", x+1) <= x <= b.get("x2", x-1)
                               and b.get("y1", y+1) <= y <= b.get("y2", y-1) for b in buildings)
                if occupied or (x, y, site["z"]) in digs:
                    continue
                # Even shallow liquid is excluded; it can be a server-selected tile.
                if (x, y, site["z"]) in wet or any(covers(area, point) for area in protected):
                    return count
                count += 1
        return count

    def room_for(self, role):
        """The dug level of a role's big room (its A site covers the whole dig), else the room itself.
        Sites that last answered no_space are skipped: a full dorm otherwise ate every bed attempt (iteration 22)."""
        rooms = [r for r in self.kind("R") if self.roles.get(r["id"]) == role and not self.is_full(r["id"])]
        for r in rooms:
            a = next((s for s in self.kind("A") if s.get("z") == r.get("z")), None)
            if a and role != "farm" and not self.is_full(a["id"]) and (r.get("dug") or a.get("open_tiles", 0) >= 6):
                return a
        dug = [r for r in rooms if r.get("dug")]
        if dug:
            return dug[0]
        taken = {r.get("z") for r in self.kind("R") if self.roles.get(r["id"], "").startswith("farm")}
        return next((s for s in self.kind("A") if (s.get("z") not in taken or role == "dorm") and not self.is_full(s["id"])
                     and s.get("open_tiles", 0) >= 6 and (s.get("z") not in taken or self.safe_shared_capacity(s) >= 1)), None)

    def needs_zone(self, room, zones, kinds, placed=()):
        if any(covers(z, room) for z in zones):
            return False
        return any(f.get("kind") in kinds and covers(room, f)
                   and not any(covers(z, f) for z in zones)
                   for f in lst(self.o.get("furniture")) + list(placed))

    def place(self, key, kind, room, count):
        protected = lst(self.o.get("farm_plots")) + self.zone("office")
        protected += [r for r in self.kind("R") if self.roles.get(r["id"], "").startswith("farm")
                      or self.roles.get(r["id"]) == "office"]
        if room.get("kind") == "A" and any(overlaps(room, p) for p in protected):
            count = min(count, self.safe_shared_capacity(room, kind))
            if count <= 0:
                return []
        result = d(self.act(key, "place_furniture", {"kind": kind, "site": room["id"], "count": count},
                            retry=1, limit=99))
        if not result.get("ok"):
            if result.get("error_code") == "no_space":
                self.full[room["id"]] = self.now
            return []
        points = d(result.get("result")).get("at") or []
        if points and not isinstance(points[0], list):
            points = [points]
        return [{"kind": kind, "x": x, "y": y, "z": z} for x, y, z in points]

    def furnish(self):
        dorm, dine = self.room_for("dorm"), self.room_for("dine") or self.room_for("dorm")
        if dorm:
            short = self.cit + 2 - (self.placed.get("bed") or 0)
            n = min(self.free.get("bed") or 0, short, 30)
            placed = self.place("beds", "bed", dorm, n) if n > 0 else []
            if self.needs_zone(dorm, self.zone("dorm") + self.zone("bedroom"), ("bed",), placed):
                self.act("z_dorm", "make_zone", {"kind": "dormitory", "site": dorm["id"]}, retry=3)
        # A generic dining fallback can fill a newly dug dorm with tables and
        # chairs before more beds finish production. Preserve housing capacity.
        housing_reserved = dine and any(overlaps(dine, area) for rid, area in self.room_reservations.items()
                                       if self.roles.get(rid) == "dorm")
        # A temporary surplus of beds is not spare floor capacity: migrants
        # will need it later. Never release a reserved dorm to dining furniture.
        if dine and not housing_reserved:
            want = math.ceil(self.cit / 2) + 1
            placed = []
            for kind in ("table", "chair"):
                n = min(self.free.get(kind) or 0, want - (self.placed.get(kind) or 0), 15)
                if n > 0:
                    placed += self.place("f_" + kind, kind, dine, n)
            if self.needs_zone(dine, self.zone("dining"), ("table", "chair"), placed):
                self.act("z_dine", "make_zone", {"kind": "dining_hall", "site": dine["id"]}, retry=3)

    # ---- cell network (operator: 3x3 bedrooms, bed in the middle, a door in every wall, a growing network)
    @staticmethod
    def cell_centre(hub, c):
        return hub[0] + CELL * c[0], hub[1] + CELL * c[1]

    @staticmethod
    def cell_tiles(hub, c):
        cx, cy = Overseer.cell_centre(hub, c)
        return [(cx + a, cy + b) for b in (-1, 0, 1) for a in (-1, 0, 1)]

    @staticmethod
    def door_tile(hub, a, b):
        """The one-tile doorway in the middle of the wall shared by 4-adjacent cells a and b."""
        return hub[0] + 2 * (a[0] + b[0]), hub[1] + 2 * (a[1] + b[1])

    @staticmethod
    def cell_fits(new, net, stair, z, m):
        """New tiles fit the map query m: each is wall or hidden (dry soil is fine), not designated by anyone,
        and every tile around them that is outside the network is not walkable (sealed; the stair is the way in).
        No liquid on z-1..z+1 anywhere in the box."""
        m = d(m)
        lv = next((l for l in lst(m.get("levels")) if d(l).get("z") == z), None)
        if not lv or any(abs(d(q).get("z", -99) - z) <= 1 for q in lst(m.get("liquid"))):
            return False
        x1, y1 = m.get("x1"), m.get("y1")
        shape, mat = lst(lv.get("shape")), lst(lv.get("material"))
        marked = {(d(q).get("x"), d(q).get("y")) for q in lst(m.get("designations")) if d(q).get("z") == z}

        def ch(rows, x, y):
            j, i = y - y1, x - x1
            return rows[j][i] if 0 <= j < len(rows) and 0 <= i < len(rows[j]) else None
        inside = set(net) | set(new) | {stair}
        for x, y in new:
            if ch(shape, x, y) not in ("#", "?") or ch(mat, x, y) in WET_MATERIALS or (x, y) in marked:
                return False
            for ax in (-1, 0, 1):
                for ay in (-1, 0, 1):
                    n = (x + ax, y + ay)
                    if n in inside:
                        continue
                    sh = ch(shape, *n)
                    if sh not in ("#", "?") or ch(mat, *n) in WET_MATERIALS or n in marked:
                        return False
        return True

    def net_tiles(self):
        n = self.net
        return [t for c in n["cells"] for t in self.cell_tiles(n["hub"], c)] + list(n["doors"])

    def net_map(self):
        n = self.net
        return self.q("map", x=n["hub"][0], y=n["hub"][1], z=n["z"] + 1, z2=n["z"] - 1, radius=CELL * CELL_RING + 3)

    def net_start(self):
        used_z = {r.get("z") for r in self.kind("R") if r["id"] in self.roles}
        for r in self.undug_rooms():
            st = d(r.get("stair"))
            if r["id"] in self.roles or r["id"] in self.net_rejected or not isinstance(st.get("x"), int):
                continue
            if r.get("z") in used_z or (self.surface is not None and r.get("z") == self.surface - 1):
                continue   # a level of its own; the first level down is the tavern's
            hub, z = (st["x"], st["y"]), r["z"]
            self.net = {"hub": hub, "z": z, "site": r["id"], "cells": {}, "doors": {}, "bad": set()}
            m = self.net_map()
            # Unavailable or incomplete facts are not evidence of an unsafe site.
            # Require the hub and its one-tile boundary in both map layers before
            # cell_fits can turn a terrain verdict into a permanent rejection.
            lv = next((l for l in lst(d(m).get("levels")) if d(l).get("z") == z), None)
            x1, y1 = d(m).get("x1"), d(m).get("y1")
            complete = type(x1) is int and type(y1) is int
            for rows in (lst(d(lv).get("shape")), lst(d(lv).get("material"))):
                complete = complete and all(
                    0 <= y - y1 < len(rows) and isinstance(rows[y - y1], str)
                    and 0 <= hub[0] - 2 - x1 and hub[0] + 2 - x1 < len(rows[y - y1])
                    for y in range(hub[1] - 2, hub[1] + 3))
            if not complete or d(m).get("ok") is False:
                self.net = None
                continue
            if self.cell_fits([t for t in self.cell_tiles(hub, (0, 0)) if t != hub], [], hub, z, m):
                self.net["cells"][(0, 0)] = {}
                self.roles[r["id"]] = "cells"
                self.find(f"cell network started at stair {hub[0]},{hub[1]},{z}")
                return m
            self.net = None
            self.net_rejected.add(r["id"])
        return None

    def net_grow(self, m):
        """Add up to CELL_BATCH cells, nearest ring first, each 4-adjacent to the network, with a doorway in every
        wall it shares with a planned cell."""
        n, hub = self.net, self.net["hub"]
        added = 0
        ring = lambda c: (max(abs(c[0]), abs(c[1])), abs(c[0]) + abs(c[1]), c)
        for _ in range(CELL_BATCH):
            cand = sorted({(c[0] + a, c[1] + b) for c in n["cells"] for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1))}
                          - set(n["cells"]) - n["bad"], key=ring)
            cand = [c for c in cand if ring(c)[0] <= CELL_RING]
            placed = False
            for c in cand:
                nb = [(c[0] + a, c[1] + b) for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1))
                      if (c[0] + a, c[1] + b) in n["cells"]]
                doors = {self.door_tile(hub, c, x): (c, x) for x in nb}
                if self.cell_fits(self.cell_tiles(hub, c) + list(doors), self.net_tiles(), hub, n["z"], m):
                    n["cells"][c] = {}
                    for t, pair in doors.items():
                        n["doors"][t] = {"pair": pair}
                    added += 1
                    placed = True
                    break
                n["bad"].add(c)
            if not placed:
                break
        return added

    def dig_box(self, key, z, box):
        x, y, w, h = box
        r = self.act(key, "dig_room", {"x": x, "y": y, "z": z, "w": w, "h": h}, retry=3, limit=3)
        if r and r.get("ok"):
            self.done.add(key)   # designated once; a re-dig would only answer nothing_designated
        return r

    def cubicles(self):
        """Once office, dorm and dining hall are dug in: a network of 3x3 cells on a 4-tile lattice around a stair
        (the hub cell), grown ring by ring as housing runs short. Every wall two cells share has a one-tile doorway
        in its middle. Each dug cell gets its bed in the middle and a bedroom zone; each dug doorway its door."""
        if self.cell_coordinates is False:
            if not self.cell_api_warned:
                self.find("cubicles unavailable: /task requires site IDs; exact room/bed/door coordinates unsupported")
                self.cell_api_warned = True
            return
        if not all(x in self.roles.values() for x in ("office", "dorm", "dine")) or self.cit < 7:
            return
        m = None
        if self.net is None:
            if not self.may("net_start", 3, 10 ** 6):
                return
            # Read-only discovery is rate limited, not lifetime limited: early
            # passes can have no candidate or temporarily unavailable map facts.
            self.last["net_start"] = self.now
            m = self.net_start()
            if self.net is None:
                return
        n, hub, z = self.net, self.net["hub"], self.net["z"]
        # Completion is not permanent readiness: an already dug room can flood later.
        # Use a fresh read before any furnishing, including after every cell was dug.
        # A missing query must not reuse a stale dry-floor verdict.
        m = m or self.net_map()
        lv = next((l for l in lst(d(m).get("levels")) if d(l).get("z") == z), None) if m else None
        rows = lst(d(lv).get("shape"))
        wet = {(d(q).get("x"), d(q).get("y")) for q in lst(d(m).get("liquid"))
               if d(q).get("z") == z}

        def ready(x, y):
            if not lv or (x, y) in wet:
                return False
            j, i = y - m["y1"], x - m["x1"]
            return 0 <= j < len(rows) and 0 <= i < len(rows[j]) and rows[j][i] in WALKABLE

        for c, v in n["cells"].items():
            v["dug"] = all(ready(*t) for t in self.cell_tiles(hub, c) if t != hub)
        for t, v in n["doors"].items():
            v["dug"] = ready(*t)
        rooms = len(n["cells"]) - 1
        undug = sum(1 for c, v in n["cells"].items() if not v.get("dug"))
        pending = self.o.get("dig_designations_pending") or 0
        if rooms < self.cit + DORM_SPARE and undug <= 1 and pending < 40 and self.may("net_grow", 2, 10 ** 6):
            self.last["net_grow"] = self.now
            m = m or self.net_map()
            if m and self.net_grow(m):
                self.find(f"cell network: {len(n['cells']) - 1} bedrooms planned, {len(n['doors'])} doorways")
        for c in n["cells"]:
            cx, cy = self.cell_centre(hub, c)
            self.dig_box(f"cell_{c[0]}_{c[1]}", z, (cx - 1, cy - 1, 3, 3))
        for t in n["doors"]:
            self.dig_box(f"dw_{t[0]}_{t[1]}", z, (t[0], t[1], 1, 1))
        doors = d(self.o.get("doors"))
        built = {(d(x).get("x"), d(x).get("y")) for x in lst(doors.get("list")) if d(x).get("z") == z}
        free_doors = doors.get("door_items_free") or 0
        want_doors = 0
        for c, v in n["cells"].items():
            if c == (0, 0) or not v.get("dug"):
                continue
            key = f"cell_{c[0]}_{c[1]}"
            cx, cy = self.cell_centre(hub, c)
            if not v.get("bed") and (self.free.get("bed") or 0) > 0:
                res = d(self.act(key + "_bed", "place_furniture",
                                 {"kind": "bed", "x": cx, "y": cy, "z": z, "w": 1, "h": 1, "count": 1}, retry=1, limit=20))
                if res.get("ok"):
                    v["bed"] = True
                    self.free["bed"] = (self.free.get("bed") or 1) - 1
            if v.get("bed") and not v.get("zone"):
                res = d(self.act(key + "_zone", "make_zone",
                                 {"kind": "bedroom", "x": cx - 1, "y": cy - 1, "z": z, "w": 3, "h": 3}, retry=2, limit=4))
                v["zone"] = bool(res.get("ok"))
        for t, v in n["doors"].items():
            if v.get("built") or t in built:
                v["built"] = True
                continue
            if not v.get("dug") or not all(n["cells"][c].get("dug") for c in v["pair"]):
                continue
            if free_doors > 0:
                res = d(self.act(f"dw_{t[0]}_{t[1]}_door", "build_door",
                                 {"kind": "door", "x": t[0], "y": t[1], "z": z}, retry=2, limit=4))
                if res.get("ok"):
                    v["built"] = True
                    free_doors -= 1
            else:
                want_doors += 1
        if want_doors and self.logs() >= 2 and not self.pending("make_door"):
            self.act("o_make_door", "add_order", {"recipe": "make_door", "amount": min(8, want_doors)}, retry=3, limit=40)

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
        alert = bur.get("civilian_alert")
        if alert and self.alert_since is None:
            self.alert_since = self.now
        elif alert is False:
            self.alert_since = None
        squads = lst(mil.get("squads"))
        squad = d(squads[0]) if squads else None
        if not squad and self.cit >= 14:
            self.act("squad", "create_squad", {"size": 4}, retry=5, limit=3)
        if squad and squad.get("uniform") == "none":
            self.act("equip", "equip_squad", {"uniform": "leather"}, retry=5, limit=3)
        shelter = self.room_for("dorm")
        if shelter and not any(d(b).get("civ_alert_burrow") for b in lst(bur.get("list"))):
            self.act("burrow", "create_burrow", {"site": shelter["id"]}, retry=5, limit=3)
        invaders = [h for h in lst(th.get("hostiles")) if d(h).get("invader")]
        hostile = th.get("visible_hostiles") or 0
        orders = lst((squad or {}).get("orders"))
        if hostile and squad and (squad.get("armed") or 0) >= 1 and not orders:
            self.act("attack", "squad_order", {"order": "attack"}, retry=1, limit=99)
        if not hostile and orders:
            self.act("stand_down", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
        near = (th.get("nearest_hostile_dist_to_wagon") or 10 ** 6) <= 45
        if invaders and near and not alert and any(d(b).get("civ_alert_burrow") for b in lst(bur.get("list"))):
            r = self.act("alert_on", "civilian_alert", {"on": True}, retry=20, limit=99)
            if r and r.get("ok"):
                self.alert_since = self.now
        self.hatches(invaders, near, alert)
        # civilians can't reach drink or food under a long alert: never hold it more than 10 days
        too_long = self.alert_since is not None and self.now - self.alert_since > 10 * DAY
        if alert and (not invaders or too_long):
            r = self.act("alert_off", "civilian_alert", {"on": False}, retry=1, limit=99)
            if r and r.get("ok"):
                self.alert_since = None

    def hatches(self, invaders, near, alert):
        """Hatch covers over the surface stairs (E sites): ordered once a hostile is reported or seen, placed when
        invaders come near, locked while the civilian alert holds them back, unlocked when it clears."""
        doors = d(self.o.get("doors"))
        threat = bool(invaders) or (self.hostile_at is not None and self.now - self.hostile_at < 10 * DAY)
        e_sites = [s for s in self.kind("E") if s.get("free")]
        have = [x for x in lst(doors.get("list")) if d(x).get("kind") == "hatch"]
        free = doors.get("hatch_cover_items_free") or 0
        if threat and not free and len(have) < 2 and not self.pending("make_hatch_cover") and self.logs():
            self.act("o_hatch", "add_order", {"recipe": "make_hatch_cover", "amount": 2}, retry=5, limit=4)
        if invaders and near and free:
            for s in e_sites[:min(free, 2)]:
                self.act("hatch_" + s["id"], "build_door", {"kind": "hatch", "site": s["id"]}, retry=3, limit=3)
        if have and alert and invaders and near and not self.locked:
            r = self.act("lock", "lock_door", {"locked": True}, retry=1, limit=99)
            self.locked = bool(r and r.get("ok"))
        elif self.locked and (not alert or not invaders):
            r = self.act("unlock", "lock_door", {"locked": False}, retry=1, limit=99)
            if r and r.get("ok"):
                self.locked = False

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
        self.configure_tools(self.game.task().get("tools") or [])
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
