"""The integration regression: on a healthy fort whose shape arms none of the integrated measures, the FULL layer's
plan() call sequence is identical to the leader's (fa9c13cc), tool for tool and arg for arg.

The fixture is chosen so every gated measure is off and the integrated changes stay numerically quiet, except the
one deliberate delta (the adaptive brew cap):
- days=60: the OP1 supply guards and the full-year growth chase (days >= 336) and food security / the adaptive
  closer (days >= 180) never fire;
- goal="" and no hands-off window: the LT08 surge cluster never arms (surge needs migrant text AND a window);
- no dig sites and no water keys: the W4water rules have nothing to probe or halt;
- no caravan glut (plants_brewable absent, no jump). At citizens=50 the adaptive brew cap max(200, 20 * cit)
  lands on 1000 and the gap-proportional amount (drink 200, a 800 gap) on 10 — the brew standing's amount and
  drink cap are this tree's intended divergence from the leader's DRINK_CAP=300 / amount 3 (the adaptive-cap fix,
  devtest hard LT08-0); every other arg stays the leader's.

The expected sequence was produced this turn by running the leader harness itself (git HEAD,
full-wt @ b98e4e2 = fa9c13cc verbatim) on the same fixture. No game or network.
"""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

DAY = 1200


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": len(self.calls)}, "day": 30}

    def query(self, *a, **kw):
        return {"result": {}}


def facts():
    return {"day": 30, "tick": 30 * DAY, "observation": {
        "date": {"abs_tick": 30 * DAY},
        "administrators": {"citizens": 50, "manager_active_for_orders": True, "MANAGER_id": 1,
                           "manager_office": {"chair": True}},
        "dwarves": [{"id": 87 + i, "job": "idle"} for i in range(6)],
        "stocks": {"drink": 200, "food_edible": 400, "beds": 60, "tables": 30, "chairs": 30,
                   "logs_usable": 40, "barrels_empty": 5},
        "map": {"sites": []}, "zones": [], "furniture": [],
        "workshops": [{"type": t, "built": True} for t in ("Carpenters", "Still", "Kitchen")],
        "orders": [], "plugins": {"autochop": "on", "seedwatch": "on", "autofarm": "on"},
        "farm_plots": [], "dig_designations_pending": 0}}


LEADER_SEQUENCE = [
    ("create_squad", {"size": 4}),
    ("add_order", {"recipe": "brew_drink", "amount": 3, "repeat": "daily", "when": [
        {"stock": "drink", "below": 300}, {"stock": "plants_brewable", "at_least": 2},
        {"stock": "barrels_empty", "at_least": 1}]}),
    ("add_order", {"recipe": "make_barrel", "amount": 2, "repeat": "daily", "when": [
        {"stock": "barrels_empty", "below": 4}, {"stock": "logs", "at_least": 2}]}),
    ("add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily", "when": [
        {"stock": "prepared_meals", "below": 200}, {"stock": "plants_total", "at_least": 10}]}),
]

# What this layer answers on the same fixture: the leader's sequence with the brew standing's amount and drink cap
# swapped for the adaptive ones (the adaptive-cap fix, devtest hard LT08-0 / ROOT_CAUSES §H/§C) — the tools, their
# order and every other arg stay the leader's.
# cx squad pick (owner 2026-11-10): the squad by dwarf_ids (squad_pick) instead of size 4 — the fixture's four
# start dwarves (no profession, no tool labor) are the four picked
EXPECTED_SEQUENCE = [("create_squad", {"dwarf_ids": [87, 88, 89, 90]}),
                     ("add_order", {"recipe": "brew_drink", "amount": 10, "repeat": "daily", "when": [
                         {"stock": "drink", "below": 1000}, {"stock": "plants_brewable", "at_least": 2},
                         {"stock": "barrels_empty", "at_least": 1}]}),
                     *LEADER_SEQUENCE[2:]]


class LeaderRegression(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def test_healthy_fort_reproduces_the_leader_call_sequence(self):
        game = FakeGame()
        ov = harness.Overseer(game, goal="", days=60)
        ov.load(facts())
        ov.count = 0
        ov.plan()
        self.assertEqual(game.calls, EXPECTED_SEQUENCE)
        # and the same day again: the gates hold, exactly as the leader's second pass adds nothing
        game.calls.clear()
        ov.load(facts())
        ov.plan()
        self.assertEqual(game.calls, [])

    def test_every_integrated_gate_reads_the_task_shape_not_the_fixture(self):
        """The same healthy fort as a 336-day run: the integration only appends to the leader's steps. The tools and
        their order are the leader's; the textual differences are the cook standing's brewable reserve (feature 2's
        full-year gate itself, asserted in test_cook_reserve) and the brew standing's adaptive amount and cap —
        the barrel when stays verbatim."""
        game = FakeGame()
        ov = harness.Overseer(game, goal="", days=336)
        ov.load(facts())
        ov.count = 0
        with redirect_stdout(io.StringIO()):
            ov.plan()
        self.assertEqual([t for t, _ in game.calls], [t for t, _ in EXPECTED_SEQUENCE])
        brew = next(a for t, a in game.calls if a.get("recipe") == "brew_drink")
        barrel = next(a for t, a in game.calls if a.get("recipe") == "make_barrel")
        self.assertEqual(brew, EXPECTED_SEQUENCE[1][1])
        self.assertEqual(barrel["when"], EXPECTED_SEQUENCE[2][1]["when"])


if __name__ == "__main__":
    unittest.main()
