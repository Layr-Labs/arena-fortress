"""Operator-compatible closed-loop candidate; the original policy is in operator.py.

Safety mixin/beast rules: e-man07 submission 65e60732, source commit
ab1668c0575c85ae1971d528b88bdaeb14b94b53, imported via iter90 verbatim.
This wrapper adds observed office readiness, optional-work ownership and feedback,
bounded core-construction recovery, and safety-first scheduling. No model calls.
"""
from .operator import *
from .openplay import OpenPlayRules
from .layout import LayoutRules
from .safety_state import initialize


class Overseer(LayoutRules, OpenPlayRules, Overseer):
    def __init__(self, game, goal="", days=0, advisory_sensing=True):
        super().__init__(game, goal, days, advisory_sensing)
        initialize(self)
        self.stuck_since = {}
        self.replacements = {}
        self.used_workshop_sites = set()
        self.optional_orders = {}   # key -> confirmed owned id, or None after an ambiguous receipt
        self.pending_optional = {}
        self.invader_alert = False
        self.invader_locks = set()
        self.rank_start = None
        self.progress_state = {"state": "unobserved", "blockers": []}

    def set_task(self, info):
        self.lab = bool(d(info).get("hands_off"))

    def open_task(self):
        # Short lab stubs and missing task clocks never acquire wildlife policy.
        return self.days >= 200 and not self.lab and not self.surge and self.hands_off is None

    def open_play(self):
        return self.open_task() and type(self.days_left) is int

    @staticmethod
    def shop_key(w):
        return (w.get("id"), w.get("type"), w.get("x"), w.get("y"), w.get("z"))

    def load(self, resp):
        super().load(resp)
        if type(self.surface) is int:
            self.surface_seen = self.surface
        rows = self.o.get("workshops")
        seen = set()
        if isinstance(rows, list):
            for w in rows:
                w = d(w)
                if w.get("id") is not None and w.get("built") is False and any(
                        d(j).get("job") == "ConstructBuilding" and d(j).get("suspended") is True
                        for j in lst(w.get("job_details"))):
                    k = self.shop_key(w)
                    self.stuck_since.setdefault(k, self.now)
                    seen.add(k)
        # An incomplete observation breaks the continuous-suspension proof.
        self.stuck_since = {k: v for k, v in self.stuck_since.items() if k in seen}
        if isinstance(self.o.get("orders"), list):
            present = {x.get("id") for x in self.orders}
            for key, oid in list(self.optional_orders.items()):
                if oid is None:
                    pending = self.pending_optional.get(key, {})
                    new = [x for x in self.orders if x.get("id") not in pending.get("before", set())
                           and x.get("job") == pending.get("job")]
                    # A complete list proves absence, but cannot prove which new
                    # anonymous order was ours. Never adopt by job name alone.
                    if not new:
                        del self.optional_orders[key]
                        self.pending_optional.pop(key, None)
                elif oid not in present:
                    del self.optional_orders[key]
                    self.pending_optional.pop(key, None)
        rank = d(self.o.get("progression")).get("fortress_rank")
        if self.rank_start is None and type(rank) is int:
            self.rank_start = rank

    def office_ready(self):
        if not self.adm.get("manager_active_for_orders"):
            return False
        manager = self.adm.get("MANAGER_id")
        if type(manager) is not int:
            return False
        office = d(self.adm.get("manager_office"))
        if office.get("zone_id") is not None and office.get("chair") is True:
            return True  # this API field is specifically the manager's office
        return any(z.get("owner") == manager and bool(d(z.get("furniture")).get("chair"))
                   for z in self.zone("office"))

    def management(self):
        if not self.adm.get("manager_active_for_orders"):
            free = [p for p in self.people if not p.get("positions") and p.get("adult", True)]
            free.sort(key=lambda p: -(p.get("organizer_skill") or 0))
            self.act("manager", "appoint_manager", {"dwarf_id": free[0]["id"]} if free else {}, retry=1, limit=8)
        self.office()
        plugins = d(self.o.get("plugins"))
        for name in ("autochop", "seedwatch"):
            if plugins.get(name) == "on":
                continue
            if name == "autochop" and self.open_play() and self.felling_waits():
                continue
            self.act("plug_" + name, "enable_automation", {"name": name}, retry=5)
        if self.o.get("farm_plots") and plugins.get("autofarm") != "on":
            self.act("plug_autofarm", "enable_automation", {"name": "autofarm"}, retry=5)
        if self.office_ready():
            if self.open_play():
                self.no_fishing(plugins)
            if plugins.get("autolabor") != "on" and not self.calm:
                self.act("plug_autolabor", "enable_automation", {"name": "autolabor"}, retry=5)

    def build(self, wtype, retry=3):
        sites = [s for s in self.kind("W") if s.get("id") not in self.used_workshop_sites]
        if not sites or not self.material():
            return None
        r = self.act("ws_" + wtype, "build_workshop", {"type": wtype, "site": sites[0]["id"]}, retry=retry)
        if r and r.get("ok"):
            self.used_workshop_sites.add(sites[0]["id"])
            self.sites.remove(sites[0])
        return r

    def workshops(self):
        # Preserve the operator's core and migrant capacity policy. Suppress fishing
        # workshops only on long open games where no_fishing has selected its policy.
        if not isinstance(self.o.get("workshops"), list):
            return
        people = self.people
        if self.open_task() and self.calm is not False:
            self.people = [p for p in people if p.get("job") != "Fish"]
        try:
            super().workshops()
        finally:
            self.people = people
        if not isinstance(self.o.get("workshops"), list):
            return
        rows = [d(w) for w in self.o["workshops"]]
        # Absent core types get priority over replacement work.
        if not {"Carpenters", "Still", "Kitchen"} <= {w.get("type") for w in rows}:
            return
        for t in ("Carpenters", "Still", "Kitchen"):
            copies = [w for w in rows if w.get("type") == t]
            if copies and all(self.shop_key(w) in self.stuck_since and
                              self.now - self.stuck_since[self.shop_key(w)] >= 3 * DAY for w in copies):
                if self.replacements.get(t, 0) < 2:
                    r = self.build(t)
                    if r and r.get("ok"):
                        self.replacements[t] = self.replacements.get(t, 0) + 1

    def optional_blockers(self):
        blocked = []
        if not self.office_ready():
            blocked.append("manager_office")
        if (d(self.o.get("burrows")).get("civilian_alert") is not False or self.lock is not None
                or self.own_locks or self.invader_locks or self.invader_alert or self.thaw_alert or self.alert_pending):
            blocked.append("safety_hold_or_unknown")
        th = d(self.o.get("threats"))
        if type(th.get("visible_hostiles")) is not int or th["visible_hostiles"] > 0 or self.beast_seen:
            blocked.append("danger_or_unknown")
        for k, floor in (("drink", max(DRINK_FLOOR, 2 * self.cit)),
                         ("food_edible", max(MEAL_FLOOR, self.cit)), ("prepared_meals", MEAL_FLOOR),
                         ("logs_usable", LOG_RESERVE + 1)):
            v = self.st.get(k)
            if type(v) not in (int, float) or v < floor:
                blocked.append(k)
        if self.housing_short():
            blocked.append("housing")
        core = {d(w).get("type") for w in lst(self.o.get("workshops")) if d(w).get("built") is True}
        if not {"Carpenters", "Still", "Kitchen"} <= core:
            blocked.append("core_workshops")
        return blocked

    def cancel_optional(self, keys=None):
        # Never touch unowned manager orders, even when their jobs look identical.
        for key, oid in list(self.optional_orders.items()):
            if keys is not None and key not in keys:
                continue
            if oid is None:
                continue  # unknown identity: no safe cancellation target
            r = self.act("pause_" + key, "cancel_order", {"order_id": oid}, retry=1, limit=10 ** 9)
            if r and r.get("ok"):
                del self.optional_orders[key]
                self.pending_optional.pop(key, None)

    def optional_order(self, key, args):
        if key in self.optional_orders:
            oid = self.optional_orders[key]
            if oid is None:
                return "ownership_unresolved"
            row = next((x for x in self.orders if x.get("id") == oid), {})
            return "active" if row.get("active") is True or (row.get("jobs_in_progress") or 0) > 0 else "requested"
        if not isinstance(self.o.get("orders"), list):
            return "orders_unavailable"
        # Material is not fully observable (INORGANIC is absent in facts).
        # Same-job orders with unknown or different intent are blockers, not
        # successful progression, and are never adopted for cancellation.
        if any(x.get("job") == args["job"] and x.get("repeat") for x in self.orders):
            return "conflicting_or_unverifiable_order"
        if key in self.done or not self.may(key, retry=4, limit=6):
            return "rate_limited"
        self.pending_optional[key] = {"job": args["job"], "before": {x.get("id") for x in self.orders}}
        self.optional_orders[key] = None  # record before POST, including transport errors
        r = self.act(key, "add_manager_order", args, retry=4, limit=6)
        if not r or not r.get("ok"):
            self.optional_orders.pop(key, None)
            self.pending_optional.pop(key, None)
            return "refused"
        oid = d(r.get("result")).get("order_id")
        if type(oid) is int:
            self.optional_orders[key] = oid
            return "requested"
        return "ownership_unresolved"

    def progress(self):
        rank = d(self.o.get("progression")).get("fortress_rank")
        wealth = d(self.o.get("wealth")).get("created")
        state = {"state": "blocked", "blockers": [], "created": wealth,
                 "rank_start": self.rank_start, "rank_observed": rank,
                 "rank_coverage": "observed" if type(rank) is int else "unavailable"}
        if self.days < 336 or (self.day or 0) < PROGRESS_FROM_DAY:
            state["state"] = "not_due"
        elif self.rank_start is not None and type(rank) is int and rank > self.rank_start:
            state["state"] = "achieved"
        elif type(rank) is int and rank >= 1:
            state["state"] = "outside_hamlet_target"
        else:
            state["blockers"] = self.optional_blockers()
            if not state["blockers"]:
                if type(wealth) not in (int, float):
                    state["blockers"] = ["wealth_unknown"]
                elif wealth >= WEALTH_TARGET:
                    state["state"] = "awaiting_rank"
                elif not any(d(w).get("type") == "Craftsdwarfs" and d(w).get("built") is True
                             for w in lst(self.o.get("workshops"))):
                    state["blockers"] = ["craft_workshop"]
                    if not any(d(w).get("type") == "Craftsdwarfs" for w in lst(self.o.get("workshops"))):
                        self.build("Craftsdwarfs", retry=5)
                else:
                    status = self.optional_order("supervisor_crafts", {"job": "MakeCrafts", "amount": 3,
                        "repeat": "daily", "material_category": ["wood"],
                        "when": [{"item_type": "WOOD", "at_least": LOG_RESERVE + 1}]})
                    if status in {"active", "requested"}:
                        state["state"] = status
                    else:
                        state["blockers"] = [status]
        if state["state"] not in {"active", "requested"}:
            self.cancel_optional(None if self.optional_blockers() else {"supervisor_crafts"})
        self.progress_state = state
        log("supervisor_progression", day=self.day, **state)

    def stonework(self):
        # Keep stone-only material policy, but optional orders share the same safety gate.
        if self.optional_blockers():
            self.cancel_optional()
            return
        if (self.st.get("boulders_usable") or 0) < STONE_MIN:
            return
        have = {d(w).get("type") for w in lst(self.o.get("workshops")) if d(w).get("built") is True}
        if "Masons" not in have:
            self.build("Masons", retry=4)
            return
        self.optional_order("supervisor_statue", {"job": "ConstructStatue", "amount": 1,
            "repeat": "daily", "material": "INORGANIC",
            "when": [{"item_type": "BOULDER", "at_least": STONE_MIN}]})
        if "Craftsdwarfs" in have:
            self.optional_order("supervisor_stonecraft", {"job": "MakeCrafts", "amount": 2,
                "repeat": "daily", "material": "INORGANIC",
                "when": [{"item_type": "BOULDER", "at_least": STONE_MIN}]})

    def act(self, key, tool, args, retry=2, limit=6):
        starting = (key == "alert_on" and tool == "civilian_alert" and args.get("on") is True
                    and key not in self.done and self.may(key, retry, limit))
        prior = self.invader_alert
        if starting:
            self.invader_alert = True
        r = super().act(key, tool, args, retry, limit)
        if starting and (not r or not r.get("ok")):
            self.invader_alert = prior
        if key == "alert_off" and r and r.get("ok"):
            self.invader_alert = False
        return r

    def hatches(self, invaders, near, alert):
        doors = d(self.o.get("doors"))
        threat = bool(invaders) or (self.hostile_at is not None and self.now - self.hostile_at < 10 * DAY)
        free = doors.get("hatch_cover_items_free") or 0
        have = [d(x) for x in lst(doors.get("list")) if d(x).get("kind") == "hatch"]
        if threat and not free and len(have) < 2 and not self.pending("make_hatch_cover") and self.logs():
            self.act("o_hatch", "add_order", {"recipe": "make_hatch_cover", "amount": 2}, retry=5, limit=4)
        if invaders and near and free:
            for site in [x for x in self.kind("E") if x.get("free")][:min(free, 2)]:
                self.act("hatch_" + site["id"], "build_door", {"kind": "hatch", "site": site["id"]}, retry=3, limit=3)
        _, hatches = self.surface_hatches()
        if alert and invaders and near:
            for h in hatches:
                if h["id"] in self.own_locks:
                    continue  # wildlife already controls/reclosed this hatch
                if h.get("locked") is True and h["id"] not in self.invader_locks:
                    continue  # someone else's pre-existing lock
                key = "invader_lock_%s" % h["id"]
                if key not in self.done and self.may(key, 1, 10 ** 9):
                    self.invader_locks.add(h["id"])
                    self.act(key, "lock_door", {"locked": True, "door_id": h["id"]}, retry=1, limit=10 ** 9)
        elif not alert or not invaders:
            # Wildlife/thaw ownership is separate: do not release their locks.
            if self.lock is None and not self.thaw_alert:
                for i in sorted(self.invader_locks):
                    r = self.act("invader_unlock_%s" % i, "lock_door", {"locked": False, "door_id": i}, retry=0, limit=10 ** 9)
                    if r and r.get("ok"):
                        self.own_locks.discard(i)
                        self.invader_locks.discard(i)
        self.locked = bool(self.invader_locks)

    def release(self):
        self.alert_pending = self.alert_pending or self.invader_alert
        self.own_locks.update(self.invader_locks)
        OpenPlayRules.release(self)
        if not self.alert_pending:
            self.invader_alert = False
        self.invader_locks.intersection_update(self.own_locks)
        self.locked = bool(self.invader_locks)

    def pace(self, resp):
        return min(super().pace(resp), self.step_days())

    def defend(self):
        if not (self.open_play() or self.lock is not None or self.own_locks or self.thaw_alert):
            return super().defend()
        th, mil, bur = d(self.o.get("threats")), d(self.o.get("military")), d(self.o.get("burrows"))
        alert = self.wildlife(bur.get("civilian_alert"), self.open_play())
        alert = self.thaw(alert, bur)
        squads = lst(mil.get("squads"))
        squad = d(squads[0]) if squads else None
        if not squad and self.cit >= 14:
            self.act("squad", "create_squad", {"size": 4}, retry=5, limit=3)
        if squad and squad.get("uniform") == "none":
            self.act("equip", "equip_squad", {"uniform": "leather"}, retry=5, limit=3)
        shelter = self.room_for("dorm")
        if shelter and not any(d(b).get("civ_alert_burrow") for b in lst(bur.get("list"))):
            self.act("burrow", "create_burrow", {"site": shelter["id"]}, retry=5, limit=3)
        self.grow_shelter(bur)
        self.place_hatches()
        invaders = [h for h in lst(th.get("hostiles")) if d(h).get("invader")]
        hostile, orders = th.get("visible_hostiles") or 0, lst((squad or {}).get("orders"))
        holding = self.lock is not None and self.lock["phase"] == "hold"
        ours = self.lock is not None or self.thaw_alert or self.alert_pending
        if hostile and squad and (squad.get("armed") or 0) >= 1 and not orders and not holding:
            self.act("attack", "squad_order", {"order": "attack"}, retry=1, limit=99)
        if (not hostile or holding) and orders:
            self.act("stand_down", "squad_order", {"order": "stand_down"}, retry=1, limit=99)
        if alert and not ours and self.alert_since is None:
            self.alert_since = self.now
        elif alert is False:
            self.alert_since = None
        near = th.get("nearest_hostile_dist_to_wagon")
        near = type(near) in (int, float) and near <= 45
        owed = self.lock is not None or self.now < self.rest_until
        if invaders and near and not alert and not owed and any(d(b).get("civ_alert_burrow") for b in lst(bur.get("list"))):
            r = self.act("alert_on", "civilian_alert", {"on": True}, retry=20, limit=99)
            if r and r.get("ok"):
                self.alert_since = self.now
                alert = True
        self.hatches(invaders, near, alert)
        too_long = self.alert_since is not None and self.now - self.alert_since > 10 * DAY
        if alert and not ours and (not invaders or too_long):
            r = self.act("alert_off", "civilian_alert", {"on": False}, retry=1, limit=99)
            if r and r.get("ok"):
                self.alert_since = None

    def plan(self):
        self.defend()  # safety owns the first action budget, before moods or economy
        try:
            self.events()
            if self.advisory_sensing:
                self.sweep()
        except (ActionLimit, HandsOff, GameOver):
            raise
        except Exception as e:
            log("sense_error", error=repr(e)[:200])
        for step in (self.mood, self.management, self.workshops, self.digging, self.farms,
                     self.supply, self.cubicles, self.furnish, self.rezone, self.progress,
                     self.stonework, self.closer):
            step()
        log("supervisor_status", day=self.day, **self.supervisor_status())

    def step_days(self):
        if (d(self.o.get("threats")).get("visible_hostiles") or self.lock is not None or self.own_locks
                or self.beast_seen or self.thaw_alert or self.thaw_window(lead=2)):
            return 1
        return 2

    def supervisor_status(self):
        return {"office_ready": self.office_ready(), "progression": dict(self.progress_state),
                "safety": {**OpenPlayRules.status(self), "invader_alert_owned": self.invader_alert,
                           "invader_locks_owned": sorted(self.invader_locks)}, "replacements": dict(self.replacements),
                "owned_optional_orders": dict(self.optional_orders)}


def main():
    """Standalone entry point uses this supervisor, not operator.main globals."""
    task = load_task()
    game = GameClient(task.game_url)
    info = {**(task.task or {}), **d(game.task().get("task"))}
    ov = Overseer(game, goal=info.get("goal", ""), days=info.get("days") or task.days)
    ov.set_task(info)
    try:
        while True:
            try:
                log("done", reason=ov.run())
                return 0
            except ActionLimit:
                game.act("advance_days", {"days": 1})
            except (HandsOff, GameOver):
                return 0
            except GameAPIError as e:
                log("game_error", error=str(e)[:300])
                return 1
    finally:
        ov.release()
