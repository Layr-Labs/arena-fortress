"""Cut 9: on a migrant task every free bed up to bed_target() is placed before the hands-off window (a second wave
can arrive inside it, when nothing can be placed). Other tasks keep the base's citizens + 2. No game or network."""
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

SURGE_GOAL = ("Migrants are arriving. From day 39 you can't act for 21 days. By day 60 every dwarf must have a placed "
              "bed, drink and food must be in stock every day from day 39.")


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, copy.deepcopy(args)))
        if tool == "place_furniture":
            n = int(args.get("count") or 1)
            return {"ok": True, "result": {"n": n, "at": [[11 + i % 6, 11 + i // 6, 9] for i in range(n)]}}
        return {"ok": True, "result": {"zone_id": len(self.calls)}}


def facts(cit, free_beds, placed_beds=0):
    furniture = [{"id": 700 + i, "kind": "bed", "x": 11, "y": 11, "z": 9, "built": True, "zone_ids": [1]}
                 for i in range(placed_beds)]
    return {"tick": 0, "day": 20, "days_left": 40, "hands_off_in_days": 19, "observation": {
        "administrators": {"citizens": cit}, "map": {"sites": [
            {"id": "A1", "kind": "A", "x": 10, "y": 10, "z": 9, "w": 12, "h": 10, "open_tiles": 100}]},
        "zones": [{"id": 1, "type": "Dormitory", "x": 10, "y": 10, "z": 9, "w": 12, "h": 10}],
        "furniture": furniture, "stocks": {"furniture_free": {"bed": free_beds}}}}


class SurgeBeds(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def beds_placed(self, goal, cit, free_beds, placed_beds=0):
        game = FakeGame()
        o = harness.Overseer(game, goal=goal, days=60)
        o.load(facts(cit, free_beds, placed_beds))
        o.count = 0
        o.furnish()
        return sum(a.get("count", 1) for t, a in game.calls if t == "place_furniture" and a.get("kind") == "bed")

    def test_surge_target_has_the_wave_margin(self):
        o = harness.Overseer(FakeGame(), goal=SURGE_GOAL, days=60)
        o.load(facts(30, 0))
        self.assertEqual(o.bed_target(), 30 + harness.SURGE_BEDS)
        self.assertEqual(harness.SURGE_BEDS, 20)

    def test_surge_places_every_free_bed_up_to_the_target(self):
        # 30 citizens after the first wave, 45 free beds: up to 50 placed in passes of at most 30 (the base stopped at 32)
        self.assertEqual(self.beds_placed(SURGE_GOAL, 30, 45), 30)        # one pass places at most 30
        self.assertEqual(self.beds_placed(SURGE_GOAL, 30, 45, placed_beds=30), 20)    # up to 50

    def test_surge_stops_at_the_target(self):
        self.assertEqual(self.beds_placed(SURGE_GOAL, 30, 60, placed_beds=40), 10)   # 50 - 40
        self.assertEqual(self.beds_placed(SURGE_GOAL, 30, 60, placed_beds=50), 0)

    def test_other_tasks_keep_citizens_plus_two(self):
        self.assertEqual(self.beds_placed("Keep the fortress alive for a year.", 30, 45, placed_beds=20), 12)
        self.assertEqual(self.beds_placed("", 7, 20), 9)


if __name__ == "__main__":
    unittest.main()
