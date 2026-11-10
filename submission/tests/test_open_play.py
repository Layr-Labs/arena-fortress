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

from overseer.harness import DAY, FEAST_BATCH, WILD_DAYS, WILD_REST, Overseer  # noqa: E402
from plain.harness import Plain  # noqa: E402

from dfbench_client import ActionLimit, GameAPIError  # noqa: E402

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
        if (tool, args.get("unit_id", args.get("order_id"))) in self.refuse or (tool, None) in self.refuse:
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
        ov, g = overseer(resp(30, 306, food=9))      # under one per citizen with the scored stretch about to start
        ov.provision()
        self.assertEqual(g.tools("slaughter"), [{"unit_id": 1}])
        ov.load(resp(26, 310, food=9)); ov.count = 0
        ov.provision()
        self.assertEqual(len(g.tools("slaughter")), 1)               # five days must pass there
        ov.load(resp(25, 311, food=9)); ov.count = 0
        ov.provision()
        self.assertEqual(len(g.tools("slaughter")), 2)
        ov, g = overseer(resp(31, 305, food=9))      # a day earlier the same stock is not hunger
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
        r = resp(300, 36, food=60, workshops=("Carpenters", "Still", "Kitchen", "Fishery"))   # a fort that fishes
        r["observation"]["map"]["sites"] = [{"id": "W1", "kind": "W"}]
        ov, g = overseer(r)
        ov.management()
        ov.workshops()
        self.assertEqual(g.tools("build_workshop"), [{"type": "Butchers", "site": "W1"}])
        lab = dict(r, hands_off_in_days=20)
        ov, g = overseer(lab)
        ov.management()
        ov.workshops()
        self.assertEqual(g.tools("build_workshop"), [])


def bare(days_left, day, fishing=True, workshops=("Carpenters", "Still", "Kitchen"), **kw):
    """A fort with a free workshop site and, by default, neither a Fishery nor a Butchers and one dwarf fishing."""
    r = resp(days_left, day, food=60, workshops=workshops, **kw)
    r["observation"]["map"]["sites"] = [{"id": "W1", "kind": "W"}]
    if fishing:
        r["observation"]["dwarves"][4].update(profession="Fisherdwarf", job="Fish")
    return r


