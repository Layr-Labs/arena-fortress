"""The measured stress causes (probe pmy14p on hint hard MY1-4, d57f599 harness; hint hard MY1-3 on e33d381):
stress care at category 2 once the category fell (rising stress), the stress dig never takes a room its own picker
refuses as near the open shaft, and a table and a chair per citizen when the wood allows (LackTables). No game."""
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
from test_bedrooms_all import ZoneGame

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class Base(unittest.TestCase):
    def setUp(self):
        out = redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def ov(self, people, sites=(), day=100, game=None, **kw):
        game = game or FakeGame()
        ov = harness.Overseer(game, days=216)
        ov.load(resp(day=day, cit=len(people), extra={"dwarves": people, "map": {"sites": list(sites)}}, **kw))
        ov.count = 0
        return ov, game

    def reload(self, ov, people, day):
        ov.load(resp(day=day, cit=len(people), extra={"dwarves": people, "map": {"sites": ov.sites}}))
        ov.count = 0


class StressEarly(Base):
    def test_category_two_counts_once_it_fell_from_three(self):
        ov, _ = self.ov([{"id": 231, "stress": 3}, {"id": 5, "stress": 2}])
        self.assertEqual(ov.stressed(), [])          # 5 was never seen higher: a steady 2 is not rising
        self.reload(ov, [{"id": 231, "stress": 2}, {"id": 5, "stress": 2}], 110)
        self.assertEqual([p["id"] for p in ov.stressed()], [231])

    def test_band_first_then_rising(self):
        ov, _ = self.ov([{"id": 1, "stress": 3}, {"id": 2, "stress": 4}])
        self.reload(ov, [{"id": 1, "stress": 2}, {"id": 2, "stress": 1}], 110)
        self.assertEqual([p["id"] for p in ov.stressed()], [2, 1])

    def test_rising_citizen_gets_the_room(self):
        sites = [{"id": "R0", "kind": "R", "dug": True, "designated": True, "x": 10, "y": 5, "z": 140,
                  "w": 3, "h": 3}]
        ov, game = self.ov([{"id": 231, "stress": 3}], sites, game=ZoneGame())
        ov.stress_housing()
        self.assertEqual([t for t, _ in game.calls if t == "make_zone"], [])
        self.reload(ov, [{"id": 231, "stress": 2}], 110)
        ov.stress_housing()
        self.assertIn(("assign_zone", 231), [(t, a.get("dwarf_id")) for t, a in game.calls if t == "assign_zone"])


class StressDigOffShaft(Base):
    def test_no_dig_for_a_room_the_picker_refuses(self):
        """hint hard MY1-3 on e33d381: R2/R3 dug for the stressed leader, both 3 tiles off the open shaft."""
        sites = [{"id": "R2", "kind": "R", "designated": False, "dug": False, "x": 10, "y": 5, "z": 140, "w": 3, "h": 3},
                 {"id": "R3", "kind": "R", "designated": False, "dug": False, "x": 40, "y": 5, "z": 140, "w": 3, "h": 3}]
        ov, game = self.ov([{"id": 84, "stress": 1}], sites)
        ov.room_near_shaft = lambda r: r.get("id") == "R2"
        ov.stress_housing()
        self.assertEqual([a["site"] for t, a in game.calls if t == "dig_room"], ["R3"])

    def test_every_room_near_the_shaft_digs_nothing(self):
        sites = [{"id": "R2", "kind": "R", "designated": False, "dug": False, "x": 10, "y": 5, "z": 140, "w": 3, "h": 3}]
        ov, game = self.ov([{"id": 84, "stress": 1}], sites)
        ov.room_near_shaft = lambda r: True
        ov.stress_housing()
        self.assertEqual([t for t, _ in game.calls if t == "dig_room"], [])


class SeatsForAll(Base):
    def people(self, n):
        return [{"id": i, "stress": 4} for i in range(n)]

    def test_full_seats_when_the_wood_allows(self):
        ov, _ = self.ov(self.people(19))
        ov.st.update(tables=12, chairs=12)
        ov.logs = lambda: 300
        self.assertEqual(ov.seats_full(), 19)

    def test_no_full_seats_on_short_wood_or_a_lean_harvest(self):
        ov, _ = self.ov(self.people(19))
        ov.st.update(tables=12, chairs=12)
        ov.logs = lambda: ov.logs_guard() + 5        # 14 logs short of 7 tables and 7 chairs
        self.assertEqual(ov.seats_full(), 0)
        ov.logs = lambda: 300
        ov.harvest_furniture_lean = lambda: True
        self.assertEqual(ov.seats_full(), 0)

    def test_supply_orders_tables_and_chairs_to_the_census(self):
        ov, game = self.ov(self.people(19))
        ov.st.update(tables=12, chairs=12, beds=30)
        ov.logs = lambda: 300
        ov.stray = lambda kind: 0
        ov.supply()
        amounts = {a["recipe"]: a["amount"] for t, a in game.calls if t == "add_order"
                   and a.get("recipe") in ("make_table", "make_chair")}
        self.assertEqual(amounts.get("make_table"), 7)          # 19 - 12
        self.assertEqual(amounts.get("make_chair"), 8)          # 19 + the manager's desk - 12


if __name__ == "__main__":
    unittest.main()
