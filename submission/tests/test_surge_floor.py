"""cx surge fixes (LT08 shape only), from the dw6 LT08 records (runs/dw6-lt08-hard LT08-0/1/2):
- beds: every fort had one dug level with its farm plots on it; the farm loop gave every soil R room the farm role
  before the surge dorm dig could see a spare one, and furnish's dormitory search excluded the farm level — the
  layer placed no bed (LT08-1) or knocked on a farm plot's R room for 30 days (LT08-0, site_used);
- stuck digs: pending 9-11 from day 4 to day 38 (Dangerous terrain) with no other R room listed;
- drink: the model's plant-floorless cook standing ate the plump helmets before the window, so drink[60] < drink[39].
Each measure must leave the windowless (MY1/OP1) and non-migrant lab shapes exactly as before."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

GOAL_LT08 = "Migrants are arriving. From day 39 you can't act for 21 days."
GOAL_OPEN = "Run the fortress for 60 days."



def bridge(a):
    """cx lt08drink: the window bridge (o_brew_bridge_win, the one brew standing with a drink cap; tested in
    test_window_bridge.py) is left out where a test counts the eve's window brew."""
    return "drink" in [w.get("stock") for w in a.get("when") or []]

class FakeGame:
    def __init__(self):
        self.calls = []
        self.full = set()       # place_furniture answers no_space here
        self.used = set()       # place_furniture answers site_used here
        self.room = {}          # site id -> beds it still takes (default: all requested)

    def act(self, tool, args):
        args = dict(args)
        self.calls.append((tool, args))
        if tool == "place_furniture":
            sid = args.get("site")
            if sid in self.used:
                return {"ok": False, "error_code": "site_used", "error": "room %s is already used (farm plot 25)" % sid}
            k = min(args.get("count", 1), self.room.get(sid, 99))
            if sid in self.full or k <= 0:
                return {"ok": False, "error_code": "no_space", "error": "no free floor tile"}
            self.room[sid] = self.room.get(sid, 99) - k
            return {"ok": True, "result": {"n": k, "at": [[i, 1, 9] for i in range(k)]}}
        return {"ok": True, "result": {"order_id": 100 + len(self.calls)}}

    def query(self, *a, **kw):
        return {"result": {}}


def obs(cit=46, hands_off=20, sites=(), stocks=None, orders=(), pending=0, day=20):
    st = {"plants_brewable": 6, "plants_total": 6, "food_edible": 116, "drink": 502, "beds": 60,
          "barrels_empty": 12, "logs_usable": 170, "furniture_free": {"bed": 22}}
    st.update(stocks or {})
    return {"tick": 0, "day": day, "hands_off_in_days": hands_off, "observation": {
        "administrators": {"citizens": cit, "manager_active_for_orders": True, "MANAGER_id": 1},
        "stocks": st, "map": {"sites": list(sites), "surface_z": 149}, "zones": [], "furniture": [],
        "workshops": [], "orders": list(orders), "farm_plots": [], "dig_designations_pending": pending,
        "plugins": {"autochop": "on", "seedwatch": "on", "autofarm": "on"}, "date": {"abs_tick": 0}}}


def A(id="A4", z=148, w=20, h=6, open_tiles=36, **kw):
    return {"id": id, "kind": "A", "x": 93, "y": 93, "z": z, "w": w, "h": h, "open_tiles": open_tiles, **kw}


def R(id, z=148, soil=True, dug=False, designated=False, **kw):
    return {"id": id, "kind": "R", "x": 90, "y": 95, "z": z, "w": 3, "h": 3, "soil": soil, "dug": dug,
            "designated": designated, "free": True, **kw}


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def ov(self, surge=True, hands_off=20, **kw):
        game = FakeGame()
        o = harness.Overseer(game, goal=GOAL_LT08 if surge else GOAL_OPEN, days=60)
        o.load(obs(hands_off=hands_off if surge else None, **kw))
        o.count = 0
        return o, game

    @staticmethod
    def beds(game):
        return [(a["site"], a["count"]) for t, a in game.calls if t == "place_furniture" and a.get("kind") == "bed"]


