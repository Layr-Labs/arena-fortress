"""cx FIGHT HOLD (hint std MY1-4 on 657e3d0, day 106.5): the 10-day cap lifted the alert a day after a kea fought the
mason and the metalcrafter at the E1 top. The nearest kea at the lift look was 52 tiles out (past WILD_NEAR_TILES, so
mark_pressing did not hold it); 0.4 days later a kea was on the stockpile and struck 5 civilians 14 times. The cap lift
now also waits while a unit of a species that fought a citizen within FIGHT_HOLD_DAYS stands within MARK_RANGE, still
bounded by CAP_DEFER_DAYS and the drink-access clock. No game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_troop_hold import FakeGame, NEAR, LANGUR_CANCELS, BRAWL, fort  # noqa: E402

FAR52 = [dict(u, x=95 + 52, y=95) for u in NEAR[:3]]   # every langur 52 tiles east of the wagon: past 30, inside 60
FIGHT = ["The gray langur bites the planter in the right foot, bruising the muscle!"]


class FightHold(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def look(self, ov, game, day, **kw):
        ov.load(fort(day, **kw))
        ov.count = 0
        game.calls.clear()
        ov.defend()
        ov.wildlife_response()
        return [a["on"] for t, a in game.calls if t == "civilian_alert"]

    def to_the_cap(self, fight_on_184):
        game = FakeGame(NEAR)
        ov = harness.Overseer(game, days=216)
        self.assertEqual(self.look(ov, game, 173, cancels=LANGUR_CANCELS), [True])
        self.assertEqual(self.look(ov, game, 180, alert=True, events=BRAWL), [])   # troop hold
        game.units = FAR52
        events = BRAWL + (FIGHT if fight_on_184 else [])
        return ov, game, self.look(ov, game, 184, alert=True, events=events)

    def test_no_fresh_fight_the_cap_lifts_as_before(self):
        ov, game, on = self.to_the_cap(False)
        self.assertEqual(on, [False])

    def test_a_fight_within_a_day_holds_the_cap_lift_then_it_lifts(self):
        ov, game, on = self.to_the_cap(True)
        self.assertEqual(on, [])                                     # held: the langurs 52 tiles out
        self.assertEqual(ov.fight_pressing(), ["gray langur"])
        # the same report text a day later is not a new fight; the stamp is a day old: still held
        self.assertEqual(self.look(ov, game, 185, alert=True, events=BRAWL + FIGHT), [])
        # two days on, no new fight: the cap lifts
        self.assertEqual(self.look(ov, game, 186, alert=True, events=BRAWL + FIGHT), [False])

    def test_the_hold_ends_when_the_species_is_out_of_mark_range(self):
        ov, game, on = self.to_the_cap(True)
        self.assertEqual(on, [])
        game.units = [dict(u, x=95 + 80) for u in FAR52]
        self.assertEqual(self.look(ov, game, 185, alert=True), [False])

    def test_cap_defer_days_bounds_the_hold(self):
        ov, game, on = self.to_the_cap(True)
        self.assertEqual(on, [])
        day = 173 + 10 + harness.CAP_DEFER_DAYS + 1
        self.assertEqual(self.look(ov, game, day, alert=True,
                                   events=["The gray langur bites the planter, wound %d!" % day]), [False])

    def test_zero_restores_the_old_rule(self):
        old = harness.FIGHT_HOLD_DAYS
        harness.FIGHT_HOLD_DAYS = 0
        try:
            ov, game, on = self.to_the_cap(True)
        finally:
            harness.FIGHT_HOLD_DAYS = old
        self.assertEqual(on, [False])


if __name__ == "__main__":
    unittest.main()
