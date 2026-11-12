"""cx lockable chunk look (std OP1-4 on 014f7eb, wellbeing 0.90): the alert sounded on d292 for a buzzard flock, the
model's advance_days(7) ran as one-day pieces, and the d294 look showed 19/19 citizens inside the Shelter with both
hatches (6 at 97,99,160 and 61 at 93,99,160 — the Shelter's own stairs, every Shelter tile subterranean) unlocked.
Nothing stopped the advance: a buzzard was in the Shelter at (95,99,159) on d295, 16 citizens fled to the surface and
the cook fought it, and the lock came only with the d296 layer pass. Two citizens at stress cat 2 went to cat 1 on
d295/d296 and stayed there through F (stressed share 0.105 > 0.10). The same open window stood on good runs too
(c44c96b d209-215 and d308-314, 0c8ca4b d218/d232) with no animal coming down. The look now stops on "lockable" —
alert on, everyone inside, an entrance hatch open — so the layer's all-in lock runs at once. No game or network."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from plain import harness as plain  # noqa: E402
from test_alert_cadence import LookGame, runner  # noqa: E402
from test_shelter_hatches import FakeGame, fort, overseer  # noqa: E402

DAY = plain.DAY
SURF = 160
E1 = {"id": "E1", "kind": "E", "x": 97, "y": 99, "z": SURF}
E2 = {"id": "E2", "kind": "E", "x": 93, "y": 99, "z": SURF}


def look(day, inside, alert=True, citizens=19, locked=(False, False), extra=()):
    hatches = [{"id": 6, "kind": "hatch", "x": 97, "y": 99, "z": SURF, "built": True, "locked": locked[0]},
               {"id": 61, "kind": "hatch", "x": 93, "y": 99, "z": SURF, "built": True, "locked": locked[1]}]
    return {"day": day, "tick": day * DAY, "days_left": 336 - day, "game_over": False, "observation": {
        "date": {"abs_tick": day * DAY},
        "administrators": {"citizens": citizens},
        "burrows": {"civilian_alert": alert, "list": [
            {"id": 0, "name": "Shelter", "tiles": 100, "civ_alert_burrow": True, "citizens_inside": inside}]},
        "doors": {"door_items_free": 0, "hatch_cover_items_free": 0, "list": hatches + list(extra)},
        "dwarves": [], "recent_events": [], "recent_cancellations": []}}


class Guard:
    def __init__(self, entrances=None, alert_locked=(), hatch_id=None):
        self.risk, self.alert_locked, self.hatch_id, self.alert_since = ["alert"], set(alert_locked), hatch_id, 292 * DAY
        if entrances is not None:
            self.entrances = entrances

    def danger_signs(self, resp, query=True):
        return ["alert"] if resp["observation"]["burrows"]["civilian_alert"] else []

    def water_rising_stop(self):
        pass


ENTS = {"E1": (97, 99, SURF), "E2": (93, 99, SURF)}


class Quiet(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)


class LockableStop(Quiet):
    def test_the_014f7eb_d292_advance_stops_on_d294_when_everyone_is_inside(self):
        base = look(292, inside=9)
        game = LookGame([look(293, inside=17), look(294, inside=19), look(295, inside=2)], day=292)
        r = runner(game, Guard(ENTS), base=base)
        resp = r.chunked({"days": 7})
        self.assertEqual([a["days"] for _, a in game.actions], [1, 1])   # d292->293, d293->294, stop
        self.assertEqual(resp["result"]["stopped"]["reason"], "danger_sign")
        self.assertIn("lockable", resp["result"]["stopped"]["detail"])

    def test_the_old_look_ran_on_into_d295(self):
        # the same looks with the hatches already locked: no stop until the model's days are spent
        base = look(292, inside=9, locked=(True, True))
        game = LookGame([look(d, inside=19, locked=(True, True)) for d in range(293, 300)], day=292)
        r = runner(game, Guard(ENTS), base=base)
        resp = r.chunked({"days": 3})
        self.assertEqual([a["days"] for _, a in game.actions], [1, 1, 1])
        self.assertIsNone(resp["result"].get("stopped"))

    def test_someone_outside_or_no_alert_is_not_lockable(self):
        r = runner(LookGame([]), Guard(ENTS))
        self.assertNotIn("lockable", r.lock_signs(look(294, inside=18)))
        self.assertNotIn("lockable", r.lock_signs(look(294, inside=19, alert=False)))
        self.assertIn("lockable", r.lock_signs(look(294, inside=19, locked=(True, False))))
        self.assertNotIn("lockable", r.lock_signs(look(294, inside=19, locked=(True, True))))

    def test_only_hatches_over_listed_entrances_count_and_never_the_floods(self):
        r = runner(LookGame([]), Guard({"E1": (97, 99, SURF)}))
        # hatch 61 is not over a listed entrance, hatch 6 is locked: nothing for the layer to lock
        self.assertNotIn("lockable", r.lock_signs(look(294, inside=19, locked=(True, False))))
        r = runner(LookGame([]), Guard(ENTS, hatch_id=61))
        self.assertNotIn("lockable", r.lock_signs(look(294, inside=19, locked=(True, False))))
        r = runner(LookGame([]), Guard())   # a layer without an entrance list: any open hatch counts
        self.assertIn("lockable", r.lock_signs(look(294, inside=19, locked=(True, False))))
        unbuilt = {"id": 70, "kind": "hatch", "x": 97, "y": 99, "z": SURF, "built": False, "locked": False}
        self.assertNotIn("lockable", runner(LookGame([]), Guard(ENTS)).lock_signs(
            look(294, inside=19, locked=(True, True), extra=[unbuilt])))

    def test_a_lockable_window_that_stood_at_the_pass_does_not_stop_again(self):
        # the layer saw it and did not lock (a lock_skip): the model's days run as before
        base = look(294, inside=19)
        game = LookGame([look(d, inside=19) for d in (295, 296, 297)], day=294)
        r = runner(game, Guard(ENTS), base=base)
        resp = r.chunked({"days": 3})
        self.assertEqual([a["days"] for _, a in game.actions], [1, 1, 1])
        self.assertIsNone(resp["result"].get("stopped"))

    def test_a_same_day_lockable_look_gets_one_more_layer_pass(self):
        r = runner(LookGame([]), Guard(ENTS))
        r.guard_day = 294
        resp = look(294, inside=19)
        self.assertTrue(r.layer_due(resp))
        self.assertFalse(r.layer_due(resp))   # once a day
        self.assertFalse(r.layer_due(look(294, inside=19, locked=(True, True))))


class TheLayerLocksOnThatLook(Quiet):
    def test_the_overseer_locks_both_hatches_on_the_stopped_look(self):
        game = FakeGame()
        ov = overseer(game)
        doors = {"door_items_free": 0, "hatch_cover_items_free": 0, "list": [
            {"id": 6, "kind": "hatch", "x": 97, "y": 99, "z": SURF, "built": True, "locked": False},
            {"id": 61, "kind": "hatch", "x": 93, "y": 99, "z": SURF, "built": True, "locked": False}]}
        resp = fort(294, sites=[E1, E2], alert=True, inside=19, citizens=19, doors=doors)
        resp["observation"]["map"]["surface_z"] = SURF
        for p in resp["observation"]["dwarves"]:
            p.update(x=95, y=99, z=SURF - 1)
        ov.load(resp)
        ov.entrance_hatches()
        self.assertEqual(sorted(a["door_id"] for a in game.tools("lock_door")), [6, 61])
        # and the plain look reads the overseer's own entrance list
        r = runner(LookGame([]), ov)
        self.assertEqual(set(ov.entrances.values()), set(ENTS.values()))
        self.assertIn("lockable", r.lock_signs(look(294, inside=19)))


if __name__ == "__main__":
    unittest.main()
