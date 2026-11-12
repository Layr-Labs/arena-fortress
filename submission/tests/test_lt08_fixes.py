"""H-family regressions (ROOT_CAUSES §H): the window brew's `when` must fit the API's 3-clause cap, and a full
primary dormitory must divert its beds to an open floor instead of knocking on the same full one forever. Both
measures stay on the surge/lab shape: a windowless task (MY1/OP1) keeps the leader's behaviour exactly. Offline:
no game and no network — the double mirrors the API's own add_order and place_furniture contracts."""
import copy
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

WHEN_CAP = 3                      # the API's documented cap on add_order's when clauses
WHEN_REJECT = "args.when has more than 3 items"
NO_SPACE = "every tile is wall, undug, built on or designated"



def bridge(a):
    """cx lt08drink: the window bridge (o_brew_bridge_win, the one brew standing with a drink cap; tested in
    test_window_bridge.py) is left out where a test counts the eve's window brew."""
    return "drink" in [w.get("stock") for w in a.get("when") or []]

class FakeGame:
    """Records every call; add_order with an oversized when is refused like the real API (so a fourth clause
    anywhere in the driven paths shows up as a recorded rejection), and place_furniture answers no_space for
    sites listed in full_sites."""

    def __init__(self):
        self.calls = []
        self.rejects = []
        self.sites = {}           # id -> site dict: place_furniture answers points inside the site, like the API
        self.full_sites = set()

    def act(self, tool, args):
        args = args.copy()
        self.calls.append((tool, args))
        if tool == "add_order":
            when = args.get("when")
            if when is not None and len(when) > WHEN_CAP:
                self.rejects.append((tool, args))
                return {"ok": False, "error_code": "bad_arguments", "error": WHEN_REJECT}
            return {"ok": True, "result": {"order_id": len(self.calls)}}
        if tool == "place_furniture":
            if args.get("site") in self.full_sites:
                return {"ok": False, "error_code": harness.OVERFLOW_ERROR, "error": NO_SPACE}
            s = self.sites.get(args.get("site")) or {}
            at = [[(s.get("x") or 10) + 1, (s.get("y") or 10) + 1, s.get("z") or 9]]
            return {"ok": True, "result": {"n": len(at), "at": copy.deepcopy(at)}}
        return {"ok": True, "result": {}}

    def query(self, *a, **kw):
        return {"result": {}}


def site(id="A1", x=10, y=10, z=9, w=7, h=6, open_tiles=32, **kw):
    return {"id": id, "kind": id[0], "x": x, "y": y, "z": z, "w": w, "h": h,
            "open_tiles": open_tiles, **kw}


def facts(cit=19, hands_off=21, sites=(), stocks=None):
    return {"tick": 0, "hands_off_in_days": hands_off, "observation": {
        "administrators": {"citizens": cit, "manager_active_for_orders": True, "MANAGER_id": 1},
        "stocks": stocks if stocks is not None else {"plants_brewable": 25, "plants_total": 30,
                                                     "food_edible": 200, "drink": 480, "beds": 12,
                                                     "barrels_empty": 5, "logs_usable": 40},
        "map": {"sites": list(sites)}, "zones": [], "furniture": [], "workshops": [],
        "orders": [], "plugins": {"autochop": "on", "seedwatch": "on", "autofarm": "on"},
        "farm_plots": [], "dig_designations_pending": 0, "date": {"abs_tick": 0},
    }}


GOAL_LT08 = "Migrants are arriving. From day 39 you can't act for 21 days."
GOAL_OPEN = "Run the fortress for {days} days."


