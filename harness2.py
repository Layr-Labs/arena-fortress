#!/usr/bin/env python3
"""DF fortress-mode LLM harness v2: context-rich.

Changes from v1 (harness.py):
  * MANUAL: a concise fortress-mode operating manual in the system prompt (production chains,
    prerequisites, what each tool really does, how to read the observation, common failure messages).
  * observe2.lua: administrators, per-dwarf jobs, usable-vs-unusable stocks, empty barrels,
    workshops (built?, queued jobs), farm plots, per-order status (validated/active/jobs in progress),
    recent cancellation reasons, free 3x3 build sites and soil farm sites.
  * Tools mirror the player's real options: appoint manager, build workshop, build farm,
    named order recipes (correct job type + material), cancel order, plugins with state.
  * act() returns errors as errors (ok:false / ERROR:), never as a normal-looking result.
  * Order diagnostics: each order is annotated with WHY it is stuck when it is stuck.
Same allowlist discipline: no raw lua/dfhack strings reach DF from the model.
"""
import json, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H   # reuses dfhack(), chat(), api_key(), Rejected, _int, validate() for dig tools

DFP = H.DFP
MAX_DAYS = 14   # 28 cut Sonnet start-year credited 750 -> 552 (runs/ab-maxdays-2026-10-09); 7 and 14 score alike
# Measured 2026-10-07: with the full manual + observation, glm-5.3-flash at default reasoning hit the
# token cap with no tool call 2 of 3 times at max_tokens=4000 (~37s); effort=low gave 3/3 tool calls at ~2s.
CHAT_EXTRA = {"max_tokens": 4000, "reasoning": {"effort": "low"}}

# ---------------------------------------------------------------- recipes (named, known-good)
# Each recipe maps a plain name to the exact manager-order JSON DF accepts, plus what it needs.
RECIPES = {
    "brew_drink":   {"order": {"job": "CustomReaction", "reaction": "BREW_DRINK_FROM_PLANT"},
                     "workshop": "Still", "needs": "brewable plant + empty barrel",
                     "makes": "5 drinks"},
    "brew_drink_from_fruit": {"order": {"job": "CustomReaction", "reaction": "BREW_DRINK_FROM_PLANT_GROWTH"},
                     "workshop": "Still", "needs": "brewable fruit + empty barrel",
                     "makes": "5 drinks"},
    "make_barrel":  {"order": {"job": "MakeBarrel", "material_category": ["wood"]},
                     "workshop": "Carpenters", "needs": "1 usable log", "makes": "1 empty barrel"},
    "make_bed":     {"order": {"job": "ConstructBed", "material_category": ["wood"]},
                     "workshop": "Carpenters", "needs": "1 usable log", "makes": "1 bed"},
    "make_door":    {"order": {"job": "ConstructDoor", "material_category": ["wood"]},
                     "workshop": "Carpenters", "needs": "1 usable log", "makes": "1 door"},
    "make_table":   {"order": {"job": "ConstructTable", "material_category": ["wood"]},
                     "workshop": "Carpenters", "needs": "1 usable log", "makes": "1 table"},
    "make_chair":   {"order": {"job": "ConstructThrone", "material_category": ["wood"]},
                     "workshop": "Carpenters", "needs": "1 usable log", "makes": "1 chair"},
    "make_bin":     {"order": {"job": "ConstructBin", "material_category": ["wood"]},
                     "workshop": "Carpenters", "needs": "1 usable log", "makes": "1 bin"},
    "cook_meal":    {"order": {"job": "PrepareMeal"},   # DFHack workorder ignores mat_type (it reads meal_ingredients); the default works
                     "workshop": "Kitchen", "needs": "2+ cookable ingredients",
                     "makes": "prepared meals"},
    "make_hatch_cover": {"order": {"job": "ConstructHatchCover", "material_category": ["wood"]},
                     "workshop": "Carpenters", "needs": "1 usable log", "makes": "1 hatch cover"},
    "make_charcoal":{"order": {"job": "MakeCharcoal"},
                     "workshop": "WoodFurnace", "needs": "1 usable log", "makes": "charcoal"},
}
WORKSHOPS = {"Carpenters": "wood furniture, barrels, bins", "Still": "brewing drink",
             "Kitchen": "cooking meals", "Masons": "stone furniture (needs boulders from mining)",
             "Craftsdwarfs": "crafts from stone/wood/bone",
             "Farmers": "plant processing", "Butchers": "butchering animals",
             "Fishery": "processing raw fish",
             "WoodFurnace": "charcoal; built from a stone boulder, not logs"}
AUTOMATION = {"autochop": "fells trees for usable logs (the wagon's logs can't be used)",
              "autofarm": "picks each plot's crop every season from your seeds",
              "seedwatch": "keeps the last seeds of each crop from being cooked or brewed",
              "autolabor": "assigns labors automatically",
              "autoclothing": "queues clothing orders"}

MANUAL = """You are the overseer of a Dwarf Fortress fortress (version 53, fortress mode). You act only through the
tools, one tool call per turn. The observation is JSON; days_left_in_run counts down to the end of the run.
If it has hands_off_in_days, that is how many days you have left to act: after that, time runs to the end of the
run without you, and only the orders, automation and buildings you set up keep working.
If the observation has `goal`, it says what this run is scored on; `scenario` describes the situation.

SCORE (open play, and what lab goals mean by a working fort). What counts is how the fort is doing, in this order:
dwarves alive (deaths and dwarves driven insane count against you, and so do raiders left on the map); drink and
food in stock every day to the end, from a supply that keeps going (a stockpile that runs out doesn't count);
dwarves' wellbeing (few stressed dwarves, no tantrums, no breakdowns); beds and dining space for everyone; and on long
runs the fort's growth (DF's own progression). Each part counts only once the parts before it hold. Making things counts only through
these: production that doesn't feed, house or protect the fort adds nothing.

HOW THINGS GET MADE. Dwarves do the work; you set up what they work on. A work order (add_order) is validated by
the MANAGER (about a day), handed to a matching built WORKSHOP, and done by a dwarf with the labor and inputs.
Every link must exist, or the order does nothing:
  - appoint_manager first. Without a manager, orders stay validated=false. From 20 citizens the manager validates
    only from an office of their own: an office zone (make_zone office) with a built chair in it (place_furniture),
    assigned to the manager (assign_zone). administrators.manager_office shows it.
  - build_workshop consumes one usable log or boulder. With no usable material the builder cancels it for good,
    so the tool refuses while stocks.logs_usable and stocks.boulders_usable are both 0. The logs in the wagon
    can't be used: enable autochop to get usable logs.
  - Inputs must be usable stock (stocks.*; rotten or forbidden items aren't counted). Brewing needs a brewable
    plant AND an empty barrel (stocks.barrels_empty); the starting barrels are full.
  - add_order repeat/when keeps an order going (e.g. brew daily while drink is below 50) instead of one-shot amounts.
Drink: dwarves drink water when they can reach it, but run unhappier and slower without drink.
Plants: stocks.plants_by_kind says which plants are brewable and which cookable; cooking and brewing can use up
the same plants. autofarm picks crops for each plot, seedwatch keeps the last seeds from being used.
Farming underground: dig_stairs down from the surface (S sites), dig_room beside the stair (R sites; "soil" means
soil there), advance until dig_designations_pending is 0, then build_farm on the dug room (site=R<n>).
Dwarves are happier eating prepared meals than raw food. Digging on its own adds nothing.
Dwarves get unhappy sleeping without a bed or eating without a table and chair: place_furniture puts built
items (stocks.furniture_free) into rooms, make_zone turns a room into a bedroom/dormitory/dining hall/office
(zones[]), and assign_zone gives an office or bedroom to one dwarf.

READING THE OBSERVATION. Compact JSON; empty lists and objects are left out. Positions are "x,y,z".
  orders[]: validated/active/jobs_in_progress; `left` counts down. stuck_because says why the harness thinks an
    order isn't progressing (missing manager/workshop/input, waiting for validation, recent cancellation reasons).
  workshops[], farm_plots[], doors.list[]: "<id> <type> @x,y,z", NOT BUILT while waiting for material or a builder.
  recent_cancellations (last 3 days): the game's reason when a dwarf abandons a job. Fix the cause; re-queuing
    the same order won't help.
  recent_actions: your last calls and their outcomes. Older observations in the conversation are omitted: the
    latest observation is the current state.
  dwarves.rows: "id profession|job|stress", then "|org N" (organizer skill, if any) and positions (a noble's
    position replaces its profession). stress: 0 (most stressed) to 6 (content); 0-1 is stressed.
  seeds_by_kind: count, `underground` (grows only on a farm plot below the surface), growing seasons.
  threats.hostiles: groups of nearby hostiles: count, race, weapons, dist (tiles from the wagon: max of |dx|,|dy|,
    plus 3 per z-level), the box they are in (x1-x2,y1-y2,z) and their unit ids (a-b is a range).
  military.squads[]: orders, uniform, armed members, members by weapon, and their dist from the wagon.
  moods: dwarves in a strange mood: mood, skill, the workshop type it needs, the workshop it claimed, and the items
    it still needs (collected/needed). A mood with no workshop or items for too long ends in insanity.
  water_on_fort_levels: water on revealed indoor tiles of the fortress levels (tiles, deep_tiles of depth 4+).
  map: candidate places by kind, each with an id that stays fixed for the run (used-up places drop out). Tools
    that place things take site=<id>:
      W free 3x3 floor for a workshop (centre)     S surface tile where a stair can start (clear of the wagon)
      R 3x3 room beside a dug stair below ground   F dug soil floor below ground (farm plot)
      G surface soil (underground crops won't grow) E stair down from the surface (a hatch over it seals it)
      A dug area below ground (shelter burrow)     D doorway below ground (door or wall closes it)
    An R site is "undug": dig_room it first. Once dug it leaves map.R, and its id then works for build_farm,
    place_furniture and make_zone.

DEFENCE. threats.hostiles lists the visible hostiles. Unarmed civilians
fight with their fists: an armed party can kill most of a fortress in a day. Squads use only weapons and armour
that exist (military.weapons_free); a squad sent against a stronger party loses its members. civilian_alert keeps
civilians inside the Shelter burrow (create_burrow) until you turn it off; while it is on, they don't work.
Locked doors and hatches stop these invaders, and your own dwarves too: lock once everyone is inside. A wall
(build_wall) in a doorway closes it for good; nothing in the tool API removes it.

TIME. Nothing happens unless you call advance_days (1-14 days). An advance stops early, and its result says
why, when a hostile appears or comes near your dwarves, a citizen dies, a dwarf has a strange mood, tantrum or
berserk fit, migrants or a caravan arrive, an invasion starts, or water rises on the fortress levels.
"""

