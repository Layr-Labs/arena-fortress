"""The steward loop.

One cycle (one "turn" of game time):
  1. GET /observe (+ /events since the last cycle)
  2. the playbook (playbook.py) proposes the essential actions for this state; the harness runs them, each with
     its own cooldown and failure memory, within the day's action limit
  3. the model is consulted when it is due (every CONSULT_DAYS game days) or when something happens that the
     playbook does not settle (a mood, hostiles, a death, repeated failures). It gets a short digest (digest.py)
     plus what the playbook did and what failed, and may make up to MODEL_ACTIONS tool calls. It never moves time.
  4. advance_days: short steps while things are being built or threats are about, longer once the fort runs itself;
     paced against the wall clock so a slow game still reaches the horizon.

The playbook alone keeps the fort supplied, housed and managed; the model adds judgement on top. If the model
fails, runs out of credits or is slow, the playbook keeps playing (unlike the baseline, which exits).
"""
import json
import os
import sys
import time

from dfbench_client import (ActionLimit, BudgetExhausted, ContextTooLong, GameAPIError, GameClient, GameOver,
                            HandsOff, ModelClient, ModelError, load_task)

from . import digest, playbook, prompt

DAY = 1200
BUDGET_STOP = 0.90          # stop calling the model at this share of the credits (the playbook keeps going)
CONSULT_DAYS = 6            # routine consult interval, in game days
MODEL_ACTIONS = 4           # tool calls the model may make per consult
MODEL_ROUNDS = 2            # chat rounds per consult (the model sees its first calls' results once)
WALL_RESERVE = 0.10         # keep this share of the wall cap unused
CHAT = {"tool_choice": "auto", "temperature": 0.2, "max_tokens": 3000, "reasoning": {"effort": "low"}}


def log(kind, **kw):
    print(json.dumps({"t": round(time.time(), 2), "kind": kind, **kw}, default=str), flush=True)


