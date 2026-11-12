"""Food security: while edible food drains below ~120 days of cover, the butcher fires outside the endgame, a
Fishery is built even without a fisher, and cooking continues without the plants condition. No game or network."""
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
    def __init__(self, units=()):
        self.calls = []
        self.units = list(units)

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"id": len(self.calls), "order_id": len(self.calls)}}

    def query(self, resource, **kw):
        return {"result": {"units": self.units}}


class FoodSecurity(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, cls=None, day=30, food=80, drink=50, citizens=2, jobs=("idle",),
                 workshops=("Carpenters", "Still", "Kitchen"), w_sites=1, logs=10, orders=(), units=(),
                 days=336):
        """days: the run length the layer was constructed with. Food security is a 180-day-and-up measure on this
        FULL tree, so the default 336 (OP1's shape) arms it; the gate test passes a lab's 60 to keep it off."""
        game = FakeGame(units)
        overseer = (cls or harness.Overseer)(game, days=days)
        overseer.load({"day": day, "tick": day * 1200, "observation": {
            "date": {"abs_tick": day * 1200},
            "administrators": {"citizens": citizens},
            "dwarves": [{"id": 87 + i, "job": job} for i, job in enumerate(jobs)],
            "stocks": {"food_edible": food, "drink": drink, "logs_usable": logs},
            "workshops": [{"type": t, "built": True} for t in workshops],
            "map": {"sites": [{"id": "W%d" % i, "kind": "W", "x": 4 * i, "y": 10, "z": 10}
                              for i in range(1, w_sites + 1)]},
            "orders": list(orders)}})
        overseer.count = 0
        return overseer

    def history(self, overseer, foods, drink=50):
        """Seed the day-history with the given edible-food series ending on the loaded day."""
        overseer.food_hist.clear()
        n = len(foods)
        for i, f in enumerate(foods):
            overseer.food_hist.append((overseer.day - (n - 1 - i), f, drink))

    # ---- (a) butcher on a draining pantry
    def test_draining_food_fires_the_butcher(self):
        overseer = self.overseer(food=80, w_sites=1, logs=10,
                                 units=[{"id": 5, "tame": True, "pet_owner_id": None,
                                         "marked_for_slaughter": False}])
        self.history(overseer, [94 - i for i in range(14)])   # slope -1/day, food 80 -> T = 80 < 120
        overseer.food_security()
        self.assertEqual(overseer.game.calls, [
            ("build_workshop", {"type": "Butchers", "site": "W1"}),
            ("slaughter", {"unit_id": 5}),
            ("add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily",
                           "when": [{"stock": "prepared_meals",
                                     "below": max(harness.MEAL_CAP, 3 * overseer.cit)}]})])

    def test_drain_inside_one_day_gate_does_not_repeat(self):
        overseer = self.overseer(food=80, w_sites=1, logs=10,
                                 units=[{"id": 5, "tame": True, "pet_owner_id": None,
                                         "marked_for_slaughter": False}])
        self.history(overseer, [94 - i for i in range(14)])
        overseer.food_security()
        overseer.food_security()
        self.assertEqual([c for c in overseer.game.calls if c[0] == "slaughter"],
                         [("slaughter", {"unit_id": 5})])

    def test_no_history_yet_means_no_alarm(self):
        overseer = self.overseer(food=80)
        overseer.food_hist.clear()
        overseer.food_hist.append((overseer.day, 80, 50))
        overseer.food_security()
        overseer.workshops()
        self.assertEqual(overseer.game.calls, [])

    # ---- (b) a flat or rising pantry never stages anything
    def test_rising_food_fires_nothing(self):
        overseer = self.overseer(food=80, w_sites=2, logs=10,
                                 units=[{"id": 5, "tame": True, "pet_owner_id": None,
                                         "marked_for_slaughter": False}])
        self.history(overseer, [67 + i for i in range(14)])   # slope +1/day -> no drain
        overseer.food_security()
        overseer.workshops()
        self.assertEqual(overseer.game.calls, [])

    def test_slow_drain_above_the_horizon_fires_nothing(self):
        overseer = self.overseer(food=80, w_sites=2, logs=10)
        self.history(overseer, [87 - 0.5 * i for i in range(14)])   # slope -0.5 -> T = 160 >= 120
        overseer.food_security()
        overseer.workshops()
        self.assertEqual(overseer.game.calls, [])

    # ---- (c) the Fishery's job condition is lifted only while food is draining
    def test_alarm_builds_fishery_without_a_fisher(self):
        overseer = self.overseer(jobs=("idle",), workshops=("Carpenters", "Still", "Kitchen"),
                                 w_sites=2, logs=10)
        self.history(overseer, [94 - i for i in range(14)])
        overseer.workshops()
        self.assertIn(("build_workshop", {"type": "Fishery", "site": "W1"}), overseer.game.calls)

    def test_existing_fishery_is_not_rebuilt_under_alarm(self):
        overseer = self.overseer(jobs=("idle",), workshops=("Carpenters", "Still", "Kitchen", "Fishery"),
                                 w_sites=2, logs=10)
        self.history(overseer, [94 - i for i in range(14)])
        overseer.workshops()
        self.assertNotIn("build_workshop", [tool for tool, _ in overseer.game.calls])

    def test_no_alarm_keeps_the_fisher_condition(self):
        overseer = self.overseer(jobs=("idle",), workshops=("Carpenters", "Still", "Kitchen"),
                                 w_sites=2, logs=10)
        self.history(overseer, [67 + i for i in range(14)])
        overseer.workshops()
        self.assertEqual(overseer.game.calls, [])

    # ---- (d) the plant-free cook order, gated on a Kitchen and sized to the population
    def cook_order(self, overseer):
        return [args for tool, args in overseer.game.calls if tool == "add_order"
                and args.get("recipe") == "cook_meal"]

    def test_alarm_adds_one_plant_free_cook_order(self):
        overseer = self.overseer(citizens=100, w_sites=0, drink=5000)
        self.history(overseer, [94 - i for i in range(14)])
        overseer.food_security()
        overseer.food_security()   # the same pass must not add it twice
        self.assertEqual(self.cook_order(overseer), [{
            "recipe": "cook_meal", "amount": 2, "repeat": "daily",
            "when": [{"stock": "prepared_meals", "below": 300}]}])   # max(200, 3 * 100)
        self.assertEqual([w.get("stock") for w in self.cook_order(overseer)[0]["when"]],
                         ["prepared_meals"])   # the plants condition is gone

    def test_cook_target_is_population_proportional(self):
        overseer = self.overseer(citizens=20, w_sites=0, drink=5000)
        self.history(overseer, [94 - i for i in range(14)])
        overseer.food_security()
        self.assertEqual(self.cook_order(overseer)[0]["when"],
                         [{"stock": "prepared_meals", "below": 200}])   # max(200, 3 * 20) = MEAL_CAP

    def test_an_existing_plant_free_cook_is_not_duplicated(self):
        orders = [{"recipe": "cook_meal", "repeat": "daily", "left": 0,
                   "when": [{"stock": "prepared_meals", "below": 5}]}]
        overseer = self.overseer(w_sites=0, orders=orders)
        self.history(overseer, [94 - i for i in range(14)])
        overseer.food_security()
        self.assertEqual(overseer.game.calls, [])

    def test_no_kitchen_means_no_extra_cook(self):
        overseer = self.overseer(workshops=("Carpenters", "Still"), w_sites=0)
        self.history(overseer, [94 - i for i in range(14)])
        overseer.food_security()
        self.assertEqual(self.cook_order(overseer), [])

    # ---- bookkeeping: one history entry per day
    def test_load_keeps_one_entry_per_day(self):
        overseer = self.overseer(day=30, food=80)
        self.assertEqual(list(overseer.food_hist), [(30, 80, 50)])
        overseer.load({"day": 30, "tick": 30 * 1200, "observation": {
            "date": {"abs_tick": 30 * 1200}, "stocks": {"food_edible": 78, "drink": 49}}})
        overseer.load({"day": 31, "tick": 31 * 1200, "observation": {
            "date": {"abs_tick": 31 * 1200}, "stocks": {"food_edible": 77, "drink": 48}}})
        self.assertEqual(list(overseer.food_hist), [(30, 78, 49), (31, 77, 48)])

    # ---- (e) with healthy stocks the leader's behaviour is unchanged
    def test_healthy_plan_call_sequence_is_unchanged(self):
        overseer = self.overseer(food=300, drink=200, citizens=6, jobs=("idle",),
                                 workshops=("Carpenters", "Still", "Kitchen"), w_sites=5, logs=40)
        self.history(overseer, list(range(280, 294)))   # a healthy, rising pantry: T is undefined, no alarm
        overseer.plan()
        self.assertEqual(overseer.game.calls, [
            ("appoint_manager", {"dwarf_id": 87}),
            ("enable_automation", {"name": "autochop"}),
            ("enable_automation", {"name": "seedwatch"}),
            # the brew cap is the adaptive-cap fix's max(200, a year of drink per citizen); at cit=6 the 200
            # floor wins, and the stock (drink 200) sits at the cap, so the gap-proportional amount is its
            # floor of 1 (brew_amount)
            ("add_order", {"recipe": "brew_drink", "amount": 1, "repeat": "daily", "when": [
                {"stock": "drink", "below": 200}, {"stock": "plants_brewable", "at_least": 2},
                {"stock": "barrels_empty", "at_least": 1}]}),
            ("add_order", {"recipe": "make_barrel", "amount": 2, "repeat": "daily", "when": [
                {"stock": "barrels_empty", "below": 4}, {"stock": "logs", "at_least": 2}]}),
            ("add_order", {"recipe": "cook_meal", "amount": 2, "repeat": "daily", "when": [
                {"stock": "prepared_meals", "below": 200}, {"stock": "plants_total", "at_least": 10},
                # this base keeps a brewable-plants reserve on the regular cook standing at days >= 336; cx: food
                # (300) is far ahead of drink (200) at 6 citizens, so the allocation has the kitchen yield — the
                # floor is the hold floor (2 per citizen + ALLOC_HOLD_MARGIN)
                {"stock": "plants_brewable", "at_least": harness.PLANT_RESERVE_PER_CIT * 6 + harness.ALLOC_HOLD_MARGIN}]}),
            ("add_order", {"recipe": "make_bed", "amount": 8}),
            ("add_order", {"recipe": "make_table", "amount": 5}),
            ("add_order", {"recipe": "make_chair", "amount": 6})])

    # ---- (f) the days gate: on a lab's short run food_alarm stays off, so the Fishery keeps the leader's
    # fisher condition however steep the drain (the stages' own cover check is untouched, per the gate's spec)
    def test_lab_length_run_never_arms_the_alarm(self):
        overseer = self.overseer(food=80, w_sites=2, logs=10, days=60,
                                 units=[{"id": 5, "tame": True, "pet_owner_id": None,
                                         "marked_for_slaughter": False}])
        self.history(overseer, [94 - i for i in range(14)])   # the same -1/day drain the alarm answers at 336
        self.assertIs(overseer.food_alarm(), False)
        overseer.workshops()
        self.assertEqual(overseer.game.calls, [])   # no Fishery: the leader's fisher-only condition holds


