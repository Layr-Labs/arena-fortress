"""cx alert cadence (owner 2026-11-10, zero deaths). (1) lock_door is the layer's: the model's call is refused
locally — with no door_id it locks every door and hatch, and entrance_hatches() never opens a lock it did not make.
(2) The layer-only stride shortens to one day while the alert is on or a hatch is locked by the layer (hint hard MY1-1
on 6adf843: wall-pace passes 7 days apart — alert_lock d163, next pass d170; a stale lock d155-162 and a thirst death
d163), and the chunked advance never runs whole while the alert stands. (3) The chunk look stops on a citizen
locked out of the Shelter, on the alert past its cap and on a fresh fight with a marked animal even when the fight
sign already stood (hint hard MY1-4 on 5d8cf68: d94 23/25 inside behind locked hatch 67 while the kea beat the
child, who died d95); a same-day tripwire stop with someone locked out still gets a layer pass. The observation
shapes follow the real /observe answers (burrows.list[].citizens_inside, doors.list[].locked,
administrators.citizens, recent_events strings). No game or network."""
import io
import json
import sys
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness as ov_harness  # noqa: E402
from plain import harness as plain  # noqa: E402

DAY = plain.DAY


def obs(day, alert=False, inside=25, citizens=25, doors=((67, False),), events=()):
    return {"day": day, "tick": day * DAY, "days_left": 216 - day, "game_over": False, "observation": {
        "date": {"abs_tick": day * DAY},
        "administrators": {"citizens": citizens},
        "burrows": {"civilian_alert": alert, "list": [
            {"id": 0, "name": "Shelter", "tiles": 300, "civ_alert_burrow": True, "citizens_inside": inside}]},
        "doors": {"door_items_free": 0, "hatch_cover_items_free": 0, "list": [
            {"id": i, "kind": "hatch", "x": 97, "y": 91, "z": 169, "built": True, "locked": lk} for i, lk in doors]},
        "dwarves": [{"id": 301, "name": "Morul", "profession": "Dwarven Child", "adult": False, "x": 117, "y": 99,
                     "z": 168}], "recent_events": list(events), "recent_cancellations": []}}


class LookGame:
    """advance_days pieces and a scripted look after each."""

    def __init__(self, looks, day=93):
        self.looks, self.day, self.actions, self.observed = list(looks), day, [], 0
        self.last = {"day": day, "tick": day * DAY, "days_left": 216 - day}

    def observe(self):
        self.observed += 1
        r = self.looks.pop(0) if self.looks else obs(self.day)
        self.day = r["day"]
        return r

    def act(self, name, args):
        self.actions.append((name, dict(args)))
        n = args.get("days", 1)
        self.day += n
        self.last = {"day": self.day, "tick": self.day * DAY, "days_left": 216 - self.day}
        return {**self.last, "ok": True, "result": {"advanced_days": n, "advanced_ticks": n * DAY, "stopped": None}}


class Guard:
    def __init__(self, risk=(), alert_locked=(), hatch_id=None, alert_since=None):
        self.risk, self.alert_locked, self.hatch_id, self.alert_since = list(risk), set(alert_locked), hatch_id, \
            alert_since

    def danger_signs(self, resp, query=True):
        return ["alert"] if resp["observation"]["burrows"]["civilian_alert"] else []

    def water_rising_stop(self):
        pass


def runner(game, guard, wall_s=None, base=None):
    r = plain.Plain.__new__(plain.Plain)
    r.game, r.guard, r.stats = game, guard, {}
    r.wall_s, r.t0, r.model_wait, r.day0 = wall_s, time.monotonic(), 0.0, 80
    r.guard_day = None
    r.last_look = base
    return r


class Quiet(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)


class LockDoorIsTheLayers(Quiet):
    def test_the_models_lock_door_is_refused_locally(self):
        game = LookGame([])
        r = runner(game, Guard())
        r.tool_names, r.messages, r.added, r.cancelled = {"lock_door", "advance_days"}, [], {}, []
        r.stats = {"actions": 0, "rejected": 0, "advances": 0, "churn_refused": 0}
        r.memory = SimpleNamespace(record=lambda *a, **k: None)
        for args in ({"locked": True}, {"locked": False, "door_id": 67}):
            r.run_call({"id": "1", "function": {"name": "lock_door", "arguments": json.dumps(args)}})
            out = json.loads(r.messages[-1]["content"])
            self.assertEqual(out["error_code"], "layer_owned")
            self.assertIn("lock_door", out["error"])
        self.assertEqual(game.actions, [])   # nothing reached the game
        self.assertIn("lock_door", plain.LAYER_TOOLS)
        self.assertIn("civilian_alert", plain.LAYER_TOOLS)


