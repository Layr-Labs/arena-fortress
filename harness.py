#!/usr/bin/env python3
"""Minimal DF fortress-mode LLM harness (phase 1; OpenRouter or any OpenAI-compatible endpoint).

observe -> decide -> act -> advance, logged as JSONL. stdlib only (urllib).
The model NEVER gets raw lua/dfhack commands: every tool call is validated
against ALLOWED_TOOLS and mapped to exactly one templated dfhack-run command.

usage: harness.py --decisions N [--model z-ai/glm-5.3-flash] [--log runs/x.jsonl]
       harness.py --selftest      (P7 allowlist checks, no model, no DF writes)
Requires DF+DFHack already running with a fortress loaded (see README in plan).
"""
import argparse, json, os, re, subprocess, sys, time, urllib.request

DFP = os.path.dirname(os.path.realpath(__file__))   # physical, like instance.sh
BASE_PORT = 5000

def set_instance(n):
    """Point this process (and every subprocess it starts) at DF instance n.
    0 = $DFP/df on port 5000 (original layout); n>=1 = $DFP/instances/n/df on port 5000+n.
    Mirrors instance.sh; reset_fort.sh/start_df.sh read DF_INSTANCE from the environment."""
    global INSTANCE, DF, BP_DIR
    INSTANCE = int(n)
    if INSTANCE < 0:
        raise ValueError("instance must be >= 0")
    DF = os.path.join(DFP, "df") if INSTANCE == 0 else os.path.join(DFP, "instances", str(INSTANCE), "df")
    BP_DIR = os.path.join(DF, "dfhack-config", "blueprints")
    os.environ["DF_INSTANCE"] = str(INSTANCE)
    os.environ["DFHACK_PORT"] = str(BASE_PORT + INSTANCE)

set_instance(os.environ.get("DF_INSTANCE") or 0)

# ---------------------------------------------------------------- dfhack I/O
# Seconds to wait for one dfhack-run call. DF answers between frames, so a starved or memory-pressured host
# (shared machine, emulation, a slow world update) can stall it for minutes; at 60 s every run of an 8-container
# batch in an 8 GB Docker VM crashed within 30 min. Waiting is safer than retrying: a timed-out command may
# still execute later (e.g. advancing time twice).
# v2.1.1: 180 s (was 600): no single RPC legitimately takes minutes, and a DF whose main thread is stuck made every
# call block 10 minutes (bake-off raid runs hung > 20 min with the advance's hang guard never firing)
DFHACK_TIMEOUT = int(os.environ.get("DFHACK_TIMEOUT", "180"))

def dfhack(*args, timeout=None, with_stderr=False):
    """stdout only by default: stderr noise (e.g. locale warnings) must never reach a parser.
    with_stderr=True appends it, for results shown to the model where DF/DFHack errors matter."""
    timeout = timeout or DFHACK_TIMEOUT
    r = subprocess.run(["./dfhack-run", *args], cwd=DF, capture_output=True,
                       text=True, timeout=timeout, errors="replace")
    out = r.stdout + ("\n" + r.stderr if with_stderr and r.stderr.strip() else "")
    return ANSI.sub("", out).strip()

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

def observe():
    raw = dfhack("lua", "-f", os.path.join(DFP, "observe.lua"))
    try:
        o = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except ValueError:
        return {"error": raw[-500:]}
    o["announcements_last5"] = [re.sub(r"\[[A-Z]:[^\]]*\]|\[B\]", "", a)[:240]
                                for a in o.get("announcements_last5", [])]
    return o

def wait_paused(max_s=120):
    t = time.time()
    while time.time() - t < max_s:
        if dfhack("lua", "print(df.global.pause_state)").strip() == "true":
            return True
        time.sleep(1)
    return False

