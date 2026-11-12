"""cx rock dorm (hint std LT08-2 on b167a15, 2026-11-12: beds 20 for 45). The 150 runs on that fort got their second
dorm R3 at (90,97) — rock, no F site — from the S6 stair dug on day 3; on b167a15 every listed room from day 4 was soil
(R1 88,104; R2 94,93 by the S4 stair), R2 became the dorm and plots took it. Owner ruling: a new surface stair under
exactly the shelter shaft's conditions while every room is soil; rock rooms first for the dorm. Shapes are the
record's day-4 observation. No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness
from test_cx_alloc import FakeGame, resp

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

R1 = {"id": "R1", "kind": "R", "x": 88, "y": 104, "z": 104, "w": 3, "h": 3, "soil": True, "dug": True,
      "designated": True, "stair": {"x": 91, "y": 105}, "free": False, "used_by": ["Office 11"]}
R2 = {"id": "R2", "kind": "R", "x": 94, "y": 93, "z": 104, "w": 3, "h": 3, "soil": True, "dug": False,
      "designated": False, "stair": {"x": 97, "y": 94}, "free": True}
R3 = {"id": "R3", "kind": "R", "x": 90, "y": 97, "z": 104, "w": 3, "h": 3, "soil": False, "dug": False,
      "designated": False, "stair": {"x": 93, "y": 98}, "free": True}
A1 = {"id": "A1", "kind": "A", "x": 83, "y": 67, "z": 104, "w": 41, "h": 44, "open_tiles": 80}
S = [{"id": i, "kind": "S", "x": x, "y": y, "z": 105, "w": 1, "h": 1, "soil": True}
     for i, (x, y) in (("S1", (93, 94)), ("S2", (93, 96)), ("S3", (95, 100)), ("S6", (93, 98)))]


class Base(unittest.TestCase):
    def setUp(self):
        out = redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def ov(self, sites=(R1, R2, A1) + tuple(S), surge=True, placed=19, beds_free=0, spare=1, zones=()):
        game = FakeGame()
        ov = harness.Overseer(game, goal="Migrants are arriving." if surge else "", days=60)
        r = resp(day=4, days=60, cit=36, drink=560, hands_off=35 if surge else None,
                 extra={"map": {"sites": [dict(s) for s in sites]}, "zones": list(zones),
                        "dig_designations_pending": 0})
        r["observation"]["stocks"]["furniture_free"] = {"bed": beds_free}
        ov.load(r)
        ov.count = 0
        ov.placed = {"bed": placed}
        ov.mig_waves = 1   # the first wave stood on day 1: surge_pop is the census
        ov.roles.update({"R1": "dorm"})
        ov.surface = 105
        ov.entrances = {"E1": (91, 105, 105), "E2": (97, 94, 105)}
        ov.hatch_free_spare = lambda: spare
        ov.column_rock = lambda s, lo, hi: True
        ov.pick_dig_site = lambda c, levels=1: c[0] if c else None
        ov.beasts_near = lambda *a, **k: []
        return ov, game

    @staticmethod
    def stairs(game):
        return [a for t, a in game.calls if t == "dig_stairs"]


class Stair(Base):
    def test_all_soil_sends_one_hatched_shaft(self):
        ov, game = self.ov()
        ov.rock_dorm_stair()
        self.assertEqual(len(self.stairs(game)), 1)
        self.assertIsNotNone(ov.shaft)
        ov.rock_dorm_stair()   # one shaft at a time
        self.assertEqual(len(self.stairs(game)), 1)

    def test_rock_room_listed_no_shaft(self):
        ov, game = self.ov(sites=(R1, R2, R3, A1) + tuple(S))
        ov.rock_dorm_stair()
        self.assertEqual(self.stairs(game), [])

    def test_owner_conditions_hold(self):
        ov, game = self.ov(spare=0)   # no cover in stock beyond the open entrances' own
        ov.rock_dorm_stair()
        self.assertEqual(self.stairs(game), [])
        ov, game = self.ov()
        ov.entrances = {"E%d" % i: (i, 1, 105) for i in range(harness.ENTRANCE_MAX)}
        ov.rock_dorm_stair()
        self.assertEqual(self.stairs(game), [])
        ov, game = self.ov()
        ov.shaft_stop = True
        ov.rock_dorm_stair()
        self.assertEqual(self.stairs(game), [])
        ov, game = self.ov()
        ov.column_rock = lambda s, lo, hi: False
        ov.rock_dorm_stair()
        self.assertEqual(self.stairs(game), [])
        # Dormitory 35 on R2 (the record): every S site within SHAFT_PEOPLE_GAP of it
        ov, game = self.ov(zones=[{"id": 35, "type": "Dormitory", "x": 94, "y": 93, "z": 104, "w": 3, "h": 3}])
        ov.rock_dorm_stair()
        self.assertEqual(self.stairs(game), [])

    def test_not_surge_or_beds_placed_or_switch(self):
        ov, game = self.ov(surge=False)
        ov.rock_dorm_stair()
        self.assertEqual(self.stairs(game), [])
        ov, game = self.ov(placed=36)
        ov.rock_dorm_stair()
        self.assertEqual(self.stairs(game), [])
        old = harness.ROCK_DORM
        harness.ROCK_DORM = False
        try:
            ov, game = self.ov()
            ov.rock_dorm_stair()
            self.assertEqual(self.stairs(game), [])
        finally:
            harness.ROCK_DORM = old


class Capacity(Base):
    def digs(self, game):
        return [a.get("site") for t, a in game.calls if t == "dig_room"]

    def test_rock_spare_first(self):
        ov, game = self.ov(sites=(R1, R2, R3, A1) + tuple(S))
        ov.roles.clear()
        ov.surge_capacity()
        self.assertEqual(self.digs(game)[:1], ["R3"])

    def test_rock_dorm_past_the_count(self):
        ov, game = self.ov(sites=(R1, dict(R2, dug=True, designated=True), R3, A1) + tuple(S))
        ov.roles["R2"] = "dorm"   # two soil dorms already: the count (36 + 24) / 30 = 2 is met
        ov.surge_capacity()
        self.assertIn("R3", self.digs(game))

    def test_wait_off_digs_soil_as_before(self):
        ov, game = self.ov()
        ov.surge_capacity()
        self.assertIn("R2", self.digs(game))


class Wait(Base):
    def setUp(self):
        super().setUp()
        old = harness.ROCK_DORM_WAIT
        harness.ROCK_DORM_WAIT = True
        self.addCleanup(setattr, harness, "ROCK_DORM_WAIT", old)

    def digs(self, game):
        return [a.get("site") for t, a in game.calls if t in ("dig_room", "dig_stairs")]

    def test_soil_second_dorm_waits_while_no_bed_waits(self):
        ov, game = self.ov()
        ov.surge_capacity()
        self.assertNotIn("R2", self.digs(game))

    def test_wait_sends_no_deeper_shaft(self):
        ov, game = self.ov()
        ov.surge_floor_short = lambda pending=0: True
        ov.surge_floor()
        self.assertEqual(self.digs(game), [])

    def test_soil_second_dorm_dug_once_a_bed_waits(self):
        ov, game = self.ov(beds_free=4)
        ov.bed_full["R1"] = (4, 80)   # R1 answered no_space this pass
        ov.surge_capacity()
        self.assertIn("R2", self.digs(game))

    def test_no_rock_stair_possible_digs_soil(self):
        ov, game = self.ov()
        ov.column_rock = lambda s, lo, hi: False
        ov.surge_capacity()
        self.assertIn("R2", self.digs(game))


if __name__ == "__main__":
    unittest.main()
