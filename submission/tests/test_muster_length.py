"""cx muster length (owner question 2026-11-11: how long must a muster be?). Arming takes hours (probe pm: 1-11 game
hours a member, 2 armed in 1-2 h) and the weapons go back within hours of a stand_down, so a squad kept on duty while
nothing comes near only costs work (members: 35% of the fort's work, 43% of its food/drink work, 4.5% while on
duty). (1) A wildlife muster stands down after MUSTER_IDLE_CAP_DAYS with no approach / fight / shaft sighting and
musters again on the next one; None keeps the old whole-reason hold. (2) With SHAFT_GUARD_TILES set, the open-shaft
foot guard holds SHAFT_GUARD_HOLD_DAYS past the start and each contact (a weak marked animal within SHAFT_GUARD_TILES
of the shaft, an approach, a fight) and stands down otherwise — never a station on the animal instead; None (the
default) keeps the guard for the whole presence. No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_guard_equip as ge  # noqa: E402
from test_danger_marks import FakeGame  # noqa: E402
from test_rescue_station import Look, my14, CHILD_IN, MINER, KEA_OVER_FORT  # noqa: E402
from overseer import harness  # noqa: E402

STAND_DOWN = ("squad_order", {"order": "stand_down"})
ARMABLE = {"id": 0, "armed": 0, "uniform": "weapon+armor", "orders": [],
           "members": [{"id": i, "weapon_assigned": True} for i in range(4)]}
KEA_FAR = dict(KEA_OVER_FORT, x=140, y=140, z=172)   # ~40 tiles from E1 (100,101): inside MARK_RANGE, past 20/30
FOOT = ("squad_order", {"order": "station", "x": 100, "y": 101, "z": 169})   # SHAFT_GUARD_TOP: the stair top


class Setting:
    """Patch a module constant for one test."""
    def __init__(self, test, **kw):
        for k, v in kw.items():
            old = getattr(harness, k)
            setattr(harness, k, v)
            test.addCleanup(setattr, harness, k, old)


class MusterCap(ge.Base):
    def muster(self, ov, game, day, orders=()):
        ov.wild_alert_since = 18 * harness.DAY   # the reason stands (the fixture names no animal)
        sq = dict(ge.my14_squad(), orders=[dict(o) for o in orders])
        return self.pass_(ov, game, day, squads=[sq], weapons_free=0, alert=True)

    def station(self, calls):
        return [a for t, a in calls if t == "squad_order" and a.get("order") == "station"]

    def test_the_muster_holds_inside_the_cap(self):
        Setting(self, MUSTER_IDLE_CAP_DAYS=3)
        ov, game = self.ov()
        st = self.station(self.muster(ov, game, 20))
        self.assertEqual(len(st), 1)
        for day in (21, 22, 23):
            self.assertNotIn(STAND_DOWN, self.muster(ov, game, day, orders=st))
        self.assertIsNotNone(ov.muster)

    def test_no_contact_past_the_cap_stands_down_and_waits(self):
        Setting(self, MUSTER_IDLE_CAP_DAYS=3)
        ov, game = self.ov()
        st = self.station(self.muster(ov, game, 20))
        self.muster(ov, game, 22, orders=st)
        calls = self.muster(ov, game, 24, orders=st)
        self.assertIn(STAND_DOWN, calls)
        self.assertIsNone(ov.muster)
        self.assertEqual(self.logs("guard_muster_end")[-1]["why"], "lingering")
        self.assertFalse(self.station(self.muster(ov, game, 25)))   # the reason still stands: no new muster
        self.assertTrue(self.logs("muster_linger"))

    def test_a_fight_musters_again_and_restarts_the_count(self):
        Setting(self, MUSTER_IDLE_CAP_DAYS=3)
        ov, game = self.ov()
        st = self.station(self.muster(ov, game, 20))
        self.muster(ov, game, 24, orders=st)            # stood down: lingering
        ov.wild_watch["kea"] = 26 * harness.DAY
        ov.wild_evidence["kea"] = 26 * harness.DAY      # a kea fight on day 26
        st2 = self.station(self.muster(ov, game, 26))
        self.assertEqual(len(st2), 1)
        # the fight counts as contact while wild_evidenced holds it (WILD_EVIDENCE_DAYS: looks to day 29)
        self.assertNotIn(STAND_DOWN, self.muster(ov, game, 28, orders=st2))
        self.assertNotIn(STAND_DOWN, self.muster(ov, game, 30, orders=st2))
        self.assertIn(STAND_DOWN, self.muster(ov, game, 32, orders=st2))      # > 3 days past the last contact

    def test_cap_none_holds_the_whole_reason(self):
        Setting(self, MUSTER_IDLE_CAP_DAYS=None)
        ov, game = self.ov()
        st = self.station(self.muster(ov, game, 20))
        for day in (24, 30, 40):
            self.assertNotIn(STAND_DOWN, self.muster(ov, game, day, orders=st))
        self.assertIsNotNone(ov.muster)

    def test_a_gone_reason_resets_the_count(self):
        Setting(self, MUSTER_IDLE_CAP_DAYS=3)
        ov, game = self.ov()
        st = self.station(self.muster(ov, game, 20))
        ov.wild_alert_since = None
        sq = dict(ge.my14_squad(), orders=[dict(st[0])], armed=4)
        calls = self.pass_(ov, game, 22, squads=[sq], weapons_free=0)
        self.assertIn(STAND_DOWN, calls)
        self.assertEqual(self.logs("guard_muster_end")[-1]["why"], "need_gone")
        self.assertIsNone(ov.muster_since)
        self.assertEqual(len(self.station(self.muster(ov, game, 40))), 1)   # a new reason: a fresh muster

    def test_a_big_beast_watched_in_the_alert_holds_the_whole_reason(self):
        # hint hard MY1-4 on b092a1d: a carnotaurus's alert (day 184, mark_alert pre; big_hold day 186) and the
        # muster stood down 'lingering' on day 191 with the beast near — the cap is for the weak thieves only
        Setting(self, MUSTER_IDLE_CAP_DAYS=3)
        ov, game = self.ov()
        ov.wild_watch["carnotaurus"] = 18 * harness.DAY   # sounded the alert (wild_alert_since 18 in muster())
        st = self.station(self.muster(ov, game, 20))
        self.assertEqual(len(st), 1)
        for day in (24, 30, 37):
            self.assertNotIn(STAND_DOWN, self.muster(ov, game, day, orders=st))
        self.assertIsNotNone(ov.muster)
        self.assertFalse(self.logs("muster_linger"))

    def test_a_big_alert_span_holds_the_whole_reason(self):
        Setting(self, MUSTER_IDLE_CAP_DAYS=3)
        ov, game = self.ov()
        self.muster(ov, game, 20)
        ov.wild_spans = [[18 * harness.DAY, None, "big"]]   # big_alert's open span
        self.assertTrue(ov.muster_big())
        ov.wild_spans = [[18 * harness.DAY, 19 * harness.DAY, "big"], [19 * harness.DAY, None]]
        self.assertFalse(ov.muster_big())

    def test_a_big_beast_from_an_earlier_alert_does_not_lift_the_cap(self):
        # watched before this alert began: the reason is the weak animal's, the cap stands
        Setting(self, MUSTER_IDLE_CAP_DAYS=3)
        ov, game = self.ov()
        ov.wild_watch["carnotaurus"] = 10 * harness.DAY
        ov.wild_spans = [[10 * harness.DAY, 14 * harness.DAY, "big"]]   # that alert closed
        st = self.station(self.muster(ov, game, 20))
        self.muster(ov, game, 22, orders=st)
        self.assertIn(STAND_DOWN, self.muster(ov, game, 24, orders=st))
        self.assertEqual(self.logs("guard_muster_end")[-1]["why"], "lingering")

    def test_muster_big_reads_a_big_marked_unit_in_range(self):
        game = FakeGame([{"id": 5, "race": "CARNOTAURUS", "hostile": False, "x": 140, "y": 140, "z": 169}])
        ov = harness.Overseer(game, days=216)
        ov.load(my14(160, [CHILD_IN, MINER]))
        self.assertTrue(ov.muster_big())
        game.units = [dict(KEA_FAR)]
        ov.load(my14(161, [CHILD_IN, MINER]))
        self.assertFalse(ov.muster_big())

    def test_invaders_are_never_capped(self):
        Setting(self, MUSTER_IDLE_CAP_DAYS=0)
        ov, game = self.ov()
        self.assertFalse(ov.muster_lingering(False))
        self.assertIsNone(ov.muster_since)


class ShaftGuardLength(Look):
    def guard(self, ov, game, day, squad=ARMABLE, alert=True):
        return self.look(ov, game, my14(day, [CHILD_IN, MINER], alert=alert, squads=(dict(squad),)))

    def on_duty(self, call):
        return dict(ARMABLE, armed=4, orders=[dict(call[1])])

    def test_default_keeps_the_guard_for_the_whole_presence(self):
        self.assertIsNone(harness.SHAFT_GUARD_TILES)
        game = FakeGame([KEA_FAR])
        ov = harness.Overseer(game, days=216)
        self.assertIn(FOOT, self.guard(ov, game, 160))
        for day in (163, 170):
            calls = self.guard(ov, game, day, squad=self.on_duty(FOOT))
            self.assertNotIn(STAND_DOWN, calls)
        self.assertTrue(ov.gate_post)

    def test_a_far_kea_gets_the_guard_at_the_start_then_it_rests(self):
        Setting(self, SHAFT_GUARD_TILES=20, SHAFT_GUARD_HOLD_DAYS=1)
        game = FakeGame([KEA_FAR])
        ov = harness.Overseer(game, days=216)
        self.assertIn(FOOT, self.guard(ov, game, 160))       # the start of the threat: out at once
        self.assertTrue(ov.gate_post)
        calls = self.guard(ov, game, 162, squad=self.on_duty(FOOT))
        self.assertIn(STAND_DOWN, calls)                     # 2 days, the kea 40 tiles out, no fight
        self.assertFalse([a for t, a in calls if t == "squad_order" and a.get("order") == "station"])
        self.assertIsNone(ov.mark_station)
        self.assertFalse(ov.gate_post)
        self.assertTrue(self.logs("shaft_guard_rest"))
        calls = self.guard(ov, game, 163)                    # still far: no station anywhere
        self.assertFalse([a for t, a in calls if t == "squad_order" and a.get("order") == "station"])

    def test_a_kea_at_the_shaft_brings_the_guard_back(self):
        Setting(self, SHAFT_GUARD_TILES=20, SHAFT_GUARD_HOLD_DAYS=1)
        game = FakeGame([KEA_FAR])
        ov = harness.Overseer(game, days=216)
        self.guard(ov, game, 160)
        self.guard(ov, game, 162, squad=self.on_duty(FOOT))   # rests
        game.units = [dict(KEA_OVER_FORT)]                    # 4 tiles from E1
        # cx muster clear: off duty after the rest nobody carries a weapon — the unarmed squad does not walk out past
        # the kea to its equipment; with MARK_RESCUE_ARMED armed it goes back to the foot
        self.assertNotIn(FOOT, self.guard(ov, game, 163))
        self.assertIn(FOOT, self.guard(ov, game, 163, squad=dict(ARMABLE, armed=harness.MARK_RESCUE_ARMED)))
        game.units = [dict(KEA_FAR)]
        self.assertNotIn(STAND_DOWN, self.guard(ov, game, 163.5, squad=self.on_duty(FOOT)))   # within the hold

    def logs(self, kind):
        import json
        out = []
        for line in self.output._new_target.getvalue().splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("kind") == kind:
                out.append(rec)
        return out


if __name__ == "__main__":
    unittest.main()
