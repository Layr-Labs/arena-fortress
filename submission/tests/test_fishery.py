"""Regressions for a Fishery when a citizen is fishing. No game or network is used."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"id": len(self.calls)}}


class Fishery(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, job="Fish", fishery=None, core=True):
        workshops = [{"type": t, "built": True} for t in ("Carpenters", "Still", "Kitchen")] if core else []
        if fishery is not None:
            workshops.append({"type": "Fishery", "built": fishery})
        game = FakeGame()
        overseer = harness.Overseer(game)
        overseer.load({"tick": 0, "observation": {
            "dwarves": [{"id": 87, "job": job, "profession": "Fisherdwarf"}],
            "stocks": {"logs_usable": 10}, "workshops": workshops,
            "map": {"sites": [{"id": "W" + str(i), "kind": "W", "x": 4*i, "y": 10, "z": 10}
                              for i in range(1, 5)]}}})
        overseer.count = 0
        return overseer, game

    def test_active_fishing_builds_missing_fishery(self):
        overseer, game = self.overseer()
        overseer.workshops()
        self.assertEqual(game.calls, [("build_workshop", {"type": "Fishery", "site": "W1"})])

    def test_fisher_profession_without_fish_job_does_not_build(self):
        overseer, game = self.overseer(job="idle")
        overseer.workshops()
        self.assertEqual(game.calls, [])

    def test_existing_fishery_does_not_build_again(self):
        overseer, game = self.overseer(fishery=True)
        overseer.workshops()
        self.assertEqual(game.calls, [])

    def test_planned_fishery_does_not_build_again(self):
        overseer, game = self.overseer(fishery=False)
        overseer.workshops()
        self.assertEqual(game.calls, [])

    def test_core_workshops_take_sites_before_fishery(self):
        overseer, game = self.overseer(core=False)
        overseer.workshops()
        self.assertEqual(game.calls, [
            ("build_workshop", {"type": "Carpenters", "site": "W1"}),
            ("build_workshop", {"type": "Still", "site": "W2"}),
            ("build_workshop", {"type": "Kitchen", "site": "W3"}),
            ("build_workshop", {"type": "Fishery", "site": "W4"})])
        self.assertEqual(overseer.kind("W"), [])


if __name__ == "__main__":
    unittest.main()
