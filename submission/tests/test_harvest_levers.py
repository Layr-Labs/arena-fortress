"""cx regressions: the OP1/MY1 harvest levers (2026-11-10 read of the hint records).

- plant census: plants_brewable counts the ripe crops still standing in the farm plots (observe.lua counts every PLANT
  item; seeds_or_crops_in_plot counts plant and seed items alike). Hint std OP1-0 on a317b90 d39-69: 9 plump helmets
  ripened in place (seeds 60 -> 51, plants 0 -> 9, sown 18 unchanged) and stood 30 days with "Brew drink from plant:
  Needs unrotten fermentable plant"; e538c50 d197-335: seeds 12 -> 2, plants 8 -> 16, sown 22 unchanged to the end.
  The PLANT stock query's in-building items are taken off the plants a Still job can reach (pb_free).
- harvest barrels: the barrels the crops in the plots will want (HARVEST_YIELD a sown tile) open the second Carpenters
  ahead of the harvest (b796327: the 10-barrel one-shot sat 10/0 -> 8/3 d7-34 on one bench; 4-7 empty barrels beside
  pb 16-27 d47-61, 24 plants rotted).
- brew labor press: brew jobs standing untaken at the Stills with empty barrels free while dwarves sit on the wood
  crafts (b796327 d41-71: 1-3 worker-less Still jobs, 0-2 brewers, 1-2 crafters) throttle the crafts; no Still job at
  all (68bd4c7 d122-225: drink over its cap) is not a missing hand.
- meat and alerts: hint hard MY1-1 on 6adf843 marked animals inside alerts (148, 155, 162); the meat rotted in the
  next alert with the Kitchen outside the Shelter. A food slaughter waits while an alert is on or recent.
- population forecast: plots sized for the waves still to come (OP1: two waves of 2-9 at days 87-125 / 172-216; MY1:
  one of 2-10 at days 53-93).
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

ALL = ["spring", "summer", "autumn", "winter"]


class FakeGame:
    def __init__(self, plant_groups=None, animals=()):
        self.calls = []
        self.queries = []
        self.plant_groups = plant_groups
        self.animals = list(animals)

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {"order_id": 900 + len(self.calls)}}

    def query(self, name, **kw):
        self.queries.append((name, kw))
        if name == "stocks" and kw.get("item_type") == "PLANT":
            if self.plant_groups is None:
                return {"error": "unknown_query"}
            return {"result": {"ok": True, "groups": self.plant_groups}}
        if name == "units" and kw.get("kind") == "animals":
            return {"result": {"ok": True, "units": self.animals}}
        return {"result": {"ok": True, "units": [], "groups": []}}


def plot(i, n):
    return {"id": i, "built": True, "w": 3, "h": 3, "z": 159, "seeds_or_crops_in_plot": n,
            "crop_this_season": "MUSHROOM_HELMET_PLUMP", "subterranean": True}


def still(i, workers=()):
    return {"id": i, "type": "Still", "built": True, "x": 98, "y": 92, "z": 159,
            "job_details": [{"job": "CustomReaction", "reaction": "BREW_DRINK_FROM_PLANT", "worker_id": w}
                            for w in workers]}


def resp(day, days=336, cit=7, pb=20, barrels=6, plots=(9,) * 6, seeds=60, drink=230, food=80, meals=30,
         stills=((None, None),), carpenters=1, crafters=1, alert=False, kitchen=(93, 101, 142),
         shelter=(88, 104, 87, 92, 140, 141), orders=(), hands_off=None, rotten=0):
    dwarves = [{"id": 90 + i, "job": "MakeCrafts" if i < crafters else "idle"} for i in range(cit)]
    shops = [{"id": 1, "type": "Kitchen", "built": True, "x": kitchen[0], "y": kitchen[1], "z": kitchen[2]}]
    shops += [{"id": 10 + i, "type": "Carpenters", "built": True} for i in range(carpenters)]
    shops += [still(20 + i, w) for i, w in enumerate(stills)]
    shops += [{"id": 40, "type": "Craftsdwarfs", "built": True}]
    stocks = {"drink": drink, "food_edible": food, "prepared_meals": meals, "plants_brewable": pb,
              "plants_total": pb, "plants_rotten": rotten, "barrels_empty": barrels, "logs_usable": 200,
              "seeds": seeds, "seeds_by_kind": {"plump helmet": {"n": seeds, "seasons": ALL, "underground": True}},
              "plants_by_kind": {"plump helmet": {"n": pb, "brewable": True, "cookable": True}} if pb else {},
              "beds": 13, "tables": 9, "chairs": 8, "furniture_free": {}}
    x1, x2, y1, y2, z1, z2 = shelter
    obs = {"date": {"abs_tick": day * harness.DAY, "day_of_year": (15 + day) % harness.YEAR_DAYS},
           "administrators": {"citizens": cit, "manager_active_for_orders": True}, "stocks": stocks,
           "map": {"sites": [{"id": "W5", "kind": "W", "x": 60, "y": 60, "z": 160, "w": 3, "h": 3, "free": True}]},
           "zones": [], "furniture": [], "wealth": {"created": 3000},
           "dwarves": dwarves, "workshops": shops, "orders": list(orders),
           "farm_plots": [plot(i, n) for i, n in enumerate(plots)],
           "burrows": {"civilian_alert": alert, "list": [
               {"id": 0, "name": "Shelter", "civ_alert_burrow": True,
                "bbox": {"x1": x1, "x2": x2, "y1": y1, "y2": y2, "z1": z1, "z2": z2}}]}}
    r = {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": days - day}
    if hands_off is not None:
        r["hands_off_in_days"] = hands_off
    return r


def brew_order(oid=7, left=10):
    return {"id": oid, "job": "CustomReaction", "reaction": "BREW_DRINK_FROM_PLANT", "recipe": "brew_drink",
            "left": left, "total": left, "active": True, "validated": True, "jobs_in_progress": 2, "repeat": None}


def crafts_order(oid=15, amount=12):
    return {"id": oid, "job": "MakeCrafts", "material_category": ["wood"], "left": amount, "total": amount,
            "active": True, "validated": True, "jobs_in_progress": 1, "repeat": "daily"}


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


class PlantCensus(Base):
    # the real answer's units: free stacks of 5 (a PLANT answer read items 6, count 30) beside 9 ripe crops standing
    # one plant each in their plots — items 13, count 29, plants_brewable 29
    GROUPS = [{"item_type": "PLANT", "material": "PLANT:MUSHROOM_HELMET_PLUMP:STRUCTURAL", "items": 13, "count": 29,
               "rotten": 0, "forbidden": 0, "in_job": 0, "in_building": 9, "in_inventory": 0, "construction": 0}]

    def test_ripe_crops_in_the_plots_are_not_free_for_the_still(self):
        ov, game = self.ov(plant_groups=self.GROUPS)
        self.load(ov, resp(45, pb=29))
        ov.plant_census()
        self.assertEqual(ov.in_plot, {"total": 9, "brewable": 9, "items": 9})
        self.assertEqual(ov.pb_free(), 20)   # in units: the 20 in the free stacks
        self.assertIn(("stocks", {"item_type": "PLANT"}), game.queries)

    def test_once_a_day_and_a_refusal_keeps_the_reading(self):
        ov, game = self.ov(plant_groups=self.GROUPS)
        self.load(ov, resp(45))
        ov.plant_census()
        ov.plant_census()
        self.assertEqual(sum(1 for q in game.queries if q[0] == "stocks"), 1)
        game.plant_groups = None   # the next day's query is refused
        self.load(ov, resp(46))
        ov.plant_census()
        self.assertEqual(ov.in_plot, {"total": 9, "brewable": 9, "items": 9})

    def test_a_group_wholly_in_buildings_gives_its_units(self):
        groups = [dict(self.GROUPS[0], items=4, count=12, in_building=4)]   # stacks of 3, every one in a building
        ov, _ = self.ov(plant_groups=groups)
        self.load(ov, resp(45, pb=12))
        ov.plant_census()
        self.assertEqual(ov.in_plot, {"total": 12, "brewable": 12, "items": 4})
        self.assertEqual(ov.pb_free(), 0)

    def test_no_reading_leaves_pb_as_observed(self):
        ov, _ = self.ov(plant_groups=None)
        self.load(ov, resp(45, pb=20))
        ov.plant_census()
        self.assertIsNone(ov.in_plot)
        self.assertEqual(ov.pb_free(), 20)

    def test_job_items_and_non_brewable_kinds(self):
        groups = [dict(self.GROUPS[0], in_building=5, in_job=2),
                  {"item_type": "PLANT", "material": "PLANT:BUSH_QUARRY:STRUCTURAL", "items": 4, "count": 4,
                   "rotten": 0, "in_job": 0, "in_building": 4}]
        ov, _ = self.ov(plant_groups=groups)
        self.load(ov, resp(45, pb=29))
        ov.plant_census()
        # plants at a job are not crops in a plot
        self.assertEqual(ov.in_plot, {"total": 7, "brewable": 3, "items": 7})

    def test_a_stall_is_logged_once_after_its_days(self):
        ov, _ = self.ov(plant_groups=self.GROUPS)
        for day in range(40, 40 + harness.HARVEST_STALL_DAYS + 3):
            self.load(ov, resp(day))
            ov.plant_census()
        stalls = self.logs("harvest_stall")
        self.assertEqual(len(stalls), 1)
        self.assertEqual(stalls[0]["since"], 40)


class HarvestBarrels(Base):
    def test_the_crops_in_the_plots_want_barrels_at_the_measured_yield(self):
        ov, _ = self.ov()
        self.load(ov, resp(20, pb=0, barrels=1, plots=(9, 9, 5, 0, 0, 0)))
        # 23 seeds sown -> 27.6 plants -> 28 barrels, less the 1 empty
        self.assertEqual(ov.harvest_barrels_short(), 27)
        self.load(ov, resp(21, pb=10, barrels=1, plots=(9,) * 6))
        self.assertEqual(ov.harvest_barrels_short(), harness.BARREL_AHEAD_MAX - 1)   # capped

    def test_a_ripe_crop_counts_as_itself(self):
        ov, _ = self.ov()
        self.load(ov, resp(50, pb=9, barrels=0, plots=(9, 9, 0, 0, 0, 0)))
        ov.in_plot = {"total": 9, "brewable": 9}
        # pb_free 0 + 9 seeds * 1.2 + 9 ripe = 19.8 -> 20
        self.assertEqual(ov.harvest_barrels_short(), 20)

    def test_not_on_a_lab_task_or_a_short_run(self):
        ov, _ = self.ov(days=90)
        self.load(ov, resp(20, days=90, pb=0, barrels=0, hands_off=40))
        self.assertEqual(ov.harvest_barrels_short(), 0)
        ov2, _ = self.ov(days=216)
        self.load(ov2, resp(20, days=216, pb=0, barrels=0))
        self.assertEqual(ov2.harvest_barrels_short(), 0)   # MY1: until its plants rot

    def test_the_second_carpenters_opens_ahead_of_the_harvest(self):
        ov, game = self.ov()
        self.load(ov, resp(7, pb=0, barrels=0, plots=(9, 9, 0, 0, 0, 0), stills=((),)))
        ov.workshops()
        self.assertTrue(any(t == "build_workshop" and a.get("type") == "Carpenters" for t, a in game.calls))
        ov2, game2 = self.ov()
        self.load(ov2, resp(7, pb=0, barrels=10, plots=(9, 0, 0, 0, 0, 0), stills=((),)))
        ov2.workshops()   # 11 wanted, 10 empty: not short enough
        self.assertFalse(any(t == "build_workshop" and a.get("type") == "Carpenters" for t, a in game2.calls))


class LaborPress(Base):
    def test_untaken_brew_jobs_throttle_the_crafts(self):
        ov, game = self.ov()
        self.load(ov, resp(47, pb=16, barrels=6, stills=((None, 93), (None,), ()),
                           orders=(brew_order(), crafts_order())))
        self.assertTrue(ov.labor_press())
        ov.barrel_press()
        self.assertFalse(ov.press_stand)      # barrels > PRESS_BARRELS_LOW: the standing reading stays off
        self.assertTrue(ov.press_harv)        # (54 tiles sown: the harvest reading presses, 6 barrels for ~80)
        self.assertTrue(ov.craft_press())
        self.assertIn(("cancel_order", {"order_id": 15}), game.calls)

    def test_no_still_job_is_not_a_missing_hand(self):
        ov, _ = self.ov()
        self.load(ov, resp(122, pb=16, barrels=14, stills=((), (), ()), crafters=4,
                           orders=(brew_order(),)))
        self.assertFalse(ov.labor_press())

    def test_held_off_by_alert_caravan_and_the_embark_days(self):
        for kw, day in ((dict(alert=True), 47), ({}, 10)):
            ov, _ = self.ov()
            self.load(ov, resp(day, pb=16, stills=((None,),), orders=(brew_order(),), **kw))
            self.assertFalse(ov.labor_press(), kw)
        ov, _ = self.ov()
        ov.caravan_active = True
        self.load(ov, resp(47, pb=16, stills=((None,),), orders=(brew_order(),)))
        ov.caravan_active = True
        ov.labor_memo = None
        self.assertFalse(ov.labor_press())

    def test_needs_someone_on_the_crafts_and_plants_the_still_can_reach(self):
        ov, _ = self.ov()
        self.load(ov, resp(47, pb=16, stills=((None,),), crafters=0, orders=(brew_order(),)))
        self.assertFalse(ov.labor_press())
        ov2, _ = self.ov()
        self.load(ov2, resp(47, pb=16, stills=((None,),), orders=(brew_order(),)))
        ov2.in_plot = {"total": 16, "brewable": 16}   # every plant still in the plots
        self.assertFalse(ov2.labor_press())

    def test_releases_when_nothing_waits_or_no_job_stands_twice(self):
        ov, _ = self.ov()
        self.load(ov, resp(47, pb=16, stills=((None,),), orders=(brew_order(),)))
        self.assertTrue(ov.labor_press())
        self.load(ov, resp(48, pb=16, stills=((),), orders=(brew_order(),)))
        self.assertTrue(ov.labor_press())    # one look without a Still job
        self.load(ov, resp(49, pb=16, stills=((),), orders=(brew_order(),)))
        self.assertFalse(ov.labor_press())   # two
        self.load(ov, resp(50, pb=16, stills=((None,),), orders=(brew_order(),)))
        self.assertTrue(ov.labor_press())
        self.load(ov, resp(51, pb=0, stills=((None,),), orders=(brew_order(),)))
        self.assertFalse(ov.labor_press())


class SlaughterAndAlerts(Base):
    ANIMAL = [{"id": 300, "tame": True, "pet_owner_id": None, "marked_for_slaughter": False}]

    def slaughtered(self, game):
        return [a for t, a in game.calls if t == "slaughter"]

    def test_no_food_slaughter_inside_an_alert_with_the_kitchen_outside(self):
        ov, game = self.ov(animals=self.ANIMAL)
        self.load(ov, resp(148, alert=True))
        ov.butcher()
        self.assertEqual(self.slaughtered(game), [])
        self.load(ov, resp(150))   # lifted 2 days ago
        ov.butcher()
        self.assertEqual(self.slaughtered(game), [])
        self.load(ov, resp(148 + harness.ALERT_QUIET_DAYS + 1))
        ov.butcher()
        self.assertEqual(self.slaughtered(game), [{"unit_id": 300}])

    def test_a_sheltered_kitchen_keeps_the_slaughter(self):
        ov, game = self.ov(animals=self.ANIMAL)
        self.load(ov, resp(148, alert=True, kitchen=(95, 90, 141)))
        self.assertTrue(ov.kitchen_sheltered())
        ov.butcher()
        self.assertEqual(self.slaughtered(game), [{"unit_id": 300}])

    def test_a_moods_bones_are_never_held(self):
        ov, game = self.ov(animals=self.ANIMAL)
        self.load(ov, resp(148, alert=True))
        ov.butcher(for_food=False)
        self.assertEqual(self.slaughtered(game), [{"unit_id": 300}])


class PopulationForecast(Base):
    def test_embark_fort_expects_two_waves(self):
        ov, _ = self.ov()
        self.load(ov, resp(10, cit=7))
        self.assertEqual(ov.pop_forecast(), 18)          # 7 + 2 * 5.5
        self.load(ov, resp(11, cit=8))                     # a birth is not a wave
        self.assertEqual(ov.mig_waves, 0)
        self.load(ov, resp(106, cit=14))
        self.assertEqual(ov.mig_waves, 1)
        self.assertEqual(ov.pop_forecast(), 20)          # 14 + 5.5
        self.load(ov, resp(203, cit=22))
        self.assertEqual(ov.pop_forecast(), 22)          # both waves in
        self.assertEqual(len(self.logs("pop_wave")), 2)

    def test_a_handover_fort_has_taken_one_wave(self):
        ov, _ = self.ov(days=216)
        self.load(ov, resp(5, days=216, cit=15))
        self.assertEqual(ov.pop_forecast(), 21)
        self.assertEqual(ov.farm_target(), 5)            # ceil(21 / 5) — the census alone gives 3 -> 4

    def test_no_forecast_on_a_lab_task_or_late(self):
        ov, _ = self.ov(days=90)
        self.load(ov, resp(5, days=90, cit=7, hands_off=60))
        self.assertEqual(ov.pop_forecast(), 7)
        ov2, _ = self.ov()
        self.load(ov2, resp(336 - harness.HOLD_GROW_DAYS, cit=7))
        self.assertEqual(ov2.pop_forecast(), 7)

    def test_full_year_plots_follow_the_forecast(self):
        ov, _ = self.ov()
        self.load(ov, resp(10, cit=7, seeds=40))
        self.assertEqual(ov.farm_target(), 6)            # 18 -> 6
        self.load(ov, resp(106, cit=15, seeds=40))
        self.assertEqual(ov.farm_target(), 7)            # 15 + 5.5 -> 21 -> 7 (the census alone: 5 -> 6)


if __name__ == "__main__":
    unittest.main()
