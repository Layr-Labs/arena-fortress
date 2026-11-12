"""cx m13many: hint std MY1-3 on 657e3d0 (13 citizens, supply 0.617). The food-lean keeper (lean d155-190) took the
held plants: its o_brew "2 daily, drink below 78, plants_brewable >= 1" was re-added each pass after hold_supply cut it
(pb 5 -> 0 over d162-185), and the lean gate kept f_plan off until d197 (pb 0). No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness  # noqa: E402
import test_harvest_hold as hh  # noqa: E402


class LeanKeeperUnderHold(hh.Base):
    def lean(self, day=162, drink=73, pb=5, looks=((150, 83), (155, 78))):
        ov, game = self.armed(cit=13)
        ov.mig_start, ov.mig_waves = 9, 1
        ov.food_lean = lambda: True
        for d0, dr in looks:
            self.step(ov, d0, cit=13, drink=dr, pb=pb)
        self.step(ov, day, cit=13, drink=drink, pb=pb)
        return ov, game

    def test_the_keeper_keeps_the_reserve(self):
        ov, _ = self.lean()
        self.assertTrue(ov.hold_active())
        floor = [c["at_least"] for c in ov.brew_when() if c["stock"] == "plants_brewable"][0]
        self.assertEqual(floor, ov.hold_reserve() + 1)
        self.assertEqual(ov.brew_amount(), 1)
        self.assertTrue(ov.leaves_reserve(ov.brew_amount(), ov.brew_when(), True, ov.hold_reserve()))

    def test_off_my1_the_keeper_is_unchanged(self):
        ov, _ = self.ov(days=336)
        ov.food_lean = lambda: True
        ov.load(hh.resp(250, days=336, cit=16, pb=5))
        self.assertEqual([c["at_least"] for c in ov.brew_when() if c["stock"] == "plants_brewable"][0], 1)
        self.assertEqual(ov.brew_amount(), harness.LEAN_BREW_AMOUNT)

    def test_the_f_plan_runs_while_lean(self):
        ov, game = self.lean(day=177, drink=73, looks=((163, 80), (170, 77)))
        ov.hold_supply()
        self.assertIsNotNone(ov.f_plan_key)   # the plan logged and placed its mid-F brew


if __name__ == "__main__":
    unittest.main()
