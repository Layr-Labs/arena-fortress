"""cx stray cull (owner 2026-11-12, narrow form). In hint hard OP1-2 on bb1feb6 the stray guineahen struck 7 citizens
from day 251 (one the furnace operator's head on day 273, killed by a stray yak bull on day 288) and the stray blue
peahen 2; e33d381 std MY1-4 a stray goose 4, 9525adc std MY1-3 a stray peacock 2. A stray that strikes a citizen is
now marked for slaughter; pets with an owner and strays that never attacked are left (the MY1 plan's F meat). No
game."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_danger_marks import Quiet  # noqa: E402
from test_grazer_shaft import AnimalGame, beast, fort119  # noqa: E402
from overseer import harness  # noqa: E402

HEN = "The stray guineahen snatches at the carpenter in the left lower leg with her first toe, left foot, bruising " \
      "the muscle through the (llama wool dress)!"
PEAHEN = "The stray blue peahen snatches at the bowyer in the left lower arm with her first toe, left foot, bruising " \
         "the fat through the (cave spider silk dress)!"
GOOSE = "The stray goose bites the miner in the head, denting the skin and bruising the muscle!"
YAK = "The stray yak bull kicks the fisherdwarf in the left upper leg with his left rear hoof, bruising the fat!"
DOG_FIGHT = "The stray doe rabbit attacks the stray dog but She rolls away!"
KEA = "The kea bites the miner in the head!"

ANIMALS = [beast(106, "BIRD_GUINEAFOWL"), beast(206, "BIRD_GUINEAFOWL", adult=False),
           beast(107, "BIRD_PEAFOWL_BLUE"), beast(120, "BIRD_PEAFOWL_BLUE", female=False),
           beast(108, "YAK", female=False, z=169), beast(213, "YAK", female=True, z=169),
           beast(130, "BIRD_GOOSE"), beast(131, "BIRD_GOOSE", pet_owner_id=95),
           beast(100, "DOG"), beast(99, "RABBIT")]


def look(day, events, carpenter=True):
    r = fort119(day)
    o = r["observation"]
    o["recent_events"] = list(events)
    o["workshops"] = [{"id": 5, "type": "Butchers", "built": True, "x": 99, "y": 103, "z": 168}]
    for p in o.get("dwarves", []):
        p["profession"] = p.get("profession") or "Miner"
    o["dwarves"] = list(o.get("dwarves", [])) + [
        {"id": 900, "profession": "Carpenter", "x": 1, "y": 1, "z": 168},
        {"id": 901, "profession": "Bowyer", "x": 1, "y": 1, "z": 168},
        {"id": 902, "profession": "Fisherdwarf", "x": 1, "y": 1, "z": 168},
        {"id": 903, "profession": "Miner", "x": 1, "y": 1, "z": 168}]
    return r


class Spec(unittest.TestCase):
    def test_caste_words(self):
        self.assertEqual(harness.stray_spec("guineahen"), ("GUINEAFOWL", True, True))
        self.assertEqual(harness.stray_spec("blue peahen"), ("PEAFOWL", True, True))
        self.assertEqual(harness.stray_spec("yak bull"), ("YAK", False, True))
        self.assertEqual(harness.stray_spec("turkey hen"), ("TURKEY", True, True))
        self.assertEqual(harness.stray_spec("keet"), ("GUINEAFOWL", None, False))
        self.assertEqual(harness.stray_spec("goose"), ("GOOSE", None, None))
        self.assertEqual(harness.stray_spec("hen")[0], "CHICKEN")
        self.assertIsNone(harness.stray_spec("strange beast")[0])


class Cull(Quiet):
    def setUp(self):
        super().setUp()
        self.game = AnimalGame(ANIMALS)
        self.ov = harness.Overseer(self.game, days=336)

    def run_day(self, day, events):
        self.ov.load(look(day, events))
        self.ov.count = 0
        self.game.calls.clear()
        self.ov.stray_cull()
        return [a["unit_id"] for t, a in self.game.calls if t == "slaughter"]

    def test_nothing_without_an_attack(self):
        self.assertEqual(self.run_day(250, [DOG_FIGHT, KEA]), [])

    def test_the_guineahen_that_struck_is_marked_not_the_keet(self):
        self.assertEqual(self.run_day(251, [HEN]), [106])

    def test_sex_picks_the_peahen_and_the_yak_bull(self):
        self.assertEqual(self.run_day(280, [PEAHEN]), [107])
        self.assertEqual(self.run_day(281, [YAK]), [108])   # on the surface too (z169); the yak cow is left

    def test_an_owned_goose_is_never_taken(self):
        self.assertEqual(self.run_day(180, [GOOSE]), [130])

    def test_a_report_counts_once(self):
        self.assertEqual(self.run_day(251, [HEN]), [106])
        for a in self.game.animals:
            if a["id"] == 106:
                a["marked_for_slaughter"] = True
        self.assertEqual(self.run_day(252, [HEN]), [])

    def test_no_shop_builds_one(self):
        r = look(251, [HEN])
        r["observation"]["workshops"] = []
        self.ov.load(r)
        self.ov.count = 0
        built = []
        self.ov.build = lambda wtype, *a, **kw: built.append(wtype)
        self.ov.stray_cull()
        self.assertEqual(built, ["Butchers"])

    def test_off_switch(self):
        old = harness.STRAY_CULL
        harness.STRAY_CULL = False
        try:
            self.assertEqual(self.run_day(251, [HEN]), [])
        finally:
            harness.STRAY_CULL = old


if __name__ == "__main__":
    unittest.main()
