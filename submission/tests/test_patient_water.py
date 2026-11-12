"""cx patient water: a standing MakeBucket (wood, monthly, while fewer than BUCKET_KEEP empty buckets) once a
Carpenters stands and a "Give water" cancel was seen; the cancels are logged. A healthy fort orders nothing.

Measured shape: hint hard OP1-0 on c44c96b — a fisher (unit 100) torn ankle ligament/tendon on day 146, idle on
98,96,161 for 160 days, melancholy on day 306; the carers' Give water at his tile cancelled "No water source." 48 times
(days 220-224, alert on) and "Need empty bucket." from day 225 (alert off). No game or network is used."""
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


class FakeGame:
    def __init__(self, ok=True):
        self.calls, self.ok = [], ok

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        if not self.ok:
            return {"ok": False, "error_code": "bad_arguments", "error": "nope"}
        return {"ok": True, "result": {"order_id": 900 + len(self.calls)}}


def fort(day=150, logs=300, carpenters=True, built=True, cancels=(), events=(), alert=False, cit=15):
    shops = [{"type": "Carpenters", "built": built, "x": 91, "y": 93, "z": 162}] if carpenters else []
    return {"day": day, "tick": day * harness.DAY, "days_left": 336 - day,
            "observation": {
                "administrators": {"citizens": cit}, "map": {"sites": [], "surface_z": 162},
                "orders": [], "farm_plots": [], "workshops": shops,
                "burrows": {"civilian_alert": alert, "list": []},
                "recent_cancellations": list(cancels), "recent_events": list(events),
                "stocks": {"logs_usable": logs, "beds": cit + 3, "tables": 12, "chairs": 12, "barrels_empty": 14,
                           "drink": 200, "food_edible": 100, "furniture_free": {}}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.out = io.StringIO()
        self.ctx = redirect_stdout(self.out)
        self.ctx.__enter__()
        self.addCleanup(self.ctx.__exit__, None, None, None)

    def overseer(self, game):
        ov = harness.Overseer(game, days=336)
        ov.count = 0
        return ov

    def buckets(self, game):
        return [a for t, a in game.calls if t == "add_manager_order" and a.get("job") == "MakeBucket"]

    def logs(self, kind):
        return [json.loads(x) for x in self.out.getvalue().splitlines() if x.startswith("{")
                and json.loads(x).get("kind") == kind]


class PatientWater(Base):
    def test_standing_order_shape(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(fort(cancels=["Urist cancels Give water: Need empty bucket."]))
        ov.patient_water()
        got = self.buckets(game)
        self.assertEqual(len(got), 1)
        a = got[0]
        self.assertEqual((a["material_category"], a["amount"], a["repeat"]), (["wood"], harness.BUCKET_KEEP, "monthly"))
        self.assertEqual(a["when"], [{"item_type": "BUCKET", "flags": ["empty"], "below": harness.BUCKET_KEEP},
                                     {"item_type": "WOOD", "at_least": harness.BUCKET_WOOD_FLOOR}])

    def test_the_arguments_pass_the_frozen_schema(self):
        if not (VARIANT.parent / "gameapi" / "facts" / "tools.py").exists():
            self.skipTest("gameapi not beside the submission")
        sys.path.insert(0, str(VARIANT.parent))
        from gameapi.facts import tools as T   # the tool's own argument check (the server runs the same)
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(fort(cancels=["Urist cancels Give water: Need empty bucket."]))
        ov.patient_water()
        spec, _ = T.manager_order_spec(self.buckets(game)[0])
        self.assertEqual(spec["job"], "MakeBucket")
        self.assertEqual(len(spec["item_conditions"]), 2)

    def test_once_per_game(self):
        game = FakeGame()
        ov = self.overseer(game)
        for day in (150, 160, 200):
            ov.load(fort(day=day, cancels=["Urist cancels Give water: Need empty bucket."]))
            ov.patient_water()
        self.assertEqual(len(self.buckets(game)), 1)

    def test_no_carpenters_no_order(self):
        for kw in ({"carpenters": False}, {"built": False}):
            game = FakeGame()
            ov = self.overseer(game)
            ov.load(fort(cancels=["Urist cancels Give water: Need empty bucket."], **kw))
            ov.patient_water()
            self.assertEqual(self.buckets(game), [], kw)

    def test_healthy_fort_orders_nothing_and_short_wood_still_serves_a_patient(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(fort(logs=900, cancels=["Udib cancels Eat: Interrupted by a giant kea."]))
        ov.patient_water()
        self.assertEqual(self.buckets(game), [])
        ov.load(fort(day=151, logs=20, cancels=["Lolor Kolled, manager cancels Give water: Need empty bucket."]))
        self.assertLess(ov.logs(), ov.logs_guard())   # under the furniture guard: a patient's water goes first
        ov.patient_water()
        self.assertEqual(len(self.buckets(game)), 1)

    def test_no_wood_no_order_even_for_a_patient(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(fort(logs=1, cancels=["Urist cancels Give water: Need empty bucket."]))
        ov.patient_water()
        self.assertEqual(self.buckets(game), [])

    def test_patient_log_reasons_and_alert(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(fort(day=224, alert=True, cancels=[
            "Lolor Kolled, manager cancels Give water: No water source.",
            "Kosoth Konosdolek, Planter cancels Give water: No water source.",
            "Atír Usenkol, Carpenter cancels Give Water: Need empty bucket.",
            "Udib, Furnace Operator cancels Eat: Interrupted by a giant kea."]))
        ov.patient_water()
        got = self.logs("patient_water")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["reasons"], {"no water source": 2, "need empty bucket": 1})
        self.assertTrue(got[0]["alert"])
        ov.load(fort(day=224, alert=True, cancels=["X cancels Give water: No water source."]))
        ov.patient_water()   # same day: logged once
        self.assertEqual(len(self.logs("patient_water")), 1)

    def test_a_refused_order_retries_paced(self):
        game = FakeGame(ok=False)
        ov = self.overseer(game)
        ov.load(fort(cancels=["Urist cancels Give water: Need empty bucket."]))
        ov.patient_water()
        ov.load(fort(cancels=["Urist cancels Give water: Need empty bucket."]))
        ov.patient_water()   # same tick: paced by act()
        self.assertEqual(len(self.buckets(game)), 1)
        ov.load(fort(day=153, cancels=["Urist cancels Give water: Need empty bucket."]))
        ov.patient_water()
        self.assertEqual(len(self.buckets(game)), 2)
        self.assertNotIn("o_bucket_prog", ov.done)

    def test_plan_runs_it(self):
        self.assertIn("self.patient_water()", Path(harness.__file__).read_text())


if __name__ == "__main__":
    unittest.main()
