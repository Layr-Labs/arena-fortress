"""cx STRANDED ALERT SKIP (owner decision 2026-11-11, option (a)): no mark alert when the marked animals are within range of
stranded citizens only (no reachable citizen or the wagon within STRANDED_ALERT_TILES). Replays of the seven pre-freeze
MY1-3 alerts raised while someone was stranded (tests/strand_alert_cases.py): only d57f599 day 62 (pre-emptive, six
gray langurs on the north bank, 213 at the fight's tile) is skipped; d57f599 day 79, cx838106a day 74 and the four
fort-side kea alerts still sound. No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from strand_alert_cases import CASES  # noqa: E402
from test_danger_marks import Quiet, fort  # noqa: E402
from overseer import harness  # noqa: E402


class UnitsGame:
    def __init__(self, units):
        self.calls, self.units = [], list(units)

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {}}

    def query(self, name, **kw):
        return {"result": {"units": [dict(u) for u in self.units]}}


def case(rec, day):
    return next(c for c in CASES if c["rec"].startswith(rec) and c["day"] == day)


def replay(c, alert=False, hostiles=0):
    r = fort(c["day"], alert=alert, dwarves=c["dwarves"], hostiles=hostiles)
    o = r["observation"]
    o["map"]["wagon"] = dict(c["wagon"])
    o["map"]["surface_z"] = c["surface_z"]
    o["administrators"]["citizens"] = len(c["dwarves"])
    o["burrows"]["list"] = [{"id": 0, "civ_alert_burrow": True, "name": "Shelter",
                             "citizens_inside": sum(1 for x in c["dwarves"] if x["z"] < c["surface_z"])}]
    return r


class Skip(Quiet):
    def sound(self, c, stranded, **kw):
        game = UnitsGame(c["others"])
        ov = harness.Overseer(game, days=216)
        ov.count = 0
        ov.stranded = set(stranded)
        ov.load(replay(c, **kw))
        ov.mark_guard()
        return [a for t, a in game.calls if t == "civilian_alert"], ov

    def test_d57_day62_is_skipped(self):
        c = case("cxd57f599", 62)
        self.assertEqual(sorted(c["stranded"]), [84, 212, 213])
        calls, ov = self.sound(c, c["stranded"])
        self.assertEqual(calls, [])
        self.assertIn("gray langur", ov.strand_skipped)
        # the same look without the stranded set: the pre-emptive alert sounds as before
        calls, _ = self.sound(c, [])
        self.assertEqual(calls, [{"on": True}])

    def test_the_other_six_still_sound(self):
        for rec, day in (("cxd57f599", 79), ("cx838106a", 74), ("cx0b49063", 77), ("cx7c43df4", 52),
                         ("cxe33d381", 55), ("cxe33d381", 72)):
            c = case(rec, day)
            with self.subTest(rec=rec, day=day):
                game = UnitsGame(c["others"])
                ov = harness.Overseer(game, days=216)
                ov.stranded = set(c["stranded"])
                ov.load(replay(c))
                units = ov.marked_units(harness.MARK_RANGE, harness.MARK_RANGE_Z)
                self.assertTrue(units)
                self.assertFalse(ov.stranded_only(units))

    def test_skip_needs_a_stranded_citizen_in_range(self):
        c = case("cxd57f599", 62)
        game = UnitsGame(c["others"])
        ov = harness.Overseer(game, days=216)
        ov.load(replay(c))
        units = ov.marked_units(harness.MARK_RANGE, harness.MARK_RANGE_Z)
        self.assertFalse(ov.stranded_only(units))          # nobody stranded: never
        ov.stranded = set(c["stranded"])
        self.assertTrue(ov.stranded_only(units))
        far = [dict(u, x=190, y=190) for u in units]
        self.assertFalse(ov.stranded_only(far))           # no stranded citizen near them either: nothing to skip

    def test_never_for_a_game_hostile(self):
        c = case("cxd57f599", 62)
        game = UnitsGame(c["others"])
        ov = harness.Overseer(game, days=216)
        ov.stranded = set(c["stranded"])
        ov.load(replay(c))
        units = ov.marked_units(harness.MARK_RANGE, harness.MARK_RANGE_Z)
        self.assertFalse(ov.stranded_only([dict(units[0], hostile=True)] + units[1:]))
        ov.load(replay(c, hostiles=1))
        self.assertFalse(ov.stranded_only(units))

    def test_sounds_the_moment_a_reachable_citizen_comes_in_range(self):
        c = case("cxd57f599", 62)
        calls, ov = self.sound(c, c["stranded"])
        self.assertEqual(calls, [])
        # two days on (past PREEMPT_WINDOW_DAYS from the arrival), the troop near a fort citizen walking north
        later = dict(c, day=c["day"] + 2)
        later["dwarves"] = [dict(x) for x in c["dwarves"]]
        langur = next(u for u in c["others"] if "LANGUR" in str(u["race"]))
        walker = next(x for x in later["dwarves"] if x["id"] not in c["stranded"])
        walker.update(x=langur["x"], y=min(191, langur["y"] + 40), z=c["surface_z"])
        game = ov.game
        game.calls.clear()
        ov.load(replay(later))
        ov.count = 0
        ov.mark_guard()
        self.assertEqual([a for t, a in game.calls if t == "civilian_alert"], [{"on": True}])


if __name__ == "__main__":
    unittest.main()
