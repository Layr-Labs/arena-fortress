"""Emergency brewing must not be blocked by idle conditional repeats."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer

class API:
    def __init__(self): self.calls = []
    def act(self, tool, args):
        self.calls.append((tool, args))
        return {"ok": True, "result": {"order_id": 99}}

class IdleBrew(unittest.TestCase):
    def layer(self, **order):
        api = API()
        layer = Overseer(api)
        layer.count = 0
        layer.load({"tick": 1200, "observation": {
            "administrators": {"citizens": 19},
            "stocks": {"drink": 0, "plants_brewable": 7, "barrels_empty": 3},
            "workshops": [{"type": "Still", "built": True}],
            "orders": [{"recipe": "brew_drink", "left": 1, "repeat": "daily",
                        "validated": True, "active": False, "jobs_in_progress": 0, **order}]}})
        return layer, api

    def check(self, pending, **order):
        layer, api = self.layer(**order)
        self.assertEqual(layer.brewing_pending(), pending)
        with contextlib.redirect_stdout(io.StringIO()): layer.floors()
        brewing = [args for tool, args in api.calls if args.get("recipe") == "brew_drink"]
        self.assertEqual(len(brewing), int(not pending))

    def test_idle_repeat_allows_emergency(self): self.check(False)
    def test_running_repeat_blocks_duplicate(self): self.check(True, active=True)
    def test_unvalidated_repeat_waits_for_manager(self): self.check(True, validated=False)
    def test_one_shot_waits_for_manager(self): self.check(True, repeat=None)
    def test_spawned_jobs_block_duplicate(self): self.check(True, left=0, jobs_in_progress=1)
    def test_unknown_active_fails_closed(self): self.check(True, active=None)
    def test_completed_one_shot_allows_emergency(self): self.check(False, repeat=None, left=0)
    def test_plenty_of_drink_does_not_brew(self):
        layer, api = self.layer()
        layer.st["drink"] = 100
        with contextlib.redirect_stdout(io.StringIO()): layer.floors()
        self.assertFalse(any(args.get("recipe") == "brew_drink" for _, args in api.calls))

if __name__ == '__main__': unittest.main()
