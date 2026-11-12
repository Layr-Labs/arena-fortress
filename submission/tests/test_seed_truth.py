"""cx: the layer reads its seeds without the ghosts, and does not lay plots on a people room's floor.

Measured shapes (no game or network is used):
- hint hard LT02-2 on 02a3eea: the SEEDS query held plump helmet 3 / cave wheat 3 / dimple cup 2 / pig tail 2 /
  quarry bush 2 / sweet pod 2 on day 0 and only cave wheat 3 / quarry bush 2 on day 1 (no kitchen, plot or job yet);
  the observation's seeds_by_kind listed all 14 until day 14-17. On 9a8a399 LT02-0 autofarm set plump helmet /
  dimple cup / sweet pod on plots 9-11 and 20 (day 10-14), and none of them ever held a seed.
- hint hard LT02-0 on 9a8a399: R1 (site 97,97 z112, 3x3) dug 9x7 as the dormitory on day 3; F1 (97,100), F2 (99,97),
  F3 (100,100), F4 (102,97), F5 (103,100) listed on its floor from day 8; five plots built there; place_furniture
  on R1 answered "room R1 is already used (farm plot 9)" 61 times.
"""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_fruit_watch import FakeGame, LT02_KINDS, DAY6_SEEDS, fort, early, Base   # noqa: E402

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class LiveSeeds(Base):
    def censused(self, day, kinds=LT02_KINDS):
        game = FakeGame({"SEEDS": DAY6_SEEDS})
        ov = self.overseer(game)
        ov.load(early(day=day, kinds=kinds))
        ov.seed_census()
        return ov

    def test_ghosts_leave_the_live_view(self):
        ov = self.censused(1)
        self.assertEqual(sorted(ov.live_seeds_by_kind()), ["cave wheat", "quarry bush"])
        self.assertEqual(ov.live_seeds_by_kind()["cave wheat"]["n"], 3)
        self.assertEqual(ov.live_seeds_by_kind()["cave wheat"]["seasons"], ["summer", "autumn"])

    def test_without_a_census_the_observation_stands(self):
        ov = self.overseer()
        ov.load(early(day=1))
        self.assertEqual(ov.live_seeds_by_kind(), LT02_KINDS)

    def test_a_stale_census_does_not_cut(self):
        ov = self.censused(1)
        ov.load(early(day=1 + harness.SEED_CENSUS_DAYS + 1))
        self.assertEqual(ov.live_seeds_by_kind(), LT02_KINDS)

    def test_rush_reads_the_live_seeds(self):
        # the live spring underground seed is quarry bush: the rush stays on
        self.assertTrue(self.censused(1).seed_rush())
        # with only cave wheat (summer / autumn) live in spring there is nothing to plant now: no rush
        game = FakeGame({"SEEDS": DAY6_SEEDS[:1]})
        ov = self.overseer(game)
        ov.load(early(day=1))
        ov.seed_census()
        self.assertEqual(sorted(ov.live_seeds_by_kind()), ["cave wheat"])
        self.assertFalse(ov.seed_rush())

    def test_harvest_closed_from_the_live_seeds(self):
        # day 40 of a 90-day run from doy 19: plump helmet (all seasons) would ripen in time, cave wheat cannot
        # (summer from doy 84 = run day 65, plus HOLD_GROW_DAYS > the run's end)
        ov = self.overseer()
        ov.load(early(day=40, hands_off=29))
        self.assertFalse(ov.harvest_closed())
        game = FakeGame({"SEEDS": DAY6_SEEDS[:1]})
        ov = self.overseer(game)
        ov.load(early(day=40, hands_off=29))
        ov.seed_census()
        self.assertTrue(ov.harvest_closed())


R1 = {"id": "R1", "kind": "R", "x": 97, "y": 97, "z": 112, "w": 3, "h": 3, "soil": False, "subterranean": True}
R2 = {"id": "R2", "kind": "R", "x": 93, "y": 97, "z": 112, "w": 3, "h": 3, "soil": True, "subterranean": True}
F_IN_R1 = [{"id": "F%d" % i, "kind": "F", "x": x, "y": y, "z": 112, "w": 3, "h": 3, "soil": True,
            "subterranean": True} for i, (x, y) in enumerate([(97, 100), (99, 97), (100, 100), (102, 97)], 1)]
F_OUT = {"id": "F9", "kind": "F", "x": 120, "y": 120, "z": 112, "w": 3, "h": 3, "soil": True, "subterranean": True}


