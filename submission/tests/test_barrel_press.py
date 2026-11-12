"""cx regressions: the barrel press (hint std OP1-4 on 02a3eea, 2026-11-10). All 7 citizens carried every labor and
logs sat at 120-240, yet barrels came at 0.42/day: the 2 Carpenters held a MakeBarrel job nearly every look while one
dwarf took them and 3-4 dwarves sat on the 12/day wood crafts standing (4 Craftsdwarfs). barrels_empty 0-2 from day
42 to 79 with 10-35 brewable plants waiting, plants_rotten 0 -> 25. While plants wait on barrels the press throttles
the crafts standing to one a day, opens Carpenters up to PRESS_CARPENTERS and keeps a barrel job on every bench; on
release the chase's own standing comes back. No game or network."""
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

PLUMP = {"plump helmet": {"n": 9, "seasons": ["spring", "summer", "autumn", "winter"], "underground": True}}
SHOPS = ("Carpenters", "Carpenters", "Still", "Still", "Still", "Kitchen",
         "Craftsdwarfs", "Craftsdwarfs", "Craftsdwarfs", "Craftsdwarfs")
CRAFTS = {"id": 19, "job": "MakeCrafts", "repeat": "daily", "total": 12, "left": 4, "jobs_in_progress": 4,
          "material_category": ["wood"], "active": True,
          "when": [{"item_type": "WOOD", "test": "AtLeast", "value": 25, "flags": []}]}
