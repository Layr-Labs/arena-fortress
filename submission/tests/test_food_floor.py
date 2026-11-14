"""Offline regressions for the full-year open-play bridge to the feast."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock

from support import DAY, HERD, overseer, resp
from overseer.openplay import FEAST_DAYS, FEAST_KEEP, FOOD_FLOOR_DAYS


class FoodFloor(unittest.TestCase):
    def setUp(self):
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def play(self, left=40, food=1, **kw):
        ov, game = overseer(resp(left, 336 - left, food=food, **kw))
        ov.provision()
        return ov, game

    def again(self, ov, left, food=1, **kw):
        ov.load(resp(left, 336 - left, food=food, **kw))
        ov.count = 0
        ov.provision()

    def test_standing_cook_accepts_meat_and_fat_without_ten_plants(self):
        plant_order = {"id": 9, "recipe": "cook_meal", "repeat": "daily", "when": [
            {"stock": "plants_total", "at_least": 10}]}
        ov, game = self.play(plants=0, orders=[plant_order])
        self.assertEqual(game.tools("add_order"), [{
            "recipe": "cook_meal", "amount": 2, "repeat": "daily", "when": [
                {"stock": "prepared_meals", "below": 20},
                {"stock": "food_edible", "at_least": 2}]}])
        order = dict(game.tools("add_order")[0], id=ov.food_floor_order)
        self.again(ov, 39, orders=[plant_order, order])
        self.assertEqual(len(game.tools("add_order")), 1)
        self.again(ov, 37, orders=[plant_order])
        self.assertEqual(len(game.tools("add_order")), 2)

    def test_boundaries_and_two_food_per_citizen(self):
        for left, food, cit, active in (
                (FOOD_FLOOR_DAYS + 1, 1, 10, False),
                (FOOD_FLOOR_DAYS, 19, 10, True),
                (FEAST_DAYS + 1, 19, 10, True),
                (40, 20, 10, False), (40, 21, 10, False),
                (40, 39, 20, True), (40, 40, 20, False)):
            with self.subTest(left=left, food=food, cit=cit):
                _, game = self.play(left=left, food=food, cit=cit)
                self.assertEqual(bool(game.tools("add_order")), active)
                if not active and left <= FOOD_FLOOR_DAYS:
                    self.assertEqual(game.calls, [])

    def test_full_year_scope_uses_task_days(self):
        for days, active in ((None, False), (0, False), (216, False), (335, False),
                             (336, True), (672, True)):
            with self.subTest(days=days):
                ov, game = overseer(resp(40, 296, food=1))
                ov.days = days
                ov.provision()
                self.assertEqual(bool(game.tools("add_order")), active)

    def test_lab_and_hands_off_do_not_run_the_step(self):
        for lab, hands_off in ((True, None), (False, 20), (True, 0)):
            with self.subTest(lab=lab, hands_off=hands_off):
                ov, _ = overseer(resp(40, 296, food=1, hands_off=hands_off))
                ov.lab = lab
                ov.provision = Mock()
                for name in ("mood", "defend", "management", "workshops", "digging", "farms", "supply",
                             "furnish", "rezone", "closer", "progression_push"):
                    setattr(ov, name, Mock())
                ov.plan()
                ov.provision.assert_not_called()

    def test_one_small_animal_every_five_days_and_no_pets_or_wildlife(self):
        ov, game = self.play(food=0)
        self.assertEqual(game.tools("slaughter"), [{"unit_id": 1}])
        game.herd = [a for a in HERD if a["id"] != 1]
        for left in (40, 39, 38, 37, 36):
            self.again(ov, left, food=0)
        self.assertEqual(game.tools("slaughter"), [{"unit_id": 1}])
        self.again(ov, 35, food=0)
        self.assertEqual(game.tools("slaughter"), [{"unit_id": 1}, {"unit_id": 8}])
        game.herd = [a for a in game.herd if a["id"] != 8]
        for left in (30, 25, 20, 15):
            self.again(ov, left, food=0)
        self.assertEqual(len(game.tools("slaughter")), 2)
        self.assertFalse({2, 3, 4, 5, 6, 7} & {a["unit_id"] for a in game.tools("slaughter")})
        self.assertEqual(FEAST_KEEP, 3)

    def test_reserve_survives_at_zero_for_small_herds(self):
        for count in range(4):
            with self.subTest(count=count):
                herd = [a for a in HERD if a["id"] in (2, 4, 7)][:count]
                ov, game = overseer(resp(40, 296, food=0), herd=herd)
                ov.provision()
                self.assertEqual(game.tools("slaughter"), [])

    def test_existing_hunger_timestamp_limits_the_first_floor_cull(self):
        ov, game = overseer(resp(40, 296, food=0))
        ov.culled["hunger"] = 295 * DAY
        ov.provision()
        self.assertEqual(game.tools("slaughter"), [])
        self.again(ov, 36, food=0)
        self.assertEqual(game.tools("slaughter"), [{"unit_id": 1}])

    def test_refused_cook_is_retried_and_query_failure_does_not_crash(self):
        ov, game = overseer(resp(40, 296, food=0), refuse={("add_order", None)}, query_error=True)
        ov.provision()
        self.assertFalse(hasattr(ov, "food_floor_order"))
        self.assertEqual(game.tools("slaughter"), [])
        game.refuse.clear()
        game.query_error = False
        self.again(ov, 37, food=0)
        self.assertIsNotNone(ov.food_floor_order)
        self.assertEqual(game.tools("slaughter"), [{"unit_id": 1}])

    def test_feast_takes_the_reserved_animals_and_keeps_its_original_actions(self):
        herd = [a for a in HERD if a["id"] in (2, 4, 7)]
        ov, game = overseer(resp(15, 321, food=0), herd=herd)
        ov.provision()
        self.assertEqual(game.tools("slaughter"), [])
        game.calls.clear()
        self.again(ov, FEAST_DAYS, food=0)
        self.assertEqual(game.tools("slaughter"), [{"unit_id": 2}, {"unit_id": 4}, {"unit_id": 7}])
        self.assertEqual(game.tools("add_order"), [])
        self.assertFalse(ov.brew_stopped)
        for left in (FEAST_DAYS, 1, 0):
            _, fresh_game = self.play(left=left, food=0)
            self.assertEqual(fresh_game.tools("add_order"), [])

    def test_new_step_does_not_change_brewing_alerts_or_locks(self):
        ov, game = self.play(food=0, drink=10000)
        self.assertEqual({tool for tool, _ in game.calls}, {"add_order", "slaughter"})
        self.assertFalse(ov.brew_stopped)
        self.assertEqual(ov.own_locks, set())
        self.assertIsNone(ov.lock)


if __name__ == "__main__":
    unittest.main()
