"""Offline regressions for the open-play slaughter schedule (MY1, OP1).

The Overseer is driven against a stub game; no DF and no model is involved. Asserted: the schedule is off on lab
tasks, a hunger cull takes one small animal (the smallest that is still a meal) and leaves the largest for the feast,
the feast marks the largest animals first, cooks only when there is meat or fish to cook, stops brewing only with
drink in hand and retries a refused cancellation, and the inherited endgame slaughter stays off on open play. The
model loop's two-day stepping is checked against scripted advances, including the two alarms it re-creates.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from overseer.harness import DAY, FEAST_BATCH, Overseer  # noqa: E402
from plain.harness import Plain  # noqa: E402

from dfbench_client import GameAPIError  # noqa: E402

HERD = [{"id": 1, "race": "CAT", "tame": True, "adult": True, "pet_owner_id": -1},
        {"id": 2, "race": "WATER_BUFFALO", "tame": True, "adult": True, "pet_owner_id": -1},
        {"id": 3, "race": "DOG", "tame": True, "adult": True, "pet_owner_id": 77},      # a pet: never marked
        {"id": 4, "race": "YAK", "tame": True, "adult": True, "pet_owner_id": None},
        {"id": 5, "race": "BIRD_TURKEY", "tame": False, "adult": True, "pet_owner_id": -1},   # not tame
        {"id": 6, "race": "COW", "tame": True, "adult": True, "pet_owner_id": -1, "marked_for_slaughter": True},
        {"id": 7, "race": "DONKEY", "tame": True, "adult": True, "pet_owner_id": -1},
        {"id": 8, "race": "RABBIT", "tame": True, "adult": True, "pet_owner_id": -1}]


class StubGame:
    def __init__(self, herd=None, refuse=(), query_error=False):
        self.calls = []
        self.queries = 0
        self.herd = HERD if herd is None else herd
        self.refuse = set(refuse)          # (tool, id) pairs the game answers ok: false to
        self.query_error = query_error

    def act(self, tool, args):
        self.calls.append((tool, json.loads(json.dumps(args))))
        if (tool, args.get("unit_id", args.get("order_id"))) in self.refuse:
            return {"ok": False, "error_code": "game_refused", "error": "scripted"}
        return {"ok": True, "result": {"order_id": 100 + len(self.calls)}}

    def query(self, name, **kw):
        self.queries += 1
        if self.query_error:
            raise GameAPIError("scripted")
        return {"result": {"units": [dict(a) for a in self.herd]}}

    def tools(self, name):
        return [a for t, a in self.calls if t == name]


def resp(days_left, day, food, drink=50, cit=10, hands_off=None, orders=(), workshops=("Carpenters", "Still",
                                                                                         "Kitchen", "Butchers"),
         meals=0, plants=0):
    r = {"day": day, "days_left": days_left, "tick": day * DAY, "observation": {
        "date": {"abs_tick": day * DAY}, "administrators": {"citizens": cit, "manager_active_for_orders": True},
        "stocks": {"food_edible": food, "drink": drink, "logs_usable": 20, "prepared_meals": meals,
                   "plants_total": plants},
        "workshops": [{"type": w, "built": True} for w in workshops], "orders": list(orders),
        "plugins": {"autochop": "on", "seedwatch": "on", "autofarm": "on"},
        "dwarves": [{"id": i, "adult": True} for i in range(cit)], "map": {"sites": []}}}
    if hands_off is not None:
        r["hands_off_in_days"] = hands_off
    return r


def overseer(r, **kw):
    g = StubGame(**kw)
    ov = Overseer(g, goal="Run the fortress", days=336)
    ov.set_task({"goal": "Run the fortress for 336 days."})
    ov.load(r)
    ov.count = 0
    return ov, g


class OpenPlay(unittest.TestCase):
    def test_lab_task_is_not_open_play(self):
        ov, g = overseer(resp(40, 20, food=0, hands_off=19))
        self.assertFalse(ov.open_play())
        ov2 = Overseer(StubGame(), goal="x", days=60)
        ov2.set_task({"goal": "x", "hands_off": 39})
        ov2.load(resp(40, 20, food=0))
        self.assertFalse(ov2.open_play())

    def test_migrant_goal_is_not_open_play(self):
        g = StubGame()
        ov = Overseer(g, goal="A migrant wave is coming", days=60)
        ov.load(resp(40, 20, food=0))
        self.assertFalse(ov.open_play())

    def test_hunger_takes_one_small_animal_and_waits(self):
        ov, g = overseer(resp(200, 136, food=2))
        ov.provision()
        self.assertEqual(g.tools("slaughter"), [{"unit_id": 1}])     # the cat: not the buffalo, not the rabbit
        ov.load(resp(198, 138, food=2)); ov.count = 0
        ov.provision()
        self.assertEqual(len(g.tools("slaughter")), 1)               # eight days must pass
        ov.load(resp(191, 145, food=2)); ov.count = 0
        ov.provision()
        self.assertEqual(len(g.tools("slaughter")), 2)

    def test_a_fort_with_a_week_of_food_keeps_its_animals(self):
        ov, g = overseer(resp(200, 136, food=3))     # ten citizens: 3 is the floor of the trigger
        ov.provision()
        self.assertEqual(g.tools("slaughter"), [])
        self.assertEqual(g.queries, 0)

    def test_final_stretch_raises_the_trigger(self):
        ov, g = overseer(resp(30, 306, food=5))      # under 6 with the scored stretch about to start
        ov.provision()
        self.assertEqual(g.tools("slaughter"), [{"unit_id": 1}])
        ov, g = overseer(resp(31, 305, food=5))      # a day earlier the same stock is not hunger
        ov.provision()
        self.assertEqual(g.tools("slaughter"), [])

    def test_hunger_leaves_the_three_largest_for_the_feast(self):
        big = [a for a in HERD if a["id"] in (2, 4, 7)]              # buffalo, yak, donkey only
        ov, g = overseer(resp(200, 136, food=1), herd=big)
        ov.provision()
        self.assertEqual(g.tools("slaughter"), [])                   # some food left: they are kept
        ov, g = overseer(resp(200, 136, food=0), herd=big)
        ov.provision()
        self.assertEqual(g.tools("slaughter"), [{"unit_id": 7}])     # nothing left to eat: the smallest of them

    def test_a_refused_animal_does_not_block_the_next(self):
        ov, g = overseer(resp(200, 136, food=2), refuse={("slaughter", 1)})
        ov.provision()
        self.assertEqual(g.tools("slaughter"), [{"unit_id": 1}, {"unit_id": 8}])

    def test_a_failed_animal_query_is_retried_next_pass(self):
        ov, g = overseer(resp(200, 136, food=2), query_error=True)
        ov.provision()                                               # must not raise
        self.assertEqual(g.tools("slaughter"), [])
        g.query_error = False
        ov.load(resp(198, 138, food=2)); ov.count = 0
        ov.provision()
        self.assertEqual(g.tools("slaughter"), [{"unit_id": 1}])     # no eight-day wait after a failed read

    def test_feast_marks_the_largest_first(self):
        ov, g = overseer(resp(14, 322, food=40, plants=40))
        ov.provision()
        self.assertEqual(g.tools("slaughter"), [{"unit_id": 2}, {"unit_id": 4}, {"unit_id": 7}][:FEAST_BATCH])
        self.assertEqual(g.tools("add_order"), [])                   # all the food is plants: nothing to cook yet
        self.assertEqual(g.tools("cancel_order"), [])                # drink 50 for 10: keep brewing

    def test_feast_cooks_when_there_is_meat_or_fish(self):
        ov, g = overseer(resp(12, 324, food=70, plants=20, meals=5))     # 45 raw
        ov.provision()
        self.assertEqual(g.tools("add_order"), [{"recipe": "cook_meal", "amount": 4}])
        pending = [{"id": 9, "recipe": "cook_meal", "left": 4, "repeat": None}]
        ov, g = overseer(resp(12, 324, food=70, plants=20, meals=5, orders=pending))
        ov.provision()
        self.assertEqual(g.tools("add_order"), [])                   # one cook order at a time

    def test_feast_with_no_animals_and_no_meat_orders_nothing(self):
        ov, g = overseer(resp(14, 322, food=4, drink=0, plants=4), herd=[])
        ov.provision()
        self.assertEqual(g.calls, [])

    def test_feast_stops_brewing_only_with_drink_in_hand(self):
        brew = [{"id": 31, "recipe": "brew_drink", "left": 3, "repeat": "Daily"}]
        ov, g = overseer(resp(14, 322, food=40, drink=270, orders=brew))     # 27 per citizen: not enough
        ov.brew_own = {31}
        ov.provision()
        self.assertEqual(g.tools("cancel_order"), [])
        ov, g = overseer(resp(14, 322, food=40, drink=280, orders=brew))
        ov.brew_own = {31}
        ov.provision()
        self.assertEqual(g.tools("cancel_order"), [{"order_id": 31}])
        self.assertTrue(ov.brew_stopped)
        ov.load(resp(12, 324, food=40, drink=280)); ov.count = 0
        ov.supply()
        self.assertFalse(any(a.get("recipe") == "brew_drink" for a in g.tools("add_order")))

    def test_a_refused_brew_cancellation_is_tried_again(self):
        brew = [{"id": 31, "recipe": "brew_drink", "left": 3, "repeat": "Daily"},
                {"id": 32, "recipe": "brew_drink", "left": 4, "repeat": "Daily"}]
        ov, g = overseer(resp(14, 322, food=40, drink=280, orders=brew), refuse={("cancel_order", 32)})
        ov.brew_own = {31, 32}
        ov.provision()
        self.assertEqual(g.tools("cancel_order"), [{"order_id": 31}, {"order_id": 32}])
        g.refuse = set()
        ov.load(resp(12, 324, food=40, drink=278, orders=brew[1:])); ov.count = 0     # 31 is gone, 32 still there
        ov.brew_own = {32}
        ov.provision()
        self.assertEqual(g.tools("cancel_order")[-1], {"order_id": 32})
        self.assertEqual(len(g.tools("cancel_order")), 3)

    def test_brewing_reopens_if_drink_falls(self):
        ov, g = overseer(resp(14, 322, food=40, drink=280))
        ov.provision()
        self.assertTrue(ov.brew_stopped)
        ov.load(resp(10, 326, food=40, drink=210)); ov.count = 0     # 21 per citizen
        ov.provision()
        self.assertFalse(ov.brew_stopped)

    def test_endgame_no_longer_slaughters_weekly_on_open_play(self):
        ov, g = overseer(resp(60, 276, food=12))     # 1.2 per citizen: under the old 4-per-citizen trigger
        ov.endgame_supply()
        self.assertEqual(g.tools("slaughter"), [])
        self.assertEqual(g.queries, 0)

    def test_butchers_is_built_early_on_open_play_only(self):
        r = resp(300, 36, food=60, workshops=("Carpenters", "Still", "Kitchen"))
        r["observation"]["map"]["sites"] = [{"id": "W1", "kind": "W"}]
        ov, g = overseer(r)
        ov.workshops()
        self.assertEqual(g.tools("build_workshop"), [{"type": "Butchers", "site": "W1"}])
        lab = dict(r, hands_off_in_days=20)
        ov, g = overseer(lab)
        ov.workshops()
        self.assertEqual(g.tools("build_workshop"), [])


class Task:
    task, days, credits = {"goal": "Run the fortress"}, 336, 0.5


class WalkGame:
    """advance_days answers from a script (one dict of extra result fields per call); observe() follows the clock."""

    def __init__(self, script=(), threats=None, water=None):
        self.script, self.advances, self.day, self.last = list(script), [], 100, {}
        self.threats, self.water = threats or {}, water or {}

    def act(self, tool, args):
        if tool != "advance_days":           # the layer's own actions between steps
            return {"ok": True, "result": {}}
        self.advances.append(args["days"])
        extra = self.script.pop(0) if self.script else {}
        self.day += args["days"]
        return {"ok": True, "day": self.day, "result": {"advanced_ticks": extra.pop("ticks", args["days"] * DAY),
                                                        "stopped": None, **extra}}

    def observe(self):
        r = resp(336 - self.day, self.day, food=60)
        if self.day in self.threats:
            r["observation"]["threats"] = {"visible_hostiles": 1, "nearest_hostile_dist_to_wagon": self.threats[self.day]}
        if self.day in self.water:
            r["observation"]["water_on_fort_levels"] = {"tiles": 9, "total_depth": self.water[self.day]}
        return r

    def query(self, *a, **kw):
        return {"result": {"units": []}}


def plain(game):
    p = Plain(Task(), game, model=None)
    p.guard.load(resp(236, 100, food=60))
    return p


class Stepping(unittest.TestCase):
    def test_model_advance_is_walked_in_two_day_steps(self):
        g = WalkGame()
        p = plain(g)
        out = p.open_advance({"days": 7})
        self.assertEqual(g.advances, [2, 2, 2, 1])
        self.assertEqual(out["result"]["advanced_days"], 7.0)
        self.assertEqual(p.guard_day, 106)       # the layer ran on days 102, 104 and 106
        self.assertNotIn("harness_stop", out["result"])

    def test_short_advance_is_a_single_call(self):
        g = WalkGame()
        out = plain(g).open_advance({"days": 2})
        self.assertEqual(g.advances, [2])
        self.assertEqual(out["result"]["advanced_days"], 2.0)

    def test_tripwire_stop_ends_the_walk_and_is_timed_from_its_start(self):
        g = WalkGame(script=[{"interruptions": [{"text": "a popup"}]},
                             {"ticks": 600, "stopped": {"reason": "announcement:STRANGE_MOOD", "after_ticks": 600}}])
        out = plain(g).open_advance({"days": 7})
        self.assertEqual(g.advances, [2, 2])
        self.assertEqual(out["result"]["stopped"]["after_ticks"], 2 * DAY + 600)
        self.assertEqual(out["result"]["advanced_ticks"], 2 * DAY + 600)
        self.assertEqual(out["result"]["interruptions"], [{"text": "a popup"}])     # the first step's popup is kept

    def test_water_rising_over_the_whole_advance_ends_it(self):
        g = WalkGame(water={100: 100, 102: 140, 104: 180, 106: 220})     # +40 a step: no single step trips
        out = plain(g).open_advance({"days": 7})
        self.assertEqual(g.advances, [2, 2])                             # 180 is +80 and 1.8x the start
        self.assertIn("indoor water rose from 100 to 180", out["result"]["harness_stop"])

    def test_steady_water_is_not_an_alarm(self):
        g = WalkGame(water={d: 300 for d in range(100, 108)})
        out = plain(g).open_advance({"days": 7})
        self.assertEqual(g.advances, [2, 2, 2, 1])
        self.assertNotIn("harness_stop", out["result"])

    def test_hostile_closing_over_the_whole_advance_ends_it(self):
        g = WalkGame(threats={100: 80, 102: 68, 104: 54, 106: 40})       # 12-14 tiles a step
        out = plain(g).open_advance({"days": 7})
        self.assertEqual(g.advances, [2, 2])
        self.assertIn("26 tiles closer", out["result"]["harness_stop"])


if __name__ == "__main__":
    unittest.main()
