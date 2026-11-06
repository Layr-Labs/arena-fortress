"""Deterministic fort management with occasional model diagnosis, using only the two service APIs."""
import json
import math
import sys
from dfbench_client import (ActionLimit, BudgetExhausted, GameAPIError, GameClient, GameOver,
                            HandsOff, ModelClient, ModelError, load_task)
from .controller import Controller, obj, rows
from .prompt import SYSTEM


def log(kind, **fields):
    print(json.dumps({'kind': kind, **fields}, ensure_ascii=False, default=str), flush=True)


QUERY_NAMES = ['stocks', 'units', 'jobs', 'orders', 'buildings', 'zones', 'map', 'manager_order_types', 'workshop_types']
QUERY_TOOL = {'type': 'function', 'function': {'name': 'read_query',
    'description': 'Read more facts from the game. Does not move time. Use query-specific optional arguments.',
    'parameters': {'type': 'object', 'required': ['query'], 'properties': {
        'query': {'type': 'string', 'enum': QUERY_NAMES}, 'kind': {'type': 'string'},
        'item_type': {'type': 'string'}, 'type': {'type': 'string'},
        **{k: {'type': 'integer'} for k in ['limit', 'id', 'x', 'y', 'z', 'z2', 'radius']}}}}}


def schema_accepts(value, schema):
    """Validate the served schema subset before model values reach controller state."""
    kind = schema.get('type')
    types = {'string': str, 'integer': int, 'number': (int, float),
             'boolean': bool, 'object': dict, 'array': list}
    if kind not in types or not isinstance(value, types[kind]):
        return False
    if kind in ('integer', 'number'):
        if isinstance(value, bool) or (isinstance(value, float) and not math.isfinite(value)):
            return False
        if value < schema.get('minimum', value) or value > schema.get('maximum', value):
            return False
    if 'enum' in schema and value not in schema['enum']:
        return False
    if kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', len(value)):
            return False
        return all(schema_accepts(item, schema.get('items', {})) for item in value)
    if kind == 'object':
        properties = schema.get('properties', {})
        if set(value) - set(properties) or any(key not in value for key in schema.get('required', [])):
            return False
        return all(schema_accepts(item, properties[key]) for key, item in value.items())
    return True


