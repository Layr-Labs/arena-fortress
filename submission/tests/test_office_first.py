"""Immediate office furnishing must precede other migrant furniture requests."""
import unittest
import test_surge_port as fixtures


class OfficeFirst(unittest.TestCase):
    def make(self, surge=True, replies=None, chairs=12):
        helper = fixtures.SurgePort()
        controller, game = helper.make(surge=surge, replies=replies)
        controller.adm["manager_office"] = "none"
        controller.free["chair"] = chairs
        return helper, controller, game

    def test_chair_follows_new_office_on_the_same_site(self):
        helper, controller, game = self.make()
        helper.invoke(controller, "office")
        self.assertEqual(game.calls, [("make_zone", {"kind": "office", "site": "A1"}),
                                      ("place_furniture", {"kind": "chair", "site": "A1"})])

    def test_ordinary_task_keeps_original_sequence(self):
        helper, controller, game = self.make(surge=False)
        helper.invoke(controller, "office")
        self.assertEqual(game.calls, [("make_zone", {"kind": "office", "site": "A1"})])

    def test_rejected_zone_does_not_place_chair(self):
        helper, controller, game = self.make(replies={"make_zone": [{"ok": False, "error_code": "no_space"}]})
        helper.invoke(controller, "office")
        self.assertEqual(len(game.calls), 1)

    def test_no_free_chair_does_not_place_chair(self):
        helper, controller, game = self.make(chairs=0)
        helper.invoke(controller, "office")
        self.assertEqual(len(game.calls), 1)

    def test_suppressed_zone_request_does_not_duplicate_chair(self):
        helper, controller, game = self.make()
        helper.invoke(controller, "office")
        helper.invoke(controller, "office")
        self.assertEqual(len(game.calls), 2)
