import json
DAY = 1200
DRINK_PER_DWARF_PER_DAY = 20 / 336
FOOD_PER_DWARF_PER_DAY = 8 / 336
CORE_WORKSHOPS = ("Carpenters", "Still", "Kitchen")
OFFICE_FROM = 20
RECIPES = {
    "brew_drink": ("Still", "brewable plant + empty barrel"),
    "brew_drink_from_fruit": ("Still", "brewable fruit + empty barrel"),
    "cook_meal": ("Kitchen", "2+ cookable ingredients"),
    "make_barrel": ("Carpenters", "1 usable log"), "make_bed": ("Carpenters", "1 usable log"),
    "make_door": ("Carpenters", "1 usable log"), "make_table": ("Carpenters", "1 usable log"),
    "make_chair": ("Carpenters", "1 usable log"), "make_bin": ("Carpenters", "1 usable log"),
    "make_hatch_cover": ("Carpenters", "1 usable log"), "make_charcoal": ("WoodFurnace", "1 usable log"),
}
JOB_RECIPE = {("CustomReaction", "BREW_DRINK_FROM_PLANT"): "brew_drink",
              ("CustomReaction", "BREW_DRINK_FROM_PLANT_GROWTH"): "brew_drink_from_fruit",
              ("PrepareMeal", None): "cook_meal", ("MakeBarrel", None): "make_barrel",
              ("ConstructBed", None): "make_bed", ("ConstructDoor", None): "make_door",
              ("ConstructTable", None): "make_table", ("ConstructThrone", None): "make_chair",
              ("ConstructBin", None): "make_bin", ("ConstructHatchCover", None): "make_hatch_cover",
              ("MakeCharcoal", None): "make_charcoal"}
JOB_WORKSHOP = {"MakeCrafts": "Craftsdwarfs", "ButcherAnimal": "Butchers", "PrepareRawFish": "Fishery",
                "ProcessPlants": "Farmers", "MillPlants": "Quern", "MakeCheese": "Farmers"}
CANCEL_KEYS = [("brew", ("brew_drink", "brew_drink_from_fruit")), ("barrel", ("make_barrel",)),
               ("cookable", ("cook_meal",)), ("prepare", ("cook_meal",)), ("meal", ("cook_meal",)),
               ("bed", ("make_bed",)), ("door", ("make_door",)), ("table", ("make_table",)),
               ("throne", ("make_chair",)), ("chair", ("make_chair",)), ("bin", ("make_bin",)),
               ("hatch", ("make_hatch_cover",)), ("charcoal", ("make_charcoal",))]
LABORS = [("MINE", "nobody digs"), ("CUTWOOD", "nobody fells trees (autochop needs a woodcutter)"),
          ("CARPENTER", "nobody builds wood furniture or barrels"), ("BREWER", "nobody brews"),
          ("COOK", "nobody cooks"), ("PLANT", "nobody farms")]
MOOD_WORKSHOP = {"CARPENTRY": "Carpenters", "MASONRY": "Masons", "BONECARVE": "Craftsdwarfs",
                 "STONECRAFT": "Craftsdwarfs", "WOODCRAFT": "Craftsdwarfs", "COOK": "Kitchen", "BREWING": "Still",
                 "BUTCHER": "Butchers", "FISH": "Fishery", "PROCESSPLANTS": "Farmers"}
def _d(x):
    return x if isinstance(x, dict) else {}
def _l(x):
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []
def _n(x, default=0):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else default
def recipe_of(o):
    r = o.get("recipe")
    if r:
        return r
    return JOB_RECIPE.get((o.get("job"), o.get("reaction")))
def workshop_for(o):
    r = recipe_of(o)
    if r and r in RECIPES:
        ws = RECIPES[r][0]
        cats = o.get("material_category") or []
        if ws == "Carpenters" and isinstance(cats, list) and any("stone" in str(c).lower() for c in cats):
            return "Masons"
        return ws
    return JOB_WORKSHOP.get(o.get("job"))
def parse_cancels(obs):
    out = []
    for t in obs.get("recent_cancellations") or []:
        if isinstance(t, str) and " cancels " in t:
            job, _, reason = t.split(" cancels ", 1)[1].partition(":")
            out.append((job.strip(), reason.strip()))
    return out
