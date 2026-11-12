"""cx grazer cull and shaft guard (hint MY1-4, 2026-11-11). (1) From dba5220 on the meeting area stands below the
surface and the fortress's tame animals gather there (std c44c96b: all at z168 days 112-147); the grazers starved in
it (std alpaca day 121.0, donkey 136.3; hard d769d66 donkey foal 121.8, alpaca 141.1) and the fort's median stress
went from -17.5k to +13-17k after them. A tame unowned grazer below the surface is now slaughtered while it lives.
(2) Every kea fight in the Shelter came down the open E1 shaft to its foot while the alert was on, and the foot guard
never stood: it waited for members carrying a weapon, and off duty nobody carries one. The guard now counts the
members known armable, answers a kea anywhere within MARK_RANGE, holds through WILD_REST_DAYS after a lift, and a
lift waits while a marked animal is at the shaft. No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_danger_marks import FakeGame, Quiet  # noqa: E402
from test_rescue_station import Look, my14, CHILD_IN, MINER, KEA_OVER_FORT  # noqa: E402
from overseer import harness  # noqa: E402


class AnimalGame(FakeGame):
    """units queries: kind=animals answers the fort's own animals, every other kind the wild ones."""
    def __init__(self, animals=(), others=()):
        super().__init__(others)
        self.animals = [dict(x) for x in animals]

    def query(self, *a, **kw):
        self.queries += 1
        if kw.get("kind") == "animals":
            return {"result": {"units": [dict(x) for x in self.animals]}}
        return {"result": {"units": list(self.units)}}


# the std c44c96b animals query on day 119 (harness-4.api.jsonl), every one at the meeting area on z168
def beast(i, race, adult=True, z=168, **kw):
    return dict({"id": i, "race": race, "tame": True, "adult": adult, "female": True, "marked_for_slaughter": False,
                 "x": 103, "y": 101, "z": z}, **kw)


DAY119 = [beast(104, "DOG", adult=False, z=170), beast(105, "CAT", z=169), beast(106, "CAT"),
          beast(108, "BIRD_GOOSE"), beast(111, "HORSE"), beast(302, "BIRD_TURKEY", adult=False),
          beast(303, "MULE"), beast(233, "DONKEY", adult=False), beast(234, "ALPACA"),
          beast(237, "BIRD_PEAFOWL_BLUE", adult=False)]


def fort119(day=119):
    r = my14(day, [CHILD_IN, MINER], alert=False, squads=())
    r["observation"]["workshops"] = [{"type": "Butchers"}]
    return r


class Races(unittest.TestCase):
    def test_the_starved_races_of_the_records_are_grazers(self):
        for race in ("HORSE", "REINDEER", "ALPACA", "DONKEY", "CAMEL_2_HUMP", "WATER_BUFFALO", "LLAMA", "RABBIT",
                     "CAVY", "YAK", "GOAT", "MULE", "COW"):
            self.assertTrue(harness.grazer_race(race), race)

    def test_dogs_cats_and_fowl_are_not(self):
        for race in ("DOG", "CAT", "BIRD_GOOSE", "BIRD_TURKEY", "BIRD_PEAFOWL_BLUE", "BIRD_KEA", "GUINEAPIG", None):
            self.assertFalse(harness.grazer_race(race), race)


class Cull(Quiet):
    def setUp(self):
        super().setUp()
        self.game = AnimalGame(DAY119)
        self.ov = harness.Overseer(self.game, days=216)
        self.ov.load(fort119())
        self.ov.count = 0
        self.game.calls.clear()

    def marked(self):
        return [a["unit_id"] for t, a in self.game.calls if t == "slaughter"]

    def test_the_grazers_below_the_surface_are_marked_adults_first(self):
        self.ov.grazer_cull()
        self.assertEqual(self.marked(), [111, 234])   # horse and alpaca (adults, by id); no dog, cat or bird

    def test_once_a_day_then_the_rest(self):
        self.ov.grazer_cull()
        self.ov.grazer_cull()                          # same day: nothing more
        self.assertEqual(len(self.marked()), 2)
        for a in self.game.animals:
            if a["id"] in (111, 234):
                a["marked_for_slaughter"] = True
        self.ov.load(fort119(120))
        self.ov.count = 0
        self.ov.grazer_cull()
        self.assertEqual(self.marked(), [111, 234, 303, 233])   # the mule, then the young donkey

    def test_a_grazer_on_the_grass_or_an_owned_pet_is_left(self):
        self.game.animals = [beast(1, "HORSE", z=169), beast(2, "ALPACA", z=170),
                             beast(3, "DONKEY", pet_owner_id=95)]
        self.ov.grazer_cull()
        self.assertEqual(self.marked(), [])

    def test_no_butchers_builds_one(self):
        r = fort119()
        r["observation"]["workshops"] = []
        self.ov.load(r)
        self.ov.last.pop("grazer_cull", None)
        built = []
        self.ov.build = lambda wtype, *a, **kw: built.append(wtype)
        self.ov.grazer_cull()
        self.assertEqual(built, ["Butchers"])

    def test_the_food_butcher_takes_a_grazer_before_a_dog(self):
        self.ov.butcher(for_food=False)
        self.assertEqual(self.marked(), [111])


