"""Closed-loop operator contracts; offline only, no game or model gateway."""
import copy
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer, DAY


class Game:
    def __init__(self):
        self.calls = []
        self.refuse = set()

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": tool not in self.refuse, "result": {"order_id": 100 + len(self.calls)}}

    def query(self, name, **kw):
        return {"ok": True, "result": {"units": [], "total": 0}}


def observation(day=50):
    return {"day": day, "tick": day * DAY, "days_left": 336 - day, "observation": {
        "administrators": {"citizens": 20, "manager_active_for_orders": True, "MANAGER_id": 3,
                           "manager_office": {"zone_id": 8, "chair": True}},
        "stocks": {"logs_usable": 60, "boulders_usable": 0, "drink": 100,
                   "food_edible": 100, "prepared_meals": 20},
        "wealth": {"created": 1000}, "progression": {"fortress_rank": 0},
        "plugins": {"autochop": "on", "seedwatch": "on", "autofarm": "on"},
        "orders": [], "zones": [], "farm_plots": [],
        "furniture": [{"kind": "bed", "built": True} for _ in range(20)],
        "map": {"surface_z": 100, "sites": [
            {"id": "W1", "kind": "W"}, {"id": "W2", "kind": "W"}, {"id": "W3", "kind": "W"}]},
        "workshops": [{"id": i, "type": t, "built": True} for i, t in enumerate(
            ["Carpenters", "Still", "Kitchen", "Craftsdwarfs"])],
        "burrows": {"civilian_alert": False, "list": []},
        "threats": {"visible_hostiles": 0, "hostiles": []}}}


