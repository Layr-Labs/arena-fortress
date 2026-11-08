"""The mood-danger warning: the overseer records when a waiting strange mood was first seen, and the digest turns an
age past the danger threshold into a NEXT line. No game or network is used."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness
from plain import digest

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__
assert Path(digest.__file__).is_relative_to(VARIANT), digest.__file__

DAY = digest.DAY


def mood_env(waited_days):
    tick = 100 * DAY
    obs = {"administrators": {"citizens": 9}, "stocks": {},
           "moods": [{"unit_id": 5, "mood": "Fey", "skill": "MASONRY", "job": "StrangeMoodMason",
                      "waiting": True, "items_needed": [{"item": "BOULDER", "collected": 0}]}]}
    layer = {"mood_waiting": {5: tick - int(waited_days * DAY)}} if waited_days is not None else {}
    return digest.digest(obs, {"day": 100, "tick": tick}, layer=layer)


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"id": len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {}}


def resp(moods, plugins=None):
    return {"tick": 3 * DAY, "day": 50, "observation": {
        "administrators": {"citizens": 9}, "stocks": {"logs_usable": 10},
        "map": {"surface_z": 10, "sites": [{"id": "W1", "kind": "W", "x": 5, "y": 5, "z": 10}]},
        "plugins": {} if plugins is None else plugins, "moods": moods}}


class MoodDanger(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, response):
        game = FakeGame()
        ov = harness.Overseer(game)
        ov.load(response)
        ov.count = 0
        return ov, game

    def test_long_waiting_mood_gets_a_danger_line_in_next(self):
        text = mood_env(23)
        self.assertIn("23 d waiting", text)
        self.assertIn("MOOD DANGER: dwarf 5", text)

    def test_short_waiting_mood_stays_informational(self):
        text = mood_env(5)
        self.assertIn("5 d waiting", text)
        self.assertNotIn("MOOD DANGER", text)

    def test_unknown_age_has_no_warning(self):
        text = mood_env(None)
        self.assertNotIn("d waiting", text)
        self.assertNotIn("MOOD DANGER", text)

    def test_overseer_records_first_seen_and_enables_autochop_for_logs(self):
        ov, game = self.overseer(resp([{"unit_id": 5, "mood": "Fey", "skill": "MASONRY", "waiting": True,
                                        "items_needed": [{"item": "LOGS", "collected": 0}]}]))
        ov.mood()
        self.assertEqual(ov.mood_seen, {5: 3 * DAY})
        self.assertIn(("enable_automation", {"name": "autochop"}), game.calls)

    def test_overseer_forgets_a_mood_that_is_gone(self):
        ov, game = self.overseer(resp([{"unit_id": 5, "mood": "Fey", "skill": "MASONRY", "waiting": True,
                                        "items_needed": []}]))
        ov.mood()
        self.assertEqual(ov.mood_seen, {5: 3 * DAY})
        ov.load(resp([]))
        ov.mood()
        self.assertEqual(ov.mood_seen, {})   # a mood that ended frees its slot in the tracker

    def test_overseer_still_butchers_for_bones(self):
        ov, game = self.overseer(resp([{"unit_id": 6, "mood": "Fey", "skill": "BONECARVE",
                                        "claimed_building_id": 9, "waiting": True,
                                        "items_needed": [{"item": "BONE", "collected": 0}]}]))
        ov.mood()
        self.assertNotIn(("enable_automation", {"name": "autochop"}), game.calls)
        self.assertTrue(any(t == "build_workshop" and a.get("type") == "Butchers" for t, a in game.calls))


if __name__ == "__main__":
    unittest.main()
