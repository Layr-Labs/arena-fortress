"""Tool schemas and argument handling for game API v0 (docs/GAME-API.md §5.3). Pure Python, no DF.

The 20 frozen v2.1.1 tools keep their names and arguments (harness2.TOOLS); descriptions say what a tool does, not
what to do with it. New in v0:
  * build_workshop takes every workshop type DF allows (the enum comes from DF: query workshop_types);
  * add_order is the frozen form exactly (recipe + frozen `when` stock names); add_manager_order takes any DF
    manager order {job, reaction, material_category, item_subtype, material} with item-type + flags `when`;
  * slaughter {unit_id}.
advance_days is listed (the server runs it: K, tripwires, max 28 days); act() here doesn't execute it.
"""

MAX_DIM = 15            # dig_room w/h (harness.MAX_DIM)
MAX_ADVANCE_DAYS = 28   # docs/GAME-API.md §2.1 limits.max_advance_days

# Frozen recipes (harness2.RECIPES): name -> the manager-order JSON DFHack's workorder takes, plus facts about it.
RECIPES = {
    "brew_drink": {"order": {"job": "CustomReaction", "reaction": "BREW_DRINK_FROM_PLANT"},
                   "workshop": "Still", "needs": "brewable plant + empty barrel", "makes": "5 drinks"},
    "brew_drink_from_fruit": {"order": {"job": "CustomReaction", "reaction": "BREW_DRINK_FROM_PLANT_GROWTH"},
                              "workshop": "Still", "needs": "brewable fruit + empty barrel", "makes": "5 drinks"},
    "make_barrel": {"order": {"job": "MakeBarrel", "material_category": ["wood"]},
                    "workshop": "Carpenters", "needs": "1 log", "makes": "1 barrel"},
    "make_bed": {"order": {"job": "ConstructBed", "material_category": ["wood"]},
                 "workshop": "Carpenters", "needs": "1 log", "makes": "1 bed"},
    "make_door": {"order": {"job": "ConstructDoor", "material_category": ["wood"]},
                  "workshop": "Carpenters", "needs": "1 log", "makes": "1 door"},
    "make_table": {"order": {"job": "ConstructTable", "material_category": ["wood"]},
                   "workshop": "Carpenters", "needs": "1 log", "makes": "1 table"},
    "make_chair": {"order": {"job": "ConstructThrone", "material_category": ["wood"]},
                   "workshop": "Carpenters", "needs": "1 log", "makes": "1 chair"},
    "make_bin": {"order": {"job": "ConstructBin", "material_category": ["wood"]},
                 "workshop": "Carpenters", "needs": "1 log", "makes": "1 bin"},
    "cook_meal": {"order": {"job": "PrepareMeal"},
                  "workshop": "Kitchen", "needs": "2+ cookable ingredients", "makes": "prepared meals"},
    "make_hatch_cover": {"order": {"job": "ConstructHatchCover", "material_category": ["wood"]},
                         "workshop": "Carpenters", "needs": "1 log", "makes": "1 hatch cover"},
    "make_charcoal": {"order": {"job": "MakeCharcoal"},
                      "workshop": "WoodFurnace", "needs": "1 log", "makes": "charcoal"},
}
# The frozen tool's 9 workshop types: the fallback enum when DF can't be asked (tests).
FROZEN_WORKSHOPS = ["Butchers", "Carpenters", "Craftsdwarfs", "Farmers", "Fishery", "Kitchen", "Masons", "Still",
                    "WoodFurnace"]
AUTOMATION = {"autochop": "fells trees", "autofarm": "sets each farm plot's crop every season from the seeds in stock",
              "seedwatch": "keeps seeds of each crop from being cooked or brewed below a threshold",
              "autolabor": "assigns labors", "autoclothing": "queues clothing orders"}
