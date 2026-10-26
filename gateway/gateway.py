#!/usr/bin/env python3
"""dfbench season-0 metering gateway: an OpenAI-compatible /v1/chat/completions proxy for one game.

Trusted component (docs/GAME-API.md §2, §4, §6). It holds the real provider key, enforces the model allowlist and
the provider pin, prices every call at a pinned price table, keeps the per-game credit budget, retries provider
throttling and accounts for the time spent waiting, turns a hung or lost provider call into a charged, retryable 504,
and appends one line per call to usage.jsonl.
See gateway/README.md for the interface and the rules. Python 3.12, stdlib only.

  OPENROUTER_API_KEY=... python3 gateway/gateway.py --listen 0.0.0.0:8080 --budget 0.50 \
      --ledger /out/usage.jsonl --status-file /out/gateway-status.json --run-id r1
"""
import argparse, hashlib, http.client, json, os, sys, threading, time, urllib.error, urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCHEMA_USAGE = "dfbench-usage/1"
SCHEMA_STATUS = "dfbench-gateway-status/1"
HERE = os.path.dirname(os.path.abspath(__file__))

# Request fields forwarded as sent. Everything else is dropped (and named in the ledger's dropped_fields): routing and
# billing identity (provider, models, route, transforms, preset, user, plugins, web_search_options, usage, ...)
# is the gateway's, and unknown fields could be either.
FORWARD_FIELDS = frozenset({
    "model", "messages", "tools", "tool_choice", "parallel_tool_calls", "temperature", "top_p", "top_k", "min_p",
    "top_a", "frequency_penalty", "presence_penalty", "repetition_penalty", "logit_bias", "logprobs", "top_logprobs",
    "max_tokens", "max_completion_tokens", "stop", "seed", "n", "response_format", "reasoning", "reasoning_effort",
    "include_reasoning", "verbosity"})
RETRYABLE = lambda s: s == 429 or 500 <= s <= 599
# Message content parts and tool types the gateway forwards. Anything else (image_url, file, input_audio, server-side
# tools) would make the provider fetch a URL or run a tool: a way in or out of the sealed game network.
CONTENT_PART_TYPES = frozenset({"text"})
TOOL_TYPES = frozenset({"function"})


def content_problem(req):
    """None, or why the request carries something other than text messages and function tools."""
    for i, m in enumerate(req.get("messages") or []):
        if not isinstance(m, dict):
            return f"messages[{i}] is not an object"
        c = m.get("content")
        if c is None or isinstance(c, str):
            continue
        if not isinstance(c, list):
            return f"messages[{i}].content must be a string or a list of text parts"
        for j, part in enumerate(c):
            if not isinstance(part, dict) or part.get("type") not in CONTENT_PART_TYPES:
                return f"messages[{i}].content[{j}]: only text parts are forwarded"
    tools = req.get("tools")
    if tools is not None:
        if not isinstance(tools, list):
            return "tools must be a list"
        for j, t in enumerate(tools):
            if not isinstance(t, dict) or t.get("type") not in TOOL_TYPES:
                return f"tools[{j}]: only function tools are forwarded"
    return None
ABANDONED = ("deadline", "idle_timeout", "connection_lost")


def env(name, default=None):
    v = os.environ.get(name)
    return default if v is None or v == "" else v


def load_prices(path):
    """The pinned price table (USD per million tokens) and its content hash (sha256 of the file's bytes)."""
    with open(path, "rb") as f:
        raw = f.read()
    table = json.loads(raw)
    models = table.get("models")
    if table.get("unit") != "per_million_tokens" or not isinstance(models, dict) or not models:
        raise ValueError(f"{path}: need unit per_million_tokens and a non-empty models map")
    for name, p in models.items():
        for k in ("input", "cached_input", "output"):
            if not isinstance(p.get(k), (int, float)) or p[k] < 0:
                raise ValueError(f"{path}: {name}.{k} must be a non-negative number")
        if not isinstance(p.get("max_output_tokens"), int) or p["max_output_tokens"] <= 0:
            raise ValueError(f"{path}: {name}.max_output_tokens must be a positive integer")
        pin = p.get("provider")
        if not isinstance(pin, dict) or not pin.get("order") or pin.get("allow_fallbacks") is not False:
            raise ValueError(f"{path}: {name}.provider must pin an order with allow_fallbacks false")
    return table, "sha256:" + hashlib.sha256(raw).hexdigest()


