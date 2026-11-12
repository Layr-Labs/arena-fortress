"""cx hold veto (hint std MY1-3 on c44c96b): the model's "brew_drink 3 daily, plants_brewable >= 1" order added on d116
brewed 2 of the harvest-closed hold's plants before the layer's next pass cancelled it (hold_cancel, d117). A model
brew order the hold would cancel is now refused at the call (layer_hold); a floor at the reserve, F itself, an
unarmed hold and every other order pass. No game or network."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness  # noqa: E402
from plain import harness as plain  # noqa: E402
import test_harvest_hold as hh  # noqa: E402

BREW = {"recipe": "brew_drink", "amount": 3, "repeat": "daily",
        "when": [{"stock": "plants_brewable", "at_least": 1}, {"stock": "barrels_empty", "at_least": 1}]}


class Veto(hh.Base):
    def test_a_floorless_brew_is_refused_while_the_hold_stands(self):
        ov, _ = self.armed(pb=7)
        msg = ov.hold_veto("add_order", BREW)
        self.assertIsNotNone(msg)
        self.assertIn(str(ov.hold_reserve()), msg)
        self.assertIsNotNone(ov.hold_veto("add_order", {"recipe": "brew_drink", "amount": 2}))
        self.assertIsNotNone(ov.hold_veto("add_manager_order", {"job": "CustomReaction",
                                                                "reaction": "BREW_DRINK_FROM_PLANT", "amount": 2}))

    def test_a_floor_at_the_reserve_passes(self):
        ov, _ = self.armed(pb=7)
        # cx MY1 supply plan: a standing's floor must leave the reserve after its firing (reserve + amount)
        ok = dict(BREW, when=[{"stock": "plants_brewable", "at_least": ov.hold_reserve() + 3}])
        self.assertIsNone(ov.hold_veto("add_order", ok))
        low = dict(BREW, when=[{"stock": "plants_brewable", "at_least": ov.hold_reserve() + 2}])
        self.assertIsNotNone(ov.hold_veto("add_order", low))

    # cx MY1 supply plan (7c43df4 std d120/148/169: three refusals while drink fell 83 -> 32 with 11 held): the
    # plants over the reserve are free before F
    def test_a_one_shot_within_the_surplus_passes(self):
        ov, _ = self.armed(pb=11)
        free = 11 - ov.hold_reserve()
        self.assertGreaterEqual(free, 1)
        self.assertIsNone(ov.hold_veto("add_order", {"recipe": "brew_drink", "amount": free}))
        msg = ov.hold_veto("add_order", {"recipe": "brew_drink", "amount": free + 1})
        self.assertIn("%d plants are free now" % free, msg)

    def test_other_orders_pass(self):
        ov, _ = self.armed(pb=7)
        self.assertIsNone(ov.hold_veto("add_order", {"recipe": "cook_meal", "amount": 2}))
        self.assertIsNone(ov.hold_veto("cancel_order", {"order_id": 5}))

    def test_inside_f_the_plan_holds_every_free_plant_on_my1(self):
        # cx MY1 supply plan: inside F only the plan brews (its own orders pass no veto)
        ov, _ = self.armed(pb=7)
        self.step(ov, 216 - ov.f_len() + 1, pb=7)
        self.assertIsNotNone(ov.hold_veto("add_order", BREW))
        self.assertIsNotNone(ov.hold_veto("add_order", {"recipe": "brew_drink", "amount": 1}))

    def test_inside_f_the_model_may_brew_off_my1(self):
        ov, _ = self.ov(days=336)
        ov.hold_armed = True
        ov.load(hh.resp(330, days=336, pb=7))
        self.assertIsNone(ov.hold_veto("add_order", BREW))

    def test_no_hold_no_veto(self):
        ov, _ = self.ov()
        self.step(ov, 40, pb=7, seeds=hh.PLUMP)
        self.assertFalse(ov.hold_armed)
        # cx plant barrel keep: outside the hold, MY1 open play refuses only a floor under the firing + BARREL_KEEP
        self.assertTrue(ov.barrel_keep())
        self.assertNotIn("last %d days" % ov.f_len(), ov.hold_veto("add_order", BREW) or "")
        ok = dict(BREW, when=[{"stock": "plants_brewable", "at_least": 3 + harness.BARREL_KEEP}])
        self.assertIsNone(ov.hold_veto("add_order", ok))


class PlainRefuses(hh.Base):
    def runner(self, guard):
        r = plain.Plain.__new__(plain.Plain)
        r.added, r.cancelled, r.guard = {}, [], guard
        return r

    def test_the_loop_refuses_with_layer_hold(self):
        ov, _ = self.armed(pb=7)
        out = self.runner(ov).refuse("add_order", BREW, 100 * plain.DAY)
        self.assertEqual(out["error_code"], "layer_hold")
        self.assertFalse(out["ok"])

    def test_a_guard_without_the_veto_changes_nothing(self):
        r = self.runner(SimpleNamespace(owned=set()))
        self.assertIsNone(r.refuse("add_order", BREW, 100 * plain.DAY))


if __name__ == "__main__":
    unittest.main()
