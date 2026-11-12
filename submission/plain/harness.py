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

HISTORY = 12
TOOL_RESULT_OLD = 300
TOOL_RESULT_MAX = 4000
MAX_DAYS = 14
STALL_AFTER = 4
MAX_API_STREAK = 5
BUDGET_STOP = 0.92
CHURN_DAYS = 3
FRESH_DAYS = 2
ORDER_TOOLS = ("add_order", "add_manager_order")
LAYER_TOOLS = ("civilian_alert", "lock_door", "create_squad", "equip_squad", "squad_order")



LAYER_REFUSAL = {
    "civilian_alert": "it sounds and clears the alert itself; a long alert keeps civilians from drink and food",
    "lock_door": "it locks the entrance hatches while the alert holds every citizen in the Shelter and opens them "
                 "when the alert clears or anyone is outside; a lock it did not make would never be opened",


    "create_squad": "it makes the squad itself at 10+ citizens (sized to the party when invaders are in sight), "
                    "picking members so miners and woodcutters keep their picks and axes",


    "equip_squad": "it gives the squad its uniform once, as soon as the squad stands, and has wooden spears made "
                   "for members without a weapon; a second equip_squad clears the uniform's assignments for good",





    "squad_order": "it orders the squad itself: attack when invaders are in sight and the odds hold, a station to "
                   "arm the soldiers or guard an entrance or a citizen against a wild animal, stand_down when the "
                   "threat is gone; a stand_down of its station sends the soldiers off duty and they drop their weapons",
}






LAYER_AUTOMATIONS = ("autolabor",)
AUTOMATION_REFUSAL = {
    "autolabor": "it keeps autolabor off: enabling it replaces the default work details, and forts that enabled "
                 "it stopped felling trees and ran out of logs",
}
CHAT = {"tool_choice": "required", "temperature": 0, "max_tokens": 4000, "reasoning": {"effort": "low"}}
ENVELOPE = ("day", "tick", "days_left", "game_over", "hands_off_in_days")
DAY = 1200
UNITS_EVERY = 10








ALERT_CAP_DAYS = 10
HOT_STEP_DAYS = 1
HOT_FALLBACK_DAYS = 2
HOT_PASS_S = 7.0
WALL_RESERVE = 0.10
WALL_PACE_FRAC = 0.85

WALL_STEP_DAYS = 7
WALL_PACE_MIN_DAYS = 5








CHUNK_DAYS = 2
RISK_CHUNK_DAYS = 1
CHUNK_WALL_FRAC = 0.6
CHUNK_WALL_STOP = 0.75









WALL_GATEWAY_EVERY_S = 120.0
WALL_GATEWAY_FAILS = 3
MODEL_PACE_MIN_CALLS = 3
MODEL_HOLD_MAX_DAYS = 28










RUNNER_GRACE_S = 3600.0
HARD_SLACK_S = 300.0
MODEL_TRY_S = 330.0
MODEL_RETRY_SLEEP_S = 20.0


def log(kind, **kw):
    print(json.dumps({"t": round(time.time(), 2), "kind": kind, **kw}, default=str), flush=True)


def prepare_tools(tools):
    """The API's tool schemas, with advance_days capped at MAX_DAYS and the layer-owned tools (LAYER_TOOLS) left out:
    the model's calls to them were only ever refused (cx hint runs: civilian_alert 42 calls, 0 run, layer_owned)."""
    out = [t for t in copy.deepcopy(tools or [])
           if (t.get("function") or {}).get("name") not in LAYER_TOOLS]
    for t in out:
        f = t.get("function") or {}
        if f.get("name") == "advance_days":
            days = ((f.get("parameters") or {}).get("properties") or {}).get("days")
            if isinstance(days, dict):
                days["maximum"] = min(days.get("maximum", MAX_DAYS), MAX_DAYS)
        elif f.get("name") == "enable_automation":
            prop = ((f.get("parameters") or {}).get("properties") or {}).get("name")
            if isinstance(prop, dict) and isinstance(prop.get("enum"), list):
                prop["enum"] = [n for n in prop["enum"] if n not in LAYER_AUTOMATIONS]
    return out


