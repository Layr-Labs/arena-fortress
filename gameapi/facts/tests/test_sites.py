import unittest

import _path  # noqa: F401
from gameapi.facts.sites import SiteState


def cands(**kw):
    return {k: v for k, v in kw.items()}


class Sites(unittest.TestCase):
    def test_ids_stable_and_never_reused(self):
        s = SiteState()
        s.update(cands(W=[{"x": 1, "y": 1, "z": 5}, {"x": 5, "y": 1, "z": 5}]))
        self.assertEqual([e["id"] for e in s.listing()], ["W1", "W2"])
        s.update(cands(W=[{"x": 5, "y": 1, "z": 5}, {"x": 9, "y": 1, "z": 5}]))   # W1 used up, a new one appears
        self.assertEqual([e["id"] for e in s.listing()], ["W2", "W3"])
        a, e = s.resolve("build_workshop", {"type": "Loom", "site": "W1"})
        self.assertEqual(e["error_code"], "site_used")
        a, e = s.resolve("build_workshop", {"type": "Loom", "site": "w3"})
        self.assertIsNone(e)
        self.assertEqual((a["x"], a["y"], a["z"]), (9, 1, 5))
        self.assertNotIn("site", a)

    def test_errors_have_no_advice(self):
        s = SiteState()
        s.update(cands(W=[{"x": 1, "y": 1, "z": 5}]))
        for args in ({"site": "R1"}, {"site": "W9"}, {}):
            _, e = s.resolve("build_workshop", dict(type="Loom", **args))
            self.assertEqual(set(e), {"ok", "error_code", "error"})
        self.assertEqual(s.resolve("build_workshop", {"type": "Loom"})[1]["error_code"], "missing_location")
        self.assertEqual(s.resolve("build_workshop", {"type": "Loom", "site": "R1"})[1]["error_code"], "wrong_site_kind")
        self.assertEqual(s.resolve("build_workshop", {"type": "Loom", "site": "W9"})[1]["error_code"], "unknown_site")

    def test_raw_coordinates_pass_through(self):
        s = SiteState()
        a, e = s.resolve("build_workshop", {"type": "Loom", "x": 1, "y": 2, "z": 3})
        self.assertIsNone(e)
        self.assertEqual(a, {"type": "Loom", "x": 1, "y": 2, "z": 3})

    def test_room_lifecycle(self):
        s = SiteState()
        room = {"x": 30, "y": 30, "z": 4, "w": 3, "h": 3, "soil": True}
        s.update(cands(R=[room]))
        self.assertEqual(s.resolve("build_farm", {"site": "R1"})[1]["error_code"], "room_not_dug_yet")
        a, e = s.resolve("dig_room", {"site": "R1"})
        self.assertEqual((a["x"], a["w"], a["h"]), (30, 3, 3))
        s.update(cands(), box_facts={"R1": {"tiles": 9, "floor": 9, "designated": 0}})   # dug: no longer a candidate
        e = s.listing()[0]
        self.assertEqual((e["id"], e["dug"], e["free"], e["tiles"]["floor"]), ("R1", True, True, 9))
        self.assertIsNone(s.resolve("build_farm", {"site": "R1"})[1])
        self.assertEqual(s.resolve("dig_room", {"site": "R1"})[1]["error_code"], "site_used")
        s.update(cands(), farm_plots=[{"id": 4, "x": 31, "y": 31, "z": 4, "w": 1, "h": 1}])
        e = s.listing()[0]
        self.assertEqual((e["free"], e["used_by"]), (False, ["farm plot 4"]))
        self.assertEqual(s.resolve("build_farm", {"site": "R1"})[1]["error_code"], "site_used")
        self.assertIsNone(s.resolve("create_burrow", {"site": "R1"})[1])   # a farmed room can still be a shelter

    def test_zone_blocks_make_zone_only(self):
        s = SiteState()
        s.update(cands(R=[{"x": 30, "y": 30, "z": 4, "w": 3, "h": 3}]))
        s.update(cands(), zones=[{"id": 7, "type": "Bedroom", "x": 30, "y": 30, "z": 4, "w": 3, "h": 3}])
        self.assertEqual(s.resolve("make_zone", {"kind": "office", "site": "R1"})[1]["error_code"], "site_used")
        self.assertIsNone(s.resolve("place_furniture", {"kind": "bed", "site": "R1"})[1])

    def test_dig_stairs_args(self):
        s = SiteState()
        s.update(cands(S=[{"x": 20, "y": 21, "z": 5}]))
        a, _ = s.resolve("dig_stairs", {"site": "S1"})
        self.assertEqual((a["x"], a["y"], a["z_top"], a["z_bottom"]), (20, 21, 5, 4))

    def test_listing_has_no_rank_and_letter_kind(self):
        s = SiteState()
        s.update(cands(D=[{"x": 1, "y": 1, "z": 1, "kind": "doorway"}], W=[{"x": 2, "y": 2, "z": 2}]))
        self.assertEqual([(e["id"], e["kind"]) for e in s.listing()], [("W1", "W"), ("D1", "D")])


if __name__ == "__main__":
    unittest.main()
