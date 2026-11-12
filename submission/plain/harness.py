"""The plain baseline harness: the model plays the fort from the raw game API, one tool call per turn.

One turn:
  1. GET /observe -> the observation as the API returns it, plus days_left_in_run, hands_off_in_days, goal, scenario
  2. the user message "OBSERVATION {...}"; the history window (system prompt + last HISTORY messages, older
     observations stubbed, older tool results trimmed)
  3. one chat call through the gateway (tool_choice required)
  4. run the first tool call (POST /act); its result goes back to the model as JSON
  5. guards: refuse order churn locally; advance a day after STALL_AFTER actions without one, or when the day's
     actions are used up; stop calling the model near the end of the credits; stop calling the model when the wall
     budget left no longer covers one call (an answer after the cap is worthless, and exiting early lets the
     server run the fort on unmanaged to the horizon instead of ending the game at the cap tick)
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
STALL_AFTER = 4             # consecutive actions without an advance before the harness advances 1 day itself
MAX_API_STREAK = 5          # consecutive failed model turns before the harness exits, unless a safe
                            #   recovery advance exists (gateway melts recover in minutes; see recover_turn)
RECOVER_MAX = 40            # consecutive no-model days the recovery advance may cover before giving up
BUDGET_STOP = 0.92          # stop calling the model at this fraction of the game's credits
WALL_PACE_AFTER = 0.50      # from this fraction of the game's wall cap, pace quiet days with the overseer
WALL_MODEL_EVERY = 5        # one model turn every N quiet overseer-pace days
WALL_CALL_DEFAULT = 60.0    # first-call estimate of a model call's wall cost (seconds)
WALL_CALL_RECENT = 8        # the recent calls whose slowest sets the estimate
WALL_MARGIN = 15.0          # budget held back for the act, the requests and their spread
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
                      "churn_refused": 0, "api_errors": 0, "no_tool_call": 0, "context_trims": 0,
                      "model_skips": 0, "quiet_days": 0, "recover_days": 0}
        self.stop_reason = None
        self.added = {}       # order id -> (signature, tick) of orders this harness added
        self.cancelled = []   # (tick, signature, order id) of orders this harness cancelled
        self.guard = Overseer(game)
        self.guard_day = None
        self.wall_frac = None     # wall_used_s / wall_s from /health, refreshed once per game day
        self.quiet_gap = 0        # overseer-paced days since the model last got a turn
        self.quiet_stalls = 0     # consecutive quiet advances that moved no game day
        self.recover_streak = 0   # consecutive no-model days from a gateway melt's safe recovery advance
        self.wall_s = None        # the server's wall cap in seconds, from /task limits
        self.call_lat = []        # wall seconds of this run's model calls, oldest first

    def setup(self):
        t = self.game.task()
        limits = t.get("limits") or {}
        wall = limits.get("wall_s")
        self.wall_s = float(wall) if isinstance(wall, (int, float)) and wall else None
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

    def refresh_wall_fraction(self):
        """Read the server's clock once per game day: wall_used_s / wall_s from GET /health. None when the
        server gives no wall fields, so pacing falls back to the model loop."""
        try:
            h = self.game.health()
        except (GameAPIError, AttributeError):
            return
        used, cap = h.get("wall_used_s"), h.get("wall_s")
        self.wall_frac = used / cap if isinstance(used, (int, float)) and isinstance(cap, (int, float)) and cap > 0 else None

    def wall_left(self):
        """Seconds of wall budget left, or None when there is nothing to trust.
        wall_s comes from /task's limits; wall_used_s from /health (read-only, free).
        The server's count excludes provider throttling and unmanaged time, so this
        is the budget the cap actually runs on."""
        if self.wall_s is None:
            return None
        try:
            used = self.game.health().get("wall_used_s")
        except Exception:
            return None
        if not isinstance(used, (int, float)):
            return None
        return self.wall_s - float(used)

    def call_estimate(self):
        """One model call's estimated wall cost: the slowest of this run's last
        WALL_CALL_RECENT calls, or WALL_CALL_DEFAULT before the first result."""
        return max(self.call_lat[-WALL_CALL_RECENT:], default=WALL_CALL_DEFAULT)

    def quiet_turn(self):
        """True when this day is quiet and the wall cap makes a model call too expensive: advance instead."""
        if self.wall_frac is None or self.wall_frac < WALL_PACE_AFTER or not self.guard.quiet():
            return False
        if self.quiet_gap >= WALL_MODEL_EVERY:
            return False          # the model gets a look every WALL_MODEL_EVERY quiet days
        self.stats["model_skips"] += 1
        self.stats["quiet_days"] += 1
        days = self.guard.safe_days()
        tick = (self.game.last or {}).get("tick")
        try:
            resp = self.game.act("advance_days", {"days": days, "stop_on": [
                "citizen_died", "hostile_visible", "invasion", "water_rising"]})
        except HandsOff:
            self.stop_reason = "HandsOff"
            return True
        except GameOver:
            self.stop_reason = "game_over"
            return True
        self.stats["advances"] += bool(resp.get("ok"))
        moved = bool(resp.get("ok")) and ((self.game.last or {}).get("tick") or tick) != tick
        log("quiet_advance", days=days, ok=resp.get("ok"), moved=moved,
            stopped=self.guard.stopped_reason(resp) if moved else None)
        if moved:
            self.quiet_gap += 1
            self.quiet_stalls = 0
        else:
            self.quiet_stalls += 1
            if self.quiet_stalls >= 4:
                self.quiet_gap = WALL_MODEL_EVERY   # not moving: let the model look at it
        if resp.get("game_over"):
            self.stop_reason = "game_over"
        return True

    def recover_turn(self):
        """One safe recovery day while the model is down (gateway melts recover in
        minutes; the saved melt abandoned at day 4 with wall 970/3600 to spare).

        The deterministic layer — standing orders plus the guard pass the loop runs
        per game day — carries a quiet fort without the model, so advance one day
        with the quiet pacing's stop_on tripwires instead of giving up. The next
        loop iteration's model call IS the gateway probe: any answer resets the
        streak. Returns False when the game itself ended or the advance broke, so
        the loop falls through to the ordinary give-up path.
        """
        days = min(self.guard.safe_days(), 1)
        try:
            resp = self.game.act("advance_days", {"days": days, "stop_on": [
                "citizen_died", "hostile_visible", "invasion", "water_rising"]})
        except HandsOff:
            self.stop_reason = "HandsOff"
            return False
        except GameOver:
            self.stop_reason = "game_over"
            return False
        self.stats["advances"] += bool(resp.get("ok"))
        self.stats["recover_days"] += 1
        self.recover_streak += 1
        log("recover_advance", days=days, ok=resp.get("ok"),
            stopped=self.guard.stopped_reason(resp))
        if resp.get("game_over"):
            self.stop_reason = "game_over"
            return False
        return True

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
                self.refresh_wall_fraction()
                try:
                    if self.guard.step(resp):
                        resp = self.game.observe()
                except (HandsOff, GameOver) as e:
                    self.stop_reason = type(e).__name__
                    break
            if self.task.credits and self.spent() >= BUDGET_STOP * self.task.credits:
                self.stop_reason = "budget"
                break
            if self.quiet_turn():
                continue
            left = self.wall_left()
            if left is not None and left <= self.call_estimate() + WALL_MARGIN:
                # One more model call would be answered after the wall cap. The
                # watchdog then ends the game at the cap tick with no run-out, while
                # an early exit lets the runner's /finish run the fort on unmanaged
                # to the horizon and score it there. Stop calling and exit now.
                log("wall_budget_exit", wall_left_s=round(left, 1),
                    call_estimate_s=round(self.call_estimate(), 1), margin_s=WALL_MARGIN)
                self.stop_reason = "wall_budget"
                break
            self.stats["turns"] += 1
            self.quiet_gap = 0
            self.quiet_stalls = 0
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
                log("model_error", error=str(e)[:300], streak=streak,
                    recover_days=self.recover_streak)
                self.messages.pop()
                safe = self.guard.quiet()
                if self.recover_streak >= RECOVER_MAX or (streak >= MAX_API_STREAK and not safe):
                    self.stop_reason = "model_failing"
                    break
                if streak >= 3 and safe:
                    # gateway melt: the deterministic layer carries a quiet fort, so creep
                    # forward instead of giving up; the next loop iteration's chat is the
                    # probe and the wall gate at the top of the loop still bounds the cost.
                    if not self.recover_turn():
                        break
                    idle = 0
                    continue
                if not self.advance(1, "model_error"):
                    break
                idle = 0
                continue
            streak = 0
            self.recover_streak = 0
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
        t0 = time.monotonic()
        try:
            resp = self.model.chat(self.messages, tools=self.tools, **params)
        except ContextTooLong as e:   # over the context window: keep the system prompt and this observation
            if len(self.messages) <= 2:
                raise
            self.messages = [self.messages[0], self.messages[-1]]
            self.stats["context_trims"] += 1
            log("context_trim", error=str(e)[:200])
            resp = self.model.chat(self.messages, tools=self.tools, **params)
        finally:
            # what one call really costs on this run, for the wall-budget gate
            self.call_lat.append(time.monotonic() - t0)
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
        if not isinstance(name, str) or name not in self.tool_names:
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
        order_id = args.get("order_id")
        if name == "cancel_order" and type(order_id) is int and order_id in self.guard.brew_orders:
            return {"ok": False, "error_code": "order_churn", "error": (
                f"not run: order {order_id} is the controller's daily brew order and stays in place.")}
        if not isinstance(tick, int):
            return None
        if name in ORDER_TOOLS:
            sig = signature(name, args)
            for t, s, oid in reversed(self.cancelled):
                if s == sig and tick - t <= CHURN_DAYS * DAY:
                    return {"ok": False, "error_code": "order_churn", "error": (
                        f"not run: you cancelled an identical order (id {oid}) {(tick - t) / DAY:.1f} days ago; "
                        "adding it again restarts the manager's validation.")}
        if name == "cancel_order" and not isinstance(args.get("order_id"), (list, dict)):
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
