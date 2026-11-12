"""cx squad hold (owner 2026-11-11): squad_order is layer-owned. On the hint runs the model's squad_order stand_down
came 0-3 days after the layer's own station (guard_muster on 11 runs, mark_rescue / mark_station on 4; c44c96b hard
OP1-3: musters on days 217 and 259, stood down on days 220/222 and 260/264, armed 4 -> 1 -> 0) while the layer kept
its muster set and never looked again. Now (1) the plain loop refuses the model's squad_order locally and leaves it
out of the tool list, (2) the layer re-sends a station or attack it owns when the squad shows no order while the need
stands (squad_hold), and stands down / drops the record when the need ends, (3) the prompt no longer tells the model
to order the squad. No game or network."""
import inspect
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness  # noqa: E402
from plain import harness as plain  # noqa: E402
from plain import prompt  # noqa: E402

import test_guard_equip as ge  # noqa: E402  (the MY1-4 fort fixture and its fake game)

SURFACE = ge.SURFACE
STAND_DOWN = ("squad_order", {"order": "stand_down"})
GOB = [{"id": 900, "race": "GOBLIN", "invader": True, "x": 60, "y": 98, "z": SURFACE}]


def armed_squad(orders=()):
    return dict(ge.my14_squad(), orders=[dict(o) for o in orders], armed=4,
                members=[ge.member(i, "(copper battle axe)", True) for i in (238, 99, 241, 95)])


class Base(ge.Base):
    def guard_pass(self, ov, game, day, **kw):
        """The plan()'s squad steps in their order: defend, mark_guard, squad_hold."""
        self.at(ov, game, day, **kw)
        ov.defend()
        ov.mark_guard()
        ov.squad_hold()
        return [c for c in game.calls if c[0] == "squad_order"]

    def at(self, ov, game, day, **kw):
        ov.load(ge.fort(day, **kw))
        ov.count = 0
        game.calls.clear()


class PlainRefuses(Base):
    class Game:
        def __init__(self):
            self.actions, self.last = [], {"day": 5, "tick": 5 * plain.DAY}

        def act(self, tool, args):
            self.actions.append((tool, args))
            return {"ok": True}

        def __getattr__(self, name):
            return lambda *a, **k: {"ok": True}

    def runner(self, game):
        r = plain.Plain.__new__(plain.Plain)
        r.game = game
        r.tool_names = {"advance_days"}   # squad_order is no longer offered
        r.messages, r.added, r.cancelled = [], {}, []
        r.stats = {"actions": 0, "rejected": 0, "advances": 0, "churn_refused": 0}
        r.memory = SimpleNamespace(record=lambda *a, **k: None)
        r.tick = lambda: 220 * plain.DAY
        r.guard = SimpleNamespace(owned=set(), water_rising_stop=lambda: None)
        return r

    def test_the_models_squad_orders_never_reach_the_game(self):
        game = self.Game()
        r = self.runner(game)
        for args in ({"order": "stand_down"}, {"order": "attack"}, {"order": "attack", "target_ids": [9]},
                     {"order": "station", "x": 1, "y": 2, "z": 3}):
            r.run_call({"id": "1", "function": {"name": "squad_order", "arguments": json.dumps(args)}})
            out = json.loads(r.messages[-1]["content"])
            self.assertFalse(out["ok"])
            self.assertEqual(out["error_code"], "layer_owned")
            self.assertIn("squad_order", out["error"])
            self.assertIn("drop their weapons", out["error"])
        self.assertEqual(game.actions, [])
        self.assertEqual(r.stats["churn_refused"], 4)
        self.assertIn("squad_order", plain.LAYER_TOOLS)
        self.assertIn("squad_order", plain.LAYER_REFUSAL)

    def test_squad_order_is_not_offered(self):
        tools = [{"type": "function", "function": {"name": n, "parameters": {}}}
                 for n in ("squad_order", "create_squad", "build_door", "advance_days")]
        self.assertEqual([t["function"]["name"] for t in plain.prepare_tools(tools)], ["build_door", "advance_days"])

    def test_the_prompt_no_longer_points_at_squad_order(self):
        s = prompt.system_prompt(tool_names=["add_manager_order"])
        self.assertNotIn("squad_order", s)
        self.assertIn("Squad orders (attack, station, stand_down) are handled for you.", s)


