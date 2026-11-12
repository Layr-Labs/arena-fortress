"""cx regressions: year-round plant allocation by the short supply leg, the cook standings' seeds floor through
add_manager_order (seeds is no add_order stock; a fourth clause is rejected), the observed-form when comparison,
the glut bank's caravan/min-leg gates, o_brew_end's floor, the wildlife civilian alert (the day-80 carnotaurus),
the stress bedroom scenario, and the wealth front-loading. No game or network."""
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
    def __init__(self, units=(), reject=()):
        self.calls = []
        self.units = list(units)
        self.reject = set(reject)
        self.queries = 0

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        if tool in self.reject:
            return {"ok": False, "error_code": "bad_arguments", "error": "Invalid item type SEEDS"}
        return {"ok": True, "result": {"order_id": 100 + len(self.calls)}}

    def query(self, *a, **kw):
        self.queries += 1
        return {"result": {"units": list(self.units)}}


def resp(day=100, days=336, days_left=None, cit=12, drink=300, food=300, pb=30, pt=None, seeds=60, barrels=20,
         farms=0, hands_off=None, orders=(), workshops=("Carpenters", "Still", "Kitchen"), extra=None):
    stocks = {"drink": drink, "food_edible": food, "prepared_meals": 10, "plants_brewable": pb,
              "plants_total": pb + 5 if pt is None else pt, "barrels_empty": barrels, "logs_usable": 60,
              "seeds": seeds, "furniture_free": {}}
    obs = {"date": {"abs_tick": day * harness.DAY}, "administrators": {"citizens": cit},
           "stocks": stocks, "map": {"sites": []}, "zones": [], "furniture": [],
           "workshops": [{"type": w} for w in workshops], "orders": list(orders),
           "farm_plots": [{"id": i, "z": 140} for i in range(farms)]}
    obs.update(extra or {})
    r = {"tick": day * harness.DAY, "day": day, "observation": obs,
         "days_left": days_left if days_left is not None else days - day}
    if hands_off is not None:
        r["hands_off_in_days"] = hands_off
    return r


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, days=336, game=None, **kw):
        game = game or FakeGame()
        ov = harness.Overseer(game, days=days)
        ov.load(resp(days=days, **kw))
        ov.count = 0
        return ov, game


