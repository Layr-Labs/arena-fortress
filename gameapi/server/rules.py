"""One game: task lifecycle, the rules of docs/GAME-API.md §4, and the end of the game.

Game is backend- and facts-agnostic (gameapi/server/backend.py, adapter.py), so the rules are unit-tested with
fakes. Every public method is called with Game.lock held by the HTTP layer (DF is single-threaded), except
envelope_unlocked()/health() and the wall-cap watchdog, which only read state or pause DF.
"""
import json, os, threading, time

DAY = 1200
API_VERSION = "v0"
K_DEFAULT = 40
MAX_ADVANCE_DAYS = 28
WALL_S_DEFAULT = 5400          # 90 min per game (contract §2.1 example)
RUNOUT_CHUNK_DAYS = 7          # unmanaged advances (hands-off window, harness exit): 7 days at a time, as run_one
MAX_STALLS = 20                # run_one's "time stopped advancing" guard
# advance.lua's tripwire reasons (announcement:<TYPE> is one family); stop_on picks a subset per call
TRIPWIRES = ("hostile_visible", "hostile_approaching", "hostile_near_citizens", "citizen_died", "invasion",
             "water_rising", "announcement")
ANNOUNCEMENT_TYPES = ("STRANGE_MOOD", "BERSERK_CITIZEN", "CITIZEN_TANTRUM", "POSSESSED_TANTRUM", "CITIZEN_DEATH",
                      "MIGRANT_ARRIVAL", "MIGRANT_ARRIVAL_NAMED", "D_MIGRANTS_ARRIVAL", "D_MIGRANT_ARRIVAL",
                      "CARAVAN_ARRIVAL", "FIRST_CARAVAN_ARRIVAL", "DIPLOMAT_ARRIVAL", "TRADE_DIPLOMAT_ARRIVAL",
                      "MONARCH_ARRIVAL", "NOBLE_ARRIVAL", "MEGABEAST_ARRIVAL", "WEREBEAST_ARRIVAL", "BEAST_AMBUSH",
                      "AMBUSH_DEFENDER", "AMBUSH_RESIDENT", "AMBUSH_THIEF", "AMBUSH_SNATCHER", "AMBUSH_AMBUSHER",
                      "AMBUSH_AMBUSHER_NATURE", "AMBUSH_MISCHIEVOUS", "AMBUSH_OTHER", "CAVE_COLLAPSE")
# every value stop_on accepts, as an enum in the schema (glm guessed 'hostile', 'death', 'mood' from the description)
STOP_ON_VALUES = list(TRIPWIRES) + [f"announcement:{t}" for t in ANNOUNCEMENT_TYPES]
FINISH_REASONS = ("harness_exited", "credits_exhausted", "runner")   # documented; any [a-z0-9_]{1,64} is accepted
# (runner/dfbenchlib/game.py sends harness_exit, credits_<blocked_reason> and runner_deadline)
import re as _re
_REASON = _re.compile(r"^[A-Za-z0-9_:.-]{1,64}$")


def advance_tool(max_days=MAX_ADVANCE_DAYS):
    return {"type": "function", "function": {
        "name": "advance_days",
        "description": (f"Let 1-{max_days} in-game days pass. Returns when they have run, or earlier at a tripwire "
                        "(the result says which) or at the wall cap. stop_on chooses the tripwires that stop it "
                        f"(default all): {', '.join(TRIPWIRES)}; 'announcement' covers every announcement:<TYPE>, "
                        "or name one, e.g. 'announcement:STRANGE_MOOD'. [] = no early stop. Doesn't count as an action."),
        "parameters": {"type": "object", "required": ["days"], "additionalProperties": False, "properties": {
            "days": {"type": "integer", "minimum": 1, "maximum": max_days},
            "stop_on": {"type": "array", "maxItems": 40, "items": {"type": "string", "enum": STOP_ON_VALUES}}}}}}


