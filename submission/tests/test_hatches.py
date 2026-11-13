"""Hatch covers: ordered on a hostile report, placed when invaders are near, locked under the alert, unlocked after."""
import io
import unittest
from contextlib import redirect_stdout
from overseer.harness import Overseer, DAY


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args))
        return {"ok": True, "result": {"order_id": len(self.calls)}}


def obs(free=0, hatches=(), alert=False, logs=10):
    return {"tick": 40 * DAY, "day": 40, "observation": {
        "administrators": {"citizens": 20}, "stocks": {"logs_usable": logs, "logs": logs},
        "doors": {"list": list(hatches), "hatch_cover_items_free": free},
        "burrows": {"civilian_alert": alert, "list": []},
        "map": {"sites": [{"id": "E1", "kind": "E", "free": True, "x": 1, "y": 1, "z": 100}, {"id": "E2", "kind": "E", "free": True, "x": 2, "y": 1, "z": 100}]}}}


class Hatches(unittest.TestCase):
    def run_hatches(self, ov, resp, invaders, near, alert):
        ov.load(resp)
        ov.count = 0
        with redirect_stdout(io.StringIO()):
            ov.hatches(invaders, near, alert)

    def test_cycle(self):
        g = FakeGame()
        ov = Overseer(g, goal="", days=336)
        ov.hostile_at = 39 * DAY
        self.run_hatches(ov, obs(), [], False, False)
        self.assertIn(("add_order", {"recipe": "make_hatch_cover", "amount": 2}), g.calls)
        self.run_hatches(ov, obs(free=2), [{"invader": True}], True, False)
        self.assertEqual([a["site"] for t, a in g.calls if t == "build_door"], ["E1", "E2"])
        h = [{"id": i, "kind": "hatch", "built": True, "x": x, "y": 1, "z": 100}
             for i, x in [(5, 1), (6, 2)]]
        self.run_hatches(ov, obs(hatches=h, alert=True), [{"invader": True}], True, True)
        self.assertEqual(g.calls[-1], ("lock_door", {"locked": True, "door_id": 6}))
        self.assertTrue(ov.locked)
        ov.now += 2 * DAY
        self.run_hatches(ov, obs(hatches=h, alert=False), [], False, False)
        self.assertEqual(g.calls[-1], ("lock_door", {"locked": False, "door_id": 6}))
        self.assertFalse(ov.locked)

    def test_quiet_fort_does_nothing(self):
        g = FakeGame()
        ov = Overseer(g, goal="", days=336)
        self.run_hatches(ov, obs(), [], False, False)
        self.assertEqual(g.calls, [])


if __name__ == "__main__":
    unittest.main()
