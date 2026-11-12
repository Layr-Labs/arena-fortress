"""cx office valid (probe lt82he on 7c1f7e7 std LT08-2: no office days 0-12, 0 orders validated): the office goes on
the open A site until a closed office room is dug, then moves there; the office room is wanted ahead of the surge's
dorm rooms; the model's own new surface stair waits for a free cover and the ENTRANCE_MAX cap.
Fixture: tests/test_closed_sites.py (LT08-2 z104 shapes). No game or network."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_closed_sites import A1, A9, R1, R2, S1, Quiet  # noqa: E402

OPEN_OFFICE = {"id": 7, "type": "Office", "x": 83, "y": 67, "z": 104, "w": 2, "h": 2, "owner": 92,
               "furniture": {"chair": 1}}
R2_DUG = dict(R2, designated=True, dug=True)


class OfficeMove(Quiet):
    def test_an_open_ground_office_moves_into_the_dug_office_room(self):
        agent, game = self.agent([A1, R1, R2_DUG])
        agent.zones = [dict(OPEN_OFFICE)]
        agent.adm["manager_office"] = {"zone_id": 7, "chair": True}
        agent.roles.update(R1="dorm", R2="office")
        agent.office()
        self.assertEqual(game.calls, [("make_zone", {"kind": "office", "site": "R2"}),
                                      ("assign_zone", {"zone_id": 50, "dwarf_id": 92}),
                                      ("place_furniture", {"kind": "chair", "site": "R2"})])

    def test_the_old_open_office_is_released_in_the_pass_it_moves(self):
        # cx audit (std LT08-2 on 642f253: the manager's ManageWorkOrders looks all stood on the open-ground office):
        # once the room office is the manager's, the open one goes to a citizen without a position
        agent, game = self.agent([A1, R1, R2_DUG])
        agent.zones = [dict(OPEN_OFFICE)]
        agent.adm["manager_office"] = {"zone_id": 7, "chair": True}
        agent.roles.update(R1="dorm", R2="office")
        real = game.act

        def act(tool, args):
            r = real(tool, args)
            if tool == "make_zone" and r.get("ok"):
                r = dict(r, result=dict(r["result"], at=[R2["x"], R2["y"], R2["z"], 3, 3]))
            return r
        game.act = act
        agent.office()
        self.assertEqual(game.calls[-1], ("assign_zone", {"zone_id": 7, "dwarf_id": 93}))

    def test_two_owned_offices_the_open_one_is_released(self):
        agent, game = self.agent([A1, R1, R2_DUG])
        agent.zones = [dict(OPEN_OFFICE), dict(OPEN_OFFICE, id=9, x=94, y=93, w=3, h=3)]   # 9: on the dug R2
        agent.adm["manager_office"] = {"zone_id": 7, "chair": True}
        # cx lt082beds: R2's level opens onto the open floor (the fixture, as LT08-2's ramps), so office_open reads
        # zone 9 open by the level rule; it stays as the dug office room (office_on_room)
        agent.roles["R2"] = "office"
        agent.office()
        self.assertEqual(game.calls, [("assign_zone", {"zone_id": 7, "dwarf_id": 93})])
        # only open offices go, and only while a closed one is the manager's
        agent2, game2 = self.agent([A1, R1, R2_DUG])
        agent2.zones = [dict(OPEN_OFFICE), dict(OPEN_OFFICE, id=9, x=84)]
        agent2.adm["manager_office"] = {"zone_id": 7, "chair": True}
        agent2.office()
        self.assertNotIn(("assign_zone", {"zone_id": 7, "dwarf_id": 93}), game2.calls)

    def test_a_closed_office_stays(self):
        agent, game = self.agent([A9, R1, R2_DUG])
        agent.zones = [dict(OPEN_OFFICE, x=60, y=60, z=103)]
        agent.adm["manager_office"] = {"zone_id": 7, "chair": True}
        agent.roles.update(R1="dorm", R2="office")
        agent.office()
        self.assertEqual(game.calls, [])

    def test_the_open_office_without_a_room_wants_one(self):
        agent, game = self.agent([A1, R1, R2])
        agent.zones = [dict(OPEN_OFFICE)]
        agent.roles["R1"] = "dorm"
        self.assertTrue(agent.office_wants_room())
        agent.roles["R2"] = "office"
        self.assertFalse(agent.office_wants_room())
        agent2, _ = self.agent([A9, R1, R2])
        agent2.zones = [dict(OPEN_OFFICE, x=60, y=60, z=103)]
        self.assertFalse(agent2.office_wants_room())


class YieldMove(Quiet):
    # cx audit: while the open-ground office is yielded (a big beast near it), a closed place standing ready takes the
    # manager's office instead of the orders waiting out the beast's stay
    YIELDED = dict(OPEN_OFFICE, owner=93)

    def yielded(self, sites, others=()):
        agent, game = self.agent(sites, others=others)
        agent.zones = [dict(self.YIELDED)]
        agent.office_yield = {"zone": 7, "holder": 93, "since": agent.now, "clear": None}
        return agent, game

    def test_a_dug_office_room_takes_the_office_during_the_yield(self):
        r9 = {"id": "R9", "kind": "R", "x": 60, "y": 60, "z": 103, "w": 3, "h": 3, "designated": True, "dug": True}
        agent, game = self.yielded([A1, R1, r9])
        agent.roles.update(R1="dorm", R9="office")
        agent.office()
        self.assertEqual(game.calls[:2], [("make_zone", {"kind": "office", "site": "R9"}),
                                          ("assign_zone", {"zone_id": 50, "dwarf_id": 92})])
        self.assertIsNone(agent.office_yield)

    def test_a_room_whose_level_opens_onto_open_ground_is_not_taken(self):
        # R2 on z104 opens onto the valley floor (as LT08-2's R2 onto its ramps): the yield holds
        agent, game = self.yielded([A1, R1, R2_DUG])
        agent.roles.update(R1="dorm", R2="office")
        agent.office()
        self.assertEqual(game.calls, [])
        self.assertIsNotNone(agent.office_yield)

    def test_a_closed_a_site_too_and_nothing_without_one(self):
        agent, game = self.yielded([A1, R1, A9])
        agent.office()
        self.assertEqual(game.calls[0], ("make_zone", {"kind": "office", "site": "A9"}))
        agent2, game2 = self.yielded([A1, R1, R2])
        agent2.office()
        self.assertEqual(game2.calls, [])                 # only open ground: the yield holds as before
        self.assertIsNotNone(agent2.office_yield)

    def test_not_next_to_a_big_beast(self):
        gator = {"id": 700, "race": "ALLIGATOR", "x": 62, "y": 62, "z": 103}
        agent, game = self.yielded([A1, R1, A9], others=[gator])
        agent.office()
        self.assertEqual(game.calls, [])


class SmallOpenSite(Quiet):
    # cx audit: an open A site under make_zone's ZONE_MAX (no wide site for office_box, no closed place, no dug office
    # room) — HEAD made no temporary office at all, so manager_office stayed "none" until the office room was dug
    SMALL = dict(A1, id="A3", w=10, h=12)   # z104 rows 67-78: open valley floor

    def test_the_small_open_site_takes_the_temporary_office_at_once(self):
        agent, game = self.agent([self.SMALL, R1, R2])
        agent.roles["R1"] = "dorm"
        agent.office()
        self.assertIn(("dig_room", {"site": "R2", "w": 9, "h": 7}), game.calls)   # the closed room is dug too
        self.assertIn(("make_zone", {"kind": "office", "site": "A3"}), game.calls)
        self.assertIn(("place_furniture", {"kind": "chair", "site": "A3"}), game.calls)
        self.assertIn(("assign_zone", {"zone_id": 50, "dwarf_id": 92}), game.calls)

    def test_before_the_first_dorm_too(self):
        agent, game = self.agent([self.SMALL, R2])
        agent.office()
        self.assertIn(("make_zone", {"kind": "office", "site": "A3"}), game.calls)

    def test_its_chair_comes_later_under_the_temporary_key(self):
        agent, game = self.agent([self.SMALL, R1, R2])
        agent.zones = [dict(OPEN_OFFICE, id=8, x=83, y=67, furniture={})]
        agent.office()
        self.assertIn(("place_furniture", {"kind": "chair", "site": "A3"}), game.calls)

    def test_a_wide_site_keeps_office_box_and_a_small_fort_keeps_waiting(self):
        agent, game = self.agent([A1, self.SMALL, R1, R2])
        agent.roles["R1"] = "dorm"
        agent.office()
        self.assertNotIn(("make_zone", {"kind": "office", "site": "A3"}), game.calls)
        agent2, game2 = self.agent([self.SMALL, R1, R2])
        agent2.load(game2.observe(cit=9))
        agent2.days = 216
        agent2.office()
        self.assertEqual([c for c in game2.calls if c[1].get("site") == "A3"], [])


class ModelStairs(Quiet):
    def entrances(self, agent, n):
        agent.entrances = {"E%d" % i: (80 + i, 120, 105) for i in range(1, n + 1)}

    def test_no_new_stair_past_the_cap_or_without_a_spare_cover(self):
        agent, _ = self.agent([A1, R1, S1])
        self.entrances(agent, 1)
        agent.o["doors"] = {"hatch_cover_items_free": 1, "list": []}
        self.assertIn("hatch cover", agent.open_refusal("dig_stairs", {"site": "S1"}))   # E1's own cover only
        agent.o["doors"] = {"hatch_cover_items_free": 2, "list": []}
        self.assertIsNone(agent.open_refusal("dig_stairs", {"site": "S1"}))
        self.entrances(agent, 4)
        agent.o["doors"] = {"hatch_cover_items_free": 9, "list": []}
        self.assertIn("surface entrances", agent.open_refusal("dig_stairs", {"site": "S1"}))


if __name__ == "__main__":
    unittest.main()
