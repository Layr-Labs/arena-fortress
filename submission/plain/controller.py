"""Fort management through the public game API. All decisions use observed facts."""
from collections import Counter
import json
import math


def obj(value):
    return value if isinstance(value, dict) else {}


def rows(value):
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def signature(name, args):
    return name + ':' + json.dumps(args, sort_keys=True, separators=(',', ':'))


def contains(box, point):
    return (box.get('z') == point.get('z') and
            box.get('x', 0) <= point.get('x', -1) < box.get('x', 0) + box.get('w', 1) and
            box.get('y', 0) <= point.get('y', -1) < box.get('y', 0) + box.get('h', 1))


MOOD_WORKSHOPS = {
    'WOODCRAFT': 'Craftsdwarfs', 'STONECRAFT': 'Craftsdwarfs', 'BONECARVE': 'Craftsdwarfs',
    'CARPENTRY': 'Carpenters', 'MASONRY': 'Masons', 'STONECUTTING': 'Masons',
    'STONECARVING': 'Masons', 'MECHANICS': 'Mechanics', 'CLOTHESMAKING': 'Clothiers',
    'WEAVING': 'Loom', 'LEATHERWORK': 'Leatherworks', 'TANNER': 'Tanners',
    'BOWYER': 'Bowyers', 'GEM_CUT': 'Jewelers', 'GEM_SETTING': 'Jewelers',
    'GLASSMAKER': 'GlassFurnace', 'METALCRAFT': 'MetalsmithsForge',
    'FORGE_WEAPON': 'MetalsmithsForge', 'FORGE_ARMOR': 'MetalsmithsForge',
    'FORGE_FURNITURE': 'MetalsmithsForge',
}


