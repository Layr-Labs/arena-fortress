"""Overseer class body, part 4 of 4. Not a module of its own: harness.py executes this file inside `class Overseer`, with harness.py's globals, after part 3."""
def butcher(self, for_food=True):
    if not self.butchers_ready():
        self.build("Butchers", key=self.butcher_key())
    if for_food:
        why = self.slaughter_wait()
        if why is not None:
            if self.may("slaughter_wait_log", 1, 99):
                self.last["slaughter_wait_log"] = self.now
                log("slaughter_wait", day=self.day, why=why, perishable=self.perishable(),
                    alert_seen=self.alert_seen_day)
            return
    if not self.may("slaughter", 5, 3):
        return
    try:
        q = query_result(self.game.query("units", kind="animals"))
    except Exception as e:
        log("butcher_query_error", error=repr(e)[:160])
        return
    keep = for_food and self.f_reserve_hold()
    for a in sorted(map(d, lst(d(q).get("units") or d(q).get("animals"))), key=lambda a: not grazer_race(a.get("race"))):
        if keep and not grazer_race(a.get("race")):
            if not self.f_reserve_logged:
                self.f_reserve_logged = True
                log("f_reserve_keep", day=self.day, unit=a.get("id"), race=a.get("race"),
                    food=self.st.get("food_edible"), cit=self.cit)
            continue
        if a.get("tame") and a.get("pet_owner_id") in (None, -1) and not a.get("marked_for_slaughter"):
            self.act("slaughter", "slaughter", {"unit_id": a.get("id")}, retry=5, limit=3)
            return
def defend(self):
    th, mil = d(self.o.get("threats")), d(self.o.get("military"))
    bur = d(self.o.get("burrows"))
    alert = bur.get("civilian_alert")
    if alert and self.alert_since is None:
        self.alert_since = self.now
    elif alert is False:
        self.alert_since = None
        if self.wild_spans and self.wild_spans[-1][1] is None and self.wild_alert_since is not None \
                and self.now - self.wild_alert_since > DAY:
            self.wild_alert_closed()
            self.wild_alert_since = None
    squads = lst(mil.get("squads"))
    squad = d(squads[0]) if squads else None
    foes = [d(h) for h in lst(th.get("hostiles")) if d(h).get("invader")]
    if squad:
        self.arm_record(squad)
    if not squad and foes and self.cit >= SQUAD_MIN_CIT:
        self.create_squad("squad", self.fight_squad_size(th))
    elif not squad and self.cit >= SQUAD_MIN_CIT:
        self.create_squad("squad", 4)
    if squad and squad.get("uniform") == "none" and self.equip_day is None:
        tpl = self.uniform_choice()
        r = self.act("equip", "equip_squad", {"uniform": tpl}, retry=1, limit=3)
        if r is not None:
            if not r.get("ok") and tpl == "metal":
                self.metal_refused = True
                self.tries["equip"] = max(0, self.tries.get("equip", 1) - 1)
                self.last.pop("equip", None)
            if r.get("ok"):
                self.equip_day = self.day
            log("equip_once", day=self.day, uniform=tpl, ok=r.get("ok"), invaders=bool(foes))
    if squad and squad.get("uniform") not in (None, "none"):
        self.spear_supply(squad)
    self.gate_survey()
    self.shelter_grow()
    invaders = [h for h in lst(th.get("hostiles")) if d(h).get("invader")]
    hostile = th.get("visible_hostiles") or 0
    window = self.invader_window is not None and self.now < self.invader_window
    if self.invader_window is not None and not window:
        log("invader_window_end", day=self.day, invaders=len(invaders), hostile=hostile,
            guard=list(self.invader_guard) if self.invader_guard else None)
        self.invader_window = None
    orders = lst((squad or {}).get("orders"))
    odds = self.fight_odds(squad, th) if hostile and squad else None
    if hostile and squad and odds["go"] and not window \
            and (not orders or self.mark_station is not None or self.invader_guard is not None
                 or self.muster is not None):
        args = {"order": "attack"}
        if odds["targets"] is not None:
            args["target_ids"] = odds["targets"]
        r = self.act("attack", "squad_order", args, retry=1, limit=99)
        if r and r.get("ok"):
            self.mark_station = None
            self.gate_post = False
            self.invader_guard = None
            self.muster = None
            log("fight_go", day=self.day, ours=odds["ours"], theirs=odds["theirs"], endgame=odds["endgame"],
                armed=odds["armed"], members=odds["members"], foes=odds["foes"])
    elif hostile and squad and not odds["go"] and not window:
        attacking = any(d(o).get("order") == "attack" for o in orders)
        armable = len(self.armable_ids(squad))
        odds_arm = self.fight_odds(dict(squad, armed=max(squad.get("armed") or 0, armable)), th)
        if invaders and not attacking and self.invader_guard is None \
                and squad.get("uniform") not in (None, "none") and odds_arm["why"] != "big_only" \
                and (odds_arm["go"] or not self.duty_seen or self.muster is not None):
            self.guard_muster(squad, force="invaders")
        elif (attacking and odds["retreat"]) or self.invader_guard is not None:
            r = self.act("fight_retreat", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
            if r and r.get("ok"):
                self.invader_guard = None
                log("fight_retreat", day=self.day, ours=odds["ours"], theirs=odds["theirs"], why=odds["why"])
        elif self.fight_log_day != self.day:
            self.fight_log_day = self.day
            log("fight_hold", day=self.day, ours=odds["ours"], theirs=odds["theirs"], why=odds["why"],
                armed=odds["armed"], members=odds["members"], foes=odds["foes"], endgame=odds["endgame"],
                attacking=attacking)
    if not hostile and orders and self.mark_station is None and self.muster is None:
        r = self.act("stand_down", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
        if r and r.get("ok"):
            self.invader_guard = None
    if not hostile and squad:
        self.guard_muster(squad)
    if window and hostile:
        self.invader_guard_station(squad, invaders)
    near = (th.get("nearest_hostile_dist_to_wagon") or 10 ** 6) <= 45
    if invaders and near and not alert and not self.alert_barred() and not window \
            and self.shelter_listed(bur):
        r = self.act("alert_on", "civilian_alert", {"on": True}, retry=1, limit=10 ** 6)
        if r and r.get("ok"):
            self.alert_since = self.now
    too_long = self.alert_since is not None and self.now - self.alert_since > 10 * DAY
    thirst = self.thirst_due()
    if thirst and alert:
        too_long = True
    elif thirst and self.access_from is not None:
        until = self.access_from + ACCESS_WINDOW_DAYS * DAY
        if self.wild_rest_until is None or self.wild_rest_until < until:
            self.wild_rest_until = until
            log("access_hold", day=self.day, until_day=round(until / DAY, 1),
                since_day=round(self.access_tick / DAY, 1))
    elif thirst and self.access_log_day != self.day:
        self.access_log_day = self.day
        inside = next((d(b).get("citizens_inside") for b in lst(bur.get("list"))
                       if d(b).get("civ_alert_burrow")), None)
        log("access_unseen", day=self.day, since_day=round(self.access_tick / DAY, 1), inside=inside,
            citizens=self.cit, drink=self.st.get("drink"), wanting=self.thirst_signs(),
            locked=sorted(str(d(x).get("id")) for x in lst(d(self.o.get("doors")).get("list"))
                          if d(x).get("locked")))
        self.trap_seen += 1
        self.shelter_trap()
    if not thirst:
        self.trap_pokes, self.trap_last, self.trap_seen = 0, None, 0
    big = self.big_units() if alert else []
    if big and self.alert_since is not None and self.now - self.alert_since > BIG_FREE_DAYS * DAY \
            and not self.wild_approaching(big):
        log("big_hold_aged", day=self.day, animals=sorted({u["_mark"] for u in big}))
        big = []
    if alert and big and not too_long and not invaders:
        for u in big:
            self.wild_watch[u["_mark"]] = self.now
        if self.big_log_day != self.day:
            self.big_log_day = self.day
            log("big_hold", day=self.day, animals=sorted({u["_mark"] for u in big}), near=len(big))
    lift = alert and ((not invaders and not big and not self.wild_alert_hold()) or too_long)
    if lift and not too_long and self.home_holding():
        lift = False
    if lift and not invaders and self.alert_since is not None \
            and self.now - self.alert_since <= (10 + CAP_DEFER_DAYS) * DAY \
            and not (thirst and self.now - self.access_tick > (ACCESS_CAP_DAYS + CAP_DEFER_DAYS) * DAY):
        pressing = self.mark_pressing()
        if too_long and not pressing:
            pressing = self.fight_pressing()
        if pressing:
            if self.may("cap_defer_log", 1, 10 ** 6):
                self.last["cap_defer_log"] = self.now
                log("cap_defer", day=self.day, animals=pressing, cap=too_long)
            lift = False
    if lift and not invaders and not thirst and self.gate_waiting:
        close = self.shaft_wait_close()
        if close:
            if self.may("shaft_wait_defer_log", 1, 10 ** 6):
                self.last["shaft_wait_defer_log"] = self.now
                log("shaft_wait_defer", day=self.day, animals=sorted({u["_mark"] for u in close}), cap=too_long)
            lift = False
    if lift and invaders:
        if thirst:
            budget = self.now - self.access_tick <= (ACCESS_CAP_DAYS + CAP_DEFER_DAYS) * DAY
        else:
            budget = self.alert_since is not None and self.now - self.alert_since <= (10 + CAP_DEFER_DAYS) * DAY
        at_door = self.invaders_at_entrance(invaders) if budget else []
        if at_door:
            if self.invader_defer_day != self.day:
                self.invader_defer_day = self.day
                log("invader_defer", day=self.day, invaders=at_door,
                    since_day=round(self.access_tick / DAY, 1) if self.access_tick is not None else None)
            lift = False
    if lift:
        r = self.act("alert_off", "civilian_alert", {"on": False}, retry=1, limit=99)
        if r and r.get("ok"):
            if isinstance(self.o.get("burrows"), dict):
                self.o["burrows"]["civilian_alert"] = False
            if self.wild_alert_since is not None or big:
                self.wild_rest_until = self.now + WILD_REST_DAYS * DAY
                self.wild_alert_closed()
                log("wild_rest", day=self.day, cap=too_long, until_day=self.day + WILD_REST_DAYS
                    if isinstance(self.day, (int, float)) else None)
            if thirst:
                until = self.now + ACCESS_WINDOW_DAYS * DAY
                if self.wild_rest_until is None or self.wild_rest_until < until:
                    self.wild_rest_until = until
                log("access_lift", day=self.day, since_day=round(self.access_tick / DAY, 1),
                    wanting=self.thirst_signs(), drink=self.st.get("drink"))
            if invaders:
                self.invader_window = self.now + ACCESS_WINDOW_DAYS * DAY
                if self.wild_rest_until is None or self.wild_rest_until < self.invader_window:
                    self.wild_rest_until = self.invader_window
                self.invader_guard = None
                log("invader_window", day=self.day, until_day=round(self.invader_window / DAY, 1),
                    invaders=len(invaders), thirst=bool(thirst),
                    squad=len(lst(squad.get("members"))) if squad else 0,
                    armed=(squad.get("armed") or 0) if squad else 0)
                if hostile:
                    self.invader_guard_station(squad, invaders)
            self.alert_since = None
            self.wild_alert_since = None
def create_squad(self, key, n):
    if key in self.done or not self.may(key, 5, 3):
        return None
    ids = self.squad_pick(n)
    args = {"dwarf_ids": ids} if ids else {"size": n}
    return self.act(key, "create_squad", args, retry=5, limit=3)
def squad_pick(self, n):
    mood_ids = {d(m).get("unit_id") for m in lst(self.o.get("moods"))}
    units = None
    try:
        res = query_result(self.game.query("units", kind="citizens", limit=300))
        if res is not None:
            units = [d(u) for u in lst(res.get("units"))]
    except Exception as e:
        log("squad_pick_query_error", error=repr(e)[:160])
    src = "units" if units else "observe"
    if not units:
        units = [d(p) for p in self.people]
    tiers = {1: [], 2: [], 3: [], 4: []}
    holders = {}
    for u in units:
        for lab in {str(x).upper() for x in lst(u.get("labors"))} & set(SQUAD_SOLE_LABORS):
            holders.setdefault(lab, []).append(u.get("id"))
    sole = {ids[0] for ids in holders.values() if len(ids) == 1}
    for u in units:
        if u.get("id") is None or u.get("adult") is False or u.get("squad_id") is not None \
                or lst(u.get("positions")) or u.get("id") in mood_ids or u.get("mood"):
            continue
        if u.get("id") in self.stranded:
            continue
        prof = str(u.get("profession") or "").lower()
        labors = {str(x).upper() for x in lst(u.get("labors"))}
        skills = d(u.get("skills"))
        combat = sum(v for k, v in skills.items() if k in SQUAD_COMBAT_SKILLS and isinstance(v, (int, float)))
        if any(t in prof for t in SQUAD_TOOL) or labors & set(SQUAD_TOOL_LABORS):
            tier = 4
        elif any(t in prof for t in SQUAD_MILITARY):
            tier = 1
        elif any(t in prof for t in SQUAD_ESSENTIAL) or u["id"] in sole:
            tier = 3
        else:
            tier = 2
        tiers[tier].append((-combat, u["id"]))
    out = []
    for t in (1, 2, 3):
        out += [i for _, i in sorted(tiers[t])]
    out = out[:n]
    drafted = []
    if len(out) < MARK_SQUAD_MIN:
        drafted = [i for _, i in sorted(tiers[4])][:max(0, min(n, MARK_SQUAD_MIN) - len(out))]
        out += drafted
    log("squad_pick", day=self.day, n=n, ids=out, source=src, tool_workers=drafted,
        tiers={k: len(v) for k, v in tiers.items()})
    return out[:10]
def arm_record(self, squad):
    if squad.get("uniform") in (None, "none"):
        return
    on = bool(lst(squad.get("orders")))
    for m in map(d, lst(squad.get("members"))):
        w = str(m.get("weapon") or "").lower()
        if m.get("weapon_assigned") or (on and w and "pick" not in w):
            self.armed_seen[m.get("id")] = self.day
    if on:
        if self.duty_from is None:
            self.duty_from = self.now
        elif self.now - self.duty_from >= DAY:
            self.duty_seen = True
    else:
        self.duty_from = None
def armable_ids(self, squad):
    ids = {d(m).get("id") for m in lst(squad.get("members"))}
    return sorted(i for i in self.armed_seen if i in ids)
def guard_muster(self, squad, force=None):
    if self.mark_station is not None or self.invader_guard is not None:
        self.muster = None
        return
    orders = lst(squad.get("orders"))
    need = force or self.guard_need()
    threat = need in ("wild_alert", "weak_mark", "invaders")
    if need in ("wild_alert", "weak_mark") and not self.open_entrances() and not self.surface_threat() \
            and not SQUAD_PREARM:
        threat = False
    armed = squad.get("armed") or 0
    present = bool(self.marked_units(MARK_RANGE, MARK_RANGE_Z))
    wild = threat and need in ("wild_alert", "weak_mark") and not self.muster_big()
    lingering = self.muster_lingering(wild and not present) \
        or (wild and self.shaft_rest)
    if SQUAD_PREARM and threat and need in ("wild_alert", "weak_mark"):
        if self.prearm_units():
            self.prearm_seen = self.now
        seen = max([t for t in (self.prearm_seen, self.wild_alert_since) if t is not None], default=None)
        lingering = seen is None or self.now - seen > PREARM_HOLD_DAYS * DAY
    if self.muster is not None:
        idle = self.duty_seen and not self.armable_ids(squad) and armed == 0
        close = self.muster_crossing(squad) \
            if threat and need in ("wild_alert", "weak_mark") and armed < MARK_RESCUE_ARMED else []
        if close:
            r = self.act("muster_stand_down", "squad_order", {"order": "stand_down"}, retry=0.25, limit=10 ** 6)
            if r and r.get("ok"):
                log("guard_muster_end", day=self.day, armed=armed, at=list(self.muster), why="clear_wait",
                    animals=sorted({u["_mark"] for u in close}), tiles=min(u["_tiles"] for u in close))
                self.muster = None
            return
        if threat and not idle and not lingering:
            return
        r = self.act("muster_stand_down", "squad_order", {"order": "stand_down"}, retry=0.25, limit=10 ** 6)
        if r and r.get("ok"):
            log("guard_muster_end", day=self.day, armed=armed, at=list(self.muster),
                why="no_weapons" if idle else "lingering" if threat else "need_gone")
            self.muster = None
        return
    if orders or not threat or squad.get("uniform") in (None, "none") \
            or (need != "invaders" and armed >= MARK_RESCUE_ARMED):
        return
    if lingering:
        if self.may("muster_linger_log", 1, 10 ** 6):
            self.last["muster_linger_log"] = self.now
            log("muster_linger", day=self.day, need=need,
                since=None if self.muster_since is None else round((self.now - self.muster_since) / DAY, 1),
                contact=None if self.muster_contact is None else round((self.now - self.muster_contact) / DAY, 1))
        return
    if need in ("wild_alert", "weak_mark"):
        close = self.muster_crossing(squad)
        if close:
            if self.may("muster_wait_log", 1, 10 ** 6):
                self.last["muster_wait_log"] = self.now
                log("muster_wait", day=self.day, need=need, animals=sorted({u["_mark"] for u in close}),
                    tiles=min(u["_tiles"] for u in close))
            return
    armable = self.armable_ids(squad)
    if len(armable) <= armed and (self.duty_seen or need != "invaders"):
        return
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    surface = self.surface if num(self.surface) else d(self.map).get("surface_z")
    if not num(surface):
        return
    ids = {d(m).get("id") for m in lst(squad.get("members"))}
    spots = [c for c in self.citizen_spots() if c["z"] < surface and c.get("id") not in ids]
    if not spots:
        return
    ents = self.invader_entrances()
    far = lambda c: min((max(abs(c["x"] - x), abs(c["y"] - y)) + 3 * abs(c["z"] - z) for x, y, z in ents),
                        default=0)
    c = max(spots, key=lambda c: (far(c), -c["z"]))
    r = self.act("guard_muster", "squad_order", {"order": "station", "x": c["x"], "y": c["y"], "z": c["z"]},
                 retry=1, limit=99)
    if r and r.get("ok"):
        self.muster = (c["x"], c["y"], c["z"])
        log("guard_muster", day=self.day, need=need, armed=armed, x=c["x"], y=c["y"], z=c["z"],
            armable=len(armable), duty_seen=self.duty_seen)
def wild_contact(self, units, gates, tiles):
    names = sorted({u["_mark"] for u in units} | set(self.wild_watched()))
    if units and self.wild_approaching(units):
        return True
    if names and self.wild_evidenced(names):
        return True
    return any(max(abs(u["x"] - gx), abs(u["y"] - gy)) <= tiles and abs(u["z"] - gz) <= WILD_NEAR_Z
               for u in units for gx, gy, gz in gates)
def mark_clear_wait(self, squad, armed, standing=False, gate=False):
    if armed >= MARK_RESCUE_ARMED:
        self.mark_wait_since = None
        return False
    close = self.muster_crossing(squad)
    if not close:
        if gate:
            self.mark_wait_since = None
        return False
    animals, tiles = sorted({u["_mark"] for u in close}), min(u["_tiles"] for u in close)
    if gate:
        if self.mark_wait_since is None:
            self.mark_wait_since = self.now
        waited = self.now - self.mark_wait_since
        if MARK_WAIT_MAX_DAYS is not None and waited >= MARK_WAIT_MAX_DAYS * DAY:
            if self.may("mark_wait_over_log", 1, 10 ** 6):
                self.last["mark_wait_over_log"] = self.now
                log("mark_wait_over", day=self.day, armed=armed, animals=animals, tiles=tiles,
                    waited=round(waited / DAY, 1), gear=self.gear_where, standing=standing)
            self.gate_waiting = False
            return False
        self.gate_waiting = True
    if standing:
        r = self.act("mark_clear_stand_down", "squad_order", {"order": "stand_down"}, retry=0.25, limit=10 ** 6)
        if r and r.get("ok"):
            log("mark_stand_down", day=self.day, why="clear_wait", station=self.mark_kind, armed=armed,
                animals=animals, tiles=tiles, gear=self.gear_where)
            self.mark_station = None
            self.gate_post = False
        return True
    if self.may("mark_wait_log", 1, 10 ** 6):
        self.last["mark_wait_log"] = self.now
        log("mark_wait", day=self.day, armed=armed, animals=animals, tiles=tiles, gear=self.gear_where,
            armable=len(self.armable_ids(squad)) if squad else 0)
    return True
def gear_sites(self):
    day = self.day if isinstance(self.day, (int, float)) else None
    if self.gear_cache is not None and day is not None and self.gear_cache[0] == day:
        return self.gear_cache[1]
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    surface = self.surface if num(getattr(self, "surface", None)) \
        else d(getattr(self, "map", None)).get("surface_z")
    out = None
    if num(surface):
        try:
            res = query_result(self.game.query("buildings", limit=1000))
        except Exception as e:
            log("gear_query_error", error=repr(e)[:160])
            res = None
        sites = [b for b in map(d, lst(d(res).get("buildings")))
                 if b.get("type") in ("Stockpile", "Weaponrack", "Armorstand") and num(b.get("z"))]
        if sites:
            box = lambda b: (b.get("x1", b.get("x")), b.get("y1", b.get("y")), b.get("x2", b.get("x")),
                             b.get("y2", b.get("y")), b["z"])
            out = [box(b) for b in sites if b["z"] >= surface and all(num(v) for v in box(b))]
    self.gear_where = "unknown" if out is None else "surface" if out else "below"
    if day is not None:
        self.gear_cache = (day, out)
    return out
def surface_threat(self):
    if not SURFACE_GUARD:
        return []
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    surface = self.surface if num(getattr(self, "surface", None)) else d(getattr(self, "map", None)).get("surface_z")
    if not num(surface):
        return []
    cits = [c for c in self.citizen_spots() if all(num(c.get(k)) for k in ("x", "y", "z"))]
    out = []
    for u in self.marked_units(max(WILD_NEAR_TILES, SURFACE_GUARD_TILES), WILD_NEAR_Z):
        if u["_mark"] not in DANGER_WEAK:
            continue
        evid = self.wild_evidenced([u["_mark"]])
        if SURFACE_GUARD_EVIDENCE and not evid:
            continue
        if any(max(abs(c["x"] - u["x"]), abs(c["y"] - u["y"])) <= SURFACE_GUARD_TILES
               and abs(c["z"] - u["z"]) <= WILD_NEAR_Z and (c["z"] >= surface or evid) for c in cits):
            out.append(u)
    return out
def muster_crossing(self, squad):
    if MUSTER_CLEAR_TILES is None:
        return []
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    members = [(m["x"], m["y"], m["z"]) for m in (d(m) for m in lst(d(squad).get("members")))
               if all(num(m.get(k)) for k in ("x", "y", "z"))]
    gear = self.gear_sites()
    boxes = []
    if gear == []:
        surface = self.surface if num(getattr(self, "surface", None)) \
            else d(getattr(self, "map", None)).get("surface_z")
        spots = [p for p in members if num(surface) and p[2] >= surface]
    else:
        spots = [p for p in self.invader_entrances() if all(num(v) for v in p)] + members
        boxes = list(gear or [])
    out = []
    for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z):
        ds = [max(abs(u["x"] - x), abs(u["y"] - y)) for x, y, z in spots if abs(u["z"] - z) <= WILD_NEAR_Z]
        ds += [max(x1 - u["x"], 0, u["x"] - x2, y1 - u["y"], u["y"] - y2)
               for x1, y1, x2, y2, z in boxes if abs(u["z"] - z) <= WILD_NEAR_Z]
        if ds and min(ds) <= MUSTER_CLEAR_TILES:
            out.append({**u, "_tiles": min(ds)})
    return out
def shaft_wait_close(self):
    tiles = MUSTER_CLEAR_TILES if MUSTER_CLEAR_TILES is not None else WILD_CLOSE_TILES
    gates = self.open_entrances()
    return [u for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z)
            if any(max(abs(u["x"] - gx), abs(u["y"] - gy)) <= tiles and abs(u["z"] - gz) <= WILD_NEAR_Z
                   for gx, gy, gz in gates)]
