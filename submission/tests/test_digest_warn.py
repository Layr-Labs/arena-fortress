"""Digest warnings the model needs before a hands-off window: idle underground plots, and drink that is not rising."""
import unittest
from plain import digest as D


def obs(plots, seeds, drink=500, brewable=0):
    return {"administrators": {"citizens": 47},
            "stocks": {"drink": drink, "food_edible": 100, "plants_brewable": brewable,
                       "seeds_by_kind": {k: {"n": n, "underground": True} for k, n in seeds.items()}},
            "farm_plots": plots, "plugins": {"autofarm": "on", "autochop": "on", "seedwatch": "on"}}


PLOT = {"built": True, "subterranean": True, "crop_this_season": "none"}


class DigestWarn(unittest.TestCase):
    def test_idle_plots_with_seeds_named(self):
        out = D.digest(obs([PLOT] * 8, {"plump helmet": 67}), {"day": 12, "hands_off_in_days": 27}, D.Memory())
        self.assertIn("8 built underground plots show no crop", out)
        self.assertIn("plump helmet 67", out)
        self.assertIn("none x8", out)

    def test_planted_plots_quiet(self):
        planted = dict(PLOT, crop_this_season="MUSHROOM_HELMET_PLUMP")
        out = D.digest(obs([planted] * 8, {"plump helmet": 3}), {"day": 12}, D.Memory())
        self.assertNotIn("show no crop", out)

    def test_drink_warning_only_near_window(self):
        o = obs([], {}, brewable=0)
        self.assertIn("DRINK BEFORE HANDS-OFF (in 10 d)", D.digest(o, {"day": 29, "hands_off_in_days": 10}, D.Memory()))
        self.assertNotIn("DRINK BEFORE", D.digest(o, {"day": 5, "hands_off_in_days": 34}, D.Memory()))
        self.assertNotIn("DRINK BEFORE", D.digest(o, {"day": 5}, D.Memory()))


if __name__ == "__main__":
    unittest.main()
