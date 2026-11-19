"""Full-year embarks brew without a drink ceiling and keep a few plants as food (Overseer.supply)."""
import unittest

from support import StubGame, overseer, resp
from overseer.harness import BREW_KEEP, DRINK_CAP, Overseer


def brews(g):
    return [a for a in g.tools("add_order") if a.get("recipe") == "brew_drink"]


class BrewKeep(unittest.TestCase):
    def test_a_full_year_embark_has_no_drink_ceiling(self):
        ov, g = overseer(resp(300, 36, food=20, drink=400))
        ov.supply()
        (o,) = brews(g)
        self.assertEqual(o["when"], [{"stock": "plants_brewable", "at_least": BREW_KEEP},
                                     {"stock": "barrels_empty", "at_least": 1}])

    def test_a_shorter_game_keeps_the_ceiling(self):
        g = StubGame()
        ov = Overseer(g, goal="Run the fortress", days=216)
        ov.set_task({"goal": "Run the fortress for 216 days."})
        ov.load(resp(200, 16, food=20, drink=400))
        ov.count = 0
        ov.supply()
        (o,) = brews(g)
        self.assertEqual(o["when"][0], {"stock": "drink", "below": DRINK_CAP})
        self.assertEqual(o["when"][1], {"stock": "plants_brewable", "at_least": 2})


ORDER = {"id": 7, "recipe": "brew_drink", "repeat": "daily", "left": 3}


def stretch(days, drink, cit=10):
    g = StubGame()
    ov = Overseer(g, goal="Run the fortress", days=days)
    ov.set_task({"goal": "Run the fortress for %d days." % days})
    ov.load(resp(25, days - 25, food=40, drink=drink, cit=cit, orders=[ORDER]))
    ov.count = 0
    ov.brew_own = {7}
    return ov, g


class BrewRest(unittest.TestCase):
    def test_a_full_year_embark_stops_brewing_for_the_whole_scored_stretch(self):
        ov, g = stretch(336, drink=300)
        ov.provision()
        self.assertEqual(g.tools("cancel_order"), [{"order_id": 7}])
        self.assertTrue(ov.brew_stopped)

    def test_it_stops_at_the_reopen_level_once(self):
        """Seen in game: 20 dwarves with 461 drink (23 each) kept brewing to the horizon, the plants went into
        drink and food stood at 0 for three days before the feast's meat landed."""
        ov, g = stretch(336, drink=460, cit=20)
        ov.provision()
        self.assertEqual(g.tools("cancel_order"), [{"order_id": 7}])
        self.assertTrue(ov.brew_stopped)

    def test_not_while_drink_is_under_the_reopen_level(self):
        ov, g = stretch(336, drink=210)
        ov.provision()
        self.assertEqual(g.tools("cancel_order"), [])
        self.assertFalse(ov.brew_stopped)

    def test_once_reopened_it_brews_up_to_the_safe_level(self):
        ov, g = stretch(336, drink=230)
        ov.provision()
        self.assertTrue(ov.brew_stopped)
        ov.load(resp(22, 314, food=40, drink=215, orders=[]))
        ov.provision()
        self.assertFalse(ov.brew_stopped)
        ov.brew_own = {8}
        ov.load(resp(20, 316, food=40, drink=240, orders=[dict(ORDER, id=8)]))
        ov.provision()
        self.assertFalse(ov.brew_stopped)                       # 24 each: over the reopen level, under the safe one
        ov.load(resp(18, 318, food=40, drink=285, orders=[dict(ORDER, id=8)]))
        ov.provision()
        self.assertTrue(ov.brew_stopped)

    def test_the_feast_of_a_full_year_embark_stops_at_the_reopen_level_too(self):
        ov, g = stretch(336, drink=230)
        ov.load(resp(12, 324, food=40, drink=230, orders=[ORDER]))
        ov.feast()
        self.assertTrue(ov.brew_stopped)

    def test_the_feast_of_a_shorter_game_keeps_the_safe_level(self):
        ov, g = stretch(216, drink=230)
        ov.load(resp(12, 204, food=40, drink=230, orders=[ORDER]))
        ov.feast()
        self.assertFalse(ov.brew_stopped)

    def test_a_shorter_game_brews_on_until_the_feast(self):
        ov, g = stretch(216, drink=300)
        ov.provision()
        self.assertEqual(g.tools("cancel_order"), [])


if __name__ == "__main__":
    unittest.main()