class LayerStride(Quiet):
    def test_the_wall_pace_stride_is_one_day_while_the_alert_stands(self):
        r = runner(LookGame([]), Guard())
        self.assertEqual(r.layer_days(obs(170, alert=False), pace=True), 7)
        self.assertEqual(r.layer_days(obs(170, alert=True), pace=True), 1)

    def test_an_alert_locked_hatch_keeps_one_day_with_the_alert_off(self):
        # the stale lock of bug (b): the alert off, the hatch still locked by the layer
        r = runner(LookGame([]), Guard(alert_locked={67}))
        self.assertEqual(r.layer_days(obs(160, alert=False, doors=((67, True),)), pace=True), 1)
        self.assertEqual(r.layer_days(obs(160, alert=False, doors=((67, False),)), pace=True), 7)   # opened

    def test_a_flood_lock_or_a_sign_takes_one_day_only_while_the_wall_fits(self):
        r = runner(LookGame([]), Guard(hatch_id=67), wall_s=10000)
        resp = obs(100, doors=((67, True),))   # 116 days left x 7 s = 812 s
        self.assertEqual(r.layer_days(resp, pace=True), 1)
        r.t0 = time.monotonic() - 9500        # 500 s left: 812 > 0.85 x 500
        self.assertEqual(r.layer_days(resp, pace=True), plain.HOT_FALLBACK_DAYS)
        r.guard = Guard(risk=["marked:kea"])
        self.assertEqual(r.layer_days(obs(100), pace=True), plain.HOT_FALLBACK_DAYS)
        r.t0 = time.monotonic()
        self.assertEqual(r.layer_days(obs(100), pace=True), 1)

    def test_the_alert_takes_one_day_even_on_a_tight_wall(self):
        r = runner(LookGame([]), Guard(), wall_s=1000)
        r.t0 = time.monotonic() - 990
        self.assertEqual(r.layer_days(obs(100, alert=True), pace=True), 1)

    def test_a_quiet_fort_keeps_its_strides(self):
        r = runner(LookGame([]), Guard())
        self.assertEqual(r.layer_days({"day": 20, "hands_off_in_days": None}, pace=True), 7)
        self.assertEqual(r.layer_days({"day": 20, "hands_off_in_days": 3}, pace=True), 1)

    def test_layer_only_on_the_pace_guard_steps_one_day_through_an_alert(self):
        looks = [obs(d, alert=d < 104) for d in range(100, 112)]
        game = LookGame(looks, day=100)
        game.observe = lambda: (lambda r: (setattr(game, "day", r["day"]), r)[1])(
            looks.pop(0) if looks else {**obs(game.day), "game_over": True})
        guard = Guard()
        guard.step = lambda resp: 0
        r = runner(game, guard)
        r.advance = lambda n, reason: (game.act("advance_days", {"days": n}), True)[1]
        r.layer_only("wall_pace")
        strides = [a["days"] for _, a in game.actions]
        self.assertEqual(strides[:4], [1, 1, 1, 1])   # days 100-103 under the alert
        self.assertEqual(strides[4], 7)              # day 104: the alert is off


