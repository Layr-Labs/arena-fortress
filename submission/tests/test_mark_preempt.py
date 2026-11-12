"""cx pre-emptive alert (hint std OP1-0 on 9c4ec71). A gray langur troop of 7, never seen before, stood at the day-269.25
look 37-46 tiles from the expedition leader on the surface (z162) and 59-68 from the wagon — past WILD_NEAR_TILES, so
no alert — and was brawling with the bone carver, the brewer and a dwarven child by day 269.75; 4-5 of 20 citizens
stayed stressed to day 336 (wellbeing 0.85). Now a species that has just arrived (not seen within MARK_RANGE for
MARK_NEW_DAYS) sounds the alert while within PREEMPT_TILES of a citizen outside. No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_danger_marks import FakeGame, Quiet, fort  # noqa: E402
from overseer import harness  # noqa: E402

# the record's own positions (cx9c4ec71 hint std OP1-0, day 269 observe and units query)
LEADER = {"id": 100, "name": "Ustuth Oslankir, expedition leader", "profession": "expedition leader",
          "x": 117, "y": 118, "z": 162}
CHILD = {"id": 292, "name": "Ducim Oddomendok, Dwarven Child", "profession": "Dwarven Child", "adult": False,
         "x": 103, "y": 104, "z": 162}
LEADER_IN = dict(LEADER, z=161)
CHILD_IN = dict(CHILD, z=161)
TROOP = [{"id": 334, "race": "GRAY_LANGUR", "hostile": False, "x": 154, "y": 81, "z": 162},
         {"id": 333, "race": "GRAY_LANGUR", "hostile": False, "x": 155, "y": 86, "z": 162},
         {"id": 331, "race": "GRAY_LANGUR", "hostile": False, "x": 156, "y": 84, "z": 162}]


def op1(day, dwarves, alert=False):
    r = fort(day, alert=alert, dwarves=dwarves)
    o = r["observation"]
    o["map"]["wagon"] = {"present": True, "x": 95, "y": 95, "z": 162}
    o["map"]["surface_z"] = 162
    o["administrators"]["citizens"] = len(dwarves)
    o["burrows"]["list"] = [{"id": 0, "civ_alert_burrow": True, "name": "Shelter",
                             "citizens_inside": sum(1 for x in dwarves if x["z"] < 162)}]
    return r


class PreEmpt(Quiet):
    def look(self, ov, game, resp):
        ov.load(resp)
        ov.count = 0
        game.calls.clear()
        ov.mark_guard()
        return [a for t, a in game.calls if t == "civilian_alert"]

    def test_a_troop_arriving_37_tiles_from_a_citizen_outside_sounds_it(self):
        game = FakeGame(TROOP)
        ov = harness.Overseer(game, days=336)
        self.assertEqual(ov.marked_units(harness.WILD_NEAR_TILES, harness.WILD_NEAR_Z,
                                         obs=op1(269, [LEADER, CHILD])["observation"], units=TROOP), [])
        self.assertEqual(self.look(ov, game, op1(269, [LEADER, CHILD])), [{"on": True}])
        self.assertIsNotNone(ov.wild_alert_since)
        self.assertIn("gray langur", ov.wild_watched())   # the owner's hold / lift rules take it from here

    def test_nobody_outside_no_alert(self):
        game = FakeGame(TROOP)
        ov = harness.Overseer(game, days=336)
        self.assertEqual(self.look(ov, game, op1(269, [LEADER_IN, CHILD_IN])), [])

    def test_a_resident_troop_is_not_new(self):
        game = FakeGame(TROOP)
        ov = harness.Overseer(game, days=336)
        for day in range(260, 269):   # seen within MARK_RANGE every day while everyone was below
            self.assertEqual(self.look(ov, game, op1(day, [LEADER_IN, CHILD_IN])), [])
        self.assertEqual(self.look(ov, game, op1(269, [LEADER, CHILD])), [])

    def test_the_window_closes_after_arrival(self):
        game = FakeGame(TROOP)
        ov = harness.Overseer(game, days=336)
        self.assertEqual(self.look(ov, game, op1(267, [LEADER_IN, CHILD_IN])), [])   # arrived, all sheltered
        self.assertEqual(self.look(ov, game, op1(269, [LEADER, CHILD])), [])        # 2 days on: not new

    def test_a_watched_species_keeps_the_evidence_rule(self):
        game = FakeGame(TROOP)
        ov = harness.Overseer(game, days=336)
        ov.wild_watch["gray langur"] = 260 * harness.DAY   # its own alert 9 days ago
        self.assertEqual(self.look(ov, game, op1(269, [LEADER, CHILD])), [])

    def test_beyond_preempt_tiles_no_alert(self):
        game = FakeGame([dict(u, x=u["x"] + 30) for u in TROOP])   # 67+ tiles from the leader
        ov = harness.Overseer(game, days=336)
        self.assertEqual(self.look(ov, game, op1(269, [LEADER, CHILD])), [])

    def test_the_spent_budget_still_bars_it(self):
        game = FakeGame(TROOP)
        ov = harness.Overseer(game, days=336)
        ov.now = 269 * harness.DAY
        ov.wild_spans = [[250 * harness.DAY, 266 * harness.DAY]]   # 16 days inside the window
        self.assertEqual(self.look(ov, game, op1(269, [LEADER, CHILD])), [])


if __name__ == "__main__":
    unittest.main()