class SurgeBeds(Base):
    def test_single_farm_level_still_takes_the_waves_beds(self):
        """dw6 LT08-1's shape: one level z148 (A4 20x6), R1-R3 farm-role, no dorm role at all."""
        o, game = self.ov(sites=[A(), R("R1", dug=True), R("R2", designated=True), R("R3", designated=True)])
        o.roles = {"R1": "farm", "R2": "farm", "R3": "farm"}
        self.assertIsNone(o.room_for("dorm", harness.ZONE_MAX))   # the leader's search finds nothing here
        o.furnish()
        self.assertEqual(self.beds(game), [("A4", 22)])

    def test_open_play_spreads_beds_without_a_dormitory(self):
        """cx housing boxes: open play with no dormitory (every R room a farm: live std OP1-1 on 80e9f9d, day 43, 10
        beds free and 0 placed) puts the free beds on the level's A box like the surge does."""
        o, game = self.ov(surge=False, sites=[A(), R("R1", dug=True)])
        o.roles = {"R1": "farm"}
        o.furnish()
        self.assertEqual(self.beds(game), [("A4", 22)])

    def test_wide_a_site_takes_beds_without_a_zone(self):
        """dw6 LT08-0/2: the level's A box grew to 23 wide — past make_zone's 20, inside place_furniture's 40."""
        o, game = self.ov(sites=[A("A3", z=169, w=23, h=13, open_tiles=167), R("R2", z=169, soil=False, dug=True)])
        o.roles = {"R2": "dorm"}
        game.used.add("R2")   # the measured site_used: a farm plot covers the dorm room
        o.furnish()
        self.assertEqual(self.beds(game), [("R2", 22), ("A3", 22)])
        self.assertNotIn("R2", o.roles)                           # the lost dorm room loses its role
        self.assertEqual([a for t, a in game.calls if t == "make_zone"], [])   # 23 wide: no zone attempt

    def test_a_refused_site_is_skipped_until_its_floor_grows(self):
        o, game = self.ov(sites=[A(open_tiles=36), A("A5", z=147, open_tiles=20)])
        game.full.add("A4")
        o.furnish()
        self.assertEqual(self.beds(game), [("A4", 22), ("A5", 22)])
        o.now += harness.DAY
        o.day += 1
        o.furnish()
        self.assertEqual(self.beds(game)[2:], [("A5", 22)])   # A4 stays skipped (same floor), A5 knocked again
        o.now += harness.DAY
        o.day += 1
        for s in o.sites:
            if s["id"] == "A4":
                s["open_tiles"] = 60                       # the level was dug out further
        game.full.discard("A4")
        o.furnish()
        self.assertEqual(self.beds(game)[-1][0], "A4")

    def test_tables_wait_while_beds_are_short(self):
        o, game = self.ov(sites=[A()], stocks={"furniture_free": {"bed": 0, "table": 10, "chair": 10}})
        o.furnish()
        self.assertEqual([a for t, a in game.calls if t == "place_furniture" and a["kind"] != "bed"], [])
        o2, game2 = self.ov(surge=False, sites=[A()], stocks={"furniture_free": {"bed": 0, "table": 10, "chair": 10}})
        o2.furnish()
        self.assertTrue([a for t, a in game2.calls if t == "place_furniture" and a["kind"] == "table"])


class SurgeDig(Base):
    def test_dorm_capacity_is_designated_before_the_farms_take_the_soil_rooms(self):
        o, game = self.ov(sites=[R("R1"), R("R2"), R("R3")])
        o.digging()
        digs = [(a["site"], a.get("w"), a.get("h")) for t, a in game.calls if t == "dig_room"]
        self.assertEqual(digs[0], ("R1", 9, 7))
        self.assertEqual(o.roles["R1"], "dorm")

    def test_windowless_keeps_the_farm_first_order(self):
        o, game = self.ov(surge=False, sites=[R("R1"), R("R2"), R("R3")])
        o.digging()
        self.assertNotIn("dorm", [o.roles.get(r) for r in ("R1",)])
        self.assertFalse([a for t, a in game.calls if t == "dig_room" and a.get("w") == 9 and a["site"] == "R1"])

    def stuck(self, surge=True):
        sites = [R("R1", dug=True), R("R2", designated=True), R("R3", designated=True),
                 {"id": "S1", "kind": "S", "x": 120, "y": 120, "z": 149}]
        o, game = self.ov(surge=surge, sites=sites, pending=11, day=10)
        o.roles = {"R1": "farm", "R2": "farm", "R3": "farm"}
        o.water_ok = lambda s: True
        o.water_wetness = lambda s: 0
        o.water_rank = lambda s: 0
        return o, game

    def test_stuck_designations_open_a_second_staircase(self):
        o, game = self.stuck()
        o.digging()                                        # first sight of pending 11: the mark is set
        self.assertEqual([a for t, a in game.calls if t == "dig_stairs" and a["site"] == "S1"
                          and o.last.get("stairs_surge") is not None], [])
        o.day += harness.SURGE_STALL_DAYS
        o.now += harness.SURGE_STALL_DAYS * harness.DAY
        o.digging()
        self.assertIn(("dig_stairs", {"site": "S1", "z_bottom": 148}), game.calls)
        self.assertIsNotNone(o.last.get("stairs_surge"))

    def test_moving_designations_or_open_play_never_open_one(self):
        o, game = self.stuck()
        o.digging()
        o.day += harness.SURGE_STALL_DAYS
        o.o["dig_designations_pending"] = 5               # the digs moved
        o.digging()
        self.assertIsNone(o.last.get("stairs_surge"))
        o2, game2 = self.stuck(surge=False)
        o2.digging()
        o2.day += harness.SURGE_STALL_DAYS
        o2.digging()
        self.assertIsNone(o2.last.get("stairs_surge"))


