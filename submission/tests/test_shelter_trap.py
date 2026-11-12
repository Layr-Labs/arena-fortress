"""cx SHELTER TRAP (hint std OP1-2 on 5ba40eb: 6 citizens dead of thirst and 8 dying, all 14 idle in the z161 farm
room — the fort's MeetingHall — from the day-282 unlock to day 336 with 539 drink in stock; 14 access_unseen looks
and nothing done). Probe of the same fort: a path re-index while the hatches are locked bakes them into the walkable
groups as walls and the flag-only unlock leaves the groups split; a finished construction anywhere, or a stair dug
from the trapped part to the surface, merges them and the Drink jobs come back. On access_unseen (from the second
look of an episode) the layer pokes: a workshop first (wood above the guard), then a stair from a free S site through
a wall column into the citizens' part, never near water. The alert and the hatch locks are untouched. No game or
network."""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness  # noqa: E402

SURFACE = 163
X0, Y0 = 84, 88
# 5ba40eb std OP1-2, /query/map of day 282, x 84..106, y 88..108 (z162: the lake at y<=94, the west pocket x90-92
# under hatch 22's X stair at (93,97), the east rooms under hatches 8/10/28; z161: the farm room under hatch 22)
Z162 = ["###^....^^##????????###", "??#^^..^^############^^", "############^^^^^^^^^^.", "^^^^^^^^^^^^...........",
        ".....................^^", "............^^^^^^^^^^#", "^^^^^^^^^^^^^##########", "###############<#??????",
        "?????#...###...##??????", "?????#...X##...<#??????", "?????#...###...##??????", "?????#####?##<########?",
        "???????????#.........#?", "???????????#.........#?", "???????????#.........#?", "???????????#.........#?",
        "???????????#.........#?", "???????????#.........#?", "???????????#.........#?", "???????????###########?",
        "???????????????????????"]
Z161 = ["?" * 23] * 7 + ["?????#########?????????", "?????#...#...#?????????", "?????#...<...#?????????",
                         "?????#...#...#?????????", "?????#########?????????"] + ["?" * 23] * 9
Z163 = ["." * 23] * 21   # the surface: open ground over the read box
LAKE = [{"x": x, "y": y, "z": 162, "depth": 7} for y in range(88, 95) for x in range(84, 97)]
SITES = [{"id": "S1", "kind": "S", "x": 93, "y": 95, "z": SURFACE, "free": True},
         {"id": "S2", "kind": "S", "x": 95, "y": 99, "z": SURFACE, "free": True},
         {"id": "S6", "kind": "S", "x": 92, "y": 96, "z": SURFACE, "free": True},
         {"id": "S8", "kind": "S", "x": 92, "y": 98, "z": SURFACE, "free": True}]
W = {"id": "W9", "kind": "W", "x": 103, "y": 105, "z": SURFACE, "w": 3, "h": 3}
DOORS = {"list": [{"id": i, "kind": "hatch", "x": x, "y": y, "z": SURFACE, "built": True, "locked": False}
                  for i, (x, y) in ((8, (99, 95)), (10, (99, 97)), (22, (93, 97)), (28, (97, 99)))],
         "hatch_cover_items_free": 0}


def pocket(n=14):
    """Every citizen idle in the pocket (the record's days 283-336): the farm room and the z162 tables."""
    spots = [(94, 97, 161), (91, 97, 161), (95, 96, 161), (91, 97, 162), (90, 96, 162), (96, 98, 161)]
    return [{"id": 92 + i, "job": "idle", "x": spots[i % 6][0], "y": spots[i % 6][1], "z": spots[i % 6][2],
             "adult": True, "profession": "Planter"} for i in range(n)]


