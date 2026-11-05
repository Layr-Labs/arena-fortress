"""python3 -m gameapi.server --task scenarios/start-year.json [--out runs/game] [--k 0] [--port 8090] ...

Starts the HTTP API at once (GET /health answers "starting"), then resets DF with the task's settings, runs the
setup and serves the game; GET /task answers once the game is ready. The process keeps serving after the game ends
so the runner can collect the artifacts (--exit-when-done to stop instead). --fake runs the API on a fake DF.
Every option also reads an env var (GAMEAPI_<OPTION>), so a compose file can configure it without a command line.
"""
import argparse, json, os, signal, sys, threading, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gameapi.server import adapter, http_api, rules   # noqa: E402
from gameapi.server.task import load_task               # noqa: E402


def game_input():
    """DFBENCH_GAME (runner/dfbenchlib/game.py; docs/GAME-API.md §2): JSON with run_id, arm, k, seed, scenario
    (repo-relative), scenario_path (the runner's copy: days and strange_moods applied), days, strange_moods,
    artifacts_dir, ledger_path, gateway_status_path, gateway_url, harness_digest, budget{credits}, rules{...}.
    -> {option name: value} defaults (command-line options still win)."""
    raw = os.environ.get("DFBENCH_GAME") or ""
    if not raw.strip():
        return {}
    c = json.loads(raw)
    r, b = c.get("rules") or {}, c.get("budget") or {}
    sp = c.get("scenario_path")
    d = {"task": sp if sp and os.path.exists(sp) else c.get("scenario"), "key_task": c.get("scenario"),
         "days": c.get("days"), "k": c.get("k"), "seed": c.get("seed"), "arm": c.get("arm"),
         "out": c.get("artifacts_dir"), "run_id": c.get("run_id"), "harness_digest": c.get("harness_digest"),
         "strange_moods": c.get("strange_moods"), "credits": b.get("credits"),
         "actions_per_day": r.get("actions_per_game_day"), "max_advance_days": r.get("max_advance_days"),
         "wall_s": r.get("wall_s"), "gateway_status_path": c.get("gateway_status_path"),
         "ledger_path": c.get("ledger_path"), "model": c.get("model")}
    return {k: v for k, v in d.items() if v is not None}


GAME = {}


def env(name, default=None):
    """An option's default: DFBENCH_GAME's field, else $GAMEAPI_<NAME>, else the built-in default."""
    key = name.replace("-", "_")
    if key in GAME:
        return GAME[key]
    return os.environ.get("GAMEAPI_" + key.upper(), default)



def reset_hint(err, task):
    """A reset failure keeps only reset_fort.sh's own FAIL line (smoke.reset reads stdout), so check the two usual
    causes here and say which (tester feedback V1, 2026-10-28). Outside the comparability key: diagnostics only."""
    if "reset failed" not in err:
        return None
    df = os.path.join(ROOT, "df")
    if not os.path.isdir(os.path.join(df, "save")):
        return ("df/save is missing: this image is the plain DF image, not the game server image. Build "
                "docker/Dockerfile.game on it (.yukon/setup.sh does) and run that as DFBENCH_GAME_IMAGE")
    snap = (task.get("start") or {}).get("snapshot") if isinstance(task.get("start"), dict) else task.get("snapshot")
    if snap:
        path = snap if os.path.isabs(snap) else os.path.join(ROOT, snap)
        if not os.path.exists(path):
            return f"start fort {snap} not found in the container (DFBENCH_SNAPSHOTS_DIR mount?)"
    return None

