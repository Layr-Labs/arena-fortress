"""cx closed fallback (after 941b64a): the people pickers see only closed A sites, the meeting area and the dining
hall get a dug room when an open A site left them without a place, and a closed-room Shelter grows with the census.
Fixture: tests/test_closed_sites.py (LT08-2 z104 light shapes). No game or network."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_closed_sites import A1, A9, R1, R2, Quiet  # noqa: E402
from overseer import harness  # noqa: E402

R1_DUG = dict(R1)
R3 = {"id": "R3", "kind": "R", "x": 90, "y": 100, "z": 104, "w": 3, "h": 3, "designated": False, "dug": False}


class ClosedA(Quiet):
    def test_pickers_see_only_closed_a_sites(self):
        agent, _ = self.agent([A1, A9, R1_DUG])
        self.assertEqual([s["id"] for s in agent.closed_a()], ["A9"])
        self.assertTrue(agent.open_a())
        agent2, _ = self.agent([A9])
        self.assertFalse(agent2.open_a())
        # the meeting fallback box and a private room never come from the open A1
        box = agent.meeting_box()
        self.assertTrue(box is None or box[0]["id"] != "A1")
        site = agent.stress_site(meeting=True)
        self.assertTrue(site is None or site["id"] != "A1")


class PeopleRooms(Quiet):
    def test_meeting_area_with_only_open_ground_digs_a_room_after_the_dorm(self):
        agent, game = self.agent([A1, R1_DUG, R2])
        self.assertIsNone(agent.people_room("meeting"))   # no dorm yet: the dorm comes first
        self.assertEqual(game.calls, [])
        agent.roles["R1"] = "dorm"
        agent.meeting_area()
        self.assertEqual([c for c in game.calls if c[0] == "dig_room"],
                         [("dig_room", {"site": "R2", "w": 9, "h": 7})])
        self.assertEqual(agent.roles["R2"], "meeting")
        # dug: the meeting zone goes on it
        agent.sites = [s for s in agent.sites if s["id"] != "R2"] + [dict(R2, designated=True, dug=True)]
        self.assertEqual(agent.stress_site(meeting=True)["id"], "R2")
        game.calls.clear()
        agent.meeting_area()
        self.assertEqual([c for c in game.calls if c[0] == "make_zone"],
                         [("make_zone", {"kind": "meeting_area", "site": "R2"})])

    def test_a_closed_level_keeps_the_old_meeting_path(self):
        agent, game = self.agent([A9, R1_DUG, R2])
        agent.roles["R1"] = "dorm"
        agent.meeting_area()
        self.assertEqual([c for c in game.calls if c[0] == "dig_room"], [])
        self.assertEqual([c[1].get("site") for c in game.calls if c[0] == "make_zone"], ["A9"])

    def test_one_room_per_role(self):
        agent, game = self.agent([A1, R1_DUG, R2, R3])
        agent.roles["R1"] = "dorm"
        self.assertEqual(agent.people_room("dine")["id"], "R2")
        self.assertIsNone(agent.people_room("dine"))
        self.assertEqual(agent.people_room("meeting")["id"], "R3")


class DiningRoom(Quiet):
    def test_no_dining_place_on_open_ground_digs_a_dine_room(self):
        game_sites = [A1, R1_DUG, R2]
        agent, game = self.agent(game_sites, goal="")
        o = game.observe()
        o["observation"]["stocks"]["furniture_free"] = {"table": 4, "chair": 4, "bed": 0}
        agent.load(o)
        agent.roles["R1"] = "dorm"
        agent.furnish()
        self.assertIn(("dig_room", {"site": "R2"}), game.calls)
        self.assertEqual(agent.roles["R2"], "dine")

    def test_a_surge_digs_no_dine_room_while_beds_are_short(self):
        agent, game = self.agent([A1, R1_DUG, R2])
        o = game.observe()
        o["observation"]["stocks"]["furniture_free"] = {"table": 4, "chair": 4, "bed": 0}
        agent.load(o)
        agent.roles["R1"] = "dorm"
        agent.furnish()
        self.assertNotIn("dine", agent.roles.values())


class ModelCalls(Quiet):
    def test_the_models_own_calls_get_the_closed_site_rules(self):
        from test_autolabor_refusal import runner, Game
        from test_closed_sites import S1
        agent, game = self.agent([A1, A9, R1_DUG, S1],
                                 others=[{"id": 113, "race": "ALLIGATOR", "x": 75, "y": 94, "z": 104}])
        r = runner(Game())
        r.guard = agent
        for name, args in (("make_zone", {"kind": "dormitory", "site": "A1", "w": 3, "h": 2}),
                           ("place_furniture", {"kind": "bed", "site": "A1", "count": 4}),
                           ("create_burrow", {"site": "A1"})):
            with self.subTest(name=name):
                self.assertEqual((r.refuse(name, args, None) or {}).get("error_code"), "site_open")
        # cx model stairs: no cover in hand for a new entrance comes first; with one, the beast near holds it
        self.assertEqual((r.refuse("dig_stairs", {"site": "S1"}, None) or {}).get("error_code"), "entrance_hold")
        agent.o["doors"] = {"hatch_cover_items_free": 2, "list": []}
        self.assertEqual((r.refuse("dig_stairs", {"site": "S1"}, None) or {}).get("error_code"), "beast_near")
        self.assertIsNone(r.refuse("make_zone", {"kind": "dormitory", "site": "A9"}, None))
        self.assertIsNone(r.refuse("place_furniture", {"kind": "bed", "site": "R1", "w": 9, "h": 7}, None))
        self.assertEqual(game.calls, [])


class ShelterGrowth(Quiet):
    def shelter(self, sites, cit=48):
        agent, game = self.agent(sites)
        agent.cit = cit
        agent.room_box["R1"] = {"x": 88, "y": 104, "z": 104, "w": 9, "h": 7}
        agent.roles["R1"] = "dorm"
        agent.shelter_grow()   # A1 skipped as open, R1 9x7 in: 63 tiles
        return agent, game

    def test_a_small_closed_room_shelter_digs_a_house_room_for_the_census(self):
        agent, game = self.shelter([A1, R1_DUG, R2, R3])
        self.assertEqual(agent.shelter_tiles(), 63)
        agent.shelter_room(0)
        digs = [c for c in game.calls if c[0] == "dig_room"]
        self.assertEqual(digs, [("dig_room", {"site": "R2", "w": 9, "h": 7})])
        self.assertEqual(agent.roles["R2"], "house")
        agent.shelter_room(0)   # one shelter room dug at a time
        self.assertEqual(len([c for c in game.calls if c[0] == "dig_room"]), 1)

    def test_enough_tiles_or_digs_in_progress_wait(self):
        agent, game = self.shelter([A1, R1_DUG, R2], cit=20)   # 63 >= 3 * 20
        agent.shelter_room(0)
        agent2, game2 = self.shelter([A1, R1_DUG, R2])
        agent2.shelter_room(40)   # a room's worth still designated
        self.assertEqual([c for c in game.calls + game2.calls if c[0] == "dig_room"], [])

    def test_a_closed_level_shelter_is_left_alone(self):
        # (cx enclosed: R1 on z104 runs out onto the fixture's open ground, so it is left out here — the closed A9
        # level alone holds the Shelter and nothing grows it)
        agent, game = self.agent([A9, R2])
        agent.cit = 48
        agent.shelter_grow()
        agent.shelter_room(0)
        self.assertEqual([c for c in game.calls if c[0] == "dig_room"], [])

    def test_no_spare_room_digs_no_new_shaft(self):
        agent, game = self.shelter([A1, R1_DUG])
        called = []
        agent.floor_stair = lambda key, kind: called.append((key, kind))
        agent.shelter_room(0)
        self.assertEqual(called, [])
        self.assertEqual([c for c in game.calls if c[0] in ("dig_room", "dig_stairs")], [])

if __name__ == "__main__":
    unittest.main()


class PeopleBoxesClosed(Quiet):
    """cx audit: on a shaft fort the private-room planners keep off the far meeting / dining boxes (people_boxes,
    b6927c2); since 8032c7a those pickers take closed A sites only, so an open A site's far cut is no one's box and
    must not hold a dug room off a stressed dwarf (stress_site answered None for the room under it)."""

    def test_an_open_site_s_far_cut_holds_no_room_off(self):
        import test_closed_sites as cs
        real = cs.light

        def light(x, y, z):
            if z == 104 and 85 <= x <= 87 and 70 <= y <= 72:
                return ".", "u"           # a dug room pocket inside the open valley's corner box
            return real(x, y, z)
        cs.light = light
        self.addCleanup(setattr, cs, "light", real)
        rx = {"id": "R7", "kind": "R", "x": 85, "y": 70, "z": 104, "w": 3, "h": 3, "designated": True, "dug": True}
        game = cs.FakeGame([cs.A1, cs.A9, rx])
        agent = harness.Overseer(game, goal="", days=60)
        agent.count = 0
        agent.load(game.observe(day=0))
        agent.shaft_people = lambda: True
        agent.shaft_gap = lambda box: 99
        self.assertNotIn("A1", [b.get("site") for b in agent.people_boxes()])
        self.assertIn("A9", [b.get("site") for b in agent.people_boxes()])   # a closed site's cut still holds
        self.assertEqual((agent.stress_site() or {}).get("id"), "R7")
