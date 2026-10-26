"""Model providers: OpenRouter (default), Amazon Bedrock (Converse, bearer token) and a fake for tests. Stdlib HTTP,
redirects refused, keys read from the environment only and never logged. A provider returns raw text; parsing and
validation happen in the committee, so every provider is held to the same schema."""
import json, os, time, urllib.error, urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODELS = {"openrouter": "openai/gpt-6-sol", "bedrock": "us.anthropic.claude-opus-5-5", "fake": "fake/scripted"}
# USD per million tokens (input, output); used only where the provider doesn't report cost (Bedrock).
PRICES = {"us.anthropic.claude-opus-5-5": (4.0, 20.0), "global.anthropic.claude-opus-5-5": (4.0, 20.0),
          "us.anthropic.claude-sonnet-5-5": (2.0, 10.0)}


class ProviderError(Exception):
    """Transport, HTTP, quota or provider failure after retries: infra, the judgment holds."""


class OutputError(Exception):
    """The provider answered but not with one usable completion (truncated, refused, empty): re-ask once."""


class Completion:
    def __init__(self, text, model, usage, cost_usd, request_id=None, latency_ms=None, cost_source="provider"):
        self.text, self.model, self.usage, self.cost_usd = text, model, usage, cost_usd
        self.request_id, self.latency_ms, self.cost_source = request_id, latency_ms, cost_source


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        raise ProviderError("provider attempted a redirect; refused")


_OPENER = urllib.request.build_opener(_NoRedirect)


def _post(url, headers, body, timeout, retries, backoff, secret):
    last = None
    for attempt in range(retries + 1):
        t0 = time.monotonic()
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with _OPENER.open(req, timeout=timeout) as r:
                data = r.read()
                return json.loads(data.decode("utf-8")), dict(r.headers), int((time.monotonic() - t0) * 1000)
        except urllib.error.HTTPError as e:
            msg = ""
            try:
                err = json.loads(e.read(65536).decode("utf-8", "replace"))
                msg = str((err.get("error") or {}).get("message") or err.get("message") or "")[:300]
            except Exception:
                pass
            if secret:
                msg = msg.replace(secret, "[redacted]")
            last = f"HTTP {e.code}" + (f": {msg}" if msg else "")
            if e.code not in (408, 409, 425, 429) and e.code < 500:
                raise ProviderError(last)
            ra = e.headers.get("Retry-After") if e.headers else None
            wait = min(60.0, float(ra)) if ra and ra.isdigit() else backoff * (3 ** attempt)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            last = f"transport: {type(e).__name__}"
            wait = backoff * (3 ** attempt)
        if attempt < retries:
            time.sleep(wait)
    raise ProviderError(last or "provider failed")


