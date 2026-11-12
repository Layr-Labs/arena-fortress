"""cx room claim: the far meeting area keeps priority; the private-bedroom planners keep off its box. Measured: hint hard
MY1-4 on e33d381 dug R3 (x94-96 y90-92 z168) for citizen 241 on day 7 (dig_bedroom_R3); on day 26 the far meeting area
went on A5 4x6 (A5's corner is R3) and bedroom_zone_241 answered "site_used: room R3 is already used (MeetingHall 72)";
750 of that meeting area's 819 idle looks after day 26 stood on R3's tiles, and the fort scored 100 (wellbeing 1.00)
without the bedroom. The geometry is the record's (day-3 and day-26 observations, the d57f599 real map of the fort).
No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_danger_marks import Quiet  # noqa: E402
from test_rescue_station import E1  # noqa: E402
from test_meeting_shaft import MapGame, look, A2, DORM  # noqa: E402
from overseer import harness  # noqa: E402

A4_DAY3 = {"id": "A4", "kind": "A", "x": 97, "y": 91, "z": 168, "w": 15, "h": 12, "open_tiles": 44, "subterranean": True}
A5 = {"id": "A5", "kind": "A", "x": 94, "y": 90, "z": 168, "w": 18, "h": 13, "open_tiles": 62, "subterranean": True}
R2_UNDUG = {"id": "R2", "kind": "R", "x": 98, "y": 90, "z": 168, "w": 3, "h": 3, "designated": False, "dug": False}
R3_UNDUG = {"id": "R3", "kind": "R", "x": 94, "y": 90, "z": 168, "w": 3, "h": 3, "designated": False, "dug": False}
R3 = dict(R3_UNDUG, designated=True, dug=True, free=True, soil=True)
# a room off the meeting / dining boxes (a level with no A site yet) and MEETING_SHAFT_TILES off the E1 column
R9 = {"id": "R9", "kind": "R", "x": 110, "y": 86, "z": 166, "w": 3, "h": 3, "designated": False, "dug": False}
NEAR_MEET = {"id": 71, "type": "MeetingHall", "x": 95, "y": 100, "z": 167, "w": 3, "h": 3}
BEDROOM_R3 = {"id": 90, "type": "Bedroom", "owner": 241, "x": 94, "y": 90, "z": 168, "w": 3, "h": 3}
PEOPLE = [{"id": 241, "stress": 4, "adult": True, "x": 96, "y": 91, "z": 168}]


class ZoneMapGame(MapGame):
    def act(self, tool, args):
        r = super().act(tool, args)
        if tool == "make_zone":
            return {"ok": True, "result": {"zone_id": 800 + len(self.calls), "zone": args.get("kind"),
                                           "at": [94, 90, 168, args.get("w", 3), args.get("h", 3)]}}
        return r


class Base(Quiet):
    def ov(self, sites, zones=(NEAR_MEET, DORM), day=26, people=PEOPLE, stress=4):
        game = ZoneMapGame([])
        game.grid = "hard_my1_4_d57f599_day17"
        r = look(day, (E1,) + tuple(sites), zones=zones)
        r["observation"]["dwarves"] = [dict(p, stress=stress) for p in people]
        r["observation"]["stocks"]["furniture_free"] = {"bed": 2}
        ov = harness.Overseer(game, days=216)
        ov.load(r)
        ov.count = 0
        game.calls.clear()
        return ov, game

    def calls(self, game, tool, kind=None):
        return [a for t, a in game.calls if t == tool and (kind is None or a.get("kind") == kind)]


class BedroomYields(Base):
    def test_day26_the_far_meeting_area_takes_A5_and_the_bedroom_keeps_off_R3(self):
        ov, game = self.ov((A2, A5, R3))
        self.assertTrue(ov.under_people(R3))
        self.assertNotEqual((ov.stress_site() or {}).get("id"), "R3")
        ov.house_everyone()
        self.assertEqual(self.calls(game, "make_zone", "bedroom"), [])
        ov.meeting_far()
        (meet,) = self.calls(game, "make_zone", "meeting_area")
        self.assertEqual(meet["site"], "A5")
        box = dict(A5, w=meet.get("w", A5["w"]), h=meet.get("h", A5["h"]))
        self.assertGreaterEqual(ov.shaft_gap(box), harness.MEETING_SHAFT_TILES)

    def test_stressed_citizen_waits_too(self):
        ov, game = self.ov((A2, A5, R3), stress=1)
        ov.stress_housing()
        self.assertEqual(self.calls(game, "make_zone", "bedroom"), [])

    def test_day3_no_dig_for_a_room_the_far_cut_will_take(self):
        # A4 at x97 y91: once R3 / R2 are dug the level's A site corner moves onto them (A5 at x94 y90)
        ov, game = self.ov((A2, A4_DAY3, R2_UNDUG, R3_UNDUG), zones=(DORM,), day=3)
        self.assertTrue(ov.people_later(R3_UNDUG))
        self.assertTrue(ov.people_later(R2_UNDUG))
        ov.house_everyone()
        self.assertEqual(self.calls(game, "dig_room"), [])   # it waits rather than take the meeting box

    def test_a_room_off_the_boxes_and_the_shaft_is_dug_instead(self):
        ov, game = self.ov((A2, A4_DAY3, R2_UNDUG, R3_UNDUG, R9), zones=(DORM,), day=3)
        self.assertFalse(ov.people_later(R9))
        self.assertFalse(ov.room_near_shaft(R9))
        ov.house_everyone()
        self.assertEqual([a["site"] for a in self.calls(game, "dig_room")], ["R9"])

    def test_off_a_shaft_fort_nothing_changes(self):
        ov, _ = self.ov((A2, A5, R3))
        ov.shaft_people = lambda: False
        self.assertEqual(ov.people_boxes(), [])
        self.assertFalse(ov.people_later(R3_UNDUG))
        self.assertEqual((ov.stress_site() or {}).get("id"), "R3")


class BedroomZoneGuard(Base):
    def test_a_standing_bedroom_is_protected(self):
        ov, game = self.ov((A2, A5, R3), zones=(NEAR_MEET, DORM, BEDROOM_R3))
        for key, tool, args in (("z1", "make_zone", {"kind": "dining_hall", "site": "A5", "w": 4, "h": 6}),
                                ("z2", "make_zone", {"kind": "meeting_area", "site": "A5", "w": 4, "h": 6}),
                                ("f1", "build_farm", {"site": "R3"}),
                                ("p1", "place_furniture", {"kind": "table", "site": "A5", "w": 4, "h": 6})):
            self.assertEqual((ov.act(key, tool, args) or {}).get("error_code"), "room_reserved", key)
        self.assertEqual(game.calls, [])
        self.assertNotEqual((ov.act("b1", "place_furniture", {"kind": "bed", "site": "R3", "count": 1})
                             or {}).get("error_code"), "room_reserved")

    def test_a_merely_dug_room_is_not_protected(self):
        ov, game = self.ov((A2, A5, R3))
        ov.roles["R3"] = "bedroom"
        r = ov.act("z2", "make_zone", {"kind": "meeting_area", "site": "A5", "w": 4, "h": 6})
        self.assertNotEqual((r or {}).get("error_code"), "room_reserved")
        self.assertEqual(len(self.calls(game, "make_zone", "meeting_area")), 1)

    def test_a_zone_made_this_pass_is_seen_by_later_pickers(self):
        ov, _ = self.ov((A2, A5, R3))
        ov.shaft_people = lambda: False   # off the claim: only the same-pass zone keeps R3 out
        n = len(ov.zones)
        ov.act("zz", "make_zone", {"kind": "dining_hall", "site": "A5", "w": 4, "h": 6})
        self.assertEqual(len(ov.zones), n + 1)
        self.assertEqual({k: ov.zones[-1][k] for k in ("type", "x", "y", "z", "w", "h")},
                         {"type": "DiningHall", "x": 94, "y": 90, "z": 168, "w": 4, "h": 6})
        self.assertNotEqual((ov.stress_site() or {}).get("id"), "R3")

    def test_the_models_own_call_gets_room_reserved(self):
        from test_autolabor_refusal import runner, Game
        ov, _ = self.ov((A2, A5, R3), zones=(NEAR_MEET, DORM, BEDROOM_R3))
        r = runner(Game())
        r.guard = ov
        out = r.refuse("make_zone", {"kind": "meeting_area", "site": "A5", "w": 4, "h": 6}, None)
        self.assertEqual((out or {}).get("error_code"), "room_reserved")
        self.assertIsNone(r.refuse("place_furniture", {"kind": "bed", "site": "R3", "count": 1}, None))


if __name__ == "__main__":
    unittest.main()
