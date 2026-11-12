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
STALL_AFTER = 4             # consecutive actions without an advance before the harness advances 1 day itself
MAX_API_STREAK = 5          # consecutive failed model turns before the harness exits
BUDGET_STOP = 0.92          # stop calling the model at this fraction of the game's credits
CHURN_DAYS = 3              # order-churn guard: no identical re-add within this many days of a cancel,
FRESH_DAYS = 2              #   and no cancel of an order this harness added under this many days ago
ORDER_TOOLS = ("add_order", "add_manager_order")
LAYER_TOOLS = ("civilian_alert", "lock_door", "create_squad", "equip_squad", "squad_order")   # the deterministic layer owns these: the model's calls are refused
# locally. lock_door: with no door_id it locks every door and hatch of the fort (act.lua lock_door; the model's
# {"locked": false} answered doors [29, 35] in hint hard LT01-1 on 9a8a399), and a lock the layer did not make is
# never claimed or opened by entrance_hatches() — a model lock would shut the dwarves in or out for good.
LAYER_REFUSAL = {
    "civilian_alert": "it sounds and clears the alert itself; a long alert keeps civilians from drink and food",
    "lock_door": "it locks the entrance hatches while the alert holds every citizen in the Shelter and opens them "
                 "when the alert clears or anyone is outside; a lock it did not make would never be opened",
    # cx squad pick (owner 2026-11-10): the layer makes the one squad by dwarf_ids, keeping miners and woodcutters
    # (and their picks and axes) out of it; a model squad by size takes them (create_squad ranks mining as combat)
    "create_squad": "it makes the squad itself at 10+ citizens (sized to the party when invaders are in sight), "
                    "picking members so miners and woodcutters keep their picks and axes",
    # cx equip once: a second equip_squad clears the members' weapon assignments for good (16 hint runs: assigned
    # 2-4 before the second call, 0 after it to the end)
    "equip_squad": "it gives the squad its uniform once, as soon as the squad stands, and has wooden spears made "
                   "for members without a weapon; a second equip_squad clears the uniform's assignments for good",
    # cx squad hold (owner 2026-11-11): the 92 model squad_order calls of the hint runs (25 runs) were stand_downs of
    # the layer's own stations (29: 24 within 0-3 days of a guard_muster, 3 mark_rescue, 2 mark_station — the
    # soldiers left duty and dropped their weapons, armed 4 -> 0), no-op stand_downs (43), stations on a kea and their
    # stand_downs (10 + 8; mark_guard's stations cover a kea) and attacks with no hostile in sight (2, no_hostiles).
    # No call attacked a visible hostile; defend()'s fight_odds owns the attack.
    "squad_order": "it orders the squad itself: attack when invaders are in sight and the odds hold, a station to "
                   "arm the soldiers or guard an entrance or a citizen against a wild animal, stand_down when the "
                   "threat is gone; a stand_down of its station sends the soldiers off duty and they drop their weapons",
}
# cx autolabor (owner 2026-11-11, A/B test): enable_automation {"name": "autolabor"} is refused locally, the other
# automations stay the model's. Hint OP1 runs played to day 336: the 4 where the model enabled autolabor by day 107
# (80e9f9d OP1-1 d12, e538c50 hard OP1-0 d25, e60d4ce OP1-3 d101, f7f4716b OP1-1 d107) gained no log after day
# 121-156 with autochop on and ended at 24-79 logs; the 13 without it gained 148-348 logs over days 200-336 and ended
# at 237-335 (same seeds: OP1-1 68bd4c7/a7b2833/b595466/full2 306-320). DFHack's autolabor is not updated for v50
# and replaces the default work details on enable (automation/commands.py).
LAYER_AUTOMATIONS = ("autolabor",)
AUTOMATION_REFUSAL = {
    "autolabor": "it keeps autolabor off: enabling it replaces the default work details, and forts that enabled "
                 "it stopped felling trees and ran out of logs",
}
CHAT = {"tool_choice": "required", "temperature": 0, "max_tokens": 4000, "reasoning": {"effort": "low"}}
ENVELOPE = ("day", "tick", "days_left", "game_over", "hands_off_in_days")
DAY = 1200                  # ticks per game day
UNITS_EVERY = 10            # game days between `units` queries (labor coverage for the digest)
# cx alert cadence (owner 2026-11-10, zero deaths): the layer's alert decisions (the 10-day cap, the lift, the
# unlock when anyone is outside) run only on a layer pass. On the wall-pace guard a pass came every 7 days with no
# look between (hint hard MY1-1 on 6adf843: alert_lock d163, next pass d170; the stale-alert lock of d155-162 lasted
# exactly one stride and a citizen died of thirst on d163). While the alert is on, a hatch is locked by the layer
# (alert or flood) or a danger sign is on, the layer-only stride is HOT_STEP_DAYS; a flood lock or a sign alone
# (they can last the whole game) takes it only while the 1-day pace fits the wall clock (else HOT_FALLBACK_DAYS).
# Measured on the hint runs (api latency_ms): advance 1 d 2.7 s median, 2 d 4.8 s, 7 d 14.8 s; observe 0.46 s;
# a layer-only pass (observe + layer + advance) 6.2-7.6 s median at 1-2 days and 18.3 s at 7 days.
ALERT_CAP_DAYS = 10         # defend()'s cap (too_long): the alert_cap sign of the chunk look
HOT_STEP_DAYS = 1
HOT_FALLBACK_DAYS = 2
HOT_PASS_S = 7.0            # wall seconds of a 1-day layer-only pass (measured median 6.2-7.6 s), until measured
WALL_RESERVE = 0.10         # hand the run to the layer when less than this fraction of the wall clock is left
WALL_PACE_FRAC = 0.85       # wall-pace guard (ROOT_CAUSES §L): switch to layer-only when the wall time the rest of
                            #   the run needs at the pace measured so far crosses this fraction of the clock left
