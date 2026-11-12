"""cx cups (harness CUP_* / Overseer.cup_supply): a daily wooden MakeGoblet standing for DrinkWithoutCup.
No game or network is used."""
import copy
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
        self.n = 100

    def act(self, tool, args):
        self.calls.append((tool, copy.deepcopy(args)))
        self.n += 1
        return {"ok": True, "result": {"order_id": self.n}}


def facts(day=10, cit=20, logs=200, shops=("Carpenters",), orders=(), hands_off=None):
    return {"tick": day * harness.DAY, "day": day, "hands_off_in_days": hands_off, "observation": {
        "date": {"abs_tick": day * harness.DAY},
        "administrators": {"citizens": cit}, "map": {"sites": [
            {"id": "W1", "kind": "W", "x": 5, "y": 5, "z": 9, "w": 3, "h": 3}]},
        "workshops": [{"type": t, "built": True, "id": i} for i, t in enumerate(shops)],
        "orders": copy.deepcopy(list(orders)),
        "stocks": {"logs_usable": logs, "furniture_free": {}}}}


class CupSupply(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.game = FakeGame()
        self.ov = harness.Overseer(self.game)

    def run_pass(self, **kw):
        self.ov.load(facts(**kw))
        self.ov.count = 0
        self.ov.cup_supply()

    def tools(self):
        return [t for t, _ in self.game.calls]

    def test_builds_craftsdwarfs_first(self):
        self.run_pass()
        self.assertEqual(self.game.calls[0][0], "build_workshop")
        self.assertEqual(self.game.calls[0][1]["type"], "Craftsdwarfs")
        self.assertNotIn("add_manager_order", self.tools())

    def test_standing_order_shape(self):
        self.run_pass(shops=("Carpenters", "Craftsdwarfs"))
        (tool, args), = self.game.calls
        self.assertEqual(tool, "add_manager_order")
        self.assertEqual(args["job"], "MakeGoblet")
        self.assertEqual(args["material_category"], ["wood"])
        self.assertEqual(args["repeat"], "daily")
        self.assertEqual(args["amount"], harness.CUP_BATCH)
        conds = {c["item_type"]: c for c in args["when"]}
        self.assertEqual(conds["GOBLET"]["below"], 20 + harness.CUP_SPARE)
        self.assertEqual(conds["WOOD"]["at_least"], self.ov.logs_guard())
        # once placed, the next passes add nothing
        self.game.calls.clear()
        self.run_pass(day=11, shops=("Carpenters", "Craftsdwarfs"))
        self.assertEqual(self.game.calls, [])

    def test_waits_for_logs_guard_and_day_and_labs(self):
        self.run_pass(day=1, shops=("Craftsdwarfs",))
        self.run_pass(logs=0, shops=("Craftsdwarfs",))
        self.run_pass(shops=("Craftsdwarfs",), hands_off=30)
        self.assertEqual(self.game.calls, [])

    def test_existing_standing_is_left_alone(self):
        self.run_pass(shops=("Craftsdwarfs",), orders=[{"id": 7, "job": "MakeGoblet", "repeat": "Daily"}])
        self.assertEqual(self.game.calls, [])

    def test_census_growth_recuts(self):
        self.run_pass(shops=("Craftsdwarfs",))
        oid = self.ov.key_order["o_cups_prog"]
        self.game.calls.clear()
        self.run_pass(day=40, cit=28, shops=("Craftsdwarfs",),
                      orders=[{"id": oid, "job": "MakeGoblet", "repeat": "Daily"}])
        self.assertEqual(self.game.calls, [("cancel_order", {"order_id": oid})])
        self.game.calls.clear()
        self.run_pass(day=41, cit=28, shops=("Craftsdwarfs",))
        (tool, args), = self.game.calls
        self.assertEqual(tool, "add_manager_order")
        self.assertEqual({c["item_type"]: c for c in args["when"]}["GOBLET"]["below"], 28 + harness.CUP_SPARE)


class StressNoSite(unittest.TestCase):
    def test_no_site_is_logged_not_silent(self):
        game = FakeGame()
        ov = harness.Overseer(game)
        f = facts()
        f["observation"]["dwarves"] = [{"id": 326, "stress": 1, "name": "x"}]
        f["observation"]["map"]["sites"] = []
        buf = io.StringIO()
        with redirect_stdout(buf):
            ov.load(f)
            ov.count = 0
            ov.stress_housing()
            ov.stress_housing()   # once a week, not every pass
        self.assertEqual(game.calls, [])
        self.assertEqual(buf.getvalue().count('"stress_no_site"'), 1)


if __name__ == "__main__":
    unittest.main()
