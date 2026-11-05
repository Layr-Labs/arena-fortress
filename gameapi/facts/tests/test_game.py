import json
import os
import re
import unittest

import _path  # noqa: F401
from fake_df import FakeDF, obs
from gameapi.facts import Game
from gameapi.facts.game import ADVICE_KEYS

LUA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lua")
WS = {"ok": True, "workshop_types": [{"type": t} for t in ("Carpenters", "Loom", "Jewelers", "SOAP_MAKER")]}


def game(**kw):
    kw.setdefault("observe", obs())
    kw.setdefault("query", {"workshop_types": WS})
    df = FakeDF(**kw)
    return Game(df=df), df


class Observe(unittest.TestCase):
    def test_schema_sites_plugins(self):
        g, df = game()
        o = g.observe()
        self.assertEqual(o["schema"], 8)
        self.assertNotIn("site_candidates", o)
        self.assertNotIn("sites", o)
        self.assertEqual([s["id"] for s in o["map"]["sites"]], ["W1", "E1", "S1", "R1"])
        for s in o["map"]["sites"]:
            self.assertTrue({"id", "kind", "x", "y", "z", "w", "h", "soil", "free", "dug"} <= set(s), s)
        self.assertEqual(o["plugins"]["autochop"], "off")
        self.assertEqual(o["plugins"]["autofarm"], "on")
        self.assertEqual(o["dig_pending_by_z"], {})

    def test_orders_annotated(self):
        g, df = game(observe=obs(orders=[{"id": 3, "job": "PrepareMeal", "when": [{"flags": ["cookable", "unrotten"], "test": "AtLeast", "value": 2}]},
                                         {"id": 4, "job": "ConstructBlocks", "material_category": ["wood"], "when": [{"item_type": "BIN", "test": "LessThan", "value": 1}]}],
                                 zones=[{"id": 1, "furniture": []}], furniture_unzoned=[]))
        g.order_meta[3] = {"recipe": "cook_meal", "stocks": ["food_edible"]}
        ob = g.observe()
        o, o2 = ob["orders"]
        self.assertEqual(o["recipe"], "cook_meal")
        self.assertEqual(o["when"][0], {"item_type": None, "flags": ["cookable", "unrotten"], "test": "AtLeast",
                                        "value": 2, "stock": "food_edible"})
        self.assertEqual(o["created_tick"], 1000)
        self.assertNotIn("recipe", o2)
        self.assertEqual(o2["when"][0]["flags"], [])
        self.assertEqual(ob["zones"][0]["furniture"], {})
        self.assertEqual(ob["furniture_unzoned"], {})

    def test_mood_primary_quantity_null(self):
        g, df = game(observe=obs(moods=[{"unit_id": 1, "mood": "Secretive", "waiting": True,
                                          "items_needed": [{"demand": "rock", "collected": 0}, {"demand": "cloth", "quantity": 2, "collected": 1}]}]))
        need = g.observe()["moods"][0]["items_needed"]
        self.assertEqual([x["quantity"] for x in need], [None, 2])

    def test_new_game_resets_state(self):
        ticks = iter([5000, 100])
        g, df = game(observe=lambda rest: obs(tick=next(ticks)))
        g.observe()
        g.order_meta[1] = {}
        g.observe()
        self.assertEqual(g.order_meta, {})

    def test_boxes_passed_for_remembered_rooms(self):
        seen = []
        def o(rest):
            seen.append(json.loads(rest[1]))
            return obs(candidates={} if seen[1:] else None)
        g, df = game(observe=o)
        g.observe(); g.observe()
        self.assertEqual(seen[1], [{"id": "R1", "x": 30, "y": 30, "z": 4, "w": 3, "h": 3}])


