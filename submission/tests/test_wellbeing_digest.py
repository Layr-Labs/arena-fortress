import unittest
from plain import digest

class WellbeingFactsTests(unittest.TestCase):
    def context(self, units, dwarves=None):
        return {'obs': {'dwarves': dwarves if dwarves is not None else [{'id': 7, 'stress': 1}]},
                'units': units, 'next': []}

    def test_current_stress_and_fresh_negative_needs_are_exposed(self):
        c = self.context({'units': [{'id': 7, 'stress': 5, 'needs': [
            {'need': 'DrinkAlcohol', 'focus_level': 100},
            {'need': 'AdmireArt', 'focus_level': -400},
            {'need': 'CraftObject', 'focus_level': -900}]}]})
        line = digest._wellbeing(c)
        self.assertIn('citizen 7 category 1', line)
        self.assertLess(line.index('CraftObject=-900'), line.index('AdmireArt=-400'))
        self.assertNotIn('DrinkAlcohol', line)
        self.assertIn('not a diagnosis', line)
        self.assertIn('does not establish the cause', c['next'][0])

    def test_happy_or_absent_citizens_are_not_described_from_cached_query(self):
        units = {'units': [{'id': 7, 'needs': [{'need': 'CraftObject', 'focus_level': -900}]}]}
        self.assertIsNone(digest._wellbeing(self.context(units, [{'id': 7, 'stress': 6}])))
        self.assertIsNone(digest._wellbeing(self.context(units, [{'id': 8, 'stress': 1}])))

    def test_absent_query_does_not_reuse_or_invent_needs(self):
        c = self.context(None)
        self.assertIsNone(digest._wellbeing(c))
        self.assertEqual(c['next'], [])

    def test_malformed_and_nonfinite_focus_values_are_ignored(self):
        bad = [None, {'need': 'nan', 'focus_level': float('nan')},
               {'need': 'infinity', 'focus_level': float('-inf')},
               {'need': 'bool', 'focus_level': False}, {'need': 'string', 'focus_level': '-9'},
               {'need': None, 'focus_level': -100}]
        self.assertIsNone(digest._wellbeing(self.context({'units': [{'id': 7, 'needs': bad}]})))

    def test_summary_bounds_citizens_needs_and_name_lengths(self):
        units = [{'id': i, 'needs': [{'need': str(n) * 100, 'focus_level': -100 + n}
                                    for n in range(10)]} for i in range(10)]
        c = self.context({'result': {'units': units}}, [{'id': i, 'stress': 1} for i in range(10)])
        line = digest._wellbeing(c)
        self.assertEqual(line.count('citizen '), 3)
        self.assertEqual(line.count('='), 9)
        self.assertLess(len(line), 750)

    def test_digest_integrates_facts_without_mutating_wire_payload(self):
        units = {'units': [{'id': 7, 'labors': ['MINE'], 'needs': [{'need': 'CraftObject', 'focus_level': -900}]}]}
        import copy
        original = copy.deepcopy(units)
        text = digest.digest({'dwarves': [{'id': 7, 'stress': 1}]}, {'day': 2}, units=units)
        self.assertIn('wellbeing query facts', text)
        self.assertIn('labors MISSING', text)
        self.assertNotIn('digest error', text)
        self.assertEqual(units, original)