# ---------------------------------------------------------------- allowlist
# Tool-facing name -> manager-order JSON DF accepts. Each spec was checked with `workorder` on DF 53.16:
# BrewDrink is not a manager job (brewing is a reaction), there is no ConstructBarrel job (it is MakeBarrel),
# furniture needs a material category, PrepareMeal needs a meal kind, and MakeTool needs an item subtype (dropped).
WOOD = ["wood"]
JOB_SPECS = {"ConstructBed": {"job": "ConstructBed", "material_category": WOOD},
             "ConstructDoor": {"job": "ConstructDoor", "material_category": WOOD},
             "ConstructTable": {"job": "ConstructTable", "material_category": WOOD},
             "ConstructThrone": {"job": "ConstructThrone", "material_category": WOOD},
             "ConstructChest": {"job": "ConstructChest", "material_category": WOOD},
             "ConstructBarrel": {"job": "MakeBarrel", "material_category": WOOD},
             "ConstructBin": {"job": "ConstructBin", "material_category": WOOD},
             "BrewDrink": {"job": "CustomReaction", "reaction": "BREW_DRINK_FROM_PLANT"},
             "PrepareMeal": {"job": "PrepareMeal", "mat_type": 4},
             "MakeCharcoal": {"job": "MakeCharcoal"}}
JOB_TYPES = set(JOB_SPECS)
AUTOMATION = {"autochop", "autofarm", "autolabor", "seedwatch", "autoclothing"}
MAX_DIM, MAX_DAYS = 15, 7

