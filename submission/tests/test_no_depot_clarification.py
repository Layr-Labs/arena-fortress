"""Black-box rendered-prompt checks: the no-depot clarification rides on the ORDERS block.

Port of the previously tested depot-capability clarification onto frontier ab1668c (96.02):
when the server offers add_manager_order, the prompt states the v0 API cannot construct a
depot. The clarification never appears without the manager tool, and the frontier PLAYBOOK,
task-specific ORDERS guidance, STATUS digest text and API sections (4, 6) stay exactly as the
parent renders them.
"""
import sys
import unittest
from pathlib import Path

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
sys.path.insert(0, str(VARIANT / "tests"))
import support  # noqa: E402
from plain import prompt  # noqa: E402

assert Path(support.__file__).is_relative_to(VARIANT), support.__file__

MANUAL = ("## 4. Sites\nsite facts here\n\n## 6. The observation\nobservation facts here\n\n"
          "## 10. Known limits of v0\nlimit facts here\n")
CLARIFICATION = "no depot-construction or trading action"


class NoDepotClarification(unittest.TestCase):
    def render(self, tool_names=None, manual=None):
        return prompt.system_prompt(MANUAL if manual is None else manual, tool_names)

    def test_clarification_present_with_manager_tool_and_by_default(self):
        for names in (None, {"add_order", "add_manager_order"}):
            s = self.render(names)
            self.assertIn("ORDERS BEYOND THE RECIPES", s)
            self.assertIn(CLARIFICATION, s)
            self.assertIn("add_manager_order is not a way to construct a depot", s)
            self.assertIn("guessing alternate", s)

    def test_clarification_absent_from_core_prompt_without_manager_tool(self):
        s = self.render({"add_order", "advance_days"})
        self.assertNotIn(CLARIFICATION, s)
        self.assertNotIn("ORDERS BEYOND THE RECIPES", s)
        self.assertIn("You are the overseer", s)

    def test_manager_tool_and_makcrafts_example_preserved(self):
        s = self.render()
        self.assertIn("e.g. MakeCrafts", s)
        self.assertIn("add_order takes one of its named recipes", s)

    def test_task_specific_orders_guidance_preserved(self):
        s = self.render()
        self.assertIn("TASK-SPECIFIC WORK THE LAYER TAKES CHARGE OF", s)
        self.assertIn("every dwarf must have a placed", s)
        self.assertIn("no drink ceiling", s)

    def test_playbook_digest_and_api_sections_unchanged(self):
        s = self.render()
        self.assertIn("appoint_manager first", s)          # PLAYBOOK
        self.assertIn("THE STATUS DIGEST", s)              # OBSERVATION/digest paragraph
        self.assertEqual(prompt.API_SECTIONS, ("4", "6"))
        self.assertIn("site facts here", s)
        self.assertIn("observation facts here", s)
        self.assertNotIn("limit facts here", s)            # section 10 stays out
        self.assertEqual(prompt.api_sections("## 4. Sites\nkeep\n", ("4",)), "## 4. Sites\nkeep")

    def test_render_without_manual_carries_no_reference_block(self):
        s = prompt.system_prompt("", {"add_order", "add_manager_order"})
        self.assertNotIn("GAME API REFERENCE", s)
        self.assertIn(CLARIFICATION, s)                    # manager tool present


if __name__ == "__main__":
    unittest.main()