# Frozen `when` stock names (harness2.ORDER_STOCKS) -> the DF item condition. DF counts the matching items itself;
# a name's DF meaning can differ from the observation field of the same name (docs/game-api-audit.md (d) 9): e.g.
# logs_usable counts every log, food_edible every unrotten cookable item. The item_type/flags form says it exactly.
ORDER_STOCKS = {
    "drink": {"item_type": "DRINK"},
    "prepared_meals": {"item_type": "FOOD"},
    "barrels_empty": {"item_type": "BARREL", "flags": ["empty"]},
    "logs": {"item_type": "WOOD"},
    "logs_usable": {"item_type": "WOOD"},
    "food_edible": {"flags": ["unrotten", "cookable"]}, "food": {"flags": ["unrotten", "cookable"]},
    "plants_total": {"item_type": "PLANT", "flags": ["unrotten"]},
    "plants_brewable": {"item_type": "PLANT", "flags": ["unrotten"], "reaction_product": "DRINK_MAT"},
    "boulders": {"item_type": "BOULDER"},
    "beds": {"item_type": "BED"}, "tables": {"item_type": "TABLE"}, "chairs": {"item_type": "CHAIR"},
    "doors": {"item_type": "DOOR"}, "bins": {"item_type": "BIN"},
}
FURNITURE = {"bed": "b", "table": "t", "chair": "c", "door": "d", "container": "h"}   # quickfort #build keys
ZONES = {"bedroom": "b", "dormitory": "D", "dining_hall": "h", "meeting_area": "m", "office": "o"}   # #zone keys
REPEATS = {"daily": "Daily", "monthly": "Monthly", "seasonally": "Seasonally", "yearly": "Yearly"}
UNIFORMS = ("weapon_only", "leather", "metal")

# Which site kinds each tool takes (harness2.SITE_KINDS).
SITE_KINDS = {"place_furniture": ("A", "R"), "make_zone": ("A", "R"), "build_workshop": ("W",),
              "build_farm": ("F", "R", "G"), "build_door": ("E", "D"), "build_wall": ("D",),
              "create_burrow": ("A", "R"), "dig_stairs": ("S",), "dig_room": ("R",)}


class Rejected(Exception):
    """An argument the schema or the tool's rules don't accept (error_code bad_arguments)."""


class Invalid(Rejected):
    """A value outside its enum: the error names it, and `allowed` lists the schema's values."""
    def __init__(self, what, value, allowed):
        super().__init__(f"unknown {what} {value!r}")
        self.allowed = sorted(allowed)


def as_int(a, k, lo=-10**6, hi=10**6):
    v = a.get(k)
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise Rejected(f"{k} must be an integer in [{lo},{hi}]")
    return v


def opt_int(a, k, lo, hi, default):
    return as_int(a, k, lo, hi) if k in a else default


def _name_list(v, what, max_n=10):
    if not isinstance(v, list) or len(v) > max_n or not all(isinstance(s, str) and 0 < len(s) <= 64 for s in v):
        raise Rejected(f"{what} must be a list of up to {max_n} names")
    return list(v)


def _name(v, what):
    if not isinstance(v, str) or not 0 < len(v) <= 80:
        raise Rejected(f"{what} must be a name")
    return v


def _threshold(c, where):
    keys = [k for k in ("below", "at_least") if k in c]
    if not keys:
        raise Rejected(f"{where} needs below or at_least (an integer count)")
    if len(keys) == 2:
        raise Rejected(f"{where} has both below and at_least: give one")
    n = as_int(c, keys[0], 0, 100000)
    return {"condition": "LessThan" if keys[0] == "below" else "AtLeast", "value": n}


def _when_list(when, tool):
    if not isinstance(when, list) or not 1 <= len(when) <= 3:
        raise Rejected(f"{tool} when must be a list of 1-3 conditions")
    for i, c in enumerate(when):
        if not isinstance(c, dict):
            raise Rejected(f"{tool} when[{i}] must be an object")
    return list(enumerate(when))


def stock_conditions(when):
    """add_order `when` (frozen form: {stock, below|at_least}) -> (workorder item_conditions, stock names)."""
    conds, stocks = [], []
    for i, c in _when_list(when, "add_order"):
        where = f"add_order when[{i}]"
        extra = set(c) - {"stock", "below", "at_least"}
        if extra:
            raise Rejected(f"{where} has unexpected fields {sorted(extra)} (it takes stock and below or at_least; "
                           "item-type conditions are add_manager_order's)")
        if "stock" not in c:
            raise Rejected(f"{where} needs stock (one of: {', '.join(sorted(ORDER_STOCKS))})")
        if c["stock"] not in ORDER_STOCKS:
            raise Invalid(f"{where} stock", c["stock"], ORDER_STOCKS)
        conds.append(dict(ORDER_STOCKS[c["stock"]], **_threshold(c, where)))
        stocks.append(c["stock"])
    return conds, stocks


