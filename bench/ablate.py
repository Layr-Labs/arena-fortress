#!/usr/bin/env python3
"""Scaffolding ablations for the model2 arm (docs/HARNESS-PLAN.md principle 6): take one piece of help away and
measure what it was worth. smoke.py --ablate manual,hints,sites (any subset; default none).

  manual  The system prompt is MINIMAL_MANUAL (role, one call per turn, goal, time passes only by advance_days)
          instead of harness2.MANUAL. Tool schemas are unchanged: they are the API, not the manual.
  hints   Harness-written advice is removed; game state stays. Exactly:
            observation  orders[].stuck_because, .shares_inputs, .recent_cancellations (the per-order mapping; the
                         top-level recent_cancellations list is game text and stays), .waiting_for_validation_days
            tool results the keys hint, valid, valid_tools, note, reminder, warning, nearest_free_centre at any
                         depth; an error's text is cut to its first sentence and before " | " (what failed, not
                         what to do next). error_code stays. Advice lives only in `hint` (harness2.ERROR_HINTS
                         and the hints act2.lua/place.lua return), never inside the error text, so this is complete.
          Not hints, kept: error_code, recipe names on orders, tool descriptions, observation field names, the
          tripwire reason in advance_days results, interruptions, recent_actions.
  sites   No site ids: map[] lists keep their coordinates but lose `id`, tools take x,y,z only (the `site`
          parameter is removed from the schemas, and a call that sends one is rejected as bad_arguments), and the
          manual's site-id paragraph names the coordinate lists instead. Error `valid` lists give coordinates.

The default (no ablation) never imports this module's patches: harness2 and smoke.run_one are untouched, so the
default comparability key is byte-identical to a harness without this file. An ablated run's key gains
`ablate=<names>:<hash>` (bench/key.py), so ablated and default rows can't share an out dir or be pooled. stdlib only.
"""
import copy, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness2 as H2

NAMES = ("hints", "manual", "sites")

MINIMAL_MANUAL = """You are the overseer of a Dwarf Fortress fortress (version 53, fortress mode). You act only through the
tools, one tool call per turn. The observation is JSON; days_left_in_run counts down to the end of the run.
If the observation has `goal`, it says what this run is scored on; `scenario` describes the situation.
Time passes only when you call advance_days.
"""


def parse(s):
    """'manual,hints' -> ('hints', 'manual'); '' or None -> ()."""
    got = tuple(sorted({x.strip() for x in (s or "").split(",") if x.strip()}))
    bad = set(got) - set(NAMES)
    if bad:
        raise SystemExit(f"--ablate: unknown {sorted(bad)}; choose from {list(NAMES)}")
    return got


def _sub(s, old, new):
    """Replace exactly one occurrence, or fail: the ablation must notice when the text it edits changes."""
    if s.count(old) != 1:
        raise AssertionError(f"ablate: expected one occurrence of {old[:60]!r}")
    return s.replace(old, new)