class ChunkLook(Quiet):
    def test_a_citizen_locked_out_stops_the_advance(self):
        # hint hard MY1-4 on 5d8cf68: d93 25/25 inside, hatch 67 locked; d94 23/25 inside, still locked
        base = obs(93, alert=True, inside=25, doors=((67, True),))
        game = LookGame([obs(94, alert=True, inside=23, doors=((67, True),))])
        r = runner(game, Guard(risk=["alert"], alert_locked={67}, alert_since=86 * DAY), base=base)
        resp = r.chunked({"days": 7})
        self.assertEqual([a["days"] for _, a in game.actions], [1])
        self.assertEqual(resp["result"]["stopped"]["reason"], "danger_sign")
        self.assertIn("locked_out", resp["result"]["stopped"]["detail"])

    def test_a_flood_lock_with_the_alert_on_and_someone_out_stops_too(self):
        base = obs(295, alert=True, inside=14, citizens=14, doors=((65, True),))
        game = LookGame([obs(296, alert=True, inside=11, citizens=14, doors=((65, True),))])
        r = runner(game, Guard(risk=["alert"], hatch_id=65, alert_since=295 * DAY), base=base)
        resp = r.chunked({"days": 3})
        self.assertIn("locked_out", resp["result"]["stopped"]["detail"])

    def test_a_lock_out_that_already_stood_at_the_pass_does_not_stop_it_again(self):
        base = obs(296, alert=True, inside=11, citizens=14, doors=((65, True),))
        game = LookGame([obs(d, alert=True, inside=11, citizens=14, doors=((65, True),)) for d in (297, 298)])
        r = runner(game, Guard(risk=["alert"], hatch_id=65, alert_since=295 * DAY), base=base)
        resp = r.chunked({"days": 3})
        self.assertEqual([a["days"] for _, a in game.actions], [1, 1, 1])
        self.assertIsNone(resp["result"].get("stopped"))

    def test_the_alert_past_its_cap_stops_the_advance(self):
        base = obs(95, alert=True)
        game = LookGame([obs(96, alert=True), obs(97, alert=True)])
        r = runner(game, Guard(risk=["alert"], alert_since=86 * DAY), base=base)   # 9 days at the pass
        resp = r.chunked({"days": 7})
        self.assertEqual([a["days"] for _, a in game.actions], [1, 1])   # d97: 11 days > 10
        self.assertIn("alert_cap", resp["result"]["stopped"]["detail"])

    def test_the_alert_never_runs_a_multi_day_advance_whole(self):
        base = obs(100, alert=True)
        game = LookGame([obs(d, alert=True) for d in range(102, 115, 2)], day=100)
        r = runner(game, Guard(risk=["alert"], alert_since=99 * DAY), wall_s=1000, base=base)
        r.t0 = time.monotonic() - 800
        r.day0 = 90   # the wall ratio is past CHUNK_WALL_STOP: a quiet fort would run 7 days whole
        r.chunked({"days": 7})
        self.assertEqual([a["days"] for _, a in game.actions], [2, 2, 2, 1])
        q = LookGame([], day=100)
        r2 = runner(q, Guard(), wall_s=1000, base=obs(100))
        r2.t0, r2.day0 = time.monotonic() - 800, 90
        r2.chunked({"days": 7})
        self.assertEqual([a["days"] for _, a in q.actions], [7])


KEA_BITE = "The kea bites the dwarven child in the head, denting the fat and bruising the muscle!"
KEA_SNATCH = "The kea snatches at the dwarven child in the head with his first toe, right foot, tearing the fat!"


class FreshFight(Quiet):
    def guard(self):
        ov = ov_harness.Overseer(SimpleNamespace(act=lambda *a: {"ok": True},
                                                 query=lambda *a, **k: {"result": {"units": []}}), days=216)
        ov.risk = ["alert", "fight:kea"]   # the fight sign already stood at the layer's pass
        ov.alert_since = 93 * DAY
        return ov

    def test_a_new_combat_report_stops_it_although_the_species_sign_stood(self):
        base = obs(93, alert=True, events=[KEA_BITE])
        game = LookGame([obs(94, alert=True, events=[KEA_BITE]), obs(95, alert=True, events=[KEA_BITE, KEA_SNATCH])])
        r = runner(game, self.guard(), base=base)
        resp = r.chunked({"days": 7})
        self.assertEqual([a["days"] for _, a in game.actions], [1, 1])   # d94 old text only: goes on
        self.assertIn("fresh_fight:kea", resp["result"]["stopped"]["detail"])

    def test_an_unmarked_species_fight_does_not_stop_it(self):
        base = obs(93, alert=True)
        game = LookGame([obs(94, alert=True, events=["The hunter bites the deer in the leg!"])])
        r = runner(game, self.guard(), base=base)
        r.guard.marked.pop("deer", None)
        resp = r.chunked({"days": 2})
        self.assertNotIn("fresh_fight:deer", str(resp["result"].get("stopped")))


class SameDayRelook(Quiet):
    def test_a_same_day_stop_with_someone_locked_out_gets_one_more_layer_pass(self):
        r = runner(LookGame([]), Guard(alert_locked={67}))
        r.guard_day = 140
        locked_out = obs(140, alert=True, inside=23, citizens=24, doors=((67, True),))
        self.assertTrue(r.layer_due(locked_out))      # migrants at the map edge, hatch 67 shut
        self.assertFalse(r.layer_due(locked_out))     # once a day: a lock the layer keeps is not re-asked
        self.assertFalse(r.layer_due(obs(140, alert=True, inside=24, citizens=24, doors=((67, True),))))
        self.assertTrue(r.layer_due(obs(141, alert=True)))   # a new day as before


if __name__ == "__main__":
    unittest.main()
