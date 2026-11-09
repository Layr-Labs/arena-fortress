"""Migrant beds must not lose their excavated level to new fields."""
import io
import unittest
from contextlib import redirect_stdout
from overseer.harness import Overseer


class Game:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {}}


class LandUse(unittest.TestCase):
    def setUp(self):
        self.quiet = redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)
        self.game = Game()
        self.ov = Overseer(self.game, goal="Migrants are arriving.", days=60)
        self.ov.count = 0

    def load(self, rooms, plots=()):
        self.ov.load({"day": 0, "observation": {
            "administrators": {"citizens": 40},
            "map": {"sites": rooms}, "stocks": {}, "farm_plots": list(plots)}})

    def test_soil_beyond_existing_farms_can_become_dorm(self):
        self.load([{"id": "R1", "kind": "R", "z": 8, "soil": True}], [{"z": 9}])
        self.ov.digging()
        self.assertEqual(self.ov.roles["R1"], "dorm")
        self.assertEqual(self.game.calls[0], ("dig_room", {"site": "R1", "w": 9, "h": 7}))

    def test_existing_crop_level_does_not_get_new_dorm(self):
        self.load([{"id": "R1", "kind": "R", "z": 9, "soil": True}], [{"z": 9}])
        self.ov.digging()
        self.assertEqual(self.ov.roles["R1"], "farm")

    def test_farm_candidate_on_reserved_level_is_skipped(self):
        self.ov.roles["R1"] = "dorm"
        self.load([{"id": "R1", "kind": "R", "z": 8, "soil": True, "designated": True},
                   {"id": "F1", "kind": "F", "z": 8},
                   {"id": "F2", "kind": "F", "z": 9}])
        self.ov.farms()
        self.assertEqual(self.game.calls, [("build_farm", {"site": "F2"})])


    def test_migrant_carpentry_queues_two_legal_batches_before_tables(self):
        self.load([])
        self.ov.st.update({"logs_usable": 100, "beds": 19})
        self.ov.supply()
        furniture = [a for t, a in self.game.calls if t == "add_order" and a["recipe"] in ("make_bed", "make_table", "make_chair")]
        self.assertEqual(furniture, [{"recipe": "make_bed", "amount": 30},
                                     {"recipe": "make_bed", "amount": 30}])

    def test_migrant_free_floor_is_kept_for_missing_beds(self):
        self.load([{"id": "A1", "kind": "A", "z": 8, "open_tiles": 90}])
        self.ov.free = {"bed": 0, "table": 20, "chair": 20}
        self.ov.furnish()
        self.assertEqual(self.game.calls, [])


    def test_office_uses_built_seat_instead_of_full_first_area(self):
        self.load([{"id": "A1", "kind": "A", "z": 9, "x": 0, "y": 0, "w": 3, "h": 3},
                   {"id": "A2", "kind": "A", "z": 8, "x": 0, "y": 0, "w": 9, "h": 7}])
        self.ov.adm.update({"manager_active_for_orders": True, "MANAGER_id": 10})
        self.ov.o["furniture"] = [{"kind": "chair", "built": True, "x": 1, "y": 1, "z": 8}]
        self.ov.free = {"chair": 3}
        self.ov.office()
        self.assertEqual(self.game.calls, [("make_zone", {"kind": "office", "site": "A2"})])


if __name__ == "__main__":
    unittest.main()
