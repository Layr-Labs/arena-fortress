"""Opening tier-2: autolabor by day 2 and a monthly chair mill by day ~8.

Forensics (reports/my1-opening-economics.md): the top MY1 runs enable
autolabor on days 2-9 and run one standing monthly make_chair order.
This test pins the scripted tier. No game, no network.

Tier-3 (reports/tier3-levers.md): the fish->meal manager order — the
whole MY1 food gap — must be scripted at day 10 once a manager exists.
"""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

DAY = harness.DAY


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {}}


def obs(abs_tick, plugins=None, logs=8, chairs=3, orders=None):
    return {"day": abs_tick // DAY, "observation": {
        "date": {"abs_tick": abs_tick},
        "administrators": {"citizens": 7, "manager_active_for_orders": True},
        "stocks": {"logs_usable": logs, "furniture_free": {}},
        "furniture": [{"kind": "chair"}] * chairs,
        "orders": orders if orders is not None else [],
        "plugins": plugins if plugins is not None
        else {"autochop": "on", "seedwatch": "on"},
        "map": {"sites": []},
        "dwarves": [],
        "farm_plots": [],
    }}


def manage(abs_tick, **kw):
    game = FakeGame()
    ov = harness.Overseer(game)
    with redirect_stdout(io.StringIO()):
        ov.load(obs(abs_tick, **kw))
        ov.management()
    return game.calls


def names(calls):
    return [(t, a.get("name") or a.get("recipe")) for t, a in calls]


class OpeningTier(unittest.TestCase):
    def test_autolabor_armed_from_day_two(self):
        c = manage(2 * DAY)
        self.assertIn(("enable_automation", "autolabor"), names(c))

    def test_autolabor_not_before_day_two(self):
        c = manage(1 * DAY)
        self.assertNotIn(("enable_automation", "autolabor"), names(c))

    def test_autolabor_skipped_when_already_on(self):
        c = manage(4 * DAY, plugins={"autochop": "on", "seedwatch": "on",
                                     "autolabor": "on"})
        self.assertNotIn(("enable_automation", "autolabor"), names(c))

    def test_chair_mill_armed_from_day_eight(self):
        c = manage(8 * DAY)
        chairs = [a for t, a in c if t == "add_order"
                  and a.get("recipe") == "make_chair"]
        self.assertEqual(len(chairs), 1)
        self.assertEqual(chairs[0]["repeat"], "monthly")
        self.assertEqual(chairs[0]["amount"], 5)

    def test_chair_mill_not_duplicated_when_standing(self):
        standing = [{"recipe": "make_chair", "repeat": "monthly"}]
        c = manage(9 * DAY, orders=standing)
        self.assertFalse([a for t, a in c if t == "add_order"
                          and a.get("recipe") == "make_chair"])

    def test_chair_mill_respects_logs_and_cap(self):
        for kw in ({"logs": 2}, {"chairs": 40}):
            c = manage(9 * DAY, **kw)
            self.assertFalse([a for t, a in c if t == "add_order"
                              and a.get("recipe") == "make_chair"], kw)

    def test_no_chair_mill_before_day_eight(self):
        c = manage(4 * DAY)
        self.assertFalse([a for t, a in c if t == "add_order"
                          and a.get("recipe") == "make_chair"])

    def test_meal_order_armed_from_day_ten(self):
        c = manage(10 * DAY)
        meals = [a for t, a in c if t == "add_manager_order"]
        self.assertEqual(len(meals), 1)
        self.assertEqual(meals[0]["job"], "PrepareMeal")
        self.assertEqual(meals[0]["repeat"], "daily")

    # frontier-v4-no-hatch ablation: the two tests here previously pinned the
    # scripted day-12 make_hatch_cover mill x4. This candidate removes that
    # scripted policy (GLM may still issue hatch orders itself); see
    # reports/no-hatch-build.md for provenance and rationale.
    def test_no_scripted_hatch_order_at_high_logs(self):
        for tick in (12 * DAY, 20 * DAY, 30 * DAY):
            for logs in (6, 8, 20):
                c = manage(tick, logs=logs)
                self.assertFalse(
                    [a for t, a in c if t == "add_order"
                     and a.get("recipe") == "make_hatch_cover"],
                    msg=f"tick={tick} logs={logs}")

    def test_hatch_orders_left_to_glm_not_scripted(self):
        # A GLM-issued standing hatch order must pass through untouched and
        # the removal must not add any hatch order of its own.
        standing = [{"recipe": "make_hatch_cover", "repeat": "daily"}]
        c = manage(30 * DAY, orders=standing)
        self.assertFalse([a for t, a in c if t == "add_order"
                          and a.get("recipe") == "make_hatch_cover"])

    def test_other_managed_actions_survive_hatch_removal(self):
        c = manage(30 * DAY)
        n = names(c)
        self.assertIn(("enable_automation", "autolabor"), n)
        self.assertTrue([a for t, a in c if t == "add_order"
                         and a.get("recipe") == "make_chair"], "chair")
        self.assertTrue([a for t, a in c if t == "add_manager_order"
                         and a.get("job") == "PrepareMeal"], "meal")

    def test_meal_order_not_before_day_ten_or_without_manager(self):
        c = manage(9 * DAY)
        self.assertFalse([t for t, a in c if t == "add_manager_order"
                          and a.get("job") == "PrepareMeal"])
        game = FakeGame()
        ov = harness.Overseer(game)
        resp = obs(12 * DAY)
        resp["observation"]["administrators"]["manager_active_for_orders"] = False
        with redirect_stdout(io.StringIO()):
            ov.load(resp)
            ov.management()
        self.assertFalse([t for t, a in game.calls if t == "add_manager_order"])

    def test_meal_order_not_duplicated_when_active(self):
        standing = [{"job": "PrepareMeal", "repeat": "daily"}]
        c = manage(30 * DAY, orders=standing)
        self.assertFalse([a for t, a in c if t == "add_manager_order"
                          and a.get("job") == "PrepareMeal"])


if __name__ == "__main__":
    unittest.main()
