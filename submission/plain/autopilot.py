"""The autopilot (cut 3): routine fortress steps the harness does itself, deterministically, before each model turn.

The fixed model is a cheap flash model at low reasoning effort. Cut 2's STATUS digest tells it what is missing, but
the steps it most often has to take are routine and unambiguous (appoint a manager; turn on autochop and seedwatch;
build the Carpenters, Still and Kitchen; keep repeating orders for drink, barrels and meals; order beds; start an
underground farm), and skipping one of them is what sinks a fort's supply. The autopilot takes those steps itself,
from the observation alone, and leaves everything that needs a decision to the model (rooms, furniture placement and
zones, the manager's office, defence, moods, fixing a stuck chain).

Before a hands-off window (lab tasks) it also checks that the fort will keep itself supplied through the window:
a repeating brew order whose threshold is above the drink the fort will have, barrels, meals, the plugins on; and
it reports what it cannot fix (an unbuilt Still, no planted farm plot, beds not placed) to the model.

Sources it adapts (RULES.md section 4 allows the repository's reference policies; credited in NOTE.md):
  - policies.Scripted (repo root): the order of the setup steps (manager; autochop and seedwatch; Carpenters, Still
    and Kitchen; barrels before brewing; beds for everyone; meals; an underground farm via a stair and a room;
    autofarm once a plot exists), its per-step retry spacing and attempt cap (_may/_do), and the farm-room wait;
  - policies.Automation: the manager pick (not the only miner, woodworker or farmer);
  - harness2.py / digest.py: the recipe table and recipe_of().

Every step is bounded: a key is tried at most every RETRY_DAYS, gives up after MAX_FAILS failures, and steps that
can recur (furniture orders) have their own attempt caps. plan() never raises on a malformed observation: a field it
cannot read means the step is simply not planned.
"""
import json

from .digest import recipe_of

DAY = 1200
DRINK_PER_DWARF_PER_DAY = 20 / 336     # docs/SUCCESS.md section 1.2: about 20 drinks a year per dwarf

CORE = ("Carpenters", "Still", "Kitchen")
STRANGE_MOODS = ("Fey", "Secretive", "Possessed", "Macabre", "Fell")   # DF's strange moods (not the insane ones)
KEY_PROFESSIONS = ("miner", "woodcutter", "woodworker", "carpenter", "planter", "farmer", "grower", "brewer")
BAD_SITE_CODES = {"tile_hidden", "not_open_floor", "tile_occupied", "site_used", "unknown_site", "wrong_site_kind",
                  "not_soil_floor", "nothing_designated", "room_not_dug_yet", "no_space", "wrong_tile_shape"}
GIVE_UP_CODES = {"bad_arguments", "unknown_tool", "already_assigned", "no_position", "server_tool", "not_enabled"}
# NEXT keys of the digest that the autopilot covers (hidden from the model's NEXT list unless it gave up on them)
OFFICE_FROM = 16      # citizens from which the autopilot sets up the manager's office (DF stops validating from ~20)
HANDLED = ("manager", "office", "plugin:autochop", "plugin:seedwatch", "plugin:autofarm", "wood", "ws", "order:brew",
           "order:barrel", "order:cook", "beds:order", "farm")


def _d(x):
    return x if isinstance(x, dict) else {}


def _l(x):
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []


def _n(x, default=0):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else default


def _used(site):
    """A site something already occupies (the server's `used_by`; `used` in some test doubles)."""
    return bool(site.get("used_by") or site.get("used"))


def short(args):
    try:
        s = json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        s = str(args)
    return s if len(s) <= 90 else s[:87] + "..."


