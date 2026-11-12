"""cx STRANDED HOME (owner 2026-11-11: bring the stranded back). The MY1-3 river froze between days 80 and 87 in probe
p13d (z144 channel -> ice floor); the records' trio walked in 0-10 days later by chance. Now, while anyone is stranded,
the survey runs every STRANDED_JOIN_DAYS, and the day a stranded citizen's region holds a fort tile they leave the
stranded set and the civilian alert calls them to the Shelter, held by defend() until they are in (at most
STRANDED_HOME_DAYS). Real maps: day 0 (open river) and day 87 (frozen) of probe p13d. No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from river_maps import answers as river_answers  # noqa: E402
from test_danger_marks import Quiet  # noqa: E402
from test_stranded import BOWYER, FURNACE, LEADER, MINER, FISHER, SURFACE, my1_3  # noqa: E402
from overseer import harness  # noqa: E402


class SeasonGame:
    """The real map of probe p13d on `day` (0: open river, 87: frozen) for /query/map."""
    def __init__(self, day=0):
        self.day, self.calls, self.maps = day, [], 0

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {}}

    def query(self, name, **kw):
        if name == "map":
            self.maps += 1
            return {"result": river_answers(kw["x"], kw["y"], kw["radius"], kw["z"], kw["z2"], day=self.day)}
        return {"result": {"units": []}}


TRIO = [LEADER, BOWYER, FURNACE]


class Home(Quiet):
    def stranded_ov(self, game):
        ov = harness.Overseer(game, days=216)
        ov.count = 0
        ov.load(my1_3(0, TRIO + [MINER, FISHER]))
        ov.stranded_survey()
        self.assertEqual(ov.stranded, {84, 212, 213})
        return ov

    def alerts(self, game):
        return [a for t, a in game.calls if t == "civilian_alert"]

    def test_the_cache_does_not_hide_the_ice(self):
        game = SeasonGame(0)
        ov = self.stranded_ov(game)
        # the trio stands on tiles the day-0 survey placed: before, no survey ever ran again
        ov.load(my1_3(2, TRIO + [MINER]))
        ov.stranded_survey()
        self.assertEqual(game.maps, 50)                      # STRANDED_JOIN_DAYS while anyone is stranded
        self.assertEqual(ov.stranded, {84, 212, 213})        # still open water: still stranded
        self.assertIsNone(ov.home_call)
        ov.load(my1_3(3, TRIO + [MINER]))
        ov.stranded_survey()
        self.assertEqual(game.maps, 50)

    def test_the_frozen_river_calls_them_home(self):
        game = SeasonGame(0)
        ov = self.stranded_ov(game)
        game.day = 87
        ov.load(my1_3(87, TRIO + [MINER]))
        game.calls.clear()
        ov.stranded_survey()
        self.assertEqual(ov.stranded, set())                 # squads and rescue count them again
        self.assertEqual(ov.home_call["ids"], {84, 212, 213})
        ov.home_call_alert()
        self.assertEqual(self.alerts(game), [{"on": True}])
        # defend() holds the alert while they are still out there
        ov.load(my1_3(88, TRIO + [MINER], alert=True))
        game.calls.clear()
        ov.defend()
        self.assertNotIn({"on": False}, self.alerts(game))
        # in the Shelter (or by home): the call ends, the alert is lifted as before
        home = [dict(c, x=100, y=101, z=142) for c in TRIO]
        ov.load(my1_3(89, home + [MINER], alert=True))
        game.calls.clear()
        ov.defend()
        self.assertIsNone(ov.home_call)
        self.assertIn({"on": False}, self.alerts(game))

    def test_the_call_holds_at_most_its_days(self):
        game = SeasonGame(87)
        ov = harness.Overseer(game, days=216)
        ov.count = 0
        ov.load(my1_3(87, TRIO + [MINER], alert=True))
        ov.home_call = {"ids": {213}, "since": 87 * harness.DAY}
        self.assertTrue(ov.home_holding())
        ov.load(my1_3(87 + harness.STRANDED_HOME_DAYS + 1, TRIO + [MINER], alert=True))
        self.assertFalse(ov.home_holding())
        self.assertIsNone(ov.home_call)

    def test_no_sound_under_an_alert_already_on_or_the_safe_state(self):
        game = SeasonGame(87)
        ov = harness.Overseer(game, days=216)
        ov.count = 0
        ov.load(my1_3(87, TRIO + [MINER], alert=True))
        ov.home_call = {"ids": {213}, "since": 87 * harness.DAY}
        ov.home_call_alert()
        self.assertEqual(self.alerts(game), [])
        ov.load(my1_3(87, TRIO + [MINER]))
        ov.safe_held = True
        ov.home_call_alert()
        self.assertEqual(self.alerts(game), [])

    def test_an_unread_tile_is_no_join(self):
        # a stranded citizen whose survey reading says nothing (lost map) is never called home on a guess
        class Blank(SeasonGame):
            def query(self, name, **kw):
                if name == "map" and self.day == 87:
                    self.maps += 1
                    return {"result": {"x1": 0, "y1": 0, "x2": 0, "y2": 0, "levels": [], "liquid": []}}
                return SeasonGame.query(self, name, **kw)
        game = Blank(0)
        ov = self.stranded_ov(game)
        game.day = 87
        ov.load(my1_3(87, TRIO + [MINER]))
        ov.stranded_survey()
        self.assertIsNone(ov.home_call)


if __name__ == "__main__":
    unittest.main()