if __name__ == "__main__":
    unittest.main()


class DrinkShortSkipsPlantFreeCook(FoodSecurity):
    def test_drought_keeps_plants_for_the_still(self):
        """cx dev hard LT01-3: drink the short leg -> the emergency cook still goes on (meat and fish become meals,
        CX_REVIEW P1-3) but under a plants_brewable floor (the yielding side's hold floor), so plants stay
        brewable."""
        overseer = self.overseer(citizens=17, w_sites=0, drink=21, food=98)
        self.history(overseer, [94 - i for i in range(14)])
        overseer.food_security()
        orders = self.cook_order(overseer)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["when"], [
            {"stock": "prepared_meals", "below": max(harness.MEAL_CAP, 3 * 17)},
            {"stock": "plants_brewable", "at_least": overseer.hold_floor()}])
        self.assertLessEqual(len(orders[0]["when"]), 3)

    def test_a_floor_free_cook_is_recut_when_drink_turns_short(self):
        overseer = self.overseer(citizens=17, w_sites=0, drink=21, food=98, orders=[
            {"id": 40, "recipe": "cook_meal", "repeat": "daily", "when": [
                {"item_type": "FOOD", "test": "LessThan", "value": 51}]}])
        overseer.owned.add(40)
        overseer.key_order["o_cook_food"] = 40
        self.history(overseer, [94 - i for i in range(14)])
        overseer.food_security()
        self.assertEqual(overseer.game.calls, [("cancel_order", {"order_id": 40})])
        self.assertNotIn("o_cook_food", overseer.done)

    def test_a_floored_cook_is_left_alone_while_drink_stays_short(self):
        overseer = self.overseer(citizens=17, w_sites=0, drink=21, food=98, orders=[
            {"id": 40, "recipe": "cook_meal", "repeat": "daily", "when": [
                {"item_type": "FOOD", "test": "LessThan", "value": 51},
                {"item_type": "PLANT", "reaction_product": "DRINK_MAT", "flags": ["unrotten"], "test": "AtLeast",
                 "value": 44}]}])
        overseer.owned.add(40)
        overseer.key_order["o_cook_food"] = 40
        self.history(overseer, [94 - i for i in range(14)])
        overseer.food_security()
        self.assertEqual([c for c in overseer.game.calls if c[0] in ("cancel_order", "add_order")], [])
