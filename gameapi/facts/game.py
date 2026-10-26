"""The facts layer of game API v0: observation, queries, tools and events for one game (docs/GAME-API.md §5).

    g = Game()                      # or Game(df=DFHack(df_dir)) / Game(df=<fake>) in tests
    g.observe() -> dict             # obs schema 6, facts only; refreshes the site state
    g.query(name, **args) -> dict   # read-only, bounded
    g.tools() -> list               # OpenAI function schemas (build_workshop's enum from DF)
    g.act(tool, args) -> dict       # {"ok": true, "result": {...}} | {"ok": false, "error_code", "error", ...}
    g.events(since_tick) -> list    # DF reports after a tick, oldest first, bounded

One Game per game: it holds the site ids and the order bookkeeping. The server owns the rules (K actions per day,
hands-off, wall cap) and advance_days; Game.act refuses advance_days (error_code server_tool).
"""
import os
import re

from . import tools as T
from .dfhack import LUA_DIR, DFHack, compact, lua_json
from .sites import SiteState

OBS_SCHEMA = 7
API_VERSION = "v0"
# result fields that are advice, never returned (bench/ablate.py's INT set for results)
ADVICE_KEYS = {"hint", "note", "reminder", "warning", "valid", "valid_tools", "nearest_free_centre", "short"}
# free text -> stable error_code, for errors that come without one (harness2.ERROR_CODES)
ERROR_CODES = [
    (r"already has a building|occupied", "tile_occupied"), (r"not soil floor", "not_soil_floor"),
    (r"designated 0 tiles|designated nothing", "nothing_designated"),
    (r"fire-safe", "needs_stone"), (r"no usable building material|no free .* item|no .* item", "no_material"),
    (r"already holds a position|already assigned", "already_assigned"), (r"no order with id", "no_such_order"),
    (r"no squad", "no_squad"), (r"no free floor tile|could not place|no suitable tiles", "no_space"),
    (r"not built|unbuilt", "not_built"), (r"unknown|not allowed|allowlist", "bad_arguments"),
    (r"must be|expected|unexpected arguments|integer", "bad_arguments"),
]
QUERIES = {   # name -> {arg: (type, lo, hi)}; every query also takes `limit` within its bound
    "stocks": {"item_type": (str,), "limit": (int, 1, 1000)},
    "units": {"kind": (str,), "id": (int, 0, 10**7), "limit": (int, 1, 300)},
    "jobs": {"limit": (int, 1, 500)},
    "orders": {"limit": (int, 1, 500)},
    "buildings": {"type": (str,), "limit": (int, 1, 1000)},
    "zones": {"limit": (int, 1, 1000)},
    "map": {"x": (int, 0, 400), "y": (int, 0, 400), "z": (int, 0, 300), "z2": (int, 0, 300), "radius": (int, 0, 20)},
    "manager_order_types": {},
    "workshop_types": {},
}
EMPTY_OBJECTS = ("dig_pending_by_z", "furniture_unzoned")   # Lua prints an empty table as []; these are objects


class FactsError(RuntimeError):
    """The observation probe failed as a whole (DF not answering, script error)."""


def _err(code, msg, **extra):
    d = {"ok": False, "error_code": code, "error": msg}
    d.update({k: v for k, v in extra.items() if v is not None})
    return d


def classify(d):
    """Make any failure dict a structured error: advice removed, error_code set."""
    d = {k: v for k, v in d.items() if k not in ADVICE_KEYS}
    d["ok"] = False
    msg = str(d.get("error") or "")
    if not d.get("error_code"):
        d["error_code"] = next((c for p, c in ERROR_CODES if re.search(p, msg, re.I)), "failed")
    d.setdefault("error", d["error_code"])
    return d


def success(d):
    return {"ok": True, "result": {k: v for k, v in d.items() if k != "ok" and k not in ADVICE_KEYS}}


