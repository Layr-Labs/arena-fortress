"""h4: on an open task the expedition leader gets an office of his own in a dug room, after the manager's office has
its chair; a lab makes none, and nothing is made for a leader who is the manager."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import resp  # noqa: E402
from test_d33 import ZoneGame, with_game  # noqa: E402
from test_d38 import RefuseChairGame, office_zone  # noqa: E402
from overseer import harness as H  # noqa: E402

MGR_ROOM = {"id": "R1", "kind": "R", "x": 97, "y": 97, "z": 157, "w": 3, "h": 3, "dug": True}
ROOM = {"id": "R2", "kind": "R", "x": 101, "y": 97, "z": 157, "w": 3, "h": 3, "dug": True}
ROOM3 = {"id": "R3", "kind": "R", "x": 105, "y": 97, "z": 157, "w": 3, "h": 3, "dug": True}
UNDUG = {"id": "R4", "kind": "R", "x": 109, "y": 97, "z": 157, "w": 3, "h": 3, "dug": False, "designated": False}
LT01 = ("From day 39 you can't act for 21 days. Keep drink in stock every day of that window, brew at least one batch "
        "of drink inside it, and end with at least one drink per dwarf. No dwarf may die.")


def mgr_office(chair=True):
    z = office_zone(600, MGR_ROOM, owner=5)
    z["furniture"] = {"chair": 1} if chair else {}
    return z


def fort(sites, zones=(), chairs=1, day=6, leader=9, manager=5, days=216):
    r = resp(days - day, day, food=60, cit=9)
    o = r["observation"]
    o["administrators"].update(MANAGER_id=manager, manager_office="none")
    if leader is not None:
        o["administrators"]["EXPEDITION_LEADER_id"] = leader
    o["map"].update(surface_z=161, sites=[dict(s) for s in sites])
    o["zones"] = [dict(z) for z in zones]
    o["stocks"]["furniture_free"] = {"chair": chairs}
    return r


class LeaderOffice(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_office_zone_chair_and_assignment_in_a_free_dug_room(self):
        g = ZoneGame()
        ov = with_game(fort([MGR_ROOM, ROOM], [mgr_office()]), g)
        ov.roles["R1"] = "office"
        ov.leader_office()
        self.assertEqual(g.tools("make_zone"), [{"kind": "office", "site": "R2"}])
        self.assertEqual([a["dwarf_id"] for a in g.tools("assign_zone")], [9])
        self.assertEqual(g.tools("place_furniture"), [{"kind": "chair", "site": "R2"}])
        self.assertEqual(ov.roles["R2"], "lead")
        self.assertIn("R2", ov.office_zoned)

    def test_the_managers_zone_comes_first_and_his_chair_before_the_leaders(self):
        g = ZoneGame()
        ov = with_game(fort([MGR_ROOM, ROOM], []), g)                    # no manager's office zone yet: nothing
        ov.leader_office()
        self.assertEqual(g.calls, [])
        ov = with_game(fort([MGR_ROOM, ROOM], [mgr_office(chair=False)]), g)   # his zone stands: the leader's is made,
        ov.leader_office()                                                     # but the free chair is the manager's
        self.assertEqual(g.tools("make_zone"), [{"kind": "office", "site": "R2"}])
        self.assertEqual([a["dwarf_id"] for a in g.tools("assign_zone")], [9])
        self.assertEqual(g.tools("place_furniture"), [])

    def test_a_room_another_zone_took_is_given_up_and_one_more_is_dug(self):
        taken = dict(ROOM, free=False, used_by=["DiningHall 59"])
        g = ZoneGame()
        ov = with_game(fort([MGR_ROOM, taken, dict(UNDUG)], [mgr_office()]), g)
        ov.roles.update(X1="dorm", X2="dine", R1="office", R2="lead")
        ov.leader_office()
        self.assertEqual(ov.roles["R2"], "lead_lost")
        self.assertEqual(g.tools("make_zone"), [])
        ov.digging()
        self.assertEqual(g.tools("dig_room"), [{"site": "R4"}])
        self.assertEqual(ov.roles["R4"], "lead")
        ov.roles["R4"] = "lead_lost"                                     # the second one lost too: no third room
        ov.load(fort([MGR_ROOM, taken, dict(UNDUG, id="R6")], [mgr_office()], day=9))
        ov.count = 0
        ov.digging()
        self.assertEqual(len(g.tools("dig_room")), 1)

    def test_no_second_zone_while_the_zone_list_lags(self):
        g = ZoneGame()
        ov = with_game(fort([MGR_ROOM, ROOM, ROOM3], [mgr_office()]), g)
        ov.leader_office()
        ov.load(fort([MGR_ROOM, ROOM, ROOM3], [mgr_office()], day=7))    # the next day's list does not show it yet
        ov.count = 0
        ov.leader_office()
        self.assertEqual([a["site"] for a in g.tools("make_zone")], ["R2"])

    def test_never_on_the_managers_room_or_twice(self):
        g = ZoneGame()
        ov = with_game(fort([MGR_ROOM], [mgr_office()]), g)       # the only dug room holds the manager's office
        ov.leader_office()
        self.assertEqual(g.calls, [])
        zones = [mgr_office(), dict(office_zone(601, ROOM, owner=9), furniture={"chair": 1})]
        ov = with_game(fort([MGR_ROOM, ROOM, ROOM3], zones), g)   # he has his office: nothing more
        ov.leader_office()
        self.assertEqual(g.calls, [])

    def test_chair_goes_to_his_zone_when_one_is_free_and_is_ordered_when_none_is(self):
        zones = [mgr_office(), office_zone(601, ROOM, owner=9)]
        g = ZoneGame()
        ov = with_game(fort([MGR_ROOM, ROOM], zones, chairs=1), g)
        ov.leader_office()
        self.assertEqual(g.tools("place_furniture"), [{"kind": "chair", "site": "R2"}])
        ov = with_game(fort([MGR_ROOM, ROOM], zones, chairs=0), ZoneGame())
        ov.leader_office()
        self.assertEqual(ov.game.calls, [])
        self.assertTrue(ov.office_chair_needed())
        ov = with_game(fort([MGR_ROOM, ROOM], [mgr_office()], chairs=0), ZoneGame())   # no zone of his yet: no chair
        self.assertFalse(ov.office_chair_needed())

    def test_an_unowned_office_is_assigned_to_him(self):
        g = ZoneGame()
        ov = with_game(fort([MGR_ROOM, ROOM], [mgr_office(), office_zone(601, ROOM, owner=None)]), g)
        ov.leader_office()
        self.assertEqual(g.tools("assign_zone"), [{"zone_id": 601, "dwarf_id": 9}])
        self.assertEqual(g.tools("make_zone"), [])

    def test_a_refused_chair_gives_the_site_up_and_two_zones_are_the_most(self):
        g = RefuseChairGame(full={"R2", "R3"})
        ov = with_game(fort([MGR_ROOM, ROOM, ROOM3], [mgr_office()]), g)
        ov.leader_office()
        self.assertIn("R2", ov.office_bad)
        ov.load(fort([MGR_ROOM, ROOM, ROOM3], [mgr_office()], day=10))
        ov.count = 0
        ov.leader_office()
        ov.load(fort([MGR_ROOM, ROOM, ROOM3, dict(UNDUG, dug=True)], [mgr_office()], day=14))
        ov.count = 0
        ov.leader_office()
        self.assertEqual([a["site"] for a in g.tools("make_zone")], ["R2", "R3"])

    def test_no_leader_or_leader_is_the_manager_or_a_lab(self):
        for r in (fort([MGR_ROOM, ROOM], [mgr_office()], leader=None),
                  fort([MGR_ROOM, ROOM], [mgr_office()], leader=5)):
            g = ZoneGame()
            ov = with_game(r, g)
            ov.leader_office()
            self.assertEqual(g.calls, [])
            self.assertFalse(ov.leader_wants_office())
        g = ZoneGame()
        r = fort([MGR_ROOM, ROOM], [mgr_office()], days=60)
        r["hands_off_in_days"] = 33
        ov = with_game(r, g)
        ov.set_task({"goal": LT01, "hands_off": {"from_day": 39}})
        ov.load(r)
        ov.count = 0
        ov.leader_office()
        self.assertEqual(g.calls, [])

    def test_one_more_room_is_dug_for_it(self):
        g = ZoneGame()
        ov = with_game(fort([dict(UNDUG)], [mgr_office()]), g)
        ov.roles.update(X1="dorm", X2="dine", X3="office")
        ov.digging()
        self.assertEqual(g.tools("dig_room"), [{"site": "R4"}])
        self.assertEqual(ov.roles["R4"], "lead")
        ov = with_game(fort([dict(UNDUG)], [mgr_office()], leader=None), ZoneGame())
        ov.roles.update(X1="dorm", X2="dine", X3="office")
        ov.digging()
        self.assertEqual(ov.game.tools("dig_room"), [])

    def test_manager_adopts_a_spare_without_losing_it_in_the_same_pass(self):
        zones = [mgr_office(chair=False), office_zone(601, ROOM, owner=None)]
        g = ZoneGame()
        ov = with_game(fort([ROOM], zones), g)
        ov.adm["manager_office"] = {"zone_id": 600, "chair": False}
        ov.office()
        ov.leader_office()
        self.assertEqual(g.tools("assign_zone"), [{"zone_id": 601, "dwarf_id": 5}])

    def test_leader_waits_while_the_manager_is_vacant(self):
        g = ZoneGame()
        ov = with_game(fort([ROOM], manager=None), g)
        ov.leader_office()
        self.assertEqual(g.calls, [])


if __name__ == "__main__":
    unittest.main()
