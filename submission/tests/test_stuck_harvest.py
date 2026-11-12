"""cx stuck harvest (probes of hint std MY1-3, 2026-11-11; LOOSE_BREW_DAYS in overseer/harness.py). The MY1 forts have
one food stockpile whose 14 tiles each already hold a barrel at the hand-over; a harvested plant is stored only in the
plant barrel or an empty barrel standing on a tile. When meals or fish take the freed tile, the harvest lies loose
(probe Y: 12-13 days, no StoreItemInBarrel job; the incident: cave wheat 5 loose from d92, rotten d104-116). A brewable
plant read loose on every PLANT census for LOOSE_BREW_DAYS leaves any hold or floor and goes to the Still, rot seen or
not; plants in barrels, plants loose for a shorter span, and a span broken by a reading of 0 loose stay as before.
No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

from test_rotting_reserve import Base, group, KINDS   # noqa: E402  (same fake game and observation)


class StuckHarvest(Base):
    def harvest(self, loose_days, inv=False, gap=None):
        """The incident's shape: the hold armed in autumn, cave wheat harvested from d89, read every day."""
        ov, game = self.ov()
        pb = 0
        for day in range(80, 92 + loose_days + 1):
            if day >= 89:
                pb = min(5, pb + 1)
            g = [group("GRASS_WHEAT_CAVE", pb, inv=pb if inv else 0)] if pb else []
            if gap is not None and day == gap:
                g = [group("GRASS_WHEAT_CAVE", pb, inv=pb)]   # one reading with every plant in a barrel
            game.groups = g
            self.step(ov, day, pb=pb)
        return ov, game

    def test_incident_shape_brews_the_stuck_plants_before_any_rot(self):
        ov, game = self.harvest(loose_days=6)          # d92 + 6 = d98, the pass the alert sounded on
        self.assertTrue(ov.hold_active())
        self.assertFalse(ov.rot_seen)
        self.assertGreaterEqual(ov.loose_stuck(), 4)   # loose on every reading since d93 (4 then, 5 now)
        self.assertGreater(ov.plant_floor(), ov.pb_free())   # the hold would keep them all
        self.assertEqual(ov.rot_keep(), ov.pb_free() - ov.loose_stuck())
        game.calls.clear()
        ov.rot_guard()
        b = self.brews(game)
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0]["amount"], ov.loose_stuck())
        self.assertNotIn("repeat", b[0])

    def test_loose_for_less_than_the_window_waits(self):
        ov, game = self.harvest(loose_days=1)
        self.assertEqual(ov.loose_stuck(), 0)
        game.calls.clear()
        ov.rot_guard()
        self.assertEqual(self.brews(game), [])

    def test_barrelled_harvest_stays_held(self):
        ov, game = self.harvest(loose_days=20, inv=True)
        self.assertEqual(ov.loose_stuck(), 0)
        self.assertEqual(ov.rotting_held(), 0)
        game.calls.clear()
        ov.rot_guard()
        self.assertEqual(self.brews(game), [])

    def test_a_reading_with_nothing_loose_restarts_the_span(self):
        ov, game = self.harvest(loose_days=6, gap=96)  # stored on d96 (a barrel was found), loose again after
        self.assertEqual(ov.loose_stuck(), 0)

    def test_no_reading_today_is_not_stuck(self):
        ov, game = self.harvest(loose_days=6)
        ov.day += 1   # a pass without a census reading of its own
        self.assertEqual(ov.loose_stuck(), 0)

    def test_without_hold_the_o_brew_floor_does_not_keep_stuck_plants(self):
        ov, game = self.ov(days=336)                   # open year, early: no hold
        for day in range(40, 47):
            game.groups = [group("GRASS_TAIL_PIG", 2)]
            self.step(ov, day, pb=2)
        self.assertFalse(ov.hold_active())
        self.assertEqual(ov.loose_stuck(), 2)
        self.assertEqual(ov.rot_keep(), 0)              # ROT_KEEP's 2 would have left both to rot
        game.calls.clear()
        ov.rot_guard()
        b = self.brews(game)
        self.assertEqual([x["amount"] for x in b], [2])

    def test_food_lean_still_brews_a_stuck_plant_no_meal_takes(self):
        ov, game = self.harvest(loose_days=6)
        plan = dict(ov.plant_plan(), lean=True)
        ov.plant_plan = lambda: plan
        self.assertFalse(any(v["cookable"] for v in KINDS.values()))
        game.calls.clear()
        ov.rot_guard()
        self.assertEqual(len(self.brews(game)), 1)
        self.assertFalse([a for t, a in game.calls if a.get("recipe") == "cook_meal"])

    def test_the_history_keeps_only_its_window(self):
        ov, game = self.harvest(loose_days=6)
        for day in range(99, 99 + harness.LOOSE_HIST_DAYS + 5):
            game.groups = [group("GRASS_WHEAT_CAVE", 5)]
            self.step(ov, day, pb=5)
        self.assertTrue(all(ov.day - h[0] <= harness.LOOSE_HIST_DAYS for h in ov.loose_hist))


if __name__ == "__main__":
    unittest.main()