class FarmOffPeopleRooms(Base):
    def dorm_ov(self, game, sites, plots=()):
        ov = self.overseer(game)
        ov.load(early(day=8, sites=sites, plots=plots, drink=40))
        ov.roles = {"R1": "dorm"}
        ov.note_room_box(R1, {"w": 9, "h": 7})
        return ov

    def built(self, game):
        return [a["site"] for t, a in game.calls if t == "build_farm"]

    def test_digging_records_the_dorm_box(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(early(day=3, sites=[R1, R2], drink=40))   # no rush: the dorm is dug with the farms
        ov.digging()
        self.assertEqual(ov.roles.get("R1"), "dorm")
        self.assertEqual(ov.room_box["R1"], {"x": 97, "y": 97, "z": 112, "w": 9, "h": 7})
        self.assertNotIn("R2", ov.room_box)   # a farm room is not a people room

    def test_f_sites_on_the_dorm_floor_are_skipped_for_one_outside(self):
        game = FakeGame()
        ov = self.dorm_ov(game, F_IN_R1 + [F_OUT])
        with redirect_stdout(io.StringIO()) as out:
            ov.farms()
        self.assertEqual(self.built(game), ["F9"])
        self.assertIn('"farm_site_in_room"', out.getvalue())

    def test_only_the_dorm_floor_left_and_no_plot_takes_one(self):
        game = FakeGame()
        ov = self.dorm_ov(game, F_IN_R1)
        ov.farms()
        self.assertEqual(self.built(game), ["F1"])

    def test_only_the_dorm_floor_left_with_a_plot_takes_none(self):
        game = FakeGame()
        ov = self.dorm_ov(game, F_IN_R1, plots=[{"id": 8, "built": True, "x": 120, "y": 120, "z": 112}])
        ov.farms()
        self.assertEqual(self.built(game), [])

    def test_a_farm_room_box_never_blocks(self):
        game = FakeGame()
        ov = self.dorm_ov(game, F_IN_R1)
        ov.roles = {"R1": "farm"}
        ov.farms()
        self.assertTrue(set(self.built(game)) <= {f["id"] for f in F_IN_R1})
        self.assertGreater(len(self.built(game)), 1)


# a survivor set where a fast brewable lives: the setup's shortage.lua removes whole seed bags (one bag per kind on
# the hint/dev hard LT02 forts), so on another fort plump helmet 1 + sweet pod 1 can be what is left
PH_SP = {"plump helmet": dict(LT02_KINDS["plump helmet"], n=1), "sweet pod": dict(LT02_KINDS["sweet pod"], n=1)}
PH_SP_QUERY = [{"material": "PLANT:MUSHROOM_HELMET_PLUMP:SEED", "items": 1, "count": 1, "in_inventory": 1},
               {"material": "PLANT:POD_SWEET:SEED", "items": 1, "count": 1, "in_inventory": 1}]


class FastBrewableSurvivor(Base):
    def test_rush_digs_the_farm_rooms_first_and_plants_on_the_day_the_plot_stands(self):
        from test_fruit_watch import DAY2_SITES, F_SITE
        game = FakeGame({"SEEDS": PH_SP_QUERY})
        ov = self.overseer(game)
        ov.load(early(day=1, kinds=PH_SP))
        ov.seed_census()
        self.assertEqual(sorted(ov.live_seeds_by_kind()), ["plump helmet", "sweet pod"])
        self.assertTrue(ov.seed_rush())
        ov.digging()
        digs = [a.get("site") for t, a in game.calls if t == "dig_room"]
        self.assertEqual(sorted(digs), ["R1", "R2"])   # the soil rooms; the dorm (R3) waits
        game.calls.clear()
        ov.load(early(day=4, kinds=PH_SP, sites=DAY2_SITES + [F_SITE]))
        ov.farms()
        tools = [t for t, _ in game.calls]
        self.assertIn("build_farm", tools)
        self.assertIn("enable_automation", tools)   # autofarm sets the in-season crop in the same pass

    def test_a_lab_brew_standing_takes_the_first_plant(self):
        ov = self.overseer()
        ov.load(early(day=30, kinds=PH_SP, hands_off=39))
        when = {c["stock"]: c for c in ov.brew_when()}
        self.assertEqual(when["plants_brewable"]["at_least"], 1)
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(early(day=30, kinds=PH_SP, hands_off=39))
        ov.supply()
        brew = [a for t, a in game.calls if a.get("recipe") == "brew_drink" and a.get("repeat")]
        self.assertTrue(brew)
        self.assertIn({"stock": "plants_brewable", "at_least": 1}, brew[0]["when"])

    def test_open_play_keeps_its_floor(self):
        ov = self.overseer(days=336)
        r = early(day=30, kinds=PH_SP)
        r["hands_off_in_days"] = None
        ov.load(r)
        self.assertGreaterEqual(ov.brew_floor(), 2)


if __name__ == "__main__":
    unittest.main()
