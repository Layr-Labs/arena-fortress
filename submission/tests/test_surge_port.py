"""Behavior checks for the LT08 transfer. FORTRESS_PORT_HARNESS selects control for red checks."""
import contextlib
import copy
import io
import os
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
PACKAGE = Path(os.environ.get("FORTRESS_PORT_HARNESS", str(Path(__file__).resolve().parents[1])))
sys.path.insert(0, str(PACKAGE))
from overseer.harness import Overseer

GOAL = "A migrant wave is due; every dwarf must have a placed bed; drink must not end lower."


class Game:
    def __init__(self, replies=None):
        self.calls = []
        self.replies = copy.deepcopy(replies or {})
        self.next_id = 100

    def act(self, tool, args):
        self.calls.append((tool, copy.deepcopy(args)))
        replies = self.replies.get(tool, [])
        if replies:
            return replies.pop(0)
        self.next_id += 1
        if tool == "place_furniture":
            return {"ok": True, "result": {"at": [[i, 10, 67] for i in range(args.get("count", 1))]}}
        return {"ok": True, "result": {"order_id": self.next_id, "id": self.next_id}}

    def query(self, *args, **kwargs):
        return {"ok": True, "result": {"units": []}}


def area(name, z=67, width=8, height=5, opened=40):
    return {"id": name, "kind": "A", "x": 10, "y": 10, "z": z,
            "w": width, "h": height, "open_tiles": opened}