TOOLS = [
    {"type": "function", "function": {"name": "dig_room",
     "description": "Designate a rectangular room for digging on one z-level (must be reachable).",
     "parameters": {"type": "object", "required": ["x", "y", "z", "w", "h"], "properties": {
        "x": {"type": "integer"}, "y": {"type": "integer"}, "z": {"type": "integer"},
        "w": {"type": "integer", "minimum": 1, "maximum": MAX_DIM},
        "h": {"type": "integer", "minimum": 1, "maximum": MAX_DIM}}}}},
    {"type": "function", "function": {"name": "dig_stairs",
     "description": "Designate a staircase column at (x,y) from z_top down to z_bottom.",
     "parameters": {"type": "object", "required": ["x", "y", "z_top", "z_bottom"], "properties": {
        "x": {"type": "integer"}, "y": {"type": "integer"},
        "z_top": {"type": "integer"}, "z_bottom": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "add_work_order",
     "description": "Queue a manager work order.",
     "parameters": {"type": "object", "required": ["job", "amount"], "properties": {
        "job": {"type": "string", "enum": sorted(JOB_TYPES)},
        "amount": {"type": "integer", "minimum": 1, "maximum": 20}}}}},
    {"type": "function", "function": {"name": "enable_automation",
     "description": "Enable a DFHack fortress-management helper.",
     "parameters": {"type": "object", "required": ["name"], "properties": {
        "name": {"type": "string", "enum": sorted(AUTOMATION)}}}}},
    {"type": "function", "function": {"name": "advance_days",
     "description": "Let the game run for N in-game days, then pause and observe.",
     "parameters": {"type": "object", "required": ["days"], "properties": {
        "days": {"type": "integer", "minimum": 1, "maximum": MAX_DAYS}}}}},
]
ALLOWED_TOOLS = {t["function"]["name"] for t in TOOLS}

class Rejected(Exception):
    pass

def _int(a, k, lo=-10**6, hi=10**6):
    v = a.get(k)
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise Rejected(f"{k} must be an integer in [{lo},{hi}]")
    return v

def validate(name, args):
    """Return the exact argv list(s) to run, or raise Rejected. Pure function."""
    if name not in ALLOWED_TOOLS:
        raise Rejected(f"tool {name!r} not allowed")
    if not isinstance(args, dict):
        raise Rejected("arguments must be an object")
    extra = set(args) - set(next(t for t in TOOLS if t["function"]["name"] == name)
                            ["function"]["parameters"]["properties"])
    if extra:
        raise Rejected(f"unexpected arguments {sorted(extra)}")
    if name == "dig_room":
        x, y, z = _int(args, "x", 0, 400), _int(args, "y", 0, 400), _int(args, "z", 0, 300)
        w, h = _int(args, "w", 1, MAX_DIM), _int(args, "h", 1, MAX_DIM)
        rows = "\n".join(",".join(["d"] * w) for _ in range(h))
        return [("bp", f"#dig start(1;1)\n{rows}\n", f"{x},{y},{z}")]
    if name == "dig_stairs":
        x, y = _int(args, "x", 0, 400), _int(args, "y", 0, 400)
        zt, zb = _int(args, "z_top", 0, 300), _int(args, "z_bottom", 0, 300)
        if not 0 < zt - zb <= 20:
            raise Rejected("z_top must be 1..20 levels above z_bottom")
        out = [("bp", "#dig start(1;1)\nj\n", f"{x},{y},{zt}")]
        out += [("bp", "#dig start(1;1)\ni\n", f"{x},{y},{z}") for z in range(zt - 1, zb, -1)]
        out += [("bp", "#dig start(1;1)\nu\n", f"{x},{y},{zb}")]
        return out
    if name == "add_work_order":
        if args.get("job") not in JOB_TYPES:
            raise Rejected("job not in allowlist")
        amt = _int(args, "amount", 1, 20)
        return [("cmd", ["workorder", json.dumps(dict(JOB_SPECS[args["job"]], amount_total=amt))])]
    if name == "enable_automation":
        if args.get("name") not in AUTOMATION:
            raise Rejected("automation not in allowlist")
        return [("cmd", ["enable", args["name"]])]
    if name == "advance_days":
        return [("advance", _int(args, "days", 1, MAX_DAYS) * 1200)]
    raise Rejected("unreachable")

def act(plan):
    out = []
    for step in plan:
        if step[0] == "bp":
            path = os.path.join(BP_DIR, "harness_tmp.csv")
            with open(path, "w") as f:
                f.write(step[1])
            r = dfhack("quickfort", "run", "harness_tmp.csv", "-c", step[2])
            m = re.search(r"designated for digging: (\d+)", r)
            out.append(f"designated {m.group(1) if m else 0} tiles at {step[2]}")
        elif step[0] == "cmd":
            r = dfhack(*step[1], with_stderr=True)
            # a DF-side refusal is an error, not a normal-looking result
            failed = step[1][0] == "workorder" and not r.startswith("Queuing")
            out.append(("ERROR: " if failed else "") + r[-300:])
        elif step[0] == "advance":
            dfhack("lua", "-f", os.path.join(DFP, "advance.lua"), str(step[1]))
            out.append("advanced" if wait_paused() else "TIMEOUT waiting for pause")
    return "; ".join(out)

# ---------------------------------------------------------------- model
# Model endpoint. Default: OpenRouter. Any OpenAI-compatible server works too (oMLX, mlx_lm.server, vLLM, ...):
# smoke.py --base-url http://host.docker.internal:8000/v1 (from a container) or $LLM_BASE_URL. The key for a
# non-OpenRouter endpoint comes from $LLM_API_KEY (may be empty for servers without auth).
OPENROUTER_URL = "https://openrouter.ai/api/v1"
BASE_URL = os.environ.get("LLM_BASE_URL") or OPENROUTER_URL

def set_endpoint(base_url):
    global BASE_URL
    BASE_URL = (base_url or OPENROUTER_URL).rstrip("/")

def is_openrouter():
    return BASE_URL.rstrip("/") == OPENROUTER_URL

def endpoint_label():
    return "openrouter" if is_openrouter() else BASE_URL

def api_key():
    if not is_openrouter():
        return os.environ.get("LLM_API_KEY", "")
    k = os.environ.get("OPENROUTER_API_KEY")
    if k:
        return k
    env_file = os.path.expanduser("~/.config/yukon-df/.env")   # original author's setup; optional
    if os.path.exists(env_file):
        for line in open(env_file):
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"\'')
    sys.exit("no OPENROUTER_API_KEY: export it (docker run -e OPENROUTER_API_KEY ...)")

# Seconds per model call. Local servers can queue requests from several containers and prefill slowly.
CHAT_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "0")) or None   # None: 120 for OpenRouter, 900 otherwise

