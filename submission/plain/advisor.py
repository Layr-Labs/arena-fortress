"""Bounded, advisory interpretation of public observations; never calls a game or model endpoint.

Raw observations remain available to the model. Estimates are not scorer predictions.
A failure can suppress an identical retry only within one unchanged public state.
"""
from collections import deque
import hashlib
import json
import math

DAY = 1200
FAILURES = 8
# Only deterministic tool refusals. Provider/server failures and time advances must stay retryable.
RETRY_CODES = frozenset({
    "bad_arguments", "tile_hidden", "tile_occupied", "not_open_floor", "not_soil_floor",
    "needs_stone", "no_material", "nothing_designated", "no_space", "already_assigned",
    "not_a_citizen", "no_such_order", "no_position", "squad_exists", "not_eligible", "no_squad",
    "not_a_hostile", "no_hostiles", "not_walkable", "no_burrow", "wrong_tile_shape", "no_doors",
    "no_such_door", "no_such_zone", "not_assignable", "missing_location", "wrong_site_kind",
    "unknown_site", "site_used", "room_not_dug_yet", "no_such_unit", "not_slaughterable",
})


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def mapping(value):
    return value if isinstance(value, dict) else {}


def records(value):
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def kind(value):
    return str(value or "").lower().replace("_", "").replace(" ", "")


def key(name, args):
    return name + ":" + json.dumps(args, sort_keys=True, separators=(",", ":"))


def office_options(obs, admin):
    """Bounded repair candidates from public facts, not a readiness claim or game action."""
    out = {"manager_id": admin.get("MANAGER_id"),
           "reported_zone_id": mapping(admin.get("manager_office")).get("zone_id")}
    furniture = records(obs.get("furniture"))
    chairs = [f for f in furniture if f.get("built") is True and kind(f.get("kind")) in ("chair", "throne")]
    if isinstance(obs.get("furniture"), list):
        out["built_chairs_listed"] = len(chairs)
        out["furniture_truncated"] = bool(number(obs.get("furniture_total")) and
                                          obs["furniture_total"] > len(furniture))
    if isinstance(obs.get("zones"), list):
        offices = []
        for zone in records(obs["zones"]):
            zid = zone.get("id")
            # Zone furniture counts are built only; furniture_planned and bounding boxes aren't proof.
            count = mapping(zone.get("furniture")).get("chair")
            linked = [f for f in chairs if isinstance(f.get("zone_ids"), list) and zid in f["zone_ids"]]
            if zid is not None and kind(zone.get("type")) == "office" and (
                    (number(count) and count > 0) or linked):
                offices.append({"zone_id": zid, "owner": zone.get("owner"),
                                "built_chair_ids": [f["id"] for f in linked if "id" in f][:4]})
        out["offices_with_built_chair"] = offices[:3]
    # make_zone accepts a site, not arbitrary chair coordinates. Only expose current usable boxes.
    candidates = []
    for site in records(mapping(obs.get("map")).get("sites")):
        if (not isinstance(site.get("id"), str) or site.get("kind") not in ("A", "R") or
                site.get("free") is not True or site.get("used_by") or
                (site["kind"] == "R" and site.get("dug") is not True)):
            continue
        dims = [site.get(k) for k in ("x", "y", "z", "w", "h")]
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in dims):
            continue
        x, y, z, w, h = dims
        if w <= 0 or h <= 0:
            continue
        contained = [f["id"] for f in chairs if "id" in f and
                     all(number(f.get(k)) for k in ("x", "y", "z")) and f["z"] == z and
                     x <= f["x"] < x + w and y <= f["y"] < y + h]
        if contained:
            candidates.append({"site": site["id"], "built_chair_ids": contained[:4]})
    out["site_boxes_with_built_chair"] = candidates[:3]
    return out


