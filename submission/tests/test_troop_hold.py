"""cx regressions: the wildlife troop hold (hint std MY1-4 on 68bd4c7, O 61.0, survival 0.8). A gray langur troop
(hostile False) reached the fort on day 171 inside a 167->173 model advance; the alert sounded at the first look
(day 173: 6 langur cancels, langurs at 27/64/56 tiles from the wagon) and was lifted at the next (day 180) after
WILD_ALERT_DAYS although the troop had brawled with a citizen on day 178. The alert this layer sounded now holds while
one of its animals stands within WILD_NEAR_TILES of the wagon (the 10-day cap still lifts it, then WILD_REST_DAYS pass),
and an animal that sounded it re-sounds it when it is back near the wagon. No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

WAGON = {"present": True, "x": 95, "y": 95, "z": 169}
NEAR = [{"id": 31, "race": "GRAY_LANGUR", "hostile": False, "x": 122, "y": 104, "z": 169},   # the record's day 173
        {"id": 32, "race": "GRAY_LANGUR", "hostile": False, "x": 159, "y": 55, "z": 169},
        {"id": 33, "race": "GRAY_LANGUR", "hostile": False, "x": 39, "y": 102, "z": 169},
        {"id": 40, "race": "KANGAROO", "hostile": False, "x": 100, "y": 100, "z": 169}]
FAR = [dict(u, x=95 + 60) for u in NEAR[:3]]   # every langur 60 tiles east of the wagon
LANGUR_CANCELS = ["Urist %d cancels Store item in stockpile: Interrupted by a gray langur." % i for i in range(6)]


class FakeGame:
    def __init__(self, units=()):
        self.calls, self.units, self.queries = [], list(units), 0

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        return {"ok": True, "result": {"civilian_alert": args.get("on")}}

    def query(self, *a, **kw):
        if kw.get("kind") != "citizens":   # cx squad pick: create_squad's member query is not a look's query
            self.queries += 1
        return {"result": {"units": list(self.units)}}


# the record's day-178 brawl (a citizen and the troop), the ongoing evidence that keeps the hold (CX_REVIEW P1-4)
BRAWL = ["The gray langur bites the planter in the left hand, bruising the muscle!"]
PLANTER = {"id": 9, "profession": "Planter", "x": 140, "y": 60, "z": 169}
AWAY = {"id": 9, "profession": "Planter", "x": 20, "y": 20, "z": 169}   # the default citizen: far from every animal


def fort(day, alert=False, cancels=(), wagon=WAGON, squads=(), events=(), dwarves=(AWAY,)):
    obs = {"date": {"abs_tick": day * harness.DAY}, "administrators": {"citizens": 18},
           "stocks": {"drink": 500, "food_edible": 150}, "map": {"sites": [], "wagon": dict(wagon)},
           "recent_cancellations": list(cancels), "military": {"squads": list(squads)},
           "recent_events": list(events), "dwarves": [dict(x) for x in dwarves],
           "threats": {"visible_hostiles": 0, "hostiles": []},
           "burrows": {"civilian_alert": alert, "list": [{"id": 0, "civ_alert_burrow": True}]}}
    return {"tick": day * harness.DAY, "day": day, "observation": obs, "days_left": 216 - day}


class TroopHold(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def look(self, ov, game, day, **kw):
        """One layer pass's alert steps, in plan()'s order."""
        ov.load(fort(day, **kw))
        ov.count = 0
        game.calls.clear()
        ov.defend()
        ov.wildlife_response()
        return [a["on"] for t, a in game.calls if t == "civilian_alert"]

    def sounded(self, units=NEAR):
        game = FakeGame(units)
        ov = harness.Overseer(game, days=216)
        self.assertEqual(self.look(ov, game, 173, cancels=LANGUR_CANCELS), [True])
        self.assertEqual(ov.wild_watched(), ["gray langur"])
        return ov, game

    def test_the_troop_near_the_wagon_keeps_the_alert_on(self):
        ov, game = self.sounded()
        self.look(ov, game, 178, alert=True, events=BRAWL)                  # the record's brawl with a citizen
        self.assertEqual(self.look(ov, game, 180, alert=True, events=BRAWL), [])   # the record lifted it here
        self.assertIsNotNone(ov.wild_alert_since)

    def test_near_without_evidence_lifts_it(self):
        # CX_REVIEW P1-4: a resident troop by the wagon, no fight, no interrupt, no approach — the civilians come out
        ov, game = self.sounded()
        self.assertEqual(self.look(ov, game, 180, alert=True), [False])
        self.assertIsNotNone(ov.wild_rest_until)                            # a rest follows every wildlife lift
        self.assertEqual(self.look(ov, game, 181, alert=False), [])

    def test_a_stale_report_is_not_evidence(self):
        ov, game = self.sounded()
        self.look(ov, game, 174, alert=True, events=BRAWL)
        # the same report text still in recent_events 6 days later: first seen on 174, past WILD_EVIDENCE_DAYS
        self.assertEqual(self.look(ov, game, 180, alert=True, events=BRAWL), [False])

    def test_a_troop_closing_on_a_citizen_keeps_it(self):
        ov, game = self.sounded()
        self.assertEqual(self.look(ov, game, 180, alert=True, dwarves=[dict(PLANTER, x=125, y=106)]), [])

    def test_the_alert_budget_lifts_it_and_bars_a_new_one(self):
        ov, game = self.sounded()
        for day in range(176, 173 + harness.WILD_BUDGET_DAYS):
            ov.alert_since = day * harness.DAY   # keep the 10-day cap out of the way: the budget alone
            ov.access_tick = day * harness.DAY   # ... and the drink-access cap (ACCESS_CAP_DAYS) too
            self.assertEqual(self.look(ov, game, day, alert=True, events=["The gray langur bites the planter in the hand, wound %d!" % day]),
                             [])
        day = 173 + harness.WILD_BUDGET_DAYS + 1
        ov.alert_since = day * harness.DAY
        ov.access_tick = day * harness.DAY
        # cx BUDGET FIGHT: no fight for 2 days (the last report first showed on day 186): the spent budget lifts it
        self.assertEqual(self.look(ov, game, day, alert=True), [False])
        ov.wild_rest_until = None
        self.assertEqual(self.look(ov, game, day + 3, alert=False, cancels=LANGUR_CANCELS), [])   # still inside the window
        self.assertLessEqual(ov.wild_budget_used(), harness.WILD_BUDGET_DAYS + 1)

    def test_a_fresh_fight_sounds_it_despite_a_spent_budget_for_a_day(self):
        # cx BUDGET FIGHT (642f253 std MY1-3: a resident badger spent the budget, then fought the manager on d110.8)
        ov, game = self.sounded()
        for day in range(176, 173 + harness.WILD_BUDGET_DAYS):
            ov.alert_since = day * harness.DAY
            ov.access_tick = day * harness.DAY
            self.look(ov, game, day, alert=True, events=["The gray langur bites the planter in the hand, wound %d!" % day])
        day = 173 + harness.WILD_BUDGET_DAYS + 1
        ov.alert_since = ov.access_tick = day * harness.DAY
        self.assertEqual(self.look(ov, game, day, alert=True), [False])
        self.assertFalse(ov.wild_budget_left())
        ov.wild_rest_until = None
        self.assertEqual(self.look(ov, game, day + 3, alert=False, cancels=LANGUR_CANCELS,
                                   events=["The gray langur bites the planter in the foot!"]), [True])   # the fight: sounded
        ov.alert_since = ov.access_tick = (day + 3) * harness.DAY
        self.assertEqual(self.look(ov, game, day + 4, alert=True, events=["The gray langur bites the planter in the foot!"]), [])
        # two days after the fight, no new one, the budget still spent: it lifts
        self.assertEqual(self.look(ov, game, day + 5, alert=True, events=["The gray langur bites the planter in the foot!"]), [False])

    def test_budget_fight_zero_keeps_the_old_bar(self):
        old = harness.BUDGET_FIGHT_DAYS
        harness.BUDGET_FIGHT_DAYS = 0
        try:
            ov, game = self.sounded()
            for day in range(176, 173 + harness.WILD_BUDGET_DAYS):
                ov.alert_since = ov.access_tick = day * harness.DAY
                self.look(ov, game, day, alert=True, events=["The gray langur bites the planter, wound %d!" % day])
            day = 173 + harness.WILD_BUDGET_DAYS + 1
            ov.alert_since = ov.access_tick = day * harness.DAY
            self.assertEqual(self.look(ov, game, day, alert=True, events=["The gray langur bites the planter!"]), [False])
            ov.wild_rest_until = None
            self.assertEqual(self.look(ov, game, day + 3, alert=False, cancels=LANGUR_CANCELS,
                                       events=["The gray langur bites the planter in the foot!"]), [])
        finally:
            harness.BUDGET_FIGHT_DAYS = old

    def test_the_troop_gone_lifts_it_after_the_short_hold(self):
        ov, game = self.sounded()
        self.assertEqual(self.look(ov, game, 175, alert=True), [])          # inside WILD_ALERT_DAYS
        game.units = FAR
        self.assertEqual(self.look(ov, game, 180, alert=True), [False])
        game.units = []
        self.assertEqual(self.look(ov, game, 181, alert=False), [])

    def test_the_ten_day_cap_still_lifts_it_and_a_rest_follows(self):
        ov, game = self.sounded()
        self.assertEqual(self.look(ov, game, 180, alert=True, events=BRAWL), [])
        self.assertEqual(self.look(ov, game, 184, alert=True), [False])     # 11 days: the cap
        self.assertIsNotNone(ov.wild_rest_until)
        self.assertEqual(self.look(ov, game, 185, alert=False, cancels=LANGUR_CANCELS), [])   # resting
        self.assertEqual(self.look(ov, game, 186, alert=False), [True])     # rest over, the troop still near
        self.assertEqual(ov.alert_since, 186 * harness.DAY)

    def test_the_troop_coming_back_re_sounds_without_cancels(self):
        ov, game = self.sounded()
        game.units = FAR
        self.assertEqual(self.look(ov, game, 180, alert=True), [False])
        self.assertEqual(self.look(ov, game, 183, alert=False), [])         # still away
        game.units = NEAR
        # back, no interrupt logged yet, but closing on a citizen (CX_REVIEW P1-4: nearness alone is not enough)
        self.assertEqual(self.look(ov, game, 188, alert=False, dwarves=[dict(PLANTER, x=128, y=104)]), [True])

    def test_a_resident_back_by_the_wagon_without_evidence_stays_quiet(self):
        ov, game = self.sounded()
        game.units = FAR
        self.assertEqual(self.look(ov, game, 180, alert=True), [False])
        game.units = NEAR
        self.assertEqual(self.look(ov, game, 188, alert=False, dwarves=[PLANTER]), [])
        self.assertEqual(self.look(ov, game, 189, alert=False, events=BRAWL), [True])   # it fights: again

    def test_the_memory_runs_out(self):
        ov, game = self.sounded()
        game.units = FAR
        self.assertEqual(self.look(ov, game, 180, alert=True), [False])
        game.units = NEAR
        self.assertEqual(self.look(ov, game, 173 + harness.WILD_MEMORY_DAYS + 1, alert=False), [])

    def test_no_wagon_or_no_positions_keeps_the_old_three_day_hold(self):
        ov, game = self.sounded()
        self.assertEqual(self.look(ov, game, 180, alert=True, wagon={}), [False])
        ov2, game2 = self.sounded([{k: v for k, v in u.items() if k not in ("x", "y")} for u in NEAR])
        self.assertEqual(self.look(ov2, game2, 180, alert=True), [False])

    def test_a_far_flier_never_holds(self):
        # hard MY1-4 (68bd4c7, O 100): the buzzards that sounded the alert on day 192 sat 38-120 tiles out
        birds = [{"id": 50 + i, "race": "BIRD_BUZZARD", "hostile": False, "x": x, "y": y, "z": z}
                 for i, (x, y, z) in enumerate([(32, 164, 169), (180, 189, 181), (57, 90, 169), (112, 136, 177)])]
        game = FakeGame(birds)
        ov = harness.Overseer(game, days=216)
        lines = ["Urist %d cancels Haul: Interrupted by a buzzard." % i for i in range(4)]
        self.assertEqual(self.look(ov, game, 192, cancels=lines), [True])
        self.assertEqual(self.look(ov, game, 199, alert=True), [False])
        self.assertEqual(self.look(ov, game, 200, alert=False), [])

    def test_one_units_query_per_look(self):
        ov, game = self.sounded()
        game.queries = 0
        self.look(ov, game, 180, alert=True)
        self.assertEqual(game.queries, 1)


if __name__ == "__main__":
    unittest.main()
