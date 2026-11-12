"""cx no provoke (hint std / hard OP1-0 on c44c96b, survival 0.76 both). Every entrance had its hatch; a marked
thief (gray langur troop / giant kea, non-hostile) came near and guard_muster (need weak_mark, armed 0) stationed
the squad below to fetch its weapons, beside the mark alert. On duty the soldiers charged the animal: std day 304 the
militia commander struck a langur at the hatches, the troop turned on a carpenter coming in (neck, SUFFOCATE 600
ticks later); hard day 146 unarmed recruits brawled a giant kea, the fisher's ankle was torn (idle 157 days, then
melancholy) and the hammerdwarf stayed stressed. 9c4ec71 met the same langurs with the alert alone: no fight, no
death. Now the wildlife muster goes only while an entrance stands that no hatch or gate closes (the squad there is
the closure); and the rescue station never takes a squad member for the citizen to rescue. No game or network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_guard_equip import Base, my14_squad, SURFACE  # noqa: E402
from test_rescue_station import Look, my14, KEA_BY_CHILD, FIGHT, SQUAD_HALF  # noqa: E402
from test_danger_marks import FakeGame  # noqa: E402
from overseer import harness  # noqa: E402


def stations(calls):
    return [a for t, a in calls if t == "squad_order" and a.get("order") == "station"]


class NoProvoke(Base):
    def test_weak_mark_with_every_entrance_hatched_sends_no_muster(self):
        ov, game = self.ov()
        ov.wild_alert_since = 18 * harness.DAY
        calls = self.pass_(ov, game, 20, squads=[my14_squad()], weapons_free=0, alert=True,
                           building=False, hatch=True)
        self.assertFalse(stations(calls))
        self.assertIsNone(ov.muster)
        self.assertFalse(self.logs("guard_muster"))

    def test_a_standing_muster_stands_down_once_every_entrance_is_closed(self):
        ov, game = self.ov()
        ov.wild_alert_since = 18 * harness.DAY
        calls = self.pass_(ov, game, 20, squads=[my14_squad()], weapons_free=0, alert=True)   # E1 unhatchable
        order = stations(calls)[0]
        ov.wild_alert_since = 18 * harness.DAY
        sq = dict(my14_squad(), orders=[dict(order)])
        calls = self.pass_(ov, game, 21, squads=[sq], weapons_free=0, alert=True, building=False, hatch=True)
        self.assertIn(("squad_order", {"order": "stand_down"}), calls)
        self.assertIsNone(ov.muster)
        self.assertEqual(self.logs("guard_muster_end")[-1]["why"], "need_gone")

    def test_the_unhatchable_entrance_still_musters(self):
        ov, game = self.ov()
        ov.wild_alert_since = 18 * harness.DAY
        calls = self.pass_(ov, game, 20, squads=[my14_squad()], weapons_free=0, alert=True)
        self.assertEqual(len(stations(calls)), 1)
        self.assertLess(stations(calls)[0]["z"], SURFACE)

    def test_invaders_still_muster_with_every_entrance_hatched(self):
        ov, game = self.ov()
        gob = [{"id": 900, "race": "GOBLIN", "invader": True, "x": 60, "y": 98, "z": SURFACE}]
        calls = self.pass_(ov, game, 20, squads=[dict(my14_squad(assigned=False), armed=0)], weapons_free=0,
                           alert=True, hostiles=gob, building=False, hatch=True)
        self.assertTrue(stations(calls))
        self.assertEqual(self.logs("guard_muster")[-1]["need"], "invaders")


class RescueSkipsSoldiers(Look):
    def test_a_squad_member_by_the_animal_is_not_rescued(self):
        soldier = {"id": 2, "name": "Vucar Soshshem, Wrestler", "profession": "Wrestler",
                   "x": 117, "y": 99, "z": 169}
        miner = {"id": 95, "name": "Solon Onolem, Miner", "profession": "Miner", "x": 105, "y": 100, "z": 168}
        game = FakeGame([KEA_BY_CHILD])
        ov = harness.Overseer(game, days=216)
        calls = self.look(ov, game, my14(94, [soldier, miner], events=FIGHT, squads=(SQUAD_HALF,)))
        self.assertNotIn(("squad_order", {"order": "station", "x": 117, "y": 99, "z": 169}), calls)

    def test_mark_threats_skips_the_given_ids(self):
        game = FakeGame([KEA_BY_CHILD])
        ov = harness.Overseer(game, days=216)
        civ = {"id": 361, "x": 117, "y": 99, "z": 169}
        ov.load(my14(94, [dict(civ), {"id": 2, "x": 117, "y": 98, "z": 169}]))
        kea = dict(KEA_BY_CHILD, _mark="kea")
        self.assertEqual([c["id"] for _, c in ov.mark_threats([kea])], [2])
        self.assertEqual([c["id"] for _, c in ov.mark_threats([kea], skip={2})], [361])


if __name__ == "__main__":
    unittest.main()
