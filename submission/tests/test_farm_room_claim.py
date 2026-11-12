"""cx: a farm-role R room still waiting for its plot is not zoned over (hint hard LT01-0 on 82d1ec1: the model's beds
landed on R1's floor inside A2, the layer's rezone made A2 a dormitory, R1 read used_by Dormitory 18 and no plot was
ever built — the fort's only soil room; drink 0 from day 0). No game or network is used."""
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
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {"zone_id": len(self.calls)}}


# the measured shapes (cx82d1ec1 hint hard LT01-0, day 8): corner-anchored boxes on z136
R1 = {"id": "R1", "kind": "R", "x": 100, "y": 90, "z": 136, "w": 3, "h": 3, "soil": True,
      "subterranean": True, "designated": True, "dug": False, "free": True}
A1 = {"id": "A1", "kind": "A", "x": 103, "y": 90, "z": 136, "w": 7, "h": 3, "open_tiles": 21}
A2 = {"id": "A2", "kind": "A", "x": 100, "y": 90, "z": 136, "w": 10, "h": 3, "open_tiles": 27}
BED_ON_R1 = {"kind": "bed", "x": 100, "y": 90, "z": 136, "built": True, "zone_ids": []}
TABLE = {"kind": "table", "x": 101, "y": 91, "z": 136, "built": True, "zone_ids": []}
CHAIR = {"kind": "chair", "x": 101, "y": 92, "z": 136, "built": True, "zone_ids": []}


def facts(sites, furniture=(), plots=(), zones=(), day=8):
    return {"day": day, "tick": day * harness.DAY, "observation": {
        "administrators": {"citizens": 18}, "map": {"sites": copy.deepcopy(list(sites)), "surface_z": 137},
        "zones": copy.deepcopy(list(zones)), "furniture": copy.deepcopy(list(furniture)),
        "farm_plots": copy.deepcopy(list(plots)), "stocks": {"furniture_free": {}}}}


class FarmRoomClaim(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)
        self.game = FakeGame()
        self.ov = harness.Overseer(self.game, days=60)
        self.ov.count = 0
        self.ov.roles["R1"] = "farm"

    def zones_made(self):
        return [a for t, a in self.game.calls if t == "make_zone"]

    def test_rezone_skips_the_box_over_a_pending_farm_room(self):
        # A2 is listed first (the measured order put A2 before A1 on the level): the old rezone took it
        self.ov.load(facts([R1, A2, A1], [BED_ON_R1]))
        self.assertTrue(self.ov.farm_claimed(A2))
        self.assertFalse(self.ov.farm_claimed(A1))
        self.ov.rezone()
        self.assertEqual(self.zones_made(), [{"kind": "dormitory", "site": "A1"}])

    def test_rezone_dining_also_skips_it(self):
        self.ov.load(facts([R1, A2, A1], [TABLE, CHAIR]))
        self.ov.rezone()
        self.assertNotIn("A2", [a["site"] for a in self.zones_made()])
        self.assertIn({"kind": "dining_hall", "site": "A1"}, self.zones_made())

    def test_no_other_box_means_no_zone_rather_than_the_farm_room(self):
        self.ov.load(facts([R1, A2], [BED_ON_R1]))
        self.ov.rezone()
        self.assertEqual(self.zones_made(), [])

    def test_a_built_plot_releases_the_room(self):
        plot = {"id": 10, "x": 100, "y": 90, "z": 136, "w": 3, "h": 3, "built": True}
        self.ov.load(facts([R1, A2, A1], [BED_ON_R1], plots=[plot]))
        self.assertFalse(self.ov.farm_claimed(A2))
        self.ov.rezone()
        self.assertEqual(self.zones_made(), [{"kind": "dormitory", "site": "A2"}])

    def test_rooms_of_other_roles_claim_nothing(self):
        self.ov.roles["R1"] = "dorm"
        self.ov.load(facts([R1, A2, A1], [BED_ON_R1]))
        self.assertFalse(self.ov.farm_claimed(A2))

    def test_stress_site_avoids_the_pending_farm_room(self):
        self.ov.load(facts([R1, A2, A1]))
        site = self.ov.stress_site()
        self.assertIsNotNone(site)
        self.assertEqual(site["id"], "A1")

    def test_room_for_dorm_avoids_the_box_over_a_farm_room(self):
        dorm = {"id": "R2", "kind": "R", "x": 110, "y": 90, "z": 136, "w": 3, "h": 3, "dug": True, "free": True}
        self.ov.roles["R2"] = "dorm"
        self.ov.load(facts([R1, dorm, A2, A1]))
        self.assertEqual(self.ov.room_for("dorm", harness.ZONE_MAX)["id"], "A1")


if __name__ == "__main__":
    unittest.main()
