"""cx shaft people (harness.py SHAFT_PEOPLE_MIN_TILES): on a fort with an open (unhatchable) entrance, the dining
tables and chairs, new beds, new farm plots and new farm/dining room digs go on boxes MEETING_SHAFT_TILES from every
open shaft column. Probe pmf1 (std MY1-4 snapshot p1): busy citizens on the dug levels stood within 3 tiles of the
open E1 foot (100,101) in 62% of looks — sleeping, eating at the day-0 tables on A2 and planting on the day-5 plot F1
(= R1, x97-99 y100-102 z168, dug on day 0). The site geometry is the record's (MY1-4 day-0..17 observations).
No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_danger_marks import FakeGame, Quiet  # noqa: E402
from test_rescue_station import my14, E1  # noqa: E402
from overseer import harness  # noqa: E402
from real_maps import MapQueries  # noqa: E402

A1 = {"id": "A1", "kind": "A", "x": 100, "y": 100, "z": 168, "w": 12, "h": 3, "open_tiles": 34, "subterranean": True}
A2 = {"id": "A2", "kind": "A", "x": 95, "y": 100, "z": 167, "w": 17, "h": 3, "open_tiles": 49, "subterranean": True}
A5 = {"id": "A5", "kind": "A", "x": 94, "y": 90, "z": 168, "w": 18, "h": 13, "open_tiles": 106, "subterranean": True}
R1 = {"id": "R1", "kind": "R", "x": 97, "y": 100, "z": 168, "w": 3, "h": 3, "soil": True, "dug": False}
R2 = {"id": "R2", "kind": "R", "x": 98, "y": 90, "z": 168, "w": 3, "h": 3, "soil": True, "dug": True,
      "designated": True}
R3 = {"id": "R3", "kind": "R", "x": 94, "y": 90, "z": 168, "w": 3, "h": 3, "soil": True, "dug": False}
F1 = {"id": "F1", "kind": "F", "x": 97, "y": 100, "z": 168, "w": 3, "h": 3, "soil": True}
F2 = {"id": "F2", "kind": "F", "x": 97, "y": 92, "z": 168, "w": 3, "h": 3, "soil": True}
DORM = {"id": 38, "type": "Dormitory", "x": 101, "y": 100, "z": 167, "w": 11, "h": 3}
DINE = {"id": 39, "type": "DiningHall", "x": 95, "y": 100, "z": 167, "w": 5, "h": 3,
        "furniture": {"table": 3, "chair": 3}}
PLOTS = [{"built": True, "id": i, "x": x, "y": 100, "z": 168, "w": 3, "h": 3, "subterranean": True}
         for i, x in ((7, 101), (8, 109), (9, 105))]
# a year-long play's plot target is 7: four standing plots (the fourth on the hard record's R3 floor) hold it half
PLOTS4 = PLOTS + [{"built": True, "id": 10, "x": 94, "y": 90, "z": 168, "w": 3, "h": 3, "subterranean": True}]
HATCH_E1 = {"id": 70, "kind": "hatch", "built": True, "locked": False, "x": 100, "y": 101, "z": 169}
MINER = {"id": 95, "name": "Urist", "x": 104, "y": 101, "z": 168}


def beds():
    return [{"built": True, "kind": "bed", "x": x, "y": y, "z": 167, "zone_ids": [38]}
            for x in range(101, 112) for y in (100, 102)]


def look(day, sites, zones=(DORM, DINE), plots=PLOTS, free=None, doors=(), cit=15, furniture=None):
    r = my14(day, [dict(MINER, id=95 + i) for i in range(cit)], alert=False, sites=sites, doors=doors)
    o = r["observation"]
    o["zones"] = [dict(z) for z in zones]
    o["farm_plots"] = [dict(p) for p in plots]
    o["furniture"] = beds() if furniture is None else furniture
    o["stocks"]["furniture_free"] = dict(free or {"table": 6, "chair": 2})
    return r


class PlaceGame(MapQueries, FakeGame):
    """place_furniture lands its items on the addressed box's top row (the zone pass reads them as placed); the map
    query answers the record's real shapes (real_maps: hint hard MY1-4 on d57f599, day 17)."""
    grid = "hard_my1_4_d57f599_day17"

    def __init__(self, sites):
        super().__init__([])
        self.sites = {s["id"]: s for s in sites}

    def act(self, tool, args):
        r = super().act(tool, args)
        s = self.sites.get(args.get("site"))
        if tool == "place_furniture" and s is not None:
            k = args.get("count", 1)
            r = {"ok": True, "result": {"n": k, "at": [[s["x"] + i, s["y"], s["z"]] for i in range(k)]}}
        return r


