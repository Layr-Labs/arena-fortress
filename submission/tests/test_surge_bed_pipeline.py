import unittest
from support import Overseer, StubGame, resp

GOAL = 'A migrant wave is coming; every dwarf must have a placed bed.'

class SurgeBedPipeline(unittest.TestCase):
    def case(self, cit=53, beds=19, left=30, hands_off=23, orders=None, refuse=False):
        game = StubGame(refuse=[('add_order', None)] if refuse else [])
        ov = Overseer(game, goal=GOAL, days=60)
        ov.set_task({'goal': GOAL, 'hands_off': {'day': 39}})
        rr = resp(44, 16, 100, cit=cit, hands_off=hands_off,
                  orders=orders if orders is not None else [{'id': 4, 'recipe': 'make_bed',
                      'job': 'ConstructBed', 'left': left, 'validated': False}])
        rr['observation']['stocks']['beds'] = beds
        ov.load(rr); ov.count = 0
        return ov, game
    def test_actual_late_order_context_adds_existing_target_shortfall_early(self):
        ov,g = self.case(); ov.surge_bed_pipeline_topup()
        self.assertEqual(g.tools('add_order'), [{'recipe': 'make_bed', 'amount': 16}])
    def test_ack_is_once_per_task(self):
        ov,g = self.case(); ov.surge_bed_pipeline_topup()
        ov.now += 3 * 1200; ov.day += 3; ov.count = 0
        ov.surge_bed_pipeline_topup(); self.assertEqual(len(g.tools('add_order')), 1)
    def test_no_extra_order_if_pending_covers_actual_citizens(self):
        ov,g = self.case(cit=49); ov.surge_bed_pipeline_topup(); self.assertEqual(g.calls, [])
    def test_every_finite_bed_order_is_counted(self):
        ov,g = self.case(orders=[{'id': 4, 'recipe': 'make_bed', 'left': 30},
                                {'id': 5, 'job': 'ConstructBed', 'left': 8}])
        ov.surge_bed_pipeline_topup(); self.assertEqual(g.calls, [])
    def test_repeating_unknown_negative_or_boolean_left_is_not_estimated(self):
        for extra in [{'repeat': 'daily', 'left': 30}, {'left': None}, {'left': -1}, {'left': True}]:
            with self.subTest(extra=extra):
                ov,g = self.case(orders=[dict(id=4, recipe='make_bed', **extra)])
                ov.surge_bed_pipeline_topup(); self.assertEqual(g.calls, [])
    def test_no_late_or_invalid_clock_topup(self):
        for ho in [14, 3, 0, None, True, 23.0]:
            with self.subTest(ho=ho):
                ov,g = self.case(hands_off=ho); ov.surge_bed_pipeline_topup(); self.assertEqual(g.calls, [])
    def test_scope_requires_actual_migrant_bed_lab_goal(self):
        for name in ['surge', 'beds_first', 'lab']:
            with self.subTest(name=name):
                ov,g = self.case(); setattr(ov, name, False)
                ov.surge_bed_pipeline_topup(); self.assertEqual(g.calls, [])
    def test_refusal_does_not_mark_done(self):
        ov,g = self.case(refuse=True); ov.surge_bed_pipeline_topup()
        self.assertNotIn('o_surge_bed_pipeline', ov.done)
    def test_supply_calls_topup_without_duplicating_existing_order(self):
        ov,g = self.case(); ov.supply()
        self.assertEqual([a for a in g.tools('add_order') if a.get('recipe') == 'make_bed'],
                         [{'recipe': 'make_bed', 'amount': 16}])
    def test_regular_same_pass_bed_order_blocks_topup(self):
        ov,g = self.case(orders=[{'id': 4, 'job': 'ConstructBed', 'left': 30}])
        ov.supply()
        self.assertEqual(len([a for a in g.tools('add_order') if a.get('recipe') == 'make_bed']), 1)
        self.assertNotIn('o_surge_bed_pipeline', ov.done)
    def test_malformed_bed_stock_is_not_estimated(self):
        for beds in [None, True, -1, 19.0, '19']:
            with self.subTest(beds=beds):
                ov,g = self.case(beds=beds); ov.surge_bed_pipeline_topup(); self.assertEqual(g.calls, [])
