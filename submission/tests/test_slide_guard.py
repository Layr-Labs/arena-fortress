"""The adaptive closer: a draining stock arms endgame_supply before the calendar. No game or network is used.

Ported from variants/W4close (tests/test_slide_guard.py). Adaptations to this FULL tree: the guard's fixture is a
336-day run (the alarm is a 180-day-and-up measure here, so lab-length runs stay on the calendar), and the leader
endgame cook standing's when-clause is the full-year OP1 form (a max(30, cit) floor plus the COOK_PLANTS_RESERVE
brewable floor) — the guard moves only the firing date, never the orders' amounts or whens.
"""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


def resp(day, days_left, drink=120, food=90, meals=40, hands_off=None, cit=10):
    return {"day": day, "tick": day * 1200, "days_left": days_left, "hands_off_in_days": hands_off,
            "observation": {"date": {"abs_tick": day * 1200}, "administrators": {"citizens": cit},
                            "stocks": {"drink": drink, "food_edible": food, "prepared_meals": meals,
                                       "logs_usable": 10}}}


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": len(self.calls) + 1}}


# Measured on this tree's v4 base (this turn): flat healthy stocks, days_left 60, one closer() pass (a second
# pass adds nothing), tools and args verbatim — including o_cook_end's cook reserve the v4 base carries, minus the
# plants_brewable clause the winter release drops on this fixture (decision day 276 = winter, ROOT_CAUSES §D-1).
# The guard must reproduce it exactly on the same fixture (slide=False here: only the calendar armed the closer).
LEADER_ENDGAME_SEQUENCE = [
    ("add_order", {"recipe": "brew_drink", "amount": 4, "repeat": "daily", "when": [
        {"stock": "drink", "below": 600}, {"stock": "plants_brewable", "at_least": 4},   # cx: BREW_END_FLOOR
        {"stock": "barrels_empty", "at_least": 1}]}),
    ("add_order", {"recipe": "make_barrel", "amount": 3, "repeat": "daily", "when": [
        {"stock": "barrels_empty", "below": 8}, {"stock": "logs", "at_least": 4}]}),
    ("add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily", "when": [
        {"stock": "prepared_meals", "below": 300}, {"stock": "food_edible", "at_least": 30}]}),
    ("add_order", {"recipe": "make_bed", "amount": 12}),
    ("add_order", {"recipe": "make_table", "amount": 6}),
    ("add_order", {"recipe": "make_chair", "amount": 6}),
]


