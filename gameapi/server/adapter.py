"""The facts adapter: the one place the game server touches the facts layer (contract docs/GAME-API.md §3.2, §5).

The server codes against this interface only:

    facts.reset()                         new game: forget site ids and any per-game tracking
    facts.tools()      -> [schema]        OpenAI function schemas (any advance_days is replaced by the server's)
    facts.key_tools()  -> [schema]        the schemas the v3 key hashes (no DF needed: static enums)
    facts.queries()    -> [{"name", "description", "params"}]
    facts.manual()     -> str             reference text: tools and observation facts, no advice (gameapi/manual/MANUAL.md)
    facts.observe()    -> dict            facts only (obs schema 6)
    facts.query(name, **params) -> dict   read-only; KeyError for an unknown query, TypeError for bad params
    facts.act(tool, args) -> {"ok": True, "result": ...} | {"ok": False, "error_code": str, "error": str, ...}
    facts.events(since_tick) -> {"events": [{"id", "tick", "type", "text", ...}], ...}
    facts.OBS_SCHEMA, facts.NAME, facts.STRICT_ARGS (the server rejects undeclared arguments itself)
    facts.KEY_TOOL_FILES, facts.KEY_OBS_FILES   repo-relative files the v3 key hashes

`load()` returns `Facts` (over gameapi/facts, merged 2026-10-23) when that package imports, else `Legacy`: the
temporary adapter over harness2.observe()/act() with the interpretation stripped. `--facts legacy|facts` forces one.
"""
import glob, importlib, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
MANUAL_PATH = os.path.join(ROOT, "gameapi", "manual", "MANUAL.md")   # contract §3: what /task serves as `manual`


def reference_manual():
    """The game API's reference manual (the frozen MANUAL minus its advice, for the season-0 surface), verbatim."""
    with open(MANUAL_PATH, encoding="utf-8") as f:
        return f.read()

# interpretation the contract moves to the baseline harness (§5): dropped wherever it appears in a legacy result
ADVICE_KEYS = {"hint", "note", "reminder", "warning", "nearest_free_centre", "stuck_because", "shares_inputs",
               "manager_needs_office", "workshop_needed"}


def strip_advice(x):
    if isinstance(x, dict):
        return {k: strip_advice(v) for k, v in x.items() if k not in ADVICE_KEYS}
    if isinstance(x, list):
        return [strip_advice(v) for v in x]
    return x


def facts_available():
    return os.path.exists(os.path.join(ROOT, "gameapi", "facts", "game.py"))


def load(prefer=None):
    """-> the facts implementation. prefer: "legacy" | "facts" | None (gameapi/facts when present)."""
    prefer = prefer or os.environ.get("GAMEAPI_FACTS") or None
    if prefer == "auto":
        prefer = None
    if prefer == "facts" or (prefer is None and facts_available()):
        return Facts()
    return Legacy()


def key_files(prefer=None):
    """-> (name, tool files, obs files) for bench/key.py, without importing DF-side code."""
    if prefer == "facts" or (prefer != "legacy" and facts_available()):
        return Facts.NAME, Facts.key_tool_files(), Facts.key_obs_files()
    return Legacy.NAME, list(Legacy.KEY_TOOL_FILES), list(Legacy.KEY_OBS_FILES)


class Facts:
    """gameapi.facts.Game, one per game."""
    NAME = "gameapi.facts"
    OBS_SCHEMA = None        # the facts layer's (gameapi.facts.OBS_SCHEMA), set below so it can't drift
    STRICT_ARGS = False      # Game.act checks arguments itself (and still takes raw x,y,z on site tools, frozen)

    @staticmethod
    def _rel(paths):
        return sorted(os.path.relpath(p, ROOT) for p in paths)

    @classmethod
    def key_tool_files(cls):
        """What the tools do: the facts layer's Python (minus its in-game check) and its Lua, the served manual, plus
        this adapter."""
        d = os.path.join(ROOT, "gameapi", "facts")
        py = [p for p in glob.glob(os.path.join(d, "*.py")) if not os.path.basename(p).startswith("check_in_game")]
        return cls._rel(py + glob.glob(os.path.join(d, "lua", "*.lua")) + [MANUAL_PATH]) + ["gameapi/server/adapter.py"]

    key_obs_files = key_tool_files   # one package: observe/query/events share game.py, sites.py and common.lua

    def __init__(self):
        sys.path.insert(0, ROOT)
        self.F = importlib.import_module("gameapi.facts")
        self.g = None
        self.reset()

    def reset(self):
        self.g = self.F.Game(df=self.F.DFHack())

    def tools(self):
        return [t for t in self.g.tools() if t["function"]["name"] not in self.F.SERVER_TOOLS]

    def key_tools(self):
        return [t for t in self.F.tool_schemas() if t["function"]["name"] not in self.F.SERVER_TOOLS]

    def queries(self):
        out = []
        for name, spec in self.F.QUERIES.items():
            params = {k: ({"type": "integer", "minimum": t[1], "maximum": t[2]} if t[0] is int else {"type": "string"})
                      for k, t in spec.items()}
            out.append({"name": name, "description": f"read-only query {name} (gameapi/facts README, Queries)",
                        "params": params})
        return out

    def manual(self):
        """gameapi/manual/MANUAL.md: tools, observation, queries, events and rules as facts, no advice."""
        return reference_manual()

    def observe(self):
        return self.g.observe()

    def query(self, name, **params):
        r = self.g.query(name, **params)
        if r.get("ok") is False:
            if r.get("error_code") == "unknown_query":
                raise KeyError(name)
            if r.get("error_code") == "bad_arguments":
                raise TypeError(r.get("error"))
        return r

    def act(self, tool, args):
        return self.g.act(tool, args)

    def events(self, since_tick):
        r = self.g.events_page(since_tick)
        if r.get("ok") is False:
            raise TypeError(r.get("error"))
        return r