# Request fields only OpenRouter understands. Sent elsewhere, they are dropped (and logged in the step record by
# smoke.py via DROPPED_FIELDS), so a local run's model condition is explicit.
OPENROUTER_ONLY = ("provider", "reasoning")
DROPPED_FIELDS = set()

RATE_LIMIT_PATIENCE = 600   # seconds of 429 back-off per call before giving up
RATE_LIMIT_WAITS = 0        # cumulative 429 waits (smoke.py reports the per-run delta)

# Pin one OpenRouter backend (e.g. "z-ai"); None lets OpenRouter route, which varies the serving stack per call.
PROVIDER = None

# Hybrid-thinking open models (Qwen3 family) on a non-OpenRouter endpoint (oMLX, vLLM, mlx_lm.server): the request
# sets chat_template_kwargs.enable_thinking, off unless smoke.py --thinking on. The fixed track's reasoning effort
# is "low" (BENCHMARK-v1 §7 Q5); for these models, which have no effort levels, low = thinking off. OpenRouter
# requests are unchanged (reasoning.effort=low in harness2.CHAT_EXTRA). Model condition, not part of the key.
THINKING = False

def thinking_label():
    """The model condition for the run record: 'off'/'on' on local endpoints, None on OpenRouter (effort low)."""
    return None if is_openrouter() else ("on" if THINKING else "off")

def chat(model, messages, seed, tools=None, extra=None):
    req_body = dict({"model": model, "messages": messages, "tools": tools or TOOLS,
                     "tool_choice": "required", "temperature": 0, "seed": seed,
                     "max_tokens": 1500}, **(extra or {}))
    if PROVIDER:
        req_body["provider"] = {"order": [PROVIDER], "allow_fallbacks": False}
    if not is_openrouter():
        for f in OPENROUTER_ONLY:
            if req_body.pop(f, None) is not None:
                DROPPED_FIELDS.add(f)
        req_body.setdefault("chat_template_kwargs", {})["enable_thinking"] = bool(THINKING)
    body = json.dumps(req_body).encode()
    headers = {"Content-Type": "application/json"}
    key = api_key()
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(BASE_URL + "/chat/completions", body, headers)
    timeout = CHAT_TIMEOUT or (120 if is_openrouter() else 900)
    attempt = rl_waited = 0
    while True:
        try:
            resp = json.load(urllib.request.urlopen(req, timeout=timeout))
            if resp.get("choices"):
                return resp
            # an error inside a 200 body (Groq: "Failed to call a function"): retry like a transient failure,
            # then raise so the caller counts an API error instead of crashing on resp["choices"]
            err = RuntimeError(f"no choices: {json.dumps(resp.get('error') or resp)[:400]}")
        except urllib.error.HTTPError as e:
            # keep the provider's explanation: a bare "404" hid that the pinned provider (z-ai) doesn't
            # support tool_choice=required. Client errors other than rate limits won't fix themselves.
            err = RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:400]}")
            if e.code == 429 and rl_waited < RATE_LIMIT_PATIENCE:
                # rate limited (issue #7): wait as told and try again. The game is paused while we wait, so
                # no decisions are lost; waits are counted separately from errors.
                global RATE_LIMIT_WAITS
                RATE_LIMIT_WAITS += 1
                try:
                    wait = float(e.headers.get("Retry-After") or 0)
                except ValueError:
                    wait = 0
                wait = min(max(wait, 5 * 2 ** min(attempt, 4)), 120)
                rl_waited += wait; attempt += 1
                time.sleep(wait)
                continue
            if 400 <= e.code < 500:
                raise err
        except Exception as e:  # transient: network, timeout
            err = e
        attempt += 1
        if attempt >= 3:
            raise err
        time.sleep(2 * attempt)

SYSTEM = """You manage a Dwarf Fortress fortress through tools only. Goal: survive, grow
population and wealth, avoid starvation. Coordinates are map tiles (x,y,z); z increases
upward and the surface is around z=106. Rooms dug below the surface need a staircase
from the surface first. Do NOT dig at the wagon tile. Call exactly one tool per turn;
call advance_days to let time pass."""

