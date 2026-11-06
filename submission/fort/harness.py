"""The loop: observe, let the playbook act, ask the advisor when it's worth it, advance.

One cycle:
  1. GET /observe (plus the free queries the playbook asks for) -> a Fort view (state.py)
  2. the playbook (playbook.py) returns the actions it wants now, in priority order; they run until the day's
     action budget (keeping a reserve for the advisor) or until one changes what the next would need
  3. the advisor (advisor.py: one model call) runs at checkpoints and when the playbook reports problems it can't
     fix; it may make a few tool calls, which run under the same guards
  4. advance: the playbook picks the days (short while things are being set up or something is wrong, longer
     when the fort is stable), with tripwires on
The harness exits at the horizon, at the hands-off window, or when the game is over.
"""
import json
import os
import time

from dfbench_client import ActionLimit, BudgetExhausted, GameOver, HandsOff, ModelError

from . import advisor, layout, playbook, state
from .memory import DAY, Memory

ACTION_RESERVE = 6          # actions per day kept for the advisor
MAX_ACTIONS_PER_CYCLE = 30  # playbook actions per cycle
STOP_ON = ["hostile_visible", "hostile_near_citizens", "citizen_died", "invasion", "water_rising",
           "announcement:STRANGE_MOOD", "announcement:MIGRANT_ARRIVAL", "announcement:BERSERK_CITIZEN",
           "announcement:CITIZEN_TANTRUM"]


def log(kind, **kw):
    print(json.dumps({"t": round(time.time(), 2), "kind": kind, **kw}, default=str), flush=True)


class Harness:
    def __init__(self, task, game, model):
        self.task, self.game, self.model = task, game, model
        self.mem = Memory()
        self.stats = {"cycles": 0, "actions": 0, "rejected": 0, "advances": 0, "advisor_calls": 0,
                      "advisor_actions": 0, "model_errors": 0}
        self.stop_reason = None
        self.t0 = time.time()
        self.no_advisor = False
        self.max_day = int(os.environ.get("FORT_MAX_DAY", "0") or 0)   # local testing: stop at this day

    # --- setup ----------------------------------------------------------------------------------------------------
    def setup(self):
        t = self.game.task()
        self.info = {**(self.task.task or {}), **(t.get("task") or {})}
        self.tools = t.get("tools") or []
        self.tool_names = {(x.get("function") or {}).get("name") for x in self.tools}
        self.days = self.info.get("days") or self.task.days or 336
        self.advisor = advisor.Advisor(self.model, self.tools, self.info, self.task.credits, log)
        self.mem.vals["task_name"] = self.info.get("name") or ""
        log("setup", task=self.info.get("name"), days=self.days, hands_off=self.info.get("hands_off"),
            credits=self.task.credits)

    # --- acting ---------------------------------------------------------------------------------------------------
    def act(self, key, tool, args, source="playbook", once=False):
        """Run one tool call. Returns the response dict (ok or not). Raises HandsOff/GameOver."""
        now = self.tick()
        if tool not in self.tool_names:
            resp = {"ok": False, "error_code": "unknown_tool", "error": tool}
        else:
            try:
                resp = self.game.act(tool, args)
            except ActionLimit as e:
                resp = {"ok": False, "error_code": "action_limit", "error": str(e)}
        ok = bool(resp.get("ok"))
        err = None if ok else f"{resp.get('error_code')}: {str(resp.get('error'))[:120]}"
        if key:
            self.mem.record(key, now, ok, err, once=once)
        self.stats["actions"] += 1
        self.stats["rejected"] += not ok
        r = resp.get("result") if isinstance(resp.get("result"), dict) else {}
        layout.after(key, tool, args, resp, self.mem)
        if ok and tool in ("add_order", "add_manager_order") and r.get("order_id") is not None:
            self.mem.orders[r["order_id"]] = (key, now)
        log("act", src=source, key=key, tool=tool, args=args, ok=ok, err=err,
            result=json.dumps(r, default=str)[:300] if ok else None)
        if not ok:
            self.mem.note(now, f"{tool} {json.dumps(args)[:80]} failed: {err}")
        return resp

    def tick(self):
        return (self.game.last or {}).get("tick") or 0

    def actions_left(self, resp=None):
        v = (resp or {}).get("actions_left_today")
        return v if isinstance(v, int) else None

    # --- main loop ------------------------------------------------------------------------------------------------
    def run(self):
        self.setup()
        while True:
            resp = self.game.observe()
            if resp.get("game_over"):
                self.stop_reason = "game_over"
                break
            fort = state.Fort(resp, self.game, self.info, self.mem)
            if self.max_day and fort.day >= self.max_day:
                self.stop_reason = "max_day"
                break
            self.stats["cycles"] += 1
            try:
                left = self.play(fort)
                if not self.no_advisor and self.advisor.due(fort, self.mem):
                    self.consult(fort, left)
                days = playbook.advance_days(fort, self.mem)
                if not self.advance(days):
                    break
            except (HandsOff, GameOver) as e:
                self.stop_reason = type(e).__name__
                break
        log("done", reason=self.stop_reason, stats=self.stats, usage=self.model.usage,
            wall_s=round(time.time() - self.t0, 1))

    def play(self, fort):
        """Run the playbook's actions for this cycle. Returns the actions left today (or None if unknown)."""
        left = None
        n = 0
        for _ in range(6):   # re-plan after a batch, since one action can enable the next
            plan = playbook.plan(fort, self.mem)
            if not plan:
                break
            ran = 0
            for step in plan:
                if n >= MAX_ACTIONS_PER_CYCLE or (left is not None and left <= ACTION_RESERVE):
                    return left
                key, tool, args = step[:3]
                once = bool(step[3]) if len(step) > 3 else False
                resp = self.act(key, tool, args, once=once)
                left = self.actions_left(resp) if self.actions_left(resp) is not None else left
                n += 1
                ran += 1
                if resp.get("ok") and playbook.replan_after(tool):
                    break
            if not ran:
                break
            fort = state.Fort(self.game.observe(), self.game, self.info, self.mem)
        return left

    def consult(self, fort, left):
        try:
            calls = self.advisor.advise(fort, self.mem)
        except BudgetExhausted:
            self.advisor.disabled = "budget"
            return
        except ModelError as e:
            self.stats["model_errors"] += 1
            log("model_error", error=str(e)[:300])
            return
        self.stats["advisor_calls"] += 1
        for tool, args in calls[:advisor.MAX_CALLS]:
            if tool == "advance_days":
                continue
            if left is not None and left <= 1:
                break
            resp = self.act("llm:" + tool, tool, args, source="advisor")
            left = self.actions_left(resp) if self.actions_left(resp) is not None else left
            self.stats["advisor_actions"] += 1
            self.advisor.feedback(tool, args, resp)

    def advance(self, days):
        try:
            resp = self.game.act("advance_days", {"days": int(days), "stop_on": STOP_ON})
        except (HandsOff, GameOver) as e:
            self.stop_reason = type(e).__name__
            return False
        self.stats["advances"] += 1
        r = resp.get("result") if isinstance(resp.get("result"), dict) else {}
        log("advance", days=days, day=resp.get("day"), stopped=r.get("stopped"),
            hands_off=r.get("hands_off"), end=r.get("end_reason"))
        if r.get("stopped"):
            self.mem.note(self.tick(), f"advance stopped: {json.dumps(r['stopped'])[:160]}")
        if resp.get("game_over") or r.get("hands_off") or r.get("end_reason") or r.get("wall_capped"):
            self.stop_reason = r.get("end_reason") or ("hands_off" if r.get("hands_off") else "game_over")
            return False
        return True
