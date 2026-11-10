"""An accepted but suspended construction must not strand an unclaimed mood."""
import io
import unittest
from contextlib import redirect_stdout
import test_workshop_repair as repair
from overseer import harness


class MoodRecovery(unittest.TestCase):
    def setUp(self):
        quiet = redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def test_unclaimed_mood_can_replace_explicitly_suspended_workshop(self):
        helper = repair.WorkshopRepair()
        w = {"type": "Craftsdwarfs", "built": False,
             "job_details": [{"job": "ConstructBuilding", "suspended": True}]}
        guard, game = helper.guard([w])
        guard.o["moods"] = [{"mood": "Fey", "skill": "WOODCRAFT", "unit_id": 1}]
        guard.mood()
        self.assertEqual(game.calls, [])
        guard.now = 7 * harness.DAY
        guard.mood()
        self.assertEqual(game.calls, [("build_workshop", {"type": "Craftsdwarfs", "site": "W1"})])
        self.assertEqual(guard.workshop_replacements["Craftsdwarfs"], 1)

    def test_claimed_mood_does_not_request_a_replacement(self):
        helper = repair.WorkshopRepair()
        guard, game = helper.guard([helper.pending()])
        guard.o["moods"] = [{"mood": "Fey", "skill": "CARPENTRY", "claimed_building_id": 6}]
        guard.mood()
        guard.now = 100 * harness.DAY
        guard.mood()
        self.assertEqual(game.calls, [])


if __name__ == "__main__":
    unittest.main()