# add_order `when` stocks -> the DF manager-order item condition DFHack's workorder accepts (the same mechanism the
# automation arm's standing orders use, automation/standing-orders.json). DF counts the items itself.
ORDER_STOCKS = {
    "drink": {"item_type": "DRINK"},
    "prepared_meals": {"item_type": "FOOD"},
    "barrels_empty": {"item_type": "BARREL", "flags": ["empty"]},
    "logs": {"item_type": "WOOD"},
    # the observation's own stocks.* names, which models reach for first (local Qwen3-8B looped 52 times on these)
    "logs_usable": {"item_type": "WOOD"},
    "food_edible": {"flags": ["unrotten", "cookable"]}, "food": {"flags": ["unrotten", "cookable"]},
    "plants_total": {"item_type": "PLANT", "flags": ["unrotten"]},
    "plants_brewable": {"item_type": "PLANT", "flags": ["unrotten"], "reaction_product": "DRINK_MAT"},
    "boulders": {"item_type": "BOULDER"},
    "beds": {"item_type": "BED"}, "tables": {"item_type": "TABLE"}, "chairs": {"item_type": "CHAIR"},
    "doors": {"item_type": "DOOR"}, "bins": {"item_type": "BIN"},
}
FURNITURE = {"bed": "b", "table": "t", "chair": "c", "door": "d", "container": "h"}   # quickfort #build keys
ZONES = {"bedroom": "b", "dormitory": "D", "dining_hall": "h", "meeting_area": "m", "office": "o"}   # quickfort #zone keys
REPEATS = {"daily": "Daily", "monthly": "Monthly", "seasonally": "Seasonally", "yearly": "Yearly"}


class Invalid(H.Rejected):
    """An argument outside its allowed values: the error names the value and lists every allowed one (`allowed`: the
    tool schema's enum, so not a hint; bench/ablate.py's hints and sites ablations leave it, unlike `valid` site ids)."""
    def __init__(self, what, value, allowed):
        super().__init__(f"unknown {what} {value!r}")
        self.allowed = sorted(allowed)


def order_spec(rec, args):
    """add_order arguments -> the workorder JSON. Raises H.Rejected on bad repeat/when."""
    spec = dict(rec["order"], amount_total=H._int(args, "amount", 1, 30))
    rep = args.get("repeat")
    if rep is not None:
        if rep not in REPEATS:
            raise Invalid("repeat", rep, REPEATS)
        spec["frequency"] = REPEATS[rep]
    when = args.get("when")
    if when is not None:
        if rep is None:
            raise H.Rejected("when needs repeat: conditions are checked at each repeat")
        if not isinstance(when, list) or not 1 <= len(when) <= 3:
            raise H.Rejected("when must be a list of 1-3 conditions")
        conds = []
        for c in when:
            if not isinstance(c, dict) or c.get("stock") not in ORDER_STOCKS:
                raise Invalid("when stock", c.get("stock") if isinstance(c, dict) else c, ORDER_STOCKS)
            keys = [k for k in ("below", "at_least") if k in c]
            if len(keys) != 1:
                raise H.Rejected("each condition needs exactly one of below / at_least")
            n = H._int(c, keys[0], 0, 100000)
            conds.append(dict(ORDER_STOCKS[c["stock"]], condition="LessThan" if keys[0] == "below" else "AtLeast", value=n))
        spec["item_conditions"] = conds
    return spec


def _recipes_by_workshop():
    """'Carpenters (1 usable log -> 1 each): make_barrel, make_bed, ...; Still: ...' (HARNESS-PLAN 1.8)."""
    groups = {}
    for k, v in RECIPES.items():
        same = v["makes"].split()[0] == "1" and v["needs"] == "1 usable log"
        groups.setdefault((v["workshop"], same), []).append(k)
    out = []
    for (ws, same), ks in groups.items():
        if same:
            out.append(f"{ws} (1 usable log -> 1 item): " + ", ".join(ks))
        else:
            out.append(f"{ws}: " + ", ".join(f"{k} ({RECIPES[k]['needs']} -> {RECIPES[k]['makes']})" for k in ks))
    return "; ".join(out)


_INT = {"type": "integer"}
_SITE = {"type": "string"}
# Site tools advertise only `site` (required since #31); act() still accepts raw x,y,z (logged separately), but the
# schemas no longer list them (HARNESS-PLAN 1.8: -~0.6k tokens per call).
TOOLS = [
    {"type": "function", "function": {"name": "appoint_manager",
     "description": "Appoint the MANAGER, who validates work orders. Omit dwarf_id to pick a citizen without a position.",
     "parameters": {"type": "object", "properties": {"dwarf_id": _INT}}}},
    {"type": "function", "function": {"name": "build_workshop",
     "description": "Place a workshop on a W site. " + "; ".join(f"{k}: {v}" for k, v in WORKSHOPS.items()),
     "parameters": {"type": "object", "required": ["type", "site"], "properties": {
        "type": {"type": "string", "enum": sorted(WORKSHOPS)}, "site": _SITE}}}},
    {"type": "function", "function": {"name": "build_farm",
     "description": "Place a farm plot on dug soil floor: an F site, or an R room you dug.",
     "parameters": {"type": "object", "required": ["site"], "properties": {"site": _SITE}}}},
    {"type": "function", "function": {"name": "add_order",
     "description": "Queue a work order. Recipes by workshop (needs -> makes): " + _recipes_by_workshop(),
     "parameters": {"type": "object", "required": ["recipe", "amount"], "properties": {
        "recipe": {"type": "string", "enum": sorted(RECIPES)},
        "amount": {"type": "integer", "minimum": 1, "maximum": 30},
        "repeat": {"type": "string", "enum": sorted(REPEATS), "description": "re-queue every period"},
        "when": {"type": "array", "maxItems": 3,
                 "description": "with repeat: only while all hold, e.g. [{\"stock\": \"drink\", \"below\": 50}]",
                 "items": {"type": "object", "required": ["stock"], "properties": {
                     "stock": {"type": "string", "enum": sorted(ORDER_STOCKS)},
                     "below": _INT, "at_least": _INT}}}}}}},
    {"type": "function", "function": {"name": "cancel_order",
     "description": "Remove a work order by orders[].id.",
     "parameters": {"type": "object", "required": ["order_id"], "properties": {"order_id": _INT}}}},
    {"type": "function", "function": {"name": "enable_automation",
     "description": "Enable a DFHack helper. " + "; ".join(f"{k}: {v}" for k, v in AUTOMATION.items()),
     "parameters": {"type": "object", "required": ["name"], "properties": {
        "name": {"type": "string", "enum": sorted(AUTOMATION)}}}}},
    {"type": "function", "function": {"name": "create_squad",
     "description": "Create the one squad from dwarf_ids (adults without a position) or size N (best fighters). Members keep working until it gets an order.",
     "parameters": {"type": "object", "properties": {
        "dwarf_ids": {"type": "array", "items": _INT, "maxItems": 10},
        "size": {"type": "integer", "minimum": 1, "maximum": 10}}}}},
    {"type": "function", "function": {"name": "equip_squad",
     "description": "Give the squad a uniform: a melee weapon plus that armour, from items that exist.",
     "parameters": {"type": "object", "required": ["uniform"], "properties": {
        "uniform": {"type": "string", "enum": ["weapon_only", "leather", "metal"]}}}}},
    {"type": "function", "function": {"name": "squad_order",
     "description": "Order the squad: attack (all visible hostiles, or target_ids), station at x,y,z, or stand_down.",
     "parameters": {"type": "object", "required": ["order"], "properties": {
        "order": {"type": "string", "enum": ["attack", "station", "stand_down"]},
        "target_ids": {"type": "array", "items": _INT, "maxItems": 20}, "x": _INT, "y": _INT, "z": _INT}}}},
    {"type": "function", "function": {"name": "create_burrow",
     "description": "Add an A site, or an R room you dug, to the Shelter burrow (the civilian-alert burrow), `levels` levels down.",
     "parameters": {"type": "object", "required": ["site"], "properties": {"site": _SITE,
        "levels": {"type": "integer", "minimum": 1, "maximum": 5}}}}},
    {"type": "function", "function": {"name": "civilian_alert",
     "description": "Civilians stay in the Shelter burrow while on.",
     "parameters": {"type": "object", "required": ["on"], "properties": {"on": {"type": "boolean"}}}}},
    {"type": "function", "function": {"name": "build_door",
     "description": "Place a hatch cover over a down stair (E site) or a door in a doorway (D site). Needs a hatch cover / door item.",
     "parameters": {"type": "object", "required": ["kind", "site"], "properties": {"site": _SITE,
        "kind": {"type": "string", "enum": ["door", "hatch"]}}}}},
    {"type": "function", "function": {"name": "build_wall",
     "description": "Build a wall in a doorway (D site) from a usable log or boulder. It closes the way for good.",
     "parameters": {"type": "object", "required": ["site"], "properties": {"site": _SITE}}}},
    {"type": "function", "function": {"name": "lock_door",
     "description": "Lock or unlock a door/hatch by door_id, or all if omitted.",
     "parameters": {"type": "object", "required": ["locked"], "properties": {"locked": {"type": "boolean"}, "door_id": _INT}}}},
    {"type": "function", "function": {"name": "dig_room",
     "description": "Dig an R site (default 3x3; w,h to change).",
     "parameters": {"type": "object", "required": ["site"], "properties": {"site": _SITE,
        "w": {"type": "integer", "minimum": 1, "maximum": H.MAX_DIM}, "h": {"type": "integer", "minimum": 1, "maximum": H.MAX_DIM}}}}},
    {"type": "function", "function": {"name": "dig_stairs",
     "description": "Dig a staircase down from an S site to z_bottom (default one level down).",
     "parameters": {"type": "object", "required": ["site"], "properties": {"site": _SITE, "z_bottom": _INT}}}},
    {"type": "function", "function": {"name": "place_furniture",
     "description": "Put built items (stocks.furniture_free) on free floor tiles of an A or R site: count of them (default 1), one per tile.",
     "parameters": {"type": "object", "required": ["kind", "site"], "properties": {
        "kind": {"type": "string", "enum": sorted(FURNITURE)}, "site": _SITE,
        "count": {"type": "integer", "minimum": 1, "maximum": 30}}}}},
    {"type": "function", "function": {"name": "make_zone",
     "description": "Zone an A or R site. Bedrooms and dormitories need beds, dining halls tables and chairs.",
     "parameters": {"type": "object", "required": ["kind", "site"], "properties": {
        "kind": {"type": "string", "enum": sorted(ZONES)}, "site": _SITE}}}},
    {"type": "function", "function": {"name": "assign_zone",
     "description": "Assign an office or bedroom zone (zones[] id) to a citizen (dwarves.rows id), as the zone's Assign button does.",
     "parameters": {"type": "object", "required": ["zone_id", "dwarf_id"], "properties": {"zone_id": _INT, "dwarf_id": _INT}}}},
    {"type": "function", "function": {"name": "advance_days",
     "description": "Let 1-14 in-game days pass. Stops early, and says why, on events (see manual).",
     "parameters": {"type": "object", "required": ["days"], "properties": {
        "days": {"type": "integer", "minimum": 1, "maximum": MAX_DAYS}}}}},
]
NAMES = {t["function"]["name"] for t in TOOLS}

