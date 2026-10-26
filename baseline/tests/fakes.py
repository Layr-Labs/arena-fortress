"""A fake game server (game API v0 shapes, docs/GAME-API.md) and a fake model gateway, for tests and local dry runs.

Neither is DF: the fake fort is a few counters (drink, food, plants, barrels) that move with simple rules, enough to
exercise a harness end to end. Both run in a thread on a free localhost port:

    with FakeGame(days=10) as game, FakeModel() as model:
        ... DFBENCH_TASK with game_url=game.url, model.base_url=model.url ...

Or from the command line, for a local dry run of a harness (it serves until the fake game is over):
    python3 tests/fakes.py --days 30            # prints a DFBENCH_TASK pointing at both fakes
    python3 tests/fakes.py --host 0.0.0.0 --advertise host.docker.internal   # for a harness in a container
"""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DAY = 1200
START_TICK = 100 * DAY
WORKSHOP_TYPES = ["Bowyers", "Butchers", "Carpenters", "Clothiers", "Craftsdwarfs", "Farmers", "Fishery",
                  "GlassFurnace", "Jewelers", "Kitchen", "Leatherworks", "Loom", "Masons", "Mechanics",
                  "MetalsmithsForge", "Still", "Tanners", "WoodFurnace"]
RECIPES = {"brew_drink": ("CustomReaction", "BREW_DRINK_FROM_PLANT", "Still"),
           "make_barrel": ("MakeBarrel", None, "Carpenters"), "make_bed": ("ConstructBed", None, "Carpenters"),
           "make_table": ("ConstructTable", None, "Carpenters"), "make_chair": ("ConstructThrone", None, "Carpenters"),
           "cook_meal": ("PrepareMeal", None, "Kitchen")}

_I = {"type": "integer"}
_S = {"type": "string"}


def _tool(name, props=None, required=()):
    return {"type": "function", "function": {"name": name, "description": name.replace("_", " "),
            "parameters": {"type": "object", "required": list(required), "properties": props or {}}}}


TOOLS = [
    _tool("appoint_manager", {"dwarf_id": _I}),
    _tool("build_workshop", {"type": {"type": "string", "enum": WORKSHOP_TYPES}, "site": _S}, ("type", "site")),
    _tool("build_farm", {"site": _S}, ("site",)),
    _tool("add_order", {"recipe": {"type": "string", "enum": sorted(RECIPES)}, "amount": _I,
                        "repeat": {"type": "string", "enum": ["daily", "monthly"]},
                        "when": {"type": "array", "items": {"type": "object"}}}, ("amount",)),
    _tool("add_manager_order", {"job": _S, "reaction": _S, "amount": _I,
                                "repeat": {"type": "string", "enum": ["daily", "monthly"]},
                                "when": {"type": "array", "items": {"type": "object"}}}, ("job", "amount")),
    _tool("cancel_order", {"order_id": _I}, ("order_id",)),
    _tool("enable_automation", {"name": {"type": "string", "enum": ["autochop", "autofarm", "seedwatch"]}}, ("name",)),
    _tool("create_squad", {"size": _I}), _tool("equip_squad", {"uniform": _S}, ("uniform",)),
    _tool("squad_order", {"order": _S}, ("order",)), _tool("create_burrow", {"site": _S}, ("site",)),
    _tool("civilian_alert", {"on": {"type": "boolean"}}, ("on",)),
    _tool("build_door", {"kind": _S, "site": _S}, ("kind", "site")), _tool("build_wall", {"site": _S}, ("site",)),
    _tool("lock_door", {"locked": {"type": "boolean"}}, ("locked",)),
    _tool("dig_room", {"site": _S}, ("site",)), _tool("dig_stairs", {"site": _S}, ("site",)),
    _tool("place_furniture", {"kind": _S, "site": _S, "count": _I}, ("kind", "site")),
    _tool("make_zone", {"kind": _S, "site": _S}, ("kind", "site")),
    _tool("assign_zone", {"zone_id": _I, "dwarf_id": _I}, ("zone_id", "dwarf_id")),
    _tool("slaughter", {"unit_id": _I}, ("unit_id",)),
    _tool("advance_days", {"days": {"type": "integer", "minimum": 1, "maximum": 28},
                           "stop_on": {"type": "array", "items": _S}}, ("days",)),
]
MANUAL = "FAKE GAME API REFERENCE. Tools take site ids from map.sites. advance_days lets 1-28 days pass."


