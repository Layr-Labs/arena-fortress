"""cx MY1 supply plan (m3r): every hint MY1-3 record (std and hard, 11-18 citizens) scored on the supply leg — 16-18
citizen runs 66-81, 11-14 citizen runs 91-100. The score reads each leg's least-squares slope over A + F against
stock_H / 336. Drink: the fewest held plants brewed at mid-F that put the projected slope over that line, the rest
brewed before F while drink is under the run's remaining use (7c43df4 std: the 1.5x hold vetoed the model's brews
while drink fell 83 -> 32, then o_brew_f brewed 8 plants one a day inside F, food -8). Food: the hand-over's pets are
F's meat (7c43df4 std d106-120 slaughtered both dogs and a cat on a passing food alarm: food -0.77/day over F).
A day-step simulator drives the layer's own orders over the MY1 calendar for 11-18 citizens. No game or network."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness  # noqa: E402
import test_harvest_hold as hh  # noqa: E402

SEEDS = {"cave wheat": {"n": 0, "seasons": ["summer", "autumn"], "underground": True},
         "pig tail": {"n": 0, "seasons": ["summer", "autumn"], "underground": True},
         "sweet pod": {"n": 2, "seasons": ["spring", "summer"], "underground": True}}
MEAT = {"DOG": 18, "CAT": 6, "BIRD_PEAFOWL_BLUE": 4}
PETS = ("DOG", "DOG", "CAT", "CAT", "BIRD_PEAFOWL_BLUE")
STOCK = {"drink": "DRINK", "plants_brewable": "PLANT", "barrels_empty": "BARREL"}


class SimFort:
    """Drink, food and brewable plants a day at a time under the layer's orders: a repeat brew order queues its
    amount when idle and its condition holds, the Still does up to 3 brews a day (a plant is a food unit and 5
    drinks), the citizens drink `dr` and eat `fr` a day each, a slaughter is meat 2 days on."""

    def __init__(self, cit, drink, food, pb, start, dr=0.06, fr=0.035, animals=PETS):
        self.cit, self.drink, self.food, self.pb, self.day = cit, float(drink), float(food), pb, start
        self.dr, self.fr = dr, fr
        self.orders, self.next_id, self.calls, self.meat_due, self.hist = [], 100, [], [], {}
        self.animals = [{"id": 900 + i, "race": r, "tame": True} for i, r in enumerate(animals)]

    def act(self, tool, args):
        self.calls.append((self.day, tool, dict(args)))
        if tool == "add_order":
            self.next_id += 1
            self.orders.append({"id": self.next_id, "recipe": args["recipe"], "repeat": args.get("repeat"),
                                "left": 0 if args.get("repeat") else args.get("amount", 1),
                                "total": args.get("amount", 1), "_when": args.get("when") or []})
            return {"ok": True, "result": {"order_id": self.next_id}}
        if tool == "cancel_order":
            self.orders = [o for o in self.orders if o["id"] != args["order_id"]]
        if tool == "slaughter":
            a = next((a for a in self.animals if a["id"] == args["unit_id"]), None)
            if a:
                self.animals.remove(a)
                self.meat_due.append((self.day + 2, MEAT.get(a["race"], 5)))
        return {"ok": True, "result": {}}

    def query(self, name, **kw):
        return {"result": {"units": [dict(a) for a in self.animals] if name == "units" else []}}

    def holds(self, when):
        st = {"drink": self.drink, "plants_brewable": self.pb, "barrels_empty": 20}
        for c in when:
            v = st.get(c["stock"], 0)
            if ("below" in c and not v < c["below"]) or ("at_least" in c and not v >= c["at_least"]):
                return False
        return True

    def tick(self):
        for o in self.orders:
            if o["repeat"] and o["left"] <= 0 and o["recipe"] == "brew_drink" and self.holds(o["_when"]):
                o["left"] = o["total"]
        done = 0
        for o in self.orders:
            while o["recipe"] == "brew_drink" and o["left"] > 0 and self.pb > 0 and done < 3:
                o["left"] -= 1
                self.pb -= 1
                self.drink += 5
                done += 1
        self.orders = [o for o in self.orders if o["repeat"] or o["left"] > 0]
        self.drink = max(0.0, self.drink - self.dr * self.cit)
        self.food = max(0.0, self.food - self.fr * self.cit)
        for due, m in list(self.meat_due):
            if due <= self.day:
                self.food += m
                self.meat_due.remove((due, m))
        self.day += 1

    def obs(self):
        # as observe.lua reads DF: an idle repeat order shows left = total and active false
        orders = [{"id": o["id"], "recipe": o["recipe"], "total": o["total"], "repeat": o["repeat"],
                   "left": o["left"] if (o["left"] > 0 or not o["repeat"]) else o["total"],
                   "active": o["left"] > 0, "jobs_in_progress": 0,
                   "when": [dict(c, item_type=STOCK[c["stock"]], test="LessThan" if "below" in c else "AtLeast",
                                 value=c.get("below", c.get("at_least")),
                                 **({"reaction_product": "DRINK_MAT"} if c["stock"] == "plants_brewable" else {}))
                            for c in o["_when"]]} for o in self.orders]
        stocks = {"drink": int(self.drink), "food_edible": int(self.food + self.pb), "prepared_meals": int(self.food),
                  "plants_brewable": self.pb, "plants_total": self.pb, "barrels_empty": 20, "logs_usable": 60,
                  "seeds": 2, "seeds_by_kind": SEEDS, "furniture_free": {},
                  "plants_by_kind": {"cave wheat": {"n": self.pb, "brewable": True, "cookable": False}}}
        o = {"date": {"abs_tick": self.day * harness.DAY, "day_of_year": (135 + self.day) % harness.YEAR_DAYS},
             "administrators": {"citizens": self.cit}, "stocks": stocks, "map": {"sites": []}, "zones": [],
             "furniture": [], "orders": orders, "farm_plots": [{"id": i, "z": 143} for i in range(4)],
             "workshops": [{"type": w, "built": True} for w in ("Carpenters", "Still", "Kitchen", "Butchers")],
             "burrows": {"civilian_alert": False}}
        return {"tick": self.day * harness.DAY, "day": self.day, "observation": o, "days_left": 216 - self.day}


def simulate(cit, pb, drink=84, food=150, cadence=3, start=115, **kw):
    """The layer's hold, plan and F livestock steps on SimFort from the end of the autumn harvest (the hold armed on
    two closed loads), o_brew kept as supply() keeps it; returns {leg: (stock_A, stock_H, slope, score)}."""
    fort = SimFort(cit, drink, food, pb, start, **kw)
    ov = harness.Overseer(fort, days=216)
    ov.mig_start, ov.mig_waves = 9, 1   # the wave came (the forecast is the census)
    with redirect_stdout(io.StringIO()):
        for day in (start - 4, start):
            fort.day = day
            ov.load(fort.obs())
            ov.count = 0
            ov.hold_active()
        while fort.day <= 216:
            if (fort.day - start) % cadence == 0:
                ov.load(fort.obs())
                ov.count = 0
                if ov.hold_active():
                    oid = ov.key_order.get("o_brew")
                    o = next((o for o in fort.orders if o["id"] == oid), None)
                    if o is None:
                        r = fort.act("add_order", {"recipe": "brew_drink", "amount": ov.brew_amount(),
                                                   "repeat": "daily", "when": ov.brew_when()})
                        ov.key_order["o_brew"] = r["result"]["order_id"]
                        ov.owned.add(r["result"]["order_id"])
                    else:
                        o["_when"], o["total"] = ov.brew_when(), ov.brew_amount()
                ov.hold_supply()
                ov.f_livestock()
            fort.hist[fort.day] = (fort.drink, fort.food + fort.pb)
            fort.tick()
    out = {}
    for i, leg in enumerate(("drink", "food")):
        pts = [(x, fort.hist[x][i]) for x in range(188, 217)]
        slope, vh = harness.ols_slope(pts), pts[-1][1]
        cover = sum(1 for x in range(189, 217) if fort.hist[x][i] > 0) / 28.0
        T = float("inf") if slope >= 0 else vh / -slope
        out[leg] = (round(pts[0][1]), round(vh), round(slope, 2), round(0.5 * cover + 0.5 * min(1.0, T / 336), 3))
    return out


class Arithmetic(hh.Base):
    def test_projection_is_the_score_s_least_squares(self):
        ov, _ = self.ov()
        days = list(range(174, 201))
        for day in days:   # drink 60 falling 1 a day, a 20-drink step on d195
            ov.load(hh.resp(day, cit=17, drink=60 - (day - 174) + (20 if day >= 195 else 0)))
        rate = 1.0
        slope, vh, low = ov.f_project(1, rate)
        want = [(x, 60 - (x - 174) + (20 if x >= 195 else 0)) for x in range(188, 217)]
        self.assertAlmostEqual(slope, harness.ols_slope(want), places=6)
        self.assertEqual(vh, want[-1][1])
        # an add lands on its day
        s2, vh2, _ = ov.f_project(1, rate, adds=[(205, 10)])
        self.assertEqual(vh2, vh + 10)
        self.assertGreater(s2, slope)

    def test_mid_f_need_by_census(self):
        ov, _ = self.ov()
        self.assertEqual([ov.f_mid_need(0.06 * c) for c in (9, 11, 14, 17, 18, 22)], [3, 4, 4, 5, 5, 6])

    def test_op1_keeps_its_hold_reserve(self):
        ov, _ = self.ov(days=336)
        ov.load(hh.resp(250, days=336, cit=16))
        self.assertFalse(ov.my1_plan())
        need = harness.HOLD_COVER * ov.use_rate("drink", harness.DRINK_PER_CIT_DAY) * 16 * ov.f_len() / 5
        self.assertEqual(ov.hold_reserve(), max(harness.HOLD_MIN, 2 + int(-(-need // 1))))


class Simulated(unittest.TestCase):
    """The plan on the MY1 calendar: harvest ended d115 with drink 84 (7c43df4 std) or 115, one load every 3 or 7
    days (the model's 7-14 day advances, the layer's own 2-4 day chunks)."""

    def test_both_legs_full_for_11_to_18_citizens(self):
        for cit in (11, 13, 14, 16, 17, 18):
            for pb in (8, 11):
                for drink in (84, 115):
                    for cadence in (3, 7):
                        out = simulate(cit, pb, drink=drink, cadence=cadence)
                        for leg in ("drink", "food"):
                            self.assertGreaterEqual(out[leg][3], 0.99, (cit, pb, drink, cadence, leg, out))

    def test_the_old_one_a_day_release_lost_the_food_leg_this_one_keeps_it(self):
        # 7c43df4 std's shape: 17 citizens, 11 held, only a cat and a peafowl left for F
        out = simulate(17, 11, animals=("CAT", "BIRD_PEAFOWL_BLUE"), fr=0.025)
        self.assertGreaterEqual(out["drink"][3], 0.99)
        self.assertLess(out["food"][2], 0)   # meat for two small animals cannot hold the leg ...
        full = simulate(17, 11, fr=0.025)
        self.assertGreaterEqual(full["food"][3], 0.99)   # ... the hand-over's pets carried into F do

    def test_a_large_hold_leaves_food_unbrewed(self):
        fort_pb = 11
        out = simulate(11, fort_pb)
        self.assertGreaterEqual(out["drink"][3], 0.99)
        self.assertGreater(out["food"][1], 150 - 11 * 0.035 * 101 - 1)   # most plants stayed food


class FReserve(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def run_butcher(self, day, food, cit=17, days=216, animals=None):
        fort = SimFort(cit, 80, food, 0, day, animals=animals or ("DOG", "CAT", "GOAT"))
        ov = harness.Overseer(fort, days=days)
        r = fort.obs()
        r["days_left"] = days - day
        ov.load(r)
        ov.count = 0
        ov.butcher()
        return [a["unit_id"] for _, t, a in fort.calls if t == "slaughter"], fort

    def test_before_f_the_pets_wait_and_a_grazer_goes(self):
        killed, fort = self.run_butcher(106, food=123)
        self.assertEqual(killed, [902])   # the goat, not the dog (900) or the cat (901)

    def test_no_grazer_no_slaughter(self):
        killed, _ = self.run_butcher(106, food=123, animals=("DOG", "CAT"))
        self.assertEqual(killed, [])

    def test_short_food_takes_a_pet(self):
        killed, _ = self.run_butcher(106, food=40, animals=("DOG", "CAT"))   # 40 < 6 x 17, no drain record
        self.assertEqual(killed, [])   # no drain measured: cover unknown -> kept
        fort = SimFort(17, 80, 40, 0, 100, animals=("DOG", "CAT"))
        ov = harness.Overseer(fort, days=216)
        with redirect_stdout(io.StringIO()):
            for day, food in ((90, 80), (95, 60), (100, 40)):   # 4/day: 10 days left of 88 to F
                fort.day, fort.food = day, food
                ov.load(fort.obs())
            ov.count = 0
            ov.butcher()
        self.assertEqual([a["unit_id"] for _, t, a in fort.calls if t == "slaughter"], [900])

    def test_inside_f_and_off_my1_unchanged(self):
        killed, _ = self.run_butcher(195, food=123, animals=("DOG", "CAT"))
        self.assertEqual(killed, [900])
        killed, _ = self.run_butcher(106, food=123, days=336, animals=("DOG", "CAT"))
        self.assertEqual(killed, [900])


class HoldShape(hh.Base):
    def test_a_high_gross_use_rate_does_not_drop_the_hold(self):
        # 7c43df4 std d91-105: use_rate read 0.13 a citizen-day; drink 108 is under half of 0.13 x 17 x 97
        ov, _ = self.armed(cit=17)
        ov.measured_rate = lambda leg: 0.13
        self.assertTrue(self.step(ov, 91, cit=17, drink=108, pb=3))
        self.assertTrue(ov.hold_active())

    def test_surplus_brews_before_f_while_drink_is_under_the_run_s_use(self):
        ov, game = self.armed(cit=17)
        ov.mig_waves = 1   # the wave came: the forecast is the census
        self.step(ov, 120, cit=17, drink=83, pb=11)
        r = ov.hold_reserve()
        self.assertEqual(r, 6)
        when = ov.brew_when()
        self.assertEqual(when[0], {"stock": "drink", "below": 98})        # 1.02 x 96 days left
        self.assertEqual(when[1], {"stock": "plants_brewable", "at_least": 7})
        self.assertEqual(ov.brew_amount(), 1)

    def test_a_floorless_model_standing_is_cancelled_a_reserve_floor_kept(self):
        ov, game = self.armed(cit=17)
        r = ov.hold_reserve()

        def standing(oid, floor, amount=2):
            return {"id": oid, "recipe": "brew_drink", "repeat": "daily", "total": amount, "left": amount,
                    "when": [{"stock": "plants_brewable", "item_type": "PLANT", "reaction_product": "DRINK_MAT",
                              "test": "AtLeast", "value": floor}]}
        self.step(ov, 130, cit=17, drink=70, pb=11, orders=[standing(61, 1), standing(62, r + 2)])
        ov.hold_supply()
        self.assertEqual([a for t, a in game.calls if t == "cancel_order"], [{"order_id": 61}])

    def test_a_standing_no_longer_needed_is_cancelled(self):
        ov, game = self.armed(cit=17)
        ov.mig_waves = 1
        self.step(ov, 180, cit=17, drink=60, pb=8)
        ov.hold_supply()
        oid = ov.key_order.get("o_brew_mid")
        self.assertIsNotNone(oid)
        mid = {"id": oid, "recipe": "brew_drink", "repeat": "daily", "total": 5, "left": 0, "jobs_in_progress": 0,
               "when": [{"stock": "drink", "item_type": "DRINK", "test": "LessThan", "value": 38}]}
        # drink 500 lasts past T_STAR (plus the margin) at 1.02/day: no brew (160 would not: T 120 days)
        self.step(ov, 184, cit=17, drink=500, pb=8, orders=[mid])
        self.assertEqual(ov.f_brew_need()[0], 0)
        ov.food_lean = lambda: False   # (drink 500 against food 132 arms the food-lean keeper, which skips the plan)
        ov.hold_supply()
        self.assertIn(("cancel_order", {"order_id": oid}), game.calls)


if __name__ == "__main__":
    unittest.main()