class ApiError(Exception):
    def __init__(self, code, msg, status=200, **extra):
        super().__init__(msg)
        self.code, self.msg, self.status, self.extra = code, msg, status, extra

    def body(self):
        return {"ok": False, "error_code": self.code, "error": self.msg, **self.extra}


# ------------------------------------------------------------------ argument checks (the tools' JSON schemas)
_TYPES = {"integer": int, "number": (int, float), "string": str, "boolean": bool, "array": list, "object": dict}


def check_schema(v, sch, path="args", strict=True):
    """A small JSON-schema subset (type, required, properties, additionalProperties, enum, minimum, maximum,
    items, maxItems, minItems). Undeclared arguments are rejected when strict (else left to the facts layer).
    -> error text or None."""
    t = sch.get("type")
    if t:
        py = _TYPES.get(t)
        if py is not None and (not isinstance(v, py) or (t in ("integer", "number") and isinstance(v, bool))):
            return f"{path} must be {'an' if t[0] in 'aeiou' else 'a'} {t}"
    if "enum" in sch and v not in sch["enum"]:
        return f"{path} must be one of {sch['enum']}"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if "minimum" in sch and v < sch["minimum"]:
            return f"{path} must be >= {sch['minimum']}"
        if "maximum" in sch and v > sch["maximum"]:
            return f"{path} must be <= {sch['maximum']}"
    if isinstance(v, list):
        if "maxItems" in sch and len(v) > sch["maxItems"]:
            return f"{path} has more than {sch['maxItems']} items"
        if "minItems" in sch and len(v) < sch["minItems"]:
            return f"{path} has fewer than {sch['minItems']} items"
        for i, x in enumerate(v):
            e = check_schema(x, sch.get("items") or {}, f"{path}[{i}]", strict)
            if e:
                return e
    if isinstance(v, dict) and (t == "object" or "properties" in sch):
        props = sch.get("properties") or {}
        for r in sch.get("required") or []:
            if r not in v:
                return f"{path}.{r} is required"
        extra = sorted(set(v) - set(props))
        if extra and sch.get("additionalProperties", not strict) is False:
            return f"unexpected arguments: {', '.join(extra)}"
        for k, x in v.items():
            if k in props:
                e = check_schema(x, props[k], f"{path}.{k}", strict)
                if e:
                    return e
    return None


def _stop_wanted(stop, stop_on):
    """Does a tripwire stop {reason: 'announcement:X' | 'hostile_visible' | ...} match the call's stop_on?"""
    if stop_on is None:
        return True
    reason = str(stop.get("reason") or "")
    return reason in stop_on or reason.split(":")[0] in stop_on


