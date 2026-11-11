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
workshop job_details are summarised by the digest instead). The loop, the guards and the model call are unchanged.

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

from . import digest, prompt

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
LAYER_TOOLS = ("civilian_alert",)   # the deterministic layer owns these: the model's calls are refused locally
CALM_WORKSHOPS = {      # refused while the layer keeps the fort from fishing and hunting (autolabor is on)
    "Fishery": ("not run: this fortress keeps no Fishery. With one, a dwarf goes back to fishing at the river, where "
                "predators have killed fishers on forts like this one. Food comes from the farms and, in the last "
                "two weeks, from the animals."),
    "Butchers": ("not run: the deterministic layer builds the Butchers itself when it is needed: just before the "
                 "final slaughter, or earlier if food runs out or a mood asks for bones. While one stands a dwarf "
                 "carries the hunting labour, so it is not built sooner.")}
CHAT = {"tool_choice": "required", "temperature": 0, "max_tokens": 4000, "reasoning": {"effort": "low"}}
ENVELOPE = ("day", "tick", "days_left", "game_over", "hands_off_in_days")
DAY = 1200                  # ticks per game day
UNITS_EVERY = 10            # game days between `units` queries (labor coverage for the digest)


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


class Plain:
    def __init__(self, task, game, model, seed=0):
        self.task, self.game, self.model, self.seed = task, game, model, seed
        self.stats = {"turns": 0, "actions": 0, "rejected": 0, "advances": 0, "stall_advances": 0,
                      "churn_refused": 0, "api_errors": 0, "no_tool_call": 0, "context_trims": 0}
        self.stop_reason = None
        self.added = {}       # order id -> (signature, tick) of orders this harness added
        self.cancelled = []   # (tick, signature, order id) of orders this harness cancelled
        self.memory = digest.Memory()   # cut 2: failed/recent actions, advance stops, order ages, supply trend
        self.guard = Overseer(game, goal=(task.task or {}).get("goal", ""), days=(task.task or {}).get("days") or task.days)
        self.guard_day = None
        self.units = None     # the last `units` query result (citizens), for the digest's labor check
        self.units_day = None

    def setup(self):
        t = self.game.task()
        self.tools = prepare_tools(t.get("tools") or [])
        self.tool_names = {(x.get("function") or {}).get("name") for x in self.tools}
        self.messages = [{"role": "system", "content": prompt.system_prompt(t.get("manual"), self.tool_names)}]
        info = {**(self.task.task or {}), **(t.get("task") or {})}
        days = info.get("days") or self.task.days
        try:   # the layer's goal policies read the task's own goal text (its failure leaves them off, not the run)
            self.guard.set_task(info)
        except Exception as e:
            log("guard_set_task_error", error=repr(e)[:200])
        self.extra = {}
        if info.get("goal"):
            self.extra["goal"] = str(info["goal"]).replace("{days}", str(days))
        if info.get("brief"):
            self.extra["scenario"] = info["brief"]
        log("setup", task=info.get("name"), days=days, credits=self.task.credits,
            system_chars=len(self.messages[0]["content"]))

    def quiet_days(self, resp):
        obs = resp.get("observation") if isinstance(resp.get("observation"), dict) else {}
        left = resp.get("hands_off_in_days")
        if (isinstance(left, int) and left <= 4) or (resp.get("day") or 0) < 14 or obs.get("dig_designations_pending"):
            return 1
        try:
            if self.guard.beds_unmet():   # the unmet bed goal keeps the pacing on the layer's schedule
                return 1
        except Exception:
            pass
        if self.open_play() or self.guard_holds():
            return self.step_days()
        return 2

    def spent(self):
        return self.model.usage.get("cost_usd") or 0.0

    def layer_only(self, reason):
        """No model: run the deterministic layer alone to the horizon (the baseline exited here and left the fort
        unmanaged). The layer runs once per game day; between its passes a day or two passes. False when the game is
        over or the hands-off window has begun."""
        self.stop_reason = reason
        log("layer_only", reason=reason)
        while True:
            resp = self.game.observe()
            if resp.get("game_over"):
                self.stop_reason = "game_over"
                return False
            if resp.get("day") != self.guard_day:
                self.guard_day = resp.get("day")
                try:
                    self.guard.step(resp)
                except (HandsOff, GameOver) as e:
                    self.stop_reason = type(e).__name__
                    return False
            if not self.advance(self.quiet_days(resp), reason):
                return False

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
                if not self.layer_only("budget"):   # no model left; the layer still runs
                    break
                continue
            self.stats["turns"] += 1
            obs = observation(resp, self.extra)
            self.messages.append({"role": "user", "content": self.user_message(resp, obs)})
            self.messages = window(self.messages)
            try:
                msg = self.chat()
            except BudgetExhausted as e:
                log("budget_exhausted", error=str(e)[:200])
                self.messages.pop()
                if not self.layer_only("budget_exhausted"):   # the credits are gone; the layer plays on
                    break
                continue
            except ModelError as e:
                self.stats["api_errors"] += 1
                streak += 1
                log("model_error", error=str(e)[:300], streak=streak)
                self.messages.pop()
                if streak >= MAX_API_STREAK:
                    if not self.layer_only("model_failing"):   # the model is unusable; the layer plays on
                        break
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

    def user_message(self, resp, obs):
        """Cut 2: the STATUS digest (from the observation, the envelope and the free queries), then the compacted
        observation as JSON. Any failure in the digest falls back to the raw observation alone."""
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
            layer = {"report": self.guard.report, "owned": self.guard.owned, "calm": self.guard_calm()}
            try:     # the open-play rules' facts: predators in sight, the lockdown and who is shut out, the felling
                layer.update(self.guard.status())
            except Exception as e:
                log("guard_status_error", error=repr(e)[:200])
            status = digest.digest(obs, env, self.memory, units=self.units, layer=layer)
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
        # name must be a string before the set lookup, and only hashable cancel ids reach the cache (peer
        # f577e8a7's failure cases, idea credited: validate before cache access; the API rejects the rest)
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
                    if self.guard.beds_unmet():   # a surrogate goal the layer is still catching up on: advance
                        args["days"] = min(args["days"], 2)   # slowly, so it can place the beds between steps
                except Exception:
                    pass
                left = (self.game.last or {}).get("hands_off_in_days")
                if isinstance(left, int) and left <= 4:   # one day at a time into a window: last chance to act
                    args["days"] = 1
            try:
                resp = self.open_advance(args) if name == "advance_days" and (self.open_play()
                                                                              or self.guard_holds()) \
                    else self.game.act(name, args)
            except ActionLimit as e:   # K actions used today: say so, and let a day pass
                self.result(call, name, args, {"ok": False, "error_code": "action_limit", "error": str(e)})
                self.advance(1, "action_limit")
                return True
            self.remember(name, args, resp, tick)
        self.result(call, name, args, resp)
        moved = name == "advance_days" and bool(resp.get("ok"))
        self.stats["advances"] += moved
        return moved

    def open_play(self):
        try:
            return self.guard.open_play()
        except Exception:
            return False

    def guard_owns_lock(self, args):
        try:
            return self.guard.owns_lock(args)
        except Exception:
            return False

    def guard_felling_waits(self):
        try:
            return isinstance(self.guard.fell, dict)
        except Exception:
            return False

    def guard_seals_stair(self, args):
        try:
            return self.guard.seals_stair(args)
        except Exception:
            return False

    def guard_calm(self):
        """The layer keeps the fort from fishing and hunting, or on an open task has yet to decide whether it does."""
        try:
            return self.guard.calm is True or (self.guard.calm is None and self.guard.open_task())
        except Exception:
            return False

    def guard_holds(self):
        try:
            return self.guard.lock is not None or bool(self.guard.own_locks)
        except Exception:
            return False

    def step_days(self):
        try:
            return 1 if self.guard.step_days() == 1 else 2
        except Exception:
            return 2

    def open_advance(self, args):
        """Open play: however far the model advances, the layer gets a pass every two game days (its slaughter
        schedule is timed in days, and one pass a fortnight would miss it). One model call still decides the advance;
        the layer's passes cost no credits. A tripwire stop ends the advance as it would have. The API measures two
        tripwires against the start of a call (a hostile 25 tiles closer, indoor water half as much again): those
        are checked here against the start of the whole advance, from the observation, and end it the same way with
        a `harness_stop` note (not an API field). The steps' interruptions and ignored tripwires are passed on."""
        total, done, ticks, resp = args["days"], 0, 0, None
        notes, ignored = [], []
        first = self.alarm_state(self.game.observe()) if total > 1 else None   # a free read; no time passes
        while done < total:
            step = min(self.step_days(), total - done)
            resp = self.game.act("advance_days", {**args, "days": step})
            res = resp.get("result") if isinstance(resp.get("result"), dict) else {}
            if isinstance(res.get("stopped"), dict) and isinstance(res["stopped"].get("after_ticks"), int):
                res["stopped"]["after_ticks"] += ticks      # counted from the start of the whole advance
            done += step
            ticks += res.get("advanced_ticks") or 0
            notes += res.get("interruptions") if isinstance(res.get("interruptions"), list) else []
            ignored += res.get("tripwires_ignored") if isinstance(res.get("tripwires_ignored"), list) else []
            if not resp.get("ok") or resp.get("game_over") or res.get("stopped") or done >= total:
                break
            obs = self.game.observe()
            if obs.get("game_over"):
                break
            if obs.get("day") != self.guard_day:
                self.guard_day = obs.get("day")
                self.guard.step(obs)
            why = self.alarm(first, self.alarm_state(obs))
            if why:
                res["harness_stop"] = why
                break
        if isinstance(resp.get("result"), dict):
            if ticks:
                resp["result"]["advanced_ticks"] = ticks
                resp["result"]["advanced_days"] = round(ticks / DAY, 2)
            if notes:
                resp["result"]["interruptions"] = notes
            if ignored:
                resp["result"]["tripwires_ignored"] = ignored
        return resp

    @staticmethod
    def alarm_state(resp):
        """(nearest visible hostile's distance to the wagon or None, indoor water depth units) from an observation."""
        o = resp.get("observation") if isinstance(resp.get("observation"), dict) else {}
        th = o.get("threats") if isinstance(o.get("threats"), dict) else {}
        water = o.get("water_on_fort_levels") if isinstance(o.get("water_on_fort_levels"), dict) else {}
        near = th.get("nearest_hostile_dist_to_wagon") if th.get("visible_hostiles") else None
        return (near if isinstance(near, (int, float)) else None,
                water.get("total_depth") if isinstance(water.get("total_depth"), (int, float)) else 0)

    @staticmethod
    def alarm(first, now):
        if first[0] is not None and now[0] is not None and first[0] - now[0] >= 25:
            return f"a visible hostile is {first[0] - now[0]:.0f} tiles closer to the wagon than when this advance began"
        if now[1] - first[1] >= 50 and now[1] >= 1.5 * first[1]:
            return f"indoor water rose from {first[1]} to {now[1]} depth units during this advance"
        return None

    def refuse(self, name, args, tick):
        """The layer's ownership guard and the order-churn guard: a local refusal (no API call), or None."""
        if name == "slaughter" and self.open_play():
            return {"ok": False, "error_code": "layer_owned", "error": (
                "not run: the deterministic layer schedules slaughter on this task. Food rots in about 17 days here, "
                "so it keeps the animals for the last two weeks and slaughters one earlier only if food runs short.")}
        if name == "lock_door" and self.guard_owns_lock(args):      # true only while a lockdown stands
            return {"ok": False, "error_code": "layer_owned", "error": (
                "not run: the deterministic layer has the stair hatches locked while dangerous wildlife is near and "
                "the civilians are inside. It opens them itself when the wildlife has gone. Other doors are yours: "
                "give their door_id.")}
        if name == "lock_door" and self.guard_seals_stair(args):    # open play, no lockdown standing
            return {"ok": False, "error_code": "layer_owned", "error": (
                "not run: this would lock the hatch on a surface stair. The deterministic layer keeps those hatches: "
                "it locks them itself when hostiles come near, once the civilians are below, and opens them again. "
                "Locked at any other time they cut the dwarves off from the food and drink on the surface. A door of "
                "your own that is not on a surface stair can be locked by its door_id.")}
        if name == "enable_automation" and args.get("name") == "autochop" and self.guard_felling_waits():
            return {"ok": False, "error_code": "layer_owned", "error": (
                "not run: tree felling is waiting. A large predator is in sight near the river, the felling plugin "
                "sends dwarves across the whole map and cannot be turned off again. The deterministic layer enables "
                "it itself when the animal has left, or when drink, food or time runs short.")}
        if name == "build_workshop" and isinstance(args, dict) and args.get("type") in CALM_WORKSHOPS \
                and self.guard_calm():
            return {"ok": False, "error_code": "layer_owned", "error": CALM_WORKSHOPS[args["type"]]}
        if name in LAYER_TOOLS:
            return {"ok": False, "error_code": "layer_owned", "error": (
                f"not run: {name} is handled by the deterministic layer (it sounds and clears the alert itself; a long "
                "alert keeps civilians from drink and food).")}
        oid = args.get("order_id") if isinstance(args, dict) else None
        if name == "cancel_order" and isinstance(oid, int) and oid in self.guard.owned:
            return {"ok": False, "error_code": "layer_owned", "error": (
                f"not run: order {oid} is a standing order of the deterministic layer; it keeps "
                "drink, food, barrels and furniture coming, inside hands-off windows too.")}
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
        try:
            self.memory.record((self.game.last or {}).get("day"), name, args, resp)
        except Exception as e:
            log("memory_error", error=repr(e)[:200])
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
    plain = Plain(task, game, model, seed=int(os.environ.get("DFBENCH_SEED", "0")))
    try:
        plain.run()
    except GameAPIError as e:   # the game server went away: nothing more to do
        log("game_error", error=str(e)[:300])
        return 1
    finally:                    # an exit must not leave the fort locked down: the server plays on unmanaged
        try:
            plain.guard.release()
        except Exception as e:
            log("release_error", error=repr(e)[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
