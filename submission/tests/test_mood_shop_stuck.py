"""cx mood shop: a suspended frame is no shop for a strange mood, and a toppled wagon (empty W list) does not stop the
rebuild. Shapes from hint hard LT03-3 on c44c96b (Craftsdwarfs frames 6/14 suspended from day 0 to 41, wagon toppled on
day 2, then only R1 listed) and LT03-0 on f2bd283 (the Craftsdwarfs toppled with the wagon on day 1)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from overseer import harness as h   # noqa: E402

W_DAY0 = [{"id": "W1", "kind": "W", "x": 95, "y": 93, "z": 91, "w": 3, "h": 3},
          {"id": "W2", "kind": "W", "x": 101, "y": 95, "z": 91, "w": 3, "h": 3},
          {"id": "W3", "kind": "W", "x": 100, "y": 92, "z": 91, "w": 3, "h": 3},
          {"id": "W10", "kind": "W", "x": 88, "y": 88, "z": 91, "w": 3, "h": 3}]
MOOD = {"mood": "Fey", "skill": "WOODCRAFT", "unit_id": 95, "claimed_building_id": None}


class FakeGame:
    def __init__(self, ok=True):
        self.calls, self.ok = [], ok

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": self.ok, "id": 99} if self.ok else {"ok": False, "error_code": "tile_occupied"}


def overseer(workshops, sites, wagon_present, now=0, day=0):
    ov = h.Overseer.__new__(h.Overseer)
    ov.o = {"moods": [dict(MOOD)], "workshops": workshops}
    ov.map = {"wagon": {"present": wagon_present, "x": 97 if wagon_present else 97,
                        "y": 97 if wagon_present else 96, "z": 91 if wagon_present else 106}, "sites": sites}
    ov.sites = list(sites)
    ov.done, ov.tries, ov.last = set(), {}, {}
    ov.now, ov.day, ov.count, ov.report = now, day, 0, []
    ov.shop_stuck = {}
    ov.site_mem, ov.wagon_seen, ov.mem_tried = {}, None, set()
    ov.material = lambda: 200
    ov.butcher = lambda for_food=True: None
    ov.game = FakeGame()
    ov.built = []
    ov.build = lambda t, retry=3, key=None: ov.built.append((t, key))
    ov.note_w_sites()
    return ov


class MoodShopStuck(unittest.TestCase):
    def test_suspended_frame_counts_as_absent(self):
        ws = [{"id": 1, "type": "Carpenters", "built": True, "x": 90, "y": 94, "z": 91},
              {"id": 6, "type": "Craftsdwarfs", "built": False, "x": 95, "y": 93, "z": 91,
               "job_details": [{"job": "ConstructBuilding", "suspended": True}]}]
        ov = overseer(ws, W_DAY0[1:], True)
        ov.shop_stuck = {6: 0}
        ov.mood()
        self.assertEqual(len(ov.game.calls), 1)
        tool, args = ov.game.calls[0]
        self.assertEqual((tool, args["type"]), ("build_workshop", "Craftsdwarfs"))
        self.assertEqual(args.get("site"), "W10")   # farthest listed site from the wagon at 97,97

    def test_unsuspended_frame_still_counts(self):
        ws = [{"id": 6, "type": "Craftsdwarfs", "built": False, "x": 95, "y": 93, "z": 91,
               "job_details": [{"job": "ConstructBuilding", "suspended": None}]}]
        ov = overseer(ws, W_DAY0[1:], True)
        ov.mood()
        self.assertEqual(ov.game.calls, [])
        self.assertEqual(ov.built, [])

    def test_built_shop_counts_even_if_marked(self):
        ws = [{"id": 6, "type": "Craftsdwarfs", "built": True, "x": 95, "y": 93, "z": 91}]
        ov = overseer(ws, [], True)
        ov.shop_stuck = {6: 0}
        ov.mood()
        self.assertEqual(ov.game.calls, [])

    def test_toppled_wagon_rebuilds_on_remembered_site_by_coordinates(self):
        ov = overseer([{"id": 1, "type": "Carpenters", "built": True, "x": 90, "y": 94, "z": 91}], W_DAY0, True)
        # day 2: the wagon is toppled; observe lists no W site any more (only R1), the Craftsdwarfs is gone
        ov.map = {"wagon": {"present": False, "x": 97, "y": 96, "z": 106},
                  "sites": [{"id": "R1", "kind": "R", "x": 88, "y": 97, "z": 90}]}
        ov.sites = list(ov.map["sites"])
        ov.note_w_sites()
        self.assertEqual(ov.wagon_seen, (97, 97, 91))   # the standing wagon's position is kept
        ov.now, ov.day = 2 * h.DAY, 2
        ov.mood()
        self.assertEqual(len(ov.game.calls), 1)
        _, args = ov.game.calls[0]
        self.assertNotIn("site", args)
        self.assertEqual((args["x"], args["y"], args["z"], args["type"]), (88, 88, 91, "Craftsdwarfs"))
        self.assertIn("W10", ov.mem_tried)

    def test_remembered_site_under_a_frame_is_skipped_and_next_tried(self):
        ws = [{"id": 6, "type": "Craftsdwarfs", "built": False, "x": 88, "y": 88, "z": 91,
               "job_details": [{"job": "ConstructBuilding", "suspended": True}]}]
        ov = overseer(ws, W_DAY0, True)
        ov.map, ov.sites = {"wagon": {"present": False}, "sites": []}, []
        ov.note_w_sites()
        ov.shop_stuck = {6: 1}
        ov.now, ov.day = 4 * h.DAY, 4
        ov.mood()
        _, args = ov.game.calls[0]
        self.assertNotEqual((args["x"], args["y"]), (88, 88))   # W10 holds the stuck frame
        # the next farthest from 97,97: W1 95,93 (4), W2 101,95 (4), W3 100,92 (5) -> W3
        self.assertEqual((args["x"], args["y"]), (100, 92))

    def test_refused_coordinates_move_on(self):
        ov = overseer([], W_DAY0, True)
        ov.map, ov.sites = {"wagon": {"present": False}, "sites": []}, []
        ov.note_w_sites()
        ov.game = FakeGame(ok=False)
        ov.now, ov.day = 3 * h.DAY, 3
        ov.mood()
        first = ov.game.calls[0][1]
        ov.now, ov.day = 6 * h.DAY, 6
        ov.mood()
        second = ov.game.calls[1][1]
        self.assertNotEqual((first["x"], first["y"]), (second["x"], second["y"]))

    def test_no_sites_at_all_falls_back_to_build(self):
        ov = overseer([], [], False)
        ov.mood()
        self.assertEqual(ov.built[0][0], "Craftsdwarfs")
        self.assertEqual(ov.game.calls, [])

    def test_insane_mood_does_nothing(self):
        ov = overseer([], W_DAY0, True)
        ov.o["moods"] = [{"mood": "Berserk", "unit_id": 95}]
        ov.mood()
        self.assertEqual(ov.game.calls, [])
        self.assertEqual(ov.built, [])


def toppled(ov):
    """The observation after the tantrum: wagon gone, only R1 listed."""
    ov.map = {"wagon": {"present": False, "x": 97, "y": 96, "z": 106},
              "sites": [{"id": "R1", "kind": "R", "x": 88, "y": 97, "z": 90}]}
    ov.sites = list(ov.map["sites"])
    ov.note_w_sites()


class BuildAfterToppledWagon(unittest.TestCase):
    def ov(self, workshops=()):
        ov = overseer(list(workshops), W_DAY0 + [G1], True)
        del ov.build   # the real build()
        ov.kind = lambda k: [s for s in ov.sites if str(s.get("id", "")).startswith(k)]
        toppled(ov)
        ov.now, ov.day = 2 * h.DAY, 2
        return ov

    def test_build_uses_remembered_w_site_by_coordinates(self):
        ov = self.ov([{"id": 1, "type": "Carpenters", "built": True, "x": 95, "y": 93, "z": 91}])
        ov.build("Kitchen", key="ws_Kitchen")
        tool, args = ov.game.calls[0]
        self.assertEqual(tool, "build_workshop")
        self.assertNotIn("site", args)
        # W1 (95,93) holds the Carpenters: the next remembered one in site order, W2
        self.assertEqual((args["x"], args["y"], args["z"], args["type"]), (101, 95, 91, "Kitchen"))
        self.assertIn("W2", ov.mem_tried)
        ov.now += 5 * h.DAY
        ov.build("Still", key="ws_Still")
        self.assertEqual((ov.game.calls[1][1]["x"], ov.game.calls[1][1]["y"]), (100, 92))

    def test_listed_w_site_still_preferred(self):
        ov = self.ov()
        ov.sites.append({"id": "W12", "kind": "W", "x": 110, "y": 110, "z": 91, "w": 3, "h": 3})
        ov.build("Kitchen")
        self.assertEqual(ov.game.calls[0][1].get("site"), "W12")
        self.assertEqual(ov.mem_tried, set())

    def test_wagon_standing_keeps_old_behaviour(self):
        ov = overseer([], W_DAY0, True)
        del ov.build
        ov.kind = lambda k: [s for s in ov.sites if str(s.get("id", "")).startswith(k)]
        ov.build("Kitchen")
        self.assertEqual(ov.game.calls[0][1], {"site": "W1", "type": "Kitchen"})
        self.assertNotIn("W1", [s["id"] for s in ov.sites])

    def test_remembered_g_site_args_carry_the_box(self):
        ov = self.ov()
        g = ov.remembered("G")
        self.assertEqual([s["id"] for s in g], ["G1"])
        self.assertEqual(ov.site_args(g[0], box=True), {"x": 90, "y": 100, "z": 91, "w": 3, "h": 3})
        self.assertEqual(ov.site_args({"id": "G2"}, box=True), {"site": "G2"})

    def test_farms_build_on_remembered_g_site(self):
        ov = self.ov()
        ov.o["farm_plots"] = []
        ov.farm_target = lambda: 2
        ov.live_seeds_by_kind = lambda: {"GRASS_WHEAT_CAVE": {"underground": False}}
        ov.dug_rooms = lambda role=None: []
        ov.plot_rooms, ov.roles, ov.wet_z, ov.room_box = set(), {}, set(), {}
        ov.seed_rush = lambda: False
        ov.farms()
        farm = [c for c in ov.game.calls if c[0] == "build_farm"]
        self.assertEqual(farm, [("build_farm", {"x": 90, "y": 100, "z": 91, "w": 3, "h": 3})])
        self.assertIn("G1", ov.mem_tried)

    def test_no_coordinates_while_the_wagon_stands(self):
        ov = overseer([], W_DAY0, True)
        ov.sites = []   # every W site used up, wagon still standing
        self.assertEqual(ov.remembered("W"), [])


G1 = {"id": "G1", "kind": "G", "x": 90, "y": 100, "z": 91, "w": 3, "h": 3}


if __name__ == "__main__":
    unittest.main()