def defense_status(obs, population):
    """Describe the single supported squad; suggestions are caps, not autonomous orders."""
    hostile_count = mapping(obs.get("threats")).get("visible_hostiles")
    emergency = number(hostile_count) and hostile_count > 0
    urgent = (["Visible hostiles: protect civilians in a supplied shelter/burrow and assess carried weapons "
               "before fighting. Do not send an unarmed squad into combat; door locks also block civilians."]
              if emergency else [])
    military = mapping(obs.get("military"))
    if not isinstance(military.get("squads"), list):
        return {}, urgent, []
    squads = records(military["squads"])
    if len(squads) != len(military["squads"]):
        return {}, urgent, []
    out = {"squads_listed": len(squads)}
    advice = []
    members_known = all(isinstance(s.get("members"), list) and
                        len(records(s["members"])) == len(s["members"]) for s in squads)
    members = [m for s in squads for m in records(s.get("members"))]
    member_ids = {m["id"] for m in members if isinstance(m.get("id"), int)}
    if members_known:
        out["members_listed"] = len(members)
        if number(population) and population >= len(member_ids):
            out["civilians_outside_squads"] = population - len(member_ids)
    # The API's armed count counts inventory weapons, not uniform assignments.
    if members_known and all(number(s.get("armed")) and 0 <= s["armed"] <= len(s["members"])
                             for s in squads):
        out["armed"] = sum(s["armed"] for s in squads)
        if out["armed"] < len(members):
            advice.append("Some squad members have no carried weapon. Uniform/weapon_assigned is not equipment "
                          "in hand: equip existing gear, allow time to fetch it, then verify military.armed.")
    free = military.get("weapons_free")
    if number(free) and free >= 0:
        out["weapons_free"] = free
    dwarves = records(obs.get("dwarves"))
    adults_outside = {d["id"]: d for d in dwarves if isinstance(d.get("id"), int) and
                      d.get("adult") is True and d.get("squad_id", -1) == -1 and d["id"] not in member_ids}
    eligible = [i for i, d in adults_outside.items() if d.get("positions") == [] and
                not (number(d.get("stress")) and d["stress"] <= 1)]
    if isinstance(obs.get("dwarves"), list):
        out["eligible_ids"] = eligible[:10]
    out["suggested_recruits"] = 0
    if not squads and number(population) and number(free) and free > 0:
        # Keep seven civilians in peace, five under attack, and at least five known adult workers.
        capacity = max(0, int(population) - (5 if emergency else 7))
        workers = max(0, len(adults_outside) - 5)
        out["suggested_recruits"] = min(4, int(free), len(eligible), capacity, workers)
        if out["suggested_recruits"]:
            advice.append(f"Standing guard opportunity: at most {out['suggested_recruits']} recruits, only after "
                          "supply is stable. Preserve essential workers; this cap is not an order to recruit.")
    stressed = sum(d.get("id") in member_ids and number(d.get("stress")) and d["stress"] <= 1
                   for d in dwarves)
    if isinstance(obs.get("dwarves"), list) and members_known:
        out["stressed_members"] = stressed
    on_duty = any(s.get("on_duty") is True for s in squads)
    if on_duty and hostile_count == 0 and (stressed or len(adults_outside) < 5):
        advice.append("Peacetime duty is straining stress or available workers: use stand_down for recovery/work, "
                      "then resume guard duty only when sustainable. Member removal is not supported.")
    elif squads and any(s.get("on_duty") is False for s in squads):
        advice.append("Keep the equipped guard ready: when supply/labor allow, station at a revealed, walkable "
                      "stair choke facing the threat, not an invented coordinate. Stationing is not training.")
    return out, urgent, advice


