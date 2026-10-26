#!/usr/bin/env python3
"""§5 smoke-test batch: N runs per arm, 1 in-game year each,
all from the same starting fort (fort_start_snapshot via reset_fort.sh).
Interleaved by arm so a partial batch still has every arm.

Arms: model (v1 tools), model2 (v2 tools + manual), and references on the v2 tool API:
noop (no actions), random (random valid tool calls), scripted (the MANUAL's playbook, policies.py),
automation (DFHack's bundled automation + quickfort blueprints, set up once; policies.Automation, automation/).
Experimental: dfai (the df-ai C++ plugin plays by itself; needs the yukon-df:dfai image, docker/Dockerfile.dfai,
and is a privileged reference, not a tool-API arm: research/df-ai-fairness-audit.md).

usage: smoke.py --runs 5 [--arms model2,noop,random,scripted] [--out runs/smoke5] [--decision-cap 500]
                [--provider z-ai]
Writes <out>/<arm>-<k>.jsonl (per step) and <out>/summary.jsonl (per run). Crashed runs are retried on
resume; analyze.py keeps the last completed row per (arm, k). dfai runs where DF itself crashed are recorded
(crashed + df_crashed) and not retried; other dfai failures are retried once.

Parallel mode (native Linux): smoke.py --workers W runs W DF instances (instances/1..W, ports 5001..5000+W; see
instance.sh). The parent hands out (arm, k) jobs one at a time to free slots; each job runs as
`smoke.py --instance i --job arm:k` against its own DF copy, so a slow run never holds up the queue. A slot only
starts a job when MemAvailable >= --min-free-mb. Results don't depend on the instance: every run restores the same
snapshot and reset_fort.sh asserts its start state. In Docker, run one container per instance (docker/batch.sh).
"""
import argparse, fcntl, json, os, re, shutil, signal, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
import harness2 as H2
import loopwatch
from bench import prompts as PL
from bench import key as BK
from bench import ablate as AB
import policies

V2_ARMS = ("model2", "scripted", "random", "automation")
OTHER_ARMS = ("dfai",)  # no observe/act loop: the arm plays inside DF
DFAI_CONFIG = os.path.join(H.DFP, "docker", "dfai", "df-ai.json")   # --dfai-config; read by df-ai at DF start
DFAI_LOG_EVENTS = {   # df-ai.log lines of the behaviours the fairness audit switches off, and some progress markers
    "trade_complete": "trade: complete", "trade_caravan": "trade: caravan detected",
    "diplomacy_completed": "[DIPLO] completed", "diplomacy_anvil_request": "[DIPLO] requested anvils",
    "petition_accepted": "[PETITION] accepted", "petition_ignored": "[PETITION] ignoring",
    "squad_created": "[military] created", "soldier_drafted": "[military] drafted",
    "noble_appointed": "Appointing ", "noble_slot_created": "Created assignment slot",
    "vein_tunnel_planned": "Planning tunnel to", "cavern_outpost": "outpost: wall",
    "manager_order": "add_manager_order(", "setup_complete": "Planning complete!",
    "abandon": "abandon called", "exception": "EXCEPTION",
    "farm_mud_cheat": "cheat: mud invocation"}   # research/df-ai-privilege-audit.md: mud conjured under a farm plot
DFAI_MAX_ATTEMPTS = 2   # a (dfai, k) that failed this often without a DF crash is not retried again
SCENARIO = None      # loaded scenarios/<name>.json (see scenarios/README.md), or None for the default year

def load_scenario(path):
    """A scenario: start snapshot, setup dfhack commands run after load, horizon, agent brief and goal, scored metrics."""
    sc = json.load(open(path))
    sc.setdefault("name", os.path.splitext(os.path.basename(path))[0])
    snap = sc.get("snapshot")
    if snap:   # fort_start_snapshot without its save -> the seed-built default fort (bench/key.py start_snapshot)
        sc["snapshot"] = BK.start_snapshot(snap if os.path.isabs(snap) else os.path.join(H.DFP, snap))
    sc["snapshot_pool"] = [p if os.path.isabs(p) else os.path.join(H.DFP, p) for p in sc.get("snapshot_pool") or []]
    sc["_setup"] = sc.get("setup", [])
    seeded = any("{seed}" in c for cmd in sc["_setup"] for c in cmd)
    if seeded and not sc.get("setup_seeds"):
        sys.exit(f"{path}: setup uses {{seed}} but the scenario has no setup_seeds [lo, hi]")
    if sc.get("split") == "train":
        lo, hi = sc.get("setup_seeds") or (0, 999)
        if not (0 <= lo <= hi <= 999):
            sys.exit(f"{path}: train setup_seeds must lie in 0-999 (BENCHMARK-v1 §5.4), got {sc['setup_seeds']}")
    return sc

def setup_for(sc, k):
    """The scenario's setup for run k: {seed} becomes setup_seeds[0] + k (§2.1), refused outside [lo, hi], so a
    split's seed range can't leak into another's. Applied outside run_one, so the loop hash doesn't change."""
    if not sc or not sc.get("setup_seeds"):
        return sc.get("_setup", []) if sc else []
    lo, hi = sc["setup_seeds"]
    if not lo <= lo + k <= hi:
        sys.exit(f"run k={k}: setup seed {lo + k} is outside this scenario's setup_seeds [{lo}, {hi}]")
    return [[c.replace("{seed}", str(lo + k)) for c in cmd] for cmd in sc["_setup"]]

def split_of(sc):
    """A scenario's split (§5.4). Files without one are the test-public suite: only "train" is trainable."""
    return (sc or {}).get("split") or "test-public"

def pick_snapshot(k, seed):
    """A scenario with a `snapshot_pool` (LT09/LT10 embark sites) starts run k on pool[(seed + k) mod n]
    (BENCHMARK-v1 §LT09). Called before run_one, so the decision loop is unchanged."""
    pool = (SCENARIO or {}).get("snapshot_pool")
    if pool:
        SCENARIO["snapshot"] = pool[(seed + k) % len(pool)]
        print(f"=== snapshot {os.path.relpath(SCENARIO['snapshot'], H.DFP)} (pool {(seed + k) % len(pool)}/{len(pool)})", flush=True)

def task_obs(sc, days):
    """What the agent is told about the task (BENCHMARK-v1 §2.4.4): the scenario's `brief` and its plain-language
    `goal`, with {days} filled in from the actual horizon. Never the `metrics` dict or any other scoring internals."""
    o = {}
    if sc and sc.get("goal"):
        o["goal"] = sc["goal"].replace("{days}", str(days))
    if sc and sc.get("brief"):
        o["scenario"] = sc["brief"]
    return o

def hands_off_tick(sc, start, days):
    """BENCHMARK-v1 §2.1 / v2 §1.2: the abs_tick from which no arm is asked for a decision (the hands-off window
    W = (A, H] with A = days - hands_off_days), or None when the scenario has no window."""
    w = int((sc or {}).get("hands_off_days") or 0)
    return start + max(0, days - w) * DAY if w > 0 else None

