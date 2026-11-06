"""The advisor: one model call at a checkpoint, with a compact brief of the fort, that may return a few tool calls.

The playbook does the routine work. The advisor sees what the playbook is doing, what keeps failing and what looks
wrong, and can act where the rules don't reach (an odd layout, a mood, a threat, a shortage the rules didn't fix).
Its calls run under the harness's guards; advance_days is the harness's, never the advisor's.
"""
import json

from . import knowledge
from .memory import DAY

MAX_CALLS = 4             # tool calls run per advice
EVERY_DAYS = 28           # routine checkpoint gap (game days)
PROBLEM_GAP_DAYS = 5      # min gap between problem-driven calls
# the advisor's tools: additive and local. Cancelling orders, digging, appointing and plugins stay with the
# playbook, so one bad call can't undo the fort's layout or management.
ALLOWED = {"build_workshop", "build_farm", "add_order", "add_manager_order", "place_furniture", "make_zone",
           "assign_zone", "slaughter", "create_squad", "equip_squad", "squad_order", "create_burrow",
           "civilian_alert", "build_door", "lock_door"}
BUDGET_STOP = 0.85        # stop asking at this share of the game's credits
CHAT = {"temperature": 0.2, "max_tokens": 3000, "reasoning": {"effort": "low"}}
FEEDBACK_KEEP = 8


class Advisor:
    def __init__(self, model, tools, info, credits, log):
        self.model, self.info, self.credits, self.log = model, info, credits, log
        self.tools = [t for t in tools if (t.get("function") or {}).get("name") in ALLOWED]
        self.last_tick = None
        self.last_problem_tick = None
        self.disabled = None
        self.recent = []   # (tool, args, ok, error) of the advisor's own recent calls

    def spent(self):
        return self.model.usage.get("cost_usd") or 0.0

    def due(self, fort, mem):
        if self.disabled:
            return False
        if self.credits and self.spent() >= BUDGET_STOP * self.credits:
            self.disabled = "budget"
            return False
        now = fort.tick
        if fort.hands_off_in is not None and fort.hands_off_in <= 0:
            return False
        if fort.problems() and (self.last_problem_tick is None or now - self.last_problem_tick >= PROBLEM_GAP_DAYS * DAY):
            return True
        return self.last_tick is None or now - self.last_tick >= EVERY_DAYS * DAY

    def advise(self, fort, mem):
        now = fort.tick
        self.last_tick = now
        if fort.problems():
            self.last_problem_tick = now
        msgs = [{"role": "system", "content": knowledge.ADVISOR_SYSTEM},
                {"role": "user", "content": self.brief(fort, mem)}]
        resp = self.model.chat(msgs, tools=self.tools, tool_choice="auto", **CHAT)
        msg = (resp.get("choices") or [{}])[0].get("message") or {}
        calls = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                continue
            if isinstance(args, dict) and fn.get("name") in ALLOWED:
                calls.append((fn["name"], args))
        self.log("advice", day=fort.day, calls=calls, text=(msg.get("content") or "")[:400],
                 usage=resp.get("usage"))
        return calls

    def feedback(self, tool, args, resp):
        ok = bool(resp.get("ok"))
        self.recent.append((tool, args, ok, None if ok else f"{resp.get('error_code')}: {str(resp.get('error'))[:100]}"))
        self.recent = self.recent[-FEEDBACK_KEEP:]

    def brief(self, fort, mem):
        parts = [f"TASK: {self.info.get('name')}. Day {fort.day} of {fort.days_total}; {fort.days_left} days left."]
        if fort.hands_off_in is not None:
            parts.append(f"HANDS-OFF in {fort.hands_off_in} days: after that no actions are possible.")
        if self.info.get("goal"):
            parts.append("GOAL: " + str(self.info["goal"]).replace("{days}", str(fort.days_total)))
        if self.info.get("brief"):
            parts.append("SITUATION: " + str(self.info["brief"]))
        parts.append("FORT:\n" + fort.summary())
        probs = fort.problems()
        if probs:
            parts.append("PROBLEMS (from the harness's checks):\n" + "\n".join("- " + p for p in probs))
        parts.append("THE AUTOPILOT IS HANDLING:\n" + "\n".join("- " + p for p in fort.autopilot_plan()))
        fails = mem.failing()
        if fails:
            parts.append("STEPS THAT KEEP FAILING:\n" + "\n".join(f"- {k}: {v}" for k, v in list(fails.items())[:10]))
        if self.recent:
            parts.append("YOUR LAST CALLS:\n" + "\n".join(
                f"- {t} {json.dumps(a)[:100]} -> {'ok' if ok else err}" for t, a, ok, err in self.recent))
        notes = [t for _, t in mem.log[-8:]]
        if notes:
            parts.append("RECENT HARNESS NOTES:\n" + "\n".join("- " + n for n in notes))
        parts.append("Make at most %d tool calls that fix the most important problem the autopilot is not already "
                     "handling, or make no call if nothing needs you. Reply with one short sentence of reasoning."
                     % MAX_CALLS)
        return "\n\n".join(parts)