class Allocation(Base):
    # the measured MY1 fort: food 304 / drink 220 at day -150 — drink is the short leg, the kitchen yields
    def test_drink_short_leg_runs_the_still_and_holds_the_kitchen(self):
        ov, _ = self.ov(days=216, day=66, cit=12, drink=220, food=304)
        self.assertEqual(ov.allocation(), frozenset({"brew"}))
        self.assertEqual(ov.cook_floor(), ov.hold_floor())
        # cx plant barrel keep: a short open-play run's o_brew fires 2 over a floor of 3 (one plant stays barrelled)
        self.assertEqual(ov.brew_floor(), harness.BARREL_KEEP_AMOUNT + harness.BARREL_KEEP)
        pb = [c for c in ov.cook_when() if c["stock"] == "plants_brewable"][0]
        self.assertEqual(pb["at_least"], harness.PLANT_RESERVE_PER_CIT * 12 + harness.ALLOC_HOLD_MARGIN)

    # the measured food-short fort: 6.5 food per citizen while it kept brewing — the Still yields
    def test_food_short_leg_runs_the_kitchen_and_holds_the_still(self):
        ov, _ = self.ov(day=150, cit=12, drink=400, food=78)
        self.assertEqual(ov.allocation(), frozenset({"cook"}))
        self.assertEqual(ov.brew_floor(), ov.hold_floor())
        self.assertEqual(ov.brew_when()[1], {"stock": "plants_brewable", "at_least": ov.hold_floor()})
        self.assertEqual(ov.cook_floor(), harness.COOK_PLANTS_RESERVE)

    def test_balanced_or_both_short_runs_both(self):
        ov, _ = self.ov(day=150, cit=12, drink=100, food=50)   # both under ALLOC_SHORT_DAYS
        self.assertEqual(ov.allocation(), frozenset({"brew", "cook"}))
        ov2, _ = self.ov(day=150, cit=12, drink=400, food=250)   # neither 1.5x ahead
        self.assertEqual(ov2.allocation(), frozenset({"brew", "cook"}))

    def test_last_stretch_runs_both_and_converts_the_reserve(self):
        ov, _ = self.ov(day=290, cit=12, drink=220, food=900)
        self.assertTrue(ov.last_stretch())
        self.assertEqual(ov.allocation(), frozenset({"brew", "cook"}))
        self.assertEqual(ov.plant_floor(), 2)

    def test_reserve_build_window_holds_two_per_citizen(self):
        ov, _ = self.ov(day=336 - harness.LAST_STRETCH_DAYS - 20, cit=16, drink=400, food=250)
        self.assertTrue(ov.reserve_build())
        self.assertEqual(ov.plant_floor(), 32)
        self.assertEqual(ov.cook_floor(), 32)

    def test_flip_waits_the_dwell(self):
        ov, game = self.ov(day=100, cit=12, drink=220, food=600)
        self.assertEqual(ov.allocation(), frozenset({"brew"}))
        ov.load(resp(day=102, cit=12, drink=600, food=80))
        self.assertEqual(ov.allocation(), frozenset({"brew"}))   # 2 days < ALLOC_DWELL_DAYS
        ov.load(resp(day=100 + harness.ALLOC_DWELL_DAYS, cit=12, drink=600, food=80))
        self.assertEqual(ov.allocation(), frozenset({"cook"}))

    def test_lab_tasks_keep_the_legacy_shapes(self):
        for days, ho in ((60, 10), (30, 5), (336, 20)):
            ov, game = self.ov(days=days, day=10, cit=12, drink=10, food=900, hands_off=ho)
            self.assertFalse(ov.alloc_on())
            self.assertEqual(ov.allocation(), frozenset({"brew", "cook"}))
            self.assertEqual(ov.brew_floor(), 1)   # cx: a lab task brews its first plant (test_seed_truth)
            ov.allocate_plants()
            self.assertEqual(game.calls, [])

    def test_one_shot_brew_while_drink_is_short(self):
        ov, game = self.ov(days=216, day=66, cit=12, drink=220, food=304, pb=30)
        ov.allocate_plants()
        brews = [a for t, a in game.calls if a.get("recipe") == "brew_drink"]
        self.assertEqual(brews, [{"recipe": "brew_drink", "amount": harness.ALLOC_BREW_MAX}])
        self.assertNotIn("cook_meal", [a.get("recipe") for _, a in game.calls])
        # the order is still on the book: no second batch
        ov.load(resp(days=216, day=67, cit=12, drink=220, food=304, pb=30,
                     orders=[{"id": ov.key_order["o_brew_alloc"], "recipe": "brew_drink", "left": 5}]))
        game.calls.clear()
        ov.allocate_plants()
        self.assertEqual(game.calls, [])

    def test_one_shot_cook_while_food_is_short_respects_the_seeds_floor(self):
        ov, game = self.ov(day=150, cit=12, drink=400, food=78, pb=20, farms=4, seeds=60)
        ov.allocate_plants()
        self.assertEqual([a.get("recipe") for _, a in game.calls], ["cook_meal"])
        ov2, game2 = self.ov(day=150, cit=12, drink=400, food=78, pb=20, farms=4, seeds=20)   # under 4 x 9
        ov2.allocate_plants()
        self.assertEqual(game2.calls, [])

    def test_last_stretch_brews_and_cooks(self):
        ov, game = self.ov(day=300, cit=12, drink=220, food=200, pb=30)
        ov.allocate_plants()
        self.assertEqual(sorted(a.get("recipe") for _, a in game.calls), ["brew_drink", "cook_meal"])