def cancellations_for(recipe, cancels):
    if not recipe:
        return []
    out = []
    for job, reason in cancels:
        text = (job + " " + (reason if not job else "")).lower()
        if any(k in text and recipe in rs for k, rs in CANCEL_KEYS) and reason and reason not in out:
            out.append(reason)
    return out[:2]
class Memory:
    FAILED, DONE = 8, 6
    def __init__(self):
        self.failed = []
        self.done = []
        self.stops = []
        self.first_unvalidated = {}
        self.prev = None
        self.labors_missing = None
        self.last_units_tick = None
    @staticmethod
    def short_args(args):
        try:
            s = json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)
        except Exception:
            s = str(args)
        return s if len(s) <= 90 else s[:87] + "..."
    def record(self, day, tool, args, resp):
        a = self.short_args(args)
        if resp.get("ok"):
            self.done = (self.done + [(day, tool, a)])[-self.DONE:]
            r = _d(resp.get("result"))
            if tool == "advance_days" and isinstance(r.get("stopped"), dict):
                st = r["stopped"]
                self.stops = (self.stops + [(day, str(st.get("reason")), str(st.get("detail") or "")[:60])])[-3:]
        else:
            err = str(resp.get("error") or "")[:110]
            self.failed = (self.failed + [(day, tool, a, str(resp.get("error_code") or "failed"), err)])[-self.FAILED:]
def days_of(stock, per_day):
    if per_day <= 0:
        return None
    return stock / per_day
def fmt_days(x):
    if x is None:
        return "?"
    if x > 999:
        return ">999"
    return "%.0f" % x
def digest(obs, env, memory=None, units=None, animals=None, layer=None):
    mem = memory or Memory()
    lines = []
    tick = _n(env.get("tick"), None) if isinstance(env, dict) else None
    day = _n(env.get("day"), None) if isinstance(env, dict) else None
    sections = (_clock, _population, _supply, _manager, _workshops, _orders, _farms, _housing, _threats, _moods,
                _sites, _labors, _memory, _layer)
    ctx = {"obs": obs, "env": _d(env), "mem": mem, "tick": tick, "day": day, "units": units, "animals": animals,
           "layer": _d(layer),
           "next": [], "citizens": len(_l(obs.get("dwarves"))) or _n(_d(obs.get("administrators")).get("citizens"), 0)}
    for fn in sections:
        try:
            out = fn(ctx)
            if out:
                lines.extend(out if isinstance(out, list) else [out])
        except Exception as e:
            lines.append(f"{fn.__name__.strip('_')}: (digest error {type(e).__name__})")
    try:
        if ctx["next"]:
            nxt = list(dict.fromkeys(ctx["next"]))
            lines.append("NEXT (gaps found, in playbook order; skip what the observation shows is already under way"
                         + (", and what the LAYER line shows it is doing" if ctx.get("layer") else "") + "): "
                         + "; ".join(nxt[:6]))
    except Exception:
        pass
    return "STATUS (derived by the harness from the observation and read-only queries; the observation is the ground truth)\n" + "\n".join(lines)
def _clock(c):
    env, obs = c["env"], c["obs"]
    date = _d(obs.get("date"))
    s = f"clock: day {env.get('day')}, {date.get('season', '?')} of year {date.get('year', '?')}, {env.get('days_left')} days left"
    ho = env.get("hands_off_in_days")
    if ho is not None:
        s += f"; HANDS-OFF in {ho} days: everything must be self-running (repeating orders with when, farms, autofarm) by then"
    return s
def _population(c):
    obs = c["obs"]
    dw = _l(obs.get("dwarves"))
    n = c["citizens"]
    idle = [d for d in dw if d.get("job") in ("idle", None, "")]
    stressed = _n(obs.get("stressed_citizens"), None)
    if stressed is None:
        stressed = sum(1 for d in dw if _n(d.get("stress"), 6) <= 1)
    th = _d(obs.get("threats"))
    s = f"population: {n} citizens, {len(idle)} idle, {stressed} stressed (category 0-1)"
    if _n(th.get("dead_citizens_total")):
        s += f", {th['dead_citizens_total']} dead in total"
    if idle and len(idle) <= 6:
        s += "; idle ids " + ",".join(str(d.get("id")) for d in idle)
    if n and stressed and stressed / n > 0.3:
        c["next"].append("wellbeing: many stressed dwarves: check drink, beds, dining")
    return s
