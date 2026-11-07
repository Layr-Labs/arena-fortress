"""Cut 8: the final-stretch supply step and the advance cap that lets the daily pass see the stretch.
No game or network is used."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness
from overseer.harness import Overseer

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

WORKSHOPS = [{"type": t, "built": True} for t in ("Carpenters", "Still", "Kitchen", "Butchers")]
ANIMALS = [{"id": 501, "race": "DOG", "tame": True, "adult": True, "pet_owner_id": 12, "marked_for_slaughter": False},
           {"id": 502, "race": "CALF", "tame": True, "adult": False, "pet_owner_id": None, "marked_for_slaughter": False},
           {"id": 503, "race": "YAK", "tame": True, "adult": True, "pet_owner_id": None, "marked_for_slaughter": False},
           {"id": 504, "race": "YAK", "tame": True, "adult": True, "pet_owner_id": -1, "marked_for_slaughter": False}]


class FakeGame:
    def __init__(self, animals=ANIMALS):
        self.calls, self.animals = [], animals

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if tool == "slaughter":
            for a in self.animals:
                if a["id"] == args["unit_id"]:
                    a["marked_for_slaughter"] = True
        return {"ok": True, "result": {"order_id": 900 + len(self.calls)}}

    def query(self, name, **kw):
        return {"query": name, "result": {"ok": True, "kind": kw.get("kind"), "units": [dict(a) for a in self.animals]}}


def resp(day, days_left, drink=300, food=200, cit=20, hands_off=None, workshops=WORKSHOPS):
    r = {"day": day, "days_left": days_left, "tick": day * 1200, "observation": {
        "date": {"abs_tick": day * 1200}, "administrators": {"citizens": cit},
        "stocks": {"drink": drink, "food_edible": food, "logs_usable": 5}, "workshops": workshops,
        "orders": [], "map": {"sites": [{"id": "W1", "kind": "W", "x": 1, "y": 1, "z": 10}]}}}
    if hands_off is not None:
        r["hands_off_in_days"] = hands_off
    return r


class FinalStretch(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def run_day(self, o, r):
        o.load(r)
        o.count = 0
        o.final_stretch()

    def test_nothing_before_the_stretch(self):
        game = FakeGame()
        o = Overseer(game)
        self.run_day(o, resp(300, 36))           # OP1: 336 days, stretch 28, lead 3 -> starts at 31 days left
        self.assertEqual(game.calls, [])
        self.assertEqual(o.fhist, [])

    def test_raised_brew_cap_once_at_the_lead(self):
        game = FakeGame()
        o = Overseer(game)
        self.run_day(o, resp(305, 31, drink=280, cit=20))
        brew = [a for t, a in game.calls if t == "add_order"]
        self.assertEqual(len(brew), 1, game.calls)
        cap = brew[0]["when"][0]["below"]
        self.assertGreater(cap, 300 + 20 * 20 / 336 * 31)   # above DRINK_CAP plus the stretch's consumption
        self.assertEqual(brew[0]["recipe"], "brew_drink")
        self.assertEqual(brew[0]["repeat"], "daily")
        self.assertIn(901, o.brew_orders)                     # protected like the base's daily brew order
        self.run_day(o, resp(306, 30))
        self.assertEqual(len([1 for t, _ in game.calls if t == "add_order"]), 1)   # once

    def test_no_brew_order_without_a_still(self):
        game = FakeGame()
        o = Overseer(game)
        self.run_day(o, resp(305, 31, workshops=[{"type": "Kitchen", "built": True}]))
        self.assertEqual([t for t, _ in game.calls if t == "add_order"], [])

    def test_hands_off_tasks_are_left_alone(self):
        game = FakeGame()
        o = Overseer(game)
        self.run_day(o, resp(35, 25, hands_off=4))           # LT08-like: the window has its own readiness
        self.assertEqual(game.calls, [])

    def test_falling_food_slaughters_a_spare_adult(self):
        game = FakeGame()
        o = Overseer(game)
        for i, food in enumerate((120, 110, 100, 90)):       # the stretch starts at day 308; food falls 10 a day
            self.run_day(o, resp(307 + i, 29 - i, food=food))
        kills = [a["unit_id"] for t, a in game.calls if t == "slaughter"]
        self.assertEqual(kills, [503], game.calls)           # not the pet (501), not the calf (502)
        self.assertEqual(o.final_slaughters, 1)

    def test_steady_food_slaughters_nothing(self):
        game = FakeGame()
        o = Overseer(game)
        for i, food in enumerate((400, 401, 399, 402, 400)):
            self.run_day(o, resp(307 + i, 29 - i, food=food))
        self.assertEqual([1 for t, _ in game.calls if t == "slaughter"], [])

    def test_slaughter_is_spaced_and_capped(self):
        game = FakeGame(animals=[{"id": 600 + i, "tame": True, "adult": True, "pet_owner_id": None,
                                  "marked_for_slaughter": False} for i in range(8)])
        o = Overseer(game)
        for i in range(25):
            o.now = (307 + i) * 1200
            self.run_day(o, resp(307 + i, 29 - i, food=max(0, 200 - 8 * i)))
        kills = [a["unit_id"] for t, a in game.calls if t == "slaughter"]
        self.assertEqual(len(kills), harness.FINAL_SLAUGHTERS, kills)
        self.assertEqual(len(set(kills)), len(kills))

    def test_missing_butchers_is_built_first(self):
        game = FakeGame()
        o = Overseer(game)
        ws = [{"type": t, "built": True} for t in ("Carpenters", "Still", "Kitchen")]
        for i, food in enumerate((120, 100, 80)):
            self.run_day(o, resp(307 + i, 29 - i, food=food, workshops=ws))
        self.assertIn(("build_workshop", {"type": "Butchers", "site": "W1"}), game.calls)
        self.assertEqual([1 for t, _ in game.calls if t == "slaughter"], [])

    def test_slope_matches_least_squares(self):
        self.assertAlmostEqual(Overseer.slope([(0, 10), (1, 8), (2, 6)]), -2.0)
        self.assertEqual(Overseer.slope([(0, 10)]), 0.0)


class FinalCap(unittest.TestCase):
    def test_caps(self):
        self.assertIsNone(Overseer.final_cap(10, 50, 4))          # hands-off task
        self.assertIsNone(Overseer.final_cap(None, 50, None))
        self.assertEqual(Overseer.final_cap(290, 46, None), 15)   # OP1: lands at 31 days left
        self.assertEqual(Overseer.final_cap(305, 31, None), 3)    # in the lead-in and the stretch: 3 days at a time
        self.assertEqual(Overseer.final_cap(330, 6, None), 3)
        self.assertEqual(Overseer.final_cap(100, 116, None), 85)  # MY1 216 days: stretch 28, lands at 31 days left


if __name__ == "__main__":
    unittest.main()