def _quickfort(blueprint, x, y, z):
    """Run a one-off quickfort blueprint with its top-left at x,y,z; returns quickfort's output."""
    with open(os.path.join(H.BP_DIR, "harness_place.csv"), "w") as f:
        f.write(blueprint)
    return H.dfhack("quickfort", "run", "harness_place.csv", "-c", f"{x},{y},{z}", with_stderr=True)


def _lua_json(*args):
    raw = H.dfhack("lua", "-f", *args)
    try:
        return json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except ValueError:
        return {"ok": False, "error_code": "internal_error", "error": "the game-side script failed: " + raw[-300:]}

def plugin_state():
    out = H.dfhack("enable")
    st = {}
    for name in AUTOMATION:
        m = re.search(rf"\b{name}:\s+(on|off)", out)
        st[name] = m.group(1) if m else "unknown"
    return st

def diagnose(obs):
    """Annotate each order with the most likely reason it is not progressing."""
    adm = obs.get("administrators") or {}
    stocks = obs.get("stocks") or {}
    built = {w["type"] for w in obs.get("workshops") or [] if w.get("built")}
    planned = {w["type"] for w in obs.get("workshops") or [] if not w.get("built")}
    plugins = obs.get("plugins", {})
    cancels = _parse_cancels(obs)
    for o in obs.get("orders") or []:
        recipe = next((k for k, v in RECIPES.items() if v["order"]["job"] == o["job"] and
                       v["order"].get("reaction") == o.get("reaction")), None)
        o["recipe"] = recipe
        ws = RECIPES[recipe]["workshop"] if recipe else None
        why = []
        if not adm.get("manager_active_for_orders"):
            why.append("no manager appointed (use appoint_manager)")
        if ws and ws not in built:
            why.append(f"no built {ws} workshop" + (" (one is planned, waiting to be built)" if ws in planned else " (use build_workshop)"))
        if ws in ("Carpenters", "WoodFurnace") and stocks.get("logs_usable", 0) == 0:
            why.append("no usable logs" + ("" if plugins.get("autochop") == "on" else " (enable autochop)"))
        if recipe and recipe.startswith("brew"):
            if stocks.get("barrels_empty", 0) == 0:
                why.append("no empty barrels (add_order make_barrel)")
            if recipe == "brew_drink" and stocks.get("plants_brewable", 0) == 0:
                why.append("no brewable plants (farm, or gather)")
        if o.get("repeat") and o.get("validated") and not o.get("active") and o.get("jobs_in_progress", 0) == 0:
            why.append(f"repeating order between runs: re-queued at its next {o['repeat']} check when its conditions hold")
        if not o.get("validated"):
            waited = _order_age_days(o["id"], obs)
            o["waiting_for_validation_days"] = round(waited, 1)
            office = adm.get("manager_office")
            lacks = None
            if adm.get("manager_needs_office") and adm.get("manager_active_for_orders"):
                if not isinstance(office, dict):
                    lacks = "the manager has no office zone assigned to them"
                elif not office.get("chair"):
                    lacks = f"the manager's office (zone {office.get('zone_id')}) has no built chair"
            if lacks:   # v2: the >= 20-citizen stall, named (it used to read as an ordinary wait)
                why.append(f"not validated ({waited:.1f} days): with 20 or more citizens the manager validates orders "
                           f"only from an office zone assigned to them with a built chair in it; {lacks}")
            elif adm.get("manager_needs_office"):   # office in place: validation from it took 2-4 days in game
                why.append(f"not yet validated by the manager ({waited:.1f} days; usually within 4 days)")
            else:
                why.append(f"not yet validated by the manager ({waited:.1f} days; usually within a day)")
        reasons = _cancellations_for(recipe, cancels)
        if reasons:
            o["recent_cancellations"] = reasons
            why += [f"recently cancelled: {r}" for r in reasons]
        if why and o.get("jobs_in_progress", 0) == 0:
            o["stuck_because"] = why
    pending = {o.get("recipe") for o in obs.get("orders") or [] if o.get("left", 0) > 0}
    if "cook_meal" in pending and pending & {"brew_drink", "brew_drink_from_fruit"}:
        for o in obs.get("orders") or []:
            if o.get("recipe") in ("cook_meal", "brew_drink", "brew_drink_from_fruit"):
                o["shares_inputs"] = (f"cooking and brewing can both use the same plants "
                                      f"(plants_brewable={stocks.get('plants_brewable', 0)}, plants_total={stocks.get('plants_total', 0)})")
    return obs


# --- order age and cancellation reasons (for diagnose) ---------------------------------------------------------
_FIRST_SEEN = {}        # order id -> abs_tick when the harness first saw it unvalidated
_LAST_TICK = [None]

def reset_tracking():
    """Call at the start of each run: order ids repeat across runs from the same save, and site ids are per run."""
    _FIRST_SEEN.clear(); _LAST_TICK[0] = None
    _SITE_IDS.clear(); _SITE_N.clear(); SITES.clear(); _ROOMS.clear(); _USED.clear()

def _order_age_days(oid, obs):
    tick = (obs.get("date") or {}).get("abs_tick")
    if tick is None:
        return 0.0
    if _LAST_TICK[0] is not None and tick < _LAST_TICK[0]:   # time went backwards: a new run
        reset_tracking()
    _LAST_TICK[0] = tick
    return (tick - _FIRST_SEEN.setdefault(oid, tick)) / 1200

# DF job names in cancellation reports ("<dwarf> cancels <job>: <reason>") -> recipes. Cooking reports have an empty
# job name ("cancels : Needs unrotten cookable solid item"), so the reason text is matched too.
_CANCEL_KEYS = [("brew", ("brew_drink", "brew_drink_from_fruit")), ("barrel", ("make_barrel",)),
                ("cookable", ("cook_meal",)), ("prepare", ("cook_meal",)), ("meal", ("cook_meal",)),
                ("bed", ("make_bed",)), ("door", ("make_door",)), ("table", ("make_table",)),
                ("throne", ("make_chair",)), ("chair", ("make_chair",)), ("bin", ("make_bin",)),
                ("hatch", ("make_hatch_cover",)), ("charcoal", ("make_charcoal",))]

