"""Full-year normal brewing on the exact promoted controller.
The cap extends our V73 experiment. The original endgame_supply is inherited unchanged.
"""
from .frontier import Overseer as FrontierOverseer
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