def price_usage(usage, price):
    """Tokens and cost from an upstream usage object, or None when it can't be priced (fail closed).

    Cached prompt tokens are priced at cached_input, the rest of prompt_tokens at input, completion_tokens (which
    include reasoning tokens on OpenRouter) at output. Reasoning tokens are recorded, not priced twice."""
    if not isinstance(usage, dict):
        return None
    pt, ct = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in (pt, ct)):
        return None
    pd = usage.get("prompt_tokens_details") or {}
    cd = usage.get("completion_tokens_details") or {}
    cached = pd.get("cached_tokens") or 0
    if not isinstance(cached, int) or cached < 0 or cached > pt:
        return None
    reasoning = cd.get("reasoning_tokens") or 0
    cost = ((pt - cached) * price["input"] + cached * price["cached_input"] + ct * price["output"]) / 1e6
    reported = usage.get("cost")
    return {"prompt_tokens": pt, "cached_tokens": cached,
            "cache_write_tokens": pd.get("cache_write_tokens") if isinstance(pd.get("cache_write_tokens"), int) else None,
            "completion_tokens": ct, "reasoning_tokens": reasoning if isinstance(reasoning, int) else None,
            "cost_usd": round(cost, 12),
            "openrouter_cost_usd": reported if isinstance(reported, (int, float)) and not isinstance(reported, bool)
            else None}


def _in_out_n(body_len, req, price, out_cap=None):
    msgs = req.get("messages") if isinstance(req.get("messages"), list) else []
    in_tok = body_len + 256 + 16 * len(msgs)
    out = req.get("max_completion_tokens", req.get("max_tokens"))
    cap = price["max_output_tokens"] if out_cap is None else min(out_cap, price["max_output_tokens"])
    out_tok = min(out, cap) if isinstance(out, int) and not isinstance(out, bool) and out > 0 else cap
    n = req.get("n") if isinstance(req.get("n"), int) and req.get("n", 0) > 0 else 1
    return in_tok, out_tok, n


def reservation_usd(body_len, req, price):
    """An upper bound on a call's cost, reserved while it is in flight: every body byte as an uncached input token
    (a token covers at least one byte), plus chat-template overhead, plus max_tokens (or the model's maximum
    output) of output, times n."""
    in_tok, out_tok, n = _in_out_n(body_len, req, price)
    return n * (in_tok * price["input"] + out_tok * price["output"]) / 1e6


def timeout_charge_usd(body_len, req, price, abandoned, out_cap):
    """What a call that ended without usage is charged (README "Hung and lost calls").

    provider-reported failure (a 200 whose body is an error, no choices, no usage): the prompt only, at the
    reservation's upper bound, since providers may bill prompt processing when nothing is generated.
    abandoned (the gateway's deadline or idle timeout, or the connection lost after sending): OpenRouter bills a
    non-streaming request it keeps processing in full, so the prompt bound plus output up to max_tokens, capped at
    out_cap tokens, times n. An estimate, not a bound: the harness gets no content either way."""
    in_tok, out_tok, n = _in_out_n(body_len, req, price, out_cap)
    if not abandoned:
        return in_tok * price["input"] / 1e6
    return n * (in_tok * price["input"] + out_tok * price["output"]) / 1e6


def _out_cap(req, price):
    """The output tokens a request may generate: max_tokens (or max_completion_tokens), else the model's maximum."""
    out = req.get("max_completion_tokens", req.get("max_tokens"))
    ok = isinstance(out, int) and not isinstance(out, bool) and out > 0
    return min(out, price["max_output_tokens"]) if ok else price["max_output_tokens"]


def fit_output_tokens(body_len, req, price, remaining):
    """The largest max_tokens whose reservation fits in `remaining` USD (at most the request's own), or None."""
    in_tok, out_tok, n = _in_out_n(body_len + 32, req, price)   # +32: the max_tokens field the clamp may add
    room = remaining * 1e6 / n - in_tok * price["input"]
    fit = int(room / price["output"]) if price["output"] > 0 else out_tok
    fit = min(fit, out_tok)
    return fit if fit >= 1 else None


def clamp_body(fwd, max_tokens, price):
    """fwd with its output capped at max_tokens -> (body bytes, reservation)."""
    fwd["max_tokens"] = max_tokens
    if "max_completion_tokens" in fwd:
        fwd["max_completion_tokens"] = max_tokens
    body = json.dumps(fwd, separators=(",", ":")).encode()
    return body, reservation_usd(len(body), fwd, price)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):   # never follow: the 3xx comes back as an HTTPError
        return None


