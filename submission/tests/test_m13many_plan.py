"""cx m13many: the MY1 plan on 16-17 citizen forts. Hint hard MY1-3 on 838106a (supply 0.512, 16 citizens): drink
reached o_brew_dry's floor on d181, which spent the plan's held plants one a day (pb 5 -> 1 over d181-202) and the d202
midshot had 1 of 3; and the layer's own o_brew_alloc one-shot of 5 (d76) brewed on after the hold armed on d88 (pb 7
-> 1). No game or network."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness  # noqa: E402
import test_harvest_hold as hh  # noqa: E402

LOOKS_838 = ((160, 27), (164, 21), (167, 19), (171, 16), (174, 13))   # drink, 16 citizens, pb 5


def dry_floor(game):
    adds = [a for t, a in game.calls if t == "add_order" and a.get("repeat") and
            {"stock": "drink", "below": 6} in a.get("when", [])]
    return [c["at_least"] for c in adds[-1]["when"] if c["stock"] == "plants_brewable"][0] if adds else None


class PreLift(hh.Base):
    def run_838(self, looks=LOOKS_838, pb=5, cit=16):
        ov, game = self.armed(cit=cit)
        ov.mig_start, ov.mig_waves = 9, 1
        for day, drink in looks:
            self.step(ov, day, cit=cit, drink=drink, pb=pb)
        ov.hold_supply()
        return ov, game

    def test_one_lift_now_and_the_rest_held_for_mid_f(self):
        ov, game = self.run_838()
        lifts = [a for t, a in game.calls if t == "add_order" and a == {"recipe": "brew_drink", "amount": 1}]
        self.assertEqual(len(lifts), 1)
        self.assertEqual(ov.f_dry_floor, 5)   # 4 held for mid-F: o_brew_dry may take only a plant over them

    def test_the_dry_standing_is_recut_to_leave_the_mid_f_plants(self):
        ov, game = self.run_838()
        # cx audit: the plan runs before the standing, so the first standing already leaves the mid-F plants
        self.assertEqual(dry_floor(game), ov.f_dry_floor)
        self.assertGreater(ov.f_dry_floor, 1)
        oid = ov.key_order["o_brew_dry"]
        dry = {"id": oid, "recipe": "brew_drink", "repeat": "daily", "left": 1, "total": 1, "jobs_in_progress": 0,
               "when": [{"item_type": "DRINK", "test": "LessThan", "value": 6, "stock": "drink"},
                        {"item_type": "PLANT", "flags": ["unrotten"], "reaction_product": "DRINK_MAT",
                         "test": "AtLeast", "value": 1, "stock": "plants_brewable"}]}
        n = len(game.calls)
        self.step(ov, 177, cit=16, drink=13, pb=4, orders=[dry])
        ov.hold_supply()
        self.assertIn(("cancel_order", {"order_id": oid}), game.calls[n:])
        # cx audit (hint hard MY1-3 on 642f253: o_brew_dry cut d197 / d211 and re-added a look later or never): the
        # cut standing is re-added at the plan's floor in the same pass
        later = [a for t, a in game.calls[n:] if t == "add_order" and a.get("repeat")
                 and {"stock": "drink", "below": 6} in a.get("when", [])]
        self.assertEqual(len(later), 1)
        self.assertEqual(dry_floor(game), ov.f_dry_floor)
        self.assertGreater(ov.f_dry_floor, 1)

    def test_split_score_prefers_the_lift_over_the_dribble(self):
        ov, _ = self.run_838()
        pre, mid = ov.f_split(5, 0.96, 202)
        self.assertEqual((pre, mid), (1, 4))
        dribble = [(x, 5) for x in (181, 185, 192, 199, 204)]
        self.assertGreater(ov.f_leg_score(0.96, [(176, 5), (202, 20)]), ov.f_leg_score(0.96, dribble) + 0.3)

    def test_a_stock_that_reaches_mid_f_gets_no_lift(self):
        # e33d381 std probe shape: drink 61 on d174, 17 citizens, pb 3: the plan's mid-F standing, no lift
        ov, game = self.run_838(looks=((160, 75), (164, 70), (167, 69), (171, 64), (174, 61)), pb=3, cit=17)
        self.assertIsNone(ov.f_dry_floor)
        self.assertNotIn(("add_order", {"recipe": "brew_drink", "amount": 1}), game.calls)


class LayerOneShot(hh.Base):
    def alloc(self, left):
        return {"id": 101, "recipe": "brew_drink", "repeat": None, "left": left, "total": 5, "active": True,
                "jobs_in_progress": 1, "when": []}

    def test_the_alloc_one_shot_is_cut_when_it_would_take_the_reserve(self):
        ov, game = self.armed(cit=16)
        ov.owned.add(101)
        ov.key_order["o_brew_alloc"] = 101
        self.step(ov, 88, cit=16, drink=110, pb=7, orders=[self.alloc(5)])
        ov.hold_supply()
        self.assertIn(("cancel_order", {"order_id": 101}), game.calls)

    def test_a_one_shot_over_the_reserve_stays(self):
        ov, game = self.armed(cit=16)
        ov.owned.add(101)
        ov.key_order["o_brew_alloc"] = 101
        self.step(ov, 88, cit=16, drink=110, pb=14, orders=[self.alloc(2)])
        ov.hold_supply()
        self.assertNotIn(("cancel_order", {"order_id": 101}), game.calls)


if __name__ == "__main__":
    unittest.main()


class CaravanRecycle(unittest.TestCase):
    """838106a hard MY1-3: caravan d44-76; d58-81 the harvest stood as 11 brewable plants (cave wheat 5, pig tail 6),
    no fort seed free, 4 empty plots (36 tiles), the merchants' quarry bush / sweet pod seeds in the stocks."""

    def setUp(self):
        out = redirect_stdout(io.StringIO())
        out.__enter__()
        self.addCleanup(out.__exit__, None, None, None)

    def run_it(self, caravan=True, merchants=40, merchant_plump=0, harvest=(5, 6), plump_seeds=None):
        import test_seed_recycle as sr
        aut = ["summer", "autumn"]
        own = {"cave wheat": {"n": 5, "seasons": aut}, "pig tail": {"n": 5, "seasons": aut},
               "sweet pod": {"n": 2, "seasons": ["spring", "summer"]}}
        allyear = ["spring", "summer", "autumn", "winter"]
        if plump_seeds is not None:
            own["plump helmet"] = {"n": plump_seeds, "seasons": allyear}
        game = sr.FakeGame()
        ov = harness.Overseer(game, days=216)
        ov.load(sr.resp(41, cit=9, drink=61, food=90, plump=0, seeds=own, plots=(0, 0, 5, 5)))
        seeds = {"cave wheat": {"n": 0, "seasons": aut}, "pig tail": {"n": 0, "seasons": aut},
                 "sweet pod": {"n": 22, "seasons": ["spring", "summer"]},
                 "quarry bush": {"n": merchants, "seasons": ["spring", "summer", "autumn"]}}
        if plump_seeds is not None:
            seeds["plump helmet"] = {"n": plump_seeds, "seasons": allyear}
        other = {"cave wheat": {"n": harvest[0], "brewable": True, "cookable": False},
                 "pig tail": {"n": harvest[1], "brewable": True, "cookable": False}}
        ov.caravan_active = caravan
        # cx audit: the stay's first look (d45): the merchants' goods stand, the harvest not yet in
        ov.load(sr.resp(45, cit=9, drink=128, food=322, plump=merchant_plump, seeds=seeds, plots=(0, 0, 0, 0)))
        ov.caravan_active = caravan
        ov.load(sr.resp(60, cit=9, drink=128, food=322, plump=merchant_plump, seeds=seeds, plots=(0, 0, 0, 0),
                        other=other))
        ov.count = 0
        ov.seed_recycle()
        return [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"]

    def test_the_merchants_plants_are_not_brewed(self):
        # cx audit (hint MY1-4/MY1-1/OP1 records: plump helmet +19..+105 at the caravan's arrival): the recycle
        # sizes on the fort's own plants
        self.assertEqual(self.run_it(merchant_plump=45), self.run_it(merchant_plump=0))
        # the fort's own 6 plants are the plant floor: nothing to brew, whatever the merchants show
        self.assertEqual(self.run_it(harvest=(3, 3)), [])
        self.assertEqual(self.run_it(merchant_plump=45, harvest=(3, 3)), [])
        # a kind the fort itself sows (MY1-4: plump helmet, the merchants bring 40-100 of it)
        self.assertEqual(self.run_it(merchant_plump=45, harvest=(3, 3), plump_seeds=0),
                         self.run_it(merchant_plump=0, harvest=(3, 3), plump_seeds=0))

    def test_the_arrival_look_is_not_taken_as_the_fort_s_own(self):
        # cx audit: the look the arrival announcement first shows on already holds the merchants' goods; the own-
        # stock snapshot is not taken from it (the caravan state is read before the snapshot)
        import test_seed_recycle as sr

        class EvGame(sr.FakeGame):
            evs = []

            def events(self, since_tick=0):
                return {"events": list(self.evs)}
        game = EvGame()
        ov = harness.Overseer(game, days=216)
        own = {"cave wheat": {"n": 5, "seasons": ["summer", "autumn"]}}
        ov.load(sr.resp(41, cit=9, seeds=own, plump=0))
        self.assertFalse(ov.caravan_active)
        game.evs = [{"id": 1, "type": "CARAVAN_ARRIVAL", "tick": 45 * harness.DAY - 10}]
        ov.load(sr.resp(45, cit=9, seeds=dict(own, **{"quarry bush": {"n": 40, "seasons": ["spring"]}}), plump=45))
        self.assertTrue(ov.caravan_active)
        self.assertEqual(ov.own_seeds, {"cave wheat": 5})
        self.assertEqual(ov.merchant_plants, {"plump helmet": 45})

    def test_the_autumn_harvest_goes_back_to_seed_during_the_caravan(self):
        brews = self.run_it()
        self.assertTrue(brews)
        self.assertGreaterEqual(brews[0]["amount"], 5)   # 11 standing less the plant floor (6) the layer keeps

    def test_the_merchants_seeds_do_not_count_as_the_fort_s(self):
        # counted, their 40 plantable quarry bush seeds would fill the 36 tiles and stop the recycle
        self.assertEqual(self.run_it(caravan=True, merchants=40), self.run_it(caravan=True, merchants=0))


class MidShotTiming(hh.Base):
    """std MY1-3 probe on 657e3d0 (17 citizens, supply 0.735): looks d177/191/198/205; on d198 the plan wanted 5
    brews landing d202 with drink 9 and placed nothing, the next look was d205, the batch landed d207-211 and drink
    read 0 on d207."""

    def run_looks(self, looks):
        ov, game = self.armed(cit=17)
        ov.mig_start, ov.mig_waves = 9, 1
        for day, drink in looks:
            self.step(ov, day, cit=17, drink=drink, pb=5)
            ov.hold_supply()
        return ov, [a for t, a in game.calls if t == "add_order" and a.get("recipe") == "brew_drink"
                    and not a.get("repeat")]

    def test_the_batch_goes_on_the_last_look_before_its_start(self):
        ov, shots = self.run_looks(((177, 26), (184, 22), (191, 16), (198, 9)))
        self.assertEqual(ov.f_load_gap(), 7)
        self.assertTrue(any(a["amount"] >= 4 for a in shots), shots)

    def test_not_a_look_earlier(self):
        _, shots = self.run_looks(((177, 26), (184, 22), (191, 16)))
        self.assertFalse(any(a["amount"] >= 4 for a in shots), shots)


class ShotDue2(hh.Base):
    """e20ce56 std MY1-3 probe (17 citizens): looks d179/186/190/197/204; on d197 f_plan wanted 3 brews landing d202
    and nothing went out; the d204 midshot (5) landed d208-212, 6 days late."""

    def test_d197_sends_the_batch(self):
        ov, _ = self.armed(cit=17)
        ov.f_rec = [(183, 66, 92), (190, 65, 85), (197, 64, 84)]   # the plan's looks, 7 days apart
        self.assertEqual(ov.f_load_gap(), 7)
        self.assertTrue(ov.f_shot_due(197, 202, 3))     # start d200; next look d204 > d200
        self.assertTrue(ov.f_shot_due(197, 202, 5))

    def test_a_look_due_on_the_start_day_is_waited_for(self):
        ov, _ = self.armed(cit=17)
        ov.f_rec = [(180, 70, 99), (187, 66, 92), (194, 56, 90)]
        self.assertFalse(ov.f_shot_due(194, 202, 2))    # start d201 = the next look: it starts on time then

    def test_d179_waits(self):
        ov, _ = self.armed(cit=17)
        ov.f_rec = [(165, 80, 99), (172, 77, 99), (179, 74, 92)]
        self.assertFalse(ov.f_shot_due(179, 202, 4))    # start d200; next look d186

    def test_a_late_start_is_not_waited_for_at_any_batch_size(self):
        ov, _ = self.armed(cit=17)
        ov.f_rec = [(183, 66, 92), (190, 65, 85), (197, 64, 84)]
        for k in range(1, 9):
            start = 202 - (k + 1) // 2
            due = ov.f_shot_due(197, 202, k)
            self.assertTrue(due or 197 + 7 <= start, k)  # waiting never lets the next look pass the start
