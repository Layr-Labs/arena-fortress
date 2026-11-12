"""cx drink access (hint hard MY1-1 on 6adf843, score 66.0): the expedition leader (unit 99, hf 142) died of THIRST
at tick 1163452 (day 163.5) with 382 drink in stock. Every drink/food stockpile, Still and Kitchen stood on the
surface (z142); the Shelter was the dug levels z140-141, reached only through hatches 64 (93,88,142) and 65
(96,92,142). Confinements (alert on or the alert hatches locked) ran 22-28, 29-45, 50-64, 106-127 and 148-177;
the drink stock stood at 388 from day 106 to 147 — from day 127 the switches read free, yet all 22 citizens stayed
in the Shelter's top rooms, idle — all drank once on 147-148 (388 -> 367) while the leader slept, the alert sounded
again on 148 and the stock stood at 382 to day 178. Confinement is now measured from the last confirmed access
window (free for ACCESS_WINDOW_DAYS with evidence: a citizen on the surface / out of the Shelter, or drink falling).
No game or network."""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness  # noqa: E402

SURFACE = 142
WAGON = {"present": True, "x": 96, "y": 96, "z": SURFACE}
E1 = {"id": "E1", "kind": "E", "x": 93, "y": 88, "z": SURFACE}
E2 = {"id": "E2", "kind": "E", "x": 96, "y": 92, "z": SURFACE}
CIT = 22


def dwarf(i, z=141, job="idle", x=98, y=88):
    return {"id": i, "job": job, "x": x, "y": y, "z": z, "adult": True, "profession": "Stonecrafter"}


def sheltered(n=CIT, leader_job="idle"):
    """Every citizen in the Shelter's top rooms (the record's days 127-141)."""
    return [dwarf(99, job=leader_job)] + [dwarf(200 + i) for i in range(n - 1)]


def working(n_out=14):
    """The record's day 148: 14 of 22 on the surface, the leader asleep in the dormitory."""
    out = [dwarf(99, z=140, job="Sleep", x=96, y=89)]
    out += [dwarf(200 + i, z=SURFACE, job="CustomReaction", x=100, y=99) for i in range(n_out)]
    out += [dwarf(300 + i) for i in range(CIT - 1 - n_out)]
    return out


def hatch(hid, site, locked=False):
    return {"id": hid, "kind": "hatch", "x": site["x"], "y": site["y"], "z": site["z"], "built": True,
            "locked": locked}


def fort(day, alert=False, locked=False, dwarves=None, drink=388, inside=None, cancels=()):
    dwarves = sheltered() if dwarves is None else dwarves
    if inside is None:
        inside = sum(1 for p in dwarves if p["z"] < SURFACE)
    obs = {"date": {"abs_tick": int(day * harness.DAY)}, "administrators": {"citizens": len(dwarves)},
           "stocks": {"drink": drink, "food_edible": 131},
           "map": {"sites": [dict(E1), dict(E2)], "wagon": dict(WAGON), "surface_z": SURFACE},
           "dwarves": [dict(x) for x in dwarves], "recent_cancellations": list(cancels), "recent_events": [],
           "military": {"squads": []}, "threats": {"visible_hostiles": 0, "hostiles": []},
           "doors": {"list": [hatch(64, E1, locked), hatch(65, E2, locked)], "hatch_cover_items_free": 0},
           "burrows": {"civilian_alert": alert, "list": [{"id": 0, "name": "Shelter", "civ_alert_burrow": True,
                                                          "citizens_inside": inside}]}}
    return {"tick": int(day * harness.DAY), "day": int(day), "observation": obs, "days_left": 216 - int(day)}


class FakeGame:
    def __init__(self, units=()):
        self.calls, self.units = [], list(units)

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {}}

    def query(self, *a, **kw):
        return {"result": {"units": list(self.units)}}

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

    def ov(self, units=()):
        game = FakeGame(units)
        ov = harness.Overseer(game, days=216)
        ov.count = 0
        return ov, game

    def pass_(self, ov, game, day, **kw):
        """One layer pass's alert steps, in plan()'s order."""
        ov.load(fort(day, **kw))
        ov.count = 0
        game.calls.clear()
        ov.defend()
        ov.wildlife_response()
        ov.mark_guard()
        ov.entrance_hatches()
        return game.calls