BREW = {"id": 8, "recipe": "brew_drink", "job": "CustomReaction", "reaction": "BREW_DRINK_FROM_PLANT", "left": 30,
        "total": 30, "active": True}   # the record's one-shot brew backlog (15-26 jobs): the brews waiting on barrels


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, json.loads(json.dumps(args))))
        return {"ok": True, "result": {"order_id": 500 + len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {"units": []}}


def resp(day, pb=20, barrels=0, rot=0, logs=177, orders=(CRAFTS, BREW), shops=SHOPS, days=336, cit=7, wealth=3000,
         hands_off=None, sites=()):
    stocks = {"drink": 241, "food_edible": 95, "prepared_meals": 25, "plants_brewable": pb, "plants_total": pb,
              "plants_rotten": rot, "barrels_empty": barrels, "logs_usable": logs, "seeds": 40, "seeds_by_kind": PLUMP,
              "beds": 13, "tables": 9, "chairs": 8, "furniture_free": {}}
    obs = {"date": {"abs_tick": day * harness.DAY, "day_of_year": (15 + day) % harness.YEAR_DAYS},
           "administrators": {"citizens": cit, "manager_active_for_orders": True}, "stocks": stocks,
           "map": {"sites": list(sites)}, "zones": [], "furniture": [], "wealth": {"created": wealth},
           "workshops": [{"id": i, "type": w, "built": True} for i, w in enumerate(shops)], "orders": list(orders),
           "farm_plots": [{"id": i, "z": 159, "seeds_or_crops_in_plot": n} for i, n in enumerate((2, 2, 1, 0, 2))]}
    r = {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": days - day}
    if hands_off is not None:
        r["hands_off_in_days"] = hands_off
    return r


W5 = {"id": "W5", "kind": "W", "x": 80, "y": 90, "z": 160, "w": 3, "h": 3}


class BarrelPress(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, days=336):
        game = FakeGame()
        return harness.Overseer(game, days=days), game

    @staticmethod
    def load(ov, r):
        ov.load(r)
        ov.count = 0

    @staticmethod
    def calls(game, tool, **match):
        return [a for t, a in game.calls if t == tool and all(a.get(k) == v for k, v in match.items())]

    # ---- the gate
    def test_plants_waiting_on_barrels_start_the_press_with_hysteresis(self):
        ov, game = self.ov()
        self.load(ov, resp(42, pb=10, barrels=0))
        self.assertTrue(ov.barrel_press())           # 10 - 2 - 0 = 8 waiting
        self.load(ov, resp(43, pb=4, barrels=1))
        self.assertTrue(ov.barrel_press())           # 1 waiting: still on (off at PRESS_OFF)
        self.load(ov, resp(44, pb=5, barrels=7))
        self.assertFalse(ov.barrel_press())          # none waiting: released
        self.load(ov, resp(45, pb=5, barrels=2))
        self.assertFalse(ov.barrel_press())          # 3 waiting: under PRESS_ON, stays off
        self.load(ov, resp(46, pb=20, barrels=5))
        self.assertFalse(ov.barrel_press())          # 15 waiting beside 5 empty barrels: the Still is not barrel-bound
        self.load(ov, resp(47, pb=20, barrels=4))
        self.assertTrue(ov.barrel_press())
        self.load(ov, resp(48, pb=30, barrels=10))
        self.assertFalse(ov.barrel_press())          # PRESS_BARRELS_FREE empty barrels release it

    def test_plants_no_brew_wants_do_not_press(self):
        # hint std OP1-1 on 68bd4c7 shape without rot: plants standing under a capped standing, no one-shot brew
        capped = {"id": 47, "recipe": "brew_drink", "repeat": "daily", "left": 1, "total": 1, "active": False,
                  "when": [{"item_type": "DRINK", "test": "LessThan", "value": 300}]}
        ov, game = self.ov()
        self.load(ov, resp(169, pb=40, barrels=0, orders=(CRAFTS, capped)))
        self.assertEqual(ov.brew_planned(), 0)
        self.assertFalse(ov.barrel_press())

    def test_no_press_on_the_embark_stock(self):
        ov, game = self.ov()
        self.load(ov, resp(0, pb=30, barrels=0, logs=0))
        self.assertFalse(ov.barrel_press())
        self.load(ov, resp(19, pb=12, barrels=0))
        self.assertFalse(ov.barrel_press())
        self.load(ov, resp(20, pb=12, barrels=0))
        self.assertTrue(ov.barrel_press())

    def test_no_press_on_labs_or_short_runs_without_rot(self):
        ov, game = self.ov()
        self.load(ov, resp(42, pb=30, hands_off=20))
        self.assertFalse(ov.barrel_press())
        ov, game = self.ov(days=100)
        self.load(ov, resp(42, pb=30, days=100))
        self.assertFalse(ov.barrel_press())
        ov, game = self.ov(days=216)                 # MY1: only once this fort's plants rot
        self.load(ov, resp(42, pb=30, days=216, rot=0))
        self.assertFalse(ov.barrel_press())
        self.load(ov, resp(43, pb=30, days=216, rot=3))
        self.assertTrue(ov.rot_seen)
        self.assertTrue(ov.barrel_press())

    # ---- the crafts throttle
    def test_the_chase_standing_is_throttled_then_restored(self):
        ov, game = self.ov()
        self.load(ov, resp(49, pb=20, barrels=0))
        ov.progress()
        self.assertEqual(self.calls(game, "cancel_order"), [{"order_id": 19}])
        self.assertEqual(self.calls(game, "add_manager_order"), [])   # the cancel must show first
        self.assertEqual(self.calls(game, "build_workshop"), [])       # no bench while pressed
        # the next load: the heavy standing is gone, the press adds its one-a-day standing
        self.load(ov, resp(50, pb=22, barrels=0, orders=(BREW,)))
        ov.progress()
        add = self.calls(game, "add_manager_order")
        self.assertEqual(len(add), 1)
        self.assertEqual((add[0]["job"], add[0]["amount"], add[0]["repeat"], add[0]["material_category"]),
                         ("MakeCrafts", harness.PRESS_CRAFT_AMOUNT, "daily", ["wood"]))
        mine = ov.key_order["o_crafts_press"]
        light = dict(CRAFTS, id=mine, total=1, left=1)
        self.load(ov, resp(51, pb=24, barrels=1, orders=(light, BREW)))
        ov.progress()
        self.assertEqual(len(self.calls(game, "add_manager_order")), 1)
        self.assertEqual(len(self.calls(game, "cancel_order")), 1)    # the light standing stays
        # released: the press standing goes, then the chase's own standing comes back at its amount
        self.load(ov, resp(84, pb=5, barrels=7, orders=(light, BREW)))
        self.assertFalse(ov.barrel_press())
        ov.progress()
        self.assertEqual(self.calls(game, "cancel_order")[-1], {"order_id": mine})
        self.load(ov, resp(85, pb=5, barrels=8, orders=(BREW,)))
        ov.progress()
        back = [a for a in self.calls(game, "add_manager_order") if a.get("amount") != harness.PRESS_CRAFT_AMOUNT]
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0]["amount"], harness.CRAFT_AMOUNT_WAVE)
        self.assertIn("o_crafts_prog", ov.done)

    def test_the_model_s_or_bone_standings_and_an_unpressed_fort_are_left_alone(self):
        ov, game = self.ov()
        self.load(ov, resp(49, pb=4, barrels=3))                      # no plants waiting
        ov.progress()
        self.assertEqual(self.calls(game, "cancel_order"), [])
        bone = dict(CRAFTS, id=33, material_category=["bone"], total=4)
        ov, game = self.ov()
        self.load(ov, resp(49, pb=20, barrels=0, orders=(bone, BREW)))
        ov.progress()
        self.assertEqual(self.calls(game, "cancel_order"), [])        # bone crafts don't take the wood or benches

    def test_no_bone_fallback_while_or_just_after_the_press(self):
        ov, game = self.ov()
        for day in range(49, 60):                                     # flat wealth under the press
            self.load(ov, resp(day, pb=20, barrels=0, wealth=3000))
            ov.progress()
        bone = [a for a in self.calls(game, "add_manager_order") if a.get("material_category") == ["bone"]]
        self.assertEqual(bone, [])
        self.load(ov, resp(60, pb=4, barrels=6, wealth=3000, orders=(BREW,)))
        self.assertFalse(ov.barrel_press())
        ov.progress()
        bone = [a for a in self.calls(game, "add_manager_order") if a.get("material_category") == ["bone"]]
        self.assertEqual(bone, [])

    # ---- benches and barrel jobs
    def test_press_opens_carpenters_up_to_the_cap(self):
        ov, game = self.ov()
        self.load(ov, resp(49, pb=20, barrels=0, sites=(W5,)))
        ov.workshops()
        self.assertEqual(self.calls(game, "build_workshop"), [{"type": "Carpenters", "site": "W5"}])
        ov, game = self.ov()
        shops = SHOPS + ("Carpenters", "Carpenters")
        self.load(ov, resp(49, pb=20, barrels=0, sites=(W5,), shops=shops))
        ov.workshops()
        self.assertEqual(self.calls(game, "build_workshop", type="Carpenters"), [])
        ov, game = self.ov()
        self.load(ov, resp(49, pb=4, barrels=3, sites=(W5,)))         # not pressed: two benches stay
        ov.workshops()
        self.assertEqual(self.calls(game, "build_workshop", type="Carpenters"), [])

    def test_press_keeps_a_barrel_job_on_every_bench(self):
        # the record's d49 book: one-shot barrel orders with 2 + 3 + 5 left on 2 Carpenters
        book = (CRAFTS, BREW, {"id": 1, "recipe": "make_barrel", "left": 2}, {"id": 4, "recipe": "make_barrel", "left": 3},
                {"id": 16, "recipe": "make_barrel", "left": 5})
        ov, game = self.ov()
        self.load(ov, resp(49, pb=20, barrels=0, orders=book))
        ov.supply()
        self.assertEqual(self.calls(game, "add_order", recipe="make_barrel", amount=None), [])
        one = [a for a in self.calls(game, "add_order", recipe="make_barrel") if not a.get("repeat")]
        self.assertEqual(one, [])                                     # 10 left >= 2 per bench: enough work queued
        ov, game = self.ov()
        self.load(ov, resp(49, pb=20, barrels=0, orders=(CRAFTS, BREW, {"id": 4, "recipe": "make_barrel", "left": 1})))
        ov.supply()
        one = [a for a in self.calls(game, "add_order", recipe="make_barrel") if not a.get("repeat")]
        self.assertEqual(len(one), 1)
        self.assertGreaterEqual(one[0]["amount"], 2 * 2 - 1)
        self.assertLessEqual(one[0]["amount"], harness.PRESS_BARREL_BATCH)

    def test_press_barrels_keep_the_logs_guard(self):
        ov, game = self.ov()
        self.load(ov, resp(49, pb=20, barrels=0, logs=30, orders=(CRAFTS, BREW)))
        ov.supply()
        one = [a for a in self.calls(game, "add_order", recipe="make_barrel") if not a.get("repeat")]
        self.assertEqual(one, [])