class Supervisor(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def make(self, r=None):
        o = Overseer(Game(), days=336, advisory_sensing=False)
        o.count = 0
        o.load(r or observation())
        return o

    def crafts(self, o):
        return [a for t, a in o.game.calls if t == "add_manager_order" and a.get("job") == "MakeCrafts"]

    def test_unready_office_cannot_assign_labors(self):
        r = observation()
        r["observation"]["administrators"]["manager_office"]["chair"] = False
        o = self.make(r)
        o.management()
        self.assertNotIn(("enable_automation", {"name": "autolabor"}), o.game.calls)

    def test_ready_office_assigns_labors(self):
        o = self.make()
        o.management()
        self.assertIn(("enable_automation", {"name": "autolabor"}), o.game.calls)

    def test_short_supplies_or_alert_block_crafts(self):
        for field, value in [("drink", 0), ("food_edible", 0), ("prepared_meals", 0), ("logs_usable", 25)]:
            r = observation()
            r["observation"]["stocks"][field] = value
            o = self.make(r)
            o.progress()
            self.assertEqual(self.crafts(o), [], field)
        r = observation()
        r["observation"]["burrows"]["civilian_alert"] = True
        o = self.make(r)
        o.progress()
        self.assertEqual(self.crafts(o), [])

    def test_unknown_supply_fails_closed_for_optional_work(self):
        r = observation()
        del r["observation"]["stocks"]["drink"]
        o = self.make(r)
        o.progress()
        self.assertEqual(self.crafts(o), [])

    def test_cancelled_owned_crafts_recover_but_unreadable_orders_do_not_duplicate(self):
        o = self.make()
        o.progress()
        self.assertEqual(len(self.crafts(o)), 1)
        r = observation(55)
        r["observation"]["orders"] = None
        o.load(r)
        o.progress()
        self.assertEqual(len(self.crafts(o)), 1)
        o.load(observation(60))  # complete empty list confirms the order is gone
        o.progress()
        self.assertEqual(len(self.crafts(o)), 2)

    def test_safety_depletion_cancels_only_owned_optional_orders(self):
        o = self.make()
        o.progress()
        oid = o.game.calls[-1][1]
        self.assertEqual(oid["job"], "MakeCrafts")
        r = observation(55)
        r["observation"]["orders"] = [{"id": 101, "job": "MakeCrafts", "repeat": "daily"},
                                       {"id": 999, "job": "MakeCrafts", "repeat": "daily"}]
        r["observation"]["stocks"]["drink"] = 0
        o.load(r)
        o.progress()
        self.assertEqual([a for t, a in o.game.calls if t == "cancel_order"], [{"order_id": 101}])

    def test_unobserved_or_same_pass_order_is_not_achievement(self):
        o = self.make()
        o.progress()
        self.assertEqual(o.supervisor_status()["progression"]["state"], "requested")
        r = observation(55)
        r["observation"]["wealth"]["created"] = 5600
        o.load(r)
        o.progress()
        self.assertEqual(o.supervisor_status()["progression"]["state"], "awaiting_rank")
        r["observation"]["progression"]["fortress_rank"] = 1
        o.load(r)
        o.progress()
        self.assertEqual(o.supervisor_status()["progression"]["state"], "achieved")

    def test_preexisting_rank_not_counted_as_new(self):
        r = observation()
        r["observation"]["progression"]["fortress_rank"] = 1
        o = self.make(r)
        o.progress()
        self.assertNotEqual(o.supervisor_status()["progression"]["state"], "achieved")
        self.assertEqual(self.crafts(o), [])  # this supervisor only targets Hamlet

    def test_suspended_core_recovery_waits_three_days_and_is_bounded(self):
        r = observation()
        rows = r["observation"]["workshops"]
        rows[1].update(built=False, job_details=[{"job": "ConstructBuilding", "suspended": True}])
        o = self.make(r)
        o.workshops()
        self.assertEqual(o.game.calls, [])
        for day in [53, 56, 59]:
            r["day"], r["tick"] = day, day * DAY
            o.load(copy.deepcopy(r))
            o.workshops()
        builds = [a for t, a in o.game.calls if t == "build_workshop" and a["type"] == "Still"]
        self.assertEqual(len(builds), 2)
        self.assertEqual(len({a["site"] for a in builds}), 2)

    def test_missing_workshop_observation_breaks_suspension_timer(self):
        r = observation()
        r["observation"]["workshops"][1].update(
            built=False, job_details=[{"job": "ConstructBuilding", "suspended": True}])
        o = self.make(r)
        missing = observation(52)
        missing["observation"]["workshops"] = None
        o.load(missing)
        r["day"], r["tick"] = 53, 53 * DAY
        o.load(r)
        o.workshops()
        self.assertEqual(o.game.calls, [])

    def test_safety_precedes_economy_in_whole_plan(self):
        o = self.make()
        seen = []
        for name in ["events", "sweep", "mood", "defend", "management", "workshops", "digging", "farms",
                     "supply", "cubicles", "furnish", "rezone", "progress", "stonework", "closer"]:
            setattr(o, name, lambda name=name: seen.append(name))
        o.plan()
        self.assertLess(seen.index("defend"), seen.index("mood"))
        self.assertLess(seen.index("defend"), seen.index("management"))

    def test_standalone_main_selects_supervisor(self):
        from overseer import harness
        self.assertIs(harness.main.__globals__["Overseer"], Overseer)

    def test_conflicting_material_order_is_blocker_not_active(self):
        r = observation()
        r["observation"]["orders"] = [{"id": 888, "job": "MakeCrafts", "repeat": "daily"}]
        o = self.make(r)
        o.progress()
        self.assertEqual(self.crafts(o), [])
        self.assertIn("conflicting_or_unverifiable_order", o.progress_state["blockers"])
        self.assertEqual(o.game.calls, [])

    def test_observed_active_is_distinct_from_requested(self):
        o = self.make()
        o.progress()
        self.assertEqual(o.progress_state["state"], "requested")
        r = observation(55)
        r["observation"]["orders"] = [{"id": 101, "job": "MakeCrafts", "repeat": "daily", "active": True}]
        o.load(r)
        o.progress()
        self.assertEqual(o.progress_state["state"], "active")

    def test_ambiguous_receipt_absence_recovers_without_adopting_others(self):
        o = self.make()
        original = o.game.act
        o.game.act = lambda tool, args: {"ok": True, "result": {}}
        o.progress()
        self.assertIn("ownership_unresolved", o.progress_state["blockers"])
        r = observation(55)
        r["observation"]["orders"] = [{"id": 888, "job": "MakeCrafts", "repeat": "daily"}]
        r["observation"]["stocks"]["drink"] = 0
        o.load(r)
        o.progress()
        self.assertIsNone(o.optional_orders["supervisor_crafts"])
        self.assertNotIn(("cancel_order", {"order_id": 888}), o.game.calls)
        o.game.act = original
        o.load(observation(60))
        o.progress()
        self.assertEqual(len(self.crafts(o)), 1)

    def test_transport_error_records_pending_before_post(self):
        o = self.make()
        def fail(tool, args):
            raise OSError("lost receipt")
        o.game.act = fail
        with self.assertRaises(OSError):
            o.progress()
        self.assertIsNone(o.optional_orders["supervisor_crafts"])
        self.assertEqual(o.pending_optional["supervisor_crafts"]["job"], "MakeCrafts")

    def test_invader_sealing_and_exit_cleanup_by_owned_id(self):
        r = observation()
        r["observation"]["threats"] = {"visible_hostiles": 1, "nearest_hostile_dist_to_wagon": 10,
                                         "hostiles": [{"id": 42, "invader": True}]}
        r["observation"]["burrows"] = {"civilian_alert": False, "list": [{"civ_alert_burrow": True}]}
        r["observation"]["map"]["sites"].append({"id": "E1", "kind": "E", "x": 1, "y": 1, "z": 100})
        r["observation"]["doors"] = {"list": [{"id": 7, "kind": "hatch", "built": True,
                                                 "x": 1, "y": 1, "z": 100, "locked": False}]}
        o = self.make(r)
        o.defend()
        self.assertIn(("lock_door", {"locked": True, "door_id": 7}), o.game.calls)
        self.assertTrue(o.invader_alert)
        self.assertEqual(o.invader_locks, {7})
        self.assertNotIn(7, o.own_locks)  # wildlife must not unlock invader ownership mid-pass
        o.release()
        self.assertIn(("civilian_alert", {"on": False}), o.game.calls)
        self.assertIn(("lock_door", {"locked": False, "door_id": 7}), o.game.calls)
        self.assertFalse(o.invader_alert)
        self.assertEqual(o.invader_locks, set())

    def test_unknown_workshop_list_does_not_construct(self):
        r = observation()
        r["observation"]["workshops"] = None
        o = self.make(r)
        o.workshops()
        self.assertEqual(o.game.calls, [])


if __name__ == "__main__":
    unittest.main()