class _Server:
    host, port_wanted, advertise = "127.0.0.1", 0, None   # set before __init__ (the CLI does) to serve elsewhere

    def __init__(self, handler_cls):
        self.httpd = ThreadingHTTPServer((self.host, self.port_wanted), handler_cls)
        self.httpd.owner = self
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, headers=None):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return None


# =================================================================================================================
class FakeGame(_Server):
    """A fake game server. Rules as the contract (§4): K actions per day, advance 1..max_advance days, stopped early
    by a mood tripwire, hands-off from day `hands_off_day`, game over at the horizon or when drink and food both run
    out for 10 days. `mood_day`: a strange mood starts that day (StrangeMoodCarpenter, obs schema 7 facts); it claims
    a Carpenters workshop once one is built. With `mood_demand` (e.g. "logs") the dwarf then waits in the workshop
    for it until autochop is on; then (or with no demand) it finishes the next day."""

    def __init__(self, days=10, k=40, max_advance=28, hands_off_day=None, mood_day=None, mood_demand=None, citizens=7,
                 status_on_error=200):
        self.days, self.k, self.max_advance = days, k, max_advance
        self.hands_off_day, self.mood_day, self.mood_demand = hands_off_day, mood_day, mood_demand
        self.status_on_error = status_on_error   # 200 or 4xx for failed actions (the client must accept both)
        self.lock = threading.Lock()
        self.tick = START_TICK
        self.actions_today = 0
        self.log = []          # every /act request
        self.events = []
        self.next_id = 100
        self.manager = None
        self.dwarves = [{"id": 10 + i, "name": f"Urist {i}", "profession": "Miner", "job": "idle", "stress": 4,
                         "positions": []} for i in range(citizens)]
        self.stocks = {"drink": 40.0, "food_edible": 60.0, "prepared_meals": 0, "plants_brewable": 20,
                       "plants_total": 30, "barrels_empty": 3, "barrels_total": 5, "logs_usable": 10,
                       "boulders_usable": 0, "seeds": 20, "furniture_free": {"bed": 0, "table": 0, "chair": 0}}
        self.workshops, self.orders, self.zones, self.plots = [], [], [], []
        self.plugins = {"autochop": "off", "autofarm": "off", "seedwatch": "off"}
        self.sites = [{"id": "W1", "kind": "W", "x": 90, "y": 90, "z": 106, "w": 3, "h": 3},
                      {"id": "W2", "kind": "W", "x": 94, "y": 90, "z": 106, "w": 3, "h": 3},
                      {"id": "W3", "kind": "W", "x": 98, "y": 90, "z": 106, "w": 3, "h": 3},
                      {"id": "S1", "kind": "S", "x": 92, "y": 95, "z": 106},
                      {"id": "R1", "kind": "R", "x": 93, "y": 95, "z": 105, "w": 3, "h": 3, "soil": True,
                       "dug": False}]
        self.mood = None
        self.mood_done = False
        self.game_over = False
        self.dry_days = 0
        super().__init__(_GameHandler)

    @property
    def url(self):
        return f"http://{self.advertise or '127.0.0.1'}:{self.port}"

    @property
    def day(self):
        return (self.tick - START_TICK) // DAY

    def env(self):
        e = {"day": self.day, "tick": self.tick, "days_left": max(0, self.days - self.day), "game_over": self.game_over}
        if self.hands_off_day is not None:
            e["hands_off_in_days"] = max(0, self.hands_off_day - self.day)
        return e

    # --- observation (obs schema 6 as the starter's adapter assumes it) --------------------------------------
    def observation(self):
        st = {k: (int(v) if isinstance(v, float) else v) for k, v in self.stocks.items()}
        o = {"date": {"year": 1, "season": "spring", "day_of_year": 1 + self.day, "abs_tick": self.tick},
             "dwarves": self.dwarves,
             "administrators": {"MANAGER": self.manager["name"] if self.manager else "VACANT",
                                "BOOKKEEPER": "VACANT", "manager_active_for_orders": self.manager is not None,
                                "manager_office": "none"},
             "stocks": st, "orders": [{k: v for k, v in o.items() if not k.startswith("_")} for o in self.orders],
             "workshops": self.workshops, "zones": self.zones, "farm_plots": self.plots,
             "plugins": self.plugins, "dig_designations_pending": 0,
             "threats": {"visible_hostiles": 0, "dead_citizens_total": 0},
             "map": {"wagon": {"x": 95, "y": 95, "z": 106}, "surface_z": 106, "sites": self.sites}}
        if self.mood:
            o["moods"] = [self.mood]
        return o

    # --- simulation -----------------------------------------------------------------------------------------
    def _simulate_day(self):
        s = self.stocks
        n = len(self.dwarves)
        s["drink"] = max(0.0, s["drink"] - 0.5 * n)
        s["food_edible"] = max(0.0, s["food_edible"] - 0.3 * n)
        built = {w["type"] for w in self.workshops if w["built"]}
        for w in self.workshops:
            w["built"] = True    # built the day after it was placed
        for o in self.orders:
            o["validated"] = self.manager is not None
            if not o["validated"] or RECIPES.get(o["_recipe"], (0, 0, None))[2] not in built:
                continue
            if o["_recipe"] == "brew_drink":
                if s["barrels_empty"] > 0 and s["plants_brewable"] > 0:
                    s["drink"] += 5
                    s["plants_brewable"] -= 1
                    s["barrels_empty"] -= 1
                    o["active"] = True
                else:
                    self._report("Urist 2, Brewer cancels Brew drink from plant: Needs empty barrel")
            elif o["_recipe"] == "make_barrel" and s["logs_usable"] > 0:
                s["barrels_empty"] += 1
                s["logs_usable"] -= 1
            elif o["_recipe"] == "cook_meal":
                s["prepared_meals"] += 2
        s["plants_brewable"] += 1 if self.plots else 0
        for x in self.sites:
            if x.get("digging"):
                x["dug"], x["digging"] = True, False
        if s["drink"] <= 0 and s["food_edible"] <= 0:
            self.dry_days += 1
            if self.dry_days >= 10:
                self.game_over = True
        if self.mood is None and self.mood_day is not None and self.day >= self.mood_day and not self.mood_done:
            self.mood = {"unit_id": self.dwarves[0]["id"], "mood": "Fey", "skill": "CARPENTRY",
                         "job": "StrangeMoodCarpenter", "collected_items": 0, "waiting": False}
            self._report("Urist 0 is taken by a fey mood!", "STRANGE_MOOD")
            return "strange_mood"
        m = self.mood
        if m and m.get("claimed_building_id") is None:
            if "Carpenters" in built:
                ws = next(w for w in self.workshops if w["type"] == "Carpenters")
                m.update(claimed_building_id=ws["id"], claimed_workshop="Carpenters")
                if self.mood_demand:
                    m.update(waiting=True, items_needed=[{"demand": self.mood_demand, "quantity": None, "collected": 0}])
                else:
                    m["collected_items"] = 1
        elif m and m.get("waiting"):
            if self.plugins.get("autochop") == "on" and self.mood_demand == "logs":
                m.update(waiting=False, collected_items=1)
                m.pop("items_needed")
        elif m:
            self.mood, self.mood_done = None, True
            self._report("Urist 0 has created a masterpiece artifact!", "ARTIFACT")
        return None

    def _report(self, text, typ="CANCEL"):
        self.next_id += 1
        self.events.append({"id": self.next_id, "tick": self.tick, "type": typ, "text": text})

    def _fail(self, code, msg):
        return {"ok": False, "error_code": code, "error": msg}

    def act(self, req):
        if not isinstance(req, dict) or not isinstance(req.get("args", {}), dict):
            return self._fail("bad_arguments", "body must be {tool, args}")
        tool, args = req.get("tool"), req.get("args") or {}
        self.log.append({"tick": self.tick, "tool": tool, "args": args})
        if self.game_over or self.day >= self.days:
            self.game_over = True
            return self._fail("game_over", "the game is over")
        if self.hands_off_day is not None and self.day >= self.hands_off_day:
            return self._fail("hands_off", "the hands-off window has begun")
        names = {t["function"]["name"] for t in TOOLS}
        if tool not in names:
            return self._fail("unknown_tool", f"no tool named {tool!r}")
        if tool == "advance_days":
            return self._advance(args)
        if self.actions_today >= self.k:
            return self._fail("action_limit", f"{self.k} actions used today; only advance_days is accepted")
        self.actions_today += 1
        r = self._tool(tool, args)
        r.setdefault("ok", True)
        r["actions_left_today"] = self.k - self.actions_today
        return r

    def _advance(self, args):
        d = args.get("days")
        if not isinstance(d, int) or not 1 <= d <= self.max_advance:
            return self._fail("bad_arguments", f"days is 1-{self.max_advance}")
        start = self.tick
        stop = None
        for _ in range(d):
            if self.day >= self.days or self.game_over:
                break
            if self.hands_off_day is not None and self.day >= self.hands_off_day:
                break
            self.tick += DAY
            self.actions_today = 0
            why = self._simulate_day()
            if why:
                stop = {"reason": why, "detail": "unit 10", "after_ticks": self.tick - start}
                break
        if self.day >= self.days:
            self.game_over = True
        res = {"advanced_ticks": self.tick - start}
        if stop:
            res["stopped"] = stop
        return {"ok": True, "result": res, "actions_left_today": self.k}

    def _site(self, sid, kinds):
        s = next((x for x in self.sites if x["id"] == str(sid).upper()), None)
        if s is None:
            return None, self._fail("unknown_site", f"no site {sid}")
        if s["kind"] not in kinds:
            return None, self._fail("wrong_site_kind", f"takes a {'/'.join(kinds)} site, not {sid}")
        if s.get("used"):
            return None, self._fail("site_used", f"site {sid} is used")
        return s, None

    def _tool(self, tool, a):
        self.next_id += 1
        nid = self.next_id
        if tool == "appoint_manager":
            if self.manager:
                return self._fail("already_assigned", "the manager position is filled")
            self.manager = self.dwarves[1]
            self.manager["positions"] = ["MANAGER"]
            return {"result": {"manager_id": self.manager["id"]}}
        if tool == "build_workshop":
            if a.get("type") not in WORKSHOP_TYPES:
                return dict(self._fail("bad_arguments", f"unknown workshop type {a.get('type')!r}"),
                            allowed=WORKSHOP_TYPES)
            s, e = self._site(a.get("site"), ("W",))
            if e:
                return e
            s["used"] = True
            self.workshops.append({"id": nid, "type": a["type"], "x": s["x"] + 1, "y": s["y"] + 1, "z": s["z"],
                                   "built": False})
            return {"result": {"id": nid}}
        if tool in ("add_order", "add_manager_order"):
            if tool == "add_order" and "recipe" not in a:
                return self._fail("bad_arguments", "give either recipe or job")
            if tool == "add_manager_order":
                if "job" not in a:
                    return self._fail("bad_arguments", "job is required")
                rec = next((r for r in RECIPES.values() if r[0] == a["job"] and r[1] == a.get("reaction")),
                           (a["job"], a.get("reaction"), None))
            else:
                rec = RECIPES.get(a.get("recipe"))
            if not rec:
                return self._fail("bad_arguments", f"unknown recipe {a.get('recipe')!r}")
            when = [{"item_type": "DRINK", "flags": [], "test": "LessThan" if "below" in c else "AtLeast",
                     "value": c.get("below", c.get("at_least")), "stock_name": c.get("stock")}
                    for c in a.get("when") or [] if isinstance(c, dict)]
            o = {"id": nid, "_recipe": a.get("recipe") or next((k for k, r in RECIPES.items() if r == rec), None),
                 "job": rec[0], "reaction": rec[1], "left": a.get("amount", 1), "total": a.get("amount", 1),
                 "validated": False, "active": False, "jobs_in_progress": 0}
            if a.get("repeat"):
                o["repeat"] = a["repeat"]
            if when:
                o["when"] = when
            self.orders.append(o)
            return {"result": {"id": nid, "queued": f"Queuing order for {a.get('amount', 1)}"}}
        if tool == "cancel_order":
            n = len(self.orders)
            self.orders = [o for o in self.orders if o["id"] != a.get("order_id")]
            return {"result": {}} if len(self.orders) < n else self._fail("no_such_order", "no order with id")
        if tool == "enable_automation":
            was = self.plugins.get(a.get("name"), "off")
            self.plugins[a.get("name")] = "on"
            return {"result": {"was": was, "now": "on"}}
        if tool == "dig_room":
            s, e = self._site(a.get("site"), ("R",))
            if e:
                return e
            s["digging"] = True
            return {"result": {"designated": 9}}
        if tool == "build_farm":
            s, e = self._site(a.get("site"), ("F", "R", "G"))
            if e:
                return e
            if s["kind"] == "R" and not s.get("dug"):
                return self._fail("room_not_dug_yet", f"room {s['id']} is not dug yet")
            s["used"] = True
            self.plots.append({"id": nid, "x": s["x"], "y": s["y"], "z": s["z"], "w": 3, "h": 3, "built": True})
            return {"result": {"id": nid, "subterranean": True}}
        if tool == "place_furniture":
            return self._fail("no_space", "could not place: no free floor tile in the site")
        return {"result": {"id": nid}}


