"""cx OP1-2 supply (hint std OP1-2 on 0bd4308, supply 0.29, drink 185 -> 0, farm_plots 0 all year): the layer's
bedroom dig took R1 on day 1 with 14 river tiles touching its box (dry() and water_ok() only), deep water stood
indoors from day 3 and every z162 room was halted for the year; on day 48 the dorm's 9x7 box (R6) covered the new farm
room R5 and the A5 box over that floor took 9 beds, so no plot was ever built. Replay of the record through b167a15
makes the same three decisions. No game or network."""
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


def room(rid, x, y, z=162, soil=True, dug=False):
    return {"id": rid, "kind": "R", "x": x, "y": y, "z": z, "w": 3, "h": 3, "soil": soil, "subterranean": True,
            "designated": dug, "dug": dug, "free": True}


# the record's sites (cx0bd4308 hint std OP1-2): R1 under the river rows, R2/R3 dry soil rooms on z162, R4 rock
R1, R2, R3, R4 = room("R1", 100, 94), room("R2", 98, 96), room("R3", 92, 98), room("R4", 98, 98, soil=False)
R5 = room("R5", 98, 98, z=161)
R6 = room("R6", 94, 98, z=161)


class Base(unittest.TestCase):
    def setUp(self):
        out = redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def ov(self, sites, people=7, day=1, beds=0, plots=0):
        game = FakeGame()
        ov = harness.Overseer(game, days=336)
        dwarves = [{"id": 90 + i, "stress": 4, "adult": True} for i in range(people)]
        r = resp(day=day, cit=people, farms=plots, extra={"dwarves": dwarves, "map": {"sites": [dict(s) for s in sites]}})
        r["observation"]["stocks"]["furniture_free"] = {"bed": beds}
        ov.load(r)
        ov.count = 0
        return ov, game

    @staticmethod
    def digs(game):
        return [a for t, a in game.calls if t == "dig_room"]


class BedroomDig(Base):
    def test_a_room_water_touches_is_never_dug_as_a_bedroom(self):
        ov, game = self.ov([R1, R4])
        ov.water_cache["R1"], ov.water_cache_day["R1"] = 14, 1   # measured: 14 river tiles touch R1's box
        ov.water_cache["R4"], ov.water_cache_day["R4"] = 0, 1
        ov.house_everyone()
        self.assertEqual([a["site"] for a in self.digs(game)], ["R4"])
        self.assertNotEqual(ov.roles.get("R1"), "bedroom")

    def test_soil_rooms_wait_for_the_farms(self):
        # day 1, no plot, no farm room: R2/R3 (soil) are the farms' rooms; the rock room takes the bedroom
        ov, game = self.ov([R2, R3, R4])
        ov.house_everyone()
        self.assertEqual([a["site"] for a in self.digs(game)], ["R4"])

    def test_only_soil_left_waits_while_farms_are_short(self):
        ov, game = self.ov([R2, R3])
        ov.house_everyone()
        self.assertEqual(self.digs(game), [])

    def test_soil_room_once_the_farms_are_met(self):
        ov, game = self.ov([R2, R3], plots=20)
        self.assertTrue(ov.farms_met())
        ov.house_everyone()
        self.assertEqual(len(self.digs(game)), harness.BEDROOM_PASS_CAP)


class FarmBox(Base):
    def test_dorm_box_never_covers_a_farm_room_waiting_for_its_plot(self):
        rock6 = dict(R6, soil=False)
        ov, game = self.ov([dict(R5, designated=True), rock6], day=48)
        ov.roles["R5"] = "farm"
        self.assertTrue(ov.farm_claimed(dict(rock6, w=9, h=7)))
        ov.digging()
        self.assertNotIn("R6", [a["site"] for a in self.digs(game)])

    def test_dorm_box_digs_when_no_farm_room_is_under_it(self):
        rock6 = dict(R6, soil=False)
        ov, game = self.ov([dict(R5, designated=True), rock6], day=48)
        ov.roles["R5"] = "dine"   # a people room under it, not a farm: the dorm takes its 9x7 box as before
        ov.digging()
        self.assertIn({"site": "R6", "w": 9, "h": 7}, self.digs(game))

    def test_house_floor_skips_a_box_over_a_farm_room(self):
        ov, game = self.ov([dict(R5, designated=True), dict(R6, soil=False)], day=48)
        ov.roles["R5"] = "farm"
        ov.house_blocked = lambda full=False: True
        ov.house_waiting = lambda full=False: (True, True)
        ov.house_floor(0)
        self.assertNotIn("R6", [a["site"] for a in self.digs(game)])
        ov.roles["R5"] = "dorm"
        ov.house_floor(0)
        self.assertIn("R6", [a["site"] for a in self.digs(game)])


if __name__ == "__main__":
    unittest.main()