def station_held(self, squad, x, y, z):
    return any(o.get("order") == "station" and (o.get("x"), o.get("y"), o.get("z")) == (x, y, z)
               for o in map(d, lst(d(squad).get("orders"))))
def muster_big(self):
    span = self.wild_spans[-1] if self.wild_spans else None
    if span is not None and span[1] is None and len(span) > 2 and span[2] == "big":
        return True
    if any(big_race(u.get("race")) or big_race(u.get("_mark"))
           for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z)):
        return True
    since = self.wild_alert_since
    return since is not None and any(big_race(n) and isinstance(t, (int, float)) and t >= since
                                     for n, t in self.wild_watch.items())
def muster_lingering(self, wild):
    if not wild or MUSTER_IDLE_CAP_DAYS is None:
        self.muster_since = None
        return False
    if self.muster_since is None:
        self.muster_since = self.now
    units = self.marked_units(MARK_RANGE, MARK_RANGE_Z)
    if self.wild_contact(units, self.open_entrances(), WILD_CLOSE_TILES):
        self.muster_contact = self.now
    ref = self.muster_since if self.muster_contact is None else max(self.muster_since, self.muster_contact)
    return self.now - ref > MUSTER_IDLE_CAP_DAYS * DAY
def shaft_guard_due(self, units, gates):
    if SHAFT_GUARD_TILES is None:
        return True
    if self.shaft_since is None:
        self.shaft_since = self.now
    if self.wild_contact(units, gates, SHAFT_GUARD_TILES):
        self.shaft_contact = self.now
    ref = self.shaft_since if self.shaft_contact is None else max(self.shaft_since, self.shaft_contact)
    return self.now - ref <= SHAFT_GUARD_HOLD_DAYS * DAY
def squad_hold(self):
    post = getattr(self, "squad_post", None)
    if post is None:
        return
    squad = next(iter(lst(d(self.o.get("military")).get("squads"))), None)
    if not isinstance(squad, dict):
        self.squad_post = None
        return
    if lst(squad.get("orders")):
        return
    key, args = post
    th = d(self.o.get("threats"))
    hostile = th.get("visible_hostiles") or 0
    window = self.invader_window is not None and self.now < self.invader_window
    if key == "guard_muster":
        need = self.muster is not None
    elif key in ("mark_rescue", "mark_gate", "mark_station"):
        need = self.mark_station is not None
    elif key == "invader_guard":
        need = self.invader_guard is not None and window and bool(hostile)
        if not need:
            self.invader_guard = None
    elif key == "attack":
        odds = self.fight_odds(squad, th) if hostile else None
        need = bool(odds and odds["go"]) and not window
        if need:
            args = {"order": "attack"}
            if odds["targets"] is not None:
                args["target_ids"] = odds["targets"]
    elif key == "wild_attack":
        seen = {d(h).get("id") for h in lst(th.get("hostiles"))}
        ids = [i for i in lst(args.get("target_ids")) if i in seen]
        need = bool(ids)
        args = {"order": "attack", "target_ids": ids}
    else:
        need = False
    if not need:
        self.squad_post = None
        return
    r = self.act("squad_reassert", "squad_order", args, retry=0.25, limit=10 ** 6)
    if r is not None:
        log("squad_reassert", day=self.day, owner=key, order=args.get("order"), ok=r.get("ok"),
            code=r.get("error_code"))
