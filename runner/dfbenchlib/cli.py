"""dfbench CLI (runner/README.md):

  dfbench local smoke [--harness submission/] [--task …] [--days 3]   # real DF, fake model, $0: run this first
  dfbench local run --harness DIR --task scenarios/X.json [--seed K] [--n N] [--parallel P] [--budget 0.50] [--out DIR]
  dfbench local suite --harness DIR [--suite runner/suites/season0-public.json]   # the public suite, scored
  dfbench suite run --harness DIR --suite runner/suites/season0.json [--stages 1,2] [--games LT01-0,MY1] [--out DIR]
  dfbench suite plan --suite FILE [--stages 1] [--per-job 2]      # CI matrix JSON
  dfbench score DIR [--suite FILE]                                 # -> DIR/score.json, DIR/score_detail.json
  dfbench local run|suite|smoke ... --watch [--watch-live]        # LOCAL only: record each game (NOT comparable)
Common: --stack real|fake|mixed, --model, --key-env NAME (default: DFBENCH_PROVIDER_KEY, else OPENROUTER_API_KEY), --upstream URL, --harness-cpus, --harness-mem, --game-mem, --retries,
        --harness-image TAG --harness-digest D (skip the build: CI builds once), --resume.
"""
import argparse, json, os, re, sys, time

from . import ROOT, RUNNER_VERSION
from .game import DEFAULT_MODEL, build_fakes, build_gateway, build_harness, harness_digest, log
from .suite import check_forts, expand, load_suite, local_task, run_games


def run_prefix(value):
    """--run-prefix becomes part of Docker image and Compose project names (`<prefix>-harness:<hash>`, `<prefix>-<game>-…`),
    which must be lowercase: lowercase it (game.py already lowercases its run ids, so names stay consistent), and refuse
    anything that still isn't a valid name start."""
    v = (value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,40}", v):
        raise argparse.ArgumentTypeError(f"--run-prefix {value!r}: use letters, digits, '.', '_' or '-' "
                                         "(starting with a letter or digit, at most 41 characters)")
    return v


def _common(p):
    p.add_argument("--harness", help="the harness directory (has a Dockerfile)")
    p.add_argument("--harness-image", help="a prebuilt harness image (skips the build; give --harness-digest)")
    p.add_argument("--harness-digest")
    p.add_argument("--out")
    p.add_argument("--seed", type=int)
    p.add_argument("--n", type=int)
    p.add_argument("--parallel", type=int, default=1)
    p.add_argument("--budget", type=float, help="per-game credits, USD (default: the suite's rate x days / 336)")
    p.add_argument("--stack", choices=["real", "fake", "mixed"], default="real",
                   help="fake: runner/fakes for game and gateway; mixed: the real game server with the fake gateway "
                        "(test the server without a model)")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--provider", default="together")
    p.add_argument("--key-env", help="host env var holding the provider key (default: DFBENCH_PROVIDER_KEY if set, "
                   "else OPENROUTER_API_KEY); it reaches only the gateway container")
    p.add_argument("--upstream", help="the gateway's upstream (default https://openrouter.ai/api/v1; any "
                   "OpenAI-compatible https endpoint serving the model)")
    p.add_argument("--harness-cpus", type=float, default=1.0)
    p.add_argument("--harness-mem", default="2g")
    p.add_argument("--game-mem", default="3g")
    p.add_argument("--retries", type=int, default=1, help="re-runs of a game that failed for infra reasons")
    p.add_argument("--resume", action="store_true", help="skip games whose game.json says ok")
    p.add_argument("--run-prefix", default="dfb", type=run_prefix,
                   help="Compose project prefix (container and image names start with it; lowercased)")
    p.add_argument("--log-cap", type=int, default=5 * 2 ** 20, help="bytes of harness output kept per game")
    p.add_argument("--poll", type=float, default=5.0)
    p.add_argument("--startup-timeout", type=float, default=900)


def _watch_flags(p):
    """`dfbench local ...` only (runner/dfbenchlib/watch.py): never on `suite run`, refused in CI."""
    g = p.add_argument_group("watch mode (local only; results are NOT comparable)")
    g.add_argument("--watch", action="store_true",
                   help="render DF and record each game to <run>/<game>/video/<game>.mp4 (+ -4x.mp4); slower, "
                        "different DF prefs, labelled watch: true")
    g.add_argument("--watch-live", action="store_true",
                   help="--watch plus a view-only VNC of each game on 127.0.0.1 (password printed per game)")
    g.add_argument("--watch-port", type=int, default=5900, help="first 127.0.0.1 port for --watch-live")
    g.add_argument("--watch-no-4x", action="store_true", help="skip the 4x timelapse")