class CookSeeds(Base):
    def test_cook_standing_with_plots_is_a_manager_order_of_three(self):
        ov, game = self.ov(day=100, cit=12, drink=300, food=300, farms=3)
        ov.supply()
        cook = [(t, a) for t, a in game.calls if a.get("job") == "PrepareMeal"]
        self.assertEqual(len(cook), 1)
        tool, args = cook[0]
        self.assertEqual(tool, "add_manager_order")
        self.assertEqual(args["when"], [{"item_type": "FOOD", "below": harness.MEAL_CAP},
                                        {"item_type": "SEEDS", "at_least": 3 * harness.SEEDS_PER_PLOT},
                                        {"item_type": "PLANT", "flags": ["unrotten"], "reaction_product": "DRINK_MAT",
                                         "at_least": ov.cook_floor()}])
        for t, a in game.calls:   # no add_order anywhere carries a fourth clause or the seeds stock
            if t == "add_order" and a.get("when"):
                self.assertLessEqual(len(a["when"]), 3)
                self.assertNotIn("seeds", [c.get("stock") for c in a["when"]])

    def test_rejected_seeds_condition_falls_back_to_add_order(self):
        ov, game = self.ov(day=100, cit=12, drink=300, food=300, farms=3,
                           game=FakeGame(reject={"add_manager_order"}))
        ov.supply()
        self.assertFalse(ov.seeds_cond_ok)
        ov.supply()
        cooks = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "cook_meal"]
        self.assertEqual(len(cooks), 1)
        self.assertLessEqual(len(cooks[0]["when"]), 3)

    def test_winter_cook_push_is_valid(self):
        ov, game = self.ov(days=336, day=230, cit=12, drink=50, food=20, farms=3)
        ov.winter_plan()
        cook = [(t, a) for t, a in game.calls if a.get("job") == "PrepareMeal" or a.get("recipe") == "cook_meal"]
        self.assertEqual(len(cook), 1)
        self.assertEqual(cook[0][0], "add_manager_order")
        self.assertLessEqual(len(cook[0][1]["when"]), 3)
        self.assertIn({"item_type": "SEEDS", "at_least": 27}, cook[0][1]["when"])

    def test_observed_form_does_not_recut(self):
        ov, game = self.ov(day=100, cit=12, drink=300, food=300, farms=3)
        tool, args = ov.cook_order(ov.cook_when())
        observed = [{"item_type": "FOOD", "test": "LessThan", "value": harness.MEAL_CAP, "flags": []},
                    {"item_type": "SEEDS", "test": "AtLeast", "value": 27, "flags": []},
                    {"item_type": "PLANT", "flags": ["unrotten"], "reaction_product": "DRINK_MAT",
                     "test": "AtLeast", "value": ov.cook_floor()}]
        ov.key_order["o_cook"] = 5
        ov.orders = [{"id": 5, "recipe": "cook_meal", "repeat": "daily", "when": observed}]
        self.assertFalse(ov.sync_cook("o_cook", args["when"]))
        observed[2]["value"] = 99
        self.assertTrue(ov.sync_cook("o_cook", args["when"]))

    def test_sync_brew_reads_the_observed_form(self):
        ov, game = self.ov(day=100, cit=12, drink=150, food=200)
        ov.key_order["o_brew"] = 9
        ov.orders = [{"id": 9, "recipe": "brew_drink", "repeat": "daily", "when": [
            {"item_type": "DRINK", "test": "LessThan", "value": ov.brew_cap(), "flags": [], "stock": "drink"},
            {"item_type": "PLANT", "flags": ["unrotten"], "reaction_product": "DRINK_MAT", "test": "AtLeast",
             "value": ov.brew_floor(), "stock": "plants_brewable"},
            {"item_type": "BARREL", "flags": ["empty"], "test": "AtLeast", "value": 1, "stock": "barrels_empty"}]}]
        self.assertFalse(ov.sync_brew())   # was: when[0].below is None -> recut every 4 days
        self.assertEqual(game.calls, [])


