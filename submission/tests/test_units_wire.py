"""The served units object must reach the existing labor digest.

The analogous public wire decoder correction in c808a2e1-5ea8-4fd0-a323-0350e050daee
motivated this fix. This implementation adds only the actual units-list field.
"""
import unittest
from plain import digest


class UnitsWire(unittest.TestCase):
    def line(self, payload):
        context = {"units": payload, "mem": digest.Memory(), "next": []}
        return digest._labors(context)

    def test_served_units_object_produces_coverage_line(self):
        citizen = {"id": 1, "labors": ["MINE", "CUTWOOD", "CARPENTER", "BREWER", "COOK", "PLANT"]}
        payload = {"kind": "citizens", "ok": True, "total": 1, "units": [citizen]}
        self.assertIn("every core labor", self.line(payload))

    def test_served_missing_labor_is_reported_without_mutating_facts(self):
        citizen = {"id": 1, "labors": ["MINE"]}
        payload = {"kind": "citizens", "ok": True, "total": 1, "units": [citizen]}
        self.assertIn("BREWER (nobody brews)", self.line(payload))
        self.assertEqual(citizen["labors"], ["MINE"])

    def test_legacy_list_and_citizens_envelopes_still_work(self):
        people = [{"id": 1, "labors": ["MINE"]}]
        for payload in (people, {"citizens": people}, {"result": people}):
            with self.subTest(payload=payload):
                self.assertIn("BREWER (nobody brews)", self.line(payload))


if __name__ == "__main__":
    unittest.main()