WALL_STEP_DAYS = 7          # the layer-only advance once the wall-pace guard has switched (big decisive strides)
WALL_PACE_MIN_DAYS = 5      # game days measured before the pace estimate is trusted (a shorter span is noise)
# cx chunked advance (owner 2026-11-10, zero deaths): the game's tripwires stop an advance only for units DF flags
# isDanger, and no tool can set that flag; the gray langur troop (hostile False) killed a citizen inside a 167->173
# model advance, the carnotaurus inside a 77->80 one. The model's advance_days N now runs as CHUNK_DAYS-day pieces
# (RISK_CHUNK_DAYS while a danger sign is already on), with a look between pieces (observe + the layer's danger check,
# its units query at most once a game day): a new sign stops the advance there and the loop's next pass runs the
# layer (alert, station) before the model's next turn; no sign, and the pieces go on to N. No extra model call
# unless a sign stops it early. Measured API latency (cx records, 513 advances): 4.3 s + 1.8 s per day per call,
# observe 0.47 s, a units query 0.1 s.
CHUNK_DAYS = 2
RISK_CHUNK_DAYS = 1
CHUNK_WALL_FRAC = 0.6       # wall guard: the pace projection (wall_pace_due's) over this share of the clock left
CHUNK_WALL_STOP = 0.75      #   doubles the pieces, over this one runs the advance whole (the pace guard is at 0.85)
# cx model cadence (hint OP1-2, owner standard: every fort plays its 336 days): the server's wall clock counts the
# model's own response time — only the throttling the gateway reports (429/5xx waits, /status
# throttle_wait_total_s) is excluded (gameapi/server/rules.py wall_used). On the hint OP1-2 runs the game advanced
# 2.5 s a day all year while the model answered in 65-92 s a call (local GLM relay, ~1.2 calls a game day): 95% of the
# wall went to the model, day 88 at 2 h 22 min (cxc44c96b hard), day 214 at the cap (full2 std attempt 0), and the
# old pace guard, which subtracted every model second, never fired. The model share: the measured model seconds per
# game day it plays (minus the reported throttle) against the clock the layer's own pace leaves; when the rest of the
# run does not fit, the model plays only that share of the remaining days and the layer plays the days between (the
# quiet/hot cadence, a layer pass once a game day), set after each model-played stretch.
WALL_GATEWAY_EVERY_S = 120.0   # seconds between the gateway /status reads (its throttle_wait_total_s)
WALL_GATEWAY_FAILS = 3         # consecutive reads without the throttle field before the reads stop (count it all)
MODEL_PACE_MIN_CALLS = 3       # model calls measured before the model share is trusted
MODEL_HOLD_MAX_DAYS = 28       # layer-played days after one model-played stretch, at most
# cx hard clock (hint hard LT02-2, cxba93eee x2 and cxe33d381: three runs killed at runner_deadline, no score). The
# runner's backstop is real time: deadline = wall_s + finish_grace_s (3600) from the harness start
# (runner/dfbenchlib/game.py), and it stops the harness whatever the server's counted clock says. The gateway's
# excluded provider time is not excluded there. On LT02-2 the GLM relay timed out calls (HTTP 502 "glm upstream:
# TimeoutError" after ~306 s each; 13-15 per run) and the client retried each 4 times: one turn at day 60 took
# 1533 s (5 x 306 s) and raised, the next at day 62 hung 1700 s into the deadline. Throttle 4993-5295 s > the 3600 s
# grace, so the server's clock showed 3115 s used of 4500 (left_s 1728 at day 61) while 1695 real seconds were left.
# The hard clock: wall_s + RUNNER_GRACE_S - HARD_SLACK_S real seconds from t0, every model second counted. A model
# call may only spend what is left after the layer's own pace to the horizon (the attempts and the per-attempt
# timeout are cut to fit); when less than one attempt fits, the layer plays the rest alone.
RUNNER_GRACE_S = 3600.0        # the runner's finish_grace_s default (its hard backstop past wall_s)
HARD_SLACK_S = 300.0           # the runner's clock starts before t0 (compose up), and its /finish and stop take time
MODEL_TRY_S = 330.0            # one model attempt at most: the relay's hung-call 502 came after ~306 s (LT02-2 runs)
MODEL_RETRY_SLEEP_S = 20.0     # the client's longest sleep between attempts (dfbench_client.model: min(2 s x n, 20))


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
        elif f.get("name") == "enable_automation":   # cx autolabor: the layer-owned names leave the choices
            prop = ((f.get("parameters") or {}).get("properties") or {}).get("name")
            if isinstance(prop, dict) and isinstance(prop.get("enum"), list):
                prop["enum"] = [n for n in prop["enum"] if n not in LAYER_AUTOMATIONS]
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
                      "churn_refused": 0, "api_errors": 0, "no_tool_call": 0, "context_trims": 0,
                      "wall_switches": 0}
        self.stop_reason = None
        self.added = {}       # order id -> (signature, tick) of orders this harness added
        self.cancelled = []   # (tick, signature, order id) of orders this harness cancelled
        self.memory = digest.Memory()   # cut 2: failed/recent actions, advance stops, order ages, supply trend
        self.guard = Overseer(game, goal=(task.task or {}).get("goal", ""), days=(task.task or {}).get("days") or task.days)
        self.guard_day = None
        self.units = None     # the last `units` query result (citizens), for the digest's labor check
        self.units_day = None
        w = getattr(task, "wall_s", None)   # DFBENCH_TASK limits.wall_s (seconds); absent in some stubs
        self.wall_s = w if isinstance(w, (int, float)) and w > 0 else None
        self.t0 = time.monotonic()   # wall-clock guard: elapsed real time since the run was built
        self.model_wait = 0.0        # seconds spent inside model.chat (the pace projection subtracts the throttle)
        self.day0 = None             # the first game day seen: the pace's days-advanced denominator
        self.excluded_s = 0.0        # cx: the wall time the server does not count (the gateway's reported throttle)
        self.gw_read = None          # monotonic time of the last gateway /status read
        self.model_days = 0.0        # cx model cadence: game days advanced while the model played
        self.model_mark = None       # the day a model turn started on (the model-played days are counted from it)
        self.hold_left = 0.0         # layer-played days left before the model's next turn
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
        if callable(status) and fails < WALL_GATEWAY_FAILS \
                and (self.gw_read is None or now - self.gw_read >= WALL_GATEWAY_EVERY_S):
            self.gw_read = now
            try:
                st = status()
            except Exception as e:   # noqa: BLE001  a lost read keeps the last value
                log("gateway_status_error", error=repr(e)[:160])
                st = None
            v = st.get("throttle_wait_total_s") if isinstance(st, dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                self.excluded_s = max(self.excluded_s, float(v))
                self.gw_fails = 0
            else:   # no /status (or no throttle field): stop asking after a few misses (each may wait its timeout)
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
        # cx hard clock: the same share on the runner's real clock, every model second counted (the throttle the
        # server leaves out still runs the backstop down); the smaller share holds
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
        if n == HOT_STEP_DAYS:   # cx: this run's own 1-day pass cost, for hot_fits()
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
        # flood-caused pending digs never clear (the measured collapse sat at pending>0 on 67/67 and 76/76
        # observed days, ROOT_CAUSES §L): they must not pin the pace to one day a pass
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

    # ---- cx alert cadence: the layer's own state, read only (Overseer.alert_locked / hatch_id / alert_since)
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
        spots = {tuple(p) for p in ents.values() if isinstance(p, (tuple, list)) and len(p) == 3} \
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
        except Exception as e:   # noqa: BLE001
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
            self.model_played(resp)   # cx model cadence: the days the last model turn moved, and the hold after it
            if self.layer_due(resp):   # the deterministic layer runs once per game day and costs no credits
                self.guard_day = resp.get("day")
                try:
                    if self.guard.step(resp):
                        resp = self.game.observe()
                except (HandsOff, GameOver) as e:
                    self.stop_reason = type(e).__name__
                    break
            if self.wall_low():   # the wall clock is nearly up: no more model calls, the layer plays it out
                left = self.wall_left()
                log("wall_guard", phase="reserve", left_s=round(left, 1) if left else left)
                if not self.layer_only("wall"):
                    break
                continue
            if self.wall_pace_due(resp):   # the projected pace outruns the remaining wall clock (ROOT_CAUSES §L)
                self.stats["wall_switches"] += 1
                left = self.wall_left()
                log("wall_guard", phase="pace", elapsed_s=round(time.monotonic() - self.t0, 1),
                    model_wait_s=round(self.model_wait, 1), left_s=round(left, 1) if left else left)
                if not self.layer_only("wall_pace"):
                    break
                continue
            if self.hard_low(resp):   # cx hard clock: not one model attempt fits before the runner's backstop
                self.stats["hard_switches"] = self.stats.get("hard_switches", 0) + 1
                hard = self.hard_left()
                log("wall_guard", phase="hard", hard_left_s=round(hard, 1), need_s=round(self.layer_need(resp), 1),
                    model_wait_s=round(self.model_wait, 1), days_left=resp.get("days_left"))
                if not self.layer_only("hard_clock"):
                    break
                continue
            if self.task.credits and self.spent() >= BUDGET_STOP * self.task.credits:
                if not self.layer_only("budget"):   # no model left; the layer still runs
                    break
                continue
            ho = resp.get("hands_off_in_days")
            if isinstance(ho, int) and ho <= 4:
                self.hold_left = 0.0   # the model's last turns before a hands-off window are never held
            if self.hold_left > 0:   # cx model cadence: the layer plays these days, the model's turn comes after
                got = self.layer_pass("model_hold", cap=max(1, round(self.hold_left)))
                if got is None:
                    break
                self.hold_left = max(0.0, self.hold_left - max(1, got))
                continue
            if isinstance(resp.get("day"), (int, float)):
                self.model_mark = resp["day"]
            self.stats["turns"] += 1
            self.last_look = resp   # cx: the chunk look's baseline (lock signs, combat reports already seen)
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
                    self.units_day = day   # don't retry every turn
            status = digest.digest(obs, env, self.memory, units=self.units,
                                   layer={"report": self.guard.report, "owned": self.guard.owned})
            self.units = None   # the digest keeps the labor line; the query runs again in UNITS_EVERY days
            compact = digest.compact_observation(obs)
            return status + "\n\nOBSERVATION " + json.dumps(compact, separators=(",", ":"), ensure_ascii=False)
        except Exception as e:   # never let the digest cost a turn
            self.stats["digest_errors"] = self.stats.get("digest_errors", 0) + 1
            log("digest_error", error=repr(e)[:300])
            return raw

    def chat(self):
        t0 = time.monotonic()   # the model response time: the layer pace leaves it out, the model share reads it
        self.model_calls += 1
        try:
            params = {**CHAT, "seed": self.seed}
            try:
                resp = self.bounded_chat(params)
            except ContextTooLong as e:   # over the context window: keep the system prompt and this observation
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
        if budget >= (retries + 1) * (timeout + MODEL_RETRY_SLEEP_S):   # the client's worst case fits: as is
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
            resp = refused   # cx: no longer offered, still answered with the layer's reason (not unknown_tool)
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
                if "stop_on" in args:   # cx: every tripwire stops the advance (the default); a model's narrower list
                    log("stop_on_dropped", stop_on=args.get("stop_on"))   # let a flood drown two (df2 MY1-5)
                    args = {k: v for k, v in args.items() if k != "stop_on"}
                left = (self.game.last or {}).get("hands_off_in_days")
                if isinstance(left, int) and left <= 4:   # one day at a time into a window: last chance to act
                    args["days"] = 1
            try:
                resp = self.chunked(args) if name == "advance_days" else self.game.act(name, args)
            except ActionLimit as e:   # K actions used today: say so, and let a day pass
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
        if left is None or left <= 0 or self.day0 is None or not isinstance(day, (int, float)) \
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
        base = getattr(self, "last_look", None) or {}   # the observation this turn was decided on
        signs = set(getattr(self.guard, "risk", None) or [])   # the signs at the layer's pass on this day
        try:   # cx: the lock-out / cap signs that already stand are not new (the layer has seen them)
            signs |= self.lock_signs(base)
        except Exception as e:   # noqa: BLE001
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
            if not resp.get("ok") or res.get("stopped") or res.get("hands_off") or resp.get("game_over") \
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
            except Exception as e:   # noqa: BLE001
                log("chunk_error", error=repr(e)[:200])
                now = set()
            try:   # cx: a citizen locked out / the alert past its cap / a fresh fight with a marked animal
                now |= self.lock_signs(look)   # (hint hard MY1-4 on 5d8cf68: d94 23/25 inside behind locked hatch
                fights = self.fresh_fights(look, seen)   # 67 while the kea beat the child; no stop until d96)
            except Exception as e:   # noqa: BLE001
                log("chunk_error", error=repr(e)[:200])
                fights = set()
            new = sorted((now - signs) | fights)
            if new:
                self.stats["chunk_stops"] = self.stats.get("chunk_stops", 0) + 1
                break
            # cx: an alert held for an animal that has now left: stop so the layer can lift it at once (the citizens
            # would otherwise stay sheltered to the end of the model's N days)
            gone = sorted(x for x in signs - now if x.startswith(("near:", "marked:")))
            if gone and "alert" in now and not any(x.startswith(("near:", "marked:")) for x in now):
                self.stats["chunk_clear_stops"] = self.stats.get("chunk_clear_stops", 0) + 1
                new = ["cleared:" + x for x in gone]
                break
            step = self.piece_days(now) or (days - round(done))
            if self.shelterless(look):
                step = min(step, RISK_CHUNK_DAYS)
        if isinstance(res, dict) and (len(pieces) > 1 or new):   # cx: a stop after the first piece says so too
            resp = {**resp, "result": {**res, "advanced_days": round(done, 2), "advanced_ticks": ticks}}
            if new:
                resp["result"]["stopped"] = {"reason": "danger_sign", "detail": ", ".join(new)[:200]}
        self.stats["chunk_pieces"] = self.stats.get("chunk_pieces", 0) + len(pieces)
        log("chunked_advance", asked=days, pieces=pieces, advanced=round(done, 2), signs=sorted(signs), new=new)
        return resp

    def water_hook(self, resp):
        res = resp.get("result") if isinstance(resp.get("result"), dict) else {}
        if (res.get("stopped") if isinstance(res.get("stopped"), dict) else {}).get("reason") == "water_rising":
            try:   # B-2: a water_rising stop halts the dig fronts and arms the breach check (the model's own too)
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
        if name in ("dig_room", "dig_stairs"):   # cx: the layer's water rules apply to the model's digs too
            try:
                why = self.guard.dig_refusal(name, args)
            except Exception as e:   # noqa: BLE001  never let the check cost the model's turn
                log("dig_refusal_error", error=repr(e)[:200])
                why = None
            if why:
                return {"ok": False, "error_code": "water_risk", "error": f"not run: {why}. Pick a drier site."}
        if name in ("place_furniture", "make_zone", "build_farm", "dig_room"):   # cx shaft people
            try:
                sr = getattr(self.guard, "shaft_refusal", None)
                why = sr(name, args) if callable(sr) else None
            except Exception as e:   # noqa: BLE001  never let the check cost the model's turn
                log("shaft_refusal_error", error=repr(e)[:200])
                why = None
            if why:
                return {"ok": False, "error_code": "shaft_risk", "error": (
                    f"not run: {why}. Animals come down an open shaft; people rooms stay away from its foot.")}
        if name in ("place_furniture", "make_zone", "create_burrow", "dig_stairs"):   # cx closed fallback
            try:
                orf = getattr(self.guard, "open_refusal", None)
                why = orf(name, args) if callable(orf) else None
            except Exception as e:   # noqa: BLE001  never let the check cost the model's turn
                log("open_refusal_error", error=repr(e)[:200])
                why = None
            if why:
                code = "site_open" if name != "dig_stairs" else ("beast_near" if "beast" in why else "entrance_hold")
                return {"ok": False, "error_code": code,
                        "error": f"not run: {why}."}
        if name in ("place_furniture", "make_zone", "build_farm"):   # cx room claim
            try:
                rr = getattr(self.guard, "room_reserved", None)
                why = rr(name, args) if callable(rr) else None
            except Exception as e:   # noqa: BLE001  never let the check cost the model's turn
                log("room_reserved_error", error=repr(e)[:200])
                why = None
            if why:
                return {"ok": False, "error_code": "room_reserved", "error": f"not run: {why}. Pick another site."}
        oid = args.get("order_id")
        if name == "cancel_order" and type(oid) is int and oid in self.guard.owned:
            return {"ok": False, "error_code": "layer_owned", "error": (
                f"not run: order {args.get('order_id')} is a standing order of the deterministic layer; it keeps "
                "drink, food, barrels and furniture coming, inside hands-off windows too.")}
        try:   # cx hold veto: a brew order that would take the harvest-closed hold's plants before F
            hv = getattr(self.guard, "hold_veto", None)
            veto = hv(name, args) if callable(hv) else None
        except Exception as e:   # noqa: BLE001 — a layer surprise never blocks the model's call
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
            try:   # B-2: a water_rising stop halts the dig fronts and arms the breach check
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
    except GameAPIError as e:   # the game server went away: nothing more to do
        log("game_error", error=str(e)[:300])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
