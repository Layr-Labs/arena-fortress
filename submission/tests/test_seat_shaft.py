"""cx seat shaft (owner: a new entrance is fine hatched and locked like the others): std OP1-4 on 014f7eb had 6 tables
and 9 chairs free d250-H with 11 seats for 19 citizens, no seat box at all (R1 full, A3 used up, A4-A6 open) and no
spare R site (the game only ever listed R1-R3). house_floor now sends one new stair for seats under exactly
shelter_shaft's conditions — cover in stock and reserved, ENTRANCE_MAX, no big beast, SHAFT_PEOPLE_GAP, rock column,
hatched the pass its E site lists, a refused hatch ends new shafts — only when seats are short with free pairs and
the last seat pass found no seat box at all. Fixture: tests/test_shelter_shaft.py. No game or network."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_shelter_shaft as ts  # noqa: E402

S1, Quiet = ts.S1, ts.Quiet


class SeatShaft(Quiet):
    fort, look, digs = ts.Shaft.fort, ts.Shaft.look, ts.Shaft.digs

    def seats_short(self, agent, nobox=True, refused=False):
        day = agent.obs_day()
        agent.surge, agent.hands_off = False, None   # open play (the fixture's goal names a surge)
        agent.free = {"bed": 0, "table": 6, "chair": 9}
        agent.seats = lambda: 11
        agent.seats_full = lambda: 48
        agent.farms_met = lambda: True
        agent.house_full_day = None
        agent.seat_nobox_day = day if nobox else None
        agent.seat_refused_day = day if refused else None

    def test_no_seat_box_and_no_spare_room_digs_one_shaft(self):
        agent, game = self.fort()
        self.seats_short(agent)
        agent.house_floor(0)
        self.assertEqual(self.digs(game), [("dig_stairs", {"site": "S1", "z_bottom": 103})])   # off the dorm (S9)
        self.assertEqual(agent.shaft["site"], "S1")
        self.assertIn('"why": "seats"', self.output._new_target.getvalue())
        agent.house_floor(0)   # one at a time
        self.assertEqual(len(self.digs(game)), 1)

    def test_refused_boxes_or_an_old_mark_or_no_pairs_dig_nothing(self):
        for kw in ({"nobox": False, "refused": True}, {"nobox": False}):
            agent, game = self.fort()
            self.seats_short(agent, **kw)
            agent.house_floor(0)
            self.assertEqual(self.digs(game), [], kw)
        agent, game = self.fort()
        self.seats_short(agent)
        agent.seat_nobox_day -= 10   # HOUSE_FULL_DAYS ago
        agent.house_floor(0)
        self.assertEqual(self.digs(game), [])
        agent, game = self.fort()
        self.seats_short(agent)
        agent.free = {"bed": 0, "table": 6, "chair": 0}
        agent.house_floor(0)
        self.assertEqual(self.digs(game), [])

    def test_the_shelter_shaft_conditions_hold(self):
        agent, game = self.fort(covers=0)               # no spare cover
        self.seats_short(agent)
        agent.house_floor(0)
        self.assertEqual(self.digs(game), [])
        agent, game = self.fort(others=[{"id": 113, "race": "ALLIGATOR", "x": 80, "y": 94, "z": 104}])
        self.seats_short(agent)                          # a big beast near
        agent.house_floor(0)
        self.assertEqual(self.digs(game), [])
        agent, game = self.fort()
        game.rock = set()                                # open column
        self.seats_short(agent)
        agent.house_floor(0)
        self.assertEqual(self.digs(game), [])
        agent, game = self.fort()
        agent.shaft_stop = True                          # a hatch was refused earlier
        self.seats_short(agent)
        agent.house_floor(0)
        self.assertEqual(self.digs(game), [])

    def test_the_seat_shaft_is_hatched_on_the_pass_it_lists(self):
        agent, game = self.fort()
        self.seats_short(agent)
        agent.house_floor(0)
        game.sites.append({"id": "E2", "kind": "E", "x": S1["x"], "y": S1["y"], "z": S1["z"], "w": 1, "h": 1,
                           "building": False})
        self.look(agent, game, 18)
        agent.shaft_hatch()
        self.assertIn(("build_door", {"kind": "hatch", "site": "E2"}), game.calls)

    def test_a_house_room_being_dug_waits(self):
        agent, game = self.fort()
        self.seats_short(agent)
        agent.roles["R9"] = "house"
        agent.kind = (lambda orig: lambda k: orig(k) + ([{"id": "R9", "kind": "R", "x": 1, "y": 1, "z": 104,
                                                           "dug": False}] if k == "R" else []))(agent.kind)
        agent.house_floor(0)
        self.assertEqual(self.digs(game), [])


if __name__ == "__main__":
    unittest.main()
