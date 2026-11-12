"""cx invader drink window (owner decision 2026-11-10): game invaders no longer keep the civilians in past the drink
access cap. Before, the cap (ACCESS_CAP_DAYS since the last confirmed access window) lifted the alert under invaders
and defend()'s invader alert_on sounded it again on the next day's pass — one free day, never the ACCESS_WINDOW_DAYS a
window needs. Now the lift gives ACCESS_WINDOW_DAYS with the invader re-sound barred, the squad stationed on the
entrance nearest the invaders; the alert re-sounds after the window if invaders are still in sight; with no squad the
window is still given and logged. The fort is the MY1-1 layout of test_drink_access (stores on the surface z142, the
Shelter the dug levels, hatches 64/65 on E1/E2). No game or network."""
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
# goblins west of the fort: E1 (x93) is the entrance nearest them, both entrances more than 15 tiles away
FAR = [{"id": 900 + i, "race": "GOBLIN", "invader": True, "x": 60 + i, "y": 88, "z": SURFACE} for i in range(3)]


def dwarf(i, z=141, job="idle", x=98, y=88):
    return {"id": i, "job": job, "x": x, "y": y, "z": z, "adult": True, "profession": "Stonecrafter"}


def sheltered(n=CIT):
    return [dwarf(99)] + [dwarf(200 + i) for i in range(n - 1)]


def hatch(hid, site, locked=False):
    return {"id": hid, "kind": "hatch", "x": site["x"], "y": site["y"], "z": site["z"], "built": True,
            "locked": locked}


def squad_of(orders=(), armed=4, uniform="leather", n=4):
    return {"id": 1, "members": list(range(1, n + 1)), "armed": armed, "uniform": uniform,
            "orders": [dict(o) for o in orders]}


def fort(day, alert=False, invaders=(), squads=(), dwarves=None, drink=388, dist=30):
    dwarves = sheltered() if dwarves is None else dwarves
    inside = sum(1 for p in dwarves if p["z"] < SURFACE)
    obs = {"date": {"abs_tick": int(day * harness.DAY)}, "administrators": {"citizens": len(dwarves)},
           "stocks": {"drink": drink, "food_edible": 131},
           "map": {"sites": [dict(E1), dict(E2)], "wagon": dict(WAGON), "surface_z": SURFACE},
           "dwarves": [dict(x) for x in dwarves], "recent_cancellations": [], "recent_events": [],
           "military": {"squads": [dict(q) for q in squads]},
           "threats": {"visible_hostiles": len(invaders), "hostiles": [dict(h) for h in invaders],
                       **({"nearest_hostile_dist_to_wagon": dist} if invaders else {})},
           "doors": {"list": [hatch(64, E1), hatch(65, E2)], "hatch_cover_items_free": 0},
           "burrows": {"civilian_alert": alert, "list": [{"id": 0, "name": "Shelter", "civ_alert_burrow": True,
                                                          "citizens_inside": inside}]}}
    return {"tick": int(day * harness.DAY), "day": int(day), "observation": obs, "days_left": 216 - int(day)}


class FakeGame:
    def __init__(self):
        self.calls, self.refuse = [], []

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        for pred in self.refuse:
            if pred(tool, args):
                return {"ok": False, "error_code": "invalid_target", "error": "refused"}
        return {"ok": True, "result": {}}

    def query(self, *a, **kw):
        return {"result": {"units": []}}


STATION = ("squad_order", {"order": "station", "x": E1["x"], "y": E1["y"], "z": SURFACE})
ATTACK = ("squad_order", {"order": "attack"})
ON, OFF = ("civilian_alert", {"on": True}), ("civilian_alert", {"on": False})


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

    def ov(self):
        game = FakeGame()
        ov = harness.Overseer(game, days=216)
        ov.count = 0
        return ov, game

    def pass_(self, ov, game, day, **kw):
        """One layer pass's alert steps, in plan()'s order."""
        ov.load(fort(day, **kw))
        ov.count = 0
        game.calls.clear()
        ov.safe_state()
        ov.defend()
        ov.wildlife_response()
        ov.mark_guard()
        ov.entrance_hatches()
        return list(game.calls)

    def siege(self, ov, game, squads=()):
        """Invaders in sight from day 100 (the alert on, the first look starts the access clock) to the cap."""
        self.pass_(ov, game, 100, alert=True, invaders=FAR, squads=squads)
        self.assertEqual(ov.access_tick, 100 * harness.DAY)
        calls = self.pass_(ov, game, 109, alert=True, invaders=FAR, squads=squads)
        self.assertNotIn(OFF, calls)   # inside the cap: the invader alert holds


