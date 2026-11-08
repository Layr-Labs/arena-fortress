"""The bed-placement fallback: beds that don't fit the dorm room are placed on a spare level, and a full room is
not mistaken for a done job. No game or network is used."""
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
    """Bed tiles per site: the dorm room (A1) has two, a spare area (A2) has three. `room_fit` caps how many tiles
    any single call will yield, whatever the request."""

    def __init__(self, a1=2, a2=3, room_fit=None):
        self.tiles = {"A1": [[11, 11, 9], [12, 11, 9]][:a1], "A2": [[20, 20, 9], [21, 20, 9], [22, 20, 9]][:a2]}
        self.room_fit = room_fit
        self.calls = []
        self.placed_at = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if tool == "make_zone":
            return {"ok": True, "result": {"zone_id": len(self.calls)}}
        pool = self.tiles.get(args.get("site"), [])
        want = min(args.get("count", 1), len(pool), self.room_fit if self.room_fit is not None else 30)
        if not want:
            return {"ok": False, "error_code": "no_space"}
        at = [pool.pop(0) for _ in range(want)]
        self.placed_at.extend(at)
        return {"ok": True, "result": {"n": want, "at": at[0] if want == 1 else at}}


def site(id, x=10, y=10, z=9, w=9, h=7, open_tiles=40, **kw):
    return {"id": id, "kind": id[0], "x": x, "y": y, "z": z, "w": w, "h": h, "open_tiles": open_tiles, **kw}


def facts(sites, zones=(), furniture=(), free=None):
    return {"tick": 0, "observation": {
        "administrators": {"citizens": 6}, "map": {"sites": copy.deepcopy(sites)},
        "zones": copy.deepcopy(list(zones)), "furniture": copy.deepcopy(list(furniture)),
        "stocks": {"furniture_free": free if free is not None else {"bed": 10}}}}


class BedFallback(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def agent(self, sites, game):
        agent = harness.Overseer(game)
        agent.count = 0
        agent.load(facts(sites))
        return agent

    def bed_sites(self, game):
        return [a["site"] for t, a in game.calls if t == "place_furniture" and a["kind"] == "bed"]

    def test_beds_go_to_a_spare_level_when_the_room_fills(self):
        game = FakeGame()
        agent = self.agent([site("A1"), site("A2", z=8)], game)
        agent.furnish()
        self.assertEqual(self.bed_sites(game), ["A1", "A2"])   # second batch falls through to the spare level
        self.assertEqual(agent.placed.get("bed", 0), 0)        # nothing placed yet: only the queue moved

    def test_no_spare_level_leaves_the_batch_at_the_intended_room(self):
        game = FakeGame(a2=0)
        agent = self.agent([site("A1")], game)
        agent.furnish()
        self.assertEqual(self.bed_sites(game), ["A1"])

    def test_a_full_room_then_a_spare_one_covers_the_shortfall(self):
        game = FakeGame(room_fit=2)                            # every room yields only two beds per call
        agent = self.agent([site("A1"), site("A2", z=8)], game)
        agent.furnish()
        self.assertGreaterEqual(len(self.bed_sites(game)), 2)  # the room, then the spare level
        self.assertGreaterEqual(len(game.placed_at), 3)        # 2 from the room plus at least 1 from the spare

    def test_place_reports_a_shortfall_as_short_not_failed(self):
        game = FakeGame(a1=1)
        agent = self.agent([site("A1")], game)
        agent.load(facts([site("A1")]))
        _spots, err, short = agent.place("beds", "bed", site("A1"), 5)
        self.assertIsNone(err)
        self.assertTrue(short)


if __name__ == "__main__":
    unittest.main()
