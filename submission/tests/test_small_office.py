"""cx small fort office (hint MY1-3: 9 citizens at the handover, the manager's office "none" until the day-51 / day-76
migrant wave or never — office() waited for 14 citizens). Below OFFICE_FULL_CIT the office is made on a ready closed
place only (a closed A site, a dug office room, an unowned office zone); no open-ground temporary office and no dig.
Fixture: tests/test_closed_sites.py (LT08-2 z104 shapes, z103 all dug). No game or network."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_closed_sites import A1, A9, R1, R2, Quiet, harness  # noqa: E402

A8 = dict(A9, id="A8", x=70)   # a second closed dug box on z103
R2_DUG = dict(R2, designated=True, dug=True)
OPEN_OFFICE = {"id": 7, "type": "Office", "x": 83, "y": 67, "z": 104, "w": 2, "h": 2, "owner": 92,
               "furniture": {"chair": 1}}


class SmallFortOffice(Quiet):
    def small(self, sites, cit=9):
        agent, game = self.agent(sites)
        agent.days = 216                                 # MY1: open play shorter than a year (my1_plan)
        obs = game.observe(day=0, cit=cit)
        obs.pop("hands_off_in_days")                     # MY1 has no hands-off window
        agent.load(obs)
        self.assertLess(agent.cit, harness.OFFICE_FULL_CIT)
        self.assertTrue(agent.my1_plan())
        return agent, game

    def test_nine_citizens_get_the_office_on_a_closed_site_at_once(self):
        agent, game = self.small([A1, R1, A9])
        agent.office()
        self.assertEqual(game.calls[:2], [("make_zone", {"kind": "office", "site": "A9"}),
                                          ("place_furniture", {"kind": "chair", "site": "A9"})])
        # cx small office assign (e20ce56 std MY1-3 probe: made d0, assigned d5): the manager's in the same pass
        self.assertEqual(len(game.calls), 3)
        self.assertEqual(game.calls[2][0], "assign_zone")
        self.assertEqual(game.calls[2][1]["dwarf_id"], 92)
        self.assertEqual(game.calls[2][1]["zone_id"], 50)   # the id make_zone returned

    def test_no_same_pass_assign_while_a_big_beast_is_near(self):
        # cx smalloffice3: the made zone is not handed to the manager while office_beasts sees a big beast at its box
        agent, game = self.small([A1, R1, A9])
        seen = []
        agent.office_beasts = lambda zone, rules=None: seen.append(dict(zone)) or [("bear", 0, 0, 103, 5)]
        agent.office()
        self.assertEqual([t for t, _ in game.calls], ["make_zone", "place_furniture"])
        self.assertEqual({k: seen[0].get(k) for k in ("x", "y", "z")}, {k: A9[k] for k in ("x", "y", "z")})
        agent2, game2 = self.small([A1, R1, A9])
        agent2.office_beasts = lambda zone, rules=None: []
        agent2.office()
        self.assertIn("assign_zone", [t for t, _ in game2.calls])

    def test_the_new_office_is_not_handed_to_the_stressed_leader_in_the_same_pass(self):
        # cx audit: make_zone answers its box ("at"), so the zone joins self.zones this pass; its same-pass owner must
        # too, or stress_noble_office takes it as an unowned spare for the expedition leader
        agent, game = self.small([A1, R1, A9])
        agent.adm["EXPEDITION_LEADER_id"] = 93
        real = game.act

        def act(tool, args):
            r = real(tool, args)
            if tool == "make_zone" and r.get("ok"):
                r = dict(r, result=dict(r["result"], at=[A9["x"], A9["y"], A9["z"], 5, 5]))
            return r
        game.act = act
        agent.office()
        self.assertIn(("assign_zone", {"zone_id": 50, "dwarf_id": 92}), game.calls)
        agent.stress_noble_office({"id": 93})
        self.assertNotIn(("assign_zone", {"zone_id": 50, "dwarf_id": 93}), game.calls)
        self.assertEqual(agent.zone_of("office", 92) is not None, True)

    def test_no_assign_when_the_zone_was_refused(self):
        agent, game = self.small([A1, R1, A9])
        real = game.act
        game.act = lambda tool, args: ({"ok": False, "error": {"code": "no_space"}} if tool == "make_zone"
                                       else real(tool, args))
        agent.office()
        self.assertNotIn("assign_zone", [t for t, _ in game.calls])

    def test_a_spare_office_zone_is_assigned_below_the_full_count(self):
        agent, game = self.small([A1, R1, A9])
        agent.zones = [{"id": 12, "type": "Office", "x": 60, "y": 60, "z": 103, "w": 3, "h": 3}]
        agent.office()
        self.assertEqual(game.calls, [("assign_zone", {"zone_id": 12, "dwarf_id": 92})])

    def test_no_open_ground_office_and_no_dig_below_the_full_count(self):
        agent, game = self.small([A1, R1, R2])
        agent.roles["R1"] = "dorm"
        agent.office()
        self.assertEqual(game.calls, [])                 # A1 is open valley floor: nothing ready, nothing dug
        self.assertFalse(agent.office_wants_room())
        agent.digging()
        self.assertNotIn("dig_office_room", [k for k in agent.tries])
        self.assertNotIn("office", agent.roles.values())

    def test_an_open_office_waits_for_the_full_count_to_dig_but_moves_into_a_dug_room(self):
        agent, game = self.small([A1, R1, R2])
        agent.zones = [dict(OPEN_OFFICE)]
        agent.adm["manager_office"] = {"zone_id": 7, "chair": True}
        agent.roles["R1"] = "dorm"
        agent.office()
        self.assertEqual(game.calls, [])                 # no office_room dig below the full count
        agent2, game2 = self.small([A1, R1, R2_DUG])
        agent2.zones = [dict(OPEN_OFFICE)]
        agent2.adm["manager_office"] = {"zone_id": 7, "chair": True}
        agent2.roles.update(R1="dorm", R2="office")
        agent2.office()
        self.assertEqual(game2.calls[0], ("make_zone", {"kind": "office", "site": "R2"}))

    def test_a_closed_box_away_from_the_open_shaft_comes_first(self):
        agent, game = self.small([A1, R1, A9, A8])
        agent.shaft_people = lambda: True
        agent.shaft_near = lambda box: box.get("id") == "A8"
        agent.office()
        self.assertEqual(game.calls[0], ("make_zone", {"kind": "office", "site": "A9"}))
        agent2, game2 = self.small([A1, R1, A8, A9])
        agent2.shaft_people = lambda: True
        agent2.shaft_near = lambda box: box.get("id") == "A8"
        agent2.office()
        self.assertEqual(game2.calls[0], ("make_zone", {"kind": "office", "site": "A9"}))

    def test_a_wide_site_read_closed_takes_the_office_box(self):
        wide = dict(A9, id="A7", w=25, h=25)          # past make_zone's ZONE_MAX, all dug (z103)
        agent, game = self.small([A1, R1, wide])
        agent.office()
        self.assertEqual(game.calls[0], ("place_furniture", {"kind": "chair", "site": "A7", "w": 20, "h": 20}))
        self.assertFalse([c for c in game.calls if c[1].get("site") == "A1"])

    def test_the_full_count_keeps_its_behaviour(self):
        agent, game = self.agent([A1, R1, A9])           # 40 citizens
        agent.office()
        self.assertEqual(game.calls[0], ("make_zone", {"kind": "office", "site": "A9"}))

    def test_a_full_year_small_fort_keeps_waiting(self):
        agent, game = self.small([A1, R1, A9])
        agent.days = 336                                 # OP1: the full year keeps its own path
        agent.office()
        self.assertEqual(game.calls, [])

    def test_no_citizens_or_no_manager_no_office(self):
        agent, game = self.small([A1, R1, A9])
        agent.adm["manager_active_for_orders"] = False
        agent.office()
        agent.cit = 0
        agent.adm["manager_active_for_orders"] = True
        agent.office()
        self.assertEqual(game.calls, [])


if __name__ == "__main__":
    unittest.main()
