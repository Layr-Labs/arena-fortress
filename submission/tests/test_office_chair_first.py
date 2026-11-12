"""cx office chair first (hint std LT08-1 on 5c14f02, 65.08: beds 19 for 50, drink 480 -> 475). On day 8 office_move
zoned the dug office room R6 (94,94,163) for manager 90 with free chair 0, and office_release handed the chaired A1
office (zone 7, 103,96,164) to citizen 91; DF cancelled the manager's d17 round with "Need office." and no work order
was validated until d43, so no bed was made in time. Shapes are the record's day-8 / day-11 observations. No game or
network."""
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

R6 = {"id": "R6", "kind": "R", "x": 94, "y": 94, "z": 163, "w": 3, "h": 3, "soil": True, "dug": True,
      "designated": True, "stair": {"x": 93, "y": 95}, "subterranean": True, "free": True}
Z7 = {"id": 7, "type": "Office", "owner": 90, "x": 103, "y": 96, "z": 164, "w": 1, "h": 1, "furniture": {"chair": 1},
      "building_ids": [6]}
Z60 = {"id": 60, "type": "Office", "owner": 90, "x": 94, "y": 94, "z": 163, "w": 3, "h": 3, "furniture": {}}
CHAIR7 = {"built": True, "id": 6, "kind": "chair", "x": 103, "y": 96, "z": 164}
ADM = {"citizens": 41, "MANAGER_id": 90, "manager_active_for_orders": True, "manager_required_office": 1}


class Game(FakeGame):
    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"zone_id": 60, "order_id": 1}}


class Base(unittest.TestCase):
    def setUp(self):
        out = redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def ov(self, zones=(Z7,), chairs=0, furniture=(CHAIR7,), office=None, day=8):
        game = Game()
        ov = harness.Overseer(game, goal="Migrants are arriving.", days=60)
        r = resp(day=day, days=60, cit=41, hands_off=31,
                 extra={"map": {"sites": [dict(R6)]}, "zones": [dict(z) for z in zones],
                        "furniture": [dict(f) for f in furniture]})
        r["observation"]["administrators"] = dict(ADM, manager_office=office or {"chair": True, "zone_id": 7})
        r["observation"]["stocks"]["furniture_free"] = {"chair": chairs}
        ov.load(r)
        ov.count = 0
        ov.roles.update({"R6": "office"})
        # the record: zone 7's tile is roofed (box 0) and its level runs out to open ground (level_open 1 from d6)
        ov.box_open = lambda box: 0
        ov.level_open = lambda box: 1
        ov.office_beasts = lambda box: []
        return ov, game

    def tools(self, game):
        return [(t, a.get("site") or a.get("zone_id")) for t, a in game.calls]


class MoveWaitsForChair(Base):
    def test_measured_day_8_no_free_chair_keeps_the_chaired_office(self):
        ov, game = self.ov()
        ov.office()
        self.assertEqual(game.calls, [])

    def test_free_chair_moves_with_its_chair(self):
        ov, game = self.ov(chairs=1)
        ov.office()
        tools = self.tools(game)
        self.assertIn(("make_zone", "R6"), tools)
        self.assertIn(("assign_zone", 60), tools)
        self.assertIn(("place_furniture", "R6"), tools)

    def test_chair_already_in_the_room_moves(self):
        chair = {"built": True, "id": 70, "kind": "chair", "x": 95, "y": 95, "z": 163}
        ov, game = self.ov(furniture=(CHAIR7, chair))
        ov.office()
        self.assertIn(("make_zone", "R6"), self.tools(game))

    def test_switch_off_is_as_before(self):
        old = harness.OFFICE_CHAIR_FIRST
        harness.OFFICE_CHAIR_FIRST = False
        self.addCleanup(setattr, harness, "OFFICE_CHAIR_FIRST", old)
        ov, game = self.ov()
        ov.office()
        self.assertIn(("make_zone", "R6"), self.tools(game))


class ReleaseKeepsTheChair(Base):
    def r6_used(self, ov):
        for s in ov.sites:
            if s.get("id") == "R6":
                s["free"] = False
                s["used_by"] = ["Office 60"]

    def test_measured_day_11_chaired_office_not_released(self):
        # d11 after the model gave zone 7 back: the manager owns 7 (chair) and 60 (on R6, no chair)
        ov, game = self.ov(zones=(Z7, Z60), day=11)
        self.r6_used(ov)
        self.assertFalse(ov.office_release(90))
        ov.office()
        self.assertNotIn(("assign_zone", 7), self.tools(game))

    def test_chaired_settled_office_releases_the_open_one(self):
        z60 = dict(Z60, furniture={"chair": 1})
        ov, game = self.ov(zones=(Z7, z60), day=11)
        self.r6_used(ov)
        ov.office_holder = lambda mgr: 91
        self.assertTrue(ov.office_release(90))
        self.assertIn(("assign_zone", 7), self.tools(game))

    def test_no_chair_anywhere_is_as_before(self):
        z7 = dict(Z7, furniture={})
        ov, game = self.ov(zones=(z7, Z60), day=11)
        self.r6_used(ov)
        ov.office_holder = lambda mgr: 91
        self.assertTrue(ov.office_release(90))


if __name__ == "__main__":
    unittest.main()
