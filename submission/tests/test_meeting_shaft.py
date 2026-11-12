"""cx shaft child, part 2 (hint std MY1-4 on 7c43df4): the day-0 meeting area went on A1 (x100-111 y100-102 z168),
the box holding the foot of the open E1 shaft (100,101) — idle dwarves (children all day) gather on the meeting
area, and 1021 of 2125 citizen-looks on the dug levels stood within 3 tiles of that foot, where the kea that came down
the shaft on day 85 wounded the child (dead of infection on day 166). On a fort with an open entrance the meeting area
goes on a box MEETING_SHAFT_TILES from every open shaft column when one is available, and once such a box exists a
second meeting area is zoned there. The site geometry is the record's (MY1-4 day-0 and day-5 observations).
No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_danger_marks import FakeGame, Quiet  # noqa: E402
from test_rescue_station import my14, E1, E2  # noqa: E402
from overseer import harness  # noqa: E402
from real_maps import MapQueries  # noqa: E402

A1 = {"id": "A1", "kind": "A", "x": 100, "y": 100, "z": 168, "w": 12, "h": 3, "open_tiles": 34, "subterranean": True}
A2 = {"id": "A2", "kind": "A", "x": 95, "y": 100, "z": 167, "w": 17, "h": 3, "open_tiles": 49, "subterranean": True}
# the record's own A4 (std MY1-4 on 7c43df4, day 4): open_tiles 44 — its floor is the A1 strip and R1 at y100-102, the
# far cut y91-95 holds only the new stair (real_maps std_my1_4_7c43df4_day6)
A4 = {"id": "A4", "kind": "A", "x": 97, "y": 91, "z": 168, "w": 15, "h": 12, "open_tiles": 44, "subterranean": True}
# hint hard MY1-4 on d57f599 (s93005), day 14: A4 over the plot rooms R3/R2 (x94-100 y90-92) and the A1 strip
A4_HARD = {"id": "A4", "kind": "A", "x": 94, "y": 90, "z": 168, "w": 18, "h": 13, "open_tiles": 53, "subterranean": True}
PLOTS_HARD = [{"built": True, "id": i, "x": x, "y": 90, "z": 168, "w": 3, "h": 3} for i, x in ((54, 94), (55, 98))]
MEET_A1 = {"id": 40, "type": "MeetingHall", "x": 100, "y": 100, "z": 168, "w": 12, "h": 3}
DORM = {"id": 38, "type": "Dormitory", "x": 101, "y": 100, "z": 167, "w": 11, "h": 3}
HATCH_E1 = {"id": 70, "kind": "hatch", "built": True, "locked": False, "x": 100, "y": 101, "z": 169}
CHILD = {"id": 266, "name": "Etur Nishginet, Dwarven Child", "x": 101, "y": 101, "z": 168}


def look(day, sites, zones=(), doors=()):
    r = my14(day, [CHILD], alert=False, sites=sites, doors=doors)
    r["observation"]["zones"] = [dict(z) for z in zones]
    return r


class MapGame(MapQueries, FakeGame):
    pass


class MeetingFar(Quiet):
    def ov(self, resp, grid="std_my1_4_7c43df4_day6", plots=()):
        game = MapGame([])
        game.grid, game.plots = grid, list(plots)
        resp["observation"]["farm_plots"] = [dict(p) for p in plots]
        ov = harness.Overseer(game, days=216)
        ov.load(resp)
        ov.count = 0
        game.calls.clear()
        return ov, game

    def zone_calls(self, game):
        return [a for t, a in game.calls if t == "make_zone"]

    def test_the_shaft_gap_of_the_record_boxes(self):
        ov, _ = self.ov(look(5, (E1, A1, A2, A4)))
        self.assertEqual(ov.open_entrances(), [(100, 101, 169)])
        self.assertEqual(ov.shaft_gap(MEET_A1), 0)
        self.assertEqual(ov.shaft_gap(dict(A4, h=5)), 6)
        self.assertEqual(ov.shaft_gap(dict(A4, h=6)), 5)

    def test_day0_no_far_box_waits_then_takes_a_near_box_off_the_foot(self):
        # cx audit 4: the wait ends at MEETING_NEAR_DAY (not 30); the near box keeps MEETING_FOOT_TILES off the
        # E1 column (100,101) — the old fallback zoned A1, the box holding the foot itself
        grid = "hard_my1_4_d57f599_day17"   # z167 and z168 read (A2's floor x95-99 / x101-111, y100-102)
        ov, game = self.ov(look(0, (E1, A1, A2), zones=(DORM,)), grid=grid)
        ov.meeting_area()
        ov.meeting_far()
        self.assertEqual(self.zone_calls(game), [])   # only boxes over the shaft: wait for the digging
        ov.load(look(harness.MEETING_NEAR_DAY - 1, (E1, A1, A2), zones=(DORM,)))
        game.calls.clear()
        ov.meeting_area()
        self.assertEqual(self.zone_calls(game), [])
        ov.load(look(harness.MEETING_NEAR_DAY, (E1, A1, A2), zones=(DORM,)))
        ov.count = 0
        game.calls.clear()
        ov.meeting_area()
        calls = self.zone_calls(game)
        self.assertEqual(calls, [{"kind": "meeting_area", "site": "A2", "w": 3, "h": 3}])
        box = {"x": 95, "y": 100, "z": 167, "w": 3, "h": 3}
        self.assertGreaterEqual(ov.shaft_gap(box), harness.MEETING_FOOT_TILES)
        self.assertLess(ov.shaft_gap(box), harness.MEETING_SHAFT_TILES)   # near: the far one comes later

    def test_no_box_off_the_foot_makes_no_meeting_area_on_it(self):
        ov, game = self.ov(look(harness.MEETING_FAR_WAIT_DAY, (E1, A1), zones=(DORM,)),
                           grid="hard_my1_4_d57f599_day17")
        ov.meeting_area()
        self.assertEqual(self.zone_calls(game), [])   # A1 holds the foot: never zoned as the meeting area

    def test_a_near_meeting_area_gets_its_far_one_when_it_appears(self):
        near = dict(MEET_A1, id=41, x=95, y=100, z=167, w=3, h=3)
        ov, game = self.ov(look(20, (E1, A2, A4_HARD), zones=(near, DORM)), grid="hard_my1_4_d57f599_day17",
                           plots=PLOTS_HARD)
        ov.meeting_area()
        ov.meeting_far()
        self.assertEqual(self.zone_calls(game), [{"kind": "meeting_area", "site": "A4", "w": 18, "h": 6}])

    def test_no_open_shaft_no_wait(self):
        e1 = dict(E1, building=False)
        ov, game = self.ov(look(0, (e1, A1, A2), zones=(DORM,), doors=(HATCH_E1,)))
        ov.meeting_area()
        self.assertEqual(self.zone_calls(game)[0]["site"], "A1")

    def test_a_second_meeting_area_goes_on_the_far_box(self):
        # hard MY1-4 on d57f599 (s93005 z_meeting_far day 14: A4 18x6): its floor is the two plot rooms — people
        # gather on plots, so the cut counts them (walk floor)
        ov, game = self.ov(look(14, (E1, A2, A4_HARD), zones=(MEET_A1, DORM)), grid="hard_my1_4_d57f599_day17",
                           plots=PLOTS_HARD)
        ov.meeting_area()
        ov.meeting_far()
        self.assertEqual(self.zone_calls(game), [{"kind": "meeting_area", "site": "A4", "w": 18, "h": 6}])
        game.calls.clear()
        ov.load(look(15, (E1, A2, A4_HARD), zones=(MEET_A1, DORM, dict(MEET_A1, id=41, x=94, y=90, w=18, h=6))))
        game.calls.clear()
        ov.meeting_far()
        self.assertEqual(self.zone_calls(game), [])   # one far meeting area stands: nothing more

    def test_a_far_cut_over_rock_is_no_far_box(self):
        # cx confirmed floor: the record's A4 cut (x97-111 y91-95) is rock but for the stair — the old pass zoned the
        # first meeting area there; now nothing far exists, so the day-5 pass waits for the digging
        ov, game = self.ov(look(5, (E1, A1, A2, A4), zones=(DORM,)))
        self.assertIsNone(ov.meeting_far_box())
        ov.meeting_area()
        self.assertEqual(self.zone_calls(game), [])

    def test_the_first_meeting_area_avoids_the_shaft_when_it_can(self):
        ov, game = self.ov(look(14, (E1, A1, A2, A4_HARD), zones=(DORM,)), grid="hard_my1_4_d57f599_day17",
                           plots=PLOTS_HARD)
        ov.meeting_area()
        self.assertEqual(self.zone_calls(game), [{"kind": "meeting_area", "site": "A4", "w": 18, "h": 6}])

    def test_a_hatched_entrance_changes_nothing(self):
        e1 = dict(E1, building=False)
        ov, game = self.ov(look(5, (e1, A1, A2, A4), zones=(MEET_A1, DORM), doors=(HATCH_E1,)))
        self.assertEqual(ov.open_entrances(), [])
        ov.meeting_far()
        self.assertEqual(self.zone_calls(game), [])

    def test_the_far_box_stays_off_the_sleepers(self):
        dorm = {"id": 72, "type": "Dormitory", "x": 97, "y": 91, "z": 168, "w": 15, "h": 5}
        ov, game = self.ov(look(5, (E1, A1, A2, A4), zones=(MEET_A1, dorm)))
        self.assertIsNone(ov.meeting_far_box())

    def test_a_farm_room_in_the_far_part_cuts_the_box_short_of_it(self):
        # the probe fort's day-90 sites: A5 (x94-111 y90-102), the farm-role R2 (x98-100 y90-92) with no plot yet
        a5 = {"id": "A5", "kind": "A", "x": 94, "y": 90, "z": 168, "w": 18, "h": 13, "open_tiles": 106,
              "subterranean": True}
        r2 = {"id": "R2", "kind": "R", "x": 98, "y": 90, "z": 168, "w": 3, "h": 3, "dug": True}
        ov, game = self.ov(look(90, (E1, A2, a5, r2), zones=(MEET_A1, DORM)), grid="hard_my1_4_d57f599_day17")
        ov.roles["R2"] = "farm"
        ov.meeting_far()
        self.assertEqual(self.zone_calls(game), [{"kind": "meeting_area", "site": "A5", "w": 4, "h": 6}])

    def test_none_turns_it_off(self):
        old = harness.MEETING_SHAFT_TILES
        harness.MEETING_SHAFT_TILES = None
        try:
            ov, game = self.ov(look(5, (E1, A1, A2, A4), zones=(MEET_A1, DORM)))
            ov.meeting_far()
            self.assertEqual(self.zone_calls(game), [])
        finally:
            harness.MEETING_SHAFT_TILES = old
