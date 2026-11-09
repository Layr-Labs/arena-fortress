import unittest
from plain import digest

class UnitsShapeTests(unittest.TestCase):
    def context(self, units, memory=None):
        return {"units": units, "mem": memory or digest.Memory(), "next": []}

    def test_live_units_shape_reports_missing_labor(self):
        c = self.context({"units": [{"id": 3, "labors": ["MINE"]}]})
        line = digest._labors(c)
        self.assertIn("labors MISSING", line)
        self.assertIn("BREWER", line)
        self.assertNotIn("MINE (nobody digs)", line)

    def test_wire_and_legacy_envelopes_match(self):
        units = [{"id": 3, "labors": [name for name, _ in digest.LABORS]}]
        variants = [units, {"units": units}, {"citizens": units}, {"result": units},
                    {"result": {"units": units}}]
        for payload in variants:
            with self.subTest(payload=payload):
                self.assertIn("every core labor", digest._labors(self.context(payload)))

    def test_cached_line_survives_absent_query_and_bad_query_does_not_invent_labors(self):
        memory = digest.Memory()
        c = self.context({"units": [{"labors": ["MINE"]}]}, memory)
        line = digest._labors(c)
        self.assertEqual(digest._labors(self.context(None, memory)), line)
        self.assertIsNone(digest._labors(self.context({"units": [{"id": 2}]}, memory)))
        self.assertEqual(memory.labors_missing, line)
