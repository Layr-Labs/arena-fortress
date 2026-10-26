"""Site state for game API v0 (docs/GAME-API.md §5.1): the site ids tools take (W2, R3, ...), owned server-side.

Ported from harness2 (_assign_sites, _mark_used, _resolve_site) without the advice (no `hint`, no `valid` lists).
Semantics kept from the frozen harness:
  * a candidate gets an id the first time it is listed, per kind (W1, W2, ...), from its kind and x,y,z; ids are
    never reused within a game, and a site keeps its id while it stays listed;
  * a dug room (an R candidate no longer listed) keeps its id, for build_farm, place_furniture, make_zone and
    create_burrow; it is "used" once a farm plot (or, for make_zone, a zone) covers it;
  * a site resolves to the coordinates the tool expects (x,y,z, plus w,h for boxes; dig_stairs: z_top/z_bottom).
Pure Python: fed by observe.lua's site_candidates, farm_plots, zones and box_facts.
"""
from .tools import SITE_KINDS

KINDS = {   # letter -> what the candidate is (observe.lua site_candidates)
    "W": "free 3x3 floor on the wagon's level (x,y = centre)",
    "G": "3x3 soil/grass floor on the surface (top-left x,y)",
    "F": "3x3 dug soil floor below the surface (top-left x,y)",
    "E": "down stair on the surface level",
    "A": "dug area on a level below the surface (bounding box of its revealed indoor floor)",
    "S": "free surface floor tile where a stair can start",
    "R": "3x3 box beside a dug stair below the surface (top-left x,y); undug until dug",
    "D": "one-tile doorway below the surface (floor between two walls)",
}
ORDER = "WGFEASRD"
# what makes a dug room unusable for a tool: a farm plot covers its floor; a zone is already there
USED_BY = {"build_farm": ("farm",), "place_furniture": ("farm",), "make_zone": ("farm", "zone"), "create_burrow": ()}
ROOM_TOOLS = ("build_farm", "place_furniture", "make_zone", "create_burrow")


def _err(code, msg):
    return {"ok": False, "error_code": code, "error": msg}


def overlap(a, b):
    """Two x,y,z,w,h boxes (top-left) on the same z-level share a tile."""
    try:
        return (a["z"] == b["z"] and a["x"] < b["x"] + (b.get("w") or 1) and b["x"] < a["x"] + (a.get("w") or 1)
                and a["y"] < b["y"] + (b.get("h") or 1) and b["y"] < a["y"] + (a.get("h") or 1))
    except (KeyError, TypeError):
        return False


class SiteState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.ids = {}       # (kind, x, y, z) -> id, for the whole game
        self.n = {}         # kind -> last number given
        self.current = {}   # id -> candidate dict, listed now
        self.rooms = {}     # every R site seen this game, by id
        self.used = {}      # dug room id -> {"farm": "farm plot 4", "zone": "Bedroom 7"}
        self.box = {}       # room id -> box facts (floor, designated, ...)

    def boxes(self):
        """Remembered rooms to ask observe.lua's box_facts about."""
        return [{"id": rid, "x": r["x"], "y": r["y"], "z": r["z"], "w": r.get("w", 3), "h": r.get("h", 3)}
                for rid, r in sorted(self.rooms.items())]

    def update(self, candidates, farm_plots=(), zones=(), box_facts=None):
        """Take one probe's site_candidates ({kind: [site, ...]}) and the buildings that can cover rooms."""
        self.current = {}
        for kind in ORDER:
            for site in (candidates or {}).get(kind) or []:
                key = (kind, site.get("x"), site.get("y"), site.get("z"))
                if key not in self.ids:
                    self.n[kind] = self.n.get(kind, 0) + 1
                    self.ids[key] = f"{kind}{self.n[kind]}"
                sid = self.ids[key]
                self.current[sid] = dict(site)
                if kind == "R":
                    self.rooms[sid] = dict(site)
        self.box = dict(box_facts or {})
        self.used = {}
        for rid, room in self.rooms.items():
            if rid in self.current:
                continue
            for kind, items in (("farm", farm_plots), ("zone", zones)):
                for b in items or []:
                    if isinstance(b, dict) and overlap(room, b):
                        label = f"farm plot {b.get('id')}" if kind == "farm" else f"{b.get('type', 'zone')} {b.get('id')}"
                        self.used.setdefault(rid, {}).setdefault(kind, label)

    def listing(self):
        """Every site with its facts, by id (no ranking): listed candidates, and every dug room of the game."""
        out = []
        for sid, s in list(self.current.items()) + [(r, s) for r, s in self.rooms.items() if r not in self.current]:
            # contract §3.1: {id, kind, x, y, z, w, h, soil, free, dug} plus the candidate's own facts
            e = {"id": sid, "w": 1, "h": 1, "soil": None}
            e.update(s)
            e["kind"] = sid[0]   # the letter (E/D candidates' own `kind` text says the same)
            e["dug"] = (sid not in self.current) if sid[0] == "R" else None
            if sid[0] == "R" and sid in self.box:
                e["tiles"] = self.box[sid]
            used = self.used.get(sid)
            e["free"] = not used
            if used:
                e["used_by"] = sorted(used.values())
            out.append(e)
        out.sort(key=lambda e: (ORDER.index(e["kind"]), int(e["id"][1:])))
        return out

    def _known(self, sid):
        return sid in self.ids.values()

    def _used_for(self, tool, sid):
        u = self.used.get(sid) or {}
        return next((u[k] for k in USED_BY.get(tool, ()) if k in u), None)

    def _usable(self, tool, sid):
        return sid in self.current or (tool in USED_BY and sid in self.rooms and not self._used_for(tool, sid))

    def resolve(self, tool, args):
        """site="W2" -> the tool's coordinate arguments. Returns (args, error dict or None)."""
        if "site" not in args:
            need = ("x", "y", "z_top") if tool == "dig_stairs" else ("x", "y", "z")
            if tool in SITE_KINDS and any(k not in args for k in need):
                return args, _err("missing_location", f"no location given: site=<id> or {','.join(need)}")
            return args, None
        sid = str(args["site"]).strip().upper()
        kinds = SITE_KINDS.get(tool)
        if not kinds:
            return args, _err("bad_arguments", f"{tool} takes no site")
        if sid[:1] not in kinds:
            return args, _err("wrong_site_kind", f"{tool} takes a {'/'.join(kinds)} site, not {sid}")
        if tool in ROOM_TOOLS and sid[:1] == "R" and sid in self.current:
            return args, _err("room_not_dug_yet", f"room {sid} is not dug yet")
        site = (self.current.get(sid) or self.rooms.get(sid)) if self._usable(tool, sid) else None
        if not site:
            used = self._used_for(tool, sid)
            if used:
                return args, _err("site_used", f"room {sid} is already used ({used})")
            if self._known(sid):
                return args, _err("site_used", f"site {sid} is no longer listed (used up or blocked)")
            return args, _err("unknown_site", f"no site {sid} in this game")
        a = {k: v for k, v in args.items() if k != "site"}
        if tool == "dig_stairs":
            a.update(x=site["x"], y=site["y"], z_top=site["z"])
            a.setdefault("z_bottom", site["z"] - 1)
        else:
            a.update(x=site["x"], y=site["y"], z=site["z"])
            if tool in ("build_farm", "create_burrow", "dig_room", "place_furniture", "make_zone"):
                a.setdefault("w", site.get("w", 3))
                a.setdefault("h", site.get("h", 3))
        return a, None