class SlideGuard(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        self.output = redirect_stdout(self.stream)
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, drink_seq, food_seq=None, day0=100, days_left=222, drink=None, food=90, hands_off=None,
                 days=336):
        """An overseer holding one sample per day from the sequences, then loaded once more at the decision day.
        days: the run length (the alarm is a 180-day-and-up measure; the gate test passes a lab's 60)."""
        game = FakeGame()
        ov = harness.Overseer(game, days=days)
        for i, dv in enumerate(drink_seq):
            ov.load(resp(day0 + i, days_left, drink=dv, food=(food_seq[i] if food_seq else food),
                         hands_off=hands_off))
        ov.load(resp(day0 + len(drink_seq), days_left, drink=(drink if drink is not None else drink_seq[-1]),
                     food=food, hands_off=hands_off))
        ov.count = 0
        return ov, game

    def brew_orders(self, game):
        return [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"]

    def alarms(self):
        return [json.loads(line) for line in self.stream.getvalue().splitlines()
                if '"slide_alarm"' in line]

    def test_ols_slope_fits_the_record_per_day(self):
        self.assertEqual(harness.ols_slope([(d, 114 - d) for d in range(100, 114)]), -1.0)
        # the loop advances two days a pass, so samples skip days: real day values keep the -1/day slope
        self.assertEqual(harness.ols_slope([(d, 120 - d // 2) for d in range(100, 128, 2)]), -0.5)
        self.assertEqual(harness.ols_slope([(5, 10)]), 0.0)
        self.assertEqual(harness.ols_slope([(5, 10), (5, 20)]), 0.0)   # no spread in days: no fit

    def test_load_records_one_sample_per_day(self):
        ov, _ = self.overseer([120, 120, 120], day0=10, days_left=320)
        self.assertEqual(len(ov.stock_hist), 4)
        self.assertEqual(ov.stock_hist[-1], (13, 120, 90, 40))   # (day, drink, food_edible, prepared_meals)
        same_day = {"day": 13, "tick": 13 * 1200, "days_left": 323,
                    "observation": {"date": {"abs_tick": 13 * 1200},
                                    "stocks": {"drink": 118, "food_edible": 90, "prepared_meals": 40}}}
        ov.load(same_day)   # a second load on the same day must not add a sample
        self.assertEqual(len(ov.stock_hist), 4)

    def test_draining_drink_arms_endgame_supply_before_the_calendar(self):
        # 14 days of -1/day drink, days_left 222: far outside ENDGAME_DAYS, yet the stock dies long before day 336
        ov, game = self.overseer(list(range(114, 100, -1)), drink=100)
        self.assertEqual(len(ov.stock_hist), harness.SLOPE_WINDOW)
        ov.closer()
        ov.closer()   # a second pass the same day: no re-order, no second alarm
        brews = self.brew_orders(game)
        self.assertEqual(len(brews), 1)
        self.assertEqual(brews[0]["amount"], 4)   # the amount is unchanged: only the firing date moved earlier
        self.assertIn("o_brew_end", ov.done)
        self.assertTrue(ov.sliding)
        on = [a for a in self.alarms() if a["on"]]
        self.assertEqual(len(on), 1)              # the ON flip is logged exactly once
        self.assertEqual(on[0]["slope_drink"], -1.0)
        self.assertEqual(on[0]["days_left"], 222)

    def test_flat_stock_keeps_the_calendar_trigger(self):
        ov, game = self.overseer([120] * 14, days_left=60, drink=120)
        ov.closer()
        brews = self.brew_orders(game)
        self.assertEqual(len(brews), 1)
        self.assertEqual(brews[0]["amount"], 4)   # armed the old way, same order as ever
        self.assertFalse(ov.sliding)
        self.assertEqual(self.alarms(), [])       # a healthy stock raises no alarm

    def test_rising_stock_does_not_fire(self):
        ov, game = self.overseer(list(range(101, 115)), days_left=222)
        ov.closer()
        self.assertEqual(game.calls, [])
        self.assertFalse(ov.sliding)
        self.assertEqual(self.alarms(), [])

    def test_food_drain_arms_it_too(self):
        ov, game = self.overseer([120] * 14, food_seq=list(range(94, 80, -1)), days_left=222, food=80)
        ov.closer()
        cooks = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "cook_meal"]
        self.assertEqual(len(cooks), 1)
        self.assertEqual(cooks[0]["amount"], 2)
        self.assertTrue(ov.sliding)

    def test_lab_tasks_keep_window_supply_as_sole_owner(self):
        # a steep drain inside a lab task must not add endgame orders next to the window's own
        ov, game = self.overseer(list(range(114, 100, -1)), drink=100, days_left=100, hands_off=10)
        ov.closer()
        ov.closer()
        brews = self.brew_orders(game)
        self.assertEqual(len(brews), 1)
        self.assertEqual(brews[0]["amount"], 5)   # o_brew_win, the window's own order
        self.assertNotIn("o_brew_end", ov.done)
        self.assertEqual([a for a in game.calls if "when" in a[1] and a[1].get("amount") == 4], [])
        # a lab task far from its window: nothing fires, the alarm stays off (hands_off owns the run)
        ov2, game2 = self.overseer(list(range(114, 100, -1)), drink=100, days_left=100, hands_off=40)
        ov2.closer()
        self.assertEqual(game2.calls, [])
        self.assertFalse(ov2.sliding)
        self.assertEqual(self.alarms(), [])

    def test_healthy_stock_at_the_horizon_reproduces_the_leader_sequence(self):
        ov, game = self.overseer([120] * 10, day0=266, days_left=60, drink=120)
        ov.closer()
        ov.closer()   # the second pass of the same day adds nothing, as on the leader
        self.assertEqual(game.calls, LEADER_ENDGAME_SEQUENCE)
        self.assertFalse(ov.sliding)
        self.assertEqual(self.alarms(), [])

    # ---- the days gate: a lab-length run (days < 180) never slides, however steep the drain
    def test_lab_length_run_never_slides(self):
        ov, game = self.overseer(list(range(114, 100, -1)), drink=100, days_left=222, days=60)
        ov.closer()
        ov.closer()
        self.assertEqual(game.calls, [])      # no endgame orders: neither the calendar nor the slope armed
        self.assertFalse(ov.sliding)
        self.assertEqual(self.alarms(), [])
        self.assertEqual(len(ov.stock_hist), harness.SLOPE_WINDOW)   # the record still accumulates


if __name__ == "__main__":
    unittest.main()