def _cancellations_for(recipe, cancels):
    if not recipe:
        return []
    out = []
    for job, reason in cancels:
        text = (job + " " + (reason if not job else "")).lower()
        if any(k in text and recipe in rs for k, rs in _CANCEL_KEYS) and reason not in out:
            out.append(reason)
    return out[:3]

def _parse_cancels(obs):
    out = []
    for t in obs.get("recent_cancellations") or []:
        if " cancels " in t:
            job, _, reason = t.split(" cancels ", 1)[1].partition(":")
            out.append((job.strip(), reason.strip()))
    return out

def observe():
    obs = _lua_json(os.path.join(DFP, "observe2.lua"))
    _assign_sites(obs.get("map") or {})
    _mark_used(obs)
    obs["plugins"] = plugin_state()
    return diagnose(obs)

# --- what the model sees (HARNESS-PLAN 1.4, 1.6): the observation as compact text, and the history window ---------
# observe() returns the full dict; the reference policies (policies.py) and the site resolver read that. The model
# gets render_obs(): the same facts in fewer tokens. Dropped on purpose: dwarf and squad-member names (ids and
# professions identify them), abs_tick, map size, threats.note (in the manual), per-order job/reaction when the
# recipe is known, and names in cancellation reports. Hostiles are grouped (race, weapons, dist range, bounding box,
# id ranges) and squad members by weapon, with their dist range instead of positions (pre-freeze: raid observation
# 1.7k -> 1.5k Qwen3 tokens). Lists are capped (OBS_CAPS), with a count of what was left out.
OBS_CAPS = {"dwarves": 30, "hostile_groups": 6, "orders": 15, "recent_events": 5, "recent_cancellations": 5,
            "recent_actions": 8, "sites": 5, "sites_G": 2}
OBS_ORDER = ("goal", "scenario", "date", "days_left_in_run", "hands_off_in_days", "interruptions", "threats", "moods",
             "water_on_fort_levels", "stressed_citizens",
             "administrators", "stocks", "orders", "plants_shared", "workshops", "farm_plots", "zones", "dwarves",
             "military", "burrows", "doors", "dig_designations_pending", "plugins", "wealth", "recent_cancellations",
             "recent_events", "recent_actions", "map")
OLD_OBS = "stub"   # smoke.py --old-obs: older observations in the history window become one line ("full": kept whole)
SEASONS = ["spring", "summer", "autumn", "winter"]


def _at(d, z="z"):
    return f"{d.get('x')},{d.get('y')},{d.get(z)}"


def _cap(xs, n):
    xs = list(xs or [])
    return xs[:n] + ([f"+{len(xs) - n} more"] if len(xs) > n else [])


def _site(s):
    t = _at(s)
    if s.get("w") and s.get("h"):
        t += f" {s['w']}x{s['h']}"
    if s.get("stair") is not None:   # room sites: listed until dug (harness2.act refuses to farm them before)
        t += " undug"
    if s.get("soil"):
        t += " soil"
    if isinstance(s.get("stair"), dict):
        t += f" stair={s['stair'].get('x')},{s['stair'].get('y')}"
    if s.get("open_tiles") is not None:
        t += f" open={s['open_tiles']}"
    if s.get("kind") and s["kind"] != "down_stair":
        t += " " + str(s["kind"])
    return t


def _action(e):
    """recent_actions entry (smoke._log_entry) -> one line: day, call, outcome."""
    if not isinstance(e, dict):
        return e
    a = e.get("args")
    args = ",".join(f"{k}={json.dumps(v, separators=(',', ':'))}" for k, v in a.items()) if isinstance(a, dict) else str(a)
    out = "error " + str(e["error"]) if "error" in e else "ok"
    ok = str(e.get("ok") or "")
    if "stopped early" in ok:   # 'stopped after 0.2 days: hostile_approaching'
        out = "stopped" + ok.split("stopped early", 1)[1].rstrip()
    return f"d{e.get('day')} {e.get('tool')}({args}): {out}"


def _cancel(t):
    """'<name>, <profession> cancels <job>: <reason>' -> '<job>: <reason>'."""
    t = t.split(" cancels ", 1)[1].strip() if " cancels " in t else t
    return t[2:] if t.startswith(": ") else t   # cooking reports have no job name


def _counted(xs, n, width=140):
    out, seen = [], {}
    for x in xs or []:
        x = str(x)[:width]
        if x in seen:
            seen[x] += 1
        else:
            seen[x] = 1; out.append(x)
    return _cap([x + (f" (x{seen[x]})" if seen[x] > 1 else "") for x in out], n)


def _ids(ids):
    """[388, 389, 391, 392, 393] -> '388-389,391-393'."""
    out, ids = [], sorted(i for i in ids if isinstance(i, int))
    for i in ids:
        if out and i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return ",".join(f"{a}" if a == b else f"{a}-{b}" for a, b in out)


def _box(us):
    """Units with x,y,z -> 'x' or 'x1-x2' per axis: '98-103,184-186,106'."""
    r = lambda k: (lambda v: f"{min(v)}" if min(v) == max(v) else f"{min(v)}-{max(v)}")([u.get(k, 0) for u in us])
    return ",".join(r(k) for k in ("x", "y", "z"))


def _hostile_groups(hs, inv_races):
    """Visible hostiles -> one line per group of the same race within 10 tiles (and 1 z-level) of its first unit."""
    groups = []
    for h in sorted(hs, key=lambda h: (h.get("dist_to_wagon", 0), h.get("id", 0))):
        k = (h.get("race"), bool(h.get("invader")))
        g = next((g for g in groups if g[0] == k and max(abs(h.get("x", 0) - g[1][0].get("x", 0)),
                  abs(h.get("y", 0) - g[1][0].get("y", 0))) <= 10 and abs(h.get("z", 0) - g[1][0].get("z", 0)) <= 1), None)
        if g:
            g[1].append(h)
        else:
            groups.append((k, [h]))
    out = []
    for (race, inv), us in groups:
        w = {}
        for u in us:
            w[u.get("weapon") or "unarmed"] = w.get(u.get("weapon") or "unarmed", 0) + 1
        ds = [u.get("dist_to_wagon", 0) for u in us]
        n_in = sum(1 for u in us if u.get("in_shelter"))
        arms = (", ".join(f"{n} {k}" for k, n in sorted(w.items(), key=lambda x: -x[1])) if len(us) > 1 else next(iter(w)))
        out.append(f"{len(us)} {race}" + (" invader" if inv or race in inv_races else "") + f" ({arms})" +
                   f" dist={min(ds)}" + (f"-{max(ds)}" if max(ds) != min(ds) else "") + f" @{_box(us)}" +
                   (f" {n_in} in_shelter" if n_in else "") + f" ids={_ids([u.get('id') for u in us])}")
    return out


def _dist(u, w):
    """observe2.lua's dist_to_wagon: max of |dx|,|dy|, plus 3 per z-level."""
    return max(abs(u.get("x", 0) - w.get("x", 0)), abs(u.get("y", 0) - w.get("y", 0))) + 3 * abs(u.get("z", 0) - w.get("z", 0))


def _squad(q, wagon=None):
    """A squad dict (observe2.lua) -> compact: orders, uniform, armed n/m, members by weapon, and how far from the
    wagon they are (the same dist as threats.hostiles, so the two compare directly)."""
    ms = [x for x in q.get("members") or [] if isinstance(x, dict)]
    by = {}
    for x in ms:
        k = str(x["weapon"]).strip("()") if x.get("weapon") else "unarmed" + ("" if x.get("weapon_assigned") else ", none assigned")
        by.setdefault(k, []).append(str(x.get("id")))
    orders = []
    for o in q.get("orders") or []:
        if not isinstance(o, dict):
            continue
        if o.get("order") == "attack":
            orders.append(f"attack: {o.get('targets_alive')} of {o.get('targets')} targets alive")
        elif o.get("order") == "station":
            orders.append(f"station @{_at(o)}")
        else:
            orders.append(str(o.get("order")))
    r = {"on_duty": bool(q.get("on_duty"))}
    if orders:
        r["orders"] = orders
    r["uniform"] = q.get("uniform")
    r["armed"] = f"{q.get('armed', 0)}/{len(ms)}"
    lead = next((x.get("id") for x in ms if x.get("leader")), None)
    if lead is not None:
        r["leader"] = lead
    if by:
        r["members"] = {k: " ".join(v) for k, v in by.items()}
    if ms and isinstance(wagon, dict) and all("x" in x for x in ms):
        ds = [_dist(x, wagon) for x in ms]
        r["dist"] = f"{min(ds)}" + (f"-{max(ds)}" if max(ds) != min(ds) else "")
    return r


def _dwarf(x):
    """'88 Carpenter|MakeBarrel|3', '86 MANAGER|PrepareMeal|3' (a profession that is just the position's title is
    replaced by the position), '|org N' only when the organizer skill is above 0, then any other positions."""
    pos, prof = list(x.get("positions") or []), x.get("profession")
    if pos and str(prof).upper().replace(" ", "_") == pos[0]:
        prof = pos.pop(0)
    t = f"{x.get('id')} {prof}|{x.get('job')}|{x.get('stress')}"
    if x.get("organizer_skill"):
        t += f"|org {x['organizer_skill']}"
    if pos:
        t += "|" + ",".join(pos)
    return t