class OpenRouter:
    name = "openrouter"

    def __init__(self, model=None, reasoning_effort="medium", max_tokens=16000, temperature=None, timeout=300,
                 retries=2, backoff=5.0, zdr=None):
        self.model = model or os.environ.get("DFBENCH_JUDGE_MODEL") or DEFAULT_MODELS["openrouter"]
        self.reasoning_effort, self.max_tokens, self.temperature = reasoning_effort, max_tokens, temperature
        self.timeout, self.retries, self.backoff = timeout, retries, backoff
        self.zdr = (os.environ.get("DFBENCH_JUDGE_ZDR", "false").lower() in ("1", "true", "yes")) if zdr is None else zdr
        # The judge's own key only: never the gateway's OPENROUTER_API_KEY (no fallback, by design).
        self._key = os.environ.get("DFBENCH_JUDGE_OPENROUTER_KEY") or ""
        if not self._key:
            raise ProviderError("no OpenRouter key (DFBENCH_JUDGE_OPENROUTER_KEY)")
        if any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in self._key):
            raise ProviderError("the OpenRouter key contains invalid characters")

    def config(self):
        return {"provider": self.name, "model": self.model, "reasoning_effort": self.reasoning_effort,
                "max_tokens": self.max_tokens, "temperature": self.temperature, "seed": 0, "zdr": self.zdr,
                "data_collection": "deny", "structured_output": "json_schema strict", "endpoint": OPENROUTER_URL}

    def complete(self, role, system, user, schema, meta, attempt):
        body = {"model": self.model, "stream": False, "max_tokens": self.max_tokens, "seed": 0,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": f"dfbench_judge_{role}", "strict": True, "schema": schema}},
                "provider": {"require_parameters": True, "data_collection": "deny", "zdr": self.zdr},
                "usage": {"include": True}}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if self.reasoning_effort:
            body["reasoning"] = {"effort": self.reasoning_effort, "exclude": True}
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json",
                   "User-Agent": "dfbench-judge/1", "X-Title": "dfbench season-0 judge"}
        data, hdrs, ms = _post(OPENROUTER_URL, headers, json.dumps(body).encode(), self.timeout, self.retries,
                               self.backoff, self._key)
        if isinstance(data.get("error"), dict):
            raise ProviderError(f"provider error: {str(data['error'].get('message', ''))[:200]}")
        ch = (data.get("choices") or [None])[0]
        if not isinstance(ch, dict):
            raise OutputError("no choices in the response")
        msg = ch.get("message") or {}
        u = data.get("usage") or {}
        usage = {"prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
                 "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                 "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens")}
        comp = Completion(msg.get("content") or "", data.get("model") or self.model, usage, u.get("cost"),
                          str(data.get("id", ""))[:100], ms)
        if msg.get("refusal"):
            raise _out("the model refused", comp)
        if ch.get("finish_reason") not in ("stop", None) and ch.get("native_finish_reason") != "completed":
            raise _out(f"incomplete completion (finish_reason {ch.get('finish_reason')})", comp)
        if msg.get("tool_calls"):
            raise _out("tool calls are not allowed", comp)
        return comp


def _out(msg, comp):
    e = OutputError(msg)
    e.completion = comp      # usage still counts
    return e


class Bedrock:
    name = "bedrock"

    def __init__(self, model=None, region=None, max_tokens=16000, temperature=0.0, timeout=300, retries=2,
                 backoff=5.0):
        self.model = model or os.environ.get("DFBENCH_JUDGE_BEDROCK_MODEL") or DEFAULT_MODELS["bedrock"]
        self.region = region or os.environ.get("DFBENCH_JUDGE_BEDROCK_REGION") or "us-east-1"
        self.max_tokens, self.temperature = max_tokens, temperature
        self.timeout, self.retries, self.backoff = timeout, retries, backoff
        self._key = os.environ.get("AWS_BEARER_TOKEN_BEDROCK") or ""
        if not self._key:
            raise ProviderError("no Bedrock key (AWS_BEARER_TOKEN_BEDROCK)")

    def url(self):
        return f"https://bedrock-runtime.{self.region}.amazonaws.com/model/{urllib.request.quote(self.model, safe='')}/converse"

    def config(self):
        return {"provider": self.name, "model": self.model, "region": self.region, "max_tokens": self.max_tokens,
                "temperature": self.temperature, "structured_output": "schema in prompt, validated locally",
                "price_per_mtok": PRICES.get(self.model)}

    def complete(self, role, system, user, schema, meta, attempt):
        body = {"system": [{"text": system}], "messages": [{"role": "user", "content": [{"text": user}]}],
                "inferenceConfig": {"maxTokens": self.max_tokens}}
        if self.temperature is not None:
            body["inferenceConfig"]["temperature"] = self.temperature
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        data, hdrs, ms = _post(self.url(), headers, json.dumps(body).encode(), self.timeout, self.retries,
                               self.backoff, self._key)
        u = data.get("usage") or {}
        usage = {"prompt_tokens": u.get("inputTokens"), "completion_tokens": u.get("outputTokens"),
                 "cached_tokens": u.get("cacheReadInputTokens")}
        price = PRICES.get(self.model)
        cost = None
        if price and usage["prompt_tokens"] is not None and usage["completion_tokens"] is not None:
            cost = (usage["prompt_tokens"] * price[0] + usage["completion_tokens"] * price[1]) / 1e6
        parts = (((data.get("output") or {}).get("message") or {}).get("content")) or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        comp = Completion(text, self.model, usage, cost, hdrs.get("x-amzn-RequestId") or hdrs.get("x-amzn-requestid"),
                          ms, "price_table" if cost is not None else "unknown")
        if data.get("stopReason") not in ("end_turn", "stop_sequence"):
            raise _out(f"incomplete completion (stopReason {data.get('stopReason')})", comp)
        return comp


# ---------------------------------------------------------------------------------------------------- fake

def benign(role, meta):
    """A well-formed, everything-is-fine answer for any role (what a naive or compromised model would say)."""
    if role in ("attribution", "fair_play", "contents"):
        out = {"assessment": "clean", "summary": "No issues found.", "findings": [], "injection_observed": False,
               "signal_reviews": [{"signal_id": s, "disposition": "benign", "reason": "benign"}
                                  for s in meta.get("signal_ids", [])]}
        if role == "attribution":
            out["inheritance"] = [{"context_id": c, "used": "yes" if c in meta.get("declared_ids", []) else "no",
                                   "what": ""} for c in meta.get("context_ids", [])]
            out["note_states_changes"] = "yes"
        return out
    if role == "defender":
        return {"defenses": [{"finding_id": f, "argument": "benign", "evidence": [], "concedes": False}
                             for f in meta.get("fatal_ids", [])]}
    return {"summary": "dismissed", "rulings": [{"finding_id": f, "ruling": "dismissed", "residual_severity": "none",
                                                 "reason": "benign", "evidence": []} for f in meta.get("fatal_ids", [])]}


class Fake:
    """responder(role, system, user, meta, attempt) -> str | dict | Exception (raised) | None (= benign)."""
    name = "fake"

    def __init__(self, responder=None, model="fake/scripted", cost_per_call=0.0):
        self.responder, self.model, self.cost_per_call = responder, model, cost_per_call
        self.calls = []

    @classmethod
    def from_script(cls, path):
        """JSON {role: [response, ...]}; a response is an object, a string, or "benign"; missing roles are benign."""
        with open(path, encoding="utf-8") as f:
            script = json.load(f)
        pos = {}

        def responder(role, system, user, meta, attempt):
            seq = script.get(role) or []
            i = pos.get(role, 0)
            pos[role] = i + 1
            r = seq[i] if i < len(seq) else "benign"
            if r == "benign":
                return None
            if r == "provider_error":
                return ProviderError("scripted provider error")
            return r
        return cls(responder)

    def config(self):
        return {"provider": self.name, "model": self.model}

    def complete(self, role, system, user, schema, meta, attempt):
        self.calls.append({"role": role, "system": system, "user": user, "meta": meta, "attempt": attempt})
        r = self.responder(role, system, user, meta, attempt) if self.responder else None
        if isinstance(r, Exception):
            raise r
        if r is None:
            r = benign(role, meta)
        text = r if isinstance(r, str) else json.dumps(r)
        return Completion(text, self.model, {"prompt_tokens": len(system + user) // 4,
                                              "completion_tokens": len(text) // 4}, self.cost_per_call)


def make(provider, model=None, **kw):
    if provider == "openrouter":
        return OpenRouter(model=model, **kw)
    if provider == "bedrock":
        kw.pop("reasoning_effort", None)
        kw.pop("zdr", None)
        return Bedrock(model=model, **kw)
    if provider == "fake":
        script = os.environ.get("DFBENCH_JUDGE_FAKE_SCRIPT")
        return Fake.from_script(script) if script else Fake()
    raise ProviderError(f"unknown provider {provider!r}")
