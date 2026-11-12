"""cx shaft child (hint std MY1-4 on 7c43df4, score 80.0: Etur Nishginet, Dwarven Child, dead of INFECTION on day
166.7). The day-83 pass sounded the mark alert for a kea (unit 273) on the surface at (59,97,169) — and in that same
pass read the alert as off (the observation's), so the open-shaft guard (mark_gate, which needs the alert) was passed
over and the all-armed squad went out on the kea itself, 41 tiles west of the open E1 shaft (100,101,169). The next
piece of the model's advance (day 84) ran without a layer pass; on day 85.23 another kea (unit 272, 29 tiles east on
the day-84 look) flew down E1 into the Shelter (the mason at (101,100,168) first) and fought the sheltered civilians
on the stair for 0.7 days; the child (idle at the meeting area over the shaft foot) was knocked out, its head skin
torn and upper lip ripped to shreds. No hospital zone, no medical labor: the wounds were never treated and infected.
Now an alert this pass sounded counts as on for the rest of the pass (the gate goes to the shaft foot, never a
station on the animal while the Shelter is held with a shaft open). No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_danger_marks import FakeGame  # noqa: E402
from test_rescue_station import Look, my14, E1, E2  # noqa: E402
from overseer import harness  # noqa: E402

# the record's own numbers (cx7c43df4 hint std MY1-4, harness-4.api.jsonl lines 418-438)
CHILD = {"id": 266, "name": "Etur Nishginet, Dwarven Child", "profession": "Dwarven Child", "adult": False,
         "x": 93, "y": 99, "z": 169}
MASON = {"id": 100, "name": "Ushat Romekathel, Mason", "profession": "Mason", "x": 75, "y": 97, "z": 169}
KEA_WEST = {"id": 273, "race": "BIRD_KEA", "hostile": False, "x": 59, "y": 97, "z": 169}
KEA_EAST = {"id": 272, "race": "BIRD_KEA", "hostile": False, "x": 129, "y": 93, "z": 173}
SQUAD = {"id": 0, "armed": 4, "uniform": "weapon+armor", "orders": [],
         "members": [{"id": 241 + i, "x": 100 + i, "y": 102, "z": 168} for i in range(4)]}
FOOT = {"order": "station", "x": 100, "y": 101, "z": 169}   # cx SHAFT GUARD TOP: the stair top


class SameDayAlert(Look):
    def test_an_alert_sounded_this_pass_puts_the_squad_at_the_shaft_foot(self):
        game = FakeGame([KEA_WEST, KEA_EAST])
        ov = harness.Overseer(game, days=216)
        calls = self.look(ov, game, my14(83, [CHILD, MASON], alert=False, squads=(SQUAD,)))
        self.assertIn(("civilian_alert", {"on": True}), calls)
        orders = [a for t, a in calls if t == "squad_order"]
        self.assertIn(FOOT, orders)
        self.assertNotIn({"order": "station", "x": 59, "y": 97, "z": 169}, orders)
        self.assertEqual(ov.mark_kind, "mark_gate")

    def test_no_open_shaft_keeps_the_station_on_the_animal(self):
        game = FakeGame([KEA_WEST])
        ov = harness.Overseer(game, days=216)
        calls = self.look(ov, game, my14(83, [CHILD, MASON], alert=False, squads=(SQUAD,), sites=(E2,)))
        self.assertIn(("squad_order", {"order": "station", "x": 59, "y": 97, "z": 169}), calls)
