"""Iter92 prerequisite allocation and bounded same-observation map reuse.

The public API offers site handles, not arbitrary coordinates. Expanded housing
and dining therefore need uncontested levels whose A handle exposes the dig.
No private facts, scorer state, or new model calls are used.
"""
import itertools
from .operator import d, lst, overlaps, covers
from .mapcache import MapCacheRules


class LayoutRules(MapCacheRules):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.layout = {}
        self.layout_mode = False
        self.layout_reason = 'not_started'

    def load(self, resp):
        super().load(resp)
        if (not self.layout_mode and not self.roles and self.days >= 336 and not self.surge
                and self.hands_off is None and type(self.day) is int and self.day <= 3
                and self.cit <= 9 and not self.placed.get('bed') and not self.zone('dining')):
            self.layout_mode = True

    @staticmethod
    def box_valid(box):
        return (all(type(box.get(k)) is int for k in ('x', 'y', 'z', 'w', 'h'))
                and box['w'] > 0 and box['h'] > 0)

    def layout_clear(self, box):
        protected = self.zones + [d(f) for f in lst(self.o.get('farm_plots'))]
        return self.box_valid(box) and not any(
            not self.box_valid(p) or overlaps(box, p) for p in protected)

    def choose_layout(self):
        if type(self.surface) is not int:
            self.layout_reason = 'surface_unavailable'
            return
        rooms = [r for r in self.undug_rooms() if r.get('free') is True and self.box_valid(r)]
        if self.layout and 'dorm' not in self.layout:
            office, tavern = self.layout['office'], self.layout['dine']
            for r in sorted(rooms, key=lambda r: (-r['z'], r['x'])):
                box = {**r, **self.dorm_size()}
                if (r['z'] not in {office['z'], tavern['z']} and self.layout_clear(box)
                        and not any(p.get('z') == r['z'] for p in self.zones + lst(self.o.get('farm_plots')))):
                    self.layout['dorm'] = box
                    self.layout_reason = 'all_roles_reserved'
                    return
            self.layout_reason = 'awaiting_housing_level'
            return
        proposals = []
        for tavern, dorm, office in itertools.permutations(rooms, 3):
            if tavern['z'] != self.surface - 1 or len({tavern['z'], dorm['z'], office['z']}) != 3:
                continue
            boxes = {'office': {**office, 'w': 3, 'h': 3},
                     'dorm': {**dorm, **self.dorm_size()}, 'dine': {**tavern, 'w': 7, 'h': 5}}
            if not all(self.layout_clear(v) for v in boxes.values()):
                continue
            # A whole-level handle cannot safely isolate our room from a farm
            # or pre-existing activity zone elsewhere on the same level.
            occupied = self.zones + [d(f) for f in lst(self.o.get('farm_plots'))]
            if any(p.get('z') in {tavern['z'], dorm['z']} for p in occupied):
                continue
            # Prefer shallow housing and an office alongside a disjoint soil
            # farm. Tie-break by stable geometry rather than transient A IDs.
            farm_slots = sum(bool(r.get('soil')) and r['z'] not in {tavern['z'], dorm['z']}
                             and not overlaps(r, boxes['office']) and self.layout_clear(r) for r in rooms)
            if not farm_slots:
                continue
            key = (-farm_slots, -dorm['z'], office['x'], tavern['x'], dorm['x'])
            proposals.append((key, boxes))
        if proposals:
            self.layout = min(proposals, key=lambda x: x[0])[1]
            self.layout_reason = 'reserved_not_yet_dug'
        else:
            # Only four undug R candidates are advertised at first. Reserve a
            # tavern level and an office+farm level, leaving the third for beds.
            partial = []
            for tavern, office in itertools.permutations(rooms, 2):
                if tavern['z'] != self.surface - 1 or office['z'] >= tavern['z']:
                    continue
                boxes = {'office': {**office, 'w': 3, 'h': 3}, 'dine': {**tavern, 'w': 7, 'h': 5}}
                if not all(self.layout_clear(v) for v in boxes.values()):
                    continue
                if any(p.get('z') == tavern['z'] for p in self.zones + lst(self.o.get('farm_plots'))):
                    continue
                if not any(r.get('soil') and r['z'] == office['z'] and not overlaps(r, boxes['office'])
                           and self.layout_clear(r) for r in rooms):
                    continue
                partial.append(((-office['z'], office['x'], tavern['x']), boxes))
            if partial:
                self.layout = min(partial, key=lambda x: x[0])[1]
                self.layout_reason = 'office_tavern_reserved_housing_level_pending'
            else:
                self.layout_reason = 'awaiting_disjoint_living_levels_and_farm'

    def office(self):
        # A 1x1 stair zone cannot hold a chair. On all tasks, do not create it
        # as an early fallback; wait for observed room floor or a real A area.
        if self.layout_mode and not self.layout:
            return
        original = self.sites
        self.sites = [s for s in original if s.get('kind') != 'A' or (s.get('open_tiles') or 0) >= 6]
        if self.layout:
            chosen = self.layout['office']
            self.sites = [s for s in self.sites if s.get('kind') not in {'A', 'R'}
                          or (s.get('z') == chosen['z'] and s.get('x') == chosen['x']
                              and s.get('y') == chosen['y'] and s.get('w') == chosen['w']
                              and s.get('h') == chosen['h'])]
        try:
            return super().office()
        finally:
            self.sites = original

    def digging(self):
        if not self.layout_mode:
            return super().digging()
        stairs = self.kind('S')
        if not self.layout or 'dorm' not in self.layout:
            self.choose_layout()
        if 'dorm' not in self.layout and stairs and type(self.surface) is int:
            # A partial two-level reservation is not proof the third floor is
            # reachable. The bounded retry survives that waiting state.
            self.act('stairs', 'dig_stairs', {'site': stairs[-1]['id'], 'z_bottom': self.surface - 4}, retry=12, limit=3)
        if not self.layout:
            return  # never burn the scarce offered sites on opportunistic farms
        if (self.o.get('dig_designations_pending') or 0) > 90:
            return
        for role in ('office', 'dorm', 'dine'):
            box = self.layout.get(role)
            if box is None:
                continue
            if self.roles.get(box['id']) == role:
                continue
            live = next((r for r in self.kind('R') if r['id'] == box['id']), None)
            if (not live or live.get('designated') or not live.get('free')
                    or any(live.get(k) != box[k] for k in ('x', 'y', 'z'))
                    or not self.layout_clear(box)):
                self.layout_reason = 'reserved_site_unavailable:' + role
                continue
            result = self.act('layout_dig_' + box['id'], 'dig_room',
                              {'site': box['id'], 'w': box['w'], 'h': box['h']}, retry=3, limit=3)
            if result and result.get('ok'):
                self.roles[box['id']] = role
                self.room_reservations[box['id']] = dict(box)
        if 'dorm' not in self.layout or not all(self.roles.get(v['id']) == role for role, v in self.layout.items()):
            return
        self.layout_reason = 'living_digs_accepted_waiting_observation'
        reserved_levels = {self.layout[r]['z'] for r in ('dorm', 'dine')}
        farms = len(lst(self.o.get('farm_plots'))) + sum(v == 'farm' for v in self.roles.values())
        for r in self.undug_rooms():
            if (farms >= self.farm_target() or r['id'] in self.roles or not r.get('soil')
                    or r.get('z') in reserved_levels or not self.layout_clear(r)
                    or any(overlaps(r, box) for box in self.layout.values())):
                continue
            result = self.act('dig_' + r['id'], 'dig_room', {'site': r['id']}, retry=3, limit=2)
            if result and result.get('ok'):
                self.roles[r['id']] = 'farm'
                self.room_reservations[r['id']] = dict(r)
                farms += 1

    def farms(self):
        if not self.layout_mode:
            return super().farms()
        if 'dorm' not in self.layout:
            return
        # F sites are discovered independently of role-labelled R rooms. Keep
        # the whole living levels exclusive, not only the requested dig boxes.
        levels = {self.layout[r]['z'] for r in ('dorm', 'dine')}
        original = self.sites
        self.sites = [site for site in original if site.get('z') not in levels]
        try:
            return super().farms()
        finally:
            self.sites = original

    def room_for(self, role):
        if self.layout_mode and role in {'dorm', 'dine'}:
            box = self.layout.get(role)
            if box is None:
                return None
            # Reobserve the actual expanded footprint. R remains a small handle;
            # only a disjoint A area can target the rest of the excavation.
            areas = [s for s in self.kind('A') if self.box_valid(s) and covers(s, box)
                     and (s.get('open_tiles') or 0) >= 6 and not self.is_full(s['id'])
                     and not any(overlaps(s, p) for p in lst(self.o.get('farm_plots')) + self.zone('office'))]
            if areas:
                return min(areas, key=lambda s: s['w'] * s['h'])
            return next((r for r in self.kind('R') if r['id'] == box['id'] and r.get('dug')
                         and not self.is_full(r['id'])), None)
        return super().room_for(role)