# a badger (seeded DANGER_SEED, not big, not weak) by the hatches: the record's days 162/170 had two on (93,88,142)
BADGER = {"id": 284, "race": "BADGER", "hostile": False, "x": 93, "y": 88, "z": SURFACE}


class Clock(Base):
    def test_free_looks_with_someone_out_complete_a_window(self):
        ov, game = self.ov()
        ov.load(fort(99, dwarves=working()))
        self.assertEqual(ov.access_tick, 99 * harness.DAY)
        ov.load(fort(100, dwarves=working()))
        self.assertEqual(ov.access_tick, 99 * harness.DAY)   # one day: the window is not complete yet
        ov.load(fort(101, dwarves=working()))
        self.assertEqual(ov.access_tick, 101 * harness.DAY)
        self.assertFalse(ov.thirst_due())

    def test_the_trap_free_switches_but_nobody_out_and_the_stock_unmoved_is_no_access(self):
        # the record's days 127, 134, 141: alert off, hatches unlocked, 22 of 22 inside, drink 388 unmoved
        ov, game = self.ov()
        ov.load(fort(106, dwarves=working()))
        ov.load(fort(108, dwarves=working()))
        self.assertEqual(ov.access_tick, 108 * harness.DAY)
        for day in (127, 134, 141):
            self.pass_(ov, game, day)
        self.assertEqual(ov.access_tick, 108 * harness.DAY)
        self.assertTrue(ov.thirst_due())
        self.assertTrue(self.logs("access_unseen"))
        self.assertIsNone(ov.wild_rest_until)   # nothing to release: the wildlife alerts are not barred on no evidence

    def test_the_drink_stock_falling_is_evidence_in_an_underground_fort(self):
        ov, game = self.ov()
        ov.load(fort(50, drink=300))
        ov.load(fort(51, drink=290))   # everyone in the Shelter, yet someone drank
        ov.load(fort(53, drink=285))
        self.assertEqual(ov.access_tick, 53 * harness.DAY)

    def test_a_confined_look_closes_the_window(self):
        ov, game = self.ov()
        ov.load(fort(60, dwarves=working()))
        ov.load(fort(61, alert=True))
        self.assertIsNone(ov.access_from)
        ov.load(fort(62, dwarves=working()))
        self.assertEqual(ov.access_tick, 60 * harness.DAY)   # the window restarts at 62

    def test_this_layers_locked_hatches_are_confinement_too(self):
        ov, game = self.ov()
        ov.alert_locked = {64, 65}
        self.assertFalse(ov.access_free(fort(70, locked=True)["observation"]))
        ov.alert_locked = set()   # a hatch the flood locked is not this layer's: evidence decides
        self.assertTrue(ov.access_free(fort(70, locked=True)["observation"]))

    def test_thirst_signs(self):
        ov, game = self.ov()
        obs = fort(162, locked=True, dwarves=sheltered(leader_job="DrinkItem"),
                   cancels=["Degël Avuzasiz, Clothier cancels Drink: Could not find path.",
                            "Mebzuth Vabôkïlun, Doctor cancels Drink: Forbidden area.",
                            "Imush Amithnish, queen cancels Eat: Item inaccessible.",
                            "Inod Igathlitast, Weaponsmith cancels Plant seeds: Could not find path."])["observation"]
        self.assertEqual(ov.thirst_signs(obs), 4)


