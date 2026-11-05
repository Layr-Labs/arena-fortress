"""Local watch mode (runner/README.md "Watching your games"): `dfbench local run|suite|smoke --watch [--watch-live]`.

The game runs in a watch image (docker/Dockerfile.watch, built FROM the configured game image): DF draws into a
virtual X display that ffmpeg records into the game's artifacts dir. After each game the runner stops the recording,
then a throwaway container of the same image (its own ffmpeg) writes <run>/<game>/video/<game>.mp4 and -4x.mp4.
--watch-live also serves a view-only VNC of the display on 127.0.0.1 (no container port is published: each VNC
connection is relayed through `docker compose exec game`, docker/watch/vnc_stdio.sh).

Watch results are never comparable: rendering slows DF and its prefs differ (PRINT_MODE, G_FPS_CAP, WINDOWED, SOUND).
The run is labelled `watch: true` in run.json, game.json and score.json. Refused in CI and outside `dfbench local`.
"""
import hashlib, json, os, secrets, shutil, socket, subprocess, threading

from . import ROOT
from .game import clean_env, log, sh

DOCKERFILE = os.path.join(ROOT, "docker", "Dockerfile.watch")
CONTEXT = os.path.join(ROOT, "docker", "watch")
DEFAULT_GAME_IMAGE = "yukon-df:s0"     # compose.real.yml's default
NOTE = ("watch mode: DF rendered and recorded (PRINT_MODE:SOFTWARE, G_FPS_CAP:20, windowed): slower than headless, "
        "different DF prefs; NOT comparable with any headless or official result")


def refuse_reason(a, environ=None):
    """Why --watch / --watch-live can't run here, or None. Local runs only: never in CI, never for official scoring,
    never with the fake game (nothing to render)."""
    env = os.environ if environ is None else environ
    if not (getattr(a, "watch", False) or getattr(a, "watch_live", False)):
        return None
    if a.cmd != "local":
        return "--watch is for `dfbench local run|suite|smoke` only"
    if env.get("GITHUB_ACTIONS"):
        return "--watch is refused in CI (GITHUB_ACTIONS is set): watch runs are local and never scored officially"
    if env.get("DFBENCH_RESULT_KIND", "local") != "local":
        return f"--watch is refused with DFBENCH_RESULT_KIND={env['DFBENCH_RESULT_KIND']}: watch runs are local only"
    if getattr(a, "stack", None) == "fake":
        return "--watch needs real DF: use --stack mixed (fake model, $0) or --stack real"
    return None


def image_tag(base_id):
    """dfbench-watch:<16 hex of (base image id, Dockerfile.watch, docker/watch/*)>: rebuilt when either changes."""
    h = hashlib.sha256(base_id.encode() + b"\0")
    for p in [DOCKERFILE] + sorted(os.path.join(CONTEXT, f) for f in os.listdir(CONTEXT)):
        with open(p, "rb") as f:
            h.update(os.path.basename(p).encode() + b"\0" + f.read())
    return "dfbench-watch:" + h.hexdigest()[:16]


def ensure_image(base):
    """Build (or reuse) the watch image FROM `base`, the game image this run would otherwise play. Local only."""
    r = sh(["docker", "image", "inspect", "-f", "{{.Id}}", base], check=False)
    if r.returncode:
        raise SystemExit(f"--watch: the game image {base} isn't here; build it first (.yukon/setup.sh), or set "
                         "DFBENCH_GAME_IMAGE")
    tag = image_tag(r.stdout.strip())
    if sh(["docker", "image", "inspect", tag], check=False).returncode == 0:
        log(f"watch: reusing {tag} (from {base})")
        return tag
    log(f"watch: building {tag} from {base} (docker/Dockerfile.watch; local only, a few minutes the first time)")
    sh(["docker", "build", "-q", "--platform", "linux/amd64", "--build-arg", f"BASE={base}", "-f", DOCKERFILE,
        "-t", tag, CONTEXT], env=clean_env())
    return tag


def configure(opt, a):
    """Called by the CLI for --watch: switch the game image to the watch image and label the run."""
    base = opt.get("DFBENCH_GAME_IMAGE") or DEFAULT_GAME_IMAGE
    opt["watch_base_image"] = base
    opt["DFBENCH_GAME_IMAGE"] = ensure_image(base)
    opt["watch"] = True
    opt["watch_live"] = bool(getattr(a, "watch_live", False))
    opt["watch_port"] = int(getattr(a, "watch_port", 5900) or 5900)
    opt["watch_4x"] = not getattr(a, "watch_no_4x", False)
    if opt["watch_live"]:
        opt["_watch_ports"] = PortPool(opt["watch_port"])
    log(f"== {NOTE} ==")
    return opt


# ---- per game (called from Game.run when opt["watch"])
def stop_recording(game):
    """Before teardown: let ffmpeg finish its last fragment (docker/watch/stop_rec.sh)."""
    r = game.compose("exec", "-T", "game", "/opt/dfwatch/stop_rec.sh", timeout=60, check=False)
    if r.returncode:
        game.rec["notes"].append(f"watch: stop_rec exited {r.returncode} (the fragmented recording is kept)")


