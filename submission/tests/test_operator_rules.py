"""Operator's standing dwarf rules: manager office asap, tavern on the first level down, never a bartender."""
from pathlib import Path
import io, sys, unittest
from contextlib import redirect_stdout

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overseer import harness


class Rec:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {}}


def make(obs):
    o = harness.Overseer(Rec())
    o.count = 0
    o.load({"observation": obs, "day": 5, "tick": 6000})
    return o


def room(i, z, soil=False):
    return {"id": f"R{i}", "kind": "R", "x": 10 * i, "y": 10, "z": z, "w": 3, "h": 3, "soil": soil}


class OperatorRules(unittest.TestCase):
    def test_office_before_14_citizens(self):
        o = make({"administrators": {"citizens": 7, "manager_active_for_orders": True, "MANAGER_id": 3},
                  "map": {"sites": [{"id": "A1", "kind": "A", "x": 1, "y": 1, "z": 99, "w": 5, "h": 5}]},
                  "stocks": {"furniture_free": {"chair": 2}}})
        with redirect_stdout(io.StringIO()):
            o.office()
        self.assertIn("make_zone", [t for t, _ in o.game.calls])

    def test_office_dug_first_and_tavern_first_level_down(self):
        sites = [room(1, 99), room(2, 98), room(3, 98), room(4, 99)]
        o = make({"administrators": {"citizens": 7}, "map": {"surface_z": 100, "sites": sites}})
        with redirect_stdout(io.StringIO()):
            o.digging()
        self.assertEqual(o.roles["R1"], "office")
        dine = [r for r, v in o.roles.items() if v == "dine"]
        self.assertEqual(dine, ["R4"], o.roles)   # z 99 = surface - 1, not a z 98 room

    def test_manager_then_office_then_autolabor(self):
        o = make({"administrators": {"citizens": 7}, "dwarves": [{"id": 3, "organizer_skill": 2}]})
        with redirect_stdout(io.StringIO()):
            o.management()
        self.assertNotIn(("enable_automation", {"name": "autolabor"}), o.game.calls)   # no manager yet
        o = make({"administrators": {"citizens": 7, "manager_active_for_orders": True, "MANAGER_id": 3},
                  "map": {"sites": [{"id": "A1", "kind": "A", "x": 1, "y": 1, "z": 99, "w": 5, "h": 5}]},
                  "stocks": {"furniture_free": {"chair": 2}}})
        with redirect_stdout(io.StringIO()):
            o.management()
        tools = [(t, a.get("name") or a.get("kind")) for t, a in o.game.calls]
        self.assertLess(tools.index(("make_zone", "office")), tools.index(("enable_automation", "autolabor")))

    def test_stone_orders_use_inorganic_once(self):
        o = make({"administrators": {"citizens": 9}, "stocks": {"boulders_usable": 20},
                  "workshops": [{"type": "Masons"}, {"type": "Craftsdwarfs"}]})
        with redirect_stdout(io.StringIO()):
            o.stonework(); o.now += 10 * harness.DAY; o.stonework()
        orders = [a for t, a in o.game.calls if t == "add_manager_order"]
        self.assertEqual(sorted(a["job"] for a in orders), ["ConstructStatue", "MakeCrafts"])
        self.assertTrue(all(a.get("material") == "INORGANIC" and "material_category" not in a for a in orders))

    def test_full_dorm_skipped_and_second_dorm_dug(self):
        sites = [dict(room(1, 99), dug=True), room(2, 98)]
        o = make({"administrators": {"citizens": 10}, "map": {"surface_z": 100, "sites": sites}})
        o.roles = {"R1": "dorm", "Rx": "office", "Ry": "dine"}
        o.placed = {"bed": 4}
        self.assertEqual(o.room_for("dorm")["id"], "R1")
        o.full["R1"] = o.now
        self.assertIsNone(o.room_for("dorm"))
        with redirect_stdout(io.StringIO()):
            o.digging()
        self.assertEqual(o.roles.get("R2"), "dorm", o.roles)

    def test_housing_short_caps_advances(self):
        o = make({"administrators": {"citizens": 10}})
        o.placed = {"bed": 4}
        self.assertTrue(o.housing_short())
        o.placed = {"bed": 10}
        self.assertFalse(o.housing_short())

    def test_office_reuses_built_chair_room(self):
        site = dict(room(1, 99), dug=True, free=True)
        obs = {"administrators": {"citizens": 30, "manager_active_for_orders": True, "MANAGER_id": 3,
                                   "manager_office": {"zone_id": 8, "chair": False}},
               "zones": [{"id": 8, "type": "Office", "owner": 3,
                          "x": 20, "y": 10, "z": 99, "w": 7, "h": 3}],
               "map": {"sites": [site]},
               "furniture": [{"kind": "chair", "built": True, "x": 10, "y": 10, "z": 99, "zone_ids": []}]}
        o = make(obs)
        with redirect_stdout(io.StringIO()): o.office()
        self.assertEqual(o.game.calls, [("make_zone", {"kind": "office", "site": "R1"})])
        # Missing evidence, construction plans and already-zoned chairs are not reuse candidates.
        for update in ({"built": False}, {"zone_ids": [7]}):
            changed = dict(obs, furniture=[dict(obs["furniture"][0], **update)])
            o = make(changed)
            with redirect_stdout(io.StringIO()): o.office()
            self.assertEqual(o.game.calls, [])
        for field in ("furniture", "farms"):
            o = make(dict(obs, **{field: None}))
            with redirect_stdout(io.StringIO()): o.office()

    def test_office_summary_can_hide_ready_second_office(self):
        obs = {"administrators": {"manager_active_for_orders": True, "MANAGER_id": 3,
                                   "manager_office": {"zone_id": 8, "chair": False}},
               "zones": [{"id": 8, "type": "Office", "owner": 3},
                         {"id": 18, "type": "Office", "owner": 3, "furniture": {"chair": 9}}]}
        o = make(obs)
        with redirect_stdout(io.StringIO()): o.office()
        self.assertEqual(o.game.calls, [])
        obs["zones"][1]["owner"] = None
        o = make(obs)
        with redirect_stdout(io.StringIO()): o.office()
        self.assertEqual(o.game.calls, [("assign_zone", {"zone_id": 18, "dwarf_id": 3})])
        obs["zones"][1]["owner"] = 4
        o = make(obs)
        with redirect_stdout(io.StringIO()): o.office()
        self.assertEqual(o.game.calls, [])

    def test_office_reuse_respects_zone_and_farm_conflicts(self):
        site = dict(room(1, 99), dug=True, free=True)
        for field in ("zones", "farms"):
            obs = {"administrators": {"manager_active_for_orders": True, "MANAGER_id": 3},
                   "map": {"sites": [site]}, "furniture": [dict(kind="chair", built=True, x=10, y=10, z=99)],
                   field: [dict(id=7, type="DiningHall", x=10, y=10, z=99, w=3, h=3)]}
            o = make(obs)
            with redirect_stdout(io.StringIO()):
                self.assertFalse(o.office_reuse(3, []))
            self.assertEqual(o.game.calls, [])

    def test_never_appoints_tavern_keeper(self):
        src = Path(harness.__file__).read_text().lower()
        for word in ("tavern_keeper", "tavernkeeper", "bartender", "assign_location", "make_location"):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
