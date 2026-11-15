"""The deterministic playbook: what a competent overseer does every few days, as rules over the Fort view.

plan(fort, mem) returns steps (key, tool, args[, once]) in priority order. Each rule checks mem.may(key) so a
failing step backs off instead of burning actions. Layout (see layout.py) and defence/moods (see crisis.py) are
separate modules; this file holds the core economy: manager, plugins, workshops, orders, farms.
"""
import json

from . import crisis, layout
from .memory import DAY
from .state import ceil_div

PLUGINS = ("autochop", "seedwatch", "autofarm")
ENDGAME_DAYS = 60     # open play: the score reads drink and food over the last quarter of the run (at most 28 days)
                      # and wants both flat or rising there; production is raised a month before that stretch
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
def drink_target(fort, cs):
    """Brew up to this stock. Lab tasks with a hands-off window score drink held or rising through the window, so
    they brew whenever plants allow; open play balances drink against food (1 plant = 5 drinks or 1 food)."""
    if fort.info.get("hands_off"):
        return 2000
    return min(400, 6 * cs + 60)


def plant_reserve(fort, cs):
    """Brewable plants kept back for eating: brew only from plants above this. Lab tasks (hands-off window) need
    drink to hold through the window, so they keep a smaller reserve."""
    if fort.info.get("hands_off"):
        return max(2, cs // 6)
    return max(2, cs // 2)


def endgame(fort):
    """Open-play tasks (no hands-off window) near their horizon."""
    return not fort.info.get("hands_off") and fort.days_left <= ENDGAME_DAYS


def has_standing(fort, recipe):
    return bool(fort.orders_for(recipe, repeat=True))


def scale(c):
    """Citizens rounded up to a multiple of 4: standing-order thresholds follow the fort's size in steps, so a
    standing order is re-issued when the fort has grown (or shrunk) by a step, not on every migrant."""
    return max(4, 4 * ceil_div(max(1, c), 4))


def standing(fort, mem, now, key, args):
    """Keep one standing order per key with these exact arguments: add it when missing; when the arguments have
    changed (the fort's size moved a step), cancel the old one first and add the new one on the next cycle."""
    live = {o.get("id") for o in fort.orders}
    mine = [oid for oid, (k, _) in mem.orders.items() if k == key and oid in live]
    sigs = mem.vals.setdefault("so_sig", {})
    sig = json.dumps(args, sort_keys=True)
    if mine:
        if sigs.get(key) == sig or (fort.hands_off_in is not None and fort.hands_off_in <= 5):
            return []          # unchanged, or too close to a hands-off window to risk a gap between cancel and add
        if mem.may(key + ":cancel", now, 2):
            return [(key + ":cancel", "cancel_order", {"order_id": mine[0]})]
        return []
    if mem.may(key, now, 2):
        sigs[key] = sig
        return [(key, "add_order", args)]
    return []


def order_steps(fort, mem, now):
    out = []
    if not fort.adm.get("manager_active_for_orders") and not fort.adm.get("MANAGER_id"):
        return out
    c = max(1, fort.citizens)
    cs = scale(c)
    built = lambda t: bool(fort.ws(t, built=True)) or bool(fort.ws(t))
    if built("Carpenters"):
        out += standing(fort, mem, now, "so:barrel", {"recipe": "make_barrel", "amount": 2, "repeat": "daily", "when": [
            {"stock": "barrels_empty", "below": 2 + cs // 8}, {"stock": "logs", "at_least": 4}]})
    if built("Still"):
        out += standing(fort, mem, now, "so:brew", {"recipe": "brew_drink", "amount": 3 + cs // 8, "repeat": "daily",
                                                    "when": [{"stock": "drink", "below": drink_target(fort, cs)},
                                                             {"stock": "plants_brewable", "at_least": plant_reserve(fort, cs)}]})
        if not fort.info.get("hands_off"):
            # drink running low: brew from any plant, food reserve or not
            out += standing(fort, mem, now, "so:brew_low", {"recipe": "brew_drink", "amount": 2 + cs // 8, "repeat": "daily",
                                                            "when": [{"stock": "drink", "below": 3 * cs + 10},
                                                                     {"stock": "plants_brewable", "at_least": 2}]})
    if built("Kitchen"):
        # meals keep and raw plants rot, so cooking protects the food count (a cooked plant loses its seed, though):
        # keep about four meals per citizen while there are two food per citizen
        out += standing(fort, mem, now, "so:cook", {"recipe": "cook_meal", "amount": 2 + cs // 10, "repeat": "daily", "when": [
            {"stock": "prepared_meals", "below": 4 * cs}, {"stock": "food", "at_least": 2 * cs},
            # drink first: the kitchen and the still want the same plants
            {"stock": "drink", "at_least": 3 * cs + 10}]})
    if endgame(fort):
        out += endgame_orders(fort, mem, now, built)
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


def endgame_orders(fort, mem, now, built):
    """A second set of standing orders for the scored final stretch: brew to a cap the run can't reach while plants
    stay above a reserve (plants are food too), barrels for it, and meals from surplus food (meals keep, raw plants
    rot). The everyday orders stay in place underneath. Idea credited in NOTE.md (the leader's endgame orders)."""
    out = []
    cs = scale(fort.citizens)
    if built("Still"):
        out += standing(fort, mem, now, "so:brew_end", {"recipe": "brew_drink", "amount": 4 + cs // 6, "repeat": "daily",
                                                        "when": [{"stock": "drink", "below": max(600, 30 * cs)},
                                                                 {"stock": "plants_brewable", "at_least": max(4, cs // 4)},
                                                                 {"stock": "barrels_empty", "at_least": 1}]})
    if built("Carpenters") and fort.s("logs_usable") >= 4:
        out += standing(fort, mem, now, "so:barrel_end", {"recipe": "make_barrel", "amount": 3, "repeat": "daily",
                                                          "when": [{"stock": "barrels_empty", "below": 8 + cs // 5},
                                                                   {"stock": "logs", "at_least": 4}]})
    if built("Kitchen"):
        out += standing(fort, mem, now, "so:cook_end", {"recipe": "cook_meal", "amount": 3 + cs // 8, "repeat": "daily",
                                                        "when": [{"stock": "prepared_meals", "below": max(300, 10 * cs)},
                                                                 {"stock": "food", "at_least": max(30, 4 * cs)},
                                                                 {"stock": "drink", "at_least": 6 * cs}]})
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
