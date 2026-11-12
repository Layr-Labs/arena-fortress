"""cx shelter / big-beast hold / entrance hatches (owner-approved 2026-11-10). (1) The Shelter burrow covers every
dug level (each A site below the surface, a dug R room where the A box is too wide for create_burrow or missing),
never a wet level. (2) A large beast (DANGER_BIG) near the wagon or a citizen holds the alert with no evidence rule
and outside the wildlife budget; the 10-day cap and the rest stay, and an approach during the rest re-sounds it.
(3) Surface entrances get hatch covers; while the alert is on and every citizen is in the Shelter they are locked,
and unlocked when it clears or anyone is outside. No game or network."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness  # noqa: E402

SURFACE = 169
WAGON = {"present": True, "x": 95, "y": 95, "z": SURFACE}
MASON = {"id": 7, "name": "Catten", "profession": "Mason", "x": 150, "y": 40, "z": SURFACE}
E1 = {"id": "E1", "kind": "E", "x": 100, "y": 101, "z": SURFACE}
E2 = {"id": "E2", "kind": "E", "x": 97, "y": 91, "z": SURFACE}


class FakeGame:
    def __init__(self, units=(), answers=None):
        self.calls, self.units, self.answers = [], list(units), dict(answers or {})

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool == "lock_door" and (tool, args.get("site")) not in self.answers:
            # the real /act lock_door answer (hint hard MY1-1 api log): result {doors, locked, unbuilt}
            return {"ok": True, "result": {"doors": [args["door_id"]] if "door_id" in args else [],
                                           "locked": bool(args.get("locked")), "unbuilt": 0}}
        return self.answers.get((tool, args.get("site")), {"ok": True, "result": {}})

    def query(self, *a, **kw):
        return {"result": {"units": list(self.units)}}

    def tools(self, name):
        return [a for t, a in self.calls if t == name]


def fort(day, sites=(), alert=False, inside=None, citizens=18, doors=None, dwarves=(MASON,), orders=(),
         squads=(), logs=0):
    """The real observation's shape: the dwarves list holds every citizen (the given ones first, the rest in the
    Shelter at z168, 30 tiles from the wagon); with `inside` given, exactly that many stand below the surface (the given ones go out first)."""
    bur = {"id": 0, "civ_alert_burrow": True}
    people = [dict(x) for x in dwarves][:citizens]
    people += [{"id": 1000 + i, "name": "Urist", "profession": "Miner", "x": 125, "y": 125, "z": SURFACE - 1}
               for i in range(citizens - len(people))]
    if inside is not None:
        bur["citizens_inside"] = inside
        out = max(0, citizens - inside)
        for i, p in enumerate(people):
            if i < out:
                p["z"] = SURFACE
            elif p["z"] >= SURFACE:
                p.update(x=125, y=125, z=SURFACE - 1)
    dwarves = people
    obs = {"date": {"abs_tick": day * harness.DAY}, "administrators": {"citizens": citizens},
           "stocks": {"drink": 500, "food_edible": 150, "logs_usable": logs},
           "map": {"sites": [dict(s) for s in sites], "wagon": dict(WAGON), "surface_z": SURFACE},
           "dwarves": [dict(x) for x in dwarves], "recent_cancellations": [], "recent_events": [],
           "military": {"squads": [dict(q) for q in squads]}, "threats": {"visible_hostiles": 0, "hostiles": []},
           "burrows": {"civilian_alert": alert, "list": [bur]}, "orders": list(orders)}
    if doors is not None:
        obs["doors"] = doors
    return {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": 336 - day}


class Quiet(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)


def overseer(game):
    ov = harness.Overseer(game, days=336)
    ov.count = 0
    return ov


def A(sid, z, w=12, h=3):
    return {"id": sid, "kind": "A", "x": 94, "y": 90, "z": z, "w": w, "h": h, "open_tiles": 20}


class Shelter(Quiet):
    def test_every_dug_level_goes_into_the_shelter_highest_first_three_a_pass(self):
        game = FakeGame()
        ov = overseer(game)
        sites = [A("A1", 168), A("A2", 167), A("A3", 166), A("A4", 165), A("A9", SURFACE)]
        ov.load(fort(10, sites))
        ov.shelter_grow()
        self.assertEqual(game.tools("create_burrow"), [{"site": "A1"}, {"site": "A2"}, {"site": "A3"}])
        game.calls.clear()
        ov.load(fort(11, sites))
        ov.shelter_grow()
        self.assertEqual(game.tools("create_burrow"), [{"site": "A4"}])   # the surface "A" is never added
        game.calls.clear()
        ov.load(fort(12, sites))
        ov.shelter_grow()
        self.assertEqual(game.tools("create_burrow"), [])   # all in: nothing repeats

    def test_a_grown_level_box_is_added_again_under_its_new_id(self):
        game = FakeGame()
        ov = overseer(game)
        ov.load(fort(10, [A("A1", 168)]))
        ov.shelter_grow()
        ov.load(fort(20, [A("A3", 168, w=15, h=12)]))
        ov.shelter_grow()
        self.assertEqual(game.tools("create_burrow"), [{"site": "A1"}, {"site": "A3"}])

    def test_a_too_wide_level_falls_back_to_its_dug_rooms_and_deep_rooms_join_too(self):
        # hint hard MY1-1: z141 grew to a 56x25 box, past create_burrow's [1,40] gate
        game = FakeGame()
        ov = overseer(game)
        sites = [A("A5", 168, w=56, h=25),
                 {"id": "R1", "kind": "R", "x": 100, "y": 100, "z": 168, "w": 3, "h": 3, "dug": True},
                 {"id": "R2", "kind": "R", "x": 100, "y": 100, "z": 168, "w": 3, "h": 3, "dug": False},
                 {"id": "R7", "kind": "R", "x": 100, "y": 100, "z": 162, "w": 3, "h": 3, "dug": True}]
        ov.load(fort(10, sites))
        ov.shelter_grow()
        self.assertEqual(game.tools("create_burrow"), [{"site": "R1"}, {"site": "R7"}])

    def test_a_dug_room_on_a_level_with_an_a_site_is_not_added_twice(self):
        game = FakeGame()
        ov = overseer(game)
        ov.load(fort(10, [A("A1", 168),
                          {"id": "R1", "kind": "R", "x": 100, "y": 100, "z": 168, "w": 3, "h": 3, "dug": True}]))
        ov.shelter_grow()
        self.assertEqual(game.tools("create_burrow"), [{"site": "A1"}])

    def test_a_wet_level_is_never_added(self):
        game = FakeGame()
        ov = overseer(game)
        ov.wet_z = {167}
        ov.load(fort(10, [A("A1", 168), A("A2", 167)]))
        ov.shelter_grow()
        self.assertEqual(game.tools("create_burrow"), [{"site": "A1"}])

    def test_nothing_designated_counts_as_done_and_a_refusal_retries(self):
        game = FakeGame(answers={("create_burrow", "A1"): {"ok": False, "error_code": "nothing_designated"},
                                 ("create_burrow", "A2"): {"ok": False, "error_code": "game_refused"}})
        ov = overseer(game)
        sites = [A("A1", 168), A("A2", 167)]
        ov.load(fort(10, sites))
        ov.shelter_grow()
        self.assertIn("A1", ov.shelter_added)
        self.assertNotIn("A2", ov.shelter_added)
        game.calls.clear()
        ov.load(fort(12, sites))
        ov.shelter_grow()
        self.assertEqual(game.tools("create_burrow"), [{"site": "A2"}])

    def test_defend_grows_the_shelter(self):
        game = FakeGame()
        ov = overseer(game)
        ov.load(fort(10, [A("A1", 168)]))
        ov.defend()
        self.assertEqual(game.tools("create_burrow"), [{"site": "A1"}])


class BigBeast(Quiet):
    def look(self, ov, game, day, **kw):
        ov.load(fort(day, **kw))
        ov.count = 0
        game.calls.clear()
        ov.defend()
        ov.wildlife_response()
        ov.mark_guard()
        return game.tools("civilian_alert")

    def test_big_races(self):
        for r in ("CARNOTAURUS", "GRIZZLY_BEAR", "GIANT_ALLIGATOR", "WOLF", "COUGAR"):
            self.assertTrue(harness.big_race(r), r)
        for r in ("ALLIGATOR_SNAPPING_TURTLE", "WOLF_SPIDER", "GRAY_LANGUR", "BIRD_KEA", "BADGER", "", None):
            self.assertFalse(harness.big_race(r), r)
        for n in harness.DANGER_BIG:
            self.assertIn(n, harness.DANGER_SEED)       # every big name is marked from the start
            self.assertNotIn(n, harness.DANGER_WEAK)    # and never gets soldiers

    def test_a_spent_wildlife_budget_does_not_stop_a_big_beast_alert_and_its_days_are_not_charged(self):
        game = FakeGame([{"id": 5, "race": "CARNOTAURUS", "hostile": False, "x": 100, "y": 100, "z": SURFACE}])
        ov = overseer(game)
        ov.load(fort(60))
        ov.wild_spans = [[40 * harness.DAY, 55 * harness.DAY]]   # 15 small-animal days inside the window
        self.assertFalse(ov.wild_budget_left())
        self.assertEqual(self.look(ov, game, 60), [{"on": True}])
        self.assertEqual(self.look(ov, game, 66, alert=True), [])   # held, budget or not, no evidence
        self.assertEqual(ov.wild_spans[-1][2:], ["big"])
        self.assertAlmostEqual(ov.wild_budget_used(), 15.0)         # the big span is not charged

    def test_a_kea_under_a_spent_budget_still_sounds_nothing(self):
        game = FakeGame([{"id": 5, "race": "BIRD_KEA", "hostile": False, "x": 100, "y": 100, "z": SURFACE}])
        ov = overseer(game)
        ov.load(fort(60))
        ov.wild_spans = [[40 * harness.DAY, 55 * harness.DAY]]
        self.assertEqual(self.look(ov, game, 60), [])

    def test_the_beast_leaving_lifts_the_alert(self):
        game = FakeGame([{"id": 5, "race": "CARNOTAURUS", "hostile": False, "x": 100, "y": 100, "z": SURFACE}])
        ov = overseer(game)
        self.assertEqual(self.look(ov, game, 60), [{"on": True}])
        game.units = [{"id": 5, "race": "CARNOTAURUS", "hostile": False, "x": 10, "y": 200, "z": SURFACE}]
        self.assertEqual(self.look(ov, game, 64, alert=True), [{"on": False}])

    def test_an_approach_during_the_rest_re_sounds_at_once(self):
        game = FakeGame([{"id": 5, "race": "CARNOTAURUS", "hostile": False, "x": 100, "y": 100, "z": SURFACE}])
        ov = overseer(game)
        self.assertEqual(self.look(ov, game, 60), [{"on": True}])
        self.assertEqual(self.look(ov, game, 71, alert=True), [{"on": False}])   # the 10-day cap
        self.assertTrue(ov.wild_resting())
        self.assertEqual(self.look(ov, game, 71.5), [])                        # by the wagon, 50 tiles off
        game.units = [{"id": 5, "race": "CARNOTAURUS", "hostile": False, "x": 144, "y": 44, "z": SURFACE}]
        self.assertEqual(self.look(ov, game, 72), [{"on": True}])               # 6 tiles from the mason
        self.assertFalse(ov.wild_resting())

    def test_no_shelter_no_alert(self):
        game = FakeGame([{"id": 5, "race": "CARNOTAURUS", "hostile": False, "x": 100, "y": 100, "z": SURFACE}])
        ov = overseer(game)
        resp = fort(60)
        resp["observation"]["burrows"]["list"] = []
        ov.load(resp)
        game.calls.clear()
        ov.mark_guard()
        self.assertEqual(game.tools("civilian_alert"), [])


def hatch(hid, site, locked=False, built=True):
    return {"id": hid, "kind": "hatch", "x": site["x"], "y": site["y"], "z": site["z"], "built": built,
            "locked": locked}


class Hatches(Quiet):
    def run_once(self, ov, game, day, breach=None, **kw):
        ov.load(fort(day, **kw))
        if breach is not None:   # set after the load: the dry test fort would release it there
            ov.breach, ov.hatch_id = breach
        game.calls.clear()
        ov.entrance_hatches()
        return game.calls

    def test_every_entrance_gets_a_hatch_and_covers_are_ordered_ahead(self):
        # cx hatch early: covers for every hatchless entrance plus HATCH_SPARE ahead, ordered at once, wood permitting
        game = FakeGame()
        ov = overseer(game)
        calls = self.run_once(ov, game, 20, sites=[E1, E2], logs=20,
                              doors={"list": [], "hatch_cover_items_free": 1, "door_items_free": 0})
        self.assertEqual(calls, [("build_door", {"kind": "hatch", "site": "E1"}),   # one item: one hatch
                                 ("add_order", {"recipe": "make_hatch_cover", "amount": 2})])   # E2 + 1 ahead
        calls = self.run_once(ov, game, 22, sites=[E1, E2], logs=20, orders=[{"recipe": "make_hatch_cover", "left": 2}],
                              doors={"list": [hatch(9, E1, built=False)], "hatch_cover_items_free": 0})
        self.assertEqual(calls, [])   # the order stands
        calls = self.run_once(ov, game, 24, sites=[E1, E2], logs=2,
                              doors={"list": [hatch(9, E1, built=False)], "hatch_cover_items_free": 0})
        self.assertEqual(calls, [])   # wood: the amount + HATCH_WOOD_FLOOR logs
        ov.hatch_ordered = harness.HATCH_ORDER_CAP
        calls = self.run_once(ov, game, 40, sites=[E1, E2], logs=20,
                              doors={"list": [hatch(9, E1, built=False)], "hatch_cover_items_free": 0})
        self.assertEqual(calls, [])   # the lifetime cap: no more logs into hatch covers

    def test_covers_are_ordered_on_day_0_and_during_an_alert(self):
        game = FakeGame()
        ov = overseer(game)
        calls = self.run_once(ov, game, 0, sites=[E1], logs=10, alert=True, inside=3,
                              doors={"list": [], "hatch_cover_items_free": 0})
        self.assertEqual(calls, [("add_order", {"recipe": "make_hatch_cover", "amount": 2})])
        # four entrances listed: no cover ahead of a fifth
        es = [dict(E1, id="E%d" % i, x=100 + i) for i in range(1, 5)]
        ov2 = overseer(FakeGame())
        ov2.load(fort(0, sites=es, logs=10, doors={"list": [], "hatch_cover_items_free": 4}))
        ov2.game.calls.clear()
        ov2.entrance_hatches()
        self.assertEqual([c for c in ov2.game.calls if c[0] == "add_order"], [])

    def test_alert_builds_only_where_no_marked_animal_is_near_the_stair(self):
        doors = {"list": [], "hatch_cover_items_free": 2}
        kea = {"id": 500, "race": "BIRD_KEA", "x": 110, "y": 101, "z": SURFACE}   # 10 tiles from E1, 23 from E2
        game = FakeGame(units=[kea])
        ov = overseer(game)
        far = dict(E2, x=140, y=140)   # 30+ tiles from the kea
        self.assertEqual([c for c in self.run_once(ov, game, 20, sites=[E1, far], alert=True, inside=3, doors=doors)
                          if c[0] == "build_door"], [("build_door", {"kind": "hatch", "site": "E2"})])
        game2 = FakeGame()
        ov2 = overseer(game2)
        self.assertEqual([c for c in self.run_once(ov2, game2, 20, sites=[E1], alert=True, inside=3, doors=doors)
                          if c[0] == "build_door"], [("build_door", {"kind": "hatch", "site": "E1"})])
        # a stair top inside a Shelter box takes its hatch with the kea near
        game3 = FakeGame(units=[kea])
        ov3 = overseer(game3)
        ov3.shelter_boxes["X"] = (99, 100, 101, 102, SURFACE)
        self.assertEqual([c for c in self.run_once(ov3, game3, 20, sites=[E1], alert=True, inside=3, doors=doors)
                          if c[0] == "build_door"], [("build_door", {"kind": "hatch", "site": "E1"})])

    def test_alert_builds_no_hatch_with_a_game_hostile_near_the_stair(self):
        # cx audit: an invader / any game-hostile unit (isDanger, not a marked species) near the stair top holds the
        # build as a marked animal does — the observation's threats list and the units query both count
        doors = {"list": [], "hatch_cover_items_free": 2}
        gob = {"id": 501, "race": "GOBLIN", "hostile": True, "x": 105, "y": 101, "z": SURFACE}
        game = FakeGame(units=[gob])
        ov = overseer(game)
        self.assertEqual([c for c in self.run_once(ov, game, 20, sites=[E1], alert=True, inside=3, doors=doors)
                          if c[0] == "build_door"], [])
        game2 = FakeGame()
        ov2 = overseer(game2)
        ov2.load(fort(20, sites=[E1], alert=True, inside=3, doors=doors))
        ov2.o["threats"] = {"visible_hostiles": 1, "hostiles": [dict(gob, invader=True)]}
        game2.calls.clear()
        ov2.entrance_hatches()
        self.assertEqual([c for c in game2.calls if c[0] == "build_door"], [])
        # a hostile far off (40 tiles) holds nothing
        game3 = FakeGame(units=[dict(gob, x=140, y=140)])
        ov3 = overseer(game3)
        self.assertEqual([c for c in self.run_once(ov3, game3, 20, sites=[E1], alert=True, inside=3, doors=doors)
                          if c[0] == "build_door"], [("build_door", {"kind": "hatch", "site": "E1"})])

    def test_no_build_in_a_breach_or_without_the_doors_section(self):
        game = FakeGame()
        ov = overseer(game)
        doors = {"list": [], "hatch_cover_items_free": 2}
        self.assertEqual(self.run_once(ov, game, 20, sites=[E1], doors=doors,
                                       breach=({"day": 19, "z": SURFACE}, None)), [])
        ov.breach = None
        self.assertEqual(self.run_once(ov, game, 20, sites=[E1]), [])

    def test_locked_only_with_every_citizen_inside_and_unlocked_when_the_alert_clears(self):
        game = FakeGame()
        ov = overseer(game)
        doors = {"list": [hatch(9, E1), hatch(10, E2)], "hatch_cover_items_free": 0}
        # hint std MY1-4 day 180: 17 of 18 inside, the administrator out at the map edge — never lock him out
        self.assertEqual(self.run_once(ov, game, 180, sites=[E1, E2], alert=True, inside=17, doors=doors), [])
        calls = self.run_once(ov, game, 180.5, sites=[E1, E2], alert=True, inside=18, doors=doors)
        self.assertEqual(calls, [("lock_door", {"locked": True, "door_id": 9}),
                                 ("lock_door", {"locked": True, "door_id": 10})])
        doors = {"list": [hatch(9, E1, locked=True), hatch(10, E2, locked=True)], "hatch_cover_items_free": 0}
        self.assertEqual(self.run_once(ov, game, 181, sites=[E1, E2], alert=True, inside=18, doors=doors), [])
        calls = self.run_once(ov, game, 185, sites=[E1, E2], alert=False, inside=18, doors=doors)
        self.assertEqual(calls, [("lock_door", {"locked": False, "door_id": 9}),
                                 ("lock_door", {"locked": False, "door_id": 10})])
        self.assertEqual(ov.alert_locked, set())

    def test_every_entrance_past_entrance_max_gets_its_hatch_and_the_lock(self):
        # cx entrances (hard OP1-2 on 7fa625d: 11 surface stairs, 7 hatchless; lock_skip "open:" on every alert day):
        # every listed entrance takes a hatch and a cover order, and the alert lock closes them all
        es = [dict(E1, id="E%d" % i, x=100 + i) for i in range(1, 7)]
        game = FakeGame()
        ov = overseer(game)
        calls = self.run_once(ov, game, 20, sites=es, logs=20, doors={"list": [], "hatch_cover_items_free": 6})
        self.assertEqual(sorted(a["site"] for t, a in calls if t == "build_door"), ["E%d" % i for i in range(1, 7)])
        calls = self.run_once(ov, game, 21, sites=es, logs=20,
                              doors={"list": [hatch(20 + i, e, built=False) for i, e in enumerate(es[:4])],
                                     "hatch_cover_items_free": 0})
        self.assertIn(("add_order", {"recipe": "make_hatch_cover", "amount": 2}), calls)   # E5, E6 (no spare: 6>4)
        doors = {"list": [hatch(20 + i, e) for i, e in enumerate(es)], "hatch_cover_items_free": 0}
        calls = self.run_once(ov, game, 30, sites=es, alert=True, inside=18, doors=doors)
        self.assertEqual(sorted(a["door_id"] for t, a in calls if t == "lock_door" and a.get("locked")),
                         list(range(20, 26)))

    def test_the_layer_digs_no_surface_stair_the_observation_could_not_list(self):
        # cx entrances: past ENTRANCE_LIST_MAX an entrance drops out of the E list and can take no hatch
        s9 = {"id": "S9", "kind": "S", "x": 120, "y": 120, "z": SURFACE}
        es = [dict(E1, id="E%d" % i, x=100 + i) for i in range(1, 9)]
        for n, code in ((0, None), (2, None), (7, None), (8, "entrance_hold")):
            game = FakeGame()
            ov = overseer(game)
            ov.load(fort(20, sites=es[:n] + [s9], doors={"list": [], "hatch_cover_items_free": 0}))
            ov.entrance_hatches()
            game.calls.clear()
            r = ov.act("stairs_surge", "dig_stairs", {"site": "S9", "z_bottom": 160})
            with self.subTest(entrances=n):
                self.assertEqual(r.get("error_code"), code)
                self.assertEqual(bool(game.calls), code is None)

    def test_someone_outside_opens_the_hatches_again(self):
        game = FakeGame()
        ov = overseer(game)
        doors = {"list": [hatch(9, E1)], "hatch_cover_items_free": 0}
        self.run_once(ov, game, 100, sites=[E1], alert=True, inside=18, doors=doors)
        doors = {"list": [hatch(9, E1, locked=True)], "hatch_cover_items_free": 0}
        # a migrant wave: 21 citizens, 18 inside — the newcomers must get in
        calls = self.run_once(ov, game, 101, sites=[E1], alert=True, inside=18, citizens=21, doors=doors)
        self.assertEqual(calls, [("lock_door", {"locked": False, "door_id": 9})])

    def test_a_flood_locked_hatch_is_held_during_the_breach_and_opened_after(self):
        # cx (audit 4): the flood's lock is keyed by its building id and released with the breach — before, nothing
        # ever unlocked it (cxe538c50 std OP1-0: hatches 33 and 39 locked to day 336; cxe60d4ce OP1-3: hatch 12
        # days 13-336). During a breach no alert lock closes the Shelter at all (audit 5).
        game = FakeGame()
        ov = overseer(game)
        ov.flood_locked = {9}
        doors = {"list": [hatch(9, E1, locked=True), hatch(10, E2)], "hatch_cover_items_free": 0}
        calls = self.run_once(ov, game, 100, sites=[E1, E2], alert=True, inside=18, doors=doors,
                              breach=({"day": 99, "z": SURFACE}, 9))
        self.assertEqual(calls, [])                      # 9 held (everyone inside), 10 not alert-locked into a flood
        ov.breach = None
        calls = self.run_once(ov, game, 104, sites=[E1, E2], alert=False, inside=2, doors=doors)
        self.assertEqual(calls, [("lock_door", {"locked": False, "door_id": 9})])   # the breach is over: opened
        self.assertEqual(ov.flood_locked, set())

    def test_a_flood_lock_with_citizens_outside_and_a_dry_column_is_opened(self):
        # cx: a flood lock shuts out whoever is outside; it stays only while water is at the hatch's column
        game = FakeGame()   # every map answer is dry
        ov = overseer(game)
        ov.flood_locked = {9}
        doors = {"list": [hatch(9, E1, locked=True)], "hatch_cover_items_free": 0}
        calls = self.run_once(ov, game, 100, sites=[E1], alert=False, inside=0, doors=doors,
                              breach=({"day": 99, "z": SURFACE}, 9))
        self.assertEqual(calls, [("lock_door", {"locked": False, "door_id": 9})])

    def test_no_alert_lock_during_a_breach(self):
        game = FakeGame()
        ov = overseer(game)
        doors = {"list": [hatch(10, E2)], "hatch_cover_items_free": 0}
        calls = self.run_once(ov, game, 100, sites=[E2], alert=True, inside=18, doors=doors,
                              breach=({"day": 99, "z": SURFACE}, None))
        self.assertEqual(calls, [])

    def test_a_breach_takes_over_an_alert_lock(self):
        game = FakeGame()
        ov = overseer(game)
        doors = {"list": [hatch(9, E1)], "hatch_cover_items_free": 0}
        self.run_once(ov, game, 100, sites=[E1], alert=True, inside=18, doors=doors)
        doors = {"list": [hatch(9, E1, locked=True)], "hatch_cover_items_free": 0}
        self.assertEqual(self.run_once(ov, game, 102, sites=[E1], alert=False, inside=2, doors=doors,
                                       breach=({"day": 101, "z": SURFACE}, 9)), [])
        self.assertEqual(ov.alert_locked, set())

    def test_the_entrance_is_remembered_when_its_site_drops_out(self):
        game = FakeGame()
        ov = overseer(game)
        self.run_once(ov, game, 20, sites=[E1], doors={"list": [], "hatch_cover_items_free": 0})
        doors = {"list": [hatch(9, E1)], "hatch_cover_items_free": 0}
        calls = self.run_once(ov, game, 30, sites=[], alert=True, inside=18, doors=doors)
        self.assertEqual(calls, [("lock_door", {"locked": True, "door_id": 9})])


class LiftUnlocksSamePass(Quiet):
    """cx (hint std OP1-4 on b796327): defend() lifted the alert on day 93 and day 120, but entrance_hatches() in
    the same pass still read the loaded civilian_alert True and kept hatch 19 locked; the unlock came on the next
    pass (day 100, day 125), after the model's 5-7 day advance, with every citizen idle in the Shelter. A lift this
    layer made is the state the rest of the pass reads, so the hatches it locked open in that same pass."""

    def test_the_cap_lift_opens_the_alert_hatches_in_the_same_pass(self):
        game = FakeGame()
        ov = overseer(game)
        doors = {"list": [hatch(19, E1)], "hatch_cover_items_free": 0}
        ov.load(fort(85, sites=[E1], alert=True, inside=18, doors=doors))
        ov.entrance_hatches()
        self.assertIn(("lock_door", {"locked": True, "door_id": 19}), game.calls)
        doors = {"list": [hatch(19, E1, locked=True)], "hatch_cover_items_free": 0}
        ov.load(fort(93, sites=[E1], alert=True, inside=18, doors=doors))   # nothing holds the alert any more
        game.calls.clear()
        ov.defend()
        ov.entrance_hatches()
        self.assertEqual(game.tools("civilian_alert"), [{"on": False}])
        self.assertIn(("lock_door", {"locked": False, "door_id": 19}), game.calls)
        self.assertEqual(ov.alert_locked, set())

    def test_no_lift_keeps_the_hatches_locked(self):
        # a big beast by the mason holds the alert: no lift, so the hatches stay locked
        # (every citizen is inside: the beast stands 15 tiles from the wagon, not by the mason)
        game = FakeGame([{"id": 5, "race": "CARNOTAURUS", "hostile": False, "x": 110, "y": 100, "z": SURFACE}])
        ov = overseer(game)
        doors = {"list": [hatch(19, E1)], "hatch_cover_items_free": 0}
        ov.load(fort(85, sites=[E1], alert=True, inside=18, doors=doors))
        ov.entrance_hatches()
        doors = {"list": [hatch(19, E1, locked=True)], "hatch_cover_items_free": 0}
        ov.load(fort(87, sites=[E1], alert=True, inside=18, doors=doors))
        ov.alert_since = ov.now - 2 * harness.DAY
        game.calls.clear()
        ov.defend()
        ov.entrance_hatches()
        self.assertEqual(game.tools("civilian_alert"), [])
        self.assertNotIn(("lock_door", {"locked": False, "door_id": 19}), game.calls)
        self.assertEqual(ov.alert_locked, {19})


if __name__ == "__main__":
    unittest.main()