class _GameHandler(_Handler):
    def do_GET(self):
        g = self.server.owner
        u = urlparse(self.path)
        with g.lock:
            if u.path == "/health":
                return self._send(200, {"ok": True, **g.env()})
            if u.path == "/task":
                return self._send(200, {**g.env(), "api": "v0", "task": {"name": "fake", "days": g.days,
                                        "goal": "Keep the fort alive for {days} days.", "brief": "A fake fort."},
                                        "rules": {"actions_per_game_day": g.k, "max_advance_days": g.max_advance},
                                        "tools": TOOLS, "queries": ["stocks", "units"], "manual": MANUAL})
            if u.path == "/observe":
                return self._send(200, {**g.env(), **g.observation()})
            if u.path == "/events":
                since = int((parse_qs(u.query).get("since_tick") or ["0"])[0])
                return self._send(200, {**g.env(), "events": [e for e in g.events if e["tick"] >= since]})
            if u.path.startswith("/query/"):
                name = u.path[len("/query/"):]
                if name == "stocks":
                    return self._send(200, {**g.env(), "stocks": g.observation()["stocks"]})
                if name == "units":
                    return self._send(200, {**g.env(), "citizens": g.dwarves,
                                            "animals": [{"id": 500, "race": "COW", "tame": True}]})
                return self._send(404, {**g.env(), "ok": False, "error_code": "unknown_query", "error": name})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        g = self.server.owner
        if urlparse(self.path).path != "/act":
            return self._send(404, {"error": "not found"})
        body = self._body()
        with g.lock:
            r = g.act(body)
            code = 200 if r.get("ok") else g.status_on_error
            self._send(code, {**g.env(), **r})


