"""An empty office must not deadlock its own furniture production at 20 citizens."""
import copy
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from overseer.harness import Overseer, DAY


class Game:
    def __init__(self, accepted=True):
        self.calls = []
        self.accepted = accepted

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": self.accepted, "result": {"zone_id": 42}} if tool == "make_zone" else {"ok": True}


def observation():
    # Reduced facts from public seed2009's 336-day draw: office on 82, chairs on 80.
    return {"day": 214, "tick": 214 * DAY, "observation": {
        "administrators": {"citizens": 20, "MANAGER_id": 83, "manager_active_for_orders": True,
                           "manager_office": {"chair": False, "zone_id": 41}},
        "stocks": {"furniture_free": {"chair": 0}},
        "zones": [{"id": 41, "type": "Office", "owner": 83, "x": 93, "y": 91,
                   "z": 82, "w": 7, "h": 3, "furniture": {}}],
        "map": {"sites": [{"id": "A2", "kind": "A", "x": 93, "y": 91,
                            "z": 80, "w": 13, "h": 7, "open_tiles": 91}]},
        "furniture": [{"kind": "chair", "built": True, "x": 95, "y": 91, "z": 80}]}}


class OfficeRecovery(unittest.TestCase):
    def run_office(self, obs=None, accepted=True):
        g = Game(accepted)
        a = Overseer(g)
        a.load(obs or observation())
        a.count = 0
        with redirect_stdout(io.StringIO()):
            a.office()
        return a, g

    def test_missing_free_chair_uses_existing_built_chair_and_assigns_new_office(self):
        a, g = self.run_office()
        self.assertEqual(g.calls, [("make_zone", {"kind": "office", "site": "A2"}),
                                   ("assign_zone", {"zone_id": 42, "dwarf_id": 83})])
        self.assertEqual(a.office_recoveries, 1)

    def test_healthy_manager_keeps_working_office(self):
        o = observation()
        o["observation"]["administrators"]["manager_office"]["chair"] = True
        _, g = self.run_office(o)
        self.assertEqual(g.calls, [])

    def test_planned_office_chair_is_allowed_to_finish(self):
        o = observation()
        o["observation"]["zones"][0]["furniture_planned"] = {"chair": 1}
        _, g = self.run_office(o)
        self.assertEqual(g.calls, [])

    def test_existing_unowned_furnished_office_only_needs_assignment(self):
        o = observation()
        z = copy.deepcopy(o["observation"]["zones"][0])
        z.update(id=42, owner=None, furniture={"chair": 1})
        o["observation"]["zones"].append(z)
        _, g = self.run_office(o)
        self.assertEqual(g.calls, [("assign_zone", {"zone_id": 42, "dwarf_id": 83})])

    def test_unbuilt_chair_does_not_prove_a_ready_office(self):
        o = observation()
        o["observation"]["furniture"][0]["built"] = False
        _, g = self.run_office(o)
        self.assertEqual(g.calls, [])

    def test_oversized_area_is_not_sent_to_zone_tool(self):
        o = observation()
        o["observation"]["map"]["sites"][0]["h"] = 50
        _, g = self.run_office(o)
        self.assertEqual(g.calls, [])

    def test_farm_level_is_not_repurposed_for_office(self):
        o = observation()
        o["observation"]["farm_plots"] = [{"id": 1, "z": 80}]
        _, g = self.run_office(o)
        self.assertEqual(g.calls, [])

    def test_refused_zone_is_not_counted_as_recovery_or_assigned(self):
        a, g = self.run_office(accepted=False)
        self.assertEqual(a.office_recoveries, 0)
        self.assertEqual([t for t, _ in g.calls], ["make_zone"])

    def test_recovery_has_two_acceptance_limit_even_if_manager_state_stays_stale(self):
        a, g = self.run_office()
        with redirect_stdout(io.StringIO()):
            for _ in range(4):
                a.now += 4 * DAY
                a.office()
        self.assertEqual(a.office_recoveries, 2)
        self.assertEqual(sum(t == "make_zone" for t, _ in g.calls), 2)


if __name__ == "__main__":
    unittest.main()