def spear_supply(self, squad):
    members = len(lst(squad.get("members")))
    known = (self.equip_day is not None and self.day is not None and self.day >= self.equip_day + 1) \
        or self.duty_seen
    if not members or not known:
        return
    short = members - len(self.armable_ids(squad))
    n = min(short, SPEAR_LIFETIME - self.spears_ordered)
    if n <= 0 or self.own_pending("spear") or not self.may("spear", SPEAR_RETRY_DAYS, 10 ** 6):
        return
    have = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict)}
    why = None
    if "Carpenters" not in have:
        why = "no_carpenters"
    elif self.logs() < self.logs_guard() + n:
        why = "logs"
    elif self.barrel_press() and self.press_stand:
        why = "barrel_press"
    if why is not None:
        if self.may("spear_wait_log", 1, 10 ** 6):
            self.last["spear_wait_log"] = self.now
            log("spear_wait", day=self.day, short=short, why=why, logs=self.logs(), guard=self.logs_guard())
        return
    r = self.act("spear", "add_manager_order", {"job": "MakeWeapon", "material_category": ["wood"],
                                                 "item_subtype": "ITEM_WEAPON_SPEAR", "amount": n},
                 retry=SPEAR_RETRY_DAYS, limit=10 ** 6)
    if r is not None:
        if r.get("ok"):
            self.spears_ordered += n
        log("spear_order", day=self.day, amount=n, short=short, members=members, ok=r.get("ok"),
            ordered=self.spears_ordered, logs=self.logs())
def patient_cancels(self):
    out = {}
    for t in lst(self.o.get("recent_cancellations")) + lst(self.o.get("recent_events")):
        m = GIVE_WATER_RE.search(str(t))
        if m:
            why = m.group(1).strip().lower()
            out[why] = out.get(why, 0) + 1
    return out
def cup_supply(self):
    if self.hands_off is not None or (self.day or 0) < CUP_FROM_DAY or not self.cit:
        return
    target = self.cit + CUP_SPARE
    standing = next((x for x in self.orders if x.get("job") == "MakeGoblet" and x.get("repeat")), None)
    if standing is not None and "o_cups_prog" not in self.done and self.cup_target is None:
        return
    if "o_cups_prog" in self.done:
        oid = self.key_order.get("o_cups_prog")
        if self.cup_target is not None and target > self.cup_target + 1 and oid is not None:
            r = self.act("o_cups_recut", "cancel_order", {"order_id": oid}, retry=2, limit=4)
            if r is not None and r.get("ok"):
                self.done.discard("o_cups_prog")
                self.tries.pop("o_cups_prog", None)
                self.last.pop("o_cups_prog", None)
                log("cup_recut", day=self.day, old=self.cup_target, new=target)
        return
    shops = [w for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("type") == "Craftsdwarfs"
             and not self.shop_stale(w)]
    if not shops:
        owned = self.days >= 336 and (self.day or 0) >= PROGRESS_FROM_DAY and self.cit >= 7
        if not owned and self.logs() >= self.logs_guard():
            self.build("Craftsdwarfs", key="ws_Craftsdwarfs_cup", retry=5)
        return
    guard = self.logs_guard()
    if self.logs() < guard:
        return
    r = self.act("o_cups_prog", "add_manager_order", {
        "job": "MakeGoblet", "material_category": ["wood"], "amount": CUP_BATCH, "repeat": "daily",
        "when": [{"item_type": "GOBLET", "below": target}, {"item_type": "WOOD", "at_least": guard}]},
        retry=3, limit=4)
    if r is not None:
        if r.get("ok"):
            self.cup_target = target
        log("cup_standing", day=self.day, ok=r.get("ok"), target=target, logs=self.logs(), guard=guard,
            err=str(r.get("error") or "")[:120])
def patient_water(self):
    why = self.patient_cancels()
    if why and self.may("patient_water_log", 1, 10 ** 6):
        self.last["patient_water_log"] = self.now
        log("patient_water", day=self.day, reasons=why,
            alert=bool(d(self.o.get("burrows")).get("civilian_alert")))
    if "o_bucket_prog" in self.done:
        return
    shops = {w.get("type") for w in lst(self.o.get("workshops")) if isinstance(w, dict) and w.get("built")}
    if not why or "Carpenters" not in shops or self.logs() < BUCKET_WOOD_FLOOR:
        return
    r = self.act("o_bucket_prog", "add_manager_order", {
        "job": "MakeBucket", "material_category": ["wood"], "amount": BUCKET_KEEP, "repeat": "monthly",
        "when": [{"item_type": "BUCKET", "flags": ["empty"], "below": BUCKET_KEEP},
                 {"item_type": "WOOD", "at_least": BUCKET_WOOD_FLOOR}]}, retry=2, limit=5)
    if r is not None:
        log("bucket_standing", day=self.day, ok=r.get("ok"), patient=bool(why), logs=self.logs(),
            guard=self.logs_guard(), err=str(r.get("error") or "")[:120])
def uniform_choice(self):
    if self.metal_refused:
        return "leather"
    try:
        res = query_result(self.game.query("stocks", item_type="ARMOR"))
    except Exception as e:
        log("uniform_query_error", error=repr(e)[:160])
        return "leather"
    metal = 0
    for g in map(d, lst((res or {}).get("groups"))):
        if str(g.get("material") or "").upper().startswith("INORGANIC"):
            metal += max(0, (g.get("items") or 0) - (g.get("forbidden") or 0) - (g.get("in_job") or 0)
                         - (g.get("in_building") or 0))
    return "metal" if metal > 0 else "leather"
def prearm_units(self):
    return [u for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z)
            if u["_mark"] in DANGER_WEAK or u["_mark"] in self.mark_fought]
def guard_need(self):
    why = None
    if self.wild_alert_since is not None:
        why = "wild_alert"
    elif any(u["_mark"] in DANGER_WEAK for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z)) \
            or (SQUAD_PREARM and self.prearm_units()):
        why = "weak_mark"
    elif SQUAD_PREARM and self.prearm_seen is not None and self.now - self.prearm_seen <= PREARM_HOLD_DAYS * DAY:
        why = "weak_mark"
    elif self.open_entrances():
        why = "open_entrance"
    self.guard_need_why = why
    return why
def fight_left(self):
    left = self.days_to_end()
    ho = self.hands_off
    if isinstance(ho, (int, float)) and not isinstance(ho, bool):
        left = ho if left is None else min(left, ho)
    return left
def fight_odds(self, squad, th):
    squad = d(squad)
    members = len(lst(squad.get("members")))
    armed = min(members, squad.get("armed") or 0) if members else (squad.get("armed") or 0)
    unarmed = max(0, members - armed)
    listed = [d(h) for h in lst(th.get("hostiles"))]
    big = [h for h in listed if not h.get("invader") and big_race(h.get("race"))]
    rest = [h for h in listed if h not in big]
    f_armed = sum(1 for h in rest if h.get("invader") and h.get("weapon"))
    f_unarmed = sum(1 for h in rest if h.get("invader") and not h.get("weapon"))
    f_other = sum(1 for h in rest if not h.get("invader"))
    f_other += max(0, (th.get("visible_hostiles") or 0) - len(listed))
    foes_armed = f_armed + f_other > 0
    ours = armed * FIGHT_ARMED + unarmed * (FIGHT_UNARMED_VS_ARMED if foes_armed else FIGHT_UNARMED)
    theirs = f_armed * FOE_ARMED + f_unarmed * FOE_UNARMED + f_other * FOE_OTHER
    left = self.fight_left()
    endgame = bool(listed) and any(h.get("invader") for h in listed) and left is not None \
        and left <= FIGHT_ENDGAME_DAYS
    ratio = FIGHT_ENDGAME_RATIO if endgame else FIGHT_RATIO
    why = None
    if not squad:
        why = "no_squad"
    elif armed < 1:
        why = "unarmed"
    elif theirs <= 0:
        why = "big_only" if big else "no_target"
    elif foes_armed and unarmed > armed:
        why = "unarmed_majority"
    elif ours < ratio * theirs:
        why = "outmatched"
    retreat = armed < 1 or theirs <= 0 or ours < FIGHT_RETREAT_RATIO * theirs
    return {"ours": round(ours, 2), "theirs": round(theirs, 2), "go": why is None, "retreat": retreat, "why": why,
            "targets": [h.get("id") for h in rest][:20] if big and rest else None, "endgame": endgame,
            "armed": armed, "members": members,
            "foes": {"armed": f_armed, "unarmed": f_unarmed, "other": f_other, "big": len(big)}}
