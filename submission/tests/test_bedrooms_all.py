"""cx bedrooms for everyone (cup probe std MY1-4 on cf32708: LackBedroom the 2nd negative thought, 0 bedroom zones,
no citizen owned a bed) and the dining chairs (11 tables, 8 chairs at the horizon: two overlapping dining zones
counted the same chairs twice). No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness
from test_cx_alloc import FakeGame, resp

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class ZoneGame(FakeGame):
    def act(self, tool, args):
        if tool == "make_zone":
            self.calls.append((tool, args.copy()))
            return {"ok": True, "result": {"zone_id": 600 + len(self.calls), "at": [0, 0, 140, 3, 3]}}
        return super().act(tool, args)


def rooms(n, dug=True, z=140):
    return [{"id": "R%d" % i, "kind": "R", "dug": dug, "designated": dug, "x": 10 * i, "y": 5, "z": z,
             "w": 3, "h": 3} for i in range(n)]


class Base(unittest.TestCase):
    def setUp(self):
        out = redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def ov(self, people, sites, beds=2, game=None, **kw):
        game = game or ZoneGame()
        ov = harness.Overseer(game, days=336)
        r = resp(day=100, cit=len(people), extra={"dwarves": people, "map": {"sites": sites}}, **kw)
        r["observation"]["stocks"]["furniture_free"] = {"bed": beds}
        ov.load(r)
        ov.count = 0
        return ov, game


class Bedrooms(Base):
    def test_unstressed_citizens_get_rooms_newest_adults_first(self):
        people = [{"id": 10, "stress": 4, "adult": True}, {"id": 30, "stress": 4, "adult": False},
                  {"id": 20, "stress": 4, "adult": True}]
        ov, game = self.ov(people, rooms(3))
        ov.house_everyone()
        zones = [a for t, a in game.calls if t == "make_zone"]
        self.assertEqual([z["kind"] for z in zones], ["bedroom"] * harness.BEDROOM_PASS_CAP)
        self.assertEqual(len({z["site"] for z in zones}), len(zones))
        assigned = [a["dwarf_id"] for t, a in game.calls if t == "assign_zone"]
        self.assertEqual(assigned, [20, 10])   # adults newest first, the child after them
        beds = [a for t, a in game.calls if t == "place_furniture"]
        self.assertEqual(len(beds), 2)
        self.assertTrue(all(b["kind"] == "bed" and b["w"] == b["h"] == harness.STRESS_ROOM_SIZE for b in beds))

    def test_owned_rooms_are_left_alone(self):
        people = [{"id": 1, "stress": 4}]
        ov, game = self.ov(people, rooms(2))
        ov.zones = [{"id": 5, "type": "Bedroom", "owner": 1, "x": 0, "y": 5, "z": 140, "w": 3, "h": 3}]
        ov.house_everyone()
        self.assertEqual(game.calls, [])

    def test_off_in_hands_off_windows_and_surge(self):
        people = [{"id": 1, "stress": 4}]
        ov, game = self.ov(people, rooms(2), hands_off=10)
        ov.house_everyone()
        self.assertEqual(game.calls, [])
        ov, game = self.ov(people, rooms(2))
        ov.surge = True
        ov.house_everyone()
        self.assertEqual(game.calls, [])

    def test_no_free_room_digs_bedroom_rooms_two_at_a_time(self):
        people = [{"id": i, "stress": 4, "adult": True} for i in range(5)]
        ov, game = self.ov(people, rooms(4, dug=False))
        ov.house_everyone()
        digs = [a["site"] for t, a in game.calls if t == "dig_room"]
        self.assertEqual(len(digs), harness.BEDROOM_PASS_CAP)
        self.assertTrue(all(ov.roles.get(s) == "bedroom" for s in digs))
        # the next pass sees them designated and undug: no third dig while two are in flight
        for s in ov.sites:
            if s["id"] in digs:
                s["designated"] = True
        game.calls.clear()
        for k in list(ov.last):
            ov.last.pop(k)
        ov.house_everyone()
        self.assertEqual([t for t, _ in game.calls if t == "dig_room"], [])

    def test_no_free_bed_orders_beds(self):
        people = [{"id": 1, "stress": 4}]
        ov, game = self.ov(people, rooms(1), beds=0)
        ov.house_everyone()
        self.assertIn("make_bed", [a.get("recipe") for t, a in game.calls if t == "add_order"])
        self.assertIn("assign_zone", [t for t, _ in game.calls])

    def test_near_shaft_room_is_skipped(self):
        people = [{"id": 1, "stress": 4}]
        ov, game = self.ov(people, rooms(2))
        ov.shaft_people = lambda: True
        ov.shaft_near = lambda box: box.get("x") == 0
        self.assertEqual(ov.stress_site()["id"], "R1")


class DiningChairs(Base):
    def test_overlapping_dining_zones_count_each_item_once(self):
        ov, _ = self.ov([{"id": 1, "stress": 4}], [])
        ov.zones = [{"id": 39, "type": "DiningHall", "furniture": {"chair": 4, "table": 9}},
                    {"id": 57, "type": "DiningHall", "furniture": {"chair": 7, "table": 11}}]
        ov.o["furniture"] = [{"kind": "chair", "built": True, "zone_ids": [39, 57]} for _ in range(4)] \
            + [{"kind": "chair", "built": True, "zone_ids": [57]} for _ in range(3)] \
            + [{"kind": "table", "built": True, "zone_ids": [39, 57]} for _ in range(9)] \
            + [{"kind": "table", "built": True, "zone_ids": [57]} for _ in range(2)]
        self.assertEqual(ov.dine_count("chair"), 7)
        self.assertEqual(ov.dine_count("table"), 11)

    def test_zone_sum_without_furniture_ids(self):
        ov, _ = self.ov([{"id": 1, "stress": 4}], [])
        ov.zones = [{"id": 57, "type": "DiningHall", "furniture": {"chair": 7, "table": 11}}]
        self.assertEqual(ov.dine_count("chair"), 7)


if __name__ == "__main__":
    unittest.main()
