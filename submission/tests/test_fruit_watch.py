"""cx: a lab fort short of drink leaves a fruit brew standing for its window, reads the seed stock daily in the first
days, and logs the seed kinds the observation still lists after the query lost them.

Measured shape: hint hard LT02-0 on 9a8a399 and LT02-1 on 6adf843 (and the leader's harness on LT02-0): the SEEDS
query listed plump helmet 3 / cave wheat 3 / dimple cup 2 / pig tail 2 / quarry bush 2 / sweet pod 2 on day 0 and only
cave wheat 3 / quarry bush 2 on day 6-7, while /observe seeds_by_kind kept all 14 until day 14-17; plants 0 and
PLANT_GROWTH 0 in every census through day 67; drink 0 for all 90 days (partial 0.60). No game or network is used."""
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
    def __init__(self, stocks=None):
        self.calls, self.queries = [], []
        self.stocks = stocks or {}

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {"order_id": 900 + len(self.calls)}}

    def query(self, name, **params):
        self.queries.append((name, params))
        return {"ok": True, "result": {"ok": True, "groups": self.stocks.get(params.get("item_type"), [])}}


LT02_KINDS = {"cave wheat": {"n": 3, "seasons": ["summer", "autumn"], "underground": True},
              "dimple cup": {"n": 2, "seasons": ["spring", "summer", "autumn", "winter"], "underground": True},
              "pig tail": {"n": 2, "seasons": ["summer", "autumn"], "underground": True},
              "plump helmet": {"n": 3, "seasons": ["spring", "summer", "autumn", "winter"], "underground": True},
              "quarry bush": {"n": 2, "seasons": ["spring", "summer", "autumn"], "underground": True},
              "sweet pod": {"n": 2, "seasons": ["spring", "summer"], "underground": True}}
# the query on day 6 (cx9a8a399-hint-hard-LT02-0, game/harness-0.api.jsonl)
DAY6_SEEDS = [{"material": "PLANT:GRASS_WHEAT_CAVE:SEED", "items": 3, "count": 3, "in_inventory": 3},
              {"material": "PLANT:BUSH_QUARRY:SEED", "items": 2, "count": 2, "in_inventory": 2}]