class CraftRecut(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def test_a_chase_recut_re_adds_its_standing(self):
        # the chase's own re-cut cancels the standing and re-adds it on a later load under the once-per-game key
        # o_crafts_prog: that key must be free again after the cancel (it stayed in done before)
        game = FakeGame()
        ov = harness.Overseer(game, days=336)
        ov.load(resp(60, pb=0, barrels=10, orders=()))
        ov.count = 0
        ov.progress()
        self.assertIn("o_crafts_prog", ov.done)
        sid = ov.key_order["o_crafts_prog"]
        ov.craft_desired, ov.craft_amount_day = harness.CRAFT_AMOUNT_BASE, None
        ov.load(resp(61, pb=0, barrels=10, orders=(dict(CRAFTS, id=sid, total=harness.CRAFT_AMOUNT_BASE),)))
        ov.count = 0
        ov.progress()
        self.assertEqual([a for t, a in game.calls if t == "cancel_order"], [{"order_id": sid}])
        self.assertNotIn("o_crafts_prog", ov.done)
        ov.load(resp(64, pb=0, barrels=10, orders=()))   # o_crafts_prog paces at retry=4 days
        ov.count = 0
        ov.progress()
        adds = [a for t, a in game.calls if t == "add_manager_order" and a.get("job") == "MakeCrafts"]
        self.assertEqual(len(adds), 2)


if __name__ == "__main__":
    unittest.main()
