"""The LT08 probe's three measures must be scoped to the surge-with-window shape (LT08): a windowless task
whose goal mentions migrants (MY1/OP1's shape) and the labs must see the leader's behaviour exactly."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import math
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__



def bridge(a):
    """cx lt08drink: the window bridge (o_brew_bridge_win, the one brew standing with a drink cap; tested in
    test_window_bridge.py) is left out where a test counts the eve's window brew."""
    return "drink" in [w.get("stock") for w in a.get("when") or []]

class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": len(self.calls)}}


def facts(cit=19, hands_off=21, stocks=None, sites=(), roles=None):
    return {"tick": 0, "hands_off_in_days": hands_off, "observation": {
        "administrators": {"citizens": cit, "manager_active_for_orders": True, "MANAGER_id": 1},
        "stocks": stocks if stocks is not None else {"plants_brewable": 25, "plants_total": 30,
                                                     "food_edible": 200, "drink": 480, "beds": 12,
                                                     "barrels_empty": 5, "logs_usable": 40},
        "map": {"sites": list(sites)}, "zones": [], "furniture": [], "workshops": [],
        "orders": [], "plugins": {"autochop": "on", "seedwatch": "on", "autofarm": "on"},
        "farm_plots": [], "dig_designations_pending": 0,
        "date": {"abs_tick": 0},
    }}, None


GOAL_LT08 = "Migrants are arriving. From day 39 you can't act for 21 days."
GOAL_OPEN = "Run the fortress for {days} days."


class Surge(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, cit=19, hands_off=21, goal_migrant=True, stocks=None, sites=()):
        game = FakeGame()
        obs, _ = facts(cit=cit, hands_off=hands_off, stocks=stocks, sites=sites)
        goal = GOAL_LT08 if goal_migrant else GOAL_OPEN
        overseer = harness.Overseer(game, goal=goal, days=60)
        overseer.load({"tick": 0, "hands_off_in_days": hands_off, "observation": obs["observation"]})
        overseer.count = 0
        return overseer, game

    def test_lt08_shape_arms_the_surge(self):
        overseer, _ = self.overseer()
        self.assertIs(overseer.surge, True)
        self.assertEqual(overseer.bed_target(), overseer.cit + 12)

    def test_windowless_or_lab_goals_do_not_arm_it(self):
        overseer, _ = self.overseer(hands_off=None)           # MY1/OP1's shape
        self.assertIs(overseer.surge, False)
        overseer2, _ = self.overseer(goal_migrant=False)      # the other labs
        self.assertIs(overseer2.surge, False)

    def test_window_brew_lowers_the_plant_floor_and_adds_a_food_floor(self):
        overseer, game = self.overseer(hands_off=harness.SURGE_BREW_LEAD)   # cx: the surge's brew waits for the eve
        overseer.window_supply()
        brews = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink" and not bridge(a)]
        self.assertEqual(len(brews), 1)
        self.assertIn({"stock": "plants_brewable", "at_least": 2}, brews[0]["when"])
        self.assertIn({"stock": "food_edible", "at_least": max(3, overseer.cit // 2)}, brews[0]["when"])

    def test_surge_bed_orders_carry_thirty(self):
        overseer, game = self.overseer(cit=40)   # the wave's shortfall exceeds 30, so the batch caps at 30
        overseer.supply()
        beds = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "make_bed"]
        self.assertEqual(beds[0]["amount"], 30)

    def test_non_surge_bed_orders_stay_at_eight(self):
        overseer, game = self.overseer(goal_migrant=False, hands_off=None)
        overseer.supply()
        beds = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "make_bed"]
        self.assertEqual(beds[0]["amount"], 8)

    def test_surge_digs_the_wave_dorm_capacity(self):
        sites = [{"id": "R1", "kind": "R", "z": 3, "x": 5, "y": 5, "w": 9, "h": 7, "soil": False},
                 {"id": "R2", "kind": "R", "z": 3, "x": 20, "y": 5, "w": 9, "h": 7, "soil": False}]
        overseer, game = self.overseer(sites=sites)
        overseer.digging()
        digs = [a for t, a in game.calls if t == "dig_room"]
        self.assertGreaterEqual(len(digs), 1)   # the wave dorms start before the beds exist

    def test_open_play_never_digs_the_wave_capacity(self):
        overseer, game = self.overseer(goal_migrant=False, hands_off=None)
        overseer.digging()
        self.assertEqual([t for t, _ in game.calls if t == "dig_room"], [])   # only the leader's own flow

    # ---- the integration gate (a): on MY1/OP1's shape (migrant text, no hands-off window) every bed measure of
    # the surge cluster is inert — the bed system runs the leader's path exactly, seats included.
    def test_open_play_with_migrant_text_runs_the_leaders_bed_system(self):
        stocks = {"plants_brewable": 4, "plants_total": 6, "food_edible": 200, "drink": 480, "beds": 2,
                  "tables": 0, "chairs": 0, "barrels_empty": 5, "logs_usable": 40}
        overseer, game = self.overseer(hands_off=None, stocks=stocks)   # migrant goal, no window: OP1's shape
        self.assertEqual(overseer.bed_target(), overseer.cit + 3)   # the leader's margin, not the surge's +12
        overseer.housing_check()   # no supply this pass: the closer's own orders show what the seats branch did
        overseer.closer()
        beds = [a for t, a in game.calls if a.get("recipe") == "make_bed"]
        self.assertEqual([a["amount"] for a in beds], [min(30, overseer.cit + 2)])   # the leader's close order
        tables = [a for t, a in game.calls if a.get("recipe") == "make_table"]
        chairs = [a for t, a in game.calls if a.get("recipe") == "make_chair"]
        self.assertEqual([a["amount"] for a in tables], [math.ceil(overseer.cit / 2) + 1])   # seats work ran
        self.assertEqual([a["amount"] for a in chairs], [math.ceil(overseer.cit / 2) + 1])
        self.assertEqual([t for t, _ in game.calls if t == "build_workshop"], [])   # no surge Carpentry either

    def test_windowless_migrant_dig_pass_digs_only_the_leader_rooms(self):
        sites = [{"id": "R%d" % i, "kind": "R", "z": 3, "x": 5 + 20 * i, "y": 5, "w": 9, "h": 7, "soil": False}
                 for i in range(1, 5)]
        overseer, game = self.overseer(hands_off=None, sites=sites)   # migrant text, no window: MY1's shape
        overseer.digging()
        digs = [a for t, a in game.calls if t == "dig_room"]
        # the leader's own flow: one dorm, one dine, one office — the fourth room waits (no wave-capacity dig;
        # with the surge armed the same fixture draws a fourth dig_room for the wave dorm)
        self.assertEqual(len(digs), 3)
        self.assertEqual(sorted(a["site"] for a in digs), ["R1", "R2", "R3"])


if __name__ == "__main__":
    unittest.main()