def render_obs(obs):
    """observe()'s dict (plus the loop's additions) -> the compact dict the model sees. Pure; doesn't change obs."""
    o = dict(obs)
    r = {k: o.pop(k) for k in list(o) if isinstance(o[k], str) and o[k].startswith("ERR")}   # observe2.lua try() failures
    names = {d.get("name"): d.get("id") for d in o.get("dwarves") or [] if isinstance(d, dict)}
    d = o.pop("date", None)
    if isinstance(d, dict):
        r["date"] = {"year": d.get("year"), "season": d.get("season"), "day": d.get("day_of_year")}
    adm = o.pop("administrators", None)
    if isinstance(adm, dict):
        adm = dict(adm)
        office, needs = adm.pop("manager_office", None), adm.pop("manager_needs_office", None)
        a = {k: names.get(v, v.split(",")[0]) for k, v in sorted(adm.items())
             if isinstance(v, str) and v != "VACANT"}
        vac = sorted(k for k, v in adm.items() if v == "VACANT")
        if vac:
            a["vacant"] = vac
        a["manager_active_for_orders"] = bool(adm.get("manager_active_for_orders"))
        if office is not None:
            a["manager_office"] = (f"zone {office.get('zone_id')}" + ("" if office.get("chair") else ", no built chair")
                                   if isinstance(office, dict) else "none")
            if needs:
                a["manager_office"] += " (needed: 20+ citizens)"
        r["administrators"] = a
    st = o.pop("stocks", None)
    if isinstance(st, dict):
        s = {}
        for k, v in sorted(st.items()):
            if k == "seeds_by_kind" and isinstance(v, dict):
                v = {kind: f"{x.get('n')}" + (" underground" if x.get("underground") else "") + " " +
                     ("all seasons" if set(x.get("seasons") or []) == set(SEASONS) else ",".join(x.get("seasons") or []))
                     for kind, x in sorted(v.items()) if isinstance(x, dict)}
            elif k == "plants_by_kind" and isinstance(v, dict):
                v = {kind: " ".join([str(x.get("n"))] + [f for f in ("brewable", "cookable") if x.get(f)])
                     for kind, x in sorted(v.items()) if isinstance(x, dict)}
            if v in ({}, []):
                continue
            s[k] = v
        r["stocks"] = s
    orders, shared = [], None
    for x in o.pop("orders", None) or []:
        if not isinstance(x, dict):
            continue
        y = {"id": x.get("id")}
        if x.get("recipe"):
            y["recipe"] = x["recipe"]
        else:
            y["job"] = x.get("job") + (":" + x["reaction"] if x.get("reaction") else "")
        y.update(left=x.get("left"), total=x.get("total"), validated=bool(x.get("validated")))
        for k in ("active", "jobs_in_progress", "repeat", "when", "stuck_because"):
            if x.get(k):
                y[k] = x[k]
        if x.get("recent_cancellations") and not x.get("stuck_because"):
            y["recent_cancellations"] = x["recent_cancellations"]
        shared = shared or x.get("shares_inputs")
        orders.append(y)
    if orders:
        r["orders"] = _cap(orders, OBS_CAPS["orders"])
    if shared:
        r["plants_shared"] = shared
    ws = [f"{w.get('id')} {w.get('type')} @{_at(w)}" + ("" if w.get("built") else " NOT BUILT") +
          (": " + ", ".join(w["jobs"]) if w.get("jobs") else "") for w in o.pop("workshops", None) or [] if isinstance(w, dict)]
    if ws:
        r["workshops"] = ws
    fp = [f"{p.get('id')} @{_at(p)} {p.get('w')}x{p.get('h')}" + ("" if p.get("built") else " NOT BUILT") +
          f" crop={p.get('crop_this_season')} planted={p.get('seeds_or_crops_in_plot')}"
          for p in o.pop("farm_plots", None) or [] if isinstance(p, dict)]
    if fp:
        r["farm_plots"] = fp
    zs = [f"{z.get('id')} {z.get('type')} @{_at(z)} {z.get('w')}x{z.get('h')}" +
          (f" owner={z['owner']}" if z.get("owner") is not None else "") +
          (" has " + ",".join(f"{n} {k}" for k, n in sorted(z["furniture"].items())) if isinstance(z.get("furniture"), dict) else "")
          for z in o.pop("zones", None) or [] if isinstance(z, dict)]
    if zs:
        r["zones"] = zs
    dw = [x for x in o.pop("dwarves", None) or [] if isinstance(x, dict)]
    if dw:
        keep = sorted(dw, key=lambda x: (x.get("stress", 9), x.get("id", 0)))[:OBS_CAPS["dwarves"]]
        keep = sorted(keep, key=lambda x: x.get("id", 0))
        r["dwarves"] = {"n": len(dw), "rows": [_dwarf(x) for x in keep]}
        if len(dw) > len(keep):
            r["dwarves"]["omitted"] = f"{len(dw) - len(keep)} least stressed"
    th = o.pop("threats", None)
    if isinstance(th, dict):
        t = {k: th[k] for k in ("visible_hostiles", "dead_citizens_total", "invaders_dead") if th.get(k) is not None}
        hs = [h for h in th.get("hostiles") or [] if isinstance(h, dict)]
        inv = {k for k, v in (th.get("by_race") or {}).items() if isinstance(v, dict) and v.get("invader")}
        if hs:
            t["hostiles"] = _cap(_hostile_groups(hs, inv), OBS_CAPS["hostile_groups"])
        listed = {}
        for h in hs:
            listed[h.get("race")] = listed.get(h.get("race"), 0) + 1
        more = {k: v.get("n", 0) - listed.get(k, 0) for k, v in sorted((th.get("by_race") or {}).items())
                if isinstance(v, dict) and v.get("n", 0) > listed.get(k, 0)}
        if more:   # observe2.lua lists at most 20 hostiles; by_race counts all visible ones
            t["not_listed"] = {k: f"{n}" + (" invader" if k in inv else "") for k, n in more.items()}
        r["threats"] = t
    mo = [x for x in o.pop("moods", None) or [] if isinstance(x, dict)]
    if mo:   # '123 Fey woodcraft, needs Craftsdwarfs, claimed 45; items: WOOD 0/1'
        r["moods"] = [f"{x.get('unit_id')} {x.get('mood')} {str(x.get('skill') or '?').lower()}" +
                      (f", needs {x['workshop_needed']}" if x.get("workshop_needed") else "") +
                      (f", claimed {x['claimed_building_id']}" if x.get("claimed_building_id") is not None else ", no workshop claimed") +
                      ("; items: " + ", ".join(f"{i.get('material') + ' ' if i.get('material') else ''}{i.get('item')} "
                                               f"{i.get('collected', 0)}/{i.get('quantity')}" for i in x["items_needed"])
                       if x.get("items_needed") else "") for x in mo]
    mil = o.pop("military", None)
    if isinstance(mil, dict):
        m = {"weapons_free": mil.get("weapons_free")}
        sq = [_squad(q, (o.get("map") or {}).get("wagon")) for q in mil.get("squads") or [] if isinstance(q, dict)]
        if sq:
            m["squads"] = sq
        r["military"] = m
    bu = o.pop("burrows", None)
    if isinstance(bu, dict):
        b = {"civilian_alert": True} if bu.get("civilian_alert") else {}
        bl = []
        for x in bu.get("list") or []:
            bb = x.get("bbox") or {}
            bl.append(f"{x.get('id')} {x.get('name')} tiles={x.get('tiles')} citizens_inside={x.get('citizens_inside')}" +
                      (" civ_alert_burrow" if x.get("civ_alert_burrow") else "") +
                      (" @" + ",".join(f"{bb[a + '1']}" + (f"-{bb[a + '2']}" if bb[a + '2'] != bb[a + '1'] else "")
                                       for a in "xyz") if bb else ""))
        if bl:
            b["list"] = bl
        if b:
            r["burrows"] = b
    do = o.pop("doors", None)
    if isinstance(do, dict):
        x = {k: do[k] for k in ("door_items_free", "hatch_cover_items_free") if do.get(k)}
        dl = [f"{e.get('id')} {e.get('kind')} @{_at(e)}" + ("" if e.get("built") else " NOT BUILT") +
              (" locked" if e.get("locked") else "") for e in do.get("list") or [] if isinstance(e, dict)]
        if dl:
            x["list"] = dl
        if x:
            r["doors"] = x
    pl = o.pop("plugins", None)
    if isinstance(pl, dict):
        r["plugins"] = {s: sorted(k for k, v in pl.items() if v == s) for s in ("on", "off")
                        if any(v == s for v in pl.values())}
    for k in ("recent_cancellations", "recent_events"):
        v = o.pop(k, None)
        if v:
            r[k] = _counted([_cancel(t) for t in v] if k == "recent_cancellations" else v[-OBS_CAPS[k]:], OBS_CAPS[k],
                            width=140 if k == "recent_cancellations" else 100)
    it = o.pop("interruptions", None)
    if it:
        r["interruptions"] = [str(x.get("text") if isinstance(x, dict) else x)[:200] for x in it]
    ra = o.pop("recent_actions", None)
    if ra:
        r["recent_actions"] = [_action(e) for e in ra[-OBS_CAPS["recent_actions"]:]]
    mp = o.pop("map", None)
    if isinstance(mp, dict):
        m = {}
        if isinstance(mp.get("wagon"), dict):
            m["wagon"] = _at(mp["wagon"])
        if mp.get("surface_z") is not None:
            m["surface_z"] = mp["surface_z"]
        for prefix, key in SITE_LISTS.items():
            got = [s for s in (mp.get(key) or [])[:OBS_CAPS.get("sites_" + prefix, OBS_CAPS["sites"])] if isinstance(s, dict)]
            if got and all(s.get("id") for s in got):
                m[prefix] = {s["id"]: _site(s) for s in got}
            elif got:   # no ids (bench/ablate.py sites): the list under its own name, as coordinates
                m[key] = [_site(s) for s in got]
        r["map"] = m
    for k in ("stressed_citizens", "dig_designations_pending", "days_left_in_run", "hands_off_in_days", "goal", "scenario"):
        if k in o:
            r[k] = o.pop(k)
    w = o.pop("wealth", None)
    if isinstance(w, dict):
        r["wealth"] = w
    r.update(o)   # anything not handled above (new fields, '<key>: ERR' strings) passes through unchanged
    return {k: r[k] for k in [*[k for k in OBS_ORDER if k in r], *sorted(k for k in r if k not in OBS_ORDER)]}


