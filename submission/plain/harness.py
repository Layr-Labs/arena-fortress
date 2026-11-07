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

Cut 2 adds, on top of the organiser's plain baseline and cut 1's prompt: a STATUS digest before the observation
(digest.py: supply per dwarf and days left, the manager/office rule, workshops, each order with why it is stuck,
farms, housing, threats, moods, sites, labors from the `units` query, and a NEXT list), a memory of recent failed
and successful actions and advance stops (digest.Memory), and a compacted observation (the furniture list and
workshop job_details are summarised by the digest instead).

Cut 3 adds the autopilot (autopilot.py): before each model turn the harness itself takes the routine, unambiguous
steps (manager, autochop/seedwatch/autofarm, the Carpenters/Still/Kitchen, standing orders for drink, barrels and
meals, bed/table/chair orders, an underground farm) and, before a hands-off window, makes sure brewing keeps going
through the window. The model's NEXT list leaves out what the autopilot covers. When the model can't be called any
more (credits near their end, a failing model) the harness no longer exits: it keeps running the autopilot and
advancing time itself, and exits only when the wall clock would otherwise cut the game short (the server's own
run-out after an exit doesn't count against the wall cap). A model advance that would run into a hands-off window
is cut to stop READY_CLAMP days before it, so the readiness check runs. The model's call cadence is unchanged.

Run: python -m plain   (reads DFBENCH_TASK)
"""
import copy
import json
import os
import sys
import time

from dfbench_client import (ActionLimit, BudgetExhausted, ContextTooLong, GameAPIError, GameClient, GameOver,
                            HandsOff, ModelClient, ModelError, load_task)

from . import autopilot, digest, prompt

HISTORY = 12                # messages kept after the system prompt
TOOL_RESULT_OLD = 300       # chars of an older tool result kept in the window (the latest is whole)
TOOL_RESULT_MAX = 4000      # chars of the latest tool result
MAX_DAYS = 14               # advance_days cap (the API allows 28)
STALL_AFTER = 10            # consecutive actions without an advance before the harness advances 1 day itself
MAX_API_STREAK = 5          # consecutive failed model turns before the harness stops calling the model
BUDGET_STOP = 0.92          # stop calling the model at this fraction of the game's credits
CHURN_DAYS = 3              # order-churn guard: no identical re-add within this many days of a cancel,
FRESH_DAYS = 2              #   and no cancel of an order this harness added under this many days ago
ORDER_TOOLS = ("add_order", "add_manager_order")
CHAT = {"tool_choice": "required", "temperature": 0, "max_tokens": 4000, "reasoning": {"effort": "low"}}
ENVELOPE = ("day", "tick", "days_left", "game_over", "hands_off_in_days")
DAY = 1200                  # ticks per game day
UNITS_EVERY = 10            # game days between `units` queries (labor coverage for the digest)
AUTO_DAYS = 7               # cut 3: days per harness advance once the model is off (autopilot only)
AUTO_DAYS_BUSY = 3          #   ... while digging is pending or a workshop waits to be built
READY_CLAMP = 2             # a model advance stops this many days before a hands-off window (the readiness check)
WALL_RESERVE_S = 150        # exit when less wall time than this is left (the server then runs the rest itself)
WALL_MODEL_S = 240          # no more model calls with less wall time than this left
PRICES = {"input": 0.15, "cached_input": 0.03, "output": 0.50}   # gateway/prices.json, if the task has none


class WallGuard(Exception):
    """No wall time is left for the advance the model asked for: the harness exits and the server runs the rest."""


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
        if i and x["role"] == "user" and i != last_user and isinstance(c, str) and (
                c.startswith("OBSERVATION {") or c.startswith("STATUS")):
            x = {**x, "content": "OBSERVATION (older, omitted)"}
        elif x["role"] == "tool" and i != last_tool and isinstance(c, str) and len(c) > TOOL_RESULT_OLD:
            x = {**x, "content": c[:TOOL_RESULT_OLD] + " ...(trimmed)"}
        out.append(x)
    return out


def signature(tool, args):
    return tool + ":" + json.dumps(args, sort_keys=True, separators=(",", ":"))


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


class Plain:
    def __init__(self, task, game, model, seed=0):
        self.task, self.game, self.model, self.seed = task, game, model, seed
        self.stats = {"turns": 0, "actions": 0, "rejected": 0, "advances": 0, "stall_advances": 0,
                      "churn_refused": 0, "api_errors": 0, "no_tool_call": 0, "context_trims": 0,
                      "model_turns": 0, "auto_actions": 0, "auto_failed": 0, "auto_advances": 0,
                      "advance_clamped": 0}
        self.stop_reason = None
        self.added = {}       # order id -> (signature, tick) of orders this harness added
        self.cancelled = []   # (tick, signature, order id) of orders this harness cancelled
        self.memory = digest.Memory()   # cut 2: failed/recent actions, advance stops, order ages, supply trend
        self.units = None     # the last `units` query result (citizens), for the digest's labor check
        self.units_day = None
        self.autopilot = autopilot.Autopilot()   # cut 3
        self.model_on = True  # cut 3: False once the credits, the wall clock or the model rule out more calls
        self.model_off_reason = None
        self.t0 = None        # wall clock at the first observe (the server's wall cap starts there)
        self.sec_per_day = None   # measured wall seconds per advanced game day
        self.stuck_advances = 0   # autopilot-only advances in a row that moved no time

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
        if not self.model.prices and not (self.task.prices or None):
            self.model.prices = dict(PRICES)   # so the credit stop works even if the gateway reports no cost
        log("setup", task=info.get("name"), days=days, credits=self.task.credits,
            system_chars=len(self.messages[0]["content"]))

    def spent(self):
        return self.model.usage.get("cost_usd") or 0.0

    # --- the loop -------------------------------------------------------------------------------------------
    def run(self, max_turns=None):
        self.setup()
        idle = streak = 0
        while max_turns is None or self.stats["turns"] < max_turns:
            if self.t0 is None:
                self.t0 = time.time()
            resp = self.game.observe()
            if resp.get("game_over"):
                self.stop_reason = "game_over"
                break
            if self.wall_left() is not None and self.wall_left() < WALL_RESERVE_S:
                self.stop_reason = "wall_guard"   # exit: the server runs the rest, outside the wall cap
                break
            self.stats["turns"] += 1
            try:
                if self.autopilot_pass(resp):
                    resp = self.game.observe()
                    if resp.get("game_over"):
                        self.stop_reason = "game_over"
                        break
            except (HandsOff, GameOver) as e:
                self.stop_reason = type(e).__name__
                break
            if self.model_on and self.task.credits and self.spent() >= BUDGET_STOP * self.task.credits:
                self.model_off("budget")
            if self.model_on and self.wall_left() is not None and self.wall_left() < WALL_MODEL_S:
                self.model_off("wall")
            if not self.model_on:
                if not self.auto_advance(resp):
                    break
                continue
            obs = observation(resp, self.extra)
            self.messages.append({"role": "user", "content": self.user_message(resp, obs)})
            self.messages = window(self.messages)
            self.stats["model_turns"] += 1
            try:
                msg = self.chat()
            except BudgetExhausted as e:
                log("budget_exhausted", error=str(e)[:200])
                self.messages.pop()
                self.model_off("budget_exhausted")
                continue
            except ModelError as e:
                self.stats["api_errors"] += 1
                streak += 1
                log("model_error", error=str(e)[:300], streak=streak)
                self.messages.pop()
                if streak >= MAX_API_STREAK:
                    self.model_off("model_failing")
                    continue
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
                except WallGuard:
                    self.stop_reason = "wall_guard"
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
        log("done", reason=self.stop_reason, stats=self.stats, usage=self.model.usage, spent=round(self.spent(), 4),
            model_off=self.model_off_reason, autopilot_gave_up=sorted(self.autopilot.gave_up),
            sec_per_day=self.sec_per_day)
        return self.stats

    def model_off(self, reason):
        """Cut 3: no more model calls; the autopilot and the harness's own advances carry the game on."""
        if self.model_on:
            self.model_on = False
            self.model_off_reason = reason
            log("model_off", reason=reason, spent=round(self.spent(), 4), day=(self.game.last or {}).get("day"))

    # --- cut 3: the autopilot -------------------------------------------------------------------------------
    def autopilot_pass(self, resp):
        """Run the autopilot's steps for this observation. Returns how many actions it took."""
        obs = resp.get("observation") if isinstance(resp.get("observation"), dict) else resp
        env = {k: resp.get(k) for k in ENVELOPE if k in resp}
        steps = self.autopilot.plan(obs, env, self.tool_names)
        done = 0
        for key, tool, args, why in steps:
            tick = self.tick()
            try:
                r = self.game.act(tool, args)
            except ActionLimit:
                break
            done += 1
            self.stats["auto_actions"] += 1
            self.stats["auto_failed"] += not r.get("ok")
            day = (self.game.last or {}).get("day")
            try:
                self.autopilot.record(key, tool, args, r, tick, day)
                self.memory.record_auto(day, tool, args, r)
            except Exception as e:
                log("memory_error", error=repr(e)[:200])
            self.remember(tool, args, r, tick)
            log("auto", key=key, tool=tool, args=args, ok=r.get("ok"), error_code=r.get("error_code"), why=why)
        return done

    def auto_advance(self, resp):
        """The harness's own advance while the model is off. False when the game ended or the harness should exit."""
        h = _num(resp.get("hands_off_in_days"))
        busy = (_num((resp.get("observation") or {}).get("dig_designations_pending")) or 0) > 0 or any(
            isinstance(w, dict) and not w.get("built") for w in (resp.get("observation") or {}).get("workshops") or [])
        days = AUTO_DAYS_BUSY if busy else AUTO_DAYS
        if h is not None and h > 0:
            days = h if h <= READY_CLAMP else min(days, max(1, h - READY_CLAMP))
        self.stats["auto_advances"] += 1
        t = self.tick()
        if not self.advance(days, "autopilot", stop_on=[]):
            return False
        moved = isinstance(t, int) and isinstance(self.tick(), int) and self.tick() > t
        self.stuck_advances = 0 if moved else self.stuck_advances + 1
        if self.stuck_advances >= 3:   # time isn't moving (never seen on the real server): stop, the server runs the rest
            self.stop_reason = "no_progress"
            return False
        return True

    def wall_left(self):
        wall = _num(self.task.wall_s)
        if not wall or self.t0 is None:
            return None
        return wall - (time.time() - self.t0)

    def wall_days(self, days):
        """The most days an advance can run before the wall reserve (None = no limit known)."""
        left, spd = self.wall_left(), self.sec_per_day
        if left is None or not spd:
            return days
        return min(days, int((left - WALL_RESERVE_S) / (1.25 * spd)))

    def act_advance(self, args):
        """advance_days with the wall clock measured (seconds per game day, for wall_days)."""
        t = time.time()
        r = self.game.act("advance_days", args)
        res = r.get("result") if isinstance(r.get("result"), dict) else {}
        ticks = _num(res.get("advanced_ticks"))
        if r.get("ok") and ticks and ticks >= DAY // 2 and not res.get("hands_off"):
            spd = (time.time() - t) / (ticks / DAY)
            self.sec_per_day = spd if self.sec_per_day is None else 0.7 * self.sec_per_day + 0.3 * spd
        return r

    # --- the model's turn -----------------------------------------------------------------------------------
    def user_message(self, resp, obs):
        """Cut 2: the STATUS digest (from the observation, the envelope and the free queries), then the compacted
        observation as JSON. Any failure in the digest falls back to the raw observation alone. Cut 3: the NEXT
        items the autopilot covers are left out, and its hands-off readiness report is added."""
        raw = "OBSERVATION " + json.dumps(obs, separators=(",", ":"), ensure_ascii=False)
        try:
            env = {k: resp.get(k) for k in ENVELOPE if k in resp}
            day = env.get("day")
            if isinstance(day, int) and (self.units_day is None or day - self.units_day >= UNITS_EVERY):
                try:
                    q = self.game.query("units", kind="citizens")
                    self.units = q.get("result", q)
                    self.units_day = day
                except GameAPIError as e:
                    log("query_error", query="units", error=str(e)[:200])
                    self.units_day = day   # don't retry every turn
            line, missing = self.autopilot.readiness(obs, env)
            extra = ([(None, line)] if line else []) + [(k, t) for k, t in missing]
            status = digest.digest(obs, env, self.memory, units=self.units, handled=self.autopilot.handled(),
                                   extra=extra)
            self.units = None   # the digest keeps the labor line; the query runs again in UNITS_EVERY days
            compact = digest.compact_observation(obs)
            return status + "\n\nOBSERVATION " + json.dumps(compact, separators=(",", ":"), ensure_ascii=False)
        except Exception as e:   # never let the digest cost a turn
            self.stats["digest_errors"] = self.stats.get("digest_errors", 0) + 1
            log("digest_error", error=repr(e)[:300])
            return raw

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
        note = None
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
                args, note = self.clamp_advance(args)
                if args is None:   # the wall clock leaves no room for this advance: exit, the server runs the rest
                    raise WallGuard()
            try:
                resp = self.act_advance(args) if name == "advance_days" else self.game.act(name, args)
            except ActionLimit as e:   # K actions used today: say so, and let a day pass
                self.result(call, name, args, {"ok": False, "error_code": "action_limit", "error": str(e)})
                self.advance(1, "action_limit")
                return True
            self.remember(name, args, resp, tick)
            if note:
                resp = {**resp, "harness_note": note}
        self.result(call, name, args, resp)
        moved = name == "advance_days" and bool(resp.get("ok"))
        self.stats["advances"] += moved
        return moved

    def clamp_advance(self, args):
        """Cut 3: (args, note). A model advance that would reach the hands-off window stops READY_CLAMP days before
        it (the autopilot's readiness check runs there), and no advance runs past the wall reserve. args None: no
        wall time is left for any advance."""
        days, note = args["days"], None
        h = _num((self.game.last or {}).get("hands_off_in_days"))
        if h is not None and h > READY_CLAMP and days > h - READY_CLAMP:
            days = int(h - READY_CLAMP)
            note = (f"advance cut to {days} days: the hands-off window starts in {h} days, and the harness stops "
                    f"{READY_CLAMP} days before it to check that the fort will run itself through the window")
        wd = self.wall_days(days)
        if wd < days:
            if wd < 1:
                return None, None
            days, note = wd, f"advance cut to {wd} days: the wall clock is nearly used up"
        if days != args["days"]:
            self.stats["advance_clamped"] += 1
        return {**args, "days": days}, note

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
                    f"not run: order {args.get('order_id')} was added only {(tick - t) / DAY:.1f} days ago; a new "
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
            self.autopilot.on_cancel(args.get("order_id"), tick)

    def result(self, call, name, args, resp):
        ok = bool(resp.get("ok"))
        self.stats["actions"] += 1
        self.stats["rejected"] += not ok
        text = json.dumps(resp, separators=(",", ":"), ensure_ascii=False, default=str)[:TOOL_RESULT_MAX]
        self.messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": text})
        try:
            self.memory.record((self.game.last or {}).get("day"), name, args, resp)
        except Exception as e:
            log("memory_error", error=repr(e)[:200])
        log("act", tool=name, args=args, ok=ok, error_code=resp.get("error_code"))

    def advance(self, days, reason, stop_on=None):
        """A harness-initiated advance. False when the game is over, the hands-off window has started, or the wall
        clock leaves no room for it (the harness then exits and the server runs the rest)."""
        days = self.wall_days(days)
        if days < 1:
            self.stop_reason = "wall_guard"
            return False
        args = {"days": int(days)}
        if stop_on is not None:
            args["stop_on"] = list(stop_on)
        try:
            resp = self.act_advance(args)
        except (HandsOff, GameOver) as e:
            self.stop_reason = type(e).__name__
            return False
        self.stats["advances"] += bool(resp.get("ok"))
        log("harness_advance", reason=reason, days=days, ok=resp.get("ok"), error_code=resp.get("error_code"))
        if resp.get("game_over"):
            self.stop_reason = "game_over"
            return False
        if not resp.get("ok"):   # e.g. a stop_on value this server doesn't take: plain advance instead
            try:
                resp = self.act_advance({"days": int(days)})
            except (HandsOff, GameOver) as e:
                self.stop_reason = type(e).__name__
                return False
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