def item_conditions(when):
    """add_manager_order `when` ({item_type, flags?, ..., below|at_least}) -> workorder item_conditions.
    item_type ANY = no item type (then flags are required: a flag-only condition, e.g. unrotten + cookable)."""
    conds = []
    for i, c in _when_list(when, "add_manager_order"):
        where = f"add_manager_order when[{i}]"
        extra = set(c) - {"item_type", "flags", "item_subtype", "material", "reaction_product", "reaction_class",
                          "below", "at_least"}
        if extra:
            raise Rejected(f"{where} has unexpected fields {sorted(extra)}")
        if "item_type" not in c:
            raise Rejected(f"{where} needs item_type (a DF item type such as DRINK, PLANT, BARREL, or ANY with flags)")
        cond = {}
        it = _name(c["item_type"], f"{where} item_type")
        if it.upper() != "ANY":
            cond["item_type"] = it
        if "flags" in c:
            cond["flags"] = _name_list(c["flags"], f"{where} flags")
        if "item_type" not in cond and not cond.get("flags"):
            raise Rejected(f"{where}: item_type ANY needs flags (e.g. [\"unrotten\", \"cookable\"])")
        if "item_subtype" in c:
            if "item_type" not in cond:
                raise Rejected(f"{where} item_subtype needs a real item_type")
            cond["item_subtype"] = _name(c["item_subtype"], f"{where} item_subtype")
        for k in ("material", "reaction_product", "reaction_class"):
            if k in c:
                cond[k] = _name(c[k], f"{where} {k}")
        cond.update(_threshold(c, where))
        conds.append(cond)
    return conds


def _amount_repeat(spec, args, tool):
    if "amount" not in args:
        raise Rejected(f"{tool} needs amount (an integer 1-30)")
    spec["amount_total"] = as_int(args, "amount", 1, 30)
    rep = args.get("repeat")
    if rep is not None:
        if rep not in REPEATS:
            raise Invalid(f"{tool} repeat", rep, REPEATS)
        spec["frequency"] = REPEATS[rep]
    if args.get("when") is not None and rep is None:
        raise Rejected(f"{tool} when needs repeat (daily, monthly, seasonally or yearly): conditions are checked at each repeat")
    return rep


def order_spec(args):
    """add_order (the frozen form) -> (workorder JSON for one order, meta {recipe, stocks}). Raises Rejected."""
    if "recipe" not in args:
        raise Rejected(f"add_order needs recipe (one of: {', '.join(sorted(RECIPES))}); "
                       "for any other DF manager order use add_manager_order")
    rec = RECIPES.get(args["recipe"])
    if not rec:
        raise Invalid("add_order recipe", args["recipe"], RECIPES)
    spec = dict(rec["order"])
    _amount_repeat(spec, args, "add_order")
    stocks = []
    if args.get("when") is not None:
        spec["item_conditions"], stocks = stock_conditions(args["when"])
    return spec, {"recipe": args["recipe"], "stocks": stocks}


def manager_order_spec(args):
    """add_manager_order -> (workorder JSON for one order, meta). Raises Rejected."""
    if "job" not in args:
        raise Rejected("add_manager_order needs job (a df.job_type name, e.g. ConstructBlocks or CustomReaction; "
                       "query manager_order_types); for a frozen recipe such as brew_drink use add_order")
    spec = {"job": _name(args["job"], "add_manager_order job")}
    if "reaction" in args:
        spec["reaction"] = _name(args["reaction"], "add_manager_order reaction")
    if "material_category" in args:
        spec["material_category"] = _name_list(args["material_category"], "add_manager_order material_category", 5)
    if "item_subtype" in args:
        spec["item_subtype"] = _name(args["item_subtype"], "add_manager_order item_subtype")
    if "material" in args:
        spec["material"] = _name(args["material"], "add_manager_order material")
    _amount_repeat(spec, args, "add_manager_order")
    if args.get("when") is not None:
        spec["item_conditions"] = item_conditions(args["when"])
    return spec, {"recipe": None, "stocks": [None] * len(spec.get("item_conditions") or [])}


def recipe_of(order):
    """An observed order (job, reaction, material_category) -> the frozen recipe name, or None."""
    for name, rec in RECIPES.items():
        o = rec["order"]
        if (o["job"] == order.get("job") and o.get("reaction") == order.get("reaction")
                and sorted(o.get("material_category") or []) == sorted(order.get("material_category") or [])):
            return name
    return None