def main(argv=None):
    GAME.clear(); GAME.update(game_input())
    p = argparse.ArgumentParser(prog="python3 -m gameapi.server")
    p.add_argument("--task", default=env("task") or os.environ.get("DFBENCH_SCENARIO"),
                   help="scenario JSON (scenarios/<name>.json)")
    p.add_argument("--days", type=int, default=env("days"), help="horizon (default: the scenario's)")
    p.add_argument("--k", type=int, default=int(env("k", 0)), help="run index: setup seed and snapshot pool member")
    p.add_argument("--seed", type=int, default=int(env("seed", 12345)))
    p.add_argument("--arm", default=env("arm", "harness"), help="artifact stem <arm>-<k>")
    p.add_argument("--out", default=env("out", os.path.join(ROOT, "runs", "game")))
    p.add_argument("--host", default=env("host", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(env("port", 8090)))
    p.add_argument("--actions-per-day", type=int, default=int(env("actions_per_day", rules.K_DEFAULT)))
    p.add_argument("--max-advance-days", type=int, default=int(env("max_advance_days", rules.MAX_ADVANCE_DAYS)))
    p.add_argument("--wall-s", type=float, default=float(env("wall_s", rules.WALL_S_DEFAULT)),
                   help="wall cap in seconds (0 = none)")
    p.add_argument("--run-id", default=env("run_id"))
    p.add_argument("--harness-digest", default=env("harness_digest"))
    p.add_argument("--model", default=env("model", "z-ai/glm-5.3-flash"))
    p.add_argument("--price-table-hash", default=env("price_table_hash"),
                   help="the gateway's price table id (default: sha256 of this tree's gateway/prices.json)")
    p.add_argument("--gateway-status-url", default=env("gateway_status_url"),
                   help="e.g. http://gateway:8080/status: poll throttle_wait_total_s (wall-cap exclusion) and, with "
                        "--finish-on-blocked, blocked_reason (credits gone -> run out the horizon)")
    p.add_argument("--finish-on-blocked", action="store_true", default=bool(env("finish_on_blocked")))
    p.add_argument("--gateway-status-path", default=env("gateway_status_path"),
                   help="the gateway's status file (runner: /ledger/gateway-status.json): throttle_wait_total_s")
    p.add_argument("--ledger-path", default=env("ledger_path"), help="fallback: the ledger's throttle_wait_s summed")
    p.add_argument("--key-task", default=env("key_task"),
                   help="the repo scenario the key's task hash names (default --task; the runner's copy of a "
                        "scenario has its days and strange_moods rewritten, which the key covers separately)")
    p.add_argument("--strange-moods", choices=["true", "false"], default=None if env("strange_moods") is None
                   else str(env("strange_moods")).lower())
    p.add_argument("--credits", type=float, default=float(env("credits", 0.5)))
    p.add_argument("--facts", choices=["auto", "legacy", "facts"], default=env("facts", "auto"))
    p.add_argument("--fake", action="store_true", default=bool(env("fake")), help="no DF: a fake game (development)")
    p.add_argument("--exit-when-done", action="store_true", default=bool(env("exit_when_done")))
    a = p.parse_args(argv)
    if not a.task:
        p.error("--task is required (or GAMEAPI_TASK)")

    task = load_task(a.task, k=a.k, seed=a.seed, days=a.days)
    try:                                    # gameapi/season1 is research-only: the season-0 challenge export leaves it out
        from gameapi import season1
        s1 = season1.rules_version(task)    # "s1" for a season-1 task (gameapi/season1), else None
    except ImportError:
        s1 = None
    if a.strange_moods is not None:
        task["strange_moods"] = a.strange_moods == "true"
    key_task = a.key_task if a.key_task and os.path.exists(os.path.join(ROOT, a.key_task)) else task["_path"]
    os.makedirs(a.out, exist_ok=True)
    if a.fake:
        from gameapi.server.fake import FakeBackend, FakeFacts
        backend, facts = FakeBackend(), FakeFacts()
    else:
        from gameapi.server.backend import DFBackend
        backend, facts = DFBackend(), adapter.load(None if a.facts == "auto" else a.facts)
    if s1:
        if not a.fake and getattr(facts, "NAME", "") != "gameapi.facts":
            p.error(f"rules_version {s1} needs the gameapi.facts layer, not {getattr(facts, 'NAME', '?')}")
        facts = season1.wrap(facts, fake=a.fake)
    budget = {"credits": a.credits, "unit": "USD at the pinned reference prices", "per": "game"}
    from bench import key as BK
    pth = a.price_table_hash or BK.price_table_hash()
    prices = None
    pp = os.path.join(ROOT, "gateway", "prices.json")
    if os.path.exists(pp):
        m = (json.load(open(pp)).get("models") or {}).get(a.model) or {}
        prices = {k: m[k] for k in ("input", "cached_input", "output") if k in m} or None
    condition = {"model": a.model, "price_table_hash": pth, "endpoint": "gateway", "prices": prices,
                 "prices_unit": "USD per million tokens" if prices else None}
    wall_s = (int(a.wall_s) if float(a.wall_s).is_integer() else a.wall_s) if a.wall_s else None
    # the key hashes the static schemas (build_workshop's enum comes from DF, pinned by the df version), so it can be
    # computed before DF starts and matches `bench/key.py --v3`
    tools = [t for t in facts.key_tools() if t["function"]["name"] != "advance_days"] + [rules.advance_tool(a.max_advance_days)]
    kf = BK.compute_v3(key_task, task["days"], k_actions=a.actions_per_day, max_advance_days=a.max_advance_days,
                       wall_s=wall_s, model=a.model, price_table_hash=pth,
                       budget=budget, strange_moods=bool(task.get("strange_moods")), tools=tools,
                       queries=facts.queries(), obs_schema=getattr(facts, "OBS_SCHEMA", None),
                       facts_impl=None if a.fake else ("facts" if getattr(facts, "NAME", "") == "gameapi.facts" else "legacy"))
    BK.record_batch(a.out, kf, {"arm": a.arm, "k": a.k, "seed": a.seed, "run_id": a.run_id,
                                "harness_digest": a.harness_digest, "facts": kf["facts"], "fake": a.fake},
                    sys.argv[1:] if argv is None else argv)
    if s1:
        from gameapi.season1.game import Game
    else:
        Game = rules.Game
    game = Game(backend, facts, task, out=a.out, arm=a.arm, k=a.k, K=a.actions_per_day,
                max_days=a.max_advance_days, wall_s=wall_s, condition=condition, key=kf["key"],
                harness_digest=a.harness_digest, run_id=a.run_id, budget=budget)
    srv = http_api.serve(game, a.host, a.port)
    print(json.dumps({"listening": f"{a.host}:{a.port}", "task": task["name"], "key": kf["key"], "out": a.out}),
          flush=True)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        game.start()
    except Exception as e:   # noqa: BLE001  /health reports phase=failed; keep serving so the runner sees why
        hint = reset_hint(str(e), task)
        if hint:
            game.error = f"{game.error} | {hint}"
        print(json.dumps({"start_failed": str(e)[:500], "hint": hint}), flush=True)
    print(json.dumps({"phase": game.phase, **game.envelope()}), flush=True)
    dog = rules.Watchdog(game, gateway_status_url=a.gateway_status_url, finish_on_blocked=a.finish_on_blocked,
                         gateway_status_path=a.gateway_status_path, ledger_path=a.ledger_path)
    dog.start()
    try:
        while not stop.wait(1.0):
            if a.exit_when_done and game.phase in ("finalized", "failed"):
                time.sleep(1.0)   # let the last response go out
                break
    except KeyboardInterrupt:
        pass
    dog.stop.set()
    srv.shutdown()
    print(json.dumps({"exit": game.phase, "end_reason": game.end_reason}), flush=True)
    return 0 if game.phase != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
