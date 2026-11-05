#!/usr/bin/env python3
"""A fake model gateway for the season-0 runner: the interface of gateway/gateway.py (gateway/README.md) with canned
tool calls instead of an upstream. `POST /v1/chat/completions` (OpenAI format, non-streaming, model allowlist),
`GET /status`, a usage.jsonl ledger (schema dfbench-usage/1, refusals included, `outcome` per row) and the status file.

Canned policy: a fixed opening (brew, a Still, farms, beds, chairs, a Craftsdwarf's workshop), then advance_days(7)
forever. Only tools offered in the request are called.

Env, as the real gateway: GATEWAY_BUDGET_USD (0.50), GATEWAY_RUN_ID, GATEWAY_LEDGER (/out/usage.jsonl),
GATEWAY_STATUS_FILE (/out/gateway-status.json), OPENROUTER_API_KEY (checked non-empty only with FAKE_REQUIRE_KEY=1;
popped from the environment as the real one does). Fake-only: FAKE_THROTTLE_S (a simulated provider wait on every 5th
call), FAKE_COST_PER_CALL (USD; default priced from tokens), FAKE_USAGE_MISSING_AT (call index that fails closed),
FAKE_TIMEOUT_EVERY (every Nth call is a charged, retryable 504 upstream_timeout; more than
GATEWAY_MAX_UPSTREAM_TIMEOUTS (5) of them block the game as upstream_unreliable).
  python3 fake_gateway.py [--port 8080]
"""
import argparse, hashlib, json, os, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "z-ai/glm-5.3-flash"
PRICES = {"input": 0.15, "cached_input": 0.03, "output": 0.50}       # USD / 1M tokens, as gateway/prices.json
PRICE_HASH = "sha256:fake-price-table"
OPENING = [("add_order", {"recipe": "brew_drink", "amount": 10}), ("build_workshop", {"type": "Still", "site": "W1"}),
           ("build_farm", {"site": "F1"}), ("build_farm", {"site": "F2"}), ("dig_room", {"site": "R1"}),
           ("place_furniture", {"kind": "bed", "site": "A1", "count": 30}),
           ("place_furniture", {"kind": "chair", "site": "A1", "count": 30}),
           ("build_workshop", {"type": "Craftsdwarfs", "site": "W2"})]
KEY = os.environ.pop("OPENROUTER_API_KEY", "")


class St:
    lock = threading.RLock()
    seq = calls = refused = usage_unknown = timeouts = 0
    spent = throttle = 0.0
    blocked_reason = None
    started = time.time()


def budget():
    return float(os.environ.get("GATEWAY_BUDGET_USD", "0.50"))


def status():
    return {"schema": "dfbench-gateway-status/1", "run_id": os.environ.get("GATEWAY_RUN_ID", ""),
            "budget_usd": budget(), "spent_usd": round(St.spent, 8), "remaining_usd": round(max(0, budget() - St.spent), 8),
            "reserved_usd": 0, "inflight": 0, "calls": St.calls, "calls_refused": St.refused,
            "calls_upstream_error": 0, "upstream_timeouts": St.timeouts, "usage_unknown_calls": St.usage_unknown,
            "provider_mismatches": 0,
            "throttle_wait_total_s": round(St.throttle, 3), "blocked": St.blocked_reason is not None,
            "blocked_reason": St.blocked_reason, "price_table_hash": PRICE_HASH,
            "models": {MODEL: {"provider": {"order": ["together"], "allow_fallbacks": False}}},
            "upstream_host": "fake", "started_at": St.started, "fake": True}


