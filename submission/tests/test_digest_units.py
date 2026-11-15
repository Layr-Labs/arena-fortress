import unittest
from plain import digest

ALL = ['MINE', 'CUTWOOD', 'CARPENTER', 'BREWER', 'COOK', 'PLANT']

class CitizenUnitsShape(unittest.TestCase):
    def context(self, units, memory=None):
        return {'units': units, 'mem': memory or digest.Memory(), 'next': []}
    def test_native_units_envelope_is_read(self):
        c = self.context({'ok': True, 'kind': 'citizens', 'total': 1,
                          'units': [{'id': 1, 'labors': ALL}]})
        self.assertIn('every core labor', digest._labors(c))
        self.assertEqual(c['next'], [])
    def test_native_units_missing_cook_is_reported(self):
        c = self.context({'units': [{'id': 1, 'labors': [x for x in ALL if x != 'COOK']}]})
        self.assertIn('COOK (nobody cooks)', digest._labors(c))
        self.assertIn('enable_automation autolabor', c['next'][0])
    def test_legacy_shapes_keep_behavior(self):
        people = [{'id': 1, 'labors': ALL}]
        for units in [{'citizens': people}, {'result': people}, people]:
            with self.subTest(units=units):
                self.assertIn('every core labor', digest._labors(self.context(units)))
    def test_malformed_or_missing_labors_do_not_invent_gaps(self):
        for units in [{}, {'units': None}, {'units': [None, 3, {}]}, {'units': [{'labors': 'COOK'}]}]:
            with self.subTest(units=units):
                c = self.context(units)
                self.assertIsNone(digest._labors(c))
                self.assertEqual(c['next'], [])
    def test_none_reuses_last_native_labor_line(self):
        mem = digest.Memory()
        first = digest._labors(self.context({'units': [{'labors': ALL}]}, mem))
        self.assertEqual(digest._labors(self.context(None, mem)), first)
    def test_complete_native_empty_labors_reports_missing(self):
        c = self.context({'units': [{'id': 1, 'labors': []}]})
        self.assertIn('MISSING', digest._labors(c))
    def test_no_native_mutation(self):
        import copy
        units = {'units': [{'id': 1, 'labors': ALL.copy()}]}
        before = copy.deepcopy(units)
        digest._labors(self.context(units))
        self.assertEqual(units, before)
    def test_status_integration_has_labor_line_without_error(self):
        obs = {'administrators': {'citizens': 1}, 'stocks': {}}
        text = digest.digest(obs, {'day': 10, 'tick': 12000}, units={'units': [{'labors': ALL}]})
        self.assertIn('labors: every core labor', text)
        self.assertNotIn('labors: (digest error', text)
