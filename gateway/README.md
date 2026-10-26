# gateway/: the trusted metering gateway (season 0)

One gateway per game (`docs/GAME-API.md` §2). It sits between the untrusted harness and OpenRouter, holds the real
key, and is the only source of truth for what a game spent on the model. Python 3.12, stdlib only, one file
(`gateway.py`), plus the pinned price table (`prices.json`).

```text
harness --(placeholder key)--> gateway:8080/v1/chat/completions --(real key, provider pin)--> openrouter.ai
                                   |-- usage.jsonl (one row per call)
                                   `-- GET /status, gateway-status.json (spent, budget, throttle waits, blocked)
```

## Config (runner interface)

Every flag has an env var; flags win. The Docker image sets the first four env defaults shown.

| env | flag | default | meaning |
|---|---|---|---|
| `GATEWAY_LISTEN` | `--listen` | `127.0.0.1:8080` (image: `0.0.0.0:8080`) | host:port. The image listens on all interfaces of the container; the compose network decides who can reach it |
| `GATEWAY_PRICES` | `--prices` | `prices.json` next to the script | pinned price table; its models are the allowlist |
| `GATEWAY_LEDGER` | `--ledger` | `usage.jsonl` (image: `/out/usage.jsonl`) | ledger path (appended, fsync per row) |
| `GATEWAY_STATUS_FILE` | `--status-file` | none (image: `/out/gateway-status.json`) | status JSON, rewritten atomically after every call |
| `GATEWAY_BUDGET_USD` | `--budget` | `0.50` | per-game credits, USD at the pinned prices |
| `GATEWAY_RUN_ID` | `--run-id` | empty | copied into every row |
| `OPENROUTER_API_KEY` | (name set by `--key-env` / `GATEWAY_KEY_ENV`) | required | the real key. Read once, removed from the process environment, never logged |
| `GATEWAY_UPSTREAM` | `--upstream` | `https://openrouter.ai/api/v1` | must be https (http only with `--allow-http-upstream`, for tests) |
| `GATEWAY_MAX_BODY_BYTES` | `--max-body-bytes` | 16 MiB | request size cap (413 above) |
| `GATEWAY_MAX_RESPONSE_BYTES` | `--max-response-bytes` | 32 MiB | an upstream response larger than this is treated as usage unknown |
| `GATEWAY_MAX_CONCURRENCY` | `--max-concurrency` | 4 | in-flight upstream calls per game; more wait in the queue (`queue_wait_s`, the harness's time) |
| `GATEWAY_THROTTLE_ATTRIB_INFLIGHT` | `--throttle-attrib-inflight` | 2 | 429 time is the provider's (`throttle_wait_s`: excluded from the wall cap, counted by the throttling infra rule) only on calls admitted with at most this many of the game's calls in flight; otherwise it is the harness's (`throttle_wait_harness_s`) |
| `GATEWAY_UPSTREAM_TIMEOUT_S` | `--upstream-timeout` | 180 | idle limit per socket wait (headers, then each read) |
| `GATEWAY_UPSTREAM_DEADLINE_S` | `--upstream-deadline` | 320 | limit on one attempt, checked between reads (an attempt ends by deadline + one idle wait) |
| `GATEWAY_MAX_UPSTREAM_TIMEOUTS` | `--max-upstream-timeouts` | 5 | hung or lost calls tolerated per game; one more blocks it (`upstream_unreliable`) |
| `GATEWAY_ABANDON_OUTPUT_TOKENS` | `--abandon-output-tokens` | 32768 | output tokens charged, at most, for an abandoned call (below) |
| `GATEWAY_RETRY_ATTEMPTS` | `--retry-attempts` | 6 | attempts per call, including the first |
| `GATEWAY_RETRY_MAX_WAIT_S` | `--retry-max-wait` | 300 | max throttle time per call before the error goes back to the harness |
| `GATEWAY_RETRY_BASE_S`, `GATEWAY_RETRY_AFTER_CAP_S` | `--retry-base`, `--retry-after-cap` | 2, 60 | backoff: `Retry-After` if sent, else base·2^(n-1); both capped |
| `GATEWAY_DEBUG=1` | `--debug` | off | adds the forwarded request and the response to each ledger row. **Off in the runner** |

Compose sketch (the runner owns the real file):

```yaml
gateway:
  build: ./gateway            # or the pinned image
  environment: {OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}, GATEWAY_BUDGET_USD: "0.50", GATEWAY_RUN_ID: ${RUN_ID}}
  volumes: ["./out/gateway:/out"]
  networks: [game_internal, egress]
```

## Endpoints

Only these two; everything else is 404 (405 for other methods).

- `POST /v1/chat/completions`: OpenAI chat format, non-streaming. The harness's `Authorization` header is ignored.
- `GET /status`: `{"schema": "dfbench-gateway-status/1", run_id, budget_usd, spent_usd, remaining_usd, reserved_usd,
  inflight, calls, calls_refused, calls_upstream_error, upstream_timeouts, usage_unknown_calls, provider_mismatches, tokens{prompt,
  cached, completion, reasoning}, openrouter_cost_usd, retries, throttle_wait_total_s, blocked, blocked_reason,
  price_table_hash, models{<id>: {provider}}, upstream_host, started_at}`. `blocked_reason` is null,
  `budget_exhausted`, `usage_missing`, `upstream_unreliable` or `ledger_unreadable`. The harness can read it too (its own spend is not
  secret); the runner and game server use it for the wall-cap exclusion and the "credits ran out" end.

## Requests

- **Model allowlist:** `model` must be a key of `prices.json` `models`, exactly (`z-ai/glm-5.3-flash`; no `:nitro`
  or other variants). Otherwise 400 `model_not_allowed`, not forwarded.
- **Forwarded as sent:** `messages, tools, tool_choice, parallel_tool_calls, temperature, top_p, top_k, min_p, top_a,
  frequency_penalty, presence_penalty, repetition_penalty, logit_bias, logprobs, top_logprobs, max_tokens,
  max_completion_tokens, stop, seed, n, response_format, reasoning, reasoning_effort, include_reasoning, verbosity`.
  The harness chooses reasoning effort and max_tokens.
- **Set by the gateway:** `provider` = the table's pin (`{"order": ["together"], "allow_fallbacks": false}`),
  `usage: {"include": true}`, `stream: false`.
- **Dropped** (listed per row in `dropped_fields`): everything else, including `provider`, `models`, `route`,
  `transforms`, `plugins`, `web_search_options`, `preset`, `user`, `usage`, `stream_options` and unknown fields. An
  allowlist, so a new OpenRouter routing or billing field can't slip through.
- **Text and function tools only:** a message's `content` must be a string, null or a list of `{"type": "text"}`
  parts, and every `tools` entry must be `{"type": "function", ...}`. Anything else (`image_url`, `file`,
  `input_audio`, server-side tools) → 400 `content_not_allowed`, not forwarded: those make the provider fetch a URL
  or run a tool, a channel into or out of the sealed game network.
- `stream: true` → 400 `stream_unsupported`. Bodies need a `Content-Length` (411 otherwise) and at most
  `max-body-bytes`.
- The upstream response body goes back to the harness unchanged (it includes OpenRouter's `usage` and `provider`).

## Pricing

`prices.json` (schema `dfbench-prices/1`, USD per million tokens) per model: `input`, `cached_input`, `output`,
`max_output_tokens` (for reservations), the `provider` pin and the expected `provider_name`. The pin is in the table so
one hash covers prices and routing. **`price_table_hash` = `sha256:` + sha256 of the file's bytes**, today
`sha256:547d7f992e4e8356cadf8fd92428e475b28b791c25e7728c9f1b0d209d857162` (check: `shasum -a 256 gateway/prices.json`).
Prices: Together's endpoint on OpenRouter, 2026-10-23: $0.15/M input, $0.03/M cached input, $0.50/M output.

cost = (prompt_tokens − cached_tokens)·input + cached_tokens·cached_input + completion_tokens·output. OpenRouter's
`completion_tokens` include reasoning tokens, so `reasoning_tokens` is recorded but not priced twice. OpenRouter's own
`usage.cost` is recorded beside it (`openrouter_cost_usd`); the budget uses the pinned price only. On the 2026-10-23
end-to-end check the two agreed to the last digit.

## Ledger: `usage.jsonl` (contract §6)

One row per request that reached the model logic (refusals included, so the ledger is a full audit), compact JSON:

| field | meaning |
|---|---|
| `schema`, `seq`, `run_id`, `price_table_hash` | `dfbench-usage/1`; 1-based sequence |
| `t_start`, `t_end`, `latency_s` | unix seconds; total time in the gateway |
| `outcome` | `ok`, `upstream_error`, `upstream_timeout`, `usage_missing`, `refused_model`, `refused_stream`, `refused_too_large`, `refused_budget_exhausted`, `refused_usage_missing`, `refused_upstream_unreliable` |
| `model`, `provider`, `provider_mismatch`, `generation_id`, `finish_reason` | from the response; mismatch = provider ≠ the table's `provider_name` |
| `prompt_tokens`, `cached_tokens`, `cache_write_tokens`, `completion_tokens`, `reasoning_tokens` | upstream usage |
| `cost_usd`, `openrouter_cost_usd`, `spent_after_usd` | pinned-price cost (null when unknown), OpenRouter's, running total |
| `reservation_usd`, `exceeded_reservation`, `cost_upper_bound_usd` | the admission estimate (below); the bound is set when usage is unknown |
| `upstream_status`, `attempts`, `retry_statuses`, `throttle_wait_s`, `upstream_latency_s`, `queue_wait_s` | throttling (below); `queue_wait_s` = time waiting for in-flight calls at admission |
| `request_digest`, `request_bytes`, `n_messages`, `n_tools`, `max_tokens`, `reasoning`, `dropped_fields` | sha256 of the exact forwarded body; no prompt text |
| `error` | ≤ 200 chars of the upstream error message |
| `failure`, `cost_basis` | `upstream_timeout` rows only: `deadline`, `idle_timeout`, `connection_lost` or `provider_reported`; `abandoned_estimate` or `prompt_estimate` |

A restarted gateway replays its ledger first, so a restart can't reset the spend or lift a block.

## Budget semantics

- Before forwarding: refuse with **HTTP 402** `{"error": {"code": "budget_exhausted", "reason", "spent_usd",
  "budget_usd"}}` if spent ≥ budget.
- A call that crosses the budget finishes and is **counted in full** (never clipped). Every later call is refused.
- **Concurrency (reservations):** each call reserves an upper bound on its cost while in flight: every forwarded body
  byte as one uncached input token (+256 + 16 per message for the chat template) plus `max_tokens` (or the model's
  `max_output_tokens` when absent) of output, times `n`. A call is admitted when nothing else is in flight, or when
  spent + in-flight reservations + its own reservation ≤ budget; otherwise it **waits** (not refused) for in-flight
  calls to finish, then rechecks. A call admitted alone whose reservation is over the remaining budget has its
  `max_tokens` **clamped** so that its reservation fits (the row says `clamped_max_tokens`); if not even one output
  token fits, it gets 402 `insufficient_budget` and the game is not blocked. So no call can spend past the budget by
  asking for a huge `max_tokens` or `n`; the overshoot left is the one crossing call's actual cost.
  Consequence for harnesses: parallel calls need a `max_tokens`; without one the reservation is the model's ~944k
  output tokens (~$0.47), so such calls effectively run one at a time. The bound assumes `completion_tokens` ≤
  `max_tokens` (true on OpenRouter); a row where the actual cost beat the estimate says `exceeded_reservation: true`.

## Hung and lost calls

About 1% of calls in the 2026-10-23 season-0 runs hung for ~300 s and then came back as a 200 whose body was only an
error ("A Timeout Occurred", "Upstream error from Together: The upstream model stream ended unexpectedly"), with no
usage. Failing those closed made most long games infra, so a call that was **sent and came back with no usable
response** is an `upstream_timeout` instead:

- **which calls:** the gateway's deadline or idle limit ran out (`deadline`, `idle_timeout`), the connection broke after
  sending (`connection_lost`), or the body is only the provider's error: an `error` object, no `choices`, no `usage`
  (`provider_reported`).
- **charge:** the harness got no content, so this is not unmetered inference; it is charged an estimate, never null.
  - `provider_reported` → `prompt_estimate`: the prompt at the reservation's bound (body bytes + overhead, uncached
    input price). OpenRouter's error docs: "you may still be charged for the prompt processing cost by the upstream
    provider, even if no content is generated".
  - abandoned (`deadline`, `idle_timeout`, `connection_lost`) → `abandoned_estimate`: the prompt bound plus output up to
    `max_tokens`, capped at `--abandon-output-tokens`, times `n`. OpenRouter's streaming docs: "For non-streaming
    requests …, the model will continue processing and you will be billed for the complete response." The charge is
    an estimate, not a bound: a runaway completion the gateway abandoned can cost the organiser more, at most
    `max-upstream-timeouts` times per game.

  The 320 s deadline sits just above OpenRouter's own ~300 s cut-off, so a hung call usually ends as
  `provider_reported` (prompt only) rather than abandoned. In 2,937 priced calls of those runs, p99.9 latency was 25 s
  and the maximum 139 s, under both limits. 
- **reply:** HTTP 504 `{"error": {"code": "upstream_timeout", "failure", "charged_usd", "retryable": true}}` with
  `Retry-After: 2`. The harness may retry. The gateway itself doesn't, so one hang costs one charge and one wait.
- **whose timeout:** a call that asked for more than `--infra-max-output-tokens` (8,192) of output (or omitted
  `max_tokens`) can run past the deadline on its own, so its timeout is the harness's: the row says
  `harness_attributable: true` and the 504 says `counted_as_infra: false`. Such timeouts are charged the same, but
  their time is **not** excluded from the wall cap and they **don't** count towards the limit below. Otherwise a
  harness could re-roll a bad game as infra by asking for long generations on purpose.
- **wall cap:** an attributable-to-the-provider call's time counts as `throttle_wait_s` (provider time, excluded from
  the wall cap like throttling).
