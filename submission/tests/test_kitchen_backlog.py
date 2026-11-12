"""cx KITCHEN BACKLOG (hint std OP1-3 on 014f7eb, 2026-11-11, food leg 0.79). One Kitchen never finished its daily
o_cook from d320 to d330 while the one-shot cook batches 136 (5), 138 (4) and 139 (4) stood with no job and the 23
loose plump helmets rotted (plants_rotten 3 -> 20 on d320-335). A full-year open-play fort with KITCHEN_BACKLOG
queued one-shot cook jobs while its plants rot or age opens a second Kitchen (a work order spreads its jobs over every
workshop of its type). No game or network."""
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

PLUMP = {"plump helmet": {"n": 35, "seasons": ["spring", "summer", "autumn", "winter"], "underground": True}}
SHOPS = ("Carpenters", "Carpenters", "Still", "Still", "Still", "Kitchen", "Fishery", "Butchers")
DAILY = {"id": 135, "recipe": "cook_meal", "job": "PrepareMeal", "repeat": "daily", "left": 2, "total": 2,
         "active": True, "validated": True, "jobs_in_progress": 1,
         "when": [{"item_type": "FOOD", "test": "LessThan", "value": 200, "stock": "prepared_meals"}]}


def shot(oid, left, active=True):
    return {"id": oid, "recipe": "cook_meal", "job": "PrepareMeal", "left": left, "total": left, "active": active,
            "validated": active, "jobs_in_progress": 0}


