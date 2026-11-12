"""cx alert/lock safety (audit of e311881): (1) the last pass before a hands-off window leaves no alert and no lock of
this layer's (hard LT08-0 on f2bd283: a mark alert on day 37 with hands_off 2 stood through days 38-60); (7) the
alert/lock steps run first, each in its own try; (8) no lock while the squad is sent to the surface; (9) entrances
sort as numbers and a lock goes on only when it closes every entrance; (12) wild_approaching reads one baseline a
pass. No game or network."""
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from overseer import harness  # noqa: E402
from test_shelter_hatches import E1, E2, SURFACE, FakeGame, fort, hatch, overseer  # noqa: E402


class Quiet(unittest.TestCase):
    def setUp(self):
        self.out = io.StringIO()
        self.output = redirect_stdout(self.out)
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)


def E(n):
    return {"id": "E%d" % n, "kind": "E", "x": 80 + n, "y": 80, "z": SURFACE}


class SafeState(Quiet):
    def locked_fort(self, day, hands_off):
        resp = fort(day, sites=[E1], alert=True, inside=18, doors={"list": [hatch(19, E1, locked=True)]})
        resp["hands_off_in_days"] = hands_off
        return resp

    def test_the_last_pass_before_the_window_lifts_and_unlocks_and_sounds_nothing(self):
        beast = {"id": 5, "race": "CARNOTAURUS", "hostile": False, "x": 110, "y": 100, "z": SURFACE}
        game = FakeGame([beast])
        ov = overseer(game)
        ov.alert_locked = {19}
        ov.pass_days = [23, 30]                 # the model's 7-day stride
        ov.load(self.locked_fort(30, hands_off=9))
        ov.safe_state()
        self.assertFalse(ov.safe_held)          # 9 > 7: another pass comes before the window
        self.assertEqual(game.calls, [])
        ov.load(self.locked_fort(37, hands_off=2))
        game.calls.clear()
        ov.safe_state()
        ov.defend()
        ov.mark_guard()
        ov.entrance_hatches()
        self.assertTrue(ov.safe_held)
        self.assertEqual(game.tools("civilian_alert"), [{"on": False}])   # the big beast near: no new alert
        self.assertEqual(game.tools("lock_door"), [{"locked": False, "door_id": 19}])
        self.assertEqual(ov.alert_locked, set())
        self.assertIn('"safe_state"', self.out.getvalue())

    def test_plan_runs_it_first(self):
        game = FakeGame()
        ov = overseer(game)
        ov.alert_locked = {19}
        ov.pass_days = [30, 37]
        ov.load(self.locked_fort(37, hands_off=1))
        ov.management = lambda: (_ for _ in ()).throw(KeyError("stop here"))
        with self.assertRaises(KeyError):
            ov.plan()
        self.assertIn(("lock_door", {"locked": False, "door_id": 19}), game.calls)

    def test_the_standalone_exit_path_makes_it_safe(self):
        game = FakeGame()
        game.observe = lambda: fort(50, sites=[E1], alert=True, inside=18, doors={"list": [hatch(19, E1, True)]})
        ov = overseer(game)
        ov.alert_locked = {19}
        harness.exit_safe(ov, "game_error")
        self.assertEqual(game.tools("civilian_alert"), [{"on": False}])
        self.assertEqual(game.tools("lock_door"), [{"locked": False, "door_id": 19}])


class StepsIsolated(Quiet):
    def test_an_error_in_mood_does_not_skip_the_unlock(self):
        game = FakeGame()
        ov = overseer(game)
        ov.alert_locked = {19}
        ov.load(fort(50, sites=[E1], alert=False, inside=18, doors={"list": [hatch(19, E1, locked=True)]}))
        ov.mood = lambda: 1 / 0
        ov.management = lambda: (_ for _ in ()).throw(KeyError("stop here"))
        with self.assertRaises(KeyError):
            ov.plan()
        self.assertIn(("lock_door", {"locked": False, "door_id": 19}), game.calls)
        self.assertIn("guard_step_error", self.out.getvalue())


