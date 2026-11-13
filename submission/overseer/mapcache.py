"""Bounded public map-query reuse within a single observation and mutation epoch."""
import copy
import json


class MapCacheRules:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._map_cache = {}
        self.map_cache_hits = 0

    def load(self, resp):
        self._map_cache.clear()
        return super().load(resp)

    def act(self, *args, **kwargs):
        # Clear BEFORE even a refused/ambiguous mutation. No response fingerprint
        # or observed tick is treated as permission to retain stale map state.
        self._map_cache.clear()
        return super().act(*args, **kwargs)

    def q(self, name, **params):
        if name != 'map':
            return super().q(name, **params)
        key = json.dumps(params, sort_keys=True, separators=(',', ':'))
        if key in self._map_cache:
            self.map_cache_hits += 1
            return copy.deepcopy(self._map_cache[key])
        value = super().q(name, **params)
        if value is not None and len(self._map_cache) < 16:
            self._map_cache[key] = copy.deepcopy(value)
        return value