class NoFishing(unittest.TestCase):
    def test_a_fort_with_neither_workshop_gets_autolabor_and_no_fishery(self):
        ov, g = overseer(bare(336, 0))
        ov.management()
        ov.workshops()
        self.assertIs(ov.calm, True)
        self.assertEqual(g.tools("enable_automation"), [{"name": "autolabor"}])
        self.assertEqual(g.tools("build_workshop"), [])          # no Fishery for the catch, no Butchers yet

    def test_autolabor_that_is_on_is_left_alone(self):
        r = bare(300, 36)
        r["observation"]["plugins"]["autolabor"] = "on"
        ov, g = overseer(r)
        ov.management()
        ov.workshops()
        self.assertIs(ov.calm, True)
        self.assertEqual(g.tools("enable_automation"), [])
        self.assertEqual(g.tools("build_workshop"), [])

    def test_butchers_waits_for_the_feast_when_nobody_hunts(self):
        ov, g = overseer(bare(18, 318))
        ov.management()
        ov.workshops()
        self.assertEqual(g.tools("build_workshop"), [])
        ov.load(bare(17, 319))
        ov.management()
        ov.workshops()
        self.assertEqual(g.tools("build_workshop"), [{"type": "Butchers", "site": "W1"}])

    def test_a_hunger_cull_still_builds_the_butchers_at_once(self):
        ov, g = overseer(bare(200, 136))
        ov.management()
        ov.load(dict(bare(200, 136), **{}))
        ov.o["stocks"]["food_edible"] = 0
        ov.st = ov.o["stocks"]
        ov.provision()
        self.assertEqual(g.tools("build_workshop"), [{"type": "Butchers", "site": "W1"}])
        self.assertEqual(len(g.tools("slaughter")), 1)

    def test_a_fort_that_already_fishes_or_butchers_is_left_as_it_was(self):
        for have in ("Fishery", "Butchers"):
            ov, g = overseer(bare(336, 0, workshops=("Carpenters", "Still", "Kitchen", have)))
            ov.management()
            ov.workshops()
            self.assertIs(ov.calm, False)
            self.assertEqual(g.tools("enable_automation"), [])
            other = "Butchers" if have == "Fishery" else "Fishery"
            self.assertEqual(g.tools("build_workshop"), [{"type": other, "site": "W1"}])   # the inherited rules

    def test_the_choice_is_made_once(self):
        ov, g = overseer(bare(336, 0))
        ov.management()
        ov.load(bare(300, 36, workshops=("Carpenters", "Still", "Kitchen", "Fishery")))   # the model built one
        ov.management()
        ov.workshops()
        self.assertIs(ov.calm, True)
        self.assertEqual(g.tools("build_workshop"), [])

    def test_no_choice_is_made_without_the_workshop_list(self):
        r = bare(336, 0)
        r["observation"]["workshops"] = "ERR: scripted"
        ov, g = overseer(r)
        ov.management()
        self.assertIsNone(ov.calm)
        self.assertEqual(g.tools("enable_automation"), [])

    def test_a_reply_without_the_task_clock_builds_no_fishery(self):
        ov, g = overseer(bare(336, 0))
        ov.management()
        self.assertIs(ov.calm, True)
        r = bare(330, 6)                                                 # the fisher has not been reassigned yet
        del r["days_left"]
        ov.load(r)
        self.assertFalse(ov.open_play())
        ov.management()
        ov.workshops()
        self.assertEqual(g.tools("build_workshop"), [])

    def test_the_choice_is_made_on_a_first_reply_without_the_task_clock(self):
        r = bare(336, 0)
        del r["days_left"]
        ov, g = overseer(r)
        ov.management()
        ov.workshops()
        self.assertIs(ov.calm, True)
        self.assertEqual(g.tools("enable_automation"), [{"name": "autolabor"}])
        self.assertEqual(g.tools("build_workshop"), [])

    def test_lab_task_keeps_its_fishery(self):
        ov, g = overseer(bare(60, 0, hands_off=40))
        ov.management()
        ov.workshops()
        self.assertIsNone(ov.calm)
        self.assertFalse(ov.open_task())
        self.assertEqual(g.tools("enable_automation"), [])
        self.assertEqual(g.tools("build_workshop"), [{"type": "Fishery", "site": "W1"}])

    def test_autolabor_that_will_not_turn_on_gives_the_fishery_back(self):
        ov, g = overseer(bare(336, 0), refuse={("enable_automation", None)})
        for day in range(0, 6):
            ov.load(bare(336 - day, day))
            ov.management()
            ov.workshops()
        self.assertEqual(len(g.tools("enable_automation")), 5)
        self.assertIs(ov.calm, False)
        self.assertEqual(g.tools("build_workshop")[0], {"type": "Fishery", "site": "W1"})

    def test_nothing_is_built_for_the_catch_while_the_choice_is_still_to_be_made(self):
        r = bare(336, 0)
        r["observation"]["workshops"] = "ERR: scripted"
        ov, g = overseer(r)
        ov.management()
        ov.workshops()
        self.assertIsNone(ov.calm)
        self.assertNotIn({"type": "Fishery", "site": "W1"}, g.tools("build_workshop"))
        self.assertNotIn({"type": "Butchers", "site": "W1"}, g.tools("build_workshop"))
        ov.load(bare(335, 1))                                            # readable on the next pass
        ov.management()
        ov.workshops()
        self.assertIs(ov.calm, True)
        self.assertEqual(g.tools("enable_automation"), [{"name": "autolabor"}])
        self.assertNotIn({"type": "Fishery", "site": "W1"}, g.tools("build_workshop"))

    def test_the_model_cannot_build_them_while_the_choice_is_still_to_be_made(self):
        p = plain(WalkGame())
        self.assertIsNone(p.guard.calm)
        self.assertTrue(p.open_play())
        self.assertEqual(p.refuse("build_workshop", {"type": "Fishery", "site": "W2"}, 100 * DAY)["error_code"],
                         "layer_owned")
        p.guard.calm = True
        p.guard.days_left = None                                         # the task clock missing from a reply
        self.assertFalse(p.open_play())
        self.assertEqual(p.refuse("build_workshop", {"type": "Fishery", "site": "W2"}, 100 * DAY)["error_code"],
                         "layer_owned")
        lab = Plain(Task(), WalkGame(), model=None)
        lab.guard.set_task({"goal": "x", "hands_off": 39})
        lab.guard.load(resp(40, 20, food=60, hands_off=19))
        self.assertIsNone(lab.refuse("build_workshop", {"type": "Fishery", "site": "W2"}, 20 * DAY))

    def test_one_day_steps_hold_while_a_lockdown_stands_even_without_the_task_clock(self):
        p = plain(WalkGame())
        p.guard.lock = hold(99)
        p.guard.days_left = None
        self.assertFalse(p.open_play())
        r = resp(236, 100, food=60)
        self.assertEqual(p.quiet_days(r), 1)
        p.guard.lock = None
        self.assertEqual(p.quiet_days(r), 2)

    def test_the_model_cannot_build_a_fishery_before_the_choice_even_without_the_task_clock(self):
        p = plain(WalkGame())
        self.assertIsNone(p.guard.calm)
        p.guard.days_left = None
        self.assertFalse(p.open_play())
        self.assertEqual(p.refuse("build_workshop", {"type": "Fishery", "site": "W2"}, 100 * DAY)["error_code"],
                         "layer_owned")

    def test_the_model_cannot_lock_a_surface_stair_on_open_play(self):
        p = plain(WalkGame())
        r = threat_resp(100, None)
        p.guard.load(r); p.guard.count = 0
        p.guard.defend()
        self.assertTrue(p.open_play())
        self.assertFalse(p.guard_holds())
        for args in ({"locked": True}, {"locked": True, "door_id": 14}, {"locked": True, "door_id": 77}):
            self.assertEqual(p.refuse("lock_door", args, 100 * DAY)["error_code"], "layer_owned")
        self.assertIsNone(p.refuse("lock_door", {"locked": False}, 100 * DAY))
        self.assertIsNone(p.refuse("lock_door", {"locked": False, "door_id": 14}, 100 * DAY))
        lab = Plain(Task(), WalkGame(), model=None)
        lab.guard.set_task({"goal": "x", "hands_off": 39})
        lab.guard.load(resp(40, 20, food=60, hands_off=19))
        self.assertIsNone(lab.refuse("lock_door", {"locked": True}, 20 * DAY))

    def test_the_model_cannot_build_the_two_workshops_meanwhile(self):
        p = plain(WalkGame())
        p.guard.calm = True
        for kind in ("Fishery", "Butchers"):
            out = p.refuse("build_workshop", {"type": kind, "site": "W2"}, 100 * DAY)
            self.assertEqual(out["error_code"], "layer_owned")
        self.assertIsNone(p.refuse("build_workshop", {"type": "Still", "site": "W2"}, 100 * DAY))
        p.guard.calm = False
        self.assertIsNone(p.refuse("build_workshop", {"type": "Fishery", "site": "W2"}, 100 * DAY))


E1 = {"id": "E1", "kind": "E", "x": 92, "y": 100, "z": 153}
HATCH = {"id": 14, "kind": "hatch", "built": True, "locked": False, "x": 92, "y": 100, "z": 153}
BOX = {"x1": 89, "x2": 101, "y1": 99, "y2": 105, "z1": 150, "z2": 152}


def threat_resp(day, dist, n=3, invader=False, alert=False, inside=0, cit=10, tiles=124, doors=(HATCH,), sites=(E1,),
                free_hatch=0, at=None, drop=()):
    """An open-play observation with `n` hostiles `dist` tiles from the wagon (None: no hostile in sight). `drop`
    names sections to leave out, as a failed part of an observation would be."""
    r = resp(336 - day, day, food=60, cit=cit)
    o = r["observation"]
    o["threats"] = {"visible_hostiles": 0, "hostiles": [], "by_race": {}, "dead_citizens_total": 0}
    if dist is not None:
        x, y, z = at or (10, 10, 165)
        o["threats"] = {"visible_hostiles": n, "nearest_hostile_dist_to_wagon": dist, "dead_citizens_total": 0,
                        "by_race": {"HARPY": {"n": n, "invader": invader}},
                        "hostiles": [{"id": 900 + i, "race": "HARPY", "invader": invader, "x": x, "y": y, "z": z,
                                      "dist_to_wagon": dist} for i in range(n)]}
    o["burrows"] = {"civilian_alert": alert, "list": [{"id": 0, "name": "Shelter", "civ_alert_burrow": True,
                                                       "citizens_inside": inside, "tiles": tiles, "bbox": BOX}]}
    o["doors"] = {"list": [dict(x) for x in doors], "hatch_cover_items_free": free_hatch}
    o["map"]["surface_z"] = 153
    if sites is None:
        del o["map"]["sites"]
    else:
        o["map"]["sites"] = [dict(s) for s in sites]
    for name in drop:
        o[name] = "ERR: scripted"
    return r


