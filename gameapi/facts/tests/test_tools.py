import unittest

import _path  # noqa: F401
from gameapi.facts import tools as T


class OrderSpec(unittest.TestCase):
    def test_recipe(self):
        spec, meta = T.order_spec({"recipe": "make_bed", "amount": 2})
        self.assertEqual(spec, {"job": "ConstructBed", "material_category": ["wood"], "amount_total": 2})
        self.assertEqual(meta, {"recipe": "make_bed", "stocks": []})

    def test_frozen_stock_names(self):
        spec, meta = T.order_spec({"recipe": "cook_meal", "amount": 1, "repeat": "daily",
                                   "when": [{"stock": "food_edible", "at_least": 20}]})
        self.assertEqual(spec["item_conditions"], [{"flags": ["unrotten", "cookable"], "condition": "AtLeast", "value": 20}])
        self.assertEqual(meta["stocks"], ["food_edible"])

    def test_manager_order(self):
        spec, meta = T.manager_order_spec({"job": "CustomReaction", "reaction": "MAKE_PEARLASH", "amount": 1,
                                           "repeat": "monthly",
                                           "when": [{"item_type": "BIN", "flags": ["empty"], "below": 3},
                                                    {"item_type": "ANY", "flags": ["unrotten", "cookable"], "at_least": 5}]})
        self.assertEqual(spec["reaction"], "MAKE_PEARLASH")
        self.assertEqual(spec["frequency"], "Monthly")
        self.assertEqual(spec["item_conditions"], [
            {"item_type": "BIN", "flags": ["empty"], "condition": "LessThan", "value": 3},
            {"flags": ["unrotten", "cookable"], "condition": "AtLeast", "value": 5}])
        self.assertEqual(meta["stocks"], [None, None])

    def rejected(self, fn, args, *words):
        with self.assertRaises(T.Rejected, msg=args) as c:
            fn(args)
        for w in words:
            self.assertIn(w, str(c.exception), args)

    def test_the_glm_call_names_what_is_missing(self):
        # the e2e failure: no recipe, a `when` item with no stock
        glm = {"amount": 5, "repeat": "daily", "when": [{"below": 70, "at_least": 0}]}
        self.rejected(T.order_spec, glm, "add_order needs recipe", "brew_drink", "add_manager_order")
        self.rejected(T.manager_order_spec, glm, "add_manager_order needs job", "add_order")
        self.rejected(T.order_spec, dict(glm, recipe="brew_drink"), "when[0] needs stock", "drink")
        self.rejected(T.manager_order_spec, dict(glm, job="MakeBarrel"), "when[0] needs item_type")

    def test_rejects(self):
        o, m = T.order_spec, T.manager_order_spec
        self.rejected(o, {"recipe": "make_bed"}, "needs amount")
        self.rejected(o, {"recipe": "make_bed", "amount": 31}, "amount")
        self.rejected(o, {"recipe": "nope", "amount": 1}, "recipe")
        self.rejected(o, {"recipe": "make_bed", "amount": 1, "when": [{"stock": "drink", "below": 1}]}, "needs repeat")
        self.rejected(o, {"recipe": "make_bed", "amount": 1, "repeat": "daily", "when": [{"stock": "drink"}]},
                      "when[0] needs below or at_least")
        self.rejected(o, {"recipe": "make_bed", "amount": 1, "repeat": "daily",
                          "when": [{"stock": "drink", "below": 1, "at_least": 2}]}, "both below and at_least")
        self.rejected(o, {"recipe": "make_bed", "amount": 1, "repeat": "daily",
                          "when": [{"stock": "drink", "item_type": "DRINK", "below": 1}]}, "unexpected fields", "add_manager_order")
        self.rejected(o, {"recipe": "make_bed", "amount": 1, "repeat": "daily", "when": [{"stock": "drink", "below": 1}] * 4}, "1-3")
        self.rejected(m, {"job": "MakeBarrel", "amount": 1, "repeat": "daily", "when": [{"item_type": "ANY", "below": 1}]},
                      "ANY needs flags")
        self.rejected(m, {"job": "MakeBarrel", "amount": 1, "repeat": "daily",
                          "when": [{"item_type": "ANY", "flags": ["a"], "item_subtype": "X", "below": 1}]}, "item_subtype")
        self.rejected(m, {"job": "MakeBarrel", "material_category": "wood", "amount": 1}, "material_category")
        self.rejected(m, {"job": "MakeBarrel", "amount": 1, "repeat": "daily", "when": [{"stock": "drink", "below": 1}]},
                      "unexpected fields")

    def test_invalid_lists_allowed(self):
        with self.assertRaises(T.Invalid) as c:
            T.order_spec({"recipe": "make_bed", "amount": 1, "repeat": "hourly"})
        self.assertEqual(c.exception.allowed, sorted(T.REPEATS))

    def test_recipe_of(self):
        self.assertEqual(T.recipe_of({"job": "ConstructBed", "material_category": ["wood"]}), "make_bed")
        self.assertEqual(T.recipe_of({"job": "CustomReaction", "reaction": "BREW_DRINK_FROM_PLANT"}), "brew_drink")
        self.assertIsNone(T.recipe_of({"job": "ConstructBlocks", "material_category": ["wood"]}))