def write(row):
    """Append a ledger row and rewrite the status file (both under the lock)."""
    with St.lock:
        St.seq += 1
        row = {"schema": "dfbench-usage/1", "seq": St.seq, "run_id": os.environ.get("GATEWAY_RUN_ID", ""),
               "price_table_hash": PRICE_HASH, "model": MODEL, "provider": "fake", **row,
               "spent_after_usd": round(St.spent, 8)}
        p = os.environ.get("GATEWAY_LEDGER", "/out/usage.jsonl")
        with open(p, "a") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
        sp = os.environ.get("GATEWAY_STATUS_FILE", "/out/gateway-status.json")
        if sp:
            with open(sp + ".tmp", "w") as f:
                json.dump(status(), f)
            os.replace(sp + ".tmp", sp)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip("/") == "/status":
            with St.lock:
                return self._send(200, status())
        self._send(404, {"error": {"code": "not_found"}})

    def do_POST(self):
        t0 = time.time()
        if self.path.rstrip("/") != "/v1/chat/completions":
            return self._send(404, {"error": {"code": "not_found"}})
        if os.environ.get("FAKE_REQUIRE_KEY") == "1" and not KEY:
            return self._send(500, {"error": {"code": "no_key", "message": "gateway has no provider key"}})
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            return self._send(400, {"error": {"code": "bad_json"}})
        base = {"t_start": t0, "request_bytes": len(raw), "n_messages": len(body.get("messages") or []),
                "n_tools": len(body.get("tools") or []),
                "request_digest": "sha256:" + hashlib.sha256(raw or b"").hexdigest()}
        if body.get("model") != MODEL:
            write({**base, "outcome": "refused_model", "t_end": time.time(), "latency_s": 0, "cost_usd": 0})
            return self._send(400, {"error": {"code": "model_not_allowed", "message": f"only {MODEL}"}})
        if body.get("stream"):
            write({**base, "outcome": "refused_stream", "t_end": time.time(), "latency_s": 0, "cost_usd": 0})
            return self._send(400, {"error": {"code": "stream_unsupported"}})
        with St.lock:
            if St.blocked_reason in ("usage_missing", "upstream_unreliable"):
                St.refused += 1
                write({**base, "outcome": "refused_" + St.blocked_reason, "t_end": time.time(), "latency_s": 0,
                       "cost_usd": 0})
                return self._send(503, {"error": {"code": "gateway_blocked", "reason": St.blocked_reason}})
            if St.spent >= budget():
                St.refused += 1
                St.blocked_reason = "budget_exhausted"
                write({**base, "outcome": "refused_budget_exhausted", "t_end": time.time(), "latency_s": 0, "cost_usd": 0})
                return self._send(402, {"error": {"code": "budget_exhausted", "spent_usd": St.spent,
                                                  "budget_usd": budget()}})
            i = St.calls
            St.calls += 1
        if os.environ.get("FAKE_USAGE_MISSING_AT") and i == int(os.environ["FAKE_USAGE_MISSING_AT"]):
            with St.lock:
                St.usage_unknown += 1
                St.blocked_reason = "usage_missing"
                write({**base, "outcome": "usage_missing", "t_end": time.time(), "latency_s": 0, "cost_usd": None,
                       "cost_upper_bound_usd": 0.01})
            return self._send(502, {"error": {"code": "usage_missing"}})
        every = int(os.environ.get("FAKE_TIMEOUT_EVERY") or 0)
        if every and i % every == every - 1:
            with St.lock:
                St.timeouts += 1
                St.spent += 0.001
                if St.timeouts > int(os.environ.get("GATEWAY_MAX_UPSTREAM_TIMEOUTS") or 5):
                    St.blocked_reason = "upstream_unreliable"
                write({**base, "outcome": "upstream_timeout", "failure": "provider_reported", "t_end": time.time(),
                       "latency_s": 0, "cost_usd": 0.001, "cost_basis": "prompt_estimate", "throttle_wait_s": 0})
            return self._send(504, {"error": {"code": "upstream_timeout", "retryable": True}})
        offered = {t.get("function", {}).get("name") for t in body.get("tools") or []}
        opening = [c for c in OPENING if c[0] in offered]
        name, args = opening[i] if i < len(opening) else ("advance_days", {"days": 7})
        if offered and name not in offered:
            name, args = sorted(offered)[0], {}
        throttle = float(os.environ.get("FAKE_THROTTLE_S", "0")) if i % 5 == 4 else 0.0
        if throttle:
            time.sleep(throttle)
        p_tok = max(1, len(raw) // 4)
        c_tok = 20 + len(json.dumps(args)) // 4
        cached = p_tok // 2 if i else 0
        cost = float(os.environ["FAKE_COST_PER_CALL"]) if os.environ.get("FAKE_COST_PER_CALL") else (
            ((p_tok - cached) * PRICES["input"] + cached * PRICES["cached_input"] + c_tok * PRICES["output"]) / 1e6)
        with St.lock:
            St.spent += cost
            St.throttle += throttle
            if St.spent >= budget():
                St.blocked_reason = "budget_exhausted"
            write({**base, "outcome": "ok", "t_end": time.time(), "latency_s": round(time.time() - t0, 4),
                   "prompt_tokens": p_tok, "cached_tokens": cached, "completion_tokens": c_tok, "reasoning_tokens": 0,
                   "cost_usd": round(cost, 10), "upstream_status": 200, "attempts": 1 + bool(throttle),
                   "retry_statuses": [429] if throttle else [], "throttle_wait_s": throttle, "finish_reason": "tool_calls",
                   "generation_id": f"fake-{i}", "tools_called": [name]})
        self._send(200, {
            "id": f"fake-{i}", "object": "chat.completion", "created": int(t0), "model": MODEL, "provider": "fake",
            "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": f"call_{i}", "type": "function",
                                "function": {"name": name, "arguments": json.dumps(args)}}]}}],
            "usage": {"prompt_tokens": p_tok, "completion_tokens": c_tok, "total_tokens": p_tok + c_tok,
                      "prompt_tokens_details": {"cached_tokens": cached}}})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    a = ap.parse_args()
    write_status = os.environ.get("GATEWAY_STATUS_FILE", "/out/gateway-status.json")
    if write_status:
        with open(write_status, "w") as f:
            json.dump(status(), f)
    print(f"fake gateway on :{a.port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