# ------------------------------------------------------------------ sites
SITES_MANUAL = [
    ("Farming underground: dig_stairs down from the surface (S sites), dig_room beside the stair (R sites; \"soil\" means\n"
     "soil there), advance until dig_designations_pending is 0, then build_farm on the dug room (site=R<n>).",
     "Farming underground: dig_stairs down from the surface (map.stair_sites), dig_room beside the stair\n"
     "(map.room_sites; \"soil\" means soil there), advance until dig_designations_pending is 0, then build_farm on\n"
     "the dug room."),
    ("""  map: candidate places by kind, each with an id that stays fixed for the run (used-up places drop out). Tools
    that place things take site=<id>:
      W free 3x3 floor for a workshop (centre)     S surface tile where a stair can start (clear of the wagon)
      R 3x3 room beside a dug stair below ground   F dug soil floor below ground (farm plot)
      G surface soil (underground crops won't grow) E stair down from the surface (a hatch over it seals it)
      A dug area below ground (shelter burrow)     D doorway below ground (door or wall closes it)
    An R site is "undug": dig_room it first. Once dug it leaves map.R, and its id then works for build_farm,
    place_furniture and make_zone.
""",
     """  map: candidate places as "x,y,z" (top-left, with w x h, for areas; used-up places drop out). Tools take x,y,z:
      free_3x3_sites_near_wagon: free 3x3 floor for a workshop (centre)
      stair_sites: surface tile where a stair can start (clear of the wagon)
      room_sites: 3x3 room beside a dug stair below ground
      underground_soil_farm_sites: dug soil floor below ground (farm plot)
      surface_soil_sites_NOT_for_starting_seeds: surface soil (underground crops won't grow)
      surface_entrances: stair down from the surface (a hatch over it seals it)
      underground_dug_areas: dug area below ground (shelter burrow)
      doorways: doorway below ground (door or wall closes it)
    A room_sites entry is "undug": dig_room it first; once dug it leaves map.room_sites.
"""),
]
SITES_DESC = {   # tool -> [(old, new)] in its description
    "build_workshop": [("Place a workshop on a W site.", "Place a workshop centred at x,y,z (a free 3x3 floor).")],
    "build_farm": [("dug soil floor: an F site, or an R room you dug.", "dug soil floor: a w x h box at top-left x,y,z.")],
    "create_burrow": [("Add an A site, or an R room you dug, to the Shelter burrow (the civilian-alert burrow), `levels` levels down.",
                       "Add a w x h box at top-left x,y,z to the Shelter burrow (the civilian-alert burrow), `levels` "
                       "levels down.")],
    "build_door": [("over a down stair (E site) or a door in a doorway (D site).",
                    "over a down stair or a door in a doorway, at x,y,z.")],
    "build_wall": [("in a doorway (D site)", "on a floor tile at x,y,z (a doorway)")],
    "dig_room": [("Dig an R site (default 3x3; w,h to change).",
                  "Dig a w x h room at top-left x,y,z that connects to a dug stair or tunnel.")],
    "dig_stairs": [("Dig a staircase down from an S site to z_bottom (default one level down).",
                    "Dig a staircase at x,y from z_top down to z_bottom.")],
    "place_furniture": [("on free floor tiles of an A or R site:",
                         "on free floor tiles of the w x h box at top-left x,y,z (default 1x1):")],
    "make_zone": [("Zone an A or R site.", "Zone a w x h box at top-left x,y,z.")],
}
# without a site, these have no default extent (harness.validate / create_burrow need it); others: x, y, z
SITES_REQUIRED = {"dig_stairs": ["x", "y", "z_top", "z_bottom"], "dig_room": ["x", "y", "z", "w", "h"],
                  "create_burrow": ["x", "y", "z", "w", "h"]}
SITES_EXTENT = {"build_farm": 10, "create_burrow": 40, "place_furniture": 40, "make_zone": 20, "dig_room": None}
SITES_HINTS = [("site=<id> or ", ""), ("site=<id>", "x,y,z"), ("R sites appear", "map.room_sites entries appear"),
               ("an R room you dug", "a room you dug"), ("a listed site", "a listed map entry"),
               ("a dug R room listed with soil", "a dug map.room_sites room listed with soil")]
_SITE_WORD = re.compile(r"\b(an?|another|the) ([WSRFGEAD])(?: or ([WSRFGEAD]))? site\b")


def _site_words(text):
    """'use an E site' -> 'use a map.surface_entrances entry' (hints name site kinds by their id letter)."""
    for old, new in SITES_HINTS:
        text = text.replace(old, new)
    art = {"a": "a", "an": "a", "another": "another", "the": "the"}
    return _SITE_WORD.sub(lambda m: f"{art[m.group(1)]} " + " or ".join(
        "map." + H2.SITE_LISTS[k] for k in (m.group(2), m.group(3)) if k) + " entry", text)


def sites_tools(tools):
    out = copy.deepcopy(tools)
    for t in out:
        f = t["function"]; name = f["name"]
        props = f["parameters"]["properties"]
        if "site" not in props:
            continue
        for old, new in SITES_DESC[name]:
            f["description"] = _sub(f["description"], old, new)
        del props["site"]
        need = SITES_REQUIRED.get(name, ["x", "y", "z"])
        coords = {k: {"type": "integer"} for k in need if k not in ("w", "h")}   # the schemas list only `site` (1.8)
        if name in SITES_EXTENT and "w" not in props:   # the site gave it an area; with coordinates the agent gives the box
            ext = SITES_EXTENT[name] or 10
            coords.update(w={"type": "integer", "minimum": 1, "maximum": ext}, h={"type": "integer", "minimum": 1, "maximum": ext})
        f["parameters"]["properties"] = {**coords, **props}
        req = [k for k in f["parameters"].get("required", []) if k != "site"]
        f["parameters"]["required"] = req + need
    assert not any("site" in t["function"]["parameters"]["properties"] for t in out)
    return out


def sites_manual(manual):
    for old, new in SITES_MANUAL:
        manual = _sub(manual, old, new)
    return manual