class Window(Base):
    def test_cap_reached_with_invaders_lifts_and_stations_the_squad_on_the_entrance(self):
        ov, game = self.ov()
        sq = squad_of([{"order": "attack"}])
        self.siege(ov, game, [sq])
        calls = self.pass_(ov, game, 111, alert=True, invaders=FAR, squads=[sq])
        self.assertIn(OFF, calls)
        self.assertIn(STATION, calls)            # E1: the entrance nearest the goblins, the hatch tile
        self.assertNotIn(ATTACK, calls)
        self.assertEqual(ov.invader_window, 113 * harness.DAY)
        self.assertTrue(self.logs("invader_window"))
        self.assertTrue(self.logs("invader_guard"))
        self.assertGreaterEqual(ov.wild_rest_until, 113 * harness.DAY)   # no wildlife alert inside the window
        # the next day: invaders still in sight, yet no re-sound and the squad keeps the entrance
        calls = self.pass_(ov, game, 112, invaders=FAR, squads=[squad_of([STATION[1]])])
        self.assertNotIn(ON, calls)
        self.assertNotIn(ATTACK, calls)
        self.assertNotIn(("squad_order", {"order": "stand_down"}), calls)
        self.assertFalse(any(t == "lock_door" and a.get("locked") for t, a in calls))

    def test_re_sound_after_the_window_while_invaders_are_still_in_sight(self):
        ov, game = self.ov()
        sq = squad_of([{"order": "attack"}])
        self.siege(ov, game, [sq])
        self.pass_(ov, game, 111, alert=True, invaders=FAR, squads=[sq])
        self.pass_(ov, game, 112, invaders=FAR, squads=[squad_of([STATION[1]])])
        calls = self.pass_(ov, game, 113, invaders=FAR, squads=[squad_of([STATION[1]])])
        self.assertIn(ON, calls)
        self.assertIn(ATTACK, calls)             # the guard ends with the window: back to the attack
        self.assertIsNone(ov.invader_window)
        self.assertIsNone(ov.invader_guard)
        self.assertTrue(self.logs("invader_window_end"))

    def test_window_completed_by_citizens_at_the_stores_keeps_the_re_sounded_alert(self):
        ov, game = self.ov()
        sq = squad_of([{"order": "attack"}])
        self.siege(ov, game, [sq])
        self.pass_(ov, game, 111, alert=True, invaders=FAR, squads=[sq])
        out = [dwarf(99, z=SURFACE, x=100, y=99)] + [dwarf(200 + i, z=SURFACE, x=100, y=99) for i in range(CIT - 1)]
        self.pass_(ov, game, 111.5, invaders=FAR, squads=[squad_of([STATION[1]])], dwarves=out, drink=380)
        self.pass_(ov, game, 113.5, invaders=FAR, squads=[squad_of([STATION[1]])], dwarves=out, drink=370)
        self.assertEqual(ov.access_tick, int(113.5 * harness.DAY))   # the window completed
        self.assertFalse(ov.thirst_due())
        calls = self.pass_(ov, game, 114.5, alert=True, invaders=FAR, squads=[squad_of([{"order": "attack"}])])
        self.assertNotIn(OFF, calls)             # the cap clock restarted: the invader alert holds again

    def test_no_squad_still_gives_the_window_and_logs_it(self):
        ov, game = self.ov()
        self.siege(ov, game)
        calls = self.pass_(ov, game, 111, alert=True, invaders=FAR)
        self.assertIn(OFF, calls)
        self.assertFalse(any(t == "squad_order" for t, a in calls))
        self.assertEqual(ov.invader_window, 113 * harness.DAY)
        un = self.logs("invader_unguarded")
        self.assertTrue(un)
        self.assertEqual(un[-1]["why"], "no_squad")
        calls = self.pass_(ov, game, 112, invaders=FAR)
        self.assertNotIn(ON, calls)
        calls = self.pass_(ov, game, 113, invaders=FAR)
        self.assertIn(ON, calls)

    def test_unequipped_squad_is_equipped_and_the_window_still_given(self):
        ov, game = self.ov()
        sq = squad_of(armed=0, uniform="none")
        self.siege(ov, game, [sq])
        calls = self.pass_(ov, game, 111, alert=True, invaders=FAR, squads=[sq])
        self.assertIn(OFF, calls)
        self.assertIn("equip", ov.last)          # equip_squad went out (the uniform reads none)
        self.assertNotIn(STATION, calls)         # no unarmed soldier is put in front of the goblins
        self.assertEqual(self.logs("invader_unguarded")[-1]["why"], "unequipped")
        self.assertEqual(ov.invader_window, 113 * harness.DAY)

    def test_invaders_gone_normal_lift_without_guard(self):
        ov, game = self.ov()
        sq = squad_of([{"order": "attack"}])
        self.siege(ov, game, [sq])
        calls = self.pass_(ov, game, 111, alert=True, squads=[sq])
        self.assertIn(OFF, calls)
        self.assertIsNone(ov.invader_window)
        self.assertFalse(self.logs("invader_window"))
        self.assertNotIn(STATION, calls)
        self.assertIn(("squad_order", {"order": "stand_down"}), calls)


