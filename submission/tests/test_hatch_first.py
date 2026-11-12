"""cx HATCH FIRST (OP1-3 day-0 macaques): the run's first hatch cover is ordered on the first pass that wants one,
logs or not, within HATCH_FIRST_DAYS, so it is the Carpenters' first job ahead of the day-0 barrel and furniture
orders (e60d4ce: ordered 5th on day 1.33, out on day 10.33 behind a barrel). No game or network."""
import inspect
import sys
import unittest
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness  # noqa: E402
from test_shelter_hatches import FakeGame, Quiet, fort, overseer  # noqa: E402

DOORS = {"door_items_free": 0, "hatch_cover_items_free": 0, "list": []}
ORDER = ("add_order", {"recipe": "make_hatch_cover", "amount": 1})


class HatchFirst(Quiet):
    def run_once(self, ov, game, day, **kw):
        ov.load(fort(day, citizens=7, doors=dict(DOORS), **kw))
        game.calls.clear()
        ov.entrance_hatches()
        return game.calls

    def test_day_0_no_logs_orders_one_cover(self):
        game = FakeGame()
        ov = overseer(game)
        self.assertEqual(self.run_once(ov, game, 0, logs=0), [ORDER])
        self.assertEqual(ov.hatch_ordered, 1)

    def test_queued_cover_is_not_ordered_twice(self):
        game = FakeGame()
        ov = overseer(game)
        self.run_once(ov, game, 0, logs=0)
        q = [{"id": 4, "recipe": "make_hatch_cover", "left": 1, "job": "ConstructHatchCover"}]
        self.assertEqual(self.run_once(ov, game, 1, logs=0, orders=q), [])

    def test_past_the_first_days_the_wood_floor_holds(self):
        game = FakeGame()
        ov = overseer(game)
        self.assertEqual(self.run_once(ov, game, harness.HATCH_FIRST_DAYS + 1, logs=0), [])

    def test_off_restores_the_wood_floor(self):
        old = harness.HATCH_FIRST_EARLY
        harness.HATCH_FIRST_EARLY = False
        try:
            game = FakeGame()
            ov = overseer(game)
            self.assertEqual(self.run_once(ov, game, 0, logs=0), [])
        finally:
            harness.HATCH_FIRST_EARLY = old

    def test_the_hatch_step_runs_before_the_supply_orders(self):
        src = inspect.getsource(harness.Overseer.plan)
        self.assertLess(src.index("self.entrance_hatches"), src.index("self.management()"))
        self.assertLess(src.index("self.entrance_hatches"), src.index("self.supply()"))


if __name__ == "__main__":
    unittest.main()