class Game:
    def __init__(self, df=None):
        self.df = df or DFHack()
        self.sites = SiteState()
        self.order_meta = {}    # order id -> {"recipe", "stocks"} for orders made by add_order
        self.first_seen = {}    # order id -> abs tick first seen (observe or add_order)
        self._tools = None
        self._ws_names = None
        self._last_tick = None

    # ------------------------------------------------------------------ observation
    def _probe(self, section):
        o = lua_json(self.df, "observe.lua", section, compact(self.sites.boxes()))
        if o.get("ok") is False or "date" not in o:
            raise FactsError(o.get("error") or "observation probe returned no date")
        tick = (o.get("date") or {}).get("abs_tick")
        if isinstance(tick, int):
            if self._last_tick is not None and tick < self._last_tick:   # a new game from the same save: start over
                self.sites.reset(); self.order_meta.clear(); self.first_seen.clear()
            self._last_tick = tick
        self.sites.update(o.pop("site_candidates", None) or {}, o.get("farm_plots") or [],
                          o.get("zones") if isinstance(o.get("zones"), list) else [], o.pop("box_facts", None) or {})
        return o

    def refresh_sites(self):
        """Re-read the site candidates (cheap probe section); act() does this before resolving a site."""
        self._probe("sites")

    def observe(self):
        o = self._probe("all")
        tick = o["date"].get("abs_tick")
        for k in EMPTY_OBJECTS:
            if o.get(k) == []:
                o[k] = {}
        threats = o.get("threats")
        if isinstance(threats, dict) and threats.get("by_race") == []:
            threats["by_race"] = {}
        stocks = o.get("stocks")
        if isinstance(stocks, dict):
            for k in ("plants_by_kind", "seeds_by_kind"):
                if stocks.get(k) == []:
                    stocks[k] = {}
        for z in o.get("zones") if isinstance(o.get("zones"), list) else []:
            if z.get("furniture") == []:
                z["furniture"] = {}
        for m in o.get("moods") if isinstance(o.get("moods"), list) else []:
            for x in m.get("items_needed") or []:
                x.setdefault("quantity", None)   # the primary material's count isn't shown in DF
        if isinstance(o.get("orders"), list):
            for od in o["orders"]:
                for c in od.get("when") or []:   # contract §3.1: {item_type, flags, test, value} always present
                    c.setdefault("item_type", None)
                    c.setdefault("flags", [])
                self._annotate_order(od, tick)
        if isinstance(o.get("map"), dict):
            o["map"]["sites"] = self.sites.listing()   # contract §3.1: map.sites
        o["plugins"] = self.plugin_state()
        o["schema"] = OBS_SCHEMA
        return o

    def _annotate_order(self, od, tick, conds="when"):
        """Interface facts the server knows: recipe name (reverse map), the stock names add_order used, first seen."""
        oid = od.get("id")
        recipe = T.recipe_of(od)
        if recipe:   # contract §3.1: present when the order matches a frozen recipe (job/reaction are always there)
            od["recipe"] = recipe
        meta = self.order_meta.get(oid)
        if meta and od.get(conds):
            for c, s in zip(od[conds], meta.get("stocks") or []):
                if s:
                    c["stock"] = s
        if isinstance(tick, int) and oid is not None:
            # DF keeps no creation tick: the tick add_order made it, else the first observation that saw it
            od["created_tick"] = self.first_seen.setdefault(oid, tick)

    def plugin_state(self):
        out = self.df.run("enable")
        st = {}
        for name in T.AUTOMATION:
            m = re.search(rf"\b{name}:\s+(on|off)", out)
            st[name] = m.group(1) if m else "unknown"
        return st

    # ------------------------------------------------------------------ queries
    def query(self, name, **args):
        spec = QUERIES.get(name)
        if spec is None:
            return _err("unknown_query", f"no query named {name!r}", allowed=sorted(QUERIES))
        for k, v in args.items():
            if k not in spec:
                return _err("bad_arguments", f"{name} takes no argument {k!r}", allowed=sorted(spec))
            t = spec[k]
            if t[0] is int:
                if isinstance(v, str) and re.fullmatch(r"-?\d+", v):   # query strings arrive as text
                    v = args[k] = int(v)
                if not isinstance(v, int) or isinstance(v, bool) or not t[1] <= v <= t[2]:
                    return _err("bad_arguments", f"{k} must be an integer in [{t[1]},{t[2]}]")
            elif not isinstance(v, str) or not 0 < len(v) <= 64:
                return _err("bad_arguments", f"{k} must be a name")
        r = lua_json(self.df, "query.lua", name, compact(args))
        if r.get("ok") is False:
            return classify(r)
        if name == "orders":
            for od in r.get("orders") or []:
                self._annotate_order(od, self._last_tick, conds="item_conditions")
        elif name == "manager_order_types":
            r["recipes"] = {k: v["order"] for k, v in sorted(T.RECIPES.items())}
            r["when_stocks"] = T.ORDER_STOCKS
        return r

    # ------------------------------------------------------------------ tools
    def workshop_type_names(self):
        """build_workshop's enum, from DF (cached per game; None if DF can't say)."""
        if self._ws_names is None:
            r = self.query("workshop_types")
            if r.get("ok"):
                self._ws_names = [w["type"] for w in r.get("workshop_types") or []]
        return self._ws_names

    def tools(self):
        if self._tools is None:
            self._tools = T.tool_schemas(self.workshop_type_names())
        return self._tools

    def act(self, tool, args):
        """One action. {"ok": true, "result": {...}} or {"ok": false, "error_code", "error", ...}."""
        if tool not in T.TOOL_NAMES:
            return _err("unknown_tool", f"no tool named {tool!r}", allowed=sorted(T.TOOL_NAMES))
        if tool in T.SERVER_TOOLS:
            return _err("server_tool", f"{tool} is run by the game server, not the facts layer")
        if not isinstance(args, dict):
            return _err("bad_arguments", "arguments must be a JSON object")
        schema = next(t for t in self.tools() if t["function"]["name"] == tool)["function"]["parameters"]
        allowed = set(schema["properties"])
        if tool in T.SITE_KINDS:   # raw coordinates still work (frozen behaviour, not advertised)
            allowed |= {"x", "y", "z", "w", "h", "z_top"}
        extra = set(args) - allowed
        if extra:
            return _err("bad_arguments", f"{tool} takes no argument {', '.join(sorted(extra))} "
                                         f"(it takes: {', '.join(sorted(schema['properties']))})")
        for key in ("kind", "type"):   # check enums before the location (frozen order for kind)
            enum = (schema["properties"].get(key) or {}).get("enum")
            if enum and key in args and args[key] not in enum:
                return _err("bad_arguments", f"unknown {key} {args[key]!r}", allowed=enum)
        try:
            if "site" in args:
                self.refresh_sites()
            a, e = self.sites.resolve(tool, args)
            if e:
                return e
            r = getattr(self, "_t_" + tool)(a)
        except T.Invalid as e:
            return _err("bad_arguments", str(e), allowed=e.allowed)
        except T.Rejected as e:
            return _err("bad_arguments", str(e))
        except FactsError as e:
            return _err("internal_error", str(e))
        return success(r) if r.get("ok") else classify(r)

    def _lua(self, *args):
        return lua_json(self.df, "act.lua", *args)

    def _xyz(self, a):
        return [str(T.as_int(a, "x", 0, 400)), str(T.as_int(a, "y", 0, 400)), str(T.as_int(a, "z", 0, 300))]

    def _quickfort(self, name, blueprint, x, y, z):
        self.df.write_blueprint(name, blueprint)
        return self.df.run("quickfort", "run", name, "-c", f"{x},{y},{z}", with_stderr=True)

    def _t_appoint_manager(self, a):
        extra = [str(T.as_int(a, "dwarf_id", 0, 10**7))] if "dwarf_id" in a else []
        return self._lua("assign_manager", *extra)

    def _t_build_workshop(self, a):
        enum = self.workshop_type_names() or T.FROZEN_WORKSHOPS
        if a.get("type") not in enum:
            raise T.Invalid("workshop type", a.get("type"), enum)
        return self._lua("build_workshop", a["type"], *self._xyz(a))

    def _t_build_farm(self, a):
        w, h = T.opt_int(a, "w", 1, 10, 3), T.opt_int(a, "h", 1, 10, 3)
        return self._lua("build_farm", *self._xyz(a), str(w), str(h))

    def _t_add_order(self, a):
        return self._queue(*T.order_spec(a))

    def _t_add_manager_order(self, a):
        return self._queue(*T.manager_order_spec(a))

    def _queue(self, spec, meta):
        r = self._lua("add_order", compact(spec))
        if r.get("ok") and r.get("order_id") is not None:
            self.order_meta[r["order_id"]] = meta
            if self._last_tick is not None:
                self.first_seen.setdefault(r["order_id"], self._last_tick)
            if meta.get("recipe"):
                r["recipe"] = meta["recipe"]
        return r

    def _t_cancel_order(self, a):
        return self._lua("cancel_order", str(T.as_int(a, "order_id", 0, 10**6)))

    def _t_create_squad(self, a):
        ids = a.get("dwarf_ids")
        if ids is not None:
            if (not isinstance(ids, list) or not 1 <= len(ids) <= 10 or len(set(map(str, ids))) != len(ids)
                    or not all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i <= 10**7 for i in ids)):
                raise T.Rejected("dwarf_ids must be 1-10 distinct citizen ids")
            return self._lua("create_squad", str(len(ids)), *map(str, ids))
        return self._lua("create_squad", str(T.opt_int(a, "size", 1, 10, 4)))

    def _t_equip_squad(self, a):
        if a.get("uniform") not in T.UNIFORMS:
            raise T.Invalid("uniform", a.get("uniform"), T.UNIFORMS)
        return self._lua("equip_squad", a["uniform"])

    def _t_squad_order(self, a):
        order = a.get("order")
        if order == "attack":
            ids = a.get("target_ids") or []
            if not isinstance(ids, list) or len(ids) > 20 or not all(
                    isinstance(i, int) and not isinstance(i, bool) and 0 <= i <= 10**7 for i in ids):
                raise T.Rejected("target_ids must be up to 20 unit ids")
            return self._lua("squad_order", "attack", *map(str, ids))
        if order == "station":
            return self._lua("squad_order", "station", *self._xyz(a))
        if order == "stand_down":
            return self._lua("squad_order", "stand_down")
        raise T.Invalid("order", order, ("attack", "station", "stand_down"))

    def _t_create_burrow(self, a):
        x, y, z = (T.as_int(a, "x", 0, 400), T.as_int(a, "y", 0, 400), T.as_int(a, "z", 0, 300))
        w, h = T.as_int(a, "w", 1, 40) if "w" in a else 1, T.as_int(a, "h", 1, 40) if "h" in a else 1
        levels = T.opt_int(a, "levels", 1, 5, 1)
        if z - levels + 1 < 0:
            raise T.Rejected("levels go below the map")
        first = f"a{{name=Shelter create=true civalert=true}}({w}x{h})"
        out = self._quickfort("gameapi_burrow.csv", "#burrow start(1;1)\n" + "\n#>\n".join([first] * levels) + "\n", x, y, z)
        m = re.search(r"Burrow tiles added: (\d+)", out)
        added = int(m.group(1)) if m else 0
        if not added:
            return {"ok": False, "error_code": "nothing_designated", "error": "no tiles added to the burrow",
                    "detail": out[-200:]}
        return {"ok": True, "burrow": "Shelter", "tiles_added": added, "created": "Burrows created: 1" in out}

    def _t_civilian_alert(self, a):
        if not isinstance(a.get("on"), bool):
            raise T.Rejected("on must be true or false")
        return self._lua("civ_alert", "on" if a["on"] else "off")

    def _t_build_door(self, a):
        if a.get("kind") not in ("door", "hatch"):
            raise T.Invalid("kind", a.get("kind"), ("door", "hatch"))
        return self._lua("build_door", a["kind"], *self._xyz(a))

    def _t_build_wall(self, a):
        return self._lua("build_wall", *self._xyz(a))

    def _t_lock_door(self, a):
        if not isinstance(a.get("locked"), bool):
            raise T.Rejected("locked must be true or false")
        extra = [str(T.as_int(a, "door_id", 0, 10**7))] if "door_id" in a else []
        return self._lua("lock_door", "on" if a["locked"] else "off", *extra)

    def _dig(self, steps):
        """steps: [(blueprint, 'x,y,z')] -> per-step designated counts (quickfort #dig)."""
        out = []
        for bp, at in steps:
            x, y, z = at.split(",")
            r = self._quickfort("gameapi_dig.csv", bp, x, y, z)
            m = re.search(r"designated for digging: (\d+)", r)
            out.append({"at": at, "tiles": int(m.group(1)) if m else 0})
        return out

    def _dig_result(self, steps, **extra):
        zero = [s["at"] for s in steps if s["tiles"] == 0]
        if zero:
            return {"ok": False, "error_code": "nothing_designated",
                    "error": f"{len(zero)} step(s) designated nothing at {', '.join(zero)}", "steps": steps, **extra}
        return {"ok": True, "designated": sum(s["tiles"] for s in steps), "steps": steps, **extra}

    def _t_dig_room(self, a):
        x, y, z = (T.as_int(a, "x", 0, 400), T.as_int(a, "y", 0, 400), T.as_int(a, "z", 0, 300))
        w, h = T.as_int(a, "w", 1, T.MAX_DIM), T.as_int(a, "h", 1, T.MAX_DIM)
        # never overwrite a stair: a room dug over its own access stair becomes unreachable (frozen dig_room)
        plan = self.df.run("lua", "-f", os.path.join(LUA_DIR, "digplan.lua"), x, y, z, w, h)
        keep = set(plan.split("KEEP", 1)[-1].split()) if "KEEP" in plan else set()
        rows = [",".join("" if f"{dx},{dy}" in keep else "d" for dx in range(w)) for dy in range(h)]
        steps = self._dig([("#dig start(1;1)\n" + "\n".join(rows) + "\n", f"{x},{y},{z}")])
        return self._dig_result(steps, kept_stair_tiles=len(keep))

    def _t_dig_stairs(self, a):
        x, y = T.as_int(a, "x", 0, 400), T.as_int(a, "y", 0, 400)
        zt, zb = T.as_int(a, "z_top", 0, 300), T.as_int(a, "z_bottom", 0, 300)
        if not 0 < zt - zb <= 20:
            raise T.Rejected("z_top must be 1..20 levels above z_bottom")
        steps = [("#dig start(1;1)\nj\n", f"{x},{y},{zt}")]
        steps += [("#dig start(1;1)\ni\n", f"{x},{y},{z}") for z in range(zt - 1, zb, -1)]
        steps += [("#dig start(1;1)\nu\n", f"{x},{y},{zb}")]
        return self._dig_result(self._dig(steps))

    def _t_place_furniture(self, a):
        kind = a["kind"]
        box = self._xyz(a) + [str(T.as_int(a, k, 1, 40) if k in a else 1) for k in ("w", "h")]
        count = T.opt_int(a, "count", 1, 30, 1)
        r = lua_json(self.df, "place.lua", kind, *box, str(min(400, 4 * count + 8)))
        if not r.get("ok"):
            return r
        placed, rejected, detail = [], 0, ""
        want = min(count, r.get("available", count))
        for x, y, z in r.get("tiles") or [[r["x"], r["y"], r["z"]]]:
            if len(placed) >= want:
                break
            out = self._quickfort("gameapi_place.csv", f"#build\n{T.FURNITURE[kind]}\n", x, y, z)
            n = re.search(r"Buildings designated: (\d+)", out)
            if n and int(n.group(1)) > 0:
                placed.append([x, y, z])
            else:
                rejected += 1
                detail = out[-160:]
        if not placed:
            return {"ok": False, "error_code": "no_space", "detail": detail,
                    "error": f"could not place a {kind}: the game refused {rejected} free-looking tile(s) in the box"}
        return {"ok": True, "placed": kind, "n": len(placed), "requested": count, "available": r.get("available"),
                "at": placed if count > 1 else placed[0], "tiles_rejected": rejected}

    def _t_make_zone(self, a):
        x, y, z = (T.as_int(a, "x", 0, 400), T.as_int(a, "y", 0, 400), T.as_int(a, "z", 0, 300))
        w, h = T.opt_int(a, "w", 1, 20, 3), T.opt_int(a, "h", 1, 20, 3)
        key = T.ZONES[a["kind"]]
        out = self._quickfort("gameapi_zone.csv", "#zone\n" + "\n".join([",".join([key] * w)] * h) + "\n", x, y, z)
        n = re.search(r"Zones designated: (\d+)", out)
        t = re.search(r"Zone tiles designated: (\d+)", out)
        if not (n and int(n.group(1)) > 0):
            return {"ok": False, "error_code": "no_space", "error": "no zone made: no suitable tiles", "detail": out[-160:]}
        return {"ok": True, "zone": a["kind"], "tiles": int(t.group(1)) if t else None, "at": [x, y, z, w, h],
                "zone_id": self._lua("zone_at", str(x), str(y), str(z)).get("zone_id")}

    def _t_assign_zone(self, a):
        return self._lua("assign_zone", str(T.as_int(a, "zone_id", 0, 10**7)), str(T.as_int(a, "dwarf_id", 0, 10**7)))

    def _t_enable_automation(self, a):
        if a.get("name") not in T.AUTOMATION:
            raise T.Invalid("automation", a.get("name"), T.AUTOMATION)
        before = self.plugin_state().get(a["name"])
        self.df.run("enable", a["name"])
        after = self.plugin_state().get(a["name"])
        r = {"ok": after == "on", "name": a["name"], "was": before, "now": after}
        if after != "on":
            r.update(error_code="not_enabled", error=f"{a['name']} did not turn on (now {after})")
        return r

    def _t_slaughter(self, a):
        return self._lua("slaughter", str(T.as_int(a, "unit_id", 0, 10**7)))

    # ------------------------------------------------------------------ events
    def events_page(self, since_tick=0, limit=200, since_id=None):
        """{"events": [...], "dropped": n, "now": tick}: at most `limit` (newest kept when more match)."""
        if not isinstance(since_tick, int) or isinstance(since_tick, bool) or since_tick < 0:
            return _err("bad_arguments", "since_tick must be a non-negative integer")
        limit = max(1, min(1000, int(limit)))
        args = [str(since_tick), str(limit)] + ([str(int(since_id))] if since_id is not None else [])
        r = lua_json(self.df, "events.lua", *args)
        if r.get("ok") is False:
            return classify(r)
        r.pop("ok", None)
        return r

    def events(self, since_tick=0, limit=200):
        """DF's reports after since_tick: [{id, tick, type, text, announcement, repeat_count?, x?, y?, z?}]."""
        r = self.events_page(since_tick, limit)
        if r.get("ok") is False:
            raise FactsError(r.get("error"))
        return r.get("events") or []