class GlutAndCloser(Base):
    def test_own_harvest_banks_while_the_caravan_stays(self):
        ov, game = self.ov(day=200, cit=12, drink=150, food=400, pb=50)
        ov.caravan_active, ov.caravan_arrival_day = True, 190
        ov.glut_bank()
        self.assertEqual([a for t, a in game.calls if a.get("recipe") == "brew_drink"],
                         [{"recipe": "brew_drink", "amount": 5}])

    def test_caravan_arrival_jump_is_skipped(self):
        ov, game = self.ov(day=200, cit=12, drink=150, food=400, pb=50)
        ov.caravan_active, ov.caravan_arrival_day, ov.glut_jump = True, 200, 25
        ov.glut_bank()
        self.assertEqual(game.calls, [])

    def test_glut_yields_when_the_allocation_holds_the_still(self):
        ov, game = self.ov(day=150, cit=12, drink=400, food=78, pb=50)
        ov.glut_bank()
        self.assertEqual(game.calls, [])

    def test_brew_end_floor_sits_under_the_cook_floor(self):
        self.assertLess(harness.BREW_END_FLOOR, harness.COOK_PLANTS_RESERVE)
        ov, game = self.ov(day=300, cit=20, drink=220, food=400, pb=10)
        ov.endgame_supply()
        end = [a for t, a in game.calls if a.get("recipe") == "brew_drink" and a.get("repeat")]
        self.assertEqual(end[0]["when"][1], {"stock": "plants_brewable", "at_least": harness.BREW_END_FLOOR})

    def test_brew_end_retires_when_the_allocation_holds_the_still(self):
        ov, game = self.ov(day=150, cit=12, drink=400, food=78, pb=10)
        ov.key_order["o_brew_end"] = 7
        ov.owned.add(7)
        ov.endgame_supply()
        self.assertIn(("cancel_order", {"order_id": 7}), game.calls)


class Wildlife(Base):
    CARNO = {"id": 501, "race": "CARNOTAURUS", "hostile": True, "visitor": False}

    def fort(self, day, cancels=(), alert=False, squads=()):
        return resp(day=day, cit=7, extra={
            "recent_cancellations": list(cancels),
            "burrows": {"civilian_alert": alert, "list": [{"id": 1, "civ_alert_burrow": True}]},
            "military": {"squads": list(squads)}, "threats": {}})

    def test_first_sighting_sounds_the_alert_without_a_squad(self):
        game = FakeGame(units=[self.CARNO])
        ov = harness.Overseer(game, days=336)
        ov.load(self.fort(80, ["Urist cancels Gather Plants: Interrupted by a carnotaurus."]))
        ov.count = 0
        ov.wildlife_response()
        self.assertIn(("civilian_alert", {"on": True}), game.calls)
        # defend keeps it while the hold lasts (no invader in sight), then lifts it
        ov.load(self.fort(81, alert=True))
        game.calls.clear()
        ov.defend()
        self.assertNotIn(("civilian_alert", {"on": False}), game.calls)
        ov.load(self.fort(80 + harness.WILD_ALERT_DAYS + 1, alert=True))
        ov.defend()
        self.assertIn(("civilian_alert", {"on": False}), game.calls)

    def test_no_alert_for_a_harmless_animal_or_with_an_armed_squad(self):
        game = FakeGame(units=[{"id": 9, "race": "GOOSE", "hostile": False}])
        ov = harness.Overseer(game, days=336)
        ov.load(self.fort(80, ["Urist cancels Fish: Interrupted by a goose."]))
        ov.count = 0
        ov.wildlife_response()
        self.assertNotIn("civilian_alert", [t for t, _ in game.calls])
        game2 = FakeGame(units=[self.CARNO])
        ov2 = harness.Overseer(game2, days=336)
        ov2.load(self.fort(80, ["Urist cancels Fish: Interrupted by a carnotaurus."],
                           squads=[{"id": 1, "armed": 4, "orders": []}]))
        ov2.count = 0
        ov2.wildlife_alert()
        self.assertEqual(game2.calls, [])


class StressScenario(Base):
    def test_stressed_fort_gets_private_bedrooms(self):
        """The OP1 41.8 aftermath: 12/16 strongly stressed, bedrooms assigned 0 — §J acts given a spare room."""
        people = [{"id": i, "stress": 0 if i < 12 else 4} for i in range(16)]
        sites = [{"id": "R%d" % i, "kind": "R", "dug": True, "x": 10 * i, "y": 5, "z": 140, "w": 5, "h": 5}
                 for i in range(5)]
        game = FakeGame()
        ov = harness.Overseer(game, days=336)
        ov.load(resp(day=170, cit=16, extra={"dwarves": people, "map": {"sites": sites}}))
        ov.count = 0
        ov.stress_housing()
        zones = [a for t, a in game.calls if t == "make_zone" and a.get("kind") == "bedroom"]
        self.assertEqual(len(zones), harness.STRESS_ROOM_CAP)
        self.assertEqual(len({z["site"] for z in zones}), harness.STRESS_ROOM_CAP)

    def test_no_spare_room_digs_one(self):
        """cx hint MY1: one dwarf stuck stressed, every dug room taken -> dig a room reserved for them."""
        people = [{"id": i, "stress": 1 if i == 0 else 4} for i in range(16)]
        sites = [{"id": "R0", "kind": "R", "designated": False, "dug": False, "x": 10, "y": 5, "z": 140,
                  "w": 3, "h": 3}]
        game = FakeGame()
        ov = harness.Overseer(game, days=336)
        ov.load(resp(day=170, cit=16, extra={"dwarves": people, "map": {"sites": sites}}))
        ov.count = 0
        ov.stress_housing()
        self.assertIn(("dig_room", {"site": "R0"}), [(t, a) for t, a in game.calls if t == "dig_room"])
        self.assertEqual(ov.roles.get("R0"), "stress")