MODEL_COOK = {"id": 8, "recipe": "cook_meal", "repeat": "daily",
              "when": [{"item_type": "FOOD", "test": "LessThan", "value": 76, "stock": "prepared_meals"}]}
MODEL_BREW_CAPPED = {"id": 7, "recipe": "brew_drink", "repeat": "daily",
                     "when": [{"item_type": "DRINK", "test": "LessThan", "value": 320, "stock": "drink"}]}
MODEL_BREW_OPEN = {"id": 9, "recipe": "brew_drink", "repeat": "daily",
                   "when": [{"item_type": "DRINK", "test": "LessThan", "value": 900, "stock": "drink"}]}


class SurgeDrink(Base):
    def cancels(self, game):
        return sorted(a["order_id"] for t, a in game.calls if t == "cancel_order")

    def test_prep_holds_the_plants_for_the_window(self):
        o, game = self.ov(hands_off=10, orders=[MODEL_COOK, MODEL_BREW_CAPPED, MODEL_BREW_OPEN])
        o.closer()
        self.assertEqual(self.cancels(game), [8, 9])     # the plant-eating cook and the open brew; "below 320" stays
        self.assertEqual([a for t, a in game.calls if a.get("recipe") == "brew_drink" and not bridge(a)], [])   # not before the eve

    def test_short_food_keeps_the_kitchen(self):
        o, game = self.ov(hands_off=10, orders=[MODEL_COOK], stocks={"food_edible": 60})
        o.closer()
        self.assertEqual(self.cancels(game), [])

    def test_own_standings_are_retired_and_not_re_added(self):
        o, game = self.ov(hands_off=10, orders=[{"id": 50, "recipe": "brew_drink", "repeat": "daily",
                                                  "when": [{"item_type": "DRINK", "test": "LessThan", "value": 920}]}])
        o.key_order["o_brew"] = 50
        o.closer()
        self.assertIn(50, self.cancels(game))
        o.orders = []
        o.supply()
        self.assertEqual([a for t, a in game.calls if t == "add_order" and a.get("recipe") in ("brew_drink",
                                                                                               "cook_meal")
                          and not bridge(a)], [])

    def test_the_eve_adds_the_window_brew(self):
        o, game = self.ov(hands_off=harness.SURGE_BREW_LEAD)
        o.closer()
        brews = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink" and not bridge(a)]
        self.assertEqual(len(brews), 1)
        self.assertLessEqual(len(brews[0]["when"]), 3)

    def test_the_eve_covers_the_models_stride(self):
        """cx (hint std LT08-4 on f815b7c): passes on days 24, 25, 27, 32 (hands_off 7) then 60 — the model's 7-day
        advance skipped the eve, so the window brew never existed and drink fell 487 -> 442 in the window."""
        o, game = self.ov(hands_off=7)
        o.pass_days = [24, 25, 27, 32]          # gaps 1, 2, 5: the stride is 5
        self.assertEqual(o.surge_brew_lead(), harness.SURGE_BREW_LEAD + 5)
        o.closer()
        brews = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink" and not bridge(a)]
        self.assertEqual(len(brews), 1)

    def test_a_short_stride_keeps_the_brew_for_the_eve(self):
        o, game = self.ov(hands_off=7)
        o.pass_days = [29, 30, 31, 32]          # one-day passes: the eve will be seen
        self.assertEqual(o.surge_brew_lead(), harness.SURGE_BREW_LEAD + 1)
        o.closer()
        self.assertEqual([a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink" and not bridge(a)], [])
        o.pass_days = [2, 30]                   # a huge gap is capped
        self.assertEqual(o.surge_brew_lead(), harness.SURGE_BREW_LEAD_MAX)

    def test_before_prep_and_other_shapes_are_untouched(self):
        o, game = self.ov(hands_off=20, orders=[MODEL_COOK, MODEL_BREW_OPEN])   # surge, not yet in prep
        o.closer()
        self.assertEqual(self.cancels(game), [])
        lab = harness.Overseer(FakeGame(), goal="Brew a batch. From day 39 you can't act for 21 days.", days=60)
        lab.load(obs(hands_off=10, orders=[MODEL_COOK, MODEL_BREW_OPEN]))
        lab.count = 0
        lab.closer()
        self.assertEqual([a for t, a in lab.game.calls if t == "cancel_order"], [])
        self.assertTrue([a for t, a in lab.game.calls if a.get("recipe") == "brew_drink" and not bridge(a)])   # lab keeps prep brew


if __name__ == "__main__":
    unittest.main()
