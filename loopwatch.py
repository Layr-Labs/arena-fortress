#!/usr/bin/env python3
"""Loop / stuck detection for agent arms: flags when an agent repeats failing calls, spams one tool, never
advances time on its own, or keeps acting with nothing to show for it.

smoke.py feeds every step record to a LoopWatch (telemetry for all v2 arms: per-step `loop_flags`, a `loops`
block in the summary). With `smoke.py --loop-notes` the model2 arm also gets a one-line HARNESS NOTE appended to
the tool result when a flag starts; that changes what the agent sees, so it is a different arm and off by default.

Works on step logs too (the same records), so existing runs can be checked offline:
    python3 loopwatch.py runs/<batch>/*/model2-*.jsonl
stdlib only.
"""
import json, sys
from collections import deque

DAY = 1200
REPEAT_FAILS = 3        # identical (tool, args) call failed this many times within the window
WINDOW = 20             # calls considered by repeat_fail and error_rate
ERROR_STREAK = 5        # consecutive failed calls
ERROR_RATE = 0.6        # share of failed calls in the last WINDOW calls (needs a full window)
TOOL_SPAM = 10          # consecutive calls to one tool (any args) other than advance_days
FORCED_STREAK = 3       # consecutive harness-forced advances: the agent never advances time itself
NO_PROGRESS_DAYS = 60   # in-game days with no rise in credited value, drink or food while the agent keeps acting
NO_PROGRESS_CALLS = 30  # ...and at least this many non-advance calls in that span

NOTES = {
    "repeat_fail": "this exact call has failed {n} times recently ({err}). Repeating it will not work: change the "
                   "arguments, fix the cause, or do something else.",
    "error_streak": "your last {n} calls all failed. Read the errors and the observation before the next call.",
    "error_rate": "{n} of your last {w} calls failed.",
    "tool_spam": "you have called {tool} {n} times in a row. If it is not making progress, try something else "
                 "or advance_days.",
    "forced_advance": "the harness has advanced time for you {n} times in a row because you did not call "
                      "advance_days. Advance time once your orders and designations are in place.",
    "no_progress": "nothing measurable has improved in {n} days (credited production, drink, food) although you "
                   "keep acting. Re-check stuck_because on your orders.",
}


def _sig(tool, raw):
    try:
        return tool, json.dumps(json.loads(raw or "{}"), sort_keys=True)
    except (ValueError, TypeError):
        return tool, str(raw)


class LoopWatch:
    def __init__(self, start_tick):
        self.start = start_tick
        self.calls = deque(maxlen=WINDOW)    # (sig, err)
        self.err_streak = self.spam = self.forced = self.busy = 0
        self.spam_tool = None
        self.best = None                     # (credited, drink, food) high-water marks
        self.best_tick = start_tick
        self.active = set()
        self.stats = {}                      # kind -> {episodes, steps, first_day, example}
        self.max_err_streak = self.max_spam = 0

    def step(self, rec):
        """Update from one step record (smoke.py's `rec`). Returns [(kind, note)] for flags that start here."""
        tick = rec.get("abs_tick") or self.start
        day = (tick - self.start) // DAY
        progress = (rec.get("credited") or 0, rec.get("drink") or 0, rec.get("food") or 0)
        if self.best is None:
            self.best = progress
        elif any(p > b for p, b in zip(progress, self.best)):
            self.best = tuple(max(p, b) for p, b in zip(progress, self.best)); self.best_tick = tick; self.busy = 0
        call = rec.get("call")
        on = {}
        if call:
            tool, err = call.get("tool"), bool(call.get("error"))
            sig = _sig(tool, call.get("args"))
            self.calls.append((sig, err))
            self.err_streak = self.err_streak + 1 if err else 0
            self.max_err_streak = max(self.max_err_streak, self.err_streak)
            if tool == "advance_days":
                self.spam, self.spam_tool = 0, None
            else:
                self.busy += 1
                self.spam = self.spam + 1 if tool == self.spam_tool else 1
                self.spam_tool = tool
            self.max_spam = max(self.max_spam, self.spam)
            fails = sum(1 for s, e in self.calls if e and s == sig)
            if err and fails >= REPEAT_FAILS:
                on["repeat_fail"] = {"n": fails, "err": str(call.get("result", ""))[:120], "tool": tool}
            if self.err_streak >= ERROR_STREAK:
                on["error_streak"] = {"n": self.err_streak, "tool": tool}
            n_err = sum(e for _, e in self.calls)
            if len(self.calls) == WINDOW and n_err >= ERROR_RATE * WINDOW:
                on["error_rate"] = {"n": n_err, "w": WINDOW, "tool": tool}
            if self.spam >= TOOL_SPAM:
                on["tool_spam"] = {"n": self.spam, "tool": tool}
        if "forced_advance" in rec:
            self.forced += 1
        elif call and call.get("tool") == "advance_days":
            self.forced = 0
        if self.forced >= FORCED_STREAK:
            on["forced_advance"] = {"n": self.forced}
        idle_days = (tick - self.best_tick) // DAY
        if idle_days >= NO_PROGRESS_DAYS and self.busy >= NO_PROGRESS_CALLS:
            on["no_progress"] = {"n": idle_days}
        started = []
        for kind, info in on.items():
            st = self.stats.setdefault(kind, {"episodes": 0, "steps": 0, "first_day": day, "example": None})
            st["steps"] += 1
            if kind not in self.active:
                st["episodes"] += 1
                if st["example"] is None:
                    st["example"] = {"day": day, **{k: v for k, v in info.items() if k != "w"}}
                started.append((kind, "HARNESS NOTE: " + NOTES[kind].format(**{"tool": "", "w": WINDOW, **info})))
        self.active = set(on)
        return started

    def summary(self):
        return {"flags": self.stats, "max_error_streak": self.max_err_streak, "max_tool_streak": self.max_spam,
                "flagged": sorted(self.stats)}


def scan(path):
    """Replay a step log; -> (LoopWatch, n_steps)."""
    recs = [json.loads(l) for l in open(path) if l.strip()]
    w = LoopWatch(recs[0]["abs_tick"] if recs else 0)
    for r in recs:
        w.step(r)
    return w, len(recs)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        w, n = scan(p)
        s = w.summary()
        flags = ", ".join(f"{k} x{v['episodes']} ({v['steps']} steps, from day {v['first_day']})"
                          for k, v in sorted(s["flags"].items())) or "none"
        print(f"{p}: {n} steps, max error streak {s['max_error_streak']}, max same-tool streak "
              f"{s['max_tool_streak']}: {flags}")
