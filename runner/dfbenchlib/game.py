"""One game = one Docker Compose project (docs/GAME-API.md §2): start game, wait for /health and /task, start the
gateway (with the key), start the harness (with DFBENCH_TASK), wait for the harness to exit or the game to end, call
POST /finish if the harness left early, collect the artifacts (§6) and tear down.

Every container the runner starts belongs to the project `<prefix>-<run id>`; teardown is `compose down -v`.
The runner never reaches the game over the host network: it uses `docker compose exec game python3 -c ...`.
"""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, time

from . import RUNNER, ROOT, RUNNER_VERSION

ENV_URL = "http://game:8090"     # the environment service as the harness reaches it (spec or task "env_url" overrides)

COMPOSE_DIR = os.path.join(RUNNER, "compose")
FAKES_DIR = os.path.join(RUNNER, "fakes")
FAKES_IMAGE = "s0run-fakes:latest"
DEFAULT_MODEL = "z-ai/glm-5.3-flash"
DAYS_PER_YEAR = 336
# env vars never passed to docker/compose unless a step needs them (the key goes only to `up gateway`)
SECRET_ENV = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", re.I)

# a tiny HTTP client run inside the game container (the DF image and the fakes both have python3)
_EXEC_HTTP = ("import json,sys,urllib.request,urllib.error\n"
              "m,p,b,t=sys.argv[1],sys.argv[2],sys.argv[3],float(sys.argv[4])\n"
              "r=urllib.request.Request('http://127.0.0.1:8090'+p,data=(b.encode() if m=='POST' else None),method=m,"
              "headers={'Content-Type':'application/json'})\n"
              "try:\n  print(urllib.request.urlopen(r,timeout=t).read().decode())\n"
              "except urllib.error.HTTPError as e:\n  print(e.read().decode())\n")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


def harness_digest(path):
    """sha256 over the harness directory: sorted relative paths and file digests (.git and __pycache__ skipped)."""
    h = hashlib.sha256()
    for d, dirs, files in os.walk(path):
        dirs[:] = sorted(x for x in dirs if x not in (".git", "__pycache__"))
        for f in sorted(files):
            p = os.path.join(d, f)
            rel = os.path.relpath(p, path).replace(os.sep, "/")
            with open(p, "rb") as fh:
                h.update(rel.encode() + b"\0" + hashlib.sha256(fh.read()).digest())
    return "sha256:" + h.hexdigest()


def clean_env(extra=None):
    """The runner's env minus anything secret-looking, plus `extra`."""
    env = {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}
    env.update(extra or {})
    return env


def sh(cmd, env=None, timeout=None, check=True, capture=True):
    r = subprocess.run(cmd, env=env, timeout=timeout, text=True,
                       stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(cmd[:6])}... exited {r.returncode}: {(r.stderr or '')[-2000:]}")
    return r


def build_harness(path, tag_prefix="dfbench-harness"):
    """docker build the submission's Dockerfile with no secrets in the env (build may fetch pinned dependencies)."""
    if not os.path.exists(os.path.join(path, "Dockerfile")):
        raise SystemExit(f"{path}: no Dockerfile")
    digest = harness_digest(path)
    tag = f"{tag_prefix}:{digest.split(':')[1][:16]}"
    log(f"building harness {path} -> {tag}")
    sh(["docker", "build", "-q", "-t", tag, path], env=clean_env(), capture=True)
    return tag, digest


def build_gateway():
    """The trusted gateway image from this checkout's gateway/ (never from the submission)."""
    tag = "dfbench-gateway:" + harness_digest(os.path.join(ROOT, "gateway")).split(":")[1][:16]
    sh(["docker", "build", "-q", "-t", tag, os.path.join(ROOT, "gateway")], env=clean_env())
    return tag


def build_fakes():
    sh(["docker", "build", "-q", "-t", FAKES_IMAGE, FAKES_DIR], env=clean_env())
    return FAKES_IMAGE