def hands_off_in_days(now, ho_tick):
    """The observation field: whole days until the window starts (0 in its last day), as days_left_in_run counts."""
    return max(0, (ho_tick - now) // DAY)

DAY = 1200
MAX_API_STREAK = 5      # consecutive model-API failures before the run is marked crashed
# A request the server rejects because the prompt exceeds the model's context window (local models: Qwen3-8B has
# 40,960 tokens; a fort with dozens of orders makes 12 messages of history overflow it). Retrying the same prompt
# can't succeed, so the turn is retried once with the history dropped: system prompt + current observation.
CONTEXT_ERROR = re.compile(r"HTTP 4\d\d.*(context (window|length)|prompt too long|maximum context|too many tokens)", re.I | re.S)
FORCE_AFTER = 5          # consecutive non-advance decisions before the harness advances 1 day itself
LOOP_NOTES = False
HISTORY = 12             # --history: messages kept after the system prompt, the new observation included (HARNESS-PLAN 1.6)
ACTION_LOG = 8           # recent_actions entries in the v2 observation (HARNESS-PLAN 1.5)       # --loop-notes: tell model2 when loopwatch flags a loop (changes the arm; off by default)

CALL_TIMEOUT = None   # v2.1.1: set to POLL_TIMEOUT after DF hangs, so the run's final reads can't block 600 s each

def lua_json(script, *args):
    raw = H.dfhack("lua", "-f", os.path.join(H.DFP, script), *args, timeout=CALL_TIMEOUT)
    return json.loads(raw[raw.index("{"):raw.rindex("}") + 1])

def score():
    return lua_json("score.lua")

ADVANCE_STOP = None   # abs_tick no advance may pass (next snapshot day), set by run_one

INTERRUPTIONS = []    # popup texts dismissed since the agent's last observation (issue #5)
INTERRUPTION_LOG = [] # all of this run's, for the summary (every arm, including ones that never observe)
POLL = ("local p=df.global.world.status.popups local t={} for i=0,#p-1 do local ok,x=pcall(function() return "
        "dfhack.df2utf(p[i].text) end) t[#t+1]=ok and x or '?' end "
        "print(df.global.pause_state, df.global.cur_year*403200+df.global.cur_year_tick, "
        "table.concat(dfhack.gui.getCurFocus(true),','), require('json').encode(t), #dfhack.units.getCitizens())")
STUCK_S = 5           # unpaused, not ticking this long, and a popup or another screen showing = blocked: dismiss it
POLL_TIMEOUT = 30     # v2.1.1: a poll DF doesn't answer within this counts as not ticking (H.dfhack's default is 600 s)
HANG_S = 300          # not ticking this long with nothing to dismiss = DF hung: the run fails (infra), never a silent pause

def _poll():
    """-> (paused, tick, focus, popup texts, citizens); citizens is None if not reported. A poll DF doesn't answer
    within POLL_TIMEOUT (its main thread is stuck, so dfhack-run blocks) returns tick None."""
    try:
        out = H.dfhack("lua", POLL, timeout=POLL_TIMEOUT).split("\t", 4)
    except subprocess.TimeoutExpired:
        return False, None, "(no answer)", [], None
    try:
        cit = int(out[4]) if len(out) > 4 else None
        return out[0].strip() == "true", int(out[1]), out[2], json.loads(out[3]) if len(out) > 3 else [], cit
    except (ValueError, IndexError):
        return False, None, "", [], None

def advance(ticks):
    """Advance up to `ticks`; returns ticks actually elapsed. DF auto-pause may end it early.
    Some events (first caravan, succession, ...) open a modal popup: the game stays unpaused but stops ticking.
    That used to cost the full deadline (2-3 min) and was then dismissed silently (issue #5). Now a popup stall is
    detected within STUCK_S seconds, its text is kept for the agent (INTERRUPTIONS), and it's dismissed.
    v2.1: only game ticks end an advance. There is no wall-clock deadline any more (it paused at a load-dependent
    tick on a slow host), and a stall is dismissed only when DF shows a popup or a screen other than the main
    fortress view: "no tick for 5 s" alone (a slow or busy host) is waited out, and sending Esc then opened DF's
    Options screen. HANG_S without a tick and with nothing to dismiss raises (an infra failure, retried)."""
    t0 = score()["abs_tick"]
    if ADVANCE_STOP is not None and ADVANCE_STOP > t0:
        ticks = min(ticks, ADVANCE_STOP - t0)   # snapshots land on their day, not up to 7 days late
    LAST_STOP.clear()
    out = H.dfhack("lua", "-f", os.path.join(H.DFP, "advance.lua"), str(ticks))
    gen = out.split("gen ")[-1].strip() if "gen " in out else None
    last_tick, still_since, dismissals = None, time.time(), 0
    while True:
        time.sleep(1)
        paused, tick, focus, popups, cit = _poll()
        if paused:
            break
        if cit == 0:   # v2.1.1: the fort is lost (DF then opens its Options screen and stops time): end the advance
            H.dfhack("lua", "df.global.pause_state=true")
            break
        if tick is not None and tick != last_tick:
            last_tick, still_since = tick, time.time()
            continue
        still = time.time() - still_since
        # a stuck DF (tick None) gets no dismiss calls: they would block too; the hang guard below covers it
        blocked = tick is not None and (bool(popups) or (focus or "").split(",")[0] != "dwarfmode/Default")
        if blocked and still >= STUCK_S and dismissals < 5:
            got = ([{"tick": tick, "focus": focus, "text": t[:300]} for t in popups] or
                   [{"tick": tick, "focus": focus, "text": "(modal screen, no popup text)"}])
            INTERRUPTIONS.extend(got); INTERRUPTION_LOG.extend(got)
            dismiss_popups()
            dismissals += 1; still_since = time.time()
        elif still >= HANG_S:
            try:
                H.dfhack("lua", "df.global.pause_state=true", timeout=POLL_TIMEOUT)
            except subprocess.TimeoutExpired:
                pass
            raise DFCrash(f"DF stopped ticking for {HANG_S} s at tick {last_tick} (focus {focus}, {len(popups)} popups)")
    moved = score()["abs_tick"] - t0
    if moved == 0:   # paused immediately on something: dismiss once, as before
        dismiss_popups()
    if gen:   # advance.lua's tripwires: why the game paused early, if it did (HARNESS-PLAN 1.1)
        raw = H.dfhack("lua", "local s=rawget(_G,'__adv_stop') if s and tostring(s.gen)=='" + gen +
                       "' then print(require('json').encode(s)) end")
        try:
            LAST_STOP.update(json.loads(raw[raw.index("{"):raw.rindex("}") + 1]) if "{" in raw else {})
        except ValueError:
            pass
    return moved


def _log_entry(ticks, name, raw_args, result, err):
    """One recent_actions entry: day, call, and a short outcome (error code, or the first part of the result)."""
    try:
        a = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
    except ValueError:
        a = raw_args
    e = {"day": round(ticks / DAY, 1), "tool": name, "args": a}
    if err:
        try:
            d = json.loads(result[len("ERROR: "):])
            e["error"] = d.get("error_code") or "failed"
        except ValueError:
            e["error"] = result[7:60]
    else:
        e["ok"] = result[:70]
    return e


LAST_STOP = {}   # the last advance's tripwire stop: {reason, detail, abs_tick, after_ticks}, empty if none


def stop_note():
    """Text added to the advance_days result when a tripwire stopped it early."""
    if not LAST_STOP:
        return ""
    return (f"; stopped early after {LAST_STOP.get('after_ticks', 0) / DAY:.1f} days: {LAST_STOP.get('reason')}"
            + (f" ({LAST_STOP['detail']})" if LAST_STOP.get("detail") else ""))

class DFCrash(RuntimeError):
    """The DF process died (or stopped answering) during a run."""

def df_alive():
    return subprocess.run(["pgrep", "-x", "dwarfort"], capture_output=True).returncode == 0

def dfai_install_config():
    """df-ai reads dfhack-config/df-ai.json once, when DF loads the plugin, so this must run before reset()."""
    shutil.copyfile(DFAI_CONFIG, os.path.join(H.DF, "dfhack-config", "df-ai.json"))
    log = os.path.join(H.DF, "df-ai.log")
    if os.path.exists(log):
        os.remove(log)

def dfai_enable():
    """Enable df-ai once, after the reset and the scenario setup. It is never disabled or re-enabled during a run:
    re-enabling re-plans the fort over itself and crashed DF in the port assessment."""
    out = H.dfhack("enable", "df-ai", with_stderr=True)
    for _ in range(60):          # it starts on the next dwarfmode frame and then plans the fort (PlanSetup)
        time.sleep(1)
        st = H.dfhack("ai")
        if st and "not running" not in st:
            return {"enable": out[-300:], "version": H.dfhack("ai", "version")[-600:]}
    raise RuntimeError("df-ai did not start: " + (out + " | " + st)[-300:])

def dfai_advance(ticks):
    """Let df-ai play `ticks` game ticks. df-ai unpauses the game itself about 2 s after any pause, so wait for
    the tick count rather than for a pause; unpause too if the game stays paused (auto-pause, popup).
    Raises DFCrash if the DF process dies."""
    def state():
        raw = H.dfhack("lua", "print(df.global.cur_year*403200+df.global.cur_year_tick, df.global.pause_state)")
        t, p = raw.split()[:2]
        return int(t), p == "true"
    if not df_alive():
        raise DFCrash("DF process not running")
    t0, _ = state(); target = t0 + ticks
    H.dfhack("lua", "-f", os.path.join(H.DFP, "advance.lua"), str(ticks), "notrip")   # pauses again exactly at target; df-ai plays on, so no tripwires
    deadline, paused_s, t = time.time() + max(180, ticks / 30), 0, t0
    while time.time() < deadline:
        time.sleep(1)
        if not df_alive():
            raise DFCrash(f"DF process died (last abs_tick {t})")
        try:
            t, paused = state()
        except (ValueError, subprocess.TimeoutExpired) as e:
            if not df_alive():
                raise DFCrash(f"DF process died (last abs_tick {t})")
            raise DFCrash(f"DF not answering at abs_tick {t}: {type(e).__name__}")
        if t >= target:
            break
        paused_s = paused_s + 1 if paused else 0
        if paused_s >= 5:
            H.dfhack("lua", "df.global.pause_state=false"); paused_s = 0
    moved = state()[0] - t0
    if moved == 0:   # stuck on a popup/auto-pause screen: try dismissing once, as advance() does
        H.dfhack("lua", "local p=df.global.world.status.popups for i=#p-1,0,-1 do p:erase(i) end")
    return moved

def dismiss_popups():
    """Clear popups; leave a screen only if one other than the main fortress view is showing. v2.1: Esc used to be
    sent whenever the top viewscreen wasn't viewscreen_dwarfmodest (a DFHack overlay counts), which on the main view
    opened DF's Options screen and stopped time. Options itself is closed again."""
    H.dfhack("lua", "local p=df.global.world.status.popups for i=#p-1,0,-1 do p:erase(i) end")
    # v2.1.1: Options is closed by its flag (Esc doesn't close it, checked in game); Esc only off the fortress view
    H.dfhack("lua", "local mi=df.global.game.main_interface if mi.options.open then mi.options.open=false return end "
                    "local f=dfhack.gui.getCurFocus(true)[1] or '' if f:find('^dwarfmode') then return end "
                    "require('gui').simulateInput(dfhack.gui.getDFViewscreen(true),'LEAVESCREEN')")

def append_line(path, line):
    """Append one line under an exclusive flock (parallel workers share summary.jsonl)."""
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(line + "\n"); f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)

