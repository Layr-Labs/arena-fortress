"""What the harness remembers across turns: attempts per step, failures, notes for the advisor, orders it made.

A step is keyed by a short string (e.g. "ws:Still", "order:brew"). Each attempt is recorded with its tick and the
API's error code, so the playbook can back off a failing step and the advisor can be told what keeps failing.
"""
DAY = 1200


class Memory:
    def __init__(self):
        self.tries = {}      # key -> attempts
        self.last = {}       # key -> tick of the last attempt
        self.fails = {}      # key -> consecutive failures
        self.errors = {}     # key -> last error text (short)
        self.done = set()    # keys that succeeded and never need repeating
        self.vals = {}       # free-form state the playbook keeps (stair site, room ids, ...)
        self.log = []        # (tick, text) recent notable outcomes, for the advisor
        self.orders = {}     # order id -> (key, tick) for orders this harness added

    # --- attempts -----------------------------------------------------------------------------------------------
    def may(self, key, now, every_days=2.0, max_tries=None, backoff=True):
        """True when the step may be tried now: not done, under max_tries, and its retry gap has passed. The gap
        doubles with each consecutive failure (capped at 16x) when backoff is on."""
        if key in self.done:
            return False
        if max_tries is not None and self.tries.get(key, 0) >= max_tries:
            return False
        gap = every_days * DAY
        if backoff:
            gap *= min(16, 2 ** self.fails.get(key, 0))
        return now - self.last.get(key, -10 ** 12) >= gap

    def record(self, key, now, ok, error=None, once=False):
        self.tries[key] = self.tries.get(key, 0) + 1
        self.last[key] = now
        if ok:
            self.fails[key] = 0
            self.errors.pop(key, None)
            if once:
                self.done.add(key)
        else:
            self.fails[key] = self.fails.get(key, 0) + 1
            self.errors[key] = str(error or "failed")[:160]

    def note(self, now, text):
        self.log.append((now, str(text)[:240]))
        self.log = self.log[-40:]

    def failing(self, min_fails=2):
        """Steps that failed at least min_fails times in a row: {key: last error}."""
        return {k: self.errors.get(k, "") for k, n in self.fails.items() if n >= min_fails}