# =================================================================================================================
class FakeModel(_Server):
    """A fake OpenAI-compatible gateway. By default it plays a scripted policy (scripted_policy below) from the
    latest OBSERVATION message. `script`: a list of special replies used first, one per call:
      ("http", code, body[, headers]), ("length",) (no tool call, finish_reason length), ("text",) (no tool call),
      ("two",) (two tool calls), ("badjson",) (unparseable arguments), ("call", name, args).
    Usage: prompt tokens ~ chars/4; cost reported in usage.cost when report_cost (at `price_in`/`price_out` per M)."""

    def __init__(self, script=None, report_cost=True, price_in=1.0, price_out=4.0, policy=None):
        self.script = list(script or [])
        self.report_cost = report_cost
        self.price_in, self.price_out = price_in, price_out
        self.policy = policy or scripted_policy
        self.requests = []
        self.spent = 0.0
        self.lock = threading.Lock()
        super().__init__(_ModelHandler)

    @property
    def url(self):
        return f"http://{self.advertise or '127.0.0.1'}:{self.port}/v1"

    def reply(self, body):
        self.requests.append(body)
        p_tok = len(json.dumps(body.get("messages"))) // 4
        c_tok = 40
        cost = (p_tok * self.price_in + c_tok * self.price_out) / 1e6
        usage = {"prompt_tokens": p_tok, "completion_tokens": c_tok, "total_tokens": p_tok + c_tok}
        if self.report_cost:
            usage["cost"] = cost
        step = self.script.pop(0) if self.script else None
        if step and step[0] == "http":
            return step[1], step[2], (step[3] if len(step) > 3 else {})
        self.spent += cost
        n = len(self.requests)
        if step and step[0] in ("length", "text"):
            msg = {"role": "assistant", "content": "thinking..."}
            return 200, _completion(msg, "length" if step[0] == "length" else "stop", usage), {}
        if step and step[0] == "call":
            name, args = step[1], step[2]
        else:
            name, args = self.policy(body.get("messages") or [])
        calls = [{"id": f"call_{n}", "type": "function",
                  "function": {"name": name, "arguments": "{not json" if step and step[0] == "badjson"
                               else json.dumps(args)}}]
        if step and step[0] == "two":
            calls.append({"id": f"call_{n}b", "type": "function",
                          "function": {"name": "advance_days", "arguments": "{\"days\": 1}"}})
        return 200, _completion({"role": "assistant", "content": None, "tool_calls": calls}, "tool_calls", usage), {}


