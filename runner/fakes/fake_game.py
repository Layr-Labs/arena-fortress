#!/usr/bin/env python3
"""A fake game server for the season-0 runner (docs/GAME-API.md §3, §4, §6), with no DF.

It implements the v0 HTTP API on port 8090 with a toy fort simulation (stocks, beds, a strange mood, migrants), enforces
the rules (K actions per game-day, max advance, hands-off window, wall cap, a lost fort ends the game, game_over) and
writes the §6 artifacts in the shapes `bench/outcomes.py` and `bench/predicates.py` read: summary.jsonl, <run>.daily.json,
<run>.credit.json, <run>.final.json and <run>.api.jsonl. Not a DF model: the numbers only have to move with the actions
so that scoring is exercised end to end.

Input (as the runner gives the real server): env DFBENCH_GAME (JSON, runner/README.md "game input"), the scenario JSON
at DFBENCH_GAME.scenario_path, the artifacts dir DFBENCH_GAME.artifacts_dir, the gateway ledger at
DFBENCH_GAME.ledger_path and gateway_status_path (read-only; throttle waits are excluded from the wall cap).

  python3 fake_game.py [--port 8090]
Env FAKE_SEC_PER_DAY (default 0.01) sets the simulated wall time per game-day.
stdlib only; also importable (class Game) for in-process tests.
"""
import argparse, json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

DAY = 1200
T0 = 1228020                       # abs_tick at load (any value: the scorers use ticks relative to sample 0)
API = "v0"
FROZEN = ["appoint_manager", "build_workshop", "build_farm", "add_order", "add_manager_order", "cancel_order", "enable_automation",
          "create_squad", "equip_squad", "squad_order", "create_burrow", "civilian_alert", "build_door", "build_wall",
          "lock_door", "dig_room", "dig_stairs", "place_furniture", "make_zone", "assign_zone", "advance_days"]
TOOLS = FROZEN + ["slaughter"]
QUERIES = ["stocks", "units", "jobs", "orders", "buildings", "zones", "map", "manager_order_types", "workshop_types"]
WORKSHOP_TYPES = ["Carpenters", "Masons", "Craftsdwarfs", "Still", "Kitchen", "Butchers", "Farmers", "Mechanics"]
# a copy of gameapi/server/rules.py STOP_ON_VALUES (the fakes image has no gameapi/; a test checks they match)
TRIPWIRES = ["hostile_visible", "hostile_approaching", "hostile_near_citizens", "citizen_died", "invasion",
             "water_rising", "announcement"]
ANNOUNCEMENT_TYPES = ["STRANGE_MOOD", "BERSERK_CITIZEN", "CITIZEN_TANTRUM", "POSSESSED_TANTRUM", "CITIZEN_DEATH",
                      "MIGRANT_ARRIVAL", "MIGRANT_ARRIVAL_NAMED", "D_MIGRANTS_ARRIVAL", "D_MIGRANT_ARRIVAL",
                      "CARAVAN_ARRIVAL", "FIRST_CARAVAN_ARRIVAL", "DIPLOMAT_ARRIVAL", "TRADE_DIPLOMAT_ARRIVAL",
                      "MONARCH_ARRIVAL", "NOBLE_ARRIVAL", "MEGABEAST_ARRIVAL", "WEREBEAST_ARRIVAL", "BEAST_AMBUSH",
                      "AMBUSH_DEFENDER", "AMBUSH_RESIDENT", "AMBUSH_THIEF", "AMBUSH_SNATCHER", "AMBUSH_AMBUSHER",
                      "AMBUSH_AMBUSHER_NATURE", "AMBUSH_MISCHIEVOUS", "AMBUSH_OTHER", "CAVE_COLLAPSE"]