- **limit:** more than `max-upstream-timeouts` (5) provider-attributable timeouts in one game, and every later call
  gets 503 `gateway_blocked` (`reason: upstream_unreliable`). The game runs on unmanaged, and the runner and scorer
  mark it infra (re-run).
- **oversized responses** (over `max-response-bytes`, e.g. a large `n` with `top_logprobs`): charged the call's
  reservation (`cost_basis: reservation_oversized`), 502 `response_too_large`, the game goes on. Not infra.
- `GET /status` `upstream_timeouts` counts them, and a restarted gateway replays them from the ledger.

## Fail closed

A response whose usage can't be priced while it may have carried content (a 200 with `choices` but without `usage`,
non-integer tokens, cached > prompt), or an oversized response: the row says `usage_missing` with
`cost_usd: null` and `cost_upper_bound_usd`, the harness gets 502 `usage_missing`, and **every later call gets 503
`gateway_blocked`** (`reason: usage_missing`). The game goes on unmanaged, as when credits run out. The runner should
treat `usage_unknown_calls > 0` as an infra flag. Not billed, not blocking: upstream errors without usage (4xx, and
429/5xx after retries; passed through with their status) and connection failures before sending (502
`upstream_unreachable`). A non-200 that carries usage is charged.

## Throttle accounting (contract §4 wall cap)