class ShaftPeople(Quiet):
    def ov(self, resp, days=216):
        game = PlaceGame(resp["observation"]["map"]["sites"])
        game.plots = list(resp["observation"]["farm_plots"])
        ov = harness.Overseer(game, days=days)
        ov.load(resp)
        ov.count = 0
        game.calls.clear()
        return ov, game

    def calls(self, game, tool):
        return [a for t, a in game.calls if t == tool]

    def test_day0_with_no_far_box_the_standing_dining_hall_takes_the_seats(self):
        # cx audit 3 (hard MY1-4 on d57f599, s93005): the old pass waited days 0-30 (shaft_dine_wait) with the handover
        # fort's DiningHall standing on A2, then placed there anyway — seats are scored at H: no wait
        ov, game = self.ov(look(0, (E1, A1, A2, R1)))
        self.assertTrue(ov.shaft_wait())
        ov.furnish()
        tables = [a for a in self.calls(game, "place_furniture") if a["kind"] == "table"]
        self.assertTrue(tables)
        self.assertLessEqual({a["site"] for a in tables}, {"A1", "A2"})

    def test_the_far_box_takes_the_tables_and_its_dining_zone(self):
        ov, game = self.ov(look(17, (E1, A1, A2, A5, R2, R3)))
        ov.roles.update(R2="farm", R3="dorm")   # R2 dug for a plot that has not stood yet: it cuts the box at x97
        ov.furnish()
        places = self.calls(game, "place_furniture")
        self.assertEqual([(a["kind"], a["site"], a.get("w"), a.get("h")) for a in places],
                         [("table", "A5", 4, 6), ("chair", "A5", 4, 6)])
        self.assertEqual(self.calls(game, "make_zone"),
                         [{"kind": "dining_hall", "site": "A5", "w": 4, "h": 6}])
        box = {"x": 94, "y": 90, "z": 168, "w": 4, "h": 6}
        self.assertGreaterEqual(ov.shaft_gap(box), harness.MEETING_SHAFT_TILES)

    def test_past_the_wait_with_no_far_box_the_old_placement_stands(self):
        ov, game = self.ov(look(harness.MEETING_FAR_WAIT_DAY, (E1, A1, A2, R1)))
        ov.furnish()
        places = self.calls(game, "place_furniture")
        self.assertTrue(places)   # housing is never left short at H: the old placement (the foot's levels)
        self.assertLessEqual({a["site"] for a in places}, {"A1", "A2"})

    def test_a_hatched_entrance_changes_nothing(self):
        e1 = dict(E1, building=False)
        ov, game = self.ov(look(0, (e1, A1, A2, R1), doors=(HATCH_E1,)))
        self.assertFalse(ov.shaft_people())
        ov.furnish()
        places = self.calls(game, "place_furniture")
        self.assertTrue(places)
        self.assertLessEqual({a["site"] for a in places}, {"A1", "A2"})

    def test_new_beds_go_far_and_the_tables_stay_off_them(self):
        free = {"bed": 4, "table": 6, "chair": 6}
        ov, game = self.ov(look(17, (E1, A1, A2, A5, R2, R3), free=free, cit=24))   # 22 beds for 24: 4 due
        ov.roles.update(R2="farm", R3="dorm")
        ov.room_box["R3"] = {"x": 94, "y": 90, "z": 168, "w": 9, "h": 7}
        r3 = dict(R3, dug=True, designated=True)
        ov.load(look(17, (E1, A1, A2, A5, R2, r3), free=free, cit=24))
        ov.count = 0
        game.calls.clear()
        ov.furnish()
        places = self.calls(game, "place_furniture")
        bed = [a for a in places if a["kind"] == "bed"]
        self.assertTrue(bed)
        self.assertEqual((bed[0]["site"], bed[0].get("w"), bed[0].get("h")), ("R3", 4, 6))   # the dorm room's far cut
        tables = [a for a in places if a["kind"] == "table"]
        # the beds took the only far box this pass: the seats never share it (and no longer wait — audit 3)
        self.assertFalse(any(a["site"] == "R3" for a in tables))

    def test_seat_spread_tries_far_boxes_first_and_near_ones_only_after_the_wait(self):
        ov, _ = self.ov(look(17, (E1, A1, A2, A5, R2)))
        ov.roles.update(R2="farm")
        boxes = [{"id": "A2:17x3", "site": "A2", "x": 95, "y": 100, "z": 167, "w": 17, "h": 3, "zoned": True},
                 {"id": "A5:18x13", "site": "A5", "x": 94, "y": 90, "z": 168, "w": 18, "h": 13, "zoned": False}]
        got = ov.shaft_seats(boxes)
        # far first; the near box after it, never held back (audit 3)
        self.assertEqual([(b["site"], b["w"], b["h"]) for b in got], [("A5", 4, 6), ("A2", 17, 3)])

    def test_the_fourth_plot_waits_for_a_far_site(self):
        # a year-long open play with drink to spare (500 for 15 citizens): the near plot may wait
        ov, game = self.ov(look(5, (E1, A1, A2, F1), plots=PLOTS4), days=336)
        ov.farms()
        self.assertEqual(self.calls(game, "build_farm"), [])   # F1 (R1's floor) is one tile off the foot
        ov, game = self.ov(look(7, (E1, A1, A2, F1, F2), plots=PLOTS4), days=336)
        ov.farms()
        self.assertEqual([a["site"] for a in self.calls(game, "build_farm")], ["F2"])

    def test_my1_plots_never_wait(self):
        # cx audit 5 (hard MY1-3 on d57f599, s92315: pb 4, the model's build_farm F1 refused shaft_risk on day 3):
        # on the MY1 plan every plant is a brew
        ov, game = self.ov(look(5, (E1, A1, A2, F1)))
        ov.farms()
        self.assertEqual([a["site"] for a in self.calls(game, "build_farm")][:1], ["F1"])
        self.assertIsNone(ov.shaft_refusal("build_farm", {"site": "F1"}))

    def test_a_drink_short_fort_never_holds_plots(self):
        resp = look(5, (E1, A1, A2, F1), plots=PLOTS4)
        resp["observation"]["stocks"].update(drink=40, plants_brewable=4)   # 60 for 211 days x 15 citizens
        ov, game = self.ov(resp, days=336)
        ov.farms()
        self.assertEqual([a["site"] for a in self.calls(game, "build_farm")][:1], ["F1"])

    def test_the_first_plot_never_waits(self):
        ov, game = self.ov(look(5, (E1, A1, A2, F1), plots=()))
        ov.farms()
        self.assertEqual([a["site"] for a in self.calls(game, "build_farm")][:1], ["F1"])

    def test_a_fort_short_of_plots_never_waits(self):
        ov, game = self.ov(look(5, (E1, A1, A2, F1), plots=PLOTS[:1]))   # 1 of the 4-plot target
        ov.farms()
        self.assertEqual([a["site"] for a in self.calls(game, "build_farm")][:1], ["F1"])

    def test_the_near_farm_room_is_not_dug_early(self):
        ov, game = self.ov(look(0, (E1, A1, A2, R1), plots=PLOTS4), days=336)
        ov.digging()
        self.assertNotIn("R1", [a["site"] for a in self.calls(game, "dig_room")])
        ov, game = self.ov(look(0, (E1, A1, A2, R1)))   # MY1: plants are drink, the farm room is dug (audit 5)
        ov.digging()
        self.assertIn("R1", [a["site"] for a in self.calls(game, "dig_room")])
        ov, game = self.ov(look(harness.MEETING_FAR_WAIT_DAY, (E1, A1, A2, R1), plots=PLOTS4), days=336)
        ov.digging()
        self.assertIn("R1", [a["site"] for a in self.calls(game, "dig_room")])

    def test_the_models_own_near_tables_and_digs_are_refused(self):
        # pdn1: the model placed 5 tables on A2 on day 0 and 5 chairs on day 3, past the layer's wait
        ov, _ = self.ov(look(0, (E1, A1, A2, R1)))
        # cx audit 3: the handover fort's DiningHall on A2 is never refused, and with no far box nothing waits
        self.assertIsNone(ov.shaft_refusal("place_furniture", {"kind": "table", "site": "A2", "count": 5}))
        self.assertIsNone(ov.shaft_refusal("make_zone", {"kind": "dining_hall", "site": "A2"}))
        self.assertIsNone(ov.shaft_refusal("place_furniture", {"kind": "table", "site": "A1", "count": 5}))
        self.assertIn("open shaft", ov.shaft_refusal("dig_room", {"site": "R1", "w": 9, "h": 7}))   # 22 beds, 15 cit
        self.assertIsNone(ov.shaft_refusal("place_furniture", {"kind": "bed", "site": "A2", "count": 2}))
        ov, _ = self.ov(look(17, (E1, A1, A2, A5, R2)))
        ov.roles.update(R2="farm")
        self.assertIsNone(ov.shaft_refusal("place_furniture", {"kind": "table", "site": "A2", "count": 5}))
        why = ov.shaft_refusal("place_furniture", {"kind": "table", "site": "A1", "count": 5})
        self.assertIn("use site A5 with w=4 h=6", why)
        self.assertIsNone(ov.shaft_refusal("place_furniture", {"kind": "table", "site": "A5", "w": 4, "h": 6}))
        e1 = dict(E1, building=False)
        ov, _ = self.ov(look(0, (e1, A1, A2, R1), doors=(HATCH_E1,)))
        self.assertIsNone(ov.shaft_refusal("place_furniture", {"kind": "table", "site": "A2", "count": 5}))

    def test_none_turns_it_off(self):
        old = harness.MEETING_SHAFT_TILES
        harness.MEETING_SHAFT_TILES = None
        try:
            ov, game = self.ov(look(0, (E1, A1, A2, R1)))
            self.assertFalse(ov.shaft_people())
            ov.furnish()
            places = self.calls(game, "place_furniture")
            self.assertTrue(places)
            self.assertLessEqual({a["site"] for a in places}, {"A1", "A2"})
        finally:
            harness.MEETING_SHAFT_TILES = old


if __name__ == "__main__":
    unittest.main()