class Incident(Base):
    def test_replay_the_day_148_re_sound_is_barred_until_the_window_completes(self):
        ov, game = self.ov()
        ov.load(fort(104, dwarves=working(), drink=384))
        ov.load(fort(106, dwarves=working(), drink=388))   # the last window before the run's day-106 alert
        self.assertEqual(ov.access_tick, 106 * harness.DAY)
        for day in (127, 134, 141):                          # free on the switches, nobody out, 388 unmoved
            self.pass_(ov, game, day, drink=388)
        self.assertTrue(self.logs("access_unseen"))
        game.units = [dict(BADGER, x=100, y=105)]            # near the citizens out on the surface
        calls = self.pass_(ov, game, 148, dwarves=working(), drink=367)
        self.assertNotIn(("civilian_alert", {"on": True}), calls)   # the record's mark_alert of day 148 is held
        self.assertTrue(ov.wild_resting())
        self.assertTrue(self.logs("access_hold"))
        calls = self.pass_(ov, game, 150, dwarves=working(), drink=380)
        self.assertEqual(ov.access_tick, 150 * harness.DAY)       # the window completed: 148 -> 150
        self.assertFalse(ov.thirst_due())
        self.assertIn(("civilian_alert", {"on": True}), calls)    # and the owner's mark alert works again

    def test_a_cumulative_confinement_lifts_past_the_cap_and_opens_the_hatches(self):
        # the record's 106-127: the alert (106), the hatches (113), the alert off (120) with the hatches kept to 127
        # a big beast 22 tiles from the citizens (no fight, not closing): the owner's BIG_FREE_DAYS hold applies
        ov, game = self.ov([{"id": 5, "race": "CARNOTAURUS", "hostile": False, "x": 120, "y": 100, "z": SURFACE}])
        ov.load(fort(104, dwarves=working()))
        ov.load(fort(106, dwarves=working()))
        ov.alert_locked = {64, 65}
        calls = self.pass_(ov, game, 113, alert=True, locked=True)
        self.assertNotIn(("civilian_alert", {"on": False}), calls)   # 7 days past the window: held
        calls = self.pass_(ov, game, 117, alert=True, locked=True)
        self.assertIn(("civilian_alert", {"on": False}), calls)       # 11 days past the window: lifted
        self.assertIn(("lock_door", {"locked": False, "door_id": 64}), calls)
        self.assertIn(("lock_door", {"locked": False, "door_id": 65}), calls)
        self.assertTrue(self.logs("access_lift"))
        self.assertTrue(ov.wild_resting())
        calls = self.pass_(ov, game, 118, dwarves=working())   # the beast still near: no re-sound in the window
        self.assertNotIn(("civilian_alert", {"on": True}), calls)

    def test_a_marked_animal_at_a_citizens_side_defers_the_lift_at_most_cap_defer_days(self):
        ov, game = self.ov([dict(BADGER, x=98, y=88, z=141)])   # down in the Shelter beside the citizens
        ov.load(fort(104, dwarves=working()))
        ov.load(fort(106, dwarves=working()))
        for day in (117, 119):   # 11 and 13 days past the window: the rescue station's wait
            ov.wild_evidence["badger"] = (day - 0.5) * harness.DAY
            calls = self.pass_(ov, game, day, alert=True)
            self.assertNotIn(("civilian_alert", {"on": False}), calls, day)
        self.assertTrue(self.logs("cap_defer"))
        ov.wild_evidence["badger"] = 119.4 * harness.DAY
        calls = self.pass_(ov, game, 119.5, alert=True)   # past ACCESS_CAP_DAYS + CAP_DEFER_DAYS: lifted
        self.assertIn(("civilian_alert", {"on": False}), calls)

    def test_the_chunked_look_stops_on_thirst_while_confined(self):
        ov, game = self.ov()
        ov.load(fort(104, dwarves=working()))
        ov.load(fort(106, dwarves=working()))
        self.assertNotIn("thirst", ov.danger_signs(fort(115, alert=True), query=False))
        self.assertIn("thirst", ov.danger_signs(fort(117, alert=True), query=False))
        self.assertNotIn("thirst", ov.danger_signs(fort(117, dwarves=working()), query=False))   # free: no stop


class OwnerPolicyKept(Base):
    def test_a_big_beast_holds_its_unconditional_days_inside_the_cap(self):
        beast = {"id": 5, "race": "CARNOTAURUS", "hostile": False, "x": 100, "y": 100, "z": SURFACE}
        ov, game = self.ov([beast])
        ov.load(fort(58, dwarves=working()))
        calls = self.pass_(ov, game, 60, dwarves=working())
        self.assertIn(("civilian_alert", {"on": True}), calls)
        calls = self.pass_(ov, game, 65, alert=True)
        self.assertNotIn(("civilian_alert", {"on": False}), calls)   # day 5 of BIG_FREE_DAYS: held

    def test_no_thirst_lift_while_the_last_window_is_recent(self):
        ov, game = self.ov([BADGER])
        ov.load(fort(98, dwarves=working()))
        ov.load(fort(100, dwarves=working()))
        ov.wild_alert_on()
        ov.wild_watch["badger"] = 100 * harness.DAY
        ov.wild_evidence["badger"] = 104 * harness.DAY
        calls = self.pass_(ov, game, 105, alert=True)
        self.assertEqual([a for t, a in calls if t == "civilian_alert"], [])
        self.assertFalse(self.logs("access_lift"))


if __name__ == "__main__":
    unittest.main()