def _completion(msg, finish, usage):
    return {"id": "fake", "object": "chat.completion", "model": "fake",
            "choices": [{"index": 0, "message": msg, "finish_reason": finish}], "usage": usage}


class _ModelHandler(_Handler):
    def do_GET(self):
        m = self.server.owner
        if urlparse(self.path).path in ("/status", "/v1/status"):
            st = {"spent_usd": round(m.spent, 6), "calls": len(m.requests)}
            if getattr(m, "budget_usd", None) is not None:
                st["budget_usd"] = m.budget_usd
            return self._send(200, st)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        m = self.server.owner
        if urlparse(self.path).path != "/v1/chat/completions":
            return self._send(404, {"error": "not found"})
        body = self._body()
        with m.lock:
            try:
                code, out, headers = m.reply(body)
            except Exception as e:   # a policy bug: answer 500 instead of dropping the connection
                code, out, headers = 500, {"error": f"fake model failed: {type(e).__name__}: {e}"}, {}
        self._send(code, out, headers)


def latest_observation(messages):
    for msg in reversed(messages):
        c = msg.get("content")
        if msg.get("role") == "user" and isinstance(c, str) and c.startswith("OBSERVATION {"):
            return json.loads(c[len("OBSERVATION "):])
    return {}


def scripted_policy(messages):
    """A tiny fort manager: manager, Still, brew order, the mood's workshop (from the starter's status), advance.
    Reads the starter's rendered observation, or the raw observation (the minimal harness)."""
    o = latest_observation(messages)
    st = o.get("status") or {}
    mp = o.get("map") or {}
    free_w = list(mp.get("W") or {}) or [x["id"] for x in mp.get("sites") or [] if x.get("kind") == "W" and not x.get("used")]
    w_site = free_w[0] if free_w else "W1"
    ws = " ".join(w if isinstance(w, str) else f" {w.get('type')} " for w in o.get("workshops") or [])
    for t in st.get("now") or []:
        m = re.search(r"build_workshop (\w+) now", t)
        if m and f" {m.group(1)} " not in ws:
            return "build_workshop", {"type": m.group(1), "site": w_site}
        if "autochop" in t and "autochop" not in ((o.get("plugins") or {}).get("on") or []):
            return "enable_automation", {"name": "autochop"}
    adm = o.get("administrators") or {}
    if not adm.get("manager_active_for_orders"):
        return "appoint_manager", {}
    if "Still" not in ws:
        return "build_workshop", {"type": "Still", "site": w_site}
    if not any(x.get("recipe") == "brew_drink" or x.get("reaction") == "BREW_DRINK_FROM_PLANT"
               for x in o.get("orders") or [] if isinstance(x, dict)):
        return "add_order", {"recipe": "brew_drink", "amount": 5, "repeat": "daily",
                             "when": [{"stock": "drink", "below": 70}]}
    return "advance_days", {"days": 3}