class Autopilot:
    RETRY_DAYS = 3        # don't repeat the same step more often than this (policies.Scripted.RETRY_DAYS)
    MAX_FAILS = 3         # give up on a step after this many failures
    MAX_ATTEMPTS = 4      # ... or this many attempts of a one-time step (a success the observation never shows)
    MAX_STEPS = 8         # actions per pass
    READY_DAYS = 7        # the hands-off readiness check starts this many days before the window
    STAIR_WAIT_DAYS = 15  # a stair whose rooms never appear: try another stair site after this long
    RECURRING = {"order:beds": 12, "order:tables": 8, "order:chairs": 8, "order:brew_more": 3, "ready:brew": 3}

    def __init__(self):
        self.attempts = {}    # key -> attempts
        self.fails = {}       # key -> failures
        self.last = {}        # key -> tick of the last attempt
        self.gave_up = set()
        self.bad_sites = set()
        self.orders = {}      # order id -> recipe, for orders the autopilot added
        self.log = []         # (day, tool, args_short, ok, error_code) of every autopilot action
        self.farm_failures = 0
        self.farm_blocked = False   # the farm pipeline has no next step (no soil room to dig, no stair site)
        self.office_site = None     # cut 4: the site the autopilot made (or is digging) the manager's office on
        self.office_blocked = False  # cut 4: the office is needed and the autopilot has no way to make it
        self.ws_blocked = False     # a core workshop is missing and no free W site is listed
        self.mood_pause = False     # a strange mood is on: no log-consuming steps

    # --- bookkeeping ----------------------------------------------------------------------------------------
    def may(self, key, now, retry_days=None):
        if key in self.gave_up:
            return False
        cap = self.RECURRING.get(key.split("@")[0], self.MAX_ATTEMPTS)
        if self.attempts.get(key, 0) >= cap or self.fails.get(key, 0) >= self.MAX_FAILS:
            return False
        last = self.last.get(key)
        if last is None or now is None:
            return True
        return now - last >= (self.RETRY_DAYS if retry_days is None else retry_days) * DAY

    def record(self, key, tool, args, resp, now, day):
        """The result of one autopilot action: counts, gives up where the error says retrying can't help."""
        ok = bool(_d(resp).get("ok"))
        code = None if ok else str(_d(resp).get("error_code") or "failed")
        self.attempts[key] = self.attempts.get(key, 0) + 1
        self.last[key] = now
        self.log = (self.log + [(day, tool, short(args), ok, code)])[-40:]
        r = _d(_d(resp).get("result")) or _d(resp)
        if ok:
            oid = r.get("order_id", r.get("id")) if tool == "add_order" else None
            if oid is not None:
                self.orders[oid] = args.get("recipe")
            return
        self.fails[key] = self.fails.get(key, 0) + 1
        site = args.get("site")
        if site and code in BAD_SITE_CODES:
            self.bad_sites.add(site)
            self.fails[key] -= 1          # a bad site is not the step's failure: the next try picks another site
            self.attempts[key] -= 1
            self.last[key] = None
        if tool in ("build_farm", "dig_room", "dig_stairs"):
            self.farm_failures += 1
        if code in GIVE_UP_CODES and not (tool == "appoint_manager" and args.get("dwarf_id") is not None
                                          and code != "already_assigned"):
            self.gave_up.add(key)

    ORDER_KEYS = {"brew_drink": "order:brew", "make_barrel": "order:barrel", "cook_meal": "order:cook",
                  "make_bed": "order:beds", "make_table": "order:tables", "make_chair": "order:chairs"}

    def on_cancel(self, order_id, now):
        """The model cancelled an order the autopilot added: wait RETRY_DAYS before adding it again (and count the
        attempt), so the two don't undo each other turn after turn."""
        key = self.ORDER_KEYS.get(self.orders.pop(order_id, None))
        if key:
            self.last[key] = now
            self.attempts[key] = self.attempts.get(key, 0) + 1

    def handled(self):
        """The digest's NEXT keys the autopilot covers (so the model isn't asked to duplicate them)."""
        out = set(HANDLED)
        if self.ws_blocked or any(k.startswith("ws:") and not self.may(k, None, 0)
                                  for k in list(self.attempts) + list(self.gave_up)):
            out.discard("ws")
        if self.farm_failures >= 4 or "stairs" in self.gave_up or self.farm_blocked:
            out.discard("farm")
        if self.office_blocked or any(k.startswith("office:") and (k in self.gave_up
                                                                    or self.fails.get(k, 0) >= self.MAX_FAILS)
                                      for k in list(self.attempts) + list(self.gave_up)):
            out.discard("office")
        for k in ("manager", "plugin:autochop", "plugin:seedwatch", "plugin:autofarm"):
            if k in self.gave_up or self.fails.get(k, 0) >= self.MAX_FAILS:
                out.discard(k)
        if "plugin:autochop" not in out:
            out.discard("wood")
        for k, nk in (("order:brew", "order:brew"), ("order:barrel", "order:barrel"), ("order:cook", "order:cook"),
                      ("order:beds", "beds:order")):
            if k in self.gave_up or self.fails.get(k, 0) >= self.MAX_FAILS:
                out.discard(nk)
        return out

    def recent(self, k=6):
        return self.log[-k:]

    # --- facts --------------------------------------------------------------------------------------------
    @staticmethod
    def _orders_with(orders, recipes, repeating=None, pending=False, mine=None):
        out = []
        for o in orders:
            rec = recipe_of(o) or (mine or {}).get(o.get("id"))
            if rec not in recipes:
                continue
            if repeating is True and not o.get("repeat"):
                continue
            if pending and not (o.get("repeat") or _n(o.get("left")) > 0):
                continue
            out.append(o)
        return out

    @staticmethod
    def brew_threshold(orders):
        """The highest drink level below which a repeating brew order still runs (None: no repeating brew order;
        inf: one with no drink condition)."""
        best = None
        for o in orders:
            if recipe_of(o) not in ("brew_drink", "brew_drink_from_fruit") or not o.get("repeat"):
                continue
            conds = [w for w in _l(o.get("when")) if str(w.get("item_type") or "").upper() == "DRINK"
                     or w.get("stock") == "drink"]
            lt = [_n(w.get("value"), None) for w in conds if str(w.get("test") or "").lower().startswith("less")]
            lt = [v for v in lt if v is not None]
            v = max(lt) if lt else float("inf")
            best = v if best is None else max(best, v)
        return best

    # --- the plan -------------------------------------------------------------------------------------------
    def plan(self, obs, env, tool_names=None):
        """The autopilot's next steps for this observation: [(key, tool, args, why)], at most MAX_STEPS, at most
        one step per site kind (a site list is only fresh until something is placed on it)."""
        try:
            return self._plan(_d(obs), _d(env), tool_names)
        except Exception:   # a malformed observation: plan nothing rather than fail the turn
            return []

    def _plan(self, obs, env, tool_names):
        now = _n(env.get("tick"), None)
        if now is None:
            now = _n(_d(obs.get("date")).get("abs_tick"), None)
        h = env.get("hands_off_in_days")
        if isinstance(h, (int, float)) and not isinstance(h, bool) and h <= 0:
            return []
        dwarves = _l(obs.get("dwarves"))
        n = len(dwarves) or _n(_d(obs.get("administrators")).get("citizens"), 0)
        if n <= 0:
            return []
        st = _d(obs.get("stocks"))
        adm = _d(obs.get("administrators"))
        plugins = _d(obs.get("plugins"))
        orders = _l(obs.get("orders"))
        workshops = _l(obs.get("workshops"))
        sites = [s for s in _l(_d(obs.get("map")).get("sites")) if isinstance(s.get("id"), str)]
        plots = _l(obs.get("farm_plots"))
        built = {str(w.get("type")) for w in workshops if w.get("built")}
        have_ws = {str(w.get("type")) for w in workshops}
        steps, kinds_used = [], set()
        # a dwarf in a strange mood needs its workshop (which costs a log or boulder) and often a log: while one is
        # on, the autopilot adds nothing that uses up logs (workshops, barrels, furniture), so they stay available
        self.mood_pause = any(str(m.get("mood")) in STRANGE_MOODS or str(m.get("job") or "").startswith("StrangeMood")
                              for m in _l(obs.get("moods")))

        def add(key, tool, args, why, site_kind=None, retry_days=None):
            if tool_names is not None and tool not in tool_names:
                return
            if site_kind and site_kind in kinds_used:
                return
            if any(s[0] == key for s in steps) or not self.may(key, now, retry_days):
                return
            steps.append((key, tool, args, why))
            if site_kind:
                kinds_used.add(site_kind)

        # 1. the manager (no manager: every order stays unvalidated)
        mgr = adm.get("MANAGER")
        if not adm.get("manager_active_for_orders") and mgr in (None, "", "VACANT"):
            args = {} if self.fails.get("manager") else self._pick_manager(dwarves)
            add("manager", "appoint_manager", args, "no manager: orders are never validated")

        # 1b. the manager's office (cut 4): from OFFICE_FROM citizens DF validates orders only from it
        self._office(obs, now, n, dwarves, sites, add)

        # 2. plugins
        for p in ("autochop", "seedwatch"):
            state = plugins.get(p)
            if state == "off" or (state == "unknown" and not self.attempts.get("plugin:" + p)):
                add("plugin:" + p, "enable_automation", {"name": p},
                    "autochop keeps usable logs coming" if p == "autochop" else "seedwatch keeps seeds from being eaten or brewed")
        if plots:
            state = plugins.get("autofarm")
            if state == "off" or (state == "unknown" and not self.attempts.get("plugin:autofarm")):
                add("plugin:autofarm", "enable_automation", {"name": "autofarm"}, "farm plots get no crop without it")

        # 3. the core workshops, one per pass, on a free W site, when a usable log or boulder exists
        material = _n(st.get("logs_usable")) > 0 or _n(st.get("boulders_usable")) > 0
        free_w = [s for s in sites if s.get("kind") == "W" and s.get("free") is not False and not _used(s)
                  and s["id"] not in self.bad_sites]
        self.ws_blocked = any(t not in have_ws for t in CORE) and not free_w
        if material and free_w and not self.mood_pause:
            for t in CORE:
                if t not in have_ws:
                    add("ws:" + t, "build_workshop", {"type": t, "site": free_w[0]["id"]},
                        f"no {t} (drink, food and furniture need it)", site_kind="W")
                    break

        # 4. the underground farm
        self._farm(obs, now, n, sites, plots, add)

        # 5. standing orders, once their workshop exists (built or placed)
        mine = self.orders
        if "Carpenters" in have_ws and not self.mood_pause and not self._orders_with(orders, {"make_barrel"},
                                                                                     repeating=True, mine=mine):
            add("order:barrel", "add_order", {"recipe": "make_barrel", "amount": 2, "repeat": "daily",
                                              "when": [{"stock": "barrels_empty", "below": 3}]},
                "brewing needs empty barrels")
        thr = self.brew_threshold(orders)
        want = int(max(60, 10 * n))
        if "Still" in have_ws:
            if thr is None and not self._orders_with(orders, {"brew_drink"}, repeating=True, mine=mine):
                add("order:brew", "add_order", {"recipe": "brew_drink", "amount": 5, "repeat": "daily",
                                                "when": [{"stock": "drink", "below": want}]},
                    f"no standing brew order (keeps drink near {want})")
            elif thr is not None and thr != float("inf") and want > 1.5 * thr:
                add("order:brew_more@%d" % want, "add_order", {"recipe": "brew_drink", "amount": 5, "repeat": "daily",
                                                              "when": [{"stock": "drink", "below": want}]},
                    f"the population outgrew the brew order's threshold {int(thr)}", retry_days=10)
        if "Kitchen" in have_ws and not self._orders_with(orders, {"cook_meal"}, repeating=True, mine=mine):
            add("order:cook", "add_order", {"recipe": "cook_meal", "amount": 3, "repeat": "daily",
                                            "when": [{"stock": "prepared_meals", "below": int(max(20, 2 * n))},
                                                     {"stock": "drink", "at_least": int(4 * n)}]},
                "no standing cooking order (it pauses while drink is low, so plants go to the still)")

        # 6. hands-off readiness: brewing must keep going through the window
        if isinstance(h, (int, float)) and not isinstance(h, bool) and 0 < h <= self.READY_DAYS and "Still" in have_ws:
            need, target = self.window_drink(obs, env, n)
            if thr is None or thr < need:
                add("ready:brew", "add_order", {"recipe": "brew_drink", "amount": 5, "repeat": "daily",
                                                "when": [{"stock": "drink", "below": target}]},
                    f"hands-off in {h} d: keep brewing through the window (drink {_n(st.get('drink'))}, threshold "
                    f"{'none' if thr is None else int(thr)} < {need})", retry_days=1)

        # 7. one-shot furniture orders at a built Carpenters: beds for everyone, then dining tables and chairs
        if "Carpenters" in built and not self.mood_pause:
            beds = _n(st.get("beds"))
            if beds < n + 2 and not self._orders_with(orders, {"make_bed"}, pending=True, mine=mine):
                add("order:beds", "add_order", {"recipe": "make_bed", "amount": int(min(10, n + 2 - beds))},
                    f"beds {beds} for {n} citizens")
            elif beds >= n:
                need = (n + 1) // 2 + 1
                if _n(st.get("tables")) < need and not self._orders_with(orders, {"make_table"}, pending=True, mine=mine):
                    add("order:tables", "add_order", {"recipe": "make_table",
                                                      "amount": int(min(5, need - _n(st.get("tables"))))},
                        f"dining needs a table per two citizens ({_n(st.get('tables'))}/{need})")
                if _n(st.get("chairs")) < need + 1 and not self._orders_with(orders, {"make_chair"}, pending=True, mine=mine):
                    add("order:chairs", "add_order", {"recipe": "make_chair",
                                                      "amount": int(min(5, need + 1 - _n(st.get("chairs"))))},
                        f"dining (and the manager's office) need chairs ({_n(st.get('chairs'))}/{need + 1})")
        return steps[:self.MAX_STEPS]

    @staticmethod
    def _pick_manager(dwarves):
        free = [d for d in dwarves if not d.get("positions") and d.get("adult") is not False
                and isinstance(d.get("id"), int) and not isinstance(d.get("id"), bool)]
        spare = [d for d in free if not any(k in str(d.get("profession") or "").lower() for k in KEY_PROFESSIONS)]
        pool = spare or free
        if not pool:
            return {}
        best = max(pool, key=lambda d: _n(d.get("organizer_skill")))
        return {"dwarf_id": best["id"]}

    def _office(self, obs, now, n, dwarves, sites, add):
        """policies.manager_office_step on the v3 tools: an Office zone on a dug room (a free R room, else the dug
        A area of a level), assigned to the manager, with a chair placed in it (or ordered, if none is free)."""
        self.office_blocked = False
        adm = _d(obs.get("administrators"))
        if n < OFFICE_FROM or not adm.get("manager_active_for_orders"):
            return
        office = adm.get("manager_office")
        if isinstance(office, dict) and office.get("chair"):
            return                                    # in place: an assigned office with a built chair
        mid = adm.get("MANAGER_id")
        if not isinstance(mid, int) or isinstance(mid, bool):
            self.office_blocked = True                # no manager id to assign to: the model's
            return
        zones = _l(obs.get("zones"))
        offices = [z for z in zones if str(z.get("type") or "").lower() == "office"]
        mine = None
        if isinstance(office, dict) and office.get("zone_id") is not None:
            mine = next((z for z in offices if z.get("id") == office.get("zone_id")), {"id": office.get("zone_id")})
        if mine is None:
            mine = next((z for z in offices if z.get("owner") == mid), None)
        if mine is None:
            living = {d.get("id") for d in dwarves}
            free = next((z for z in offices if z.get("owner") is None or z.get("owner") not in living), None)
            if free is not None and free.get("id") is not None:
                add("office:assign", "assign_zone", {"zone_id": free["id"], "dwarf_id": mid},
                    f"{n} citizens: the manager needs an office (office zone {free['id']} has no living owner)",
                    retry_days=1)
                return
            room = self._office_room(sites)
            if room is not None:
                self.office_site = room["id"]
                add("office:zone", "make_zone", {"kind": "office", "site": room["id"]},
                    f"{n} citizens: DF validates new orders only from the manager's office", site_kind=room["kind"],
                    retry_days=1)
                return
            free_r = [s for s in sites if s.get("kind") == "R" and not s.get("designated") and not s.get("dug")
                      and not _used(s) and s["id"] not in self.bad_sites]
            if free_r:
                free_r.sort(key=lambda s: bool(s.get("soil")))   # stone first: soil rooms are for farms
                self.office_site = free_r[0]["id"]
                add("office:dig", "dig_room", {"site": free_r[0]["id"]},
                    f"{n} citizens: no dug room for the manager's office", site_kind="R", retry_days=5)
            else:
                self.office_blocked = True
            return
        # the office exists and is the manager's: a chair in it
        planned = _d(mine.get("furniture_planned"))
        if any("chair" in str(k).lower() or "throne" in str(k).lower() for k, v in planned.items() if _n(v)):
            return                                    # a chair is placed and waits to be built
        site = self.office_site if self._site_matches(sites, self.office_site, mine) else self._site_of(sites, mine)
        if site in self.bad_sites or site in getattr(self, "full_sites", ()):
            self.office_blocked = True                # the chair found no tile there: the model's
            return
        free_chairs = _n(_d(_d(obs.get("stocks")).get("furniture_free")).get("chair"))
        if free_chairs > 0 and site:
            add("office:chair", "place_furniture", {"kind": "chair", "site": site, "count": 1},
                "the manager's office needs a built chair", retry_days=2)
        elif free_chairs <= 0:
            built = {str(w.get("type")) for w in _l(obs.get("workshops")) if w.get("built")}
            pending = self._orders_with(_l(obs.get("orders")), {"make_chair"}, pending=True, mine=self.orders)
            if "Carpenters" in built and not pending and not self.mood_pause:   # a chair costs a log
                add("office:chair_order", "add_order", {"recipe": "make_chair", "amount": 1},
                    "a chair for the manager's office (none is free)", retry_days=2)
        else:
            self.office_blocked = True                # an office zone the autopilot can't map to a site: the model's

    def _office_room(self, sites):
        """A dug room for the office: the one already chosen, else a free dug R room (one that is not all soil
        first: those are the farm's), else a dug A area."""
        rooms = [s for s in sites if s.get("kind") == "R" and s.get("dug") and not _used(s) and s["id"] not in self.bad_sites]
        if self.office_site:
            keep = [s for s in rooms if s["id"] == self.office_site]
            if keep:
                return keep[0]

        def all_soil(s):
            t = _d(s.get("tiles"))
            return _n(t.get("soil_floor"), -1) >= _n(t.get("tiles"), 9) if t else bool(s.get("soil"))
        rooms.sort(key=all_soil)
        if rooms:
            return rooms[0]
        areas = [s for s in sites if s.get("kind") == "A" and s["id"] not in self.bad_sites]
        return areas[0] if areas else None

    @staticmethod
    def _site_matches(sites, sid, zone):
        s = next((x for x in sites if x.get("id") == sid), None)
        return bool(s) and all(s.get(k) == zone.get(k) for k in ("x", "y", "z") if zone.get(k) is not None)

    @staticmethod
    def _site_of(sites, zone):
        """The R or A site whose box starts where the zone does (make_zone covers the site's box)."""
        if zone.get("x") is None:
            return None
        for s in sites:
            if s.get("kind") in ("R", "A") and (s.get("x"), s.get("y"), s.get("z")) == (zone.get("x"), zone.get("y"), zone.get("z")):
                return s["id"]
        return None

    def _farm(self, obs, now, n, sites, plots, add):
        """policies.Scripted's underground farm, on the v3 sites: a stair from an S site, a room on a soil R site
        beside it, a farm plot once the room is dug. Only while the fort has fewer plots than it needs."""
        target = 2 if n < 15 else 3 if n < 30 else 4
        self.farm_blocked = False
        if len(plots) >= target:
            return
        bad = self.bad_sites
        ready = [s for s in sites if s.get("kind") == "F" and s.get("free") is not False and not _used(s)
                 and s["id"] not in bad]
        for s in sites:
            if s.get("kind") != "R" or not s.get("dug") or _used(s) or s["id"] in bad or s["id"] == self.office_site:
                continue
            tiles = _d(s.get("tiles"))
            all_soil = _n(tiles.get("soil_floor"), -1) >= _n(tiles.get("tiles"), 9) if tiles else bool(s.get("soil"))
            if all_soil:
                ready.append(s)
        if ready:
            s = ready[0]
            add("farm:" + s["id"], "build_farm", {"site": s["id"]}, f"farm plots {len(plots)}/{target}: {s['id']} is "
                + ("dug soil" if s.get("kind") == "R" else "a soil floor"), site_kind="farm")
            return
        digging = [s for s in sites if s.get("kind") == "R" and s.get("designated") and not s.get("dug")]
        if digging and (_n(obs.get("dig_designations_pending")) > 0 or not isinstance(obs.get("dig_designations_pending"), (int, float))):
            return   # a room is being dug: wait for it
        free_r = [s for s in sites if s.get("kind") == "R" and not s.get("designated") and not s.get("dug")
                  and not _used(s) and s.get("soil") and s["id"] not in bad and s["id"] != self.office_site]
        if free_r:
            s = free_r[0]
            add("dig:" + s["id"], "dig_room", {"site": s["id"]}, f"farm plots {len(plots)}/{target}: dig a soil room "
                "for one", site_kind="R")
            return
        if plots or any(s.get("kind") == "R" for s in sites) or _n(obs.get("dig_designations_pending")) > 0:
            # stairs exist (rooms are listed) or digging is under way: nothing more to start here; with no plot at
            # all and no soil room left to dig, the model gets the farm item back
            self.farm_blocked = not plots and not _n(obs.get("dig_designations_pending"))
            return
        s_sites = [s for s in sites if s.get("kind") == "S" and s["id"] not in bad]
        if not s_sites or not self.may("stairs", now, self.STAIR_WAIT_DAYS):
            self.farm_blocked = True
        if s_sites:
            s = s_sites[0]
            args = {"site": s["id"]}
            if isinstance(s.get("z"), int) and not isinstance(s.get("z"), bool):
                args["z_bottom"] = s["z"] - 2
            add("stairs", "dig_stairs", args, "no farm and no room to dig one: a stair down two levels first",
                site_kind="S", retry_days=self.STAIR_WAIT_DAYS)

    # --- hands-off readiness -------------------------------------------------------------------------------
    @staticmethod
    def window_drink(obs, env, n):
        """(the drink level a brew order's threshold must exceed so brewing keeps going through the window,
        the threshold to give a new one)."""
        st = _d(obs.get("stocks"))
        drink = _n(st.get("drink"))
        h = _n(env.get("hands_off_in_days"), 0)
        w = max(1, _n(env.get("days_left"), h + 21) - h)
        cons = n * DRINK_PER_DWARF_PER_DAY * w
        return int(drink + cons + 5 * n), int(min(100000, drink + cons + 10 * n))

    def readiness(self, obs, env):
        """The hands-off readiness report: (line or None, [(key, text)] of what needs the model)."""
        try:
            return self._readiness(_d(obs), _d(env))
        except Exception:
            return None, []

    def _readiness(self, obs, env):
        h = env.get("hands_off_in_days")
        if not isinstance(h, (int, float)) or isinstance(h, bool) or h <= 0 or h > self.READY_DAYS:
            return None, []
        n = len(_l(obs.get("dwarves"))) or _n(_d(obs.get("administrators")).get("citizens"), 0) or 1
        st = _d(obs.get("stocks"))
        orders = _l(obs.get("orders"))
        ws = _l(obs.get("workshops"))
        plots = _l(obs.get("farm_plots"))
        plugins = _d(obs.get("plugins"))
        okl, bad = [], []
        stills = [w for w in ws if str(w.get("type")) == "Still"]
        if any(w.get("built") for w in stills):
            okl.append("Still built")
        else:
            bad.append(("ready:still", "Still " + ("placed but NOT BUILT" if stills else "MISSING")
                        + ": the window needs a built Still (it needs a usable log or boulder and a free dwarf)"))
        thr = self.brew_threshold(orders)
        need, _ = self.window_drink(obs, env, n)
        if thr is not None and thr >= need:
            okl.append("standing brew order covers the window")
        else:
            bad.append(("ready:brew", f"no repeating brew order that keeps brewing through the window (needs a drink "
                                      f"threshold >= {need}; the autopilot adds one)"))
        tick = _n(env.get("tick"), None)
        unval = [o for o in orders if o.get("repeat") and not o.get("validated")
                 and recipe_of(o) in ("brew_drink", "cook_meal", "make_barrel")
                 and (tick is None or _n(o.get("created_tick"), None) is None
                      or tick - o["created_tick"] > 1.5 * DAY)]   # a new order normally waits about a day
        if unval:
            bad.append(("ready:validated", "repeating orders not yet validated: " + ", ".join(
                f"#{o.get('id')} {recipe_of(o)}" for o in unval[:4]) + " (manager active? office at 20+ citizens?)"))
        if _n(st.get("barrels_empty")) > 0 or self._orders_with(orders, {"make_barrel"}, repeating=True):
            okl.append("barrels")
        else:
            bad.append(("ready:barrels", "no empty barrel and no repeating make_barrel order"))
        if _n(st.get("plants_brewable")) <= 0 and not plots:
            bad.append(("ready:plants", "no brewable plant and no farm plot: nothing to brew in the window"))
        planted = [p for p in plots if _n(p.get("seeds_or_crops_in_plot")) > 0
                   or str(p.get("crop_this_season") or "none") not in ("none", "")]
        if plots and not planted:
            bad.append(("ready:planted", "no farm plot is planted (seeds in stock? autofarm on? a farmer?)"))
        elif planted:
            okl.append(f"{len(planted)} planted plot(s)")
        off = [p for p in ("autofarm", "seedwatch", "autochop") if plugins.get(p) == "off" and (p != "autofarm" or plots)]
        if off:
            bad.append(("ready:plugins", "plugins off: " + ", ".join(off)))
        furn = _l(obs.get("furniture"))
        beds = sum(1 for f in furn if str(f.get("kind")).lower() == "bed" and f.get("built"))
        if beds < n:
            bad.append(("ready:beds", f"beds placed {beds}/{n}: every dwarf needs a placed bed (place_furniture bed "
                                      "on a dug A/R site; more migrants may come during the window)"))
        if _n(st.get("food_edible")) < 2 * n:
            bad.append(("ready:food", f"food_edible {_n(st.get('food_edible'))} is under 2 per dwarf"))
        line = (f"HANDS-OFF READINESS ({h} d left to act): ok: " + (", ".join(okl) or "nothing yet")
                + ("; MISSING: " + "; ".join(t for _, t in bad) if bad else "; nothing missing"))
        model = [(k, t) for k, t in bad if k not in ("ready:brew",)]
        return line, model
