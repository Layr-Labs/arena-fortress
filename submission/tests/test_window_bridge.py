"""cx lt08drink: the surge's window brew bridge (harness.window_bridge, SURGE_BRIDGE_RATE / SURGE_WINDOW_USE). The eve's
o_brew_win (d32-38) waits for the manager's next look (7be81c2 hard LT08-2: added d36, validated d40.5) and drink[H] <
drink[A] in 12 of 33 LT08 records; the bridge goes on the book at the start of the window prep so a look before A
validates it, capped at the projected drink[A] so it brews nothing before the window. No game or network."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_surge_floor import Base, harness  # noqa: E402


def bridges(game):
    return [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"
            and "drink" in [w.get("stock") for w in a.get("when") or []]]


class WindowBridge(Base):
    def test_prep_start_adds_the_capped_bridge(self):
        # 7be81c2 hard LT08-2 at d25: 47 citizens, drink 533 (drink[A] was 488)
        o, game = self.ov(hands_off=14, cit=47, stocks={"drink": 533}, day=25)
        o.closer()
        b = bridges(game)
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0]["repeat"], "daily")
        self.assertEqual(b[0]["when"], [{"stock": "drink", "below": 486},   # 533 - 0.071*47*14 = 486 <= 488
                                        {"stock": "plants_brewable", "at_least": 2},
                                        {"stock": "food_edible", "at_least": 23}])
        self.assertEqual(b[0]["amount"], 2)   # need ceil(0.049*47*21/5) = 10 brews; 3x a day's share -> 2

    def test_the_cap_never_lies_above_drink_a_in_the_failing_records(self):
        # (drink d25, citizens, drink[A]) of the records whose drink[H] < drink[A]
        for d25, cit, a in ((533, 47, 488), (532, 48, 484), (530, 47, 483), (535, 43, 492), (565, 48, 523),
                            (533, 45, 498), (532, 45, 487)):
            with self.subTest(d25=d25):
                o, game = self.ov(hands_off=14, cit=cit, stocks={"drink": d25}, day=25)
                o.window_bridge()
                self.assertLessEqual(bridges(game)[0]["when"][0]["below"], a)

    def test_added_once_per_game(self):
        o, game = self.ov(hands_off=14, stocks={"drink": 533}, day=25)
        o.closer()
        o.load(__import__("test_surge_floor").obs(hands_off=8, stocks={"drink": 520}, day=31))
        o.count = 0
        o.closer()
        self.assertEqual(len(bridges(game)), 1)

    def test_sized_by_the_window_and_the_census(self):
        o, game = self.ov(hands_off=14, cit=90, stocks={"drink": 700}, day=25)
        o.window_bridge()
        self.assertEqual(bridges(game)[0]["amount"], 3)   # ceil(0.049*90*21/5) = 19 brews -> ceil(57/21) = 3
        o2, game2 = self.ov(hands_off=14, cit=10, stocks={"drink": 300}, day=25)
        o2.window_bridge()
        self.assertEqual(bridges(game2)[0]["amount"], 2)

    def test_not_before_prep_nor_in_other_shapes(self):
        o, game = self.ov(hands_off=20)
        o.closer()
        self.assertEqual(bridges(game), [])
        o2, game2 = self.ov(surge=False)
        o2.window_bridge()
        self.assertEqual(bridges(game2), [])

    def test_the_window_hold_keeps_the_bridge(self):
        o, game = self.ov(hands_off=10, stocks={"drink": 520})
        o.key_order["o_brew_bridge_win"] = 77
        o.orders = [{"id": 77, "recipe": "brew_drink", "repeat": "daily",
                     "when": [{"item_type": "DRINK", "test": "LessThan", "value": 999, "stock": "drink"}]}]
        o.surge_window_hold()
        self.assertNotIn(("cancel_order", {"order_id": 77}), game.calls)


if __name__ == "__main__":
    unittest.main()
