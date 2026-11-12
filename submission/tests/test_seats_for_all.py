"""cx seats spread for all (std OP1-4 on 014f7eb, wellbeing 0.90): 6 tables and 9 chairs sat free from d250 to H with 11
dining seats for 19 citizens. f_table on the full dine room R1 answered no_space 16 times and seat_spread stopped at
want = ceil(19/2)+1 = 11, while seats_full() (one pair per citizen) was 19. LackChairs / LackTables are measured
negative thoughts (cx95fa9d3 hard LT08-1 side-car: 80 LackChairs in F; the MY1-4 recorder probe: 32 LackTables).
Now: seat_spread fills to max(want, seats_full()) on the next closed seat box when the dine room is full; with no
closed box at all, house_floor digs a listed spare R room for them once the farm rooms are met — never a new shaft
(floor_stair keeps waiting for the beds or the half-census seats, as before). No game or network."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_housing_boxes import A6, R, Base, harness  # noqa: E402


class SeatsForAll(Base):
    def dine_full(self, free, cit=19, sites=(), seats=11, **kw):
        # R1 the full dine room: a dining zone holding `seats` pairs; place_furniture answers no_space there
        r1 = R("R1", 98, 98, used_by=["Dormitory 12", "DiningHall 13"])
        dining = {"id": 13, "type": "DiningHall", "x": 98, "y": 98, "z": 159, "w": 9, "h": 7,
                  "furniture": {"table": seats, "chair": seats}}
        o, game = self.ov(sites=[r1] + list(sites), zones=[dining], free=free, cit=cit,
                          roles={"R1": "dorm"}, **kw)
        game.full.add("R1")
        o.st.update(tables=seats + free.get("table", 0), chairs=seats + free.get("chair", 0))
        return o, game

    def test_the_014f7eb_stock_goes_to_the_next_closed_box_up_to_every_citizen(self):
        o, game = self.dine_full({"bed": 0, "table": 6, "chair": 9}, sites=[A6])
        self.assertEqual(o.seats(), 11)
        self.assertEqual(o.seats_full(), 19)
        o.furnish()
        t = [a for a in self.calls(game, "place_furniture", kind="table") if a["site"] == "A6"]
        c = [a for a in self.calls(game, "place_furniture", kind="chair") if a["site"] == "A6"]
        self.assertEqual([a["count"] for a in t], [6])   # min(19 - 11, 6 tables, 9 chairs)
        self.assertEqual([a["count"] for a in c], [6])
        self.assertEqual(len(self.calls(game, "make_zone", kind="dining_hall", site="A6")), 1)

    def test_the_old_goal_stopped_at_half_the_census(self):
        o, game = self.dine_full({"bed": 0, "table": 6, "chair": 9}, sites=[A6])
        o.seat_spread(o.cit // 2 + 2)   # want = ceil(19/2)+1 = 11, as before
        self.assertEqual([a for a in self.calls(game, "place_furniture") if a["site"] == "A6"], [])

    def test_seats_full_off_keeps_the_half_census_goal(self):
        o, game = self.dine_full({"bed": 0, "table": 6, "chair": 9}, sites=[A6])
        o.seats_full = lambda: 0   # lean harvest / logs short / surge / breach
        o.furnish()
        self.assertEqual([a for a in self.calls(game, "place_furniture") if a["site"] == "A6"], [])

    def test_no_closed_box_logs_and_digs_a_spare_room_but_no_shaft(self):
        s1 = {"id": "S1", "kind": "S", "x": 130, "y": 120, "z": 160, "w": 1, "h": 1, "soil": True}
        o, game = self.dine_full({"bed": 0, "table": 6, "chair": 9}, stairs_s=[s1])
        o.farms_met = lambda: True
        o.furnish()
        self.assertEqual(o.seat_refused_day, 251)  # the full dine room refused, past the half-census goal
        self.assertIsNone(o.seat_nobox_day)        # a box exists (refused): no seat shaft
        self.assertIsNone(o.house_full_day)        # floor_stair's own trigger is not armed by it
        o.house_floor(0)
        self.assertEqual(self.calls(game, "dig_stairs"), [])   # no listed R room: still no new shaft
        r9 = R("R9", 60, 80, dug=False, designated=False)
        o, game = self.dine_full({"bed": 0, "table": 6, "chair": 9}, sites=[r9], stairs_s=[s1])
        o.farms_met = lambda: True
        o.furnish()
        o.house_floor(0)
        self.assertEqual(self.calls(game, "dig_room"), [{"site": "R9", "w": 9, "h": 7}])
        self.assertEqual(o.roles["R9"], "house")

    def test_the_014f7eb_shape_no_seat_box_at_all_is_logged(self):
        # the dining zone's corner (94,98) is no listed site (A3 used up), R1 at 98,98 carries it: no box at all
        o, game = self.dine_full({"bed": 0, "table": 6, "chair": 9})
        o.zones[0].update(x=94, w=13)
        o.furnish()
        self.assertEqual(o.seat_nobox_day, 251)
        self.assertIsNone(o.house_full_day)
        self.assertIn('"seat_no_box"', self.output._new_target.getvalue())

    def test_a_rock_room_is_no_farm_and_takes_the_seats_before_the_farms_are_met(self):
        # the seat shaft's new level lists rock R sites (014f7eb: farm target 7 never met for lack of floor)
        r9 = R("R9", 60, 80, dug=False, designated=False, soil=False)
        o, game = self.dine_full({"bed": 0, "table": 6, "chair": 9}, sites=[r9])
        o.farms_met = lambda: False
        o.zones[0].update(x=94, w=13)   # no seat box at all
        o.furnish()
        o.house_floor(0)
        self.assertEqual(self.calls(game, "dig_room"), [{"site": "R9", "w": 9, "h": 7}])

    def test_the_spare_room_waits_for_the_farm_rooms(self):
        r9 = R("R9", 60, 80, dug=False, designated=False)
        o, game = self.dine_full({"bed": 0, "table": 6, "chair": 9}, sites=[r9])
        o.farms_met = lambda: False
        o.furnish()
        o.house_floor(0)
        self.assertEqual(self.calls(game, "dig_room"), [])

    def test_half_census_seats_keep_the_old_shaft_step(self):
        s1 = {"id": "S1", "kind": "S", "x": 130, "y": 120, "z": 160, "w": 1, "h": 1, "soil": True}
        o, game = self.dine_full({"bed": 0, "table": 6, "chair": 9}, seats=5, stairs_s=[s1], sites=[A6])
        game.full.add("A6")
        o.furnish()                     # every box refused: house_full_day as before
        self.assertEqual(o.house_full_day, 251)
        o.house_floor(0)
        self.assertEqual(len(self.calls(game, "dig_stairs")), 1)

    def test_farms_met_reads_the_plot_target(self):
        o, _ = self.dine_full({"bed": 0, "table": 6, "chair": 9})
        o.farm_target = lambda: 2
        self.assertFalse(o.farms_met())
        o.roles.update({"R2": "farm", "R3": "farm"})
        self.assertTrue(o.farms_met())


if __name__ == "__main__":
    unittest.main()