class Base(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def overseer(self, cit=19, hands_off=21, goal_migrant=True, sites=(), days=60):
        game = FakeGame()
        overseer = harness.Overseer(game, goal=GOAL_LT08 if goal_migrant else GOAL_OPEN.format(days=days),
                                    days=days)
        overseer.load(facts(cit=cit, hands_off=hands_off, sites=sites))
        overseer.count = 0
        return overseer, game

    @staticmethod
    def placed_beds(game):
        return [(a.get("site"), a.get("count")) for t, a in game.calls
                if t == "place_furniture" and a.get("kind") == "bed"]

    @staticmethod
    def zones(game):
        return [a for t, a in game.calls if t == "make_zone"]


# ---- H-1: the window brew order, and the whole layer's order book, must fit the API's 3-clause when cap
class WindowBrewWhen(Base):
    def test_window_brew_carries_three_clauses_and_no_drink_cap(self):
        overseer, game = self.overseer(hands_off=harness.SURGE_BREW_LEAD)   # cx: the surge's brew waits for the eve
        overseer.window_supply()
        brews = [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink" and not bridge(a)]
        self.assertEqual(len(brews), 1)
        self.assertEqual(len(brews[0]["when"]), 3)
        self.assertIn({"stock": "plants_brewable", "at_least": 2}, brews[0]["when"])
        self.assertIn({"stock": "food_edible", "at_least": max(3, overseer.cit // 2)}, brews[0]["when"])
        self.assertIn({"stock": "barrels_empty", "at_least": 1}, brews[0]["when"])
        self.assertNotIn("drink", [w.get("stock") for w in brews[0]["when"]])
        self.assertEqual(game.rejects, [])

    def test_every_order_whens_stay_within_the_api_cap_across_the_shapes(self):
        """Scans every add_order the double received while the whole order-emitting surface runs on the three task
        shapes: the surge lab (LT08), a windowless 200-day run (MY1's cook-reserve stage), a full-year run. Any
        path that grows a fourth clause trips the double's API-faithful rejection, asserted empty."""
        shapes = [dict(goal_migrant=True, hands_off=21, days=60, cit=19),
                  dict(goal_migrant=True, hands_off=2, days=60, cit=19),   # cx: the surge window brew's eve
                  dict(goal_migrant=True, hands_off=None, days=200, cit=17),
                  dict(goal_migrant=False, hands_off=None, days=340, cit=21),
                  dict(goal_migrant=False, hands_off=None, days=180, cit=15)]
        for shape in shapes:
            with self.subTest(**shape):
                overseer, game = self.overseer(**shape)
                overseer.supply()
                overseer.window_supply()
                overseer.endgame_supply()
                overseer.glut_bank()
                overseer.housing_check()
                overseer.food_hist.extend([(0, 400, 100), (1, 350, 100), (2, 300, 100)])
                overseer.o["workshops"] = [{"type": "Kitchen"}]
                overseer.food_security()
                overseer.stock_hist.extend([(0, 100, 10, 0), (1, 90, 10, 0), (2, 80, 10, 0),
                                            (3, 70, 10, 0), (4, 60, 10, 0), (5, 50, 10, 0)])
                overseer.o["recent_events"] = []
                overseer.stock_sliding()   # the merged tree's slope watch (replaces the removed brew_watch)
                oversize = [(t, a) for t, a in game.calls
                            if t == "add_order" and a.get("when") and len(a["when"]) > WHEN_CAP]
                self.assertEqual(oversize, [])
                self.assertEqual(game.rejects, [])


# ---- H-2: a full primary dormitory diverts its beds instead of repeating no_space on the same site
def dorm_sites(extra=()):
    """The measured LT08 shape: A1 covers the whole dorm dig on z9 (R1 beneath it, same floor, so equally full);
    R2 is a surge dorm room on another level with open tiles to spare."""
    return [site("A1", z=9, open_tiles=1), site("R1", z=9, open_tiles=1, dug=True),
            site("R2", z=5, open_tiles=30, dug=True)] + list(extra)


class BedOverflow(Base):
    def prime(self, sites, full, cit=19, goal_migrant=True, hands_off=21):
        overseer, game = self.overseer(cit=cit, goal_migrant=goal_migrant, hands_off=hands_off, sites=sites)
        game.sites = {s["id"]: s for s in sites}
        overseer.roles = {"R1": "dorm", "R2": "dorm"}
        overseer.free = {"bed": 10}   # free furniture is snapshotted in load(); the fixture sets it directly
        game.full_sites = set(full)
        return overseer, game

    def test_full_primary_site_diverts_to_the_surge_dorm_room(self):
        overseer, game = self.prime(dorm_sites(), full={"A1", "R1"})
        overseer.furnish()
        beds = self.placed_beds(game)
        self.assertEqual(beds[0], ("A1", 10))          # the primary dormitory is still tried first
        self.assertEqual(beds[1], ("R2", 10))          # the surge dorm room takes the wave's beds
        self.assertEqual([a.get("site") for a in self.zones(game)], ["R2"])   # and is zoned a dormitory

    def test_open_play_spreads_a_full_dormitorys_beds(self):
        """cx housing boxes: open play's full dormitory no longer strands the free beds (std OP1-3 e60d4ce: A11
        no_space from day 228 with 4 beds free, beds 14 for 16 citizens at H) — the next site with floor takes them."""
        overseer, game = self.prime(dorm_sites(), full={"A1", "R1"}, goal_migrant=False, hands_off=None)
        overseer.furnish()
        beds = self.placed_beds(game)
        self.assertEqual(beds[0], ("A1", 10))          # the primary dormitory is still tried first
        self.assertGreater(len(beds), 1)               # then the spread knocks on another floor
        self.assertNotIn(("R1", 10), beds[1:])         # never back on a refused one

    def test_no_divert_while_the_primary_still_places(self):
        overseer, game = self.prime(dorm_sites(), full=set())
        overseer.furnish()
        self.assertEqual(self.placed_beds(game), [("A1", 10)])   # success: no second knock anywhere
        self.assertEqual(self.zones(game), [{"kind": "dormitory", "site": "A1"}])   # the leader's own zoning

    def test_a_tried_floor_is_not_knocked_on_again(self):
        sites = dorm_sites(extra=[site("R3", z=6, open_tiles=40, dug=True)])
        overseer, game = self.prime(sites, full={"A1", "R1"})
        overseer.roles["R3"] = "dorm"
        overseer.furnish()                       # tries R3 first: the biggest open dorm room in the pool
        self.assertEqual(self.placed_beds(game)[1], ("R3", 10))
        game.full_sites.add("R3")
        overseer.now += harness.DAY              # the act gate needs a day between attempts
        overseer.furnish()
        beds = self.placed_beds(game)
        self.assertEqual(beds[-1][0], "R2")      # next pass diverts elsewhere, never R3 again
        self.assertEqual(len([b for b in beds if b[0] == "R3"]), 1)

    def test_farm_levels_take_beds_but_farm_rooms_do_not(self):
        """Changed (cx surge beds): every measured surge fort had ONE dug level with its farm plots on it (dw6
        LT08-0/1/2), so excluding farm levels left the wave no floor at all. The level's A site takes beds now; a
        farm-role R room itself never does."""
        sites = [site("A1", z=9, open_tiles=32), site("A2", z=7, open_tiles=40),
                 site("R3", z=7, open_tiles=40, dug=True)]
        overseer, game = self.prime(sites, full={"A1"})
        overseer.roles = {"R3": "farm"}
        overseer.furnish()
        self.assertEqual(self.placed_beds(game), [("A1", 10), ("A2", 10)])
        self.assertNotIn("R3", [b[0] for b in self.placed_beds(game)])


if __name__ == "__main__":
    unittest.main()
