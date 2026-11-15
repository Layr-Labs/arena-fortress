"""Offline regressions for a visiting caravan's goods (the challenge's known issue #125; discussion #173 item 1): while
merchants are on the map, stocks.food_edible and stocks.drink include their goods. In six local games the food count
jumped by 155 to 304 on the arrival report and fell back to 0-22 within a day of the departure report, so the hunger
cull never fired while the fort's own food ran out. The layer now plans from the fort's own share. Stub game; no DF.
The numbers below are a recorded full-year game's (19 food before the merchants, 174 with them, 16 after).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from overseer.harness import CARAVAN_DAYS, Overseer  # noqa: E402
from support import StubGame, resp  # noqa: E402

ARRIVE = {"text": "The merchants need a trade depot to unload their goods."}
SOON = {"text": "The merchants from Dastot Kor will be leaving soon."}
LEAVE = {"text": "The merchants from Dastot Kor have embarked on their journey."}
OTHER = {"text": "Tobul Letmoskot has created a masterpiece maple crown!"}


def fort(day, food, drink, events=(), cit=13, days_left=None):
    r = resp(336 - day if days_left is None else days_left, day, food=food, drink=drink, cit=cit)
    r["observation"]["recent_events"] = list(events)
    return r


def overseer():
    g = StubGame()
    ov = Overseer(g, goal="Run the fortress", days=336)
    ov.set_task({"goal": "Run the fortress for 336 days."})
    ov.count = 0
    return ov, g


class Caravan(unittest.TestCase):
    def test_the_goods_are_taken_off_from_arrival_to_departure(self):
        ov, _ = overseer()
        ov.load(fort(164, 19, 60, [OTHER]))
        ov.load(fort(166, 174, 140, [ARRIVE, OTHER]))
        self.assertEqual((ov.st["food_edible"], ov.st["drink"]), (19, 60))
        self.assertEqual((ov.st["food_reported"], ov.st["drink_reported"]), (174, 140))
        ov.load(fort(180, 160, 150, [SOON]))                     # the fort ate 14 and brewed 10 of its own
        self.assertEqual((ov.st["food_edible"], ov.st["drink"]), (5, 70))
        ov.load(fort(198, 170, 145, [LEAVE, SOON]))                # the count still holds the goods on the report
        self.assertEqual((ov.st["food_edible"], ov.st["drink"]), (15, 65))
        ov.load(fort(200, 16, 64, [LEAVE, SOON]))                  # they are gone
        self.assertIsNone(ov.caravan)
        self.assertEqual((ov.st["food_edible"], ov.st["drink"]), (16, 64))

    def test_a_departure_report_ends_it_within_days(self):
        ov, _ = overseer()
        ov.load(fort(160, 18, 60))
        ov.load(fort(162, 219, 140, [ARRIVE]))
        ov.load(fort(194, 222, 141, [LEAVE]))
        self.assertIsNotNone(ov.caravan)
        ov.load(fort(198, 223, 142, [LEAVE]))                      # still the same count four days on: stop
        self.assertIsNone(ov.caravan)
        self.assertEqual(ov.st["food_edible"], 223)

    def test_the_hunger_cull_reads_the_forts_own_food(self):
        ov, g = overseer()
        ov.load(fort(160, 18, 60))
        ov.load(fort(162, 219, 140, [ARRIVE]))
        ov.provision()
        self.assertEqual(g.tools("slaughter"), [])               # 18 of its own for 13: not hungry yet
        ov.load(fort(185, 203, 130, [SOON]))                    # 2 left of its own; the count still shows 203
        ov.provision()
        self.assertEqual(len(g.tools("slaughter")), 1)

    def test_a_harvest_or_a_feast_is_not_a_caravan(self):
        ov, _ = overseer()
        ov.load(fort(326, 17, 300, [OTHER]))
        ov.load(fort(327, 132, 300, [{"text": "The Stray Yak (Tame) has been slaughtered."}]))
        self.assertIsNone(ov.caravan)
        self.assertEqual(ov.st["food_edible"], 132)

    def test_goods_gone_without_a_report_or_too_long_end_it(self):
        ov, _ = overseer()
        ov.load(fort(45, 8, 40))
        ov.load(fort(47, 312, 90, [ARRIVE]))
        ov.load(fort(76, 117, 40))                                # below the goods: they are gone
        self.assertIsNone(ov.caravan)
        self.assertEqual(ov.st["food_edible"], 117)
        ov, _ = overseer()
        ov.load(fort(45, 8, 40))
        ov.load(fort(47, 312, 90, [ARRIVE]))
        ov.load(fort(47 + CARAVAN_DAYS + 1, 320, 95))
        self.assertIsNone(ov.caravan)

    def test_the_same_report_is_not_taken_twice(self):
        ov, _ = overseer()
        ov.load(fort(45, 8, 40))
        ov.load(fort(47, 312, 90, [ARRIVE]))
        ov.load(fort(49, 100, 50, [ARRIVE]))                      # goods gone while the report is still listed
        ov.load(fort(51, 300, 90, [ARRIVE]))
        self.assertIsNone(ov.caravan)
        self.assertEqual(ov.st["food_edible"], 300)

    def test_no_stocks_no_change(self):
        ov, _ = overseer()
        r = fort(10, 30, 50)
        del r["observation"]["stocks"]["food_edible"]
        ov.load(r)
        self.assertIsNone(ov.prev_stock)


if __name__ == "__main__":
    unittest.main()