def run(n, model, log_path, seed):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    log = open(log_path, "a")
    wagon = dfhack("lua", "for _,b in ipairs(df.global.world.buildings.all) do "
                   "if df.building_wagonst:is_instance(b) then print(b.centerx,b.centery,b.z) end end")
    messages = [{"role": "system", "content": SYSTEM}]
    usage = {"prompt": 0, "completion": 0}
    for i in range(n):
        obs = observe()
        obs["wagon_xyz"] = wagon
        messages.append({"role": "user", "content": "OBSERVATION " + json.dumps(obs)})
        messages = messages[:1] + messages[-12:]           # bounded context
        while messages[1]["role"] == "tool":               # never orphan a tool msg
            messages.pop(1)
        resp = chat(model, messages, seed)
        u = resp.get("usage") or {}
        usage["prompt"] += u.get("prompt_tokens", 0); usage["completion"] += u.get("completion_tokens", 0)
        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        messages.append({k: msg[k] for k in ("role", "content", "tool_calls") if k in msg})
        results = []
        for c in calls[:1]:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
                result = act(validate(name, args))
            except (Rejected, ValueError) as e:
                result = f"REJECTED: {e}"
            results.append({"tool": name, "args": c["function"].get("arguments"), "result": result})
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})
        for c in calls[1:]:
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": "REJECTED: one tool per turn"})
        rec = {"i": i, "ts": time.time(), "obs": obs, "calls": results,
               "fingerprint": resp.get("system_fingerprint"), "provider": resp.get("provider"),
               "usage": u}
        log.write(json.dumps(rec) + "\n"); log.flush()
        print(f"[{i}] y{obs.get('year')} t{obs.get('tick')} pop={obs.get('citizens')} "
              f"wealth={obs.get('wealth_created')} -> {results}")
    print("usage", usage)
    return usage

def selftest():
    bad = [("lua", {"code": "x"}), ("reveal", {}), ("dig_room", {"x": 1, "y": 1, "z": 1, "w": 99, "h": 1}),
           ("dig_room", {"x": "1;reveal", "y": 1, "z": 1, "w": 1, "h": 1}),
           ("dig_room", {"x": 1, "y": 1, "z": 1, "w": 1, "h": 1, "cmd": "fastdwarf 1"}),
           ("add_work_order", {"job": "fastdwarf", "amount": 1}),
           ("enable_automation", {"name": "fastdwarf"}), ("enable_automation", {"name": "reveal"}),
           ("advance_days", {"days": 500}), ("dig_stairs", {"x": 1, "y": 1, "z_top": 5, "z_bottom": 9}),
           ("dig_room", {"x": True, "y": 1, "z": 1, "w": 1, "h": 1})]
    good = [("dig_room", {"x": 1, "y": 1, "z": 1, "w": 3, "h": 3}), ("advance_days", {"days": 1}),
            ("add_work_order", {"job": "ConstructBed", "amount": 2}), ("enable_automation", {"name": "autochop"}),
            ("dig_stairs", {"x": 1, "y": 1, "z_top": 106, "z_bottom": 103})]
    fails = 0
    for n, a in bad:
        try:
            validate(n, a); print("FAIL accepted", n, a); fails += 1
        except Rejected as e:
            print("ok rejected", n, "-", e)
    for n, a in good:
        try:
            validate(n, a); print("ok accepted", n)
        except Rejected as e:
            print("FAIL rejected", n, a, e); fails += 1
    print("SELFTEST", "PASS" if not fails else f"FAIL ({fails})")
    return fails

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--decisions", type=int, default=5)
    p.add_argument("--model", default="z-ai/glm-5.3-flash")
    p.add_argument("--seed", type=int, default=12345)
    p.add_argument("--log", default=os.path.join(DFP, "runs", time.strftime("run-%Y%m%dT%H%M%S.jsonl")))
    p.add_argument("--selftest", action="store_true")
    a = p.parse_args()
    if a.selftest:
        sys.exit(1 if selftest() else 0)
    run(a.decisions, a.model, a.log, a.seed)