class SurgePort(unittest.TestCase):
    def make(self, surge=True, day=0, cit=19, beds=6, sites=None, replies=None):
        game = Game(replies)
        goal = GOAL if surge else "Run the fortress for 336 days."
        c = Overseer(game, goal=goal, days=60 if surge else 336)
        c.set_task({"goal": goal, "hands_off": {"from_day": 39} if surge else None})
        c.load({"day": day, "tick": day * 1200, "days_left": (60 if surge else 336) - day,
                "hands_off_in_days": 39 - day if surge else None,
                "observation": {
                    "date": {"abs_tick": day * 1200},
                    "administrators": {"citizens": cit, "manager_active_for_orders": True,
                                       "MANAGER_id": 7, "manager_office": {"chair": True}},
                    "stocks": {"beds": beds, "chairs": 0, "tables": 0, "logs_usable": 40,
                               "boulders_usable": 0, "seeds_by_kind": {},
                               "furniture_free": {"bed": beds, "chair": 2, "table": 0}},
                    "map": {"surface_z": 70, "sites": sites or [area("A1"), area("A2", z=66)]},
                    "orders": [], "zones": [], "furniture": [], "dwarves": [],
                    "farm_plots": [],
                    "workshops": [{"type": "Carpenters", "built": True},
                                  {"type": "Still", "built": True}, {"type": "Kitchen", "built": True}],
                }})
        c.count = 0
        return c, game

    def invoke(self, c, method):
        with contextlib.redirect_stdout(io.StringIO()):
            getattr(c, method)()

    def orders(self, game, recipe):
        return [args for tool, args in game.calls if tool == "add_order" and args.get("recipe") == recipe]

    def placements(self, game):
        return [args for tool, args in game.calls if tool == "place_furniture" and args.get("kind") == "bed"]

    def test_day_zero_orders_a_legal_large_batch(self):
        c, g = self.make()
        self.invoke(c, "supply")
        self.assertEqual(self.orders(g, "make_bed")[0]["amount"], 30)

    def test_large_population_stays_inside_api_amount_limit(self):
        c, g = self.make(cit=100, beds=0)
        self.invoke(c, "supply")
        self.assertEqual(self.orders(g, "make_bed")[0]["amount"], 30)
        self.assertIsInstance(self.orders(g, "make_bed")[0]["amount"], int)

    def test_ordinary_task_keeps_small_batch(self):
        c, g = self.make(surge=False)
        self.invoke(c, "supply")
        self.assertEqual(self.orders(g, "make_bed")[0]["amount"], 8)

    def test_only_one_office_chair_bypasses_bed_queue(self):
        c, g = self.make(cit=30)
        c.adm["manager_office"] = {"chair": False}
        c.free["chair"] = 0
        c.st["chairs"] = 25
        self.invoke(c, "supply")
        self.assertEqual([r["amount"] for r in self.orders(g, "make_chair")], [1])
        self.assertEqual(self.orders(g, "make_table"), [])

    def test_planned_office_chair_does_not_queue_another(self):
        c, g = self.make(cit=30)
        c.adm["manager_office"] = {"chair": False}
        c.free["chair"] = 0
        c.zones = [{"type": "Office", "owner": 7, "furniture_planned": {"chair": 1}}]
        self.invoke(c, "supply")
        self.assertEqual(self.orders(g, "make_chair"), [])

    def test_third_carpenter_when_beds_are_short(self):
        c, g = self.make(cit=30, sites=[{"id": "W3", "kind": "W", "x": 30, "y": 30, "z": 67}])
        c.o["workshops"].append({"type": "Carpenters", "built": False})
        self.invoke(c, "workshops")
        self.assertEqual(sum(tool == "build_workshop" and a["type"] == "Carpenters" for tool, a in g.calls), 1)

    def test_planned_carpenters_count_toward_cap(self):
        c, g = self.make(cit=30, sites=[{"id": "W4", "kind": "W"}])
        c.o["workshops"] += [{"type": "Carpenters", "built": False}] * 2
        self.invoke(c, "workshops")
        self.assertFalse(any(tool == "build_workshop" and a["type"] == "Carpenters" for tool, a in g.calls))

    def test_covered_beds_keep_two_shop_target(self):
        c, g = self.make(cit=30, sites=[{"id": "W3", "kind": "W"}])
        c.o["workshops"].append({"type": "Carpenters", "built": True})
        c.placed["bed"] = 30
        self.invoke(c, "workshops")
        self.assertFalse(any(tool == "build_workshop" and a["type"] == "Carpenters" for tool, a in g.calls))

    def test_deep_dorm_box_is_not_farmed(self):
        sites = [{"id": "R3", "kind": "R", "x": 10, "y": 10, "z": 67, "soil": True},
                 {"id": "Finside", "kind": "F", "x": 10, "y": 10, "z": 67, "w": 3, "h": 3},
                 {"id": "Fedge", "kind": "F", "x": 19, "y": 10, "z": 67, "w": 3, "h": 3}]
        c, g = self.make(sites=sites)
        self.invoke(c, "digging")
        self.assertEqual(c.roles.get("R3"), "dorm")
        dig = next(a for tool, a in g.calls if tool == "dig_room")
        self.assertEqual((dig["w"], dig["h"]), (9, 7))
        self.invoke(c, "farms")
        self.assertEqual([a["site"] for tool, a in g.calls if tool == "build_farm"], ["Fedge"])

    def test_rejected_dig_does_not_claim_surge_role(self):
        c, g = self.make(sites=[{"id": "R3", "kind": "R", "x": 10, "y": 10, "z": 67, "soil": True}],
                         replies={"dig_room": [{"ok": False, "error_code": "bad_site"}]})
        self.invoke(c, "digging")
        self.assertNotIn("R3", c.roles)

    def test_depth_relaxes_only_from_day_eight(self):
        for day, expected in ((0, "farm"), (8, "dorm")):
            with self.subTest(day=day):
                c, g = self.make(day=day, sites=[{"id": "R2", "kind": "R", "x": 10, "y": 10, "z": 68, "soil": True}])
                self.invoke(c, "digging")
                self.assertEqual(c.roles.get("R2"), expected)

    def test_partial_success_places_only_remaining_beds(self):
        c, g = self.make(cit=30, replies={"place_furniture": [
            {"ok": True, "result": {"at": [[10, 10, 67], [11, 10, 67]]}}]})
        self.invoke(c, "furnish")
        self.assertEqual([(a["site"], a["count"]) for a in self.placements(g)], [("A1", 6), ("A2", 4)])
        self.invoke(c, "furnish")
        self.assertEqual(len(self.placements(g)), 2)

    def test_shallow_stone_fallback_cannot_bypass_dorm_depth(self):
        c, g = self.make(sites=[
            {"id": "R2", "kind": "R", "x": 10, "y": 10, "z": 68, "soil": False},
            {"id": "R3", "kind": "R", "x": 10, "y": 10, "z": 67, "soil": True}])
        self.invoke(c, "digging")
        self.assertNotEqual(c.roles.get("R2"), "dorm")
        self.assertEqual(c.roles.get("R3"), "dorm")

    def test_no_space_skips_overlapping_level_and_oversize(self):
        c, g = self.make(sites=[area("A1"), area("same", opened=90), area("huge", z=66, width=21, opened=100),
                                area("legal", z=65, width=6, height=6, opened=36)],
                         replies={"place_furniture": [{"ok": False, "error_code": "no_space"}]})
        self.invoke(c, "furnish")
        self.assertEqual([a["site"] for a in self.placements(g)], ["A1", "legal"])

    def test_shallow_layout_requests_bounded_depth_access(self):
        for day in (0, 8):
            with self.subTest(day=day):
                sites = [{"id": "S1", "kind": "S", "z": 70},
                         {"id": "R1", "kind": "R", "x": 10, "y": 10, "z": 69, "soil": True},
                         {"id": "R2", "kind": "R", "x": 20, "y": 10, "z": 69, "soil": True}]
                c, g = self.make(day=day, sites=sites)
                c.o["farm_plots"] = [{"id": i} for i in range(4)]
                self.invoke(c, "digging")
                self.invoke(c, "digging")
                self.assertEqual([a for tool, a in g.calls if tool == "dig_stairs"],
                                 [{"site": "S1", "z_bottom": 66}])
                self.assertNotIn("dorm", c.roles.values())

    def test_existing_deep_room_avoids_extra_stairs(self):
        c, g = self.make(sites=[
            {"id": "S1", "kind": "S", "z": 70},
            {"id": "R1", "kind": "R", "x": 10, "y": 10, "z": 69, "soil": True},
            {"id": "R3", "kind": "R", "x": 20, "y": 10, "z": 67, "soil": True}])
        c.o["farm_plots"] = [{"id": i} for i in range(4)]
        self.invoke(c, "digging")
        self.assertFalse(any(tool == "dig_stairs" for tool, _ in g.calls))
        self.assertEqual(c.roles.get("R3"), "dorm")

    def test_other_error_and_unknown_receipt_do_not_overflow(self):
        for response in ({"ok": False, "error_code": "bad_site"}, {"ok": True, "result": {}}):
            with self.subTest(response=response):
                c, g = self.make(replies={"place_furniture": [response]})
                self.invoke(c, "furnish")
                self.assertEqual([a["site"] for a in self.placements(g)], ["A1"])

    def test_complete_success_does_not_overflow(self):
        c, g = self.make()
        self.invoke(c, "furnish")
        self.assertEqual([a["site"] for a in self.placements(g)], ["A1"])


if __name__ == "__main__":
    unittest.main()