class Advisor:
    def __init__(self):
        self.samples = deque(maxlen=16)
        self.failures = deque(maxlen=FAILURES)
        self.state = None
        self.epoch = 0

    def observe(self, obs, tick):
        """Build a fresh status; same-tick actions replace the sample, not the prior day's baseline."""
        obs = mapping(obs)
        # Hash only API facts, not harness-added task/advice, and not the wall/turn counters.
        facts = {k: v for k, v in obs.items() if k not in (
            "harness_status", "goal", "scenario", "days_left_in_run", "hands_off_in_days")}
        self.state = hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()
        stocks = mapping(obs.get("stocks"))
        if number(tick):
            if self.samples and tick < self.samples[-1][0]:
                self.samples.clear()
            if self.samples and tick == self.samples[-1][0]:
                self.samples.pop()
            self.samples.append((tick, {s: stocks[s] for s in ("drink", "food_edible")
                                        if number(stocks.get(s))}))
        admin = mapping(obs.get("administrators"))
        population = admin.get("citizens")
        if not number(population):
            population = len(obs["dwarves"]) if isinstance(obs.get("dwarves"), list) else None
        out = {"basis": "public API facts; estimates/advice, not a score", "priorities": [],
               "supply": {}, "housing": {}, "sites": {},
               "recent_failures": [{**{k: f[k] for k in ("tool", "tick", "error_code", "error")},
                                    "args": json.dumps(f["args"], sort_keys=True)[:320]}
                                   for f in self.failures]}
        advice = out["priorities"]
        if number(population):
            out["citizens"] = population
        if admin.get("manager_active_for_orders") is False or admin.get("MANAGER") == "VACANT":
            advice.append("Appoint a manager: unvalidated orders cannot start without one.")
        office = mapping(admin.get("manager_office"))
        has_manager = admin.get("manager_active_for_orders") is True or admin.get("MANAGER_id") is not None
        office_known_missing = admin.get("manager_office") == "none" or office.get("chair") is False
        if has_manager and number(population) and population >= 20 and office_known_missing:
            out["manager_office_repair"] = office_options(obs, admin)
            advice.append("Check manager office: around 20+ citizens validation can require an office zone with a built "
                          "chair assigned to the manager. Assignment ok with chair:false is NOT readiness. See "
                          "manager_office_repair for existing chaired offices/owners or usable site boxes containing "
                          "built chairs; do not keep placing chairs into packed rooms. If making an office, use an "
                          "advertised site and its returned zone_id, then assign_zone to the manager separately. "
                          "Recheck manager_office.chair and order validation after time passes; candidates alone "
                          "prove neither. Do not cancel/re-add while it validates.")
        pending = [o.get("id") for o in records(obs.get("orders")) if o.get("validated") is False]
        if pending:
            out["unvalidated_order_ids"] = pending[:20]
            if has_manager and office.get("chair") is True:
                advice.append("Manager office reports a built chair, but listed orders are still unvalidated. "
                              "Office assignment and manager_active_for_orders are not proof that validation ran. "
                              "Inspect the manager's observed job/needs and access, order state and cancellations; "
                              "allow a short interval and recheck validation before relying on production. "
                              "Do not rebuild/reassign a chaired office or cancel/re-add orders just to refresh them; "
                              "no fixed validation delay is guaranteed.")
        for stock in ("drink", "food_edible"):
            value = stocks.get(stock)
            if not number(value):
                continue
            entry = {"stock": value}
            if number(population) and population > 0:
                entry["per_citizen"] = round(value / population, 2)
            previous = next(((t, s) for t, s in reversed(list(self.samples)[:-1])
                             if number(tick) and t < tick and stock in s), None)
            if previous:
                t, s = previous
                rate = (value - s[stock]) * DAY / (tick - t)
                entry["net_per_day"] = round(rate, 3)
                entry["interval_days"] = round((tick - t) / DAY, 3)
                if rate < 0:
                    entry["estimated_days_at_net_rate"] = round(value / -rate, 1)
                    advice.append(f"{stock} declined at {rate:.2f}/day over the last interval; verify sustainable "
                                  "production before advancing far (short-interval estimate, not a forecast).")
            out["supply"][stock] = entry
        workshops = records(obs.get("workshops"))
        if isinstance(obs.get("workshops"), list):
            stills = [w for w in workshops if w.get("type") == "Still"]
            if not stills:
                advice.append("No Still listed: brewing needs a Still, manager order, brewable plants and empty barrels.")
            elif not any(w.get("built") is True for w in stills):
                advice.append("Still is planned, not built: advance a little and check construction/labors.")
        if stocks.get("plants_brewable") == 0:
            advice.append("No brewable plants: check crops/seeds or suitable fruit reactions; cooking plants destroys seeds.")
        if stocks.get("barrels_empty") == 0:
            advice.append("No empty barrels: brew jobs need an empty barrel; make barrels at a built Carpenters.")
        plugins = mapping(obs.get("plugins"))
        for plugin in ("autolabor", "autochop", "seedwatch", "autofarm"):
            if plugins.get(plugin) == "off":
                advice.append(f"{plugin} is off; consider enabling it for labor/material/crop sustainability.")
        plots = records(obs.get("farm_plots"))
        sites = records(mapping(obs.get("map")).get("sites"))
        if isinstance(obs.get("farm_plots"), list) and not plots:
            advice.append("No farm plots listed: match subterranean/surface plots to available seeds; autofarm selects crops.")
        if isinstance(obs.get("farm_plots"), list):
            built_plots = [p for p in plots if p.get("built") is True]
            farms = {"listed": len(plots), "built": len(built_plots),
                     "planned": sum(p.get("built") is False for p in plots),
                     "with_seeds_or_crops": sum(number(p.get("seeds_or_crops_in_plot")) and
                                                p["seeds_or_crops_in_plot"] > 0 for p in plots),
                     "fallow_built_ids": [p.get("id") for p in built_plots
                                          if p.get("crop_this_season") == "none"][:12]}
            out["farms"] = farms
            area_known = all(number(p.get("w")) and p["w"] > 0 and number(p.get("h")) and p["h"] > 0
                             for p in built_plots)
            if area_known:
                area = sum(p["w"] * p["h"] for p in built_plots)
                farms["built_area_tiles"] = area
                if number(population) and population > 0:
                    farms["tiles_per_citizen"] = round(area / population, 2)
            season = mapping(obs.get("date")).get("season")
            seeds = mapping(stocks.get("seeds_by_kind"))
            eligible = {v.get("underground") for v in seeds.values() if isinstance(v, dict)
                        and isinstance(v.get("underground"), bool) and number(v.get("n")) and v["n"] > 0
                        and isinstance(v.get("seasons"), list) and season in v["seasons"]}
            compatible = [s.get("id") for s in sites if s.get("kind") in ("F", "G")
                          and s.get("free") is True and not s.get("used_by") and s.get("soil") is True
                          and isinstance(s.get("subterranean"), bool) and s["subterranean"] in eligible]
            farms["seed_compatible_free_sites"] = compatible[:12]
            if area_known and number(population) and population > 0 and area < 2 * population and compatible:
                advice.insert(0, "Food capacity risk: fewer than 2 known built farm tiles per citizen (expansion "
                              "heuristic, not a DF requirement or yield guarantee). With suitable seeds and free "
                              "sites, expand several compatible farms early, ahead of optional decor; allow building/"
                              "planting time and verify harvest plus edible food and brewing inputs before handover.")
            if farms["fallow_built_ids"]:
                advice.append("Built plots show no selected crop: autofarm on is not proof of planting. Check "
                              "seed/season/light compatibility, then advance briefly and recheck; re-enabling an "
                              "already-on plugin is not a documented force-refresh or crop-choice tool.")
        out["sites"]["dug_soil_rooms"] = [s.get("id") for s in sites if s.get("kind") == "R"
                                                   and s.get("soil") is True and s.get("dug") is True
                                                   and not s.get("used_by")][:8]
        if isinstance(obs.get("furniture"), list):
            furniture = records(obs["furniture"])
            built = [f for f in furniture if f.get("built") is True]
            beds = sum(kind(f.get("kind")) == "bed" for f in built)
            truncated = number(obs.get("furniture_total")) and obs["furniture_total"] > len(furniture)
            housing = out["housing"]
            housing.update(built_beds=beds, truncated=bool(truncated))
            if number(population) and not truncated:
                housing["bed_shortfall"] = max(0, population - beds)
            # Union building ids across dining zones: overlapping zones must not multiply seats.
            if isinstance(obs.get("zones"), list):
                dining = {z.get("id") for z in records(obs["zones"]) if kind(z.get("type")) == "dininghall"
                          and z.get("id") is not None}
                dining_items = {f.get("id"): f for f in built if f.get("id") is not None and
                                any(z in dining for z in (f.get("zone_ids") or []) if isinstance(z, (int, str)))}
                tables = sum(kind(f.get("kind")) == "table" for f in dining_items.values())
                chairs = sum(kind(f.get("kind")) in ("chair", "throne") for f in dining_items.values())
                housing["dining_seats_upper_bound"] = min(tables, chairs)  # adjacency is not assumed
        if number(obs.get("hands_off_in_days")) and obs["hands_off_in_days"] <= 7:
            advice.append("Hands-off soon: verify built Still, continuing brew order, plants/barrels, planted farms, "
                          "manager validation and placed beds now; planned work alone is not enough.")
        defense, urgent, readiness = defense_status(obs, population)
        if defense:
            out["defense"] = defense
        out["priorities"] = (urgent + advice + readiness)[:16]
        return out

    def refuse(self, name, args, tick):
        if name == "advance_days":
            return None
        signature = key(name, args)
        for failure in reversed(self.failures):
            if (failure["signature"] == signature and failure["tick"] == tick
                    and failure["state"] == self.state and failure["epoch"] == self.epoch):
                return {"ok": False, "error_code": "unchanged_failure", "error": (
                    "not run: identical action already failed without public-state or successful-action progress; "
                    f"original {failure['error_code']}: {failure['error']}. Change prerequisites/arguments or advance.")}
        return None

    def remember(self, name, args, resp, tick):
        if resp.get("ok"):
            self.epoch += 1  # any successful prerequisite action makes prior failures retryable
            return
        code = resp.get("error_code")
        if name == "advance_days" or code not in RETRY_CODES:
            return
        self.failures.append({"tool": name, "args": args, "tick": tick, "error_code": code,
                              "error": str(resp.get("error") or "")[:240], "signature": key(name, args),
                              "state": self.state, "epoch": self.epoch})
