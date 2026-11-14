"""d64: four fixes from the code review of 13 November, each found in recorded local games.
1. layer_only gives an advance the game stopped early (a tripwire) a pass of its own on open play, within the day.
2. On open tasks the squad fights only a hostile within 45 tiles of the wagon, and only with every member armed.
3. A lockdown's hatch is opened for a citizen outside when every hostile, the API's included, is more than ADMIT_FAR
   from that hatch (before: never while an API hostile was within WILD_CLEAR of the wagon).
4. The office may take a farm-role room no plot uses once the fort has its plots (before: no office site at all on
   maps where every dug room had the farm role)."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import HATCH, Task, hold, overseer, resp, threat_resp  # noqa: E402
from overseer.harness import DAY  # noqa: E402
from overseer.openplay import ADMIT_FAR  # noqa: E402
from plain import harness  # noqa: E402

LOCK = {"locked": True, "door_id": 14}


class StopGame:
    """advance_days answers `stopped` for the scripted calls and then stays within the day; observe follows the clock.
    The game is over from day 106."""

    def __init__(self, stops=(), hands_off=None):
        self.day, self.tick, self.stops, self.hands_off, self.advances = 100, 100 * DAY, list(stops), hands_off, []

    def task(self):
        return {"tools": [], "manual": "", "task": {"name": "t", "days": 336}}

    def act(self, tool, args):
        if tool != "advance_days":
            return {"ok": True, "result": {}}
        self.advances.append(args["days"])
        stop = self.stops.pop(0) if self.stops else None
        if stop:
            self.tick += 300
            return {"ok": True, "day": self.day, "result": {"advanced_ticks": 300, "stopped": stop}}
        self.day += args["days"]
        self.tick = self.day * DAY
        return {"ok": True, "day": self.day, "result": {"advanced_ticks": args["days"] * DAY, "stopped": None}}

    def observe(self):
        r = resp(336 - self.day, self.day, food=60, hands_off=self.hands_off)
        r["tick"] = self.tick
        r["observation"]["date"]["abs_tick"] = self.tick
        if self.day >= 106:
            r["game_over"] = True
        return r

    def query(self, *a, **kw):
        return {"result": {"units": [], "total": 0}}


def passes(game):
    """The days on which the layer ran a pass during layer_only."""
    p = harness.Plain(Task(), game, model=None)
    days = []
    real = p.guard.step

    def step(r):
        days.append(r.get("day"))
        return real(r)
    p.guard.step = step
    p.layer_only("test")
    return days


def squad_resp(dist, armed, orders=(), doors=()):
    """An open-play observation, the fort unsealed (no hatch: no lockdown holds), two hostiles `dist` from the wagon,
    and a squad of four with `armed` members armed."""
    r = threat_resp(200, dist, n=2, doors=doors, cit=16)
    r["observation"]["military"] = {"squads": [{"id": 1, "members": [{"id": i} for i in range(4)], "armed": armed,
                                                "uniform": "leather", "orders": list(orders)}]}
    return r


def office_resp(plots, cit=20):
    """An open-task observation with three dug soil rooms and `plots` farm plots on a level of their own."""
    r = resp(120, 216, food=60, cit=cit)
    r["observation"]["map"]["sites"] = [{"id": "R%d" % i, "kind": "R", "dug": True, "free": True, "soil": True,
                                         "x": 90 + 4 * i, "y": 90, "z": 151} for i in (1, 2, 3)]
    r["observation"]["farm_plots"] = [{"id": 50 + i, "x": 80 + 4 * i, "y": 80, "z": 150, "built": True}
                                      for i in range(plots)]
    return r


class D64(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    # 1. tripwire stops
    def test_a_stopped_advance_gets_its_own_pass(self):
        days = passes(StopGame(stops=[{"reason": "hostile_approaching", "detail": "harpy"}]))
        self.assertEqual(days[:2], [100, 100])            # the day's pass, then one for the stop within the day
        self.assertEqual(len(days), len(set(days)) + 1)    # and only that one extra

    def test_no_stop_no_extra_pass(self):
        days = passes(StopGame())
        self.assertEqual(len(days), len(set(days)))

    def test_lab_tasks_keep_one_pass_a_day(self):
        days = passes(StopGame(stops=[{"reason": "hostile_visible"}], hands_off=20))
        self.assertEqual(len(days), len(set(days)))

    # 2. the squad
    def test_no_attack_on_a_far_hostile_with_one_member_armed(self):
        ov, g = overseer(squad_resp(132, armed=1))
        ov.defend()
        self.assertEqual(g.tools("squad_order"), [])

    def test_no_attack_near_the_wagon_while_members_are_unarmed(self):
        ov, g = overseer(squad_resp(30, armed=1))
        ov.defend()
        self.assertEqual(g.tools("squad_order"), [])

    def test_an_armed_squad_fights_at_the_wagon(self):
        ov, g = overseer(squad_resp(30, armed=4))
        ov.defend()
        self.assertEqual(g.tools("squad_order"), [{"order": "attack", "target_ids": [900, 901]}])   # d65: named

    def test_a_chase_is_called_off(self):
        ov, g = overseer(squad_resp(132, armed=1, orders=["attack"]))
        ov.defend()
        self.assertEqual(g.tools("squad_order"), [{"order": "stand_down"}])

    # 3. admission against hostiles the API lists
    def admit_pass(self, at):
        r = threat_resp(190, 87, n=2, alert=True, inside=9, at=at)
        for p in r["observation"]["dwarves"]:          # citizen 3 beside the hatch, the rest below
            p.update(x=93, y=100, z=153, profession="Craftsdwarf") if p["id"] == 3 else p.update(x=95, y=101, z=151)
        ov, g = overseer(r)
        ov.lock = hold(189, due=189 * DAY)
        ov.defend()
        return ov, g

    def test_a_citizen_outside_is_let_in_while_the_harpies_are_far_from_the_hatch(self):
        ov, g = self.admit_pass(at=(10, 10, 165))         # 126 from the hatch by the API's measure
        self.assertNotIn(LOCK, g.tools("lock_door"))
        self.assertEqual(ov.lock["open"], {HATCH["id"]})

    def test_not_while_one_is_near_the_hatch(self):
        ov, g = self.admit_pass(at=(92 + ADMIT_FAR - 10, 100, 153))
        self.assertIn(LOCK, g.tools("lock_door"))
        self.assertEqual(ov.lock["open"], set())

    # 4. the office
    def test_a_spare_farm_room_takes_the_office_once_the_plots_are_made(self):
        ov, g = overseer(office_resp(plots=4))
        ov.roles = {"R1": "farm", "R2": "farm", "R3": "farm"}
        self.assertEqual((ov.office_site() or {}).get("id"), "R1")

    def test_not_while_the_plots_are_short(self):
        ov, g = overseer(office_resp(plots=3))
        ov.roles = {"R1": "farm", "R2": "farm", "R3": "farm"}
        self.assertIsNone(ov.office_site())

    def test_a_room_a_plot_uses_stays_a_farm(self):
        r = office_resp(plots=4)
        for s in r["observation"]["map"]["sites"]:
            s["used_by"] = ["farm plot 7"]
        ov, g = overseer(r)
        ov.roles = {"R1": "farm", "R2": "farm", "R3": "farm"}
        self.assertIsNone(ov.office_site())


if __name__ == "__main__":
    unittest.main()
