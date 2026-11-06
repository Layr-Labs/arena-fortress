"""The plain baseline harness: the model plays the fort from the raw game API, one tool call per turn.

One turn:
  1. GET /observe -> the observation as the API returns it, plus days_left_in_run, hands_off_in_days, goal, scenario
  2. the user message "OBSERVATION {...}"; the history window (system prompt + last HISTORY messages, older
     observations stubbed, older tool results trimmed)
  3. one chat call through the gateway (tool_choice required)
  4. run the first tool call (POST /act); its result goes back to the model as JSON
  5. guards: refuse order churn locally; advance a day after STALL_AFTER actions without one, or when the day's
     actions are used up; stop calling the model near the end of the credits
The harness exits when the game is over, the hands-off window starts, the model keeps failing, or the credits run
low; the server then runs the fort on unmanaged to the horizon (contract §2).

There is no summary of the fort, no diagnosis of stuck orders and no memory beyond the history window: the model
reads the raw facts. README.md lists the obvious places to improve.

Run: python -m plain   (reads DFBENCH_TASK)
"""
import copy
import json
import os
import sys
import time

from dfbench_client import (ActionLimit, BudgetExhausted, ContextTooLong, GameAPIError, GameClient, GameOver,
                            HandsOff, ModelClient, ModelError, load_task)

from overseer.harness import Overseer

from . import prompt

HISTORY = 12                # messages kept after the system prompt
TOOL_RESULT_OLD = 300       # chars of an older tool result kept in the window (the latest is whole)
TOOL_RESULT_MAX = 4000      # chars of the latest tool result
MAX_DAYS = 14               # advance_days cap (the API allows 28)
STALL_AFTER = 10            # consecutive actions without an advance before the harness advances 1 day itself
MAX_API_STREAK = 5          # consecutive failed model turns before the harness exits
BUDGET_STOP = 0.92          # stop calling the model at this fraction of the game's credits
CHURN_DAYS = 3              # order-churn guard: no identical re-add within this many days of a cancel,
FRESH_DAYS = 2              #   and no cancel of an order this harness added under this many days ago
ORDER_TOOLS = ("add_order", "add_manager_order")
CHAT = {"tool_choice": "required", "temperature": 0, "max_tokens": 4000, "reasoning": {"effort": "low"}}
ENVELOPE = ("day", "tick", "days_left", "game_over", "hands_off_in_days")
DAY = 1200                  # ticks per game day


def log(kind, **kw):
    print(json.dumps({"t": round(time.time(), 2), "kind": kind, **kw}, default=str), flush=True)


def prepare_tools(tools):
    """The API's tool schemas, with advance_days capped at MAX_DAYS."""
    out = copy.deepcopy(tools or [])
    for t in out:
        f = t.get("function") or {}
        if f.get("name") == "advance_days":
            days = ((f.get("parameters") or {}).get("properties") or {}).get("days")
            if isinstance(days, dict):
                days["maximum"] = min(days.get("maximum", MAX_DAYS), MAX_DAYS)
    return out


def observation(resp, extra):
    """GET /observe's response -> the dict the model sees: the observation, plus the run's clock and the task text."""
    obs = resp.get("observation") if isinstance(resp.get("observation"), dict) else \
        {k: v for k, v in resp.items() if k not in ENVELOPE}
    obs = dict(obs)
    if resp.get("days_left") is not None:
        obs["days_left_in_run"] = resp["days_left"]
    if resp.get("hands_off_in_days") is not None:
        obs["hands_off_in_days"] = resp["hands_off_in_days"]
    obs.update(extra)
    return obs


def window(messages):
    """System prompt + the last HISTORY messages, never starting with a tool result; older observations become a
    one-line stub and older tool results are trimmed."""
    m = messages[:1] + messages[1:][-HISTORY:]
    while len(m) > 1 and m[1]["role"] == "tool":
        m.pop(1)
    last_user = max((i for i, x in enumerate(m) if x["role"] == "user"), default=-1)
    last_tool = max((i for i, x in enumerate(m) if x["role"] == "tool"), default=-1)
    out = []
    for i, x in enumerate(m):
        c = x.get("content")
        if i and x["role"] == "user" and i != last_user and isinstance(c, str) and c.startswith("OBSERVATION {"):
            x = {**x, "content": "OBSERVATION (older, omitted)"}
        elif x["role"] == "tool" and i != last_tool and isinstance(c, str) and len(c) > TOOL_RESULT_OLD:
            x = {**x, "content": c[:TOOL_RESULT_OLD] + " ...(trimmed)"}
        out.append(x)
    return out