def fight_squad_size(self, th):
    listed = [d(h) for h in lst(th.get("hostiles"))]
    theirs = sum(FOE_ARMED if h.get("weapon") else FOE_UNARMED for h in listed if h.get("invader")) \
        + FOE_OTHER * sum(1 for h in listed if not h.get("invader") and not big_race(h.get("race"))) \
        + FOE_OTHER * max(0, (th.get("visible_hostiles") or 0) - len(listed))
    need = int(-(-FIGHT_RATIO * theirs // FIGHT_ARMED))
    return max(4, min(10, (self.cit or 0) // 3, need))
def invader_entrances(self):
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    out = {p: None for _, p in sorted(self.entrances.items(), key=lambda kv: site_key(kv[0]))}
    for s in self.kind("E"):
        p = (s.get("x"), s.get("y"), s.get("z"))
        if all(num(v) for v in p):
            out.setdefault(p, None)
    return list(out)
def invaders_at_entrance(self, invaders):
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    ents = self.invader_entrances()
    out = []
    for h in map(d, invaders):
        if not all(num(h.get(k)) for k in ("x", "y", "z")):
            continue
        if any(max(abs(h["x"] - x), abs(h["y"] - y)) <= INVADER_ENTRANCE_TILES and abs(h["z"] - z) <= WILD_NEAR_Z
               for x, y, z in ents):
            out.append(h.get("id"))
    return out
def invader_guard_station(self, squad, invaders):
    if self.invader_guard is not None:
        return
    why = None
    if not squad:
        why = "no_squad"
    elif (squad.get("armed") or 0) < 1:
        why = "unarmed" if squad.get("uniform") not in (None, "none") else "unequipped"
    ents = self.invader_entrances()
    if why is None and not ents:
        why = "no_entrance"
    if why is not None:
        if self.invader_unguarded_day != self.day:
            self.invader_unguarded_day = self.day
            log("invader_unguarded", day=self.day, why=why, invaders=len(invaders),
                until_day=round(self.invader_window / DAY, 1) if self.invader_window is not None else None)
        return
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    pos = [d(h) for h in invaders if all(num(d(h).get(k)) for k in ("x", "y"))]
    gx, gy, gz = min(ents, key=lambda p: min((max(abs(p[0] - h["x"]), abs(p[1] - h["y"])) for h in pos),
                                             default=0))
    z = gz - 1 if self.invader_guard_foot else gz
    r = self.act("invader_guard", "squad_order", {"order": "station", "x": gx, "y": gy, "z": z},
                 retry=0.25, limit=10 ** 6)
    if r and r.get("ok"):
        self.invader_guard = (gx, gy, z)
        self.mark_station = None
        self.gate_post = False
        log("invader_guard", day=self.day, x=gx, y=gy, z=z, invaders=len(invaders),
            armed=squad.get("armed") or 0)
    elif r is not None:
        self.invader_guard_foot = not self.invader_guard_foot
def cancel_animals(self):
    out = []
    for t in lst(self.o.get("recent_cancellations")):
        m = re.search(r"interrupted by an? ([a-z][a-z '\-]*[a-z])", str(t).lower())
        if m:
            out.append(m.group(1).strip())
    return out
def record_wildlife(self, stamp):
    seen = set(self.cancel_animals())
    if stamp is None:
        return seen
    for name in seen:
        last = self.wild_day.get(name)
        if last is None or not isinstance(last, (int, float)) or stamp - last > WILDLIFE_GAP_DAYS:
            self.wild_from[name] = stamp
        self.wild_day[name] = stamp
    for name, last in list(self.wild_day.items()):
        if name not in seen and isinstance(last, (int, float)) and stamp - last > WILDLIFE_GAP_DAYS:
            self.wild_day.pop(name, None)
            self.wild_from.pop(name, None)
    return seen
def wild_units(self, names, hostile_only=True):
    if self.wild_units_memo is not None and self.wild_units_memo[0] == self.loads:
        units = self.wild_units_memo[1]
    else:
        try:
            q = self.game.query("units", kind="others", limit=300)
        except Exception as e:
            log("wild_query_error", error=repr(e)[:160])
            return []
        res = query_result(q)
        if res is None:
            log("wild_query_error", error=query_error(q))
            return []
        units = [d(u) for u in lst(res.get("units"))]
        self.wild_units_memo = (self.loads, units)
    out = []
    for u in units:
        race = str(u.get("race") or "").lower().replace("_", " ")
        if not u.get("visitor") and race and (u.get("hostile") or not hostile_only) \
                and any(race in name or name in race for name in names):
            out.append(u)
    return out
def wild_targets(self, names, hostile_only=True):
    return [u.get("id") for u in self.wild_units(names, hostile_only)][:20]
def wild_near(self, names):
    return [u.get("id") for u in self.wild_near_units(names)]
def wild_near_units(self, names):
    wag = d(self.map.get("wagon"))
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if not names or not all(num(wag.get(k)) for k in ("x", "y", "z")):
        return []
    out = []
    for u in self.wild_units(names, hostile_only=False):
        if all(num(u.get(k)) for k in ("x", "y", "z")) \
                and max(abs(u["x"] - wag["x"]), abs(u["y"] - wag["y"])) <= WILD_NEAR_TILES \
                and abs(u["z"] - wag["z"]) <= WILD_NEAR_Z:
            out.append(u)
    return out
def wild_watched(self):
    return sorted(n for n, t in self.wild_watch.items()
                  if isinstance(t, (int, float)) and self.now - t <= WILD_MEMORY_DAYS * DAY)
def wild_resting(self):
    return self.wild_rest_until is not None and self.now < self.wild_rest_until
def wild_alert_on(self, now=None, big=False):
    now = self.now if now is None else now
    self.wild_alert_since = now
    self.alert_since = now
    if not self.wild_spans or self.wild_spans[-1][1] is not None:
        self.wild_spans.append([now, None, "big"] if big else [now, None])
def wild_alert_closed(self):
    if self.wild_spans and self.wild_spans[-1][1] is None:
        self.wild_spans[-1][1] = self.now
def wild_budget_used(self):
    lo = self.now - WILD_BUDGET_WINDOW * DAY
    used = 0
    for sp in self.wild_spans:
        if len(sp) > 2:
            continue
        a, b = sp[0], sp[1]
        b = self.now if b is None else b
        used += max(0, min(b, self.now) - max(a, lo))
    self.wild_spans = [sp for sp in self.wild_spans if sp[1] is None or sp[1] > lo]
    return used / DAY
def wild_budget_left(self):
    return self.wild_budget_used() < WILD_BUDGET_DAYS
def budget_fight(self, names):
    if not BUDGET_FIGHT_DAYS or not names:
        return False
    fought = [set(n.split()) for n, t in self.wild_fight.items()
              if isinstance(t, (int, float)) and self.now - t <= BUDGET_FIGHT_DAYS * DAY]
    hit = any(w and f and (w <= f or f <= w) for f in fought for w in (set(str(n).split()) for n in names))
    if hit and not self.wild_budget_left() and self.may("budget_fight_log", 1, 10 ** 6):
        self.last["budget_fight_log"] = self.now
        log("budget_fight", day=self.day, animals=sorted(names), used=round(self.wild_budget_used(), 1))
    return hit
def note_wild_evidence(self, obs):
    obs = d(obs)
    for n in self.cancel_animals_of(obs):
        self.wild_evidence[n] = self.now
        m = mark_name(n)
        if m:
            self.wild_evidence[m] = self.now
    fresh = []
    for t in lst(obs.get("recent_events")):
        t = str(t)
        if t not in self.event_seen:
            self.event_seen[t] = self.now
        if self.now - self.event_seen[t] <= WILD_EVIDENCE_DAYS * DAY:
            fresh.append(t)
    if len(self.event_seen) > 2000:
        for t, _ in sorted(self.event_seen.items(), key=lambda kv: kv[1])[:1000]:
            self.event_seen.pop(t, None)
    for name in self.combat_species(obs, fresh):
        self.wild_evidence[name] = self.now
    for name in self.combat_species(obs, [t for t in fresh if self.event_seen.get(t) == self.now]):
        self.wild_fight[name] = self.now
def cancel_animals_of(self, obs):
    out = []
    for t in lst(d(obs).get("recent_cancellations")):
        m = re.search(r"interrupted by an? ([a-z][a-z '\-]*[a-z])", str(t).lower())
        if m:
            out.append(m.group(1).strip())
    return out
def combat_species(self, obs, events):
    obs = d(obs)
    profs = {str(p.get("profession") or "").lower() for p in lst(obs.get("dwarves")) if isinstance(p, dict)}
    profs = {p for p in profs if p} | CITIZEN_WORDS
    out = []
    for t in events:
        m = COMBAT_RE.match(str(t).lower().strip())
        if not m:
            continue
        a, b = m.group(1).strip(), m.group(2).strip()
        ca, cb = citizen_noun(a, profs), citizen_noun(b, profs)
        other = b if ca and not cb else a if cb and not ca else None
        name = mark_name(other) if other else None
        if name and name not in profs:
            out.append(name)
    return out
def wild_evidenced(self, names):
    def same(a, b):
        wa, wb = set(a.split()), set(b.split())
        return bool(wa) and bool(wb) and (wa <= wb or wb <= wa)
    return any(isinstance(t, (int, float)) and self.now - t <= WILD_EVIDENCE_DAYS * DAY and same(n, e)
               for n in names for e, t in self.wild_evidence.items())
def wild_approaching(self, units):
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    cits = [(p["x"], p["y"], p["z"]) for p in lst(self.o.get("dwarves"))
            if isinstance(p, dict) and all(num(p.get(k)) for k in ("x", "y", "z"))]
    if not cits:
        return False
    if self.wild_dist_load != self.loads:
        self.wild_dist_load = self.loads
        self.wild_dist_prev = dict(self.wild_dist)
    hit = False
    for u in units:
        u = d(u)
        if not all(num(u.get(k)) for k in ("x", "y", "z")):
            continue
        dist = min(max(abs(u["x"] - x), abs(u["y"] - y)) for x, y, z in cits if abs(u["z"] - z) <= WILD_NEAR_Z) \
            if any(abs(u["z"] - z) <= WILD_NEAR_Z for _, _, z in cits) else None
        if dist is None:
            continue
        prev = self.wild_dist_prev.get(u.get("id"))
        if dist <= WILD_CLOSE_TILES or (prev is not None and prev - dist >= WILD_APPROACH_TILES):
            hit = True
        self.wild_dist[u.get("id")] = dist
    return hit
def wildlife_response(self):
    if d(self.o.get("burrows")).get("civilian_alert"):
        return
    self.wildlife_alert()
    stamp = self.wild_stamp()
    names = [n for n in self.wild_day
             if self.wild_from.get(n) is not None and self.wild_day[n] != self.wild_from[n]]
    if not names or self.wild_act_stamp == stamp:
        return
    squad = next(iter(lst(d(self.o.get("military")).get("squads"))), None)
    if squad is None:
        if self.cit >= WILDLIFE_MIN_CIT:
            r = self.create_squad("wild_squad", WILDLIFE_SQUAD_SIZE)
            if r:
                self.wild_act_stamp = stamp
        return
    orders = lst(d(squad).get("orders"))
    if any(d(o).get("order") == "attack" and (d(o).get("targets_alive") or 0) > 0 for o in orders):
        self.wild_act_stamp = stamp
        return
    targets = self.wild_targets(sorted(names))
    if targets:
        self.act("wild_attack", "squad_order", {"order": "attack", "target_ids": targets}, retry=1, limit=99)
    self.wild_act_stamp = stamp
def wild_alert_hold(self):
    if self.wild_alert_since is None:
        return False
    if not self.wild_budget_left() and not self.budget_fight(self.wild_watched()):
        log("wild_budget_out", day=self.day, used=round(self.wild_budget_used(), 1))
        return False
    if self.now - self.wild_alert_since <= WILD_ALERT_DAYS * DAY:
        watched = self.wild_watched()
        last = max((self.wild_watch.get(n) or 0 for n in watched), default=self.wild_alert_since)
        far_ok = not self.marked_units(MARK_RANGE, MARK_RANGE_Z) and not (
            self.wild_near_units(watched) if watched else [])
        gone = self.now - max(last, self.wild_alert_since) > WILD_GONE_DAYS * DAY
        if not (far_ok and gone):
            return True
        log("wild_gone", day=self.day, animals=watched)
        return False
    names = self.wild_watched()
    near = self.wild_near_units(names) if names else []
    marked = self.marked_units(WILD_NEAR_TILES, WILD_NEAR_Z)
    if marked:
        names = sorted(set(names) | {u["_mark"] for u in marked})
        near = near + marked
    if near:
        approach = self.wild_approaching(near)
        if not (self.wild_evidenced(names) or approach):
            log("wild_hold_no_evidence", day=self.day, animals=names, near=len(near))
            return False
        for n in names:
            self.wild_watch[n] = self.now
        log("wild_hold", day=self.day, animals=names, near=len(near), approach=approach)
        return True
    return False
def wildlife_alert(self):
    if self.wild_alert_since is not None or self.wild_resting() \
            or (not self.wild_budget_left() and not self.budget_fight(self.wild_watched())) \
            or self.alert_barred():
        return
    squad = next(iter(lst(d(self.o.get("military")).get("squads"))), None)
    armed = squad is not None and (d(squad).get("armed") or 0) >= 1
    bur = d(self.o.get("burrows"))
    if not self.shelter_listed(bur):
        return
    watched = self.wild_watched()
    if watched and self.may("wild_return_q", 1, 10 ** 6):
        self.last["wild_return_q"] = self.now
        near_u = self.wild_near_units(watched)
        near = [u.get("id") for u in near_u]
        if near and not (armed and self.wild_targets(watched)) \
                and (self.wild_evidenced(watched) or self.wild_approaching(near_u)):
            if self.shelter_wet("wild_return"):
                return
            r = self.act("wild_return", "civilian_alert", {"on": True}, retry=1, limit=99)
            if r and r.get("ok"):
                self.wild_alert_on()
                for n in watched:
                    self.wild_watch[n] = self.now
                log("wild_alert", day=self.day, animals=watched, reason="return", near=len(near))
            return
    seen = [n for n, last in self.wild_day.items() if last == self.wild_stamp()]
    if not seen:
        return
    if not self.may("wild_alert", 7, 99) or not self.may("wild_alert_q", 1, 10 ** 6):
        return
    self.last["wild_alert_q"] = self.now
    if armed and self.wild_targets(sorted(seen)):
        return
    animals = sorted(seen)
    if not self.wild_targets(animals):
        counts = {}
        for n in self.cancel_animals():
            counts[n] = counts.get(n, 0) + 1
        troop = sorted(n for n in seen if counts.get(n, 0) >= WILD_TROOP_CANCELS)
        if not troop or not self.wild_targets(troop, hostile_only=False):
            return
        animals = troop
    if self.shelter_wet("wild_alert"):
        return
    r = self.act("wild_alert", "civilian_alert", {"on": True}, retry=7, limit=99)
    if r and r.get("ok"):
        self.wild_alert_on()
        for n in animals:
            self.wild_watch[n] = self.now
        log("wild_alert", day=self.day, animals=sorted(seen))
def learn_marks(self, obs):
    obs = d(obs)
    profs = {str(p.get("profession") or "").lower() for p in lst(obs.get("dwarves")) if isinstance(p, dict)}
    profs = {p for p in profs if p} | CITIZEN_WORDS
    found = []
    for t in lst(obs.get("recent_cancellations")):
        m = re.search(r"interrupted by an? ([a-z][a-z '\-]*[a-z])", str(t).lower())
        if m:
            found.append((mark_name(m.group(1)), "interrupt", str(t)))
    for t in lst(obs.get("recent_events")):
        m = COMBAT_RE.match(str(t).lower().strip())
        if not m:
            continue
        a, b = m.group(1).strip(), m.group(2).strip()
        ca, cb = citizen_noun(a, profs), citizen_noun(b, profs)
        if ca and not cb:
            found.append((mark_name(b), "combat", str(t)))
        elif cb and not ca:
            found.append((mark_name(a), "combat", str(t)))
    for name, src, text in found:
        if name and src == "combat" and name not in profs:
            self.mark_fought.add(name)
        if not name or name in profs or name in self.marked:
            continue
        if src == "interrupt":
            seen = self.mark_interrupts.setdefault(name, set())
            if len(seen) < 50:
                seen.add(text)
            if len(seen) < MARK_LEARN_INTERRUPTS:
                continue
        self.marked[name] = src
        log("danger_mark", day=self.day, species=name, source=src, text=text[:160])
    return found
def others(self, day=None):
    if day is None:
        if self.wild_units_memo is not None and self.wild_units_memo[0] == self.loads:
            return self.wild_units_memo[1]
    elif self.mark_query is not None and self.mark_query[0] == day:
        return self.mark_query[1]
    try:
        q = self.game.query("units", kind="others", limit=300)
    except Exception as e:
        log("mark_query_error", error=repr(e)[:160])
        return []
    res = query_result(q)
    if res is None:
        log("mark_query_error", error=query_error(q))
        return []
    units = [d(u) for u in lst(res.get("units"))]
    if day is None:
        self.wild_units_memo = (self.loads, units)
    else:
        self.mark_query = (day, units)
    return units
def mark_of(self, u):
    if d(u).get("visitor"):
        return None
    hits = [n for n in self.marked if race_matches(d(u).get("race"), n)]
    return max(hits, key=len) if hits else None
def marked_units(self, tiles, z, obs=None, units=None):
    obs = d(self.o if obs is None else obs)
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    anchors = [d(d(obs.get("map")).get("wagon"))] + [p for p in lst(obs.get("dwarves")) if isinstance(p, dict)]
    anchors = [(a["x"], a["y"], a["z"]) for a in anchors if all(num(a.get(k)) for k in ("x", "y", "z"))]
    if not anchors:
        return []
    out = []
    for u in (self.others() if units is None else units):
        name = self.mark_of(u)
        if not name or not all(num(u.get(k)) for k in ("x", "y", "z")):
            continue
        if any(max(abs(u["x"] - x), abs(u["y"] - y)) <= tiles and abs(u["z"] - zz) <= z for x, y, zz in anchors):
            out.append({**u, "_mark": name})
    return out
def danger_signs(self, resp, query=True):
    obs = d(resp.get("observation"))
    self.learn_marks(obs)
    signs = set()
    if d(obs.get("threats")).get("visible_hostiles"):
        signs.add("hostile")
    for t in lst(obs.get("recent_cancellations")):
        m = re.search(r"interrupted by an? ([a-z][a-z '\-]*[a-z])", str(t).lower())
        if m and mark_name(m.group(1)):
            signs.add("interrupt:" + mark_name(m.group(1)))
    if d(obs.get("burrows")).get("civilian_alert"):
        signs.add("alert")
    for m in lst(obs.get("moods")):
        if d(m).get("mood") in ("Berserk", "Raving", "Melancholy", "Traumatized", "Fell", "Macabre"):
            signs.add("mood:" + str(d(m).get("mood")))
    tick = d(obs.get("date")).get("abs_tick") or resp.get("tick")
    self.note_access(obs, tick)
    if self.thirst_due(tick) and not self.access_free(obs):
        signs.add("thirst")
    if self.breach or (self.water_rise_tick is not None and isinstance(tick, (int, float))
                       and tick - self.water_rise_tick <= 3 * DAY):
        signs.add("water")
    day = resp.get("day")
    if query:
        units = self.others(day if isinstance(day, int) else -1)
    elif self.wild_units_memo is not None and self.wild_units_memo[0] == self.loads:
        units = self.wild_units_memo[1]
    else:
        units = []
    for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z, obs=obs, units=units):
        signs.add("marked:" + u["_mark"])
    for u in self.marked_units(WILD_NEAR_TILES, WILD_NEAR_Z, obs=obs, units=units):
        signs.add("near:" + u["_mark"])
        surface = d(obs.get("map")).get("surface_z", getattr(self, "surface", None))
        if isinstance(surface, (int, float)) and any(
                c["z"] >= surface and abs(c["z"] - u["z"]) <= WILD_NEAR_Z
                and max(abs(c["x"] - u["x"]), abs(c["y"] - u["y"])) <= WILD_CLOSE_TILES
                for c in self.citizen_spots(obs)):
            signs.add("exposed:" + u["_mark"])
    for name in self.combat_species(obs, lst(obs.get("recent_events"))):
        if name in self.marked:
            signs.add("fight:" + name)
    try:
        signs |= self.rush_signs(obs)
    except Exception as e:
        log("rush_sign_error", error=repr(e)[:160])
    return sorted(signs)
def big_units(self):
    return [u for u in self.marked_units(WILD_NEAR_TILES, WILD_NEAR_Z) if big_race(u.get("race"))]
def big_alert(self, bur, alert):
    if alert or self.wild_alert_since is not None or self.alert_barred() \
            or not self.shelter_listed(bur):
        return False
    big = self.big_units()
    if not big:
        return False
    resting = self.wild_resting()
    if resting and not self.wild_approaching(big):
        return False
    if self.shelter_wet("big_alert"):
        return False
    r = self.act("big_alert", "civilian_alert", {"on": True}, retry=0.25, limit=10 ** 6)
    if not (r and r.get("ok")):
        return False
    self.wild_alert_on(big=True)
    self.wild_rest_until = None
    for u in big:
        self.wild_watch[u["_mark"]] = self.now
    log("big_alert", day=self.day, animals=sorted({u["_mark"] for u in big}), near=len(big),
        reason="approach_in_rest" if resting else "near")
    return True
def shelter_grow(self):
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    below = lambda z: num(z) and (not num(self.surface) or z < self.surface)
    todo, a_levels, level_open = [], set(), []
    open_z = {b[4] for sid, b in self.shelter_boxes.items() if sid in self.shelter_level_in
              and isinstance(b, tuple) and len(b) == 5}
    short = self.shelter_tiles() < SHELTER_TILES_PER_CIT * (self.cit or 0)
    same_open = lambda z: short and z in open_z
    level_in = set()
    landing = self.gate_landings()
    held = self.gate_pending()
    def gated(s):
        if not all(num(s.get(k)) for k in ("x", "y", "z")):
            return False
        x1, y1 = s["x"], s["y"]
        x2, y2 = x1 + max(1, int(s.get("w") or 1)) - 1, y1 + max(1, int(s.get("h") or 1)) - 1
        if any(c == s["z"] and x1 <= a <= x2 and y1 <= b <= y2 for a, b, c in landing):
            return True
        r = GATE_QUERY_RADIUS
        return any(zs - GATE_LEVELS <= s["z"] < zs and x1 <= a + r and a - r <= x2 and y1 <= b + r and b - r <= y2
                   for a, b, zs in held)
    for s in sorted(self.kind("A"), key=lambda s: -(s.get("z") or 0)):
        z = s.get("z")
        if not below(z) or not self.dry(z) or s.get("id") is None:
            continue
        if s["id"] not in self.shelter_added and gated(s):
            if s["id"] not in self.shelter_skip:
                self.shelter_skip.add(s["id"])
                log("shelter_gate_skip", day=self.day, site=s["id"], z=z, held=bool(held))
            continue
        if (s.get("w") or 0) > SHELTER_SIDE_MAX or (s.get("h") or 0) > SHELTER_SIDE_MAX:
            if s["id"] not in self.shelter_skip:
                self.shelter_skip.add(s["id"])
                log("shelter_wide", day=self.day, site=s["id"], z=z, w=s.get("w"), h=s.get("h"))
            continue
        if s["id"] not in self.shelter_added:
            n_open = self.site_open(s)
            if n_open:
                if ("open", s["id"]) not in self.shelter_skip:
                    self.shelter_skip.add(("open", s["id"]))
                    log("shelter_open_skip", day=self.day, site=s["id"], z=z, outside=n_open)
                continue
            if self.level_open(self.shelter_box_of(s)):
                if ("level", s["id"]) not in self.shelter_skip:
                    self.shelter_skip.add(("level", s["id"]))
                    log("shelter_level_skip", day=self.day, site=s["id"], z=z)
                if not same_open(z):
                    level_open.append(s)
                    continue
                level_in.add(s["id"])
        a_levels.add(z)
        todo.append(s)
    for r in sorted(self.kind("R"), key=lambda s: -(s.get("z") or 0)):
        z = r.get("z")
        if r.get("dug") and below(z) and self.dry(z) and z not in a_levels and r.get("id") is not None \
                and (r["id"] in self.shelter_added or not gated(r)):
            if r["id"] not in self.shelter_added and self.level_open(self.shelter_box_of(r)):
                if ("level", r["id"]) not in self.shelter_skip:
                    self.shelter_skip.add(("level", r["id"]))
                    log("shelter_level_skip", day=self.day, site=r["id"], z=z)
                if not same_open(z):
                    level_open.append(r)
                    continue
                level_in.add(r["id"])
            todo.append(r)
    if not self.shelter_added and not todo and level_open:
        todo.append(level_open[0])
        level_in.add(level_open[0].get("id"))
        if self.may("shelter_level_fallback_log", 1, 10 ** 6):
            self.last["shelter_level_fallback_log"] = self.now
            log("shelter_level_fallback", day=self.day, site=level_open[0].get("id"))
    n = 0
    for s in todo:
        if s["id"] in self.shelter_added or n >= SHELTER_PER_PASS:
            continue
        args = {"site": s["id"]}
        if s.get("kind") == "R":
            args.update(self.box_wh(s, SHELTER_SIDE_MAX))
        if self.shelter_added and self.pocket_box(dict(s, **{k: args[k] for k in ("w", "h") if k in args})):
            if ("pocket", s["id"]) not in self.shelter_skip:
                self.shelter_skip.add(("pocket", s["id"]))
                log("shelter_pocket_skip", day=self.day, site=s["id"], z=s.get("z"))
            continue
        res = self.act("shelter_" + str(s["id"]), "create_burrow", args, retry=1, limit=3)
        if res is None:
            continue
        n += 1
        if res.get("ok") or res.get("error_code") == "nothing_designated":
            self.shelter_added.add(s["id"])
            if s["id"] in level_in:
                self.shelter_level_in.add(s["id"])
            if all(num(s.get(k)) for k in ("x", "y", "z")):
                bw, bh = args.get("w", s.get("w") or 1), args.get("h", s.get("h") or 1)
                self.shelter_boxes[s["id"]] = (s["x"], s["y"], s["x"] + max(1, int(bw)) - 1,
                                               s["y"] + max(1, int(bh)) - 1, s["z"])
            log("shelter_add", day=self.day, site=s["id"], z=s.get("z"),
                tiles=d(res.get("result")).get("tiles_added", res.get("tiles_added")))
def shelter_listed(self, bur):
    return any(d(b).get("civ_alert_burrow") for b in lst(d(bur).get("list"))) or bool(getattr(self, "shelter_made", False))
def shelter_wet(self, what=None):
    wet = bool(self.breach) or any(box[4] in self.wet_z for box in self.shelter_boxes.values()
                                   if isinstance(box, tuple) and len(box) == 5)
    if wet and what is not None and self.wet_skip_day.get(what) != self.day:
        self.wet_skip_day[what] = self.day
        log("shelter_wet_hold", day=self.day, held=what, breach=bool(self.breach), wet_z=sorted(self.wet_z))
    return wet
def shelter_counts(self):
    bur = d(self.o.get("burrows"))
    shelter = next((d(b) for b in lst(bur.get("list")) if d(b).get("civ_alert_burrow")), None)
    inside = (shelter or {}).get("citizens_inside")
    ok = isinstance(inside, (int, float)) and not isinstance(inside, bool)
    return (inside if ok else None), self.cit
def hatch_water(self, hatch):
    hid = hatch.get("id")
    memo = self.hatch_water_memo.get(hid)
    if memo is not None and memo[0] == self.day:
        return memo[1]
    x, y, z = hatch.get("x"), hatch.get("y"), hatch.get("z")
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in (x, y, z)):
        return None
    box = (x, y, 1, 1, z)
    z2 = max(0, z - 2)
    n = self.scan_count(box, WATER_DIG_MARGIN, z2, z)
    if n is None and getattr(self.game, "query", None) is not None and self.water_probe_ok():
        n = self.probe_count("hatch_%s" % hid, box, WATER_DIG_MARGIN, z2, z)
    if n is not None:
        self.hatch_water_memo[hid] = (self.day, n)
    return n
def flood_lock_wanted(self, hatch):
    n = self.hatch_water(hatch)
    if n is not None:
        return n > 0
    inside, cit = self.shelter_counts()
    return inside is not None and isinstance(cit, (int, float)) and cit > 0 and inside >= cit
def flood_hatch_release(self, doors):
    if not self.flood_locked:
        return
    by_id = {d(x).get("id"): d(x) for x in lst(doors.get("list")) if d(x).get("id") is not None}
    inside, cit = self.shelter_counts()
    outside = inside is None or (isinstance(cit, (int, float)) and inside < cit)
    for hid in sorted(self.flood_locked, key=lambda v: (str(type(v)), str(v).zfill(12))):
        x = by_id.get(hid)
        if x is None or not x.get("locked"):
            self.flood_locked.discard(hid)
            continue
        if self.breach and not (outside and self.hatch_water(x) == 0):
            continue
        r = self.act("flood_unlock_" + str(hid), "lock_door", {"locked": False, "door_id": hid},
                     retry=0.25, limit=10 ** 6)
        if r and r.get("ok"):
            self.flood_locked.discard(hid)
            log("flood_unlock", day=self.day, door=hid, breach=bool(self.breach), inside=inside, citizens=cit)
    if not self.breach and not self.flood_locked:
        self.hatch_id = None
def entrance_hatches(self):
    doors = self.o.get("doors")
    if not isinstance(doors, dict):
        return
    self.flood_hatch_release(doors)
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    for s in self.kind("E"):
        if s.get("id") is not None and all(num(s.get(k)) for k in ("x", "y", "z")):
            self.entrances[s["id"]] = (s["x"], s["y"], s["z"])
    dl = [d(x) for x in lst(doors.get("list"))]
    by_id = {x.get("id"): x for x in dl if x.get("id") is not None}
    at = {(x.get("x"), x.get("y"), x.get("z")): x for x in dl if x.get("kind") == "hatch"}
    ents_all = sorted(self.entrances.items(), key=lambda kv: site_key(kv[0]))
    ents = ents_all
    hatches = [at[p] for _, p in ents if p in at]
    blocked = {d(x).get("id") for x in self.kind("E") if d(x).get("building")} | self.entrance_occupied
    for sid, p in ents:
        if p not in at and sid in blocked and sid not in self.entrance_occupied:
            self.entrance_occupied.add(sid)
            log("entrance_open", day=self.day, site=sid, at=p, why="building")
    missing = [sid for sid, p in ents if p not in at and sid not in blocked]
    sh = getattr(self, "shaft", None)
    if sh is not None:
        missing = [sid for sid in missing if sid != sh.get("e")
                   and self.entrances.get(sid) != (sh.get("x"), sh.get("y"), sh.get("z"))]
    bur = d(self.o.get("burrows"))
    alert = bur.get("civilian_alert") is True
    shelter = next((d(b) for b in lst(bur.get("list")) if d(b).get("civ_alert_burrow")), None)
    free = doors.get("hatch_cover_items_free") or 0
    if sh is not None and not any(p == (sh.get("x"), sh.get("y"), sh.get("z")) for p in at):
        free -= 1
    if shelter is not None and missing and not self.breach and free > 0:
        ok = [sid for sid in missing if not alert or self.hatch_safe(self.entrances.get(sid))]
        for sid in ok[:free]:
            r = self.act("entrance_hatch_" + str(sid), "build_door", {"kind": "hatch", "site": sid},
                         retry=1 if alert else 3, limit=6)
            if r and r.get("ok"):
                log("entrance_hatch", day=self.day, site=sid, **({"alert": True} if alert else {}))
            elif r and r.get("error_code") == "tile_occupied" and sid not in self.entrance_occupied:
                self.entrance_occupied.add(sid)
                log("entrance_open", day=self.day, site=sid, at=self.entrances.get(sid))
        if alert and len(ok) < len(missing) and self.may("hatch_hold_log", 1, 10 ** 6):
            self.last["hatch_hold_log"] = self.now
            log("hatch_hold", day=self.day, held=[sid for sid in missing if sid not in ok])
    self.hatch_order(missing, free)
    if shelter is not None:
        self.gate_build(doors, alert)
    inside = (shelter or {}).get("citizens_inside")
    all_in = alert and num(inside) and num(self.cit) and self.cit > 0 and inside >= self.cit
    flood = self.hatch_id if self.breach else None
    if all_in and self.shelter_wet("alert_lock"):
        all_in = False
    if all_in:
        skip = self.lock_skip(ents_all, at)
        if skip:
            all_in = False
            if self.lock_skip_day != self.day:
                self.lock_skip_day = self.day
                log("alert_lock_skip", day=self.day, why=skip)
    if all_in:
        spots = {(c["x"], c["y"], c["z"]) for c in self.citizen_spots()}
        gates = [g for g, land in self.gate_locks() if not (spots & land)]
        for h in hatches + gates:
            hid = h.get("id")
            if hid is None or h.get("locked") or hid == flood or hid in self.flood_locked:
                continue
            r = self.act("alert_lock_" + str(hid), "lock_door", {"locked": True, "door_id": hid},
                         retry=0.25, limit=10 ** 6)
            if r and r.get("ok"):
                self.alert_locked.add(hid)
                log("alert_lock", day=self.day, door=hid, inside=inside, citizens=self.cit)
        return
    for hid in sorted(self.alert_locked, key=lambda v: (str(type(v)), str(v).zfill(12))):
        x = by_id.get(hid)
        if x is None or hid == flood or hid in self.flood_locked or not x.get("locked"):
            self.alert_locked.discard(hid)
            continue
        r = self.act("alert_unlock_" + str(hid), "lock_door", {"locked": False, "door_id": hid},
                     retry=0.25, limit=10 ** 6)
        if r and r.get("ok"):
            self.alert_locked.discard(hid)
            log("alert_unlock", day=self.day, door=hid, alert=alert, inside=inside, citizens=self.cit)
def hatch_safe(self, p):
    if not (isinstance(p, tuple) and len(p) == 3):
        return False
    x, y, z = p
    if any(isinstance(b, tuple) and len(b) == 5 and b[4] == z and b[0] <= x <= b[2] and b[1] <= y <= b[3]
           for b in self.shelter_boxes.values()):
        return True
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    hostiles = [d(h) for h in lst(d(self.o.get("threats")).get("hostiles"))]
    for u in list(self.others()) + hostiles:
        if (self.mark_of(u) or u.get("hostile") or u in hostiles) and all(num(u.get(k)) for k in ("x", "y", "z")) \
                and max(abs(u["x"] - x), abs(u["y"] - y)) <= WILD_NEAR_TILES and abs(u["z"] - z) <= WILD_NEAR_Z:
            return False
    return True
def hatch_order(self, missing, free):
    if self.breach or self.hatch_ordered >= HATCH_ORDER_CAP:
        return
    queued = sum(max(0, x.get("left") or 0) for x in self.orders if x.get("recipe") == "make_hatch_cover")
    want = len(missing) + (HATCH_SPARE if len(self.entrances) < ENTRANCE_MAX else 0)
    need = want - max(0, free) - queued
    if need <= 0:
        return
    amount = min(need, ENTRANCE_MAX, HATCH_ORDER_CAP - self.hatch_ordered)
    if HATCH_FIRST_EARLY and self.hatch_ordered == 0 and isinstance(self.day, (int, float)) \
            and self.day <= HATCH_FIRST_DAYS and self.logs() < amount + HATCH_WOOD_FLOOR:
        amount = 1
    elif self.logs() < amount + HATCH_WOOD_FLOOR:
        if self.may("hatch_wood_log", 2, 10 ** 6):
            self.last["hatch_wood_log"] = self.now
            log("hatch_wood_wait", day=self.day, need=amount, logs=self.logs())
        return
    r = self.act("hatch_early_order", "add_order", {"recipe": "make_hatch_cover", "amount": amount},
                 retry=1, limit=4 * ENTRANCE_MAX)
    if r and r.get("ok"):
        self.hatch_ordered += amount
        log("hatch_order", day=self.day, amount=amount, missing=len(missing), free=free, queued=queued)
def squad_out(self):
    surface = self.surface
    for sq in lst(d(self.o.get("military")).get("squads")):
        for o in lst(d(sq).get("orders")):
            o = d(o)
            if o.get("order") == "attack" and (o.get("targets_alive") is None or o.get("targets_alive") > 0):
                return True
            if o.get("order") == "station":
                z = o.get("z")
                if not isinstance(z, (int, float)) or not isinstance(surface, (int, float)) or z >= surface:
                    return True
    return False
def shelter_trap(self):
    drink = self.st.get("drink")
    if not isinstance(drink, (int, float)) or isinstance(drink, bool) or drink <= 0:
        return
    if self.trap_seen < TRAP_SEEN or self.trap_pokes >= TRAP_POKES:
        return
    if self.trap_last is not None and isinstance(self.now, (int, float)) \
            and self.now - self.trap_last < TRAP_POKE_DAYS * DAY:
        return
    how, r = None, None
    if self.trap_pokes == 0 and self.logs() - self.logs_guard() >= TRAP_WOOD_SPARE:
        sites = [s for s in self.kind("W") if not self.frame_on(s)]
        if sites:
            how = "workshop"
            r = self.act("trap_shop", "build_workshop", dict(self.site_args(sites[0]), type=TRAP_SHOP), retry=1,
                         limit=10 ** 6)
            if r and r.get("ok"):
                self.sites.remove(sites[0])
    if how is None:
        pick = self.trap_stair()
        if pick is not None:
            how = "stair"
            sid, zb = pick
            r = self.act("trap_stair_" + str(sid), "dig_stairs", {"site": sid, "z_bottom": zb}, retry=1,
                         limit=10 ** 6)
    self.trap_last = self.now
    self.trap_pokes += 1
    log("trap_poke", day=self.day, how=how, ok=bool(r and r.get("ok")),
        err=(r or {}).get("error_code") if r and not r.get("ok") else None, pokes=self.trap_pokes,
        drink=drink, logs=self.logs())
def trap_stair(self):
    num = lambda v: isinstance(v, int) and not isinstance(v, bool)
    surf = self.surface
    query = getattr(self.game, "query", None)
    if not num(surf) or query is None:
        return None
    cits = [(c["x"], c["y"], c["z"]) for c in self.citizen_spots()
            if all(num(c.get(k)) for k in ("x", "y", "z")) and c["z"] < surf]
    if not cits:
        return None
    zlow = max(min(c[2] for c in cits), surf - 4)
    cx = sorted(c[0] for c in cits)[len(cits) // 2]
    cy = sorted(c[1] for c in cits)[len(cits) // 2]
    try:
        res = query_result(query("map", x=min(400, max(0, cx)), y=min(400, max(0, cy)), z=surf, z2=zlow,
                                 radius=14))
    except Exception as e:
        log("trap_map_error", day=self.day, error=repr(e)[:160])
        return None
    if res is None:
        return None
    shape, water, _ = map_tiles([res])
    under = {p: ch for p, ch in shape.items() if p[2] < surf}
    part = set()
    for c in cits:
        if c not in part:
            tiles, _ = walk_region(under, water, c)
            part |= tiles
    if not part:
        return None
    best = None
    for s in sorted(self.kind("S"), key=lambda s: site_key(s.get("id"))):
        if not s.get("free", True) or not all(num(s.get(k)) for k in ("x", "y")):
            continue
        if not self.water_ok(s):
            continue
        x, y = s["x"], s["y"]
        if shape.get((x, y, surf)) not in STRANDED_FLOOR:
            continue
        for zb in range(surf - 1, zlow - 1, -1):
            if shape.get((x, y, zb)) != "#":
                break
            if any((x + dx, y + dy, zb) in part for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                n = self.probe_count("trap_" + str(s.get("id")), (x, y, 1, 1, surf), TRAP_WATER_MARGIN, zb,
                                     surf)
                if n == 0 and not any(z in self.wet_z for z in range(zb, surf)):
                    cand = (surf - zb, site_key(s.get("id")), s.get("id"), zb)
                    best = cand if best is None or cand < best else best
                break
    return (best[2], best[3]) if best else None
def pocket_box(self, box):
    num = lambda v: isinstance(v, int) and not isinstance(v, bool)
    if not all(num(d(box).get(k)) for k in ("x", "y", "z")):
        return False
    bx, by, bz = box["x"], box["y"], box["z"]
    bw = box.get("w") if num(box.get("w")) else 1
    bh = box.get("h") if num(box.get("h")) else 1
    key = (bx, by, bz, bw, bh)
    memo = self.pocket_memo.get(key)
    if memo is not None and memo[0] == self.day:
        return memo[1]
    out = False
    surf = self.surface
    query = getattr(self.game, "query", None)
    ents = [(e["x"], e["y"]) for e in self.kind("E") if num(e.get("x")) and num(e.get("y"))]
    if num(surf) and query is not None and len(ents) >= 2 and bz < surf:
        xs = [x for x, _ in ents] + [bx, bx + bw - 1]
        ys = [y for _, y in ents] + [by, by + bh - 1]
        cx, cy = (min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2
        radius = max(max(xs) - min(xs), max(ys) - min(ys)) // 2 + 3
        z2 = max(0, surf - POCKET_LEVELS)
        res = None
        reads = self.pocket_reads[1] if self.pocket_reads[0] == self.day else 0
        if radius <= 20 and bz >= z2 and reads < POCKET_READS_PER_DAY:
            self.pocket_reads = (self.day, reads + 1)
            try:
                res = query_result(query("map", x=min(400, max(0, cx)), y=min(400, max(0, cy)), z=surf, z2=z2,
                                         radius=radius))
            except Exception as e:
                log("pocket_map_error", day=self.day, error=repr(e)[:160])
        if res is not None:
            shape, water, _ = map_tiles([res])
            under = {p: ("#" if p[2] >= surf else ch) for p, ch in shape.items()}
            parts, ok = [], True
            for x in range(bx, bx + bw):
                for y in range(by, by + bh):
                    p = (x, y, bz)
                    if under.get(p) not in STRANDED_FLOOR or any(p in q for q in parts):
                        continue
                    tiles, opened = walk_region(under, water, p)
                    edge = any((t[0] + dx, t[1] + dy, t[2]) not in under for t in tiles
                               for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                    if opened or edge or not tiles:
                        ok = False
                        break
                    parts.append(tiles)
                if not ok:
                    break
            if ok and parts:
                stairs = [(x, y, surf - 1) for x, y in ents]
                pocket = []
                for q in parts:
                    mine = [t for t in stairs if t in q]
                    if len(mine) != 1:
                        pocket.append(False)
                        continue
                    rest, best = [t for t in stairs if t not in q and under.get(t) in STRANDED_FLOOR], 0
                    while rest:
                        tiles, opened = walk_region(under, water, rest[0])
                        best = max(best, sum(1 for t in rest if t in tiles))
                        rest = [t for t in rest[1:] if t not in tiles]
                    pocket.append(best >= 2)
                out = all(pocket)
    self.pocket_memo[key] = (self.day, out)
    return out
def lock_skip(self, ents, at):
    if self.safe_held:
        return "safe_state"
    if self.squad_out():
        return "squad_out"
    open_ = [sid for sid, p in ents
             if not (p in at and d(at[p]).get("built", True)) and not self.gate_closed(sid)]
    if open_:
        return "open:" + ",".join(str(s) for s in open_[:6])
    return None
def mark_guard(self):
    self.mark_arrivals()
    self.gate_waiting = False
    near = self.marked_units(WILD_NEAR_TILES, WILD_NEAR_Z)
    near_all = list(near)
    bur = d(self.o.get("burrows"))
    alert = bur.get("civilian_alert")
    sounded = self.big_alert(bur, alert)
    watched = set(self.wild_watched())
    if near and all(u["_mark"] in watched for u in near):
        if not (self.wild_evidenced(sorted({u["_mark"] for u in near})) or self.wild_approaching(near)):
            near = []
    pre = [] if near else self.mark_preempt(watched)
    sound = near or pre
    if sound and not alert and not sounded and self.wild_alert_since is None and not self.wild_resting() \
            and not self.alert_barred() \
            and (self.wild_budget_left() or self.budget_fight(sorted({u["_mark"] for u in sound}))) \
            and self.shelter_listed(bur) \
            and not self.shelter_wet("mark_alert") and not self.stranded_only(sound, pre=bool(pre)):
        r = self.act("mark_alert", "civilian_alert", {"on": True}, retry=1, limit=99)
        if r and r.get("ok"):
            self.wild_alert_on()
            for u in sound:
                self.wild_watch[u["_mark"]] = self.now
            log("mark_alert", day=self.day, animals=sorted({u["_mark"] for u in sound}), near=len(sound),
                **({"pre": True} if pre else {}))
    alert = alert or bool(d(self.o.get("burrows")).get("civilian_alert"))
    squad = d(next(iter(lst(d(self.o.get("military")).get("squads"))), None))
    weak = [u for u in near if u["_mark"] in DANGER_WEAK and not u.get("hostile")]
    weak_all = [u for u in near_all if u["_mark"] in DANGER_WEAK and not u.get("hostile")]
    members = lst(squad.get("members"))
    armed = squad.get("armed") or 0
    uniform = squad.get("uniform") not in (None, "none")
    ready = bool(squad) and len(members) >= MARK_SQUAD_MIN and armed >= len(members) and uniform
    rescue = bool(squad) and armed >= MARK_RESCUE_ARMED and uniform \
        and (len(members) >= MARK_SQUAD_MIN or (SURFACE_GUARD and armed >= len(members))) \
        and (not SQUAD_PREARM or armed >= len(members))
    hostile_now = d(self.o.get("threats")).get("visible_hostiles")
    squad_ids = {d(m).get("id") for m in members}
    far_off = set(self.stranded) if self.stranded and not (squad_ids & self.stranded) else set()
    threats = self.mark_threats(weak_all, skip=squad_ids | far_off) if rescue and not hostile_now else []
    if threats:
        u, c = min(threats, key=lambda uc: max(abs(uc[0]["x"] - uc[1]["x"]), abs(uc[0]["y"] - uc[1]["y"])))
        r = self.act("mark_rescue", "squad_order", {"order": "station", "x": c["x"], "y": c["y"], "z": c["z"]},
                     retry=0.25, limit=10 ** 6)
        if r and r.get("ok"):
            self.mark_station = self.now
            self.mark_kind = "mark_rescue"
            self.gate_post = False
            log("mark_rescue", day=self.day, species=u["_mark"], unit=u.get("id"), citizen=c.get("id"),
                name=str(c.get("name") or "")[:40], x=c["x"], y=c["y"], z=c["z"])
        self.mark_hold = self.now
        return
    gates = self.open_entrances()
    if gates and [u for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z) if u["_mark"] in DANGER_WEAK]:
        self.gate_mark_seen = self.now
    if self.mark_station is not None and self.mark_kind in ("mark_gate", "mark_station") and not hostile_now \
            and self.mark_clear_wait(squad, armed, standing=True, gate=self.mark_kind == "mark_gate"):
        return
    armable = len(self.armable_ids(squad)) if squad else 0
    gate_ready = bool(squad) and len(members) >= MARK_SQUAD_MIN and max(armed, armable) >= MARK_RESCUE_ARMED \
        and uniform
    weak_range = [u for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z)
                  if u["_mark"] in DANGER_WEAK and not u.get("hostile")] if gates else []
    if gates and weak_range and not weak_all:
        weak_all = sorted(weak_range, key=lambda u: min(max(abs(u["x"] - g[0]), abs(u["y"] - g[1]))
                                                         for g in gates))
    after_lift = isinstance(self.day, (int, float)) and self.alert_seen_day is not None \
        and self.day - self.alert_seen_day <= WILD_REST_DAYS
    if not (weak_all and gates and gate_ready and not hostile_now and (alert or sounded or after_lift)):
        self.shaft_since = None
        self.shaft_rest = False
        if not (self.mark_station is not None and self.mark_kind == "mark_gate"):
            self.mark_wait_since = None
    elif not self.shaft_guard_due(weak_all, gates):
        self.shaft_rest = True
        if self.mark_station is not None and self.gate_post:
            r = self.act("shaft_stand_down", "squad_order", {"order": "stand_down"}, retry=0.25, limit=10 ** 6)
            if r and r.get("ok"):
                self.mark_station = None
                self.gate_post = False
                log("shaft_guard_rest", day=self.day, species=weak_all[0]["_mark"],
                    since=round((self.now - self.shaft_since) / DAY, 1))
        return
    else:
        self.shaft_rest = False
    if weak_all and gates and gate_ready and not hostile_now and (alert or sounded or after_lift):
        if self.mark_clear_wait(squad, armed, gate=True):
            return
        wx, wy = weak_all[0]["x"], weak_all[0]["y"]
        gx, gy, gz = min(gates, key=lambda p: max(abs(p[0] - wx), abs(p[1] - wy)))
        first, other = (gz, gz - 1) if SHAFT_GUARD_TOP else (gz - 1, gz)
        z = other if self.gate_top else first
        if self.mark_station is not None and self.mark_kind == "mark_gate" and self.station_held(squad, gx, gy, z):
            self.gate_post = True
            self.mark_hold = self.now
            return
        r = self.act("mark_gate", "squad_order", {"order": "station", "x": gx, "y": gy, "z": z}, retry=1, limit=99)
        if r and r.get("ok"):
            self.mark_station = self.now
            self.mark_kind = "mark_gate"
            self.gate_post = True
            self.mark_hold = self.now
            log("mark_gate", day=self.day, species=weak_all[0]["_mark"], x=gx, y=gy, z=z)
        elif r is not None:
            self.gate_top = not self.gate_top
        return
    pressing = bool(weak) and (self.wild_evidenced(sorted({u["_mark"] for u in weak}))
                               or self.wild_approaching(weak))
    if pressing:
        self.mark_hold = self.now
        for u in weak:
            self.mark_settled.pop(u["_mark"], None)
    held = self.mark_hold is not None and self.now - self.mark_hold <= MARK_HOLD_DAYS * DAY
    fresh = [u for u in weak if pressing or self.now - self.mark_settled.get(u["_mark"], -10 ** 12)
             > WILD_MEMORY_DAYS * DAY]
    keep_gate = self.mark_station is not None and self.mark_kind == "mark_gate" and self.gate_post \
        and bool(gates) and not hostile_now and self.gate_mark_seen is not None \
        and self.now - self.gate_mark_seen <= GATE_GONE_DAYS * DAY
    if keep_gate:
        if self.may("gate_keep_log", 1, 10 ** 6):
            self.last["gate_keep_log"] = self.now
            log("gate_keep", day=self.day, seen=round((self.now - self.gate_mark_seen) / DAY, 1), alert=bool(alert))
        return
    if fresh and ready and not hostile_now and (pressing or held or self.mark_station is None) \
            and not self.mark_clear_wait(squad, armed):
        wag = d(d(self.o.get("map")).get("wagon"))
        wx, wy = wag.get("x", fresh[0]["x"]), wag.get("y", fresh[0]["y"])
        u = min(fresh, key=lambda v: max(abs(v["x"] - wx), abs(v["y"] - wy)))
        r = self.act("mark_station", "squad_order", {"order": "station", "x": u["x"], "y": u["y"], "z": u["z"]},
                     retry=1, limit=99)
        if r and r.get("ok"):
            if self.mark_station is None:
                self.mark_hold = self.now
            self.mark_station = self.now
            self.mark_kind = "mark_station"
            self.gate_post = False
            log("mark_station", day=self.day, species=u["_mark"], unit=u.get("id"), x=u["x"], y=u["y"], z=u["z"])
        return
    near_weak = [v for v in self.marked_units(MARK_RANGE, MARK_RANGE_Z) if v["_mark"] in DANGER_WEAK]
    if self.mark_station is not None and not hostile_now and (not near_weak or not held):
        r = self.act("mark_stand_down", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
        if r and r.get("ok"):
            self.mark_station = None
            self.gate_post = False
            for v in near_weak:
                self.mark_settled[v["_mark"]] = self.now
            log("mark_stand_down", day=self.day, settled=sorted({v["_mark"] for v in near_weak}))
def mark_arrivals(self):
    seen = getattr(self, "mark_last_seen", None)
    if seen is None:
        self.mark_last_seen, self.mark_arrived = {}, {}
        seen = self.mark_last_seen
    for n in sorted({u["_mark"] for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z)}):
        t = seen.get(n)
        if t is None or self.now - t > MARK_NEW_DAYS * DAY:
            self.mark_arrived[n] = self.now
        seen[n] = self.now
def stranded_only(self, units, pre=False):
    if not self.stranded or not units:
        return False
    if any(d(u).get("hostile") for u in units) or d(self.o.get("threats")).get("visible_hostiles"):
        return False
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    wag = d(d(self.o.get("map")).get("wagon"))
    cits = self.citizen_spots()
    reach = [c for c in cits if c.get("id") not in self.stranded]
    if all(num(wag.get(k)) for k in ("x", "y", "z")):
        reach.append({"id": "wagon", "x": wag["x"], "y": wag["y"], "z": wag["z"]})
    cut = [c for c in cits if c.get("id") in self.stranded]
    def nearest(u, group):
        ds = [max(abs(c["x"] - u["x"]), abs(c["y"] - u["y"])) for c in group if abs(c["z"] - u["z"]) <= WILD_NEAR_Z]
        return min(ds) if ds else None
    rows, near_cut = [], False
    for u in units:
        if not all(num(u.get(k)) for k in ("x", "y", "z")):
            return False
        dr, dc = nearest(u, reach), nearest(u, cut)
        if dr is not None and dr <= STRANDED_ALERT_TILES:
            return False
        near_cut = near_cut or (dc is not None and dc <= STRANDED_ALERT_TILES)
        rows.append({"unit": u.get("id"), "animal": u.get("_mark"), "at": (u["x"], u["y"], u["z"]),
                     "to_stranded": dc, "to_reachable": dr})
    if not near_cut:
        return False
    for u in units:
        self.strand_skipped[u.get("_mark")] = self.now
    if self.may("alert_skip_stranded_log", 1, 10 ** 6):
        self.last["alert_skip_stranded_log"] = self.now
        log("alert_skip_stranded", day=self.day, pre=pre, animals=sorted({r["animal"] for r in rows}),
            stranded=sorted(self.stranded, key=str), units=rows[:12])
    return True
def mark_preempt(self, watched=()):
    arrived = getattr(self, "mark_arrived", None) or {}
    surface = d(self.o.get("map")).get("surface_z", getattr(self, "surface", None))
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if not num(surface):
        return []
    out_c = [c for c in self.citizen_spots() if c["z"] >= surface]
    if not out_c:
        return []
    out = []
    for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z):
        n = u["_mark"]
        t = arrived.get(n)
        if t is not None and n in self.strand_skipped:
            t = max(t, self.strand_skipped[n])
        if n in watched or t is None or self.now - t > PREEMPT_WINDOW_DAYS * DAY:
            continue
        if any(max(abs(c["x"] - u["x"]), abs(c["y"] - u["y"])) <= PREEMPT_TILES
               and abs(c["z"] - u["z"]) <= WILD_NEAR_Z for c in out_c):
            out.append(u)
    return out
def citizen_spots(self, obs=None):
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    return [p for p in lst(d(self.o if obs is None else obs).get("dwarves"))
            if isinstance(p, dict) and all(num(p.get(k)) for k in ("x", "y", "z"))]
def stranded_home(self):
    num = lambda v: isinstance(v, int) and not isinstance(v, bool)
    home = []
    wag = d(d(self.o.get("map")).get("wagon"))
    if wag.get("present", True) and all(num(wag.get(k)) for k in ("x", "y", "z")):
        home.append((wag["x"], wag["y"], wag["z"]))
    for s_ in self.kind("E"):
        if all(num(s_.get(k)) for k in ("x", "y", "z")):
            home.append((s_["x"], s_["y"], s_["z"]))
    return home
def home_holding(self):
    hc = self.home_call
    if not hc:
        return False
    if self.now - hc["since"] > STRANDED_HOME_DAYS * DAY:
        log("home_call_end", day=self.day, why="days", ids=sorted(hc["ids"], key=str))
        self.home_call = None
        return False
    home = self.stranded_home()
    surface = self.surface
    out = []
    for c in self.citizen_spots():
        if c.get("id") in hc["ids"] and isinstance(surface, int) and c["z"] >= surface and home \
                and min(max(abs(c["x"] - h[0]), abs(c["y"] - h[1])) for h in home) > STRANDED_FAR_TILES:
            out.append(c["id"])
    if not out:
        log("home_call_end", day=self.day, why="home", ids=sorted(hc["ids"], key=str))
        self.home_call = None
        return False
    return True
def home_call_alert(self):
    if not self.home_holding():
        return
    bur = d(self.o.get("burrows"))
    if bur.get("civilian_alert") or self.alert_barred() \
            or not self.shelter_listed(bur) or self.shelter_wet("home_call"):
        return
    r = self.act("home_call", "civilian_alert", {"on": True}, retry=1, limit=10 ** 6)
    if r and r.get("ok"):
        self.alert_since = self.now
        if isinstance(self.o.get("burrows"), dict):
            self.o["burrows"]["civilian_alert"] = True
        log("home_call", day=self.day, ids=sorted(self.home_call["ids"], key=str))
def stranded_survey(self):
    surface = self.surface
    num = lambda v: isinstance(v, int) and not isinstance(v, bool)
    if not num(surface) or not isinstance(self.day, (int, float)):
        return
    home = self.stranded_home()
    cits = self.citizen_spots()
    by_id = {c.get("id"): c for c in cits}
    for i in sorted(self.stranded, key=str):
        c = by_id.get(i)
        if c is None or c["z"] < surface or (c["x"], c["y"], c["z"]) in self.stranded_fort \
                or (home and min(max(abs(c["x"] - h[0]), abs(c["y"] - h[1])) for h in home) <= STRANDED_FAR_TILES):
            self.stranded.discard(i)
            log("stranded_back", day=self.day, citizen=i, at=None if c is None else (c["x"], c["y"], c["z"]))
    if not home:
        return
    far = [c for c in cits if c["z"] >= surface
           and min(max(abs(c["x"] - h[0]), abs(c["y"] - h[1])) for h in home) > STRANDED_FAR_TILES]
    far = [c for c in far if (c["x"], c["y"], c["z"]) not in self.stranded_known or c.get("id") in self.stranded]
    if not far:
        return
    gap = STRANDED_JOIN_DAYS if any(c.get("id") in self.stranded for c in far) else STRANDED_SCAN_DAYS
    if self.stranded_day is not None and self.day - self.stranded_day < gap:
        return
    query = getattr(self.game, "query", None)
    size = d(self.o.get("map")).get("size_tiles")
    if query is None or not (isinstance(size, (list, tuple)) and len(size) >= 2 and num(size[0]) and num(size[1])):
        return
    self.stranded_day = self.day
    step = 2 * STRANDED_RADIUS + 1
    answers = []
    for cy in range(STRANDED_RADIUS, size[1] + STRANDED_RADIUS, step):
        for cx in range(STRANDED_RADIUS, size[0] + STRANDED_RADIUS, step):
            try:
                r = query("map", x=min(400, max(0, cx)), y=min(400, max(0, cy)), z=min(300, surface + 1),
                          z2=max(0, surface - 1), radius=STRANDED_RADIUS)
            except Exception as e:
                log("stranded_survey_error", day=self.day, error=repr(e)[:160])
                return
            res = query_result(r)
            if res is None:
                log("stranded_survey_error", day=self.day, error=query_error(r))
                return
            answers.append(res)
    shape, water, _ = map_tiles(answers)
    checked = {c["id"] for c in far}
    found = (self.stranded - checked) | stranded_of(shape, water, far, home, surface)
    fort_tiles = set()
    for p_ in home:
        if p_ not in fort_tiles:
            fort_tiles |= walk_region(shape, water, p_)[0]
    known = set(fort_tiles)
    for p_ in [(by_id[i]["x"], by_id[i]["y"], by_id[i]["z"]) for i in sorted(found, key=str) if i in by_id]:
        if p_ not in known:
            known |= walk_region(shape, water, p_)[0]
    self.stranded_fort = fort_tiles
    self.stranded_known = known
    joined = sorted((i for i in (self.stranded & checked) - found if i in by_id
                     and walk_region(shape, water, (by_id[i]["x"], by_id[i]["y"], by_id[i]["z"]))[0] & set(home)),
                    key=str)
    if joined:
        log("stranded_joined", day=self.day, citizens=joined,
            at={str(i): (by_id[i]["x"], by_id[i]["y"], by_id[i]["z"]) for i in joined if i in by_id})
        ids = set(joined) | set((self.home_call or {}).get("ids") or ())
        self.home_call = {"ids": ids, "since": self.now}
    if found != self.stranded:
        log("stranded", day=self.day, citizens=sorted(found, key=str), queries=len(answers),
            at={str(i): (by_id[i]["x"], by_id[i]["y"], by_id[i]["z"]) for i in sorted(found, key=str)
                if i in by_id})
    self.stranded = set(found)
def mark_threats(self, units, obs=None, skip=()):
    obs = d(self.o if obs is None else obs)
    surface = d(obs.get("map")).get("surface_z", getattr(self, "surface", None))
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    cits = [c for c in self.citizen_spots(obs) if c.get("id") not in skip]
    out = []
    for u in units:
        if not all(num(u.get(k)) for k in ("x", "y", "z")):
            continue
        close = [c for c in cits if max(abs(c["x"] - u["x"]), abs(c["y"] - u["y"])) <= WILD_CLOSE_TILES
                 and abs(c["z"] - u["z"]) <= WILD_NEAR_Z]
        if not close:
            continue
        outside = [c for c in close if num(surface) and c["z"] >= surface]
        pool = outside or (close if self.wild_evidenced([u.get("_mark") or ""]) else [])
        if pool:
            out.append((u, min(pool, key=lambda c: max(abs(c["x"] - u["x"]), abs(c["y"] - u["y"])))))
    return out
def mark_pressing(self):
    cits = self.citizen_spots()
    if not cits:
        return []
    out = set()
    for u in self.marked_units(WILD_NEAR_TILES, WILD_NEAR_Z):
        near_c = [c for c in cits if abs(c["z"] - u["z"]) <= WILD_NEAR_Z]
        dist = min((max(abs(c["x"] - u["x"]), abs(c["y"] - u["y"])) for c in near_c), default=None)
        if dist is None or dist > WILD_NEAR_TILES:
            continue
        if dist <= WILD_CLOSE_TILES or self.wild_evidenced([u["_mark"]]):
            out.add(u["_mark"])
    for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z):
        if any(max(abs(u["x"] - gx), abs(u["y"] - gy)) <= WILD_CLOSE_TILES and abs(u["z"] - gz) <= WILD_NEAR_Z
               for gx, gy, gz in self.open_entrances()):
            out.add(u["_mark"])
    return sorted(out)
def fight_pressing(self):
    if not FIGHT_HOLD_DAYS:
        return []
    fought = [set(n.split()) for n, t in self.wild_fight.items()
              if isinstance(t, (int, float)) and self.now - t <= FIGHT_HOLD_DAYS * DAY]
    if not fought:
        return []
    out = set()
    for u in self.marked_units(MARK_RANGE, MARK_RANGE_Z):
        w = set(u["_mark"].split())
        if any(w and f and (w <= f or f <= w) for f in fought):
            out.add(u["_mark"])
    return sorted(out)
def open_entrances(self):
    doors = d(getattr(self, "o", None)).get("doors")
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    at = set()
    if isinstance(doors, dict):
        at = {(x.get("x"), x.get("y"), x.get("z")) for x in map(d, lst(doors.get("list")))
              if x.get("kind") == "hatch"}
    out = []
    for s in self.kind("E"):
        p = (s.get("x"), s.get("y"), s.get("z"))
        if all(num(v) for v in p) and p not in at \
                and (s.get("building") or s.get("id") in self.entrance_occupied) \
                and not self.gate_closed(s.get("id")):
            out.append(p)
    return sorted(out)
def unhatchable(self):
    doors = d(getattr(self, "o", None)).get("doors")
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    at = set()
    if isinstance(doors, dict):
        at = {(x.get("x"), x.get("y"), x.get("z")) for x in map(d, lst(doors.get("list")))
              if x.get("kind") == "hatch"}
    out = []
    for s in self.kind("E"):
        p = (s.get("x"), s.get("y"), s.get("z"))
        if s.get("id") is not None and all(num(v) for v in p) and p not in at \
                and (s.get("building") or s.get("id") in self.entrance_occupied):
            out.append((s["id"], p))
    return sorted(out, key=lambda kv: str(kv[0]))
def gate_doors(self, sid):
    dl = [d(x) for x in lst(d(d(getattr(self, "o", None)).get("doors")).get("list"))]
    at = {(x.get("x"), x.get("y"), x.get("z")): x for x in dl if x.get("kind") == "door"}
    return {z: at.get(g["at"]) for z, g in self.gates.get(sid, {}).items()}
def gate_closed(self, sid):
    doors = self.gate_doors(sid)
    return bool(doors) and all(x is not None and x.get("built", True) for x in doors.values())
def gate_landings(self):
    out = set()
    for g in self.gates.values():
        for lv in g.values():
            out |= lv["landing"]
    return out
def gate_candidates(self, pos):
    x, y, zs = pos
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    return [s for s in self.kind("D") if s.get("id") is not None and all(num(s.get(k)) for k in ("x", "y", "z"))
            and zs - GATE_LEVELS <= s["z"] < zs and max(abs(s["x"] - x), abs(s["y"] - y)) <= GATE_RADIUS]
def gate_pending(self):
    out = []
    for sid, pos in self.unhatchable():
        ds = self.gate_candidates(pos)
        if ds and tuple(sorted(str(s["id"]) for s in ds)) != self.gate_seen.get(sid) \
                and not self.gate_closed(sid):
            out.append(pos)
    return out
@staticmethod
def gate_plan(levels, x1, y1, pos, ds):
    def shape(z, x, y):
        rows = levels.get(z)
        if not rows or y < y1 or y - y1 >= len(rows) or x < x1 or x - x1 >= len(rows[y - y1]):
            return "?"
        return rows[y - y1][x - x1]
    def flood(z, start, block):
        seen, todo = {start}, [start]
        while todo:
            cx, cy = todo.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    p = (cx + dx, cy + dy)
                    if p in seen or p == block or shape(z, *p) in GATE_SOLID:
                        continue
                    seen.add(p)
                    todo.append(p)
        return seen
    x, y, zs = pos
    shaft, z = [], zs - 1
    while shape(z, x, y) in ("X", "<"):
        shaft.append(z)
        if shape(z, x, y) == "<":
            break
        z -= 1
    if not shaft:
        return {}, "no_shaft"
    if shape(shaft[-1], x, y) == "X" and shaft[-1] - 1 not in levels:
        return {}, "shaft_deeper"
    plan = {}
    for z in shaft:
        full = flood(z, (x, y), None)
        best = None
        for s in ds:
            if s.get("z") != z or (s["x"], s["y"]) not in full:
                continue
            door = (s["x"], s["y"])
            land = flood(z, (x, y), door)
            rest = full - land - {door}
            if len(land) > GATE_LANDING_MAX or len(rest) <= len(land):
                continue
            if any(shape(z, *p) in GATE_DOWN for p in land if p != (x, y)):
                continue
            if best is None or len(land) < len(best[1]):
                best = (s, land)
        if best is None:
            return {}, "no_door_z%d" % z
        s, land = best
        plan[z] = {"site": s["id"], "at": (s["x"], s["y"], z), "landing": frozenset((a, b, z) for a, b in land)}
    return plan, "ok"
@staticmethod
def gate_doorways(levels, x1, y1, pos):
    walk = set(".<>X")
    x, y, zs = pos
    out = []
    for z in sorted(levels, reverse=True):
        rows = levels.get(z) or []
        if not isinstance(z, int) or not zs - GATE_LEVELS <= z < zs:
            continue
        def at(a, b):
            return rows[b - y1][a - x1] if 0 <= b - y1 < len(rows) and 0 <= a - x1 < len(rows[b - y1]) else "?"
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                a, b = x1 + i, y1 + j
                if ch != "." or max(abs(a - x), abs(b - y)) > GATE_RADIUS:
                    continue
                ns = at(a, b - 1) == "#" and at(a, b + 1) == "#" and at(a - 1, b) in walk and at(a + 1, b) in walk
                ew = at(a - 1, b) == "#" and at(a + 1, b) == "#" and at(a, b - 1) in walk and at(a, b + 1) in walk
                if ns or ew:
                    out.append({"id": "doorway", "kind": "doorway", "x": a, "y": b, "z": z})
    return out
def gate_survey(self):
    for sid, pos in self.unhatchable():
        if sid in self.gates:
            continue
        ds = self.gate_candidates(pos)
        key = tuple(sorted(str(s["id"]) for s in ds))
        if key == self.gate_seen.get(sid):
            continue
        if self.gate_probe_day == self.day:
            return
        self.gate_probe_day = self.day
        x, y, zs = pos
        try:
            r = self.game.query("map", x=min(400, max(0, x)), y=min(400, max(0, y)), z=min(300, max(0, zs - 1)),
                                z2=max(0, zs - GATE_LEVELS), radius=GATE_QUERY_RADIUS)
        except Exception as e:
            log("gate_probe_error", day=self.day, site=sid, error=repr(e)[:160])
            return
        res = d(query_result(r))
        if not lst(res.get("levels")):
            log("gate_probe_error", day=self.day, site=sid, error=query_error(r) if query_result(r) is None
                else "no levels")
            return
        levels = {d(lv).get("z"): lst(d(lv).get("shape")) for lv in lst(res.get("levels"))}
        plan, why = self.gate_plan(levels, res.get("x1") or 0, res.get("y1") or 0, pos, ds)
        self.gate_seen[sid] = key
        if not plan:
            spots = self.gate_doorways(levels, res.get("x1") or 0, res.get("y1") or 0, pos)
            alt, alt_why = self.gate_plan(levels, res.get("x1") or 0, res.get("y1") or 0, pos, spots)
            log("gate_none", day=self.day, site=sid, at=pos, reason=why, d_sites=list(key),
                doorways=[[p["x"], p["y"], p["z"]] for p in spots][:12],
                unlisted_gate=({z: list(g["at"]) for z, g in alt.items()} if alt else alt_why))
            continue
        self.gates[sid] = plan
        log("gate_plan", day=self.day, site=sid, at=pos,
            doors={z: [g["site"], list(g["at"])] for z, g in plan.items()},
            landing={z: len(g["landing"]) for z, g in plan.items()})
        for aid, (bx1, by1, bx2, by2, bz) in sorted(self.shelter_boxes.items(), key=lambda kv: str(kv[0])):
            if any(bz == c and bx1 <= a <= bx2 and by1 <= b <= by2 for a, b, c in self.gate_landings()):
                log("gate_landing_sheltered", day=self.day, site=sid, box=aid)
def gate_build(self, doors, alert):
    if alert or self.breach:
        return
    free = doors.get("door_items_free") or 0
    for sid in sorted(self.gates, key=str):
        for z, door in sorted(self.gate_doors(sid).items(), reverse=True):
            if door is not None or sid not in self.gates:
                continue
            g = self.gates[sid][z]
            if free <= 0:
                if not self.pending("make_door") and self.gate_door_ordered < 2 * ENTRANCE_MAX:
                    r = self.act("gate_door_order", "add_order", {"recipe": "make_door", "amount": 1},
                                 retry=7, limit=8)
                    if r and r.get("ok"):
                        self.gate_door_ordered += 1
                return
            r = self.act("gate_door_" + str(g["site"]), "build_door", {"kind": "door", "site": g["site"]},
                         retry=1, limit=4)
            if r and r.get("ok"):
                free -= 1
                log("gate_door", day=self.day, entrance=sid, site=g["site"], at=list(g["at"]))
            elif r and r.get("error_code") in ("site_used", "unknown_site", "wrong_tile_shape", "tile_occupied"):
                log("gate_drop", day=self.day, entrance=sid, site=g["site"], code=r.get("error_code"))
                del self.gates[sid]
                self.gate_seen.pop(sid, None)
def gate_locks(self):
    out = []
    for sid in sorted(self.gates, key=str):
        if self.gate_closed(sid):
            for z, door in self.gate_doors(sid).items():
                out.append((door, self.gates[sid][z]["landing"]))
    return out
def step(self, resp):
    self.count = 0
    try:
        self.load(resp)
    except (HandsOff, GameOver):
        raise
    except Exception as e:
        log("guard_load_error", error=repr(e)[:300])
        return 0
    try:
        self.plan()
    except (HandsOff, GameOver):
        raise
    except ActionLimit:
        log("guard_action_limit")
    except Exception as e:
        log("guard_error", error=repr(e)[:300])
    try:
        self.risk = self.danger_signs(resp, query=False)
    except Exception as e:
        log("risk_error", error=repr(e)[:200])
        self.risk = []
    return self.count
def pace(self, resp):
    if d(self.o.get("threats")).get("visible_hostiles") or self.o.get("moods") or self.risk:
        return 1
    if ((self.o.get("dig_designations_pending") or 0) > 0 and not self.flooded_pending()) \
            or (resp.get("day") or 0) < 14:
        return 1
    return 2
def run(self):
    self.game.task()
    while True:
        resp = self.game.observe()
        if resp.get("game_over"):
            return "game_over"
        for _ in range(MAX_PASSES):
            self.load(resp)
            self.count = 0
            try:
                self.plan()
            except (ActionLimit, HandsOff, GameOver):
                raise
            except Exception as e:
                log("plan_error", error=repr(e)[:300])
            if not self.count:
                break
            resp = self.game.observe()
        self.load(resp)
        self.risk = self.danger_signs(resp, query=False)
        r = self.game.act("advance_days", {"days": self.pace(resp)})
        log("advance", day=r.get("day"), stopped=d(r.get("result")).get("stopped"), cit=self.cit,
            drink=self.st.get("drink"), food=self.st.get("food_edible"))
        if d(d(r.get("result")).get("stopped")).get("reason") == "water_rising":
            self.water_rising_stop()
        if r.get("game_over") or d(r.get("result")).get("hands_off"):
            return "over"
