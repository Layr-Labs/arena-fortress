"""cx housing boxes (harness.py HOUSE_*): the growth half of s4 is housing at H — built beds per citizen and seats
(tables and chairs inside dining zones) per two citizens — and the hint OP1 forts lost it to placement, not production:
- std OP1-4 (cxb796327): 10 tables + 13 chairs placed on A4, the dining zone answered "w must be an integer in [1,20]",
  furniture_unzoned table 10 / chair 13 to H, dining seats 8 for 21 citizens;
- std OP1-3 (cxe60d4ce): A11 and every R room answered no_space from day 228 with 4 beds free, beds 14 for 16;
- live std OP1-4 (cx80e9f9d, day 251): one level's box A6 59x36, every R room a plot or a zone, beds/tables free;
- live std OP1-1 (cx80e9f9d, day 43): every R room soil -> farm first, no dorm dug, 10 beds free and 0 placed.
No network is used."""
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
        self.full = set()       # place_furniture answers no_space on these site ids
        self.sites = {}         # site id -> site (placements land at its corner row)

    def act(self, tool, args):
        args = dict(args)
        self.calls.append((tool, args))
        if tool == "place_furniture":
            if args.get("site") in self.full:
                return {"ok": False, "error_code": "no_space", "error": "no free floor tile"}
            k = args.get("count", 1)
            s = self.sites.get(args.get("site"), {"x": 80, "y": 101, "z": 159})
            at = [[s["x"] + i, s["y"], s["z"]] for i in range(k)]
            return {"ok": True, "result": {"n": k, "at": at if k > 1 else at[0]}}
        return {"ok": True, "result": {"order_id": 100 + len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {}}


# the live std OP1-4 level (cx80e9f9d, day 251): A6 is the whole z159 dug level
A6 = {"id": "A6", "kind": "A", "x": 68, "y": 91, "z": 159, "w": 59, "h": 36, "open_tiles": 145}


def R(rid, x, y, dug=True, used_by=None, designated=True, z=159, soil=True):
    r = {"id": rid, "kind": "R", "x": x, "y": y, "z": z, "w": 3, "h": 3, "soil": soil, "dug": dug,
         "designated": designated, "free": not used_by}
    if used_by:
        r["used_by"] = list(used_by)
    return r


def fur(kind, x, y, zone_ids=(), z=159):
    return {"built": True, "kind": kind, "x": x, "y": y, "z": z, "zone_ids": list(zone_ids)}


def obs(cit=16, sites=(), furniture=(), zones=(), free=None, day=251, pending=0, plots=(), stairs_s=()):
    st = {"plants_brewable": 6, "plants_total": 6, "food_edible": 200, "drink": 700, "beds": 22, "tables": 10,
          "chairs": 12, "barrels_empty": 10, "logs_usable": 300,
          "furniture_free": free if free is not None else {"bed": 0, "table": 0, "chair": 0}}
    return {"tick": day * harness.DAY, "day": day, "days_left": 336 - day, "observation": {
        "administrators": {"citizens": cit, "manager_active_for_orders": True, "MANAGER_id": 1},
        "stocks": st, "map": {"sites": list(sites) + list(stairs_s), "surface_z": 160}, "zones": list(zones),
        "furniture": list(furniture), "workshops": [], "orders": [], "farm_plots": list(plots),
        "dig_designations_pending": pending,
        "plugins": {"autochop": "on", "seedwatch": "on", "autofarm": "on"}, "date": {"abs_tick": day * harness.DAY}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, roles=None, days=336, **kw):
        game = FakeGame()
        o = harness.Overseer(game, goal="Run the fortress for a year.", days=days)
        o.load(obs(**kw))
        game.sites = {x["id"]: x for x in o.sites}
        o.roles.update(roles or {})
        o.count = 0
        return o, game

    @staticmethod
    def calls(game, tool, **match):
        return [a for t, a in game.calls if t == tool and all(a.get(k) == v for k, v in match.items())]


class BoxArguments(Base):
    def test_wide_site_is_clamped_to_each_tools_gate_and_a_dug_room_is_its_dug_box(self):
        o, _ = self.ov(sites=[A6, R("R7", 90, 96)])
        self.assertEqual(o.box_wh(A6, harness.PLACE_MAX), {"w": 40, "h": 36})
        self.assertEqual(o.box_wh(A6, harness.ZONE_MAX), {"w": 20, "h": 20})
        small = dict(A6, w=13, h=7)
        self.assertEqual(o.box_wh(small, harness.ZONE_MAX), {})   # the tool's own default: no extra arguments
        r7 = R("R7", 90, 96)
        self.assertEqual(o.box_wh(r7, harness.PLACE_MAX), {})
        o.note_room_box(r7, {"site": "R7", "w": 9, "h": 7})
        self.assertEqual(o.box_wh(r7, harness.PLACE_MAX), {"w": 9, "h": 7})

    def test_the_dormitory_room_is_furnished_and_zoned_as_dug(self):
        r1 = R("R1", 98, 98, used_by=None)
        o, game = self.ov(sites=[r1], roles={"R1": "dorm"}, free={"bed": 4, "table": 0, "chair": 0}, cit=4)
        o.note_room_box(r1, {"site": "R1", "w": 9, "h": 7})
        o.furnish()
        self.assertEqual(self.calls(game, "place_furniture", kind="bed")[0],
                         {"kind": "bed", "site": "R1", "count": 4, "w": 9, "h": 7})
        self.assertEqual(self.calls(game, "make_zone", kind="dormitory"),
                         [{"kind": "dormitory", "site": "R1", "w": 9, "h": 7}])


class LooseSeats(Base):
    STRAY = [fur("table", 79, 101), fur("table", 83, 102), fur("chair", 79, 102), fur("chair", 79, 103),
             fur("chair", 80, 103)]

    def test_stray_seats_on_a_wide_level_get_a_corner_zone_box(self):
        """live std OP1-4 day 251: 2 tables + 3 chairs unzoned on A6 (59x36) — rezone's whole-site zone is refused
        there (the 20 gate), so the box runs from A6's corner to the furthest stray."""
        o, game = self.ov(sites=[A6, R("R1", 98, 98, used_by=["Dormitory 9", "farm plot 24"])],
                          furniture=self.STRAY)
        o.rezone()
        self.assertEqual(self.calls(game, "make_zone", kind="dining_hall"),
                         [{"kind": "dining_hall", "site": "A6", "w": 16, "h": 13}])
        self.assertEqual(o.stray("table"), 2)
        self.assertEqual(o.stray("chair"), 3)

    def test_zoned_seats_and_unreachable_strays_ask_for_nothing(self):
        dining = {"id": 11, "type": "DiningHall", "x": 75, "y": 100, "z": 159, "w": 10, "h": 5}
        zoned = [dict(f, zone_ids=[11]) for f in self.STRAY]
        o, game = self.ov(sites=[A6], furniture=zoned, zones=[dining])
        o.rezone()
        self.assertEqual(self.calls(game, "make_zone"), [])
        # a stray 30 tiles from every zoneable corner: no box reaches it (R1 carries a plot and a zone)
        far = [fur("table", 100, 120), fur("chair", 101, 120)]
        o, game = self.ov(sites=[A6, R("R1", 98, 98, used_by=["farm plot 24"])], furniture=far)
        o.rezone()
        self.assertEqual(self.calls(game, "make_zone"), [])

    def test_stray_beds_get_a_dormitory_box(self):
        o, game = self.ov(sites=[A6], furniture=[fur("bed", 70, 92), fur("bed", 72, 92)])
        o.rezone()
        self.assertEqual(self.calls(game, "make_zone", kind="dormitory"),
                         [{"kind": "dormitory", "site": "A6", "w": 5, "h": 2}])

    def test_strays_raise_the_furniture_stock_target(self):
        o, game = self.ov(sites=[A6], furniture=self.STRAY, cit=16)
        o.st.update(tables=10, chairs=12)   # ceil(16/2)+2 = 10 tables: met without the strays
        o.seats_full = lambda: 0            # the strays alone (seats for all has its own test: test_stress_measured)
        o.supply()
        tables = self.calls(game, "add_order", recipe="make_table")
        self.assertEqual([a["amount"] for a in tables], [2])


class SeatSpread(Base):
    def test_seats_go_into_a_box_that_is_placed_and_zoned_together(self):
        """b796327 OP1-4 shape: seats short, free pairs, the level too wide for a whole-site zone."""
        o, game = self.ov(sites=[A6], free={"bed": 0, "table": 3, "chair": 3}, cit=16)
        o.furnish()
        t = self.calls(game, "place_furniture", kind="table")
        c = self.calls(game, "place_furniture", kind="chair")
        z = self.calls(game, "make_zone", kind="dining_hall")
        self.assertEqual(t, [{"kind": "table", "site": "A6", "w": 20, "h": 20, "count": 3}])
        self.assertEqual(c, [{"kind": "chair", "site": "A6", "w": 20, "h": 20, "count": 3}])
        self.assertEqual(z, [{"kind": "dining_hall", "site": "A6", "w": 20, "h": 20}])
        o.rezone()   # the pass's own zone covers what it placed: no second zone over the same seats
        self.assertEqual(len(self.calls(game, "make_zone", kind="dining_hall")), 1)

    def test_an_existing_dining_zone_box_is_filled_first_without_a_new_zone(self):
        r6 = R("R6", 97, 91, used_by=["DiningHall 60"])
        dining = {"id": 60, "type": "DiningHall", "x": 97, "y": 91, "z": 159, "w": 3, "h": 3,
                  "furniture": {"table": 1, "chair": 1}}
        o, game = self.ov(sites=[A6, r6], zones=[dining], free={"bed": 0, "table": 2, "chair": 2}, cit=16)
        o.seat_spread(9)
        self.assertEqual(self.calls(game, "place_furniture", kind="table")[0]["site"], "R6")
        self.assertEqual(self.calls(game, "make_zone"), [])

    def test_refused_boxes_rest_and_a_pass_of_refusals_arms_the_floor_dig(self):
        o, game = self.ov(sites=[A6], free={"bed": 0, "table": 3, "chair": 3}, cit=16)
        game.full.add("A6")
        o.seat_spread(9)
        self.assertEqual(o.house_full_day, 251)
        n = len(game.calls)
        o.now += harness.DAY
        o.day += 1
        o.seat_spread(9)   # the refused box rests SURGE_BED_RETRY_DAYS
        self.assertEqual(len(game.calls), n)

    def test_no_pairs_or_enough_seats_places_nothing(self):
        o, game = self.ov(sites=[A6], free={"bed": 0, "table": 3, "chair": 0}, cit=16)
        o.seat_spread(9)
        self.assertEqual(game.calls, [])


class HouseFloor(Base):
    S1 = {"id": "S1", "kind": "S", "x": 130, "y": 120, "z": 160, "w": 1, "h": 1, "soil": True}

    def test_open_play_digs_a_people_room_when_free_beds_found_no_floor(self):
        r9 = R("R9", 60, 80, dug=False, designated=False)
        o, game = self.ov(sites=[A6, r9], free={"bed": 5, "table": 0, "chair": 0}, cit=16)
        o.house_full_day = 250
        o.house_floor(0)
        self.assertEqual(self.calls(game, "dig_room"), [{"site": "R9", "w": 9, "h": 7}])
        self.assertEqual(o.roles["R9"], "house")
        self.assertEqual(o.room_box["R9"]["w"], 9)

    def test_no_r_site_digs_a_shaft_to_a_new_level(self):
        o, game = self.ov(sites=[A6], stairs_s=[self.S1], free={"bed": 5, "table": 0, "chair": 0}, cit=16)
        o.house_full_day = 251
        o.house_floor(0)
        self.assertEqual(self.calls(game, "dig_stairs"), [{"site": "S1", "z_bottom": 158}])

    def test_waits_without_a_refusal_a_pending_dig_or_items(self):
        r9 = R("R9", 60, 80, dug=False, designated=False)
        o, game = self.ov(sites=[A6, r9], free={"bed": 5, "table": 0, "chair": 0}, cit=16)
        o.house_floor(0)                       # no refusal recorded
        o.house_full_day = 240
        o.house_floor(0)                       # an old refusal
        o.house_full_day = 251
        o.house_floor(harness.HOUSE_PENDING_MAX)   # a room is being dug
        o.free = {"bed": 0, "table": 0, "chair": 0}
        o.house_floor(0)                       # nothing waits
        self.assertEqual(game.calls, [])

    def test_lab_and_surge_shapes_keep_their_own_floor_rules(self):
        r9 = R("R9", 60, 80, dug=False, designated=False)
        o, game = self.ov(sites=[A6, r9], free={"bed": 5, "table": 0, "chair": 0}, cit=16)
        o.house_full_day = 251
        o.hands_off = 10
        o.house_floor(0)
        self.assertEqual(game.calls, [])


class HouseFirst(Base):
    def test_blocked_housing_takes_the_next_soil_room_after_two_farms(self):
        """live std OP1-1 (80e9f9d): every R site soil; the farm loop took them all and no dorm was dug by day 43
        while 10 beds waited with no floor."""
        rs = [R("R%d" % i, 80 + 4 * i, 91, dug=False, designated=False) for i in range(1, 6)]
        o, game = self.ov(sites=rs, day=43, cit=7, free={"bed": 10, "table": 6, "chair": 8})
        o.house_full_day = 43
        o.digging()
        roles = [o.roles.get("R%d" % i) for i in range(1, 6)]
        self.assertEqual(roles[:2], ["farm", "farm"])
        self.assertEqual(roles[2:4], ["dorm", "dine"])
        self.assertEqual(roles[4], "farm")   # the farms resume once the people rooms are dug

    def test_unblocked_housing_keeps_the_farms_first(self):
        rs = [R("R%d" % i, 80 + 4 * i, 91, dug=False, designated=False) for i in range(1, 6)]
        o, game = self.ov(sites=rs, day=3, cit=7, free={"bed": 1, "table": 0, "chair": 0})
        o.digging()   # no refusal recorded: the leader's farm-first order stands
        self.assertEqual([o.roles.get("R%d" % i) for i in range(1, 6)], ["farm"] * 5)


class DineRoomTaken(Base):
    """hint hard OP1-4 on c44c96b: no dine room, the fallback dine was the dorm R3 (zoned Dormitory 62 in the same
    pass); from day 221 every free table and chair went into R3 and z_dine answered site_used — 14 tables + 13 chairs
    inside the dormitory, dining seats 9 for 19 citizens at H (housing 0.974)."""
    A3 = {"id": "A3", "kind": "A", "x": 60, "y": 80, "z": 150, "w": 40, "h": 29, "open_tiles": 120}   # wider than ZONE_MAX: room_for skips it

    def test_the_dorm_room_of_the_same_pass_takes_no_tables(self):
        r3 = R("R3", 98, 98)
        o, game = self.ov(sites=[r3, self.A3], roles={"R3": "dorm"}, cit=19,
                          free={"bed": 4, "table": 3, "chair": 3})
        o.furnish()
        self.assertEqual(self.calls(game, "make_zone", kind="dormitory")[0]["site"], "R3")
        self.assertEqual(self.calls(game, "place_furniture", kind="table", site="R3"), [])
        self.assertEqual(self.calls(game, "place_furniture", kind="chair", site="R3"), [])
        self.assertEqual(self.calls(game, "make_zone", kind="dining_hall", site="R3"), [])
        # the pairs go to a box that is zoned a dining hall in the same move
        self.assertEqual([a["site"] for a in self.calls(game, "place_furniture", kind="table")], ["A3"])
        self.assertEqual([a["site"] for a in self.calls(game, "make_zone", kind="dining_hall")], ["A3"])

    def test_a_dine_room_another_zone_holds_is_skipped(self):
        r3 = R("R3", 98, 98, used_by=["Dormitory 62"])
        o, game = self.ov(sites=[r3, self.A3], roles={"R3": "dine"}, cit=19,
                          free={"bed": 0, "table": 2, "chair": 2})
        self.assertFalse(o.dine_usable(r3))
        o.furnish()
        self.assertEqual(self.calls(game, "place_furniture", site="R3"), [])
        self.assertEqual(self.calls(game, "make_zone", site="R3"), [])

    def test_a_free_or_dining_held_dine_room_still_serves(self):
        r4 = R("R4", 90, 90)
        o, _ = self.ov(sites=[r4])
        self.assertTrue(o.dine_usable(r4))
        self.assertTrue(o.dine_usable(R("R5", 90, 95, used_by=["DiningHall 58"])))
        self.assertFalse(o.dine_usable(R("R6", 90, 99, used_by=["Office 65"])))
        self.assertTrue(o.dine_usable(self.A3, dorm=self.A3))   # an A site takes a second zone

    def test_the_closer_orders_seats_when_the_stock_sits_in_a_dormitory(self):
        dorm = {"id": 62, "type": "Dormitory", "x": 98, "y": 98, "z": 159, "w": 9, "h": 7,
                "furniture": {"bed": 4, "table": 14, "chair": 13}}
        dining = {"id": 58, "type": "DiningHall", "x": 60, "y": 80, "z": 150, "w": 20, "h": 20,
                  "furniture": {"table": 9, "chair": 10}}
        o, game = self.ov(sites=[self.A3], zones=[dorm, dining], cit=19, day=300,
                          free={"bed": 0, "table": 0, "chair": 0})
        o.st.update(tables=22, chairs=22, beds=21)
        o.placed["bed"] = 21
        self.assertEqual(o.seats(), 9)
        o.housing_check()
        self.assertEqual([a["amount"] for a in self.calls(game, "add_order", recipe="make_table")], [2])
        self.assertEqual([a["amount"] for a in self.calls(game, "add_order", recipe="make_chair")], [1])


if __name__ == "__main__":
    unittest.main()
