"""A fake DFHack for the facts layer's unit tests: canned answers by script/command, every call recorded."""
import json
import os


class FakeDF:
    def __init__(self, observe=None, act=None, query=None, events=None, enable="autochop: off\nautofarm: on\n",
                 quickfort="", place=None, digplan="KEEP"):
        self.calls = []
        self.blueprints = {}
        self.observe_out = observe or {}
        self.act_out = act or {}          # cmd -> dict or callable(args) -> dict
        self.query_out = query or {}      # name -> dict
        self.events_out = events or {"ok": True, "events": [], "dropped": 0, "now": 0}
        self.enable = enable
        self.quickfort = quickfort
        self.place = place or {"ok": True, "x": 1, "y": 1, "z": 1, "available": 5, "tiles": [[1, 1, 1], [2, 1, 1]]}
        self.digplan = digplan

    def write_blueprint(self, name, text):
        self.blueprints[name] = text

    def run(self, *args, with_stderr=False):
        args = [str(a) for a in args]
        self.calls.append(args)
        if args[0] == "enable":
            return self.enable
        if args[0] == "quickfort":
            return self.quickfort(args) if callable(self.quickfort) else self.quickfort
        if args[:2] == ["lua", "-f"]:
            script, rest = os.path.basename(args[2]), args[3:]
            if script == "observe.lua":
                o = self.observe_out(rest) if callable(self.observe_out) else self.observe_out
                return json.dumps(o)
            if script == "act.lua":
                v = self.act_out.get(rest[0], {"ok": True})
                return json.dumps(v(rest) if callable(v) else v)
            if script == "query.lua":
                v = self.query_out.get(rest[0], {"ok": True})
                return json.dumps(v(rest) if callable(v) else v)
            if script == "events.lua":
                return json.dumps(self.events_out)
            if script == "place.lua":
                return json.dumps(self.place)
            if script == "digplan.lua":
                return self.digplan
        return ""


def obs(tick=1000, candidates=None, **extra):
    o = {"schema": 7, "date": {"abs_tick": tick, "year": 1, "day_of_year": 1, "season": "spring"},
         "site_candidates": candidates if candidates is not None else {
             "W": [{"x": 10, "y": 10, "z": 5, "w": 3, "h": 3, "anchor": "centre"}],
             "S": [{"x": 20, "y": 20, "z": 5, "w": 1, "h": 1}],
             "R": [{"x": 30, "y": 30, "z": 4, "w": 3, "h": 3, "soil": True}],
             "E": [{"x": 5, "y": 5, "z": 5, "w": 1, "h": 1, "kind": "down_stair"}]},
         "farm_plots": [], "zones": [], "zones_total": 0, "orders": [], "dig_pending_by_z": [],
         "map": {"size": [12, 12, 122], "wagon": {"x": 1, "y": 1, "z": 5, "present": True}, "surface_z": 5}}
    o.update(extra)
    return o
