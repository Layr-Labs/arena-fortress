"""The final-stretch brew order (Overseer.endgame_supply, o_brew_final)."""
import unittest

from support import overseer, resp


def brew_orders(g):
    return [a for a in g.tools("add_order") if a.get("recipe") == "brew_drink"]


class FinalBrew(unittest.TestCase):
    def test_in_the_final_stretch_drink_is_brewed_from_two_plants_unless_food_is_short(self):
        ov, g = overseer(resp(28, 308, food=40, drink=328, cit=19))
        ov.endgame_supply()
        final = [a for a in brew_orders(g) if {"stock": "plants_brewable", "at_least": 2} in a["when"]]
        self.assertEqual(len(final), 1)
        self.assertIn({"stock": "food_edible", "at_least": 19}, final[0]["when"])
        self.assertEqual(final[0]["repeat"], "daily")

    def test_not_before_the_final_stretch(self):
        ov, g = overseer(resp(50, 286, food=40, drink=328, cit=19))
        ov.endgame_supply()
        self.assertFalse([a for a in brew_orders(g) if {"stock": "plants_brewable", "at_least": 2} in a["when"]])

    def test_not_while_the_feast_has_stopped_brewing(self):
        ov, g = overseer(resp(10, 326, food=40, drink=600, cit=19))
        ov.brew_stopped = True
        ov.endgame_supply()
        self.assertEqual(brew_orders(g), [])

    def test_not_on_a_lab_task(self):
        ov, g = overseer(resp(20, 40, food=40, drink=100, cit=19, hands_off=5))
        ov.endgame_supply()
        self.assertFalse([a for a in brew_orders(g) if {"stock": "plants_brewable", "at_least": 2} in a["when"]])


if __name__ == "__main__":
    unittest.main()