class Gateway:
    def __init__(self, cfg):
        self.cfg = cfg
        self.prices, self.price_table_hash = load_prices(cfg.prices)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
        self.cond = threading.Condition()
        self.started_at = time.time()
        self.seq = 0
        self.spent = 0.0
        self.openrouter_cost = 0.0
        self.reserved = 0.0
        self.inflight = 0
        self.calls = 0                  # forwarded calls with a priced usage
        self.calls_refused = 0
        self.calls_upstream_error = 0
        self.upstream_timeouts = 0      # calls sent that came back with no usable response (charged, retryable)
        self.usage_unknown_calls = 0
        self.provider_mismatches = 0
        self.retries = 0
        self.throttle_total = 0.0
        self.tokens = {"prompt": 0, "cached": 0, "completion": 0, "reasoning": 0}
        self.usage_blocked = None       # reason string once a call's usage is unknown
        if cfg.ledger and os.path.exists(cfg.ledger):
            self._replay(cfg.ledger)

    # ---- state ------------------------------------------------------------------------------------------------
    def _replay(self, path):
        """Restore the counters from an existing ledger, so a restarted gateway can't reset the budget."""
        with open(path) as f:
            lines = f.readlines()
        for line in lines:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                self.usage_blocked = "ledger_unreadable"
                continue
            self._account(r)

    def _account(self, r):
        self.seq = max(self.seq, r.get("seq") or 0)
        self.spent += r.get("cost_usd") or 0.0
        self.openrouter_cost += r.get("openrouter_cost_usd") or 0.0
        self.throttle_total += r.get("throttle_wait_s") or 0.0
        self.retries += max(0, (r.get("attempts") or 1) - 1)
        out = r.get("outcome")
        if out == "ok":
            self.calls += 1
            for k in self.tokens:
                self.tokens[k] += r.get(k + "_tokens") or 0
            if r.get("provider_mismatch"):
                self.provider_mismatches += 1
        elif out == "usage_missing":
            self.usage_unknown_calls += 1
            self.usage_blocked = "usage_missing"
        elif out == "upstream_error":
            self.calls_upstream_error += 1
        elif out == "upstream_timeout":
            if not r.get("harness_attributable"):
                self.upstream_timeouts += 1
        elif out and out.startswith("refused"):
            self.calls_refused += 1

    def blocked_reason(self):
        if self.usage_blocked:
            return self.usage_blocked
        if self.upstream_timeouts > self.cfg.max_upstream_timeouts:
            return "upstream_unreliable"
        if self.spent >= self.cfg.budget:
            return "budget_exhausted"
        return None

    def status(self):
        with self.cond:
            return self._status()

    def _status(self):
        reason = self.blocked_reason()
        return {"schema": SCHEMA_STATUS, "run_id": self.cfg.run_id, "budget_usd": self.cfg.budget,
                "spent_usd": round(self.spent, 9), "remaining_usd": round(max(0.0, self.cfg.budget - self.spent), 9),
                "reserved_usd": round(self.reserved, 9), "inflight": self.inflight, "calls": self.calls,
                "calls_refused": self.calls_refused, "calls_upstream_error": self.calls_upstream_error,
                "upstream_timeouts": self.upstream_timeouts,
                "usage_unknown_calls": self.usage_unknown_calls, "provider_mismatches": self.provider_mismatches,
                "tokens": dict(self.tokens), "openrouter_cost_usd": round(self.openrouter_cost, 9),
                "retries": self.retries, "throttle_wait_total_s": round(self.throttle_total, 3),
                "blocked": reason is not None, "blocked_reason": reason,
                "price_table_hash": self.price_table_hash,
                "models": {m: {"provider": p["provider"]} for m, p in self.prices["models"].items()},
                "upstream_host": urllib.parse.urlsplit(self.cfg.upstream).hostname,
                "started_at": self.started_at}

    def _write_row(self, row):
        """Append a ledger row and refresh the status file. Caller holds self.cond."""
        self.seq += 1
        row = {"schema": SCHEMA_USAGE, "seq": self.seq, "run_id": self.cfg.run_id, **row,
               "price_table_hash": self.price_table_hash}
        self._account({**row, "seq": 0})
        row["spent_after_usd"] = round(self.spent, 12)
        if self.cfg.ledger:
            with open(self.cfg.ledger, "a") as f:
                f.write(json.dumps(row, separators=(",", ":")) + "\n")
                f.flush()
                os.fsync(f.fileno())
        if self.cfg.status_file:
            tmp = self.cfg.status_file + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self._status(), f, indent=1)
            os.replace(tmp, self.cfg.status_file)
        return row

    def log_refusal(self, t0, outcome, model, **extra):
        with self.cond:
            self._write_row({"t_start": t0, "t_end": time.time(), "outcome": outcome, "model": model,
                             "cost_usd": 0.0, "throttle_wait_s": 0.0, "attempts": 0, **extra})

    # ---- upstream ---------------------------------------------------------------------------------------------
    def _post(self, body):
        """One upstream attempt -> (status, headers, data, err). err: None; 'connect' (request not sent: safe to
        retry, not billed); 'deadline' or 'idle_timeout' (sent, abandoned by the gateway); 'connection_lost' (sent,
        the connection broke); 'oversized' (a response over max_response_bytes: billing unknown).

        upstream_timeout bounds each socket wait; upstream_deadline bounds the whole attempt, checked between reads
        (so an attempt ends within deadline + one idle wait), because a provider that sends its 200 headers early
        can hold the body for minutes."""
        req = urllib.request.Request(self.cfg.upstream + "/chat/completions", body, {
            "Content-Type": "application/json", "Authorization": "Bearer " + self.cfg.key,
            "X-Title": "dfbench-gateway"}, method="POST")
        deadline = time.monotonic() + self.cfg.upstream_deadline
        try:
            with self.opener.open(req, timeout=min(self.cfg.upstream_timeout, self.cfg.upstream_deadline)) as r:
                chunks, total = [], 0
                while True:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        return r.status, r.headers, b"", "deadline"
                    c = r.read1(65536)
                    if not c:
                        break
                    total += len(c)
                    if total > self.cfg.max_response_bytes:
                        return r.status, r.headers, b"", "oversized"
                    chunks.append(c)
                return r.status, r.headers, b"".join(chunks), None
        except urllib.error.HTTPError as e:
            try:
                data = e.read(self.cfg.max_response_bytes)
            except Exception:
                data = b""
            return e.code, e.headers, data, None
        except urllib.error.URLError:
            return 0, {}, b"", "connect"
        except TimeoutError:
            return 0, {}, b"", ("deadline" if time.monotonic() >= deadline - 0.05 else "idle_timeout")
        except (OSError, http.client.HTTPException):
            return 0, {}, b"", "connection_lost"

    def _backoff(self, attempt, headers):
        try:
            ra = float((headers or {}).get("Retry-After") or "")
        except (TypeError, ValueError):
            ra = None
        if ra is not None and ra >= 0:
            return min(ra, self.cfg.retry_after_cap)
        return min(self.cfg.retry_base * 2 ** (attempt - 1), self.cfg.retry_after_cap)

    def call_upstream(self, body):
        """Forward with bounded retries on 429/5xx/connection failures. Returns the last attempt's result plus
        attempts, throttle_wait_s (failed attempts' durations + backoff sleeps), retry_statuses, last latency."""
        attempts, throttle, retry_statuses = 0, 0.0, []
        t429 = 0.0                       # the part of `throttle` spent on 429s (rate limits)
        while True:
            attempts += 1
            ta = time.monotonic()
            status, headers, data, err = self._post(body)
            dt = time.monotonic() - ta
            retryable = err == "connect" or (err is None and RETRYABLE(status))
            if not retryable:
                break
            is429 = err is None and status == 429
            wait = self._backoff(attempts, headers)
            if attempts >= self.cfg.retry_attempts or throttle + dt + wait > self.cfg.retry_max_wait:
                throttle += dt           # the failed final attempt is provider time too
                t429 += dt if is429 else 0.0
                break
            throttle += dt
            retry_statuses.append(status if err is None else err)
            time.sleep(wait)
            throttle += wait
            t429 += (dt + wait) if is429 else 0.0
        threading.current_thread()._dfb_t429 = t429   # per request thread (ThreadingHTTPServer)
        return status, headers, data, err, attempts, throttle, retry_statuses, dt