def _opt(a):
    if a.harness_image:
        tag, digest = a.harness_image, a.harness_digest or (harness_digest(a.harness) if a.harness else None)
    elif a.harness:
        tag, digest = build_harness(os.path.abspath(a.harness), tag_prefix=f"{a.run_prefix}-harness")
    else:
        raise SystemExit("--harness DIR or --harness-image TAG is required")
    key_env = a.key_env or next((k for k in ("DFBENCH_PROVIDER_KEY", "OPENROUTER_API_KEY") if os.environ.get(k)),
                                "DFBENCH_PROVIDER_KEY")
    opt = {"stack": a.stack, "model": a.model, "provider": a.provider, "key_env": key_env,
           "harness_image": tag, "digest": digest, "harness_cpus": a.harness_cpus, "harness_mem": a.harness_mem,
           "game_mem": a.game_mem, "resume": a.resume, "run_prefix": a.run_prefix, "log_cap": a.log_cap,
           "poll_s": a.poll, "startup_timeout": a.startup_timeout}
    for k in ("DFBENCH_GAME_IMAGE", "DFBENCH_GATEWAY_IMAGE", "DFBENCH_UPSTREAM_URL", "FAKE_SEC_PER_DAY",
              "FAKE_THROTTLE_S", "FAKE_COST_PER_CALL", "FAKE_REQUIRE_KEY", "FAKE_USAGE_MISSING_AT",
              "GATEWAY_ALLOW_HTTP_UPSTREAM"):
        if os.environ.get(k):
            opt[k] = os.environ[k]
    if a.upstream:
        opt["DFBENCH_UPSTREAM_URL"] = a.upstream
    if a.stack in ("fake", "mixed"):
        opt["DFBENCH_FAKES_IMAGE"] = build_fakes()
    elif not opt.get("DFBENCH_GATEWAY_IMAGE"):
        opt["DFBENCH_GATEWAY_IMAGE"] = build_gateway()
    if getattr(a, "watch", False) or getattr(a, "watch_live", False):
        from . import watch
        watch.configure(opt, a)
    return opt


def _start(out, suite, opt, argv):
    from .score import anchors_id
    log(f"== local run, NOT an official result: stack {opt['stack']} | suite {suite.get('name')} | tasks "
        f"{','.join(t['id'] for t in suite['tasks'])} | anchors {anchors_id(suite)} ==")
    opt["infra"] = suite.get("infra") or {}
    os.makedirs(out, exist_ok=True)
    json.dump(suite, open(os.path.join(out, "suite.json"), "w"), indent=1)
    meta = {"runner": RUNNER_VERSION, "argv": argv, "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "harness_image": opt["harness_image"], "harness_digest": opt["digest"], "stack": opt["stack"],
            "model": opt["model"]}
    if opt.get("watch"):     # labelled so the score never passes for a headless one (score.result_labels)
        from .watch import NOTE
        meta.update({"watch": True, "watch_note": NOTE, "game_image": opt.get("DFBENCH_GAME_IMAGE"),
                     "watch_base_image": opt.get("watch_base_image")})
    json.dump(meta, open(os.path.join(out, "run.json"), "w"), indent=1)


def _score_and_print(out, suite):
    from .score import labels_banner, score_dir
    score, _ = score_dir(out, suite)
    print(json.dumps(score, indent=1))
    log(labels_banner(score["metrics"]))
    return score


SMOKE_HINTS = (   # (substring of a game note or error, likely cause, next step)
    ("no dockerfile", "the harness directory has no Dockerfile", "pass --harness <dir with a Dockerfile> (default submission/)"),
    ("start forts not built", "the public start forts aren't built yet", "run .yukon/setup.sh (or set DFBENCH_SNAPSHOTS_DIR)"),
    ("df/save", "the game server image is the plain DF image (no df/save, no game server)",
     "re-run .yukon/setup.sh: it builds docker/Dockerfile.game as DFBENCH_GAME_IMAGE (default yukon-df:s0)"),
    ("not mounted", "the start fort isn't where the game container looks", "run .yukon/setup.sh, or set DFBENCH_SNAPSHOTS_DIR"),
    ("reset failed", "the game server couldn't load the start fort", "re-run .yukon/setup.sh; see the game log in the run dir"),
    ("oom", "a container ran out of memory", "give Docker more memory (about 3 GB per DF game plus 2 GB for the harness)"),
    ("harness", "your harness exited early or crashed", "see harness.log in the run dir; it ran against a fake model"),
    ("timeout", "the game server didn't start in time", "check Docker's CPU and memory; Apple Silicon runs DF under Rosetta, slower"),
)


