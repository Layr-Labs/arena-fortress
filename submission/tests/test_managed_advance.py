"""Controller scheduling must preserve the requested horizon and server stops."""
import unittest
from plain.harness import Plain, DAY


class Game:
    def __init__(self, stop=None, fail=False, hands_off=False):
        self.day = 0
        self.calls = []
        self.stop, self.fail, self.hands_off = stop, fail, hands_off

    def act(self, tool, args):
        self.calls.append((tool, args.copy()))
        elapsed = 0 if self.fail else args['days']
        self.day += elapsed
        response = {'ok': not self.fail, 'day': self.day,
                    'result': {'advanced_ticks': elapsed * DAY, 'advanced_days': elapsed,
                               'stopped': self.stop}}
        if self.hands_off:
            response['hands_off_in_days'] = 0
        return response

    def observe(self):
        return {'day': self.day}


class Guard:
    def __init__(self):
        self.days = []

    def step(self, obs):
        self.days.append(obs['day'])


class ManagedAdvance(unittest.TestCase):
    def agent(self, **kwargs):
        agent = Plain.__new__(Plain)
        agent.game = Game(**kwargs)
        agent.guard = Guard()
        agent.guard_day = 0
        return agent

    def test_preserves_horizon_and_stop_on_while_visiting_between_steps(self):
        agent = self.agent()
        result = agent.managed_advance({'days': 7, 'stop_on': ['announcement:MIGRANT_ARRIVAL']})
        self.assertEqual([a['days'] for _, a in agent.game.calls], [2, 2, 2, 1])
        self.assertTrue(all(a['stop_on'] == ['announcement:MIGRANT_ARRIVAL'] for _, a in agent.game.calls))
        self.assertEqual(agent.guard.days, [2, 4, 6])
        self.assertEqual(result['result']['advanced_days'], 7)

    def test_returns_to_model_immediately_on_tripwire(self):
        agent = self.agent(stop='hostile_near_citizens')
        result = agent.managed_advance({'days': 14})
        self.assertEqual(len(agent.game.calls), 1)
        self.assertEqual(agent.guard.days, [])
        self.assertEqual(result['result']['stopped'], 'hostile_near_citizens')
        self.assertEqual(result['result']['advanced_days'], 2)

    def test_no_controller_actions_after_hands_off(self):
        agent = self.agent(hands_off=True)
        agent.managed_advance({'days': 14})
        self.assertEqual(len(agent.game.calls), 1)
        self.assertEqual(agent.guard.days, [])

    def test_rejected_advance_does_not_loop_or_manage(self):
        agent = self.agent(fail=True)
        result = agent.managed_advance({'days': 14})
        self.assertFalse(result['ok'])
        self.assertEqual(len(agent.game.calls), 1)
        self.assertEqual(agent.guard.days, [])


class AdvanceScope(unittest.TestCase):
    def test_established_open_play_keeps_original_advance_path(self):
        import contextlib
        import io
        import json
        from types import SimpleNamespace
        from unittest.mock import patch
        from test_pacing import FakeGame, FakeModel
        for horizon, window, expected in [(216, None, False), (336, None, True), (60, 20, True)]:
            with self.subTest(horizon=horizon, window=window):
                agent = Plain(SimpleNamespace(task={'days': horizon}, days=horizon, credits=None),
                              FakeGame(), FakeModel())
                agent.guard.hands_off = window
                agent.tool_names = {'advance_days'}
                agent.messages = []
                call = {'id': 'a', 'function': {'name': 'advance_days',
                                              'arguments': json.dumps({'days': 7})}}
                with patch.object(agent, 'managed_advance', return_value={'ok': True}) as managed:
                    with contextlib.redirect_stdout(io.StringIO()):
                        agent.run_call(call)
                self.assertEqual(managed.called, expected)
                if not expected:
                    self.assertEqual(agent.game.actions, [('advance_days', {'days': 7})])
