"""d49: the squad is stationed beside the wagon while a wild gray langur or rhesus macaque is near, and stands down
when none is; never during a lockdown, the thaw or with a hostile in sight, and never on the labs."""
import io
import os
import sys
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
from support import StubGame, resp  # noqa: E402
from overseer import harness as H  # noqa: E402
from overseer.harness import Overseer  # noqa: E402

WAGON = {"present": True, "x": 100, "y": 100, "z": 150}
SQUAD = {"id": 1, "members": 4, "armed": 2, "uniform": "leather", "orders": []}


def fort(rows, lab=False, orders=()):
    r = resp(150, 60, food=100, drink=200, cit=16, hands_off=(5 if lab else None))
    o = r["observation"]
    o["map"]["wagon"] = dict(WAGON)
    o["military"] = {"squads": [dict(SQUAD, orders=list(orders))]}
    g = StubGame(herd=[])
    ov = Overseer(g, goal="Run the fortress", days=216)
    ov.set_task({"goal": "Run the fortress.", **({"hands_off": {"from_day": 30, "days": 10}} if lab else {})})
    ov.load(r)
    ov.count = 0
    ov.others, ov.others_at = [dict(u) for u in rows], ov.now
    return ov, g


def monkey(race, dist, **kw):
    return dict({"id": 7, "race": race, "x": 100 + dist, "y": 100, "z": 150, "hostile": False}, **kw)


def guard(ov, orders=(), hostile=0, holding=False):
    squad = dict(SQUAD, orders=list(orders))
    ov.troop_guard(squad, list(orders), hostile, holding)


class D49(unittest.TestCase):
    def setUp(self):
        self.out = redirect_stdout(io.StringIO())
        self.out.__enter__()
        self.addCleanup(self.out.__exit__, None, None, None)

    def test_a_near_macaque_stations_the_squad_beside_the_wagon(self):
        ov, g = fort([monkey("MACAQUE_RHESUS", 70)])
        guard(ov)
        self.assertEqual(g.tools("squad_order"), [{"order": "station", "x": 100, "y": 102, "z": 150}])
        self.assertIsNotNone(ov.troop_post)

    def test_it_stays_between_the_two_distances_and_goes_when_none_is_near(self):
        ov, g = fort([monkey("GRAY_LANGUR", 70)])
        guard(ov)
        ov.others = [monkey("GRAY_LANGUR", 95)]
        guard(ov, orders=[{"type": "station"}])
        self.assertIsNotNone(ov.troop_post)
        ov.others = [monkey("GRAY_LANGUR", 130)]
        guard(ov, orders=[{"type": "station"}])
        self.assertIsNone(ov.troop_post)      # defend() then stands the squad down (it has orders, no hostile)

    def test_a_hostile_or_a_lockdown_takes_the_squad_back(self):
        ov, g = fort([monkey("MACAQUE_RHESUS", 60)])
        guard(ov)
        guard(ov, orders=[{"type": "station"}], hostile=1)
        self.assertIsNone(ov.troop_post)
        self.assertEqual(g.tools("squad_order")[-1], {"order": "stand_down"})
        ov2, g2 = fort([monkey("MACAQUE_RHESUS", 60)])
        ov2.lock = {"phase": "hold", "why": "wildlife"}
        guard(ov2)
        self.assertEqual(g2.tools("squad_order"), [])

    def test_keas_tame_or_far_animals_station_nobody(self):
        for rows in ([monkey("BIRD_KEA", 20)], [monkey("GRAY_LANGUR", 20, tame=True)], [monkey("GRAY_LANGUR", 90)], []):
            ov, g = fort(rows)
            guard(ov)
            self.assertEqual(g.tools("squad_order"), [])

    def test_an_old_look_shows_nothing(self):
        ov, g = fort([monkey("GRAY_LANGUR", 30)])
        ov.others_at = ov.now - (H.TROOP_STALE + 1) * H.DAY
        guard(ov)
        self.assertEqual(g.tools("squad_order"), [])

    def test_a_refused_tile_moves_the_station_on(self):
        ov, g = fort([monkey("GRAY_LANGUR", 30)])
        original = g.act

        def refuse(tool, args):
            if tool == "squad_order" and args.get("y") == 102:
                g.calls.append((tool, dict(args)))
                return {"ok": False, "error_code": "not_walkable", "error": "scripted"}
            return original(tool, args)
        g.act = refuse
        guard(ov)
        ov.now += 2 * H.DAY
        guard(ov)
        self.assertEqual([(a["x"], a["y"]) for a in g.tools("squad_order")], [(100, 102), (102, 100)])

    def test_the_labs_never_station_for_troops(self):
        ov, g = fort([monkey("GRAY_LANGUR", 30)], lab=True)
        self.assertFalse(ov.open_task())


if __name__ == "__main__":
    unittest.main()