def cmd_local_smoke(a, argv):
    """Real DF with a fake model, a few game-days of one task, $0: does the setup work, before any paid model call?"""
    suite = local_task(a.task, a.seed if a.seed is not None else 12345, 1, None)
    suite["tasks"][0]["days"] = a.days
    suite["tasks"][0]["wall_s"] = max(600, 120 * a.days)
    suite["name"], suite["smoke"] = f"smoke-{suite['tasks'][0]['id']}", True
    out = a.out or os.path.join(ROOT, "runs", f"dfbench-smoke-{time.strftime('%Y%m%d-%H%M%S')}")
    print(f"[smoke] {a.stack} stack (real DF, fake model, $0): {suite['tasks'][0]['id']} for {a.days} game-days -> {out}")
    try:
        specs = expand(suite, n=1, seed=a.seed)
        check_forts(specs, a.stack)
        opt = _opt(a)
        _start(out, suite, opt, argv)
        run_games(specs, opt, out, 1, 0)
    except SystemExit as e:
        msg = str(e.code if e.code is not None else "")
        _smoke_verdict(False, msg, out)
        raise SystemExit(1)
    except Exception as e:  # noqa: BLE001  a smoke test reports, it doesn't trace back
        _smoke_verdict(False, f"{type(e).__name__}: {e}", out)
        raise SystemExit(1)
    rec = {}
    for p in sorted(__import__("glob").glob(os.path.join(out, "*", "game.json"))):
        rec = json.load(open(p))
    ok = rec.get("status") == "ok"
    if ok:   # labelled scope "smoke": a 3-day score means nothing, but the labels say so wherever it's read
        from .score import labels_banner, score_dir
        try:
            log(labels_banner(score_dir(out, suite)[0]["metrics"]))
        except Exception as e:  # noqa: BLE001  the smoke verdict is about the stack, not the score
            log(f"smoke: not scored ({type(e).__name__}: {e})")
    _smoke_verdict(ok, " | ".join(str(n) for n in rec.get("notes") or []) or str(rec.get("status")), out)
    if not ok:
        raise SystemExit(1)


def _smoke_verdict(ok, detail, out):
    if ok:
        print(f"[smoke] PASS: DF loaded the fort, the game server, gateway and your harness ran together. Next: "
              f".yukon/run.sh (or `runner/dfbench local run --task …`) with your model key. Run dir: {out}")
        return
    low = (detail or "").lower()
    cause, step = next(((c, n) for k, c, n in SMOKE_HINTS if k in low),
                       ("see the run dir's game.json notes and logs", "fix it, then re-run the smoke test"))
    print(f"[smoke] FAIL: {detail.strip()[:400]}\n[smoke]   likely cause: {cause}\n[smoke]   next: {step}\n"
          f"[smoke]   run dir: {out}", file=sys.stderr)


def cmd_local_run(a, argv):
    suite = local_task(a.task, a.seed if a.seed is not None else 12345, a.n or 1, a.budget, a.wall_s)
    out = a.out or os.path.join(ROOT, "runs", f"dfbench-{suite['tasks'][0]['id']}-{time.strftime('%Y%m%d-%H%M%S')}")
    specs = expand(suite, n=a.n or 1, seed=a.seed, budget=a.budget)
    check_forts(specs, a.stack)
    opt = _opt(a)
    _start(out, suite, opt, argv)
    run_games(specs, opt, out, a.parallel, a.retries)
    _score_and_print(out, suite)
    log(f"out: {out}")


def cmd_suite_run(a, argv):
    suite = load_suite(a.suite)
    stages = sorted({int(x) for x in a.stages.split(",")}) if a.stages else sorted({t.get("stage", 1) for t in suite["tasks"]})
    only = set(a.games.split(",")) if a.games else None
    out = a.out or os.path.join(ROOT, "runs", f"dfbench-{suite['name']}-{time.strftime('%Y%m%d-%H%M%S')}")
    check_forts(expand(suite, stages=set(stages), only=only, seed=a.seed, n=a.n, budget=a.budget), a.stack)
    opt = _opt(a)
    _start(out, suite, opt, argv)
    for st in stages:
        specs = expand(suite, stages={st}, only=only, seed=a.seed, n=a.n, budget=a.budget)
        if st >= 2 and a.leader_stage1 is not None:
            from .score import score_dir
            s1, _ = score_dir(out, suite, write=False)
            ub = s1["metrics"].get("ub95")
            if ub is None or ub < a.leader_stage1:
                log(f"stage {st} skipped: stage-1 ub95 {ub} < leader's stage-1 point {a.leader_stage1}")
                continue
        log(f"stage {st}: {len(specs)} games")
        run_games(specs, opt, out, a.parallel, a.retries)
    _score_and_print(out, suite)
    log(f"out: {out}")


