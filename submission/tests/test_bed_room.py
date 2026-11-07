"""Check first dormitory dig size with offline responses only."""
import io
from contextlib import redirect_stdout
import unittest

from test_brew_growth import public_task
from test_repairs import FakeGame, facts, harness, room


class BedRoom(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def agent(self, goal=True, soil=False, failures=0, roles=None, pending=0):
        game = FakeGame(failures)
        agent = harness.Overseer(game)
        agent.set_task(public_task("lt08-migrant-surge.json" if goal else "op1-start-year.json"))
        resp = facts([room(soil)])
        resp["observation"]["dig_designations_pending"] = pending
        agent.load(resp)
        agent.count = 0
        agent.roles = dict(roles or {})
        return agent, game

    def test_public_bed_goal_uses_larger_first_dormitory_dig(self):
        agent, game = self.agent()
        self.assertTrue(agent.beds_first)
        agent.digging()
        self.assertEqual(game.calls, [("dig_room", {"site": "R1", "w": 11, "h": 9})])
        self.assertEqual(agent.roles, {"R1": "dorm"})
        agent.now = 3 * harness.DAY
        agent.digging()
        self.assertEqual(len(game.calls), 1)

    def test_normal_goal_keeps_existing_dormitory_dimensions(self):
        agent, game = self.agent(goal=False)
        self.assertFalse(agent.beds_first)
        agent.digging()
        self.assertEqual(game.calls, [("dig_room", {"site": "R1", "w": 9, "h": 7})])
        self.assertEqual(agent.roles, {"R1": "dorm"})

    def test_farm_dining_and_office_sizes_do_not_change(self):
        for goal in (False, True):
            for role, soil, roles, expected in (
                    ("farm", True, {}, {"site": "R1"}),
                    ("dine", False, {"R0": "dorm"}, {"site": "R1", "w": 7, "h": 5}),
                    ("office", False, {"R0": "dorm", "R2": "dine"}, {"site": "R1"})):
                with self.subTest(goal=goal, role=role):
                    agent, game = self.agent(goal=goal, soil=soil, roles=roles)
                    agent.digging()
                    self.assertEqual(game.calls, [("dig_room", expected)])
                    self.assertEqual(agent.roles, {**roles, "R1": role})

    def test_failed_and_retry_blocked_digs_keep_role_free(self):
        agent, game = self.agent(failures=1)
        agent.digging()
        self.assertEqual(agent.roles, {})
        self.assertEqual(agent.tries["dig_R1"], 1)
        agent.now = 2 * harness.DAY
        agent.digging()
        self.assertEqual(agent.roles, {})
        self.assertEqual(len(game.calls), 1)
        agent.now = 3 * harness.DAY
        agent.digging()
        self.assertEqual(game.calls, [("dig_room", {"site": "R1", "w": 11, "h": 9})] * 2)
        self.assertEqual(agent.roles, {"R1": "dorm"})
        self.assertEqual(agent.tries["dig_R1"], 1)

    def test_failed_bed_goal_digs_keep_existing_two_failure_limit(self):
        agent, game = self.agent(failures=2)
        for day in (0, 3, 6):
            agent.now = day * harness.DAY
            agent.digging()
        self.assertEqual(len(game.calls), 2)
        self.assertEqual(agent.tries["dig_R1"], 2)
        self.assertEqual(agent.roles, {})

    def test_pending_dig_gate_prevents_new_dormitory_dig(self):
        agent, game = self.agent(pending=91)
        agent.digging()
        self.assertEqual(game.calls, [])
        self.assertEqual(agent.roles, {})


if __name__ == "__main__":
    unittest.main()
