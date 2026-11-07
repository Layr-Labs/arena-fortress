"""Soil rooms must leave space to install furniture, even at migrant populations."""
import contextlib
import io
import unittest
from overseer.harness import Overseer


class Game:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, args))
        return {"ok": True}


class HousingReservation(unittest.TestCase):
    def test_existing_farms_do_not_take_every_new_room(self):
        game = Game()
        guard = Overseer(game)
        guard.count = 0
        guard.load({"tick": 1200, "observation": {
            "administrators": {"citizens": 47},
            "farm_plots": [{"id": 1}, {"id": 2}],
            "map": {"surface_z": 78, "sites": [
                {"kind": "R", "id": "R" + str(i), "soil": True, "z": 77,
                 "x": 10 * i, "y": 10, "w": 3, "h": 3}
                for i in range(1, 7)]}}})
        with contextlib.redirect_stdout(io.StringIO()):
            guard.digging()
        self.assertEqual([guard.roles['R' + str(i)] for i in range(1, 4)],
                         ['dorm', 'dine', 'office'])
        self.assertTrue(any(role == 'farm' for role in guard.roles.values()))
        self.assertGreaterEqual(game.calls[0][1]['w'] * game.calls[0][1]['h'], 2 * 47)
        self.assertEqual(game.calls[1][1]['w'], 7)


    def test_migrant_beds_precede_extra_dining_orders(self):
        game = Game()
        guard = Overseer(game, goal="Migrants are arriving")
        guard.count = 0
        guard.load({"tick": 1200, "observation": {
            "administrators": {"citizens": 40},
            "stocks": {"beds": 19, "chairs": 12, "tables": 12,
                       "logs_usable": 200}}})
        with contextlib.redirect_stdout(io.StringIO()):
            guard.supply()
        orders = [args for tool, args in game.calls if tool == 'add_order']
        beds = [o for o in orders if o['recipe'] == 'make_bed']
        self.assertEqual(len(beds), 1)
        self.assertEqual(beds[0]['amount'], 30)
        self.assertFalse(any(o['recipe'] in ('make_table', 'make_chair') for o in orders))

    def test_manager_chair_is_not_deferred_with_dining(self):
        game = Game()
        guard = Overseer(game, goal="Migrants are arriving")
        guard.count = 0
        guard.load({"tick": 1200, "observation": {
            "administrators": {"citizens": 40},
            "stocks": {"beds": 19, "chairs": 0, "logs_usable": 200}}})
        with contextlib.redirect_stdout(io.StringIO()):
            guard.supply()
        self.assertTrue(any(args.get('recipe') == 'make_chair' for _, args in game.calls))


if __name__ == '__main__':
    unittest.main()