def _supply(c):
    obs, mem, n = c["obs"], c["mem"], max(1, c["citizens"])
    st = _d(obs.get("stocks"))
    drink, food, meals = _n(st.get("drink")), _n(st.get("food_edible")), _n(st.get("prepared_meals"))
    d_days = days_of(drink, n * DRINK_PER_DWARF_PER_DAY)
    f_days = days_of(food, n * FOOD_PER_DWARF_PER_DAY)
    trend = ""
    tick = c["tick"]
    if mem.prev and tick is not None and tick > mem.prev[0]:
        dd = (tick - mem.prev[0]) / DAY
        if dd >= 1:
            trend = f"; trend over the last {dd:.0f} d: drink {(drink - mem.prev[1]) / dd:+.1f}/d, food {(food - mem.prev[2]) / dd:+.1f}/d"
    if tick is not None:
        mem.prev = (tick, drink, food)
    s = (f"supply: drink {drink} ({drink / n:.1f} per dwarf, ~{fmt_days(d_days)} d at the usual rate); "
         f"food_edible {food} ({food / n:.1f} per dwarf, ~{fmt_days(f_days)} d), prepared_meals {meals}; "
         f"plants_brewable {_n(st.get('plants_brewable'))}, plants_total {_n(st.get('plants_total'))}, "
         f"seeds {_n(st.get('seeds'))}; barrels_empty {_n(st.get('barrels_empty'))}/{_n(st.get('barrels_total'))}; "
         f"logs_usable {_n(st.get('logs_usable'))} (unusable/wagon {_n(st.get('logs_unusable'))}), "
         f"boulders_usable {_n(st.get('boulders_usable'))}" + trend)
    ff = {k: v for k, v in _d(st.get("furniture_free")).items() if _n(v)}
    if ff:
        s += "; free items: " + ", ".join(f"{k} {v}" for k, v in ff.items())
    c["stocks"] = st
    if drink / n < 3 or (d_days is not None and d_days < 30):
        c["next"].append(f"DRINK LOW ({drink} for {n}): brew (needs Still + plants_brewable + barrels_empty); standing order brew_drink repeat=daily when drink below {8 * n}")
    if food / n < 2 or (f_days is not None and f_days < 30):
        c["next"].append(f"FOOD LOW ({food} for {n}): cook_meal needs Kitchen + 2 cookable; farms for the long run")
    return s
def _manager(c):
    obs = c["obs"]
    adm = _d(obs.get("administrators"))
    n = c["citizens"]
    active = adm.get("manager_active_for_orders")
    mgr = adm.get("MANAGER")
    office = adm.get("manager_office")
    need_office = n >= OFFICE_FROM
    s = f"manager: {mgr if mgr else 'VACANT'}" + (f" (id {adm.get('MANAGER_id')})" if adm.get("MANAGER_id") is not None else "")
    if not active:
        s += "; NOT ACTIVE for orders: nothing gets validated"
        if not mgr or mgr == "VACANT":
            c["next"].append("appoint_manager (no manager: orders never validate)")
    if isinstance(office, dict):
        s += f"; office zone {office.get('zone_id')} chair={'yes' if office.get('chair') else 'NO'}"
        if need_office and not office.get("chair"):
            c["next"].append(f"manager office zone {office.get('zone_id')} has no built chair: place_furniture chair there (make_chair if none free)")
    else:
        s += "; office: none" + (f" (REQUIRED at {n} citizens: make_zone office, place a chair, assign_zone to the manager)" if need_office else " (needed from ~20 citizens)")
        if need_office and active:
            c["next"].append("manager office missing at 20+ citizens: make_zone office on a dug A/R site, place_furniture chair, assign_zone to the MANAGER_id")
    c["manager_active"] = bool(active)
    c["office_ok"] = (not need_office) or (isinstance(office, dict) and bool(office.get("chair")))
    return s