# ---- HTTP -----------------------------------------------------------------------------------------------------
def error_body(code, message, **extra):
    return {"error": {"type": code, "code": code, "message": message, **extra}}


class Handler(BaseHTTPRequestHandler):
    gw: Gateway = None
    timeout = 120                      # client socket timeout
    server_version = "dfbench-gateway"
    sys_version = ""

    def log_message(self, *a):         # no access log (paths are fixed; nothing useful, nothing secret)
        pass

    def reply(self, status, obj=None, raw=None, retry_after=None):
        data = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        if retry_after is not None:
            self.send_header("Retry-After", str(retry_after))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/status":
            return self.reply(200, self.gw.status())
        if self.path == "/v1/chat/completions":
            return self.reply(405, error_body("method_not_allowed", "POST only"))
        self.reply(404, error_body("not_found", "endpoints: POST /v1/chat/completions, GET /status"))

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            return self.reply(404, error_body("not_found", "endpoints: POST /v1/chat/completions, GET /status"))
        gw, cfg = self.gw, self.gw.cfg
        t0 = time.time()
        try:
            n = int(self.headers.get("Content-Length") or -1)
        except ValueError:
            n = -1
        if n < 0:
            self.close_connection = True
            return self.reply(411, error_body("length_required", "Content-Length required"))
        if n > cfg.max_body_bytes:
            self.close_connection = True
            gw.log_refusal(t0, "refused_too_large", None, request_bytes=n)
            return self.reply(413, error_body("request_too_large", f"body over {cfg.max_body_bytes} bytes"))
        raw = self.rfile.read(n)
        try:
            req = json.loads(raw)
            assert isinstance(req, dict)
        except (ValueError, AssertionError, UnicodeDecodeError):
            return self.reply(400, error_body("bad_request", "body must be a JSON object"))
        model = req.get("model")
        price = gw.prices["models"].get(model) if isinstance(model, str) else None
        if price is None:
            gw.log_refusal(t0, "refused_model", model if isinstance(model, str) else None)
            return self.reply(400, error_body("model_not_allowed", "allowed models: " +
                                              ", ".join(gw.prices["models"])))
        if req.get("stream"):
            gw.log_refusal(t0, "refused_stream", model)
            return self.reply(400, error_body("stream_unsupported", "streaming is not supported; send stream=false"))
        if not isinstance(req.get("messages"), list) or not req["messages"]:
            return self.reply(400, error_body("bad_request", "messages must be a non-empty list"))

        bad = content_problem(req)
        if bad:
            gw.log_refusal(t0, "refused_content", model)
            return self.reply(400, error_body("content_not_allowed", bad))

        fwd = {k: v for k, v in req.items() if k in FORWARD_FIELDS}
        dropped = sorted(k for k in req if k not in FORWARD_FIELDS and k != "stream")
        fwd["provider"] = price["provider"]
        fwd["usage"] = {"include": True}
        fwd["stream"] = False
        body = json.dumps(fwd, separators=(",", ":")).encode()
        digest = "sha256:" + hashlib.sha256(body).hexdigest()
        est = reservation_usd(len(body), fwd, price)
        meta = {"model": model, "request_digest": digest, "request_bytes": len(body),
                "n_messages": len(fwd["messages"]), "n_tools": len(fwd.get("tools") or []),
                "max_tokens": fwd.get("max_completion_tokens", fwd.get("max_tokens")),
                "reasoning": fwd.get("reasoning", fwd.get("reasoning_effort")),
                "dropped_fields": dropped, "reservation_usd": round(est, 9)}

        # admission: refuse when blocked or spent >= budget; otherwise admit when nothing is in flight or the
        # in-flight reservations plus this one fit in the budget; else wait for in-flight calls to finish.
        tq = time.monotonic()
        with gw.cond:
            while True:
                reason = gw.blocked_reason()
                if reason:
                    break
                if gw.inflight == 0 and gw.spent + est > cfg.budget:
                    # alone but over the remaining budget: clamp the output so the call's upper bound fits, so
                    # no call can spend past the budget (a huge max_tokens or n would otherwise run on our key)
                    clamp = fit_output_tokens(len(body), fwd, price, cfg.budget - gw.spent)
                    if clamp is None:
                        reason = "insufficient_budget"
                        break
                    body, est = clamp_body(fwd, clamp, price)
                    meta.update(clamped_max_tokens=clamp, request_bytes=len(body), reservation_usd=round(est, 9),
                                request_digest="sha256:" + hashlib.sha256(body).hexdigest(), max_tokens=clamp)
                    gw.inflight += 1
                    gw.reserved += est
                    break
                if gw.inflight == 0 or (gw.inflight < cfg.max_concurrency and
                                        gw.spent + gw.reserved + est <= cfg.budget):
                    gw.inflight += 1
                    gw.reserved += est
                    break
                gw.cond.wait(1.0)
            queue_wait = round(time.monotonic() - tq, 3)
            inflight_at_admit = gw.inflight      # this call included
            if reason:
                code = 402 if reason in ("budget_exhausted", "insufficient_budget") else 503
                gw._write_row({"t_start": t0, "t_end": time.time(), "outcome": "refused_" + reason,
                               "cost_usd": 0.0, "throttle_wait_s": 0.0, "attempts": 0, "queue_wait_s": queue_wait,
                               **meta})
                spent = round(gw.spent, 9)
                return self.reply(code, error_body(reason if code == 402 else "gateway_blocked",
                                                   f"model calls refused: {reason}", reason=reason,
                                                   spent_usd=spent, budget_usd=cfg.budget))

        t429 = 0.0
        threading.current_thread()._dfb_t429 = 0.0
        try:
            status, headers, data, err, attempts, throttle, retry_statuses, lat = gw.call_upstream(body)
            t429 = getattr(threading.current_thread(), "_dfb_t429", None) or 0.0
        except Exception as e:      # never leave a reservation behind
            status, headers, data, err, attempts, throttle, retry_statuses, lat = 0, {}, b"", "unknown", 1, 0.0, [], 0
            sys.stderr.write(f"gateway: upstream call raised {type(e).__name__}\n")
        # Rate limits the game's own parallelism caused are the harness's: time spent on 429s while more than
        # throttle_attrib_inflight calls of this game were in flight is not excluded from the wall cap and doesn't
        # count towards the throttling infra rule (red team: a harness could otherwise drive 429s on the shared key
        # to buy wall time or re-roll a game). Retries still happen either way.
        throttle_mine = 0.0
        if inflight_at_admit > cfg.throttle_attrib_inflight and t429 > 0:
            throttle_mine = min(throttle, t429)
            throttle -= throttle_mine

        resp, priced = None, None
        try:
            resp = json.loads(data) if data else None
        except ValueError:
            resp = None
        if isinstance(resp, dict):
            priced = price_usage(resp.get("usage"), price)

        row = {"t_start": t0, "upstream_status": status or None, "attempts": attempts,
               "throttle_wait_s": round(throttle, 3), "retry_statuses": retry_statuses, "queue_wait_s": queue_wait,
               "inflight_at_admit": inflight_at_admit, "throttle_wait_harness_s": round(throttle_mine, 3),
               "upstream_latency_s": round(lat, 3), **meta}
        if priced:                                   # billed (whatever the status): count it in full
            prov = resp.get("provider")
            want = price.get("provider_name")
            row.update(priced, outcome="ok" if status == 200 else "upstream_error",
                       provider=prov, generation_id=resp.get("id"),
                       provider_mismatch=bool(want and prov and str(prov).lower() != want.lower()),
                       finish_reason=((resp.get("choices") or [{}])[0] or {}).get("finish_reason"))
            if row["outcome"] == "upstream_error":
                row["error"] = str((resp.get("error") or {}).get("message", ""))[:200]
            row["exceeded_reservation"] = priced["cost_usd"] > est
            out_status, out_raw = status, data
        elif err == "connect" or (err is None and status != 200):
            # not sent, or rejected/failed upstream without usage: not billed
            row.update(outcome="upstream_error", cost_usd=0.0, error=_err_text(resp, data, err))
            if err == "connect":
                out_status, out_raw = 502, json.dumps(error_body("upstream_unreachable", "provider unreachable")).encode()
            elif 300 <= status < 400:
                out_status, out_raw = 502, json.dumps(error_body("upstream_redirect", "provider redirected")).encode()
            else:
                out_status, out_raw = status, data or json.dumps(error_body("upstream_error", f"HTTP {status}")).encode()
        elif err == "oversized":
            # a response over max_response_bytes (e.g. n and logprobs inflating it): the harness asked for it, so it
            # is charged the call's upper bound and the game goes on; not an infra failure, nothing blocked
            row.update(outcome="upstream_error", cost_usd=round(est, 12), cost_basis="reservation_oversized",
                       harness_attributable=True, error="response over max_response_bytes")
            out_status = 502
            out_raw = json.dumps(error_body("response_too_large", "the provider's response was over the gateway's "
                                            "size limit; charged the call's upper bound", charged_usd=row["cost_usd"]
                                            )).encode()
        elif err in ABANDONED or (err is None and _provider_failure(resp)):
            # sent, and no usable response: a hung call the gateway gave up on, a lost connection, or a 200 whose
            # body is the provider's own error. The harness got no content, so it is charged an estimate (not
            # failed closed) and may retry; the time spent is provider time, excluded from the wall cap like
            # throttling. More than max_upstream_timeouts of these in a game block it as infra.
            abandoned = err in ABANDONED
            charge = timeout_charge_usd(len(body), fwd, price, abandoned, cfg.abandon_output_tokens)
            # A call that asked for more output than infra_max_output_tokens can run past the deadline on its own:
            # its timeout is the harness's (charged, not excluded from the wall cap, not counted towards infra),
            # or a harness could re-roll a bad game by asking for long generations on purpose.
            mine = _out_cap(fwd, price) > cfg.infra_max_output_tokens
            row.update(outcome="upstream_timeout", failure=err or "provider_reported", cost_usd=round(charge, 12),
                       cost_basis="abandoned_estimate" if abandoned else "prompt_estimate",
                       harness_attributable=mine,
                       throttle_wait_s=round(throttle + (0.0 if mine else lat), 3), error=_err_text(resp, data, err))
            out_status = 504
            out_raw = json.dumps(error_body(
                "upstream_timeout", "the provider gave no usable response; charged an estimate, safe to retry",
                failure=row["failure"], charged_usd=row["cost_usd"], retryable=True,
                counted_as_infra=not mine)).encode()
        else:
            # a 200 without priceable usage (content may have been delivered), or an oversized response: fail closed
            row.update(outcome="usage_missing", cost_usd=None, cost_upper_bound_usd=round(est, 9),
                       error=_err_text(resp, data, err))
            out_status = 502
            out_raw = json.dumps(error_body("usage_missing", "the provider's usage was missing; model calls are "
                                            "blocked for the rest of this game")).encode()
        if cfg.debug:
            row["debug_request"] = fwd
            row["debug_response"] = data[:200000].decode(errors="replace")
        with gw.cond:
            gw.inflight -= 1
            gw.reserved = max(0.0, gw.reserved - est)
            row["t_end"] = time.time()
            row["latency_s"] = round(row["t_end"] - t0, 3)
            gw._write_row(row)
            gw.cond.notify_all()
        self.reply(out_status, raw=out_raw, retry_after=2 if out_status == 504 else None)

    def do_PUT(self):
        self.reply(405, error_body("method_not_allowed", "POST /v1/chat/completions or GET /status"))

    do_DELETE = do_PATCH = do_PUT


