"""Regression tests for Iter102 Master Pareto mechanisms."""
import unittest

from support import StubGame, bare
from overseer.harness import Overseer, SURGE_BEDS


class NoSpaceChairGame(StubGame):
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


class Iter102ParetoTests(unittest.TestCase):
    def test_surge_beds_target_is_56(self):
        self.assertEqual(SURGE_BEDS, 56)

    def test_office_skips_farm_plots_prefers_stone_and_remembers_no_space(self):
        resp = bare(150, 186, fishing=False, cit=18)
        o = resp["observation"]
        o["administrators"].update(MANAGER_id=41, manager_office={"zone_id": 11, "chair": False})
        o["zones"] = [{"id": 11, "type": "Office", "owner": 41, "x": 96, "y": 93, "z": 105, "furniture": {}}]
        o["stocks"]["furniture_free"] = {"chair": 1}
        o["farm_plots"] = [{"id": 4, "x": 97, "y": 94, "z": 105, "w": 3, "h": 3, "built": True}]
        o["map"]["sites"] = [
            {"id": "A4", "kind": "A", "x": 96, "y": 93, "z": 105, "w": 7, "h": 5, "open_tiles": 12, "soil": True},
            {"id": "A6", "kind": "A", "x": 96, "y": 93, "z": 104, "w": 7, "h": 5, "open_tiles": 12, "soil": True},
            {"id": "A8", "kind": "A", "x": 96, "y": 93, "z": 102, "w": 7, "h": 5, "open_tiles": 12, "soil": False},
        ]
        game = NoSpaceChairGame({"A4"})
        ov = Overseer(game, days=336)
        ov.load(resp)
        ov.count = 0
        ov.office()
        self.assertIn("A4", ov.office_full)
        ov.now += 1200
        ov.load(resp)
        ov.count = 0
        ov.office()
        self.assertIn({"kind": "office", "site": "A8"}, game.tools("make_zone"))
        self.assertIn({"kind": "chair", "site": "A8"}, game.tools("place_furniture"))

    def test_open_play_under_20_defers_built_chair_borrow_and_orders_dedicated_chair(self):
        resp = bare(206, 10, fishing=False, cit=16)
        o = resp["observation"]
        o["administrators"].update(MANAGER_id=77, manager_office=None)
        o["zones"] = [{"id": 5, "type": "DiningHall", "furniture": {"table": 12, "chair": 12}}]
        o["furniture"] = [
            {"id": i, "kind": "table", "built": True, "zone_ids": [5], "x": 90 + i, "y": 95, "z": 103}
            for i in range(1, 13)
        ] + [
            {"id": 20 + i, "kind": "chair", "built": True, "zone_ids": [5], "x": 90 + i, "y": 96, "z": 103}
            for i in range(1, 13)
        ]
        o["stocks"].update(logs_usable=10, beds=20, tables=12, chairs=12, furniture_free={"chair": 0})
        o["map"]["sites"] = [{"id": "A8", "kind": "A", "x": 88, "y": 94, "z": 103, "w": 16, "h": 6, "open_tiles": 20}]
        game = StubGame()
        ov = Overseer(game, days=216)
        ov.load(resp)
        ov.count = 0
        ov.office()
        self.assertEqual([c for c in game.tools("make_zone") if c.get("site") == "A8" and c.get("kind") == "office"],
                         [{"kind": "office", "site": "A8"}])
        ov.supply()
        chair_orders = [c for c in game.tools("add_order") if c.get("recipe") == "make_chair"]
        self.assertTrue(chair_orders)

    def test_post_feast_endgame_brew_order_added_only_in_feast_window(self):
        resp = bare(10, 326, fishing=False, cit=18)
        game = StubGame()
        ov = Overseer(game, days=336)
        ov.load(resp)
        ov.count = 0
        ov.endgame_supply()
        brew_orders = [c for c in game.tools("add_order") if c.get("recipe") == "brew_drink"]
        self.assertEqual(len(brew_orders), 2)
        self.assertTrue(any(any(w.get("stock") == "food_edible" for w in c.get("when", [])) for c in brew_orders))

    def test_thaw_alert_stands_down_active_squad_orders(self):
        resp = bare(1, 335, fishing=False, cit=18)
        o = resp["observation"]
        o["threats"] = {"visible_hostiles": 1, "hostiles": [{"id": 9, "invader": False}]}
        o["military"] = {"squads": [{"id": 1, "uniform": "leather", "armed": 2, "orders": ["attack"]}]}
        o["burrows"] = {"civilian_alert": True, "list": [{"id": 1, "civ_alert_burrow": True}]}
        game = StubGame()
        ov = Overseer(game, days=336)
        ov.thaw_alert = True
        ov.load(resp)
        ov.count = 0
        ov.defend()
        self.assertIn({"order": "stand_down"}, game.tools("squad_order"))

    def test_surge_bed_overflow_skips_no_space_area_and_lowers_window_plant_reserve(self):
        resp = bare(18, 24, fishing=False, cit=42)
        o = resp["observation"]
        o["stocks"]["furniture_free"] = {"bed": 25, "chair": 1, "table": 0}
        o["stocks"]["logs_usable"] = 12
        o["stocks"]["boulders_usable"] = 10
        o["workshops"] = [{"id": 1, "type": "Carpenters", "built": True},
                          {"id": 2, "type": "Carpenters", "built": True},
                          {"id": 3, "type": "Carpenters", "built": True},
                          {"id": 4, "type": "Still", "built": True}]
        o["map"]["sites"] = [
            {"id": "A10", "kind": "A", "x": 91, "y": 99, "z": 113, "w": 13, "h": 7, "open_tiles": 10},
            {"id": "A2", "kind": "A", "x": 90, "y": 88, "z": 115, "w": 10, "h": 16, "open_tiles": 12},
            {"id": "A5", "kind": "A", "x": 85, "y": 88, "z": 112, "w": 9, "h": 9, "open_tiles": 9},
            {"id": "W1", "kind": "W", "x": 80, "y": 80, "z": 114, "w": 3, "h": 3},
            {"id": "W2", "kind": "W", "x": 84, "y": 80, "z": 114, "w": 3, "h": 3},
        ]

        class BedOverflowGame(StubGame):
            def act(self, tool, args=None):
                args = args or {}
                self.calls.append((tool, args))
                if tool == "place_furniture" and args.get("kind") == "bed":
                    if args.get("site") in ("A10", "A2"):
                        return {"ok": False, "error_code": "no_space", "error": "full"}
                    return {"ok": True, "result": {"at": [[85, 88, 112]] * 10}}
                return {"ok": True, "result": {}}

        game = BedOverflowGame()
        ov = Overseer(game, goal="A migrant wave is coming; every dwarf must have a placed bed and drink must not end lower.", days=60)
        ov.set_task({"hands_off": {"start_day": 42, "end_day": 60},
                     "goal": "every dwarf must have a placed bed and drink must not end lower"})
        ov.load(resp)
        ov.count = 0
        ov.furnish()
        self.assertIn("A10", ov.dorm_full)
        self.assertIn("A2", ov.dorm_full)
        bed_sites = [c["site"] for c in game.tools("place_furniture") if c.get("kind") == "bed"]
        self.assertEqual(bed_sites, ["A10", "A2", "A5"])
        ov.workshops()
        self.assertIn({"type": "Still", "site": "W2"}, game.tools("build_workshop"))
        ov.window_supply()
        brew = [c for c in game.tools("add_order") if c.get("recipe") == "brew_drink"][0]
        self.assertEqual(brew["amount"], 6)
        self.assertIn({"stock": "plants_brewable", "at_least": 4}, brew["when"])


if __name__ == "__main__":
    unittest.main()
