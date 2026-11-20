"""d73: (a) the standing wood-crafts order is cancelled once created wealth reaches the target (yukonautominer's
11ff6d2a); (b) during the feast a fort whose drink is under a year's worth brews the plants the endgame order holds back,
once the meat is in; (c) a mood's workshop whose construction has stood suspended for three days is built again
(yukonautominer's 9f1e1d32)."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import StubGame, overseer, resp  # noqa: E402
from overseer import harness as H  # noqa: E402
from overseer.openplay import DRINK_NEED, FEAST_MEAT  # noqa: E402

CRAFTS = {"id": 41, "job": "MakeCrafts", "repeat": "daily"}
OTHER = {"id": 42, "job": "MakeCrafts", "repeat": "daily"}


class Quiet(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)


class CraftStop(Quiet):
    def fort(self, wealth, orders=(CRAFTS, OTHER), own=(41,)):
        r = resp(200, 135, food=60, orders=orders,
                 workshops=("Carpenters", "Still", "Kitchen", "Butchers", "Craftsdwarfs"))
        r["observation"]["wealth"] = {"created": wealth}
        ov, g = overseer(r)
        ov.craft_ids = set(own)
        return ov, g

    def test_at_the_target_only_this_layers_order_is_cancelled(self):
        ov, g = self.fort(H.PROG_WEALTH)
        ov.progression_push()
        self.assertEqual(g.tools("cancel_order"), [{"order_id": 41}])
        self.assertEqual(g.tools("add_manager_order"), [])

    def test_an_accepted_cancel_is_not_repeated_while_the_listing_still_shows_the_order(self):
        ov, g = self.fort(H.PROG_WEALTH)
        for _ in range(5):
            ov.progression_push()
            ov.now += 2 * H.DAY
        self.assertEqual(g.tools("cancel_order"), [{"order_id": 41}])

    def test_a_refused_cancel_is_asked_again_a_few_times(self):
        ov, g = self.fort(H.PROG_WEALTH)
        g.refuse = {("cancel_order", 41)}
        for _ in range(9):
            ov.progression_push()
            ov.now += 2 * H.DAY
        self.assertEqual(len(g.tools("cancel_order")), 4)

    def test_below_the_target_the_order_stays(self):
        ov, g = self.fort(H.PROG_WEALTH - 1)
        ov.progression_push()
        self.assertEqual(g.calls, [])

    def test_below_the_target_with_no_order_it_is_added(self):
        ov, g = self.fort(3000, orders=(OTHER,), own=())
        ov.progression_push()
        self.assertEqual([a["job"] for a in g.tools("add_manager_order")], ["MakeCrafts"])

    def test_a_cancelled_order_is_not_asked_again_once_gone(self):
        ov, g = self.fort(6000, orders=(OTHER,))
        ov.progression_push()
        self.assertEqual(g.calls, [])

    def test_a_lab_task_is_untouched(self):
        r = resp(20, 30, food=60, orders=(CRAFTS,))
        r["observation"]["wealth"] = {"created": 9000}
        r["hands_off_in_days"] = 9
        g = StubGame()
        ov = H.Overseer(g, goal="Run the fortress", days=60)
        ov.set_task({"goal": "Keep the fort supplied.", "hands_off": {"from_day": 39}})
        ov.load(r)
        ov.count = 0
        ov.craft_ids = {41}
        ov.progression_push()
        self.assertEqual(g.calls, [])


class FeastBrew(Quiet):
    def fort(self, drink, cit=22, food=70, plants=7, brewable=7, barrels=5, orders=(), days_left=10):
        r = resp(days_left, 336 - days_left - 1, food=food, drink=drink, cit=cit, plants=plants, orders=orders)
        r["observation"]["stocks"].update(plants_brewable=brewable, barrels_empty=barrels)
        return overseer(r, herd=[])

    def brews(self, g):
        return [a for a in g.tools("add_order") if a.get("recipe") == "brew_drink"]

    def test_a_big_fort_short_of_a_years_drink_brews_the_plants(self):
        ov, g = self.fort(333)                       # 22 citizens: a year's worth is 440
        ov.feast()
        self.assertEqual(self.brews(g), [{"recipe": "brew_drink", "amount": 6}])

    def test_no_more_than_the_shortfall_or_the_plants(self):
        ov, g = self.fort(DRINK_NEED * 22 - 8)       # two batches cover it
        ov.feast()
        self.assertEqual(self.brews(g), [{"recipe": "brew_drink", "amount": 2}])
        ov, g = self.fort(333, plants=3, brewable=3)
        ov.feast()
        self.assertEqual(self.brews(g), [{"recipe": "brew_drink", "amount": 3}])

    def test_enough_drink_brews_nothing(self):
        ov, g = self.fort(DRINK_NEED * 22)
        ov.feast()
        self.assertEqual(self.brews(g), [])
        ov, g = self.fort(333, cit=14)               # a small fort: 280 is its year
        ov.feast()
        self.assertEqual(self.brews(g), [])

    def test_before_the_meat_is_in_the_plants_stay_food(self):
        ov, g = self.fort(333, food=FEAST_MEAT * 22 + 7 - 1, plants=7)
        ov.feast()
        self.assertEqual(self.brews(g), [])

    def test_no_plant_or_no_barrel_brews_nothing(self):
        for kw in ({"brewable": 0}, {"barrels": 0}):
            ov, g = self.fort(333, **kw)
            ov.feast()
            self.assertEqual(self.brews(g), [])

    def test_one_order_at_a_time(self):
        pending = {"id": 9, "recipe": "brew_drink", "left": 4}
        ov, g = self.fort(333, orders=(pending,))
        ov.feast()
        self.assertEqual(self.brews(g), [])

    def test_only_in_the_feast(self):
        ov, g = self.fort(333, days_left=20)
        ov.provision()
        self.assertEqual(self.brews(g), [])
        ov, g = self.fort(333, days_left=12)
        ov.provision()
        self.assertEqual(len(self.brews(g)), 1)


class MoodWorkshop(Quiet):
    def fort(self, day, built=False, suspended=True, claimed=None):
        r = resp(30, day, food=60, workshops=("Carpenters", "Still", "Kitchen"))
        o = r["observation"]
        job = {"job": "ConstructBuilding", "suspended": suspended}
        o["workshops"].append({"id": 6, "type": "Craftsdwarfs", "built": built, "x": 1, "y": 2, "z": 3,
                               "job_details": [] if built else [job]})
        o["map"]["sites"] = [{"id": "W1", "kind": "W"}, {"id": "W2", "kind": "W"}]
        mood = {"unit_id": 9, "mood": "Fey", "skill": "WOODCRAFT"}
        if claimed is not None:
            mood["claimed_building_id"] = claimed
        o["moods"] = [mood]
        return r

    def built(self, g):
        return [a.get("type") for a in g.tools("build_workshop")]

    def test_a_workshop_suspended_for_three_days_is_built_again(self):
        ov, g = overseer(self.fort(1))
        ov.mood()
        self.assertEqual(self.built(g), [])              # first seen suspended: the clock starts
        ov.load(self.fort(1 + H.STUCK_DAYS))
        ov.count = 0
        ov.mood()
        self.assertEqual(self.built(g), ["Craftsdwarfs"])

    def test_a_built_or_working_one_is_left_alone(self):
        for kw in ({"built": True}, {"suspended": False}):
            ov, g = overseer(self.fort(1, **kw))
            ov.load(self.fort(9, **kw))
            ov.count = 0
            ov.mood()
            self.assertEqual(self.built(g), [])

    def test_a_claimed_mood_asks_for_nothing(self):
        ov, g = overseer(self.fort(1))
        ov.load(self.fort(9, claimed=6))
        ov.count = 0
        ov.mood()
        self.assertEqual(self.built(g), [])


if __name__ == "__main__":
    unittest.main()
