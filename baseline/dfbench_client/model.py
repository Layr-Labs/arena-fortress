"""Client for the model through the trusted gateway: OpenAI-compatible chat completions with tools. stdlib only.

    m = ModelClient("http://gateway:8080/v1", "z-ai/glm-5.3-flash")
    resp = m.chat(messages, tools=tools, tool_choice="required", temperature=0, max_tokens=4000)
    msg = resp["choices"][0]["message"]          # msg.get("tool_calls"), msg.get("content")
    m.usage                                     # running totals: calls, prompt/completion tokens, cost_usd
    m.gateway_status()                          # the gateway's GET /status (credits used/left), or None

Retries (bounded, `max_retries`): connection errors and timeouts, HTTP 5xx (including the gateway's 504
`upstream_timeout`, a hung or lost provider call it has charged an estimate for), and 429 (waiting Retry-After,
capped). The gateway reports provider throttling and hung calls separately, so those waits don't count against the
game's wall cap. Not retried: BudgetExhausted (HTTP 402, an error that names the budget/credits, or the gateway's
503 `gateway_blocked`: model calls are over for this game), ContextTooLong, other 4xx.

Cost: the gateway prices every call at the pinned reference rates and is the authority. This client adds up
`usage.cost` when the gateway returns it; otherwise it estimates from tokens at `prices` (USD per million tokens,
{"input", "cached_input", "output"}), which you should set from the challenge's published price table.
"""
import json
import re
import socket
import time
import urllib.error
import urllib.request

from .errors import BudgetExhausted, ContextTooLong, ModelError

CONTEXT_RE = re.compile(r"context (window|length)|prompt too long|maximum context|too many tokens", re.I)
BUDGET_RE = re.compile(r"budget|credit|insufficient|quota", re.I)


class ModelClient:
    def __init__(self, base_url, model, api_key="placeholder", timeout=600.0, max_retries=4,
                 rate_limit_base_s=5.0, prices=None, log=None, retry_sleep_s=2.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limit_base_s = rate_limit_base_s   # minimum wait after a 429 (doubles per attempt, capped at 120 s)
        self.retry_sleep_s = retry_sleep_s           # base wait after a connection error or 5xx
        self.prices = prices
        self.log = log
        self.usage = {"calls": 0, "failed_calls": 0, "prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0,
                      "reasoning_tokens": 0, "cost_usd": 0.0, "cost_source": None, "rate_limit_waits": 0,
                      "rate_limit_wait_s": 0.0}

    def chat(self, messages, tools=None, **params):
        """POST /chat/completions. params go into the body as given (tool_choice, temperature, max_tokens, seed,
        reasoning, ...). Returns the response dict; raises ModelError and its subclasses."""
        body = {"model": self.model, "messages": messages, **params}
        if tools:
            body["tools"] = tools
        attempt = 0
        while True:
            t0 = time.time()
            try:
                resp = self._post("/chat/completions", body)
                if not resp.get("choices"):   # an error inside a 200 body
                    raise ModelError("no choices: " + json.dumps(resp.get("error") or resp)[:400], 200, resp)
                self._count(resp)
                if self.log:
                    self.log({"t": t0, "latency_s": round(time.time() - t0, 3), "usage": resp.get("usage"),
                              "finish_reason": resp["choices"][0].get("finish_reason")})
                return resp
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")
                e.close()
                err = _classify(e.code, text)
                if e.code == 429 and not isinstance(err, BudgetExhausted) and attempt < self.max_retries:
                    wait = _retry_after(e.headers, attempt, self.rate_limit_base_s)
                    self.usage["rate_limit_waits"] += 1
                    self.usage["rate_limit_wait_s"] += wait
                    attempt += 1
                    time.sleep(wait)
                    continue
                if e.code >= 500 and not isinstance(err, BudgetExhausted) and attempt < self.max_retries:
                    attempt += 1
                    time.sleep(max(_retry_after(e.headers, 0, 0.0) if e.code == 504 else 0.0,
                                   min(self.retry_sleep_s * attempt, 20.0)))
                    continue
                self.usage["failed_calls"] += 1
                raise err from None
            except ModelError as e:
                if attempt < self.max_retries:
                    attempt += 1
                    time.sleep(min(self.retry_sleep_s * attempt, 20.0))
                    continue
                self.usage["failed_calls"] += 1
                raise
            except (urllib.error.URLError, ConnectionError, socket.timeout, OSError, ValueError) as e:
                if attempt < self.max_retries:
                    attempt += 1
                    time.sleep(min(self.retry_sleep_s * attempt, 20.0))
                    continue
                self.usage["failed_calls"] += 1
                raise ModelError(f"gateway unreachable: {e}") from e

    def gateway_status(self):
        """The gateway's GET /status (per-game credits used and left), if it has one; None otherwise. Tries
        <root>/status, then <base_url>/status."""
        root = re.sub(r"/v1/?$", "", self.base_url)
        for url in dict.fromkeys([root + "/status", self.base_url + "/status"]):
            try:
                req = urllib.request.Request(url, headers=self._headers())
                with urllib.request.urlopen(req, timeout=10) as r:
                    d = json.loads(r.read().decode())
                    if isinstance(d, dict):
                        return d
            except Exception:
                continue
        return None

    # --- internals ----------------------------------------------------------------------------------------------
    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = "Bearer " + self.api_key
        return h

    def _post(self, path, body):
        req = urllib.request.Request(self.base_url + path, json.dumps(body).encode(), self._headers())
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    def _count(self, resp):
        u = resp.get("usage") or {}
        self.usage["calls"] += 1
        p, c = u.get("prompt_tokens") or 0, u.get("completion_tokens") or 0
        cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        self.usage["prompt_tokens"] += p
        self.usage["completion_tokens"] += c
        self.usage["cached_tokens"] += cached
        self.usage["reasoning_tokens"] += (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        if isinstance(u.get("cost"), (int, float)):
            self.usage["cost_usd"] += u["cost"]
            self.usage["cost_source"] = "gateway"
        elif self.prices:
            pr = self.prices
            self.usage["cost_usd"] += ((p - cached) * pr.get("input", 0) + cached * pr.get("cached_input", pr.get("input", 0))
                                       + c * pr.get("output", 0)) / 1e6
            self.usage["cost_source"] = self.usage["cost_source"] or "estimate"


def _classify(code, text):
    if code == 402 or (code in (403, 429) and BUDGET_RE.search(text)) or (code == 503 and "gateway_blocked" in text):
        return BudgetExhausted(f"HTTP {code}: {text[:300]}", code, text)
    if 400 <= code < 500 and CONTEXT_RE.search(text):
        return ContextTooLong(f"HTTP {code}: {text[:300]}", code, text)
    return ModelError(f"HTTP {code}: {text[:400]}", code, text)


def _retry_after(headers, attempt, base):
    try:
        wait = float(headers.get("Retry-After") or 0)
    except (TypeError, ValueError):
        wait = 0.0
    return min(max(wait, base * 2 ** min(attempt, 4)), 120.0)
