"""Year reserve and required-office repair with short public-combat retreats.
Late-food timing/threshold adapts e-man07's published 1e6cbe5e rule through our V76
experiment; it reuses the existing butcher helper after the original endgame.
"""
import re
from .frontier import Overseer as FrontierOverseer, DAY, d, lst
from .harness import Overseer as ManagedOverseer, covers

class YearOverseer(FrontierOverseer):
    def supply(self):
        if self.days >= 336 and not self.standing("brew_drink"):
            self.act("o_brew", "add_order", {"recipe": "brew_drink", "amount": 3, "repeat": "daily", "when": [
                {"stock": "drink", "below": max(600, 30 * self.cit)},
                {"stock": "plants_brewable", "at_least": 2},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=3)
        # The shared o_brew daily gate prevents a second creation from the stale observation.
        super().supply()

    def office(self):
        # Year-only repair when DF actually requires an office and a built chair is known.
        mo = self.adm.get("manager_office")
        if (self.days >= 336 and self.cit >= 20 and self.adm.get("manager_active_for_orders")
                and self.adm.get("manager_required_office")
                and not (isinstance(mo, dict) and mo.get("chair"))):
            known = any(
                f.get("kind") == "chair" and f.get("built") is True
                and all(type(site.get(k)) is int for k in ("x", "y", "z", "w", "h"))
                and min(20, site["w"]) * min(20, site["h"]) >= 6
                and covers({**site, "w": min(20, site["w"]), "h": min(20, site["h"])}, f)
                for site in self.kind("A") + self.dug_rooms()
                for f in self.o.get("furniture", []) if isinstance(f, dict))
            if known:
                ManagedOverseer.managed_office(self, self.zone("office"), self.adm.get("MANAGER_id"))
                return
        super().office()

    def defend(self):
        # A short retreat responds to public combat reports even when danger count is zero.
        if self.days < 336:
            return super().defend()
        bur = d(self.o.get("burrows"))
        alert = bool(bur.get("civilian_alert"))
        until = getattr(self, "combat_retreat_until", None)
        if until is not None:
            if any(d(h).get("invader") for h in lst(d(self.o.get("threats")).get("hostiles"))):
                # Keep the current alert; the original policy owns an observed invasion.
                self.combat_retreat_until = None
                self.combat_retreat_cooldown = self.now + 8 * DAY
                return super().defend()
            if (self.now >= until or not alert or (self.st.get("drink") or 0) < 20
                    or (self.st.get("food_edible") or 0) < 10):
                if alert:
                    self.act("combat_retreat_off", "civilian_alert", {"on": False}, retry=1, limit=99)
                self.combat_retreat_until = None
                self.combat_retreat_cooldown = self.now + 8 * DAY
            else:
                return
        super().defend()
        events = tuple(str(x) for x in lst(self.o.get("recent_events")))
        fighting = any(re.search(r"\b(bites|strikes|gores|latches on|attack)\b", x, re.I) for x in events)
        old = getattr(self, "combat_retreat_events", None)
        self.combat_retreat_events = events
        if (not fighting or events == old or alert
                or self.now < getattr(self, "combat_retreat_cooldown", -1)
                or (self.st.get("drink") or 0) < 40 or (self.st.get("food_edible") or 0) < 20
                or any(d(h).get("invader") for h in lst(d(self.o.get("threats")).get("hostiles")))):
            return
        available = any(d(b).get("civ_alert_burrow") for b in lst(bur.get("list")))
        if not available:
            surface = d(self.o.get("map")).get("surface_z")
            rooms = [r for r in self.dug_rooms() if type(surface) is int
                     and type(r.get("z")) is int and r["z"] < surface]
            if rooms:
                result = self.act("combat_shelter", "create_burrow", {"site": rooms[0]["id"]}, retry=5, limit=3)
                available = bool(result and result.get("ok"))
        if available:
            result = self.act("combat_retreat_on", "civilian_alert", {"on": True}, retry=10, limit=99)
            if result and result.get("ok"):
                self.combat_retreat_until = self.now + 2 * DAY

    def endgame_supply(self):
        super().endgame_supply()
        if (self.days >= 336 and 2 <= self.days_left <= 14
                and (self.st.get("food_edible") or 0) < 40 * self.cit):
            self.butcher()  # Same existing five-day slaughter gate; never two marks in one pass.