Upstream 429, any 5xx, and connection failures before sending are retried inside the gateway: up to
`retry-attempts`, waiting `Retry-After` (capped) or exponential backoff, while the call's throttle time stays under
`retry-max-wait`. **`throttle_wait_s`** per row = the durations of the failed attempts + the backoff sleeps (the
final successful attempt is normal latency; a final failed one is throttle time too). `GET /status`
`throttle_wait_total_s` is the running sum; the game server subtracts it from the wall clock. Other 4xx are not
retried. Note that overlapping parallel calls each count their own waits, so the total can exceed wall time when a
harness runs parallel calls into a 429 storm (see open problems).

## Security notes

- The key is read from the env var once and popped from `os.environ`; it appears only in the upstream
  `Authorization` header. It is never in the ledger, status, stderr or error messages (tested). It is still visible to
  anyone who can `docker inspect` the container, so only the runner should have Docker access.
- Listens only on `--listen`; two endpoints; no access log; request size bounded (16 MiB, `Content-Length` required);
  response size bounded; client socket timeout 120 s; listen backlog 128.
- Upstream: https only; **redirects are never followed** (a 3xx becomes 502 `upstream_redirect`); environment proxy
  variables are ignored (`ProxyHandler({})`).
- No prompt text in any log unless `--debug`; rows carry a request digest instead.
- The harness can't change routing or billing identity: allowlisted fields only, the provider pin is overwritten.