def _workshops(c):
    obs = c["obs"]
    ws = _l(obs.get("workshops"))
    built = {}
    planned = {}
    for w in ws:
        (built if w.get("built") else planned).setdefault(str(w.get("type")), []).append(w)
    c["built"], c["planned"] = built, planned
    parts = []
    for t, lst in sorted(built.items()):
        busy = sum(1 for w in lst if w.get("jobs"))
        parts.append(f"{t} x{len(lst)}" + (f" ({busy} busy)" if busy else " (idle)"))
    s = "workshops built: " + (", ".join(parts) if parts else "none")
    if planned:
        s += "; placed, not yet built: " + ", ".join(f"{t} x{len(l)}" for t, l in sorted(planned.items()))
    st = c.get("stocks") or _d(obs.get("stocks"))
    missing = [t for t in CORE_WORKSHOPS if t not in built and t not in planned]
    if missing:
        s += "; MISSING core: " + ", ".join(missing)
        plugins = _d(obs.get("plugins"))
        if _n(st.get("logs_usable")) == 0 and _n(st.get("boulders_usable")) == 0:
            c["next"].append("no usable log or boulder, so no workshop can be built: enable_automation autochop"
                             + ("" if plugins.get("autochop") != "on" else " is on; advance a few days for logs") )
        else:
            c["next"].append("build_workshop " + ", then ".join(missing) + " on free W sites")
    if planned and _n(st.get("logs_usable")) == 0 and _n(st.get("boulders_usable")) == 0:
        s += "; placed workshops wait for a usable log/boulder"
    return s
def _orders(c):
    obs, mem = c["obs"], c["mem"]
    orders = _l(obs.get("orders"))
    st = c.get("stocks") or _d(obs.get("stocks"))
    built = c.get("built") or {}
    planned = c.get("planned") or {}
    plugins = _d(obs.get("plugins"))
    cancels = parse_cancels(obs)
    tick = c["tick"]
    have = set()
    out = []
    for o in orders[:14]:
        rec = recipe_of(o)
        if rec:
            have.add(rec)
        ws = workshop_for(o)
        name = rec or (str(o.get("job")) + (f"/{o['reaction']}" if o.get("reaction") else ""))
        if o.get("id") in (c.get("layer") or {}).get("owned", ()):
            name += "[layer]"
        why = []
        left, jip = _n(o.get("left")), _n(o.get("jobs_in_progress"))
        if not o.get("validated"):
            oid = o.get("id")
            if tick is not None and oid is not None:
                first = mem.first_unvalidated.setdefault(oid, _n(o.get("created_tick"), tick) or tick)
                waited = max(0.0, (tick - first) / DAY)
            else:
                waited = 0.0
            if not c.get("manager_active", True):
                why.append("no manager")
            elif not c.get("office_ok", True):
                why.append(f"unvalidated {waited:.0f} d: manager needs an office with a chair")
            else:
                why.append(f"awaiting validation {waited:.0f} d" + (" (slow: check the office rule)" if waited > 4 else ""))
        if ws and ws not in built:
            why.append(f"no built {ws}" + (" (placed, not built)" if ws in planned else ""))
        if ws in ("Carpenters", "WoodFurnace") and _n(st.get("logs_usable")) == 0:
            why.append("no usable logs" + ("" if plugins.get("autochop") == "on" else " (autochop off)"))
        if rec in ("brew_drink", "brew_drink_from_fruit"):
            if _n(st.get("barrels_empty")) == 0:
                why.append("no empty barrel")
            if rec == "brew_drink" and _n(st.get("plants_brewable")) == 0:
                why.append("no brewable plant")
        if rec == "cook_meal" and _n(st.get("food_edible")) + _n(st.get("plants_total")) < 2:
            why.append("fewer than 2 cookable items")
        for r in cancellations_for(rec, cancels):
            why.append("cancelled: " + r[:70])
        if o.get("repeat") and o.get("validated") and not o.get("active") and jip == 0 and left == 0:
            why = ["repeating, between runs (re-queued when its conditions hold)"]
        when = ""
        if _l(o.get("when")):
            when = " when " + ",".join(f"{w.get('stock') or w.get('item_type') or 'ANY'} {str(w.get('test', ''))[:2]}{w.get('value')}"
                                      for w in _l(o.get("when")))
        line = f"  #{o.get('id')} {name} {left}/{_n(o.get('total'))} left, jobs {jip}" + (f", {o['repeat']}" if o.get("repeat") else "") + when
        if why and jip == 0 and (left > 0 or not o.get("validated")):
            line += "  stuck: " + "; ".join(why)
        out.append(line)
    c["have_orders"] = have
    head = f"orders ({len(orders)})" + (" (first 14 shown)" if len(orders) > 14 else "") + ":" if orders else "orders: none"
    n = max(1, c["citizens"])
    if "Still" in built or "Still" in planned:
        if not (have & {"brew_drink", "brew_drink_from_fruit"}) and _n(st.get("plants_brewable")) > 0:
            c["next"].append(f"no brew order: add_order brew_drink amount=5 repeat=daily when=[{{stock drink below {8 * n}}}]")
        if _n(st.get("barrels_empty")) < 2 and "make_barrel" not in have and "Carpenters" in built:
            c["next"].append("barrels_empty low: add_order make_barrel amount=3 repeat=daily when=[{stock barrels_empty below 3}]")
    if ("Kitchen" in built or "Kitchen" in planned) and "cook_meal" not in have and _n(st.get("prepared_meals")) < 2 * n:
        c["next"].append(f"no cooking order: add_order cook_meal amount=3 repeat=daily when=[{{stock prepared_meals below {2 * n}}}]")
    return [head] + out if out else head
