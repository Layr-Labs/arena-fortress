"""Bounded, public-facts maintenance layered onto the promoted status harness."""

class MeetingArea:
    def __init__(self):
        self.next_try = 0

    def step(self, obs, tick):
        if tick is None or tick < self.next_try or obs.get('moods') or obs.get('dig_designations_pending'):
            return None
        if (obs.get('threats') or {}).get('visible_hostiles'):
            return None
        labels = [str(d.get('profession') or '').lower() for d in obs.get('dwarves') or []]
        for event in obs.get('recent_events') or []:
            text = str(event).lower()
            if any(p in text for p in ('attack', 'bites the', 'shakes the', 'strikes the')) and any(
                    label and 'the ' + label in text for label in labels):
                return None
        zones = obs.get('zones') or []
        for area in (obs.get('map') or {}).get('sites') or []:
            if (area.get('kind') != 'A' or area.get('open_tiles', 0) < 50
                    or area.get('w', 99) > 20 or area.get('h', 99) > 20):
                continue
            if any(z.get('type') == 'MeetingHall' and z.get('z') == area.get('z') for z in zones):
                return None
            self.next_try = tick + 7 * 1200
            return 'make_zone', {'kind': 'meeting_area', 'site': area['id']}
        return None