# the record's book on d317: o_cook_meat 136 (5), o_cook_alloc 138 (4), o_cook_rot 139 (4) beside the daily o_cook
BOOK = (DAILY, shot(136, 5), shot(138, 4), shot(139, 4))
W8 = {"id": "W8", "kind": "W", "x": 80, "y": 90, "z": 150, "w": 3, "h": 3}


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, json.loads(json.dumps(args))))
        return {"ok": True, "result": {"order_id": 500 + len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {"units": []}}


def resp(day, orders=BOOK, shops=SHOPS, rot=3, pb=23, logs=60, days=336, hands_off=None, sites=(W8,), jobs=None,
         food=176):
    stocks = {"drink": 905, "food_edible": food, "prepared_meals": 153, "plants_brewable": pb, "plants_total": pb,
              "plants_rotten": rot, "barrels_empty": 34, "logs_usable": logs, "seeds": 35, "seeds_by_kind": PLUMP,
              "beds": 21, "tables": 9, "chairs": 9, "furniture_free": {}}
    obs = {"date": {"abs_tick": day * harness.DAY, "day_of_year": (15 + day) % harness.YEAR_DAYS},
           "administrators": {"citizens": 21, "manager_active_for_orders": True}, "stocks": stocks,
           "map": {"sites": [dict(s) for s in sites]}, "zones": [], "furniture": [], "wealth": {"created": 17000},
           "workshops": [dict({"id": i, "type": w, "built": True},
                              **({"job_details": list(jobs)} if jobs is not None and w == "Kitchen" else {}))
                         for i, w in enumerate(shops)], "orders": list(orders),
           "farm_plots": [{"id": i, "z": 149, "seeds_or_crops_in_plot": 5} for i in range(6)]}
    r = {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": days - day}
    if hands_off is not None:
        r["hands_off_in_days"] = hands_off
    return r


class KitchenBacklog(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def run_with(self, days=336, rot_seen=True, **kw):
        game = FakeGame()
        ov = harness.Overseer(game, days=days)
        ov.load(resp(317, days=days, **kw))
        ov.count = 0
        ov.rot_seen = rot_seen
        ov.workshops()
        kitchens = [a for t, a in game.calls if t == "build_workshop" and a.get("type") == "Kitchen"]
        return ov, kitchens

    def test_backlog_with_rotting_plants_opens_a_second_kitchen(self):
        ov, kitchens = self.run_with()
        self.assertEqual(kitchens, [{"site": "W8", "type": "Kitchen"}])

    def test_unvalidated_batches_count_too(self):
        # d309 in the record: 138 and 139 were just added (active false, not yet validated by the manager)
        ov, kitchens = self.run_with(orders=(DAILY, shot(136, 5), shot(138, 4, False), shot(139, 4, False)))
        self.assertEqual(len(kitchens), 1)

    def test_small_backlog_keeps_one_kitchen(self):
        ov, kitchens = self.run_with(orders=(DAILY, shot(136, 5), shot(139, 2)))
        self.assertEqual(kitchens, [])

    def test_the_daily_standing_is_not_a_backlog(self):
        many = dict(DAILY, left=20, total=20)
        ov, kitchens = self.run_with(orders=(many,))
        self.assertEqual(kitchens, [])

    def test_no_rot_and_no_aged_plants_keeps_one_kitchen(self):
        ov, kitchens = self.run_with(rot_seen=False)
        self.assertEqual(kitchens, [])

    def test_two_kitchens_are_the_cap(self):
        ov, kitchens = self.run_with(shops=SHOPS + ("Kitchen",))
        self.assertEqual(kitchens, [])

    def test_no_kitchen_is_the_rebuild_not_the_backlog(self):
        shops = tuple(s for s in SHOPS if s != "Kitchen")
        ov, kitchens = self.run_with(shops=shops)
        self.assertEqual(len(kitchens), 1)          # the ordinary rebuild, keyed ws_Kitchen
        self.assertIn("ws_Kitchen", ov.last)
        self.assertNotIn("ws_Kitchen_2", ov.last)

    def test_handover_fort_and_short_runs_never_open_one(self):
        ov, kitchens = self.run_with(days=216)
        self.assertEqual(kitchens, [])
        ov, kitchens = self.run_with(days=60, hands_off=21)
        self.assertEqual(kitchens, [])

    def test_no_wood_no_kitchen(self):
        ov, kitchens = self.run_with(logs=2)
        self.assertEqual(kitchens, [])


LEAN = {"sides": ["cook"], "lean": True, "hold": False, "last": True, "build": False, "floor": 2, "rot_keep": 2,
        "f_need": 11, "reserve": 42, "run_out": [False, False], "food_first": False, "in_f": False}
DAILY_JOB = {"by_manager": True, "job": "PrepareMeal", "order_id": 135, "worker_id": 93}


class KitchenStall(unittest.TestCase):
    """cx KITCHEN STALL: the at-risk plants of a food-lean fort go to the Stills once the Kitchen has not taken the rot
    batch (or has held another order's job) for COOK_STALL_DAYS; never inside F while food falls over the stretch."""

    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, plan=LEAN):
        game = FakeGame()
        ov = harness.Overseer(game, days=336)
        ov.plant_plan = lambda: dict(plan)
        return ov, game

    def look(self, ov, day, **kw):
        ov.load(resp(day, **kw))
        ov.count = 0
        ov.rot_seen = True
        ov.plant_age = [[day - 12, 15]]   # 15 loose plants 12 days old: past PLANT_USE_AGE
        ov.rot_guard()

    @staticmethod
    def adds(game, recipe):
        return [a for t, a in game.calls if t == "add_order" and a.get("recipe") == recipe]

    def test_busy_kitchen_for_a_day_brews_the_aged_plants(self):
        ov, game = self.ov()
        self.look(ov, 290, orders=(DAILY,), jobs=[DAILY_JOB], pb=17)
        self.assertEqual(self.adds(game, "brew_drink"), [])          # busy for less than a day: the Kitchen's turn
        game.calls.clear()
        self.look(ov, 291, orders=(DAILY,), jobs=[DAILY_JOB], pb=17)
        brews = self.adds(game, "brew_drink")
        self.assertEqual(len(brews), 1)
        self.assertEqual(brews[0]["amount"], 15)                      # the 15 aged plants, the keep's 2 stay
        self.assertEqual(self.adds(game, "cook_meal"), [])
        oid = ov.key_order.get("o_brew_rot")
        self.assertIn(oid, ov.stall_brews)

    def test_a_rot_batch_with_no_job_for_a_day_brews(self):
        ov, game = self.ov()
        self.look(ov, 300, orders=(DAILY,), jobs=[], pb=17)
        cooks = self.adds(game, "cook_meal")
        self.assertEqual(len(cooks), 1)                               # the Kitchen idle: the rot batch goes there
        rot = dict(shot(ov.key_order["o_cook_rot"], cooks[0]["amount"]))
        game.calls.clear()
        self.look(ov, 300.5, orders=(DAILY, rot), jobs=[DAILY_JOB], pb=17)
        self.assertEqual(self.adds(game, "brew_drink"), [])
        self.look(ov, 301.5, orders=(DAILY, rot), jobs=[DAILY_JOB], pb=17)
        self.assertEqual(len(self.adds(game, "brew_drink")), 1)

    def test_the_kitchen_on_the_rot_batch_keeps_cooking(self):
        ov, game = self.ov()
        self.look(ov, 300, orders=(DAILY,), jobs=[], pb=17)
        oid = ov.key_order["o_cook_rot"]
        rot = dict(shot(oid, 4), jobs_in_progress=1)
        mine = dict(DAILY_JOB, order_id=oid)
        for day in (301, 302, 303):
            self.look(ov, day, orders=(DAILY, rot), jobs=[mine], pb=17)
        self.assertEqual(self.adds(game, "brew_drink"), [])

    def test_inside_f_with_food_falling_no_stall_brew(self):
        ov, game = self.ov(dict(LEAN, in_f=True))
        for day, food in ((306, 209), (310, 202), (314, 190), (318, 176), (320, 174)):
            self.look(ov, day, orders=(DAILY,), jobs=[DAILY_JOB], pb=20, food=food)
        self.assertEqual(self.adds(game, "brew_drink"), [])
        self.assertTrue(ov.f_food_falling())

    def test_inside_f_with_food_rising_the_stall_brews(self):
        ov, game = self.ov(dict(LEAN, in_f=True))
        for day, food in ((306, 170), (310, 175), (314, 180), (318, 186), (320, 190)):
            self.look(ov, day, orders=(DAILY,), jobs=[DAILY_JOB], pb=20, food=food)
        self.assertFalse(ov.f_food_falling())
        self.assertGreaterEqual(len(self.adds(game, "brew_drink")), 1)

    def test_lean_supply_spares_the_stall_brews(self):
        ov, game = self.ov()
        self.look(ov, 290, orders=(DAILY,), jobs=[DAILY_JOB], pb=17)
        self.look(ov, 291, orders=(DAILY,), jobs=[DAILY_JOB], pb=17)
        oid = ov.key_order["o_brew_rot"]
        brew = {"id": oid, "recipe": "brew_drink", "job": "CustomReaction", "left": 15, "total": 15, "active": True}
        ov.load(resp(292, orders=(DAILY, brew), jobs=[DAILY_JOB], pb=17))
        ov.count = 0
        ov.food_lean = lambda: True
        game.calls.clear()
        ov.lean_supply()
        self.assertNotIn(("cancel_order", {"order_id": oid}), game.calls)


if __name__ == "__main__":
    unittest.main()