def locked(*ids):
    return [dict(HATCH, locked=HATCH["id"] in ids)] + [{"id": i, "kind": "door", "built": True, "locked": True,
                                                         "x": 95, "y": 101, "z": 151} for i in ids if i != HATCH["id"]]


def hold(day, **kw):
    return {"since": day * DAY, "phase": "hold", "why": None, "alert_off": False, "rest": False, "due": None,
            "tries": 0, "fresh": False, "blind": 0, "shut": False, **kw}


class Wildlife(unittest.TestCase):
    def play(self, r, refuse=(), **state):
        ov, g = overseer(r, refuse=refuse)
        for k, v in state.items():
            setattr(ov, k, v)
        ov.defend()
        return ov, g

    def again(self, ov, g, r):
        ov.load(r); ov.count = 0
        ov.defend()

    # ---- starting
    def test_nearby_wildlife_starts_a_lockdown_when_the_fort_can_be_shut(self):
        ov, g = self.play(threat_resp(186, 74))
        self.assertEqual(g.tools("civilian_alert"), [{"on": True}])
        self.assertEqual((ov.lock["since"], ov.lock["phase"]), (186 * DAY, "hold"))
        self.assertEqual(g.tools("lock_door"), [])                   # nobody is inside yet and no day has passed

    def test_everyone_already_inside_is_locked_in_the_same_pass(self):
        ov, g = self.play(threat_resp(186, 74, inside=10))
        self.assertEqual(g.tools("civilian_alert"), [{"on": True}])
        self.assertEqual(g.tools("lock_door"), [{"locked": True, "door_id": 14}])

    def test_distant_wildlife_does_not(self):
        ov, g = self.play(threat_resp(184, 141))
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_no_lockdown_unless_every_stair_has_its_own_built_hatch(self):
        for doors, sites in (((), (E1,)),                                             # no hatch at all
                             ((dict(HATCH, built=False),), (E1,)),                     # placed, not built
                             ((HATCH,), (E1, dict(E1, id="E2", x=98))),               # a second stair is open
                             ((dict(HATCH, x=98),), (E1,)),                           # a hatch, but somewhere else
                             ((HATCH,), None),                                        # no site list this pass
                             ((HATCH,), [dict(E1, id="E%d" % i, x=60 + i) for i in range(8)])):   # list at its cap
            ov, g = self.play(threat_resp(186, 74, doors=doors, sites=sites))
            self.assertEqual(g.tools("civilian_alert"), [], (doors, sites))
            self.assertIsNone(ov.lock)

    def test_a_stair_that_dropped_out_of_the_list_still_needs_its_hatch(self):
        ov, g = self.play(threat_resp(100, None, sites=(E1, dict(E1, id="E2", x=98))))
        self.again(ov, g, threat_resp(186, 74, sites=(E1,)))         # E2 is no longer listed and has no hatch
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_no_lockdown_into_a_shelter_that_is_too_small(self):
        ov, g = self.play(threat_resp(186, 74, tiles=1))
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_no_lockdown_when_the_hostile_list_is_cut_short(self):
        r = threat_resp(186, 74, n=3)
        r["observation"]["threats"]["visible_hostiles"] = 21         # more in sight than listed
        ov, g = self.play(r)
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_no_lockdown_on_an_incomplete_observation(self):
        for name in ("threats", "burrows", "doors"):
            ov, g = self.play(threat_resp(186, 74, drop=(name,)))
            self.assertEqual(g.tools("civilian_alert"), [], name)

    def test_a_refused_start_is_not_a_lockdown(self):
        ov, g = self.play(threat_resp(186, 74), refuse={("civilian_alert", None)})
        self.assertEqual(g.tools("civilian_alert"), [{"on": True}])
        self.assertIsNone(ov.lock)

    def test_lab_task_keeps_the_inherited_rule(self):
        r = threat_resp(30, 20)
        r["hands_off_in_days"] = 9
        ov, g = self.play(r)
        self.assertEqual(g.calls, [])                                # not an invader: nothing, as before

    # ---- holding and locking
    def test_only_the_stair_hatch_is_locked_and_only_by_id(self):
        ov, g = self.play(threat_resp(187, 30, alert=True, inside=9, doors=locked(30)), lock=hold(186))
        self.assertEqual(g.tools("lock_door"), [{"locked": True, "door_id": 14}])     # door 30 is not this layer's
        self.assertEqual(ov.own_locks, {14})

    def test_locking_waits_for_the_civilians_or_a_day(self):
        ov, g = self.play(threat_resp(186, 30, alert=True, inside=5), lock=hold(186))
        self.assertEqual(g.tools("lock_door"), [])
        self.again(ov, g, threat_resp(187, 30, alert=True, inside=5))
        self.assertEqual(g.tools("lock_door"), [{"locked": True, "door_id": 14}])

    def test_a_lock_whose_answer_was_lost_is_still_owned(self):
        class Lost(StubGame):
            def act(self, tool, args):
                if tool == "lock_door" and args.get("locked"):
                    self.calls.append((tool, dict(args)))
                    raise GameAPIError("no answer")
                return super().act(tool, args)
        g = Lost()
        ov = Overseer(g, goal="Run the fortress", days=336)
        ov.set_task({"goal": "Run the fortress for 336 days."})
        ov.lock = hold(186)
        ov.step(threat_resp(187, 30, alert=True, inside=10))         # step() swallows the error, as in play
        self.assertEqual(ov.own_locks, {14})                         # sent, unanswered: it must be undone later

    def test_a_hatch_that_will_not_lock_ends_the_lockdown_for_good(self):
        ov, g = self.play(threat_resp(187, 30, alert=True, inside=10), lock=hold(186),
                          refuse={("lock_door", None)})
        self.assertEqual(ov.own_locks, set())                        # refused outright: nothing to undo
        self.again(ov, g, threat_resp(188, 30, alert=True, inside=10))
        self.assertEqual(ov.lock["phase"], "hold")                   # one more try
        self.again(ov, g, threat_resp(189, 30, alert=True, inside=10))
        self.assertIsNone(ov.lock)                                   # given up: alert off, nothing was locked
        self.assertTrue(ov.wild_off)
        self.assertEqual(g.tools("civilian_alert")[-1], {"on": False})

    def test_squad_is_stood_down_only_during_a_hold(self):
        squad = {"squads": [{"id": 1, "uniform": "leather", "armed": 2, "orders": [{"order": "attack"}]}]}
        r = threat_resp(187, 30, alert=True, inside=10, doors=locked(14))
        r["observation"]["military"] = squad
        ov, g = self.play(r, lock=hold(186), own_locks={14})
        self.assertEqual(g.tools("squad_order"), [{"order": "stand_down"}])
        r = threat_resp(187, 140)                                    # in sight but far: the inherited rule stands
        r["observation"]["military"] = {"squads": [{"id": 1, "uniform": "leather", "armed": 2, "orders": []}]}
        ov, g = self.play(r)
        self.assertEqual(g.tools("squad_order"), [{"order": "attack"}])

    def test_a_failed_section_is_not_read_as_safe(self):
        for name in ("threats", "burrows", "doors"):
            ov, g = self.play(threat_resp(190, 30, alert=True, inside=10, doors=locked(14), drop=(name,)),
                              lock=hold(186), own_locks={14})
            self.assertEqual(g.tools("civilian_alert") + g.tools("lock_door"), [], name)
            self.assertEqual((ov.lock["phase"], ov.own_locks), ("hold", {14}), name)

    # ---- ending
    def test_ends_and_unlocks_when_the_wildlife_has_gone(self):
        ov, g = self.play(threat_resp(190, 150, alert=True, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)
        self.assertEqual((ov.rest_until, ov.wild_off), (0, False))

    def test_a_refused_clear_keeps_the_hatch_shut_and_is_carried_through(self):
        ov, g = self.play(threat_resp(207, 30, alert=True, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14}, refuse={("civilian_alert", None)})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [])                   # still confined: do not open the stair
        self.assertEqual((ov.lock["since"], ov.lock["phase"], ov.lock["why"]), (186 * DAY, "release", "cap"))
        g.refuse = set()
        self.again(ov, g, threat_resp(208, 30, alert=True, inside=10, doors=locked(14)))
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)
        self.assertEqual(ov.rest_until, (208 + WILD_REST) * DAY)

    def test_a_decided_release_is_not_undone_when_its_reason_passes(self):
        ov, g = self.play(threat_resp(190, 5, alert=True, inside=10, doors=locked(14), at=(95, 101, 151)),
                          lock=hold(186), own_locks={14}, refuse={("civilian_alert", None)})
        self.assertTrue(ov.wild_off)                                 # decided at once, whatever the API answered
        self.assertEqual(ov.lock["why"], "inside")
        g.refuse = set()
        self.again(ov, g, threat_resp(191, 30, alert=True, inside=10, doors=locked(14)))     # it has moved out
        self.assertEqual(g.tools("civilian_alert")[-1], {"on": False})
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)

    def test_a_refused_unlock_blocks_a_new_lockdown_until_it_is_done(self):
        ov, g = self.play(threat_resp(190, 150, alert=True, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14}, refuse={("lock_door", None)})
        self.assertEqual(ov.lock["phase"], "release")                # alert off, hatch still shut
        self.again(ov, g, threat_resp(191, 30, alert=False, inside=10, doors=locked(14)))    # it is back already
        self.assertEqual(len(g.tools("civilian_alert")), 1)          # no new lockdown over an unfinished release
        g.refuse = set()
        self.again(ov, g, threat_resp(192, 30, alert=False, inside=10, doors=locked(14)))
        self.assertEqual(g.tools("lock_door")[-1], {"locked": False, "door_id": 14})
        self.assertIsNone(ov.lock)
        self.again(ov, g, threat_resp(193, 30, alert=False, inside=10))
        self.assertEqual(g.tools("civilian_alert")[-1], {"on": True})

    def test_a_missing_door_list_does_not_forget_a_lock(self):
        ov, g = self.play(threat_resp(206, 30, alert=True, inside=10, doors=locked(14), drop=("doors",)),
                          lock=hold(186), own_locks={14})                 # day 20: the cap needs no observation
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])     # sent blind, by id
        self.assertIsNone(ov.lock)
        ov, g = self.play(threat_resp(206, 30, alert=True, inside=10, doors=locked(14), drop=("doors",)),
                          lock=hold(186), own_locks={14}, refuse={("lock_door", None)})
        self.assertEqual(ov.own_locks, {14})                         # refused and unseen: still owed

    def test_cap_then_a_day_above_ground_then_it_may_start_again(self):
        day = 100 + WILD_DAYS
        ov, g = self.play(threat_resp(day, 10, alert=True, inside=10, doors=locked(14)), lock=hold(100),
                          own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertEqual(ov.rest_until, (day + WILD_REST) * DAY)
        r = threat_resp(day, 10)
        r["tick"] = r["observation"]["date"]["abs_tick"] = day * DAY + DAY // 2      # half a day later
        self.again(ov, g, r)
        self.assertEqual(len(g.tools("civilian_alert")), 1)          # owed its day above ground
        self.again(ov, g, threat_resp(day + WILD_REST, 10))
        self.assertEqual(g.tools("civilian_alert")[-1], {"on": True})

    def test_a_lockdown_that_ended_early_owes_no_time_above_ground(self):
        ov, g = self.play(threat_resp(105, None, n=0, alert=True, inside=10, doors=locked(14)), lock=hold(100),
                          own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(ov.rest_until, 0)
        self.again(ov, g, threat_resp(106, 40))
        self.assertEqual(g.tools("civilian_alert")[-1], {"on": True})

    def test_a_hostile_inside_the_shelter_ends_it_for_good(self):
        ov, g = self.play(threat_resp(190, 5, alert=True, inside=10, doors=locked(14), at=(95, 101, 151)),
                          lock=hold(186), own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertTrue(ov.wild_off)
        self.again(ov, g, threat_resp(192, 30))
        self.assertEqual(len(g.tools("civilian_alert")), 1)          # no second lockdown this game

    def test_a_lost_seal_ends_it_for_good(self):
        ov, g = self.play(threat_resp(190, 30, alert=True, inside=10, doors=()), lock=hold(186), own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertTrue(ov.wild_off)
        self.assertEqual(ov.own_locks, set())                        # a complete list without it: it is gone

    def test_an_alert_switched_off_by_something_else_ends_it(self):
        ov, g = self.play(threat_resp(190, 30, alert=False, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [])              # already off: nothing to clear
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)

    def test_invaders_take_the_alert_over_and_the_stair_stays_shut_until_it_ends(self):
        ov, g = self.play(threat_resp(190, 30, invader=True, alert=True, inside=10, doors=locked(14)),
                          lock=hold(186), own_locks={14})
        self.assertEqual(g.tools("civilian_alert") + g.tools("lock_door"), [])     # alert on, hatch shut
        self.assertEqual((ov.lock["why"], ov.alert_since), ("invaders", 186 * DAY))
        self.again(ov, g, threat_resp(197, 30, invader=True, alert=True, inside=10, doors=locked(14)))
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])     # ten days from the start, as inherited
        self.assertEqual(g.tools("lock_door"), [])
        self.again(ov, g, threat_resp(198, None, alert=False, inside=10, doors=locked(14)))
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)

    def test_invaders_among_more_hostiles_than_are_listed_still_take_over(self):
        r = threat_resp(190, 30, alert=True, inside=10, doors=locked(14))
        r["observation"]["threats"]["by_race"]["GOBLIN"] = {"n": 1, "invader": True}     # not in the cut list
        ov, g = self.play(r, lock=hold(186), own_locks={14})
        self.assertEqual(ov.lock["why"], "invaders")

    # ---- invaders alone: as before
    def test_invaders_alone_are_handled_as_before(self):
        ov, g = self.play(threat_resp(186, 40, invader=True))
        self.assertEqual(g.tools("civilian_alert"), [{"on": True}])
        self.assertIsNone(ov.lock)
        self.assertEqual(g.tools("lock_door"), [])
        ov, g = self.play(threat_resp(186, 80, invader=True))        # invaders: only within 45 tiles
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_a_lock_this_layer_did_not_make_is_left_alone(self):
        ov, g = self.play(threat_resp(190, 20, invader=True, alert=True, inside=10, doors=locked(14, 30)),
                          alert_since=188 * DAY)
        self.assertEqual(g.tools("lock_door"), [])
        ov, g = self.play(threat_resp(190, None, doors=locked(14, 30)))
        self.assertEqual(g.tools("lock_door"), [])

    # ---- upkeep
    def test_shelter_grows_with_the_dig_and_refusals_are_retried(self):
        a = {"id": "A1", "kind": "A", "z": 150, "open_tiles": 40}
        ov, g = self.play(threat_resp(50, None, sites=(E1, a)), refuse={("create_burrow", None)})
        for day in (56, 62, 68):
            self.again(ov, g, threat_resp(day, None, sites=(E1, a)))
        self.assertEqual(len(g.tools("create_burrow")), 4)           # four refusals: still trying
        self.assertEqual(ov.sheltered, {})
        g.refuse = set()
        self.again(ov, g, threat_resp(74, None, sites=(E1, a)))
        self.assertEqual(ov.sheltered, {"A1": 40})
        self.again(ov, g, threat_resp(80, None, sites=(E1, dict(a, open_tiles=45))))
        self.assertEqual(len(g.tools("create_burrow")), 5)           # five more tiles: not worth another call
        self.again(ov, g, threat_resp(86, None, sites=(E1, dict(a, open_tiles=90))))
        self.assertEqual(len(g.tools("create_burrow")), 6)

    def test_hatch_cover_is_ordered_then_placed_on_the_surface_stair(self):
        ov, g = self.play(threat_resp(20, None, doors=()))
        self.assertEqual(g.tools("add_order"), [{"recipe": "make_hatch_cover", "amount": 1}])
        ov, g = self.play(threat_resp(24, None, doors=(), free_hatch=1))
        self.assertEqual(g.tools("build_door"), [{"kind": "hatch", "site": "E1"}])
        ov, g = self.play(threat_resp(28, None, doors=(dict(HATCH, built=False),)))
        self.assertEqual(g.tools("add_order") + g.tools("build_door"), [])       # placed and waiting to be built

    # ---- the third review's cases
    def test_a_refused_invader_clear_keeps_its_clock_and_is_tried_again(self):
        ov, g = self.play(threat_resp(111, 30, invader=True, alert=True, inside=10, doors=locked(14)),
                          lock=hold(100, phase="release", why="invaders", alert_off=True), own_locks={14},
                          alert_since=100 * DAY, refuse={("civilian_alert", None)})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])     # the inherited ten-day rule, refused
        self.assertEqual(ov.alert_since, 100 * DAY)
        g.refuse.clear()
        self.again(ov, g, threat_resp(112, 30, invader=True, alert=True, inside=10, doors=locked(14)))
        self.assertEqual(len(g.tools("civilian_alert")), 2)
        self.assertIsNone(ov.alert_since)
        self.again(ov, g, threat_resp(113, 30, invader=True, inside=10, doors=locked(14)))
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)

    def test_an_invader_alert_cannot_keep_the_stair_shut_past_the_limit(self):
        day = 100 + WILD_DAYS
        ov, g = self.play(threat_resp(day, 30, invader=True, alert=True, inside=10, doors=locked(14)),
                          lock=hold(100, phase="release", why="invaders", alert_off=True), own_locks={14},
                          alert_since=None)                              # the inherited clock was lost
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)
        self.assertEqual(ov.rest_until, (day + WILD_REST) * DAY)

    def test_an_invader_release_opens_once_the_alert_is_seen_off_whatever_else_is_missing(self):
        for gone in ("threats", "doors", None):
            r = threat_resp(113, 30, invader=True, inside=10, doors=locked(14),
                            sites=None if gone is None else (E1,), drop=(gone,) if gone else ())
            ov, g = self.play(r, lock=hold(100, phase="release", why="invaders", alert_off=True), own_locks={14})
            self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}], gone)
            self.assertIsNone(ov.lock, gone)
        r = threat_resp(113, 30, invader=True, inside=10, doors=locked(14), drop=("burrows",))
        ov, g = self.play(r, lock=hold(100, phase="release", why="invaders", alert_off=True), own_locks={14})
        self.assertEqual(g.tools("lock_door"), [])                       # the alert itself cannot be read: wait

    def test_an_alert_is_not_held_blind_over_a_stair_never_seen_shut(self):
        ov, g = self.play(threat_resp(101, 30, alert=True, inside=10, drop=("doors",)), lock=hold(100))
        self.again(ov, g, threat_resp(102, 30, alert=True, inside=10, drop=("doors",)))
        self.assertEqual(g.tools("civilian_alert"), [])
        self.again(ov, g, threat_resp(103, 30, alert=True, inside=10, drop=("doors",)))
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertTrue(ov.wild_off)
        self.assertIsNone(ov.lock)

    def test_a_stair_seen_shut_is_held_through_unreadable_passes(self):
        ov, g = self.play(threat_resp(101, 30, alert=True, inside=10, doors=locked(14)), lock=hold(100),
                          own_locks={14})
        self.assertTrue(ov.lock["shut"])
        for day in range(102, 108):
            self.again(ov, g, threat_resp(day, 30, alert=True, inside=10, drop=("doors",)))
        self.assertEqual(g.tools("civilian_alert"), [])
        self.assertEqual(ov.lock["phase"], "hold")
        self.again(ov, g, threat_resp(108, 30, alert=True, inside=10, doors=locked(14)))
        self.assertEqual(ov.lock["blind"], 0)

    def test_more_hostiles_than_are_listed_are_not_called_gone(self):
        r = threat_resp(105, 150, n=2, alert=True, inside=10, doors=locked(14))
        r["observation"]["threats"]["visible_hostiles"] = 25
        ov, g = self.play(r, lock=hold(100), own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [])
        self.assertEqual(ov.lock["phase"], "hold")

    def test_hostiles_in_sight_without_a_distance_are_not_called_gone(self):
        r = threat_resp(105, 30, alert=True, inside=10, doors=locked(14))
        del r["observation"]["threats"]["nearest_hostile_dist_to_wagon"]
        ov, g = self.play(r, lock=hold(100), own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [])
        self.assertEqual(ov.lock["phase"], "hold")
        r = threat_resp(105, 30, inside=10)
        del r["observation"]["threats"]["nearest_hostile_dist_to_wagon"]
        ov, g = self.play(r)                                             # and nothing starts on it either
        self.assertEqual(g.tools("civilian_alert"), [])

    def test_a_missing_alert_flag_is_not_read_as_alert_off(self):
        r = threat_resp(105, 30, alert=True, inside=10, doors=locked(14))
        del r["observation"]["burrows"]["civilian_alert"]
        ov, g = self.play(r, lock=hold(100), own_locks={14})
        self.assertEqual(g.tools("lock_door"), [])
        self.assertEqual(ov.lock["phase"], "hold")

    def test_a_door_list_or_lock_flag_that_is_not_there_proves_nothing(self):
        r = threat_resp(105, 150, alert=True, inside=10, doors=locked(14))
        del r["observation"]["doors"]["list"]
        ov, g = self.play(r, lock=hold(100, phase="release", why="gone", alert_off=True), own_locks={14})
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])   # asked, not assumed
        r = threat_resp(105, 150, inside=10, doors=locked(14))
        del r["observation"]["doors"]["list"][0]["locked"]
        ov, g = self.play(r, lock=hold(100, phase="release", why="gone", alert_off=True), own_locks={14},
                          refuse={("lock_door", None)})
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertEqual(ov.own_locks, {14})                             # refused and not shown open: still owed

    def test_a_breach_ends_lockdowns_for_good_whatever_else_ends_this_one(self):
        day = 100 + WILD_DAYS
        ov, g = self.play(threat_resp(day, 5, alert=True, inside=10, doors=locked(14), at=(95, 101, 151)),
                          lock=hold(100), own_locks={14})
        self.assertEqual(ov.lock, None)
        self.assertTrue(ov.wild_off)                                     # the limit ended it, the breach counts
        ov, g = self.play(threat_resp(105, 5, alert=True, inside=10, doors=locked(14), at=(95, 101, 151)),
                          lock=hold(100, phase="release", why="gone"), own_locks={14},
                          refuse={("civilian_alert", None)})
        self.assertTrue(ov.wild_off)                                     # seen while a release was under way

    def test_the_model_cannot_open_a_stair_hatch_this_layer_has_not_locked_yet(self):
        other = dict(HATCH, id=15, x=120, y=100)
        ov, g = self.play(threat_resp(190, 30, alert=True, inside=10, doors=locked(14) + [other]),
                          lock=hold(186), own_locks={14}, stairs={"E1": (92, 100, 153), "E2": (120, 100, 153)})
        self.assertTrue(ov.owns_lock({"locked": True, "door_id": 15}))   # a second stair's hatch, not yet owned
        self.assertFalse(ov.owns_lock({"locked": True, "door_id": 30}))

    # ---- the fourth review's cases
    def test_a_fort_let_out_after_an_invader_alert_is_not_shut_in_again_at_once(self):
        inv = dict(invader=True, inside=10, doors=locked(14))
        ov, g = self.play(threat_resp(105, 30, alert=True, **inv), lock=hold(100), own_locks={14})
        self.assertEqual((ov.lock["phase"], ov.lock["why"], ov.alert_since), ("release", "invaders", 100 * DAY))
        self.again(ov, g, threat_resp(111, 30, alert=True, **inv))       # the inherited ten-day rule clears it
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [])                       # seen off only on the next pass
        self.again(ov, g, threat_resp(112, 30, **inv))
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)
        self.assertEqual(ov.rest_until, 113 * DAY)
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])     # not sounded again in the same pass
        r = threat_resp(112, 30, invader=True, inside=10)
        r["tick"] = r["observation"]["date"]["abs_tick"] = 112 * DAY + DAY // 2
        self.again(ov, g, r)
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])     # nor during the day above ground
        self.again(ov, g, threat_resp(113, 30, invader=True, inside=10))
        self.assertEqual(g.tools("civilian_alert")[-1], {"on": True})    # after it the invader rule is as inherited

    def test_no_alert_sounds_over_a_release_that_is_still_being_carried_out(self):
        day = 100 + WILD_DAYS
        inv = dict(invader=True, inside=10, doors=locked(14))
        ov, g = self.play(threat_resp(day, 30, alert=True, **inv),
                          lock=hold(100, phase="release", why="invaders", alert_off=True, rest=True),
                          own_locks={14}, refuse={("lock_door", None)})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])     # taken back at the limit and cleared
        self.assertEqual(ov.own_locks, {14})                             # the unlock was refused
        g.refuse.clear()
        self.again(ov, g, threat_resp(day + 1, 30, **inv))
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])     # the invader rule did not sound it again
        self.assertIsNone(ov.lock)
        self.assertEqual(ov.rest_until, (day + 1 + WILD_REST) * DAY)

    def test_an_alert_found_on_again_is_cleared_again_before_the_stair_opens(self):
        ov, g = self.play(threat_resp(105, 150, alert=True, inside=10, doors=locked(14)),
                          lock=hold(100, phase="release", why="gone", alert_off=True), own_locks={14})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])

    def test_a_stair_seen_open_again_is_no_longer_counted_as_shut(self):
        ov, g = self.play(threat_resp(101, 30, alert=True, inside=10, doors=locked(14)), lock=hold(100),
                          own_locks={14})
        self.assertTrue(ov.lock["shut"])
        self.again(ov, g, threat_resp(102, 30, alert=True, inside=10), )   # the hatch shows unlocked
        self.assertFalse(ov.lock["shut"])

    def test_a_lost_seal_counts_even_when_the_threats_cannot_be_read(self):
        ov, g = self.play(threat_resp(105, 30, alert=True, inside=10, doors=(), drop=("threats",)),
                          lock=hold(100), own_locks={14})
        self.assertTrue(ov.wild_off)

    def test_release_does_not_advance_a_day_it_will_not_use(self):
        class Never(StubGame):
            def act(self, tool, args):
                self.calls.append((tool, dict(args)))
                if tool == "advance_days":
                    return {"ok": True}
                raise ActionLimit("no actions left today")
        ov, g = self.play(threat_resp(190, 30, alert=True, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14})
        ov.game = Never()
        ov.release()
        self.assertEqual(len(ov.game.tools("advance_days")), 2)          # between the three rounds only
        self.assertEqual(ov.own_locks, {14})                             # nothing confirmed: nothing forgotten
        self.assertIsNotNone(ov.lock)

    def test_release_gives_every_call_its_own_chance(self):
        ov, g = self.play(threat_resp(190, 30, alert=True, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14})
        g.calls.clear()
        ov.release()
        self.assertEqual(g.calls, [("civilian_alert", {"on": False}), ("lock_door", {"locked": False, "door_id": 14})])
        self.assertEqual((ov.lock, ov.own_locks), (None, set()))

        class Dying(StubGame):
            def act(self, tool, args):
                self.calls.append((tool, dict(args)))
                if tool == "civilian_alert":
                    raise GameAPIError("gone")
                return {"ok": True}
        ov, g = self.play(threat_resp(190, 30, alert=True, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14})
        ov.game = Dying()
        ov.release()                                                 # must not raise
        self.assertIn(("lock_door", {"locked": False, "door_id": 14}), ov.game.calls)
        self.assertEqual(ov.own_locks, set())
        self.assertEqual(ov.game.tools("civilian_alert"), [{"on": False}] * 3)      # tried again, then left
        self.assertIsNotNone(ov.lock)
        ov, g = self.play(threat_resp(190, None))
        g.calls.clear()
        ov.release()
        self.assertEqual(g.calls, [])                                # nothing held: nothing sent

    def test_release_tries_a_refused_call_again(self):
        class Once(StubGame):                                        # each call is refused the first time
            def act(self, tool, args):
                first = (tool, json.dumps(args, sort_keys=True)) not in {(t, json.dumps(a, sort_keys=True))
                                                                         for t, a in self.calls}
                self.calls.append((tool, dict(args)))
                return {"ok": not first}
        ov, g = self.play(threat_resp(190, 30, alert=True, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14})
        ov.game = Once()
        ov.release()
        self.assertEqual(ov.game.calls, [("civilian_alert", {"on": False}), ("lock_door", {"locked": False,
                                                                                         "door_id": 14})] * 2)
        self.assertEqual((ov.lock, ov.own_locks), (None, set()))

    def test_release_buys_a_new_day_when_the_actions_are_spent(self):
        class Spent(StubGame):
            day = 0

            def act(self, tool, args):
                self.calls.append((tool, dict(args)))
                if tool == "advance_days":
                    self.day += 1
                    return {"ok": True}
                if self.day == 0:
                    raise ActionLimit("no actions left today")
                return {"ok": True}
        ov, g = self.play(threat_resp(190, 30, alert=True, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14})
        ov.game = Spent()
        ov.release()
        self.assertEqual([t for t, _ in ov.game.calls], ["civilian_alert", "lock_door", "advance_days",
                                                          "civilian_alert", "lock_door"])
        self.assertEqual((ov.lock, ov.own_locks), (None, set()))

    def test_an_alert_whose_answer_was_lost_is_cleared_on_the_way_out(self):
        class Lost(StubGame):
            def act(self, tool, args):
                self.calls.append((tool, dict(args)))
                if tool == "civilian_alert" and args.get("on"):
                    raise GameAPIError("no answer")                 # applied or not: unknown
                return {"ok": True}
        ov, g = overseer(threat_resp(186, 74))
        ov.game = Lost()
        with self.assertRaises(GameAPIError):
            ov.defend()
        self.assertIsNone(ov.lock)
        self.assertTrue(ov.alert_pending)
        ov.release()
        self.assertEqual(ov.game.calls[-1], ("civilian_alert", {"on": False}))
        self.assertFalse(ov.alert_pending)
        ov, g = self.play(threat_resp(186, 74), refuse={("civilian_alert", None)})   # a refusal is an answer
        self.assertFalse(ov.alert_pending)

    def test_an_unanswered_alert_seen_off_is_forgotten(self):
        ov, g = self.play(threat_resp(187, 150), alert_pending=True)
        self.assertFalse(ov.alert_pending)
        ov, g = self.play(threat_resp(187, 150, drop=("burrows",)), alert_pending=True)
        self.assertTrue(ov.alert_pending)

    def test_which_model_lock_calls_would_undo_a_lockdown(self):
        ov, g = self.play(threat_resp(190, 30, alert=True, inside=10, doors=locked(14)), lock=hold(186),
                          own_locks={14})
        self.assertTrue(ov.owns_lock({"locked": False}))             # every door at once
        self.assertTrue(ov.owns_lock({"locked": False, "door_id": 14}))
        self.assertFalse(ov.owns_lock({"locked": True, "door_id": 30}))
        ov, g = self.play(threat_resp(190, None))
        self.assertFalse(ov.owns_lock({"locked": True}))             # no lockdown: the doors are the model's

    # ---- the model's own locks (a real-model game: one call locked all three stair hatches)
    def test_the_model_cannot_shut_a_surface_stair_itself(self):
        mine = {"id": 30, "kind": "door", "built": True, "locked": False, "x": 95, "y": 101, "z": 151}
        ov, g = self.play(threat_resp(190, None, doors=(HATCH, mine)))
        self.assertIsNone(ov.lock)
        self.assertTrue(ov.seals_stair({"locked": True}))                    # every door at once
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 14}))     # the hatch on the stair
        self.assertFalse(ov.seals_stair({"locked": True, "door_id": 30}))    # its own door somewhere else
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 99}))     # not in the list: it cannot be placed
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": "14"}))
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": True}))
        self.assertFalse(ov.seals_stair({"locked": False}))                  # opening is never refused here
        self.assertFalse(ov.seals_stair({"locked": False, "door_id": 14}))
        self.assertEqual(g.tools("lock_door"), [])

    def test_a_door_of_any_kind_on_a_stair_that_left_the_list_still_counts(self):
        door = {"id": 21, "kind": "door", "built": True, "locked": False, "x": 92, "y": 100, "z": 153}
        ov, g = self.play(threat_resp(190, None))
        self.again(ov, g, threat_resp(192, None, doors=(door,), sites=()))
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 21}))

    def test_the_guard_on_the_stairs_outlives_a_reply_without_the_task_clock(self):
        ov, g = self.play(threat_resp(190, None))
        r = threat_resp(192, None)
        del r["days_left"]
        self.again(ov, g, r)
        self.assertFalse(ov.open_play())
        self.assertTrue(ov.seals_stair({"locked": True}))
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 14}))

    # ---- the fifth review's cases
    def test_a_hatch_on_the_surface_that_no_stair_list_has_is_not_locked_for_the_model(self):
        far = dict(HATCH, id=77, x=131)                  # a surface stair outside the 30 tiles the stair list covers
        deep = {"id": 30, "kind": "hatch", "built": True, "locked": False, "x": 95, "y": 101, "z": 151}
        ov, g = self.play(threat_resp(100, None, doors=(far, deep), sites=()))
        self.assertEqual(ov.stairs, {})
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 77}))
        self.assertFalse(ov.seals_stair({"locked": True, "door_id": 30}))    # below the surface: the model's own
        hill = dict(far, id=78, z=155)
        self.again(ov, g, threat_resp(102, None, doors=(far, deep, hill), sites=()))
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 78}))     # above the wagon's level too

    def test_the_surface_level_is_remembered_through_a_reply_without_it(self):
        far = dict(HATCH, id=77, x=131)
        deep = {"id": 30, "kind": "door", "built": True, "locked": False, "x": 95, "y": 101, "z": 151}
        ov, g = self.play(threat_resp(100, None, doors=(far, deep), sites=()))
        r = threat_resp(102, None, doors=(far, deep), sites=())
        del r["observation"]["map"]["surface_z"]
        self.again(ov, g, r)
        self.assertEqual(ov.surface_seen, 153)
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 77}))
        self.assertFalse(ov.seals_stair({"locked": True, "door_id": 30}))

    def test_without_a_surface_level_no_lock_is_passed_on(self):
        deep = {"id": 30, "kind": "door", "built": True, "locked": False, "x": 95, "y": 101, "z": 151}
        r = threat_resp(100, None, doors=(HATCH, deep))
        del r["observation"]["map"]["surface_z"]
        ov, g = self.play(r)
        self.assertIsNone(ov.surface_seen)
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 30}))
        self.assertFalse(ov.seals_stair({"locked": False, "door_id": 30}))

    def test_the_guard_on_the_stairs_is_up_before_any_stair_is_known_and_without_the_clock(self):
        r = threat_resp(100, None, sites=())
        del r["days_left"]
        ov, g = self.play(r)
        self.assertEqual(ov.stairs, {})
        self.assertFalse(ov.open_play())
        self.assertTrue(ov.open_task())
        self.assertTrue(ov.seals_stair({"locked": True}))

    def test_a_day_above_ground_is_owed_on_a_reply_without_the_task_clock_too(self):
        inv = dict(invader=True, inside=10, doors=locked(14))
        ov, g = self.play(threat_resp(105, 30, alert=True, **inv), lock=hold(100), own_locks={14})
        self.again(ov, g, threat_resp(111, 30, alert=True, **inv))       # the inherited ten-day rule clears it
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        r = threat_resp(112, 30, **inv)
        del r["days_left"]
        self.again(ov, g, r)
        self.assertFalse(ov.open_play())
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])
        self.assertIsNone(ov.lock)
        self.assertEqual(ov.rest_until, 113 * DAY)
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])     # not sounded again over the open stair

    def test_a_refused_invader_clear_keeps_its_clock_without_the_task_clock_too(self):
        r = threat_resp(111, 30, invader=True, alert=True, inside=10, doors=locked(14))
        del r["days_left"]
        ov, g = self.play(r, lock=hold(100, phase="release", why="invaders", alert_off=True), own_locks={14},
                          alert_since=100 * DAY, refuse={("civilian_alert", None)})
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(ov.alert_since, 100 * DAY)

    def test_without_a_door_list_no_lock_is_passed_on(self):
        ov, g = self.play(threat_resp(190, None, drop=("doors",)))
        self.assertTrue(ov.seals_stair({"locked": True, "door_id": 30}))
        self.assertFalse(ov.seals_stair({"locked": False, "door_id": 30}))

    def test_on_a_lab_task_the_doors_stay_the_models(self):
        r = threat_resp(30, None)
        r["hands_off_in_days"] = 9
        ov, g = self.play(r)
        self.assertFalse(ov.seals_stair({"locked": True}))
        self.assertFalse(ov.seals_stair({"locked": True, "door_id": 14}))

    def test_a_dug_level_too_large_for_one_burrow_call_is_left_out(self):
        big = {"id": "A2", "kind": "A", "z": 149, "w": 42, "h": 51, "open_tiles": 43}
        fits = {"id": "A1", "kind": "A", "z": 150, "w": 40, "h": 12, "open_tiles": 40}
        ov, g = self.play(threat_resp(50, None, sites=(E1, big, fits)))
        self.again(ov, g, threat_resp(56, None, sites=(E1, big, fits)))
        self.assertEqual(g.tools("create_burrow"), [{"site": "A1"}])
        self.assertEqual(ov.sheltered, {"A1": 40})

    def test_a_standing_lockdown_is_still_ended_if_the_task_clock_goes_missing(self):
        r = threat_resp(190, 150, alert=True, inside=10, doors=locked(14))
        del r["days_left"]
        ov, g = self.play(r, lock=hold(186), own_locks={14})
        self.assertFalse(ov.open_play())
        self.assertEqual(g.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(g.tools("lock_door"), [{"locked": False, "door_id": 14}])

    def test_one_day_passes_while_a_hostile_is_in_sight(self):
        ov, g = self.play(threat_resp(190, 140))
        self.assertEqual(ov.step_days(), 1)
        ov, g = self.play(threat_resp(190, None))
        self.assertEqual(ov.step_days(), 2)


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
        g = WalkGame(threats={100: 80, 101: 74, 102: 68, 103: 61, 104: 54, 105: 47, 106: 40})   # 6-7 tiles a day
        out = plain(g).open_advance({"days": 7})
        self.assertEqual(g.advances, [2, 1, 1])                          # one day at a time once it is in sight
        self.assertIn("26 tiles closer", out["result"]["harness_stop"])


if __name__ == "__main__":
    unittest.main()
