"""Client for the game API v0 (docs/GAME-API.md §3). stdlib only.

    g = GameClient("http://game:8090")
    task = g.task()                      # the task, rules, tool schemas, query list, reference manual
    obs = g.observe()                    # the facts-only observation (+ the envelope: day, tick, days_left, game_over)
    r = g.act("add_order", {"recipe": "brew_drink", "amount": 5})
    if not r["ok"]: print(r["error_code"], r["error"])
    r = g.advance(3)                     # == g.act("advance_days", {"days": 3})
    stocks = g.query("stocks")
    new = g.events(since_tick=obs["tick"])

Every response is the server's JSON dict, unchanged (the envelope fields `day`, `tick`, `days_left`, `game_over`,
`hands_off_in_days` included). `act` returns tool failures (`ok: false`, `error_code`, `error`) as results, because
the model should see them; the three rule rejections raise instead, because the loop must handle them:
ActionLimit (K actions used today), HandsOff (the window has begun), GameOver.

Retries: connection errors only (the server is down or restarting), with backoff. A request that reached the server
is never retried blindly: a POST /act that times out or loses its connection mid-way may have run, so it raises
GameUnavailable rather than risk running the action twice. HTTP errors are never retried.
"""
import http.client
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from .errors import GameAPIError, GameUnavailable, RULE_ERRORS


class GameClient:
    def __init__(self, base_url, timeout=60.0, advance_timeout=1800.0, retries=5, backoff_s=1.0, log=None):
        """base_url: DFBENCH_TASK.game_url. timeout: per request, except advance_days (advance_timeout: an advance
        runs game days and can take minutes). log: optional callable(dict) called once per request."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.advance_timeout = advance_timeout
        self.retries = retries
        self.backoff_s = backoff_s
        self.log = log
        self.last = None


    def task(self):
        return self._request("GET", "/task")

    def observe(self):
        return self._request("GET", "/observe")

    def act(self, tool, args=None):
        """One action. Returns the response dict ({"ok": bool, "result" | "error_code"/"error", "actions_left_today",
        + the envelope}). Raises ActionLimit, HandsOff or GameOver for those error codes."""
        body = {"tool": tool, "args": args if args is not None else {}}
        timeout = self.advance_timeout if tool == "advance_days" else self.timeout
        r = self._request("POST", "/act", body, timeout=timeout, accept_error_body=True)
        code = r.get("error_code") if not r.get("ok") else None
        if code in RULE_ERRORS:
            raise RULE_ERRORS[code](r.get("error") or code, body=r)
        return r

    def advance(self, days, stop_on=None):
        args = {"days": int(days)}
        if stop_on is not None:
            args["stop_on"] = list(stop_on)
        return self.act("advance_days", args)

    def query(self, name, **params):
        """A read-only query (§5.2): stocks, units, jobs, orders, buildings, zones, map, manager_order_types,
        workshop_types. Never moves time, never counts as an action."""
        q = "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}) if params else ""
        return self._request("GET", "/query/" + urllib.parse.quote(name) + q)

    def events(self, since_tick=0):
        return self._request("GET", f"/events?since_tick={int(since_tick)}")

    def health(self):
        return self._request("GET", "/health")

    def wait_ready(self, timeout_s=120.0):
        """Poll /health (then /task) until the server answers; the runner normally does this before starting us."""
        end = time.time() + timeout_s
        while True:
            try:
                return self._request("GET", "/health", retries=0)
            except GameAPIError:
                if time.time() > end:
                    raise
                time.sleep(1.0)


    def _request(self, method, path, body=None, timeout=None, accept_error_body=False, retries=None):
        url = self.base_url + path
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        retries = self.retries if retries is None else retries
        attempt = 0
        while True:
            t0 = time.time()
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                    raw, status = resp.read(), resp.status
            except urllib.error.HTTPError as e:
                raw, status = e.read(), e.code
                e.close()
            except (urllib.error.URLError, ConnectionError, socket.timeout, http.client.HTTPException, OSError) as e:
                if attempt < retries and _safe_to_retry(method, e):
                    attempt += 1
                    time.sleep(min(self.backoff_s * 2 ** (attempt - 1), 30.0))
                    continue
                raise GameUnavailable(f"{method} {path}: {e}") from e
            parsed = _json(raw)
            if self.log:
                self.log({"t": t0, "method": method, "path": path, "status": status,
                          "latency_s": round(time.time() - t0, 3), "request": body,
                          "response": parsed if parsed is not None else raw[:300].decode(errors="replace")})
            if not isinstance(parsed, dict):
                raise GameAPIError(f"{method} {path}: HTTP {status}, body is not a JSON object: {raw[:200]!r}", status)
            if status >= 400:

                if accept_error_body and ("error_code" in parsed or "ok" in parsed):
                    parsed.setdefault("ok", False)
                else:
                    raise GameAPIError(f"{method} {path}: HTTP {status}: {parsed.get('error') or parsed}", status, parsed)
            if "tick" in parsed or "day" in parsed:
                self.last = {k: parsed.get(k) for k in ("day", "tick", "days_left", "game_over", "hands_off_in_days")
                             if k in parsed}
            return parsed


def _safe_to_retry(method, e):
    """GETs are read-only: any connection error or timeout may be retried. A POST may already have run unless the
    connection was refused (nothing was sent)."""
    if method == "GET":
        return True
    reason = getattr(e, "reason", e)
    return isinstance(reason, ConnectionRefusedError)


def _json(raw):
    try:
        return json.loads(raw.decode() if isinstance(raw, bytes) else raw)
    except (ValueError, UnicodeDecodeError):
        return None