def observation(resp, extra):
    """GET /observe's response -> the dict the model sees: the observation, plus the run's clock and the task text."""
    obs = resp.get("observation") if isinstance(resp.get("observation"), dict) else\
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
                      "churn_refused": 0, "api_errors": 0, "no_tool_call": 0, "context_trims": 0,
                      "wall_switches": 0}
        self.stop_reason = None
        self.added = {}
        self.cancelled = []
        self.memory = digest.Memory()
        self.guard = Overseer(game, goal=(task.task or {}).get("goal", ""), days=(task.task or {}).get("days") or task.days)
        self.guard_day = None
        self.units = None
        self.units_day = None
        w = getattr(task, "wall_s", None)
        self.wall_s = w if isinstance(w, (int, float)) and w > 0 else None
        self.t0 = time.monotonic()
        self.model_wait = 0.0
        self.day0 = None
        self.excluded_s = 0.0
        self.gw_read = None
        self.model_days = 0.0
        self.model_mark = None
        self.hold_left = 0.0
        self.model_calls = 0

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

    def excluded(self):
        """cx: the wall seconds the server leaves out of the cap — the gateway's reported throttle
        (GET /status throttle_wait_total_s, read every WALL_GATEWAY_EVERY_S) or the client's own 429 waits, whichever
        is larger; never more than the model wait itself. Never lowered."""
        now = time.monotonic()
        model = getattr(self, "model", None)
        self.excluded_s = getattr(self, "excluded_s", 0.0)
        self.gw_read = getattr(self, "gw_read", None)
        status = getattr(model, "gateway_status", None)
        fails = getattr(self, "gw_fails", 0)
        if callable(status) and fails < WALL_GATEWAY_FAILS\
                and (self.gw_read is None or now - self.gw_read >= WALL_GATEWAY_EVERY_S):
            self.gw_read = now
            try:
                st = status()
            except Exception as e:
                log("gateway_status_error", error=repr(e)[:160])
                st = None
            v = st.get("throttle_wait_total_s") if isinstance(st, dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                self.excluded_s = max(self.excluded_s, float(v))
                self.gw_fails = 0
            else:
                self.gw_fails = fails + 1
        usage = getattr(model, "usage", None)
        v = usage.get("rate_limit_wait_s") if isinstance(usage, dict) else None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            self.excluded_s = max(self.excluded_s, float(v))
        return min(self.excluded_s, getattr(self, "model_wait", 0.0))

    def wall_used(self):
        """The wall seconds the server counts against the cap (rules.py wall_used): elapsed minus the excluded
        throttle. The model's own response time counts."""
        return (time.monotonic() - self.t0) - self.excluded()

    def wall_left(self):
        """Seconds of the task's wall clock left (time.monotonic based), or None when no wall limit is set."""
        if self.wall_s is None:
            return None
        return self.wall_s - self.wall_used()

    def hard_left(self):
        """cx hard clock: real seconds left before the runner's backstop (wall_s + RUNNER_GRACE_S from the start,
        less HARD_SLACK_S), every second counted (no throttle exclusion); None without a wall limit."""
        if self.wall_s is None:
            return None
        return self.wall_s + RUNNER_GRACE_S - HARD_SLACK_S - (time.monotonic() - self.t0)

    def layer_need(self, resp):
        """cx hard clock: real seconds the layer alone needs to play the days left — the measured layer pace
        ((elapsed - model wait) per advanced day) or a 1-day layer pass (hot_pass_s / HOT_PASS_S), whichever is
        larger, times days_left."""
        rest = resp.get("days_left") if isinstance(resp, dict) else None
        if not isinstance(rest, (int, float)) or isinstance(rest, bool) or rest <= 0:
            return 0.0
        per = getattr(self, "hot_pass_s", None) or HOT_PASS_S
        day = resp.get("day")
        if self.day0 is not None and isinstance(day, (int, float)) and day - self.day0 >= WALL_PACE_MIN_DAYS:
            per = max(per, max(0.0, time.monotonic() - self.t0 - self.model_wait) / (day - self.day0))
        return per * rest

    def model_budget(self, resp):
        """cx hard clock: real seconds a model call may take now — the smaller of the runner's real clock
        (hard_left) and the server's counted clock (wall_left), less layer_need — or None without a wall limit.
        A model second counts on the server's clock unless the gateway later reports it as throttle, which is not
        known while the call runs (hint hard LT02-1 on 5c14f02: day 63, wall_left ~1270 s, 27 days to play, throttle
        0; the hard clock alone left ~4400 s, so the client's 5 x 600 s worst case went out as is, the call took the
        rest and the server's wall cap ended the game at day 63, before the LT02 window: W empty, partial 0.15)."""
        hard = self.hard_left()
        if hard is None:
            return None
        wall = self.wall_left()
        left = hard if wall is None else min(hard, wall)
        return left - self.layer_need(resp)

    def hard_low(self, resp):
        """cx hard clock: less than one model attempt fits before the runner's backstop (after the layer's need)."""
        budget = self.model_budget(resp)
        return budget is not None and budget < MODEL_TRY_S + MODEL_RETRY_SLEEP_S

    def wall_low(self, frac=WALL_RESERVE):
        left = self.wall_left()
        return left is not None and left < frac * self.wall_s

    def wall_pace_due(self, resp):
        """The wall-pace guard (ROOT_CAUSES §L: five dev games died at runner_deadline advancing one day a turn
        through a flooded fort). The wall time the rest of the run needs at the layer's own pace —
        (elapsed − model wait) per advanced day × the days left — against ~85% of the wall clock left (wall_left:
        the model's response time counts there, only the reported throttle is excluded). The deterministic layer
        needs no model time, so this decides when even the layer alone can only just finish; the model share
        (model_share) thins the model's turns well before that."""
        if self.wall_s is None or self.day0 is None:
            return False
        left = self.wall_left()
        if left is None or left <= 0:
            return False
        day = resp.get("day")
        if not isinstance(day, (int, float)):
            return False
        done = day - self.day0
        if done < WALL_PACE_MIN_DAYS:
            return False
        left_days = resp.get("days_left")
        if not isinstance(left_days, (int, float)) or left_days <= 0:
            return False
        pace = (time.monotonic() - self.t0 - self.model_wait) / done
        return pace * left_days > WALL_PACE_FRAC * left

    def model_share(self, resp):
        """cx model cadence: the share of the remaining game days the model can still play inside the wall clock —
        1.0 when the whole rest fits at the measured model pace (or nothing is measured yet), 0.0 when even the
        layer's own pace leaves no room. Model pace: the model's seconds (minus the excluded throttle) per game day
        it played; layer pace: wall_pace_due's (elapsed − model wait) per advanced day."""
        left = self.wall_left()
        if left is None or self.day0 is None:
            return 1.0
        day, rest = resp.get("day"), resp.get("days_left")
        if not isinstance(day, (int, float)) or not isinstance(rest, (int, float)) or rest <= 0:
            return 1.0
        done = day - self.day0
        if done < WALL_PACE_MIN_DAYS or self.model_days < WALL_PACE_MIN_DAYS or self.model_calls < MODEL_PACE_MIN_CALLS:
            return 1.0
        model = max(0.0, self.model_wait - self.excluded()) / self.model_days
        layer = max(0.0, time.monotonic() - self.t0 - self.model_wait) / done
        room = WALL_PACE_FRAC * max(0.0, left) - layer * rest
        share = 1.0 if model <= 0 or model * rest <= room else max(0.0, room / (model * rest))


        hard = self.hard_left()
        real = self.model_wait / self.model_days
        if hard is not None and real > 0:
            room_h = WALL_PACE_FRAC * max(0.0, hard) - layer * rest
            if real * rest > room_h:
                share = min(share, max(0.0, room_h / (real * rest)))
        return share

    def model_played(self, resp):
        """cx model cadence: count the days the last model turn moved (from model_mark) and, when the rest of the
        run does not fit the model's pace, set the layer-played days before its next turn: the moved days ×
        (1 − share) / share, at most MODEL_HOLD_MAX_DAYS."""
        mark, self.model_mark = self.model_mark, None
        day = resp.get("day")
        if mark is None or not isinstance(day, (int, float)) or day <= mark:
            return
        moved = day - mark
        self.model_days += moved
        share = self.model_share(resp)
        if share >= 1.0:
            return
        hold = MODEL_HOLD_MAX_DAYS if share <= 0 else min(MODEL_HOLD_MAX_DAYS, moved * (1.0 - share) / share)
        self.hold_left = max(self.hold_left, hold)
        self.stats["model_holds"] = self.stats.get("model_holds", 0) + 1
        left = self.wall_left()
        log("model_hold", day=day, share=round(share, 3), hold_days=round(hold, 1), model_days=self.model_days,
            model_wait_s=round(self.model_wait, 1), excluded_s=round(self.excluded_s, 1),
            left_s=round(left, 1) if left is not None else None, days_left=resp.get("days_left"))

    def layer_pass(self, reason, pace=False, cap=None):
        """One pass of the deterministic layer with no model: observe, the layer (once a game day), one advance of
        layer_days (at most `cap` days). Returns the days advanced, or None when the game is over or the hands-off
        window has begun (stop_reason set)."""
        t0 = time.monotonic()
        resp = self.game.observe()
        if resp.get("game_over"):
            self.stop_reason = "game_over"
            return None
        if self.layer_due(resp):
            self.guard_day = resp.get("day")
            try:
                self.guard.step(resp)
            except (HandsOff, GameOver) as e:
                self.stop_reason = type(e).__name__
                return None
        n = self.layer_days(resp, pace)
        if cap is not None:
            n = max(1, min(n, int(cap)))
        before = resp.get("day")
        if not self.advance(n, reason):
            return None
        if n == HOT_STEP_DAYS:
            dt = time.monotonic() - t0
            prev = getattr(self, "hot_pass_s", None)
            self.hot_pass_s = dt if prev is None else 0.8 * prev + 0.2 * dt
        after = (self.game.last or {}).get("day")
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            return max(0, after - before)
        return n

    def quiet_days(self, resp):
        obs = resp.get("observation") if isinstance(resp.get("observation"), dict) else {}
        left = resp.get("hands_off_in_days")
        if (isinstance(left, int) and left <= 4) or (resp.get("day") or 0) < 14:
            return 1


        if obs.get("dig_designations_pending") and not self.guard.flooded_pending():
            return 1
        return 2

    def layer_days(self, resp, pace=False):
        """Layer-only advance size: 7 game days on the wall-pace guard (the deterministic layer sprints to the
        horizon at near-zero cost), the quiet pacing otherwise; always one day into a close hands-off window."""
        left = resp.get("hands_off_in_days")
        if isinstance(left, int) and left <= 4:
            return 1
        n = WALL_STEP_DAYS if pace else self.quiet_days(resp)
        hot = self.hot(resp)
        if n > HOT_STEP_DAYS and hot:
            if hot == "alert" or self.hot_fits(resp):
                return HOT_STEP_DAYS
            return min(n, HOT_FALLBACK_DAYS)
        return n


    @staticmethod
    def obs_of(resp):
        return resp.get("observation") if isinstance(resp.get("observation"), dict) else {}

    def layer_locks(self, obs):
        """(the alert-locked door ids still locked, the flood hatch id when it is locked) from the layer's state and
        this observation's doors (an observation without the doors section trusts the layer's own record)."""
        doors = obs.get("doors") if isinstance(obs.get("doors"), dict) else None
        rows = {x.get("id"): x for x in (doors or {}).get("list") or [] if isinstance(x, dict)}
        locked = (lambda i: bool(rows.get(i, {}).get("locked"))) if doors is not None else (lambda i: True)
        alert_ids = {i for i in (getattr(self.guard, "alert_locked", None) or ()) if locked(i)}
        flood = getattr(self.guard, "hatch_id", None)
        flood = flood if flood is not None and doors is not None and locked(flood) else None
        return alert_ids, flood

    def open_entrance_hatch(self, obs, flood=None):
        """cx lockable: an unlocked built hatch over an entrance the layer lists (guard.entrances: E site -> (x, y, z));
        any unlocked built hatch when the layer lists none. The flood's hatch is the flood rules' and never counts."""
        doors = obs.get("doors") if isinstance(obs.get("doors"), dict) else {}
        ents = getattr(self.guard, "entrances", None)
        spots = {tuple(p) for p in ents.values() if isinstance(p, (tuple, list)) and len(p) == 3}\
            if isinstance(ents, dict) else set()
        flood_id = getattr(self.guard, "hatch_id", None)
        for x in doors.get("list") or []:
            if not isinstance(x, dict) or x.get("kind") != "hatch" or x.get("locked") or x.get("built") is False:
                continue
            if x.get("id") is not None and x.get("id") in (flood, flood_id):
                continue
            if not spots or (x.get("x"), x.get("y"), x.get("z")) in spots:
                return True
        return False

    def hot(self, resp):
        """Why the layer-only stride shortens: "alert" (the alert is on or a hatch is alert-locked), "lock" (the flood
        hatch is locked), "sign" (a danger sign at the last layer pass), or None."""
        obs = self.obs_of(resp)
        bur = obs.get("burrows") if isinstance(obs.get("burrows"), dict) else {}
        alert_ids, flood = self.layer_locks(obs)
        if bur.get("civilian_alert") or alert_ids:
            return "alert"
        if flood is not None:
            return "lock"
        if getattr(self.guard, "risk", None):
            return "sign"
        return None

    def hot_fits(self, resp):
        """The 1-day layer pace (HOT_PASS_S, or this run's measured 1-day passes) times the days left fits
        WALL_PACE_FRAC of the wall clock left; True without a wall limit."""
        left = self.wall_left()
        if left is None:
            return True
        days = resp.get("days_left")
        if not isinstance(days, (int, float)):
            return True
        per = getattr(self, "hot_pass_s", None) or HOT_PASS_S
        return per * days <= WALL_PACE_FRAC * max(0.0, left)

    def lock_signs(self, resp):
        """cx chunk look: "locked_out" — a hatch the layer locked for the alert is still locked with the alert off or
        a citizen outside the Shelter, or the flood hatch is locked with the alert on and a citizen outside;
        "alert_cap" — the alert has stood longer than ALERT_CAP_DAYS since the layer saw it start; "lockable" — the
        alert is on, every citizen is inside the Shelter and a hatch over a listed entrance stands unlocked, so the
        layer's pass can lock it now (std OP1-4 on 014f7eb: d294 19/19 inside with hatches 6 and 61 open over the
        Shelter's stairs inside a model advance of 3 one-day pieces; d295 a buzzard stood in the Shelter, 16 citizens
        fled to the surface and fought it, the lock came only with the d296 pass — 2 citizens stressed through F)."""
        obs = self.obs_of(resp)
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        bur = obs.get("burrows") if isinstance(obs.get("burrows"), dict) else {}
        alert = bur.get("civilian_alert") is True
        shelter = next((b for b in bur.get("list") or [] if isinstance(b, dict) and b.get("civ_alert_burrow")), {})
        inside = shelter.get("citizens_inside")
        adm = obs.get("administrators") if isinstance(obs.get("administrators"), dict) else {}
        cit = adm.get("citizens") or len(obs.get("dwarves") or [])
        out = num(inside) and num(cit) and inside < cit
        alert_ids, flood = self.layer_locks(obs)
        signs = set()
        if (alert_ids and (not alert or out)) or (flood is not None and alert and out):
            signs.add("locked_out")
        if alert and num(inside) and num(cit) and cit > 0 and inside >= cit and self.open_entrance_hatch(obs, flood):
            signs.add("lockable")
        since = getattr(self.guard, "alert_since", None)
        tick = (obs.get("date") or {}).get("abs_tick") if isinstance(obs.get("date"), dict) else None
        tick = tick if num(tick) else resp.get("tick")
        if alert and num(since) and num(tick) and tick - since > ALERT_CAP_DAYS * DAY:
            signs.add("alert_cap")
        return signs

    def fresh_fights(self, resp, seen):
        """cx chunk look: the marked species in combat reports (a citizen and an animal) this look shows for the first
        time — `seen` holds the report texts already looked at and is updated."""
        obs = self.obs_of(resp)
        events = [str(t) for t in obs.get("recent_events") or []]
        fresh = [t for t in events if t not in seen]
        seen.update(events)
        species = getattr(self.guard, "combat_species", None)
        if not fresh or species is None:
            return set()
        marked = getattr(self.guard, "marked", None) or {}
        return {"fresh_fight:" + n for n in species(obs, fresh) if n in marked}

    def spent(self):
        return self.model.usage.get("cost_usd") or 0.0

    def layer_only(self, reason):
        """No model: run the deterministic layer alone to the horizon (the baseline exited here and left the fort
        unmanaged). The layer runs once per game day; between its passes a day or two passes — seven on the
        wall-pace guard. False when the game is over or the hands-off window has begun."""
        self.stop_reason = reason
        log("layer_only", reason=reason)
        while True:
            if self.layer_pass(reason, reason in ("wall_pace", "hard_clock")) is None:
                return False

    def layer_due(self, resp):
        """The layer runs once per game day — and once more on the same day when a citizen is locked out of the
        Shelter (a migrant tripwire stops an advance inside the day the layer already ran on: hint hard MY1-4 on
        5d8cf68 kept 2 citizens behind a locked hatch for 4 days)."""
        day = resp.get("day")
        if day != self.guard_day:
            return True
        try:
            out = bool({"locked_out", "lockable"} & self.lock_signs(resp))
        except Exception as e:
            log("chunk_error", error=repr(e)[:200])
            out = False
        if out and getattr(self, "relook_day", None) != day:
            self.relook_day = day
            log("layer_relook", day=day, reason="lock")
            return True
        return False

    def run(self, max_turns=None):
        self.setup()
        idle = streak = 0
        while max_turns is None or self.stats["turns"] < max_turns:
            resp = self.game.observe()
            if resp.get("game_over"):
                self.stop_reason = "game_over"
                break
            if self.day0 is None and isinstance(resp.get("day"), (int, float)):
                self.day0 = resp["day"]
            self.model_played(resp)
            if self.layer_due(resp):
                self.guard_day = resp.get("day")
                try:
                    if self.guard.step(resp):
                        resp = self.game.observe()
                except (HandsOff, GameOver) as e:
                    self.stop_reason = type(e).__name__
                    break
            if self.wall_low():
                left = self.wall_left()
                log("wall_guard", phase="reserve", left_s=round(left, 1) if left else left)
                if not self.layer_only("wall"):
                    break
                continue
            if self.wall_pace_due(resp):
                self.stats["wall_switches"] += 1
                left = self.wall_left()
                log("wall_guard", phase="pace", elapsed_s=round(time.monotonic() - self.t0, 1),
                    model_wait_s=round(self.model_wait, 1), left_s=round(left, 1) if left else left)
                if not self.layer_only("wall_pace"):
                    break
                continue
            if self.hard_low(resp):
                self.stats["hard_switches"] = self.stats.get("hard_switches", 0) + 1
                hard = self.hard_left()
                log("wall_guard", phase="hard", hard_left_s=round(hard, 1), need_s=round(self.layer_need(resp), 1),
                    model_wait_s=round(self.model_wait, 1), days_left=resp.get("days_left"))
                if not self.layer_only("hard_clock"):
                    break
                continue
            if self.task.credits and self.spent() >= BUDGET_STOP * self.task.credits:
                if not self.layer_only("budget"):
                    break
                continue
            ho = resp.get("hands_off_in_days")
            if isinstance(ho, int) and ho <= 4:
                self.hold_left = 0.0
            if self.hold_left > 0:
                got = self.layer_pass("model_hold", cap=max(1, round(self.hold_left)))
                if got is None:
                    break
                self.hold_left = max(0.0, self.hold_left - max(1, got))
                continue
            if isinstance(resp.get("day"), (int, float)):
                self.model_mark = resp["day"]
            self.stats["turns"] += 1
            self.last_look = resp
            obs = observation(resp, self.extra)
            self.messages.append({"role": "user", "content": self.user_message(resp, obs)})
            self.messages = window(self.messages)
            try:
                msg = self.chat()
            except BudgetExhausted as e:
                log("budget_exhausted", error=str(e)[:200])
                self.messages.pop()
                if not self.layer_only("budget_exhausted"):
                    break
                continue
            except ModelError as e:
                self.stats["api_errors"] += 1
                streak += 1
                log("model_error", error=str(e)[:300], streak=streak)
                self.messages.pop()
                if streak >= MAX_API_STREAK:
                    if not self.layer_only("model_failing"):
                        break
                    continue
                if not self.advance(1, "model_error"):
                    break
                idle = 0
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
                    self.units_day = day
            status = digest.digest(obs, env, self.memory, units=self.units,
                                   layer={"report": self.guard.report, "owned": self.guard.owned})
            self.units = None
            compact = digest.compact_observation(obs)
            return status + "\n\nOBSERVATION " + json.dumps(compact, separators=(",", ":"), ensure_ascii=False)
        except Exception as e:
            self.stats["digest_errors"] = self.stats.get("digest_errors", 0) + 1
            log("digest_error", error=repr(e)[:300])
            return raw

    def chat(self):
        t0 = time.monotonic()
        self.model_calls += 1
        try:
            params = {**CHAT, "seed": self.seed}
            try:
                resp = self.bounded_chat(params)
            except ContextTooLong as e:
                if len(self.messages) <= 2:
                    raise
                self.messages = [self.messages[0], self.messages[-1]]
                self.stats["context_trims"] += 1
                log("context_trim", error=str(e)[:200])
                resp = self.bounded_chat(params)
            return resp["choices"][0].get("message") or {}
        finally:
            self.model_wait += time.monotonic() - t0

    def bounded_chat(self, params):
        """cx hard clock: one model.chat whose attempts (max_retries + 1) and per-attempt timeout fit model_budget —
        each attempt costs at most its timeout plus the client's retry sleep. The client's own settings come back
        after the call. A client without max_retries/timeout attributes, or no wall limit, is called as is."""
        m = self.model
        budget = self.model_budget(getattr(self, "last_look", None) or self.game.last or {})
        retries, timeout = getattr(m, "max_retries", None), getattr(m, "timeout", None)
        if budget is None or not isinstance(retries, int) or not isinstance(timeout, (int, float)):
            return m.chat(self.messages, tools=self.tools, **params)
        if budget >= (retries + 1) * (timeout + MODEL_RETRY_SLEEP_S):
            return m.chat(self.messages, tools=self.tools, **params)
        tries = max(1, min(retries + 1, int(budget // (MODEL_TRY_S + MODEL_RETRY_SLEEP_S))))
        cut_retries = tries - 1
        cut_timeout = min(timeout, max(MODEL_TRY_S, budget / tries - MODEL_RETRY_SLEEP_S))
        if (cut_retries, cut_timeout) != (retries, timeout):
            self.stats["model_bounds"] = self.stats.get("model_bounds", 0) + 1
            log("model_bound", budget_s=round(budget, 1), max_retries=cut_retries, timeout_s=round(cut_timeout, 1))
        m.max_retries, m.timeout = cut_retries, cut_timeout
        try:
            return m.chat(self.messages, tools=self.tools, **params)
        finally:
            m.max_retries, m.timeout = retries, timeout

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
        if refused and name in LAYER_TOOLS:
            resp = refused
            self.stats["churn_refused"] += 1
        elif not isinstance(name, str) or name not in self.tool_names:
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
                if "stop_on" in args:
                    log("stop_on_dropped", stop_on=args.get("stop_on"))
                    args = {k: v for k, v in args.items() if k != "stop_on"}
                left = (self.game.last or {}).get("hands_off_in_days")
                if isinstance(left, int) and left <= 4:
                    args["days"] = 1
            try:
                resp = self.chunked(args) if name == "advance_days" else self.game.act(name, args)
            except ActionLimit as e:
                self.result(call, name, args, {"ok": False, "error_code": "action_limit", "error": str(e)})
                self.advance(1, "action_limit")
                return True
            self.remember(name, args, resp, tick)
        self.result(call, name, args, resp)
        moved = name == "advance_days" and bool(resp.get("ok"))
        self.stats["advances"] += moved
        return moved

    def wall_ratio(self):
        """The wall-pace projection (wall_pace_due's: layer pace × days left) over the wall clock left, or None
        while it is not measurable (no wall limit, no start day, fewer than WALL_PACE_MIN_DAYS advanced)."""
        resp = self.game.last or {}
        left = self.wall_left()
        day, left_days = resp.get("day"), resp.get("days_left")
        if left is None or left <= 0 or self.day0 is None or not isinstance(day, (int, float))\
                or not isinstance(left_days, (int, float)):
            return None
        done = day - self.day0
        if done < WALL_PACE_MIN_DAYS:
            return None
        return (time.monotonic() - self.t0 - self.model_wait) / done * left_days / left

    def chunk_days(self, signs):
        """The piece size of a chunked advance: RISK_CHUNK_DAYS while a danger sign is on, CHUNK_DAYS otherwise;
        doubled past CHUNK_WALL_FRAC of the wall clock, None (run whole) past CHUNK_WALL_STOP."""
        n = RISK_CHUNK_DAYS if signs else CHUNK_DAYS
        ratio = self.wall_ratio()
        if ratio is not None and ratio > CHUNK_WALL_STOP:
            return None
        if ratio is not None and ratio > CHUNK_WALL_FRAC:
            n *= 2
        return n

    def piece_days(self, signs):
        """chunk_days(), except that the alert (or a lock-out / cap sign) never runs a multi-day advance whole: past
        CHUNK_WALL_STOP it keeps HOT_FALLBACK_DAYS pieces with a look between them."""
        n = self.chunk_days(signs)
        if n is None and set(signs) & {"alert", "locked_out", "alert_cap"}:
            return HOT_FALLBACK_DAYS
        return n

    def shelterless(self, resp):
        """cx same-pass Shelter: the look shows a burrows section with no civilian-alert burrow and the layer has made
        none. Until one stands the chunked advance looks every RISK_CHUNK_DAYS (hint hard OP1-3 on 6c42bb2: day 0 ran
        one 2-day piece; the rhesus macaque troop reached the wagon at d0.77 and beat the expedition leader from d0.86
        with no look until the game's water stop at d1.33 — he died of INFECTION on d78)."""
        bur = self.obs_of(resp).get("burrows")
        if not isinstance(bur, dict) or getattr(self.guard, "shelter_made", False):
            return False
        return not any(isinstance(b, dict) and b.get("civ_alert_burrow") for b in bur.get("list") or [])

    def chunked(self, args):
        """The model's advance_days as pieces with a danger look between them (see CHUNK_DAYS). Returns the last
        piece's response with the totals advanced and a `chunks` note; a piece's own stop (any tripwire), the
        game's end or a hands-off start ends it as before."""
        days = args.get("days") or 1
        base = getattr(self, "last_look", None) or {}
        signs = set(getattr(self.guard, "risk", None) or [])
        try:
            signs |= self.lock_signs(base)
        except Exception as e:
            log("chunk_error", error=repr(e)[:200])
        seen = {str(t) for t in self.obs_of(base).get("recent_events") or []}
        step = self.piece_days(signs)
        if step is not None and self.shelterless(base):
            step = min(step, RISK_CHUNK_DAYS)
        if step is None or step >= days:
            resp = self.game.act("advance_days", args)
            self.water_hook(resp)
            return resp
        done, ticks, pieces, new = 0.0, 0, [], []
        while True:
            n = min(step, days - round(done))
            resp = self.game.act("advance_days", {**args, "days": n})
            res = resp.get("result") if isinstance(resp.get("result"), dict) else {}
            got = res.get("advanced_days")
            done += got if isinstance(got, (int, float)) else n
            ticks += res.get("advanced_ticks") or 0
            pieces.append(n)
            self.water_hook(resp)
            if not resp.get("ok") or res.get("stopped") or res.get("hands_off") or resp.get("game_over")\
                    or round(done) >= days:
                break
            look = self.game.observe()
            if look.get("game_over"):
                break
            left = look.get("hands_off_in_days")
            if isinstance(left, int) and left <= 4:
                break
            try:
                now = set(self.guard.danger_signs(look, query=True))
            except Exception as e:
                log("chunk_error", error=repr(e)[:200])
                now = set()
            try:
                now |= self.lock_signs(look)
                fights = self.fresh_fights(look, seen)
            except Exception as e:
                log("chunk_error", error=repr(e)[:200])
                fights = set()
            new = sorted((now - signs) | fights)
            if new:
                self.stats["chunk_stops"] = self.stats.get("chunk_stops", 0) + 1
                break


            gone = sorted(x for x in signs - now if x.startswith(("near:", "marked:")))
            if gone and "alert" in now and not any(x.startswith(("near:", "marked:")) for x in now):
                self.stats["chunk_clear_stops"] = self.stats.get("chunk_clear_stops", 0) + 1
                new = ["cleared:" + x for x in gone]
                break
            step = self.piece_days(now) or (days - round(done))
            if self.shelterless(look):
                step = min(step, RISK_CHUNK_DAYS)
        if isinstance(res, dict) and (len(pieces) > 1 or new):
            resp = {**resp, "result": {**res, "advanced_days": round(done, 2), "advanced_ticks": ticks}}
            if new:
                resp["result"]["stopped"] = {"reason": "danger_sign", "detail": ", ".join(new)[:200]}
        self.stats["chunk_pieces"] = self.stats.get("chunk_pieces", 0) + len(pieces)
        log("chunked_advance", asked=days, pieces=pieces, advanced=round(done, 2), signs=sorted(signs), new=new)
        return resp

    def water_hook(self, resp):
        res = resp.get("result") if isinstance(resp.get("result"), dict) else {}
        if (res.get("stopped") if isinstance(res.get("stopped"), dict) else {}).get("reason") == "water_rising":
            try:
                self.guard.water_rising_stop()
            except Exception as e:
                log("water_hook_error", error=repr(e)[:160])

    def refuse(self, name, args, tick):
        """The layer's ownership guard and the order-churn guard: a local refusal (no API call), or None."""
        if name in LAYER_TOOLS:
            return {"ok": False, "error_code": "layer_owned", "error": (
                f"not run: {name} is handled by the deterministic layer ({LAYER_REFUSAL.get(name, 'it owns this tool')}).")}
        auto = args.get("name")
        if name == "enable_automation" and isinstance(auto, str) and auto.strip().lower() in LAYER_AUTOMATIONS:
            auto = auto.strip().lower()
            return {"ok": False, "error_code": "layer_owned", "error": (
                f"not run: enable_automation {auto} is refused by the deterministic layer "
                f"({AUTOMATION_REFUSAL.get(auto, 'it keeps this plugin off')}). The other automations still run.")}
        if name in ("dig_room", "dig_stairs"):
            try:
                why = self.guard.dig_refusal(name, args)
            except Exception as e:
                log("dig_refusal_error", error=repr(e)[:200])
                why = None
            if why:
                return {"ok": False, "error_code": "water_risk", "error": f"not run: {why}. Pick a drier site."}
        if name in ("place_furniture", "make_zone", "build_farm", "dig_room"):
            try:
                sr = getattr(self.guard, "shaft_refusal", None)
                why = sr(name, args) if callable(sr) else None
            except Exception as e:
                log("shaft_refusal_error", error=repr(e)[:200])
                why = None
            if why:
                return {"ok": False, "error_code": "shaft_risk", "error": (
                    f"not run: {why}. Animals come down an open shaft; people rooms stay away from its foot.")}
        if name in ("place_furniture", "make_zone", "create_burrow", "dig_stairs"):
            try:
                orf = getattr(self.guard, "open_refusal", None)
                why = orf(name, args) if callable(orf) else None
            except Exception as e:
                log("open_refusal_error", error=repr(e)[:200])
                why = None
            if why:
                code = "site_open" if name != "dig_stairs" else ("beast_near" if "beast" in why else "entrance_hold")
                return {"ok": False, "error_code": code,
                        "error": f"not run: {why}."}
        if name in ("place_furniture", "make_zone", "build_farm"):
            try:
                rr = getattr(self.guard, "room_reserved", None)
                why = rr(name, args) if callable(rr) else None
            except Exception as e:
                log("room_reserved_error", error=repr(e)[:200])
                why = None
            if why:
                return {"ok": False, "error_code": "room_reserved", "error": f"not run: {why}. Pick another site."}
        oid = args.get("order_id")
        if name == "cancel_order" and type(oid) is int and oid in self.guard.owned:
            return {"ok": False, "error_code": "layer_owned", "error": (
                f"not run: order {args.get('order_id')} is a standing order of the deterministic layer; it keeps "
                "drink, food, barrels and furniture coming, inside hands-off windows too.")}
        try:
            hv = getattr(self.guard, "hold_veto", None)
            veto = hv(name, args) if callable(hv) else None
        except Exception as e:
            log("hold_veto_error", error=repr(e)[:160])
            veto = None
        if veto:
            return {"ok": False, "error_code": "layer_hold", "error": veto}
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
        res = resp.get("result") if isinstance(resp.get("result"), dict) else {}
        stopped = res.get("stopped") if isinstance(res.get("stopped"), dict) else {}
        if stopped.get("reason") == "water_rising":
            try:
                self.guard.water_rising_stop()
            except Exception as e:
                log("water_hook_error", error=repr(e)[:160])
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
    except GameAPIError as e:
        log("game_error", error=str(e)[:300])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