_INT = {"type": "integer"}
_SITE = {"type": "string", "description": "a site id from the observation's sites (e.g. W2)"}


def _fn(name, description, properties, required=()):
    p = {"type": "object", "properties": properties}
    if required:
        p["required"] = list(required)
    return {"type": "function", "function": {"name": name, "description": description, "parameters": p}}


def tool_schemas(workshop_types=None):
    """OpenAI function schemas for every v0 tool. workshop_types: the build_workshop enum (from DF's
    workshop_types query); None falls back to the frozen 9."""
    ws = sorted(workshop_types or FROZEN_WORKSHOPS)
    recipes = "; ".join(f"{k}: {v['workshop']}, {v['needs']} -> {v['makes']}" for k, v in sorted(RECIPES.items()))
    num = {"type": "integer", "minimum": 0, "maximum": 100000}
    thr = "give exactly one of below / at_least"
    stock_cond = {"type": "object", "required": ["stock"], "description": thr, "properties": {
        "stock": {"type": "string", "enum": sorted(ORDER_STOCKS)}, "below": num, "at_least": num}}
    item_cond = {"type": "object", "required": ["item_type"], "description": thr, "properties": {
        "item_type": {"type": "string", "description": "a DF item type (df.item_type), e.g. DRINK, PLANT, BARREL; "
                                                       "ANY = any item type (then flags are required)"},
        "flags": {"type": "array", "items": {"type": "string"}, "maxItems": 10,
                  "description": "DF item condition flags (query manager_order_types: condition_flags), e.g. unrotten, empty"},
        "item_subtype": {"type": "string"}, "material": {"type": "string", "description": "DF material token"},
        "reaction_product": {"type": "string", "description": "e.g. DRINK_MAT"}, "reaction_class": {"type": "string"},
        "below": num, "at_least": num}}
    return [
        _fn("appoint_manager", "Appoint the MANAGER (validates work orders). Omit dwarf_id to pick a citizen without a position.",
            {"dwarf_id": _INT}),
        _fn("build_workshop", "Place a workshop or furnace centred on a W site (or x,y,z). Types and their footprints "
            "and inputs: query workshop_types.", {"type": {"type": "string", "enum": ws}, "site": _SITE}, ("type", "site")),
        _fn("build_farm", "Place a farm plot on soil floor: an F or G site, or a dug R room.", {"site": _SITE}, ("site",)),
        _fn("add_order", "Queue a work order from a frozen recipe. For any other DF manager order (a job type, a "
            "reaction, item-type conditions) use add_manager_order. Recipes: " + recipes,
            {"recipe": {"type": "string", "enum": sorted(RECIPES)},
             "amount": {"type": "integer", "minimum": 1, "maximum": 30},
             "repeat": {"type": "string", "enum": sorted(REPEATS), "description": "re-queue every period"},
             "when": {"type": "array", "minItems": 1, "maxItems": 3, "items": stock_cond,
                      "description": "with repeat: only while all hold, e.g. [{\"stock\": \"drink\", \"below\": 50}]"}},
            ("recipe", "amount")),
        _fn("add_manager_order", "Queue any DF manager order: job is a df.job_type name (query manager_order_types), "
            "with reaction for job CustomReaction. For the frozen recipes (brew_drink, make_bed, ...) use add_order.",
            {"job": {"type": "string"}, "reaction": {"type": "string"},
             "material_category": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
             "item_subtype": {"type": "string"}, "material": {"type": "string", "description": "DF material token"},
             "amount": {"type": "integer", "minimum": 1, "maximum": 30},
             "repeat": {"type": "string", "enum": sorted(REPEATS), "description": "re-queue every period"},
             "when": {"type": "array", "minItems": 1, "maxItems": 3, "items": item_cond,
                      "description": "with repeat: only while all hold, e.g. [{\"item_type\": \"DRINK\", \"below\": 50}]"}},
            ("job", "amount")),
        _fn("cancel_order", "Remove a work order by id.", {"order_id": _INT}, ("order_id",)),
        _fn("enable_automation", "Enable a DFHack plugin. " + "; ".join(f"{k}: {v}" for k, v in AUTOMATION.items()),
            {"name": {"type": "string", "enum": sorted(AUTOMATION)}}, ("name",)),
        _fn("create_squad", "Create the fortress's one squad from dwarf_ids (adult citizens without a position or squad) "
            "or size N (the N with the highest combat skills, then strength). Members keep working until it has an order.",
            {"dwarf_ids": {"type": "array", "items": _INT, "maxItems": 10},
             "size": {"type": "integer", "minimum": 1, "maximum": 10}}),
        _fn("equip_squad", "Give the squad a uniform template: a melee weapon plus that armour, from items that exist.",
            {"uniform": {"type": "string", "enum": list(UNIFORMS)}}, ("uniform",)),
        _fn("squad_order", "Order the squad: attack (all visible hostiles, or target_ids), station at x,y,z, or stand_down.",
            {"order": {"type": "string", "enum": ["attack", "station", "stand_down"]},
             "target_ids": {"type": "array", "items": _INT, "maxItems": 20}, "x": _INT, "y": _INT, "z": _INT}, ("order",)),
        _fn("create_burrow", "Add an A site or a dug R room, `levels` levels down from it, to the Shelter burrow "
            "(the civilian-alert burrow).", {"site": _SITE, "levels": {"type": "integer", "minimum": 1, "maximum": 5}},
            ("site",)),
        _fn("civilian_alert", "Turn the civilian alert on or off (civilians stay in the Shelter burrow while on).",
            {"on": {"type": "boolean"}}, ("on",)),
        _fn("build_door", "Place a hatch cover over a down stair (E site) or a door in a doorway (D site); uses a free "
            "hatch cover / door item.", {"site": _SITE, "kind": {"type": "string", "enum": ["door", "hatch"]}},
            ("kind", "site")),
        _fn("build_wall", "Build a wall on a floor tile (D site) from a log or boulder.", {"site": _SITE}, ("site",)),
        _fn("lock_door", "Lock or unlock a door/hatch by door_id, or all of them if omitted.",
            {"locked": {"type": "boolean"}, "door_id": _INT}, ("locked",)),
        _fn("dig_room", "Designate an R site for digging (default 3x3; w,h to change).",
            {"site": _SITE, "w": {"type": "integer", "minimum": 1, "maximum": MAX_DIM},
             "h": {"type": "integer", "minimum": 1, "maximum": MAX_DIM}}, ("site",)),
        _fn("dig_stairs", "Designate a staircase down from an S site to z_bottom (default one level down).",
            {"site": _SITE, "z_bottom": _INT}, ("site",)),
        _fn("place_furniture", "Place free furniture items, one per free floor tile, in an A site or a dug R room "
            "(count, default 1).", {"kind": {"type": "string", "enum": sorted(FURNITURE)}, "site": _SITE,
                                     "count": {"type": "integer", "minimum": 1, "maximum": 30}}, ("kind", "site")),
        _fn("make_zone", "Make an activity zone on an A site or a dug R room.",
            {"kind": {"type": "string", "enum": sorted(ZONES)}, "site": _SITE}, ("kind", "site")),
        _fn("assign_zone", "Assign an office or bedroom zone to a citizen (the zone's Assign button).",
            {"zone_id": _INT, "dwarf_id": _INT}, ("zone_id", "dwarf_id")),
        _fn("slaughter", "Mark a tame animal of the fortress for slaughter (the animal list's Slaughter button). "
            "A dwarf with the butchery labor slaughters it at a Butchers workshop.", {"unit_id": _INT}, ("unit_id",)),
        _fn("advance_days", f"Let 1-{MAX_ADVANCE_DAYS} in-game days pass. Stops early at a tripwire; the result says which.",
            {"days": {"type": "integer", "minimum": 1, "maximum": MAX_ADVANCE_DAYS},
             "stop_on": {"type": "array", "items": {"type": "string"},
                         "description": "tripwires that stop the advance (default: all)"}}, ("days",)),
    ]


TOOL_NAMES = {t["function"]["name"] for t in tool_schemas()}
SERVER_TOOLS = {"advance_days"}   # executed by gameapi/server (rules, tripwires), not by Game.act

_site_tools = {t["function"]["name"] for t in tool_schemas() if "site" in t["function"]["parameters"]["properties"]}
assert _site_tools == set(SITE_KINDS), f"site tools {sorted(_site_tools)} != SITE_KINDS {sorted(SITE_KINDS)}"