STOP_ON_VALUES = TRIPWIRES + [f"announcement:{t}" for t in ANNOUNCEMENT_TYPES]
ORDER_STOCKS = ["drink", "food", "booze", "meals", "logs", "beds", "barrels"]
SCHEMAS = {
    "advance_days": {"type": "object", "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 28},
                                                      "stop_on": {"type": "array", "maxItems": 40,
                                                                  "items": {"type": "string", "enum": STOP_ON_VALUES}}},
                     "required": ["days"]},
    "build_workshop": {"type": "object", "properties": {"type": {"enum": WORKSHOP_TYPES}, "site": {"type": "string"}},
                       "required": ["type"]},
    "add_order": {"type": "object", "properties": {"recipe": {"type": "string"}, "amount": {"type": "integer"},
                                                   "when": {"type": "array"}}, "required": ["recipe", "amount"]},
    "add_manager_order": {"type": "object", "properties": {"job": {"type": "string"}, "reaction": {"type": "string"},
                                                           "amount": {"type": "integer"}, "when": {"type": "array"}},
                          "required": ["job", "amount"]},
    "slaughter": {"type": "object", "properties": {"unit_id": {"type": "integer"}}, "required": ["unit_id"]},
    "place_furniture": {"type": "object", "properties": {"item": {"enum": ["bed", "table", "chair", "door"]},
                                                         "site": {"type": "string"}, "n": {"type": "integer"}},
                        "required": ["item"]},
}
MANUAL = ("Fake game server for runner tests. Tools act on a toy fort: add_order {recipe: brew_drink, amount} brews when a "
          "Still exists; build_farm farms; place_furniture bed|chair houses; build_workshop Craftsdwarfs serves a mood.")


def tool_schema(name):
    params = SCHEMAS.get(name, {"type": "object", "properties": {}, "additionalProperties": True})
    return {"type": "function", "function": {"name": name, "description": f"(fake) {name}", "parameters": params}}


def _rules(cfg):
    r = cfg.get("rules") or {}
    return {"actions_per_game_day": int(r.get("actions_per_game_day", 40)),
            "max_advance_days": int(r.get("max_advance_days", 28)), "wall_s": float(r.get("wall_s", 5400))}


