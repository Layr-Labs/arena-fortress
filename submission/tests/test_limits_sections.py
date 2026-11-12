"""Black-box: the rendered system prompt carries served manual sections 4, 6 and 10.

Section 10 ("Known limits of v0": no trade/labor/crop-choice/removal tools, manager_order_types
caveat) was omitted while the model looped on infeasible actions. Rules: include 4/6/10 verbatim
and exactly once, exclude every other section, never fabricate text when 10 or the whole manual
is absent, keep the tool_names-dependent ORDERS clause.
"""
from pathlib import Path
import sys
import unittest

VARIANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VARIANT))
from plain import prompt

assert Path(prompt.__file__).is_relative_to(VARIANT), prompt.__file__

S = {n: "## %s. Title %s\nbody%s\n" % (n, n, n) for n in
     ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]}
S["4"] = "## 4. Sites\nsite facts\n"
S["6"] = "## 6. The observation (obs schema 8)\nobs facts\n"
S["10"] = ("## 10. Known limits of v0\n- No trade, no labor tool, no crop choice tool.\n"
           "- `manager_order_types` lists DF's job classes, not the work-order screen's own list.\n")
MANUAL = "preamble\n" + "".join(S[n] for n in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"])


class LimitsSections(unittest.TestCase):
    def test_includes_4_6_10_exactly_once(self):
        out = prompt.system_prompt(MANUAL)
        for n in ("4", "6", "10"):
            self.assertEqual(out.count(S[n].splitlines()[0]), 1, "section %s header count" % n)
            self.assertIn(S[n].strip(), out, "section %s verbatim" % n)

    def test_excludes_unrelated_sections(self):
        out = prompt.system_prompt(MANUAL)
        for n in ("1", "2", "3", "5", "7", "8", "9"):
            self.assertNotIn("## %s. " % n, out, "section %s leaked" % n)
            self.assertNotIn("body%s" % n, out, "section %s body leaked" % n)

    def test_no_marker_for_absent_section10(self):
        m = MANUAL.replace(S["10"], "")
        out = prompt.system_prompt(m)
        self.assertIn("## 4. Sites", out)
        self.assertIn("## 6. The observation", out)
        self.assertNotIn("Known limits", out)
        self.assertNotIn("## 10.", out)

    def test_none_and_empty_manuals_fabricate_nothing(self):
        for m in (None, ""):
            out = prompt.system_prompt(m)
            self.assertNotIn("Known limits", out)
            self.assertNotIn("GAME API REFERENCE", out)
            self.assertIn("You are the overseer", out)

    def test_orders_clause_follows_tool_names(self):
        with_mo = prompt.system_prompt(MANUAL, ["add_manager_order", "advance_days"])
        without = prompt.system_prompt(MANUAL, ["advance_days"])
        self.assertIn("add_manager_order", with_mo.split("GAME API REFERENCE")[0])
        self.assertNotIn("ORDERS BEYOND THE RECIPES", without)
        self.assertIn("## 10. ", with_mo)
        self.assertIn("## 10. ", without)


if __name__ == "__main__":
    unittest.main()
