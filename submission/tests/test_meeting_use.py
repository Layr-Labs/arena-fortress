"""cx rain shelter: a meeting area the idle never use gets a second one near where the citizens eat or sleep. No game.

Measured: hint hard MY1-3 on e33d381 zoned its only meeting area on A1's 20x20 corner (a ramp tunnel, x67-86 y66-85
z143) on day 0; 0 of 1,567 idle looks stood in it and 1,172 stood on the surface (z144), where the probe on hint hard
MY1-4 (pmy14p) recorded Rain as the top negative thought (2,859 at full strength, 96% on the surface level). The
MY1-4 meeting areas below the surface held 2,338 of 3,155 (d57f599) and 1,601 of 2,623 (e33d381) idle looks."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness
from test_meeting_box import FakeGame, BEDS, TABLES, ZONES, site, zone

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

TUNNEL = zone(70, "MeetingHall", 67, 66, 143, 20, 20)
SITES = [site("A3", 67, 67, 143, 61, 55, 120), site("A2", 90, 101, 142, 17, 3, 49)]


def facts(dwarves, zones=ZONES + [TUNNEL], day=24, tick=None):
    return {"tick": tick or 967200 + day * harness.DAY, "day": day, "observation": {
        "administrators": {"citizens": len(dwarves)}, "map": {"sites": [dict(s) for s in SITES], "surface_z": 144},
        "zones": [dict(z) for z in zones], "furniture": [dict(f) for f in BEDS + TABLES],
        "dwarves": [dict(p) for p in dwarves], "stocks": {"furniture_free": {}},
        "date": {"abs_tick": tick or 967200 + day * harness.DAY}}}


def idle(n, z=144, x=150, y=20):
    return [{"id": i, "job": "idle", "x": x + i, "y": y, "z": z, "stress": 3} for i in range(n)]


class MeetingUse(unittest.TestCase):
    def setUp(self):
        out = redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)
        self.game = FakeGame()
        self.ov = harness.Overseer(self.game, days=216)

    def looks(self, dwarves, passes):
        for k in range(passes):
            self.ov.load(facts(dwarves, tick=967200 + 20 * harness.DAY + k * 100))
            self.ov.count = 0
            self.ov.meeting_use()

    def zones_made(self):
        return [a for t, a in self.game.calls if t == "make_zone" and a.get("kind") == "meeting_area"]

    def test_unused_meeting_area_gets_one_near_the_dining_room(self):
        self.looks(idle(10), 7)          # 70 idle looks, none inside, all on the surface
        made = self.zones_made()
        self.assertEqual(len(made), 1)
        self.assertEqual(made[0]["site"], "A2")   # the dining level below the surface, not the tunnel's site again
        self.looks(idle(10), 7)
        self.assertEqual(len(self.zones_made()), 1)   # once a run

    def test_used_meeting_area_is_left_alone(self):
        inside = [{"id": i, "job": "idle", "x": 70 + i, "y": 70, "z": 143, "stress": 3} for i in range(10)]
        self.looks(inside, 7)
        self.assertEqual(self.zones_made(), [])

    def test_too_few_looks_or_idle_below_the_surface_wait(self):
        self.looks(idle(10), 5)          # 50 looks: under MEETING_USE_LOOKS
        self.assertEqual(self.zones_made(), [])
        game = FakeGame()
        self.game, self.ov = game, harness.Overseer(game, days=216)
        self.looks(idle(10, z=142, x=100, y=95), 7)   # idle off the zone but below the surface: no rain there
        self.assertEqual(self.zones_made(), [])

    def test_one_count_per_observation(self):
        for _ in range(9):               # the same observation loaded nine times counts once
            self.ov.load(facts(idle(10)))
            self.ov.meeting_use()
        self.assertEqual(self.ov.meeting_looks[0], 10)

    def test_never_on_an_open_shafts_foot_nor_far_from_home(self):
        self.ov.shaft_gap = lambda b: 1
        self.looks(idle(10), 7)
        self.assertEqual(self.zones_made(), [])
        game = FakeGame()
        self.game, self.ov = game, harness.Overseer(game, days=216)
        far_home = [zone(38, "DiningHall", 10, 10, 142, 5, 3), zone(39, "Dormitory", 10, 20, 142, 11, 3), TUNNEL]
        for k in range(7):
            self.ov.load(facts(idle(10), zones=far_home, tick=967200 + 20 * harness.DAY + k * 100))
            self.ov.count = 0
            self.ov.meeting_use()
        self.assertEqual(self.zones_made(), [])

    def test_no_meeting_area_yet_is_meeting_areas_job(self):
        self.ov.load(facts(idle(10), zones=ZONES))
        self.ov.meeting_use()
        self.assertEqual(self.ov.meeting_looks, [0, 0, 0])


if __name__ == "__main__":
    unittest.main()