ARMABLE = {"id": 0, "armed": 0, "uniform": "weapon+armor", "orders": [],
           "members": [{"id": i, "weapon_assigned": True} for i in range(4)]}
UNKNOWN = {"id": 0, "armed": 0, "uniform": "weapon+armor", "orders": [], "members": [{"id": i} for i in range(4)]}
KEA_FAR = dict(KEA_OVER_FORT, x=140, y=140, z=172)   # 39-45 tiles out: past WILD_NEAR_TILES, inside MARK_RANGE
FOOT = ("squad_order", {"order": "station", "x": 100, "y": 101, "z": 169})   # SHAFT_GUARD_TOP: the stair top


class ShaftGuard(Look):
    def test_an_off_duty_armable_squad_goes_to_the_foot_when_the_alert_sounds(self):
        # c44c96b std day 156: armed 0 off duty, all four weapon_assigned. cx muster clear: with the kea 4 tiles from
        # E1 the unarmed members would fetch their uniform past it, so the foot waits for it to be farther than
        # MUSTER_CLEAR_TILES (or for MARK_RESCUE_ARMED members armed); 40 tiles out it goes (test below)
        game = FakeGame([KEA_OVER_FORT])
        ov = harness.Overseer(game, days=216)
        calls = self.look(ov, game, my14(156, [CHILD_IN, MINER], squads=(ARMABLE,)))
        self.assertNotIn(FOOT, calls)
        game.units = [dict(KEA_FAR)]
        calls = self.look(ov, game, my14(156.5, [CHILD_IN, MINER], squads=(ARMABLE,)))
        self.assertIn(FOOT, calls)

    def test_a_squad_nothing_is_known_of_is_not_sent_to_the_foot(self):
        game = FakeGame([KEA_OVER_FORT])
        ov = harness.Overseer(game, days=216)
        calls = self.look(ov, game, my14(156, [CHILD_IN, MINER], squads=(UNKNOWN,)))
        self.assertNotIn(FOOT, calls)

    def test_a_kea_inside_mark_range_holds_the_foot_too(self):
        game = FakeGame([KEA_FAR])
        ov = harness.Overseer(game, days=216)
        calls = self.look(ov, game, my14(160, [CHILD_IN, MINER], squads=(ARMABLE,)))   # the alert on
        self.assertIn(FOOT, calls)

    def test_the_guard_holds_after_a_lift_then_not(self):
        game = FakeGame([KEA_FAR])
        ov = harness.Overseer(game, days=216)
        ov.wild_rest_until = 10 ** 9   # resting: no alert sounds in these passes
        self.look(ov, game, my14(160, [CHILD_IN, MINER], squads=(ARMABLE,)))   # alert seen on day 160
        calls = self.look(ov, game, my14(161, [CHILD_IN, MINER], alert=False, squads=(ARMABLE,)))
        self.assertIn(FOOT, calls)
        ov2 = harness.Overseer(game, days=216)
        ov2.wild_rest_until = 10 ** 9
        calls = self.look(ov2, game, my14(161, [CHILD_IN, MINER], alert=False, squads=(ARMABLE,)))
        self.assertNotIn(FOOT, calls)   # no alert seen at all: no guard

    def test_a_kea_at_the_shaft_keeps_the_lift_waiting(self):
        at_shaft = dict(KEA_OVER_FORT, x=104, y=96, z=169)
        far = [dict(CHILD_IN, x=60, y=40, z=168), dict(MINER, x=62, y=40, z=168)]   # nobody near the shaft
        game = FakeGame([at_shaft])
        ov = harness.Overseer(game, days=216)
        ov.load(my14(150, far, squads=()))
        self.assertEqual(ov.mark_pressing(), ["kea"])
        game.units = [dict(at_shaft, x=125, y=125)]
        ov.load(my14(151, far, squads=()))
        self.assertEqual(ov.mark_pressing(), [])
        ov.load(my14(152, far, squads=(), sites=(dict(harness_E1_hatched()),)))
        game.units = [at_shaft]
        self.assertEqual(ov.mark_pressing(), [])   # a hatched entrance is no open shaft


def harness_E1_hatched():
    from test_rescue_station import E1
    return dict(E1, building=False)


if __name__ == "__main__":
    unittest.main()
