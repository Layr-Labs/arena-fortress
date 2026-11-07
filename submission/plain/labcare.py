"""Routine upkeep from visible API facts; every write still uses a public game tool.

The organiser's policies.py and gameapi/manual/MANUAL.md informed the manager,
workshop and farm prerequisites. This implements the season-0 site-id interface.
"""
import json


class Caretaker:
    def __init__(self):
        self.tried = {}
        self.long_farm_goal = 0
        self.combat_signature = ()
        self.combat_until = 0
        self.deaths_seen = 0

    def step(self, obs, tick):
        tick = tick or 0
        # Some animal fights appear in announcements without hostile unit flags.
        labels = set()
        for dwarf in obs.get('dwarves') or []:
            name = str(dwarf.get('name') or '').lower()
            profession = str(dwarf.get('profession') or '').lower()
            if name:
                labels.add(name.split(',')[0].strip())
            if profession:
                labels.add('the ' + profession)
        combat = tuple(str(e) for e in obs.get('recent_events') or [] if any(
            phrase in str(e).lower() for phrase in ('attack', 'bites the', 'shakes the', 'strikes the'))
            and any(label and label in str(e).lower() for label in labels))
        deaths = (obs.get('threats') or {}).get('dead_citizens_total', 0)
        if (combat and combat != self.combat_signature) or deaths > self.deaths_seen:
            self.combat_until = tick + 2 * 1200
        self.combat_signature = combat
        self.deaths_seen = max(self.deaths_seen, deaths)
        if tick < self.combat_until:
            return None
        sites = (obs.get('map') or {}).get('sites') or []
        stocks = obs.get('stocks') or {}
        workshops = obs.get('workshops') or []
        orders = obs.get('orders') or []
        zones = obs.get('zones') or []
        dwarves = obs.get('dwarves') or []
        pop = max(7, len(dwarves))
        free = stocks.get('furniture_free') or {}
        admin = obs.get('administrators') or {}

        def offer(name, args):
            key = name + json.dumps(args, sort_keys=True)
            if tick - self.tried.get(key, -1000000) < 3 * 1200:
                return None
            self.tried[key] = tick
            return name, args

        def site(kind, **checks):
            return next((s for s in sites if s.get('kind') == kind and
                         all(s.get(k) == v for k, v in checks.items())), None)

        def order(recipe, amount, stock, target, extra_conditions=None):
            matching = [o for o in orders if o.get('recipe') == recipe and o.get('repeat')]
            if matching:
                for o in matching:
                    conditions = o.get('when') or []
                    threshold = max((c.get('value', c.get('below', 0)) for c in conditions
                                     if c.get('stock') == stock), default=0)
                    resize_at = target if stock in ('beds', 'tables', 'chairs') and obs.get('hands_off_in_days') is not None else target * 0.8
                    small_bed_batch = recipe == 'make_bed' and type(o.get('total')) in (int, float) and o['total'] < amount
                    if o.get('repeat') and ((threshold and threshold < resize_at) or small_bed_batch) and tick - o.get('created_tick', tick) > 3 * 1200:
                        return offer('cancel_order', {'order_id': o['id']})
                return None
            return offer('add_order', {'recipe': recipe, 'amount': amount,
                         'repeat': 'daily', 'when': [{'stock': stock, 'below': target}] + (extra_conditions or [])})

        # Urgent moods and visible dangers remain model decisions.
        if obs.get('moods'):
            return None
        if (obs.get('threats') or {}).get('visible_hostiles'):
            return None
        if not admin.get('manager_active_for_orders'):
            r = offer('appoint_manager', {})
            if r: return r
        for plugin in ('autolabor', 'autochop', 'seedwatch'):
            if (obs.get('plugins') or {}).get(plugin) != 'on':
                r = offer('enable_automation', {'name': plugin})
                if r: return r
        # Active appointment is not a furnished office. In large forts the manager
        # cannot validate production until this prerequisite exists.
        office_info = admin.get('manager_office')
        mgr = admin.get('MANAGER_id')
        if mgr is None:
            mgr = next((d.get('id') for d in dwarves if d.get('name') == admin.get('MANAGER')), None)
        office_ready = isinstance(office_info, dict) and office_info.get('chair')
        if mgr is not None and pop >= 20 and not office_ready:
            area = next((a for a in sites if a.get('kind') == 'A' and a.get('open_tiles', 0) > 0
                         and a.get('w', 99) <= 20 and a.get('h', 99) <= 20), None)
            office = next((z for z in zones if z.get('type') == 'Office' and area
                           and z.get('z') == area.get('z')
                           and z.get('x', 99999) <= area.get('x', 0)
                           and z.get('y', 99999) <= area.get('y', 0)
                           and z.get('x', 0) + z.get('w', 0) >= area.get('x', 0) + area.get('w', 0)
                           and z.get('y', 0) + z.get('h', 0) >= area.get('y', 0) + area.get('h', 0)), None)
            if area and not obs.get('dig_designations_pending'):
                if not office:
                    r = offer('make_zone', {'kind': 'office', 'site': area['id']})
                    if r: return r
                elif office.get('owner') != mgr:
                    r = offer('assign_zone', {'zone_id': office['id'], 'dwarf_id': mgr})
                    if r: return r
                else:
                    has_chair = any(f.get('kind') == 'chair' and f.get('z') == office.get('z')
                                    and office.get('x', 0) <= f.get('x', -1) < office.get('x', 0) + office.get('w', 0)
                                    and office.get('y', 0) <= f.get('y', -1) < office.get('y', 0) + office.get('h', 0)
                                    for f in obs.get('furniture') or [])
                    if not has_chair and free.get('chair', 0) > 0:
                        r = offer('place_furniture', {'kind': 'chair', 'site': area['id'], 'count': 1})
                        if r: return r
        have = {w.get('type') for w in workshops}
        ready = {w.get('type') for w in workshops if w.get('built')}
        for kind in ('Carpenters', 'Still', 'Kitchen'):
            s = site('W', free=True)
            target_workshops = min(6, 1 + pop // 10) if kind == 'Carpenters' else (
                min(3, 1 + pop // 25) if kind == 'Still' else 1)
            count_workshops = sum(w.get('type') == kind for w in workshops)
            if count_workshops < target_workshops and s and stocks.get('logs_usable', 0) + stocks.get('boulders_usable', 0) > 0:
                r = offer('build_workshop', {'type': kind, 'site': s['id']})
                if r: return r
        if 'Carpenters' in ready:
            r = order('make_barrel', 3, 'barrels_empty', 8)
            if r: return r
        if 'Still' in ready:
            drink_target = max(150, 12 * pop)
            hands = obs.get('hands_off_in_days')
            left = obs.get('days_left_in_run')
            late_long_game = hands is None and isinstance(left, (int, float)) and left <= 56
            if (hands is not None and hands <= 14) or late_long_game:
                drink_target = max(400, 32 * pop)
            r = order('brew_drink', 10, 'drink', drink_target)
            if r: return r
        def bounded_room(s):
            # make_zone rejects A boxes wider or taller than twenty tiles.
            a = next((a for a in sites if a.get('kind') == 'A' and a['z'] == s['z']), None)
            if not a:
                return {'site': s['id'], 'w': 15, 'h': 15}
            x, y = min(a['x'], s['x']), min(a['y'], s['y'])
            w, h = min(15, x + 20 - s['x']), min(15, y + 20 - s['y'])
            if w < 3 or h < 3 or a['x'] + a['w'] > x + 20 or a['y'] + a['h'] > y + 20:
                return None
            return {'site': s['id'], 'w': w, 'h': h}

        # Farm before cooking: don't consume the embark's entire brewing supply.
        farms = obs.get('farm_plots') or []
        food = stocks.get('food_edible')
        if (obs.get('hands_off_in_days') is None and obs.get('days_left_in_run', 0) >= 35
                and isinstance(food, (int, float)) and food < 4 * pop):
            self.long_farm_goal = max(self.long_farm_goal, 12)
        farm_goal = max(6, (pop + 5) // 6, self.long_farm_goal)
        if len(farms) < farm_goal:
            s = site('F', free=True)
            if s:
                r = offer('build_farm', {'site': s['id']})
                if r: return r
            s = next((s for s in sites if s.get('kind') == 'R' and s.get('soil') and
                      not s.get('designated') and not s.get('used_by')), None)
            if s and bounded_room(s) and not obs.get('dig_designations_pending'):
                r = offer('dig_room', bounded_room(s))
                if r: return r
            if not obs.get('dig_designations_pending') and not any(s.get('kind') in ('A', 'R', 'E') for s in sites):
                s = site('S', free=True)
                if s:
                    r = offer('dig_stairs', {'site': s['id'], 'z_bottom': s['z'] - 1})
                    if r: return r
        # Farm footprints and three pieces of furniture per citizen compete for
        # the same floor. Open a second access when the first room is too small.
        capacity = sum(s.get('open_tiles', 0) for s in sites if s.get('kind') == 'A')
        need_space = capacity < 3 * pop + 9 * farm_goal + 5
        if need_space and not obs.get('dig_designations_pending'):
            rsite = next((s for s in sites if s.get('kind') == 'R' and s.get('soil') and
                          not s.get('designated') and not s.get('used_by')), None)
            if rsite and bounded_room(rsite):
                r = offer('dig_room', bounded_room(rsite))
                if r: return r
            areas = [s for s in sites if s.get('kind') == 'A']
            starts = [s for s in sites if s.get('kind') == 'S' and s.get('free') and not any(
                a.get('z') == s.get('z', 0) - 1 and
                a['x'] <= s['x'] < a['x'] + a['w'] and
                a['y'] <= s['y'] < a['y'] + a['h'] for a in areas) and all(
                max(a['x'] + a['w'], s['x'] + 1) - min(a['x'], s['x']) <= 20 and
                max(a['y'] + a['h'], s['y'] + 1) - min(a['y'], s['y']) <= 20
                for a in areas if a['z'] == s['z'] - 1)]
            entrances = [s for s in sites if s.get('kind') == 'E']
            if starts and areas:
                far = max(starts, key=lambda s: min((abs(s['x'] - e['x']) + abs(s['y'] - e['y'])
                                                     for e in entrances), default=0))
                r = offer('dig_stairs', {'site': far['id'], 'z_bottom': far['z'] - 1})
                if r: return r
        if farms and (obs.get('plugins') or {}).get('autofarm') != 'on':
            r = offer('enable_automation', {'name': 'autofarm'})
            if r: return r
        if 'Kitchen' in ready and (stocks.get('drink', 0) > 4 * pop or stocks.get('plants_brewable', 0) > 50):
            long_game = obs.get('hands_off_in_days') is None
            r = order('cook_meal', 3, 'prepared_meals', (6 if long_game else 2) * pop,
                      [{'stock': 'plants_brewable', 'at_least': 5 if long_game else 50}])
            if r: return r
        area = next((s for s in sites if s.get('kind') == 'A' and s.get('open_tiles', 0) > 0), None)
        if 'Carpenters' in ready:
            for recipe, stock, target in [('make_bed', 'beds', pop + 3),
                                          ('make_table', 'tables', pop + 2),
                                          ('make_chair', 'chairs', pop + 3)]:
                batch = 15 if recipe == 'make_bed' and pop >= 25 and obs.get('hands_off_in_days') is not None else 5
                r = order(recipe, batch, stock, target)
                if r: return r
        if area and not obs.get('dig_designations_pending'):
            # An A area spans a level and may overlap all of these room functions.
            for kind in ('dormitory', 'dining_hall', 'office'):
                typename = {'dormitory': 'Dormitory', 'dining_hall': 'DiningHall', 'office': 'Office'}[kind]
                if not any(z.get('type') == typename and z.get('z') == area.get('z') and
                           z.get('x', 99999) <= area.get('x', 0) and z.get('y', 99999) <= area.get('y', 0) and
                           z.get('x', 0) + z.get('w', 0) >= area.get('x', 0) + area.get('w', 0) and
                           z.get('y', 0) + z.get('h', 0) >= area.get('y', 0) + area.get('h', 0) for z in zones):
                    r = offer('make_zone', {'kind': kind, 'site': area['id']})
                    if r: return r
            office = next((z for z in reversed(zones) if z.get('type') == 'Office'), None)
            mgr = next((d.get('id') for d in dwarves if d.get('name') == admin.get('MANAGER')), None)
            if office and mgr is not None and office.get('owner') != mgr:
                r = offer('assign_zone', {'zone_id': office['id'], 'dwarf_id': mgr})
                if r: return r
            furniture = obs.get('furniture') or []
            for kind in ('chair', 'table', 'bed'):
                placed = sum(1 for f in furniture if f.get('kind') == kind)
                target = pop + (1 if kind == 'chair' else 0)
                if placed < target and free.get(kind, 0) > 0:
                    r = offer('place_furniture', {'kind': kind, 'site': area['id'],
                                                'count': min(30, target - placed, free[kind])})
                    if r: return r
        return None
