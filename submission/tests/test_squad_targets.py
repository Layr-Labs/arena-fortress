"""Offline regressions for the squad on the long open tasks: it is sent only at invaders, by id, and stands down when
the only dangers in sight are beasts. Stub game; no DF, no model."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from support import overseer, resp


def fort(hostiles, orders=()):
    r = resp(200, 136, food=80, cit=16)
    r["observation"]["threats"] = {"visible_hostiles": len(hostiles), "hostiles": hostiles,
                                   "nearest_hostile_dist_to_wagon": 120}
    r["observation"]["military"] = {"squads": [{"name": "S", "members": [1, 2, 3, 4], "armed": 2,
                                                "uniform": "leather", "orders": list(orders)}]}
    return r


def squad_orders(g):
    return [a for a in g.tools("squad_order")]


BEAST = {"id": 501, "race": "FORGOTTEN_BEAST", "invader": False, "dist_to_wagon": 120}
GOBLIN = {"id": 502, "race": "GOBLIN", "invader": True, "dist_to_wagon": 120}


class SquadTargets(unittest.TestCase):
    def test_a_beast_alone_draws_no_attack(self):
        ov, g = overseer(fort([BEAST]))
        ov.defend()
        self.assertEqual(squad_orders(g), [])

    def test_invaders_are_attacked_by_id(self):
        ov, g = overseer(fort([BEAST, GOBLIN]))
        ov.defend()
        self.assertEqual(squad_orders(g), [{"order": "attack", "target_ids": [502]}])

    def test_a_standing_order_with_only_a_beast_in_sight_is_stood_down(self):
        ov, g = overseer(fort([BEAST], orders=[{"kind": "kill"}]))
        ov.defend()
        self.assertEqual(squad_orders(g), [{"order": "stand_down"}])


if __name__ == "__main__":
    unittest.main()