def cmd_suite_plan(a, argv):
    suite = load_suite(a.suite)
    stages = {int(x) for x in a.stages.split(",")} if a.stages else None
    specs = expand(suite, stages=stages, n=a.n)
    # longest games first, then pack per_job games per job (short labs share a job; OP1 runs alone if per_job_long=1)
    specs.sort(key=lambda s: -s["days"])
    jobs, cur = [], []
    for s in specs:
        cap = a.per_job_long if s["days"] >= 200 else a.per_job
        if cur and (len(cur) >= cap or (cur[0]["days"] >= 200) != (s["days"] >= 200)):
            jobs.append(cur)
            cur = []
        cur.append(s)
    if cur:
        jobs.append(cur)
    m = {"include": [{"job": f"j{i:02d}-{'-'.join(s['game_id'] for s in j)}"[:90],
                      "games": ",".join(s["game_id"] for s in j),
                      # the Play step stops at play_timeout_min (a step failure the job tolerates); the job's own
                      # timeout_min leaves 20 more minutes to seal and upload what was played
                      "play_timeout_min": int(sum(s["wall_s"] for s in j) / 60 + 30 * len(j) + 10),
                      "timeout_min": int(sum(s["wall_s"] for s in j) / 60 + 30 * len(j) + 30)} for i, j in enumerate(jobs)]}
    print(json.dumps(m))


def cmd_score(a, argv):
    suite = load_suite(a.suite) if a.suite else json.load(open(os.path.join(a.dir, "suite.json")))
    _score_and_print(a.dir, suite)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser(prog="dfbench", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    loc = sp.add_parser("local").add_subparsers(dest="sub", required=True)
    lr = loc.add_parser("run", help="play N games of one task locally")
    _common(lr)
    lr.add_argument("--task", required=True, help="scenarios/X.json")
    _watch_flags(lr)
    lr.add_argument("--wall-s", type=float, help="the game's wall cap (default max(1800, 5400 x days / 336))")
    sm = loc.add_parser("smoke", help="real DF + fake model, a few game-days, $0: check the setup first")
    _common(sm)
    _watch_flags(sm)
    sm.set_defaults(stack="mixed", harness=os.path.join(ROOT, "submission"))
    sm.add_argument("--task", default="scenarios/season0/lt01-drought.json")
    sm.add_argument("--days", type=int, default=3)
    su = sp.add_parser("suite").add_subparsers(dest="sub", required=True)
    ls_ = loc.add_parser("suite", help="play the public suite locally (same scoring), then score it")
    sr = su.add_parser("run", help="play a suite (stages, per-game dirs), then score it")
    for p_, default in ((ls_, os.path.join(ROOT, "runner", "suites", "season0-public.json")), (sr, None)):
        _common(p_)
        p_.add_argument("--suite", required=default is None, default=default)
        p_.add_argument("--stages", help="e.g. 1 or 1,2 (default: all)")
        p_.add_argument("--games", help="comma list of game ids (LT01-3) or task ids (MY1): a CI shard")
        p_.add_argument("--leader-stage1", type=float, help="run stage 2 only if the stage-1 ub95 reaches this")
    _watch_flags(ls_)
    pl = su.add_parser("plan", help="print the CI job matrix for a suite")
    pl.add_argument("--suite", required=True)
    pl.add_argument("--stages")
    pl.add_argument("--n", type=int)
    pl.add_argument("--per-job", type=int, default=2)
    pl.add_argument("--per-job-long", type=int, default=1)
    sc = sp.add_parser("score", help="trusted scoring of a run dir -> score.json")
    sc.add_argument("dir")
    sc.add_argument("--suite")
    a = ap.parse_args(argv)
    from .watch import refuse_reason
    why = refuse_reason(a)
    if why:
        ap.error(why)
    if getattr(a, "watch_live", False):
        a.watch = True
    {("local", "smoke"): cmd_local_smoke, ("local", "run"): cmd_local_run, ("local", "suite"): cmd_suite_run, ("suite", "run"): cmd_suite_run, ("suite", "plan"): cmd_suite_plan,
     ("score", None): cmd_score}[(a.cmd, getattr(a, "sub", None))](a, argv)


if __name__ == "__main__":
    main()
