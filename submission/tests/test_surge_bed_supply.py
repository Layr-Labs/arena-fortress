"""cx LT08 bed supply (hint hard LT08-0 on 72587ab: beds placed 40 for 47 citizens at H). The surge's bed book tops
up to the wave at once (beds on hand + one-shot make_bed left, validated or not), the first wave is forecast before
it lands, tables and chairs wait while the beds are short, and the fort runs SURGE_CARPENTERS benches. Offline: the
double records the calls; nothing here runs on a windowless or non-migrant shape."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

GOAL_LT08 = ("Migrants are arriving. From day 39 you can't act for 21 days. By day 60 every dwarf must have a "
             "placed bed, drink and food must be in stock every day from day 39.")
GOAL_OPEN = "Run the fortress for 60 days."


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {"order_id": len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {}}


def facts(day, cit, beds, orders=(), workshops=("Carpenters", "Carpenters", "Still", "Kitchen"), hands_off=None,
          tables=12, chairs=12, placed=0, logs=237):
    return {"tick": 828100 + 1200 * day, "day": day,
            "hands_off_in_days": (39 - day) if hands_off is None else hands_off, "observation": {
                "administrators": {"citizens": cit, "manager_active_for_orders": True, "MANAGER_id": 90},
                "stocks": {"beds": beds, "tables": tables, "chairs": chairs, "logs_usable": logs, "drink": 571,
                           "food_edible": 60, "plants_brewable": 7, "plants_total": 7, "barrels_empty": 3,
                           "seeds": 95},
                "map": {"sites": [{"id": "W%d" % i, "kind": "W", "x": 90 + 4 * i, "y": 90, "z": 154, "w": 3, "h": 3}
                                  for i in range(4, 9)]},
                "zones": [], "furniture": [{"kind": "bed", "x": 1, "y": i, "z": 153} for i in range(placed)],
                "workshops": [{"type": w, "built": True, "id": i} for i, w in enumerate(workshops)],
                "orders": list(orders), "plugins": {"autochop": "on", "seedwatch": "on", "autofarm": "on"},
                "farm_plots": [], "dig_designations_pending": 0, "date": {"abs_tick": 828100 + 1200 * day}}}


def bed_order(left, total=None, repeat=None, validated=False):
    o = {"recipe": "make_bed", "job": "ConstructBed", "left": left, "total": total or left, "active": validated,
         "validated": validated, "jobs_in_progress": 0, "id": 100 + left}
    if repeat:
        o["repeat"] = repeat
    return o


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def run_days(self, loads, goal=GOAL_LT08, step="supply"):
        """Loads each fact in turn (the census history drives the wave count), runs `step` on the last."""
        game = FakeGame()
        ov = harness.Overseer(game, goal=goal, days=60)
        for f in loads:
            ov.load(f)
        ov.count = 0
        getattr(ov, step)()
        return ov, game

    @staticmethod
    def orders(game, recipe):
        return [a["amount"] for t, a in game.calls if t == "add_order" and a.get("recipe") == recipe]


class SurgeBedBook(Base):
    def test_day0_orders_the_first_waves_beds_before_it_lands(self):
        # measured day 0: 18 citizens, 19 bed items; the layer ordered 11 (18 + 12 - 19)
        ov, game = self.run_days([facts(0, 18, 19)])
        self.assertTrue(ov.surge)
        self.assertEqual(ov.bed_target(), 2 * 18 + harness.SURGE_BED_MARGIN)
        self.assertEqual(self.orders(game, "make_bed"), [29])

    def test_day1_wave_tops_the_unvalidated_book_up(self):
        # measured day 1: the wave (18 -> 40) landed; make_bed 11 sat unvalidated; the layer added nothing for beds
        # and ordered tables 8 + chairs 8 instead
        ov, game = self.run_days([facts(0, 18, 19), facts(1, 40, 19, orders=[bed_order(11)])])
        self.assertEqual(ov.mig_waves, 1)
        self.assertEqual(ov.bed_target(), 40 + harness.SURGE_BED_MARGIN)
        self.assertEqual(self.orders(game, "make_bed"), [52 - 19 - 11])
        self.assertEqual(self.orders(game, "make_table"), [])
        self.assertEqual(self.orders(game, "make_chair"), [])

    def test_gap_over_thirty_goes_on_the_book_in_one_pass(self):
        ov, game = self.run_days([facts(0, 18, 19), facts(1, 47, 10)])
        self.assertEqual(self.orders(game, "make_bed"), [30, 47 + 12 - 10 - 30])

    def test_a_repeat_bed_order_does_not_count_as_booked(self):
        # the model's make_bed 10 daily [beds < 45] is not this layer's book (it stops at its own threshold)
        ov, game = self.run_days([facts(0, 18, 19), facts(8, 40, 19, orders=[bed_order(10, repeat="daily")])])
        self.assertEqual(sum(self.orders(game, "make_bed")), 52 - 19)

    def test_a_full_book_adds_nothing(self):
        ov, game = self.run_days([facts(0, 18, 19), facts(1, 40, 19, orders=[bed_order(30), bed_order(3)])])
        self.assertEqual(self.orders(game, "make_bed"), [])

    def test_the_pre_wave_forecast_lapses(self):
        ov, _ = self.run_days([facts(0, 18, 19), facts(harness.SURGE_WAVE_WAIT_DAYS + 1, 18, 19)])
        self.assertEqual(ov.bed_target(), 18 + harness.SURGE_BED_MARGIN)

    def test_seats_return_once_the_beds_are_in(self):
        ov, game = self.run_days([facts(0, 18, 19), facts(30, 40, 60, placed=40, tables=2, chairs=2)])
        self.assertEqual(self.orders(game, "make_bed"), [])
        self.assertTrue(self.orders(game, "make_table"))

    def test_open_play_keeps_the_leaders_bed_and_seat_orders(self):
        ov, game = self.run_days([facts(0, 18, 19, hands_off=0), facts(1, 40, 19, orders=[bed_order(11)])],
                                 goal=GOAL_OPEN)
        self.assertFalse(ov.surge)
        self.assertEqual(self.orders(game, "make_bed"), [])            # pending() holds, as before
        self.assertEqual(self.orders(game, "make_table"), [8])


class SurgeCarpenters(Base):
    def builds(self, game):
        return [a["type"] for t, a in game.calls if t == "build_workshop" and a.get("type") == "Carpenters"]

    def test_a_wave_fort_opens_benches_up_to_the_cap(self):
        ov, game = self.run_days([facts(0, 18, 19), facts(1, 40, 19)], step="closer")
        self.assertEqual(self.builds(game), ["Carpenters"])

    def test_no_bench_past_the_cap_or_once_beds_are_in(self):
        shops = ("Carpenters",) * harness.SURGE_CARPENTERS + ("Still", "Kitchen")
        _, game = self.run_days([facts(0, 18, 19), facts(1, 40, 19, workshops=shops)], step="closer")
        self.assertEqual(self.builds(game), [])
        _, game = self.run_days([facts(0, 18, 19), facts(30, 40, 60, placed=40)], step="closer")
        self.assertEqual(self.builds(game), [])

    def test_open_play_never_opens_surge_benches(self):
        _, game = self.run_days([facts(0, 18, 19, hands_off=0), facts(1, 40, 19)], goal=GOAL_OPEN, step="closer")
        self.assertEqual(self.builds(game), [])


if __name__ == "__main__":
    unittest.main()