def _provider_failure(resp):
    """A response body that is the provider's error and nothing else: an error object, no choices, no usage."""
    return (isinstance(resp, dict) and isinstance(resp.get("error"), dict) and not resp.get("choices")
            and not resp.get("usage"))


def _err_text(resp, data, err):
    if err:
        return err
    if isinstance(resp, dict) and isinstance(resp.get("error"), dict):
        return str(resp["error"].get("message", ""))[:200]
    return data[:200].decode(errors="replace") if data else ""


# ---- config ---------------------------------------------------------------------------------------------------
class Config:
    pass


def parse_config(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a = p.add_argument
    a("--listen", default=env("GATEWAY_LISTEN", "127.0.0.1:8080"), help="host:port (env GATEWAY_LISTEN)")
    a("--upstream", default=env("GATEWAY_UPSTREAM", "https://openrouter.ai/api/v1"),
      help="OpenAI-compatible base URL (env GATEWAY_UPSTREAM)")
    a("--key-env", default=env("GATEWAY_KEY_ENV", "OPENROUTER_API_KEY"),
      help="name of the env var holding the provider key (env GATEWAY_KEY_ENV)")
    a("--prices", default=env("GATEWAY_PRICES", os.path.join(HERE, "prices.json")),
      help="pinned price table JSON; its models are the allowlist (env GATEWAY_PRICES)")
    a("--budget", type=float, default=float(env("GATEWAY_BUDGET_USD", "0.50")),
      help="per-game credits, USD at the pinned prices (env GATEWAY_BUDGET_USD)")
    a("--ledger", default=env("GATEWAY_LEDGER", "usage.jsonl"), help="usage.jsonl path (env GATEWAY_LEDGER)")
    a("--status-file", default=env("GATEWAY_STATUS_FILE"),
      help="JSON status rewritten after every call (env GATEWAY_STATUS_FILE)")
    a("--run-id", default=env("GATEWAY_RUN_ID", ""), help="recorded in every row (env GATEWAY_RUN_ID)")
    a("--max-body-bytes", type=int, default=int(env("GATEWAY_MAX_BODY_BYTES", str(16 << 20))))
    a("--max-response-bytes", type=int, default=int(env("GATEWAY_MAX_RESPONSE_BYTES", str(32 << 20))))
    a("--max-concurrency", type=int, default=int(env("GATEWAY_MAX_CONCURRENCY", "4")),
      help="in-flight calls per game; more wait in the gateway's queue, and queue time is the harness's (wall cap)")
    a("--throttle-attrib-inflight", type=int, default=int(env("GATEWAY_THROTTLE_ATTRIB_INFLIGHT", "2")),
      help="429 time counts as the provider's (excluded from the wall cap, towards the throttling infra rule) "
           "only for calls admitted with at most this many of the game's calls in flight")
    a("--upstream-timeout", type=float, default=float(env("GATEWAY_UPSTREAM_TIMEOUT_S", "180")),
      help="idle limit per socket wait on an upstream call (env GATEWAY_UPSTREAM_TIMEOUT_S)")
    a("--upstream-deadline", type=float, default=float(env("GATEWAY_UPSTREAM_DEADLINE_S", "320")),
      help="limit on one upstream attempt, checked between reads; just above OpenRouter's own ~300 s cut-off, "
           "which reports an error the provider may bill only as prompt (env GATEWAY_UPSTREAM_DEADLINE_S)")
    a("--max-upstream-timeouts", type=int, default=int(env("GATEWAY_MAX_UPSTREAM_TIMEOUTS", "5")),
      help="hung or lost calls tolerated per game; one more blocks the game as upstream_unreliable "
           "(env GATEWAY_MAX_UPSTREAM_TIMEOUTS)")
    a("--infra-max-output-tokens", type=int, default=int(env("GATEWAY_INFRA_MAX_OUTPUT_TOKENS", "8192")),
      help="a hung call counts towards upstream_unreliable (infra) and is excluded from the wall cap only if it asked "
           "for at most this many output tokens (env GATEWAY_INFRA_MAX_OUTPUT_TOKENS)")
    a("--abandon-output-tokens", type=int, default=int(env("GATEWAY_ABANDON_OUTPUT_TOKENS", "32768")),
      help="output tokens charged, at most, for a call the gateway abandoned (env GATEWAY_ABANDON_OUTPUT_TOKENS)")
    a("--retry-attempts", type=int, default=int(env("GATEWAY_RETRY_ATTEMPTS", "6")),
      help="attempts per call including the first (env GATEWAY_RETRY_ATTEMPTS)")
    a("--retry-max-wait", type=float, default=float(env("GATEWAY_RETRY_MAX_WAIT_S", "300")),
      help="max throttle time per call before giving up (env GATEWAY_RETRY_MAX_WAIT_S)")
    a("--retry-base", type=float, default=float(env("GATEWAY_RETRY_BASE_S", "2")))
    a("--retry-after-cap", type=float, default=float(env("GATEWAY_RETRY_AFTER_CAP_S", "60")))
    a("--allow-http-upstream", action="store_true", default=env("GATEWAY_ALLOW_HTTP_UPSTREAM") == "1",
      help="allow a non-TLS upstream (tests only)")
    a("--debug", action="store_true", default=env("GATEWAY_DEBUG") == "1",
      help="log full requests and responses into the ledger (never in the runner)")
    ns = p.parse_args(argv)
    cfg = Config()
    cfg.__dict__.update(vars(ns))
    cfg.upstream = cfg.upstream.rstrip("/")
    u = urllib.parse.urlsplit(cfg.upstream)
    if u.scheme != "https" and not (u.scheme == "http" and cfg.allow_http_upstream):
        p.error("upstream must be https (or --allow-http-upstream)")
    host, _, port = cfg.listen.rpartition(":")
    cfg.host, cfg.port = host or "127.0.0.1", int(port)
    if cfg.budget < 0 or cfg.max_concurrency < 1 or cfg.retry_attempts < 1:
        p.error("bad budget, concurrency or retry attempts")
    if cfg.upstream_timeout <= 0 or cfg.upstream_deadline <= 0 or cfg.max_upstream_timeouts < 0 \
            or cfg.abandon_output_tokens < 0:
        p.error("bad upstream timeout, deadline, timeout limit or abandon output tokens")
    cfg.key = os.environ.pop(cfg.key_env, "")       # keep it out of the environment from here on
    if not cfg.key:
        p.error(f"provider key missing: set {cfg.key_env}")
    return cfg


class Server(ThreadingHTTPServer):
    request_queue_size = 128          # the default backlog (5) resets bursts of parallel harness calls
    daemon_threads = True


def make_server(cfg):
    gw = Gateway(cfg)
    handler = type("BoundHandler", (Handler,), {"gw": gw})
    srv = Server((cfg.host, cfg.port), handler)
    srv.gw = gw
    return srv


def main(argv=None):
    cfg = parse_config(argv)
    srv = make_server(cfg)
    gw = srv.gw
    sys.stderr.write(f"dfbench gateway on {cfg.host}:{srv.server_address[1]} -> "
                     f"{urllib.parse.urlsplit(cfg.upstream).hostname}; models {list(gw.prices['models'])}; "
                     f"budget ${cfg.budget}; prices {gw.price_table_hash}; spent ${gw.spent:.6f}"
                     + ("; DEBUG LOGGING ON" if cfg.debug else "") + "\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
