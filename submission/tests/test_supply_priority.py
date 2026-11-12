"""The OP1 supply-priority guards on the wave-wealth chase (the 2026-11-09 interference read,
OP1_SUPPLY_INTERFERENCE.md): the chase yields to beds, seats and barrels while the wood on hand is under
logs_guard(), and the chase order's amount eases once this run's own measured wealth rate already carries the
remaining fund across the reporting window. The measured clean runs bound the guards' cost at zero there
(df2-op1-hard OP1-1/2: amount 12, supply 1.00, logs_usable never under 168) — these tests pin the mechanics, not
a behaviour change on the measured board. No game or network is used."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness as overseer_harness

assert Path(overseer_harness.__file__).is_relative_to(VARIANT), overseer_harness.__file__


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"id": len(self.calls), "order_id": len(self.calls)}}


def facts(day=100, cit=15, wealth=8000, logs=60, beds=25, tables=12, chairs=14, barrels=10,
          orders=(), workshops=("Carpenters", "Still", "Kitchen", "Craftsdwarfs")):
    return {"day": day, "tick": day * 1200, "hands_off_in_days": None, "days_left": 336 - day, "observation": {
        "administrators": {"citizens": cit, "manager_active_for_orders": True, "MANAGER_id": 1},
        "wealth": {"created": wealth, "total": wealth},
        "stocks": {"logs_usable": logs, "boulders_usable": 0, "drink": 200, "food_edible": 100,
                   "plants_brewable": 10, "plants_total": 30, "barrels_empty": barrels,
                   "beds": beds, "tables": tables, "chairs": chairs},
        "map": {"sites": []}, "zones": [], "furniture": [],
        "workshops": [{"type": w} for w in workshops],
        "orders": list(orders), "plugins": {"autochop": "on", "seedwatch": "on", "autofarm": "on"},
        "date": {"abs_tick": day * 1200},
    }}


class SupplyPriority(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, sites=(), **kw):
        game = FakeGame()
        ov = overseer_harness.Overseer(game, days=336)
        ov.load(facts(**kw))
        ov.sites = list(sites)
        ov.count = 0
        return ov, game

    # ---- the logs guard: beds, seats and barrels claim the wood before the chase
    def test_furniture_logs_needed_composes_the_shortfalls(self):
        ov, _ = self.overseer()          # beds 25 >= 21, seats 10 vs 12/14, barrels 10 >= 8: covered
        self.assertEqual(ov.furniture_logs_needed(), 0)
        ov2, _ = self.overseer(beds=10, tables=5, chairs=5, barrels=3, cit=15)
        # bed_target 21 -> 11; seats 10 -> 5+6; barrels 8-3 -> 5
        self.assertEqual(ov2.furniture_logs_needed(), 11 + 5 + 6 + 5)
        self.assertEqual(ov2.logs_guard(), overseer_harness.LOG_RESERVE + 27)

    def test_low_logs_pause_the_standing_and_the_extra_benches(self):
        ov, game = self.overseer(logs=20)   # guard floor 25, wood under it: the chase yields
        ov.progress()
        self.assertEqual(game.calls, [])

    def test_low_logs_do_not_block_the_first_bench_or_the_furniture(self):
        ov, game = self.overseer(logs=20, workshops=("Carpenters", "Still", "Kitchen"),
                                 sites=[{"id": "W1", "kind": "W"}])
        ov.progress()
        self.assertEqual([t for t, _ in game.calls], ["build_workshop"])   # the bench itself still goes up
        self.assertEqual(game.calls[0][1]["type"], "Craftsdwarfs")

    def test_covered_inventory_keeps_the_chase_at_the_measured_amount(self):
        ov, game = self.overseer()          # the measured board: wood 60 over the floor, stocks covered
        ov.progress()
        ordered = [a for t, a in game.calls if t == "add_manager_order"]
        self.assertEqual([a["amount"] for a in ordered], [overseer_harness.CRAFT_AMOUNT_WAVE])
        self.assertEqual(ordered[0]["when"], [{"item_type": "WOOD", "at_least": overseer_harness.LOG_RESERVE}])

    def test_low_logs_hold_the_third_bench_but_not_one_already_far_fund(self):
        ov, game = self.overseer(logs=20, wealth=5000,
                                 workshops=("Carpenters", "Still", "Kitchen", "Craftsdwarfs"),
                                 orders=({"job": "MakeCrafts", "repeat": "daily", "total": 12, "id": 7,
                                          "left": 12, "active": True,
                                          "when": [{"item_type": "WOOD", "test": "AtLeast", "value": 25}]},))
        ov.progress()                        # fund far, but the wood is under the guard: no third bench
        self.assertEqual([t for t, _ in game.calls], [])

    # ---- the adaptive amount: the measured rate, not the ceiling, decides the order size
    def test_first_pass_without_history_keeps_the_full_amount(self):
        ov, _ = self.overseer()
        self.assertEqual(ov.craft_amount_chase(), overseer_harness.CRAFT_AMOUNT_WAVE)

    def test_amount_eases_once_the_measured_rate_carries_the_fund(self):
        ov, _ = self.overseer()              # d80 -> d100: +3000 wealth over 20 d = 150/d; 150 * 105 * 1.25 >> gap
        ov.craft_mark = (80, 5000)
        self.assertLess(ov.craft_amount_chase(), overseer_harness.CRAFT_AMOUNT_WAVE)
        self.assertEqual(ov.craft_amount_chase(), overseer_harness.CRAFT_AMOUNT_BASE)

    def test_amount_stays_full_when_the_rate_falls_short_of_the_fund(self):
        ov, _ = self.overseer(wealth=5600)   # 600/20 = 30/d: 30 * 105 * 1.25 < gap 15400
        ov.craft_mark = (80, 5000)
        self.assertEqual(ov.craft_amount_chase(), overseer_harness.CRAFT_AMOUNT_WAVE)

    def test_on_track_standing_is_recut_to_the_eased_amount(self):
        ov, game = self.overseer(orders=({"job": "MakeCrafts", "repeat": "daily", "total": 12, "id": 7,
                                          "left": 12, "active": True,
                                          "when": [{"item_type": "WOOD", "test": "AtLeast", "value": 25}]},))
        ov.craft_mark = (80, 5000)
        ov.progress()
        cuts = [a for t, a in game.calls if t == "cancel_order"]
        self.assertEqual(cuts, [{"order_id": 7}])
        self.assertEqual(ov.craft_desired, overseer_harness.CRAFT_AMOUNT_BASE)
        self.assertEqual(ov.craft_amount_day, 100)

    def test_recut_waits_out_the_dwell(self):
        ov, game = self.overseer(day=100, orders=({"job": "MakeCrafts", "repeat": "daily", "total": 12, "id": 7,
                                                   "left": 12, "active": True,
                                                   "when": [{"item_type": "WOOD", "test": "AtLeast", "value": 25}]},))
        ov.craft_mark = (80, 5000)
        ov.craft_amount_day = 95             # a re-cut 5 days ago: inside the dwell
        ov.progress()
        self.assertEqual([t for t, _ in game.calls], [])

    def test_readd_after_a_recut_keeps_the_decided_regime(self):
        ov, game = self.overseer()
        ov.craft_desired = overseer_harness.CRAFT_AMOUNT_BASE   # decided while on track; the cancel has landed
        ov.craft_mark = (100, 8000)          # fresh mark: a fresh computation would read the full amount again
        ov.progress()
        ordered = [a for t, a in game.calls if t == "add_manager_order"]
        self.assertEqual([a["amount"] for a in ordered], [overseer_harness.CRAFT_AMOUNT_BASE])

    def test_after_the_window_the_leader_floor_neither_recuts_nor_guards_the_amount(self):
        ov, game = self.overseer(day=overseer_harness.PROGRESS_LAST_DAY + 1, wealth=5000, logs=5,
                                 orders=({"job": "MakeCrafts", "repeat": "daily", "total": 12, "id": 7,
                                          "left": 12, "active": True,
                                          "when": [{"item_type": "WOOD", "test": "AtLeast", "value": 25}]},))
        ov.progress()                        # chasing is over: the standing is left to the game-side when
        self.assertEqual([t for t, _ in game.calls], [])


if __name__ == "__main__":
    unittest.main()
