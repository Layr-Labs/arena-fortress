"""The HTTP API of docs/GAME-API.md §3 over a rules.Game (stdlib http.server). One game per process.

Harness endpoints: GET /task, GET /observe, POST /act, GET /query/<name>?k=v, GET /events?since_tick=N, GET /health.
Admin endpoints (the runner and the gateway; header X-Admin-Token = $GAMEAPI_ADMIN_TOKEN, or from localhost when no
token is set): POST /finish {"reason": "harness_exited"|"credits_exhausted"|"runner"} [?wait=1],
POST /admin/throttle {"seconds": s} | {"total_s": gateway throttle_wait_total_s}, GET /admin/summary.
"""
import hmac, json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from gameapi.server import rules
from gameapi.server.rules import ApiError

MAX_BODY = 1 << 20


def _num(v):
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return {"true": True, "false": False}.get(v, v)


def make_handler(game, admin_token=None):
    admin_token = admin_token if admin_token is not None else os.environ.get("GAMEAPI_ADMIN_TOKEN") or None

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "dfbench-game/v0"

        def log_message(self, fmt, *a):   # the api.jsonl log is the record; keep stderr quiet
            pass

        def _send(self, status, body):
            data = json.dumps(body, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ApiError("bad_request", "body too large", status=413)
            raw = self.rfile.read(n) if n else b""
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except ValueError:
                raise ApiError("bad_request", "the body is not JSON", status=400)

        def _admin(self):
            if admin_token:
                return hmac.compare_digest(self.headers.get("X-Admin-Token") or "", admin_token)
            return self.client_address[0] in ("127.0.0.1", "::1")

        def _handle(self, method):
            t0 = time.monotonic()
            u = urlparse(self.path)
            path, qs = u.path.rstrip("/") or "/", {k: _num(v[-1]) for k, v in parse_qs(u.query).items()}
            req = None
            status, body = 200, None
            try:
                if path == "/health" and method == "GET":
                    return self._send(200, game.health())   # never blocks on the game lock, never logged
                req = self._body() if method == "POST" else (qs or None)
                if path in ("/finish", "/admin/throttle", "/admin/summary"):
                    if not self._admin():
                        raise ApiError("forbidden", "admin endpoint", status=403)
                    body = self._admin_call(method, path, req or {}, qs)
                else:
                    body = self._harness_call(method, path, req, qs)
            except ApiError as e:
                status = e.status
                body = {**game.envelope(), **e.body()}
                if e.code in ("action_limit", "hands_off", "game_over", "bad_arguments", "unknown_tool") \
                        and path == "/act" and not game.over:
                    body.setdefault("actions_left_today", game.actions_left())
            except Exception as e:   # noqa: BLE001
                status, body = 500, {**game.envelope(), "ok": False, "error_code": "internal_error",
                                     "error": f"{type(e).__name__}: {e}"[:300]}
            self._send(status, body)
            game.log(method, path, req, status, body, time.monotonic() - t0)

        def _harness_call(self, method, path, req, qs):
            if path == "/task" and method == "GET":
                with game.lock:
                    game._require_ready()
                    return {**game.envelope(), **game.task_info()}
            if path == "/observe" and method == "GET":
                with game.lock:
                    game.touch()
                    obs = game.observe()
                    return {**game.envelope(), "observation": obs}
            if path == "/act" and method == "POST":
                if not isinstance(req, dict):
                    raise ApiError("bad_request", "body must be {\"tool\": name, \"args\": {...}}", status=400)
                with game.lock:
                    game.touch()
                    r = game.act(req.get("tool"), req.get("args"))
                    return {**game.envelope(), **r}
            if path.startswith("/query/") and method == "GET":
                with game.lock:
                    game.touch()
                    name = path[len("/query/"):]
                    return {**game.envelope(), "query": name, "result": game.query(name, qs)}
            if path == "/events" and method == "GET":
                with game.lock:
                    game.touch()
                    since = qs.get("since_tick", 0)
                    if not isinstance(since, int):
                        raise ApiError("bad_arguments", "since_tick must be an integer")
                    return {**game.envelope(), "since_tick": since, **game.events(since)}
            raise ApiError("not_found", f"no endpoint {method} {path}", status=404)

        def _admin_call(self, method, path, req, qs):
            if path == "/finish" and method == "POST":
                reason = req.get("reason", "harness_exited")
                if qs.get("wait"):
                    with game.lock:
                        return game.finish(reason)
                game._require_ready()
                if not isinstance(reason, str) or not rules._REASON.match(reason):
                    raise ApiError("bad_arguments", "reason must be a short identifier")

                def run():
                    with game.lock:
                        try:
                            game.finish(reason)
                        except ApiError:
                            pass
                threading.Thread(target=run, daemon=True).start()
                return {**game.health(), "accepted": True}
            if path == "/admin/throttle" and method == "POST":
                with game.lock:
                    game.add_throttle(req.get("seconds"), req.get("total_s"))
                    return game.health()
            if path == "/admin/summary" and method == "GET":
                return {"summary": game.summary, **game.health()}
            raise ApiError("not_found", f"no endpoint {method} {path}", status=404)

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

    return Handler


def serve(game, host="0.0.0.0", port=8090, admin_token=None):
    srv = ThreadingHTTPServer((host, port), make_handler(game, admin_token))
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv
