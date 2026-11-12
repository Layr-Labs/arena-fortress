"""Replay LT08's two available office tiles before beds fill them. No network is used."""
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

AREA = {"id": "A1", "kind": "A", "x": 93, "y": 86, "z": 77, "w": 7, "h": 3,
        "open_tiles": 21}
OFFICE = {"id": 6, "type": "Office", "x": 93, "y": 86, "z": 77, "w": 7, "h": 3}


class FakeGame:
    def __init__(self, chairs=12, zone_ok=True, chair_ok=True):
        self.chairs, self.zone_ok, self.chair_ok = chairs, zone_ok, chair_ok
        self.calls, self.furniture = [], []
        self.zone = None
        # qwen-brew-growth-one-lt08 API line 16: these were the two valid furniture tiles.
        self.tiles = [(93, 86, 77), (93, 88, 77)]

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if tool == "make_zone":
            if not self.zone_ok:
                return {"ok": False, "error_code": "no_space"}
            self.zone = OFFICE.copy()
            return {"ok": True, "result": {"zone_id": 6, "at": [93, 86, 77, 7, 3]}}
        if tool == "assign_zone":
            self.zone["owner"] = args["dwarf_id"]
            return {"ok": True, "result": {"zone_id": 6, "owner": args["dwarf_id"]}}
        kind = args["kind"]
        if kind == "chair" and not self.chair_ok:
            return {"ok": False, "error_code": "no_space"}
        n = min(args.get("count", 1), len(self.tiles), self.chairs if kind == "chair" else 19)
        if not n:
            return {"ok": False, "error_code": "no_space"}
        at = [self.tiles.pop(0) for _ in range(n)]
        for x, y, z in at:
            self.furniture.append({"kind": kind, "x": x, "y": y, "z": z, "built": False})
        if kind == "chair":
            self.chairs -= n
        return {"ok": True, "result": {"n": n, "at": at[0] if n == 1 else at}}

    def observe(self, day=0):
        if day:
            for item in self.furniture:
                item["built"] = True
        zone = copy.deepcopy(self.zone)
        if zone:
            zone["furniture"], zone["furniture_planned"] = {}, {}
            for item in self.furniture:
                counts = zone["furniture" if item["built"] else "furniture_planned"]
                counts[item["kind"]] = counts.get(item["kind"], 0) + 1
        office = {"zone_id": 6, "chair": bool(zone["furniture"].get("chair"))} \
            if zone and zone.get("owner") == 72 else "none"
        return {"tick": 828100 + day * harness.DAY, "observation": {
            "administrators": {"citizens": 19, "manager_active_for_orders": True,
                               "MANAGER_id": 72, "manager_office": office},
            "stocks": {"furniture_free": {"chair": self.chairs}},
            "map": {"sites": [AREA.copy()]}, "zones": [zone] if zone else [],
            "furniture": copy.deepcopy(self.furniture)}}


class OfficeChairFirst(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def agent(self, **kw):
        game = FakeGame(**kw)
        agent = harness.Overseer(game)
        agent.load(game.observe())
        agent.count = 0
        return agent, game

    def test_new_office_keeps_a_chair_when_beds_take_the_remaining_floor(self):
        agent, game = self.agent()
        agent.office()
        game.act("place_furniture", {"kind": "bed", "site": "A1", "count": 19})
        agent.load(game.observe(day=1))
        agent.office()
        self.assertEqual(game.observe(day=1)["observation"]["administrators"]["manager_office"],
                         {"zone_id": 6, "chair": True})
        self.assertEqual([item["kind"] for item in game.furniture], ["chair", "bed"])
        self.assertEqual(game.calls, [
            ("make_zone", {"kind": "office", "site": "A1"}),
            ("place_furniture", {"kind": "chair", "site": "A1"}),
            ("place_furniture", {"kind": "bed", "site": "A1", "count": 19}),
            ("assign_zone", {"zone_id": 6, "dwarf_id": 72})])
        self.assertEqual(agent.count, 3)
        agent.load(game.observe(day=2))
        agent.office()
        self.assertEqual(len(game.calls), 4)

    def test_failed_zone_does_not_place_a_chair(self):
        agent, game = self.agent(zone_ok=False)
        agent.office()
        self.assertEqual(game.calls, [("make_zone", {"kind": "office", "site": "A1"})])
        self.assertEqual(game.chairs, 12)

    def test_no_free_chair_keeps_zone_creation_only(self):
        agent, game = self.agent(chairs=0)
        agent.office()
        self.assertEqual(game.calls, [("make_zone", {"kind": "office", "site": "A1"})])
        self.assertEqual(len(game.tiles), 2)

    def test_retry_blocked_zone_does_not_place_a_chair(self):
        agent, game = self.agent()
        agent.last["office_zone"] = agent.now
        agent.office()
        self.assertEqual(game.calls, [])

    def test_failed_chair_keeps_later_assignment_and_two_day_retry(self):
        agent, game = self.agent(chair_ok=False)
        agent.office()
        self.assertEqual(agent.tries.get("office_chair"), 1)
        game.chair_ok = True
        agent.load(game.observe(day=1))
        agent.office()
        self.assertEqual(len(game.calls), 3)
        self.assertEqual(game.calls[-1], ("assign_zone", {"zone_id": 6, "dwarf_id": 72}))
        agent.load(game.observe(day=2))
        agent.office()
        self.assertEqual(game.calls[-1], ("place_furniture", {"kind": "chair", "site": "A1"}))
        self.assertEqual((len(game.calls), agent.tries["office_chair"]), (4, 1))

    def test_existing_unassigned_office_still_only_assigns(self):
        agent, game = self.agent()
        game.zone = OFFICE.copy()
        agent.load(game.observe())
        agent.office()
        self.assertEqual(game.calls, [("assign_zone", {"zone_id": 6, "dwarf_id": 72})])
        self.assertEqual(game.chairs, 12)


if __name__ == "__main__":
    unittest.main()