def scenario_task_id(sc, path):
    """'LT01' for lab scenarios (their id starts with the lab task), else the scenario id or name."""
    sid = sc.get("id") or sc.get("name") or os.path.splitext(os.path.basename(path))[0]
    m = re.match(r"^(LT\d\d)\b", sid)
    return m.group(1) if m else sid


class Game:
    """One game's lifecycle. `spec`: game_id, task_id, kind, scenario (repo-relative path), k, seed, days, budget_usd,
    wall_s, strange_moods, plus runner options in `opt` (stack, model, key_env, harness_image, digest, ...)."""

    def __init__(self, spec, opt, out_dir):
        self.spec, self.opt = spec, opt
        self.dir = os.path.abspath(os.path.join(out_dir, spec["game_id"]))
        self.run_id = f"{opt.get('run_prefix', 'dfb')}-{spec['game_id']}-{os.urandom(3).hex()}".lower()
        self.project = re.sub(r"[^a-z0-9_-]", "-", self.run_id)
        self.rec = {"runner": RUNNER_VERSION, "run_id": self.run_id, "spec": spec, "status": None, "notes": []}

    # ---- compose plumbing
    def _files(self):
        overlays = {"fake": ["compose.fake.yml"], "mixed": ["compose.real.yml", "compose.mixed.yml"]}.get(
            self.opt.get("stack"), ["compose.real.yml"])
        out = ["-f", os.path.join(COMPOSE_DIR, "compose.yml")]
        for o in overlays:
            out += ["-f", os.path.join(COMPOSE_DIR, o)]
        return out

    def _env(self, **extra):
        s = self.spec
        e = clean_env({
            "DFBENCH_PROJECT": self.project, "DFBENCH_RUN_ID": self.run_id,
            "DFBENCH_GAME": json.dumps(self.game_cfg), "DFBENCH_SCENARIO_FILE": self.scenario_file,
            "DFBENCH_GAME_DIR": os.path.join(self.dir, "game"), "DFBENCH_LEDGER_DIR": os.path.join(self.dir, "gateway"),
            "DFBENCH_HARNESS_IMAGE": self.opt["harness_image"],
            "DFBENCH_HARNESS_CPUS": str(self.opt.get("harness_cpus", 1)),
            "DFBENCH_HARNESS_MEM": self.opt.get("harness_mem", "2g"),
            "DFBENCH_GAME_MEM": self.opt.get("game_mem", "3g"),
            "DFBENCH_MODEL": self.opt.get("model", DEFAULT_MODEL), "DFBENCH_PROVIDER": self.opt.get("provider", "together"),
            "DFBENCH_BUDGET_USD": f"{s['budget_usd']:.4f}",
            "DFBENCH_SNAPSHOTS_DIR": os.environ.get("DFBENCH_SNAPSHOTS_DIR") or os.path.join(ROOT, "scenarios", "snapshots")})
        for k in ("DFBENCH_GAME_IMAGE", "DFBENCH_GATEWAY_IMAGE", "DFBENCH_UPSTREAM_URL", "DFBENCH_FAKES_IMAGE",
                  "FAKE_SEC_PER_DAY", "FAKE_THROTTLE_S", "FAKE_COST_PER_CALL", "FAKE_REQUIRE_KEY", "FAKE_USAGE_MISSING_AT",
                  "GATEWAY_ALLOW_HTTP_UPSTREAM"):
            if self.opt.get(k) is not None:
                e[k] = str(self.opt[k])
        e.update(extra)
        return e

    def compose(self, *args, env=None, timeout=300, check=True):
        return sh(["docker", "compose", *self._files(), "--project-directory", self.dir, *args],
                  env=env or self._env(), timeout=timeout, check=check)

    def game_http(self, method, path, body=None, timeout=30):
        """HTTP to the game from inside its container; -> parsed JSON or None."""
        r = self.compose("exec", "-T", "game", "python3", "-c", _EXEC_HTTP, method, path, json.dumps(body or {}),
                         str(timeout), timeout=timeout + 30, check=False)
        try:
            return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None
        except ValueError:
            return None

    def gateway_ok(self):
        code = ("import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/status',timeout=5)")
        return self.compose("exec", "-T", "gateway", "python3", "-c", code, timeout=60, check=False).returncode == 0

    def gateway_status(self):
        """The gateway's status file (host side of its /out mount; rewritten atomically after every call)."""
        try:
            with open(os.path.join(self.dir, "gateway", "gateway-status.json")) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def harness_state(self):
        return self.container_state("harness")

    def container_state(self, service):
        r = self.compose("ps", "-a", "-q", service, timeout=60, check=False)
        cid = (r.stdout or "").strip().splitlines()
        if not cid:
            return None
        r = sh(["docker", "inspect", "-f", "{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}", cid[0]],
               check=False)
        parts = (r.stdout or "").split()
        return {"status": parts[0], "exit_code": int(parts[1]), "oom": parts[2] == "true"} if len(parts) == 3 else None

    # ---- lifecycle
    def prepare(self):
        s = self.spec
        for d in ("game", "gateway", "harness", "task", "logs"):
            os.makedirs(os.path.join(self.dir, d), exist_ok=True)
        open(os.path.join(self.dir, "gateway", "usage.jsonl"), "a").close()
        # the gateway image runs as `nobody`: on Linux the bind-mounted dir must be writable for it
        os.chmod(os.path.join(self.dir, "gateway"), 0o777)
        os.chmod(os.path.join(self.dir, "gateway", "usage.jsonl"), 0o666)
        sc = json.load(open(os.path.join(ROOT, s["scenario"])))
        sc["days"] = s["days"]
        sc["strange_moods"] = bool(s.get("strange_moods", sc.get("strange_moods", False)))
        self.scenario_file = os.path.join(self.dir, "task", "scenario.json")
        json.dump(sc, open(self.scenario_file, "w"), indent=1)
        self.game_cfg = {"schema": "dfbench-game/1", "run_id": self.run_id, "arm": "harness", "k": s["k"],
                         "seed": s["seed"], "scenario": s["scenario"], "scenario_path": "/dfbench/scenario.json",
                         "days": s["days"], "strange_moods": sc["strange_moods"], "artifacts_dir": "/artifacts",
                         "ledger_path": "/ledger/usage.jsonl", "gateway_status_path": "/ledger/gateway-status.json",
                         "gateway_url": "http://gateway:8080", "harness_digest": self.opt.get("digest"),
                         "budget": {"credits": s["budget_usd"], "unit": "USD at the pinned reference prices", "per": "game"},
                         "rules": {"actions_per_game_day": s.get("actions_per_game_day", 40),
                                   "max_advance_days": s.get("max_advance_days", 28), "wall_s": s["wall_s"]}}
        json.dump(self.game_cfg, open(os.path.join(self.dir, "task", "game_input.json"), "w"), indent=1)

    def done_before(self):
        p = os.path.join(self.dir, "game.json")
        rec = json.load(open(p)) if os.path.exists(p) else {}
        return rec.get("status") == "ok"

    def run(self):
        if self.opt.get("resume") and self.done_before():
            log(f"{self.spec['game_id']}: done before, skipped")
            return json.load(open(os.path.join(self.dir, "game.json")))
        if os.path.isdir(self.dir):
            self._keep_previous_attempt()    # a fresh attempt; the earlier one's artifacts move to attempt-<n>/
        self.prepare()
        watch = None
        if self.opt.get("watch"):        # local watch mode only (runner/dfbenchlib/watch.py); never set in CI
            from . import watch
        live = watch.start_live(self) if watch and self.opt.get("watch_live") else None
        t0 = time.time()
        self.rec["t_start"] = t0
        try:
            self._play()
        except Exception as e:  # noqa: BLE001 - recorded as an infra failure, then torn down
            self.rec["status"] = "infra"
            self.rec["infra_cause"] = "game"
            self.rec["notes"].append(f"runner error: {e}")
            log(f"{self.spec['game_id']}: infra error: {e}")
        finally:
            try:
                if watch:
                    watch.stop_recording(self)
                self._collect_logs()
            finally:
                if live:
                    live.close()
                self.compose("down", "-v", "--remove-orphans", "-t", "5", timeout=180, check=False)
        self.rec["wall_s"] = round(time.time() - t0, 1)
        if watch:
            try:
                watch.finish(self)
            except Exception as e:  # noqa: BLE001 - a failed video never changes the game's result
                self.rec["notes"].append(f"watch: post-processing failed: {e}")
        self._check_artifacts()
        json.dump(self.rec, open(os.path.join(self.dir, "game.json"), "w"), indent=1)
        log(f"{self.spec['game_id']}: {self.rec['status']} ({self.rec.get('finished_by')}) in {self.rec['wall_s']} s")
        return self.rec

    def _keep_previous_attempt(self):
        """Move an earlier attempt's files to <game>/attempt-<n>/ (kept for diagnosis; the scorer skips them)."""
        old = [x for x in os.listdir(self.dir) if not x.startswith("attempt-")]
        if not old:
            return
        n = 0
        while os.path.exists(os.path.join(self.dir, f"attempt-{n}")):
            n += 1
        dest = os.path.join(self.dir, f"attempt-{n}")
        os.makedirs(dest)
        for x in old:
            shutil.move(os.path.join(self.dir, x), os.path.join(dest, x))
        self.rec["notes"].append(f"earlier attempt kept in attempt-{n}/")

    def _wait(self, what, fn, timeout, every=2.0):
        t = time.time()
        while time.time() - t < timeout:
            v = fn()
            if v:
                return v
            time.sleep(every)
        raise RuntimeError(f"timed out after {timeout} s waiting for {what}")

    def _game_ready(self):
        """One startup poll: the /health reply once the game is ready; None while it starts. Raises at once when the
        server reports a failed start or its container has exited, instead of waiting out the startup timeout."""
        h = self.game_http("GET", "/health", timeout=10)
        if h and (h.get("phase") == "failed" or h.get("ok") is False):
            raise RuntimeError(f"game server failed to start: {h.get('error') or h.get('phase')}")
        if h and (h.get("ready") or ("ready" not in h and "phase" not in h)):   # (a server without the flags)
            return h
        st = self.container_state("game")
        if st and st["status"] in ("exited", "dead"):
            tail = (self.compose("logs", "--no-color", "--tail", "15", "game", timeout=60, check=False).stdout or "")
            raise RuntimeError(f"game server exited (code {st['exit_code']}{', OOM' if st['oom'] else ''}) "
                               f"before it was ready; last log lines: {tail.strip()[-800:]}")
        return None

    def _play(self):
        s, o = self.spec, self.opt
        self.compose("up", "-d", "--no-deps", "game", timeout=600)
        self._wait("the game to be ready", self._game_ready, o.get("startup_timeout", 900))
        task = self._wait("game /task", lambda: (lambda t: t if t and not t.get("error_code") else None)(
            self.game_http("GET", "/task")), 120)
        json.dump(task, open(os.path.join(self.dir, "task", "server_task.json"), "w"), indent=1)
        # the gateway: the only step that sees the key
        key = os.environ.get(o.get("key_env") or "DFBENCH_PROVIDER_KEY", "")
        if o.get("stack") == "real" and not key:
            raise RuntimeError(f"no model key in ${o.get('key_env') or 'DFBENCH_PROVIDER_KEY'}")
        self.compose("up", "-d", "--no-deps", "gateway", env=self._env(DFBENCH_PROVIDER_KEY=key), timeout=300)
        try:
            self._wait("gateway /health", self.gateway_ok, 120)
        except RuntimeError as e:
            self.rec["notes"].append(f"{e} (started the harness anyway)")
        rules = task.get("rules") or {}
        dtask = {"schema": "dfbench-task/1", "run_id": self.run_id, "api": task.get("api", "v0"),
                 "game_url": s.get("env_url") or task.get("env_url") or ENV_URL,
                 "model": {"base_url": "http://gateway:8080/v1", "name": o.get("model", DEFAULT_MODEL),
                           "api": "openai-chat", "api_key": "placeholder",
                           "prices": model_prices(o.get("model", DEFAULT_MODEL))},
                 "budget": {"credits": s["budget_usd"], "unit": "USD at the pinned reference prices", "per": "game"},
                 "limits": {"wall_s": rules.get("wall_s", s["wall_s"]),
                            "actions_per_game_day": rules.get("actions_per_game_day", 40),
                            "max_advance_days": rules.get("max_advance_days", 28)},
                 "task": task.get("task")}
        json.dump(dtask, open(os.path.join(self.dir, "task", "dfbench_task.json"), "w"), indent=1)
        self.compose("up", "-d", "--no-deps", "harness", env=self._env(DFBENCH_TASK=json.dumps(dtask)), timeout=300)
        self.rec["t_harness"] = time.time()
        # wait: harness exit or game end; the server owns the wall cap, the runner a hard backstop past it
        deadline = time.time() + s["wall_s"] + o.get("finish_grace_s", 3600)
        poll = o.get("poll_s", 5)
        hs, h = None, None
        while time.time() < deadline:
            hs = self.harness_state()
            h = self.game_http("GET", "/health") or {}
            if h.get("finished"):
                break
            if hs and hs["status"] in ("exited", "dead"):
                break
            blocked = self.gateway_status().get("blocked_reason")
            if blocked:      # credits ran out (or usage unknown, fail closed): the server runs the fort on (§2)
                self.rec["notes"].append(f"gateway blocked ({blocked}) at day {h.get('day')}; POST /finish")
                self.game_http("POST", "/finish", {"reason": f"credits_{blocked}"}, timeout=60)
                self.compose("stop", "-t", "10", "harness", timeout=120, check=False)
                hs = self.harness_state()
                break
            time.sleep(poll)
        self.rec["harness"] = hs
        h = self.game_http("GET", "/health") or h
        if not h.get("finished"):
            if any(n.startswith("gateway blocked") for n in self.rec["notes"]):
                pass
            elif hs and hs["status"] in ("exited", "dead"):
                self.rec["notes"].append(f"harness exited ({hs['exit_code']}{', OOM' if hs['oom'] else ''}) "
                                         f"at day {h.get('day')}; POST /finish")
                self.game_http("POST", "/finish", {"reason": "harness_exit"}, timeout=60)
            else:
                self.rec["notes"].append("runner deadline reached; POST /finish")
                self.compose("stop", "-t", "10", "harness", timeout=120, check=False)
                self.game_http("POST", "/finish", {"reason": "runner_deadline"}, timeout=60)
            left = max(600, deadline - time.time() + 600)
            h = self._wait("the server to finish", lambda: (self.game_http("GET", "/health") or {}).get("finished")
                           and self.game_http("GET", "/health"), left, every=poll)
        if hs is None or hs["status"] not in ("exited", "dead"):
            self.compose("stop", "-t", "10", "harness", timeout=120, check=False)
            self.rec["harness"] = self.harness_state()
        self.rec["finished_by"] = h.get("finished_by")
        self.rec["status"] = "ok"
        self._final_gateway_status()

    def _final_gateway_status(self):
        """The real gateway writes gateway-status.json only after a call: fetch /status if the file is missing."""
        p = os.path.join(self.dir, "gateway", "gateway-status.json")
        if os.path.exists(p):
            return
        code = "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8080/status',timeout=10).read().decode())"
        r = self.compose("exec", "-T", "gateway", "python3", "-c", code, timeout=60, check=False)
        try:
            st = json.loads(r.stdout)
        except ValueError:
            return
        with open(p, "w") as f:
            json.dump(st, f)

    def _collect_logs(self):
        """Bounded copies of each service's output (harness: --log-cap bytes, untrusted, never read by the scorer)."""
        cap = int(self.opt.get("log_cap", 5 * 2 ** 20))
        for svc, dest in (("harness", "harness/output.log"), ("gateway", "logs/gateway.log"), ("game", "logs/game.log")):
            p = os.path.join(self.dir, dest)
            try:
                with open(p, "wb") as f:
                    proc = subprocess.Popen(["docker", "compose", *self._files(), "--project-directory", self.dir,
                                             "logs", "--no-color", "--no-log-prefix", "-t", svc],
                                            env=self._env(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                    n = 0
                    for chunk in iter(lambda: proc.stdout.read(65536), b""):
                        if n + len(chunk) > cap:
                            f.write(chunk[:cap - n] + b"\n[truncated by the runner]\n")
                            proc.kill()
                            break
                        f.write(chunk)
                        n += len(chunk)
                    proc.wait(timeout=60)
            except (OSError, subprocess.SubprocessError) as e:
                self.rec["notes"].append(f"log copy {svc}: {e}")

    def _check_artifacts(self):
        """The game counts only with the server's artifacts; an infra rule from the gateway ledger can void it."""
        g = os.path.join(self.dir, "game")
        stem = os.path.join(g, f"harness-{self.spec['k']}")
        missing = [x for x in ("summary.jsonl",) if not os.path.exists(os.path.join(g, x))] + \
                  [x for x in (".daily.json",) if not os.path.exists(stem + x)]
        if missing and self.rec["status"] == "ok":
            self.rec["status"] = "infra"
            self.rec["infra_cause"] = "game"
            self.rec["notes"].append(f"missing server artifacts: {missing}")
        crashed = last_summary_row(g)
        crashed = crashed.get("crashed") if crashed else None
        if crashed:
            # DF crashed or hung (the server ended the game as crashed): an infra re-run, once (SCORING.md §6).
            # The last harness actions go into game.json (sealed per-game data) so a crash exploit can be found.
            self.rec["crash"] = {"error": str(crashed)[:300], "last_actions": last_actions(g, self.spec["k"])}
            if self.rec["status"] == "ok":
                self.rec["status"] = "infra"
                self.rec["infra_cause"] = "game"
                self.rec["notes"].append(f"DF crashed or hung: {str(crashed)[:120]}: infra re-run")
        u = ledger_summary(os.path.join(self.dir, "gateway", "usage.jsonl"))
        st = self.gateway_status()
        self.rec["ledger"] = u
        self.rec["gateway_status"] = {k: st.get(k) for k in ("spent_usd", "budget_usd", "calls", "calls_refused",
                                                              "calls_upstream_error", "upstream_timeouts", "usage_unknown_calls",
                                                              "throttle_wait_total_s", "blocked_reason",
                                                              "price_table_hash", "provider_mismatches")}
        lim = self.opt.get("infra") or {}
        if self.rec["status"] != "ok":
            return
        self.rec["infra_cause"] = "provider"      # each rule below is the provider's (or the gateway's) fault
        if (st.get("usage_unknown_calls") or 0) > 0 or u["usage_missing"] > 0:
            self.rec["status"] = "infra"
            self.rec["notes"].append("gateway usage_unknown_calls > 0 (fail closed): infra re-run")
        elif st.get("blocked_reason") == "upstream_unreliable":
            self.rec["status"] = "infra"
            self.rec["notes"].append(f"provider hung or lost {st.get('upstream_timeouts')} calls: infra re-run")
        elif u["calls"] >= 10 and u["upstream_errors_provider"] / u["calls"] > lim.get("max_upstream_error_share", 0.10):
            self.rec["status"] = "infra"
            self.rec["notes"].append(f"provider errors {u['upstream_errors_provider']}/{u['calls']}: infra re-run")
        elif (st.get("throttle_wait_total_s") or 0) > lim.get("max_throttle_share", 0.5) * (time.time() - self.rec["t_start"]):
            self.rec["status"] = "infra"
            self.rec["notes"].append(f"provider throttling {st.get('throttle_wait_total_s')} s: infra re-run")
        if self.rec["status"] == "ok":
            self.rec.pop("infra_cause", None)


LAST_ACTIONS = 20


def last_summary_row(gdir):
    """The server's last summary row (crashed or not), or None."""
    try:
        with open(os.path.join(gdir, "summary.jsonl")) as f:
            rows = [json.loads(l) for l in f if l.strip()]
    except (OSError, ValueError):
        return None
    return rows[-1] if rows else None


def last_actions(gdir, k, n=LAST_ACTIONS):
    """The last n POST /act calls in the server's API log (tool, arguments, status, day): what the harness did
    just before DF crashed. Bounded; stays in the sealed per-game data."""
    p = os.path.join(gdir, f"harness-{k}.api.jsonl")
    out = []
    try:
        with open(p) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("method") == "POST" and str(r.get("path", "")).startswith("/act"):
                    out.append({"day": r.get("day"), "tick": r.get("tick"), "status": r.get("status"),
                                "request": json.dumps(r.get("request"), default=str)[:500]})
                    out = out[-n:]
    except OSError:
        return []
    return out


def crash_twice(causes):
    """True when a game's attempts (their infra causes, oldest first) hold two DF-side failures and no ok: the
    game is then scored at the state reached instead of re-run again (SCORING.md §6)."""
    return sum(1 for c in causes if c == "game") >= 2


def model_prices(model):
    """The gateway's pinned prices for `model` (gateway/prices.json), for DFBENCH_TASK.model.prices (contract §3.1):
    USD per million tokens, as in the table and as the starter harness reads them."""
    p = os.path.join(ROOT, "gateway", "prices.json")
    try:
        raw = open(p, "rb").read()
        m = json.loads(raw)["models"][model]
    except (OSError, ValueError, KeyError):
        return None
    return {"input": m["input"], "cached_input": m["cached_input"], "output": m["output"],
            "unit": "USD per million tokens", "price_table_hash": "sha256:" + hashlib.sha256(raw).hexdigest()}


def ledger_summary(path):
    """Totals from the gateway's usage.jsonl (trusted; schema dfbench-usage/1, gateway/README.md "Ledger")."""
    t = {"calls": 0, "ok_calls": 0, "refused": 0, "refused_budget": 0, "upstream_errors": 0,
         "upstream_errors_provider": 0, "upstream_timeouts": 0,
         "usage_missing": 0,
         "cost_usd": 0.0, "prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0,
         "throttle_wait_s": 0.0, "latency_s": 0.0, "price_table_hash": None}
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except OSError:
        return t
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        oc = r.get("outcome") or "ok"
        t["calls"] += 1
        t["ok_calls"] += oc == "ok"
        t["refused"] += oc.startswith("refused_")
        t["refused_budget"] += oc == "refused_budget_exhausted"
        t["upstream_errors"] += oc == "upstream_error"
        # the provider's own failures (5xx, 429 after retries, unreachable): a 4xx is the request's fault, which a
        # harness can cause at will, so only these count towards the infra rule
        us = r.get("upstream_status")
        t["upstream_errors_provider"] += oc == "upstream_error" and not r.get("harness_attributable") and (
            us is None or us == 429 or (isinstance(us, int) and us >= 500))
        t["upstream_timeouts"] += oc == "upstream_timeout"
        t["usage_missing"] += oc == "usage_missing"
        t["cost_usd"] += float(r.get("cost_usd") if r.get("cost_usd") is not None else (r.get("cost_upper_bound_usd") or 0))
        for k in ("prompt_tokens", "cached_tokens", "completion_tokens", "reasoning_tokens"):
            t[k] += int(r.get(k) or 0)
        t["throttle_wait_s"] += float(r.get("throttle_wait_s") or 0)
        t["latency_s"] += float(r.get("latency_s") or 0)
        t["price_table_hash"] = r.get("price_table_hash") or t["price_table_hash"]
    for k, d in (("cost_usd", 6), ("throttle_wait_s", 2), ("latency_s", 2)):
        t[k] = round(t[k], d)
    return t


def docker_mem_mb():
    r = sh(["docker", "info", "--format", "{{.MemTotal}}"], check=False)
    try:
        return int(r.stdout.strip()) // 2 ** 20
    except ValueError:
        return None


def mem_mb(s):
    m = re.match(r"^(\d+(?:\.\d+)?)([kmg]?)b?$", str(s).lower())
    if not m:
        return 0
    return int(float(m.group(1)) * {"k": 1 / 1024, "m": 1, "g": 1024, "": 1 / 2 ** 20}[m.group(2)])
