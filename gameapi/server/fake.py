"""A fake DF backend and a fake facts layer: the rules' unit tests, and `python3 -m gameapi.server --fake` (the API
without DF, for developing a harness or the runner against). Time, a few stocks and tripwires only."""
import json, os

DAY = 1200


class FakeBackend:
    def __init__(self, start=1_000_000, citizens=7, ticks_per_s=None, stops=None, die_at=None):
        self.tick, self.citizens = start, citizens
        self.food = self.drink = 50
        self.stops = dict(stops or {})   # abs_tick -> stop dict: an advance crossing it stops there
        self.die_at = die_at             # abs_tick at which every citizen dies
        self.advances = []               # (from, requested ticks)
        self.prepared = self.setup_cmds = None
        self.interrupted = 0
        self.ticks_per_s = ticks_per_s
        self.on_advance = None           # hook(backend, ticks) for tests (e.g. move a fake clock)

    def df_settings(self, task):
        return {"ARTIFACTS": "YES" if task.get("strange_moods") else "NO"}

    def prepare(self, task):
        self.prepared = task
        return self.score()

    def setup(self, cmds):
        self.setup_cmds = cmds
        return ["ok"] * len(cmds)

    def credit_start(self):
        return {}

    def score(self):
        return {"abs_tick": self.tick, "citizens": self.citizens, "food": self.food, "drink": self.drink,
                "wealth_created": 0, "citizen_deaths": 0}

    def advance(self, ticks):
        self.advances.append((self.tick, ticks))
        if self.on_advance:
            self.on_advance(self, ticks)
        target = self.tick + ticks
        stop = None
        for t in sorted(self.stops):
            if self.tick < t <= target:
                target, stop = t, dict(self.stops.pop(t), abs_tick=t, after_ticks=t - self.tick)
                break
        if self.die_at is not None and self.tick < self.die_at <= target:
            target, self.citizens = self.die_at, 0
        moved = target - self.tick
        self.drink = max(0, self.drink - moved // DAY)
        self.tick = target
        return moved, stop, []

    def interrupt(self):
        self.interrupted += 1

    def interruption_log(self):
        return []

    def final(self, outdir, stem, start, hung=False):
        n = (self.tick - start) // DAY + 1
        daily = {"samples": [{"abs_tick": start + i * DAY, "citizens": self.citizens, "drink": self.drink,
                              "food": self.food} for i in range(n)], "events": {}}
        with open(os.path.join(outdir, f"{stem}.daily.json"), "w") as f:
            json.dump(daily, f)
        with open(os.path.join(outdir, f"{stem}.credit.json"), "w") as f:
            json.dump({"items": []}, f)
        return self.score(), {"days_sampled": n}, {"items": []}, None


class FakeFacts:
    NAME = "fake"
    OBS_SCHEMA = "6-fake"
    STRICT_ARGS = True

    def __init__(self):
        self.calls = []
        self.resets = 0

    def reset(self):
        self.resets += 1

    def tools(self):
        return [{"type": "function", "function": {"name": "add_order", "description": "queue a work order",
                 "parameters": {"type": "object", "required": ["recipe", "amount"], "properties": {
                     "recipe": {"type": "string", "enum": ["brew_drink", "make_bed"]},
                     "amount": {"type": "integer", "minimum": 1, "maximum": 30}}}}},
                {"type": "function", "function": {"name": "cancel_order", "description": "remove an order",
                 "parameters": {"type": "object", "required": ["order_id"], "properties": {
                     "order_id": {"type": "integer"}}}}},
                {"type": "function", "function": {"name": "advance_days", "description": "the facts layer's own",
                 "parameters": {"type": "object", "properties": {"days": {"type": "integer"}}}}}]

    def key_tools(self):
        return self.tools()

    def queries(self):
        return [{"name": "stocks", "description": "stock counts", "params": {}}]

    def manual(self):
        return "fake manual"

    def observe(self):
        return {"obs_schema": self.OBS_SCHEMA, "stocks": {"drink": 50}}

    def query(self, name, **params):
        if name != "stocks":
            raise KeyError(name)
        return {"stocks": {"drink": 50}, "params": params}

    def act(self, tool, args):
        self.calls.append((tool, args))
        if tool == "cancel_order":
            return {"ok": False, "error_code": "no_such_order", "error": f"no order with id {args['order_id']}"}
        return {"ok": True, "result": {"order_id": len(self.calls)}}

    def events(self, since_tick):
        return {"events": [{"id": 1, "tick": since_tick, "type": "FAKE", "text": "nothing happened"}], "dropped": 0}