def _farms(c):
    obs = c["obs"]
    plots = _l(obs.get("farm_plots"))
    plugins = _d(obs.get("plugins"))
    on = [k for k, v in plugins.items() if v == "on"]
    off = [k for k, v in plugins.items() if v != "on"]
    s = f"farms: {len(plots)} plots" + (f" ({sum(1 for p in plots if p.get('built'))} built, {sum(1 for p in plots if p.get('subterranean'))} underground)" if plots else "")
    if plots:
        crops = [str(p.get("crop_this_season") or "none") for p in plots[:4]]
        s += "; crops now: " + ", ".join(crops)
    s += f"; plugins on: {', '.join(on) or 'none'}; off: {', '.join(off) or 'none'}"
    pend = _n(obs.get("dig_designations_pending"))
    if pend:
        s += f"; digging pending: {pend} tiles"
    for p in ("autochop", "seedwatch"):
        if plugins.get(p) != "on" and not any(p in x for x in c["next"]):
            c["next"].append(f"enable_automation {p}")
    if plots and plugins.get("autofarm") != "on":
        c["next"].append("enable_automation autofarm (plots have no crop choice without it)")
    if not plots:
        sites = _l(_d(obs.get("map")).get("sites"))
        dug = [x for x in sites if x.get("kind") == "R" and x.get("dug") and x.get("soil") and not x.get("used_by")]
        desig = [x for x in sites if x.get("kind") == "R" and x.get("designated") and not x.get("dug")]
        f_sites = [x for x in sites if x.get("kind") == "F"]
        if dug or f_sites:
            c["next"].append("no farm yet: build_farm on " + ", ".join(x.get("id") for x in (dug + f_sites)[:3]))
        elif desig or pend:
            pass
        else:
            s_sites = [x.get("id") for x in sites if x.get("kind") == "S"]
            r_sites = [x.get("id") for x in sites if x.get("kind") == "R" and not x.get("designated")]
            if r_sites:
                c["next"].append("no farm yet: dig_room " + r_sites[0] + " (soil R site preferred), then build_farm once dug")
            elif s_sites:
                c["next"].append("no farm yet: dig_stairs " + s_sites[0] + " down 1 level, then dig_room an R site beside it")
    return s