class Act(unittest.TestCase):
    def test_success_shape_and_advice_stripped(self):
        g, df = game(act={"build_workshop": {"ok": True, "id": 9, "note": "planned", "hint": "x"}})
        r = g.act("build_workshop", {"type": "Loom", "site": "W1"})
        self.assertEqual(r, {"ok": True, "result": {"id": 9}})
        call = [c for c in df.calls if c[:2] == ["lua", "-f"] and c[2].endswith("act.lua")][0]
        self.assertEqual(call[3:], ["build_workshop", "Loom", "10", "10", "5"])

    def test_error_shape(self):
        g, df = game(act={"build_workshop": {"ok": False, "error_code": "tile_occupied", "error": "t", "hint": "h",
                                             "nearest_free_centre": {"x": 1}}})
        r = g.act("build_workshop", {"type": "Loom", "site": "W1"})
        self.assertEqual(r, {"ok": False, "error_code": "tile_occupied", "error": "t"})

    def test_error_code_classified_when_missing(self):
        g, df = game(act={"cancel_order": {"ok": False, "error": "no order with id 5"}})
        self.assertEqual(g.act("cancel_order", {"order_id": 5})["error_code"], "no_such_order")

    def test_workshop_enum_from_df(self):
        g, df = game()
        r = g.act("build_workshop", {"type": "Still", "site": "W1"})   # frozen type, not in this DF's list
        self.assertEqual(r["error_code"], "bad_arguments")
        self.assertEqual(r["allowed"], ["Carpenters", "Jewelers", "Loom", "SOAP_MAKER"])

    def test_unknown_tool_bad_args_server_tool(self):
        g, df = game()
        self.assertEqual(g.act("teleport", {})["error_code"], "unknown_tool")
        self.assertEqual(g.act("advance_days", {"days": 3})["error_code"], "server_tool")
        self.assertEqual(g.act("cancel_order", {"order_id": "x"})["error_code"], "bad_arguments")
        self.assertEqual(g.act("cancel_order", {"order_id": 1, "extra": 2})["error_code"], "bad_arguments")
        self.assertEqual(g.act("cancel_order", [])["error_code"], "bad_arguments")
        self.assertEqual(g.act("make_zone", {"kind": "pub", "site": "R1"})["error_code"], "bad_arguments")

    def test_add_order_passes_workorder_json_and_remembers(self):
        g, df = game(act={"add_order": {"ok": True, "order_id": 42, "job": "ConstructBin"}})
        g.observe()
        r = g.act("add_manager_order", {"job": "ConstructBin", "material_category": ["wood"], "amount": 2, "repeat": "daily",
                                        "when": [{"item_type": "BIN", "below": 5}, {"item_type": "DRINK", "at_least": 1}]})
        self.assertTrue(r["ok"])
        call = [c for c in df.calls if len(c) > 3 and c[3] == "add_order"][0]
        self.assertEqual(json.loads(call[4]), {"job": "ConstructBin", "material_category": ["wood"], "amount_total": 2,
                                               "frequency": "Daily", "item_conditions": [
                                                   {"item_type": "BIN", "condition": "LessThan", "value": 5},
                                                   {"item_type": "DRINK", "condition": "AtLeast", "value": 1}]})
        self.assertNotIn(" ", call[4])
        self.assertEqual(g.order_meta[42]["stocks"], [None, None])
        self.assertEqual(g.first_seen[42], 1000)
        r = g.act("add_order", {"recipe": "brew_drink", "amount": 5, "repeat": "daily", "when": [{"stock": "drink", "below": 70}]})
        self.assertTrue(r["ok"])
        self.assertEqual(g.order_meta[42]["stocks"], ["drink"])

    def test_add_order_without_recipe_names_it(self):
        g, df = game()
        r = g.act("add_order", {"amount": 5, "repeat": "daily", "when": [{"below": 70, "at_least": 0}]})
        self.assertEqual(r["error_code"], "bad_arguments")
        self.assertIn("add_order needs recipe", r["error"])
        r = g.act("add_order", {"recipe": "make_bed", "amount": 1, "job": "X"})
        self.assertIn("add_order takes no argument job", r["error"])

    def test_slaughter(self):
        g, df = game(act={"slaughter": lambda rest: {"ok": True, "unit_id": int(rest[1]), "marked": True}})
        self.assertEqual(g.act("slaughter", {"unit_id": 7}), {"ok": True, "result": {"unit_id": 7, "marked": True}})
        self.assertEqual(g.act("slaughter", {})["error_code"], "bad_arguments")

    def test_dig_stairs_structured(self):
        g, df = game(quickfort="Tiles designated for digging: 1")
        r = g.act("dig_stairs", {"site": "S1"})
        self.assertEqual(r["result"]["designated"], 2)
        self.assertEqual(df.blueprints["gameapi_dig.csv"], "#dig start(1;1)\nu\n")
        g, df = game(quickfort="nothing")
        self.assertEqual(g.act("dig_stairs", {"site": "S1"})["error_code"], "nothing_designated")

    def test_dig_room_keeps_stairs(self):
        g, df = game(quickfort="designated for digging: 8", digplan="KEEP 1,1")
        r = g.act("dig_room", {"site": "R1"})
        self.assertEqual(r["result"]["kept_stair_tiles"], 1)
        self.assertEqual(df.blueprints["gameapi_dig.csv"], "#dig start(1;1)\nd,d,d\nd,,d\nd,d,d\n")

    def test_place_furniture_short_is_a_fact(self):
        g, df = game(observe=obs(candidates={"A": [{"x": 1, "y": 1, "z": 1, "w": 3, "h": 3}]}),
                     quickfort="Buildings designated: 1", place={"ok": True, "x": 1, "y": 1, "z": 1, "available": 1,
                                                                 "tiles": [[1, 1, 1], [2, 1, 1]]})
        r = g.act("place_furniture", {"kind": "bed", "site": "A1", "count": 3})
        self.assertEqual(r["result"]["n"], 1)
        self.assertEqual(r["result"]["requested"], 3)
        self.assertEqual(r["result"]["available"], 1)
        self.assertFalse(set(r["result"]) & ADVICE_KEYS)

    def test_enable_automation(self):
        g, df = game(enable="autochop: on\n")
        self.assertEqual(g.act("enable_automation", {"name": "autochop"})["result"], {"name": "autochop", "was": "on", "now": "on"})


