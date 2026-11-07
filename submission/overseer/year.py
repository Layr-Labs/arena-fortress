"""Full-year normal brewing on the exact promoted controller.
The cap extends our V73 experiment. The original endgame_supply is inherited unchanged.
"""
from .frontier import Overseer as FrontierOverseer

class YearOverseer(FrontierOverseer):
    def supply(self):
        if self.days >= 336 and not self.standing("brew_drink"):
            self.act("o_brew", "add_order", {"recipe": "brew_drink", "amount": 3, "repeat": "daily", "when": [
                {"stock": "drink", "below": max(600, 30 * self.cit)},
                {"stock": "plants_brewable", "at_least": 2},
                {"stock": "barrels_empty", "at_least": 1}]}, retry=3)
        # The shared o_brew daily gate prevents a second creation from the stale observation.
        super().supply()
