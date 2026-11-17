"""Replay a real cap-blocked OP1 observation; no simulation of DF's seed production."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from overseer.harness import DAY, Overseer
from support import StubGame

FACTS = json.loads((Path(__file__).parent / "fixtures/op1-seed-depletion.json").read_text())["response"]


class SeedRecovery(unittest.TestCase):
    def setUp(self):
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def play(self, facts=None):
        g = StubGame()
        ov = Overseer(g, days=336)
        ov.set_task({"goal": "Run the fortress for 336 days."})
        ov.load(copy.deepcopy(FACTS if facts is None else facts))
        ov.count = 0
        return ov, g

    def recovery(self, game):
        return [a for a in game.tools("add_order") if a.get("recipe") == "brew_drink"
                and not a.get("repeat")]

    def test_real_seedless_cap_blocked_observation_requests_one_brew_job(self):
        ov, game = self.play()
        ov.supply()
        self.assertEqual(self.recovery(game), [{"recipe": "brew_drink", "amount": 1}])

    def test_pending_one_shot_blocks_duplicate_but_daily_cap_order_does_not(self):
        facts = copy.deepcopy(FACTS)
        facts["observation"]["orders"].append({"recipe": "brew_drink", "left": 1, "id": 90})
        ov, game = self.play(facts)
        ov.supply()
        self.assertEqual(self.recovery(game), [])

    def test_retries_are_spaced_and_resume_after_refusal(self):
        ov, game = self.play()
        game.refuse = {("add_order", None)}
        ov.supply()
        ov.now += 3 * DAY
        ov.supply()
        self.assertEqual(len(self.recovery(game)), 1)
        game.refuse.clear()
        ov.now += DAY
        ov.supply()
        self.assertEqual(len(self.recovery(game)), 2)

    def test_no_override_when_seed_facts_missing_or_supply_not_ready(self):
        for field, value in (("seeds", None), ("seeds", 10), ("drink", 299),
                             ("plants_brewable", 1), ("barrels_empty", 0)):
            with self.subTest(field=field, value=value):
                facts = copy.deepcopy(FACTS)
                facts["observation"]["stocks"][field] = value
                ov, game = self.play(facts)
                ov.supply()
                self.assertEqual(self.recovery(game), [])

    def test_preserves_hands_off_and_final_feast_policies(self):
        for mode in ("lab", "feast", "stopped"):
            with self.subTest(mode=mode):
                ov, game = self.play()
                if mode == "lab":
                    ov.set_task({"goal": "Keep drink flowing", "hands_off": {"from_day": 39}})
                elif mode == "feast":
                    ov.days_left = 1
                else:
                    ov.brew_stopped = True
                ov.supply()
                self.assertEqual(self.recovery(game), [])


if __name__ == "__main__":
    unittest.main()