class SquadOut(Quiet):
    def test_no_lock_while_the_squad_is_stationed_on_the_surface(self):
        game = FakeGame()
        ov = overseer(game)
        squad = {"id": 0, "members": [], "orders": [{"order": "station", "x": 100, "y": 100, "z": SURFACE}]}
        ov.load(fort(50, sites=[E1], alert=True, inside=18, doors={"list": [hatch(19, E1)]}, squads=[squad]))
        ov.entrance_hatches()
        self.assertEqual(game.tools("lock_door"), [])
        self.assertIn("squad_out", self.out.getvalue())
        squad["orders"] = [{"order": "station", "x": 100, "y": 100, "z": SURFACE - 2}]   # down in the fort
        ov.load(fort(51, sites=[E1], alert=True, inside=18, doors={"list": [hatch(19, E1)]}, squads=[squad]))
        ov.entrance_hatches()
        self.assertEqual(game.tools("lock_door"), [{"locked": True, "door_id": 19}])

    def test_an_order_sent_this_pass_opens_the_hatches_in_the_same_pass(self):
        game = FakeGame()
        ov = overseer(game)
        ov.alert_locked = {19}
        squad = {"id": 0, "members": [], "orders": []}
        ov.load(fort(50, sites=[E1], alert=True, inside=18, doors={"list": [hatch(19, E1, True)]}, squads=[squad]))
        ov.act("mark_rescue", "squad_order", {"order": "station", "x": 100, "y": 100, "z": SURFACE}, retry=0.25)
        ov.entrance_hatches()
        self.assertIn(("lock_door", {"locked": False, "door_id": 19}), game.calls)


class Entrances(Quiet):
    def test_site_ids_sort_as_numbers(self):
        self.assertEqual(sorted(["E10", "E2", "E1", "X"], key=harness.site_key), ["E1", "E2", "E10", "X"])

    def test_an_open_entrance_means_no_lock(self):
        game = FakeGame()
        ov = overseer(game)
        doors = {"list": [hatch(19, E1), hatch(20, E2)], "hatch_cover_items_free": 0}
        ov.load(fort(50, sites=[E1, E2, E(10)], alert=True, inside=18, doors=doors))
        ov.entrance_hatches()
        self.assertEqual(game.tools("lock_door"), [])
        self.assertIn("open:E10", self.out.getvalue())

    def test_more_entrances_than_hatches_means_no_lock_and_the_old_locks_open(self):
        game = FakeGame()
        ov = overseer(game)
        sites = [E(n) for n in range(1, 6)]
        doors = {"list": [hatch(10 + n, E(n), locked=n <= 4) for n in range(1, 5)], "hatch_cover_items_free": 0}
        ov.alert_locked = {11, 12, 13, 14}
        ov.load(fort(50, sites=sites, alert=True, inside=18, doors=doors))
        ov.entrance_hatches()
        self.assertEqual(sorted(a["door_id"] for a in game.tools("lock_door") if not a["locked"]), [11, 12, 13, 14])
        self.assertIn("open:E5", self.out.getvalue())

    def test_an_unbuilt_hatch_does_not_close_its_entrance(self):
        game = FakeGame()
        ov = overseer(game)
        doors = {"list": [hatch(19, E1), hatch(20, E2, built=False)], "hatch_cover_items_free": 0}
        ov.load(fort(50, sites=[E1, E2], alert=True, inside=18, doors=doors))
        ov.entrance_hatches()
        self.assertEqual(game.tools("lock_door"), [])


class ApproachBaseline(Quiet):
    def test_two_asks_in_one_pass_give_one_answer(self):
        game = FakeGame()
        ov = overseer(game)
        u = {"id": 5, "x": 150 + 20, "y": 40, "z": SURFACE}   # 20 tiles from the mason
        ov.load(fort(50))
        self.assertFalse(ov.wild_approaching([u]))
        ov.load(fort(51))
        u2 = dict(u, x=150 + 15)                             # 5 tiles closer than at the last pass
        self.assertTrue(ov.wild_approaching([u2]))
        self.assertTrue(ov.wild_approaching([u2]))           # asked again in the same pass: still approaching


if __name__ == "__main__":
    unittest.main()