# ------------------------------------------------------------------ the game
class Game:
    def __init__(self, backend, facts, task, *, out, arm="harness", k=0, K=K_DEFAULT, max_days=MAX_ADVANCE_DAYS,
                 wall_s=WALL_S_DEFAULT, clock=time.monotonic, condition=None, key=None, harness_digest=None,
                 run_id=None, log_api=True, budget=None):
        self.backend, self.facts, self.task = backend, facts, task
        self.out, self.arm, self.k = out, arm, k
        self.stem = f"{arm}-{k}"
        self.K, self.max_days, self.wall_s, self.clock = K, max_days, wall_s, clock
        self.condition = condition or {}
        self.key, self.harness_digest, self.run_id = key, harness_digest, run_id
        self.budget = budget
        self.days = int(task.get("days") or 336)
        self.lock = threading.RLock()
        self.phase = "starting"            # starting -> ready -> running_out -> over -> finalized | failed
        self.end_reason = None             # horizon | fort_lost | wall_cap | crashed
        self.finish_reason = None          # harness_exited | credits_exhausted | runner (POST /finish)
        self.error = None
        self.wall_capped = False
        self.wall_hit = False
        self.advancing = False
        self.t_first = None                # wall clock starts at the harness's first call
        self.t_wall0 = time.time()
        self.throttle_s = 0.0              # provider throttling the gateway reported: not the harness's time
        self.unmanaged_s = 0.0             # server-run time (hands-off window, run-out): not the harness's either
        self.actions_today, self.action_day = 0, None
        self.actions_used = self.actions_rejected = self.limit_rejections = 0
        self.stats = {"decisions": 0, "rejected": 0, "tools": {}, "tripwire_stops": {}, "tripwires_ignored": 0,
                      "stalls": 0, "hands_off_advances": 0, "advances": 0, "runout_advances": 0,
                      "queries": 0, "observes": 0, "cap_hit_day": None}
        self.setup_out = []
        self.summary = None
        self.api_log = None
        self._log_lock = threading.Lock()
        if log_api and out:
            os.makedirs(out, exist_ok=True)
            self.api_log = open(os.path.join(out, f"{self.stem}.api.jsonl"), "a")

    # ---------------------------------------------------------- lifecycle
    def start(self):
        """Reset DF with the task's settings, start the recorder, run the setup, start credit. Then ready."""
        with self.lock:
            try:
                self.s0 = self.backend.prepare(self.task)
                self.start_tick = self.s0["abs_tick"]
                self.end_tick = self.start_tick + self.days * DAY
                w = int(self.task.get("hands_off_days") or 0)
                self.ho_tick = self.start_tick + max(0, self.days - w) * DAY if w > 0 else None
                self.peak, self.min_food, self.min_drink = self.s0["citizens"], self.s0["food"], self.s0["drink"]
                self.last = self.s0
                self.tick = self.start_tick
                self.facts.reset()
                self.setup_out = self.backend.setup(self.task.get("setup") or [])
                self.backend.credit_start()
                self.phase = "ready"
            except Exception as e:   # noqa: BLE001
                self.phase, self.error = "failed", f"{type(e).__name__}: {e}"[:300]
                raise

    @property
    def over(self):
        return self.phase in ("over", "finalized", "failed")

    def day(self):
        return (self.tick - self.start_tick) // DAY

    def envelope(self):
        if self.phase in ("starting",) or not hasattr(self, "start_tick"):
            return {"day": None, "tick": None, "days_left": None, "game_over": self.phase == "failed"}
        e = {"day": self.day(), "tick": self.tick, "days_left": max(0, (self.end_tick - self.tick) // DAY),
             "game_over": self.over or self.phase == "running_out"}
        if self.ho_tick is not None:
            e["hands_off_in_days"] = max(0, (self.ho_tick - self.tick) // DAY)
        return e

    def touch(self):
        """The harness's first call starts the wall clock."""
        if self.t_first is None:
            self.t_first = self.clock()

    def wall_used(self):
        if self.t_first is None:
            return 0.0
        elapsed = self.clock() - self.t_first
        # throttle waits of parallel model calls overlap: never exclude more than the game's elapsed wall time
        return elapsed - min(self.throttle_s, elapsed) - self.unmanaged_s

    def finished_by(self):
        """What ended the game: horizon | fort_lost | wall_cap | crashed, or the /finish reason when the server ran
        the rest of the horizon after it (runner/: harness_exit, credits_<why>, runner_deadline)."""
        if self.end_reason == "horizon" and self.finish_reason:
            return self.finish_reason
        return self.end_reason

    def health(self):
        return {"ok": self.phase != "failed", "phase": self.phase, "ready": self.phase != "starting",
                "finished": self.phase == "finalized", "finished_by": self.finished_by(),
                "end_reason": self.end_reason, "finish_reason": self.finish_reason, "error": self.error,
                "finalized": self.phase == "finalized", "wall_used_s": round(self.wall_used(), 1),
                "wall_s": self.wall_s, "throttle_s": round(self.throttle_s, 1), **self.envelope()}

    # ---------------------------------------------------------- read-only endpoints
    def task_info(self):
        t = self.task
        goal = (t.get("goal") or "").replace("{days}", str(self.days)) or None
        ho = None
        if self.ho_tick is not None:
            ho = {"from_day": (self.ho_tick - self.start_tick) // DAY, "days": int(t.get("hands_off_days"))}
        cond = self.condition or {}
        return {"api": API_VERSION, "key": self.key, "run_id": self.run_id,
                "model": {k: cond.get(k) for k in ("model", "prices", "prices_unit", "price_table_hash")},
                "budget": self.budget, "limits": {"wall_s": self.wall_s, "actions_per_game_day": self.K,
                                                  "max_advance_days": self.max_days},
                "task": {"name": t.get("name"), "days": self.days, "goal": goal, "brief": t.get("brief"),
                         "hands_off": ho, "strange_moods": bool(t.get("strange_moods"))},
                "rules": self.rules(), "tools": self.tools(), "queries": self.facts.queries(),
                "manual": self.facts.manual(), "obs_schema": getattr(self.facts, "OBS_SCHEMA", None)}

    def rules(self):
        return {"actions_per_game_day": self.K, "max_advance_days": self.max_days, "wall_s": self.wall_s,
                "advance_counts_as_action": False, "tripwires": list(TRIPWIRES),
                "announcement_types": list(ANNOUNCEMENT_TYPES), "lost_fort_ends_game": True,
                "hands_off": "actions rejected from day A; advances cut at A; the server then runs the window",
                "wall_excludes": ["provider throttling reported by the gateway", "server-run unmanaged time"]}

    def tools(self):
        return [t for t in self.facts.tools() if t["function"]["name"] != "advance_days"] + [advance_tool(self.max_days)]

    def _schemas(self):
        return {t["function"]["name"]: t["function"].get("parameters") or {"type": "object"} for t in self.tools()}

    def _require_ready(self):
        if self.phase == "starting":
            raise ApiError("not_ready", "the game is still starting", status=503)
        if self.phase == "failed":
            raise ApiError("game_over", "the game failed to start: " + str(self.error))

    def observe(self):
        self._require_ready()
        self.stats["observes"] += 1
        try:
            return self.facts.observe()
        except Exception as e:   # noqa: BLE001  FactsError: the probe failed as a whole
            raise ApiError("internal_error", f"the observation failed: {type(e).__name__}: {e}"[:300])

    def query(self, name, params):
        self._require_ready()
        self.stats["queries"] += 1
        try:
            return self.facts.query(name, **params)
        except KeyError:
            raise ApiError("unknown_query", f"no query named {name!r}", status=404,
                           valid=[q["name"] for q in self.facts.queries()])
        except TypeError as e:
            raise ApiError("bad_arguments", str(e))

    def events(self, since_tick):
        """-> {"events": [...], ...} (the facts layer's page: dropped / now when it reports them)."""
        self._require_ready()
        if since_tick < 0:
            raise ApiError("bad_arguments", "since_tick must be >= 0")
        try:
            r = self.facts.events(since_tick)
        except TypeError as e:
            raise ApiError("bad_arguments", str(e))
        return r if isinstance(r, dict) else {"events": r}

    # ---------------------------------------------------------- actions
    def actions_left(self):
        if self.action_day != self.day():
            return self.K
        return max(0, self.K - self.actions_today)

    def act(self, tool, args):
        """One /act call. -> body dict (ok/result or ok:false/error_code)."""
        self._require_ready()
        if self.over or self.phase == "running_out":
            raise ApiError("game_over", f"the game is over ({self.end_reason or self.finish_reason})")
        if self.wall_hit:   # the watchdog flagged the cap and hasn't ended the game yet
            self.wall_cap()
            raise ApiError("game_over", "the game is over (wall_cap)")
        self.stats["decisions"] += 1
        schemas = self._schemas()
        if not isinstance(tool, str) or tool not in schemas:
            self.actions_rejected += 1
            raise ApiError("unknown_tool", f"no tool named {tool!r}", valid_tools=sorted(schemas))
        if args is None:
            args = {}
        e = check_schema(args, schemas[tool], strict=tool == "advance_days" or getattr(self.facts, "STRICT_ARGS", True))
        if tool == "advance_days":
            if e:
                self.actions_rejected += 1
                raise ApiError("bad_arguments", e)
            return self.advance_days(args["days"], args.get("stop_on"))
        if self.ho_tick is not None and self.tick >= self.ho_tick:
            self.actions_rejected += 1
            raise ApiError("hands_off", "the hands-off window has begun: no actions until the end of the game")
        if self.action_day != self.day():
            self.action_day, self.actions_today = self.day(), 0
        if self.actions_today >= self.K:
            self.actions_rejected += 1; self.limit_rejections += 1
            raise ApiError("action_limit", f"{self.K} actions used today; only advance_days is accepted until the "
                                           "day changes", actions_left_today=0)
        # an action counts once it passes the limit check, whether or not the game accepts it
        self.actions_today += 1; self.actions_used += 1
        self.stats["tools"][tool] = self.stats["tools"].get(tool, 0) + 1
        if e:
            self.actions_rejected += 1; self.stats["rejected"] += 1
            raise ApiError("bad_arguments", e, actions_left_today=self.actions_left())
        r = self.facts.act(tool, args)
        if not r.get("ok"):
            self.actions_rejected += 1; self.stats["rejected"] += 1
        return {**r, "actions_left_today": self.actions_left()}

    def _record_stop(self, stop):
        r = str(stop.get("reason", "?")).split(":")[0]
        self.stats["tripwire_stops"][r] = self.stats["tripwire_stops"].get(r, 0) + 1

    def _track(self, s):
        self.last = s
        self.tick = s["abs_tick"]
        self.peak = max(self.peak, s["citizens"])
        self.min_food = min(self.min_food, s["food"]); self.min_drink = min(self.min_drink, s["drink"])

    def _advance_to(self, target, stop_on=None, unmanaged=False):
        """Advance until target (or a wanted tripwire, the wall cap, a lost fort, or a stall).
        -> (ticks moved, the stop that ended it or None, ignored stops, popups dismissed)."""
        moved_total, stopped, ignored, popups = 0, None, [], []
        while self.tick < target and not (self.wall_hit and not unmanaged):
            self.advancing = True
            try:
                moved, stop, intr = self.backend.advance(target - self.tick)
            finally:
                self.advancing = False
            popups += intr
            self._track(self.backend.score())
            moved_total += moved
            self.stats["runout_advances" if unmanaged else "advances"] += 1
            if moved == 0:
                self.stats["stalls"] += 1
                if self.stats["stalls"] > MAX_STALLS:
                    raise RuntimeError(f"time stopped advancing ({MAX_STALLS} stalls)")
                if not unmanaged:
                    break
            if stop:
                self._record_stop(stop)
                if not unmanaged and _stop_wanted(stop, stop_on):
                    stopped = stop
                    break
                ignored.append(stop)
                self.stats["tripwires_ignored"] += 1
            if self.last["citizens"] == 0:
                break
        return moved_total, stopped, ignored, popups

    def advance_days(self, days, stop_on=None):
        if stop_on is not None:
            bad = [s for s in stop_on if not (s in TRIPWIRES or (s.startswith("announcement:") and
                                                                  s.split(":", 1)[1] in ANNOUNCEMENT_TYPES))]
            if bad:
                raise ApiError("bad_arguments", f"unknown stop_on {bad}", valid=list(TRIPWIRES))
        t0 = self.tick
        target = min(self.tick + days * DAY, self.end_tick)
        if self.ho_tick is not None and self.tick < self.ho_tick:
            target = min(target, self.ho_tick)          # no advance runs past day A
        try:
            moved, stopped, ignored, popups = self._advance_to(target, stop_on)
        except Exception as e:   # noqa: BLE001  DF hung or died: the game ends as crashed (an infra re-run)
            self._end("crashed", error=f"{type(e).__name__}: {e}"[:300])
            raise ApiError("game_over", "the game crashed: " + str(e)[:200])
        # contract §3.1: {"advanced_ticks", "stopped": null | {"reason", "detail", "after_ticks"}}
        result = {"advanced_ticks": self.tick - t0, "advanced_days": round((self.tick - t0) / DAY, 2),
                  "stopped": {k: stopped.get(k) for k in ("reason", "detail", "after_ticks", "abs_tick")}
                  if stopped else None}
        if ignored:
            result["tripwires_ignored"] = [{k: x.get(k) for k in ("reason", "detail", "abs_tick")} for x in ignored]
        if popups:
            result["interruptions"] = [{"tick": p.get("tick"), "text": p.get("text")} for p in popups]
        if self.last["citizens"] == 0:
            self._end("fort_lost")
        elif self.tick >= self.end_tick:
            self._end("horizon")
        elif self.wall_hit:
            self.wall_capped = True
            result["wall_capped"] = True
            self._end("wall_cap")
        elif self.ho_tick is not None and self.tick >= self.ho_tick:
            result["hands_off"] = True        # the window has begun: the server runs it now, no actions
            self._run_out(hands_off=True)
        if self.over:
            result["end_reason"] = self.end_reason
        return {"ok": True, "result": result, "actions_left_today": self.actions_left()}

    # ---------------------------------------------------------- the end
    def _run_out(self, hands_off=False):
        """The rest of the horizon with no actions (hands-off window, harness exit, credits gone), then the end."""
        self.phase = "running_out"
        t = self.clock()
        if self.stats["cap_hit_day"] is None and not hands_off:
            self.stats["cap_hit_day"] = self.day()
        try:
            while self.tick < self.end_tick and self.last["citizens"] > 0:
                n0 = self.stats["runout_advances"]
                self._advance_to(min(self.tick + RUNOUT_CHUNK_DAYS * DAY, self.end_tick), unmanaged=True)
                if hands_off:
                    self.stats["hands_off_advances"] += self.stats["runout_advances"] - n0
        except Exception as e:   # noqa: BLE001
            self.unmanaged_s += self.clock() - t
            self._end("crashed", error=f"{type(e).__name__}: {e}"[:300])
            return
        self.unmanaged_s += self.clock() - t
        self._end("fort_lost" if self.last["citizens"] == 0 else "horizon")

    def finish(self, reason="harness_exited"):
        """POST /finish: the harness exited or its credits are gone. Runs out the horizon, then the artifacts."""
        if not isinstance(reason, str) or not _REASON.match(reason):
            raise ApiError("bad_arguments", "reason must be a short identifier, e.g. " + ", ".join(FINISH_REASONS))
        self._require_ready()
        if not self.over:
            self.finish_reason = reason
            if self.phase != "running_out":
                self._run_out()
        return self.health()

    def wall_cap(self):
        """Called by the watchdog (lock held) once the wall clock ran out outside an advance."""
        if not self.over and self.phase == "ready":
            self.wall_capped = True
            self._end("wall_cap")

    def add_throttle(self, seconds=None, total_s=None):
        """Provider throttling the gateway reports: `seconds` more, or its running `total_s` (gateway /status
        throttle_wait_total_s; never lowers what was already excluded)."""
        if total_s is not None:
            self.throttle_s = max(self.throttle_s, float(total_s))
        if seconds is not None:
            self.throttle_s += max(0.0, float(seconds))
        if self.wall_hit and self.wall_used() < self.wall_s and not self.over:
            self.wall_hit = False

    def _end(self, reason, error=None):
        if self.over:
            return
        self.end_reason = reason
        if error:
            self.error = error
        self.phase = "over"
        self.finalize()

    def finalize(self):
        """Write the §6 artifacts: <stem>.daily.json, .credit.json, .final.json, the summary.jsonl row."""
        from gameapi.server import artifacts as A
        crashed = self.error if self.end_reason == "crashed" else None
        hung = bool(crashed) and crashed.startswith(("DFCrash", "TimeoutExpired"))
        sf, daily, credit, err = self.backend.final(self.out, self.stem, self.start_tick, hung=hung)
        if err:
            crashed = crashed or err
            sf = sf or (self.last if hung else sf)
        if sf:
            with open(os.path.join(self.out, f"{self.stem}.final.json"), "w") as f:
                json.dump({"F0": self.s0, "F": sf}, f)
        self.summary = A.summary_row(self, sf, daily, credit, crashed)
        A.append_line(os.path.join(self.out, "summary.jsonl"), json.dumps(self.summary))
        self.phase = "finalized"
        return self.summary

    # ---------------------------------------------------------- log
    def log(self, method, path, request, status, response, latency_s):
        if not self.api_log:
            return
        rec = {"t": round(time.time(), 3), "tick": getattr(self, "tick", None),
               "day": self.day() if hasattr(self, "start_tick") else None, "method": method, "path": path,
               "request": request, "status": status, "response": response, "latency_ms": round(latency_s * 1000, 1)}
        with self._log_lock:
            self.api_log.write(json.dumps(rec, default=str) + "\n"); self.api_log.flush()


class Watchdog(threading.Thread):
    """Ends the game at the wall cap: pauses DF inside an advance (the advance then returns), or ends it between
    calls. Polls once a second."""

    def __init__(self, game, period=1.0, gateway_status_url=None, finish_on_blocked=False, gateway_every=10.0,
                 gateway_status_path=None, ledger_path=None):
        super().__init__(daemon=True)
        self.game, self.period, self.stop = game, period, threading.Event()
        self.gw_url, self.finish_on_blocked, self.gw_every, self.gw_last = gateway_status_url, finish_on_blocked, \
            gateway_every, 0.0
        self.gw_path, self.ledger_path = gateway_status_path, ledger_path
        self.gw_status = None

    def read_status_file(self):
        """The gateway's status file (runner: /ledger/gateway-status.json), else its ledger's throttle_wait_s summed.
        -> status dict or None."""
        try:
            with open(self.gw_path) as f:
                return json.load(f)
        except (OSError, ValueError, TypeError):
            pass
        if not self.ledger_path:
            return None
        tot = 0.0
        try:
            with open(self.ledger_path) as f:
                for line in f:
                    try:
                        tot += float(json.loads(line).get("throttle_wait_s") or 0)
                    except (ValueError, AttributeError):
                        pass
        except OSError:
            return None
        return {"throttle_wait_total_s": tot}

    def poll_gateway(self, fetch=None):
        """Read the gateway's /status: throttle_wait_total_s -> excluded wall time; blocked_reason (credits gone) ->
        run out the horizon when finish_on_blocked. fetch: url -> dict (tests)."""
        g = self.game
        if fetch is None:
            import urllib.request

            def fetch(u):
                with urllib.request.urlopen(u, timeout=5) as r:
                    return json.loads(r.read())
        try:
            st = fetch(self.gw_url) if self.gw_url else self.read_status_file()
        except Exception:   # noqa: BLE001  the gateway may not be up yet
            return
        if not isinstance(st, dict):
            return
        self.gw_status = st
        if st.get("throttle_wait_total_s") is not None:
            g.add_throttle(total_s=st["throttle_wait_total_s"])
        if self.finish_on_blocked and st.get("blocked_reason") and g.phase == "ready" and not g.advancing:
            def run():
                with g.lock:
                    try:
                        g.finish("credits_exhausted")
                    except ApiError:
                        pass
            threading.Thread(target=run, daemon=True).start()

    def check(self):
        g = self.game
        if g.over or g.phase != "ready" or g.wall_s is None or g.t_first is None:
            return
        if g.wall_used() < g.wall_s:
            return
        g.wall_hit = True
        if g.advancing:
            g.backend.interrupt()     # without the lock: the advance holds it
            return
        if g.lock.acquire(timeout=self.period):
            try:
                if not g.advancing:
                    g.wall_cap()
            finally:
                g.lock.release()

    def run(self):
        while not self.stop.wait(self.period):
            try:
                if (self.gw_url or self.gw_path or self.ledger_path) and time.monotonic() - self.gw_last >= self.gw_every:
                    self.gw_last = time.monotonic()
                    self.poll_gateway()
                self.check()
            except Exception:   # noqa: BLE001  never kill the watchdog
                pass