def done_jobs(outdir, sc_name):
    """(arm, k) pairs that resume skips: completed rows of this scenario (crashed rows are retried), plus dfai runs
    where DF itself crashed or that failed DFAI_MAX_ATTEMPTS times. A child killed mid-write can leave a truncated
    last line; it is skipped."""
    sp = os.path.join(outdir, "summary.jsonl")
    if not os.path.exists(sp):
        return set()
    rows = []
    for l in open(sp):
        try:
            rows.append(json.loads(l))
        except ValueError:
            pass
    rows = [r for r in rows if r.get("scenario") == sc_name]   # one --out dir may hold several scenarios
    done = {(r["arm"], r["k"]) for r in rows if not r.get("crashed")}
    # dfai: a DF crash is an outcome, not a harness fault, so it is not retried; other failures get one retry
    dfai_rows = [r for r in rows if r["arm"] == "dfai"]
    done |= {("dfai", r["k"]) for r in dfai_rows if r.get("df_crashed")}
    done |= {("dfai", k) for k in {r["k"] for r in dfai_rows}
             if sum(r["k"] == k for r in dfai_rows) >= DFAI_MAX_ATTEMPTS}
    return done

def batch_lock(outdir):
    """One batch per --out dir; the lock is held until this process exits."""
    lock = open(os.path.join(outdir, ".batch.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(f"another batch already holds {outdir}/.batch.lock")
    return lock

def mem_available_mb():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return 0

def stop_instance(n):
    """Kill instance n's DF (only that one) and confirm it is gone. Returns the pids still alive."""
    r = subprocess.run(["bash", "-c", '. "$0/instance.sh" || exit 1; for i in 1 2 3 4 5 6 7 8 9 10; do '
                        'p=$(df_pids); [ -z "$p" ] && exit 0; kill -9 $p; sleep 0.5; done; df_pids', H.DFP],
                       env=dict(os.environ, DF_INSTANCE=str(n)), capture_output=True, text=True)
    left = r.stdout.split()
    if left:
        print(f"WARNING: instance {n} DF still alive after stop: {left}", flush=True)
    return left

def run_parallel(a, jobs, child_args):
    """Dynamic queue over W instance slots (1..W). Each job is a child process; its stdout goes to
    <out>/<arm>-<k>.stdout and its summary row to the shared summary.jsonl. On exit, normal or not (Ctrl-C,
    SIGTERM, an exception), every child is terminated and every instance's DF stopped: DF runs under setsid, so
    it would otherwise outlive the batch and a re-run's resets would kill it mid-run."""
    def on_term(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    signal.signal(signal.SIGTERM, on_term)
    base = [sys.executable, "-u", os.path.abspath(__file__), *child_args]
    free = list(range(1, a.workers + 1)); running = {}; failed = []
    try:
        while jobs or running:
            for slot, (proc, job, fh, t0) in list(running.items()):
                timed_out = a.job_timeout and proc.poll() is None and time.time() - t0 > a.job_timeout
                if timed_out:
                    proc.kill(); proc.wait(); stop_instance(slot)
                if proc.poll() is not None:
                    fh.close(); del running[slot]; free.append(slot)
                    rc = "timeout" if timed_out else proc.returncode
                    print(f"=== {job[0]} {job[1]} end   {time.strftime('%H:%M:%S')} instance={slot} rc={rc}", flush=True)
                    if rc != 0:
                        failed.append(job)
            while jobs and free:
                slot = free[0]
                stop_instance(slot)   # a finished job's DF stays up until the next reset; don't count it as used
                avail = mem_available_mb()
                if avail < a.min_free_mb:
                    if not running:
                        raise RuntimeError(f"MemAvailable {avail} MB < --min-free-mb {a.min_free_mb} with nothing running")
                    break
                free.pop(0); job = jobs.pop(0)
                fh = open(os.path.join(a.out, f"{job[0]}-{job[1]}.stdout"), "w")
                proc = subprocess.Popen(base + ["--instance", str(slot), "--job", f"{job[0]}:{job[1]}"],
                                        stdout=fh, stderr=subprocess.STDOUT)
                running[slot] = (proc, job, fh, time.time())
                print(f"=== {job[0]} {job[1]} start {time.strftime('%H:%M:%S')} instance={slot} mem_avail={avail}MB", flush=True)
                if jobs:
                    time.sleep(a.stagger)   # stagger DF launches: each load spikes CPU and RSS
            time.sleep(5)
    finally:
        for proc, job, fh, _ in running.values():
            proc.terminate()
        for proc, job, fh, _ in running.values():
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait()
            fh.close()
        for slot in range(1, a.workers + 1):   # leave no DF instances running (~750 MB each)
            stop_instance(slot)
    return failed

def reset():
    env = dict(os.environ)
    if SCENARIO and SCENARIO.get("snapshot"):
        env["SNAPSHOT"] = SCENARIO["snapshot"]
    out = subprocess.run([os.path.join(H.DFP, "reset_fort.sh")], capture_output=True,
                         text=True, timeout=1800, env=env).stdout.strip()
    if "READY" not in out:
        raise RuntimeError("reset failed: " + out[-300:])

def daily_metrics(start, dump_path=None):
    """From recorder.lua's once-per-day samples and announcement counts: dynamics and failure events the
    per-decision log can miss. Writes the full timeline to dump_path if given."""
    rec = lua_json("recorder.lua", "dump")
    if dump_path:
        with open(dump_path, "w") as f:
            json.dump(rec, f)
    samples = [x for x in rec.get("samples") or [] if x["abs_tick"] >= start]
    events = rec.get("events") or {}
    if isinstance(events, list):        # empty Lua table encodes as []
        events = {}
    dry = [x for x in samples if x["drink"] <= 0]
    return {"days_sampled": len(samples),
            "peak_stressed": max((x.get("stressed", 0) for x in samples), default=0),
            "days_any_stressed": sum(x.get("stressed", 0) > 0 for x in samples),
            "days_hostiles_visible": sum(x.get("hostiles", 0) > 0 for x in samples),
            "peak_hostiles": max((x.get("hostiles", 0) for x in samples), default=0),
            "events": {t: {"n": e["n"], "first_day": (e["first_tick"] - start) // DAY} for t, e in events.items()},
            "days_drink_positive": sum(x["drink"] > 0 for x in samples),
            "first_day_drink_zero": (dry[0]["abs_tick"] - start) // DAY if dry else None,
            "days_food_positive": sum(x["food"] > 0 for x in samples),
            "citizen_days": sum(x["citizens"] for x in samples)}

# order-creating automation (credit.lua): if any is already on when a run starts (a snapshot), orders created while
# time runs can't be told apart from the arm's, so none of them are credited. Plugins, and `repeat` jobs that queue orders.
ORDER_PLUGINS = ("tailor", "autoclothing", "autoslab", "stockflow", "workflow", "autobutcher")
REPEAT_NOT_ORDERS = ("control-panel/fix/", "orders-sort", "cleanowned", "prioritize")

def ambient_automation():
    on = re.findall(r"^\s*([\w/-]+):\s+on\b", H.dfhack("enable"), re.M)
    reps = [l.strip() for l in H.dfhack("repeat", "--list").splitlines() if l.strip()]
    return sorted({p for p in on if p in ORDER_PLUGINS} | {r for r in reps if not r.startswith(REPEAT_NOT_ORDERS)})

def credit_start():
    """Start credit.lua (agent-credited production). Call after the scenario setup: the setup is not the arm's."""
    amb = ambient_automation()
    return lua_json("credit.lua", "start", ",".join(amb))

def snapshot(outdir, name):
    """quicksave, then copy the save folder it wrote. quicksave rotates through save/autosave 1..3, so find the
    folder whose world.sav changed (copying a fixed folder silently snapshots a stale save)."""
    save = os.path.join(H.DF, "save")
    def stamps():
        out = {}
        for d in os.listdir(save):
            w = os.path.join(save, d, "world.sav")
            if d not in ("current", "region1") and os.path.exists(w):
                out[d] = (os.path.getmtime(w), os.path.getsize(w))
        return out
    before = stamps()
    H.dfhack("quicksave")
    src, t0 = None, time.time()
    while time.time() - t0 < H.DFHACK_TIMEOUT:
        time.sleep(2)
        changed = [d for d, st in stamps().items() if before.get(d) != st]
        if changed:
            d = max(changed, key=lambda d: stamps()[d][0])
            first = stamps()[d]
            time.sleep(3)
            if stamps().get(d) == first:      # finished writing
                src = os.path.join(save, d); break
    if src is None:
        raise RuntimeError("quicksave wrote no save folder")
    dst = os.path.join(outdir, "snapshots", name)
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    s = score()
    with open(os.path.join(dst, "SNAPSHOT.json"), "w") as f:
        json.dump({"abs_tick": s["abs_tick"], "citizens": s["citizens"], "source": name,
                   "save_folder": os.path.basename(src)}, f)
    return dst

def run_one(arm, k, outdir, cap, model, seed, days=336, snapshot_days=()):
    global ADVANCE_STOP
    if arm == "dfai":
        dfai_install_config()
    reset()
    lua_json("recorder.lua", "start")
    H2.reset_tracking()   # diagnose()'s order ages: order ids repeat across runs from the same save
    policy = {"scripted": policies.Scripted, "random": policies.Random, "automation": policies.Automation}.get(arm)
    policy = policy(seed + k) if policy else None
    log = open(os.path.join(outdir, f"{arm}-{k}.jsonl"), "w")
    store = PL.Store(os.path.join(outdir, "prompts"))   # exact requests and responses (bench/prompts.py)
    s0 = score(); start = s0["abs_tick"]; end = start + days * DAY   # baselines: before the scenario setup
    ho_tick = hands_off_tick(SCENARIO, start, days)   # hands-off window: from here no arm is asked for decisions
    peak = s0["citizens"]; min_food = s0["food"]; min_drink = s0["drink"]
    watch = loopwatch.LoopWatch(start)   # loop/stuck flags, every arm (telemetry only unless LOOP_NOTES)
    INTERRUPTIONS.clear(); INTERRUPTION_LOG.clear()
    rl0 = H.RATE_LIMIT_WAITS
    stats = {"interruptions": 0, "length_retries": 0, "rate_limit_waits": 0, "no_tool_call": 0, "decisions": 0, "rejected": 0, "forced_adv": 0, "api_errors": 0, "stalls": 0, "context_trims": 0,
             "tools": {}, "tripwire_stops": {}, "prompt_tok": 0, "completion_tok": 0, "cap_hit_day": None, "providers": {},
             "hands_off_advances": 0}
    t_wall = time.time(); crashed = None
    wagon = H.dfhack("lua", "for _,b in ipairs(df.global.world.buildings.all) do "
                     "if df.building_wagonst:is_instance(b) then print(b.centerx,b.centery,b.z) end end")
    messages = [{"role": "system", "content": H.SYSTEM}]
    idle_streak = api_streak = 0
    action_log = []   # recent_actions for the v2 observation
    snaps = sorted(snapshot_days)
    setup_out = []
    dfai = {}
    last_s = s0
    try:
        for cmd in (SCENARIO or {}).get("setup", []):   # after the recorder starts, so injected events are counted
            cmd = [os.path.join(H.DFP, c) if c.startswith("scenarios/") else c for c in cmd]
            r = subprocess.run(["./dfhack-run", *cmd], cwd=H.DF, capture_output=True, text=True,
                               timeout=H.DFHACK_TIMEOUT, errors="replace")
            out = H.ANSI.sub("", r.stdout + r.stderr).strip()
            setup_out.append(out[-200:])
            # a scenario without its setup is a different scenario: fail loudly, don't score it. `lua` exits 0 even when
            # the script raises (error() or qerror()), so also look for a traceback or a "lua: " error line
            lua_failed = cmd[0] == "lua" and ("stack traceback" in out or re.search(r"^lua: ", out, re.M))
            if r.returncode != 0 or lua_failed:
                raise RuntimeError(f"scenario setup failed (rc={r.returncode}): {cmd}: {out[-200:]}")
        credit_start()
        if arm == "dfai":
            dfai.update(dfai_enable())
            dfai["config"] = json.load(open(DFAI_CONFIG))
        while True:
            s = score(); last_s = s
            if snaps and s["abs_tick"] - start >= snaps[0] * DAY:
                snapshot(outdir, f"{arm}-{k}-d{snaps.pop(0)}")
            ADVANCE_STOP = start + snaps[0] * DAY if snaps else None
            if ho_tick is not None and s["abs_tick"] < ho_tick:   # no advance runs past day A: W is the same length for every arm
                ADVANCE_STOP = ho_tick if ADVANCE_STOP is None else min(ADVANCE_STOP, ho_tick)
            peak = max(peak, s["citizens"]); min_food = min(min_food, s["food"]); min_drink = min(min_drink, s["drink"])
            if s["abs_tick"] >= end or s["citizens"] == 0:
                break
            rec = {"t": time.time(), "abs_tick": s["abs_tick"], "pop": s["citizens"],
                   "wealth": s["wealth_created"], "credited": s.get("credited_value"), "food": s["food"], "drink": s["drink"]}
            hands_off = ho_tick is not None and s["abs_tick"] >= ho_tick
            if hands_off:
                rec["phase"] = "hands_off"
            if arm == "noop" or (hands_off and arm != "dfai"):
                # noop, and every tool-API arm in the hands-off window: no observation, no decision, 7 days at a
                # time (dfai plays inside DF and can't be paused without re-planning, so it is exempt)
                moved = advance(min(7 * DAY, end - s["abs_tick"]))
                rec["advanced"] = moved
                stats["stalls"] += moved == 0
                stats["hands_off_advances"] += hands_off
            elif arm == "dfai":
                moved = dfai_advance(min(7 * DAY, end - s["abs_tick"]))
                rec["advanced"] = moved
                stats["stalls"] += moved == 0
            elif arm in V2_ARMS:
                if stats["decisions"] >= cap:
                    if stats["cap_hit_day"] is None:
                        stats["cap_hit_day"] = (s["abs_tick"] - start) // DAY
                    rec["advanced_post_cap"] = advance(min(7 * DAY, end - s["abs_tick"]))
                else:
                    obs = H2.observe()
                    obs["days_left_in_run"] = (end - s["abs_tick"]) // DAY
                    if ho_tick is not None:
                        obs["hands_off_in_days"] = hands_off_in_days(s["abs_tick"], ho_tick)
                    if ACTION_LOG and action_log:   # what this agent did lately, so the history window can be short
                        obs["recent_actions"] = action_log[-ACTION_LOG:]
                    if INTERRUPTIONS:   # popups that blocked time since the last turn: the agent should know
                        obs["interruptions"] = INTERRUPTIONS[:]; rec["interruptions"] = INTERRUPTIONS[:]
                        INTERRUPTIONS.clear()
                    obs.update(task_obs(SCENARIO, days))
                    stats["decisions"] += 1
                    if arm == "model2":
                        if messages[0]["content"] != H2.MANUAL:
                            messages = [{"role": "system", "content": H2.MANUAL}]
                        messages.append({"role": "user", "content": H2.obs_text(obs)})
                        messages = H2.window(messages, HISTORY)   # history policy: older observations stubbed (1.6)
                        try:
                            rec["prompt_ref"] = store.request(model, messages, H2.TOOLS, {**H2.CHAT_EXTRA, "seed": seed})
                            try:
                                resp = H.chat(model, messages, seed, tools=H2.TOOLS, extra=H2.CHAT_EXTRA)
                            except Exception as e:
                                if not (CONTEXT_ERROR.search(str(e)) and len(messages) > 2):
                                    raise
                                messages = [messages[0], messages[-1]]   # over the context window: drop the history
                                stats["context_trims"] += 1; rec["context_trim"] = str(e)[:200]
                                rec["prompt_ref"] = store.request(model, messages, H2.TOOLS, {**H2.CHAT_EXTRA, "seed": seed})
                                resp = H.chat(model, messages, seed, tools=H2.TOOLS, extra=H2.CHAT_EXTRA)
                        except Exception as e:
                            stats["api_errors"] += 1; rec["api_error"] = str(e)[:300]
                            api_streak += 1
                            if api_streak >= MAX_API_STREAK:   # don't let time pass with no agent: that's a different arm
                                raise RuntimeError(f"model API failing ({api_streak} in a row): {e}")
                            messages.pop(); rec["advanced"] = advance(DAY)
                            log.write(json.dumps(rec) + "\n"); continue
                        api_streak = 0
                        u = resp.get("usage") or {}
                        stats["prompt_tok"] += u.get("prompt_tokens", 0); stats["completion_tok"] += u.get("completion_tokens", 0)
                        prov = str(resp.get("provider")); stats["providers"][prov] = stats["providers"].get(prov, 0) + 1
                        rec["provider"] = prov
                        rec["finish_reason"] = resp["choices"][0].get("finish_reason")
                        rec["prompt_tokens"] = u.get("prompt_tokens"); rec["completion_tokens"] = u.get("completion_tokens")
                        rec["reasoning_tokens"] = (u.get("completion_tokens_details") or {}).get("reasoning_tokens")
                        msg = resp["choices"][0]["message"]
                        rec["response_ref"] = store.put(msg)
                        if not msg.get("tool_calls") and rec["finish_reason"] == "length":
                            # ran out of output tokens before calling a tool (issue #6): one retry with a nudge,
                            # instead of silently dropping the turn and letting the harness advance
                            stats["length_retries"] += 1
                            nudge = messages + [{"role": "user", "content": "Your previous reply ran out of output "
                                                 "tokens before calling a tool. Think briefly and call exactly one tool now."}]
                            try:
                                rec["retry_prompt_ref"] = store.request(model, nudge, H2.TOOLS, {**H2.CHAT_EXTRA, "seed": seed})
                                resp = H.chat(model, nudge, seed, tools=H2.TOOLS, extra=H2.CHAT_EXTRA)
                                u2 = resp.get("usage") or {}
                                stats["prompt_tok"] += u2.get("prompt_tokens", 0); stats["completion_tok"] += u2.get("completion_tokens", 0)
                                msg = resp["choices"][0]["message"]
                                rec["retry_response_ref"] = store.put(msg)
                                rec["retry_finish_reason"] = resp["choices"][0].get("finish_reason")
                            except Exception as e:
                                rec["retry_error"] = str(e)[:200]
                        calls = [(c["id"], c["function"]["name"], c["function"].get("arguments") or "{}")
                                 for c in msg.get("tool_calls") or []]
                        messages.append({k2: msg[k2] for k2 in ("role", "content", "tool_calls") if k2 in msg})
                        if not calls:
                            messages.pop(); stats["no_tool_call"] += 1
                            rec["no_tool_call"] = resp["choices"][0].get("finish_reason")
                    else:
                        name, pargs = policy(obs)
                        calls = [(None, name, json.dumps(pargs))]
                        if hasattr(policy, "drain"):         # automation: DFHack commands it ran itself
                            rec["automation"] = policy.drain()
                    advanced = False
                    for cid, name, raw_args in calls[:1]:
                        stats["tools"][name] = stats["tools"].get(name, 0) + 1
                        try:
                            args = json.loads(raw_args)
                        except ValueError:
                            args = None
                        if name == "advance_days" and isinstance(args, dict):
                            try:
                                ndays = H._int(args, "days", 1, H2.MAX_DAYS)
                                moved = advance(min(ndays * DAY, end - s["abs_tick"]))
                                result, err = f"advanced {moved} ticks" + stop_note(), False; advanced = True
                                if LAST_STOP: rec["stopped_because"] = dict(LAST_STOP)
                                stats["stalls"] += moved == 0
                            except H.Rejected as e:
                                result, err = H2._err("bad_arguments", str(e), hint=f"days is 1-{H2.MAX_DAYS}"), True
                        else:
                            result, err = H2.act(name, args)
                        stats["rejected"] += err
                        rec["call"] = {"tool": name, "args": raw_args, "result": result[:400], "error": err}
                        action_log.append(_log_entry(s["abs_tick"] - start, name, raw_args, result, err))
                        if cid is not None:
                            messages.append({"role": "tool", "tool_call_id": cid, "content": result})
                    for cid, _, _ in calls[1:]:
                        messages.append({"role": "tool", "tool_call_id": cid,
                                         "content": H2._err("one_tool_per_turn", "not run: one tool call per turn")})
                    idle_streak = 0 if advanced else idle_streak + 1
                    if idle_streak >= FORCE_AFTER:
                        rec["forced_advance"] = advance(DAY); stats["forced_adv"] += 1; idle_streak = 0
            else:
                if stats["decisions"] >= cap:
                    if stats["cap_hit_day"] is None:
                        stats["cap_hit_day"] = (s["abs_tick"] - start) // DAY
                    moved = advance(min(7 * DAY, end - s["abs_tick"]))   # cap hit: finish the year with no actions
                    rec["advanced_post_cap"] = moved
                else:
                    obs = H.observe(); obs["wagon_xyz"] = wagon
                    obs["days_left_in_run"] = (end - s["abs_tick"]) // DAY
                    if ho_tick is not None:
                        obs["hands_off_in_days"] = hands_off_in_days(s["abs_tick"], ho_tick)
                    if INTERRUPTIONS:   # popups that blocked time since the last turn: the agent should know
                        obs["interruptions"] = INTERRUPTIONS[:]; rec["interruptions"] = INTERRUPTIONS[:]
                        INTERRUPTIONS.clear()
                    obs.update(task_obs(SCENARIO, days))
                    messages.append({"role": "user", "content": "OBSERVATION " + json.dumps(obs)})
                    messages = messages[:1] + messages[1:][-12:]
                    while messages[1]["role"] == "tool":
                        messages.pop(1)
                    stats["decisions"] += 1
                    try:
                        resp = H.chat(model, messages, seed)
                    except Exception as e:
                        stats["api_errors"] += 1; rec["api_error"] = str(e)[:300]
                        api_streak += 1
                        if api_streak >= MAX_API_STREAK:
                            raise RuntimeError(f"model API failing ({api_streak} in a row): {e}")
                        messages.pop()
                        rec["advanced"] = advance(DAY); log.write(json.dumps(rec) + "\n"); continue
                    api_streak = 0
                    u = resp.get("usage") or {}
                    stats["prompt_tok"] += u.get("prompt_tokens", 0); stats["completion_tok"] += u.get("completion_tokens", 0)
                    msg = resp["choices"][0]["message"]; calls = msg.get("tool_calls") or []
                    messages.append({k2: msg[k2] for k2 in ("role", "content", "tool_calls") if k2 in msg})
                    advanced = False
                    for c in calls[:1]:
                        name = c["function"]["name"]
                        stats["tools"][name] = stats["tools"].get(name, 0) + 1
                        try:
                            plan = H.validate(name, json.loads(c["function"].get("arguments") or "{}"))
                            if plan and plan[0][0] == "advance":
                                moved = advance(min(plan[0][1], end - s["abs_tick"]))
                                result = f"advanced {moved} ticks" + stop_note(); advanced = True
                                stats["stalls"] += moved == 0
                            else:
                                result = H.act(plan)
                                stats["rejected"] += "ERROR: " in result
                        except (H.Rejected, ValueError) as e:
                            result = f"REJECTED: {e}"; stats["rejected"] += 1
                        rec["call"] = {"tool": name, "args": c["function"].get("arguments"), "result": result[:300]}
                        messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})
                    for c in calls[1:]:
                        messages.append({"role": "tool", "tool_call_id": c["id"], "content": "REJECTED: one tool per turn"})
                    if not calls:
                        messages.pop()   # drop an empty assistant turn
                    idle_streak = 0 if advanced else idle_streak + 1
                    if idle_streak >= FORCE_AFTER:
                        rec["forced_advance"] = advance(DAY); stats["forced_adv"] += 1; idle_streak = 0
            flags = watch.step(rec)
            if flags:
                rec["loop_flags"] = [kind for kind, _ in flags]
                if LOOP_NOTES and arm == "model2" and messages[-1]["role"] == "tool":
                    messages[-1]["content"] += "\n" + "\n".join(note for _, note in flags)
                    rec["loop_notes"] = True
            if LAST_STOP:   # any arm's advance that a tripwire stopped (noop, forced, post-cap included)
                rec.setdefault("stopped_because", dict(LAST_STOP))
                r_ = LAST_STOP.get("reason", "?").split(":")[0]
                stats["tripwire_stops"][r_] = stats["tripwire_stops"].get(r_, 0) + 1
                LAST_STOP.clear()
            log.write(json.dumps(rec) + "\n"); log.flush()
            if stats["stalls"] > 20:
                raise RuntimeError("time stopped advancing (20 stalls)")
    except Exception as e:
        crashed = f"{type(e).__name__}: {e}"[:300]
        if arm == "dfai" and not isinstance(e, DFCrash) and not df_alive():
            e = DFCrash(str(e))
        if isinstance(e, DFCrash):
            dfai["df_crashed"] = True
    stats["rate_limit_waits"] = H.RATE_LIMIT_WAITS - rl0
    stats["interruptions"] = len(INTERRUPTION_LOG)
    stats["interruption_log"] = [{"day": (x["tick"] - start) // DAY if x["tick"] else None, "focus": x["focus"],
                                  "text": x["text"][:160]} for x in INTERRUPTION_LOG[:20]]
    sf, daily, credit = {}, {}, {}
    global CALL_TIMEOUT
    hung = bool(crashed) and crashed.startswith(("DFCrash", "TimeoutExpired"))
    if hung:   # v2.1.1: DF stopped answering: final reads get POLL_TIMEOUT each instead of 600 s
        CALL_TIMEOUT = POLL_TIMEOUT
    if arm == "dfai" and not dfai.get("df_crashed"):
        try:   # df-ai's own status, before the final score (the game may still be running)
            dfai["status"] = H.dfhack("ai")[-6000:]
        except Exception as e:
            dfai["status"] = f"ai status failed: {e}"
    try:
        sf = score()
        daily = daily_metrics(start, os.path.join(outdir, f"{arm}-{k}.daily.json"))
        credit = lua_json("credit.lua", "dump", "items")
        with open(os.path.join(outdir, f"{arm}-{k}.credit.json"), "w") as f:
            json.dump(credit, f)
    except Exception as e:
        crashed = crashed or f"final score failed: {e}"
        if arm == "dfai" and not df_alive():
            dfai["df_crashed"] = True
        if hung or dfai.get("df_crashed"):
            sf = sf or last_s    # the last sample before the crash, so days_played shows how far it got
    CALL_TIMEOUT = None
    if arm == "dfai":
        try:
            log = os.path.join(H.DF, "df-ai.log")
            if os.path.exists(log):
                counts, tail = {name: 0 for name in DFAI_LOG_EVENTS}, []
                with open(log, errors="replace") as f:
                    for line in f:
                        for name, pat in DFAI_LOG_EVENTS.items():
                            counts[name] += pat in line
                        tail.append(line)
                        if len(tail) > 6000:
                            del tail[:3000]
                dfai["log_counts"] = counts   # how often each audited behaviour fired (research/df-ai-fairness-audit.md)
                with open(os.path.join(outdir, f"{arm}-{k}.dfai.log"), "w") as f:
                    f.writelines(tail[-3000:])
            if dfai.get("df_crashed"):
                with open(os.path.join(H.DFP, "df_run.log"), errors="replace") as f:
                    dfai["df_run_log_tail"] = f.read()[-1500:]
        except OSError:
            pass
    played = ((sf.get("abs_tick") or start) - start) / DAY
    def causes(sc):
        c = sc.get("citizen_death_causes") or {}
        return {} if isinstance(c, list) else c   # json.encode writes an empty Lua table as []
    # incidents persist in the save, so a mid-game snapshot already carries earlier deaths: count only this run's
    start_causes = causes(s0)
    deaths = {k: v - start_causes.get(k, 0) for k, v in causes(sf).items() if v - start_causes.get(k, 0) > 0}
    o0 = s0.get("other_death_causes") or {}
    o0 = {} if isinstance(o0, list) else o0
    other_deaths = sf.get("other_death_causes") or {}
    other_deaths = {} if isinstance(other_deaths, list) else other_deaths
    other_deaths = {k: v - o0.get(k, 0) for k, v in other_deaths.items() if v - o0.get(k, 0) > 0}
    thefts = [t for t in (sf.get("thefts") or []) if isinstance(t, dict) and t.get("tick", -1) >= start]
    if sf:   # F0 / F (BENCHMARK-v1 §3.7): the full score.lua output at the start and the end, for rescoring
        with open(os.path.join(outdir, f"{arm}-{k}.final.json"), "w") as f:
            json.dump({"F0": s0, "F": sf}, f)
    summary = {"arm": arm, "k": k, "crashed": crashed, "wall_s": round(time.time() - t_wall),
               "scenario": SCENARIO["name"] if SCENARIO else None,
               "scenario_metrics": SCENARIO.get("metrics") if SCENARIO else None, "scenario_setup": setup_out,
               "days_played": round(played, 1), "days_target": days,
               "hands_off_from_day": (ho_tick - start) // DAY if ho_tick is not None else None,
               "survived_year": played >= 336 and sf.get("citizens", 0) > 0,
               "survived_horizon": played >= days and sf.get("citizens", 0) > 0,
               "pop_start": s0["citizens"], "pop_peak": peak, "pop_final": sf.get("citizens"),
               "wealth_created_start": s0["wealth_created"], "wealth_created_final": sf.get("wealth_created"),
               "wealth_total_final": sf.get("wealth_total"),
               "wealth_crafted_final": sf.get("wealth_crafted"), "wealth_logs_final": sf.get("wealth_logs"),
               "wealth_by_category_final": sf.get("wealth_by_category"),
               # agent-credited production (credit.lua, research/credited-production.md)
               "produced_value_final": credit.get("produced"), "credited_value_final": credit.get("credited"),
               "produced_by_category_final": credit.get("produced_by_category"),
               "credited_by_category_final": credit.get("credited_by_category"),
               "placed_value_final": credit.get("placed_value"), "raw_value_final": credit.get("raw_value"),
               "credit_meta": credit.get("meta"),
               "food_min": min_food, "drink_min": min_drink, "food_final": sf.get("food"), "drink_final": sf.get("drink"),
               "food_positive": min(min_food, sf.get("food", 0) or 0) > 0,
               "citizen_deaths": (sf["citizen_deaths"] - s0.get("citizen_deaths", 0)) if "citizen_deaths" in sf else None,
               "citizen_deaths_before_start": s0.get("citizen_deaths", 0),
               "starvation_or_thirst_deaths": deaths.get("HUNGER", 0) + deaths.get("THIRST", 0),
               "citizen_death_causes": deaths, "other_death_causes": other_deaths,
               "invaders_killed": sf.get("invaders_killed"), "invaders_alive_final": sf.get("invaders_alive"),
               # LT06: thefts from this fort during the run (ITEM_STOLEN history events), and thief units
               "thefts": len(thefts), "theft_items": [t.get("item_type") for t in thefts],
               "thief_held_items_final": sf.get("thief_held_items"), "thieves_on_map_final": sf.get("thieves_on_map"),
               "thieves_caged_final": sf.get("thieves_caged"),
               "thieves_killed": (sf["thieves_dead"] - s0.get("thieves_dead", 0)) if "thieves_dead" in sf else None,
               "loops": watch.summary(), "loop_notes": LOOP_NOTES and arm == "model2",
               "history": HISTORY if arm == "model2" else None, "old_obs": H2.OLD_OBS if arm == "model2" else None, "action_log": ACTION_LOG if arm in V2_ARMS else None,
               **daily, **stats, "model": model if arm.startswith("model") else None, "provider_pin": H.PROVIDER,
               "endpoint": H.endpoint_label() if arm.startswith("model") else None,
               "dropped_request_fields": sorted(H.DROPPED_FIELDS) if arm.startswith("model") else None,
               "thinking": H.thinking_label() if arm.startswith("model") else None}
    if arm == "dfai":
        summary["df_crashed"] = bool(dfai.pop("df_crashed", False))
        summary["dfai"] = dfai
    summary["instance"] = H.INSTANCE
    append_line(os.path.join(outdir, "summary.jsonl"), json.dumps(summary))
    print(json.dumps(summary), flush=True)
    return summary

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--k-start", type=int, default=0, help="first run index (docker/batch.sh runs one k per container)")
    p.add_argument("--out", default=os.path.join(H.DFP, "runs", "smoke5"))
    p.add_argument("--decision-cap", type=int, default=500)
    p.add_argument("--model", default="z-ai/glm-5.3-flash")
    p.add_argument("--seed", type=int, default=12345)
    p.add_argument("--only", choices=["model", "noop", *V2_ARMS, *OTHER_ARMS])
    p.add_argument("--arms", default="model,noop")
    p.add_argument("--provider", help="pin one OpenRouter provider (no fallbacks)")
    p.add_argument("--history", type=int, default=12, help="model2: messages kept after the system prompt, the new "
                   "observation included (12 = the original window; 3 = the last call and result plus the observation)")
    p.add_argument("--old-obs", choices=["stub", "full"], default="stub", help="model2: older observations in the "
                   "history window become a one-line stub (default), or stay whole (the pre-2026-10-10 policy)")
    p.add_argument("--action-log", type=int, default=8, help="recent_actions entries in the observation (0 = none)")
    p.add_argument("--ablate", default="", help="model2 scaffolding ablations, comma list of manual, hints, sites "
                   "(bench/ablate.py; a different arm, recorded in the key). Default: none")
    p.add_argument("--loop-notes", action="store_true", help="append a HARNESS NOTE to model2's tool result when "
                   "loopwatch flags a loop (a different arm: compare against runs without it)")
    p.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL"),
                   help="OpenAI-compatible endpoint instead of OpenRouter, e.g. http://host.docker.internal:8000/v1 "
                        "(oMLX or mlx_lm.server on the Docker host); key from $LLM_API_KEY. Default $LLM_BASE_URL")
    p.add_argument("--thinking", choices=["on", "off"], help="--base-url endpoints only: hybrid-thinking models "
                   "(Qwen3) get chat_template_kwargs.enable_thinking (default off = the fixed track's low effort). "
                   "OpenRouter requests always use reasoning.effort=low")
    p.add_argument("--days", type=int, help="in-game days per run (default: the scenario's, else 336 = one year)")
    p.add_argument("--scenario", help="scenarios/<name>.json: start snapshot, setup, horizon, brief, metrics")
    p.add_argument("--snapshot-days", default="", help="comma list of days at which to quicksave and copy the fort "
                                                         "to <out>/snapshots/ (e.g. 336,672)")
    p.add_argument("--dfai-config", help="df-ai.json for the dfai arm (default docker/dfai/df-ai.json, the fair config)")
    p.add_argument("--instance", type=int, default=None,
                   help="DF instance to drive (0 = ./df on port 5000; N = instances/N/df on 5000+N). Default: $DF_INSTANCE or 0")
    p.add_argument("--workers", type=int, default=1, help="parallel DF instances, native Linux only (uses instances 1..W)")
    p.add_argument("--min-free-mb", type=int, default=1500, help="parallel: only start a job when MemAvailable >= this")
    p.add_argument("--stagger", type=int, default=30, help="parallel: seconds between job launches")
    p.add_argument("--job-timeout", type=int, default=0, help="parallel: kill a job after this many wall seconds (0 = none)")
    p.add_argument("--job", help=argparse.SUPPRESS)   # internal: run exactly one arm:k (used by --workers)
    p.add_argument("--require-split", help="refuse to run unless the scenario's split is this one (teacher and SFT "
                   "collection: --require-split train; scenarios without a split are test-public)")
    a = p.parse_args()
    if a.instance is not None:
        H.set_instance(a.instance)
    if a.dfai_config:
        DFAI_CONFIG = os.path.abspath(a.dfai_config)
    H.PROVIDER = a.provider
    LOOP_NOTES = a.loop_notes
    HISTORY = max(1, a.history); ACTION_LOG = max(0, a.action_log); H2.OLD_OBS = a.old_obs
    H.set_endpoint(a.base_url)
    if a.thinking and H.is_openrouter():
        sys.exit("--thinking applies to --base-url endpoints; OpenRouter requests use reasoning.effort=low")
    H.THINKING = a.thinking == "on"
    if a.scenario:
        SCENARIO = load_scenario(a.scenario)
    if a.require_split and split_of(SCENARIO) != a.require_split:
        sys.exit(f"--require-split {a.require_split}: scenario {a.scenario or '(default start-year)'} is split "
                 f"{split_of(SCENARIO)!r}; never collect training data on a test split")
    if a.days is None:
        a.days = (SCENARIO or {}).get("days", 336)
    os.makedirs(a.out, exist_ok=True)
    arms = [a.only] if a.only else a.arms.split(",")
    bad = set(arms) - {"model", "noop", *V2_ARMS, *OTHER_ARMS}
    if bad:
        sys.exit(f"unknown arm(s): {sorted(bad)}")
    snapshot_days = [int(x) for x in a.snapshot_days.split(",") if x]
    ablate = AB.parse(a.ablate)
    if ablate and set(arms) != {"model2"}:
        sys.exit("--ablate applies to the model2 arm only; run other arms in a separate batch")
    AB.apply(ablate)   # no-op without ablations: harness2 is left as it is
    if a.job:   # a --workers child: one run, no lock (the parent holds it), no resume check (the parent did it)
        arm, k = a.job.rsplit(":", 1)
        if SCENARIO:
            SCENARIO["setup"] = setup_for(SCENARIO, int(k))
        pick_snapshot(int(k), a.seed)
        s = run_one(arm, int(k), a.out, a.decision_cap, a.model, a.seed, a.days, snapshot_days)
        sys.exit(1 if s.get("crashed") else 0)
    if a.workers > 1 and os.path.exists("/.dockerenv") and not os.environ.get("SMOKE_WORKERS_IN_DOCKER"):  # set only to test
        sys.exit("--workers runs several DFs in one host; in Docker use one container per instance (docker/batch.sh)")
    lock = batch_lock(a.out)
    # comparability key (bench/key.py): refuse to resume into an out dir made by a different harness or task version
    BK.record_batch(a.out, BK.compute(a.scenario, a.decision_cap, a.days, a.history, a.action_log, ablate, a.old_obs),
                    {"arms": arms, "model": a.model, "provider_pin": a.provider, "seed": a.seed,
                     "chat_extra": H2.CHAT_EXTRA, "runs": a.runs, "k_start": a.k_start, "split": split_of(SCENARIO),
                     "endpoint": H.endpoint_label(), "thinking": H.thinking_label(),
                     **({"ablate": list(ablate)} if ablate else {})}, sys.argv[1:])
    done = done_jobs(a.out, SCENARIO["name"] if SCENARIO else None)
    jobs = []
    for k in range(a.k_start, a.k_start + a.runs):
        for arm in arms:
            if (arm, k) in done:
                print(f"=== {arm} {k} already done, skipping", flush=True)
            else:
                jobs.append((arm, k))
    if a.workers > 1:
        # everything a child needs to run the same batch; --instance and --job are added per job
        child_args = ["--out", a.out, "--decision-cap", str(a.decision_cap), "--model", a.model, "--seed", str(a.seed),
                      "--days", str(a.days), "--snapshot-days", a.snapshot_days, "--dfai-config", DFAI_CONFIG]
        if a.scenario:
            child_args += ["--scenario", a.scenario]
        if a.provider:
            child_args += ["--provider", a.provider]
        if a.loop_notes:
            child_args += ["--loop-notes"]
        if a.require_split:
            child_args += ["--require-split", a.require_split]
        child_args += ["--history", str(a.history), "--action-log", str(a.action_log), "--old-obs", a.old_obs]
        if ablate:
            child_args += ["--ablate", ",".join(ablate)]
        if a.base_url:
            child_args += ["--base-url", a.base_url]
        if a.thinking:
            child_args += ["--thinking", a.thinking]
        try:
            failed = run_parallel(a, jobs, child_args)
        except KeyboardInterrupt as e:   # Ctrl-C or SIGTERM: children and DFs are already stopped
            sys.exit(f"interrupted ({e or 'Ctrl-C'}): all jobs and DF instances stopped; re-run to resume")
        print(f"BATCH DONE failed={len(failed)} {failed if failed else ''}".rstrip(), flush=True)
        sys.exit(1 if failed else 0)
    for arm, k in jobs:
        print(f"=== {arm} {k} start {time.strftime('%H:%M:%S')} instance={H.INSTANCE}", flush=True)
        if SCENARIO:
            SCENARIO["setup"] = setup_for(SCENARIO, k)
        pick_snapshot(k, a.seed)
        run_one(arm, k, a.out, a.decision_cap, a.model, a.seed, a.days, snapshot_days)
    print("BATCH DONE", flush=True)
