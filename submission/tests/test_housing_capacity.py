"""Regressions for the housing-capacity planner, the batched furniture orders and the pre-window plant reserve.
No game or network is used."""
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
    """place_furniture puts at most `room[site]` items in a site (then answers like DF: n < requested, or no_space)."""

    def __init__(self, room=None, z=None):
        self.calls = []
        self.room = dict(room or {})
        self.z = dict(z or {})   # site -> z of the tiles it places on

    def act(self, tool, args):
        self.calls.append((tool, copy.deepcopy(args)))
        if tool == "place_furniture":
            left = self.room.get(args["site"], 99)
            n = min(left, args.get("count", 1))
            if n <= 0:
                return {"ok": False, "error_code": "no_space", "error": "no free floor tile"}
            self.room[args["site"]] = left - n
            at = [[100 + i, 10, self.z.get(args["site"], 5)] for i in range(n)]
            return {"ok": True, "result": {"placed": args["kind"], "n": n, "requested": args.get("count", 1),
                                           "available": 99, "at": at}}
        if tool in ("add_order", "add_manager_order"):
            return {"ok": True, "result": {"order_id": len(self.calls)}}
        return {"ok": True, "result": {}}

    def query(self, name, **kw):
        return {"result": {}}


def site(id, kind=None, x=100, y=10, z=5, w=9, h=7, **kw):
    return {"id": id, "kind": kind or id[0], "x": x, "y": y, "z": z, "w": w, "h": h, **kw}


def obs(sites, cit=30, free=None, furniture=(), stocks=None, day=20, days_left=200, hands_off=None, **extra):
    st = {"furniture_free": free or {}, "logs_usable": 100, **(stocks or {})}
    o = {"administrators": {"citizens": cit}, "map": {"sites": copy.deepcopy(sites), "surface_z": 8},
         "furniture": copy.deepcopy(list(furniture)), "stocks": st, "zones": [], "orders": [], **extra}
    r = {"tick": day * harness.DAY, "day": day, "days_left": days_left, "observation": o}
    if hands_off is not None:
        r["hands_off_in_days"] = hands_off
    return r


class Base(unittest.TestCase):
    def setUp(self):
        out = redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def make(self, goal="", days=336, room=None, z=None):
        self.game = FakeGame(room, z)
        self.ov = harness.Overseer(self.game, goal=goal, days=days)
        self.ov.count = 0
        return self.ov

    def calls(self, tool):
        return [a for t, a in self.game.calls if t == tool]


class Fullness(Base):
    def test_short_placement_marks_the_area_full_and_beds_overflow_to_the_next_level(self):
        ov = self.make(room={"A1": 4}, z={"A2": 4})
        ov.roles = {"R1": "dorm"}
        ov.load(obs([site("A1", z=5, open_tiles=40), site("A2", z=4, open_tiles=50),
                     site("R1", z=5, w=3, h=3, dug=True, designated=True)], free={"bed": 10}))
        ov.furnish()
        beds = [a for a in self.calls("place_furniture") if a["kind"] == "bed"]
        self.assertEqual([a["site"] for a in beds], ["A1", "A2"])
        self.assertEqual(beds[1]["count"], 6)
        self.assertTrue(ov.is_full(site("A1", open_tiles=40)))
        self.assertIn({"kind": "dormitory", "site": "A2"}, self.calls("make_zone"))

    def test_an_area_is_not_full_once_more_of_it_is_dug(self):
        ov = self.make()
        ov.mark_full(site("A1", open_tiles=40))
        self.assertTrue(ov.is_full(site("A1", open_tiles=40)))
        self.assertFalse(ov.is_full(site("A1", open_tiles=60)))

    def test_no_space_marks_full(self):
        ov = self.make(room={"A1": 0})
        ov.roles = {"R1": "dorm"}
        ov.load(obs([site("A1", open_tiles=40), site("R1", w=3, h=3, dug=True, designated=True)], free={"bed": 3}))
        ov.furnish()
        self.assertTrue(ov.is_full(site("A1", open_tiles=40)))


