"""A refused excavation cannot reserve a room's role or prevent a bounded retry.

Uses the public dig_room refusal shape; no DF or network is needed.
"""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer.harness import DAY, Overseer


class Game:
    def __init__(self, failures=1):
        self.failures = failures
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        if self.failures:
            self.failures -= 1
            return {"ok": False, "error_code": "nothing_designated",
                    "error": "1 step(s) designated nothing at 10,10,9",
                    "steps": [{"at": "10,10,9", "tiles": 0}]}
        return {"ok": True, "result": {"designated": 9}}


def facts(day, soil):
    return {"day": day, "tick": day * DAY, "observation": {
        "administrators": {"citizens": 7}, "stocks": {},
        "map": {"surface_z": 10, "sites": [
            {"id": "R1", "kind": "R", "x": 10, "y": 10, "z": 9,
             "w": 3, "h": 3, "soil": soil, "free": True,
             "designated": False, "dug": False}]}}}


class DigRetries(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, role, failures=1):
        game = Game(failures)
        overseer = Overseer(game)
        # Earlier accepted rooms make each of the ordinary room roles next.
        rooms = ("dorm", "dine", "office")
        preceding = rooms[:rooms.index(role)] if role in rooms else ()
        overseer.roles = {"old_" + r: r for r in preceding}
        overseer.count = 0
        return overseer, game

    def test_refused_dig_retries_after_delay_and_assigns_only_on_acceptance(self):
        for role in ("farm", "dorm", "dine", "office"):
            with self.subTest(role=role):
                overseer, game = self.overseer(role)
                initial_roles = dict(overseer.roles)
                overseer.load(facts(0, role == "farm"))
                overseer.digging()
                self.assertEqual(overseer.roles, initial_roles)
                self.assertEqual(overseer.tries["dig_R1"], 1)
                overseer.load(facts(2, role == "farm"))
                overseer.digging()
                self.assertEqual(len(game.calls), 1)
                overseer.load(facts(3, role == "farm"))
                overseer.digging()
                self.assertEqual(len(game.calls), 2)
                self.assertEqual(overseer.roles, {**initial_roles, "R1": role})
                overseer.load(facts(6, role == "farm"))
                overseer.digging()
                self.assertEqual(len(game.calls), 2)

    def test_repeated_refusals_keep_existing_two_attempt_limit(self):
        for role in ("farm", "dorm", "dine", "office"):
            with self.subTest(role=role):
                overseer, game = self.overseer(role, failures=3)
                initial_roles = dict(overseer.roles)
                for day in (0, 3, 6):
                    overseer.load(facts(day, role == "farm"))
                    overseer.digging()
                self.assertEqual(len(game.calls), 2)
                self.assertEqual(overseer.tries["dig_R1"], 2)
                self.assertEqual(overseer.roles, initial_roles)

    def test_successful_dig_keeps_original_dimensions_and_role(self):
        for role, size in (("farm", {}), ("dorm", {"w": 9, "h": 7}),
                           ("dine", {"w": 7, "h": 5}), ("office", {})):
            with self.subTest(role=role):
                overseer, game = self.overseer(role, failures=0)
                overseer.load(facts(0, role == "farm"))
                overseer.digging()
                self.assertEqual(game.calls, [("dig_room", {"site": "R1", **size})])
                self.assertEqual(overseer.roles["R1"], role)


if __name__ == "__main__":
    unittest.main()
