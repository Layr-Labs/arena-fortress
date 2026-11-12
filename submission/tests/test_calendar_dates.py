"""cx stage B (CX_REVIEW P2, owner-approved): the run-day dates read off the game calendar (date.day_of_year) when it
is observed — OP1 records start at doy 15 and MY1 at doy 135, so the old run days (OP1 crafts 90/200, liaison 120,
winter plan 220; MY1 winter plan 100) are the same calendar days — and events arm what they announce: the caravan's
or a liaison's arrival the head office, "Needs logs" the bone crafts, autofarm's fallow the harvest-closed hold. No
game or network."""
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from overseer import harness

assert Path(harness.__file__).is_relative_to(VARIANT), harness.__file__

import test_head_office as tho   # noqa: E402


class FakeGame:
    def __init__(self):
        self.calls = []

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        return {"ok": True, "result": {"order_id": len(self.calls), "zone_id": 77}}


def ov_at(day, doy=None, days=336, stocks=None, plots=None, cancels=(), orders=()):
    ov = harness.Overseer(FakeGame(), days=days)
    date = {"abs_tick": day * harness.DAY}
    if doy is not None:
        date["day_of_year"] = doy
    obs = {"date": date, "administrators": {"citizens": 12}, "stocks": dict(stocks or {}), "map": {"sites": []},
           "recent_cancellations": list(cancels), "orders": list(orders)}
    if plots is not None:
        obs["farm_plots"] = plots
    ov.load({"day": day, "tick": day * harness.DAY, "days_left": days - day, "observation": obs})
    return ov


class Quiet(unittest.TestCase):
    def setUp(self):
        self.output = redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)


class CalendarDays(Quiet):
    def test_the_records_start_days_map_to_the_old_run_days(self):
        op1 = ov_at(50, doy=65)            # OP1: day 0 = doy 15
        self.assertEqual(op1.calendar_day(harness.WINTER_PLAN_DOY, -1), 220)
        self.assertEqual(op1.calendar_day(harness.LIAISON_OFFICE_DOY, -1), harness.LIAISON_OFFICE_DAY)
        self.assertEqual([op1.calendar_day(x, -1) for x in harness.CRAFT_CHECKPOINT_DOYS],
                         [c[0] for c in harness.CRAFT_CHECKPOINTS])
        my1 = ov_at(50, doy=185, days=216)   # MY1: day 0 = doy 135
        self.assertEqual(my1.calendar_day(harness.WINTER_PLAN_DOY, -1), 100)

    def test_a_different_start_moves_the_dates_with_the_calendar(self):
        ov = ov_at(10, doy=95)   # a run that starts at doy 85 (summer)
        self.assertEqual(ov.calendar_day(harness.WINTER_PLAN_DOY, -1), 150)
        self.assertEqual(ov.craft_checkpoint()[0], 20)   # doy 105

    def test_no_calendar_keeps_the_run_day_form(self):
        ov = ov_at(10)
        self.assertEqual(ov.calendar_day(harness.WINTER_PLAN_DOY, 220), 220)
        self.assertEqual(ov.craft_checkpoint()[0], 90)


class Events(Quiet):
    def test_the_caravan_or_a_liaison_arms_the_head_office_early(self):
        game = tho.FakeGame()
        ov = harness.Overseer(game, days=336)
        ov.load(tho.facts(day=60, zones=(tho.MGR_OFFICE,)))
        ov.sites, ov.count = [dict(tho.ROOM), dict(tho.LEVEL)], 0
        ov.head_offices()
        self.assertEqual(game.calls, [])                 # day 60: not due
        ov.liaison_seen = True
        ov.head_offices()
        self.assertTrue(any(t == "make_zone" for t, _ in game.calls))
        game2 = tho.FakeGame()
        ov2 = harness.Overseer(game2, days=336)
        ov2.load(tho.facts(day=60, zones=(tho.MGR_OFFICE,)))
        ov2.sites, ov2.count = [dict(tho.ROOM), dict(tho.LEVEL)], 0
        ov2.caravan_arrival_day = 58
        ov2.head_offices()
        self.assertTrue(any(t == "make_zone" for t, _ in game2.calls))

    def test_needs_logs_stalls_the_wood_crafts_at_once(self):
        wood = {"id": 5, "job": "MakeCrafts", "repeat": "daily", "left": 3, "material_category": ["wood"]}
        ov = ov_at(200, orders=[wood], cancels=["Urist, Woodcrafter cancels Make wooden crafts: Needs logs."])
        self.assertTrue(ov.craft_stalled())
        ov = ov_at(200, orders=[wood])
        self.assertFalse(ov.craft_stalled())   # no history and no cancel: not yet

    def test_autofarm_fallow_closes_the_harvest_before_the_next_turn(self):
        plump = {"plump helmet": {"n": 9, "seasons": ["spring", "summer", "autumn", "winter"]}}
        fallow = [{"id": 1, "crop_this_season": "none", "seeds_or_crops_in_plot": 0}]
        # 20 days left, 30 to the season turn: autofarm fallowed although the 42-day sum calls it open
        ov = ov_at(196, doy=222, days=216, stocks={"seeds": 9, "seeds_by_kind": plump}, plots=fallow)
        self.assertTrue(ov.harvest_closed())
        planted = [{"id": 1, "crop_this_season": "MUSHROOM_HELMET_PLUMP", "seeds_or_crops_in_plot": 3}]
        ov = ov_at(196, doy=222, days=216, stocks={"seeds": 9, "seeds_by_kind": plump}, plots=planted)
        self.assertFalse(ov.harvest_closed())
        # the season turns inside the run: autofarm decides again, so the fallow alone closes nothing
        ov = ov_at(100, doy=222, days=216, stocks={"seeds": 9, "seeds_by_kind": plump}, plots=fallow)
        self.assertFalse(ov.harvest_closed())


if __name__ == "__main__":
    unittest.main()