def obs_text(obs):
    """The user message for one observation."""
    return "OBSERVATION " + json.dumps(render_obs(obs), separators=(",", ":"), ensure_ascii=False)


def _stub(content):
    """An older observation in the window -> one line: the current observation carries the state."""
    try:
        left = json.loads(content[len("OBSERVATION "):]).get("days_left_in_run")
    except (ValueError, AttributeError):
        left = None
    return "OBSERVATION (older, omitted" + (f"; days_left_in_run was {left}" if left is not None else "") + ")"


TOOL_RESULT_OLD = 300   # chars of an older tool result kept in the window (the latest is whole)


def window(messages, history, old_obs=None):
    """The history policy (part of the comparability key): system prompt + the last `history` messages, never
    starting with a tool result; older observations stubbed and older tool results trimmed unless old_obs='full'."""
    m = messages[:1] + messages[1:][-history:]   # not [-N:]: that repeated the system prompt
    while len(m) > 1 and m[1]["role"] == "tool":
        m.pop(1)
    if (old_obs or OLD_OBS) == "full":
        return m
    last_user = max((i for i, x in enumerate(m) if x["role"] == "user"), default=-1)
    last_tool = max((i for i, x in enumerate(m) if x["role"] == "tool"), default=-1)
    out = []
    for i, x in enumerate(m):
        c = x.get("content")
        if i and x["role"] == "user" and i != last_user and isinstance(c, str) and c.startswith("OBSERVATION {"):
            x = {**x, "content": _stub(c)}
        elif x["role"] == "tool" and i != last_tool and isinstance(c, str) and len(c) > TOOL_RESULT_OLD:
            x = {**x, "content": c[:TOOL_RESULT_OLD] + " ...(trimmed)"}
        out.append(x)
    return out

ACT = os.path.join(DFP, "act2.lua")
SHELTER = "Shelter"

def create_burrow(x, y, z, w, h, levels):
    """Burrows screen: paint a box into the Shelter burrow. Done with quickfort's #burrow mode (create the burrow on
    first use and register it with gui/civ-alert), one w x h layer per level from z downward."""
    if z - levels + 1 < 0:
        raise H.Rejected("levels go below the map")
    first = f"a{{name={SHELTER} create=true civalert=true}}({w}x{h})"
    bp = "#burrow start(1;1)\n" + "\n#>\n".join([first] * levels) + "\n"
    with open(os.path.join(H.BP_DIR, "harness_burrow.csv"), "w") as f:
        f.write(bp)
    out = H.dfhack("quickfort", "run", "harness_burrow.csv", "-c", f"{x},{y},{z}", with_stderr=True)
    m = re.search(r"Burrow tiles added: (\d+)", out)
    added = int(m.group(1)) if m else 0
    if not added:
        return {"ok": False, "error_code": "nothing_designated", "error": "no tiles added to the burrow",
                "hint": "the box is off the map or already in the burrow: use another A site", "detail": out[-200:]}
    return {"ok": True, "burrow": SHELTER, "tiles_added": added, "created": "Burrows created: 1" in out,
            "note": "civilian_alert on keeps civilians inside it"}

