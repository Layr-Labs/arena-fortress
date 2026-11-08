"""The digest's wealth line: created wealth against the Hamlet rank, from the observation (the layer's copy is the
fallback for observations without the field). No game or network is used."""
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from plain import digest

assert Path(digest.__file__).is_relative_to(VARIANT), digest.__file__

ENV = {"day": 45, "tick": 45 * digest.DAY, "days_left": 100}


def obs(**over):
    o = {"administrators": {"citizens": 8}, "stocks": {}}
    o.update(over)
    return o


class WealthLine(unittest.TestCase):
    def test_observation_wealth_is_reported_against_the_target(self):
        text = digest.digest(obs(wealth={"created": 1200, "crafted": 900, "raw_logs_value": 55}), ENV)
        self.assertIn("wealth: created 1200 / target 5500", text)
        self.assertIn("22%", text)
        self.assertIn("gap 4300", text)
        self.assertIn("crafted 900", text)

    def test_layer_wealth_is_the_fallback(self):
        text = digest.digest(obs(), ENV, layer={"wealth": {"created": 6000}})
        self.assertIn("wealth: created 6000 / target 5500", text)
        self.assertIn("100%", text)

    def test_no_wealth_line_without_a_source(self):
        self.assertNotIn("wealth:", digest.digest(obs(), ENV))
        self.assertNotIn("wealth:", digest.digest(obs(), ENV, layer={}))

    def test_progression_hint_once_the_layer_builds_crafts(self):
        text = digest.digest(obs(wealth={"created": 1200}), ENV)   # day 45, 8 citizens, below target
        self.assertIn("progression", text)
        early = digest.digest(obs(wealth={"created": 1200}), {"day": 10, "tick": 10 * digest.DAY})
        self.assertNotIn("progression", early)
        done = digest.digest(obs(wealth={"created": 6000}), ENV)
        self.assertNotIn("progression", done)

    def test_compact_observation_still_strips_wealth(self):
        self.assertNotIn("wealth", digest.compact_observation(obs(wealth={"created": 1})))


if __name__ == "__main__":
    unittest.main()