def signature(tool, args):
    return tool + ":" + json.dumps(args, sort_keys=True, separators=(",", ":"))


class Plain:
    def __init__(self, task, game, model, seed=0):
        self.task, self.game, self.model, self.seed = task, game, model, seed
        self.stats = {"turns": 0, "actions": 0, "rejected": 0, "advances": 0, "stall_advances": 0,
                      "churn_refused": 0, "api_errors": 0, "no_tool_call": 0, "context_trims": 0}
        self.stop_reason = None
        self.added = {}       # order id -> (signature, tick) of orders this harness added
        self.cancelled = []   # (tick, signature, order id) of orders this harness cancelled
        self.guard = Overseer(game)
        self.guard_day = None

    def setup(self):
        t = self.game.task()
        self.tools = prepare_tools(t.get("tools") or [])
        self.tool_names = {(x.get("function") or {}).get("name") for x in self.tools}
        self.messages = [{"role": "system", "content": prompt.system_prompt(t.get("manual"), self.tool_names)}]
        info = {**(self.task.task or {}), **(t.get("task") or {})}
        days = info.get("days") or self.task.days
        self.extra = {}
        if info.get("goal"):
            self.extra["goal"] = str(info["goal"]).replace("{days}", str(days))
        if info.get("brief"):
            self.extra["scenario"] = info["brief"]
        log("setup", task=info.get("name"), days=days, credits=self.task.credits,
            system_chars=len(self.messages[0]["content"]))

    def spent(self):
        return self.model.usage.get("cost_usd") or 0.0

    def run(self, max_turns=None):
        self.setup()
        idle = streak = 0
        while max_turns is None or self.stats["turns"] < max_turns:
            resp = self.game.observe()
            if resp.get("game_over"):
                self.stop_reason = "game_over"
                break
            if resp.get("day") != self.guard_day:   # the deterministic layer runs once per game day and costs no credits
                self.guard_day = resp.get("day")
                try:
                    if self.guard.step(resp):
                        resp = self.game.observe()
                except (HandsOff, GameOver) as e:
                    self.stop_reason = type(e).__name__
                    break
            if self.task.credits and self.spent() >= BUDGET_STOP * self.task.credits:
                self.stop_reason = "budget"
                break
            self.stats["turns"] += 1
            obs = observation(resp, self.extra)
            self.messages.append({"role": "user", "content": "OBSERVATION " + json.dumps(
                obs, separators=(",", ":"), ensure_ascii=False)})
            self.messages = window(self.messages)
            try:
                msg = self.chat()
            except BudgetExhausted as e:
                log("budget_exhausted", error=str(e)[:200])
                self.stop_reason = "budget_exhausted"
                break
            except ModelError as e:
                self.stats["api_errors"] += 1
                streak += 1
                log("model_error", error=str(e)[:300], streak=streak)
                self.messages.pop()
                if streak >= MAX_API_STREAK:
                    self.stop_reason = "model_failing"
                    break
                if not self.advance(1, "model_error"):
                    break
                continue
            streak = 0
            calls = msg.get("tool_calls") or []
            if not calls:
                self.stats["no_tool_call"] += 1
                idle += 1
            else:
                self.messages.append({k: msg[k] for k in ("role", "content", "tool_calls") if k in msg})
                try:
                    moved = self.run_call(calls[0])
                except (HandsOff, GameOver) as e:
                    self.stop_reason = type(e).__name__
                    break
                for c in calls[1:]:
                    self.messages.append({"role": "tool", "tool_call_id": c.get("id"), "content": json.dumps(
                        {"ok": False, "error_code": "one_tool_per_turn", "error": "not run: one tool call per turn"})})
                idle = 0 if moved else idle + 1
            if idle >= STALL_AFTER:
                idle = 0
                self.stats["stall_advances"] += 1
                if not self.advance(1, "stall_guard"):
                    break
        log("done", reason=self.stop_reason, stats=self.stats, usage=self.model.usage, spent=round(self.spent(), 4))
        return self.stats

    def chat(self):
        params = {**CHAT, "seed": self.seed}
        try:
            resp = self.model.chat(self.messages, tools=self.tools, **params)
        except ContextTooLong as e:   # over the context window: keep the system prompt and this observation
            if len(self.messages) <= 2:
                raise
            self.messages = [self.messages[0], self.messages[-1]]
            self.stats["context_trims"] += 1
            log("context_trim", error=str(e)[:200])
            resp = self.model.chat(self.messages, tools=self.tools, **params)
        return resp["choices"][0].get("message") or {}

    def run_call(self, call):
        """Run one tool call and append its result. Returns True when game time moved."""
        fn = call.get("function") or {}
        name = fn.get("name")
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = None
        tick = self.tick()
        refused = self.refuse(name, args, tick) if isinstance(args, dict) else None
        if name not in self.tool_names:
            resp = {"ok": False, "error_code": "unknown_tool", "error": f"no tool named {name!r}"}
        elif not isinstance(args, dict):
            resp = {"ok": False, "error_code": "bad_arguments", "error": "arguments must be a JSON object"}
        elif refused:
            resp = refused
            self.stats["churn_refused"] += 1
        else:
            if name == "advance_days":
                try:
                    args = {**args, "days": max(1, min(MAX_DAYS, int(args.get("days") or 1)))}
                except (TypeError, ValueError):
                    args = {**args, "days": 1}
            try:
                resp = self.game.act(name, args)
            except ActionLimit as e:   # K actions used today: say so, and let a day pass
                self.result(call, name, args, {"ok": False, "error_code": "action_limit", "error": str(e)})
                self.advance(1, "action_limit")
                return True
            self.remember(name, args, resp, tick)
        self.result(call, name, args, resp)
        moved = name == "advance_days" and bool(resp.get("ok"))
        self.stats["advances"] += moved
        return moved

    def refuse(self, name, args, tick):
        """The order-churn guard: a local refusal (no API call), or None."""
        if not isinstance(tick, int):
            return None
        if name in ORDER_TOOLS:
            sig = signature(name, args)
            for t, s, oid in reversed(self.cancelled):
                if s == sig and tick - t <= CHURN_DAYS * DAY:
                    return {"ok": False, "error_code": "order_churn", "error": (
                        f"not run: you cancelled an identical order (id {oid}) {(tick - t) / DAY:.1f} days ago; "
                        "adding it again restarts the manager's validation.")}
        if name == "cancel_order":
            sig, t = self.added.get(args.get("order_id"), (None, None))
            if t is not None and tick - t < FRESH_DAYS * DAY:
                return {"ok": False, "error_code": "order_churn", "error": (
                    f"not run: you added order {args.get('order_id')} only {(tick - t) / DAY:.1f} days ago; a new "
                    "order waits for the manager's validation, and cancelling it restarts that wait.")}
        return None

    def remember(self, name, args, resp, tick):
        if not resp.get("ok") or not isinstance(tick, int):
            return
        r = resp.get("result") if isinstance(resp.get("result"), dict) else resp
        if name in ORDER_TOOLS and r.get("order_id", r.get("id")) is not None:
            self.added[r.get("order_id", r.get("id"))] = (signature(name, args), tick)
        elif name == "cancel_order":
            sig, _ = self.added.pop(args.get("order_id"), (None, None))
            if sig is not None:
                self.cancelled = (self.cancelled + [(tick, sig, args.get("order_id"))])[-50:]

    def result(self, call, name, args, resp):
        ok = bool(resp.get("ok"))
        self.stats["actions"] += 1
        self.stats["rejected"] += not ok
        text = json.dumps(resp, separators=(",", ":"), ensure_ascii=False, default=str)[:TOOL_RESULT_MAX]
        self.messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": text})
        log("act", tool=name, args=args, ok=ok, error_code=resp.get("error_code"))

    def advance(self, days, reason):
        """A harness-initiated advance. False when the game is over or the hands-off window has started."""
        try:
            resp = self.game.act("advance_days", {"days": days})
        except (HandsOff, GameOver) as e:
            self.stop_reason = type(e).__name__
            return False
        self.stats["advances"] += bool(resp.get("ok"))
        log("harness_advance", reason=reason, ok=resp.get("ok"))
        if resp.get("game_over"):
            self.stop_reason = "game_over"
            return False
        return True

    def tick(self):
        return (self.game.last or {}).get("tick")


def main():
    task = load_task()
    game = GameClient(task.game_url)
    model = ModelClient(task.model_base_url, task.model_name, task.api_key, prices=task.prices)
    log("start", task=repr(task), model=task.model_name)
    try:
        Plain(task, game, model, seed=int(os.environ.get("DFBENCH_SEED", "0"))).run()
    except GameAPIError as e:   # the game server went away: nothing more to do
        log("game_error", error=str(e)[:300])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