def finish(game):
    """After teardown: <game>/game/video/rec-*.mp4 -> <game>/video/<game>.mp4 (+ -4x.mp4), with the image's ffmpeg.
    The raw fragments are removed on success, else moved next to the output for a manual remux."""
    gid = game.spec["game_id"]
    raw, out = os.path.join(game.dir, "game", "video"), os.path.join(game.dir, "video")
    info = {"base_image": game.opt.get("watch_base_image"), "image": game.opt.get("DFBENCH_GAME_IMAGE"),
            "comparable": False, "note": NOTE}
    game.rec["watch"] = info
    if not os.path.isdir(raw) or not any(f.startswith("rec-") for f in os.listdir(raw)):
        info["error"] = "no recording (DF never started?)"
        log(f"{gid}: watch: no recording")
        return info
    os.makedirs(out, exist_ok=True)
    args = ["/v/raw", "/v/out", gid] + ([] if game.opt.get("watch_4x", True) else ["--no-4x"])
    r = sh(["docker", "run", "--rm", "--platform", "linux/amd64", "--network", "none", "--entrypoint",
            "/opt/dfwatch/finish.sh", "-v", f"{raw}:/v/raw", "-v", f"{out}:/v/out", game.opt["DFBENCH_GAME_IMAGE"],
            *args], env=clean_env(), timeout=1800, check=False)
    probe = {}
    try:
        probe = json.loads((r.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        pass
    mp4 = os.path.join(out, f"{gid}.mp4")
    if r.returncode or not os.path.exists(mp4):
        info["error"] = f"finish.sh exited {r.returncode}: {(r.stderr or r.stdout or '')[-400:]}"
        for f in os.listdir(raw):
            shutil.move(os.path.join(raw, f), os.path.join(out, f))
        log(f"{gid}: watch: post-processing failed; raw recording kept in {out}")
        return info
    shutil.rmtree(raw, ignore_errors=True)
    st = (probe.get("streams") or [{}])[0]
    info.update({"video": os.path.relpath(mp4, game.dir), "frames": int(st.get("nb_read_packets") or 0),
                 "width": st.get("width"), "height": st.get("height"),
                 "duration_s": round(float((probe.get("format") or {}).get("duration") or 0), 1)})
    fast = os.path.join(out, f"{gid}-4x.mp4")
    if os.path.exists(fast):
        info["video_4x"] = os.path.relpath(fast, game.dir)
    print(f"[watch] {gid}: {mp4} ({info['frames']} frames, {info['duration_s']} s, {info['width']}x{info['height']})"
          + (f"\n[watch] {gid}: {fast} (4x)" if os.path.exists(fast) else ""), flush=True)
    return info


# ---- --watch-live: a view-only VNC on 127.0.0.1, relayed through `docker compose exec` (no published port)
class PortPool:
    """Hands out 127.0.0.1 ports from `start` up (one per game playing at once)."""

    def __init__(self, start):
        self.start, self.used, self.lock = start, set(), threading.Lock()

    def take(self):
        with self.lock:
            p = self.start
            while p in self.used:
                p += 1
            self.used.add(p)
            return p

    def give(self, p):
        with self.lock:
            self.used.discard(p)


class LiveView:
    """A TCP listener on 127.0.0.1:<port>; each connection runs docker/watch/vnc_stdio.sh in the game container
    (`compose exec -T`: a view-only x11vnc on the container's loopback, bridged to stdin/stdout) and pipes the socket
    through it. Password: a fresh random one per game (VNC auth, 8 characters)."""

    def __init__(self, game, pool):
        self.game, self.pool = game, pool
        self.password = secrets.token_urlsafe(6)[:8]
        self.port = pool.take()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(("127.0.0.1", self.port))
        except OSError:
            pool.give(self.port)
            raise
        self.sock.listen(4)
        self.closed = False
        threading.Thread(target=self._accept, daemon=True).start()
        print(f"[watch] {game.spec['game_id']}: live view (view-only) at vnc://127.0.0.1:{self.port} password "
              f"{self.password}  (DF appears once the game server has started it)", flush=True)

    def _cmd(self):
        g = self.game
        return ["docker", "compose", *g._files(), "--project-directory", g.dir, "exec", "-T", "game",
                "/opt/dfwatch/vnc_stdio.sh", self.password]

    def _accept(self):
        while not self.closed:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        try:
            p = subprocess.Popen(self._cmd(), env=self.game._env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, bufsize=0)
        except OSError:
            conn.close()
            return

        def up():
            try:
                for chunk in iter(lambda: conn.recv(65536), b""):
                    p.stdin.write(chunk)
            except OSError:
                pass
            finally:
                try:
                    p.stdin.close()
                except OSError:
                    pass

        threading.Thread(target=up, daemon=True).start()
        try:
            for chunk in iter(lambda: p.stdout.read(65536), b""):
                conn.sendall(chunk)
        except OSError:
            pass
        finally:
            conn.close()
            p.kill()
            p.wait()

    def close(self):
        self.closed = True
        try:
            self.sock.close()
        finally:
            self.pool.give(self.port)


def start_live(game):
    pool = game.opt.get("_watch_ports")
    if not pool:
        return None
    try:
        return LiveView(game, pool)
    except OSError as e:
        game.rec["notes"].append(f"watch: live view not started: {e}")
        log(f"{game.spec['game_id']}: watch: live view not started: {e}")
        return None