def _act_raw(name, args):
    """Validate + execute. Returns (result_text, is_error). act() wraps this with sites and error codes."""
    if not isinstance(args, dict):
        return "ERROR: arguments must be an object", True
    try:
        if name in ("dig_room", "dig_stairs"):
            plan = H.validate(name, args)
            if name == "dig_room":
                # never overwrite a stair: a room dug over its own access stair becomes unreachable
                out = H.dfhack("lua", "-f", os.path.join(DFP, "digplan.lua"), str(args["x"]), str(args["y"]),
                               str(args["z"]), str(args["w"]), str(args["h"]))
                keep = set(out.split("KEEP", 1)[-1].split()) if "KEEP" in out else set()
                if keep:
                    rows = [",".join("" if f"{dx},{dy}" in keep else "d" for dx in range(args["w"]))
                            for dy in range(args["h"])]
                    plan = [("bp", "#dig start(1;1)\n" + "\n".join(rows) + "\n", plan[0][2])]
            res = H.act(plan)
            if name == "dig_room" and keep:
                res += f" (kept {len(keep)} existing stair tile(s) so the room stays reachable)"
            zero = re.findall(r"designated 0 tiles at ([\d,]+)", res)
            if zero:
                return _err("nothing_designated", f"{len(zero)} step(s) designated nothing at {', '.join(zero)}",
                            hint="the tile has a building (the wagon covers the 3x3 around map.wagon), is already open, "
                                 "or is not diggable: use another site", result=res), True
            return res, False
        if name == "advance_days":
            return "advance", False          # handled by caller
        if name == "appoint_manager":
            extra = []
            if "dwarf_id" in args:
                extra = [str(H._int(args, "dwarf_id", 0, 10**7))]
            r = _lua_json(os.path.join(DFP, "act2.lua"), "assign_manager", *extra)
        elif name == "build_workshop":
            if args.get("type") not in WORKSHOPS:
                raise Invalid("workshop type", args.get("type"), WORKSHOPS)
            r = _lua_json(os.path.join(DFP, "act2.lua"), "build_workshop", args["type"],
                          str(H._int(args, "x", 0, 400)), str(H._int(args, "y", 0, 400)), str(H._int(args, "z", 0, 300)))
        elif name == "build_farm":
            w = H._int(args, "w", 1, 10) if "w" in args else 3
            h = H._int(args, "h", 1, 10) if "h" in args else 3
            r = _lua_json(os.path.join(DFP, "act2.lua"), "build_farm", str(H._int(args, "x", 0, 400)),
                          str(H._int(args, "y", 0, 400)), str(H._int(args, "z", 0, 300)), str(w), str(h))
            if r.get("ok"):
                sub = H.dfhack("lua", f"print(dfhack.maps.getTileFlags({args['x']},{args['y']},{args['z']}).subterranean)").strip()
                if sub.endswith("false"):
                    r["warning"] = ("this plot is on the SURFACE; none of the starting seeds grow here, so it will "
                                    "stay empty. Farm underground instead (see manual).")
        elif name == "add_order":
            rec = RECIPES.get(args.get("recipe"))
            if not rec:
                raise Invalid("recipe", args.get("recipe"), RECIPES)
            spec = order_spec(rec, args)
            out = H.dfhack("workorder", json.dumps(spec), with_stderr=True)
            ok = out.startswith("Queuing")
            r = {"ok": ok, "result": out[-200:]} if ok else {"ok": False, "error_code": "game_refused",
                                                            "error": "the game refused the order: " + out[-200:]}
            if ok:
                r["reminder"] = f"runs at a built {rec['workshop']}; needs {rec['needs']}"
                if "frequency" in spec:
                    r["repeat"] = (f"re-queues {spec['amount_total']} {args['repeat']}"
                                   + (" when " + ", ".join(f"{c['stock']} {'below' if 'below' in c else 'at least'} "
                                                           f"{c.get('below', c.get('at_least'))}" for c in args['when'])
                                      if args.get("when") else ""))
        elif name == "cancel_order":
            r = _lua_json(os.path.join(DFP, "act2.lua"), "cancel_order", str(H._int(args, "order_id", 0, 10**6)))
        elif name == "create_squad":
            ids = args.get("dwarf_ids")
            if ids is not None:
                if (not isinstance(ids, list) or not 1 <= len(ids) <= 10 or len(set(map(str, ids))) != len(ids)
                        or not all(isinstance(i, int) and not isinstance(i, bool) and 0 <= i <= 10**7 for i in ids)):
                    raise H.Rejected("dwarf_ids must be 1-10 distinct citizen ids")
                r = _lua_json(ACT, "create_squad", str(len(ids)), *map(str, ids))
            else:
                r = _lua_json(ACT, "create_squad", str(H._int(args, "size", 1, 10) if "size" in args else 4))
        elif name == "equip_squad":
            if args.get("uniform") not in ("weapon_only", "leather", "metal"):
                raise H.Rejected("uniform must be weapon_only, leather or metal")
            r = _lua_json(ACT, "equip_squad", args["uniform"])
        elif name == "squad_order":
            order = args.get("order")
            if order == "attack":
                ids = args.get("target_ids") or []
                if not isinstance(ids, list) or len(ids) > 20 or not all(
                        isinstance(i, int) and not isinstance(i, bool) and 0 <= i <= 10**7 for i in ids):
                    raise H.Rejected("target_ids must be up to 20 unit ids")
                r = _lua_json(ACT, "squad_order", "attack", *map(str, ids))
            elif order == "station":
                r = _lua_json(ACT, "squad_order", "station", str(H._int(args, "x", 0, 400)),
                              str(H._int(args, "y", 0, 400)), str(H._int(args, "z", 0, 300)))
            elif order == "stand_down":
                r = _lua_json(ACT, "squad_order", "stand_down")
            else:
                raise H.Rejected("order must be attack, station or stand_down")
        elif name == "create_burrow":
            r = create_burrow(H._int(args, "x", 0, 400), H._int(args, "y", 0, 400), H._int(args, "z", 0, 300),
                              H._int(args, "w", 1, 40), H._int(args, "h", 1, 40),
                              H._int(args, "levels", 1, 5) if "levels" in args else 1)
        elif name == "civilian_alert":
            if not isinstance(args.get("on"), bool):
                raise H.Rejected("on must be true or false")
            r = _lua_json(ACT, "civ_alert", "on" if args["on"] else "off")
        elif name == "build_door":
            if args.get("kind") not in ("door", "hatch"):
                raise H.Rejected("kind must be door or hatch")
            r = _lua_json(ACT, "build_door", args["kind"], str(H._int(args, "x", 0, 400)),
                          str(H._int(args, "y", 0, 400)), str(H._int(args, "z", 0, 300)))
        elif name == "build_wall":
            r = _lua_json(ACT, "build_wall", str(H._int(args, "x", 0, 400)), str(H._int(args, "y", 0, 400)),
                          str(H._int(args, "z", 0, 300)))
        elif name == "lock_door":
            if not isinstance(args.get("locked"), bool):
                raise H.Rejected("locked must be true or false")
            extra = [str(H._int(args, "door_id", 0, 10**7))] if "door_id" in args else []
            r = _lua_json(ACT, "lock_door", "on" if args["locked"] else "off", *extra)
        elif name == "place_furniture":
            if args.get("kind") not in FURNITURE:
                raise H.Rejected(f"kind must be one of {sorted(FURNITURE)}")
            box = [str(H._int(args, k, 0, 400)) for k in ("x", "y", "z")] + [str(H._int(args, k, 1, 40) if k in args else 1) for k in ("w", "h")]
            count = H._int(args, "count", 1, 30) if "count" in args else 1
            # v2: up to count items, one per tile; a tile quickfort rejects ("Buildings designated: 0") is skipped
            # and the next candidate tried, instead of failing on the same tile every call
            r = _lua_json(os.path.join(DFP, "place.lua"), args["kind"], *box, str(min(400, 4 * count + 8)))
            if r.get("ok"):
                placed, rejected, detail = [], 0, ""
                want = min(count, r.get("available", count))
                for x, y, z in r.get("tiles") or [[r["x"], r["y"], r["z"]]]:
                    if len(placed) >= want:
                        break
                    out = _quickfort(f"#build\n{FURNITURE[args['kind']]}\n", x, y, z)
                    n = re.search(r"Buildings designated: (\d+)", out)
                    if n and int(n.group(1)) > 0:
                        placed.append([x, y, z])
                    else:
                        rejected += 1; detail = out[-160:]
                if placed:
                    r = {"ok": True, "placed": args["kind"], "n": len(placed), "at": placed if count > 1 else placed[0],
                         "note": "a dwarf carries each item there and installs it (usually within a day)"}
                    if len(placed) < count:
                        r["short"] = (f"placed {len(placed)} of {count}: " +
                                      (f"only {want} free item(s)" if len(placed) == want else "no more usable tiles in the site"))
                    if rejected:
                        r["tiles_rejected"] = rejected
                else:
                    r = {"ok": False, "error_code": "no_space", "error": f"could not place a {args['kind']}: the game refused "
                         f"{rejected} free-looking tile(s) in the site", "hint": "use another A or R site", "detail": detail}
        elif name == "make_zone":
            if args.get("kind") not in ZONES:
                raise H.Rejected(f"kind must be one of {sorted(ZONES)}")
            x, y, z = H._int(args, "x", 0, 400), H._int(args, "y", 0, 400), H._int(args, "z", 0, 300)
            w = H._int(args, "w", 1, 20) if "w" in args else 3
            h = H._int(args, "h", 1, 20) if "h" in args else 3
            key = ZONES[args["kind"]]
            out = _quickfort("#zone\n" + "\n".join([",".join([key] * w)] * h) + "\n", x, y, z)
            n = re.search(r"Zones designated: (\d+)", out)
            t = re.search(r"Zone tiles designated: (\d+)", out)
            r = ({"ok": True, "zone": args["kind"], "tiles": int(t.group(1)) if t else None, "at": [x, y, z, w, h],
                  "zone_id": _lua_json(ACT, "zone_at", str(x), str(y), str(z)).get("zone_id")}
                 if n and int(n.group(1)) > 0 else {"ok": False, "error_code": "no_space", "error": "no zone made: no suitable tiles",
                                                    "hint": "zone a dug A or R site", "detail": out[-160:]})
        elif name == "assign_zone":
            r = _lua_json(ACT, "assign_zone", str(H._int(args, "zone_id", 0, 10**7)), str(H._int(args, "dwarf_id", 0, 10**7)))
        elif name == "enable_automation":
            if args.get("name") not in AUTOMATION:
                raise Invalid("automation", args.get("name"), AUTOMATION)
            before = plugin_state().get(args["name"])
            H.dfhack("enable", args["name"])
            after = plugin_state().get(args["name"])
            r = {"ok": after == "on", "was": before, "now": after}
            if after != "on":
                r.update(error_code="not_enabled", error=f"{args['name']} did not turn on (now {after})")
            if before == "on":
                r["note"] = "was already on; no change"
        else:
            raise H.Rejected("unreachable")
    except Invalid as e:      # a value outside its enum: say which, and list the allowed ones
        return _err("bad_arguments", str(e), allowed=e.allowed, hint="use a value from allowed"), True
    except H.Rejected as e:   # argument validation
        return _err("bad_arguments", str(e)), True
    ok = bool(r.get("ok"))
    return ("" if ok else "ERROR: ") + json.dumps(r), not ok


# --- sites and structured errors (HARNESS-PLAN 1.3, 1.7) -------------------------------------------------------------
# observe() gives each candidate site in obs["map"] an id; tools accept site="<id>" instead of coordinates.
SITE_LISTS = {"W": "free_3x3_sites_near_wagon", "F": "underground_soil_farm_sites",
              "G": "surface_soil_sites_NOT_for_starting_seeds", "E": "surface_entrances", "D": "doorways",
              "A": "underground_dug_areas", "S": "stair_sites", "R": "room_sites"}
SITE_KINDS = {"place_furniture": ("A", "R"), "make_zone": ("A", "R"), "build_workshop": ("W",),
              "build_farm": ("F", "R", "G"),   # R: farm the room you dug (same tiles)
              "build_door": ("E", "D"), "build_wall": ("D",), "create_burrow": ("A", "R"), "dig_stairs": ("S",),
              "dig_room": ("R",)}
SITES = {}      # id -> site dict, from the last observation
_SITE_IDS = {}  # (prefix, x, y, z) -> id, for the whole run: a site keeps its id, and ids are never reused
_SITE_N = {}
_ROOMS = {}     # every room site seen this run, by id

CURRENT = set()   # ids listed in the last observation
_USED = {}        # dug room id -> {"farm": "farm plot 4", "zone": ...}: what covers it now (from the last observation)

def _assign_sites(m):
    SITES.clear(); CURRENT.clear()
    for prefix, key in SITE_LISTS.items():
        for site in m.get(key) or []:
            k = (prefix, site.get("x"), site.get("y"), site.get("z"))
            if k not in _SITE_IDS:
                _SITE_N[prefix] = _SITE_N.get(prefix, 0) + 1
                _SITE_IDS[k] = f"{prefix}{_SITE_N[prefix]}"
            site["id"] = _SITE_IDS[k]
            SITES[site["id"]] = site; CURRENT.add(site["id"])
            if prefix == "R":
                _ROOMS[site["id"]] = site
    for rid, room in _ROOMS.items():   # a dug room drops out of room_sites; keep its id for build_farm
        SITES.setdefault(rid, room)

def _overlap(a, b):
    """Two x,y,z,w,h boxes (top-left) on the same z-level share a tile."""
    try:
        return (a["z"] == b["z"] and a["x"] < b["x"] + b.get("w", 1) and b["x"] < a["x"] + a.get("w", 1)
                and a["y"] < b["y"] + b.get("h", 1) and b["y"] < a["y"] + a.get("h", 1))
    except (KeyError, TypeError):
        return False


def _mark_used(obs):
    """Dug rooms keep their ids (they leave map.R), so note which are now covered by a farm plot or a zone."""
    _USED.clear()
    for rid, room in _ROOMS.items():
        if rid in CURRENT:   # still listed: not dug yet
            continue
        for kind, key in (("farm", "farm_plots"), ("zone", "zones")):
            for b in obs.get(key) or []:
                if isinstance(b, dict) and _overlap(room, {**b, "w": b.get("w") or 1, "h": b.get("h") or 1}):
                    _USED.setdefault(rid, {}).setdefault(kind, f"{'farm plot' if kind == 'farm' else b.get('type', 'zone')} {b.get('id')}")