class MusterHeld(Base):
    """c44c96b hard OP1-3: the muster's station cancelled by someone else while the wildlife need stands."""

    def muster(self):
        ov, game = self.ov()
        ov.wild_alert_since = 18 * harness.DAY
        calls = self.guard_pass(ov, game, 20, squads=[ge.my14_squad()], weapons_free=0, alert=True)
        order = next(a for t, a in calls if t == "squad_order" and a.get("order") == "station")
        self.assertEqual(ov.squad_post, ("guard_muster", order))
        return ov, game, order

    def test_a_cancelled_muster_is_stationed_again_while_the_need_stands(self):
        ov, game, order = self.muster()
        ov.wild_alert_since = 18 * harness.DAY
        calls = self.guard_pass(ov, game, 21, squads=[ge.my14_squad()], weapons_free=0, alert=True)
        self.assertEqual(calls, [("squad_order", order)])
        rec = self.logs("squad_reassert")[-1]
        self.assertEqual((rec["owner"], rec["order"], rec["ok"]), ("guard_muster", "station", True))
        self.assertIsNotNone(ov.muster)
        self.assertEqual(ov.squad_post, ("guard_muster", order))   # the owner stays the muster
        # the cached observation reads the order again (entrance_hatches reads it in the same pass)
        self.assertTrue(ov.o["military"]["squads"][0]["orders"])

    def test_the_re_send_is_rate_limited_within_a_day(self):
        ov, game, order = self.muster()
        ov.wild_alert_since = 18 * harness.DAY
        self.guard_pass(ov, game, 21, squads=[ge.my14_squad()], weapons_free=0, alert=True)
        ov.wild_alert_since = 18 * harness.DAY
        calls = self.guard_pass(ov, game, 21.1, squads=[ge.my14_squad()], weapons_free=0, alert=True)
        self.assertEqual(calls, [])
        ov.wild_alert_since = 18 * harness.DAY
        calls = self.guard_pass(ov, game, 21.3, squads=[ge.my14_squad()], weapons_free=0, alert=True)
        self.assertEqual(calls, [("squad_order", order)])

    def test_no_re_send_while_the_order_stands(self):
        ov, game, order = self.muster()
        ov.wild_alert_since = 18 * harness.DAY
        calls = self.guard_pass(ov, game, 21, squads=[dict(ge.my14_squad(), orders=[dict(order)])], weapons_free=0,
                                alert=True)
        self.assertEqual(calls, [])

    def test_the_need_gone_stands_down_and_drops_the_record(self):
        ov, game, order = self.muster()
        ov.wild_alert_since = None
        calls = self.guard_pass(ov, game, 25, squads=[ge.my14_squad()], weapons_free=0)
        self.assertEqual(calls, [STAND_DOWN])   # guard_muster's own stand_down, no re-send
        self.assertIsNone(ov.muster)
        self.assertIsNone(ov.squad_post)
        self.assertFalse(self.logs("squad_reassert"))


class MarkHeld(Base):
    def test_a_cancelled_mark_station_is_stationed_again_until_mark_guard_ends_it(self):
        ov, game = self.ov()
        self.at(ov, game, 60, squads=[armed_squad()], weapons_free=0)
        st = {"order": "station", "x": 117, "y": 99, "z": SURFACE}
        self.assertTrue(ov.act("mark_rescue", "squad_order", st, retry=0.25)["ok"])
        ov.mark_station = ov.now
        self.assertEqual(ov.squad_post, ("mark_rescue", st))
        self.at(ov, game, 61, squads=[armed_squad()], weapons_free=0)
        ov.squad_hold()
        self.assertEqual(game.calls, [("squad_order", st)])
        # mark_guard's stand_down (no marked animal within MARK_RANGE) ends the station and the record
        self.at(ov, game, 62, squads=[armed_squad([st])], weapons_free=0)
        ov.mark_guard()
        ov.squad_hold()
        self.assertEqual(game.calls, [STAND_DOWN])
        self.assertIsNone(ov.mark_station)
        self.assertIsNone(ov.squad_post)

    def test_a_record_whose_owner_cleared_its_state_is_dropped(self):
        ov, game = self.ov()
        self.at(ov, game, 60, squads=[armed_squad()], weapons_free=0)
        ov.act("mark_station", "squad_order", {"order": "station", "x": 1, "y": 2, "z": SURFACE})
        ov.mark_station = None   # e.g. the invader window's guard or an attack replaced it, then ended
        self.at(ov, game, 61, squads=[armed_squad()], weapons_free=0)
        ov.squad_hold()
        self.assertEqual(game.calls, [])
        self.assertIsNone(ov.squad_post)


