"""cx m13many: the MY1 plan's drink rate leaves out the caravan's looks. Hint std MY1-3 on e33d381, 17 citizens: the
caravan's goods stood in the stocks d44-78 (drink 171-205) and left d79 (110); the settle window ended d88 while the
21-day record still held d71-78, so on d91 f_drink_rate read 5.1 a day, hold_active's drink-to-F test dropped the
armed hold, and the model's brew_drink "2 daily, plants_brewable >= 3" brewed 2 of the scarce plants before F
(supply 0.713). No game or network."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness  # noqa: E402
import test_harvest_hold as hh  # noqa: E402

# the probe's drink looks (day, drink), caravan arrived d43, embarked d74, goods out by d79
LOOKS = [(60, 206), (62, 206), (64, 205), (65, 205), (67, 205), (69, 205), (71, 204), (72, 204), (74, 204),
         (76, 177), (78, 185), (79, 110), (81, 109), (83, 109), (84, 109), (86, 114), (88, 116), (90, 121),
         (91, 121)]
MODEL_BREW = {"recipe": "brew_drink", "amount": 2, "repeat": "daily",
              "when": [{"stock": "drink", "below": 300}, {"stock": "plants_brewable", "at_least": 3},
                       {"stock": "barrels_empty", "at_least": 1}]}


class CaravanRecord(hh.Base):
    def run_looks(self, upto=91, caravan=True):
        ov, game = self.ov()
        ov.mig_start, ov.mig_waves = 9, 2   # the waves came: the forecast is the census
        held = {}
        for day, drink in LOOKS:
            if day > upto:
                break
            if caravan:
                ov.caravan_active = day <= 78
                ov.caravan_last_day = 74 if day >= 74 else 43
            held[day] = self.step(ov, day, cit=17 if day >= 84 else 9, drink=drink, pb=3)
        return ov, held

    def test_the_hold_stays_armed_after_the_settle_window(self):
        ov, held = self.run_looks()
        self.assertTrue(ov.hold_armed)
        self.assertTrue(all(held[d] for d in (88, 90, 91)), held)
        self.assertAlmostEqual(ov.f_drink_rate(), harness.DRINK_PER_CIT_DAY * 17)

    def test_the_model_s_low_floor_brew_is_vetoed_on_day_91(self):
        ov, _ = self.run_looks()
        self.assertIsNotNone(ov.hold_veto("add_order", MODEL_BREW))
        ok = dict(MODEL_BREW, when=[{"stock": "plants_brewable", "at_least": ov.hold_reserve() + 2}])
        self.assertIsNone(ov.hold_veto("add_order", ok))

    def test_a_record_without_a_caravan_still_reads_the_net_decline(self):
        ov, _ = self.ov()
        ov.mig_start, ov.mig_waves = 9, 1
        for day in range(150, 172, 2):   # 17 citizens drinking 1.5 a day net
            self.step(ov, day, cit=17, drink=int(120 - 1.5 * (day - 150)), pb=8)
        self.assertAlmostEqual(ov.f_drink_rate(), 1.5, delta=0.1)
        self.assertAlmostEqual(ov.f_drink_rate(prior_only=True), harness.DRINK_PER_CIT_DAY * 17)


if __name__ == "__main__":
    unittest.main()
