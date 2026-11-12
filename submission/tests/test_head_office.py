"""cx: the liaison's meeting room. In the 10 measured hint OP1 runs with daily.json (cx*/f7f4716b/full2, read
2026-11-10) the outpost liaison arrived on day 163-169 and left unhappy on day 174-198 every time, and no
expedition leader owned an office in any run's observation at that point. On full-year open play the head of the
site (expedition leader, and any citizen holding a HEAD_POSITIONS code such as a claimed MONARCH) gets an office
zone with a chair from LIAISON_OFFICE_DAY. MY1 and the hands-off labs are unchanged. No game or network is used."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

ROOM = {"id": "R5", "kind": "R", "x": 80, "y": 80, "z": 150, "w": 3, "h": 3, "dug": True, "free": True,
        "open_tiles": 9}
LEVEL = {"id": "A4", "kind": "A", "x": 70, "y": 70, "z": 151, "w": 12, "h": 9, "open_tiles": 80}
MGR_OFFICE = {"id": 42, "type": "Office", "x": 70, "y": 70, "z": 151, "w": 12, "h": 9, "owner": 96,
              "furniture": {"chair": 1}}


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"zone_id": 77}}


def dwarf(did, positions=()):
    return {"id": did, "adult": True, "positions": list(positions), "stress": 3, "job": "idle"}


def facts(day=130, zones=(), people=None, leader=99, chairs=2, hands_off=None):
    people = people if people is not None else [dwarf(96, ["MANAGER"]), dwarf(leader, ["EXPEDITION_LEADER"]),
                                                dwarf(101)]
    return {"day": day, "tick": day * 1200, "hands_off_in_days": hands_off, "days_left": 336 - day, "observation": {
        "administrators": {"citizens": 15, "manager_active_for_orders": True, "MANAGER_id": 96,
                           "EXPEDITION_LEADER_id": leader, "manager_office": {"chair": True, "zone_id": 42}},
        "stocks": {"logs_usable": 60, "boulders_usable": 0, "drink": 200, "food_edible": 100,
                   "beds": 10, "tables": 8, "chairs": 9, "furniture_free": {"chair": chairs}},
        "map": {"sites": []}, "zones": [dict(z) for z in zones], "furniture": [], "workshops": [],
        "orders": [], "plugins": {}, "dwarves": people, "date": {"abs_tick": day * 1200},
    }}


class HeadOffice(unittest.TestCase):
    def setUp(self):
        self.buffer = io.StringIO()
        self.output = redirect_stdout(self.buffer)
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, days=336, sites=(ROOM, LEVEL), **kw):
        game = FakeGame()
        ov = harness.Overseer(game, days=days)
        ov.load(facts(**kw))
        ov.sites = [dict(s) for s in sites]
        ov.count = 0
        return ov, game

    def test_leader_gets_an_office_zone_and_chair_on_a_free_room(self):
        ov, game = self.overseer(zones=(MGR_OFFICE,))
        ov.head_offices()
        self.assertEqual(game.calls[0], ("make_zone", {"kind": "office", "site": "R5"}))
        self.assertEqual(game.calls[1], ("assign_zone", {"zone_id": 77, "dwarf_id": 99}))   # the head's at once
        self.assertEqual(game.calls[2], ("place_furniture", {"kind": "chair", "site": "R5"}))
        self.assertIn("R5", ov.stress_rooms)          # the room is reserved: no private bedroom lands on it
        self.assertIn(77, ov.head_zones)

    def test_a_head_zone_is_never_the_managers_spare(self):
        # hint std OP1-4 on b796327: the leader's R5 office (zone 71, day 161) went to the manager on day 203
        head = {"id": 71, "type": "Office", "x": 80, "y": 80, "z": 150, "w": 3, "h": 3, "owner": None}
        ov, game = self.overseer(zones=(head,))
        ov.head_zones.add(71)
        ov.head_offices()
        self.assertIn(("assign_zone", {"zone_id": 71, "dwarf_id": 99}), game.calls)
        ov2, game2 = self.overseer(zones=(head,))
        ov2.head_zones.add(71)
        ov2.adm["manager_office"] = None
        ov2.office()
        self.assertNotIn(("assign_zone", {"zone_id": 71, "dwarf_id": 96}), game2.calls)

    def test_a_failed_zone_assigns_nothing(self):
        ov, game = self.overseer(zones=(MGR_OFFICE,))
        game.act = lambda tool, args: (game.calls.append((tool, args.copy())) or
                                       {"ok": False, "error_code": "site_used", "error": "used"})
        ov.head_offices()
        self.assertEqual([t for t, _ in game.calls], ["make_zone"])
        self.assertEqual(ov.head_zones, set())

    def test_the_new_unowned_office_is_assigned_to_the_leader(self):
        new = {"id": 77, "type": "Office", "x": 80, "y": 80, "z": 150, "w": 3, "h": 3, "owner": None,
               "furniture_planned": {"chair": 1}}
        ov, game = self.overseer(zones=(MGR_OFFICE, new))
        ov.head_offices()
        self.assertEqual(game.calls, [("assign_zone", {"zone_id": 77, "dwarf_id": 99})])

    def test_a_manager_without_a_desk_keeps_the_first_spare(self):
        spare = {"id": 70, "type": "Office", "x": 80, "y": 80, "z": 150, "w": 3, "h": 3, "owner": None}
        ov, game = self.overseer(zones=(spare,))
        ov.head_offices()
        self.assertNotIn(("assign_zone", {"zone_id": 70, "dwarf_id": 99}), game.calls)

    def test_an_owned_office_without_a_chair_gets_one(self):
        mine = {"id": 77, "type": "Office", "x": 80, "y": 80, "z": 150, "w": 3, "h": 3, "owner": 99,
                "furniture": {}}
        ov, game = self.overseer(zones=(MGR_OFFICE, mine))
        ov.head_offices()
        self.assertEqual(game.calls, [("place_furniture", {"kind": "chair", "site": "R5"})])
        done = dict(mine, furniture={"chair": 1})
        ov2, game2 = self.overseer(zones=(MGR_OFFICE, done))
        ov2.head_offices()
        self.assertEqual(game2.calls, [])

    def test_a_claimed_monarch_is_a_head_too(self):
        people = [dwarf(96, ["MANAGER"]), dwarf(99, ["EXPEDITION_LEADER"]), dwarf(102, ["MONARCH"])]
        ov, game = self.overseer(zones=(MGR_OFFICE,), people=people)
        self.assertEqual(ov.head_ids(), [99, 102])
        ov.head_offices()
        made = [a["site"] for t, a in game.calls if t == "make_zone"]
        self.assertEqual(made, ["R5", "A4"])          # the second head falls back to a dug level

    def test_the_manager_is_never_a_head_here(self):
        people = [dwarf(96, ["MANAGER", "EXPEDITION_LEADER"])]
        ov, game = self.overseer(zones=(MGR_OFFICE,), people=people, leader=96)
        ov.head_offices()
        self.assertEqual(game.calls, [])

    def test_off_before_the_day_on_my1_and_on_labs(self):
        for kw in ({"day": harness.LIAISON_OFFICE_DAY - 1}, {"days": 216}, {"hands_off": 40}):
            days = kw.pop("days", 336)
            ov, game = self.overseer(days=days, zones=(MGR_OFFICE,), **kw)
            ov.head_offices()
            self.assertEqual(game.calls, [], kw)

    def test_full_year_chair_target_carries_the_heads(self):
        people = [dwarf(96, ["MANAGER"]), dwarf(99, ["EXPEDITION_LEADER"]), dwarf(102, ["MONARCH"])]
        ov, _ = self.overseer(zones=(MGR_OFFICE,), people=people)
        self.assertEqual(ov.chair_target(10), 13)      # 10 seats + the manager's desk + two heads
        ov_my1, _ = self.overseer(days=216, zones=(MGR_OFFICE,), people=people)
        self.assertEqual(ov_my1.chair_target(10), 11)  # MY1 keeps seats + 1
        ov_lab, _ = self.overseer(zones=(MGR_OFFICE,), people=people, hands_off=40)
        self.assertEqual(ov_lab.chair_target(10), 11)

class StandaloneMain(unittest.TestCase):
    def test_main_passes_the_task_horizon(self):
        # the standalone entry point used days=0, which turns off every full-year rule (head_offices among them)
        import os
        from unittest import mock
        seen = {}

        class Stop(Exception):
            pass

        def fake(game, goal="", days=0):
            seen.update(goal=goal, days=days)
            raise Stop()
        task = '{"game_url": "http://127.0.0.1:9", "task": {"days": 336, "goal": "Run the fortress"}}'
        with mock.patch.dict(os.environ, {"DFBENCH_TASK": task}), mock.patch.object(harness, "Overseer", fake), \
                redirect_stdout(io.StringIO()):
            with self.assertRaises(Stop):
                harness.main()
        self.assertEqual(seen, {"goal": "Run the fortress", "days": 336})


if __name__ == "__main__":
    unittest.main()