def fort(day=56, drink=0, pb=0, hands_off=13, cit=17, kinds=None, orders=()):
    return {"day": day, "tick": day * harness.DAY, "hands_off_in_days": hands_off, "days_left": 90 - day,
            "observation": {
                "administrators": {"citizens": cit}, "map": {"sites": [], "surface_z": 113},
                "orders": [dict(o) for o in orders], "farm_plots": [],
                "stocks": {"seeds": 14, "drink": drink, "plants_brewable": pb, "plants_total": pb,
                           "food_edible": 35, "furniture_free": {}, "seeds_by_kind": dict(kinds or {})}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, game=None, days=90):
        ov = harness.Overseer(game or FakeGame(), days=days)
        ov.count = 0
        return ov

    def fruit_orders(self, game):
        return [a for t, a in game.calls if t == "add_manager_order"
                and a.get("reaction") == "BREW_DRINK_FROM_PLANT_GROWTH"]


class FruitWatch(Base):
    def test_window_prep_without_drink_leaves_a_conditioned_fruit_standing(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(fort())
        ov.window_supply()
        got = self.fruit_orders(game)
        self.assertEqual(len(got), 1)
        a = got[0]
        self.assertEqual((a["job"], a["repeat"], a["amount"]), ("CustomReaction", "daily", 1))
        self.assertEqual(len(a["when"]), 3)   # the API's 3-clause cap
        growth = [c for c in a["when"] if c["item_type"] == "PLANT_GROWTH"][0]
        self.assertEqual((growth["reaction_product"], growth["at_least"]), ("DRINK_MAT", 1))
        self.assertIn("unrotten", growth["flags"])
        self.assertIn({"item_type": "BARREL", "flags": ["empty"], "at_least": 1}, a["when"])
        self.assertIn({"item_type": "DRINK", "below": harness.FRUIT_WIN_DRINK_PER_CIT * 17}, a["when"])

    def test_the_standing_is_added_once(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(fort())
        ov.window_supply()
        ov.load(fort(day=60, hands_off=9))
        ov.window_supply()
        self.assertEqual(len(self.fruit_orders(game)), 1)

    def test_drink_at_the_cap_adds_nothing(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(fort(drink=harness.FRUIT_WIN_DRINK_PER_CIT * 17))
        ov.fruit_watch()
        self.assertEqual(self.fruit_orders(game), [])

    def test_open_play_and_the_surge_add_nothing(self):
        game = FakeGame()
        ov = self.overseer(game, days=336)
        ov.load(fort(hands_off=None))
        ov.fruit_watch()
        ov2 = self.overseer(game)
        ov2.load(fort())
        ov2.surge = True
        ov2.fruit_watch()
        self.assertEqual(self.fruit_orders(game), [])

    def test_the_closer_reaches_it_in_window_prep(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(fort(hands_off=harness.WINDOW_PREP_DAYS))
        ov.closer()
        self.assertEqual(len(self.fruit_orders(game)), 1)
        game2 = FakeGame()
        ov2 = self.overseer(game2)
        ov2.load(fort(day=20, hands_off=49))
        ov2.closer()
        self.assertEqual(self.fruit_orders(game2), [])


class EarlyCensus(Base):
    def test_daily_through_the_first_days_then_every_five(self):
        game = FakeGame({"SEEDS": DAY6_SEEDS})
        ov = self.overseer(game)
        for day in (0, 1, 2):
            ov.load(fort(day=day, hands_off=69 - day, kinds=LT02_KINDS))
            ov.seed_census()
        self.assertEqual(len(game.queries), 6)
        ov.load(fort(day=harness.SEED_CENSUS_EARLY_DAYS + 1, hands_off=60, kinds=LT02_KINDS))
        ov.seed_census()   # day 9: 7 days after day 2, so it runs
        ov.load(fort(day=harness.SEED_CENSUS_EARLY_DAYS + 2, hands_off=59, kinds=LT02_KINDS))
        ov.seed_census()   # day 10: the 5-day interval again
        self.assertEqual(len(game.queries), 8)

    def test_ghost_kinds_are_the_observation_beyond_the_query(self):
        game = FakeGame({"SEEDS": DAY6_SEEDS})
        ov = self.overseer(game)
        ov.load(fort(day=6, hands_off=63, kinds=LT02_KINDS))
        out = io.StringIO()
        with redirect_stdout(out):
            ov.seed_census()
        self.assertEqual(ov.seeds_not_in_query(),
                         {"dimple cup": 2, "pig tail": 2, "plump helmet": 3, "sweet pod": 2})
        self.assertIn('"seed_ghosts"', out.getvalue())

    def test_no_ghosts_when_the_query_holds_every_kind(self):
        game = FakeGame({"SEEDS": DAY6_SEEDS})
        ov = self.overseer(game)
        ov.load(fort(day=19, hands_off=50, kinds={k: v for k, v in LT02_KINDS.items()
                                                  if k in ("cave wheat", "quarry bush")}))
        ov.seed_census()
        self.assertEqual(ov.seeds_not_in_query(), {})

    def test_no_census_no_ghosts(self):
        ov = self.overseer()
        ov.load(fort(kinds=LT02_KINDS))
        self.assertEqual(ov.seeds_not_in_query(), {})


# 6adf843 LT02-1, observation on day 2 (z 125 surface): the R sites the stair revealed
DAY2_SITES = [{"id": "G1", "kind": "G", "z": 125, "soil": True, "subterranean": False, "x": 1, "y": 1},
              {"id": "R1", "kind": "R", "z": 124, "soil": True, "subterranean": True, "x": 5, "y": 5},
              {"id": "R2", "kind": "R", "z": 124, "soil": True, "subterranean": True, "x": 9, "y": 5},
              {"id": "R3", "kind": "R", "z": 124, "soil": False, "subterranean": True, "x": 13, "y": 5},
              {"id": "S4", "kind": "S", "z": 125, "x": 20, "y": 20}]
F_SITE = {"id": "F1", "kind": "F", "z": 124, "soil": True, "subterranean": True, "x": 5, "y": 5}


def early(day=2, sites=DAY2_SITES, plots=(), drink=0, pb=0, kinds=None, hands_off=None, doy=None, plugins=None):
    r = fort(day=day, drink=drink, pb=pb, hands_off=67 - day if hands_off is None else hands_off,
             kinds=LT02_KINDS if kinds is None else kinds)
    o = r["observation"]
    o["map"] = {"sites": [dict(x) for x in sites], "surface_z": 125}
    o["farm_plots"] = [dict(p) for p in plots]
    o["date"] = {"day_of_year": (19 + day) if doy is None else doy, "abs_tick": 828000 + day * harness.DAY}
    o["plugins"] = dict(plugins or {"autochop": "on", "seedwatch": "on", "autofarm": "off"})
    o["administrators"]["manager_active_for_orders"] = True
    return r


class SeedRush(Base):
    def test_on_for_the_lt02_shape(self):
        ov = self.overseer()
        ov.load(early())
        self.assertTrue(ov.seed_rush())

    def test_off_after_the_rush_days_with_drink_with_a_built_plot_or_in_open_play(self):
        for kw in ({"day": harness.SEED_RUSH_DAYS + 1}, {"drink": 17}, {"pb": 2},
                   {"plots": [{"id": 5, "built": True, "z": 124}]}):
            ov = self.overseer()
            ov.load(early(**kw))
            self.assertFalse(ov.seed_rush(), kw)
        ov = self.overseer(days=336)
        r = early()
        r["hands_off_in_days"] = None
        ov.load(r)
        self.assertFalse(ov.seed_rush())

    def test_off_without_an_in_season_underground_seed(self):
        ov = self.overseer()
        ov.load(early(kinds={"cave wheat": LT02_KINDS["cave wheat"]}))   # summer / autumn only, now spring
        self.assertFalse(ov.seed_rush())
        ov.load(early(kinds={}))
        self.assertFalse(ov.seed_rush())

    def test_an_unbuilt_plot_keeps_it_on(self):
        ov = self.overseer()
        ov.load(early(plots=[{"id": 5, "built": False, "z": 124}]))
        self.assertTrue(ov.seed_rush())

    def test_the_dormitory_dig_waits_for_the_farm_rooms(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(early())
        ov.digging()
        digs = {a.get("site"): a for t, a in game.calls if t == "dig_room"}
        self.assertIn("R1", digs)
        self.assertIn("R2", digs)
        self.assertNotIn("R3", digs)   # the non-soil room (dorm) waits
        self.assertNotIn("w", digs["R1"])   # the farm room keeps its 3x3 default
        self.assertEqual(ov.roles.get("R1"), "farm")

    def test_without_the_rush_the_dormitory_is_dug_with_the_farms(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(early(drink=40))
        ov.digging()
        self.assertIn("R3", [a.get("site") for t, a in game.calls if t == "dig_room"])

    def test_a_placed_plot_turns_autofarm_on_in_the_same_pass(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(early(day=4, sites=DAY2_SITES + [F_SITE]))
        ov.farms()
        tools = [(t, a.get("site") or a.get("name")) for t, a in game.calls]
        self.assertIn(("build_farm", "F1"), tools)
        self.assertIn(("enable_automation", "autofarm"), tools)
        self.assertLess(tools.index(("build_farm", "F1")), tools.index(("enable_automation", "autofarm")))

    def test_no_autofarm_call_when_it_is_on(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(early(day=4, sites=DAY2_SITES + [F_SITE], plugins={"autofarm": "on"}))
        ov.farms()
        self.assertNotIn("enable_automation", [t for t, _ in game.calls])

    def test_the_chunk_look_stops_on_the_rooms_and_then_on_the_f_site(self):
        ov = self.overseer()
        ov.load(early(day=0, sites=[DAY2_SITES[0], DAY2_SITES[4]]))
        self.assertEqual(ov.rush_signs(early(day=0, sites=[DAY2_SITES[0], DAY2_SITES[4]])["observation"]), set())
        look = early(day=2)["observation"]
        self.assertEqual(ov.rush_signs(look), {"farm_room:R1", "farm_room:R2"})
        ov.roles.update({"R1": "farm", "R2": "farm"})   # the layer designated them
        self.assertEqual(ov.rush_signs(look), set())
        self.assertEqual(ov.rush_signs(early(day=4, sites=DAY2_SITES + [F_SITE])["observation"]),
                         {"farm_site:F1"})

    def test_rush_signs_reach_the_danger_look(self):
        game = FakeGame()
        ov = self.overseer(game)
        ov.load(early(day=0, sites=[DAY2_SITES[0], DAY2_SITES[4]]))
        ov.others = lambda day: []
        self.assertIn("farm_room:R2", ov.danger_signs(early(day=2), query=True))


if __name__ == "__main__":
    unittest.main()