def fort(day, drink=539, logs=203, sites=SITES, w=True, dwarves=None, alert=False):
    dwarves = pocket() if dwarves is None else dwarves
    inside = sum(1 for p in dwarves if p["z"] < SURFACE)
    obs = {"date": {"abs_tick": int(day * harness.DAY)}, "administrators": {"citizens": len(dwarves)},
           "stocks": {"drink": drink, "food_edible": 369, "logs_usable": logs},
           "map": {"sites": [dict(s) for s in sites] + ([dict(W)] if w else []),
                   "wagon": {"present": True, "x": 96, "y": 96, "z": SURFACE}, "surface_z": SURFACE},
           "dwarves": [dict(x) for x in dwarves], "recent_cancellations": [], "recent_events": [],
           "military": {"squads": []}, "threats": {"visible_hostiles": 0, "hostiles": []},
           "doors": json.loads(json.dumps(DOORS)),
           "burrows": {"civilian_alert": alert, "list": [{"id": 0, "name": "Shelter", "civ_alert_burrow": True,
                                                          "citizens_inside": inside}]}}
    return {"tick": int(day * harness.DAY), "day": int(day), "observation": obs, "days_left": 336 - int(day)}


class MapGame:
    def __init__(self, lake=True):
        self.calls, self.maps, self.lake = [], [], lake

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {}}

    def query(self, name, **kw):
        if name != "map":
            return {"result": {"units": []}}
        self.maps.append(dict(kw))
        levels = [{"z": z, "shape": rows} for z, rows in ((163, Z163), (162, Z162), (161, Z161))
                  if min(kw.get("z", 163), kw.get("z2", 161)) <= z <= max(kw.get("z", 163), kw.get("z2", 161))]
        liquid = (list(LAKE) if self.lake else []) + list(getattr(self, "extra", []))
        return {"result": {"x1": X0, "y1": Y0, "levels": levels, "liquid": liquid}}

    def tools(self, name):
        return [a for t, a in self.calls if t == name]


class Base(unittest.TestCase):
    def setUp(self):
        self.out = io.StringIO()
        self.output = redirect_stdout(self.out)
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def logs(self, kind):
        out = []
        for line in self.out.getvalue().splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("kind") == kind:
                out.append(rec)
        return out

    def ov(self, game=None):
        game = game or MapGame()
        ov = harness.Overseer(game, days=336)
        ov.count = 0
        return ov, game

    def pass_(self, ov, game, day, **kw):
        ov.load(fort(day, **kw))
        ov.count = 0
        game.calls.clear()
        ov.defend()
        ov.wildlife_response()
        ov.mark_guard()
        ov.entrance_hatches()
        return list(game.calls)

    def trapped(self, ov, game, days, **kw):
        """The record: drink access confirmed on day 276, then every look free, nobody out, the stock unmoved."""
        ov.load(fort(275, dwarves=pocket()[:13] + [dict(pocket()[13], z=SURFACE, x=100, y=105)]))
        ov.load(fort(277, dwarves=pocket()[:13] + [dict(pocket()[13], z=SURFACE, x=100, y=105)]))
        out = []
        for day in days:
            out.append(self.pass_(ov, game, day, **kw))
        return out


class Stair(Base):
    def test_the_5ba40eb_pocket_gets_s2_down_to_the_farm_room_and_s1_by_the_lake_is_refused(self):
        ov, game = self.ov()
        ov.load(fort(296))
        self.assertEqual(ov.trap_stair(), ("S2", 161))
        # S1 (93,95): its z162 wall touches the pocket, but the lake is 1 tile off — refused; S6/S8 stand over the
        # pocket's floor (dig_stairs would designate nothing there)

    def test_without_the_lake_s1_is_shorter_and_wins(self):
        ov, game = self.ov(MapGame(lake=False))
        ov.load(fort(296))
        self.assertEqual(ov.trap_stair(), ("S1", 162))

    def test_the_water_rules_decide_a_halted_site(self):
        # the generic deep_indoor_water halt holds every S site (5ba40eb: S1/S2 from day 14); water_ok re-probes it
        ov, game = self.ov()
        ov.load(fort(296))
        ov.water_halts.update({"S1": 14, "S2": 14})
        self.assertEqual(ov.trap_stair(), ("S2", 161))   # dry around S2: released by water_ok, then picked
        self.assertTrue(self.logs("water_resume"))
        game2 = MapGame()
        game2.extra = [{"x": 96, "y": 101, "z": 161, "depth": 4}]   # water by S2's column: halted, and refused
        ov2, _ = self.ov(game2)
        ov2.load(fort(296))
        ov2.water_halts["S2"] = 14
        self.assertIsNone(ov2.trap_stair())

    def test_no_citizen_below_the_surface_no_stair(self):
        ov, game = self.ov()
        ov.load(fort(296, dwarves=[dict(p, z=SURFACE) for p in pocket()]))
        self.assertIsNone(ov.trap_stair())