class Steward:
    def __init__(self, task, game, model):
        self.task, self.game, self.model = task, game, model
        self.t0 = time.monotonic()
        self.wall = float(task.wall_s or 5400)
        self.stats = {"cycles": 0, "pb_actions": 0, "pb_failed": 0, "model_calls": 0, "model_actions": 0,
                      "model_failed": 0, "advances": 0, "model_errors": 0}
        self.model_off = None          # reason the model is no longer called
        self.next_consult = 0          # game day of the next routine consult
        self.notes = []                # the model's own notes (memory), newest last
        self.journal = []              # what happened: actions and their results, newest last
        self.last_tick = None
        self.stop_reason = None

    # ---- setup ---------------------------------------------------------------------------------------------------
    def setup(self):
        t = self.game.task()
        info = {**(self.task.task or {}), **(t.get("task") or {})}
        self.days = int(info.get("days") or self.task.days or 336)
        ho = info.get("hands_off") or {}
        self.hands_off_day = (self.days - int(ho["days"])) if isinstance(ho, dict) and ho.get("days") else None
        self.goal = str(info.get("goal") or "").replace("{days}", str(self.days))
        self.brief = str(info.get("brief") or "")
        self.name = str(info.get("name") or "")
        tools = t.get("tools") or []
        self.tool_names = {(x.get("function") or {}).get("name") for x in tools}
        self.model_tools = prompt.model_tools(tools)
        self.system = prompt.system_prompt(self.goal, self.brief, self.days, self.hands_off_day)
        self.pb = playbook.Playbook(days=self.days, hands_off_day=self.hands_off_day, name=self.name,
                                    brief=self.brief, goal=self.goal)
        log("setup", task=self.name, days=self.days, hands_off_day=self.hands_off_day, credits=self.task.credits,
            wall=self.wall, system_chars=len(self.system))

    # ---- helpers -------------------------------------------------------------------------------------------------
    def elapsed(self):
        return time.monotonic() - self.t0

    def spent(self):
        return self.model.usage.get("cost_usd") or 0.0

    def remember(self, who, tool, args, resp, day):
        ok = bool(resp.get("ok"))
        r = resp.get("result") if ok else {"error_code": resp.get("error_code"), "error": resp.get("error")}
        self.journal.append({"day": day, "by": who, "tool": tool, "args": args, "ok": ok,
                             "result": json.dumps(r, default=str)[:240]})
        self.journal = self.journal[-60:]

    def act(self, who, tool, args, day):
        """One action through the API. Returns the response dict, or None when the day's actions are used up."""
        try:
            resp = self.game.act(tool, {k: v for k, v in args.items() if not str(k).startswith("_")})
        except ActionLimit:
            return None
        ok = bool(resp.get("ok"))
        self.stats["pb_actions" if who == "playbook" else "model_actions"] += 1
        if not ok:
            self.stats["pb_failed" if who == "playbook" else "model_failed"] += 1
        self.remember(who, tool, args, resp, day)
        log("act", by=who, tool=tool, args=args, ok=ok, code=resp.get("error_code"),
            err=(resp.get("error") or "")[:200] if not ok else None,
            res=None if not ok else json.dumps(resp.get("result"), default=str)[:200])
        return resp

    # ---- the loop ------------------------------------------------------------------------------------------------
    def run(self, resume=False):
        if not resume:
            self.setup()
        events_since = getattr(self, "events_since", 0)
        while True:
            resp = self.game.observe()
            if resp.get("game_over"):
                self.stop_reason = "game_over"
                break
            obs = resp.get("observation") if isinstance(resp.get("observation"), dict) else {}
            day = int(resp.get("day") or 0)
            days_left = resp.get("days_left")
            self.stats["cycles"] += 1
            try:
                ev = self.game.events(since_tick=events_since)
                events = ev.get("events") or []
                events_since = max([events_since] + [e.get("tick") or 0 for e in events])
                self.events_since = events_since
            except GameAPIError:
                events = []
            self.pb.see_events(events)

            # 1. the playbook (a bug in one cycle must not end the game: log it and let time pass)
            self.pb.animals = None
            try:
                if self.pb.wants_animals(obs, day):  # free query, only when the playbook may need livestock
                    q = self.game.query("units", kind="animals", limit=300)
                    r = q.get("result") if isinstance(q, dict) else None
                    units = r.get("units") if isinstance(r, dict) else r
                    self.pb.animals = [a for a in units or [] if isinstance(a, dict)]
            except Exception as e:
                log("query_error", error=repr(e)[:200])
            try:
                planned = self.pb.plan(obs, day)
            except Exception as e:
                import traceback
                log("playbook_error", error=repr(e)[:300], tb=traceback.format_exc()[-1500:])
                planned = []
            log("pb", day=day, n=len(planned), debug=getattr(self.pb, "debug", None))
            for key, tool, args in planned:
                if tool not in self.tool_names:
                    continue
                r = self.act("playbook", tool, args, day)
                if r is None:
                    break
                self.pb.result(key, tool, args, r, day)
                if r.get("ok") and tool in playbook.REOBSERVE:
                    # sites and stocks changed: re-read before the next placement
                    obs = (self.game.observe().get("observation") or obs)

            # 2. the model
            reason = self.consult_reason(obs, day, events)
            if reason and not self.model_off:
                try:
                    self.consult(obs, day, days_left, reason, events)
                except (HandsOff, GameOver) as e:
                    self.stop_reason = type(e).__name__
                    break
                except GameAPIError:
                    raise
                except Exception as e:
                    import traceback
                    log("consult_error", error=repr(e)[:300], tb=traceback.format_exc()[-1500:])

            # 3. time
            try:
                n = self.pb.advance_days(obs, day, days_left)
            except Exception as e:
                log("playbook_error", error=repr(e)[:300])
                n = 2
            n = self.pace(n, day, days_left)
            try:
                a = self.game.act("advance_days", {"days": n})
            except (HandsOff, GameOver) as e:
                self.stop_reason = type(e).__name__
                break
            except ActionLimit:
                continue
            self.stats["advances"] += 1
            res = a.get("result") or {}
            log("advance", day=day, days=n, ok=a.get("ok"), stopped=res.get("stopped"),
                elapsed=round(self.elapsed()), spent=round(self.spent(), 4))
            if res.get("stopped"):
                self.pb.tripwire(res["stopped"])
            if a.get("game_over") or res.get("hands_off") or res.get("end_reason"):
                self.stop_reason = res.get("end_reason") or ("hands_off" if res.get("hands_off") else "game_over")
                break
        log("done", reason=self.stop_reason, stats=self.stats, usage=self.model.usage, spent=round(self.spent(), 4),
            elapsed=round(self.elapsed()), model_off=self.model_off)
        return self.stats

    def pace(self, n, day, days_left):
        """Lengthen advances when the wall clock runs short: the remaining days must fit in the remaining time."""
        if not days_left:
            return max(1, min(n, 28))
        left_s = self.wall * (1 - WALL_RESERVE) - self.elapsed()
        if day > 0 and left_s > 0:
            per_day = self.elapsed() / max(1, day)            # wall seconds per game day so far (all costs)
            need = days_left * per_day
            if need > left_s:                                 # behind: fewer, longer cycles
                n = max(n, int(n * need / left_s) + 1)
        elif left_s <= 0:
            n = 28
        if self.hands_off_day is not None and day < self.hands_off_day:
            n = min(n, max(1, self.hands_off_day - day))       # stop exactly at the window (it then runs itself)
        return max(1, min(n, 28, days_left))

    # ---- the model -----------------------------------------------------------------------------------------------
    def consult_reason(self, obs, day, events):
        if self.hands_off_day is not None and day >= self.hands_off_day:
            return None
        if self.task.credits and self.spent() >= BUDGET_STOP * self.task.credits:
            self.model_off = self.model_off or "budget"
            return None
        if self.elapsed() > self.wall * 0.8:
            return None
        urgent = self.pb.urgent(obs)
        if urgent:
            return urgent
        if day >= self.next_consult:
            return "routine"
        return None

    def consult(self, obs, day, days_left, reason, events):
        self.next_consult = day + CONSULT_DAYS
        report = digest.report(obs, day, days_left, self.days, self.hands_off_day, events, self.journal, self.notes,
                               self.pb.status(), reason)
        messages = [{"role": "system", "content": self.system}, {"role": "user", "content": report}]
        budget = MODEL_ACTIONS
        for rnd in range(MODEL_ROUNDS):
            try:
                resp = self.model.chat(messages, tools=self.model_tools, **CHAT)
            except BudgetExhausted as e:
                self.model_off = "budget_exhausted"
                log("model_off", reason=str(e)[:200])
                return
            except ContextTooLong as e:
                log("model_error", error=str(e)[:200])
                return
            except ModelError as e:
                self.stats["model_errors"] += 1
                log("model_error", error=str(e)[:300])
                if self.stats["model_errors"] >= 12:
                    self.model_off = "model_failing"
                return
            self.stats["model_calls"] += 1
            msg = (resp.get("choices") or [{}])[0].get("message") or {}
            calls = msg.get("tool_calls") or []
            text = (msg.get("content") or "").strip()
            if text:
                self.note(day, text)
            if not calls:
                return
            messages.append({k: msg[k] for k in ("role", "content", "tool_calls") if k in msg})
            for c in calls:
                fn = c.get("function") or {}
                name = fn.get("name")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = None
                if budget <= 0:
                    out = {"ok": False, "error_code": "not_run", "error": "action budget for this consult used"}
                elif name == "note":
                    self.note(day, str((args or {}).get("text") or ""))
                    out = {"ok": True}
                elif name not in self.tool_names or not isinstance(args, dict):
                    out = {"ok": False, "error_code": "bad_call", "error": f"unknown tool or bad arguments: {name}"}
                else:
                    refused = self.pb.veto(name, args, obs)
                    if refused:
                        out = {"ok": False, "error_code": "refused", "error": refused}
                        self.remember("model", name, args, out, day)
                    else:
                        budget -= 1
                        out = self.act("model", name, args, day)
                        if out is None:
                            out = {"ok": False, "error_code": "action_limit", "error": "no actions left today"}
                            budget = 0
                        else:
                            self.pb.result("model:" + name, name, args, out, day)
                messages.append({"role": "tool", "tool_call_id": c.get("id"),
                                 "content": json.dumps(_short(out), default=str)[:1500]})
            if budget <= 0:
                return

    def note(self, day, text):
        text = " ".join(text.split())[:300]
        if text:
            self.notes = (self.notes + [f"d{day}: {text}"])[-8:]


def _short(resp):
    if resp.get("ok"):
        return {"ok": True, "result": resp.get("result")}
    return {k: resp.get(k) for k in ("ok", "error_code", "error") if k in resp}


def main():
    task = load_task()
    game = GameClient(task.game_url)
    model = ModelClient(task.model_base_url, task.model_name, task.api_key, prices=task.prices, max_retries=3)
    log("start", task=repr(task), model=task.model_name)
    st = Steward(task, game, model)
    # a bug must not leave the fort unmanaged: after a crash, re-enter the loop (state kept) up to 20 times
    for attempt in range(20):
        try:
            st.run(resume=attempt > 0)
            return 0
        except (HandsOff, GameOver):
            return 0
        except GameAPIError as e:
            log("game_error", error=str(e)[:300])
            if "game_over" in str(e) or attempt >= 3:
                return 1
            time.sleep(5)
        except Exception as e:
            import traceback
            log("crash", attempt=attempt, error=repr(e)[:300], tb=traceback.format_exc()[-2000:])
            try:
                game.act("advance_days", {"days": 1})
            except Exception:
                pass
    return 1


if __name__ == "__main__":
    sys.exit(main())
