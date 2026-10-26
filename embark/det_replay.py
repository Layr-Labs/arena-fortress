#!/usr/bin/env python3
"""Noop replay-divergence check (research/determinism.md): load the same start fort K times, advance it a day at a time
with nothing else touching the game, and fingerprint the state (embark/det_state.lua) and the RNG (embark/det_rng.lua)
after every day.

  python3 embark/det_replay.py --out FILE --label MODE [--k 3] [--days 28] [--reseed SEED] [--shim det_shim.so]
                               [--shim-mode count|fix] [--shim-seed N]

--reseed refills DF's main RNG buffer from SEED right after the load (before the first advance).
--shim preloads the shim into DF (DF_PRELOAD; dfhack's launcher already runs DF under `setarch -R`, so ASLR is off).
Writes one JSON line per replay: {label, k, load_rng, reseed_rng, days: [{day, state..., rng}], shim_counts}.
Compare replays with det_compare.py (or `--compare FILE...`, which prints the first divergent day per field).
"""
import argparse, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TPD = 1200   # ticks per day


def lua_json(*args):
    import harness as H
    raw = H.dfhack("lua", "-f", *args)
    return json.loads(raw[raw.index("{"):raw.rindex("}") + 1])


def replay(a, k):
    import smoke   # game-side imports only here, so --compare and det_summary.py run on any host
    import harness as H
    env = dict(os.environ)
    status = f"/tmp/det_status_{a.label}_{k}.json"
    if a.shim:
        env.update(DF_PRELOAD=a.shim, DET_MODE=a.shim_mode, DET_SEED=str(a.shim_seed), DET_STATUS=status,
                   DET_LOG=f"/tmp/det_log_{a.label}_{k}.jsonl")
        if a.trandom:
            env.update(DET_TRANDOM=a.trandom, DET_TRANDOM_LOG=f"/tmp/det_trandom_{a.label}_{k}.jsonl",
                       DET_UI_PAUSED="1" if a.ui_paused else "0", DET_UI_SITES=a.ui_sites or "")
        if a.pause_dump:
            os.makedirs(a.pause_dump, exist_ok=True)
            env["DET_PAUSE_DUMP"] = a.pause_dump
    if a.env:   # extra environment for DF (e.g. GLIBC_TUNABLES=glibc.malloc.perturb=165)
        env.update(kv.split("=", 1) for kv in a.env)
    if a.reseed_before_load is not None:   # reset_fort.sh reseeds DF's RNG just before it clicks the save
        env["DET_RESEED_BEFORE_LOAD"] = str(a.reseed_before_load)
    # stop the previous replay's DF and wait for its port to free (reset_fort.sh on main refuses a busy port)
    subprocess.run("pkill -9 -x dwarfort; for i in $(seq 1 40); do "
                   "(exec 3<>/dev/tcp/127.0.0.1/${DFHACK_PORT:-5000}) 2>/dev/null || exit 0; sleep 0.5; done",
                   shell=True, executable="/bin/bash")
    r = subprocess.run([os.path.join(ROOT, "reset_fort.sh")], capture_output=True, text=True, timeout=600, env=env)
    last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "NO OUTPUT"
    if not last.startswith("READY"):
        return {"label": a.label, "k": k, "error": last}
    row = {"label": a.label, "k": k, "ready": last, "load_rng": lua_json(os.path.join(ROOT, "embark/det_rng.lua"), "read")}
    if a.quiet_view:   # camera to empty sky and unit caches cleared, before anything else (embark/det_view.lua)
        row["view"] = lua_json(os.path.join(ROOT, "embark/det_view.lua"), "reset")
    if a.idle_paused:   # paused, nothing simulated (frames still run: lets frame-time work such as caches finish)
        import time
        time.sleep(a.idle_paused)
    for cmd in a.post_load or []:   # DFHack commands right after the load, e.g. "disable buildingplan"
        row.setdefault("post_load", []).append([cmd, H.dfhack(*cmd.split())[-300:]])
    if a.record_plugins:
        row["plug"] = H.dfhack("plug")[-4000:]
    row["day0"] = lua_json(os.path.join(ROOT, "embark/det_state.lua"))   # the loaded state, before any tick
    if a.deep:   # hidden unit state at load (every scalar reachable within 3 levels)
        row["deep0"] = lua_json(os.path.join(ROOT, "embark/det_deep.lua"))
    if a.addr:   # heap addresses of units, items, buildings at load
        row["addr0"] = lua_json(os.path.join(ROOT, "embark/det_addr.lua"))
    if a.reseed is not None:
        row["reseed_rng"] = lua_json(os.path.join(ROOT, "embark/det_rng.lua"), "seed", str(a.reseed))
    if a.tick_trace:   # one tick at a time: RNG and state after each, to find the first tick that differs
        import time
        trace = []
        for _ in range(a.tick_trace // a.trace_step):
            if a.quiet_view:
                lua_json(os.path.join(ROOT, "embark/det_view.lua"), "camera")
            H.dfhack("lua", "-f", os.path.join(ROOT, "advance.lua"), str(a.trace_step), "notrip")
            if a.trace_step > 1:
                time.sleep(a.trace_step / a.quiet_tps)
            for _w in range(400):
                if H.dfhack("lua", "print(df.global.pause_state)").strip().endswith("true"):
                    break
                time.sleep(0.05)
            r = lua_json(os.path.join(ROOT, "embark/det_rng.lua"), "read")
            s = lua_json(os.path.join(ROOT, "embark/det_state.lua"))
            trace.append({"tick": s["abs_tick"], "rng": r["buf0_fnv"], "index0": r["index0"], "all": r["all_fnv"],
                          "units": s["units"], "items": s["items"], "jobs": s["jobs"], "caches": s.get("caches"),
                          "cache_counts": s.get("cache_counts")})
        row["tick_trace"] = trace
    days, t0 = [], smoke.score()["abs_tick"]
    for d in range(1, a.days + 1):
        if a.quiet_view:   # DF can recenter the view on an announcement; point it back each day
            lua_json(os.path.join(ROOT, "embark/det_view.lua"), "camera")
        if a.advance == "smoke":
            # the harness's own advance (v2.1: ends on game ticks only, polled over RPC every second; popups dismissed
            # as in a real run). Tripwire pauses end it early, so loop to the day boundary.
            stuck = 0
            while smoke.score()["abs_tick"] < t0 + d * TPD and stuck < 5:
                stuck = stuck + 1 if smoke.advance(t0 + d * TPD - smoke.score()["abs_tick"]) == 0 else 0
        else:
            # quiet: advance.lua `chunk` ticks (notrip: it re-pauses exactly at the target), then no RPC at all until
            # it should be done (sleep chunk / QUIET_TPS + slack), then check; repeat to the day boundary
            import time
            for _c in range(TPD // a.chunk):
                H.dfhack("lua", "-f", os.path.join(ROOT, "advance.lua"), str(a.chunk), "notrip")
                time.sleep(a.chunk / a.quiet_tps + a.quiet_slack)
                while not H.dfhack("lua", "print(df.global.pause_state)").strip().endswith("true"):
                    time.sleep(a.quiet_slack + 1)
        s = lua_json(os.path.join(ROOT, "embark/det_state.lua"))
        s["day"] = d
        s["rng"] = lua_json(os.path.join(ROOT, "embark/det_rng.lua"), "read")["buf0_fnv"]
        if a.quiet_view:
            s["window_end"] = H.dfhack("lua", "print(df.global.window_x, df.global.window_y, df.global.window_z)").strip()
        days.append(s)
    row["days"] = days
    if a.shim and os.path.exists(status):
        row["shim_counts"] = json.load(open(status))
    if a.trandom == "count":   # the shim rewrites the histogram periodically; give it a moment, then keep a copy
        import shutil, time
        time.sleep(3)
        src = f"/tmp/det_trandom_{a.label}_{k}.jsonl"
        if os.path.exists(src) and a.out:
            shutil.copy(src, os.path.splitext(a.out)[0] + f"-trandom-k{k}.jsonl")
    return row


FIELDS = ("abs_tick", "rng", "units", "items", "jobs", "units_n", "items_n", "jobs_n", "reports_n", "item_next_id",
          "unit_next_id", "job_next_id")


def compare(rows):
    """First day (1-based) on which any replay differs from replay 0, per field; None = identical throughout."""
    rows = [r for r in rows if "days" in r]
    out = {}
    if len(rows) < 2:
        return out
    n = min(len(r["days"]) for r in rows)
    for f in FIELDS:
        out[f] = next((d + 1 for d in range(n) if len({json.dumps(r["days"][d].get(f)) for r in rows}) > 1), None)
    out["any"] = min((v for v in out.values() if v), default=None)
    out["load_rng_identical"] = len({r["load_rng"]["buf0_fnv"] for r in rows}) == 1
    out["n_replays"], out["days"] = len(rows), n
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out")
    p.add_argument("--label", default="base")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--days", type=int, default=28)
    p.add_argument("--reseed", type=int)
    p.add_argument("--shim")
    p.add_argument("--shim-mode", default="count", choices=["count", "fix"])
    p.add_argument("--shim-seed", type=int, default=1)
    p.add_argument("--trandom", choices=["count", "split", "simroot"], help="shim: histogram DF's RNG draws, or split UI draws off")
    p.add_argument("--ui-paused", action="store_true", help="split: draws while paused count as UI")
    p.add_argument("--ui-sites", help="split: comma-separated hex caller addresses that count as UI")
    p.add_argument("--idle-paused", type=float, default=0, help="seconds to sit paused after the load")
    p.add_argument("--tick-trace", type=int, default=0, help="after the reseed, advance this many single ticks, "
                   "fingerprinting RNG and state after each")
    p.add_argument("--trace-step", type=int, default=1, help="tick trace: ticks per step")
    p.add_argument("--pause-dump", help="shim (with --trandom count): write the draw histogram to DIR at every pause")
    p.add_argument("--env", nargs="*", help="KEY=VALUE pairs added to DF's environment")
    p.add_argument("--post-load", action="append", help="a DFHack command to run right after the load (repeatable)")
    p.add_argument("--record-plugins", action="store_true", help="keep `plug` output (enabled plugins) in the row")
    p.add_argument("--deep", action="store_true", help="deep fingerprint of hidden unit state at load (det_deep.lua)")
    p.add_argument("--addr", action="store_true", help="heap addresses of units/items/buildings at load (det_addr.lua)")
    p.add_argument("--reseed-before-load", type=int, help="reseed DF's RNG in the save list, just before the load")
    p.add_argument("--quiet-view", action="store_true", help="after the load: camera to empty sky, unit caches "
                   "cleared; the camera is re-pointed before every advance")
    p.add_argument("--advance", choices=["smoke", "quiet"], default="smoke",
                   help="smoke: smoke.advance (RPC poll every second); quiet: no RPC while ticks run")
    p.add_argument("--chunk", type=int, default=1200, help="quiet: ticks per advance (divides 1200)")
    p.add_argument("--quiet-tps", type=float, default=150.0, help="quiet: assumed ticks/s for the wait")
    p.add_argument("--quiet-slack", type=float, default=1.0, help="quiet: extra seconds per wait")
    p.add_argument("--compare", nargs="+", help="replay JSONL files: print per-label divergence")
    a = p.parse_args()
    if a.compare:
        by = {}
        for f in a.compare:
            for line in open(f):
                r = json.loads(line)
                if "label" in r:   # skip shim thread logs
                    by.setdefault(r["label"], []).append(r)
        for lab, rows in by.items():
            print(lab, json.dumps(compare(rows)))
        return
    for k in range(a.k):
        row = replay(a, k)
        with open(a.out, "a") as fh:
            fh.write(json.dumps(row) + "\n")
        print(a.label, k, row.get("error") or row["load_rng"]["buf0_fnv"], flush=True)


if __name__ == "__main__":
    main()
