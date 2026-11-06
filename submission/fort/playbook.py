"""The deterministic playbook: what a competent overseer does every few days, as rules over the Fort view.

plan(fort, mem) returns steps (key, tool, args[, once]) in priority order. Each rule checks mem.may(key) so a
failing step backs off instead of burning actions. Layout (see layout.py) and defence/moods (see crisis.py) are
separate modules; this file holds the core economy: manager, plugins, workshops, orders, farms.
"""
from . import crisis, layout
from .memory import DAY
from .state import ceil_div

PLUGINS = ("autochop", "seedwatch", "autofarm")
KEY_PROFS = ("Miner", "Woodworker", "Woodcutter", "Carpenter", "Planter", "Farmer", "Brewer", "Grower")


def replan_after(tool):
    """Tools whose success changes the sites or stocks the next steps read."""
    return tool in ("build_workshop", "build_farm", "dig_room", "dig_stairs")


def plan(fort, mem):
    now = fort.tick
    steps = []
    if fort.hands_off_in is not None and fort.hands_off_in <= 0:
        return steps
    steps += crisis.steps(fort, mem)
    steps += manager_steps(fort, mem, now)
    steps += plugin_steps(fort, mem, now)
    steps += workshop_steps(fort, mem, now)
    steps += order_steps(fort, mem, now)
    steps += layout.steps(fort, mem)
    # de-duplicate keys (a rule may be reached twice in one cycle)
    seen, out = set(), []
    for s in steps:
        if s[0] not in seen:
            seen.add(s[0])
            out.append(s)
    return out


# --- manager -----------------------------------------------------------------------------------------------------
def pick_manager(fort):
    free = [d for d in fort.dwarves if not d.get("positions") and d.get("adult", True)]
    spare = [d for d in free if not any(p in str(d.get("profession") or "") for p in KEY_PROFS)]
    pool = spare or free
    if not pool:
        return None
    return max(pool, key=lambda d: d.get("organizer_skill") or 0).get("id")


def manager_steps(fort, mem, now):
    if fort.adm.get("manager_active_for_orders") or fort.adm.get("MANAGER_id"):
        return []
    if not mem.may("manager", now, every_days=1):
        return []
    pick = pick_manager(fort)
    return [("manager", "appoint_manager", {"dwarf_id": pick} if pick is not None else {})]


def plugin_steps(fort, mem, now):
    out = []
    for p in PLUGINS:
        if fort.plugins.get(p) != "on" and mem.may("plugin:" + p, now, every_days=2, max_tries=4):
            out.append(("plugin:" + p, "enable_automation", {"name": p}))
    return out