class Moment(Base):
    def test_lift_waits_while_an_invader_stands_at_an_entrance_then_goes(self):
        ov, game = self.ov()
        sq = squad_of([{"order": "attack"}])
        self.siege(ov, game, [sq])
        at_door = [dict(FAR[0], x=E1["x"] - 5, y=E1["y"])] + FAR[1:]
        calls = self.pass_(ov, game, 111, alert=True, invaders=at_door, squads=[sq])
        self.assertNotIn(OFF, calls)
        self.assertEqual(self.logs("invader_defer")[-1]["invaders"], [900])
        calls = self.pass_(ov, game, 112, alert=True, invaders=FAR, squads=[sq])   # it walked off
        self.assertIn(OFF, calls)
        self.assertIn(STATION, calls)

    def test_lift_goes_past_the_defer_budget_even_with_an_invader_at_the_door(self):
        ov, game = self.ov()
        sq = squad_of([{"order": "attack"}])
        self.siege(ov, game, [sq])
        at_door = [dict(FAR[0], x=E1["x"] - 5, y=E1["y"])]
        for day in (111, 112, 113):
            self.assertNotIn(OFF, self.pass_(ov, game, day, alert=True, invaders=at_door, squads=[sq]))
        calls = self.pass_(ov, game, 113.5, alert=True, invaders=at_door, squads=[sq])
        self.assertIn(OFF, calls)                # thirst death is certain: 10 + CAP_DEFER_DAYS is the end
        self.assertIn(STATION, calls)

    def test_a_refused_hatch_tile_station_tries_the_stair_foot(self):
        ov, game = self.ov()
        game.refuse.append(lambda t, a: t == "squad_order" and a.get("z") == SURFACE)
        sq = squad_of([{"order": "attack"}])
        self.siege(ov, game, [sq])
        calls = self.pass_(ov, game, 111, alert=True, invaders=FAR, squads=[sq])
        self.assertIn(STATION, calls)
        self.assertIsNone(ov.invader_guard)
        calls = self.pass_(ov, game, 111.5, invaders=FAR, squads=[sq])
        self.assertIn(("squad_order", {"order": "station", "x": E1["x"], "y": E1["y"], "z": SURFACE - 1}), calls)
        self.assertEqual(ov.invader_guard, (E1["x"], E1["y"], SURFACE - 1))
        self.assertNotIn(ON, calls)


if __name__ == "__main__":
    unittest.main()
