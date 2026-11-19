"""A Butchers whose construction nobody takes is built again on another site (Overseer.load, shops, workshops).

Seen in recorded full-year games: on some sites the construction job was never suspended and never taken, for the
120 to 190 days left of the game, while every other site on the same map was built on within two days."""
import json
import unittest

from support import DAY, bare, overseer
from overseer.harness import STUCK_DAYS, STUCK_REBUILDS

SITES = [{"id": "W%d" % i, "kind": "W"} for i in (1, 2, 3, 4, 5)]


def shop(i, built=False, suspended=False, wtype="Butchers"):
    job = {"job": "ConstructBuilding"}
    if suspended:
        job["suspended"] = True
    return {"type": wtype, "built": built, "id": i, "x": 80 + i, "y": 94, "z": 132,
            "job_details": [] if built else [job], "jobs": [] if built else ["ConstructBuilding"]}


def fort(day, *extra, sites=SITES):
    r = bare(336 - day, day, fishing=False)
    r["observation"]["map"]["sites"] = [dict(s) for s in sites]
    r["observation"]["workshops"] += [dict(w) for w in extra]
    return r


def builds(g):
    return [a for a in g.tools("build_workshop") if a.get("type") == "Butchers"]


def started(day=150):
    """A fort whose layer ordered its Butchers on W1 at `day` (a hunger cull)."""
    ov, g = overseer(fort(day))
    ov.build("Butchers")
    assert builds(g) == [{"type": "Butchers", "site": "W1"}]
    return ov, g


class UnbuiltButchers(unittest.TestCase):
    def test_a_butchers_nobody_builds_is_ordered_again_on_the_next_site(self):
        ov, g = started()
        ov.load(fort(151, shop(53), sites=SITES[1:]))
        ov.workshops()
        self.assertEqual(len(builds(g)), 1)                     # one day on: it may still be on its way
        ov.load(fort(151 + STUCK_DAYS, shop(53), sites=SITES[1:]))
        self.assertNotIn("Butchers", ov.shops())
        ov.workshops()
        self.assertEqual(builds(g)[1:], [{"type": "Butchers", "site": "W2"}])

    def test_a_butchers_that_was_built_is_left_alone(self):
        ov, g = started()
        ov.load(fort(151, shop(53), sites=SITES[1:]))
        ov.load(fort(151 + STUCK_DAYS, shop(53, built=True), sites=SITES[1:]))
        self.assertIn("Butchers", ov.shops())
        ov.workshops()
        self.assertEqual(len(builds(g)), 1)

    def test_the_clock_runs_from_the_first_sight_of_each_shop(self):
        ov, g = started()
        ov.load(fort(151, shop(53), sites=SITES[1:]))
        ov.load(fort(151 + STUCK_DAYS, shop(53), sites=SITES[1:]))
        ov.workshops()                                          # the second, on W2
        ov.load(fort(152 + STUCK_DAYS, shop(53), shop(54), sites=SITES[2:]))
        self.assertIn("Butchers", ov.shops())                   # the new one has had a day: no third yet
        ov.workshops()
        self.assertEqual(len(builds(g)), 2)

    def rebuilds(self, wtype, suspended):
        """Builds of `wtype` accepted while every listed one stays stuck, with five sites to use."""
        ov, g = overseer(fort(150, sites=SITES))
        if wtype != "Butchers":      # a core workshop: the fort starts without it
            r = fort(150, sites=SITES)
            r["observation"]["workshops"] = [w for w in r["observation"]["workshops"] if w["type"] != wtype]
            ov.load(r)
        day, listed = 150, []
        for n in range(8):
            ov.workshops()
            made = [a for a in g.tools("build_workshop") if a.get("type") == wtype]
            if len(made) > len(listed):
                listed.append(shop(53 + len(listed), suspended=suspended, wtype=wtype))
            day += 1
            r = fort(day, *listed, sites=SITES[len(listed):])
            r["observation"]["workshops"] = [w for w in r["observation"]["workshops"]
                                             if w["type"] != wtype or w.get("id") is not None]
            ov.load(r)
            day += STUCK_DAYS + 1
            r = json.loads(json.dumps(r))
            r.update(day=day, days_left=336 - day, tick=day * DAY)
            r["observation"]["date"]["abs_tick"] = day * DAY
            ov.load(r)
        return [a["site"] for a in g.tools("build_workshop") if a.get("type") == wtype]

    def test_a_stuck_butchers_is_built_again_while_a_site_is_listed(self):
        ov, g = started()
        ov.load(fort(151, shop(53), sites=SITES[1:]))
        listed = [shop(53, suspended=True)]
        day = 151
        for n in range(1, 8):
            day += STUCK_DAYS + 1
            ov.load(fort(day, *listed, sites=SITES[len(listed):]))
            ov.workshops()
            if len(builds(g)) > len(listed):
                listed.append(shop(53 + len(listed), suspended=True))
                ov.load(fort(day, *listed, sites=SITES[len(listed):]))
        self.assertEqual([a["site"] for a in builds(g)], ["W1", "W2", "W3", "W4", "W5"])

    def test_a_stuck_core_workshop_keeps_the_rebuild_limit(self):
        self.assertEqual(len(self.rebuilds("Carpenters", suspended=True)), 1 + STUCK_REBUILDS)

    def test_other_workshops_keep_the_suspended_rule_only(self):
        ov, g = overseer(fort(20, shop(9, wtype="Craftsdwarfs")))
        ov.load(fort(20 + 2 * STUCK_DAYS, shop(9, wtype="Craftsdwarfs")))
        self.assertIn("Craftsdwarfs", ov.shops())

    def test_an_unreadable_listing_does_not_restart_the_clock(self):
        ov, g = started()
        ov.load(fort(151, shop(53), sites=SITES[1:]))
        r = fort(152, sites=SITES[1:])
        r["observation"]["workshops"] = "ERR: scripted"
        ov.load(r)
        ov.load(fort(151 + STUCK_DAYS, shop(53), sites=SITES[1:]))
        self.assertNotIn("Butchers", ov.shops())


if __name__ == "__main__":
    unittest.main()
