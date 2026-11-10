"""Housing must remain possible when farms consume every available soil-room candidate."""
import io
from contextlib import redirect_stdout
import unittest
from overseer.harness import Overseer


class Game:
    def __init__(self, reject=False):
        self.calls = []
        self.reject = reject

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": not self.reject, "error_code": "no_space" if self.reject else None}


class Capacity(unittest.TestCase):
    def plan(self, goal, reject=False):
        game = Game(reject)
        layer = Overseer(game, goal=goal)
        layer.count = 0
        layer.load({"day": 0, "tick": 0, "observation": {
            "administrators": {"citizens": 38}, "farm_plots": [{"id": 1}, {"id": 2}],
            "map": {"sites": [{"id": "R1", "kind": "R", "soil": True,
                                "x": 10, "y": 10, "z": 9, "w": 3, "h": 3}]}}})
        with redirect_stdout(io.StringIO()):
            layer.digging()
        return game, layer

    def test_migrant_room_precedes_farm_and_has_space_for_shared_furniture(self):
        game, layer = self.plan("Migrants are arriving")
        self.assertEqual(layer.roles, {"R1": "dorm"})
        args = game.calls[0][1]
        self.assertGreaterEqual(args["w"] * args["h"], 2 * layer.bed_target() + 12)
        self.assertLessEqual(max(args["w"], args["h"]), 15)

    def test_other_tasks_keep_farms_first(self):
        game, layer = self.plan("Keep drink flowing")
        self.assertEqual(layer.roles, {"R1": "farm"})
        self.assertEqual(game.calls[0][1], {"site": "R1"})

    def test_failed_reservation_does_not_claim_room(self):
        _, layer = self.plan("Migrants are arriving", reject=True)
        self.assertEqual(layer.roles, {})


if __name__ == "__main__":
    unittest.main()
