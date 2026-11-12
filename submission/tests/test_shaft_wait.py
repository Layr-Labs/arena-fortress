"""cx shaft wait / gate keep (audit 2026-11-11): the open-shaft foot guard (mark_gate) and its clear wait.

Hint hard MY1-4 on 0b49063, days 184-197: a gray langur 25, 13, 8, 24, 19 tiles from the open E1 shaft, the squad off
duty with armed 0 (all four weapon_assigned), the alert on; mark_clear_wait counted the weapons CARRIED (off duty
nobody carries one), so it logged mark_wait every look and the foot guard was never ordered; on day 195 the alert
lifted with the langur 24 tiles off and the shaft still open. Days 10/11, 57/58, 72/73 of the same run: the foot guard
stood down at each lift and was sent again the next day; 7c43df4 std MY1-4 re-sent the same station on days 76-80.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from overseer import harness  # noqa: E402
from test_danger_marks import FakeGame as MarkGame  # noqa: E402
from test_rescue_station import Look, my14, CHILD_IN, MINER  # noqa: E402

DAY = harness.DAY
SURFACE = 169
MEMBERS = [{"id": i, "weapon_assigned": True, "x": 95 + i, "y": 93, "z": 168} for i in range(4)]
OFF_DUTY = {"id": 0, "armed": 0, "uniform": "weapon+armor", "orders": [], "members": MEMBERS}
FOOT_ARGS = {"order": "station", "x": 100, "y": 101, "z": 169}   # SHAFT_GUARD_TOP: the stair top
FOOT = ("squad_order", FOOT_ARGS)
ON_FOOT = dict(OFF_DUTY, orders=[dict(FOOT_ARGS)])
STAND_DOWN = ("squad_order", {"order": "stand_down"})
ALERT_OFF = ("civilian_alert", {"on": False})


def langur(tiles, y=101):
    """A gray langur `tiles` east of the E1 stair top (100, 101, 169)."""
    return {"id": 501, "race": "GRAY_LANGUR", "hostile": False, "x": 100 + tiles, "y": y, "z": SURFACE}


# the 0b49063 hard MY1-4 looks: day -> tiles from E1
LOOKS_0B49063 = [(184, 25), (185, 13), (192, 8), (195, 24), (197, 19)]


class GearGame(MarkGame):
    """MarkGame with a buildings answer (None: the query answers no buildings, as MarkGame does)."""

    def __init__(self, units=(), buildings=None):
        super().__init__(units)
        self.buildings = buildings

    def query(self, name, **kw):
        if name == "buildings" and self.buildings is not None:
            return {"day": 0, "result": {"ok": True, "buildings": [dict(b) for b in self.buildings],
                                         "total": len(self.buildings)}}
        return super().query(name, **kw)


def stockpile(x1, y1, x2, y2, z):
    return {"id": 42, "type": "Stockpile", "x1": x1, "y1": y1, "x2": x2, "y2": y2, "z": z, "built": True}


class Base(Look):
    def ov(self, units, buildings=None):
        game = GearGame(units, buildings)
        return harness.Overseer(game, days=216), game

    def guard(self, ov, game, day, squad=OFF_DUTY, alert=True):
        return self.look(ov, game, my14(day, [CHILD_IN, MINER], alert=alert, squads=(dict(squad),)))

    @staticmethod
    def stations(calls):
        return [a for t, a in calls if t == "squad_order" and a.get("order") == "station"]

    def logs(self, kind):
        out = []
        for line in self.output._new_target.getvalue().splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("kind") == kind:
                out.append(rec)
        return out


class ShaftWait0b49063(Base):
    def test_days_184_197_the_foot_guard_goes_within_the_bound_and_holds(self):
        self.assertEqual(harness.MARK_WAIT_MAX_DAYS, 1)
        ov, game = self.ov([langur(25)])
        calls = self.guard(ov, game, 184)                       # langur 25 tiles off, armed 0: the wait holds
        self.assertNotIn(FOOT, calls)
        self.assertEqual(self.logs("mark_wait")[-1]["armed"], 0)
        self.assertEqual(self.logs("mark_wait")[-1]["armable"], 4)
        self.assertTrue(ov.gate_waiting)
        game.units = [langur(13)]
        calls = self.guard(ov, game, 185)                       # a day of waiting: the foot guard goes unarmed
        self.assertIn(FOOT, calls)
        self.assertEqual((ov.mark_kind, ov.gate_post), ("mark_gate", True))
        over = self.logs("mark_wait_over")[-1]
        self.assertEqual((over["armed"], over["tiles"]), (0, 13))
        self.assertFalse(ov.gate_waiting)
        for day, tiles in LOOKS_0B49063[2:]:
            game.units = [langur(tiles)]
            calls = self.guard(ov, game, day, squad=ON_FOOT)    # on duty at the foot, still arming
            self.assertNotIn(STAND_DOWN, calls, day)
            self.assertFalse(self.stations(calls), day)         # the same station is not sent again
            self.assertEqual(ov.mark_kind, "mark_gate", day)
            self.assertIsNotNone(ov.mark_station, day)

    def test_before_the_fix_shape_the_wait_never_ended(self):
        # MARK_WAIT_MAX_DAYS None: the old rule (the wait holds while the animal stays close) — every look waits
        old = harness.MARK_WAIT_MAX_DAYS
        harness.MARK_WAIT_MAX_DAYS = None
        self.addCleanup(setattr, harness, "MARK_WAIT_MAX_DAYS", old)
        ov, game = self.ov([langur(25)])
        for day, tiles in LOOKS_0B49063:
            game.units = [langur(tiles)]
            self.assertNotIn(FOOT, self.guard(ov, game, day), day)
        self.assertIsNone(ov.mark_station)

    def test_an_armed_squad_resets_the_wait_clock(self):
        ov, game = self.ov([langur(13)])
        self.guard(ov, game, 184)
        self.assertIsNotNone(ov.mark_wait_since)
        game.units = [langur(45)]                                # gone past MUSTER_CLEAR_TILES: the foot goes
        self.assertIn(FOOT, self.guard(ov, game, 184.5))
        self.assertIsNone(ov.mark_wait_since)


class ShaftWaitLift(Base):
    def setUp(self):
        super().setUp()
        old = harness.MARK_WAIT_MAX_DAYS
        harness.MARK_WAIT_MAX_DAYS = None   # the wait holding (the bound is tested above)
        self.addCleanup(setattr, harness, "MARK_WAIT_MAX_DAYS", old)

    def capped(self, ov, day):
        ov.alert_since = (day - 14) * DAY        # past the cap and its CAP_DEFER_DAYS
        ov.wild_alert_since = (day - 14) * DAY

    def test_day_195_no_lift_while_the_wait_holds_with_the_langur_24_tiles_from_the_shaft(self):
        ov, game = self.ov([langur(19)])
        self.capped(ov, 194)
        self.guard(ov, game, 194)                 # the wait holds (sets gate_waiting)
        self.assertTrue(ov.gate_waiting)
        game.units = [langur(24)]
        self.capped(ov, 195)
        calls = self.guard(ov, game, 195)
        self.assertNotIn(ALERT_OFF, calls)
        self.assertEqual(self.logs("shaft_wait_defer")[-1]["animals"], ["gray langur"])

    def test_the_cap_lifts_once_the_animal_is_past_30_tiles_of_the_shaft(self):
        ov, game = self.ov([langur(19)])
        self.capped(ov, 194)
        self.guard(ov, game, 194)
        game.units = [langur(45)]
        self.capped(ov, 195)
        self.assertIn(ALERT_OFF, self.guard(ov, game, 195))

    def test_the_drink_access_clock_still_lifts(self):
        ov, game = self.ov([langur(19)])
        self.capped(ov, 194)
        self.guard(ov, game, 194)
        self.assertTrue(ov.gate_waiting)
        game.units = [langur(24)]
        self.capped(ov, 195)
        ov.access_tick = (195 - harness.ACCESS_CAP_DAYS - 1) * DAY   # no access window for 11 days
        self.assertIn(ALERT_OFF, self.guard(ov, game, 195))
        self.assertTrue(self.logs("access_lift"))
        self.assertFalse(self.logs("shaft_wait_defer"))


class GearSites(Base):
    def test_gear_below_the_surface_sends_the_foot_guard_at_once(self):
        ov, game = self.ov([langur(8)], buildings=[stockpile(96, 90, 99, 94, 168)])   # in the Shelter
        calls = self.guard(ov, game, 192)
        self.assertIn(FOOT, calls)
        self.assertFalse(self.logs("mark_wait"))
        self.assertEqual(ov.gear_where, "below")

    def test_gear_below_but_a_member_on_the_surface_by_the_animal_waits(self):
        on_top = dict(OFF_DUTY, members=[dict(m, x=106, y=101, z=SURFACE) if m["id"] == 0 else m for m in MEMBERS])
        ov, game = self.ov([langur(8)], buildings=[stockpile(96, 90, 99, 94, 168)])
        self.assertNotIn(FOOT, self.guard(ov, game, 192, squad=on_top))
        self.assertEqual(self.logs("mark_wait")[-1]["gear"], "below")

    def test_gear_on_the_surface_waits_for_an_animal_by_the_stockpile(self):
        # 35 tiles from E1 (past MUSTER_CLEAR_TILES) but 5 from a surface stockpile the members would walk to
        ov, game = self.ov([langur(35)], buildings=[stockpile(128, 100, 130, 102, SURFACE)])
        self.assertNotIn(FOOT, self.guard(ov, game, 192))
        w = self.logs("mark_wait")[-1]
        self.assertEqual((w["gear"], w["tiles"]), ("surface", 5))

    def test_the_buildings_query_runs_once_a_day(self):
        ov, game = self.ov([langur(13)], buildings=[stockpile(88, 98, 92, 107, SURFACE)])
        self.guard(ov, game, 184)
        n = game.queries
        ov.muster_crossing(OFF_DUTY)
        ov.muster_crossing(OFF_DUTY)
        self.assertEqual(game.queries, n)   # cached for the day (MarkGame counts every query)


class GateKeep(Base):
    def test_the_foot_guard_holds_through_a_lift_when_the_animal_drops_out_of_view(self):
        far = langur(40)
        ov, game = self.ov([far])
        self.assertIn(FOOT, self.guard(ov, game, 9))
        game.units = []                                          # day 10: the kea not in view, the alert lifted
        calls = self.guard(ov, game, 10, squad=ON_FOOT, alert=False)
        self.assertNotIn(STAND_DOWN, calls)
        self.assertEqual(ov.mark_kind, "mark_gate")
        game.units = [far]                                       # day 11: back — no second station order
        calls = self.guard(ov, game, 11, squad=ON_FOOT, alert=False)
        self.assertFalse(self.stations(calls))
        self.assertNotIn(STAND_DOWN, calls)

    def test_the_foot_guard_stands_down_once_the_animal_is_gone_for_gate_gone_days(self):
        ov, game = self.ov([langur(40)])
        self.guard(ov, game, 9)
        game.units = []
        self.guard(ov, game, 10, squad=ON_FOOT, alert=False)
        calls = self.guard(ov, game, 9 + harness.GATE_GONE_DAYS + 0.5, squad=ON_FOOT, alert=False)
        self.assertIn(STAND_DOWN, calls)
        self.assertIsNone(ov.mark_station)

    def test_the_foot_guard_holds_past_the_rest_while_the_animal_stays_in_mark_range(self):
        ov, game = self.ov([langur(40)])
        self.guard(ov, game, 9)
        for day in (10, 12, 14, 18):                              # alert off, rest over, no fresh evidence
            calls = self.guard(ov, game, day, squad=ON_FOOT, alert=False)
            self.assertNotIn(STAND_DOWN, calls, day)
            self.assertFalse(self.stations(calls), day)

    def test_the_same_station_is_not_sent_twice(self):
        ov, game = self.ov([langur(40)])
        self.assertIn(FOOT, self.guard(ov, game, 76))
        self.assertFalse(self.stations(self.guard(ov, game, 77, squad=ON_FOOT)))
        self.assertFalse(self.stations(self.guard(ov, game, 79, squad=ON_FOOT)))


if __name__ == "__main__":
    unittest.main()
