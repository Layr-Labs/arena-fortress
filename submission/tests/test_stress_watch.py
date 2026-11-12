"""cx stress watch: a daily log line naming who sits at stress category <= 2 and their most unmet needs (hint hard
MY1-4 on d57f599: nothing in the game's records said why one citizen rose at day 191). No game or network."""
import io
import json
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


def lines(buf, kind):
    out = []
    for l in buf.getvalue().splitlines():
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if r.get("kind") == kind:
            out.append(r)
    return out


class StressWatch(unittest.TestCase):
    def fort(self, people, units, day=100):
        game = FakeGame(units=units)
        buf = io.StringIO()
        with redirect_stdout(buf):
            ov = harness.Overseer(game, days=216)
            ov.load(resp(day=day, cit=len(people), extra={"dwarves": people}))
            ov.count = 0
        return ov, game, buf

    def test_logs_low_citizens_with_their_most_unmet_needs_once_a_day(self):
        people = [{"id": 231, "stress": 2, "job": "idle", "squad_id": 0, "x": 96, "y": 90, "z": 168},
                  {"id": 95, "stress": 4}]
        units = [{"id": 231, "needs": [{"need": "AdmireArt", "focus_level": -8008, "need_level": 2},
                                       {"need": "DrinkAlcohol", "focus_level": -1590, "need_level": 10},
                                       {"need": "Socialize", "focus_level": 392, "need_level": 2}]},
                 {"id": 95, "needs": [{"need": "MakeMerry", "focus_level": -5528, "need_level": 1}]}]
        ov, game, buf = self.fort(people, units)
        with redirect_stdout(buf):
            ov.stress_watch()
            ov.stress_watch()   # the same day: no second line, no second query
        rows = lines(buf, "stress_watch")
        self.assertEqual(len(rows), 1)
        self.assertEqual(game.queries, 1)
        self.assertEqual(game.calls, [])
        (c,) = rows[0]["cits"]
        self.assertEqual((c["id"], c["cat"], c["squad"], c["at"]), (231, 2, 0, [96, 90, 168]))
        self.assertEqual([n[0] for n in c["unmet"]], ["AdmireArt", "DrinkAlcohol"])   # focus x level, worst first

    def test_quiet_fort_neither_queries_nor_logs(self):
        ov, game, buf = self.fort([{"id": 1, "stress": 3}], [])
        with redirect_stdout(buf):
            ov.stress_watch()
        self.assertEqual(lines(buf, "stress_watch"), [])
        self.assertEqual(game.queries, 0)

    def test_lost_query_still_logs_the_categories(self):
        ov, game, buf = self.fort([{"id": 7, "stress": 1}], [])
        game.query = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))
        with redirect_stdout(buf):
            ov.stress_watch()
        (row,) = lines(buf, "stress_watch")
        self.assertEqual(row["cits"][0]["unmet"], [])


if __name__ == "__main__":
    unittest.main()
