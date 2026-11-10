"""Food emergencies use large adult livestock; material requests keep their choice."""
import copy
import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer.harness import Overseer


class Game:
    def __init__(self, animals):
        self.animals = animals
        self.calls = []

    def query(self, name, **params):
        assert name == "units" and params == {"kind": "animals"}
        return {"result": {"units": copy.deepcopy(self.animals)}}

    def act(self, tool, args):
        self.calls.append((tool, args))
        return {"ok": True, "result": {}}


def animal(id, race, **kw):
    return {"id": id, "race": race, "tame": True, "adult": True, "female": False,
            "marked_for_slaughter": False, **kw}


class FoodSelection(unittest.TestCase):
    def choose(self, animals, prefer_food):
        game = Game(animals)
        overseer = Overseer(game)
        overseer.count = 0
        overseer.load({"observation": {"workshops": [{"type": "Butchers"}], "stocks": {}}})
        with redirect_stdout(io.StringIO()):
            overseer.butcher(prefer_food=prefer_food)
        return game.calls

    def test_food_prefers_large_adult_over_first_small_animal(self):
        calls = self.choose([animal(1, "RABBIT"), animal(2, "YAK")], True)
        self.assertEqual(calls, [("slaughter", {"unit_id": 2})])

    def test_material_request_keeps_original_selection(self):
        calls = self.choose([animal(1, "RABBIT"), animal(2, "YAK")], False)
        self.assertEqual(calls, [("slaughter", {"unit_id": 1})])

    def test_large_pets_marked_and_untame_animals_remain_excluded(self):
        calls = self.choose([animal(1, "RABBIT"), animal(2, "YAK", pet_owner_id=0),
                             animal(3, "YAK", marked_for_slaughter=True), animal(4, "HORSE", tame=False)], True)
        self.assertEqual(calls, [("slaughter", {"unit_id": 1})])

    def test_juvenile_livestock_does_not_receive_adult_priority(self):
        calls = self.choose([animal(1, "RABBIT"), animal(2, "YAK", adult=False)], True)
        self.assertEqual(calls, [("slaughter", {"unit_id": 1})])

    def test_prefers_male_within_large_adult_candidates(self):
        calls = self.choose([animal(1, "RABBIT"), animal(2, "YAK", female=True), animal(3, "COW")], True)
        self.assertEqual(calls, [("slaughter", {"unit_id": 3})])


if __name__ == "__main__":
    unittest.main()