class Schemas(unittest.TestCase):
    def test_frozen_tools_keep_names_and_arguments(self):
        frozen = {"appoint_manager": {"dwarf_id"}, "build_workshop": {"type", "site"}, "build_farm": {"site"},
                  "add_order": {"recipe", "amount", "repeat", "when"}, "cancel_order": {"order_id"},
                  "enable_automation": {"name"}, "create_squad": {"dwarf_ids", "size"}, "equip_squad": {"uniform"},
                  "squad_order": {"order", "target_ids", "x", "y", "z"}, "create_burrow": {"site", "levels"},
                  "civilian_alert": {"on"}, "build_door": {"site", "kind"}, "build_wall": {"site"},
                  "lock_door": {"locked", "door_id"}, "dig_room": {"site", "w", "h"}, "dig_stairs": {"site", "z_bottom"},
                  "place_furniture": {"kind", "site", "count"}, "make_zone": {"kind", "site"},
                  "assign_zone": {"zone_id", "dwarf_id"}, "advance_days": {"days"}}
        by = {t["function"]["name"]: t["function"] for t in T.tool_schemas()}
        self.assertEqual(set(by) - set(frozen), {"slaughter", "add_manager_order"})
        for name, args in frozen.items():
            self.assertTrue(args <= set(by[name]["parameters"]["properties"]), name)

    def test_order_tools_require_their_key(self):
        by = {t["function"]["name"]: t["function"]["parameters"] for t in T.tool_schemas()}
        self.assertEqual(by["add_order"]["required"], ["recipe", "amount"])
        self.assertEqual(by["add_order"]["properties"]["when"]["items"]["required"], ["stock"])
        self.assertEqual(set(by["add_order"]["properties"]), {"recipe", "amount", "repeat", "when"})
        self.assertEqual(by["add_manager_order"]["required"], ["job", "amount"])
        self.assertEqual(by["add_manager_order"]["properties"]["when"]["items"]["required"], ["item_type"])
        d = {t["function"]["name"]: t["function"]["description"] for t in T.tool_schemas()}
        self.assertIn("add_manager_order", d["add_order"])
        self.assertIn("add_order", d["add_manager_order"])

    def test_workshop_enum_from_df(self):
        t = next(t for t in T.tool_schemas(["Loom", "Jewelers"]) if t["function"]["name"] == "build_workshop")
        self.assertEqual(t["function"]["parameters"]["properties"]["type"]["enum"], ["Jewelers", "Loom"])

    def test_no_advice_words_in_descriptions(self):
        for t in T.tool_schemas():
            d = t["function"]["description"].lower()
            for w in ("first", "should", "can't be used", "usually", "remember"):
                self.assertNotIn(w, d, t["function"]["name"])


if __name__ == "__main__":
    unittest.main()
