"""Regressions for the MY1-autopsy fixes (MY1_AUTOPSY.md §3-§5, runs/w3-my1-s0):

- the standing brew gate keeps a 200-drink floor under its per-citizen cap: at cap 6*7=42 the measured run lost
  eligibility exactly while the caravan glut sat in the fort (d47-76: drink 150-158, pb 26-30), the plants went out
  as raw food and drink hit 0 by d197; the endgame cap max(600, 8*cit) stays untouched,
- glut banking (o_brew_glut): a brewable stock that jumps caravan-scale (GLUT_JUMP over the last load, or standing
  at GLUT_PB and up) draws a one-shot brew order that converts the mountain into drink and returned seeds — one
  attempt a day at most, no done record, because gluts return.

No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {}}


def resp(day, cit=7, pb=0):
    return {"tick": day * harness.DAY, "day": day, "observation": {
        "administrators": {"citizens": cit},
        "stocks": {"plants_brewable": pb, "furniture_free": {}},
        "map": {"sites": []}, "zones": [], "furniture": [],
        "workshops": [{"type": "Still"}, {"type": "Kitchen"}], "orders": []}}


def glut_orders(calls):
    return [a for t, a in calls if t == "add_order" and a.get("recipe") == "brew_drink"
            and "repeat" not in a]


class GlutBank(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=336)
        ov.count = 0
        return ov, game

    # (a) the cap floor: the gate stays clear inside a glut, and still scales above it
    def test_brew_cap_floor_keeps_the_gate_clear_in_a_glut(self):
        ov, game = self.overseer()
        ov.load(resp(45, cit=7))
        ov.supply()
        brew = next(a for t, a in game.calls if a.get("recipe") == "brew_drink")
        self.assertEqual(brew["when"][0], {"stock": "drink", "below": 200})   # max(200, 20 * 7): the floor wins
        ov2, game2 = self.overseer()
        ov2.load(resp(45, cit=40))
        ov2.supply()
        brew2 = next(a for t, a in game2.calls if a.get("recipe") == "brew_drink")
        self.assertEqual(brew2["when"][0], {"stock": "drink", "below": 800})  # 20 * 40 clears the floor

    # (a') the endgame cap stays as the leader's (max(600, 30 * cit)): the fix is the regular standing only
    def test_endgame_brew_cap_is_untouched(self):
        ov, game = self.overseer()
        ov.load(resp(45, cit=7, pb=30))
        ov.endgame_supply()
        end = next(a for t, a in game.calls if a.get("recipe") == "brew_drink")
        self.assertEqual(end["when"][0], {"stock": "drink", "below": max(600, 30 * ov.cit)})
        self.assertEqual(end["when"][1], {"stock": "plants_brewable", "at_least": harness.BREW_END_FLOOR})   # cx: under the cook floor

    # (b) the glut: a caravan-sized jump draws one one-shot brew order, shaped as specified
    def test_glut_jump_draws_a_one_shot_brew(self):
        ov, game = self.overseer()
        ov.load(resp(45, pb=10))                                              # the pre-caravan stock
        ov.load(resp(45, pb=25))                                              # the caravan lands: +15 >= GLUT_JUMP
        ov.glut_bank()
        added = glut_orders(game.calls)
        self.assertEqual(len(added), 1)
        # no `when` on the order: the game rejects a one-shot with when ("add_order when needs repeat",
        # dfull-my1-hard 2026-11-09: 0/151 accepted across 6 runs) — the act gate carries the pb floor
        self.assertEqual(added[0], {"recipe": "brew_drink", "amount": 5})
        self.assertEqual(ov.owned, {1})                                       # the layer's own order, cancellable
                                                                              #   (FakeGame ids by call count)

    def test_glut_order_is_not_done_managed_and_reorders_next_glut(self):
        ov, game = self.overseer()
        ov.load(resp(45, pb=10))
        ov.load(resp(45, pb=25))
        ov.glut_bank()
        self.assertNotIn("o_brew_glut", ov.done)   # gluts return: the key is never retired
        ov.glut_bank()                                                        # the same day: the gate holds it
        self.assertEqual(len(glut_orders(game.calls)), 1)
        ov.load(resp(46, pb=3))                                               # the glut is eaten down: nothing fires
        ov.glut_bank()
        self.assertEqual(len(glut_orders(game.calls)), 1)
        ov.load(resp(47, pb=14))                                              # the next caravan: +11 >= GLUT_JUMP
        ov.glut_bank()
        self.assertEqual(len(glut_orders(game.calls)), 2)

    def test_standing_pb_draws_the_order_without_a_jump(self):
        ov, game = self.overseer()
        ov.load(resp(45, pb=12))                                              # a first load, no previous to jump from
        self.assertEqual(ov.glut_jump, 0)
        ov.glut_bank()                                                        # pb >= GLUT_PB banks it anyway
        self.assertEqual(len(glut_orders(game.calls)), 1)
        ov.load(resp(46, pb=12))                                              # the glut stands: still banked, a day later
        ov.glut_bank()
        self.assertEqual(len(glut_orders(game.calls)), 2)

    def test_small_drip_and_small_stock_draw_nothing(self):
        ov, game = self.overseer()
        ov.load(resp(45, pb=6))
        ov.load(resp(46, pb=9))                                               # farm drip (+3), under the floor
        ov.glut_bank()
        self.assertEqual(glut_orders(game.calls), [])

    # (c) coexistence: the one-shot never suppresses the daily standing, and plan() runs both once
    def test_plan_runs_the_standing_and_the_glut_side_by_side(self):
        ov, game = self.overseer()
        ov.load(resp(45, pb=25))
        ov.plan()
        brews = [a for t, a in game.calls if a.get("recipe") == "brew_drink"]
        self.assertEqual(len([a for a in brews if a.get("repeat") == "daily"]), 1)   # o_brew, cap floored at 200
        self.assertEqual(len([a for a in brews if "repeat" not in a]), 1)            # o_brew_glut, one-shot
        game.calls.clear()
        ov.plan()                                                                  # same day again: both gates hold
        self.assertEqual([a for t, a in game.calls if a.get("recipe") == "brew_drink"], [])


if __name__ == "__main__":
    unittest.main()