class Steward:
    def __init__(self, task, game, model):
        self.task, self.game, self.model = task, game, model
        self.stats = {'actions': 0, 'rejected': 0, 'advances': 0, 'consultations': 0, 'model_errors': 0}
        self.last_consult = -100
        self.model_disabled = False
        self.stop_reason = None

    def setup(self):
        contract = self.game.task()
        self.tools = contract.get('tools', [])
        self.tool_names = {t['function']['name'] for t in self.tools}
        self.schemas = {t['function']['name']: t['function']['parameters'] for t in self.tools}
        self.info = {**self.task.task, **obj(contract.get('task'))}
        self.control = Controller(self.info)
        log('setup', task=self.info.get('name'), days=self.info.get('days'), credits=self.task.credits)

    def observe(self):
        response = self.game.observe()
        self.control.update(response)
        return response

    def action(self, name, args, source):
        if name not in self.tool_names:
            return {'ok': False, 'error_code': 'unknown_tool'}
        try:
            response = self.game.act(name, args)
        except ActionLimit:
            return self.action('advance_days', {'days': 1}, 'action_limit')
        self.control.remember(name, args, response)
        self.stats['actions'] += name != 'advance_days'
        self.stats['advances'] += name == 'advance_days'
        self.stats['rejected'] += not bool(response.get('ok'))
        log('action', day=self.control.day, source=source, tool=name, args=args,
            ok=response.get('ok'), result=response.get('result'), error=response.get('error'))
        return response

    def model_allowed(self, name, args):
        c = self.control
        if not isinstance(name, str) or name not in self.tool_names:
            return False
        if not schema_accepts(args, self.schemas[name]) or not c.available(name, args):
            return False
        if name == 'dig_room' and (args.get('w', 3) != 3 or args.get('h', 3) != 3):
            return False
        if name == 'add_order' and c.bed_focus and args.get('recipe') in ('make_table', 'make_chair'):
            if obj(c.adm.get('manager_office')).get('chair'):
                return False
        if name == 'add_order' and c.pending(recipe=args.get('recipe')):
            return False
        if name == 'add_manager_order':
            if any(o.get('job') == args.get('job') and o.get('reaction') == args.get('reaction')
                   and (o.get('left', 0) > 0 or o.get('repeat')) for o in c.orders):
                return False
        if name == 'build_workshop':
            kind = args.get('type')
            if sum(w.get('type') == kind for w in c.workshops) >= c.workshop_target(kind):
                return False
        if name == 'enable_automation' and c.plugins.get(args.get('name')) == 'on':
            return False
        if name == 'appoint_manager' and c.adm.get('manager_active_for_orders'):
            return False
        if name == 'cancel_order':
            # The controller owns essential supply orders; do not churn them during diagnosis.
            order = next((o for o in c.orders if o.get('id') == args.get('order_id')), {})
            if order.get('recipe') in ('brew_drink', 'make_barrel'):
                return False
        return True

    def consult(self):
        c = self.control
        self.last_consult = c.day
        self.stats['consultations'] += 1
        # Bounded facts: the model can query a fuller section when it needs it.
        observation = dict(c.obs)
        observation['dwarves'] = [{k: d[k] for k in ('id', 'profession', 'job', 'stress', 'positions') if k in d}
                                  for d in c.dwarves]
        observation.update(days_left_in_run=c.response.get('days_left'),
                           hands_off_in_days=c.response.get('hands_off_in_days'), goal=self.info.get('goal'))
        messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content':
                    'OBSERVATION ' + json.dumps(observation, separators=(',', ':'))},
                    {'role': 'user', 'content': 'CONTROLLER ' + json.dumps(c.status(), separators=(',', ':'))}]
        for _ in range(3):
            credits = self.task.credits
            if credits is not None and (self.model.usage.get('cost_usd') or 0) >= credits * 0.65:
                self.model_disabled = True
                return
            try:
                response = self.model.chat(messages, tools=self.tools + [QUERY_TOOL], tool_choice='required',
                                           temperature=0, max_tokens=1800, reasoning={'effort': 'low'})
            except BudgetExhausted:
                self.model_disabled = True
                return
            except ModelError as error:
                self.stats['model_errors'] += 1
                log('model_error', error=str(error)[:400])
                if self.stats['model_errors'] >= 3:
                    self.model_disabled = True
                return
            msg = obj(response['choices'][0].get('message'))
            calls = rows(msg.get('tool_calls'))
            if not calls:
                return
            call = calls[0]
            fn = obj(call.get('function'))
            try:
                args = json.loads(fn.get('arguments') or '{}')
            except (ValueError, TypeError, RecursionError):
                return
            if not isinstance(args, dict):
                return
            name = fn.get('name')
            if not isinstance(name, str) or not isinstance(call.get('id'), str):
                return
            if name == 'advance_days':
                return
            if name == 'read_query':
                if not schema_accepts(args, QUERY_TOOL['function']['parameters']):
                    result = {'ok': False, 'error': 'Invalid read_query arguments.'}
                else:
                    args = dict(args)
                    query = args.pop('query')
                    try:
                        result = self.game.query(query, **args)
                    except GameAPIError as error:
                        result = {'error': str(error)[:300]}
            elif self.model_allowed(name, args):
                result = self.action(name, args, 'model')
                self.observe()
            else:
                result = {'ok': False, 'error': 'Already satisfied, duplicate, invalid arguments, or recent failed action. Choose another action or advance_days.'}
            messages.append({'role': 'assistant', 'content': msg.get('content'), 'tool_calls': [call]})
            messages.append({'role': 'tool', 'tool_call_id': call.get('id'),
                             'content': json.dumps(result, separators=(',', ':'))[:16000]})

    def run(self, max_steps=5000):
        self.setup()
        day_actions = 0
        action_day = None
        try:
            for _ in range(max_steps):
                response = self.observe()
                c = self.control
                if response.get('game_over') or response.get('days_left', 1) <= 0:
                    self.stop_reason = 'game_over'
                    break
                if response.get('hands_off_in_days', 1) <= 0:
                    self.stop_reason = 'hands_off'
                    break
                day_index = int(c.day)
                if day_index != action_day:
                    action_day, day_actions = day_index, 0
                    log('state', day=c.day, citizens=c.n, stocks=c.stock, placed=dict(c.placed),
                        farms=len(c.farms), manager_office=c.adm.get('manager_office'))
                limit = min(30, self.task.limits.get('actions_per_game_day', 40) - 1)
                next_action = c.next() if day_actions < limit else None
                if next_action:
                    name, args = next_action
                    result = self.action(name, args, 'controller')
                    day_actions += 1
                else:
                    interval = 4 if rows(c.obs.get('moods')) else 14
                    if not self.model_disabled and c.day - self.last_consult >= interval and day_actions < limit - 3:
                        self.consult()
                        day_actions += 3
                        continue
                    days = 1 if day_actions >= limit else c.advance_days()
                    days = min(days, self.task.limits.get('max_advance_days', 28))
                    result = self.action('advance_days', {'days': max(1, int(days))}, 'controller')
                if result.get('game_over'):
                    self.stop_reason = 'game_over'
                    break
            else:
                self.stop_reason = 'step_limit'
        except (GameOver, HandsOff) as error:
            self.stop_reason = type(error).__name__
        log('done', reason=self.stop_reason, stats=self.stats, usage=self.model.usage)
        return self.stats


def main():
    task = load_task()
    game = GameClient(task.game_url)
    model = ModelClient(task.model_base_url, task.model_name, task.api_key, prices=task.prices,
                        timeout=180, max_retries=1)
    try:
        Steward(task, game, model).run()
    except GameAPIError as error:
        log('game_error', error=str(error)[:500])
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