def _housing(c):
    obs = c["obs"]
    n = max(1, c["citizens"])
    furn = _l(obs.get("furniture"))
    beds_placed = sum(1 for f in furn if str(f.get("kind")).lower() == "bed" and f.get("built"))
    beds_planned = sum(1 for f in furn if str(f.get("kind")).lower() == "bed" and not f.get("built"))
    zones = _l(obs.get("zones"))
    seats = 0
    kinds = {}
    for z in zones:
        t = str(z.get("type") or "").lower()
        kinds[t] = kinds.get(t, 0) + 1
        if "din" in t:
            fz = _d(z.get("furniture"))
            ch = sum(_n(v) for k, v in fz.items() if "chair" in k.lower() or "throne" in k.lower())
            tb = sum(_n(v) for k, v in fz.items() if "table" in k.lower())
            seats += min(ch, tb) if tb else 0
    st = c.get("stocks") or _d(obs.get("stocks"))
    ff = _d(st.get("furniture_free"))
    s = (f"housing: beds placed {beds_placed}/{n} citizens" + (f" (+{beds_planned} placed, not built)" if beds_planned else "")
         + f", bed items in stock {_n(st.get('beds'))} (free {_n(ff.get('bed'))}); dining seats (chair+table in a dining zone) "
         f"{seats}, need {(n + 1) // 2}; zones: " + (", ".join(f"{k} x{v}" for k, v in sorted(kinds.items())) if kinds else "none"))
    if obs.get("furniture_total") is not None and len(furn) < _n(obs.get("furniture_total")):
        s += f" (furniture list cut at {len(furn)} of {obs['furniture_total']})"
    sites = _l(_d(obs.get("map")).get("sites"))
    rooms = [x.get("id") for x in sites if x.get("kind") == "A" or (x.get("kind") == "R" and x.get("dug") and not x.get("used_by"))]
    if beds_placed < n:
        if _n(ff.get("bed")) > 0 and rooms:
            c["next"].append(f"{_n(ff.get('bed'))} free beds: place_furniture bed count={min(30, _n(ff.get('bed')))} on {rooms[0]} (make_zone dormitory there)")
        elif _n(st.get("beds")) < n and "make_bed" not in (c.get("have_orders") or set()) and "Carpenters" in (c.get("built") or {}):
            c["next"].append(f"beds {_n(st.get('beds'))} < {n} citizens: add_order make_bed amount={min(30, n - _n(st.get('beds')))}")
        elif not rooms:
            c["next"].append("no dug room for beds: dig_stairs + dig_room (a 5x5 or larger room via w,h)")
    if seats < (n + 1) // 2 and rooms and (_n(ff.get("chair")) and _n(ff.get("table"))):
        c["next"].append(f"dining: make_zone dining_hall on {rooms[-1]} and place_furniture table + chair there")
    return s
def _threats(c):
    obs = c["obs"]
    th = _d(obs.get("threats"))
    mil = _d(obs.get("military"))
    bur = _d(obs.get("burrows"))
    hostiles = _n(th.get("visible_hostiles"))
    squads = _l(mil.get("squads"))
    sq = squads[0] if squads else None
    s = f"threats: {hostiles} visible hostiles"
    if hostiles:
        s += f", nearest {th.get('nearest_hostile_dist_to_wagon')} tiles from the wagon"
        by = _d(th.get("by_race"))
        if by:
            s += "; " + ", ".join(f"{_n(_d(v).get('n'))} {k}" + (" (invaders)" if _d(v).get("invader") else "") for k, v in list(by.items())[:4])
    if sq:
        s += f"; squad '{sq.get('name')}' {len(_l(sq.get('members')))} members, {_n(sq.get('armed'))} armed, uniform {sq.get('uniform')}, orders {len(_l(sq.get('orders')))}"
    else:
        s += "; no squad"
    shelter = any(b.get("civ_alert_burrow") for b in _l(bur.get("list")))
    s += f"; shelter burrow {'yes' if shelter else 'no'}; civilian_alert {'ON' if bur.get('civilian_alert') else 'off'}; weapons_free {_n(mil.get('weapons_free'))}"
    if hostiles:
        c["next"].insert(0, "HOSTILES VISIBLE: the squad and the civilian alert are handled for you"
                         + ("" if shelter else "; create_burrow on an A site for the Shelter"))
    return s
def _moods(c):
    obs = c["obs"]
    moods = _l(obs.get("moods"))
    if not moods:
        return None
    out = []
    for m in moods[:3]:
        skill = str(m.get("skill") or "")
        ws = MOOD_WORKSHOP.get(skill.upper().replace("_", ""), None)
        line = f"  dwarf {m.get('unit_id')} {m.get('mood')} ({skill}), job {m.get('job')}, claimed {m.get('claimed_workshop') or 'NO WORKSHOP'}"
        if m.get("waiting"):
            needs = _l(m.get("items_needed"))
            line += "; WAITING for: " + ", ".join(f"{x.get('demand') or x.get('item')} ({_n(x.get('collected'))} collected)" for x in needs[:4])
        out.append(line)
        if not m.get("claimed_workshop") and str(m.get("mood")) in ("Fey", "Secretive", "Possessed", "Macabre", "Fell"):
            if ws and ws not in (c.get("built") or {}):
                c["next"].insert(0, f"MOOD: build_workshop {ws} (the {skill} mood needs it) before the dwarf goes insane")
    return ["moods:"] + out