# what makes a dug room unusable for each tool that takes one: a farm plot covers its floor; a zone is already there
_USED_BY = {"build_farm": ("farm",), "place_furniture": ("farm",), "make_zone": ("farm", "zone"), "create_burrow": ()}


def _used(name, sid):
    """-> what occupies a remembered room for this tool ("farm plot 4"), or None."""
    u = _USED.get(sid) or {}
    return next((u[k] for k in _USED_BY.get(name, ()) if k in u), None)


def _valid(name):
    """Site ids a tool accepts now, best first (build_farm: underground before surface)."""
    ok = [k for p in SITE_KINDS.get(name, ()) for k in SITES if k[:1] == p and _usable(name, k)
          and not (name in _USED_BY and p == "R" and k in CURRENT)   # still listed in map.R: not dug yet
          and not (name == "build_farm" and p == "R" and not SITES[k].get("soil"))]   # farms need soil
    return ok[:8]

def _usable(name, sid):
    """Remembered (already dug) rooms count for the tools that use a dug room: farms, furniture, zones."""
    return sid in CURRENT or (name in _USED_BY and sid in _ROOMS and not _used(name, sid))

def _hint(name):
    if name == "build_farm" and not any(k[:1] in "FR" and _usable(name, k) for k in SITES):
        return "no underground soil farm site yet: dig_stairs from an S site, then dig_room at an R site; the dug room becomes a farm site"
    if name == "dig_room" and not any(k[:1] == "R" and k in CURRENT for k in SITES):
        return "no room site yet: dig_stairs down from an S site first; R sites appear beside the dug stair"
    return None

def _resolve_site(name, args):
    """site="W2" -> the site's coordinates in the argument names the tool expects. Returns (args, error_or_None)."""
    if "site" not in args:
        need = ("x", "y", "z_top") if name == "dig_stairs" else ("x", "y", "z")
        if name in SITE_KINDS and any(k not in args for k in need):
            return args, _err("missing_location", "no location given", valid=_valid(name),
                              hint=_hint(name) or f"give site=<id> or {','.join(need)}")
        return args, None
    sid = str(args["site"]).strip().upper()
    kinds = SITE_KINDS.get(name)
    if not kinds:
        return args, _err("bad_arguments", f"{name} takes no site")
    if sid[:1] not in kinds:
        return args, _err("wrong_site_kind", f"{name} takes a {'/'.join(kinds)} site, not {sid}", valid=_valid(name),
                          **({"hint": _hint(name)} if _hint(name) else {}))
    site = SITES.get(sid) if _usable(name, sid) else None
    if not site and (_used(name, sid) or sid in _SITE_IDS.values()):   # a farmed/zoned room, or a site gone from map
        ok = _valid(name)
        return args, _err("site_used", f"room {sid} is already used ({_used(name, sid)})" if _used(name, sid)
                          else f"site {sid} is no longer listed (used up or blocked)", valid=ok,
                          hint=_hint(name) or ("use a site from valid" if ok else
                                               "dig_room another R site first" if name in _USED_BY else
                                               "no such site is listed now"))
    if not site:
        return args, _err("unknown_site", f"no site {sid} in the last observation", valid=_valid(name),
                          **({"hint": _hint(name)} if _hint(name) else {}))
    a = {k: v for k, v in args.items() if k != "site"}
    if name == "dig_stairs":
        a.update(x=site["x"], y=site["y"], z_top=site["z"])
        a.setdefault("z_bottom", site["z"] - 1)
    else:
        a.update(x=site["x"], y=site["y"], z=site["z"])
        if name in ("build_farm", "create_burrow", "dig_room", "place_furniture", "make_zone"):
            a.setdefault("w", site.get("w", 3)); a.setdefault("h", site.get("h", 3))
    return a, None

ERROR_CODES = [   # (pattern in the error text, code); first match wins
    (r"already has a building|occupied", "tile_occupied"), (r"not soil floor", "not_soil_floor"),
    (r"designated 0 tiles|designated nothing", "nothing_designated"),
    (r"fire-safe", "needs_stone"), (r"no usable building material|no free .* item|no .* item", "no_material"),
    (r"already holds a position|already assigned", "already_assigned"), (r"no order with id", "no_such_order"),
    (r"no squad", "no_squad"), (r"no free floor tile|could not place|no suitable tiles", "no_space"), (r"not built|unbuilt", "not_built"), (r"unknown|not allowed|allowlist", "bad_arguments"),
    (r"must be|expected|unexpected arguments|integer", "bad_arguments"),
]

# A one-line default hint per error_code, for errors that don't bring their own (HARNESS-PLAN 1.7). The hint says
# what to do; the error says what failed (bench/ablate.py hints removes the hint and keeps the error).
ERROR_HINTS = {
    "bad_arguments": "check the tool's parameters and allowed values",
    "missing_location": "give site=<id> from map",
    "wrong_site_kind": "use a site of the kind the tool takes",
    "unknown_site": "use a site id listed in the latest observation's map",
    "room_not_dug_yet": "dig_room the R site first",
    "site_used": "use a site from valid",
    "unknown_tool": "call one of the listed tools",
    "one_tool_per_turn": "only the first tool call of a turn runs",
    "tile_occupied": "use another site",
    "not_open_floor": "use a W site",
    "not_soil_floor": "farm plots need soil: use an F site, or a dug R room listed with soil",
    "nothing_designated": "use another site",
    "needs_stone": "mine stone first (dig into rock), then build",
    "no_material": "make or collect the item first (stocks)",
    "already_assigned": "the position is filled; see administrators",
    "no_such_order": "use an id from orders[]",
    "no_squad": "create_squad first",
    "squad_exists": "use the existing squad: equip_squad, then squad_order",
    "not_eligible": "use ids from dwarves.rows without positions, or give size instead",
    "no_position": "this fortress can't have a squad",
    "not_a_citizen": "use an id from dwarves.rows",
    "not_a_hostile": "use ids from threats.hostiles, or omit target_ids",
    "no_hostiles": "threats has no hostiles: station the squad or stand_down",
    "tile_hidden": "use a revealed tile, e.g. a listed site",
    "not_walkable": "use a floor or stair tile, e.g. a listed site",
    "no_burrow": "create_burrow on an A site first",
    "wrong_tile_shape": "use an E site",
    "no_doors": "build_door on an E site first",
    "no_such_door": "use an id from doors.list",
    "no_such_zone": "use an id from zones[]",
    "not_assignable": "only office and bedroom zones have an owner",
    "no_space": "use another A or R site",
    "not_built": "wait until it is built (advance_days)",
    "not_enabled": "the helper didn't start; carry on without it",
    "game_refused": "try another site or option",
    "internal_error": "a harness problem, not your call; carry on",
    "failed": "the call failed; read the error",
}


def _err(code, msg, **extra):
    extra.setdefault("hint", ERROR_HINTS.get(code))
    return "ERROR: " + json.dumps({"ok": False, "error_code": code, "error": msg,
                                   **{k: v for k, v in extra.items() if v is not None}})

def _structured(result):
    """Any error result -> 'ERROR: {"ok": false, "error_code": ..., "error": ..., ...}'."""
    body = result[len("ERROR: "):] if result.startswith("ERROR: ") else result
    try:
        d = json.loads(body)
        if not isinstance(d, dict):
            raise ValueError
    except ValueError:
        d = {"error": body}
    d["ok"] = False
    msg = str(d.get("error") or body)
    d.setdefault("error_code", next((c for p, c in ERROR_CODES if re.search(p, msg, re.I)), "failed"))
    if not d.get("hint"):
        d["hint"] = ERROR_HINTS.get(d["error_code"], ERROR_HINTS["failed"])
    return "ERROR: " + json.dumps(d)

def act(name, args):
    """Validate + execute one tool call. Returns (result_text, is_error); errors are structured JSON."""
    if name not in NAMES:
        return _err("unknown_tool", f"no tool named {name!r}", valid_tools=sorted(NAMES)), True
    if not isinstance(args, dict):
        return _err("bad_arguments", "arguments must be a JSON object"), True
    kinds = {"place_furniture": FURNITURE, "make_zone": ZONES}.get(name)
    if kinds is not None and args.get("kind") not in kinds:   # check the kind before the location
        return _err("bad_arguments", f"kind must be one of {sorted(kinds)}"), True
    sid = str(args.get("site", "")).strip().upper()
    if name in ("build_farm", "place_furniture", "make_zone", "create_burrow") and sid[:1] == "R" and sid in CURRENT:   # still in room_sites: the room isn't dug yet
        return _err("room_not_dug_yet", f"room {sid} is not dug yet",
                    hint=f"call dig_room site={sid} first, then advance until dig_designations_pending is 0; the dug room keeps its id"), True
    args, e = _resolve_site(name, args)
    if e:
        return e, True
    res, is_err = _act_raw(name, args)
    return (_structured(res) if is_err else res), is_err


# Every tool that advertises a `site` parameter must resolve sites. An inline comment once hid build_door and
# create_burrow from SITE_KINDS, so site= failed for them ("takes no site") until the Phase 1 A/B caught it.
_site_tools = {t["function"]["name"] for t in TOOLS if "site" in t["function"]["parameters"]["properties"]}
assert _site_tools == set(SITE_KINDS), f"site tools {sorted(_site_tools)} != SITE_KINDS {sorted(SITE_KINDS)}"