class WealthFrontLoad(Base):
    def test_checkpoint_keeps_the_full_amount(self):
        ov, _ = self.ov(day=70, cit=12)
        ov.o["wealth"] = {"created": 5000}
        ov.craft_mark = (50, 2000)   # 150/day: on track for day 205's fund, not for 9k by day 90
        self.assertEqual(ov.craft_amount_chase(), harness.CRAFT_AMOUNT_WAVE)
        ov.craft_mark = (50, 1000)   # 200/day clears both
        self.assertEqual(ov.craft_amount_chase(), harness.CRAFT_AMOUNT_BASE)


if __name__ == "__main__":
    unittest.main()


class CookFoodRetire(unittest.TestCase):
    def test_regular_cook_ignores_emergency(self):
        from overseer import harness as h
        ov = h.Overseer.__new__(h.Overseer)
        ov.key_order = {"o_cook_food": 87}
        ov.owned = {87}
        ov.orders = [{"id": 87, "recipe": "cook_meal", "repeat": "daily"}]
        self.assertFalse(ov.regular_cook_on_book())
        ov.orders.append({"id": 90, "recipe": "cook_meal", "repeat": "daily"})
        self.assertTrue(ov.regular_cook_on_book())


class TroopAlert(unittest.TestCase):
    def test_unflagged_troop_sounds_the_alert_even_with_a_squad(self):
        from overseer import harness as h
        T = sys.modules[__name__]
        base = T.Wildlife()
        game = T.FakeGame(units=[{"id": 9, "race": "GRAY_LANGUR", "hostile": False}])
        ov = h.Overseer(game, days=336)
        lines = ["A%d cancels Drink: Interrupted by a gray langur." % i for i in range(4)]
        ov.load(base.fort(153, lines, squads=[{"id": 1, "armed": 4, "orders": []}]))
        ov.count = 0
        ov.wildlife_alert()
        self.assertIn("civilian_alert", [t for t, _ in game.calls])


class SeedFloorEndgame(unittest.TestCase):
    def test_floor_drops_in_the_last_stretch_of_open_play(self):
        from overseer import harness as h
        ov = h.Overseer.__new__(h.Overseer)
        ov.o = {"farm_plots": [{}] * 5}
        ov.hands_off = None
        ov.days_to_end = lambda: 30
        ov.harvest_closed = lambda: False
        self.assertEqual(ov.seed_floor(), 0)
        ov.days_to_end = lambda: 120
        self.assertEqual(ov.seed_floor(), 5 * h.SEEDS_PER_PLOT)
        ov.hands_off = 20
        ov.days_to_end = lambda: 30
        self.assertEqual(ov.seed_floor(), 5 * h.SEEDS_PER_PLOT)


class StillBacklog(unittest.TestCase):
    def test_backlog_builds_a_second_still(self):
        from overseer import harness as h
        ov = h.Overseer.__new__(h.Overseer)
        ov.o = {"workshops": [{"type": "Carpenters"}, {"type": "Still"}, {"type": "Kitchen"}, {"type": "Fishery"}]}
        ov.orders = [{"recipe": "brew_drink", "repeat": None, "left": 5, "active": True}] * 4
        ov.hands_off = None
        ov.rot_seen = False
        ov.surge = False
        ov.shop_stale = lambda w: False
        ov.logs = lambda: 50
        ov.food_alarm = lambda: False
        ov.people = []
        built = []
        ov.build = lambda t, retry=3, key=None: built.append((t, key))
        ov.workshops()
        self.assertEqual(built, [("Still", "ws_Still_2"), ("Carpenters", "ws_Carpenters_2")])
        built.clear(); ov.hands_off = 20
        ov.workshops()
        self.assertEqual(built, [])