class Game:
    """The toy fort and the v0 rules. Not thread-safe: the HTTP layer holds a lock."""

    def __init__(self, cfg, scenario, sec_per_day=0.0, clock=time.monotonic):
        self.cfg, self.sc = cfg, scenario
        self.clock, self.sec_per_day = clock, sec_per_day
        self.rules = _rules(cfg)
        self.name = scenario.get("name") or "task"
        self.H = int(cfg.get("days") or scenario.get("days") or 60)
        ho = scenario.get("hands_off_days")
        self.A = self.H - int(ho) if ho else None
        self.run = f"{cfg.get('arm', 'harness')}-{int(cfg.get('k', 0))}"
        self.out = cfg.get("artifacts_dir") or "artifacts"
        self.ledger = cfg.get("ledger_path")
        self.t_start = clock()
        self.day, self.actions_today, self.actions_used, self.actions_rejected = 0, 0, 0, 0
        self.game_over, self.finished, self.finished_by, self.wall_capped = False, False, None, False
        self.managed_days = 0
        fam = (scenario.get("family") or "").lower()
        lab = self.name.startswith("lt")
        self.cit = 19 if lab else (30 if fam == "midyear" else 7)
        self.C0 = self.cit
        self.drink = {"drink": 2, "rescue": 0}.get(fam, 300 if not lab else 571)
        self.food = 166 if lab else 250
        self.beds_items = 19 if lab else 0
        self.beds_placed = 0 if lab or fam != "midyear" else 20
        self.seats = 0 if fam != "midyear" else 10
        self.workshops = {"Carpenters", "Still", "Kitchen"} if lab and fam != "rescue" else set()
        if fam == "midyear":
            self.workshops = {"Carpenters", "Still", "Kitchen", "Masons"}
        self.farms, self.brewing, self.cooking = 0, False, False
        self.mood_ws_day, self.artifacts, self.insanities = None, 0, 0
        self.surge = fam == "population"
        self.next_id, self.cit_ids = 100, []
        self.cit_log = []
        for _ in range(self.cit):
            self._add_cit("start")
        self.mood = {"unit_id": self.cit_ids[0], "mood": "Fey", "since": 0} if fam == "mood" else None
        self.dry_days, self.deaths = 0, 0
        self.samples, self.events, self.credit = [], [], []
        self.ev_today = {}
        self.api_log = []
        self.S0 = self._S()
        self._sample()   # sample 0, at load

    # ---- state helpers
    def _add_cit(self, kind):
        self.next_id += 1
        self.cit_ids.append(self.next_id)
        self.cit_log.append({"id": self.next_id, "hf": self.next_id + 1000, "kind": kind, "first_tick": self.tick()})

    def tick(self):
        return T0 + self.day * DAY

    def _event(self, ty, text):
        self.ev_today[ty] = self.ev_today.get(ty, 0) + 1
        self.events.append({"id": len(self.events) + 1, "tick": self.tick(), "type": ty, "text": text})

    def _prog(self):
        pos = ["EXPEDITION_LEADER", "MANAGER"] + (["MAYOR"] if self.cit >= 50 else [])
        return {"fortress_rank": 1 if self.cit >= 20 else 0, "positions": pos, "exported": 0, "king_arrived": False,
                "invasions": {"n": 0, "active": 0, "siege": 0}, "wealth_created": 4000 + 50 * self.day}

    def _home(self):
        return {"beds_placed": self.beds_placed, "dining_seats": self.seats, "bedrooms_owned": self.beds_placed,
                "bedrooms": self.beds_placed}

    def _S(self):
        return {"abs_tick": self.tick(), "prog": self._prog(), "home": self._home(),
                "workshops": [{"type": w, "built": True} for w in sorted(self.workshops)],
                "farm_plots": [{"built": True, "planted": 4} for _ in range(self.farms)],
                "num_artifacts": self.artifacts, "total_insanities": self.insanities,
                "citizens": [{"id": i} for i in self.cit_ids], "total_deaths": self.deaths}

    def _stressed(self):
        return min(self.cit, self.dry_days // 2)

    def _sample(self):
        moods = [] if not self.mood else [{"unit_id": self.mood["unit_id"], "mood": self.mood["mood"]}]
        self.samples.append({
            "abs_tick": self.tick(), "citizens": self.cit, "drink": int(self.drink), "food": int(self.food),
            "beds_placed": self.beds_placed, "beds_items": max(self.beds_items, self.beds_placed),
            "stressed": self._stressed(), "hostiles": 0, "moods": moods, "ev": dict(self.ev_today),
            "home": self._home(), "prog": self._prog(), "in_mood": len(moods),
            "wb": {"needs": {"n": 20 * max(1, self.cit), "unmet": 4 * max(1, self.cit) + 2 * self._stressed()}}})
        self.ev_today = {}

    def _day(self):
        """Simulate one game-day, then take the day's sample."""
        self.day += 1
        if self.surge and self.day in (1, 19):
            for _ in range(20 if self.day == 1 else 8):
                self.cit += 1
                self._add_cit("migrant")
            self._event("MIGRANT_ARRIVAL", "Some migrants have arrived.")
        made = self.cit * 0.9 if (self.brewing and "Still" in self.workshops) else 0
        self.drink = max(0.0, self.drink + made - self.cit * 0.5)
        if made:
            self.credit.append({"ty": "DRINK", "stack": int(made), "credited": True, "tick": self.tick()})
        grown = self.cit * 0.3 * min(self.farms, 2)
        self.food = max(0.0, self.food + grown - self.cit * 0.4)
        self.dry_days = self.dry_days + 1 if self.drink <= 0 else 0
        if self.dry_days >= 10 and self.dry_days % 5 == 0 and self.cit:
            self.cit -= 1
            self.deaths += 1
            gone = self.cit_ids.pop()
            for e in self.cit_log:
                if e["id"] == gone:
                    e["gone"] = "died"
            self._event("CITIZEN_DEATH", "A dwarf has died of thirst.")
        if self.mood:
            d = self.day
            if self.mood_ws_day is not None and self.mood["mood"] == "Fey":
                if d == self.mood_ws_day + 1:
                    self._event("MOOD_BUILDING_CLAIMED", "A dwarf has claimed a Craftsdwarf's Workshop.")
                if d == self.mood_ws_day + 2:
                    self._event("ARTIFACT_BEGUN", "A dwarf has begun a mysterious construction!")
                if d == self.mood_ws_day + 5:
                    self.artifacts += 1
                    self._event("MADE_ARTIFACT", "A dwarf has created an artifact.")
                    self.mood = None
            elif self.mood["mood"] == "Fey" and d >= 30:
                self.mood["mood"] = "Melancholy"
                self.insanities += 1
        if self.cit == 0:
            self._end("fort_lost")
        self._sample()

    def wall_used(self):
        """Wall seconds counted against the cap: elapsed minus the gateway's reported throttle waits."""
        return max(0.0, self.clock() - self.t_start - self.throttle_s())

    def throttle_s(self):
        """The gateway's throttle_wait_total_s (its status file), capped at the game's elapsed wall time (parallel
        calls' waits overlap, contract §6); else the ledger's per-row throttle_wait_s summed."""
        tot = None
        try:
            with open(self.cfg.get("gateway_status_path") or "") as f:
                tot = float(json.load(f).get("throttle_wait_total_s") or 0)
        except (OSError, ValueError, TypeError):
            pass
        if tot is None:
            tot = 0.0
            try:
                with open(self.ledger) as f:
                    for line in f:
                        try:
                            tot += float(json.loads(line).get("throttle_wait_s") or 0)
                        except ValueError:
                            pass
            except (OSError, TypeError):
                pass
        return min(tot, max(0.0, self.clock() - self.t_start))

    def days_left(self):
        return self.H - self.day

    def envelope(self):
        e = {"day": self.day, "tick": self.tick(), "days_left": self.days_left(), "game_over": self.game_over}
        if self.A is not None:
            e["hands_off_in_days"] = max(0, self.A - self.day)
        return e

    # ---- API
    def task(self):
        sc = self.sc
        return {**self.envelope(), "api": API,
                "task": {"name": self.name, "days": self.H, "goal": (sc.get("goal") or "").replace("{days}", str(self.H)),
                         "brief": sc.get("brief"), "hands_off": None if self.A is None else {"from_day": self.A},
                         "strange_moods": bool(self.cfg.get("strange_moods", sc.get("strange_moods", False)))},
                "rules": self.rules, "tools": [tool_schema(t) for t in TOOLS], "queries": QUERIES, "manual": MANUAL}

    def observe(self):
        return {**self.envelope(), "observation": self._obs()}

    def _obs(self):
        """observe2.lua-like keys (contract §3.1), a toy subset."""
        return {"obs_schema": 6, "citizens": self.cit, "stocks": {"drink": int(self.drink),
                "food": int(self.food)}, "beds_placed": self.beds_placed, "dining_seats": self.seats,
                "workshops": sorted(self.workshops), "farms": self.farms, "orders": {"brew_drink": self.brewing},
                "moods": [] if not self.mood else [{"unit_id": self.mood["unit_id"], "mood": self.mood["mood"],
                                                    "job_type": "StrangeMoodCrafter", "claimed_workshop": None,
                                                    "items_needed": [{"type": "WOOD", "quantity": 1, "available": 5}]}],
                "map": {"sites": [{"id": "A1", "kind": "room", "x": 10, "y": 10, "z": 0, "w": 3, "h": 3, "soil": False,
                                   "free": True, "dug": True},
                                  {"id": "S1", "kind": "surface", "x": 20, "y": 10, "z": 1, "w": 3, "h": 3, "soil": True,
                                   "free": True, "dug": False}]},
                "zones": [], "furniture_unzoned": {"bed": self.beds_placed},
                "administrators": {"manager_required_office": self.cit > 20},
                "actions_left_today": self.rules["actions_per_game_day"] - self.actions_today}

    def query(self, name, params):
        if name not in QUERIES:
            return {**self.envelope(), "ok": False, "error_code": "unknown_query", "error": f"no query {name!r}"}
        data = {"stocks": {"drink": int(self.drink), "food": int(self.food), "bed": self.beds_items},
                "units": [{"id": i, "profession": "Peasant"} for i in self.cit_ids[:200]],
                "jobs": [], "orders": [{"recipe": "brew_drink"}] if self.brewing else [],
                "buildings": sorted(self.workshops), "zones": [], "map": {"bounded": True, "tiles": []},
                "manager_order_types": ["brew_drink", "prepare_meal", "make_bed"],
                "workshop_types": WORKSHOP_TYPES}[name]
        return {**self.envelope(), "ok": True, "query": name, "result": data}

    def act(self, tool, args):
        """-> response dict. Enforces the §4 rules in the order: game over, unknown tool, schema, hands-off, K."""
        def err(code, msg):
            self.actions_rejected += 1
            return {**self.envelope(), "ok": False, "error_code": code, "error": msg,
                    "actions_left_today": self.rules["actions_per_game_day"] - self.actions_today}
        if self.game_over:
            return err("game_over", "the game is over")
        if tool not in TOOLS:
            return err("unknown_tool", f"no tool named {tool!r}")
        if not isinstance(args, dict):
            return err("bad_arguments", "args must be an object")
        if tool == "advance_days":
            return self._advance(args, err)
        if self.A is not None and self.day >= self.A:
            return err("hands_off", f"hands-off from day {self.A}")
        if self.actions_today >= self.rules["actions_per_game_day"]:
            return err("action_limit", "K actions reached today: only advance_days until the day changes")
        res = self._apply(tool, args)
        if isinstance(res, str):
            return err("bad_arguments", res)
        self.actions_today += 1
        self.actions_used += 1
        self.managed_days = self.day
        return {**self.envelope(), "ok": True, "result": res,
                "actions_left_today": self.rules["actions_per_game_day"] - self.actions_today}

    def _apply(self, tool, a):
        if tool == "build_workshop":
            ty = a.get("type")
            if ty not in WORKSHOP_TYPES:
                return f"type must be one of {WORKSHOP_TYPES}"
            self.workshops.add(ty)
            if ty == "Craftsdwarfs" and self.mood and self.mood_ws_day is None:
                self.mood_ws_day = self.day
            return {"built": ty}
        if tool in ("add_order", "add_manager_order"):
            key, need = ("recipe", "stock") if tool == "add_order" else ("job", "item_type")
            if not isinstance(a.get(key), str) or not isinstance(a.get("amount"), int):
                return f"{tool} needs {key} and amount"
            for i, c in enumerate(a.get("when") or []):
                if not isinstance(c, dict) or need not in c:
                    return f"{tool} when[{i}] needs {need}"
                if tool == "add_order" and c["stock"] not in ORDER_STOCKS:
                    return f"{tool} when[{i}] stock must be one of {ORDER_STOCKS}"
            r = a[key]
            if "drink" in r or r == "BrewDrink":
                self.brewing = True
            return {"order": r, "queued": True}
        if tool == "build_farm":
            self.farms += 1
            return {"farm": self.farms}
        if tool == "place_furniture":
            item, n = a.get("item"), int(a.get("n") or 1)
            if item == "bed":
                self.beds_placed += n
            elif item in ("chair", "table"):
                self.seats += n if item == "chair" else 0
            else:
                return "item must be bed, table, chair or door"
            return {"placed": item, "n": n}
        if tool == "slaughter":
            if not isinstance(a.get("unit_id"), int):
                return "unit_id must be an integer"
            return {"marked": a["unit_id"]}
        return {"done": tool}

    def _advance(self, a, err):
        n = a.get("days")
        if not isinstance(n, int) or not 1 <= n <= self.rules["max_advance_days"]:
            return err("bad_arguments", f"days must be an integer 1..{self.rules['max_advance_days']}")
        bad = [x for x in a.get("stop_on") or [] if x not in STOP_ON_VALUES]
        if bad:
            return err("bad_arguments", f"stop_on values must be among {STOP_ON_VALUES}; got {bad}")
        stop_on = set(a.get("stop_on") or STOP_ON_VALUES)
        target = min(self.H, self.day + n)
        if self.A is not None and self.day < self.A:
            target = min(target, self.A)       # advances are cut at the start of the hands-off window
        stopped, ran = None, 0
        while self.day < target and not self.game_over:
            if self.wall_used() > self.rules["wall_s"]:
                self.wall_capped = True
                self._end("wall_cap")
                stopped = "wall_cap"
                break
            if self.sec_per_day:
                time.sleep(self.sec_per_day)
            cit0 = self.cit
            self._day()
            ran += 1
            if "citizen_died" in stop_on and self.cit < cit0:
                stopped = "citizen_died"
            elif ({"announcement", "announcement:MIGRANT_ARRIVAL"} & stop_on) and self.surge and self.day in (1, 19):
                stopped = "announcement:MIGRANT_ARRIVAL"
            if stopped:
                break
        self.actions_today = 0 if ran else self.actions_today
        if self.day >= self.H and not self.game_over:
            self._end("horizon")
        if not stopped and self.A is not None and self.day == self.A and ran:
            stopped = "hands_off"
        why = stopped or (self.finished_by if self.game_over and self.finished_by != "horizon" else None)
        return {**self.envelope(), "ok": True, "result": {
                    "advanced_ticks": ran * DAY, "days_run": ran,
                    "stopped": None if not why else {"reason": why, "detail": None, "after_ticks": ran * DAY}},
                "actions_left_today": self.rules["actions_per_game_day"]}

    def finish(self, why="harness_exit"):
        """The harness has exited (or its credits ran out): run the rest of the horizon with no actions."""
        if not self.game_over:
            while self.day < self.H and not self.game_over:
                if self.wall_used() > self.rules["wall_s"]:
                    self.wall_capped = True
                    self._end("wall_cap")
                    break
                self._day()
            if not self.game_over:
                self._end(why)
        return {**self.envelope(), "ok": True, "phase": "finalized" if self.finished else "ready", "ready": True,
                "finished": self.finished, "finished_by": self.finished_by}

    def _end(self, why):
        self.game_over, self.finished_by = True, why
        self.write_artifacts()
        self.finished = True

    def health(self):
        return {**self.envelope(), "ok": True, "phase": "finalized" if self.finished else "ready", "ready": True,
                "finished": self.finished, "finished_by": self.finished_by}

    # ---- artifacts (§6)
    def write_artifacts(self):
        os.makedirs(self.out, exist_ok=True)
        stem = os.path.join(self.out, self.run)
        S = self._S()
        daily = {"samples": self.samples, "cit_log": self.cit_log, "hist_deaths": [], "S0": self.S0, "S": S,
                 "events": {}}
        json.dump(daily, open(stem + ".daily.json", "w"))
        json.dump({"items": self.credit}, open(stem + ".credit.json", "w"))
        z = {"citizen_deaths": 0, "invaders_killed": 0, "invaders_alive": 0}
        json.dump({"F0": z, "F": {**z, "citizen_deaths": self.deaths}}, open(stem + ".final.json", "w"))
        with open(stem + ".api.jsonl", "w") as f:
            for e in self.api_log:
                f.write(json.dumps(e) + "\n")
        row = {"arm": self.cfg.get("arm", "harness"), "k": int(self.cfg.get("k", 0)), "crashed": None,
               "wall_s": round(self.clock() - self.t_start, 1), "scenario": self.name, "days_played": float(self.day),
               "days_target": self.H, "hands_off_from_day": self.A, "pop_start": self.C0, "pop_final": self.cit,
               "citizen_deaths": self.deaths, "invaders_alive_final": 0, "survived_horizon": self.cit > 0,
               "drink_final": int(self.drink), "food_final": int(self.food),
               "api": API, "key": self.cfg.get("key") or "dfbench/v3|fake", "harness_digest": self.cfg.get("harness_digest"),
               "run_id": self.cfg.get("run_id"), "seed": self.cfg.get("seed"), "wall_capped": self.wall_capped,
               "actions_used": self.actions_used, "actions_rejected": self.actions_rejected,
               "finished_by": self.finished_by, "managed_until_day": self.managed_days,
               "throttle_excluded_s": round(self.throttle_s(), 1), "fake": True}
        with open(os.path.join(self.out, "summary.jsonl"), "a") as f:
            f.write(json.dumps(row) + "\n")


class Handler(BaseHTTPRequestHandler):
    game, lock = None, threading.Lock()

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _handle(self, method):
        t = time.monotonic()
        u = urlparse(self.path)
        body = None
        if method == "POST":
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                return self._send(400, {"ok": False, "error_code": "bad_arguments", "error": "body is not JSON"})
        g = self.game
        with self.lock:
            code, out = 200, None
            p = u.path.rstrip("/") or "/"
            if method == "GET" and p == "/health":
                return self._send(200, g.health())          # not logged: the runner polls it
            elif method == "GET" and p == "/task":
                out = g.task()
            elif method == "GET" and p == "/observe":
                out = g.observe()
            elif method == "GET" and p.startswith("/query/"):
                out = g.query(p[len("/query/"):], {k: v[0] for k, v in parse_qs(u.query).items()})
                code = 200 if out.get("ok") else 404
            elif method == "GET" and p == "/events":
                since = int((parse_qs(u.query).get("since_tick") or ["0"])[0])
                out = {**g.envelope(), "events": [e for e in g.events if e["tick"] > since][-500:]}
            elif method == "POST" and p == "/act":
                if not isinstance(body, dict) or not isinstance(body.get("tool"), str):
                    out = {**g.envelope(), "ok": False, "error_code": "bad_arguments", "error": "need {tool, args}"}
                else:
                    out = g.act(body["tool"], body.get("args") if "args" in body else {})
            elif method == "POST" and p == "/finish":
                out = g.finish((body or {}).get("reason") or "harness_exit")
            else:
                code, out = 404, {"ok": False, "error_code": "not_found", "error": u.path}
            g.api_log.append({"tick": g.tick(), "method": method, "path": u.path, "request": body, "response": out,
                              "latency_ms": round(1000 * (time.monotonic() - t), 2)})
        self._send(code, out)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8090)
    a = ap.parse_args()
    cfg = json.loads(os.environ.get("DFBENCH_GAME") or "{}")
    sc = json.load(open(cfg.get("scenario_path") or "/dfbench/scenario.json"))
    Handler.game = Game(cfg, sc, sec_per_day=float(os.environ.get("FAKE_SEC_PER_DAY", "0.01")))
    print(f"fake game {sc.get('name')} H={Handler.game.H} on :{a.port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