class Controller:
    def __init__(self, info):
        self.info = info
        self.bed_focus = bool(info.get('hands_off')) and 'bed' in str(info.get('goal', '')).lower()
        self.failures = {}
        self.successes = {}
        self.recent = []
        self.samples = []
        self.state_token = None
        self.dig_pending = None
        self.dig_changed_day = 0
        self.order_added = {}
        self.order_seen = {}
        self.stairs_started = {}
        self.rooms_started = {}
        self.zone_attempts = set()
        self.full_rooms = {}
        self.day = 0

    def update(self, response):
        self.response = response
        self.day = float(response.get('day', 0))
        self.obs = obj(response.get('observation')) or {k: v for k, v in response.items() if k not in ('day', 'tick', 'days_left', 'game_over', 'hands_off_in_days')}
        self.stock = obj(self.obs.get('stocks'))
        self.dwarves = rows(self.obs.get('dwarves'))
        self.n = len(self.dwarves)
        self.adm = obj(self.obs.get('administrators'))
        self.sites = rows(obj(self.obs.get('map')).get('sites'))
        self.workshops = rows(self.obs.get('workshops'))
        self.farms = rows(self.obs.get('farm_plots'))
        self.furniture = rows(self.obs.get('furniture'))
        self.zones = rows(self.obs.get('zones'))
        self.orders = rows(self.obs.get('orders'))
        recipes = {'MakeBarrel': 'make_barrel', 'ConstructBed': 'make_bed', 'ConstructThrone': 'make_chair',
                   'ConstructTable': 'make_table', 'PrepareMeal': 'cook_meal'}
        for order in self.orders:
            self.order_seen.setdefault(order.get('id'), self.day)
            if not order.get('recipe'):
                order['recipe'] = ('brew_drink' if order.get('reaction') == 'BREW_DRINK_FROM_PLANT' else recipes.get(order.get('job')))
        self.plugins = obj(self.obs.get('plugins'))
        self.placed = Counter(x.get('kind') for x in self.furniture)
        self.free = obj(self.stock.get('furniture_free'))
        pending = self.obs.get('dig_designations_pending', 0)
        if pending != self.dig_pending:
            self.dig_pending, self.dig_changed_day = pending, self.day
        self.areas = [s for s in self.sites if s.get('kind') == 'A' and s.get('w', 1) <= 40 and s.get('h', 1) <= 40]
        self.areas.sort(key=lambda s: -s.get('open_tiles', 0))
        if not self.samples or self.samples[-1]['day'] != self.day:
            self.samples.append({'day': self.day, 'citizens': self.n, **{
                k: self.stock.get(k, 0) for k in ('drink', 'food_edible', 'plants_brewable', 'seeds', 'logs_usable')}})
            self.samples = self.samples[-40:]
        self.state_token = hash(json.dumps({k: v for k, v in self.obs.items() if k != 'actions_left_today'},
                                          sort_keys=True, separators=(',', ':')))

    def available(self, tool, args):
        if tool == 'place_furniture':
            key = (args.get('kind'), args.get('site'))
            if key in self.full_rooms and self.full_rooms[key] == self.room_state(args.get('site')):
                return False
        if tool != 'advance_days' and self.successes.get(signature(tool, args)) == (self.day, self.state_token):
            return False
        fail = self.failures.get(signature(tool, args))
        if fail and not (tool == 'place_furniture' and fail[2] == 'no_space'):
            day, count, code = fail
            delay = 10 if code in ('bad_arguments', 'wrong_site_kind', 'unknown_tool') else min(14, 2 ** count)
            if self.day - day < delay:
                return False
        if tool == 'cancel_order' and self.day - self.order_added.get(args.get('order_id'), -100) < 7:
            return False
        return True

    def remember(self, name, args, response):
        sig = signature(name, args)
        result = obj(response.get('result'))
        self.recent.append({'day': self.day, 'tool': name, 'args': args, 'ok': bool(response.get('ok')),
                            'result': result if response.get('ok') else {k: response.get(k) for k in ('error_code', 'error')}})
        self.recent = self.recent[-16:]
        if response.get('ok'):
            self.failures.pop(sig, None)
            self.successes[sig] = (self.day, self.state_token)
            if name in ('add_order', 'add_manager_order'):
                self.order_added[result.get('order_id')] = self.day
            if name == 'dig_stairs':
                self.stairs_started[args['site']] = self.day
            if name == 'dig_room':
                self.rooms_started[args['site']] = self.day
            if name == 'make_zone':
                self.zone_attempts.add((args['kind'], args['site']))
        else:
            old = self.failures.get(sig, (0, 0, ''))
            self.failures[sig] = (self.day, old[1] + 1, response.get('error_code'))
            if name == 'place_furniture' and response.get('error_code') == 'no_space':
                self.full_rooms[(args.get('kind'), args.get('site'))] = self.room_state(args.get('site'))

    def room_state(self, site_id):
        area = next((s for s in self.sites if s.get('id') == site_id), {})
        geometry = tuple(area.get(k) for k in ('x', 'y', 'z', 'w', 'h', 'open_tiles'))
        occupied = tuple(sorted(f['id'] for f in self.furniture + self.farms
                                if 'id' in f and contains(area, f)))
        water = obj(self.obs.get('water_on_fort_levels')).get('total_depth')
        return geometry, occupied, water

    def call(self, tool, **args):
        return (tool, args) if self.available(tool, args) else None

    def sites_of(self, kind):
        return [s for s in self.sites if s.get('kind') == kind and s.get('free', True) and not s.get('used')]

    def has(self, workshop, built=False):
        return any(w.get('type') == workshop and (not built or w.get('built')) for w in self.workshops)

    def pending(self, recipe=None, job=None):
        return [o for o in self.orders if (o.get('recipe') == recipe if recipe else o.get('job') == job)
                and (o.get('left', 0) > 0 or o.get('repeat'))]

    def workshop_target(self, kind):
        if kind == 'Carpenters':
            return min(6, 1 + self.n // 10)
        if kind == 'Still':
            return min(3, 1 + self.n // 25)
        return 1

    def drink_target(self):
        target = max(500, self.n * 18)
        if self.response.get('hands_off_in_days', 100) <= 14:
            target = max(target, self.n * 32)
        return target

    def build(self, kind, target=1):
        count = sum(w.get('type') == kind for w in self.workshops)
        if count >= target or self.stock.get('logs_usable', 0) + self.stock.get('boulders_usable', 0) < 1:
            return None
        for s in self.sites_of('W'):
            action = self.call('build_workshop', type=kind, site=s['id'])
            if action:
                return action

    def recipe(self, recipe, amount, conditions=None):
        pending = self.pending(recipe)
        if conditions is None:
            if pending:
                return None
        else:
            standing = [o for o in pending if o.get('repeat')]
            if standing:
                # Population-based capacity and standing-order resizing follow PR #15; see dependencies.json.
                stock, target = conditions[0]['stock'], conditions[0].get('below')
                item_type = {'drink': 'DRINK', 'barrels_empty': 'BARREL', 'prepared_meals': 'FOOD',
                             'beds': 'BED', 'tables': 'TABLE', 'chairs': 'CHAIR'}.get(stock)
                thresholds = []
                for order in standing:
                    for condition in rows(order.get('when')):
                        matches = condition.get('stock') == stock or (
                            not condition.get('stock') and item_type and condition.get('item_type') == item_type and
                            (stock != 'barrels_empty' or 'empty' in (condition.get('flags') or [])))
                        if matches and (condition.get('test') == 'LessThan' or 'below' in condition):
                            value = condition.get('value', condition.get('below'))
                            if isinstance(value, (int, float)):
                                thresholds.append((value, order['id']))
                if target and thresholds:
                    threshold, order_id = max(thresholds)
                    age = self.day - self.order_added.get(order_id, self.order_seen.get(order_id, self.day))
                    if threshold < target * 0.8 and age >= 7:
                        return self.call('cancel_order', order_id=order_id)
                return None
        args = {'recipe': recipe, 'amount': min(30, max(1, amount))}
        if conditions is not None:
            args.update(repeat='daily', when=conditions)
        return self.call('add_order', **args)

    def zone(self, kind, area):
        if (kind, area['id']) in self.zone_attempts:
            return None
        if area.get('w', 1) > 20 or area.get('h', 1) > 20:
            return None
        return self.call('make_zone', kind=kind, site=area['id'])

    def office(self):
        if not self.adm.get('manager_active_for_orders'):
            return None
        if obj(self.adm.get('manager_office')).get('chair'):
            return None
        manager = self.adm.get('MANAGER_id')
        if manager is None:
            manager = next((d['id'] for d in self.dwarves if d.get('name') == self.adm.get('MANAGER')), None)
        offices = [z for z in self.zones if z.get('type', '').lower() == 'office']
        mine = next((z for z in offices if z.get('owner') == manager and manager is not None), None)
        if mine is None and manager is not None:
            free = next((z for z in offices if z.get('owner') is None), None)
            if free:
                return self.call('assign_zone', zone_id=free['id'], dwarf_id=manager)
        if mine is not None:
            chairs = obj(mine.get('furniture')).get('chair', 0) + obj(mine.get('furniture_planned')).get('chair', 0)
            if chairs:
                return None
            areas = [a for a in self.areas if contains(mine, a) and
                     a['x'] + a.get('w', 1) <= mine['x'] + mine.get('w', 1) and
                     a['y'] + a.get('h', 1) <= mine['y'] + mine.get('h', 1)]
        else:
            areas = [a for a in self.areas if a.get('open_tiles', 0) > 1 and
                     a.get('w', 1) <= 20 and a.get('h', 1) <= 20]
            # The room can grow while miners work. Put a chair in it first so the office
            # covers that exact chair even if the bounding box changes on the next advance.
            for area in areas:
                if any(f.get('kind') == 'chair' and contains(area, f) for f in self.furniture):
                    action = self.zone('office', area)
                    if action:
                        return action
        if self.free.get('chair', 0):
            for area in areas:
                action = self.call('place_furniture', kind='chair', site=area['id'], count=1)
                if action:
                    return action
        elif self.has('Carpenters'):
            return self.recipe('make_chair', 2)

    def housing(self):
        # Place items as soon as they exist. Bed capacity includes construction sites to avoid duplicate orders.
        target = self.n + (4 if self.info.get('days', 0) >= 180 else 2)
        beds_missing = target - self.placed['bed']
        placement = []
        if beds_missing > 0 and self.free.get('bed', 0):
            placement.append(('bed', min(30, beds_missing, self.free['bed'])))
        # Alternate tables and chairs so row-major placement creates usable adjacent seats.
        # One extra chair is reserved for the manager.
        dining = math.ceil(self.n / 2)
        tables, chairs = self.placed['table'], self.placed['chair']
        if tables < dining and tables <= chairs and self.free.get('table', 0):
            placement.append(('table', 1))
        if chairs < dining + 1 and chairs <= tables + 1 and self.free.get('chair', 0):
            placement.append(('chair', 1))
        for kind, count in placement:
            for area in self.areas:
                action = self.call('place_furniture', kind=kind, site=area['id'], count=count)
                if action:
                    return action
        # Re-zone grown rooms only when existing furniture is outside the corresponding zone.
        for kind, furniture_kind, zone_type in [('dormitory', 'bed', 'dormitory'), ('dining_hall', 'table', 'dininghall')]:
            zones = [z for z in self.zones if z.get('type', '').lower().replace('_', '') == zone_type]
            for area in self.areas:
                unzoned = [f for f in self.furniture if f.get('kind') == furniture_kind and contains(area, f)
                           and not any(z['id'] in (f.get('zone_ids') or []) for z in zones)]
                if unzoned:
                    # Each changed bounding box can need a larger zone.
                    if any(not contains(z, f) for f in unzoned for z in zones) or not zones:
                        self.zone_attempts.discard((kind, area['id']))
                    action = self.zone(kind, area)
                    if action:
                        return action

    def farming(self):
        underground = [f for f in self.farms if f.get('subterranean')]
        target = min(10, max(4, math.ceil(self.n / 6)))
        if len(underground) < target:
            for s in self.sites_of('F'):
                if s.get('subterranean', True):
                    action = self.call('build_farm', site=s['id'])
                    if action:
                        return action
            for s in self.sites_of('R'):
                tiles = obj(s.get('tiles'))
                if s.get('dug') and s.get('soil') and tiles.get('soil_floor', 9) == tiles.get('tiles', 9):
                    action = self.call('build_farm', site=s['id'])
                    if action:
                        return action
        return None

    def digging(self):
        area = sum(s.get('open_tiles', 0) for s in self.areas)
        target = max(100, self.n * 3 + min(10, max(4, math.ceil(self.n / 6))) * 9 + 15)
        farms_enough = sum(bool(f.get('subterranean')) for f in self.farms) >= min(10, max(4, math.ceil(self.n / 6)))
        if area >= target and farms_enough:
            return None
        pending = self.obs.get('dig_designations_pending', 0)
        if isinstance(pending, (int, float)) and pending > 15 and self.day - self.dig_changed_day < 12:
            return None
        rooms = [s for s in self.sites_of('R') if not s.get('designated') and not s.get('dug')]
        rooms.sort(key=lambda s: (not s.get('soil'), -s.get('z', 0), s['id']))
        for s in rooms:
            if s['id'] in self.rooms_started:
                continue
            # R describes only a 3x3 candidate. Enlarging it can cut a brook beyond that box.
            action = self.call('dig_room', site=s['id'], w=3, h=3)
            if action:
                return action
        # Another stair is only needed after existing digging has had time to expose room candidates.
        recent = max([*self.stairs_started.values(), *self.rooms_started.values()], default=-100)
        if self.day - recent < 2 or len(self.stairs_started) >= 8:
            return None
        for s in sorted(self.sites_of('S'), key=lambda s: not s.get('soil')):
            if s['id'] not in self.stairs_started:
                return self.call('dig_stairs', site=s['id'], z_bottom=s['z'] - 2)

    def production(self):
        if not isinstance(self.obs.get('stocks'), dict):
            return None
        n, s = max(1, self.n), self.stock
        if self.has('Carpenters'):
            action = self.recipe('make_barrel', 3, [{'stock': 'barrels_empty', 'below': 8},
                                                  {'stock': 'logs', 'at_least': 1}])
            if action:
                return action
        if self.has('Still'):
            action = self.recipe('brew_drink', 5, [{'stock': 'drink', 'below': self.drink_target()},
                                                 {'stock': 'plants_brewable', 'at_least': 6},
                                                 {'stock': 'barrels_empty', 'at_least': 1}])
            if action:
                return action
        if self.has('Carpenters'):
            for kind, stock, target in [('bed', 'beds', n + 6), ('chair', 'chairs', math.ceil(n / 2) + 2),
                                        ('table', 'tables', math.ceil(n / 2))]:
                if self.bed_focus and kind != 'bed':
                    continue
                if self.bed_focus:
                    action = self.recipe('make_bed', 5, [{'stock': 'beds', 'below': max(60, n * 3)},
                                                        {'stock': 'logs', 'at_least': 1}])
                else:
                    have = s.get(stock, self.placed[kind] + self.free.get(kind, 0))
                    action = self.recipe('make_' + kind, min(10, target - have)) if have < target else None
                if action:
                    return action
        if self.has('Kitchen'):
            action = self.recipe('cook_meal', 2, [{'stock': 'prepared_meals', 'below': max(30, n * 3)},
                                                {'stock': 'drink', 'at_least': n * 4},
                                                {'stock': 'plants_total', 'at_least': max(40, n * 2)}])
            if action:
                return action
        # Processing pig tails returns seeds. It also supplies cloth for mood demands.
        kinds = obj(s.get('plants_by_kind'))
        if self.has('Farmers') and any('tail' in k.lower() and obj(v).get('n', 0) for k, v in kinds.items()):
            if not self.pending(job='ProcessPlants'):
                return self.call('add_manager_order', job='ProcessPlants', amount=2, repeat='daily',
                                 when=[{'item_type': 'PLANT', 'flags': ['unrotten'],
                                        'at_least': 20}])

    def mood(self):
        for m in rows(self.obs.get('moods')):
            if not m.get('claimed_workshop'):
                kind = MOOD_WORKSHOPS.get(m.get('skill'))
                if not kind:
                    kind = {'StrangeMoodCrafter': 'Craftsdwarfs', 'StrangeMoodCarpenter': 'Carpenters',
                            'StrangeMoodMason': 'Masons'}.get(m.get('job'))
                if kind:
                    action = self.build(kind)
                    if action:
                        return action

    def defence(self):
        th = obj(self.obs.get('threats'))
        mil = obj(self.obs.get('military'))
        squads = rows(mil.get('squads'))
        if not th.get('visible_hostiles'):
            if obj(self.obs.get('burrows')).get('civilian_alert'):
                return self.call('civilian_alert', on=False)
            if any(d.get('locked') for d in rows(obj(self.obs.get('doors')).get('list'))):
                return self.call('lock_door', locked=False)
            if squads and squads[0].get('orders'):
                return self.call('squad_order', order='stand_down')
            return None
        if squads:
            squad = squads[0]
            if squad.get('uniform') in ('none', None):
                return self.call('equip_squad', uniform='weapon_only')
            hostiles = rows(th.get('hostiles'))
            if squad.get('armed', 0) >= len(hostiles) and squad.get('armed', 0) > 0:
                if not any(o.get('order') == 'attack' and o.get('targets_alive') for o in rows(squad.get('orders'))):
                    return self.call('squad_order', order='attack')
        elif self.n >= 10:
            return self.call('create_squad', size=min(6, self.n // 2))

    def next(self):
        # Dependencies precede throughput: workers, materials, manager, workshops, office, growing space.
        action = self.defence() or self.mood()
        if action:
            return action
        for plugin in ('autolabor', 'autochop', 'seedwatch', 'autofarm'):
            if self.plugins.get(plugin) != 'on':
                action = self.call('enable_automation', name=plugin)
                if action:
                    return action
        if not self.adm.get('manager_active_for_orders'):
            free = [d for d in self.dwarves if not d.get('positions') and d.get('adult', True)]
            free.sort(key=lambda d: (any(k in d.get('profession', '').lower() for k in ('miner', 'wood', 'carpent', 'planter')),
                                     -d.get('organizer_skill', 0)))
            if free:
                action = self.call('appoint_manager', dwarf_id=free[0]['id'])
                if action:
                    return action
        for workshop in ('Carpenters', 'Still'):
            action = self.build(workshop, target=self.workshop_target(workshop))
            if action:
                return action
        action = self.office() or self.farming() or self.production() or self.housing() or self.digging()
        if action:
            return action
        for workshop in ('Kitchen', 'Farmers', 'Fishery'):
            action = self.build(workshop)
            if action:
                return action
        return None

    def advance_days(self):
        if self.response.get('hands_off_in_days', 100) <= 5:
            return 1
        unfinished = (any(not w.get('built') for w in self.workshops) or
                      any(not f.get('built') for f in self.furniture) or self.obs.get('dig_designations_pending'))
        if unfinished or rows(self.obs.get('moods')) or obj(self.obs.get('threats')).get('visible_hostiles'):
            return 2
        if self.stock.get('drink', 0) < self.n * 2 or self.stock.get('food_edible', 0) < self.n:
            return 2
        return 4 if self.day < 60 else 7

    def status(self):
        history = self.samples[-8:]
        flow = {}
        if len(history) >= 2:
            mean_day = sum(x['day'] for x in history) / len(history)
            variance = sum((x['day'] - mean_day) ** 2 for x in history)
            for resource in ('drink', 'food_edible'):
                average = sum(x[resource] for x in history) / len(history)
                slope = sum((x['day'] - mean_day) * (x[resource] - average) for x in history) / max(1, variance)
                flow[resource] = {'change_per_day': round(slope, 2),
                                  'days_left_at_recent_rate': round(self.stock.get(resource, 0) / -slope, 1) if slope < 0 else None}
        return {'citizens': self.n, 'placed': dict(self.placed),
                'farm_tiles': sum(f.get('w', 3) * f.get('h', 3) for f in self.farms),
                'flow': flow, 'history': history, 'recent_actions': self.recent[-8:]}