def _sites(c):
    obs = c["obs"]
    sites = _l(_d(obs.get("map")).get("sites"))
    by = {}
    for x in sites:
        k = x.get("kind")
        if k == "R":
            tag = x.get("id")
            if x.get("dug"):
                tag += "(dug" + (",soil" if x.get("soil") else "") + (",used" if x.get("used_by") else "") + ")"
            elif x.get("designated"):
                tag += "(digging)"
            else:
                tag += "(soil)" if x.get("soil") else ""
            by.setdefault(k, []).append(tag)
        elif k == "A":
            by.setdefault(k, []).append(f"{x.get('id')}({x.get('w')}x{x.get('h')} z{x.get('z')})")
        else:
            by.setdefault(k, []).append(str(x.get("id")))
    desc = {"W": "workshop", "S": "stair start", "R": "room", "F": "farm (dug soil)", "G": "surface farm",
            "A": "dug area", "E": "stair for hatch", "D": "doorway"}
    return "sites: " + "; ".join(f"{k} {desc.get(k, '')}: " + ", ".join(v[:6]) for k, v in sorted(by.items())) if by else "sites: none listed"
def _labors(c):
    units = c.get("units")
    if units is None:
        return c["mem"].labors_missing
    cits = _l(_d(units).get("citizens")) or _l(_d(units).get("result")) or _l(units if isinstance(units, list) else None)
    cits = [u for u in cits if isinstance(u.get("labors"), list)]
    if not cits:
        return None
    all_labors = {str(l).upper() for u in cits for l in u.get("labors") or []}
    missing = [(k, why) for k, why in LABORS if not any(k in l for l in all_labors)]
    if not missing:
        line = "labors: every core labor (mining, woodcutting, carpentry, brewing, cooking, farming) is held by someone"
    else:
        line = "labors MISSING: " + "; ".join(f"{k} ({why})" for k, why in missing)
    c["mem"].labors_missing = line
    return line
def _memory(c):
    mem = c["mem"]
    out = []
    if mem.failed:
        out.append("your recent FAILED actions (don't repeat unchanged): " + " | ".join(
            f"d{d} {t} {a} -> {code}: {err[:60]}" for d, t, a, code, err in mem.failed[-6:]))
    if mem.done:
        out.append("your recent actions: " + " | ".join(f"d{d} {t} {a}" for d, t, a in mem.done[-5:]))
    if mem.stops:
        out.append("recent advance stops: " + " | ".join(f"d{d} {r} {det}" for d, r, det in mem.stops))
    return out or None
def _layer(c):
    lay = c.get("layer") or {}
    rep = _l(lay.get("report"))
    if not rep:
        return None
    today = [r for r in rep if _d(r).get("day") == c["day"]] or rep[-6:]
    parts = []
    for r in today[-10:]:
        r = _d(r)
        a = Memory.short_args(r.get("args"))
        parts.append(f"d{r.get('day')} {r.get('tool')} {a} -> " + ("ok" if r.get("ok") else
                     f"FAILED {r.get('error_code')}: {str(r.get('error') or '')[:50]}"))
    failed = sum(1 for r in today if not _d(r).get("ok"))
    return ["LAYER (deterministic, runs once a day before you: manager/office, plugins, workshops, rooms, farms, standing "
            "orders, beds/seats, zones, shelter, mood workshop; don't redo or cancel its work): " + " | ".join(parts)
            + (f" -- {failed} refused: those are yours to solve" if failed else "")]
def compact_observation(obs):
    o = dict(obs)
    if isinstance(o.get("furniture"), list):
        o["furniture_count"] = len(o["furniture"])
        del o["furniture"]
    if isinstance(o.get("workshops"), list):
        o["workshops"] = [{k: v for k, v in w.items() if k != "job_details"} if isinstance(w, dict) else w
                          for w in o["workshops"]]
    if isinstance(o.get("zones"), list) and len(o["zones"]) > 40:
        o["zones"] = o["zones"][:40]
    o.pop("wealth", None)
    return o
