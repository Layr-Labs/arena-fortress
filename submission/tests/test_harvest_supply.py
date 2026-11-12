"""cx regressions (2026-11-11 read of the hint OP1 records): the harvest press's benches and furniture, the pre-rot
guard, the drink glut and the wood dry.

- benches: past PRESS_CARPENTERS the harvest press opens a fifth/sixth Carpenters only while every bench holds a
  MakeBarrel job and a citizen stood idle on the last two observed days (9c4ec71 OP1-0 d57-80: 4 benches, one barrel
  job each, 0.8-0.9 barrels/day).
- furniture: while the harvest press holds, this layer's beds/tables/chairs fall to the census's scored need and its
  own one-shots past it are cancelled (the same record: beds 8, tables 6, chairs 8 queued on the 2 benches from day 5
  beside the one MakeBarrel job); the margins come back on release and in the last ENDGAME_DAYS.
- pre-rot guard: plants harvested d36-38 rotted d52 (0c8ca4b OP1-4), d46-51 -> d63 (9c4ec71 OP1-0), d50-53 -> d67
  (80e9f9d OP1-4); loose plants PLANT_USE_AGE days old are brewed before any rot (OP1 only; the embark stock does not
  age).
- drink glut: 80e9f9d OP1-1 drink 302 -> 950 for 16-18 citizens (336-day cover ~500) while food stood 229-289; past
  DRINK_GLUT_MARGIN covers only the aged plants are taken, and to the Kitchen while barrels are short; no glut bank.
- wood dry: the same record felled nothing after d119 and logs ran 191 -> 7; with no felling and no log rise for
  WOOD_DRY_DAYS under WOOD_DRY_LOGS, the wood crafts stop.
No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness
from test_harvest_levers import FakeGame, crafts_order, resp

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__


def with_barrel_jobs(r, benches=None):
    for w in r["observation"]["workshops"]:
        if w["type"] == "Carpenters" and (benches is None or w["id"] in benches):
            w["job_details"] = [{"job": "MakeBarrel", "by_manager": True, "order_id": 4}]
    return r


def own(ov, key, oid):
    ov.key_order[key] = oid
    ov.owned.add(oid)


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, days=336, **kw):
        game = FakeGame(**kw)
        return harness.Overseer(game, days=days), game

    @staticmethod
    def load(ov, r):
        ov.load(r)
        ov.count = 0

    @staticmethod
    def built(game):
        return [a for t, a in game.calls if t == "build_workshop" and a.get("type") == "Carpenters"]

    def logs(self, kind):
        import json
        out = []
        for line in self.output._new_target.getvalue().splitlines():
            try:
                j = json.loads(line)
            except ValueError:
                continue
            if j.get("kind") == kind:
                out.append(j)
        return out


class HarvestBenches(Base):
    def test_a_fifth_bench_when_every_bench_has_a_barrel_job_and_hands_idle(self):
        ov, game = self.ov()
        self.load(ov, with_barrel_jobs(resp(40, pb=0, barrels=2, plots=(9,) * 5, carpenters=4)))
        self.load(ov, with_barrel_jobs(resp(41, pb=0, barrels=2, plots=(9,) * 5, carpenters=4)))
        self.assertTrue(ov.barrel_press() and ov.press_harv)
        ov.workshops()
        self.assertEqual(len(self.built(game)), 1)

    def test_no_fifth_bench_while_a_bench_has_no_barrel_job(self):
        ov, game = self.ov()
        for day in (40, 41):
            self.load(ov, with_barrel_jobs(resp(day, pb=0, barrels=2, plots=(9,) * 5, carpenters=4), benches={10, 11}))
        ov.workshops()
        self.assertEqual(self.built(game), [])

    def test_no_fifth_bench_without_idle_hands_on_two_days(self):
        ov, game = self.ov()
        self.load(ov, with_barrel_jobs(resp(40, pb=0, barrels=2, plots=(9,) * 5, carpenters=4, crafters=7)))
        self.load(ov, with_barrel_jobs(resp(41, pb=0, barrels=2, plots=(9,) * 5, carpenters=4)))
        ov.workshops()
        self.assertEqual(self.built(game), [])

    def test_never_past_the_cap(self):
        ov, game = self.ov()
        for day in (40, 41):
            self.load(ov, with_barrel_jobs(resp(day, pb=0, barrels=2, plots=(9,) * 5,
                                                carpenters=harness.HARVEST_CARPENTERS)))
        ov.workshops()
        self.assertEqual(self.built(game), [])


class HarvestFurniture(Base):
    def test_own_furniture_past_the_census_need_yields_its_bench(self):
        ov, game = self.ov()
        table = {"id": 6, "job": "ConstructTable", "recipe": "make_table", "left": 3, "total": 6, "active": True}
        own(ov, "o_make_table", 6)
        r = resp(30, pb=0, barrels=2, plots=(9,) * 5, orders=(table,))
        r["observation"]["stocks"].update(beds=7, tables=4, chairs=6)
        self.load(ov, r)
        self.assertTrue(ov.harvest_furniture_lean())
        ov.supply()
        self.assertIn(("cancel_order", {"order_id": 6}), game.calls)
        self.assertEqual(self.logs("furniture_yield")[0]["recipe"], "make_table")
        self.assertFalse(any(t == "add_order" and a.get("recipe") in ("make_bed", "make_table", "make_chair")
                             for t, a in game.calls))   # 7 beds for 7, 4 tables for 4, chairs 6 >= 4 + 1 + heads

    def test_the_census_need_is_still_made(self):
        ov, game = self.ov()
        r = resp(30, pb=0, barrels=2, plots=(9,) * 5)
        r["observation"]["stocks"].update(beds=3, tables=1, chairs=1)
        self.load(ov, r)
        ov.supply()
        beds = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "make_bed"]
        self.assertEqual(beds[0]["amount"], 4)   # to the 7 citizens, not the +FULL_YEAR_BEDS margin

    def test_the_margins_return_without_the_press_or_near_the_end(self):
        ov, _ = self.ov()
        self.load(ov, resp(30, pb=0, barrels=40, plots=(0,) * 6))
        self.assertFalse(ov.harvest_furniture_lean())
        ov2, _ = self.ov()
        self.load(ov2, resp(336 - harness.ENDGAME_DAYS + 1, pb=0, barrels=2, plots=(9,) * 5))
        self.assertTrue(ov2.press_harv or ov2.barrel_press())
        self.assertFalse(ov2.harvest_furniture_lean())

    def test_the_model_s_furniture_order_is_left_alone(self):
        ov, game = self.ov()
        chairs = {"id": 77, "job": "ConstructThrone", "recipe": "make_chair", "left": 5, "total": 8, "active": True}
        r = resp(30, pb=0, barrels=2, plots=(9,) * 5, orders=(chairs,))
        r["observation"]["stocks"].update(beds=7, tables=4, chairs=9)
        self.load(ov, r)
        ov.supply()
        self.assertNotIn(("cancel_order", {"order_id": 77}), game.calls)


class PreRotGuard(Base):
    def run_days(self, ov, seq, **kw):
        for day in seq:
            self.load(ov, resp(day, **kw))
            ov.rot_guard()

    def test_loose_plants_brew_before_they_rot(self):
        ov, game = self.ov()
        self.run_days(ov, (36, 40), pb=6, barrels=11, drink=201, plots=(9,) * 6)
        self.assertEqual([a for t, a in game.calls if t == "add_order"], [])   # 4 days old: not yet
        self.run_days(ov, (44,), pb=6, barrels=11, drink=201, plots=(9,) * 6)
        brews = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"]
        self.assertEqual(len(brews), 1)
        self.assertLessEqual(brews[0]["amount"], 6)
        self.assertFalse(ov.rot_seen)

    def test_fresh_plants_wait_and_consumption_takes_the_oldest(self):
        ov, game = self.ov()
        self.run_days(ov, (36,), pb=6, barrels=11, plots=(9,) * 6)
        self.run_days(ov, (40,), pb=10, barrels=11, plots=(9,) * 6)    # +4 new
        self.run_days(ov, (42,), pb=5, barrels=11, plots=(9,) * 6)     # 5 taken: the 6 oldest -> 1 left
        self.assertEqual(ov.plant_age[0][1], 1)
        self.run_days(ov, (44,), pb=5, barrels=11, plots=(9,) * 6)
        self.assertEqual(ov.aged_plants(), 1)

    def test_the_embark_stock_does_not_age(self):
        ov, game = self.ov()
        self.run_days(ov, (0, 9, 12), pb=30, barrels=2, plots=(0,) * 6)
        self.assertEqual(ov.aged_plants(), 0)
        self.assertEqual(game.calls, [])

    def test_not_on_my1(self):
        ov, game = self.ov(days=216)
        self.run_days(ov, (40, 60), days=216, pb=50, barrels=3, plots=(9,) * 6)
        self.assertEqual(ov.aged_plants(), 0)
        self.assertEqual(game.calls, [])


class DrinkGlut(Base):
    def glut(self, ov, day, barrels, pb=12):
        r = resp(day, cit=18, pb=pb, barrels=barrels, drink=950, food=230, seeds=80, plots=(9,) * 6)
        self.load(ov, r)

    def test_glut_reading(self):
        ov, _ = self.ov()
        self.glut(ov, 200, barrels=2)
        self.assertTrue(ov.drink_glut())
        r = resp(201, cit=18, pb=12, barrels=2, drink=400, food=230, seeds=80, plots=(9,) * 6)
        self.load(ov, r)
        self.assertFalse(ov.drink_glut())

    def test_aged_plants_go_to_the_kitchen_while_barrels_are_short(self):
        ov, game = self.ov()
        self.glut(ov, 200, barrels=2)
        self.glut(ov, 210, barrels=2)
        ov.rot_guard()
        self.assertTrue(any(t == "add_order" and a.get("recipe") == "cook_meal" for t, a in game.calls))
        self.assertFalse(any(t == "add_order" and a.get("recipe") == "brew_drink" for t, a in game.calls))

    def test_with_free_barrels_the_aged_plants_brew(self):
        ov, game = self.ov()
        self.glut(ov, 200, barrels=20)
        self.glut(ov, 210, barrels=20)
        ov.rot_guard()
        self.assertTrue(any(t == "add_order" and a.get("recipe") == "brew_drink" for t, a in game.calls))

    def test_a_rotting_fort_past_the_glut_brews_only_the_aged(self):
        ov, game = self.ov()
        ov.rot_seen = True
        self.glut(ov, 200, barrels=20, pb=12)
        ov.rot_guard()                                   # nothing aged yet: the guard leaves the fresh plants
        self.assertFalse(any(t == "add_order" and a.get("recipe") == "brew_drink" for t, a in game.calls))

    def test_no_glut_bank(self):
        ov, game = self.ov()
        self.glut(ov, 200, barrels=20, pb=60)
        ov.glut_bank()
        self.assertEqual(game.calls, [])


class WoodDry(Base):
    def day(self, ov, day, logs, fell=False, orders=()):
        r = resp(day, pb=0, barrels=20, plots=(0,) * 6, orders=orders)
        r["observation"]["stocks"]["logs_usable"] = logs
        if fell:
            r["observation"]["dwarves"][-1]["job"] = "FellTree"
        self.load(ov, r)

    def test_no_felling_and_falling_logs_under_the_mark(self):
        ov, _ = self.ov()
        for i, day in enumerate(range(150, 172, 2)):
            self.day(ov, day, 100 - 2 * i)
        self.assertTrue(ov.wood_dry())

    def test_a_felling_or_a_rise_is_not_dry(self):
        ov, _ = self.ov()
        for i, day in enumerate(range(150, 172, 2)):
            self.day(ov, day, 100 - 2 * i, fell=(day == 160))
        self.assertFalse(ov.wood_dry())
        ov2, _ = self.ov()
        for i, day in enumerate(range(150, 172, 2)):
            self.day(ov2, day, 80 + (5 if day == 166 else 0))
        self.assertFalse(ov2.wood_dry())

    def test_high_stock_or_short_history_is_not_dry(self):
        ov, _ = self.ov()
        for i, day in enumerate(range(150, 172, 2)):
            self.day(ov, day, 140 - i)
        self.assertFalse(ov.wood_dry())
        ov2, _ = self.ov()
        for day in (150, 155):
            self.day(ov2, day, 50)
        self.assertFalse(ov2.wood_dry())

    def test_the_wood_crafts_stop(self):
        ov, game = self.ov()
        for i, day in enumerate(range(150, 172, 2)):
            self.day(ov, day, 80 - i, orders=(crafts_order(amount=1),))
        self.assertTrue(ov.craft_press())
        self.assertIn(("cancel_order", {"order_id": 15}), game.calls)
        self.assertEqual(len(self.logs("wood_dry")), 1)


if __name__ == "__main__":
    unittest.main()
