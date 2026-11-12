"""cx butcher frame (hint hard OP1-2 on bb1feb6, 2026-11-12). ws_Butchers went on W6 (95,87,163), a plateau across the
water north of the fort, on day 7; its ConstructBuilding stood with no worker for 90 days and every rebuild on that
plateau vanished within 30-50 ticks. The unbuilt frame counted as a Butchers, so the 13 slaughter marks (the yak bull
that killed citizen 204 on day 288 among them, marked on day 18) never had a shop. An idle or vanished frame is now no
shop, its place is never used for a Butchers again, and the slaughter callers build on the next W site. No game."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_danger_marks import Quiet  # noqa: E402
from test_grazer_shaft import AnimalGame, beast, fort119  # noqa: E402
from overseer import harness  # noqa: E402

W6 = {"id": "W6", "kind": "W", "x": 96, "y": 88, "z": 168, "w": 3, "h": 3}
W7 = {"id": "W7", "kind": "W", "x": 104, "y": 96, "z": 168, "w": 3, "h": 3}
FRAME = {"id": 7, "type": "Butchers", "built": False, "x": 96, "y": 88, "z": 168,
         "job_details": [{"job": "ConstructBuilding"}], "jobs": ["ConstructBuilding"]}


def look(day, shops, sites=(W6, W7), alert=False, logs=12):
    r = fort119(day)
    o = r["observation"]
    o["workshops"] = [dict(w) for w in shops]
    o["map"] = dict(o.get("map") or {}, sites=[dict(s) for s in sites])
    o.setdefault("stocks", {})["logs_usable"] = logs
    o["burrows"] = dict(o.get("burrows") or {}, civilian_alert=alert)
    return r


class Frame(Quiet):
    def setUp(self):
        super().setUp()
        self.game = AnimalGame([beast(108, "YAK")])
        self.ov = harness.Overseer(self.game, days=336)

    def feed(self, days, shops, **kw):
        for day in days:
            self.ov.load(look(day, shops, **kw))

    def test_a_fresh_frame_still_counts(self):
        self.feed([7, 8], [FRAME])
        self.assertTrue(self.ov.butchers_ready())

    def test_an_idle_frame_is_no_shop_and_its_site_is_dead(self):
        self.feed([7, 8, 9], [FRAME])
        self.assertFalse(self.ov.butchers_ready())
        self.assertTrue(self.ov.dead_site(W6))
        self.assertFalse(self.ov.dead_site(W7))

    def test_alert_days_and_no_material_do_not_count(self):
        self.feed([7, 8], [FRAME], alert=True)
        self.feed([9, 10], [FRAME], logs=0)
        self.feed([11], [FRAME])
        self.assertTrue(self.ov.butchers_ready())

    def test_a_builder_on_it_clears_the_count(self):
        self.feed([7, 8], [FRAME])
        worked = dict(FRAME, job_details=[{"job": "ConstructBuilding", "worker_id": 92}])
        self.feed([9], [worked])
        self.feed([10, 11], [FRAME])
        self.assertTrue(self.ov.butchers_ready())

    def test_a_frame_that_vanished_unbuilt_kills_its_site(self):
        self.feed([7], [FRAME])
        self.feed([8], [])
        self.assertTrue(self.ov.dead_site(W6))
        self.assertFalse(self.ov.butchers_ready())

    def test_a_built_shop_is_ready_and_never_dead(self):
        built = dict(FRAME, built=True, job_details=[], jobs=[])
        self.feed([7, 8, 9, 10], [built])
        self.assertTrue(self.ov.butchers_ready())
        self.assertFalse(self.ov.dead_site(W6))

    def test_the_rebuild_goes_to_the_next_site_under_a_fresh_key(self):
        self.feed([7, 8, 9], [FRAME])
        self.game.calls.clear()
        self.ov.count = 0
        self.ov.grazer_cull()
        builds = [a for t, a in self.game.calls if t == "build_workshop"]
        self.assertEqual(builds, [{"site": "W7", "type": "Butchers"}])
        self.assertIn(108, [a["unit_id"] for t, a in self.game.calls if t == "slaughter"])

    def test_after_the_frame_vanishes_the_dead_site_is_skipped(self):
        self.feed([7, 8, 9], [FRAME])
        self.feed([10], [], sites=(W6, W7))   # the frame is gone and W6 is listed free again
        self.game.calls.clear()
        self.ov.count = 0
        self.ov.butcher(for_food=False)
        builds = [a for t, a in self.game.calls if t == "build_workshop"]
        self.assertEqual(builds, [{"site": "W7", "type": "Butchers"}])

    def test_only_dead_sites_left_builds_nothing(self):
        self.feed([7, 8, 9], [FRAME])
        self.feed([10], [], sites=(W6,))
        self.game.calls.clear()
        self.ov.count = 0
        self.ov.butcher(for_food=False)
        self.assertEqual([a for t, a in self.game.calls if t == "build_workshop"], [])

    def test_other_shop_types_keep_their_sites(self):
        self.feed([7, 8, 9], [FRAME])
        self.feed([10], [], sites=(W6, W7))
        self.game.calls.clear()
        self.ov.count = 0
        self.ov.build("Craftsdwarfs", key="ws_test")
        self.assertEqual([a["site"] for t, a in self.game.calls if t == "build_workshop"], ["W6"])


if __name__ == "__main__":
    unittest.main()