class SeatsWaitForBeds(Base):
    def test_seats_take_only_the_floor_beds_do_not_still_need(self):
        ov = self.make()
        ov.roles = {"R1": "dorm"}
        # 20 free tiles, 30 citizens, no beds made yet: the beds still need 32 tiles, so no seats are placed
        ov.load(obs([site("A1", open_tiles=20), site("R1", w=3, h=3, dug=True, designated=True)],
                    free={"table": 10, "chair": 10}))
        ov.furnish()
        self.assertEqual([a for a in self.calls("place_furniture") if a["kind"] in ("table", "chair")], [])

    def test_seats_are_placed_once_beds_are_covered(self):
        ov = self.make()
        ov.roles = {"R1": "dorm"}
        beds = [{"kind": "bed", "x": 100 + i % 9, "y": 10 + i // 9, "z": 5, "built": True} for i in range(32)]
        ov.load(obs([site("A1", w=20, h=10, open_tiles=120), site("R1", w=3, h=3, dug=True, designated=True)],
                    free={"table": 10, "chair": 10}, furniture=beds))
        ov.furnish()
        kinds = [a["kind"] for a in self.calls("place_furniture")]
        self.assertIn("table", kinds)
        self.assertIn("chair", kinds)


class SurgeSeats(Base):
    def test_a_migrant_task_places_no_seats_while_beds_are_short(self):
        ov = self.make(goal="Migrants are arriving.", days=60)
        ov.roles = {"R1": "dorm"}
        ov.load(obs([site("A1", w=20, h=10, open_tiles=150), site("R1", w=3, h=3, dug=True, designated=True)],
                    free={"table": 10, "chair": 10}, hands_off=30))
        ov.furnish()
        self.assertEqual([a for a in self.calls("place_furniture") if a["kind"] in ("table", "chair")], [])


class NoDormRole(Base):
    def test_beds_go_to_the_expansion_room_when_no_room_has_the_dorm_role(self):
        ov = self.make()
        ov.roles = {"R1": "house", "R2": "farm"}
        ov.load(obs([site("A1", x=100, y=10, z=5, w=9, h=7, open_tiles=63),
                     site("R1", x=100, y=10, z=5, w=3, h=3, dug=True, designated=True)], cit=20, free={"bed": 10}))
        ov.furnish()
        self.assertIn({"kind": "bed", "site": "A1", "count": 10}, self.calls("place_furniture"))


class Expansion(Base):
    def test_digs_a_room_on_a_non_soil_site_once_floor_has_run_out(self):
        ov = self.make()
        ov.mark_full(site("A1", open_tiles=20))
        ov.load(obs([site("A1", open_tiles=20), site("R5", w=3, h=3, soil=True, designated=False),
                     site("R6", w=3, h=3, soil=False, designated=False)]))
        ov.expand()
        self.assertEqual(self.calls("dig_room"), [{"site": "R6", **harness.HOUSE_DIG}])
        self.assertEqual(ov.roles.get("R6"), "house")

    def test_an_open_run_digs_nothing_before_floor_runs_out(self):
        ov = self.make()
        ov.load(obs([site("A1", open_tiles=20), site("R6", w=3, h=3, designated=False)]))
        ov.expand()
        self.assertEqual(self.calls("dig_room"), [])

    def test_a_migrant_task_digs_ahead(self):
        ov = self.make(goal="Migrants are arriving.", days=60)
        ov.load(obs([site("A1", open_tiles=20), site("R6", w=3, h=3, designated=False)], hands_off=30))
        ov.expand()
        self.assertEqual(self.calls("dig_room"), [{"site": "R6", **harness.HOUSE_DIG}])

    def test_never_with_water_on_the_fort_levels(self):
        ov = self.make(goal="Migrants are arriving.", days=60)
        ov.load(obs([site("A1", open_tiles=20), site("R6", w=3, h=3, designated=False)], hands_off=30,
                    water_on_fort_levels={"tiles": 4}))
        ov.expand()
        self.assertEqual(self.calls("dig_room"), [])

    def test_one_expansion_at_a_time(self):
        ov = self.make(goal="Migrants are arriving.", days=60)
        ov.roles = {"R6": "house"}
        ov.load(obs([site("A1", open_tiles=20), site("R6", w=3, h=3, designated=True, dug=False),
                     site("R7", w=3, h=3, designated=False)], hands_off=30))
        ov.expand()
        self.assertEqual(self.calls("dig_room"), [])

    def test_enough_floor_digs_nothing(self):
        ov = self.make(goal="Migrants are arriving.", days=60)
        ov.load(obs([site("A1", w=20, h=15, open_tiles=300), site("R6", w=3, h=3, designated=False)], cit=10,
                    hands_off=30))
        ov.expand()
        self.assertEqual(self.calls("dig_room"), [])

    def test_no_room_site_left_digs_no_stairs(self):
        ov = self.make(goal="Migrants are arriving.", days=60)
        ov.load(obs([site("A1", open_tiles=20), site("S1", w=1, h=1)], hands_off=30))
        ov.expand()
        self.assertEqual(self.calls("dig_stairs"), [])


class Orders(Base):
    def test_bed_shortfall_is_one_order(self):
        ov = self.make()
        ov.load(obs([site("W1")], cit=40, stocks={"beds": 10, "tables": 30, "chairs": 30}))
        ov.supply()
        beds = [a for a in self.calls("add_order") if a["recipe"] == "make_bed"]
        self.assertEqual(beds, [{"recipe": "make_bed", "amount": 30}])

    def test_migrant_task_orders_beds_before_seats(self):
        ov = self.make(goal="Migrants are arriving.", days=60)
        ov.load(obs([site("W1")], cit=40, stocks={"beds": 19, "tables": 0, "chairs": 0}, hands_off=30))
        ov.supply()
        recipes = [a["recipe"] for a in self.calls("add_order")]
        self.assertIn("make_bed", recipes)
        self.assertNotIn("make_table", recipes)
        self.assertNotIn("make_chair", recipes)


class PlantReserve(Base):
    def test_plenty_of_other_food_releases_the_plants(self):
        ov = self.make(goal="Migrants are arriving.", days=60)
        ov.load(obs([], cit=45, stocks={"food_edible": 100, "plants_brewable": 6}, days_left=30, hands_off=9))
        self.assertEqual(ov.plant_reserve(), 1)

    def test_short_food_keeps_the_old_reserve(self):
        ov = self.make(goal="", days=60)
        ov.load(obs([], cit=45, stocks={"food_edible": 20, "plants_brewable": 6}, days_left=30, hands_off=9))
        self.assertEqual(ov.plant_reserve(), 22)


class Office(Base):
    def office_obs(self, zones, sites, free=None):
        r = obs(sites, cit=24, free=free or {"chair": 1})
        r["observation"]["administrators"].update({"manager_active_for_orders": True, "MANAGER_id": 86,
                                                   "manager_office": {"zone_id": 51, "chair": False}})
        r["observation"]["zones"] = zones
        return r

    def test_a_one_tile_office_on_a_stair_landing_is_moved_and_assigned(self):
        ov = self.make()
        self.game.act = self.with_zone_id(self.game.act)
        ov.load(self.office_obs([{"id": 51, "type": "Office", "x": 93, "y": 95, "z": 3, "w": 1, "h": 1, "owner": 86}],
                                [site("A5", x=93, y=95, z=3, w=1, h=1, open_tiles=1),
                                 site("A7", x=90, y=90, z=4, w=9, h=7, open_tiles=50)]))
        ov.office()
        self.assertIn(("make_zone", {"kind": "office", "site": "A7"}), self.game.calls)
        self.assertIn(("place_furniture", {"kind": "chair", "site": "A7"}), self.game.calls)
        self.assertIn(("assign_zone", {"zone_id": 777, "dwarf_id": 86}), self.game.calls)

    def test_a_new_office_never_goes_on_a_stair_only_area(self):
        ov = self.make()
        r = self.office_obs([], [site("A5", x=93, y=95, z=3, w=1, h=1, open_tiles=1),
                                 site("A7", x=90, y=90, z=4, w=9, h=7, open_tiles=50)])
        r["observation"]["administrators"]["manager_office"] = "none"
        ov.load(r)
        ov.office()
        self.assertEqual(self.calls("make_zone"), [{"kind": "office", "site": "A7"}])

    def test_a_usable_office_just_gets_its_chair(self):
        ov = self.make()
        ov.load(self.office_obs([{"id": 51, "type": "Office", "x": 90, "y": 90, "z": 4, "w": 9, "h": 7, "owner": 86}],
                                [site("A7", x=90, y=90, z=4, w=9, h=7, open_tiles=50)]))
        ov.office()
        self.assertEqual(self.game.calls, [("place_furniture", {"kind": "chair", "site": "A7"})])

    @staticmethod
    def with_zone_id(act):
        def wrapped(tool, args):
            r = act(tool, args)
            if tool == "make_zone":
                r = {"ok": True, "result": {"zone_id": 777}}
            return r
        return wrapped


class EndgameBrew(Base):
    def test_surplus_brewing_is_guarded_by_food_and_short_drink_brews_from_any_plant(self):
        ov = self.make(days=216)
        ov.load(obs([], cit=19, stocks={"food_edible": 113, "drink": 400}, days_left=40))
        ov.endgame_supply()
        brews = {tuple((w["stock"], "below" if "below" in w else "at_least", w.get("below", w.get("at_least")))
                       for w in a["when"]) for a in self.calls("add_order") if a["recipe"] == "brew_drink"}
        self.assertEqual(brews, {
            (("drink", "below", 228), ("plants_brewable", "at_least", 2), ("barrels_empty", "at_least", 1)),
            (("drink", "below", 380), ("food_edible", "at_least", 152), ("barrels_empty", "at_least", 1)),
            (("drink", "below", 600), ("food_edible", "at_least", 228), ("barrels_empty", "at_least", 1))})


class LateFood(Base):
    def run_endgame(self, days, days_left, food, cit=17):
        ov = self.make(days=days)
        self.game.query = lambda name, **kw: {"result": {"units": [
            {"id": 93, "tame": True, "pet_owner_id": None, "marked_for_slaughter": False}]}}
        r = obs([site("W1")], cit=cit, stocks={"food_edible": food, "drink": 300, "logs_usable": 50}, days_left=days_left)
        r["observation"]["workshops"] = [{"type": "Butchers", "built": True}]
        ov.load(r)
        ov.endgame_supply()
        return self.calls("slaughter")

    def test_slaughters_in_the_last_two_weeks_while_food_is_short(self):
        self.assertEqual(self.run_endgame(216, 10, food=69), [{"unit_id": 93}])

    def test_not_before_the_last_two_weeks(self):
        self.assertEqual(self.run_endgame(216, 30, food=69), [])

    def test_not_with_ample_food(self):
        self.assertEqual(self.run_endgame(216, 10, food=900), [])

    def test_not_on_short_tasks(self):
        self.assertEqual(self.run_endgame(60, 10, food=69), [])


if __name__ == "__main__":
    unittest.main()
