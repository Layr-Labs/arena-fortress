"""Offline regressions for variant A's three changes: the gateway-resilience backoff (connection-class model
errors are slept on, bounded per sleep and per game), the population magnet (wave history from existing fields,
bed/seat headroom, one meeting_area attempt), and the STATUS line's PROGRESSION row. Stub game; no DF, no model,
no network.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import plain.harness as plain_harness  # noqa: E402
from plain.harness import Plain  # noqa: E402
from overseer.harness import DAY  # noqa: E402
from plain import digest  # noqa: E402
from plain.harness import ModelError  # noqa: E402
from support import overseer, plain, resp  # noqa: E402


# --- B: gateway resilience -----------------------------------------------------------------------------------------
class GatewayResilience(unittest.TestCase):
    def under_test(self):
        p = plain(None)   # the model loop's Plain with a stubbed game: only model_backoff is under test here
        return p, p.game

    def test_constants_and_total_backoff_budget(self):
        self.assertEqual(plain_harness.MAX_API_STREAK, 8)
        left, waits = plain_harness.BACKOFF_BUDGET_S, []
        for streak in range(1, plain_harness.MAX_API_STREAK):   # every retry before the layer-only switch
            wait = min(plain_harness.MAX_BACKOFF_S, 2 ** max(1, streak), left)
            left -= wait
            waits.append(wait)
        self.assertEqual(sum(waits), 120.0)                     # the whole-game budget is never overspent
        self.assertTrue(all(w <= 30.0 for w in waits))

    def test_only_connection_class_errors_are_slept_on(self):
        p, _ = self.under_test()
        self.assertEqual(p.backoff_left, plain_harness.BACKOFF_BUDGET_S)
        waited = []
        with mock.patch.object(plain_harness.time, "sleep", waited.append):
            self.assertEqual(p.model_backoff(1, ModelError("gateway unreachable: DNS name resolution failed")), 2)
            self.assertEqual(p.model_backoff(2, ModelError("gateway unreachable: [Errno 60] connection refused")), 4)
            self.assertEqual(p.model_backoff(4, ModelError("gateway unreachable: timed out")), 16)
            self.assertEqual(p.model_backoff(5, ModelError("HTTP 502: bad gateway", 502)), 0.0)   # not connection
            self.assertEqual(p.model_backoff(5, ModelError("context overflow", 400)), 0.0)
        self.assertEqual(waited, [2, 4, 16])
        self.assertEqual(round(p.backoff_left, 2), plain_harness.BACKOFF_BUDGET_S - 22)

    def test_backoff_never_exceeds_its_budget(self):
        p, _ = self.under_test()
        p.backoff_left = 3
        waited = []
        with mock.patch.object(plain_harness.time, "sleep", waited.append):
            self.assertEqual(p.model_backoff(6, ModelError("gateway unreachable: name resolution failed")), 3.0)
            self.assertEqual(p.backoff_left, 0)
            self.assertEqual(p.model_backoff(7, ModelError("gateway unreachable: name resolution failed")), 0.0)
        self.assertEqual(waited, [3.0])



# --- A: population magnet ------------------------------------------------------------------------------------------
class PopulationMagnet(unittest.TestCase):
    def test_headroom(self):
        ov, g = overseer(resp(136, 200, food=60, cit=15))       # an open full-year task below 20 citizens
        self.assertEqual(ov.population_headroom(), (4, 2))      # max(6, no wave seen) above the usual cit+3
        ov.max_wave = 8
        self.assertEqual(ov.population_headroom(), (6, 2))      # the largest wave seen goes into the targets
        ov.days, ov.lab, ov.hands_off = 60, True, 21            # a lab task: no magnet
        self.assertEqual(ov.population_headroom(), (0, 0))
        ov.lab, ov.hands_off, ov.days = False, None, 216        # a 216-day game: no magnet (MY1 is unchanged)
        self.assertEqual(ov.population_headroom(), (0, 0))

    def test_wave_history_reads_only_existing_fields_and_paces(self):
        r = resp(140, 196, food=60, cit=15)
        r["observation"]["recent_events"] = ["Some migrants have arrived."]
        ov, g = overseer(r)
        self.assertIsNone(ov.wave_day)                          # the announcements alone decide nothing
        ov.last_cit = 10
        ov.read_waves()                                         # the citizens jump over the announcement days
        self.assertEqual((ov.max_wave, ov.wave_day), (5, 196))
        self.assertTrue(ov.wave_recent())
        self.assertEqual(ov.step_days(), 1)                     # in a wave season the passes stay at a day
        ov.load(resp(76, 260, food=60, cit=15))                 # the wave day is long gone
        self.assertFalse(ov.wave_recent())
        self.assertEqual(ov.step_days(), 2)

    def test_one_meeting_area_attempt_when_beds_are_met(self):
        r = resp(136, 200, food=60, cit=16)
        r["observation"]["furniture"] = [{"kind": "bed", "built": True} for _ in range(17)]
        r["observation"]["map"]["sites"] = [{"id": "A1", "kind": "A", "open_tiles": 12}]
        ov, g = overseer(r)
        ov.population_step()
        self.assertEqual(g.tools("make_zone"), [({"kind": "meeting_area", "site": "A1"})])
        ov.population_step()                                    # once per game, accepted or refused
        self.assertEqual(len(g.tools("make_zone")), 1)

    def test_no_meeting_area_while_beds_are_unmet_or_one_stands(self):
        r = resp(136, 200, food=60, cit=16)
        r["observation"]["furniture"] = [{"kind": "bed", "built": True, "x": i} for i in range(4)]
        r["observation"]["map"]["sites"] = [{"id": "A1", "kind": "A", "open_tiles": 12}]
        ov, g = overseer(r)
        ov.population_step()
        self.assertEqual(g.tools("make_zone"), [])              # unmet beds first
        r["observation"]["furniture"] = [{"kind": "bed", "built": True, "x": i} for i in range(17)]
        r["observation"]["zones"] = [{"id": 3, "type": "meeting_area"}]
        ov.load(r)
        ov.meeting_tried = False
        ov.population_step()
        self.assertEqual(g.tools("make_zone"), [])              # one exists: nothing is asked


# --- C: the PROGRESSION line ---------------------------------------------------------------------------------------
# --- A: population magnet ------------------------------------------------------------------------------------------
class ProgressionLine(unittest.TestCase):
    @staticmethod
    def obs(created=10900, cit=19, beds=21, **extra):
        return {"date": {}, "administrators": {"citizens": cit},
                "dwarves": [{"id": i, "job": "mine"} for i in range(cit)],
                "stocks": {"food_edible": 60, "drink": 50, "logs_usable": 20},
                "furniture": [{"kind": "bed", "built": True} for _ in range(beds)],
                "map": {"sites": []}, "workshops": [{"type": "Carpenters", "built": True}],
                "wealth": {"created": created}, "recent_events": [], **extra}

    @staticmethod
    def status(o):
        return digest.digest(o, {"day": 200, "tick": 200 * DAY, "days_left": 136})

    def test_the_line_stands_right_after_the_alert_lines(self):
        o = self.obs(recent_events=["Urist, Mason has been found dead."])
        lines = self.status(o).splitlines()
        prog = next(i for i, l in enumerate(lines) if l.startswith("PROGRESSION"))
        self.assertLess(max(i for i, l in enumerate(lines) if l.startswith("ALERT")), prog)
        self.assertEqual(prog, 2)                               # header, ALERT death, PROGRESSION, then clock...
        self.assertIn("clock:", lines[prog + 1])
        self.assertIn("pop 19/20, beds 21, wealth 10900/5500 (created), rank 1 citizen(s) short of Hamlet",
                      lines[prog])

    def test_the_rank_gap_names_what_is_still_missing(self):
        lines = self.status(self.obs(cit=17, beds=8, created=5180)).splitlines()
        self.assertIn("rank 3 citizen(s) short, 320 created short of Hamlet", lines[1])
        lines = self.status(self.obs(cit=21, beds=25)).splitlines()
        self.assertIn("rank Hamlet met", lines[1])
        lines = self.status(self.obs(created=5180)).splitlines()
        self.assertIn(", 320 created short of Hamlet", lines[1])    # the wealth gap joins the citizens' one

    def test_no_line_without_a_wealth_report(self):
        o = self.obs()
        del o["wealth"]
        self.assertNotIn("PROGRESSION", self.status(o))


if __name__ == "__main__":
    unittest.main()


# --- wall guard: the wall cap never eats the year's last weeks -------------------------------------------------------
class WallGuard(unittest.TestCase):
    def under_test(self, wall_s=5400, ago=0.0):
        import time
        t = type("T", (), {"task": {"days": 336}, "days": 336, "credits": 0.5, "wall_s": wall_s})
        p = Plain(t, None, None)
        p.t0 = None if ago is None else time.monotonic() - ago
        return p

    def test_no_cap_no_guard(self):
        self.assertIsNone(self.under_test(wall_s=None).wall_left())
        self.assertIsNone(self.under_test(ago=None).wall_left())

    def test_threshold_at_the_horizon_is_the_base_reserve(self):
        import plain.harness as ph
        p = self.under_test(wall_s=None)          # wall irrelevant for the estimate
        p.days_total = 336
        self.assertAlmostEqual(p.wall_needed(336), ph.WALL_GUARD_BASE_S)
        self.assertAlmostEqual(p.wall_needed(0), ph.WALL_GUARD_BASE_S + 336 * ph.WALL_GUARD_EMA0_S / ph.WALL_GUARD_STRIDE)
        p.call_ema = 12.0
        self.assertAlmostEqual(p.wall_needed(300), ph.WALL_GUARD_BASE_S + 36 * 12.0 / ph.WALL_GUARD_STRIDE)

    def test_backoff_never_sleeps_into_the_guard_reserve(self):
        with mock.patch("time.sleep"):
            import time
            p = self.under_test(wall_s=5400, ago=5100)   # 300 left: below base+any wait
            p.backoff_left = 120.0
            self.assertEqual(p.model_backoff(1, ModelError("Connection refused by the gateway")), 0.0)
            p = self.under_test(wall_s=5400, ago=4800)   # 600 left: the cap binds below the wait, not the wall
            self.assertEqual(p.model_backoff(1, ModelError("gateway unreachable")), 2.0)
            self.assertEqual(p.model_backoff(6, ModelError("gateway unreachable")), 30.0)
            p = self.under_test(wall_s=None, ago=0)      # no cap: ordinary budget applies
            self.assertEqual(p.model_backoff(1, ModelError("gateway unreachable")), 2.0)