# --- workshops ---------------------------------------------------------------------------------------------------
def wanted_workshops(fort):
    want = [("Carpenters", 1), ("Still", 1), ("Kitchen", 1)]
    logs = fort.s("logs_usable")
    if fort.citizens >= 10 or logs >= 60:
        want.append(("Carpenters", 2))
    if fort.citizens >= 14:
        want.append(("Still", 2))
    bed_gap = fort.citizens + 3 - fort.s("beds")
    if logs >= 20:
        for n in range(3, 2 + min(4, max(0, bed_gap) // 8 + (fort.citizens >= 25))):
            want.append(("Carpenters", n))
    if fort.days_total >= 300 and fort.citizens >= 9 and logs >= 40:
        want.append(("Craftsdwarfs", 1))
    if fort.raw_fish() > 0:
        want.append(("Fishery", 1))
    return want


def workshop_steps(fort, mem, now):
    out = []
    has_mat = fort.s("logs_usable") > 0 or fort.s("boulders_usable") > 0
    if not has_mat:
        return out
    sites = fort.near_wagon(fort.sites_of("W"))
    used = 0
    for typ, n in wanted_workshops(fort):
        if len(fort.ws(typ)) >= n or used >= len(sites):
            continue
        key = f"ws:{typ}:{n}"
        if mem.may(key, now, every_days=2, max_tries=6):
            out.append((key, "build_workshop", {"type": typ, "site": sites[used]["id"]}))
            used += 1
    return out


# --- standing orders ---------------------------------------------------------------------------------------------
def drink_target(fort):
    """Brew up to this stock. Lab tasks with a hands-off window score drink held or rising through the window, so
    they brew whenever plants allow; open play balances drink against food (1 plant = 5 drinks or 1 food)."""
    if fort.info.get("hands_off"):
        return 2000
    return min(400, 6 * max(1, fort.citizens) + 60)


def plant_reserve(fort):
    """Brewable plants kept back for eating: brew only from plants above this. Lab tasks (hands-off window) need
    drink to hold through the window, so they keep a smaller reserve."""
    if fort.info.get("hands_off"):
        return max(2, fort.citizens // 6)
    return max(2, fort.citizens // 2)


def has_standing(fort, recipe):
    return bool(fort.orders_for(recipe, repeat=True))


def order_steps(fort, mem, now):
    out = []
    if not fort.adm.get("manager_active_for_orders") and not fort.adm.get("MANAGER_id"):
        return out
    c = max(1, fort.citizens)
    built = lambda t: bool(fort.ws(t, built=True)) or bool(fort.ws(t))
    if built("Carpenters") and not has_standing(fort, "make_barrel") and mem.may("so:barrel", now, 2, 6):
        out.append(("so:barrel", "add_order", {"recipe": "make_barrel", "amount": 2, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 2 + c // 10}, {"stock": "logs", "at_least": 4}]}))
    if built("Still") and not has_standing(fort, "brew_drink") and mem.may("so:brew", now, 2, 6):
        out.append(("so:brew", "add_order", {"recipe": "brew_drink", "amount": 3 + c // 8, "repeat": "daily", "when": [
            {"stock": "drink", "below": drink_target(fort)},
            {"stock": "plants_brewable", "at_least": plant_reserve(fort)}]}))
    if built("Kitchen") and not has_standing(fort, "cook_meal") and mem.may("so:cook", now, 2, 6):
        out.append(("so:cook", "add_order", {"recipe": "cook_meal", "amount": 2 + c // 10, "repeat": "daily", "when": [
            # cooking a plant returns no seed: cook only from a comfortable surplus
            {"stock": "prepared_meals", "below": 2 * c}, {"stock": "food", "at_least": 4 * c}]}))
    if built("Carpenters"):
        # furniture: beds for everyone (+ a few for migrants), table/chair pairs for half of them (+ spare)
        need = {"make_bed": c + 3 - fort.s("beds"),
                # one table/chair pair per citizen: only about half the pairs land next to each other, and the
                # score wants a seat per two citizens
                "make_table": c + 2 - fort.s("tables"),
                "make_chair": c + 3 - fort.s("chairs")}   # +1: the manager's office chair
        if need["make_bed"] > 4:
            # beds first: every carpenter on them; a first few tables and chairs only
            need["make_table"] = min(need["make_table"], 4 - fort.s("tables"))
            need["make_chair"] = min(need["make_chair"], 5 - fort.s("chairs"))
        if fort.s("logs_usable") >= 3:
            for recipe, n in need.items():
                n -= fort.pending(recipe)
                if n > 0 and mem.may("o:" + recipe, now, 1, None, backoff=True):
                    out.append(("o:" + recipe, "add_order", {"recipe": recipe, "amount": min(30, n)}))
        if (fort.days_total >= 300 and fort.has_ws("Craftsdwarfs") and fort.s("logs_usable") >= 30
                and not fort.orders_for(job="MakeCrafts", repeat=True) and mem.may("so:crafts", now, 3, 4)):
            out.append(("so:crafts", "add_manager_order", {"job": "MakeCrafts", "material_category": ["wood"],
                                                            "amount": 2, "repeat": "daily",
                                                            "when": [{"item_type": "WOOD", "at_least": 25}]}))
    return out


# --- pacing --------------------------------------------------------------------------------------------------------
def advance_days(fort, mem):
    """How many days to let pass now."""
    if fort.day < 3:
        d = 1
    elif crisis.urgent(fort):
        d = 1
    elif layout.busy(fort) or fort.problems():
        d = 2
    else:
        d = 4
    if fort.hands_off_in is not None and fort.hands_off_in > 0:
        d = min(d, fort.hands_off_in)
    return max(1, min(d, max(1, fort.days_left)))
