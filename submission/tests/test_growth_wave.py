"""The full-year growth mechanics must fire on OP1 (days=336) and stay off on MY1 (216) and the labs: the
wave-wealth chase in the progression step and the full-year bed margin. No game or network is used. The wave
mechanism (wiki Immigration, DF2014 formula: the first wealth-driven migrant wave is sized from created wealth/1000
minus the citizens the autumn caravan reported) is what these knobs serve. On this FULL tree the growth measure lives
only in overseer/harness.py (the AI-facing plain/ layers stay at the leader), so the source variant's digest-line
tests are not carried over."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness as overseer_harness

assert Path(overseer_harness.__file__).is_relative_to(VARIANT), overseer_harness.__file__


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"id": len(self.calls), "order_id": len(self.calls)}}


def facts(day=100, cit=15, wealth=8000, orders=(), workshops=("Carpenters", "Still", "Kitchen")):
    return {"day": day, "tick": day * 1200, "hands_off_in_days": None, "days_left": 336 - day, "observation": {
        "administrators": {"citizens": cit, "manager_active_for_orders": True, "MANAGER_id": 1},
        "wealth": {"created": wealth, "total": wealth},
        "stocks": {"logs_usable": 60, "boulders_usable": 0, "drink": 200, "food_edible": 100,
                   "plants_brewable": 10, "plants_total": 30, "barrels_empty": 5,
                   "beds": 10, "tables": 8, "chairs": 9},
        "map": {"sites": []}, "zones": [], "furniture": [], "workshops": [{"type": w} for w in workshops],
        "orders": list(orders), "plugins": {"autochop": "on", "seedwatch": "on", "autofarm": "on"},
        "date": {"abs_tick": day * 1200},
    }}


class GrowthWave(unittest.TestCase):
    def setUp(self):
        self.buffer = io.StringIO()
        self.output = redirect_stdout(self.buffer)
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, days, day=100, cit=15, wealth=8000, orders=(), workshops=("Carpenters", "Still", "Kitchen"),
                 sites=()):
        game = FakeGame()
        ov = overseer_harness.Overseer(game, days=days)
        ov.load(facts(day=day, cit=cit, wealth=wealth, orders=orders, workshops=workshops))
        ov.sites = list(sites)
        ov.count = 0
        return ov, game

    # ---- the wave-wealth target
    def test_wave_target_raises_the_craft_target_until_twenty_citizens(self):
        ov, _ = self.overseer(336, cit=15, wealth=8000)
        self.assertEqual(ov.wealth_target(),
                         (overseer_harness.WAVE_POP_TARGET + overseer_harness.WAVE_POP_BUFFER)
                         * overseer_harness.WAVE_WEALTH_PER_CIT)
        self.assertEqual(ov.wealth_target(), 21000)   # pop after the wave ≈ reported wealth/1000: 20 + jitter
        ov1b, _ = self.overseer(336, cit=12, wealth=8000)   # the target is census-free (desired = W/1000 − cit)
        self.assertEqual(ov1b.wealth_target(), ov.wealth_target())
        ov2, _ = self.overseer(336, cit=21, wealth=8000)   # rank is already granted at 20+
        self.assertEqual(ov2.wealth_target(), overseer_harness.WEALTH_TARGET)
        ov3, _ = self.overseer(336, day=overseer_harness.PROGRESS_LAST_DAY + 1, wealth=5000)
        self.assertEqual(ov3.wealth_target(), overseer_harness.WEALTH_TARGET)   # the report window is closed
        ov4, _ = self.overseer(216, cit=15, wealth=8000)   # MY1: the leader's floor, no chase
        self.assertEqual(ov4.wealth_target(), overseer_harness.WEALTH_TARGET)

    # ---- the progression step's both sides
    def test_full_year_chase_builds_craftsdwarfs_and_a_heavier_order(self):
        ov, game = self.overseer(336, wealth=8000)
        ov.progress()                                       # first pass: the workshop is missing
        ov.o["workshops"] = [{"type": w} for w in ("Carpenters", "Still", "Kitchen", "Craftsdwarfs")]
        ov.progress()                                       # second pass: the standing order
        built = [a for t, a in game.calls if t == "build_workshop"]
        ordered = [a for t, a in game.calls if t == "add_manager_order"]
        self.assertTrue(all(a["type"] == "Craftsdwarfs" for a in built))
        self.assertEqual(len(ordered), 1)
        self.assertEqual(ordered[0]["amount"], overseer_harness.CRAFT_AMOUNT_WAVE)
        self.assertEqual(ordered[0]["when"], [{"item_type": "WOOD", "at_least": overseer_harness.LOG_RESERVE}])

    def test_full_year_second_craftsdwarfs_while_the_fund_is_short(self):
        shops = ("Carpenters", "Still", "Kitchen", "Craftsdwarfs")
        ov, game = self.overseer(336, wealth=8000, workshops=shops, sites=[{"id": "W1", "kind": "W"}])
        ov.progress()
        self.assertIn(("build_workshop", {"type": "Craftsdwarfs", "site": "W1"}), game.calls)
        ov2, game2 = self.overseer(336, cit=22, wealth=8000, workshops=shops,
                                   sites=[{"id": "W1", "kind": "W"}])   # rank granted: no chase, no second bench
        ov2.progress()
        self.assertNotIn("build_workshop", [t for t, _ in game2.calls])

    def test_third_craftsdwarfs_only_when_the_fund_is_far(self):
        """The measured OP1 rate was 39-54☼/day on 2 benches; a fund farther than WAVE_GAP_THIRD_SHOP from the
        ~21k wave target opens a third bench (same site rules as the second), a near one keeps two."""
        shops = ("Carpenters", "Still", "Kitchen", "Craftsdwarfs", "Craftsdwarfs")
        target = (overseer_harness.WAVE_POP_TARGET + overseer_harness.WAVE_POP_BUFFER)
        near, _ = self.overseer(336, wealth=target * overseer_harness.WAVE_WEALTH_PER_CIT
                                - overseer_harness.WAVE_GAP_THIRD_SHOP, workshops=shops,
                                sites=[{"id": "W1", "kind": "W"}])   # gap == threshold: not far
        near.progress()
        self.assertEqual([t for t, _ in near.game.calls if t == "build_workshop"], [])
        far2, game_far = self.overseer(336, wealth=5000, workshops=shops, sites=[{"id": "W1", "kind": "W"}])
        far2.progress()
        self.assertEqual([a.get("type") for t, a in game_far.calls if t == "build_workshop"], ["Craftsdwarfs"])

    def test_chase_order_amount_is_the_throttle_fix(self):
        """The measured OP1-hard rate 39-54☼/day ≈ the old 6/day order × 7-9☼/craft with unmade jobs queued:
        the chase order must carry the doubled amount and keep the log reserve behind beds and barrels."""
        self.assertEqual(overseer_harness.CRAFT_AMOUNT_WAVE, 12)
        ov, game = self.overseer(336, wealth=8000,
                                 workshops=("Carpenters", "Still", "Kitchen", "Craftsdwarfs"))
        ov.progress()
        ordered = [a for t, a in game.calls if t == "add_manager_order"]
        self.assertEqual([a["amount"] for a in ordered], [overseer_harness.CRAFT_AMOUNT_WAVE])
        self.assertEqual(ordered[0]["when"], [{"item_type": "WOOD", "at_least": overseer_harness.LOG_RESERVE}])
        # cx: after the caravan window the standing keeps CRAFT_AMOUNT_POST (wealth creation never stops)
        ov2, game2 = self.overseer(336, day=overseer_harness.PROGRESS_LAST_DAY + 1, wealth=5000,
                                   workshops=("Carpenters", "Still", "Kitchen", "Craftsdwarfs"))
        ov2.progress()
        self.assertEqual([a["amount"] for t, a in game2.calls if t == "add_manager_order"],
                         [overseer_harness.CRAFT_AMOUNT_POST])

    def test_wealth_at_target_stops_the_chase(self):
        ov, game = self.overseer(336, cit=15, wealth=(overseer_harness.WAVE_POP_TARGET + overseer_harness.WAVE_POP_BUFFER)
                                 * overseer_harness.WAVE_WEALTH_PER_CIT,
                                 workshops=("Carpenters", "Still", "Kitchen", "Craftsdwarfs"))
        ov.progress()
        # cx: a met fund no longer stops wealth creation — a missing standing is re-added at the base amount, and
        # no extra bench is built; an existing standing is left alone
        self.assertEqual([(t, a["amount"]) for t, a in game.calls],
                         [("add_manager_order", overseer_harness.CRAFT_AMOUNT_BASE)])
        ov2, game2 = self.overseer(336, cit=15, wealth=21000,
                                   workshops=("Carpenters", "Still", "Kitchen", "Craftsdwarfs"),
                                   orders=({"job": "MakeCrafts", "repeat": "daily", "total": 12, "id": 7},))
        ov2.progress()
        self.assertEqual(game2.calls, [])

    def test_after_the_caravan_window_crafting_continues(self):
        ov, game = self.overseer(336, day=overseer_harness.PROGRESS_LAST_DAY + 35, wealth=18000,
                                 workshops=("Carpenters", "Still", "Kitchen", "Craftsdwarfs"))
        ov.progress()   # the measured fort stopped creating at ~18k after day 240
        ordered = [a for t, a in game.calls if t == "add_manager_order"]
        self.assertEqual([a["amount"] for a in ordered], [overseer_harness.CRAFT_AMOUNT_POST])

    def test_my1_and_labs_never_move_the_progression_step(self):
        for days, day in ((216, 130), (60, 40)):
            ov, game = self.overseer(days, day=day, wealth=4000,
                                     sites=[{"id": "W1", "kind": "W"}])
            ov.progress()
            self.assertEqual(game.calls, [])

    def test_craft_start_moves_to_day_20(self):
        """The fund's first eight days are worth ~300-500☼ at the measured ramp (df2 54.5-68☼/day from day 28)
        and no other step claims day 20-28, so the chase starts at day 20."""
        self.assertEqual(overseer_harness.PROGRESS_FROM_DAY, 20)
        ov, game = self.overseer(336, day=overseer_harness.PROGRESS_FROM_DAY - 1, wealth=1000)
        ov.progress()
        self.assertEqual(game.calls, [])
        ov2, game2 = self.overseer(336, day=overseer_harness.PROGRESS_FROM_DAY, wealth=1000,
                                   sites=[{"id": "W1", "kind": "W"}])
        ov2.progress()
        self.assertEqual([t for t, _ in game2.calls], ["build_workshop"])

    def test_fourth_craftsdwarfs_when_the_fund_is_far(self):
        """The new-code runs (runs/df2-op1-hard OP1-1/2, read 2026-11-09) pin the rate to the bench count:
        MakeCrafts jobs_in_progress sits at 3 on 3 benches while 4-5 dwarves idle and the standing backlog holds
        9-12 — so a fund still farther than WAVE_GAP_FOURTH_SHOP opens a fourth bench; a nearer fund keeps three
        (and the third-bench rule below WAVE_GAP_FOURTH_SHOP is unchanged)."""
        shops3 = ("Carpenters", "Still", "Kitchen", "Craftsdwarfs", "Craftsdwarfs", "Craftsdwarfs")
        far, game_far = self.overseer(336, wealth=5000, workshops=shops3, sites=[{"id": "W1", "kind": "W"}])
        far.progress()
        self.assertEqual([a.get("type") for t, a in game_far.calls if t == "build_workshop"], ["Craftsdwarfs"])
        near, game_near = self.overseer(336, wealth=10000, workshops=shops3, sites=[{"id": "W1", "kind": "W"}])
        near.progress()                                    # gap 11000: the third-bench band, three held
        self.assertEqual([t for t, _ in game_near.calls if t == "build_workshop"], [])
        short2, game_short = self.overseer(336, wealth=10000,
                                           workshops=("Carpenters", "Still", "Kitchen", "Craftsdwarfs"),
                                           sites=[{"id": "W1", "kind": "W"}])
        short2.progress()                                  # gap 11000 > WAVE_GAP_THIRD_SHOP: the third, unchanged
        self.assertEqual([a.get("type") for t, a in game_short.calls if t == "build_workshop"], ["Craftsdwarfs"])

    # ---- the progression record: log-only evidence of the rank race (the AI-facing layers stay untouched)
    def lines(self, kind):
        return [l for l in self.buffer.getvalue().splitlines() if f'"kind": "{kind}"' in l]

    def test_progress_record_logs_the_rank_expectation_once(self):
        ov, game = self.overseer(336, cit=21, wealth=6000)
        ov.progress()
        ov.progress()
        races = self.lines("prog_rank_race")
        self.assertEqual(len(races), 1)                    # logged once however often the pass re-runs
        self.assertIn('"citizens": 21', races[0])
        self.assertEqual(game.calls, [])                   # record-only: no tool call backs the note
        ov2, _ = self.overseer(336, cit=21, wealth=4000)   # under the Hamlet wealth leg: not a rank yet
        n = len(self.lines("prog_rank_race"))
        ov2.progress()
        self.assertEqual(len(self.lines("prog_rank_race")), n)

    def test_progress_record_logs_migrant_jumps_and_the_stall(self):
        ov, _ = self.overseer(336, cit=15, wealth=6000, day=100)
        ov.progress()                                      # first sight: the baseline, no jump yet
        ov.cit = 18
        ov.progress_record()                               # the jump the next load would carry
        waves = self.lines("prog_wave")
        self.assertEqual(len(waves), 1)
        self.assertIn('"arrived": 3', waves[0])
        self.assertIn('"waves": 3', waves[0])
        ov2, _ = self.overseer(336, cit=15, wealth=6000, day=220)
        ov2.progress_record()                              # both hard-coded waves are in, the census is short
        ov2.progress_record()
        stalls = self.lines("prog_wave_stall")
        self.assertEqual(len(stalls), 1)                   # once, with the fund the window closed on
        self.assertIn('"window_fund": 6000', stalls[0])

    def test_progress_record_runs_even_when_the_chase_has_won(self):
        """The record sits before the wealth-target return: a fund already past the target still logs the rank
        expectation, because the chase's early return must not swallow the race's evidence."""
        ov, game = self.overseer(336, cit=21, wealth=25000)
        ov.progress()
        self.assertEqual(len(self.lines("prog_rank_race")), 1)
        self.assertEqual(game.calls, [])

    def test_progress_record_stays_silent_off_full_year(self):
        for days, day in ((216, 130), (60, 40)):
            n = (len(self.lines("prog_wave")), len(self.lines("prog_rank_race")), len(self.lines("prog_wave_stall")))
            ov, _ = self.overseer(days, day=day, wealth=6000)
            ov.progress()
            self.assertEqual((len(self.lines("prog_wave")), len(self.lines("prog_rank_race")),
                              len(self.lines("prog_wave_stall"))), n)

    # ---- the bed margin
    def test_bed_margin_only_on_full_year(self):
        ov, _ = self.overseer(336, cit=15)
        self.assertEqual(ov.bed_target(), 15 + overseer_harness.FULL_YEAR_BEDS)
        ov2, _ = self.overseer(216, cit=15)
        self.assertEqual(ov2.bed_target(), 18)              # MY1: the leader's +3
        ov3, _ = self.overseer(60, cit=19)
        self.assertEqual(ov3.bed_target(), 22)              # labs: the leader's +3

    def test_surge_tasks_keep_their_own_margin(self):
        game = FakeGame()
        ov = overseer_harness.Overseer(game, goal="migrants are arriving; house them", days=60)
        fact = facts(cit=19)
        fact["hands_off_in_days"] = 21                     # LT08's shape: a window arms the surge
        ov.load(fact)
        self.assertIs(ov.surge, True)
        self.assertEqual(ov.bed_target(), 19 + 12)   # the leader's surge margin (+12); this tree ports no SURGE_BEDS

    # ---- the wave chase respects the caravan window and the rank in the layer's own order, end to end
    def test_chase_runs_through_the_layer_plan_on_a_full_year_fort(self):
        ov, game = self.overseer(336, day=overseer_harness.PROGRESS_FROM_DAY + 5, wealth=1000,
                                 sites=[{"id": "W1", "kind": "W"}, {"id": "W2", "kind": "W"}])
        with redirect_stdout(io.StringIO()):
            ov.plan()
        builds = [a for t, a in game.calls if t == "build_workshop" and a.get("type") == "Craftsdwarfs"]
        self.assertEqual(len(builds), 1)                   # the first bench
        ov.o["workshops"] = list(ov.o["workshops"]) + [{"type": "Craftsdwarfs"}]
        ov.orders = []
        game.calls.clear()
        with redirect_stdout(io.StringIO()):
            ov.progress()
        ordered = [a for t, a in game.calls if t == "add_manager_order"]
        self.assertEqual([a["amount"] for a in ordered], [overseer_harness.CRAFT_AMOUNT_WAVE])
        ov2, game2 = self.overseer(336, day=overseer_harness.PROGRESS_FROM_DAY + 5, wealth=1000,
                                   sites=[{"id": "W1", "kind": "W"}, {"id": "W2", "kind": "W"}])
        ov2.o["workshops"] = list(ov2.o["workshops"]) + [{"type": "Craftsdwarfs"}, {"type": "Craftsdwarfs"}]
        with redirect_stdout(io.StringIO()):
            ov2.progress()
        # both benches are up and the fund is far (target 21000 − 1000 > WAVE_GAP_THIRD_SHOP): the chase adds the third
        self.assertEqual(len([a for t, a in game2.calls if t == "build_workshop"]), 1)
        # a fund within WAVE_GAP_THIRD_SHOP of the target keeps the two benches it has
        ov3, game3 = self.overseer(336, day=overseer_harness.PROGRESS_FROM_DAY + 5,
                                   wealth=(overseer_harness.WAVE_POP_TARGET + overseer_harness.WAVE_POP_BUFFER)
                                   * overseer_harness.WAVE_WEALTH_PER_CIT - overseer_harness.WAVE_GAP_THIRD_SHOP,
                                   sites=[{"id": "W1", "kind": "W"}, {"id": "W2", "kind": "W"}])
        ov3.o["workshops"] = list(ov3.o["workshops"]) + [{"type": "Craftsdwarfs"}, {"type": "Craftsdwarfs"}]
        with redirect_stdout(io.StringIO()):
            ov3.progress()
        self.assertEqual(len([a for t, a in game3.calls if t == "build_workshop"]), 0)


if __name__ == "__main__":
    unittest.main()