class MeetingArea(unittest.TestCase):
    def test_zone_once_when_none(self):
        from overseer import harness as h
        ov = h.Overseer.__new__(h.Overseer)
        ov.breach = False
        ov.zone = lambda w: []
        ov.stress_site = lambda **kw: {"id": "R3"}
        calls = []
        ov.act = lambda k, t, a, retry=3, limit=6: calls.append((k, t, a))
        ov.meeting_area()
        self.assertEqual(calls, [("z_meeting", "make_zone", {"kind": "meeting_area", "site": "R3"})])
        calls.clear(); ov.zone = lambda w: [{"type": "MeetingHall"}]
        ov.meeting_area()
        self.assertEqual(calls, [])


class WildGone(unittest.TestCase):
    def ov(self, now, last, marked=(), near=()):
        from overseer import harness as h
        ov = h.Overseer.__new__(h.Overseer)
        ov.now, ov.day = now, now // h.DAY
        ov.wild_alert_since = 0
        ov.wild_watch = {"gray langur": last}
        ov.wild_budget_left = lambda: True
        ov.marked_units = lambda t, z: list(marked)
        ov.wild_near_units = lambda names: list(near)
        return ov, h

    def test_lifts_one_day_after_last_seen(self):
        ov, h = self.ov(now=int(1.5 * 1200), last=int(0.2 * 1200))
        self.assertFalse(ov.wild_alert_hold())

    def test_holds_while_seen_recently_or_within_range(self):
        ov, h = self.ov(now=int(1.5 * 1200), last=int(1.0 * 1200))
        self.assertTrue(ov.wild_alert_hold())
        ov, h = self.ov(now=int(2.5 * 1200), last=0, marked=[{"_mark": "gray langur"}])
        self.assertTrue(ov.wild_alert_hold())


class MoodShopRebuild(unittest.TestCase):
    def test_vanished_mood_shop_is_rebuilt(self):
        from overseer import harness as h
        ov = h.Overseer.__new__(h.Overseer)
        ov.o = {"moods": [{"mood": "Fey", "skill": "WOODCRAFT", "claimed_building_id": None}],
                "workshops": [{"type": "Carpenters"}]}
        ov.done = {"ws_Craftsdwarfs"}
        ov.now = 5 * h.DAY
        built = []
        ov.build = lambda t, retry=3, key=None: built.append((t, key))
        ov.butcher = lambda: None
        ov.mood()
        want = h.MOOD_WORKSHOP.get("WOODCRAFT", "Craftsdwarfs")
        self.assertEqual(built[0][0], want)
        self.assertNotIn("ws_" + want, ov.done)


class StressBedBySite(Base):
    """cx (hint hard LT03-0 on f2bd283): the stressed dwarf's bed went out as raw x,y,z,w,h and the server answered
    "args.site is required" — every site tool needs `site`; the bed goes to the zone's own site with its w/h."""

    def test_the_private_bed_is_placed_by_the_rooms_site(self):
        class ZoneGame(FakeGame):
            def act(self, tool, args):
                if tool == "make_zone":
                    self.calls.append((tool, args))
                    return {"ok": True, "result": {"zone_id": 61, "at": [10, 5, 140]}}
                return super().act(tool, args)
        people = [{"id": 0, "stress": 0}] + [{"id": i, "stress": 4} for i in range(1, 12)]
        sites = [{"id": "R0", "kind": "R", "dug": True, "x": 10, "y": 5, "z": 140, "w": 5, "h": 5}]
        game = ZoneGame()
        ov = harness.Overseer(game, days=336)
        r = resp(day=170, cit=12, extra={"dwarves": people, "map": {"sites": sites}})
        r["observation"]["stocks"]["furniture_free"] = {"bed": 2}
        ov.load(r)
        ov.count = 0
        ov.stress_housing()
        beds = [a for t, a in game.calls if t == "place_furniture"]
        self.assertEqual(beds, [{"kind": "bed", "site": "R0", "w": harness.STRESS_ROOM_SIZE,
                                 "h": harness.STRESS_ROOM_SIZE, "count": 1}])