class Poke(Base):
    def test_record_replay_workshop_then_stair_one_poke_per_two_days(self):
        ov, game = self.ov()
        calls = self.trapped(ov, game, [289, 290, 291, 292, 293])
        shops = [c for day in calls for c in day if c[0] == "build_workshop"]
        stairs = [c for day in calls for c in day if c[0] == "dig_stairs"]
        poke = lambda day: [c for c in day if c[0] in ("build_workshop", "dig_stairs")]
        self.assertEqual(poke(calls[0]), [])   # the first access_unseen look: no poke yet (TRAP_SEEN)
        self.assertEqual(shops, [("build_workshop", {"site": "W9", "type": "Carpenters"})])
        self.assertEqual(stairs, [("dig_stairs", {"site": "S2", "z_bottom": 161})])
        self.assertEqual([c for c in calls[1] if c[0] == "build_workshop"], shops)   # day 290: the workshop
        self.assertEqual([c for c in calls[3] if c[0] == "dig_stairs"], stairs)      # day 292: the stair
        self.assertEqual(len(self.logs("trap_poke")), 2)
        self.assertFalse([c for day in calls for c in day if c[0] in ("lock_door", "civilian_alert")])

    def test_no_wood_to_spare_goes_straight_to_the_stair(self):
        ov, game = self.ov()
        calls = self.trapped(ov, game, [289, 290], logs=5)
        self.assertEqual([c[0] for c in calls[1] if c[0] in ("build_workshop", "dig_stairs")], ["dig_stairs"])

    def test_no_drink_in_stock_no_poke(self):
        ov, game = self.ov()
        calls = self.trapped(ov, game, [289, 290, 291], drink=0)
        self.assertFalse([c for day in calls for c in day if c[0] in ("build_workshop", "dig_stairs")])

    def test_access_seen_again_ends_the_episode(self):
        ov, game = self.ov()
        self.trapped(ov, game, [289, 290])
        self.assertEqual(ov.trap_pokes, 1)
        out = [dict(p, z=SURFACE, x=100, y=105) for p in pocket()]
        for day in (291, 293, 294):
            self.pass_(ov, game, day, dwarves=out)
        self.assertFalse(ov.thirst_due())
        self.assertEqual((ov.trap_pokes, ov.trap_seen, ov.trap_last), (0, 0, None))

    def test_a_single_unseen_look_that_clears_never_pokes(self):
        # c44c96b std OP1-4 day 151: one access_unseen look, an access window the same day
        ov, game = self.ov()
        calls = self.trapped(ov, game, [289])
        out = [dict(p, z=SURFACE, x=100, y=105) for p in pocket()]
        calls += [self.pass_(ov, game, d, dwarves=out) for d in (290, 292)]
        self.assertFalse([c for day in calls for c in day if c[0] in ("build_workshop", "dig_stairs")])

    def test_at_most_trap_pokes_an_episode(self):
        ov, game = self.ov()
        calls = self.trapped(ov, game, range(289, 289 + 2 * harness.TRAP_POKES + 8))
        n = sum(1 for day in calls for c in day if c[0] in ("build_workshop", "dig_stairs"))
        self.assertEqual(n, harness.TRAP_POKES)


if __name__ == "__main__":
    unittest.main()