if __name__ == "__main__":
    import argparse
    import time
    ap = argparse.ArgumentParser(description="run the fake game and the fake gateway; print a DFBENCH_TASK")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--mood-day", type=int)
    ap.add_argument("--host", default="127.0.0.1", help="interface to listen on (0.0.0.0 for containers)")
    ap.add_argument("--advertise", help="host name the harness should use, e.g. host.docker.internal")
    ap.add_argument("--game-port", type=int, default=0)
    ap.add_argument("--model-port", type=int, default=0)
    a = ap.parse_args()
    _Server.host, _Server.advertise = a.host, a.advertise
    FakeGame.port_wanted, FakeModel.port_wanted = a.game_port, a.model_port
    with FakeGame(days=a.days, mood_day=a.mood_day) as g, FakeModel() as m:
        print(json.dumps({"schema": "dfbench-task/1", "run_id": "fake", "api": "v0", "game_url": g.url,
                          "model": {"base_url": m.url, "name": "fake", "api": "openai-chat", "api_key": "placeholder"},
                          "budget": {"credits": 0.5, "unit": "USD", "per": "game"},
                          "limits": {"wall_s": 5400, "actions_per_game_day": 40, "max_advance_days": 28},
                          "task": {"name": "fake", "days": a.days}}), flush=True)
        while not g.game_over:
            time.sleep(0.5)
        time.sleep(1)
