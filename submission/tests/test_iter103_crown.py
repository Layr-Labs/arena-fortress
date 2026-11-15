"""Regression tests for Iter103 Master Pareto Crown mechanisms."""
import unittest

from support import StubGame, bare
from overseer.harness import Overseer, PROG_WEALTH, SURGE_BEDS, FULL_YEAR_BEDS


class NoSpaceGame(StubGame):
    def __init__(self, full_sites):
        super().__init__()
        self.full_sites = set(full_sites)

    def act(self, tool, args):
        if tool == "place_furniture" and args.get("site") in self.full_sites:
            self.calls.append((tool, dict(args)))
            return {"ok": False, "error_code": "no_space", "error": "no space"}
        res = super().act(tool, args)
        if tool == "make_zone" and res.get("ok"):
            res["result"]["zone_id"] = 808
        return res


class Iter103CrownTests(unittest.TestCase):
    def test_constants_and_clean_dining_contract(self):
        self.assertEqual(SURGE_BEDS, 56)
        self.assertEqual(PROG_WEALTH, 5500)
        self.assertEqual(FULL_YEAR_BEDS, 25)
        self.assertFalse(hasattr(Overseer, "extra_dining_ready"))

    def test_office_skips_farm_plots_prefers_stone_and_remembers_no_space(self):
        resp = bare(150, 186, fishing=False, cit=18)
        o = resp["observation"]
        o["administrators"].update(MANAGER_id=41, manager_office={"zone_id": 11, "chair": False})
        o["zones"] = [{"id": 11, "type": "Office", "owner": 41, "x": 96, "y": 93, "z": 104, "furniture": {}}]
        o["stocks"]["furniture_free"] = {"chair": 1}
        o["farm_plots"] = [{"id": 4, "x": 97, "y": 94, "z": 105, "w": 3, "h": 3, "built": True}]
        o["map"]["sites"] = [
            {"id": "A4", "kind": "A", "x": 96, "y": 93, "z": 105, "w": 7, "h": 5, "open_tiles": 12, "soil": True},
            {"id": "A6", "kind": "A", "x": 96, "y": 93, "z": 104, "w": 7, "h": 5, "open_tiles": 12, "soil": True},
            {"id": "A8", "kind": "A", "x": 96, "y": 93, "z": 102, "w": 7, "h": 5, "open_tiles": 12, "soil": False},
        ]
        game = NoSpaceGame({"A6"})
        ov = Overseer(game, days=336)
        ov.load(resp)
        ov.count = 0
        ov.office()
        self.assertIn("A6", ov.office_full)
        ov.now += 1200
        ov.load(resp)
        ov.count = 0
        ov.office()
        self.assertIn({"kind": "office", "site": "A8"}, game.tools("make_zone"))
        self.assertIn({"kind": "chair", "site": "A8"}, game.tools("place_furniture"))

    def test_open_play_never_steals_dining_hall_chair_for_office(self):
        resp = bare(200, 10, fishing=False, cit=22)
        o = resp["observation"]
        o["administrators"].update(MANAGER_id=77, manager_office=None)
        o["zones"] = [{"id": 5, "type": "DiningHall", "x": 88, "y": 94, "z": 103, "w": 16, "h": 6,
                       "furniture": {"table": 12, "chair": 12}}]
        o["furniture"] = [
            {"id": 21, "kind": "chair", "built": True, "zone_ids": [5], "x": 91, "y": 96, "z": 103}
        ]
        o["stocks"].update(logs_usable=10, beds=24, tables=12, chairs=12, furniture_free={"chair": 0})
        o["map"]["sites"] = [{"id": "A8", "kind": "A", "x": 88, "y": 94, "z": 103, "w": 16, "h": 6, "open_tiles": 20}]
        game = StubGame()
        ov = Overseer(game, days=336)
        ov.load(resp)
        ov.count = 0
        self.assertFalse(ov.office_over_chair(77, []))

    def test_open_task_bed_overflow_on_no_space_places_and_zones_backup_dorm(self):
        resp = bare(30, 138, fishing=False, cit=18)
        o = resp["observation"]
        o["stocks"]["furniture_free"] = {"bed": 6, "chair": 0, "table": 0}
        o["furniture"] = [{"id": i, "kind": "bed", "built": True, "x": 90, "y": 90 + (i % 4), "z": 103}
                          for i in range(14)]
        o["stocks"]["furniture_placed"] = {"bed": 14}
        o["map"]["sites"] = [
            {"id": "A1", "kind": "A", "x": 88, "y": 88, "z": 103, "w": 8, "h": 8, "open_tiles": 10, "soil": False},
            {"id": "A2", "kind": "A", "x": 88, "y": 88, "z": 102, "w": 9, "h": 9, "open_tiles": 18, "soil": False},
        ]
        game = NoSpaceGame({"A1"})
        ov = Overseer(game, days=168)
        ov.load(resp)
        ov.count = 0
        ov.furnish()
        self.assertIn("A1", ov.dorm_full)
        self.assertTrue(any(c.get("site") == "A2" and c.get("kind") == "bed" for c in game.tools("place_furniture")))
        self.assertIn({"kind": "dormitory", "site": "A2"}, game.tools("make_zone"))

    def test_feast_skips_kitchen_boiloff_when_food_abundant_and_drink_tight(self):
        resp = bare(10, 326, fishing=False, cit=13)
        o = resp["observation"]
        o["stocks"].update(drink=236, food_edible=195, prepared_meals=54, plants_total=5, plants_brewable=5, barrels_empty=16)
        game = StubGame()
        ov = Overseer(game, days=336)
        ov.load(resp)
        ov.count = 0
        ov.feast()
        cook_calls = [c for c in game.tools("add_order") if c.get("recipe") == "cook_meal"]
        self.assertEqual(cook_calls, [])

    def test_thaw_alert_never_stands_down_armed_squad_facing_hostiles(self):
        resp = bare(1, 335, fishing=False, cit=18)
        o = resp["observation"]
        o["threats"] = {"visible_hostiles": 1, "hostiles": [{"id": 9, "invader": True}]}
        o["military"] = {"squads": [{"id": 1, "uniform": "leather", "armed": 2, "orders": ["attack"]}]}
        o["burrows"] = {"civilian_alert": True, "list": [{"id": 1, "civ_alert_burrow": True}]}
        game = StubGame()
        ov = Overseer(game, days=336)
        ov.thaw_alert = True
        ov.load(resp)
        ov.count = 0
        ov.defend()
        self.assertNotIn({"order": "stand_down"}, game.tools("squad_order"))


if __name__ == "__main__":
    unittest.main()
