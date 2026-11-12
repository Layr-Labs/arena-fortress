"""cx F livestock (probe of hint std MY1-3 on 94a64ee with the rotting reserve: drink 1.0, but food 149 -> 127 over
F for 16 citizens, supply 0.714, while 5 tame animals stood alive at H). Inside F, while food's cover at the fort's
gross use is under F_FOOD_COVER_DAYS, a tame unowned animal is slaughtered every F_SLAUGHTER_DAYS. No game or
network."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overseer import harness  # noqa: E402

ANIMALS = [{"id": 90, "race": "CAT", "tame": True, "pet_owner_id": 81},
           {"id": 91, "race": "GOAT", "tame": True, "marked_for_slaughter": True},
           {"id": 92, "race": "KEA", "tame": False},
           {"id": 93, "race": "WATER_BUFFALO", "tame": True, "pet_owner_id": -1},
           {"id": 94, "race": "ALPACA", "tame": True}]


class FakeGame:
    def __init__(self, animals=ANIMALS):
        self.calls, self.animals = [], animals

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {}}

    def query(self, name, **kw):
        if name == "units" and kw.get("kind") == "animals":
            return {"result": {"units": [dict(a) for a in self.animals]}}
        return {"result": {"units": []}}


def resp(day, days=216, cit=16, food=149, drink=45):
    stocks = {"drink": drink, "food_edible": food, "prepared_meals": 130, "plants_brewable": 0, "plants_total": 0,
              "barrels_empty": 20, "logs_usable": 100, "seeds": 3, "furniture_free": {}}
    obs = {"date": {"abs_tick": day * harness.DAY, "day_of_year": (135 + day) % harness.YEAR_DAYS},
           "administrators": {"citizens": cit}, "stocks": stocks, "map": {"sites": []}, "zones": [], "furniture": [],
           "workshops": [{"type": w, "built": True} for w in ("Still", "Kitchen", "Butchers")], "orders": [],
           "burrows": {"civilian_alert": False}}
    return {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": days - day}


class FLivestock(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def run_day(self, ov, day, **kw):
        ov.load(resp(day, days=ov.days, **kw))
        ov.count = 0
        ov.f_livestock()

    @staticmethod
    def slaughtered(game):
        return [a["unit_id"] for t, a in game.calls if t == "slaughter"]

    def test_inside_f_a_short_food_cover_slaughters_the_first_free_animal(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        self.run_day(ov, 188 + harness.F_SLAUGHTER_FROM)
        self.assertEqual(self.slaughtered(game), [93])   # not the pet, the marked goat, the wild kea

    # cx MY1 supply plan: F's first days lift the slope ~nothing (6p(28-p)/28^3); the slaughters start 3 days in
    def test_not_in_f_s_first_days(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        for day in range(189, 188 + harness.F_SLAUGHTER_FROM):
            self.run_day(ov, day)
        self.assertEqual(self.slaughtered(game), [])

    def test_the_larger_animals_go_first(self):
        game = FakeGame(animals=[{"id": 1, "race": "CAT", "tame": True}, {"id": 2, "race": "BIRD_PEAFOWL_BLUE",
                                                                         "tame": True},
                                 {"id": 3, "race": "DOG", "tame": True}])
        ov = harness.Overseer(game, days=216)
        self.run_day(ov, 192)
        self.assertEqual(self.slaughtered(game), [3])

    def test_one_every_f_slaughter_days(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        for day in range(191, 191 + harness.F_SLAUGHTER_DAYS):
            self.run_day(ov, day)
        self.assertEqual(len(self.slaughtered(game)), 1)
        self.run_day(ov, 191 + harness.F_SLAUGHTER_DAYS)
        self.assertEqual(len(self.slaughtered(game)), 2)

    def test_before_f_nothing(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        self.run_day(ov, 216 - ov.f_len() - 1)
        self.assertEqual(self.slaughtered(game), [])

    def test_the_last_days_nothing(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        self.run_day(ov, 216 - harness.F_SLAUGHTER_TAIL + 1)
        self.assertEqual(self.slaughtered(game), [])

    def test_a_full_cover_keeps_the_animals(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        prior = harness.ALLOC_FOOD_PER_CIT_DAY * 16
        self.run_day(ov, 190, food=int(prior * harness.F_FOOD_COVER_DAYS) + 1)
        self.assertEqual(self.slaughtered(game), [])

    def test_no_free_animal_no_call(self):
        game = FakeGame(animals=ANIMALS[:3])
        ov = harness.Overseer(game, days=216)
        self.run_day(ov, 190)
        self.assertEqual(self.slaughtered(game), [])

    def test_lab_task_never(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=60)
        self.run_day(ov, 50)
        self.assertEqual(self.slaughtered(game), [])


if __name__ == "__main__":
    unittest.main()