class Query(unittest.TestCase):
    def test_validation(self):
        g, df = game()
        self.assertEqual(g.query("nope")["error_code"], "unknown_query")
        self.assertEqual(g.query("jobs", limit=0)["error_code"], "bad_arguments")
        self.assertEqual(g.query("jobs", limit=501)["error_code"], "bad_arguments")
        self.assertEqual(g.query("map", radius=21)["error_code"], "bad_arguments")
        self.assertEqual(g.query("jobs", bogus=1)["error_code"], "bad_arguments")
        self.assertTrue(g.query("jobs", limit="5")["ok"])   # query-string ints
        call = [c for c in df.calls if len(c) > 3 and c[3] == "jobs"][-1]
        self.assertEqual(json.loads(call[4]), {"limit": 5})

    def test_manager_order_types_adds_interface_names(self):
        g, df = game()
        r = g.query("manager_order_types")
        self.assertIn("make_bed", r["recipes"])
        self.assertIn("food_edible", r["when_stocks"])


class Events(unittest.TestCase):
    def test_list(self):
        g, df = game(events={"ok": True, "events": [{"id": 1, "tick": 5, "text": "x"}], "dropped": 0, "now": 9})
        self.assertEqual(g.events(since_tick=0), [{"id": 1, "tick": 5, "text": "x"}])
        self.assertEqual(g.events_page(since_tick=-1)["error_code"], "bad_arguments")


class LuaSources(unittest.TestCase):
    """The probes: no advice fields, no interpretation, the hidden-information helpers used."""
    def read(self, name):
        with open(os.path.join(LUA, name)) as f:
            return f.read()

    def test_no_advice_fields(self):
        for name in os.listdir(LUA):
            src = "\n".join(l for l in self.read(name).splitlines() if not l.lstrip().startswith("--"))
            for key in ("hint", "note", "reminder", "warning", "nearest_free_centre"):
                self.assertIsNone(re.search(rf"\b{key}\s*=", src), f"{name}: {key}")

    def test_interpretation_removed_from_observe(self):
        src = self.read("observe.lua")
        code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("--"))
        for k in ("manager_needs_office", "workshop_needed", "MOOD_WORKSHOP", "OFFICE_FROM", "NOT_for_starting_seeds",
                  "free_3x3_sites_near_wagon", "df.job_type.StrangeMood "):
            self.assertNotIn(k, code)
        self.assertIn("job_items.elements", code)
        self.assertIn("^StrangeMood", code)

    def test_hidden_information_rules_present(self):
        common = self.read("common.lua")
        for fn in ("function C.seen", "function C.visible_unit", "function C.report_seen", "function C.revealed"):
            self.assertIn(fn, common)
        q = self.read("query.lua")
        self.assertIn("seen(it)", q)          # stocks
        self.assertIn("visible_unit(u)", q)   # animals/others
        self.assertIn("'?'", q)               # map hides unrevealed tiles
        self.assertIn("report_seen", self.read("events.lua"))
        code = self.read("observe.lua").split("try('moods'")[1].split("end)")[0]
        for k in ("available", "flags =", "isSuitable"):   # schema 7: no showmood-level mood facts
            self.assertNotIn(k, code)
        self.assertIn("e.waiting", code)


if __name__ == "__main__":
    unittest.main()
