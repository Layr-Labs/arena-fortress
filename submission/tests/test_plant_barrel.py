"""cx plant barrel guard (hint std MY1-3 on 642f253, supply 0.519): the plant barrel emptied d42-49 and never came
back; every later harvest lay loose and was brewed before it rotted, so nothing was held for F. Measured (read-only
DFHack recorder, cx-9525adc std MY1-3): the Still took its plant from the plant barrel on all 5 brews over d1-27, also
while a loose plant waited; a barrel emptied on the food stockpile went to the next loose food stored (meals d8, meat
d35.5). No game or network."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness  # noqa: E402
import test_harvest_hold as hh  # noqa: E402


class PlantBarrel(hh.Base):
    def fort(self, day=44, contained=1, loose=2, pb=3, days=216, **kw):
        ov, game = self.ov(days=days)
        self.step(ov, day, pb=pb, **kw)
        ov.plant_loose = {"loose": loose, "contained": contained, "day": day}
        return ov, game

    def test_layer_brews_leave_the_last_barrelled_plant(self):
        ov, _ = self.fort(contained=1, loose=2, pb=3)
        self.assertEqual(ov.barrel_brew_cap(), 0)
        self.assertEqual(ov.brew_shot_allow("o_brew_rot"), 0)
        ov, _ = self.fort(contained=4, loose=0, pb=4)
        self.assertEqual(ov.barrel_brew_cap(), 3)

    def test_the_standing_floor_sits_on_top_of_the_loose_plants(self):
        ov, _ = self.fort(day=20, contained=1, loose=2, pb=3)
        self.assertTrue(ov.barrel_keep())
        self.assertEqual(ov.brew_floor(), harness.BARREL_KEEP_AMOUNT + harness.BARREL_KEEP + 2)

    def test_no_barrelled_plant_turns_the_brew_guard_off(self):
        ov, _ = self.fort(contained=0, loose=3, pb=3)
        self.assertIsNone(ov.barrel_brew_cap())   # no barrel to keep: the stuck harvest is brewed as before

    def test_a_stale_census_or_op1_turns_it_off(self):
        ov, _ = self.fort(contained=1, loose=2, pb=3)
        ov.plant_loose["day"] = 30
        self.assertIsNone(ov.plant_barrel())
        ov, _ = self.fort(contained=1, loose=2, pb=3, days=336)
        self.assertIsNone(ov.plant_barrel())

    def test_meals_wait_while_plants_lie_loose_with_no_barrel_at_most_a_week(self):
        ov, _ = self.fort(contained=0, loose=2, pb=2)
        self.assertTrue(ov.meal_wait())
        for day in (47, 50):
            self.step(ov, day, pb=2)
            ov.plant_loose = {"loose": 2, "contained": 0, "day": day}
            self.assertTrue(ov.meal_wait())
        self.step(ov, 51, pb=2)
        ov.plant_loose = {"loose": 2, "contained": 0, "day": 51}
        self.assertFalse(ov.meal_wait())          # 7 days on: the meat must not rot waiting
        ov.plant_loose = {"loose": 0, "contained": 2, "day": 51}
        self.assertFalse(ov.meal_wait())

    def test_meat_keep_waits_for_the_plant_barrel(self):
        ov, game = self.fort(contained=0, loose=2, pb=2)
        ov.perishable = lambda: 40
        ov.meat_keep()
        self.assertNotIn("o_cook_meat", ov.key_order)
        ov.plant_loose = {"loose": 0, "contained": 2, "day": 44}
        ov.meat_keep()
        self.assertIn("o_cook_meat", ov.key_order)


if __name__ == "__main__":
    unittest.main()
