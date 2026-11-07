"""Military readiness is public evidence, not invented training or equipment."""
import copy
import unittest

from plain.advisor import Advisor
from plain import prompt


def fort(population=19, hostiles=0):
    return {
        "administrators": {"citizens": population},
        "dwarves": [{"id": i, "adult": True, "positions": [], "stress": 4}
                    for i in range(population)],
        "military": {"squads": [], "weapons_free": 6},
        "threats": {"visible_hostiles": hostiles},
    }


def squad(obs, armed=1, members=2):
    obs["military"]["squads"] = [{
        "id": 8, "armed": armed, "uniform": "weapon+armor", "on_duty": True,
        "members": [{"id": i, "weapon_assigned": True} for i in range(members)],
        "orders": [{"order": "station", "x": 2, "y": 3, "z": 100}],
    }]
    for dwarf in obs["dwarves"][:members]:
        dwarf["squad_id"] = 8


class ReadinessTests(unittest.TestCase):
    def status(self, obs):
        return Advisor().observe(obs, 120000)

    def test_missing_or_failed_military_observation_is_unknown(self):
        for value in (None, "ERR: probe failed", {}):
            obs = {"military": value}
            result = self.status(obs)
            self.assertEqual(result.get("defense", {}), {})
            self.assertNotIn("recruit", " ".join(result["priorities"]).lower())

    def test_seven_founders_are_not_assigned_permanent_peacetime_duty(self):
        result = self.status(fort(7))
        self.assertEqual(result["defense"]["suggested_recruits"], 0)

    def test_growth_allows_a_small_guard_not_a_second_squad(self):
        result = self.status(fort(19))
        self.assertEqual(result["defense"]["suggested_recruits"], 4)
        obs = fort(19)
        squad(obs)
        result = self.status(obs)
        self.assertEqual(result["defense"]["suggested_recruits"], 0)
        self.assertEqual(result["defense"]["squads_listed"], 1)

    def test_recruitment_excludes_children_officials_members_and_unknowns(self):
        obs = fort(19)
        obs["dwarves"] = [
            {"id": 1, "adult": True, "positions": [], "squad_id": -1},
            {"id": 2, "adult": False, "positions": []},
            {"id": 3, "adult": True, "positions": ["MANAGER"]},
            {"id": 4, "adult": True, "positions": [], "squad_id": 8},
            {"id": 5, "adult": True},  # positions unknown, not known empty
            {"id": 6, "positions": []},  # adulthood unknown
            *({"id": i, "adult": True, "positions": ["BROKER"]} for i in range(7, 10)),
        ]
        result = self.status(obs)
        self.assertEqual(result["defense"]["eligible_ids"], [1])
        self.assertEqual(result["defense"]["suggested_recruits"], 1)

    def test_emergency_recruitment_preserves_workers_and_requires_weapons(self):
        obs = fort(7, hostiles=2)
        self.assertEqual(self.status(obs)["defense"]["suggested_recruits"], 2)
        obs["military"]["weapons_free"] = 0
        result = self.status(obs)
        self.assertEqual(result["defense"]["suggested_recruits"], 0)
        self.assertIn("shelter", result["priorities"][0].lower())

    def test_assignment_and_armor_template_do_not_establish_carried_weapons(self):
        obs = fort()
        squad(obs, armed=0)
        result = self.status(obs)
        self.assertEqual(result["defense"]["armed"], 0)
        self.assertEqual(result["defense"]["members_listed"], 2)
        self.assertIn("carried", " ".join(result["priorities"]).lower())
        self.assertNotIn("armor_worn", result["defense"])

    def test_missing_armed_count_does_not_become_zero(self):
        obs = fort()
        squad(obs)
        del obs["military"]["squads"][0]["armed"]
        result = self.status(obs)
        self.assertNotIn("armed", result["defense"])

    def test_threat_advice_survives_a_full_production_checklist(self):
        from test_advisor import fort as troubled_fort
        obs = troubled_fort()
        obs.update(military={"squads": [], "weapons_free": 0}, threats={"visible_hostiles": 3})
        result = self.status(obs)
        self.assertIn("hostile", result["priorities"][0].lower())
        self.assertIn("shelter", result["priorities"][0].lower())
        self.assertLessEqual(len(result["priorities"]), 16)

    def test_stressed_existing_guard_gets_relief_not_impossible_rotation(self):
        obs = fort(7)
        squad(obs, armed=2, members=4)
        obs["dwarves"][0]["stress"] = 0
        result = self.status(obs)
        self.assertEqual(result["defense"]["stressed_members"], 1)
        text = " ".join(result["priorities"]).lower()
        self.assertIn("stand_down", text)
        self.assertNotIn("rotate", text)
        self.assertEqual(result["defense"]["civilians_outside_squads"], 3)

    def test_advice_is_bounded_and_does_not_mutate_public_observation(self):
        obs = fort(500)
        before = copy.deepcopy(obs)
        result = self.status(obs)
        self.assertEqual(obs, before)
        self.assertLessEqual(len(result["defense"]["eligible_ids"]), 10)
        self.assertLessEqual(result["defense"]["suggested_recruits"], 4)

    def test_prompt_explains_no_training_and_requires_readiness_verification(self):
        text = prompt.system_prompt(tool_names={"create_squad", "equip_squad", "squad_order"})
        self.assertIn("STANDING GUARD", text)
        self.assertIn("no training order", text)
        self.assertIn("not training", text)
        self.assertIn("stand_down", text)
        self.assertIn("weapon_assigned", text)
        self.assertIn("one squad", text)

    def test_military_doctrine_not_injected_without_military_tools(self):
        text = prompt.system_prompt(tool_names={"advance_days", "build_farm"})
        self.assertNotIn("STANDING GUARD", text)


if __name__ == "__main__":
    unittest.main()
