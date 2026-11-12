"""cx muster clear (MUSTER_CLEAR_TILES): a wildlife muster sends the members out to fetch their uniform; hint hard
MY1-4 on b092a1d day 5 sent them up the E1 stair into a kea 6 tiles from its top (both "Pickup equipment:
Interrupted by a kea" at the stair top, a recruit "I'm panicking!", stressed for the rest of the run). The muster now
waits while a marked animal stands within MUSTER_CLEAR_TILES of a surface entrance or a squad member, and goes once
it is farther. Invaders are never held. No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_guard_equip as ge  # noqa: E402
from overseer import harness  # noqa: E402

S = ge.SURFACE
KEA_AT_STAIR = {"id": 242, "race": "BIRD_KEA", "hostile": False, "x": 110, "y": 100, "z": S}   # 6 tiles from E1
KEA_FAR = {"id": 242, "race": "BIRD_KEA", "hostile": False, "x": 150, "y": 140, "z": S + 2}    # 46 from E1
GATOR_AT_STAIR = {"id": 7, "race": "ALLIGATOR", "hostile": False, "x": 98, "y": 92, "z": S}


class UnitsGame(ge.FakeGame):
    def __init__(self, units=()):
        super().__init__()
        self.units = [dict(u) for u in units]

    def query(self, name, **kw):
        if name == "units":
            self.queries.append((name, kw))
            return {"result": {"ok": True, "units": [dict(u) for u in self.units]}}
        return super().query(name, **kw)


class MusterClear(ge.Base):
    def go(self, units, day=20, members_at=None, alert=True):
        game = UnitsGame(units)
        ov = harness.Overseer(game, days=216)
        ov.wild_alert_since = (day - 2) * harness.DAY
        sq = ge.my14_squad()
        if members_at:
            sq["members"] = [dict(m, x=members_at[0], y=members_at[1], z=members_at[2]) for m in sq["members"]]
        calls = self.pass_(ov, game, day, squads=[sq], weapons_free=0, alert=alert)
        return ov, game, [a for t, a in calls if t == "squad_order" and a.get("order") == "station"]

    def test_a_kea_by_the_stair_holds_the_muster(self):
        ov, game, st = self.go([KEA_AT_STAIR])
        self.assertFalse(st)
        self.assertIsNone(ov.muster)
        w = self.logs("muster_wait")[-1]
        self.assertEqual(w["animals"], ["kea"])
        self.assertLessEqual(w["tiles"], harness.MUSTER_CLEAR_TILES)

    def test_a_far_kea_musters(self):
        ov, game, st = self.go([KEA_FAR])
        self.assertEqual(len(st), 1)
        self.assertFalse(self.logs("muster_wait"))

    def test_the_muster_goes_once_the_kea_draws_off(self):
        ov, game, st = self.go([KEA_AT_STAIR])
        self.assertFalse(st)
        game.units = [dict(KEA_FAR)]
        sq = ge.my14_squad()
        calls = self.pass_(ov, game, 21, squads=[sq], weapons_free=0, alert=True)
        self.assertEqual(len([a for t, a in calls if t == "squad_order" and a.get("order") == "station"]), 1)

    def test_a_kea_near_a_member_holds_it_too(self):
        # far from every entrance, 5 tiles from members working on the surface
        kea = dict(KEA_FAR, x=150, y=150, z=S)
        ov, game, st = self.go([kea], members_at=(145, 150, S))
        self.assertFalse(st)

    def test_a_big_beast_by_the_stair_holds_it(self):
        ov, game, st = self.go([GATOR_AT_STAIR])
        self.assertFalse(st)

    def test_none_keeps_the_old_muster(self):
        old = harness.MUSTER_CLEAR_TILES
        harness.MUSTER_CLEAR_TILES = None
        self.addCleanup(setattr, harness, "MUSTER_CLEAR_TILES", old)
        ov, game, st = self.go([KEA_AT_STAIR])
        self.assertEqual(len(st), 1)

    def test_invaders_are_not_held(self):
        gob = [{"id": 900, "race": "GOBLIN", "invader": True, "x": 106, "y": 98, "z": S}]
        game = UnitsGame([KEA_AT_STAIR])
        ov = harness.Overseer(game, days=216)
        ov.load(ge.fort(20, squads=[ge.my14_squad()], weapons_free=0, hostiles=gob, alert=True))
        self.assertEqual(ov.muster_crossing(ge.my14_squad())[0]["_mark"], "kea")   # it would hold wildlife
        ov.count = 0
        game.calls.clear()
        ov.guard_muster(ge.my14_squad(), force="invaders")
        self.assertTrue([a for t, a in game.calls if t == "squad_order" and a.get("order") == "station"])


STAND_DOWN = ("squad_order", {"order": "stand_down"})
KEA_GONE = dict(KEA_FAR, x=400, y=400)   # past MARK_RANGE


class Presence(ge.Base):
    """Open entrance (wildlife musters stand only there): the muster goes at the first sighting beyond
    MUSTER_CLEAR_TILES and holds for the whole presence (owner); a standing muster still arming stands down while the
    animal is within MUSTER_CLEAR_TILES (on duty the members walk out to their equipment)."""

    def setUp(self):
        super().setUp()
        old = harness.MUSTER_IDLE_CAP_DAYS
        harness.MUSTER_IDLE_CAP_DAYS = 3
        self.addCleanup(setattr, harness, "MUSTER_IDLE_CAP_DAYS", old)
        self.game = UnitsGame([KEA_FAR])
        self.ov = harness.Overseer(self.game, days=216)
        self.ov.wild_alert_since = 18 * harness.DAY

    def look(self, day, units=None, orders=(), armed=1):
        if units is not None:
            self.game.units = [dict(u) for u in units]
        self.ov.wild_alert_since = 18 * harness.DAY   # the alert stands (defend() may lift it with the animal gone)
        sq = dict(ge.my14_squad(), orders=[dict(o) for o in orders], armed=armed)
        return self.pass_(self.ov, self.game, day, squads=[sq], weapons_free=0, alert=True)

    def station(self, calls):
        return [a for t, a in calls if t == "squad_order" and a.get("order") == "station"]

    def test_first_sighting_beyond_clear_musters_and_holds_the_presence(self):
        st = self.station(self.look(20))
        self.assertEqual(len(st), 1)
        for day in (24, 30, 40):   # no approach, no fight, the kea 46 tiles out: no cap while it is present
            self.assertNotIn(STAND_DOWN, self.look(day, orders=st))
        self.assertIsNotNone(self.ov.muster)
        self.assertFalse(self.logs("muster_linger"))

    def test_the_cap_counts_once_the_animal_is_gone_and_the_alert_stands(self):
        st = self.station(self.look(20))
        self.look(21, units=[KEA_GONE], orders=st)
        self.look(23, orders=st)
        calls = self.look(25, orders=st)
        self.assertIn(STAND_DOWN, calls)
        self.assertEqual(self.logs("guard_muster_end")[-1]["why"], "lingering")

    def test_an_arming_muster_stands_down_when_the_animal_comes_close_then_musters_again(self):
        st = self.station(self.look(20))
        calls = self.look(20.5, units=[KEA_AT_STAIR], orders=st, armed=0)
        self.assertIn(STAND_DOWN, calls)
        end = self.logs("guard_muster_end")[-1]
        self.assertEqual(end["why"], "clear_wait")
        self.assertEqual(end["animals"], ["kea"])
        self.assertIsNone(self.ov.muster)
        self.assertFalse(self.station(self.look(21, armed=0)))           # still close: waits
        self.assertEqual(len(self.station(self.look(22, units=[KEA_FAR], armed=0))), 1)   # clear: again

    def test_an_armed_muster_keeps_its_station(self):
        st = self.station(self.look(20))
        calls = self.look(21, units=[KEA_AT_STAIR], orders=st, armed=harness.MARK_RESCUE_ARMED)
        self.assertNotIn(STAND_DOWN, calls)
        self.assertFalse([e for e in self.logs("guard_muster_end") if e["why"] == "clear_wait"])


from test_danger_marks import FakeGame as MarkGame  # noqa: E402
from test_rescue_station import Look, my14, CHILD_IN, MINER, KEA_OVER_FORT  # noqa: E402

ARMABLE = {"id": 0, "armed": 0, "uniform": "weapon+armor", "orders": [],
           "members": [{"id": i, "weapon_assigned": True} for i in range(4)]}
FOOT = ("squad_order", {"order": "station", "x": 100, "y": 101, "z": 169})   # SHAFT_GUARD_TOP: the stair top
KEA_40 = dict(KEA_OVER_FORT, x=140, y=140, z=172)   # ~40 tiles from E1: inside MARK_RANGE, past MUSTER_CLEAR_TILES


class MarkStationClear(Look):
    """The same rule for mark_guard's own stations: mark_gate counts armable members (arm_record), so it goes out with
    nobody carrying a weapon, and on duty the members walk out to their equipment — past a kea at the shaft. While
    fewer than MARK_RESCUE_ARMED are armed and a marked animal is within MUSTER_CLEAR_TILES of a surface entrance or a
    member, no mark_gate / mark_station is ordered and a standing one stands down; mark_rescue is not held."""

    def ov(self, units):
        game = MarkGame(units)
        return harness.Overseer(game, days=216), game

    def guard(self, ov, game, day, squad=ARMABLE, alert=True):
        return self.look(ov, game, my14(day, [CHILD_IN, MINER], alert=alert, squads=(dict(squad),)))

    @staticmethod
    def stations(calls):
        return [a for t, a in calls if t == "squad_order" and a.get("order") == "station"]

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

    def test_an_unarmed_gate_waits_while_the_kea_is_at_the_shaft(self):
        ov, game = self.ov([KEA_OVER_FORT])                     # 4 tiles from E1
        calls = self.guard(ov, game, 156)
        self.assertFalse(self.stations(calls))                  # neither the gate nor an arming muster
        self.assertIsNone(ov.mark_station)
        w = self.logs("mark_wait")[-1]
        self.assertEqual(w["animals"], ["kea"])
        self.assertEqual(w["armed"], 0)
        self.assertLessEqual(w["tiles"], harness.MUSTER_CLEAR_TILES)

    def test_the_gate_goes_once_the_kea_is_farther(self):
        ov, game = self.ov([KEA_OVER_FORT])
        self.guard(ov, game, 156)
        game.units = [dict(KEA_40)]
        self.assertIn(FOOT, self.guard(ov, game, 156.5))
        self.assertEqual(ov.mark_kind, "mark_gate")

    def test_an_armed_gate_is_not_held(self):
        ov, game = self.ov([KEA_OVER_FORT])
        self.assertIn(FOOT, self.guard(ov, game, 156, squad=dict(ARMABLE, armed=harness.MARK_RESCUE_ARMED)))
        self.assertFalse(self.logs("mark_wait"))

    def test_a_standing_gate_still_arming_stands_down_when_the_kea_comes_close(self):
        ov, game = self.ov([KEA_40])
        self.assertIn(FOOT, self.guard(ov, game, 160))
        self.assertTrue(ov.gate_post)
        game.units = [dict(KEA_OVER_FORT)]
        on_duty = dict(ARMABLE, armed=1, orders=[dict(FOOT[1])])   # one member back with his weapon so far
        calls = self.guard(ov, game, 160.2, squad=on_duty)
        self.assertIn(STAND_DOWN, calls)
        self.assertFalse(self.stations(calls))
        end = self.logs("mark_stand_down")[-1]
        self.assertEqual((end["why"], end["station"], end["animals"]), ("clear_wait", "mark_gate", ["kea"]))
        self.assertIsNone(ov.mark_station)
        self.assertFalse(ov.gate_post)
        self.assertFalse(self.stations(self.guard(ov, game, 161)))          # still close: waits
        game.units = [dict(KEA_40)]
        self.assertIn(FOOT, self.guard(ov, game, 162))                      # farther: out again

    def test_a_standing_gate_with_enough_armed_holds(self):
        ov, game = self.ov([KEA_40])
        self.guard(ov, game, 160)
        game.units = [dict(KEA_OVER_FORT)]
        on_duty = dict(ARMABLE, armed=harness.MARK_RESCUE_ARMED, orders=[dict(FOOT[1])])
        calls = self.guard(ov, game, 160.2, squad=on_duty)
        self.assertNotIn(STAND_DOWN, calls)
        self.assertIsNotNone(ov.mark_station)

    def test_a_standing_station_on_the_animal_is_held_the_same_way(self):
        ov, game = self.ov([KEA_OVER_FORT])
        ov.mark_station, ov.mark_kind, ov.gate_post = 159 * harness.DAY, "mark_station", False
        ov.mark_hold = 159 * harness.DAY
        sq = dict(ARMABLE, armed=1, orders=[{"order": "station", "x": 101, "y": 105, "z": 169}])
        calls = self.guard(ov, game, 159.5, squad=sq)
        self.assertIn(STAND_DOWN, calls)
        self.assertEqual(self.logs("mark_stand_down")[-1]["station"], "mark_station")
        self.assertIsNone(ov.mark_station)

    def test_a_rescue_is_not_held_by_the_clear_wait(self):
        ov, game = self.ov([KEA_OVER_FORT])
        ov.mark_station, ov.mark_kind, ov.gate_post = 159 * harness.DAY, "mark_rescue", False
        sq = dict(ARMABLE, armed=0, orders=[{"order": "station", "x": 104, "y": 100, "z": 168}])
        self.guard(ov, game, 159.2, squad=sq)
        self.assertFalse([e for e in self.logs("mark_stand_down") if e.get("why") == "clear_wait"])

    def test_none_keeps_the_old_gate(self):
        old = harness.MUSTER_CLEAR_TILES
        harness.MUSTER_CLEAR_TILES = None
        self.addCleanup(setattr, harness, "MUSTER_CLEAR_TILES", old)
        ov, game = self.ov([KEA_OVER_FORT])
        self.assertIn(FOOT, self.guard(ov, game, 156))


if __name__ == "__main__":
    unittest.main()
