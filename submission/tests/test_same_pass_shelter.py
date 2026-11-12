"""cx same-pass Shelter (hint hard OP1-3 on 6c42bb2): the expedition leader died of INFECTION on d78 after a rhesus
macaque beating at the wagon on d0.9-2.2. The d1.33 pass made the first Shelter burrow (A1) but read the
alert gates off the observation from before it, so the alert waited a day; and day 0 ran one 2-day piece with no look."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from overseer import harness  # noqa: E402
from tests.test_danger_marks import (FakeGame, Quiet, fort, ChunkGame, FakeGuard,  # noqa: E402
                                     plain_runner)

MACAQUE = {"id": 109, "race": "MACAQUE_RHESUS", "hostile": False, "x": 152, "y": 42, "z": 169}


def shelterless(day):
    resp = fort(day)
    resp["observation"]["burrows"] = {"civilian_alert": False, "list": []}
    return resp


class SamePassAlert(Quiet):
    def look(self, ov, game, resp):
        ov.load(resp)
        ov.count = 0
        game.calls.clear()
        ov.defend()
        ov.wildlife_response()
        ov.mark_guard()
        return [(t, a) for t, a in game.calls if t == "civilian_alert"]

    def test_no_burrow_yet_sounds_nothing(self):
        game = FakeGame([MACAQUE])
        ov = harness.Overseer(game, days=336)
        self.assertEqual(self.look(ov, game, shelterless(1)), [])

    def test_a_burrow_made_this_pass_lets_the_alert_sound(self):
        game = FakeGame([MACAQUE])
        ov = harness.Overseer(game, days=336)
        ov.load(shelterless(1))
        ov.count = 0
        r = ov.act("shelter_test", "create_burrow", {"x": 95, "y": 95, "z": 168})
        self.assertTrue(r and r.get("ok"))
        self.assertTrue(ov.shelter_made)
        self.assertEqual(self.look(ov, game, shelterless(1)), [("civilian_alert", {"on": True})])

    def test_a_refused_create_burrow_is_no_shelter(self):
        game = FakeGame([MACAQUE])
        game.act = lambda tool, args: {"ok": False, "error_code": "nothing_designated"}
        ov = harness.Overseer(game, days=336)
        ov.load(shelterless(1))
        ov.count = 0
        ov.act("shelter_test", "create_burrow", {"x": 95, "y": 95, "z": 168})
        self.assertFalse(ov.shelter_made)
        self.assertFalse(ov.shelter_listed({"list": []}))

    def test_the_listed_burrow_still_counts(self):
        ov = harness.Overseer(FakeGame(), days=336)
        self.assertTrue(ov.shelter_listed({"list": [{"id": 0, "civ_alert_burrow": True}]}))
        self.assertFalse(ov.shelter_listed({"list": [{"id": 0, "civ_alert_burrow": False}]}))


class ShelterlessChunks(Quiet):
    def runner(self, guard, burrows):
        game = ChunkGame()
        r = plain_runner(game, guard)
        obs = {"date": {"abs_tick": 100 * 1200}}
        if burrows is not None:
            obs["burrows"] = burrows
        r.last_look = {"day": 100, "observation": obs}
        return game, r

    def test_no_shelter_runs_one_day_pieces(self):
        game, r = self.runner(FakeGuard(), {"civilian_alert": False, "list": []})
        r.chunked({"days": 3})
        self.assertEqual([a["days"] for _, a in game.actions][0], 1)

    def test_a_shelter_runs_two_day_pieces(self):
        game, r = self.runner(FakeGuard(), {"civilian_alert": False, "list": [{"id": 0, "civ_alert_burrow": True}]})
        r.chunked({"days": 4})
        self.assertEqual([a["days"] for _, a in game.actions], [2, 2])

    def test_a_shelter_made_by_the_layer_runs_two_day_pieces(self):
        guard = FakeGuard()
        guard.shelter_made = True
        game, r = self.runner(guard, {"civilian_alert": False, "list": []})
        r.chunked({"days": 4})
        self.assertEqual([a["days"] for _, a in game.actions], [2, 2])

    def test_an_observation_without_burrows_is_unchanged(self):
        game, r = self.runner(FakeGuard(), None)
        r.chunked({"days": 4})
        self.assertEqual([a["days"] for _, a in game.actions], [2, 2])

    def test_a_fight_seen_at_the_first_day_stops_the_advance(self):
        game, r = self.runner(FakeGuard([["fight:rhesus macaque"]]), {"civilian_alert": False, "list": []})
        resp = r.chunked({"days": 3})
        self.assertEqual([a["days"] for _, a in game.actions], [1])
        self.assertEqual(resp["result"]["stopped"]["reason"], "danger_sign")


if __name__ == "__main__":
    unittest.main()
