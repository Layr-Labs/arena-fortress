"""cx office yield + miner guard (hint std LT08-2 on 838106a, 2026-11-11: one death, beds 45 / 48, score 4.44).

Measured shape (the record's api.jsonl / output.log): the manager's office was the 1x1 box over the chair at A1's corner
(83,67,104), a roofed overhang at the north rim of an open valley floor above the river; alligators 113/114 stood at
z101-102, 12-20 tiles off, on days 0-7 and came up to (89,62,104) / (88,61,104) on days 8-9. On day 9.6 the manager
went to the office, was attacked at (84,67,104) and killed at (74,81,105). He was the only citizen holding MINE, so the
43 pending dorm tiles on z104 were never dug and the beds stopped at 45 placed for 48 citizens. No game or network."""
import copy
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness  # noqa: E402

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

OFFICE = {"id": 7, "type": "Office", "x": 83, "y": 67, "z": 104, "w": 1, "h": 1, "owner": 92, "furniture": {"chair": 1}}
GATOR_RIVER = [{"id": 113, "race": "ALLIGATOR", "x": 65, "y": 71, "z": 101, "hostile": False},     # day 0: 18 tiles
               {"id": 114, "race": "ALLIGATOR", "x": 64, "y": 71, "z": 101, "hostile": False}]
GATOR_DAY8 = [{"id": 113, "race": "ALLIGATOR", "x": 89, "y": 62, "z": 104, "hostile": False},      # 6 tiles, same z
              {"id": 114, "race": "ALLIGATOR", "x": 80, "y": 56, "z": 102, "hostile": False}]
GATOR_DAY10 = [{"id": 113, "race": "ALLIGATOR", "x": 135, "y": 54, "z": 103, "hostile": False},    # 52 tiles
               {"id": 114, "race": "ALLIGATOR", "x": 58, "y": 99, "z": 104, "hostile": False}]     # 32 tiles


def dwarves():
    out = [{"id": 92, "adult": True, "positions": ["MANAGER"], "x": 94, "y": 84, "z": 104, "job": "idle"},
           {"id": 98, "adult": True, "positions": ["EXPEDITION_LEADER"], "x": 96, "y": 85, "z": 104, "job": "idle"}]
    out += [{"id": i, "adult": True, "positions": [], "x": 93, "y": 82, "z": 104, "job": "idle"} for i in (93, 94, 95)]
    return out


class FakeGame:
    def __init__(self, others, citizens=None):
        self.others, self.citizens = list(others), citizens
        self.calls, self.zones = [], [dict(OFFICE)]
        self.manager = 92

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool == "assign_zone":
            z = next(z for z in self.zones if z["id"] == args["zone_id"])
            z["owner"] = args["dwarf_id"]
            return {"ok": True, "result": {"zone_id": z["id"], "owner": args["dwarf_id"], "changed": True}}
        if tool == "enable_automation":
            return {"ok": True, "result": {"name": args["name"], "was": "off", "now": "on"}}
        return {"ok": True, "result": {}}

    def query(self, name, **kw):
        if kw.get("kind") == "citizens":
            return {"result": {"units": copy.deepcopy(self.citizens or [])}}
        return {"result": {"units": copy.deepcopy(self.others)}}

    def observe(self, day=0, pending=0, beds=45, cit=48):
        mine = next((z for z in self.zones if z.get("owner") == self.manager), None)
        return {"tick": 828100 + day * harness.DAY, "day": day, "hands_off_in_days": 39 - day, "days_left": 60 - day,
                "observation": {
                    "date": {"abs_tick": 828100 + day * harness.DAY},
                    "administrators": {"citizens": cit, "manager_active_for_orders": True, "MANAGER_id": self.manager,
                                       "manager_office": {"zone_id": mine["id"], "chair": True} if mine else "none"},
                    "stocks": {"furniture_free": {"chair": 0}},
                    "dwarves": dwarves(),
                    "map": {"sites": [{"id": "A1", "kind": "A", "x": 83, "y": 67, "z": 104, "w": 41, "h": 41,
                                       "open_tiles": 71}], "surface_z": 105},
                    "zones": copy.deepcopy(self.zones),
                    "furniture": [{"kind": "bed", "z": 104} for _ in range(beds)],
                    "dig_designations_pending": pending,
                    "plugins": {"autolabor": "off"}}}


