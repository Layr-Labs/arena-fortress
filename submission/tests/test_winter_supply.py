"""The winter measures and the caravan exclusion (ROOT_CAUSES §C/§D/§G/§X):

- the internal calendar: day % 336 // 84 is the season (docs/SUCCESS.md T_STAR: a 336-day year of 84-day seasons);
- D-1 the winter cook release: the cook standings' plants_brewable reserve drops out of their when in winter, where
  it sat unreachable (pb = 0) and inactivated every cook order (df2-op1-hard/OP1-1 d302-330), and the food-security
  guard counts only orders the game still marks active;
- D-2 the winter plan: once a year at the growth season's end (OP1 ~220, MY1 ~100) the winter's pantry is sized at
  citizens x (drink 20, food 10) plus the consumption until the F window opens, and a shortfall full-opens brewing
  (uncapped when no winter-growing seed can brew after the harvest, capped at the need when one can) and cooking;
- C the seed protection: below SEEDS_PER_PLOT per plot the cook standings carry a seeds floor, so the seed-bearing
  plants reach the Still (brewing returns seeds, cooking never does);
- G the min-leg allocation: the glut bank draws only while drink is the short leg, and the closer's brew standing
  retires inside BREW_SPARE_DAYS when food falls while drink holds;
- X the caravan exclusion: the announcement stream (FIRST_CARAVAN_ARRIVAL / CARAVAN_ARRIVAL until
  MERCHANTS_EMBARKED + a haul-out grace) drives caravan_active, and the stock rules (glut bank, slide and food
  alarms, the standing brew/fruit adds) hold off while the merchants' goods sit in the observed stocks;
- the brew-lock guard is gone (ROOT_CAUSES §5.2: a misdiagnosis — the "locked" brews were the caravan glut §X and
  the flood's frozen farms).

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
    def __init__(self, pages=()):
        self.calls = []          # act() calls only: (tool, args)
        self.probes = []         # events() since_ticks, in order
        self.pages = list(pages)

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"order_id": len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {}}

    def events(self, since_tick=0):
        self.probes.append(since_tick)
        return self.pages.pop(0) if self.pages else {"events": [], "dropped": 0}


def resp(day, days_left=60, drink=120, food=90, pb=5, meals=10, hands_off=None, cit=10,
         farms=None, seed_kinds=None, orders=()):
    stocks = {"drink": drink, "food_edible": food, "prepared_meals": meals, "plants_brewable": pb,
              "plants_total": pb + 5, "barrels_empty": 20, "logs_usable": 60, "seeds": 40}
    if seed_kinds is not None:
        stocks["seeds_by_kind"] = seed_kinds
    obs = {"date": {"abs_tick": day * harness.DAY}, "administrators": {"citizens": cit},
           "stocks": stocks, "map": {"sites": []}, "zones": [], "furniture": [], "workshops": [],
           "orders": list(orders)}
    if farms is not None:
        obs["farm_plots"] = list(range(farms))
    return {"day": day, "tick": day * harness.DAY, "days_left": days_left, "hands_off_in_days": hands_off,
            "observation": obs}


SEEDS_WINTER = {"plump helmet": {"n": 5, "underground": True, "seasons": ["spring", "summer", "autumn", "winter"]}}
SEEDS_NO_WINTER = {"sweet pod": {"n": 5, "underground": True, "seasons": ["spring", "summer", "autumn"]}}


class WinterSupply(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, pages=(), days=336):
        game = FakeGame(pages)
        ov = harness.Overseer(game, days=days)
        ov.count = 0
        return ov, game

    # ---- the internal calendar
    def test_season_map_matches_the_success_doc(self):
        ov, _ = self.overseer()
        for day, want in ((0, 0), (83, 0), (84, 1), (167, 1), (168, 2), (251, 2), (252, 3), (335, 3),
                          (336, 0), (500, 1)):      # 500 % 336 = 164 -> summer
            ov.day = day
            self.assertEqual(ov.season(), want, day)
            self.assertEqual(ov.winter(), want == 3, day)

    # ---- (a) the winter cook release: the pb reserve leaves the when where it is unreachable
    def test_winter_cook_standing_drops_the_pb_reserve(self):
        ov, game = self.overseer()
        ov.load(resp(260, farms=0))                       # winter, pb 5: the reserve would block nothing here,
        ov.supply()                                        #   but pb 0 farms are the point — the clause is gone
        cook = next(a for t, a in game.calls if a.get("recipe") == "cook_meal")
        self.assertEqual(cook["when"], [{"stock": "prepared_meals", "below": harness.MEAL_CAP},
                                        {"stock": "plants_total", "at_least": 10}])
        self.assertNotIn("plants_brewable", [w.get("stock") for w in cook["when"]])

    def test_growth_season_cook_standing_keeps_the_pb_reserve(self):
        ov, game = self.overseer()
        ov.load(resp(100, farms=0))                       # late spring of a 336-day run
        ov.supply()
        cook = next(a for t, a in game.calls if a.get("recipe") == "cook_meal")
        self.assertEqual(cook["when"], [{"stock": "prepared_meals", "below": harness.MEAL_CAP},
                                        {"stock": "plants_total", "at_least": 10},
                                        {"stock": "plants_brewable", "at_least": harness.COOK_PLANTS_RESERVE}])

    def test_winter_release_recuts_the_standing_the_autumn_added(self):
        ov, game = self.overseer()
        ov.load(resp(240, farms=0))                       # autumn: the standing is added with the reserve
        ov.supply()
        first = next(a for t, a in game.calls if a.get("recipe") == "cook_meal")
        ov.day, ov.now, ov.caravan_probe_day = 262, 262 * harness.DAY, None
        ov.o["farm_plots"] = []
        ov.orders = [{"id": 1, "recipe": "cook_meal", "repeat": "daily", "left": 5, "when": first["when"]}]
        ov.supply()                                        # winter now: the stale standing is re-cut
        cut = [a for t, a in game.calls if t == "cancel_order"]
        self.assertEqual(cut, [{"order_id": 1}])
        self.assertNotIn("o_cook", ov.done)

    # ---- (c) the seed protection
    def test_seeds_floor_joins_the_cook_whens(self):
        ov, game = self.overseer()
        ov.load(resp(100, farms=4))
        ov.supply()
        # cx: "seeds" is no add_order stock and a fourth clause is rejected (args.when has more than 3 items), so
        # the floor rides add_manager_order's SEEDS item condition, in place of plants_total
        tool, cook = next((t, a) for t, a in game.calls if a.get("job") == "PrepareMeal")
        self.assertEqual(tool, "add_manager_order")
        self.assertIn({"item_type": "SEEDS", "at_least": 4 * harness.SEEDS_PER_PLOT}, cook["when"])
        self.assertLessEqual(len(cook["when"]), 3)
        ov2, game2 = self.overseer()
        ov2.load(resp(100, farms=4, seed_kinds=SEEDS_WINTER))
        _, end = ov2.cook_order(ov2.cook_when(endgame=True))
        self.assertIn({"item_type": "SEEDS", "at_least": 4 * harness.SEEDS_PER_PLOT}, end["when"])
        self.assertLessEqual(len(end["when"]), 3)

    def test_no_farms_no_seeds_clause(self):
        ov, game = self.overseer()
        ov.load(resp(100, farms=0))
        ov.supply()
        cook = next(a for t, a in game.calls if a.get("recipe") == "cook_meal")
        self.assertNotIn("seeds", [w.get("stock") for w in cook["when"]])

    # ---- (b) the winter plan
    def test_winter_needs_scale_with_citizens_and_the_window(self):
        ov, _ = self.overseer()
        ov.load(resp(220, days_left=116, cit=20))          # OP1's checkpoint: 52 days to the F window
        drink, food = ov.winter_needs()
        self.assertEqual(drink, int(20 * 20 + 0.06 * 20 * 52))          # the 400 buffer + the road there
        self.assertEqual(food, int(10 * 20 + (8 / 336) * 20 * 52))
        ov2, _ = self.overseer()
        ov2.hands_off = 14                                 # a lab window: its own countdown rules the road
        ov2.cit = 20
        self.assertEqual(ov2.winter_needs()[0], int(20 * 20 + 0.06 * 20 * 14))   # the window leg included

    def test_winter_plan_full_opens_brewing_at_the_checkpoint(self):
        ov, game = self.overseer()
        ov.load(resp(220, days_left=116, cit=20, drink=100, food=100, seed_kinds=SEEDS_WINTER))
        ov.winter_plan()
        brews = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"]
        self.assertEqual(len(brews), 1)
        self.assertEqual(brews[0]["when"][0], {"stock": "drink", "below": ov.winter_needs()[0]})
        self.assertIn({"stock": "plants_brewable", "at_least": 2}, brews[0]["when"])
        cooks = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "cook_meal"]
        self.assertEqual(len(cooks), 1)
        self.assertEqual(cooks[0]["when"][0], {"stock": "prepared_meals", "below": max(300, ov.winter_needs()[1])})

    def test_winter_plan_uncapped_without_winter_seeds(self):
        ov, game = self.overseer(days=216)                 # MY1's checkpoint day 100 = days - 116
        ov.load(resp(100, days_left=116, cit=17, drink=100, seed_kinds=SEEDS_NO_WINTER))
        ov.winter_plan()                                   # MY1's checkpoint, no seed can grow through winter
        brews = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"]
        self.assertEqual(len(brews), 1)
        self.assertNotIn("drink", [w.get("stock") for w in brews[0]["when"]])   # the whole harvest converts

    def test_winter_plan_fires_once_a_year_and_skips_a_covered_pantry(self):
        ov, game = self.overseer()
        ov.load(resp(220, days_left=116, cit=20, drink=500, food=300, seed_kinds=SEEDS_WINTER))
        ov.winter_plan()
        self.assertEqual([a for t, a in game.calls if t == "add_order"], [])
        self.assertEqual(ov.winter_plan_year, 0)           # covered: the year is marked, nothing ordered
        ov.load(resp(224, days_left=112, cit=20, drink=100, food=100, seed_kinds=SEEDS_WINTER))
        ov.winter_plan()
        self.assertEqual([a for t, a in game.calls if t == "add_order"], [])   # once per winter, even when short

    def test_winter_plan_gates(self):
        ov, game = self.overseer()
        ov.load(resp(220, days_left=116, cit=20, drink=100, seed_kinds=SEEDS_WINTER))
        ov.days = 60                                       # a lab run never plans
        ov.winter_plan()
        self.assertEqual(game.calls, [])
        ov2, game2 = self.overseer()
        ov2.load(resp(300, days_left=36, cit=20, drink=100, seed_kinds=SEEDS_WINTER))
        ov2.winter_plan()                                  # already winter: the plan had its window
        self.assertEqual(game2.calls, [])

    # ---- (d) the F window's min-leg allocation
    def test_glut_bank_yields_to_the_falling_food_leg(self):
        ov, game = self.overseer()
        for i in range(6):   # cx: the min-leg yield holds only inside the final BREW_SPARE_DAYS
            ov.load(resp(300 + i, days_left=30, drink=140, food=90 - i, pb=6))   # drink flat, food draining
        ov.glut_jump = harness.GLUT_JUMP
        ov.glut_bank()
        self.assertEqual([a for t, a in game.calls if t == "add_order"], [])

    def test_glut_bank_food_min_leg_does_not_gate_outside_the_spare_days(self):
        ov, game = self.overseer()
        for i in range(6):
            ov.load(resp(200 + i, days_left=130, drink=140, food=90 - i, pb=20))   # food falling, far from F
        ov.glut_bank()
        self.assertEqual(len([a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"]), 1)

    def test_glut_bank_still_banks_when_drink_is_the_short_leg(self):
        ov, game = self.overseer()
        for i in range(6):
            ov.load(resp(300 + i, drink=140 - i, food=90, pb=6))     # drink draining, food flat
        ov.glut_jump = harness.GLUT_JUMP
        ov.glut_bank()
        added = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"
                 and "repeat" not in a]
        self.assertEqual(len(added), 1)

    def test_closer_brew_standing_retires_for_the_food_leg_near_the_horizon(self):
        ov, game = self.overseer()
        ov.load(resp(280, days_left=50, drink=120, food=90))          # armed the calendar way, food flat
        ov.closer()
        brew_id = ov.key_order.get("o_brew_end")
        self.assertIsNotNone(brew_id)
        game.calls.clear()
        standing = [{"id": brew_id, "recipe": "brew_drink", "repeat": "daily", "left": 5, "when": []}]
        for i in range(6):                                            # food now drains while drink holds
            ov.load(resp(320 + i, days_left=16 - i, drink=120, food=90 - i, orders=standing))
        ov.endgame_supply()
        tools = [t for t, _ in game.calls]
        self.assertIn("cancel_order", tools)
        self.assertEqual([a for t, a in game.calls if t == "cancel_order"], [{"order_id": brew_id}])
        self.assertNotIn("o_brew_end", ov.done)
        self.assertNotIn("o_brew_end", [a.get("recipe") for t, a in game.calls if t == "add_order"])

    def test_closer_brew_standing_stays_while_drink_is_the_short_leg(self):
        ov, game = self.overseer()
        for i in range(6):
            ov.load(resp(320 + i, days_left=16 - i, drink=120 - i, food=90))   # drink drains: it is the min leg
        ov.endgame_supply()
        brews = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"]
        self.assertEqual(len(brews), 1)
        self.assertEqual(brews[0]["amount"], 4)                       # the closer's standing, unchanged

    # ---- (e) the caravan exclusion
    def test_caravan_flag_tracks_the_announcement_stream(self):
        arrive = {"events": [{"type": "FIRST_CARAVAN_ARRIVAL", "tick": 50 * harness.DAY}], "dropped": 0}
        embark = {"events": [{"type": "MERCHANTS_EMBARKED", "tick": 60 * harness.DAY}], "dropped": 0}
        # one page per probe, in probe order (loads at 50, 51, 60, 62, 65): the embark exists only from day 60
        ov, game = self.overseer(pages=[arrive, {"events": [], "dropped": 0}, embark])
        ov.load(resp(50))
        self.assertTrue(ov.caravan_active)
        ov.load(resp(51))
        self.assertTrue(ov.caravan_active)                             # the stay holds
        ov.load(resp(60))
        self.assertEqual(len(game.probes), 3)
        self.assertTrue(ov.caravan_active)                             # the embark: a few haul-out days remain
        ov.load(resp(62))
        self.assertTrue(ov.caravan_active)
        ov.load(resp(65))
        self.assertFalse(ov.caravan_active)                            # the grace is over
        self.assertEqual(ov.caravan_probe_day, 65)                     # one events page per game day

    # cx: a handover fort's clock starts far from tick 0 (hint hard MY1-3: abs_tick 967200 at run day 0; the arrival
    # at tick 1027090 was read as "day 855" against run day 49 and the caravan never ended: on 0 -> never off)
    def test_caravan_clock_on_a_handover_fort(self):
        t0 = 967200
        arrive = {"events": [{"type": "FIRST_CARAVAN_ARRIVAL", "tick": t0 + 48 * harness.DAY + 690}], "dropped": 0}
        embark = {"events": [{"type": "MERCHANTS_EMBARKED", "tick": t0 + 81 * harness.DAY + 220}], "dropped": 0}
        ov, game = self.overseer(pages=[arrive, embark], days=216)

        def load(day):
            r = resp(day)
            r["tick"] = r["observation"]["date"]["abs_tick"] = t0 + day * harness.DAY
            ov.load(r)

        load(49)
        self.assertTrue(ov.caravan_active)
        self.assertEqual(ov.caravan_arrival_day, 48)
        load(82)
        self.assertEqual(ov.caravan_leave_day, 81)
        self.assertTrue(ov.caravan_active)                             # the haul-out grace
        load(85)
        self.assertTrue(ov.caravan_active)
        load(86)
        self.assertFalse(ov.caravan_active)                            # gone: the stock rules run again

    def test_caravan_flag_caps_on_the_thirty_day_rule(self):
        arrive = {"events": [{"type": "CARAVAN_ARRIVAL", "tick": 50 * harness.DAY}], "dropped": 0}
        ov, game = self.overseer(pages=[arrive])
        ov.load(resp(50))
        ov.load(resp(80))
        self.assertTrue(ov.caravan_active)
        ov.load(resp(81))
        self.assertFalse(ov.caravan_active)                            # no embark seen: the hard cap rules

    def test_caravan_holds_off_the_stock_rules(self):
        arrive = {"events": [{"type": "FIRST_CARAVAN_ARRIVAL", "tick": 50 * harness.DAY}], "dropped": 0}
        ov, game = self.overseer(pages=[arrive])
        for i in range(10):                                            # a draining board, caravan in
            ov.load(resp(50 + i, days_left=260 - i, drink=140 - i, food=90 - i, pb=6))
        self.assertTrue(ov.caravan_active)
        self.assertFalse(ov.stock_sliding())                           # the slide alarm ignores the jump
        self.assertFalse(ov.food_alarm())                              # ... and the departure dip
        ov.glut_jump = harness.GLUT_JUMP
        ov.glut_bank()
        self.assertEqual([a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"], [])
        ov.supply()                                                    # no new standing brew, no fruit one-shot
        self.assertEqual([a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"], [])
        ov.winter_plan()                                               # the plan waits for the merchants to leave
        self.assertEqual(ov.winter_plan_year, None)

    def test_caravan_settling_outlasts_the_visit(self):
        arrive = {"events": [{"type": "FIRST_CARAVAN_ARRIVAL", "tick": 50 * harness.DAY}],
                  "dropped": 0}
        embark = {"events": [{"type": "MERCHANTS_EMBARKED", "tick": 60 * harness.DAY}], "dropped": 0}
        ov, _ = self.overseer(pages=[arrive, embark])
        ov.load(resp(50))
        ov.load(resp(60))
        ov.load(resp(65))
        self.assertFalse(ov.caravan_active)
        self.assertTrue(ov.caravan_settling())                         # the slope records still carry the visit
        ov.day = 60 + harness.CARAVAN_SETTLE_DAYS
        self.assertFalse(ov.caravan_settling())

    # ---- (f) the brew-lock guard is gone
    def test_brew_lock_guard_removed(self):
        for name in ("brew_halt", "brew_watch"):
            self.assertFalse(hasattr(harness.Overseer, name), name)
        for name in ("BREW_HALT_DAYS", "BREW_HALT_DROP", "BREW_HALT_PB", "BREW_HALT_PERSIST", "BREW_ONESHOT_KEEP"):
            self.assertFalse(hasattr(harness, name), name)
        ov, game = self.overseer()
        ov.load(resp(100, farms=0))
        ov.plan()                                                      # runs clean, no alarm tools anywhere
        self.assertFalse([t for t, _ in game.calls if "brew_prune" in t or t == "alarm_brew_lock"])
        self.assertEqual(ov.plan(), None)

    def test_plan_runs_without_the_guard_state(self):
        ov, _ = self.overseer()
        ov.load(resp(45, farms=0))
        self.assertFalse(hasattr(ov, "brew_hist"))
        self.assertFalse(hasattr(ov, "brew_alarm"))
        self.assertTrue(hasattr(ov, "caravan_active"))
        self.assertTrue(hasattr(ov, "winter_plan_year"))


if __name__ == "__main__":
    unittest.main()


class SeasonFromCalendar(unittest.TestCase):
    def test_my1_run_reads_the_real_calendar(self):
        from overseer import harness as h
        ov = h.Overseer.__new__(h.Overseer)
        ov.o = {"date": {"day_of_year": 135}}
        ov.day = 0
        self.assertEqual(ov.season(), 1)           # MY1 day 0 = summer, not spring
        ov.o = {"date": {"day_of_year": 255}}
        ov.day = 120
        self.assertTrue(ov.winter())               # run day 120 = real winter