## Tests

```sh
python3.12 -m unittest discover -s gateway/tests -v      # ~25 s, no network
```

A fake upstream covers: pass-through (fields, body, key replaced), model allowlist, provider override and field
stripping, provider mismatch, pricing and the price hash, budget crossing and refusal, missing or malformed usage →
fail closed, hung calls (idle timeout, deadline after early headers with trickled whitespace, provider-reported
timeout) → charged 504 and not blocking, too many → `upstream_unreliable` (and replayed), 429/503 retry and throttle accounting (and retries exhausted), 4xx not
retried or billed, redirects not followed, concurrency (overshoot ≤ one call; serialised without `max_tokens`),
ledger replay on restart, size limits and endpoints, the key never written, the debug flag, bad price tables.

End-to-end, 2026-10-23 (Docker image, real OpenRouter, 2 calls + 1 refused): both served by **Together**, tool calls
correct; 160 + 20 and 160 + 45 (25 reasoning) tokens; $0.0000340 and $0.0000465 at the pinned prices, equal to
OpenRouter's `usage.cost`; a harness-sent `provider: fireworks` and `models` were dropped; `openai/gpt-4o-mini` refused.

## Contract mapping

- §2: `gateway` service, holds the key, harness reaches `http://gateway:8080/v1`; `DFBENCH_TASK.model.api_key` is a
  placeholder the gateway ignores. `budget.credits` = `GATEWAY_BUDGET_USD`.
- §1: the key's model condition = model id + `provider` pin + `price_table_hash`, all in `GET /status`.
- §4 wall cap: `throttle_wait_total_s`. "Credits run out" = `blocked_reason` non-null.
- §6: `usage.jsonl` as above.