class InvaderGuardHeld(Base):
    def setup_guard(self):
        ov, game = self.ov()
        self.at(ov, game, 30, squads=[armed_squad()], weapons_free=0, hostiles=GOB, alert=True)
        st = {"order": "station", "x": 104, "y": 98, "z": SURFACE}
        ov.act("invader_guard", "squad_order", st, retry=0.25, limit=10 ** 6)
        ov.invader_guard = (104, 98, SURFACE)
        ov.invader_window = ov.now + 3 * harness.DAY
        return ov, game, st

    def test_re_sent_while_the_window_and_the_invaders_stand(self):
        ov, game, st = self.setup_guard()
        self.at(ov, game, 31, squads=[armed_squad()], weapons_free=0, hostiles=GOB, alert=True)
        ov.squad_hold()
        self.assertEqual(game.calls, [("squad_order", st)])

    def test_window_over_clears_the_guard_without_an_order(self):
        ov, game, st = self.setup_guard()
        self.at(ov, game, 34, squads=[armed_squad()], weapons_free=0, hostiles=GOB, alert=True)
        ov.squad_hold()
        self.assertEqual(game.calls, [])
        self.assertIsNone(ov.invader_guard)
        self.assertIsNone(ov.squad_post)


class AttackHeld(Base):
    def test_a_cancelled_attack_goes_again_while_the_odds_hold(self):
        ov, game = self.ov()
        calls = self.guard_pass(ov, game, 30, squads=[armed_squad()], weapons_free=0, hostiles=GOB, alert=True)
        self.assertIn(("squad_order", {"order": "attack"}), calls)
        self.assertEqual(ov.squad_post, ("attack", {"order": "attack"}))
        # someone stood it down the same day: defend's own attack waits a day (retry 1), squad_hold does not
        calls = self.guard_pass(ov, game, 30.3, squads=[armed_squad()], weapons_free=0, hostiles=GOB, alert=True)
        self.assertEqual(calls, [("squad_order", {"order": "attack"})])
        self.assertEqual(self.logs("squad_reassert")[-1]["owner"], "attack")

    def test_no_re_send_once_the_hostiles_are_gone(self):
        ov, game = self.ov()
        self.guard_pass(ov, game, 30, squads=[armed_squad()], weapons_free=0, hostiles=GOB, alert=True)
        self.at(ov, game, 30.3, squads=[armed_squad()], weapons_free=0)
        ov.squad_hold()
        self.assertEqual(game.calls, [])
        self.assertIsNone(ov.squad_post)

    def test_a_wild_kill_list_keeps_only_targets_in_sight(self):
        ov, game = self.ov()
        self.at(ov, game, 30, squads=[armed_squad()], weapons_free=0)
        ov.act("wild_attack", "squad_order", {"order": "attack", "target_ids": [700, 701]})
        langur = [{"id": 701, "race": "GRAY_LANGUR", "x": 90, "y": 98, "z": SURFACE}]
        self.at(ov, game, 31, squads=[armed_squad()], weapons_free=0, hostiles=langur)
        ov.squad_hold()
        self.assertEqual(game.calls, [("squad_order", {"order": "attack", "target_ids": [701]})])
        self.at(ov, game, 32, squads=[armed_squad()], weapons_free=0)
        ov.squad_hold()
        self.assertEqual(game.calls, [])
        self.assertIsNone(ov.squad_post)


class PlanOrder(unittest.TestCase):
    def test_squad_hold_runs_after_the_owners_and_before_the_hatches(self):
        src = inspect.getsource(harness.Overseer.plan)
        self.assertLess(src.index("self.mark_guard"), src.index("self.squad_hold"))
        self.assertLess(src.index("self.squad_hold"), src.index("self.entrance_hatches"))

    def test_no_squad_drops_the_record(self):
        game = ge.FakeGame()
        ov = harness.Overseer(game, days=216)
        with redirect_stdout(io.StringIO()):
            ov.load(ge.fort(20, squads=[], weapons_free=0))
            ov.squad_post = ("guard_muster", {"order": "station", "x": 1, "y": 1, "z": 1})
            ov.squad_hold()
        self.assertIsNone(ov.squad_post)
        self.assertEqual(game.calls, [])


if __name__ == "__main__":
    unittest.main()