class Quiet(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def agent(self, others, citizens=None, goal="", day=0, **kw):
        game = FakeGame(others, citizens)
        agent = harness.Overseer(game, goal=goal, days=60)
        agent.count = 0
        agent.load(game.observe(day=day, **kw))
        return agent, game


class OfficeYield(Quiet):
    def test_river_gators_leave_the_office_alone(self):
        # days 0-5: 17-26 tiles off, 3 levels down — the office stays the manager's
        agent, game = self.agent(GATOR_RIVER)
        agent.office_guard()
        self.assertEqual(game.calls, [])
        self.assertIsNone(agent.office_yield)

    def test_day8_gator_on_the_office_level_hands_the_office_away_and_back(self):
        agent, game = self.agent(GATOR_DAY8, day=8)
        agent.office_guard()
        self.assertEqual(game.calls, [("assign_zone", {"zone_id": 7, "dwarf_id": 93})])
        self.assertEqual(agent.office_yield["holder"], 93)
        # office() makes and assigns nothing while yielded (the manager reads "no office" now)
        agent.load(game.observe(day=8))
        n = len(game.calls)
        agent.office()
        agent.office_guard()
        self.assertEqual(len(game.calls), n)
        # day 9: still near -> held; day 10: gone, but the clear clock starts; day 11: back to the manager
        game.others = GATOR_DAY8
        agent.load(game.observe(day=9))
        agent.office_guard()
        self.assertEqual(len(game.calls), n)
        game.others = GATOR_DAY10
        agent.load(game.observe(day=10))
        agent.office_guard()
        self.assertEqual(len(game.calls), n)
        agent.load(game.observe(day=11))
        agent.office_guard()
        self.assertEqual(game.calls[-1], ("assign_zone", {"zone_id": 7, "dwarf_id": 92}))
        self.assertIsNone(agent.office_yield)
        self.assertEqual(game.zones[0]["owner"], 92)

    def test_a_return_behind_the_layers_back_is_yielded_again(self):
        # the model gave the office back to the manager (it did assign_zone 7 on day 10 of the record)
        agent, game = self.agent(GATOR_DAY8, day=8)
        agent.office_guard()
        game.zones[0]["owner"] = 92
        agent.load(game.observe(day=8.5))
        agent.office_guard()
        self.assertEqual(game.calls[-1], ("assign_zone", {"zone_id": 7, "dwarf_id": 93}))
        self.assertEqual(game.zones[0]["owner"], 93)

    def test_close_but_three_levels_down_counts(self):
        # day 6 of the record: 113 at (73,55,102), 12 tiles and 2 levels from the office (the manager went there)
        agent, game = self.agent([{"id": 113, "race": "ALLIGATOR", "x": 73, "y": 55, "z": 102}], day=6)
        agent.office_guard()
        self.assertEqual(game.calls, [("assign_zone", {"zone_id": 7, "dwarf_id": 93})])

    def test_snapping_turtle_and_tame_animals_do_not_count(self):
        others = [{"id": 1, "race": "ALLIGATOR_SNAPPING_TURTLE", "x": 84, "y": 66, "z": 104},
                  {"id": 2, "race": "DOG", "x": 84, "y": 66, "z": 104}]
        agent, game = self.agent(others, day=8)
        agent.office_guard()
        self.assertEqual(game.calls, [])

    def test_an_unowned_office_is_not_handed_to_the_manager_while_a_beast_is_near(self):
        agent, game = self.agent(GATOR_DAY8, day=8)
        game.zones[0]["owner"] = None
        agent.load(game.observe(day=8))
        agent.office()
        self.assertEqual(game.calls, [])
        game.others = GATOR_DAY10
        agent.load(game.observe(day=10))
        agent.office()
        self.assertEqual(game.calls, [("assign_zone", {"zone_id": 7, "dwarf_id": 92})])

    def test_no_holder_without_a_position_keeps_the_office(self):
        agent, game = self.agent(GATOR_DAY8, day=8)
        agent.people = [p for p in agent.people if p.get("positions")]
        agent.office_guard()
        self.assertEqual(game.calls, [])


if __name__ == "__main__":
    unittest.main()