def sites_obs(obs):
    m = obs.get("map") or {}
    for key in H2.SITE_LISTS.values():
        for site in m.get(key) or []:
            site.pop("id", None)
    return obs


def _coords(sid):
    s = H2.SITES.get(sid) or {}
    return {k: s[k] for k in ("x", "y", "z", "w", "h") if k in s}


def sites_result(result):
    if not result.startswith("ERROR: "):
        return result
    try:
        d = json.loads(result[len("ERROR: "):])
    except ValueError:
        return result
    if not isinstance(d, dict):
        return result
    if isinstance(d.get("valid"), list):
        d["valid"] = [_coords(v) for v in d["valid"] if isinstance(v, str)]
    for k in ("error", "hint"):   # e.g. missing_location: "give site=<id> or x,y,z"; "use an E site"
        if isinstance(d.get(k), str):
            d[k] = _site_words(d[k])
    return "ERROR: " + json.dumps(d)


# ------------------------------------------------------------------ hints
HINT_ORDER_KEYS = ("stuck_because", "shares_inputs", "recent_cancellations", "waiting_for_validation_days")
HINT_RESULT_KEYS = ("hint", "valid", "valid_tools", "note", "reminder", "warning", "nearest_free_centre")


def hints_obs(obs):
    for o in obs.get("orders") or []:
        for k in HINT_ORDER_KEYS:
            o.pop(k, None)
    return obs


def _first_sentence(msg):
    msg = msg.split(" | ", 1)[0]
    m = re.search(r"\. (?=[A-Z])", msg)
    return msg[:m.start()] if m else msg


def _strip(x):
    if isinstance(x, dict):
        return {k: _strip(v) for k, v in x.items() if k not in HINT_RESULT_KEYS}
    if isinstance(x, list):
        return [_strip(v) for v in x]
    return x


def hints_result(result):
    err = result.startswith("ERROR: ")
    body = result[len("ERROR: "):] if err else result
    try:
        d = json.loads(body)
    except ValueError:   # plain text: dig results, "advanced N ticks", unstructured errors
        return ("ERROR: " + _first_sentence(body)) if err else result
    if not isinstance(d, dict):
        return result
    d = _strip(d)
    if err and isinstance(d.get("error"), str):
        d["error"] = _first_sentence(d["error"])
    return ("ERROR: " if err else "") + json.dumps(d)


# ------------------------------------------------------------------ apply
def apply(names):
    """Patch harness2 for this process: MANUAL, TOOLS, observe() and act(). Call once, before any run."""
    names = tuple(sorted(names))
    if not names:
        return
    if getattr(H2, "_ABLATED", None) is not None:
        raise RuntimeError("ablations already applied")
    H2._ABLATED = names
    if "manual" in names:
        H2.MANUAL = MINIMAL_MANUAL
    elif "sites" in names:
        H2.MANUAL = sites_manual(H2.MANUAL)
    if "sites" in names:
        H2.TOOLS = sites_tools(H2.TOOLS)
    observe, act = H2.observe, H2.act

    def observe_ablated():
        obs = observe()
        obs = copy.deepcopy(obs)   # harness2.SITES holds the same site dicts
        if "sites" in names:
            obs = sites_obs(obs)
        if "hints" in names:
            obs = hints_obs(obs)
        return obs

    def act_ablated(name, args):
        if "sites" in names and isinstance(args, dict) and "site" in args:
            res, err = H2._err("bad_arguments", "site ids are not available; give x,y,z"), True
        else:
            res, err = act(name, args)
        if "sites" in names:
            res = sites_result(res)
        if "hints" in names:
            res = hints_result(res)
        return res, err

    H2.observe, H2.act = observe_ablated, act_ablated


def effective(names):
    """(manual, tools) the model sees under these ablations, without patching anything (for the key)."""
    names = tuple(sorted(names))
    manual, tools = H2.MANUAL, H2.TOOLS
    if getattr(H2, "_ABLATED", None) is not None:   # already patched in this process: the originals are gone
        return manual, tools
    if "manual" in names:
        manual = MINIMAL_MANUAL
    elif "sites" in names:
        manual = sites_manual(manual)
    if "sites" in names:
        tools = sites_tools(tools)
    return manual, tools


if __name__ == "__main__":   # print what the model sees: python3 bench/ablate.py sites
    n = parse(sys.argv[1] if len(sys.argv) > 1 else "")
    m, t = effective(n)
    print(m)
    print(json.dumps(t, indent=1))