class Legacy:
    """harness2's observation and tools, minus the interpretation layer. Needs a running DF (imports harness2)."""
    OBS_SCHEMA = "6-legacy"
    NAME = "legacy-harness2"
    STRICT_ARGS = True
    # files whose code defines what the tools do and what the observation says (bench/key.py v3 reads these names)
    KEY_TOOL_FILES = ("harness2.py", "harness.py", "act2.lua", "place.lua", "digplan.lua", "wo_lib.lua",
                      "gameapi/server/adapter.py")
    KEY_OBS_FILES = ("observe2.lua", "harness2.py", "gameapi/server/legacy_events.lua", "gameapi/server/adapter.py")

    def __init__(self):
        sys.path.insert(0, ROOT)
        self.H2 = importlib.import_module("harness2")

    def reset(self):
        self.H2.reset_tracking()

    def tools(self):
        return [t for t in self.H2.TOOLS if t["function"]["name"] != "advance_days"]

    key_tools = tools

    QUERIES = {"stocks": "stock counts (the observation's stocks block)",
               "units": "citizens: professions, jobs, stress, positions (the observation's dwarves and military)",
               "jobs": "per-citizen current jobs (dwarves[].job)",
               "orders": "work orders with their conditions",
               "buildings": "workshops, farm plots, doors",
               "zones": "zones with owners and furniture",
               "workshop_types": "workshop types build_workshop accepts",
               "manager_order_types": "recipes add_order accepts"}

    def queries(self):
        return [{"name": n, "description": d, "params": {}} for n, d in self.QUERIES.items()]

    def manual(self):
        return self.H2.MANUAL   # known gap: still carries the frozen manual's advice

    def _raw(self):
        H2 = self.H2
        obs = H2._lua_json(os.path.join(H2.DFP, "observe2.lua"))
        H2._assign_sites(obs.get("map") or {})
        H2._mark_used(obs)
        obs["plugins"] = H2.plugin_state()
        return obs

    def observe(self):
        obs = self._raw()
        m = obs.pop("map", None) or {}
        H2 = self.H2
        # sites: every listed site with its facts and the server-owned id, unranked (sorted by id)
        # contract §3.1: map.sites [{id, kind, x, y, z, w, h, soil, free, dug}], unranked (by id)
        sites = []
        for sid in sorted(H2.SITES, key=lambda s: (s[:1], int(s[1:]) if s[1:].isdigit() else 0)):
            s = dict(H2.SITES[sid])
            listed, used = sid in H2.CURRENT, H2._USED.get(sid)
            s.update(kind=sid[:1], dug=sid[:1] == "R" and not listed, free=not used)
            if used:
                s["used_by"] = used
            sites.append(s)
        obs["map"] = {k: v for k, v in m.items() if k not in H2.SITE_LISTS.values()}
        obs["map"]["sites"] = sites
        obs["obs_schema"] = self.OBS_SCHEMA
        return strip_advice(obs)

    def query(self, name, **params):
        if name not in self.QUERIES:
            raise KeyError(name)
        H2 = self.H2
        if name == "workshop_types":
            return {"workshop_types": sorted(H2.WORKSHOPS)}
        if name == "manager_order_types":
            return {"recipes": {k: v.get("order") for k, v in sorted(H2.RECIPES.items())}}
        obs = strip_advice(self._raw())
        if name == "units":
            return {"dwarves": obs.get("dwarves"), "military": obs.get("military")}
        if name == "jobs":
            rows = (obs.get("dwarves") or {}).get("rows") if isinstance(obs.get("dwarves"), dict) else obs.get("dwarves")
            return {"jobs": [{"unit_id": d.get("id"), "job": d.get("job")} for d in rows or [] if isinstance(d, dict)]}
        if name == "buildings":
            return {k: obs.get(k) for k in ("workshops", "farm_plots", "doors")}
        return {name: obs.get(name)}

    def act(self, tool, args):
        text, err = self.H2.act(tool, args)
        body = text[len("ERROR: "):] if text.startswith("ERROR: ") else text
        try:
            d = json.loads(body)
        except ValueError:
            d = body
        if err:
            d = d if isinstance(d, dict) else {"error": str(d)}
            d = strip_advice(d)
            return {"ok": False, "error_code": d.pop("error_code", "failed"), "error": str(d.pop("error", "")),
                    **{k: v for k, v in d.items() if k != "ok"}}
        return {"ok": True, "result": strip_advice(d)}

    def events(self, since_tick):
        out = self.H2.H.dfhack("lua", "-f", os.path.join(HERE, "legacy_events.lua"), str(int(since_tick)))
        try:
            d = json.loads(out[out.index("{"):out.rindex("}") + 1])
        except ValueError:
            return {"events": []}
        ev = d.get("events")
        return {"events": ev if isinstance(ev, list) else [], "truncated": bool(d.get("truncated"))}


def _facts_obs_schema():
    try:
        from gameapi.facts import OBS_SCHEMA
        return OBS_SCHEMA
    except Exception:   # the facts package needs no DF to import; fall back only if it's absent
        return 7


Facts.OBS_SCHEMA = _facts_obs_schema()
