"""Offline regressions for the manager's office on every task: from about 20 citizens DF validates no order until the
manager has an office with a chair, the chair's own order included. A local full-year game made the office over a
7x3 level with no open floor (site A4), its chair was refused six times, and from day 210, at 21 citizens, no bed,
chair, brew or meal order was validated again. Here the office goes on open floor, its chair goes in when the zone
is made, and an office whose site refuses the chair is handed on and made again elsewhere. Stub game; no DF.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from overseer.harness import DAY, OFFICE_FAILS, Overseer  # noqa: E402
from support import StubGame, resp  # noqa: E402

STAIRS = {"id": "A4", "kind": "A", "x": 88, "y": 92, "z": 105, "w": 7, "h": 3, "open_tiles": 0}
HALL = {"id": "A7", "kind": "A", "x": 88, "y": 92, "z": 103, "w": 13, "h": 7, "open_tiles": 40}
SPARE = {"id": "A9", "kind": "A", "x": 80, "y": 90, "z": 101, "w": 9, "h": 5, "open_tiles": 20}
SHARED = [{"id": 8, "type": "Dormitory", "x": 88, "y": 92, "z": 103, "w": 13, "h": 7, "furniture": {"bed": 19}},
          {"id": 12, "type": "DiningHall", "x": 88, "y": 92, "z": 103, "w": 13, "h": 7, "furniture": {"chair": 11}}]


class OfficeGame(StubGame):
    """place_furniture is refused (no_space) on the sites in `no_floor`; make_zone answers with a new zone id."""

    def __init__(self, no_floor=()):
        super().__init__()
        self.no_floor = set(no_floor)
        self.zone_id = 40

    def act(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool == "place_furniture" and args.get("site") in self.no_floor:
            return {"ok": False, "error_code": "no_space",
                    "error": "no free floor tile in 88,92,105 (7x3): every tile is wall, undug, built on or designated"}
        if tool == "make_zone":
            self.zone_id += 1
            return {"ok": True, "result": {"zone": args.get("kind"), "zone_id": self.zone_id}}
        return {"ok": True, "result": {}}


def fort(day, office=None, sites=(STAIRS, HALL), chairs=1, cit=21):
    """A fort at `day` with `cit` citizens; dwarf 0 is the manager; `office` is its office zone (owner, chair)."""
    r = resp(100, day, food=200, cit=cit)
    o = r["observation"]
    o["dwarves"][0]["positions"] = ["MANAGER"]
    o["administrators"].update(MANAGER_id=0, manager_required_office=1, manager_office="none")
    o["zones"] = [dict(z) for z in SHARED]
    if office:
        o["zones"].append(office)
        if office.get("owner") == 0:
            o["administrators"]["manager_office"] = {"zone_id": office["id"],
                                                     "chair": bool(office["furniture"].get("chair"))}
    o["map"]["sites"] = [dict(s) for s in sites]
    o["stocks"]["furniture_free"] = {"chair": chairs}
    return r


def stairs_office(owner=0):
    return {"id": 31, "type": "Office", "x": 88, "y": 92, "z": 105, "w": 7, "h": 3, "owner": owner, "furniture": {}}


def overseer(g):
    ov = Overseer(g, goal="Run the fortress", days=336)
    ov.set_task({"goal": "Run the fortress for 336 days."})
    ov.count = 0
    return ov


def office_pass(ov, r):
    ov.load(r)
    ov.office()


class Office(unittest.TestCase):
    def test_a_new_office_goes_on_open_floor_and_gets_its_chair_on_a_full_year_task(self):
        g = OfficeGame(no_floor={"A4"})
        ov = overseer(g)
        office_pass(ov, fort(117, sites=(STAIRS, HALL, SPARE), cit=16))
        self.assertEqual(g.tools("make_zone"), [{"kind": "office", "site": "A9"}])   # not A4 (no floor), not the hall
        self.assertEqual(g.tools("place_furniture"), [{"kind": "chair", "site": "A9"}])
        self.assertFalse(ov.surge)

    def test_the_dining_level_is_the_last_choice(self):
        g = OfficeGame()
        ov = overseer(g)
        office_pass(ov, fort(117, sites=(STAIRS, HALL), cit=16))
        self.assertEqual(g.tools("make_zone"), [{"kind": "office", "site": "A7"}])   # the only open floor left

    def test_an_office_whose_site_refuses_the_chair_is_handed_on_and_made_again(self):
        g = OfficeGame(no_floor={"A4"})
        ov = overseer(g)
        day = 129
        for _ in range(OFFICE_FAILS):                      # the recorded game: every chair refused for want of floor
            office_pass(ov, fort(day, office=stairs_office()))
            day += 2
        self.assertEqual(len(g.tools("place_furniture")), OFFICE_FAILS)
        self.assertIn(31, ov.office_bad)
        office_pass(ov, fort(day, office=stairs_office()))                     # handed to a citizen with no position
        self.assertEqual(g.tools("assign_zone"), [{"zone_id": 31, "dwarf_id": 1}])
        day += 2
        office_pass(ov, fort(day, office=stairs_office(owner=1)))              # the manager has none: a new one
        self.assertEqual(g.tools("make_zone"), [{"kind": "office", "site": "A7"}])
        self.assertEqual(g.tools("place_furniture")[-1], {"kind": "chair", "site": "A7"})
        self.assertEqual(g.tools("assign_zone"), [{"zone_id": 31, "dwarf_id": 1}])   # the given-up one is not taken back

    def test_a_good_office_keeps_its_chair_rule(self):
        g = OfficeGame()
        ov = overseer(g)
        office = {"id": 50, "type": "Office", "x": 80, "y": 90, "z": 101, "w": 9, "h": 5, "owner": 0, "furniture": {}}
        office_pass(ov, fort(140, office=office, sites=(STAIRS, HALL, SPARE)))
        self.assertEqual(g.tools("place_furniture"), [{"kind": "chair", "site": "A9"}])
        self.assertEqual((g.tools("assign_zone"), g.tools("make_zone")), ([], []))

    def test_nothing_below_fourteen_citizens_or_with_a_chair(self):
        g = OfficeGame()
        ov = overseer(g)
        office_pass(ov, fort(60, cit=13))
        done = dict(stairs_office(), furniture={"chair": 1})
        office_pass(ov, fort(200, office=done))
        self.assertEqual(g.calls, [])


if __name__ == "__main__":
    unittest.main()
