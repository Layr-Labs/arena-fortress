"""cx order audit (70 hint runs, 2026-11-10): the supply layer's orders against the game's own semantics.

- SEEDS: the game's SEEDS item condition counts the free seeds only (the sown ones stand in the plots, in a building):
  the cook standings' bank floor (seed_floor, size kept) goes out as the free seeds it still needs (seed_need), the
  layer's checks read free seeds, and a cook order the game cannot activate does not stand in for o_cook. The measured
  case: hint hard MY1-4 on d769d66 order 116 (FOOD<300, PLANT>=10, SEEDS>=36) inactive days 101-216, seeds 41-58 of
  which 17-36 sown.
- brew budget: the glut bank, the allocation, the rot guard and the seed recycle size their one-shots from one budget
  (pb_free less every queued one-shot of this layer), and the trim takes back what a flip to cook-only, the build
  window or the hold no longer allows (peaks of 298 queued brews in 60 orders; 45 brews completed under a cook-only
  plan in cxe60d4ce OP1-3).
- observed orders carry left/total, never amount (brew_planned).
- o_brew / o_cook re-adds: only this layer's own standing, or one that fires wherever it would, suppresses them; the
  plants floor's drift with the measured rate no longer re-cuts o_brew (68bd4c7 OP1-1: 9 adds / 8 re-cuts).
- o_fruit waits on a free fruit (PLANT_GROWTH), not on plants_by_kind.

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


class FakeGame:
    def __init__(self, plant_groups=None, growth_groups=None):
        self.calls, self.queries = [], []
        self.plant_groups, self.growth_groups = plant_groups, growth_groups
        self.next_id = 500

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        self.next_id += 1
        return {"ok": True, "result": {"order_id": self.next_id}}

    def query(self, name, **kw):
        self.queries.append((name, kw))
        groups = self.plant_groups if kw.get("item_type") == "PLANT" else \
            self.growth_groups if kw.get("item_type") == "PLANT_GROWTH" else None
        if groups is None:
            return {"ok": False, "error_code": "bad_arguments"}
        return {"result": {"ok": True, "groups": groups}}


def plot(n, w=3, h=3):
    return {"id": n, "x": 0, "y": 0, "z": 0, "w": w, "h": h, "built": True, "seeds_or_crops_in_plot": n}


def resp(day, days=336, cit=7, pb=0, seeds=0, sown=(), orders=(), drink=100, food=200, barrels=5, meals=20,
         plants=None, kinds=None, hands_off=None, shops=("Still", "Kitchen", "Carpenters")):
    farm = [dict(plot(n), id=i) for i, n in enumerate(sown)]
    r = {"tick": day * harness.DAY, "day": day, "days_left": days - day, "observation": {
        "administrators": {"citizens": cit},
        "stocks": {"plants_brewable": pb, "plants_total": pb if plants is None else plants, "seeds": seeds,
                   "drink": drink, "food_edible": food, "prepared_meals": meals, "barrels_empty": barrels,
                   "logs_usable": 50, "furniture_free": {}, "beds": 20, "tables": 20, "chairs": 20,
                   "plants_by_kind": kinds if kinds is not None else
                   ({"plump helmet": {"n": pb, "brewable": True, "cookable": True}} if pb else {}),
                   "seeds_by_kind": {"plump helmet": {"n": seeds, "seasons": ["spring", "summer", "autumn",
                                                                             "winter"]}} if seeds else {}},
        "map": {"sites": []}, "zones": [], "furniture": [], "farm_plots": farm,
        "workshops": [{"type": t} for t in shops], "orders": [dict(o) for o in orders]}}
    if hands_off is not None:
        r["hands_off_in_days"] = hands_off
    return r


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
    def adds(game, recipe=None, job=None):
        return [a for t, a in game.calls if t in ("add_order", "add_manager_order")
                and (recipe is None or a.get("recipe") == recipe) and (job is None or a.get("job") == job)]

    @staticmethod
    def cancels(game):
        return [a["order_id"] for t, a in game.calls if t == "cancel_order"]


# the observed form of the d769d66 MY1-4 order 116 (o_winter_cook)
ORDER_116 = {"id": 116, "job": "PrepareMeal", "recipe": "cook_meal", "repeat": "daily", "left": 2, "total": 2,
             "active": False, "validated": True,
             "when": [{"item_type": "FOOD", "test": "LessThan", "value": 300, "flags": []},
                      {"item_type": "PLANT", "test": "AtLeast", "value": 10, "flags": ["unrotten"]},
                      {"item_type": "SEEDS", "test": "AtLeast", "value": 36, "flags": []}]}


class Seeds(Base):
    def test_the_order_116_shape_goes_out_live(self):
        # day 101: seeds 58, 31 in the 4 plots, no ripe crop: the bank (36) holds, 27 seeds free
        ov, _ = self.ov(days=216)
        self.load(ov, resp(101, days=216, seeds=58, sown=(9, 9, 9, 4), pb=9, plants=19))
        self.assertEqual(ov.seed_floor(), 36)
        self.assertEqual(ov.free_seeds(), 27)
        self.assertEqual(ov.seed_need(), 5)
        self.assertTrue(ov.seed_clause_dead(ORDER_116))           # the old clause: 36 > 27 free, never active
        tool, args = ov.cook_order([{"stock": "prepared_meals", "below": 300}, {"stock": "plants_total",
                                                                                 "at_least": 10}])
        self.assertEqual(tool, "add_manager_order")
        self.assertEqual(args["when"][-1], {"item_type": "SEEDS", "at_least": 5})
        self.assertFalse(ov.seed_clause_dead({"when": args["when"]}))   # 5 <= 27: the game activates it

    def test_ripe_crops_in_the_plots_are_not_sown_seeds(self):
        ov, _ = self.ov(days=216)
        self.load(ov, resp(101, days=216, seeds=40, sown=(9, 9, 9, 9)))
        ov.in_plot = {"total": 6, "brewable": 6, "items": 6}   # 6 of the 36 plot items are ripe plants
        self.assertEqual(ov.sown_seeds(), 30)
        self.assertEqual(ov.free_seeds(), 10)
        self.assertEqual(ov.seed_need(), 6)
        self.assertTrue(ov.seeds_banked())

    def test_the_bank_short_keeps_the_kitchen_shut(self):
        ov, _ = self.ov(days=216)
        self.load(ov, resp(101, days=216, seeds=30, sown=(9, 9, 9, 0)))   # 27 sown + 3 free < 36
        self.assertFalse(ov.seeds_banked())
        self.assertEqual(ov.seed_need(), 9)
        self.assertTrue(ov.seed_clause_dead({"when": ov.cook_order([{"stock": "prepared_meals", "below": 200}])[1]
                                             ["when"]}))

    def test_seed_guard_reads_the_free_seeds(self):
        # a lab task: a model cook whose SEEDS floor sits under the bank's need is cancelled, one at it is kept
        low = {"id": 7, "recipe": "cook_meal", "repeat": "daily",
               "when": [{"item_type": "SEEDS", "test": "AtLeast", "value": 3}]}
        high = {"id": 8, "recipe": "cook_meal", "repeat": "daily",
                "when": [{"item_type": "SEEDS", "test": "AtLeast", "value": 9}]}
        ov, game = self.ov(days=90)
        self.load(ov, resp(20, days=90, seeds=20, sown=(9, 0), drink=100, hands_off=40, orders=(low, high)))
        # floor 18 (2 plots), 9 sown: the bank needs 9 free, 11 free stand — banked, nothing cancelled
        ov.seed_guard()
        self.assertEqual(self.cancels(game), [])
        self.load(ov, resp(21, days=90, seeds=15, sown=(9, 0), drink=100, hands_off=40, orders=(low, high)))
        ov.seed_guard()   # 6 free < 9 needed: the low floor goes, the floor at the need stays
        self.assertEqual(self.cancels(game), [7])

    def test_a_dead_cook_order_does_not_stand_in_for_o_cook(self):
        ov, game = self.ov(days=216)
        self.load(ov, resp(101, days=216, seeds=58, sown=(9, 9, 9, 4), pb=9, plants=19,
                           orders=(dict(ORDER_116, id=90),)))
        self.assertFalse(ov.regular_cook_on_book())
        ov.supply()
        cook = self.adds(game, job="PrepareMeal")
        self.assertEqual(len(cook), 1)
        self.assertIn({"item_type": "SEEDS", "at_least": 5}, cook[0]["when"])

    def test_a_low_capped_model_cook_does_not_lock_o_cook_out(self):
        low = {"id": 86, "recipe": "cook_meal", "repeat": "daily", "left": 3, "total": 3,
               "when": [{"item_type": "FOOD", "test": "LessThan", "value": 30}]}
        ov, game = self.ov(days=216)
        self.load(ov, resp(101, days=216, seeds=58, sown=(9, 9, 9, 4), pb=9, plants=19, orders=(low,)))
        self.assertFalse(ov.regular_cook_on_book())
        wide = dict(low, when=[{"item_type": "FOOD", "test": "LessThan", "value": 400}])
        self.load(ov, resp(102, days=216, seeds=58, sown=(9, 9, 9, 4), pb=9, plants=19, orders=(wide,)))
        self.assertTrue(ov.regular_cook_on_book())

    def test_the_own_cook_standing_counts_and_its_seeds_clause_has_slack(self):
        ov, game = self.ov(days=216)
        self.load(ov, resp(101, days=216, seeds=58, sown=(9, 9, 9, 4), pb=9, plants=19))
        ov.supply()
        args = self.adds(game, job="PrepareMeal")[0]
        mine = {"id": ov.key_order["o_cook"], "job": "PrepareMeal", "recipe": "cook_meal", "repeat": "daily",
                "left": 2, "total": 2, "when": args["when"]}
        ov.owned.add(mine["id"])
        # 3 more seeds sown from the free ones: the need falls 5 -> 2, within the slack: no re-cut, no second add
        self.load(ov, resp(103, days=216, seeds=58, sown=(9, 9, 9, 7), pb=9, plants=19, orders=(mine,)))
        n = len(game.calls)
        ov.supply()
        self.assertEqual([c for c in game.calls[n:] if c[0] in ("cancel_order", "add_manager_order")], [])
        # the bank emptied into the plots (sown 36, free 22): need 0, the standing at 5 fires still — kept
        self.load(ov, resp(104, days=216, seeds=58, sown=(9, 9, 9, 9), pb=9, plants=19, orders=(mine,)))
        self.assertTrue(ov.cook_when_same(mine["when"], ov.cook_order(ov.cook_when())[1]["when"]))
        # a harvest takes 20 seeds' plots back to crops-in-hand (sown 16) and the bank needs 20: 5 is 15 short
        self.load(ov, resp(130, days=216, seeds=40, sown=(9, 7, 0, 0), pb=9, plants=19, orders=(mine,)))
        self.assertFalse(ov.cook_when_same(mine["when"], ov.cook_order(ov.cook_when())[1]["when"]))


def brew_shot(oid, left, key=None):
    return {"id": oid, "recipe": "brew_drink", "left": left, "total": left}


class BrewBudget(Base):
    def owned_shots(self, ov, shots):
        for oid, key in shots:
            ov.brew_shots[oid] = key
            ov.owned.add(oid)

    def test_the_glut_bank_reads_the_queued_one_shots(self):
        ov, game = self.ov()
        book = [brew_shot(1, 5), brew_shot(2, 5), brew_shot(3, 5)]
        self.load(ov, resp(60, pb=20, drink=20, food=400, barrels=30, orders=book))
        self.owned_shots(ov, [(1, "o_brew_glut"), (2, "o_brew_glut"), (3, "o_brew_alloc")])
        self.assertEqual(ov.brew_budget(), 5)
        ov.glut_bank()
        glut = [a for a in self.adds(game, "brew_drink") if not a.get("repeat")]
        self.assertEqual(glut, [])   # 5 left, the floor (COOK_PLANTS_RESERVE 6) keeps them
        self.load(ov, resp(61, pb=30, drink=20, food=400, barrels=30, orders=book))
        ov.glut_bank()
        glut = [a for a in self.adds(game, "brew_drink") if not a.get("repeat")]
        self.assertEqual(glut, [{"recipe": "brew_drink", "amount": 5}])   # 15 free over the queued 15, floor 6

    def test_the_rot_guard_reads_every_queued_one_shot(self):
        ov, game = self.ov()
        book = [brew_shot(1, 10), brew_shot(2, 8)]
        self.load(ov, resp(60, pb=20, drink=20, food=400, barrels=30, orders=book))
        self.owned_shots(ov, [(1, "o_brew_glut"), (2, "o_brew_alloc")])
        ov.rot_seen = True
        ov.rot_guard()
        self.assertEqual([a for a in self.adds(game, "brew_drink")], [])   # 20 - 18 queued - keep 2 = 0

    def test_a_flip_to_cook_only_takes_the_glut_and_allocation_back(self):
        ov, game = self.ov()
        book = [brew_shot(1, 5), brew_shot(2, 5), brew_shot(3, 4)]
        # drink far ahead of food: the allocation yields the Still (cook only)
        self.load(ov, resp(60, pb=20, drink=900, food=40, barrels=30, orders=book))
        self.owned_shots(ov, [(1, "o_brew_glut"), (2, "o_brew_alloc"), (3, "o_brew_rot")])
        ov.alloc, ov.alloc_day = frozenset(("cook",)), 0
        self.assertNotIn("brew", ov.allocation())
        ov.brew_shot_trim()
        self.assertEqual(sorted(self.cancels(game)), [1, 2])   # the rot guard's one-shot stays (rot loses seeds)

    def test_the_hold_takes_back_what_eats_into_the_reserve(self):
        ov, game = self.ov()
        book = [brew_shot(1, 5), brew_shot(2, 5), brew_shot(3, 5)]
        self.load(ov, resp(250, pb=20, drink=400, food=400, barrels=30, orders=book))
        self.owned_shots(ov, [(1, "o_brew_rot"), (2, "o_brew_alloc"), (3, "o_brew_glut")])
        ov.alloc, ov.alloc_day = frozenset(("brew", "cook")), 0
        ov.hold_active = lambda: True
        ov.hold_reserve = lambda: 12
        # every source keeps the hold's reserve 12 of the 20 free: the rot guard's 5 fit, the next 5 do not wholly
        # (5 + 5 > 8 but the first 5 sit under it: kept), the glut's lies wholly beyond — cancelled
        ov.brew_shot_trim()
        self.assertEqual(self.cancels(game), [3])

    def test_no_trim_while_the_one_shots_fit(self):
        ov, game = self.ov()
        book = [brew_shot(1, 5), brew_shot(2, 5)]
        self.load(ov, resp(60, pb=30, drink=20, food=400, barrels=30, orders=book))
        self.owned_shots(ov, [(1, "o_brew_glut"), (2, "o_brew_alloc")])
        ov.alloc, ov.alloc_day = frozenset(("brew", "cook")), 0
        ov.brew_shot_trim()
        self.assertEqual(self.cancels(game), [])

    def test_the_allocation_sizes_from_the_budget(self):
        ov, game = self.ov()
        book = [brew_shot(1, 10)]
        self.load(ov, resp(60, pb=20, drink=20, food=400, barrels=30, orders=book))
        self.owned_shots(ov, [(1, "o_brew_glut")])
        ov.alloc, ov.alloc_day = frozenset(("brew", "cook")), 0
        ov.allocate_plants()
        alloc = [a for a in self.adds(game, "brew_drink") if not a.get("repeat")]
        self.assertEqual(alloc, [{"recipe": "brew_drink", "amount": 4}])   # 20 - 10 queued - floor 6

    def test_one_shots_are_recorded_by_their_key(self):
        ov, game = self.ov()
        self.load(ov, resp(60, pb=30, drink=20, food=400, barrels=30))
        ov.glut_bank()
        self.assertEqual(set(ov.brew_shots.values()), {"o_brew_glut"})


class ObservedOrders(Base):
    def test_brew_planned_reads_left_and_total(self):
        firing = {"id": 1, "recipe": "brew_drink", "repeat": "daily", "left": 3, "total": 4,
                  "when": [{"item_type": "DRINK", "test": "LessThan", "value": 200}]}
        done = dict(firing, id=2, left=0, total=4)
        ov, _ = self.ov()
        self.load(ov, resp(60, pb=30, drink=100, orders=(firing, done)))
        self.assertEqual(ov.brew_planned(), 7)   # 3 left of this firing + the next firing's 4


class BrewStanding(Base):
    LOW = {"id": 70, "recipe": "brew_drink", "repeat": "daily", "left": 1, "total": 1,
           "when": [{"item_type": "DRINK", "test": "LessThan", "value": 60},
                    {"item_type": "PLANT", "reaction_product": "DRINK_MAT", "test": "AtLeast", "value": 2}]}

    def test_a_low_capped_standing_does_not_lock_o_brew_out(self):
        ov, game = self.ov()
        self.load(ov, resp(214, pb=20, drink=150, orders=(self.LOW,)))
        ov.supply()
        self.assertEqual(len([a for a in self.adds(game, "brew_drink") if a.get("repeat")]), 1)

    def test_a_standing_that_fires_wherever_o_brew_would_suppresses_it(self):
        wide = dict(self.LOW, when=[{"item_type": "DRINK", "test": "LessThan", "value": 900},
                                    {"item_type": "PLANT", "reaction_product": "DRINK_MAT", "test": "AtLeast",
                                     "value": 2},
                                    {"item_type": "BARREL", "test": "AtLeast", "value": 1, "flags": ["empty"]}])
        ov, game = self.ov()
        self.load(ov, resp(214, pb=20, drink=150, orders=(wide,)))
        ov.supply()
        self.assertEqual([a for a in self.adds(game, "brew_drink") if a.get("repeat")], [])

    def test_the_floor_drift_does_not_recut(self):
        same = harness.Overseer.brew_rest_same
        sig = lambda v: harness.when_sig([{"stock": "plants_brewable", "at_least": v},
                                          {"stock": "barrels_empty", "at_least": 1}])
        self.assertTrue(same(sig(40), sig(48)))    # the measured 40 -> 48 drift (68bd4c7 OP1-1 day 204)
        self.assertFalse(same(sig(2), sig(24)))    # an allocation flip re-cuts
        self.assertFalse(same(sig(2), sig(1)))     # the keeper's last plant re-cuts
        self.assertFalse(same(sig(20), sig(40)))


class Fruit(Base):
    GROWTH = [{"item_type": "PLANT_GROWTH", "material": "PLANT:SHRUB_X:FRUIT", "items": 3, "count": 3,
               "rotten": 0, "forbidden": 0, "in_building": 0, "construction": 0}]

    def test_open_play_reads_the_growths_for_o_fruit(self):
        ov, game = self.ov(growth_groups=self.GROWTH)
        self.load(ov, resp(60, pb=0, drink=5, plants=4,
                           kinds={"quarry bush": {"n": 4, "brewable": False, "cookable": False}}))
        ov.supply()
        self.assertEqual(self.adds(game, "brew_drink_from_fruit"), [{"recipe": "brew_drink_from_fruit", "amount": 3}])
        self.assertIn(("stocks", {"item_type": "PLANT_GROWTH"}), game.queries)

    def test_plants_without_fruit_order_no_fruit_brew(self):
        ov, game = self.ov(growth_groups=[])
        self.load(ov, resp(60, pb=0, drink=5, plants=4,
                           kinds={"quarry bush": {"n": 4, "brewable": False, "cookable": False}}))
        ov.supply()
        self.assertEqual(self.adds(game, "brew_drink_from_fruit"), [])
        ov.supply()   # one query a day
        self.assertEqual(sum(1 for q in game.queries if q[1].get("item_type") == "PLANT_GROWTH"), 1)


if __name__ == "__main__":
    unittest.main()
